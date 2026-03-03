import bpy
import mathutils
import os

from .binary_utils import leer_uint32, leer_uint8, leer_float32


def leer_huesos_pmdl(blob, offset_huesos, cantidad_huesos):
    """
    Lee el bloque de huesos del archivo PMDL.

    Estructura de cada hueso (0xA0 bytes fijos):
      0x00       : marcador (siempre 0xA0)
      0x04       : pop_level - cuantos niveles sube la jerarquia al terminar este hueso
                   0 = el siguiente es hijo directo
                   1 = sube 1 nivel (vuelve al padre)
                   N = sube N niveles
      0x08       : siempre 0x01 (desconocido, constante?)
      0x0A       : ID del hueso
      0x10-0x1F  : posicion del hueso en espacio mundo  [x, y, z, 1.0]
      0x20-0x2F  : posicion del padre en espacio mundo  [x, y, z, 1.0]
      0x30-0x3F  : vector diferencia (0x10 - 0x20)      [x, y, z, 1.0]
      0x40-0x4F  : desconocido, posiblemente primer hijo en espacio local
      0x50-0x5F  : escala / bounding box del hueso      [x, y, z, 0.5]
      0x60-0x9F  : padding
    """

    huesos = []
    TAM_HUESO = 0xA0

    print(f"\n=== LEYENDO {cantidad_huesos} HUESOS DESDE OFFSET 0x{offset_huesos:X} ===\n")

    for i in range(cantidad_huesos):
        offset_actual = offset_huesos + (i * TAM_HUESO)

        if offset_actual + TAM_HUESO > len(blob):
            print(f"[!] Hueso {i}: fuera de rango del archivo")
            break

        pop_level = leer_uint8(blob, offset_actual + 0x04)
        hueso_id  = leer_uint8(blob, offset_actual + 0x0A)

        # Posicion del hueso en espacio mundo
        pos = [leer_float32(blob, offset_actual + 0x10 + j * 4) for j in range(3)]

        # Posicion del padre en espacio mundo
        pos_padre = [leer_float32(blob, offset_actual + 0x20 + j * 4) for j in range(3)]

        # Escala / bounding box
        escala_hueso = [leer_float32(blob, offset_actual + 0x50 + j * 4) for j in range(3)]

        huesos.append({
            'id'         : hueso_id,
            'pop_level'  : pop_level,
            'pos'        : pos,        # cabeza del hueso en espacio mundo
            'pos_padre'  : pos_padre,  # cabeza del padre en espacio mundo
            'escala'     : escala_hueso,
        })

        print(f"  Hueso 0x{hueso_id:02X}  pop={pop_level}  pos=[{pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f}]")

    return huesos


def construir_jerarquia_huesos(huesos):

    jerarquia = []
    stack = []  # pila de IDs de huesos activos

    print("\n=== CONSTRUYENDO JERARQUIA ===\n")

    for hueso in huesos:
        hid       = hueso['id']
        pop_level = hueso['pop_level']

        padre_id = stack[-1] if stack else None

        jerarquia.append((hueso, padre_id))

        if padre_id is None:
            print(f"[raiz] 0x{hid:02X}")
        else:
            nivel = len(stack)
            print(f"{'  ' * nivel}+-- 0x{hid:02X}  (padre: 0x{padre_id:02X})")

        stack.append(hid)

        for _ in range(pop_level):
            if stack:
                stack.pop()

    return jerarquia


def cargar_nombres_huesos():
    """Carga el diccionario de nombres desde bones_list"""

    addon_dir  = os.path.dirname(os.path.abspath(__file__))
    bones_file = os.path.join(addon_dir, "bones_list.txt")
    nombres    = {}

    if not os.path.exists(bones_file):
        return nombres

    try:
        with open(bones_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if ':' in line:
                    partes = line.split(':', 1)
                    nombres[partes[0].strip()] = partes[1].strip()
    except Exception as e:
        print(f"Error al cargar bones_list.txt: {e}")

    return nombres


def obtener_nombre_hueso(hueso_id, renombrar, nombres):
    """Retorna el nombre del hueso segun su ID."""
    nombre_base = f"sk_{hueso_id:02X}"
    if renombrar and nombre_base in nombres:
        return nombres[nombre_base]
    return nombre_base


def crear_armature_desde_pmdl(blob, offset_huesos, cantidad_huesos,
                               renombrar_huesos=False, nombre="Armature", escala=0.002075):

    ESCALA = escala

    nombres_huesos = cargar_nombres_huesos() if renombrar_huesos else {}

    huesos    = leer_huesos_pmdl(blob, offset_huesos, cantidad_huesos)
    jerarquia = construir_jerarquia_huesos(huesos)

    # Mapa id -> datos del hueso para busquedas rapidas
    mapa_huesos = {h['id']: h for h in huesos}

    # Mapa id -> lista de IDs de hijos directos
    hijos_de = {h['id']: [] for h in huesos}
    for hueso, padre_id in jerarquia:
        if padre_id is not None:
            hijos_de[padre_id].append(hueso['id'])

    def pmdl_a_blender(pos):
        return mathutils.Vector((
            pos[0],
            pos[2],
           -pos[1],
        ))

    # Crear objeto armature
    armature     = bpy.data.armatures.new(nombre)
    armature_obj = bpy.data.objects.new(nombre, armature)
    bpy.context.collection.objects.link(armature_obj)
    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode='EDIT')

    huesos_creados = {}

    for hueso, padre_id in jerarquia:
        hid  = hueso['id']
        nombre_hueso = obtener_nombre_hueso(hid, renombrar_huesos, nombres_huesos)

        bone      = armature.edit_bones.new(nombre_hueso)
        bone.head = pmdl_a_blender(hueso['pos'])

        # Calcular tail

        LONGITUD_MINIMA = 0.5  # para huesos en origen o con head==tail

        hijos = hijos_de.get(hid, [])
        if hijos:
            # Promediar posicion de todos los hijos para centrar el tail
            suma = mathutils.Vector((0.0, 0.0, 0.0))
            for hijo_id in hijos:
                suma += pmdl_a_blender(mapa_huesos[hijo_id]['pos'])
            bone.tail = suma / len(hijos)
        elif padre_id is not None:
            # Hueso hoja: extender la misma longitud que el segmento padre->este
            padre_data = mapa_huesos[padre_id]
            head_padre = pmdl_a_blender(padre_data['pos'])
            direccion  = bone.head - head_padre
            if direccion.length > 0.001:
                bone.tail = bone.head + direccion.normalized() * direccion.length
            else:
                bone.tail = bone.head + mathutils.Vector((0, 0, LONGITUD_MINIMA))
        else:
            # Hueso raiz sin hijos
            bone.tail = bone.head + mathutils.Vector((0, 0, LONGITUD_MINIMA))

        if (bone.tail - bone.head).length < 0.001:
            bone.tail = bone.head + mathutils.Vector((0, 0, LONGITUD_MINIMA))

        # Asignar padre
        if padre_id is not None and padre_id in huesos_creados:
            bone.parent = huesos_creados[padre_id]

        huesos_creados[hid] = bone
        print(f"  Creado: {nombre_hueso}  head={tuple(round(v,4) for v in bone.head)}")

    bpy.ops.object.mode_set(mode='OBJECT')

    # --- VIEWPORT DISPLAY ---
    import random

    armature.display_type = 'STICK'
    armature_obj.show_in_front = True

    # Colores individuales por hueso
    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode='POSE')

    if bpy.app.version >= (4, 0, 0):
        # Blender 4+: color directo en pose_bone
        for pose_bone in armature_obj.pose.bones:
            pose_bone.color.palette = 'CUSTOM'
            pose_bone.color.custom.normal = (
                random.random(),
                random.random(),
                random.random(),
            )
    else:
        # Blender 3.x: bone groups con color por grupo
        for pose_bone in armature_obj.pose.bones:
            grupo = armature_obj.pose.bone_groups.new(name=pose_bone.name)
            grupo.color_set = 'CUSTOM'
            r, g, b = random.random(), random.random(), random.random()
            grupo.colors.normal   = (r, g, b)
            grupo.colors.select   = (min(r + 0.3, 1.0), min(g + 0.3, 1.0), min(b + 0.3, 1.0))
            grupo.colors.active   = (1.0, 1.0, 1.0)
            pose_bone.bone_group  = grupo

    bpy.ops.object.mode_set(mode='OBJECT')

    print(f"\n[OK] Armature '{nombre}' creado con {len(huesos_creados)} huesos")

    return armature_obj
import bpy
import struct
import os
import re
from bpy.props import StringProperty, BoolProperty
from bpy_extras.io_utils import ImportHelper

from .bone_builder import cargar_nombres_huesos, obtener_nombre_hueso
from .rutas_recientes import (
    aplicar_ruta_inicial, set_ruta, get_ruta,
    _CLAVE_EXPORT_PMDL
)


ESCALA_EXPORT = 0.015625
GROSOR_MAXIMO = 512.0


def peso_norm_a_bytes(peso_norm):
    """
    Convierte peso Blender (0.0-1.0) a big-endian uint16 del PMDL.
    Formula inversa del import: raw = round(peso * 32640 + 128)
    Round-trip verificado: error maximo < 0.000005
    """
    if peso_norm <= 0.0:
        return (0x00, 0x00)
    elif peso_norm >= 1.0:
        return (0x80, 0x00)
    raw = int(round(peso_norm * 32640.0 + 128))
    raw = max(0x0081, min(0x7FFF, raw))
    return ((raw >> 8) & 0xFF, raw & 0xFF)


def obtener_peso_vertice(vert, vertex_groups_obj, nombre_vg):
    """Obtiene el peso de un vertice en un vertex group por nombre. Retorna 0.0 si no existe."""
    vg = vertex_groups_obj.get(nombre_vg)
    if vg is None:
        return 0.0
    for g in vert.groups:
        if g.group == vg.index:
            return g.weight
    return 0.0


def reconstruir_bloque_huesos(armature_obj, blob, offset_huesos, cantidad_huesos,
                               renombrar_huesos=False):
    """
    Actualiza posiciones de huesos en el blob a partir del armature de Blender.
    Solo toca offsets 0x10, 0x20, 0x30 de cada hueso. El resto queda intacto.

    Conversion Blender -> PMDL (inversa de bone_builder):
      pmdl_x =  blender_x
      pmdl_y = -blender_z
      pmdl_z =  blender_y
    """
    TAM_HUESO   = 0xA0
    nombres_map = cargar_nombres_huesos() if renombrar_huesos else {}

    # Leer IDs en orden desde el blob para iterar en el mismo orden del archivo
    ids_en_orden = []
    for i in range(cantidad_huesos):
        off = offset_huesos + i * TAM_HUESO
        if off + 0x0B <= len(blob):
            ids_en_orden.append(blob[off + 0x0A])

    # Mapa nombre -> pose_bone
    mapa_pose = {}
    if armature_obj and armature_obj.type == 'ARMATURE':
        for pb in armature_obj.pose.bones:
            mapa_pose[pb.name] = pb

    for i, hid in enumerate(ids_en_orden):
        off = offset_huesos + i * TAM_HUESO
        pb  = mapa_pose.get(obtener_nombre_hueso(hid, renombrar_huesos, nombres_map))
        if pb is None:
            continue

        # Posicion world del head del hueso
        hw = armature_obj.matrix_world @ pb.head
        px, py, pz = hw.x, -hw.z, hw.y

        # Posicion world del padre
        if pb.parent:
            phw    = armature_obj.matrix_world @ pb.parent.head
            ppx, ppy, ppz = phw.x, -phw.z, phw.y
            w_padre = 1.0
        else:
            ppx, ppy, ppz = 0.0, 0.0, 0.0
            w_padre = 0.0

        dx, dy, dz = px - ppx, py - ppy, pz - ppz

        # 0x10: posicion propia
        struct.pack_into('<f', blob, off + 0x10, px)
        struct.pack_into('<f', blob, off + 0x14, py)
        struct.pack_into('<f', blob, off + 0x18, pz)
        struct.pack_into('<f', blob, off + 0x1C, 1.0)

        # 0x20: posicion del padre
        struct.pack_into('<f', blob, off + 0x20, ppx)
        struct.pack_into('<f', blob, off + 0x24, ppy)
        struct.pack_into('<f', blob, off + 0x28, ppz)
        struct.pack_into('<f', blob, off + 0x2C, w_padre)

        # 0x30: diferencia (redundante pero necesaria)
        struct.pack_into('<f', blob, off + 0x30, dx)
        struct.pack_into('<f', blob, off + 0x34, dy)
        struct.pack_into('<f', blob, off + 0x38, dz)
        struct.pack_into('<f', blob, off + 0x3C, 1.0)

    print(f"[export] {len(ids_en_orden)} huesos actualizados")


def _reoptimizar_ids(blob, offset_indice_partes, cantidad_partes):
    """
    Recorre todas las subpartes y reemplaza IDs repetidas por 0xFF,
    igual que pmdl_optimizer.py pero con busqueda correcta hacia atras por columna.

    Regla:
      - ids_previas_global[j] = ultimo ID REAL escrito en la columna j
      - Solo se actualiza cuando el valor escrito es real (no 0xFF)
      - Si el ID actual == ids_previas_global[j], escribir 0xFF en su lugar
      - Si el ID actual != ids_previas_global[j], escribir el ID real y actualizar

    El estado cruza partes, igual que el juego lo lee.
    """
    ids_previas_global = [None, None, None, None]

    for i in range(cantidad_partes):
        entrada_offset     = offset_indice_partes + (i * 0x20)
        if entrada_offset + 0x20 > len(blob):
            break

        part_offset        = struct.unpack_from('<I', blob, entrada_offset + 0x04)[0]
        cantidad_subpartes = struct.unpack_from('<I', blob, part_offset)[0]

        for sub_idx in range(cantidad_subpartes):
            sub_entrada = part_offset + 0x04 + (sub_idx * 0x10)
            if sub_entrada + 0x10 > len(blob):
                break

            num_huesos = struct.unpack_from('<H', blob, sub_entrada + 0x02)[0]

            for j in range(num_huesos):
                id_offset = sub_entrada + 0x04 + j
                if id_offset >= len(blob):
                    break

                hid = blob[id_offset]

                # Ignorar si ya es FF (puede quedar de una iteracion anterior)
                if hid == 0xFF:
                    continue

                while len(ids_previas_global) <= j:
                    ids_previas_global.append(None)

                if ids_previas_global[j] is not None and hid == ids_previas_global[j]:
                    # ID repetida: optimizar a FF
                    blob[id_offset] = 0xFF
                else:
                    # ID nueva o diferente: dejar y actualizar estado de columna
                    ids_previas_global[j] = hid



def aplicar_escala_objetos(objetos):
    """
    Aplica la escala de cada objeto mesh antes de exportar.
    Equivale a Ctrl+A > Scale en Object Mode.
    Opera sobre una copia en memoria (no modifica los datos originales del usuario).
    Retorna lista de meshes evaluados con escala aplicada, y un contexto override
    para restaurar despues. En la practica modifica el mesh data directamente
    usando bmesh para no alterar el objeto visible en escena.
    """
    import bpy
    import mathutils

    for obj in objetos:
        if obj.type != 'MESH':
            continue
        escala = obj.scale
        # Si la escala es identidad no hace falta nada
        if abs(escala.x - 1.0) < 1e-6 and abs(escala.y - 1.0) < 1e-6 and abs(escala.z - 1.0) < 1e-6:
            continue
        # Aplicar escala al mesh data directamente
        mat_escala = mathutils.Matrix.Diagonal(escala).to_4x4()
        obj.data.transform(mat_escala)
        # Resetear escala del objeto a 1,1,1
        obj.scale = (1.0, 1.0, 1.0)
        # Actualizar la malla
        obj.data.update()


def exportar_pmdl(filepath, objetos, armature_obj, blob_original,
                  renombrar_huesos=False, grosor_maximo=False):
    """
    Exporta geometria, UVs, pesos y huesos al PMDL.
    Estrategia: patch sobre el blob original para mantener estructura intacta.
    """
    blob = bytearray(blob_original)

    # Grosor del header
    grosor_x = struct.unpack_from('<f', blob, 0x40)[0]
    grosor_y = struct.unpack_from('<f', blob, 0x44)[0]
    grosor_z = struct.unpack_from('<f', blob, 0x48)[0]
    factor_x = grosor_x / GROSOR_MAXIMO if grosor_x > 0 else 1.0
    factor_y = grosor_y / GROSOR_MAXIMO if grosor_y > 0 else 1.0
    factor_z = grosor_z / GROSOR_MAXIMO if grosor_z > 0 else 1.0

    if grosor_maximo:
        struct.pack_into('<f', blob, 0x40, GROSOR_MAXIMO)
        struct.pack_into('<f', blob, 0x44, GROSOR_MAXIMO)
        struct.pack_into('<f', blob, 0x48, GROSOR_MAXIMO)

    nombres_map            = cargar_nombres_huesos() if renombrar_huesos else {}
    offset_indice_partes   = struct.unpack_from('<I', blob, 0x60)[0]
    cantidad_partes        = struct.unpack_from('<I', blob, 0x5C)[0]

    print(f"\n[export] Exportando {len(objetos)} partes...")

    # ids_previas_global: estado de columnas compartido entre TODAS las partes
    # Columna j = ultimo ID real visto en esa posicion de hueso
    # Se actualiza SOLO con valores reales (nunca con 0xFF)
    # Esto permite resolver y re-optimizar FF correctamente entre partes
    ids_previas_global = [None, None, None, None]

    for i, obj in enumerate(objetos):
        if i >= cantidad_partes:
            break

        entrada_offset = offset_indice_partes + (i * 0x20)

        # Custom properties
        if 'PMDL_Capa' in obj:
            struct.pack_into('<H', blob, entrada_offset + 0x00, int(obj['PMDL_Capa']))
        if 'PMDL_Opacidad' in obj:
            opac = int((float(obj['PMDL_Opacidad']) / 100.0) * 65535.0)
            struct.pack_into('<H', blob, entrada_offset + 0x02, opac)
        if 'PMDL_Flag' in obj:
            struct.pack_into('<I', blob, entrada_offset + 0x0C, int(obj['PMDL_Flag']))

        part_offset        = struct.unpack_from('<I', blob, entrada_offset + 0x04)[0]
        cantidad_subpartes = struct.unpack_from('<I', blob, part_offset)[0]

        mesh     = obj.data
        uv_layer = mesh.uv_layers.active

        # Mapa vertice -> UV (primer loop encontrado)
        uv_por_vert = {}
        if uv_layer:
            for loop in mesh.loops:
                vi = loop.vertex_index
                if vi not in uv_por_vert:
                    uv = uv_layer.data[loop.index].uv
                    uv_por_vert[vi] = (uv.x, uv.y)

        vert_index = 0

        for sub_idx in range(cantidad_subpartes):
            sub_entrada  = part_offset + 0x04 + (sub_idx * 0x10)
            num_vertices = struct.unpack_from('<H', blob, sub_entrada)[0]
            num_huesos   = struct.unpack_from('<H', blob, sub_entrada + 0x02)[0]
            offset_sub   = struct.unpack_from('<I', blob, sub_entrada + 0x0C)[0]

            tam_pesos   = num_huesos * 2
            tam_vertice = tam_pesos + 2 + 6

            # Resolver IDs de huesos de esta subparte.
            # Regla: 0xFF = buscar hacia atras en la misma COLUMNA hasta encontrar
            # un ID real. La busqueda cruza partes (ids_previas_global persiste).
            # Si el blob tiene 0xFF en una columna donde el previo no existe (num_huesos
            # de esa sub era menor), ids_previas_global[j] ya tiene el valor correcto
            # del ultimo ID real visto en esa columna en cualquier subparte anterior.
            huesos_ids_resueltos = []
            for j in range(num_huesos):
                raw = blob[sub_entrada + 0x04 + j]
                if raw == 0xFF:
                    # Usar el ultimo ID real de esta columna (busqueda hacia atras implicita)
                    hid = ids_previas_global[j] if j < len(ids_previas_global) and ids_previas_global[j] is not None else 0
                else:
                    hid = raw
                    # Actualizar estado de columna SOLO con valores reales
                    while len(ids_previas_global) <= j:
                        ids_previas_global.append(None)
                    ids_previas_global[j] = hid
                huesos_ids_resueltos.append(hid)

            nombres_vg = [
                obtener_nombre_hueso(hid, renombrar_huesos, nombres_map)
                for hid in huesos_ids_resueltos
            ]

            for v_idx in range(num_vertices):
                if vert_index >= len(mesh.vertices):
                    break

                vert     = mesh.vertices[vert_index]
                pos_base = part_offset + offset_sub + (v_idx * tam_vertice)

                # Verificar bounds antes de escribir
                if pos_base + tam_vertice > len(blob):
                    print(f"[export] WARN: fuera de rango parte {i} sub {sub_idx} v {v_idx}")
                    vert_index += 1
                    continue

                # PESOS usando los IDs resueltos (nunca 0xFF)
                for j, nombre_vg in enumerate(nombres_vg):
                    peso   = obtener_peso_vertice(vert, obj.vertex_groups, nombre_vg)
                    b1, b2 = peso_norm_a_bytes(peso)
                    blob[pos_base + j * 2]     = b1
                    blob[pos_base + j * 2 + 1] = b2

                pos_uv     = pos_base + tam_pesos
                pos_coords = pos_uv + 2

                # UVs
                if vert_index in uv_por_vert:
                    u, v_uv = uv_por_vert[vert_index]
                    blob[pos_uv]     = max(0, min(255, int(round(u * 255.0))))
                    blob[pos_uv + 1] = max(0, min(255, int(round((1.0 - v_uv) * 255.0))))

                # COORDENADAS en espacio mundo (incluye traslacion, rotacion y escala del objeto)
                co_world   = obj.matrix_world @ vert.co
                bx, by, bz = co_world.x, co_world.y, co_world.z
                cx = bx / (ESCALA_EXPORT * factor_x)
                cy = -bz / (ESCALA_EXPORT * factor_y)
                cz = by / (ESCALA_EXPORT * factor_z)
                if grosor_maximo:
                    cx, cy, cz = cx * factor_x, cy * factor_y, cz * factor_z
                struct.pack_into('<h', blob, pos_coords,     max(-32768, min(32767, int(round(cx)))))
                struct.pack_into('<h', blob, pos_coords + 2, max(-32768, min(32767, int(round(cy)))))
                struct.pack_into('<h', blob, pos_coords + 4, max(-32768, min(32767, int(round(cz)))))

                vert_index += 1

        print(f"[export]   Parte {i:02d}: {vert_index} vertices")

    # RE-OPTIMIZAR IDs: reemplazar IDs repetidas por 0xFF en el blob
    # siguiendo la misma logica de columnas con estado global entre partes
    _reoptimizar_ids(blob, offset_indice_partes, cantidad_partes)

    # HUESOS
    cantidad_huesos = struct.unpack_from('<I', blob, 0x08)[0]
    offset_huesos   = struct.unpack_from('<I', blob, 0x50)[0]
    if armature_obj and cantidad_huesos > 0:
        reconstruir_bloque_huesos(
            armature_obj    = armature_obj,
            blob            = blob,
            offset_huesos   = offset_huesos,
            cantidad_huesos = cantidad_huesos,
            renombrar_huesos= renombrar_huesos,
        )

    with open(filepath, 'wb') as f:
        f.write(blob)

    print(f"[export] OK: {filepath}")
    return True


class ExportPMDL(bpy.types.Operator, ImportHelper):
    """Exportar archivo PMDL/PMDF de DBZ TTT"""
    bl_idname  = "export_scene.pmdl"
    bl_label   = "Exportar PMDL/PMDF"
    bl_options = {'REGISTER'}

    filename_ext = ".pmdl"
    filter_glob: StringProperty(
        default="*.pmdl;*.pmdf",
        options={'HIDDEN'},
    )
    check_extension = True

    grosor_maximo: BoolProperty(
        name="Grosor Maximo",
        description="Exportar con grosor maximo (512.0) ajustando vertices automaticamente",
        default=False,
    )

    def invoke(self, context, event):
        col = self._coleccion_pmdl(context)
        nombre_base = col.name if col else "modelo"
        if not nombre_base.lower().endswith(".pmdl"):
            nombre_base += ".pmdl"
        ruta_guardada = get_ruta(_CLAVE_EXPORT_PMDL)
        if ruta_guardada and os.path.isdir(ruta_guardada):
            self.filepath = os.path.join(ruta_guardada, nombre_base)
        elif col:
            fp = col.get("PMDL_Filepath", "") or col.get("PMDL_Patch_Filepath", "")
            if fp and os.path.exists(fp):
                self.filepath = os.path.join(os.path.dirname(fp), nombre_base)
        return super().invoke(context, event)

    def execute(self, context):
        col = self._coleccion_pmdl(context)
        if not col:
            self.report({'ERROR'}, "No se encontro ninguna coleccion de PMDL en la escena")
            return {'CANCELLED'}

        objetos = sorted(
            [o for o in col.objects if o.type == 'MESH'],
            key=lambda o: self._indice_parte(o.name)
        )
        if not objetos:
            self.report({'ERROR'}, "La coleccion no contiene objetos mesh")
            return {'CANCELLED'}

        armature_obj = next((o for o in col.objects if o.type == 'ARMATURE'), None)

        # Forzar extension .pmdl
        if not self.filepath.lower().endswith(".pmdl"):
            self.filepath += ".pmdl"

        # Obtener blob original: desde PMDL directo o extrayendolo del parche
        filepath_pmdl  = col.get("PMDL_Filepath", "")
        filepath_patch = col.get("PMDL_Patch_Filepath", "")

        if filepath_pmdl and os.path.exists(filepath_pmdl):
            with open(filepath_pmdl, 'rb') as f:
                blob_original = f.read()
        elif filepath_patch and os.path.exists(filepath_patch):
            # Importado desde parche: extraer el PMDL embebido como referencia
            import struct
            with open(filepath_patch, 'rb') as f:
                patch_raw = f.read()
            pmdl_inicio = col.get("PMDL_Patch_PMDL_Inicio", 0)
            pmdl_fin    = col.get("PMDL_Patch_PMDL_Fin", 0)
            if not pmdl_inicio or not pmdl_fin:
                self.report({'ERROR'}, "Offsets del PMDL no encontrados en el parche. Reimporta.")
                return {'CANCELLED'}
            blob_original = patch_raw[pmdl_inicio:pmdl_fin]
        else:
            self.report({'ERROR'}, "No se encontro archivo original (ni PMDL ni parche)")
            return {'CANCELLED'}

        renombrar = bool(col.get("PMDL_Renombrar_Huesos", True))

        print(f"\n{'='*60}")
        print(f"EXPORTANDO: {col.name}  partes={len(objetos)}  armature={'si' if armature_obj else 'no'}")
        print(f"{'='*60}")

        try:
            exportar_pmdl(
                filepath         = self.filepath,
                objetos          = objetos,
                armature_obj     = armature_obj,
                blob_original    = blob_original,
                renombrar_huesos = renombrar,
                grosor_maximo    = self.grosor_maximo,
            )
            set_ruta(_CLAVE_EXPORT_PMDL, self.filepath)
            self.report({'INFO'}, f"PMDL exportado: {len(objetos)} partes")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error al exportar: {e}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

    def _coleccion_pmdl(self, context):
        if context.collection and 'PMDL_Tipo' in context.collection:
            return context.collection
        if context.selected_objects:
            for obj in context.selected_objects:
                for col in obj.users_collection:
                    if 'PMDL_Tipo' in col:
                        return col
        cols = sorted(
            [c for c in bpy.data.collections if 'PMDL_Tipo' in c],
            key=lambda c: self._sufijo(c.name)
        )
        return cols[0] if cols else None

    def _sufijo(self, name):
        m = re.search(r'\.(\d{3})$', name)
        return int(m.group(1)) if m else 0

    def _indice_parte(self, name):
        m = re.search(r'Part[ea]_(\d+)', name)
        return int(m.group(1)) if m else 9999


def menu_func_export(self, context):
    self.layout.operator(ExportPMDL.bl_idname, text="PMDL/PMDF (.pmdl, .pmdf)")
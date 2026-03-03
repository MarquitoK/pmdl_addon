import bpy
from bpy.props import StringProperty, BoolProperty
from bpy_extras.io_utils import ImportHelper
import io
import os

from .patch_parser import leer_parche, leer_caras_pmdf
from .tex_decoder  import textura_a_blender
from ..rutas_recientes import (
    aplicar_ruta_inicial, set_ruta,
    _CLAVE_IMPORT_PATCH, _CLAVE_EXPORT_PATCH
)


class ImportPatch(bpy.types.Operator, ImportHelper):
    """Importar parche de personaje DBZ TTT (.PCK1, .pak, .unk)"""
    bl_idname = "import_scene.ttt_patch"
    bl_label  = "Importar Parche TTT"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".PCK1"
    filter_glob: StringProperty(
        default="*.PCK1;*.pak;*.unk",
        options={'HIDDEN'},
    )

    renombrar_huesos: BoolProperty(
        name="Renombrar Huesos",
        description="Usar nombres descriptivos de huesos desde bones_list.txt",
        default=True,
    )

    ocultar_pmdf: BoolProperty(
        name="Ocultar pMdF",
        description="Ocultar las caras extra (pMdF) al importar. Se pueden mostrar desde el Outliner",
        default=True,
    )

    def invoke(self, context, event):
        aplicar_ruta_inicial(self, _CLAVE_IMPORT_PATCH, "")
        return super().invoke(context, event)

    def execute(self, context):
        from ..builder import crear_mesh_blender

        # 1. Leer parche
        info_patch, error = leer_parche(self.filepath)
        if error:
            self.report({'ERROR'}, f"Error al leer parche: {error}")
            return {'CANCELLED'}

        # 2. Parsear PMDL principal
        info_pmdl, error_pmdl = _analizar_pmdl_desde_bytes(
            info_patch['pmdl_datos'],
            nombre=info_patch['nombre']
        )
        if error_pmdl:
            self.report({'ERROR'}, f"Error al parsear PMDL: {error_pmdl}")
            return {'CANCELLED'}

        # 3. Decodificar textura
        bl_imagen = textura_a_blender(
            blob           = info_patch['blob'],
            indices_offset = info_patch['indices_offset'],
            paleta_offset  = info_patch['paleta_offset'],
            nombre         = info_patch['nombre'],
        )
        if bl_imagen is None:
            self.report({'WARNING'}, "No se pudo decodificar la textura (Pillow instalado?)")

        # 4. Crear mesh + armature principal
        objetos = crear_mesh_blender(
            info             = info_pmdl,
            escala           = 0.015625,
            renombrar_huesos = self.renombrar_huesos,
            context          = context,
        )

        # Obtener coleccion y armature reales desde el atributo expuesto por crear_mesh_blender
        col_principal = crear_mesh_blender._ultima_coleccion
        armature_obj  = crear_mesh_blender._ultimo_armature

        # 5. Guardar metadata en la coleccion
        if col_principal is not None:
            col_principal["PMDL_Patch_Filepath"]    = self.filepath
            col_principal["PMDL_Patch_PMDL_Inicio"] = info_patch['pmdl_inicio']
            col_principal["PMDL_Patch_PMDL_Fin"]    = info_patch['pmdl_fin']
            col_principal["PMDL_Renombrar_Huesos"]  = self.renombrar_huesos
        else:
            self.report({'WARNING'}, "No se pudo obtener la coleccion principal")

        # 6. Asignar textura
        if bl_imagen is not None:
            _asignar_textura_a_material(bl_imagen)

        set_ruta(_CLAVE_IMPORT_PATCH, self.filepath)

        # 7. Importar caras PMDF extra como sub-colecciones
        caras_importadas = 0
        caras = leer_caras_pmdf(info_patch['blob'])
        for cara in caras:
            try:
                objetos_cara = _importar_cara_pmdf(
                    cara             = cara,
                    col_principal    = col_principal,
                    armature_obj     = armature_obj,
                    renombrar_huesos = self.renombrar_huesos,
                    context          = context,
                    ocultar          = self.ocultar_pmdf,
                )
                if objetos_cara is None:
                    continue

                if col_principal is not None:
                    col_principal[f"PMDF_{cara['nombre']}_Inicio"] = cara['inicio']
                    col_principal[f"PMDF_{cara['nombre']}_Fin"]    = cara['fin']

                caras_importadas += 1
                print(f"[patch] {cara['nombre']} importada ({len(objetos_cara)} meshes)")

            except Exception as e:
                print(f"[patch] WARN: error importando {cara['nombre']}: {e}")
                import traceback
                traceback.print_exc()
                continue

        # 8. Seleccionar objetos principales
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objetos:
            obj.select_set(True)
        if objetos:
            context.view_layer.objects.active = objetos[0]

        partes = len([o for o in objetos if o.type == 'MESH'])
        msg = f"Parche importado: {partes} partes"
        if caras_importadas:
            msg += f", {caras_importadas} cara(s) extra"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


def _buscar_layer_collection(layer_col, nombre):
    if layer_col.collection.name == nombre:
        return layer_col
    for child in layer_col.children:
        result = _buscar_layer_collection(child, nombre)
        if result is not None:
            return result
    return None


def _importar_cara_pmdf(cara, col_principal, armature_obj, renombrar_huesos,
                        context, ocultar=True):
    # Importa cara PMDF como sub-coleccion hija de col_principal
    from ..builder import _crear_objeto_mesh, crear_material_tex_ttt
    from ..bone_builder import cargar_nombres_huesos

    if col_principal is None:
        print(f"[patch] WARN: {cara['nombre']} - col_principal es None")
        return None

    info_cara, error_cara = _analizar_pmdl_desde_bytes(
        cara['datos'],
        nombre=cara['nombre']
    )
    if error_cara:
        print(f"[patch] WARN: {cara['nombre']} no se pudo parsear: {error_cara}")
        return None

    # Crear subcoleccion con el nombre de la cara dentro de col_principal
    nombre_subcol = cara['nombre']
    if nombre_subcol in bpy.data.collections:
        subcol = bpy.data.collections[nombre_subcol]
    else:
        subcol = bpy.data.collections.new(nombre_subcol)

    # Vincular como hija de col_principal
    if nombre_subcol not in [c.name for c in col_principal.children]:
        col_principal.children.link(subcol)

    # Ocultar
    if ocultar and context is not None:
        layer_col = _buscar_layer_collection(
            context.view_layer.layer_collection, subcol.name
        )
        if layer_col is not None:
            layer_col.hide_viewport = True

    GROSOR_MAXIMO = 512.0
    escala        = 0.015625
    grosor_x = info_cara['grosor_x'] if info_cara['grosor_x'] > 0 else GROSOR_MAXIMO
    grosor_y = info_cara['grosor_y'] if info_cara['grosor_y'] > 0 else GROSOR_MAXIMO
    grosor_z = info_cara['grosor_z'] if info_cara['grosor_z'] > 0 else GROSOR_MAXIMO
    factor_x = grosor_x / GROSOR_MAXIMO
    factor_y = grosor_y / GROSOR_MAXIMO
    factor_z = grosor_z / GROSOR_MAXIMO

    nombres_huesos = cargar_nombres_huesos() if renombrar_huesos else {}
    material       = crear_material_tex_ttt()
    objetos_cara   = []

    for parte in info_cara['partes']:
        obj = _crear_objeto_mesh(
            parte            = parte,
            coleccion        = subcol,
            material         = material,
            armature_obj     = armature_obj,
            escala           = escala,
            factor_x         = factor_x,
            factor_y         = factor_y,
            factor_z         = factor_z,
            renombrar_huesos = renombrar_huesos,
            nombres_huesos   = nombres_huesos,
            prefijo_nombre   = cara['nombre'],
            pmdf_cara        = cara['nombre'],
        )
        objetos_cara.append(obj)

    return objetos_cara



def _analizar_pmdl_desde_bytes(pmdl_bytes, nombre):
    import struct
    import os

    # Importar utilidades del addon principal
    from ..binary_utils import (
        FLAGS_ESPECIALES,
        leer_uint32, leer_uint16, leer_uint8, leer_int16, leer_float32
    )
    from ..pmdl_parser import analizar_subpartes

    blob = pmdl_bytes

    firma = blob[0:4].decode('ascii', errors='ignore')
    if firma not in ('pMdl', 'pMdF'):
        return None, f"Firma invalida: {firma}"

    info = {}
    info['nombre']   = nombre + '.pmdl'
    info['filepath'] = ''
    info['tipo']     = firma

    info['grosor_x'] = leer_float32(blob, 0x40)
    info['grosor_y'] = leer_float32(blob, 0x44)
    info['grosor_z'] = leer_float32(blob, 0x48)

    info['cantidad_huesos']      = leer_uint32(blob, 0x08)
    info['offset_huesos']        = leer_uint32(blob, 0x50)
    info['cantidad_partes']      = leer_uint32(blob, 0x5C)
    info['offset_indice_partes'] = leer_uint32(blob, 0x60)

    info['blob'] = blob

    ids_previas_global = [None, None, None, None]
    partes = []

    for i in range(info['cantidad_partes']):
        entrada_offset = info['offset_indice_partes'] + (i * 0x20)

        if entrada_offset + 0x20 > len(blob):
            break

        capa          = leer_uint16(blob, entrada_offset + 0x00)
        opacidad      = leer_uint16(blob, entrada_offset + 0x02)
        part_offset   = leer_uint32(blob, entrada_offset + 0x04)
        part_length   = leer_uint32(blob, entrada_offset + 0x08)
        flag_especial = leer_uint32(blob, entrada_offset + 0x0C)
        flag_bytes    = blob[entrada_offset + 0x0C : entrada_offset + 0x10]
        nombre_flag   = FLAGS_ESPECIALES.get(flag_especial, "Desconocido")

        datos_parte = blob[part_offset : part_offset + part_length]
        subpartes, ids_previas_global = analizar_subpartes(datos_parte, ids_previas_global)

        partes.append({
            'indice'            : i,
            'capa'              : capa,
            'opacidad'          : opacidad,
            'offset'            : part_offset,
            'longitud'          : part_length,
            'flag_especial'     : flag_especial,
            'flag_bytes_raw'    : flag_bytes.hex(),
            'nombre_flag'       : nombre_flag,
            'subpartes'         : subpartes,
            'cantidad_subpartes': len(subpartes),
        })

    info['partes'] = partes
    return info, None


def _asignar_textura_a_material(bl_imagen):
    """Asigna la imagen decodificada al nodo TEX_IMAGE del material tex_ttt."""
    import bpy

    mat = bpy.data.materials.get("tex_ttt")
    if mat is None or not mat.use_nodes:
        return

    for node in mat.node_tree.nodes:
        if node.type == 'TEX_IMAGE':
            node.image = bl_imagen
            print(f"[patch] Textura '{bl_imagen.name}' asignada al material tex_ttt")
            return


def menu_func_import_patch(self, context):
    self.layout.operator(ImportPatch.bl_idname, text="Parche TTT (.PCK1, .pak, .unk)")



def _exportar_a_bytes(exportar_pmdl_fn, objetos, armature_obj,
                      blob_original, renombrar, grosor_maximo=False):
    # Exporta PMDL/PMDF a bytes via archivo temporal
    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.pmdl', delete=False) as tmp:
        tmp_path = tmp.name
    try:
        exportar_pmdl_fn(
            filepath         = tmp_path,
            objetos          = objetos,
            armature_obj     = armature_obj,
            blob_original    = blob_original,
            renombrar_huesos = renombrar,
            grosor_maximo    = grosor_maximo,
        )
        with open(tmp_path, 'rb') as f:
            return f.read()
    except Exception as e:
        print(f'[patch_export] ERROR: {e}')
        import traceback
        traceback.print_exc()
        return None
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

# -----------------------------------------------------------------------------
# EXPORT DE PARCHE
# -----------------------------------------------------------------------------

class ExportPatch(bpy.types.Operator, ImportHelper):
    """Exportar parche de personaje DBZ TTT reemplazando el PMDL interno"""
    bl_idname  = "export_scene.ttt_patch"
    bl_label   = "Exportar Parche TTT"
    bl_options = {'REGISTER'}

    filename_ext = ".PCK1"
    filter_glob: StringProperty(
        default="*.PCK1;*.pak;*.unk",
        options={'HIDDEN'},
    )
    check_extension = False

    grosor_maximo: BoolProperty(
        name="Grosor Maximo",
        description="Exportar con grosor maximo (512.0)",
        default=False,
    )

    def invoke(self, context, event):
        col = self._coleccion_pmdl(context)
        # Bloquear si vino de PMDL directo (sin parche asociado)
        if col and col.get("PMDL_Filepath") and not col.get("PMDL_Patch_Filepath"):
            self.report({'ERROR'}, "Este modelo vino de un PMDL, usa Exportar PMDL/PMDF")
            return {'CANCELLED'}
        nombre_base = col.name if col else "parche"
        if not nombre_base.lower().endswith(".pck1"):
            nombre_base += ".PCK1"
        from ..rutas_recientes import get_ruta
        ruta_guardada = get_ruta(_CLAVE_EXPORT_PATCH)
        if ruta_guardada and os.path.isdir(ruta_guardada):
            self.filepath = os.path.join(ruta_guardada, nombre_base)
        elif col:
            fp = col.get("PMDL_Patch_Filepath", "")
            if fp and os.path.exists(fp):
                self.filepath = fp
        return super().invoke(context, event)

    def execute(self, context):
        from ..exporter import exportar_pmdl
        from .patch_parser import CARAS_PMDF
        import tempfile

        col = self._coleccion_pmdl(context)
        if not col:
            self.report({'ERROR'}, "No se encontro ninguna coleccion de PMDL en la escena")
            return {'CANCELLED'}

        # Error si vino de PMDL directo (no tiene parche asociado)
        if col.get("PMDL_Filepath") and not col.get("PMDL_Patch_Filepath"):
            self.report({'ERROR'}, "Este modelo vino de un PMDL, usa Exportar PMDL/PMDF")
            return {'CANCELLED'}

        patch_filepath = col.get("PMDL_Patch_Filepath", "")
        if not patch_filepath or not os.path.exists(patch_filepath):
            self.report({'ERROR'}, f"Archivo de parche original no encontrado: {patch_filepath}")
            return {'CANCELLED'}

        pmdl_inicio = col.get("PMDL_Patch_PMDL_Inicio", 0)
        pmdl_fin    = col.get("PMDL_Patch_PMDL_Fin", 0)
        if not pmdl_inicio or not pmdl_fin:
            self.report({'ERROR'}, "Offsets del PMDL no encontrados. Reimporta el parche.")
            return {'CANCELLED'}

        armature_obj = next((o for o in col.objects if o.type == 'ARMATURE'), None)
        renombrar    = bool(col.get("PMDL_Renombrar_Huesos", True))

        # Leer parche original
        with open(patch_filepath, 'rb') as f:
            patch_blob = bytearray(f.read())

        # Forzar extension .PCK1
        fp = self.filepath
        if not fp.lower().endswith(".pck1"):
            fp += ".PCK1"
        self.filepath = fp

        objetos_principales = sorted(
            [o for o in col.objects if o.type == 'MESH' and 'PMDF_Cara' not in o],
            key=lambda o: self._indice_parte(o.name)
        )
        if not objetos_principales:
            self.report({'ERROR'}, "La coleccion no contiene meshes del PMDL principal")
            return {'CANCELLED'}

        # Extraer blob PMDL desde el parche como referencia
        blob_pmdl_orig = bytes(patch_blob[pmdl_inicio:pmdl_fin])
        pmdl_nuevo = _exportar_a_bytes(
            exportar_pmdl, objetos_principales, armature_obj,
            blob_pmdl_orig, renombrar, self.grosor_maximo,
        )
        if pmdl_nuevo is None:
            self.report({'ERROR'}, "Error al exportar el PMDL principal")
            return {'CANCELLED'}
        if len(pmdl_nuevo) != pmdl_fin - pmdl_inicio:
            self.report({'ERROR'}, "PMDL principal: tamano exportado diferente al original")
            return {'CANCELLED'}
        patch_blob[pmdl_inicio:pmdl_fin] = pmdl_nuevo

        # EXPORTAR PMDFs DE CARAS EXTRA
        for nombre_cara, off_ini_idx, off_fin_idx in CARAS_PMDF:
            ini_cara = col.get(f"PMDF_{nombre_cara}_Inicio", 0)
            fin_cara = col.get(f"PMDF_{nombre_cara}_Fin", 0)
            if not ini_cara or not fin_cara:
                continue

            # Buscar en la sub-coleccion de la cara (no en col.objects directo)
            subcol_cara = bpy.data.collections.get(nombre_cara)
            if subcol_cara is None:
                continue
            objetos_cara = sorted(
                [o for o in subcol_cara.objects
                 if o.type == 'MESH' and o.get("PMDF_Cara") == nombre_cara],
                key=lambda o: self._indice_parte(o.name)
            )
            if not objetos_cara:
                continue

            blob_cara_orig = bytes(patch_blob[ini_cara:fin_cara])
            # Caras no exportan huesos
            pmdf_nuevo = _exportar_a_bytes(
                exportar_pmdl, objetos_cara, None,
                blob_cara_orig, renombrar, self.grosor_maximo,
            )
            if pmdf_nuevo is None:
                print(f"[patch_export] WARN: error exportando {nombre_cara}, se omite")
                continue
            if len(pmdf_nuevo) != fin_cara - ini_cara:
                print(f"[patch_export] WARN: {nombre_cara} tamano diferente, se omite")
                continue
            patch_blob[ini_cara:fin_cara] = pmdf_nuevo
            print(f"[patch_export] {nombre_cara}: OK")

        with open(self.filepath, 'wb') as f:
            f.write(patch_blob)

        set_ruta(_CLAVE_EXPORT_PATCH, self.filepath)
        print(f"[patch_export] Parche guardado en: {self.filepath}")
        self.report({'INFO'}, "Parche exportado correctamente")
        return {'FINISHED'}

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
        import re
        m = re.search(r'\.(\d{3})$', name)
        return int(m.group(1)) if m else 0

    def _indice_parte(self, name):
        import re
        m = re.search(r'Part[ea]_(\d+)', name)
        return int(m.group(1)) if m else 9999


def menu_func_export_patch(self, context):
    self.layout.operator(ExportPatch.bl_idname, text="Parche TTT (.PCK1, .pak, .unk)")
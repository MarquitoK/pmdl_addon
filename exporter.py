import bpy
import struct
import os
import re
from bpy.props import StringProperty, BoolProperty
from bpy_extras.io_utils import ImportHelper


class ExportPMDL(bpy.types.Operator, ImportHelper):
    bl_idname = "export_scene.pmdl"
    bl_label = "Exportar PMDL/PMDF"
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
        # Intentar obtener la ruta del archivo original desde la coleccion activa
        if context.collection and "PMDL_Filepath" in context.collection:
            filepath_original = context.collection["PMDL_Filepath"]
            if filepath_original and os.path.exists(filepath_original):
                self.filepath = filepath_original

        return super().invoke(context, event)

    def execute(self, context):
        # Buscar coleccion de PMDL activa o seleccionada
        coleccion_pmdl = None

        # Intentar usar la coleccion activa primero
        if context.collection and "PMDL_Tipo" in context.collection:
            coleccion_pmdl = context.collection
        else:
            # Buscar entre las seleccionadas
            if context.selected_objects:
                for obj in context.selected_objects:
                    for col in obj.users_collection:
                        if "PMDL_Tipo" in col:
                            coleccion_pmdl = col
                            break
                    if coleccion_pmdl:
                        break

        # Si no hay seleccion, buscar coleccion por defecto
        if not coleccion_pmdl:
            colecciones_pmdl = []
            for col in bpy.data.collections:
                if "PMDL_Tipo" in col:
                    colecciones_pmdl.append(col)

            if not colecciones_pmdl:
                self.report({'ERROR'}, "No se encontro ninguna coleccion de PMDL en la escena.")
                return {'CANCELLED'}

            # Ordenar colecciones por sufijo
            def extraer_sufijo_coleccion(col_name):
                match = re.search(r'\.(\d{3})$', col_name)
                if match:
                    return int(match.group(1))
                return 0  # Sin sufijo = prioridad maxima

            colecciones_pmdl_ordenadas = sorted(colecciones_pmdl, key=lambda c: extraer_sufijo_coleccion(c.name))
            coleccion_pmdl = colecciones_pmdl_ordenadas[0]

            print(f"\n[!] No hay seleccion, exportando coleccion por defecto: {coleccion_pmdl.name}")

        # Obtener SOLO los objetos que pertenecen a esta coleccion especifica
        objetos_coleccion = []

        for obj in coleccion_pmdl.objects:
            if obj.type != 'MESH':
                continue
            objetos_coleccion.append(obj)

        if not objetos_coleccion:
            self.report({'ERROR'}, "La coleccion no contiene objetos mesh")
            return {'CANCELLED'}

        # Ordenar objetos por indice de parte (extraido del nombre)
        def extraer_indice_parte(obj):
            obj_name = obj.name if isinstance(obj, bpy.types.Object) else str(obj)
            # Buscar patron "Parte_XX" o "Part_XX"
            match = re.search(r'Part[ea]_(\d+)', obj_name)
            if match:
                return int(match.group(1))
            return 9999  # Si no encuentra, poner al final

        objetos = sorted(objetos_coleccion, key=extraer_indice_parte)

        # Obtener filepath original si existe
        filepath_original = coleccion_pmdl.get("PMDL_Filepath", "")

        # Debug: Mostrar que se va a exportar
        print(f"\n{'='*60}")
        print(f"EXPORTANDO PMDL: {coleccion_pmdl.name}")
        print(f"{'='*60}")
        print(f"Coleccion: {coleccion_pmdl.name}")
        print(f"Archivo original: {filepath_original}")
        print(f"Cantidad de partes: {len(objetos)}")
        print(f"Partes a exportar:")
        for i, obj in enumerate(objetos):
            print(f"  {i:2d}. {obj.name}")
        print(f"{'='*60}\n")

        try:
            exportar_pmdl(self.filepath, objetos, context, filepath_original, self.grosor_maximo)
            self.report({'INFO'}, f"PMDL '{coleccion_pmdl.name}' exportado exitosamente ({len(objetos)} partes)")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Error al exportar: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}


def exportar_pmdl(filepath, objetos, context, filepath_original="", grosor_maximo=False):
    # Si no se especifico un archivo original, usar el filepath de destino
    if not filepath_original or not os.path.exists(filepath_original):
        filepath_original = filepath

    # Leer el PMDL original primero para mantener la estructura
    if not os.path.exists(filepath_original):
        raise FileNotFoundError(f"No se encontro el archivo PMDL original: {filepath_original}")

    with open(filepath_original, 'rb') as f:
        pmdl_original = bytearray(f.read())

    # Calcular factores de grosor desde el header original
    grosor_x_original = struct.unpack_from("<f", pmdl_original, 0x40)[0]
    grosor_y_original = struct.unpack_from("<f", pmdl_original, 0x44)[0]
    grosor_z_original = struct.unpack_from("<f", pmdl_original, 0x48)[0]

    GROSOR_MAXIMO = 512.0  # 0x44000000 en float = 512.0

    # Si se solicita grosor maximo, actualizar el header
    if grosor_maximo:
        struct.pack_into("<f", pmdl_original, 0x40, GROSOR_MAXIMO)
        struct.pack_into("<f", pmdl_original, 0x44, GROSOR_MAXIMO)
        struct.pack_into("<f", pmdl_original, 0x48, GROSOR_MAXIMO)

    escala = 0.002075  # Escala por defecto usada en import

    # Actualizar vertices en el PMDL original
    offset_indice_partes = struct.unpack_from("<I", pmdl_original, 0x60)[0]
    cantidad_partes = struct.unpack_from("<I", pmdl_original, 0x5C)[0]

    for i, obj in enumerate(objetos):
        if i >= cantidad_partes:
            break

        entrada_offset = offset_indice_partes + (i * 0x20)

        # Actualizar capa, opacidad y flag desde custom properties
        if "PMDL_Capa" in obj:
            capa_nueva = int(obj["PMDL_Capa"])
            struct.pack_into("<H", pmdl_original, entrada_offset + 0x00, capa_nueva)

        if "PMDL_Opacidad" in obj:
            # Convertir de 0-100 a 0-65535
            opacidad_porcentaje = float(obj["PMDL_Opacidad"])
            opacidad_hex = int((opacidad_porcentaje / 100.0) * 65535.0)
            struct.pack_into("<H", pmdl_original, entrada_offset + 0x02, opacidad_hex)

        if "PMDL_Flag" in obj:
            flag_nuevo = int(obj["PMDL_Flag"])
            struct.pack_into("<I", pmdl_original, entrada_offset + 0x0C, flag_nuevo)

        # Leer info de esta parte desde el indice
        part_offset = struct.unpack_from("<I", pmdl_original, entrada_offset + 0x04)[0]

        # Leer cantidad de subpartes
        cantidad_subpartes = struct.unpack_from("<I", pmdl_original, part_offset)[0]

        # Obtener mesh data
        mesh = obj.data
        uv_layer = mesh.uv_layers.active

        if not uv_layer:
            continue

        vert_index = 0

        # Procesar cada subparte
        for sub_idx in range(cantidad_subpartes):
            subparte_entrada = part_offset + 0x04 + (sub_idx * 0x10)
            num_vertices = struct.unpack_from("<H", pmdl_original, subparte_entrada)[0]
            num_huesos = struct.unpack_from("<H", pmdl_original, subparte_entrada + 0x02)[0]
            offset_subparte = struct.unpack_from("<I", pmdl_original, subparte_entrada + 0x0C)[0]

            tamano_pesos = num_huesos * 2
            tamano_vertice = tamano_pesos + 2 + 6

            # Actualizar cada vertice
            for v_idx in range(num_vertices):
                if vert_index >= len(mesh.vertices):
                    break

                vert = mesh.vertices[vert_index]
                pos_vertice = part_offset + offset_subparte + (v_idx * tamano_vertice)

                # Saltar pesos
                pos_vertice += tamano_pesos

                # Actualizar UVs (convertir de float 0-1 a int 0-255)
                uv_x_int = 0
                uv_y_int = 0

                for loop in mesh.loops:
                    if loop.vertex_index == vert_index and uv_layer:
                        uv = uv_layer.data[loop.index].uv
                        uv_x_int = int(round(uv.x * 255.0))
                        uv_y_int = int(round((1.0 - uv.y) * 255.0))
                        # Clampear a rango valido
                        uv_x_int = max(0, min(255, uv_x_int))
                        uv_y_int = max(0, min(255, uv_y_int))
                        break

                pmdl_original[pos_vertice] = uv_x_int
                pmdl_original[pos_vertice + 1] = uv_y_int
                pos_vertice += 2

                # Blender coords -> PMDL coords
                x_blender = vert.co.x
                y_blender = vert.co.y
                z_blender = vert.co.z

                # Revertir escala y factores de grosor ORIGINALES (sin grosor maximo)
                factor_x_original = grosor_x_original / GROSOR_MAXIMO if grosor_x_original > 0 else 1.0
                factor_y_original = grosor_y_original / GROSOR_MAXIMO if grosor_y_original > 0 else 1.0
                factor_z_original = grosor_z_original / GROSOR_MAXIMO if grosor_z_original > 0 else 1.0

                coord_x = int(round(x_blender / (escala * factor_x_original)))
                coord_z = int(round(y_blender / (escala * factor_z_original)))
                coord_y = int(round(-z_blender / (escala * factor_y_original)))

                # Si se exporta con grosor maximo, escalar las coordenadas
                if grosor_maximo:
                    # coord_nueva = coord_original * (grosor_original / grosor_nuevo)
                    coord_x = int(round(coord_x * (grosor_x_original / GROSOR_MAXIMO)))
                    coord_y = int(round(coord_y * (grosor_y_original / GROSOR_MAXIMO)))
                    coord_z = int(round(coord_z * (grosor_z_original / GROSOR_MAXIMO)))

                # Clampear a rango int16
                coord_x = max(-32768, min(32767, coord_x))
                coord_y = max(-32768, min(32767, coord_y))
                coord_z = max(-32768, min(32767, coord_z))

                # Escribir coordenadas
                struct.pack_into("<h", pmdl_original, pos_vertice, coord_x)
                struct.pack_into("<h", pmdl_original, pos_vertice + 2, coord_y)
                struct.pack_into("<h", pmdl_original, pos_vertice + 4, coord_z)

                vert_index += 1

    # Escribir archivo modificado
    with open(filepath, 'wb') as f:
        f.write(pmdl_original)


def menu_func_export(self, context):
    self.layout.operator(ExportPMDL.bl_idname, text="PMDL/PMDF (.pmdl, .pmdf)")

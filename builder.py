import bpy
import bmesh
import os

from .bone_builder import (
    crear_armature_desde_pmdl,
    cargar_nombres_huesos,
    obtener_nombre_hueso
)


def crear_material_tex_ttt():

    if "tex_ttt" in bpy.data.materials:
        mat = bpy.data.materials["tex_ttt"]
        if not mat.use_nodes:
            mat.use_nodes = True
        return mat

    mat           = bpy.data.materials.new(name="tex_ttt")
    mat.use_nodes = True
    nodes         = mat.node_tree.nodes
    links         = mat.node_tree.links

    bsdf_node = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf_node is None:
        bsdf_node = nodes.new(type='ShaderNodeBsdfPrincipled')

    tex_node          = nodes.new(type='ShaderNodeTexImage')
    tex_node.location = (-300, 300)

    base_color = bsdf_node.inputs.get('Base Color')
    if base_color:
        links.new(tex_node.outputs['Color'], base_color)

    if bpy.app.version < (4, 0, 0):
        if 'Specular' in bsdf_node.inputs:
            bsdf_node.inputs['Specular'].default_value = 0.0
    else:
        if 'Specular IOR Level' in bsdf_node.inputs:
            bsdf_node.inputs['Specular IOR Level'].default_value = 0.0

    return mat


def establecer_viewport_solid_texture(context):
    """Establece el viewport en modo Solid con Flat lighting y Texture color."""

    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.type       = 'SOLID'
                    space.shading.light      = 'FLAT'
                    space.shading.color_type = 'TEXTURE'
                    return True
    return False


def limpiar_coleccion_vacia(context):
    col_default = bpy.data.collections.get("Collection")
    if col_default and len(col_default.objects) == 0 and len(col_default.children) == 0:
        # Desvincular de la escena y eliminar
        try:
            context.scene.collection.children.unlink(col_default)
            bpy.data.collections.remove(col_default)
        except Exception:
            pass

def _crear_objeto_mesh(parte, coleccion, material, armature_obj,
                       escala, factor_x, factor_y, factor_z,
                       renombrar_huesos, nombres_huesos,
                       prefijo_nombre="Parte", pmdf_cara=None):

    nombre_parte = f"{prefijo_nombre}_{parte['indice']:02d}"
    mesh         = bpy.data.meshes.new(nombre_parte)
    obj          = bpy.data.objects.new(nombre_parte, mesh)
    coleccion.objects.link(obj)

    opacidad_porcentaje  = (parte['opacidad'] / 65535.0) * 100.0
    obj["PMDL_Capa"]     = int(parte['capa'])
    obj["PMDL_Opacidad"] = float(opacidad_porcentaje)
    obj["PMDL_Flag"]     = int(parte['flag_especial'])

    obj.id_properties_ui("PMDL_Capa").update(
        min=0, max=65535,
        description="Capa de delineado del modelo"
    )
    obj.id_properties_ui("PMDL_Opacidad").update(
        min=0.0, max=100.0,
        description="Opacidad de la parte (0-100%)"
    )
    obj.id_properties_ui("PMDL_Flag").update(
        min=0, max=8,
        description="Flag: 0=Ninguna, 1=Equip.1, 2=Equip.2, 6=Cara, 7=Ocultable"
    )

    # Marcar si pertenece a una cara PMDF extra
    if pmdf_cara is not None:
        obj["PMDF_Cara"] = pmdf_cara

    if len(obj.data.materials) == 0:
        obj.data.materials.append(material)
    else:
        obj.data.materials[0] = material

    bm           = bmesh.new()
    uv_layer     = bm.loops.layers.uv.new("UVMap")
    deform_layer = bm.verts.layers.deform.new()

    huesos_usados = set()
    for subparte in parte['subpartes']:
        for hid in subparte['huesos_ids']:
            huesos_usados.add(hid)

    vertex_groups_map = {}
    for hid in sorted(huesos_usados):
        nombre_vg = obtener_nombre_hueso(hid, renombrar_huesos, nombres_huesos)
        vg        = obj.vertex_groups.new(name=nombre_vg)
        vertex_groups_map[hid] = vg.index

    for subparte in parte['subpartes']:
        vertices_bm = []

        for vertice in subparte['vertices']:
            x =  vertice['coord_x'] * escala * factor_x
            y =  vertice['coord_z'] * escala * factor_z
            z = -vertice['coord_y'] * escala * factor_y

            v = bm.verts.new((x, y, z))

            for hid, peso in zip(subparte['huesos_ids'], vertice['pesos']):
                if hid in vertex_groups_map and peso > 0.0:
                    v[deform_layer][vertex_groups_map[hid]] = peso

            vertices_bm.append(v)

        for i in range(len(vertices_bm) - 2):
            v1, v2, v3 = vertices_bm[i], vertices_bm[i+1], vertices_bm[i+2]
            if i % 2 == 0:
                verts_face = [v1, v2, v3]
                uv_indices = [i, i+1, i+2]
            else:
                verts_face = [v1, v3, v2]
                uv_indices = [i, i+2, i+1]

            try:
                face = bm.faces.new(verts_face)
                for j, loop in enumerate(face.loops):
                    idx = uv_indices[j]
                    if idx < len(subparte['vertices']):
                        ud            = subparte['vertices'][idx]
                        u             = ud['uv_x'] / 255.0
                        v_uv          = 1.0 - (ud['uv_y'] / 255.0)
                        loop[uv_layer].uv = (u, v_uv)
            except ValueError:
                continue

    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    bm.to_mesh(mesh)
    bm.free()

    if bpy.app.version < (4, 0, 0):
        mesh.calc_normals()
    mesh.update()

    # Parentar al armature
    if armature_obj is not None:
        obj.parent                     = armature_obj
        modifier                       = obj.modifiers.new(name="Armature", type='ARMATURE')
        modifier.object                = armature_obj
        modifier.use_vertex_groups     = True

    return obj



def crear_mesh_blender(info, escala=0.015625, renombrar_huesos=False, context=None):
    """Crea los objetos mesh y armature en Blender a partir de los datos del PMDL."""

    objetos_creados = []
    nombres_huesos  = cargar_nombres_huesos() if renombrar_huesos else {}
    nombre_sin_ext  = os.path.splitext(info['nombre'])[0]

    # Crear o reutilizar coleccion
    if nombre_sin_ext in bpy.data.collections:
        coleccion = bpy.data.collections[nombre_sin_ext]
    else:
        coleccion = bpy.data.collections.new(nombre_sin_ext)
        context.scene.collection.children.link(coleccion)

    coleccion["PMDL_Filepath"] = info.get('filepath', '')
    coleccion["PMDL_Tipo"]     = info['tipo']

    # Eliminar coleccion vacia predeterminada
    limpiar_coleccion_vacia(context)

    # --- ARMATURE ---
    armature_obj = None
    if info.get('cantidad_huesos', 0) > 0:
        nombre_armature = nombre_sin_ext
        if nombre_armature in bpy.data.armatures:
            arm_data = bpy.data.armatures[nombre_armature]
            if arm_data.users == 0:
                bpy.data.armatures.remove(arm_data)

        armature_obj = crear_armature_desde_pmdl(
            blob             = info['blob'],
            offset_huesos    = info['offset_huesos'],
            cantidad_huesos  = info['cantidad_huesos'],
            renombrar_huesos = renombrar_huesos,
            nombre           = nombre_armature,
            escala           = escala,
        )

        # Mover a la coleccion del PMDL
        for col in armature_obj.users_collection:
            col.objects.unlink(armature_obj)
        coleccion.objects.link(armature_obj)
        coleccion["PMDL_Cantidad_Huesos"] = info['cantidad_huesos']

    # --- MESH ---
    material     = crear_material_tex_ttt()
    filepath_dir = os.path.dirname(info.get('filepath', ''))
    textura_path = os.path.join(filepath_dir, nombre_sin_ext + '.png')

    if os.path.exists(textura_path):
        img_name = nombre_sin_ext + '.png'
        if img_name in bpy.data.images:
            textura_image = bpy.data.images[img_name]
            textura_image.reload()
        else:
            textura_image = bpy.data.images.load(textura_path)

        if material.use_nodes:
            for node in material.node_tree.nodes:
                if node.type == 'TEX_IMAGE':
                    node.image = textura_image
                    break

    GROSOR_MAXIMO = 512.0
    grosor_x = info['grosor_x'] if info['grosor_x'] > 0 else GROSOR_MAXIMO
    grosor_y = info['grosor_y'] if info['grosor_y'] > 0 else GROSOR_MAXIMO
    grosor_z = info['grosor_z'] if info['grosor_z'] > 0 else GROSOR_MAXIMO
    factor_x = grosor_x / GROSOR_MAXIMO
    factor_y = grosor_y / GROSOR_MAXIMO
    factor_z = grosor_z / GROSOR_MAXIMO

    for parte in info['partes']:
        obj = _crear_objeto_mesh(
            parte            = parte,
            coleccion        = coleccion,
            material         = material,
            armature_obj     = armature_obj,
            escala           = escala,
            factor_x         = factor_x,
            factor_y         = factor_y,
            factor_z         = factor_z,
            renombrar_huesos = renombrar_huesos,
            nombres_huesos   = nombres_huesos,
        )
        objetos_creados.append(obj)

    if context:
        establecer_viewport_solid_texture(context)

    # Devolver todos los objetos (armature + meshes)
    todos = []
    if armature_obj:
        todos.append(armature_obj)
    todos.extend(objetos_creados)

    # Exponer coleccion y armature para que el llamador pueda usarlos
    crear_mesh_blender._ultima_coleccion  = coleccion
    crear_mesh_blender._ultimo_armature   = armature_obj

    return todos
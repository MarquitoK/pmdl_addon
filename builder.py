import os
import bpy
import bmesh

from .pmdl_parser import (
    cargar_nombres_huesos,
    obtener_nombre_hueso,
    leer_huesos_pmdl,
    construir_jerarquia_huesos
)


def crear_armature_desde_pmdl(huesos_data, renombrar_huesos, nombres_huesos, nombre_armature="Armature"):
    print(f"\n=== CREANDO ARMATURE: {nombre_armature} ===\n")
    
    # Construir jerarquía
    jerarquia = construir_jerarquia_huesos(huesos_data)
    
    # Crear armature
    armature = bpy.data.armatures.new(nombre_armature)
    armature_obj = bpy.data.objects.new(nombre_armature, armature)
    bpy.context.collection.objects.link(armature_obj)
    
    # Entrar en modo edición
    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode='EDIT')
    
    # Diccionario para guardar los huesos creados
    huesos_creados = {}
    
    # Factor de escala (igual que los vértices)
    escala = 0.002075
    
    # Crear huesos
    for hueso_data, padre_id in jerarquia:
        hueso_id = hueso_data['id']
        fila3 = hueso_data['fila3']  # [x, y, z, w]
        
        # Obtener nombre del hueso
        nombre_hueso = obtener_nombre_hueso(hueso_id, renombrar_huesos, nombres_huesos)
        
        # Crear hueso en Blender
        bone = armature.edit_bones.new(nombre_hueso)
        
        # Extraer posición de la fila 3 (índices 0, 1, 2)
        pos_x = fila3[0]
        pos_y = fila3[1]
        pos_z = fila3[2]
        
        # Posición head del hueso (convertir de coordenadas PMDL a Blender)
        # PMDL: X, Y, Z -> Blender: X, -Z, Y
        bone.head = (
            pos_x * escala,
            -pos_z * escala,
            pos_y * escala
        )
        
        # Tail del hueso
        # Si tiene padre, extender desde el padre
        # Si no, simplemente agregar longitud en Z
        if padre_id is not None and padre_id in huesos_creados:
            bone.parent = huesos_creados[padre_id]
            # Calcular dirección desde padre hasta este hueso
            import mathutils
            direccion = mathutils.Vector(bone.head) - mathutils.Vector(bone.parent.head)
            longitud = direccion.length
            if longitud < 0.01:
                # Si está muy cerca del padre, usar longitud fija
                bone.tail = (bone.head[0], bone.head[1], bone.head[2] + 0.1)
            else:
                # Extender en la misma dirección
                bone.tail = tuple(mathutils.Vector(bone.head) + direccion.normalized() * 0.1)
        else:
            # Hueso raíz, extender hacia arriba
            bone.tail = (bone.head[0], bone.head[1], bone.head[2] + 0.1)
        
        # Guardar referencia
        huesos_creados[hueso_id] = bone
        
        print(f"✓ Creado: {nombre_hueso} en {bone.head}")
    
    # Salir de modo edición
    bpy.ops.object.mode_set(mode='OBJECT')
    
    print(f"\n✓ Armature creado con {len(huesos_creados)} huesos")
    
    return armature_obj


def crear_material_tex_ttt():
    # Verificar si ya existe
    if "tex_ttt" in bpy.data.materials:
        mat = bpy.data.materials["tex_ttt"]
        if not mat.use_nodes:
            mat.use_nodes = True
        return mat
    
    # Crear nuevo material
    mat = bpy.data.materials.new(name="tex_ttt")
    mat.use_nodes = True
    
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    
    # Buscar el Principled BSDF
    bsdf_node = None
    for node in nodes:
        if node.type == 'BSDF_PRINCIPLED':
            bsdf_node = node
            break
    
    if bsdf_node is None:
        bsdf_node = nodes.new(type='ShaderNodeBsdfPrincipled')
    
    # Crear nodo de Image Texture
    tex_node = nodes.new(type='ShaderNodeTexImage')
    tex_node.location = (-300, 300)
    
    # Conectar Image Texture al Base Color
    base_color_input = bsdf_node.inputs.get('Base Color')
    if base_color_input:
        links.new(tex_node.outputs['Color'], base_color_input)
    
    # Configurar specular a 0
    blender_version = bpy.app.version
    if blender_version < (4, 0, 0):
        if 'Specular' in bsdf_node.inputs:
            bsdf_node.inputs['Specular'].default_value = 0.0
    else:
        if 'Specular IOR Level' in bsdf_node.inputs:
            bsdf_node.inputs['Specular IOR Level'].default_value = 0.0
    
    return mat


def establecer_viewport_solid_texture(context):
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    # Establecer shading en SOLID
                    space.shading.type = 'SOLID'
                    # Lighting en FLAT
                    space.shading.light = 'FLAT'
                    # Color en TEXTURE
                    space.shading.color_type = 'TEXTURE'
                    return True
    return False


def crear_mesh_blender(info, escala=0.002075, renombrar_huesos=False, importar_huesos=False, context=None):
    objetos_creados = []
    
    # Cargar nombres de huesos si es necesario
    nombres_huesos = cargar_nombres_huesos() if renombrar_huesos else {}
    
    # Si se solicita importar solo huesos
    if importar_huesos and info.get('cantidad_huesos', 0) > 0:
        print("\n" + "="*60)
        print("MODO: IMPORTAR SOLO HUESOS (ARMATURE)")
        print("="*60)
        
        # Leer huesos del PMDL
        huesos_data = leer_huesos_pmdl(
            info['blob'],
            info['offset_huesos'],
            info['cantidad_huesos']
        )
        
        # Crear armature
        nombre_sin_ext = os.path.splitext(info['nombre'])[0]
        armature_obj = crear_armature_desde_pmdl(
            huesos_data,
            renombrar_huesos,
            nombres_huesos,
            nombre_sin_ext + "_Armature"
        )
        
        # Crear colección para el PMDL
        nombre_coleccion = nombre_sin_ext
        if nombre_coleccion in bpy.data.collections:
            coleccion = bpy.data.collections[nombre_coleccion]
        else:
            coleccion = bpy.data.collections.new(nombre_coleccion)
            context.scene.collection.children.link(coleccion)
        
        # Mover armature a la colección
        for col in armature_obj.users_collection:
            col.objects.unlink(armature_obj)
        coleccion.objects.link(armature_obj)
        
        # Guardar metadata
        coleccion["PMDL_Filepath"] = info.get('filepath', '')
        coleccion["PMDL_Tipo"] = info['tipo']
        coleccion["PMDL_Cantidad_Huesos"] = info['cantidad_huesos']
        
        return [armature_obj]
    
    # Crear material compartido
    material = crear_material_tex_ttt()
    
    # Intentar cargar textura si existe
    filepath_dir = os.path.dirname(info.get('filepath', ''))
    nombre_sin_ext = os.path.splitext(info['nombre'])[0]
    textura_path = os.path.join(filepath_dir, nombre_sin_ext + '.png')
    
    textura_image = None
    if os.path.exists(textura_path):
        # Cargar o reutilizar imagen
        if nombre_sin_ext + '.png' in bpy.data.images:
            textura_image = bpy.data.images[nombre_sin_ext + '.png']
            textura_image.reload()  # Recargar por si cambió
        else:
            textura_image = bpy.data.images.load(textura_path)
        
        # Asignar textura al material
        if material.use_nodes:
            nodes = material.node_tree.nodes
            for node in nodes:
                if node.type == 'TEX_IMAGE':
                    node.image = textura_image
                    break
    
    # Crear colección para este PMDL
    nombre_coleccion = nombre_sin_ext
    
    # Verificar si ya existe la colección
    if nombre_coleccion in bpy.data.collections:
        coleccion = bpy.data.collections[nombre_coleccion]
    else:
        coleccion = bpy.data.collections.new(nombre_coleccion)
        context.scene.collection.children.link(coleccion)
    
    # Guardar la ruta del archivo original en la colección
    coleccion["PMDL_Filepath"] = info.get('filepath', '')
    coleccion["PMDL_Tipo"] = info['tipo']
    
    # Calcular factores de escala por eje
    GROSOR_MAXIMO = 512.0  # 0x44000000 en float = 512.0
    
    grosor_x = info['grosor_x'] if info['grosor_x'] > 0 else GROSOR_MAXIMO
    grosor_y = info['grosor_y'] if info['grosor_y'] > 0 else GROSOR_MAXIMO
    grosor_z = info['grosor_z'] if info['grosor_z'] > 0 else GROSOR_MAXIMO
    
    factor_x = grosor_x / GROSOR_MAXIMO
    factor_y = grosor_y / GROSOR_MAXIMO
    factor_z = grosor_z / GROSOR_MAXIMO
    
    for parte in info['partes']:
        # Nombre simplificado
        nombre_parte = f"Parte_{parte['indice']:02d}"
        
        # Crear mesh y objeto
        mesh = bpy.data.meshes.new(nombre_parte)
        obj = bpy.data.objects.new(nombre_parte, mesh)
        
        # Agregar a la colección del PMDL (no a la colección de la escena)
        coleccion.objects.link(obj)
        
        # Convertir opacidad de 0-65535 a 0-100
        opacidad_porcentaje = (parte['opacidad'] / 65535.0) * 100.0
        
        # Propiedades personalizadas editables
        obj["PMDL_Capa"] = int(parte['capa'])
        obj["PMDL_Opacidad"] = float(opacidad_porcentaje)
        obj["PMDL_Flag"] = int(parte['flag_especial'])
        
        # Configurar UI de las propiedades
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
            description="Flag: 0=Ninguna, 1=Equip.1, 2=Equip.2, 3-5=Desconocido, 6=Cara, 7=Ocultable, 8=Desconocido"
        )
        
        # Asignar material
        if len(obj.data.materials) == 0:
            obj.data.materials.append(material)
        else:
            obj.data.materials[0] = material
        
        # Crear el mesh usando bmesh
        bm = bmesh.new()
        
        # Capa UV
        uv_layer = bm.loops.layers.uv.new("UVMap")
        
        # Crear capa de deform (para pesos)
        deform_layer = bm.verts.layers.deform.new()
        
        # Recopilar todos los huesos únicos usados en esta parte
        huesos_usados = set()
        for subparte in parte['subpartes']:
            for hueso_id in subparte['huesos_ids']:
                huesos_usados.add(hueso_id)
        
        # Crear vertex groups para cada hueso
        vertex_groups_map = {}
        for hueso_id in sorted(huesos_usados):
            nombre_vg = obtener_nombre_hueso(hueso_id, renombrar_huesos, nombres_huesos)
            vg = obj.vertex_groups.new(name=nombre_vg)
            vertex_groups_map[hueso_id] = vg.index
        
        # Procesar cada subparte como triangle strip
        for subparte in parte['subpartes']:
            vertices_bm = []
            
            # Crear vértices en Blender
            for vert_idx, vertice in enumerate(subparte['vertices']):
                # Convertir coordenadas con escala POR EJE
                # INVERTIR EJE Z (Y del juego -> Z de Blender)
                x = vertice['coord_x'] * escala * factor_x
                y = vertice['coord_z'] * escala * factor_z
                z = -vertice['coord_y'] * escala * factor_y  # INVERTIDO
                
                v = bm.verts.new((x, y, z))
                
                # Guardar coordenadas originales como atributo custom (para export preciso)
                v.index = len(vertices_bm)  # Temporal, se actualizará después
                
                # Asignar pesos a los vertex groups correspondientes
                if len(vertice['pesos']) == len(subparte['huesos_ids']):
                    for i, (hueso_id, peso) in enumerate(zip(subparte['huesos_ids'], vertice['pesos'])):
                        if hueso_id in vertex_groups_map and peso > 0.0:
                            vg_index = vertex_groups_map[hueso_id]
                            v[deform_layer][vg_index] = peso
                
                vertices_bm.append(v)
            
            # Crear triángulos usando triangle strip
            for i in range(len(vertices_bm) - 2):
                v1 = vertices_bm[i]
                v2 = vertices_bm[i + 1]
                v3 = vertices_bm[i + 2]
                
                # En triangle strip, alternar el orden del winding
                if i % 2 == 0:
                    verts_face = [v1, v2, v3]
                    uv_indices = [i, i + 1, i + 2]
                else:
                    verts_face = [v1, v3, v2]
                    uv_indices = [i, i + 2, i + 1]
                
                try:
                    face = bm.faces.new(verts_face)
                    
                    # Asignar UVs
                    for j, loop in enumerate(face.loops):
                        vert_idx = uv_indices[j]
                        if vert_idx < len(subparte['vertices']):
                            uv_data = subparte['vertices'][vert_idx]
                            # Convertir de entero 0-255 a float 0.0-1.0 para Blender
                            u = uv_data['uv_x'] / 255.0
                            v = 1.0 - (uv_data['uv_y'] / 255.0)
                            loop[uv_layer].uv = (u, v)
                except ValueError:
                    continue
        
        # Actualizar índices
        bm.verts.ensure_lookup_table()
        bm.verts.index_update()
        
        # Aplicar al mesh
        bm.to_mesh(mesh)
        bm.free()
        
        # Calcular normales (solo en Blender 3.x)
        blender_version = bpy.app.version
        if blender_version < (4, 0, 0):
            mesh.calc_normals()
        # En Blender 4.x las normales se calculan automáticamente
        
        mesh.update()
        
        objetos_creados.append(obj)
    
    # Establecer viewport en Solid con Flat + Texture
    if context:
        establecer_viewport_solid_texture(context)
    
    return objetos_creados

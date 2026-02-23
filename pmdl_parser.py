import os

from .binary_utils import (
    FLAGS_ESPECIALES,
    leer_uint32, leer_uint16, leer_uint8, leer_int16, leer_float32
)


def cargar_nombres_huesos():
    """Carga el diccionario de nombres de huesos desde bones_list.txt"""
    
    # Obtener la ruta del addon
    addon_dir = os.path.dirname(os.path.abspath(__file__))
    bones_file = os.path.join(addon_dir, "bones_list.txt")
    
    nombres_huesos = {}
    
    if not os.path.exists(bones_file):
        return nombres_huesos
    
    try:
        with open(bones_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if ':' in line:
                    # Formato: sk_00: 000_NULL
                    partes = line.split(':', 1)
                    sk_name = partes[0].strip()
                    real_name = partes[1].strip()
                    nombres_huesos[sk_name] = real_name
    except Exception as e:
        print(f"Error al cargar bones_list.txt: {e}")
    
    return nombres_huesos


def obtener_nombre_hueso(hueso_id, renombrar_huesos, nombres_huesos):
    """Retorna el nombre del hueso según su ID"""
    
    nombre_base = f"sk_{hueso_id:02X}"
    
    if renombrar_huesos and nombre_base in nombres_huesos:
        return nombres_huesos[nombre_base]
    
    return nombre_base


def leer_huesos_pmdl(blob, offset_huesos, cantidad_huesos):
    huesos = []
    tamaño_hueso = 0xA0
    
    print(f"\n=== LEYENDO {cantidad_huesos} HUESOS DESDE OFFSET 0x{offset_huesos:X} ===\n")
    
    for i in range(cantidad_huesos):
        offset_actual = offset_huesos + (i * tamaño_hueso)
        
        # Verificar que no nos salgamos del archivo
        if offset_actual + tamaño_hueso > len(blob):
            print(f"⚠️ Hueso {i}: Fuera de rango del archivo")
            break
        
        # Leer datos básicos
        marcador = leer_uint32(blob, offset_actual + 0x00)
        tipo_hueso = leer_uint8(blob, offset_actual + 0x04)
        hueso_id = leer_uint8(blob, offset_actual + 0x0A)
        
        # Leer matriz de transformación basado en el análisis
        # Fila 1 (orientación): offset 0x14, añadir 0.0 al inicio
        fila1 = [0.0]
        for j in range(3):
            fila1.append(leer_float32(blob, offset_actual + 0x14 + j*4))
        
        # Fila 2 (orientación): offset 0x44, añadir 0.0 al inicio
        fila2 = [0.0]
        for j in range(3):
            fila2.append(leer_float32(blob, offset_actual + 0x44 + j*4))
        
        # Fila 3 (posición): offset 0x50, leer los 4 valores
        fila3 = []
        for j in range(4):
            fila3.append(leer_float32(blob, offset_actual + 0x50 + j*4))
        
        hueso_data = {
            'id': hueso_id,
            'tipo': tipo_hueso,
            'marcador': marcador,
            'fila1': fila1,  # [0.0, x, y, z] - Orientación 1
            'fila2': fila2,  # [0.0, x, y, z] - Orientación 2
            'fila3': fila3,  # [x, y, z, w] - Posición + escala/flag
        }
        
        huesos.append(hueso_data)
        
        # Log detallado
        tipo_nombre = {0x00: "PADRE", 0x01: "HIJO", 0x04: "FIN"}.get(tipo_hueso, f"0x{tipo_hueso:02X}")
        print(f"Hueso {i:3d} | ID: 0x{hueso_id:02X} | Tipo: {tipo_nombre:6s} | Pos: [{fila3[0]:8.3f}, {fila3[1]:8.3f}, {fila3[2]:8.3f}]")
    
    return huesos


def construir_jerarquia_huesos(huesos):
    jerarquia = []
    padre_actual = None
    
    print("\n=== CONSTRUYENDO JERARQUÍA ===\n")
    
    for hueso in huesos:
        tipo = hueso['tipo']
        hueso_id = hueso['id']
        
        if tipo == 0x00:
            # Es un hueso padre (raíz de nuevo grupo)
            jerarquia.append((hueso, None))
            padre_actual = hueso_id
            print(f"✓ Grupo nuevo: sk_{hueso_id:02X} (PADRE)")
        
        elif tipo == 0x01:
            # Es un hueso hijo del padre actual
            jerarquia.append((hueso, padre_actual))
            print(f"  └─ sk_{hueso_id:02X} (hijo de sk_{padre_actual:02X})")
        
        elif tipo == 0x04:
            # Fin de grupo
            jerarquia.append((hueso, padre_actual))
            print(f"  └─ sk_{hueso_id:02X} (FIN de grupo)")
            padre_actual = None
        
        else:
            # Tipo desconocido, tratarlo como hijo del padre actual
            jerarquia.append((hueso, padre_actual))
            print(f"  └─ sk_{hueso_id:02X} (tipo desconocido 0x{tipo:02X})")
    
    return jerarquia


def leer_vertices(datos_parte, offset_subparte, num_vertices, num_huesos):
    vertices = []
    
    # Calcular tamaño de pesos según cantidad de huesos
    tamaño_pesos = num_huesos * 2
    
    # Tamaño total de cada vértice
    tamaño_vertice = tamaño_pesos + 2 + 6
    
    # Posición inicial de los vértices
    pos = offset_subparte
    
    for i in range(num_vertices):
        # Verificar que no nos salgamos de los datos
        if pos + tamaño_vertice > len(datos_parte):
            break
        
        # Leer pesos (2 bytes por hueso en BIG-ENDIAN)
        pesos = []
        for j in range(num_huesos):
            if pos + (j * 2) + 2 <= len(datos_parte):
                # Leer peso como uint16 BIG-ENDIAN (no little-endian)
                byte1 = leer_uint8(datos_parte, pos + (j * 2))
                byte2 = leer_uint8(datos_parte, pos + (j * 2) + 1)
                peso_raw = (byte1 << 8) | byte2  # Big-endian
                
                # Convertir de rango 0x0080-0x8000 a 0.0-1.0
                # 0x8000 (32768) = 1.0, 0x0080 (128) = 0.0
                if peso_raw <= 0x0080:
                    peso_normalizado = 0.0
                elif peso_raw >= 0x8000:
                    peso_normalizado = 1.0
                else:
                    peso_normalizado = (peso_raw - 128) / 32640.0
                
                pesos.append(peso_normalizado)
        
        # Saltar los pesos
        pos += tamaño_pesos
        
        # Leer UVs (2 bytes) - MANTENER COMO ENTEROS
        uv_x = leer_uint8(datos_parte, pos)
        uv_y = leer_uint8(datos_parte, pos + 1)
        pos += 2
        
        # Leer coordenadas (6 bytes: 2 por eje)
        coord_x = leer_int16(datos_parte, pos)
        coord_y = leer_int16(datos_parte, pos + 2)
        coord_z = leer_int16(datos_parte, pos + 4)
        pos += 6
        
        vertices.append({
            'indice': i,
            'pesos': pesos,
            'uv_x': uv_x,  # Entero 0-255
            'uv_y': uv_y,  # Entero 0-255
            'coord_x': coord_x,
            'coord_y': coord_y,
            'coord_z': coord_z
        })
    
    return vertices


def analizar_subpartes(datos_parte, ids_previas_global):
    if len(datos_parte) < 4:
        return [], ids_previas_global
    
    cantidad_subpartes = leer_uint32(datos_parte, 0x00)
    
    subpartes = []
    
    # Usar las IDs previas globales (que vienen de la parte anterior)
    ids_previas = list(ids_previas_global)  # Copiar para no modificar el original directamente
    
    for i in range(cantidad_subpartes):
        entrada_offset = 0x04 + (i * 0x10)
        
        if entrada_offset + 0x10 > len(datos_parte):
            break
        
        num_vertices = leer_uint16(datos_parte, entrada_offset + 0x00)
        num_huesos = leer_uint16(datos_parte, entrada_offset + 0x02)
        
        # Leer IDs de huesos (offset 0x04, cada ID es 1 byte)
        huesos_ids = []
        for j in range(num_huesos):
            if entrada_offset + 0x04 + j < len(datos_parte):
                hueso_id = leer_uint8(datos_parte, entrada_offset + 0x04 + j)
                
                # Si es 0xFF, usar la ID de la columna anterior (fila previa o parte previa)
                if hueso_id == 0xFF:
                    if ids_previas[j] is not None:
                        hueso_id = ids_previas[j]
                    else:
                        # Si no hay ID previa, mantener 0xFF (caso muy raro)
                        hueso_id = 0xFF
                
                huesos_ids.append(hueso_id)
                # Actualizar la ID previa para esta columna
                ids_previas[j] = hueso_id
        
        # Offset de la subparte (últimos 4 bytes del índice)
        offset_subparte = leer_uint32(datos_parte, entrada_offset + 0x0C)
        
        vertices = leer_vertices(datos_parte, offset_subparte, num_vertices, num_huesos)
        
        subpartes.append({
            'indice': i,
            'num_vertices': num_vertices,
            'num_huesos': num_huesos,
            'huesos_ids': huesos_ids,
            'offset': offset_subparte,
            'vertices': vertices
        })
    
    # Retornar las IDs actualizadas para la siguiente parte
    return subpartes, ids_previas


def analizar_pmdl(filepath):
    with open(filepath, 'rb') as f:
        blob = f.read()
    
    # Verificar firma (pMdl o pMdF)
    firma = blob[0:4].decode('ascii', errors='ignore')
    if firma not in ('pMdl', 'pMdF'):
        return None, "Error: No es un archivo PMDL/PMDF válido (firma incorrecta)"
    
    info = {}
    
    info['nombre'] = os.path.basename(filepath)
    info['filepath'] = filepath  # Guardar ruta completa para export
    info['tipo'] = firma
    
    info['huesos'] = blob[0x08]
    
    info['grosor_x'] = leer_float32(blob, 0x40)
    info['grosor_y'] = leer_float32(blob, 0x44)
    info['grosor_z'] = leer_float32(blob, 0x48)
    
    info['offset_huesos'] = leer_uint32(blob, 0x50)
    info['cantidad_partes'] = leer_uint32(blob, 0x5C)
    info['offset_indice_partes'] = leer_uint32(blob, 0x60)
    
    # Leer datos de huesos si existen
    cantidad_huesos = leer_uint32(blob, 0x08)
    offset_huesos = leer_uint32(blob, 0x50)
    
    info['cantidad_huesos'] = cantidad_huesos
    info['datos_huesos'] = None
    
    if cantidad_huesos > 0 and offset_huesos > 0:
        try:
            # Almacenar el blob completo para que leer_huesos_pmdl pueda acceder a él
            info['blob'] = blob
            info['offset_huesos'] = offset_huesos
        except Exception as e:
            print(f"⚠️ Error leyendo huesos: {e}")
    
    # Mantener IDs previas GLOBALES (a través de todas las partes)
    ids_previas_global = [None, None, None, None]
    
    partes = []
    for i in range(info['cantidad_partes']):
        entrada_offset = info['offset_indice_partes'] + (i * 0x20)
        
        if entrada_offset + 0x20 > len(blob):
            break
        
        capa = leer_uint16(blob, entrada_offset + 0x00)
        opacidad = leer_uint16(blob, entrada_offset + 0x02)
        part_offset = leer_uint32(blob, entrada_offset + 0x04)
        part_length = leer_uint32(blob, entrada_offset + 0x08)
        
        # El flag está en offset 0x0C (bytes 12-15 del índice de 32 bytes)
        flag_especial = leer_uint32(blob, entrada_offset + 0x0C)
        
        # Debug: leer los bytes raw para verificar
        flag_bytes = blob[entrada_offset + 0x0C : entrada_offset + 0x10]
        
        nombre_flag = FLAGS_ESPECIALES.get(flag_especial, f"Desconocido")
        
        datos_parte = blob[part_offset : part_offset + part_length]
        # Pasar las IDs previas globales a la función
        subpartes, ids_previas_global = analizar_subpartes(datos_parte, ids_previas_global)
        
        partes.append({
            'indice': i,
            'capa': capa,
            'opacidad': opacidad,
            'offset': part_offset,
            'longitud': part_length,
            'flag_especial': flag_especial,
            'flag_bytes_raw': flag_bytes.hex(),
            'nombre_flag': nombre_flag,
            'subpartes': subpartes,
            'cantidad_subpartes': len(subpartes)
        })
    
    info['partes'] = partes
    
    return info, None


def generar_log(info):
    log = "=" * 70 + "\n"
    log += f"ANÁLISIS DE ARCHIVO {info['tipo']} - DBZ TTT\n"
    log += "=" * 70 + "\n\n"
    
    log += f"Nombre del archivo: {info['nombre']}\n"
    log += f"Tipo: {info['tipo']}\n"
    log += f"Cantidad de huesos: {info['huesos']}\n"
    log += f"Cantidad de partes: {info['cantidad_partes']}\n"
    log += f"Grosor X: {info['grosor_x']:.2f}\n"
    log += f"Grosor Y: {info['grosor_y']:.2f}\n"
    log += f"Grosor Z: {info['grosor_z']:.2f}\n"
    
    GROSOR_MAXIMO = 512.0  # 0x44000000 en float = 512.0
    factor_x = info['grosor_x'] / GROSOR_MAXIMO if info['grosor_x'] > 0 else 1.0
    factor_y = info['grosor_y'] / GROSOR_MAXIMO if info['grosor_y'] > 0 else 1.0
    factor_z = info['grosor_z'] / GROSOR_MAXIMO if info['grosor_z'] > 0 else 1.0
    
    log += f"Factores de grosor aplicados:\n"
    log += f"  X: {factor_x:.4f} ({info['grosor_x']:.2f}/512.0)\n"
    log += f"  Y: {factor_y:.4f} ({info['grosor_y']:.2f}/512.0)\n"
    log += f"  Z: {factor_z:.4f} ({info['grosor_z']:.2f}/512.0)\n\n"
    
    for parte in info['partes']:
        log += f"PARTE {parte['indice']:02d}:\n"
        log += f"  Capa: 0x{parte['capa']:04X}\n"
        log += f"  Opacidad: 0x{parte['opacidad']:04X}\n"
        log += f"  Flag: {parte['flag_especial']} (raw: {parte.get('flag_bytes_raw', 'N/A')})\n"
        log += f"  Subpartes: {parte['cantidad_subpartes']}\n"
        
        for subparte in parte['subpartes']:
            # Formatear IDs de huesos
            if subparte['huesos_ids']:
                huesos_str = ", ".join([f"0x{h:02X}" for h in subparte['huesos_ids']])
            else:
                huesos_str = "Ninguno"
            
            log += f"    Subparte {subparte['indice']:02d}:\n"
            log += f"      Vértices: {subparte['num_vertices']}\n"
            log += f"      Huesos influyentes: {subparte['num_huesos']}\n"
            log += f"      IDs de huesos: [{huesos_str}]\n"
        
        log += "\n"
    
    log += "=" * 70 + "\n"
    
    return log

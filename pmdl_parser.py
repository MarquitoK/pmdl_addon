import os

from .binary_utils import (
    FLAGS_ESPECIALES,
    leer_uint32, leer_uint16, leer_uint8, leer_int16, leer_float32
)


def leer_vertices(datos_parte, offset_subparte, num_vertices, num_huesos):

    vertices    = []
    tamano_pesos   = num_huesos * 2
    tamano_vertice = tamano_pesos + 2 + 6
    pos         = offset_subparte

    for i in range(num_vertices):
        if pos + tamano_vertice > len(datos_parte):
            break

        pesos = []
        for j in range(num_huesos):
            if pos + (j * 2) + 2 <= len(datos_parte):
                byte1    = leer_uint8(datos_parte, pos + (j * 2))
                byte2    = leer_uint8(datos_parte, pos + (j * 2) + 1)
                peso_raw = (byte1 << 8) | byte2  # big-endian

                if peso_raw <= 0x0080:
                    peso_norm = 0.0
                elif peso_raw >= 0x8000:
                    peso_norm = 1.0
                else:
                    peso_norm = (peso_raw - 128) / 32640.0
            else:
                # Bytes fuera de rango: peso 0.0 para mantener longitud correcta
                peso_norm = 0.0

            pesos.append(peso_norm)

        pos += tamano_pesos

        uv_x   = leer_uint8(datos_parte, pos)
        uv_y   = leer_uint8(datos_parte, pos + 1)
        pos   += 2

        coord_x = leer_int16(datos_parte, pos)
        coord_y = leer_int16(datos_parte, pos + 2)
        coord_z = leer_int16(datos_parte, pos + 4)
        pos    += 6

        vertices.append({
            'indice' : i,
            'pesos'  : pesos,
            'uv_x'   : uv_x,
            'uv_y'   : uv_y,
            'coord_x': coord_x,
            'coord_y': coord_y,
            'coord_z': coord_z,
        })

    return vertices


def analizar_subpartes(datos_parte, ids_previas_global):
    """Analiza las subpartes dentro de una parte individual."""

    if len(datos_parte) < 4:
        return [], ids_previas_global

    cantidad_subpartes = leer_uint32(datos_parte, 0x00)
    subpartes          = []
    ids_previas        = list(ids_previas_global)

    for i in range(cantidad_subpartes):
        entrada_offset = 0x04 + (i * 0x10)

        if entrada_offset + 0x10 > len(datos_parte):
            break

        num_vertices = leer_uint16(datos_parte, entrada_offset + 0x00)
        num_huesos   = leer_uint16(datos_parte, entrada_offset + 0x02)

        huesos_ids = []
        for j in range(num_huesos):
            if entrada_offset + 0x04 + j < len(datos_parte):
                hueso_id = leer_uint8(datos_parte, entrada_offset + 0x04 + j)

                if hueso_id == 0xFF:
                    hueso_id = ids_previas[j] if ids_previas[j] is not None else 0xFF

                huesos_ids.append(hueso_id)
                ids_previas[j] = hueso_id

        offset_subparte = leer_uint32(datos_parte, entrada_offset + 0x0C)
        vertices        = leer_vertices(datos_parte, offset_subparte, num_vertices, num_huesos)

        subpartes.append({
            'indice'      : i,
            'num_vertices': num_vertices,
            'num_huesos'  : num_huesos,
            'huesos_ids'  : huesos_ids,
            'offset'      : offset_subparte,
            'vertices'    : vertices,
        })

    return subpartes, ids_previas


def analizar_pmdl(filepath):
    """Analiza un archivo PMDL y retorna un diccionario con la informacion."""

    with open(filepath, 'rb') as f:
        blob = f.read()

    firma = blob[0:4].decode('ascii', errors='ignore')
    if firma not in ('pMdl', 'pMdF'):
        return None, "Error: No es un archivo PMDL/PMDF valido (firma incorrecta)"

    info = {}
    info['nombre']   = os.path.basename(filepath)
    info['filepath'] = filepath
    info['tipo']     = firma

    info['grosor_x'] = leer_float32(blob, 0x40)
    info['grosor_y'] = leer_float32(blob, 0x44)
    info['grosor_z'] = leer_float32(blob, 0x48)

    info['cantidad_huesos']      = leer_uint32(blob, 0x08)
    info['offset_huesos']        = leer_uint32(blob, 0x50)
    info['cantidad_partes']      = leer_uint32(blob, 0x5C)
    info['offset_indice_partes'] = leer_uint32(blob, 0x60)

    # Guardar blob completo para que bone_builder pueda leer los huesos
    info['blob'] = blob

    ids_previas_global = [None, None, None, None]
    partes = []

    for i in range(info['cantidad_partes']):
        entrada_offset = info['offset_indice_partes'] + (i * 0x20)

        if entrada_offset + 0x20 > len(blob):
            break

        capa         = leer_uint16(blob, entrada_offset + 0x00)
        opacidad     = leer_uint16(blob, entrada_offset + 0x02)
        part_offset  = leer_uint32(blob, entrada_offset + 0x04)
        part_length  = leer_uint32(blob, entrada_offset + 0x08)
        flag_especial = leer_uint32(blob, entrada_offset + 0x0C)
        flag_bytes   = blob[entrada_offset + 0x0C : entrada_offset + 0x10]
        nombre_flag  = FLAGS_ESPECIALES.get(flag_especial, "Desconocido")

        datos_parte = blob[part_offset : part_offset + part_length]
        subpartes, ids_previas_global = analizar_subpartes(datos_parte, ids_previas_global)

        partes.append({
            'indice'           : i,
            'capa'             : capa,
            'opacidad'         : opacidad,
            'offset'           : part_offset,
            'longitud'         : part_length,
            'flag_especial'    : flag_especial,
            'flag_bytes_raw'   : flag_bytes.hex(),
            'nombre_flag'      : nombre_flag,
            'subpartes'        : subpartes,
            'cantidad_subpartes': len(subpartes),
        })

    info['partes'] = partes
    return info, None


def generar_log(info):
    """Genera un string con el log de informacion del PMDL."""

    GROSOR_MAXIMO = 512.0
    log  = "=" * 70 + "\n"
    log += f"ANALISIS DE ARCHIVO {info['tipo']} - DBZ TTT\n"
    log += "=" * 70 + "\n\n"
    log += f"Nombre: {info['nombre']}\n"
    log += f"Tipo: {info['tipo']}\n"
    log += f"Huesos: {info['cantidad_huesos']}\n"
    log += f"Partes: {info['cantidad_partes']}\n"
    log += f"Grosor X: {info['grosor_x']:.2f}  Y: {info['grosor_y']:.2f}  Z: {info['grosor_z']:.2f}\n"

    factor_x = info['grosor_x'] / GROSOR_MAXIMO if info['grosor_x'] > 0 else 1.0
    factor_y = info['grosor_y'] / GROSOR_MAXIMO if info['grosor_y'] > 0 else 1.0
    factor_z = info['grosor_z'] / GROSOR_MAXIMO if info['grosor_z'] > 0 else 1.0
    log += f"Factores: X={factor_x:.4f}  Y={factor_y:.4f}  Z={factor_z:.4f}\n\n"

    for parte in info['partes']:
        log += f"PARTE {parte['indice']:02d}:\n"
        log += f"  Capa: 0x{parte['capa']:04X}  Opacidad: 0x{parte['opacidad']:04X}  Flag: {parte['flag_especial']}\n"
        log += f"  Subpartes: {parte['cantidad_subpartes']}\n"
        for sub in parte['subpartes']:
            huesos_str = ", ".join([f"0x{h:02X}" for h in sub['huesos_ids']]) or "Ninguno"
            log += f"    Sub {sub['indice']:02d}: {sub['num_vertices']} verts, huesos=[{huesos_str}]\n"
        log += "\n"

    log += "=" * 70 + "\n"
    return log
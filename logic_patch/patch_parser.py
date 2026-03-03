import struct
import os


def leer_offset_be(blob, pos):
    if pos + 4 > len(blob):
        return 0
    return struct.unpack_from('>I', blob, pos)[0]


def validar_y_corregir_indice(blob):
    data = bytearray(blob)

    if len(data) < 0x7D0:
        return data

    if data[0x7CC:0x7D0] != b'\x00\x00\x00\x00':
        data[0x7CC] = 0x00
        data[0x7CD] = 0x00
        data[0x7CE] = 0x00
        data[0x7CF] = 0x00
        print("[patch] Indice corregido en 0x7CC-0x7CF")

    return data


def leer_parche(filepath):
    try:
        with open(filepath, 'rb') as f:
            raw = f.read()
    except Exception as e:
        return None, f"No se pudo leer el archivo: {e}"

    if len(raw) < 0x40:
        return None, "Archivo demasiado pequeno para ser un parche valido"

    blob = validar_y_corregir_indice(raw)

    # Leer offsets del PMDL
    pmdl_inicio = leer_offset_be(blob, 0x0C)
    pmdl_fin    = leer_offset_be(blob, 0x10)

    if pmdl_inicio == 0 or pmdl_fin == 0 or pmdl_fin <= pmdl_inicio:
        return None, "No se encontro un PMDL valido en el parche (offsets invalidos)"

    if pmdl_fin > len(blob):
        return None, f"PMDL fuera de rango del archivo (fin=0x{pmdl_fin:X}, archivo=0x{len(blob):X})"

    # Verificar firma del PMDL
    firma = blob[pmdl_inicio:pmdl_inicio+4]
    if firma not in (b'pMdl', b'pMdF'):
        return None, f"Firma del PMDL invalida en 0x{pmdl_inicio:X}: {firma.hex()}"

    pmdl_datos = bytes(blob[pmdl_inicio:pmdl_fin])

    # Leer offsets de la textura
    tex_inicio = leer_offset_be(blob, 0x30)
    tex_fin    = leer_offset_be(blob, 0x34)

    if tex_inicio == 0 or tex_fin == 0 or tex_fin <= tex_inicio:
        return None, "No se encontro una textura valida en el parche (offsets invalidos)"

    if tex_fin > len(blob):
        return None, f"Textura fuera de rango del archivo"

    # Layout interno de la textura
    TEX_HEADER        = 0x80
    TEX_INDICES_SIZE  = 0x10000   # 256 * 256
    TEX_PALETA_SIZE   = 0x400     # 256 colores * 4 bytes RGBA

    indices_offset = tex_inicio + TEX_HEADER
    paleta_offset  = indices_offset + TEX_INDICES_SIZE

    if paleta_offset + TEX_PALETA_SIZE > len(blob):
        return None, "Textura incompleta: no hay suficientes bytes para indices + paleta"

    nombre = os.path.splitext(os.path.basename(filepath))[0]

    info = {
        'nombre'         : nombre,
        'filepath'       : filepath,
        'blob'           : blob,
        'pmdl_datos'     : pmdl_datos,
        'pmdl_inicio'    : pmdl_inicio,
        'pmdl_fin'       : pmdl_fin,
        'pmdl_tamano'    : pmdl_fin - pmdl_inicio,
        'tex_inicio'     : tex_inicio,
        'tex_fin'        : tex_fin,
        'indices_offset' : indices_offset,
        'paleta_offset'  : paleta_offset,
    }

    print(f"[patch] PMDL: 0x{pmdl_inicio:X} -> 0x{pmdl_fin:X}  ({info['pmdl_tamano']} bytes)")
    print(f"[patch] Textura: 0x{tex_inicio:X} -> 0x{tex_fin:X}")
    print(f"[patch] Indices: 0x{indices_offset:X}  Paleta: 0x{paleta_offset:X}")

    return info, None


# Definicion de caras extra en el indice del parche (offsets big-endian)
CARAS_PMDF = [
    ("Cara_damage",   0x10, 0x14),
    ("Cara_hablar_1", 0x14, 0x18),
    ("Cara_hablar_2", 0x18, 0x1C),
    ("Cara_hablar_3", 0x1C, 0x20),
    ("Cara_1",        0x20, 0x24),
    ("Cara_2",        0x24, 0x28),
    ("Cara_3",        0x28, 0x2C),
    ("Cara_no_usada", 0x2C, 0x30),
]


def leer_caras_pmdf(blob):
    caras = []

    for nombre, off_inicio, off_fin in CARAS_PMDF:
        inicio = leer_offset_be(blob, off_inicio)
        fin    = leer_offset_be(blob, off_fin)

        # Validar rango
        if inicio == 0 or fin == 0 or fin <= inicio or fin > len(blob):
            continue

        # Verificar firma
        firma = blob[inicio:inicio + 4]
        if firma not in (b'pMdl', b'pMdF'):
            continue

        datos = bytes(blob[inicio:fin])
        caras.append({
            'nombre' : nombre,
            'datos'  : datos,
            'inicio' : inicio,
            'fin'    : fin,
            'tamano' : fin - inicio,
        })
        print(f"[patch] {nombre}: 0x{inicio:X} -> 0x{fin:X}  ({fin - inicio} bytes)  firma={firma.decode('ascii', errors='ignore')}")

    return caras
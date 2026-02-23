import struct


# Diccionario de flags especiales
FLAGS_ESPECIALES = {
    0x00: "Ninguna",
    0x01: "Equipamiento 1",
    0x02: "Equipamiento 2",
    0x06: "Cara",
    0x07: "Ocultable"
}


def leer_uint32(blob, offset):
    """Lee un uint32 en little-endian desde el offset especificado"""
    return struct.unpack_from("<I", blob, offset)[0]


def leer_uint16(blob, offset):
    """Lee un uint16 en little-endian desde el offset especificado"""
    return struct.unpack_from("<H", blob, offset)[0]


def leer_uint8(blob, offset):
    """Lee un uint8 desde el offset especificado"""
    return blob[offset]


def leer_int16(blob, offset):
    """Lee un int16 en little-endian desde el offset especificado"""
    return struct.unpack_from("<h", blob, offset)[0]


def leer_float32(blob, offset):
    """Lee un float32 en little-endian desde el offset especificado"""
    return struct.unpack_from("<f", blob, offset)[0]


def escribir_uint32(valor):
    """Escribe un uint32 en little-endian"""
    return struct.pack("<I", valor)


def escribir_uint16(valor):
    """Escribe un uint16 en little-endian"""
    return struct.pack("<H", valor)


def escribir_uint8(valor):
    """Escribe un uint8"""
    return struct.pack("B", valor)


def escribir_int16(valor):
    """Escribe un int16 en little-endian"""
    return struct.pack("<h", valor)


def escribir_float32(valor):
    """Escribe un float32 en little-endian"""
    return struct.pack("<f", valor)

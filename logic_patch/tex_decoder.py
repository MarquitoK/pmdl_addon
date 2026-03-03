def decodificar_textura(blob, indices_offset, paleta_offset):
    try:
        from PIL import Image
    except ImportError:
        print("[tex] ERROR: Pillow no esta instalado. Ejecuta: pip install Pillow")
        return None

    # Leer paleta RGBA (256 colores)
    paleta = []
    for i in range(256):
        off = paleta_offset + (i * 4)
        if off + 3 < len(blob):
            r = blob[off]
            g = blob[off + 1]
            b = blob[off + 2]
            a = blob[off + 3]
            paleta.append((r, g, b, a))
        else:
            paleta.append((0, 0, 0, 255))

    # Crear imagen RGBA 256x256
    img    = Image.new('RGBA', (256, 256))
    pixels = img.load()

    # Algoritmo de desentrelazado por bloques 16x8
    # Replica exacta del ShowTex() del C# original
    num  = 0   # offset X del bloque actual
    num2 = 0   # offset Y del bloque actual
    num3 = 0   # indice lineal en el buffer de indices (0..65535)
    num4 = 32  # contador de filas de bloques (256/8 = 32)

    while num4 != 0:
        num5 = 16  # contador de columnas de bloques (256/16 = 16)

        while num5 != 0:
            num6 = 0  # fila dentro del bloque (0..7)

            while num6 < 8:
                num7 = 0  # columna dentro del bloque (0..15)

                while num7 < 16:
                    if num3 < 65536:
                        idx = indices_offset + num3
                        if idx < len(blob):
                            color_idx = blob[idx]
                            color     = paleta[color_idx] if color_idx < len(paleta) else (0, 0, 0, 255)
                            x = int(num7 + num)
                            y = int(num6 + num2)
                            if x < 256 and y < 256:
                                pixels[x, y] = color
                        num3 += 1
                    num7 += 1

                num6 += 1

            # Avanzar al siguiente bloque horizontal
            if num + 2 < 256:
                num += 16

            num5 -= 1

        # Avanzar al siguiente bloque vertical
        if num2 + 2 < 256:
            num2 += 8

        num = 0   # reiniciar X al inicio de cada fila de bloques
        num4 -= 1

    print(f"[tex] Imagen decodificada: 256x256 RGBA ({num3} pixeles procesados)")

    # La textura del juego esta invertida verticalmente, corregir antes de retornar
    img = img.transpose(Image.FLIP_TOP_BOTTOM)

    return img


def textura_a_blender(blob, indices_offset, paleta_offset, nombre):
    img_pil = decodificar_textura(blob, indices_offset, paleta_offset)
    if img_pil is None:
        return None

    try:
        import bpy
        import numpy as np

        # Convertir PIL RGBA a array numpy normalizado (0.0-1.0)
        arr = np.array(img_pil, dtype=float) / 255.0

        # Crear imagen en Blender
        nombre_img = nombre + "_tex"
        if nombre_img in bpy.data.images:
            bpy.data.images.remove(bpy.data.images[nombre_img])

        bl_img        = bpy.data.images.new(nombre_img, width=256, height=256, alpha=True)
        bl_img.pixels  = arr.flatten().tolist()
        bl_img.pack()   # embeber en el .blend para que no se pierda
        bl_img.update()

        print(f"[tex] Imagen registrada en Blender como '{nombre_img}'")
        return bl_img

    except Exception as e:
        print(f"[tex] Error al registrar imagen en Blender: {e}")
        return None
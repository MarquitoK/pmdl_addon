# PMDL Importer/Exporter for Blender
### DBZ Tenkaichi Tag Team (PSP) — by Los ijue30s

Addon de Blender para importar y exportar archivos `.pmdl` y `.pmdf` de **Dragon Ball Z: Tenkaichi Tag Team (PSP)**, permitiendo editar modelos del juego directamente en Blender y exportarlos de vuelta para uso in-game.

Compatible con **Blender 3.5 y 4.x+**.

---

## Caracteristicas

- **Importacion** de archivos `.pmdl` / `.pmdf` / `.unk`
- Reconstruye la malla completa con geometria correcta
- Importa **mapas UV** listos para edicion de texturas
- Importa **pesos de vertices** (skin weights por influencia de hueso)
- Carga automaticamente la textura `.png` si se encuentra en la misma carpeta
- Preserva metadatos del juego por parte como propiedades editables:
  - `PMDL_Capa` — valor de capa de delineado
  - `PMDL_Opacidad` — opacidad de la parte (0–100%)
  - `PMDL_Flag` — flag especial (equipamiento, cara, ocultable, etc.)
- **Exportacion** de vuelta a `.pmdl` / `.pmdf`, parcheando el archivo original con:
  - Posiciones de vertices actualizadas
  - UVs actualizados
  - Metadatos actualizados (capa, opacidad, flag)
  - Modo de **grosor maximo** opcional (`grosor_maximo`)
- Deteccion automatica de la coleccion correcta a exportar segun la seleccion
- Establece el viewport en Solid + Flat + Texture al importar para visualizacion optima
- Material compartido (`tex_ttt`) creado automaticamente y reutilizado entre partes

---

## Estructura de archivos

```
pmdl_addon/
├── __init__.py        # Punto de entrada del addon, registro
├── binary_utils.py    # Funciones de lectura/escritura binaria
├── pmdl_parser.py     # Parser del formato PMDL/PMDF
├── builder.py         # Construccion de objetos en Blender
├── importer.py        # Operador de importacion
└── exporter.py        # Operador de exportacion
```

Se puede colocar un archivo opcional `bones_list.txt` en la carpeta del addon para habilitar nombres legibles de huesos al importar.

---

## Instalacion

1. Descarga o clona este repositorio
2. Renombra la carpeta a `pmdl_addon` si es necesario (no debe empezar con `__`)
3. En Blender: `Edit > Preferences > Add-ons > Install`
4. Selecciona la **carpeta** (o comprimela en zip primero y selecciona el zip)
5. Activa el addon: busca **"PMDL Reader for DBZ TTT"**

---

## Uso

### Importar
`File > Import > PMDL/PMDF (.pmdl, .pmdf, .unk)`

| Opcion | Descripcion |
|---|---|
| Escala | Factor de escala de vertices (default `0.002075`) |
| Renombrar Huesos | Usar nombres de `bones_list.txt` en lugar de IDs `sk_XX` |
| Importar Solo Huesos | Importa solo el armature, sin geometria (modo debug) |
| Mostrar Log Detallado | Imprime el analisis completo del archivo en la consola |

### Exportar
`File > Export > PMDL/PMDF (.pmdl, .pmdf)`

El exportador parchea el **archivo original** para preservar todos los datos que aun no son editables (animaciones, shaders, etc.). El archivo `.pmdl` original debe seguir accesible en su ruta original.

| Opcion | Descripcion |
|---|---|
| Grosor Maximo | Fuerza el grosor a 512.0 y reescala los vertices automaticamente |

> La coleccion correcta a exportar se detecta automaticamente desde la seleccion activa. Si no hay nada seleccionado, se usa la primera coleccion PMDL encontrada en la escena.

---

## Referencia de Flags especiales

| Valor | Significado |
|---|---|
| `0x00` | Ninguna |
| `0x01` | Equipamiento slot 1 |
| `0x02` | Equipamiento slot 2 |
| `0x06` | Parte de cara |
| `0x07` | Parte ocultable |

---

## Limitaciones conocidas

- El exportador actualmente parchea solo geometria y UVs — los pesos de vertices se preservan del archivo original pero aun no pueden editarse y re-exportarse
- El exportador requiere que el archivo `.pmdl` original este presente; no construye el formato desde cero
- La precision de UV esta limitada a 8 bits (rango entero 0–255) segun el formato original

---

## Roadmap

- [ ] Importacion completa de armature con orientacion de huesos y jerarquia correctas
- [ ] Vinculacion malla-armature al importar
- [ ] Soporte de exportacion de pesos
- [ ] Panel UI para acceso rapido y visualizacion de metadatos
- [ ] Escritura completa de PMDL (exportar sin necesitar el archivo original)

---

## Creditos

**by Los ijue30s**

Investigacion, ingenieria inversa y desarrollo del formato PMDL para DBZ Tenkaichi Tag Team.
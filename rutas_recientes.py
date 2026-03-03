import os

# Claves para WindowManager
_CLAVE_IMPORT_PMDL  = "ttt_ruta_import_pmdl"
_CLAVE_EXPORT_PMDL  = "ttt_ruta_export_pmdl"
_CLAVE_IMPORT_PATCH = "ttt_ruta_import_patch"
_CLAVE_EXPORT_PATCH = "ttt_ruta_export_patch"


def get_ruta(clave):
    try:
        import bpy
        return bpy.context.window_manager.get(clave, "")
    except Exception:
        return ""


def set_ruta(clave, filepath):
    try:
        import bpy
        directorio = os.path.dirname(filepath)
        if directorio:
            bpy.context.window_manager[clave] = directorio
    except Exception:
        pass


def aplicar_ruta_inicial(operador, clave, nombre_archivo_defecto):
    ruta = get_ruta(clave)
    if ruta and os.path.isdir(ruta):
        operador.filepath = os.path.join(ruta, nombre_archivo_defecto)
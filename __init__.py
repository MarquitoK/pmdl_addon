bl_info = {
    "name": "PMDL Reader for DBZ TTT",
    "author": "Tu Nombre",
    "version": (1, 4, 0),
    "blender": (3, 5, 0),
    "location": "File > Import/Export > PMDL Reader",
    "description": "Importa y exporta archivos PMDL de DBZ Tenkaichi Tag Team (Compatible con Blender 3.5 - 4.x)",
    "category": "Import-Export",
}

import bpy

from .importer import ImportPMDL, menu_func_import
from .exporter import ExportPMDL, menu_func_export


def register():
    bpy.utils.register_class(ImportPMDL)
    bpy.utils.register_class(ExportPMDL)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.utils.unregister_class(ImportPMDL)
    bpy.utils.unregister_class(ExportPMDL)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)


if __name__ == "__main__":
    register()

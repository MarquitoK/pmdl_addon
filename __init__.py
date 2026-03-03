bl_info = {
    "name": "PMDL Reader for DBZ TTT",
    "author": "Los ijue30s",
    "version": (1, 6, 0),
    "blender": (3, 5, 0),
    "location": "File > Import/Export > PMDL Reader",
    "description": "Importa y exporta archivos PMDL y parches de DBZ Tenkaichi Tag Team",
    "category": "Import-Export",
}

import bpy

from .dependencies import instalar_dependencias
from .importer     import ImportPMDL, menu_func_import
from .exporter     import ExportPMDL, menu_func_export
from .logic_patch  import ImportPatch, ExportPatch, menu_func_import_patch, menu_func_export_patch


def register():
    instalar_dependencias()

    bpy.utils.register_class(ImportPMDL)
    bpy.utils.register_class(ExportPMDL)
    bpy.utils.register_class(ImportPatch)
    bpy.utils.register_class(ExportPatch)

    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import_patch)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export_patch)


def unregister():
    bpy.utils.unregister_class(ImportPMDL)
    bpy.utils.unregister_class(ExportPMDL)
    bpy.utils.unregister_class(ImportPatch)
    bpy.utils.unregister_class(ExportPatch)

    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import_patch)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export_patch)


if __name__ == "__main__":
    register()
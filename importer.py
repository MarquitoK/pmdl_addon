import bpy
from bpy.props import StringProperty, BoolProperty
from bpy_extras.io_utils import ImportHelper

from .pmdl_parser import analizar_pmdl
from .builder import crear_mesh_blender
from .rutas_recientes import (
    aplicar_ruta_inicial, set_ruta,
    _CLAVE_IMPORT_PMDL
)


class ImportPMDL(bpy.types.Operator, ImportHelper):
    """Importar archivo PMDL/PMDF de DBZ TTT"""
    bl_idname = "import_scene.pmdl"
    bl_label = "Importar PMDL/PMDF"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".pmdl"
    filter_glob: StringProperty(
        default="*.pmdl;*.pmdf;*.unk",
        options={'HIDDEN'},
    )

    renombrar_huesos: BoolProperty(
        name="Renombrar Huesos",
        description="Usar nombres descriptivos de huesos desde bones_list.txt",
        default=True,
    )

    def invoke(self, context, event):
        aplicar_ruta_inicial(self, _CLAVE_IMPORT_PMDL, "")
        return super().invoke(context, event)

    def execute(self, context):
        info, error = analizar_pmdl(self.filepath)

        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        set_ruta(_CLAVE_IMPORT_PMDL, self.filepath)

        objetos = crear_mesh_blender(info, 0.015625, self.renombrar_huesos, context)

        bpy.ops.object.select_all(action='DESELECT')
        for obj in objetos:
            obj.select_set(True)

        if objetos:
            context.view_layer.objects.active = objetos[0]

        tipo_archivo = "PMDF" if info['tipo'] == 'pMdF' else "PMDL"
        partes = len([o for o in objetos if o.type == 'MESH'])
        self.report({'INFO'}, f"{tipo_archivo} importado: {partes} partes, armature listo")

        return {'FINISHED'}


def menu_func_import(self, context):
    self.layout.operator(ImportPMDL.bl_idname, text="PMDL/PMDF (.pmdl, .pmdf, .unk)")
import bpy
from bpy.props import StringProperty, BoolProperty, FloatProperty
from bpy_extras.io_utils import ImportHelper

from .pmdl_parser import analizar_pmdl, generar_log
from .builder import crear_mesh_blender


class ImportPMDL(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.pmdl"
    bl_label = "Importar PMDL/PMDF"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".pmdl"
    filter_glob: StringProperty(
        default="*.pmdl;*.pmdf;*.unk",
        options={'HIDDEN'},
    )

    mostrar_log: BoolProperty(
        name="Mostrar log detallado",
        description="Imprimir analisis detallado en consola",
        default=False,
    )

    escala: FloatProperty(
        name="Escala",
        description="Factor de escala para el modelo",
        default=0.002075,
        min=0.0001,
        max=1.0,
    )

    renombrar_huesos: BoolProperty(
        name="Renombrar Huesos",
        description="Usar nombres descriptivos de huesos desde bones_list.txt",
        default=False,
    )

    importar_huesos: BoolProperty(
        name="Importar Huesos",
        description="Importar solo el armature (huesos) sin geometria. Util para depuracion",
        default=False,
    )

    def execute(self, context):
        info, error = analizar_pmdl(self.filepath)

        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        objetos = crear_mesh_blender(info, self.escala, self.renombrar_huesos, self.importar_huesos, context)

        bpy.ops.object.select_all(action='DESELECT')
        for obj in objetos:
            obj.select_set(True)

        if objetos:
            context.view_layer.objects.active = objetos[0]

        if self.mostrar_log:
            log = generar_log(info)
            print("\n" + log)

        tipo_archivo = "PMDF" if info['tipo'] == 'pMdF' else "PMDL"
        self.report({'INFO'}, f"{tipo_archivo} importado: {len(objetos)} partes creadas")

        return {'FINISHED'}


def menu_func_import(self, context):
    self.layout.operator(ImportPMDL.bl_idname, text="PMDL/PMDF (.pmdl, .pmdf, .unk)")

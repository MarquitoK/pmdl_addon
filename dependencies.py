import subprocess
import sys
import importlib


def verificar_e_instalar(nombre_paquete, nombre_importacion=None):
    #Verifica si el paquete "pillow" está instalado o no, de no estarlo, lo instala al momento de instalar el addon
    if nombre_importacion is None:
        nombre_importacion = nombre_paquete

    # Intentar importar primero
    try:
        importlib.import_module(nombre_importacion)
        print(f"[deps] {nombre_paquete}: ya instalado")
        return True
    except ImportError:
        pass

    # No esta instalado, intentar instalarlo
    print(f"[deps] {nombre_paquete} no encontrado, instalando...")

    python_exe = sys.executable

    try:
        resultado = subprocess.run(
            [python_exe, "-m", "pip", "install", nombre_paquete],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if resultado.returncode == 0:
            # Verificar que ahora si se puede importar
            try:
                importlib.import_module(nombre_importacion)
                print(f"[deps] {nombre_paquete}: instalado correctamente")
                return True
            except ImportError:
                print(f"[deps] {nombre_paquete}: instalado pero no se puede importar aun, reinicia Blender")
                return False
        else:
            print(f"[deps] Error al instalar {nombre_paquete}:")
            print(resultado.stderr)
            return False

    except subprocess.TimeoutExpired:
        print(f"[deps] Timeout al instalar {nombre_paquete}")
        return False
    except Exception as e:
        print(f"[deps] Error inesperado al instalar {nombre_paquete}: {e}")
        return False


def instalar_dependencias():
    #Instala todas las dependencias requeridas por el addon.
    print("\n[deps] Verificando dependencias del addon...")
    ok = verificar_e_instalar("Pillow", "PIL")
    if ok:
        print("[deps] Todas las dependencias estan listas\n")
    else:
        print("[deps] ATENCION: Algunas dependencias fallaron. Reinicia Blender e intenta de nuevo.\n")
    return ok

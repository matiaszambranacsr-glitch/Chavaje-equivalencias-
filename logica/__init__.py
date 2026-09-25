"""La lógica de la app: todo lo que no es una pantalla. Se carga UNA vez por proceso.

Por qué partes que comparten un solo espacio de nombres, y no módulos que se importan entre sí:
la lógica son 566 funciones que se llaman unas a otras por su nombre, sin prefijo, porque
nacieron en un solo archivo. Convertirlas en módulos de verdad obliga a escribir cientos de
imports cruzados, y con importaciones circulares el orden de carga decide qué nombre existe y
cuál no: un error que aparece recién al tocar el botón que usa esa función. Así, cada archivo
se ejecuta en orden en este mismo espacio de nombres, y todo se sigue viendo como antes. Se
controló al partir: cada línea del archivo original quedó exactamente en un lugar, y ninguna
función de acá usa un nombre que se defina en las pantallas.

Por qué se carga una vez: antes Streamlit volvía a ejecutar las 30.800 líneas en cada toque de
cada persona —definir de nuevo 566 funciones y rearmar cada @st.cache_data, que le calcula la
huella leyendo su código fuente—. Ahora eso pasa al arrancar, y cada toque ejecuta solo app.py
y la pantalla.

Lo que tiene que sobrevivir a una recarga (candados, sesiones con proveedores) sigue en
del_proceso(), que vive aparte.
"""
import os

from orden import PARTES_DE_LA_LOGICA as _PARTES

_CARPETA = os.path.dirname(os.path.abspath(__file__))


# La fecha de cada archivo al cargarlo. Ver cambio_algun_archivo().
_VERSIONES = {}


def _cargar_las_partes():
    import orden
    _VERSIONES[orden.__file__] = os.path.getmtime(orden.__file__)
    _VERSIONES[__file__] = os.path.getmtime(__file__)
    for parte in _PARTES:
        ruta = os.path.join(_CARPETA, parte)
        _VERSIONES[ruta] = os.path.getmtime(ruta)
        with open(ruta, encoding="utf-8") as archivo:
            codigo = compile(archivo.read(), ruta, "exec")
        exec(codigo, globals())


_cargar_las_partes()


def cambio_algun_archivo():
    """Si algún archivo de la lógica cambió desde que se cargó. app.py lo pregunta en cada toque
    y, si cambió, la vuelve a cargar.

    No se le deja al vigilante de archivos de Streamlit. Probado: cada sesión abierta tiene su
    propio vigilante, y solo las que estaban conectadas cuando cambió el archivo tiran la
    versión vieja en su toque siguiente. Una sesión nueva —o cualquiera, si al subir un cambio
    no había nadie adentro— seguía con la lógica vieja hasta reiniciar el servidor. Mirar las
    fechas son 19 consultas al disco por toque: microsegundos."""
    try:
        return any(os.path.getmtime(ruta) != fecha for ruta, fecha in _VERSIONES.items())
    except OSError:
        return True

# Lo de este archivo, que no es de la lógica. os, sys y types no van acá: la primera parte
# también los importa, y las pantallas los usan.
_PROPIOS = {"_PARTES", "_CARPETA", "_cargar_las_partes", "_PROPIOS", "todo_lo_de_la_logica",
            "_VERSIONES", "cambio_algun_archivo"}


def todo_lo_de_la_logica():
    """Los nombres de la lógica, para que app.py y las pantallas los usen sin prefijo, como
    cuando todo era un archivo. Van también los que empiezan con «_», que «import *» deja
    afuera y las pantallas usan (_ULTIMOS_ERRORES, _actividad_del_mostrador...)."""
    return {nombre: valor for nombre, valor in globals().items()
            if not (nombre.startswith("__") and nombre.endswith("__"))
            and nombre not in _PROPIOS}

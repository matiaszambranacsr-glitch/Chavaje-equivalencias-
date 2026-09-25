"""Las pantallas: una por archivo. Corren en cada toque, desde app.py.

Cada archivo es el pedazo de app.py que era, tal cual: empieza con su «if pagina ==
PAGINAS[n]:» y usa sin importarlos los nombres de app.py y de logica/. Por eso se ejecuta en
el mismo espacio de nombres que app.py (el que Streamlit arma en cada toque), y no se importa
como un módulo: así se comporta exactamente como cuando estaba escrito ahí.

Se compila una vez y se vuelve a compilar solo si el archivo cambió. Compilar las 8.600 líneas
de pantallas en cada toque de cada persona sería justo el gasto que la partición vino a sacar.
"""
import os

from orden import PANTALLAS

_CARPETA = os.path.dirname(os.path.abspath(__file__))
_COMPILADAS = {}


def codigo_de_la_pantalla(nombre):
    """El código compilado de pantallas/<nombre>, rehecho solo si el archivo cambió."""
    ruta = os.path.join(_CARPETA, nombre)
    version = os.path.getmtime(ruta)
    guardada = _COMPILADAS.get(ruta)
    if guardada is None or guardada[0] != version:
        with open(ruta, encoding="utf-8") as archivo:
            guardada = (version, compile(archivo.read(), ruta, "exec"))
        _COMPILADAS[ruta] = guardada
    return guardada[1]

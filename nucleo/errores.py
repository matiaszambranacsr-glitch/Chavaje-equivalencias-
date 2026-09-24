"""Registro de los errores que la app decide ignorar.

Está aparte y sin dependencias porque lo usan todos los demás módulos: si esto importara algo,
ese algo no podría anotar sus propios errores."""
import sys
import types
from datetime import datetime


# Los últimos errores que la app se tragó. Hay 142 lugares donde algo puede fallar y la app
# sigue igual: son fallbacks a propósito —una tabla que todavía no existe, una función opcional
# que no está—, pero si ahí se esconde un bug real, nadie se entera nunca.
#
# Con esto quedan anotados. No cambia el comportamiento: el fallback sigue corriendo igual.
def del_proceso(nombre, crear):
    """Un objeto que dura lo que dura el PROCESO del servidor, no una pasada del script.

    Streamlit vuelve a ejecutar app.py entero en cada toque, y cada vez en un módulo nuevo:
    todo lo que se crea a este nivel con «= threading.Lock()» o «= []» es OTRO objeto en cada
    pasada. Para una constante da igual; para un candado que tiene que ser uno solo, no. Medido
    con una base con trabajo de fondo pendiente: cada toque largaba otra tanda de fondo, y
    después de seis toques había **diez corriendo a la vez**, cuando la regla era una. Cada una
    puede durar diez minutos contra la base: así es como se cae un servidor chico.

    Esto los guarda en un módulo propio adentro de sys.modules, que Streamlit no toca entre
    pasadas. Tampoco se borra con el «Clear cache» del menú, ni cuando se sube código nuevo sin
    reiniciar: la tanda que largó el código viejo sigue teniendo el candado, y el nuevo la
    respeta. dict.setdefault es atómico, así que dos sesiones que llegan juntas se quedan con
    el mismo objeto."""
    registro = sys.modules.setdefault("_equivalencias_el_chavo_del_proceso",
                                      types.ModuleType("_equivalencias_el_chavo_del_proceso"))
    guardados = registro.__dict__
    if nombre not in guardados:
        guardados.setdefault(nombre, crear())
    return guardados[nombre]


MAXIMO_ERRORES_ANOTADOS = 150


# Del proceso y no de la pasada (ver del_proceso): si no, la pantalla que los muestra veía solo
# los errores de su propia pasada, y los de los hilos de fondo no los veía nunca nadie.
_ULTIMOS_ERRORES = del_proceso("ultimos_errores", list)


def anotar_error(donde, error):
    """Deja registrado un error que la app decidió ignorar. NUNCA puede fallar.

    Va a memoria y no a la base a propósito: si lo que falló ES la base, escribir ahí sería
    fallar de nuevo dentro del manejo del primer error."""
    try:
        _ULTIMOS_ERRORES.append({
            "cuando": datetime.now().strftime("%d/%m %H:%M:%S"),
            "donde": str(donde)[:60],
            "tipo": type(error).__name__,
            "detalle": str(error)[:200],
        })
        if len(_ULTIMOS_ERRORES) > MAXIMO_ERRORES_ANOTADOS:
            del _ULTIMOS_ERRORES[:-MAXIMO_ERRORES_ANOTADOS]
    except Exception:
        # Acá NO se puede llamar a anotar_error: era lo que hacía antes y, como el except
        # existe justamente para cuando el cuerpo de arriba falla, el segundo intento fallaba
        # igual que el primero y se llamaba a sí mismo para siempre. El RecursionError que
        # salía de ahí no lo agarraba nadie (los llamadores esperan ValueError, sqlite3.Error,
        # etc.) y tumbaba la pantalla entera. Es decir: la única función de la app que promete
        # no fallar nunca era la que rompía más fuerte, y encima justo cuando se la necesitaba.
        # Un error que no se pudo anotar se pierde, y está bien: perderlo es infinitamente
        # mejor que voltear la pantalla del usuario por no poder escribirlo en una lista.
        pass


def errores_anotados():
    """Los últimos errores ignorados, del más viejo al más nuevo. Para mostrarlos en una
    pantalla de diagnóstico sin tocar la lista de adentro."""
    return list(_ULTIMOS_ERRORES)

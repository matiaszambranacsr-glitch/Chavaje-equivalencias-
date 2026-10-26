"""Lo básico: errores anotados, vista celular/computadora, estilo, usuarios y claves.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""


import streamlit as st
import sqlite3
import re
import io
import html          # para escapar el texto de la base antes de meterlo en HTML
import gzip          # la copia del repositorio va comprimida: ver ARCHIVO_SEMILLA_COMPRIMIDA
import shutil
import uuid
import threading
import unicodedata
import json
import hmac
import hashlib
import os
import pickle
import contextlib
import functools
import time
import requests          # se usa en varias funciones; importarlo una vez evita repetirlo
import sys
import collections
import itertools
import types
from datetime import datetime, timedelta, date, time as dtime
from urllib.parse import quote
from openpyxl import load_workbook, Workbook


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


# LO GUARDADO EN EL PROCESO QUE SALE DE LA BASE. Restaurar una copia —o cambiar una base dañada
# por otra— deja OTRA base en el mismo archivo, y estas memorias seguían contestando con la de
# antes: la cobertura del catálogo hasta 10 minutos, la escala de precios 5, y las marcas con
# CHAS hasta que se reiniciara el servidor. Ver olvidar_lo_guardado_de_la_base(). Cada
# del_proceso() de la app está en una de las dos listas: pruebas_de_la_recuperacion.py falla si
# aparece uno nuevo sin decidir de cuál es.
MEMORIAS_DE_LA_BASE = ("autos_contra_el_catalogo", "cobertura_del_catalogo", "cuenta_de_palabras",
                       "escala_de_precios", "marca_del_modelo", "marcas_con_chas", "red_de_equivalencias",
                       "salud_compartida")
MEMORIAS_QUE_NO_SON_DE_LA_BASE = (
    # Candados, sesiones con los sitios de afuera, lo bajado de internet y lo que se midió.
    "candado_de_la_copia_a_github", "candado_de_la_salud_compartida",
    "candado_de_la_tanda_de_fondo", "candado_de_las_tareas_del_dia",
    "candado_de_paginas_recientes", "candado_de_sesiones_de_catalogo", "intentos_en_recuperacion",
    "libros_de_excel_leidos", "lo_traido_de_la_nhtsa", "mediciones_de_busqueda",
    "paginas_recientes", "paquetes_de_certificados", "sesiones_de_catalogo",
    "sesiones_de_portal", "token_de_mercado_libre", "ultimos_errores")


def olvidar_lo_guardado_de_la_base():
    """Vacía las memorias de MEMORIAS_DE_LA_BASE que ya existen, sin crear las que no: cada
    una se crea con su forma la primera vez que se usa (ver del_proceso())."""
    guardados = sys.modules.setdefault("_equivalencias_el_chavo_del_proceso",
                                       types.ModuleType("_equivalencias_el_chavo_del_proceso")
                                       ).__dict__
    for nombre in MEMORIAS_DE_LA_BASE:
        memoria = guardados.get(nombre)
        if nombre == "escala_de_precios" and isinstance(memoria, dict):
            memoria.update(cuando=0.0, datos=None)       # ver _escala_guardada()
        elif hasattr(memoria, "clear"):
            memoria.clear()


# Del proceso y no de la pasada (ver del_proceso): si no, la pantalla que los muestra veía solo
# los errores de su propia pasada, y los de los hilos de fondo no los veía nunca nadie.
_ULTIMOS_ERRORES = del_proceso("ultimos_errores", list)
MAXIMO_ERRORES_ANOTADOS = 150


def miles(numero, decimales=None):
    """Un número como se escribe acá: «1.380», «87.155», «1.234,5».

    Los f-string con «:,» separan los miles con coma, a la inglesa, y había 211 en la app:
    arriba de todo decía «1,380 par(es) de motores», y el presupuesto, «$1,505», que acá se lee
    uno coma cinco. decimales=None deja los que traiga el número (como «:,»); 0 o 1 los fija
    (como «:,.0f» y «:,.1f»).

    Lo que no es un número vuelve tal cual: también se usa para st.metric, que recibe lo que
    sea —un None, un «—»— y lo muestra crudo."""
    if isinstance(numero, bool) or not isinstance(numero, (int, float)):
        return numero
    try:
        texto = format(numero, ",") if decimales is None else format(float(numero), f",.{decimales}f")
    except (TypeError, ValueError):
        return str(numero)
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


# LO SENSIBLE NO SE ANOTA. El detalle de un error es el texto de la excepción, y una excepción de
# red trae la dirección entera: si alguna vez una clave fuera en la dirección (?key=…, un token,
# la contraseña de un portal), quedaría a la vista en «Los errores» (lo señaló una revisión con
# ChatGPT). Hoy ninguna va así —Gemini y GitHub la mandan en la cabecera—; esto es para que, si
# alguna vez va, no se copie.
_PATRONES_SENSIBLES = [
    (re.compile(r"(?i)\b(api[_-]?key|key|token|access_token|password|passwd|pass|clave|secret|"
                r"contrase[ñn]a|usuario|user)=([^&\s'\"]+)"), r"\1=***"),
    (re.compile(r"(?i)\bbearer\s+[\w.\-]+"), "Bearer ***"),
    (re.compile(r"\b(ghp_|gho_|ghs_|github_pat_)[\w]+"), r"\1***"),
    (re.compile(r"\bAIza[\w\-]{20,}"), "AIza***"),
    (re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@"), r"\1***:***@"),
]


def tapar_lo_sensible(texto):
    texto = str(texto)
    for patron, reemplazo in _PATRONES_SENSIBLES:
        texto = patron.sub(reemplazo, texto)
    return texto


# DE QUÉ ES CADA ERROR. Una lista de 150 errores sueltos no dice si el problema es la base o un
# proveedor caído; agrupados sí: «140 de internet y proveedores, 0 de la base» (lo propuso una
# revisión con ChatGPT). Se decide por el tipo de error y por dónde pasó, en este orden.
CATEGORIAS_DE_ERRORES = (
    ("🗄️ Base de datos", lambda d, t: t in ("OperationalError", "DatabaseError", "IntegrityError",
                                            "ProgrammingError", "InterfaceError")),
    ("🌐 Internet y proveedores", lambda d, t: t in (
        "ConnectionError", "Timeout", "ReadTimeout", "ConnectTimeout", "SSLError", "HTTPError",
        "ChunkedEncodingError", "TooManyRedirects", "ProxyError", "RequestException")
        or any(x in d for x in ("proveedor", "portal", "catalogo", "mercado_libre", "fotos",
                                "equiv", "bcra", "tasas", "dnrpa", "parque", "chas", "nhtsa",
                                "ipc", "contexto_de_precios", "certificado"))),
    ("☁️ Copias", lambda d, t: any(x in d for x in ("copia", "github", "backup", "restaurar",
                                                     "semilla"))),
    ("📥 Importación", lambda d, t: any(x in d for x in ("import", "excel", "lista", "mapeo"))),
    ("🔑 Ingreso y permisos", lambda d, t: t == "PermissionError"
        or any(x in d for x in ("password", "login", "exigir", "sesion", "ingreso"))),
    ("🔍 Buscador", lambda d, t: "busc" in d),
    ("🧹 Mantenimiento y tareas", lambda d, t: any(x in d for x in (
        "_trabajo_de_fondo", "mantenimiento", "tareas", "salud", "diagnostico", "descubrimiento"))),
)


def _renglon_del_error(error):
    try:
        import traceback
        ultimo = traceback.extract_tb(error.__traceback__)[-1]
        return f"{os.path.basename(ultimo.filename)}:{ultimo.lineno}"
    except Exception:          # sin traceback (un texto, un error armado a mano): no hay renglón
        return ""


# UN CÓDIGO PARA DICTAR. Una pantalla que fallaba mostraba el error técnico de Streamlit, en rojo
# y con rutas del servidor, y el error no quedaba en «Los errores». Ahora dice «no se pudo
# mostrar, código BUS-8F31»: quien está en el mostrador se lo pasa al administrador, que lo
# encuentra en Estado y papelera → «🐞 Errores» con dónde y en qué renglón (lo propuso una
# revisión con ChatGPT). El administrador ve además el error completo ahí mismo.
PREFIJOS_DE_LAS_PANTALLAS = ("BUS", "VIN", "EXC", "ADM", "EST", "WSP", "VEH", "MEC", "DEP", "VEN",
                             "DVL", "CAJ")


def codigo_de_error(prefijo):
    return f"{prefijo}-{uuid.uuid4().hex[:4].upper()}"


def mostrar_error_inesperado(donde, error, prefijo="APP"):
    codigo = codigo_de_error(prefijo)
    anotar_error(donde, error, codigo=codigo)
    st.error(f"😕 No se pudo terminar de mostrar esta pantalla. Código: **{codigo}**. Pasáselo "
             "al administrador: con eso encuentra qué pasó. El resto de la app sigue andando.")
    if es_admin():
        st.exception(error)
    return codigo


def categoria_del_error(error_anotado):
    d, t = str(error_anotado.get("donde", "")).lower(), str(error_anotado.get("tipo", ""))
    return next((nombre for nombre, es in CATEGORIAS_DE_ERRORES if es(d, t)), "🖥️ Pantallas y otros")


def anotar_error(donde, error, codigo=""):
    """Deja registrado un error que la app decidió ignorar. NUNCA puede fallar.

    Va a memoria y no a la base a propósito: si lo que falló ES la base, escribir ahí sería
    fallar de nuevo dentro del manejo del primer error."""
    try:
        _ULTIMOS_ERRORES.append({
            "cuando": datetime.now().strftime("%d/%m %H:%M:%S"),
            "donde": str(donde)[:60],
            "tipo": type(error).__name__,
            "detalle": tapar_lo_sensible(error)[:200],
            # El renglón donde saltó (ver mostrar_error_inesperado()) y el código que vio quien
            # estaba usando la app, si hubo uno.
            "lugar": _renglon_del_error(error),
            "codigo": codigo,
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
        pass      # anotar un error jamás puede romper nada

# ============================================================
# CONFIGURACIÓN DE PÁGINA
# ============================================================


@st.cache_resource
def _actividad_del_mostrador():
    """Cuándo empezó y cuándo terminó de dibujarse la última pantalla. Ver ceder_al_mostrador().
    Va acá arriba porque se usa en la línea de abajo, al arrancar cada dibujo."""
    return {"empezo": 0.0, "termino": 0.0}




# ============================================================
# MODO DE VISTA (celular / computadora)
# ============================================================
# En vez de mantener dos archivos separados (que habría que corregir dos veces cada vez que
# se cambia algo, y terminarían desincronizándose), es la misma app con dos modos de vista.
# Cada uno acomoda la pantalla distinto: el celular apila las cosas en vertical y usa un
# selector compacto; la computadora aprovecha el ancho con columnas y pestañas en fila.
def _el_navegador_es_de_celular():
    """True si el navegador dice ser de un celular, False si no, None si no se sabe.

    Se mira «Mobi» en el User-Agent, que es lo que recomiendan los que mantienen los
    navegadores: lo traen Chrome y Firefox en Android, Safari en iPhone, Samsung Internet. Una
    tablet Android dice «Android» pero no «Mobi», y un iPad dice ser una Mac: las dos quedan
    en vista de computadora, que es lo que les va con esa pantalla."""
    try:
        agente = st.context.headers.get("User-Agent") or ""
    except Exception:
        return None
    if not agente:
        return None
    return "Mobi" in agente


VISTAS = ["📱 Celular", "💻 Computadora"]


def vista_detectada():
    """La vista que corresponde según el navegador; si no se sabe, celular, como era antes."""
    return VISTAS[1] if _el_navegador_es_de_celular() is False else VISTAS[0]


def es_celular():
    # Al abrir, la vista se elige sola según el navegador. Antes arrancaba SIEMPRE en celular y
    # el que entraba desde la computadora tenía que cambiarla a mano, cada vez: el selector no
    # se guarda entre visitas. Sigue estando, por si la detección no acierta: una vez tocado,
    # manda lo que se eligió.
    # La detección NO se escribe en st.session_state["modo_vista"]: esa es la clave del
    # selector, y cargarla antes de que el selector exista (en la pantalla de entrada todavía
    # no está) deja a Streamlit con el valor bueno y a la pantalla mostrando la primera opción;
    # al siguiente toque la pantalla le devuelve la suya y la vista se da vuelta sola. Por eso
    # la detección le llega al selector como opción inicial (index=).
    return st.session_state.get("modo_vista", vista_detectada()) == VISTAS[0]


def cols(pesos, apilar_en_celular=True):
    """Devuelve columnas como st.columns, pero en modo celular apila los elementos en vertical
    (uno abajo del otro, a ancho completo) en vez de aplastarlos de costado. Para filas de 2
    elementos simples se puede pasar apilar_en_celular=False y dejarlas lado a lado."""
    cantidad = len(pesos) if isinstance(pesos, (list, tuple)) else pesos
    if es_celular() and apilar_en_celular:
        return [st.container() for _ in range(cantidad)]
    return st.columns(pesos)


CSS_CUSTOM = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

/* ==== LOS COLORES Y LAS MEDIDAS ====
   Oscuro y sobrio: grises azulados, un solo color de acento (el ámbar de la marca) para lo que
   hay que hacer, y verde, ámbar y rojo solo para decir cómo está algo. Los mismos colores van
   en .streamlit/config.toml: si se cambia uno, cambiar el otro. */
:root {
  --bg: #0F1216;
  --bg-panel: #161A1F;
  --bg-panel-2: #1C2127;
  --bg-input: #0C0F12;
  --border: #252B33;
  --border-strong: #323943;
  --text: #E8EBEE;
  --text-muted: #94A0AC;
  --accent: #E8A33D;
  --accent-hover: #F0B456;
  --accent-soft: rgba(232, 163, 61, 0.12);
  --accent-2: #5B9BF7;
  --ok: #3FB27F;
  --bad: #E5534B;
  --radius: 12px;
  --radius-sm: 9px;
  --shadow: 0 1px 2px rgba(0, 0, 0, 0.35), 0 10px 30px rgba(0, 0, 0, 0.22);
}

html, body, [class*="css"], .stApp, button, input, textarea, select {
  font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif;
  font-feature-settings: "cv11", "ss01";
}
[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(1200px 380px at 50% -140px, rgba(232, 163, 61, 0.07), transparent 70%),
    var(--bg);
  color: var(--text);
}
/* Menos aire arriba: la barra de Streamlit queda vacía (ver toolbarMode en config.toml). */
[data-testid="stHeader"] { background: transparent; height: 0 !important; min-height: 0 !important; }
.block-container { padding-top: 1rem !important; }
h1, h2, h3, h4 { font-family: 'Inter', sans-serif !important; font-weight: 700 !important;
  letter-spacing: -0.02em; color: var(--text); }
h3 { font-size: 1.25rem !important; }
p, li { line-height: 1.55; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: var(--text-muted) !important; }
code { font-family: 'IBM Plex Mono', monospace; color: var(--accent-2); background: rgba(91, 155, 247, 0.08);
  padding: 0.05em 0.35em; border-radius: 5px; }
hr { border-color: var(--border) !important; margin: 1.1rem 0 !important; }

/* ==== EL ENCABEZADO ====
   Un solo renglón: la marca a la izquierda y, a la derecha, los avisos y quién está adentro
   (ver «ENCABEZADO» en app.py). Antes eran dos: la tarjeta y otro con la sesión, la vista y
   «Salir», que en el celular ocupaba todo el ancho. */
.st-key-barra_superior {
  padding: 8px 10px 8px 12px !important; margin-bottom: 6px;
  background: linear-gradient(180deg, var(--bg-panel-2) 0%, var(--bg-panel) 100%);
  border: 1px solid var(--border); border-radius: 16px; box-shadow: var(--shadow);
}
.st-key-barra_superior [data-testid="stPopoverButton"] { min-height: 2.35rem; }
.app-bar { display: flex; align-items: center; gap: 12px; min-width: 0; }
.app-bar__logo {
  width: 38px; height: 38px; border-radius: 11px; flex: 0 0 auto;
  display: flex; align-items: center; justify-content: center; font-size: 1.15rem;
  background: linear-gradient(135deg, var(--accent) 0%, #C47719 100%);
  box-shadow: 0 2px 10px rgba(232, 163, 61, 0.30), inset 0 1px 0 rgba(255, 255, 255, 0.25);
}
.app-bar__title { font-weight: 700; font-size: 1.08rem; color: var(--text); line-height: 1.15;
  letter-spacing: -0.015em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.app-bar__sub { font-size: 0.76rem; color: var(--text-muted); line-height: 1.25; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }

/* El título de cada sección, con para qué sirve abajo (ver «Para qué sirve» en app.py). */
.titulo-seccion { margin: 2px 0 6px 2px; }
.titulo-seccion__nombre { font-size: 1.55rem; font-weight: 700; letter-spacing: -0.025em;
  color: var(--text); line-height: 1.2; }

/* ==== LA NAVEGACIÓN ====
   Las opciones de un radio como pastillas, sin el puntito de formulario. Se esconde el aro
   entero (label > div > div), no solo el punto de adentro: con el punto solo, en cada pastilla
   quedaba un circulito vacío al lado del nombre. */
[data-testid="stRadioOption"] > div > div:not([data-testid="stMarkdownContainer"]) {
  display: none !important;
}
/* [role="radiogroup"] y no «.stRadio label» a secas: así agarraba también el TÍTULO del grupo
   —«Buscar por:», «Qué tan lejos buscar:»— y lo dibujaba como una opción más, con su pastilla.
   Se vio en capturas de la app en un celular. */
.stRadio [role="radiogroup"] { gap: 6px; flex-wrap: wrap; }
.stRadio [role="radiogroup"] label {
  background: var(--bg-panel); border: 1px solid var(--border); border-radius: 10px !important;
  padding: 6px 14px !important; transition: background 0.15s ease, border-color 0.15s ease;
}
.stRadio [role="radiogroup"] label:hover { border-color: var(--border-strong); background: var(--bg-panel-2); }
.stRadio [role="radiogroup"] label:has(input:checked) { border-color: rgba(232, 163, 61, 0.55);
  background: var(--accent-soft); }
.stRadio [role="radiogroup"] label:has(input:checked) p { color: var(--accent); font-weight: 600; }

/* La barra de secciones: un renglón. En el celular se desliza de costado. Todo a lo ancho de
   la pantalla y no más: sin esto la barra se estiraba al largo de sus botones y la PÁGINA
   entera se corría de costado en el celular. */
.st-key-nav_principal, .st-key-nav_principal [data-testid="stElementContainer"],
.st-key-nav_principal .stRadio, .st-key-nav_principal .stRadio > div {
  max-width: 100% !important; min-width: 0 !important;
}
.st-key-nav_principal [role="radiogroup"] {
  flex-wrap: nowrap !important; overflow-x: auto; gap: 2px !important;
  max-width: 100%; box-sizing: border-box;
  /* Los botones de radio escondidos de cada opción van con position: absolute. Sin esto se
     ubicaban contra el contenedor principal y lo ensanchaban: la página entera se corría de
     costado al tocar una sección de la derecha. */
  position: relative;
  padding: 4px; background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: 14px; scrollbar-width: none;
}
.st-key-nav_principal [role="radiogroup"]::-webkit-scrollbar { display: none; }
.st-key-nav_principal [role="radiogroup"] label {
  flex: 0 0 auto; background: transparent !important; border: 1px solid transparent !important;
  padding: 7px 12px !important;
}
.st-key-nav_principal [role="radiogroup"] label:hover { background: var(--bg-panel-2) !important; }
.st-key-nav_principal [role="radiogroup"] label:has(input:checked) {
  background: var(--accent-soft) !important; border-color: rgba(232, 163, 61, 0.45) !important;
  box-shadow: inset 0 -2px 0 var(--accent);
}
.st-key-nav_principal [role="radiogroup"] label p { white-space: nowrap; font-weight: 600; font-size: 0.9rem; }
/* Con pocas secciones —sin sesión son tres: Buscador, Lista WhatsApp y Modo Mecánico— van en
   uno o dos renglones también en el celular. Deslizándose, al elegir la de la derecha la primera
   quedaba cortada («r» de «Buscador»), y el cliente no veía cómo volver. Cada opción va en su
   propia caja: se cuentan las cajas (con «label:nth-of-type» se aplicaba también a las doce). */
.st-key-nav_principal [role="radiogroup"]:not(:has(> div:nth-child(5))) {
  flex-wrap: wrap !important; overflow-x: visible;
}
/* En la computadora no hay dedo para deslizar ni barra que se vea: si no entran, van en dos
   renglones; en el celular siguen deslizándose. */
@media (min-width: 768px) {
  .st-key-nav_principal [role="radiogroup"] { flex-wrap: wrap !important; overflow-x: visible; }
  .st-key-nav_principal [role="radiogroup"] label { padding: 6px 8px !important; }
  .st-key-nav_principal [role="radiogroup"] label p { font-size: 0.85rem; }
}

/* Los renglones de productos (los del menú del click derecho): una lista con separadores,
   como una tabla, en vez de texto suelto. */
[class*="st-key-conmenu_"] { border-bottom: 1px solid var(--border); padding: 4px 6px 6px 6px;
  border-radius: 0 !important; }
[class*="st-key-conmenu_"]:last-of-type { border-bottom: none; }

/* ==== LOS BOTONES ====
   Por su data-testid: «.stButton > button» no agarraba los que tienen ayuda (help=), que van
   un nivel más adentro, y unos quedaban de un color y otros de otro. */
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"],
[data-testid="stPopoverButton"], .stDownloadButton button, .stLinkButton a {
  background: var(--bg-panel-2) !important; border: 1px solid var(--border-strong) !important;
  border-radius: var(--radius-sm) !important; color: var(--text) !important; font-weight: 500 !important;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.05s ease;
}
[data-testid="stBaseButton-secondary"]:hover, [data-testid="stBaseButton-secondaryFormSubmit"]:hover,
[data-testid="stPopoverButton"]:hover, .stDownloadButton button:hover, .stLinkButton a:hover {
  border-color: rgba(232, 163, 61, 0.6) !important; background: #222831 !important;
}
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"],
[data-testid="stPopoverButton"][kind="primary"] {
  background: var(--accent) !important; border: 1px solid var(--accent) !important;
  color: #17120A !important; font-weight: 600 !important; border-radius: var(--radius-sm) !important;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.22), 0 4px 14px rgba(232, 163, 61, 0.16);
}
[data-testid="stBaseButton-primary"] p, [data-testid="stBaseButton-primaryFormSubmit"] p { color: #17120A !important; }
[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover {
  background: var(--accent-hover) !important; border-color: var(--accent-hover) !important;
}
button:active { transform: translateY(1px); }
button:disabled { opacity: 0.45 !important; }

/* ==== LOS CAMPOS ==== */
[data-testid="stTextInputRootElement"], [data-testid="stNumberInputContainer"],
.stTextArea [data-baseweb="textarea"], .stSelectbox [data-baseweb="select"] > div,
.stMultiSelect [data-baseweb="select"] > div, .stDateInput [data-baseweb="input"] {
  background: var(--bg-input) !important; border: 1px solid var(--border-strong) !important;
  border-radius: var(--radius-sm) !important;
}
[data-testid="stTextInputRootElement"] input, [data-testid="stNumberInputContainer"] input,
.stTextArea textarea, .stDateInput input { background: transparent !important; color: var(--text) !important; }
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stNumberInputContainer"]:focus-within,
.stTextArea [data-baseweb="textarea"]:focus-within, .stSelectbox [data-baseweb="select"] > div:focus-within {
  border-color: var(--accent) !important; box-shadow: 0 0 0 3px rgba(232, 163, 61, 0.15) !important;
}
[data-testid="stNumberInputStepDown"], [data-testid="stNumberInputStepUp"] { background: transparent !important; }
[data-testid="stWidgetLabel"] p { font-weight: 500; color: #C9D0D7; }
.stCheckbox input:checked, .stCheckbox [data-baseweb="checkbox"] svg { accent-color: var(--accent); }

/* Subida de archivos */
[data-testid="stFileUploaderDropzone"] {
  background: var(--bg-panel) !important; border: 1px dashed var(--border-strong) !important;
  border-radius: var(--radius) !important;
}
/* Los textos de la caja de subir archivos vienen en inglés y Streamlit no deja cambiarlos:
   «Upload» y «200MB per file • PNG, JPG», en cinco pantallas. Se tapan y se escriben en
   castellano. La lista de tipos no hace falta: el selector del teléfono ya muestra solo los
   archivos que sirven. */
[data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p { font-size: 0 !important; }
[data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p::after {
  content: "Elegir archivo"; font-size: 0.9rem;
}
[data-testid="stFileUploaderDropzoneInstructions"] span { font-size: 0 !important; }
[data-testid="stFileUploaderDropzoneInstructions"] span::after {
  content: "Hasta 200 MB por archivo"; font-size: 0.8rem;
}
/* Lo mismo con el botón de la cámara (escanear el código de barras): decía «Take Photo» y,
   después de sacarla, «Clear photo». */
[data-testid="stCameraInputButton"] { font-size: 0 !important; }
[data-testid="stCameraInputButton"]::after { content: "📷 Sacar la foto"; font-size: 0.95rem; }
[data-testid="stCameraInputButton"]:has(span)::after { content: "🔄 Sacar otra"; }
[data-testid="stCameraInputButton"] svg { display: none; }

/* ==== TARJETAS, DESPLEGABLES Y VENTANAS ==== */
[data-testid="stVerticalBlockBorderWrapper"], .stForm, [data-testid="stForm"] {
  border-radius: var(--radius) !important; border-color: var(--border) !important;
}
[data-testid="stForm"] { background: var(--bg-panel); }
[data-testid="stExpander"] details {
  border: 1px solid var(--border) !important; border-radius: var(--radius) !important;
  background: var(--bg-panel); overflow: hidden;
}
[data-testid="stExpander"] { margin-bottom: 6px; }
[data-testid="stExpander"] summary { background: transparent !important; font-weight: 600; padding-top: 0.7rem;
  padding-bottom: 0.7rem; }
[data-testid="stExpander"] summary:hover { background: var(--bg-panel-2) !important; }
[data-testid="stExpander"] details[open] > summary { border-bottom: 1px solid var(--border); }
[data-testid="stDialog"] [role="dialog"] {
  background: var(--bg-panel) !important; border: 1px solid var(--border-strong);
  border-radius: 18px !important; box-shadow: 0 24px 80px rgba(0, 0, 0, 0.55) !important;
}
[data-baseweb="popover"] > div { border-radius: var(--radius) !important; }
[data-testid="stToast"] { background: var(--bg-panel-2) !important; border: 1px solid var(--border-strong);
  border-left: 3px solid var(--accent); border-radius: var(--radius) !important; box-shadow: var(--shadow); }

/* Métricas: una tarjeta con el número grande. */
[data-testid="stMetric"] {
  background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 12px 16px;
}
[data-testid="stMetricLabel"] p { color: var(--text-muted) !important; font-size: 0.82rem !important; font-weight: 500; }
[data-testid="stMetricValue"] { font-family: 'Inter', sans-serif; font-weight: 700; letter-spacing: -0.02em;
  color: var(--text); font-variant-numeric: tabular-nums; }

/* Avisos: un borde de color al costado y el fondo apenas teñido. */
[data-testid="stAlert"] > div, [data-testid="stAlertContainer"] { border-radius: var(--radius) !important; }
[data-testid="stAlertContainer"] { border: 1px solid var(--border); }
[data-testid="stDataFrame"] { border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }

/* Los gráficos (st.bar_chart / Vega-Lite) muestran un tooltip flotante al tocar una barra.
   En celular no hay evento que lo "suelte" al hacer scroll con el dedo, y queda pegado en
   pantalla tapando el contenido de abajo. Se desactiva: el dato ya se ve en las barras. */
#vg-tooltip-element, .vg-tooltip { display: none !important; }

/* El plano del depósito escrito a mano: cada letra tiene que ocupar lo mismo, como en una hoja
   cuadriculada (ver «EL MAPA DEL DEPÓSITO» en logica/mapa.py). */
[class*="st-key-plano_a_mano"] textarea { font-family: 'IBM Plex Mono', monospace !important;
  letter-spacing: .08em; line-height: 1.25 !important; }

/* Las ayudas plegadas (ver ayuda()): un renglón gris, sin caja, que se abre con una línea de
   color al costado. Se distinguen de los desplegables que son parte de la pantalla. */
[class*="st-key-ayuda_"] [data-testid="stExpander"],
[class*="st-key-ayuda_"] [data-testid="stExpander"] details {
  border: none !important; background: transparent !important; box-shadow: none !important;
  margin: 0 !important;
}
[class*="st-key-ayuda_"] [data-testid="stExpander"] summary {
  background: transparent !important; padding: 0.1rem 0 !important; min-height: 0 !important;
  font-weight: 500 !important;
}
[class*="st-key-ayuda_"] [data-testid="stExpander"] summary p {
  font-size: 0.84rem !important; color: var(--text-muted) !important;
}
[class*="st-key-ayuda_"] [data-testid="stExpander"] summary:hover p { color: var(--accent) !important; }
[class*="st-key-ayuda_"] [data-testid="stExpander"] details[open] > summary { border-bottom: none !important; }
[class*="st-key-ayuda_"] [data-testid="stExpander"] summary [data-testid="stIconMaterial"] {
  color: var(--text-muted); font-size: 1rem;
}
[class*="st-key-ayuda_"] [data-testid="stExpanderDetails"] {
  border-left: 2px solid var(--accent); margin: 0.2rem 0 0.5rem 0.45rem;
  padding: 0.1rem 0 0.2rem 0.9rem !important;
}
[class*="st-key-ayuda_"] [data-testid="stExpanderDetails"] p,
[class*="st-key-ayuda_"] [data-testid="stExpanderDetails"] li {
  font-size: 0.88rem; color: var(--text-muted);
}

/* EL MENÚ DEL CLICK DERECHO: ver «EL CLICK DERECHO, LAS TECLAS Y EL PITIDO» en
   logica/interfaz.py. Lo que esconde los botones va en app.py, solo en la vista de computadora.
   La caja del script no se ve (ni deja el hueco de su renglón). */
[data-testid="stLayoutWrapper"]:has(> .st-key-ayudas_del_navegador),
.st-key-ayudas_del_navegador { display: none; }
/* Lo mismo la parte que pregunta si hay avisos para quien vende (ver «LOS AVISOS DE LO QUE
   TERMINÓ OTRO» en app.py): sus carteles salen arriba, la caja no se ve. */
[data-testid="stLayoutWrapper"]:has(> .st-key-novedades_para_mi),
.st-key-novedades_para_mi { display: none; }
.menu-del-renglon {
  position: fixed; z-index: 1000100; min-width: 230px; max-width: 360px; padding: 5px;
  background: var(--bg-panel-2); border: 1px solid var(--border-strong); border-radius: 12px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.55);
}
.menu-del-renglon button {
  display: block; width: 100%; text-align: left; padding: 8px 12px; border: 0;
  border-radius: 8px; background: none; color: var(--text); font: inherit; font-size: 0.92rem;
  cursor: pointer;
}
.menu-del-renglon button:hover:not([disabled]), .menu-del-renglon button:focus-visible {
  background: var(--accent-soft); outline: none;
}
.menu-del-renglon button[disabled] { opacity: 0.45; cursor: not-allowed; }

/* ==== LO QUE SE MUEVE ====
   El dueño pidió una página más dinámica. Que se note que la app responde, sin marear:
   - Mientras trabaja, una barra ámbar finita arriba de todo. Recién después de un instante:
     un toque que se resuelve rápido no la muestra.
   - Lo que queda viejo mientras se redibuja se apaga un poco y despacio, no de golpe (Streamlit
     lo marca con data-stale).
   - Lo que aparece entra suave, y un número que cambia —los de la caja, el 🔔— se ilumina un
     momento (la clase la pone el script del navegador: ver «EL CLICK DERECHO, LAS TECLAS Y EL
     PITIDO» en logica/interfaz.py).
   - Los botones se levantan apenas al pasarles el mouse.
   Con «reducir movimiento» prendido en el teléfono o la computadora, nada de esto se mueve. */
body:has([data-testid="stStatusWidget"])::before {
  content: ""; position: fixed; top: 0; left: 0; right: 0; height: 3px; z-index: 1000200;
  background: linear-gradient(90deg, transparent, var(--accent), transparent) no-repeat;
  background-size: 40% 100%;
  animation: trabajando 1.1s ease-in-out infinite, aparecer 0.2s ease 0.35s both;
}
@keyframes trabajando { from { background-position: -60% 0; } to { background-position: 160% 0; } }
@keyframes aparecer { from { opacity: 0; } to { opacity: 1; } }
[data-testid="stElementContainer"][data-stale="true"] {
  opacity: 0.6 !important; transition: opacity 0.25s ease 0.3s !important;
}
.stMainBlockContainer [data-testid="stElementContainer"] { animation: entrar 0.22s ease-out both; }
@keyframes entrar { from { opacity: 0; transform: translateY(3px); } to { opacity: 1; transform: none; } }
.recien-cambiado { animation: destello 1.2s ease-out; }
@keyframes destello {
  0% { color: var(--accent); text-shadow: 0 0 14px rgba(232, 163, 61, 0.6); }
  100% { text-shadow: 0 0 0 rgba(232, 163, 61, 0); }
}
[data-testid="stBaseButton-primary"]:hover:not(:disabled),
[data-testid="stBaseButton-primaryFormSubmit"]:hover:not(:disabled) {
  transform: translateY(-1px); box-shadow: 0 6px 18px rgba(232, 163, 61, 0.28);
}
[data-testid="stBaseButton-secondary"]:hover:not(:disabled) { transform: translateY(-1px); }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
</style>
"""


DB_PATH = "equivalencias_app.db"

# La conexión a la base se comparte entre todas las personas que usan la app al mismo
# tiempo (así funciona el hosting gratuito). Este candado evita que dos operaciones
# (por ejemplo una importación larga y una búsqueda de otra persona) se pisen y
# dejen todo trabado.
# OJO: este candado es de cada PASADA del script, no del proceso (ver del_proceso()), así que
# en los hechos ordena solo lo de una misma pasada: dos personas, o la pantalla y el hilo de
# fondo, tienen cada una el suyo. Lo que de verdad ordena las escrituras entre ellas es SQLite
# (modo WAL y busy_timeout, en get_connection()). Se dejó así a propósito: hacerlo del proceso
# abre una traba que hoy no existe —uno con el candado esperando la base, otro con la base
# esperando el candado— y eso se probaría recién con dos personas a la vez en el servidor.
db_lock = threading.Lock()

# Subir este número cuando se agreguen WMI nuevos: hace que la lista se vuelva a aplicar una vez
# sobre las bases que ya existen, sin pisar lo que el usuario haya corregido a mano.
SEMILLA_WMI_VERSION = "3"
# Lo mismo para el diccionario de códigos de falla: subir este número hace que la lista se
# vuelva a aplicar una vez, con INSERT OR IGNORE, así quien ya tiene la app recibe los códigos
# nuevos sin perder los que cargó o corrigió a mano.
# "4": se corrigieron P0134/P0135 y sus pares de cada sonda (estaban corridos), P0045, P0046 y
# P0451, y la causa de P0045, que ofrecía solenoides de caja automática para una falla del turbo.
# Los que alguien editó a mano (editado = 1) no se tocan.
SEMILLA_DTC_VERSION = "4"
# Y para los combos de fábrica («suelen cambiarse junto»): ver COMBOS_DE_FABRICA en datos.py.
SEMILLA_COMBOS_VERSION = "2"
# Y lo mismo para la columna `busqueda`: subir este número hace que se vuelva a calcular una vez
# sobre todos los productos ya cargados. Hace falta cada vez que cambie _sql_sin_acentos(), si
# no las filas viejas se quedan con la normalización anterior y dejan de encontrarse por lo
# nuevo, sin ningún error a la vista.
VERSION_NORMALIZACION = "2"

# La versión de las REGLAS DE CONFIANZA. Sirve para lo mismo que la de arriba: el puntaje de
# cada vínculo se guarda en la base porque el buscador lo necesita en cada búsqueda, así que
# cuando las reglas cambian, lo guardado queda contando una película vieja.
# No es teórico. Al agregar la señal de «misma descripción» y el veto del código que hoy no se
# tomaría, se recalcularon los 24.774 vínculos cargados y cambió el puntaje de 22.257 — el 90%.
# La mayoría se movió adentro de su misma banda, pero 145 BAJARON, y de esos 31 se cayeron de
# «55-74» a «0-34»: vínculos que el buscador venía mostrando como confiables y que con las
# reglas de hoy están mal. Sin esta marca, eso no se entera nadie hasta tropezárselo.
# Subir el número cuando cambien las reglas de evaluar_equivalencia(). El recálculo NO corre al
# abrir la app —son 12,8 s— sino en la tarea de fondo, igual que el descubrimiento.
VERSION_CONFIANZA = "19"   # ver VERSIONES_DE_LAS_REGLAS

# LAS REGLAS VERSIONADAS, con la fecha y qué cambió en cada una. Lo pidió una revisión con
# ChatGPT («versionar reglas como datos» y «comparar versiones»): cada vínculo guarda con qué
# versión se puntuó, cada decisión del historial también, y antes de subir una versión se
# corre pruebas_de_la_revision.py --base copia.db --linea-base: es la simulación de la regla
# nueva sobre todo lo que ya se decidió. Volver atrás una regla es volver atrás el cambio en
# git y subir el número otra vez (el repuntaje lo hace la tarea de fondo).
VERSIONES_DE_LAS_REGLAS = [
    ("19", "2026-10-26", "dos bujías que por su código calzan igual (rosca, largo, hexágono, "
                         "asiento y material) se dan una por otra aunque cambie el grado térmico; "
                         "la que no entra no es la misma"),
    ("18", "2026-10-26", "si dos listas distintas citan el mismo número de fábrica, que nombren "
                         "otros autos u otro motor no las separa; lo que contradice la pieza sí"),
    ("17", "2026-10-26", "lo que solo se alcanza pasando por otra pieza de la misma lista queda "
                         "para revisar; dos de la misma lista que citan el mismo número de "
                         "fábrica son la misma pieza"),
    ("16", "2026-10-26", "dos productos distintos de una misma lista son dos piezas, salvo "
                         "variantes, mellizos de FISPA y LUCAS y el reemplazo que nombra al otro"),
    ("15", "2026-10-12", "lo aprendido de las marcas y de las ventas no hace pasar ninguna franja "
                         "(tampoco la de «sólida», 70); y de lo vendido solo suma la instalación "
                         "que alguien confirmó que anduvo, no el silencio"),
    ("14", "2026-10-09", "un diámetro imposible (el interno mayor que el externo, el externo "
                         "más de 8 veces el interno) no prueba nada"),
    ("13", "2026-10-08", "dientes, fase y la tensión escrita «Volts V 24»"),
    ("12", "2026-10-08", "tensión, caudal, rosca, giro, cantidad y reacondicionada; tolerancia "
                         "en mm"),
    ("11", "2026-10-08", "con o sin ABS, aire o sensor; las medidas del mismo texto no suman"),
    ("10", "2026-10-08", "los vetos ganan siempre; las ventas no pasan de franja solas"),
    ("9", "2026-10-05", "el Sprint 6.07 no es un 4 cilindros"),
    ("8", "2026-10-05", "la tapa de flotante no es el conjunto"),
    ("7", "2026-10-05", "la tapa de inspección es la tapa; el dueño del número"),
    ("6", "2026-09-30", "el kit de reparación no es la bomba que repara"),
    ("5", "2026-09-29", "espesor sin unidad, sensor exterior, módulo, motores Honda y Cummins"),
    ("4", "2026-09-28", "los códigos de fábrica no se muestran en el buscador"),
]

# La versión del LECTOR DE MEDIDAS. Mismo mecanismo: las medidas se deducen de la descripción
# una vez y quedan guardadas, así que cuando el lector aprende a leer algo nuevo —el espesor de
# la junta, las vías de la ficha— lo que ya está cargado no se entera.
# Sobre la base real eran 1.402 productos con la medida escrita en el texto y 0 cargadas,
# porque llenarlas era un botón de Mantenimiento que había que saber apretar.
# Subir el número al agregar una medida nueva a medidas_desde_descripcion().
VERSION_MEDIDAS = "7"   # 7: no lee «1/2X20», «M12X162» ni «X1 X3 X4», ni un externo 8 veces el interno, y descarta lo que leyó así

# La versión del LECTOR DE APLICACIONES: a qué auto le va cada pieza, deducido de la
# descripción. Es el dato gratis más grande que tiene esta base —114.673 filas que salen de
# texto ya cargado, contra 0 que había— y el que hace andar la búsqueda por vehículo.
# Como las otras dos, corría solo después de importar una lista, así que en una base donde no
# se importó nada desde que la función existe nunca corrió.
# Subir el número al cambiar cómo se leen los modelos (o el combustible: el 8 es el D4D de
# Renault, que se leía diésel).
VERSION_APLICACIONES = "8"
# Lo que se arregla de las aplicaciones YA deducidas sin volver a leer las 111.795: los años
# imposibles (2035 a 2120, de «PEUGEOT 2061.0») y los «modelos» que son una motorización
# («CHEVROLET MPFI»). Subir el número para que se vuelva a correr una vez. Ver
# _poner_al_dia_las_aplicaciones_deducidas().
VERSION_LIMPIEZA_DE_APLICACIONES = "1"

# Quién FABRICA la pieza, leído del final de la descripción. Ver marca_de_repuesto_en().
# Subir el número al agregar marcas a MARCAS_QUE_FABRICAN_LA_PIEZA o al cambiar cómo se leen.
# 2: entraron nueve marcas más (PRESTOLITE, KOBLA, BOUGICORD, HOLLEY, TAILLOT, INDIEL, LOCX,
# PAIA, GATES), sacadas de contar las últimas palabras del catálogo real.
VERSION_MARCAS_REPUESTO = "2"

# El separador de texto pegado aprendió cosas después de que se importaran las listas, y las
# descripciones que ya estaban en la base quedaron como entraron. Ver
# reseparar_descripciones_viejas(). Subir el número al mejorar separar_texto_pegado().
VERSION_SEPARACION = "1"

# La cola de pendientes pasó a guardar UNA fila por par y a no recibir lo ya rechazado ni lo ya
# cargado (ver guardar_equivalencias_pendientes()). Esto limpia lo que quedó de antes.
# 2: además se sacan los pendientes de productos que ya no existen. Ver el trigger
# productos_sin_pendientes_colgando.
# 3: otra vuelta para lo ya cargado: reimportar una lista volvía a poner en la cola todo lo
# que ya estaba aprobado (13.756 de 13.943 con la de FISPA), y una base que reimportó algo
# desde la versión 2 lo tiene adentro. La limpieza es la misma y no cambia.
VERSION_COLA_PENDIENTES = "3"


def secretos_app():
    """Los Secrets de Streamlit, o {} si en este servidor no hay ninguno configurado.

    Preguntar si el atributo existe NO alcanza, y era lo que se hacía en los ocho lugares que
    leen secrets. El atributo existe siempre; lo que falla es LEERLO: sin un secrets.toml, el
    primer acceso tira StreamlitSecretNotFoundError. O sea que el guardián nunca se activaba y
    la excepción salía igual.

    No es un detalle de una función de IA: lo mismo pasaba en validar_password(). En un
    servidor sin secrets.toml —una instalación nueva, una copia local para probar— apretar
    «🔓 Ingresar con contraseña» tiraba la excepción en pantalla en vez de decir «contraseña
    incorrecta», y con ella se caía también cualquier candado de administrador, porque todos
    terminan llamando a validar_password().

    Probado: leer una clave cualquiera levanta StreamlitSecretNotFoundError cuando no hay
    archivo de secrets."""
    try:
        st.secrets.get("_sonda_de_existencia")
        return st.secrets
    except Exception:
        return {}


def corre_en_streamlit_cloud():
    """¿La app corre en los servidores de Streamlit (la de internet) y no en una máquina propia?
    Ahí el repositorio se clona en /mount/src. Lo que se lee del disco por ruta es del servidor,
    no del teléfono ni de la computadora de quien la usa."""
    return _CARPETA.startswith("/mount/src/")


# Lo que sobrevive a «Salir»: cómo se ve la app, no qué se hizo en ella.
CLAVES_QUE_QUEDAN_AL_SALIR = ("modo_vista",)


# Los campos de texto del buscador (ver cerrar_sesion()). auditar.py controla que estén todos.
CAMPOS_DEL_BUSCADOR_QUE_SE_VACIAN_AL_SALIR = ("busqueda_input", "texto_input", "pista_internet",
                                             "picking_codigos", "url_foto_visual",
                                             "med_paso", "med_seguro")


def cerrar_sesion():
    """«Salir», y la sesión que se cerró sola por estar sin uso: se borra TODO lo de la sesión
    menos la vista. Antes se borraban el nivel, el nombre y el mecánico, y quedaba lo demás:
    la última búsqueda, la lista de WhatsApp, el cliente o la cuenta corriente que se estaba
    mirando. En la computadora del mostrador, el que se sentaba después lo encontraba ahí (lo
    señaló una revisión con ChatGPT)."""
    for clave in list(st.session_state.keys()):
        if clave not in CLAVES_QUE_QUEDAN_AL_SALIR:
            del st.session_state[clave]
    # Borrar la clave no alcanza para lo que sigue a la vista: el navegador recuerda lo escrito
    # en cada campo que no se desarma, y después de «Salir» se vuelve al buscador, que no se
    # desarma nunca. Probado en un navegador: la última búsqueda seguía en la caja para el que
    # se sentaba después (los resultados no, el texto sí). Hay que ponerlos vacíos A PROPÓSITO,
    # que es lo que le dice al navegador que los vacíe. Los de las otras pantallas no hacen
    # falta: al salir se desarman, y ahí el navegador los olvida (la contraseña de «Ingresar»,
    # también probado, no queda).
    for clave in CAMPOS_DEL_BUSCADOR_QUE_SE_VACIAN_AL_SALIR:
        try:
            st.session_state[clave] = ""
        except Exception as _err:      # ya dibujado en esta pasada: Streamlit no deja tocarlo
            anotar_error("cerrar_sesion", _err)


def nivel_vigente_de_la_sesion():
    """El nivel que tiene que tener HOY quien está adentro: el de los Secrets, el de su cuenta
    de empleado o el de su cuenta de mecánico. None si ya no puede entrar (lo desactivaron, lo
    borraron o le sacaron la clave).

    El nivel se guarda en la sesión al entrar, y antes no se volvía a mirar: a un empleado
    desactivado, o al que le bajaban el rol de administrador a operador, le seguían valiendo
    los permisos viejos hasta que tocaba «Salir» o pasaban cuatro horas sin usarla (lo señaló
    una revisión con ChatGPT). Se mira en cada toque: es una consulta chica."""
    nivel = st.session_state.get("nivel_usuario")
    nombre = str(st.session_state.get("admin_nombre") or "")
    if nivel == "mecanico":
        c.execute("SELECT 1 FROM mecanicos WHERE id = ? AND activo = 1",
                  (st.session_state.get("mecanico_id"),))
        return "mecanico" if c.fetchone() else None
    if nivel not in ("admin", "operador"):
        return nivel
    secretos = secretos_app()
    admins = {n for n in dict(secretos.get("admin_passwords", {}))
              if es_un_usuario_de_los_secretos(n)}
    if secretos.get("admin_password"):
        admins.add("admin")
    operadores = {n for n in dict(secretos.get("operador_passwords", {}))
                  if es_un_usuario_de_los_secretos(n)}
    if nombre in admins:
        return "admin"
    if nombre in operadores:
        return "operador"
    c.execute("SELECT rol FROM usuarios WHERE nombre = ? AND activo = 1", (nombre,))
    fila = c.fetchone()
    return (fila["rol"] if fila["rol"] in ("admin", "operador") else None) if fila else None


# ============================================================
# PERMISOS ADENTRO DE LAS FUNCIONES Y REGISTRO DE CAMBIOS
# ============================================================
# LA SEGUNDA BARRERA. Los botones que borran o configuran están detrás de una contraseña en la
# pantalla (candado(), seccion_permitida()). En Streamlit la pantalla corre en el servidor y
# no hay otra forma de llamar a una función que pasar por ella, así que esa ya es una barrera
# de verdad. Pero si un día un botón nuevo se escribe sin su candado, la función igual borraba.
# Ahora las que borran, restauran o tocan permisos y cuentas vuelven a mirar quién está adentro
# (lo propuso una revisión con ChatGPT). Sin una sesión de Streamlit —el trabajo de fondo, las
# pruebas— no se mira: ahí no hay nadie a quien pedirle nada. Sin ninguna contraseña
# configurada tampoco: la app está abierta a propósito (ver seccion_permitida()).
def _nivel_de_quien_esta_adentro():
    """El nivel de la sesión de Streamlit que está corriendo, o None si no hay sesión."""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        if get_script_run_ctx() is None:
            return None
    except Exception:
        return None
    return st.session_state.get("nivel_usuario") or ""


# LA BASE CON DAÑO: SOLO LECTURA. La base abre, pero el control de integridad que corre antes
# de cada copia (ver la_base_esta_sana()) encontró daño. Hasta acá era un aviso y se seguía
# cargando encima; ahora solo el administrador, que es quien la arregla, puede cambiar algo.
# Los demás pueden buscar (lo propuso una revisión con ChatGPT: «no dejar que un empleado siga
# modificando datos»).
TEXTO_DE_SOLO_LECTURA = ("🧯 La base tiene un problema y el administrador tiene que revisarla. "
                         "Mientras tanto se puede buscar, pero no cargar ni cambiar nada.")


def la_base_tiene_dano():
    return bool(obtener_config("base_danada", ""))


def modo_solo_lectura():
    """True si quien está adentro no puede cambiar nada porque la base tiene daño."""
    return la_base_tiene_dano() and not es_admin()


def exigir_nivel(nivel, accion):
    """Levanta PermissionError si quien está adentro no tiene `nivel` («admin» o «empleado»),
    o si es empleado y la base tiene daño (ver TEXTO_DE_SOLO_LECTURA)."""
    adentro = _nivel_de_quien_esta_adentro()
    if adentro is None or not hay_claves_configuradas():
        return
    if adentro == "admin":
        return
    if nivel == "empleado" and adentro == "operador":
        if la_base_tiene_dano():
            raise PermissionError(TEXTO_DE_SOLO_LECTURA)
        return
    anotar_error("exigir_nivel", PermissionError(f"{accion}: nivel «{adentro}»"))
    raise PermissionError(f"Para {accion} hace falta entrar como "
                          f"{'administrador' if nivel == 'admin' else 'empleado'}.")


def exigir_que_sea_su_cuenta(mecanico_id, accion, si_no_es_mecanico="empleado"):
    """El portal del mecánico externo: un mecánico solo toca lo de SU cuenta —sus presupuestos,
    su código de retiro, sus movimientos—. El portal pasa siempre el de la sesión; esto es la
    segunda barrera, por si otro camino llamara a la función con otro número (como exigir_nivel()
    para las secciones). Quien no es mecánico necesita `si_no_es_mecanico` («empleado»), o nada
    (None) para lo que también se lee desde las pantallas de los empleados."""
    adentro = _nivel_de_quien_esta_adentro()
    if adentro is None or not hay_claves_configuradas():
        return
    if adentro == "mecanico":
        if st.session_state.get("mecanico_id") != mecanico_id:
            anotar_error("exigir_que_sea_su_cuenta",
                         PermissionError(f"{accion}: cuenta {mecanico_id}"))
            raise PermissionError(f"Para {accion} de otra cuenta hay que ser esa cuenta.")
        return
    if si_no_es_mecanico:
        exigir_nivel(si_no_es_mecanico, accion)


# Lo que se guarda en el registro: hasta tantos cambios, los más viejos se van.
CAMBIOS_QUE_SE_GUARDAN = 50_000


def anotar_cambio(accion, entidad, entidad_id="", antes=None, despues=None, detalle="",
                  usuario=None):
    """Una línea en el registro de cambios: quién, cuándo, qué, y el antes y el después. Nunca
    toma db_lock (lo llaman funciones que ya lo tienen) y nunca rompe lo que se estaba haciendo:
    si no se puede anotar, se anota el error y se sigue."""
    def texto(valor):
        if valor is None:
            return None
        return valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False,
                                                                default=str)
    try:
        c.execute("""INSERT INTO registro_de_cambios (usuario, accion, entidad, entidad_id,
                                                      detalle, antes, despues)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (usuario or obtener_usuario_actual(), accion, entidad, str(entidad_id),
                   str(detalle or "")[:300], texto(antes), texto(despues)))
        ultimo = c.lastrowid or 0
        if ultimo % 1000 == 0:
            c.execute("DELETE FROM registro_de_cambios WHERE id <= ?",
                      (ultimo - CAMBIOS_QUE_SE_GUARDAN,))
    except Exception as _err:
        anotar_error("anotar_cambio", _err)


def cambios_registrados(buscar="", entidad=None, entidad_id=None, limite=200):
    """Lo último del registro, del más nuevo al más viejo. Con `buscar`, lo que lo nombra en
    el usuario, la acción, la entidad, el detalle o los valores."""
    condiciones, valores = [], []
    if entidad:
        condiciones.append("entidad = ?")
        valores.append(entidad)
    if entidad_id is not None:
        condiciones.append("entidad_id = ?")
        valores.append(str(entidad_id))
    if buscar.strip():
        condiciones.append("(usuario LIKE ? OR accion LIKE ? OR entidad LIKE ? OR entidad_id "
                           "LIKE ? OR detalle LIKE ? OR antes LIKE ? OR despues LIKE ?)")
        valores += [f"%{buscar.strip()}%"] * 7
    c.execute(f"""SELECT cuando, usuario, accion, entidad, entidad_id, detalle, antes, despues
                  FROM registro_de_cambios
                  {"WHERE " + " AND ".join(condiciones) if condiciones else ""}
                  ORDER BY id DESC LIMIT ?""", valores + [int(limite)])
    return [{"Cuándo": r["cuando"], "Quién": r["usuario"], "Qué": r["accion"],
             "Sobre": f"{r['entidad']} {r['entidad_id'] or ''}".strip(), "Detalle": r["detalle"],
             "Antes": r["antes"], "Después": r["despues"]} for r in c.fetchall()]


def es_admin():
    return st.session_state.get("nivel_usuario") == "admin"


def es_operador_o_admin():
    """Para acciones que un empleado de confianza puede hacer (usar funciones de IA, agregar
    piezas a un esquema) sin necesitar la contraseña completa de administrador, que además
    desbloquea borrados y configuración sensible."""
    return st.session_state.get("nivel_usuario") in ("admin", "operador")


# Cuántas vueltas se le da a la contraseña antes de guardarla. Cuantas más, más caro es
# probarlas una por una — y también más tarda el ingreso.
# El número sale de medir, y hay que tener en cuenta algo: para entrar no se pide el nombre de
# usuario, así que se prueba contra TODOS los usuarios activos hasta encontrar el que coincide.
# O sea que el costo se multiplica por la cantidad de gente que trabaja en el negocio:
#     100.000 vueltas ->  61 ms por usuario -> 0,6 s de ingreso con diez personas
#     200.000 vueltas -> 121 ms por usuario -> 1,2 s de ingreso con diez personas
# Se eligen 100.000: el ingreso queda por debajo del segundo y romper un diccionario de cien
# mil claves pasa de dos centésimas de segundo a más de hora y media.
VUELTAS_CLAVE = 100_000


def hash_password(password, salt=None, formato=None):
    """Nunca guardamos la contraseña en texto plano — se guarda un hash junto con una sal
    aleatoria distinta por usuario, para que ni siquiera dos personas con la misma clave
    tengan el mismo hash guardado.

    Antes eso era UN solo SHA-256, y ahí estaba el problema: SHA-256 está hecho para ser
    rápido. Una placa de video prueba miles de millones por segundo, así que con el hash a la
    vista una clave de mostrador («chavaje», «1234», el nombre del negocio) cae en segundos.
    Y el hash está a la vista más de lo que parece: el backup de la base incluye la tabla de
    usuarios, y este mismo backup se sube al repositorio de GitHub para que sobreviva a los
    reinicios del hosting. Si ese repositorio es público, las claves de todos están publicadas.

    Ahora se usa PBKDF2, que es el mismo SHA-256 repetido 200.000 veces: entrar sigue tardando
    lo mismo para una persona (60 ms) y cuesta 200.000 veces más para quien prueba a lo bruto.
    No hace falta instalar nada, viene con Python.

    El formato guardado dice cómo se generó ('pbkdf2$200000$...'), así que las claves viejas
    se siguen pudiendo verificar y se pasan al formato nuevo solas la próxima vez que la
    persona entra. Nadie tiene que cambiar su clave."""
    if salt is None:
        salt = os.urandom(16).hex()
    if formato == "sha256":          # el de antes, solo para poder verificar lo ya guardado
        return hashlib.sha256((salt + password).encode("utf-8")).hexdigest(), salt
    crudo = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                salt.encode("utf-8"), VUELTAS_CLAVE)
    return f"pbkdf2${VUELTAS_CLAVE}${crudo.hex()}", salt


def verificar_password(password, guardado, salt):
    """¿Esta contraseña corresponde al hash guardado? Entiende el formato viejo y el nuevo.

    Devuelve (coincide, hay_que_actualizar). Lo segundo es para pasar al formato nuevo los
    hashes viejos sin molestar a nadie."""
    if not guardado:
        return False, False
    if str(guardado).startswith("pbkdf2$"):
        try:
            _, vueltas, esperado = str(guardado).split("$", 2)
            crudo = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                        salt.encode("utf-8"), int(vueltas))
        except (ValueError, TypeError) as _err:
            anotar_error("verificar_password", _err)
            return False, False
        # compare_digest y no ==: comparar de a byte tarda distinto según cuántos coincidan,
        # y con muchos intentos eso deja adivinar el hash carácter por carácter.
        return hmac.compare_digest(crudo.hex(), esperado), int(vueltas) != VUELTAS_CLAVE
    viejo, _ = hash_password(password, salt, formato="sha256")
    return hmac.compare_digest(viejo, str(guardado)), True


# CADA CUENTA CON SU CLAVE. Al entrar no se escribe el nombre: la contraseña sola dice quién
# sos. Con dos cuentas con la misma clave, entraba siempre la primera que se encontraba —un
# taller como otro taller, o peor, un taller como un empleado— (lo señaló una revisión con
# ChatGPT). Al crear una cuenta o cambiarle la clave, se mira que nadie más la use.
TEXTO_CLAVE_REPETIDA = ("Esa contraseña ya la usa otra cuenta. Cada cuenta necesita la suya: al "
                        "entrar, la contraseña sola dice quién sos.")


def clave_ya_usada(password, excepto_usuario=None, excepto_mecanico=None):
    """True si alguna cuenta activa —de los Secrets, de empleado o de taller— ya usa esa clave."""
    secretos = secretos_app()
    de_los_secretos = [p for seccion in ("admin_passwords", "operador_passwords")
                       for n, p in dict(secretos.get(seccion, {})).items()
                       if es_un_usuario_de_los_secretos(n)]
    if secretos.get("admin_password"):
        de_los_secretos.append(secretos["admin_password"])
    if any(hmac.compare_digest(str(p), str(password)) for p in de_los_secretos):
        return True
    for tabla, excepto in (("usuarios", excepto_usuario), ("mecanicos", excepto_mecanico)):
        c.execute(f"SELECT id, password_hash, salt FROM {tabla} WHERE activo = 1 AND id IS NOT ?",
                  (excepto,))
        if any(verificar_password(password, f["password_hash"], f["salt"])[0]
               for f in c.fetchall()):
            return True
    return False


def crear_usuario(nombre, password, rol="operador", solo_deposito=False):
    exigir_nivel("admin", "crear empleados")
    if clave_ya_usada(password):
        raise ValueError(TEXTO_CLAVE_REPETIDA)
    h, salt = hash_password(password)
    with db_lock:
        c.execute("""INSERT INTO usuarios (nombre, password_hash, salt, rol, solo_deposito)
                     VALUES (?, ?, ?, ?, ?)""",
                  (nombre.strip(), h, salt, rol, 1 if solo_deposito and rol != "admin" else 0))
        anotar_cambio("creó empleado", "usuario", nombre.strip(),
                      despues={"rol": rol, "solo_deposito": bool(solo_deposito)})
        conn.commit()


def listar_usuarios():
    c.execute("""SELECT id AS "ID", nombre AS "Nombre", rol AS "Rol",
                 CASE WHEN COALESCE(solo_deposito, 0) = 1 THEN '📦 Sí' ELSE '' END
                     AS "Del depósito",
                 CASE WHEN activo=1 THEN 'Sí' ELSE 'No' END AS "Activo", creado_en AS "Creado"
                 FROM usuarios ORDER BY nombre""")
    return filas_a_listas(c)


# LOS DEL DEPÓSITO. Lo pidió el dueño: «el depósito separalo, así los chicos del depósito se
# meten ahí y no reniegan». Un empleado marcado «del depósito» entra directo a 📦 Depósito y
# ve solo eso y ↩️ Devoluciones (ver PAGINAS_DEL_DEPOSITO): sin el buscador, las estadísticas
# ni los avisos de administración en el medio. Es un operador como cualquiera —puede entregar,
# recibir y armar el mapa—; el administrador nunca queda limitado.
def es_del_deposito():
    """¿Quien está adentro es «del depósito»? Ver «LOS DEL DEPÓSITO»."""
    if st.session_state.get("nivel_usuario") != "operador":
        return False
    c.execute("SELECT solo_deposito FROM usuarios WHERE nombre = ? AND activo = 1",
              (st.session_state.get("admin_nombre") or "",))
    fila = c.fetchone()
    return bool(fila and fila["solo_deposito"])


def cambiar_solo_deposito(usuario_id, valor):
    """Marca (o desmarca) a un empleado como «del depósito». Solo el administrador."""
    exigir_nivel("admin", "cambiar lo que ve un empleado")
    with db_lock:
        c.execute("UPDATE usuarios SET solo_deposito = ? WHERE id = ? AND rol != 'admin'",
                  (1 if valor else 0, usuario_id))
        cambio = c.rowcount
        anotar_cambio("lo marcó del depósito" if valor else "le sacó lo del depósito", "usuario",
                      usuario_id)
        conn.commit()
    return bool(cambio)


def validar_password_usuario(password):
    c.execute("SELECT id, nombre, password_hash, salt, rol FROM usuarios WHERE activo = 1")
    for fila in c.fetchall():
        coincide, hay_que_actualizar = verificar_password(password, fila["password_hash"],
                                                           fila["salt"])
        if coincide:
            if hay_que_actualizar:
                # Se pasa al formato nuevo en silencio, la primera vez que entra.
                try:
                    nuevo, sal_nueva = hash_password(password)
                    with db_lock:
                        c.execute("UPDATE usuarios SET password_hash=?, salt=? WHERE id=?",
                                  (nuevo, sal_nueva, fila["id"]))
                        conn.commit()
                except sqlite3.Error as _err:
                    anotar_error("validar_password_usuario", _err)
            return fila["nombre"], fila["rol"]
    return None, None


def cambiar_password_usuario(usuario_id, nueva_password):
    exigir_nivel("admin", "cambiar contraseñas")
    if clave_ya_usada(nueva_password, excepto_usuario=usuario_id):
        raise ValueError(TEXTO_CLAVE_REPETIDA)
    h, salt = hash_password(nueva_password)
    with db_lock:
        c.execute("UPDATE usuarios SET password_hash=?, salt=? WHERE id=?", (h, salt, usuario_id))
        # La contraseña no: solo que se cambió.
        anotar_cambio("cambió la contraseña", "usuario", usuario_id)
        conn.commit()


def activar_desactivar_usuario(usuario_id, activo):
    exigir_nivel("admin", "activar o desactivar empleados")
    with db_lock:
        c.execute("UPDATE usuarios SET activo=? WHERE id=?", (1 if activo else 0, usuario_id))
        anotar_cambio("reactivó empleado" if activo else "desactivó empleado", "usuario",
                      usuario_id)
        conn.commit()


def eliminar_usuario(usuario_id):
    exigir_nivel("admin", "eliminar empleados")
    with db_lock:
        c.execute("SELECT nombre, rol FROM usuarios WHERE id=?", (usuario_id,))
        antes = c.fetchone()
        c.execute("DELETE FROM usuarios WHERE id=?", (usuario_id,))
        anotar_cambio("eliminó empleado", "usuario", usuario_id,
                      antes=dict(antes) if antes else None)
        conn.commit()


def crear_mecanico(nombre, password):
    exigir_nivel("admin", "crear cuentas de taller")
    if clave_ya_usada(password):
        raise ValueError(TEXTO_CLAVE_REPETIDA)
    h, salt = hash_password(password)
    with db_lock:
        c.execute("INSERT INTO mecanicos (nombre, password_hash, salt) VALUES (?, ?, ?)",
                   (nombre.strip(), h, salt))
        anotar_cambio("creó taller", "taller", nombre.strip())
        conn.commit()


def listar_mecanicos():
    c.execute("""SELECT id AS "ID", nombre AS "Nombre",
                 CASE WHEN activo=1 THEN 'Sí' ELSE 'No' END AS "Activo", creado_en AS "Creado"
                 FROM mecanicos ORDER BY nombre""")
    return filas_a_listas(c)


def validar_password_mecanico(password):
    """(id, nombre) del taller con esa clave, o (None, None). NO tiene freno propio: el ingreso
    la llama desde validar_password(con_mecanicos=True), detrás del freno de intentos."""
    c.execute("SELECT id, nombre, password_hash, salt FROM mecanicos WHERE activo = 1")
    for fila in c.fetchall():
        # verificar_password() compara con compare_digest; acá estaba con ==.
        if verificar_password(password, fila["password_hash"], fila["salt"])[0]:
            return fila["id"], fila["nombre"]
    return None, None


def activar_desactivar_mecanico(mecanico_id, activo):
    # Solo administrador, como crearlo o borrarlo: reactivar un taller le devuelve la cuenta
    # corriente. La pantalla ya estaba en la sección de administrador.
    exigir_nivel("admin", "activar o desactivar un taller")
    with db_lock:
        c.execute("UPDATE mecanicos SET activo=? WHERE id=?", (1 if activo else 0, mecanico_id))
        conn.commit()


def eliminar_mecanico(mecanico_id):
    exigir_nivel("admin", "eliminar cuentas de taller")
    with db_lock:
        c.execute("SELECT nombre FROM mecanicos WHERE id=?", (mecanico_id,))
        antes = c.fetchone()
        c.execute("DELETE FROM mecanicos WHERE id=?", (mecanico_id,))
        anotar_cambio("eliminó taller", "taller", mecanico_id,
                      antes=antes["nombre"] if antes else None)
        conn.commit()


# Cuántos intentos fallidos se dejan pasar sin freno, y hasta cuánto llega la espera.
# Esta app vive en una dirección pública y el ingreso es UN campo de contraseña, sin nombre de
# usuario: cualquiera puede probar claves todo el día. PBKDF2 protege el hash si alguien se
# baja la base; no protege nada contra probar «chavaje», «1234» o el nombre del negocio contra
# la pantalla de ingreso, que es como se entra de verdad a un sistema de mostrador.
#
# La espera crece al doble con cada fallo y se corta a un minuto. Lo que eso hace es cambiar
# el orden de magnitud del problema: sin freno se prueban miles de claves por minuto; con esto,
# después del quinto intento se prueba una por minuto y adivinar deja de ser viable.
#
# EL PRECIO, dicho de frente: no hay forma de saber la IP desde Streamlit, así que el freno es
# para todos. Alguien que insista puede dejar al dueño esperando hasta un minuto. Se eligió ese
# tope justamente por eso — un minuto de espera es molesto, probar claves sin límite es perder
# el negocio— y por eso NO se bloquea la cuenta: la espera pasa sola.
INTENTOS_ANTES_DE_FRENAR = 3
ESPERA_MAXIMA_POR_INTENTOS = 60


def _segundos_de_espera_por_intentos():
    """Cuántos segundos faltan antes de aceptar otro intento de contraseña. 0 si se puede ya.

    El contador va en la base y no en session_state a propósito: session_state se borra
    recargando la página, así que un freno guardado ahí se saltea apretando F5."""
    try:
        fallidos = int(obtener_config("login_fallidos", "0") or 0)
        if fallidos < INTENTOS_ANTES_DE_FRENAR:
            return 0
        ultimo = obtener_config("login_ultimo_fallo", "")
        if not ultimo:
            return 0
        cuando = datetime.strptime(ultimo[:19], "%Y-%m-%d %H:%M:%S")
        espera = min(2 ** (fallidos - INTENTOS_ANTES_DE_FRENAR), ESPERA_MAXIMA_POR_INTENTOS)
        faltan = espera - (datetime.now() - cuando).total_seconds()
        return int(faltan) + 1 if faltan > 0 else 0
    except (ValueError, TypeError) as _err:
        anotar_error("_segundos_de_espera_por_intentos", _err)
        return 0


def _anotar_intento(acerto):
    """Lleva la cuenta de los intentos fallidos seguidos. Acertar la reinicia."""
    try:
        if acerto:
            guardar_config("login_fallidos", "0")
            return
        fallidos = int(obtener_config("login_fallidos", "0") or 0) + 1
        guardar_config("login_fallidos", str(fallidos))
        guardar_config("login_ultimo_fallo", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    except (ValueError, TypeError) as _err:
        anotar_error("_anotar_intento", _err)


def validar_password(clave, con_mecanicos=False):
    """Chequea la contraseña contra los secrets de admin/operador Y contra las cuentas creadas
    desde la propia app (tabla usuarios). Devuelve (nombre, nivel, error) — nivel es 'admin',
    'operador', o None si no matcheó ninguna.

    con_mecanicos=True (solo el ingreso): también las claves de los talleres, que dan nivel
    'mecanico'. Van ADENTRO y no después, a propósito: el ingreso probaba la clave de los
    mecánicos aparte, aunque este freno hubiera dicho «esperá», así que contra el portal de
    mecánicos se podían probar claves sin límite —y cada una calculaba un PBKDF2 por taller—, y
    un mecánico que acertaba no reiniciaba la cuenta de fallos (lo encontró una revisión con
    ChatGPT). Las pantallas que piden clave para una acción no los incluyen: la clave de un
    taller no autoriza nada adentro del negocio."""
    secretos = secretos_app()
    # [admin_passwords] / [operador_passwords] en Streamlit Secrets, cada una con nombre:clave.
    # También soporta la forma anterior de una sola clave (admin_password) por compatibilidad.
    # Sin las claves de la copia a GitHub: pegadas al final de los secretos quedan adentro de
    # la última sección (ver config_github()), y leídas como usuarios, el nombre del
    # repositorio —que no es ningún secreto— entraba como contraseña de administrador.
    admin_passwords = {n: p for n, p in dict(secretos.get("admin_passwords", {})).items()
                       if es_un_usuario_de_los_secretos(n)}
    clave_unica = secretos.get("admin_password")
    if clave_unica:
        admin_passwords.setdefault("admin", clave_unica)
    operador_passwords = {n: p for n, p in dict(secretos.get("operador_passwords", {})).items()
                          if es_un_usuario_de_los_secretos(n)}

    # El freno va ANTES de comparar nada, y también antes de validar_password_usuario(), que
    # calcula un PBKDF2 por cada empleado activo: sin el freno, cada intento fallido le cuesta
    # al servidor 25 ms por empleado y eso lo paga la app entera, que es un solo proceso.
    _faltan = _segundos_de_espera_por_intentos()
    if _faltan:
        # El intento rechazado TAMBIÉN cuenta, y eso es lo que hace que el freno sirva de algo.
        # Sin contarlo, la espera se quedaba clavada en un segundo para siempre: el que insiste
        # vuelve a probar cada segundo y en un día prueba ochenta mil claves. Contándolo, la
        # espera se duplica con cada insistencia hasta el minuto, y la cuenta deja de cerrarle.
        # Para el dueño que se apuró es un segundo más; para el que está probando, el final.
        _anotar_intento(False)
        return None, None, (
            f"Demasiados intentos fallidos seguidos. Esperá {_faltan} segundo(s) y probá una "
            "sola vez: cada intento durante la espera la alarga. No hay ninguna cuenta "
            "bloqueada, la espera pasa sola."
        )

    # compare_digest y no ==, por el mismo motivo que está escrito en verificar_password():
    # comparar de a byte tarda distinto según cuántos caracteres coincidan, y con muchos
    # intentos eso deja adivinar la clave de a un carácter. Acá estaba con == a secas, así que
    # el cuidado que se había tomado con las claves de la base no valía para las de los secrets.
    nombre_admin = next((n for n, p in admin_passwords.items()
                         if hmac.compare_digest(str(p), str(clave))), None)
    if nombre_admin:
        _anotar_intento(True)
        return nombre_admin, "admin", None
    nombre_operador = next((n for n, p in operador_passwords.items()
                            if hmac.compare_digest(str(p), str(clave))), None)
    if nombre_operador:
        _anotar_intento(True)
        return nombre_operador, "operador", None

    # Cuentas creadas desde la propia app (además de las de Secrets)
    nombre_db, rol_db = validar_password_usuario(clave)
    if nombre_db:
        _anotar_intento(True)
        return nombre_db, rol_db, None

    if con_mecanicos:
        _mecanico_id, nombre_mecanico = validar_password_mecanico(clave)
        if _mecanico_id:
            _anotar_intento(True)
            return nombre_mecanico, "mecanico", None

    if not admin_passwords and not operador_passwords:
        c.execute("SELECT COUNT(*) FROM usuarios")
        _sin_usuarios = c.fetchone()[0] == 0
        # Con talleres cargados SÍ hay contra qué acertar en el ingreso: un fallo cuenta.
        if _sin_usuarios and con_mecanicos:
            c.execute("SELECT COUNT(*) FROM mecanicos WHERE activo = 1")
            _sin_usuarios = c.fetchone()[0] == 0
        if _sin_usuarios:
            # No es un intento fallido: no hay contra qué acertar. Contarlo acá dejaría a una
            # instalación recién hecha frenándose sola antes de poder configurar la primera clave.
            return None, None, (
                "No configuraste todavía ninguna contraseña en Streamlit Cloud (Settings → Secrets) "
                "ni creaste ningún usuario desde la app. Sin eso, nadie puede entrar a las secciones protegidas."
            )
    _anotar_intento(False)
    return None, None, None


def candado(motivo, disparador, clave, nivel="admin"):
    """Un botón protegido por contraseña, que NO se olvida de que lo apretaste.

    Lo que había antes no funcionaba, y esto no es teoría — está probado con la app corriendo:

        if st.button("Arreglar los 36 códigos"):
            if pedir_password_admin("..."):
                arreglar()

    Apretás el botón, aparece el pedido de contraseña, la ponés… y no pasa nada. El motivo es
    cómo funciona Streamlit: cada interacción vuelve a correr la página entera, y st.button()
    devuelve True SOLO en la corrida del clic. Cuando mandás la contraseña eso es otra corrida,
    el botón ya devuelve False, el `if` de afuera no entra y la acción nunca se ejecuta. La
    pantalla queda igual y parece que el botón está roto.

    Acá el pedido se ANOTA en la sesión: sobrevive a las corridas siguientes, así que cuando
    llega la contraseña la acción sí corre. Se borra apenas se autoriza, para que no vuelva a
    dispararse sola en el próximo refresco.

    `disparador` es el resultado del st.button(...), y `clave` lo distingue de los otros
    botones con candado de la misma pantalla."""
    pendiente = f"_candado_{clave}"
    if disparador:
        st.session_state[pendiente] = True
    if not st.session_state.get(pendiente):
        return False
    if modo_solo_lectura():
        st.session_state.pop(pendiente, None)
        st.error(TEXTO_DE_SOLO_LECTURA)
        return False
    autorizado = (pedir_password_operador_o_admin(motivo) if nivel == "empleado"
                  else pedir_password_admin(motivo))
    if autorizado:
        st.session_state.pop(pendiente, None)
        return True
    return False


def pedir_password_operador_o_admin(motivo=""):
    """Candado de EMPLEADO: alcanza con la contraseña de operador, o la de administrador.

    Distinto de pedir_password_admin(), que es para borrar y configurar. Este es para lo que
    hace un empleado de confianza todos los días y que igual no puede hacer cualquiera que
    entró con «Continuar»: tocar el precio y el stock. Pedir la de administrador para eso
    sería romper el mostrador; no pedir nada era dejar los precios abiertos a quien pase.

    Como el nivel queda guardado en la sesión, la contraseña se pide UNA vez por turno, no en
    cada producto."""
    if es_operador_o_admin():
        return True

    st.warning(f"🔒 Para esto hace falta entrar como empleado{(' — ' + motivo) if motivo else ''}.")
    with st.form(f"login_empleado_{motivo}"):
        clave = st.text_input("Contraseña (de operador o de administrador):", type="password")
        entrar = st.form_submit_button("Ingresar")

    if entrar:
        nombre, nivel, error = validar_password(clave)
        if error:
            st.error(error)
        elif nivel in ("admin", "operador"):
            st.session_state.nivel_usuario = nivel
            st.session_state.admin_nombre = nombre
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    return False


# Lo que se pega al final de los secretos queda ADENTRO de la última sección (así es TOML), y
# si esa sección es [admin_passwords] se leía como un usuario más: el nombre del repositorio
# entraba como contraseña de administrador, y la frase de cifrado de la copia también.
_NO_SON_USUARIOS = {"clave_copia"}


def es_un_usuario_de_los_secretos(nombre):
    nombre = str(nombre)
    return not nombre.startswith("github_") and nombre not in _NO_SON_USUARIOS


def hay_claves_configuradas():
    """¿Hay al menos una contraseña con la que entrar? (en los secretos o creada en la app).

    UNA VEZ QUE HUBO, SIEMPRE HAY. Sin contraseñas las secciones quedan abiertas (ver
    seccion_permitida()), y eso es para una instalación nueva, no para una que ya las tenía:
    si un día Streamlit no pudiera leer los secretos —se borraron por error, falló la
    plataforma—, la app creía que nunca se configuraron y abría todo, backups incluidos. Queda
    anotado la primera vez que se ven, y después no hay vuelta atrás sola: sin los secretos,
    las secciones piden una contraseña que no se puede poner, y hay que arreglar los secretos.
    (Lo señaló la revisión con Gemini.)"""
    try:
        secretos = secretos_app()
        hay = any(any(es_un_usuario_de_los_secretos(n) for n in dict(secretos.get(s, {})))
                  for s in ("admin_passwords", "operador_passwords"))
        hay = hay or bool(secretos.get("admin_password"))
        if not hay:
            c.execute("SELECT 1 FROM usuarios WHERE activo = 1 LIMIT 1")
            hay = c.fetchone() is not None
        if hay:
            if obtener_config("hubo_claves", "") != "1":
                guardar_config("hubo_claves", "1")
            return True
        return obtener_config("hubo_claves", "") == "1"
    except Exception as _err:
        anotar_error("hay_claves_configuradas", _err)
        return True      # ante la duda, que pida la contraseña


def es_empleado_o_abierto():
    """Para lo que un invitado no tiene por qué ver ni cambiar dentro de una sección abierta
    (los datos del cliente, cargar o corregir cosas). Sin ninguna contraseña configurada todo
    queda abierto, igual que en seccion_permitida()."""
    return es_operador_o_admin() or not hay_claves_configuradas()


# EL INVITADO MIRA, NO TOCA. El Buscador, la lista de WhatsApp y el Modo Mecánico quedan
# abiertos para mirar —es el mostrador, y «Por patente» lo puede consultar cualquiera—, pero
# anotar o cambiar algo pide entrar con contraseña. Recorriendo la app como invitado y tocando
# cada botón se encontró que, sin contraseña, se podía anotar «Se llevó» (pesa en las
# equivalencias sugeridas), «Reponer», marcar favoritos, apartar stock, anotar consultas de
# clientes con nombre y teléfono, enseñarle modelos y fabricantes al lector de VIN y prender
# las fotos en segundo plano. Ahora esos botones se ven apagados, con este aviso, y la función
# de cada uno lo vuelve a mirar adentro (ver exigir_nivel()). Lo que la app anota sola al
# buscar —el historial de búsquedas, las veces que se buscó cada código— sigue igual.
TEXTO_SOLO_MIRAR = ("🔒 Mirar se puede sin entrar. Para anotar o cambiar algo, entrá con tu "
                    "contraseña («🔑 Ingresar», arriba).")


def solo_mirar():
    """True para un invitado cuando la app tiene contraseñas: ve lo abierto y no cambia nada.
    Ver «EL INVITADO MIRA, NO TOCA»."""
    return not es_empleado_o_abierto()


def seccion_permitida(nivel, motivo=""):
    """El candado de una SECCIÓN entera: 'empleado' (operador o administrador) o 'admin'.

    La app está publicada en internet y se entra sin contraseña, como Invitado. Hasta acá solo
    pedían clave los botones que borran; todo lo demás quedaba abierto a cualquiera que tuviera
    el link. Probado entrando como invitado: se podía armar y DESCARGAR LA BASE ENTERA (61 MB,
    con precios, clientes, teléfonos y usuarios), aprobar o descartar equivalencias en bloque,
    ver los clientes de Vehículos y crear vínculos a mano.

    Si todavía no hay ninguna contraseña configurada no se cierra nada —dejaría afuera al propio
    dueño—: se avisa, bien visible, que la sección está abierta."""
    if not hay_claves_configuradas():
        # En palabras del negocio: «Secrets» y «[admin_passwords]» no le dicen nada al dueño
        # (lo señaló la revisión con Gemini). El camino técnico queda en Usuarios.
        st.warning("🔓 **La app todavía no tiene contraseña**: cualquiera con el link entra acá. "
                   "Creá una en **Administrar → 👥 Usuarios**.")
        return True
    if nivel == "admin":
        return pedir_password_admin(motivo)
    return pedir_password_operador_o_admin(motivo)


def pedir_password_admin(motivo=""):
    """Muestra un formulario de contraseña de ADMINISTRADOR COMPLETO. Devuelve True si ya está
    autenticado como admin — para borrados y configuración sensible, un 'operador' no alcanza."""
    if es_admin():
        return True

    st.warning(f"🔒 Esta sección está protegida{(' — ' + motivo) if motivo else ''}.")
    with st.form(f"login_admin_{motivo}"):
        clave = st.text_input("Contraseña de administrador:", type="password")
        entrar = st.form_submit_button("Ingresar")

    if entrar:
        nombre, nivel, error = validar_password(clave)
        if error:
            st.error(error)
        elif nivel == "admin":
            st.session_state.nivel_usuario = "admin"
            st.session_state.admin_nombre = nombre
            st.rerun()
        elif nivel == "operador":
            st.error("Esa es una contraseña de operador — para esto hace falta la de administrador completo.")
        else:
            st.error("Contraseña incorrecta.")
    return False


def mostrar_login_inicial():
    """El nombre y la contraseña, adentro de «🔑 Ingresar». Sin contraseña se sigue igual,
    como Invitado o con el nombre que se ponga. Las acciones destructivas van a seguir pidiendo la
    contraseña de administrador completo aparte, esto es solo la pantalla de entrada."""
    # Va adentro de «🔑 Ingresar», arriba de todo (ver app.py): ya no es una pantalla que hay
    # que pasar para llegar al buscador.
    st.caption(
        "Tu nombre separa tus búsquedas recientes de las de tus compañeros. Es opcional: "
        "sin nombre figurás como «Invitado»."
    )
    with st.form("login_inicial"):
        nombre_usuario = st.text_input("Tu nombre:", placeholder="Ej: Matías", key="login_inicial_nombre")
        st.markdown("---")
        st.caption(
            "Si tenés contraseña (de administrador completo o de operador), ingresala acá. "
            "Un operador puede usar las funciones de IA y cargar cosas, pero no borrar ni configurar."
        )
        clave = st.text_input("Contraseña (opcional):", type="password", key="login_inicial_clave")
        col_a, col_b = st.columns(2)
        entrar = col_a.form_submit_button("🔓 Ingresar con contraseña", type="primary", width="stretch")
        seguir = col_b.form_submit_button("👤 Continuar sin contraseña", width="stretch")

    if entrar:
        nombre, nivel, error = validar_password(clave, con_mecanicos=True)
        if nivel == "mecanico":
            # El nombre del taller es único (ver la tabla mecanicos).
            c.execute("SELECT id FROM mecanicos WHERE nombre = ? AND activo = 1", (nombre,))
            st.session_state.nivel_usuario = "mecanico"
            st.session_state.admin_nombre = nombre
            st.session_state.mecanico_id = c.fetchone()["id"]
            st.rerun()
        elif nivel:
            st.session_state.nivel_usuario = nivel
            st.session_state.admin_nombre = nombre
            # Al entrar, a lo primero de la barra (🧾 Ventas: ver ORDEN_DE_LAS_PAGINAS), salvo que
            # ya estuviera buscando algo: eso no se le saca de abajo.
            if not str(st.session_state.get("busqueda_input") or "").strip():
                st.session_state["_al_principio_de_la_barra"] = True
            st.rerun()
        elif error:
            st.error(error)
        else:
            st.error("Contraseña incorrecta.")
    if seguir:
        st.session_state.usuario_nombre = nombre_usuario.strip() or "Invitado"
        st.rerun()

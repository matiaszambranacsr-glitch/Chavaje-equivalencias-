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
import types
from datetime import datetime, timedelta
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


# Del proceso y no de la pasada (ver del_proceso): si no, la pantalla que los muestra veía solo
# los errores de su propia pasada, y los de los hilos de fondo no los veía nunca nadie.
_ULTIMOS_ERRORES = del_proceso("ultimos_errores", list)
MAXIMO_ERRORES_ANOTADOS = 150


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
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {
  --bg: #14171B;
  --bg-panel: #1D2126;
  --bg-panel-2: #242830;
  --border: #2D3239;
  --text: #ECEEF0;
  --text-muted: #9BA3AC;
  --accent: #E8A33D;
  --accent-hover: #F2B658;
  --accent-2: #4C8BF5;
}

html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif; }

[data-testid="stAppViewContainer"] {
  background: radial-gradient(circle at 15% 0%, #1A1E24 0%, var(--bg) 45%) fixed;
  color: var(--text);
}
[data-testid="stHeader"] { background: transparent; }

/* Encabezado tipo ficha/etiqueta de repuesto */
.app-header {
  display: flex; flex-direction: column; gap: 2px;
  padding: 18px 22px; margin-bottom: 10px;
  background: linear-gradient(135deg, var(--bg-panel) 0%, var(--bg-panel-2) 100%);
  border: 1px solid var(--border); border-left: 3px solid var(--accent);
  border-radius: 10px;
}
.app-header__eyebrow {
  font-family: 'IBM Plex Mono', monospace; font-size: 0.68rem;
  letter-spacing: 0.14em; color: var(--accent); text-transform: uppercase; margin: 0 0 4px 0;
}
.app-header h1 {
  font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 1.9rem;
  margin: 0; color: var(--text); letter-spacing: -0.01em;
}
.app-header p { margin: 4px 0 0 0; color: var(--text-muted); font-size: 0.92rem; }

/* Pestañas (nivel principal) */
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--border); }
.stTabs [data-baseweb="tab"] {
  font-family: 'Space Grotesk', sans-serif; font-weight: 600; font-size: 0.86rem;
  color: var(--text-muted); background: transparent; border-radius: 8px 8px 0 0; padding: 10px 14px;
}
.stTabs [aria-selected="true"] { color: var(--accent) !important; border-bottom: 2px solid var(--accent) !important; }

/* Sub-pestañas anidadas (ej: dentro de Administrar o Modo Mecánico) — más chicas y sutiles,
   para que se note la jerarquía: esto es una subdivisión de la pestaña principal, no otra más. */
.stTabs .stTabs [data-baseweb="tab-list"] {
  border-bottom: 1px solid var(--border); gap: 2px; margin-top: 4px; margin-bottom: 8px;
}
.stTabs .stTabs [data-baseweb="tab"] {
  font-size: 0.78rem; padding: 7px 11px; color: var(--text-muted); opacity: 0.85;
}
.stTabs .stTabs [aria-selected="true"] { opacity: 1; }

/* Botones */
.stButton > button, .stDownloadButton > button, .stLinkButton > a, .stFormSubmitButton > button {
  border-radius: 8px; border: 1px solid var(--border); font-family: 'Inter', sans-serif;
  font-weight: 600; transition: all 0.15s ease;
}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
  background: var(--accent); color: #1A1300; border: none;
}
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover { background: var(--accent-hover); }
.stButton > button:hover { border-color: var(--accent); color: var(--accent); }
.stButton > button:disabled { opacity: 0.4; }

/* Radios usados como selector de modo (ej: Código/Descripción, Foto real/IA) —
   look de pastillas en vez del radio suelto por defecto, para que se sienta como
   un selector de vista, no como un formulario más. */
.stRadio [role="radiogroup"] { gap: 6px; flex-wrap: wrap; }
/* [role="radiogroup"] y no «.stRadio label» a secas: así agarraba también el TÍTULO del grupo
   —«Buscar por:», «Qué tan lejos buscar:»— y lo dibujaba como una opción más, con su pastilla.
   Se vio en capturas de la app en un celular. */
.stRadio [role="radiogroup"] label {
  background: var(--bg-panel); border: 1px solid var(--border); border-radius: 999px;
  padding: 5px 14px 5px 10px !important; transition: all 0.15s ease;
}
.stRadio [role="radiogroup"] label:has(input:checked) { border-color: var(--accent); background: rgba(232, 163, 61, 0.12); }

/* Inputs */
.stTextInput input, .stNumberInput input, .stTextArea textarea,
.stSelectbox div[data-baseweb="select"] > div {
  background: var(--bg-panel) !important; border: 1px solid var(--border) !important;
  border-radius: 7px !important; color: var(--text) !important;
}
.stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus {
  border-color: var(--accent) !important; box-shadow: 0 0 0 1px var(--accent) !important;
}
.stCheckbox input:checked, .stCheckbox [data-baseweb="checkbox"] svg { accent-color: var(--accent); }

/* Subida de archivos */
[data-testid="stFileUploaderDropzone"] {
  background: var(--bg-panel) !important; border: 1px dashed var(--border) !important; border-radius: 8px !important;
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

/* Expanders */
[data-testid="stExpander"] { border: 1px solid var(--border) !important; border-radius: 8px !important; margin-bottom: 4px; }
.streamlit-expanderHeader, [data-testid="stExpander"] summary {
  background: var(--bg-panel) !important; border-radius: 8px !important; font-weight: 600;
}

/* Métricas */
[data-testid="stMetric"] {
  background: var(--bg-panel); border: 1px solid var(--border); border-radius: 10px; padding: 10px 14px;
}
[data-testid="stMetricValue"] { font-family: 'IBM Plex Mono', monospace; color: var(--accent); }

/* Alertas y tablas */
[data-testid="stAlert"] { border-radius: 8px; border: 1px solid var(--border); }
[data-testid="stDataFrame"] { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }

code { font-family: 'IBM Plex Mono', monospace; color: var(--accent-2); }
hr { border-color: var(--border) !important; margin: 1.1rem 0 !important; }

/* Los gráficos (st.bar_chart / Vega-Lite) muestran un tooltip flotante al tocar una barra.
   En celular no hay evento que lo "suelte" al hacer scroll con el dedo, y queda pegado en
   pantalla tapando el contenido de abajo. Se desactiva: el dato ya se ve en las barras. */
#vg-tooltip-element, .vg-tooltip { display: none !important; }
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
SEMILLA_DTC_VERSION = "3"
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
VERSION_CONFIANZA = "4"

# La versión del LECTOR DE MEDIDAS. Mismo mecanismo: las medidas se deducen de la descripción
# una vez y quedan guardadas, así que cuando el lector aprende a leer algo nuevo —el espesor de
# la junta, las vías de la ficha— lo que ya está cargado no se entera.
# Sobre la base real eran 1.402 productos con la medida escrita en el texto y 0 cargadas,
# porque llenarlas era un botón de Mantenimiento que había que saber apretar.
# Subir el número al agregar una medida nueva a medidas_desde_descripcion().
VERSION_MEDIDAS = "4"

# La versión del LECTOR DE APLICACIONES: a qué auto le va cada pieza, deducido de la
# descripción. Es el dato gratis más grande que tiene esta base —114.673 filas que salen de
# texto ya cargado, contra 0 que había— y el que hace andar la búsqueda por vehículo.
# Como las otras dos, corría solo después de importar una lista, así que en una base donde no
# se importó nada desde que la función existe nunca corrió.
# Subir el número al cambiar cómo se leen los modelos.
VERSION_APLICACIONES = "7"

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


def crear_usuario(nombre, password, rol="operador"):
    h, salt = hash_password(password)
    with db_lock:
        c.execute("INSERT INTO usuarios (nombre, password_hash, salt, rol) VALUES (?, ?, ?, ?)",
                   (nombre.strip(), h, salt, rol))
        conn.commit()


def listar_usuarios():
    c.execute("""SELECT id AS "ID", nombre AS "Nombre", rol AS "Rol",
                 CASE WHEN activo=1 THEN 'Sí' ELSE 'No' END AS "Activo", creado_en AS "Creado"
                 FROM usuarios ORDER BY nombre""")
    return filas_a_listas(c)


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
    h, salt = hash_password(nueva_password)
    with db_lock:
        c.execute("UPDATE usuarios SET password_hash=?, salt=? WHERE id=?", (h, salt, usuario_id))
        conn.commit()


def activar_desactivar_usuario(usuario_id, activo):
    with db_lock:
        c.execute("UPDATE usuarios SET activo=? WHERE id=?", (1 if activo else 0, usuario_id))
        conn.commit()


def eliminar_usuario(usuario_id):
    with db_lock:
        c.execute("DELETE FROM usuarios WHERE id=?", (usuario_id,))
        conn.commit()


def crear_mecanico(nombre, password):
    h, salt = hash_password(password)
    with db_lock:
        c.execute("INSERT INTO mecanicos (nombre, password_hash, salt) VALUES (?, ?, ?)",
                   (nombre.strip(), h, salt))
        conn.commit()


def listar_mecanicos():
    c.execute("""SELECT id AS "ID", nombre AS "Nombre",
                 CASE WHEN activo=1 THEN 'Sí' ELSE 'No' END AS "Activo", creado_en AS "Creado"
                 FROM mecanicos ORDER BY nombre""")
    return filas_a_listas(c)


def validar_password_mecanico(password):
    c.execute("SELECT id, nombre, password_hash, salt FROM mecanicos WHERE activo = 1")
    for fila in c.fetchall():
        h, _ = hash_password(password, fila["salt"])
        if h == fila["password_hash"]:
            return fila["id"], fila["nombre"]
    return None, None


def activar_desactivar_mecanico(mecanico_id, activo):
    with db_lock:
        c.execute("UPDATE mecanicos SET activo=? WHERE id=?", (1 if activo else 0, mecanico_id))
        conn.commit()


def eliminar_mecanico(mecanico_id):
    with db_lock:
        c.execute("DELETE FROM mecanicos WHERE id=?", (mecanico_id,))
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


def validar_password(clave):
    """Chequea la contraseña contra los secrets de admin/operador Y contra las cuentas creadas
    desde la propia app (tabla usuarios). Devuelve (nombre, nivel, error) — nivel es 'admin',
    'operador', o None si no matcheó ninguna. Los mecánicos externos se validan aparte, con
    validar_password_mecanico(), porque tienen su propio portal separado."""
    secretos = secretos_app()
    # [admin_passwords] / [operador_passwords] en Streamlit Secrets, cada una con nombre:clave.
    # También soporta la forma anterior de una sola clave (admin_password) por compatibilidad.
    admin_passwords = dict(secretos.get("admin_passwords", {}))
    clave_unica = secretos.get("admin_password")
    if clave_unica:
        admin_passwords.setdefault("admin", clave_unica)
    operador_passwords = dict(secretos.get("operador_passwords", {}))

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

    if not admin_passwords and not operador_passwords:
        c.execute("SELECT COUNT(*) FROM usuarios")
        if c.fetchone()[0] == 0:
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
    """Pide la contraseña apenas se abre la app, con opción de seguir sin loguearse para
    quien solo quiera buscar/consultar. Las acciones destructivas van a seguir pidiendo la
    contraseña de administrador completo aparte, esto es solo la pantalla de entrada."""
    st.markdown("### 👋 ¿Quién sos?")
    st.caption(
        "Poné tu nombre para que tus búsquedas recientes queden separadas de las de tus "
        "compañeros — el resto de la información (catálogo, esquemas, etc.) la ven todos igual. "
        "Es opcional, si lo dejás vacío vas a figurar como 'Invitado'."
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
        seguir = col_b.form_submit_button("➡️ Continuar", width="stretch")

    if entrar:
        nombre, nivel, error = validar_password(clave)
        if nivel:
            st.session_state.nivel_usuario = nivel
            st.session_state.admin_nombre = nombre
            st.session_state.saltar_login = True
            st.rerun()
        else:
            mecanico_id, nombre_mecanico = validar_password_mecanico(clave)
            if mecanico_id:
                st.session_state.nivel_usuario = "mecanico"
                st.session_state.admin_nombre = nombre_mecanico
                st.session_state.mecanico_id = mecanico_id
                st.session_state.saltar_login = True
                st.rerun()
            elif error:
                st.error(error)
            else:
                st.error("Contraseña incorrecta.")
    if seguir:
        st.session_state.usuario_nombre = nombre_usuario.strip() or "Invitado"
        st.session_state.saltar_login = True
        st.rerun()

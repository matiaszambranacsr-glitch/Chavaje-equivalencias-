"""Chavaje — buscador de equivalencias de repuestos.

CÓMO ESTÁ ORGANIZADO

Este archivo es el que corre Streamlit en cada toque: la configuración de la página, el
encabezado, la entrada y la navegación. Lo demás está en dos carpetas (ver orden.py):

    logica/      todo lo que no es una pantalla. Se carga UNA vez por proceso.
    pantallas/   una pantalla por archivo; corren en cada toque, al final de este.

Cada archivo está dividido en secciones con un encabezado de tres líneas como este:

    # ====================================================
    # NOMBRE DE LA SECCIÓN
    # ====================================================

Buscando «# ===» se salta de una a la otra. El orden va de lo más básico a lo más
específico, y las pantallas quedan todas al final:

    logica/base.py
        · CONFIGURACIÓN DE PÁGINA
        · MODO DE VISTA (celular / computadora)
    logica/datos.py
        · CONEXIÓN Y ESQUEMA
        · TODO O NADA: operaciones que son de varias sentencias
    logica/codigos.py
        · CÓDIGOS: limpiar, reconocer, partir y sacarlos de una descripción
        · MARCAS Y CATÁLOGOS EXTERNOS DE PROVEEDOR
    logica/copias_y_mantenimiento.py
        · INTEGRIDAD DE LA BASE, BACKUP Y RESTAURACIÓN
        · MANTENIMIENTO QUE CORRE SOLO AL ABRIR
    logica/mostrador.py
        · BÚSQUEDA POR NÚMERO DE MOTOR Y POR PATENTE
        · CONSULTAS DE CLIENTES (lo que pidieron y no había)
        · STOCK Y RESERVAS
        · PRECIOS Y MÁRGENES
        · FUSIONAR MARCAS Y PRODUCTOS DUPLICADOS
    logica/equivalencias_descubiertas.py
        · EQUIVALENCIAS DESCUBIERTAS DESDE LAS VENTAS
    logica/importar.py
        · IMPORTAR UNA LISTA: leer el archivo y adivinar qué es cada columna
        · AVISOS DE BACKUP Y HUELLA DEL ARCHIVO IMPORTADO
    logica/busqueda.py
        · BÚSQUEDA DE EQUIVALENCIAS (el corazón de la app)
        · DESHACER UNA IMPORTACIÓN
        · CONFIANZA DE CADA VÍNCULO
        · CÓDIGOS PUENTE: aprobar los buenos, encontrar los falsos
    logica/salud.py
        · DIAGNÓSTICO DE SALUD DEL CATÁLOGO
        · POR QUÉ DOS CÓDIGOS NO SE RELACIONAN
    logica/proveedores.py
        · CATÁLOGO WEB DEL PROVEEDOR (fotos y equivalencias)
        · LAS TANDAS QUE CORREN SOLAS, EN SEGUNDO PLANO
    logica/calidad.py
        · PESO DE LAS FOTOS Y BACKUP LIVIANO
        · MAPEO DE COLUMNAS RECORDADO POR PROVEEDOR
        · CONTROLES DE CALIDAD DE UN CÓDIGO
        · BÚSQUEDA POR PARECIDO Y ERRORES DE TIPEO
    logica/descripciones.py
        · AÑOS, MODELOS Y FAMILIAS DE REPUESTO
        · CATÁLOGOS DE APLICACIONES (qué repuesto le va a cada auto)
    logica/negocio.py
        · COMBOS DE REPUESTOS RELACIONADOS (ej: correa de distribución -> kit + tensor + bomba de agua)
        · INTELIGENCIA ARTIFICIAL: fotos, audio y remitos
        · BUSCAR POR PIEZA Y AUTO
        · DISCONTINUADOS Y REEMPLAZOS DE FÁBRICA
        · REPOSICIÓN Y FAVORITOS
        · CONFIGURACIÓN, USUARIO Y USO DE IA
        · PAPELERA (borrar con red)
        · HISTORIAL, DUPLICADOS Y EXPORTAR A EXCEL
        · COBROS: alias de transferencia y QR
    logica/interfaz.py
        · PIEZAS DE INTERFAZ QUE SE REPITEN
        · PDF: cotización y ficha del vehículo
        · LEER EL ARCHIVO: encabezado, hojas y codificación
    logica/vehiculos.py
        · FICHA DIGITAL DEL VEHÍCULO (patente + historial de piezas)
        · LA PATENTE ARGENTINA: QUÉ SE PUEDE LEER DE ELLA SIN CONSULTAR NADA
    logica/piezas.py
        · SUSTITUCIÓN POR MEDIDAS MECÁNICAS (retenes, o'rings, bujes)
        · COMPARACIÓN VISUAL DE PIEZAS
        · GUARDADO DE FOTOS (varias por producto)
        · AUDITORÍA DIARIA DE STOCK POR MUESTREO
        · UBICACIÓN EN DEPÓSITO (matriz ABC)
    logica/mecanico.py
        · MODO MECÁNICO — DICCIONARIO DE CÓDIGOS OBD2 / DTC
        · MODO MECÁNICO — LECTOR DE VIN
        · MODO MECÁNICO — VISOR DE ESQUEMAS
    app.py
        · ENCABEZADO
        · NAVEGACIÓN PRINCIPAL
    pantallas/buscador.py
        · BUSCADOR
    pantallas/vincular.py
        · VINCULAR MANUAL
    pantallas/cargar_excel.py
        · CARGAR EXCEL
    pantallas/administrar.py
        · ADMINISTRAR
    pantallas/estadisticas.py
        · ESTADÍSTICAS
    pantallas/whatsapp.py
        · LISTA PARA WHATSAPP
    pantallas/vehiculos.py
        · VEHÍCULOS (ficha digital / historial de piezas)
    pantallas/mecanico.py
        · MODO MECÁNICO

La lógica que no depende de Streamlit está ADEMÁS en el paquete nucleo/, que se puede usar
desde otro sistema. Se genera desde logica/ con `python3 nucleo/generar.py`, así que si
tocás algo de códigos, planillas o equivalencias, conviene regenerarlo y correr
`python3 -m nucleo.pruebas`.

Antes de subir un cambio: `python3 auditar.py` tiene que dar ERROR 0. Revisa la app entera,
las tres partes juntas, en el orden en que corren.
"""
import time

import streamlit as st

# Antes que nada: Streamlit pide que la configuración de la página sea lo primero que se dibuja,
# y cargar la lógica (abajo) ya abre la base.
st.set_page_config(page_title="Equivalencias El Chavo", page_icon="🔧", layout="wide")

# La lógica se carga una vez por proceso, no en cada toque (ver logica/__init__.py). Sus nombres
# se traen acá para que este archivo y las pantallas los usen como siempre, sin prefijo.
import importlib
import sys

import logica
import pantallas

# Si cambió algún archivo de la lógica desde que se cargó (se subió código nuevo), se vuelve a
# cargar entera: orden.py incluido, por si cambió la lista de partes. Ver
# logica.cambio_algun_archivo(). Las pantallas no lo necesitan: se recompilan solas al cambiar.
# Si la lógica cargada ni siquiera tiene esa función, es de antes de que existiera: también está
# vieja. Pasó probándolo: app.py nuevo contra una lógica cargada antes del cambio.
_cambio = getattr(logica, "cambio_algun_archivo", None)
if _cambio is None or _cambio():
    for _nombre in [n for n in sys.modules if n in ("orden", "logica", "pantallas")
                    or n.startswith("logica.")]:
        del sys.modules[_nombre]
    importlib.import_module("logica")
    importlib.import_module("pantallas")
logica, pantallas = sys.modules["logica"], sys.modules["pantallas"]

globals().update(logica.todo_lo_de_la_logica())

# Hay alguien esperando esta pantalla: la tarea de fondo le cede el paso hasta que termine de
# dibujarse (la marca de «terminó» está en la última línea del archivo). Ver ceder_al_mostrador().
_actividad_del_mostrador()["empezo"] = time.monotonic()

st.markdown(CSS_CUSTOM, unsafe_allow_html=True)

# Ajustes según el modo de vista elegido. En celular se agranda lo que hay que tocar con el
# dedo y se achica el texto de las tablas para que entre; en computadora se aprovecha el ancho.
if es_celular():
    st.markdown("""
    <style>
    .block-container { padding: 0.8rem 0.7rem 3rem 0.7rem !important; max-width: 100% !important; }
    /* Botones a lo ancho: más fáciles de acertar con el pulgar, y todos del mismo largo en vez
       de uno por renglón cada uno de su tamaño. La regla era «.stButton > button», pero en esta
       versión de Streamlit el botón está uno o dos niveles más adentro (más todavía si tiene
       ayuda, que lo envuelve en el globito) y la caja de afuera se achica al texto: medido en el
       celular, «🔍 Buscar Equivalencias» ocupaba 169 px de 336. Nunca se había aplicado. */
    [data-testid="stElementContainer"]:has(.stButton, .stDownloadButton, .stFormSubmitButton, .stLinkButton),
    [data-testid="stElementContainer"]:has(.stButton, .stDownloadButton, .stFormSubmitButton, .stLinkButton) > div,
    .stButton, .stDownloadButton, .stFormSubmitButton, .stLinkButton,
    .stButton div, .stDownloadButton div, .stFormSubmitButton div, .stLinkButton div {
      width: 100% !important;
    }
    .stButton button, .stDownloadButton button, .stLinkButton a, .stFormSubmitButton button {
      min-height: 2.7rem; width: 100% !important;
    }
    /* Las métricas de a dos por renglón. Streamlit apila las columnas en pantallas angostas y
       cada número quedaba solo, a lo ancho: en «Equivalencias sugeridas» los seis ocupaban una
       pantalla entera antes de llegar a lo que hay que revisar. */
    [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] > [data-testid="stMetric"]) {
      min-width: calc(50% - 0.5rem) !important; flex: 1 1 calc(50% - 0.5rem) !important;
    }
    [data-testid="stMetricValue"] { font-size: 1.7rem !important; }
    [data-testid="stDataFrame"] { font-size: 0.78rem; }
    .app-header h1 { font-size: 1.45rem !important; }
    /* En el celular el encabezado va con el nombre solo: la línea de arriba y el subtítulo
       ocupaban lo mismo que el nombre y empujaban la caja de búsqueda hacia abajo. */
    .app-header { padding: 10px 14px !important; margin-bottom: 6px !important; }
    .app-header__eyebrow, .app-header p { display: none !important; }
    [data-testid="stExpander"] summary { padding: 0.65rem 0.5rem !important; }
    h3 { font-size: 1.1rem !important; }
    /* Navegación en pastillas: compactas para que las 8 secciones entren en pocas filas
       sin comerse la pantalla, y con buen tamaño para tocar con el dedo. */
    .stRadio [role="radiogroup"] { gap: 4px; }
    .stRadio [role="radiogroup"] label { padding: 4px 10px 4px 6px !important; font-size: 0.82rem; }
    .stRadio [role="radiogroup"] label p { font-size: 0.82rem !important; }
    </style>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <style>
    .block-container { padding: 1.6rem 3rem 4rem 3rem !important; max-width: 1500px !important; }
    [data-testid="stDataFrame"] { font-size: 0.88rem; }
    </style>
    """, unsafe_allow_html=True)


# ============================================================
# ENCABEZADO
# ============================================================
st.markdown(
    """
    <div class="app-header">
        <p class="app-header__eyebrow">Base de equivalencias de repuestos</p>
        <h1>🔧 Equivalencias El Chavo</h1>
        <p>Sistema de búsqueda de repuestos por equivalencia</p>
    </div>
    """,
    unsafe_allow_html=True
)

# Pantalla de login apenas se abre la app, con opción de seguir sin loguearse.
if not es_admin() and not st.session_state.get("saltar_login"):
    mostrar_login_inicial()
    st.stop()

if es_admin() or es_operador_o_admin() or st.session_state.get("nivel_usuario") == "mecanico":
    col_estado, col_modo, col_salir = st.columns([3, 1.4, 1])
    nombre_sesion = st.session_state.get("admin_nombre", "")
    etiquetas_nivel = {"admin": "administrador", "operador": "operador", "mecanico": "mecánico"}
    etiqueta_nivel = etiquetas_nivel.get(st.session_state.get("nivel_usuario"), "administrador")
    col_estado.caption(f"🔓 Sesión de {etiqueta_nivel} activa ({nombre_sesion}).")
    col_modo.selectbox("Vista:", VISTAS, index=VISTAS.index(vista_detectada()), key="modo_vista",
                        label_visibility="collapsed",
                        help="Se elige sola según desde dónde entres. Cambiala si no acertó.")
    if col_salir.button("Salir"):
        st.session_state.nivel_usuario = None
        st.session_state.admin_nombre = None
        st.session_state.mecanico_id = None
        st.rerun()
else:
    col_estado, col_modo = st.columns([3, 1.4])
    col_estado.caption(f"👤 Usando como: {obtener_usuario_actual()}")
    col_modo.selectbox("Vista:", VISTAS, index=VISTAS.index(vista_detectada()), key="modo_vista",
                        label_visibility="collapsed",
                        help="Se elige sola según desde dónde entres. Cambiala si no acertó.")

if st.session_state.get("nivel_usuario") == "mecanico":
    mostrar_portal_mecanico()
    st.stop()

if "lista_whatsapp" not in st.session_state:
    st.session_state.lista_whatsapp = []  # lista de códigos agregados para el mensaje

# ============================================================
# NAVEGACIÓN PRINCIPAL
# ============================================================
# Antes esto era st.tabs(). Se cambió por un selector guardado en la sesión por dos motivos:
#  1) st.tabs pierde en qué pestaña estabas cada vez que la página se refresca, y te devolvía
#     al Buscador (el problema de "me vuelve al inicio" al tocar un botón).
#  2) st.tabs dibuja TODAS las pestañas en cada refresco, aunque no las estés mirando —
#     con 8 pestañas haciendo consultas a la base, eso era trabajo al pedo. Ahora solo se
#     arma la sección que estás viendo, así que la app responde bastante más rápido.
# Aviso fuerte si la base quedó vacía: Streamlit Cloud borra el disco al redesplegar, y sin
# este cartel uno se entera recién cuando busca un código y no aparece nada.
c.execute("SELECT COUNT(*) FROM productos")
_total_productos = c.fetchone()[0]
if _total_productos == 0:
    st.error(
        "⚠️ **La base está vacía.** Esto pasa porque el servidor borra el disco de la app cuando "
        "se redespliega o se reinicia. Si tenés un backup (.db) descargado, restauralo desde "
        "**Estadísticas → 💾 Backup y config**. Para que no vuelva a pasar, mirá ahí abajo la "
        "sección de copia permanente."
    )
elif st.session_state.get("_restaurado_de_semilla"):
    st.info(
        f"♻️ La base se restauró sola desde la copia guardada en el repositorio "
        f"({_total_productos} productos). Lo cargado después de esa copia no está — "
        "acordate de actualizarla cada tanto."
    )

# Chequeo de salud, en cualquier sección. Va arriba a propósito: los controles de mantenimiento
# se fueron sumando de a uno y quedaron repartidos en siete pantallas distintas, ninguna avisa
# sola, y en la práctica nadie entra a mirarlas hasta que algo ya salió mal.
#
# El resultado se guarda en la sesión y se recalcula cada 3 minutos. Correrlo en CADA clic serían
# 75 ms de más en cada cosa que se toca, y estos números no cambian de un segundo al otro.
# Mantenimiento del día. Va acá porque es el único lugar por el que pasan todos, sin importar
# a qué sección entren. Se protege con try porque una tarea de fondo que falla NUNCA puede
# impedir que la app abra.
if not st.session_state.get("_tareas_dia_corridas"):
    st.session_state["_tareas_dia_corridas"] = True
    try:
        _hecho_hoy = tareas_automaticas_del_dia()
        if _hecho_hoy:
            st.session_state["_aviso_tareas"] = _hecho_hoy
    except Exception as _err:
        anotar_error("nivel principal", _err)
        pass

# Las bajadas del catálogo del proveedor, en un hilo aparte. Va afuera del «una vez por día»:
# mientras la app esté abierta puede seguir avanzando, que es lo único que hace que un catálogo
# grande termine alguna vez. Casi siempre esta llamada no hace nada —ya hay una corriendo, o
# está apagado, o se gastó el cupo del día— y vuelve enseguida.
try:
    arrancar_tanda_de_fondo()
except Exception as _err:
    anotar_error("nivel principal", _err)

# La copia a GitHub cuando hay cambios, en su propio hilo. Ver vigilar_la_copia().
try:
    vigilar_la_copia()
except Exception as _err:
    anotar_error("nivel principal", _err)

_hecho_hoy = st.session_state.pop("_aviso_tareas", None)
if _hecho_hoy:
    st.caption("🔧 Mantenimiento automático de hoy: " + " · ".join(_hecho_hoy))

# El resultado del descubrimiento que corrió por atrás. Se muestra una sola vez por resultado:
# sin eso, el mismo cartel quedaría en todas las pantallas hasta la próxima importación.
try:
    _desc_txt = obtener_config("descubrimiento_ultimo", "")
    _desc_fec = obtener_config("descubrimiento_fecha", "")
    if _desc_txt and st.session_state.get("_desc_visto") != _desc_fec:
        st.session_state["_desc_visto"] = _desc_fec
        st.caption(f"🧠 Búsqueda automática de relaciones ({_desc_fec}): {_desc_txt}")
    elif obtener_config("descubrimiento_pendiente", "") == "1":
        st.caption("🧠 Buscando relaciones nuevas en todo el catálogo, por atrás…")
except Exception as _err:
    anotar_error("nivel principal", _err)

_cache_salud = salud_compartida()

def ir_a_donde_dice_el_aviso(donde):
    """Lleva a la pantalla que el aviso nombra en su «📍». Va como on_click.

    Hasta ahora los avisos terminaban en una miga de pan escrita —«📍 Administrar →
    Mantenimiento → 🧹 Limpiar y corregir → Códigos puente»— y ahí quedaba: había que
    acordarse del camino y hacerlo a mano. De los 28 textos de la app que mandan a otra
    pantalla, UNO SOLO tenía botón.

    Se navega leyendo la miga en vez de escribir un destino por aviso, y eso tiene una ventaja
    que no es de código: si la miga miente, el botón no llega, y se nota. Ya pasó al escribir
    esto — había 11 lugares que decían «Estadísticas → Mantenimiento» y Mantenimiento vive en
    Administrar. Nadie lo había visto porque una miga de pan escrita no se prueba sola.

    Como callback y no suelto, por lo mismo que _ir_al_grupo_de_mantenimiento(): Streamlit no
    deja tocar la clave de un widget que ya se dibujó en esta pasada."""
    tramos = [t.strip() for t in str(donde or "").split("→")]
    if not tramos:
        return

    # Mantenimiento primero, y sin mirar el primer tramo: vive adentro de Administrar aunque
    # la miga diga otra cosa.
    if any("Mantenimiento" in t for t in tramos):
        st.session_state["pagina_actual"] = "🗂️ Administrar"
        st.session_state["sub_admin"] = "🧹 Mantenimiento"
        for tramo in tramos:
            for grupo in GRUPOS_MANTENIMIENTO:
                if tramo == grupo:
                    st.session_state["sub_mantenimiento"] = grupo
                    return
        return

    for pantalla in PAGINAS:
        # Se compara sin el emoji: la miga escribe «Estadísticas», no «📊 Estadísticas».
        if pantalla.split(" ", 1)[-1].lower() in tramos[0].lower():
            st.session_state["pagina_actual"] = pantalla
            break
    for tramo in tramos[1:]:
        for solapa in SUB_STATS:
            # Sin el emoji: varias migas escriben «Backup y config» y la solapa se llama
            # «💾 Backup y config». Exigir el emoji dejaba el botón a mitad de camino.
            if tramo == solapa or tramo == solapa.split(" ", 1)[-1]:
                st.session_state["sub_stats"] = solapa
                return


_problemas = _cache_salud["problemas"]
if _problemas:
    # Se separa por urgencia en vez de mostrar una lista pareja. Antes todo se veía igual y
    # «hay clientes esperando algo que ya tenés» quedaba mezclado con «hay descripciones
    # pegadas». Lo que da plata va arriba y sin plegar; el resto, plegado.
    _graves = [p for p in _problemas if p["nivel"] == "alto"]
    _resto = [p for p in _problemas if p["nivel"] != "alto"]

    # PLEGADO en el celular, y en la computadora para quien no es administrador. Abierto, cada
    # aviso trae su texto y su botón: con los seis de la base real la caja de búsqueda quedaba
    # TRES pantallas más abajo en el celular, y casi DOS en una computadora de 1366x768 —se vio
    # sacando capturas de las dos—. Quien atiende el mostrador entra a buscar un código, y estos
    # avisos son tareas de administración: «Ir a arreglarlo» igual le pide la clave. Siguen
    # arriba de todo, en rojo, con el número, y se abren con un toque. Abiertos quedan solo para
    # el administrador en la computadora, que es quien los arregla.
    _plegar_avisos = es_celular() or not es_admin()

    if _graves:
        if _plegar_avisos:
            _caja_graves = st.expander(
                f"🔴 {len(_graves)} cosa(s) que conviene mirar hoy"
                + (f" · 🟡 {len(_resto)} sin apuro" if _resto else ""), expanded=False)
        else:
            st.markdown(
                "<div style='background:rgba(255,75,75,.08);border-left:4px solid #ff4b4b;"
                "border-radius:6px;padding:.7rem .9rem;margin-bottom:.6rem'>"
                f"<b>🔴 {len(_graves)} cosa(s) que conviene mirar hoy</b></div>",
                unsafe_allow_html=True
            )
            _caja_graves = st.container()
        with _caja_graves:
            for _i_p, _p in enumerate(_graves):
                cS1, cS2 = st.columns([5, 2])
                cS1.markdown(f"**{_p['titulo']}**  \n<span style='opacity:.75;font-size:.87em'>"
                              f"{_p['detalle']}</span>", unsafe_allow_html=True)
                cS2.button("Ir a arreglarlo →", key=f"ir_salud_alto_{_i_p}",
                            on_click=ir_a_donde_dice_el_aviso, args=(_p["donde"],),
                            help=_p["donde"])
                cS2.caption(f"📍 {_p['donde']}")

    if _resto:
        # Plegados, con avisos graves, los «sin apuro» van en el MISMO plegable: dos renglones
        # plegados uno abajo del otro eran otro renglón entre el encabezado y la caja de
        # búsqueda. Sin graves, o abiertos, quedan en el suyo como antes.
        if _graves and _plegar_avisos:
            with _caja_graves:
                st.markdown("**🟡 Sin apuro**")
            _caja_resto = _caja_graves
        else:
            _caja_resto = st.expander(f"🟡 {len(_resto)} cosa(s) más, sin apuro", expanded=False)
        with _caja_resto:
            for _i_p, _p in enumerate(_resto):
                st.markdown(f"**{_p['titulo']}**")
                st.caption(_p["detalle"])
                st.button(f"Ir a {_p['donde'].split('→')[-1].strip()} →",
                           key=f"ir_salud_resto_{_i_p}",
                           on_click=ir_a_donde_dice_el_aviso, args=(_p["donde"],),
                           help=_p["donde"])

    # En el celular va adentro del aviso plegado: suelto era una fila más entre el encabezado y
    # la caja de búsqueda. Si no hay avisos graves, queda donde estaba.
    with (_caja_graves if (_graves and _plegar_avisos) else st.container()):
        if st.button("🔄 Volver a revisar", key="refrescar_salud"):
            invalidar_salud()
            st.rerun()
    st.markdown("")


PAGINAS = ["🔍 Buscador", "🔗 Vincular manual", "📁 Cargar Excel", "🗂️ Administrar",
           "📊 Estadísticas", "📋 Lista WhatsApp", "🚗 Vehículos", "🛠️ Modo Mecánico"]

# Las sub-solapas de Estadísticas viven acá arriba y no adentro de la pantalla porque el
# botón de los avisos de salud —que se dibuja mucho antes— necesita poder llevar hasta una.
SUB_STATS = ["📈 Resumen", "📥 Importaciones", "💾 Backup y config", "🧮 Auditoría y depósito",
             "🔎 Búsquedas sin resultado", "📌 Para pedir", "🔗 Equivalencias sugeridas"]

# Una línea por pantalla diciendo para qué sirve. Sin esto hay que entrar a cada una para
# saber qué hace, y el que atiende el mostrador no tiene tiempo de andar explorando.
PARA_QUE_SIRVE = {
    "🔍 Buscador": "Buscar un repuesto y ver todas las marcas que sirven en su lugar.",
    "🔗 Vincular manual": "Decir a mano que dos códigos son equivalentes.",
    "📁 Cargar Excel": "Subir la lista de precios de un proveedor.",
    "🗂️ Administrar": "Editar productos, marcas y usuarios.",
    "📊 Estadísticas": "Qué comprar, qué no se vende, cuánto aumentó cada proveedor.",
    "📋 Lista WhatsApp": "Pegar un pedido que llegó por mensaje y resolverlo de una.",
    "🚗 Vehículos": "Fichas de los autos: qué se le puso a cada uno y cuándo.",
    "🛠️ Modo Mecánico": "Identificar un auto por patente, chasis o número de motor.",
}

if st.session_state.get("pagina_actual") not in PAGINAS:
    st.session_state["pagina_actual"] = PAGINAS[0]

# En los dos modos se usa st.radio en vez de un desplegable: el desplegable de Streamlit lleva
# un campo de texto adentro para filtrar, y en el celular eso abre el teclado cada vez que lo
# tocás, que es molesto para algo que se usa todo el tiempo. Con radio es un toque y listo.
# El CSS los muestra como pastillas: en el celular se acomodan solas en varias filas.
st.radio("Sección:", PAGINAS, key="pagina_actual", horizontal=True, label_visibility="collapsed")

pagina = st.session_state["pagina_actual"]

# Debajo de las pastillas, una línea que dice para qué sirve la sección elegida. Es lo que
# convierte una fila de ocho botones en algo que se entiende sin que nadie te lo explique.
# En el celular, en el buscador no: es la pantalla que se explica sola, y cada renglón arriba de
# la caja de búsqueda es un renglón que hay que bajar para llegar a ella.
if PARA_QUE_SIRVE.get(pagina) and not (es_celular() and pagina == PAGINAS[0]):
    st.markdown(
        f"<div style='margin:-.4rem 0 .9rem 0;padding:.45rem .8rem;"
        f"background:rgba(128,128,128,.10);border-radius:6px;font-size:.9em;opacity:.85'>"
        f"{PARA_QUE_SIRVE[pagina]}</div>",
        unsafe_allow_html=True
    )

# Los avisos que quedaron guardados antes del último refresco. Van acá, arriba del contenido
# de la página, para que se vean sí o sí — sin esto, cada "Guardado" se perdía en el refresco.
mostrar_avisos_pendientes()


# Las pantallas, en el orden en que estaban escritas acá: cada una empieza con su
# «if pagina == PAGINAS[n]:», así que correrlas todas en fila es lo mismo que antes. Corren en
# este mismo espacio de nombres, como si estuvieran escritas en este lugar (ver
# pantallas/__init__.py).
# «AQUÍ CORREN LAS PANTALLAS»
for _pantalla in pantallas.PANTALLAS:
    exec(pantallas.codigo_de_la_pantalla(_pantalla), globals())

# La pantalla terminó de dibujarse: la tarea de fondo puede volver a correr a toda velocidad.
# Ver ceder_al_mostrador().
_actividad_del_mostrador()["termino"] = time.monotonic()

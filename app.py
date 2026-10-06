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
        · MODO RECUPERACIÓN: CUANDO LA BASE NO SE PUEDE LEER
        · MANTENIMIENTO QUE CORRE SOLO AL ABRIR
    logica/mostrador.py
        · BÚSQUEDA POR NÚMERO DE MOTOR Y POR PATENTE
        · CONSULTAS DE CLIENTES (lo que pidieron y no había)
        · STOCK Y RESERVAS
        · PRECIOS Y MÁRGENES
        · FUSIONAR MARCAS Y PRODUCTOS DUPLICADOS
    logica/equivalencias_descubiertas.py
        · EQUIVALENCIAS DESCUBIERTAS DESDE LAS VENTAS
        · APROBAR POR GRUPOS, CON UNA MUESTRA DE CONTROL
        · PARA REVISAR, POR MOTIVO
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
        · FUENTES OFICIALES DE AFUERA: INDEC Y BCRA
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
    logica/firmas.py
        · LA FICHA DE CADA PIEZA Y LA COMPARACIÓN ENTRE DOS
    logica/evidencia.py
        · LA EVIDENCIA DE CADA PAR Y LAS EQUIVALENCIAS QUE SE DEDUCEN
    logica/repuestos_por_auto.py
        · REPUESTOS POR AUTO Y LECTOR DE VIN
    logica/busqueda_por_texto.py
        · DESCRIPCIONES PEGADAS Y BÚSQUEDA POR TEXTO
    logica/parque_automotor.py
        · EL PARQUE AUTOMOTOR: QUÉ AUTOS CIRCULAN (DNRPA)
    logica/homologaciones.py
        · AUTOPARTES DE SEGURIDAD: EL REGISTRO DE CHAS
    logica/negocio.py
        · COMBOS DE REPUESTOS RELACIONADOS (ej: correa de distribución -> kit + tensor + bomba de agua)
        · LO QUE VA CON ESTO: las otras piezas del MISMO TRABAJO, para el MISMO MOTOR, del catálogo
        · ANTES DE VENDER, PREGUNTÁ: las versiones de la misma pieza para el mismo auto
        · INTELIGENCIA ARTIFICIAL: fotos, audio y remitos
        · BUSCAR POR PIEZA Y AUTO
        · DISCONTINUADOS Y REEMPLAZOS DE FÁBRICA
        · REPOSICIÓN Y FAVORITOS
        · CONFIGURACIÓN, USUARIO Y USO DE IA
        · PAPELERA (borrar con red)
        · HISTORIAL, DUPLICADOS Y EXPORTAR A EXCEL
        · COBROS: alias de transferencia y QR
        · COTIZAR: lo que se le puede ofrecer al cliente
    logica/interfaz.py
        · PIEZAS DE INTERFAZ QUE SE REPITEN
        · NAVEGACIÓN: DÓNDE ESTÁ CADA COSA
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
        · MODO MECÁNICO — CAMPAÑAS DE SEGURIDAD Y FALLAS REPORTADAS (NHTSA)
        · MODO MECÁNICO — VISOR DE ESQUEMAS
        · CUENTA CORRIENTE DE LOS TALLERES
        · INTERÉS POR MORA (con la tasa del BCRA)
    logica/deposito.py
        · EL DEPÓSITO: DEL MOSTRADOR A LA CUENTA
        · CUÁNTO TARDA EL DEPÓSITO
        · A QUIÉN SE ESTÁ ATENDIENDO
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
    pantallas/mantenimiento.py (y un archivo por grupo: mantenimiento_encontrar.py, …)
        · MANTENIMIENTO
        · MANTENIMIENTO → ENCONTRAR EQUIVALENCIAS
        · MANTENIMIENTO → LIMPIAR Y CORREGIR
        · MANTENIMIENTO → CALIDAD Y APRENDIZAJE
        · MANTENIMIENTO → CÓDIGOS DE BARRAS
        · MANTENIMIENTO → FOTOS
        · MANTENIMIENTO → ESTADO Y PAPELERA
    pantallas/estadisticas.py
        · ESTADÍSTICAS
    pantallas/whatsapp.py
        · LISTA PARA WHATSAPP
    pantallas/vehiculos.py
        · VEHÍCULOS (ficha digital / historial de piezas)
    pantallas/mecanico.py
        · MODO MECÁNICO
    pantallas/deposito.py
        · DEPÓSITO: lo que pidió el mostrador, y lo que queda para facturar

La lógica que no depende de Streamlit está ADEMÁS en el paquete nucleo/, que se puede usar
desde otro sistema. Se genera desde logica/ con `python3 nucleo/generar.py`, así que si
tocás algo de códigos, planillas o equivalencias, conviene regenerarlo y correr
`python3 -m nucleo.pruebas`.

Antes de subir un cambio: `python3 auditar.py` tiene que dar ERROR 0. Revisa la app entera,
las tres partes juntas, en el orden en que corren.
Si el cambio toca el análisis de equivalencias, además `python3 pruebas_de_la_revision.py`.
"""
import time

import streamlit as st

# LO QUE TARDA CADA ETAPA DE UNA PASADA (lo sugirió una revisión con ChatGPT: «medí antes de
# optimizar»). Se anotan los cortes y se muestran en Mantenimiento → 🩺 Estado y papelera.
# Es de cada pasada a propósito: se crea de nuevo en cada toque y mide solo ese.
_RELOJ = [("inicio", time.perf_counter())]


def _corte(etapa):
    _RELOJ.append((etapa, time.perf_counter()))

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
_corte("cargar la lógica")

# Con la base dañada, la app abre solo para recuperarla: ver «MODO RECUPERACIÓN» en
# logica/copias_y_mantenimiento.py.
if BASE_ILEGIBLE:
    anotar_error("nivel principal/base ilegible", BASE_ILEGIBLE)
    mostrar_modo_recuperacion(BASE_ILEGIBLE)
    st.stop()

# Hay alguien esperando esta pantalla: la tarea de fondo le cede el paso hasta que termine de
# dibujarse (la marca de «terminó» está en la última línea del archivo). Ver ceder_al_mostrador().
_actividad_del_mostrador()["empezo"] = time.monotonic()

st.markdown(CSS_CUSTOM, unsafe_allow_html=True)
# Las ayudas plegadas numeran sus cajas por pasada: ver _clave_de_ayuda().
st.session_state["_ayudas_de_esta_pasada"] = {}

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
    /* En el celular el encabezado va con el nombre solo: el subtítulo empujaba la caja de
       búsqueda hacia abajo. */
    .app-bar { padding: 8px 10px !important; margin-bottom: 6px !important; gap: 10px !important; }
    .app-bar__logo { width: 32px !important; height: 32px !important; font-size: 1rem !important; }
    .app-bar__title { font-size: 1.05rem !important; }
    .app-bar__sub { display: none !important; }
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
    .block-container { padding: 1rem 3rem 4rem 3rem !important; max-width: 1500px !important; }
    [data-testid="stDataFrame"] { font-size: 0.88rem; }
    </style>
    """, unsafe_allow_html=True)


# ============================================================
# ENCABEZADO
# ============================================================
st.markdown(
    """
    <div class="app-bar">
        <div class="app-bar__logo">🔧</div>
        <div>
            <div class="app-bar__title">Equivalencias El Chavo</div>
            <div class="app-bar__sub">Búsqueda de repuestos por equivalencia</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

# La copia a GitHub cuando hay cambios, en su propio hilo. Ver vigilar_la_copia().
# Va ANTES del login, a propósito: después de un reinicio de Streamlit, la primera visita
# suele ser el despertador de GitHub (.github/despertar_la_app.py), que no entra con usuario y
# se queda en esta pantalla. Con la llamada más abajo, el st.stop() del login la cortaba, y
# lo que se cargara después no tenía copia hasta que alguien iniciara sesión. Casi siempre
# vuelve enseguida: el hilo ya está corriendo.
# Con el nombre de la tarea y no «nivel principal»: así cuenta para el aviso de las tareas que
# fallan seguido (ver errores_de_las_tareas_de_fondo()). Anotado como «nivel principal», un
# vigilante roto no avisaba nunca (lo señaló una revisión con ChatGPT).
try:
    vigilar_la_copia()
except Exception as _err:
    anotar_error("vigilar_la_copia/arranque", _err)

# LA SESIÓN CON CONTRASEÑA SE CIERRA SOLA si nadie la usa por un rato. En la computadora del
# mostrador la pestaña queda abierta días: sin esto, la sesión de administrador que abrió el
# dueño a la mañana la hereda cualquiera que se siente después, con permiso para borrar y bajar
# la base entera. Cuenta desde el último toque, así que usándola no se corta nunca.
HORAS_DE_SESION_SIN_USO = 4
if st.session_state.get("nivel_usuario") in ("admin", "operador", "mecanico"):
    _ultimo_toque = st.session_state.get("_ultimo_toque", time.time())
    if time.time() - _ultimo_toque > HORAS_DE_SESION_SIN_USO * 3600:
        cerrar_sesion()
        st.info(f"🔒 La sesión se cerró sola: pasaron más de {HORAS_DE_SESION_SIN_USO} horas "
                "sin usarla. Para volver a entrar, «🔑 Ingresar», arriba.")
    else:
        st.session_state["_ultimo_toque"] = time.time()
        # Y que siga pudiendo entrar con ese nivel: ver nivel_vigente_de_la_sesion().
        try:
            _nivel_hoy = nivel_vigente_de_la_sesion()
        except sqlite3.Error as _err:
            anotar_error("nivel_vigente_de_la_sesion", _err)
            _nivel_hoy = st.session_state.get("nivel_usuario")
        if _nivel_hoy is None:
            cerrar_sesion()
            st.warning("🔒 La sesión se cerró: esa cuenta ya no está activa o cambió su "
                       "contraseña. Para volver a entrar, «🔑 Ingresar», arriba.")
        elif _nivel_hoy != st.session_state.get("nivel_usuario"):
            st.session_state["nivel_usuario"] = _nivel_hoy
            st.info(f"🔑 Tu cuenta ahora es de {_nivel_hoy}: los permisos ya se actualizaron.")
else:
    # Sin sesión con contraseña no hay nada que contar, y así el próximo ingreso arranca la
    # cuenta de cero. Antes el reloj de una sesión anterior («Salir» no lo borraba) cerraba la
    # nueva apenas entraba, si habían pasado más de cuatro horas desde aquella.
    st.session_state.pop("_ultimo_toque", None)

# LA APP ABRE EN EL BUSCADOR. Antes abría en «👋 ¿Quién sos?», con nombre y contraseña, y el
# que entraba a buscar un código tenía que pasar por ahí primero —aunque las dos cosas eran
# opcionales—. Ahora se entra como Invitado, y «🔑 Ingresar» queda arriba, chico (lo sugirió
# una revisión de la interfaz con ChatGPT). Lo que pide contraseña la sigue pidiendo: ver
# NIVEL_DE_CADA_SECCION y seccion_permitida().

def selector_de_vista(donde, **extra):
    """El selector de vista, en el lugar que toque (arriba en la computadora, al pie en el
    celular). Uno solo: la clave es una y no puede dibujarse dos veces en la misma pasada."""
    donde.selectbox("Vista:", VISTAS, index=VISTAS.index(vista_detectada()), key="modo_vista",
                    help="Se elige sola según desde dónde entres. Cambiala si no acertó.", **extra)


# En el celular el selector de vista va al pie de la página: las columnas se apilan y ocupaba
# un renglón entero arriba de la caja de búsqueda, para algo que se elige solo.
_VISTA_AL_PIE = es_celular()
if es_admin() or es_operador_o_admin() or st.session_state.get("nivel_usuario") == "mecanico":
    col_estado, col_modo, col_salir = st.columns([3, 1.4, 1])
    nombre_sesion = st.session_state.get("admin_nombre", "")
    etiquetas_nivel = {"admin": "administrador", "operador": "operador", "mecanico": "mecánico"}
    etiqueta_nivel = etiquetas_nivel.get(st.session_state.get("nivel_usuario"), "administrador")
    col_estado.caption(f"🔓 Sesión de {etiqueta_nivel} activa ({nombre_sesion}).")
    if not _VISTA_AL_PIE:
        selector_de_vista(col_modo, label_visibility="collapsed")
    if col_salir.button("Salir"):
        cerrar_sesion()
        st.rerun()
else:
    col_estado, col_modo, col_ingresar = st.columns([3, 1.4, 1])
    col_estado.caption(f"👤 {obtener_usuario_actual()}")
    if not _VISTA_AL_PIE:
        selector_de_vista(col_modo, label_visibility="collapsed")
    with col_ingresar.popover("🔑 Ingresar"):
        mostrar_login_inicial()

if st.session_state.get("nivel_usuario") == "mecanico":
    mostrar_portal_mecanico()
    st.stop()

if "lista_whatsapp" not in st.session_state:
    st.session_state.lista_whatsapp = []  # lista de códigos agregados para el mensaje

_corte("sesión y encabezado")

# ============================================================
# NAVEGACIÓN PRINCIPAL
# ============================================================
# Antes esto era st.tabs(). Se cambió por un selector guardado en la sesión por dos motivos:
#  1) st.tabs pierde en qué pestaña estabas cada vez que la página se refresca, y te devolvía
#     al Buscador (el problema de "me vuelve al inicio" al tocar un botón).
#  2) st.tabs dibuja TODAS las pestañas en cada refresco, aunque no las estés mirando —
#     con 8 pestañas haciendo consultas a la base, eso era trabajo al pedo. Ahora solo se
#     arma la sección que estás viendo, así que la app responde bastante más rápido.
# PAGINAS, SUB_STATS y PARA_QUE_SIRVE viven en logica/interfaz.py, con las demás listas de
# navegación: ver «NAVEGACIÓN: DÓNDE ESTÁ CADA COSA».
if st.session_state.get("pagina_actual") not in PAGINAS:
    st.session_state["pagina_actual"] = PAGINAS[0]

# El menú va ANTES que los avisos del día. Iba después, y con cuatro avisos abiertos quedaba
# a media pantalla en TODAS las secciones: para pasar de Administrar a Estadísticas había que
# bajar a buscarlo. Ver más abajo dónde se abren los avisos.
#
# En los dos modos se usa st.radio en vez de un desplegable: el desplegable de Streamlit lleva
# un campo de texto adentro para filtrar, y en el celular eso abre el teclado cada vez que lo
# tocás, que es molesto para algo que se usa todo el tiempo. Con radio es un toque y listo.
# El CSS los muestra como pastillas, en un solo renglón: en el celular se deslizan de costado
# (ver «La navegación principal» en logica/base.py).
with st.container(key="nav_principal"):
    st.radio("Sección:", PAGINAS, key="pagina_actual", horizontal=True,
             label_visibility="collapsed")

pagina = st.session_state["pagina_actual"]

# Debajo de las pastillas, una línea que dice para qué sirve la sección elegida. Es lo que
# convierte una fila de ocho botones en algo que se entiende sin que nadie te lo explique.
# En el celular, en el buscador no: es la pantalla que se explica sola, y cada renglón arriba de
# la caja de búsqueda es un renglón que hay que bajar para llegar a ella.
# A la vista y no plegada: plegada ocupaba el mismo renglón («ℹ️ ¿Para qué sirve esta
# sección?») y escondía justo la respuesta. Las ayudas largas sí van plegadas (ver ayuda());
# esta es de una línea.
if PARA_QUE_SIRVE.get(pagina) and not (es_celular() and pagina == PAGINAS[0]):
    st.caption(f"ℹ️ {PARA_QUE_SIRVE[pagina]}")

# Aviso fuerte si la base quedó vacía: Streamlit Cloud borra el disco al redesplegar, y sin
# este cartel uno se entera recién cuando busca un código y no aparece nada.
# Con la base ilegible —dañada, o un archivo que no es una base— esto era un error técnico
# en rojo y la pantalla cortada. Ahora lo dice, y se sigue: la restauración de un backup está
# en Estadísticas → 💾 Backup y config, y para llegar ahí la app tiene que seguir dibujándose.
# Si se dañó con la app abierta: el mismo modo recuperación. Una base OCUPADA no es una base
# dañada («database is locked» es OperationalError): eso se dice y se sigue.
try:
    c.execute("SELECT COUNT(*) FROM productos")
    _total_productos = c.fetchone()[0]
except sqlite3.DatabaseError as _err:
    anotar_error("nivel principal/base ilegible", _err)
    if es_una_base_danada(_err):
        mostrar_modo_recuperacion(str(_err))
        st.stop()
    _total_productos = None
    st.warning("⏳ La base está ocupada en este momento. Esperá unos segundos y tocá de nuevo.")
if _total_productos == 0:
    # Sin afirmar la causa: lo más común es un redespliegue, pero no es la única (lo señaló una
    # revisión con ChatGPT).
    st.error(
        "⚠️ **La base no tiene productos.** Puede haberse perdido el archivo de datos en un "
        "despliegue o un reinicio del servidor. Si tenés un backup (.db) descargado, restauralo "
        "desde **Estadísticas → 💾 Backup y config**; para que no vuelva a pasar, mirá ahí abajo "
        "la sección de copia permanente."
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
_corte("navegación y base")
if not st.session_state.get("_tareas_dia_corridas"):
    st.session_state["_tareas_dia_corridas"] = True
    try:
        _hecho_hoy = tareas_automaticas_del_dia()
        if _hecho_hoy:
            st.session_state["_aviso_tareas"] = _hecho_hoy
    except Exception as _err:
        anotar_error("tareas_automaticas_del_dia", _err)

# Las bajadas del catálogo del proveedor, en un hilo aparte. Va afuera del «una vez por día»:
# mientras la app esté abierta puede seguir avanzando, que es lo único que hace que un catálogo
# grande termine alguna vez. Casi siempre esta llamada no hace nada —ya hay una corriendo, o
# está apagado, o se gastó el cupo del día— y vuelve enseguida.
try:
    arrancar_tanda_de_fondo()
except Exception as _err:
    anotar_error("arrancar_tanda_de_fondo/arranque", _err)


# Los partes del mantenimiento y del descubrimiento son para quien administra, no para el
# mostrador: en el celular eran dos o tres renglones técnicos arriba de la caja de búsqueda.
_hecho_hoy = st.session_state.pop("_aviso_tareas", None)
if _hecho_hoy and es_operador_o_admin():
    st.caption("🔧 Mantenimiento automático de hoy: " + " · ".join(_hecho_hoy))

# El resultado del descubrimiento que corrió por atrás. Se muestra una sola vez por resultado:
# sin eso, el mismo cartel quedaría en todas las pantallas hasta la próxima importación.
try:
    _desc_txt = obtener_config("descubrimiento_ultimo", "")
    _desc_fec = obtener_config("descubrimiento_fecha", "")
    if not es_operador_o_admin():
        pass
    elif _desc_txt and st.session_state.get("_desc_visto") != _desc_fec:
        st.session_state["_desc_visto"] = _desc_fec
        st.caption(f"🧠 Búsqueda automática de relaciones ({_desc_fec}): {_desc_txt}")
    elif obtener_config("descubrimiento_pendiente", "") == "1":
        st.caption("🧠 Buscando relaciones nuevas en todo el catálogo, por atrás…")
except Exception as _err:
    anotar_error("nivel principal", _err)

_corte("tareas automáticas")
try:
    _cache_salud = salud_compartida()
except Exception as _err:             # los avisos no pueden impedir que la app abra
    anotar_error("nivel principal/salud", _err)
    _cache_salud = {"problemas": []}

_problemas = _cache_salud["problemas"]
# Los avisos de salud son del negocio (cuántos productos, qué está roto, clientes esperando):
# no se le muestran a quien entró sin contraseña. Ver seccion_permitida().
if _problemas and (es_operador_o_admin() or not hay_claves_configuradas()):
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
    # el administrador en la computadora, que es quien los arregla, y solo en el Buscador, que
    # es donde se arranca: en las demás secciones ya se vieron, y abiertos tapaban la pantalla
    # a la que uno acababa de entrar.
    _plegar_avisos = es_celular() or not es_admin() or pagina != PAGINAS[0]
    # EN EL BUSCADOR, UN BOTÓN CHICO. Plegados seguían siendo un renglón rojo entre el
    # encabezado y la caja de búsqueda, y quien atiende entra a buscar un código, no a
    # administrar. Ahí van en un «🔔 N avisos» que se abre encima, cuando uno quiere (lo
    # sugirió una revisión de la interfaz con ChatGPT). En las demás secciones, como antes.
    _en_el_buscador = pagina == PAGINAS[0]
    if _en_el_buscador:
        _plegar_avisos = True
        _caja_graves = _caja_resto = st.popover(
            f"🔔 {len(_problemas)} aviso(s)" + (f" · 🔴 {len(_graves)}" if _graves else ""))

    if _graves:
        if _en_el_buscador:
            pass
        elif _plegar_avisos:
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
                # Escapados: el título y el detalle llevan nombres de marcas y códigos que
                # vienen de las listas importadas, y acá van adentro de HTML (lo señaló una
                # revisión con ChatGPT). Ver texto_para_html().
                cS1.markdown(f"**{texto_para_html(_p['titulo'])}**  \n<span style='opacity:.75;"
                              f"font-size:.87em'>{texto_para_html(_p['detalle'])}</span>",
                              unsafe_allow_html=True)
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
        elif _en_el_buscador:
            pass
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
    with (_caja_graves if ((_graves and _plegar_avisos) or _en_el_buscador) else st.container()):
        if st.button("🔄 Volver a revisar", key="refrescar_salud"):
            if revisar_la_salud_a_mano():
                st.rerun()
            st.caption("Recién revisado: esto ya es lo de ahora.")
    st.markdown("")


# Los avisos que quedaron guardados antes del último refresco. Van acá, arriba del contenido
# de la página, para que se vean sí o sí — sin esto, cada "Guardado" se perdía en el refresco.
mostrar_avisos_pendientes()
_corte("avisos")


# QUIÉN PUEDE ENTRAR A CADA SECCIÓN. El Buscador, la lista de WhatsApp y el modo mecánico
# quedan abiertos: son el mostrador. Lo demás muestra o cambia datos del negocio —clientes y
# teléfonos, precios, vínculos, la base entera para descargar— y pide contraseña de empleado.
# Ver seccion_permitida(). Adentro, lo que borra o configura sigue pidiendo la de administrador.
NIVEL_DE_CADA_SECCION = {PAGINAS[1]: "empleado", PAGINAS[3]: "empleado",
                         PAGINAS[4]: "empleado", PAGINAS[6]: "empleado",
                         PAGINAS[8]: "empleado"}
if (NIVEL_DE_CADA_SECCION.get(pagina)
        and not seccion_permitida(NIVEL_DE_CADA_SECCION[pagina], pagina.split(" ", 1)[-1])):
    _actividad_del_mostrador()["termino"] = time.monotonic()      # ver ceder_al_mostrador()
    st.stop()

# Las pantallas, en el orden en que estaban escritas acá: cada una empieza con su
# «if pagina == PAGINAS[n]:», así que correrlas todas en fila es lo mismo que antes. Corren en
# este mismo espacio de nombres, como si estuvieran escritas en este lugar (ver
# pantallas/__init__.py).
# «AQUÍ CORREN LAS PANTALLAS»
for _pantalla in pantallas.PANTALLAS:
    exec(pantallas.codigo_de_la_pantalla(_pantalla), globals())

if _VISTA_AL_PIE:
    st.markdown("---")
    selector_de_vista(st)

_corte("la pantalla")
# Se guarda la pasada que terminó; la pantalla de Estado muestra la anterior a la propia.
st.session_state["_tiempos_de_la_pasada"] = [
    (etapa, (t - t_antes) * 1000) for (_e, t_antes), (etapa, t) in zip(_RELOJ, _RELOJ[1:])]
st.session_state["_tiempos_de_la_pasada_de"] = pagina

# La pantalla terminó de dibujarse: la tarea de fondo puede volver a correr a toda velocidad.
# Ver ceder_al_mostrador().
_actividad_del_mostrador()["termino"] = time.monotonic()

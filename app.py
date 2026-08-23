import streamlit as st
import sqlite3
import re
import io
import threading
import unicodedata
import json
from datetime import datetime
from urllib.parse import quote
from openpyxl import load_workbook, Workbook

# ============================================================
# CONFIGURACIÓN DE PÁGINA
# ============================================================
st.set_page_config(page_title="Equivalencias El Chavo", page_icon="🔧", layout="wide")

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
.stRadio label {
  background: var(--bg-panel); border: 1px solid var(--border); border-radius: 999px;
  padding: 5px 14px 5px 10px !important; transition: all 0.15s ease;
}
.stRadio label:has(input:checked) { border-color: var(--accent); background: rgba(232, 163, 61, 0.12); }

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
st.markdown(CSS_CUSTOM, unsafe_allow_html=True)

DB_PATH = "equivalencias_app.db"

# La conexión a la base se comparte entre todas las personas que usan la app al mismo
# tiempo (así funciona el hosting gratuito). Este candado evita que dos operaciones
# (por ejemplo una importación larga y una búsqueda de otra persona) se pisen y
# dejen todo trabado.
db_lock = threading.Lock()


def es_admin():
    return st.session_state.get("nivel_usuario") == "admin"


def es_operador_o_admin():
    """Para acciones que un empleado de confianza puede hacer (usar funciones de IA, agregar
    piezas a un esquema) sin necesitar la contraseña completa de administrador, que además
    desbloquea borrados y configuración sensible."""
    return st.session_state.get("nivel_usuario") in ("admin", "operador")


def validar_password(clave):
    """Chequea la contraseña contra los secrets de admin y de operador. Devuelve
    (nombre, nivel, error) — nivel es 'admin', 'operador', o None si no matcheó ninguna."""
    secretos = st.secrets if hasattr(st, "secrets") else {}
    # [admin_passwords] / [operador_passwords] en Streamlit Secrets, cada una con nombre:clave.
    # También soporta la forma anterior de una sola clave (admin_password) por compatibilidad.
    admin_passwords = dict(secretos.get("admin_passwords", {}))
    clave_unica = secretos.get("admin_password")
    if clave_unica:
        admin_passwords.setdefault("admin", clave_unica)
    operador_passwords = dict(secretos.get("operador_passwords", {}))

    if not admin_passwords and not operador_passwords:
        return None, None, (
            "No configuraste todavía ninguna contraseña en Streamlit Cloud (Settings → Secrets). "
            "Sin eso, nadie puede entrar a las secciones protegidas."
        )
    nombre_admin = next((n for n, p in admin_passwords.items() if p == clave), None)
    if nombre_admin:
        return nombre_admin, "admin", None
    nombre_operador = next((n for n, p in operador_passwords.items() if p == clave), None)
    if nombre_operador:
        return nombre_operador, "operador", None
    return None, None, None


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
        entrar = col_a.form_submit_button("🔓 Ingresar con contraseña", type="primary", use_container_width=True)
        seguir = col_b.form_submit_button("➡️ Continuar", use_container_width=True)

    if entrar:
        nombre, nivel, error = validar_password(clave)
        if error:
            st.error(error)
        elif nivel:
            st.session_state.nivel_usuario = nivel
            st.session_state.admin_nombre = nombre
            st.session_state.saltar_login = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    if seguir:
        st.session_state.usuario_nombre = nombre_usuario.strip() or "Invitado"
        st.session_state.saltar_login = True
        st.rerun()


# ============================================================
# CONEXIÓN Y ESQUEMA
# ============================================================
@st.cache_resource
def get_connection():
    """Conexión única y persistente entre reruns de Streamlit."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # mejor concurrencia / menos bloqueos
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS marcas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE NOT NULL,
        tipo TEXT NOT NULL DEFAULT 'PROVEEDOR',
        url_ficha_template TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    columnas_marcas = [f[1] for f in c.execute("PRAGMA table_info(marcas)").fetchall()]
    if "url_ficha_template" not in columnas_marcas:
        c.execute("ALTER TABLE marcas ADD COLUMN url_ficha_template TEXT")

    c.execute("""CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_raw TEXT NOT NULL,
        codigo_clean TEXT NOT NULL,
        descripcion TEXT,
        marca_id INTEGER NOT NULL REFERENCES marcas(id) ON DELETE CASCADE,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(codigo_clean, marca_id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS equivalencias (
        producto_a_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
        producto_b_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
        created_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (producto_a_id, producto_b_id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS importaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        marca TEXT,
        archivo TEXT,
        filas_cargadas INTEGER,
        filas_omitidas INTEGER,
        fecha TEXT DEFAULT (datetime('now'))
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS catalogos_externos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE NOT NULL,
        url TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS historial_busquedas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        termino TEXT NOT NULL,
        usuario TEXT,
        fecha TEXT DEFAULT (datetime('now'))
    )""")
    columnas_historial = [f[1] for f in c.execute("PRAGMA table_info(historial_busquedas)").fetchall()]
    if "usuario" not in columnas_historial:
        c.execute("ALTER TABLE historial_busquedas ADD COLUMN usuario TEXT")

    # Migraciones: agregar columnas nuevas si no existen todavía
    columnas_productos = [f[1] for f in c.execute("PRAGMA table_info(productos)").fetchall()]
    if "precio" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN precio REAL")
    if "stock" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN stock INTEGER")
    if "favorito" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN favorito INTEGER DEFAULT 0")
    if "imagen_url" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN imagen_url TEXT")
    if "imagen_orb_blob" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN imagen_orb_blob BLOB")
    if "diametro_interno" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN diametro_interno REAL")
    if "diametro_externo" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN diametro_externo REAL")
    if "diametro_interno_cara_b" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN diametro_interno_cara_b REAL")
    if "diametro_externo_cara_b" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN diametro_externo_cara_b REAL")
    if "diametro_rosca_homocinetica" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN diametro_rosca_homocinetica REAL")
    if "diametro_copa" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN diametro_copa REAL")
    if "ancho" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN ancho REAL")
    if "paso_rosca" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN paso_rosca TEXT")
    if "cantidad_estrias" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN cantidad_estrias INTEGER")
    if "estrias_internas" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN estrias_internas INTEGER")
    if "estrias_externas" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN estrias_externas INTEGER")
    if "posicion_seguro" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN posicion_seguro TEXT")
    if "tiene_abs" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN tiene_abs INTEGER")
    if "ubicacion" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN ubicacion TEXT")
    if "veces_buscado" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN veces_buscado INTEGER DEFAULT 0")

    # Vehículos y ficha digital ("mellizo digital") para historial de piezas por patente
    c.execute("""CREATE TABLE IF NOT EXISTS vehiculos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patente TEXT UNIQUE NOT NULL,
        cliente_nombre TEXT,
        cliente_telefono TEXT,
        marca_auto TEXT,
        modelo_auto TEXT,
        anio TEXT,
        motorizacion TEXT,
        km_registro INTEGER,
        km_actual INTEGER,
        km_actualizado_fecha TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    columnas_vehiculos_extra = [f[1] for f in c.execute("PRAGMA table_info(vehiculos)").fetchall()]
    if "anio" not in columnas_vehiculos_extra:
        c.execute("ALTER TABLE vehiculos ADD COLUMN anio TEXT")
    if "motorizacion" not in columnas_vehiculos_extra:
        c.execute("ALTER TABLE vehiculos ADD COLUMN motorizacion TEXT")

    # Migración: instalaciones existentes que no tenían km_registro (km de cuando se cargó
    # el vehículo por primera vez, fijo, para poder calcular km recorridos).
    columnas_vehiculos = [f[1] for f in c.execute("PRAGMA table_info(vehiculos)").fetchall()]
    if "km_registro" not in columnas_vehiculos:
        c.execute("ALTER TABLE vehiculos ADD COLUMN km_registro INTEGER")
        # Para los vehículos que ya existían, se usa el km_actual que tengan como punto de partida
        # (es lo mejor que se puede hacer sin el dato original; a partir de ahora queda fijo).
        c.execute("UPDATE vehiculos SET km_registro = km_actual WHERE km_registro IS NULL")

    c.execute("""CREATE TABLE IF NOT EXISTS historial_piezas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vehiculo_id INTEGER NOT NULL REFERENCES vehiculos(id) ON DELETE CASCADE,
        producto_id INTEGER REFERENCES productos(id) ON DELETE SET NULL,
        descripcion_pieza TEXT NOT NULL,
        marca_pieza TEXT,
        codigo_pieza TEXT,
        km_instalacion INTEGER,
        fecha_instalacion TEXT DEFAULT (datetime('now')),
        vida_util_km INTEGER,
        nota TEXT
    )""")

    # Auditoría diaria de stock por muestreo aleatorio
    c.execute("""CREATE TABLE IF NOT EXISTS auditoria_diaria (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL,
        producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
        stock_sistema INTEGER,
        stock_contado INTEGER,
        diferencia INTEGER,
        resuelto INTEGER DEFAULT 0,
        UNIQUE(fecha, producto_id)
    )""")

    # ---- Modo Mecánico ----
    # fabricante = '' significa código genérico (estándar OBD-II, válido para cualquier auto).
    # Un mismo código (ej. P1105) puede repetirse con distinto fabricante, porque en los
    # códigos específicos de marca el mismo número significa cosas distintas según el auto.
    c.execute("""CREATE TABLE IF NOT EXISTS codigos_dtc (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT NOT NULL,
        fabricante TEXT NOT NULL DEFAULT '',
        descripcion TEXT NOT NULL,
        sistema TEXT,
        causas_posibles TEXT,
        UNIQUE(codigo, fabricante)
    )""")

    # Migración: las instalaciones que ya tenían la tabla vieja (sin columna fabricante,
    # con UNIQUE solo en codigo) se convierten al esquema nuevo sin perder datos cargados.
    columnas_dtc = [f[1] for f in c.execute("PRAGMA table_info(codigos_dtc)").fetchall()]
    if "fabricante" not in columnas_dtc:
        c.execute("ALTER TABLE codigos_dtc RENAME TO codigos_dtc_old")
        c.execute("""CREATE TABLE codigos_dtc (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL,
            fabricante TEXT NOT NULL DEFAULT '',
            descripcion TEXT NOT NULL,
            sistema TEXT,
            causas_posibles TEXT,
            UNIQUE(codigo, fabricante)
        )""")
        c.execute("""INSERT INTO codigos_dtc (codigo, fabricante, descripcion, sistema, causas_posibles)
                     SELECT codigo, '', descripcion, sistema, causas_posibles FROM codigos_dtc_old""")
        c.execute("DROP TABLE codigos_dtc_old")

    c.execute("""CREATE TABLE IF NOT EXISTS fabricantes_vin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wmi TEXT UNIQUE NOT NULL,
        fabricante TEXT NOT NULL,
        pais TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS esquemas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL,
        marca_auto TEXT,
        modelo_auto TEXT,
        sistema TEXT,
        descripcion TEXT,
        imagen_blob BLOB,
        imagen_nombre TEXT,
        generado_ia INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    columnas_esquemas = [f[1] for f in c.execute("PRAGMA table_info(esquemas)").fetchall()]
    if "generado_ia" not in columnas_esquemas:
        c.execute("ALTER TABLE esquemas ADD COLUMN generado_ia INTEGER DEFAULT 0")

    # Catálogo de marca/vehículo para "Explorar por categoría", separado de los esquemas en sí:
    # permite precargar la estructura (Volkswagen > Gol Trend) sin necesidad de subir ya una imagen.
    c.execute("""CREATE TABLE IF NOT EXISTS esquemas_catalogo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        marca TEXT NOT NULL,
        modelo TEXT NOT NULL,
        UNIQUE(marca, modelo)
    )""")

    # Piezas marcadas dentro de un esquema (número/nombre + código), para poder buscarlas
    # directamente en el catálogo desde el diagrama — es lo que le da función de "despiece".
    c.execute("""CREATE TABLE IF NOT EXISTS esquema_puntos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        esquema_id INTEGER NOT NULL REFERENCES esquemas(id) ON DELETE CASCADE,
        numero TEXT,
        nombre_pieza TEXT NOT NULL,
        codigo TEXT,
        producto_id INTEGER REFERENCES productos(id) ON DELETE SET NULL,
        pos_x REAL,
        pos_y REAL,
        orden INTEGER DEFAULT 0
    )""")

    # Alias/CBU para el QR de transferencia en las cotizaciones. Se pueden cargar varios
    # (Mercado Pago, distintos bancos, etc.) y elegir cuál usar en cada cotización puntual.
    c.execute("""CREATE TABLE IF NOT EXISTS alias_transferencia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        alias TEXT,
        cbu TEXT,
        titular TEXT,
        qr_real_blob BLOB
    )""")
    columnas_alias = [f[1] for f in c.execute("PRAGMA table_info(alias_transferencia)").fetchall()]
    if "qr_real_blob" not in columnas_alias:
        c.execute("ALTER TABLE alias_transferencia ADD COLUMN qr_real_blob BLOB")

    # Configuración simple de clave/valor (ej: encabezado/pie del mensaje de WhatsApp).
    c.execute("""CREATE TABLE IF NOT EXISTS configuracion (
        clave TEXT PRIMARY KEY,
        valor TEXT
    )""")

    # Contador de uso de las funciones de IA — para ver de un vistazo cuánto se usa cada una
    # y anticipar si alguna se está acercando a los límites gratuitos.
    c.execute("""CREATE TABLE IF NOT EXISTS uso_ia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        funcion TEXT NOT NULL,
        usuario TEXT,
        exito INTEGER,
        fecha TEXT DEFAULT (datetime('now'))
    )""")

    # Papelera: guarda una copia de lo que se borra (marcas, productos, combos, alias) para
    # poder restaurarlo si fue un error. No reemplaza el backup completo, es para el día a día.
    c.execute("""CREATE TABLE IF NOT EXISTS papelera (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT NOT NULL,
        datos_json TEXT NOT NULL,
        eliminado_por TEXT,
        eliminado_en TEXT DEFAULT (datetime('now'))
    )""")

    # Cuando un empleado busca algo y no hay stock (o le falta), lo marca acá para que el dueño
    # lo revise después y decida qué pedirle a cada proveedor. Un mismo producto pedido varias
    # veces por distintos empleados suma en "veces_solicitado" en vez de duplicar filas.
    c.execute("""CREATE TABLE IF NOT EXISTS pedidos_reposicion (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
        veces_solicitado INTEGER DEFAULT 1,
        ultimo_solicitado_por TEXT,
        ultima_fecha TEXT DEFAULT (datetime('now')),
        estado TEXT DEFAULT 'pendiente',
        UNIQUE(producto_id)
    )""")

    # Historial de precios: cada vez que se cambia el precio de un producto queda un registro,
    # para poder ver cómo fue variando en el tiempo.
    c.execute("""CREATE TABLE IF NOT EXISTS historial_precios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
        precio REAL,
        fecha TEXT DEFAULT (datetime('now'))
    )""")

    # Combos de repuestos que suelen cambiarse juntos (ej: correa de distribución -> kit + tensor + bomba de agua).
    # "disparador" es la palabra/frase que se busca dentro de la descripción del producto encontrado.
    c.execute("""CREATE TABLE IF NOT EXISTS combos_sugeridos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        disparador TEXT NOT NULL,
        item TEXT NOT NULL
    )""")
    c.execute("SELECT COUNT(*) FROM combos_sugeridos")
    if c.fetchone()[0] == 0:
        c.executemany(
            "INSERT INTO combos_sugeridos (disparador, item) VALUES (?, ?)",
            [
                ("correa de distribucion", "Kit de distribución"),
                ("correa de distribucion", "Tensor de distribución"),
                ("correa de distribucion", "Bomba de agua"),
            ]
        )

    # Semilla inicial de códigos DTC genéricos (estándar OBD-II / SAE J2012, no específicos de
    # marca), verificados contra fuentes de referencia. Es un punto de partida — sumá o corregí
    # los que necesites desde la app. Los códigos P1xxx específicos de fabricante se cargan
    # aparte indicando la marca (ver Modo Mecánico → Códigos DTC).
    c.execute("SELECT COUNT(*) FROM codigos_dtc")
    if c.fetchone()[0] == 0:
        seed_dtc = [
            ("P0010","Falla eléctrica en el actuador de posición A del árbol de levas, banco 1","Motor - Sensores/Admisión","Cableado cortado o en corto, conector sucio/flojo, sensor o actuador dañado"),
            ("P0011","Avance excesivo o mal desempeño en la posición A del árbol de levas, banco 1","Motor - Sensores/Admisión","Sensor descalibrado, obstrucción física, fuga, componente mecánico desgastado"),
            ("P0012","Retardo excesivo en la posición A del árbol de levas, banco 1","Motor - Sensores/Admisión","Sensor descalibrado, obstrucción física, fuga, componente mecánico desgastado"),
            ("P0013","Falla eléctrica en el actuador de posición B del árbol de levas, banco 1","Motor - Sensores/Admisión","Cableado cortado o en corto, conector sucio/flojo, sensor o actuador dañado"),
            ("P0014","Avance excesivo o mal desempeño en la posición B del árbol de levas, banco 1","Motor - Sensores/Admisión","Sensor descalibrado, obstrucción física, fuga, componente mecánico desgastado"),
            ("P0015","Retardo excesivo en la posición B del árbol de levas, banco 1","Motor - Sensores/Admisión","Sensor descalibrado, obstrucción física, fuga, componente mecánico desgastado"),
            ("P0020","Falla eléctrica en el actuador de posición A del árbol de levas, banco 2","Motor - Sensores/Admisión","Cableado cortado o en corto, conector sucio/flojo, sensor o actuador dañado"),
            ("P0021","Avance excesivo o mal desempeño en la posición A del árbol de levas, banco 2","Motor - Sensores/Admisión","Sensor descalibrado, obstrucción física, fuga, componente mecánico desgastado"),
            ("P0022","Retardo excesivo en la posición A del árbol de levas, banco 2","Motor - Sensores/Admisión","Sensor descalibrado, obstrucción física, fuga, componente mecánico desgastado"),
            ("P0030","Falla eléctrica en el calefactor del sensor de oxígeno, banco 1 sensor 1","Emisiones","Cableado cortado o en corto, conector sucio/flojo, sensor o actuador dañado"),
            ("P0031","Señal baja en el calefactor del sensor de oxígeno, banco 1 sensor 1","Emisiones","Cortocircuito a masa, sensor en mal estado, cableado dañado"),
            ("P0032","Señal alta en el calefactor del sensor de oxígeno, banco 1 sensor 1","Emisiones","Circuito abierto, cortocircuito a positivo, sensor en mal estado"),
            ("P0036","Falla eléctrica en el calefactor del sensor de oxígeno, banco 1 sensor 2","Emisiones","Cableado cortado o en corto, conector sucio/flojo, sensor o actuador dañado"),
            ("P0037","Señal baja en el calefactor del sensor de oxígeno, banco 1 sensor 2","Emisiones","Cortocircuito a masa, sensor en mal estado, cableado dañado"),
            ("P0038","Señal alta en el calefactor del sensor de oxígeno, banco 1 sensor 2","Emisiones","Circuito abierto, cortocircuito a positivo, sensor en mal estado"),
            ("P0050","Falla eléctrica en el calefactor del sensor de oxígeno, banco 2 sensor 1","Emisiones","Cableado cortado o en corto, conector sucio/flojo, sensor o actuador dañado"),
            ("P0051","Señal baja en el calefactor del sensor de oxígeno, banco 2 sensor 1","Emisiones","Cortocircuito a masa, sensor en mal estado, cableado dañado"),
            ("P0052","Señal alta en el calefactor del sensor de oxígeno, banco 2 sensor 1","Emisiones","Circuito abierto, cortocircuito a positivo, sensor en mal estado"),
            ("P0056","Falla eléctrica en el calefactor del sensor de oxígeno, banco 2 sensor 2","Emisiones","Cableado cortado o en corto, conector sucio/flojo, sensor o actuador dañado"),
            ("P0057","Señal baja en el calefactor del sensor de oxígeno, banco 2 sensor 2","Emisiones","Cortocircuito a masa, sensor en mal estado, cableado dañado"),
            ("P0058","Señal alta en el calefactor del sensor de oxígeno, banco 2 sensor 2","Emisiones","Circuito abierto, cortocircuito a positivo, sensor en mal estado"),
            ("P0070","Falla eléctrica en el sensor de temperatura de aire ambiente","Motor - Sensores/Admisión","Cableado cortado o en corto, conector sucio/flojo, sensor dañado"),
            ("P0071","Sensor de temperatura de aire ambiente fuera de rango","Motor - Sensores/Admisión","Sensor descalibrado, cableado dañado"),
            ("P0072","Señal baja en el sensor de temperatura de aire ambiente","Motor - Sensores/Admisión","Cortocircuito a masa, sensor en mal estado"),
            ("P0073","Señal alta en el sensor de temperatura de aire ambiente","Motor - Sensores/Admisión","Circuito abierto, sensor en mal estado"),
            ("P0074","Señal intermitente en el sensor de temperatura de aire ambiente","Motor - Sensores/Admisión","Conector flojo u oxidado, falso contacto"),
            ("P0100","Falla eléctrica en el medidor de caudal de aire (MAF)","Motor - Sensores/Admisión","Sensor sucio, cableado, conector"),
            ("P0101","Medidor de caudal de aire (MAF) fuera de rango","Motor - Sensores/Admisión","Filtro de aire sucio, fugas de vacío, sensor sucio"),
            ("P0102","Señal baja en el medidor de caudal de aire (MAF)","Motor - Sensores/Admisión","Cortocircuito a masa, sensor sucio o dañado"),
            ("P0103","Señal alta en el medidor de caudal de aire (MAF)","Motor - Sensores/Admisión","Circuito abierto, sensor dañado"),
            ("P0104","Señal intermitente en el medidor de caudal de aire (MAF)","Motor - Sensores/Admisión","Conector flojo u oxidado, falso contacto"),
            ("P0105","Falla eléctrica en el sensor de presión absoluta de múltiple / barométrica (MAP)","Motor - Sensores/Admisión","Manguera de vacío rota, sensor o cableado dañado"),
            ("P0106","Sensor MAP fuera de rango","Motor - Sensores/Admisión","Fuga de vacío, sensor descalibrado"),
            ("P0107","Señal baja en el sensor MAP","Motor - Sensores/Admisión","Cortocircuito a masa, sensor dañado"),
            ("P0108","Señal alta en el sensor MAP","Motor - Sensores/Admisión","Circuito abierto, sensor dañado"),
            ("P0109","Señal intermitente en el sensor MAP","Motor - Sensores/Admisión","Conector flojo u oxidado, falso contacto"),
            ("P0110","Falla eléctrica en el sensor de temperatura del aire de admisión (IAT)","Motor - Sensores/Admisión","Sensor o cableado en mal estado"),
            ("P0111","Sensor IAT fuera de rango","Motor - Sensores/Admisión","Sensor descalibrado, cableado dañado"),
            ("P0112","Señal baja en el sensor IAT","Motor - Sensores/Admisión","Cortocircuito a masa, sensor dañado"),
            ("P0113","Señal alta en el sensor IAT","Motor - Sensores/Admisión","Circuito abierto, sensor dañado"),
            ("P0114","Señal intermitente en el sensor IAT","Motor - Sensores/Admisión","Conector flojo u oxidado, falso contacto"),
            ("P0115","Falla eléctrica en el sensor de temperatura del refrigerante (ECT)","Motor - Sensores/Admisión","Sensor, conector, cableado"),
            ("P0116","Sensor ECT fuera de rango","Motor - Sensores/Admisión","Sensor descalibrado, nivel de refrigerante bajo"),
            ("P0117","Señal baja en el sensor ECT","Motor - Sensores/Admisión","Cortocircuito a masa, sensor dañado"),
            ("P0118","Señal alta en el sensor ECT","Motor - Sensores/Admisión","Circuito abierto, sensor dañado"),
            ("P0119","Señal intermitente en el sensor ECT","Motor - Sensores/Admisión","Conector flojo u oxidado, falso contacto"),
            ("P0120","Falla eléctrica en el sensor de posición del acelerador/pedal A (TPS)","Motor - Sensores/Admisión","Sensor TPS, cableado"),
            ("P0121","Sensor TPS A fuera de rango","Motor - Sensores/Admisión","Sensor descalibrado, cableado dañado"),
            ("P0122","Señal baja en el sensor TPS A","Motor - Sensores/Admisión","Cortocircuito a masa, sensor dañado"),
            ("P0123","Señal alta en el sensor TPS A","Motor - Sensores/Admisión","Circuito abierto, sensor dañado"),
            ("P0124","Señal intermitente en el sensor TPS A","Motor - Sensores/Admisión","Conector flojo u oxidado, falso contacto"),
            ("P0125","El refrigerante no llega a la temperatura necesaria para el lazo cerrado de combustible","Motor - Sensores/Admisión","Termostato pegado en abierto, sensor ECT"),
            ("P0128","Termostato: el refrigerante no alcanza la temperatura de regulación","Motor - Sensores/Admisión","Termostato pegado en abierto"),
            ("P0130","Falla eléctrica en el sensor de oxígeno, banco 1 sensor 1","Emisiones","Sonda lambda, cableado"),
            ("P0131","Voltaje bajo en el sensor de oxígeno, banco 1 sensor 1","Emisiones","Cortocircuito a masa, sonda en mal estado"),
            ("P0132","Voltaje alto en el sensor de oxígeno, banco 1 sensor 1","Emisiones","Circuito abierto, sonda en mal estado"),
            ("P0133","Respuesta lenta en el sensor de oxígeno, banco 1 sensor 1","Emisiones","Sonda envejecida o contaminada"),
            ("P0134","Sin actividad detectada en el sensor de oxígeno, banco 1 sensor 1","Emisiones","Sonda desconectada o sin actividad, cableado"),
            ("P0135","Falla eléctrica en el calefactor del sensor de oxígeno, banco 1 sensor 1","Emisiones","Calefactor de la sonda dañado, fusible, cableado"),
            ("P0136","Falla eléctrica en el sensor de oxígeno, banco 1 sensor 2","Emisiones","Sonda lambda, cableado"),
            ("P0137","Voltaje bajo en el sensor de oxígeno, banco 1 sensor 2","Emisiones","Cortocircuito a masa, sonda en mal estado"),
            ("P0138","Voltaje alto en el sensor de oxígeno, banco 1 sensor 2","Emisiones","Circuito abierto, sonda en mal estado"),
            ("P0140","Sin actividad detectada en el sensor de oxígeno, banco 1 sensor 2","Emisiones","Sonda desconectada o sin actividad, cableado"),
            ("P0141","Falla eléctrica en el calefactor del sensor de oxígeno, banco 1 sensor 2","Emisiones","Calefactor de la sonda dañado, fusible, cableado"),
            ("P0150","Falla eléctrica en el sensor de oxígeno, banco 2 sensor 1","Emisiones","Sonda lambda, cableado"),
            ("P0155","Falla eléctrica en el calefactor del sensor de oxígeno, banco 2 sensor 1","Emisiones","Calefactor de la sonda dañado, fusible, cableado"),
            ("P0170","Ajuste de mezcla fuera de rango, banco 1","Motor - Sensores/Admisión","Sonda O2, inyectores, fugas de vacío"),
            ("P0171","Mezcla demasiado pobre, banco 1","Motor - Sensores/Admisión","Fuga de vacío, inyector, sensor MAF"),
            ("P0172","Mezcla demasiado rica, banco 1","Motor - Sensores/Admisión","Inyector, presión de combustible, sensor O2"),
            ("P0173","Ajuste de mezcla fuera de rango, banco 2","Motor - Sensores/Admisión","Sonda O2, inyectores, fugas de vacío"),
            ("P0174","Mezcla demasiado pobre, banco 2","Motor - Sensores/Admisión","Fuga de vacío, inyector, sensor MAF"),
            ("P0175","Mezcla demasiado rica, banco 2","Motor - Sensores/Admisión","Inyector, presión de combustible, sensor O2"),
            ("P0200","Falla eléctrica general en el circuito de inyectores","Motor - Inyectores/Combustible","Inyector, cableado, módulo"),
            ("P0201","Falla eléctrica en el inyector del cilindro 1","Motor - Inyectores/Combustible","Inyector, cableado de ese cilindro"),
            ("P0202","Falla eléctrica en el inyector del cilindro 2","Motor - Inyectores/Combustible","Inyector, cableado de ese cilindro"),
            ("P0203","Falla eléctrica en el inyector del cilindro 3","Motor - Inyectores/Combustible","Inyector, cableado de ese cilindro"),
            ("P0204","Falla eléctrica en el inyector del cilindro 4","Motor - Inyectores/Combustible","Inyector, cableado de ese cilindro"),
            ("P0217","Sobretemperatura del motor","Motor - Encendido/Combustión","Refrigerante, bomba de agua, termostato"),
            ("P0230","Falla eléctrica en el circuito primario de la bomba de combustible","Motor - Inyectores/Combustible","Bomba, relé, cableado"),
            ("P0300","Fallos de encendido detectados en varios cilindros o aleatorios","Motor - Encendido/Combustión","Bujías, bobinas, compresión"),
            ("P0301","Fallo de encendido en el cilindro 1","Motor - Encendido/Combustión","Bujía, bobina, inyector de ese cilindro"),
            ("P0302","Fallo de encendido en el cilindro 2","Motor - Encendido/Combustión","Bujía, bobina, inyector de ese cilindro"),
            ("P0303","Fallo de encendido en el cilindro 3","Motor - Encendido/Combustión","Bujía, bobina, inyector de ese cilindro"),
            ("P0304","Fallo de encendido en el cilindro 4","Motor - Encendido/Combustión","Bujía, bobina, inyector de ese cilindro"),
            ("P0325","Falla eléctrica en el sensor de detonación (knock sensor), banco 1 o único","Motor - Encendido/Combustión","Sensor, cableado"),
            ("P0326","Sensor de detonación 1 fuera de rango","Motor - Encendido/Combustión","Sensor descalibrado, cableado"),
            ("P0327","Señal baja en el sensor de detonación 1","Motor - Encendido/Combustión","Cortocircuito a masa, sensor dañado"),
            ("P0328","Señal alta en el sensor de detonación 1","Motor - Encendido/Combustión","Circuito abierto, sensor dañado"),
            ("P0335","Falla eléctrica en el sensor de posición del cigüeñal (CKP)","Motor - Encendido/Combustión","Sensor CKP, cableado, tone wheel"),
            ("P0336","Sensor CKP fuera de rango","Motor - Encendido/Combustión","Sensor descalibrado, rueda fónica dañada"),
            ("P0340","Falla eléctrica en el sensor de posición del árbol de levas (CMP)","Motor - Encendido/Combustión","Sensor CMP, cableado"),
            ("P0341","Sensor CMP fuera de rango","Motor - Encendido/Combustión","Sensor descalibrado, cableado"),
            ("P0400","Falla en el caudal de recirculación de gases de escape (EGR)","Emisiones","Válvula EGR, conductos obstruidos"),
            ("P0401","Caudal insuficiente de EGR","Emisiones","Válvula EGR trabada cerrada, conducto obstruido"),
            ("P0402","Caudal excesivo de EGR","Emisiones","Válvula EGR trabada abierta"),
            ("P0420","Eficiencia del catalizador por debajo del umbral, banco 1","Emisiones","Catalizador, sonda lambda"),
            ("P0430","Eficiencia del catalizador por debajo del umbral, banco 2","Emisiones","Catalizador, sonda lambda"),
            ("P0440","Falla general en el sistema de control de emisiones evaporativas (EVAP)","Emisiones","Tapa de nafta, válvula, mangueras"),
            ("P0441","Caudal de purga EVAP incorrecto","Emisiones","Válvula de purga, mangueras obstruidas"),
            ("P0442","Fuga pequeña detectada en el sistema EVAP","Emisiones","Tapa de nafta floja, manguera con fisura"),
            ("P0446","Falla eléctrica en la válvula de ventilación del sistema EVAP","Emisiones","Válvula de venteo, cableado"),
            ("P0447","Circuito de ventilación EVAP abierto","Emisiones","Cableado cortado, válvula desconectada"),
            ("P0448","Circuito de ventilación EVAP en corto","Emisiones","Cableado en corto, válvula dañada"),
            ("P0451","Falla eléctrica en el sensor de presión del sistema EVAP","Emisiones","Sensor de presión, cableado"),
            ("P0452","Señal baja en el sensor de presión del sistema EVAP","Emisiones","Cortocircuito a masa, sensor dañado"),
            ("P0453","Señal alta en el sensor de presión del sistema EVAP","Emisiones","Circuito abierto, sensor dañado"),
            ("P0455","Fuga grande detectada en el sistema EVAP","Emisiones","Tapa de nafta, manguera desconectada"),
            ("P0456","Fuga muy pequeña detectada en el sistema EVAP","Emisiones","Tapa de nafta, fisura muy pequeña"),
            ("P0457","Fuga detectada, posible tapa de combustible floja o mal cerrada","Emisiones","Tapa de nafta floja, dañada o mal puesta"),
            ("P0461","Sensor de nivel de combustible fuera de rango","Motor - Inyectores/Combustible","Sensor de nivel, flotante"),
            ("P0462","Señal baja en el sensor de nivel de combustible","Motor - Inyectores/Combustible","Cortocircuito a masa, sensor dañado"),
            ("P0463","Señal alta en el sensor de nivel de combustible","Motor - Inyectores/Combustible","Circuito abierto, sensor dañado"),
            ("P0500","Falla eléctrica en el sensor de velocidad del vehículo (VSS)","Transmisión","Sensor VSS, cableado"),
            ("P0501","Sensor VSS fuera de rango","Transmisión","Sensor descalibrado, cableado"),
            ("P0505","Falla en el sistema de control de marcha lenta (IAC)","Motor - Sensores/Admisión","Válvula IAC, cuerpo de aceleración sucio"),
            ("P0506","RPM de marcha lenta por debajo de lo esperado","Motor - Sensores/Admisión","Válvula IAC, fuga de vacío"),
            ("P0507","RPM de marcha lenta por encima de lo esperado","Motor - Sensores/Admisión","Válvula IAC trabada, fuga de vacío grande"),
            ("P0600","Falla en el enlace serial de comunicaciones del módulo","Módulo de control / Eléctrico","Cableado del bus de datos, módulo"),
            ("P0601","Error de suma de verificación en la memoria del módulo de control","Módulo de control / Eléctrico","Módulo de control con falla interna"),
            ("P0700","Avería general en el sistema de control de la transmisión","Transmisión","Ver códigos específicos de la TCM"),
            ("P0701","Sistema de control de la transmisión fuera de rango","Transmisión","Sensor o solenoide de la transmisión"),
            ("P0705","Falla eléctrica en el sensor de rango de la transmisión (PRNDL)","Transmisión","Sensor, cableado"),
            ("P0710","Falla eléctrica en el sensor de temperatura del fluido de la transmisión","Transmisión","Sensor, cableado"),
            ("P0715","Falla eléctrica en el sensor de velocidad de entrada / turbina","Transmisión","Sensor, cableado"),
            ("P0720","Falla eléctrica en el sensor de velocidad de salida de la transmisión","Transmisión","Sensor, cableado"),
            ("P0730","Relación de engranes incorrecta","Transmisión","Solenoides de cambio, fluido bajo o degradado"),
            ("P0740","Falla en el circuito del embrague del convertidor de par","Transmisión","Solenoide TCC, cableado"),
            ("P0750","Falla en el solenoide de cambios A","Transmisión","Solenoide, cableado"),
            ("P0755","Falla en el solenoide de cambios B","Transmisión","Solenoide, cableado"),
            ("P0205","Falla eléctrica en el inyector del cilindro 5","Motor - Inyectores/Combustible","Inyector, cableado de ese cilindro"),
            ("P0206","Falla eléctrica en el inyector del cilindro 6","Motor - Inyectores/Combustible","Inyector, cableado de ese cilindro"),
            ("P0207","Falla eléctrica en el inyector del cilindro 7","Motor - Inyectores/Combustible","Inyector, cableado de ese cilindro"),
            ("P0208","Falla eléctrica en el inyector del cilindro 8","Motor - Inyectores/Combustible","Inyector, cableado de ese cilindro"),
            ("P0221","Sensor TPS B fuera de rango","Motor - Sensores/Admisión","Sensor descalibrado, cableado dañado"),
            ("P0222","Señal baja en el sensor TPS B","Motor - Sensores/Admisión","Cortocircuito a masa, sensor dañado"),
            ("P0223","Señal alta en el sensor TPS B","Motor - Sensores/Admisión","Circuito abierto, sensor dañado"),
            ("P0224","Señal intermitente en el sensor TPS B","Motor - Sensores/Admisión","Conector flojo u oxidado, falso contacto"),
            ("P0231","Señal baja en el circuito secundario de la bomba de combustible","Motor - Inyectores/Combustible","Cortocircuito a masa, bomba, relé"),
            ("P0232","Señal alta en el circuito secundario de la bomba de combustible","Motor - Inyectores/Combustible","Circuito abierto, bomba, relé"),
            ("P0234","Sobrepresión de sobrealimentación (turbo)","Motor - Sensores/Admisión","Válvula wastegate, actuador del turbo"),
            ("P0261","Señal baja en el inyector del cilindro 1","Motor - Inyectores/Combustible","Cortocircuito a masa, inyector dañado"),
            ("P0262","Señal alta en el inyector del cilindro 1","Motor - Inyectores/Combustible","Circuito abierto, inyector dañado"),
            ("P0330","Falla eléctrica en el sensor de detonación 2, banco 2","Motor - Encendido/Combustión","Sensor, cableado"),
            ("P0331","Sensor de detonación 2 fuera de rango","Motor - Encendido/Combustión","Sensor descalibrado, cableado"),
            ("P0339","Señal intermitente en el sensor CKP","Motor - Encendido/Combustión","Conector flojo u oxidado, falso contacto"),
            ("P0343","Señal alta en el sensor CMP","Motor - Encendido/Combustión","Circuito abierto, sensor dañado"),
            ("P0344","Señal intermitente en el sensor CMP","Motor - Encendido/Combustión","Conector flojo u oxidado, falso contacto"),
            ("P0350","Falla general en el circuito primario/secundario de bobina de encendido","Motor - Encendido/Combustión","Bobina, cableado, módulo"),
            ("P0351","Falla en la bobina de encendido A","Motor - Encendido/Combustión","Bobina, cableado"),
            ("P0352","Falla en la bobina de encendido B","Motor - Encendido/Combustión","Bobina, cableado"),
            ("P0353","Falla en la bobina de encendido C","Motor - Encendido/Combustión","Bobina, cableado"),
            ("P0354","Falla en la bobina de encendido D","Motor - Encendido/Combustión","Bobina, cableado"),
            ("P0370","Falla en la señal de referencia de sincronización de alta resolución A","Motor - Encendido/Combustión","Sensor, cableado, rueda fónica"),
            ("P0380","Falla en la bujía/circuito calefactor (motores diésel)","Motor - Encendido/Combustión","Bujía de precalentamiento, relé, cableado"),
            ("P0410","Falla en el sistema de inyección de aire secundario","Emisiones","Bomba de aire secundario, válvulas, mangueras"),
            ("P0411","Caudal incorrecto en la inyección de aire secundario","Emisiones","Bomba de aire secundario, fugas"),
            ("P0480","Falla eléctrica en el circuito de control del ventilador de enfriamiento 1","Motor - Sensores/Admisión","Relé, motor del ventilador, cableado"),
            ("P0481","Falla eléctrica en el circuito de control del ventilador de enfriamiento 2","Motor - Sensores/Admisión","Relé, motor del ventilador, cableado"),
            ("P0510","Falla en el interruptor de mariposa en posición cerrada","Motor - Sensores/Admisión","Interruptor, cableado"),
            ("P0520","Falla eléctrica en el circuito de presión de aceite del motor","Motor - Sensores/Admisión","Sensor, cableado"),
            ("P0521","Presión de aceite del motor fuera de rango","Motor - Sensores/Admisión","Sensor descalibrado, nivel de aceite"),
            ("P0522","Voltaje bajo en la señal de presión de aceite del motor","Motor - Sensores/Admisión","Cortocircuito a masa, sensor dañado"),
            ("P0523","Voltaje alto en la señal de presión de aceite del motor","Motor - Sensores/Admisión","Circuito abierto, sensor dañado"),
            ("P0530","Falla eléctrica en el sensor de presión del refrigerante de A/C","Motor - Sensores/Admisión","Sensor, cableado"),
            ("P0532","Voltaje bajo en el sensor de presión del refrigerante de A/C","Motor - Sensores/Admisión","Cortocircuito a masa, sensor dañado"),
            ("P0533","Voltaje alto en el sensor de presión del refrigerante de A/C","Motor - Sensores/Admisión","Circuito abierto, sensor dañado"),
            ("P0534","Pérdida de carga de refrigerante del A/C","Motor - Sensores/Admisión","Fuga en el circuito de A/C"),
            ("P0560","Falla en el voltaje del sistema","Módulo de control / Eléctrico","Batería, alternador, cableado"),
            ("P0562","Voltaje del sistema bajo","Módulo de control / Eléctrico","Batería descargada, alternador"),
            ("P0563","Voltaje del sistema alto","Módulo de control / Eléctrico","Regulador de tensión, alternador"),
            ("P0602","Módulo de control sin programar","Módulo de control / Eléctrico","Requiere programación con equipo de diagnóstico"),
            ("P0603","Falla en la memoria KAM (no borrable) del módulo de control","Módulo de control / Eléctrico","Módulo de control con falla interna"),
            ("P0604","Falla en la memoria RAM del módulo de control","Módulo de control / Eléctrico","Módulo de control con falla interna"),
            ("P0605","Falla en la memoria ROM del módulo de control","Módulo de control / Eléctrico","Módulo de control con falla interna"),
            ("P0606","Falla en el procesador del módulo de control (PCM)","Módulo de control / Eléctrico","Módulo de control con falla interna"),
            ("P0620","Falla eléctrica en el circuito de control del generador/alternador","Módulo de control / Eléctrico","Alternador, cableado, regulador"),
            ("P0630","VIN no programado o no coincide con el ECM/PCM","Módulo de control / Eléctrico","Requiere reprogramación con equipo de diagnóstico"),
            ("P0650","Falla eléctrica en el circuito de la luz indicadora de fallas (MIL)","Módulo de control / Eléctrico","Bombilla, cableado, módulo"),
            ("P0703","Falla en el circuito del interruptor de freno / convertidor de par B","Transmisión","Interruptor de freno, cableado"),
            ("P0706","Sensor de rango de la transmisión fuera de rango","Transmisión","Sensor PRNDL descalibrado, cableado"),
            ("P0725","Falla en el circuito de entrada de velocidad del motor","Transmisión","Sensor, cableado"),
            ("P0731","Relación de engranes incorrecta en primera marcha","Transmisión","Solenoides de cambio, fluido bajo o degradado"),
            ("P0732","Relación de engranes incorrecta en segunda marcha","Transmisión","Solenoides de cambio, fluido bajo o degradado"),
            ("P0733","Relación de engranes incorrecta en tercera marcha","Transmisión","Solenoides de cambio, fluido bajo o degradado"),
            ("P0734","Relación de engranes incorrecta en cuarta marcha","Transmisión","Solenoides de cambio, fluido bajo o degradado"),
            ("P0743","Problema eléctrico en el embrague del convertidor de par","Transmisión","Solenoide TCC, cableado"),
            ("P0745","Falla en el solenoide de control de presión de la transmisión","Transmisión","Solenoide, cableado, fluido"),
            ("P0760","Falla en el solenoide de cambios C","Transmisión","Solenoide, cableado"),
            ("P0765","Falla en el solenoide de cambios D","Transmisión","Solenoide, cableado"),
            ("P0770","Falla en el solenoide de cambios E","Transmisión","Solenoide, cableado"),
            ("P0850","Falla en el interruptor de posición de estacionamiento/neutro","Transmisión","Interruptor, cableado"),
        ]
        c.executemany(
            "INSERT OR IGNORE INTO codigos_dtc (codigo, fabricante, descripcion, sistema, causas_posibles) "
            "VALUES (?, '', ?, ?, ?)",
            seed_dtc
        )

    columnas_equiv = [f[1] for f in c.execute("PRAGMA table_info(equivalencias)").fetchall()]
    if "verificada" not in columnas_equiv:
        c.execute("ALTER TABLE equivalencias ADD COLUMN verificada INTEGER DEFAULT 0")
    if "nivel" not in columnas_equiv:
        c.execute("ALTER TABLE equivalencias ADD COLUMN nivel TEXT DEFAULT 'Exacta'")
    if "nota" not in columnas_equiv:
        c.execute("ALTER TABLE equivalencias ADD COLUMN nota TEXT")

    columnas_historial = [f[1] for f in c.execute("PRAGMA table_info(historial_busquedas)").fetchall()]
    if "sin_resultado" not in columnas_historial:
        c.execute("ALTER TABLE historial_busquedas ADD COLUMN sin_resultado INTEGER DEFAULT 0")

    c.execute("CREATE INDEX IF NOT EXISTS idx_codigo_clean ON productos(codigo_clean)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_marca_id ON productos(marca_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_eq_a ON equivalencias(producto_a_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_eq_b ON equivalencias(producto_b_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_vehiculo_patente ON vehiculos(patente)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_historial_vehiculo ON historial_piezas(vehiculo_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_auditoria_fecha ON auditoria_diaria(fecha)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_dtc_codigo ON codigos_dtc(codigo)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_vin_wmi ON fabricantes_vin(wmi)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_esquema_puntos ON esquema_puntos(esquema_id)")
    conn.commit()
    return conn


conn = get_connection()
c = conn.cursor()


# ============================================================
# UTILIDADES
# ============================================================
def sanitizar(codigo):
    """Limpia un código dejando solo letras y números en mayúscula."""
    if codigo is None:
        return ""
    codigo = str(codigo).strip()
    if codigo == "" or codigo.lower() == "nan":
        return ""
    return re.sub(r'[^A-Z0-9]', '', codigo.upper())


def dividir_codigos(celda):
    """Separa una celda que puede traer varios códigos juntos (', ' '/' ';' salto de línea)."""
    if celda is None:
        return []
    texto = str(celda).strip()
    if texto == "" or texto.lower() == "nan":
        return []
    partes = re.split(r'[,/;\n]+', texto)
    return [p.strip() for p in partes if p.strip()]


def valor_o_vacio(valor):
    """Devuelve el valor de una celda como string, o '' si es None."""
    if valor is None:
        return ""
    return str(valor).strip()


def get_or_create_marca(nombre, tipo="PROVEEDOR"):
    nombre = nombre.strip().upper()
    c.execute("INSERT OR IGNORE INTO marcas (nombre, tipo) VALUES (?, ?)", (nombre, tipo))
    c.execute("SELECT id FROM marcas WHERE nombre = ?", (nombre,))
    return c.fetchone()[0]


def listar_catalogos_externos():
    c.execute("SELECT id, nombre, url FROM catalogos_externos ORDER BY nombre")
    return [dict(row) for row in c.fetchall()]


def agregar_catalogo_externo(nombre, url):
    nombre = nombre.strip()
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    with db_lock:
        c.execute("INSERT OR REPLACE INTO catalogos_externos (nombre, url) VALUES (?, ?)", (nombre, url))
        conn.commit()


def eliminar_catalogo_externo(catalogo_id):
    with db_lock:
        c.execute("DELETE FROM catalogos_externos WHERE id = ?", (catalogo_id,))
        conn.commit()


def depurar_huerfanos():
    """Borra productos que no tienen ninguna equivalencia vinculada (quedaron sueltos)."""
    with db_lock:
        c.execute("""
            DELETE FROM productos
            WHERE id NOT IN (SELECT DISTINCT producto_a_id FROM equivalencias)
              AND id NOT IN (SELECT DISTINCT producto_b_id FROM equivalencias)
        """)
        borrados = c.rowcount
        conn.commit()
    return borrados


def chequear_integridad_bd():
    """Revisa la base en busca de datos rotos o inconsistentes — sobre todo útil para detectar
    algo que se haya colado antes de que ciertas protecciones existieran, o algo que se rompió
    a mano editando la base fuera de la app."""
    resultados = []

    c.execute("""SELECT COUNT(*) FROM productos p
                 WHERE p.marca_id NOT IN (SELECT id FROM marcas)""")
    n = c.fetchone()[0]
    resultados.append({"Chequeo": "Productos con una marca que ya no existe", "Problemas": n})

    c.execute("""SELECT COUNT(*) FROM equivalencias e
                 WHERE e.producto_a_id NOT IN (SELECT id FROM productos)
                    OR e.producto_b_id NOT IN (SELECT id FROM productos)""")
    n = c.fetchone()[0]
    resultados.append({"Chequeo": "Equivalencias que apuntan a un producto que ya no existe", "Problemas": n})

    c.execute("""SELECT COUNT(*) FROM productos
                 WHERE codigo_raw IS NULL OR TRIM(codigo_raw) = ''
                    OR codigo_clean IS NULL OR TRIM(codigo_clean) = ''""")
    n = c.fetchone()[0]
    resultados.append({"Chequeo": "Productos con código vacío", "Problemas": n})

    c.execute("SELECT COUNT(*) FROM productos WHERE precio IS NOT NULL AND precio < 0")
    n = c.fetchone()[0]
    resultados.append({"Chequeo": "Productos con precio negativo", "Problemas": n})

    c.execute("SELECT COUNT(*) FROM productos WHERE stock IS NOT NULL AND stock < 0")
    n = c.fetchone()[0]
    resultados.append({"Chequeo": "Productos con stock negativo", "Problemas": n})

    c.execute("""SELECT codigo_clean, marca_id, COUNT(*) AS repetidos FROM productos
                 GROUP BY codigo_clean, marca_id HAVING COUNT(*) > 1""")
    duplicados = c.fetchall()
    resultados.append({"Chequeo": "Códigos duplicados dentro de la misma marca", "Problemas": len(duplicados)})

    c.execute("""SELECT COUNT(*) FROM vehiculos
                 WHERE km_registro IS NOT NULL AND km_actual IS NOT NULL AND km_actual < km_registro""")
    n = c.fetchone()[0]
    resultados.append({"Chequeo": "Vehículos con km actual menor al km de registro", "Problemas": n})

    c.execute("""SELECT COUNT(*) FROM historial_piezas h
                 WHERE h.vehiculo_id NOT IN (SELECT id FROM vehiculos)""")
    n = c.fetchone()[0]
    resultados.append({"Chequeo": "Piezas de historial que apuntan a un vehículo que ya no existe", "Problemas": n})

    return resultados


def listar_productos_sin_equivalencias(marca_filtro="Todas", limite=500):
    """Devuelve productos que no tienen ninguna equivalencia vinculada, sin borrarlos."""
    query = """
        SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
               m.nombre AS "Marca", m.tipo AS "Tipo"
        FROM productos p JOIN marcas m ON m.id = p.marca_id
        WHERE p.id NOT IN (SELECT DISTINCT producto_a_id FROM equivalencias)
          AND p.id NOT IN (SELECT DISTINCT producto_b_id FROM equivalencias)
    """
    params = []
    if marca_filtro and marca_filtro != "Todas":
        query += " AND UPPER(m.nombre) = ?"
        params.append(marca_filtro.upper())
    query += " ORDER BY m.nombre, p.codigo_raw LIMIT ?"
    params.append(limite)
    c.execute(query, params)
    return filas_a_listas(c)


def restaurar_backup(archivo_subido):
    """Reemplaza la base de datos actual por un archivo .db subido, de forma segura."""
    with db_lock:
        conn.commit()
        contenido = archivo_subido.read()
        conn.close()
        with open(DB_PATH, "wb") as f:
            f.write(contenido)
        # Muy importante: la conexión estaba cacheada por Streamlit. Si no limpiamos el
        # caché, la próxima vez que se pida se devolvería esta misma conexión ya cerrada.
        get_connection.clear()


def listar_marcas_con_conteo():
    c.execute("""SELECT m.id, m.nombre, m.tipo, COUNT(p.id) AS productos
                 FROM marcas m LEFT JOIN productos p ON p.marca_id = m.id
                 GROUP BY m.id ORDER BY m.nombre""")
    return c.fetchall()


def fusionar_marcas(marca_origen_id, marca_destino_id):
    """Mueve todos los productos de una marca a otra y borra la marca origen."""
    with db_lock:
        c.execute("UPDATE productos SET marca_id = ? WHERE marca_id = ?", (marca_destino_id, marca_origen_id))
        c.execute("DELETE FROM marcas WHERE id = ?", (marca_origen_id,))
        conn.commit()


def aumentar_precios_por_marca(marca_id, porcentaje):
    """Sube (o baja, con porcentaje negativo) todos los precios cargados de una marca."""
    with db_lock:
        c.execute(
            "UPDATE productos SET precio = ROUND(precio * (1 + ? / 100.0), 2) "
            "WHERE marca_id = ? AND precio IS NOT NULL",
            (porcentaje, marca_id)
        )
        afectados = c.rowcount
        conn.commit()
    return afectados


def listar_favoritos_stock_bajo(umbral=2):
    c.execute("""SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
                 m.nombre AS "Marca", p.precio AS "Precio", p.stock AS "Stock"
                 FROM productos p JOIN marcas m ON m.id = p.marca_id
                 WHERE p.favorito = 1 AND (p.stock IS NULL OR p.stock <= ?)
                 ORDER BY p.stock ASC, p.codigo_raw""", (umbral,))
    return filas_a_listas(c)


def registrar_busqueda_sin_resultado(termino):
    with db_lock:
        c.execute("INSERT INTO historial_busquedas (termino, sin_resultado) VALUES (?, 1)", (termino,))
        conn.commit()


def listar_busquedas_sin_resultado(limite=50):
    c.execute("""SELECT termino AS "Buscado", COUNT(*) AS "Veces", MAX(fecha) AS "Última vez"
                 FROM historial_busquedas WHERE sin_resultado = 1
                 GROUP BY termino ORDER BY COUNT(*) DESC, MAX(fecha) DESC LIMIT ?""", (limite,))
    return filas_a_listas(c)


def contar_productos_sin_equivalencias():
    c.execute("""
        SELECT COUNT(*) FROM productos
        WHERE id NOT IN (SELECT DISTINCT producto_a_id FROM equivalencias)
          AND id NOT IN (SELECT DISTINCT producto_b_id FROM equivalencias)
    """)
    return c.fetchone()[0]


def get_or_create_producto(raw, clean, desc, marca_id, imagen_url=None):
    c.execute(
        "INSERT OR IGNORE INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) VALUES (?, ?, ?, ?)",
        (raw, clean, desc, marca_id)
    )
    if desc:
        c.execute(
            "UPDATE productos SET descripcion = ?, codigo_raw = ? "
            "WHERE codigo_clean = ? AND marca_id = ? AND (descripcion IS NULL OR descripcion = '')",
            (desc, raw, clean, marca_id)
        )
    if imagen_url:
        c.execute(
            "UPDATE productos SET imagen_url = ? WHERE codigo_clean = ? AND marca_id = ?",
            (imagen_url, clean, marca_id)
        )
    c.execute("SELECT id FROM productos WHERE codigo_clean = ? AND marca_id = ?", (clean, marca_id))
    return c.fetchone()[0]


def filas_a_listas(cursor):
    """Convierte el resultado de un cursor (sqlite3.Row) en una lista de diccionarios."""
    return [dict(row) for row in cursor.fetchall()]


def buscar_por_codigo(clean_code, marca_filtro="Todas"):
    query = '''
    WITH RECURSIVE Red(id) AS (
        SELECT id FROM productos WHERE codigo_clean = ?
        UNION
        SELECT CASE WHEN eq.producto_a_id = re.id THEN eq.producto_b_id ELSE eq.producto_a_id END
        FROM equivalencias eq JOIN Red re ON (eq.producto_a_id = re.id OR eq.producto_b_id = re.id)
    )
    SELECT DISTINCT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
           m.nombre AS "Marca", m.tipo AS "Tipo", p.precio AS "Precio", p.stock AS "Stock",
           p.favorito AS "Favorito", p.imagen_url AS "Imagen", m.url_ficha_template AS "_template"
    FROM Red r JOIN productos p ON p.id = r.id JOIN marcas m ON m.id = p.marca_id
    '''
    params = [clean_code]
    if marca_filtro and marca_filtro != "Todas":
        query += " WHERE UPPER(m.nombre) = ?"
        params.append(marca_filtro.upper())
    query += " ORDER BY m.tipo, m.nombre;"

    with db_lock:
        c.execute(query, params)
        res = filas_a_listas(c)
        if not res:
            return res

        # Marca qué filas están verificadas con un link directo hacia el producto buscado,
        # y trae el nivel/nota de esa relación. Una sola consulta para todo el lote.
        c.execute("SELECT id FROM productos WHERE codigo_clean = ?", (clean_code,))
        origenes = [r["id"] for r in c.fetchall()]
        verificados_set = set()
        info_relacion = {}  # producto_id -> {"nivel": ..., "nota": ...}
        if origenes:
            result_ids = [f["ID"] for f in res]
            placeholders_o = ",".join("?" * len(origenes))
            placeholders_r = ",".join("?" * len(result_ids))
            c.execute(
                f"""SELECT producto_a_id, producto_b_id, verificada, nivel, nota FROM equivalencias
                    WHERE ((producto_a_id IN ({placeholders_o}) AND producto_b_id IN ({placeholders_r}))
                        OR (producto_b_id IN ({placeholders_o}) AND producto_a_id IN ({placeholders_r})))""",
                origenes + result_ids + origenes + result_ids
            )
            for a, b, verif, nivel, nota in c.fetchall():
                if verif:
                    verificados_set.add(a)
                    verificados_set.add(b)
                otro_id = b if a in origenes else a
                if nivel or nota:
                    info_relacion[otro_id] = {"nivel": nivel, "nota": nota}

    for fila in res:
        fila["Verificada"] = "✅" if fila["ID"] in verificados_set else ""
        rel = info_relacion.get(fila["ID"], {})
        fila["Nivel"] = rel.get("nivel") or ("Exacta" if fila["ID"] in verificados_set else "")
        fila["Nota"] = rel.get("nota") or ""
        template = fila.pop("_template", None)
        fila["Ficha"] = template.replace("{codigo}", quote(fila["Codigo"], safe="")) if template else ""
    return res


def incrementar_veces_buscado(clean_code):
    """Suma 1 al contador de búsquedas de un código (usado para la matriz ABC).
    Se llama únicamente desde el buscador público, no desde búsquedas internas de administración."""
    with db_lock:
        c.execute(
            "UPDATE productos SET veces_buscado = COALESCE(veces_buscado, 0) + 1 WHERE codigo_clean = ?",
            (clean_code,)
        )
        conn.commit()


def armar_lista_picking(codigos_texto):
    """Busca varios códigos a la vez y devuelve el resultado ordenado por ubicación en el
    depósito, para que el que arma el pedido camine en un solo recorrido en vez de ir y volver."""
    codigos = [sanitizar(x) for x in codigos_texto.split(",")]
    codigos = [x for x in codigos if x]
    if not codigos:
        return []
    placeholders = ",".join("?" * len(codigos))
    c.execute(f'''SELECT p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion", m.nombre AS "Marca",
                  p.ubicacion AS "Ubicación", p.stock AS "Stock"
                  FROM productos p JOIN marcas m ON m.id = p.marca_id
                  WHERE p.codigo_clean IN ({placeholders})''', codigos)
    resultado = filas_a_listas(c)
    resultado.sort(key=lambda r: (not r["Ubicación"], r["Ubicación"] or ""))
    return resultado


def _sql_sin_acentos(columna):
    """Arma una expresión SQL que le saca los acentos a una columna (funciona con mayúscula
    y minúscula, porque SQLite no toca letras acentuadas al hacer UPPER())."""
    reemplazos = [("á", "A"), ("Á", "A"), ("é", "E"), ("É", "E"), ("í", "I"), ("Í", "I"),
                  ("ó", "O"), ("Ó", "O"), ("ú", "U"), ("Ú", "U"), ("ñ", "N"), ("Ñ", "N")]
    expr = f"UPPER({columna})"
    for viejo, nuevo in reemplazos:
        expr = f"REPLACE({expr},'{viejo}','{nuevo}')"
    return expr


def buscar_por_texto(texto):
    """Busca por descripción de forma flexible: cada palabra tiene que aparecer en algún lado
    (descripción o código), sin importar el orden ni las tildes. Así 'ruleman delantero gol'
    encuentra 'Gol 1.6 - Ruleman de rueda delantero', y 'rótula' encuentra 'ROTULA' aunque el
    catálogo la tenga cargada sin tilde (frecuente en listas de proveedores)."""
    palabras = [normalizar_texto(p.strip()) for p in texto.upper().split() if p.strip()]
    if not palabras:
        return []
    # Compara contra la descripción/código sin tildes de ningún lado, para que no importe si
    # la búsqueda o el dato cargado tienen o no acentos.
    desc_sin_acentos = _sql_sin_acentos("p.descripcion")
    codigo_sin_acentos = _sql_sin_acentos("p.codigo_raw")
    condiciones = []
    params = []
    for palabra in palabras:
        condiciones.append(f"({desc_sin_acentos} LIKE ? OR {codigo_sin_acentos} LIKE ?)")
        like = f"%{palabra}%"
        params.extend([like, like])
    query = f'''
    SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
           m.nombre AS "Marca", m.tipo AS "Tipo", p.precio AS "Precio", p.stock AS "Stock",
           p.favorito AS "Favorito"
    FROM productos p JOIN marcas m ON m.id = p.marca_id
    WHERE {" AND ".join(condiciones)}
    ORDER BY m.nombre LIMIT 200;
    '''
    with db_lock:
        c.execute(query, params)
        return filas_a_listas(c)


# ============================================================
# COMBOS DE REPUESTOS RELACIONADOS (ej: correa de distribución -> kit + tensor + bomba de agua)
# ============================================================
def normalizar_texto(texto):
    """Mayúsculas y sin acentos, para poder comparar 'distribución' con 'distribucion'."""
    texto = texto or ""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return texto.upper().strip()


def buscar_combos_para_descripcion(descripcion):
    """Devuelve {disparador: [items]} para los disparadores que aparecen dentro de la descripción dada."""
    desc_norm = normalizar_texto(descripcion)
    c.execute("SELECT disparador, item FROM combos_sugeridos ORDER BY disparador, item")
    resultado = {}
    for row in c.fetchall():
        if normalizar_texto(row["disparador"]) in desc_norm:
            resultado.setdefault(row["disparador"], []).append(row["item"])
    return resultado


def listar_combos():
    c.execute("SELECT DISTINCT disparador FROM combos_sugeridos ORDER BY disparador")
    disparadores = [r["disparador"] for r in c.fetchall()]
    resultado = []
    for d in disparadores:
        c.execute("SELECT item FROM combos_sugeridos WHERE disparador = ? ORDER BY item", (d,))
        resultado.append({"disparador": d, "items": [r["item"] for r in c.fetchall()]})
    return resultado


def guardar_combo(disparador, items_lista):
    disparador = disparador.strip().lower()
    with db_lock:
        c.execute("DELETE FROM combos_sugeridos WHERE disparador = ?", (disparador,))
        c.executemany(
            "INSERT INTO combos_sugeridos (disparador, item) VALUES (?, ?)",
            [(disparador, item.strip()) for item in items_lista if item.strip()]
        )
        conn.commit()


def eliminar_combo(disparador):
    disparador = disparador.strip().lower()
    c.execute("SELECT item FROM combos_sugeridos WHERE disparador = ?", (disparador,))
    items = [r["item"] for r in c.fetchall()]
    if items:
        mover_a_papelera("combo", {"disparador": disparador, "items": items})
    with db_lock:
        c.execute("DELETE FROM combos_sugeridos WHERE disparador = ?", (disparador,))
        conn.commit()


def identificar_pieza_por_foto(imagen_bytes):
    """Le manda una foto a Gemini y le pide que identifique la pieza, extrayendo el código
    de forma estructurada (no solo texto libre) para poder buscarlo directo en el catálogo."""
    from google import genai
    from google.genai import types

    api_key = st.secrets.get("gemini_api_key") if hasattr(st, "secrets") else None
    if not api_key:
        return None, "No configuraste 'gemini_api_key' en Streamlit Cloud (Settings → Secrets)."

    try:
        client = genai.Client(api_key=api_key)
        prompt = (
            "Esta es una foto de un repuesto de auto tomada en un taller o local de repuestos. Tu "
            "tarea principal es ENCONTRAR EL CÓDIGO — mirá con mucha atención toda la superficie de "
            "la pieza: suelen estar grabados en bajorrelieve sobre el metal (a veces se ven mejor con "
            "el contraste de la luz, poco legibles a simple vista), impresos en una etiqueta pegada, "
            "moldeados en el plástico/goma, o troquelados en el borde. Es una combinación de letras y "
            "números, a veces con guiones, barras o puntos. Revisá TODOS los lados de la pieza que se "
            "vean en la foto antes de rendirte. Devolvé ÚNICAMENTE un JSON válido (sin texto extra, "
            'sin markdown), con esta forma exacta: {"codigo": "...", "marca_visible": "...", '
            '"tipo_pieza": "...", "confianza": "alta/media/baja"}. Si después de mirar con atención en '
            'serio no hay ningún código legible, dejá "codigo" como null — no inventes ni completes un '
            "código que no se vea con claridad."
        )
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=[
                prompt,
                types.Part.from_bytes(data=imagen_bytes, mime_type="image/jpeg"),
            ],
        )
        texto = response.text.strip()
        if texto.startswith("```"):
            texto = texto.split("```")[1]
            texto = texto[4:] if texto.lower().startswith("json") else texto
        datos = json.loads(texto)
        registrar_uso_ia("Identificar pieza por foto", True)
        return datos, None
    except json.JSONDecodeError:
        registrar_uso_ia("Identificar pieza por foto", False)
        return None, "No pude interpretar la respuesta — probá con una foto más clara y de más cerca."
    except Exception as e:
        registrar_uso_ia("Identificar pieza por foto", False)
        return None, traducir_error_gemini(e)


def extraer_datos_cedula(imagen_bytes):
    """Lee una foto de cédula verde/azul o título del auto y extrae patente, marca, modelo, año
    y motorización con Gemini. SIEMPRE hay que revisar antes de guardar — el OCR puede confundir
    caracteres parecidos (0/O, 1/I) y en la patente o el VIN eso es grave."""
    from google import genai
    from google.genai import types
    import json

    api_key = st.secrets.get("gemini_api_key") if hasattr(st, "secrets") else None
    if not api_key:
        return None, "No configuraste 'gemini_api_key' en Streamlit Cloud (Settings → Secrets)."

    try:
        client = genai.Client(api_key=api_key)
        prompt = (
            "Esta es una foto de una cédula verde/azul o título de un vehículo argentino. Extraé "
            "ÚNICAMENTE un JSON válido (sin texto extra, sin markdown), con esta forma exacta: "
            '{"patente": "...", "marca": "...", "modelo": "...", "anio": "...", "motorizacion": "..."}. '
            "Si no podés leer algún campo con claridad, dejalo como null en vez de adivinar. No inventes datos."
        )
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=[prompt, types.Part.from_bytes(data=imagen_bytes, mime_type="image/jpeg")],
        )
        texto = response.text.strip()
        if texto.startswith("```"):
            texto = texto.split("```")[1]
            texto = texto[4:] if texto.lower().startswith("json") else texto
        datos = json.loads(texto)
        registrar_uso_ia("Leer cédula/título", True)
        return datos, None
    except json.JSONDecodeError:
        registrar_uso_ia("Leer cédula/título", False)
        return None, "No pude interpretar la respuesta como datos del vehículo — probá con una foto más clara."
    except Exception as e:
        registrar_uso_ia("Leer cédula/título", False)
        return None, traducir_error_gemini(e)


def transcribir_audio(audio_bytes, mime_type="audio/wav"):
    """Transcribe un audio a texto con Gemini — esto es solo 'hablar en vez de tipear', no un
    asistente conversacional: el texto transcripto se busca con el buscador normal de siempre."""
    from google import genai
    from google.genai import types

    api_key = st.secrets.get("gemini_api_key") if hasattr(st, "secrets") else None
    if not api_key:
        return None, "No configuraste 'gemini_api_key' en Streamlit Cloud (Settings → Secrets)."

    try:
        client = genai.Client(api_key=api_key)
        prompt = "Transcribí exactamente lo que se dice en este audio, en español. Devolvé solo el texto transcripto, nada más — sin comillas, sin comentarios."
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=[prompt, types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)],
        )
        registrar_uso_ia("Búsqueda por voz", True)
        return response.text.strip(), None
    except Exception as e:
        registrar_uso_ia("Búsqueda por voz", False)
        return None, traducir_error_gemini(e)


def leer_remito_por_foto(imagen_bytes):
    """Le pide a Gemini que lea un remito/factura de proveedor y devuelva los ítems en JSON.
    Devuelve (lista_items, error) — lista_items siempre queda para revisión manual antes de
    tocar el stock, la IA nunca actualiza nada por sí sola."""
    from google import genai
    from google.genai import types
    import json

    api_key = st.secrets.get("gemini_api_key") if hasattr(st, "secrets") else None
    if not api_key:
        return None, "No configuraste 'gemini_api_key' en Streamlit Cloud (Settings → Secrets)."

    try:
        client = genai.Client(api_key=api_key)
        prompt = (
            "Esta es una foto de un remito o factura de un proveedor de repuestos. Extraé cada ítem "
            "listado y devolvé ÚNICAMENTE un JSON válido (sin texto extra, sin markdown), con esta forma "
            'exacta: [{"codigo": "...", "descripcion": "...", "cantidad": 0, "costo_unitario": 0.0}, ...]. '
            "Si no podés leer algún campo con claridad, dejalo como null. No inventes datos que no estén "
            "visibles en la imagen."
        )
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=[prompt, types.Part.from_bytes(data=imagen_bytes, mime_type="image/jpeg")],
        )
        texto = response.text.strip()
        if texto.startswith("```"):
            texto = texto.split("```")[1]
            texto = texto[4:] if texto.lower().startswith("json") else texto
        items = json.loads(texto)
        if not isinstance(items, list):
            registrar_uso_ia("Leer remito por foto", False)
            return None, "Gemini no devolvió una lista de ítems reconocible."
        registrar_uso_ia("Leer remito por foto", True)
        return items, None
    except json.JSONDecodeError:
        registrar_uso_ia("Leer remito por foto", False)
        return None, "No pude interpretar la respuesta como una lista de ítems — probá con una foto más clara."
    except Exception as e:
        registrar_uso_ia("Leer remito por foto", False)
        return None, traducir_error_gemini(e)


def cotejar_items_remito(items):
    """Para cada ítem leído del remito, busca si el código ya existe en el catálogo."""
    resultado = []
    for item in items:
        codigo = (item.get("codigo") or "").strip()
        clean = sanitizar(codigo) if codigo else ""
        producto_id, marca_actual, stock_actual = None, None, None
        if clean:
            c.execute("""SELECT p.id, m.nombre AS marca, p.stock FROM productos p
                         JOIN marcas m ON m.id = p.marca_id WHERE p.codigo_clean = ? LIMIT 1""", (clean,))
            fila = c.fetchone()
            if fila:
                producto_id, marca_actual, stock_actual = fila["id"], fila["marca"], fila["stock"]
        resultado.append({
            "Código": codigo or "(sin leer)",
            "Descripción": item.get("descripcion") or "",
            "Cantidad": item.get("cantidad") if item.get("cantidad") is not None else 0,
            "Costo unitario": item.get("costo_unitario") if item.get("costo_unitario") is not None else 0.0,
            "_producto_id": producto_id,
            "Coincide con": f"{marca_actual} (stock actual: {stock_actual})" if producto_id else "❌ No está en el catálogo",
        })
    return resultado


def aplicar_carga_remito(items_cotejados):
    """Suma la cantidad recibida al stock de los ítems que sí coinciden con un producto ya cargado."""
    actualizados = 0
    with db_lock:
        for item in items_cotejados:
            if item.get("_producto_id"):
                cantidad = item.get("Cantidad") or 0
                c.execute("UPDATE productos SET stock = COALESCE(stock, 0) + ? WHERE id = ?",
                          (cantidad, item["_producto_id"]))
                actualizados += 1
        conn.commit()
    return actualizados


def actualizar_precio_stock(producto_id, precio, stock):
    with db_lock:
        c.execute("SELECT precio FROM productos WHERE id = ?", (producto_id,))
        fila = c.fetchone()
        precio_anterior = fila["precio"] if fila else None
        c.execute("UPDATE productos SET precio = ?, stock = ? WHERE id = ?", (precio, stock, producto_id))
        # Solo se guarda un registro nuevo en el historial si el precio realmente cambió
        # (evita ensuciar el historial cada vez que se toca el stock sin tocar el precio).
        if precio_anterior != precio:
            c.execute("INSERT INTO historial_precios (producto_id, precio) VALUES (?, ?)", (producto_id, precio))
        conn.commit()


def historial_precio_producto(producto_id, limite=50):
    c.execute("""SELECT precio AS "Precio", fecha AS "Fecha" FROM historial_precios
                 WHERE producto_id = ? ORDER BY fecha DESC LIMIT ?""", (producto_id, limite))
    return filas_a_listas(c)


def solicitar_reposicion(producto_id):
    with db_lock:
        c.execute(
            "INSERT INTO pedidos_reposicion (producto_id, veces_solicitado, ultimo_solicitado_por, ultima_fecha, estado) "
            "VALUES (?, 1, ?, datetime('now'), 'pendiente') "
            "ON CONFLICT(producto_id) DO UPDATE SET veces_solicitado = veces_solicitado + 1, "
            "ultimo_solicitado_por = excluded.ultimo_solicitado_por, ultima_fecha = excluded.ultima_fecha, "
            "estado = 'pendiente'",
            (producto_id, obtener_usuario_actual())
        )
        conn.commit()


def listar_pedidos_reposicion(estado="pendiente"):
    c.execute("""SELECT pr.id AS "ID", p.id AS "ProductoID", p.codigo_raw AS "Codigo",
                 p.descripcion AS "Descripcion", m.nombre AS "Marca", p.stock AS "Stock actual",
                 pr.veces_solicitado AS "Veces pedido", pr.ultimo_solicitado_por AS "Último en pedirlo",
                 pr.ultima_fecha AS "Fecha"
                 FROM pedidos_reposicion pr
                 JOIN productos p ON p.id = pr.producto_id
                 JOIN marcas m ON m.id = p.marca_id
                 WHERE pr.estado = ?
                 ORDER BY pr.veces_solicitado DESC, pr.ultima_fecha DESC""", (estado,))
    return filas_a_listas(c)


def marcar_pedido_resuelto(pedido_id):
    with db_lock:
        c.execute("UPDATE pedidos_reposicion SET estado = 'resuelto' WHERE id = ?", (pedido_id,))
        conn.commit()


def descartar_pedido_reposicion(pedido_id):
    with db_lock:
        c.execute("DELETE FROM pedidos_reposicion WHERE id = ?", (pedido_id,))
        conn.commit()


def alternar_favorito(producto_id, valor):
    with db_lock:
        c.execute("UPDATE productos SET favorito = ? WHERE id = ?", (1 if valor else 0, producto_id))
        conn.commit()


def listar_favoritos():
    c.execute("""SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
                 m.nombre AS "Marca", p.precio AS "Precio", p.stock AS "Stock"
                 FROM productos p JOIN marcas m ON m.id = p.marca_id
                 WHERE p.favorito = 1 ORDER BY p.codigo_raw""")
    return filas_a_listas(c)


def obtener_config(clave, default=""):
    c.execute("SELECT valor FROM configuracion WHERE clave = ?", (clave,))
    fila = c.fetchone()
    return fila["valor"] if fila and fila["valor"] is not None else default


def guardar_config(clave, valor):
    with db_lock:
        c.execute(
            "INSERT INTO configuracion (clave, valor) VALUES (?, ?) "
            "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
            (clave, valor)
        )
        conn.commit()


def obtener_usuario_actual():
    """Nombre que identifica a la persona para su historial personal: si está logueada como
    admin usa ese nombre, si no usa el que puso al entrar, o 'Invitado' si no puso nada."""
    return st.session_state.get("admin_nombre") or st.session_state.get("usuario_nombre") or "Invitado"


def registrar_uso_ia(funcion, exito):
    with db_lock:
        c.execute("INSERT INTO uso_ia (funcion, usuario, exito) VALUES (?, ?, ?)",
                   (funcion, obtener_usuario_actual(), 1 if exito else 0))
        conn.commit()


def traducir_error_gemini(e):
    """Convierte el JSON crudo de error de la API de Gemini en un mensaje legible en español.
    El nivel gratuito de estas funciones tiene un límite MUY chico (a veces 5 consultas por
    minuto compartidas entre todos los empleados) — esto es lo más común que se va a chocar."""
    texto_error = str(e)
    if "RESOURCE_EXHAUSTED" in texto_error or "429" in texto_error or "quota" in texto_error.lower():
        return (
            "⏳ Se alcanzó el límite de consultas gratuitas de la IA por ahora (es un límite por "
            "minuto, compartido entre todos los que usan la app). Esperá un minuto y probá de nuevo — "
            "no es un error, es solo que hay que esperar a que se libere cupo."
        )
    return f"Error consultando a Gemini: {texto_error}"


def resumen_uso_ia(dias=30):
    c.execute("""SELECT funcion, COUNT(*) AS total, SUM(exito) AS exitosos
                 FROM uso_ia WHERE fecha >= datetime('now', ?) GROUP BY funcion ORDER BY total DESC""",
              (f"-{dias} days",))
    return [{"Función": r["funcion"], "Usos": r["total"], "Exitosos": r["exitosos"],
              "Con error": r["total"] - r["exitosos"]} for r in c.fetchall()]


def mover_a_papelera(tipo, datos_dict):
    with db_lock:
        c.execute("INSERT INTO papelera (tipo, datos_json, eliminado_por) VALUES (?, ?, ?)",
                   (tipo, json.dumps(datos_dict, ensure_ascii=False), obtener_usuario_actual()))
        conn.commit()


def eliminar_marca_con_papelera(nombre_marca):
    """Guarda la marca completa (con todos sus productos y las equivalencias que los tocan)
    en la papelera antes de borrarla — es la operación más destructiva de la app, así que
    ahora también tiene red de seguridad."""
    c.execute("SELECT * FROM marcas WHERE nombre = ?", (nombre_marca,))
    marca_row = c.fetchone()
    if not marca_row:
        return False
    marca_id = marca_row["id"]
    c.execute("SELECT * FROM productos WHERE marca_id = ?", (marca_id,))
    productos_rows = [dict(r) for r in c.fetchall()]
    producto_ids = [p["id"] for p in productos_rows]
    equivalencias_rows = []
    if producto_ids:
        placeholders = ",".join("?" * len(producto_ids))
        c.execute(
            f"SELECT * FROM equivalencias WHERE producto_a_id IN ({placeholders}) "
            f"OR producto_b_id IN ({placeholders})",
            producto_ids + producto_ids
        )
        equivalencias_rows = [dict(r) for r in c.fetchall()]

    snapshot = {"marca": dict(marca_row), "productos": productos_rows, "equivalencias": equivalencias_rows}
    mover_a_papelera("marca", snapshot)

    with db_lock:
        c.execute("DELETE FROM marcas WHERE id = ?", (marca_id,))
        conn.commit()
    return True


def listar_papelera():
    c.execute("""SELECT id AS "ID", tipo AS "Tipo", datos_json, eliminado_por AS "Eliminado por",
                 eliminado_en AS "Fecha" FROM papelera ORDER BY id DESC LIMIT 100""")
    filas = []
    for row in c.fetchall():
        detalle = ""
        if row["Tipo"] == "marca":
            datos = json.loads(row["datos_json"])
            detalle = f"{datos['marca']['nombre']} ({len(datos['productos'])} producto(s))"
        elif row["Tipo"] == "producto":
            datos = json.loads(row["datos_json"])
            detalle = datos.get("codigo_raw", "")
        elif row["Tipo"] == "combo":
            datos = json.loads(row["datos_json"])
            detalle = datos.get("disparador", "")
        elif row["Tipo"] == "alias":
            datos = json.loads(row["datos_json"])
            detalle = datos.get("nombre", "")
        filas.append({"ID": row["ID"], "Tipo": row["Tipo"], "Detalle": detalle,
                       "Eliminado por": row["Eliminado por"], "Fecha": row["Fecha"]})
    return filas


def vaciar_papelera_antigua(dias=30):
    """Borra en forma permanente lo que ya lleva más de `dias` en la papelera."""
    with db_lock:
        c.execute("DELETE FROM papelera WHERE eliminado_en < datetime('now', ?)", (f"-{dias} days",))
        conn.commit()


def restaurar_de_papelera(item_id):
    c.execute("SELECT tipo, datos_json FROM papelera WHERE id = ?", (item_id,))
    row = c.fetchone()
    if not row:
        return False, "No se encontró ese ítem en la papelera (puede que ya se haya restaurado)."
    tipo, datos = row["tipo"], json.loads(row["datos_json"])
    with db_lock:
        try:
            if tipo == "combo":
                for item in datos["items"]:
                    c.execute("INSERT INTO combos_sugeridos (disparador, item) VALUES (?, ?)",
                              (datos["disparador"], item))
            elif tipo == "alias":
                c.execute(
                    "INSERT INTO alias_transferencia (nombre, alias, cbu, titular) VALUES (?, ?, ?, ?)",
                    (datos["nombre"], datos["alias"], datos["cbu"], datos["titular"])
                )
            elif tipo == "producto":
                columnas = ", ".join(datos.keys())
                placeholders = ", ".join("?" * len(datos))
                c.execute(f"INSERT INTO productos ({columnas}) VALUES ({placeholders})", list(datos.values()))
            elif tipo == "marca":
                marca = datos["marca"]
                columnas_marca = ", ".join(marca.keys())
                placeholders_marca = ", ".join("?" * len(marca))
                c.execute(f"INSERT INTO marcas ({columnas_marca}) VALUES ({placeholders_marca})",
                          list(marca.values()))
                for producto in datos["productos"]:
                    columnas_p = ", ".join(producto.keys())
                    placeholders_p = ", ".join("?" * len(producto))
                    c.execute(f"INSERT INTO productos ({columnas_p}) VALUES ({placeholders_p})",
                              list(producto.values()))
                for equiv in datos["equivalencias"]:
                    columnas_e = ", ".join(equiv.keys())
                    placeholders_e = ", ".join("?" * len(equiv))
                    c.execute(f"INSERT INTO equivalencias ({columnas_e}) VALUES ({placeholders_e})",
                              list(equiv.values()))
            else:
                return False, f"No sé cómo restaurar el tipo '{tipo}'."
            c.execute("DELETE FROM papelera WHERE id = ?", (item_id,))
            conn.commit()
            return True, None
        except Exception as e:
            conn.rollback()
            return False, f"No se pudo restaurar: {e}"


def guardar_busqueda(termino):
    with db_lock:
        c.execute("INSERT INTO historial_busquedas (termino, usuario) VALUES (?, ?)",
                   (termino, obtener_usuario_actual()))
        conn.commit()


def historial_reciente(limite=10):
    """Solo las búsquedas de la persona actual — antes mezclaba las de todos los empleados."""
    c.execute("""SELECT DISTINCT termino FROM historial_busquedas WHERE usuario = ?
                 ORDER BY id DESC LIMIT ?""", (obtener_usuario_actual(), limite))
    return [r["termino"] for r in c.fetchall()]


def similitud(a, b):
    """Similitud simple entre dos strings (0 a 1) usando coincidencia de secuencia."""
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()


def detectar_posibles_duplicados(marca_id, umbral=0.87, limite_productos=1500):
    """Busca códigos parecidos pero no idénticos dentro de la misma marca (posibles errores de tipeo).
    Es una comparación O(n²), así que por seguridad no corre si la marca tiene demasiados productos."""
    c.execute("SELECT id, codigo_raw, codigo_clean FROM productos WHERE marca_id = ?", (marca_id,))
    productos = c.fetchall()
    if len(productos) > limite_productos:
        return None  # catálogo muy grande: se omite para no colgar la app
    sospechosos = []
    vistos = set()
    for i in range(len(productos)):
        for j in range(i + 1, len(productos)):
            a, b = productos[i], productos[j]
            if a["codigo_clean"] == b["codigo_clean"]:
                continue
            par = tuple(sorted([a["id"], b["id"]]))
            if par in vistos:
                continue
            if similitud(a["codigo_clean"], b["codigo_clean"]) >= umbral:
                sospechosos.append({"Código 1": a["codigo_raw"], "Código 2": b["codigo_raw"]})
                vistos.add(par)
    return sospechosos


def quitar_id(filas):
    """Quita la clave ID de cada diccionario para mostrar en pantalla."""
    return [{k: v for k, v in f.items() if k != "ID"} for f in filas]


def to_excel_bytes(filas, columnas=None):
    """Genera un archivo .xlsx en memoria a partir de una lista de diccionarios."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Resultados"
    if not filas:
        wb.save(buf := io.BytesIO())
        return buf.getvalue()
    columnas = columnas or list(filas[0].keys())
    ws.append(columnas)
    for fila in filas:
        ws.append([fila.get(col, "") for col in columnas])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def listar_alias_transferencia():
    c.execute("""SELECT id AS "ID", nombre AS "Nombre", alias AS "Alias",
                 cbu AS "CBU", titular AS "Titular",
                 CASE WHEN qr_real_blob IS NOT NULL THEN 1 ELSE 0 END AS "TieneQrReal"
                 FROM alias_transferencia ORDER BY nombre""")
    return filas_a_listas(c)


def guardar_alias_transferencia(nombre, alias, cbu, titular, alias_id=None, qr_real_bytes=None):
    with db_lock:
        if alias_id:
            if qr_real_bytes is not None:
                c.execute(
                    "UPDATE alias_transferencia SET nombre=?, alias=?, cbu=?, titular=?, qr_real_blob=? WHERE id=?",
                    (nombre.strip(), alias.strip(), cbu.strip(), titular.strip(), qr_real_bytes, alias_id)
                )
            else:
                c.execute(
                    "UPDATE alias_transferencia SET nombre=?, alias=?, cbu=?, titular=? WHERE id=?",
                    (nombre.strip(), alias.strip(), cbu.strip(), titular.strip(), alias_id)
                )
        else:
            c.execute(
                "INSERT INTO alias_transferencia (nombre, alias, cbu, titular, qr_real_blob) VALUES (?, ?, ?, ?, ?)",
                (nombre.strip(), alias.strip(), cbu.strip(), titular.strip(), qr_real_bytes)
            )
        conn.commit()


def obtener_qr_real(alias_id):
    c.execute("SELECT qr_real_blob FROM alias_transferencia WHERE id = ?", (alias_id,))
    fila = c.fetchone()
    return fila["qr_real_blob"] if fila else None


def eliminar_qr_real(alias_id):
    with db_lock:
        c.execute("UPDATE alias_transferencia SET qr_real_blob = NULL WHERE id = ?", (alias_id,))
        conn.commit()


def eliminar_alias_transferencia(alias_id):
    c.execute("SELECT nombre, alias, cbu, titular, qr_real_blob FROM alias_transferencia WHERE id = ?", (alias_id,))
    fila = c.fetchone()
    if fila:
        mover_a_papelera("alias", {
            "nombre": fila["nombre"], "alias": fila["alias"], "cbu": fila["cbu"], "titular": fila["titular"]
        })
        # El QR real (si tenía) no se puede guardar en la papelera como texto — si restaurás este
        # alias vas a tener que volver a subirlo.
    with db_lock:
        c.execute("DELETE FROM alias_transferencia WHERE id = ?", (alias_id,))
        conn.commit()



def generar_qr_bytes(texto):
    """Genera una imagen QR (PNG) con el texto dado — el alias/CBU/titular como texto plano.
    No es un pago directo por QR (eso requiere ser comercio adherido a un sistema de cobro real):
    al escanearlo, la mayoría de las apps de billetera muestran ese texto para que el
    cliente confirme la transferencia, en vez de tener que tipear el alias a mano."""
    import qrcode
    img = qrcode.make(texto)
    salida = io.BytesIO()
    img.save(salida, format="PNG")
    return salida.getvalue()


def generar_pdf_cotizacion(lista_productos, incluir_precio=True, incluir_stock=False, alias_qr=None, qr_real_bytes=None):
    """Genera un PDF simple de cotización a partir de la lista armada para WhatsApp.
    Si se pasa alias_qr (un dict con nombre/alias/cbu/titular), agrega un QR con esos datos
    para transferencia — el cliente lo escanea y ve el alias/CBU listo para pegar, sin tipear."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Equivalencias El Chavo - Cotizacion", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Fecha: {datetime.now():%d/%m/%Y %H:%M}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    def limpiar(texto):
        # fpdf2 con fuentes básicas no soporta todo unicode; reemplazamos lo problemático
        return str(texto).encode("latin-1", "replace").decode("latin-1")

    for item in lista_productos:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, limpiar(f"Codigo buscado: {item['codigo_buscado']}"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        for fila in item["resultados"]:
            linea = f"  - {fila['Marca']}: {fila['Codigo']}"
            if fila.get("Descripcion"):
                linea += f" - {fila['Descripcion']}"
            extras = []
            if incluir_precio and fila.get("Precio"):
                extras.append(f"${fila['Precio']:,.0f}")
            if incluir_stock and fila.get("Stock") is not None:
                extras.append(f"Stock: {fila['Stock']}")
            if extras:
                linea += " (" + " / ".join(extras) + ")"
            pdf.multi_cell(0, 6, limpiar(linea), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    if alias_qr:
        qr_bytes = qr_real_bytes if qr_real_bytes else generar_qr_bytes(
            f"Alias: {alias_qr['Alias']}\nCBU: {alias_qr['CBU']}\nTitular: {alias_qr['Titular']}"
        )
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, limpiar(f"Transferir a: {alias_qr['Nombre']}"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, limpiar(f"Alias: {alias_qr['Alias']}  /  CBU: {alias_qr['CBU']}  /  Titular: {alias_qr['Titular']}"),
                       new_x="LMARGIN", new_y="NEXT")
        pdf.image(io.BytesIO(qr_bytes), w=35)
        pdf.set_font("Helvetica", "I", 8)
        if qr_real_bytes:
            pdf.multi_cell(0, 4, "Escaneá el QR con tu app de Mercado Pago/MODO/banco para transferir.",
                           new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.multi_cell(0, 4, "Escaneá el QR para ver el alias/CBU y transferir desde tu banco o billetera virtual.",
                           new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


def generar_pdf_ficha_vehiculo(vehiculo, km_calc, alertas, proyeccion, historial):
    """Genera un PDF con el resumen de la ficha digital del vehículo, para entregarle al cliente."""
    from fpdf import FPDF

    def limpiar(texto):
        return str(texto).encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Equivalencias El Chavo - Ficha del vehiculo", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Fecha: {datetime.now():%d/%m/%Y %H:%M}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, limpiar(f"Patente: {vehiculo['patente']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    nombre_auto = f"{vehiculo.get('marca_auto') or ''} {vehiculo.get('modelo_auto') or ''}".strip()
    if nombre_auto:
        pdf.cell(0, 6, limpiar(nombre_auto), new_x="LMARGIN", new_y="NEXT")
    if vehiculo.get("cliente_nombre"):
        pdf.cell(0, 6, limpiar(f"Cliente: {vehiculo['cliente_nombre']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "Kilometraje", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    km_reg = vehiculo.get("km_registro")
    km_act = vehiculo.get("km_actual")
    pdf.cell(0, 6, limpiar(f"Km de registro: {km_reg if km_reg is not None else '-'}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, limpiar(f"Km actual: {km_act if km_act is not None else '-'}"), new_x="LMARGIN", new_y="NEXT")
    if km_calc.get("km_recorridos") is not None:
        pdf.cell(0, 6, limpiar(f"Km recorridos: {km_calc['km_recorridos']:,}"), new_x="LMARGIN", new_y="NEXT")
    if km_calc.get("promedio_mensual") is not None:
        pdf.cell(0, 6, limpiar(f"Promedio aproximado: {km_calc['promedio_mensual']:,} km/mes"),
                  new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    if alertas:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 7, "Alertas de mantenimiento", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        for a in alertas:
            linea = f"- {a['Pieza']} ({a.get('Marca') or 's/marca'}): {a['% consumido']}% de su vida util consumida"
            pdf.multi_cell(0, 6, limpiar(linea), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    if proyeccion:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 7, "Proyeccion de mantenimiento", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        for p in proyeccion:
            linea = (f"- {p['Pieza']}: cambiada {p['Veces cambiada']} vez/veces, "
                      f"deberia {p['Veces que debería (según km)']} - atraso: {p['Atraso estimado']}")
            pdf.multi_cell(0, 6, limpiar(linea), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    if historial:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 7, "Historial de piezas cambiadas", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        for h in historial:
            linea = f"- {h['Pieza']} ({h.get('Marca') or ''}) - {h.get('Fecha') or ''} - {h.get('Km instalación') or '-'} km"
            pdf.multi_cell(0, 6, limpiar(linea), new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


def leer_excel(archivo, nrows=None):
    """Lee un archivo Excel, CSV o PDF (subido o por ruta) y devuelve una lista de listas (filas)."""
    nombre = archivo if isinstance(archivo, str) else getattr(archivo, "name", "")
    nombre_lower = nombre.lower()

    if nombre_lower.endswith(".csv"):
        import csv as csv_module
        if isinstance(archivo, str):
            texto = open(archivo, "r", encoding="utf-8-sig").read()
        else:
            archivo.seek(0)
            texto = archivo.read().decode("utf-8-sig")
        delimitador = ";" if texto.count(";") > texto.count(",") else ","
        filas = []
        for i, row in enumerate(csv_module.reader(texto.splitlines(), delimiter=delimitador)):
            filas.append(row)
            if nrows and i + 1 >= nrows:
                break
        return filas

    if nombre_lower.endswith(".pdf"):
        import pdfplumber
        filas = []
        with pdfplumber.open(archivo) as pdf:
            for pagina in pdf.pages:
                tabla = pagina.extract_table()
                if tabla:
                    for row in tabla:
                        filas.append([c if c is not None else "" for c in row])
                        if nrows and len(filas) >= nrows:
                            return filas
        return filas

    wb = load_workbook(archivo, data_only=True, read_only=True)
    ws = wb.active
    filas = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        filas.append(list(row))
        if nrows and i + 1 >= nrows:
            break
    return filas


# ============================================================
# IDEA 2: FICHA DIGITAL DEL VEHÍCULO (patente + historial de piezas)
# ============================================================
def get_or_create_vehiculo(patente, cliente_nombre="", cliente_telefono="", marca_auto="", modelo_auto="",
                            km_actual=None, anio="", motorizacion=""):
    patente = patente.strip().upper()
    with db_lock:
        c.execute("SELECT id FROM vehiculos WHERE patente = ?", (patente,))
        row = c.fetchone()
        if row:
            vid = row["id"]
            c.execute(
                "UPDATE vehiculos SET "
                "cliente_nombre = COALESCE(NULLIF(?, ''), cliente_nombre), "
                "cliente_telefono = COALESCE(NULLIF(?, ''), cliente_telefono), "
                "marca_auto = COALESCE(NULLIF(?, ''), marca_auto), "
                "modelo_auto = COALESCE(NULLIF(?, ''), modelo_auto), "
                "anio = COALESCE(NULLIF(?, ''), anio), "
                "motorizacion = COALESCE(NULLIF(?, ''), motorizacion), "
                "km_actual = COALESCE(?, km_actual), "
                "km_registro = COALESCE(km_registro, ?), "  # solo se fija si todavía no tenía uno
                "km_actualizado_fecha = CASE WHEN ? IS NOT NULL THEN datetime('now') ELSE km_actualizado_fecha END "
                "WHERE id = ?",
                (cliente_nombre.strip(), cliente_telefono.strip(), marca_auto.strip(), modelo_auto.strip(),
                 anio.strip(), motorizacion.strip(), km_actual, km_actual, km_actual, vid)
            )
        else:
            c.execute(
                "INSERT INTO vehiculos (patente, cliente_nombre, cliente_telefono, marca_auto, modelo_auto, "
                "anio, motorizacion, km_registro, km_actual, km_actualizado_fecha) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
                (patente, cliente_nombre.strip(), cliente_telefono.strip(), marca_auto.strip(),
                 modelo_auto.strip(), anio.strip(), motorizacion.strip(), km_actual, km_actual)
            )
            c.execute("SELECT id FROM vehiculos WHERE patente = ?", (patente,))
            vid = c.fetchone()["id"]
        conn.commit()
    return vid


def actualizar_km_registro(vehiculo_id, km_registro):
    """Corrige manualmente el km de registro (por si se cargó mal la primera vez)."""
    with db_lock:
        c.execute("UPDATE vehiculos SET km_registro = ? WHERE id = ?", (km_registro, vehiculo_id))
        conn.commit()


def buscar_vehiculo(patente):
    c.execute("SELECT * FROM vehiculos WHERE patente = ?", (patente.strip().upper(),))
    row = c.fetchone()
    return dict(row) if row else None


def calcular_km_recorridos(vehiculo):
    """A partir del km de registro y el km actual, calcula km recorridos y el promedio
    aproximado por mes (usando la fecha de creación de la ficha como punto de partida)."""
    km_registro = vehiculo.get("km_registro")
    km_actual = vehiculo.get("km_actual")
    resultado = {"km_recorridos": None, "promedio_mensual": None, "dias_transcurridos": None}
    if km_registro is None or km_actual is None:
        return resultado
    recorridos = km_actual - km_registro
    if recorridos < 0:
        return resultado
    resultado["km_recorridos"] = recorridos

    creado = vehiculo.get("created_at")
    if creado:
        try:
            fecha_creado = datetime.strptime(creado[:19], "%Y-%m-%d %H:%M:%S")
            dias = max((datetime.now() - fecha_creado).days, 1)
            resultado["dias_transcurridos"] = dias
            resultado["promedio_mensual"] = round(recorridos / dias * 30)
        except (ValueError, TypeError):
            pass
    return resultado


def agregar_pieza_historial(vehiculo_id, descripcion, marca_pieza, codigo_pieza, km_instalacion, vida_util_km, nota):
    with db_lock:
        c.execute(
            "INSERT INTO historial_piezas (vehiculo_id, descripcion_pieza, marca_pieza, codigo_pieza, "
            "km_instalacion, vida_util_km, nota) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (vehiculo_id, descripcion.strip(), marca_pieza.strip(), codigo_pieza.strip(),
             km_instalacion, vida_util_km, nota.strip())
        )
        conn.commit()


def listar_historial_vehiculo(vehiculo_id):
    c.execute("""SELECT id AS "ID", descripcion_pieza AS "Pieza", marca_pieza AS "Marca",
                 codigo_pieza AS "Código", km_instalacion AS "Km instalación",
                 vida_util_km AS "Vida útil (km)", fecha_instalacion AS "Fecha", nota AS "Nota"
                 FROM historial_piezas WHERE vehiculo_id = ? ORDER BY fecha_instalacion DESC""", (vehiculo_id,))
    return filas_a_listas(c)


def calcular_proyeccion_mantenimiento(vehiculo_id, km_recorridos):
    """Para cada tipo de pieza con vida útil cargada, compara cuántas veces se cambió
    realmente contra cuántas veces debería haberse cambiado según los km recorridos totales
    del vehículo desde que se registró."""
    if km_recorridos is None:
        return []
    c.execute("""SELECT descripcion_pieza, COUNT(*) AS veces_reales, AVG(vida_util_km) AS vida_util_prom
                 FROM historial_piezas
                 WHERE vehiculo_id = ? AND vida_util_km IS NOT NULL AND vida_util_km > 0
                 GROUP BY UPPER(descripcion_pieza)""", (vehiculo_id,))
    proyeccion = []
    for row in c.fetchall():
        vida_util_prom = row["vida_util_prom"]
        veces_esperadas = int(km_recorridos // vida_util_prom)
        atraso = veces_esperadas - row["veces_reales"]
        proyeccion.append({
            "Pieza": row["descripcion_pieza"],
            "Vida útil prom. (km)": round(vida_util_prom),
            "Veces cambiada": row["veces_reales"],
            "Veces que debería (según km)": veces_esperadas,
            "Atraso estimado": max(atraso, 0),
        })
    return sorted(proyeccion, key=lambda p: -p["Atraso estimado"])


def listar_vehiculos_atrasados():
    """Recorre todos los vehículos con km cargado y arma un ranking de los que tienen
    mantenimiento atrasado, ordenados por urgencia (el atraso más grande primero)."""
    c.execute("""SELECT id, patente, cliente_nombre, cliente_telefono, marca_auto, modelo_auto,
                 km_registro, km_actual, created_at FROM vehiculos""")
    vehiculos = [dict(r) for r in c.fetchall()]
    resultado = []
    for v in vehiculos:
        km_calc = calcular_km_recorridos(v)
        if km_calc["km_recorridos"] is None:
            continue
        proyeccion = calcular_proyeccion_mantenimiento(v["id"], km_calc["km_recorridos"])
        atrasadas = [p for p in proyeccion if p["Atraso estimado"] > 0]
        if atrasadas:
            resultado.append({
                "vehiculo": v,
                "piezas_atrasadas": atrasadas,
                "atraso_max": max(p["Atraso estimado"] for p in atrasadas),
            })
    resultado.sort(key=lambda r: -r["atraso_max"])
    return resultado


def calcular_alertas_vehiculo(vehiculo_id, km_actual):
    """Piezas que ya recorrieron el 85% o más de su vida útil estimada."""
    c.execute("""SELECT descripcion_pieza, marca_pieza, codigo_pieza, km_instalacion, vida_util_km
                 FROM historial_piezas
                 WHERE vehiculo_id = ? AND vida_util_km IS NOT NULL AND km_instalacion IS NOT NULL""",
              (vehiculo_id,))
    alertas = []
    for row in c.fetchall():
        recorridos = km_actual - row["km_instalacion"]
        if recorridos < 0 or not row["vida_util_km"]:
            continue
        porcentaje = recorridos / row["vida_util_km"]
        if porcentaje >= 0.85:
            alertas.append({
                "Pieza": row["descripcion_pieza"], "Marca": row["marca_pieza"], "Código": row["codigo_pieza"],
                "Km recorridos": recorridos, "Vida útil estimada": row["vida_util_km"],
                "% consumido": round(porcentaje * 100)
            })
    return sorted(alertas, key=lambda a: -a["% consumido"])


# ============================================================
# IDEA 3: SUSTITUCIÓN INTELIGENTE POR MEDIDAS MECÁNICAS
# ============================================================
def buscar_por_medidas(diam_int=None, diam_ext=None, ancho=None, paso_rosca=None, estrias=None, tolerancia_pct=5,
                        estrias_internas=None, estrias_externas=None, posicion_seguro=None, tiene_abs="Cualquiera",
                        diam_int_cara_b=None, diam_ext_cara_b=None,
                        diam_rosca_homocinetica=None, diam_copa=None):
    condiciones = []
    params = []

    def rango(valor, campo):
        if valor:
            tol = valor * tolerancia_pct / 100.0
            condiciones.append(f"p.{campo} BETWEEN ? AND ?")
            params.extend([valor - tol, valor + tol])

    rango(diam_int, "diametro_interno")
    rango(diam_ext, "diametro_externo")
    rango(diam_int_cara_b, "diametro_interno_cara_b")
    rango(diam_ext_cara_b, "diametro_externo_cara_b")
    rango(diam_rosca_homocinetica, "diametro_rosca_homocinetica")
    rango(diam_copa, "diametro_copa")
    rango(ancho, "ancho")
    if paso_rosca:
        condiciones.append("UPPER(p.paso_rosca) = ?")
        params.append(paso_rosca.strip().upper())
    if estrias:
        condiciones.append("p.cantidad_estrias = ?")
        params.append(estrias)
    if estrias_internas:
        condiciones.append("p.estrias_internas = ?")
        params.append(estrias_internas)
    if estrias_externas:
        condiciones.append("p.estrias_externas = ?")
        params.append(estrias_externas)
    if posicion_seguro:
        condiciones.append("UPPER(p.posicion_seguro) = ?")
        params.append(posicion_seguro.strip().upper())
    if tiene_abs != "Cualquiera":
        condiciones.append("p.tiene_abs = ?")
        params.append(1 if tiene_abs == "Sí" else 0)

    if not condiciones:
        return []

    query = f"""SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion", m.nombre AS "Marca",
                p.diametro_interno AS "Diám. interno (cara A)", p.diametro_interno_cara_b AS "Diám. interno (cara B)",
                p.diametro_externo AS "Diám. externo (cara A)", p.diametro_externo_cara_b AS "Diám. externo (cara B)",
                p.diametro_rosca_homocinetica AS "Diám. rosca homocinética", p.diametro_copa AS "Diám. copa",
                p.ancho AS "Ancho",
                p.paso_rosca AS "Paso de rosca", p.cantidad_estrias AS "Estrías",
                p.estrias_internas AS "Estrías internas", p.estrias_externas AS "Estrías externas",
                p.posicion_seguro AS "Posición del seguro",
                CASE WHEN p.tiene_abs = 1 THEN 'Sí' WHEN p.tiene_abs = 0 THEN 'No' ELSE '' END AS "ABS",
                p.precio AS "Precio", p.stock AS "Stock"
                FROM productos p JOIN marcas m ON m.id = p.marca_id
                WHERE {" AND ".join(condiciones)} ORDER BY m.nombre LIMIT 100"""
    c.execute(query, params)
    return filas_a_listas(c)


def actualizar_medidas(producto_id, diam_int, diam_ext, ancho, paso_rosca, estrias, ubicacion,
                        estrias_internas=None, estrias_externas=None, posicion_seguro=None, tiene_abs="Cualquiera",
                        diam_int_cara_b=None, diam_ext_cara_b=None,
                        diam_rosca_homocinetica=None, diam_copa=None):
    tiene_abs_valor = None if tiene_abs == "Cualquiera" else (1 if tiene_abs == "Sí" else 0)
    with db_lock:
        c.execute(
            "UPDATE productos SET diametro_interno=?, diametro_externo=?, ancho=?, paso_rosca=?, "
            "cantidad_estrias=?, ubicacion=?, estrias_internas=?, estrias_externas=?, posicion_seguro=?, "
            "tiene_abs=?, diametro_interno_cara_b=?, diametro_externo_cara_b=?, "
            "diametro_rosca_homocinetica=?, diametro_copa=? WHERE id=?",
            (diam_int or None, diam_ext or None, ancho or None, (paso_rosca.strip() or None) if paso_rosca else None,
             estrias or None, (ubicacion.strip() or None) if ubicacion else None,
             estrias_internas or None, estrias_externas or None,
             (posicion_seguro.strip() or None) if posicion_seguro else None, tiene_abs_valor,
             diam_int_cara_b or None, diam_ext_cara_b or None,
             diam_rosca_homocinetica or None, diam_copa or None, producto_id)
        )
        conn.commit()


def calcular_descriptores_orb(imagen_bytes):
    """Calcula puntos característicos (ORB) de una imagen para poder compararla contra otras
    sin depender tanto del ángulo o el fondo exacto. Devuelve bytes serializados para guardar
    en la base, o None si la imagen no tiene puntos suficientes (muy lisa, borrosa o uniforme)."""
    import cv2
    import numpy as np
    import pickle

    arr = np.frombuffer(imagen_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    alto, ancho = img.shape
    escala = 500 / max(alto, ancho)
    if escala < 1:
        img = cv2.resize(img, (int(ancho * escala), int(alto * escala)))
    orb = cv2.ORB_create(nfeatures=300)
    _, descriptores = orb.detectAndCompute(img, None)
    if descriptores is None or len(descriptores) < 5:
        return None
    return pickle.dumps(descriptores)


def comparar_descriptores_orb(desc_bytes_a, desc_bytes_b):
    """Cuenta cuántos puntos característicos matchean bien entre dos fotos — cuanto más alto,
    más parecidas. Es un puntaje relativo para ORDENAR candidatos, no un porcentaje de certeza."""
    import cv2
    import pickle

    desc_a = pickle.loads(desc_bytes_a)
    desc_b = pickle.loads(desc_bytes_b)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    matches = bf.knnMatch(desc_a, desc_b, k=2)
    buenos = 0
    for par in matches:
        if len(par) == 2:
            m, n = par
            if m.distance < 0.75 * n.distance:  # test de razón de Lowe: descarta matches ambiguos
                buenos += 1
    return buenos


def buscar_por_similitud_visual(imagen_bytes, top_n=8):
    """Compara una foto contra todas las que ya tenés cargadas en el catálogo, y devuelve las
    más parecidas ordenadas — son candidatos a revisar a mano, NUNCA una identificación confirmada.
    Con piezas metálicas lisas y sin textura (muchas rótulas, rulemanes, bulones) va a rendir mal
    por más buena que sea la foto — no hay suficiente detalle visual distintivo para agarrarse."""
    descriptores_query = calcular_descriptores_orb(imagen_bytes)
    if descriptores_query is None:
        return None, (
            "La foto no tiene suficientes detalles distintivos para comparar (muy lisa, borrosa, "
            "poco iluminada, o la pieza es un objeto metálico simple sin textura marcada)."
        )

    c.execute("""SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
                 m.nombre AS "Marca", p.precio AS "Precio", p.stock AS "Stock", p.imagen_orb_blob
                 FROM productos p JOIN marcas m ON m.id = p.marca_id
                 WHERE p.imagen_orb_blob IS NOT NULL""")
    candidatos = c.fetchall()
    if not candidatos:
        return None, "Todavía no tenés ninguna foto de producto cargada en el catálogo para comparar."

    resultados = []
    for fila in candidatos:
        try:
            puntaje = comparar_descriptores_orb(descriptores_query, fila["imagen_orb_blob"])
        except Exception:
            continue
        resultados.append({
            "ID": fila["ID"], "Codigo": fila["Codigo"], "Descripcion": fila["Descripcion"],
            "Marca": fila["Marca"], "Precio": fila["Precio"], "Stock": fila["Stock"], "Puntaje": puntaje
        })
    resultados.sort(key=lambda r: -r["Puntaje"])
    return resultados[:top_n], None


def actualizar_imagen_producto(producto_id, imagen_bytes):
    """Guarda la foto de un producto directo en la base (como data URI comprimida) para que
    aparezca en la columna 'Imagen' del buscador, y calcula sus puntos característicos (ORB)
    para poder compararla contra otras fotos con el buscador por similitud visual."""
    from PIL import Image as PILImage
    import base64
    img = PILImage.open(io.BytesIO(imagen_bytes)).convert("RGB")
    img.thumbnail((400, 400))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=80)
    imagen_comprimida = buffer.getvalue()
    b64 = base64.b64encode(imagen_comprimida).decode("ascii")
    data_uri = f"data:image/jpeg;base64,{b64}"
    descriptores = calcular_descriptores_orb(imagen_comprimida)
    with db_lock:
        c.execute("UPDATE productos SET imagen_url = ?, imagen_orb_blob = ? WHERE id = ?",
                   (data_uri, descriptores, producto_id))
        conn.commit()


def eliminar_imagen_producto(producto_id):
    with db_lock:
        c.execute("UPDATE productos SET imagen_url = NULL, imagen_orb_blob = NULL WHERE id = ?", (producto_id,))
        conn.commit()


def migrar_hashes_orb_pendientes():
    """Calcula los descriptores ORB de fotos de producto que se cargaron ANTES de que existiera
    la comparación visual (o que por algún motivo se quedaron sin calcular). Se salta las que ya
    los tienen, así que en cada arranque solo procesa lo pendiente, no todo de nuevo."""
    import base64
    c.execute("SELECT id, imagen_url FROM productos WHERE imagen_url IS NOT NULL AND imagen_orb_blob IS NULL")
    pendientes = c.fetchall()
    for fila in pendientes:
        try:
            data_uri = fila["imagen_url"]
            b64_data = data_uri.split(",", 1)[1] if "," in data_uri else data_uri
            imagen_bytes = base64.b64decode(b64_data)
            descriptores = calcular_descriptores_orb(imagen_bytes)
            if descriptores:
                with db_lock:
                    c.execute("UPDATE productos SET imagen_orb_blob = ? WHERE id = ?", (descriptores, fila["id"]))
                    conn.commit()
        except Exception:
            continue
    return len(pendientes)


@st.cache_resource
def _ejecutar_migracion_orb_una_vez():
    """Corre migrar_hashes_orb_pendientes() una sola vez por proceso (no en cada rerun de
    Streamlit), con el mismo patrón que ya usa get_connection() para la conexión a la base."""
    return migrar_hashes_orb_pendientes()


_ejecutar_migracion_orb_una_vez()


# ============================================================
# IDEA 5: AUDITORÍA PREVENTIVA POR MUESTREO ALEATORIO
# ============================================================
def generar_auditoria_hoy(cantidad=8):
    """Genera (si no existe todavía) la muestra aleatoria de hoy, priorizando favoritos y productos con precio cargado."""
    hoy = datetime.now().strftime("%Y-%m-%d")
    with db_lock:
        c.execute("SELECT COUNT(*) FROM auditoria_diaria WHERE fecha = ?", (hoy,))
        if c.fetchone()[0] > 0:
            return False
        c.execute(
            "SELECT id, stock FROM productos WHERE favorito = 1 OR precio IS NOT NULL ORDER BY RANDOM() LIMIT ?",
            (cantidad,)
        )
        elegidos = c.fetchall()
        for row in elegidos:
            c.execute(
                "INSERT OR IGNORE INTO auditoria_diaria (fecha, producto_id, stock_sistema) VALUES (?, ?, ?)",
                (hoy, row["id"], row["stock"])
            )
        conn.commit()
    return True


def listar_auditoria_hoy():
    hoy = datetime.now().strftime("%Y-%m-%d")
    c.execute("""SELECT a.id AS "ID_auditoria", p.codigo_raw AS "Codigo", m.nombre AS "Marca",
                 a.stock_sistema AS "Stock sistema", a.stock_contado AS "Stock contado",
                 a.diferencia AS "Diferencia", a.resuelto AS "Resuelto"
                 FROM auditoria_diaria a JOIN productos p ON p.id = a.producto_id JOIN marcas m ON m.id = p.marca_id
                 WHERE a.fecha = ? ORDER BY a.resuelto ASC, p.codigo_raw""", (hoy,))
    return filas_a_listas(c)


def registrar_conteo_auditoria(auditoria_id, stock_contado):
    with db_lock:
        c.execute("SELECT stock_sistema FROM auditoria_diaria WHERE id = ?", (auditoria_id,))
        row = c.fetchone()
        diferencia = stock_contado - (row["stock_sistema"] or 0)
        c.execute(
            "UPDATE auditoria_diaria SET stock_contado=?, diferencia=?, resuelto=1 WHERE id=?",
            (stock_contado, diferencia, auditoria_id)
        )
        conn.commit()


# ============================================================
# IDEA 6: UBICACIÓN INTELIGENTE EN DEPÓSITO (matriz ABC)
# ============================================================
def calcular_matriz_abc(limite=300):
    """Clasifica productos en A/B/C usando la frecuencia de búsqueda como indicador de rotación
    (no hay módulo de ventas en la app, así que esto es una aproximación de demanda)."""
    c.execute("""SELECT p.id AS "ID", p.codigo_raw AS "Codigo", m.nombre AS "Marca",
                 p.ubicacion AS "Ubicación", COALESCE(p.veces_buscado, 0) AS "Veces buscado"
                 FROM productos p JOIN marcas m ON m.id = p.marca_id
                 WHERE COALESCE(p.veces_buscado, 0) > 0 OR p.favorito = 1
                 ORDER BY COALESCE(p.veces_buscado, 0) DESC LIMIT ?""", (limite,))
    filas = filas_a_listas(c)
    total = len(filas)
    for i, f in enumerate(filas):
        if total <= 1 or i < max(1, round(total * 0.2)):
            f["Categoría"] = "A"
            f["Sugerencia"] = "Cerca de la entrada, a la altura de la cintura"
        elif i < round(total * 0.5):
            f["Categoría"] = "B"
            f["Sugerencia"] = "Zona intermedia"
        else:
            f["Categoría"] = "C"
            f["Sugerencia"] = "Estante superior o trasero"
    return filas


# ============================================================
# MODO MECÁNICO — DICCIONARIO DE CÓDIGOS OBD2 / DTC
# ============================================================
def buscar_dtc(codigo, fabricante_filtro="Todos"):
    codigo = codigo.strip().upper()
    query = """SELECT codigo AS "Código",
               CASE WHEN fabricante = '' THEN 'Genérico' ELSE fabricante END AS "Fabricante",
               descripcion AS "Descripción", sistema AS "Sistema",
               causas_posibles AS "Causas posibles" FROM codigos_dtc
               WHERE (codigo = ? OR codigo LIKE ?)"""
    params = [codigo, f"%{codigo}%"]
    if fabricante_filtro == "Genérico":
        query += " AND fabricante = ''"
    elif fabricante_filtro and fabricante_filtro != "Todos":
        query += " AND fabricante = ?"
        params.append(fabricante_filtro)
    query += " ORDER BY fabricante, codigo"
    c.execute(query, params)
    return filas_a_listas(c)


def agregar_dtc(codigo, descripcion, sistema, causas, fabricante=""):
    codigo = codigo.strip().upper()
    fabricante = fabricante.strip()
    with db_lock:
        c.execute(
            "INSERT INTO codigos_dtc (codigo, fabricante, descripcion, sistema, causas_posibles) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(codigo, fabricante) DO UPDATE SET descripcion=excluded.descripcion, "
            "sistema=excluded.sistema, causas_posibles=excluded.causas_posibles",
            (codigo, fabricante, descripcion.strip(), sistema.strip(), causas.strip())
        )
        conn.commit()


def importar_dtc_masivo(texto):
    """Importa códigos DTC pegados como texto, una línea por código:
    codigo;descripcion;sistema;causas;fabricante (fabricante es opcional, vacío = código genérico)."""
    cargados = 0
    with db_lock:
        for linea in texto.strip().splitlines():
            partes = [p.strip() for p in linea.split(";")]
            if len(partes) < 2 or not partes[0]:
                continue
            codigo = partes[0].upper()
            descripcion = partes[1]
            sistema = partes[2] if len(partes) > 2 else ""
            causas = partes[3] if len(partes) > 3 else ""
            fabricante = partes[4] if len(partes) > 4 else ""
            c.execute(
                "INSERT INTO codigos_dtc (codigo, fabricante, descripcion, sistema, causas_posibles) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(codigo, fabricante) DO UPDATE SET descripcion=excluded.descripcion, "
                "sistema=excluded.sistema, causas_posibles=excluded.causas_posibles",
                (codigo, fabricante, descripcion, sistema, causas)
            )
            cargados += 1
        conn.commit()
    return cargados


def contar_dtc():
    c.execute("SELECT COUNT(*) FROM codigos_dtc")
    return c.fetchone()[0]


def listar_fabricantes_dtc():
    c.execute("SELECT DISTINCT fabricante FROM codigos_dtc WHERE fabricante != '' ORDER BY fabricante")
    return [r["fabricante"] for r in c.fetchall()]


# ============================================================
# MODO MECÁNICO — LECTOR DE VIN
# ============================================================
# Primer carácter del VIN = región/país de fabricación (estándar ISO 3779, dato genérico).
PAISES_VIN = {
    "1": "Estados Unidos", "4": "Estados Unidos", "5": "Estados Unidos",
    "2": "Canadá", "3": "México", "6": "Australia",
    "8": "Argentina", "9": "Brasil / Argentina",
    "J": "Japón", "K": "Corea del Sur", "L": "China",
    "S": "Reino Unido", "T": "Suiza", "V": "Francia / España",
    "W": "Alemania", "Y": "Suecia / Finlandia", "Z": "Italia",
}
# Código de año en la 10ª posición del VIN (estándar, cíclico cada 30 años).
ANIOS_VIN = {
    "A": 1980, "B": 1981, "C": 1982, "D": 1983, "E": 1984, "F": 1985, "G": 1986, "H": 1987,
    "J": 1988, "K": 1989, "L": 1990, "M": 1991, "N": 1992, "P": 1993, "R": 1994, "S": 1995,
    "T": 1996, "V": 1997, "W": 1998, "X": 1999, "Y": 2000,
    "1": 2001, "2": 2002, "3": 2003, "4": 2004, "5": 2005, "6": 2006, "7": 2007, "8": 2008, "9": 2009,
}


def decodificar_vin(vin):
    vin = re.sub(r'\s', '', vin.strip().upper())
    resultado = {"vin": vin, "valido": False}
    if len(vin) != 17:
        resultado["error"] = "El VIN debe tener 17 caracteres."
        return resultado
    if any(ch in vin for ch in ("I", "O", "Q")):
        resultado["error"] = "El VIN no puede contener las letras I, O ni Q."
        return resultado

    resultado["valido"] = True
    wmi = vin[:3]
    resultado["wmi"] = wmi
    resultado["pais"] = PAISES_VIN.get(vin[0], "Desconocido / no cargado")

    c.execute("SELECT fabricante, pais FROM fabricantes_vin WHERE wmi = ?", (wmi,))
    fila = c.fetchone()
    if fila:
        resultado["fabricante"] = fila["fabricante"]
        if fila["pais"]:
            resultado["pais"] = fila["pais"]
    else:
        resultado["fabricante"] = None

    letra_anio = vin[9]
    base_anio = ANIOS_VIN.get(letra_anio)
    if base_anio:
        # El 7° carácter numérico suele indicar el ciclo 1980-2009; alfabético, el ciclo 2010+.
        if vin[6].isdigit():
            resultado["anio_estimado"] = base_anio
        else:
            resultado["anio_estimado"] = base_anio + 30
    else:
        resultado["anio_estimado"] = None

    return resultado


def agregar_fabricante_vin(wmi, fabricante, pais):
    wmi = wmi.strip().upper()
    with db_lock:
        c.execute(
            "INSERT INTO fabricantes_vin (wmi, fabricante, pais) VALUES (?, ?, ?) "
            "ON CONFLICT(wmi) DO UPDATE SET fabricante=excluded.fabricante, pais=excluded.pais",
            (wmi, fabricante.strip(), pais.strip())
        )
        conn.commit()


def listar_fabricantes_vin():
    c.execute("""SELECT wmi AS "WMI", fabricante AS "Fabricante", pais AS "País"
                 FROM fabricantes_vin ORDER BY fabricante""")
    return filas_a_listas(c)


# ============================================================
# MODO MECÁNICO — VISOR DE ESQUEMAS
# ============================================================
def guardar_esquema(titulo, marca_auto, modelo_auto, sistema, descripcion, imagen_bytes, imagen_nombre, generado_ia=False):
    with db_lock:
        c.execute(
            "INSERT INTO esquemas (titulo, marca_auto, modelo_auto, sistema, descripcion, imagen_blob, "
            "imagen_nombre, generado_ia) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (titulo.strip(), marca_auto.strip(), modelo_auto.strip(), sistema.strip(), descripcion.strip(),
             imagen_bytes, imagen_nombre, 1 if generado_ia else 0)
        )
        conn.commit()


# Pistas de piezas típicas en inglés por sistema, para ayudar al modelo gratuito (Flux) a acertar
# mejor el contenido — sin esto tiende a dibujar cualquier cosa genérica de "auto".
PARTES_TIPICAS_POR_SISTEMA = {
    "Motor": "engine block, pistons, cylinder head, timing chain, oil pan",
    "Refrigeración": "radiator, water pump, thermostat, coolant hoses, coolant expansion tank, cooling fan",
    "Retenes y juntas": "crankshaft seal, camshaft seal, gaskets, o-rings",
    "Frenos": "brake disc, brake caliper, brake pads, brake drum, brake hose",
    "Suspensión": "shock absorber, coil spring, control arm, ball joint, stabilizer bar",
    "Dirección": "steering rack, tie rod, steering column, power steering pump",
    "Transmisión": "gearbox, clutch disc, driveshaft, CV joint",
    "Embrague": "clutch disc, clutch pressure plate, release bearing, clutch cable",
    "Correas y distribución": "timing belt, timing belt tensioner, timing belt kit, pulleys",
    "Eléctrico": "alternator, starter motor, battery, wiring harness, fuse box",
    "Combustible": "fuel pump, fuel filter, fuel injectors, fuel tank, fuel lines",
    "Escape": "exhaust manifold, muffler, catalytic converter, exhaust pipe",
    "Aire acondicionado": "AC compressor, condenser, evaporator, AC hoses",
}

# Nombre del sistema en inglés, para no mezclar español dentro de un prompt en inglés.
SISTEMA_EN = {
    "Motor": "engine", "Refrigeración": "cooling", "Retenes y juntas": "seals and gaskets",
    "Frenos": "brake", "Suspensión": "suspension", "Dirección": "steering",
    "Transmisión": "transmission", "Embrague": "clutch", "Correas y distribución": "timing belt",
    "Eléctrico": "electrical", "Combustible": "fuel", "Escape": "exhaust",
    "Aire acondicionado": "air conditioning",
}


def generar_esquema_orientativo_ia(marca, modelo, motorizacion, sistema):
    """Genera una imagen orientativa/genérica (NO una foto real del vehículo) con Gemini.
    Requiere facturación habilitada en la API key (el nivel gratuito no incluye generación de imágenes).
    Usa una key APARTE de la del resto de las funciones de IA (identificar_pieza_por_foto,
    extraer_datos_cedula, transcribir_audio, leer_remito_por_foto) — así, aunque esas otras se usen
    mucho y choquen contra el límite gratuito, nunca pueden generar un cobro por sí solas: la única
    key con facturación habilitada es esta, y solo la usa esta función."""
    from google import genai
    from PIL import Image as PILImage

    api_key = st.secrets.get("gemini_api_key_imagenes") if hasattr(st, "secrets") else None
    if not api_key:
        return None, (
            "No configuraste 'gemini_api_key_imagenes' en Streamlit Cloud (Settings → Secrets). "
            "A propósito es una key distinta de 'gemini_api_key' — esta es la única que necesita "
            "facturación habilitada, para que el resto de las funciones de IA queden totalmente gratis."
        )

    sistema_en = SISTEMA_EN.get(sistema, sistema)
    pistas = PARTES_TIPICAS_POR_SISTEMA.get(sistema, "")
    pistas_txt = f" Mostrá específicamente: {pistas}." if pistas else ""
    prompt = (
        f"Genera un diagrama técnico de despiece ('exploded view') en estilo línea/dibujo técnico "
        f"(como los planos de catálogos de repuestos), mostrando ÚNICAMENTE los componentes del sistema "
        f"de {sistema_en} de un automóvil {marca} {modelo} {motorizacion}.{pistas_txt} No dibujes la "
        f"carrocería completa del auto — solo estas piezas mecánicas, separadas entre sí (vista "
        f"explosionada), unidas por líneas finas, sobre fondo blanco liso, en blanco y negro o con líneas "
        f"oscuras simples. IMPORTANTE: no incluyas números, letras, flechas de referencia, texto ni logos "
        f"de ninguna marca dentro del dibujo — esos se agregan después por separado. Es una referencia "
        f"orientativa general de cómo se relacionan las piezas entre sí, no necesita ser exacto a ese "
        f"modelo puntual."
    )
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model="gemini-2.5-flash-image", contents=[prompt])
        for part in response.candidates[0].content.parts:
            if getattr(part, "inline_data", None) is not None:
                img = PILImage.open(io.BytesIO(part.inline_data.data)).convert("RGB")
                salida = io.BytesIO()
                img.save(salida, format="JPEG", quality=90)
                registrar_uso_ia("Generar imagen orientativa (paga)", True)
                return salida.getvalue(), None
        registrar_uso_ia("Generar imagen orientativa (paga)", False)
        return None, "Gemini no devolvió ninguna imagen para ese pedido."
    except Exception as e:
        registrar_uso_ia("Generar imagen orientativa (paga)", False)
        texto_error = str(e)
        if "RESOURCE_EXHAUSTED" in texto_error or "429" in texto_error or "quota" in texto_error.lower():
            return None, (
                "La generación de imágenes no está incluida en el nivel gratuito de la API de Gemini "
                "(el error dice 'limit: 0' para ese modelo). Para usar esta función hay que habilitar "
                "facturación en aistudio.google.com para la API key 'gemini_api_key_imagenes' — el costo "
                "ronda los US$0,04 por imagen generada. El resto de las funciones de IA usan una key "
                "distinta y separada, así que no se ven afectadas por esto."
            )
        return None, f"Error generando la imagen: {texto_error}"


def listar_marcas_esquemas():
    """Marcas con esquemas ya cargados, UNIDAS con las precargadas en el catálogo (sin imagen todavía)."""
    c.execute("""SELECT marca_auto AS marca FROM esquemas WHERE marca_auto IS NOT NULL AND TRIM(marca_auto) != ''
                 UNION
                 SELECT marca FROM esquemas_catalogo
                 ORDER BY marca""")
    return [r["marca"] for r in c.fetchall()]


def listar_modelos_esquemas(marca):
    c.execute("""SELECT modelo_auto AS modelo FROM esquemas
                 WHERE marca_auto = ? AND modelo_auto IS NOT NULL AND TRIM(modelo_auto) != ''
                 UNION
                 SELECT modelo FROM esquemas_catalogo WHERE marca = ?
                 ORDER BY modelo""", (marca, marca))
    return [r["modelo"] for r in c.fetchall()]


def listar_sistemas_esquemas(marca, modelo):
    c.execute("""SELECT DISTINCT sistema FROM esquemas
                 WHERE marca_auto = ? AND modelo_auto = ? AND sistema IS NOT NULL AND TRIM(sistema) != ''
                 ORDER BY sistema""", (marca, modelo))
    return [r["sistema"] for r in c.fetchall()]


def listar_esquemas_por_categoria(marca, modelo, sistema):
    c.execute("""SELECT id, titulo, descripcion, generado_ia FROM esquemas
                 WHERE marca_auto = ? AND modelo_auto = ? AND sistema = ? ORDER BY titulo""",
              (marca, modelo, sistema))
    return [dict(r) for r in c.fetchall()]


def agregar_vehiculo_catalogo(marca, modelo):
    with db_lock:
        c.execute("INSERT OR IGNORE INTO esquemas_catalogo (marca, modelo) VALUES (?, ?)",
                   (marca.strip(), modelo.strip()))
        conn.commit()


def eliminar_vehiculo_catalogo(marca, modelo):
    with db_lock:
        c.execute("DELETE FROM esquemas_catalogo WHERE marca = ? AND modelo = ?", (marca, modelo))
        conn.commit()


def listar_catalogo_precargado():
    """Marca/modelo precargados sin ningún esquema real cargado todavía (candidatos a borrar)."""
    c.execute("""SELECT marca, modelo FROM esquemas_catalogo ec
                 WHERE NOT EXISTS (
                     SELECT 1 FROM esquemas e WHERE e.marca_auto = ec.marca AND e.modelo_auto = ec.modelo
                 ) ORDER BY marca, modelo""")
    return [dict(r) for r in c.fetchall()]


def listar_esquemas(texto_filtro=""):
    if texto_filtro.strip():
        like = f"%{texto_filtro.strip().upper()}%"
        c.execute("""SELECT id, titulo, marca_auto, modelo_auto, sistema, descripcion, generado_ia FROM esquemas
                     WHERE UPPER(titulo) LIKE ? OR UPPER(marca_auto) LIKE ? OR UPPER(modelo_auto) LIKE ?
                        OR UPPER(sistema) LIKE ?
                     ORDER BY marca_auto, modelo_auto""", (like, like, like, like))
    else:
        c.execute("SELECT id, titulo, marca_auto, modelo_auto, sistema, descripcion, generado_ia FROM esquemas "
                   "ORDER BY marca_auto, modelo_auto")
    return [dict(row) for row in c.fetchall()]


def obtener_imagen_esquema(esquema_id):
    c.execute("SELECT imagen_blob FROM esquemas WHERE id = ?", (esquema_id,))
    row = c.fetchone()
    return row["imagen_blob"] if row else None


def eliminar_esquema(esquema_id):
    with db_lock:
        c.execute("DELETE FROM esquemas WHERE id = ?", (esquema_id,))
        conn.commit()


def agregar_punto_esquema(esquema_id, numero, nombre_pieza, codigo, pos_x=None, pos_y=None):
    """Agrega una pieza marcada dentro de un esquema. Si el código coincide con un producto
    ya cargado, lo vincula (producto_id); si no, igual guarda el código como texto de referencia.
    pos_x/pos_y son porcentajes (0-100) de dónde está la pieza en la imagen, para dibujar el marcador."""
    codigo = (codigo or "").strip()
    producto_id = None
    if codigo:
        clean = sanitizar(codigo)
        if clean:
            c.execute("SELECT id FROM productos WHERE codigo_clean = ? LIMIT 1", (clean,))
            fila = c.fetchone()
            if fila:
                producto_id = fila["id"]
    with db_lock:
        c.execute("SELECT COALESCE(MAX(orden), 0) + 1 FROM esquema_puntos WHERE esquema_id = ?", (esquema_id,))
        siguiente_orden = c.fetchone()[0]
        c.execute(
            "INSERT INTO esquema_puntos (esquema_id, numero, nombre_pieza, codigo, producto_id, pos_x, pos_y, orden) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (esquema_id, (numero or "").strip(), nombre_pieza.strip(), codigo, producto_id, pos_x, pos_y, siguiente_orden)
        )
        conn.commit()
    return producto_id is not None


def listar_puntos_esquema(esquema_id):
    c.execute("""SELECT id, numero, nombre_pieza, codigo, producto_id, pos_x, pos_y FROM esquema_puntos
                 WHERE esquema_id = ? ORDER BY orden""", (esquema_id,))
    return [dict(r) for r in c.fetchall()]


def generar_imagen_con_marcadores(imagen_bytes, puntos):
    """Dibuja círculos numerados sobre la imagen real, en las posiciones (%) que cargó el admin.
    Si la imagen está corrupta, devuelve la original sin marcadores en vez de romper la pantalla."""
    from PIL import Image, ImageDraw, UnidentifiedImageError

    puntos_con_pos = [p for p in puntos if p.get("pos_x") is not None and p.get("pos_y") is not None]
    if not puntos_con_pos:
        return imagen_bytes

    try:
        img = Image.open(io.BytesIO(imagen_bytes)).convert("RGB")
        ancho, alto = img.size
        draw = ImageDraw.Draw(img)
        radio = max(min(ancho, alto) // 40, 12)

        for i, p in enumerate(puntos_con_pos, start=1):
            x = int(p["pos_x"] / 100 * ancho)
            y = int(p["pos_y"] / 100 * alto)
            etiqueta = p.get("numero") or str(i)
            draw.ellipse([x - radio, y - radio, x + radio, y + radio], fill=(232, 163, 61), outline=(20, 20, 20), width=2)
            bbox = draw.textbbox((0, 0), etiqueta)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text((x - tw / 2, y - th / 2 - bbox[1]), etiqueta, fill=(20, 20, 20))

        salida = io.BytesIO()
        img.save(salida, format="JPEG", quality=90)
        return salida.getvalue()
    except (UnidentifiedImageError, OSError):
        return imagen_bytes


def eliminar_punto_esquema(punto_id):
    with db_lock:
        c.execute("DELETE FROM esquema_puntos WHERE id = ?", (punto_id,))
        conn.commit()


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

if es_admin() or es_operador_o_admin():
    col_estado, col_salir = st.columns([4, 1])
    nombre_sesion = st.session_state.get("admin_nombre", "")
    etiqueta_nivel = "administrador" if es_admin() else "operador"
    col_estado.caption(f"🔓 Sesión de {etiqueta_nivel} activa ({nombre_sesion}).")
    if col_salir.button("Salir"):
        st.session_state.nivel_usuario = None
        st.session_state.admin_nombre = None
        st.rerun()
else:
    st.caption(f"👤 Usando como: {obtener_usuario_actual()}")

if "lista_whatsapp" not in st.session_state:
    st.session_state.lista_whatsapp = []  # lista de códigos agregados para el mensaje

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
    ["🔍 Buscador", "🔗 Vincular manual", "📁 Cargar Excel", "🗂️ Administrar",
     "📊 Estadísticas", "📋 Lista WhatsApp", "🚗 Vehículos", "🛠️ Modo Mecánico"]
)

# ============================================================
# TAB 1: BUSCADOR
# ============================================================
with tab1:
    with st.expander("❓ Guía rápida — cómo usar esta app"):
        st.markdown("""
- **🔍 Buscador** — el corazón de la app. Buscá por código (acepta varios separados por coma) o por
  descripción. Los resultados muestran todas las marcas equivalentes, precio, stock y un link directo
  a la ficha del proveedor si lo cargaste.
- **🔗 Vincular manual** — cuando encontrás que dos o más códigos de distintos proveedores son la misma
  pieza y todavía no están relacionados, los agrupás acá de una sola vez.
- **📁 Cargar Excel** — subís la lista completa de un proveedor (Excel, CSV o PDF con tabla) y la app
  arma las equivalencias sola comparando código OEM. También lee remitos por foto.
- **🗂️ Administrar** — todo lo de mantenimiento: marcas, medidas de piezas, fotos de productos,
  combos relacionados, mensajería y cobros.
- **📊 Estadísticas** — números generales, backups, auditoría de stock y qué se buscó sin encontrar nada.
- **📋 Lista WhatsApp** — armá una cotización con varios productos y mandala por WhatsApp o como PDF.
- **🚗 Vehículos** — ficha por patente: historial de piezas, alertas de mantenimiento, y podés cargar
  los datos sacándole una foto a la cédula.
- **🛠️ Modo Mecánico** — diccionario de códigos de falla (DTC), lector de VIN, esquemas técnicos y
  un conversor de unidades.

Casi todo lo que edita o borra algo pide la contraseña de administrador la primera vez que lo usás.
        """)

    # Si se tocó un botón de sugerencia rápida (favorito o búsqueda reciente), precargamos el
    # campo de búsqueda ANTES de crear el widget — si se hace después de creado, Streamlit tira error.
    if "sugerencia_busqueda" in st.session_state:
        st.session_state["busqueda_input"] = st.session_state.pop("sugerencia_busqueda")

    if es_operador_o_admin():
        with st.expander("🖼️ Buscar por similitud visual (experimental)"):
            st.caption(
                "Compará una foto contra las fotos que ya tenés cargadas en el catálogo — "
                "gratis, corre local, sin límite de uso. Es MUCHO menos confiable que un código "
                "exacto: con piezas metálicas lisas sin marcas ni textura (rótulas, rulemanes, "
                "bulones) va a rendir mal aunque la foto sea buena. Úsalo solo para acortar "
                "candidatos a revisar a mano, nunca como confirmación."
            )
            c.execute("SELECT COUNT(*) FROM productos WHERE imagen_orb_blob IS NOT NULL")
            cantidad_listas = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM productos WHERE imagen_url IS NOT NULL AND imagen_orb_blob IS NULL")
            cantidad_pendientes = c.fetchone()[0]
            st.caption(f"📊 Fotos listas para comparar: {cantidad_listas}" +
                       (f" — {cantidad_pendientes} pendiente(s) de procesar" if cantidad_pendientes else ""))
            if cantidad_pendientes and st.button("🔄 Procesar fotos pendientes ahora"):
                with st.spinner("Procesando..."):
                    migrar_hashes_orb_pendientes()
                st.rerun()

            foto_visual = st.file_uploader(
                "Foto de la pieza:", type=["png", "jpg", "jpeg"], key="foto_similitud_visual",
                label_visibility="collapsed"
            )
            if foto_visual and st.button("🖼️ Comparar con fotos del catálogo"):
                with st.spinner("Comparando..."):
                    res_visual, error_visual = buscar_por_similitud_visual(foto_visual.getvalue())
                if error_visual:
                    st.info(error_visual)
                elif res_visual:
                    st.warning(
                        f"⚠️ {len(res_visual)} candidato(s) por parecido visual, de más a menos "
                        "parecido — NINGUNO está confirmado, es una comparación aproximada. "
                        "Compará físicamente antes de vender cualquiera de estos."
                    )
                    st.dataframe(
                        [{k: v for k, v in r.items() if k != "ID"} for r in res_visual],
                        use_container_width=True, hide_index=True
                    )

    modo = st.radio("Buscar por:", ["Código", "Descripción"], horizontal=True)

    c.execute("SELECT nombre FROM marcas ORDER BY nombre")
    lista_marcas = ["Todas"] + [r["nombre"] for r in c.fetchall()]

    if modo == "Código":
        with st.form("form_buscar_codigo"):
            col_busq, col_filt = st.columns([3, 1])
            with col_busq:
                busqueda = st.text_input(
                    "Ingresá uno o varios códigos (separados por coma):",
                    placeholder="Ej: W712/94, 036115561G...",
                    key="busqueda_input"
                )
            with col_filt:
                marca_filtro = st.selectbox("Filtrar por marca:", lista_marcas)
            buscar_click = st.form_submit_button("🔍 Buscar Equivalencias", type="primary")

        # La búsqueda en sí (con sus efectos de una sola vez: guardar historial, contar
        # veces_buscado) se hace acá, solo cuando se tocó "Buscar". El resultado se guarda en
        # session_state y el DESPLIEGUE se hace más abajo, FUERA de este "if", para que los
        # botones de adentro (agregar a WhatsApp, favoritos, combos) sigan funcionando en los
        # reruns siguientes — si el despliegue dependiera de "buscar_click", cualquier otro botón
        # que se toque después haría que buscar_click vuelva a False y todo el bloque desaparezca
        # antes de que el click en el botón de adentro llegue a registrarse.
        if buscar_click:
            codigos_buscados = [x.strip() for x in busqueda.split(",") if x.strip()]
            if not codigos_buscados:
                st.info("Ingresá al menos un código válido para buscar.")
                st.session_state.pop("ultima_busqueda_codigo", None)
            else:
                guardar_busqueda(busqueda.strip())
                resultados_guardados = []
                for codigo_individual in codigos_buscados:
                    clean = sanitizar(codigo_individual)
                    if not clean:
                        resultados_guardados.append(
                            {"codigo_individual": codigo_individual, "clean": None, "res": None}
                        )
                        continue
                    res = buscar_por_codigo(clean, marca_filtro)
                    if res:
                        incrementar_veces_buscado(clean)
                    else:
                        registrar_busqueda_sin_resultado(codigo_individual)
                    resultados_guardados.append(
                        {"codigo_individual": codigo_individual, "clean": clean, "res": res}
                    )
                st.session_state["ultima_busqueda_codigo"] = resultados_guardados

        if st.session_state.get("ultima_busqueda_codigo"):
            catalogos = listar_catalogos_externos()
            total_codigos_buscados = len(st.session_state["ultima_busqueda_codigo"])
            for item in st.session_state["ultima_busqueda_codigo"]:
                codigo_individual = item["codigo_individual"]
                clean = item["clean"]
                res = item["res"]
                if not clean:
                    st.warning(f"🔎 {codigo_individual} — código no válido, se omitió.")
                    continue

                if res:
                    etiqueta_resultado = f"🔎 {codigo_individual} — {len(res)} coincidencia" + ("s" if len(res) != 1 else "")
                else:
                    etiqueta_resultado = f"🔎 {codigo_individual} — sin resultados"

                with st.expander(etiqueta_resultado, expanded=(total_codigos_buscados == 1)):
                    if res:
                        st.success(f"Se encontraron {len(res)} coincidencias:")
                        # Marca la opción más barata ENTRE LAS QUE TIENEN STOCK, para no tener que
                        # comparar precios a ojo cuando hay varias marcas equivalentes.
                        candidatos_precio = [f for f in res if f.get("Precio") and (f.get("Stock") or 0) > 0]
                        id_mas_barato = min(candidatos_precio, key=lambda f: f["Precio"])["ID"] if candidatos_precio else None
                        for f in res:
                            f["💰"] = "🏆 Más barato en stock" if f["ID"] == id_mas_barato else ""
                        mostrar = quitar_id(res)
                        st.dataframe(
                            mostrar, use_container_width=True, hide_index=True,
                            column_config={
                                "Imagen": st.column_config.ImageColumn("Imagen", width="small"),
                                "Ficha": st.column_config.LinkColumn("Ficha", display_text="Ver en proveedor ↗")
                            }
                        )

                        # Botones de link aparte, para no depender de scrollear la tabla al costado en el celular.
                        # La key incluye el código buscado (clean) además del ID: si se buscan varios códigos
                        # a la vez y dos están vinculados entre sí, el mismo producto puede aparecer en más de
                        # un resultado — sin el prefijo de clean, la key se repetiría y Streamlit tira error.
                        con_ficha = [f for f in res if f.get("Ficha")]
                        if con_ficha:
                            for f in con_ficha:
                                st.link_button(
                                    f"🔗 Ver {f['Codigo']} ({f['Marca']}) en el sitio del proveedor",
                                    f["Ficha"], key=f"link_ficha_{clean}_{f['ID']}"
                                )

                        # Combos: piezas que suelen cambiarse junto con lo que se encontró
                        combos_encontrados = {}
                        for f in res:
                            for disp, items in buscar_combos_para_descripcion(f.get("Descripcion", "")).items():
                                combos_encontrados.setdefault(disp, set()).update(items)
                        if combos_encontrados:
                            st.markdown("**💡 Suelen cambiarse junto con esto:**")
                            for disp, items_set in combos_encontrados.items():
                                items = sorted(items_set)
                                st.caption(f"Relacionado con: {disp}")
                                item_cols = st.columns(len(items))
                                for col_item, item in zip(item_cols, items):
                                    if col_item.button(f"🔍 {item}", key=f"combo_{clean}_{disp}_{item}"):
                                        res_item = buscar_por_texto(item)
                                        if res_item:
                                            con_stock = any((r.get("Stock") or 0) > 0 for r in res_item)
                                            if not con_stock:
                                                st.error(f"⚠️ Tenés '{item}' cargado pero SIN STOCK en ningún proveedor.")
                                            st.dataframe(quitar_id(res_item), use_container_width=True, hide_index=True)
                                        else:
                                            st.error(f"⚠️ No tenés '{item}' cargado en la base — vas a necesitar pedirlo.")

                        col_dl, col_add = st.columns(2)
                        with col_dl:
                            st.download_button(
                                "⬇️ Descargar (Excel)",
                                data=to_excel_bytes(mostrar),
                                file_name=f"equivalencias_{clean}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key=f"dl_{clean}"
                            )
                        with col_add:
                            if st.button("📋 Agregar a lista de WhatsApp", key=f"add_wa_{clean}"):
                                st.session_state.lista_whatsapp.append({
                                    "codigo_buscado": codigo_individual,
                                    "resultados": res
                                })
                                st.success("Agregado a la lista. Andá a la pestaña 'Lista WhatsApp' para armarla.")

                        st.markdown("**📌 ¿Falta stock de alguno? Marcalo para reposición**")
                        st.caption("El dueño lo va a ver en Estadísticas → Para pedir, y decide qué comprarle a cada proveedor.")
                        for fila_stock in res:
                            colr1, colr2 = st.columns([3, 1])
                            colr1.write(f"{fila_stock['Marca']} - {fila_stock['Codigo']} (stock actual: {fila_stock.get('Stock') if fila_stock.get('Stock') is not None else 's/d'})")
                            if colr2.button("📌 Pedir", key=f"pedir_repo_{fila_stock['ID']}_{clean}"):
                                solicitar_reposicion(fila_stock["ID"])
                                st.success("Marcado para reposición.")

                        # Marcar favoritos / editar precio y stock
                        with st.expander("✏️ Marcar favorito / editar precio y stock"):
                            for fila in res:
                                colF, colC, colP, colS, colG, colH = st.columns([0.5, 1.7, 1.1, 0.9, 0.7, 0.7])
                                es_fav = bool(fila.get("Favorito"))
                                nuevo_fav = colF.checkbox("⭐", value=es_fav, key=f"fav_{fila['ID']}_{clean}")
                                if nuevo_fav != es_fav:
                                    alternar_favorito(fila["ID"], nuevo_fav)
                                colC.write(f"{fila['Marca']} - {fila['Codigo']}")
                                nuevo_precio = colP.number_input(
                                    "Precio", value=float(fila.get("Precio") or 0),
                                    key=f"precio_{fila['ID']}_{clean}", min_value=0.0, step=100.0,
                                    label_visibility="collapsed"
                                )
                                nuevo_stock = colS.number_input(
                                    "Stock", value=int(fila.get("Stock") or 0),
                                    key=f"stock_{fila['ID']}_{clean}", min_value=0, step=1,
                                    label_visibility="collapsed"
                                )
                                if colG.button("💾", key=f"save_{fila['ID']}_{clean}"):
                                    actualizar_precio_stock(fila["ID"], nuevo_precio, nuevo_stock)
                                    st.success("Guardado.")
                                if colH.button("📈", key=f"hist_precio_{fila['ID']}_{clean}", help="Ver historial de precio"):
                                    st.session_state[f"mostrar_hist_{fila['ID']}"] = True
                                if st.session_state.get(f"mostrar_hist_{fila['ID']}"):
                                    historial_p = historial_precio_producto(fila["ID"])
                                    if historial_p:
                                        st.dataframe(historial_p, use_container_width=True, hide_index=True)
                                    else:
                                        st.caption("Todavía no hay cambios de precio registrados para este producto.")

                        if catalogos:
                            st.caption("Buscar este código también en:")
                            cols = st.columns(len(catalogos))
                            for col, cat in zip(cols, catalogos):
                                with col:
                                    st.link_button(f"🌐 {cat['nombre']}", cat["url"],
                                                    use_container_width=True, key=f"link_{cat['id']}_{clean}")
                    else:
                        st.warning("No hay equivalencias registradas para ese código.")
                        parcial = buscar_por_texto(clean)
                        if parcial:
                            st.info("¿Quisiste decir alguno de estos códigos parecidos?")
                            st.dataframe(quitar_id(parcial)[:10], use_container_width=True, hide_index=True)
    else:
        with st.expander("🎙️ Buscar por voz"):
            st.caption(
                "Grabá diciendo lo que buscás — la IA lo transcribe y lo busca con el buscador de "
                "siempre. No es un asistente que entienda pedidos complejos, es simplemente hablar "
                "en vez de tipear."
            )
            audio_busqueda = st.audio_input("Grabar:", key="audio_busqueda_voz")
            if audio_busqueda and st.button("🔍 Transcribir y buscar"):
                with st.spinner("Transcribiendo..."):
                    mime_audio = audio_busqueda.type or "audio/wav"
                    texto_voz, error_voz = transcribir_audio(audio_busqueda.getvalue(), mime_audio)
                if error_voz:
                    st.error(error_voz)
                else:
                    st.session_state["texto_desde_voz"] = texto_voz
                    st.rerun()

        # Precargar el texto transcripto ANTES de crear el widget del form — si se hace después
        # de que ya se dibujó en pantalla, Streamlit tira un error.
        if "texto_desde_voz" in st.session_state:
            st.session_state["texto_input"] = st.session_state.pop("texto_desde_voz")

        with st.form("form_buscar_texto"):
            texto = st.text_input(
                "Ingresá parte de una descripción:",
                placeholder="Ej: ruleman delantero gol (no hace falta el orden exacto)",
                key="texto_input"
            )
            buscar_texto_click = st.form_submit_button("🔍 Buscar por Descripción", type="primary")

        if buscar_texto_click:
            if not texto.strip():
                st.info("Ingresá un texto para buscar.")
            else:
                guardar_busqueda(texto.strip())
                res = buscar_por_texto(texto)
                if res:
                    st.success(f"Se encontraron {len(res)} coincidencias:")
                    st.dataframe(quitar_id(res), use_container_width=True, hide_index=True)
                else:
                    st.warning("No se encontraron productos con esa descripción.")

    with st.expander("📦 Armar pedido (ordenado por ubicación en depósito)"):
        st.caption(
            "Pegá varios códigos separados por coma — te devuelve la lista ordenada por ubicación "
            "en el depósito, para juntar todo en un solo recorrido en vez de ir y volver."
        )
        codigos_picking = st.text_input(
            "Códigos del pedido (separados por coma):",
            placeholder="Ej: W712/94, 036115561G, 24427...", key="picking_codigos"
        )
        if st.button("📦 Ordenar para picking"):
            if not codigos_picking.strip():
                st.info("Pegá al menos un código.")
            else:
                res_picking = armar_lista_picking(codigos_picking)
                if res_picking:
                    sin_ubicacion = [r for r in res_picking if not r["Ubicación"]]
                    st.success(f"Se encontraron {len(res_picking)} de los códigos pedidos:")
                    st.dataframe(res_picking, use_container_width=True, hide_index=True)
                    if sin_ubicacion:
                        st.caption(
                            f"⚠️ {len(sin_ubicacion)} producto(s) todavía no tienen ubicación cargada "
                            "(aparecen al final) — cargala desde 'Administrar' para que la próxima vez "
                            "el orden sea completo."
                        )
                else:
                    st.warning("No encontré ninguno de esos códigos en el catálogo.")

    with st.expander("📐 Buscar por medidas mecánicas (cuando no hay código ni equivalencia cargada)"):
        st.caption(
            "Para piezas de autos antiguos, importados o fuera de catálogo: medí la pieza rota con un "
            "calibre y buscá alternativas que compartan esas cotas, aunque no tengan equivalencia registrada."
        )
        cm1, cm2, cm3 = st.columns(3)
        m_diam_int = cm1.number_input("Diámetro interno (mm)", min_value=0.0, step=0.1, value=0.0, key="med_di")
        m_diam_ext = cm2.number_input("Diámetro externo (mm)", min_value=0.0, step=0.1, value=0.0, key="med_de")
        m_ancho = cm3.number_input("Ancho (mm)", min_value=0.0, step=0.1, value=0.0, key="med_an")
        cm4, cm5, cm6 = st.columns(3)
        m_paso = cm4.text_input("Paso de rosca (opcional)", key="med_paso", placeholder="Ej: M12x1.5")
        m_estrias = cm5.number_input("Cantidad de estrías (opcional)", min_value=0, step=1, value=0, key="med_estrias")
        m_tolerancia = cm6.slider("Tolerancia (%)", min_value=1, max_value=15, value=5, key="med_tol")

        st.markdown("**↔️ Segunda cara (opcional, para piezas con distinta medida de cada lado)**")
        st.caption(
            "Ej: un retén con labio interior de un diámetro de un lado y otro del otro, o un tensor "
            "con el interior escalonado (17mm de una cara, 8mm de la otra)."
        )
        cb1, cb2 = st.columns(2)
        m_diam_int_b = cb1.number_input("Diámetro interno cara B (mm)", min_value=0.0, step=0.1, value=0.0, key="med_di_b")
        m_diam_ext_b = cb2.number_input("Diámetro externo / labio exterior cara B (mm)", min_value=0.0, step=0.1,
                                         value=0.0, key="med_de_b")

        st.markdown("**🔩 Homocinéticas (opcional)**")
        ch1, ch2 = st.columns(2)
        m_estrias_int = ch1.number_input("Estrías internas", min_value=0, step=1, value=0, key="med_estrias_int")
        m_estrias_ext = ch2.number_input("Estrías externas", min_value=0, step=1, value=0, key="med_estrias_ext")
        ch3, ch4 = st.columns(2)
        m_seguro = ch3.text_input("Posición del seguro", key="med_seguro", placeholder="Ej: 1er ranura, a 12mm")
        m_abs = ch4.selectbox("¿Tiene ABS?", ["Cualquiera", "Sí", "No"], key="med_abs")
        ch5, ch6 = st.columns(2)
        m_rosca_homo = ch5.number_input("Diámetro de rosca (mm)", min_value=0.0, step=0.1, value=0.0, key="med_rosca_homo")
        m_copa = ch6.number_input("Diámetro de la copa (mm)", min_value=0.0, step=0.1, value=0.0, key="med_copa")

        if st.button("📐 Buscar por medidas"):
            res_medidas = buscar_por_medidas(
                m_diam_int or None, m_diam_ext or None, m_ancho or None,
                m_paso or None, m_estrias or None, m_tolerancia,
                m_estrias_int or None, m_estrias_ext or None, m_seguro or None, m_abs,
                m_diam_int_b or None, m_diam_ext_b or None,
                m_rosca_homo or None, m_copa or None
            )
            if res_medidas:
                st.success(f"Se encontraron {len(res_medidas)} pieza(s) con medidas compatibles:")
                st.dataframe(quitar_id(res_medidas), use_container_width=True, hide_index=True)
            else:
                st.warning(
                    "Sin resultados. Puede ser que no haya piezas con esas medidas cargadas todavía — "
                    "cargalas desde la pestaña 'Administrar' a medida que las vayas midiendo."
                )

    if es_operador_o_admin():
        with st.expander("📷 Identificar pieza por foto (con IA)"):
            st.caption(
                "Sacale una foto a la pieza o subí una que ya tengas. La IA busca un código visible "
                "y, si lo encuentra, lo busca directo en tu catálogo."
            )
            foto = st.file_uploader(
                "Foto de la pieza:", type=["png", "jpg", "jpeg"], key="foto_identificar_pieza",
                label_visibility="collapsed"
            )
            if foto and st.button("🔍 Identificar"):
                with st.spinner("Consultando..."):
                    datos_pieza, error = identificar_pieza_por_foto(foto.getvalue())
                if error:
                    st.error(error)
                elif datos_pieza:
                    st.session_state["datos_pieza_foto"] = datos_pieza
                    st.session_state["buscar_tipo_pieza_click"] = False

            if st.session_state.get("datos_pieza_foto"):
                datos_pieza = st.session_state["datos_pieza_foto"]
                codigo_detectado = (datos_pieza.get("codigo") or "").strip()
                confianza = (datos_pieza.get("confianza") or "").strip().lower()

                if codigo_detectado:
                    st.success(f"**Código detectado: `{codigo_detectado}`** (confianza de la IA: {confianza or 's/d'})")
                    if confianza in ("media", "baja"):
                        st.caption(
                            "⚠️ La propia IA no está muy segura de haber leído bien el código — "
                            "confirmalo mirando la pieza antes de vender."
                        )
                else:
                    st.warning("No se distinguió ningún código legible en la foto.")
                if datos_pieza.get("marca_visible"):
                    st.caption(f"Marca visible en la pieza: {datos_pieza['marca_visible']}")
                if datos_pieza.get("tipo_pieza"):
                    st.caption(f"Tipo de pieza (según la IA): {datos_pieza['tipo_pieza']}")

                if codigo_detectado:
                    clean_foto = sanitizar(codigo_detectado)
                    res_foto = buscar_por_codigo(clean_foto) if clean_foto else []
                    if res_foto:
                        incrementar_veces_buscado(clean_foto)
                        st.success(f"✅ Coincidencia CONFIRMADA en tu catálogo — {len(res_foto)} resultado(s):")
                        st.caption(
                            "Esto es un match exacto por código, con las equivalencias que ya tenés "
                            "cargadas — no es una suposición de la IA."
                        )
                        st.dataframe(quitar_id(res_foto), use_container_width=True, hide_index=True)
                    else:
                        st.info(
                            f"El código `{codigo_detectado}` no coincide con nada cargado — puede que la "
                            "IA haya leído mal algún carácter, o que sea un código que todavía no tenés."
                        )
                        if datos_pieza.get("tipo_pieza") and st.button("🔍 Buscar por el tipo de pieza en vez del código"):
                            st.session_state["buscar_tipo_pieza_click"] = True

                if (not codigo_detectado or (codigo_detectado and st.session_state.get("buscar_tipo_pieza_click"))) \
                        and datos_pieza.get("tipo_pieza"):
                    if not codigo_detectado:
                        mostrar_tipo = st.button("🔍 Buscar por el tipo de pieza")
                    else:
                        mostrar_tipo = True
                    if mostrar_tipo:
                        tipo_pieza_texto = datos_pieza["tipo_pieza"]
                        res_tipo = buscar_por_texto(tipo_pieza_texto)
                        busqueda_usada = tipo_pieza_texto
                        if not res_tipo:
                            # La frase completa no encontró nada — reintenta con menos palabras
                            # (más amplio), por si tus descripciones no usan las mismas palabras
                            # exactas que eligió la IA (ej: "rótula de suspensión" vs "ROTULA DERECHA").
                            palabras_tipo = tipo_pieza_texto.split()
                            for n in range(len(palabras_tipo) - 1, 0, -1):
                                intento = " ".join(palabras_tipo[:n])
                                res_tipo = buscar_por_texto(intento)
                                if res_tipo:
                                    busqueda_usada = intento
                                    break
                        if res_tipo:
                            if busqueda_usada != tipo_pieza_texto:
                                st.caption(
                                    f"No encontré nada con \"{tipo_pieza_texto}\" completo — probé de nuevo "
                                    f"solo con \"{busqueda_usada}\" y esto apareció (todavía menos preciso, "
                                    "revisá con más cuidado):"
                                )
                            if len(res_tipo) > 1:
                                st.warning(
                                    f"⚠️ Encontré {len(res_tipo)} pieza(s) parecida(s) por palabras clave — "
                                    "NINGUNA está confirmada como la exacta, es solo una búsqueda por texto. "
                                    "Si son piezas como rótulas, retenes, etc. que varían por modelo de auto, "
                                    "comparalas físicamente (o por medidas, en '📐 Buscar por medidas mecánicas') "
                                    "antes de vender la que sea."
                                )
                            else:
                                st.info(
                                    "Encontré 1 coincidencia por palabras clave — tampoco está confirmada, "
                                    "revisala antes de vender."
                                )
                            st.dataframe(quitar_id(res_tipo)[:15], use_container_width=True, hide_index=True)
                            if len(res_tipo) > 15:
                                st.caption(f"Mostrando las primeras 15 de {len(res_tipo)} coincidencias.")
                        else:
                            st.caption("No encontré nada parecido en la base por ese tipo de pieza.")

    historial = historial_reciente()
    if historial:
        st.caption("🕘 Búsquedas recientes:")
        cols_hist = st.columns(min(len(historial), 5))
        for i, termino in enumerate(historial[:5]):
            if cols_hist[i % 5].button(termino, key=f"sugerencia_hist_{i}_{termino}", use_container_width=True):
                st.session_state["sugerencia_busqueda"] = termino
                st.rerun()

    favoritos = listar_favoritos()
    if favoritos:
        with st.expander(f"⭐ Favoritos ({len(favoritos)})"):
            for fila_fav in favoritos[:8]:
                colf1, colf2 = st.columns([4, 1])
                colf1.write(f"{fila_fav.get('Codigo') or ''} — {fila_fav.get('Marca') or ''}")
                if colf2.button("🔍", key=f"sugerencia_fav_{fila_fav['ID']}"):
                    st.session_state["sugerencia_busqueda"] = fila_fav.get("Codigo") or ""
                    st.rerun()
            st.dataframe(quitar_id(favoritos), use_container_width=True, hide_index=True)

# ============================================================
# TAB 2: VINCULAR MANUAL
# ============================================================
def vincular_grupo_equivalencias(productos_info, nivel, nota, verificar):
    """Crea (o reutiliza) cada producto de la lista y los vincula a TODOS entre sí — así se puede
    armar de una un grupo de equivalencias con productos de varios proveedores distintos,
    en vez de tener que ir vinculando de a pares."""
    ids = []
    with db_lock:
        for p in productos_info:
            clean = sanitizar(p["codigo"])
            marca_id = get_or_create_marca(p["marca"])
            pid = get_or_create_producto(
                p["codigo"].strip(), clean, p.get("descripcion", "").strip(),
                marca_id, p.get("imagen_url", "").strip() or None
            )
            ids.append(pid)
        v = 1 if verificar else 0
        pares = 0
        for i in range(len(ids)):
            for j in range(len(ids)):
                if i == j or ids[i] == ids[j]:
                    continue
                c.execute(
                    "INSERT OR REPLACE INTO equivalencias "
                    "(producto_a_id, producto_b_id, created_at, verificada, nivel, nota) "
                    "VALUES (?, ?, datetime('now'), ?, ?, ?)",
                    (ids[i], ids[j], v, nivel, nota.strip())
                )
                pares += 1
        conn.commit()
    return len(set(ids)), pares


with tab2:
    st.subheader("Vincular varios códigos como equivalentes")
    st.caption(
        "Armá un grupo de códigos — de la marca/proveedor que sea, se pueden mezclar — y vinculalos "
        "todos entre sí de una sola vez. Antes había que hacerlo de a pares; ahora si tenés 5 productos "
        "de 5 proveedores distintos que son lo mismo, los sumás todos a la tanda y los vinculás juntos."
    )

    c.execute("SELECT id, nombre FROM marcas ORDER BY nombre")
    nombres_marcas = [m["nombre"] for m in c.fetchall()]

    if "grupo_equivalencia" not in st.session_state:
        st.session_state["grupo_equivalencia"] = []

    # Si se vino desde "Productos sin equivalencias" (pestaña Administrar) con un código para
    # precargar, hay que fijar estos valores ANTES de crear los widgets de abajo — si se hace
    # después de que ya se dibujaron en pantalla, Streamlit tira un error.
    if "vincular_pendiente" in st.session_state:
        pendiente = st.session_state.pop("vincular_pendiente")
        st.session_state["nuevo_codigo_grupo"] = pendiente.get("cod_a", "")
        st.session_state["nueva_desc_grupo"] = pendiente.get("desc_a", "")
        if pendiente.get("marca_a") in nombres_marcas:
            st.session_state["nueva_marca_opcion_grupo"] = pendiente["marca_a"]

    st.markdown("**➕ Agregar un código a la tanda**")
    cg1, cg2 = st.columns(2)
    nuevo_codigo = cg1.text_input("Código", key="nuevo_codigo_grupo")
    marca_opcion = cg2.selectbox("Marca", nombres_marcas + ["➕ Nueva marca..."], key="nueva_marca_opcion_grupo")
    nueva_marca = st.text_input("Nombre de la nueva marca", key="nueva_marca_texto_grupo") \
        if marca_opcion == "➕ Nueva marca..." else marca_opcion
    cg3, cg4 = st.columns(2)
    nueva_desc = cg3.text_input("Descripción (opcional)", key="nueva_desc_grupo")
    nueva_img = cg4.text_input("URL de foto (opcional)", key="nueva_img_grupo", placeholder="https://...")

    if st.button("➕ Agregar a la tanda"):
        clean = sanitizar(nuevo_codigo)
        if not clean:
            st.warning("Completá el código.")
        elif not nueva_marca or not nueva_marca.strip():
            st.warning("Completá la marca.")
        else:
            ya_esta = any(
                sanitizar(it["codigo"]) == clean and it["marca"].strip().upper() == nueva_marca.strip().upper()
                for it in st.session_state["grupo_equivalencia"]
            )
            if ya_esta:
                st.warning("Ese código con esa marca ya está en la tanda.")
            else:
                st.session_state["grupo_equivalencia"].append({
                    "codigo": nuevo_codigo.strip(), "marca": nueva_marca.strip(),
                    "descripcion": nueva_desc.strip(), "imagen_url": nueva_img.strip()
                })
                for k in ["nuevo_codigo_grupo", "nueva_desc_grupo", "nueva_img_grupo"]:
                    st.session_state.pop(k, None)
                st.rerun()

    grupo = st.session_state["grupo_equivalencia"]
    if grupo:
        st.markdown(f"**📋 Tanda actual ({len(grupo)} código{'s' if len(grupo) != 1 else ''}):**")
        for i, it in enumerate(grupo):
            colg1, colg2 = st.columns([5, 1])
            colg1.write(f"{it['marca']}: {it['codigo']}" + (f" — {it['descripcion']}" if it['descripcion'] else ""))
            if colg2.button("🗑️", key=f"quitar_grupo_{i}"):
                grupo.pop(i)
                st.rerun()

        st.markdown("---")
        nivel_equiv = st.selectbox(
            "Nivel de equivalencia (aplica a todo el grupo):",
            ["Exacta", "Reemplazo con modificación", "Solo alternativa de menor calidad"],
            help="Qué tan intercambiables son en la práctica."
        )
        nota_tecnica = st.text_input(
            "Nota técnica (opcional, aplica a todo el grupo):",
            placeholder="Ej: Equivale pero requiere cambiar la ficha eléctrica"
        )
        verificar = st.checkbox("✅ Marcar como verificada", value=True,
                                 help="Verificada = confirmaste vos mismo que son intercambiables.")

        if len(grupo) < 2:
            st.info("Agregá al menos 2 códigos a la tanda para poder vincularlos.")
        elif st.button(f"🔗 Vincular los {len(grupo)} códigos entre sí", type="primary"):
            cantidad_prod, cantidad_pares = vincular_grupo_equivalencias(grupo, nivel_equiv, nota_tecnica, verificar)
            st.success(f"Listo: {cantidad_prod} productos quedaron vinculados entre sí ({cantidad_pares} relaciones creadas).")
            st.session_state["grupo_equivalencia"] = []
            st.rerun()
    else:
        st.caption("Todavía no agregaste ningún código a la tanda.")

# ============================================================
# TAB 3: CARGAR EXCEL
# ============================================================
with tab3:
    if not pedir_password_admin("cargar listas de proveedores"):
        pass
    else:
        st.subheader("Cargar nueva planilla (.xlsx / .csv / .pdf)")
        nombre_prov = st.text_input("Nombre de la Marca / Proveedor:", placeholder="Ej: Mahle, Bosch, Mann...")

        metodo = st.radio(
            "¿Cómo querés indicar el archivo?",
            ["Subir archivo", "Escribir la ruta en el teléfono"],
            horizontal=True,
            help="Si el botón de subir no responde en el navegador del celular, usá la opción de ruta."
        )

        archivo = None

        if metodo == "Subir archivo":
            archivo = st.file_uploader("Seleccioná el archivo", type=["xlsx", "csv", "pdf"])
            if archivo and archivo.name.lower().endswith(".pdf"):
                st.caption(
                    "📄 PDF: funciona mejor con catálogos que tienen tablas reales (no una imagen escaneada). "
                    "Revisá bien la vista previa antes de importar, el resultado puede variar según el PDF."
                )
        else:
            st.caption(
                "Ejemplo: /storage/emulated/0/Download/lista.xlsx "
                "(si el archivo está en Descargas, esa es la ruta de siempre)."
            )
            ruta_archivo = st.text_input("Ruta completa del archivo (.xlsx, .csv o .pdf) en el teléfono:",
                                          placeholder="/storage/emulated/0/Download/lista.xlsx")
            if ruta_archivo:
                import os
                if not os.path.isfile(ruta_archivo):
                    st.error("No se encontró un archivo en esa ruta. Revisá que esté bien escrita.")
                elif not ruta_archivo.lower().endswith((".xlsx", ".csv", ".pdf")):
                    st.error("El archivo debe terminar en .xlsx, .csv o .pdf")
                else:
                    archivo = ruta_archivo

        # --- Mapeo dinámico de columnas ---
        todas_filas = None
        idx_prov = idx_oem = 0
        idx_desc = None

        if archivo:
            try:
                todas_filas = leer_excel(archivo, nrows=200)
                if isinstance(archivo, object) and not isinstance(archivo, str):
                    archivo.seek(0)
            except Exception as e:
                st.error(f"No se pudo leer el archivo: {e}")
                todas_filas = None

        if todas_filas:
            # Detectar automáticamente la fila de encabezado como punto de partida
            header_row = 0
            for idx, fila in enumerate(todas_filas[:15]):
                texto = [v for v in fila if isinstance(v, str) and v.strip()]
                if len(texto) >= 2:
                    header_row = idx
                    break
            encabezado = todas_filas[header_row]
            preview_filas = todas_filas[header_row:header_row + 6]

            st.write("Vista previa (primeras filas detectadas):")
            st.dataframe(preview_filas, use_container_width=True)

            if len(encabezado) < 2:
                st.error("El archivo debe tener al menos 2 columnas (código proveedor y código OEM).")
            else:
                st.markdown("**Mapeo de columnas** — revisá que coincida con tu archivo (se sugiere automáticamente):")
                cols_upper = [str(x).upper() if x else "" for x in encabezado]
                idx_prov_auto, idx_oem_auto, idx_desc_auto = 0, min(1, len(encabezado) - 1), None
                for i, col_name in enumerate(cols_upper):
                    if any(x in col_name for x in ['COD', 'ART', 'REF']):
                        idx_prov_auto = i
                    elif any(x in col_name for x in ['OEM', 'ORIG', 'EQUIV']):
                        idx_oem_auto = i
                    elif any(x in col_name for x in ['DESC', 'DETALLE', 'PROD']):
                        idx_desc_auto = i

                opciones_cols = [f"Columna {i}: {str(v)[:20] if v else '(sin título)'}"
                                  for i, v in enumerate(encabezado)]

                c_p, c_o, c_d = st.columns(3)
                with c_p:
                    idx_prov = st.selectbox("Código Proveedor:", range(len(opciones_cols)),
                                             format_func=lambda x: opciones_cols[x], index=idx_prov_auto)
                with c_o:
                    idx_oem = st.selectbox("Código OEM / Equivalente:", range(len(opciones_cols)),
                                            format_func=lambda x: opciones_cols[x], index=idx_oem_auto)
                with c_d:
                    opciones_desc = [None] + list(range(len(opciones_cols)))
                    idx_default_desc = opciones_desc.index(idx_desc_auto) if idx_desc_auto is not None else 0
                    idx_desc = st.selectbox("Descripción (opcional):", opciones_desc,
                                             format_func=lambda x: "Ninguna" if x is None else opciones_cols[x],
                                             index=idx_default_desc)

        procesar = st.button("📥 Procesar e Importar Lista", type="primary")

        if procesar:
            if not archivo:
                st.warning("Indicá un archivo primero (subilo o escribí su ruta).")
            elif not nombre_prov.strip():
                st.warning("Ingresá el nombre de la marca / proveedor.")
            elif not todas_filas:
                st.warning("No se pudo leer el archivo, revisá el formato.")
            elif len(encabezado) < 2:
                st.warning("El archivo debe tener al menos 2 columnas (código proveedor y código OEM).")
            else:
                try:
                    header_row = 0
                    for idx, fila in enumerate(todas_filas[:15]):
                        texto = [v for v in fila if isinstance(v, str) and v.strip()]
                        if len(texto) >= 2:
                            header_row = idx
                            break

                    # Releer completo (leer_excel con nrows=200 antes era solo para la vista previa)
                    todas_filas_completas = leer_excel(archivo)
                    filas_datos = todas_filas_completas[header_row + 1:]

                    cargados = 0
                    omitidos = 0
                    filas_omitidas = []
                    eq_batch = set()  # inserción en lote: se acumulan los pares y se insertan todos juntos al final
                    progreso = st.progress(0, text="Procesando filas...")
                    total = len(filas_datos)

                    # Todo el trabajo de escritura va con el candado tomado, para que ninguna otra
                    # persona pueda buscar/escribir a mitad de una importación larga y quede todo trabado.
                    with db_lock:
                        prov_id = get_or_create_marca(nombre_prov, "PROVEEDOR")
                        oem_id = get_or_create_marca("OEM / FABRICA", "OEM")

                        for n, fila in enumerate(filas_datos):
                            def celda(idx):
                                return fila[idx] if idx is not None and idx < len(fila) else None

                            raw_p_cell = valor_o_vacio(celda(idx_prov))
                            raw_o_cell = valor_o_vacio(celda(idx_oem))
                            desc = valor_o_vacio(celda(idx_desc))

                            codigos_prov = dividir_codigos(raw_p_cell) or ([raw_p_cell] if raw_p_cell else [])
                            codigos_oem = dividir_codigos(raw_o_cell) or ([raw_o_cell] if raw_o_cell else [])

                            if not codigos_prov or not codigos_oem:
                                omitidos += 1
                                filas_omitidas.append({"Proveedor": raw_p_cell, "OEM": raw_o_cell, "Descripcion": desc})
                                if total and n % 25 == 0:
                                    progreso.progress(min((n + 1) / total, 1.0))
                                continue

                            ids_prov = []
                            for raw_p in codigos_prov:
                                clean_p = sanitizar(raw_p)
                                if clean_p:
                                    ids_prov.append(get_or_create_producto(raw_p, clean_p, desc, prov_id))

                            ids_oem = []
                            for raw_o in codigos_oem:
                                clean_o = sanitizar(raw_o)
                                if clean_o:
                                    ids_oem.append(get_or_create_producto(raw_o, clean_o, desc, oem_id))

                            if not ids_prov or not ids_oem:
                                omitidos += 1
                                filas_omitidas.append({"Proveedor": raw_p_cell, "OEM": raw_o_cell, "Descripcion": desc})
                                if total and n % 25 == 0:
                                    progreso.progress(min((n + 1) / total, 1.0))
                                continue

                            for pid in ids_prov:
                                for oid in ids_oem:
                                    eq_batch.add((pid, oid))
                                    eq_batch.add((oid, pid))
                                for pid2 in ids_prov:
                                    if pid2 != pid:
                                        eq_batch.add((pid, pid2))

                            cargados += 1
                            if total and n % 25 == 0:
                                progreso.progress(min((n + 1) / total, 1.0))

                            # Commit periódico: evita mantener una transacción gigante abierta
                            # durante toda la importación (eso es lo que trababa las búsquedas).
                            if n % 300 == 0 and n > 0:
                                conn.commit()

                        # Inserción en lote: mucho más rápido que insertar de a un vínculo por vez
                        if eq_batch:
                            c.executemany(
                                "INSERT OR IGNORE INTO equivalencias (producto_a_id, producto_b_id, created_at) "
                                "VALUES (?, ?, datetime('now'))",
                                list(eq_batch)
                            )

                        c.execute(
                            "INSERT INTO importaciones (marca, archivo, filas_cargadas, filas_omitidas) VALUES (?, ?, ?, ?)",
                            (nombre_prov.upper(), getattr(archivo, "name", str(archivo)), cargados, omitidos)
                        )
                        conn.commit()

                    progreso.empty()

                    st.success(f"Se importaron {cargados} filas correctamente.")
                    if omitidos:
                        st.warning(f"Se omitieron {omitidos} filas por falta de código proveedor u OEM.")
                        st.dataframe(filas_omitidas, use_container_width=True)
                        st.download_button(
                            "⬇️ Descargar filas omitidas",
                            data=to_excel_bytes(filas_omitidas),
                            file_name="filas_omitidas.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )

                    # Detección de posibles duplicados / errores de tipeo dentro de la marca recién cargada
                    sospechosos = detectar_posibles_duplicados(prov_id)
                    if sospechosos is None:
                        st.caption(
                            "ℹ️ La marca tiene demasiados códigos cargados como para revisar duplicados "
                            "automáticamente sin demorar la página."
                        )
                    elif sospechosos:
                        st.warning(
                            f"⚠️ Encontré {len(sospechosos)} par(es) de códigos muy parecidos dentro de "
                            f"'{nombre_prov}' — podrían ser errores de tipeo. Revisalos:"
                        )
                        st.dataframe(sospechosos, use_container_width=True, hide_index=True)
                except Exception as e:
                    st.error(f"Error procesando la lista: {e}")

        st.markdown("---")
        st.markdown("**📄 Cargar remito por foto (con IA)**")
        st.caption(
            "Sacale una foto o subí una imagen del remito/factura de un proveedor. La IA lee los "
            "ítems y te arma una lista para revisar — no toca el stock hasta que vos confirmes. "
            "Solo actualiza cantidad de los códigos que ya existen en tu catálogo; los que no "
            "coincidan con nada, los tenés que cargar por 'Vincular manual' o con un Excel nuevo."
        )
        foto_remito = st.file_uploader("Foto del remito:", type=["png", "jpg", "jpeg"], key="foto_remito")
        if foto_remito and st.button("🔍 Leer remito"):
            with st.spinner("Leyendo remito..."):
                items_leidos, error_remito = leer_remito_por_foto(foto_remito.getvalue())
            if error_remito:
                st.error(error_remito)
            elif not items_leidos:
                st.warning("No se pudo leer ningún ítem en esa imagen.")
            else:
                st.session_state["items_remito"] = cotejar_items_remito(items_leidos)

        if st.session_state.get("items_remito"):
            items_actuales = st.session_state["items_remito"]
            coinciden = [i for i in items_actuales if i["_producto_id"]]
            no_coinciden = [i for i in items_actuales if not i["_producto_id"]]
            st.success(f"Se leyeron {len(items_actuales)} ítem(s) — {len(coinciden)} coinciden con tu catálogo.")
            st.dataframe(
                [{k: v for k, v in i.items() if not k.startswith("_")} for i in items_actuales],
                use_container_width=True, hide_index=True
            )
            if no_coinciden:
                st.caption(
                    f"⚠️ {len(no_coinciden)} ítem(s) no coinciden con ningún código cargado — "
                    "revisá si están mal leídos o si son productos nuevos para vos."
                )
            colr1, colr2 = st.columns(2)
            if coinciden and colr1.button(f"💾 Sumar stock de los {len(coinciden)} que coinciden"):
                actualizados = aplicar_carga_remito(items_actuales)
                st.success(f"Stock actualizado en {actualizados} producto(s).")
                st.session_state.pop("items_remito", None)
                st.rerun()
            if colr2.button("🗑️ Descartar esta lectura"):
                st.session_state.pop("items_remito", None)
                st.rerun()

# ============================================================
# TAB 4: ADMINISTRAR
# ============================================================
def exportar_configuracion_txt():
    """Junta combos de repuestos, códigos DTC cargados y fabricantes VIN en un solo archivo de texto,
    para respaldo aparte de la base completa o para copiarle la configuración a otra sucursal."""
    lineas = []
    lineas.append(f"# Exportación de configuración — Equivalencias El Chavo — {datetime.now():%d/%m/%Y %H:%M}")
    lineas.append("")

    lineas.append("## COMBOS DE REPUESTOS RELACIONADOS (disparador;item)")
    for combo in listar_combos():
        for item in combo["items"]:
            lineas.append(f"{combo['disparador']};{item}")
    lineas.append("")

    lineas.append("## CÓDIGOS DTC (codigo;descripcion;sistema;causas;fabricante — mismo formato que la carga masiva)")
    c.execute("SELECT codigo, descripcion, sistema, causas_posibles, fabricante FROM codigos_dtc ORDER BY fabricante, codigo")
    for row in c.fetchall():
        lineas.append(f"{row['codigo']};{row['descripcion']};{row['sistema'] or ''};{row['causas_posibles'] or ''};{row['fabricante'] or ''}")
    lineas.append("")

    lineas.append("## FABRICANTES POR WMI - lector de VIN (wmi;fabricante;pais)")
    for f in listar_fabricantes_vin():
        lineas.append(f"{f['WMI']};{f['Fabricante']};{f.get('País') or ''}")

    return "\n".join(lineas)


with tab4:
    st.subheader("🗂️ Administrar")

    sub_marcas, sub_productos, sub_mensajeria, sub_combos, sub_mantenimiento = st.tabs(
        ["🏷️ Marcas", "📦 Productos", "💬 Mensajería y cobros", "🧩 Combos", "🧹 Mantenimiento"]
    )

    c.execute("""SELECT m.id, m.nombre, m.tipo, COUNT(p.id) AS productos
                 FROM marcas m LEFT JOIN productos p ON p.marca_id = m.id
                 GROUP BY m.id ORDER BY m.nombre""")
    marcas_info = c.fetchall()

    with sub_marcas:
        if not marcas_info:
            st.info("Todavía no hay marcas cargadas.")
        else:
            tabla_marcas = [{"Marca": m["nombre"], "Tipo": m["tipo"], "Productos cargados": m["productos"]}
                             for m in marcas_info]
            st.dataframe(tabla_marcas, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.markdown("**🔗 Link a la ficha del proveedor (en vez de guardar la foto)**")
            st.caption(
                "Por cada marca/proveedor podés cargar un patrón de URL con `{codigo}` donde va el código del "
                "producto. La app arma el link automáticamente para cada resultado de búsqueda, sin copiar "
                "ninguna imagen — así podés sumar Taranto y cualquier otro proveedor que uses, cada uno con su "
                "propio patrón. Ejemplo: `https://www.taranto.com.ar/busqueda?q={codigo}`"
            )
            nombres_para_link = [m["nombre"] for m in marcas_info]
            marca_link = st.selectbox("Marca:", nombres_para_link, key="marca_link_ficha")
            id_marca_link = next(m["id"] for m in marcas_info if m["nombre"] == marca_link)
            c.execute("SELECT url_ficha_template FROM marcas WHERE id = ?", (id_marca_link,))
            template_actual = c.fetchone()["url_ficha_template"] or ""
            nuevo_template = st.text_input(
                "Patrón de URL (usá {codigo} donde va el código):", value=template_actual,
                placeholder="https://www.taranto.com.ar/busqueda?q={codigo}", key="input_template_link"
            )
            if st.button("💾 Guardar patrón de link"):
                if nuevo_template.strip() and "{codigo}" not in nuevo_template:
                    st.warning("El patrón tiene que incluir '{codigo}' en algún lado, si no todos los links quedan iguales.")
                else:
                    with db_lock:
                        c.execute("UPDATE marcas SET url_ficha_template = ? WHERE id = ?",
                                  (nuevo_template.strip() or None, id_marca_link))
                        conn.commit()
                    st.success(f"Patrón de link guardado para '{marca_link}'.")
                    st.rerun()

            st.markdown("---")
            st.markdown("**🔀 Fusionar marcas duplicadas**")
            st.caption(
                "Útil cuando una marca quedó cargada con nombres distintos por error de tipeo "
                "(ej: 'MANN' y 'MANN FILTER'). Mueve todos los productos de una a la otra."
            )
            nombres_para_fusion = [m["nombre"] for m in marcas_info]
            colOrig, colDest = st.columns(2)
            marca_origen = colOrig.selectbox("Marca a eliminar (origen):", nombres_para_fusion, key="fusion_origen")
            marca_destino = colDest.selectbox("Marca a conservar (destino):", nombres_para_fusion, key="fusion_destino")
            if st.button("🔀 Fusionar", disabled=(marca_origen == marca_destino)):
                if pedir_password_admin("fusionar marcas"):
                    id_origen = next(m["id"] for m in marcas_info if m["nombre"] == marca_origen)
                    id_destino = next(m["id"] for m in marcas_info if m["nombre"] == marca_destino)
                    fusionar_marcas(id_origen, id_destino)
                    st.success(f"'{marca_origen}' se fusionó dentro de '{marca_destino}'.")
                    st.rerun()

            st.markdown("---")
            st.markdown("**💲 Aumentar/bajar precios por porcentaje**")
            st.caption("Aplica el ajuste a todos los productos con precio cargado de la marca elegida.")
            marca_precio = st.selectbox("Marca:", nombres_para_fusion, key="marca_ajuste_precio")
            porcentaje = st.number_input("Porcentaje (usá negativo para bajar, ej: -5):", value=0.0, step=1.0)
            if st.button("💲 Aplicar ajuste de precios", disabled=(porcentaje == 0)):
                if pedir_password_admin("ajustar precios masivamente"):
                    id_marca_precio = next(m["id"] for m in marcas_info if m["nombre"] == marca_precio)
                    afectados = aumentar_precios_por_marca(id_marca_precio, porcentaje)
                    st.success(f"Se ajustaron {afectados} precio(s) de '{marca_precio}' en {porcentaje:+.1f}%.")

            st.markdown("---")
            st.markdown("**Eliminar una marca** (borra también sus productos y equivalencias asociadas)")
            marca_a_borrar = st.selectbox("Elegí una marca", [m["nombre"] for m in marcas_info])
            confirmar = st.checkbox(f"Confirmo que quiero borrar '{marca_a_borrar}' y todo lo asociado")
            if st.button("🗑️ Eliminar marca", disabled=not confirmar):
                if pedir_password_admin("eliminar una marca"):
                    eliminar_marca_con_papelera(marca_a_borrar)
                    st.success(f"Marca '{marca_a_borrar}' eliminada (podés restaurarla desde la papelera).")
                    st.rerun()

        st.markdown("**Catálogos externos**")
        st.caption("Agregá los sitios de proveedores que querés que aparezcan como botones al buscar un código.")

        catalogos = listar_catalogos_externos()
        if catalogos:
            for cat in catalogos:
                colA, colB, colC = st.columns([2, 5, 1])
                colA.write(cat["nombre"])
                colB.write(cat["url"])
                if colC.button("🗑️", key=f"del_cat_{cat['id']}"):
                    eliminar_catalogo_externo(cat["id"])
                    st.rerun()
        else:
            st.caption("Todavía no agregaste ningún catálogo externo.")

        with st.form("nuevo_catalogo", clear_on_submit=True):
            colN, colU = st.columns(2)
            nombre_cat = colN.text_input("Nombre del proveedor", placeholder="Ej: Wega")
            url_cat = colU.text_input("URL del catálogo", placeholder="Ej: wegamotors.com")
            agregar = st.form_submit_button("➕ Agregar catálogo")
            if agregar:
                if not nombre_cat.strip() or not url_cat.strip():
                    st.warning("Completá nombre y URL.")
                else:
                    agregar_catalogo_externo(nombre_cat, url_cat)
                    st.success(f"'{nombre_cat}' agregado.")
                    st.rerun()

    with sub_productos:
        st.markdown("**Buscar y editar un producto puntual**")
        texto_prod = st.text_input("Buscar producto por código o descripción", key="admin_buscar")
        if texto_prod.strip():
            res_admin = buscar_por_texto(texto_prod)
            if not res_admin:
                clean_admin = sanitizar(texto_prod)
                if clean_admin:
                    res_admin = buscar_por_codigo(clean_admin)
            if res_admin:
                st.dataframe(res_admin, use_container_width=True, hide_index=True)
                st.caption(
                    "¿Necesitás borrar un producto? Está en '🧹 Mantenimiento' → separado a propósito "
                    "de la edición, para que un descuido acá no borre nada."
                )

                st.markdown("**📐 Cargar medidas mecánicas / ubicación en depósito**")
                opciones_prod = {f"{f['Codigo']} ({f['Marca']}) — ID {f['ID']}": f['ID'] for f in res_admin}
                elegido_label = st.selectbox("Elegí el producto a editar:", list(opciones_prod.keys()), key="sel_medidas")
                id_medidas = opciones_prod[elegido_label]
                c.execute(
                    "SELECT diametro_interno, diametro_externo, ancho, paso_rosca, cantidad_estrias, ubicacion, "
                    "estrias_internas, estrias_externas, posicion_seguro, tiene_abs, "
                    "diametro_interno_cara_b, diametro_externo_cara_b, "
                    "diametro_rosca_homocinetica, diametro_copa "
                    "FROM productos WHERE id = ?", (id_medidas,)
                )
                actual = c.fetchone()
                em1, em2, em3 = st.columns(3)
                e_diam_int = em1.number_input("Diám. interno cara A (mm)", min_value=0.0, step=0.1,
                                               value=float(actual["diametro_interno"] or 0), key="e_di")
                e_diam_ext = em2.number_input("Diám. externo cara A (mm)", min_value=0.0, step=0.1,
                                               value=float(actual["diametro_externo"] or 0), key="e_de")
                e_ancho = em3.number_input("Ancho (mm)", min_value=0.0, step=0.1,
                                            value=float(actual["ancho"] or 0), key="e_an")
                em4, em5, em6 = st.columns(3)
                e_paso = em4.text_input("Paso de rosca", value=actual["paso_rosca"] or "", key="e_paso")
                e_estrias = em5.number_input("Cantidad de estrías", min_value=0, step=1,
                                              value=int(actual["cantidad_estrias"] or 0), key="e_estrias")
                e_ubicacion = em6.text_input("Ubicación en depósito", value=actual["ubicacion"] or "",
                                              placeholder="Ej: Pasillo 3, estante B", key="e_ubic")

                st.markdown("**↔️ Segunda cara (opcional)**")
                st.caption(
                    "Para piezas con distinta medida de cada lado — retenes con labio interior/exterior "
                    "escalonado, tensores con el interior de un diámetro de un lado y otro del otro, etc."
                )
                eb1, eb2 = st.columns(2)
                e_diam_int_b = eb1.number_input("Diám. interno cara B (mm)", min_value=0.0, step=0.1,
                                                 value=float(actual["diametro_interno_cara_b"] or 0), key="e_di_b")
                e_diam_ext_b = eb2.number_input("Diám. externo / labio exterior cara B (mm)", min_value=0.0, step=0.1,
                                                 value=float(actual["diametro_externo_cara_b"] or 0), key="e_de_b")

                st.markdown("**🔩 Homocinéticas**")
                eh1, eh2 = st.columns(2)
                e_estrias_int = eh1.number_input("Estrías internas", min_value=0, step=1,
                                                  value=int(actual["estrias_internas"] or 0), key="e_estrias_int")
                e_estrias_ext = eh2.number_input("Estrías externas", min_value=0, step=1,
                                                  value=int(actual["estrias_externas"] or 0), key="e_estrias_ext")
                eh3, eh4 = st.columns(2)
                e_seguro = eh3.text_input("Posición del seguro", value=actual["posicion_seguro"] or "",
                                           placeholder="Ej: 1er ranura, a 12mm", key="e_seguro")
                abs_actual = "Cualquiera" if actual["tiene_abs"] is None else ("Sí" if actual["tiene_abs"] else "No")
                e_abs = eh4.selectbox("¿Tiene ABS?", ["Cualquiera", "Sí", "No"],
                                       index=["Cualquiera", "Sí", "No"].index(abs_actual), key="e_abs")
                eh5, eh6 = st.columns(2)
                e_rosca_homo = eh5.number_input("Diámetro de rosca (mm)", min_value=0.0, step=0.1,
                                                 value=float(actual["diametro_rosca_homocinetica"] or 0), key="e_rosca_homo")
                e_copa = eh6.number_input("Diámetro de la copa (mm)", min_value=0.0, step=0.1,
                                           value=float(actual["diametro_copa"] or 0), key="e_copa")

                if st.button("💾 Guardar medidas y ubicación"):
                    actualizar_medidas(id_medidas, e_diam_int, e_diam_ext, e_ancho, e_paso, e_estrias, e_ubicacion,
                                        e_estrias_int, e_estrias_ext, e_seguro, e_abs,
                                        e_diam_int_b, e_diam_ext_b, e_rosca_homo, e_copa)
                    st.success("Guardado.")

                st.markdown("**📷 Foto del producto**")
                c.execute("SELECT imagen_url FROM productos WHERE id = ?", (id_medidas,))
                imagen_actual = c.fetchone()["imagen_url"]
                if imagen_actual:
                    st.image(imagen_actual, width=150)
                foto_producto = st.file_uploader(
                    "Subí una foto (se guarda comprimida, aparece en la columna 'Imagen' del buscador):",
                    type=["png", "jpg", "jpeg"], key="foto_producto_admin"
                )
                cf1, cf2 = st.columns(2)
                if foto_producto and cf1.button("💾 Guardar foto"):
                    actualizar_imagen_producto(id_medidas, foto_producto.getvalue())
                    st.success("Foto guardada.")
                    st.rerun()
                if imagen_actual and cf2.button("🗑️ Sacar la foto"):
                    eliminar_imagen_producto(id_medidas)
                    st.success("Foto eliminada.")
                    st.rerun()
            else:
                st.info("Sin resultados.")

        st.markdown("**🧩 Productos sin equivalencias**")
        st.caption(
            "Esta sección puede ser pesada, así que se calcula solo cuando la pedís (no en cada búsqueda)."
        )

        if "mostrar_huerfanos" not in st.session_state:
            st.session_state.mostrar_huerfanos = False

        col_ver, col_ocultar = st.columns(2)
        if col_ver.button("📋 Mostrar productos sin equivalencias"):
            st.session_state.mostrar_huerfanos = True
            st.rerun()
        if st.session_state.mostrar_huerfanos and col_ocultar.button("🙈 Ocultar"):
            st.session_state.mostrar_huerfanos = False
            st.rerun()

        if st.session_state.mostrar_huerfanos:
            total_sin_eq = contar_productos_sin_equivalencias()
            st.write(f"Total: **{total_sin_eq}** producto(s) sin ninguna equivalencia.")

            if total_sin_eq == 0:
                st.info("¡Todos los productos tienen al menos una equivalencia! 🎉")
            else:
                c.execute("SELECT nombre FROM marcas ORDER BY nombre")
                marcas_para_filtro = ["Todas"] + [r["nombre"] for r in c.fetchall()]
                marca_filtro_huerfanos = st.selectbox("Filtrar por marca:", marcas_para_filtro, key="filtro_huerfanos")
                cantidad_mostrar = st.selectbox("Mostrar en pantalla:", [25, 50, 100], index=0,
                                                 help="La descarga en Excel siempre incluye todo, esto es solo lo que se dibuja en pantalla.")

                pendientes_completo = listar_productos_sin_equivalencias(marca_filtro_huerfanos, limite=2000)
                if pendientes_completo:
                    st.download_button(
                        "⬇️ Descargar lista completa (Excel)",
                        data=to_excel_bytes(quitar_id(pendientes_completo)),
                        file_name="productos_sin_equivalencias.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    pendientes = pendientes_completo[:cantidad_mostrar]
                    st.caption(f"Mostrando {len(pendientes)} de {len(pendientes_completo)}.")
                    for fila in pendientes:
                        colC, colM, colB = st.columns([3, 2, 1.2])
                        colC.write(f"{fila['Codigo']}" + (f" — {fila['Descripcion']}" if fila.get('Descripcion') else ""))
                        colM.write(fila['Marca'])
                        if colB.button("🔗 Usar", key=f"usar_huerfano_{fila['ID']}"):
                            st.session_state["vincular_pendiente"] = {
                                "cod_a": fila["Codigo"],
                                "marca_a": fila["Marca"],
                                "desc_a": fila.get("Descripcion") or ""
                            }
                            st.success("Cargado. Andá a la pestaña '🔗 Vincular manual' para completar el Código B.")
                            st.rerun()
                else:
                    st.info("Sin resultados para esa marca.")

    with sub_mensajeria:
        st.markdown("**💬 Texto del mensaje de WhatsApp**")
        st.caption(
            "Personalizá el encabezado y el pie del mensaje que se arma en 'Lista WhatsApp' — por "
            "ejemplo para poner el nombre real de tu local, un teléfono de contacto, horarios, etc."
        )
        encabezado_actual = obtener_config("whatsapp_encabezado", "🔧 *Equivalencias El Chavo*")
        pie_actual = obtener_config("whatsapp_pie", "")
        nuevo_encabezado = st.text_input("Encabezado del mensaje:", value=encabezado_actual, key="wa_encabezado_in")
        nuevo_pie = st.text_area("Pie del mensaje (opcional):", value=pie_actual, key="wa_pie_in",
                                  placeholder="Ej: 📍 Av. Siempreviva 742 - Horario: L a V 9 a 18hs")
        if st.button("💾 Guardar textos del mensaje"):
            guardar_config("whatsapp_encabezado", nuevo_encabezado.strip() or "🔧 *Equivalencias El Chavo*")
            guardar_config("whatsapp_pie", nuevo_pie.strip())
            st.success("Guardado.")
            st.rerun()

        st.markdown("---")
        st.markdown("**💳 Alias para QR de transferencia**")
        st.caption(
            "Cargá los alias/CBU que usás (Mercado Pago, distintos bancos, etc.). Al armar una "
            "cotización en 'Lista WhatsApp' vas a poder elegir cuál de estos usar para el QR del PDF. "
            "Si subís el QR real que te da tu banco/Mercado Pago/MODO, se usa ese (funciona de verdad "
            "para transferir). Si no subís nada, se genera uno con el alias/CBU como texto plano — "
            "sirve para no tipear a mano, pero no lo van a reconocer como QR de pago."
        )
        alias_cargados = listar_alias_transferencia()
        if alias_cargados:
            st.dataframe(
                [{k: v for k, v in a.items() if k not in ("ID", "TieneQrReal")} | {"QR real": "✅" if a["TieneQrReal"] else "—"}
                 for a in alias_cargados],
                use_container_width=True, hide_index=True
            )

        opciones_alias_edit = ["➕ Nuevo alias..."] + [f"{a['Nombre']} (editar)" for a in alias_cargados]
        alias_opcion_edit = st.selectbox("Elegí qué hacer:", opciones_alias_edit, key="alias_opcion_edit")
        alias_actual = None
        if alias_opcion_edit != "➕ Nuevo alias...":
            nombre_buscar = alias_opcion_edit.replace(" (editar)", "")
            alias_actual = next(a for a in alias_cargados if a["Nombre"] == nombre_buscar)

        cae1, cae2 = st.columns(2)
        nombre_alias_in = cae1.text_input("Nombre (ej: Mercado Pago, Banco Galicia)",
                                           value=(alias_actual or {}).get("Nombre", ""), key="alias_nombre_in")
        alias_in = cae2.text_input("Alias", value=(alias_actual or {}).get("Alias", ""), key="alias_alias_in")
        cae3, cae4 = st.columns(2)
        cbu_in = cae3.text_input("CBU/CVU (opcional)", value=(alias_actual or {}).get("CBU", ""), key="alias_cbu_in")
        titular_in = cae4.text_input("Titular (opcional)", value=(alias_actual or {}).get("Titular", ""), key="alias_titular_in")

        archivo_qr_real = st.file_uploader(
            "QR real (opcional — el que te dio tu banco/Mercado Pago/MODO):",
            type=["png", "jpg", "jpeg"], key="alias_qr_real_archivo"
        )
        if alias_actual and alias_actual["TieneQrReal"]:
            st.caption("✅ Este alias ya tiene un QR real cargado. Subí uno nuevo para reemplazarlo.")

        cbtn1, cbtn2, cbtn3 = st.columns(3)
        if cbtn1.button("💾 Guardar alias"):
            if not nombre_alias_in.strip() or not alias_in.strip():
                st.warning("Completá al menos el nombre y el alias.")
            else:
                guardar_alias_transferencia(
                    nombre_alias_in, alias_in, cbu_in, titular_in,
                    alias_id=(alias_actual["ID"] if alias_actual else None),
                    qr_real_bytes=(archivo_qr_real.getvalue() if archivo_qr_real else None)
                )
                st.success("Alias guardado.")
                st.rerun()
        if alias_actual and alias_actual["TieneQrReal"] and cbtn2.button("🗑️ Sacar el QR real"):
            eliminar_qr_real(alias_actual["ID"])
            st.success("QR real eliminado — vuelve a usar el de texto plano.")
            st.rerun()
        if alias_actual and cbtn3.button("🗑️ Eliminar este alias"):
            eliminar_alias_transferencia(alias_actual["ID"])
            st.success("Alias eliminado.")
            st.rerun()

    with sub_combos:
        st.markdown("**🧩 Combos de repuestos relacionados**")
        st.caption(
            "Cuando alguien busca un producto cuya descripción contenga el 'disparador', la app va a "
            "sugerir estos ítems relacionados con un botón para buscarlos también. Ej: disparador "
            "'correa de distribucion' → ítems 'Kit de distribución', 'Tensor', 'Bomba de agua'."
        )
        combos_actuales = listar_combos()
        if combos_actuales:
            st.dataframe(
                [{"Disparador": c_["disparador"], "Ítems sugeridos": ", ".join(c_["items"])} for c_ in combos_actuales],
                use_container_width=True, hide_index=True
            )
        disparador_edit = st.text_input(
            "Disparador (palabra/frase que aparece en la descripción del producto):",
            placeholder="Ej: correa de distribucion", key="combo_disparador"
        )
        items_edit = st.text_area(
            "Ítems sugeridos (uno por línea):",
            placeholder="Kit de distribución\nTensor de distribución\nBomba de agua",
            key="combo_items", height=100
        )
        cc1, cc2 = st.columns(2)
        if cc1.button("💾 Guardar combo"):
            if not disparador_edit.strip() or not items_edit.strip():
                st.warning("Completá el disparador y al menos un ítem.")
            else:
                guardar_combo(disparador_edit, items_edit.strip().splitlines())
                st.success(f"Combo para '{disparador_edit.strip()}' guardado.")
                st.rerun()
        if cc2.button("🗑️ Eliminar combo (según el disparador de arriba)"):
            if disparador_edit.strip():
                eliminar_combo(disparador_edit)
                st.success(f"Combo para '{disparador_edit.strip()}' eliminado.")
                st.rerun()

    with sub_mantenimiento:
        st.markdown("**🗑️ Eliminar un producto puntual**")
        st.caption(
            "Separado a propósito de la edición de medidas/fotos, para que buscar y editar un producto "
            "no te deje el botón de borrar a mano por accidente."
        )
        texto_prod_borrar = st.text_input("Buscar el producto a borrar (por código o descripción):", key="mant_buscar_borrar")
        if texto_prod_borrar.strip():
            res_borrar = buscar_por_texto(texto_prod_borrar)
            if not res_borrar:
                clean_borrar = sanitizar(texto_prod_borrar)
                if clean_borrar:
                    res_borrar = buscar_por_codigo(clean_borrar)
            if res_borrar:
                opciones_borrar = {f"{f['Codigo']} ({f['Marca']}) — ID {f['ID']}": f['ID'] for f in res_borrar}
                elegido_borrar_label = st.selectbox("Elegí el producto a eliminar:", list(opciones_borrar.keys()),
                                                     key="mant_sel_borrar")
                id_a_borrar = opciones_borrar[elegido_borrar_label]
                st.caption(
                    "⚠️ Se borran también sus equivalencias con otros productos. Si lo restaurás desde "
                    "la papelera, el producto vuelve pero **sin** esos vínculos — hay que volver a "
                    "vincularlo manualmente."
                )
                confirmar_borrado = st.checkbox(f"Confirmo que quiero borrar '{elegido_borrar_label}'",
                                                 key="mant_confirmar_borrar")
                if st.button("🗑️ Eliminar producto", disabled=not confirmar_borrado):
                    if pedir_password_admin("eliminar un producto"):
                        c.execute("SELECT * FROM productos WHERE id = ?", (id_a_borrar,))
                        fila_producto = c.fetchone()
                        if fila_producto:
                            mover_a_papelera("producto", dict(fila_producto))
                        with db_lock:
                            c.execute("DELETE FROM productos WHERE id = ?", (id_a_borrar,))
                            conn.commit()
                        st.success("Producto eliminado (podés restaurarlo desde la papelera, más abajo).")
                        st.rerun()
            else:
                st.caption("Sin resultados.")

        st.markdown("---")
        st.markdown("**🔍 Salud de los datos**")
        st.caption(
            "Revisa la base en busca de cosas rotas o inconsistentes — útil para detectar corrupción "
            "de datos antes de encontrártela buscando un producto."
        )
        if st.button("🔍 Revisar salud de los datos"):
            reporte_salud = chequear_integridad_bd()
            total_problemas = sum(r["Problemas"] for r in reporte_salud)
            if total_problemas == 0:
                st.success("✅ Todo en orden, no se encontró ningún problema.")
            else:
                st.warning(f"⚠️ Se encontraron {total_problemas} problema(s) en total.")
            st.dataframe(
                [r for r in reporte_salud],
                use_container_width=True, hide_index=True,
                column_config={"Problemas": st.column_config.NumberColumn(
                    "Problemas", help="0 está bien; más de 0 conviene revisarlo"
                )}
            )

        st.markdown("---")
        st.markdown("**Limpieza de la base**")
        st.caption(
            "Con el tiempo pueden quedar códigos cargados por error que no están vinculados a "
            "ninguna equivalencia. Este botón los borra."
        )
        if st.button("🧹 Borrar productos sin ninguna equivalencia"):
            if pedir_password_admin("borrar productos sin equivalencias"):
                borrados = depurar_huerfanos()
                if borrados:
                    st.success(f"Se borraron {borrados} producto(s) sin equivalencias.")
                else:
                    st.info("No había productos sueltos para borrar.")

        st.markdown("---")
        st.markdown("**🗑️ Papelera**")
        st.caption(
            "Cuando borrás una marca entera, un combo, un alias de transferencia o un producto puntual "
            "(por ID), queda acá guardado por si te equivocaste. Se borra en forma permanente solo cuando "
            "vos lo pedís o pasan más de 30 días. (Fusionar marcas y restaurar un backup completo siguen "
            "siendo irreversibles — esos no pasan por acá.)"
        )
        items_papelera = listar_papelera()
        if not items_papelera:
            st.caption("La papelera está vacía.")
        else:
            iconos_tipo = {"combo": "🧩", "alias": "💳", "producto": "📦", "marca": "🏷️"}
            for item in items_papelera:
                colp1, colp2, colp3 = st.columns([3, 1, 1])
                icono = iconos_tipo.get(item["Tipo"], "🗑️")
                colp1.write(
                    f"{icono} {item['Tipo'].capitalize()}: **{item['Detalle']}** — "
                    f"eliminado por {item['Eliminado por'] or 'alguien'} el {item['Fecha']}"
                )
                if colp2.button("↩️ Restaurar", key=f"restaurar_papelera_{item['ID']}"):
                    ok, error_restaurar = restaurar_de_papelera(item["ID"])
                    if ok:
                        st.success("Restaurado.")
                        st.rerun()
                    else:
                        st.error(error_restaurar)
                if colp3.button("🗑️", key=f"borrar_papelera_{item['ID']}", help="Borrar en forma permanente, sin restaurar"):
                    with db_lock:
                        c.execute("DELETE FROM papelera WHERE id = ?", (item["ID"],))
                        conn.commit()
                    st.rerun()

            st.caption("También se limpia sola: lo que lleva más de 30 días acá se borra en forma permanente.")
            if st.button("🧹 Vaciar ahora lo de más de 30 días"):
                vaciar_papelera_antigua(30)
                st.rerun()

# ============================================================
# TAB 5: ESTADÍSTICAS
# ============================================================
with tab5:
    st.subheader("📊 Estadísticas")

    sub_resumen, sub_importaciones, sub_backup, sub_auditoria, sub_busquedas, sub_para_pedir = st.tabs(
        ["📈 Resumen", "📥 Importaciones", "💾 Backup y config", "🧮 Auditoría y depósito",
         "🔎 Búsquedas sin resultado", "📌 Para pedir"]
    )

    with sub_resumen:
        st.subheader("Estadísticas generales")

        c.execute("SELECT COUNT(*) FROM marcas")
        total_marcas = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM productos")
        total_productos = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM equivalencias")
        total_equiv = c.fetchone()[0]

        m1, m2, m3 = st.columns(3)
        m1.metric("Marcas registradas", total_marcas)
        m2.metric("Códigos cargados", total_productos)
        m3.metric("Vínculos de equivalencia", total_equiv // 2 if total_equiv else 0)

        st.markdown("---")
        c.execute("""SELECT m.nombre, COUNT(p.id) AS productos
                     FROM marcas m LEFT JOIN productos p ON p.marca_id = m.id
                     GROUP BY m.id ORDER BY productos DESC LIMIT 15""")
        top_marcas = c.fetchall()
        if top_marcas:
            st.markdown("---")
            st.markdown("**📊 Top marcas por cantidad de códigos cargados**")
            chart_data = {"Marca": [t["nombre"] for t in top_marcas],
                           "Productos": [t["productos"] for t in top_marcas]}
            st.bar_chart(chart_data, x="Marca", y="Productos")

        st.markdown("---")
        st.markdown("**🤖 Uso de las funciones de IA (últimos 30 días)**")
        st.caption(
            "Las primeras 4 funciones usan una API key gratuita — nunca pueden generarte un cobro, "
            "en el peor caso fallan por límite de uso. Solo 'Generar imagen orientativa' usa una key "
            "aparte con facturación habilitada, y es la única que tiene costo real."
        )
        uso_ia_actual = resumen_uso_ia()
        if uso_ia_actual:
            st.dataframe(uso_ia_actual, use_container_width=True, hide_index=True)
        else:
            st.caption("Todavía no se usó ninguna función de IA.")

    with sub_importaciones:
        st.markdown("**Historial de importaciones**")
        c.execute("""SELECT marca AS Marca, archivo AS Archivo, filas_cargadas AS Cargadas,
                     filas_omitidas AS Omitidas, fecha AS Fecha FROM importaciones
                     ORDER BY fecha DESC LIMIT 20""")
        imports = filas_a_listas(c)
        if imports:
            st.dataframe(imports, use_container_width=True, hide_index=True)
        else:
            st.caption("Todavía no se registraron importaciones.")

    with sub_backup:
        if st.button("🗄️ Preparar backup de la base de datos"):
            with open(DB_PATH, "rb") as f:
                st.session_state["backup_bytes"] = f.read()
        if "backup_bytes" in st.session_state:
            st.download_button("⬇️ Descargar backup (.db)", data=st.session_state["backup_bytes"],
                                file_name=f"equivalencias_backup_{datetime.now():%Y%m%d}.db")

        st.markdown("---")
        st.markdown("**📦 Exportar configuración (sin el catálogo de productos)**")
        st.caption(
            "Combos de repuestos, códigos DTC y fabricantes por WMI en un solo archivo de texto — útil "
            "como respaldo liviano aparte del backup completo, o para copiarle la configuración a otra "
            "sucursal sin duplicar todo el catálogo de productos."
        )
        st.download_button(
            "⬇️ Descargar configuración (.txt)",
            data=exportar_configuracion_txt(),
            file_name=f"configuracion_{datetime.now():%Y%m%d}.txt",
            mime="text/plain"
        )

        st.markdown("---")
        st.markdown("**♻️ Restaurar desde un backup**")
        st.caption(
            "⚠️ Esto reemplaza TODA la base actual por la del archivo que subas. "
            "Usalo si el hosting se reinició y perdiste datos, o para volver a un backup anterior."
        )
        archivo_restaurar = st.file_uploader("Subí un archivo .db de backup:", type=["db"], key="restore_upload")
        confirmar_restore = st.checkbox("Entiendo que esto borra los datos actuales y los reemplaza")
        if st.button("♻️ Restaurar backup", disabled=not (archivo_restaurar and confirmar_restore)):
            if pedir_password_admin("restaurar un backup"):
                restaurar_backup(archivo_restaurar)
                st.success("Backup restaurado. Recargando...")
                st.rerun()

    with sub_auditoria:
        st.markdown("**🧮 Auditoría diaria de stock (muestreo aleatorio)**")
        st.caption(
            "Todas las mañanas se puede generar una lista corta de productos al azar (priorizando favoritos "
            "y los que tienen precio cargado) para contarlos a mano en 5 minutos y detectar descalces antes de que se acumulen."
        )
        cant_auditoria = st.number_input("Cantidad de productos a auditar hoy:", min_value=3, max_value=20, value=8, step=1)
        if st.button("🎲 Generar auditoría de hoy"):
            generada = generar_auditoria_hoy(cant_auditoria)
            if generada:
                st.success("Auditoría de hoy generada.")
                st.rerun()
            else:
                st.info("Ya había una auditoría generada para hoy (ver abajo).")

        auditoria_hoy = listar_auditoria_hoy()
        if auditoria_hoy:
            for item in auditoria_hoy:
                colA1, colA2, colA3 = st.columns([3, 1.5, 1])
                colA1.write(f"**{item['Codigo']}** ({item['Marca']}) — sistema: {item['Stock sistema']}")
                if item["Resuelto"]:
                    signo = "✅ OK" if item["Diferencia"] == 0 else f"⚠️ Diferencia: {item['Diferencia']:+d}"
                    colA2.write(f"Contado: {item['Stock contado']} — {signo}")
                else:
                    contado = colA2.number_input("Contado", min_value=0, step=1, key=f"conteo_{item['ID_auditoria']}",
                                                  label_visibility="collapsed")
                    if colA3.button("💾", key=f"guardar_conteo_{item['ID_auditoria']}"):
                        registrar_conteo_auditoria(item["ID_auditoria"], contado)
                        st.rerun()
        else:
            st.caption("Todavía no generaste la auditoría de hoy.")

        st.markdown("---")
        st.markdown("**📦 Matriz ABC — ubicación sugerida en depósito**")
        st.caption(
            "Como la app no tiene un módulo de ventas, la rotación se aproxima con la cantidad de veces que "
            "se buscó cada código. Los más buscados (A) conviene tenerlos más a mano."
        )
        matriz = calcular_matriz_abc()
        if matriz:
            st.dataframe(quitar_id(matriz), use_container_width=True, hide_index=True)
            st.caption("Para cargar o corregir la ubicación de un producto, andá a la pestaña 'Administrar'.")
        else:
            st.caption("Todavía no hay suficientes búsquedas registradas para armar la matriz.")

    with sub_busquedas:
        st.markdown("**🔎 Códigos buscados sin resultado**")
        st.caption("Qué te están pidiendo los clientes que todavía no tenés cargado.")
        fallidas = listar_busquedas_sin_resultado()
        if fallidas:
            st.dataframe(fallidas, use_container_width=True, hide_index=True)
        else:
            st.caption("Sin registros todavía.")

    with sub_para_pedir:
        st.markdown("**🙋 Pedidos marcados por empleados**")
        st.caption(
            "Cuando alguien busca algo y toca '📌 Pedir' en el buscador, aparece acá para que decidas "
            "qué comprarle a cada proveedor."
        )
        pedidos = listar_pedidos_reposicion("pendiente")
        seleccionados = []
        if pedidos:
            for p in pedidos:
                colp1, colp2, colp3 = st.columns([4, 1, 1])
                stock_txt = p["Stock actual"] if p["Stock actual"] is not None else "s/d"
                marcado = colp1.checkbox(
                    f"{p['Marca']} - {p['Codigo']} — {p['Descripcion'] or ''} "
                    f"(stock: {stock_txt}, pedido {p['Veces pedido']}x, último: {p['Último en pedirlo']})",
                    key=f"chk_pedido_{p['ID']}"
                )
                if marcado:
                    seleccionados.append(p)
                if colp2.button("✅", key=f"resuelto_{p['ID']}", help="Marcar como resuelto"):
                    marcar_pedido_resuelto(p["ID"])
                    st.rerun()
                if colp3.button("🗑️", key=f"descartar_{p['ID']}", help="Descartar (no hace falta pedirlo)"):
                    descartar_pedido_reposicion(p["ID"])
                    st.rerun()
        else:
            st.caption("Ningún empleado marcó nada para pedir todavía.")

        st.markdown("---")
        st.markdown("**📦 Favoritos con poco stock**")
        umbral_stock = st.number_input("Alertar cuando el stock sea menor o igual a:", min_value=0, value=2, step=1,
                                        key="umbral_para_pedir")
        stock_bajo = listar_favoritos_stock_bajo(umbral_stock)
        if stock_bajo:
            for f in stock_bajo:
                stock_txt_f = f["Stock"] if f["Stock"] is not None else "s/d"
                marcado_f = st.checkbox(
                    f"{f['Marca']} - {f['Codigo']} — {f['Descripcion'] or ''} (stock: {stock_txt_f})",
                    key=f"chk_stockbajo_{f['ID']}"
                )
                if marcado_f:
                    seleccionados.append(f)
        else:
            st.caption("Ningún favorito con stock bajo por ahora.")

        if seleccionados:
            st.markdown("---")
            st.markdown(f"**📲 Armar mensaje para el proveedor ({len(seleccionados)} ítem(s) elegidos)**")
            por_marca = {}
            for item in seleccionados:
                por_marca.setdefault(item["Marca"], []).append(item)
            for marca, items in por_marca.items():
                lineas_msg = [f"Hola! Necesito reponer estos productos de {marca}:"]
                for it in items:
                    stock_it = it.get("Stock actual", it.get("Stock"))
                    lineas_msg.append(
                        f"- {it['Codigo']} ({it.get('Descripcion') or ''}) — "
                        f"quedan {stock_it if stock_it is not None else 's/d'}"
                    )
                mensaje_reposicion = "\n".join(lineas_msg)
                with st.expander(f"📨 {marca} ({len(items)} ítem(s))"):
                    st.text_area("Mensaje:", value=mensaje_reposicion, height=120, key=f"msg_repo_{marca}")
                    url_wa_repo = "https://wa.me/?text=" + quote(mensaje_reposicion)
                    st.link_button(f"📲 Abrir WhatsApp para {marca}", url_wa_repo, key=f"wa_repo_{marca}")

# ============================================================
# TAB 6: LISTA PARA WHATSAPP
# ============================================================
with tab6:
    st.subheader("Armar lista de productos para enviar por WhatsApp")
    st.caption(
        "Buscá códigos en la pestaña Buscador y tocá '📋 Agregar a lista de WhatsApp'. "
        "Acá se arma un mensaje agrupado por producto, con las equivalencias y precios de cada marca."
    )

    lista = st.session_state.lista_whatsapp

    if not lista:
        st.info("Todavía no agregaste ningún producto a la lista. Andá a Buscador y agregá alguno.")
    else:
        st.markdown(f"**{len(lista)} producto(s) en la lista:**")
        for i, item in enumerate(lista):
            colT, colX = st.columns([5, 1])
            colT.write(f"{i + 1}. {item['codigo_buscado']} ({len(item['resultados'])} equivalencias)")
            if colX.button("🗑️", key=f"quitar_wa_{i}"):
                lista.pop(i)
                st.rerun()

        st.markdown("---")
        incluir_precio = st.checkbox("Incluir precios en el mensaje", value=True)
        incluir_stock = st.checkbox("Incluir stock en el mensaje", value=False)

        # Armado del texto del mensaje, agrupado por producto buscado
        encabezado_wa = obtener_config("whatsapp_encabezado", "🔧 *Equivalencias El Chavo*")
        pie_wa = obtener_config("whatsapp_pie", "")
        partes = [f"{encabezado_wa}\n"]
        for item in lista:
            partes.append(f"\n📦 *{item['codigo_buscado']}*")
            for fila in item["resultados"]:
                linea = f"  • {fila['Marca']}: {fila['Codigo']}"
                if fila.get("Descripcion"):
                    linea += f" - {fila['Descripcion']}"
                extras = []
                if incluir_precio and fila.get("Precio"):
                    extras.append(f"${fila['Precio']:,.0f}")
                if incluir_stock and fila.get("Stock") is not None:
                    extras.append(f"Stock: {fila['Stock']}")
                if extras:
                    linea += " (" + " · ".join(extras) + ")"
                partes.append(linea)
        if pie_wa.strip():
            partes.append(f"\n{pie_wa}")
        mensaje = "\n".join(partes)

        st.text_area("Vista previa del mensaje:", value=mensaje, height=300)

        alias_disponibles = listar_alias_transferencia()
        alias_elegido = None
        qr_real_para_pdf = None
        if alias_disponibles:
            opciones_alias = ["Sin QR de transferencia"] + [a["Nombre"] for a in alias_disponibles]
            alias_sel = st.selectbox("Alias para el QR del PDF (opcional):", opciones_alias, key="alias_para_pdf")
            if alias_sel != "Sin QR de transferencia":
                alias_elegido = next(a for a in alias_disponibles if a["Nombre"] == alias_sel)
                if alias_elegido["TieneQrReal"]:
                    qr_real_para_pdf = obtener_qr_real(alias_elegido["ID"])
                    st.caption("✅ Se va a usar el QR real que subiste para este alias.")
                else:
                    st.caption("ℹ️ Este alias no tiene QR real cargado — se va a generar uno con el alias/CBU como texto.")
        else:
            st.caption(
                "Todavía no cargaste ningún alias/CBU — podés hacerlo en 'Administrar' → "
                "'💳 Alias para QR de transferencia' si querés que la cotización incluya uno."
            )

        import urllib.parse
        url_whatsapp = "https://wa.me/?text=" + urllib.parse.quote(mensaje)
        col_wa, col_pdf = st.columns(2)
        col_wa.link_button("📲 Abrir en WhatsApp", url_whatsapp, type="primary", use_container_width=True)
        pdf_bytes = generar_pdf_cotizacion(lista, incluir_precio, incluir_stock,
                                            alias_qr=alias_elegido, qr_real_bytes=qr_real_para_pdf)
        col_pdf.download_button(
            "📄 Descargar cotización (PDF)", data=pdf_bytes,
            file_name=f"cotizacion_{datetime.now():%Y%m%d_%H%M}.pdf",
            mime="application/pdf", use_container_width=True
        )

        if st.button("🗑️ Vaciar toda la lista"):
            st.session_state.lista_whatsapp = []
            st.rerun()

# ============================================================
# TAB 7: VEHÍCULOS (ficha digital / historial de piezas)
# ============================================================
with tab7:
    st.subheader("🚗 Ficha digital del vehículo")
    st.caption(
        "Registrá la patente de un cliente frecuente junto con las piezas que le fuiste cambiando. "
        "La app avisa cuándo una pieza ya recorrió casi toda su vida útil estimada."
    )

    vehiculos_atrasados = listar_vehiculos_atrasados()
    with st.expander(f"⚠️ Vehículos con mantenimiento atrasado ({len(vehiculos_atrasados)})", expanded=bool(vehiculos_atrasados)):
        if not vehiculos_atrasados:
            st.caption(
                "Ninguno detectado por ahora (o todavía no cargaste km de registro/actual en los vehículos)."
            )
        else:
            st.caption("Ordenados por urgencia — el que tiene la pieza más atrasada aparece primero.")
            for item in vehiculos_atrasados:
                v = item["vehiculo"]
                nombre_auto = f"{v.get('marca_auto') or ''} {v.get('modelo_auto') or ''}".strip()
                piezas_txt = ", ".join(f"{p['Pieza']} (x{p['Atraso estimado']})" for p in item["piezas_atrasadas"])
                colv1, colv2 = st.columns([4, 1])
                colv1.write(f"**{v['patente']}** {nombre_auto} — {v.get('cliente_nombre') or 'sin nombre'}")
                colv1.caption(f"Atrasado: {piezas_txt}")
                if colv2.button("👁️ Ver", key=f"ver_atrasado_{v['id']}"):
                    st.session_state["patente_buscar"] = v["patente"]
                    st.rerun()

    st.markdown("---")
    st.markdown("**Buscar / registrar un vehículo**")

    with st.expander("📷 Cargar por foto de cédula/título (con IA)"):
        st.caption(
            "Sacale una foto a la cédula verde/azul o al título. La IA lee patente, marca, modelo, "
            "año y motorización — **siempre revisá los datos antes de guardar**, un OCR puede "
            "confundir letras o números parecidos."
        )
        foto_cedula = st.file_uploader("Foto de la cédula/título:", type=["png", "jpg", "jpeg"], key="foto_cedula")
        if foto_cedula and st.button("🔍 Leer datos"):
            with st.spinner("Leyendo..."):
                datos_cedula, error_cedula = extraer_datos_cedula(foto_cedula.getvalue())
            if error_cedula:
                st.error(error_cedula)
            else:
                st.session_state["datos_cedula_leidos"] = datos_cedula
        if st.session_state.get("datos_cedula_leidos"):
            datos = st.session_state["datos_cedula_leidos"]
            st.json(datos)
            if st.button("✅ Usar estos datos"):
                st.session_state["cedula_pendiente"] = datos
                st.session_state.pop("datos_cedula_leidos", None)
                st.rerun()

    # Si se leyó una cédula, precargar los campos ANTES de crear los widgets — si se hace
    # después de que ya se dibujaron en pantalla, Streamlit tira un error.
    if "cedula_pendiente" in st.session_state:
        datos = st.session_state.pop("cedula_pendiente")
        if datos.get("patente"):
            st.session_state["patente_buscar"] = str(datos["patente"]).strip().upper()
        st.session_state["form_marca_auto"] = datos.get("marca") or ""
        st.session_state["form_modelo_auto"] = datos.get("modelo") or ""
        st.session_state["form_anio_auto"] = str(datos.get("anio") or "")
        st.session_state["form_motorizacion_auto"] = datos.get("motorizacion") or ""

    patente_input = st.text_input("Patente:", placeholder="Ej: AB123CD", key="patente_buscar").strip().upper()

    if patente_input:
        vehiculo = buscar_vehiculo(patente_input)

        with st.expander("✏️ Datos del cliente / vehículo", expanded=(vehiculo is None)):
            with st.form("form_vehiculo"):
                cv1, cv2 = st.columns(2)
                cliente_nombre = cv1.text_input("Nombre del cliente", value=(vehiculo or {}).get("cliente_nombre") or "")
                cliente_tel = cv2.text_input("Teléfono", value=(vehiculo or {}).get("cliente_telefono") or "")
                cv3, cv4 = st.columns(2)
                marca_auto = cv3.text_input("Marca del auto", value=(vehiculo or {}).get("marca_auto") or "",
                                             key="form_marca_auto")
                modelo_auto = cv4.text_input("Modelo", value=(vehiculo or {}).get("modelo_auto") or "",
                                              key="form_modelo_auto")
                cv5, cv6, cv7 = st.columns(3)
                anio_auto = cv5.text_input("Año", value=(vehiculo or {}).get("anio") or "", key="form_anio_auto")
                motorizacion_auto = cv6.text_input("Motorización", value=(vehiculo or {}).get("motorizacion") or "",
                                                    key="form_motorizacion_auto")
                km_actual_input = cv7.number_input(
                    "Km actual", min_value=0, step=1000,
                    value=int((vehiculo or {}).get("km_actual") or 0)
                )
                guardar_vehiculo = st.form_submit_button("💾 Guardar vehículo", type="primary")
            if guardar_vehiculo:
                get_or_create_vehiculo(patente_input, cliente_nombre, cliente_tel, marca_auto, modelo_auto,
                                        km_actual_input or None, anio_auto, motorizacion_auto)
                st.success(f"Vehículo {patente_input} guardado.")
                st.rerun()

        vehiculo = buscar_vehiculo(patente_input)
        if vehiculo:
            km_actual = vehiculo.get("km_actual")
            km_registro = vehiculo.get("km_registro")
            st.write(
                f"**{vehiculo.get('marca_auto') or ''} {vehiculo.get('modelo_auto') or ''}** — "
                f"Cliente: {vehiculo.get('cliente_nombre') or 'sin nombre'}"
            )

            km_calc = calcular_km_recorridos(vehiculo)
            mk1, mk2, mk3 = st.columns(3)
            mk1.metric("Km de registro", km_registro if km_registro is not None else "—")
            mk2.metric("Km actual", km_actual if km_actual is not None else "—")
            mk3.metric("Km recorridos", km_calc["km_recorridos"] if km_calc["km_recorridos"] is not None else "—")
            if km_calc["promedio_mensual"] is not None:
                st.caption(
                    f"📈 Promedio aproximado: **{km_calc['promedio_mensual']:,} km/mes** "
                    f"(en base a {km_calc['dias_transcurridos']} día(s) desde que se registró el vehículo)."
                )

            with st.expander("✏️ Corregir km de registro (solo si se cargó mal la primera vez)"):
                st.caption(
                    "El km de registro queda fijo automáticamente la primera vez que cargás el vehículo. "
                    "Usá esto solo para corregir un error de tipeo — cambiarlo afecta los cálculos de abajo."
                )
                nuevo_km_registro = st.number_input(
                    "Km de registro correcto", min_value=0, step=1000,
                    value=int(km_registro or 0), key="corregir_km_registro"
                )
                if st.button("💾 Corregir km de registro"):
                    actualizar_km_registro(vehiculo["id"], nuevo_km_registro or None)
                    st.success("Km de registro actualizado.")
                    st.rerun()

            alertas = []
            if km_actual is not None:
                alertas = calcular_alertas_vehiculo(vehiculo["id"], km_actual)
                if alertas:
                    st.warning(f"⚠️ {len(alertas)} pieza(s) cerca de cumplir su vida útil estimada:")
                    st.dataframe(alertas, use_container_width=True, hide_index=True)
                else:
                    st.info("Sin alertas de mantenimiento por ahora.")

            st.markdown("---")
            st.markdown("**➕ Agregar pieza al historial**")
            with st.form("form_pieza", clear_on_submit=True):
                cp1, cp2 = st.columns(2)
                desc_pieza = cp1.text_input("Descripción de la pieza", placeholder="Ej: Kit de distribución")
                marca_pieza = cp2.text_input("Marca de la pieza", placeholder="Ej: SKF")
                cp3, cp4, cp5 = st.columns(3)
                codigo_pieza = cp3.text_input("Código (opcional)")
                km_instalacion = cp4.number_input("Km al instalarla", min_value=0, step=1000,
                                                    value=int(km_actual or 0))
                vida_util = cp5.number_input("Vida útil estimada (km, opcional)", min_value=0, step=5000, value=0)
                nota_pieza = st.text_input("Nota (opcional)")
                agregar_pieza = st.form_submit_button("➕ Agregar al historial", type="primary")
            if agregar_pieza:
                if not desc_pieza.strip():
                    st.warning("Completá la descripción de la pieza.")
                else:
                    agregar_pieza_historial(vehiculo["id"], desc_pieza, marca_pieza, codigo_pieza,
                                             km_instalacion or None, vida_util or None, nota_pieza)
                    st.success("Pieza agregada al historial.")
                    st.rerun()

            st.markdown("---")
            st.markdown("**📋 Historial completo**")
            historial_vehiculo = listar_historial_vehiculo(vehiculo["id"])
            if historial_vehiculo:
                st.dataframe(quitar_id(historial_vehiculo), use_container_width=True, hide_index=True)
            else:
                st.caption("Todavía no hay piezas registradas para este vehículo.")

            st.markdown("---")
            st.markdown("**🔧 Proyección de mantenimiento**")
            st.caption(
                "Compara, para cada tipo de pieza con vida útil cargada, cuántas veces se cambió "
                "realmente contra cuántas veces debería haberse cambiado según los km recorridos "
                "totales desde que se registró el vehículo."
            )
            proyeccion = []
            if km_calc["km_recorridos"] is None:
                st.info(
                    "Para calcular esto hace falta el km de registro y el km actual del vehículo "
                    "(completá 'Kilometraje actual' arriba si todavía no lo cargaste)."
                )
            else:
                proyeccion = calcular_proyeccion_mantenimiento(vehiculo["id"], km_calc["km_recorridos"])
                if proyeccion:
                    atrasadas = [p for p in proyeccion if p["Atraso estimado"] > 0]
                    if atrasadas:
                        st.warning(f"⚠️ {len(atrasadas)} pieza(s) con cambios atrasados según el kilometraje:")
                    st.dataframe(proyeccion, use_container_width=True, hide_index=True)
                else:
                    st.caption("Todavía no hay piezas con vida útil cargada para proyectar.")
                    atrasadas = []

            st.markdown("---")
            st.markdown("**📤 Compartir con el cliente**")
            col_pdf, col_wa = st.columns(2)
            with col_pdf:
                st.download_button(
                    "📄 Descargar ficha en PDF",
                    data=generar_pdf_ficha_vehiculo(vehiculo, km_calc, alertas, proyeccion, historial_vehiculo),
                    file_name=f"ficha_{vehiculo['patente']}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            with col_wa:
                if proyeccion and atrasadas:
                    nombre_cliente = vehiculo.get("cliente_nombre") or ""
                    nombre_auto_msg = f"{vehiculo.get('marca_auto') or ''} {vehiculo.get('modelo_auto') or ''}".strip()
                    piezas_atrasadas_txt = ", ".join(p["Pieza"] for p in atrasadas)
                    mensaje_wa = (
                        f"Hola {nombre_cliente}! Te escribimos de El Chavo. Revisando el kilometraje de tu "
                        f"{nombre_auto_msg} ({vehiculo['patente']}), notamos que tenés atrasado el cambio de: "
                        f"{piezas_atrasadas_txt}. ¿Coordinamos un turno?"
                    ).strip()
                    tel_limpio = re.sub(r"\D", "", vehiculo.get("cliente_telefono") or "")
                    url_wa_vehiculo = (
                        f"https://wa.me/{tel_limpio}" if tel_limpio else "https://wa.me/"
                    ) + "?text=" + quote(mensaje_wa)
                    st.link_button("📲 Avisar atraso por WhatsApp", url_wa_vehiculo,
                                    type="primary", use_container_width=True)
                else:
                    st.caption("Sin atrasos detectados todavía para avisar por WhatsApp.")

# ============================================================
# TAB 8: MODO MECÁNICO
# ============================================================
with tab8:
    st.subheader("🛠️ Modo Mecánico")

    sub_dtc, sub_vin, sub_esq, sub_conv = st.tabs(
        ["📖 Códigos DTC", "🔢 Lector de VIN", "🗺️ Esquemas", "🧮 Conversor de unidades"]
    )

    # -------- Diccionario de códigos OBD2 / DTC --------
    with sub_dtc:
        st.caption(
            f"Diccionario de códigos de falla OBD2/DTC. Arranca con {contar_dtc()} códigos genéricos "
            "estándar (no específicos de marca) — sumá los que te falten con el formulario de abajo. "
            "Los códigos P1xxx u otros específicos de fabricante se cargan indicando la marca, porque "
            "el mismo número puede significar algo distinto según el auto."
        )
        fabricantes_dtc = ["Todos", "Genérico"] + listar_fabricantes_dtc()
        cdb1, cdb2 = st.columns([2, 1])
        codigo_buscar = cdb1.text_input("Buscar código:", placeholder="Ej: P0301 o P1105", key="dtc_buscar")
        filtro_fab_dtc = cdb2.selectbox("Fabricante:", fabricantes_dtc, key="dtc_filtro_fab")
        if codigo_buscar.strip():
            res_dtc = buscar_dtc(codigo_buscar, filtro_fab_dtc)
            if res_dtc:
                st.dataframe(res_dtc, use_container_width=True, hide_index=True)
            else:
                st.warning("No tengo ese código cargado todavía (con ese filtro de fabricante). Podés agregarlo abajo.")

        with st.expander("➕ Agregar / corregir un código"):
            st.caption("Dejá 'Fabricante' vacío si es un código genérico (P0xxx). Completalo si es específico de una marca (ej: Ford, Toyota).")
            with st.form("form_dtc", clear_on_submit=True):
                cd1, cd2, cd3 = st.columns(3)
                nuevo_codigo = cd1.text_input("Código (ej: P0301)")
                nuevo_fabricante = cd2.text_input("Fabricante (opcional)", placeholder="Ej: Ford")
                nuevo_sistema = cd3.text_input("Sistema (ej: Motor, Transmisión)")
                nueva_desc = st.text_input("Descripción")
                nuevas_causas = st.text_input("Causas posibles (opcional)")
                guardar_dtc_btn = st.form_submit_button("💾 Guardar código", type="primary")
            if guardar_dtc_btn:
                if not nuevo_codigo.strip() or not nueva_desc.strip():
                    st.warning("Completá al menos el código y la descripción.")
                else:
                    agregar_dtc(nuevo_codigo, nueva_desc, nuevo_sistema, nuevas_causas, nuevo_fabricante)
                    etiqueta_fab = f" ({nuevo_fabricante.strip()})" if nuevo_fabricante.strip() else " (genérico)"
                    st.success(f"Código {nuevo_codigo.upper()}{etiqueta_fab} guardado.")
                    st.rerun()

        with st.expander("📋 Carga masiva de códigos (pegar texto)"):
            st.caption(
                "Un código por línea, formato: `codigo;descripción;sistema;causas;fabricante` "
                "(sistema, causas y fabricante son opcionales — dejá fabricante vacío para códigos genéricos)."
            )
            texto_dtc = st.text_area("Pegá los códigos acá:", height=150, key="dtc_masivo",
                                      placeholder="P0455;Fuga grande en sistema EVAP;Emisiones;Tapa de nafta, manguera\n"
                                                   "P1105;Solenoide de presión de combustible;Motor;;Chrysler")
            if st.button("📥 Importar códigos"):
                if texto_dtc.strip():
                    cargados_dtc = importar_dtc_masivo(texto_dtc)
                    st.success(f"Se cargaron/actualizaron {cargados_dtc} código(s).")
                    st.rerun()
                else:
                    st.warning("Pegá al menos un código.")

    # -------- Lector de VIN --------
    with sub_vin:
        st.caption(
            "Decodifica el país de fabricación y año a partir del VIN (estándar ISO 3779). "
            "El fabricante exacto por WMI (los primeros 3 caracteres) lo tenés que cargar vos, "
            "ya que varía mucho según los modelos que manejes."
        )
        vin_input = st.text_input("VIN (17 caracteres):", placeholder="Ej: 9BWZZZ377VT004251", key="vin_input")
        if vin_input.strip():
            datos_vin = decodificar_vin(vin_input)
            if not datos_vin["valido"]:
                st.error(datos_vin["error"])
            else:
                cv1, cv2, cv3 = st.columns(3)
                cv1.metric("WMI", datos_vin["wmi"])
                cv2.metric("País", datos_vin["pais"])
                cv3.metric("Año estimado", datos_vin["anio_estimado"] or "—")
                if datos_vin["fabricante"]:
                    st.success(f"Fabricante cargado para este WMI: **{datos_vin['fabricante']}**")
                else:
                    st.info(
                        "Ese WMI todavía no está cargado en la base de fabricantes. "
                        "Si lo conocés, agregalo abajo para la próxima vez."
                    )

        with st.expander("➕ Agregar fabricante por WMI"):
            with st.form("form_vin_fab", clear_on_submit=True):
                cw1, cw2, cw3 = st.columns(3)
                nuevo_wmi = cw1.text_input("WMI (3 caracteres)", max_chars=3, placeholder="Ej: 9BW")
                nuevo_fabricante = cw2.text_input("Fabricante", placeholder="Ej: Volkswagen Argentina")
                nuevo_pais_vin = cw3.text_input("País (opcional)", placeholder="Ej: Argentina")
                guardar_vin_btn = st.form_submit_button("💾 Guardar", type="primary")
            if guardar_vin_btn:
                if len(nuevo_wmi.strip()) != 3 or not nuevo_fabricante.strip():
                    st.warning("El WMI debe tener 3 caracteres y el fabricante es obligatorio.")
                else:
                    agregar_fabricante_vin(nuevo_wmi, nuevo_fabricante, nuevo_pais_vin)
                    st.success(f"WMI {nuevo_wmi.upper()} guardado.")
                    st.rerun()

        fabricantes_cargados = listar_fabricantes_vin()
        if fabricantes_cargados:
            with st.expander(f"📋 Fabricantes cargados ({len(fabricantes_cargados)})"):
                st.dataframe(fabricantes_cargados, use_container_width=True, hide_index=True)

    # -------- Visor de esquemas --------
    CATEGORIAS_ESQUEMA = [
        "Motor", "Refrigeración", "Retenes y juntas", "Frenos", "Suspensión", "Dirección",
        "Transmisión", "Embrague", "Correas y distribución", "Eléctrico", "Combustible",
        "Escape", "Aire acondicionado", "Otro"
    ]

    def mostrar_lista_esquemas(lista_esq):
        if not lista_esq:
            st.caption("No hay esquemas cargados acá todavía.")
            return
        for esq in lista_esq:
            titulo_expander = f"🗺️ {esq['titulo']}" + (" 🤖 (orientativo, generado por IA)" if esq.get("generado_ia") else "")
            with st.expander(titulo_expander):
                if esq.get("generado_ia"):
                    st.warning(
                        "🤖 Esta imagen fue generada por IA como referencia orientativa — "
                        "NO es una foto real de este vehículo. No la uses para identificar piezas con precisión."
                    )
                if esq.get("descripcion"):
                    st.write(esq["descripcion"])
                img_bytes = obtener_imagen_esquema(esq["id"])
                puntos = listar_puntos_esquema(esq["id"])
                if img_bytes:
                    imagen_a_mostrar = generar_imagen_con_marcadores(img_bytes, puntos)
                    st.image(imagen_a_mostrar, use_container_width=True)
                    if any(p.get("pos_x") is not None for p in puntos):
                        st.caption("Los números marcados en la foto corresponden a la lista de piezas de abajo.")

                # Piezas marcadas en el esquema, con búsqueda directa por código
                if puntos:
                    st.markdown("**🔩 Piezas de este esquema**")
                    for punto in puntos:
                        etiqueta = f"{punto['numero']}. " if punto.get("numero") else ""
                        cp1, cp2 = st.columns([3, 1])
                        cp1.write(f"{etiqueta}{punto['nombre_pieza']}" + (f" — `{punto['codigo']}`" if punto.get("codigo") else ""))
                        if punto.get("codigo"):
                            if cp2.button("🔍 Buscar", key=f"buscar_punto_{punto['id']}"):
                                clean_punto = sanitizar(punto["codigo"])
                                res_punto = buscar_por_codigo(clean_punto) if clean_punto else []
                                if not res_punto:
                                    res_punto = buscar_por_texto(punto["nombre_pieza"])
                                if res_punto:
                                    st.dataframe(quitar_id(res_punto), use_container_width=True, hide_index=True)
                                else:
                                    st.error(f"No encontré '{punto['codigo']}' ni '{punto['nombre_pieza']}' en la base.")
                        if es_admin():
                            if cp2.button("🗑️", key=f"del_punto_{punto['id']}"):
                                eliminar_punto_esquema(punto["id"])
                                st.rerun()

                if es_operador_o_admin():
                    with st.expander("➕ Agregar pieza a este esquema"):
                        if img_bytes:
                            st.caption(
                                "Mirá la foto de arriba y estimá en qué parte está la pieza: "
                                "0% = borde izquierdo/superior, 100% = borde derecho/inferior."
                            )
                        cpp1, cpp2, cpp3 = st.columns([1, 2, 2])
                        num_punto = cpp1.text_input("N°", key=f"num_punto_{esq['id']}", placeholder="1")
                        nombre_punto = cpp2.text_input("Nombre de la pieza", key=f"nombre_punto_{esq['id']}")
                        codigo_punto = cpp3.text_input("Código (opcional)", key=f"codigo_punto_{esq['id']}")
                        marcar_posicion = st.checkbox(
                            "Marcar posición en la foto", value=bool(img_bytes), key=f"marcar_pos_{esq['id']}",
                            disabled=not img_bytes
                        )
                        pos_x_punto, pos_y_punto = None, None
                        if marcar_posicion and img_bytes:
                            cpx, cpy = st.columns(2)
                            pos_x_punto = cpx.slider("Posición horizontal (%)", 0, 100, 50, key=f"posx_{esq['id']}")
                            pos_y_punto = cpy.slider("Posición vertical (%)", 0, 100, 50, key=f"posy_{esq['id']}")
                            vista_previa = generar_imagen_con_marcadores(
                                img_bytes,
                                puntos + [{"numero": num_punto or "?", "pos_x": pos_x_punto, "pos_y": pos_y_punto}]
                            )
                            st.image(vista_previa, use_container_width=True, caption="Vista previa de dónde quedaría el marcador")
                        if st.button("💾 Agregar pieza", key=f"agregar_punto_{esq['id']}"):
                            if not nombre_punto.strip():
                                st.warning("Completá el nombre de la pieza.")
                            else:
                                vinculado = agregar_punto_esquema(
                                    esq["id"], num_punto, nombre_punto, codigo_punto, pos_x_punto, pos_y_punto
                                )
                                if codigo_punto.strip() and not vinculado:
                                    st.info(
                                        "Pieza agregada. El código no coincide con ningún producto cargado "
                                        "todavía, pero igual queda guardado como referencia."
                                    )
                                else:
                                    st.success("Pieza agregada.")
                                st.rerun()

                    if st.button("🗑️ Eliminar este esquema", key=f"del_esq_{esq['id']}"):
                        eliminar_esquema(esq["id"])
                        st.rerun()

    with sub_esq:
        st.caption(
            "Diagramas organizados por Marca › Vehículo › Sistema, donde cada pieza marcada tiene "
            "su código vinculado al catálogo — así se busca directo desde el dibujo, ya sea en el "
            "taller o en el mostrador de una casa de repuestos. Las imágenes las tenés que subir vos."
        )
        modo_esq = st.radio(
            "¿Cómo lo buscás?", ["📂 Explorar por categoría", "🔎 Buscar por texto"],
            horizontal=True, key="modo_esquemas"
        )

        if modo_esq.startswith("📂"):
            marcas_esq = listar_marcas_esquemas()
            if not marcas_esq:
                st.info("Todavía no hay esquemas cargados con marca definida. Subí el primero más abajo.")
            else:
                marca_sel = st.selectbox("Marca:", marcas_esq, key="esq_marca_sel")
                modelos_esq = listar_modelos_esquemas(marca_sel)
                if not modelos_esq:
                    st.caption(f"No hay vehículos cargados todavía para {marca_sel}.")
                else:
                    modelo_sel = st.selectbox("Vehículo / modelo:", modelos_esq, key="esq_modelo_sel")
                    sistemas_esq = listar_sistemas_esquemas(marca_sel, modelo_sel)
                    if not sistemas_esq:
                        st.caption("No hay esquemas con sistema/parte definida para este vehículo.")
                    else:
                        sistema_sel = st.selectbox("Sistema / parte:", sistemas_esq, key="esq_sistema_sel")
                        mostrar_lista_esquemas(listar_esquemas_por_categoria(marca_sel, modelo_sel, sistema_sel))
        else:
            filtro_esq = st.text_input("Buscar esquema (título, marca, modelo o sistema):", key="esq_filtro")
            mostrar_lista_esquemas(listar_esquemas(filtro_esq))

        st.markdown("---")
        if not pedir_password_admin("subir esquemas nuevos"):
            pass
        else:
            marcas_existentes = listar_marcas_esquemas()

            st.markdown("**🚗 Precargar marca / vehículo (sin imagen todavía)**")
            st.caption(
                "Dejá lista la estructura del árbol aunque todavía no tengas ningún esquema para subir — "
                "va a aparecer en 'Explorar por categoría' apenas la guardes."
            )
            cp1, cp2 = st.columns(2)
            if marcas_existentes:
                marca_pre_opcion = cp1.selectbox("Marca", marcas_existentes + ["➕ Nueva marca..."], key="pre_marca_opcion")
                marca_pre = cp1.text_input("Nombre de la nueva marca", key="pre_marca_nueva") \
                    if marca_pre_opcion == "➕ Nueva marca..." else marca_pre_opcion
            else:
                marca_pre = cp1.text_input("Marca", key="pre_marca_sola")
            modelo_pre = cp2.text_input("Vehículo / modelo", placeholder="Ej: Corsa", key="pre_modelo")
            if st.button("➕ Precargar"):
                if not marca_pre.strip() or not modelo_pre.strip():
                    st.warning("Completá marca y modelo.")
                else:
                    agregar_vehiculo_catalogo(marca_pre, modelo_pre)
                    st.success(f"{marca_pre.strip()} {modelo_pre.strip()} precargado.")
                    for k in ["pre_marca_nueva", "pre_marca_sola", "pre_modelo"]:
                        st.session_state.pop(k, None)
                    st.rerun()

            precargados = listar_catalogo_precargado()
            if precargados:
                with st.expander(f"📋 Ver / borrar precargados sin esquema todavía ({len(precargados)})"):
                    for pv in precargados:
                        colp1, colp2 = st.columns([4, 1])
                        colp1.write(f"{pv['marca']} — {pv['modelo']}")
                        if colp2.button("🗑️", key=f"del_precarga_{pv['marca']}_{pv['modelo']}"):
                            eliminar_vehiculo_catalogo(pv["marca"], pv["modelo"])
                            st.rerun()

            st.markdown("---")
            st.markdown("**➕ Subir un esquema nuevo**")
            marcas_existentes = listar_marcas_esquemas()  # puede haber cambiado si acabás de precargar una
            titulo_esq = st.text_input("Título", placeholder="Ej: Esquema eléctrico bomba de combustible", key="esq_titulo")
            ce1, ce2 = st.columns(2)
            if marcas_existentes:
                marca_opcion = ce1.selectbox("Marca", marcas_existentes + ["➕ Nueva marca..."], key="esq_marca_opcion")
                marca_esq = ce1.text_input("Nombre de la nueva marca", key="esq_marca_nueva") \
                    if marca_opcion == "➕ Nueva marca..." else marca_opcion
            else:
                marca_esq = ce1.text_input("Marca del auto", key="esq_marca_sola")
            modelos_para_marca = listar_modelos_esquemas(marca_esq) if marca_esq else []
            if modelos_para_marca:
                modelo_opcion = ce2.selectbox("Vehículo / modelo", modelos_para_marca + ["➕ Nuevo modelo..."], key="esq_modelo_opcion")
                modelo_esq = ce2.text_input("Nombre del nuevo modelo", key="esq_modelo_nuevo") \
                    if modelo_opcion == "➕ Nuevo modelo..." else modelo_opcion
            else:
                modelo_esq = ce2.text_input("Vehículo / modelo", placeholder="Ej: Gol Trend", key="esq_modelo_solo")
            sistema_opcion = st.selectbox("Sistema / parte:", CATEGORIAS_ESQUEMA, key="esq_sistema_opcion")
            sistema_esq = st.text_input("Especificá el sistema/parte:", key="esq_sistema_nuevo") \
                if sistema_opcion == "Otro" else sistema_opcion
            desc_esq = st.text_input("Descripción (opcional)", key="esq_desc")

            origen_imagen = st.radio(
                "¿De dónde sale la imagen?",
                ["📷 Subir foto real", "🤖 Generar orientativo con IA (sin foto real)"],
                key="esq_origen_imagen"
            )

            archivo_esq = None
            imagen_generada_bytes = None
            if origen_imagen.startswith("📷"):
                archivo_esq = st.file_uploader("Imagen del esquema", type=["png", "jpg", "jpeg"], key="esq_archivo")
            else:
                st.caption(
                    "Para cuando no tenés el auto físico enfrente (útil en el mostrador de una casa de "
                    "repuestos): la IA arma un dibujo genérico de referencia, **no una foto real de ese "
                    "vehículo**. Sirve para orientar, no para identificar piezas con precisión milimétrica. "
                    "Usa Gemini — necesita facturación habilitada en la API key (no es gratis, pero el costo "
                    "es bajo, ronda los US$0,04 por imagen)."
                )
                motorizacion_ia = st.text_input("Motorización", placeholder="Ej: 1.6 MSI Nafta", key="esq_motorizacion_ia")
                boton_label = "🔄 Generar otra vez" if st.session_state.get("esq_preview_ia") else "🤖 Generar imagen orientativa"
                if st.button(boton_label):
                    if not marca_esq.strip() or not modelo_esq.strip():
                        st.warning("Completá marca y modelo antes de generar.")
                    else:
                        with st.spinner("Generando..."):
                            img_ia, error_ia = generar_esquema_orientativo_ia(
                                marca_esq, modelo_esq, motorizacion_ia,
                                sistema_esq if sistema_opcion == "Otro" else sistema_opcion
                            )
                        if error_ia:
                            st.error(error_ia)
                        else:
                            st.session_state["esq_preview_ia"] = img_ia
                            st.rerun()
                if st.session_state.get("esq_preview_ia"):
                    st.image(st.session_state["esq_preview_ia"], use_container_width=True,
                              caption="Vista previa — orientativo, no es una foto real")
                    imagen_generada_bytes = st.session_state["esq_preview_ia"]

            subir_esq_btn = st.button("📥 Guardar esquema", type="primary")
            if subir_esq_btn:
                imagen_final = archivo_esq.getvalue() if archivo_esq else imagen_generada_bytes
                nombre_final = archivo_esq.name if archivo_esq else "generado_ia.jpg"
                if not titulo_esq.strip() or not imagen_final or not marca_esq.strip() or not modelo_esq.strip():
                    st.warning("Completá título, marca, modelo, y subí o generá una imagen.")
                elif sistema_opcion == "Otro" and not sistema_esq.strip():
                    st.warning("Especificá el sistema/parte.")
                else:
                    guardar_esquema(titulo_esq, marca_esq, modelo_esq, sistema_esq, desc_esq,
                                     imagen_final, nombre_final, generado_ia=(imagen_generada_bytes is not None))
                    st.success("Esquema guardado.")
                    st.session_state.pop("esq_preview_ia", None)
                    for k in ["esq_titulo", "esq_marca_nueva", "esq_modelo_nuevo", "esq_sistema_nuevo",
                              "esq_desc", "esq_archivo", "esq_motorizacion_ia"]:
                        st.session_state.pop(k, None)
                    st.rerun()

    # -------- Conversor de unidades --------
    with sub_conv:
        st.caption("Conversiones rápidas de unidades que se usan seguido en manuales de taller antiguos o importados.")

        categoria_conv = st.radio("Categoría:", ["Torque", "Presión", "Longitud"], horizontal=True, key="conv_categoria")

        if categoria_conv == "Torque":
            direccion = st.radio("Convertir:", ["lb-ft → Nm", "Nm → lb-ft", "lb-in → Nm", "Nm → lb-in"],
                                  key="conv_torque_dir")
            valor = st.number_input("Valor a convertir:", min_value=0.0, step=0.1, key="conv_torque_valor")
            factores = {
                "lb-ft → Nm": (valor * 1.35582, "Nm"),
                "Nm → lb-ft": (valor / 1.35582, "lb-ft"),
                "lb-in → Nm": (valor * 0.112985, "Nm"),
                "Nm → lb-in": (valor / 0.112985, "lb-in"),
            }
            resultado, unidad = factores[direccion]
            st.metric("Resultado", f"{resultado:.2f} {unidad}")

        elif categoria_conv == "Presión":
            direccion = st.radio("Convertir:", ["PSI → Bar", "Bar → PSI", "PSI → kPa", "kPa → PSI"],
                                  key="conv_presion_dir")
            valor = st.number_input("Valor a convertir:", min_value=0.0, step=0.1, key="conv_presion_valor")
            factores = {
                "PSI → Bar": (valor * 0.0689476, "Bar"),
                "Bar → PSI": (valor / 0.0689476, "PSI"),
                "PSI → kPa": (valor * 6.89476, "kPa"),
                "kPa → PSI": (valor / 6.89476, "PSI"),
            }
            resultado, unidad = factores[direccion]
            st.metric("Resultado", f"{resultado:.2f} {unidad}")

        else:  # Longitud
            direccion = st.radio("Convertir:", ["Pulgadas → mm", "mm → Pulgadas", "Pulgadas → cm", "cm → Pulgadas"],
                                  key="conv_longitud_dir")
            valor = st.number_input("Valor a convertir:", min_value=0.0, step=0.1, key="conv_longitud_valor")
            factores = {
                "Pulgadas → mm": (valor * 25.4, "mm"),
                "mm → Pulgadas": (valor / 25.4, "pulgadas"),
                "Pulgadas → cm": (valor * 2.54, "cm"),
                "cm → Pulgadas": (valor / 2.54, "pulgadas"),
            }
            resultado, unidad = factores[direccion]
            st.metric("Resultado", f"{resultado:.3f} {unidad}")

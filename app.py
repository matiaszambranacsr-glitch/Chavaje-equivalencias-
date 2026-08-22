import streamlit as st
import sqlite3
import re
import io
import threading
from datetime import datetime
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

/* Pestañas */
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--border); }
.stTabs [data-baseweb="tab"] {
  font-family: 'Space Grotesk', sans-serif; font-weight: 600; font-size: 0.86rem;
  color: var(--text-muted); background: transparent; border-radius: 8px 8px 0 0; padding: 10px 14px;
}
.stTabs [aria-selected="true"] { color: var(--accent) !important; border-bottom: 2px solid var(--accent) !important; }

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

/* Inputs */
.stTextInput input, .stNumberInput input, .stTextArea textarea,
.stSelectbox div[data-baseweb="select"] > div {
  background: var(--bg-panel) !important; border: 1px solid var(--border) !important;
  border-radius: 7px !important; color: var(--text) !important;
}
.stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus {
  border-color: var(--accent) !important; box-shadow: 0 0 0 1px var(--accent) !important;
}

/* Expanders */
[data-testid="stExpander"] { border: 1px solid var(--border) !important; border-radius: 8px !important; }
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
hr { border-color: var(--border) !important; }
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
    return st.session_state.get("es_admin", False)


def pedir_password_admin(motivo=""):
    """Muestra un formulario de contraseña. Devuelve True si ya está autenticado."""
    if es_admin():
        return True

    st.warning(f"🔒 Esta sección está protegida{(' — ' + motivo) if motivo else ''}.")
    with st.form(f"login_admin_{motivo}"):
        clave = st.text_input("Contraseña de administrador:", type="password")
        entrar = st.form_submit_button("Ingresar")

    if entrar:
        secretos = st.secrets if hasattr(st, "secrets") else {}
        # Soporta varias contraseñas con nombre, por ejemplo en Secrets:
        # [admin_passwords]
        # matias = "clave123"
        # socio = "otraclave456"
        # También soporta la forma anterior de una sola clave (admin_password) por compatibilidad.
        passwords_nombradas = dict(secretos.get("admin_passwords", {}))
        clave_unica = secretos.get("admin_password")
        if clave_unica:
            passwords_nombradas.setdefault("admin", clave_unica)

        if not passwords_nombradas:
            st.error(
                "No configuraste todavía ninguna contraseña de administrador en Streamlit Cloud "
                "(Settings → Secrets). Sin eso, nadie puede entrar a esta sección."
            )
        else:
            nombre_coincidente = next((n for n, p in passwords_nombradas.items() if p == clave), None)
            if nombre_coincidente:
                st.session_state.es_admin = True
                st.session_state.admin_nombre = nombre_coincidente
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
    return False


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
        created_at TEXT DEFAULT (datetime('now'))
    )""")

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
        fecha TEXT DEFAULT (datetime('now'))
    )""")

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
    if "diametro_interno" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN diametro_interno REAL")
    if "diametro_externo" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN diametro_externo REAL")
    if "ancho" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN ancho REAL")
    if "paso_rosca" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN paso_rosca TEXT")
    if "cantidad_estrias" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN cantidad_estrias INTEGER")
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
        km_registro INTEGER,
        km_actual INTEGER,
        km_actualizado_fecha TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")

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
        created_at TEXT DEFAULT (datetime('now'))
    )""")

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
           p.favorito AS "Favorito", p.imagen_url AS "Imagen"
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


def buscar_por_texto(texto):
    like = f"%{texto.upper()}%"
    query = '''
    SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
           m.nombre AS "Marca", m.tipo AS "Tipo", p.precio AS "Precio", p.stock AS "Stock",
           p.favorito AS "Favorito"
    FROM productos p JOIN marcas m ON m.id = p.marca_id
    WHERE UPPER(p.descripcion) LIKE ? OR UPPER(p.codigo_raw) LIKE ?
    ORDER BY m.nombre LIMIT 200;
    '''
    with db_lock:
        c.execute(query, (like, like))
        return filas_a_listas(c)


def identificar_pieza_por_foto(imagen_bytes):
    """Le manda una foto a Gemini y le pide que identifique la pieza. Devuelve texto libre."""
    from google import genai
    from google.genai import types

    api_key = st.secrets.get("gemini_api_key") if hasattr(st, "secrets") else None
    if not api_key:
        return None, "No configuraste 'gemini_api_key' en Streamlit Cloud (Settings → Secrets)."

    try:
        client = genai.Client(api_key=api_key)
        prompt = (
            "Esta es una foto de un repuesto de auto tomada en un taller o local de repuestos. "
            "Identificá, si podés: 1) cualquier código o marca visible impresa/grabada en la pieza, "
            "2) qué tipo de repuesto es (ej: filtro de aceite, bomba de agua, correa, etc). "
            "Respondé corto y directo, en español, solo con esos datos. Si no distinguís nada con claridad, decilo."
        )
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=[
                prompt,
                types.Part.from_bytes(data=imagen_bytes, mime_type="image/jpeg"),
            ],
        )
        return response.text, None
    except Exception as e:
        return None, f"Error consultando a Gemini: {e}"


def actualizar_precio_stock(producto_id, precio, stock):
    with db_lock:
        c.execute("UPDATE productos SET precio = ?, stock = ? WHERE id = ?", (precio, stock, producto_id))
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


def guardar_busqueda(termino):
    with db_lock:
        c.execute("INSERT INTO historial_busquedas (termino) VALUES (?)", (termino,))
        conn.commit()


def historial_reciente(limite=10):
    c.execute("SELECT DISTINCT termino FROM historial_busquedas ORDER BY id DESC LIMIT ?", (limite,))
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


def generar_pdf_cotizacion(lista_productos, incluir_precio=True, incluir_stock=False):
    """Genera un PDF simple de cotización a partir de la lista armada para WhatsApp."""
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
            pdf.multi_cell(0, 6, limpiar(linea))
        pdf.ln(3)

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
def get_or_create_vehiculo(patente, cliente_nombre="", cliente_telefono="", marca_auto="", modelo_auto="", km_actual=None):
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
                "km_actual = COALESCE(?, km_actual), "
                "km_registro = COALESCE(km_registro, ?), "  # solo se fija si todavía no tenía uno
                "km_actualizado_fecha = CASE WHEN ? IS NOT NULL THEN datetime('now') ELSE km_actualizado_fecha END "
                "WHERE id = ?",
                (cliente_nombre.strip(), cliente_telefono.strip(), marca_auto.strip(), modelo_auto.strip(),
                 km_actual, km_actual, km_actual, vid)
            )
        else:
            c.execute(
                "INSERT INTO vehiculos (patente, cliente_nombre, cliente_telefono, marca_auto, modelo_auto, "
                "km_registro, km_actual, km_actualizado_fecha) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
                (patente, cliente_nombre.strip(), cliente_telefono.strip(), marca_auto.strip(),
                 modelo_auto.strip(), km_actual, km_actual)
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
def buscar_por_medidas(diam_int=None, diam_ext=None, ancho=None, paso_rosca=None, estrias=None, tolerancia_pct=5):
    condiciones = []
    params = []

    def rango(valor, campo):
        if valor:
            tol = valor * tolerancia_pct / 100.0
            condiciones.append(f"p.{campo} BETWEEN ? AND ?")
            params.extend([valor - tol, valor + tol])

    rango(diam_int, "diametro_interno")
    rango(diam_ext, "diametro_externo")
    rango(ancho, "ancho")
    if paso_rosca:
        condiciones.append("UPPER(p.paso_rosca) = ?")
        params.append(paso_rosca.strip().upper())
    if estrias:
        condiciones.append("p.cantidad_estrias = ?")
        params.append(estrias)

    if not condiciones:
        return []

    query = f"""SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion", m.nombre AS "Marca",
                p.diametro_interno AS "Diám. interno", p.diametro_externo AS "Diám. externo", p.ancho AS "Ancho",
                p.paso_rosca AS "Paso de rosca", p.cantidad_estrias AS "Estrías",
                p.precio AS "Precio", p.stock AS "Stock"
                FROM productos p JOIN marcas m ON m.id = p.marca_id
                WHERE {" AND ".join(condiciones)} ORDER BY m.nombre LIMIT 100"""
    c.execute(query, params)
    return filas_a_listas(c)


def actualizar_medidas(producto_id, diam_int, diam_ext, ancho, paso_rosca, estrias, ubicacion):
    with db_lock:
        c.execute(
            "UPDATE productos SET diametro_interno=?, diametro_externo=?, ancho=?, paso_rosca=?, "
            "cantidad_estrias=?, ubicacion=? WHERE id=?",
            (diam_int or None, diam_ext or None, ancho or None, (paso_rosca.strip() or None) if paso_rosca else None,
             estrias or None, (ubicacion.strip() or None) if ubicacion else None, producto_id)
        )
        conn.commit()


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
def guardar_esquema(titulo, marca_auto, modelo_auto, sistema, descripcion, imagen_bytes, imagen_nombre):
    with db_lock:
        c.execute(
            "INSERT INTO esquemas (titulo, marca_auto, modelo_auto, sistema, descripcion, imagen_blob, imagen_nombre) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (titulo.strip(), marca_auto.strip(), modelo_auto.strip(), sistema.strip(), descripcion.strip(),
             imagen_bytes, imagen_nombre)
        )
        conn.commit()


def listar_esquemas(texto_filtro=""):
    if texto_filtro.strip():
        like = f"%{texto_filtro.strip().upper()}%"
        c.execute("""SELECT id, titulo, marca_auto, modelo_auto, sistema, descripcion FROM esquemas
                     WHERE UPPER(titulo) LIKE ? OR UPPER(marca_auto) LIKE ? OR UPPER(modelo_auto) LIKE ?
                        OR UPPER(sistema) LIKE ?
                     ORDER BY marca_auto, modelo_auto""", (like, like, like, like))
    else:
        c.execute("SELECT id, titulo, marca_auto, modelo_auto, sistema, descripcion FROM esquemas "
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

if es_admin():
    col_estado, col_salir = st.columns([4, 1])
    nombre_sesion = st.session_state.get("admin_nombre", "admin")
    col_estado.caption(f"🔓 Sesión de administrador activa ({nombre_sesion}).")
    if col_salir.button("Salir"):
        st.session_state.es_admin = False
        st.session_state.admin_nombre = None
        st.rerun()

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
    if es_admin():
        with st.expander("📷 Identificar pieza por foto (con IA)"):
            st.caption(
                "Sacale una foto a la pieza. La IA intenta leer códigos visibles o describir qué tipo de "
                "repuesto es, y después podés buscar con eso."
            )
            foto = st.camera_input("Sacar foto", label_visibility="collapsed")
            if foto and st.button("🔍 Identificar"):
                with st.spinner("Consultando..."):
                    descripcion, error = identificar_pieza_por_foto(foto.getvalue())
                if error:
                    st.error(error)
                elif descripcion:
                    st.session_state["descripcion_foto"] = descripcion
                    st.info(descripcion)
            if st.session_state.get("descripcion_foto"):
                if st.button("🔍 Buscar con esta descripción"):
                    res_foto = buscar_por_texto(st.session_state["descripcion_foto"])
                    if res_foto:
                        st.success(f"Se encontraron {len(res_foto)} coincidencias:")
                        st.dataframe(quitar_id(res_foto), use_container_width=True, hide_index=True)
                    else:
                        st.warning("No se encontró nada parecido en la base con esa descripción.")

    modo = st.radio("Buscar por:", ["Código", "Descripción"], horizontal=True)

    c.execute("SELECT nombre FROM marcas ORDER BY nombre")
    lista_marcas = ["Todas"] + [r["nombre"] for r in c.fetchall()]

    if modo == "Código":
        with st.form("form_buscar_codigo"):
            col_busq, col_filt = st.columns([3, 1])
            with col_busq:
                busqueda = st.text_input(
                    "Ingresá uno o varios códigos (separados por coma):",
                    placeholder="Ej: W712/94, 036115561G..."
                )
            with col_filt:
                marca_filtro = st.selectbox("Filtrar por marca:", lista_marcas)
            buscar_click = st.form_submit_button("🔍 Buscar Equivalencias", type="primary")

        if buscar_click:
            codigos_buscados = [x.strip() for x in busqueda.split(",") if x.strip()]
            if not codigos_buscados:
                st.info("Ingresá al menos un código válido para buscar.")
            else:
                guardar_busqueda(busqueda.strip())
                catalogos = listar_catalogos_externos()

                for codigo_individual in codigos_buscados:
                    clean = sanitizar(codigo_individual)
                    st.markdown(f"#### 🔎 {codigo_individual}")
                    if not clean:
                        st.info("Código no válido, se omitió.")
                        continue

                    res = buscar_por_codigo(clean, marca_filtro)
                    if res:
                        incrementar_veces_buscado(clean)
                        st.success(f"Se encontraron {len(res)} coincidencias:")
                        mostrar = quitar_id(res)
                        st.dataframe(
                            mostrar, use_container_width=True, hide_index=True,
                            column_config={
                                "Imagen": st.column_config.ImageColumn("Imagen", width="small")
                            }
                        )

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

                        # Marcar favoritos / editar precio y stock
                        with st.expander("✏️ Marcar favorito / editar precio y stock"):
                            for fila in res:
                                colF, colC, colP, colS, colG = st.columns([0.6, 2, 1.3, 1, 0.8])
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
                                    st.rerun()

                        if catalogos:
                            st.caption("Buscar este código también en:")
                            cols = st.columns(len(catalogos))
                            for col, cat in zip(cols, catalogos):
                                with col:
                                    st.link_button(f"🌐 {cat['nombre']}", cat["url"],
                                                    use_container_width=True, key=f"link_{cat['id']}_{clean}")
                    else:
                        st.warning("No hay equivalencias registradas para ese código.")
                        registrar_busqueda_sin_resultado(codigo_individual)
                        parcial = buscar_por_texto(clean)
                        if parcial:
                            st.info("¿Quisiste decir alguno de estos códigos parecidos?")
                            st.dataframe(quitar_id(parcial)[:10], use_container_width=True, hide_index=True)
                    st.markdown("---")
    else:
        with st.form("form_buscar_texto"):
            texto = st.text_input("Ingresá parte de una descripción:", placeholder="Ej: filtro de aceite, bomba...")
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

        if st.button("📐 Buscar por medidas"):
            res_medidas = buscar_por_medidas(
                m_diam_int or None, m_diam_ext or None, m_ancho or None,
                m_paso or None, m_estrias or None, m_tolerancia
            )
            if res_medidas:
                st.success(f"Se encontraron {len(res_medidas)} pieza(s) con medidas compatibles:")
                st.dataframe(quitar_id(res_medidas), use_container_width=True, hide_index=True)
            else:
                st.warning(
                    "Sin resultados. Puede ser que no haya piezas con esas medidas cargadas todavía — "
                    "cargalas desde la pestaña 'Administrar' a medida que las vayas midiendo."
                )

    historial = historial_reciente()
    if historial:
        st.caption("Búsquedas recientes: " + " · ".join(historial))

    favoritos = listar_favoritos()
    if favoritos:
        with st.expander(f"⭐ Favoritos ({len(favoritos)})"):
            st.dataframe(quitar_id(favoritos), use_container_width=True, hide_index=True)

# ============================================================
# TAB 2: VINCULAR MANUAL
# ============================================================
with tab2:
    st.subheader("Vincular dos códigos como equivalentes")
    st.caption("Usalo para corregir o agregar una equivalencia puntual sin subir un Excel entero.")

    c.execute("SELECT id, nombre FROM marcas ORDER BY nombre")
    marcas_disponibles = c.fetchall()
    nombres_marcas = [m["nombre"] for m in marcas_disponibles]

    # Si se vino desde "Productos sin equivalencias" (pestaña Administrar) con un código para
    # precargar, hay que fijar estos valores ANTES de crear los widgets de abajo — si se hace
    # después de que ya se dibujaron en pantalla, Streamlit tira un error.
    if "vincular_pendiente" in st.session_state:
        pendiente = st.session_state.pop("vincular_pendiente")
        st.session_state["cod_a"] = pendiente.get("cod_a", "")
        st.session_state["desc_a"] = pendiente.get("desc_a", "")
        if pendiente.get("marca_a") in nombres_marcas:
            st.session_state["marca_a"] = pendiente["marca_a"]

    colA, colB = st.columns(2)
    with colA:
        st.markdown("**Código A**")
        codigo_a = st.text_input("Código A", label_visibility="collapsed", key="cod_a")
        marca_a = st.selectbox("Marca A", nombres_marcas + ["➕ Nueva marca..."], key="marca_a")
        if marca_a == "➕ Nueva marca...":
            marca_a = st.text_input("Nombre de la nueva marca (A)", key="nueva_marca_a")
        desc_a = st.text_input("Descripción (opcional)", key="desc_a")
        img_a = st.text_input("URL de foto (opcional)", key="img_a", placeholder="https://...")

    with colB:
        st.markdown("**Código B**")
        codigo_b = st.text_input("Código B", label_visibility="collapsed", key="cod_b")
        marca_b = st.selectbox("Marca B", nombres_marcas + ["➕ Nueva marca..."], key="marca_b")
        if marca_b == "➕ Nueva marca...":
            marca_b = st.text_input("Nombre de la nueva marca (B)", key="nueva_marca_b")
        desc_b = st.text_input("Descripción (opcional)", key="desc_b")
        img_b = st.text_input("URL de foto (opcional)", key="img_b", placeholder="https://...")

    nivel_equiv = st.selectbox(
        "Nivel de equivalencia:",
        ["Exacta", "Reemplazo con modificación", "Solo alternativa de menor calidad"],
        help="Qué tan intercambiables son en la práctica."
    )
    nota_tecnica = st.text_input(
        "Nota técnica (opcional):",
        placeholder="Ej: Equivale pero requiere cambiar la ficha eléctrica"
    )
    verificar = st.checkbox("✅ Marcar esta equivalencia como verificada", value=True,
                             help="Verificada = confirmaste vos mismo que son intercambiables.")

    if st.button("🔗 Vincular como equivalentes", type="primary"):
        clean_a, clean_b = sanitizar(codigo_a), sanitizar(codigo_b)
        if not clean_a or not clean_b:
            st.warning("Completá ambos códigos.")
        elif not marca_a or not marca_b:
            st.warning("Completá ambas marcas.")
        elif clean_a == clean_b and marca_a.strip().upper() == marca_b.strip().upper():
            st.warning("Los dos códigos son idénticos, no hay nada para vincular.")
        else:
            with db_lock:
                marca_a_id = get_or_create_marca(marca_a)
                marca_b_id = get_or_create_marca(marca_b)
                id_a = get_or_create_producto(codigo_a.strip(), clean_a, desc_a.strip(), marca_a_id, img_a.strip())
                id_b = get_or_create_producto(codigo_b.strip(), clean_b, desc_b.strip(), marca_b_id, img_b.strip())
                v = 1 if verificar else 0
                c.execute(
                    "INSERT OR REPLACE INTO equivalencias "
                    "(producto_a_id, producto_b_id, created_at, verificada, nivel, nota) "
                    "VALUES (?, ?, datetime('now'), ?, ?, ?)", (id_a, id_b, v, nivel_equiv, nota_tecnica.strip())
                )
                c.execute(
                    "INSERT OR REPLACE INTO equivalencias "
                    "(producto_a_id, producto_b_id, created_at, verificada, nivel, nota) "
                    "VALUES (?, ?, datetime('now'), ?, ?, ?)", (id_b, id_a, v, nivel_equiv, nota_tecnica.strip())
                )
                conn.commit()
            st.success(f"{codigo_a} ({marca_a}) y {codigo_b} ({marca_b}) quedaron vinculados.")

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

# ============================================================
# TAB 4: ADMINISTRAR
# ============================================================
with tab4:
    st.subheader("Administrar marcas y productos")

    c.execute("""SELECT m.id, m.nombre, m.tipo, COUNT(p.id) AS productos
                 FROM marcas m LEFT JOIN productos p ON p.marca_id = m.id
                 GROUP BY m.id ORDER BY m.nombre""")
    marcas_info = c.fetchall()

    if not marcas_info:
        st.info("Todavía no hay marcas cargadas.")
    else:
        tabla_marcas = [{"Marca": m["nombre"], "Tipo": m["tipo"], "Productos cargados": m["productos"]}
                         for m in marcas_info]
        st.dataframe(tabla_marcas, use_container_width=True, hide_index=True)

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
                with db_lock:
                    c.execute("DELETE FROM marcas WHERE nombre = ?", (marca_a_borrar,))
                    conn.commit()
                st.success(f"Marca '{marca_a_borrar}' eliminada.")
                st.rerun()

        st.markdown("---")
        st.markdown("**Buscar y eliminar un producto puntual**")
        texto_prod = st.text_input("Buscar producto por código o descripción", key="admin_buscar")
        if texto_prod.strip():
            res_admin = buscar_por_texto(texto_prod)
            if not res_admin:
                clean_admin = sanitizar(texto_prod)
                if clean_admin:
                    res_admin = buscar_por_codigo(clean_admin)
            if res_admin:
                st.dataframe(res_admin, use_container_width=True, hide_index=True)
                id_borrar = st.number_input("ID del producto a borrar", min_value=0, step=1)
                if st.button("🗑️ Eliminar producto por ID"):
                    if id_borrar and pedir_password_admin("eliminar un producto"):
                        with db_lock:
                            c.execute("DELETE FROM productos WHERE id = ?", (int(id_borrar),))
                            conn.commit()
                        st.success(f"Producto ID {id_borrar} eliminado.")
                        st.rerun()

                st.markdown("**📐 Cargar medidas mecánicas / ubicación en depósito**")
                opciones_prod = {f"{f['Codigo']} ({f['Marca']}) — ID {f['ID']}": f['ID'] for f in res_admin}
                elegido_label = st.selectbox("Elegí el producto a editar:", list(opciones_prod.keys()), key="sel_medidas")
                id_medidas = opciones_prod[elegido_label]
                c.execute(
                    "SELECT diametro_interno, diametro_externo, ancho, paso_rosca, cantidad_estrias, ubicacion "
                    "FROM productos WHERE id = ?", (id_medidas,)
                )
                actual = c.fetchone()
                em1, em2, em3 = st.columns(3)
                e_diam_int = em1.number_input("Diám. interno (mm)", min_value=0.0, step=0.1,
                                               value=float(actual["diametro_interno"] or 0), key="e_di")
                e_diam_ext = em2.number_input("Diám. externo (mm)", min_value=0.0, step=0.1,
                                               value=float(actual["diametro_externo"] or 0), key="e_de")
                e_ancho = em3.number_input("Ancho (mm)", min_value=0.0, step=0.1,
                                            value=float(actual["ancho"] or 0), key="e_an")
                em4, em5, em6 = st.columns(3)
                e_paso = em4.text_input("Paso de rosca", value=actual["paso_rosca"] or "", key="e_paso")
                e_estrias = em5.number_input("Cantidad de estrías", min_value=0, step=1,
                                              value=int(actual["cantidad_estrias"] or 0), key="e_estrias")
                e_ubicacion = em6.text_input("Ubicación en depósito", value=actual["ubicacion"] or "",
                                              placeholder="Ej: Pasillo 3, estante B", key="e_ubic")
                if st.button("💾 Guardar medidas y ubicación"):
                    actualizar_medidas(id_medidas, e_diam_int, e_diam_ext, e_ancho, e_paso, e_estrias, e_ubicacion)
                    st.success("Guardado.")
            else:
                st.info("Sin resultados.")

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

    st.markdown("---")
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

# ============================================================
# TAB 5: ESTADÍSTICAS
# ============================================================
with tab5:
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
    st.markdown("**📦 Favoritos con poco stock**")
    umbral_stock = st.number_input("Alertar cuando el stock sea menor o igual a:", min_value=0, value=2, step=1)
    stock_bajo = listar_favoritos_stock_bajo(umbral_stock)
    if stock_bajo:
        st.warning(f"{len(stock_bajo)} producto(s) favorito(s) con poco stock — considerá reponerlos:")
        st.dataframe(quitar_id(stock_bajo), use_container_width=True, hide_index=True)
    else:
        st.caption("Ningún favorito con stock bajo por ahora.")

    c.execute("""SELECT m.nombre, COUNT(p.id) AS productos
                 FROM marcas m LEFT JOIN productos p ON p.marca_id = m.id
                 GROUP BY m.id ORDER BY productos DESC LIMIT 15""")
    top_marcas = c.fetchall()
    if top_marcas:
        chart_data = {"Marca": [t["nombre"] for t in top_marcas],
                       "Productos": [t["productos"] for t in top_marcas]}
        st.bar_chart(chart_data, x="Marca", y="Productos")

    st.markdown("---")
    st.markdown("**Historial de importaciones**")
    c.execute("""SELECT marca AS Marca, archivo AS Archivo, filas_cargadas AS Cargadas,
                 filas_omitidas AS Omitidas, fecha AS Fecha FROM importaciones
                 ORDER BY fecha DESC LIMIT 20""")
    imports = filas_a_listas(c)
    if imports:
        st.dataframe(imports, use_container_width=True, hide_index=True)
    else:
        st.caption("Todavía no se registraron importaciones.")

    st.markdown("---")
    if st.button("🗄️ Preparar backup de la base de datos"):
        with open(DB_PATH, "rb") as f:
            st.session_state["backup_bytes"] = f.read()
    if "backup_bytes" in st.session_state:
        st.download_button("⬇️ Descargar backup (.db)", data=st.session_state["backup_bytes"],
                            file_name=f"equivalencias_backup_{datetime.now():%Y%m%d}.db")

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

    st.markdown("---")
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

    st.markdown("---")
    st.markdown("**🔎 Códigos buscados sin resultado**")
    st.caption("Qué te están pidiendo los clientes que todavía no tenés cargado.")
    fallidas = listar_busquedas_sin_resultado()
    if fallidas:
        st.dataframe(fallidas, use_container_width=True, hide_index=True)
    else:
        st.caption("Sin registros todavía.")

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
        partes = ["🔧 *Equivalencias El Chavo*\n"]
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
        mensaje = "\n".join(partes)

        st.text_area("Vista previa del mensaje:", value=mensaje, height=300)

        import urllib.parse
        url_whatsapp = "https://wa.me/?text=" + urllib.parse.quote(mensaje)
        col_wa, col_pdf = st.columns(2)
        col_wa.link_button("📲 Abrir en WhatsApp", url_whatsapp, type="primary", use_container_width=True)
        pdf_bytes = generar_pdf_cotizacion(lista, incluir_precio, incluir_stock)
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

    st.markdown("**Buscar / registrar un vehículo**")
    patente_input = st.text_input("Patente:", placeholder="Ej: AB123CD", key="patente_buscar").strip().upper()

    if patente_input:
        vehiculo = buscar_vehiculo(patente_input)

        with st.expander("✏️ Datos del cliente / vehículo", expanded=(vehiculo is None)):
            with st.form("form_vehiculo"):
                cv1, cv2 = st.columns(2)
                cliente_nombre = cv1.text_input("Nombre del cliente", value=(vehiculo or {}).get("cliente_nombre") or "")
                cliente_tel = cv2.text_input("Teléfono", value=(vehiculo or {}).get("cliente_telefono") or "")
                cv3, cv4, cv5 = st.columns(3)
                marca_auto = cv3.text_input("Marca del auto", value=(vehiculo or {}).get("marca_auto") or "")
                modelo_auto = cv4.text_input("Modelo", value=(vehiculo or {}).get("modelo_auto") or "")
                km_actual_input = cv5.number_input(
                    "Kilometraje actual (se actualiza cada vez)", min_value=0, step=1000,
                    value=int((vehiculo or {}).get("km_actual") or 0)
                )
                guardar_vehiculo = st.form_submit_button("💾 Guardar vehículo", type="primary")
            if guardar_vehiculo:
                get_or_create_vehiculo(patente_input, cliente_nombre, cliente_tel, marca_auto, modelo_auto,
                                        km_actual_input or None)
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

# ============================================================
# TAB 8: MODO MECÁNICO
# ============================================================
with tab8:
    st.subheader("🛠️ Modo Mecánico")

    sub_dtc, sub_vin, sub_esq = st.tabs(["📖 Códigos DTC", "🔢 Lector de VIN", "🗺️ Esquemas"])

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
    with sub_esq:
        st.caption(
            "Guardá diagramas o esquemas (fotos, planos, capturas) para consultarlos rápido. "
            "La app solo los almacena y muestra — las imágenes las tenés que subir vos."
        )
        filtro_esq = st.text_input("Buscar esquema (título, marca, modelo o sistema):", key="esq_filtro")
        esquemas = listar_esquemas(filtro_esq)
        if esquemas:
            for esq in esquemas:
                with st.expander(f"🗺️ {esq['titulo']} — {esq.get('marca_auto') or ''} {esq.get('modelo_auto') or ''}"):
                    if esq.get("sistema"):
                        st.caption(f"Sistema: {esq['sistema']}")
                    if esq.get("descripcion"):
                        st.write(esq["descripcion"])
                    img_bytes = obtener_imagen_esquema(esq["id"])
                    if img_bytes:
                        st.image(img_bytes, use_container_width=True)
                    if es_admin():
                        if st.button("🗑️ Eliminar este esquema", key=f"del_esq_{esq['id']}"):
                            eliminar_esquema(esq["id"])
                            st.rerun()
        else:
            st.caption("Todavía no hay esquemas cargados.")

        st.markdown("---")
        if not pedir_password_admin("subir esquemas nuevos"):
            pass
        else:
            st.markdown("**➕ Subir un esquema nuevo**")
            with st.form("form_esquema", clear_on_submit=True):
                titulo_esq = st.text_input("Título", placeholder="Ej: Esquema eléctrico bomba de combustible")
                ce1, ce2, ce3 = st.columns(3)
                marca_esq = ce1.text_input("Marca del auto (opcional)")
                modelo_esq = ce2.text_input("Modelo (opcional)")
                sistema_esq = ce3.text_input("Sistema (opcional)", placeholder="Ej: Eléctrico, Frenos")
                desc_esq = st.text_input("Descripción (opcional)")
                archivo_esq = st.file_uploader("Imagen del esquema", type=["png", "jpg", "jpeg"])
                subir_esq_btn = st.form_submit_button("📥 Guardar esquema", type="primary")
            if subir_esq_btn:
                if not titulo_esq.strip() or not archivo_esq:
                    st.warning("Completá el título y subí una imagen.")
                else:
                    guardar_esquema(titulo_esq, marca_esq, modelo_esq, sistema_esq, desc_esq,
                                     archivo_esq.getvalue(), archivo_esq.name)
                    st.success("Esquema guardado.")
                    st.rerun()

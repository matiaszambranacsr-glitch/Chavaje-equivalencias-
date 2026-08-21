import streamlit as st
import sqlite3
import re
import io
from datetime import datetime
from openpyxl import load_workbook, Workbook

# ============================================================
# CONFIGURACIÓN DE PÁGINA
# ============================================================
st.set_page_config(page_title="Equivalencias El Chavo", page_icon="🔧", layout="wide")

DB_PATH = "equivalencias_app.db"


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

    columnas_equiv = [f[1] for f in c.execute("PRAGMA table_info(equivalencias)").fetchall()]
    if "verificada" not in columnas_equiv:
        c.execute("ALTER TABLE equivalencias ADD COLUMN verificada INTEGER DEFAULT 0")

    c.execute("CREATE INDEX IF NOT EXISTS idx_codigo_clean ON productos(codigo_clean)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_marca_id ON productos(marca_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_eq_a ON equivalencias(producto_a_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_eq_b ON equivalencias(producto_b_id)")
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
    c.execute("INSERT OR REPLACE INTO catalogos_externos (nombre, url) VALUES (?, ?)", (nombre, url))
    conn.commit()


def eliminar_catalogo_externo(catalogo_id):
    c.execute("DELETE FROM catalogos_externos WHERE id = ?", (catalogo_id,))
    conn.commit()


def depurar_huerfanos():
    """Borra productos que no tienen ninguna equivalencia vinculada (quedaron sueltos)."""
    c.execute("""
        DELETE FROM productos
        WHERE id NOT IN (SELECT DISTINCT producto_a_id FROM equivalencias)
          AND id NOT IN (SELECT DISTINCT producto_b_id FROM equivalencias)
    """)
    borrados = c.rowcount
    conn.commit()
    return borrados


def get_or_create_producto(raw, clean, desc, marca_id):
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
           p.favorito AS "Favorito"
    FROM Red r JOIN productos p ON p.id = r.id JOIN marcas m ON m.id = p.marca_id
    '''
    params = [clean_code]
    if marca_filtro and marca_filtro != "Todas":
        query += " WHERE UPPER(m.nombre) = ?"
        params.append(marca_filtro.upper())
    query += " ORDER BY m.tipo, m.nombre;"

    c.execute(query, params)
    res = filas_a_listas(c)
    # Marca qué filas están verificadas con un link directo hacia el producto buscado
    c.execute("SELECT id FROM productos WHERE codigo_clean = ?", (clean_code,))
    origenes = [r["id"] for r in c.fetchall()]
    for fila in res:
        verificada = False
        for oid in origenes:
            c.execute(
                "SELECT 1 FROM equivalencias WHERE verificada = 1 AND "
                "((producto_a_id = ? AND producto_b_id = ?) OR (producto_a_id = ? AND producto_b_id = ?))",
                (oid, fila["ID"], fila["ID"], oid)
            )
            if c.fetchone():
                verificada = True
                break
        fila["Verificada"] = "✅" if verificada else ""
    return res


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
    c.execute(query, (like, like))
    return filas_a_listas(c)


def actualizar_precio_stock(producto_id, precio, stock):
    c.execute("UPDATE productos SET precio = ?, stock = ? WHERE id = ?", (precio, stock, producto_id))
    conn.commit()


def alternar_favorito(producto_id, valor):
    c.execute("UPDATE productos SET favorito = ? WHERE id = ?", (1 if valor else 0, producto_id))
    conn.commit()


def listar_favoritos():
    c.execute("""SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
                 m.nombre AS "Marca", p.precio AS "Precio", p.stock AS "Stock"
                 FROM productos p JOIN marcas m ON m.id = p.marca_id
                 WHERE p.favorito = 1 ORDER BY p.codigo_raw""")
    return filas_a_listas(c)


def guardar_busqueda(termino):
    c.execute("INSERT INTO historial_busquedas (termino) VALUES (?)", (termino,))
    conn.commit()


def historial_reciente(limite=10):
    c.execute("SELECT DISTINCT termino FROM historial_busquedas ORDER BY id DESC LIMIT ?", (limite,))
    return [r["termino"] for r in c.fetchall()]


def similitud(a, b):
    """Similitud simple entre dos strings (0 a 1) usando coincidencia de secuencia."""
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()


def detectar_posibles_duplicados(marca_id, umbral=0.87):
    """Busca códigos parecidos pero no idénticos dentro de la misma marca (posibles errores de tipeo)."""
    c.execute("SELECT id, codigo_raw, codigo_clean FROM productos WHERE marca_id = ?", (marca_id,))
    productos = c.fetchall()
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


def leer_excel(archivo, nrows=None):
    """Lee un archivo Excel o CSV (subido o por ruta) y devuelve una lista de listas (filas)."""
    nombre = archivo if isinstance(archivo, str) else getattr(archivo, "name", "")
    if nombre.lower().endswith(".csv"):
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
    wb = load_workbook(archivo, data_only=True, read_only=True)
    ws = wb.active
    filas = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        filas.append(list(row))
        if nrows and i + 1 >= nrows:
            break
    return filas


# ============================================================
# ENCABEZADO
# ============================================================
st.title("🔧 Equivalencias El Chavo")
st.caption("¡Fue sin querer queriendo! Sistema de búsqueda de repuestos por equivalencia")

if "lista_whatsapp" not in st.session_state:
    st.session_state.lista_whatsapp = []  # lista de códigos agregados para el mensaje

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["🔍 Buscador", "🔗 Vincular manual", "📁 Cargar Excel", "🗂️ Administrar",
     "📊 Estadísticas", "📋 Lista WhatsApp"]
)

# ============================================================
# TAB 1: BUSCADOR
# ============================================================
with tab1:
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
                        st.success(f"Se encontraron {len(res)} coincidencias:")
                        mostrar = quitar_id(res)
                        st.dataframe(mostrar, use_container_width=True, hide_index=True)

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
                        st.warning("¡Se me chispoteó! No hay equivalencias registradas para ese código.")
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

    colA, colB = st.columns(2)
    with colA:
        st.markdown("**Código A**")
        codigo_a = st.text_input("Código A", label_visibility="collapsed", key="cod_a")
        marca_a = st.selectbox("Marca A", nombres_marcas + ["➕ Nueva marca..."], key="marca_a")
        if marca_a == "➕ Nueva marca...":
            marca_a = st.text_input("Nombre de la nueva marca (A)", key="nueva_marca_a")
        desc_a = st.text_input("Descripción (opcional)", key="desc_a")

    with colB:
        st.markdown("**Código B**")
        codigo_b = st.text_input("Código B", label_visibility="collapsed", key="cod_b")
        marca_b = st.selectbox("Marca B", nombres_marcas + ["➕ Nueva marca..."], key="marca_b")
        if marca_b == "➕ Nueva marca...":
            marca_b = st.text_input("Nombre de la nueva marca (B)", key="nueva_marca_b")
        desc_b = st.text_input("Descripción (opcional)", key="desc_b")

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
            marca_a_id = get_or_create_marca(marca_a)
            marca_b_id = get_or_create_marca(marca_b)
            id_a = get_or_create_producto(codigo_a.strip(), clean_a, desc_a.strip(), marca_a_id)
            id_b = get_or_create_producto(codigo_b.strip(), clean_b, desc_b.strip(), marca_b_id)
            v = 1 if verificar else 0
            c.execute(
                "INSERT OR REPLACE INTO equivalencias (producto_a_id, producto_b_id, created_at, verificada) "
                "VALUES (?, ?, datetime('now'), ?)", (id_a, id_b, v)
            )
            c.execute(
                "INSERT OR REPLACE INTO equivalencias (producto_a_id, producto_b_id, created_at, verificada) "
                "VALUES (?, ?, datetime('now'), ?)", (id_b, id_a, v)
            )
            conn.commit()
            st.success(f"¡Eso, eso, eso! {codigo_a} ({marca_a}) y {codigo_b} ({marca_b}) quedaron vinculados.")

# ============================================================
# TAB 3: CARGAR EXCEL
# ============================================================
with tab3:
    st.subheader("Cargar nueva planilla (.xlsx / .csv)")
    nombre_prov = st.text_input("Nombre de la Marca / Proveedor:", placeholder="Ej: Mahle, Bosch, Mann...")

    metodo = st.radio(
        "¿Cómo querés indicar el archivo?",
        ["Subir archivo", "Escribir la ruta en el teléfono"],
        horizontal=True,
        help="Si el botón de subir no responde en el navegador del celular, usá la opción de ruta."
    )

    archivo = None

    if metodo == "Subir archivo":
        archivo = st.file_uploader("Seleccioná el archivo", type=["xlsx", "csv"])
    else:
        st.caption(
            "Ejemplo: /storage/emulated/0/Download/lista.xlsx "
            "(si el archivo está en Descargas, esa es la ruta de siempre)."
        )
        ruta_archivo = st.text_input("Ruta completa del archivo (.xlsx o .csv) en el teléfono:",
                                      placeholder="/storage/emulated/0/Download/lista.xlsx")
        if ruta_archivo:
            import os
            if not os.path.isfile(ruta_archivo):
                st.error("No se encontró un archivo en esa ruta. Revisá que esté bien escrita.")
            elif not ruta_archivo.lower().endswith((".xlsx", ".csv")):
                st.error("El archivo debe terminar en .xlsx o .csv")
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

                prov_id = get_or_create_marca(nombre_prov, "PROVEEDOR")
                oem_id = get_or_create_marca("OEM / FABRICA", "OEM")

                cargados = 0
                omitidos = 0
                filas_omitidas = []
                eq_batch = set()  # inserción en lote: se acumulan los pares y se insertan todos juntos al final
                progreso = st.progress(0, text="Procesando filas...")
                total = len(filas_datos)

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

                st.balloons()
                st.success(f"¡Eso, eso, eso! Se importaron {cargados} filas correctamente.")
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
                if sospechosos:
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
        st.markdown("**Eliminar una marca** (borra también sus productos y equivalencias asociadas)")
        marca_a_borrar = st.selectbox("Elegí una marca", [m["nombre"] for m in marcas_info])
        confirmar = st.checkbox(f"Confirmo que quiero borrar '{marca_a_borrar}' y todo lo asociado")
        if st.button("🗑️ Eliminar marca", disabled=not confirmar):
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
                    if id_borrar:
                        c.execute("DELETE FROM productos WHERE id = ?", (int(id_borrar),))
                        conn.commit()
                        st.success(f"Producto ID {id_borrar} eliminado.")
                        st.rerun()
            else:
                st.info("Sin resultados.")

    st.markdown("---")
    st.markdown("**Limpieza de la base**")
    st.caption(
        "Con el tiempo pueden quedar códigos cargados por error que no están vinculados a "
        "ninguna equivalencia. Este botón los borra."
    )
    if st.button("🧹 Borrar productos sin ninguna equivalencia"):
        borrados = depurar_huerfanos()
        if borrados:
            st.success(f"Se borraron {borrados} producto(s) sin equivalencias.")
        else:
            st.info("No había productos sueltos para borrar.")

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
    with open(DB_PATH, "rb") as f:
        st.download_button("⬇️ Descargar backup de la base de datos (.db)", data=f,
                            file_name=f"equivalencias_backup_{datetime.now():%Y%m%d}.db")

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
        st.link_button("📲 Abrir en WhatsApp", url_whatsapp, type="primary", use_container_width=True)

        if st.button("🗑️ Vaciar toda la lista"):
            st.session_state.lista_whatsapp = []
            st.rerun()

"""Fotos y backup liviano, columnas recordadas, controles de calidad de un código, búsqueda por parecido.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================================================
# PESO DE LAS FOTOS Y BACKUP LIVIANO
# ============================================================================================
def peso_estimado_por_foto(liviano=True):
    """KB aproximados que ocupa cada foto en la base, para poder avisar antes de llenarla.
    Medido sobre fotos de producto reales: en liviano son la firma visual (~20 KB) más la
    miniatura (~2 KB); en completo se suma la imagen de 500px, que es la que pesa."""
    return 22 if liviano else 120


def _ruta_temporal_de_backup(nombre):
    """Un nombre distinto en cada llamada, y esto no es paranoia: la app está hecha para que la
    usen dos personas a la vez (por eso hay una conexión por sesión).

    Con un nombre fijo, si los dos tocan «Preparar backup» al mismo tiempo, el segundo le borra
    el archivo al primero mientras SQLite lo está escribiendo. Lo que se baja en ese caso no da
    error: da un archivo cortado, que es la peor forma de que falle un backup."""
    import tempfile
    import uuid
    return os.path.join(tempfile.gettempdir(), f"{uuid.uuid4().hex}_{nombre}")


def generar_backup_completo():
    """El backup entero, fotos incluidas, bajado con la API backup() de SQLite y NO leyendo el
    archivo .db a mano, que es como estaba antes.

    Es exactamente el mismo error que ya se había arreglado del otro lado, en
    restaurar_backup(), y de este lado había quedado. La base anda en modo WAL: todo lo que se
    escribió desde el último «checkpoint» vive en equivalencias_app.db-wal, no adentro del
    .db. Leer el .db crudo devuelve la base como estaba hace rato — y ni siquiera de forma
    pareja, porque el checkpoint corre cuando SQLite quiere.

    Está medido, y es peor de lo que suena. Base nueva en WAL, 5.000 filas insertadas y
    COMMITEADAS:
        archivo .db crudo ..... 4.096 bytes — al abrirlo: «no such table: productos»
        conn.backup() ......... 94.208 bytes — 5.000 filas, todas
    O sea que el botón «backup completo» podía entregar un archivo que no tenía NI LA TABLA.
    Y este es el archivo con el que se restaura todo cuando Streamlit borra el disco: no hay
    otra copia atrás. Un backup que miente es peor que no tener backup, porque uno deja de
    revisar.

    El backup liviano de acá abajo ya usaba backup() desde el principio; por eso el problema
    no se veía: el que se sube al repositorio todos los días salía bien."""
    ruta_temporal = _ruta_temporal_de_backup("backup_completo.db")
    destino = sqlite3.connect(ruta_temporal)
    try:
        with db_lock:
            conn.backup(destino)
    finally:
        # Cerrar SIEMPRE, aunque backup() se caiga: si no, la conexión queda abierta contra un
        # archivo que después se borra, y en Windows el borrado falla y el temporal se acumula.
        destino.close()
    try:
        with open(ruta_temporal, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(ruta_temporal)
        except OSError as _err:
            anotar_error("generar_backup_completo", _err)


def _sacar_las_fotos(destino):
    """Le saca las fotos a una copia recién hecha (ver generar_backup_sin_fotos())."""
    destino.execute("UPDATE productos SET imagen_url = NULL, imagen_thumb = NULL, "
                    "imagen_orb_blob = NULL, imagen_orb_estado = NULL")
    for _limpieza in ("DELETE FROM producto_fotos",
                      "UPDATE esquemas SET imagen_blob = NULL",
                      "UPDATE alias_transferencia SET qr_real_blob = NULL"):
        try:
            destino.execute(_limpieza)
        except sqlite3.OperationalError as _err:
            # La tabla puede no existir si el backup sale de una base vieja: se sigue.
            anotar_error("generar_backup_sin_fotos", _err)
    destino.commit()


def copia_para_github(huella_anterior=""):
    """La copia sin fotos y su huella. Devuelve (huella, datos), y datos=None si la huella es
    la misma que la anterior: no cambió nada que valga la pena subir.

    Antes se decidía si subir comparando la CANTIDAD de productos con la de la última copia.
    Aprobar 8.000 equivalencias, cambiar precios, anotar ventas, cargar fichas de autos: nada
    de eso cambia la cantidad de productos, y nada de eso se subía. La huella es el sha256 de
    la copia entera, y cualquier cambio la mueve.
    Menos la tabla de configuración: ahí van las marcas de avance de las tareas de fondo y la
    fecha de la última copia misma, que cambian solas, y con ellas adentro la copia no quedaría
    igual nunca. La que se sube sí la lleva completa; solo la huella no la mira.
    Probado sobre la base real: dos copias seguidas sin cambios dan la misma huella; armar la
    copia tarda 0,7 s, y comprimirla 1,4 s."""
    ruta_temporal = _ruta_temporal_de_backup("copia_para_github.db")
    destino = sqlite3.connect(ruta_temporal)
    try:
        with db_lock:
            conn.backup(destino)
        _sacar_las_fotos(destino)
        configuracion = destino.execute("SELECT clave, valor FROM configuracion").fetchall()
        destino.execute("DELETE FROM configuracion")
        destino.commit()
        destino.execute("VACUUM")
    finally:
        # La huella se saca con la copia CERRADA. La copia hereda el modo WAL de la base: lo
        # escrito va primero a un archivo aparte y el principal se pone al día recién al
        # cerrar (o cuando SQLite decide). Leyéndolo abierto, la misma base daba a veces otra
        # huella, y se subía una copia idéntica.
        destino.close()
    with open(ruta_temporal, "rb") as f:
        huella = hashlib.sha256(f.read()).hexdigest()
    if huella == huella_anterior:
        try:
            os.remove(ruta_temporal)
        except OSError as _err:
            anotar_error("copia_para_github", _err)
        return huella, None
    destino = sqlite3.connect(ruta_temporal)
    try:
        destino.executemany("INSERT INTO configuracion (clave, valor) VALUES (?, ?)", configuracion)
        # La copia ya sabe de qué huella es: restaurada, la primera revisión la reconoce como
        # igual y no la vuelve a subir.
        destino.executemany(
            "INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)",
            [("huella_copia_github", huella),
             ("ultimo_backup_github", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
             ("ultimo_backup_github_error", "")])
        destino.commit()
        destino.execute("VACUUM")
        destino.commit()
    finally:
        destino.close()
    try:
        with open(ruta_temporal, "rb") as f:
            return huella, f.read()
    finally:
        try:
            os.remove(ruta_temporal)
        except OSError as _err:
            anotar_error("copia_para_github", _err)


def _ya_hay_copia_en_github(cfg):
    """Si la rama de copias ya existe. Si no se puede saber, se contesta que sí: del lado
    seguro, que es no pisar nada."""
    try:
        r = requests.get(f"{API_DE_GITHUB}/repos/{cfg['repo']}/git/ref/heads/{cfg['rama']}",
                         headers={"Authorization": f"Bearer {cfg['token']}",
                                  "Accept": "application/vnd.github+json"}, timeout=20)
        return r.status_code != 404
    except Exception as _err:
        anotar_error("_ya_hay_copia_en_github", _err)
        return True


def subir_la_copia_si_cambio(aunque_no_haya_cambios=False):
    """Arma la copia y la sube a GitHub si cambió algo desde la última. Devuelve (ok, mensaje);
    ok=None quiere decir que no hacía falta."""
    cfg = config_github()
    if not cfg:
        return None, "La subida automática no está configurada."
    c.execute("SELECT COUNT(*) FROM productos")
    productos = c.fetchone()[0]
    # Las dos trabas de abajo son para el día que GitHub no conteste justo cuando la app
    # arranca: la base arranca vacía (o con la copia vieja del repositorio), y a los quince
    # minutos el vigía subiría ESO encima de la copia buena. Se perdería todo, y por hacer
    # justamente lo que tenía que proteger.
    if not productos:
        return None, "La base está vacía: no se sube, para no pisar la copia buena."
    huella_anterior = obtener_config("huella_copia_github", "")
    if (not aunque_no_haya_cambios and not huella_anterior
            and cfg["rama"] == RAMA_DE_LA_COPIA and _ya_hay_copia_en_github(cfg)):
        # Una base que nunca subió copia —no tiene huella— y en GitHub ya hay una: no viene
        # de ahí. O la app no la pudo bajar al arrancar, o es otra base. No se decide sola.
        texto = ("En GitHub hay una copia que esta base no reconoce, y no se la reemplaza sola "
                 "por si la buena es esa: puede que al arrancar no se haya podido bajar. "
                 "Reiniciá la app (menú ⋮ → Reboot) para que la baje. Si estás seguro de que "
                 "lo bueno es lo que hay acá, tocá «Subir el backup al repositorio ahora».")
        guardar_config("ultimo_backup_github_error", f"{datetime.now():%d/%m %H:%M} — {texto}")
        return False, texto
    huella, datos = copia_para_github("" if aunque_no_haya_cambios else huella_anterior)
    if datos is None:
        return None, "No cambió nada desde la última copia."
    ok, texto = subir_backup_a_github(datos, f"Copia automática — {productos:,} productos")
    if ok:
        guardar_config("huella_copia_github", huella)
    return ok, texto


# Cada cuánto se mira si hay algo nuevo para subir. Armar la copia y compararla cuesta 0,7 s de
# un hilo aparte; subirla, solo cuando cambió. Es también lo máximo que se puede perder si el
# servidor se reinicia: lo hecho en los últimos quince minutos.
MINUTOS_ENTRE_COPIAS = 15


def vigilar_la_copia():
    """Larga el hilo que sube la copia cuando hay cambios. Uno solo por proceso: se llama en
    cada pasada y casi siempre vuelve enseguida porque ya está corriendo.

    Antes la subida era un paso de las tareas del día: UNA vez por día, el último, dentro de
    los seis segundos que tienen esas tareas —si los pasos de antes los gastaban, ese día no
    había copia— y encima subiendo 11 MB mientras alguien esperaba que se dibujara la pantalla.
    Lo cargado durante el día vivía solo en un disco que se borra al reiniciar."""
    if not config_github():
        return False
    candado = del_proceso("candado_de_la_copia_a_github", threading.Lock)
    if not candado.acquire(blocking=False):
        return False

    def correr():
        try:
            time.sleep(60)          # que termine de arrancar la app primero
            while True:
                try:
                    subir_la_copia_si_cambio()
                except Exception as _err:
                    anotar_error("vigilar_la_copia", _err)
                time.sleep(MINUTOS_ENTRE_COPIAS * 60)
        finally:
            candado.release()

    try:
        threading.Thread(target=correr, daemon=True, name="copia_a_github").start()
        return True
    except RuntimeError as _err:
        candado.release()
        anotar_error("vigilar_la_copia", _err)
        return False


def generar_backup_sin_fotos():
    """Copia de la base SIN las fotos. Las fotos son lo que más pesa: con unos 1.000 productos
    con foto el archivo pasa los 100 MB que acepta GitHub, y ahí se pierde la copia de
    seguridad del repositorio justo cuando más datos hay para proteger.
    Todo lo demás va completo — catálogo, precios, equivalencias, vehículos, historial. Las
    fotos se vuelven a traer con los botones de Mantenimiento."""
    ruta_temporal = _ruta_temporal_de_backup("backup_sin_fotos.db")
    destino = sqlite3.connect(ruta_temporal)
    try:
        with db_lock:
            conn.backup(destino)
        _sacar_las_fotos(destino)
        destino.execute("VACUUM")   # sin esto el archivo sigue pesando lo mismo
        destino.commit()
    finally:
        # Cerrar SIEMPRE: si algo de arriba se cae, la conexión queda abierta contra el
        # temporal y el borrado de abajo falla.
        destino.close()
    try:
        with open(ruta_temporal, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(ruta_temporal)
        except OSError as _err:
            anotar_error("generar_backup_sin_fotos", _err)


def peso_de_las_fotos():
    """Cuánto de la base ocupan las fotos, para poder avisar antes de que sea un problema."""
    c.execute("""SELECT COUNT(*) AS con_foto,
                        COALESCE(SUM(LENGTH(COALESCE(imagen_url,'')) +
                                     LENGTH(COALESCE(imagen_thumb,''))), 0) AS bytes
                 FROM productos WHERE imagen_url IS NOT NULL""")
    fila = c.fetchone()
    total = fila["bytes"]
    try:
        c.execute("""SELECT COALESCE(SUM(LENGTH(COALESCE(imagen_data,'')) +
                                         LENGTH(COALESCE(firma_blob, X''))), 0) FROM producto_fotos""")
        total += c.fetchone()[0]
    except sqlite3.OperationalError as _err:
        anotar_error("peso_de_las_fotos", _err)
        pass
    return fila["con_foto"], total / (1024 * 1024)


# ============================================================================================
# MAPEO DE COLUMNAS RECORDADO POR PROVEEDOR
# ============================================================================================
def guardar_mapeo_columnas(proveedor, idx_prov, idx_oem, idx_desc, idx_precio, idx_stock,
                            buscar_oem_en_desc, prov_es_oem, idx_ean=None):
    """Recuerda cómo se mapearon las columnas de este proveedor, para que la próxima vez venga
    preseleccionado igual y no haya que acertarle de nuevo."""
    if not proveedor or not proveedor.strip():
        return
    with db_lock:
        c.execute("""INSERT OR REPLACE INTO mapeo_columnas
                     (proveedor, idx_prov, idx_oem, idx_desc, idx_precio, idx_stock,
                      buscar_oem_en_desc, prov_es_oem, idx_ean, fecha)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                  (proveedor.strip().upper(), idx_prov, idx_oem, idx_desc, idx_precio, idx_stock,
                   1 if buscar_oem_en_desc else 0, 1 if prov_es_oem else 0, idx_ean))
        conn.commit()


def leer_mapeo_columnas(proveedor):
    if not proveedor or not proveedor.strip():
        return None
    c.execute("SELECT * FROM mapeo_columnas WHERE proveedor = ?", (proveedor.strip().upper(),))
    fila = c.fetchone()
    return dict(fila) if fila else None


# Piezas que se identifican POR SU MEDIDA: en retenes, o'rings, rulemanes y bujes, la medida
# ES el código. Un retén Taranto se pide como "35x52x7" y así figura en el catálogo.
_RE_PIEZA_POR_MEDIDA = re.compile(
    r'\b(RETEN|RETENES|O.?RING|ORING|ANILLO|JUNTA\s+TORICA|SELLO|BUJE|BUJES|'
    r'RULEMAN|RODAMIENTO|ARANDELA|ESPACIADOR|SEPARADOR)\b', re.I)


# ============================================================================================
# CONTROLES DE CALIDAD DE UN CÓDIGO
# ============================================================================================
def codigo_sospechoso(codigo, descripcion=""):
    """¿Esto parece un código de repuesto de verdad? Devuelve (es_sospechoso, motivo).
    Sirve para cazar importaciones mal mapeadas: cuando la columna que se tomó como código
    en realidad tenía medidas, cantidades o pedazos de la descripción, quedan cargados como
    productos códigos tipo '0', '1200cc' o '20x2.50x180' — que después ensucian todo.

    OJO con las medidas: en retenes, o'rings, rulemanes y bujes la medida ES el código. Un
    retén Taranto se pide como «35x52x7» y así figura en el catálogo. Marcarlos como
    sospechosos hacía que TODOS los retenes cargados por medida aparecieran con alarma, que es
    justo lo contrario de lo que sirve. Por eso se mira la descripción antes de descartar."""
    es_por_medida = bool(descripcion and _RE_PIEZA_POR_MEDIDA.search(str(descripcion)))
    if codigo is None:
        return True, "está vacío"
    texto = str(codigo).strip()
    if not texto:
        return True, "está vacío"

    limpio = sanitizar(texto)
    if len(limpio) <= 2:
        return True, f"«{texto}» es demasiado corto para ser un código"
    if re.fullmatch(r"\d{1,3}", limpio):
        return True, f"«{texto}» es solo un número chico, no parece un código"
    # OJO con este: tiene que ser el código ENTERO el que sea un número en notación científica,
    # que es lo que hace Excel cuando el código es largo y numérico ("1.09E+11"). Antes se
    # buscaba el patrón en cualquier parte del texto, y así «BE-777» quedaba marcado: la E de
    # "BE" seguida de "-777" alcanzaba. Se comía todos los códigos tipo BE-, DE-, SE-, RE-, que
    # son de lo más común, y esos vínculos quedaban en la cola de revisión para siempre — o sea,
    # los equivalentes de ese proveedor no aparecían nunca en una búsqueda.
    # Es la misma regla que usa sanitizar() unas líneas más arriba; acá estaba más floja.
    # El signo del exponente es obligatorio, igual que en sanitizar(): sin eso, '233900E010'
    # —un código Toyota de verdad— quedaba marcado como número roto y su vínculo se iba a la
    # cola de revisión para siempre.
    if re.fullmatch(r"\d+(?:[.,]\d+)?[Ee][+\-]\d+", texto.strip()):
        return True, f"«{texto}» quedó en notación científica de Excel (el número real se perdió)"
    # Una medida solo es sospechosa si ES el código, no si es una PARTE del código. Es la misma
    # idea que ya usaba es_por_medida unas líneas más arriba, aplicada a la forma del código.
    # Medido sobre las cinco listas reales: de los 2.406 códigos marcados sospechosos, unos
    # 1.456 eran códigos de proveedor perfectamente válidos que llevan la medida adentro —
    # 'H21A1/2"RF1,5' es el código de IMPERIAL para esa abrazadera, y 'F000 TE1 3X9' es un Bosch.
    # Cada uno de esos mandaba un vínculo bueno a la cola de revisión para siempre, o sea que los
    # equivalentes de ese proveedor no aparecían nunca en una búsqueda.
    # El corte: si sacándole la parte que parece medida todavía quedan 4 o más caracteres de
    # código, es un código con una medida adentro y se respeta. Si no queda casi nada
    # ('20x2.50x180', '1/2"'), es una medida disfrazada de código y sigue marcándose.
    def _queda_codigo_sin(patron):
        """¿Sacándole eso, todavía queda algo con forma de código?

        Dos condiciones: que quede material —cuatro caracteres o más— y que ese resto tenga
        algún NÚMERO. Lo segundo es lo que separa «278.897 c/CHAPA», que es un código con una
        aclaración al lado, de «JUEGO DE AROS DIESEL», que es la descripción entera metida en
        la columna del código. Sin pedir el número, las dos pasaban igual."""
        resto = re.sub(patron, "", texto, flags=re.IGNORECASE)
        solo_alfanum = re.sub(r"[^A-Za-z0-9]", "", resto)
        return len(solo_alfanum) >= 4 and any(ch.isdigit() for ch in solo_alfanum)

    _queda_codigo_sin_la_medida = _queda_codigo_sin

    if not es_por_medida:
        _medida_x = r"\d\s*[xX]\s*\d+[.,]?\d*\s*[xX]?\s*\d*\s*(MM|mm)?$"
        if (re.search(_medida_x, texto) and "x" in texto.lower()
                and not _queda_codigo_sin_la_medida(_medida_x)):
            return True, f"«{texto}» parece una medida, no un código"
        # Las unidades de varias letras (MM, CC, KG...) van como antes. V y W sueltos, en
        # cambio, solo cuentan si el código ES el número y nada más ("24V", "1.6W"): una V o una
        # W al final es de lo más común en códigos de verdad —MD-135V, AB-100V, XW-25W— y
        # marcarlos mandaba a revisión manual vínculos que estaban perfectos.
        if re.search(r"\d+\s*(MM|CM|CC|ML|KG|GR|LTS?)\b", texto, re.I):
            return True, f"«{texto}» parece una medida o especificación"
        if re.fullmatch(r"\d+(?:[.,]\d+)?\s*[VW]", texto.strip(), re.I):
            return True, f"«{texto}» parece una especificación eléctrica, no un código"
        if ("Ø" in texto or '"' in texto or "″" in texto) and not _queda_codigo_sin_la_medida(
                r"[Ø\"″]|\d+\s*/\s*\d+|\d+[.,]\d+"):
            return True, f"«{texto}» tiene símbolos de medida (Ø o pulgadas)"
    # Misma idea que con las medidas: una palabra de la descripción pegada al código no hace
    # que el código deje de existir. JL escribe sus códigos como «278.897 c/CHAPA» —el código es
    # 278.897 y "c/CHAPA" aclara que viene con chapa—, y eran 739 productos marcados como si la
    # columna estuviera mal mapeada. Cada uno mandaba un vínculo bueno a la cola de revisión.
    # Si sacándole la palabra todavía quedan 4 caracteres o más, es un código con una aclaración
    # al lado. Si no queda nada («JUEGO DE AROS DIESEL»), sí es un pedazo de la descripción, que
    # es el caso para el que existe esta regla.
    _palabras_de_desc = r"\b(DIESEL|NAFTA|SECTOR|CANAL|JUEGO|ARO|CHAPA|TIPO|MEDIDA)\b"
    if re.search(_palabras_de_desc, texto, re.I) and not _queda_codigo_sin(_palabras_de_desc):
        return True, f"«{texto}» parece un pedazo de la descripción"
    return False, None


def cb_ver_equivalencias(codigo_raw):
    """Callback para que cualquier código listado en pantalla sea clickeable: al tocarlo,
    busca sus equivalencias y las deja mostradas arriba, sin tener que copiar el código a mano
    y volver a buscarlo."""
    clean = sanitizar(codigo_raw)
    res = buscar_por_codigo(clean) if clean else []
    if res:
        incrementar_veces_buscado(clean)
    guardar_busqueda(codigo_raw)
    st.session_state["ultima_busqueda_codigo"] = [
        {"codigo_individual": codigo_raw, "clean": clean, "res": res}
    ]
    st.session_state["sugerencia_busqueda"] = codigo_raw
    st.session_state["modo_busqueda"] = "Código"   # por si se tocó desde la búsqueda por texto


def mostrar_lista_clickeable(filas, prefijo_key, limite=15, nota=None):
    """Muestra resultados con el código como botón: al tocarlo se abren sus equivalencias.
    Antes esto era una tabla y había que ir copiando los códigos de a uno para buscarlos."""
    if nota:
        st.caption(nota)
    for f in filas[:limite]:
        col_cod, col_desc = st.columns([1.2, 3])
        col_cod.button(f"🔎 {f['Codigo']}", key=f"{prefijo_key}_{f['ID']}",
                        on_click=cb_ver_equivalencias, args=(f["Codigo"],),
                        help="Ver sus equivalencias")
        descripcion = (f.get("Descripcion") or "")[:90]
        precio = f"${f['Precio']:,.0f}" if f.get("Precio") else ""
        stock = f" · stock {f['Stock']}" if f.get("Stock") is not None else ""
        col_desc.caption(f"**{f.get('Marca', '')}** {descripcion}  \n{precio}{stock}")
    if len(filas) > limite:
        st.caption(f"(mostrando {limite} de {len(filas)})")


# ============================================================================================
# BÚSQUEDA POR PARECIDO Y ERRORES DE TIPEO
# ============================================================================================
def buscar_codigos_parecidos(clean_code, limite=30):
    """Cuando el código exacto no aparece, busca códigos que EMPIECEN igual o que lo contengan.
    Es el caso típico de las familias: pedís 'TC-421' y en la base están 'TC-421-15' y
    'TC-421-20' (mismo repuesto, distinto espesor/variante). Antes eso no aparecía por ningún
    lado, porque la búsqueda por código exige coincidencia exacta."""
    if not clean_code or len(clean_code) < 3:
        return []
    c.execute("""SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
                        m.nombre AS "Marca", m.tipo AS "Tipo", p.precio AS "Precio",
                        p.stock AS "Stock", p.codigo_clean AS "_clean"
                 FROM productos p JOIN marcas m ON m.id = p.marca_id
                 WHERE p.codigo_clean LIKE ? OR p.codigo_clean LIKE ?
                 ORDER BY CASE WHEN p.codigo_clean LIKE ? THEN 0 ELSE 1 END,
                          LENGTH(p.codigo_clean), p.codigo_clean
                 LIMIT ?""",
              (f"{clean_code}%", f"%{clean_code}%", f"{clean_code}%", limite))
    return filas_a_listas(c)


def _distancia_edicion(a, b, tope=2):
    """Cuántos cambios de un carácter hacen falta para pasar de un código al otro.
    Corta apenas supera el tope: no interesa saber si son 7 u 8, solo si están cerca."""
    if abs(len(a) - len(b)) > tope:
        return tope + 1
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        actual = [i]
        for j, cb in enumerate(b, 1):
            actual.append(min(anterior[j] + 1, actual[j - 1] + 1,
                              anterior[j - 1] + (ca != cb)))
        if min(actual) > tope:
            return tope + 1
        anterior = actual
    return anterior[-1]


def codigos_por_tipeo(clean_code, limite=10):
    """Códigos que se escriben casi igual al que buscaste. Es para el error de tipeo.

    Lo que ya existía busca códigos que EMPIECEN igual o que lo CONTENGAN, y eso no sirve
    cuando el error está en el medio: pidiendo 'W71249' en vez de 'W71294' no aparece nada,
    aunque sea el mismo filtro con dos dígitos cambiados de lugar. Acá se mide cuántos
    caracteres hay que cambiar para pasar de uno al otro, así que agarra los dígitos dados
    vuelta, la letra de más y la que falta.

    El truco para que no tarde: el código se parte en tres pedazos y se le pide a la base que
    el candidato contenga AL MENOS UNO igual. Con dos errores como mucho se pueden arruinar dos
    pedazos, así que el tercero sobrevive sí o sí — no se pierde ningún candidato y la base
    devuelve un puñado en vez de todo el catálogo. Sin esto, con 40.000 productos tardaba casi
    un segundo en cada búsqueda fallida."""
    if not clean_code or len(clean_code) < 4:
        return []
    largo = len(clean_code)
    tercio = max(largo // 3, 1)
    # Los tres pedazos van SIEMPRE, aunque alguno quede de un solo carácter. Descartar los
    # cortos rompía la garantía: con 'OC9O' quedaba solo el pedazo '9O', y el código correcto
    # 'OC90' no lo contiene, así que se perdía. Son exactamente tres para que dos errores no
    # puedan arruinarlos a todos.
    pedazos = [clean_code[:tercio], clean_code[tercio:tercio * 2], clean_code[tercio * 2:]]
    pedazos = [p for p in pedazos if p]

    condiciones = " OR ".join("p.codigo_clean LIKE ?" for _ in pedazos)
    params = [f"%{p}%" for p in pedazos] + [largo - 2, largo + 2, clean_code]
    # EN DOS PASOS: primero solo el id y el código, que es lo único que hace falta para medir la
    # distancia, y la fila entera recién para los que quedan cerca. Un pedazo corto —«12» de
    # W71294, «27» de 2711500— aparece en miles de códigos: eran hasta 7.444 filas COMPLETAS,
    # con descripción y precio, convertidas en diccionarios para quedarse con diez. Sola no se
    # notaba; mientras corre la tarea de fondo, cada una de esas filas espera su turno para
    # agarrar el intérprete y una búsqueda sin resultado pasaba de 0,4 s a 4 s.
    # Y en UNA fila, con group_concat. Cada fila que entrega SQLite obliga a Python a soltar el
    # intérprete y volver a pedirlo; con la tarea de fondo ocupándolo, cada vuelta espera, y
    # 3.950 vueltas eran un segundo entero aunque las filas fueran dos números. Una fila, una
    # espera. Los separadores son los caracteres de control 30 y 31, que un código limpio no
    # puede tener (sanitizar() deja letras y números).
    c.execute(f"""SELECT group_concat(p.id || char(30) || p.codigo_clean, char(31))
                  FROM productos p
                  WHERE ({condiciones})
                    AND LENGTH(p.codigo_clean) BETWEEN ? AND ?
                    AND p.codigo_clean <> ?""", params)
    juntos = c.fetchone()[0] or ""
    cerca = []
    for trozo in juntos.split("\x1f") if juntos else ():
        pid, cod = trozo.split("\x1e", 1)
        d = _distancia_edicion(clean_code, cod)
        if d <= 2:
            cerca.append((int(pid), d))
    if not cerca:
        return []
    completas = {}
    for tanda, marcas in en_tandas([pid for pid, _d in cerca]):
        c.execute(f"""SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
                             m.nombre AS "Marca", m.tipo AS "Tipo", p.precio AS "Precio",
                             p.stock AS "Stock", p.codigo_clean AS "_clean"
                      FROM productos p JOIN marcas m ON m.id = p.marca_id
                      WHERE p.id IN ({marcas})""", tanda)
        for fila in filas_a_listas(c):
            completas[fila["ID"]] = fila
    # En el orden del primer paso, que es el que tenía antes: el sort de abajo es estable y,
    # con la misma distancia y el mismo stock, desempata por ese orden.
    candidatos = []
    for pid, d in cerca:
        if pid in completas:
            completas[pid]["_dist"] = d
            candidatos.append(completas[pid])
    # Primero los de un solo carácter de diferencia, y dentro de esos los que tienen stock.
    # El código al final no es cosmético: sin él, entre empatados —misma distancia, sin stock,
    # que es lo común— el orden era el que se le ocurría a SQLite al recorrer la tabla, y al
    # cortar en diez quedaban unos u otros según el plan de la consulta.
    candidatos.sort(key=lambda f: (f["_dist"], -(f["Stock"] or 0), f["Codigo"] or ""))
    return candidatos[:limite]


def precios_incoherentes_entre_equivalentes(factor=8, limite=200):
    """Pares de productos marcados como equivalentes cuyos precios no se parecen en nada.

    Dos repuestos que hacen lo mismo pueden costar distinto según la marca, pero no ocho veces
    distinto. Cuando pasa eso, una de dos cosas está mal, y las dos importan:
      - el precio (se importó una columna equivocada o el separador de decimales al revés), o
      - la equivalencia (los vinculó una lista mal cargada y no son la misma pieza).
    Cualquiera de las dos que sea, es plata: o cotizás mal, o vendés lo que no entra."""
    c.execute(f"""SELECT pa.codigo_raw AS "Código A", ma.nombre AS "Marca A", pa.precio AS "Precio A",
                        pb.codigo_raw AS "Código B", mb.nombre AS "Marca B", pb.precio AS "Precio B",
                        ROUND(MAX(pa.precio, pb.precio) / MIN(pa.precio, pb.precio), 1) AS "Veces",
                        pa.descripcion AS "Descripción",
                        pa.id AS "_ida", pb.id AS "_idb"
                 FROM equivalencias e
                 JOIN productos pa ON pa.id = e.producto_a_id
                 JOIN productos pb ON pb.id = e.producto_b_id
                 JOIN marcas ma ON ma.id = pa.marca_id
                 JOIN marcas mb ON mb.id = pb.marca_id
                 WHERE {SIN_CONTAR_EL_ESPEJO} AND pa.precio > 0 AND pb.precio > 0
                   AND MAX(pa.precio, pb.precio) / MIN(pa.precio, pb.precio) >= ?
                 ORDER BY "Veces" DESC LIMIT ?""", (factor, limite))
    return filas_a_listas(c)


# Se ordena de más largo a más corto para que gane la coincidencia más específica:
# "LAND ROVER" tiene que ganarle a "ROVER", y "MERCEDES BENZ" a "MERCEDES".
# No se agregan marcas de 2 letras (MG, DS) porque en una descripción de repuesto casi siempre
# son otra cosa (medidas, siglas) y ensuciarían más de lo que aportan.
MARCAS_VEHICULO = sorted(set([
    # --- Las que ya estaban ---
    "MERCEDES BENZ", "M.BENZ", "MERCEDES", "VOLKSWAGEN", "CHEVROLET", "MITSUBISHI", "LAND ROVER",
    "MASSEY FERGUSON", "M. FERGUSON", "AGCO SISU POWER", "JOHN DEERE", "NEW HOLLAND", "ALFA ROMEO",
    "CITROEN", "PEUGEOT", "RENAULT", "CHRYSLER", "CUMMINS", "PERKINS", "ILLINOIS", "TOYOTA",
    "NISSAN", "HYUNDAI", "DAEWOO", "SUZUKI", "SCANIA", "IVECO", "AGRALE", "DEUTZ", "VOLVO",
    "HONDA", "DODGE", "BURMOR", "M.W.M.", "M.W.M", "MWM", "KNORR", "VARGA", "VALTRA", "ZANELLO",
    "PAUNY", "FIAT", "FORD", "JEEP", "AUDI", "SEAT", "BMW", "KIA", "MAN", "DAF", "HINO",
    "ISUZU", "CASE", "GM",
    # --- Chinas, que hoy son parte del parque argentino ---
    "GREAT WALL", "DONGFENG", "SHINERAY", "CHANGAN", "BAIC", "CHERY", "GEELY", "HAVAL",
    "FOTON", "LIFAN", "JINBEI", "MAXUS", "JETOUR", "SOUEAST", "BYD", "JAC",
    # --- Coreanas, japonesas y del resto de Asia ---
    "SSANGYONG", "MAHINDRA", "SUBARU", "DAIHATSU", "LEXUS", "INFINITI", "ACURA", "GENESIS",
    "MAZDA", "TATA", "PROTON",
    # --- Europeas que faltaban ---
    "VAUXHALL", "LAMBORGHINI", "ROLLS ROYCE", "ASTON MARTIN", "MASERATI", "PORSCHE", "FERRARI",
    "BENTLEY", "SKODA", "LANCIA", "JAGUAR", "DACIA", "OPEL", "SMART", "MINI", "LADA", "ROVER",
    "ZASTAVA", "YUGO", "TALBOT", "SAAB", "LOTUS", "MCLAREN",
    # --- Norteamericanas ---
    "INTERNATIONAL", "FREIGHTLINER", "WESTERN STAR", "OLDSMOBILE", "KENWORTH", "PETERBILT",
    "PLYMOUTH", "CADILLAC", "PONTIAC", "LINCOLN", "MERCURY", "SATURN", "NAVISTAR", "BUICK",
    "TESLA", "MACK", "GMC", "RAM",
    # --- Camiones, ómnibus, agro e industria ---
    "MERCEDES-BENZ", "LANDINI", "MARCOPOLO", "METALPAR", "RASTROJERO", "CATERPILLAR", "YANMAR",
    "KUBOTA", "CLAAS", "FENDT", "JCB", "VETRA", "APACHE", "SEVEL", "SIAM", "DI TELLA",
    # --- Motos ---
    "ROYAL ENFIELD", "HARLEY DAVIDSON", "MOTO GUZZI", "MV AGUSTA", "KAWASAKI", "HUSQVARNA",
    "MOTOMEL", "GUERRERO", "ZANELLA", "KYMCO", "APRILIA", "YAMAHA", "DUCATI", "PIAGGIO",
    "BENELLI", "CORVEN", "KELLER", "GILERA", "MONDIAL", "BAJAJ", "VESPA", "KTM", "SYM",
    "HERO", "TVS", "BETA",
    # --- Abreviaturas que las listas escriben todo el tiempo ---
    # Sin «VW» la app no tenía Volkswagen: 5.530 descripciones lo escriben así y ninguna dice
    # VOLKSWAGEN, o sea que 6.348 productos —Gol, Polo, Amarok, Suran— no aparecían en la
    # pantalla de vehículos ni existían para la detección de modelos. Las otras salieron de
    # contar cuántas descripciones reales las usan como palabra suelta.
    "VW", "CHEV", "PEUG", "PEU", "REN", "TOY", "CITR", "HYUN",
    # El camión Bedford, que las listas escriben partido: «BED FORD». Son 147 descripciones y
    # no estaba, así que de todas ellas la app leía FORD — o sea que una junta de diferencial
    # de un camión Bedford quedaba emparejada con repuestos de un Fiesta por «coinciden en
    # FORD». Va antes que FORD porque la lista se ordena de la marca más larga a la más corta.
    "BED FORD", "BEDFORD",
]), key=len, reverse=True)


# La misma marca escrita de varias formas es UNA marca. Sin esto el desplegable mostraba
# «MERCEDES BENZ», «M.BENZ», «MERCEDES» y «MERCEDES-BENZ» como si fueran cuatro autos
# distintos, cada uno con una parte del catálogo.
ALIAS_MARCA_VEHICULO = {
    "VW": "VOLKSWAGEN", "CHEV": "CHEVROLET", "PEUG": "PEUGEOT", "PEU": "PEUGEOT",
    "REN": "RENAULT", "TOY": "TOYOTA", "CITR": "CITROEN", "HYUN": "HYUNDAI",
    "BED FORD": "BEDFORD",
    "M.BENZ": "MERCEDES BENZ", "MERCEDES": "MERCEDES BENZ", "MERCEDES-BENZ": "MERCEDES BENZ",
    "M. FERGUSON": "MASSEY FERGUSON", "M.W.M.": "MWM", "M.W.M": "MWM",
}

# Todas las formas de escribir cada marca, para poder prefiltrar en SQL: buscar «VOLKSWAGEN»
# en la base se perdería los 5.530 productos que dicen «VW».
def _escrituras_por_marca():
    salida = {}
    for marca in MARCAS_VEHICULO:
        salida.setdefault(ALIAS_MARCA_VEHICULO.get(marca, marca), []).append(marca)
    return salida


ESCRITURAS_DE_MARCA = _escrituras_por_marca()

# UN solo regex con todas las marcas en vez de uno por marca. Medido sobre las 61.574
# descripciones reales: 15,2 s recorriendo marca por marca contra 2,1 s así, siete veces más
# rápido, y es la función que corre una vez por producto en toda la pantalla de vehículos.
# Las marcas van de más larga a más corta (así lo deja MARCAS_VEHICULO), que es lo que hace
# que en la misma posición gane «MERCEDES BENZ» antes que «MERCEDES».
# El borde excluye letras Y dígitos: sin los dígitos, «MAN» aparecía adentro de un número de
# parte. Con letras solas ya no entraba en MANGUERA, pero sí en cosas como GM1234.
# Y va en IGNORECASE. Antes se comparaba con la marca tal cual, en mayúsculas, contra el texto
# tal cual venía: «BUJIA NAFTA Ford Escort - VW Gol» encontraba VW pero no Ford, porque el
# proveedor lo escribió con minúsculas. Media lista de FISPA está escrita así.
_RE_MARCAS_VEHICULO = re.compile(
    r'(?<![A-Za-zÁÉÍÓÚÑ0-9])(' + "|".join(re.escape(_m) for _m in MARCAS_VEHICULO)
    + r')(?![A-Za-zÁÉÍÓÚÑ0-9])', re.IGNORECASE)


# El resultado de separar_texto_pegado() se guarda por descripción. No es microoptimización:
# la función hace SEIS pasadas de expresión regular sobre cada texto, y la llaman ocho lugares
# —entre ellos marcas_vehiculo_en(), que a su vez la llama una vez por descripción del catálogo
# entero—. Medido sobre las 70.888 descripciones reales: separar todas cuesta 2,70 s y hay
# 27.201 repetidas (el 38%), porque el producto OEM se crea copiando la descripción de la fila
# del proveedor. Esas 27.201 se estaban separando de nuevo cada vez.
# El tope de 50.000 entradas cubre las 43.687 descripciones distintas de esta base con lugar de
# sobra, y si alguna vez se pasa, lru_cache tira las más viejas: no crece sin control.
MAXIMO_DESCRIPCIONES_RECORDADAS = 50000


@functools.lru_cache(maxsize=MAXIMO_DESCRIPCIONES_RECORDADAS)
def _marcas_vehiculo_en_cacheado(descripcion):
    return tuple(_marcas_vehiculo_en(descripcion))


def marcas_vehiculo_en(descripcion):
    """TODOS los autos que nombra una descripción. Ver _marcas_vehiculo_en().

    Igual que separar_texto_pegado(), se recuerda por descripción: esta función se llama una
    vez por fila del catálogo desde tres lugares distintos —el contador de marcas, el lector de
    aplicaciones y el de modelos— y el 38% de las descripciones están repetidas.
    Se guarda una TUPLA y se devuelve una lista nueva cada vez: si se devolviera la misma
    lista, dos pantallas tendrían el mismo objeto y la que lo modificara le cambiaría el
    resultado a la otra. Copiar tres tuplas no cuesta nada al lado de la expresión regular."""
    if not descripcion or not isinstance(descripcion, str):
        return _marcas_vehiculo_en(descripcion)
    return list(_marcas_vehiculo_en_cacheado(descripcion))


def _marcas_vehiculo_en(descripcion):
    """TODOS los autos que nombra una descripción: [(marca, categoría, resto), ...].

    Una descripción de proveedor rara vez habla de un solo auto: «BUJIA NAFTA Ford Escort -
    VW Gol - Kombi - Parati». Son 11.874 de las 61.574 descripciones reales (el 19%) las que
    nombran dos marcas o más. Antes la app se quedaba con UNA —la que primero apareciera en
    la lista de marcas, que está ordenada por largo, o sea prácticamente al azar— y el
    producto desaparecía del catálogo de las otras. Se medía feo: CITROEN mostraba 1.831 de
    los 5.106 productos que lo nombran, OPEL 156 de 2.679, PEUGEOT 1.433 de 5.139.

    El «resto» de cada marca va hasta la marca siguiente, así que es lo que le corresponde a
    ESE auto: en el ejemplo, «Escort» para Ford y «Gol - Kombi - Parati» para Volkswagen.
    La «categoría» —el nombre de la pieza— es la misma para todas: es lo que va antes de la
    primera marca."""
    if not descripcion:
        return []
    texto = separar_texto_pegado(str(descripcion))
    encontradas = list(_RE_MARCAS_VEHICULO.finditer(texto))
    if not encontradas:
        return []
    categoria = texto[:encontradas[0].start()].strip(" -,/") or None
    salida = []
    vistas = set()
    for i, m in enumerate(encontradas):
        escrita = m.group(1).upper()
        canonica = ALIAS_MARCA_VEHICULO.get(escrita, escrita)
        if canonica in vistas:
            continue          # «Ford ... Ford» es un solo Ford
        vistas.add(canonica)
        hasta = encontradas[i + 1].start() if i + 1 < len(encontradas) else len(texto)
        salida.append((canonica, categoria, texto[m.end():hasta].strip(" -,/") or None))
    return salida


def _like_de_marca(marca_canonica):
    """(trozo de SQL, parámetros) para prefiltrar por cualquiera de las formas de esa marca."""
    formas = ESCRITURAS_DE_MARCA.get(marca_canonica, [marca_canonica])
    return ("(" + " OR ".join(["UPPER(p.descripcion) LIKE ?"] * len(formas)) + ")",
            [f"%{f}%" for f in formas])

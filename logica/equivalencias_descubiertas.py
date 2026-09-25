"""Las equivalencias que se descubren solas: ventas, descripciones, catálogos cruzados.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================
# EQUIVALENCIAS DESCUBIERTAS DESDE LAS VENTAS
# ============================================================
# La idea: si un cliente pide el código A y termina llevándose el B, eso es una equivalencia
# que pasó de verdad en el mostrador — aunque no figure en ningún catálogo. Cruzando lo que se
# pidió contra lo que se vendió, el sistema propone equivalencias candidatas para que el dueño
# las confirme. No inventa nada solo: propone, y una persona decide.

def registrar_venta(producto_id, termino_pedido=""):
    """Anota que un producto se vendió, y qué había pedido el cliente cuando lo pidió."""
    with db_lock:
        c.execute(
            "INSERT INTO ventas_registradas (producto_id, termino_pedido, codigo_pedido_clean, usuario) "
            "VALUES (?, ?, ?, ?)",
            (producto_id, termino_pedido.strip(), sanitizar(termino_pedido), obtener_usuario_actual())
        )
        conn.commit()


def red_de_equivalencias(codigo_clean):
    """IDs de todos los productos que ya están vinculados a ese código (directa o
    indirectamente). Sirve para no proponer como novedad algo que ya está cargado."""
    if not codigo_clean:
        return set()
    c.execute("""
    WITH RECURSIVE Red(id) AS (
        SELECT id FROM productos WHERE codigo_clean = ?
        UNION
        SELECT CASE WHEN eq.producto_a_id = re.id THEN eq.producto_b_id ELSE eq.producto_a_id END
        FROM equivalencias eq JOIN Red re ON (eq.producto_a_id = re.id OR eq.producto_b_id = re.id)
    )
    SELECT id FROM Red""", (codigo_clean,))
    return {r["id"] for r in c.fetchall()}


def descubrir_equivalencias_candidatas(min_veces=2, dias=180, minutos_ventana=20):
    """Devuelve pares (código pedido → producto vendido) que se repitieron y que todavía NO
    están cargados como equivalentes. Se arma de dos fuentes:
      1) Directa: el empleado marcó "se llevó este" sobre el resultado de una búsqueda.
      2) Deducida: se vendió algo justo después de que el mismo empleado buscara un código
         que no dio resultado — el caso típico de "no lo tengo, pero le doy este que sirve".
    Es solo una sugerencia: siempre la confirma una persona antes de que quede cargada."""
    conteos = {}

    def sumar(codigo_clean, termino, producto_id, veces, origen):
        if not codigo_clean or not producto_id:
            return
        clave = (codigo_clean, producto_id)
        actual = conteos.get(clave)
        if actual:
            actual["veces"] += veces
            actual["origenes"].add(origen)
        else:
            conteos[clave] = {"termino": termino, "veces": veces, "origenes": {origen}}

    # Fuente 1: marcado explícito en el mostrador
    c.execute("""SELECT codigo_pedido_clean AS cod, MAX(termino_pedido) AS termino,
                        producto_id AS pid, COUNT(*) AS veces
                 FROM ventas_registradas
                 WHERE codigo_pedido_clean IS NOT NULL AND codigo_pedido_clean <> ''
                   AND fecha >= datetime('now', ?)
                 GROUP BY codigo_pedido_clean, producto_id""", (f"-{dias} days",))
    for f in c.fetchall():
        sumar(f["cod"], f["termino"], f["pid"], f["veces"], "mostrador")

    # Fuente 2: venta poco después de una búsqueda sin resultado del mismo empleado
    c.execute("""SELECT h.termino AS termino, v.producto_id AS pid, COUNT(*) AS veces
                 FROM ventas_registradas v
                 JOIN historial_busquedas h
                   ON h.usuario = v.usuario
                  AND h.sin_resultado = 1
                  AND h.fecha <= v.fecha
                  AND h.fecha >= datetime(v.fecha, ?)
                 WHERE v.fecha >= datetime('now', ?)
                 GROUP BY h.termino, v.producto_id""",
              (f"-{minutos_ventana} minutes", f"-{dias} days"))
    for f in c.fetchall():
        sumar(sanitizar(f["termino"]), f["termino"], f["pid"], f["veces"], "deducida")

    if not conteos:
        return []

    descartadas = set()
    c.execute("SELECT codigo_clean, producto_id FROM equivalencias_descartadas")
    for f in c.fetchall():
        descartadas.add((f["codigo_clean"], f["producto_id"]))

    redes = {}
    candidatas = []
    for (codigo_clean, producto_id), datos in conteos.items():
        if datos["veces"] < min_veces or (codigo_clean, producto_id) in descartadas:
            continue
        if codigo_clean not in redes:
            redes[codigo_clean] = red_de_equivalencias(codigo_clean)
        if producto_id in redes[codigo_clean]:
            continue  # ya está cargado como equivalente, no es novedad

        c.execute("""SELECT p.codigo_raw, p.codigo_clean, p.descripcion, m.nombre AS marca
                     FROM productos p JOIN marcas m ON m.id = p.marca_id WHERE p.id = ?""", (producto_id,))
        prod = c.fetchone()
        if not prod or prod["codigo_clean"] == codigo_clean:
            continue  # se llevó exactamente lo que pidió, no hay nada nuevo

        c.execute("SELECT id FROM productos WHERE codigo_clean = ? LIMIT 1", (codigo_clean,))
        existente = c.fetchone()

        # Evidencia local que se puede calcular sola: si los dos productos tienen medidas
        # cargadas, compararlas es prueba física, no una suposición.
        if existente:
            coinciden, detalle_medidas = comparar_medidas_productos(existente["id"], producto_id)
            if coinciden is True:
                guardar_evidencia(codigo_clean, producto_id, "medidas", detalle_medidas)
            elif coinciden is False:
                guardar_evidencia(codigo_clean, producto_id, "medidas_no_coinciden", detalle_medidas)

        guardar_evidencia(codigo_clean, producto_id, "mostrador",
                           f"Se repitió {datos['veces']} vez/veces en el mostrador")
        evidencias = listar_evidencia(codigo_clean, producto_id)
        etiqueta_confianza, puntaje = nivel_por_evidencias(evidencias)

        candidatas.append({
            "codigo_pedido": datos["termino"] or codigo_clean,
            "codigo_clean": codigo_clean,
            "producto_id": producto_id,
            "codigo_vendido": prod["codigo_raw"],
            "marca_vendida": prod["marca"],
            "descripcion": prod["descripcion"] or "",
            "veces": datos["veces"],
            "origen": "mostrador" if "mostrador" in datos["origenes"] else "deducida",
            "pedido_ya_cargado": existente is not None,
            "id_pedido": existente["id"] if existente else None,
            "evidencias": evidencias,
            "confianza": etiqueta_confianza,
            "puntaje": puntaje,
        })

    # Primero lo mejor respaldado, y dentro de eso lo que más se repitió
    candidatas.sort(key=lambda x: (-x["puntaje"], -x["veces"]))
    return candidatas


# ---- Evidencia que respalda (o descarta) una equivalencia sugerida ----------------
# Regla de oro: NADA se carga solo. Cada sugerencia llega al panel con el detalle de en qué
# se basa, y una persona decide. Las fuentes están ordenadas de más a menos confiable.

PESOS_EVIDENCIA = {
    "catalogo_oficial": 100,   # el código aparece escrito en la ficha oficial del proveedor
    "lista_proveedor": 60,     # vinieron relacionados en un Excel del propio proveedor
    "medidas": 45,             # las medidas mecánicas cargadas coinciden
    "mostrador": 20,           # se repitió en ventas reales
}


def guardar_evidencia(codigo_clean, producto_id, tipo, detalle=""):
    with db_lock:
        c.execute("INSERT OR REPLACE INTO evidencia_equivalencia "
                   "(codigo_clean, producto_id, tipo, detalle) VALUES (?, ?, ?, ?)",
                   (codigo_clean, producto_id, tipo, detalle))
        conn.commit()


def listar_evidencia(codigo_clean, producto_id):
    c.execute("""SELECT tipo, detalle, fecha FROM evidencia_equivalencia
                 WHERE codigo_clean = ? AND producto_id = ?""", (codigo_clean, producto_id))
    return [dict(r) for r in c.fetchall()]


CAMPOS_MEDIDAS = [
    ("diametro_interno", "diám. interno"), ("diametro_externo", "diám. externo"),
    ("diametro_interno_cara_b", "diám. interno cara B"),
    ("diametro_externo_cara_b", "diám. externo cara B"),
    ("diametro_rosca_homocinetica", "diám. rosca"), ("diametro_copa", "diám. copa (base)"),
    ("diametro_copa_superior", "diám. copa (boca)"), ("largo_total", "largo total"),
    ("ancho", "ancho"),
    # El espesor va con los numéricos porque se compara con tolerancia igual que un diámetro:
    # una junta de 1,45 y otra de 1,50 son piezas distintas, y el 3% las separa.
    ("espesor", "espesor"),
]
COLUMNAS_MEDIDAS = (", ".join(cn for cn, _ in CAMPOS_MEDIDAS)
                    + ", paso_rosca, cantidad_estrias, cantidad_vias, cantidad_canales, posicion")


def cargar_medidas_de_varios(ids):
    """Trae las medidas de muchos productos de una sola consulta.

    Por qué: analizar un lote pendiente hacía DOS consultas por cada par para comparar medidas.
    Con 400 pares son 800 consultas — por eso el análisis estaba topeado en 400. Precargando
    todo de una, revisar 5.000 pares cuesta casi lo mismo que revisar 400."""
    ceder_al_mostrador()      # antes de la lectura grande. Ver ceder_al_mostrador().
    medidas = {}
    ids = list({int(i) for i in ids})
    columnas = _columnas_de_medidas_que_existen()
    for tanda, marcadores in en_tandas(ids):
        c.execute(f"SELECT id, {columnas} FROM productos WHERE id IN ({marcadores})", tanda)
        for fila in c.fetchall():
            medidas[fila["id"]] = dict(fila)
    return medidas


def _columnas_que_tiene_productos(cursor):
    """Los nombres de columna que la tabla productos tiene AHORA.

    SIN caché a propósito. El PRAGMA cuesta 50 µs y se llama dos veces por búsqueda: 0,1 ms.
    Cachearlo obligaría a acordarse de limpiarlo cada vez que el esquema puede cambiar —al
    restaurar un backup, al migrar— y esa es justamente la clase de olvido que esta función
    existe para cubrir. Barato y sin estado le gana a rápido y con una trampa.
    Recibe el cursor y no usa el de módulo para que el paquete nucleo pueda llevarse
    buscar_por_codigo() tal cual.

    Mismo cinturón de seguridad que _columnas_de_medidas_que_existen(), y por la misma razón:
    una columna agregada en esta versión puede no existir todavía en la base que la sesión
    tiene abierta —una conexión cacheada, un backup viejo restaurado con otra sesión adentro— y
    entonces una consulta que la nombra se cae.
    Lo que la hace importante es DÓNDE se usa: el buscador. Al agregar `marca_repuesto` a la
    búsqueda por código y por texto, contra una base sin esa columna la pantalla principal de
    la app moría con «no such column: p.marca_repuesto». Una columna nueva que agrega una
    comodidad no puede tumbar lo único que la app tiene que hacer siempre."""
    try:
        return {f["name"] if isinstance(f, sqlite3.Row) else f[1]
                for f in cursor.execute("PRAGMA table_info(productos)").fetchall()}
    except sqlite3.Error as _err:
        anotar_error("_columnas_que_tiene_productos", _err)
        return set()


def campo_opcional_de_producto(cursor, columna, alias):
    """`p.columna AS "alias"` si la columna existe, y si no un NULL con el mismo alias.

    Devolver NULL y no omitir la columna es a propósito: quien lee el resultado encuentra la
    clave igual, con el valor vacío, que es exactamente lo que significa «esta base todavía no
    tiene ese dato»."""
    if columna in _columnas_que_tiene_productos(cursor):
        return f'p.{columna} AS "{alias}"'
    return f'NULL AS "{alias}"'


@functools.lru_cache(maxsize=1)
def _columnas_de_medidas_que_existen():
    """COLUMNAS_MEDIDAS, pero recortada a las columnas que la tabla tiene de verdad.

    Cacheada porque es puro esquema y se llamaba UNA VEZ POR PAR: analizando los 3.185
    pendientes salían 3.186 `PRAGMA table_info(productos)`, 0,158 s de puro preguntar lo mismo.
    El esquema no cambia mientras la app corre… salvo en el caso que esta función existe para
    cubrir, que es justamente restaurar un backup con otro esquema. Por eso restaurar_backup()
    limpia este caché: si no, quedaría contestando con las columnas de la base anterior.

    Es un cinturón de seguridad y salió de verlo fallar. Al agregar el espesor y las vías, la
    pantalla de equivalencias sugeridas se cayó con «no such column: espesor» contra una base
    que todavía no tenía la columna: la conexión está cacheada por Streamlit y el archivo se
    había reemplazado por debajo, así que la migración de esta versión no había corrido sobre
    esa conexión. Pasa igual al restaurar un backup viejo con otra sesión abierta.
    Una columna nueva no puede tumbar una pantalla entera: lo que falte se compara como
    «todavía no medido», que es exactamente lo que es."""
    existen = {f["name"] if isinstance(f, sqlite3.Row) else f[1]
               for f in c.execute("PRAGMA table_info(productos)").fetchall()}
    pedidas = [x.strip() for x in COLUMNAS_MEDIDAS.split(",")]
    return ", ".join(x for x in pedidas if x in existen) or "id"


def comparar_medidas(a, b, tolerancia_pct=3):
    """El núcleo de la comparación, sobre dos diccionarios de medidas ya leídos."""
    campos = CAMPOS_MEDIDAS
    if not a or not b:
        return None, "No se pudo leer alguno de los dos productos."

    comparadas, diferencias = [], []
    for campo, etiqueta in campos:
        # .get() y no [ ]: si la base todavía no tiene una medida nueva, el campo no viene en
        # el diccionario y la comparación tiene que seguir con las que sí están.
        # Ver _columnas_de_medidas_que_existen().
        va, vb = a.get(campo), b.get(campo)
        if va is None or vb is None:
            continue
        comparadas.append(etiqueta)
        if va == 0 or vb == 0:
            continue
        diferencia = abs(va - vb) / max(va, vb) * 100
        if diferencia > tolerancia_pct:
            diferencias.append(f"{etiqueta}: {va} vs {vb}")

    # Las vías van por igualdad exacta y no por tolerancia: una ficha de 2 vías y una de 3 no
    # se parecen «un 33%», son dos piezas que no entran una en lugar de la otra.
    # La posición va acá por el mismo motivo: el caño superior del radiador no es el inferior,
    # y el sensor de ABS trasero izquierdo no es el delantero derecho. No es «parecido en un
    # porcentaje», es otra pieza. Ver posicion_desde_descripcion().
    for campo, etiqueta in (("paso_rosca", "paso de rosca"), ("cantidad_estrias", "estrías"),
                            ("cantidad_vias", "vías de la ficha"),
                            ("cantidad_canales", "canales de la polea"),
                            ("posicion", "posición")):
        va, vb = a.get(campo), b.get(campo)
        if va in (None, "") or vb in (None, ""):
            continue
        comparadas.append(etiqueta)
        if str(va).strip().upper() != str(vb).strip().upper():
            diferencias.append(f"{etiqueta}: {va} vs {vb}")

    if not comparadas:
        return None, "Ninguno de los dos tiene medidas cargadas todavía."
    if diferencias:
        return False, "NO coinciden: " + "; ".join(diferencias)
    return True, "Coinciden en " + ", ".join(comparadas)


def comparar_medidas_productos(id_a, id_b, tolerancia_pct=3):
    """Compara las medidas mecánicas cargadas de dos productos. Devuelve (coinciden, detalle).
    Es evidencia física real, no una suposición: si un retén mide distinto, no entra, punto.
    Si a alguno le faltan medidas cargadas, no dice nada — no es prueba ni a favor ni en contra."""
    c.execute(f"SELECT id, {COLUMNAS_MEDIDAS} FROM productos WHERE id = ?", (id_a,))
    a = c.fetchone()
    c.execute(f"SELECT id, {COLUMNAS_MEDIDAS} FROM productos WHERE id = ?", (id_b,))
    b = c.fetchone()
    return comparar_medidas(dict(a) if a else None, dict(b) if b else None, tolerancia_pct)


def verificar_en_catalogo_oficial(codigo_a_buscar, url_ficha, tiempo_maximo=8):
    """Abre la ficha oficial del proveedor y fija si el otro código aparece escrito ahí.
    Es la evidencia más fuerte que se puede conseguir sin que nadie opine: o el proveedor
    lo lista en su propia página, o no. Compara sin guiones ni espacios, porque cada catálogo
    los escribe distinto (6Q0 407 365 / 6Q0407365 / 6Q0-407-365).
    Devuelve (encontrado, detalle). 'encontrado' es None si no se pudo consultar la página."""
    import requests
    if not url_ficha:
        return None, "Esa marca no tiene cargada la dirección de su catálogo."
    objetivo = sanitizar(codigo_a_buscar)
    if not objetivo:
        return None, "Código no válido."
    try:
        respuesta = requests.get(
            url_ficha, timeout=tiempo_maximo,
            headers={"User-Agent": "Mozilla/5.0 (compatible; EquivalenciasElChavo/1.0)"}
        )
        if respuesta.status_code != 200:
            return None, f"La página respondió {respuesta.status_code} — no se pudo verificar."
        texto_plano = sanitizar(re.sub(r"<[^>]+>", " ", respuesta.text))
        if objetivo in texto_plano:
            return True, f"El código {codigo_a_buscar} aparece en la ficha oficial del proveedor."
        return False, (f"El código {codigo_a_buscar} NO aparece en esa ficha. Puede que el "
                        "proveedor no lo liste, o que la página cargue los datos aparte.")
    except Exception as e:
        anotar_error("verificar_en_catalogo_oficial", e)
        return None, f"No se pudo consultar la página ({type(e).__name__})."


def nivel_por_evidencias(evidencias):
    """Traduce la evidencia acumulada a algo legible. Nunca da 'confirmada': eso lo decide
    una persona. Si hay evidencia EN CONTRA (ej: las medidas no coinciden), lo marca.

    Se llamaba nivel_de_confianza, igual que la de más abajo que recibe un PUNTAJE. Dos def con
    el mismo nombre no son un error de Python: la segunda simplemente pisa a la primera. Así que
    esta nunca llegaba a correr — descubrir_equivalencias_candidatas() le pasaba la lista de
    evidencias a la que espera un número y reventaba con "'>=' not supported between instances
    of 'list' and 'int'", tirando abajo toda la pantalla de equivalencias sugeridas apenas
    había una candidata con evidencia."""
    tipos = {e["tipo"] for e in evidencias}
    if "medidas_no_coinciden" in tipos or "catalogo_no_lo_lista" in tipos:
        return "⛔ Con evidencia en contra", 0
    puntaje = sum(PESOS_EVIDENCIA.get(t, 0) for t in tipos)
    if puntaje >= 100:
        return "🟢 Respaldo fuerte", puntaje
    if puntaje >= 45:
        return "🟡 Respaldo medio", puntaje
    return "🔴 Solo por repetición", puntaje


def marcar_revision(pares, decision):
    """Recuerda la decisión tomada sobre un vínculo, en los dos sentidos. 'ok' = ya lo miré y
    está bien (no volver a marcarlo en la auditoría). 'rechazada' = no es equivalente (además
    de borrarlo, no se vuelve a crear aunque se reimporte la lista del proveedor)."""
    if not pares:
        return
    filas = []
    for a, b in pares:
        filas.append((a, b, decision, obtener_usuario_actual()))
        filas.append((b, a, decision, obtener_usuario_actual()))
    with db_lock:
        c.executemany(
            "INSERT OR REPLACE INTO equivalencias_revisadas "
            "(producto_a_id, producto_b_id, decision, revisado_por) VALUES (?, ?, ?, ?)", filas
        )
        conn.commit()


def pares_rechazados():
    c.execute("SELECT producto_a_id, producto_b_id FROM equivalencias_revisadas WHERE decision = 'rechazada'")
    return {(r["producto_a_id"], r["producto_b_id"]) for r in c.fetchall()}


def eliminar_equivalencia(par_a, par_b, recordar_rechazo=True):
    """Borra el vínculo en los dos sentidos. Los productos quedan; solo se corta la relación."""
    with db_lock:
        c.execute("DELETE FROM equivalencias WHERE (producto_a_id = ? AND producto_b_id = ?) "
                   "OR (producto_a_id = ? AND producto_b_id = ?)", (par_a, par_b, par_b, par_a))
        conn.commit()
    if recordar_rechazo:
        marcar_revision([(par_a, par_b)], "rechazada")


def auditar_equivalencias_existentes(limite=20000):
    """Pasa las alarmas por las equivalencias YA cargadas y las devuelve AGRUPADAS por el
    conflicto, no de a pares sueltos. La diferencia importa: si una importación mal mapeada
    creó un producto basura (código '1', por ejemplo) vinculado a cientos de códigos de
    fábrica, verlo de a pares es imposible de resolver — agrupado se ve de una y se corta.
    Lo ya revisado como correcto no vuelve a aparecer."""
    campos_medida = ["diametro_interno", "diametro_externo", "diametro_interno_cara_b",
                      "diametro_externo_cara_b", "diametro_rosca_homocinetica", "diametro_copa",
                      "diametro_copa_superior", "largo_total", "ancho"]
    etiquetas = {"diametro_interno": "diám. interno", "diametro_externo": "diám. externo",
                  "diametro_interno_cara_b": "diám. interno cara B",
                  "diametro_externo_cara_b": "diám. externo cara B",
                  "diametro_rosca_homocinetica": "diám. rosca", "diametro_copa": "diám. copa (base)",
                  "diametro_copa_superior": "diám. copa (boca)", "largo_total": "largo total",
                  "ancho": "ancho"}
    sel_a = ", ".join(f"pa.{campo} AS a_{campo}" for campo in campos_medida)
    sel_b = ", ".join(f"pb.{campo} AS b_{campo}" for campo in campos_medida)

    c.execute(f"""SELECT e.producto_a_id AS a, e.producto_b_id AS b,
                         pa.codigo_raw AS cod_a, pa.descripcion AS desc_a, ma.nombre AS marca_a, ma.tipo AS tipo_a,
                         pb.codigo_raw AS cod_b, pb.descripcion AS desc_b, mb.nombre AS marca_b, mb.tipo AS tipo_b,
                         pa.paso_rosca AS a_paso, pb.paso_rosca AS b_paso,
                         pa.cantidad_estrias AS a_estrias, pb.cantidad_estrias AS b_estrias,
                         {sel_a}, {sel_b}
                  FROM equivalencias e
                  JOIN productos pa ON pa.id = e.producto_a_id
                  JOIN productos pb ON pb.id = e.producto_b_id
                  JOIN marcas ma ON ma.id = pa.marca_id
                  JOIN marcas mb ON mb.id = pb.marca_id
                  WHERE e.producto_a_id < e.producto_b_id
                  LIMIT ?""", (limite,))
    filas = [dict(r) for r in c.fetchall()]

    c.execute("SELECT producto_a_id, producto_b_id FROM equivalencias_revisadas WHERE decision = 'ok'")
    ya_ok = {(r["producto_a_id"], r["producto_b_id"]) for r in c.fetchall()}

    # Cuántos vínculos tiene cada producto: sirve para detectar productos basura, que
    # terminan colgados de decenas o cientos de códigos de fábrica.
    vinculos_por_producto = {}
    for f in filas:
        for lado in ("a", "b"):
            pid = f[lado]
            info = vinculos_por_producto.setdefault(pid, {
                "id": pid, "codigo": f[f"cod_{lado}"], "descripcion": f[f"desc_{lado}"],
                "marca": f[f"marca_{lado}"], "tipo": f[f"tipo_{lado}"], "cantidad": 0
            })
            info["cantidad"] += 1

    # Conflicto: un código de fábrica que apunta a varios productos del MISMO proveedor
    grupos = {}
    for f in filas:
        if f["tipo_a"] == "OEM" and f["tipo_b"] != "OEM":
            oem_cod, oem_desc, otro_lado = f["cod_a"], f["desc_a"], "b"
        elif f["tipo_b"] == "OEM" and f["tipo_a"] != "OEM":
            oem_cod, oem_desc, otro_lado = f["cod_b"], f["desc_b"], "a"
        else:
            continue
        clave = (sanitizar(oem_cod), f[f"marca_{otro_lado}"])
        grupo = grupos.setdefault(clave, {
            "codigo_oem": oem_cod, "descripcion_oem": oem_desc or "",
            "marca_proveedor": f[f"marca_{otro_lado}"], "productos": {}
        })
        pid = f[otro_lado]
        grupo["productos"][pid] = {
            "id": pid, "codigo": f[f"cod_{otro_lado}"], "descripcion": f[f"desc_{otro_lado}"] or "",
            "par": (f["a"], f["b"]),
            "revisado_ok": (f["a"], f["b"]) in ya_ok,
            "vinculos_totales": vinculos_por_producto.get(pid, {}).get("cantidad", 0),
        }

    conflictos = []
    for clave, g in grupos.items():
        pendientes = [p for p in g["productos"].values() if not p["revisado_ok"]]
        if len(g["productos"]) > 1 and pendientes:
            g["productos"] = sorted(g["productos"].values(), key=lambda p: -p["vinculos_totales"])
            conflictos.append(g)
    conflictos.sort(key=lambda g: -len(g["productos"]))

    # Medidas contradictorias (esto sí tiene sentido de a pares)
    # Códigos que no parecen códigos: lo que deja una importación mal mapeada
    codigos_malos = {}
    for f in filas:
        if (f["a"], f["b"]) in ya_ok:
            continue
        for lado in ("a", "b"):
            pid = f[lado]
            if pid in codigos_malos:
                continue
            malo, motivo = codigo_sospechoso(f[f"cod_{lado}"], f.get(f"desc_{lado}", ""))
            if malo:
                codigos_malos[pid] = {
                    "id": pid, "codigo": f[f"cod_{lado}"], "marca": f[f"marca_{lado}"],
                    "motivo": motivo,
                    "vinculos": vinculos_por_producto.get(pid, {}).get("cantidad", 0),
                }

    por_medidas = []
    for f in filas:
        if (f["a"], f["b"]) in ya_ok:
            continue
        diferencias = []
        for campo in campos_medida:
            va, vb = f[f"a_{campo}"], f[f"b_{campo}"]
            if not va or not vb:
                continue
            if abs(va - vb) / max(va, vb) * 100 > 3:
                diferencias.append(f"{etiquetas[campo]}: {va} vs {vb}")
        for clave_c, etiqueta in (("paso", "paso de rosca"), ("estrias", "estrías")):
            va, vb = f[f"a_{clave_c}"], f[f"b_{clave_c}"]
            if va in (None, "") or vb in (None, ""):
                continue
            if str(va).strip().upper() != str(vb).strip().upper():
                diferencias.append(f"{etiqueta}: {va} vs {vb}")
        if diferencias:
            por_medidas.append({
                "a": f["a"], "b": f["b"], "cod_a": f["cod_a"], "desc_a": f["desc_a"] or "",
                "marca_a": f["marca_a"], "cod_b": f["cod_b"], "desc_b": f["desc_b"] or "",
                "marca_b": f["marca_b"], "detalle": "; ".join(diferencias),
            })

    # Productos con una cantidad de vínculos fuera de lo normal: candidatos a basura
    sospechosos = sorted(
        [v for v in vinculos_por_producto.values() if v["cantidad"] >= 10 and v["tipo"] != "OEM"],
        key=lambda v: -v["cantidad"]
    )

    # Si se llegó al tope, se revisó solo una parte: hay que decirlo, porque si no queda la
    # falsa sensación de que está todo limpio cuando ni siquiera se miró la mitad.
    c.execute("SELECT COUNT(*) FROM equivalencias WHERE producto_a_id < producto_b_id")
    total_en_base = c.fetchone()[0]

    return {
        "total_revisados": len(filas),
        "total_en_base": total_en_base,
        "quedo_corta": len(filas) >= limite and total_en_base > len(filas),
        "ya_revisados_ok": len(ya_ok),
        "conflictos": conflictos,
        "por_medidas": por_medidas,
        "codigos_malos": sorted(codigos_malos.values(), key=lambda x: -x["vinculos"])[:50],
        "productos_sospechosos": sospechosos[:30],
    }


def cb_auditoria_eliminar(par_a, par_b):
    """Borra el vínculo Y vuelve a calcular la auditoría. Sin esto último el panel seguía
    mostrando el resultado viejo (guardado desde que se tocó 'Auditar'), y parecía que el
    botón no hacía nada aunque el vínculo sí se hubiera borrado."""
    eliminar_equivalencia(par_a, par_b)
    st.session_state["resultado_auditoria"] = auditar_equivalencias_existentes()


def cb_auditoria_dejar(pares):
    marcar_revision(pares, "ok")
    st.session_state["resultado_auditoria"] = auditar_equivalencias_existentes()


def cb_auditoria_cortar_todos(producto_id):
    cortar_todos_los_vinculos(producto_id)
    st.session_state["resultado_auditoria"] = auditar_equivalencias_existentes()



def cortar_todos_los_vinculos(producto_id, recordar_rechazo=True):
    """Corta TODAS las equivalencias de un producto de una sola vez. Para cuando quedó un
    producto basura de una importación mal mapeada colgado de decenas de códigos."""
    c.execute("""SELECT producto_a_id, producto_b_id FROM equivalencias
                 WHERE producto_a_id = ? OR producto_b_id = ?""", (producto_id, producto_id))
    pares = [(r["producto_a_id"], r["producto_b_id"]) for r in c.fetchall()]
    with db_lock:
        c.execute("DELETE FROM equivalencias WHERE producto_a_id = ? OR producto_b_id = ?",
                   (producto_id, producto_id))
        conn.commit()
    if recordar_rechazo and pares:
        marcar_revision(pares, "rechazada")
    return len(pares)


def pares_ya_cargados():
    """Los pares que ya son equivalencia cargada, como (menor, mayor). Ver
    guardar_equivalencias_pendientes()."""
    c.execute("""SELECT MIN(producto_a_id, producto_b_id) AS a,
                        MAX(producto_a_id, producto_b_id) AS b FROM equivalencias""")
    return {(r["a"], r["b"]) for r in c.fetchall()}


def guardar_equivalencias_pendientes(pares, origen, lote):
    """Guarda vínculos para revisar en vez de cargarlos directo. Devuelve cuántos PARES entraron.

    Tres cosas se hacen acá y no en quien llama, porque quien llama son cinco lugares distintos
    y basta con que uno se olvide:

    · LO QUE YA RECHAZASTE NO VUELVE. Era el agujero más grande: ninguno de los dos que más
      proponen —el barrido de todo el catálogo y los códigos escritos en la descripción— miraba
      las decisiones anteriores, y desde que corren solos después de cada importación eso quería
      decir que TODO lo rechazado volvía a la cola con la lista siguiente. Medido: se rechazaron
      300 pares a mano, se corrió el descubrimiento de la importación siguiente, y volvieron los
      300 —y la app los anunció como nuevos—. Revisar no servía para nada si la revisión no
      quedaba. La importación de una lista ya lo hacía (ver `rechazados_antes`); esto no.
    · Lo que ya está cargado tampoco: preguntar si se aprueba algo aprobado es ruido.
    · Se guarda UNA fila por par, (menor, mayor). Quien llama mandaba las dos direcciones, la
      cola guardaba las dos, y todo lo que la cuenta con COUNT(*) —el cartel del buscador, el
      selector de listas, «Descartar TODO lo pendiente», el aviso de salud— decía el doble,
      mientras la pantalla de revisión, que filtra `a < b`, mostraba la mitad. Después de un
      descubrimiento sobre la base real: el buscador decía 22.309 esperando y los pares eran
      12.747; el selector decía 17.326 para el barrido y adentro había 8.648. Y peor: cuando
      el mismo par caía en dos listas, una se quedaba con la ida y otra con la vuelta, y la
      vuelta era invisible en la revisión —30 así en el barrido—, así que esa lista no se
      terminaba de vaciar nunca."""
    if not pares:
        return 0
    rechazados = pares_rechazados()
    cargados = pares_ya_cargados()
    vistos, limpios = set(), []
    for a, b in pares:
        if a == b:
            continue
        par = (min(a, b), max(a, b))
        if par in vistos or par in rechazados or par in cargados:
            continue
        vistos.add(par)
        limpios.append(par)
    # El kit y su pieza no son una equivalencia, así que no se pregunta. Ver
    # pares_de_kit_y_pieza().
    _kits = pares_de_kit_y_pieza(limpios)
    pares = [par for par in limpios if par not in _kits]
    if not pares:
        return 0
    with db_lock:
        c.executemany(
            "INSERT OR IGNORE INTO equivalencias_pendientes "
            "(producto_a_id, producto_b_id, origen, lote) VALUES (?, ?, ?, ?)",
            [(a, b, origen, lote) for a, b in pares]
        )
        # rowcount y no len(pares): con INSERT OR IGNORE, los que ya estaban en la cola no
        # entran, y devolver cuántos se INTENTARON es decir un número que no pasó. Se nota
        # ahora que esto corre solo después de cada importación: el barrido propone los mismos
        # 8.654 pares cada vez, y sin esto la app iba a anunciar 8.654 nuevos todas las veces.
        entraron = c.rowcount
        conn.commit()
    return max(entraron, 0)





def resumen_lotes_pendientes():
    c.execute("""SELECT lote, origen, COUNT(*) AS cantidad, MIN(fecha) AS fecha
                 FROM equivalencias_pendientes GROUP BY lote, origen ORDER BY MIN(fecha) DESC""")
    return [dict(r) for r in c.fetchall()]


def equivalencias_esperando_revision():
    """Cuántos vínculos hay cargados pero todavía sin aprobar.

    Se muestra en el buscador porque es ahí donde se sufre: mientras estén esperando, buscar un
    código NO trae los equivalentes de las otras marcas. Es exactamente el síntoma de «la app no
    relaciona proveedores», y hasta ahora no había nada que lo dijera fuera de otra pantalla."""
    try:
        c.execute("SELECT COUNT(*) FROM equivalencias_pendientes")
        return c.fetchone()[0]
    except sqlite3.OperationalError as _err:
        anotar_error("equivalencias_esperando_revision", _err)
        return 0


def contar_pendientes_del_lote(lote):
    c.execute("""SELECT COUNT(*) FROM equivalencias_pendientes
                 WHERE lote = ? AND producto_a_id < producto_b_id""", (lote,))
    return c.fetchone()[0]


MINIMO_PARA_APRENDER = 12      # decisiones necesarias antes de confiar en un patrón


def sustituciones_reales(minimo_veces=2, limite=300):
    """Qué código pediste y qué terminaste vendiendo. Es la evidencia más fuerte que hay.

    La app venía guardando esto en cada venta y no se usaba para nada. Y no es poca cosa: si un
    cliente pidió el código A y se le vendió el B, alguien del mostrador decidió que el B servía,
    el cliente se lo llevó y no volvió a reclamar. Eso pesa más que cualquier lista de
    proveedor — una lista dice lo que el proveedor cree; esto es lo que pasó de verdad.

    Se pide que haya ocurrido varias veces: una sola puede ser un error de tipeo o una venta
    por descarte."""
    c.execute("""SELECT v.codigo_pedido_clean AS pedido, v.producto_id AS vendido,
                        COUNT(*) AS veces, MAX(v.fecha) AS ultima
                 FROM ventas_registradas v
                 JOIN productos p ON p.id = v.producto_id
                 WHERE v.codigo_pedido_clean IS NOT NULL
                   AND v.codigo_pedido_clean <> ''
                   AND v.codigo_pedido_clean <> p.codigo_clean
                 GROUP BY v.codigo_pedido_clean, v.producto_id
                 HAVING COUNT(*) >= ?
                 ORDER BY COUNT(*) DESC LIMIT ?""", (minimo_veces, limite))
    filas = filas_a_listas(c)

    salida = []
    for f in filas:
        c.execute("""SELECT p.id, p.codigo_raw, p.descripcion, m.nombre AS marca
                     FROM productos p JOIN marcas m ON m.id = p.marca_id
                     WHERE p.codigo_clean = ? LIMIT 1""", (f["pedido"],))
        pedido = c.fetchone()
        c.execute("""SELECT p.id, p.codigo_raw, p.descripcion, m.nombre AS marca
                     FROM productos p JOIN marcas m ON m.id = p.marca_id
                     WHERE p.id = ?""", (f["vendido"],))
        vendido = c.fetchone()
        if not pedido or not vendido or pedido["id"] == vendido["id"]:
            continue
        c.execute("""SELECT 1 FROM equivalencias
                     WHERE producto_a_id = ? AND producto_b_id = ?""",
                  (min(pedido["id"], vendido["id"]), max(pedido["id"], vendido["id"])))
        ya_esta = c.fetchone() is not None
        salida.append({
            "Te pidieron": pedido["codigo_raw"], "Marca pedida": pedido["marca"],
            "Vendiste": vendido["codigo_raw"], "Marca vendida": vendido["marca"],
            "Veces": f["veces"], "Última": (f["ultima"] or "")[:10],
            "¿Ya vinculado?": "sí" if ya_esta else "no",
            "_a": pedido["id"], "_b": vendido["id"], "_ya": ya_esta,
        })
    return salida


def pares_confirmados_por_ventas(minimo_veces=2):
    """Los pares que la venta real confirmó, para usarlos como señal de confianza."""
    try:
        c.execute("""SELECT p1.id AS a, v.producto_id AS b, COUNT(*) AS veces
                     FROM ventas_registradas v
                     JOIN productos p ON p.id = v.producto_id
                     JOIN productos p1 ON p1.codigo_clean = v.codigo_pedido_clean
                     WHERE v.codigo_pedido_clean IS NOT NULL
                       AND v.codigo_pedido_clean <> ''
                       AND p1.id <> v.producto_id
                     GROUP BY p1.id, v.producto_id
                     HAVING COUNT(*) >= ?""", (minimo_veces,))
        return {(min(r["a"], r["b"]), max(r["a"], r["b"])): r["veces"] for r in c.fetchall()}
    except sqlite3.OperationalError as _err:
        anotar_error("pares_confirmados_por_ventas", _err)
        return {}


def aprender_de_las_decisiones():
    """Mira lo que fuiste aprobando y descartando, y saca patrones para usarlos después.

    Es la parte que faltaba para que el sistema mejore con el uso. Cada vez que aprobás o
    descartás un vínculo esa decisión se guardaba, pero no servía para nada. Y ahí hay
    información concreta sobre TU base:

      · combinaciones de marcas que casi siempre resultan bien (MAHLE ↔ OEM) o casi siempre mal
      · rubros que en tu catálogo sí se cruzan de verdad, aunque parezcan distintos

    Se exige un mínimo de decisiones antes de creerle a un patrón: con tres casos no se puede
    concluir nada, y una regla sacada de poca evidencia es peor que no tener regla."""
    patrones = {"marcas": {}, "total": 0}
    try:
        c.execute("""SELECT ma.nombre AS marca_a, mb.nombre AS marca_b, r.decision,
                            COUNT(*) AS n
                     FROM equivalencias_revisadas r
                     JOIN productos pa ON pa.id = r.producto_a_id
                     JOIN productos pb ON pb.id = r.producto_b_id
                     JOIN marcas ma ON ma.id = pa.marca_id
                     JOIN marcas mb ON mb.id = pb.marca_id
                     WHERE r.producto_a_id < r.producto_b_id
                     GROUP BY ma.nombre, mb.nombre, r.decision""")
        crudo = c.fetchall()
    except sqlite3.OperationalError as _err:
        anotar_error("aprender_de_las_decisiones", _err)
        return patrones

    acumulado = {}
    for fila in crudo:
        clave = tuple(sorted((fila["marca_a"], fila["marca_b"])))
        d = acumulado.setdefault(clave, {"ok": 0, "rechazada": 0})
        d[fila["decision"]] = d.get(fila["decision"], 0) + fila["n"]

    for clave, d in acumulado.items():
        total = d["ok"] + d["rechazada"]
        patrones["total"] += total
        if total >= MINIMO_PARA_APRENDER:
            patrones["marcas"][clave] = {
                "tasa_ok": d["ok"] / total, "decisiones": total,
                "ok": d["ok"], "rechazadas": d["rechazada"],
            }
    return patrones


def senal_aprendida(marca_a, marca_b, patrones):
    """Cuánto suma o resta esta combinación de marcas, según cómo te fue antes con ella."""
    if not patrones or not patrones.get("marcas"):
        return 0, None
    dato = patrones["marcas"].get(tuple(sorted((marca_a or "", marca_b or ""))))
    if not dato:
        return 0, None
    tasa, n = dato["tasa_ok"], dato["decisiones"]
    if tasa >= 0.85:
        return 15, ("bien", f"📚 De {n} vínculos {marca_a}↔{marca_b} que revisaste, "
                             f"aprobaste el {tasa*100:.0f}%")
    if tasa <= 0.20:
        return -30, ("mal", f"📚 De {n} vínculos {marca_a}↔{marca_b} que revisaste, "
                             f"descartaste el {(1-tasa)*100:.0f}%")
    return 0, None


@st.cache_data(ttl=300, show_spinner=False)
def escalas_de_precio():
    """El precio típico (la mediana) de cada marca, para poder comparar entre listas.

    Va con caché porque evidencia_cruzada() la consulta UNA VEZ POR PAR, y sin caché eso es
    recorrer los 40.000 precios del catálogo por cada uno de los cientos de pares que se están
    revisando. Los cinco minutos de vida alcanzan de sobra: la escala de una lista solo cambia
    cuando se importa una lista nueva.

    Hace falta porque dos listas pueden estar en escalas completamente distintas: una
    desactualizada, otra sin IVA, otra en otra unidad. Sobre las listas reales de acá el precio
    mediano de un proveedor es $1.350 y el de otro $37.610. Sin corregir por eso, cualquier
    comparación de precios entre esas dos listas dice siempre lo mismo y no informa nada.

    Se usa la MEDIANA y no el promedio a propósito: un solo motor de $3.000.000 en una lista de
    tornillos corre el promedio y deja la escala mal."""
    try:
        c.execute("""SELECT m.nombre AS marca, p.precio AS precio
                     FROM productos p JOIN marcas m ON m.id = p.marca_id
                     WHERE p.precio IS NOT NULL AND p.precio > 0
                     ORDER BY m.nombre, p.precio""")
        from collections import defaultdict
        por_marca = defaultdict(list)
        for fila in c.fetchall():
            por_marca[fila["marca"]].append(fila["precio"])
    except sqlite3.OperationalError as _err:
        anotar_error("escalas_de_precio", _err)
        return {}
    # Menos de 20 precios no alcanza para hablar de la escala de una lista.
    return {marca: precios[len(precios) // 2]
            for marca, precios in por_marca.items() if len(precios) >= 20}


# Una descripción tiene que tener algo adentro para que «son iguales» signifique algo. Con
# «JUNTA» o «FILTRO» sueltos coinciden piezas que no tienen nada que ver. Medido sobre las
# 70.888 descripciones reales: la mediana son 59 caracteres y solo 1.264 de 70.888 tienen 20 o
# menos, así que el piso deja afuera las de una palabra suelta y nada más.
LARGO_DESCRIPCION_QUE_CONVENCE = 20


def evaluar_equivalencia(desc_a, desc_b, medidas_a=None, medidas_b=None,
                         precio_a=None, precio_b=None, veces_confirmada=1,
                         respaldo_fabricante=False, marca_a="", marca_b="", patrones=None,
                         vendido_como_reemplazo=0, codigo_puente=None,
                         productos_del_puente=0, escalas=None, trae_al_otro="",
                         variante_del_origen=""):
    """Pesa toda la evidencia disponible sobre un vínculo. Devuelve (puntaje 0-100, señales).

    La diferencia con lo que había antes: las alarmas eran una lista plana, así que 397 vínculos
    con alarma se veían todos igual de mal y había que mirarlos de a uno. Pero no valen lo mismo.
    Un vínculo entre un filtro y una pastilla de freno es basura segura; uno entre dos filtros
    con precios parecidos y confirmado por dos listas distintas es casi seguro bueno.

    Las señales, de la más fuerte a la más débil:
      · las medidas se contradicen  -> prueba física en contra, no hay vuelta
      · son de rubros distintos     -> un filtro no equivale a una pastilla
      · lo dice el fabricante       -> el catálogo de aplicaciones lo respalda
      · lo confirman varias listas  -> dos proveedores independientes coinciden
      · los precios no cierran      -> sospechoso, pero puede ser una diferencia de marca
    """
    puntaje = 50.0
    senales = []

    # EL CÓDIGO DE FÁBRICA QUE HACE DE PUENTE. Sin esto, casi ningún vínculo se movía del 50.
    # Motivo: la abrumadora mayoría de los vínculos de esta base no son proveedor↔proveedor,
    # son proveedor↔código de fábrica, y el nodo del código no tiene descripción, ni rubro, ni
    # precio, ni medidas. O sea que TODAS las señales de más abajo quedaban inertes justo en el
    # caso más común. Medido sobre la base real: 24.774 vínculos, el 98% caía en la misma banda
    # y el máximo de todos era 75. Una columna de confianza donde todo dice lo mismo no informa
    # nada, y encima da la falsa impresión de que se está midiendo algo.
    #
    # Para ese caso hay dos señales que sí existen, y las dos se midieron sobre listas reales:
    if codigo_puente:
        limpio_puente = sanitizar(codigo_puente)
        largo = len(limpio_puente)
        solo_numeros = limpio_puente.isdigit()
        # 1. QUÉ TAN DISTINTIVO es el código. '0221604014' es un código de fábrica; '1234' lo
        #    tiene medio catálogo del rubro porque numeran de corrido.
        if largo >= 8 or (largo >= 6 and not solo_numeros):
            puntaje += 20
            senales.append(("bien", f"🔑 El código que los une ({codigo_puente}) es largo y "
                                     "distintivo: difícil que coincida por casualidad"))
        elif largo < 4 or (solo_numeros and largo < 6):
            puntaje -= 25
            senales.append(("mal", f"🔑 El código que los une ({codigo_puente}) es corto y "
                                    "genérico: puede coincidir con cualquier cosa"))
        # 2. A CUÁNTOS PRODUCTOS se cuelga ese mismo código. Se midió sobre cinco listas reales:
        #    el 99,9% de los códigos de fábrica verdaderos unen 4 productos o menos, y los que
        #    unían 6 o más resultaron todos texto (F14000 el camión, AP-2000 el motor). Un
        #    código que une dos productos es el caso típico y sano: el mismo repuesto en dos
        #    proveedores.
        if productos_del_puente >= 6:
            puntaje -= 30
            senales.append(("mal", f"🕸️ Ese mismo código cuelga {productos_del_puente} productos. "
                                    "Los códigos de fábrica reales casi nunca pasan de 4: "
                                    "revisalo en Mantenimiento → Puentes falsos"))
        elif 0 < productos_del_puente <= 2:
            puntaje += 10
            senales.append(("bien", "🕸️ Ese código une solo estos dos: es el mismo repuesto en "
                                     "dos proveedores"))

    # EL NODO DE FÁBRICA NO TIENE MEDIDAS PROPIAS cuando el otro lado es una variante del que
    # lo creó, así que acá no hay prueba física que valga. El producto OEM se crea copiando la
    # descripción de la fila que primero nombró ese número, y las medidas se leen de esa copia:
    # comparar el espesor de «TC-615-MG 4M» (2,40 mm) contra el que el nodo heredó de
    # «TC-615-MG 0M» (1,65 mm) es compararlo contra su propio hermano. La diferencia está
    # garantizada por construcción y no dice nada del vínculo.
    # Medido sobre la cola real: de los 3.185 pendientes hay 34 con la medida contradiciéndose,
    # y los 34 son exactamente este caso —misma base de código que el origen—. Ni uno solo era
    # una pieza distinta.
    if medidas_a and medidas_b and not variante_del_origen:
        coinciden, detalle = comparar_medidas(medidas_a, medidas_b)
        if coinciden is False:
            # TOPE, no resta. Esta función dice arriba que las medidas que se contradicen son
            # «prueba física en contra, no hay vuelta», y restando no era así: un sensor de
            # rotación de 3 polos vinculado a uno de 2 —misma marca, mismo auto, misma
            # resistencia— se iba a 20 por la medida y volvía a 50 porque el código de fábrica
            # que los une es largo y cuelga pocos productos. Quedaba arriba del umbral y la
            # auditoría no lo mostraba nunca; el buscador lo tenía con 95 de confianza.
            # Que el código «parezca un código» no puede ganarle a que las dos piezas midan
            # distinto: lo primero es una pista sobre el número, lo segundo es la pieza.
            puntaje = min(puntaje - 45, 15.0)
            senales.append(("mal", f"📐 {detalle}"))
        elif coinciden is True:
            puntaje += 30
            senales.append(("bien", f"📐 {detalle}"))

    # UNO VIENE ADENTRO DEL OTRO ('trae_al_otro' lo calcula quien llama, que es el que tiene
    # los códigos a mano). Va antes que el rubro, porque explica la mitad de los casos en
    # que los rubros no coinciden y NO es un error: la bujía está adentro del «KIT CAB Y BUJ»,
    # la bomba de agua adentro de «DISTRIBUCION C/BOMBA», el filtro de la bomba de nafta cita
    # el mismo número de Bosch que la bomba. Los rubros son distintos porque las piezas son
    # distintas — y aun así la relación es de verdad, solo que no es una equivalencia: no se
    # puede vender una en lugar de la otra.
    # Sobre los 208 vínculos cargados con rubros distintos, 126 son de esta clase.
    # Decirlo cambia qué hace el que revisa: en vez de mirar uno por uno buscando el error,
    # descarta el grupo entero sabiendo que el buscador igual se los muestra como kit.
    kit_de = trae_al_otro
    if kit_de:
        puntaje -= 40
        senales.append(("mal", f"📦 No son equivalentes: {kit_de}. El buscador te lo ofrece "
                                "igual, como kit, cuando buscás la pieza suelta"))

    # LA MISMA DESCRIPCIÓN DE LOS DOS LADOS. Faltaba, y es la señal que decidía la mayoría de
    # la cola sin que nadie la mirara: sobre los 3.185 pendientes reales había 2.495 pares con
    # la descripción palabra por palabra igual, y el puntaje los repartía entre 🟡 (1.330),
    # 🟠 (1.048) y hasta 🔴 (117). NINGUNO llegaba a 🟢 — el máximo de toda la cola era 65 —
    # así que había que mirar 3.185 vínculos de a uno para aprobar una lista que estaba bien.
    #
    # Qué prueba de verdad, dicho sin exagerar: que el vínculo salió de UNA MISMA FILA de la
    # lista del proveedor —el importador copia la descripción de la fila al crear el producto
    # OEM— o que dos proveedores copiaron la misma fuente. O sea, que lo declaró el proveedor.
    # Es la misma clase de evidencia que un «REF ORIG», y no es una certeza: si la columna de
    # OEM de esa lista está mal mapeada, van a estar todas mal Y con la descripción igual. Por
    # eso suma fuerte pero no blinda — el rubro distinto, las medidas que se contradicen y el
    # puente que cuelga de veinte productos siguen restando abajo y tumban el par igual.
    #
    # Se pide una descripción larga: «JUNTA» igual de los dos lados no dice nada, y las
    # descripciones vacías coincidirían entre sí.
    _da, _db = normalizar_texto(desc_a or ""), normalizar_texto(desc_b or "")
    if _da and _da == _db and len(_da) >= LARGO_DESCRIPCION_QUE_CONVENCE:
        puntaje += 35
        senales.append(("bien", "📄 Los dos tienen EXACTAMENTE la misma descripción: salieron "
                                 "de la misma fila de la lista del proveedor"))
    elif variante_del_origen:
        # LA MISMA EVIDENCIA, POR ORDEN DE LLEGADA. Vale lo mismo que la de arriba y por eso
        # suma lo mismo, pero hay que decirlo aparte porque la de arriba no la alcanzaba.
        #
        # El nodo de fábrica se crea copiando la descripción de la fila que primero nombró ese
        # número. O sea que «la descripción coincide» quiere decir, en realidad, «esta fila fue
        # la primera». El hermano que cita EL MISMO número con la misma evidencia arrancaba 35
        # puntos abajo por el azar del orden de importación, y nada más que por eso.
        #
        # Medido sobre la cola real: de 2.397 números de fábrica, 2.296 tienen exactamente una
        # fila de origen. De los 919 vínculos que hoy hay que revisar a mano, 643 —el 70 %— son
        # hermanos. En una muestra de 30 revisada a mano, 18 eran vínculos correctos frenados
        # por esto.
        #
        # Se pide que compartan la base del código, que es lo que distingue a una variante:
        # «TC-703-MG» y «TC-703-15» son la misma junta en otro material. En una muestra de 20
        # al azar, 20/20 correctos.
        puntaje += 35
        senales.append(("bien", f"📄 {variante_del_origen}"))

    # Rubro: es la señal más barata y una de las que más basura caza. Si las descripciones
    # hablan de piezas de familias distintas, el vínculo no puede ser correcto.
    fam_a = familia_para_comparar(desc_a) if desc_a else "Sin clasificar"
    fam_b = familia_para_comparar(desc_b) if desc_b else "Sin clasificar"
    if fam_a != "Sin clasificar" and fam_b != "Sin clasificar":
        if fam_a != fam_b and not kit_de:
            puntaje -= 40
            senales.append(("mal", f"🧩 Son de rubros distintos: «{fam_a}» y «{fam_b}»"))
        else:
            puntaje += 15
            senales.append(("bien", f"🧩 Los dos son de «{fam_a}»"))

    # La venta real es la señal más fuerte de todas: no es lo que alguien cree que sirve, es
    # lo que efectivamente se vendió en su lugar y el cliente se llevó.
    if vendido_como_reemplazo >= 2:
        puntaje += 35
        senales.append(("bien", f"🧾 Ya lo vendiste como reemplazo {vendido_como_reemplazo} "
                                 "vez(ces): funcionó en el mostrador"))

    if respaldo_fabricante:
        puntaje += 25
        senales.append(("bien", "🏭 El catálogo del fabricante respalda este vínculo"))

    if veces_confirmada >= 2:
        puntaje += 20
        senales.append(("bien", f"📋 Lo confirman {veces_confirmada} listas distintas"))

    # Lo aprendido de tus propias decisiones anteriores
    ajuste, senal = senal_aprendida(marca_a, marca_b, patrones)
    if senal:
        puntaje += ajuste
        senales.append(senal)

    if precio_a and precio_b and precio_a > 0 and precio_b > 0:
        razon = max(precio_a, precio_b) / min(precio_a, precio_b)
        # La diferencia se mide contra lo TÍPICO entre esos dos proveedores, no en absoluto.
        # Dos listas pueden estar en escalas completamente distintas —una desactualizada, otra
        # sin IVA, otra en otra unidad— y entonces TODAS las parejas entre ellas se diferencian
        # por el mismo factor. Medido sobre las listas reales: el precio mediano de un proveedor
        # es $1.350 y el de otro $37.610, o sea 28 veces. Con el umbral fijo en 8, cada pareja
        # entre esos dos disparaba la alarma aunque fuera la misma bobina — 191 de 260
        # sugerencias marcadas "con algo raro", y la alarma era siempre esta.
        # Una alarma que salta siempre no informa: enseña a ignorarla, y con ella se ignoran
        # las que sí importan.
        # Corrigiendo por la escala, lo que queda es la diferencia REAL de esa pareja: si dos
        # listas van 28 veces en general y esta pareja va 13, no hay nada raro; si va 300, sí.
        esperada = 1.0
        if escalas:
            ea, eb = escalas.get(marca_a) or 0, escalas.get(marca_b) or 0
            if ea > 0 and eb > 0:
                esperada = max(ea, eb) / min(ea, eb)
        razon_real = razon / esperada if esperada > 1 else razon
        if razon_real < 1:
            razon_real = 1 / razon_real
        if razon_real >= 8:
            puntaje -= 25
            senales.append(("mal", f"💲 Los precios se diferencian {razon:.0f} veces"
                                   + (f", y entre estos dos proveedores lo normal es "
                                      f"{esperada:.0f}" if esperada > 2 else "")))
        elif razon_real <= 2:
            puntaje += 10
            senales.append(("bien", "💲 Los precios son parecidos"
                                    + (" para lo que suele haber entre estas dos listas"
                                       if esperada > 2 else "")))

    return max(0.0, min(100.0, puntaje)), senales


def nivel_de_confianza(puntaje):
    """Traduce el puntaje a algo accionable, sin prometer de más."""
    if puntaje >= 75:
        return "🟢 Muy probable", "se puede aprobar sin mirar"
    if puntaje >= 55:
        return "🟡 Probable", "razonable, pero conviene una mirada"
    if puntaje >= 30:
        return "🟠 Dudosa", "revisala"
    return "🔴 Casi seguro mal", "descartala salvo que sepas que está bien"


# Las decisiones sobre los sospechosos se juntan y se aplican de una. Antes cada «Los N están
# bien» se aplicaba al tocarlo, y cada aplicación rehace el análisis del lote entero: 5 a 8 s
# sobre los 8.648 de BARRIDO. Revisar todo son unas 50 decisiones: varios minutos de reloj de
# arena. Ahora cada grupo (o cada par, adentro de «Ver uno por uno») se marca, y un solo botón
# aplica todo: una espera en vez de cincuenta. Rehacer el análisis después de cada decisión NO
# se puede evitar —decidir unos pares cambia el puntaje de otros, ver el README—, pero sí
# hacerlo una vez por tanda en vez de una por grupo.
# Se guardan por par y no por grupo: el mismo motivo aparece en varias páginas, y cambiar
# «Mostrar de a» rearma los grupos. Atado al grupo, lo decidido en la página 1 se hubiera
# aplicado a los de la página 2.
DECISIONES_DE_REVISION = {"—": None, "✅ Están bien": "bien", "🚫 Descartar": "mal"}
_ROTULO_DE_LA_DECISION = {v: k for k, v in DECISIONES_DE_REVISION.items()}


def decisiones_del_lote(lote):
    """{(a, b): 'bien'|'mal'} de lo marcado y todavía no aplicado en ese lote, en esta sesión."""
    return st.session_state.setdefault("_decisiones_por_lote", {}).setdefault(lote, {})


def anotar_decision(lote, clave_del_selector, pares):
    """on_change de los selectores de revisión: anota (o borra) la decisión de esos pares."""
    decididas = decisiones_del_lote(lote)
    que = DECISIONES_DE_REVISION.get(st.session_state.get(clave_del_selector))
    for par in pares:
        if que:
            decididas[par] = que
        else:
            decididas.pop(par, None)


def aplicar_decisiones(lote):
    """Aplica todo lo marcado en el lote, de una vez. Lo que otro ya resolvió mientras tanto se
    saltea solo (ver _los_que_siguen_pendientes())."""
    decididas = decisiones_del_lote(lote)
    bien = [par for par, que in decididas.items() if que == "bien"]
    mal = [par for par, que in decididas.items() if que == "mal"]
    n_bien = aprobar_pendientes(lote, bien) if bien else 0
    if mal:
        rechazar_pendientes(lote, mal)
    decididas.clear()
    invalidar_salud()
    ya_resueltos = len(bien) - n_bien
    # Flotante y no avisar(): el botón de abajo deja la pantalla scrolleada abajo, y avisar()
    # escribe arriba de todo, donde en el celular no se ve.
    st.toast(f"✅ Listo: {n_bien} aprobado(s) y {len(mal)} descartado(s), de una sola vez."
             + (f" {ya_resueltos} ya los había resuelto otra persona." if ya_resueltos > 0 else ""),
             # Largo: después viene el análisis del lote, que tarda más que los 4 s de siempre,
             # y el aviso se iba antes de que la pantalla terminara de dibujarse.
             duration="long")


def tipo_de_alarma(alarma):
    """El MOTIVO de una alarma sin el dato de cada par, para agrupar en la pantalla de revisión.

    Se agrupaba por el texto entero, y el texto trae el detalle: «se diferencian 25 veces» y
    «se diferencian 40 veces» eran dos motivos, igual que cada código ambiguo de ILLINOIS y cada
    combinación de «DELANTERA+DERECHA vs TRASERA+IZQUIERDA». Con los datos reales, los 461 de
    BARRIDO daban 93 motivos (48 de un solo vínculo) y los 381 de ILLINOIS, 251.
    El detalle no se pierde: la vista de a uno lo muestra en cada par. Lo que SÍ cambia la
    decisión queda en el motivo y no se junta: los dos rubros de «rubros distintos», las dos
    siglas de «siglas distintas», qué medida es la que no coincide."""
    if not alarma:
        return "Sin alarma puntual"
    if alarma.startswith("💲 Los precios se diferencian"):
        return "💲 Los precios se diferencian 8 veces o más"
    m = re.match(r"📐 NO coinciden: (.*)", alarma)
    if m:
        medidas = [p.split(":")[0].strip() for p in m.group(1).split(";")]
        return "📐 NO coinciden: " + " y ".join(medidas)
    m = re.match(r"⚠️ El código .+? apunta a más de un producto de (.+?) — ", alarma)
    if m:
        return (f"⚠️ Un código que apunta a más de un producto de {m.group(1)} — alguno de los "
                "dos está mal cargado")
    if alarma.startswith("🧯 «") and "no es un código de fábrica" in alarma:
        return "🧯 Lo que se tomó como código de fábrica es un modelo, una medida o un año"
    if alarma.startswith("🚫 Código ") and " parece una " in alarma:
        return "🚫 Uno de los dos códigos parece una medida o una especificación"
    return alarma


def analizar_lote_pendiente(lote, limite=None, desde=0):
    """Ver _analizar_lote_pendiente(). Esto solo abre la memoria del análisis: ver
    recordando_lo_de_cada_producto()."""
    with recordando_lo_de_cada_producto():
        return _analizar_lote_pendiente(lote, limite, desde)


def _analizar_lote_pendiente(lote, limite=None, desde=0):
    """Revisa los vínculos de una importación y marca los sospechosos. Dos alarmas:
      - Las medidas mecánicas cargadas se contradicen (prueba física en contra).
      - Un mismo código de fábrica termina apuntando a dos productos distintos del MISMO
        proveedor: uno de los dos está mal, porque un proveedor no tiene dos piezas
        distintas para el mismo código original.
    Lo que no dispara ninguna alarma se considera limpio."""
    # Se traen también las descripciones: hacen falta para saber si un código que "parece una
    # medida" en realidad es un retén o un o'ring, donde la medida ES el código.
    c.execute("""SELECT ep.producto_a_id AS a, ep.producto_b_id AS b,
                        pa.codigo_raw AS cod_a, ma.nombre AS marca_a, ma.tipo AS tipo_a,
                        pa.descripcion AS desc_a, pa.precio AS precio_a,
                        pb.codigo_raw AS cod_b, mb.nombre AS marca_b, mb.tipo AS tipo_b,
                        pb.descripcion AS desc_b, pb.precio AS precio_b
                 FROM equivalencias_pendientes ep
                 JOIN productos pa ON pa.id = ep.producto_a_id
                 JOIN productos pb ON pb.id = ep.producto_b_id
                 JOIN marcas ma ON ma.id = pa.marca_id
                 JOIN marcas mb ON mb.id = pb.marca_id
                 WHERE ep.lote = ? AND ep.producto_a_id < ep.producto_b_id
                 ORDER BY ep.producto_a_id, ep.producto_b_id
                 LIMIT ? OFFSET ?""", (lote, limite if limite else -1, desde))
    filas = [dict(r) for r in c.fetchall()]

    # Todas las medidas de una sola vez, en vez de dos consultas por par
    medidas = cargar_medidas_de_varios([f["a"] for f in filas] + [f["b"] for f in filas])

    # Detectar códigos de fábrica que apuntan a varios productos del mismo proveedor.
    # Solo se miran las filas donde uno de los dos lados ES de fábrica: entre dos proveedores
    # que un código se repita no significa nada, y la rama else tomaba igual el código B como
    # si fuera de fábrica. El uso de más abajo ya estaba protegido, pero armar el grupo con
    # códigos que no son de fábrica solo puede meter ruido.
    # Se guarda el CÓDIGO del proveedor y no solo su id, porque hace falta para distinguir las
    # variantes de una misma pieza (ver son_variantes_de_la_misma_pieza).
    apuntados = {}
    # LA FILA QUE CREÓ EL NODO DE FÁBRICA. El importador crea el producto OEM copiando la
    # descripción de la fila del proveedor, así que la fila cuya descripción es idéntica a la
    # del nodo es la que lo originó. Sobre la cola real, 2.296 de 2.397 nodos tienen
    # exactamente una; cuando hay cero o varias no se puede decidir y no se usa.
    # Hace falta para saber quién es «el hermano»: el que cita el mismo número pero llegó
    # segundo, y al que por eso no le tocó la señal de la descripción igual.
    candidatos_a_origen = {}
    juegos_y_piezas = {}      # clave -> {True si algún miembro es un juego, False si alguno no}
    for f in filas:
        if "OEM" not in (f["tipo_a"], f["tipo_b"]):
            continue
        oem, otro, marca_otro, cod_otro, desc_oem, desc_otro = (
            (f["cod_a"], f["b"], f["marca_b"], f["cod_b"], f.get("desc_a"), f.get("desc_b"))
            if f["tipo_a"] == "OEM"
            else (f["cod_b"], f["a"], f["marca_a"], f["cod_a"], f.get("desc_b"), f.get("desc_a")))
        clave = (sanitizar(oem), marca_otro)
        apuntados.setdefault(clave, {})[otro] = cod_otro
        juegos_y_piezas.setdefault(clave, set()).add(bool(es_un_kit(desc_otro)))
        if normalizar_texto(desc_oem or "") == normalizar_texto(desc_otro or "") and desc_oem:
            candidatos_a_origen.setdefault(clave, set()).add(cod_otro)
    origen_del_codigo = {k: next(iter(v)) for k, v in candidatos_a_origen.items() if len(v) == 1}

    # EL JUEGO Y LA PIEZA QUE TRAE ADENTRO, cuando comparten el número de fábrica.
    # _uno_trae_al_otro() ya resuelve el caso en que el kit NOMBRA el código de la pieza
    # —«KIT CAB Y BUJ (LEIHTT06SC/LSPKR6E)»—, pero en esta lista eso no pasa nunca: el juego y
    # la junta no se citan entre sí, se encuentran porque los dos llevan el MISMO número
    # original. «Junta Tapa de Cilindros IVECO STRALIS (460S36T)» y «Juego Completo de
    # Reparación IVECO STRALIS (460S36T)» son la junta y el juego que la trae, y el número es
    # de la junta.
    # Cuando en el mismo número conviven un juego y una pieza suelta, el del JUEGO no es una
    # equivalencia: no se puede vender uno en lugar del otro. Va al balde de «relacionadas»,
    # que la pantalla muestra en una línea, en vez de hacerlo decidir de a uno.
    # Medido sobre la cola real: 55 grupos, 79 pares del lado del juego.
    grupos_con_juego_y_pieza = {k for k, v in juegos_y_piezas.items() if v == {True, False}}

    def _variante_del_origen(clave, cod_propio):
        """¿Este producto es la misma pieza que la que originó el número, en otra medida?"""
        origen = origen_del_codigo.get(clave)
        if not origen or sanitizar(origen) == sanitizar(cod_propio):
            return ""     # no hay origen claro, o ESTE es el origen
        base_propia = codigo_base_sin_variante(cod_propio)
        if base_propia and base_propia == codigo_base_sin_variante(origen):
            return (f"Es la misma pieza que «{origen}» —la fila que trajo este número de "
                    "fábrica— en otra medida o material, así que la respalda la misma fila "
                    "de la lista del proveedor")
        return ""

    # La alarma de ambigüedad no le corresponde al hermano que ES una variante del origen:
    # que la junta venga en tres espesores no quiere decir que alguno esté mal cargado.
    # Antes era todo-o-nada sobre el grupo y alcanzaba un miembro raro para marcar a los demás:
    # en «11044BC20A», TC-384-15 / -MG / -11 son la misma junta en tres materiales y TC-801-11
    # es otra pieza, y los cuatro se llevaban el castigo.
    ambiguos = {k for k, v in apuntados.items()
                if len(v) > 1 and not son_variantes_de_la_misma_pieza(v.values())}

    # ¿Este par aparece en más de una lista? Que dos proveedores independientes digan lo mismo
    # es la mejor confirmación que se puede tener sin mirar la pieza.
    #
    # NO SE CALCULA, y no por olvido. Se contaba con COUNT(DISTINCT lote) agrupando por par, pero
    # la cola tiene clave primaria (producto_a_id, producto_b_id): un par está en UNA lista y el
    # número daba 1 siempre. La señal «📋 Lo confirman N listas distintas» (+20) no se disparó
    # nunca, y la consulta costaba 2 s de cada análisis —un IN con los 4.399 productos del
    # barrido, dos veces—.
    # Se midió si valía la pena hacerla andar: sobre la base real, de ~12.700 pares propuestos,
    # 44 los propone más de una fuente, y 30 de esos son barrido + cruce por auto, que
    # evidencia_cruzada() ya cuenta como dos métodos que coinciden. Sumarles +20 sería contar dos
    # veces la misma evidencia. Si algún día entra una SEGUNDA lista de proveedor que se pisa con
    # otra, ahí sí: habría que guardar las fuentes de cada par en una tabla aparte.
    ids = list({f["a"] for f in filas} | {f["b"] for f in filas})
    codigos_con_respaldo = set()
    if ids:
        try:
            # origen <> 'deducida' y esto importa: la señal que alimenta vale +25 y se llama
            # «el catálogo del fabricante respalda este vínculo». Una aplicación DEDUCIDA no
            # sale de ningún catálogo — sale de leerle el auto a la misma descripción que el
            # resto de las señales ya está comparando. Contarla sería contar dos veces la
            # misma evidencia, y encima diciéndole al usuario algo que no es cierto.
            # Sobre la base real son 114.673 aplicaciones deducidas: sin este filtro, cargarlas
            # le sumaba 25 a casi todos los vínculos sin que apareciera un dato nuevo.
            # En tandas: un IN con todos los productos de la lista entra hoy —4.399 variables
            # contra un tope de 32.766— pero no tiene techo, y pasado el tope se cae la
            # pantalla de revisión entera. Ver en_tandas().
            for _tanda, _marcas in en_tandas(ids):
                c.execute(f"""SELECT DISTINCT p.codigo_clean FROM productos p
                              JOIN aplicaciones ap ON ap.codigo_clean = p.codigo_clean
                              WHERE p.id IN ({_marcas})
                                AND COALESCE(ap.origen, '') <> 'deducida'""", _tanda)
                codigos_con_respaldo.update(r["codigo_clean"] for r in c.fetchall())
        except sqlite3.OperationalError as _err:
            anotar_error("analizar_lote_pendiente", _err)
            codigos_con_respaldo = set()

    # Lo que se aprendió de las revisiones anteriores. Se calcula una vez para todo el lote.
    # Y el conteo de palabras del catálogo, por lo mismo: adentro del bucle son 400 recorridas
    # completas de la tabla de productos.
    _cuenta_pal, _total_desc = cuantas_veces_aparece_cada_palabra()
    patrones_aprendidos = aprender_de_las_decisiones()
    escalas_precio = escalas_de_precio()
    _ya_juzgados = {}   # código -> ¿las reglas de hoy ya no lo tomarían? (ver más abajo)
    ventas_confirman = pares_confirmados_por_ventas()

    limpias, sospechosas, relacionadas = [], [], []
    for f in filas:
        alarmas = []
        # ¿Los códigos parecen códigos? Esto caza las importaciones mal mapeadas, donde la
        # columna que se tomó como código en realidad tenía medidas o descripciones.
        for lado, etiqueta in (("a", "Código A"), ("b", "Código B")):
            malo, motivo = codigo_sospechoso(f[f"cod_{lado}"], f.get(f"desc_{lado}", ""))
            if malo:
                alarmas.append(f"🚫 {etiqueta}: {motivo}")
        coinciden, detalle = comparar_medidas(medidas.get(f["a"]), medidas.get(f["b"]))
        if coinciden is False:
            alarmas.append(f"📐 {detalle}")
        # Este control vale SOLO cuando uno de los dos lados es un código de FÁBRICA. Ahí sí,
        # que el mismo código de fábrica apunte a dos productos del mismo proveedor significa
        # que alguno está mal cargado: el fabricante tiene una pieza por número.
        # Entre DOS PROVEEDORES no significa nada, y era lo que estaba pasando: una bobina de
        # un proveedor cubre tres códigos del otro porque el otro la numera por aplicación
        # (una para el Audi A3, otra para el A4, otra para el A6). Eso es normal en el rubro,
        # no un error de carga. Sin esta condición el par se llevaba -35 y terminaba en
        # revisión manual: 125 de 179 sugerencias marcadas, y la alarma era casi siempre esta.
        # El error estaba en el else: cuando ninguno de los dos era OEM, igual tomaba el código
        # B y lo trataba como si lo fuera.
        _variante = ""
        if "OEM" in (f["tipo_a"], f["tipo_b"]):
            oem, marca_otro, _cod_propio = (
                (f["cod_a"], f["marca_b"], f["cod_b"]) if f["tipo_a"] == "OEM"
                else (f["cod_b"], f["marca_a"], f["cod_a"]))
            _clave = (sanitizar(oem), marca_otro)
            _variante = _variante_del_origen(_clave, _cod_propio)
            # Al hermano que es una variante del origen no le corresponde la alarma: que la
            # junta venga en tres espesores no quiere decir que alguno esté mal cargado.
            if _clave in ambiguos and not _variante:
                alarmas.append(f"⚠️ El código {oem} apunta a más de un producto de "
                                f"{marca_otro} — alguno de los dos está mal cargado")
        # ¿Es un kit y la pieza que trae adentro? Entonces no se pregunta: no es una
        # equivalencia y ya lo sabemos. Se aparta y la pantalla lo dice en una línea, en vez de
        # mezclarlo con los que sí hay que decidir. Los nuevos ya no entran a la cola
        # (ver pares_de_kit_y_pieza), esto es para los que están de antes.
        _kit_de = _uno_trae_al_otro(f.get("desc_a"), f.get("cod_a"),
                                     f.get("desc_b"), f.get("cod_b"),
                                     f.get("tipo_a"), f.get("tipo_b"))
        if not _kit_de and "OEM" in (f["tipo_a"], f["tipo_b"]):
            # El juego que comparte número de fábrica con una pieza suelta del mismo proveedor.
            _oem_jp, _marca_jp, _desc_jp = (
                (f["cod_a"], f["marca_b"], f.get("desc_b")) if f["tipo_a"] == "OEM"
                else (f["cod_b"], f["marca_a"], f.get("desc_a")))
            if ((sanitizar(_oem_jp), _marca_jp) in grupos_con_juego_y_pieza
                    and es_un_kit(_desc_jp)):
                _kit_de = (f"es un juego que trae adentro la pieza con el número {_oem_jp}, "
                           "no un reemplazo de ella")
        if _kit_de:
            f["relacion"] = _kit_de
            relacionadas.append(f)
            continue
        # Puntaje de confianza: junta toda la evidencia en un número, para poder ordenar por
        # lo peor primero en vez de mirar cientos de alarmas planas.
        # (_ya_juzgados cachea la respuesta por código: en una tanda de 3.185 pares los mismos
        # códigos se repiten, y preguntar dos veces lo mismo es tiempo tirado.)
        puntaje, senales = evaluar_equivalencia(
            f.get("desc_a", ""), f.get("desc_b", ""),
            medidas.get(f["a"]), medidas.get(f["b"]),
            f.get("precio_a"), f.get("precio_b"),
            respaldo_fabricante=(sanitizar(f["cod_a"]) in codigos_con_respaldo
                                  or sanitizar(f["cod_b"]) in codigos_con_respaldo),
            marca_a=f.get("marca_a", ""), marca_b=f.get("marca_b", ""),
            patrones=patrones_aprendidos,
            vendido_como_reemplazo=ventas_confirman.get((min(f["a"], f["b"]),
                                                          max(f["a"], f["b"])), 0),
            escalas=escalas_precio,
            variante_del_origen=_variante,
            # Solo se consulta cuando uno de los dos DICE que es un kit, que es una prueba de
            # texto y cuesta nada. Sin esa guarda serían 1.000 LIKE sobre las 70.888
            # descripciones por cada tanda que se revisa.
            trae_al_otro="",   # ya se apartó arriba
        )
        for tipo, texto in senales:
            if tipo == "mal" and texto not in alarmas:
                alarmas.append(texto)

        # Las alarmas estructurales (el código no parece un código, un OEM que apunta a dos
        # productos) descuentan fuerte: son problemas de carga, no matices.
        puntaje -= 35 * len([a for a in alarmas if a.startswith(("🚫", "⚠️"))])

        # EL CÓDIGO DE FÁBRICA QUE LAS REGLAS DE HOY YA NO TOMARÍAN. Esto tapa un agujero que
        # abrió la señal de «misma descripción»: el producto OEM se crea copiando la descripción
        # de la fila, así que un modelo de camión metido en la columna de OEM da descripción
        # idéntica y llegaba a 100 de confianza. Medido sobre la cola real: 15 pares con
        # «BENZ1722», «240E42», «BENZ332-6» y compañía entraban en el botón de aprobar en bloque.
        # No alcanza con que la descripción coincida: si el código no es un código, el vínculo no
        # sirve para nada aunque las dos filas digan lo mismo.
        #
        # SOLO EL LADO DEL CÓDIGO DE FÁBRICA, y esto es lo que importa: la pregunta que hace
        # codigo_que_hoy_no_se_tomaria() es «¿el extractor sacaría esto de un texto?», y eso
        # vale para un OEM —que se adivinó de una descripción— pero NO para el código propio de
        # un proveedor, que vino de su columna. La primera versión preguntaba por los dos lados
        # y el resultado se ve de una: sobre los 24.774 vínculos cargados vetaba 12.508 contra
        # los 681 correctos. Los 11.827 de más eran pares perfectos —«10082FISPA» con
        # «8200488774A», misma descripción y todo— que quedaban marcados como basura porque
        # «10082FISPA» sin la marca es «10082», y un número de cinco cifras suelto no se
        # adivinaría de un texto. Nunca se adivinó: estaba en la columna del código.
        for _lado, _tipo in (("cod_a", "tipo_a"), ("cod_b", "tipo_b")):
            if f.get(_tipo) != "OEM":
                continue
            _cod = f.get(_lado) or ""
            if _cod and _cod not in _ya_juzgados:
                _ya_juzgados[_cod] = codigo_que_hoy_no_se_tomaria(_cod)
            if _cod and _ya_juzgados.get(_cod):
                puntaje = min(puntaje, 15.0)
                _aviso = (f"🧯 «{_cod}» no es un código de fábrica: es un modelo, una medida o "
                          "un año. Las reglas de hoy ya no lo tomarían. Borralo en Mantenimiento "
                          "→ 🧹 Limpiar y corregir → «Puentes que hoy ya no se generarían»")
                if _aviso not in alarmas:
                    alarmas.append(_aviso)
                break

        # Y el que se levantó del texto del medio en vez de la lista de referencias del final.
        # Es más blando a propósito: saca el vínculo del botón de aprobar en bloque y lo manda
        # a «conviene una mirada», sin darlo por perdido. Ver
        # el_codigo_no_figura_entre_las_referencias().
        for _lado, _tipo, _otra_desc in (("cod_a", "tipo_a", "desc_b"),
                                          ("cod_b", "tipo_b", "desc_a")):
            if f.get(_tipo) != "OEM":
                continue
            _cod_ref = f.get(_lado) or ""
            if _cod_ref and el_codigo_no_figura_entre_las_referencias(_cod_ref,
                                                                      f.get(_otra_desc) or ""):
                puntaje = min(puntaje, PUNTAJE_QUE_NO_LLEGA_A_APROBAR_SOLO)
                _av_ref = (f"🔎 «{_cod_ref}» no aparece entre los números de fábrica que la "
                           "descripción lista al final: parece sacado del texto del medio, "
                           "donde van los motores. Miralo antes de aprobarlo")
                if _av_ref not in alarmas:
                    alarmas.append(_av_ref)
                break

        # Y el cruce de métodos, que es lo que más precisión da: que dos caminos
        # independientes lleguen al mismo par es mucho más fuerte que uno solo. Un VETO —las
        # medidas se contradicen, los rubros no son el mismo— tumba el par sin importar
        # cuántos digan que sí.
        try:
            a_favor, vetos, veredicto = evidencia_cruzada(
                f["a"], f["b"], cuenta_palabras=_cuenta_pal, total_descripciones=_total_desc)
        except Exception as _err:
            anotar_error("analizar_lote_pendiente", _err)
            a_favor, vetos, veredicto = [], [], ""
        if vetos:
            puntaje = min(puntaje, 15.0)
            # El precio y los rubros los miran las dos: las señales de arriba y
            # evidencia_cruzada(), cada una con su redacción («Los precios se diferencian 19
            # veces» y «los precios se diferencian 19 veces»). Comparando el texto exacto
            # pasaban las dos, y 150 de los 12.668 vínculos de la base real mostraban la misma
            # alarma dos veces seguidas. Esas dos se reconocen por el emoji; las demás no, porque
            # otro 📐 o otro 🚫 sí puede decir algo distinto.
            _ya_dichas = {a.split()[0] for a in alarmas if a.startswith(("💲", "🧩"))}
            for v in vetos:
                if v not in alarmas and v.split()[0] not in _ya_dichas:
                    alarmas.append(v)
        elif len(a_favor) >= 3:
            puntaje = max(puntaje, 90.0)
        elif len(a_favor) == 2:
            puntaje = max(puntaje, 72.0)
        f["evidencia"] = a_favor
        f["veredicto"] = veredicto

        puntaje = max(0.0, min(100.0, puntaje))

        f["alarmas"] = alarmas
        f["confianza"] = puntaje
        f["senales"] = senales
        # El corte lo decide el PUNTAJE, no si hay alguna alarma. Antes bastaba una alarma
        # menor para mandar a revisión un vínculo con toda la evidencia a favor, y así se
        # juntaban cientos de casos que no hacía falta mirar mezclados con los que sí.
        (limpias if puntaje >= 55 else sospechosas).append(f)

    # Lo más dudoso primero: si hay que revisar 400, que los peores estén arriba
    sospechosas.sort(key=lambda x: x["confianza"])
    limpias.sort(key=lambda x: -x["confianza"])
    return limpias, sospechosas, relacionadas


def productos_que_mas_ensucian(lote, limite=15):
    """Qué productos son la causa de más vínculos pendientes marcados como problemáticos.

    Nace de un caso real: un producto con código «1S» generaba decenas de pendientes, todos con
    la misma alarma («es demasiado corto para ser un código»), y había que resolverlos de a uno.
    Cuando el problema es UN producto, corresponde resolverlo una vez y no cincuenta."""
    c.execute("""SELECT p.id AS "_id", p.codigo_raw AS "Código", m.nombre AS "Marca",
                        p.descripcion AS "Descripción",
                        COUNT(*) AS "Pendientes que genera"
                 FROM equivalencias_pendientes ep
                 JOIN productos p ON p.id IN (ep.producto_a_id, ep.producto_b_id)
                 JOIN marcas m ON m.id = p.marca_id
                 WHERE ep.lote = ?
                 GROUP BY p.id
                 HAVING COUNT(*) >= 3
                 ORDER BY COUNT(*) DESC LIMIT ?""", (lote, limite))
    filas = filas_a_listas(c)
    # Solo interesan los que además tienen un código dudoso: un producto legítimo con muchas
    # equivalencias no es un problema, es un repuesto que sirve para muchos autos.
    salida, ya = [], set()
    for f in filas:
        malo, motivo = codigo_sospechoso(f["Código"], f.get("Descripción") or "")
        if malo:
            f["Problema"] = motivo
            salida.append(f)
            ya.add(f["_id"])

    # EL OTRO CULPABLE, y el que aparece de verdad: un código de FÁBRICA que apunta a varios
    # productos DEL MISMO PROVEEDOR. Un código de fábrica identifica una pieza; si señala a
    # ocho del mismo catálogo, o no es un código o la lista lo cita en piezas que no lo llevan.
    # codigo_sospechoso() no los agarra porque tienen forma perfecta de código: en la lista de
    # Illinois los peores son 'MAXIONS4' (el motor Maxion S4), 'MB616.912' (el OM 616 de
    # Mercedes), 'OHL355' y 'BENZ813913' — todos nombres de motor o de camión.
    # Con la lista de Illinois son 20 códigos que generan 87 pendientes: resolverlos de a uno
    # es mirar 87 veces lo mismo. Antes esta pantalla no aparecía nunca porque la única
    # condición era codigo_sospechoso(), que sobre esa lista da cero.
    c.execute("""SELECT po.id AS "_id", po.codigo_raw AS "Código", mo.nombre AS "Marca",
                        po.descripcion AS "Descripción",
                        COUNT(DISTINCT p.id) AS "Pendientes que genera",
                        mp.nombre AS "_prov"
                 FROM equivalencias_pendientes ep
                 JOIN productos po ON po.id IN (ep.producto_a_id, ep.producto_b_id)
                 JOIN marcas mo ON mo.id = po.marca_id
                 JOIN productos p ON p.id IN (ep.producto_a_id, ep.producto_b_id) AND p.id <> po.id
                 JOIN marcas mp ON mp.id = p.marca_id
                 WHERE ep.lote = ? AND mo.tipo = 'OEM' AND mp.tipo <> 'OEM'
                 GROUP BY po.id, mp.id
                 HAVING COUNT(DISTINCT p.id) >= 3
                 ORDER BY COUNT(DISTINCT p.id) DESC LIMIT ?""", (lote, limite))
    for f in filas_a_listas(c):
        if f["_id"] in ya:
            continue
        prov = f.pop("_prov", "")
        f["Problema"] = (f"apunta a {f['Pendientes que genera']} productos de {prov} — "
                         "un código de fábrica identifica UNA pieza")
        salida.append(f)
        ya.add(f["_id"])
    salida.sort(key=lambda x: -x["Pendientes que genera"])
    return salida[:limite]


def rechazar_pendientes_de_producto(producto_id, lote=None):
    """Descarta de una todos los pendientes que involucran a un producto. Devuelve cuántos."""
    with db_lock:
        if lote:
            c.execute("""SELECT producto_a_id, producto_b_id FROM equivalencias_pendientes
                         WHERE lote = ? AND (producto_a_id = ? OR producto_b_id = ?)""",
                      (lote, producto_id, producto_id))
        else:
            c.execute("""SELECT producto_a_id, producto_b_id FROM equivalencias_pendientes
                         WHERE producto_a_id = ? OR producto_b_id = ?""",
                      (producto_id, producto_id))
        pares = [(r["producto_a_id"], r["producto_b_id"]) for r in c.fetchall()]
        if lote:
            c.execute("""DELETE FROM equivalencias_pendientes
                         WHERE lote = ? AND (producto_a_id = ? OR producto_b_id = ?)""",
                      (lote, producto_id, producto_id))
        else:
            c.execute("""DELETE FROM equivalencias_pendientes
                         WHERE producto_a_id = ? OR producto_b_id = ?""",
                      (producto_id, producto_id))
        borrados = c.rowcount
        conn.commit()
    if pares:
        # Quedan registrados como rechazados para que una reimportación no los reviva
        marcar_revision(pares, "rechazada")
    return borrados


_BORRAR_PENDIENTE_EN_LOS_DOS_SENTIDOS = """DELETE FROM equivalencias_pendientes
    WHERE (producto_a_id = ? AND producto_b_id = ?) OR (producto_a_id = ? AND producto_b_id = ?)"""


def _los_que_siguen_pendientes(pares):
    """De esos pares, los que TODAVÍA están en la cola, como (menor, mayor). El que llama tiene
    el candado tomado.

    Con varias personas revisando a la vez, la pantalla de uno puede tener pares que otro ya
    resolvió. Aprobar sin mirar volvía a crear una equivalencia que otro acababa de descartar
    —y descartar anotaba como rechazada una que otro acababa de aprobar, que después la
    auditoría marcaba como «evidencia en contra»—. Y con las decisiones por tandas es más
    probable: se juntan durante minutos antes de aplicarse. Se decide solo sobre lo que sigue
    esperando; lo demás ya lo decidió alguien."""
    normalizados = sorted({(min(a, b), max(a, b)) for a, b in pares if a != b})
    siguen = set()
    # Cuatro variables por par (las dos direcciones): 200 pares son 800, abajo del tope de 900.
    for i in range(0, len(normalizados), 200):
        tanda = normalizados[i:i + 200]
        c.execute(
            "SELECT producto_a_id, producto_b_id FROM equivalencias_pendientes WHERE "
            + " OR ".join(["(producto_a_id = ? AND producto_b_id = ?) OR "
                           "(producto_a_id = ? AND producto_b_id = ?)"] * len(tanda)),
            [v for a, b in tanda for v in (a, b, b, a)])
        siguen.update((min(r[0], r[1]), max(r[0], r[1])) for r in c.fetchall())
    return [par for par in normalizados if par in siguen]


def aprobar_pendientes(lote, solo_estos_pares=None):
    """Pasa los vínculos pendientes a equivalencias reales."""
    # Todo o nada: se crean las equivalencias y se borran los pendientes. Cortado en el medio,
    # o quedan los dos (el pendiente vuelve a aparecer ya aprobado) o ninguno (se perdieron).
    with db_lock, transaccion():
        if solo_estos_pares is None:
            c.execute("SELECT producto_a_id, producto_b_id FROM equivalencias_pendientes WHERE lote = ?", (lote,))
            pares = [(r["producto_a_id"], r["producto_b_id"]) for r in c.fetchall()]
        else:
            pares = _los_que_siguen_pendientes(solo_estos_pares)
        if not pares:
            return 0
        # El lote viaja con el vínculo: es lo que después permite deshacer toda una lista.
        # Y el par va siempre ordenado (menor primero), para no dejar la misma equivalencia
        # guardada dos veces en direcciones opuestas.
        c.executemany(
            "INSERT OR IGNORE INTO equivalencias (producto_a_id, producto_b_id, created_at, lote) "
            "VALUES (?, ?, datetime('now'), ?)",
            [(min(a, b), max(a, b), lote) for a, b in pares if a != b]
        )
        # Las dos direcciones, por lo mismo que en borrar_equivalencias_dudosas(): la cola ya
        # guarda una sola fila por par, pero una base de antes puede tener la vuelta, y la
        # pantalla no siempre la manda.
        c.executemany(_BORRAR_PENDIENTE_EN_LOS_DOS_SENTIDOS, [(a, b, b, a) for a, b in pares])
    # Queda registrado que ya se revisó, así la auditoría de lo existente no lo vuelve a marcar
    marcar_revision(pares, "ok")
    return len(pares)


def rechazar_pendientes(lote, solo_estos_pares=None):
    with db_lock:
        if solo_estos_pares is None:
            # Hay que leer los pares ANTES de borrarlos, si no queda sin registrar el rechazo
            c.execute("SELECT producto_a_id, producto_b_id FROM equivalencias_pendientes WHERE lote = ?", (lote,))
            marcar_para_recordar = [(r["producto_a_id"], r["producto_b_id"]) for r in c.fetchall()]
            c.execute("DELETE FROM equivalencias_pendientes WHERE lote = ?", (lote,))
            borrados = c.rowcount
        else:
            pares = _los_que_siguen_pendientes(solo_estos_pares)
            # Las dos direcciones, y se cuenta lo que se BORRÓ. Antes se devolvía len(pares), y
            # la pantalla manda casi siempre ida y vuelta: decía el doble. Y el botón de «kit y
            # pieza» mandaba solo la ida, así que la vuelta se quedaba en la cola.
            c.executemany(_BORRAR_PENDIENTE_EN_LOS_DOS_SENTIDOS, [(a, b, b, a) for a, b in pares])
            borrados = max(c.rowcount, 0)
            marcar_para_recordar = pares
        conn.commit()
    # Se recuerda el rechazo para que no vuelva a aparecer si se reimporta la misma lista
    marcar_revision(marcar_para_recordar, "rechazada")
    return borrados


def descartar_candidata(codigo_clean, producto_id):
    with db_lock:
        c.execute("INSERT OR REPLACE INTO equivalencias_descartadas "
                   "(codigo_clean, producto_id, descartado_por) VALUES (?, ?, ?)",
                   (codigo_clean, producto_id, obtener_usuario_actual()))
        conn.commit()


def _guardar_equivalencia_una_vez(a, b, verificada, nivel, nota):
    """Carga (o actualiza) una equivalencia como UNA fila (menor, mayor).

    Si ya existía anotada al revés, esa fila se va: si no, el par quedaría espejado, que es
    justo lo que esto viene a evitar. El que llama tiene el candado tomado."""
    a, b = min(a, b), max(a, b)
    c.execute("DELETE FROM equivalencias WHERE producto_a_id = ? AND producto_b_id = ?", (b, a))
    c.execute("INSERT OR REPLACE INTO equivalencias "
              "(producto_a_id, producto_b_id, created_at, verificada, nivel, nota) "
              "VALUES (?, ?, datetime('now'), ?, ?, ?)",
              (a, b, verificada, nivel, nota))


def confirmar_candidata(codigo_clean, producto_id, codigo_original, marca_para_nuevo=None):
    """Convierte una sugerencia en una equivalencia real. Si el código que pedía el cliente
    todavía no existe como producto (caso típico: un código de fábrica que no tenés cargado),
    lo crea con la marca elegida y recién ahí los vincula."""
    # Todo o nada: puede crear un producto nuevo, vincularlo y sacar el descarte. Cortado en el
    # medio deja un producto inventado sin ningún vínculo, que después aparece en las búsquedas.
    with db_lock, transaccion():
        c.execute("SELECT id FROM productos WHERE codigo_clean = ? LIMIT 1", (codigo_clean,))
        fila = c.fetchone()
        if fila:
            id_pedido = fila["id"]
        else:
            if not marca_para_nuevo:
                return False, "Elegí con qué marca cargar el código que pedía el cliente."
            marca_id = get_or_create_marca(marca_para_nuevo)
            c.execute("SELECT descripcion FROM productos WHERE id = ?", (producto_id,))
            desc = (c.fetchone() or {"descripcion": ""})["descripcion"] or ""
            id_pedido = get_or_create_producto(codigo_original.strip(), codigo_clean, desc, marca_id)

        if id_pedido == producto_id:
            return False, "Los dos códigos son el mismo producto."

        # UNA fila, (menor, mayor). Guardaba las dos direcciones a propósito, y era uno de los
        # dos lugares de donde salían las «equivalencias anotadas dos veces» que después hay
        # que unificar con una herramienta aparte. La búsqueda mira las dos columnas: con una
        # fila alcanza. Ver _guardar_equivalencia_una_vez().
        _guardar_equivalencia_una_vez(id_pedido, producto_id, 1, "Exacta",
                                      "Descubierta desde las ventas del mostrador")
        c.execute("DELETE FROM equivalencias_descartadas WHERE codigo_clean = ? AND producto_id = ?",
                   (codigo_clean, producto_id))
    return True, None


def busquedas_fallidas_que_ahora_estan(marca_id=None):
    """Lo que se buscó sin resultado y HOY sí está cargado. Devuelve una lista, lo más pedido
    primero.

    «Códigos buscados sin resultado» era un registro muerto: decía qué te pidieron y no tenías,
    pero no si ya lo tenés. Y lo normal es que sí —entra con la lista siguiente del proveedor—, y
    que nadie se entere: el cliente que lo pidió tres veces ya no vuelve a preguntar.

    Se compara con el código LIMPIO contra codigo_clean y contra el código de barras, que es lo
    mismo que mira la búsqueda al arrancar (ver buscar_por_codigo()), así que «está» quiere
    decir «buscándolo hoy, aparece». Con `marca_id` se mira solo esa marca: es lo que usa el
    informe de una importación para decir qué trajo ESA lista.

    En tandas, porque la cantidad de términos distintos no tiene techo."""
    try:
        c.execute("""SELECT termino, COUNT(*) AS veces, MAX(fecha) AS ultima
                     FROM historial_busquedas WHERE sin_resultado = 1 GROUP BY termino""")
        fallidas = filas_a_listas(c)
    except sqlite3.OperationalError as _err:
        anotar_error("busquedas_fallidas_que_ahora_estan", _err)
        return []
    # Varias formas de escribir lo mismo («06A 905 115», «06A905115») son UN pedido.
    por_codigo = {}
    for f in fallidas:
        limpio = sanitizar(f["termino"])
        if not limpio:
            continue
        d = por_codigo.setdefault(limpio, {"Buscado": f["termino"], "Veces": 0, "Última vez": ""})
        d["Veces"] += f["veces"]
        d["Última vez"] = max(d["Última vez"], f["ultima"] or "")
    if not por_codigo:
        return []
    encontrados = {}
    filtro_marca = "AND p.marca_id = ?" if marca_id else ""
    for tanda, marcas in en_tandas(list(por_codigo), usos_por_consulta=2):
        params = tanda + tanda + ([marca_id] if marca_id else [])
        c.execute(f"""SELECT p.codigo_clean, p.codigo_barras, p.codigo_raw, m.nombre AS marca
                      FROM productos p JOIN marcas m ON m.id = p.marca_id
                      WHERE (p.codigo_clean IN ({marcas}) OR p.codigo_barras IN ({marcas}))
                      {filtro_marca}""", params)
        for r in c.fetchall():
            for clave in (r["codigo_clean"], r["codigo_barras"]):
                if clave in por_codigo:
                    encontrados.setdefault(clave, []).append(f"{r['codigo_raw']} ({r['marca']})")
    salida = []
    for limpio, dato in por_codigo.items():
        if limpio in encontrados:
            salida.append({**dato, "Ahora está como": ", ".join(sorted(set(encontrados[limpio]))[:3])})
    # Lo más pedido primero y, a igual cantidad, lo más reciente.
    salida.sort(key=lambda x: x["Última vez"], reverse=True)
    salida.sort(key=lambda x: -x["Veces"])
    return salida


def listar_busquedas_sin_resultado(limite=50):
    c.execute("""SELECT termino AS "Buscado", COUNT(*) AS "Veces", MAX(fecha) AS "Última vez"
                 FROM historial_busquedas WHERE sin_resultado = 1
                 GROUP BY termino ORDER BY COUNT(*) DESC, MAX(fecha) DESC LIMIT ?""", (limite,))
    return filas_a_listas(c)

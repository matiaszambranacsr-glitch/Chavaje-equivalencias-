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
    # Que coincidan SOLO en algo que distingue variantes no prueba que sea la misma pieza.
    # El espesor separa las tres juntas de un mismo motor, pero dos juntas de motores
    # distintos pueden medir 1,10 las dos: así salía la de una S10 «confirmada» contra la de
    # un Corsa, con «las medidas coinciden (espesor)» como una de sus dos evidencias. Lo mismo
    # la posición o la cantidad de vías: si no coinciden, son otra pieza; si coinciden, no
    # dicen cuál. Hace falta al menos una medida que identifique —un diámetro, un largo—.
    if all(etiqueta in _MEDIDAS_QUE_SOLO_DISTINGUEN for etiqueta in comparadas):
        return None, ("Solo coinciden en " + ", ".join(comparadas)
                      + ": no alcanza para decir que es la misma pieza.")
    return True, "Coinciden en " + ", ".join(comparadas)


# Ver el final de comparar_medidas(). Son las etiquetas con que se anotan en «comparadas».
_MEDIDAS_QUE_SOLO_DISTINGUEN = {"espesor", "posición", "vías de la ficha"}


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


def marcar_revision(pares, decision, motivo=None):
    """Recuerda la decisión tomada sobre un vínculo, en los dos sentidos. 'ok' = ya lo miré y
    está bien (no volver a marcarlo en la auditoría). 'rechazada' = no es equivalente (además
    de borrarlo, no se vuelve a crear aunque se reimporte la lista del proveedor).
    'motivo' es una clave de MOTIVOS_DE_RECHAZO, cuando la persona dijo por qué."""
    if not pares:
        return
    filas = []
    usuario = obtener_usuario_actual()
    como_estaba = _como_estaba_en_la_revision()
    for a, b in pares:
        confianza, senal = como_estaba.get((min(a, b), max(a, b)), (None, None))
        filas.append((a, b, decision, usuario, motivo, confianza, senal))
        filas.append((b, a, decision, usuario, motivo, confianza, senal))
    with db_lock:
        c.executemany(
            "INSERT OR REPLACE INTO equivalencias_revisadas "
            "(producto_a_id, producto_b_id, decision, revisado_por, motivo, confianza, senal) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            filas
        )
        conn.commit()


def _techo_de_error(malos, total):
    """Hasta cuánto puede estar mal el grupo del que salió la muestra, con 95 % de seguridad
    (Wilson). Con 0 mal en 30, «hasta 11 %»: la muestra no dice «0 %»."""
    import math
    if not total:
        return None
    z = 1.96
    p = malos / total
    centro = (p + z * z / (2 * total)) / (1 + z * z / total)
    margen = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return min(1.0, centro + margen)


def aciertos_de_la_revision():
    """Qué tan bien acierta la app, medido con TUS decisiones. Tres tablas:

    · muestras: de los «limpios» que revisaste en las muestras de control, cuántos estaban mal,
      por franja de confianza. Es la medida honesta: son pares sorteados al azar y mirados.
    · por_banda: lo que decidiste, según la confianza que tenía el par en ese momento. Incluye
      lo aprobado en bloque, que no se miró de a uno: el verde sale mejor de lo que es.
    · por_alarma: de lo que cada alarma mandó a revisión, cuánto aprobaste igual. Una alarma que
      se equivoca seguido es una regla para ajustar.

    La confianza y la alarma se anotan al decidir desde que existe esto (ver marcar_revision()):
    las decisiones de antes cuentan en las muestras pero no en las otras dos."""
    salida = {"muestras": [], "por_banda": [], "por_alarma": [], "con_datos": 0}
    c.execute("""SELECT m.grupo, r.decision FROM muestras_de_control m
                 JOIN equivalencias_revisadas r
                   ON r.producto_a_id = m.producto_a_id AND r.producto_b_id = m.producto_b_id""")
    muestras = {}
    for fila in c.fetchall():
        partes = (fila["grupo"] or "").split("|")
        franja = next((x for x in partes[3:] if x in ("alta", "media")), "")
        tipo = "automático" if "(automático)" in partes[0] or partes[0].startswith(
            ("BARRIDO", "CRUCE", "CÓDIGO ESCRITO")) else "lista importada"
        clave = (tipo, {"alta": "confianza alta", "media": "confianza media"}.get(franja, "todas"))
        cuenta = muestras.setdefault(clave, [0, 0])
        cuenta[0] += 1
        cuenta[1] += fila["decision"] == "rechazada"
    for (tipo, franja), (total, malos) in sorted(muestras.items()):
        techo = _techo_de_error(malos, total)
        salida["muestras"].append({
            "De dónde": tipo, "Franja": franja, "Mirados": total, "Mal": malos,
            "Mal en la muestra": f"{100 * malos / total:.0f} %",
            "Mal en el grupo (hasta)": f"{100 * techo:.0f} %"})

    c.execute("""SELECT confianza, senal, decision FROM equivalencias_revisadas
                 WHERE confianza IS NOT NULL AND producto_a_id < producto_b_id""")
    filas = c.fetchall()
    salida["con_datos"] = len(filas)
    bandas, alarmas = {}, {}
    for f in filas:
        nombre, _que_hacer = nivel_de_confianza(f["confianza"])
        cuenta = bandas.setdefault(nombre, [0, 0])
        cuenta[0 if f["decision"] == "ok" else 1] += 1
        if f["confianza"] < 55 and f["senal"]:
            # Sin los números, para juntar «emparejado con 4» y «con 9» en una sola alarma.
            clave = re.sub(r"\d[\d.,]*", "N", f["senal"])[:90]
            cuenta = alarmas.setdefault(clave, [0, 0])
            cuenta[0 if f["decision"] == "ok" else 1] += 1
    orden = {"🟢": 0, "🟡": 1, "🟠": 2, "🔴": 3}
    for nombre, (ok, mal) in sorted(bandas.items(), key=lambda x: orden.get(x[0][:1], 9)):
        salida["por_banda"].append({"Confianza": nombre, "Aprobaste": ok, "Descartaste": mal,
                                    "Aprobados": f"{100 * ok / (ok + mal):.0f} %"})
    for alarma, (ok, mal) in sorted(alarmas.items(), key=lambda x: -(x[1][0] + x[1][1]))[:15]:
        salida["por_alarma"].append({"Alarma": alarma, "Decididos": ok + mal,
                                     "Aprobaste igual": ok,
                                     "La alarma se equivocó": f"{100 * ok / (ok + mal):.0f} %"})
    return salida


def _como_estaba_en_la_revision():
    """{(a, b): (confianza, primera alarma)} del análisis que tiene la pantalla de revisión.
    Vacío si no hay: lo que se decide fuera de la revisión (cortar un vínculo cargado) queda sin
    esos datos, y el panel de aciertos no lo cuenta."""
    guardado = analisis_de_lote_guardado() or {}
    salida = {}
    for lista in guardado.get("resultado") or ():
        for f in lista or ():
            if isinstance(f, dict) and "a" in f and "b" in f:
                alarmas = f.get("alarmas") or []
                salida[(min(f["a"], f["b"]), max(f["a"], f["b"]))] = (
                    f.get("confianza"), alarmas[0][:200] if alarmas else None)
    return salida


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


# Cuántos vínculos cargados mira la auditoría de una vez. Era 20.000 y la base ya tiene más
# (21.204 en el celular, 32.960 en la de prueba): quedaba corta siempre, y lo que no miraba era
# siempre lo mismo —lo último cargado—. Los 32.960 tardan 1,3 s.
VINCULOS_QUE_MIRA_LA_AUDITORIA = 150000


def auditar_equivalencias_existentes(limite=VINCULOS_QUE_MIRA_LA_AUDITORIA):
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

    # Cuántos vínculos tiene cada producto: sirve para detectar productos basura.
    # Se cuentan APARTE los que van a un código original. Un burro de arranque que lista los
    # 30 números de Bosch a los que reemplaza no está mal cargado: es una pieza con muchos
    # originales, y así vienen en las listas. Contándolos, la pantalla ponía primero a los
    # productos más completos del catálogo como «basura para revisar». Lo raro es estar
    # pegado a muchos productos de OTRAS MARCAS de repuesto: eso sí suele ser una importación
    # mal mapeada.
    vinculos_por_producto = {}
    for f in filas:
        for lado, otro in (("a", "b"), ("b", "a")):
            pid = f[lado]
            info = vinculos_por_producto.setdefault(pid, {
                "id": pid, "codigo": f[f"cod_{lado}"], "descripcion": f[f"desc_{lado}"],
                "marca": f[f"marca_{lado}"], "tipo": f[f"tipo_{lado}"], "total": 0,
                "cantidad": 0, "cantidad_oem": 0,
            })
            info["total"] += 1
            if f[f"tipo_{otro}"] == "OEM":
                info["cantidad_oem"] += 1
            else:
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
            "vinculos_totales": vinculos_por_producto.get(pid, {}).get("total", 0),
        }

    conflictos = []
    parecidos = 0
    with recordando_lo_de_cada_producto():
        for clave, g in grupos.items():
            pendientes = [p for p in g["productos"].values() if not p["revisado_ok"]]
            if len(g["productos"]) > 1 and pendientes:
                # Que el mismo original apunte a dos productos de la misma lista NO alcanza
                # para decir que uno está mal: la lista de FISPA trae piezas FISPA y LUCAS, y
                # «40027FISPA» y «LEMSM022LUCAS» con el mismo original son equivalentes de
                # verdad. Eran 2.179 de los 2.466 «conflictos». Ahora sale solo si los
                # productos se contradicen (ver _por_que_chocan()).
                motivo = _por_que_chocan(list(g["productos"].values()))
                if not motivo:
                    parecidos += 1
                    continue
                g["motivo"] = motivo
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
                    "vinculos": vinculos_por_producto.get(pid, {}).get("total", 0),
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

    # Productos con muchos vínculos: candidatos a basura. Pero MUCHOS NO ALCANZA. Una sonda
    # lambda que va en 60 autos y cita 7 originales tiene, lógicamente, 15 equivalentes de otras
    # marcas, y la pantalla la ponía primera como «basura para revisar» al lado de la verdadera:
    # JL · CHAPA pegada a 75 cables de autos distintos. Lo que distingue a la basura no es la
    # cantidad sino que sus vínculos NO SON LA MISMA PIEZA. Ver vinculos_que_no_cuadran().
    candidatos = {pid for pid, v in vinculos_por_producto.items()
                  if v["cantidad"] >= MINIMO_DE_VINCULOS_PARA_REVISAR and v["tipo"] != "OEM"}
    vecinos, originales = {}, {}
    for f in filas:
        for lado, otro in (("a", "b"), ("b", "a")):
            # Los originales de TODOS, no solo de los candidatos: hace falta saber si el de
            # enfrente cita el mismo.
            if f[f"tipo_{otro}"] == "OEM" and f[f"tipo_{lado}"] != "OEM":
                originales.setdefault(f[lado], set()).add(f[otro])
            if f[lado] not in candidatos or f[f"tipo_{otro}"] == "OEM":
                continue
            vecinos.setdefault(f[lado], []).append({
                "id": f[otro], "codigo": f[f"cod_{otro}"], "marca": f[f"marca_{otro}"],
                "descripcion": f[f"desc_{otro}"] or "", "par": (f["a"], f["b"]),
                "ok": (f["a"], f["b"]) in ya_ok})
    sospechosos = []
    with recordando_lo_de_cada_producto():
        for pid in candidatos:
            info = vinculos_por_producto[pid]
            malos, rubros = vinculos_que_no_cuadran(info, vecinos.get(pid, []), originales)
            evaluados = info["cantidad"]
            if (len(malos) >= MINIMO_DE_VINCULOS_QUE_NO_CUADRAN
                    and len(malos) >= evaluados * PROPORCION_QUE_NO_CUADRA):
                sospechosos.append(dict(info, no_cuadran=malos, rubros=rubros))
    sospechosos.sort(key=lambda v: (-len(v["no_cuadran"]), -v["cantidad"]))

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
        "originales_con_parecidos": parecidos,
        "por_medidas": por_medidas,
        "codigos_malos": sorted(codigos_malos.values(), key=lambda x: -x["vinculos"])[:50],
        "productos_sospechosos": sospechosos[:30],
    }


# Ver auditar_equivalencias_existentes() y vinculos_que_no_cuadran().
MINIMO_DE_VINCULOS_PARA_REVISAR = 10
MINIMO_DE_VINCULOS_QUE_NO_CUADRAN = 5
PROPORCION_QUE_NO_CUADRA = 0.4

# Los motivos de firmas_compatibles() que dicen que son piezas DISTINTAS, no solo que no hay
# pruebas de que sean la misma: los mismos que tumban un par en la revisión (ver
# _MOTIVOS_QUE_CONTRADICEN en descripciones.py, que se carga después), más el rubro. «Solo
# comparten 1 palabra» o «piezas distintas: SONDA y SENSOR» no son contradicciones: son dos
# formas de escribir, y marcarlos llenaba la lista de sondas buenas.
_MOTIVOS_DE_OTRA_PIEZA = ("rubros distintos", "posiciones distintas", "siglas distintas",
                          "autos distintos", "marcas distintas", "modelos distintos",
                          "cilindradas distintas", "distinta cantidad de vías", "juegos distintos",
                          "largo de cable distinto", "temperaturas distintas",
                          "carburadores distintos", "piezas de lugares distintos",
                          "sensores de tipos distintos", "bujías de tipos distintos",
                          "distinta cantidad de cilindros", "motores de distintas válvulas",
                          "años distintos", "motores distintos",
                          "sobremedida distinta", "presiones distintas",
                          "combustibles distintos", "aros de distinto color", "medidas distintas",
                          "versiones distintas")


def _por_que_chocan(productos):
    """Por qué los productos a los que apunta un mismo original no pueden ser todos la misma
    pieza, o None si pueden. Ver auditar_equivalencias_existentes().

    Chocan si dos de ellos se contradicen (otro rubro, otros autos, otra posición… ver
    _MOTIVOS_DE_OTRA_PIEZA), si uno es un juego y otro una pieza suelta, o si alguno no tiene
    descripción: ese es el que suele haber quedado de una importación mal mapeada."""
    if any(not (p["descripcion"] or "").strip() for p in productos):
        return "uno no tiene descripción"
    firmas = [(p, firma_de_producto(p["descripcion"], p["id"])) for p in productos]
    kits = {bool(es_un_kit(p["descripcion"])) for p in productos}
    if len(kits) > 1:
        return "mezcla un juego con una pieza suelta"
    for i in range(len(firmas)):
        for j in range(i + 1, len(firmas)):
            (pa, fa), (pb, fb) = firmas[i], firmas[j]
            if not fa or not fb:
                continue
            ok, motivo = firmas_compatibles(fa, fb)
            if not ok and motivo.startswith(_MOTIVOS_DE_OTRA_PIEZA):
                return motivo
    return None


def vinculos_que_no_cuadran(info, vecinos, originales):
    """Los vínculos de un producto que no son la misma pieza: [(vecino, motivo)], y los rubros.

    Un vínculo NO cuadra si la descripción de los dos se contradice: rubros distintos, autos
    que no tienen nada en común, posición, cilindrada, tipo de sensor… (ver
    _MOTIVOS_DE_OTRA_PIEZA). Y cuadra seguro, diga lo que diga la descripción, si los dos
    citan el MISMO código original: eso es la prueba más fuerte que hay.
    Los que ya marcaste como correctos no cuentan."""
    firma = firma_de_producto(info["descripcion"] or "", info["id"])
    if firma and firma["familia"] == "Sin clasificar":
        firma = None
    propios = originales.get(info["id"], set())
    firmas = {}
    rubros = collections.Counter()
    for v in vecinos:
        firma_v = firma_de_producto(v["descripcion"], v["id"])
        firmas[v["id"]] = firma_v if firma_v and firma_v["familia"] != "Sin clasificar" else None
        if firmas[v["id"]]:
            rubros[firma_v["familia"]] += 1
    # Sin descripción que se entienda (un código «1» que quedó de una columna equivocada), la
    # referencia es el rubro de la mayoría de sus vínculos: si están pegados a filtros, bombas
    # y cables a la vez, no es ninguna pieza.
    dominante = rubros.most_common(1)[0][0] if rubros else None
    malos = []
    for v in vecinos:
        if v["ok"] or (propios & originales.get(v["id"], set())):
            continue
        firma_v = firmas[v["id"]]
        if not firma_v:
            continue
        if firma:
            ok, motivo = firmas_compatibles(firma, firma_v)
            if not ok and motivo.startswith(_MOTIVOS_DE_OTRA_PIEZA):
                malos.append((v, motivo))
        elif dominante and firma_v["familia"] != dominante:
            malos.append((v, f"rubros distintos: {firma_v['familia']}, y la mayoría de sus "
                             f"vínculos son {dominante}"))
    return malos, rubros


def cb_auditoria_eliminar(par_a, par_b):
    """Borra el vínculo Y vuelve a calcular la auditoría. Sin esto último el panel seguía
    mostrando el resultado viejo (guardado desde que se tocó 'Auditar'), y parecía que el
    botón no hacía nada aunque el vínculo sí se hubiera borrado."""
    eliminar_equivalencia(par_a, par_b)
    st.session_state["resultado_auditoria"] = auditar_equivalencias_existentes()


def cb_auditoria_dejar(pares):
    marcar_revision(pares, "ok")
    st.session_state["resultado_auditoria"] = auditar_equivalencias_existentes()


def cb_auditoria_cortar_pares(pares):
    """Corta solo esos vínculos (los que no cuadran) y vuelve a revisar."""
    cortar_vinculos_cargados(pares)
    st.session_state["resultado_auditoria"] = auditar_equivalencias_existentes()


def cb_auditoria_cortar_todos(producto_id):
    cortar_todos_los_vinculos(producto_id)
    st.session_state["resultado_auditoria"] = auditar_equivalencias_existentes()



def cb_reglas_de_hoy(pares, decision):
    """«✂️ Cortar» o «✅ Están bien» sobre un grupo de 🔁 Revisar lo aprobado con las reglas de
    hoy, y vuelve a revisar para que el grupo resuelto desaparezca de la pantalla."""
    if decision == "cortar":
        cortar_vinculos_cargados(pares)
    else:
        marcar_revision(pares, "ok", motivo=MOTIVO_CONFIRMADO_CON_LAS_REGLAS_DE_HOY)
    st.session_state["resultado_reglas_de_hoy"] = aprobados_que_hoy_se_vetarian()
    guardar_resumen_de_lo_aprobado(st.session_state["resultado_reglas_de_hoy"])


def mostrar_revision_de_lo_aprobado():
    """«🔁 Revisar lo aprobado con las reglas de hoy», en Equivalencias sugeridas. Es una
    función porque se dibuja en uno de dos lugares: al final de la pantalla, como siempre, o
    arriba de todo si se tocó el aviso de mostrar_aviso_de_lo_aprobado()."""
    st.markdown("**🔁 Revisar lo aprobado con las reglas de hoy**")
    explicar(
        "Pasa cada vínculo ya cargado por los mismos vetos que usa hoy la revisión.",
        "Cada vez que la app aprende a distinguir algo —modelos distintos, largo de cable, "
        "temperaturas, un código que en realidad es un motor— lo aplica a lo que llega. Lo que "
        "ya habías aprobado antes quedó como estaba, y «🔍 Auditar lo ya cargado» no lo vuelve "
        "a mirar. Esto sí. La tarea de fondo lo revisa sola cuando la app cambia, y avisa "
        "arriba de esta pantalla. Lo que confirmes como correcto no vuelve a aparecer; lo que cortes "
        "queda descartado aunque vuelvas a importar la lista."
    )
    if st.button("🔁 Revisar lo aprobado", key="revisar_lo_aprobado"):
        with st.spinner("Revisando..."):
            st.session_state["resultado_reglas_de_hoy"] = aprobados_que_hoy_se_vetarian()
            guardar_resumen_de_lo_aprobado(st.session_state["resultado_reglas_de_hoy"])
    _rh = st.session_state.get("resultado_reglas_de_hoy")
    if _rh:
        _n_vetados = sum(len(filas) for _m, filas in _rh["grupos"])
        if not _n_vetados:
            st.success(f"✅ Ninguno de los {miles(_rh['revisados'])} vínculos cargados choca con "
                       "las reglas de hoy.")
        else:
            st.warning(
                f"**{miles(_n_vetados)} de {miles(_rh['revisados'])} vínculos cargados hoy se "
                "vetarían.** Van agrupados por motivo: mirá los ejemplos de cada grupo y "
                "resolvelo de un toque.")
        if _rh["confirmados"]:
            st.caption(f"({miles(_rh['confirmados'])} ya confirmados como correctos no se miran.)")
        for _motivo_rh, _filas_rh in _rh["grupos"][:30]:
            with st.container(border=True):
                st.markdown(f"**{texto_para_html(_motivo_rh)}** — {miles(len(_filas_rh))} "
                            "vínculo(s)")
                for _f in _filas_rh[:5]:
                    st.caption(
                        f"{_f['marca_a']} **{_f['cod_a']}** — {(_f['desc_a'] or '')[:70]}  ↔  "
                        f"{_f['marca_b']} **{_f['cod_b']}** — {(_f['desc_b'] or '')[:70]}"
                        + (f"  \n_{_f['vetos'][0]}_" if _f["vetos"][0] != _motivo_rh else ""))
                if len(_filas_rh) > 5:
                    st.caption(f"… y {miles(len(_filas_rh) - 5)} más.")
                _pares_rh = [(_f["a"], _f["b"]) for _f in _filas_rh]
                _k_rh = abs(hash(_motivo_rh))
                _c1_rh, _c2_rh = st.columns(2)
                _c1_rh.button(f"✂️ Cortar los {miles(len(_filas_rh))}", key=f"rh_cortar_{_k_rh}",
                              on_click=cb_reglas_de_hoy, args=(_pares_rh, "cortar"),
                              help="Los productos quedan; solo se corta la relación, y no "
                                   "vuelve aunque reimportes la lista")
                _c2_rh.button("✅ Están bien", key=f"rh_ok_{_k_rh}",
                              on_click=cb_reglas_de_hoy, args=(_pares_rh, "ok"),
                              help="No vuelven a aparecer acá")
        if len(_rh["grupos"]) > 30:
            st.caption(f"(mostrando 30 de {len(_rh['grupos'])} motivos)")


def cb_ver_lo_aprobado_arriba(ver):
    """El botón del aviso: revisa ahora (para ver cuáles son) y lo muestra arriba de todo."""
    if ver:
        st.session_state["resultado_reglas_de_hoy"] = aprobados_que_hoy_se_vetarian()
        guardar_resumen_de_lo_aprobado(st.session_state["resultado_reglas_de_hoy"])
    st.session_state["reglas_de_hoy_arriba"] = ver


def mostrar_aviso_de_lo_aprobado():
    """Arriba de Equivalencias sugeridas: cuántos vínculos YA CARGADOS chocan con las reglas de
    hoy, según lo último que revisó la tarea de fondo (ver revisar_lo_aprobado_por_atras()).
    No revisa nada al dibujarse: con 60 proveedores son más de 100.000 vínculos."""
    if st.session_state.get("reglas_de_hoy_arriba"):
        with st.container(border=True):
            mostrar_revision_de_lo_aprobado()
            st.button("Listo, cerrar", key="reglas_de_hoy_cerrar",
                      on_click=cb_ver_lo_aprobado_arriba, args=(False,))
        return
    resumen = resumen_de_lo_aprobado()
    if not resumen or not resumen.get("vetados"):
        return
    motivos = " · ".join(f"{texto_para_html(m)} ({miles(n)})" for m, n in resumen["grupos"])
    try:
        cuando = datetime.strptime(resumen["fecha"], "%Y-%m-%d %H:%M").strftime("%d/%m %H:%M")
    except (KeyError, ValueError):
        cuando = resumen.get("fecha", "")
    st.warning(
        f"🔁 **{miles(resumen['vetados'])} vínculo(s) que ya están cargados chocan con las "
        f"reglas de hoy.** El buscador los muestra como equivalentes. Lo que más hay: "
        f"{motivos}. (Revisado el {cuando}.)")
    st.button("🔁 Ver cuáles y resolverlos", key="reglas_de_hoy_ver",
              on_click=cb_ver_lo_aprobado_arriba, args=(True,))


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


# Lo que la persona confirmó en «🔁 Revisar lo aprobado con las reglas de hoy»: un 'ok' con
# este motivo no vuelve a aparecer ahí. Un 'ok' común —el de aprobar la cola— sí: se aprobó con
# las reglas de ese día, y es justo lo que hay que volver a mirar.
MOTIVO_CONFIRMADO_CON_LAS_REGLAS_DE_HOY = "confirmado"


def aprobados_que_hoy_se_vetarian(limite=None):
    """Los vínculos YA CARGADOS que el análisis de hoy vetaría, agrupados por el motivo.

    Cada regla nueva —modelos distintos, largo de cable, temperaturas, tapa trasera contra tapa
    de válvulas— se aplica a la cola que viene. Lo que se aprobó antes de que existiera quedó
    cargado, y la auditoría de siempre no lo vuelve a mirar: salta todo lo marcado 'ok', y
    aprobar la cola marca 'ok' justamente a todo lo aprobado. Así, cada mejora del análisis
    arreglaba el futuro y dejaba el pasado como estaba.

    Acá cada vínculo cargado pasa por evidencia_cruzada(), la misma que usa la cola, y se
    devuelven los que tienen algún veto. No se mira lo que la persona confirmó acá mismo (ver
    MOTIVO_CONFIRMADO_CON_LAS_REGLAS_DE_HOY).

    Devuelve {"revisados", "confirmados", "grupos": [(motivo, [filas])]}, de los grupos más
    grandes a los más chicos."""
    c.execute("""SELECT producto_a_id, producto_b_id FROM equivalencias_revisadas
                 WHERE decision = 'ok' AND motivo = ?""",
              (MOTIVO_CONFIRMADO_CON_LAS_REGLAS_DE_HOY,))
    confirmados = {(r[0], r[1]) for r in c.fetchall()}
    c.execute("""SELECT DISTINCT MIN(e.producto_a_id, e.producto_b_id) AS a,
                        MAX(e.producto_a_id, e.producto_b_id) AS b
                 FROM equivalencias e WHERE e.producto_a_id != e.producto_b_id
                 ORDER BY 1, 2 LIMIT ?""", (limite if limite else -1,))
    pares = [(r["a"], r["b"]) for r in c.fetchall() if (r["a"], r["b"]) not in confirmados]
    grupos = {}
    with recordando_lo_de_cada_producto():
        ids = sorted({x for par in pares for x in par})
        precargar_para_evidencia(ids, cargar_medidas_de_varios(ids))
        memoria = getattr(_MEMORIA_DEL_ANALISIS, "datos", None) or {}
        cuenta_pal, total_desc = cuantas_veces_aparece_cada_palabra()
        rubros_oem = rubros_de_los_codigos_de_fabrica()
        ya_juzgados = {}
        for n_par, (a, b) in enumerate(pares):
            if n_par % 500 == 0:
                ceder_al_mostrador()      # solo hace algo en la tarea de fondo
            pa, pb = memoria.get(("producto_ev", a)) or {}, memoria.get(("producto_ev", b)) or {}
            try:
                _a_favor, vetos, _veredicto = evidencia_cruzada(
                    a, b, cuenta_palabras=cuenta_pal, total_descripciones=total_desc,
                    rubros_oem=rubros_oem)
            except Exception as _err:
                anotar_error("aprobados_que_hoy_se_vetarian", _err)
                continue
            # El código de fábrica que hoy no se tomaría, como en la cola: solo del lado OEM,
            # que se adivinó de una descripción (ver _analizar_lote_pendiente()).
            for p in (pa, pb):
                cod = p.get("codigo_raw") or ""
                if p.get("tipo") != "OEM" or not cod:
                    continue
                if cod not in ya_juzgados:
                    ya_juzgados[cod] = codigo_que_hoy_no_se_tomaria(cod)
                if ya_juzgados[cod]:
                    vetos = [f"🧯 «{cod}» no es un código de fábrica: es un modelo, una medida "
                             "o un año. Las reglas de hoy ya no lo tomarían"] + list(vetos)
                    break
            if not vetos:
                continue
            grupos.setdefault(tipo_de_alarma(vetos[0]), []).append({
                "a": a, "b": b, "vetos": vetos,
                "marca_a": pa.get("marca"), "cod_a": pa.get("codigo_raw"),
                "desc_a": pa.get("descripcion"),
                "marca_b": pb.get("marca"), "cod_b": pb.get("codigo_raw"),
                "desc_b": pb.get("descripcion")})
    return {"revisados": len(pares), "confirmados": len(confirmados) // 2,
            "grupos": sorted(grupos.items(), key=lambda g: (-len(g[1]), g[0]))}


# Si lo único que cambió son los vínculos (se aprobó o se cortó algo), la tarea de fondo vuelve
# a revisar lo aprobado como mucho cada tantos minutos. Con otro código de la app, enseguida.
MINUTOS_ENTRE_REVISIONES_DE_LO_APROBADO = 30


def _huella_de_la_logica():
    """Cambia con cada versión de la lógica de la app: es lo que dice «las reglas cambiaron»."""
    import orden
    huella = hashlib.sha1()
    for parte in orden.PARTES_DE_LA_LOGICA:
        with open(os.path.join(orden.AQUI, "logica", parte), "rb") as archivo:
            huella.update(archivo.read())
    return huella.hexdigest()


def guardar_resumen_de_lo_aprobado(resultado):
    """Deja anotado lo que dio aprobados_que_hoy_se_vetarian(), para avisarlo sin rehacerlo."""
    c.execute("SELECT COUNT(*) FROM equivalencias")
    guardar_config("reglas_de_hoy_resumen", json.dumps({
        "codigo": _huella_de_la_logica(),
        "vinculos": c.fetchone()[0],
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "revisados": resultado["revisados"],
        "vetados": sum(len(filas) for _m, filas in resultado["grupos"]),
        "grupos": [[motivo, len(filas)] for motivo, filas in resultado["grupos"][:3]],
    }, ensure_ascii=False))


def resumen_de_lo_aprobado():
    """Lo último que dio revisar lo aprobado con las reglas de hoy, o None si no se hizo nunca."""
    try:
        return json.loads(obtener_config("reglas_de_hoy_resumen", "") or "null")
    except ValueError:
        return None


def revisar_lo_aprobado_por_atras():
    """Para la tarea de fondo: revisa lo aprobado con las reglas de hoy si la app cambió o si
    cambiaron los vínculos cargados, y lo deja anotado. Devuelve el resumen si lo rehízo.

    «🔁 Revisar lo aprobado» existía, pero había que apretarlo, y está al final de la pantalla.
    Sobre la base de prueba, lo aprobado en bloque antes de las reglas de rubros, medidas y
    códigos que son motores dejó 78 vínculos malos cargados —una junta de tapa unida a una
    bujía, poleas de otro diámetro— que el buscador mostraba como equivalentes. Ahora lo avisa
    la pantalla de sugeridas apenas se sabe."""
    guardado = resumen_de_lo_aprobado() or {}
    c.execute("SELECT COUNT(*) FROM equivalencias")
    vinculos = c.fetchone()[0]
    if guardado.get("codigo") == _huella_de_la_logica():
        if guardado.get("vinculos") == vinculos:
            return None
        try:
            hace = datetime.now() - datetime.strptime(guardado["fecha"], "%Y-%m-%d %H:%M")
        except (KeyError, ValueError):
            hace = timedelta(days=1)
        if hace < timedelta(minutes=MINUTOS_ENTRE_REVISIONES_DE_LO_APROBADO):
            return None
    ceder_al_mostrador()
    resultado = aprobados_que_hoy_se_vetarian()
    guardar_resumen_de_lo_aprobado(resultado)
    return resumen_de_lo_aprobado()


def cortar_vinculos_cargados(pares):
    """Corta esos vínculos en los dos sentidos, de una, y los recuerda como rechazados para
    que no vuelvan con la próxima importación. Devuelve cuántos se cortaron."""
    pares = [tuple(p) for p in pares]
    if not pares:
        return 0
    with transaccion():
        for a, b in pares:
            c.execute("DELETE FROM equivalencias WHERE (producto_a_id = ? AND producto_b_id = ?) "
                      "OR (producto_a_id = ? AND producto_b_id = ?)", (a, b, b, a))
    marcar_revision(pares, "rechazada")
    return len(pares)


def pares_ya_cargados():
    """Los pares que ya son equivalencia cargada, como (menor, mayor). Ver
    guardar_equivalencias_pendientes()."""
    c.execute("""SELECT MIN(producto_a_id, producto_b_id) AS a,
                        MAX(producto_a_id, producto_b_id) AS b FROM equivalencias""")
    return {(r["a"], r["b"]) for r in c.fetchall()}


def pares_ya_pendientes():
    """Los pares que ya esperan revisión, como (menor, mayor). Ver pares_ya_cargados()."""
    c.execute("""SELECT MIN(producto_a_id, producto_b_id) AS a,
                        MAX(producto_a_id, producto_b_id) AS b FROM equivalencias_pendientes""")
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





# Una lista con menos de esto va al final, aunque sea la más nueva: ver resumen_lotes_pendientes().
PARES_DE_UNA_LISTA_CHICA = 20


def resumen_lotes_pendientes():
    """Las listas esperando revisión, la primera es la que la pantalla abre.

    La más nueva primero, como antes, PERO las chicas al final. Las tareas automáticas del día
    arman listas de uno o dos pares («POR REEMPLAZO (automático)»), y como son siempre las más
    nuevas, la pantalla abría todos los días en una lista de un par mientras la importación de
    13.941 esperaba abajo en el selector."""
    c.execute("""SELECT lote, origen, COUNT(*) AS cantidad, MIN(fecha) AS fecha
                 FROM equivalencias_pendientes GROUP BY lote, origen ORDER BY MIN(fecha) DESC""")
    filas = [dict(r) for r in c.fetchall()]
    return sorted(filas, key=lambda f: f["cantidad"] < PARES_DE_UNA_LISTA_CHICA)


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
    """La escala de precios de cada lista, para poder comparar precios entre listas.

    Devuelve {marca: escala}, con la forma de siempre: escala_a / escala_b es cuánto más cara
    suele ser la lista A que la B PARA LA MISMA PIEZA. Va con caché porque evidencia_cruzada()
    la consulta una vez por par; los cinco minutos alcanzan, la escala de una lista solo cambia
    cuando se importa una lista nueva.

    Hace falta porque dos listas pueden estar en escalas completamente distintas: una
    desactualizada, otra sin IVA, otra en otra unidad. Sin corregir por eso, cualquier
    comparación de precios entre esas dos listas dice siempre lo mismo y no informa nada.

    SE MIDE SOBRE LOS PARES, NO SOBRE LA LISTA ENTERA. Antes la escala era la mediana de todos
    los precios de cada lista, y eso mezcla dos cosas: cuánto cobra la lista y QUÉ vende. Una
    lista de herramientas y juntas no tiene la misma mediana que una de sensores aunque cobren
    igual. Medido sobre la base real, con los pares que las unen:
        FISPA / JL        la misma pieza cuesta 1,06 veces   — las medianas decían 8,6
        IMPERIAL / JL                               0,71 veces — decían 5,3
        ILLINOIS / IMPERIAL                         2,3 veces  — decían 0,72
    O sea que cada par FISPA–JL con el MISMO precio salía «se diferencian 1 vez, y lo normal es
    9»: 262 pares mandados a revisión por tener el precio parecido.

    Cómo: por cada par de listas con al menos 20 pares vinculados (aprobados o pendientes,
    directos o a través del mismo código de fábrica) se toma la mediana de la razón de precios;
    y de todas esas razones se saca UNA escala por lista, la que mejor las explica a todas
    juntas (mínimos cuadrados sobre el logaritmo, pesado por cantidad de pares). La mediana
    aguanta los pares malos que haya en la cola. Una lista que no tiene pares suficientes con
    ninguna otra queda con la escala de antes, la mediana de sus precios, puesta en la misma
    unidad que las demás."""
    import math
    from collections import defaultdict
    try:
        c.execute("""SELECT m.nombre AS marca, p.precio AS precio
                     FROM productos p JOIN marcas m ON m.id = p.marca_id
                     WHERE p.precio IS NOT NULL AND p.precio > 0 AND m.tipo <> 'OEM'
                     ORDER BY m.nombre, p.precio""")
        por_marca = defaultdict(list)
        for fila in c.fetchall():
            por_marca[fila["marca"]].append(fila["precio"])
        razones = defaultdict(list)       # (marca_a, marca_b) con a < b -> log(precio_a / precio_b)

        def _anotar(ma, pa, mb, pb):
            if ma == mb or not pa or not pb or pa <= 0 or pb <= 0:
                return
            if ma > mb:
                ma, mb, pa, pb = mb, ma, pb, pa
            razones[(ma, mb)].append(math.log(pa / pb))

        for tabla in ("equivalencias", "equivalencias_pendientes"):
            c.execute(f"""SELECT ma.nombre, a.precio, mb.nombre, b.precio FROM {tabla} e
                          JOIN productos a ON a.id = e.producto_a_id
                          JOIN marcas ma ON ma.id = a.marca_id AND ma.tipo <> 'OEM'
                          JOIN productos b ON b.id = e.producto_b_id
                          JOIN marcas mb ON mb.id = b.marca_id AND mb.tipo <> 'OEM'""")
            for fila in c.fetchall():
                _anotar(*fila)
        # A través del mismo código de fábrica, que es como están casi todos los vínculos
        # aprobados: proveedor ↔ código ↔ otro proveedor. Con tope, por si un código puente
        # cuelga cientos de productos y multiplica los pares.
        c.execute("""WITH v AS (
                         -- SIN_CONTAR_EL_ESPEJO: el UNION sin ALL ya junta la fila anotada de
                         -- ida con la de vuelta, así que cada vecino del código cuenta una vez.
                         SELECT e.producto_a_id AS oem, e.producto_b_id AS otro FROM equivalencias e
                         UNION SELECT e.producto_b_id, e.producto_a_id FROM equivalencias e)
                     SELECT ma.nombre, a.precio, mb.nombre, b.precio
                     FROM v v1 JOIN v v2 ON v2.oem = v1.oem AND v2.otro > v1.otro
                     JOIN productos o ON o.id = v1.oem
                     JOIN marcas mo ON mo.id = o.marca_id AND mo.tipo = 'OEM'
                     JOIN productos a ON a.id = v1.otro
                     JOIN marcas ma ON ma.id = a.marca_id AND ma.tipo <> 'OEM'
                     JOIN productos b ON b.id = v2.otro
                     JOIN marcas mb ON mb.id = b.marca_id AND mb.tipo <> 'OEM'
                     LIMIT 200000""")
        for fila in c.fetchall():
            _anotar(*fila)
    except sqlite3.OperationalError as _err:
        anotar_error("escalas_de_precio", _err)
        return {}

    # Menos de 20 precios no alcanza para hablar de la escala de una lista.
    medianas = {marca: math.log(precios[len(precios) // 2])
                for marca, precios in por_marca.items() if len(precios) >= 20}
    aristas = {}
    for (ma, mb), lista in razones.items():
        if len(lista) >= 20 and ma in medianas and mb in medianas:
            lista.sort()
            aristas[(ma, mb)] = (lista[len(lista) // 2], len(lista))
    vecinos = defaultdict(list)
    for (ma, mb), (d, n) in aristas.items():
        vecinos[ma].append((mb, d, n))       # s_a - s_b = d
        vecinos[mb].append((ma, -d, n))
    escala = {}
    pendientes = set(vecinos)
    while pendientes:
        # Cada grupo de listas unidas entre sí se resuelve aparte.
        grupo, frontera = set(), [next(iter(pendientes))]
        while frontera:
            m = frontera.pop()
            if m in grupo:
                continue
            grupo.add(m)
            frontera.extend(o for o, _, _ in vecinos[m] if o not in grupo)
        pendientes -= grupo
        s = {m: medianas[m] for m in grupo}
        for _ in range(300):
            for m in grupo:
                total = sum(n for _, _, n in vecinos[m])
                s[m] = sum((s[o] + d) * n for o, d, n in vecinos[m]) / total
        # En la misma unidad que las demás: que en promedio coincida con las medianas.
        corrimiento = sum(medianas[m] - s[m] for m in grupo) / len(grupo)
        for m in grupo:
            escala[m] = s[m] + corrimiento
    for marca, log_mediana in medianas.items():
        escala.setdefault(marca, log_mediana)
    return {marca: math.exp(v) for marca, v in escala.items()}


def comparar_precios(precio_a, marca_a, precio_b, marca_b, escalas):
    """(cuántas veces se diferencian, cuántas veces es lo típico entre esas dos listas,
    cuánto se aparta ESTE par de lo típico). Las tres son 1 o más.

    La dirección importa, y antes no se miraba: si la lista A suele ser 10 veces más cara que
    la B y en este par A sale 10 veces MÁS BARATA, el par se aparta 100 veces de lo normal, no
    cero. Comparando solo «cuántas veces» sin mirar cuál es la cara, pasaba como normal."""
    razon = max(precio_a, precio_b) / min(precio_a, precio_b)
    ea, eb = (escalas or {}).get(marca_a) or 0, (escalas or {}).get(marca_b) or 0
    tipica = ea / eb if ea > 0 and eb > 0 else 1.0
    desvio = (precio_a / precio_b) / tipica
    if desvio < 1:
        desvio = 1 / desvio
    return razon, max(tipica, 1 / tipica), desvio


# Una descripción tiene que tener algo adentro para que «son iguales» signifique algo. Con
# «JUNTA» o «FILTRO» sueltos coinciden piezas que no tienen nada que ver. Medido sobre las
# 70.888 descripciones reales: la mediana son 59 caracteres y solo 1.264 de 70.888 tienen 20 o
# menos, así que el piso deja afuera las de una palabra suelta y nada más.
LARGO_DESCRIPCION_QUE_CONVENCE = 20


def texto_de_precios_que_no_cierran(razon, esperada):
    """La alarma del precio, dicha como se entiende. Decía «los precios se diferencian 1
    veces, y entre estos dos proveedores lo normal es 9», que es correcto y no se entiende: que
    cuesten LO MISMO entre dos listas donde uno suele salir 9 veces más es lo raro — un juego
    completo de motor al precio de una junta suelta."""
    if esperada > 2 and razon < esperada:
        detalle = ("cuestan casi lo mismo" if razon < 1.5
                   else f"uno cuesta {razon:.0f} veces el otro")
        return (f"💲 Los precios no cierran: {detalle}, y entre estos dos proveedores lo normal "
                f"es que uno salga {esperada:.0f} veces más. Puede ser más (o menos) pieza")
    return (f"💲 Los precios no cierran: uno cuesta {razon:.0f} veces el otro"
            + (f", y entre estos dos proveedores lo normal es {esperada:.0f}"
               if esperada > 2 else ""))


def evaluar_equivalencia(desc_a, desc_b, medidas_a=None, medidas_b=None,
                         precio_a=None, precio_b=None, veces_confirmada=1,
                         respaldo_fabricante=False, marca_a="", marca_b="", patrones=None,
                         vendido_como_reemplazo=0, codigo_puente=None,
                         productos_del_puente=0, escalas=None, trae_al_otro="",
                         variante_del_origen="", familia_a=None, familia_b=None):
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
    # familia_a / familia_b las pasa quien llama cuando un lado es un código de fábrica: ver
    # rubros_de_los_codigos_de_fabrica().
    fam_a = familia_a or (familia_para_comparar(desc_a) if desc_a else "Sin clasificar")
    fam_b = familia_b or (familia_para_comparar(desc_b) if desc_b else "Sin clasificar")
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
    ajuste_aprendido, senal = senal_aprendida(marca_a, marca_b, patrones)
    if senal:
        puntaje += ajuste_aprendido
        senales.append(senal)
    else:
        ajuste_aprendido = 0

    if precio_a and precio_b and precio_a > 0 and precio_b > 0:
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
        razon, esperada, razon_real = comparar_precios(precio_a, marca_a, precio_b, marca_b,
                                                        escalas)
        if razon_real >= 8:
            puntaje -= 25
            senales.append(("mal", texto_de_precios_que_no_cierran(razon, esperada)))
        elif razon_real <= 2:
            puntaje += 10
            senales.append(("bien", "💲 Los precios son parecidos"
                                    + (" para lo que suele haber entre estas dos listas"
                                       if esperada > 2 else "")))

    return sin_cruzar_la_linea_por_lo_aprendido(puntaje, ajuste_aprendido), senales


# Las líneas que deciden qué se aprueba sin mirar: 55 separa las limpias de las que se revisan,
# y CONFIANZA_ALTA parte los grupos grandes en dos muestras (ver grupos_de_limpias()).
LINEAS_DE_CONFIANZA = (55, 85)


def sin_cruzar_la_linea_por_lo_aprendido(puntaje, ajuste_aprendido):
    """El puntaje final, entre 0 y 100, sin que lo aprendido de las marcas lo suba de franja.

    LO APRENDIDO SUMA, PERO NO ALCANZA SOLO PARA PASAR UNA LÍNEA. «De 30 ILLINOIS↔TARANTO que
    revisaste, aprobaste el 100%» sale de los pares que se revisaron, y los que se revisan son
    sobre todo las limpias —la muestra de control se saca de ellas—: dice que las limpias de
    esas marcas andan bien, no que ande bien cualquier par de esas marcas. Probado sobre la base
    real: marcar bien 20 de la muestra de ILLINOIS ↔ TARANTO subió los 919 de 75 a 90 y metió
    27 sospechosos entre las limpias, que se hubieran aprobado con una muestra que no los
    incluía. Al revés no hay cuidado: si lo aprendido baja un par, que lo baje."""
    final = max(0.0, min(100.0, puntaje))
    if ajuste_aprendido > 0:
        sin_lo_aprendido = max(0.0, min(100.0, puntaje - ajuste_aprendido))
        for linea in LINEAS_DE_CONFIANZA:
            if sin_lo_aprendido < linea <= final:
                final = float(linea - 1)
                break
    return final


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


def motivos_del_lote(lote):
    """{(a, b): (motivo, fila)} de los descartes marcados con un motivo en esa tanda."""
    return st.session_state.setdefault("_motivos_por_lote", {}).setdefault(lote, {})


def anotar_motivo(lote, clave_del_selector, filas):
    """on_change del «¿por qué?» de un descarte: anota (o borra) el motivo de esos pares. Se
    guarda la fila entera porque, después de aplicar, el par ya no está en el análisis y hace
    falta su descripción para buscar los parecidos (ver pares_parecidos())."""
    motivos = motivos_del_lote(lote)
    elegido = st.session_state.get(clave_del_selector)
    clave = next((k for k, v in MOTIVOS_DE_RECHAZO.items() if v == elegido), None)
    for fila in filas:
        if clave:
            motivos[(fila["a"], fila["b"])] = (clave, fila)
        else:
            motivos.pop((fila["a"], fila["b"]), None)


def aplicar_decisiones(lote):
    """Aplica todo lo marcado en el lote, de una vez. Lo que otro ya resolvió mientras tanto se
    saltea solo (ver _los_que_siguen_pendientes()). Los descartes con motivo se guardan con su
    motivo, y quedan anotados para que la pantalla busque los parecidos con el análisis nuevo."""
    decididas = decisiones_del_lote(lote)
    motivos = motivos_del_lote(lote)
    bien = [par for par, que in decididas.items() if que == "bien"]
    mal = [par for par, que in decididas.items() if que == "mal"]
    n_bien = aprobar_pendientes(lote, bien) if bien else 0
    por_motivo = {}
    for par in mal:
        por_motivo.setdefault((motivos.get(par) or (None, None))[0], []).append(par)
    for motivo, pares in por_motivo.items():
        rechazar_pendientes(lote, pares, motivo=motivo)
    para_buscar = [motivos[par] for par in mal if par in motivos]
    if para_buscar:
        st.session_state.setdefault("_buscar_parecidos", {})[lote] = para_buscar
    decididas.clear()
    motivos.clear()
    invalidar_salud()
    ya_resueltos = len(bien) - n_bien
    # Flotante y no avisar(): el botón de abajo deja la pantalla scrolleada abajo, y avisar()
    # escribe arriba de todo, donde en el celular no se ve.
    st.toast(f"✅ Listo: {n_bien} aprobado(s) y {len(mal)} descartado(s), de una sola vez."
             + (f" {ya_resueltos} ya los había resuelto otra persona." if ya_resueltos > 0 else ""),
             # Largo: después viene el análisis del lote, que tarda más que los 4 s de siempre,
             # y el aviso se iba antes de que la pantalla terminara de dibujarse.
             duration="long")


# ============================================================
# APROBAR POR GRUPOS, CON UNA MUESTRA DE CONTROL
# ============================================================
# Las «limpias» son las que el análisis no pudo objetar, y eso no es lo mismo que estar bien:
# nadie sabe cuántas de ellas están mal hasta que alguien las mira. Aprobarlas todas a ciegas
# era la única salida que tenía la pantalla, y la alternativa —mirar 23.000 de a una— no es
# una alternativa. Sobre la base real: 5 equivalencias aprobadas y 23.001 limpias esperando.
#
# Lo que se hace es lo mismo que en cualquier control de calidad: se mira una muestra al azar
# de cada grupo, y de lo que sale se decide el grupo entero. Un grupo son las limpias de un
# mismo PAR DE LISTAS dentro de una tanda, porque los errores se parecen dentro de un par de
# listas y cambian entre uno y otro (TARANTO↔ILLINOIS falla distinto que FISPA↔JL).

TAMANO_DE_LA_MUESTRA = 30

# Ver «el abanico» en _analizar_lote_pendiente().
PRODUCTOS_DISTINTOS_PARA_ABANICO = 3
MEJORES_EMPATADOS_QUE_SE_ACEPTAN = 1


def tamano_de_la_muestra(total):
    """Cuántos mirar según el tamaño del grupo. Con 0 errores en 30 solo se puede prometer
    «menos de 11% mal», que en un grupo de 3.600 son hasta 400 vínculos; con 0 en 80 baja a
    menos de 5%. Mirar 80 para aprobar 3.600 sigue siendo muy buen negocio."""
    if total > 2000:
        return 80
    if total > 500:
        return 50
    return TAMANO_DE_LA_MUESTRA

MOTIVOS_DE_RECHAZO = {
    "otro_auto": "🚗 Es de otro auto o motor",
    "variante": "📐 Otra medida o variante",
    "juego": "📦 Juego contra pieza suelta",
    "otra_pieza": "🔩 Es otra pieza",
    "codigo": "🔢 El código está mal leído",
}


def clave_de_grupo(lote, marca_a, marca_b, franja=""):
    """El nombre con que se guarda la muestra de un grupo: la tanda, el par de listas y, si el
    grupo se partió, la franja de confianza (ver grupos_de_limpias())."""
    ma, mb = sorted((marca_a or "", marca_b or ""))
    return f"{lote}|{ma}|{mb}" + (f"|{franja}" if franja else "")


# Desde qué tamaño un grupo de limpias se parte en dos franjas de confianza, y cuántos pares
# tiene que tener cada franja para que valga la pena su propia muestra.
TAMANO_PARA_PARTIR_EL_GRUPO = 500
MINIMO_POR_FRANJA = 100
CONFIANZA_ALTA = LINEAS_DE_CONFIANZA[1]


def grupos_de_limpias(limpias):
    """[(marca_a, marca_b, filas, franja)], de los grupos más grandes a los más chicos.

    LOS GRUPOS GRANDES SE PARTEN POR CONFIANZA. Las 12.790 limpias de FISPA eran un solo grupo
    con una muestra de 80: 10.222 con 100 —la descripción es la de la fila que trajo el número— y
    1.283 entre 65 y 74, que pasaron con un aviso. En 80 al azar entraban unas 8 de esas: si
    estaban todas mal, la muestra no lo mostraba. Partidas, cada franja tiene su muestra, y la
    de confianza media dice por sí sola cuántas están mal. «franja» es "" si el grupo no se
    partió, o "alta" / "media"."""
    grupos = {}
    for fila in limpias:
        grupos.setdefault(tuple(sorted((fila.get("marca_a") or "", fila.get("marca_b") or ""))),
                          []).append(fila)
    salida = []
    for (ma, mb), filas in grupos.items():
        alta = [f for f in filas if f.get("confianza", 0) >= CONFIANZA_ALTA]
        media = [f for f in filas if f.get("confianza", 0) < CONFIANZA_ALTA]
        if (len(filas) >= TAMANO_PARA_PARTIR_EL_GRUPO
                and len(alta) >= MINIMO_POR_FRANJA and len(media) >= MINIMO_POR_FRANJA):
            salida.extend([(ma, mb, alta, "alta"), (ma, mb, media, "media")])
        else:
            salida.append((ma, mb, filas, ""))
    return sorted(salida, key=lambda g: -len(g[2]))


def muestra_de_control(grupo, pares_del_grupo, ampliar=False):
    """Los pares de la muestra de ese grupo. La primera vez se sortean y se guardan —cuántos,
    según tamano_de_la_muestra()—; después se devuelven los mismos. Con ampliar=True se suman
    TAMANO_DE_LA_MUESTRA más, sorteados entre los que todavía no estaban.

    Un grupo chico se mira entero: sacar 30 de 35 para ahorrar 5 no tiene sentido, y con la
    muestra entera la estimación deja de ser una estimación."""
    import random
    pares_del_grupo = [tuple(p) for p in pares_del_grupo]
    c.execute("SELECT producto_a_id, producto_b_id FROM muestras_de_control WHERE grupo = ?",
              (grupo,))
    ya = [(r[0], r[1]) for r in c.fetchall()]
    al_sortear = pares_al_sortear(grupo)
    guardar_al_sortear = not al_sortear
    if guardar_al_sortear:
        # La primera vez, o una muestra sacada antes de que se guardara esto: lo que hay hoy
        # es lo más parecido a lo que había.
        al_sortear = set(pares_del_grupo) | set(ya)
    # Al ampliar, se sortea entre los que estaban al sortear la primera vez: si no, la muestra
    # ampliada mezcla dos grupos distintos y la estimación no vale para ninguno.
    quedan = [] if ya and not ampliar else sorted((set(pares_del_grupo) & al_sortear) - set(ya))
    if not quedan and not guardar_al_sortear:
        return ya
    cuantos = TAMANO_DE_LA_MUESTRA if ampliar else tamano_de_la_muestra(len(pares_del_grupo))
    if len(quedan) <= cuantos * 1.3:
        nuevos = quedan
    else:
        # Sorteo con semilla: si dos personas abren el mismo grupo a la vez, las dos sortean lo
        # mismo y el INSERT OR IGNORE deja una sola muestra.
        nuevos = random.Random(f"{grupo}|{len(ya)}").sample(quedan, cuantos)
    with transaccion():
        if guardar_al_sortear:
            c.executemany("INSERT OR IGNORE INTO pares_al_sortear_la_muestra (grupo, "
                          "producto_a_id, producto_b_id) VALUES (?, ?, ?)",
                          [(grupo, a, b) for a, b in sorted(al_sortear)])
        c.executemany("INSERT OR IGNORE INTO muestras_de_control (grupo, producto_a_id, "
                      "producto_b_id) VALUES (?, ?, ?)", [(grupo, a, b) for a, b in nuevos])
    c.execute("SELECT producto_a_id, producto_b_id FROM muestras_de_control WHERE grupo = ?",
              (grupo,))
    return [(r[0], r[1]) for r in c.fetchall()]


def pares_al_sortear(grupo):
    """Los pares que tenía el grupo cuando se sorteó su muestra (vacío si no se sorteó)."""
    c.execute("SELECT producto_a_id, producto_b_id FROM pares_al_sortear_la_muestra "
              "WHERE grupo = ?", (grupo,))
    return {(r[0], r[1]) for r in c.fetchall()}


def clave_vigente_de_la_muestra(clave, pares_del_grupo):
    """La clave de la muestra que le toca hoy al grupo.

    Una muestra vale para los pares que había cuando se sorteó (ver pares_al_sortear()). Cuando
    ya no queda ninguno de esos —se aprobaron o se descartaron— y el grupo sigue teniendo pares,
    son pares que entraron después: les toca una muestra nueva, «vuelta 2», «vuelta 3»... Si
    todavía quedan de los de antes, sigue la muestra de antes y los nuevos esperan."""
    pares = {tuple(p) for p in pares_del_grupo}
    vuelta, vigente = 1, clave
    while True:
        al_sortear = pares_al_sortear(vigente)
        if not al_sortear or al_sortear & pares:
            return vigente
        vuelta += 1
        vigente = f"{clave}|vuelta {vuelta}"


def estado_de_la_muestra(pares):
    """{par: 'pendiente' | 'bien' | 'mal'}. Lo decidido se lee de la base, no de la sesión:
    la muestra la puede ir revisando más de una persona, y lo que marcó otra cuenta."""
    estado = {}
    ids = sorted({x for par in pares for x in par})
    pendientes, decisiones = set(), {}
    for tanda, marcadores in en_tandas(ids):
        c.execute(f"""SELECT producto_a_id, producto_b_id FROM equivalencias_pendientes
                      WHERE producto_a_id IN ({marcadores})""", tanda)
        pendientes.update((r[0], r[1]) for r in c.fetchall())
        c.execute(f"""SELECT producto_a_id, producto_b_id, decision FROM equivalencias_revisadas
                      WHERE producto_a_id IN ({marcadores})""", tanda)
        decisiones.update({(r[0], r[1]): r[2] for r in c.fetchall()})
    for a, b in pares:
        if (a, b) in pendientes or (b, a) in pendientes:
            estado[(a, b)] = "pendiente"
        else:
            d = decisiones.get((a, b)) or decisiones.get((b, a))
            estado[(a, b)] = {"ok": "bien", "rechazada": "mal"}.get(d, "pendiente")
    return estado


def estimacion_de_errores(errores, revisados, total):
    """(porcentaje estimado, tope razonable, cuántos del grupo estarían mal según el tope).

    El tope es el límite de arriba del intervalo de Wilson al 95%: con 0 errores en 30 no se
    puede decir «0% de errores», se puede decir «menos de 11%». Es lo que hay que mirar para
    decidir, porque aprobar el grupo es apostar a que el error de verdad no es mayor que eso."""
    import math
    if not revisados:
        return 0.0, 1.0, total
    z = 1.96
    p = errores / revisados
    centro = (p + z * z / (2 * revisados)) / (1 + z * z / revisados)
    margen = (z * math.sqrt(p * (1 - p) / revisados + z * z / (4 * revisados * revisados))
              / (1 + z * z / revisados))
    tope = min(1.0, centro + margen)
    return p, tope, round(tope * total)


# El máximo de error que se acepta para aprobar el resto de un grupo: el tope del intervalo de
# Wilson al 95% (ver estimacion_de_errores()) tiene que quedar en esto o menos. Con 0 errores en
# 30 da 11%, así que alcanza; con 1 en 30 da 17% —en un grupo de 1.000, hasta 170 vínculos
# malos— y hay que mirar 30 más (1 en 60 da 9%). Antes se aprobaba con 0 o 1 error sin importar
# de cuántos, y 1 en 30 pasaba igual que 1 en 80.
TOPE_DE_ERROR_PARA_APROBAR = 0.12


def se_puede_aprobar_el_resto(errores, revisados):
    """¿La muestra alcanza para aprobar el resto del grupo sin mirarlo?"""
    if not revisados:
        return False
    _p, tope, _n = estimacion_de_errores(errores, revisados, 0)
    return tope <= TOPE_DE_ERROR_PARA_APROBAR


def _base_de_la_pieza(codigo):
    """El código sin sus sufijos de variante, hasta que no quede ninguno: de «TC-882-20 1M» y de
    «TC-882-MG 1M» queda «TC-882». Ver codigo_base_sin_variante()."""
    base, anterior = codigo or "", None
    while base and base != anterior:
        anterior = base
        base = codigo_base_sin_variante(base) or base
    return sanitizar(base)


_RE_MEDIDA_EN_TEXTO = re.compile(r'\bESP\b\.?\s*:?\s*[\d.,]+\s*(?:MM)?|\b[\d.,]+\s*MM\b')


def _texto_sin_medidas(texto):
    """La descripción sin el espesor ni las medidas en milímetros, para reconocer variantes:
    «Junta Tapa de Cilindros NISSAN (ESP 1.20MM) ...» y «... (ESP 1.30MM) ...» quedan iguales."""
    limpio = _RE_MEDIDA_EN_TEXTO.sub(" ", normalizar_texto(texto or ""))
    return " ".join(re.sub(r"[()\[\],;]", " ", limpio).split())


# ============================================================
# PARA REVISAR, POR MOTIVO
# ============================================================
# Los motivos que dicen que el par está MAL, no que falta saber: el texto de los dos se
# contradice (otro auto, otro motor, otra pieza), las medidas no dan, el código no es un
# código. Un grupo así se descarta entero; mirar unos ejemplos alcanza para confirmarlo.
# Los demás —«nada dice», el precio, un código que apunta a dos productos— son dudas, y se
# resuelven como las limpias: con una muestra de control.
_MOTIVOS_QUE_SE_DESCARTAN = ("🔤 ", "📐 NO coinciden", "🧯", "🔎", "📦", "🧩",
                             "⚠️ Un número de fábrica que")

# Qué motivo de rechazo corresponde a cada grupo, para guardarlo al descartarlo entero.
_MOTIVO_DE_RECHAZO_DEL_GRUPO = (
    (("🔤 modelos distintos", "🔤 marcas distintas", "🔤 autos distintos",
      "🔤 cilindradas distintas", "🔤 distinta cantidad de cilindros",
      "🔤 motores de distintas válvulas"), "otro_auto"),
    (("📐 NO coinciden", "🔤 distinta cantidad de vías", "🔤 largo de cable distinto",
      "🔤 temperaturas distintas", "🔤 medidas distintas", "🔤 versiones distintas"),
     "variante"),
    (("🔤 juegos distintos",), "juego"),
    (("🔤 piezas de lugares distintos", "🔤 sensores de tipos distintos",
      "🔤 bujías de tipos distintos", "🔤 posiciones distintas", "🔤 siglas distintas",
      "🔤 carburadores distintos", "🔤 aros de distinto color", "🧩"), "otra_pieza"),
    (("🧯", "🔎"), "codigo"),
    (("⚠️ Un número de fábrica que",), "otra_pieza"),
)


def _aviso_codigo_fuera_de_las_referencias(codigo):
    """La alarma 🔎 de un código de fábrica que no está en la lista de números del final."""
    return (f"🔎 «{codigo}» no aparece entre los números de fábrica que la descripción lista al "
            "final: se sacó del texto del medio, donde van los motores y los modelos")


def motivo_para_agrupar(fila):
    """El motivo de un par en revisión, sin el detalle que no cambia la decisión. Parte de
    tipo_de_alarma(), y a las contradicciones del texto les saca lo que viene después de los
    dos puntos: «piezas de lugares distintos: CARTER vs CILINDRO» y «...: CARBURADOR vs
    VALVULA» se deciden igual, y separadas eran veinte grupos chicos."""
    alarmas = fila.get("alarmas") or []
    # La que decide: si alguna es una contradicción del texto, esa, aunque no sea la primera.
    # El precio sale primero porque lo avisa evaluar_equivalencia() antes que los vetos, y 386
    # pares de la cola real con «juego completo contra junta suelta» caían en el grupo del
    # precio —que pide muestra— en vez del de juegos distintos, que se descarta de un toque.
    decisiva = next((a for a in alarmas
                     if tipo_de_alarma(a).startswith(_MOTIVOS_QUE_SE_DESCARTAN)),
                    alarmas[0] if alarmas else "")
    tipo = tipo_de_alarma(decisiva)
    if tipo.startswith(("🔤 ", "🤷 ")):
        tipo = re.split(r"\s*[:(]", tipo, maxsplit=1)[0]
    # «... — alguno de los dos está mal cargado»: la explicación va en la pantalla, no en el
    # nombre del grupo, que tiene que entrar en una línea del celular.
    return tipo.split(" — ")[0]


def grupos_por_motivo(sospechosas):
    """[(motivo, "descartar"|"muestra", filas)]: primero los que se descartan, y dentro de cada
    clase de los más grandes a los más chicos."""
    grupos = {}
    for f in sospechosas:
        motivo = motivo_para_agrupar(f)
        # Las dudas, además, por par de listas: una muestra solo dice algo del grupo si el grupo
        # es parejo, y «nada dice que sean la misma pieza» entre CRI-FA y FISPA (sensores, casi
        # todos mal) no se parece al mismo motivo entre IMPERIAL y TARANTO (juntas, mitad y
        # mitad). Juntos, una muestra de uno escondía al otro.
        if not motivo.startswith(_MOTIVOS_QUE_SE_DESCARTAN):
            ma, mb = sorted((f.get("marca_a") or "", f.get("marca_b") or ""))
            motivo = f"{motivo} · {ma} ↔ {mb}"
        grupos.setdefault(motivo, []).append(f)
    salida = [(m, "descartar" if m.startswith(_MOTIVOS_QUE_SE_DESCARTAN) else "muestra", filas)
              for m, filas in grupos.items()]
    salida.sort(key=lambda g: (g[1] != "descartar", -len(g[2])))
    return salida


def motivo_de_rechazo_del_grupo(motivo):
    """La clave de MOTIVOS_DE_RECHAZO que corresponde a un grupo, o None."""
    return next((clave for prefijos, clave in _MOTIVO_DE_RECHAZO_DEL_GRUPO
                 if motivo.startswith(prefijos)), None)


def _submarca_del_codigo(codigo):
    """La marca pegada al final del código, en las listas que traen varias: «LEMSM017LUCAS» ->
    LUCAS, «40015FISPA» -> FISPA. Vacío si no tiene. Ver «las listas de distribuidor» en
    _analizar_lote_pendiente()."""
    limpio = sanitizar(codigo or "")
    return next((m for m in _MARCAS_QUE_SE_PEGAN_AL_CODIGO if limpio.endswith(m)), "")


_RE_MATERIAL_O_ESPESOR = re.compile(
    r"\(?\b(?:SINTETIC[OA]|SILICONA|CORCHO|GOMA|FIBRA|METALIC[OA]|METAL|ACERO|ALUMINIO|MG|"
    r"VITON|NITRILO|BRONCE|TEFLON|PTFE|MULTICAPA|METALGRAF|AMIANTO|GRAFITAD[OA]|NEOPRENO|"
    r"COBRE|PAPEL|CARTON|"
    r"GRAFITAD[OA]|MLS|ESP(?:ESOR)?\.?\s*\(?\d+(?:[.,]\d+)?\s*MM\)?|\d+(?:[.,]\d+)?\s*MM)\b\)?")
_RE_ES_ORIGINAL = re.compile(r"\(?\b(?:PRODUCTO\s+)?ORIGINAL\b\)?")


def _cabeza_de(descripcion):
    """El nombre de la pieza —la primera palabra que la nombra—, o ""."""
    firma = firma_de_producto(descripcion or "")
    return (firma or {}).get("cabeza") or ""


def _numero_sin_marca(codigo):
    """«70181FISPA» -> 70181, «LEIG030LUCAS» -> LEIG030: el número como lo escribe la lista."""
    limpio = sanitizar(codigo or "")
    sub = _submarca_del_codigo(codigo)
    return limpio[:-len(sub)] if sub and limpio.endswith(sub) else limpio


def _texto_sin_codigos(descripcion, codigo):
    """La descripción normalizada sin el código propio, para reconocer dos productos de la misma
    lista que se describen igual."""
    limpio = sanitizar(codigo or "")
    return " ".join(w for w in normalizar_texto(descripcion or "").split()
                    if not (len(sanitizar(w)) >= 3 and sanitizar(w) in limpio))


def _dos_que_citan_el_mismo_numero(cod_a, desc_a, cod_b, desc_b):
    """¿Hay una razón por la que dos productos de la MISMA marca citen el mismo número de
    fábrica sin que ninguno esté mal cargado? Devuelve la razón, o "".

    Sobre los 1.034 pares de FISPA con «el código apunta a más de un producto», las muestras
    tenían tres clases que no son errores:
      · uno NOMBRA al otro: «CAPUCHONES 79012 … MONTA EN BOBINA 70213», «PASO A PASO REGULABLE
        10609 … Regulable 10014», «70120 (reemplaza a 70181)»;
      · son la misma pieza en versión común y «(ORIGINAL)»: 84029 y 831259, el mismo sensor de
        presión de combustible de la Amarok, con la misma descripción;
      · son piezas distintas que van juntas: el microfiltro y el inyector, la rampa y el
        inyector. Cada una es la suya; ninguna está «mal cargada».
    Lo que sigue siendo una duda de verdad —el aforador de nafta y el diésel con el mismo
    número— no entra en ninguna y conserva la alarma."""
    ta, tb = normalizar_texto(desc_a or ""), normalizar_texto(desc_b or "")
    na, nb = _numero_sin_marca(cod_a), _numero_sin_marca(cod_b)
    if (len(nb) >= 4 and re.search(rf"\b{re.escape(nb)}\b", ta)) or \
            (len(na) >= 4 and re.search(rf"\b{re.escape(na)}\b", tb)):
        return "uno nombra al otro"

    def _sin_codigos(texto, codigo):
        limpio = sanitizar(codigo or "")
        salida = []
        for w in _RE_ES_ORIGINAL.sub(" ", texto).split():
            sw = sanitizar(w)
            if not (len(sw) >= 3 and sw in limpio):
                salida.append(w)
        return " ".join(salida)
    if ta and _sin_codigos(ta, cod_a) == _sin_codigos(tb, cod_b):
        return "la misma pieza, común y original"
    cabeza_a, cabeza_b = _cabeza_de(desc_a), _cabeza_de(desc_b)
    if cabeza_a and cabeza_b and cabeza_a != cabeza_b:
        return f"piezas distintas: {cabeza_a} y {cabeza_b}"
    # La misma pieza en otro material o espesor: «MEDIA LUNA TAPA DE VALVULAS (SINTETICO)» y
    # «(SILICONA)», «BOMBA NAFTA ESPESOR (0,8MM)» y «(1,6MM)». Illinois las lista por separado
    # y las dos citan el número de la pieza.
    def _sin_variante(texto, codigo):
        texto = _RE_MATERIAL_O_ESPESOR.sub(" ", _sin_codigos(texto, codigo))
        return " ".join(texto.split())
    if ta and _sin_variante(ta, cod_a) == _sin_variante(tb, cod_b):
        return "la misma pieza en otro material o espesor"
    # Juegos del mismo motor de distinto tipo —descarbonización, inferior, completo «sin TC»—:
    # Illinois les pone a todos la misma lista de números. El par con el tipo que no es lo
    # descarta el análisis por «juegos distintos»; la ambigüedad no agrega nada.
    juego_a, juego_b = tipo_de_juego_de_motor(desc_a), tipo_de_juego_de_motor(desc_b)
    if juego_a and juego_b and juegos_que_chocan(juego_a, juego_b):
        return f"juegos distintos del mismo motor: {juego_a} y {juego_b}"
    return ""


_RE_MONTA_EN = re.compile(r"\b(?:MONTA\s+EN|PARA\s+(?:LA\s+|EL\s+)?(?:BOBINA|INYECTOR|BOMBA))\b")


def _es_accesorio_del_numero(numero, cod, desc, otros):
    """Si este producto NO es la pieza de ese número de fábrica sino un accesorio o un kit que
    la trae, la relación para mostrar; si no, "". `otros` son los demás productos de la misma
    marca que citan el mismo número, [(código, descripción)].

    No alcanza con saber quién nombró el número primero: el capuchón suele ser la fila que lo
    trajo, y la bobina —la dueña del número— quedaba como «accesorio del capuchón». Se decide
    por la descripción:
      · lo que «monta en» o es «para la bobina» es el accesorio;
      · el número está en la lista de componentes de un kit —«KIT CAB Y BUJ (LEIHTF23SC/
        LSPR6F13)»—: es de una pieza que el kit trae adentro;
      · uno es un kit y el otro no —el kit de reparación y el aforador—: el kit trae la pieza.
    Lo demás —«reemplaza a», la versión original, dos piezas que no se sabe cuál es la dueña—
    solo deja de ser una alarma, sin apartar a nadie."""
    texto = normalizar_texto(desc or "")
    if re.search(r"\bREEMPLAZA\b", texto):
        return ""
    cabeza = _cabeza_de(desc)
    if _RE_MONTA_EN.search(texto) and any(_cabeza_de(d) != cabeza for _o, d in otros):
        return f"es un accesorio —«{cabeza}»— de la pieza con el número {numero}, no la pieza"
    # El número es parte del CÓDIGO del otro: «FI-IWP006FISPA» es el inyector IWP006, y el
    # microfiltro que lo cita (y a otros treinta) no es ese inyector.
    limpio_numero = sanitizar(numero)
    if (len(limpio_numero) >= 5 and limpio_numero not in sanitizar(cod)
            and any(limpio_numero in sanitizar(o) and _cabeza_de(d) != cabeza
                    for o, d in otros)):
        return (f"es otra pieza —«{cabeza}»— que cita el número {numero}, que es el de "
                f"«{next(o for o, _d in otros if limpio_numero in sanitizar(o))}»")
    # Trae adentro a otro de la misma marca que cita el número: «DISTRIBUCION C/BOMBA
    # (LKTBN417 + LWPN006)» es el kit LKTBN417 más la bomba de agua.
    listas = re.findall(r"\(([^)]*[/+][^)]*)\)", texto)
    numeros_otros = {_numero_sin_marca(o) for o, _d in otros}
    for lista in listas:
        if any(len(sanitizar(x)) >= 4 and sanitizar(x) in numeros_otros
               for x in re.split(r"[/+]", lista)):
            return (f"trae adentro a otro producto que tiene el número {numero} "
                    f"({lista.strip()}); no es un reemplazo de él")
    if es_un_kit(desc):
        for lista in listas:
            if any(sanitizar(x) == limpio_numero for x in re.split(r"[/+]", lista)):
                return (f"es un kit que trae adentro la pieza con el número {numero}, no un "
                        "reemplazo de ella")
        if any(not es_un_kit(d) and _cabeza_de(d) != cabeza for _o, d in otros):
            return (f"es un kit que trae la pieza con el número {numero}, no un reemplazo "
                    "de ella")
    return ""


# Las palabras de la firma que dicen DÓNDE va la pieza, para comparar dos filas que citan el
# mismo número. «TAPA ARBOL DE LEVAS» y «TAPA DE VALVULAS» son la misma tapa en muchos motores
# (en el Fiat Tipo, 7679315 es las dos, en los mismos espesores), así que cuentan igual.
# (Se suma a _LUGARES_DE_LA_PIEZA adentro de la función: descripciones.py se carga después.)
_LUGARES_EXTRA_PARA_EL_NUMERO = {"INYECTOR", "CAPUCHON"}
_LUGAR_QUE_ES_EL_MISMO = {"LEVAS": "VALVULA", "SALIDA": "ESCAPE"}
# Las que nombran la familia y no la pieza: «Despiece», «Juego de…», «KIT DE REPARACION».
_CABEZAS_QUE_NO_DICEN_LA_PIEZA = {"DESPIECE", "JUEGO", "JUEGOS", "KIT", "JGO", "REPUESTO"}
_RE_FORMA_DE_ILLINOIS = re.compile(r"^[A-Z][a-záéíóú]+\s")
_RE_TAMANO_DE_LA_PIEZA = re.compile(r"\b(CHIC[AO]|GRANDE)\b")
_RE_CONTENEDOR_DE_LA_PIEZA = re.compile(
    r"\b(?:CAJA|BASE|CARCASA|SOPORTE)\s+(?:DEL?\s+)?(TERMOSTATO|FILTRO|INYECTOR|BOMBA)\b")


def _lugares_para_el_numero(desc):
    pieza = (firma_de_producto(desc or "") or {}).get("pieza") or set()
    lugares = {_LUGAR_QUE_ES_EL_MISMO.get(p, p) for p in pieza
               if p in _LUGARES_DE_LA_PIEZA or p in _LUGARES_EXTRA_PARA_EL_NUMERO}
    # «4.203 INY. INDIRECTA», «C3L INY.»: la inyección del motor, no un lugar de la pieza. Con
    # otro lugar al lado no cuenta, y era lo que hacía coincidir a la junta de escape con la de
    # cárter del mismo Perkins.
    if len(lugares) > 1:
        lugares.discard("INYECCION")
    return lugares


def _otra_pieza_que_cita_el_numero(desc, otros):
    """(código, lugares propios, lugares del otro) del primero de `otros` —[(código, desc)]—
    que es OTRA pieza, o None. Otra pieza es un lugar distinto y ninguno en común —ESCAPE
    contra VALVULA, FILTRO contra CARTER— o la caja de la pieza contra la pieza: «CAJA
    TERMOSTATO» y «TERMOSTATO» con el mismo número. Distinto auto, cilindrada o cantidad de
    cilindros no cuenta: una junta de escape por cilindro sirve para el motor de 4 y el de 6."""
    propios = _lugares_para_el_numero(desc)
    texto = normalizar_texto(desc or "")
    cont = _RE_CONTENEDOR_DE_LA_PIEZA.search(texto)
    cabeza = _cabeza_de(desc)
    juego = tipo_de_juego_de_motor(desc)
    tamano = set(_RE_TAMANO_DE_LA_PIEZA.findall(texto))
    for otro, d in otros:
        ajenos = _lugares_para_el_numero(d)
        if propios and ajenos and not (propios & ajenos):
            return (otro, "/".join(sorted(propios)), "/".join(sorted(ajenos)))
        # Dos juegos distintos del mismo motor: ILLINOIS les pone a todos la misma lista de
        # números —«Juego de Descarbonización CUMMINS QSB // 4089998/4025157» y «Juego Inferior
        # CUMMINS QSB // 4089998/4025157»—, y cada número es de uno solo.
        juego_otro = tipo_de_juego_de_motor(d)
        if juego and juego_otro and juegos_que_chocan(juego, juego_otro):
            return (otro, f"juego {juego}", f"juego {juego_otro}")
        # «ADMISION CHICA» contra «ADMISION GRANDE» del mismo Cummins.
        tamano_otro = set(_RE_TAMANO_DE_LA_PIEZA.findall(normalizar_texto(d or "")))
        if tamano and tamano_otro and not (tamano & tamano_otro):
            return (otro, "/".join(sorted(tamano)), "/".join(sorted(tamano_otro)))
        # Sin lugares que comparar, el sustantivo: «ARANDELA CAMISA … // 1118500» contra
        # «1118500 RADIADOR INTERCOLLER» de Scania. Solo con la forma de ILLINOIS («Despiece
        # SCANIA …», «Junta …»), que pone el número como el SUYO. FISPA lo cita: la rampa nombra
        # el número de sus inyectores y la polea el del alternador, y eso no las hace otra pieza
        # con el mismo número. Y solo sustantivos de pieza: «Despiece IVECO 150 TURBO» no
        # tiene cabeza, tiene un modelo. Dos juegos del mismo motor (descarbonización, inferior)
        # los separa la regla de juegos, a partir de la fila que trajo el número.
        cabeza_otro = _cabeza_de(d)
        if (not (propios & ajenos) and cabeza and cabeza_otro
                and cabeza not in cabeza_otro and cabeza_otro not in cabeza
                and {cabeza, cabeza_otro} <= PALABRAS_NO_MODELO
                and not {cabeza, cabeza_otro} & _CABEZAS_QUE_NO_DICEN_LA_PIEZA
                and not (tipo_de_juego_de_motor(desc) and tipo_de_juego_de_motor(d))
                and _RE_FORMA_DE_ILLINOIS.match(desc or "") and _RE_FORMA_DE_ILLINOIS.match(d or "")):
            return (otro, cabeza, cabeza_otro)
        texto_otro = normalizar_texto(d or "")
        cont_otro = _RE_CONTENEDOR_DE_LA_PIEZA.search(texto_otro)
        if bool(cont) != bool(cont_otro):
            pieza = (cont or cont_otro).group(1)
            sin_caja = texto_otro if cont else texto
            if re.search(rf"\b{pieza}\b", sin_caja) and not re.search(r"\bJUNTA", sin_caja):
                caja = (cont or cont_otro).group(0)
                return ((otro, caja, pieza) if cont else (otro, pieza, caja))
    return None


def _numero_de_un_componente(numero, cod, desc):
    """Si el número de fábrica es el de una pieza que este producto TRAE ADENTRO, la relación
    para mostrar; si no, "".

    El importador toma como número de fábrica cualquier código de la descripción, y los kits
    listan sus componentes: «KIT BOB CAB (LEIG005/LEIHTG73SC)» es la bobina LEIG005 más los
    cables, «DISTRIBUCION C/BOMBA (LKTBN285 + LWPN029)» es el kit LKTBN285 más la bomba de agua.
    Como vínculo, eso decía que el kit ES la bobina. Sobre la cola real eran 59 pares limpios.
    Cuenta como componente si está en una lista con «+», o en una lista con «/» y además es el
    código de OTRO producto de la misma marca (con «LUCAS» pegado, como escribe FISPA): una
    lista con barras también puede ser la de los números de fábrica del propio kit."""
    texto = normalizar_texto(desc or "")
    limpio_numero = sanitizar(numero)
    if len(limpio_numero) < 4 or "(" not in texto:
        return ""
    sub = _submarca_del_codigo(cod)
    for lista in re.findall(r"\(([^)]*[/+][^)]*)\)", texto):
        # Con la cantidad afuera: «(LEIG030 X 4/LSPR6F13)» son cuatro bobinas LEIG030.
        elementos = [sanitizar(re.sub(r"\s+X\s*\d+\s*$", "", x.strip()))
                     for x in re.split(r"[/+]", lista)]
        if limpio_numero not in elementos:
            continue
        otro = ""
        if "+" not in lista:
            if not sub or limpio_numero + sub == sanitizar(cod):
                continue
            fila = c.execute("SELECT codigo_raw FROM productos WHERE codigo_clean = ? LIMIT 1",
                             (limpio_numero + sub,)).fetchone()
            if not fila:
                continue
            otro = f" («{fila['codigo_raw']}»)"
        return (f"trae adentro la pieza con el número {numero}{otro} —«{lista.strip()}»—; "
                "no es un reemplazo de ella")
    return ""


@functools.lru_cache(maxsize=50000)
def _palabras_sin_el_codigo(desc, cod):
    """Las palabras de la descripción sin las que son parte del código, sin «ORIGINAL» y sin
    la S final. Recordada: cada producto se compara contra varios hermanos."""
    limpio = sanitizar(cod or "")
    texto = _RE_ES_ORIGINAL.sub(" ", normalizar_texto(desc))
    salida = set()
    for w in re.split(r"[^A-Z0-9]+", texto):
        if len(w) < 2:
            continue
        sw = sanitizar(w)
        if not (len(sw) >= 3 and sw in limpio):
            salida.add(w.rstrip("S"))
    return frozenset(salida)


def _descripciones_mellizas(desc_a, cod_a, desc_b, cod_b):
    """¿Dos descripciones de la MISMA lista dicen lo mismo salvo el código?

    FISPA vende lo suyo y lo de LUCAS con la misma descripción, y el número de fábrica lo trae
    una sola de las dos filas: «REGULADORES DE PRESIo N 16004 FIAT Brava 1 6 16v» y «REGULADOR
    DE PRESION LEICP003 FIAT Brava 1 6 16v». La del mellizo quedaba en 50 puntos y sin ningún
    aviso —345 pares de la cola real—, porque la palabra rota y el plural hacían que las
    descripciones «no concordaran». Se comparan las palabras sin los códigos, sin «ORIGINAL» y
    sin la S final: 3 de cada 4 en común alcanza."""
    if not desc_a or not desc_b:
        return False
    # De DOS marcas: dos productos de LUCAS con casi la misma descripción no son mellizos, son
    # dos versiones —dos motores de arranque para los mismos autos— y justamente la duda que
    # marca «el código apunta a más de un producto».
    sub_a, sub_b = _submarca_del_codigo(cod_a), _submarca_del_codigo(cod_b)
    if not sub_a or not sub_b or sub_a == sub_b:
        return False

    pa, pb = _palabras_sin_el_codigo(desc_a, cod_a), _palabras_sin_el_codigo(desc_b, cod_b)
    if len(pa) < 4 or len(pb) < 4:
        return False
    return len(pa & pb) / len(pa | pb) >= 0.75


def pieza_para_el_abanico(codigo, descripcion):
    """Qué cuenta como UNA opción del abanico. Las variantes de un código son una sola
    (codigo_base_sin_variante(): «TC-882-MG 1M» y «TC-882-20» son la misma junta), y también
    los mellizos de las listas de distribuidor: FISPA vende la misma pieza con su código y con
    el de LUCAS —«SENSOR MAP 40068 FORD FIESTA VI…» y «SENSOR MAP LEMSM057 FORD FIESTA VI…»—,
    y contados como dos, cualquier producto que encajara con ese sensor tenía un empate de más
    y el abanico lo mandaba a revisión. Los mellizos se reconocen por la descripción sin el
    número del código."""
    if _submarca_del_codigo(codigo):
        limpio = sanitizar(codigo)
        sin_codigo = [w for w in normalizar_texto(descripcion or "").split()
                      if not (sanitizar(w) and len(sanitizar(w)) >= 3 and sanitizar(w) in limpio)]
        if sin_codigo:
            return "MELLIZOS:" + " ".join(sin_codigo)
    return codigo_base_sin_variante(codigo) or sanitizar(codigo or "")


def piezas_del_abanico(candidatos):
    """{(código, descripción): pieza} para los candidatos de un abanico, juntando los que son la
    misma pieza por cualquiera de los dos caminos: el mismo código base (ver
    pieza_para_el_abanico(): los espesores de una junta) o la MISMA DESCRIPCIÓN sin el código.

    Lo segundo es lo que faltaba. IMPERIAL vende la misma junta en varios materiales, cada uno
    con su código y la misma descripción: «JTA CARTER DEUTZ 913 4 CIL.» es 604AC2, 604AD2 y
    604AD6. Contados como tres piezas, la junta de Illinois de ese cárter tenía un abanico de
    tres empatados y ninguno quedaba limpio. Si la misma lista trae dos filas que dicen lo
    mismo, no hay forma de elegir entre ellas: son una opción."""
    padre = {}

    def raiz(x):
        while padre.setdefault(x, x) != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    for cod, desc in candidatos:
        yo = ("codigo", cod)
        claves = [("base", pieza_para_el_abanico(cod, desc))]
        palabras = _palabras_sin_el_codigo(desc or "", cod or "")
        if len(palabras) >= 3:
            claves.append(("descripcion", palabras))
        for clave in claves:
            padre[raiz(yo)] = raiz(clave)
    return {(cod, desc): raiz(("codigo", cod)) for cod, desc in candidatos}


def es_de_un_abanico(fila):
    """¿El par está en revisión por el abanico? Ver «el abanico» en _analizar_lote_pendiente()."""
    return any(a.startswith("🪭") for a in (fila.get("alarmas") or []))


def plan_de_la_lista(limpias, sospechosas, relacionadas):
    """Los pasos para resolver una lista, en el orden que conviene, con cuántos pares resuelve
    cada uno y cuánto trabajo a mano lleva. [{"Paso", "Pares", "Trabajo", "Dónde"}].

    La pantalla de revisión tiene cinco herramientas —los kits, los descartes por motivo, las
    muestras de las limpias, las muestras de las dudas y los abanicos— y con 28.000 pares no
    era obvio por dónde empezar. El orden va de lo que se resuelve de un toque a lo que hay que
    mirar, porque cada paso achica lo que queda para los siguientes."""
    pasos = []
    if relacionadas:
        pasos.append({"Paso": "📦 Descartar kits y accesorios", "Pares": len(relacionadas),
                      "Trabajo": "1 toque", "Dónde": "el cartel de arriba"})
    en_revision = [x for x in sospechosas
                   if not (x.get("alarmas") and all(a.startswith("🪭") for a in x["alarmas"]))]
    grupos_mot = grupos_por_motivo(en_revision)
    descartar = [g for g in grupos_mot if g[1] == "descartar"]
    con_muestra = [g for g in grupos_mot if g[1] == "muestra"]
    if descartar:
        pasos.append({"Paso": "🚫 Descartar lo que el texto contradice",
                      "Pares": sum(len(g[2]) for g in descartar),
                      "Trabajo": f"{len(descartar)} toque(s), mirando unos ejemplos",
                      "Dónde": "📋 Para revisar, por motivo"})
    grupos_l = grupos_de_limpias(limpias)
    if grupos_l:
        marcas = sum(min(len(f), tamano_de_la_muestra(len(f))) for _a, _b, f, _fr in grupos_l)
        pasos.append({"Paso": "🎯 Aprobar las limpias con su muestra",
                      "Pares": len(limpias),
                      "Trabajo": f"{marcas:,} marcas en {len(grupos_l)} muestra(s)",
                      "Dónde": "🎯 Aprobar las limpias por grupos"})
    if con_muestra:
        marcas = sum(min(len(g[2]), tamano_de_la_muestra(len(g[2]))) for g in con_muestra)
        pasos.append({"Paso": "🔍 Resolver las dudas con una muestra",
                      "Pares": sum(len(g[2]) for g in con_muestra),
                      "Trabajo": f"{marcas:,} marcas en {len(con_muestra)} muestra(s)",
                      "Dónde": "📋 Para revisar, por motivo"})
    abanicos = abanicos_para_elegir(limpias, sospechosas)
    if abanicos:
        # Solo los que están en revisión ÚNICAMENTE por el abanico: el mejor candidato, si
        # quedó limpio, ya se contó con las limpias, y los que además tienen otro motivo, con
        # su motivo.
        pasos.append({"Paso": "🪭 Elegir la equivalente entre varias",
                      "Pares": len({(f["a"], f["b"]) for a in abanicos for f in a["candidatos"]
                                    if f.get("alarmas")
                                    and all(x.startswith("🪭") for x in f["alarmas"])}),
                      "Trabajo": f"{len(abanicos):,} producto(s), uno por uno",
                      "Dónde": "🪭 Elegí cuál es la equivalente"})
    return pasos


def abanicos_para_elegir(limpias, sospechosas):
    """Los productos que tienen varios candidatos DISTINTOS en otra lista, para elegir a mano.

    Devuelve [{"producto": {...}, "marca_otra": str, "candidatos": [filas]}], de los que
    más candidatos tienen a los que menos. Se arma alrededor de los pares que el análisis mandó
    a revisión por el abanico, y cada uno se asigna al lado que más candidatos tiene: una junta
    de ILLINOIS con 11 de TARANTO se presenta como «esta junta, ¿con cuál de estas 11?», que es
    una decisión, y no como 11 pares sueltos en la lista de revisión.
    Los candidatos son TODOS los pares de ese producto con esa lista, también el que el
    análisis dejó limpio por ser el que mejor coincidía: la persona tiene que verlos juntos."""
    # Sin los vetados (15 o menos): el texto ya dice que son otra pieza u otro auto, se
    # descartan en su grupo de «Para revisar, por motivo» y no son una opción para elegir.
    todas = [f for f in limpias + sospechosas
             if "OEM" not in (f.get("tipo_a"), f.get("tipo_b")) and f.get("confianza", 0) > 15]
    por_clave = {}
    for f in todas:
        for clave in ((f["a"], f.get("marca_b")), (f["b"], f.get("marca_a"))):
            por_clave.setdefault(clave, []).append(f)
    elegidas = {}
    for f in sospechosas:
        if not es_de_un_abanico(f):
            continue
        claves = [(f["a"], f.get("marca_b")), (f["b"], f.get("marca_a"))]
        clave = max(claves, key=lambda k: len(por_clave.get(k, ())))
        elegidas.setdefault(clave, None)
    salida = []
    for (pid, marca_otra) in elegidas:
        candidatos = por_clave.get((pid, marca_otra), [])
        if len(candidatos) < 2:
            continue
        f0 = candidatos[0]
        lado = "a" if f0["a"] == pid else "b"
        salida.append({"producto": {"id": pid, "cod": f0[f"cod_{lado}"],
                                    "marca": f0[f"marca_{lado}"], "desc": f0.get(f"desc_{lado}")},
                       "marca_otra": marca_otra,
                       "candidatos": sorted(candidatos, key=lambda f: -f.get("confianza", 0))})
    salida.sort(key=lambda x: -len(x["candidatos"]))
    return salida


def candidatos_por_pieza(abanico):
    """Los candidatos de un abanico agrupados por pieza: las variantes de un mismo código
    (TC-432-20 0M, 1M, 2M, TC-432-MG 0M...) son una sola opción. Con 52 candidatos que en
    realidad eran 8 juntas en 2 materiales y 3 espesores, elegir de a uno era imposible en el
    celular.

    Devuelve [(base, [filas])], la base con el mejor puntaje primero. Si el producto dice su
    espesor, dentro de cada pieza quedan solo las variantes con ese espesor (o sin espesor
    escrito): las otras no son la misma aunque sean la misma junta."""
    pid = abanico["producto"]["id"]
    esp_prod = medidas_desde_descripcion(abanico["producto"].get("desc") or "").get("espesor")
    quedan = []
    for f in abanico["candidatos"]:
        lado = "b" if f["a"] == pid else "a"
        if esp_prod is not None:
            esp_c = medidas_desde_descripcion(f.get(f"desc_{lado}") or "").get("espesor")
            if esp_c is not None and abs(esp_c - esp_prod) > 0.03:
                continue
        quedan.append((f, (f[f"cod_{lado}"], f.get(f"desc_{lado}"))))
    # Las mismas piezas que cuenta el análisis (ver piezas_del_abanico()): los materiales de
    # IMPERIAL, con la misma descripción, son una sola opción. Cada una se nombra por la base
    # del menor de sus códigos, para que la clave sea un texto estable.
    pieza_de = piezas_del_abanico([otro for _f, otro in quedan])
    nombre = {}
    for _f, otro in sorted(quedan, key=lambda x: str(x[1][0])):
        nombre.setdefault(pieza_de[otro], pieza_para_el_abanico(*otro))
    grupos = {}
    for f, otro in quedan:
        grupos.setdefault(nombre[pieza_de[otro]], []).append(f)
    return sorted(grupos.items(), key=lambda g: -max(f.get("confianza", 0) for f in g[1]))


def tabla_del_abanico(abanico):
    """Lo que distingue a cada candidato del abanico, al lado del producto: una fila para el
    producto y una por opción (ver candidatos_por_pieza()), con ⚠️ donde no coincide.

    Elegir con «código — los primeros 80 caracteres de la descripción» era adivinar: lo que
    separa a una sonda de otra (el largo del cable, los años) o a una junta de otra (el motor,
    el espesor) casi siempre está al final del texto. Acá se pone a la vista."""
    def rasgos(desc):
        firma = firma_de_producto(desc or "") or {}
        medidas = medidas_desde_descripcion(desc or "")
        anios = firma.get("anios") or ()
        return {
            "modelos": set(firma.get("modelos") or ()),
            "Años": "/".join(f"{d}-{'…' if h == 2100 else h}" for d, h in anios[:2]),
            "Motor": "/".join(sorted(firma.get("motores") or ())[:3]),
            "Cilindrada": "/".join(sorted(firma.get("cilindradas") or ())[:3]),
            "Cable": f"{firma['cable_mm'] / 10:.0f} cm" if firma.get("cable_mm") else "",
            "Vías": str(firma["vias"]) if firma.get("vias") else "",
            "Espesor": f"{medidas['espesor']} mm" if medidas.get("espesor") else "",
            # Se muestra la estándar solo si alguna es sobremedida: ver más abajo.
            "Medida": ("sobremedida" if firma.get("sobremedida") == "SI"
                       else f"+{firma['sobremedida']}".replace(".", ",")
                       if firma.get("sobremedida") else ""),
        }
    pid = abanico["producto"]["id"]
    propio = rasgos(abanico["producto"].get("desc"))
    campos = ("Años", "Motor", "Cilindrada", "Cable", "Vías", "Espesor", "Medida")
    filas = [dict({"Opción": f"▶ {abanico['producto']['cod']} (este)", "Modelos en común": ""},
                  **{k: propio[k] for k in campos})]
    for _base, filas_b in candidatos_por_pieza(abanico):
        f = filas_b[0]
        lado = "b" if f["a"] == pid else "a"
        suyo = rasgos(f.get(f"desc_{lado}"))
        fila = {"Opción": f[f"cod_{lado}"] + (f" (+{len(filas_b) - 1})" if len(filas_b) > 1
                                              else ""),
                "Modelos en común": "/".join(sorted(propio["modelos"] & suyo["modelos"])[:3])
                                    or ("⚠️ ninguno" if propio["modelos"] and suyo["modelos"]
                                        else "")}
        for k in campos:
            valor = suyo[k]
            # Se marca lo que los dos dicen y no coincide; lo que uno solo dice no se marca.
            fila[k] = (f"⚠️ {valor}" if valor and propio[k] and valor != propio[k] else valor)
        filas.append(fila)
    # La sobremedida la dice solo la que lo es: si alguna lo dice, las otras son estándar, y
    # eso también hay que verlo (ver sobremedidas_que_chocan()).
    if any(f["Medida"] for f in filas):
        for f in filas:
            if not f["Medida"]:
                f["Medida"] = "estándar" if f is filas[0] or not propio["Medida"] else "⚠️ estándar"
            elif f is not filas[0] and not propio["Medida"]:
                f["Medida"] = f"⚠️ {f['Medida']}"
    # Las columnas que nadie tiene no se muestran: en el celular cada columna cuesta.
    usadas = [k for k in campos if any(f[k] for f in filas)]
    return [{k: f[k] for k in ("Opción", "Modelos en común", *usadas)} for f in filas]


def pieza_sugerida_del_abanico(abanico):
    """La opción del abanico que conviene traer ya elegida, o None.

    Solo cuando hay UNA que le gana a todas: la que el análisis dejó limpia (55 o más) y todas
    las demás en revisión. Es la que mejor coincide en modelo, motor y cilindrada (ver
    fuerza_de_la_coincidencia()); si empatan dos, no se sugiere ninguna."""
    grupos = candidatos_por_pieza(abanico)
    limpias = [base for base, filas in grupos
               if max(f.get("confianza", 0) for f in filas) >= 55]
    return limpias[0] if len(limpias) == 1 else None


def parecidos_de_varios(rechazados, candidatas, tope=60):
    """Los parecidos de varios rechazos juntos, agrupados por motivo, para la pantalla:
    [{"motivo", "clave_motivo", "ejemplo", "filas"}]. Un par se ofrece una sola vez aunque se
    parezca a varios. 'rechazados' son (motivo, fila). Con tope, porque descartar un grupo de
    cientos de una vez no necesita cientos de búsquedas para encontrar lo mismo."""
    ya = {(f["a"], f["b"]) for _, f in rechazados}
    salida = {}
    with recordando_lo_de_cada_producto():
        for motivo, fila in rechazados[:tope]:
            hallados = [f for f in pares_parecidos(fila, motivo, candidatas)
                        if (f["a"], f["b"]) not in ya]
            ya.update((f["a"], f["b"]) for f in hallados)
            if hallados:
                grupo = salida.setdefault(motivo, {
                    "motivo": MOTIVOS_DE_RECHAZO[motivo], "clave_motivo": motivo,
                    "ejemplo": f"{fila['cod_a']} ↔ {fila['cod_b']}", "filas": []})
                grupo["filas"].extend(hallados)
    return list(salida.values())


def pares_parecidos(fila_rechazada, motivo, candidatas):
    """Los pares de 'candidatas' que tienen el MISMO problema que el que se acaba de rechazar.

    Es lo que hace que un rechazo enseñe algo: la persona dice por qué está mal, y con eso la
    app sabe qué buscar. Los criterios son estrechos a propósito: lo que se ofrece se descarta
    con un botón, y ofrecer de más es tentar a descartar pares buenos.

      · siempre: el mismo producto contra una VARIANTE del otro (TC-882-20 1M y TC-882-MG 1M son
        la misma junta en otro material: si una está mal con la S10, la otra también);
      · otro auto: el mismo producto contra otro que nombra exactamente los mismos modelos;
      · otra medida: el mismo producto contra otro con la misma medida que el rechazado;
      · otra pieza: solo las variantes (ver el comentario adentro);
      · juego contra suelta: las mismas dos listas, y de cada lado el mismo tipo de juego y las
        mismas palabras de pieza que el rechazado;
      · código mal leído: todo lo que cuelga del mismo código de fábrica.

    Con un código de fábrica del otro lado, el texto no sirve para buscar: su descripción es una
    copia de la del proveedor que lo nombró (ver rubros_de_los_codigos_de_fabrica()), así que
    «nombra los mismos modelos» o «mide lo mismo» se cumpliría con todos los otros números de
    ese producto, los buenos incluidos. Ahí solo valen las variantes y el mismo código."""
    a, b = fila_rechazada["a"], fila_rechazada["b"]
    desc = {a: fila_rechazada.get("desc_a"), b: fila_rechazada.get("desc_b")}
    cod = {a: fila_rechazada.get("cod_a"), b: fila_rechazada.get("cod_b")}
    marca = {a: fila_rechazada.get("marca_a"), b: fila_rechazada.get("marca_b")}
    tipo = {a: fila_rechazada.get("tipo_a"), b: fila_rechazada.get("tipo_b")}
    es_oem = {p: (tipo.get(p) or "") == "OEM" for p in (a, b)}
    firmas = {}

    def _firma(texto):
        if texto not in firmas:
            firmas[texto] = firma_de_producto(texto) or {}
        return firmas[texto]

    def _texto(t):
        return normalizar_texto(t or "")

    medidas = {}
    if motivo == "variante":
        ids = {a, b} | {x for f in candidatas for x in (f["a"], f["b"]) if {f["a"], f["b"]} & {a, b}}
        medidas = cargar_medidas_de_varios(list(ids))

    def _misma_medida(x, y):
        mx, my = medidas.get(x) or {}, medidas.get(y) or {}
        campos = [cm for cm, _ in CAMPOS_MEDIDAS if mx.get(cm) is not None]
        return bool(campos) and all(mx.get(cm) == my.get(cm) for cm in campos)

    # Juego contra suelta: solo si el rechazado de verdad es un juego contra otra cosa.
    _juego = {p: _firma(desc[p]).get("juego") for p in (a, b)}
    buscar_juegos = (motivo == "juego" and _juego[a] != _juego[b]
                     and not any(es_oem.values()) and marca[a] != marca[b])

    salida = []
    for f in candidatas:
        x, y = f["a"], f["b"]
        if {x, y} == {a, b}:
            continue
        d2 = {x: f.get("desc_a"), y: f.get("desc_b")}
        c2 = {x: f.get("cod_a"), y: f.get("cod_b")}
        m2 = {x: f.get("marca_a"), y: f.get("marca_b")}
        t2 = {x: f.get("tipo_a"), y: f.get("tipo_b")}
        comun = {x, y} & {a, b}
        parecido = False
        if len(comun) == 1:
            fijo = comun.pop()
            otro_rech = b if fijo == a else a
            otro_cand = y if fijo == x else x
            if motivo == "codigo":
                # El código mal leído es el de fábrica: lo que cuelga de él tiene el mismo
                # problema. Lo demás del producto del proveedor, no: sus otros números pueden
                # estar perfectos.
                parecido = es_oem[fijo]
            elif m2[otro_cand] == marca[otro_rech]:
                base_r, base_c = _base_de_la_pieza(cod[otro_rech]), _base_de_la_pieza(c2[otro_cand])
                # La variante NO cuenta cuando el motivo es la medida: si la junta de 1,10 mm
                # estaba mal por el espesor, la misma junta en otro espesor puede ser la buena.
                # Y el código solo no alcanza: codigo_base_sin_variante() recorta todos los
                # tramos cortos, que en ILLINOIS son material y espesor, pero en otras listas es
                # la pieza misma («14-R7818.40.071» es la sonda del Escort y «.040» la del
                # Fiesta). Una variante de verdad tiene la MISMA descripción salvo la medida.
                if (base_r and base_r == base_c and motivo != "variante"
                        and _texto_sin_medidas(desc[otro_rech]) == _texto_sin_medidas(d2[otro_cand])):
                    parecido = True
                elif (not any(es_oem.values()) and (t2[otro_cand] or "") != "OEM"
                      and _texto(desc[otro_rech]) != _texto(desc[fijo])):
                    fr, fc = _firma(desc[otro_rech]), _firma(d2[otro_cand])
                    if motivo == "otro_auto":
                        parecido = bool(fr.get("modelos")) and fr.get("modelos") == fc.get("modelos")
                    elif motivo == "variante":
                        parecido = _misma_medida(otro_rech, otro_cand)
                    # «Otra pieza» no busca por texto, a propósito: si el texto de los dos dice
                    # la misma pieza y la persona dice que no lo es, el texto no tiene con qué
                    # encontrar otras. Probado: buscando por las palabras de pieza, rechazar una
                    # junta de cárter de Fiat 1100 ofrecía descartar las de Fiat 128 y 147,
                    # entre las que puede estar la buena. Quedan las variantes, de arriba.
        elif buscar_juegos and not comun and "OEM" not in {t2[x] or "", t2[y] or ""}:
            if {m2[x], m2[y]} == {marca[a], marca[b]}:
                par_c = {m2[x]: x, m2[y]: y}
                parecido = True
                for rech in (a, b):
                    cand = par_c[marca[rech]]
                    fr, fc = _firma(desc[rech]), _firma(d2[cand])
                    parecido &= (fr.get("juego") == fc.get("juego")
                                 and (fr.get("pieza") or set()) == (fc.get("pieza") or set()))
        if parecido:
            salida.append(f)
    return salida


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
    if alarma.startswith(("💲 Los precios se diferencian", "💲 los precios se diferencian",
                          "💲 Los precios no cierran")):
        return "💲 Los precios no cierran"
    m = re.match(r"📐 NO coinciden: (.*)", alarma)
    if m:
        medidas = [p.split(":")[0].strip() for p in m.group(1).split(";")]
        return "📐 NO coinciden: " + " y ".join(medidas)
    m = re.match(r"⚠️ El código .+? apunta a más de un producto de (.+?) — y «", alarma)
    if m:
        return (f"⚠️ Un número de fábrica que {m.group(1)} le pone a piezas distintas: "
                "aprobarlo las haría equivalentes")
    m = re.match(r"⚠️ El código .+? apunta a más de un producto de (.+?) — ", alarma)
    if m:
        return (f"⚠️ Un código que apunta a más de un producto de {m.group(1)} — alguno de los "
                "dos está mal cargado")
    if alarma.startswith("🎚️ "):
        return alarma
    if alarma.startswith("🪞 "):
        return ("🪞 La otra lista tiene varios productos con la misma descripción y el texto no "
                "dice cuál es este")
    if alarma.startswith("🪭 "):
        # «emparejado con 4 productos», «con 5», «con 6»...: cada cantidad era un grupo aparte, y
        # en el barrido real eran 30 grupos de la misma cosa.
        return ("🪭 Uno de los dos está emparejado con varios productos distintos de la otra "
                "lista y este no es el que mejor coincide")
    if alarma.startswith("🔎 «"):
        return ("🔎 El código de fábrica se sacó del texto del medio, donde van los motores y los "
                "modelos, y no de la lista de números del final")
    if alarma.startswith("🧯 «") and "no es un código de fábrica" in alarma:
        return "🧯 Lo que se tomó como código de fábrica es un modelo, una medida o un año"
    if alarma.startswith("🚫 Código ") and " parece una " in alarma:
        return "🚫 Uno de los dos códigos parece una medida o una especificación"
    # «63 vs 53 cm», «120/105 vs 98»: el dato de cada par. Lo que decide —que el largo, las
    # temperaturas o las vías no son las mismas— es igual para todos.
    if alarma.startswith("🔤 una de las dos no dice de qué es la junta"):
        return "🔤 Una de las dos no dice de qué es la junta: puede ser esa o no"
    if alarma.startswith("🔤 una de las dos no dice para qué auto es"):
        return "🔤 Una de las dos no dice para qué auto es: puede ir en ese o no"
    if alarma.startswith("🔤 el largo de cable se parece"):
        return "🔤 El largo de cable se parece pero no es el mismo: puede ser cómo lo mide cada lista"
    if alarma.startswith("🔤 un juego de juntas de"):
        return ("🔤 Un juego de juntas de un lugar contra la junta de ese lugar: algunas listas "
                "llaman «junta» al juego")
    if alarma.startswith("🔤 el mismo auto con otra cilindrada"):
        return ("🔤 Un sensor del mismo auto con otra cilindrada: puede servir para las dos, o no")
    if alarma.startswith("🔤 un nombre de modelo de marcas distintas"):
        return ("🔤 Solo comparten un nombre de modelo, y cada una nombra otra marca: puede ser "
                "otra cosa en cada una")
    for _sin_detalle in ("🔤 carburadores distintos", "🔤 motores de distintas válvulas"):
        if alarma.startswith(_sin_detalle):
            return _sin_detalle
    if alarma.startswith("🔤 presiones distintas"):
        return "🔤 presiones distintas"
    m = re.match(r"(🔤 (?:largo de cable distinto|temperaturas distintas|"
                 r"distinta cantidad de vías)) \(", alarma)
    if m:
        return m.group(1)
    return alarma


# Ver el análisis guardado en Estadísticas → Equivalencias sugeridas: cuántas decisiones se
# descuentan del análisis ya hecho antes de rehacerlo entero.
RECORTES_ANTES_DE_REANALIZAR = 200


# EL ANÁLISIS DEL LOTE ES DEL SERVIDOR, NO DE LA SESIÓN. Tarda 6 s sobre la cola real, y
# guardado en la sesión se perdía al recargar la página o al entrar desde el celular (cada
# reconexión es una sesión nueva). Queda UNO, el último: la clave con que se guarda dice qué
# lote, qué tanda y cuántos pendientes había, así que otro lote simplemente no coincide.
# A propósito NO va en del_proceso(): la lógica se carga una vez por proceso y se vuelve a
# cargar cuando cambia el código (ver logica/__init__.py), y un análisis hecho con las reglas
# viejas no tiene que sobrevivir a eso: es de cada carga del código —«de cada pasada» de la
# lógica—, a propósito.
_ANALISIS_DE_LOTE = {}


# Y dura unas horas: lo que se aprende de lo que vas decidiendo en otras listas, las fichas
# nuevas y los puntajes que rehace la tarea de fondo le van cambiando algo a cada par.
HORAS_QUE_DURA_EL_ANALISIS = 3


def analisis_de_lote_guardado():
    guardado = _ANALISIS_DE_LOTE.get("ultimo")
    if guardado and time.time() - guardado.get("_hecho", 0) > HORAS_QUE_DURA_EL_ANALISIS * 3600:
        return None
    return guardado


def guardar_analisis_de_lote(analisis):
    # Un recorte conserva la hora del análisis entero del que salió.
    anterior = _ANALISIS_DE_LOTE.get("ultimo") or {}
    analisis["_hecho"] = (anterior.get("_hecho", time.time()) if analisis.get("recortes")
                          else time.time())
    _ANALISIS_DE_LOTE["ultimo"] = analisis


def olvidar_analisis_de_lote():
    _ANALISIS_DE_LOTE.pop("ultimo", None)


# Las tandas que ofrece la pantalla; arranca en la que cubre la lista entera.
OPCIONES_DE_TANDA_DEL_LOTE = [400, 1000, 2500, 5000, 10000, 25000, 100000]


def tanda_que_cubre(total):
    return next((o for o in OPCIONES_DE_TANDA_DEL_LOTE if o >= total),
                OPCIONES_DE_TANDA_DEL_LOTE[-1])


def clave_del_analisis_de_lote(lote, cuantos, desde, total):
    """Lo que tiene que coincidir para que un análisis guardado siga valiendo. El total de
    pendientes lo invalida al decidir (ver el recorte en la pantalla), y los pares vistos juntos
    en un portal porque leer fichas le agrega pruebas a pares que ya estaban."""
    return (lote, int(cuantos), int(desde), int(total), cuantos_juntos_en_portales())


def falta_preparar_el_analisis():
    """¿La tanda de fondo tiene que dejar listo el análisis? Una vez por carga del código."""
    return not _ANALISIS_DE_LOTE.get("_intentado")


def preparar_el_analisis_del_primer_lote():
    """Deja hecho el análisis de la lista que la pantalla muestra primero, tal como la pantalla
    lo pediría. Lo corre la tanda de fondo al arrancar y después de cada importación: son 8 s
    sobre la cola real que antes esperaba el primero que abría «Equivalencias sugeridas».
    Devuelve si lo hizo (False si ya estaba o no hay nada pendiente)."""
    _ANALISIS_DE_LOTE["_intentado"] = True
    lotes = resumen_lotes_pendientes()
    # La lista recién importada que era muy grande para analizarla en el momento (ver
    # informe_post_importacion()) va primero: es la que alguien está por abrir.
    pedido = obtener_config("lote_a_analizar", "")
    if pedido:
        guardar_config("lote_a_analizar", "")
    if not lotes:
        return False
    lote = next((l["lote"] for l in lotes if l["lote"] == pedido), lotes[0]["lote"])
    total = contar_pendientes_del_lote(lote)
    cuantos = tanda_que_cubre(total)
    clave = clave_del_analisis_de_lote(lote, cuantos, 0, total)
    guardado = analisis_de_lote_guardado()
    if guardado and guardado.get("clave") == clave:
        return False
    _ANALISIS_DE_LOTE["_preparando"] = time.time()
    try:
        resultado = analizar_lote_pendiente(lote, limite=cuantos, desde=0)
        guardar_analisis_de_lote({"clave": clave, "resultado": resultado})
    finally:
        _ANALISIS_DE_LOTE.pop("_preparando", None)
    return True


def esperar_el_analisis_en_preparacion(tope_segundos=30):
    """Si la tanda de fondo está haciendo el análisis justo ahora, la pantalla lo espera en vez
    de hacer otro igual al lado: los dos se reparten el procesador y tardan más cada uno (7 s en
    vez de los 6 de uno solo, medido). Con tope, por si el de fondo se trabara."""
    empezo = _ANALISIS_DE_LOTE.get("_preparando")
    if empezo:
        # Mientras espera, esta pantalla no le pide el paso a la tarea de fondo: el análisis
        # le cede el procesador a la pantalla que se está dibujando (ver ceder_al_mostrador()),
        # y con las dos esperándose una a la otra se quedaban quietas hasta el tope de 20 s.
        _actividad_del_mostrador()["termino"] = time.monotonic()
    while empezo and time.time() - empezo < tope_segundos:
        time.sleep(0.1)
        empezo = _ANALISIS_DE_LOTE.get("_preparando")
    return analisis_de_lote_guardado()


def pares_pendientes_del_lote(lote):
    """{(a, b)} con a < b: los pares de ese lote que siguen esperando revisión."""
    c.execute("""SELECT MIN(producto_a_id, producto_b_id), MAX(producto_a_id, producto_b_id)
                 FROM equivalencias_pendientes WHERE lote = ?""", (lote,))
    return {(r[0], r[1]) for r in c.fetchall()}


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
    # Y lo que evidencia_cruzada() pide de a dos productos, también de una vez.
    precargar_para_evidencia({f["a"] for f in filas} | {f["b"] for f in filas}, medidas)

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
    descripcion_de = {}       # código del proveedor -> su descripción
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
        descripcion_de[cod_otro] = desc_otro or ""
        juegos_y_piezas.setdefault(clave, set()).add(bool(es_un_kit(desc_otro)))
        if normalizar_texto(desc_oem or "") == normalizar_texto(desc_otro or "") and desc_oem:
            candidatos_a_origen.setdefault(clave, set()).add(cod_otro)
    origen_del_codigo = {k: next(iter(v)) for k, v in candidatos_a_origen.items() if len(v) == 1}

    # Y LOS QUE YA ESTÁN APROBADOS con el mismo número, o esperando en OTRA lista de la cola.
    # Mirando solo este lote, el aforador de BMW —aprobado hace rato con su número— no estaba, y
    # los dos kits de reparación que citan ese número quedaban solos: dos kits iguales, nada que
    # decir, y pasaban a verde como si el kit FUERA la bomba. Y el 36866416 de PERKINS está en
    # la junta de escape del lote del barrido y en la de cárter del lote de ILLINOIS: cada lote
    # veía una sola. Con todos adentro del grupo, los kits son lo que son (ver
    # _es_accesorio_del_numero()) y las piezas distintas se ven. No entran a
    # candidatos_a_origen: el origen es el de la fila que está en la cola.
    _oem_ids = {}
    for f in filas:
        if "OEM" in (f["tipo_a"], f["tipo_b"]):
            _oid, _ocod = ((f["a"], f["cod_a"]) if f["tipo_a"] == "OEM" else (f["b"], f["cod_b"]))
            _oem_ids[_oid] = sanitizar(_ocod)
    try:
        for _tanda, _marcas in en_tandas(list(_oem_ids), usos_por_consulta=3):
            c.execute(f"""SELECT e.producto_a_id AS a, e.producto_b_id AS b,
                                 p.id AS otro, p.codigo_raw AS cod, p.descripcion AS descr,
                                 m.nombre AS marca
                          FROM (SELECT producto_a_id, producto_b_id FROM equivalencias
                                UNION
                                SELECT producto_a_id, producto_b_id FROM equivalencias_pendientes
                                 WHERE COALESCE(lote, '') <> ?) e
                          JOIN productos p ON p.id = CASE WHEN e.producto_a_id IN ({_marcas})
                                                          THEN e.producto_b_id
                                                          ELSE e.producto_a_id END
                          JOIN marcas m ON m.id = p.marca_id
                          WHERE (e.producto_a_id IN ({_marcas}) OR e.producto_b_id IN ({_marcas}))
                            AND m.tipo <> 'OEM'""", [lote] + _tanda + _tanda + _tanda)
            for r in c.fetchall():
                _oid = r["a"] if r["a"] in _oem_ids else r["b"]
                _clave_ap = (_oem_ids[_oid], r["marca"])
                if _clave_ap in apuntados and r["otro"] not in apuntados[_clave_ap]:
                    apuntados[_clave_ap][r["otro"]] = r["cod"]
                    descripcion_de.setdefault(r["cod"], r["descr"] or "")
    except sqlite3.OperationalError as _err:
        anotar_error("analizar_lote_pendiente", _err)

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
        if _descripciones_mellizas(descripcion_de.get(origen), origen,
                                   descripcion_de.get(cod_propio), cod_propio):
            return (f"Es el mellizo de «{origen}» —la fila que trajo este número de fábrica—: "
                    "la misma descripción con otro código, como vende FISPA lo suyo y lo de "
                    "LUCAS")
        return ""

    # La alarma de ambigüedad no le corresponde al hermano que ES una variante del origen:
    # que la junta venga en tres espesores no quiere decir que alguno esté mal cargado.
    # Antes era todo-o-nada sobre el grupo y alcanzaba un miembro raro para marcar a los demás:
    # en «11044BC20A», TC-384-15 / -MG / -11 son la misma junta en tres materiales y TC-801-11
    # es otra pieza, y los cuatro se llevaban el castigo.
    # LAS LISTAS DE DISTRIBUIDOR TRAEN VARIAS MARCAS. FISPA vende lo suyo («40015FISPA») y lo de
    # LUCAS («LEMSM017LUCAS») en la misma lista, y las dos citan el mismo número de fábrica
    # porque son la misma pieza de dos fabricantes. Que un número apunte a una de cada marca
    # no es un error de carga: la ambigüedad es tener DOS de la MISMA marca. Sobre la cola real
    # eran 2.585 pares con 35 puntos menos por esto, y en las muestras todos estaban bien.
    # Y dentro de la misma marca tampoco es un error cuando los dos se explican entre sí (ver
    # _dos_que_citan_el_mismo_numero()): el capuchón que «monta en bobina 70213» cita el número
    # de la bobina, FISPA vende el mismo sensor común y «(ORIGINAL)», y «70120 (reemplaza a
    # 70181)» es el código nuevo y el viejo.
    ambiguos = set()
    accesorios = {}           # (clave, código del accesorio) -> la relación, para apartarlo
    duenos = {}               # (clave, código de la pieza) -> el accesorio que trajo el número
    choques = {}              # (clave, código) -> (el otro, sus lugares) si es otra pieza
    for k, v in apuntados.items():
        if len(v) < 2:
            continue
        por_submarca = {}
        for cod in v.values():
            por_submarca.setdefault(_submarca_del_codigo(cod), []).append(cod)
        for cods in por_submarca.values():
            if len(cods) < 2 or son_variantes_de_la_misma_pieza(cods):
                continue
            # Primero se apartan los ACCESORIOS o kits que traen la pieza del número —el
            # capuchón que «monta en bobina 70213», el kit de reparación del aforador—: su par
            # con el número no es una equivalencia y se aparta con los kits. Ver
            # _es_accesorio_del_numero(). Va antes de decidir si el grupo se explica: el
            # aforador de BMW lo citan DOS kits de reparación, los dos kits no se explican
            # entre sí, y el grupo quedaba «ambiguo» sin apartar a ninguno.
            for cod in cods:
                relacion = _es_accesorio_del_numero(k[0], cod, descripcion_de.get(cod),
                                                    [(o, descripcion_de.get(o))
                                                     for o in cods if o != cod])
                if relacion:
                    accesorios[(k, cod)] = relacion
            _apartados = [cod for cod in cods if (k, cod) in accesorios]
            _quedan = [cod for cod in cods if (k, cod) not in accesorios]
            sin_explicar = any(
                not _dos_que_citan_el_mismo_numero(_quedan[i], descripcion_de.get(_quedan[i]),
                                                   _quedan[j], descripcion_de.get(_quedan[j]))
                for i in range(len(_quedan)) for j in range(i + 1, len(_quedan)))
            # OTRA PIEZA CON EL MISMO NÚMERO, se expliquen o no. Que las cabezas sean distintas
            # «explica» por qué dos filas citan el número —el microfiltro y el inyector—, pero
            # si las dos lo ponen como SUYO no lo explica: «Junta Salida de Escape PERKINS …
            # (36866416)», «Junta para Cárter PERKINS … (36866416)» y «36866416/70490267
            # ADAPTADOR» no pueden ser las tres esa pieza. Lo que sí explica —uno nombra al
            # otro, la misma pieza en otro material— no se mira.
            for cod in _quedan:
                _otros_ch = [(o, descripcion_de.get(o)) for o in _quedan if o != cod
                             and (_dos_que_citan_el_mismo_numero(
                                      cod, descripcion_de.get(cod), o, descripcion_de.get(o))
                                  or "piezas distintas").startswith("piezas distintas")]
                _choque = _otra_pieza_que_cita_el_numero(descripcion_de.get(cod), _otros_ch)
                if _choque:
                    choques[(k, cod)] = _choque
                    # Y del otro lado también: la regla del sustantivo pide que los dos sean
                    # palabras de pieza y no siempre se cumple mirando desde el otro.
                    choques.setdefault((k, _choque[0]), (cod, _choque[2], _choque[1]))
            if sin_explicar:
                ambiguos.add(k)
                continue
            # Si queda UNA sola pieza que no es accesorio, el número es de ella: el kit de
            # reparación de la bomba cita el número de la bomba. Esa pieza queda respaldada por
            # la fila del kit, como la variante por la fila de origen (ver _variante_del_origen).
            if _apartados and len(_quedan) == 1:
                duenos[(k, _quedan[0])] = _apartados[0]

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
    rubros_oem = rubros_de_los_codigos_de_fabrica()
    patrones_aprendidos = aprender_de_las_decisiones()
    escalas_precio = escalas_de_precio()
    _ya_juzgados = {}   # código -> ¿las reglas de hoy ya no lo tomarían? (ver más abajo)
    ventas_confirman = pares_confirmados_por_ventas()

    limpias, sospechosas, relacionadas = [], [], []
    evaluadas = []
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
            if not _variante and (_clave, _cod_propio) in duenos:
                _variante = (f"El número lo cita «{duenos[(_clave, _cod_propio)]}», que es un "
                             "kit o un accesorio de esta pieza: el número es de esta pieza")
            # Al hermano que es una variante del origen no le corresponde la alarma: que la
            # junta venga en tres espesores no quiere decir que alguno esté mal cargado.
            if (_clave, _cod_propio) in accesorios:
                f["relacion"] = accesorios[(_clave, _cod_propio)]
                relacionadas.append(f)
                continue
            _componente = _numero_de_un_componente(
                oem, _cod_propio, f.get("desc_b") if f["tipo_a"] == "OEM" else f.get("desc_a"))
            if _componente:
                f["relacion"] = _componente
                relacionadas.append(f)
                continue
            # El número en varias filas de la misma lista. Si son la MISMA pieza para otros
            # autos —la junta de escape del Falcon de 4 y de 7 bancadas, la del Escort CHT y la
            # del Renault 9 (el CHT es un motor Renault)— es un número que sirve para varios
            # motores y no hay nada mal cargado. Si alguna es OTRA pieza —la junta de escape, la
            # de tapa de válvulas y la de tapa de cilindros del Mazda con el mismo número, el
            # «block a filtro» con el de la junta de cárter— el número une piezas distintas y
            # aprobarlo las haría equivalentes: rojo, sin saber cuál de las filas es la dueña.
            if not _variante and (_clave, _cod_propio) in choques:
                _otro_ch, _lug_propio, _lug_otro = choques[(_clave, _cod_propio)]
                alarmas.append(f"⚠️ El código {oem} apunta a más de un producto de "
                                f"{marca_otro} — y «{_otro_ch}» es otra pieza "
                                f"({_lug_propio} contra {_lug_otro}): el número uniría piezas "
                                "distintas")
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
            familia_a=rubro_del_codigo_frente_a(rubros_oem, f["a"], f.get("desc_a"),
                                                f.get("desc_b")),
            familia_b=rubro_del_codigo_frente_a(rubros_oem, f["b"], f.get("desc_b"),
                                                f.get("desc_a")),
        )
        for tipo, texto in senales:
            if tipo == "mal" and texto not in alarmas:
                alarmas.append(texto)

        # Las alarmas estructurales (el código no parece un código, un OEM que apunta a dos
        # productos) descuentan fuerte: son problemas de carga, no matices.
        puntaje -= 35 * len([a for a in alarmas if a.startswith(("🚫", "⚠️"))])
        # Los topes por un código dudoso valen hasta el final: la evidencia a favor de más abajo
        # sube el puntaje a 72 o 90, y los pisaba. Con un código de fábrica que no es un código
        # la descripción coincide siempre —el producto de fábrica se crea copiando la de la
        # fila—, así que esa evidencia no dice nada del código.
        _tope_por_el_codigo = 100.0
        # El número de fábrica que la misma lista le pone a piezas distintas: aprobarlo las
        # haría equivalentes, así que no hay evidencia a favor que lo salve.
        if any("es otra pieza (" in a and a.startswith("⚠️") for a in alarmas):
            puntaje = min(puntaje, 15.0)
            _tope_por_el_codigo = 15.0
        # Y un código que parece una medida no se aprueba sin mirar, aunque la descripción
        # coincida entera: «Materiales para junta CORCHO Y GOMA» contra «800MM.X600MM» llegaba
        # a 65 —100 por la descripción igual, menos 35—. Los retenes y o'rings, donde la medida
        # ES el código, ya no llevan esta alarma (ver codigo_sospechoso()).
        # Solo si el código TIENE forma de medida —«700MM.X470MM», «700X470»—: la misma
        # alarma también la llevan números reales como «1920LT» o «E0NN6051CC» de Peugeot y
        # Ford, que terminan en letras que parecen unidades, y esos no hay que frenarlos.
        for _a in alarmas:
            _m = re.search(r"«([^»]+)»", _a) if _a.startswith("🚫") else None
            # («BI0113MM» es un Magneti Marelli: esa marca pega MM al final del código.)
            if _m and re.search(r"\d\s*(MM|CM)\s*[.X]|\d\s*X\s*\d|^\d+\s*(MM|CM)$",
                                _m.group(1).upper()):
                puntaje = min(puntaje, 50.0)
                _tope_por_el_codigo = min(_tope_por_el_codigo, 50.0)
                break

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
                _tope_por_el_codigo = min(_tope_por_el_codigo, 15.0)
                _aviso = (f"🧯 «{_cod}» no es un código de fábrica: es un modelo, una medida o "
                          "un año. Las reglas de hoy ya no lo tomarían. Borralo en Mantenimiento "
                          "→ 🧹 Limpiar y corregir → «Puentes que hoy ya no se generarían»")
                if _aviso not in alarmas:
                    alarmas.append(_aviso)
                break

        # Y el que se levantó del texto del medio en vez de la lista de referencias del final.
        # Ver el_codigo_no_figura_entre_las_referencias(). Era amarillo —«miralo»— y se miraron
        # todos: los ~150 de la cola real eran motores o modelos (OM651.901, 4JB1TC, THD100,
        # 19320E, DEERE1104, FERGUSONMF:165), el número de OTRA pieza (el del turbo en el juego
        # de juntas del turbo) o un número real con la marca pegada adelante («AGCO SISU
        # POWER836120129», «JOHN DEERER43413»). Los primeros son rojo. Los de la marca pegada
        # NO: el número es el de la pieza, mal escrito, igual que los ~130 que la lista escribe
        # así en el lugar de siempre y ya estaban en verde. Se corrigen todos juntos en
        # Mantenimiento (ver codigos_de_fabrica_con_la_marca_pegada()), y el vínculo queda.
        for _lado, _tipo, _otra_desc in (("cod_a", "tipo_a", "desc_b"),
                                          ("cod_b", "tipo_b", "desc_a")):
            if f.get(_tipo) != "OEM":
                continue
            _cod_ref = f.get(_lado) or ""
            if (_cod_ref and not despegar_marca_de_adelante(_cod_ref)
                    and el_codigo_no_figura_entre_las_referencias(_cod_ref,
                                                                  f.get(_otra_desc) or "")):
                puntaje = min(puntaje, 15.0)
                _tope_por_el_codigo = min(_tope_por_el_codigo, 15.0)
                _av_ref = _aviso_codigo_fuera_de_las_referencias(_cod_ref)
                if _av_ref not in alarmas:
                    alarmas.append(_av_ref)
                break

        # Y el cruce de métodos, que es lo que más precisión da: que dos caminos
        # independientes lleguen al mismo par es mucho más fuerte que uno solo. Un VETO —las
        # medidas se contradicen, los rubros no son el mismo— tumba el par sin importar
        # cuántos digan que sí.
        try:
            a_favor, vetos, veredicto = evidencia_cruzada(
                f["a"], f["b"], cuenta_palabras=_cuenta_pal, total_descripciones=_total_desc,
                rubros_oem=rubros_oem)
        except Exception as _err:
            anotar_error("analizar_lote_pendiente", _err)
            a_favor, vetos, veredicto = [], [], ""
        if vetos:
            # EL PRECIO SOLO NO ALCANZA PARA «CASI SEGURO MAL». Revisados a mano los 115 rojos
            # que tenían solo el precio en contra, la mayoría eran piezas distintas —y lo decía
            # el texto con abreviaturas que faltaban leer («AR.LEVA», «INSP.», «RESP CARTER»)—
            # pero había pares que son la misma pieza con un precio raro: «JUNTA SALIDA ESCAPE
            # RASTROJERO» contra la de ILLINOIS del Rastrojero, el juego de compresor Burmor.
            # Con el precio como único veto el par va a revisión; con otro veto, a rojo.
            _solo_precio = all(v.startswith("💲") for v in vetos)
            puntaje = min(puntaje, 45.0 if _solo_precio else 15.0)
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
        elif not a_favor and not _unidos_por_codigo(
                {"tipo": f.get("tipo_a"), "codigo_raw": f.get("cod_a"), "descripcion": f.get("desc_a")},
                {"tipo": f.get("tipo_b"), "codigo_raw": f.get("cod_b"), "descripcion": f.get("desc_b")}):
            # SIN NADA A FAVOR Y SIN UN NÚMERO QUE LOS UNA, no se aprueba solo. Un par entre dos
            # proveedores arranca en 50 y suma 15 por el rubro y 10 por el precio: 75, «limpio»,
            # sin que nada diga que es la misma pieza. Si no los une un código y las
            # descripciones no concuerdan, lo único que se sabe es que son del mismo rubro.
            puntaje = min(puntaje, 50.0)
            if not alarmas and " · " in (veredicto or ""):
                # Las descripciones dicen por qué desconfiar (ver _MOTIVOS_QUE_AVISAN).
                alarmas.append(f"🔤 {veredicto.split(' · ', 1)[1]}")
            elif not alarmas:
                alarmas.append("🤷 Nada dice que sean la misma pieza: no los une ningún código y "
                               "las descripciones no alcanzan para decirlo")
        # EL NÚMERO QUE LA OTRA FILA DECLARA COMO SUYO. El producto de fábrica 5957865 nació de la
        # junta TC-454 de ILLINOIS, y la TC-405 —otra junta de tapa del mismo 128— lo lista entre
        # sus números: «(4309957/5957865/4444452)». Es la misma declaración que dio origen al
        # vínculo de la TC-454, que queda en 100; la TC-405 quedaba en 65 porque su descripción
        # no es la del nodo. Sin ninguna alarma —ni otra pieza con el mismo número, ni precio,
        # ni texto en contra—, es tan firme como el de origen.
        if (not vetos and not alarmas and "OEM" in (f.get("tipo_a"), f.get("tipo_b"))
                and el_codigo_esta_entre_las_referencias(
                    f["cod_a"] if f.get("tipo_a") == "OEM" else f["cod_b"],
                    f.get("desc_b") if f.get("tipo_a") == "OEM" else f.get("desc_a"))):
            puntaje = max(puntaje, 90.0)
            a_favor = a_favor + ["🔢 la otra fila lo lista entre sus números de fábrica"]
        puntaje = min(puntaje, _tope_por_el_codigo)
        f["evidencia"] = a_favor
        f["veredicto"] = veredicto

        # ROJO QUIERE DECIR «CASI SEGURO MAL», y eso lo dice solo una contradicción concreta: el
        # texto (otra pieza, otro motor, otra cilindrada), las medidas, el rubro, un código de
        # fábrica que no lo es. El precio, el abanico o «un código apunta a varios productos»
        # restan, pero juntos podían bajar a rojo un par que el texto no contradice: el juego de
        # juntas del compresor Burmor de TARANTO contra los de ILLINOIS quedaba en rojo por
        # precio y abanico. Sin una contradicción, lo más bajo es revisión.
        _contradiccion = (any(not v.startswith("💲") for v in vetos)
                          or any(a.startswith(("🧯", "🔎 «")) or "es otra pieza (" in a
                                 for a in alarmas))
        if puntaje < 30 and not _contradiccion:
            puntaje = 30.0
        puntaje = max(0.0, min(100.0, puntaje))
        # En revisión y sin ningún aviso, la pantalla no tenía cómo decir por qué: quedaba en
        # «Sin alarma puntual». Casi siempre es esto.
        if puntaje < 55 and not alarmas:
            if _unidos_por_codigo(
                    {"tipo": f.get("tipo_a"), "codigo_raw": f.get("cod_a"),
                     "descripcion": f.get("desc_a")},
                    {"tipo": f.get("tipo_b"), "codigo_raw": f.get("cod_b"),
                     "descripcion": f.get("desc_b")}):
                alarmas.append("🔢 Solo los une el número de fábrica: las descripciones no "
                               "dicen lo mismo, y el número solo no alcanza para aprobarlo "
                               "sin mirar")
            else:
                alarmas.append("🤏 Las descripciones se parecen, pero no alcanza: comparten "
                               "poco más que el nombre de la pieza y el auto")

        f["alarmas"] = alarmas
        f["confianza"] = puntaje
        f["senales"] = senales
        evaluadas.append(f)

    # EL ABANICO: un producto emparejado con muchos productos DISTINTOS de una misma lista. La
    # sonda 80007 de FISPA nombra tantos autos que «concordaba» con 25 sondas distintas de
    # CRI-FA. No pueden estar todas bien: CRI-FA no vende la misma sonda 25 veces, así que como
    # mucho una es la equivalente. Las variantes de una misma pieza no cuentan (la misma junta
    # en tres espesores es legítima, ver son_variantes_de_la_misma_pieza()), ni los códigos de
    # fábrica, que tienen su propio control más arriba.
    # SE MIRA DESPUÉS DE EVALUAR CADA PAR, y solo entre los que no quedaron vetados. Antes se
    # armaba con todos, y los vetados hacían dos daños: aparecían como opción en «Elegí cuál es
    # la equivalente» —la junta de tapa de válvulas del Peugeot 404 contra el juego de
    # carburador, la de cárter y la de diferencial— e inflaban el abanico, así que un producto
    # con UN candidato bueno y cuatro vetados era «un abanico» y el bueno tenía que ganarles.
    # Las listas de distribuidor traen varias marcas: FISPA vende lo suyo y lo de LUCAS. Un
    # candidato de cada marca no compite —son dos fabricantes de la misma pieza—, así que el
    # abanico se arma por marca de adentro de la lista (ver _submarca_del_codigo()).
    _candidatos_ab = {}
    for f in evaluadas:
        if "OEM" in (f.get("tipo_a"), f.get("tipo_b")) or f["confianza"] <= 15:
            continue
        for yo, otro, desc_otro, marca_otro in (
                (f["a"], f["cod_b"], f.get("desc_b"), f.get("marca_b")),
                (f["b"], f["cod_a"], f.get("desc_a"), f.get("marca_a"))):
            _candidatos_ab.setdefault((yo, marca_otro, _submarca_del_codigo(otro)),
                                      set()).add((otro, desc_otro))
    _pieza_ab = {clave: piezas_del_abanico(cands) for clave, cands in _candidatos_ab.items()}
    _abanico = {clave: set(piezas.values()) for clave, piezas in _pieza_ab.items()}
    # Con DOS candidatos distintos también, pero solo para decidir los amarillos: «Jgo.Jtas.
    # Carburador PEUGEOT 404» (TARANTO) concordaba con el juego del Solex C34 y con el del
    # Caresa de ILLINOIS, que son dos juegos distintos, y el texto no dice cuál. Los verdes no
    # se tocan: con el umbral en dos para todos, 871 verdes bajaban y muchos eran la misma junta
    # en otro material (ver PRODUCTOS_DISTINTOS_PARA_ABANICO).
    _en_abanico = {clave for clave, bases in _abanico.items() if len(bases) >= 2}
    _abanico_de_dos = {clave for clave in _en_abanico
                       if len(_abanico[clave]) < PRODUCTOS_DISTINTOS_PARA_ABANICO}
    # Dentro del abanico se queda el que MEJOR coincide —más modelos, motor y cilindrada en
    # común (ver fuerza_de_la_coincidencia())— y los demás van a revisión. La junta de
    # ILLINOIS para la Hilux 2,8 motor 3L estaba emparejada con 11 de TARANTO de otros motores
    # de la Hilux: bajarlas todas era bajar también la buena. Si empatan muchos, como las
    # sondas que nombran veinte autos, no hay a cuál quedarse y van todos.
    _no_es_el_mejor = set()
    if _en_abanico:
        _fuerza_del_par, _pares_del_abanico = {}, {}
        for f in evaluadas:
            if "OEM" in (f.get("tipo_a"), f.get("tipo_b")) or f["confianza"] <= 15:
                continue
            _claves = [k for k in ((f["a"], f.get("marca_b"), _submarca_del_codigo(f["cod_b"])),
                                   (f["b"], f.get("marca_a"), _submarca_del_codigo(f["cod_a"])))
                       if k in _en_abanico]
            if not _claves:
                continue
            _fuerza_del_par[(f["a"], f["b"])] = fuerza_de_la_coincidencia(
                firma_de_producto(f.get("desc_a")), firma_de_producto(f.get("desc_b")))
            for k in _claves:
                _pares_del_abanico.setdefault(k, []).append(f)
        for k, pares_k in _pares_del_abanico.items():
            mejor = max(_fuerza_del_par[(f["a"], f["b"])] for f in pares_k)
            mejores = [f for f in pares_k if _fuerza_del_par[(f["a"], f["b"])] == mejor]
            def _pieza_del_otro(f, k=k):
                otro = ((f["cod_b"], f.get("desc_b")) if f["a"] == k[0]
                        else (f["cod_a"], f.get("desc_a")))
                return _pieza_ab[k].get(otro, otro)
            _bases_mejores = {_pieza_del_otro(f) for f in mejores}
            # Las otras variantes de la pieza que gana —otro espesor, otro material— no son
            # «otro candidato»: se quedan con ella.
            for f in pares_k:
                if k in _abanico_de_dos and f["confianza"] >= 75:
                    continue
                if (_pieza_del_otro(f) not in _bases_mejores
                        or len(_bases_mejores) > MEJORES_EMPATADOS_QUE_SE_ACEPTAN):
                    _no_es_el_mejor.add((f["a"], f["b"]))

    # EL ESPESOR QUE NO SE SABE. «junta tapa cil. Toyota 1kd-ftv» (TARANTO, sin espesor ni
    # muescas) concordaba con las cuatro de ILLINOIS —TC-931-20 1M, 2M, 3M y 4M—, que son la
    # misma junta en cuatro espesores: como mucho una es la suya, y el texto no dice cuál. Se
    # mandan a revisión cuando la otra lista tiene dos o más espesores de esa junta.
    _espesor_desconocido = set()
    _pares_de = {}
    for f in evaluadas:
        _pares_de.setdefault(f["a"], []).append(f)
        _pares_de.setdefault(f["b"], []).append(f)
    for (yo, _marca_otro, _sub), cands in _candidatos_ab.items():
        _con_muescas = {}
        for cod, desc in cands:
            m = re.search(r"[- ](\d)M$", (cod or "").upper().strip())
            if m and "CIL" in (desc or "").upper():
                _con_muescas.setdefault(_pieza_ab[(yo, _marca_otro, _sub)].get((cod, desc)),
                                        set()).add(m.group(1))
        _bases_con_espesores = {b for b, ms in _con_muescas.items() if len(ms) >= 2}
        if not _bases_con_espesores:
            continue
        for f in _pares_de.get(yo, ()):
            lado_yo = "a" if f["a"] == yo else "b"
            lado_otro = "b" if lado_yo == "a" else "a"
            if f.get(f"marca_{lado_otro}") != _marca_otro:
                continue
            _cod_yo = (f.get(f"cod_{lado_yo}") or "").upper().strip()
            _desc_yo = f.get(f"desc_{lado_yo}") or ""
            if (re.search(r"[- ]\d{1}M$", _cod_yo)
                    or re.search(r"(?i)ESP\.?:?\s*\(?\s*\d[.,]\d", _desc_yo)):
                continue
            _clave_otro = (f.get(f"cod_{lado_otro}"), f.get(f"desc_{lado_otro}"))
            if _pieza_ab[(yo, _marca_otro, _sub)].get(_clave_otro) in _bases_con_espesores:
                _espesor_desconocido.add((f["a"], f["b"]))

    # LOS MELLIZOS DE LA OTRA LISTA. «Jgo.Jtas.Carburador FIAT 125» es la descripción de tres
    # productos de TARANTO —250720, 250722 y 250723—, y los tres concordaban con el juego del
    # Solex del 125 de ILLINOIS. Son tres juegos distintos (para otros carburadores del 125) y
    # el texto no dice cuál es: como mucho uno es el equivalente. Solo baja a los amarillos: un
    # verde lo es por algo más que el texto.
    _mellizos = {}            # (a, b) -> los códigos mellizos
    for (yo, _marca_otro, _sub), cands in _candidatos_ab.items():
        _por_texto = {}
        for cod, desc in cands:
            _por_texto.setdefault(_texto_sin_codigos(desc, cod), []).append(cod)
        for _cods in _por_texto.values():
            if len(_cods) >= 2 and not son_variantes_de_la_misma_pieza(_cods):
                for f in _pares_de.get(yo, ()):
                    lado_otro = "b" if f["a"] == yo else "a"
                    if f.get(f"cod_{lado_otro}") in _cods and 55 <= f["confianza"] < 75:
                        _mellizos[(f["a"], f["b"])] = ", ".join(sorted(_cods)[:4])
    for f in evaluadas:
        if (f["a"], f["b"]) in _mellizos:
            f["confianza"] = min(f["confianza"], 50.0)
            f["alarmas"].append(f"🪞 La otra lista tiene varios productos con esta misma "
                                f"descripción ({_mellizos[(f['a'], f['b'])]}) y el texto no dice "
                                "cuál es este")
    for f in evaluadas:
        if (f["a"], f["b"]) in _espesor_desconocido and f["confianza"] > 15:
            f["confianza"] = min(f["confianza"], 50.0)
            f["alarmas"].append("🎚️ No dice el espesor, y la otra lista tiene esta junta en "
                                "varios: como mucho una es la equivalente")
        if (f["a"], f["b"]) in _no_es_el_mejor:
            f["confianza"] = min(f["confianza"], 50.0)
            _cuantos_ab = max(
                len(_abanico.get((f["a"], f.get("marca_b"), _submarca_del_codigo(f["cod_b"])),
                                 ())),
                len(_abanico.get((f["b"], f.get("marca_a"), _submarca_del_codigo(f["cod_a"])),
                                 ())))
            f["alarmas"].append(f"🪭 Uno de los dos está emparejado con {_cuantos_ab} productos "
                                "distintos de la otra lista y este no es el que mejor "
                                "coincide: como mucho uno es el equivalente")
        # El corte lo decide el PUNTAJE, no si hay alguna alarma. Antes bastaba una alarma
        # menor para mandar a revisión un vínculo con toda la evidencia a favor, y así se
        # juntaban cientos de casos que no hacía falta mirar mezclados con los que sí.
        (limpias if f["confianza"] >= 55 else sospechosas).append(f)

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


def rechazar_pendientes(lote, solo_estos_pares=None, motivo=None):
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
    marcar_revision(marcar_para_recordar, "rechazada", motivo)
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

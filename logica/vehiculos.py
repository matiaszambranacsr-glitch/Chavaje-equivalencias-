"""La ficha digital del vehículo y lo que se lee de la patente.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================
# FICHA DIGITAL DEL VEHÍCULO (patente + historial de piezas)
# ============================================================
def get_or_create_vehiculo(patente, cliente_nombre="", cliente_telefono="", marca_auto="", modelo_auto="",
                            km_actual=None, anio="", motorizacion="", vin=""):
    """La ficha del vehículo, nueva o actualizada. Lleva datos del cliente: solo empleados (las
    dos pantallas que la llaman ya lo piden; esto es la segunda barrera, ver exigir_nivel())."""
    exigir_nivel("empleado", "guardar la ficha de un vehículo")
    patente = patente.strip().upper()
    vin = re.sub(r'\s', '', (vin or "").strip().upper())
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
                "vin = COALESCE(NULLIF(?, ''), vin), "
                "anio = COALESCE(NULLIF(?, ''), anio), "
                "motorizacion = COALESCE(NULLIF(?, ''), motorizacion), "
                "km_actual = COALESCE(?, km_actual), "
                "km_registro = COALESCE(km_registro, ?), "  # solo se fija si todavía no tenía uno
                "km_actualizado_fecha = CASE WHEN ? IS NOT NULL THEN datetime('now') ELSE km_actualizado_fecha END "
                "WHERE id = ?",
                (cliente_nombre.strip(), cliente_telefono.strip(), marca_auto.strip(), modelo_auto.strip(),
                 vin, anio.strip(), motorizacion.strip(), km_actual, km_actual, km_actual, vid)
            )
        else:
            c.execute(
                "INSERT INTO vehiculos (patente, cliente_nombre, cliente_telefono, marca_auto, modelo_auto, "
                "vin, anio, motorizacion, km_registro, km_actual, km_actualizado_fecha) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
                (patente, cliente_nombre.strip(), cliente_telefono.strip(), marca_auto.strip(),
                 modelo_auto.strip(), vin, anio.strip(), motorizacion.strip(), km_actual, km_actual)
            )
            c.execute("SELECT id FROM vehiculos WHERE patente = ?", (patente,))
            vid = c.fetchone()["id"]
        conn.commit()
    # Cada ficha cargada con VIN y modelo enseña el patrón sola. Así el mostrador va llenando
    # la tabla de modelos sin que nadie tenga que sentarse a cargarla: al décimo Gol que pasa,
    # el próximo VIN de Gol se autocompleta.
    if len(vin) == 17 and (modelo_auto.strip() or motorizacion.strip()):
        try:
            aprender_modelo_de_vin(vin, modelo_auto, marca_auto, motorizacion)
        except Exception as _err:
            anotar_error("get_or_create_vehiculo", _err)
            pass
    return vid


def guardar_numero_de_motor(patente, numero):
    """El número de motor de la ficha del vehículo. Aparte de get_or_create_vehiculo(), que ya
    tiene nueve parámetros; antes lo escribían a mano las dos pantallas que lo piden (Vehículos y
    la cédula del Modo Mecánico), con el mismo UPDATE copiado y sin mirar el permiso (lo señaló
    una revisión con Gemini: «la lógica, en logica/; las pantallas, solo la interfaz»)."""
    exigir_nivel("empleado", "guardar el número de motor de un vehículo")
    numero, patente = (numero or "").strip(), (patente or "").strip()
    if not numero or not patente:
        return False
    with db_lock:
        c.execute("UPDATE vehiculos SET numero_motor = ? WHERE UPPER(patente) = UPPER(?)",
                  (numero, patente))
        cambio = c.rowcount > 0
        conn.commit()
    return cambio


def enseniar_motor_vin(wmi, codigo, motor, notas=None):
    """Guarda que en esta marca, ese carácter en la 8ª posición del VIN es ese motor."""
    wmi, codigo = wmi.strip().upper(), (codigo or "").strip().upper()[:1]
    if not wmi or not codigo or not (motor or "").strip():
        return False
    with db_lock:
        c.execute("""INSERT INTO motores_vin (wmi, codigo, motor, notas) VALUES (?, ?, ?, ?)
                     ON CONFLICT(wmi, codigo) DO UPDATE SET motor = excluded.motor,
                        notas = excluded.notas, veces = veces + 1""",
                  (wmi, codigo, motor.strip(), (notas or "").strip() or None))
        conn.commit()
    return True


def olvidar_motor_vin(wmi, codigo):
    with db_lock:
        c.execute("DELETE FROM motores_vin WHERE wmi = ? AND codigo = ?",
                  (wmi.strip().upper(), (codigo or "").strip().upper()[:1]))
        conn.commit()
    return c.rowcount


def listar_motores_vin():
    c.execute("""SELECT m.wmi AS "WMI", m.codigo AS "8ª posición", m.motor AS "Motor",
                        COALESCE(f.fabricante, '—') AS "Fabricante", m.veces AS "Visto",
                        m.notas AS "Notas"
                 FROM motores_vin m LEFT JOIN fabricantes_vin f ON f.wmi = m.wmi
                 ORDER BY f.fabricante, m.codigo""")
    return filas_a_listas(c)


def aprender_modelo_de_vin(vin, modelo, marca="", motor=""):
    """Guarda los patrones VIN → modelo y VIN → motor a partir de un dato real.

    Nunca pisa lo que ya esté cargado: si el patrón existe, se respeta (puede haberlo corregido
    una persona a mano, y eso vale más que una deducción automática). Devuelve qué aprendió."""
    vin = re.sub(r'\s', '', (vin or "").strip().upper())
    modelo = (modelo or "").strip()
    motor = (motor or "").strip()
    if len(vin) != 17:
        return {"modelo": False, "motor": False}
    wmi, vds = vin[:3], vin[3:8]
    origen = f"aprendido de una ficha de vehículo{f' ({marca.strip()})' if marca.strip() else ''}"
    aprendido = {"modelo": False, "motor": False}

    # Todo o nada: lo que se aprende de UNA ficha entra junto. Si entra el modelo y no el motor,
    # la próxima vez que aparezca ese VIN ya no se pregunta —el patrón de modelo existe— y el
    # motor no se aprende nunca más.
    with transaccion():
        if modelo:
            c.execute("SELECT 1 FROM modelos_vin WHERE wmi = ? AND vds IN (?, ?, ?)",
                      (wmi, vds, vds[:4], vds[:3]))
            if not c.fetchone():
                with db_lock:
                    c.execute("INSERT OR IGNORE INTO modelos_vin (wmi, vds, modelo, motor, notas) "
                              "VALUES (?, ?, ?, ?, ?)",
                              (wmi, vds, modelo, motor or None, origen))
                aprendido["modelo"] = True

        if motor:
            codigo = vin[7]
            c.execute("SELECT 1 FROM motores_vin WHERE wmi = ? AND codigo = ?", (wmi, codigo))
            if not c.fetchone():
                with db_lock:
                    c.execute("INSERT OR IGNORE INTO motores_vin (wmi, codigo, motor, notas) "
                              "VALUES (?, ?, ?, ?)", (wmi, codigo, motor, origen))
                aprendido["motor"] = True
    return aprendido


def buscar_vehiculo_por_vin(vin):
    """Busca una ficha por número de chasis. Si el auto ya pasó por el mostrador, esto da los
    datos REALES (modelo, año, motor, dueño e historial de piezas), no una estimación."""
    vin = re.sub(r'\s', '', (vin or "").strip().upper())
    if len(vin) != 17:
        return None
    c.execute("SELECT * FROM vehiculos WHERE vin = ?", (vin,))
    row = c.fetchone()
    return dict(row) if row else None


def aprender_modelos_de_fichas_existentes():
    """Recorre las fichas que ya tienen VIN y modelo cargados y arma la tabla de patrones de una.
    Sirve para no perder lo que ya está cargado cuando se estrena esta función."""
    c.execute("""SELECT vin, modelo_auto, marca_auto, motorizacion FROM vehiculos
                 WHERE vin IS NOT NULL AND LENGTH(vin) = 17
                   AND ((modelo_auto IS NOT NULL AND modelo_auto <> '')
                        OR (motorizacion IS NOT NULL AND motorizacion <> ''))""")
    modelos = motores = 0
    for fila in c.fetchall():
        r = aprender_modelo_de_vin(fila["vin"], fila["modelo_auto"] or "",
                                    fila["marca_auto"] or "", fila["motorizacion"] or "")
        modelos += 1 if r["modelo"] else 0
        motores += 1 if r["motor"] else 0
    return modelos, motores


def actualizar_km_registro(vehiculo_id, km_registro):
    """Corrige manualmente el km de registro (por si se cargó mal la primera vez)."""
    with db_lock:
        c.execute("UPDATE vehiculos SET km_registro = ? WHERE id = ?", (km_registro, vehiculo_id))
        conn.commit()


# ============================================================================================
# LA PATENTE ARGENTINA: QUÉ SE PUEDE LEER DE ELLA SIN CONSULTAR NADA
# ============================================================================================
# No existe una base pública y gratuita que traduzca patente a vehículo —las que hay cobran por
# consulta— así que de la patente sola nunca va a salir «Gol 1.6 2012». Pero no es cierto que
# no diga nada: la letra de las patentes viejas dice la PROVINCIA, y la serie dice
# aproximadamente CUÁNDO se patentó, que es justo el dato que el mostrador necesita para filtrar
# un repuesto («¿me das la junta del Corsa? — ¿de qué año?»).

# La letra de las patentes provinciales (las de antes de 1995: una letra y seis números).
# Es la misma codificación de provincias que usan los registros del automotor.
PROVINCIAS_PATENTE = {
    "A": "Salta", "B": "Buenos Aires", "C": "Capital Federal", "D": "San Luis",
    "E": "Entre Ríos", "F": "La Rioja", "G": "Santiago del Estero", "H": "Chaco",
    "J": "San Juan", "K": "Catamarca", "L": "La Pampa", "M": "Mendoza", "N": "Misiones",
    "P": "Formosa", "Q": "Neuquén", "R": "Río Negro", "S": "Santa Fe", "T": "Tucumán",
    "U": "Chubut", "V": "Tierra del Fuego", "W": "Corrientes", "X": "Córdoba",
    "Y": "Jujuy", "Z": "Santa Cruz",
}

# Anclas de la serie vieja (tres letras y tres números, 1995–2016) y de la Mercosur
# (dos letras, tres números, dos letras, desde abril de 2016).
# SON APROXIMADAS y la app lo dice cada vez que las usa. No hay una tabla oficial publicada de
# «qué serie salió qué mes»; lo que sí es seguro es el orden —las series se entregan en orden
# alfabético— así que con unos pocos puntos conocidos se interpola el resto.
# Y lo más importante: estas anclas son el punto de partida. anio_probable_de_patente() usa
# ADEMÁS las fichas del propio taller, donde cada auto cargado con patente y año es un dato
# exacto de esta zona y de este parque. Con treinta fichas cargadas, la estimación deja de
# depender de esta tabla.
ANCLAS_PATENTE_VIEJA = [("AAA", 1995), ("CAA", 1999), ("DZZ", 2002), ("FAA", 2006),
                        ("IAA", 2010), ("KAA", 2012), ("MAA", 2013), ("OAA", 2015),
                        ("PZZ", 2016)]
ANCLAS_PATENTE_MERCOSUR = [("AA", 2016), ("AC", 2018), ("AE", 2020), ("AF", 2021),
                           ("AG", 2022), ("AH", 2023), ("AJ", 2024), ("AK", 2025)]

_RE_PATENTE_VIEJA = re.compile(r'^([A-Z]{3})(\d{3})$')
_RE_PATENTE_MERCOSUR = re.compile(r'^([A-Z]{2})(\d{3})([A-Z]{2})$')
_RE_PATENTE_MOTO_MERCOSUR = re.compile(r'^([A-Z])(\d{3})([A-Z]{3})$')
_RE_PATENTE_MOTO_VIEJA = re.compile(r'^(\d{3})([A-Z]{3})$')
_RE_PATENTE_PROVINCIAL = re.compile(r'^([A-Z])(\d{6})$')


def _orden_de_letras(letras):
    """El número de orden de una serie de letras: AAA es 0, AAB es 1, ABA es 26…"""
    n = 0
    for ch in letras:
        n = n * 26 + (ord(ch) - 65)
    return n


def _anio_por_anclas(letras, anclas):
    """Interpola el año entre las anclas conocidas. Devuelve (año, es_extrapolado)."""
    x = _orden_de_letras(letras)
    puntos = sorted((_orden_de_letras(s), a) for s, a in anclas)
    if x <= puntos[0][0]:
        return puntos[0][1], x < puntos[0][0]
    if x >= puntos[-1][0]:
        return puntos[-1][1], x > puntos[-1][0]
    for (x0, a0), (x1, a1) in zip(puntos, puntos[1:]):
        if x0 <= x <= x1:
            if x1 == x0:
                return a0, False
            return int(round(a0 + (a1 - a0) * (x - x0) / (x1 - x0))), False
    return puntos[-1][1], True


def leer_patente(texto):
    """Qué se puede saber de una patente argentina sin consultar ninguna base.

    Devuelve siempre un diccionario; 'formato' es None cuando no se reconoce. El año va como
    RANGO y con el aviso de que es aproximado: sirve para filtrar el catálogo, no para
    afirmar de qué año es el auto."""
    pat = re.sub(r'[^A-Z0-9]', '', (texto or "").upper())
    salida = {"patente": pat, "formato": None, "provincia": None, "vehiculo": None,
              "anio_desde": None, "anio_hasta": None, "detalle": ""}
    if not pat:
        return salida

    m = _RE_PATENTE_MERCOSUR.match(pat)
    if m:
        anio, fuera = _anio_por_anclas(m.group(1), ANCLAS_PATENTE_MERCOSUR)
        salida.update(formato="mercosur", vehiculo="auto", anio_desde=anio - 1,
                      anio_hasta=anio + 1,
                      detalle="patente Mercosur (se entregan desde abril de 2016)")
        return salida

    m = _RE_PATENTE_MOTO_MERCOSUR.match(pat)
    if m:
        salida.update(formato="mercosur", vehiculo="moto", anio_desde=2016,
                      anio_hasta=datetime.now().year,
                      detalle="patente Mercosur de moto (desde abril de 2016)")
        return salida

    m = _RE_PATENTE_VIEJA.match(pat)
    if m:
        anio, _fuera = _anio_por_anclas(m.group(1), ANCLAS_PATENTE_VIEJA)
        # El rango se recorta a los años en que existió este formato: la primera serie salió
        # en 1995 y la última en marzo de 2016, así que no tiene sentido ofrecer 1993 ni 2018.
        salida.update(formato="vieja", vehiculo="auto", anio_desde=max(anio - 2, 1995),
                      anio_hasta=min(anio + 2, 2016),
                      detalle="patente vieja de tres letras (1995 a marzo de 2016)")
        return salida

    m = _RE_PATENTE_MOTO_VIEJA.match(pat)
    if m:
        salida.update(formato="vieja", vehiculo="moto", anio_desde=1995, anio_hasta=2016,
                      detalle="patente vieja de moto (números y letras)")
        return salida

    m = _RE_PATENTE_PROVINCIAL.match(pat)
    if m:
        salida.update(formato="provincial", vehiculo="auto", anio_hasta=1994,
                      provincia=PROVINCIAS_PATENTE.get(m.group(1)),
                      detalle="patente provincial: se entregaron hasta 1994")
        return salida
    return salida


def anio_probable_de_patente(patente):
    """El año estimado de una patente, corregido con las fichas del propio taller.

    Las anclas de arriba son de todo el país y aproximadas. Las fichas cargadas acá no: cada
    auto con patente Y año es un punto exacto. Se buscan el más cercano por debajo y el más
    cercano por arriba EN LA MISMA FAMILIA de patente y se interpola entre esos dos, que es
    mucho mejor que la tabla general — y mejora sola a medida que se cargan fichas.

    Devuelve (desde, hasta, de_dónde_salió) o (None, None, '') si no se reconoce la patente."""
    lectura = leer_patente(patente)
    if not lectura["formato"] or lectura["formato"] == "provincial":
        return lectura["anio_desde"], lectura["anio_hasta"], lectura["detalle"]

    pat = lectura["patente"]
    letras = (_RE_PATENTE_MERCOSUR.match(pat) or _RE_PATENTE_VIEJA.match(pat))
    if not letras:
        return lectura["anio_desde"], lectura["anio_hasta"], lectura["detalle"]
    letras = letras.group(1)
    largo = len(letras)

    try:
        c.execute("""SELECT patente, anio FROM vehiculos
                     WHERE anio IS NOT NULL AND TRIM(anio) <> '' AND LENGTH(patente) >= 6""")
        fichas = c.fetchall()
    except sqlite3.OperationalError as _err:
        anotar_error("anio_probable_de_patente", _err)
        fichas = []

    propios = []
    for f in fichas:
        otra = re.sub(r'[^A-Z0-9]', '', (f["patente"] or "").upper())
        if leer_patente(otra)["formato"] != lectura["formato"]:
            continue
        m2 = (_RE_PATENTE_MERCOSUR.match(otra) or _RE_PATENTE_VIEJA.match(otra))
        if not m2 or len(m2.group(1)) != largo:
            continue
        try:
            anio_ficha = int(str(f["anio"])[:4])
        except (TypeError, ValueError):
            continue
        if 1960 <= anio_ficha <= datetime.now().year + 1:
            propios.append((m2.group(1), anio_ficha))

    if len(propios) >= 2:
        anio, _fuera = _anio_por_anclas(letras, propios)
        piso, techo = ((2016, datetime.now().year) if lectura["formato"] == "mercosur"
                       else (1995, 2016))
        return (max(anio - 1, piso), min(anio + 1, techo),
                f"estimado con las {len(propios)} fichas que tenés cargadas con patente y año")

    anclas = (ANCLAS_PATENTE_MERCOSUR if lectura["formato"] == "mercosur"
              else ANCLAS_PATENTE_VIEJA)
    anio, _fuera = _anio_por_anclas(letras, anclas)
    margen = 1 if lectura["formato"] == "mercosur" else 2
    piso, techo = ((2016, datetime.now().year) if lectura["formato"] == "mercosur"
                   else (1995, 2016))
    return (max(anio - margen, piso), min(anio + margen, techo),
            "estimado por la serie de la patente (aproximado: las series se entregan en orden)")


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
        except (ValueError, TypeError) as _err:
            anotar_error("calcular_km_recorridos", _err)
            pass
    return resultado


def producto_del_codigo_anotado(codigo, marca=""):
    """(id, marca) del producto del catálogo que es ese código, o (None, '') si no está o no se
    sabe cuál es: con la marca escrita tiene que ser de esa marca; sin marca, tiene que haber
    uno solo con ese código."""
    limpio = sanitizar(codigo or "")
    if not limpio:
        return None, ""
    c.execute("""SELECT p.id, m.nombre FROM productos p JOIN marcas m ON m.id = p.marca_id
                 WHERE p.codigo_clean = ?""", (limpio,))
    filas = c.fetchall()
    if (marca or "").strip():
        filas = [f for f in filas if normalizar_texto(f["nombre"]) == normalizar_texto(marca)]
    return (filas[0]["id"], filas[0]["nombre"]) if len(filas) == 1 else (None, "")


def vida_util_de_las_otras_veces(descripcion, vehiculo_id=None):
    """La vida útil que se anotó otras veces para esa pieza, o None: la última de este auto, y
    si no, la que más se usó en los demás. Así una pieza anotada sin vida útil igual dice
    cuánto le falta."""
    clave = " ".join(str(descripcion or "").upper().split())
    if not clave:
        return None
    c.execute("""SELECT descripcion_pieza, vida_util_km, vehiculo_id FROM historial_piezas
                 WHERE vida_util_km > 0 ORDER BY id DESC LIMIT 20000""")
    de_este, de_otros = None, {}
    for f in c.fetchall():
        if " ".join((f["descripcion_pieza"] or "").upper().split()) != clave:
            continue
        if vehiculo_id is not None and f["vehiculo_id"] == vehiculo_id:
            de_este = de_este or f["vida_util_km"]
        else:
            de_otros[f["vida_util_km"]] = de_otros.get(f["vida_util_km"], 0) + 1
    if de_este:
        return de_este
    # La que más se usó; si empatan, la más reciente (el diccionario guarda el orden, y el
    # orden es del más nuevo al más viejo).
    return max(de_otros, key=lambda v: de_otros[v]) if de_otros else None


def agregar_pieza_historial(vehiculo_id, descripcion, marca_pieza, codigo_pieza, km_instalacion, vida_util_km, nota):
    """Anota una pieza en la ficha del auto. Devuelve {"producto_id", "marca", "vida_util",
    "vida_de_otras_veces"} con lo que completó solo.

    LA PIEZA QUEDA ATADA AL CATÁLOGO si el código está y no hay duda de cuál es (ver
    producto_del_codigo_anotado()). Nunca se guardaba el producto: la columna estaba, y la
    usan el precio y el stock de hoy en «Por patente», lo que se le puso a los autos con el
    mismo motor y los autos de cada producto en su evidencia, que así no veían nada de lo que
    el taller instaló."""
    exigir_nivel("empleado", "anotar una pieza en la ficha de un vehículo")
    producto_id, marca_del_catalogo = producto_del_codigo_anotado(codigo_pieza, marca_pieza)
    marca_pieza = marca_pieza.strip() or marca_del_catalogo
    vida_de_otras_veces = False
    if not vida_util_km:
        vida_util_km = vida_util_de_las_otras_veces(descripcion, vehiculo_id)
        vida_de_otras_veces = bool(vida_util_km)
    with db_lock:
        c.execute(
            "INSERT INTO historial_piezas (vehiculo_id, producto_id, descripcion_pieza, marca_pieza, "
            "codigo_pieza, km_instalacion, vida_util_km, nota) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (vehiculo_id, producto_id, descripcion.strip(), marca_pieza, codigo_pieza.strip(),
             km_instalacion, vida_util_km, nota.strip())
        )
        conn.commit()
    return {"producto_id": producto_id, "marca": marca_pieza, "vida_util": vida_util_km,
            "vida_de_otras_veces": vida_de_otras_veces}


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


def _fecha_de(texto):
    try:
        return datetime.strptime(str(texto or "")[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(str(texto or "")[:10], "%Y-%m-%d")
        except ValueError:
            return None


def km_estimado_hoy(vehiculo):
    """(km de hoy estimado, km por día). El km anotado es el de la última vez que el auto pasó
    por el local; si anda 40 km por día y pasaron tres meses, hoy tiene 3.600 más. El ritmo sale
    de lo que anduvo entre que se cargó la ficha y la última vez que se anotó el km. Sin eso,
    (km anotado, None)."""
    km_reg, km_act = vehiculo.get("km_registro"), vehiculo.get("km_actual")
    if km_act is None:
        return None, None
    desde = _fecha_de(vehiculo.get("created_at"))
    hasta = _fecha_de(vehiculo.get("km_actualizado_fecha")) or desde
    if km_reg is None or not desde or not hasta or km_act <= km_reg:
        return km_act, None
    dias = (hasta - desde).days
    if dias < 7:
        return km_act, None       # con días sueltos el ritmo es cualquier cosa
    por_dia = (km_act - km_reg) / dias
    return round(km_act + por_dia * max((datetime.now() - hasta).days, 0)), por_dia


def estado_de_cada_pieza(vehiculo, dias_de_aviso=30, km_hoy=None):
    """Cuánto le falta a cada pieza del auto, una fila por pieza. [dict], lo más urgente primero.

    Mira la ÚLTIMA vez que se cambió cada pieza (la de más km: no cuántas veces —si el filtro se
    cambió hace 2.000 km no está atrasado aunque en total se haya cambiado pocas veces—), y el km
    de hoy estimado con el ritmo de ese auto (ver km_estimado_hoy()). Si esa última vez no se
    anotó la vida útil, vale la de la vez anterior: es la misma pieza. Es la misma cuenta para
    el negocio (a_quien_avisar()) y para el cliente (resumen_publico_del_auto()).

    «Le toca pronto» es dentro de `dias_de_aviso` días al ritmo del auto, o sin ritmo conocido,
    a menos del 15% de su vida útil. Con km_hoy, la cuenta va con ese y no con el estimado."""
    km_estimado, por_dia = km_estimado_hoy(vehiculo)
    km_hoy = km_estimado if km_hoy is None else km_hoy
    c.execute("""SELECT descripcion_pieza, marca_pieza, codigo_pieza, km_instalacion,
                        vida_util_km, fecha_instalacion
                 FROM historial_piezas WHERE vehiculo_id = ?
                 ORDER BY km_instalacion IS NULL, km_instalacion DESC, id DESC""",
              (vehiculo["id"],))
    por_pieza = {}
    for fila in c.fetchall():
        clave = " ".join((fila["descripcion_pieza"] or "").upper().split())
        if clave not in por_pieza:
            por_pieza[clave] = {"ultima": fila, "vida": None}
        if por_pieza[clave]["vida"] is None and (fila["vida_util_km"] or 0) > 0:
            por_pieza[clave]["vida"] = fila["vida_util_km"]
    salida = []
    for datos in por_pieza.values():
        p, vida = datos["ultima"], datos["vida"]
        km_inst = p["km_instalacion"]
        fila = {"Pieza": p["descripcion_pieza"], "Marca": p["marca_pieza"] or "",
                "Código": p["codigo_pieza"] or "", "Km al cambiarla": km_inst,
                "Cuándo": str(p["fecha_instalacion"] or "")[:10], "Vida útil (km)": vida,
                "_faltan": None, "_dias": None, "_margen": None}
        if km_hoy is None or km_inst is None or not vida:
            fila["Estado"] = "⚪ Sin datos"
            fila["Le falta"] = ("falta la vida útil" if not vida else
                                "falta el km del auto" if km_hoy is None else
                                "falta el km al cambiarla")
            salida.append(fila)
            continue
        faltan = km_inst + vida - km_hoy
        margen = (por_dia * dias_de_aviso) if por_dia else 0.15 * vida
        fila["_faltan"], fila["_margen"] = faltan, margen
        if por_dia and faltan > 0:
            fila["_dias"] = max(round(faltan / por_dia), 1)
        if faltan <= 0:
            fila["Estado"] = "🔴 Ya le toca"
            fila["Le falta"] = f"ya pasó {miles(-faltan)} km"
        else:
            fila["Estado"] = "🟡 Le toca pronto" if faltan <= margen else "🟢 Bien"
            fila["Le falta"] = (f"{miles(faltan)} km" + (f" (unos {fila['_dias']} días)"
                                                         if fila["_dias"] else ""))
        salida.append(fila)
    salida.sort(key=lambda x: (x["_faltan"] is None, x["_faltan"] if x["_faltan"] is not None else 0))
    return salida


def a_quien_avisar(dias_de_aviso=30, limite=100):
    """Los clientes a los que ya les toca —o les va a tocar en `dias_de_aviso` días— cambiar una
    pieza, con el mensaje de WhatsApp armado. [dict]. La cuenta de cada pieza es la de
    estado_de_cada_pieza()."""
    c.execute("""SELECT id, patente, cliente_nombre, cliente_telefono, marca_auto, modelo_auto,
                        km_registro, km_actual, km_actualizado_fecha, created_at FROM vehiculos
                 WHERE km_actual IS NOT NULL""")
    vehiculos = [dict(r) for r in c.fetchall()]
    salida = []
    for v in vehiculos:
        km_hoy, por_dia = km_estimado_hoy(v)
        if km_hoy is None:
            continue
        for p in estado_de_cada_pieza(v, dias_de_aviso):
            faltan_km = p["_faltan"]
            if faltan_km is None or faltan_km > p["_margen"]:
                continue
            if faltan_km <= 0:
                cuando = f"ya pasó {miles(-faltan_km)} km"
            elif p["_dias"]:
                cuando = f"en unos {p['_dias']} días"
            else:
                cuando = f"en {miles(faltan_km)} km"
            auto = f"{v.get('marca_auto') or ''} {v.get('modelo_auto') or ''}".strip()
            # Con el link de su auto: ahí ve qué le toca y cuánto le falta a lo demás.
            mensaje = (f"Hola {v.get('cliente_nombre') or ''}! Te escribimos de El Chavo. "
                       f"Según el kilometraje de tu {auto} ({v['patente']}), le toca cambiar: "
                       f"{p['Pieza']}. ¿Coordinamos? Acá ves cuánto le falta a cada cosa: "
                       f"{link_publico_del_auto(v['id'])}").replace("Hola !", "Hola!")
            tel = re.sub(r"\D", "", v.get("cliente_telefono") or "")
            salida.append({
                "Patente": v["patente"], "Cliente": v.get("cliente_nombre") or "",
                "Auto": auto, "Pieza": p["Pieza"],
                "Código": p["Código"], "Le toca": cuando,
                "Km hoy (estimado)": km_hoy, "_faltan": faltan_km,
                "_whatsapp": (f"https://wa.me/{tel}" if tel else "https://wa.me/")
                             + "?text=" + quote(mensaje),
                "_vehiculo": v["patente"]})
    salida.sort(key=lambda x: x["_faltan"])
    return salida[:limite]


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
# LO QUE VE EL CLIENTE DE SU AUTO (sin entrar a la app)
# ============================================================
# Con el link, el cliente ve qué se le puso a su auto y cuánto le falta a cada cosa, sin entrar
# ni ver nada más del negocio. La patente sola no alcanza: se lee en la calle, y con ella
# cualquiera vería el km y los arreglos del auto de otro. Hace falta además una de dos cosas:
#   · la clave de la ficha, que viaja adentro del link que le manda el negocio (por WhatsApp o
#     en el QR de la ficha en PDF): con el link se entra directo;
#   · o, sin el link, los últimos 4 números del teléfono que dejó en la ficha.
# Nunca se muestra el nombre ni el teléfono, ni las notas internas del historial. Con la patente
# y 4 números hay 10.000 combinaciones: por eso los intentos fallidos tienen tope, por patente y
# en total, y la respuesta no dice si la patente existe o no. El tope es solo para los 4
# números: la clave del link tiene 32^10 combinaciones y no se adivina, y si contara, cualquiera
# que fallara 5 veces con una patente le dejaba el link sin andar al dueño del auto.
URL_DE_LA_APP = "https://equivalenciasdelchavo.streamlit.app/"   # la de .github/despertar_la_app.py
INTENTOS_FALLIDOS_POR_PATENTE_POR_DIA = 5
INTENTOS_FALLIDOS_EN_TOTAL_POR_HORA = 60
_LETRAS_DE_LA_CLAVE = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # sin 0/O ni 1/I: se pueden dictar
LARGO_DE_LA_CLAVE = 10
NO_SE_PUDO_ABRIR_LA_FICHA = ("No encontramos un auto con esos datos. Revisá la patente y los "
                             "números, o pedile el link al negocio.")


def problema_del_whatsapp_del_negocio(numero):
    """'' si está bien o vacío; si no, qué tiene. wa.me lo quiere con el 54 del país y el 9 de
    los celulares, sin el 0 de la característica ni el 15: 54 9 11 4567 8901."""
    digitos = re.sub(r"\D", "", str(numero or ""))
    if not digitos:
        return ""
    if not digitos.startswith("549"):
        return "tiene que empezar con 549 (el 54 del país y el 9 de los celulares)"
    if len(digitos) != 13:
        return f"después del 549 van 10 números (característica sin 0 y número sin 15), y hay {len(digitos) - 3}"
    return ""


def patente_sin_espacios(texto):
    return re.sub(r"[^A-Z0-9]", "", str(texto or "").upper())


def _vehiculos_por_patente_sin_espacios(patente):
    """Las fichas de esa patente, escrita como sea: «AB 123 CD» y «AB123CD» pueden ser dos."""
    c.execute("""SELECT * FROM vehiculos
                 WHERE REPLACE(REPLACE(REPLACE(UPPER(patente), ' ', ''), '-', ''), '.', '') = ?
                 ORDER BY id""",
              (patente_sin_espacios(patente),))
    return [dict(fila) for fila in c.fetchall()]


def link_publico_del_auto(vehiculo_id, nueva=False):
    """El link para que el cliente vea su auto. La clave se crea la primera vez; con nueva=True
    se cambia, y el link anterior deja de andar (si se lo mandaron a quien no era)."""
    import secrets as _azar
    exigir_nivel("empleado", "armar el link de la ficha para el cliente")
    with db_lock:
        c.execute("SELECT patente, clave_publica FROM vehiculos WHERE id = ?", (vehiculo_id,))
        fila = c.fetchone()
        if not fila:
            return ""
        clave = fila["clave_publica"]
        if nueva or not clave:
            clave = "".join(_azar.choice(_LETRAS_DE_LA_CLAVE) for _ in range(LARGO_DE_LA_CLAVE))
            c.execute("UPDATE vehiculos SET clave_publica = ? WHERE id = ?", (clave, vehiculo_id))
            conn.commit()
    return (link_general_de_consulta() + quote(patente_sin_espacios(fila["patente"]))
            + f"&clave={quote(clave)}")


def link_general_de_consulta():
    """El link sin patente ni clave: pide la patente y los 4 números. Para un cartel o un QR en
    el mostrador."""
    base = obtener_config("url_de_la_app", URL_DE_LA_APP).strip() or URL_DE_LA_APP
    return base.rstrip("/") + "/?auto="


def _demasiados_intentos(patente):
    c.execute("""SELECT
                   SUM(CASE WHEN patente = ? AND cuando > datetime('now', '-1 day') THEN 1 ELSE 0 END),
                   SUM(CASE WHEN cuando > datetime('now', '-1 hour') THEN 1 ELSE 0 END)
                 FROM intentos_consulta_publica""", (patente,))
    de_esta, en_total = c.fetchone()
    return ((de_esta or 0) >= INTENTOS_FALLIDOS_POR_PATENTE_POR_DIA
            or (en_total or 0) >= INTENTOS_FALLIDOS_EN_TOTAL_POR_HORA)


def _anotar_intento_fallido(patente):
    with db_lock:
        c.execute("INSERT INTO intentos_consulta_publica (patente) VALUES (?)", (patente,))
        c.execute("DELETE FROM intentos_consulta_publica WHERE cuando < datetime('now', '-2 days')")
        conn.commit()


def abrir_ficha_publica(patente, clave="", ultimos_del_telefono="", km_de_hoy=None):
    """(resumen, motivo): el resumen de resumen_publico_del_auto() si los datos coinciden, o
    None y qué decirle al cliente. Ver «LO QUE VE EL CLIENTE DE SU AUTO».

    Con la clave del link, o con los últimos 4 números del teléfono de la ficha. La respuesta es
    la misma si la patente no existe o si los números no coinciden: así no sirve para averiguar
    qué autos pasaron por el negocio. km_de_hoy: ver resumen_publico_del_auto()."""
    pat = patente_sin_espacios(patente)
    clave = str(clave or "").strip().upper()
    ultimos = re.sub(r"\D", "", str(ultimos_del_telefono or ""))
    if len(pat) < 5:
        return None, "Escribí la patente completa."
    if not clave and len(ultimos) != 4:
        return None, "Escribí los últimos 4 números del teléfono que dejaste en el negocio."
    if not clave and _demasiados_intentos(pat):
        return None, ("Hubo demasiados intentos con datos que no coinciden. Probá mañana, o "
                      "pedile el link al negocio.")
    coincide = None
    for v in _vehiculos_por_patente_sin_espacios(pat):
        if clave:
            if v.get("clave_publica") and hmac.compare_digest(
                    clave.encode(), str(v["clave_publica"]).upper().encode()):
                coincide = v
        else:
            tel = re.sub(r"\D", "", v.get("cliente_telefono") or "")
            # Con menos de 6 números el teléfono es casi todo «los últimos 4»: no alcanza para
            # saber que es el dueño. Ese auto entra solo con el link.
            if len(tel) >= 6 and hmac.compare_digest(ultimos.encode(), tel[-4:].encode()):
                coincide = v
    if not coincide:
        if not clave:
            try:
                _anotar_intento_fallido(pat)
            except sqlite3.Error as _err:
                anotar_error("abrir_ficha_publica", _err)
        return None, NO_SE_PUDO_ABRIR_LA_FICHA
    return resumen_publico_del_auto(coincide, km_de_hoy), ""


def resumen_publico_del_auto(vehiculo, km_de_hoy=None):
    """Lo que ve el cliente de su auto: el auto, el km, cuánto le falta a cada pieza, lo próximo
    que le toca y todo lo que se le puso. Sin nombre, teléfono, notas ni ids.

    km_de_hoy es el que el cliente lee en el tablero: la cuenta se hace con ese en vez del
    estimado, y NO se guarda —lo escribe cualquiera con el link—. Menor que el anotado en el
    negocio no puede ser: se ignora y lo dice «km_de_hoy_no_va»."""
    km_hoy, por_dia = km_estimado_hoy(vehiculo)
    km_de_hoy_no_va = ""
    if km_de_hoy is not None:
        if vehiculo.get("km_actual") is not None and km_de_hoy < vehiculo["km_actual"]:
            km_de_hoy_no_va = (f"Es menos que el que anotamos la última vez "
                               f"({miles(vehiculo['km_actual'])} km): la cuenta va con el nuestro.")
            km_de_hoy = None
    auto = " ".join(x for x in (vehiculo.get("marca_auto"), vehiculo.get("modelo_auto"),
                                 vehiculo.get("anio"), vehiculo.get("motorizacion"))
                    if (x or "").strip())
    estado = estado_de_cada_pieza(vehiculo, km_hoy=km_de_hoy)
    proximo = next(({"Pieza": p["Pieza"], "Estado": p["Estado"], "Le falta": p["Le falta"]}
                    for p in estado if p["_faltan"] is not None), None)
    piezas = [{k: v for k, v in p.items() if not k.startswith("_")} for p in estado]
    for p in piezas:
        p["Cuándo"] = _dia_mes_anio(p["Cuándo"])
        p["Km al cambiarla"] = miles(p["Km al cambiarla"]) if p["Km al cambiarla"] is not None else ""
        p["Vida útil (km)"] = miles(p["Vida útil (km)"]) if p["Vida útil (km)"] else ""
    c.execute("""SELECT fecha_instalacion, descripcion_pieza, marca_pieza, codigo_pieza,
                        km_instalacion
                 FROM historial_piezas WHERE vehiculo_id = ?
                 ORDER BY fecha_instalacion DESC, id DESC""", (vehiculo["id"],))
    historial = [{"Fecha": _dia_mes_anio(h["fecha_instalacion"]), "Pieza": h["descripcion_pieza"],
                  "Marca": h["marca_pieza"] or "", "Código": h["codigo_pieza"] or "",
                  "Km": miles(h["km_instalacion"]) if h["km_instalacion"] is not None else ""}
                 for h in c.fetchall()]
    return {
        "patente": vehiculo["patente"], "auto": auto,
        "km_anotado": vehiculo.get("km_actual"),
        "km_anotado_el": _dia_mes_anio(vehiculo.get("km_actualizado_fecha")),
        "km_hoy": km_de_hoy if km_de_hoy is not None else km_hoy, "km_por_dia": por_dia,
        "km_del_cliente": km_de_hoy is not None, "km_de_hoy_no_va": km_de_hoy_no_va,
        "proximo": proximo, "piezas": piezas, "historial": historial,
        "le_toca": [p["Pieza"] for p in piezas if p["Estado"][:1] in ("🔴", "🟡")],
    }


def _dia_mes_anio(texto):
    fecha = _fecha_de(texto)
    return f"{fecha:%d/%m/%Y}" if fecha else ""

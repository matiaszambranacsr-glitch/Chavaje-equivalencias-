"""La ficha digital del vehículo y lo que se lee de la patente.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================
# FICHA DIGITAL DEL VEHÍCULO (patente + historial de piezas)
# ============================================================
def get_or_create_vehiculo(patente, cliente_nombre="", cliente_telefono="", marca_auto="", modelo_auto="",
                            km_actual=None, anio="", motorizacion="", vin=""):
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

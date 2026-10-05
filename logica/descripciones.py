"""Leer las descripciones: años, modelos, familias de repuesto y catálogos de aplicaciones.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================================================
# AÑOS, MODELOS Y FAMILIAS DE REPUESTO
# ============================================================================================
def extraer_anios(descripcion):
    """Saca el rango de años de una descripción. Las listas los escriben de varias formas:
    '1969/78' (1969 a 1978), '1998/...' (1998 en adelante), '2005' (solo ese año).
    Devuelve (desde, hasta) — hasta=None significa 'en adelante'."""
    if not descripcion:
        return None, None
    texto = str(descripcion)
    # Rango con dos años: 1969/78, 1974/1981, 2005/09, y también 1998-2006 y 1998 al 2006.
    # El guion faltaba y es la forma más usada en algunas listas: sobre los archivos reales son
    # 1.116 filas (331 en una, 778 en otra). Sin él, «GOL 1998-2006» se leía como el año 1998
    # solo, así que filtrar por 2003 ESCONDÍA un repuesto que sirve. Un filtro que oculta lo que
    # corresponde es peor que no tener filtro: el de adelante no se entera de que hay stock.
    m = re.search(r'\b(19\d{2}|20\d{2})\s*(?:[/\-–—]|\s+AL?\s+)\s*(\d{2}|\d{4})\b',
                  texto, re.IGNORECASE)
    if m:
        desde = int(m.group(1))
        fin = m.group(2)
        hasta = int(fin) if len(fin) == 4 else int(str(desde)[:2] + fin)
        if hasta < desde:            # 1998/02 significa 1998 a 2002
            hasta += 100
        return desde, hasta
    # Año en adelante: 1998/... o 1998/…
    m = re.search(r'\b(19\d{2}|20\d{2})\s*/\s*\.{2,}', texto)
    if m:
        return int(m.group(1)), None
    # Un año suelto
    m = re.search(r'\b(19\d{2}|20\d{2})\b', texto)
    if m:
        return int(m.group(1)), int(m.group(1))
    return None, None


# Un RANGO de años escrito como rango: «1969/78», «1998/2006», «1998-2006», «1998 al 2006»,
# «2013/...», «2005>». El año suelto no entra a propósito: «J.DEERE 2030» es un tractor y
# «TRANSIT 2000» puede ser el motor. Ver rangos_de_anios().
_RE_RANGO_DE_ANIOS = re.compile(
    r"\b(19[5-9]\d|20[0-3]\d)\s*(?:(?:[/\-–—]|\s+AL?\s+)\s*(\d{2}|\d{4})\b"
    r"|/\s*(?:\.{2,}|…|>)|\s*>)", re.IGNORECASE)


def rangos_de_anios(descripcion):
    """TODOS los rangos de años que escribe una descripción, como tupla de (desde, hasta).
    «En adelante» es hasta 2100. A diferencia de extraer_anios(), que se queda con el primero,
    acá hacen falta todos: «HYUNDAI TRAJET 2000/2004 SONATA EF 2001/2004» son dos autos, y
    comparar contra uno solo tumbaría pares que coinciden en el otro."""
    salida = []
    for m in _RE_RANGO_DE_ANIOS.finditer(str(descripcion or "")):
        desde, fin = int(m.group(1)), m.group(2)
        if fin:
            hasta = int(fin) if len(fin) == 4 else int(str(desde)[:2] + fin)
            if hasta < desde:            # 1998/02 es 1998 a 2002
                hasta += 100
            if hasta - desde > 40:       # no es un rango de años: un código o una medida
                continue
        else:
            hasta = 2100
        salida.append((desde, hasta))
    # Y como los escribe FISPA, con dos cifras y un espacio antes del guion: «FOCUS 2 0L MFI
    # 05 -11 RANGER 2 3L MFI 01 -06», «XSARA 1 4 1 6 96 -06». Medido sobre el catálogo real, esa
    # forma es siempre un rango de años. Sin ella, un termostato de Transit 2016/2022 concordaba
    # con el de Focus 2005-2011. «03-97» sin el espacio no entra: es mes y año.
    for _d, _h in _RE_ANIOS_DE_DOS_CIFRAS.findall(str(descripcion or "")):
        desde = int(_d) + (1900 if int(_d) >= 50 else 2000)
        hasta = int(_h) + (1900 if int(_h) >= 50 else 2000)
        if desde <= hasta <= desde + 40:
            salida.append((desde, hasta))
    # Y como los escriben ILLINOIS y JL en los autos viejos, con dos cifras y una barra: «CITROEN
    # 3CV SOLEX 69/73», «AMI 8 74/79», y JL también con una sola cifra al final: «3CV 70/3»,
    # «3CV 74/9» (de 1974 a 1979). Solo de 1950 a 1999, que es donde se escriben así, y sin
    # otra barra ni otro número pegado: «R9/11/12» son modelos.
    for _d, _h in _RE_ANIOS_VIEJOS_CON_BARRA.findall(str(descripcion or "")):
        desde = 1900 + int(_d)
        hasta = (desde - desde % 10 + int(_h)) if len(_h) == 1 else 1900 + int(_h)
        if desde <= hasta <= desde + 40:
            salida.append((desde, hasta))
    return tuple(salida)


_RE_ANIOS_DE_DOS_CIFRAS = re.compile(r"(?<![\d.,])(\d{2}) -(\d{2})(?![\d.,])")
_RE_ANIOS_VIEJOS_CON_BARRA = re.compile(
    r"(?<![\w/.,])([5-9]\d)/(\d{1,2})(?![\w/.,])(?!\s?(?:HP|CV|MM|KW|V|A)\b)")


# Donde termina la parte que habla del auto. Después vienen los números de referencia —«//
# 1776501/BK3Q6051B1C/B1B», «REF ORIG …», «NGK= BP5HS»— y ahí hay siglas con forma de motor
# que no son motores: «B1B» es el final de un número de Ford y «BP5HS» es una bujía NGK.
_RE_FIN_DE_LA_APLICACION = re.compile(
    r"//|\bREF\b|\bNGK\b|\bBOSCH\b|\bCHAMPION\b|\bEQUIV|=|\bREEMPLAZA", re.IGNORECASE)


def motores_de_la_descripcion(descripcion, excluir=(), codigo_propio=""):
    """Los códigos de motor que nombra la descripción (G9U, K9K, D4F, F5L…), solo de la parte que
    habla del auto. Ver parece_designacion_de_motor() y «motores distintos» en
    firmas_compatibles(). `excluir` son los modelos y las siglas, que a veces tienen la misma
    forma (XR3I); `codigo_propio` es el del producto, que también puede tenerla (KIT20003A)."""
    texto = _RE_FIN_DE_LA_APLICACION.split(str(descripcion or ""), 1)[0]
    texto = re.sub(r"(?:\s*\([^)]*\))+\s*$", "", texto)      # las referencias del final
    propio = sanitizar(codigo_propio or "")
    return frozenset(w for w in re.findall(r"[A-Z0-9]{3,8}", _normalizar_desc(texto))
                     if parece_designacion_de_motor(w) and w not in excluir
                     and not (propio and w in propio))


# Qué motores declara el catálogo que se llevan: ver aprender_motores_que_van_juntos().
# Es de cada pasada de la lógica a propósito, y se relee cada diez minutos porque la tanda de
# fondo reescribe la tabla.
_MOTORES_QUE_VAN_JUNTOS = {}


def _motores_que_van_juntos():
    guardado = _MOTORES_QUE_VAN_JUNTOS.get("pares")
    if guardado and time.time() - guardado[0] < 600:
        return guardado[1]
    try:
        c.execute("SELECT motor_a, motor_b FROM motores_compatibles")
        pares = frozenset(frozenset((r[0], r[1])) for r in c.fetchall())
    except Exception as _err:
        anotar_error("_motores_que_van_juntos", _err)
        pares = frozenset()
    _MOTORES_QUE_VAN_JUNTOS["pares"] = (time.time(), pares)
    return pares


_RE_FAMILIA_DE_MOTOR = re.compile(r"[A-Z]+\d+")


def algun_motor_en_comun(motores_a, motores_b):
    """¿Comparten algún motor? De la misma FAMILIA —las letras y el número del principio: G10BB,
    G10A y G10T son G10; D4F y D4K son D4—, o dos que el catálogo declara que van juntos.
    F4L contra F5L (cuatro y cinco cilindros del Deutz 913) o G9U contra S8U no."""
    def familia(m):
        encontrado = _RE_FAMILIA_DE_MOTOR.match(m)
        return encontrado.group() if encontrado else m
    if {familia(a) for a in motores_a} & {familia(b) for b in motores_b}:
        return True
    juntos = _motores_que_van_juntos()
    return any(frozenset((a, b)) in juntos for a in motores_a for b in motores_b)


def anios_que_no_se_tocan(rangos_a, rangos_b):
    """¿Los dos dicen años y ningún rango de uno se cruza con alguno del otro?"""
    return bool(rangos_a and rangos_b) and not any(
        a0 <= b1 and b0 <= a1 for a0, a1 in rangos_a for b0, b1 in rangos_b)


# SOBREMEDIDA: la junta de tapa, el pistón, el aro o el espárrago para un motor rectificado.
# Cada lista lo escribe a su manera: «Jta.Tapa Cil.Superm. FIAT 1100» (TARANTO), «SUPLEMENTO
# SOBREMEDIDA» (ILLINOIS), «SUPERMEDIDA» o «SUPERME» cortado (IMPERIAL), «s/m» (JL), o la
# medida: «Cil.099,7 + 0,5», «+0,7», «+0.030». «O.S.» no: «OS3573» es un código de Vernet.
_RE_SOBREMEDIDA = re.compile(
    r"\b(?:SUPER|SOBRE)\s?-?\s?MED(?:IDA)?\b|\b(?:SUPERM|SOBREM|SUPERME)\b|\bS/M\b"
    r"|\bSOBRE\s+M\b", re.IGNORECASE)
_RE_CUANTO_DE_SOBREMEDIDA = re.compile(r"\+\s?(0?[.,]\d{1,3})(?!\d)")
_RE_MEDIDA_ESTANDAR = re.compile(r"\b(?:STD|STANDARD|EST[AÁ]NDAR)\b", re.IGNORECASE)


def sobremedida_de(descripcion):
    """None si no dice sobremedida; si la dice, cuánta («0.5», «0.03») o «SI» sin el número.
    Si dice las dos cosas —«STD y sobremedida»— es None: habla de una línea entera."""
    texto = descripcion or ""
    cuanto = _RE_CUANTO_DE_SOBREMEDIDA.search(texto)
    if not cuanto and not _RE_SOBREMEDIDA.search(texto):
        return None
    if _RE_MEDIDA_ESTANDAR.search(texto):
        return None
    if cuanto:
        return f"{float(cuanto.group(1).replace(',', '.')):g}"
    return "SI"


def sobremedidas_que_chocan(sm_a, sm_b):
    """Una es sobremedida y la otra no la dice (es la estándar: nadie vende una sobremedida
    sin avisar), o las dos dicen cuánta y no es la misma."""
    if bool(sm_a) != bool(sm_b):
        return True
    return bool(sm_a and sm_b and "SI" not in (sm_a, sm_b) and sm_a != sm_b)


def sirve_para_anio(descripcion, anio):
    """¿Este repuesto aplica a un vehículo de ese año? Si la descripción no dice nada de años,
    devuelve None: no se puede afirmar ni descartar, y es mejor mostrarlo que ocultarlo."""
    desde, hasta = extraer_anios(descripcion)
    if desde is None:
        return None
    if hasta is None:
        return anio >= desde
    return desde <= anio <= hasta


# Marcas de REPUESTO. No son modelos de auto, y tampoco dicen qué pieza es: dos proveedores
# distintos venden repuestos Bosch de cosas completamente distintas.
# Estaban saliendo primeras en el desplegable «Modelo / motor»: DELCO encabezaba la lista de
# Ford con 951 apariciones y NIPPONDENSO la de Toyota con 476, antes que COROLLA. El filtro de
# «aparece sobre todo en esta marca» no las agarra porque un proveedor sí las nombra casi
# siempre junto al mismo auto.
# Va en su propio conjunto porque firma_de_producto() necesita sacar ESTAS de lo que dice qué
# pieza es, y NO las de abajo — ver el comentario del núcleo.
MARCAS_DE_REPUESTO = {
    "BOSCH", "VALEO", "DELCO", "DENSO", "NIPPONDENSO", "MAGNETI", "MAGNETTI", "MARELLI",
    "HITACHI", "LUCAS", "SIEMENS", "DELPHI", "JAEGER", "MASSER", "CAUPLAS", "WEBER", "SOLEX",
    "SKF", "NGK", "MANN", "VITRON", "TAILLOT", "PAIA", "WAHLER", "GATES", "SACHS", "MONROE",
    "FRAM", "BERU", "FACET", "PIERBURG", "MAHLE", "ELRING", "REINZ", "AJUSA", "CORTECO",
    "PAYEN", "TRW", "FERODO", "BREMBO", "NAKATA", "ILUMA", "DPB", "FISPA", "CBOSCH",
    # Salidas de contar qué palabras entraban en la APLICACIÓN de las firmas del catálogo real:
    # estas cinco están entre las más frecuentes y no son autos, son quién hizo el repuesto.
    # LESTER no es un fabricante sino la numeración con la que se piden alternadores, pero para
    # esto da igual: tampoco dice para qué auto es.
    "INA", "HELLA", "PRESTOLITE", "UNIPOINT", "LESTER", "THOMSON", "INDUMAG",
}

# De PALABRAS_NO_MODELO, las que no nombran una PIEZA sino el CONTEXTO: qué tipo de vehículo
# es, con qué anda, cómo viene el motor. Sirven igual para el desplegable de modelos —no son
# modelos—, pero del lado de la firma van con la aplicación y no con la pieza.
# Salió de mirar lo que proponía sobre las dos listas de juntas: «Juego de juntas para Caja de
# Velocidad FORD CARGO» salía equivalente a «Jta.Tapa Cil. FORD CARGO TURBO» porque las dos
# compartían JUNTA y CARGO, y CARGO contaba como si dijera qué pieza es. Lo mismo con PICK,
# UP, BUS, CAMION y TRACTOR.
PALABRAS_DE_CONTEXTO = {
    "PICK", "UP", "BUS", "CAMION", "TRACTOR", "AGRICOLA", "CARGO", "GRAND", "SERIE",
    "DIESEL", "TURBO", "CID", "DOHC", "SOHC", "STD", "COMPLETO", "SEMI", "MECANICA",
    "MM", "CC", "V", "L", "S", "R", "AX", "DD", "F",
}

# Palabras que NO son modelos de auto, para el desplegable «Modelo / motor». Son sobre todo
# nombres de PIEZA: por eso este conjunto sirve para descartar modelos y NO sirve para
# descartar palabras del núcleo de la firma, que es justo lo contrario.
PALABRAS_NO_MODELO = {
    # Lugares de la pieza que no estaban en este vocabulario y por eso no llegaban a la pieza:
    # ver _LUGARES_DE_LA_PIEZA.
    "HIDRAULICA", "HIDRAULICO", "TRANSMISION", "EMBRAGUE", "PRECAMARA",
    # «JTA J.DEERE MANDO FINAL»: dice de qué es la junta aunque no sea un lugar del motor.
    "MANDO",
    # Lugar de la pieza que no estaba: ver _LUGARES_DE_LA_PIEZA.
    "BOTADORES", "BOTADOR",
    "JUNTA", "JUNTAS", "JUEGO", "DESPIECE", "TAPA", "CILINDROS", "VALVULAS", "CARTER", "BOMBA",
    "ACEITE", "AGUA", "COMBUSTIBLE", "NAFTA", "TERMOSTATO", "RETEN", "ARO", "AROS", "PISTON",
    "CIL", "CILINDRO", "MOTOR", "SERIE", "PICK", "UP", "BUS", "CAMION", "TRACTOR", "DIESEL",
    "TURBO", "INY", "INYECCION", "CID", "DOHC", "SOHC", "MM", "CC", "STD", "COMPLETO", "SIN",
    "CON", "PARA", "DE", "DEL", "LA", "EL", "Y", "O", "REPARACION", "ADMISION", "ESCAPE",
    "CARBURADOR", "DESCARBONIZACION", "LATERAL", "SUPLEMENTO", "CAPERUZA", "BOLILLEROS",
    "DIRECCION", "MECANICA", "AGRICOLA", "CARGO", "GRAND", "SEMI", "ORING", "ARANDELA",
    "ALUMINIO", "CLAVITO", "BANCADA", "CAPUCHON", "BUJIA", "BRIDA", "CAÑO", "CALEFACCION",
    "ARBOL", "LEVAS", "SALIDA", "TAPON", "VALVULA", "MARIPOSA", "BASE", "DISTRIBUIDOR",
    # Las dos que dejan leer «JTA M.ESC.» y «JTA TAPA C.VEL.» de IMPERIAL como piezas: ver
    # _ABREVIATURAS_CON_PUNTO.
    "MULTIPLE", "VELOCIDAD",
    # Faltaban, y sin ellas «Juntas para diferencial PEUGEOT 404» quedaba como «JUNTA» a secas.
    "DIFERENCIAL", "COLECTOR", "FILTRO",
    # Las marcas de carburador dicen QUÉ junta es: ver _MARCAS_DE_CARBURADOR.
    "WEBER", "SOLEX", "HOLLEY", "STROMBERG", "ZENITH", "CARESA", "BROSOL", "GALILEO", "IAVA",
    "EIES", "CARTER", "MOTORCRAFT", "ROCHESTER", "AUTOLITE", "DELLORTO",
    "CHUPADOR", "INTERMEDIA", "V", "L", "S", "R", "AX", "DD", "F",
    # EL VOCABULARIO DE PIEZA QUE FALTABA, y que la firma estaba contando como si dijera para
    # qué auto es. Salió de contar las palabras que entraban en la aplicación de las 30.000
    # descripciones reales y quedarse con las que no son ningún auto: nombres de pieza
    # (SENSOR está 3.988 veces, CANO 2.188, BULBO 1.298), atributos (DIAMETRO, VOLTS, VIAS,
    # DIENTES) y relleno del proveedor (REF 11.421 veces, TODOS, DESDE, LIVIANA, PESADA).
    # Con esas del lado de la aplicación, dos sensores de detonación de autos distintos
    # «coincidían en para qué auto es» porque los dos decían SENSOR y DETONACION.
    "SENSOR", "SENSORES", "BULBO", "BOBINA", "IGNICION", "INYECTOR", "POLEA", "FILTRO",
    "FICHA", "CONECTOR", "SONDA", "LAMBDA", "INTERRUPTOR", "RESISTOR", "RELAY", "REGULADOR",
    "ALTERNADOR", "ALTERNADORES", "ARRANQUE", "ROTACION", "DETONACION", "TEMPERATURA",
    "PRESION", "RADIADOR", "CALEFACTOR", "ELECTROVENTILADOR", "EGR", "MAP", "ABS", "MASA",
    "AIRE", "CANO", "CANOS", "TUBO", "CORREA", "DISTRIBUCION", "DIST", "SURTIDOR", "AFORADOR",
    "CUERPO", "VASO", "EXPANSION", "NIVEL", "STOP", "CODO",
} | MARCAS_DE_REPUESTO


def version_del_catalogo():
    """Testigo de caché del catálogo de vehículos. Cambia cuando cambia lo que se lee de él.

    El catálogo por vehículo se deduce de las DESCRIPCIONES, así que tiene que recalcularse
    cuando una descripción cambia, no solo cuando aparecen productos nuevos. Antes el testigo
    era COUNT(*) a secas y eso dejaba afuera el caso más común: correr «reparar descripciones
    pegadas» reescribe miles de descripciones sin mover el contador ni un número, así que la
    pantalla seguía mostrando los modelos viejos hasta reiniciar la app. Lo mismo al borrar
    una lista e importar otra del mismo tamaño.

    SUM(LENGTH(...)) recorre la tabla entera: 11 ms con 61.574 productos, unos 20 ms con
    108.000. Es una vez por dibujado de UNA pantalla, contra un caché que evita releer todas
    las descripciones palabra por palabra."""
    try:
        c.execute("SELECT COUNT(*), COALESCE(SUM(LENGTH(COALESCE(descripcion, ''))), 0) FROM productos")
        fila = c.fetchone()
        return (fila[0], fila[1])
    except sqlite3.OperationalError as _err:
        anotar_error("version_del_catalogo", _err)
        return (0, 0)


def es_nombre_de_modelo(token):
    """¿Esta palabra puede ser el nombre de un modelo, o es un número de parte?

    La diferencia que sí se puede medir es cuántos dígitos tiene. Un modelo lleva pocos —
    F-250, S-10, 4RUNNER, C20NE, XU7JP4— y un número de parte lleva muchos: A0091547202,
    M009T61671, EA011610461, SR0465N. Se revisaron a mano los 2.655 tokens del catálogo real
    que tienen cuatro dígitos o más, ordenados por cuánto aparecen, y no hay un solo modelo
    de verdad entre ellos; son todos números de Bosch, Valeo, Mitsubishi y Cummins.

    El precio de la regla: se pierden nombres de camión tipo «VW 11.000» cuando la lista los
    escribe pegados («VW11000EB»). Vale la pena: esto arma un desplegable para elegir, no una
    coincidencia de códigos, y de 5.670 «modelos» detectados 2.655 eran basura.

    Se probó además exigir que alterne poco entre letras y números —la idea era sacar
    'P5TG01', que es un número de parte y quedaba cargado como si fuera un modelo de Honda—.
    Se descartó con el dato a la vista: esa regla se lleva puestas las motorizaciones, y las
    motorizaciones SON el dato más preciso que trae una descripción. En el catálogo real
    'K9K' está en 109 descripciones, 'C20NE' en 70 y 'DV6CTD' en 10, y saber que una pieza va
    a un K9K vale más que saber que va a un Clio. Costaba 573 modelos para ganar uno."""
    return sum(ch.isdigit() for ch in token) <= 3


# EL PARÁMETRO NO PUEDE EMPEZAR CON GUION BAJO. Streamlit NO hashea los parámetros que
# arrancan con «_» —es su forma de decir «esto no entra en la clave del caché»— así que
# `f(_version)` se calcula UNA vez y después devuelve siempre lo mismo, pase lo que pase con el
# catálogo. Era exactamente lo contrario de lo que este testigo existe para hacer: se importaba
# una lista nueva y la pantalla de vehículos seguía mostrando los modelos viejos hasta reiniciar
# la app, y el extractor de códigos seguía sin conocer los códigos recién cargados.
@st.cache_data(show_spinner=False, max_entries=3)
def descripciones_por_palabra(version):
    """{palabra: en cuántas descripciones del catálogo aparece}. Una sola pasada.

    Existe por velocidad. modelos_de_marca() necesita, para cada palabra candidata, saber en
    cuánto del catálogo aparece —así distingue un modelo («ASTRA» es de Chevrolet y de nadie
    más) de una palabra genérica—. Lo hacía con un LIKE por candidata, o sea una recorrida
    entera de la tabla por cada una: la lista de modelos de Volkswagen tardaba 13,4 s y la de
    Ford 12,1 s, con la pantalla en blanco mientras tanto. Contar todo de una vez y compartir
    el resultado entre todas las marcas lo deja en una sola pasada.

    Además cuenta por PALABRA y no por subcadena, que es lo que se quería desde el principio:
    con LIKE '%GOL%' entraban GOLF y ARREGLO."""
    from collections import Counter
    cuenta = Counter()
    c.execute("SELECT descripcion FROM productos WHERE descripcion IS NOT NULL")
    for fila in c.fetchall():
        for palabra in set(re.findall(r"[A-ZÁÉÍÓÚÑ0-9][A-ZÁÉÍÓÚÑ0-9\-]*",
                                      (fila["descripcion"] or "").upper())):
            cuenta[palabra] += 1
    return cuenta


@st.cache_data(show_spinner=False, max_entries=3)
def codigos_del_catalogo(version):   # ver descripciones_por_palabra(): sin guion bajo
    """Todos los códigos que ya están cargados, limpios. Se usa como desempate al leer
    códigos de fábrica metidos adentro de una descripción: ver extraer_codigos_de_texto().

    Solo los códigos de las listas de PROVEEDOR, a propósito. Los de «OEM / FABRICA» no
    valen para esto porque muchos los creó esta misma función en una importación anterior,
    leyéndolos de una descripción: si contaran, la basura de ayer se legitimaría sola.
    Se ve enseguida en la base real — entre los códigos «de fábrica» hay 'DS3-BMW', 'i30-KIA',
    'S10-PEU' y 'gol1.0-golf', que son modelos de auto que entraron mal. Con esos adentro, el
    texto «CITROEN C3/C4/DS3-PEU 206» volvía a producir un código; con solo los de proveedor,
    no.

    Va cacheado porque al importar una lista se consulta una vez por fila y son decenas de
    miles. Son 39.746 códigos de proveedor en la base real: se arma en 0,03 s."""
    c.execute("""SELECT DISTINCT p.codigo_clean FROM productos p JOIN marcas m ON m.id = p.marca_id
                 WHERE p.codigo_clean IS NOT NULL AND m.tipo <> 'OEM'""")
    return {fila[0] for fila in c.fetchall() if fila[0]}


# Ni la inyección ni la carrocería son un modelo de auto. Salieron de mirar lo que la app
# ofrecía en el desplegable de vehículos: el primer «modelo» de Audi era TDI y el primero de
# Peugeot, HDI. Después venían QUATTRO, TFSI, FSI, AVANT, SPORTBACK — o sea que quien busca por
# auto elegía entre versiones y motores en vez de entre autos. Aparecen arriba de todo porque
# la lista va por frecuencia y estas palabras están en miles de descripciones.
# Los CÓDIGOS de motor (DW8, TU5JP4, EW10J4) se dejan: esos sí identifican una aplicación, y de
# hecho son el dato más preciso que trae una descripción.
MOTORIZACIONES_QUE_NO_SON_MODELO = {
    "TDI", "TDCI", "TFSI", "FSI", "HDI", "DCI", "JTD", "JTDM", "CDI", "CRDI", "TSI", "MPI",
    "SPI", "GDI", "VTI", "THP", "VVT", "MULTIJET", "MULTIAIR", "DUALOGIC", "ETORQ", "E-TORQ",
    "FIRE", "ZETEC", "ROCAM", "DURATEC", "ENDURA", "POWERSHIFT", "TIPTRONIC", "MULTIPOINT",
    "MONOPUNTO", "NAFTA", "DIESEL", "TURBO", "BITURBO",
    "QUATTRO", "AVANT", "SPORTBACK", "ALLROAD", "CABRIOLET", "COUPE", "BREAK", "WEEKEND",
    "SEDAN", "FURGON", "PICKUP", "RURAL",
}



# max_entries=20 no alcanzaba y el número sale del catálogo: hay 117 marcas de vehículo con
# productos. Con tope 20, el que mira más de veinte marcas en una sesión empieza a desalojar las
# primeras y a repagarlas —1 segundo cada vez, medido— justo cuando vuelve sobre una que ya
# había abierto. Lo que se guarda son listas de palabras, no filas del catálogo.
@st.cache_data(show_spinner=False, max_entries=130)
def modelos_de_marca(marca_vehiculo, version, minimo=2):   # ver descripciones_por_palabra()
    """Arma la lista de modelos de una marca leyendo el catálogo.

    Cómo distingue un modelo de una palabra de repuesto: las palabras de repuesto (JUNTA,
    BOMBA, ORING) aparecen en MUCHAS marcas distintas, mientras que un modelo aparece casi
    solo en la suya — un ASTRA es de Chevrolet y de nadie más. Con eso se filtra sin tener
    que cargar una lista de modelos a mano, y crece solo con cada lista nueva que importás."""
    # El prefiltro tiene que contemplar las abreviaturas: buscando «VOLKSWAGEN» se pierden
    # los 5.530 productos que escriben «VW», que son casi todos los que hay.
    # Sin LIMIT: el tope caía sobre el prefiltro por texto, no sobre los que de verdad son de
    # esta marca, así que con el catálogo grande los modelos salían de una muestra recortada
    # justo por las marcas que más productos tienen. Son 7.797 filas para FORD, la peor: no
    # hace falta topearlo.
    _donde, _params = _like_de_marca(marca_vehiculo)
    c.execute(f"""SELECT p.descripcion FROM productos p
                  WHERE p.descripcion IS NOT NULL AND {_donde}""", _params)
    propias = [r["descripcion"] for r in c.fetchall()]

    from collections import Counter
    cuenta_propia = Counter()
    for desc in propias:
        # Se toma el tramo de ESTA marca, no el de la primera que aparezca: en «Ford Escort -
        # VW Gol» los modelos de Volkswagen son «Gol», no «Escort».
        resto = next((r for m, _cat, r in marcas_vehiculo_en(desc) if m == marca_vehiculo), None)
        if not resto:
            continue
        cuenta_propia.update(_candidatos_a_modelo(resto))
    return _modelos_confirmados(cuenta_propia, version, minimo)


def _candidatos_a_modelo(resto):
    """Las palabras del tramo de una marca que pueden ser un modelo. Ver modelos_de_marca()."""
    # Dos formas de escribir un modelo que este patrón dejaba afuera, y por eso el
    # desplegable de Peugeot no tenía ni el 206 ni el 307, y el de Audi no tenía el A3:
    #   · el modelo que es un NÚMERO —Peugeot 206, Fiat 600, Mercedes 1620—, que se
    #     descartaba por ser puro número;
    #   · el de dos caracteres —A3, A4, Q7, X5—, que no llegaba al mínimo de tres.
    # Los dos siguen pasando por el mismo filtro que todo lo demás: solo quedan si
    # aparecen casi siempre dentro de esta marca, así que un número que además es una
    # medida o un año se cae ahí.
    for token in re.findall(r"[A-ZÁÉÍÓÚÑ0-9][A-ZÁÉÍÓÚÑ0-9\-]{1,}", resto.upper()):
        if (token in PALABRAS_NO_MODELO or token in MARCAS_VEHICULO
                or token in MOTORIZACIONES_QUE_NO_SON_MODELO):
            continue
        _puro_numero = re.fullmatch(r"\d{2,4}", token)
        if _puro_numero and re.fullmatch(r"(19|20)\d{2}", token):
            continue      # un año no es un modelo
        if not _puro_numero:
            if re.fullmatch(r"[\d\-]+", token) or len(token) < 2:
                continue
            if not token[0].isalpha():
                continue
            if len(token) == 2 and not (token[0].isalpha() and token[1].isdigit()):
                continue   # «A3» sí, «DE» no
            if not es_nombre_de_modelo(token):
                continue
        yield token


def _modelos_confirmados(cuenta_propia, version, minimo=2):
    """De las palabras contadas en una marca, las que son modelos suyos. Ver modelos_de_marca()."""
    if not cuenta_propia:
        return []

    # Cuántas veces aparece cada palabra en el catálogo entero (para descartar las genéricas)
    candidatos = [t for t, n in cuenta_propia.items() if n >= minimo]
    en_todo_el_catalogo = descripciones_por_palabra(version)
    modelos = []
    for token in candidatos:
        total_catalogo = en_todo_el_catalogo.get(token, 0) or 1
        # Si la mayoría de las veces que aparece es dentro de esta marca, es un modelo suyo
        if cuenta_propia[token] / total_catalogo >= 0.6:
            modelos.append((token, cuenta_propia[token]))
    return sorted(modelos, key=lambda x: -x[1])


@st.cache_data(show_spinner=False, max_entries=1)
def modelos_de_todas_las_marcas(version, minimo=2):   # ver descripciones_por_palabra()
    """{marca: modelos_de_marca(marca)} para todas las marcas de auto, en UNA pasada.

    Lo usa el lector de aplicaciones, que necesita los modelos de todas las marcas que
    aparecen, y las pedía de a una: cada marca relee el catálogo entero con su filtro por
    texto. Son 65 marcas: con 60 proveedores, 43 s después de cada lista, 19 de ellos solo
    leyendo las mismas descripciones 65 veces. Acá cada descripción se lee una vez y se reparte
    entre las marcas que nombra. Da lo mismo que modelos_de_marca() marca por marca."""
    from collections import Counter, defaultdict
    lector = conn.conexion_real().cursor()
    lector.execute("SELECT descripcion FROM productos WHERE descripcion IS NOT NULL")
    cuenta = defaultdict(Counter)
    while True:
        pedazo = lector.fetchmany(5000)
        if not pedazo:
            break
        for (desc,) in pedazo:
            ceder_al_mostrador()
            for marca, _cat, resto in marcas_vehiculo_en(desc):
                if resto:
                    cuenta[marca].update(_candidatos_a_modelo(resto))
    return {marca: _modelos_confirmados(cuenta_marca, version, minimo)
            for marca, cuenta_marca in cuenta.items()}


@st.cache_data(show_spinner=False, max_entries=30)
def catalogo_por_vehiculo(marca_vehiculo, version):   # ver descripciones_por_palabra()
    """Todos los productos cuya descripción menciona esa marca de vehículo, agrupados por
    categoría. 'version' solo sirve para que el caché se refresque cuando cambia el catálogo."""
    # Sin LIMIT. El tope de 4.000 se aplicaba al prefiltro suelto, no al resultado: para una
    # marca como MAN, que engancha por LIKE con MANGUERA y MANIJA, el tope se llenaba de
    # basura y los productos de MAN de verdad quedaban afuera del corte, así que la pantalla
    # salía vacía aunque el dato estuviera cargado.
    _donde, _params = _like_de_marca(marca_vehiculo)
    c.execute(f"""SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
                         m.nombre AS "Marca", p.precio AS "Precio", p.stock AS "Stock"
                  FROM productos p JOIN marcas m ON m.id = p.marca_id
                  WHERE p.descripcion IS NOT NULL AND {_donde}""", _params)
    filas = filas_a_listas(c)
    por_categoria = {}
    for f in filas:
        # Alcanza con que la descripción NOMBRE este auto. Antes se pedía que fuera el
        # principal, y como la descripción nombra varios, el producto solo aparecía en uno.
        tramo = next((t for t in marcas_vehiculo_en(f["Descripcion"]) if t[0] == marca_vehiculo),
                     None)
        if not tramo:
            continue
        _marca, categoria, resto = tramo
        f["_categoria"] = categoria or "Sin categoría"
        f["_aplicacion"] = resto or ""
        # El texto ya despegado, para poder filtrar por modelo sin que «206» enganche adentro
        # de un número de parte. Se hace acá porque esta función va cacheada por versión del
        # catálogo: separar las 6.991 descripciones de PEUGEOT cuesta 0,35 s y así se paga una
        # vez, no en cada vuelta de la pantalla.
        f["_texto"] = separar_texto_pegado(f["Descripcion"] or "").upper()
        por_categoria.setdefault(f["_categoria"], []).append(f)
    return por_categoria


@st.cache_data(show_spinner=False, max_entries=5)
def marcas_vehiculo_disponibles(version):   # ver descripciones_por_palabra()
    """Qué marcas de vehículo aparecen realmente en el catálogo, y cuántos productos tiene cada una.

    El número que va acá es EL MISMO que después va a devolver la pantalla. Antes era un LIKE
    suelto por marca, sin bordes de palabra, y mentía bastante:
        MAN decía 749 productos y tenía 3 (enganchaba MANGUERA, MANIJA, ALEMANIA);
        RAM decía 519 y tenía 15 (RAMPA);
        22 marcas del desplegable daban la pantalla vacía.
    Y costaba 118 recorridas enteras de la tabla, una por marca: 3,8 s. Ahora es una sola
    pasada de 2,1 s que además cuenta bien."""
    from collections import Counter
    cuenta = Counter()
    c.execute("SELECT descripcion FROM productos WHERE descripcion IS NOT NULL")
    for fila in c.fetchall():
        for marca, _categoria, _resto in marcas_vehiculo_en(fila["descripcion"]):
            cuenta[marca] += 1
    return sorted(cuenta.items(), key=lambda x: -x[1])


# Familias de repuestos. Gana la palabra clave MÁS LARGA que aparezca en la descripción, así
# "BOMBA DE AGUA" (refrigeración) le gana a "BOMBA" y "BOMBA DE ACEITE" no cae en el mismo lado.
# Medido sobre las 61.574 descripciones reales de las listas: con esta tabla como estaba, el
# 40% del catálogo (25.112 productos) quedaba en «Sin clasificar». Importa más de lo que
# parece: puentes_sospechosos() —el que detecta un código falso que fusionó dos familias de
# repuestos— descarta a propósito los «Sin clasificar», así que estaba decidiendo con menos de
# dos tercios de la evidencia. Con las claves de abajo y el arreglo del punto en
# _normalizar_desc(), el sin clasificar baja al 17% (10.502): 14.610 productos rescatados y
# ninguno perdido.
FAMILIAS_REPUESTO = {
    "Filtros": [
        "FILTRO DE ACEITE", "FILTRO DE AIRE", "FILTRO DE COMBUSTIBLE", "FILTRO DE NAFTA",
        "FILTRO DE GASOIL", "FILTRO DE HABITACULO", "FILTRO DE CABINA", "FILTRO SECADOR",
        "FILTRO", "SEPARADOR DE AGUA",
    ],
    "Frenos": [
        "PASTILLA DE FRENO", "PASTILLAS DE FRENO", "DISCO DE FRENO", "CAMPANA DE FRENO",
        "CILINDRO DE FRENO", "BOMBA DE FRENO", "ZAPATA DE FRENO", "CABLE DE FRENO",
        "LATIGUILLO", "SERVOFRENO", "PASTILLA", "PASTILLAS", "ZAPATA", "ZAPATAS", "CALIPER",
        "MORDAZA", "CAMPANA", "TUBO DE FRENO", "MANGUERA DE FRENO", "FRENO", "FRENOS", "ABS",
    ],
    "Suspensión": [
        "AMORTIGUADOR", "ESPIRAL", "ELASTICO", "ROTULA", "BIELETA", "BARRA ESTABILIZADORA",
        "BRAZO SUSPENSION", "PARRILLA", "SOPORTE DE AMORTIGUADOR", "KIT DE SUSPENSION",
        "BUJE DE PARRILLA", "TREN DELANTERO", "TOPE DE SUSPENSION", "FUELLE DE AMORTIGUADOR",
        "SUSPENSION", "MUNON",
    ],
    "Dirección": [
        "CREMALLERA", "EXTREMO DE DIRECCION", "AXIAL DE DIRECCION", "BOMBA DE DIRECCION",
        "BRAZO PITMAN", "BIELETA DE DIRECCION", "COLUMNA DE DIRECCION", "EXTREMO", "AXIAL",
        "DIRECCION",
    ],
    "Palier y transmisión": [
        "HOMOCINETICA", "PUNTA DE EJE", "SEMIEJE", "PALIER", "CRUCETA", "CARDAN",
        "FUELLE DE PALIER", "FUELLE DE HOMOCINETICA", "JUNTA HOMOCINETICA", "TRIPOIDE",
    ],
    "Embrague": [
        "DISCO DE EMBRAGUE", "PLATO DE EMBRAGUE", "PLACA DE EMBRAGUE", "KIT DE EMBRAGUE",
        "COLLARIN", "RULEMAN DE EMPUJE", "CILINDRO DE EMBRAGUE", "BOMBA DE EMBRAGUE",
        "CABLE DE EMBRAGUE", "EMBRAGUE", "VOLANTE MOTOR", "ACTUADOR HIDRAULICO",
    ],
    "Caja y diferencial": [
        "CAJA DE VELOCIDAD", "CORONA Y PINON", "SINCRONIZADO", "DIFERENCIAL", "SATELITE",
        "CAJA DE CAMBIOS", "PALANCA DE CAMBIOS",
    ],
    "Distribución": [
        "CORREA DE DISTRIBUCION", "KIT DE DISTRIBUCION", "CADENA DE DISTRIBUCION",
        "TENSOR DE DISTRIBUCION", "CORREA POLY V", "CORREA DENTADA", "DISTRIBUCION",
        "TENSOR", "POLEA", "CORREA",
    ],
    "Refrigeración": [
        "BOMBA DE AGUA", "RADIADOR", "TERMOSTATO", "ELECTROVENTILADOR", "TAPA DE RADIADOR",
        "MANGUERA DE RADIADOR", "INTERCOOLER", "DEPOSITO DE AGUA", "REFRIGERACION",
        "VENTILADOR", "COOLER", "BIDON",
    ],
    # «Caño» no es un accesorio ni parte del radiador: es una familia entera de este catálogo
    # (1.340 productos, casi todos de Cauplas) y va de agua a gasoil a gases de escape. Antes
    # caían todos en «Sin clasificar», que es lo que ciega al detector de puentes falsos.
    "Caños y mangueras": [
        "CANO", "TUBO", "MANGUERA",
    ],
    "Lubricación": [
        "BOMBA DE ACEITE", "CARTER", "ENFRIADOR DE ACEITE", "VARILLA DE ACEITE",
        "TAPA DE VALVULAS", "MALLA DE ACEITE", "TAPA ACEITE", "TAPA DE ACEITE",
    ],
    "Motor - interno": [
        "PISTON", "PISTONES", "ARO DE PISTON", "AROS", "COJINETE", "BIELA", "CIGUENAL",
        "ARBOL DE LEVAS", "VALVULA DE ADMISION", "VALVULA DE ESCAPE", "GUIA DE VALVULA",
        "BUJE DE BIELA", "CAMISA", "CULATA", "TAPA DE CILINDRO", "BANCADA", "PERNO",
        "VALVULA", "VALVULAS", "RESORTE DE VALVULA",
    ],
    "Juntas y retenes": [
        # Abreviaturas que usan los proveedores en sus listas: sin ellas, «Jgo de motor» y
        # «JTA T.C.» no caían en ninguna familia y se colaban en cualquier búsqueda.
        "JGO DE MOTOR", "JUEGO DE MOTOR", "JGO MOTOR", "JGO DE JUNTAS", "JGO JUNTAS",
        "JTA T C", "JTA TC", "JTA DE TAPA", "JTA TAPA", "JTA",
        "JGO JTAS", "JGO JUNTAS", "JGO CAJA", "JTAS",
        "JUNTA DE TAPA", "JUNTA TAPA", "JUEGO DE JUNTAS", "JUNTA HOMOCINETICA", "RETEN",
        "RETENES", "JUNTA", "JUNTAS", "ORING", "O-RING", "EMPAQUETADURA", "SELLO",
    ],
    "Combustible": [
        "BOMBA DE NAFTA", "BOMBA DE COMBUSTIBLE", "INYECTOR", "CARBURADOR", "RIEL DE INYECCION",
        "REGULADOR DE PRESION", "TANQUE DE COMBUSTIBLE", "AFORADOR", "INYECCION",
        "CUERPO MARIPOSA", "CUERPO DE ACELERACION", "CPO ACEL", "MARIPOSA", "SURTIDOR",
        "BOMBA DE ALTA", "BOMBA ALTA", "BOMBA ELECTRICA", "REGULADOR PRES",
    ],
    "Escape": [
        # «TUBO DE ESCAPE» está por el cliente, no por el catálogo: en el mostrador lo piden
        # así, y sin la clave larga ganaba «TUBO» y el pedido caía en Caños y mangueras.
        "CANO DE ESCAPE", "TUBO DE ESCAPE", "TUBO ESCAPE", "SILENCIADOR", "CATALIZADOR",
        "SONDA LAMBDA", "MULTIPLE DE ESCAPE", "ESCAPE",
    ],
    "Eléctrico y encendido": [
        "CABLE DE BUJIA", "BUJIA", "BUJIAS", "BOBINA DE ENCENDIDO", "ALTERNADOR",
        "MOTOR DE ARRANQUE", "BURRO DE ARRANQUE", "BATERIA", "REGULADOR DE VOLTAJE",
        "DISTRIBUIDOR", "PLATINO", "SENSOR", "MODULO", "RELE", "FUSIBLE", "BOBINA",
        "CAPUCHON DE BUJIA", "BULBO", "INTERRUPTOR", "INTERRUP", "LLAVE TECLA",
        "LLAVE CONMUTAD", "CONMUTADOR", "MOTOR PASO", "MOTORES DE ARRANQUE", "CAPTOR",
        "SOLENOIDE", "PORTAFUSIBLE", "BALIZA",
    ],
    "Rodamientos y mazas": [
        "RULEMAN DE RUEDA", "MAZA DE RUEDA", "CUBO DE RUEDA", "RODAMIENTO", "RULEMAN",
        "BOLILLERO",
    ],
    "Climatización": [
        "COMPRESOR DE AIRE", "CONDENSADOR", "EVAPORADOR", "AIRE ACONDICIONADO",
        "FILTRO DE POLEN", "CALEFACCION", "TUBO CALEFACTOR", "TUBO CALEFAC", "CALEFACTOR",
    ],
    "Soportes y bujes": [
        "SOPORTE DE MOTOR", "SOPORTE DE CAJA", "BUJE", "BUJES", "TACO DE MOTOR", "SOPORTE",
    ],
    "Cables y comandos": [
        "CABLE DE ACELERADOR", "CABLE DE VELOCIMETRO", "CABLE DE CAPOT", "GUAYA", "CABLE",
    ],
    "Carrocería y accesorios": [
        "OPTICA", "FARO", "ESPEJO", "PARAGOLPE", "MANIJA", "CERRADURA", "BURLETE",
        "ESCOBILLA", "PARABRISAS", "GUARDABARRO", "CAPOT", "PARRILLA DE RADIADOR",
        "PLUMA", "CRIQUE",
    ],
}


def _normalizar_desc(texto):
    """Mayúsculas, sin acentos y con espacios simples, para poder comparar contra las claves.

    Los separadores se cambian por espacio, no solo el guión. Faltaba el PUNTO y era caro:
    los proveedores abrevian pegado —«JTA.TAPA CIL.», «Jgo.Jtas.P/Motor», «Cpo.Acel.»— así que
    la clave «JTA TAPA», que alguien había agregado justamente para esto, no coincidía nunca.
    Medido sobre las 61.574 descripciones reales: 1.332 productos decían «JTA.TAPA CIL.» y
    ninguno caía en Juntas y retenes."""
    limpio = re.sub(r"[-./,;:()]", " ", normalizar_texto(str(texto or "")))
    return " " + " ".join(limpio.split()) + " "


def _armar_buscador_de_familias():
    """Una sola expresión regular con todas las claves, en vez de 522 búsquedas por descripción.

    El bucle de antes hacía `texto.find(f" {clave} ")` por cada clave y por cada plural: son
    261 claves × 2 formas = **522 `str.find` y 522 f-strings por descripción**. Con cProfile
    sobre el catálogo entero eran 24.348.168 llamadas a `str.find`, el ítem número uno del
    perfil, y clasificar las 46.644 descripciones tardaba 6,66 s.

    La alternación de Python devuelve el match MÁS A LA IZQUIERDA y, a igual posición, la
    alternativa listada primero. Ordenando las formas de más larga a más corta, eso es
    exactamente el criterio de desempate de antes —`(posición, -largo)`— sin escribirlo.

    El empate entre familias se resuelve igual que antes, y hay que resolverlo igual a
    propósito: si la misma clave está en dos familias, el bucle viejo se quedaba con la
    primera que encontraba (el `<` es estricto), así que acá la primera tampoco se pisa.

    Medido: 6,66 s → 0,462 s, **14,4×**, y comparando familia por familia sobre las 46.644
    descripciones reales, 0 diferencias."""
    de_forma_a_familia = {}
    for familia, claves in FAMILIAS_REPUESTO.items():
        for clave in claves:
            for forma in (clave, clave + "S"):
                de_forma_a_familia.setdefault(forma, familia)
    # De más larga a más corta: es lo que le da a la alternación el desempate por largo.
    formas = sorted(de_forma_a_familia, key=len, reverse=True)
    patron = re.compile(r"(?<= )(" + "|".join(re.escape(f) for f in formas) + r")(?= )")
    return patron, de_forma_a_familia


# Un solo nombre a propósito: nucleo/generar.py copia bloques POR NOMBRE, así que una
# tupla desarmada en dos variables deja la segunda línea afuera y el paquete no importa.
_BUSCADOR_DE_FAMILIAS = _armar_buscador_de_familias()


def clasificar_repuesto(descripcion):
    """Devuelve a qué familia pertenece un repuesto, mirando su descripción.

    Por qué hace falta: antes la 'categoría' era literalmente el texto que venía antes de la
    marca del auto en la descripción. Como cada proveedor la escribe distinto ('JUNTA TAPA DE
    CILINDROS', 'JUNTA DE TAPA CIL.', 'JUEGO JUNTA TAPA'), salían cientos de categorías casi
    iguales repetidas, y el filtro no servía para encontrar nada.

    Gana la palabra clave que aparece PRIMERO; entre las que empiezan en el mismo lugar, la
    más larga. Ese orden no es un capricho: en las listas de repuestos el nombre de la pieza va
    al principio y lo que sigue es dónde va o de qué auto es. Con solo mirar el largo,
    'RETEN DELANTERO CIGUENAL' caía en Motor por 'CIGUENAL' en vez de en Retenes, que es lo que
    la pieza realmente es. Y el desempate por largo resuelve el otro caso: 'BOMBA DE AGUA' cae
    en Refrigeración y no en la misma bolsa que 'BOMBA DE ACEITE' o 'BOMBA DE FRENO'."""
    # También el plural. Las claves están en singular y las listas escriben las dos formas:
    # «FILTROS PARA COMBUSTIBLE» no caía en Filtros porque la clave es «FILTRO». Medido sobre
    # las 61.574 descripciones reales: 405 rescatadas del «Sin clasificar», ninguna perdida, y
    # 72 que cambiaron de familia — todas las revisadas para mejor («Filtros inyector» dejó de
    # ser Combustible, «Juego sellos de cierre de tapa de válvulas» pasó de Lubricación a
    # Juntas y retenes). Los plurales están adentro de la expresión, ver
    # _armar_buscador_de_familias().
    texto = _normalizar_desc(descripcion)
    if not texto.strip():
        return "Sin clasificar"
    patron, familia_de_la_forma = _BUSCADOR_DE_FAMILIAS
    hallado = patron.search(texto)
    return familia_de_la_forma[hallado.group(1)] if hallado else "Sin clasificar"


# COMBO solo con «DE» o una cantidad de filtros atrás: «COMBO 3 FILTROS», «COMBO DE
# FILTROS». En el catálogo real casi todas las veces que aparece es la Chevrolet/Opel Combo, y
# «Junta para Cárter CHEVROLET CORSA … COMBO DIESEL» quedaba como juego de juntas.
_RE_ES_KIT = re.compile(r'\b(KIT|KITS|JUEGO|JUEGOS|JGO|JGOS|SET|COMBO(?= (?:\d+ FILTROS?|DE)\b))\b')

# Un kit que no dice «kit»: nombra entre paréntesis los DOS códigos que trae, sumados.
# «DISTRIBUCION C/BOMBA (LKTBN336 + LWPN007)» es el kit de distribución con la bomba de agua
# adentro, y sin esto quedaba como un producto suelto — con la consecuencia de que el vínculo
# entre la bomba y el kit aparecía en la cola como una equivalencia mal hecha («rubros
# distintos: Distribución y Refrigeración»), cuando de equivalencia no tiene nada: uno viene
# adentro del otro.
# Se pide el PARÉNTESIS y el MÁS, las dos cosas. Con la barra en lugar del más se rompe: así
# es como Illinois lista los códigos de fábrica de UNA sola pieza —«Junta Tapa de Cilindros
# CUMMINS NT310 (3036100/3411461)»— y serían 747 productos marcados como kit sin serlo.
# Medido: con el paréntesis y el más son 12 descripciones y las 12 son kits de verdad.
_RE_KIT_POR_SUMA = re.compile(
    r'\(\s*[A-Z0-9][A-Z0-9.\-]{4,}\s*\+\s*[A-Z0-9][A-Z0-9.\-]{4,}\s*\)', re.IGNORECASE)

# Un código más corto que esto adentro de un texto engancha con cualquier cosa por casualidad.
LARGO_MINIMO_CODIGO_EN_KIT = 6

# Marcas que los proveedores pegan atrás de su propio número: «LSPFR6F11LUCAS», «26001FISPA».
# Se calculan una vez y no se leen de la base: son el nombre de la marca del producto, y la
# consulta que las necesita corre una vez por búsqueda.
_MARCAS_QUE_SE_PEGAN_AL_CODIGO = ("LUCAS", "FISPA", "BOSCH", "MARELLI", "MAGNETI", "VALEO",
                                  "DELPHI", "NGK", "GATES", "SKF", "BERU", "FACET")

# Para prefiltrar en SQL. Es a propósito más flojo que _RE_ES_KIT —acá «KIT» engancha también
# dentro de «KITS»— porque después se confirma con es_un_kit(), que sí mira la palabra entera.
PALABRAS_DE_KIT = ("KIT", "JUEGO", "JGO", "SET")


# QUÉ JUEGO DE MOTOR ES. Un «Jgo.Jtas.P/Motor FORD FALCON» es el juego completo de juntas del
# motor; un «JTA T.C. FORD FALCON» es UNA junta, la de tapa de cilindros, que viene adentro de
# ese juego. Son del mismo rubro y del mismo auto, y no se vende uno en lugar del otro. Sobre la
# cola real había 914 pares aprobables con un juego de un lado y no del otro, y los de juego de
# motor contra junta suelta eran siempre esto.
# No alcanza con «es un juego»: «Juego de juntas para Carburador» contra «JUNTAS FIAT 128
# WEBER» es el mismo juego escrito de dos formas. Lo que se compara es QUÉ juego de motor: el
# completo, el superior (descarbonización) o el inferior. Si uno lo es y el otro no, o son de
# tipos distintos, son productos distintos.
# «Juego de juntas de tapa de cilindros» es el superior (el de descarbonización) dicho de otra
# forma: «Juego Jtas.tapa cilindros FORD 460», «Jgo.Jta.Tapa Cil. MAZDA».
_RE_JUEGO_SUPERIOR = re.compile(r'\b(SUPERIOR|DESCARBONIZACION|DESCARB|DESM|DESMONTAJE'
                                r'|TAPA CIL\w*|TAPA DE CIL\w*|TAPA CILINDROS)\b')
_RE_JUEGO_INFERIOR = re.compile(r'\bINFERIOR\b')
# Sobre el texto de _normalizar_desc(), que cambia la barra por un espacio: «P/Motor» llega
# como «P MOTOR».
_RE_JUEGO_COMPLETO = re.compile(r'\b(P MOTOR|PARA MOTOR|JTAS MOTOR|JUNTAS MOTOR|JUNTAS DE MOTOR'
                                r'|COMPLETO)\b')
# El «Juego Completo de Reparación "sin TC" (Semi-juego)» de ILLINOIS: el completo SIN la junta
# de tapa de cilindros. Es otro producto que el completo.
_RE_JUEGO_SIN_TAPA = re.compile(r'\b(SIN TC|SIN T C|SIN T CIL|SIN TAPA CIL\w*|SEMI JUEGO|SEMIJUEGO)\b')


# QUÉ MIDE EL SENSOR. «Sensor de velocímetro Fiat Fiorino ... Palio» contra «SENSOR MARIPOSA
# ... Palio» compartían SENSOR y los autos, y son dos piezas distintas. Se lee el tipo con sus
# sinónimos y, si los dos dicen uno y no coinciden, son sensores distintos.
_TIPOS_DE_SENSOR = [
    ("MAP", r'\bMAP\b|PRESION (?:ABSOLUTA|DE COLECTOR|DEL COLECTOR|DE ADMISION|DEL MULTIPLE)'),
    ("MAF", r'\bMAF\b|MASA DE AIRE|MASA AIRE|FLUJO DE AIRE|CAUDALIMETRO'),
    ("MARIPOSA", r'\bTPS\b|MARIPOSA|POSICION (?:DEL |DE )?ACELERADOR|PEDAL'),
    ("ROTACION", r'ROTACION|CIGUENAL|\bRPM\b|\bPMS\b'),
    ("FASE", r'\bFASE\b|ARBOL DE LEVAS|\bLEVAS\b'),
    ("DETONACION", r'DETONACION|PISTONEO'),
    ("VELOCIDAD", r'VELOCIDAD|VELOCIMETRO|ODOMETRO'),
    ("TEMPERATURA", r'TEMPERATURA|\bTEMP\b'),
    ("LAMBDA", r'LAMBDA|OXIGENO'),
    ("ABS", r'\bABS\b'),
    ("NIVEL", r'\bNIVEL\b'),
    # Los bulbos: el de retromarcha y el de electroventilador son interruptores, no el de
    # temperatura del reloj, aunque lo digan en la misma frase («BULBO DE TEMPERATURA DE
    # ELECTROVENTILADOR»). Ver tipos_de_sensor().
    ("RETROMARCHA", r'RETROMARCHA|MARCHA ATRAS|REVERSA'),
    ("ELECTROVENTILADOR", r'ELECTROVENT|ELECTRO VENT'),
    ("PRESION DE ACEITE", r'PRESION (?:DE )?ACEITE|ACEITE'),
    # Para qué es el bulbo: el del RELOJ (el indicador del tablero, que varía la resistencia) o
    # el de la LUZ (el testigo, que prende y apaga). «Bulbo de temperatura crítica … Tapón
    # azul» (CRI-FA) concordaba con «BULBO DE TEMPERATURA RELOJ» (FISPA). Ver
    # firmas_compatibles(): chocan entre ellos aunque los dos sean de temperatura.
    ("RELOJ", r'\bRELOJ\b|INDICADOR|MANOMETRO'),
    ("TESTIGO", r'CRITICA|TESTIGO|\bLUZ\b|ALARMA'),
]
_RE_TIPOS_DE_SENSOR = [(t, re.compile(p)) for t, p in _TIPOS_DE_SENSOR]


# Los motores que son un número con un separador: PERKINS «4.203», «4-203», «6.354»; MWM
# «4.07». El núcleo los tira por ser puro número (o los parte en dos por el guion), así que
# «Junta para Cárter PERKINS ... 4.203» y «Jgo.Jtas.Carter PERKINS 4-203» no compartían nada
# más que la marca. Se guardan aparte, sin el separador.
_RE_MOTOR_NUMERICO = re.compile(r'(?<![\d.,])(\d{1,2})[.\-](\d{2,3})(?![\d.,])')


# Ver el control de firmas_compatibles(). «Junta para Cárter DEUTZ 913 TRACTOR 5 CIL.» contra
# «JTA CARTER DEUTZ 913 3 CIL.»: el mismo motor en otra cantidad de cilindros tiene otro cárter.
_RE_CANTIDAD_DE_CILINDROS = re.compile(r'\b(\d{1,2})\s*CIL(?:INDROS?|IND|S)?\b')
# Y la lista: «JTA T.V. DEUTZ 913 3/4/5/6 CIL» sirve para los cuatro; se leía solo el 6.
_RE_LISTA_DE_CILINDROS = re.compile(r'\b((?:\d/)+\d)\s*CIL(?:INDROS?|IND|S)?\b')
# Y como escribe IMPERIAL: «JTA CARTER FIAT 400/500 - 3 C.», «JTA TERMOSTATO MWM X-10 4/6 C.»
# (para 4 y 6 cilindros). Con el punto después de la C, y sin un punto ni un número pegado
# adelante: «ORING 12x3.5 C.D.ACE» es una medida, no un motor de 5 cilindros.
_RE_CILINDROS_CON_C = re.compile(r'(?<![\d.,/X])((?:\d/)*\d)\s*C\.(?!\w)')
# Y los motores que lo dicen en el nombre: en PERKINS y MWM el primer número es la cantidad de
# cilindros —«4.203», «6.354», «4.07T», «6-305»—. «Junta Termostato MWM SPRINT 4.07» es de
# cuatro cilindros, y concordaba con «JTA BASE.TERM. MWM SPRINT 6 C.». Solo en esas marcas: en
# otra, «4.10» puede ser cualquier cosa. Con dos o tres cifras después, que «2.8» es la
# cilindrada.
# También SPRINT —la familia MWM, que TARANTO escribe «CHEVROLET SPRINT 6.07 T», sin decir
# MWM— y MAXION —los Perkins hechos en Brasil: «4.236», «6.358»—. Sin SPRINT, la junta de cárter
# del 6.07 se proponía igual a la de IMPERIAL «JTA CARTER MWM SPRINT 4 CIL.».
_RE_MOTOR_QUE_DICE_SUS_CILINDROS = re.compile(r'\bPERKINS\b|\bM\W?W\W?M\b|\bSPRINT\b|\bMAXION\b')
_RE_CILINDROS_EN_EL_MOTOR = re.compile(r'(?<![\d.,])([2-8])[.\-]\d{2,3}T?(?![\d.,])')
# En DEUTZ también, con otra forma: F3L, F4L, BF6L, BF4M. El número es la cantidad de cilindros.
# «Jta.Carter DEUTZ F4L 913» concordaba con «JTA CARTER DEUTZ 913 6 CIL.»: el mismo 913 con otra
# cantidad de cilindros tiene otro cárter.
_RE_CILINDROS_DEUTZ = re.compile(r'\bB?F([1-8])[LM]\b')
# Los motores en V: «FORD F-100 V/8», «CAMRY 3.0 V6». Y los MWM que dicen los cilindros al
# final: «D229-4», «D229-6», «D226-3». «Jta.Salida Escape FORD F-100 V/8» concordaba con la del
# «F-100/150 … MWM D229-4»: el V8 naftero contra el diésel de cuatro.
_RE_CILINDROS_EN_V = re.compile(r'\bV/?(6|8|10|12)\b')
_RE_CILINDROS_MWM = re.compile(r'\bD22[5-9]-?([3-6])\b')
# El puente del diferencial: «DANA 70 - F250/F350» no es el «DANA 44 FORD».
_RE_PUENTE_DANA = re.compile(r'\bDANA\s?(\d{2})\b')
# Las SERIES de motor Deutz: 912/913/914, 511/514 (con sus 1114/2114), 1011/1012/1013, 2011...
# «Jta.Carter DEUTZ F4L 913» concordaba con la de la serie «514 1114 2114 4 CIL. … F4L»: los
# dos de cuatro cilindros, pero de otra serie. Solo en descripciones que dicen DEUTZ.
_RE_SERIE_DEUTZ = re.compile(r'(?<![\d.,])(91[0-4]|51[0-4]|1011|1012|1013|1015|2011|2012|2013|1114|2114)(?![\d.,])')
# Lo que va en un motor diésel, dicho también como «2.1D» o «1.9 D»: ver firmas_compatibles(),
# donde se usa para que una junta de carburador no concuerde con algo que va en un diésel.
_RE_DIESEL_CON_LA_D = re.compile(r'\d\s?D\b(?![.,]?\d)|\bDIESEL\b|\bD[IÍ]ESEL\b|\bTDI\b|\bHDI\b|\bTD\b')

# Los rubros donde nafta contra diésel dice que son piezas distintas: las del motor. Un sensor de
# velocidad o un interruptor de stop suelen ser los mismos en las dos versiones del auto.
_RUBROS_QUE_DEPENDEN_DEL_COMBUSTIBLE = {"Juntas y retenes", "Motor - interno", "Refrigeración",
                                        "Combustible", "Distribución"}

_MARCAS_DE_CARBURADOR = {"WEBER", "SOLEX", "HOLLEY", "STROMBERG", "ZENITH", "CARESA", "BROSOL",
                         "GALILEO", "IAVA", "EIES", "CARTER", "MOTORCRAFT", "ROCHESTER",
                         "AUTOLITE", "DELLORTO",
                         # DFV es la brasileña: «JUNTAS CHEV ETTE 1400 DFV Brasil» de JL es de
                         # carburador, no el cárter del Chevette. MIKUNI y KEIHIN, las japonesas.
                         "DFV", "MIKUNI", "KEIHIN",
                         # Y WB, como abrevia JL a Weber: «JUNTAS FORD ESCORT/ CHEV ETTE 1.6 Wb»
                         # concordaba con la junta de cárter del Chevette. En el catálogo real
                         # aparece solo en JL, y siempre en piezas de carburador.
                         "WB"}

# BUJÍA DE ENCENDIDO Y BUJÍA DE PRECALENTAMIENTO se llaman igual y no tienen nada que ver: una
# va en un motor naftero y la otra en un diésel. FISPA vende las de precalentamiento como
# «BUJIA LEIGG0xx ... 2 5 TD», y se emparejaban con «BUJIA NGK» del mismo auto.
_RE_BUJIA_PRECALENTAMIENTO = re.compile(r'INCANDES|ENCANDES|PRECALENT|PRE CALENT|CALENTADOR'
                                        r'|\bGLOW\b|\bLEIGG')
_RE_BUJIA_ENCENDIDO = re.compile(r'\bNAFTA\b|\bNGK\b|\bENCEND|\bIRIDIUM\b|\bPLATINO\b')


def tipo_de_bujia(descripcion):
    """'precalentamiento', 'encendido', o None si no es una bujía o no lo dice."""
    texto = _normalizar_desc(descripcion)
    if " BUJIA" not in texto:
        return None
    if _RE_BUJIA_PRECALENTAMIENTO.search(texto):
        return "precalentamiento"
    if _RE_BUJIA_ENCENDIDO.search(texto):
        return "encendido"
    return None


def tipos_de_sensor(descripcion):
    """Qué mide, si la descripción es de un SENSOR: {'MAP'}, {'ROTACION'}... Vacío si no es un
    sensor o no lo dice. El MAP mide presión, así que PRESION sola no cuenta como tipo."""
    texto = _normalizar_desc(descripcion)
    if " SENSOR " not in texto and " SONDA " not in texto and " BULBO " not in texto:
        return frozenset()
    tipos = {t for t, patron in _RE_TIPOS_DE_SENSOR if patron.search(texto)}
    # El interruptor del electroventilador se activa por temperatura y lo dice: no por eso es
    # el sensor de temperatura del reloj. Lo que manda es para qué es.
    if "ELECTROVENTILADOR" in tipos or "RETROMARCHA" in tipos:
        tipos.discard("TEMPERATURA")
    return frozenset(tipos)


def tipo_de_juego_de_motor(descripcion):
    """'completo', 'superior', 'inferior', 'completo sin tapa de cilindros', o None si no es un
    juego de juntas de motor."""
    texto = _normalizar_desc(descripcion)
    if not _RE_ES_KIT.search(texto):
        return None
    # «Sin TC» va antes que «superior»: «sin tapa de cilindros» también dice «tapa de cil».
    if _RE_JUEGO_SIN_TAPA.search(texto):
        return "completo sin tapa de cilindros"
    if _RE_JUEGO_SUPERIOR.search(texto):
        return "superior"
    if _RE_JUEGO_INFERIOR.search(texto):
        return "inferior"
    if _RE_JUEGO_COMPLETO.search(texto):
        return "completo"
    # «Jgo.Jtas. ROVER 214/216/218» no dice de qué juego es, pero ES un juego de juntas. Antes
    # quedaba como None —igual que una junta suelta— y el análisis lo daba por equivalente de
    # «JTA T.C. ROVER 111/214», la junta de tapa de cilindros sola: salía entre las «limpias».
    # El de carburador va aparte: se compara con los otros juegos de carburador por el rubro.
    if _RE_JUEGO_DE_JUNTAS.search(texto) and " CARBURADOR" not in texto:
        return JUEGO_SIN_DECIR_CUAL
    return None


# Ver tipo_de_juego_de_motor(). Es un juego, pero no se sabe cuál: no choca con ningún otro
# juego (puede ser cualquiera), sí con una junta suelta. Ver juegos_que_chocan().
JUEGO_SIN_DECIR_CUAL = "de juntas (sin decir cuál)"
_RE_JUEGO_DE_JUNTAS = re.compile(r'\b(JTAS|JUNTAS|JTA|JUNTA)\b')


def juegos_que_chocan(juego_a, juego_b):
    """¿Estos dos «juego» de firma dicen que son piezas distintas? Un juego contra una junta
    suelta, o dos juegos que dicen cuál son y no son el mismo (completo contra superior)."""
    if juego_a == juego_b or not (juego_a or juego_b):
        return False
    if juego_a and juego_b and JUEGO_SIN_DECIR_CUAL in (juego_a, juego_b):
        return False
    return True


def es_un_kit(descripcion):
    """¿La descripción dice que esto es un kit, un juego o un combo?

    Por la palabra —KIT, JUEGO, JGO, COMBO, SET— o porque nombra entre paréntesis los dos
    códigos que trae sumados, que es como escribe los suyos uno de los proveedores. Ver
    _RE_KIT_POR_SUMA."""
    if _RE_ES_KIT.search(_normalizar_desc(descripcion)):
        return True
    return bool(descripcion and _RE_KIT_POR_SUMA.search(str(descripcion)))


def _formas_del_codigo_para_buscar_en_kits(codigo):
    """El código como lo escribe el proveedor, y también sin su marca pegada atrás.

    Ver kits_que_traen_a_varios() para el porqué: varios proveedores se agregan la marca al número —«LSPFR6F11LUCAS»,
    «26001FISPA»— pero cuando arman el kit escriben el número pelado."""
    formas = [normalizar_texto(codigo)]
    limpio = re.sub(r'[^A-Za-z0-9]', '', codigo).upper()
    for marca in _MARCAS_QUE_SE_PEGAN_AL_CODIGO:
        if limpio.endswith(marca) and len(limpio) - len(marca) >= LARGO_MINIMO_CODIGO_EN_KIT:
            formas.append(limpio[:-len(marca)])
            break
    return formas


def _elegir_un_kit_por_descripcion(candidatos, mia, limite):
    """De las filas candidatas, un kit por descripción y la que sirve para vender.

    Un mismo kit está cargado varias veces con códigos distintos —el del proveedor, el de
    fábrica, el del cable— y las filas comparten descripción. En el mostrador eso es UN kit."""
    por_descripcion = {}
    for f in candidatos:
        desc = (f["Descripcion"] or "").strip()
        if not es_un_kit(desc) or desc == mia:
            continue
        vale = (f.get("Precio") is not None, (f.get("Stock") or 0) > 0)
        previo = por_descripcion.get(desc)
        if previo is None or vale > (previo.get("Precio") is not None,
                                     (previo.get("Stock") or 0) > 0):
            por_descripcion[desc] = f
    return list(por_descripcion.values())[:limite]


def kits_que_traen_a_varios(ids, limite=8):
    """Los kits del catálogo que traen adentro alguno de ESTOS repuestos, en UNA consulta.

    La pantalla de resultados preguntaba por los doce primeros productos de a uno, y cada
    pregunta es un `LIKE '%…%'` que ningún índice puede servir: doce barridos de las 70.888
    descripciones por cada búsqueda. Medido, 0,247 s por página de resultados, en el camino más
    caliente de la app — el que corre cada vez que alguien busca un repuesto en el mostrador.

    Con una sola consulta es UN barrido en vez de doce, y el reparto se hace en Python: se trae
    también `busqueda`, que es el mismo texto contra el que el LIKE compara, así que decidir a
    qué producto corresponde cada kit es mirar si esa forma del código está adentro.

    Los filtros que son POR PRODUCTO —que el kit no sea el producto mismo, y que no compartan
    descripción— se aplican al repartir y no en el SQL, porque en el SQL serían otra vez doce
    consultas. Devuelve {id del producto: [kits]}."""
    ids = [int(x) for x in dict.fromkeys(ids)]
    if not ids:
        return {}
    marcadores = ",".join("?" * len(ids))
    c.execute(f"SELECT id, codigo_raw, descripcion FROM productos WHERE id IN ({marcadores})",
              ids)
    origen = {f["id"]: f for f in filas_a_listas(c)}

    formas_por_id = {}
    todas_las_formas = []
    for pid in ids:
        fila = origen.get(pid)
        if not fila:
            continue
        codigo = str(fila["codigo_raw"] or "").strip()
        if len(re.sub(r'[^A-Za-z0-9]', '', codigo)) < LARGO_MINIMO_CODIGO_EN_KIT:
            continue
        formas = _formas_del_codigo_para_buscar_en_kits(codigo)
        formas_por_id[pid] = formas
        todas_las_formas.extend(formas)
    if not todas_las_formas:
        return {}

    _o_kit = " OR ".join(["p.busqueda LIKE ?"] * len(PALABRAS_DE_KIT))
    _o_codigo = " OR ".join(["p.busqueda LIKE ? ESCAPE '\\'"] * len(todas_las_formas))
    c.execute(f"""SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
                         m.nombre AS "Marca", p.precio AS "Precio", p.stock AS "Stock",
                         p.busqueda AS "_busqueda"
                  FROM productos p JOIN marcas m ON m.id = p.marca_id
                  WHERE ({_o_codigo}) AND ({_o_kit})""",
              [f"%{como_texto_en_like(f)}%" for f in todas_las_formas]
              + [f"%{k}%" for k in PALABRAS_DE_KIT])
    candidatos = filas_a_listas(c)

    salida = {}
    for pid, formas in formas_por_id.items():
        mia = (origen[pid]["descripcion"] or "").strip()
        mios = [f for f in candidatos
                if f["ID"] != pid
                and any(forma in (f["_busqueda"] or "") for forma in formas)]
        kits = _elegir_un_kit_por_descripcion(mios, mia, limite)
        if kits:
            salida[pid] = kits
    return salida


def que_trae_este_kit(producto_id, limite=12):
    """Lo que trae adentro un kit: los productos del catálogo que su descripción nombra.

    Es el camino inverso de kits_que_traen_a_varios(), y sirve para lo mismo del otro lado: el
    cliente pregunta por el kit y uno puede decirle qué lleva, o venderle solo la pieza que
    necesita si no quiere el kit entero."""
    c.execute("SELECT codigo_raw, descripcion FROM productos WHERE id = ?", (producto_id,))
    fila = c.fetchone()
    if not fila or not es_un_kit(fila["descripcion"]):
        return []
    mia = (fila["descripcion"] or "").strip()
    codigos = extraer_codigos_de_texto(separar_texto_pegado(fila["descripcion"]),
                                       codigo_propio=sanitizar(fila["codigo_raw"]))
    limpios = [sanitizar(x) for x in codigos]
    limpios = [x for x in limpios if len(x) >= LARGO_MINIMO_CODIGO_EN_KIT]
    if not limpios:
        return []
    salida, vistos, por_descripcion = [], set(), {}
    for tanda, marcadores in en_tandas(limpios):
        c.execute(f"""SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
                             m.nombre AS "Marca", p.precio AS "Precio", p.stock AS "Stock"
                      FROM productos p JOIN marcas m ON m.id = p.marca_id
                      WHERE p.codigo_clean IN ({marcadores}) AND p.id <> ?""", tanda + [producto_id])
        for f in filas_a_listas(c):
            desc = (f["Descripcion"] or "").strip()
            if desc == mia or f["ID"] in vistos:
                continue      # misma fila del kit cargada con otro código, no es el contenido
            vistos.add(f["ID"])
            # Igual que arriba: una pieza por descripción, y la que se puede vender.
            vale = (f.get("Precio") is not None, (f.get("Stock") or 0) > 0)
            previo = por_descripcion.get(desc)
            if previo is None or vale > (previo.get("Precio") is not None, (previo.get("Stock") or 0) > 0):
                por_descripcion[desc] = f
    return list(por_descripcion.values())[:limite]



@functools.lru_cache(maxsize=MAXIMO_DESCRIPCIONES_RECORDADAS)   # solo depende del texto
def familia_para_comparar(descripcion):
    """La familia de la pieza, pero «Sin clasificar» cuando la descripción es un KIT de varias.

    La regla de «si son de rubros distintos, el vínculo está mal» da por sentado que cada lado
    es UNA pieza. Un kit no lo es: «KIT CAB Y BUJ» trae cables Y bujías, así que elegirle una
    sola familia es arbitrario —gana la palabra que aparezca antes— y después ese sorteo se usa
    para castigar un vínculo que está bien.

    No es una sospecha: al mejorar la clasificación, los pares marcados como «rubro distinto»
    pasaron de 127 a 208, y 81 de esos 84 nuevos tenían un kit de un lado. Los otros 3 eran
    vínculos realmente malos (un filtro de combustible atado a un sensor MAP), que es lo que se
    quiere ver.

    Se pide que el kit nombre piezas de DOS familias o más: «KIT DE EMBRAGUE» es una sola cosa
    y ahí la comparación por rubro sigue sirviendo."""
    texto = _normalizar_desc(descripcion)
    if not _RE_ES_KIT.search(texto):
        return clasificar_repuesto(descripcion)
    # ACÁ NO SIRVE la expresión única de clasificar_repuesto(), y se probó: cambia 60
    # resultados sobre las 70.888 descripciones reales. El motivo es que las dos preguntas son
    # distintas. Allá se busca UNA clave, la de más a la izquierda, y la alternación la da
    # gratis. Acá hay que saber CUÁNTAS familias distintas nombra el texto, y una expresión
    # regular consume lo que va encontrando: en «JUNTA TAPA DE CILINDROS», si una clave es
    # «JUNTA TAPA», se la come entera y ya no puede ver también «TAPA» de otra familia.
    # El bucle prueba cada clave por separado, que es justo lo que hace falta.
    # («Jgo. Junta tapa de cilindros» pasaba de «Sin clasificar» a «Juntas y retenes» — puede
    # que sea mejor, pero eso es un cambio de criterio y no entra escondido en un arreglo de
    # velocidad. Si algún día se quiere cambiar, se mide aparte.)
    # El costo igual bajó: lo caro era clasificar_repuesto(), que se llama abajo.
    familias = set()
    for familia, claves in FAMILIAS_REPUESTO.items():
        for clave in claves:
            if any(texto.find(f" {forma} ") >= 0 for forma in (clave, clave + "S")):
                familias.add(familia)
                break
    if len(familias) >= 2:
        return "Sin clasificar"
    return clasificar_repuesto(descripcion)


def rubros_de_los_codigos_de_fabrica():
    """{id de un producto OEM: su rubro}, para los códigos de fábrica cuyo rubro no es el de
    su propia descripción sino el de los productos que lo citan.

    El producto OEM no tiene descripción propia: se crea copiando la de la PRIMERA fila de la
    lista que nombró ese número. Si esa fila era de otra pieza, el código hereda un rubro que
    no es el suyo. El caso que lo mostró: el 2H0919050B es la bomba de combustible de la
    Amarok, y lo citan dos bombas de FISPA (64051 y LEFS045) y también el filtro de esa bomba
    (24075, «FILTRO BOMBA DE COMBUSTIBLE ... REF ORIG 2H0919050B»). El filtro apareció primero,
    el código quedó como «Filtros», y las dos bombas salían con 0/100 y «Son de rubros
    distintos: Filtros y Combustible». Es al revés: el que no es el mismo repuesto es el filtro.

    Se decide por mayoría entre los productos de proveedor que están unidos al código, en los
    vínculos cargados y en los pendientes: hace falta que al menos dos digan el mismo rubro y
    que sean más de la mitad. Si no hay mayoría clara, queda el de la descripción.
    Se devuelven solo los que cambian. Una consulta por tabla, para todos los códigos de una
    vez: lo llaman el análisis de la cola, la auditoría y el recálculo de confianzas, que
    recorren miles de vínculos."""
    from collections import Counter
    vecinos = {}
    propias = {}
    for tabla in ("equivalencias", "equivalencias_pendientes"):
        for lado, otro in (("producto_a_id", "producto_b_id"), ("producto_b_id", "producto_a_id")):
            try:
                c.execute(f"""SELECT o.id AS oem, o.descripcion AS desc_oem,
                                     x.id AS xid, x.descripcion AS desc_x
                              FROM {tabla} e
                              JOIN productos o ON o.id = e.{lado}
                              JOIN marcas mo ON mo.id = o.marca_id
                              JOIN productos x ON x.id = e.{otro}
                              JOIN marcas mx ON mx.id = x.marca_id
                              WHERE mo.tipo = 'OEM' AND mx.tipo <> 'OEM'""")
                for r in c.fetchall():
                    propias[r["oem"]] = r["desc_oem"]
                    vecinos.setdefault(r["oem"], {})[r["xid"]] = r["desc_x"]
            except sqlite3.OperationalError as _err:
                anotar_error("rubros_de_los_codigos_de_fabrica", _err)
                return {}
    rubro_de = {}

    def _rubro(desc):
        if desc not in rubro_de:
            rubro_de[desc] = familia_para_comparar(desc) if desc else "Sin clasificar"
        return rubro_de[desc]

    salida = {}
    for oem, descs in vecinos.items():
        if len(descs) < 2:
            continue
        votos = Counter(f for f in map(_rubro, descs.values()) if f != "Sin clasificar")
        if not votos:
            continue
        rubro, cuantos = votos.most_common(1)[0]
        if cuantos >= 2 and cuantos * 2 > sum(votos.values()) and rubro != _rubro(propias[oem]):
            salida[oem] = rubro
    return salida


def rubro_del_codigo_frente_a(rubros_oem, producto_id, su_descripcion, descripcion_del_otro):
    """El rubro por mayoría de rubros_de_los_codigos_de_fabrica(), o None para usar el de la
    descripción.

    Contra la fila de la que el código sacó su descripción NO se usa: ahí los dos dicen lo
    mismo porque son la misma fila, y el rubro tiene que salir igual de los dos lados. Sin
    esta condición, «Junta Salida de Escape FIAT ... (4309031)» contra su propio 4309031 salía
    «rubros distintos: Juntas y retenes y Escape», porque los otros productos que citan ese
    número son juntas de Illinois que el clasificador pone en otro rubro."""
    if not rubros_oem or producto_id not in rubros_oem:
        return None
    if normalizar_texto(su_descripcion or "") == normalizar_texto(descripcion_del_otro or ""):
        return None
    return rubros_oem[producto_id]


# ============================================================
# CATÁLOGOS DE APLICACIONES (qué repuesto le va a cada auto)
# ============================================================
# Es OTRA cosa que una lista de precios. Una lista dice "este código cuesta tanto"; un catálogo
# de aplicaciones dice "a este auto le va este código". Es justamente el dato que no existe
# gratis de forma general —para eso están las bases licenciadas tipo TecDoc—, pero varios
# fabricantes publican el suyo: NGK, Bosch, Mann, SKF. Cargando esos catálogos, la búsqueda por
# VIN o por vehículo deja de adivinar desde las descripciones y pasa a tener el dato real.

# Fila que es solo el nombre de la marca: una celda con texto y el resto vacío
_RE_CONTINUACION = re.compile(r'\s*-?\s*(continua[çc][ãa]o|continuaci[óo]n|cont\.?)\s*$', re.I)


def _vacia(v):
    return v is None or str(v).strip() == ""


def _limpiar(v):
    return "" if _vacia(v) else " ".join(str(v).split())


def parsear_anios(texto):
    """Saca (desde, hasta) de las formas en que se escriben los años en estos catálogos:
    '2013 a 2020', '05/1999 a 08/2000', 'Desde 2000', 'Até 2005', '2011'."""
    t = _limpiar(texto)
    if not t:
        return None, None
    anios = [int(a) for a in re.findall(r'(19\d{2}|20\d{2})', t)]
    if not anios:
        return None, None
    bajo, alto = min(anios), max(anios)
    if re.search(r'desde|a partir', t, re.I):
        return bajo, None
    if re.search(r'\bat[ée]\b|hasta', t, re.I):
        return None, alto
    return bajo, (alto if alto != bajo else None)


def es_fila_de_marca(fila):
    """¿Es el título de una marca? Texto solo en la primera celda y nada más en la fila."""
    if _vacia(fila[0]):
        return False
    if any(not _vacia(x) for x in fila[1:]):
        return False
    texto = _limpiar(fila[0])
    # Los títulos de marca son cortos y en mayúsculas; "FIAT - Continuação" también cuenta
    base = _RE_CONTINUACION.sub("", texto).strip()
    if not base or len(base) > 30:
        return False
    letras = [ch for ch in base if ch.isalpha()]
    return bool(letras) and sum(1 for ch in letras if ch.isupper()) / len(letras) > 0.7


_RE_ANIO = re.compile(r'(19\d{2}|20\d{2})')


def parece_catalogo_de_aplicaciones(filas, muestra=200):
    """¿Este archivo es un catálogo de aplicaciones y no una lista de precios?

    Existe para evitar un error caro y silencioso: los dos se abren igual, y si un catálogo de
    aplicaciones entra por el importador de listas, carga los MODELOS DE AUTO como si fueran
    códigos de repuesto ('A4', 'Q3', 'S3') y los años como si fueran precios.

    Las señales, que no aparecen nunca en una lista de precios:
      · filas con una sola celda, en mayúsculas, que son el nombre de una marca de auto
      · una columna llena de rangos de años ('2013 a 2020', 'Desde 2000')
      · la primera columna que se repite mucho, porque el modelo se escribe una sola vez y
        las motorizaciones de abajo la dejan vacía
    Devuelve (True/False, motivo)."""
    datos = [f for f in filas[:muestra] if f and any(x is not None and str(x).strip() for x in f)]
    if len(datos) < 10:
        return False, ""

    marcas_solas = 0
    for fila in datos:
        try:
            if es_fila_de_marca(fila) and _limpiar(fila[0]).upper() in MARCAS_VEHICULO:
                marcas_solas += 1
        except Exception as _err:
            anotar_error("parece_catalogo_de_aplicaciones", _err)
            continue

    ancho = max(len(f) for f in datos)
    col_con_anios = 0
    for i in range(ancho):
        con_rango = sum(1 for f in datos
                        if i < len(f) and f[i] is not None
                        and re.search(r'(19|20)\d{2}\s*(a|-|hasta|até)\s*(19|20)\d{2}'
                                      r'|desde\s*(19|20)\d{2}|at[ée]\s*(19|20)\d{2}',
                                      str(f[i]), re.I))
        if con_rango >= len(datos) * 0.3:
            col_con_anios += 1

    razones = []
    if marcas_solas >= 2:
        razones.append(f"{marcas_solas} fila(s) son solo el nombre de una marca de auto")
    if col_con_anios:
        razones.append("hay una columna de rangos de años")
    # Hacen falta las dos señales: una sola se puede dar en una lista de precios común
    if marcas_solas >= 2 and col_con_anios:
        return True, " y ".join(razones)
    return False, ""


def detectar_columnas_aplicaciones(filas):
    """Encuentra en qué columna está cada cosa, mirando los valores.

    Hace falta porque un mismo catálogo mezcla formatos: el de NGK tiene tablas de 5 columnas y
    otras de 13, con los años y el código en posiciones distintas. Leer las de 13 con los
    índices de las de 5 hace que la columna de años se cargue como si fuera el código — y ahí
    terminan entrando 'Até 1991' o 'Desde 2005' como si fueran números de repuesto."""
    if not filas:
        return {"modelo": 0, "motor": 1, "comb": 2, "anios": 3, "codigo": 4}
    ancho = max(len(f) for f in filas)
    puntajes_anio = [0] * ancho
    puntajes_cod = [0] * ancho
    for fila in filas:
        for i in range(min(len(fila), ancho)):
            v = _limpiar(fila[i])
            if not v:
                continue
            if _RE_ANIO.search(v) or re.search(r'desde|at[ée]|hasta', v, re.I):
                puntajes_anio[i] += 1
            # Un código: tiene letras Y números, sin espacios de por medio, y no es un año
            elif re.fullmatch(r'[A-Z0-9][A-Z0-9\-./ ]{2,28}', v.upper()) and \
                    any(ch.isdigit() for ch in v) and any(ch.isalpha() for ch in v):
                puntajes_cod[i] += 1

    col_anios = max(range(ancho), key=lambda i: puntajes_anio[i]) if any(puntajes_anio) else 3
    # El código va DESPUÉS de los años en estos catálogos, y nunca es la columna del modelo
    candidatas = [i for i in range(ancho) if i not in (0, 1, col_anios)]
    col_codigo = max(candidatas, key=lambda i: puntajes_cod[i]) if candidatas else ancho - 1
    return {"modelo": 0, "motor": 1, "comb": min(2, ancho - 1),
            "anios": col_anios, "codigo": col_codigo}


def parsear_catalogo_aplicaciones(filas, col_modelo=0, col_motor=1, col_comb=2,
                                  col_anios=3, col_codigo=4):
    """Devuelve una lista de aplicaciones: qué código le corresponde a qué auto."""
    apps = []
    marca_actual = ""
    modelo_actual = ""

    for fila in filas:
        if not fila or len(fila) <= col_codigo:
            continue
        if all(_vacia(x) for x in fila):
            continue

        if es_fila_de_marca(fila):
            marca_actual = _RE_CONTINUACION.sub("", _limpiar(fila[col_modelo])).strip().upper()
            modelo_actual = ""      # al cambiar de marca se olvida el modelo anterior
            continue

        codigo = _limpiar(fila[col_codigo])
        if not codigo:
            continue

        # Si la primera celda trae algo, es un modelo nuevo. Si está vacía, sigue el anterior:
        # el catálogo no repite el nombre del modelo en cada motorización.
        if not _vacia(fila[col_modelo]):
            modelo_actual = _limpiar(fila[col_modelo])
        if not marca_actual or not modelo_actual:
            continue

        desde, hasta = parsear_anios(fila[col_anios] if col_anios < len(fila) else "")

        # Una celda puede traer VARIOS códigos: "BKR6EKPA / PMR7A" son dos bujías distintas
        # (la común y la de platino) que le van al mismo auto. Guardadas como un solo texto no
        # coinciden con nada; separadas, cada una queda buscable por su cuenta.
        codigos = dividir_codigos(codigo) or [codigo]
        for cod in codigos:
            # En algunas páginas las columnas se corren y lo que cae en el lugar del código es
            # el tipo de combustible ('G' de gasolina, 'B' de flex). Un código de repuesto de
            # una sola letra no existe: si entra, después aparece como si NGK recomendara la
            # pieza «B» para un Ford, que es una recomendación inventada.
            limpio_cod = sanitizar(cod)
            if len(limpio_cod) <= 2 or not any(ch.isdigit() for ch in limpio_cod):
                continue
            apps.append({
                "marca_auto": marca_actual,
                "modelo_auto": modelo_actual.upper(),
                "motor": _limpiar(fila[col_motor]) if col_motor < len(fila) else "",
                "combustible": _limpiar(fila[col_comb]) if col_comb < len(fila) else "",
                "anio_desde": desde,
                "anio_hasta": hasta,
                "codigo": cod,
            })
    return apps


def tablas_de_archivo(archivo):
    """Devuelve las tablas de un PDF o de una planilla, para leer catálogos de aplicaciones."""
    nombre = archivo if isinstance(archivo, str) else getattr(archivo, "name", "")
    if nombre.lower().endswith(".pdf"):
        import pdfplumber
        if not isinstance(archivo, str):
            archivo.seek(0)
        tablas = []
        with pdfplumber.open(archivo) as pdf:
            for pagina in pdf.pages:
                tablas.extend(t for t in pagina.extract_tables() if t)
        return tablas
    return [leer_excel(archivo)]


def guardar_aplicaciones(apps, marca_repuesto, origen="", tipo_pieza=""):
    """Guarda las aplicaciones leídas de un catálogo. Devuelve cuántas se cargaron."""
    if not apps:
        return 0
    with db_lock:
        c.executemany("""INSERT OR IGNORE INTO aplicaciones
                         (marca_auto, modelo_auto, motor, combustible, anio_desde, anio_hasta,
                          codigo, codigo_clean, marca_repuesto, tipo_pieza, origen)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      [(a["marca_auto"], a["modelo_auto"], a["motor"], a["combustible"],
                        a["anio_desde"], a["anio_hasta"], a["codigo"], sanitizar(a["codigo"]),
                        marca_repuesto.strip().upper(), (tipo_pieza or "").strip(), origen)
                       for a in apps])
        conn.commit()
    return len(apps)


# Palabras que aparecen en las descripciones y NO dicen qué pieza es: son del auto, del envase
# o relleno del proveedor. Si entran en la firma, dos piezas distintas del mismo auto terminan
# pareciendo la misma.
# Un punto entre dos letras es una abreviatura pegada a la palabra que sigue («Jta.Tapa»),
# no parte de un código. Entre números sí es parte del dato, y por eso el patrón pide letras
# de los dos lados.
_RE_PUNTO_ENTRE_LETRAS = re.compile(r'([A-ZÁÉÍÓÚÑ])\.([A-ZÁÉÍÓÚÑ])')

# LAS ABREVIATURAS DE UNA LETRA CON PUNTO. IMPERIAL escribe «JTA T.C.» (junta tapa de
# cilindros, 1.072 veces), «JTA T.V.» (tapa de válvulas, 267), «JTA M.ESC.» / «S.ESC.»
# (múltiple / salida de escape), «M.ADM.», «A.LEVA», «T.DIST.», «C.VEL.», «R.V.». La letra
# sola se tiraba por corta, así que «JTA T.V. DODGE 1500» quedaba como «JUNTA» y nada más: sin
# ninguna palabra que dijera CUÁL junta, se emparejaba con la de tapa de cilindros, la de
# escape o la de carburador del mismo auto. Se expanden antes de partir en palabras.
# Solo las que se contaron en las descripciones reales, y con lo que viene después cuando la
# letra sola es ambigua: «M.» también es M.BENZ o M.FIRE, y «T.» es «T.Y CODO».
_ABREVIATURAS_CON_PUNTO = [
    # «JTA S.TAPA A.LEVA» es la junta de la sobretapa del árbol de levas, que en los motores con
    # el árbol arriba es la misma junta que las otras listas llaman «de tapa de válvulas».
    (re.compile(r'\bS\.\s?TAPA\s+A\.\s?LEVAS?\b'), "TAPA VALVULA "),
    (re.compile(r'\bT\.\s?C\b\.?'), "TAPA CILINDRO "),
    (re.compile(r'\bT\.\s?V\b\.?'), "TAPA VALVULA "),
    (re.compile(r'\bT\.(?=\s?(?:CIL|DIST|VALV|TERM|BOT|TRAS|DEL|INF|SUP|FRONT|LAT|BALANC))'),
     "TAPA "),
    (re.compile(r'\bM\.(?=\s?(?:ESC|ADM))'), "MULTIPLE "),
    (re.compile(r'\bS\.(?=\s?ESC)'), "SALIDA "),
    (re.compile(r'\bA\.\s?LEVAS?\b'), "ARBOL LEVAS "),
    # «JTA TAPA AR.LEVA FIAT 128 0.5m»: la de la tapa del árbol de levas del 128, que no es la de
    # tapa de cilindros. Sin leerla, solo la separaba el precio.
    (re.compile(r'\bAR\.\s?LEVAS?\b'), "ARBOL LEVAS "),
    # «JTA INSP. T.CIL. PEUGEOT XUD9» es la tapita de inspección, no la junta de la tapa.
    (re.compile(r'\bINSP\b\.?'), "INSPECCION "),
    (re.compile(r'\bPRECAM\b\.?'), "PRECAMARA "),
    # «JTA BASE CARB. FIAT REGATTA 100» es la base del carburador.
    (re.compile(r'\bBASE\s+CARB\b\.?'), "BASE CARBURADOR "),
    # «JTA.C/TERMOST. J. DEERE», «JTA J.DEERE TAPA SUP. TRANSMIS»
    (re.compile(r'\bTERMOST\b\.?'), "TERMOSTATO "),
    (re.compile(r'\bTRANSMIS\b\.?'), "TRANSMISION "),
    # «JUNTA BASE DIST.- VOLKSWAGEN» es la base del DISTRIBUIDOR de encendido, no la tapa de
    # distribución («JTA T.DIST VW GOL»).
    (re.compile(r'\bBASE\s+DIST\b\.?'), "BASE DISTRIBUIDOR "),
    (re.compile(r'\bC\.\s?VEL\b\.?'), "CAJA VELOCIDAD "),
    (re.compile(r'\bR\.\s?V\b\.?'), "RETEN VALVULA "),
    # «JTA RAD.ACEITE IVECO EURO TRA» es la del radiador de aceite, y concordaba con la junta de
    # cárter del mismo motor porque las dos dicen ACEITE e IVECO.
    (re.compile(r'\bRAD\b\.?(?=\s?(?:ACEITE|AGUA))'), "RADIADOR "),
]


def _expandir_abreviaturas_con_punto(texto):
    """Ver _ABREVIATURAS_CON_PUNTO. Recibe el texto ya en mayúsculas."""
    if "." not in texto:
        return texto
    for patron, reemplazo in _ABREVIATURAS_CON_PUNTO:
        texto = patron.sub(reemplazo, texto)
    return texto

# La coma decimal. Illinois escribe «1,6» y todos los demás «1.6»: son 3.105 descripciones de
# esa lista contra 23.244 con punto. Comparadas tal cual, las cilindradas de las dos nunca se
# cruzan y firmas_compatibles() cortaba con «cilindradas distintas» — o sea que la lista más
# nueva quedaba rechazada de entrada contra el resto del catálogo por cómo escribe un número.
# La pantalla de vehículos ya lo pasaba a punto antes de comparar; acá faltaba.
# De paso arregla otra cosa: la coma no estaba entre los caracteres que forman una palabra, así
# que «1,9TDI» se partía en «1» y «9TDI», y ese «9TDI» suelto —129 veces en el catálogo— hacía
# de modelo compartido entre un 1,9TDI y un 2,9TDI.
_RE_COMA_DECIMAL = re.compile(r'(?<=\d),(?=\d)')

# Una cilindrada o una cantidad de válvulas NO dicen para qué auto es. «16V» está en 3.513
# descripciones, «2.0I» en 142: compartir eso es compartir el idioma, no el vehículo.
# Sin esto, «BOBINA ESCORT/ORION 1.8i 16V ZETEC» salía equivalente a una bobina de
# «PEUGEOT 406 1.8i, 16V, 306 1.8 16V» — un Ford contra un Peugeot, unidos por «1.8I, 16V».
# El número solo («1.6», «2.0») ya quedaba afuera porque el núcleo descarta lo que es puro
# número: que «1.6I» contara y «1.6» no fue siempre un accidente del patrón, nunca una decisión.
# El patrón pide la coma decimal o la V de las válvulas, y por eso no se lleva puestos los
# modelos que son número y letra: 320I, 318I, 525D, 310D y 412D son BMW y Mercedes de verdad,
# y son de los datos más específicos que hay en estas listas.
# La cilindrada exacta en centímetros cúbicos SÍ queda: «843CC» no es una forma de hablar, es
# un motor. Es lo único que une la «Junta Tapa Cil. ASIA/KIA TOWNER 843CC» con la
# «Jta.Tapa Cil. DAIHATSU HI-JET 843CC» —el Towner es un Hijet con otro nombre— y sacándola
# ese par, que está bien, se perdía.
_RE_SOLO_MOTORIZACION = re.compile(
    r'^(?:\d{1,2}[.,]\d[A-Z]{0,3}|\d{1,2}V)'
    r'(?:/(?:\d{1,2}[.,]\d[A-Z]{0,3}|\d{1,2}V))*/?$')

# Una medida suelta o la palabra que la anuncia: «ESP», «1.10MM», «1,63MM». En una junta el
# espesor dice cuál de las variantes es, no para qué auto va: dos juntas de 1,10 mm de dos
# motores distintos lo comparten igual. Ver «la marca sola no alcanza» en firmas_compatibles().
# El número entero pelado NO: «128» es un Fiat 128, y ese sí dice para qué auto es.
_RE_MEDIDA_SUELTA = re.compile(r'^(?:ESP|ESPESOR|\d+[.,]\d+(?:MM|CM|MTS?)?|\d+(?:MM|CM|MTS?))$')

_RUIDO_EN_FIRMA = {
    "DESPIECE", "JUEGO", "JGO", "KIT", "PARA", "CON", "SIN", "DEL", "LOS", "LAS", "POR",
    "UNIDAD", "UN", "UNA", "IZQ", "DER", "MM", "CM", "ORIGINAL", "ORIG", "ALTERNATIVO",
    "NACIONAL", "IMPORTADO", "REPUESTO", "PIEZA", "AUTO", "MOTOR", "CAJA", "TIPO",
    # El relleno de las listas, contado sobre las descripciones reales: «REF» aparece 11.421
    # veces —es el «REF ORIG» de una de ellas—, «TODOS» 1.251, «DESDE» 552. No dicen qué pieza
    # es ni para qué auto, y tienen que salir del núcleo ENTERO y no pasar del lado de la
    # pieza: si cuentan como nombre de la pieza, «BOBINA DE IGNICION ... REF ORIG» deja de
    # parecerse a «BOBINA ... desde 2012» y se pierden vínculos que están bien.
    "REF", "OEM", "TODOS", "DESDE", "HASTA", "ENTRE", "ALTA", "FAMILIA", "CANTIDAD",
    "HORARIO", "SENTIDO", "LINEA", "LIVIANA", "LIVIANOS", "PESADA", "MOTORES", "CANALES",
    "POTENCIA", "VOLTS", "ANCHO", "DIAMETRO", "AGUJEROS", "DIENTES", "PINES", "VIAS", "BAR",
    "MODULO",
    # Los COLORES, afuera de las dos preguntas. Del lado del auto, «aislante NEGRO» contra
    # «tapón NEGRO» contaba como algo en común y salvaba de «modelos distintos» a un bulbo de
    # Escort y Gol contra uno de F100 y Cargo. Del lado de la pieza tampoco van: probado, «aro
    # GRIS» contra «aro NARANJA» hacía que dos inyectores «no coincidieran en qué pieza es».
    "NEGRO", "NEGRA", "BLANCO", "BLANCA", "GRIS", "AZUL", "ROJO", "ROJA", "VERDE", "MARRON",
    "AMARILLO", "AMARILLA", "NARANJA", "CELESTE", "VIOLETA", "COLOR",
}

# Siglas técnicas que definen QUÉ pieza es, no de qué auto. Dos válvulas del mismo auto, una
# PCV y otra EGR, no son la misma pieza — y «VALVULA» sola no las distingue. Lo mismo con los
# sensores: MAF, MAP, IAT y TPS son cuatro sensores distintos del mismo rubro.
_SIGLAS_DE_PIEZA = {
    "PCV", "EGR", "MAF", "MAP", "IAT", "TPS", "ECT", "CKP", "CMP", "IAC", "ABS", "EGT",
    "VVT", "ACC", "TDC", "PMS", "GNC", "GLP", "HDI", "TDI", "CRDI", "JTD",
}


_POSICIONES = {
    "DELANTERO": "DELANTERO", "DELANTERA": "DELANTERO", "DEL.": "DELANTERO",
    "TRASERO": "TRASERO", "TRASERA": "TRASERO", "TRAS.": "TRASERO",
    "SUPERIOR": "SUPERIOR", "INFERIOR": "INFERIOR",
    "IZQUIERDO": "IZQUIERDO", "IZQUIERDA": "IZQUIERDO",
    "DERECHO": "DERECHO", "DERECHA": "DERECHO",
    "INTERNO": "INTERNO", "INTERIOR": "INTERNO",
    "EXTERNO": "EXTERNO", "EXTERIOR": "EXTERNO",
}


# Modelos de auto que aparecen en las descripciones. Se necesita para saber dónde termina el
# nombre de la pieza y dónde empieza el auto. Sale de MARCAS_VEHICULO y de los modelos que ya
# vienen en los catálogos de aplicaciones cargados.
# Es de cada PASADA del script a propósito (ver del_proceso()): armarla cuesta 60 ms medidos
# sobre las 112.764 aplicaciones reales, y así una lista de aplicaciones recién importada entra
# en el toque siguiente sin tener que avisarle a nadie.
_MODELOS_CACHE = {"lista": None}


def _modelos_conocidos():
    if _MODELOS_CACHE["lista"] is not None:
        return _MODELOS_CACHE["lista"]
    modelos = set()
    for mv in MARCAS_VEHICULO:
        modelos.update(w for w in mv.split() if len(w) >= 3)
    # palabra -> marcas con las que figura en la columna de modelo de las aplicaciones
    de_aplicaciones = {}
    try:
        # SIN TOPE. Había un LIMIT 3000, y la base real tiene 4.042 modelos distintos: el corte
        # caía donde caía y dejaba afuera GOL, GOLF, POLO, MEGANE, LOGAN, KANGOO, HILUX,
        # PASSAT y VENTO, los más vendidos. Sin ellos, «Sonda Lambda VW Gol» contra «SONDA
        # LAMBDA VW PASSAT» no tenía modelo del que hablar y el par quedaba en «nada dice que
        # sean la misma pieza» en vez de descartarse por modelos distintos.
        c.execute("SELECT DISTINCT marca_auto, modelo_auto FROM aplicaciones")
        for fila in c.fetchall():
            for w in normalizar_texto(fila["modelo_auto"] or "").split():
                if len(w) >= 3:
                    de_aplicaciones.setdefault(w, set()).add(fila["marca_auto"])
    except Exception as _err:
        anotar_error("_modelos_conocidos", _err)
    modelos |= set(de_aplicaciones) - _modelos_que_andan_con_otras_marcas(de_aplicaciones)
    # Palabras que aparecen en la columna de modelo de las aplicaciones y no son modelos: «desde
    # 2008», «CLASE C COMPRESOR», «EURO 3», «ASTRA GLS». Con DESDE como modelo, una sonda de
    # Corolla «desde 2008» salía de un auto llamado DESDE.
    # Solo estas, a mano: sacar todo el vocabulario de pieza se llevaba también GALILEO y
    # ZENITH, que son marcas de carburador y son justo lo que empareja «JUNTAS CHEV Y GALILEO»
    # con el juego de juntas del carburador del Chevy.
    modelos -= _PALABRAS_QUE_NO_SON_MODELOS
    _MODELOS_CACHE["lista"] = modelos
    return modelos


def _huella_parecida(guardada, actual, tolerancia=0.02):
    """¿La huella «productos|último id|modelos» guardada sigue sirviendo? Sí, si la cantidad de
    productos y la de modelos no se movieron más que la tolerancia. Ver
    _modelos_que_andan_con_otras_marcas()."""
    try:
        g = [int(x) for x in str(guardada).split("|")]
        a = [int(x) for x in str(actual).split("|")]
    except ValueError:
        return False
    if len(g) != 3 or len(a) != 3:
        return False
    return all(abs(a[i] - g[i]) <= tolerancia * max(g[i], 1) for i in (0, 2))


def _modelos_que_andan_con_otras_marcas(de_aplicaciones, minimo=20):
    """Las palabras de la columna de modelo que en las descripciones NO andan con su marca.

    Las aplicaciones deducidas de las descripciones traen basura en el modelo: «DIAMETRO» como
    modelo de Fiat, «CAMION», «FAMILIA», «PISTON», «VAN». Un modelo de verdad aparece casi
    siempre junto a su marca —GOL con Volkswagen en el 85% de las descripciones que lo nombran,
    MEGANE con Renault en el 95%, COROLLA con Toyota en el 96%— y esas palabras no: DIAMETRO
    está con Fiat en el 13% y con OTRAS marcas en el 80%.

    Se saca la que anda con su marca menos del 30% de las veces y con otras al menos el 20%. La
    segunda condición cuida a las que casi nunca van con marca, que son de las dos clases:
    TORINO (se escribe sin IKA) y GALILEO (marca de carburador) sirven, MACHO y PRIMARIO no.
    Esas no se distinguen contando y las que no sirven están a mano en
    _PALABRAS_QUE_NO_SON_MODELOS.

    Recorrer el catálogo cuesta 2,6 s con 86.000 descripciones, y eso era en cada arranque de
    la app. Se guarda el resultado en la configuración con una huella del catálogo —cuántos
    productos, el último id, cuántos modelos— y se rehace solo cuando cambia DE VERDAD.

    Se rehacía con cualquier cambio, y las tareas de fondo agregan aplicaciones todo el día: con
    UN modelo más sobre 4.038, la búsqueda siguiente del mostrador tardaba 5 s. Lo que se calcula
    son palabras que aparecen al menos 20 veces y casi nunca con su marca; un 2 % más de
    catálogo no las cambia. Se rehace cuando productos o modelos cambian más que eso, que es lo
    que pasa al importar una lista."""
    try:
        _n_prod, _max_id = c.execute(
            "SELECT COUNT(*), COALESCE(MAX(id), 0) FROM productos").fetchone()
        _huella = f"{_n_prod}|{_max_id}|{len(de_aplicaciones)}"
        _guardado = json.loads(obtener_config("modelos_que_no_son", "") or "{}")
        if _guardado.get("huella") == _huella or _huella_parecida(_guardado.get("huella"),
                                                                   _huella):
            return set(_guardado.get("palabras") or ())
        c.execute("SELECT descripcion FROM productos WHERE descripcion IS NOT NULL")
        descripciones = [r["descripcion"] for r in c.fetchall()]
    except (sqlite3.OperationalError, ValueError) as _err:
        anotar_error("_modelos_que_andan_con_otras_marcas", _err)
        return set()
    total, con_la_suya, con_otras = {}, {}, {}
    for desc in descripciones:
        palabras = set(re.split(r"[^A-Z0-9]+", normalizar_texto(desc))) & de_aplicaciones.keys()
        if not palabras:
            continue
        marcas = {m for m, _cat, _resto in marcas_vehiculo_en(desc)}
        for w in palabras:
            total[w] = total.get(w, 0) + 1
            if marcas & de_aplicaciones[w]:
                con_la_suya[w] = con_la_suya.get(w, 0) + 1
            elif marcas:
                con_otras[w] = con_otras.get(w, 0) + 1
    palabras = {w for w, n in total.items()
                if n >= minimo and con_la_suya.get(w, 0) < 0.3 * n
                and con_otras.get(w, 0) >= 0.2 * n}
    try:
        guardar_config("modelos_que_no_son",
                       json.dumps({"huella": _huella, "palabras": sorted(palabras)}))
    except sqlite3.OperationalError as _err:
        anotar_error("_modelos_que_andan_con_otras_marcas", _err)
    return palabras


_PALABRAS_QUE_NO_SON_MODELOS = frozenset({
    "DESDE", "HASTA", "TODOS", "TODAS", "MODELOS", "MODELO", "VERSION", "VERSIONES", "MOTOR",
    "COMPRESOR", "EURO", "GLS", "GLX", "CVT", "BSE", "CON", "SIN", "PARA", "APLICACIONES",
    # Las que casi nunca van con una marca y no son modelos (ver
    # _modelos_que_andan_con_otras_marcas()): «TERMINAL MACHO», «FILTRO PRIMARIO», «ROSCA UNF».
    "MACHO", "PRIMARIO", "PLUS", "UNF", "HOJA", "RAPIDO", "FIBRA", "PLANO", "CURVO", "FINA",
    "FINO", "GRAF", "BCA", "DIAMETRO", "ANCHO",
    # «Blue HDI», «BlueMotion»: tecnología, no un auto.
    "BLUE",
    # «NEW LEONE», «NEW BEETLE», «UNO NUEVO»: la versión, no el auto. Como «modelo en común»
    # unía una junta de Subaru con una de Volkswagen y salteaba el control de marcas distintas.
    "NEW", "NUEVO", "NUEVA",
    # Marcas de sensores que las listas citan como referencia («Vernet OS3573 ERA 330366 FAE
    # 12436») y palabras sueltas: «ANTES ERA TAPON NEGRO». ERA como «modelo en común» unía un
    # bulbo de Ford F100 con uno de Chevrolet Aveo.
    "ERA", "FAE", "VERNET", "ANTES", "ELECTRONICO", "ELECTRONICA",
})


class _ModelosLazy:
    """Para poder escribir `w in MODELOS_CONOCIDOS` sin recalcular la lista en cada palabra."""
    def __contains__(self, palabra):
        return palabra in _modelos_conocidos()


MODELOS_CONOCIDOS = _ModelosLazy()


def aplicaciones_desde_descripciones(limite=None, desde_id=0):
    """Lee de la descripción a qué auto le va cada producto, para poder buscar por vehículo.

    La relación pieza-vehículo ya viene en las listas de los proveedores: «JUNTA TAPA DE
    CILINDROS FORD TAUNUS 1969/78» dice marca, modelo y años. Hasta ahora eso solo se guardaba
    si además cargabas el catálogo de aplicaciones del fabricante, que es un archivo aparte que
    casi ningún proveedor manda.

    Compone con lo que ya existe: derivar_equivalencias_de_aplicaciones() cruza productos que le
    sirven a los mismos autos, así que llenar esta tabla genera equivalencias nuevas solas.

    Por eso mismo hay que ser cuidadoso: un modelo mal leído termina en una equivalencia falsa.
    El modelo NO se adivina — tiene que estar en la lista que modelos_de_marca() ya deduce del
    propio catálogo, contando en cuántas marcas distintas aparece cada palabra. Un ASTRA aparece
    casi solo en Chevrolet y es un modelo; un BOMBA aparece en todas y no lo es. Si el modelo no
    está confirmado así, la fila no se genera: sin modelo no sirve para buscar por vehículo, y
    con un modelo inventado sirve para equivocarse.

    desde_id: solo los productos con id mayor. Es como corre después de importar (ver
    descubrimiento_post_importacion()). Sin eso releía cada vez todas las descripciones de las
    que antes no había sacado ningún auto —casi todas—: con 60 proveedores, 75 s de lectura y
    144 s de escritura después de cada lista. La relectura entera la sigue haciendo la tarea de
    fondo cuando se la pide (aplicaciones_pendientes), y el botón de Administrar."""
    ceder_al_mostrador()      # antes de la lectura grande. Ver ceder_al_mostrador().
    try:
        c.execute("""SELECT p.id, p.codigo_raw, p.codigo_clean, p.descripcion, m.nombre AS marca
                     FROM productos p JOIN marcas m ON m.id = p.marca_id
                     WHERE p.id > ? AND p.descripcion IS NOT NULL AND p.descripcion <> ''
                       AND p.codigo_clean NOT IN (SELECT codigo_clean FROM aplicaciones
                                                   WHERE codigo_clean IS NOT NULL)
                     ORDER BY p.id""", (desde_id,))
        filas = filas_a_listas(c)
    except sqlite3.OperationalError as _err:
        anotar_error("aplicaciones_desde_descripciones", _err)
        return []

    # El mismo testigo de caché que usa la pantalla de repuestos por vehículo: cambia al cargar
    # una lista nueva, así los modelos se recalculan cuando el catálogo creció.
    _version_cat = version_del_catalogo()

    # Los códigos del catálogo, una sola vez: hace falta para descartar los «modelos» que en
    # realidad son el número del proveedor. Preguntarlo por palabra sería una consulta por
    # token sobre 70.888 productos.
    try:
        c.execute("SELECT DISTINCT codigo_clean FROM productos")
        _codigos_del_catalogo = {r["codigo_clean"] for r in c.fetchall()}
    except sqlite3.OperationalError as _err:
        anotar_error("aplicaciones_desde_descripciones/codigos", _err)
        _codigos_del_catalogo = set()

    modelos_por_marca = {}
    salida = []
    for f in filas:
        ceder_al_mostrador()
        # TODAS las marcas que nombra, cada una con SU pedazo de texto. Antes se usaba
        # separar_por_marca_vehiculo(), que devuelve una sola, y eso rompía de las dos maneras
        # posibles sobre la misma descripción:
        #   «BULBO DE PRESION DE ACEITE VW Passat - Santana - Gol - ALFA ROMEO 155 T Spark -
        #    FORD Galaxy - Escort - SEAT Toledo»
        # De los cuatro autos se guardaba uno, así que el repuesto desaparecía del catálogo de
        # los otros tres; y el que se guardaba era ALFA ROMEO con el modelo leído de su propio
        # pedazo, «T Spark», que es el motor Twin Spark y no un modelo.
        # marcas_vehiculo_en() ya hace esto bien —le corta a cada marca su texto, hasta la
        # marca siguiente— y es la que usa la pantalla de vehículos desde hace rato.
        for marca_auto, _categoria, resto in marcas_vehiculo_en(f["descripcion"]):
            if not marca_auto or not resto:
                continue
            if marca_auto not in modelos_por_marca:
                try:
                    # Con muchas filas, todas las marcas de una pasada; con pocas (una lista
                    # chica), de a una: la pasada entera lee todo el catálogo.
                    modelos_por_marca[marca_auto] = {
                        t for t, _n in (modelos_de_todas_las_marcas(_version_cat).get(marca_auto, [])
                                        if len(filas) > 3000
                                        else modelos_de_marca(marca_auto, _version_cat))}
                except Exception as _err:
                    anotar_error("aplicaciones_desde_descripciones", _err)
                    modelos_por_marca[marca_auto] = set()
            conocidos = modelos_por_marca[marca_auto]
            # TODOS los modelos que nombra ese pedazo, no el primero. Las listas escriben
            # «FIAT PALIO/SIENA/UNO 1.3» y «RENAULT CLIO MEGANE KANGOO», y guardando uno solo
            # el repuesto desaparecía del catálogo de los otros: de 41.857 productos, 35.061
            # quedaban con UNA sola aplicación. Cada modelo se valida igual contra los que la
            # app ya reconoce para esa marca, así que no se inventa ninguno.
            vistos_modelo = set()
            modelos_hallados = []
            for _t in re.findall(r"[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9\-]{2,}", resto.upper()):
                if _t in conocidos and _t not in vistos_modelo:
                    # Un MOTOR no es un modelo. modelos_de_marca() lo confirma igual —«K4M»
                    # aparece muchas veces y casi solo en Renault, que es justo su regla— y de
                    # ahí salían 6.048 filas donde el «auto» era una motorización. Nadie busca
                    # repuestos «para un K4M», y como el motor aparece en decenas de
                    # descripciones, junta entre sí todo lo que lo nombre.
                    # Ver parece_designacion_de_motor() para los números y para el intento
                    # equivocado que vino antes.
                    if parece_designacion_de_motor(_t):
                        continue
                    # Y el que es directamente un código del catálogo con forma de código.
                    # Ver parece_un_codigo_y_no_un_modelo().
                    if parece_un_codigo_y_no_un_modelo(_t, _codigos_del_catalogo):
                        continue
                    vistos_modelo.add(_t)
                    modelos_hallados.append(_t)
            if not modelos_hallados:
                continue
            desde, hasta = extraer_anios(f["descripcion"])
            _pieza_de_esta = clasificar_repuesto(f["descripcion"])
            _combustible_de_esta = combustible_desde_descripcion(f["descripcion"]) or ""
            _motor_de_esta = motor_desde_descripcion(f["descripcion"]) or ""
            # El tipo de pieza hace falta de verdad: derivar_equivalencias_de_aplicaciones()
            # descarta las filas que no lo tienen, y con razón —sin él cruzaría una bujía con
            # un filtro por ir al mismo auto—. Se saca con el mismo clasificador que ya usa el
            # resto. Y el motor va vacío, no NULL: esa consulta compara motor = motor, y en SQL
            # dos NULL nunca son iguales, así que con NULL estas filas no se cruzarían ni entre
            # ellas.
            for modelo in modelos_hallados:
                salida.append({
                    "_id": f["id"], "Código": f["codigo_raw"], "Marca": f["marca"],
                    "Descripción": f["descripcion"],
                    "Auto": marca_auto, "Modelo": modelo,
                    "Años": ("—" if not desde else f"{desde}"
                              + (f"–{hasta}" if hasta else " en adelante")),
                    "Pieza": _pieza_de_esta,
                    "_clean": f["codigo_clean"], "_desde": desde, "_hasta": hasta,
                    "_combustible": _combustible_de_esta, "_motor": _motor_de_esta,
                })
        # Sin tope. Estaba en 400 y el catálogo real da 52.534 aplicaciones: se cargaba el 0,8%
        # de lo que las descripciones ya dicen, y esta tabla es la que hace andar la búsqueda
        # por vehículo y la que cruza productos que le sirven al mismo auto. Leerlas todas
        # tarda 30,6 s contra 12,2 s, una vez, apretando un botón.
        if limite and len(salida) >= limite:
            break
    return salida


def aprender_motores_que_van_juntos():
    """Qué motores se llevan entre sí para cada tipo de pieza. Devuelve cuántos pares aprendió.

    EL PROBLEMA QUE RESUELVE. El veto por motor dice «si los dos declaran motor y es distinto,
    no son equivalentes». Suena bien y está mal seguido: las bujías del TU5JP4 y las del EW10
    son las mismas, pero cada proveedor escribe en su descripción los motores que se le ocurren.
    Uno pone TU5JP4, el otro pone EW10, y el veto separa dos piezas que se reemplazan.

    LA EVIDENCIA YA ESTÁ EN EL CATÁLOGO, y no hace falta ningún dato de afuera: cuando un
    proveedor vende UN producto y en su descripción nombra VARIOS motores, está diciendo que esa
    pieza entra en todos. «Juego de Descarbonización PEUGEOT/CITROEN … EW10D EW10J4» es el
    proveedor declarando que para esa pieza los dos motores son el mismo caso.

    Sobre el catálogo real hay 838 descripciones que nombran dos motores o más, y de ahí salen
    **1.334 pares de motores con su tipo de pieza**. El ejemplo del mostrador está adentro:
    TU5JP4 con EW10J4 aparecen juntos en una pieza de combustible.

    SE EXIGE EL MISMO TIPO DE PIEZA, y no es un detalle. Que K4M y K7M compartan una bomba de
    agua no prueba que compartan la junta de tapa de cilindros —son un 16 válvulas y un 8
    válvulas, y la tapa es otra—. Pidiendo la misma familia, de los pares que el veto frena se
    liberan 3.755 y quedan frenados 16.056; sin pedirla se liberarían 6.408, y varios de esos
    de más son justamente juntas entre motores de distinta tapa.

    No es transitivo a propósito: que A vaya con B y B con C no dice nada de A con C."""
    try:
        c.execute("""SELECT p.descripcion FROM productos p JOIN marcas m ON m.id = p.marca_id
                     WHERE m.tipo <> 'OEM' AND p.descripcion IS NOT NULL AND p.descripcion <> ''""")
        descripciones = [r["descripcion"] for r in c.fetchall()]
    except sqlite3.OperationalError as _err:
        anotar_error("aprender_motores_que_van_juntos", _err)
        return 0

    juntos = {}
    for descripcion in descripciones:
        motores = sorted({t.upper() for t in _RE_TOKEN_DE_MOTOR.findall(descripcion)
                          if parece_designacion_de_motor(t)})
        if len(motores) < 2:
            continue
        familia = clasificar_repuesto(descripcion)
        for i, uno in enumerate(motores):
            for otro in motores[i + 1:]:
                juntos[(uno, otro, familia)] = juntos.get((uno, otro, familia), 0) + 1
    if not juntos:
        return 0
    with db_lock:
        c.executemany("""INSERT INTO motores_compatibles (motor_a, motor_b, tipo_pieza, veces)
                         VALUES (?, ?, ?, ?)
                         ON CONFLICT(motor_a, motor_b, tipo_pieza)
                         DO UPDATE SET veces = excluded.veces""",
                      [(a, b, f, n) for (a, b, f), n in juntos.items()])
        conn.commit()
    return len(juntos)


def aplicar_aplicaciones_deducidas(filas):
    """Guarda las aplicaciones leídas de las descripciones. Devuelve cuántas se cargaron.

    Quedan con origen 'deducida' a propósito: así se distinguen de las que vinieron de un
    catálogo de fabricante, que son palabra del que fabrica la pieza, y se pueden revisar o
    borrar aparte si alguna salió mal."""
    if not filas:
        return 0
    # El combustible y el motor van vacíos y no NULL: la consulta que cruza por auto compara
    # columna = columna, y en SQL dos NULL nunca son iguales.
    # El candado se suelta cada tanda: son 112.499 filas, y con una sola toma la pantalla de la
    # otra persona espera todo lo que dure el INSERT. Ver FILAS_ANTES_DE_SOLTAR_EL_CANDADO.
    # Cada tanda en UNA transacción: la conexión está en autocommit, así que executemany
    # confirmaba fila por fila. Con 60 proveedores, 6.885 aplicaciones tardaban 172 s.
    for tanda in en_tandas_para_no_trabar(filas):
        with db_lock, transaccion():
            c.executemany("""INSERT OR IGNORE INTO aplicaciones
                             (marca_auto, modelo_auto, motor, combustible, anio_desde,
                              anio_hasta, codigo, codigo_clean, marca_repuesto, tipo_pieza,
                              origen)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'deducida')""",
                          [(f["Auto"], f["Modelo"], f.get("_motor") or "",
                            f.get("_combustible") or "",
                            f["_desde"], f["_hasta"],
                            f["Código"], f["_clean"], f["Marca"],
                            f.get("Pieza") or "") for f in tanda])
    return len(filas)

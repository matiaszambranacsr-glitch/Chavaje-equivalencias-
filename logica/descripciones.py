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
    "JUNTA", "JUNTAS", "JUEGO", "DESPIECE", "TAPA", "CILINDROS", "VALVULAS", "CARTER", "BOMBA",
    "ACEITE", "AGUA", "COMBUSTIBLE", "NAFTA", "TERMOSTATO", "RETEN", "ARO", "AROS", "PISTON",
    "CIL", "CILINDRO", "MOTOR", "SERIE", "PICK", "UP", "BUS", "CAMION", "TRACTOR", "DIESEL",
    "TURBO", "INY", "INYECCION", "CID", "DOHC", "SOHC", "MM", "CC", "STD", "COMPLETO", "SIN",
    "CON", "PARA", "DE", "DEL", "LA", "EL", "Y", "O", "REPARACION", "ADMISION", "ESCAPE",
    "CARBURADOR", "DESCARBONIZACION", "LATERAL", "SUPLEMENTO", "CAPERUZA", "BOLILLEROS",
    "DIRECCION", "MECANICA", "AGRICOLA", "CARGO", "GRAND", "SEMI", "ORING", "ARANDELA",
    "ALUMINIO", "CLAVITO", "BANCADA", "CAPUCHON", "BUJIA", "BRIDA", "CAÑO", "CALEFACCION",
    "ARBOL", "LEVAS", "SALIDA", "TAPON", "VALVULA", "MARIPOSA", "BASE", "DISTRIBUIDOR",
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
    "CUERPO", "VASO", "EXPANSION", "NIVEL", "STOP",
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
            cuenta_propia[token] += 1

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


_RE_ES_KIT = re.compile(r'\b(KIT|KITS|JUEGO|JUEGOS|JGO|JGOS|COMBO|SET)\b')

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
PALABRAS_DE_KIT = ("KIT", "JUEGO", "JGO", "COMBO", "SET")


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
    try:
        c.execute("SELECT DISTINCT modelo_auto FROM aplicaciones LIMIT 3000")
        for fila in c.fetchall():
            modelos.update(w for w in normalizar_texto(fila["modelo_auto"] or "").split()
                           if len(w) >= 3)
    except Exception as _err:
        anotar_error("_modelos_conocidos", _err)
        pass
    _MODELOS_CACHE["lista"] = modelos
    return modelos


class _ModelosLazy:
    """Para poder escribir `w in MODELOS_CONOCIDOS` sin recalcular la lista en cada palabra."""
    def __contains__(self, palabra):
        return palabra in _modelos_conocidos()


MODELOS_CONOCIDOS = _ModelosLazy()


def aplicaciones_desde_descripciones(limite=None):
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
    con un modelo inventado sirve para equivocarse."""
    ceder_al_mostrador()      # antes de la lectura grande. Ver ceder_al_mostrador().
    try:
        c.execute("""SELECT p.id, p.codigo_raw, p.codigo_clean, p.descripcion, m.nombre AS marca
                     FROM productos p JOIN marcas m ON m.id = p.marca_id
                     WHERE p.descripcion IS NOT NULL AND p.descripcion <> ''
                       AND p.codigo_clean NOT IN (SELECT codigo_clean FROM aplicaciones
                                                   WHERE codigo_clean IS NOT NULL)
                     ORDER BY p.id""")
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
                    modelos_por_marca[marca_auto] = {
                        t for t, _n in modelos_de_marca(marca_auto, _version_cat)}
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
    for tanda in en_tandas_para_no_trabar(filas):
        with db_lock:
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
            conn.commit()
    return len(filas)


# LO QUE SE SABE DE CADA PRODUCTO, recordado mientras dura UN análisis.
# analizar_lote_pendiente() llama a evidencia_cruzada() una vez por par, y ésta pregunta por
# cada uno de los dos productos sus autos en los catálogos, sus autos en las fichas del taller y
# sus cambios de código. Pero los pares se repiten productos: la lista del barrido tiene 8.648
# pares hechos con 4.399 productos. Se hacían 95.144 consultas, 51.888 de ellas repetidas.
# Vive solo mientras dura el análisis y se tira al terminar: guardarlo más tiempo obligaría a
# acordarse de invalidarlo cada vez que cambia una aplicación, una ficha o un reemplazo, que es
# justo el olvido que no se ve. Una por hilo, porque la tarea de fondo analiza por su cuenta.
_MEMORIA_DEL_ANALISIS = threading.local()


@contextlib.contextmanager
def recordando_lo_de_cada_producto():
    """Mientras dura el bloque, lo que se pregunta por producto se pregunta una vez sola."""
    if getattr(_MEMORIA_DEL_ANALISIS, "datos", None) is not None:
        yield            # ya hay una abierta más afuera: se usa esa
        return
    _MEMORIA_DEL_ANALISIS.datos = {}
    try:
        yield
    finally:
        _MEMORIA_DEL_ANALISIS.datos = None


def _recordado(clave, calcular):
    """calcular() la primera vez; después, lo mismo. Fuera de un análisis, calcula siempre."""
    datos = getattr(_MEMORIA_DEL_ANALISIS, "datos", None)
    if datos is None:
        return calcular()
    if clave not in datos:
        datos[clave] = calcular()
    return datos[clave]


def autos_de_todas_las_fuentes(producto_id, codigo_clean, autos_de_la_descripcion):
    """Todos los autos a los que le va un producto, juntando lo que sabe la app.

    La descripción del proveedor casi nunca alcanza: entra lo que entra en la celda y el resto
    se corta. Pero el mismo producto puede tener autos anotados en otros lados:

      1. El catálogo del fabricante, si cargaste el PDF de NGK, Bosch o similar.
      2. Las fichas de vehículo: si alguien le puso esta pieza a un Gol, le va a un Gol.
         Ese dato es de tu propio taller y no está en ninguna lista.
      3. La descripción, que es de donde salíamos hasta ahora.

    Juntar las tres hace que dos productos se puedan cruzar aunque sus descripciones no
    compartan ni un modelo."""
    return set(autos_de_la_descripcion or ()) | _recordado(
        ("autos", producto_id, codigo_clean),
        lambda: _autos_guardados_en_la_base(producto_id, codigo_clean))


def _autos_guardados_en_la_base(producto_id, codigo_clean):
    """Las fuentes 1 y 2 de autos_de_todas_las_fuentes(): lo que dice la base, sin la
    descripción. Aparte para poder recordarlo durante un análisis."""
    autos = set()

    if codigo_clean:
        try:
            c.execute("""SELECT DISTINCT marca_auto, modelo_auto FROM aplicaciones
                         WHERE codigo_clean = ? LIMIT 200""", (codigo_clean,))
            for fila in c.fetchall():
                for campo in (fila["marca_auto"], fila["modelo_auto"]):
                    autos.update(w for w in normalizar_texto(campo or "").split() if len(w) >= 3)
        except sqlite3.OperationalError as _err:
            anotar_error("autos_de_todas_las_fuentes", _err)
            pass

    if producto_id:
        try:
            # marca_auto / modelo_auto, que es como se llaman de verdad las columnas. Decía
            # v.marca y v.modelo, y esa consulta NUNCA anduvo: fallaba con «no such column»,
            # el except la tapaba y la fuente 2 —lo que este taller le puso a cada auto—
            # no aportaba nada desde siempre. Se vio contando los errores que la app se
            # traga: 254 en una sola corrida de la tarea de fondo, todos este.
            c.execute("""SELECT DISTINCT v.marca_auto, v.modelo_auto FROM historial_piezas hp
                         JOIN vehiculos v ON v.id = hp.vehiculo_id
                         WHERE hp.producto_id = ? LIMIT 100""", (producto_id,))
            for fila in c.fetchall():
                for campo in (fila["marca_auto"], fila["modelo_auto"]):
                    autos.update(w for w in normalizar_texto(campo or "").split() if len(w) >= 3)
        except sqlite3.OperationalError as _err:
            anotar_error("autos_de_todas_las_fuentes", _err)
            pass

    return frozenset(autos)


_RE_CANTIDAD_VIAS = re.compile(
    r'\b(\d{1,2})\s*(?:VIAS?|V[IÍ]AS?|PIN|PINES|BOCAS?|POLOS?|CONTACTOS?)\b', re.IGNORECASE)


def firma_de_producto(descripcion, producto_id=None, codigo_clean=None):
    """Ver _firma_de_producto(). Durante un análisis se calcula una vez por producto: la lista
    del barrido son 8.648 pares hechos con 4.399 productos, y se calculaba 17.296 veces —4,5 s
    de los 7,8 que tardaba el análisis—. Ver recordando_lo_de_cada_producto().

    La MISMA firma se devuelve a todos los que la piden, sin copiar: nadie la modifica después
    de armada —se revisó cada llamada—. Si alguna vez hace falta cambiarle algo, copiarla antes."""
    return _recordado(("firma", descripcion, producto_id, codigo_clean),
                      lambda: _firma_de_producto(descripcion, producto_id, codigo_clean))


def _firma_de_producto(descripcion, producto_id=None, codigo_clean=None):
    """Saca de una descripción qué pieza es y para qué auto, para poder comparar entre marcas.

    Esta es la única forma de vincular dos proveedores que no traen el código de fábrica —que
    son la mayoría—. Hasta ahora, sin esa columna no se generaba ninguna equivalencia.

    Lo que se extrae:
      núcleo    → las palabras que dicen QUÉ pieza es, sin el auto ni el relleno
      modelos   → los modelos de auto nombrados
      cilindrada, posición → los dos datos que más equivocan una venta

    El núcleo es lo que evita el error grave: «CAPUCHON BUJIA» y «ANILLO BUJIA» son del mismo
    rubro y del mismo auto, pero no son la misma pieza. Comparar solo por rubro las mezclaría.
    """
    if not descripcion or not str(descripcion).strip():
        return None
    texto = separar_texto_pegado(str(descripcion))
    limpio = normalizar_texto(texto)
    # EL PUNTO QUE PEGA DOS PALABRAS. Taranto abrevia sin dejar espacio:
    # «Jta.Tapa Cilind.Ford Focus / Fiesta». Como el punto se conserva adentro del token —hace
    # falta para 1.6, 278.897 y T-PRT04/B—, eso daba las palabras JTA.TAPA y CILIND.FORD.
    # Las consecuencias eran las dos peores posibles: la marca del auto quedaba escondida
    # adentro de una palabra, así que la firma de ese producto salía SIN NINGÚN AUTO, y la
    # cabeza era «JTA.TAPA», que no coincide con nada.
    # Se separa solo cuando el punto está entre dos LETRAS. Entre números no se toca, que es
    # donde importa: 1.6 sigue siendo la cilindrada y 278.897 sigue siendo un código.
    limpio = _RE_PUNTO_ENTRE_LETRAS.sub(r"\1 \2", limpio)
    limpio = _RE_COMA_DECIMAL.sub(".", limpio)   # ver _RE_COMA_DECIMAL
    palabras = [w for w in re.split(r"[^A-Z0-9./]+", limpio) if w]

    familia = clasificar_repuesto(texto)
    marca_auto = next((mv for mv in MARCAS_VEHICULO if f" {mv} " in f" {limpio} "), None)

    posicion = None
    for w in palabras:
        if w in _POSICIONES:
            posicion = _POSICIONES[w]
            break

    # La cilindrada con la unidad pegada. Taranto escribe «SIGMA 1.6CC 16V» y el \b del final
    # no engancha, porque entre el 6 y la C no hay borde de palabra: ese producto quedaba sin
    # cilindrada y no se podía contrastar contra el «- 1.6 -» de la otra lista.
    cilindradas = set(re.findall(r'\b(\d[.,]\d)(?!\d)', limpio))

    # Los modelos: palabras que quedan después de sacar la marca del auto, el ruido y los
    # números sueltos. Se buscan contra el catálogo propio para no inventar modelos.
    nucleo, modelos, modelos_numericos = [], set(), set()
    # TODAS las marcas de auto que nombre, no solo la primera. Antes se sacaba únicamente la
    # de marca_auto, y en «JTA TAPA CIL M.BENZ ... BENZ» el «BENZ» suelto quedaba adentro del
    # núcleo: la app contaba la marca del auto como si fuera una palabra de la PIEZA y
    # proponía equivalencias «porque coinciden en BENZ». Medido sobre las sugerencias reales,
    # FIAT aparecía en 46 y FORD en 36 de ellas como motivo de la coincidencia.
    palabras_marca = set()
    for mv_encontrada, _cat, _resto in marcas_vehiculo_en(texto):
        palabras_marca.update(mv_encontrada.split())
    for mv in MARCAS_VEHICULO:
        if f" {mv} " in f" {limpio} ":
            palabras_marca.update(mv.split())
    for indice, w in enumerate(palabras):
        # «4 y 6 CIL» es la CANTIDAD de cilindros del motor, no la pieza. Sin esto, «Juego de
        # juntas para Caja de Velocidad PEUGEOT 504 INDENOR DIESEL 4 y 6 CIL» entraba al
        # núcleo con la palabra CILINDRO y salía equivalente a una junta de tapa de cilindros.
        # Se reconoce por lo que tiene adelante: un número suelto.
        if (w in ("CIL", "CILS", "CILINDROS", "CILINDRO") and indice
                and re.fullmatch(r'\d{1,2}', palabras[indice - 1])):
            continue
        # Se sacan las marcas de REPUESTO: «coinciden en BOSCH» salía en 24 sugerencias y no
        # significa nada, dos proveedores distintos venden repuestos Bosch de cosas
        # completamente distintas.
        # Acá decía PALABRAS_NO_MODELO, que es un conjunto MUCHO más grande y para otra cosa:
        # son los nombres de pieza que no hay que confundir con modelos de auto en el
        # desplegable de vehículos — JUNTA, TAPA, CILINDROS, BOMBA, VALVULA, ARO...
        # O sea que el núcleo, que existe para guardar QUÉ PIEZA ES, tiraba exactamente las
        # palabras que dicen qué pieza es y se quedaba con los MODELOS DE AUTO. En
        # «Junta Tapa de Cilindros FORD FOCUS FIESTA FUSION CMAX» el núcleo quedaba
        # ['FOCUS','FIESTA','FUSION','CMAX'] y la cabeza —el sustantivo principal, lo que
        # separa un CAPUCHON de un ANILLO— era 'FOCUS'.
        # Las dos caras del mismo error: comparaba una junta contra otra junta del mismo auto
        # y decía «piezas distintas: FOCUS y JTA.TAPA», y al revés daba por parecidas dos
        # piezas sin relación con solo compartir dos modelos de auto.
        # EL MODELO QUE ES UN NÚMERO. En los autos viejos y en los camiones el modelo ES un
        # número —FIAT 128, FIAT 600, PEUGEOT 404, VOLKSWAGEN 1300, MERCEDES 1620— y el núcleo
        # los tiraba a todos junto con los años y las medidas, por ser puro número. La
        # consecuencia se veía en las sugerencias: «Jgo.Jtas.Carburador FIAT 125» salía
        # emparejado con «Juego de juntas para Carburador FIAT 1600», porque lo único que
        # quedaba de las dos descripciones era la palabra FIAT.
        # Se pide que venga JUSTO DESPUÉS de la marca del auto, que es como se escriben, y que
        # no sea un año. Los de FISPA, que escriben la cilindrada separada («FIAT PALIO 1 3»),
        # no entran: son de un dígito y acá se piden dos.
        es_modelo_numerico = (re.fullmatch(r'\d{2,4}', w) and indice
                              and palabras[indice - 1] in palabras_marca
                              and not re.fullmatch(r'(19|20)\d{2}', w))
        if (w in _RUIDO_EN_FIRMA or w in palabras_marca or w in _POSICIONES
                or w in MARCAS_DE_REPUESTO
                or (not es_modelo_numerico
                    and (len(w) < 3 or re.fullmatch(r'[\d./,]+', w)))):
            continue
        if es_modelo_numerico:
            modelos_numericos.add(w)
        # La misma pieza abreviada distinta por cada proveedor. Taranto pone «Jta.Tapa
        # Cilind.» e Illinois «Junta Tapa de Cilindros»: sin expandir, la cabeza de una es
        # JTA y la de la otra JUNTA, y la comparación cortaba con «piezas distintas» entre
        # dos juntas de tapa de cilindros del mismo motor.
        # La tabla ya existía y la usaba _nombre_de_la_pieza(); acá no se estaba usando.
        # El punto final se saca antes de buscar: «CIL.» tiene que encontrar a «CIL».
        nucleo.append(ABREVIATURAS_DE_PIEZA.get(w.rstrip("."), w.rstrip(".")) or w)

    # Los autos nombrados: marcas y modelos. Es el dato que más discrimina, y probado con
    # listas reales es el único que no falla. Dos proveedores pueden llamar distinto a la misma
    # pieza («SENSOR DE MASA DE AIRE» y «SENSOR MAF»), pero si uno dice Ford Focus y el otro
    # Volvo 850, no es la misma pieza por más que el resto coincida.
    # La marca en su FORMA CANÓNICA, que es lo que hace marcas_vehiculo_en(): resuelve los
    # alias y gana siempre la marca más larga. Antes se buscaba cada marca como subcadena y eso
    # dejaba dos agujeros, los dos caros:
    #   · CHEV y CHEVROLET quedaban como dos marcas distintas —igual PEUG/PEUGEOT, CITR/CITROEN,
    #     VW/VOLKSWAGEN, MERCEDES-BENZ/MERCEDES— así que dos proveedores que abrevian distinto
    #     salían «autos distintos» y el par se rechazaba de entrada. Son 3.705 descripciones;
    #   · y el camión BED FORD se leía como FORD, con lo cual una junta de diferencial de un
    #     Bedford podía emparejarse con cualquier repuesto de un Fiesta.
    autos, marcas = set(), set()
    for _mv_hallada, _cat_mv, _resto_mv in marcas_vehiculo_en(texto):
        autos.update(w for w in _mv_hallada.split() if len(w) >= 3)
        marcas.add(_mv_hallada)
    # Las marcas y los MODELOS se guardan también aparte. Ver «la marca sola no alcanza» en
    # firmas_compatibles(): compartir CHEVROLET no dice nada si una es de S10 y la otra de
    # Corsa, y compartir TRAIL tampoco si una es la Trail Blazer de Chevrolet y la otra la
    # X-Trail de Nissan. La lista de modelos conocidos trae también las marcas y sus
    # abreviaturas (CHEVROLET, FIAT, CHEV, PEU, REN), y por eso se descuentan.
    modelos = set()
    for w in palabras:
        if len(w) >= 3 and w in MODELOS_CONOCIDOS:
            autos.add(w)
            if w not in _PALABRAS_DE_MARCA_DE_VEHICULO:
                modelos.add(w)

    # El sustantivo principal: en estas descripciones la pieza va primero
    # («CAPUCHON bujía...», «ANILLO bujía...»). Es lo que separa dos piezas del mismo rubro.
    cabeza = nucleo[0] if nucleo else None
    siglas = {w for w in palabras if w in _SIGLAS_DE_PIEZA}

    # EL NÚCLEO SE PARTE EN DOS, porque son dos preguntas distintas y hay que contestar las
    # dos: QUÉ PIEZA ES y PARA QUÉ AUTO ES. Mezcladas en una sola bolsa de palabras, «comparten
    # dos palabras» se cumple igual con dos modelos de auto (y entonces una junta de escape
    # sale «equivalente» a una de tapa de válvulas porque las dos dicen R11 y R19) que con dos
    # nombres de pieza (y entonces cualquier junta de tapa de cilindros sale equivalente a
    # cualquier otra, de cualquier motor).
    # PALABRAS_NO_MODELO es justamente el vocabulario de PIEZA: está curada a mano para el
    # desplegable de vehículos, donde hace falta saber qué palabra NO es un modelo.
    # PALABRAS_DE_CONTEXTO se sacan de la pieza y se dejan del lado de la aplicación: CARGO,
    # PICK UP, TRACTOR o DIESEL dicen qué vehículo es, no qué pieza es.
    pieza = {w for w in nucleo if w in PALABRAS_NO_MODELO and w not in PALABRAS_DE_CONTEXTO}
    aplicacion = [w for w in nucleo if w not in pieza]

    # Se completa con lo que la app sepa de este producto por otras vías
    if producto_id or codigo_clean:
        autos = autos_de_todas_las_fuentes(producto_id, codigo_clean, autos)

    # Cantidad de vías / pines / bocas. En fichas, conectores y carburadores ese número no es
    # un detalle: ES la pieza. Una ficha de 2 vías no entra donde va una de 3, por más que las
    # dos digan "FICHA DE INYECCION" y vayan al mismo auto. Se cuentan 723 descripciones que lo
    # declaran en un catálogo real, así que no es un caso raro.
    m_vias = _RE_CANTIDAD_VIAS.search(descripcion or "")
    vias = int(m_vias.group(1)) if m_vias else None

    return {"familia": familia, "nucleo": nucleo, "cabeza": cabeza, "autos": autos,
            "pieza": pieza, "aplicacion": set(aplicacion),
            "modelos_numericos": modelos_numericos, "modelos": modelos, "marcas": marcas,
            "siglas": siglas, "marca_auto": marca_auto, "posicion": posicion,
            "cilindradas": cilindradas, "vias": vias, "texto": limpio}


# Una palabra que aparece en más de este porcentaje del catálogo no distingue nada: está en
# miles de repuestos que no tienen relación. Medido sobre las 61.574 descripciones reales:
# SENSOR está en el 13,8%, BOMBA en el 5,8%, JUNTA en el 3,5%, BUJIA en el 2,1%. Con el 1% de
# corte, para vincular hace falta compartir además algo específico — un modelo, una medida,
# una sigla— y no solo «los dos dicen BOMBA».
PORCENTAJE_PALABRA_GENERICA = 1.0


def cuantas_veces_aparece_cada_palabra():
    """(conteo por palabra, total de descripciones). Lo que necesita firmas_compatibles() para
    saber qué palabra distingue y cuál está en todos lados. Va cacheado por versión."""
    version = version_del_catalogo()
    # Cada cosa por separado y en este orden, a propósito. Escrito como
    # `return descripciones_por_palabra(version), c.fetchone()[0]` no anda: Python evalúa
    # primero la función, que hace sus propias consultas sobre el MISMO cursor, y para cuando
    # llega el fetchone() ya está leyendo otro resultado. Devolvía None y rompía todas las
    # sugerencias por descripción.
    cuenta = descripciones_por_palabra(version)
    c.execute("SELECT COUNT(*) FROM productos WHERE descripcion IS NOT NULL")
    fila = c.fetchone()
    # El conteo se hace sobre las palabras CRUDAS y la firma compara palabras EXPANDIDAS: si
    # no se suman las formas, la palabra expandida parece rarísima y pasa por «específica».
    # Es exactamente lo que pasaba con CILINDRO: el catálogo dice CILINDROS 2.596 veces, CIL
    # otras tantas y CILINDRO apenas 476, así que la forma expandida daba 0,66% —debajo del
    # 1%— y «coinciden en CILINDRO» contaba como una coincidencia que distingue, cuando
    # CILINDRO está en el 4,3% de las descripciones. Sumadas las formas, vuelve a ser lo que
    # es: una palabra genérica.
    total = ((fila[0] if fila else 0) or 0)
    completo = dict(cuenta)
    for abreviatura, expandida in ABREVIATURAS_DE_PIEZA.items():
        if cuenta.get(abreviatura):
            completo[expandida] = completo.get(expandida, 0) + cuenta[abreviatura]
    return completo, total


def palabras_que_dicen_algo(comunes, cuenta_palabras, total_descripciones):
    """De las palabras compartidas, las que de verdad distinguen a esta pieza de las demás."""
    if not cuenta_palabras or not total_descripciones:
        return set(comunes)
    tope = max(1, int(total_descripciones * PORCENTAJE_PALABRA_GENERICA / 100))
    return {w for w in comunes if cuenta_palabras.get(w, 0) <= tope}


# Cada palabra con que se escribe una marca de vehículo, abreviaturas incluidas. Ninguna es un
# modelo: «modelos distintos: VECTRA vs CHEV» comparaba un modelo contra la marca abreviada.
# Van también las de marcas de dos palabras —NEW de NEW HOLLAND—, y está bien que vayan: «NEW
# Beetle» contra «New Fiesta» no son el mismo modelo por decir los dos NEW.
_PALABRAS_DE_MARCA_DE_VEHICULO = {p for m in MARCAS_VEHICULO for p in re.split(r'[\s.\-]+', m)
                                  if len(p) >= 2} | set(ALIAS_MARCA_VEHICULO.values())

# Marcas que comparten motores y plataformas: una pieza de una puede ser la misma de la otra, y
# que una lista diga GM y la otra CHEVROLET, o una PEUGEOT y la otra CITROEN, no es una
# contradicción. Son las familias históricas, las que se ven en el parque argentino; no el
# grupo de hoy (con Stellantis entero, «marcas distintas» no cortaría casi nunca).
_FAMILIAS_DE_MARCAS = [
    {"CHEVROLET", "GM", "OPEL", "VAUXHALL", "DAEWOO", "GMC", "BUICK", "PONTIAC", "CADILLAC",
     "OLDSMOBILE", "SATURN"},
    {"PEUGEOT", "CITROEN"},
    {"FIAT", "ALFA ROMEO", "LANCIA", "CHRYSLER", "JEEP", "DODGE", "RAM", "IVECO"},
    {"VOLKSWAGEN", "AUDI", "SEAT", "SKODA", "PORSCHE"},
    {"RENAULT", "NISSAN", "DACIA", "INFINITI", "MITSUBISHI"},
    {"FORD", "MAZDA", "VOLVO", "LINCOLN", "MERCURY"},
    {"TOYOTA", "LEXUS", "DAIHATSU"},
    {"HYUNDAI", "KIA", "GENESIS"},
    {"HONDA", "ACURA"},
    {"LAND ROVER", "ROVER", "JAGUAR"},
    {"MERCEDES BENZ", "SMART"},
    {"BMW", "MINI"},
]
# Las que hacen MOTORES para las demás: una junta de MWM va en la S10 y en la Ranger, un sensor
# Cummins va en un Iveco. Que una descripción nombre al motor y la otra al vehículo no dice que
# sean autos distintos.
_MARCAS_DE_MOTORES = {"MWM", "CUMMINS", "PERKINS", "DEUTZ", "CATERPILLAR", "YANMAR", "KUBOTA"}


def _marcas_que_se_cruzan(marcas_a, marcas_b):
    """¿Nombran alguna marca en común, o de la misma familia, o una es de motores?"""
    if (marcas_a & marcas_b) or (marcas_a | marcas_b) & _MARCAS_DE_MOTORES:
        return True
    return any(fam & marcas_a and fam & marcas_b for fam in _FAMILIAS_DE_MARCAS)


def firmas_compatibles(a, b, minimo_nucleo=2, cuenta_palabras=None, total_descripciones=0):
    """¿Estas dos descripciones hablan de la misma pieza? Devuelve (sí/no, motivo).

    Se exige coincidencia en lo que define la pieza y NO contradicción en lo que la distingue.
    Es a propósito conservador: un falso positivo acá es una equivalencia inventada, y ya
    sabemos lo que eso le hizo a la base."""
    if not a or not b:
        return False, ""
    if a["familia"] == "Sin clasificar" or b["familia"] == "Sin clasificar":
        return False, "no se pudo clasificar el rubro"
    if a["familia"] != b["familia"]:
        return False, "rubros distintos"

    # Posición: si las dos la declaran y no coinciden, son piezas distintas. Un amortiguador
    # delantero no reemplaza a uno trasero por más que vayan al mismo auto.
    if a["posicion"] and b["posicion"] and a["posicion"] != b["posicion"]:
        return False, f"posiciones distintas ({a['posicion']} vs {b['posicion']})"

    # Cilindrada: si las dos la declaran y no comparten ninguna, no es la misma aplicación
    if a["cilindradas"] and b["cilindradas"] and not (a["cilindradas"] & b["cilindradas"]):
        return False, "cilindradas distintas"

    # El modelo que es un número, con el mismo criterio que la cilindrada y las siglas: si las
    # dos descripciones lo declaran y no comparten ninguno, son de autos distintos. Hasta que
    # esos números entraron a la firma, de «Jgo.Jtas.Carburador FIAT 125» contra «Juego de
    # juntas para Carburador FIAT 1600 128» lo único que quedaba era la palabra FIAT, y el par
    # pasaba. Ver es_modelo_numerico en firma_de_producto().
    # Con una salvedad que hace falta: el número se reconoce solo cuando viene JUSTO detrás de
    # la marca, y las listas encadenan modelos («FIAT 128 EUROPA 147 DUNA»), así que del segundo
    # en adelante no quedan anotados. Antes de cortar se mira si el número del otro aparece en
    # algún lado de la descripción: sin eso, «FIAT 147 DUNA» contra «FIAT 128 EUROPA 147 DUNA»
    # —que son la misma junta— salía como «modelos distintos: 147 vs 128».
    _num_a, _num_b = a.get("modelos_numericos") or set(), b.get("modelos_numericos") or set()
    if _num_a and _num_b and not (_num_a & _num_b):
        _texto_a, _texto_b = a.get("texto") or "", b.get("texto") or ""
        _lo_nombra = (any(re.search(rf'\b{n}\b', _texto_b) for n in _num_a)
                      or any(re.search(rf'\b{n}\b', _texto_a) for n in _num_b))
        if not _lo_nombra:
            return False, (f"modelos distintos: {'/'.join(sorted(_num_a)[:2])} "
                           f"vs {'/'.join(sorted(_num_b)[:2])}")

    # LOS AUTOS. Probado sobre dos listas reales de 5.000 y 26.000 productos, es el control
    # que evita la avalancha de falsos: sin él, toda «BUJIA NAFTA» se vinculaba con toda otra
    # «BUJIA NAFTA» porque comparten dos palabras genéricas, aunque una fuera de un Renault y
    # la otra de un BMW.
    if a["autos"] and b["autos"]:
        autos_comunes = a["autos"] & b["autos"]
        if not autos_comunes:
            return False, (f"autos distintos: {'/'.join(sorted(a['autos'])[:2])} "
                           f"vs {'/'.join(sorted(b['autos'])[:2])}")
    else:
        autos_comunes = set()

    # Cantidad de vías / pines: si las dos la declaran y no es la misma, son piezas distintas.
    # Sin esto se proponía una «FICHA 3 Vias Macho» contra una «FICHA 2 vias macho»: mismo
    # rubro, misma primera palabra, mismo tipo de conector, y no entra una donde va la otra.
    if a.get("vias") and b.get("vias") and a["vias"] != b["vias"]:
        return False, f"distinta cantidad de vías ({a['vias']} vs {b['vias']})"

    # Siglas técnicas: si las dos declaran una y no coinciden, son piezas distintas. Probado
    # con listas reales: sin esto se cruzaba «VALVULA PCV» con «VALVULA EGR» del mismo auto,
    # porque comparten la palabra VALVULA y el modelo.
    if a["siglas"] and b["siglas"] and not (a["siglas"] & b["siglas"]):
        return False, (f"siglas distintas: {'/'.join(sorted(a['siglas']))} "
                       f"vs {'/'.join(sorted(b['siglas']))}")

    # El sustantivo principal: «CAPUCHON bujía» y «ANILLO bujía» son del mismo rubro, del mismo
    # auto, y son piezas distintas. Lo único que las separa es la primera palabra.
    if a["cabeza"] and b["cabeza"] and a["cabeza"] != b["cabeza"]:
        # Salvo que una sea abreviatura o parte de la otra: SENSOR MAF / SENSOR DE MASA
        if not (a["cabeza"] in b["cabeza"] or b["cabeza"] in a["cabeza"]):
            return False, f"piezas distintas: «{a['cabeza']}» y «{b['cabeza']}»"

    comunes = set(a["nucleo"]) & set(b["nucleo"])
    if len(comunes) < minimo_nucleo:
        return False, f"solo comparten {len(comunes)} palabra(s)"

    # Lo que comparten del lado del AUTO, sin la cilindrada ni las válvulas: ver más abajo, en
    # el control de «para qué auto es». Se calcula acá porque el control de la pieza lo
    # necesita para el caso de una sola palabra.
    apl_comunes = {w for w in (a.get("aplicacion") or set()) & (b.get("aplicacion") or set())
                   if not _RE_SOLO_MOTORIZACION.match(w) and not _RE_MEDIDA_SUELTA.match(w)}

    # LA MARCA SOLA NO ALCANZA cuando las dos nombran modelos y no comparten ninguno. Se vio en
    # las sugerencias: «Jta.Tapa Cil. Chevrolet S10-Trail Blazer ESP 1.10MM» salía con 90
    # puntos contra «Junta Tapa de Cilindros CHEVROLET (ESP 1.10mm) COMBO CORSA ASTRA TIGRA».
    # Los autos «coincidían» porque las dos dicen CHEVROLET, y lo demás que compartían era el
    # espesor y la palabra ESP: la misma junta, de otro motor.
    # No corta si comparten algo de la aplicación que no sea una medida —un código de motor
    # como Z13DT o 4FB1 vale: el mismo motor va en autos distintos— ni si el modelo de una
    # está escrito en cualquier lado de la otra, por lo mismo que con los modelos numéricos:
    # la lista de modelos conocidos no los tiene a todos, y un CORSA puede no estar anotado.
    _mod_a, _mod_b = a.get("modelos") or set(), b.get("modelos") or set()
    # Y al revés: comparten una palabra de modelo pero las marcas no coinciden. «S10-Trail
    # Blazer» de Chevrolet contra «X-TRAIL» de Nissan compartían TRAIL, y con eso los autos
    # «coincidían». El modelo compartido no cuenta como respaldo acá, justamente porque es la
    # palabra que se está poniendo en duda; un código de motor en común sí.
    _mar_a, _mar_b = a.get("marcas") or set(), b.get("marcas") or set()
    if (_mar_a and _mar_b and not _marcas_que_se_cruzan(_mar_a, _mar_b)
            and not (apl_comunes - _mod_a - _mod_b)):
        return False, (f"marcas distintas: {'/'.join(sorted(_mar_a)[:2])} "
                       f"vs {'/'.join(sorted(_mar_b)[:2])}")
    # Solo cuando las dos son ESPECÍFICAS: tres modelos o menos de cada lado. Una lista larga
    # —«SENSOR DE DETONACION FIAT 500 BRAVO IDEA PUNTO...» contra «Fiat BRAVA DOBLO»— es de
    # una pieza que va en muchos autos, y cada proveedor anota los que quiere: que no se pisen
    # no dice que sean piezas distintas. Una junta de tapa de cilindros de S10 y Trail Blazer
    # contra una de Corsa, Astra y Tigra, sí.
    if (_mod_a and _mod_b and not (_mod_a & _mod_b) and not apl_comunes
            and len(_mod_a) <= 3 and len(_mod_b) <= 3):
        _texto_a, _texto_b = a.get("texto") or "", b.get("texto") or ""
        _lo_nombra = (any(re.search(rf'\b{re.escape(m)}\b', _texto_b) for m in _mod_a)
                      or any(re.search(rf'\b{re.escape(m)}\b', _texto_a) for m in _mod_b))
        if not _lo_nombra:
            return False, (f"modelos distintos: {'/'.join(sorted(_mod_a)[:2])} "
                           f"vs {'/'.join(sorted(_mod_b)[:2])}")

    # LAS DOS PREGUNTAS, POR SEPARADO. Antes era una sola bolsa de palabras y «comparten dos»
    # alcanzaba, sin mirar CUÁLES. Las dos formas de equivocarse salían de ahí, y las dos se
    # veían en la base real:
    #   · dos modelos de auto compartidos daban por equivalentes piezas distintas
    #     («Junta Salida de Escape R9 R11 R19» con «Junta Tapa de Válvulas R9 R11 R19»)
    #   · dos nombres de pieza compartidos daban por equivalentes aplicaciones distintas
    #     (cualquier junta de tapa de cilindros con cualquier otra, de cualquier motor)
    # Ahora tienen que coincidir las dos cosas: qué pieza es Y para qué auto es.
    pieza_a, pieza_b = a.get("pieza") or set(), b.get("pieza") or set()
    piezas_comunes = pieza_a & pieza_b
    if pieza_a and pieza_b:
        # Dos condiciones, y las dos salieron de mirar lo que proponía sobre las listas reales:
        #
        # 1) Al menos DOS palabras de pieza. Con una sola alcanzaba «JUNTA», que está en el
        #    7,5% del catálogo, y de ahí salía «Juego de juntas para Caja de Velocidad FORD
        #    F100» contra «Jta.Tapa Valvulas FORD F100»: comparten la palabra JUNTA y la
        #    camioneta, y son dos piezas que no tienen nada que ver.
        #
        # 2) La descripción más pobre tiene que estar ENTERA adentro de la otra. Es lo que
        #    separa «Junta Tapa de VÁLVULAS» de «Junta Tapa de CILINDROS»: las dos comparten
        #    JUNTA y TAPA, las dos van al mismo auto, y la palabra en la que se diferencian
        #    es justamente la que dice cuál de las dos es. Es el mismo criterio que ya se usa
        #    con las siglas y con la posición: si las dos lo declaran y no coinciden, son
        #    piezas distintas.
        chica = pieza_a if len(pieza_a) <= len(pieza_b) else pieza_b
        # Las DOS palabras se piden cuando hay dos para pedir. Si el que menos dice nombra la
        # pieza con UNA sola palabra —«BOBINA» contra «BOBINA DE IGNICION», «SENSOR» contra
        # «SENSOR MAP»— alcanza con que esa esté del otro lado: pedirle dos es pedirle algo que
        # no escribió. El caso que la regla de dos cuida es otro, y sigue cuidado: «Juego de
        # juntas para Caja de Velocidad FORD F100» contra «Jta.Tapa Valvulas FORD F100»
        # comparten JUNTA y nada más, pero el que menos dice nombra tres palabras, así que la
        # contención falla igual.
        # Y con una sola palabra hay que pedir algo más del otro lado: que compartan el
        # MODELO y no solo la marca. Si no, «Jgo.Jtas.P/Motor BED FORD 3800» y «Juntas para
        # diferencial BED FORD EATON» pasan compartiendo nada más que la palabra JUNTA y la
        # marca del camión, que son dos piezas que no tienen nada que ver.
        if (piezas_comunes < chica
                or (len(chica) >= 2 and len(piezas_comunes) < 2)
                or (len(chica) == 1 and not apl_comunes)):
            return False, (f"no coinciden en qué pieza es: «{'/'.join(sorted(pieza_a)[:3])}» "
                           f"y «{'/'.join(sorted(pieza_b)[:3])}»")

    # Y para qué auto. Vale la marca (FORD) o el modelo/motor nombrado (FOCUS, SIGMA, F4L).
    # La cilindrada y las válvulas NO valen: dicen cómo es el motor, no cuál es el auto, y
    # cuando una de las dos descripciones no nombra ninguna marca de vehículo conocida son lo
    # único que queda para contestar esta pregunta. Así salía «BOBINA ESCORT/ORION 1.8i 16V
    # ZETEC» contra una bobina de «PEUGEOT 406 1.8i, 16V, 306 1.8 16V»: un Ford y un Peugeot
    # unidos por «1.8I, 16V». Ver _RE_SOLO_MOTORIZACION.
    # Se descuentan acá y no en la firma a propósito: para ORDENAR candidatos la cilindrada sí
    # sirve —confirma la aplicación— y sacarlas de fuerza_de_la_coincidencia() cambiaba el
    # orden de los tres que se guardan por producto, y con eso se perdían pares buenos
    # («Jta.Tapa Cil. RENAULT CLIO II», «JUNTA TAPA CILINDROS FORD M. ZETEC») a cambio de otros.
    if not autos_comunes and not apl_comunes:
        return False, "no coinciden en para qué auto es"

    # Que al menos UNA de las palabras compartidas diga algo. Coincidir en «AGUA, ORING, TUBO»
    # o en «ACEITE, BBA, JTA» son palabras que están en miles de repuestos: eso no es
    # parecerse, es hablar el mismo idioma.
    # Se perdona cuando las dos preguntas se contestaron bien igual —misma pieza Y mismo
    # auto—, porque ahí la evidencia está en la coincidencia completa y no en una palabra
    # rara. «JUNTA TAPA CILINDRO» + «FORD FOCUS FIESTA» no tiene una sola palabra rara y sin
    # embargo es exactamente el mismo repuesto.
    utiles = palabras_que_dicen_algo(comunes, cuenta_palabras, total_descripciones)
    respaldo_completo = len(piezas_comunes) >= 2 and (autos_comunes and apl_comunes)
    if cuenta_palabras and not utiles and not respaldo_completo:
        return False, ("solo comparten palabras genéricas ("
                       + ", ".join(sorted(comunes)[:3]) + ")")

    # Se muestran primero las que distinguen: es lo que hay que mirar para decidir.
    orden = sorted(comunes, key=lambda w: (w not in utiles, w))
    detalle = f"coinciden en {', '.join(orden[:4])}"
    if autos_comunes:
        detalle += f" · autos: {'/'.join(sorted(autos_comunes)[:3])}"
    if a["posicion"] or b["posicion"]:
        detalle += f" · {a['posicion'] or b['posicion']}"
    if a["cilindradas"] & b["cilindradas"]:
        detalle += f" · {'/'.join(sorted(a['cilindradas'] & b['cilindradas']))}"
    return True, detalle


def fuerza_de_la_coincidencia(a, b):
    """Cuánto se parecen dos firmas, para poder ordenar los candidatos de mejor a peor.

    Hace falta porque de cada producto se guardan solo los mejores candidatos, y hasta ahora
    «mejor» era cuántas MARCAS de auto compartían. Casi todos los productos de una lista
    comparten la misma marca, así que el orden quedaba empatado en 1 y lo desempataba el orden
    del catálogo, o sea el azar.

    Se vio con la junta de tapa de cilindros de la Illinois TC-936-MG: entre los candidatos
    estaba la 321607 de Taranto —misma pieza, mismo motor Ford 1.6 Sigma, cuatro palabras
    compartidas— y no entraba en los cinco que se guardaban, porque empataba en «comparte
    FORD» con cualquier otra junta de cualquier Ford.

    Lo que más discrimina va primero: el MODELO o el motor nombrado (FOCUS, SIGMA, F4L) es
    mucho más específico que la marca, y la cilindrada confirma la aplicación."""
    if not a or not b:
        return (0, 0, 0, 0)
    apl = len((a.get("aplicacion") or set()) & (b.get("aplicacion") or set()))
    pieza = len((a.get("pieza") or set()) & (b.get("pieza") or set()))
    cil = len((a.get("cilindradas") or set()) & (b.get("cilindradas") or set()))
    autos = len((a.get("autos") or set()) & (b.get("autos") or set()))
    return (apl, cil, pieza, autos)


def _uno_trae_al_otro(desc_a, cod_a, desc_b, cod_b, tipo_a="", tipo_b=""):
    """¿Uno de los dos es un kit que nombra al otro adentro? Devuelve el texto de la relación.

    Es la misma pregunta que contesta kits_que_traen_a_varios() para el mostrador, pero acá hace
    falta para lo contrario: para NO tratar la relación como una equivalencia. Que la bujía
    esté adentro del «KIT CAB Y BUJ» es cierto y útil, y al mismo tiempo quiere decir que no
    son intercambiables: no se puede vender una en lugar de la otra.

    Se contesta con los dos textos y nada más — sin tocar la base. Hacerlo con
    una consulta, que es lo natural, cuesta un LIKE sobre las 70.888 descripciones por
    cada par: la revisión de una tanda de 1.000 vínculos pasaba de 1,4 a 15,9 segundos.

    El código se busca también SIN la marca pegada atrás, por lo mismo que en
    _formas_del_codigo_para_buscar_en_kits(): el proveedor se llama «LSPFR6F11LUCAS» a sí mismo
    y en el kit escribe
    «LSPFR6F11».

    LA PIEZA NO PUEDE SER UN CÓDIGO DE FÁBRICA, y sin esa condición esto se equivocaba en
    grande: la descripción de un juego de juntas TERMINA con su propio número original
    —«Juego de juntas para Carburador PEUGEOT 405 SOLEX 1433630»— y de ahí sale el producto OEM
    1433630, con la MISMA descripción. Encontrar ese número adentro del texto del kit no quiere
    decir que el kit traiga otra pieza: es el kit citándose a sí mismo. Sobre la base real eran
    786 de los 3.185 pendientes y 1.054 de los 24.774 vínculos cargados marcados como «no son
    equivalentes» cuando son justo el puente que hay que tener —598 de esos 786 con las dos
    descripciones IDÉNTICAS—.

    Un kit y su pieza suelta son dos productos que un PROVEEDOR vende por separado; un código
    de fábrica no es ni un kit ni una pieza suelta, es el número con el que la fábrica llama a
    una de las dos. Por eso alcanza con que UNO de los dos lados sea OEM para que no haya nada
    que mirar: del otro lado siempre está el producto del que salió ese número, con su misma
    descripción."""
    if "OEM" in {(tipo_a or "").upper(), (tipo_b or "").upper()}:
        return ""
    for kit_desc, pieza_cod in ((desc_a, cod_b), (desc_b, cod_a)):
        if not kit_desc or not pieza_cod or not es_un_kit(kit_desc):
            continue
        texto = normalizar_texto(kit_desc)
        limpio = sanitizar(pieza_cod)
        if len(limpio) < LARGO_MINIMO_CODIGO_EN_KIT:
            continue
        formas = [limpio]
        for marca in _MARCAS_QUE_SE_PEGAN_AL_CODIGO:
            if limpio.endswith(marca) and len(limpio) - len(marca) >= LARGO_MINIMO_CODIGO_EN_KIT:
                formas.append(limpio[:-len(marca)])
                break
        if any(f in texto for f in formas):
            return f"«{str(kit_desc)[:40]}» lo trae adentro"
    return ""


def pares_de_kit_y_pieza(pares):
    """De una lista de pares (a, b), cuáles son «un kit y la pieza que trae adentro».

    Existe para NO mandarlos a la cola de revisión. La relación es cierta y sirve —el buscador
    ofrece el kit cuando buscás la pieza suelta, y eso lo resuelve kits_que_traen_a_varios() leyendo
    las descripciones en el momento— pero no es una equivalencia: no se puede vender una en
    lugar de la otra. Preguntarle a alguien «¿son equivalentes?» cuando ya sabemos que no, es
    hacerle perder el tiempo y además tentarlo a decir que sí.

    Una sola consulta por tanda para todos los productos involucrados: lo caro sería preguntar
    por par."""
    pares = [(a, b) for a, b in pares]
    ids = sorted({i for par in pares for i in par})
    if not ids:
        return set()
    datos = {}
    try:
        for tanda, marcadores in en_tandas(ids):
            c.execute(f"""SELECT p.id, p.codigo_raw, p.descripcion, m.tipo
                          FROM productos p JOIN marcas m ON m.id = p.marca_id
                          WHERE p.id IN ({marcadores})""", tanda)
            for r in c.fetchall():
                datos[r["id"]] = (r["descripcion"], r["codigo_raw"], r["tipo"])
    except sqlite3.OperationalError as _err:
        anotar_error("pares_de_kit_y_pieza", _err)
        return set()
    salida = set()
    for a, b in pares:
        da, ca, ta = datos.get(a, ("", "", ""))
        db, cb, tb = datos.get(b, ("", "", ""))
        if _uno_trae_al_otro(da, ca, db, cb, ta, tb):
            salida.add((a, b))
    return salida


# Los motivos de firmas_compatibles() que CONTRADICEN, y no solo dejan de confirmar. «Solo
# comparten una palabra» quiere decir que el texto no alcanza para opinar; «modelos distintos:
# S10 vs CORSA» quiere decir que el texto dice que es otro auto. Los primeros no suman; estos
# tumban el par, igual que las medidas que se contradicen.
# Antes eran solo la posición y las siglas, y el resto quedaba callado: la junta de la S10 con
# la de la X-Trail de Nissan no tenía ninguna evidencia a favor, pero con «mismo rubro» y
# «precio parecido» llegaba a 75 y se aprobaba sola.
# «Piezas distintas» no está, a propósito: sale de comparar la primera palabra, y BULBO y
# SENSOR, o CARCASA y BASE de termostato, son la misma pieza dicha de otra forma.
_MOTIVOS_QUE_CONTRADICEN = ("posiciones distintas", "siglas distintas", "autos distintos",
                            "marcas distintas", "modelos distintos", "cilindradas distintas",
                            "distinta cantidad de vías")
# Los que hablan del AUTO. Esos no cuentan cuando el par está unido por un código: ver
# _unidos_por_codigo().
_MOTIVOS_DEL_AUTO = ("autos distintos", "marcas distintas", "modelos distintos",
                     "cilindradas distintas")


def _unidos_por_codigo(pa, pb):
    """¿El par está unido por un número, y no por el parecido de las descripciones?

    Un lado es un código de fábrica, o el código de uno está escrito en la descripción del
    otro («... REF ORIG 0281006325» contra el 0281 006 325 de otra lista). Ahí la pieza la dice
    el número, y que cada lista nombre autos distintos es lo normal: un sensor Bosch va en
    diez marcas y cada proveedor anota las que le parecen. Medido sobre la cola real: sin esta
    excepción, 64 pares de «código escrito en la descripción» caían por «autos distintos» o
    «modelos distintos», y los que se miraron eran el mismo número de Bosch."""
    if "OEM" in {(pa.get("tipo") or "").upper(), (pb.get("tipo") or "").upper()}:
        return True
    for yo, otro in ((pa, pb), (pb, pa)):
        codigo = sanitizar(yo.get("codigo_raw") or "")
        if len(codigo) >= 6 and codigo in sanitizar(otro.get("descripcion") or ""):
            return True
    return False


def evidencia_cruzada(id_a, id_b, cuenta_palabras=None, total_descripciones=None,
                      rubros_oem=None):
    """Corre TODOS los métodos sobre un mismo par y cuenta cuántos coinciden.

    Es la mejora de precisión más grande que faltaba. Hasta ahora cada método trabajaba solo:
    el de descripciones proponía sus pares, el de medidas los suyos, el de catálogos los suyos,
    y todos caían en la misma cola con el mismo peso. Pero no valen lo mismo.

    Que DOS métodos independientes lleguen al mismo par es muchísimo más fuerte que uno solo:
    que dos descripciones se parezcan puede ser casualidad, que además midan igual y encima
    el fabricante las dé para el mismo auto, no.

    Y al revés, lo que más precisión gana: los VETOS. Si las medidas se contradicen, no importa
    cuántos métodos digan que sí — no es la misma pieza. Antes eso era una alarma más entre
    varias; acá tumba el par.

    rubros_oem es lo de rubros_de_los_codigos_de_fabrica(), para no tomarle al código de
    fábrica el rubro de la fila que lo nombró primero. Quien llama en un bucle lo pasa hecho.

    Devuelve (a_favor, vetos, veredicto)."""
    c.execute(f"""SELECT p.id, p.codigo_raw, p.codigo_clean, p.descripcion, p.precio,
                         p.marca_id, m.nombre AS marca, m.tipo AS tipo, {COLUMNAS_MEDIDAS}
                  FROM productos p JOIN marcas m ON m.id = p.marca_id
                  WHERE p.id IN (?, ?)""", (id_a, id_b))
    filas = {r["id"]: dict(r) for r in c.fetchall()}
    if id_a not in filas or id_b not in filas:
        return [], ["uno de los dos productos ya no existe"], "🔴 no se puede evaluar"
    pa, pb = filas[id_a], filas[id_b]

    a_favor, vetos = [], []

    # 0. DOS PRODUCTOS DEL MISMO PROVEEDOR. Un catálogo no lista dos veces la misma pieza
    # para que elijas: si aparecen vinculados y además dicen exactamente lo mismo, es una fila
    # leída dos veces —la celda del código traía dos cosas y una no era un código—. Son 196
    # vínculos en la base real, todos de la misma lista, y salen de pedazos de la descripción
    # que quedaron como código: «PVC», «SPR», «SOPORTE», «CHAPA».
    if pa["marca_id"] == pb["marca_id"]:
        _sin_digitos = [x["codigo_raw"] for x in (pa, pb)
                        if not any(ch.isdigit() for ch in (x["codigo_clean"] or ""))]
        if _sin_digitos:
            vetos.append(f"🏷️ los dos son de {pa['marca']} y «{_sin_digitos[0]}» no tiene ningún "
                          "número: es un pedazo de la descripción que quedó como código")
        elif (pa["descripcion"] or "").strip() == (pb["descripcion"] or "").strip():
            vetos.append(f"🏷️ los dos son de {pa['marca']} y tienen la misma descripción: es "
                          "una fila de la lista leída dos veces, no dos repuestos equivalentes")

    # 1. Medidas. Es el único método que puede VETAR: si las medidas se contradicen, no hay
    # descripción ni catálogo que lo arregle.
    medidas = cargar_medidas_de_varios([id_a, id_b])
    coinciden, detalle_med = comparar_medidas(medidas.get(id_a), medidas.get(id_b))
    if coinciden is True:
        a_favor.append(f"📐 las medidas coinciden ({detalle_med})")
    elif coinciden is False:
        vetos.append(f"📐 {detalle_med}")

    # 2. Descripción
    fa = firma_de_producto(pa["descripcion"], id_a, pa["codigo_clean"])
    fb = firma_de_producto(pb["descripcion"], id_b, pb["codigo_clean"])
    # Copia, no se toca la firma: es la misma para todos los que la piden. Ver
    # firma_de_producto().
    _rub_a = rubro_del_codigo_frente_a(rubros_oem, id_a, pa["descripcion"], pb["descripcion"])
    _rub_b = rubro_del_codigo_frente_a(rubros_oem, id_b, pb["descripcion"], pa["descripcion"])
    if fa and _rub_a:
        fa = dict(fa, familia=_rub_a)
    if fb and _rub_b:
        fb = dict(fb, familia=_rub_b)
    # El conteo de palabras del catálogo entero se puede pasar hecho, y hay que pasarlo cuando
    # se llama a esto en un bucle. Cada llamada cuesta un COUNT + SUM(LENGTH(...)) sobre toda
    # la tabla para saber si el caché sigue vigente, más deserializar el diccionario de 100.000
    # palabras. Son 34 ms; parece nada hasta que se revisan 400 vínculos de una importación:
    # la pantalla de «Equivalencias sugeridas» tardaba 37 segundos y 13 eran esto.
    if cuenta_palabras is None or total_descripciones is None:
        cuenta_palabras, total_descripciones = cuantas_veces_aparece_cada_palabra()
    _cuenta, _total = cuenta_palabras, total_descripciones
    ok_desc, motivo_desc = firmas_compatibles(fa, fb, cuenta_palabras=_cuenta,
                                              total_descripciones=_total)
    # Antes del rubro: ¿uno viene adentro del otro? Es cierto que los rubros no coinciden —una
    # bujía no es un juego de cables— y aun así «rubros distintos» no describe lo que pasa. Ver
    # _uno_trae_al_otro(): sobre los 208 vínculos con rubros distintos que hay cargados, 126
    # son de esta clase.
    _kit_de = _uno_trae_al_otro(pa.get("descripcion"), pa.get("codigo_raw"),
                                 pb.get("descripcion"), pb.get("codigo_raw"),
                                 pa.get("tipo"), pb.get("tipo"))
    if ok_desc:
        a_favor.append(f"🔤 las descripciones concuerdan ({motivo_desc})")
        # El espesor solo no prueba que sea la misma pieza (ver el final de
        # comparar_medidas()), pero cuando las descripciones ya dicen que es la misma junta del
        # mismo auto, que además midan igual confirma que es la MISMA VARIANTE: de las tres
        # juntas de un motor, la del mismo espesor. «Jta.Tapa Cil. CHEVROLET CORSA ESP 1,00MM»
        # contra «Junta Tapa de Cilindros CHEVROLET (ESP 1.00MM) CORSA...» es eso.
        # Solo el espesor: la posición y las vías salen del mismo texto que ya se comparó.
        if coinciden is None and detalle_med.startswith("Solo coinciden en espesor:"):
            a_favor.append("📐 el espesor coincide: es la misma variante")
    elif _kit_de:
        vetos.append(f"📦 no son equivalentes: {_kit_de}. El buscador te lo ofrece igual, "
                      "como kit, cuando buscás la pieza suelta")
    elif fa and fb and fa["familia"] != "Sin clasificar" and fb["familia"] != "Sin clasificar":
        if fa["familia"] != fb["familia"]:
            vetos.append(f"🧩 rubros distintos: «{fa['familia']}» y «{fb['familia']}»")
        elif (motivo_desc.startswith(_MOTIVOS_QUE_CONTRADICEN)
              and not (motivo_desc.startswith(_MOTIVOS_DEL_AUTO) and _unidos_por_codigo(pa, pb))):
            vetos.append(f"🔤 {motivo_desc}")

    # 3. El catálogo del fabricante: ¿los da para el mismo auto?
    try:
        # Las deducidas quedan afuera por lo mismo que en analizar_lote_pendiente(): esta vía
        # cuenta como UNA de las tres evidencias que fuerzan el puntaje a 90, y una aplicación
        # deducida de la descripción no es un tercer camino independiente — es el mismo texto
        # que ya miran las señales de descripción, con el cartel de «lo dice el fabricante».
        c.execute("""SELECT COUNT(*) FROM aplicaciones a JOIN aplicaciones b
                       ON a.marca_auto = b.marca_auto AND a.modelo_auto = b.modelo_auto
                     WHERE a.codigo_clean = ? AND b.codigo_clean = ?
                       AND a.marca_repuesto <> b.marca_repuesto
                       AND COALESCE(a.origen, '') <> 'deducida'
                       AND COALESCE(b.origen, '') <> 'deducida'""",
                  (pa["codigo_clean"], pb["codigo_clean"]))
        autos_juntos = c.fetchone()[0]
        if autos_juntos:
            a_favor.append(f"🏭 dos fabricantes los dan para {autos_juntos} auto(s) en común")
    except sqlite3.OperationalError as _err:
        anotar_error("evidencia_cruzada", _err)
        pass

    # 4. El mostrador: ¿ya se vendió uno en lugar del otro?
    veces = pares_confirmados_por_ventas().get((min(id_a, id_b), max(id_a, id_b)), 0)
    if veces >= 2:
        a_favor.append(f"🧾 ya lo vendiste como reemplazo {veces} vez(ces)")

    # 5. Un código de fábrica compartido
    try:
        c.execute("""SELECT COUNT(*) FROM equivalencias e
                     WHERE (e.producto_a_id = ? AND e.producto_b_id = ?)
                        OR (e.producto_a_id = ? AND e.producto_b_id = ?)""",
                  (min(id_a, id_b), max(id_a, id_b), max(id_a, id_b), min(id_a, id_b)))
        if c.fetchone()[0]:
            a_favor.append("🔗 ya están vinculados en la base")
    except sqlite3.OperationalError as _err:
        anotar_error("evidencia_cruzada", _err)
        pass

    # 6. Reemplazo de código declarado
    for viejo, nuevo in ((pa["codigo_clean"], pb["codigo_clean"]),
                         (pb["codigo_clean"], pa["codigo_clean"])):
        if any(x["clean"] == nuevo for x in cadena_de_reemplazos(viejo)):
            a_favor.append("🔄 el fabricante reemplazó uno por el otro")
            break

    # 7. Precio: no confirma nada por sí solo, pero una diferencia enorme sí desmiente.
    # Igual que en evaluar_equivalencia(), la diferencia se mide contra lo TÍPICO entre esos
    # dos proveedores. Dos listas pueden estar en escalas completamente distintas —una
    # desactualizada, otra sin IVA— y entonces TODAS las parejas entre ellas se diferencian por
    # el mismo factor. Sobre las listas reales el precio mediano de un proveedor es $1.350 y el
    # de otro $37.610: 28 veces. Con el umbral fijo en 15, este veto tumbaba a 15 puntos casi
    # todas las parejas entre esos dos, y un veto no admite discusión — el par se iba a revisión
    # manual aunque fuera la misma bobina con el mismo texto.
    # Acá pesa más que en evaluar_equivalencia() justamente porque VETA en vez de descontar.
    if pa["precio"] and pb["precio"] and pa["precio"] > 0 and pb["precio"] > 0:
        razon = max(pa["precio"], pb["precio"]) / min(pa["precio"], pb["precio"])
        escalas = escalas_de_precio()
        ea, eb = escalas.get(pa["marca"]) or 0, escalas.get(pb["marca"]) or 0
        esperada = max(ea, eb) / min(ea, eb) if ea > 0 and eb > 0 else 1.0
        razon_real = razon / esperada if esperada > 1 else razon
        if razon_real < 1:
            razon_real = 1 / razon_real
        if razon_real >= 15:
            vetos.append(f"💲 los precios se diferencian {razon:.0f} veces"
                         + (f" (entre estas dos listas lo normal es {esperada:.0f})"
                            if esperada > 2 else ""))

    if vetos:
        veredicto = "🔴 hay evidencia en contra"
    elif len(a_favor) >= 3:
        veredicto = "🟢 confirmada por varios métodos"
    elif len(a_favor) == 2:
        veredicto = "🟡 dos métodos coinciden"
    elif len(a_favor) == 1:
        veredicto = "🟠 un solo método, conviene mirarla"
    else:
        veredicto = "⚪ sin evidencia a favor"
    return a_favor, vetos, veredicto


def derivar_equivalencias_por_medidas(minimo_medidas=3, limite=400):
    """Encuentra equivalencias cruzando las MEDIDAS cargadas, entre marcas distintas.

    Las medidas se venían usando solo para verificar un vínculo que ya existía. Pero en varias
    familias la medida ES la identidad de la pieza: un retén 35x52x7 de un proveedor y uno
    35x52x7 de otro son el mismo repuesto, y no hace falta que las descripciones se parezcan
    ni que compartan un código.

    Es la evidencia más fuerte que hay: no es texto ni interpretación, es la pieza física.

    Se piden al menos 3 medidas coincidentes. Con una sola —por ejemplo, solo el diámetro
    interno— coincidirían piezas completamente distintas que casualmente miden lo mismo."""
    campos = [cn for cn, _ in CAMPOS_MEDIDAS]
    seleccion = ", ".join(f"p.{cn}" for cn in campos)
    c.execute(f"""SELECT p.id, p.codigo_raw, p.descripcion, p.marca_id, m.nombre AS marca,
                         p.precio, p.stock, {seleccion}, p.paso_rosca, p.cantidad_estrias
                  FROM productos p JOIN marcas m ON m.id = p.marca_id""")
    productos = [dict(r) for r in c.fetchall()]

    # Se agrupa por la combinación exacta de medidas. Sin agrupar habría que comparar todos
    # contra todos; agrupando, los que comparten medidas caen juntos y el resto ni se mira.
    grupos = {}
    for f in productos:
        valores = tuple(round(f[cn], 2) if f[cn] is not None else None for cn in campos)
        cuantas = sum(1 for v in valores if v is not None)
        if cuantas < minimo_medidas:
            continue
        clave = valores + ((f["paso_rosca"] or "").strip().upper(),
                           (f["cantidad_estrias"] or "").strip().upper())
        grupos.setdefault(clave, []).append(f)

    ya = set()
    c.execute("SELECT producto_a_id, producto_b_id FROM equivalencias")
    for r in c.fetchall():
        ya.add((r["producto_a_id"], r["producto_b_id"]))
    rechazados = pares_rechazados()

    salida = []
    for clave, miembros in grupos.items():
        # Solo interesa si hay al menos dos MARCAS distintas: dos códigos de la misma marca
        # con las mismas medidas suelen ser presentaciones del mismo producto, no equivalentes
        # que aporten algo.
        if len({f["marca_id"] for f in miembros}) < 2:
            continue
        for i, pa in enumerate(miembros):
            for pb in miembros[i + 1:]:
                if pa["marca_id"] == pb["marca_id"]:
                    continue
                par = (min(pa["id"], pb["id"]), max(pa["id"], pb["id"]))
                if par in ya or par in rechazados:
                    continue
                # Aun con las medidas iguales, dos rubros distintos no son la misma pieza:
                # una arandela y un separador pueden medir exactamente lo mismo.
                # Con las medidas iguales igual hay que mirar la pieza: una arandela y un
                # retén pueden medir exactamente lo mismo. Y no alcanza con comparar el rubro
                # —«ARANDELA DE COBRE» queda sin clasificar y se colaba—, así que se compara
                # también el sustantivo principal de la descripción.
                fa = firma_de_producto(pa["descripcion"] or "")
                fb = firma_de_producto(pb["descripcion"] or "")
                if not fa or not fb:
                    continue
                if ("Sin clasificar" not in (fa["familia"], fb["familia"])
                        and fa["familia"] != fb["familia"]):
                    continue
                if fa["cabeza"] and fb["cabeza"] and fa["cabeza"] != fb["cabeza"]:
                    if not (fa["cabeza"] in fb["cabeza"] or fb["cabeza"] in fa["cabeza"]):
                        continue
                detalle = ", ".join(
                    f"{eti} {clave[j]}" for j, (cn, eti) in enumerate(CAMPOS_MEDIDAS)
                    if clave[j] is not None
                )
                salida.append({
                    "Código A": pa["codigo_raw"], "Marca A": pa["marca"],
                    "Descripción A": (pa["descripcion"] or "")[:40],
                    "Código B": pb["codigo_raw"], "Marca B": pb["marca"],
                    "Descripción B": (pb["descripcion"] or "")[:40],
                    "Medidas que coinciden": detalle[:70],
                    "_a": pa["id"], "_b": pb["id"],
                })
                if len(salida) >= limite:
                    return salida
    return salida


def equivalencias_puenteadas_por_reemplazo(limite=300):
    """Vincula lo que quedó separado porque el fabricante cambió el número.

    Caso concreto: tenés A vinculado al código de fábrica viejo, y B vinculado al nuevo. Son
    el mismo repuesto, pero para la app son dos islas sin relación, porque el cambio de número
    partió la cadena al medio.

    Los reemplazos que cargaste a mano ya sabían que el viejo y el nuevo son lo mismo. Esto
    usa ese dato para volver a unir lo que el cambio de número separó."""
    try:
        c.execute("SELECT codigo_viejo_clean, codigo_nuevo_clean FROM reemplazos_codigo")
        cadenas = [(r["codigo_viejo_clean"], r["codigo_nuevo_clean"]) for r in c.fetchall()]
    except sqlite3.OperationalError as _err:
        anotar_error("equivalencias_puenteadas_por_reemplazo", _err)
        return []
    if not cadenas:
        return []

    ya = set()
    c.execute("SELECT producto_a_id, producto_b_id FROM equivalencias")
    for r in c.fetchall():
        ya.add((r["producto_a_id"], r["producto_b_id"]))
    rechazados = pares_rechazados()

    salida = []
    for viejo, nuevo in cadenas:
        c.execute("""SELECT p.id, p.codigo_raw, m.nombre AS marca, p.descripcion
                     FROM productos p JOIN marcas m ON m.id = p.marca_id
                     WHERE p.codigo_clean = ?""", (viejo,))
        de_viejo = [dict(r) for r in c.fetchall()]
        c.execute("""SELECT p.id, p.codigo_raw, m.nombre AS marca, p.descripcion
                     FROM productos p JOIN marcas m ON m.id = p.marca_id
                     WHERE p.codigo_clean = ?""", (nuevo,))
        de_nuevo = [dict(r) for r in c.fetchall()]
        for pa in de_viejo:
            for pb in de_nuevo:
                par = (min(pa["id"], pb["id"]), max(pa["id"], pb["id"]))
                if pa["id"] == pb["id"] or par in ya or par in rechazados:
                    continue
                salida.append({
                    "Código A": pa["codigo_raw"], "Marca A": pa["marca"],
                    "Código B": pb["codigo_raw"], "Marca B": pb["marca"],
                    "Por qué": f"el fabricante reemplazó {pa['codigo_raw']} por {pb['codigo_raw']}",
                    "_a": pa["id"], "_b": pb["id"],
                })
                if len(salida) >= limite:
                    return salida
    return salida


# Antes 4.000, que sobre la lista de JL —25.975 productos— dejaba afuera el 85%, y siempre
# las mismas filas: las últimas de cada lista no se comparaban NUNCA, corrieras la comparación
# las veces que la corrieras. Medido con las listas reales, sin tope el peor cruce (JL de
# 25.975 contra Illinois de 6.898) tarda 16,5 s contra 4,4 s, y JL x MOTORARG pasa de 11
# sugerencias a 400. Queda un número igual, pero uno que ninguna lista de proveedor alcanza.
TOPE_PRODUCTOS_POR_COMPARACION = 50000  # ver derivar_equivalencias_por_descripcion()


def derivar_equivalencias_por_descripcion(marca_a_id=None, marca_b_id=None,
                                          limite=2000,
                                          tope_productos=TOPE_PRODUCTOS_POR_COMPARACION,
                                          por_producto=3):
    """Vincula productos de DOS proveedores distintos comparando lo que dicen sus descripciones.

    Es la respuesta al problema de fondo: la mayoría de las listas no traen el código de
    fábrica, y sin esa columna la app no generaba ninguna equivalencia. Con esto, dos
    proveedores que describen la misma pieza para el mismo auto quedan vinculados.

    Se compara solo dentro del mismo rubro. Eso no es una optimización: es lo que evita que
    esto se convierta en otra fábrica de vínculos falsos, y de paso hace la comparación
    manejable —sin agrupar, serían millones de pares—."""
    if not marca_a_id or not marca_b_id or marca_a_id == marca_b_id:
        return []

    productos = {}
    for mid in (marca_a_id, marca_b_id):
        c.execute("""SELECT p.id, p.codigo_raw, p.codigo_clean, p.descripcion, p.precio,
                            p.stock, m.nombre AS marca
                     FROM productos p JOIN marcas m ON m.id = p.marca_id
                     WHERE p.marca_id = ? AND COALESCE(p.descripcion,'') <> ''
                     LIMIT ?""", (mid, tope_productos))
        productos[mid] = [dict(r) for r in c.fetchall()]

    # Las firmas ya calculadas, si el barrido de todo el catálogo las dejó en el caché: son
    # los mismos productos y la misma cuenta, y sacarlas de vuelta cuesta 15 s. Lo que no esté
    # —un catálogo de fábrica, que el barrido no mira— se calcula acá.
    _fichas = firmas_de_todo_el_catalogo(version_del_catalogo())[1]

    # Se agrupa por rubro antes de comparar: solo tiene sentido cruzar filtros con filtros
    por_rubro = {mid: {} for mid in productos}
    for mid, filas in productos.items():
        for f in filas:
            _guardada = _fichas.get(f["id"])
            firma = (_guardada[0] if _guardada else
                     firma_de_producto(f["descripcion"], f["id"], f.get("codigo_clean")))
            if not firma or firma["familia"] == "Sin clasificar":
                continue
            f["_firma"] = firma
            por_rubro[mid].setdefault(firma["familia"], []).append(f)

    _cuenta_pal, _total_desc = cuantas_veces_aparece_cada_palabra()
    ya_vinculados = set()
    c.execute("SELECT producto_a_id, producto_b_id FROM equivalencias")
    for r in c.fetchall():
        ya_vinculados.add((r["producto_a_id"], r["producto_b_id"]))
    rechazados = pares_rechazados()

    salida = []
    for familia in set(por_rubro[marca_a_id]) & set(por_rubro[marca_b_id]):
        for pa in por_rubro[marca_a_id][familia]:
            # Los mejores candidatos de ESTE producto, no todos. Un termostato de Ford puede
            # coincidir con quince del otro proveedor, y esos quince tapan al resto del
            # catálogo: se llega al tope mostrando siempre lo mismo. Se guardan los que más
            # autos comparten, que son los más probables.
            candidatos = []
            for pb in por_rubro[marca_b_id][familia]:
                par = (min(pa["id"], pb["id"]), max(pa["id"], pb["id"]))
                if par in ya_vinculados or par in rechazados:
                    continue
                ok, motivo = firmas_compatibles(pa["_firma"], pb["_firma"],
                                                cuenta_palabras=_cuenta_pal,
                                                total_descripciones=_total_desc)
                if not ok:
                    continue
                fuerza = fuerza_de_la_coincidencia(pa["_firma"], pb["_firma"])
                candidatos.append((fuerza, pb, motivo))
            # De mayor a menor fuerza. Antes ordenaba solo por marcas de auto compartidas y
            # empataba casi todo en 1: ver fuerza_de_la_coincidencia().
            candidatos.sort(key=lambda x: x[0], reverse=True)
            for _fuerza, pb, motivo in candidatos[:por_producto]:
                salida.append({
                    "Código A": pa["codigo_raw"], "Marca A": pa["marca"],
                    "Descripción A": (pa["descripcion"] or "")[:44],
                    "Código B": pb["codigo_raw"], "Marca B": pb["marca"],
                    "Descripción B": (pb["descripcion"] or "")[:44],
                    "Rubro": familia, "Por qué": motivo,
                    "_a": pa["id"], "_b": pb["id"],
                })
                if len(salida) >= limite:
                    return salida
    return salida


RELLENO_EN_NOMBRE_DE_PIEZA = {"DE", "LA", "EL", "CON", "SIN", "PARA", "POR", "DEL", "EN", "LOS",
                       "LAS", "UN", "UNA", "MM", "CM", "TIPO", "JUEGO", "JGO", "KIT", "COMPLETO",
                       "REF", "ORIG"}
# El nombre es específico a propósito: más abajo hay un _PALABRAS_DE_RELLENO que es OTRA cosa
# —las muletillas de un pedido hablado, «necesito», «dame»— y dos constantes casi homónimas a
# mil líneas de distancia son una edición equivocada esperando pasar.


# Cómo abrevian los proveedores el nombre de la pieza. No están inventadas: salieron de contar
# las palabras que entran al nombre en las 61.574 descripciones reales — «JTA» aparece 4.836
# veces, «JTAS» 2.456, «CIL» 2.115. Sin esto, «CABLE BUJIA» y «KIT CAB Y BUJ» son dos cosas
# distintas para la app, y el vínculo correcto entre ellas queda marcado como sospechoso.
ABREVIATURAS_DE_PIEZA = {
    "JTA": "JUNTA", "JTAS": "JUNTA", "JUNTAS": "JUNTA", "JGO": "JUEGO", "JGOS": "JUEGO",
    "CIL": "CILINDRO", "CILS": "CILINDRO", "CILINDROS": "CILINDRO",
    "CAB": "CABLE", "CABLES": "CABLE", "BUJ": "BUJIA", "BUJIAS": "BUJIA",
    "CPO": "CUERPO", "INY": "INYECCION", "INYEC": "INYECCION",
    "BBA": "BOMBA", "BOMBAS": "BOMBA", "TEMP": "TEMPERATURA", "MULT": "MULTIPLE",
    "ELECTROV": "ELECTROVENTILADOR", "ELECTROVENT": "ELECTROVENTILADOR",
    "ACEL": "ACELERADOR", "DISTRIB": "DISTRIBUCION", "REFRIG": "REFRIGERACION",
    "ALTERN": "ALTERNADOR", "ARRANQ": "ARRANQUE", "SENS": "SENSOR", "SENSORES": "SENSOR",
    "VALV": "VALVULA", "VALVULAS": "VALVULA", "TAPAS": "TAPA", "CANOS": "CANO",
    "RET": "RETEN", "RETENES": "RETEN", "TERM": "TERMOSTATO", "AMORT": "AMORTIGUADOR",
    "PAST": "PASTILLA", "PASTILLAS": "PASTILLA", "FILT": "FILTRO", "FILTROS": "FILTRO",
    "INTERRUP": "INTERRUPTOR", "REGUL": "REGULADOR", "PRES": "PRESION",
    "COMB": "COMBUSTIBLE", "IGNIC": "IGNICION", "ROTAC": "ROTACION", "DETONAC": "DETONACION",
    # Salidas de comparar las dos listas de juntas, que abrevian distinto la misma pieza:
    # Taranto escribe «Jta.Tapa Cilind.Ford» e Illinois «Junta Tapa de Cilindros FORD».
    "CILIND": "CILINDRO", "CILINDRICO": "CILINDRO", "CILIN": "CILINDRO", "JTO": "JUEGO",
    "JUEGOS": "JUEGO", "VAL": "VALVULA", "VALV": "VALVULA", "VALVS": "VALVULA",
    "ADMIS": "ADMISION", "ESCAP": "ESCAPE", "TRANSM": "TRANSMISION", "DELANT": "DELANTERO",
    "TRAS": "TRASERO", "SUPL": "SUPLEMENTO", "SUPLEM": "SUPLEMENTO", "REPAR": "REPARACION",
    "COLEC": "COLECTOR", "COLECT": "COLECTOR", "ASPIR": "ASPIRACION", "COMPRES": "COMPRESOR",
}


def _nombre_de_la_pieza(descripcion, aceptar_codigos=False):
    """Las palabras que nombran LA PIEZA, sin los códigos y con las abreviaturas expandidas.

    Se corta apenas aparece una marca de auto o un año, porque de ahí en adelante la descripción
    deja de hablar de la pieza y empieza a listar para qué autos sirve.

    Los tokens con dígitos se descartan: son el número de parte o una medida, no el nombre. Eran
    el 73% de las palabras distintas que entraban acá (LEIHTT09SCFIAT, 64033, LSPKR6E), y como
    nunca coinciden entre dos proveedores solo servían para bajar el parecido de vínculos que
    estaban bien. Si al sacarlos no queda nada, se vuelve a armar con ellos: un nombre flojo es
    mejor que ninguno, porque sin nombre el parecido da 0 y eso también marca de más.

    Medido sobre los 24.774 vínculos reales: los marcados como «nombre de pieza muy distinto»
    bajan de 963 a 608, y los pocos que dejan de marcarse —revisados uno por uno— eran todos
    vínculos correctos («CABLE DE BUJIA» contra «KIT CAB Y BUJ»)."""
    # «VW» y «GM» ya están en MARCAS_VEHICULO; queda «MB», que no vale la pena agregar allá
    # porque como palabra suelta aparece adentro de descripciones que no hablan de Mercedes.
    marcas_auto = set(MARCAS_VEHICULO) | {"MB"}
    palabras = []
    for palabra in re.split(r'[^A-Z0-9]+', normalizar_texto(descripcion or "")):
        if not palabra:
            continue
        if palabra in marcas_auto or re.fullmatch(r'(19|20)\d{2}', palabra):
            break
        if any(ch.isdigit() for ch in palabra) and not aceptar_codigos:
            continue
        palabra = ABREVIATURAS_DE_PIEZA.get(palabra, palabra)
        if len(palabra) >= 3 and palabra not in RELLENO_EN_NOMBRE_DE_PIEZA:
            palabras.append(palabra)
        if len(palabras) >= 4:
            break
    if not palabras and not aceptar_codigos:
        return _nombre_de_la_pieza(descripcion, aceptar_codigos=True)
    return set(palabras)


def _parecido_nombre_pieza(desc_a, desc_b):
    """Cuánto se parecen los NOMBRES DE LA PIEZA de dos descripciones, de 0 a 1."""
    pieza_a, pieza_b = _nombre_de_la_pieza(desc_a), _nombre_de_la_pieza(desc_b)
    if not pieza_a or not pieza_b:
        return 0.0
    return len(pieza_a & pieza_b) / len(pieza_a | pieza_b)


def _mejores_primero(pares):
    """Ordena las sugerencias por cuánto se parecen, de mejor a peor.

    Sin esto salían en el orden en que se recorre el índice de palabras, o sea al azar. Daba lo
    mismo cuando eran 807; con 5.597 no da lo mismo: nadie revisa 5.597 de una sentada, y el que
    revisa las primeras cincuenta tiene que estar viendo las cincuenta mejores, no cincuenta
    cualesquiera. Ordena por el modelo compartido primero, después la cilindrada, el nombre de
    la pieza y la marca del auto — ver fuerza_de_la_coincidencia()."""
    return sorted(pares, key=lambda x: x.get("_fuerza") or (0, 0, 0, 0), reverse=True)


@st.cache_data(show_spinner=False, max_entries=1)
def firmas_de_todo_el_catalogo(version):
    """(índice de palabras, fichas) de todos los productos de proveedor. Cacheado por catálogo.

    Es lo caro del barrido y lo único que no cambia entre una corrida y la siguiente: leer las
    46.644 descripciones y sacarles la firma tarda 15,2 s, contra 3 s que cuesta comparar. Sin
    caché, apretar el botón dos veces cuesta dos veces lo mismo aunque no se haya tocado nada.
    Guardado ocupa 17 MB y volver a leerlo 0,4 s, así que la segunda corrida pasa de 19 a 4 s.

    El testigo va SIN guion bajo a propósito: ver descripciones_por_palabra()."""
    ceder_al_mostrador()      # antes de la lectura grande. Ver ceder_al_mostrador().
    from collections import defaultdict
    try:
        c.execute("""SELECT p.id, p.codigo_raw, p.codigo_clean, p.descripcion, p.marca_id,
                            m.nombre AS marca
                     FROM productos p JOIN marcas m ON m.id = p.marca_id
                     WHERE m.tipo <> 'OEM' AND COALESCE(p.descripcion, '') <> ''""")
        productos = filas_a_listas(c)
    except sqlite3.OperationalError as _err:
        anotar_error("firmas_de_todo_el_catalogo", _err)
        return {}, {}
    indice, ficha = defaultdict(list), {}
    for prod in productos:
        ceder_al_mostrador()
        firma = firma_de_producto(prod["descripcion"], prod["id"], prod.get("codigo_clean"))
        if not firma or firma["familia"] == "Sin clasificar":
            continue
        palabras = {p for p in re.split(r'[^A-Z0-9]+', normalizar_texto(prod["descripcion"]))
                    if len(p) >= 3}
        ficha[prod["id"]] = (firma, prod)
        for palabra in palabras:
            indice[palabra].append(prod["id"])
    return dict(indice), ficha


# Sobre el catálogo real salen 8.122, así que 8.000 volvía a cortar justo como cortaba 600
# antes y 2.000 después. Traerlos todos no cuesta nada —lo caro es compararlos, y eso ya está
# hecho— y ahora además se ordenan antes de cortar, así que si alguna vez se llega al tope lo
# que queda afuera son los peores. Ver sugerir_entre_todas_las_marcas().
TOPE_SUGERENCIAS_TODAS = 20000  # ver sugerir_entre_todas_las_marcas()


def sugerir_entre_todas_las_marcas(limite=TOPE_SUGERENCIAS_TODAS, tope_palabra=250):
    """Lo mismo que derivar_equivalencias_por_descripcion(), pero de UNA VEZ para todo el
    catálogo en vez de elegir dos proveedores a mano.

    Por qué hace falta: con cinco proveedores cargados hay diez combinaciones para correr de a
    una, y con ocho son veintiocho. Nadie las corre todas, así que la mitad de los cruces
    posibles no se buscan nunca.

    La decisión de si dos productos son el mismo repuesto NO se toma acá: se delega en
    firmas_compatibles(), que es la que ya venía haciéndolo y sabe mirar la posición, la
    cilindrada, las siglas y el sustantivo principal. Duplicar ese criterio sería peor que no
    tenerlo — dos reglas parecidas que con el tiempo dejan de decir lo mismo.

    Lo único que aporta esta función es cómo ELEGIR qué pares mirar sin comparar todo contra
    todo. Con 110.000 productos serían seis mil millones de pares. En vez de eso se arma un
    índice de palabras POCO COMUNES: las que aparecen en pocos productos. Una palabra que está
    en miles no distingue nada; una que está en uno solo no puede emparejar; sirven las del
    medio. Comparando únicamente los pares que comparten alguna de esas queda del orden de
    ciento cincuenta mil, y se resuelve en segundos.

    DÓNDE CORTAR ESE «POCO COMÚN» ES LA DECISIÓN MÁS CARA DE ACÁ, y estaba en 40 sin haberla
    medido. Corrido sobre el catálogo real, cambiando solo ese número:

        40   →    807 sugerencias   15,9 s   confianza media 51,5   1% por debajo de 40
        100  →  2.280               16,2 s   confianza media 52,4   2%
        250  →  5.597               18,8 s   confianza media 61,4   1%
        500  → 11.899               26,4 s   confianza media 45,4   41%  ← se rompe

    O sea que con 40 se estaban perdiendo siete de cada ocho relaciones buenas por tres
    segundos, y que el límite de verdad está entre 250 y 500: pasando de ahí entran los pares
    que solo comparten la marca del auto y dos palabras genéricas («INTERRUPTOR STOP FORD»
    contra otro «INTERRUPTOR STOP FORD» de otro modelo), y 4 de cada 10 nacen ya en rojo.

    El tiempo casi no se mueve entre 40 y 250 porque lo caro no es comparar: es leer las 46.644
    descripciones y sacarles la firma (15,2 s de los 18,8). Eso ahora va cacheado por versión
    del catálogo —ver firmas_de_todo_el_catalogo()—, así que la segunda corrida tarda 4 s.

    Nada se carga solo: todo va a la cola de pendientes para que lo apruebe una persona.

    El tope no ahorra tiempo: el recorrido cuesta lo mismo con tope o sin él (19 s sobre 70.888
    productos), porque lo caro es armar el índice y comparar, no guardar el resultado. Lo único
    que hace el tope es esconder pares. Estuvo en 200 y cortaba de verdad —de 284 pares reales
    se veían 84—, se subió a 600 y volvió a cortar en cuanto entró una lista más: con Illinois
    cargada salen 787 y se veían 600. Ahora está en 2.000, y si alguna vez se llega, la
    pantalla lo dice en vez de callárselo."""
    indice, ficha = firmas_de_todo_el_catalogo(version_del_catalogo())
    if not ficha:
        return []

    _cuenta_pal, _total_desc = cuantas_veces_aparece_cada_palabra()
    raras = {p: ids for p, ids in indice.items() if 2 <= len(ids) <= tope_palabra}
    vistos, salida = set(), []
    for ids in raras.values():
        ceder_al_mostrador()
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = (ids[i], ids[j]) if ids[i] < ids[j] else (ids[j], ids[i])
                if (a, b) in vistos:
                    continue
                vistos.add((a, b))
                firma_a, prod_a = ficha[a]
                firma_b, prod_b = ficha[b]
                # Del mismo proveedor no: son dos productos de su catálogo, no equivalentes.
                if prod_a["marca_id"] == prod_b["marca_id"]:
                    continue
                ok, motivo = firmas_compatibles(firma_a, firma_b,
                                                cuenta_palabras=_cuenta_pal,
                                                total_descripciones=_total_desc)
                if not ok:
                    continue
                # Un filtro MÁS, que solo hace falta acá. Comparando de a dos proveedores,
                # firmas_compatibles() alcanza porque el recorrido ya va por familia y se queda
                # con los tres mejores de cada producto. Barriendo TODO el catálogo entran
                # muchísimos más pares y ahí se ve que su control del sustantivo principal es
                # demasiado permisivo: deja pasar SENSOR contra SENSOR, y así proponía un sensor
                # MAP contra un sensor de velocidad de caja, un sensor ABS contra uno de
                # temperatura, y una ficha de 4 vías contra una de 2. Todos comparten la primera
                # palabra y el auto, y son piezas distintas.
                # Se midió: sin esto, de cada diez propuestas acertaba dos; con esto, nueve.
                # Se comparan las primeras palabras de cada descripción —las que nombran la
                # pieza, antes de que empiece a listar autos— y se pide que sean casi las mismas.
                if _parecido_nombre_pieza(prod_a["descripcion"], prod_b["descripcion"]) < 0.5:
                    continue
                # Acá el AUTO no puede faltar, y esto también es propio de este recorrido.
                # firmas_compatibles() exige que coincidan solo cuando las DOS descripciones
                # nombran alguno: si una no nombra ninguno, deja pasar, porque no se puede
                # descartar por falta de dato. Comparando de a dos proveedores eso está bien.
                # Acá no: el 36% de los productos no nombra ninguna marca de auto, así que esa
                # excepción se aplicaba a un tercio del catálogo y emparejaba por el nombre de
                # la pieza sola. De ahí salía un «SENSOR ABS» de VW Golf contra uno de BMW X5.
                # Con tantos pares candidatos, "no hay dato" tiene que ser un no.
                if not (firma_a["autos"] and firma_b["autos"] and (firma_a["autos"] & firma_b["autos"])):
                    continue
                salida.append({
                    "Código A": prod_a["codigo_raw"], "Marca A": prod_a["marca"],
                    "Descripción A": (prod_a["descripcion"] or "")[:44],
                    "Código B": prod_b["codigo_raw"], "Marca B": prod_b["marca"],
                    "Descripción B": (prod_b["descripcion"] or "")[:44],
                    "Rubro": firma_a["familia"], "Por qué": motivo,
                    "_a": a, "_b": b,
                    # Para poder mostrar primero lo mejor. Se calcula acá, que es donde las dos
                    # firmas ya están a mano: pedirlas de vuelta al final costaría el doble.
                    "_fuerza": fuerza_de_la_coincidencia(firma_a, firma_b),
                })
    # Se ordena ANTES de cortar. Cortando al llegar al tope, lo que quedaba afuera no eran los
    # peores: eran los que el recorrido del índice tocaba último, o sea cualquiera.
    return _mejores_primero(salida)[:limite]


def derivar_equivalencias_de_aplicaciones(limite=500, minimo_autos=2):
    """Deduce equivalencias cruzando los catálogos de aplicaciones de distintos fabricantes.

    El razonamiento: si NGK dice que su bujía U2003 va en un Palio 1.0 2003-2006, y Bosch dice
    que la suya va en EXACTAMENTE el mismo auto, las dos hacen el mismo trabajo. Son
    equivalentes, y ninguna lista de proveedor te lo iba a decir — es información que sale de
    cruzar dos catálogos que ya tenés.

    Tres condiciones, y las tres importan:
      · MISMO tipo de pieza. Sin esto se cruzaría una bujía con un filtro por ir al mismo auto,
        que es exactamente el error que venimos limpiando.
      · Fabricantes DISTINTOS. Dos códigos de la misma marca para el mismo auto suelen ser
        variantes (la común y la de platino), no equivalentes entre sí.
      · Coincidir en varios autos, no en uno. Una coincidencia suelta puede ser casualidad;
        que dos códigos vayan juntos en varios modelos ya es un patrón.

    Y DOS MÁS QUE HACEN FALTA DESDE QUE LAS APLICACIONES SE DEDUCEN DE LAS DESCRIPCIONES.
    Antes esta tabla se llenaba solo con el catálogo que mandaba un fabricante —unos cientos de
    filas— y ahora se llena leyendo las 70.888 descripciones, o sea 52.534 aplicaciones. Con
    eso, «mismo tipo de pieza y mismo auto» deja de alcanzar:
      · el «fabricante» no puede ser OEM / FABRICA. Esa marca no es el catálogo de nadie: son
        los códigos de fábrica que la app dedujo, y cruzarlos por aplicación propone el mismo
        vínculo que ya hace el puente por código, pero sin la certeza del número.
      · el tipo de pieza que se guarda es la FAMILIA (21 en total), así que «misma familia y
        mismo auto» mete en la misma bolsa todas las sondas lambda de ese auto — que se
        diferencian en los cables, el largo y la ficha. Se le pide además que las dos
        descripciones se parezcan, con el mismo criterio de siempre.
    Medido sobre el catálogo real: 32.768 candidatos, 1.987 al sacar los de OEM / FABRICA y
    146 al pedirles además que las descripciones coincidan. Lo que se va es justo eso: cinco
    sondas lambda distintas colgadas del mismo código de Bosch por ir a los mismos 13 autos.

    No las carga: las deja como pendientes para que pasen por la misma revisión que el resto."""
    c.execute("""SELECT a.codigo_clean AS cod_a, a.marca_repuesto AS marca_a,
                        b.codigo_clean AS cod_b, b.marca_repuesto AS marca_b,
                        COUNT(DISTINCT a.marca_auto || '|' || a.modelo_auto || '|' || a.motor) AS autos
                 FROM aplicaciones a
                 JOIN aplicaciones b
                   ON a.marca_auto = b.marca_auto
                  AND a.modelo_auto = b.modelo_auto
                  -- EL MOTOR CONTRADICE SOLO SI LOS DOS LO SABEN, igual que las medidas
                  -- físicas. Con `a.motor = b.motor` a secas, llenar esta columna EMPEORA las
                  -- cosas en vez de mejorarlas: el que declara su motor deja de cruzar con el
                  -- que no lo declara, y son la enorme mayoría. Medido al agregar el lector de
                  -- motores —4.880 filas de 112.764 quedaron con motor—: con la comparación
                  -- estricta se pierden 84.862 pares candidatos que antes cruzaban bien, sin
                  -- ganar nada a cambio. Un dato parcial comparado por igualdad estricta es
                  -- peor que no tener el dato.
                  -- …y tampoco contradice si alguna lista declara que esos dos motores se
                  -- llevan para ESTE tipo de pieza. Las bujías del TU5JP4 y las del EW10 son
                  -- las mismas y cada proveedor escribe los motores que se le ocurren; sin
                  -- esta excepción el veto separaba piezas que sí se reemplazan.
                  -- Ver aprender_motores_que_van_juntos().
                  AND (a.motor = b.motor OR COALESCE(a.motor,'') = ''
                       OR COALESCE(b.motor,'') = ''
                       OR EXISTS (SELECT 1 FROM motores_compatibles mc
                                  WHERE mc.tipo_pieza = COALESCE(a.tipo_pieza,'')
                                    AND mc.motor_a = MIN(a.motor, b.motor)
                                    AND mc.motor_b = MAX(a.motor, b.motor)))
                  -- El combustible, por el mismo motivo que el motor: una pieza del 1.6 nafta
                  -- no entra en el 1.9 diesel aunque el auto se llame igual. Con COALESCE
                  -- porque las filas viejas lo tienen en NULL y en SQL dos NULL nunca son
                  -- iguales: sin esto, esas filas dejarían de cruzarse entre ellas.
                  AND COALESCE(a.combustible,'') = COALESCE(b.combustible,'')
                  AND COALESCE(a.tipo_pieza,'') = COALESCE(b.tipo_pieza,'')
                  AND a.marca_repuesto <> b.marca_repuesto
                  AND a.codigo_clean < b.codigo_clean
                 WHERE COALESCE(a.tipo_pieza,'') <> ''
                   AND a.marca_repuesto <> 'OEM / FABRICA'
                   AND b.marca_repuesto <> 'OEM / FABRICA'
                 GROUP BY a.codigo_clean, b.codigo_clean
                 HAVING autos >= ?
                 ORDER BY autos DESC LIMIT ?""", (minimo_autos, limite))
    candidatos = filas_a_listas(c)

    # Solo sirven los que además existen en el catálogo propio: proponer una equivalencia entre
    # dos códigos que no tenés cargados no le sirve a nadie.
    # Los productos se buscan de a tandas y no de a uno: eran dos consultas por candidato, o
    # sea 65.536 consultas sobre los 32.768 candidatos del catálogo real.
    codigos = sorted({x["cod_a"] for x in candidatos} | {x["cod_b"] for x in candidatos})
    productos = {}
    for tanda, marcadores in en_tandas(codigos):
        c.execute(f"""SELECT p.id, p.codigo_raw, p.codigo_clean, p.descripcion,
                             m.nombre AS marca, m.tipo
                      FROM productos p JOIN marcas m ON m.id = p.marca_id
                      WHERE p.codigo_clean IN ({marcadores})""", tanda)
        for fila in c.fetchall():
            productos.setdefault(fila["codigo_clean"], dict(fila))

    _cuenta_pal, _total_desc = cuantas_veces_aparece_cada_palabra()
    firmas = {}

    def _firma(prod):
        if prod["id"] not in firmas:
            firmas[prod["id"]] = firma_de_producto(prod["descripcion"], prod["id"],
                                                    prod["codigo_clean"])
        return firmas[prod["id"]]

    salida = []
    for x in candidatos:
        pa, pb = productos.get(x["cod_a"]), productos.get(x["cod_b"])
        if not pa or not pb or pa["id"] == pb["id"]:
            continue
        if "OEM" in (pa["tipo"], pb["tipo"]):
            continue
        # Que además las descripciones digan que es la misma pieza. Ver el docstring: la
        # familia sola mete en la misma bolsa cinco sondas distintas del mismo auto.
        ok, _motivo = firmas_compatibles(_firma(pa), _firma(pb),
                                         cuenta_palabras=_cuenta_pal,
                                         total_descripciones=_total_desc)
        if not ok:
            continue
        salida.append({
            "Código A": pa["codigo_raw"], "Marca A": pa["marca"],
            "Código B": pb["codigo_raw"], "Marca B": pb["marca"],
            "Coinciden en": f"{x['autos']} auto(s)",
            "Según": f"{x['marca_a']} y {x['marca_b']}",
            "_a": pa["id"], "_b": pb["id"],
        })
    return salida


def guardar_equivalencias_derivadas(pares, lote):
    """Deja las equivalencias deducidas como PENDIENTES, no cargadas.

    A propósito: por más buena que sea la deducción, sigue siendo una deducción. Pasa por la
    misma revisión que todo lo demás, y ahí el sistema de confianza la evalúa como a cualquier
    otra."""
    # Esta era la única de las dos que ya miraba los rechazos y ordenaba el par. Ahora las dos
    # pasan por el mismo lugar, que además descarta lo que ya está cargado.
    return guardar_equivalencias_pendientes(pares, "catalogos_fabricante", lote)


def buscar_aplicaciones(marca_auto, modelo="", anio=None, limite=200):
    """Los códigos que un catálogo de aplicaciones dice que le van a este auto.

    A diferencia de buscar por la descripción del proveedor, acá el dato lo puso el fabricante
    del repuesto: si NGK dice que a un Fiat Argo 1.3 le va la U5443, le va."""
    condiciones = ["UPPER(marca_auto) LIKE ?"]
    params = [f"%{(marca_auto or '').strip().upper()}%"]
    if modelo:
        condiciones.append("UPPER(modelo_auto) LIKE ?")
        params.append(f"%{modelo.strip().upper()}%")
    if anio:
        # Se descarta solo lo que declara OTRO rango; lo que no aclara años se deja pasar
        condiciones.append("(anio_desde IS NULL OR anio_desde <= ?)")
        params.append(int(anio))
        condiciones.append("(anio_hasta IS NULL OR anio_hasta >= ?)")
        params.append(int(anio))
    c.execute(f"""SELECT a.codigo AS "Código", a.marca_repuesto AS "Marca del repuesto",
                         a.marca_auto AS "Marca auto", a.modelo_auto AS "Modelo",
                         a.motor AS "Motor",
                         COALESCE(a.anio_desde, '') || '-' || COALESCE(a.anio_hasta, '') AS "Años",
                         (SELECT COUNT(*) FROM productos p
                           WHERE p.codigo_clean = a.codigo_clean) AS "En tu catálogo"
                  FROM aplicaciones a
                  WHERE {" AND ".join(condiciones)}
                  ORDER BY a.marca_repuesto, a.modelo_auto LIMIT ?""", params + [limite])
    return filas_a_listas(c)


def repuestos_de_este_auto(marca_auto, modelo="", anio=None, motor="", vin="", limite=500,
                            pieza=""):
    """Los códigos que le corresponden a ESTE auto. Es lo que hace falta en el mostrador: el VIN
    dice qué auto es, pero lo que se vende son códigos.

    IMPORTANTE sobre de dónde sale cada cosa. No existe una tabla pública que diga qué repuesto
    lleva cada auto — eso es una base de aplicaciones licenciada (TecDoc y similares) y se paga.
    Lo que sí hay es información propia del negocio, y se usa en este orden de confianza:

      1. Lo que YA se le puso a ESTE auto (por VIN o patente). Certeza total: alguien lo instaló.
      2. Lo que se le puso a OTROS autos del MISMO modelo. Evidencia real del mostrador.
      3. Lo que dicen las descripciones del catálogo del proveedor ('... FORD FIESTA 1.6 2010/15').
         Es lo más amplio y lo menos seguro: depende de cómo escriba cada proveedor.

    Devuelve un dict con las tres listas por separado, a propósito: mezclarlas escondería que
    una es un hecho y la otra una coincidencia de texto."""
    marca_auto = (marca_auto or "").strip().upper()
    modelo = (modelo or "").strip().upper()
    motor = (motor or "").strip().upper()
    vin = re.sub(r'\s', '', (vin or "").strip().upper())
    resultado = {"de_este_auto": [], "de_otros_iguales": [], "del_catalogo": [],
                 "del_fabricante": [], "modelo_usado": modelo, "sin_datos": True}

    # Fuente nueva y la más confiable de las que no son propias: el catálogo de aplicaciones
    # del fabricante del repuesto. No es una coincidencia de texto, es el fabricante diciendo
    # a qué auto le va su pieza.
    try:
        resultado["del_fabricante"] = buscar_aplicaciones(marca_auto, modelo, anio)
    except sqlite3.OperationalError as _err:
        anotar_error("repuestos_de_este_auto", _err)
        resultado["del_fabricante"] = []

    # --- 1. Lo que ya se le puso a este auto ---
    vehiculo_id = None
    if len(vin) == 17:
        c.execute("SELECT id FROM vehiculos WHERE vin = ?", (vin,))
        f = c.fetchone()
        vehiculo_id = f["id"] if f else None
    if vehiculo_id:
        c.execute("""SELECT h.descripcion_pieza AS "Pieza", h.codigo_pieza AS "Código",
                            h.marca_pieza AS "Marca", h.km_instalacion AS "Km",
                            substr(h.fecha_instalacion, 1, 10) AS "Fecha", h.producto_id AS "_pid"
                     FROM historial_piezas h WHERE h.vehiculo_id = ?
                     ORDER BY h.fecha_instalacion DESC""", (vehiculo_id,))
        resultado["de_este_auto"] = filas_a_listas(c)

    # --- 2. Lo que se le puso a otros autos del mismo modelo ---
    if modelo:
        c.execute("""SELECT h.descripcion_pieza AS "Pieza", h.codigo_pieza AS "Código",
                            h.marca_pieza AS "Marca", COUNT(*) AS "Veces",
                            COUNT(DISTINCT v.id) AS "Autos"
                     FROM historial_piezas h JOIN vehiculos v ON v.id = h.vehiculo_id
                     WHERE UPPER(COALESCE(v.modelo_auto,'')) LIKE ?
                       AND (? = '' OR UPPER(COALESCE(v.marca_auto,'')) LIKE ?)
                       AND (v.id IS NOT ?)
                       AND h.codigo_pieza IS NOT NULL AND h.codigo_pieza <> ''
                     GROUP BY UPPER(h.codigo_pieza)
                     ORDER BY "Autos" DESC, "Veces" DESC LIMIT 100""",
                  (f"%{modelo}%", marca_auto, f"%{marca_auto}%", vehiculo_id))
        resultado["de_otros_iguales"] = filas_a_listas(c)

    # --- 3. El catálogo, por lo que dicen las descripciones ---
    if marca_auto:
        condiciones = ["p.descripcion IS NOT NULL", "UPPER(p.descripcion) LIKE ?"]
        params = [f"%{marca_auto}%"]
        if modelo:
            condiciones.append("UPPER(p.descripcion) LIKE ?")
            params.append(f"%{modelo}%")
        # QUÉ PIEZA, y va en la CONSULTA y no después. Un auto con 1.855 repuestos en el
        # catálogo se lista cortado en los primeros 200, así que filtrar el resultado por
        # «junta de tapa» buscaba adentro de 200 que casi nunca son juntas. Filtrando en la
        # consulta, los 200 que quedan son los de esa pieza.
        for _palabra_pieza in re.split(r'\s+', (pieza or "").strip()):
            # Sin acentos de los dos lados: las listas escriben «INYECCION» y el que pregunta
            # escribe «inyección». normalizar_texto() hace lo mismo que el SQL de al lado.
            _limpia_pieza = normalizar_texto(_palabra_pieza)
            if len(_limpia_pieza) >= 3:
                _cond, _par = like_en_descripcion(f"%{_limpia_pieza}%")
                condiciones.append(_cond)
                params.extend(_par)
        c.execute(f"""SELECT p.id AS "ID", p.codigo_raw AS "Código", p.descripcion AS "Descripcion",
                             m.nombre AS "Marca", p.precio AS "Precio", p.stock AS "Stock"
                      FROM productos p JOIN marcas m ON m.id = p.marca_id
                      WHERE {" AND ".join(condiciones)}
                      LIMIT 4000""", params)
        candidatos = filas_a_listas(c)

        # La cilindrada es lo que más afina ("1.6", "2.0"): si el motor la trae, se usa para
        # filtrar, pero solo descartando lo que declara OTRA cilindrada — lo que no dice nada
        # se deja pasar, porque la mayoría de las listas no la aclaran.
        cilindrada = None
        if motor:
            m_cil = re.search(r'\d[.,]\d', motor)
            cilindrada = m_cil.group(0).replace(",", ".") if m_cil else None

        filtrados = []
        for f in candidatos:
            desc = (f["Descripcion"] or "").upper()
            if anio:
                sirve = sirve_para_anio(f["Descripcion"], int(anio))
                if sirve is False:
                    continue
                f["Año"] = "✅ coincide" if sirve else "— no aclara"
            if cilindrada:
                otras = set(re.findall(r'\d[.,]\d', desc))
                if otras and cilindrada not in {o.replace(",", ".") for o in otras}:
                    continue
                f["Motor"] = "✅ coincide" if cilindrada in desc else "— no aclara"
            f["Categoría"] = clasificar_repuesto(f["Descripcion"])
            filtrados.append(f)

        filtrados.sort(key=lambda x: (x.get("Año") != "✅ coincide",
                                       x.get("Motor") != "✅ coincide",
                                       x["Categoría"]))
        resultado["del_catalogo"] = filtrados[:limite]
        resultado["total_catalogo"] = len(filtrados)

    resultado["sin_datos"] = not (resultado["de_este_auto"] or resultado["de_otros_iguales"]
                                   or resultado["del_catalogo"] or resultado["del_fabricante"])
    return resultado


def panel_vin(clave="vin", mostrar_ensenar=True):
    """La ÚNICA pantalla de VIN de la app. Antes había dos (una en el Buscador y otra en Modo
    Mecánico) que hacían casi lo mismo y ninguna terminaba en lo que hace falta: los códigos.
    Esta identifica el auto y va derecho a qué repuestos lleva."""
    explicar(
        "Pegá el número de chasis y te dice qué repuestos lleva ese auto.",
        "Del VIN salen con certeza el fabricante, el país y el año. El modelo y el motor no "
        "están normalizados: los aprende la app de tus propias fichas, o se los enseñás una "
        "vez."
    )
    vin_txt = st.text_input("VIN / número de chasis (17 caracteres):",
                             placeholder="Ej: 9BWZZZ377VT004251", key=f"{clave}_texto").strip().upper()
    if not vin_txt:
        return None

    d = decodificar_vin(vin_txt)
    if not d["valido"]:
        st.error(d["error"])
        return None

    # --- Qué auto es ---
    fab = d.get("fabricante") or "(fabricante no cargado)"
    if d.get("fabricante_por_prefijo"):
        fab += " (por familia de WMI)"
    linea = f"**{fab}** · {d['pais']}"
    if d.get("anio_estimado"):
        linea += f" · año {d['anio_estimado']}" if d.get("anio_preciso") else f" · año ~{d['anio_estimado']}"
    if d.get("modelo"):
        linea += f" · **{d['modelo']}**"
    if d.get("motor"):
        linea += f" · motor {d['motor']}"
    st.success(linea)

    # Este bloque esperaba un booleano que la app nunca seteaba: el mensaje no salía nunca.
    # Ahora se calcula de verdad, con la cuenta de la norma ISO 3779.
    if d.get("corregido"):
        st.warning(
            "✏️ **Se corrigieron letras que un VIN no puede tener:** "
            + "; ".join(d["corregido"])
            + f". Quedó **{d['vin']}**.\n\nLa norma prohíbe la I, la O y la Q justamente "
              "porque se confunden con 1 y 0, así que la corrección es segura."
        )
    _dv = d.get("digito_verificador")
    if _dv == "mal":
        st.error("❌ " + d.get("mensaje_digito", "") +
                  "\n\nBuscar repuestos con un VIN mal copiado es buscar los del auto equivocado.")
    elif _dv == "ok":
        st.caption("✅ " + d.get("mensaje_digito", ""))
    elif _dv == "no_aplica" and d.get("mensaje_digito"):
        st.caption("ℹ️ " + d["mensaje_digito"])

    # Si el modelo no lo sabemos, se ofrece preguntarle a la base pública de la NHTSA. Es
    # gratis y sin clave. No se consulta sola en cada búsqueda: sería pegarle a un servidor
    # ajeno cada vez que alguien tipea un VIN, y la mayoría ya están resueltos acá.
    if not d.get("modelo"):
        st.caption(
            "El modelo no está en la norma del VIN, así que hay que aprenderlo. Se puede "
            "preguntar a la base pública de la NHTSA (gratis, del gobierno de EE.UU.)."
        )
        if st.button("🌐 Preguntar a la base pública", key=f"nhtsa_{clave}"):
            with st.spinner("Consultando..."):
                _dn, _en = consultar_vin_en_nhtsa(d["vin"])
            st.session_state[f"nhtsa_res_{clave}"] = (_dn, _en)
        _guardado = st.session_state.get(f"nhtsa_res_{clave}")
        if _guardado:
            _dn, _en = _guardado
            if _en:
                st.warning(_en)
            elif _dn:
                st.success(
                    f"🌐 **{_dn['marca']} {_dn['modelo']}** {_dn['anio']}"
                    + (f" · motor {_dn['motor']}" if _dn["motor"] else "")
                    + (f" · {_dn['carroceria']}" if _dn["carroceria"] else "")
                    + (f"\n\nFabricado en {_dn['planta']}." if _dn["planta"] else "")
                )
                st.caption(
                    "Esto viene de una base ajena y **no se guardó**. Si es correcto, "
                    "confirmalo y queda aprendido para todos los VIN de ese patrón."
                )
                if st.button("✅ Es correcto, guardarlo", key=f"nhtsa_ok_{clave}"):
                    _modelo_n = " ".join(x for x in [_dn["marca"], _dn["modelo"]] if x)
                    aprender_modelo_de_vin(d["vin"], _modelo_n, _dn.get("marca") or "",
                                            _dn.get("motor") or "")
                    st.session_state.pop(f"nhtsa_res_{clave}", None)
                    avisar("success", f"Aprendido: ese patrón es un {_modelo_n}.")
                    st.rerun()

    ficha = d.get("vehiculo")
    if ficha:
        st.info(f"🎯 Este chasis ya está en tus fichas: patente **{ficha.get('patente')}**"
                 + (f" — cliente {ficha['cliente_nombre']}" if ficha.get("cliente_nombre") else ""))

    anio_usar = d.get("anio_estimado")
    if d.get("anio_alternativo"):
        # El código de año se repite cada 30. Elegir mal acá filtra los repuestos correctos.
        anio_usar = st.radio(
            "El VIN no permite saber cuál de los dos años es — elegí (miralo en la cédula):",
            sorted({d["anio_estimado"], d["anio_alternativo"]}), horizontal=True,
            key=f"{clave}_anio"
        )

    # --- Lo que importa: los códigos ---
    marca_para_buscar = None
    if d.get("fabricante"):
        marca_para_buscar = next(
            (mv for mv in MARCAS_VEHICULO if mv in d["fabricante"].upper()), None
        )

    if not marca_para_buscar:
        st.warning(
            "No puedo buscar repuestos porque no sé de qué marca es este WMI. "
            "Cargalo abajo en «Enseñar» y la próxima vez sale solo."
        )
    else:
        # OJO con value= junto a key=: Streamlit ignora el value y usa lo que haya en la sesión,
        # que arranca vacío. Por eso el modelo que el VIN reconocía ("Fiesta") aparecía en el
        # cartel verde pero el campo quedaba en blanco, y la búsqueda terminaba trayendo TODOS
        # los repuestos de la marca en vez de los del modelo.
        # Se siembra en session_state, y solo cuando cambia el VIN, para no pisar una corrección.
        clave_modelo = f"{clave}_modelo_manual"
        if st.session_state.get(f"{clave}_vin_previo") != vin_txt:
            st.session_state[clave_modelo] = d.get("modelo") or ""
            st.session_state[f"{clave}_vin_previo"] = vin_txt
        st.session_state.setdefault(clave_modelo, d.get("modelo") or "")

        modelo_manual = st.text_input(
            "Modelo (corregilo si hace falta):", key=clave_modelo,
            help="Se completa solo con lo que reconoce del VIN. Corregilo si no acertó; si lo "
                 "dejás vacío, busca todos los repuestos de la marca."
        ).strip()

        motor_reconocido = d.get("motor") or ""
        if motor_reconocido:
            st.caption(f"⚙️ Filtrando además por motor **{motor_reconocido}** "
                        "(se usa la cilindrada para afinar el catálogo).")

        r = repuestos_de_este_auto(
            marca_para_buscar, modelo_manual, anio_usar, d.get("motor") or "", vin_txt
        )
        _mostrar_repuestos_del_auto(r, marca_para_buscar, modelo_manual, anio_usar, clave)

    if mostrar_ensenar:
        with st.expander("✏️ Enseñarle a la app este auto (para que la próxima salga solo)"):
            _formulario_ensenar_vin(d, clave)
    return d


def _mostrar_repuestos_del_auto(r, marca, modelo, anio, clave):
    """Muestra los códigos separados por fuente. Van separados a propósito: uno es un hecho
    (se lo pusiste a este auto) y el otro es una coincidencia de texto en una descripción.
    Mezclarlos haría parecer que todos valen lo mismo, y no es así."""
    if r["de_este_auto"]:
        st.markdown("#### 🎯 Ya se le puso a ESTE auto")
        st.caption("Certeza total: alguien lo instaló y quedó registrado en la ficha.")
        st.dataframe([{k: v for k, v in f.items() if not k.startswith("_")}
                       for f in r["de_este_auto"]], width="stretch", hide_index=True)

    if r["de_otros_iguales"]:
        st.markdown("#### 🔁 Se le puso a otros autos del mismo modelo")
        st.caption(
            "Evidencia real de tu mostrador: estos códigos se instalaron en autos iguales. "
            "«Autos» es en cuántos distintos — mientras más, más confiable."
        )
        st.dataframe(r["de_otros_iguales"], width="stretch", hide_index=True)

    if r.get("del_fabricante"):
        st.markdown(f"#### 🏭 Según el catálogo del fabricante ({len(r['del_fabricante'])})")
        explicar(
            "Esto no es una coincidencia de texto: es el fabricante del repuesto diciendo a qué "
            "auto le va su pieza.",
            "Es lo más confiable después de lo que ya le pusiste vos. La columna «En tu catálogo» "
            "dice si ese código está cargado en tus listas."
        )
        st.dataframe(r["del_fabricante"], width="stretch", hide_index=True)

    if r["del_catalogo"]:
        total = r.get("total_catalogo", len(r["del_catalogo"]))
        st.markdown(f"#### 📚 Del catálogo, según las descripciones ({total} código(s))")
        st.caption(
            "Sale de que la descripción del proveedor menciona esta marca y modelo. Es lo más "
            "amplio y lo menos seguro: depende de cómo escriba cada proveedor. "
            + (f"Se filtró por año {anio} descartando lo que declara otro rango. " if anio else "")
            + "Confirmá por código antes de vender."
        )
        # Antes acá el filtro listaba el texto crudo previo a la marca en cada descripción, así
        # que con varios proveedores salían cientos de opciones casi iguales ("JUNTA TAPA DE
        # CILINDROS", "JUNTA DE TAPA CIL.", "JUEGO JUNTA TAPA"...) y no servía para encontrar
        # nada. Ahora son ~20 familias fijas, con la cantidad al lado.
        conteo = {}
        for f in r["del_catalogo"]:
            conteo[f["Categoría"]] = conteo.get(f["Categoría"], 0) + 1
        orden_familias = sorted(conteo, key=lambda k: (-conteo[k], k))
        etiquetas = {f"{k} ({conteo[k]})": k for k in orden_familias}

        cf1, cf2 = st.columns([2, 1])
        with cf1:
            elegidas_lbl = st.multiselect("Tipo de pieza:", list(etiquetas.keys()),
                                           key=f"{clave}_cats",
                                           placeholder="Todas — o elegí una o varias")
        with cf2:
            texto_filtro = st.text_input("Buscar en estos resultados:", key=f"{clave}_txt",
                                          placeholder="Ej: delantero, 1.6, kit").strip()

        elegidas = {etiquetas[e] for e in elegidas_lbl}
        filas = [f for f in r["del_catalogo"] if not elegidas or f["Categoría"] in elegidas]
        if texto_filtro:
            # Todas las palabras tienen que estar, sin importar el orden ni los acentos: así
            # "kit delantero" encuentra "Kit de rodamiento delantero" igual.
            palabras = [normalizar_texto(x) for x in texto_filtro.split() if x.strip()]
            filas = [f for f in filas
                     if all(pal in normalizar_texto(f"{f['Código']} {f['Descripcion']}")
                            for pal in palabras)]
        st.caption(f"Mostrando {len(filas)} de {len(r['del_catalogo'])}.")
        st.dataframe(quitar_id(filas), width="stretch", hide_index=True)
        st.download_button(
            "⬇️ Bajar estos códigos en Excel",
            data=to_excel_bytes(quitar_id(filas)),
            file_name=f"repuestos_{marca}_{modelo or 'todos'}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{clave}_dl"
        )
        if total > len(r["del_catalogo"]):
            st.caption(f"(mostrando {len(r['del_catalogo'])} de {total} — afiná el modelo para ver menos)")

    if r["sin_datos"]:
        st.warning(
            f"No encontré repuestos para **{marca} {modelo}**. Puede ser que en tu catálogo las "
            "descripciones lo escriban distinto (probá con otra forma del modelo, o dejá el modelo "
            "vacío para ver todo lo de la marca), o que todavía no tengas cargada esa lista."
        )


def _formulario_ensenar_vin(d, clave):
    """Cargar el modelo y el motor de este patrón, una sola vez."""
    st.caption(
        f"Patrón `{d['wmi']}`-`{d['vds']}` · 8ª posición `{d['codigo_motor']}`. "
        "El modelo se guarda por el patrón; el motor por la 8ª posición, que vale para toda la marca."
    )
    if not d.get("fabricante"):
        cw1, cw2 = st.columns(2)
        nuevo_fab = cw1.text_input("Fabricante de este WMI:", key=f"{clave}_fab")
        nuevo_pais = cw2.text_input("País:", value=d["pais"], key=f"{clave}_pais")
        if st.button("💾 Guardar fabricante", key=f"{clave}_guardar_fab"):
            if nuevo_fab.strip():
                agregar_fabricante_vin(d["wmi"], nuevo_fab, nuevo_pais)
                avisar("success", f"WMI {d['wmi']} guardado.")
                st.rerun()
            else:
                st.warning("Escribí el fabricante.")

    with st.form(f"{clave}_form_ensenar", clear_on_submit=True):
        ce1, ce2 = st.columns(2)
        mod_in = ce1.text_input("Modelo", value=d.get("modelo") or "", placeholder="Ej: FIESTA")
        mot_in = ce2.text_input("Motor", value=d.get("motor") or "", placeholder="Ej: 1.6 16V nafta")
        nota_in = st.text_input("Nota (opcional)", placeholder="Ej: 5 puertas")
        alcance = st.radio("El MODELO, ¿para qué VIN vale?",
                           ["Este patrón exacto (5 caracteres)", "Toda la familia (3 caracteres)"],
                           horizontal=True)
        if st.form_submit_button("💾 Guardar", type="primary"):
            hechos = []
            if mod_in.strip():
                largo = 5 if alcance.startswith("Este") else 3
                enseniar_modelo_vin(d["wmi"], d["vds"][:largo], mod_in, nota_in)
                hechos.append(f"modelo {mod_in.strip()}")
            if mot_in.strip():
                enseniar_motor_vin(d["wmi"], d["codigo_motor"], mot_in, nota_in)
                hechos.append(f"motor {mot_in.strip()}")
            if hechos:
                avisar("success", "Guardado: " + " y ".join(hechos) + ".")
                st.rerun()
            else:
                st.warning("Escribí al menos el modelo o el motor.")


def esquemas_de_vehiculo(marca_vehiculo):
    c.execute("""SELECT id, titulo, marca_auto, modelo_auto, sistema FROM esquemas
                 WHERE UPPER(marca_auto) LIKE ? ORDER BY titulo""", (f"%{marca_vehiculo}%",))
    return [dict(r) for r in c.fetchall()]


# Marcas que se usan para despegar descripciones. Se dejan solo las de 5 letras o más y se
# excluyen las que además son palabras comunes del rubro: separar por "MAN" partiría MANGUERA
# en "MAN GUERA", y por "RAM" partiría RAMAL. Con las largas el riesgo desaparece y son
# justamente las que aparecen pegadas en las listas (VOLKSWAGEN, CHEVROLET, MITSUBISHI...).
_MARCAS_RIESGOSAS = {"BETA", "CASE", "HINO", "SEAT", "LADA", "TATA", "MINI", "HERO", "TVS"}
# Las marcas de REPUESTO se despegan igual que las de auto. Las listas las pegan al código y
# eso se lleva puesto el código: «...MULTIPUNTO BOSCHF1003» daba el código de fábrica
# 'BOSCHF1003', y «MPFIMARELLIF1011» daba 'MPFIMARELLIF1011'. Los dos están cargados en la
# base como si fueran códigos de Bosch y de Marelli.
# MPFI, MPI y TBI no son marcas sino el tipo de inyección, pero se pegan igual y hacen el
# mismo daño, así que van en la misma bolsa.
_SIGLAS_PEGAJOSAS = {"MPFI", "TBI", "SPI", "GDI", "CRDI"}
MARCAS_PARA_DESPEGAR = [m for m in (set(MARCAS_VEHICULO) | MARCAS_DE_REPUESTO | _SIGLAS_PEGAJOSAS)
                        if len(m) >= 4 and m not in _MARCAS_RIESGOSAS and " " not in m]

# Las expresiones se arman UNA vez, al arrancar. Antes se compilaban las 164 de nuevo en cada
# fila: 332 µs por descripción, o sea 3,3 s en una lista de 10.000 filas — diez veces más que
# toda la importación junta.
_RE_PEGADO_MAYUS = re.compile(r'(?<=[a-záéíóúñ])(?=[A-ZÁÉÍÓÚÑ])')
# Se rodea la marca de espacios y después se colapsan los sobrantes. Es más simple y más
# robusto que exigir letra pegada de un lado o del otro: con "DespieceCHEVROLETCAPUCHON" hay
# que separar por IZQUIERDA y por DERECHA a la vez, y una condición sola nunca cubre las dos.
# El orden es de marca más larga a más corta, así "VOLKSWAGEN" gana antes de que pruebe "VW".
_RE_MARCAS_PEGADAS = re.compile(
    "(" + "|".join(re.escape(m) for m in sorted(MARCAS_PARA_DESPEGAR, key=len, reverse=True)) + ")"
) if MARCAS_PARA_DESPEGAR else None
_RE_ESPACIOS = re.compile(r'\s{2,}')

# LA MARCA CORTA PEGADA A UN NÚMERO: «19505VW PASSAT», «314GM Astra», «10127BMW», «FI-IWP041VW».
# MARCAS_PARA_DESPEGAR deja afuera las marcas de menos de cuatro letras a propósito: un «VW» o
# un «GM» sueltos se meten adentro de cualquier palabra y harían un desastre. Pero con un
# DÍGITO justo antes no hay ambigüedad: ninguna palabra del castellano tiene un número pegado
# adelante. Son 1.150 descripciones reales, casi todas de VW (680), GM (193) y BMW (186).
# Y no es solo cosmético: la descripción es de donde sale el código de fábrica, así que
# «FI-IWP041VW Gol» daba el código IWP041VW en vez de IWP041. Hay 5 así cargados en la base.
# Se pide que después de la marca venga algo que NO sea una letra, o una palabra en Mayúscula
# minúscula. Sin esa condición se rompen los errores de tipeo del proveedor —«109103PEUGOET»
# quedaba «109103 PEU GOET» y «LKTCN1007TOYOYA» quedaba «LKTCN1007 TOY OYA»—, que son 32.
_MARCAS_CORTAS_PEGADAS = sorted(
    [m for m in MARCAS_VEHICULO if 2 <= len(m) <= 3 and " " not in m], key=len, reverse=True)
_RE_MARCA_CORTA_TRAS_NUMERO = re.compile(
    r'(?<=\d)(' + "|".join(re.escape(m) for m in _MARCAS_CORTAS_PEGADAS)
    + r')(?=[^A-Za-zÁÉÍÓÚÑ]|[A-ZÁÉÍÓÚÑ][a-záéíóúñ])'
) if _MARCAS_CORTAS_PEGADAS else None

# EL MODELO CON LA CILINDRADA PEGADA: «CORSA1.4», «AMAROK2.0», «HILLUX2.4», «Siena1.0».
# Sale de la exportación del proveedor, que se come el espacio, y hace daño de dos maneras: el
# modelo deja de ser reconocible como modelo, y —peor— «CORSA1.4» tiene forma de código, así
# que se cargaba como código de fábrica. En la base real ese código llegó a colgar un tubo, una
# correa multicanal y un sensor MAP: tres repuestos que no tienen nada que ver, hermanados
# porque las tres descripciones nombran el mismo auto.
# Se piden CUATRO letras antes del número, y ahí está todo el cuidado: con menos se rompían las
# designaciones de zócalo y las medidas, que son iguales pero con una o dos letras —«W2x4.6d»,
# «BX8.2d», «SV8,5-8», «M14X1.5X42», «6mmx8mm x7,89mm»—. Medido sobre las 53.255 descripciones
# reales: separa 158 y no toca ninguna de esas.
_RE_MODELO_CON_CILINDRADA = re.compile(r'(?<=[A-Za-zÁÉÍÓÚÑáéíóúñ]{4})(?=\d[.,]\d)')


# «REF» de «REF. ORIG.» pegado a lo que viene antes. Es la forma de escribir de una de las
# listas y aparece 9.038 veces: «Passat 1 8 98REF ORIG 030121121B», «16VREF ORIG 0280155868».
# Hace daño dos veces:
#   · «98REF», «16VREF», «HDIREF», «PARTNERREF» se cuentan como si fueran modelos de auto y
#     ensucian el desplegable de la pantalla de vehículos;
#   · y sobre todo tapa el marcador: «REF ORIG» es el proveedor diciendo EXPLÍCITAMENTE cuál
#     es el código de fábrica, que es la mejor información que puede llegar. Pegado, el
#     marcador no se reconoce y el código que le sigue queda como una adivinanza más.
# Se pide que después venga ORIG/ORG/ORI/OEM para no partir un código que termine en REF por
# casualidad. Medido sobre las descripciones reales: de 9.038 casos, los 9.038 siguen esa
# forma, así que la condición no deja nada afuera y sí evita el accidente.
_RE_REF_PEGADO = re.compile(r'([A-Za-z0-9])REF(?=\s*\.?\s*(?:ORIG|ORG|ORI|OEM)\b)', re.I)


@functools.lru_cache(maxsize=MAXIMO_DESCRIPCIONES_RECORDADAS)
def _separar_texto_pegado_cacheado(texto):
    return _separar_texto_pegado(texto)


def separar_texto_pegado(texto):
    """Separa las columnas que la exportación pegó. Ver _separar_texto_pegado().

    Esta capa existe solo para el caché: lru_cache necesita un argumento hashable y acá llegan
    cosas que no lo son —None, y los valores que devuelve openpyxl al leer una celda—."""
    if not texto:
        return texto
    if isinstance(texto, str):
        return _separar_texto_pegado_cacheado(texto)
    return _separar_texto_pegado(texto)


def _separar_texto_pegado(texto):
    """Algunas listas de proveedor exportan varias columnas pegadas sin espacio en el medio:
    'Junta Tapa de CilindrosFORDTAUNUS COUPE' o 'PASTILLAS FRENOVOLKSWAGENGOL'.
    Esto las vuelve legibles separando en dos puntos:
      1) donde una minúscula toca una MAYÚSCULA (ahí se pegaron dos campos), y
      2) donde una marca de vehículo quedó pegada a la descripción.

    El punto 2 antes solo funcionaba si la descripción tenía minúsculas: pedía que el carácter
    anterior a la marca NO fuera mayúscula, así que en una lista escrita toda en mayúsculas
    —que son la mayoría— no separaba nada.

    Y dos puntos más: «REF» pegado al final de la palabra anterior cuando después viene ORIG
    (ver _RE_REF_PEGADO), y el modelo con la cilindrada pegada, «CORSA1.4»
    (ver _RE_MODELO_CON_CILINDRADA)."""
    if not texto:
        return texto
    t = str(texto).strip()
    t = _RE_REF_PEGADO.sub(r'\1 REF ', t)
    t = _RE_PEGADO_MAYUS.sub(' ', t)
    t = _RE_MODELO_CON_CILINDRADA.sub(' ', t)
    if _RE_MARCAS_PEGADAS is not None:
        t = _RE_MARCAS_PEGADAS.sub(r' \1 ', t)
    if _RE_MARCA_CORTA_TRAS_NUMERO is not None:
        t = _RE_MARCA_CORTA_TRAS_NUMERO.sub(r' \1 ', t)
    return _RE_ESPACIOS.sub(' ', t).strip()


@st.cache_data(show_spinner=False, max_entries=3)
def _contar_descripciones_pegadas(version):   # ver descripciones_por_palabra()
    c.execute("SELECT descripcion FROM productos WHERE descripcion IS NOT NULL")
    return sum(1 for r in c.fetchall()
               if separar_texto_pegado(r["descripcion"]) != r["descripcion"])


def contar_descripciones_pegadas():
    """Cuántas descripciones del catálogo están pegadas. TODAS, no una muestra.

    Antes miraba las primeras 3.000 filas y mostraba ese número. Sobre el catálogo real eso
    decía «al menos 1.682» cuando son 9.324 — y, peor, si en esas 3.000 no había ninguna la
    pantalla afirmaba «✅ Ninguna descripción con ese problema» con 50.000 filas sin mirar.
    Recorrer las 53.255 tarda 1,4 s y queda cacheado hasta que cambia el catálogo: el número
    exacto vale mucho más que el segundo que cuesta, porque de él depende que alguien decida
    correr el arreglo o no."""
    return _contar_descripciones_pegadas(version_del_catalogo())


def reparar_descripciones_pegadas():
    c.execute("SELECT id, descripcion FROM productos WHERE descripcion IS NOT NULL")
    # Se separa UNA vez por fila y se compara con el resultado guardado. Antes se llamaba dos
    # veces —una en la condición y otra en el valor— y son 53.255 filas: la mitad del trabajo
    # era tirarlo a la basura.
    cambios = []
    for fila in c.fetchall():
        nueva = separar_texto_pegado(fila["descripcion"])
        if nueva != fila["descripcion"]:
            cambios.append((nueva, fila["id"]))
    with db_lock:
        c.executemany("UPDATE productos SET descripcion = ? WHERE id = ?", cambios)
        conn.commit()
    return len(cambios)


def buscar_por_texto(texto):
    """Busca por descripción de forma flexible: cada palabra tiene que aparecer en algún lado
    (descripción o código), sin importar el orden ni las tildes. Así 'ruleman delantero gol'
    encuentra 'Gol 1.6 - Ruleman de rueda delantero', y 'rótula' encuentra 'ROTULA' aunque el
    catálogo la tenga cargada sin tilde (frecuente en listas de proveedores)."""
    palabras = [normalizar_texto(p.strip()) for p in texto.upper().split() if p.strip()]
    if not palabras:
        return []
    # Compara contra la columna 'busqueda', que ya tiene la descripción y el código en
    # mayúscula y sin acentos (la mantienen dos triggers, ver init_db). Antes se le sacaban los
    # acentos a cada fila acá mismo, con doce REPLACE() anidados por columna y por palabra:
    # 981 ms por búsqueda sobre 44.000 productos, y más de tres segundos sobre 110.000. Con la
    # columna guardada la misma búsqueda tarda 40 ms.
    # En vez de exigir que estén TODAS las palabras, se cuenta cuántas coinciden y se ordena
    # por eso. Así "junta tapa cilindro ford taunus" igual encuentra la que dice
    # "Junta Tapa de Cilindros FORD TAUNUS COUPE" aunque no diga exactamente lo mismo, y las
    # que más se parecen quedan arriba. Antes, si fallaba una sola palabra, no aparecía nada.
    puntajes = []
    params = []
    for palabra in palabras:
        # También se compara contra el código sin guiones ni espacios: si alguien escribe
        # "TC421" o "tc-421", tiene que encontrar igual el producto cargado como "TC-421-15".
        # ESCAPE: sin esto, escribir «100%» o «f_ltro» devolvía 200 filas cualesquiera,
        # porque SQLite tomaba el % y el _ como comodines. Ver como_texto_en_like().
        ramas, suyos = [], []
        limpia = sanitizar(palabra)
        for columna, valor in (("p.busqueda", palabra), ("p.codigo_clean", limpia)):
            # Un LIKE '%%' coincide con TODO. Pasaba al buscar «%» o «_»: sanitizar() los deja
            # en nada, el patrón quedaba vacío y la búsqueda devolvía el catálogo entero.
            if not valor:
                continue
            ramas.append(f"{columna} LIKE ? ESCAPE '\\'")
            suyos.append(f"%{como_texto_en_like(valor)}%")
        if not ramas:
            continue        # la palabra era solo símbolos: no aporta nada para buscar
        puntajes.append("(CASE WHEN " + " OR ".join(ramas) + " THEN 1 ELSE 0 END)")
        params.extend(suyos)
    if not puntajes:
        return []
    suma = " + ".join(puntajes)

    # Con una o dos palabras se piden todas (si no, aparece cualquier cosa). Con tres o más
    # alcanza con que coincida la mayoría: es lo que permite "interpretar" y no fallar por una.
    utiles = len(puntajes)
    minimo = utiles if utiles <= 2 else max(2, (utiles * 2) // 3)

    _fabricante = campo_opcional_de_producto(c, "marca_repuesto", "Fabricante")
    query = f'''
    SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
           m.nombre AS "Marca", m.tipo AS "Tipo",
           -- Quién FABRICA la pieza, que es otra cosa que la lista de quién te la vende. En el
           -- mostrador, entre cinco equivalentes, la pregunta es «¿cuál es el Bosch?».
           -- Ver marca_de_repuesto_en(): sale del final de la descripción, 13.705 productos.
           -- Va por campo_opcional_de_producto() y no directo: contra una base que todavía no
           -- tiene la columna, nombrarla acá tumba el buscador entero.
           {_fabricante},
           p.precio AS "Precio", p.stock AS "Stock",
           p.favorito AS "Favorito", ({suma}) AS _coincidencias
    FROM productos p JOIN marcas m ON m.id = p.marca_id
    WHERE ({suma}) >= ?
    ORDER BY _coincidencias DESC, LENGTH(p.descripcion), m.nombre LIMIT 200;
    '''
    with db_lock:
        c.execute(query, params + params + [minimo])
        filas = filas_a_listas(c)
        # Si pidiendo TODAS las palabras no aparece nada, se afloja y se pide una menos.
        # Con dos palabras se exigían las dos, y «rótula suspensión» devolvía CERO resultados
        # sobre un catálogo lleno de rótulas: ninguna descripción dice las dos cosas juntas.
        # Cero resultados es la peor respuesta posible —el de adelante concluye que no hay, y
        # hay— así que es mejor mostrar lo que coincide en parte y que decida la persona.
        if not filas and len(palabras) >= 2:
            c.execute(query, params + params + [minimo - 1])
            filas = filas_a_listas(c)

    # Filtro por RUBRO. Contar palabras coincidentes no alcanza: buscando «bujía golf 1.4 tsi»
    # aparecían juntas de tapa y juegos de motor, porque coinciden en «golf», «1.4» y «tsi» —
    # o sea, en el AUTO, no en la pieza. Y el auto es lo de menos: nadie que pide una bujía se
    # lleva una junta porque va al mismo Golf.
    #
    # Si en el pedido se reconoce un rubro, se dejan solo los resultados de ESE rubro. Los que
    # no se pudieron clasificar se conservan: descartar lo que no se entiende es peor que
    # mostrarlo, porque las descripciones de proveedor son un desastre y muchas piezas legítimas
    # no caen en ninguna familia.
    familia_pedida = clasificar_repuesto(texto)
    if familia_pedida != "Sin clasificar":
        del_rubro, sin_clasificar, de_otro_rubro = [], [], []
        for f in filas:
            fam = clasificar_repuesto(f.get("Descripcion") or "")
            if fam == familia_pedida:
                del_rubro.append(f)
            elif fam == "Sin clasificar":
                sin_clasificar.append(f)
            else:
                de_otro_rubro.append(f)
        # Solo se descarta lo de otro rubro si quedó algo del rubro pedido; si no, es mejor
        # mostrar todo que dejar la pantalla vacía.
        if del_rubro:
            filas = del_rubro + sin_clasificar

    for f in filas:
        f.pop("_coincidencias", None)
    return filas

"""La ficha de cada pieza (firma_de_producto) y la comparación entre dos (firmas_compatibles).

Salió de logica/descripciones.py, que con 5.400 renglones juntaba cinco temas.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================================================
# LA FICHA DE CADA PIEZA Y LA COMPARACIÓN ENTRE DOS
# ============================================================================================
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


# CABLES, TERMINALES y SALIDAS son lo mismo dicho por otras listas: «SONDA LAMBDA ... 4 CABLES»,
# «Sensor de rotación ... 3 terminales», «Bulbo electroventilador ... 4 salidas».
# EL LARGO DEL CABLE DE UNA SONDA. CRI-FA escribe «Largo cable 28 centimetros», «Largo del cable
# 63 cm»; FISPA «Cable de 48cm», «LARGO DEL CABLE 530mm». Dos sondas del mismo auto con cables
# de 28 y 48 cm son dos sondas distintas —antes y después del catalizador, o de otro motor—.
_RE_LARGO_DE_CABLE = re.compile(
    r'(?:LARGO\s+(?:DEL\s+)?CABLE|CABLE\s+DE)\s*:?\s*(\d{2,4})\s*(CM|CENTIMETROS?|MM)\b',
    re.IGNORECASE)
# LAS TEMPERATURAS DE UN BULBO: «92º/82º», «temp. 102/97», «95º/100º-76º/86º»; FISPA «Temp 86?
# 76?» (el signo de grado llega roto). Un bulbo de electroventilador de 92/82 no reemplaza a uno
# de 102/97 aunque vaya en el mismo auto: el ventilador arrancaría a otra temperatura.
_RE_PAR_DE_TEMPERATURAS = re.compile(
    r'(?<![\d.,])(\d{2,3})\s*[º°?]?\s*[/\- ]\s*(\d{2,3})\s*[º°?]?(?![\d.,])')
_RE_HABLA_DE_TEMPERATURA = re.compile(r'\b(BULBO|TERMO|TERMOSTATO|TEMP|ELECTROVENT)', re.I)


# La presión en bar, como la escribe cada lista: «0.40 BAR», «1.40 Bar», «3BAR», y FISPA con el
# espacio en lugar de la coma: «PRESION 0 5 BAR», «3 5 BAR». No se toma si viene pegado a una
# letra o a otro número («M3 3BAR» es el BMW M3 y 3 bar), ni el final de un rango: «0-7 BAR»
# es lo que mide un sensor continuo, no la presión a la que abre (los rangos arrancan en 0).
_RE_PRESION_EN_BAR = re.compile(
    r"(?<![\w.,])(?<!\b0-)(?<!\b0\s-)(?<!\b0-\s)(?<!\b0\s-\s)(\d{1,2}(?:[.,]\d{1,2}|\s\d{1,2})?)"
    r"\s?-?\s?BAR\b", re.IGNORECASE)


def presiones_en_bar(descripcion):
    """Las presiones que declara la descripción, en bar: {0.4}, {3.5}. Vacío si no dice."""
    return frozenset(float(re.sub(r"[\s,]", ".", x)) for x in
                     _RE_PRESION_EN_BAR.findall(descripcion or ""))


def presiones_que_chocan(bar_a, bar_b):
    """Las dos dicen la presión y ninguna coincide (con 0,05 bar de tolerancia)."""
    return bool(bar_a and bar_b) and not any(abs(x - y) <= 0.05 for x in bar_a for y in bar_b)


def largo_de_cable_mm(descripcion):
    """El largo del cable que declara la descripción, en milímetros, o None."""
    m = _RE_LARGO_DE_CABLE.search(descripcion or "")
    if not m:
        return None
    valor = int(m.group(1))
    return valor if m.group(2).upper() == "MM" else valor * 10


def temperaturas_declaradas(descripcion):
    """Las temperaturas de trabajo que declara un bulbo o un termostato, o un conjunto vacío.
    Solo pares de 70 a 125 grados, y solo si la descripción habla de un bulbo o temperatura:
    «1 6 16V» o «2 0 - 2 2» no son temperaturas."""
    texto = descripcion or ""
    if not _RE_HABLA_DE_TEMPERATURA.search(texto) or not re.search(r"[º°?]|TEMP", texto, re.I):
        return set()
    salida = set()
    for x, y in _RE_PAR_DE_TEMPERATURAS.findall(texto):
        if 70 <= int(x) <= 125 and 70 <= int(y) <= 125:
            salida.update((int(x), int(y)))
    return salida


_RE_CANTIDAD_VIAS = re.compile(
    r'\b(\d{1,2})\s*(?:VIAS?|V[IÍ]AS?|PIN|PINES|BOCAS?|POLOS?|CONTACTOS?|CABLES|TERMINALES'
    r'|SALIDAS)\b', re.IGNORECASE)


# «8V», «16V», «16 VALV.»: las válvulas del motor. Ver el control de firmas_compatibles().
_RE_CANTIDAD_DE_VALVULAS = re.compile(r"(?<![\d.,])(8|12|16|20|24|32)\s?V(?:ALV\w*)?\b")

# Los Ford S-MAX, C-MAX y B-MAX. Partidos por el guion quedaba un MAX suelto, y «Jta.Tapa Cil.
# FORD MAX ECONO» de Taranto concordaba con la junta de un S-MAX 2.3 Duratec de Illinois.
_RE_MODELO_CON_LETRA_Y_MAX = re.compile(r"\b([BCS])[\s-]?MAX\b")


def firma_de_producto(descripcion, producto_id=None, codigo_clean=None):
    """Ver _firma_de_producto(). Durante un análisis se calcula una vez por producto: la lista
    del barrido son 8.648 pares hechos con 4.399 productos, y se calculaba 17.296 veces —4,5 s
    de los 7,8 que tardaba el análisis—. Ver recordando_lo_de_cada_producto().

    La MISMA firma se devuelve a todos los que la piden, sin copiar: nadie la modifica después
    de armada —se revisó cada llamada—. Si alguna vez hace falta cambiarle algo, copiarla antes."""
    return _recordado(("firma", descripcion, producto_id, codigo_clean),
                      lambda: _firma_de_producto(descripcion, producto_id, codigo_clean))


# Las que se usan palabra por palabra en _firma_armada(), compiladas una vez: escritas en el
# bucle, cada palabra pasaba por la caché de expresiones de re —3 millones de consultas para
# analizar la lista de FISPA—.
_RE_1_O_2_DIGITOS = re.compile(r'\d{1,2}')
_RE_2_A_4_DIGITOS = re.compile(r'\d{2,4}')
# El modelo o el motor que es un número, con la versión pegada: «14000», «1006.6C/T/TW»,
# «6081H/T». Ver es_modelo_numerico en firma_de_producto().
_RE_MODELO_NUMERICO = re.compile(r'(\d{2,5}(?:\.\d)?)((?:[A-Z]{1,2})(?:/[A-Z]{1,2})*)?')
_RE_NUMERO_DE_MODELO = re.compile(r'\d{2,5}(?:\.\d)?')
_SUFIJOS_QUE_NO_SON_VERSION = {"V", "CC", "L", "LT", "MM", "CM", "KG", "HP", "CV", "KW", "I",
                               "MI", "M", "GR", "X", "RPM"}
_RE_UN_ANIO = re.compile(r'(19|20)\d{2}')
_RE_SOLO_NUMERO = re.compile(r'[\d./,]+')


def _firma_de_producto(descripcion, producto_id=None, codigo_clean=None):
    """La firma del texto (ver _firma_armada()) más los autos que la base sabe de ese producto.

    LO QUE SALE DEL TEXTO SE GUARDA, POR TEXTO. Leer una descripción son 0,7 ms, y analizar la
    lista de FISPA las leía 16.000 veces: 10,6 de sus 14 segundos. La mitad eran repetidas —el
    código de fábrica copia la descripción del producto que lo nombró— y además cada decisión
    en la pantalla de revisión rehace el análisis entero, y volvía a leer todo. Lo que depende
    del texto no cambia mientras la app corre, así que se lee una vez por proceso. Los autos
    guardados en la base sí pueden cambiar, y se siguen preguntando cada vez (dentro de un
    análisis, una vez por producto: ver _recordado()).
    La firma que se devuelve es compartida: nadie la modifica. Si cambian los autos, se
    devuelve una copia con los autos nuevos."""
    base = (_firma_del_texto(descripcion) if isinstance(descripcion, str)
            else _firma_armada(descripcion))
    if not base or not (producto_id or codigo_clean):
        return base
    autos = autos_de_todas_las_fuentes(producto_id, codigo_clean, base["autos"])
    # El código del propio producto puede tener forma de motor (KIT20003A): no es un motor.
    motores = base.get("motores") or frozenset()
    if codigo_clean and motores:
        propio = sanitizar(codigo_clean)
        motores = frozenset(m for m in motores if m not in propio)
    if autos == base["autos"] and motores == (base.get("motores") or frozenset()):
        return base
    return dict(base, autos=autos, motores=motores)


@functools.lru_cache(maxsize=20000)
def _firma_del_texto(descripcion):
    return _firma_armada(descripcion)


# SALIDAS DE REVISAR A MANO LOS AMARILLOS DEL BARRIDO. Cada una es un dato que las dos listas
# escriben y que distingue dos piezas que el resto del texto hacía parecer la misma.
_RE_CARBURADOR_CARTER = re.compile(r"\bCARTER\s+(YF|YH|RBS|WCD|BBD|AFB|WGD|WO|WA1)\b")
_MODELOS_DE_SOLEX = {"TEIE", "PAIA", "EISA", "PIBT", "PICT"}
# La bobina con el módulo de encendido incorporado no es la de sin módulo: «BOBINA IGNICION, VW
# POLO/ GOLF / PASSAT CON MODULO» (TARANTO) contra «BOBINA … VW POLO-GOLF-PASSAT Sin Modulo».
_RE_CON_MODULO = re.compile(r"\b(?:CON|C/)\s*MODULO\b")
_RE_SIN_MODULO = re.compile(r"\b(?:SIN|S/)\s*MODULO\b")
# El sensor de la temperatura del aire de afuera (el del tablero) no es el del agua del motor:
# «SENSOR TEMP EXTERIOR VW BORA/GOLF… Masser» (JL) concordaba con «Sensor de temperatura
# Volkswagen Fox Suran … 2 salidas» (CRI-FA).
_RE_AIRE_EXTERIOR = re.compile(r"\b(?:TEMP\w*\s+(?:DE\s+)?(?:AIRE\s+)?EXTERIOR|AMBIENTE)\b")
# El aro de color de los inyectores y de los sensores de temperatura: «Inyector … Magneti
# Marelli aro gris» (CRI-FA) contra «INYECTOR LEICJ051 … ARO VERDE … IWP 042» (FISPA), «Sensor
# temperatura inyección VW Gol … Aro rojo» contra «… aro amarillo Masser» (JL). El color es
# cómo los distinguen las propias listas.
_RE_ARO_DE_COLOR = re.compile(
    r"\bARO\s+(GRIS|VERDE|NEGRO|AZUL|ROJO|MARRON|BLANCO|AMARILLO|NARANJA|VIOLETA|CELESTE|BEIGE)\b")
# Los espárragos de la junta del turbo: «SALIDA TURBO (ESPÁRRAGOS 10MM)» contra «(… 8MM)».
_RE_ESPARRAGOS_MM = re.compile(r"\bESPARRAGOS?\s*(\d{1,2})\s*MM\b")
# El diámetro del cilindro en una junta de tapa: «JOHN DEERE 3530 … 6329D (119MM)» contra la
# del 3420 «303 (115MM)». Entre paréntesis y sin «ESP» adelante, que es el espesor.
_RE_DIAMETRO_DE_LA_JUNTA = re.compile(r"\((\d{2,3})(?:[.,]\d+)?\s?MM\)")


_RE_PARTE_DEL_CARBURADOR = re.compile(
    r"(?<!C/)(?<!CON )(?<!SIN )\b(BASE|BSE|CUBA|PLACA|INT|INTE|INTERMEDIA)\b")
_PARTE_DEL_CARBURADOR = {"BSE": "BASE", "INT": "INTERMEDIA", "INTE": "INTERMEDIA"}


def _partes_del_carburador(texto):
    """BASE, CUBA, PLACA o INTERMEDIA: de qué parte del carburador es una junta suelta
    («JTA BSE CARB. WEBER FIAT 133», «JTA INT CARB WEBER 2 B RENAULT» de IMPERIAL)."""
    return {_PARTE_DEL_CARBURADOR.get(p, p) for p in _RE_PARTE_DEL_CARBURADOR.findall(texto)}


def _es_juego_de_carburador(firma):
    """El juego de juntas del carburador: «Juego de juntas para Carburador …» (ILLINOIS),
    «Jgo.Jtas.Carburador» (TARANTO), «JUNTAS SIERRA 1.6 WEBER» (JL, en plural y sin decir juego)."""
    return bool(firma.get("kit") or re.match(r"(?:JUNTAS|JUEGO|JGO)\b", firma.get("texto") or ""))


# Los Cummins se nombran por la cilindrada y cada una es de una cantidad de cilindros: la serie
# B de 3.9 y el QSB 4.5 son de 4, la de 5.9, el ISB 6.7 y la serie C de 8.3 son de 6. «Junta
# para Cárter CUMMINS ELECTRÓNICO - 3,9 - ISBE» concordaba en verde con «JTA CARTER CUMMINS 6
# CIL ISBe» porque ninguna de las dos decía los cilindros de la misma forma.
_CILINDROS_DE_CUMMINS = {"3.9": "4", "4.5": "4", "5.9": "6", "6.7": "6", "8.3": "6"}


def _cilindros_de_cummins(texto, cilindradas):
    if "CUMMINS" not in texto:
        return []
    return [_CILINDROS_DE_CUMMINS[c] for c in cilindradas if c in _CILINDROS_DE_CUMMINS]


def _familia_de_motor_ford(texto):
    """SIGMA, ROCAM, CHT o ENDURA, si la descripción nombra una sola. «Termostato Ford Fiesta
    Focus Ecosport 1.6 Sigma» no es el del «FIESTA 1 6 8V ROCAM FLEX»: son dos motores."""
    familias = set()
    if re.search(r"\bSIGMA\b|\bZETEC\s+SE\b", texto):
        familias.add("SIGMA")
    if re.search(r"\bROCAM\b", texto):
        familias.add("ROCAM")
    if re.search(r"\bCHT\b", texto):
        familias.add("CHT")
    if re.search(r"\bENDURA\b", texto):
        familias.add("ENDURA")
    return next(iter(familias)) if len(familias) == 1 else None


def _termostato_con_carcasa(texto):
    """True si es el termostato con su carcasa, False si es solo el termostato, None si no dice.
    «Termostato para carcaza Volkswagen Up Fox» (CRI-FA) es el termostato solo; «TERMOSTATO
    COMPLETO … VERNET THK727411» (FISPA) viene con la carcasa."""
    if "TERMOSTATO" not in texto:
        return None
    if re.search(r"\b(?:PARA|SIN)\s+(?:LA\s+)?CARCA[SZ]A\b", texto):
        return False
    if re.search(r"\bTERMOSTATO\s+COMPLETO\b|\b(?:CON|C/)\s*CARCA[SZ]A\b", texto):
        return True
    return None


def _firma_armada(descripcion, producto_id=None, codigo_clean=None):
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
    limpio = _expandir_abreviaturas_con_punto(limpio)
    limpio = _RE_PUNTO_ENTRE_LETRAS.sub(r"\1 \2", limpio)
    # «JUNTAS JEEP IKA CARTER YF» y «JUNTAS RAMBLER TORINO CARTER RBS» (JL) son del carburador
    # Carter —YF y RBS son sus modelos—, no del cárter, y concordaban con la junta de cárter del
    # Jeep y del Torino.
    limpio = _RE_CARBURADOR_CARTER.sub(r"CARBURADOR \1", limpio)
    limpio = _RE_COMA_DECIMAL.sub(".", limpio)   # ver _RE_COMA_DECIMAL
    # El largo del cable ya se lee aparte (ver largo_de_cable_mm()); como palabras, «LARGO» y
    # «CABLE» hacían concordar a cualquier sonda de CRI-FA con cualquiera de FISPA: una de
    # Honda Fit «coincidía en LAMBDA, LARGO, SONDA, CABLE» con una de Ford Zetec.
    limpio = _RE_LARGO_DE_CABLE.sub(" ", limpio)
    limpio = _RE_MODELO_CON_LETRA_Y_MAX.sub(r"\1MAX", limpio)
    # «4 CIL.» es la cantidad de cilindros (se lee aparte, ver "cilindros"), no la tapa de
    # cilindros: «Junta Tapa de Válvulas M.W.M. CHEV S10 TURBO 4 CIL.» quedaba como junta de
    # tapa de CILINDROS y concordaba con la de la tapa de cilindros del mismo motor.
    palabras = [w for w in re.split(r"[^A-Z0-9./]+", _RE_CANTIDAD_DE_CILINDROS.sub(" ", limpio))
                if w]

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
    # Sin el ESPESOR: «Jta.Tapa Cil. FIAT DAILY/DUCATO ESP 1.6MM» no es un 1.6, y concordaba con
    # las juntas del Palio 1.6.
    cilindradas = set(re.findall(r'\b(\d[.,]\d)(?!\d)(?!\s?MM\b)', limpio))
    # Y en centímetros cúbicos, que es como escribe TARANTO: «Hilux 2779cc» es el 2.8, «1587CC»
    # el 1.6. Sin pasarlo a litros, la junta de la Hilux 2,8 no encontraba a su par por la
    # cilindrada y el abanico elegía otra (ver _analizar_lote_pendiente()).
    for _cc in re.findall(r'\b(\d{3,4})\s*CC\b', limpio):
        if 600 <= int(_cc) <= 9999:
            cilindradas.add(f"{int(_cc) / 1000:.1f}")
    # Y sin CC pero con el combustible atrás, como escribe IMPERIAL: «HILUX 2200 D.», «GACEL 1600
    # DIESEL», «FIAT 1300 D». Hasta 3900: «FORD TRACTOR 4600/6600 DIESEL» son modelos.
    for _cc in re.findall(r'\b([1-3]\d00)\s?(?:D|TD|TDI|DIESEL)\b', limpio):
        cilindradas.add(f"{int(_cc) / 1000:.1f}")
    # Y en litros: «JEEP CHEROKEE 4 l», «2.0 lts», «2,5 L». «Jta.Tapa Cil. JEEP CHEROKEE 4 l» —el
    # seis en línea de 4 litros— concordaba con la del Cherokee 2013 de 2,4. No pegado a una
    # letra (F4L es un Deutz de 4 cilindros) ni a otro número («120L H» son litros por hora), ni
    # detrás de otro número con espacio: «1 6L» es el 1,6 de FISPA. Y sin decimal, solo
    # separado: «HILUX 2L» es el motor 2L de Toyota, no dos litros.
    for _ent, _dec in re.findall(r'(?<![\w.,])(?<!\d\s)(\d)(?:[.,](\d)\s?L|\s(?:L|LTS?|LITROS?)'
                                 r'|(?:LTS?|LITROS?))\b', limpio):
        cilindradas.add(f"{_ent}.{_dec or 0}")
    # Y sin punto, como escribe FISPA: su lista llega sin ningún signo, y «FOCUS 2 0 DURATEC»
    # o «ASTRA 1 8 - CELTA 1 4» son el 2.0, el 1.8 y el 1.4. Sin leerlas, «Sensor MAP Ford
    # Focus 1.8» no se podía separar del sensor del Focus 2.0 y quedaban empatados. Solo en las
    # descripciones que no traen NINGÚN número con punto o coma —las de esa lista—, y no
    # después de una «X» suelta: «M 12 x 1 5» es una rosca (y «HILUX 2 5 3 0» no: la X era la
    # de HILUX, y se leía 5,3). Con la L o la T pegadas también: «ASTRA 1 8L», «BORA 1 8T».
    if not cilindradas and not re.search(r'\d[.,]\d', limpio):
        cilindradas.update(f"{a}.{b}" for a, b in
                           re.findall(r'(?<!\bX )\b([0-6]) (\d)[LT]?\b(?! ?(?:MM|X)\b)', limpio))

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
    # LOS MODELOS CON NÚMERO ESCRITOS CON BARRA: «J.DEERE 2420/2730», «FORD 350/351», «FIAT
    # 1500/1600». La barra dejaba todo como una sola palabra y no era ni un número ni un modelo,
    # así que «Jgo.Jtas.Caja JHON DEERE 4220-2530» contra «JTA T.C. J.DEERE 2420/2730» no tenía
    # modelos que comparar. Cada número de la barra cuenta como si viniera después de la marca.
    # Y la marca con punto —«J.DEERE», «M.BENZ»— cuenta como la marca.
    def _es_de_marca(tok):
        return tok in palabras_marca or any(len(p) >= 3 and p in palabras_marca
                                            for p in tok.split("."))
    anterior = {}
    _con_barra = []
    for _i, _w in enumerate(palabras):
        _partes = _w.split("/")
        if len(_partes) > 1 and all(_RE_2_A_4_DIGITOS.fullmatch(x) for x in _partes):
            for _x in _partes:
                anterior[len(_con_barra)] = palabras[_i - 1] if _i else ""
                _con_barra.append(_x)
        else:
            anterior[len(_con_barra)] = palabras[_i - 1] if _i else ""
            _con_barra.append(_w)
    palabras = _con_barra
    for indice, w in enumerate(palabras):
        # «4 y 6 CIL» es la CANTIDAD de cilindros del motor, no la pieza. Sin esto, «Juego de
        # juntas para Caja de Velocidad PEUGEOT 504 INDENOR DIESEL 4 y 6 CIL» entraba al
        # núcleo con la palabra CILINDRO y salía equivalente a una junta de tapa de cilindros.
        # Se reconoce por lo que tiene adelante: un número suelto.
        if (w in ("CIL", "CILS", "CILINDROS", "CILINDRO") and indice
                and _RE_1_O_2_DIGITOS.fullmatch(palabras[indice - 1])):
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
        # También los de camión y los motores: «FORD 14000», «PERKINS 1006.6C/T/TW», «J.DEERE
        # 6081H/T». Del token se toma el número —«1006.6», «6081»—, que es lo que el otro
        # proveedor escribe; las letras de atrás son la versión. Sin años, y sin lo que es
        # válvulas, cilindrada o una medida («16V», «1600CC», «120MM»).
        # Solo cuando hay decimal o barra: «22R» y «6359D» son motores que el otro proveedor
        # escribe igual, y partidos dejaban de coincidir.
        _m_num = _RE_MODELO_NUMERICO.fullmatch(w)
        if (_m_num and _m_num.group(2) and ("." in _m_num.group(1) or "/" in _m_num.group(2))
                and _m_num.group(2).split("/")[0] not in _SUFIJOS_QUE_NO_SON_VERSION):
            w = _m_num.group(1)
        es_modelo_numerico = (_RE_NUMERO_DE_MODELO.fullmatch(w) and indice
                              and _es_de_marca(anterior.get(indice, ""))
                              and not _RE_UN_ANIO.fullmatch(w))
        if (w in _RUIDO_EN_FIRMA or w in palabras_marca or w in _POSICIONES
                or w in MARCAS_DE_REPUESTO
                or (not es_modelo_numerico
                    and (len(w) < 3 or _RE_SOLO_NUMERO.fullmatch(w)))):
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
        # Sin el punto final: CRI-FA escribe «Sonda lambda Toyota Corolla. 1.8-16 valvulas.», y
        # «COROLLA.» no es COROLLA para la lista. Esa sonda quedaba sin modelo, y el único que
        # le quedaba era «DESDE», de «Desde 2008».
        w = w.strip("./")
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
    # «TAPA TRASERA» y «TAPA DELANTERA» del motor son lugares, aunque TRASERA y DELANTERA solas
    # sean una posición (un amortiguador trasero): «JTA TAPA TRASERA FIAT FIRE 16V» no es la
    # junta de tapa de válvulas del Fire, y salía limpia contra ella.
    # Con las abreviaturas de IMPERIAL («TAPA TRASE.», «TAPA DELAN.», «TAPA DEL.») y sin
    # confundir la preposición: «TAPA DEL CARTER» no es la tapa delantera.
    # «JTA.TAPA INSP.ARBOL DE LEVA» (TARANTO, en singular) es el lugar LEVAS de las otras listas.
    if re.search(r"\bLEVA\b", limpio):
        pieza.add("LEVAS")
    if re.search(r"\bTAPA\s+(TRAS\w*|POST\w*)", limpio):
        pieza.add("TAPATRASERA")
    if re.search(r"\bTAPA\s+(DELANT\w*|DELAN\w*|DEL\.|FRONTAL)", limpio):
        pieza.add("TAPADELANTERA")
    # La tapa delantera del block es la de la distribución: «TAPA BLOCK LADO DIST.» de Taranto
    # es la «TAPA DELAN. BLOCK» de Imperial. Se marcan juntas para que no se lean como dos
    # lugares distintos.
    if "TAPA" in pieza and ("TAPADELANTERA" in pieza or "DISTRIBUCION" in pieza):
        pieza.update(("TAPADELANTERA", "DISTRIBUCION"))
    # La junta de la CAJA. CAJA sola no cuenta («caja x 10 unidades», ver _RUIDO_EN_FIRMA), así
    # que «Junta Caja JHON DEERE» quedaba como «junta» a secas y en la cola aparecía emparejada
    # con «JTA T.C. J.DEERE», la de tapa de cilindros del mismo tractor. Cuando la caja viene
    # pegada a la junta o dice de velocidad / de cambios, es un lugar como cualquier otro.
    # «JTA CAJA ADMISION» es la caja de admisión (el múltiple), no la de velocidades.
    if (re.search(r"\b(?:JUNTAS?|JTAS?)\.?\s*(?:DE\s+|PARA\s+)?(?:LA\s+)?CAJA\b"
                  r"(?!\.?\s*(?:DE\s+)?(?:ADM|AIRE|FILT|TERMOST|AGUA|DIREC|MARIP|ESC|MULT))",
                  limpio)
            or re.search(r"\bCAJA\s+(?:DE\s+)?(?:VEL\w*|CAMBIO\w*|TRANSM\w*)", limpio)):
        pieza.add("CAJAVELOCIDAD")
    # JL escribe «JUNTAS FIAT TEMPRA WEBER» y «JUNTAS DODGE 1500 STROMBERG» sin decir
    # «carburador»: la marca del carburador lo dice. Sin esto se emparejaban con juntas de tapa
    # de cilindros del mismo auto. CARTER no cuenta acá: también es la junta de cárter.
    # Se mira en TODAS las palabras y no solo en la pieza: WEBER, SOLEX y HOLLEY también son
    # marcas de repuesto, y esas se sacan antes de armar la pieza. «JUNTAS FIAT 128 1972/ WEBER
    # 1b» quedaba como «JUNTA 128» a secas y concordaba con la junta de tapa de cilindros del
    # 128. Solo en las juntas: un «SENSOR TPS WEBER» es de inyección, no del carburador.
    _marcas_carb = (pieza | set(palabras)) & (_MARCAS_DE_CARBURADOR - {"CARTER"})
    if "WB" in _marcas_carb:      # la abreviatura de JL: que no salga «carburadores distintos»
        _marcas_carb = (_marcas_carb - {"WB"}) | {"WEBER"}
    # Los modelos de Solex sin la marca: «JUNTA TAPA CUBA Renault 18/Ford SIERRA TEIE» (JL) es de
    # un Solex, y concordaba con la de la cuba del Holley del Ford V8.
    if set(palabras) & _MODELOS_DE_SOLEX:
        _marcas_carb = _marcas_carb | {"SOLEX"}
    if _marcas_carb and (pieza & {"JUNTA", "JUNTAS"} or "JUNTA" in (cabeza or "")):
        pieza.add("CARBURADOR")
    # «JUNTA TAPA CUBA Renault 18/Ford SIERRA» es la de la cuba del carburador: concordaba con
    # la junta de tapa de cilindros del Sierra porque las dos dicen JUNTA y TAPA.
    if "CUBA" in palabras and (pieza & {"JUNTA", "JUNTAS"} or "JUNTA" in (cabeza or "")):
        pieza.add("CARBURADOR")
    # «JUNTAS CITROEN VISA 2 bocas» (JL), «(2 BOCAS)» (ILLINOIS): las bocas son del carburador.
    if re.search(r"\bBOCAS?\b", limpio) and (pieza & {"JUNTA", "JUNTAS"} or "JUNTA" in (cabeza or "")):
        pieza.add("CARBURADOR")
    # «JUNTA MPI FIAT TEMPRA 2.0 16V» (JL) es la de la inyección, y concordaba con «JTA T.C.
    # FIAT TEMPRA 2.0»: sin ningún lugar, la tapa de cilindros no tenía con qué chocar. Solo si
    # no nombra otro lugar: TARANTO escribe «Jta.Tapa Cil. … 1.6 MPI», y ahí MPI es el motor.
    if ((pieza & {"JUNTA", "JUNTAS"} or "JUNTA" in (cabeza or ""))
            and set(palabras) & {"MPI", "SPI", "TBI", "MPFI"}
            and not pieza & _LUGARES_DE_LA_PIEZA):
        pieza.add("INYECCION")
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

    return _sin_conjuntos_vacios({"familia": familia, "nucleo": nucleo, "cabeza": cabeza, "autos": autos,
            "pieza": pieza, "aplicacion": set(aplicacion),
            "modelos_numericos": modelos_numericos, "modelos": modelos, "marcas": marcas,
            "juego": tipo_de_juego_de_motor(texto), "sensor": tipos_de_sensor(texto),
            "cable_mm": largo_de_cable_mm(descripcion),
            "bar": presiones_en_bar(descripcion),
            "temperaturas": temperaturas_declaradas(descripcion),
            "carburador": (_marcas_carb if "CARBURADOR" in pieza else set()),
            "valvulas": {int(v) for v in _RE_CANTIDAD_DE_VALVULAS.findall(limpio)},
            "motores_numericos": {a + b for a, b in _RE_MOTOR_NUMERICO.findall(limpio)},
            "cilindros": {int(n) for n in
                          _RE_CANTIDAD_DE_CILINDROS.findall(limpio)
                          + [x for grupo in _RE_LISTA_DE_CILINDROS.findall(limpio)
                             for x in grupo.split("/")]
                          + [x for grupo in _RE_CILINDROS_CON_C.findall(limpio)
                             for x in grupo.split("/")]
                          + (_RE_CILINDROS_EN_EL_MOTOR.findall(limpio)
                             if _RE_MOTOR_QUE_DICE_SUS_CILINDROS.search(limpio) else [])
                          + (_RE_CILINDROS_DEUTZ.findall(limpio) if "DEUTZ" in limpio else [])
                          + _RE_CILINDROS_EN_V.findall(limpio)
                          + _RE_CILINDROS_MWM.findall(limpio)
                          + _cilindros_de_cummins(limpio, cilindradas)
                          if 1 <= int(n) <= 16},
            "bujia": tipo_de_bujia(texto),
            "aro": frozenset(_RE_ARO_DE_COLOR.findall(limpio)),
            "modulo": (True if _RE_CON_MODULO.search(limpio)
                       else False if _RE_SIN_MODULO.search(limpio) else None),
            "aire_exterior": bool(_RE_AIRE_EXTERIOR.search(limpio)),
            "motor_ford": _familia_de_motor_ford(limpio),
            "termostato_con_carcasa": _termostato_con_carcasa(limpio),
            "kit": bool(es_un_kit(texto)),
            "esparragos": frozenset(_RE_ESPARRAGOS_MM.findall(limpio)),
            "diametro": (frozenset(_RE_DIAMETRO_DE_LA_JUNTA.findall(limpio))
                         if re.search(r"\bTAPA\s+(?:DE\s+)?CIL", limpio) else _CONJUNTO_VACIO),
            "siglas": siglas, "marca_auto": marca_auto, "posicion": posicion,
            "cilindradas": cilindradas, "vias": vias, "texto": limpio,
            "anios": rangos_de_anios(descripcion),
            "sobremedida": sobremedida_de(descripcion),
            "combustible": combustible_desde_descripcion(descripcion),
            "dana": frozenset(_RE_PUENTE_DANA.findall(limpio)),
            "deutz": (frozenset("514" if x in ("1114", "2114") else x
                                for x in _RE_SERIE_DEUTZ.findall(limpio))
                      if "DEUTZ" in limpio else _CONJUNTO_VACIO),
            "motores": motores_de_la_descripcion(descripcion, excluir=set(modelos) | set(siglas))})


# Un solo conjunto vacío para todas las firmas. Cada firma traía una docena de set() vacíos
# —autos, modelos, siglas, temperaturas…— de 216 bytes cada uno: con 60 proveedores, las
# 269.000 firmas del barrido ocupaban 1,7 GB, la mitad en conjuntos vacíos. Es un frozenset:
# nadie modifica una firma (ver firma_de_producto()), y si alguien lo intentara fallaría en
# vez de ensuciar las firmas de todos.
_CONJUNTO_VACIO = frozenset()


def _sin_conjuntos_vacios(firma):
    for clave, valor in firma.items():
        if isinstance(valor, (set, frozenset)) and not valor:
            firma[clave] = _CONJUNTO_VACIO
    return firma


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


# Dónde va la pieza, que es lo que separa dos juntas del mismo auto. Ver «piezas de lugares
# distintos» en firmas_compatibles(). SENSOR, PRESION o VELOCIDAD no están: dicen qué mide, y
# el mismo sensor MAP se escribe «de presión» en una lista y no en otra.
_LUGARES_DE_LA_PIEZA = {
    "CILINDRO", "VALVULA", "CARTER", "ESCAPE", "ADMISION", "MULTIPLE", "SALIDA", "DISTRIBUCION",
    "LEVAS", "BANCADA", "CARBURADOR", "TERMOSTATO", "DIFERENCIAL", "TURBO", "COLECTOR",
    "BOMBA", "FILTRO", "INYECCION",
    # «JTA CPO.BBA. ACEITE» contra «JTA CPO.BBA.AGUA»: la bomba de aceite y la de agua. Solo
    # cortan cuando cada lado nombra uno que el otro no: «Jta carter aceite» contra «Junta para
    # Cárter» sigue pasando.
    "AGUA", "ACEITE",
    # «JTA LATERAL BOTADORES» y «JTA LATERAL T.V.» son dos tapas distintas del motor. (CAJA no
    # entra: está entre las palabras que no cuentan, por «caja x 10 unidades».)
    "BOTADORES",
    # Ver «TAPA TRASERA» y «la junta de la CAJA» en _firma_armada().
    "TAPATRASERA", "TAPADELANTERA", "CAJAVELOCIDAD",
    # Salidas de revisar a mano los rojos que solo tenían el precio en contra: «Jta.hidraulica
    # JHON DEERE» contra la de tapa de cilindros, la base del distribuidor contra la tapa de
    # distribución, la tapa de la transmisión y la del embrague contra la del termostato.
    "HIDRAULICA", "HIDRAULICO", "DISTRIBUIDOR", "TRANSMISION", "EMBRAGUE",
    # «JTA TAPA INSP.PRECAM. FIAT 2.8» es la de la precámara, no la del árbol de levas.
    "PRECAMARA", "PALIER",
    # «JTA RAD.ACEITE» contra la junta de cárter, «JTA CODO AGUA TORINO» contra la de la bomba
    # de agua del Torino: salidas de revisar a mano los amarillos del barrido.
    "RADIADOR", "CODO",
}

# Las juntas de una PARTE de otra pieza: la tapita de inspección de la tapa de cilindros, el
# respiradero del cárter, el frente de la tapa. «JTA INSP. T.CIL. PEUGEOT XUD9» comparte TAPA y
# CILINDRO con la junta de tapa de cilindros y no es ella. Si una sola de las dos la nombra, son
# juntas distintas. Ver firmas_compatibles().
# Y la tapa LATERAL del cárter: «JTA LAT.CARTER DEUTZ 514 2 C.» de IMPERIAL es la de la tapita
# del costado, y «Junta para Cárter DEUTZ 514» de ILLINOIS la del cárter. IMPERIAL las vende
# por separado (527AC2 y 528AC2).
# La tapa de INSPECCIÓN es una parte solo de las tapas grandes: la de cilindros, la de válvulas,
# el cárter. De lo demás ES la tapa: «JTA. TAPA CAM.AGUA DIESEL» (TARANTO) y «JTA T.INSP.CAM.AGUA
# FIAT REGAT» (IMPERIAL) son la misma junta, igual que la tapa del árbol de levas y la tapa de
# inspección del árbol de levas. Las cuatro salían en rojo; revisadas, eran la misma pieza.
# «INSP» va también sin expandir: «JTA TAPA INSP BLOCK» contra «JTA TAPA.INSP. BLOCK».
_RE_PARTE_DE_UNA_PIEZA = re.compile(
    r"\b(INSP(?:ECCION)?|RESP|RESPIRADERO|FRENTE|LAT(?:ERAL)?(?=\s+CARTER\b)"
    r"|(?<=CARTER )LAT(?:ERAL)?)\b")
_PIEZAS_CON_TAPA_DE_INSPECCION = {"CILINDRO", "VALVULA", "CARTER"}

# Ver «la marca sola no alcanza» en firmas_compatibles().
_TECNOLOGIAS_DE_MOTOR = {
    "TDI", "TDCI", "HDI", "CRDI", "DCI", "JTD", "JTDM", "MULTIJET", "CDI", "CDTI", "DTI", "TDDI",
    "TDS", "TSI", "TFSI", "FSI", "GTI", "MPI", "SPI", "MPFI", "VTI", "VTEC", "TURBO", "TD", "D",
    "DIESEL", "NAFTA", "GNC", "16V", "8V", "12V", "20V", "24V", "32V", "DOHC", "SOHC", "INY",
    "INYECCION", "CARB", "CARBURADOR", "EFI", "TBI", "ECO", "FLEX", "EVO",
}


def _una_letra_de_diferencia(x, y):
    """¿Son la misma palabra con una letra de más, de menos o cambiada? CKEROKEE y CHEROKEE."""
    if abs(len(x) - len(y)) > 1:
        return False
    if len(x) == len(y):
        return sum(1 for p, q in zip(x, y) if p != q) == 1
    corta, larga = (x, y) if len(x) < len(y) else (y, x)
    return any(larga[:i] + larga[i + 1:] == corta for i in range(len(larga)))


def _modelos_en_comun(modelos_a, modelos_b):
    """Los modelos que nombran las dos, contando los que las listas escriben mal: FISPA pone
    «JEEP CKEROKEE DAKOTA RAM» y TARANTO «MAZDA CAPELA … 626-MX-6», y con eso un sensor MAP de
    Grand Cherokee y la junta del Capella salían en rojo por «modelos distintos». Una letra de
    diferencia solo en nombres de seis letras o más —ASTRA y ASTRO son dos Chevrolet—, y sin
    los guiones: MX-6 es el MX6."""
    comunes = set(modelos_a) & set(modelos_b)
    if comunes:
        return comunes
    sin_guion_b = {m.replace("-", ""): m for m in modelos_b}
    for m in modelos_a:
        if m.replace("-", "") in sin_guion_b:
            comunes.add(m)
            continue
        if len(m) >= 6 and any(len(o) >= 6 and _una_letra_de_diferencia(m, o)
                               for o in modelos_b):
            comunes.add(m)
    return comunes


def _marcas_que_se_cruzan(marcas_a, marcas_b):
    """¿Nombran alguna marca en común, o de la misma familia, o una nombra solo motores?

    La marca de motores cruza con cualquiera solo si ese lado NO nombra además un vehículo.
    «Bulbo presion de aceite Ford F100 … Cargo … Cummins Mwm» (CRI-FA 32-42371) contra el de
    «CHEVROLET AVEO CRUZE TRACKER» (349FISPA) pasaba sin alarmas: Cummins y MWM lo salvaban,
    y FORD contra CHEVROLET nunca se comparaba."""
    if marcas_a & marcas_b:
        return True
    autos_a, autos_b = marcas_a - _MARCAS_DE_MOTORES, marcas_b - _MARCAS_DE_MOTORES
    if not autos_a or not autos_b:
        return True
    return any(fam & autos_a and fam & autos_b for fam in _FAMILIAS_DE_MARCAS)


def _lo_fisico_que_no_coincide(a, b):
    """El motivo, si las dos firmas declaran algo físico de la pieza y no coincide: las vías de
    la ficha, el largo del cable, la temperatura. None si no. Ver firmas_compatibles()."""
    # Cantidad de vías / pines: si las dos la declaran y no es la misma, son piezas distintas.
    # Sin esto se proponía una «FICHA 3 Vias Macho» contra una «FICHA 2 vias macho»: mismo
    # rubro, misma primera palabra, mismo tipo de conector, y no entra una donde va la otra.
    if a.get("vias") and b.get("vias") and a["vias"] != b["vias"]:
        return f"distinta cantidad de vías ({a['vias']} vs {b['vias']})"
    # Ver _RE_LARGO_DE_CABLE: con una tolerancia de 3 cm o el 10%, lo que sea más, porque
    # uno redondea y otro no.
    _cab_a, _cab_b = a.get("cable_mm"), b.get("cable_mm")
    if _cab_a and _cab_b and abs(_cab_a - _cab_b) > max(30, 0.1 * max(_cab_a, _cab_b)):
        # Con poca diferencia no es seguro: revisando a mano los rojos por cable, 40 contra 45 o
        # 30 contra 34 cm pueden ser la misma sonda medida con la ficha o sin ella. Hasta 8 cm o
        # el 25%, a revisión (ver _MOTIVOS_QUE_AVISAN); más, a rojo (37 contra 63 es otra).
        if abs(_cab_a - _cab_b) <= max(80, 0.25 * max(_cab_a, _cab_b)):
            return (f"el largo de cable se parece pero no es el mismo ({_cab_a / 10:.0f} "
                    f"vs {_cab_b / 10:.0f} cm)")
        return f"largo de cable distinto ({_cab_a / 10:.0f} vs {_cab_b / 10:.0f} cm)"
    # Ver _RE_PAR_DE_TEMPERATURAS.
    _tem_a, _tem_b = a.get("temperaturas") or set(), b.get("temperaturas") or set()
    if _tem_a and _tem_b and not (_tem_a & _tem_b):
        return (f"temperaturas distintas ({'/'.join(map(str, sorted(_tem_a, reverse=True)))}"
                f" vs {'/'.join(map(str, sorted(_tem_b, reverse=True)))})")
    return None


def firmas_compatibles(a, b, minimo_nucleo=2, cuenta_palabras=None, total_descripciones=0):
    """¿Estas dos descripciones hablan de la misma pieza? Devuelve (sí/no, motivo).

    Se exige coincidencia en lo que define la pieza y NO contradicción en lo que la distingue.
    Es a propósito conservador: un falso positivo acá es una equivalencia inventada, y ya
    sabemos lo que eso le hizo a la base.

    UNA DUDA NO TAPA UNA CONTRADICCIÓN. Las reglas corren en orden y la primera que dice algo
    corta. Algunas son dudas —«el mismo auto con otra cilindrada», «una de las dos no dice para
    qué auto es»— y mandan a revisión; si una de esas cortaba antes, una contradicción que venía
    después (36 contra 63 cm de cable) no se veía nunca, y el buscador encadenaba la pieza como
    «sólida». Así que, si la respuesta es una duda, se compara otra vez salteando las dudas, y
    si aparece una contradicción, gana esa."""
    ok, motivo = _comparar_firmas(a, b, minimo_nucleo, cuenta_palabras, total_descripciones)
    if not ok and motivo.startswith(_MOTIVOS_QUE_AVISAN):
        ok2, motivo2 = _comparar_firmas(a, b, minimo_nucleo, cuenta_palabras,
                                        total_descripciones, con_dudas=False)
        if not ok2 and motivo2.startswith(_MOTIVOS_QUE_CONTRADICEN):
            return False, motivo2
    return ok, motivo


def _comparar_firmas(a, b, minimo_nucleo=2, cuenta_palabras=None, total_descripciones=0,
                     con_dudas=True):
    """Ver firmas_compatibles(). Con con_dudas=False, las reglas que solo dudan no cortan."""
    if not a or not b:
        return False, ""
    if a["familia"] == "Sin clasificar" or b["familia"] == "Sin clasificar":
        return False, "no se pudo clasificar el rubro"
    if a["familia"] != b["familia"]:
        return False, "rubros distintos"

    # El juego de juntas del motor contra una junta suelta, o dos juegos distintos (completo
    # contra superior). Ver tipo_de_juego_de_motor().
    if juegos_que_chocan(a.get("juego"), b.get("juego")):
        # EL JUEGO DE UN LUGAR CONTRA LA JUNTA DE ESE LUGAR no es seguro que sean distintos:
        # la junta de cárter de un Perkins 4.203 viene en varias piezas, y TARANTO la llama
        # «Jgo.Jtas.Carter PERKINS 4-203» e ILLINOIS «Junta para Cárter PERKINS … 4.203». Lo
        # mismo con «Jgo.Jtas.Mult.Adm. y Esc.» contra «JTA ADM y ESC». Solo cuando el juego no
        # es de motor, comparten el lugar y la suelta no es una parte («CARTER CHICO», «BASE»).
        _juego, _suelta = ((a, b) if a.get("juego") else (b, a))
        _lugar_comun = (set(a.get("pieza") or ()) & set(b.get("pieza") or ())
                        & _LUGARES_DE_LA_PIEZA)
        if (_juego.get("juego") == JUEGO_SIN_DECIR_CUAL and not _suelta.get("juego")
                and _lugar_comun
                and not re.search(r"\b(CHICO|CHICA|GRANDE|BASE|BSE|SOBRE|TAPA)\b",
                                  _suelta.get("texto") or "")):
            return False, (f"un juego de juntas de {'/'.join(sorted(_lugar_comun))} contra una "
                           "junta suelta del mismo lugar: algunas listas llaman «junta» al juego")
        return False, (f"juegos distintos: {a.get('juego') or 'junta suelta'} vs "
                       f"{b.get('juego') or 'junta suelta'}")

    # La junta de tapa de supermedida contra la estándar: mismo auto, misma pieza, y no
    # reemplaza una a la otra. No es un motivo «del auto»: corta aunque los una un código,
    # porque la de supermedida suele citar el número original de la estándar.
    # Ver sobremedida_de().
    if sobremedidas_que_chocan(a.get("sobremedida"), b.get("sobremedida")):
        def _sm(x):
            return ("sobremedida" if x == "SI" else f"+{x}".replace(".", ",")) if x else "estándar"
        return False, (f"sobremedida distinta: {_sm(a.get('sobremedida'))} vs "
                       f"{_sm(b.get('sobremedida'))}")

    # La junta de una parte de la pieza contra la de la pieza: ver _RE_PARTE_DE_UNA_PIEZA.
    def _partes(f):
        return {"INSPECCION" if p == "INSP" else p
                for p in _RE_PARTE_DE_UNA_PIEZA.findall(f.get("texto") or "")}
    _parte_a, _parte_b = _partes(a), _partes(b)
    # La inspección, solo contra la junta de una tapa grande: ver _PIEZAS_CON_TAPA_DE_INSPECCION.
    for _con, _sin in ((_parte_a, b), (_parte_b, a)):
        if _con == {"INSPECCION"} and not (_PIEZAS_CON_TAPA_DE_INSPECCION
                                           & set(_sin.get("pieza") or ())):
            _con.clear()
    if (bool(_parte_a) != bool(_parte_b) and "JUNTA" in (a.get("pieza") or ())
            and "JUNTA" in (b.get("pieza") or ())):
        # En castellano y no la palabra de la lista: se leía «la del INSPECCION vs la pieza
        # entera».
        _cual = {"INSPECCION": "la tapa de inspección", "RESP": "el respiradero",
                 "RESPIRADERO": "el respiradero", "FRENTE": "el frente", "LAT": "el costado",
                 "LATERAL": "el costado"}.get(min(_parte_a or _parte_b),
                                              min(_parte_a or _parte_b).lower())
        return False, (f"piezas de lugares distintos: la junta de {_cual} vs la de la pieza "
                       "entera")

    # UNA PARTE DEL CARBURADOR CONTRA EL JUEGO DEL CARBURADOR: «JTA BASE CARB F. SIERRA 1.6»
    # (IMPERIAL, la base sola) contra «JUNTAS SIERRA 1.6 1983/86 WEBER» (JL, el juego). Las dos
    # son del carburador del Sierra y no son la misma pieza.
    if ("CARBURADOR" in (a.get("pieza") or ()) and "CARBURADOR" in (b.get("pieza") or ())):
        _juego_a, _juego_b = _es_juego_de_carburador(a), _es_juego_de_carburador(b)
        # En un juego, «(CUBA CHICA)» dice para qué cuba es, no que sea la junta de la cuba.
        _pc_a = set() if _juego_a else _partes_del_carburador(a.get("texto") or "")
        _pc_b = set() if _juego_b else _partes_del_carburador(b.get("texto") or "")
        for _pc, _juego_otro in ((_pc_a, _juego_b), (_pc_b, _juego_a)):
            if _pc and _juego_otro:
                return False, (f"piezas de lugares distintos: la junta {'/'.join(sorted(_pc))} "
                               "del carburador vs el juego de juntas del carburador")
        if _pc_a and _pc_b and not (_pc_a & _pc_b):
            return False, (f"piezas de lugares distintos: {'/'.join(sorted(_pc_a))} vs "
                           f"{'/'.join(sorted(_pc_b))} del carburador")
    # El bulbo del reloj contra el de la luz: ver RELOJ y TESTIGO en _TIPOS_DE_SENSOR.
    _uso_a = (a.get("sensor") or frozenset()) & {"RELOJ", "TESTIGO"}
    _uso_b = (b.get("sensor") or frozenset()) & {"RELOJ", "TESTIGO"}
    if len(_uso_a) == 1 and len(_uso_b) == 1 and _uso_a != _uso_b:
        return False, (f"sensores de tipos distintos: el del {'reloj' if 'RELOJ' in _uso_a else 'testigo'}"
                       f" vs el del {'reloj' if 'RELOJ' in _uso_b else 'testigo'}")
    if (a.get("modulo") is not None and b.get("modulo") is not None
            and a["modulo"] != b["modulo"]):
        return False, "versiones distintas: con módulo de encendido vs sin módulo"
    if ((a.get("sensor") or b.get("sensor")) and a.get("aire_exterior") != b.get("aire_exterior")
            and "TEMPERATURA" in ((a.get("sensor") or frozenset()) & (b.get("sensor") or frozenset()))):
        return False, ("sensores de tipos distintos: el de la temperatura del aire exterior vs el "
                       "del motor")
    if a.get("aro") and b.get("aro") and not (a["aro"] & b["aro"]):
        return False, (f"aros de distinto color: {'/'.join(sorted(a['aro']))} vs "
                       f"{'/'.join(sorted(b['aro']))}")
    # En un sensor o una sonda no: nombran varios motores y cada lista anota los que quiere.
    if (a.get("motor_ford") and b.get("motor_ford") and a["motor_ford"] != b["motor_ford"]
            and not (a.get("sensor") or b.get("sensor"))):
        return False, f"motores distintos: {a['motor_ford']} vs {b['motor_ford']}"
    _tc_a, _tc_b = a.get("termostato_con_carcasa"), b.get("termostato_con_carcasa")
    if _tc_a is not None and _tc_b is not None and _tc_a != _tc_b:
        return False, "juegos distintos: el termostato solo vs el termostato con su carcasa"
    # Un kit contra la pieza suelta, fuera de las juntas (que tienen su propia regla: ver
    # tipo_de_juego_de_motor()): «KIT DE CORREA POLY V … SKF 32000A1» contra «CORREA POLY V
    # 3PK905». Se vende uno o el otro.
    if (a.get("kit") != b.get("kit") and not a.get("juego") and not b.get("juego")
            and not ({"JUNTA", "JUNTAS"} & (set(a.get("pieza") or ()) | set(b.get("pieza") or ())))):
        return False, "juegos distintos: un kit vs la pieza suelta"
    for _clave, _nombre in (("esparragos", "espárragos"), ("diametro", "diámetro del cilindro")):
        _m_a, _m_b = a.get(_clave), b.get(_clave)
        if _m_a and _m_b and not (_m_a & _m_b):
            return False, (f"medidas distintas: {_nombre} {'/'.join(sorted(_m_a))} vs "
                           f"{'/'.join(sorted(_m_b))} mm")
    if a.get("deutz") and b.get("deutz") and not (a["deutz"] & b["deutz"]):
        return False, (f"motores distintos: DEUTZ {'/'.join(sorted(a['deutz']))} vs "
                       f"DEUTZ {'/'.join(sorted(b['deutz']))}")
    # La junta de CARBURADOR contra algo que va en un diésel: «JUNTA RENAULT R18 1.6/2.0/2.1D»,
    # «… TRAFIC nafta/diesel con posicionador» (JL) concordaban con el juego de juntas del
    # carburador del R18 y del Trafic. Un diésel no tiene carburador.
    for _carb, _otro in ((a, b), (b, a)):
        if ("CARBURADOR" in (_carb.get("pieza") or ()) and "CARBURADOR" not in (_otro.get("pieza") or ())
                and _RE_DIESEL_CON_LA_D.search(_otro.get("texto") or "")):
            return False, "piezas de lugares distintos: CARBURADOR vs una pieza que va en un diésel"
    if a.get("dana") and b.get("dana") and not (a["dana"] & b["dana"]):
        return False, (f"modelos distintos: DANA {'/'.join(sorted(a['dana']))} vs "
                       f"DANA {'/'.join(sorted(b['dana']))}")
    # «Bulbo presion de aceite … 0.40 BAR» contra «BULBO DE PRESION DE ACEITE … PRESION 0 5
    # BAR»: el bulbo abre a otra presión, la bomba de nafta empuja otra. Ver presiones_en_bar().
    if presiones_que_chocan(a.get("bar"), b.get("bar")):
        def _bar(x):
            return "/".join(f"{v:g}".replace(".", ",") for v in sorted(x))
        return False, f"presiones distintas: {_bar(a['bar'])} vs {_bar(b['bar'])} bar"

    if a.get("bujia") and b.get("bujia") and a["bujia"] != b["bujia"]:
        return False, f"bujías de tipos distintos: {a['bujia']} vs {b['bujia']}"
    _cil_a, _cil_b = a.get("cilindros") or set(), b.get("cilindros") or set()
    if _cil_a and _cil_b and not (_cil_a & _cil_b):
        return False, (f"distinta cantidad de cilindros: {'/'.join(map(str, sorted(_cil_a)))} vs "
                       f"{'/'.join(map(str, sorted(_cil_b)))}")
    _sen_a, _sen_b = a.get("sensor") or frozenset(), b.get("sensor") or frozenset()
    if _sen_a and _sen_b and not (_sen_a & _sen_b):
        return False, (f"sensores de tipos distintos: {'/'.join(sorted(_sen_a))} vs "
                       f"{'/'.join(sorted(_sen_b))}")

    # Posición: si las dos la declaran y no coinciden, son piezas distintas. Un amortiguador
    # delantero no reemplaza a uno trasero por más que vayan al mismo auto.
    if a["posicion"] and b["posicion"] and a["posicion"] != b["posicion"]:
        return False, f"posiciones distintas ({a['posicion']} vs {b['posicion']})"
    # «Tapa de válvulas superior» contra «Tapa de Válvulas Lateral» (TARANTO 350332 contra
    # ILLINOIS JVL-163-43, las dos del OM352): dos tapas distintas del mismo motor. LATERAL no
    # es una posición más de _POSICIONES a propósito: «soporte motor lateral izquierdo» y
    # «soporte motor izquierdo» son el mismo soporte. Solo choca contra SUPERIOR.
    _lat_a = bool(re.search(r"\bLATERAL\b", a.get("texto") or ""))
    _lat_b = bool(re.search(r"\bLATERAL\b", b.get("texto") or ""))
    if _lat_a != _lat_b and "SUPERIOR" in (a["posicion"] if _lat_b else b["posicion"],):
        return False, "posiciones distintas (SUPERIOR vs LATERAL)"

    # Cilindrada: si las dos la declaran y no comparten ninguna, no es la misma aplicación
    if a["cilindradas"] and b["cilindradas"] and not (a["cilindradas"] & b["cilindradas"]):
        # En un SENSOR del mismo auto no alcanza: el sensor de rotación o el MAP suelen servir
        # para varios motores, y cada lista anota los que quiere. «Sensor de rotacion Renault
        # Fluence Duster Logan 1,6» contra «LEMSR215 RENAULT Duster Oroch Captur 2 0 … Kangoo
        # 1 5 dci» pueden ser el mismo. Revisando a mano 40 rojos por cilindrada, en las juntas
        # la regla acertó siempre y en los sensores del mismo auto no se podía afirmar. Esos van
        # a revisión (ver _MOTIVOS_QUE_AVISAN); sin ningún auto en común siguen en rojo.
        _mismo_auto = (a.get("modelos") or set()) & (b.get("modelos") or set())
        if (a.get("sensor") or b.get("sensor")) and _mismo_auto:
            # Es una duda: ver «una duda no tapa una contradicción» en firmas_compatibles().
            if con_dudas:
                return False, (f"el mismo auto con otra cilindrada: "
                               f"{'/'.join(sorted(a['cilindradas'])[:3])} vs "
                               f"{'/'.join(sorted(b['cilindradas'])[:3])} "
                               f"({'/'.join(sorted(_mismo_auto)[:2])}); un sensor suele servir "
                               "para varias")
        else:
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
        _lo_nombra = (any(re.search(rf'\b{re.escape(n)}\b', _texto_b) for n in _num_a)
                      or any(re.search(rf'\b{re.escape(n)}\b', _texto_a) for n in _num_b))
        if not _lo_nombra:
            return False, (f"modelos distintos: {'/'.join(sorted(_num_a)[:2])} "
                           f"vs {'/'.join(sorted(_num_b)[:2])}")

    # LOS AUTOS. Probado sobre dos listas reales de 5.000 y 26.000 productos, es el control
    # que evita la avalancha de falsos: sin él, toda «BUJIA NAFTA» se vinculaba con toda otra
    # «BUJIA NAFTA» porque comparten dos palabras genéricas, aunque una fuera de un Renault y
    # la otra de un BMW.
    if a["autos"] and b["autos"]:
        autos_comunes = a["autos"] & b["autos"]
        # Cuando UNA sola nombra nada más que al que hizo el motor —«JTA CARTER MWM SPRINT»
        # contra «Jta.Carter CHEVROLET SPRINT 4.07T»— no se contradicen: la S10 lleva el MWM.
        # Si las dos nombran solo motoristas, sí: un MWM no es un Cummins.
        _solo_motor_a = a["autos"] <= _MARCAS_DE_MOTORES
        _solo_motor_b = b["autos"] <= _MARCAS_DE_MOTORES
        if not autos_comunes and _solo_motor_a == _solo_motor_b:
            return False, (f"autos distintos: {'/'.join(sorted(a['autos'])[:2])} "
                           f"vs {'/'.join(sorted(b['autos'])[:2])}")
    else:
        autos_comunes = set()

    # LOS AÑOS. «Jta.Tapa Cil. HONDA CIVIC … 1984/1989» y «Junta Tapa de Cilindros HONDA CIVIC
    # 2015/... L15B8» comparten el modelo y son de autos con 26 años de diferencia: salían en
    # verde. Solo cuando las dos escriben rangos (ver rangos_de_anios()) y ninguno se cruza.
    # Cuenta como motivo «del auto»: si los une un código, el código manda (un inyector de un
    # Corsa 1993 y uno de un Corsa 1999 con el mismo número ICD00107 son el mismo).
    if anios_que_no_se_tocan(a.get("anios"), b.get("anios")):
        def _txt(rangos):
            return "/".join(f"{d}-{'…' if h == 2100 else h}" for d, h in rangos[:2])
        return False, f"años distintos: {_txt(a['anios'])} vs {_txt(b['anios'])}"

    # Nafta contra diésel, en las piezas del motor: «Termostato Chevrolet Blazer S10 -2.2 …
    # Naftero» contra el de la «S10 2012 2013 Motor 180 Duramax». Cuenta como motivo «del auto»:
    # si los une un código, el código manda. Ver combustible_desde_descripcion().
    if (a["familia"] in _RUBROS_QUE_DEPENDEN_DEL_COMBUSTIBLE and a.get("combustible")
            and b.get("combustible") and a["combustible"] != b["combustible"]):
        return False, f"combustibles distintos: {a['combustible']} vs {b['combustible']}"

    # LOS MOTORES. «Jta.Carter DEUTZ F4L 913» contra «Junta para Cárter DEUTZ 913 … F5L»: el
    # mismo tractor, cuatro cilindros contra cinco. «Jta.Tapa Cilindros Renault Master motor
    # G9U» contra la del Master S8U. Si las dos nombran motores y no comparten ninguno (ni de la
    # misma familia, ni declarados juntos: ver algun_motor_en_comun()), son de motores
    # distintos. Las bujías no: sus códigos de otras marcas tienen forma de motor (W8BC).
    # Cuenta como motivo «del auto»: si los une un código, el código manda.
    _mot_a, _mot_b = a.get("motores") or (), b.get("motores") or ()
    if (_mot_a and _mot_b and "BUJIA" not in (a.get("cabeza"), b.get("cabeza"))
            and not algun_motor_en_comun(_mot_a, _mot_b)):
        return False, (f"motores distintos: {'/'.join(sorted(_mot_a)[:2])} "
                       f"vs {'/'.join(sorted(_mot_b)[:2])}")

    _fisico = _lo_fisico_que_no_coincide(a, b)
    if _fisico:
        return False, _fisico

    # El carburador que las dos nombran. «Juego de juntas para Carburador FIAT 1500 WEBER 28-36»
    # y «JUNTAS FIAT 128/1500 SOLEX 2 bocas» son del mismo auto y de otro carburador: las juntas
    # de un Weber no van en un Solex.
    _carb_a, _carb_b = a.get("carburador") or set(), b.get("carburador") or set()
    if _carb_a and _carb_b and not (_carb_a & _carb_b):
        return False, (f"carburadores distintos: {'/'.join(sorted(_carb_a))} "
                       f"vs {'/'.join(sorted(_carb_b))}")

    # Las válvulas del motor, en las juntas de la tapa de cilindros: la tapa de un Fire 8V no es
    # la de un Fire 16V, ni la de un Captiva 16V la del V6 de 24. Solo ahí: un sensor o una
    # sonda nombran varios motores y dicen las válvulas de algunos («GOL III 1 0 Mi 2 0 16v»),
    # y que no nombre el 8V no quiere decir que no le vaya.
    _val_a, _val_b = a.get("valvulas") or set(), b.get("valvulas") or set()
    if (_val_a and _val_b and not (_val_a & _val_b)
            and {"JUNTA"} <= (a["pieza"] & b["pieza"])
            and any({"TAPA", "CILINDRO"} <= x["pieza"] for x in (a, b))):
        return False, (f"motores de distintas válvulas: "
                       f"{'/'.join(f'{v}V' for v in sorted(_val_a))} "
                       f"vs {'/'.join(f'{v}V' for v in sorted(_val_b))}")

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

    # Los lugares, también cuando comparten poco. Si cada una nombra un lugar que la otra no
    # —la caja contra la tapa de cilindros— no es que falten palabras: son dos juntas distintas.
    # Sin esto, «Junta Caja JHON DEERE» contra «JTA T.C. J.DEERE» salía por «solo comparten 1
    # palabra», que no tumba el par, y quedaba dudoso en vez de rojo. Es la misma regla de más
    # abajo (ver «piezas de lugares distintos»), mirada antes.
    _lug_a = (set(a.get("pieza") or ()) - set(b.get("pieza") or ())) & _LUGARES_DE_LA_PIEZA
    _lug_b = (set(b.get("pieza") or ()) - set(a.get("pieza") or ())) & _LUGARES_DE_LA_PIEZA
    if _lug_a and _lug_b:
        return False, (f"piezas de lugares distintos: {'/'.join(sorted(_lug_a))} "
                       f"vs {'/'.join(sorted(_lug_b))}")

    # LA JUNTA QUE NO DICE DE QUÉ ES contra una que sí: «JUNTA FORD F100 2.5TD/3.6 V6/4.3TD»
    # o «JUNTA RENAULT R9-R11-R19-TRAFIC nafta/diesel con posicionador» (JL) concordaban con la
    # de palier y con la de cárter de los mismos autos. No se puede decir que sea otra pieza,
    # pero tampoco que sea esa: a revisión (ver _MOTIVOS_QUE_AVISAN).
    _lugares_a = set(a.get("pieza") or ()) & _LUGARES_DE_LA_PIEZA
    _lugares_b = set(b.get("pieza") or ()) & _LUGARES_DE_LA_PIEZA
    def _no_dice_de_que(f):
        return (not (set(f.get("pieza") or ()) - {"JUNTA", "JUNTAS", "TAPA"})
                and not f.get("siglas"))
    # JUNTAS en plural también: «Juntas para palier FORD F100-350» (ILLINOIS).
    if ({"JUNTA", "JUNTAS"} & set(a.get("pieza") or ()) and {"JUNTA", "JUNTAS"} & set(b.get("pieza") or ())
            and not a.get("juego") and not b.get("juego")
            and bool(_lugares_a) != bool(_lugares_b)
            and _no_dice_de_que(b if _lugares_a else a) and con_dudas):
        return False, (f"una de las dos no dice de qué es la junta; la otra es de "
                       f"{'/'.join(sorted(_lugares_a or _lugares_b))}")
    # Y LA QUE NO DICE PARA QUÉ AUTO ES contra una que sí: «Junta Acople Agua» (TARANTO) contra
    # «JTA ACOPLE CAÑO AGUA TOYOTA 1K». Las dos genéricas se comparan igual que siempre.
    def _nombra_auto(f):
        return bool(f.get("autos") or f.get("marcas") or f.get("motores")
                    or f.get("modelos_numericos") or f.get("motores_numericos"))
    if _nombra_auto(a) != _nombra_auto(b) and con_dudas:
        return False, "una de las dos no dice para qué auto es"

    comunes = set(a["nucleo"]) & set(b["nucleo"])
    if len(comunes) < minimo_nucleo:
        return False, f"solo comparten {len(comunes)} palabra(s)"

    # Lo que comparten del lado del AUTO, sin la cilindrada ni las válvulas: ver más abajo, en
    # el control de «para qué auto es». Se calcula acá porque el control de la pieza lo
    # necesita para el caso de una sola palabra.
    apl_comunes = {w for w in (a.get("aplicacion") or set()) & (b.get("aplicacion") or set())
                   if not _RE_SOLO_MOTORIZACION.match(w) and not _RE_MEDIDA_SUELTA.match(w)}
    # El mismo motor con otro separador: «PERKINS 4.203» y «4-203», «6.354» y «6-354»,
    # «411-R» y «411R». Se comparan sin puntos, guiones ni barras, y solo los que tienen algún
    # número: sin eso, dos palabras que se escriben igual sin separadores no dicen nada.
    def _sin_separadores(w):
        return re.sub(r"[.\-/]", "", w)
    _apl_b_normal = {}
    for w in (b.get("aplicacion") or set()):
        if any(ch.isdigit() for ch in w) and not _RE_SOLO_MOTORIZACION.match(w) \
                and not _RE_MEDIDA_SUELTA.match(w):
            _apl_b_normal.setdefault(_sin_separadores(w), w)
    for w in (a.get("aplicacion") or set()):
        _n = _sin_separadores(w)
        if (w not in apl_comunes and len(_n) >= 3 and _n in _apl_b_normal
                and any(ch.isdigit() for ch in w)
                and not _RE_SOLO_MOTORIZACION.match(w) and not _RE_MEDIDA_SUELTA.match(w)):
            apl_comunes.add(w)

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
    # Para estas dos reglas, lo compartido que salva tiene que ser un MOTOR, no una tecnología
    # de motor: «TDCI», «HDI» o «16V» los tienen decenas de motores distintos. Lo mostró la
    # muestra de control: «Ranger Puma 2168cc» contra «Fiesta Focus Transit 1,8» pasaba porque
    # las dos dicen TDCI.
    apl_comunes = {w for w in apl_comunes if w not in _TECNOLOGIAS_DE_MOTOR}
    # Y al revés: comparten una palabra de modelo pero las marcas no coinciden. «S10-Trail
    # Blazer» de Chevrolet contra «X-TRAIL» de Nissan compartían TRAIL, y con eso los autos
    # «coincidían». El modelo compartido no cuenta como respaldo acá, justamente porque es la
    # palabra que se está poniendo en duda; un código de motor en común sí.
    _mar_a, _mar_b = a.get("marcas") or set(), b.get("marcas") or set()
    # Si una nombra una marca de motores y comparten un nombre de modelo, no se corta acá:
    # «PERKINS CASE 580H F350 VW680» es una lista de vehículos con ese motor, y la F350 que
    # nombra es la de Ford. Eso queda para la regla de abajo, que lo manda a revisión.
    _con_motores_y_modelo = bool(
        (_mar_a | _mar_b) & _MARCAS_DE_MOTORES
        and (a.get("autos") or set()) & (b.get("autos") or set()) & (_mod_a | _mod_b))
    if (_mar_a and _mar_b and not _marcas_que_se_cruzan(_mar_a, _mar_b)
            and not (apl_comunes - _mod_a - _mod_b) and not _con_motores_y_modelo):
        return False, (f"marcas distintas: {'/'.join(sorted(_mar_a)[:2])} "
                       f"vs {'/'.join(sorted(_mar_b)[:2])}")
    # LA MARCA DE MOTORES NO SALVA UN NOMBRE DE OTRA MARCA. Que una nombre a MWM y la otra a
    # FORD no dice que sean autos distintos (ver _MARCAS_DE_MOTORES), pero si lo ÚNICO que
    # comparten es un nombre de modelo, ese nombre es de otra cosa en cada marca: «Junta Tapa
    # Valvulas MWM SPRINT 4.07» (el motor Sprint) salía sin alarmas contra la de «FORD FALCON
    # … 221 SPRINT» y contra la de «CHEVROLET SPRINT SWIFT». Con un motor o un número en común,
    # o nombrando las dos a la misma marca, no se corta.
    # Va a REVISIÓN y no a rojo: el motivo no está en _MOTIVOS_QUE_CONTRADICEN. Medido sobre la
    # cola, lo demás que agarra es «FORD F100» contra «PERKINS F100»: la misma camioneta, que
    # puede tener el mismo motor o no. Eso lo decide una persona, no se descarta de una.
    if (_mar_a and _mar_b and not (_mar_a & _mar_b)
            and not any(fam & _mar_a and fam & _mar_b for fam in _FAMILIAS_DE_MARCAS)
            and not (apl_comunes - _mod_a - _mod_b)):
        _comunes = (a.get("autos") or set()) & (b.get("autos") or set())
        if _comunes and _comunes <= (_mod_a | _mod_b) and con_dudas:
            return False, (f"un nombre de modelo de marcas distintas: "
                           f"{'/'.join(sorted(_comunes)[:2])} ({'/'.join(sorted(_mar_a)[:2])} vs "
                           f"{'/'.join(sorted(_mar_b)[:2])}), puede ser otra cosa en cada una")
    # Solo cuando las dos son ESPECÍFICAS: tres modelos o menos de cada lado. Una lista larga
    # —«SENSOR DE DETONACION FIAT 500 BRAVO IDEA PUNTO...» contra «Fiat BRAVA DOBLO»— es de
    # una pieza que va en muchos autos, y cada proveedor anota los que quiere: que no se pisen
    # no dice que sean piezas distintas. Una junta de tapa de cilindros de S10 y Trail Blazer
    # contra una de Corsa, Astra y Tigra, sí.
    # Y cuando UNA es específica —uno o dos modelos— alcanza con esa, aunque la otra sea una
    # lista larga: «Sensor MAP Chevrolet Onix Prisma» contra «SENSOR MAP CHEVROLET CAPTIVA -
    # LACETTI - NUBIRA...». Si la lista larga nombra veinte autos y ni uno es el de la corta, es
    # el sensor de otros autos. Sobre la cola real eran 284 pares en «nada dice que sean la misma
    # pieza», y en la muestra los 25 eran de autos distintos. Lo que las salva sigue igual: que
    # el modelo de una esté escrito en cualquier lado de la otra, o un motor en común.
    _especificas = ((len(_mod_a) <= 3 and len(_mod_b) <= 3)
                    or min(len(_mod_a), len(_mod_b)) <= 2)
    if (_mod_a and _mod_b and not _modelos_en_comun(_mod_a, _mod_b) and not apl_comunes
            and _especificas):
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
            # Cuando cada una nombra un LUGAR del motor que la otra no —cárter contra tapa de
            # válvulas, múltiple contra salida de escape— no es que el texto no alcance: dice
            # que son dos piezas distintas. Ese motivo tumba el par (ver
            # _MOTIVOS_QUE_CONTRADICEN); el otro solo deja de sumar. La diferencia la mostró la
            # muestra de control: «Jta.Tapa Cil. S10» contra «Junta Tapa de Válvulas M.W.M.»
            # quedaba limpia con 75 por el rubro y el precio.
            _lugar_a = (pieza_a - pieza_b) & _LUGARES_DE_LA_PIEZA
            _lugar_b = (pieza_b - pieza_a) & _LUGARES_DE_LA_PIEZA
            if _lugar_a and _lugar_b:
                return False, (f"piezas de lugares distintos: {'/'.join(sorted(_lugar_a))} "
                               f"vs {'/'.join(sorted(_lugar_b))}")
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

    # SOLO LA MARCA NO ES CONCORDAR. «SONDA LAMBDA ... Ford largo del cable 92 cm» contra «SONDA
    # LAMBDA 80014 FORD ESCORT MONDEO ...» coinciden en la pieza y en FORD, y nada más: con las
    # listas de FISPA, que nombran veinte autos, eso lo cumple casi cualquier sonda. No es una
    # contradicción —puede ser la misma—, pero tampoco es evidencia a favor: hace falta un
    # modelo o un motor en común.
    _en_comun = ({w for w in autos_comunes if w not in _PALABRAS_DE_MARCA_DE_VEHICULO}
                 | set(apl_comunes))
    # El modelo que es un número cuenta aunque no venga pegado a la marca: «FIAT 1600 125»
    # contra «FIAT 125». Es el mismo criterio que «modelos distintos», más arriba.
    if not _en_comun:
        _txt_a, _txt_b = a.get("texto") or "", b.get("texto") or ""
        _en_comun = ({n for n in (a.get("modelos_numericos") or set())
                      if re.search(rf'\b{re.escape(n)}\b', _txt_b)}
                     | {n for n in (b.get("modelos_numericos") or set())
                        if re.search(rf'\b{re.escape(n)}\b', _txt_a)})
    if not _en_comun:
        _en_comun = (a.get("motores_numericos") or set()) & (b.get("motores_numericos") or set())
    if not _en_comun:
        # Y SI LAS DOS NOMBRAN MODELOS Y NO COMPARTEN NINGUNO, no es «falta un dato»: dicen para
        # qué autos son, y son otros. «Sonda Lambda Volkswagen Gol Fox Voyage Saveiro Suran»
        # contra la LUCAS de «GM Astra Celta Corsa … VW Golf» compartían VOLKSWAGEN y nada más,
        # y la cola la dejaba en 50, «dudosa», como si no se supiera. De los 3.595 dudosos de la
        # cola, 156 eran esto. Las marcas que hacen motores para otras (Perkins, MWM…) no
        # cuentan: ahí un lado nombra el motor y el otro el vehículo.
        _mod_a, _mod_b = a.get("modelos") or set(), b.get("modelos") or set()
        if (_mod_a and _mod_b and not _modelos_en_comun(_mod_a, _mod_b)
                and not ({a.get("marca_auto"), b.get("marca_auto")} & _MARCAS_DE_MOTORES)):
            return False, (f"modelos distintos: {'/'.join(sorted(_mod_a)[:2])} "
                           f"vs {'/'.join(sorted(_mod_b)[:2])} (misma marca, ningún modelo "
                           "en común)")
        return False, "solo comparten la marca del auto"

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
                            "distinta cantidad de vías", "juegos distintos",
                            "largo de cable distinto", "temperaturas distintas",
                            "carburadores distintos", "piezas de lugares distintos",
                            "sensores de tipos distintos", "bujías de tipos distintos",
                            "distinta cantidad de cilindros", "motores de distintas válvulas",
                            "años distintos", "motores distintos",
                            "sobremedida distinta", "presiones distintas",
                            "aros de distinto color", "medidas distintas",
                            "versiones distintas",
                            "combustibles distintos")
# Los que no alcanzan para decir que son piezas distintas pero sí para desconfiar: no vetan
# (el par va a revisión, no a rojo) y se muestran como el porqué. Ver evidencia_cruzada().
_MOTIVOS_QUE_AVISAN = ("un nombre de modelo de marcas distintas", "el mismo auto con otra cilindrada",
                       "un juego de juntas de", "el largo de cable se parece",
                       "una de las dos no dice")
# Los que hablan del AUTO. Esos no cuentan cuando el par está unido por un código: ver
# _unidos_por_codigo().
_MOTIVOS_DEL_AUTO = ("autos distintos", "marcas distintas", "modelos distintos",
                     "cilindradas distintas", "motores de distintas válvulas", "años distintos",
                     "motores distintos", "combustibles distintos")


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
        # Y como FISPA cita a CRI-FA: «SENSOR MAP 40055 MERCEDES … REF ORIG T7148» es el
        # 14-R7148 de CRI-FA. Salía en rojo por «modelos distintos» (Sprinter contra Clase A).
        _cri = re.fullmatch(r"\d{2}R(\d{4,6})", codigo)
        if _cri and re.search(rf"\bT{_cri.group(1)}\b", (otro.get("descripcion") or "").upper()):
            return True
    return False

"""Todo lo que tiene que ver con LIMPIAR y RECONOCER códigos de repuesto.

Es el corazón del sistema y no depende de nada: ni de la base, ni de la interfaz, ni de cómo se
leyó el archivo. Se puede probar con strings sueltos.

El orden importa: primero se decide si algo ES un código (sanitizar, es_codigo_util), después
se parte una celda que trae varios (dividir_codigos), y recién al final se intenta adivinar
códigos escondidos adentro de una descripción (extraer_codigos_de_texto), que es lo más
delicado porque ahí se está SUPONIENDO."""
import re
import unicodedata
from collections import Counter

from .errores import anotar_error


# ============================================================
# UTILIDADES
# ============================================================
def es_fecha_disfrazada(valor):
    """¿Esta celda es una fecha que en realidad era un código?

    Pasa todo el tiempo y en silencio: el proveedor abre la lista en Excel, y códigos como
    '12-15', '3/8' o '8-10' se convierten solos en fechas al guardar. Después llegan acá como
    una fecha de verdad, y limpiarlas normalmente da '20261215000000' — un código que no existe
    y que no va a coincidir con nada, sin que nadie se entere de por qué."""
    import datetime as _dt
    return isinstance(valor, (_dt.datetime, _dt.date))


def sanitizar(codigo):
    """Limpia un código dejando solo letras y números en mayúscula.

    Ojo con el '.0' del final: Excel guarda los códigos numéricos como número, así que
    '2776400' llega como '2776400.0'. Si no se saca antes de limpiar, queda '27764000'
    (un cero de más) y ese producto se vuelve imposible de encontrar por su código real.

    Y ojo también con la notación científica: un código largo que Excel muestra como
    '1.09E+11' limpiado a lo bruto queda '109E11', que no es ningún código."""
    if codigo is None:
        return ""
    if es_fecha_disfrazada(codigo):
        # Se devuelve vacío a propósito: es preferible que la fila se saltee y quede contada
        # como problema, antes que cargar un código inventado de 14 dígitos que nunca va a
        # coincidir con nada. El aviso al importar explica cómo arreglar el archivo.
        return ""
    codigo = str(codigo).strip()
    if codigo == "" or codigo.lower() == "nan":
        return ""
    if re.fullmatch(r"\d+\.0+", codigo):
        codigo = codigo.split(".")[0]
    # Notación científica: se pasa al número entero que representa.
    # El signo del exponente es OBLIGATORIO, y ahí está toda la diferencia. Excel siempre
    # escribe '1.09E+11' o '2.7E-05' —nunca sin el + o el −—, mientras que los códigos de
    # fábrica que TIENEN una E en el medio no lo llevan: '233900E010' es el filtro de
    # combustible Toyota 23390-0E010, y sin exigir el signo se convertía en el número
    # 2339000000000000. Ese producto quedaba imposible de encontrar por su código real, y sus
    # equivalencias apuntaban a un código que no existe.
    # Se cuentan 283 apariciones de esa forma dentro de las descripciones de cinco listas
    # reales, y CERO notaciones científicas de Excel de verdad: exigir el signo no cuesta nada
    # y salva las 283.
    # La coma también entra como separador decimal: '2,7E-05' es lo que sale de un Excel en
    # español, y sin contemplarla caía en la limpieza a lo bruto y quedaba '27E05'.
    if re.fullmatch(r"\d+([.,]\d+)?[Ee][+-]\d+", codigo):
        try:
            entero = int(float(codigo.replace(",", ".")))
            if abs(float(codigo.replace(",", ".")) - entero) < 1e-6:
                codigo = str(entero)
        except (ValueError, OverflowError) as _err:
            anotar_error("sanitizar", _err)
            pass
    return re.sub(r'[^A-Z0-9]', '', codigo.upper())


LARGO_MINIMO_NUMERICO = 3


def es_codigo_util(texto):
    """¿Vale la pena cargar esto como código? Descarta lo que es solo 1 o 2 dígitos y nada más
    ('1', '12', '07', '3.0', '  2  ').

    Por qué: en muchas listas la columna de código trae metida la cantidad, el número de orden
    o la cantidad por bulto. Cada uno de esos números entraba como si fuera un producto, y como
    la app vincula todo lo que aparece en la misma fila, el '1' de una fila terminaba siendo
    "equivalente" al '1' de otra — y con eso, dos repuestos que no tienen nada que ver quedaban
    linkeados entre sí. Un solo número basura arrastra decenas de equivalencias falsas.

    Un código con al menos una letra se acepta aunque sea corto (A1, B2 existen de verdad)."""
    limpio = sanitizar(texto)
    if not limpio:
        return False
    if limpio.isdigit() and len(limpio) < LARGO_MINIMO_NUMERICO:
        return False
    # Tampoco entran los de DOS caracteres, tengan letra o no ("1S", "A1", "2S").
    # Esto estaba incoherente: la importación los dejaba pasar, y después la revisión marcaba
    # cada vínculo suyo con «es demasiado corto para ser un código». Con un solo "1S" de
    # IMPERIAL eso son cientos de pendientes con la misma alarma, uno por cada fila donde
    # apareció. Si el propio análisis dice que no es un código, no tiene por qué entrar.
    if len(limpio) < 3:
        return False
    return True


def _partir_por_barra(trozo):
    """La barra es el caso jodido: a veces separa dos códigos y a veces es PARTE del código.
    'W712/94' y 'WK842/2' son códigos Mann enteros, un filtro solo — partirlos ahí generaba dos
    productos falsos ('W712' y '94') y encima los dejaba vinculados entre sí como si fueran
    equivalentes. Pero '1109AN/1109AB' sí son dos códigos.

    La diferencia práctica: cuando la barra separa de verdad, los dos lados son códigos completos.
    Cuando es parte del código, del otro lado queda un numerito corto (el sufijo de la variante).
    Con espacios alrededor ('ABC / DEF') es separador seguro."""
    if "/" not in trozo:
        return [trozo]
    if re.search(r'\s/|/\s', trozo):          # 'ABC / DEF' → separador
        return [p for p in re.split(r'\s*/\s*', trozo) if p]
    partes = [p for p in trozo.split("/") if p]
    for parte in partes:
        limpio = sanitizar(parte)
        if limpio.isdigit() and len(limpio) <= 3:   # sufijo de variante: es un solo código
            return [trozo]
    return partes


def dividir_codigos(celda):
    """Separa una celda que puede traer varios códigos juntos (coma, punto y coma, barra, salto
    de línea). De paso descarta los pedazos que no son un código (ver es_codigo_util)."""
    if celda is None:
        return []
    texto = str(celda).strip()
    if texto == "" or texto.lower() == "nan":
        return []
    salida = []
    for trozo in re.split(r'[,;\n|]+', texto):
        trozo = trozo.strip()
        if not trozo:
            continue
        for parte in _partir_por_barra(trozo):
            parte = parte.strip()
            if parte and es_codigo_util(parte):
                salida.append(parte)
    return salida


# Piezas que se identifican POR SU MEDIDA: en retenes, o'rings, rulemanes y bujes, la medida
# ES el código. Un retén Taranto se pide como "35x52x7" y así figura en el catálogo.
_RE_PIEZA_POR_MEDIDA = re.compile(
    r'\b(RETEN|RETENES|O.?RING|ORING|ANILLO|JUNTA\s+TORICA|SELLO|BUJE|BUJES|'
    r'RULEMAN|RODAMIENTO|ARANDELA|ESPACIADOR|SEPARADOR)\b', re.I)


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


# Cuántas filas de la MISMA lista puede aparecer un código sacado de la descripción antes de
# que se lo considere texto y no código. Medido sobre dos listas reales (5.063 y 25.875 filas):
# los códigos de fábrica verdaderos (0221504036, 03C906433A, IWP065, 46474600, 90919-C2003)
# aparecen 1 o 2 veces cada uno — como mucho el mismo repuesto en dos presentaciones. Lo que
# se repite más es siempre texto: motorizaciones (TU5JP4, DW10BTED4), modelos (CLA200, SLK230),
# o muletillas del proveedor (16VREF aparecía 130 veces). Con el tope en 4 se conservan los 9
# códigos reales que había y se van los 12 que más daño hacían.
TOPE_REPETICIONES_EN_DESCRIPCION = 4


def codigos_confiables_de_descripciones(descripciones, tope=TOPE_REPETICIONES_EN_DESCRIPCION):
    """De todos los códigos que se pueden sacar de las descripciones de una lista, devuelve
    solo los que NO se repiten demasiado.

    'descripciones' son pares (texto, código de esa misma fila): el código propio hace falta
    para descartar el caso de la palabra pegada, ver extraer_codigos_de_texto().

    Por qué hace falta mirar la lista entera y no fila por fila: 'CLA200' e 'IWP065' tienen
    exactamente la misma forma —tres letras y tres números— y no hay expresión regular que
    distinga el modelo de Mercedes del inyector de Magneti Marelli. Lo que sí los distingue es
    cuántas veces aparecen: el inyector está en 2 filas, el modelo en 15.

    Y el repetido es justo el que hace daño, porque el daño crece al cuadrado: un código que
    aparece 1 vez en cada lista genera 1 equivalencia falsa, pero uno que aparece 130 veces
    genera cientos, y cada una vincula dos repuestos que no tienen nada que ver. Sacar los
    repetidos no es prolijidad: es lo único que evita que activar esta opción ensucie la base
    más de lo que la llena."""
    conteo = Counter()
    for texto, codigo_propio in descripciones:
        # set() por fila: si la misma descripción nombra dos veces el mismo código, cuenta una.
        # Lo que se está midiendo es en cuántos PRODUCTOS distintos aparece, no cuántas veces.
        for cod in set(sanitizar(c) for c in extraer_codigos_de_texto(texto, codigo_propio=codigo_propio)):
            if cod:
                conteo[cod] += 1
    return {cod for cod, veces in conteo.items() if veces <= tope}, conteo


def _es_el_codigo_propio_con_texto(candidato, propio):
    """¿'candidato' es 'propio' con una palabra pegada atrás? Ver extraer_codigos_de_texto()."""
    iguales = 0
    for a, b in zip(candidato, propio):
        if a != b:
            break
        iguales += 1
    if iguales < 3:
        return False
    resto = candidato[iguales:]
    return bool(resto) and resto.isalpha()


def extraer_codigos_de_texto(texto, minimo=6, codigo_propio=None):
    """Busca códigos de fábrica escondidos dentro de una descripción.
    Muchas listas de proveedor no traen una columna de OEM aparte, pero lo meten en el texto
    ('ROTULA VW GOL - ORIG 6Q0407365'). Esto lo saca de ahí.
    Es a propósito conservador — ante la duda, no lo toma — porque un código inventado ensucia
    la base con equivalencias falsas, que es peor que no tener la equivalencia:
      - descarta palabras sin números (ROTULA, DERECHA, DELANTERO)
      - descarta números solos cortos: años, medidas, cilindradas (2005, 1.6, 16V)
      - pide un largo mínimo, porque los códigos de fábrica son largos
    """
    if not texto:
        return []
    propio = sanitizar(codigo_propio) if codigo_propio else ""
    ruido = {"16V", "8V", "12V", "24V", "4X4", "4X2", "2WD", "4WD", "TDI", "TSI", "CRDI",
             "16valv", "MM", "CM", "KG"}

    # Formas que NO son códigos de repuesto y aparecen todo el tiempo en las descripciones.
    # Se aplican SOLO acá, cuando el código se está adivinando de un texto. Si el proveedor lo
    # puso en la columna del código, es un código y se respeta: la exigencia va donde estamos
    # suponiendo, no donde nos lo dijeron.
    formas_prohibidas = (
        # Códigos de MOTOR: letras, números y letras al final. MR20DE, B4204S, Z18XER, X20XEV,
        # DV6DTED, MT560B. Describen la motorización del auto, no la pieza — y como se repiten
        # en decenas de filas, cada uno vincula entre sí todo lo que lo menciona.
        # Se midió sobre 4.340 códigos extraídos de una lista real: descarta 36, y los 36 son
        # códigos de motor. El 1% de pérdida vale, porque cada uno de esos generaba decenas de
        # equivalencias falsas.
        re.compile(r'^[A-Z]{1,3}\d{1,5}[A-Z]{1,4}$'),
        # Medidas: 14X20X1, 7,5X12X5, y con la unidad pegada: 32X18X105MM
        re.compile(r'^\d+([.,]\d+)?X\d+([.,]\d+)?(X\d+([.,]\d+)?)?(MM|CM|M)?$'),
        # Cilindradas y potencias sueltas: 1.6, 2.0TDI, 110CV
        re.compile(r'^\d[.,]\d[A-Z]*$'),
        re.compile(r'^\d+(CV|HP|KW|CC)$'),
        # RANGOS DE AÑOS: 1998-2006, 2012/2015, 1995-96. Es el peor de todos los falsos códigos
        # y el más común, porque casi toda descripción de repuesto dice para qué años sirve.
        # Se midió sobre dos listas reales (5.063 y 25.875 filas): de los 224 "códigos" que las
        # dos tenían en común, 163 eran rangos de años. Y no es que no sirvieran: activamente
        # rompían. "2003-2008" aparecía en 12 filas de una lista y 6 de la otra, o sea que solo
        # ese texto declaraba 72 equivalencias falsas entre repuestos que no tienen nada que
        # ver — un filtro de aceite "equivalente" a un sensor porque los dos van en autos de
        # esos años. Un código así no aporta un vínculo malo: aporta cientos.
        re.compile(r'^(19|20)\d{2}[-/](19|20)?\d{2}$'),
        # LISTAS DE MODELOS con números cortos: 205-206-306, 106-206-306, 206-306-307. Son las
        # familias de Peugeot/Citroën enumeradas en la descripción. Un código de fábrica con
        # guiones tiene partes largas (1234-5678); estas son todas de 3 dígitos o menos.
        re.compile(r'^\d{1,3}([-/]\d{1,3})+$'),
        # NOMBRES DE MODELO con guion: 4-RUNNER, 9-RENAULT, 10-BLAZER, BLAZER-S10, 206-PARTNER.
        # La marca de que es texto y no código: uno de los lados es una palabra entera de 4
        # letras o más, sin un solo número. Los códigos reales con guion llevan prefijos cortos
        # (MD-12345, A-4567), nunca una palabra.
        re.compile(r'^([A-Z0-9]+[-])*[A-Z]{4,}([-][A-Z0-9]+)*$'),
        # MOTORES japoneses, que empiezan con número: 2AZ-FE, 2GD-FTV, 1KD-FTV, 4G63.
        # El de arriba no los agarra porque arrancan con dígito. Se vio que juntaban una
        # válvula VVT con una sonda lambda, y una bujía con un kit de embrague: lo único que
        # comparten es que van en el mismo motor.
        re.compile(r'^\d[A-Z]{2}[-]?[A-Z]{2,3}$'),
        # MODELOS de BMW/Mercedes enumerados: 320I-323I, 320D-330D. Unían un MAF de Kia con
        # una tapa de BMW.
        re.compile(r'^\d{3}[A-Z][-]?\d{3}[A-Z]$'),
        # MEDIDAS DE CORREA: 6PK1555, 4PK850, 10X1075. Es la medida de la correa, no el código
        # del repuesto — y aparece adentro de la descripción de cualquier kit que la incluya,
        # así que juntaba una bomba de agua con una correa suelta.
        re.compile(r'^\d{1,2}PK\d{3,4}$'),
        re.compile(r'^\d{1,2}X\d{3,4}$'),
        # MOTORES de PSA (Peugeot/Citroën), que son los que más aparecen en las listas de acá:
        # TU5JP4, XU7JP4, EW10J4, DW10BTED4, XUD9. La forma es dos letras, número, letras,
        # número — nunca la de un código de repuesto, que no alterna así.
        # Juntaban un termostato con un sensor de RPM, y un sensor de rotación con un bidón
        # recuperador: comparten el motor y nada más.
        # Ojo que esto NO puede tocar los códigos reales de tres letras + números (IWP044,
        # H3T021, MAF069): por eso pide exactamente dos letras al principio y letras DESPUÉS
        # del primer número, cosa que un código de repuesto no tiene.
        # La letra final de más cubre XU10J4R, DJ5T12V, TU3F2K y EP6CDTMD, que son la misma
        # familia. XU10J4R llegó a colgar 6 productos de tres proveedores distintos: una junta
        # de tapa de Peugeot 405, un juego de reparación y una tapa de cilindros — todo lo que
        # menciona ese motor, "equivalente" entre sí.
        re.compile(r'^[A-Z]{2}\d{1,2}[A-Z]{1,4}\d{0,2}[A-Z]?$'),
        # NÚMERO CON UNA PALABRA PEGADA: 24Amperes, 1990BOSCH, 16VREF, 7LDIESEL, 4RUNNER,
        # 1600CCAPTO. Sale de la descripción cuando la exportación se come el espacio, y de acá
        # salían los peores puentes de todos: '16VREF' aparecía en 130 filas de una sola lista,
        # y '4RUNNER' terminó uniendo una bobina de ignición, un sensor de masa de aire de Mazda
        # y un sensor de temperatura de Corolla — tres repuestos que no tienen nada que ver,
        # hermanados porque el texto nombra la misma camioneta.
        # Medido sobre las cinco listas reales: saca 639 códigos falsos y no rompe ninguno de
        # los verdaderos. Un código de fábrica no termina en una palabra entera; termina en una
        # letra o dos (03C906433A, 55575988CA), y eso queda a salvo porque acá se piden cuatro.
        re.compile(r'^\d+[A-Z]{4,}$'),
        # LISTAS DE MODELOS pegadas: A3A4A6, 206306307. Salen de "AUDI A3-A4-A6" y son el
        # equivalente de los rangos de años, con el mismo daño.
        re.compile(r'^([A-Z]\d[-]?){3,}$'),
    )
    # Palabras de la descripción que quedan pegadas al año y disfrazan el rango:
    # 'DESDE1993', 'HASTA2005', 'MODELO2010'.
    arranques_de_texto = ("DESDE", "HASTA", "PARA", "MODELO", "MEDIDA", "ORIGEN", "SERIE")
    # Algunas listas traen la descripción con HTML adentro ('LRSC108197<b>DAEWOO</b>' o
    # '0001115005<br>BOSCH'). Sin sacarlo, la etiqueta queda pegada al número y el código sale
    # deformado: '0001115005BRBOSCH' en vez de '0001115005'.
    texto = re.sub(r'<[^>]{1,30}>', ' ', str(texto))
    # Muletillas que el proveedor pega al código cuando la exportación se come el espacio:
    # 'REF ORIGINALES 0360601402' llega como 'ORIGINALES0360601402'. Se despega la palabra en
    # vez de descartar el token, porque lo que viene atrás es el código de fábrica de verdad.
    texto = re.sub(r'(ORIGINALES|ORIGINAL|ORIG|REF|CODIGO|COD|EQUIV)(?=\d{5,})', r'\1 ',
                   texto, flags=re.IGNORECASE)

    encontrados = []
    for token in re.split(r'[\s,;/|()\[\]<>]+', str(texto)):
        limpio = token.strip().strip(".-_")
        if len(limpio) < minimo:
            continue
        if limpio.upper() in ruido:
            continue
        if any(p.match(limpio.upper()) for p in formas_prohibidas):
            continue
        if limpio.upper().startswith(arranques_de_texto):
            continue
        # Un '?' adentro del token es texto que se rompió al exportar (acentos, comillas o
        # símbolos que se perdieron): '118?CREF' salía de '1.18 °C REF'. No es un código.
        if "?" in limpio or "\ufffd" in limpio:
            continue
        if not any(ch.isdigit() for ch in limpio):
            continue
        tiene_letra = any(ch.isalpha() for ch in limpio)
        # Números sueltos: solo se aceptan si son largos (un código de barras o de fábrica),
        # así no se cuelan años ni medidas
        if not tiene_letra and len(re.sub(r'\D', '', limpio)) < 7:
            continue
        # Descartar cosas tipo "1.6" o "2.0TDI" que empiezan con cilindrada
        if re.match(r'^\d\.\d', limpio):
            continue
        # El largo mínimo va sobre el código LIMPIO, no sobre el token con su puntuación.
        # 'TDI-A6' son seis caracteres y pasaba, pero el código que quedaba era 'TDIA6', que
        # son cinco: demasiado corto para ser un código de fábrica y suficiente para chocar con
        # cualquier cosa. De ahí salían puentes como 'Aveo5:', '16V-KA' y '1000-F', que en la
        # base real estaban uniendo una dirección con una refrigeración y una distribución con
        # un encendido — familias enteras hermanadas por un pedazo de texto.
        # Los códigos reales de seis caracteres (IWP044, H3T021, TPRT04) no se pierden: seis
        # limpios siguen siendo seis.
        codigo_limpio = sanitizar(limpio)
        if len(codigo_limpio) < minimo:
            continue
        # El código de la propia fila con una palabra pegada atrás NO es un código de fábrica.
        # Pasa cuando el proveedor exporta y se le come el espacio: la fila 52031FISPA tiene de
        # descripción "FICHA DE INYECCION 52031Ficha para Bomba de Nafta BOSCH", y de ahí salía
        # "52031Ficha" como si fuera un OEM. Sobre la lista real eran 4.443 de 5.063 filas:
        # 4.443 productos fantasma bajo la marca OEM, uno por fila, que no cruzaban con nada
        # (son únicos) pero aparecían en cada búsqueda y hacían que la importación informara
        # miles de "equivalencias" que no existían.
        # Se pide que lo que sobra sean SOLO letras: así se saca la palabra pegada
        # (52031+Ficha, 24075+VW) y no se tocan las variantes reales de un mismo código, que se
        # diferencian por números o por letra y número (FLO35121 / FLO35122 / FLO35122A).
        if propio and _es_el_codigo_propio_con_texto(sanitizar(limpio), propio):
            continue
        encontrados.append(limpio)
    # sin repetidos, conservando el orden
    vistos, salida = set(), []
    for cod in encontrados:
        clave = sanitizar(cod)
        if clave not in vistos:
            vistos.add(clave)
            salida.append(cod)
    return salida


# ============================================================
# COMBOS DE REPUESTOS RELACIONADOS (ej: correa de distribución -> kit + tensor + bomba de agua)
# ============================================================
def normalizar_texto(texto):
    """Mayúsculas y sin acentos, para poder comparar 'distribución' con 'distribucion'."""
    texto = texto or ""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return texto.upper().strip()


def valor_o_vacio(valor):
    """Devuelve el valor de una celda como texto, o '' si está vacía.

    Le saca el '.0' que Excel le agrega a los códigos numéricos. Esto no es cosmético: el
    código que se guarda acá es el que después se MUESTRA y se copia en un presupuesto o en un
    mensaje de WhatsApp. Guardarlo como '2776400.0' significa mandarle al cliente un código que
    no existe. La búsqueda igual funcionaba porque sanitizar() lo limpiaba, así que el problema
    pasaba desapercibido hasta que alguien copiaba el código de la pantalla."""
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    texto = str(valor).strip()
    if re.fullmatch(r"\d+\.0+", texto):
        return texto.split(".")[0]
    return texto


def valor_codigo(valor):
    """Lee una celda que TIENE que ser un código. Devuelve '' si es una fecha.

    Va aparte de valor_o_vacio a propósito. La detección de fechas tiene que hacerse sobre la
    celda cruda, ANTES de pasarla a texto: una vez convertida ya es '2026-12-15 00:00:00' y no
    hay forma de distinguirla de un código raro. Ese era el agujero — el chequeo estaba puesto
    más adelante en la cadena, cuando el dato ya se había perdido."""
    if es_fecha_disfrazada(valor):
        return ""
    return valor_o_vacio(valor)

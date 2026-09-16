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


def es_fecha_disfrazada(valor):
    """¿Esta celda es una fecha que en realidad era un código?

    Pasa todo el tiempo y en silencio: el proveedor abre la lista en Excel, y códigos como
    '12-15', '3/8' o '8-10' se convierten solos en fechas al guardar. Después llegan acá como
    una fecha de verdad, y limpiarlas normalmente da '20261215000000' — un código que no existe
    y que no va a coincidir con nada, sin que nadie se entere de por qué."""
    import datetime as _dt
    return isinstance(valor, (_dt.datetime, _dt.date))


# ============================================================
# CÓDIGOS: limpiar, reconocer, partir y sacarlos de una descripción
# ============================================================
def como_texto_en_like(texto):
    """Prepara un texto para meterlo adentro de un LIKE, sin que se lo coman los comodines.

    En SQL, «%» significa «cualquier cosa» y «_» significa «un carácter cualquiera». Si eso
    llega desde el buscador, la consulta deja de buscar lo que se escribió:

        buscar «100%»    -> 200 resultados cualesquiera (el tope), ninguno tiene que ver
        buscar «f_ltro»  -> lo mismo
        buscar «%»       -> devuelve el catálogo entero

    Y no son textos raros: «aceite 100% sintético» es lo que dice la caja. Medido sobre el
    catálogo real: los tres casos de arriba devolvían las 200 filas del tope.

    Se escapa también la barra invertida, porque es el carácter de escape que se usa después
    en la cláusula ESCAPE. Quien use esto tiene que agregar ESCAPE '\\' a su LIKE."""
    return (str(texto or "").replace("\\", "\\\\")
            .replace("%", "\\%").replace("_", "\\_"))


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
    # 'c/', 's/', 'p/' son abreviaturas de "con", "sin" y "para", no separadores. JL escribe
    # «208.856 C/PVC» y «23 8130R c/soporte»: el código es 208.856 y lo de atrás aclara con qué
    # viene. Partiéndolo se cargaban DOS productos, uno con el código mutilado y otro llamado
    # «PVC» o «soporte» — y ese segundo es lo peor, porque un código así se cuelga después de
    # todo lo que mencione PVC y fusiona familias que no tienen nada que ver.
    if re.search(r'(?i)(?:^|[\s\-])[cspx]/\S', trozo):
        return [trozo]
    if re.search(r'\s/|/\s', trozo):          # 'ABC / DEF' → separador
        return [p for p in re.split(r'\s*/\s*', trozo) if p]
    # Una barra con un número pegado de los DOS lados es una fracción, o sea una medida metida
    # adentro del código: 1/2", 3/8, 7/16. IMPERIAL vende ferretería y los usa por todos lados
    # —«H21A1/2"RF1,5» es una abrazadera de media pulgada— y se partía en 'H21A1' y '2"RF1':
    # dos códigos que no existen, y el producto real desaparecía.
    if re.search(r'\d/\d', trozo):
        return [trozo]
    partes = [p for p in trozo.split("/") if p]
    for parte in partes:
        limpio = sanitizar(parte)
        # Un pedazo corto es un SUFIJO DE VARIANTE, no un código aparte. Antes solo se
        # contemplaba el sufijo numérico ('W712/94'), pero los de letras son igual de comunes:
        # 'SABO-02233/BRG', 'RODGE-MINI/10F'. Cuando la barra separa dos códigos de verdad
        # —'1109AN/1109AB'— los dos lados son completos, así que exigir largo de los dos es lo
        # que distingue un caso del otro.
        if len(limpio) <= 4:
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
    # La coma entre dos dígitos es el separador DECIMAL, no una lista. Es la coma argentina:
    # «RHEIN-CCSP-20,5» es un código, no los códigos «RHEIN-CCSP-20» y «5». Cortando ahí pasaban
    # dos cosas, y la segunda es la grave: el código quedaba mutilado, y como el sufijo era lo
    # único que los distinguía, «RHEIN-CCSP-20,5» y «RHEIN-CCSP-20,0» terminaban siendo el mismo
    # código y uno pisaba al otro — un producto entero desaparecía del catálogo sin aviso.
    # Sobre una lista real son 3.811 códigos.
    # Se protege reemplazando la coma decimal por un marcador antes de cortar, y devolviéndola
    # después: así el resto de la función sigue partiendo por comas de verdad.
    texto = re.sub(r'(?<=\d),(?=\d)', "\x00", texto)
    for trozo in re.split(r'[,;\n|]+', texto):
        trozo = trozo.replace("\x00", ",")
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


# Cuántas filas de la MISMA lista puede aparecer un código sacado de la descripción antes de
# que se lo considere texto y no código. Medido sobre dos listas reales (5.063 y 25.875 filas):
# los códigos de fábrica verdaderos (0221504036, 03C906433A, IWP065, 46474600, 90919-C2003)
# aparecen 1 o 2 veces cada uno — como mucho el mismo repuesto en dos presentaciones. Lo que
# se repite más es siempre texto: motorizaciones (TU5JP4, DW10BTED4), modelos (CLA200, SLK230),
# o muletillas del proveedor (16VREF aparecía 130 veces). Con el tope en 4 se conservan los 9
# códigos reales que había y se van los 12 que más daño hacían.
TOPE_REPETICIONES_EN_DESCRIPCION = 4


def codigos_confiables_de_descripciones(descripciones, tope=TOPE_REPETICIONES_EN_DESCRIPCION,
                                        codigos_conocidos=None):
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
        # El mismo juego de códigos conocidos que va a usar la importación. Si acá se contara
        # con otro criterio, el recuento y la extracción real no hablarían del mismo conjunto:
        # un código rescatado al importar no estaría en la lista de confiables y se tiraría
        # igual, que es peor que no rescatarlo — parecería que el arreglo no hizo nada.
        for cod in set(sanitizar(c) for c in extraer_codigos_de_texto(
                texto, codigo_propio=codigo_propio, codigos_conocidos=codigos_conocidos)):
            if cod:
                conteo[cod] += 1
    return {cod for cod, veces in conteo.items() if veces <= tope}, conteo


# Cuando el proveedor ESCRIBE que lo que sigue es el código de fábrica. Ahí ya no estamos
# adivinando: nos lo están diciendo, y las reglas que existen para adivinar tienen que aflojarse.
_MARCADORES_DE_OEM = {"//", "ORIG", "ORIG.", "ORIGINAL", "ORIGINALES", "OEM", "EQUIV",
                      "EQUIVALE", "REEMPLAZA", "CROSS", "N°ORIG", "NºORIG", "REF.ORIG"}


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


# Marcas que los proveedores pegan atrás de su propio número: «LSPFR6F11LUCAS», «26001FISPA».
# Se calculan una vez y no se leen de la base: son el nombre de la marca del producto, y la
# consulta que las necesita corre una vez por búsqueda.
_MARCAS_QUE_SE_PEGAN_AL_CODIGO = ("LUCAS", "FISPA", "BOSCH", "MARELLI", "MAGNETI", "VALEO",
                                  "DELPHI", "NGK", "GATES", "SKF", "BERU", "FACET")


def _es_lista_de_modelos(token):
    """«106-206-306-406-607» no es un código: es la lista de modelos a los que le va la pieza.

    Las listas las escriben así y son de los peores códigos inventados que hay, porque cada uno
    cuelga de sí mismo todo lo que nombre esos autos. Se piden tres segmentos de TRES dígitos
    —que es como se numeran los Peugeot, los BMW y los Mercedes— y ninguno de más de cuatro
    caracteres, y ahí está el cuidado: los códigos de fábrica con guiones tienen algún segmento
    largo («8-01115-315-0» de Isuzu, «7700747549-7700850589» de Renault) o no llegan a tres
    segmentos de tres dígitos («06K-905-601-B» de VW).

    Medido contra los 70.888 códigos del catálogo real: marca 25 y los 25 son listas de modelos
    («316-318-320-325-330-520-530-540-X3-X5-Z3-Z4», «1214-1215-1315-1615-1620-608-912-913»)."""
    partes = (token or "").split("-")
    if len(partes) < 3 or any(not p or len(p) > 4 for p in partes):
        return False
    return sum(1 for p in partes if p.isdigit() and len(p) == 3) >= 3


def extraer_codigos_de_texto(texto, minimo=6, codigo_propio=None, codigos_conocidos=None):
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
    # Los códigos que YA están en el catálogo. Es el desempate para las formas ambiguas de más
    # abajo: esos patrones existen para tirar designaciones de motor (MR20DE, Z18XER), y una
    # designación de motor no es algo que alguien venda. Si el token coincide exactamente con
    # el código de un producto cargado, entonces es un código de repuesto, se llame como se
    # llame.
    # Hacía falta: medido contra los 39.746 códigos reales del catálogo, el patrón de
    # "código de motor" (^[A-Z]{1,3}\d{1,5}[A-Z]{1,4}$) le pega a 672 de ellos —bujías CT5FMR,
    # capuchones RB9009B— y el de motores PSA a otros 52. Todos esos se perdían cuando
    # aparecían nombrados adentro de la descripción de otro proveedor, que es justo el momento
    # en que servían para cruzar las dos listas.
    # Y no reabre la puerta a lo que se cerró: de 30 designaciones de motor conocidas
    # (Z18XER, XU10J4R, MR20DE, 4G63, K9K, OM646...), ninguna existe como código de producto.
    conocidos = codigos_conocidos or ()
    ruido = {"16V", "8V", "12V", "24V", "4X4", "4X2", "2WD", "4WD", "TDI", "TSI", "CRDI",
             "16valv", "MM", "CM", "KG"}

    # Formas que NO son códigos de repuesto y aparecen todo el tiempo en las descripciones.
    # Se aplican SOLO acá, cuando el código se está adivinando de un texto. Si el proveedor lo
    # puso en la columna del código, es un código y se respeta: la exigencia va donde estamos
    # suponiendo, no donde nos lo dijeron.
    # AMBIGUAS: aciertan casi siempre, pero la misma forma la tienen códigos de repuesto de
    # verdad —ERR4685B es un número de Land Rover, no un motor—, así que dejan de aplicarse
    # cuando el proveedor DECLARÓ que lo que sigue es el código de fábrica.
    formas_ambiguas = (
        # Códigos de MOTOR: letras, números y letras al final. MR20DE, B4204S, Z18XER, X20XEV,
        # DV6DTED, MT560B. Describen la motorización del auto, no la pieza — y como se repiten
        # en decenas de filas, cada uno vincula entre sí todo lo que lo menciona.
        # Se midió sobre 4.340 códigos extraídos de una lista real: descarta 36, y los 36 son
        # códigos de motor. El 1% de pérdida vale, porque cada uno de esos generaba decenas de
        # equivalencias falsas.
        re.compile(r'^[A-Z]{1,3}\d{1,5}[A-Z]{1,4}$'),
        # MOTORES de PSA con letra final: XU10J4R, DJ5T12V, TU3F2K, EP6CDTMD. XU10J4R llegó a
        # colgar 6 productos de tres proveedores: una junta de tapa de Peugeot 405, un juego de
        # reparación y una tapa de cilindros — todo lo que menciona ese motor. Va acá porque
        # comparte el problema de arriba: la misma forma la tiene un código real.
        re.compile(r'^[A-Z]{2}\d{1,2}[A-Z]{1,4}\d{0,2}[A-Z]?$'),
    )
    # Y estas son texto sin discusión: un rango de años o una medida no dejan de serlo porque
    # el proveedor los haya escrito después de un «ORIG».
    formas_solo_texto = (
        # Medidas: 14X20X1, 7,5X12X5, y con la unidad pegada: 32X18X105MM
        re.compile(r'^\d+([.,]\d+)?X\d+([.,]\d+)?(X\d+([.,]\d+)?)?(MM|CM|M)?$'),
        # Cilindradas y potencias sueltas: 1.6, 2.0TDI, 110CV
        re.compile(r'^\d[.,]\d[A-Z]*$'),
        re.compile(r'^\d+(CV|HP|KW|CC)$'),
        # MEDIDAS SUELTAS con la unidad pegada: 1060MM, 1425MM, L=1010MM (que se limpia como
        # L1010MM). Salen de descripciones de cables y mangueras, donde el largo es el dato
        # que las distingue. Con el patrón de arriba no alcanzaba: ese pide la forma AxB.
        re.compile(r'^L?\d+(MM|CM|MTS|MT)$'),
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
        # MOTORIZACIONES CUMMINS y parientes: 4BTA3.9, 6BTA5.9, 6CTA8.3, 4BT3.9. Es
        # «cantidad de cilindros + familia + litros», o sea el motor, y aparece en cualquier
        # descripción que lo nombre. Le pega a 0 de los 46.644 códigos de proveedor del
        # catálogo, así que no se pierde nada.
        re.compile(r'^\d[A-Z]{2,4}\d[.,]?\d?$'),
        # CAMIONES FORD: F14000, F4000, F12000, F1000, F16000. No es un código, es el modelo
        # del camión, y hace el daño de siempre: el F14000 estaba cargado como código de
        # fábrica uniendo un FILTRO DE COMBUSTIBLE con un CILINDRO MAESTRO, y el F4000 un
        # filtro con un sensor de nivel. Aparecen en 148 y 123 descripciones.
        # Se probó antes la regla general —descartar lo que aparece en muchas descripciones—
        # y no sirve: los mejores puentes que tiene la base son las tablas de equivalencias de
        # Bosch, donde un mismo número de arranque está en 84 descripciones. La forma sí los
        # separa: «F» y de tres a cinco dígitos le pega a 0 códigos de proveedor y a los 8
        # camiones que están cargados.
        re.compile(r'^F\d{3,5}$'),
        # EL MODELO CON LA CILINDRADA PEGADA: CORSA1.4, AMAROK2.0, TRAFIC-1.6, PALIO1.4.
        # separar_texto_pegado() ya los despega, pero esto es el cinturón de seguridad: la
        # descripción puede llegar acá sin pasar por ahí, y un código de fábrica NUNCA tiene
        # esta forma —una palabra entera seguida de un número con coma—. Va entre las formas
        # que son texto SIN DISCUSIÓN, o sea que ni un «REF ORIG» adelante las rescata.
        # En la base real había cinco de estos cargados como código de fábrica, y el peor
        # —CORSA1.4— colgaba un tubo, una correa multicanal y un sensor MAP. Le pega a 0 de
        # los 39.746 códigos reales del catálogo.
        re.compile(r'^[A-Z]{4,}-?\d[.,]\d[A-Z]*$'),
    )
    formas_prohibidas = formas_ambiguas + formas_solo_texto
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
    # Y al revés: el REF pegado a lo que viene ANTES, «PEUGEOT 404 - 504 - 505REF ORIG 024210».
    # Esa regla ya existía para la pantalla de vehículos y acá faltaba, así que entraban 212
    # códigos de fábrica terminados en REF —«505REF», «70010REF», «156REF»— que no son códigos:
    # son el modelo del auto, o el número interno del proveedor, con el «REF» de «REF ORIG»
    # pegado atrás. Y de paso tapaban el marcador: «REF ORIG» es el proveedor diciendo cuál es
    # el código de fábrica, que es el mejor dato que trae la lista.
    texto = _RE_REF_PEGADO.sub(r'\1 REF ', texto)

    # Dónde el proveedor DECLARÓ que lo que sigue es el código de fábrica. Sin esto se perdía
    # justo el mejor dato que trae la lista: «JTA SCANIA 113 Nº ORIG 287559» no daba nada,
    # porque un número de seis dígitos se descarta por si es un año o una medida — y con un
    # «Nº ORIG» adelante ya no hay duda de qué es. Lo mismo con «// 134048», «// 900432» y
    # «// ERR4685B», que además se caía por parecerse a un código de motor.
    posiciones_declaradas = set()
    # El '=' separa: una de las listas escribe la equivalencia como «BOSCH=0250202087» y
    # «HESCHER=HC173», o sea marca y número pegados por el igual. Sin partir por ahí entraban
    # como un código solo, y encima uno que no se cruza con nadie porque nadie más lo escribe
    # con la marca adelante.
    piezas = re.split(r'[\s,;/|()\[\]<>=]+', str(texto))
    for i, pieza in enumerate(piezas):
        if pieza.strip().upper().strip(".:") in _MARCADORES_DE_OEM:
            # las dos siguientes: cubre «Nº ORIG 287559» y «REF ORIG: 0360601402»
            posiciones_declaradas.update((i + 1, i + 2))
    # La barra doble desaparece al partir por '/', así que se marca aparte: en esas listas
    # «//» es la convención para «de acá en adelante va el código de fábrica».
    if "//" in str(texto):
        antes = len(re.split(r'[\s,;/|()\[\]<>=]+', str(texto).split("//", 1)[0]))
        posiciones_declaradas.update(range(antes - 1, antes + 3))

    encontrados = []
    for indice, token in enumerate(piezas):
        limpio = token.strip().strip(".-_")
        # La marca pegada atrás del número, que es como escriben varias listas: «26001FISPA»,
        # «2015NGK», «4EC1TBOSCH», «tu5pjp4NGK». Se despega en vez de descartar el token,
        # porque adelante puede haber un código de verdad — y cuando adelante hay una
        # motorización («4EC1T», «DW10ATED») lo que queda lo descartan las reglas de siempre,
        # que con la marca pegada no lo reconocían.
        for _marca_pegada in _MARCAS_QUE_SE_PEGAN_AL_CODIGO:
            if (limpio.upper().endswith(_marca_pegada)
                    and len(limpio) - len(_marca_pegada) >= 4):
                limpio = limpio[:-len(_marca_pegada)]
                break
        if len(limpio) < minimo:
            continue
        if limpio.upper() in ruido:
            continue
        declarado = indice in posiciones_declaradas
        # Estar en el catálogo desarma las formas AMBIGUAS —las de código de motor— y nada
        # más. Es el desempate que esos patrones no tienen: la duda era si 'TC936MG' es una
        # motorización o un repuesto, y que alguien lo venda la despeja.
        # Lo que NO desarma es el largo mínimo de los códigos puramente numéricos, y la
        # diferencia es cara: la descripción de FISPA «CONECTOR PARA MANGUERA 260035 16 X 5
        # 16» trae '260035', que es la medida 5/16 pegada al código 26003 — y da la
        # casualidad de que '260035' existe en el catálogo como una junta de colector de
        # MOTORARG. Aflojando también el largo, esa medida rota quedaba uniendo un conector
        # de manguera con una junta de admisión. Los códigos cortos de solo números son
        # justamente los que chocan entre catálogos; los que tienen letras, no.
        en_catalogo = sanitizar(limpio) in conocidos
        formas = formas_solo_texto if (declarado or en_catalogo) else formas_prohibidas
        if any(p.match(limpio.upper()) for p in formas):
            continue
        if limpio.upper().startswith(arranques_de_texto):
            continue
        # Una lista de modelos no es un código, lo haya declarado el proveedor o no.
        if _es_lista_de_modelos(limpio.upper()):
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
        # Si el proveedor lo declaró como código de fábrica alcanza con seis dígitos: los años
        # tienen cuatro, así que seis los sigue dejando afuera.
        if not tiene_letra and len(re.sub(r'\D', '', limpio)) < (6 if declarado else 7):
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
        # Las formas prohibidas se vuelven a probar sobre el código LIMPIO, por el mismo motivo
        # que el largo mínimo: la puntuación las disfraza. «L=1010MM» —el largo de un cable de
        # ABS— no coincidía con el patrón de medidas por el signo igual, pero limpio es
        # «L1010MM» y sí. Eran catorce medidas entrando como códigos de fábrica.
        if any(p.match(codigo_limpio.upper()) for p in formas):
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


def digito_verificador_gtin(cuerpo):
    """El dígito que le corresponde a un código de barras, calculado. '' si no se puede.

    Es aritmética de la norma GS1, no hay nada que consultar. Y es UNA sola cuenta para los
    cuatro largos —EAN-8, UPC-A de 12, EAN-13 y DUN-14 (la caja)—: se completa con ceros a la
    izquierda hasta trece dígitos, se suman con pesos 3 y 1 alternados **empezando por 3 a la
    izquierda**, y el verificador es lo que falta para llegar a la decena.

    Lo de completar con ceros no es un atajo: es exactamente lo que dice la norma, y es la
    diferencia entre leer bien y mal un DUN-14. Tratarlo como «un EAN-13 con un dígito de
    agrupación adelante» —sacarle el primero y hacer la cuenta de trece— da otro número: sobre
    la lista real de MOTORARG, esos 21 códigos de caja aparecían como mal copiados cuando están
    perfectos.

    `cuerpo` es el código SIN su dígito verificador."""
    n = re.sub(r'\D', '', str(cuerpo or ""))
    if not n or len(n) > 13:
        return ""
    n = n.rjust(13, "0")
    suma = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(n))
    return str((10 - suma % 10) % 10)


def codigo_de_barras_cierra(codigo):
    """¿El código de barras cierra con su dígito verificador? None si no se puede saber.

    None y no False cuando el largo no es de código de barras: no es lo mismo «este código está
    mal copiado» que «esto no es un código de barras», y confundirlos haría que la app acuse de
    error a un código de fábrica que nunca pretendió ser un EAN."""
    n = re.sub(r'\D', '', str(codigo or ""))
    if len(n) not in (8, 12, 13, 14):
        return None
    esperado = digito_verificador_gtin(n[:-1])
    return bool(esperado) and esperado == n[-1]


def columna_es_codigo_de_barras(valores):
    """¿La columna que se eligió como «código de fábrica» trae en realidad códigos de barras?

    Es la diferencia entre que la lista sirva para cruzar con otros proveedores y que no sirva
    para nada. El código de fábrica lo pone la terminal (036115561G, 7700274177) y lo repiten
    todos los que fabrican esa pieza: por ahí es por donde se encadenan las listas. El código
    de barras lo saca el proveedor para SU producto, es único de él y no lo va a tener nadie
    más nunca.

    Pasó de verdad y es caro: en la base real la lista de MOTORARG entró con la columna de
    código de barras mapeada como código de fábrica. Resultado: 8.076 "códigos de fábrica" que
    empiezan todos con 7793960 —el prefijo de GS1 de esa empresa—, ninguno compartido con nadie,
    y 8.652 productos que en la búsqueda muestran una equivalencia que no lleva a ningún lado.
    Desde el mostrador se ve como «no me hace las equivalencias con las otras marcas».

    Cómo se reconoce, sin inventar nada: un código de barras es TODO números, de 12 a 14
    dígitos, y —esto es lo que lo delata— los primeros dígitos son el prefijo de empresa, así
    que en una lista de un solo proveedor son casi siempre los mismos. Un código de fábrica de
    verdad no tiene esa forma: o trae letras, o es más corto, o los de una misma lista arrancan
    distinto porque salen de terminales distintas.

    Devuelve (es_codigo_de_barras, prefijo_comun, cuantos_del_total)."""
    limpios = [re.sub(r'\D', '', str(v or "")) for v in valores if str(v or "").strip()]
    limpios = [v for v in limpios if v]
    if len(limpios) < 20:          # con menos filas cualquier coincidencia es casualidad
        return False, "", (0, 0)
    largos = [v for v in limpios if 12 <= len(v) <= 14]
    if len(largos) < len(limpios) * 0.7:
        return False, "", (len(largos), len(limpios))
    # El prefijo de empresa de GS1 tiene entre 6 y 9 dígitos contando el país. Se busca el
    # más largo que comparta la mayoría: cuanto más largo, más seguro que es una sola empresa.
    for largo_prefijo in (9, 8, 7, 6):
        conteo = {}
        for v in largos:
            conteo[v[:largo_prefijo]] = conteo.get(v[:largo_prefijo], 0) + 1
        prefijo, cuantos = max(conteo.items(), key=lambda kv: kv[1])
        if cuantos >= len(largos) * 0.7:
            return True, prefijo, (cuantos, len(limpios))
    # Segunda señal, para las listas que el prefijo no agarra: un revendedor que trae productos
    # de veinte fábricas tiene veinte prefijos distintos y ninguno llega al 70%. Ahí lo que los
    # delata es el DÍGITO VERIFICADOR. Está medido contra la base real: de los códigos largos de
    # MOTORARG —que son códigos de barras— cierran los 8.319, y de los de FISPA —que son códigos
    # de fábrica de verdad, largos y numéricos— cierra el 13%, que es lo que da el azar. No se
    # puede confundir una cosa con la otra.
    cierran = [v for v in largos if codigo_de_barras_cierra(v)]
    if len(cierran) >= len(largos) * 0.7:
        return True, "", (len(cierran), len(limpios))
    return False, "", (len(largos), len(limpios))


# El prefijo de un código de barras dice EN QUÉ PAÍS se registró la empresa que lo emitió.
# Es público, es fijo y no hace falta consultar nada: lo asigna GS1 y está en la norma.
# Sirve para dos cosas en el mostrador: saber si algo es nacional o importado sin mirar la caja,
# y darse cuenta de que una lista entera cargó códigos de barras como si fueran códigos de
# fábrica —todos con el mismo prefijo de empresa— que es el error que más vínculos muertos deja.
# OJO con lo que NO es un país: 020-029 y 200-299 son de uso interno del comercio (los que
# imprime la balanza del supermercado), y 977-979 son revistas y libros.
PREFIJOS_GS1 = [
    ((0, 19), "Estados Unidos y Canadá"), ((20, 29), "uso interno del comercio"),
    ((30, 39), "Estados Unidos"), ((40, 49), "uso interno del comercio"),
    ((50, 59), "cupón"), ((60, 139), "Estados Unidos y Canadá"),
    ((200, 299), "uso interno del comercio"),
    ((300, 379), "Francia"), ((380, 380), "Bulgaria"), ((383, 383), "Eslovenia"),
    ((385, 385), "Croacia"), ((387, 387), "Bosnia y Herzegovina"), ((389, 389), "Montenegro"),
    ((400, 440), "Alemania"), ((450, 459), "Japón"), ((460, 469), "Rusia"),
    ((470, 470), "Kirguistán"), ((471, 471), "Taiwán"), ((474, 474), "Estonia"),
    ((475, 475), "Letonia"), ((476, 476), "Azerbaiyán"), ((477, 477), "Lituania"),
    ((478, 478), "Uzbekistán"), ((479, 479), "Sri Lanka"), ((480, 480), "Filipinas"),
    ((481, 481), "Bielorrusia"), ((482, 482), "Ucrania"), ((484, 484), "Moldavia"),
    ((485, 485), "Armenia"), ((486, 486), "Georgia"), ((487, 487), "Kazajistán"),
    ((489, 489), "Hong Kong"), ((490, 499), "Japón"), ((500, 509), "Reino Unido"),
    ((520, 521), "Grecia"), ((528, 528), "Líbano"), ((529, 529), "Chipre"),
    ((530, 530), "Albania"), ((531, 531), "Macedonia del Norte"), ((535, 535), "Malta"),
    ((539, 539), "Irlanda"), ((540, 549), "Bélgica y Luxemburgo"), ((560, 560), "Portugal"),
    ((569, 569), "Islandia"), ((570, 579), "Dinamarca"), ((590, 590), "Polonia"),
    ((594, 594), "Rumania"), ((599, 599), "Hungría"), ((600, 601), "Sudáfrica"),
    ((603, 603), "Ghana"), ((608, 608), "Baréin"), ((609, 609), "Mauricio"),
    ((611, 611), "Marruecos"), ((613, 613), "Argelia"), ((616, 616), "Kenia"),
    ((618, 618), "Costa de Marfil"), ((619, 619), "Túnez"), ((621, 621), "Siria"),
    ((622, 622), "Egipto"), ((624, 624), "Libia"), ((625, 625), "Jordania"),
    ((626, 626), "Irán"), ((627, 627), "Kuwait"), ((628, 628), "Arabia Saudita"),
    ((629, 629), "Emiratos Árabes Unidos"), ((640, 649), "Finlandia"), ((690, 695), "China"),
    ((700, 709), "Noruega"), ((729, 729), "Israel"), ((730, 739), "Suecia"),
    ((740, 740), "Guatemala"), ((741, 741), "El Salvador"), ((742, 742), "Honduras"),
    ((743, 743), "Nicaragua"), ((744, 744), "Costa Rica"), ((745, 745), "Panamá"),
    ((746, 746), "República Dominicana"), ((750, 750), "México"), ((754, 755), "Canadá"),
    ((759, 759), "Venezuela"), ((760, 769), "Suiza"), ((770, 771), "Colombia"),
    ((773, 773), "Uruguay"), ((775, 775), "Perú"), ((777, 777), "Bolivia"),
    ((778, 779), "Argentina"), ((780, 780), "Chile"), ((784, 784), "Paraguay"),
    ((786, 786), "Ecuador"), ((789, 790), "Brasil"), ((800, 839), "Italia"),
    ((840, 849), "España"), ((850, 850), "Cuba"), ((858, 858), "Eslovaquia"),
    ((859, 859), "Chequia"), ((860, 860), "Serbia"), ((865, 865), "Mongolia"),
    ((867, 867), "Corea del Norte"), ((868, 869), "Turquía"), ((870, 879), "Países Bajos"),
    ((880, 880), "Corea del Sur"), ((884, 884), "Camboya"), ((885, 885), "Tailandia"),
    ((888, 888), "Singapur"), ((890, 890), "India"), ((893, 893), "Vietnam"),
    ((896, 896), "Pakistán"), ((899, 899), "Indonesia"), ((900, 919), "Austria"),
    ((930, 939), "Australia"), ((940, 949), "Nueva Zelanda"), ((955, 955), "Malasia"),
    ((958, 958), "Macao"), ((977, 977), "revista o publicación periódica"),
    ((978, 979), "libro (ISBN)"), ((980, 980), "comprobante de devolución"),
    ((981, 984), "cupón"), ((990, 999), "cupón"),
]


def pais_del_codigo_de_barras(codigo):
    """De qué país es el código de barras, por su prefijo GS1. '' si no se puede decir.

    El país es el de la empresa que REGISTRÓ el código, no el de la fábrica: un repuesto con
    779 lo vende una empresa argentina, aunque la pieza venga de China. Eso igual sirve — lo
    que se quiere saber en el mostrador es si lo consigue un proveedor local."""
    limpio = re.sub(r'\D', '', str(codigo or ""))
    if len(limpio) not in (8, 12, 13, 14):
        return ""
    if len(limpio) == 12:          # UPC-A: es EAN-13 con un cero adelante
        limpio = "0" + limpio
    if len(limpio) == 14:          # DUN-14 (la caja): el dígito de agrupación va adelante
        limpio = limpio[1:]
    try:
        prefijo = int(limpio[:3])
    except ValueError:
        return ""
    for (desde, hasta), pais in PREFIJOS_GS1:
        if desde <= prefijo <= hasta:
            return pais
    return ""


def pais_de_estos_codigos(valores):
    """El país que comparten estos códigos de barras, o '' si no hay uno solo claro.

    Se usa cuando se descubrió que una lista entera cargó códigos de barras como si fueran
    códigos de fábrica: poder decir «son de una empresa de Argentina» hace reconocible un
    número que si no es una tira de dígitos.

    Mira los códigos ENTEROS y no el prefijo común que devuelve columna_es_codigo_de_barras(),
    que sería lo cómodo, por una razón concreta: ese prefijo se corta de la cadena tal como
    está guardada, y un UPC-A de 12 dígitos es un EAN-13 con un cero adelante que ahí no está.
    Sobre el código entero eso ya lo resuelve pais_del_codigo_de_barras(); sobre el prefijo
    suelto, «045496» daría «uso interno del comercio» cuando en realidad es 004, Estados
    Unidos."""
    conteo = {}
    for v in valores:
        pais = pais_del_codigo_de_barras(v)
        if pais:
            conteo[pais] = conteo.get(pais, 0) + 1
    if not conteo:
        return ""
    pais, cuantos = max(conteo.items(), key=lambda kv: kv[1])
    # Si la lista mezcla países no se afirma ninguno: sería peor que no decir nada.
    return pais if cuantos >= sum(conteo.values()) * 0.7 else ""


# No todo prefijo es un país: estos cinco valores son usos especiales de la norma. Importan
# porque si un escaneo cae en uno de ellos, el número NO identifica un repuesto — es la
# etiqueta que imprimió una balanza, un cupón, o el ISBN del manual que estaba al lado. Sin
# esto, el mostrador lee «no está cargado» y se pone a buscar un producto que no existe.
GS1_NO_ES_UN_PAIS = {"uso interno del comercio", "cupón", "revista o publicación periódica",
                     "libro (ISBN)", "comprobante de devolución"}


# ============================================================
# COMBOS DE REPUESTOS RELACIONADOS (ej: correa de distribución -> kit + tensor + bomba de agua)
# ============================================================
def normalizar_texto(texto):
    """Mayúsculas y sin acentos, para poder comparar 'distribución' con 'distribucion'."""
    texto = texto or ""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return texto.upper().strip()


# Excel escribe los caracteres de control que quedaron en una celda como «_x001F_», y el
# lector los entrega así, como texto. Ver valor_o_vacio().
_RE_ESCAPE_DE_EXCEL = re.compile(r'_x[0-9A-Fa-f]{4}_')


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
    # «_x001f_» y compañía: así escribe Excel un caracter de control que quedó adentro de la
    # celda, y llega tal cual, como siete caracteres de texto. Pega dos palabras y arruina las
    # dos: de «INYECTOR FI-0280155888_x001f_Ford Ka» salió un producto con el código
    # «FI-0280155888_x001f_Fo». Se cambia por un espacio, que es lo que había.
    if "_x" in texto:
        texto = _RE_ESCAPE_DE_EXCEL.sub(" ", texto).strip()
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

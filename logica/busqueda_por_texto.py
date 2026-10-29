"""Las descripciones con las columnas pegadas y la búsqueda por texto.

Salió de logica/descripciones.py, que con 5.400 renglones juntaba cinco temas.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================================================
# DESCRIPCIONES PEGADAS Y BÚSQUEDA POR TEXTO
# ============================================================================================
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
    "(" + alternativas_en_arbol(MARCAS_PARA_DESPEGAR) + ")"   # la más larga primero
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
    r'(?<=\d)(' + alternativas_en_arbol(_MARCAS_CORTAS_PEGADAS)
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
    correr el arreglo o no.

    Y se guarda en la base con la versión del catálogo con que se contó: el caché de Streamlit
    se pierde con cada reinicio del servidor —en Streamlit Cloud, seguido— y eran 1,9 s en la
    primera visita a «Limpiar y corregir» después de cada uno, para volver a contar lo mismo."""
    # Con la versión del separador: si cambian sus reglas, lo contado ya no vale.
    version = f"{version_del_catalogo()} · separador {VERSION_SEPARACION}"
    if obtener_config("pegadas_version", "") == version:
        try:
            return int(obtener_config("pegadas_cantidad", ""))
        except ValueError:
            pass
    n = _contar_descripciones_pegadas(version)
    guardar_config("pegadas_version", version)
    guardar_config("pegadas_cantidad", str(n))
    return n


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


def parece_una_descripcion(texto):
    """Si lo escrito en el buscador de CÓDIGOS es en realidad una descripción: solo palabras
    (ningún número), y no es un código cargado. «filtro aceite gol» o «mannol» sí —el nombre de
    una lista también se busca así, y aparecen todos sus productos—; «W712/94» o «filtro
    24058» no: esos los resuelve la búsqueda por código.
    En el catálogo real hay 77 códigos de solo letras («BAFAH», «BRAGS»): por eso se pregunta
    si existe antes de decidir. Una sola palabra de menos de cuatro letras se deja como código."""
    texto = (texto or "").strip()
    if not texto or "," in texto:
        return False
    palabras = [p for p in re.split(r"\s+", texto) if p]
    if re.search(r"\d", texto):
        # Con números, solo si son datos chicos de una descripción —«1.6», «4», «16V»— y hay
        # al menos dos palabras de verdad: «bomba agua gol 1.6», «ficha 4 vias». Un número
        # que parece código («24058», «W712/94») deja la búsqueda por código.
        if any(re.search(r"\d", p) and len(sanitizar(p)) >= 5 for p in palabras):
            return False
        if sum(1 for p in palabras if re.fullmatch(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}", p)) < 2:
            return False
    if len(palabras) == 1 and len(sanitizar(palabras[0])) < 4:
        return False
    limpio = sanitizar(texto)
    if not limpio or existe_el_codigo(limpio):
        return False
    return any(re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}", p) for p in palabras)


def marcas_que_nombra(palabra):
    """Los id de las listas (no los códigos de fábrica) cuyo nombre tiene esa palabra entera:
    «mannol» → MANNOL LUBRICANTES, «crifa» → CRI-FA. Palabras de tres letras o más: «JL» o
    «VW» solas engancharían cualquier cosa."""
    limpia = re.sub(r"[^A-Z0-9]", "", normalizar_texto(palabra))
    if len(limpia) < 3:
        return []
    c.execute("SELECT id, nombre FROM marcas WHERE tipo <> 'OEM'")
    salida = []
    for fila in c.fetchall():
        nombre = normalizar_texto(fila["nombre"] or "")
        palabras_del_nombre = {re.sub(r"[^A-Z0-9]", "", x) for x in re.split(r"\s+", nombre)}
        if limpia in palabras_del_nombre or limpia == re.sub(r"[^A-Z0-9]", "", nombre):
            salida.append(fila["id"])
    return salida


# LAS ABREVIATURAS DE LAS LISTAS, EN LA BÚSQUEDA POR TEXTO. El mostrador escribe «juego juntas
# motor» y la lista dice «Jgo.Jtas.P/Motor»: con la palabra entera como pedazo de texto no se
# encontraba ninguno de los 779 juegos escritos así en la copia de la base real, ni ninguna de
# las 301 «JTA … ESC» buscando «junta escape», ni las 27 «BBA … NAFTA» buscando «bomba nafta».
# Las formas salen de ABREVIATURAS_DE_PIEZA, contadas en tus listas. Las cortas se buscan como
# palabra entera (con el punto, la barra y el guion como espacios): «ESC» no es DESCARGA ni
# «RET» es CARRETERA. Las de cinco letras o más, como pedazo: ESCAP solo está en ESCAPE.
_BUSQUEDA_CON_ESPACIOS = ("(' ' || REPLACE(REPLACE(REPLACE(REPLACE(p.busqueda, '.', ' '), "
                          "'/', ' '), '-', ' '), ',', ' ') || ' ')")


@functools.lru_cache(maxsize=1)
def _formas_por_palabra():
    por_pieza = {}
    for corta, pieza in ABREVIATURAS_DE_PIEZA.items():
        por_pieza.setdefault(pieza, {pieza}).add(corta)
    return {forma: formas for formas in por_pieza.values() for forma in formas}


def singulares_de(palabra):
    """Cómo se escribe en singular lo que se pidió en plural: RULEMANES → RULEMAN, PASTILLAS →
    PASTILLA, CABLES → CABLE, PEDALES → PEDAL. El mostrador escribe «rulemanes rueda gol» y la
    lista dice «RULEMAN»: había 9 así y salía 1. Con la pieza en plural, las 794 consultas de
    `medir.py texto` encontraban primero 207 en vez de 263. Solo lo más corto: «PISTON» ya
    encuentra todo lo que encontraría «PISTONE»."""
    if len(palabra) < 5 or not palabra.isalpha() or not palabra.endswith("S"):
        return []
    candidatos = []
    if palabra[-2] in "AEIOU":
        candidatos.append(palabra[:-1])
    if palabra.endswith("ES") and palabra[-3] not in "AEIOU" and len(palabra) >= 7:
        candidatos.append(palabra[:-2])
    return [x for x in candidatos if not any(y != x and y in x for y in candidatos)]


# La cilindrada como la escriben las listas: «1.6», «1,6», «1 6» (FISPA) y «1.4/1.6». Y las
# válvulas: «16V», «16 V», «16VALV».
_RE_CILINDRADA = re.compile(r"\d[.,]\d")
_RE_VALVULAS = re.compile(r"(8|12|16|20|24|32)V")

# LA MARCA DEL AUTO, COMO LA ESCRIBA LA LISTA. En la copia de la base, «VW» está en 3.518 productos
# y «VOLKSWAGEN» en 2.476; «CHEVROLET» en 4.672, «GM» en 1.221 y «CHEV» en 719. Buscando
# «volkswagen gol» no salía ningún «VW GOL». Las formas son las de ESCRITURAS_DE_MARCA, y para
# buscar, además, GM es Chevrolet (Corsa, Astra, Meriva): no se toca la marca guardada, que
# decide equivalencias.
_SINONIMOS_DE_MARCA_PARA_BUSCAR = {"CHEVROLET": ("GM",), "GM": ("CHEVROLET", "CHEV")}


def escrituras_de_la_marca(palabra):
    """Las otras formas de la marca de auto `palabra`, con espacios donde la lista pone punto o
    guion: «VW» → [VOLKSWAGEN]; «CHEVROLET» → [CHEV, GM]; «MERCEDES» → [M BENZ, …]. [] si
    no es una marca."""
    marcas = marcas_vehiculo_en(palabra)
    if len(marcas) != 1:
        return []
    canonica = marcas[0][0]
    formas = ({canonica} | set(ESCRITURAS_DE_MARCA.get(canonica, ()))
              | set(_SINONIMOS_DE_MARCA_PARA_BUSCAR.get(canonica, ())))
    return sorted({re.sub(r"[.\-/,]+", " ", f).strip() for f in formas} - {palabra})


# COMO SE DICE EN EL MOSTRADOR Y COMO LO ESCRIBE LA LISTA. Contados en la copia de la base:
# «bomba de nafta» en 204 productos y «bomba de combustible» en 711; «palier» 36 y «semieje» 13;
# «termostato» 875 y «termostática» 114; «motor de arranque» 1.486 y nadie escribe «burro»;
# «alternador» 892 y «dínamo» 2; «válvula» 2.134 y «sopapa» 0; «pistón» 153 y «émbolo» 0.
# «Cojinete» no: acá también son los de biela y bancada, no un rulemán.
SINONIMOS_DEL_MOSTRADOR = {
    "NAFTA": ("COMBUSTIBLE",), "COMBUSTIBLE": ("NAFTA",),
    "PALIER": ("SEMIEJE",), "SEMIEJE": ("PALIER",),
    "TERMOSTATO": ("TERMOSTATICA",), "TERMOSTATICA": ("TERMOSTATO",),
    "RULEMAN": ("RODAMIENTO",), "RODAMIENTO": ("RULEMAN",),
    "PATIN": ("PASTILLA",), "PASTILLA": ("PATIN",),
    "BURRO": ("ARRANQUE",), "DINAMO": ("ALTERNADOR",), "SOPAPA": ("VALVULA",),
    "EMBOLO": ("PISTON",),
}


def formas_de_la_palabra(palabra):
    """Las otras formas de escribir `palabra` en las listas: [(forma, si va como palabra
    entera)]. «JUNTA» → JTA y JTAS enteras, JUNTAS como pedazo. Sin la palabra misma. Y el
    singular de lo pedido en plural (singulares_de()), con sus abreviaturas; y la cilindrada
    escrita de las tres maneras: «1.6» busca también «1 6» entera, que con el punto, la coma
    y la barra como espacios encuentra «1,6», «1 6» y «1.4/1.6»."""
    formas = set(_formas_por_palabra().get(palabra, set()))
    # Sin el singular de una marca o un modelo: «MERCEDES» no es el plural de nada.
    for singular in (singulares_de(palabra) if not nivel_del_auto(palabra) else ()):
        formas |= {singular} | _formas_por_palabra().get(singular, set())
    if _RE_CILINDRADA.fullmatch(palabra):
        formas.add(f"{palabra[0]} {palabra[2]}")
    if _RE_VALVULAS.fullmatch(palabra):
        formas.add(f"{palabra[:-1]} V")
    # La viscosidad: «aceite 10w40» no encontraba nada, y las listas escriben «10W-40».
    if re.fullmatch(r"\d{1,2}W\d{2}", palabra):
        formas.add(f"{palabra[:palabra.index('W') + 1]} {palabra[palabra.index('W') + 1:]}")
    formas |= set(escrituras_de_la_marca(palabra))
    for base in [palabra] + singulares_de(palabra):
        formas |= set(SINONIMOS_DEL_MOSTRADOR.get(base, ()))
    formas.discard(palabra)
    # La que contiene a la palabra ya la encuentra el LIKE de la palabra: «JUNTAS» con «JUNTA».
    return sorted((f, len(f) < 5 or " " in f) for f in formas if palabra not in f)


# LO QUE NOMBRA EL AUTO MANDA. «bomba de agua k4m» traía 200 resultados y uno solo decía K4M:
# con tres palabras alcanza con dos, y «bomba» y «agua» las dice cualquier bomba de agua. Lo que
# pidió el dueño: «llega un momento que no tienen nada que ver los productos más que ser bombas
# de agua». Ahora, si lo pedido nombra el auto, lo que no lo nombra va aparte (ver
# ResultadosDeTexto); si nada lo nombra, se muestra todo como antes: nunca la pantalla vacía.
_RE_CILINDRADA_O_VALVULAS = re.compile(r"\d[.,]\d|\d{1,2}V")


# Los modelos de dos letras, que MODELOS_CONOCIDOS deja afuera (pide tres): «ford ka embrague»
# traía el embrague de la Transit, porque sin el Ka lo único del auto era «FORD». Contados como
# palabra entera en la copia de la base: KA 865, C3 838, A3 1.145. «UP» no: es «pick up».
MODELOS_CORTOS = {"KA", "C3", "C4", "C5", "A3", "A4", "A5", "A6", "Q3", "Q5", "X1", "X3", "X5"}


def nivel_del_auto(palabra):
    """Cuánto dice `palabra` de qué auto es: 3 el modelo o el motor (GOL, CLIO, K4M, F8Q), 2 la
    marca (RENAULT, VW), 1 la cilindrada o las válvulas (1.6, 16V), 0 nada."""
    if marcas_vehiculo_en(palabra):
        return 2           # antes que el modelo: MODELOS_CONOCIDOS tiene también las marcas
    if (parece_designacion_de_motor(palabra) or palabra in MODELOS_CONOCIDOS
            or palabra in MODELOS_CORTOS):
        return 3
    return 1 if _RE_CILINDRADA_O_VALVULAS.fullmatch(palabra) else 0


def palabras_del_auto(palabras):
    """Las palabras pedidas que dicen el auto, las más precisas: el modelo o el motor; si no
    hay, la marca; si no, la cilindrada. «bomba de agua renault clio 1.6» → [CLIO]."""
    niveles = {p: nivel_del_auto(p) for p in palabras}
    tope = max(niveles.values(), default=0)
    return [p for p, n in niveles.items() if n == tope] if tope else []


def nombra_alguna(fila, palabras):
    """¿La descripción o el código dicen alguna de `palabras` sin otra letra pegada? «GOL» no
    está en GOLF; sí en «GOL/PARATI» y en «GOL1.6», «K4M» en K4M700 y «GALLOPER» en
    «FIS-202003Galloper», que es como lo escribe la lista. Si la palabra empieza o termina en
    número, tampoco otro número: «F100» no es F1000, ni «1.6» es 11.6."""
    crudo = normalizar_texto(f"{fila.get('Descripcion') or ''} {fila.get('Codigo') or ''}")
    return bool(_patron_de_palabras_del_auto(tuple(palabras)).search(crudo))


@functools.lru_cache(maxsize=64)
def _patron_de_palabras_del_auto(palabras):
    # Con las otras formas de la marca: buscando «volkswagen», «VW GOL» la nombra.
    todas = [x for p in palabras for x in [p] + escrituras_de_la_marca(p)]
    return re.compile("|".join(
        ("(?<![A-Z0-9.])" if p[:1].isdigit() else "(?<![A-Z])")
        + (f"{p[0]}[., ]{p[2]}" if _RE_CILINDRADA.fullmatch(p)
           else re.escape(p).replace("\\ ", "[ .\\-]+"))
        + ("(?![0-9])" if p[-1:].isdigit() else "(?![A-Z])") for p in todas))


# LA CILINDRADA PEDIDA. «embrague gol 1.6» traía también el del Gol 1.0, el del 1.8 y el del 1.9
# diesel: nombran el auto, pero declaran OTRA cilindrada. Como el año (ver sirve_para_anio()),
# lo que no declara ninguna se deja; lo que declara otras y no la pedida va aparte. Con la copia
# de la base: 8 de 104 en ese, 35 de 69 en «junta tapa cilindros palio 1.3» (las del 1.4).
# Sin una letra antes: en «AUDI A3 1.6», «3 1» no es una cilindrada.
_RE_CILINDRADA_DECLARADA = re.compile(r"(?<![A-Z0-9.,])(\d)[., ](\d)(?![0-9])")


def cilindradas_que_declara(fila):
    """{"1.6", "1.4"}: las cilindradas que dice la descripción, escritas «1.6», «1,6» o «1 6»
    (FISPA). Entre 0.8 y 6.0: «2.30MM» de un espesor no es una cilindrada."""
    return {f"{a}.{b}" for a, b in _RE_CILINDRADA_DECLARADA.findall(
        normalizar_texto(fila.get("Descripcion") or "")) if "0.8" <= f"{a}.{b}" <= "6.0"}


# Las válvulas, igual: «kit distribucion clio 16v» traía los del Clio 8V.
_RE_VALVULAS_DECLARADAS = re.compile(r"(?<![0-9.,])(8|12|16|20|24|32) ?V(?:ALV[A-Z]*)?(?![A-Z0-9])")


def valvulas_que_declara(fila):
    """{"16V", "8V"}: las válvulas que dice la descripción («16V», «16 V», «16VALV»)."""
    return {f"{n}V" for n in _RE_VALVULAS_DECLARADAS.findall(
        normalizar_texto(fila.get("Descripcion") or ""))}


# LA PIEZA PEDIDA, LO MISMO. «filtro de aire chevrolet corsa» traía, entre los que dicen Corsa,
# filtros de combustible, juegos de juntas del carburador y 95 de IMPERIAL que dicen solo
# «CHEVROLET CORSA 1.6»: algo del Corsa, pero no se sabe qué. La pieza es la clave de rubro que
# se lee en lo pedido (ver clasificar_repuesto()): «FILTRO DE AIRE». Lo que no la dice va
# aparte, como lo que no dice el auto; con abreviaturas y singular (ver dice_la_palabra()).
_PALABRAS_DE_UNION = {"DE", "DEL", "LA", "EL", "LOS", "LAS", "PARA", "P", "C", "CON", "Y"}


def _sin_uniones(texto):
    return " ".join(w for w in _normalizar_desc(texto).split() if w not in _PALABRAS_DE_UNION)


@functools.lru_cache(maxsize=1)
def _claves_de_pieza():
    """{clave sin «de» ni «para»: la clave}, de la más larga a la más corta."""
    claves = {}
    for lista in FAMILIAS_REPUESTO.values():
        for clave in lista:
            claves.setdefault(_sin_uniones(clave), clave)
    return sorted(claves.items(), key=lambda x: -len(x[0]))


def pieza_que_nombra(texto):
    """La pieza que nombra lo pedido, con las claves de rubro (ver clasificar_repuesto()): la
    que aparece primero y, en el mismo lugar, la más larga. Sin contar «de» ni «para»: «filtro
    aire chevrolet corsa» es «FILTRO DE AIRE», no solo «FILTRO» (y entonces los filtros de
    aceite pasaban). "" si no se reconoce ninguna."""
    limpio = f" {_sin_uniones(texto or '')} "
    mejor = None
    for sin, clave in _claves_de_pieza():
        lugar = limpio.find(f" {sin} ")
        if lugar >= 0 and (mejor is None or lugar < mejor[0]):
            mejor = (lugar, clave)
    return mejor[1] if mejor else ""


def palabras_de_la_pieza(texto):
    """Las palabras de la pieza que nombra lo pedido: «filtro de aire chevrolet corsa» →
    [FILTRO, AIRE]. [] si no se reconoce ninguna."""
    return [w for w in _sin_uniones(pieza_que_nombra(texto)).split() if len(w) >= 3]


def _dice_el_numero(fila, palabra):
    """Como dice_la_palabra(), pero un número no vale adentro de otro: «0151» no está en
    C12015120, ni «260» en 12600. Sí entre letras: MFLA260."""
    if not palabra.isdigit():
        return dice_la_palabra(fila, palabra)
    if fila.get("_barras") == palabra:       # el código de barras entero (ver más arriba)
        return True
    crudo = normalizar_texto(f"{fila.get('Descripcion') or ''} {fila.get('Codigo') or ''}")
    return bool(re.search(rf"(?<!\d){palabra}(?!\d)", crudo))


def familia_de_codigos(prefijo, numero, limite=8):
    """Los productos cuyo código es `prefijo` y un número (OC305, MFLA 258), del número más
    cercano a `numero` al más lejano, con «_a» (a cuánto está) y «Por qué». Sin los códigos de
    fábrica, que no se venden. Con la columna del código indexada: 0,1 ms."""
    c.execute("""SELECT p.id, p.codigo_clean FROM productos p JOIN marcas m ON m.id = p.marca_id
                 WHERE p.codigo_clean GLOB ? AND m.tipo <> 'OEM'""", (f"{prefijo}[0-9]*",))
    distancia = {}
    for pid, codigo in c.fetchall():
        hallado = re.match(r"\d+", codigo[len(prefijo):])
        distancia[pid] = abs(int(hallado.group()) - numero)
    elegidos = sorted(distancia, key=lambda pid: (distancia[pid], pid))[:limite]
    if not elegidos:
        return []
    c.execute(f"""SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
                         m.nombre AS "Marca", p.precio AS "Precio", p.stock AS "Stock"
                  FROM productos p JOIN marcas m ON m.id = p.marca_id
                  WHERE p.id IN ({",".join("?" * len(elegidos))})""", elegidos)
    salida = filas_a_listas(c)
    for f in salida:
        f["_a"] = distancia[f["ID"]]
        f["Por qué"] = f"es otro: a {f['_a']} del {numero}"
    return sorted(salida, key=lambda f: (f["_a"], f["ID"]))


def _dice_el_codigo(fila, familias, numero):
    """¿La fila dice el código pedido —las letras y el número juntos: «MFLA 260», «OC-306»,
    «SP0451»—, en el código o en la descripción?"""
    crudo = normalizar_texto(f"{fila.get('Descripcion') or ''} {fila.get('Codigo') or ''}")
    sin_ceros = numero.lstrip("0") or "0"
    return any(re.search(rf"(?<![A-Z0-9]){q}[\s.\-/]*0*{sin_ceros}(?!\d)", crudo)
               for q in familias)


def _numero_en_la_familia(fila, prefijo):
    """El número del código de la fila si es de la familia `prefijo` (MFLA 258 → 258), o None."""
    codigo = re.sub(r"[^A-Z0-9]", "", normalizar_texto(fila.get("Codigo") or ""))
    numero = re.match(r"\d+", codigo[len(prefijo):]) if codigo.startswith(prefijo) else None
    return int(numero.group()) if numero else None


def dice_la_palabra(fila, palabra):
    """¿La fila dice `palabra`, como la encuentra la búsqueda: adentro de otra («JUNTA» en
    JUNTAS), abreviada (JTA) o en singular (CILINDRO por CILINDROS)?"""
    crudo = normalizar_texto(f"{fila.get('Descripcion') or ''} {fila.get('Codigo') or ''}")
    if palabra in crudo:
        return True
    sin_puntos = " " + re.sub(r"[^A-Z0-9]+", " ", crudo) + " "
    return any((f" {forma} " in sin_puntos) if entera else (forma in crudo)
               for forma, entera in formas_de_la_palabra(palabra))


# DE QUÉ AUTOS ES UN MOTOR, SEGÚN TUS LISTAS. «bomba de agua k4m» encuentra lo que dice K4M, y
# las bombas que dicen «Clio 1.6 16V» sin nombrar el motor quedan abajo: se probó meterlas solas
# y no fue confiable (para el F8Q trajo una del N7Q). Como AYUDA sí: «K4M: Clio, Megane, Scenic,
# Kangoo… 1.6 16V», con un botón para buscar así y que la persona elija.
def autos_del_motor(motor):
    """{"marca", "modelos", "cilindrada", "valvulas", "productos"} de lo que dicen las
    descripciones que nombran el motor, o None si son menos de cinco. Los modelos, los que
    aparecen en el 5 % o más (y al menos dos veces); la cilindrada y las válvulas, la más común
    si la dicen tres o más y el 60 % de los que dicen alguna: el F8Q tenía 9 «16V» y 9 «8V»."""
    memoria = del_proceso("autos_del_motor", dict)
    clave = (motor, version_del_catalogo())
    if clave in memoria:
        return memoria[clave]
    if len(memoria) > 50:
        memoria.clear()
    c.execute("SELECT descripcion FROM productos WHERE busqueda LIKE ? LIMIT 3000",
              (f"%{como_texto_en_like(motor)}%",))
    filas = [{"Descripcion": r[0]} for r in c.fetchall()]
    filas = [f for f in filas if nombra_alguna(f, [motor])]
    salida = None
    if len(filas) >= 5:
        marcas, modelos, cilindradas, valvulas = (collections.Counter() for _ in range(4))
        for f in filas:
            texto = normalizar_texto(f["Descripcion"] or "")
            marcas.update({m for m, _cat, _resto in marcas_vehiculo_en(f["Descripcion"] or "")})
            modelos.update({w for w in re.findall(r"[A-Z0-9]+", texto)
                            if w != motor and nivel_del_auto(w) == 3
                            and not parece_designacion_de_motor(w)})
            cilindradas.update(cilindradas_que_declara(f))
            valvulas.update(valvulas_que_declara(f))

        def la_mas_comun(cuenta):
            if not cuenta:
                return None
            valor, veces = cuenta.most_common(1)[0]
            return valor if veces >= 3 and veces >= 0.6 * sum(cuenta.values()) else None
        salida = {"marca": marcas.most_common(1)[0][0] if marcas else None,
                  "modelos": [m for m, n in modelos.most_common(8)
                              if n >= max(2, len(filas) * 0.05)],
                  "cilindrada": la_mas_comun(cilindradas), "valvulas": la_mas_comun(valvulas),
                  "productos": len(filas)}
        if not salida["modelos"]:
            salida = None
    memoria[clave] = salida
    return salida


def sugerencias_por_el_motor(texto):
    """[(motor, autos_del_motor(), [búsquedas])]: para cada motor pedido, lo mismo con el auto en
    vez del motor: «bomba de agua k4m» → «bomba de agua clio 1.6 16v», «… megane 1.6 16v»…"""
    palabras, _ = palabras_de_la_busqueda(texto)
    salida = []
    for motor in palabras:
        if not parece_designacion_de_motor(motor) or nivel_del_auto(motor) != 3:
            continue
        autos = autos_del_motor(motor)
        if not autos:
            continue
        resto = " ".join(p.lower() for p in palabras if p != motor)
        extra = " ".join(x.lower() for x in (autos["cilindrada"], autos["valvulas"]) if x)
        salida.append((motor, autos, [" ".join(x for x in (resto, m.lower(), extra) if x)
                                      for m in autos["modelos"][:3]]))
    return salida


class ResultadosDeTexto(list):
    """Lo que devuelve buscar_por_texto(): la lista de siempre, y aparte (`.aparte`) lo que no
    nombra el auto pedido (`.del_auto`) o declara otra cilindrada; `.por_que_aparte` lo dice
    para la pantalla. Es una lista para que los que ya la usaban sigan igual; ellos también
    dejan de ver las bombas de cualquier auto. `.cercanos`: si lo pedido es un código que no
    está («mfla 260»), los de esa familia con el número más cercano."""
    def __init__(self, filas=(), aparte=(), del_auto=(), por_que_aparte="", cercanos=()):
        super().__init__(filas)
        self.aparte, self.del_auto = list(aparte), list(del_auto)
        self.por_que_aparte = por_que_aparte
        self.cercanos = list(cercanos)


# ======================================================================================
# EL ÍNDICE DE LA BÚSQUEDA POR TEXTO
# ======================================================================================
# Lo pidió el dueño («hacé 3, 4, 5 y 6»; esta es la 6). Cada palabra se buscaba con un LIKE
# '%…%' sobre los 87.000 productos: unos 20 ms por palabra y por cada forma (abreviatura,
# sinónimo, singular), y una búsqueda de cuatro palabras con sus formas pasaba los 100 ms. Un
# índice por trigramas de SQLite (FTS5) encuentra exactamente lo mismo que el LIKE —medido
# palabra por palabra con la copia de la base: JUNTA 5.182, K4M 269, «1.6» 3.438, iguales— en
# 0,4 a 3 ms. Se usa solo para ACHICAR: dice qué productos pueden llegar al mínimo de palabras,
# y el puntaje y el orden siguen saliendo de la consulta de siempre, sobre esos.
# Va en un archivo aparte (28 MB con la copia de la base), al lado de la base: la copia de
# seguridad no crece, y si se pierde se vuelve a armar sola, en otro hilo (1,6 s); mientras
# tanto se busca como antes. Lo que cambia en los productos lo anota la base
# (cambios_para_el_indice, ver _esquema_busqueda) y se pone al día antes de cada búsqueda.
ARCHIVO_DEL_INDICE = "indice_de_busqueda.db"
VERSION_DEL_INDICE = "1"
# Con más cambios juntos que esto (una lista entera recién importada), conviene armarlo de nuevo.
CAMBIOS_PARA_ARMAR_DE_NUEVO = 2000
_SEPARADORES_DE_LA_BUSQUEDA = (" ", ".", "/", "-", ",")


def _estado_del_indice():
    return del_proceso("indice_de_busqueda", dict)


def _candado_del_indice():
    return del_proceso("candado_del_indice_de_busqueda", threading.Lock)


def _ruta_del_indice(ruta_base=None):
    return os.path.join(os.path.dirname(os.path.abspath(ruta_base or DB_PATH)), ARCHIVO_DEL_INDICE)


def armar_el_indice_de_busqueda(ruta_base=None):
    """Arma el índice entero desde la base, en un archivo nuevo que después reemplaza al de
    antes. Devuelve cuántos productos indexó. Lo anotado en cambios_para_el_indice se borra
    ANTES de leer los productos: lo que cambie mientras se arma queda anotado para después."""
    ruta_base = os.path.abspath(ruta_base or DB_PATH)
    ruta = _ruta_del_indice(ruta_base)
    nuevo = ruta[:-3] + ".nuevo.db"
    if os.path.exists(nuevo):
        os.remove(nuevo)
    base = sqlite3.connect(ruta_base, timeout=30)
    try:
        base.execute("DELETE FROM cambios_para_el_indice")
        base.commit()
        filas = base.execute("SELECT id, COALESCE(busqueda, ''), COALESCE(codigo_clean, '') "
                             "FROM productos").fetchall()
    finally:
        base.close()
    con = sqlite3.connect(nuevo)
    try:
        con.execute("CREATE VIRTUAL TABLE indice USING fts5(busqueda, codigo, tokenize='trigram', "
                    "content='', contentless_delete=1)")
        con.execute("CREATE TABLE datos (clave TEXT PRIMARY KEY, valor TEXT)")
        con.executemany("INSERT INTO indice(rowid, busqueda, codigo) VALUES (?, ?, ?)", filas)
        con.executemany("INSERT INTO datos VALUES (?, ?)", [
            ("version", VERSION_DEL_INDICE), ("productos", str(len(filas))),
            ("ultimo", str(max((f[0] for f in filas), default=0)))])
        con.commit()
    finally:
        con.close()
    os.replace(nuevo, ruta)
    return len(filas)


def _armar_en_otro_hilo():
    """Lo arma sin hacer esperar a nadie: mientras tanto se busca como antes."""
    estado = _estado_del_indice()
    if estado.get("armando"):
        return
    estado["armando"] = True
    ruta_base = os.path.abspath(DB_PATH)

    def trabajo():
        try:
            armar_el_indice_de_busqueda(ruta_base)
        except Exception as _err:     # noqa: BLE001 — sin índice se busca igual, más lento
            anotar_error("armar_el_indice_de_busqueda", _err)
        finally:
            with _candado_del_indice():
                vieja = estado.pop("conn", None)
                if vieja is not None:
                    vieja.close()
                estado["armando"] = False
    threading.Thread(target=trabajo, daemon=True, name="indice_de_busqueda").start()


def _poner_al_dia(con):
    """Pasa al índice lo anotado en cambios_para_el_indice. False si son demasiados."""
    with db_lock:
        c.execute(f"SELECT producto_id FROM cambios_para_el_indice ORDER BY producto_id "
                  f"LIMIT {CAMBIOS_PARA_ARMAR_DE_NUEVO + 1}")
        ids = [r[0] for r in c.fetchall()]
        if not ids:
            return True
        if len(ids) > CAMBIOS_PARA_ARMAR_DE_NUEVO:
            return False
        nuevas = []
        for tanda, marcadores in en_tandas(ids):
            c.execute(f"SELECT id, COALESCE(busqueda, ''), COALESCE(codigo_clean, '') "
                      f"FROM productos WHERE id IN ({marcadores})", tanda)
            nuevas.extend(tuple(r) for r in c.fetchall())
        cuantos, ultimo = c.execute("SELECT COUNT(*), COALESCE(MAX(id), 0) FROM productos").fetchone()
        # Todo o nada en el índice: cortado entre el borrar y el volver a escribir, esos
        # productos quedarían sin indexar.
        with con:
            con.executemany("DELETE FROM indice WHERE rowid = ?", [(i,) for i in ids])
            con.executemany("INSERT INTO indice(rowid, busqueda, codigo) VALUES (?, ?, ?)", nuevas)
            con.executemany("INSERT OR REPLACE INTO datos VALUES (?, ?)",
                            [("productos", str(cuantos)), ("ultimo", str(ultimo))])
        # Recién después se borra lo anotado: cortado acá, la próxima vez se vuelven a pasar
        # (pasarlos dos veces da lo mismo).
        with transaccion():
            c.executemany("DELETE FROM cambios_para_el_indice WHERE producto_id = ?",
                          [(i,) for i in ids])
    return True


def indice_al_dia():
    """La conexión al índice, al día con la base; o None si todavía no hay (y lo manda a
    armar). Al abrirlo se controla que tenga los mismos productos que la base: después de
    restaurar una copia no los tiene, y se arma de nuevo."""
    if os.environ.get("EQUIVALENCIAS_SIN_INDICE"):
        return None
    estado = _estado_del_indice()
    try:
        with _candado_del_indice():
            if estado.get("armando"):
                return None
            con = estado.get("conn")
            recien_abierto = con is None
            if recien_abierto:
                ruta = _ruta_del_indice()
                if not os.path.exists(ruta):
                    _armar_en_otro_hilo()
                    return None
                con = sqlite3.connect(ruta, check_same_thread=False)
            if not _poner_al_dia(con):
                con.close()
                estado.pop("conn", None)
                _armar_en_otro_hilo()
                return None
            if recien_abierto:
                datos = dict(con.execute("SELECT clave, valor FROM datos"))
                with db_lock:
                    cuantos, ultimo = c.execute(
                        "SELECT COUNT(*), COALESCE(MAX(id), 0) FROM productos").fetchone()
                if (datos.get("version"), datos.get("productos"), datos.get("ultimo")) != (
                        VERSION_DEL_INDICE, str(cuantos), str(ultimo)):
                    con.close()
                    _armar_en_otro_hilo()
                    return None
                estado["conn"] = con
            return con
    except sqlite3.Error as _err:
        anotar_error("indice_al_dia", _err)
        return None


def _frases_para(texto):
    """Lo que hay que pedirle al índice para cubrir un LIKE '%texto%' (con tres letras o más),
    o None si no se puede: los trigramas no ven menos de tres."""
    return [texto] if len(texto) >= 3 else None


def _frases_para_entera(forma):
    """Una forma que va como palabra entera, con el punto, la barra, el guion y la coma como
    espacios (ver _BUSQUEDA_CON_ESPACIOS): «1 6» se pide como «1 6», «1.6», «1/6», «1-6» y
    «1,6». Con más de dos espacios, o muy corta, None."""
    if " " not in forma:
        return _frases_para(forma)
    partes = forma.split(" ")
    if len(partes) > 3 or len(forma) < 3:
        return None
    salida = [partes[0]]
    for parte in partes[1:]:
        salida = [antes + sep + parte for antes in salida for sep in _SEPARADORES_DE_LA_BUSQUEDA]
    return salida


def _juntar_frases(frases, mas):
    return None if frases is None or mas is None else frases + mas


def productos_de_las_listas(marca_ids):
    """Los productos de esas listas (para la rama «la palabra es el nombre de la lista»)."""
    c.execute(f"SELECT id FROM productos WHERE marca_id IN ({','.join('?' * len(marca_ids))})",
              marca_ids)
    return {r[0] for r in c.fetchall()}


def candidatos_del_indice(pedidos_por_palabra, minimo):
    """Los productos que pueden llegar a `minimo` palabras según el índice, o None si no se
    puede achicar: sin índice, o cuando las palabras que el índice no sabe buscar (las de una
    o dos letras) ya alcanzan para llegar al mínimo. Cada palabra es {"frases", "ids"} o None."""
    desconocidas = sum(1 for p in pedidos_por_palabra if p is None)
    hace_falta = minimo - desconocidas
    if hace_falta <= 0:
        return None
    con = indice_al_dia()
    if con is None:
        return None
    # La cuenta la hace el índice: cada palabra es UNA consulta con sus formas unidas por OR
    # (cada producto una vez), y se juntan todas contando en cuántas aparece. Contarlo en Python
    # eran 3 millones de filas en 200 búsquedas: la mitad del tiempo.
    partes, valores = [], []
    for pedido in pedidos_por_palabra:
        if pedido is None:
            continue
        if not pedido["frases"] and not pedido["ids"]:
            continue
        de_la_palabra = []
        if pedido["frases"]:
            de_la_palabra.append("SELECT rowid AS r FROM indice WHERE indice MATCH ?")
            valores.append(" OR ".join('"' + f.replace('"', '""') + '"' for f in pedido["frases"]))
        if pedido["ids"]:
            de_la_palabra.append("SELECT value FROM json_each(?)")
            valores.append(json.dumps(sorted(pedido["ids"])))
        partes.append("SELECT r FROM (" + " UNION ".join(de_la_palabra) + ")")
    if not partes:
        return None
    try:
        return {r[0] for r in con.execute(
            "SELECT r FROM (" + " UNION ALL ".join(partes) + ") GROUP BY r HAVING COUNT(*) >= ?",
            valores + [hace_falta])}
    except sqlite3.Error as _err:
        anotar_error("candidatos_del_indice", _err)
        return None


def buscar_por_texto(texto, aflojar=True):
    """Busca por descripción de forma flexible: cada palabra tiene que aparecer en algún lado
    (descripción o código), sin importar el orden ni las tildes. Así 'ruleman delantero gol'
    encuentra 'Gol 1.6 - Ruleman de rueda delantero', y 'rótula' encuentra 'ROTULA' aunque el
    catálogo la tenga cargada sin tilde (frecuente en listas de proveedores)."""
    palabras, anio_pedido = palabras_de_la_busqueda(texto)
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
    # EL NOMBRE DE LA MARCA TAMBIÉN CUENTA. En el mostrador se buscó «mannol» y no salió nada,
    # con 81 productos de MANNOL LUBRICANTES cargados: sus descripciones dicen «Extreme 5W-40 -
    # 4L», no la marca. Ver marcas_que_nombra().
    _marcas_por_palabra = {p: marcas_que_nombra(p) for p in palabras}
    pedidos_al_indice, con_pedido = [], []      # con_pedido: la palabra de cada pedido
    for palabra in palabras:
        # También se compara contra el código sin guiones ni espacios: si alguien escribe
        # "TC421" o "tc-421", tiene que encontrar igual el producto cargado como "TC-421-15".
        # ESCAPE: sin esto, escribir «100%» o «f_ltro» devolvía 200 filas cualesquiera,
        # porque SQLite tomaba el % y el _ como comodines. Ver como_texto_en_like().
        ramas, suyos, abreviadas, de_abreviadas = [], [], [], []
        limpia = sanitizar(palabra)
        en_like = como_texto_en_like(palabra)
        # Lo que hay que pedirle al índice para cubrir cada rama (ver candidatos_del_indice()):
        # None en cuanto una rama no se puede pedir.
        frases = []
        # LAS PALABRAS DE UNA O DOS LETRAS, ENTERAS: «mb 0151» traía bulones de IMPERIAL porque
        # «MB» está adentro de CAMBA. En la copia de la base, «MB» está adentro de 9.916
        # productos y como palabra en 229; «KA» 3.211 y 865; «4» (de «ficha 4 vías») 54.790 y
        # 11.756. Tampoco se las busca adentro de los códigos.
        if len(palabra) <= 2:
            ramas.append(f"(p.busqueda LIKE ? ESCAPE '\\' AND {_BUSQUEDA_CON_ESPACIOS} LIKE ? "
                         "ESCAPE '\\')")
            suyos.extend([f"%{en_like}%", f"% {en_like} %"])
            limpia = ""
            frases = None
        # Y LOS NÚMEROS, NO ADENTRO DEL CÓDIGO DE BARRAS: «0151» estaba en el EAN de seis
        # productos que no tenían nada que ver. El código de barras entero, sí.
        elif palabra.isdigit():
            ramas.append("(p.descripcion LIKE ? ESCAPE '\\' OR p.codigo_raw LIKE ? ESCAPE '\\' "
                         "OR p.codigo_barras = ?)")
            suyos.extend([f"%{en_like}%", f"%{en_like}%", palabra])
            frases = _juntar_frases(frases, _frases_para(palabra))
        # Un LIKE '%%' coincide con TODO. Pasaba al buscar «%» o «_»: sanitizar() los deja
        # en nada, el patrón quedaba vacío y la búsqueda devolvía el catálogo entero.
        elif palabra:
            ramas.append("p.busqueda LIKE ? ESCAPE '\\'")
            suyos.append(f"%{en_like}%")
            frases = _juntar_frases(frases, _frases_para(palabra))
        if limpia:
            ramas.append("p.codigo_clean LIKE ? ESCAPE '\\'")
            suyos.append(f"%{como_texto_en_like(limpia)}%")
            frases = _juntar_frases(frases, _frases_para(limpia))
        # Y COMO LO ABREVIAN LAS LISTAS: «junta» busca también JTA y JTAS, «juego» JGO, «bomba»
        # BBA, y al revés. Ver formas_de_la_palabra().
        for forma, entera in formas_de_la_palabra(palabra):
            if entera:
                # Primero el pedazo, que es barato: los REPLACE corren solo en las filas que
                # tienen «JTA» en algún lado. Todos juntos en cada fila subían «juego juntas
                # motor» de 50 a 760 ms.
                abreviadas.append(f"(p.busqueda LIKE ? ESCAPE '\\' AND "
                                  f"{_BUSQUEDA_CON_ESPACIOS} LIKE ? ESCAPE '\\')")
                # El espacio de «1 6», en el pedazo barato, es cualquier letra: «1.6», «1,6».
                de_abreviadas.extend([f"%{como_texto_en_like(forma).replace(' ', '_')}%",
                                      f"% {como_texto_en_like(forma)} %"])
                frases = _juntar_frases(frases, _frases_para_entera(forma))
            else:
                abreviadas.append("p.busqueda LIKE ? ESCAPE '\\'")
                de_abreviadas.append(f"%{como_texto_en_like(forma)}%")
                frases = _juntar_frases(frases, _frases_para(forma))
        ids_de_la_lista = set()
        if _marcas_por_palabra.get(palabra):
            ramas.append(f"p.marca_id IN ({','.join('?' * len(_marcas_por_palabra[palabra]))})")
            suyos.extend(_marcas_por_palabra[palabra])
            ids_de_la_lista = productos_de_las_listas(tuple(_marcas_por_palabra[palabra]))
        if not ramas:
            continue        # la palabra era solo símbolos: no aporta nada para buscar
        con_pedido.append(palabra)
        pedidos_al_indice.append(None if frases is None
                                 else {"frases": frases, "ids": ids_de_la_lista})
        # Cada palabra vale 1000 si está, y 1 más si está tal cual se escribió: así una sola
        # cuenta da las coincidencias (÷ 1000) y cuántas no hizo falta adivinar (el resto), sin
        # recorrer la tabla dos veces. «jgo descarbonizacion palio» sacaba la «JGO DESCARB…»
        # del puesto 2 al 42, debajo de los «JUEGO …» más cortos.
        puntajes.append("(CASE WHEN " + " OR ".join(ramas) + " THEN 1001"
                        + (" WHEN " + " OR ".join(abreviadas) + " THEN 1000" if abreviadas else "")
                        + " ELSE 0 END)")
        params.extend(suyos + de_abreviadas)
    if not puntajes:
        return []
    suma = " + ".join(puntajes)

    # Con una o dos palabras se piden todas (si no, aparece cualquier cosa). Con tres o más
    # alcanza con que coincida la mayoría: es lo que permite "interpretar" y no fallar por una.
    utiles = len(puntajes)
    minimo = utiles if utiles <= 2 else max(2, (utiles * 2) // 3)

    _fabricante = campo_opcional_de_producto(c, "marca_repuesto", "Fabricante")
    # Dónde está en el depósito, si se cargó: «📍 Estante 4» al lado del stock. Lo pidió una
    # revisión con ChatGPT («ubicación física del repuesto, y desde la búsqueda»).
    _ubicacion = campo_opcional_de_producto(c, "ubicacion", "Ubicación")
    # Siempre al menos uno, para que el IN () no quede vacío.
    # Y el código escrito con espacio, entero: «oc 305» es OC305 (ver «EL CÓDIGO ESCRITO CON
    # ESPACIO, PRIMERO»), también si es de fábrica.
    _junto = sanitizar("".join(palabras))
    _codigos_escritos = [sanitizar(p) for p in palabras if sanitizar(p)] + [_junto]
    # UNA pasada por la tabla: las coincidencias se cuentan una vez (antes se calculaban en el
    # SELECT y otra vez en el WHERE), y se trae de una lo que llega al mínimo aflojado; el
    # mínimo de verdad se aplica después, sin volver a recorrer (ver el aflojado más abajo).
    # Medido con 63 proveedores (659.000 productos), mismos resultados: la mediana de 365 a
    # 333 ms y la peor de 594 a 450 ms (la que no encuentra todas las palabras: eran 2 pasadas).
    minimo_flojo = minimo - 1 if (utiles >= 2 and minimo > 1) else minimo
    # El índice achica (ver candidatos_del_indice()): primero a los que pueden llegar al mínimo
    # DE VERDAD; si con eso no queda ninguno con el mínimo, a los que pueden llegar al flojo,
    # que es el corte de la consulta. Lo que se muestra sale igual que sin índice: lo que llega
    # al mínimo está en los dos, y va primero en el orden. Sin índice, la consulta de siempre.
    _candidatos = candidatos_del_indice(pedidos_al_indice, minimo)
    query = f'''
    SELECT * FROM (
    SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
           m.nombre AS "Marca", m.tipo AS "Tipo",
           -- Quién FABRICA la pieza, que es otra cosa que la lista de quién te la vende. En el
           -- mostrador, entre cinco equivalentes, la pregunta es «¿cuál es el Bosch?».
           -- Ver marca_de_repuesto_en(): sale del final de la descripción, 13.705 productos.
           -- Va por campo_opcional_de_producto() y no directo: contra una base que todavía no
           -- tiene la columna, nombrarla acá tumba el buscador entero.
           {_fabricante},
           p.precio AS "Precio", p.stock AS "Stock", {_ubicacion},
           p.favorito AS "Favorito", ({suma}) AS _puntaje,
           LENGTH(p.descripcion) AS _largo, p.codigo_barras AS _barras
    FROM productos p JOIN marcas m ON m.id = p.marca_id
    WHERE 1 {{por_el_indice}}
      -- Los códigos de fábrica copian la descripción de la fila que los nombró: buscando
      -- «motor de arranque corsa» salía el arranque y, abajo, sus veinte números de Bosch con
      -- la misma descripción. No son algo que se venda: solo si se escribe el código exacto.
      AND (m.tipo <> 'OEM' OR p.codigo_clean IN ({",".join("?" * len(_codigos_escritos))}))
    ) WHERE _puntaje >= ?
    ORDER BY _puntaje DESC, _largo, "Marca" LIMIT 400;
    '''
    def _consultar(candidatos, umbral=None):
        with db_lock:
            c.execute(query.replace("{por_el_indice}", "" if candidatos is None else
                                    "AND p.id IN (SELECT value FROM json_each(?))"),
                      params + ([] if candidatos is None else [json.dumps(sorted(candidatos))])
                      + _codigos_escritos
                      + [minimo_flojo * 1000 if umbral is None else umbral])
            salida = filas_a_listas(c)
        for f in salida:
            f["_coincidencias"], f["_tal_cual"] = divmod(f.pop("_puntaje"), 1000)
        return salida
    todas = _consultar(_candidatos)
    if (_candidatos is not None and minimo_flojo < minimo
            and not any(f["_coincidencias"] >= minimo for f in todas)):
        todas = _consultar(candidatos_del_indice(pedidos_al_indice, minimo_flojo))
    # Lo que llega al mínimo va primero por el orden; si no hay nada, queda lo aflojado.
    # Sin cortar en 200 todavía: el corte va después del orden de abajo, que sabe de
    # palabras enteras y abreviaturas. Cortando acá, las «Jta mult. Adm.» quedaban afuera
    # buscando «junta multiple admision», detrás de 141 que dicen «JUNTA» adentro de otra.
    filas = [f for f in todas if f["_coincidencias"] >= minimo]
    # El código escrito con espacio (ver «EL CÓDIGO ESCRITO CON ESPACIO, PRIMERO»).
    exactos = []
    if len(palabras) >= 2 and re.search(r"\d", _junto) and re.search(r"[A-Z]", _junto):
        c.execute("SELECT id FROM productos WHERE codigo_clean = ?", (_junto,))
        _ids_exactos = {r[0] for r in c.fetchall()}
        if _ids_exactos:
            exactos = _consultar(_ids_exactos, umbral=0)
    # Las palabras de las que se vio TODO lo que las dice: la consulta corta en 400, y lo que
    # quedó afuera puede decirlas (ver «UN NÚMERO PEDIDO QUE NO DICE NINGUNO»).
    vistas_enteras = set(palabras) if len(todas) < 400 else set()
    # Si pidiendo TODAS las palabras no aparece nada, se afloja y se pide una menos.
    # Con dos palabras se exigían las dos, y «rótula suspensión» devolvía CERO resultados
    # sobre un catálogo lleno de rótulas: ninguna descripción dice las dos cosas juntas.
    # Cero resultados es la peor respuesta posible —el de adelante concluye que no hay, y
    # hay— así que es mejor mostrar lo que coincide en parte y que decida la persona.
    # Con las palabras que CUENTAN, no con todas las escritas: «QQQZZZ °» son dos palabras
    # pero una sola útil, y aflojar a «0 coincidencias» devolvía 200 productos cualquiera
    # (lo encontró la revisión independiente del buscador). Nunca se pide menos de una.
    # aflojar=False es para el buscador de CÓDIGOS (ver «kit 22382» en buscador.py): ahí
    # una sola de las dos palabras traía 200 productos cualesquiera.
    if aflojar and not filas and utiles >= 2 and minimo > 1:
        # LA PALABRA MÁS RARA, PRIMERO. Aflojado, cada fila dice una palabra menos, y entraban las
        # 400 más cortas: «aceite 10w40» traía aceites y ninguno de los diez «Classic 10W-40»
        # (que no dicen «aceite»), porque hay miles que dicen «aceite» y esos van tal cual. Ahora
        # se trae palabra por palabra, la más rara primero (lo dice el índice: sin índice, como
        # antes).
        _por_palabra = [] if _candidatos is None or None in pedidos_al_indice else [
            candidatos_del_indice([pedido], 1) for pedido in pedidos_al_indice]
        if _por_palabra and None not in _por_palabra:
            _vistos, todas = set(), []
            for _palabra, _ids in sorted(zip(con_pedido, _por_palabra), key=lambda x: len(x[1])):
                _de_esta = _consultar(_ids)
                if len(_de_esta) < 400:
                    vistas_enteras.add(_palabra)
                for f in _de_esta:
                    if f["ID"] not in _vistos:
                        _vistos.add(f["ID"])
                        f["_rareza"] = len(_ids)
                        todas.append(f)
        filas = todas

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
    de_la_pieza = palabras_de_la_pieza(texto)
    if familia_pedida != "Sin clasificar":
        del_rubro, sin_clasificar, de_otro_rubro = [], [], []
        for f in filas:
            fam = clasificar_repuesto(f.get("Descripcion") or "")
            # El rubro sale de la PRIMERA pieza que se nombra, y el orden cambia: «porta bancada
            # reten» es de Motor (BANCADA) y «PORTA RETEN BANCADA MAXION» de Retenes (RETEN), y
            # se descartaba diciendo las tres palabras. Lo que dice la pieza pedida es del rubro.
            if fam == familia_pedida or (de_la_pieza and all(dice_la_palabra(f, p)
                                                             for p in de_la_pieza)):
                del_rubro.append(f)
            elif fam == "Sin clasificar":
                sin_clasificar.append(f)
            else:
                de_otro_rubro.append(f)
        # Solo se descarta lo de otro rubro si quedó algo del rubro pedido; si no, es mejor
        # mostrar todo que dejar la pantalla vacía.
        if del_rubro:
            filas = del_rubro + sin_clasificar

    # EL AÑO NO SE BUSCA COMO TEXTO: las listas escriben «2008-2011» o «2010/15», casi nunca
    # «2012». Se descarta solo lo que declara OTROS años (ver sirve_para_anio()); lo que no
    # dice años se deja.
    if anio_pedido:
        filas = [f for f in filas if sirve_para_anio(f.get("Descripcion") or "", anio_pedido)
                 is not False]
    # LA PALABRA ENTERA PRIMERO. El LIKE encuentra «GOL» adentro de «GOLF», y con el mismo
    # número de coincidencias ganaba la descripción más corta: «junta de tapa de cilindros
    # gol» traía primero las del Golf, y «filtro de aceite para Gol 1.6» un «Filtro para
    # aceite sellado» que no dice ningún auto. Ahora, a igual cantidad de palabras, va primero
    # la que las tiene como palabra entera.
    # Una abreviatura de las listas cuenta como la palabra: «JTA TAPA GOL» va antes que «JUNTA
    # TAPA GOLF» buscando «junta tapa gol». Y a igual cantidad, la que la tiene tal cual.
    def _enteras(f):
        crudo = normalizar_texto(f"{f.get('Descripcion') or ''} {f.get('Codigo') or ''}")
        texto_fila = " " + re.sub(r"[^A-Z0-9.]+", " ", crudo) + " "
        sin_puntos = " " + re.sub(r"[^A-Z0-9]+", " ", crudo) + " "
        # El punto pegado también separa: «Jgo.Descarbonizacion» tiene las dos enteras.
        return sum(1 for p in palabras if f" {p} " in texto_fila or f" {p} " in sin_puntos
                   or any(f" {forma} " in sin_puntos for forma, _ in formas_de_la_palabra(p)))
    # Y A IGUAL CANTIDAD, LA PIEZA ANTES QUE SU ACCESORIO: «bomba de agua k4m» traía primero
    # «JTA BBA AGUA RENAULT K4M», la junta de la bomba, que dice las tres cosas. Como en el
    # Modo Mecánico (ver _ACCESORIO_DE_LA_PIEZA): no se esconde, va después; salvo que el
    # accesorio sea lo pedido («junta tapa»).
    def _es_accesorio(f):
        hallado = _RE_ACCESORIO.match(normalizar_texto(f.get("Descripcion") or "").lstrip())
        return bool(hallado) and not any(
            dice_la_palabra({"Descripcion": hallado.group(1)}, p) for p in palabras)
    filas.sort(key=lambda f: (-f.get("_coincidencias", 0), f.get("_rareza", 0),
                              _es_accesorio(f), -_enteras(f),
                              -f.get("_tal_cual", 0), f.get("_largo") or 0))
    # Lo que no nombra el auto pedido, aparte (ver nivel_del_auto()). Cada fila apartada dice
    # por qué («Por qué»), y lo apartado va en el orden de antes, el de parecido: antes se cortaba
    # en 200 por regla y lo más parecido —«CHEVROLET CORSA NAFTA» buscando «filtro de nafta
    # corsa»— quedaba afuera hasta del desplegable.
    for puesto, f in enumerate(filas):
        f["_puesto"] = puesto
    del_auto, aparte, no_dicen, motivos = palabras_del_auto(palabras), [], [], []
    if del_auto:
        nombran = [nombra_alguna(f, del_auto) for f in filas]
        if any(nombran) and not all(nombran):
            aparte = [f for f, n in zip(filas, nombran) if not n]
            for f in aparte:
                f["Por qué"] = "no dice " + " ni ".join(f"«{p.lower()}»" for p in del_auto)
            filas = [f for f, n in zip(filas, nombran) if n]
            no_dicen.append(" ni ".join(f"«{p.lower()}»" for p in del_auto))
    # Lo que no nombra la pieza pedida (ver palabras_de_la_pieza()).
    if de_la_pieza:
        la_dicen = [all(dice_la_palabra(f, p) for p in de_la_pieza) for f in filas]
        if any(la_dicen) and not all(la_dicen):
            for f, d in zip(filas, la_dicen):
                if not d:
                    f["Por qué"] = f"no dice «{pieza_que_nombra(texto).lower()}»"
                    aparte.append(f)
            filas = [f for f, d in zip(filas, la_dicen) if d]
            no_dicen.append(f"«{pieza_que_nombra(texto).lower()}»")
    # Y lo que declara otra cilindrada u otras válvulas (ver cilindradas_que_declara()).
    for patron, declara, que, como in (
            (_RE_CILINDRADA, cilindradas_que_declara, "otra cilindrada",
             lambda p: f"{p[0]}.{p[2]}"),
            (_RE_VALVULAS, valvulas_que_declara, "otras válvulas", lambda p: p)):
        pedida = next((como(p) for p in palabras if patron.fullmatch(p)), None)
        # Si lo único del auto era esto, la regla de arriba ya apartó lo que no lo dice.
        if not pedida or any(patron.fullmatch(p) for p in del_auto):
            continue
        declaradas = [declara(f) for f in filas]
        otra = [bool(d) and pedida not in d for d in declaradas]
        if any(otra) and not all(otra):
            for f, o, d in zip(filas, otra, declaradas):
                if o:
                    f["Por qué"] = f"es {' / '.join(sorted(d))}"
                    aparte.append(f)
            filas = [f for f, o in zip(filas, otra) if not o]
            motivos.append(f"son de {que}, no {pedida}")
    # UN NÚMERO PEDIDO QUE NO DICE NINGUNO. En las búsquedas reales: «kit 22382» traía 200 kits,
    # «mb 0151» kits de Mercedes, «rodamiento 6205» extractores de rulemán. El número es lo que
    # identifica lo pedido: si ningún resultado lo dice, lo que queda va aparte y adelante no
    # queda nada: la pantalla dice que no está. No el número del auto (un modelo, un motor: ver
    # nivel_del_auto()), ni la cilindrada o las válvulas, que tienen su regla. Y solo si se vio
    # todo lo que dice el número (`vistas_enteras`): si no, lo que lo dice puede haber quedado
    # afuera.
    # Si lo pedido es un código de una familia del catálogo —«mfla 260»: hay MFLA 258, 272,
    # 276—, tiene que decir el código, no el número suelto: traía 191 cosas que dicen 260 (un
    # motor Ford 225/260/289). Solo con una familia: «aceite 10w40» encuentra «Classic 10W-40 -
    # 1L», que no dice «aceite»; una marca de auto no es una familia («ford 260» es el motor); y
    # solo con dos palabras: en «sensor maf 320» o «bobina bosch 500», MAF y BOSCH son parte de
    # la descripción, aunque también haya códigos MAF y BOSCH.
    _cercano, cercanos = {}, []
    for p in palabras:
        if (len(p) < 3 or not re.search(r"\d", p) or p in del_auto
                or _RE_CILINDRADA.fullmatch(p) or _RE_VALVULAS.fullmatch(p)):
            continue
        familia = {q: familia_de_codigos(q, int(p)) for q in palabras
                   if len(palabras) == 2 and p.isdigit() and q.isalpha() and len(q) >= 2
                   and not nivel_del_auto(q)}
        familia = {q: cerca for q, cerca in familia.items() if cerca}
        if not familia and p not in vistas_enteras:
            continue
        if not filas or any(_dice_el_codigo(f, familia, p) if familia else _dice_el_numero(f, p)
                            for f in filas + aparte + exactos):
            continue
        pedido = " ".join([*familia, p]).lower()
        for f in filas:
            f["Por qué"] = f"no dice «{pedido}»"
        # De la familia, primero lo más cercano: «no tengo el MFLA 260; tengo el 258». Se ofrece
        # en la pantalla como otros códigos (ver .cercanos), nunca como el pedido.
        cercanos = sorted((f for cerca in familia.values() for f in cerca),
                          key=lambda f: f["_a"])[:8]
        for q in familia:
            for f in filas + aparte:
                n = _numero_en_la_familia(f, q)
                if n is not None and id(f) not in _cercano:
                    _cercano[id(f)] = abs(n - int(p))
                    f["Por qué"] = f"es otro: a {_cercano[id(f)]} del {int(p)}"
        aparte, filas = filas + aparte, []
        no_dicen.append(f"«{pedido}»")
        break
    aparte.sort(key=lambda f: (_cercano.get(id(f), float("inf")), f["_puesto"]))
    # EL CÓDIGO ESCRITO CON ESPACIO, PRIMERO. «oc 305» o «mfla 258» por descripción: es un
    # código. De 150 así sacados de las listas, 59 no salían primero y 18 ni aparecían («oc» lo
    # dicen miles de descripciones).
    if exactos:
        _ya = {f["ID"] for f in exactos}
        filas = exactos + [f for f in filas if f["ID"] not in _ya]
        aparte = [f for f in aparte if f["ID"] not in _ya]
    filas, aparte = filas[:200], aparte[:200]
    for f in filas + aparte:
        f.pop("_puesto", None)
        f.pop("_coincidencias", None)
        f.pop("_rareza", None)
        f.pop("_barras", None)
        f.pop("_tal_cual", None)
        f.pop("_largo", None)
    # «no dicen «gol» o «embrague», o son de otra cilindrada, no 1.6»
    if no_dicen:
        motivos.insert(0, "no dicen " + " o ".join(no_dicen))
    return ResultadosDeTexto(filas, aparte, del_auto if no_dicen and del_auto and aparte else (),
                             ", o ".join(motivos), cercanos)


# Las palabras que no buscan nada: «necesito pastillas delanteras para un Corsa Classic
# 2012» son ocho palabras, y con «necesito», «para» y «un» adentro se exigían cinco
# coincidencias: daba cero. «UNO» no está: es un Fiat.
PALABRAS_DE_RELLENO = {"NECESITO", "NECESITA", "NECESITAN", "QUIERO", "BUSCO", "BUSCA", "TENES",
                       "TENGO", "TIENE", "TIENEN", "HAY", "PARA", "POR", "CON", "UN", "UNA", "EL",
                       "LA", "LOS", "LAS", "DE", "DEL", "AL", "A", "Y", "O", "QUE", "ME", "MI",
                       "SE", "LE", "LO", "ES", "SI", "TE", "CUAL", "CUANTO", "ALGUN",
                       "ALGUNA", "DAME", "PASAME", "FAVOR", "HOLA"}


def palabras_de_la_busqueda(texto):
    """(palabras para buscar, año pedido o None). Sin signos en las puntas («¿Qué», «1.6?»),
    sin las palabras de relleno (si queda alguna otra) y sin el año, que se usa para filtrar."""
    palabras = [normalizar_texto(re.sub(r"^[^\w]+|[^\w]+$", "", p))
                for p in str(texto or "").upper().split()]
    palabras = [p for p in palabras if p]
    anio = None
    for p in palabras:
        if re.fullmatch(r"(19[5-9]\d|20[0-4]\d)", p) and len(palabras) > 1:
            anio = int(p)
    utiles = [p for p in palabras if p not in PALABRAS_DE_RELLENO and p != str(anio)]
    return (utiles or [p for p in palabras if p != str(anio)] or palabras), anio


# ERRORES DE TIPEO. En el mostrador se escribe rápido: «bomba de agau gol» traía juntas y bombas
# de lavaparabrisas —«agau» no está en ningún producto, así que buscaba solo «bomba» y «gol»—.
# Se corrige SOLO lo que no puede encontrar nada: una palabra que no aparece en ninguna
# descripción, ni siquiera adentro de otra, ni es el nombre de una lista. Y solo si a un tecleo
# de distancia hay una que el catálogo sí usa. Lo escrito bien no se toca nunca, y la pantalla
# dice qué se cambió.
_LETRAS_DE_UNA_PALABRA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
# Cuántos productos tiene que tener la palabra correcta para proponerla: con menos, lo que hay
# es otro error de tipeo del proveedor, no una palabra del rubro.
MINIMO_DE_PRODUCTOS_PARA_CORREGIR = 3


@st.cache_data(show_spinner=False, max_entries=2)
def vocabulario_de_busqueda(version):   # ver descripciones_por_palabra(): sin guion bajo
    """{palabra sin acentos: en cuántos productos aparece}, sacado de descripciones_por_palabra()."""
    salida = {}
    for palabra, cuantos in descripciones_por_palabra(version).items():
        clave = normalizar_texto(palabra)
        salida[clave] = salida.get(clave, 0) + cuantos
    return salida


def dejar_listo_de_antemano():
    """Arma por atrás, una vez por proceso y apenas arranca la app, lo que si no paga la primera
    persona que lo pide.

    1. vocabulario_de_busqueda(). Lo pedía palabras_corregidas() en cada búsqueda con una
       palabra de cuatro letras o más, o sea en casi todas, aunque no hubiera nada mal escrito.
       Medido con la copia de la base real: la primera búsqueda después de cada reinicio
       («bomba de agua») tardaba 0,94 s solo en esto, y la segunda 0,03. El servidor se
       reinicia seguido, y la primera búsqueda es la de alguien que está en el mostrador. De
       paso queda el conteo de palabras que usa «🚙 Repuestos por vehículo».
    2. marcas_vehiculo_disponibles(), que se guarda en la base pero se rehace cuando cambió el
       catálogo: con la copia real, 1,3 s del primero que abría «🚙 Repuestos por vehículo»
       —que se abre sin contraseña— después de cargar una lista.
    0. Antes que todo, las bibliotecas de las tablas (pandas y pyarrow). La app no las usa
       directamente: Streamlit las carga recién con la primera tabla que dibuja, y esa primera
       tabla —la de los resultados de la primera búsqueda por texto, casi siempre— tardaba
       0,37 s en vez de 2 ms. Se importan acá, en el hilo de atrás, y quedan para todos.

    Antes de cada paso espera a que termine de dibujarse la pantalla (ver ceder_al_mostrador()),
    así no le quita el procesador a nadie. Si alguien lo pide mientras se arma, Streamlit no lo
    hace dos veces: espera al que ya está armándose. Y si falla, lo arma quien lo pida."""
    lanzado = del_proceso("lo_de_antemano_lanzado", threading.Event)
    if lanzado.is_set():
        return
    lanzado.set()

    def _armar():
        _HILO_DE_FONDO.corriendo = True
        try:
            ceder_al_mostrador()
            import pandas    # noqa: F401 — ver el punto 0 de arriba
            import pyarrow   # noqa: F401
            ceder_al_mostrador()
            version = version_del_catalogo()
            vocabulario_de_busqueda(version)
            ceder_al_mostrador()
            marcas_vehiculo_disponibles(version)
        except Exception as _err:     # noqa: BLE001 — es una ayuda: si falla, lo arma quien lo pida
            anotar_error("dejar_listo_de_antemano", _err)
    threading.Thread(target=_armar, daemon=True, name="de_antemano").start()


def _a_un_tecleo(palabra):
    """Las palabras a un tecleo de distancia: una letra de menos, una de más, una cambiada, o dos
    vecinas al revés («AGAU» → «AGUA», que es el error más común escribiendo rápido)."""
    cortes = [(palabra[:i], palabra[i:]) for i in range(len(palabra) + 1)]
    salida = {a + b[1:] for a, b in cortes if b}
    salida |= {a + b[1] + b[0] + b[2:] for a, b in cortes if len(b) > 1}
    salida |= {a + letra + b[1:] for a, b in cortes if b for letra in _LETRAS_DE_UNA_PALABRA}
    salida |= {a + letra + b for a, b in cortes for letra in _LETRAS_DE_UNA_PALABRA}
    salida.discard(palabra)
    return salida


def palabras_corregidas(texto):
    """{escrita: corregida} para las palabras de la búsqueda con un error de tipeo seguro. Ver
    _LETRAS_DE_UNA_PALABRA: solo las que hoy no pueden encontrar nada."""
    palabras, _ = palabras_de_la_busqueda(texto)
    candidatas = [p for p in palabras if len(p) >= 4 and p.isalpha()]
    if not candidatas:
        return {}
    # Es una ayuda: si algo falla acá, se busca lo escrito, como antes.
    try:
        vocabulario = vocabulario_de_busqueda(version_del_catalogo())
    except Exception as _err:
        anotar_error("palabras_corregidas", _err)
        return {}
    salida = {}
    for palabra in candidatas:
        if palabra in vocabulario or any(palabra in w for w in vocabulario):
            continue           # está, aunque sea adentro de otra: el LIKE la encuentra
        if marcas_que_nombra(palabra):
            continue           # es el nombre de una lista («mannol»)
        if any(forma in vocabulario for forma, _ in formas_de_la_palabra(palabra)):
            continue           # la encuentra otra forma: «sopapa» es VALVULA, no SOLAPA
        opciones = [(vocabulario[w], w) for w in _a_un_tecleo(palabra)
                    if vocabulario.get(w, 0) >= MINIMO_DE_PRODUCTOS_PARA_CORREGIR]
        if opciones:
            salida[palabra] = max(opciones)[1]
    return salida


def texto_con_las_correcciones(texto, correcciones):
    """El texto como se escribió, con las palabras de palabras_corregidas() cambiadas y el resto
    igual —«de», el año, los signos—, para que la búsqueda lo lea como lo leería sin el error."""
    if not correcciones:
        return texto
    trozos = []
    for trozo in str(texto or "").split():
        limpio = normalizar_texto(re.sub(r"^[^\w]+|[^\w]+$", "", trozo.upper()))
        trozos.append(correcciones.get(limpio, trozo))
    return " ".join(trozos)


def palabras_que_no_aparecen(texto, filas):
    """Las palabras pedidas que no dice ninguno de los resultados: «pastillas» en un catálogo
    sin pastillas de freno. Para decirlo, en vez de mostrar «Corsa Classic» sin explicar por
    qué no hay lo que se pidió."""
    palabras, _ = palabras_de_la_busqueda(texto)
    juntos = " ".join(normalizar_texto(f"{f.get('Descripcion') or ''} {f.get('Codigo') or ''} "
                                       f"{f.get('Marca') or ''}") for f in filas)
    # Con las otras formas, como las encuentra la búsqueda (ver dice_la_palabra()): «semieje
    # gol» trae palieres, y el aviso decía que ninguno dice «semieje».
    return [p for p in palabras if len(p) >= 3 and p not in juntos
            and not any(dice_la_palabra(f, p) for f in filas)]

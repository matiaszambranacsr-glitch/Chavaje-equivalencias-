"""Lo que sabe de AUTOS y de tipos de repuesto: marcas de vehículo, familias de pieza, y cómo
leer una descripción de proveedor para sacar de ahí el modelo, los años y las medidas.

Se usa para dos cosas distintas y conviene no confundirlas:
  - despegar texto que vino sin espacios ('DespieceCHEVROLETCAPUCHON'), que es limpieza y se
    puede aplicar siempre;
  - DEDUCIR datos (medidas, aplicaciones), que es suponer, y por eso cada función de acá es
    conservadora a propósito: ante la duda no devuelve nada."""
import re
import unicodedata

from .errores import anotar_error
from .codigos import normalizar_texto, sanitizar


# Se ordena de más largo a más corto para que gane la coincidencia más específica:
# "LAND ROVER" tiene que ganarle a "ROVER", y "MERCEDES BENZ" a "MERCEDES".
# No se agregan marcas de 2 letras (MG, DS) porque en una descripción de repuesto casi siempre
# son otra cosa (medidas, siglas) y ensuciarían más de lo que aportan.
MARCAS_VEHICULO = sorted(set([
    # --- Las que ya estaban ---
    "MERCEDES BENZ", "M.BENZ", "MERCEDES", "VOLKSWAGEN", "CHEVROLET", "MITSUBISHI", "LAND ROVER",
    "MASSEY FERGUSON", "M. FERGUSON", "AGCO SISU POWER", "JOHN DEERE", "NEW HOLLAND", "ALFA ROMEO",
    "CITROEN", "PEUGEOT", "RENAULT", "CHRYSLER", "CUMMINS", "PERKINS", "ILLINOIS", "TOYOTA",
    "NISSAN", "HYUNDAI", "DAEWOO", "SUZUKI", "SCANIA", "IVECO", "AGRALE", "DEUTZ", "VOLVO",
    "HONDA", "DODGE", "BURMOR", "M.W.M.", "M.W.M", "MWM", "KNORR", "VARGA", "VALTRA", "ZANELLO",
    "PAUNY", "FIAT", "FORD", "JEEP", "AUDI", "SEAT", "BMW", "KIA", "MAN", "DAF", "HINO",
    "ISUZU", "CASE", "GM",
    # --- Chinas, que hoy son parte del parque argentino ---
    "GREAT WALL", "DONGFENG", "SHINERAY", "CHANGAN", "BAIC", "CHERY", "GEELY", "HAVAL",
    "FOTON", "LIFAN", "JINBEI", "MAXUS", "JETOUR", "SOUEAST", "BYD", "JAC",
    # --- Coreanas, japonesas y del resto de Asia ---
    "SSANGYONG", "MAHINDRA", "SUBARU", "DAIHATSU", "LEXUS", "INFINITI", "ACURA", "GENESIS",
    "MAZDA", "TATA", "PROTON",
    # --- Europeas que faltaban ---
    "VAUXHALL", "LAMBORGHINI", "ROLLS ROYCE", "ASTON MARTIN", "MASERATI", "PORSCHE", "FERRARI",
    "BENTLEY", "SKODA", "LANCIA", "JAGUAR", "DACIA", "OPEL", "SMART", "MINI", "LADA", "ROVER",
    "ZASTAVA", "YUGO", "TALBOT", "SAAB", "LOTUS", "MCLAREN",
    # --- Norteamericanas ---
    "INTERNATIONAL", "FREIGHTLINER", "WESTERN STAR", "OLDSMOBILE", "KENWORTH", "PETERBILT",
    "PLYMOUTH", "CADILLAC", "PONTIAC", "LINCOLN", "MERCURY", "SATURN", "NAVISTAR", "BUICK",
    "TESLA", "MACK", "GMC", "RAM",
    # --- Camiones, ómnibus, agro e industria ---
    "MERCEDES-BENZ", "LANDINI", "MARCOPOLO", "METALPAR", "RASTROJERO", "CATERPILLAR", "YANMAR",
    "KUBOTA", "CLAAS", "FENDT", "JCB", "VETRA", "APACHE", "SEVEL", "SIAM", "DI TELLA",
    # --- Motos ---
    "ROYAL ENFIELD", "HARLEY DAVIDSON", "MOTO GUZZI", "MV AGUSTA", "KAWASAKI", "HUSQVARNA",
    "MOTOMEL", "GUERRERO", "ZANELLA", "KYMCO", "APRILIA", "YAMAHA", "DUCATI", "PIAGGIO",
    "BENELLI", "CORVEN", "KELLER", "GILERA", "MONDIAL", "BAJAJ", "VESPA", "KTM", "SYM",
    "HERO", "TVS", "BETA",
    # --- Abreviaturas que las listas escriben todo el tiempo ---
    # Sin «VW» la app no tenía Volkswagen: 5.530 descripciones lo escriben así y ninguna dice
    # VOLKSWAGEN, o sea que 6.348 productos —Gol, Polo, Amarok, Suran— no aparecían en la
    # pantalla de vehículos ni existían para la detección de modelos. Las otras salieron de
    # contar cuántas descripciones reales las usan como palabra suelta.
    "VW", "CHEV", "PEUG", "PEU", "REN", "TOY", "CITR", "HYUN",
]), key=len, reverse=True)


# La misma marca escrita de varias formas es UNA marca. Sin esto el desplegable mostraba
# «MERCEDES BENZ», «M.BENZ», «MERCEDES» y «MERCEDES-BENZ» como si fueran cuatro autos
# distintos, cada uno con una parte del catálogo.
ALIAS_MARCA_VEHICULO = {
    "VW": "VOLKSWAGEN", "CHEV": "CHEVROLET", "PEUG": "PEUGEOT", "PEU": "PEUGEOT",
    "REN": "RENAULT", "TOY": "TOYOTA", "CITR": "CITROEN", "HYUN": "HYUNDAI",
    "M.BENZ": "MERCEDES BENZ", "MERCEDES": "MERCEDES BENZ", "MERCEDES-BENZ": "MERCEDES BENZ",
    "M. FERGUSON": "MASSEY FERGUSON", "M.W.M.": "MWM", "M.W.M": "MWM",
}


# Todas las formas de escribir cada marca, para poder prefiltrar en SQL: buscar «VOLKSWAGEN»
# en la base se perdería los 5.530 productos que dicen «VW».
def _escrituras_por_marca():
    salida = {}
    for marca in MARCAS_VEHICULO:
        salida.setdefault(ALIAS_MARCA_VEHICULO.get(marca, marca), []).append(marca)
    return salida


ESCRITURAS_DE_MARCA = _escrituras_por_marca()


# UN solo regex con todas las marcas en vez de uno por marca. Medido sobre las 61.574
# descripciones reales: 15,2 s recorriendo marca por marca contra 2,1 s así, siete veces más
# rápido, y es la función que corre una vez por producto en toda la pantalla de vehículos.
# Las marcas van de más larga a más corta (así lo deja MARCAS_VEHICULO), que es lo que hace
# que en la misma posición gane «MERCEDES BENZ» antes que «MERCEDES».
# El borde excluye letras Y dígitos: sin los dígitos, «MAN» aparecía adentro de un número de
# parte. Con letras solas ya no entraba en MANGUERA, pero sí en cosas como GM1234.
# Y va en IGNORECASE. Antes se comparaba con la marca tal cual, en mayúsculas, contra el texto
# tal cual venía: «BUJIA NAFTA Ford Escort - VW Gol» encontraba VW pero no Ford, porque el
# proveedor lo escribió con minúsculas. Media lista de FISPA está escrita así.
_RE_MARCAS_VEHICULO = re.compile(
    r'(?<![A-Za-zÁÉÍÓÚÑ0-9])(' + "|".join(re.escape(_m) for _m in MARCAS_VEHICULO)
    + r')(?![A-Za-zÁÉÍÓÚÑ0-9])', re.IGNORECASE)


def marcas_vehiculo_en(descripcion):
    """TODOS los autos que nombra una descripción: [(marca, categoría, resto), ...].

    Una descripción de proveedor rara vez habla de un solo auto: «BUJIA NAFTA Ford Escort -
    VW Gol - Kombi - Parati». Son 11.874 de las 61.574 descripciones reales (el 19%) las que
    nombran dos marcas o más. Antes la app se quedaba con UNA —la que primero apareciera en
    la lista de marcas, que está ordenada por largo, o sea prácticamente al azar— y el
    producto desaparecía del catálogo de las otras. Se medía feo: CITROEN mostraba 1.831 de
    los 5.106 productos que lo nombran, OPEL 156 de 2.679, PEUGEOT 1.433 de 5.139.

    El «resto» de cada marca va hasta la marca siguiente, así que es lo que le corresponde a
    ESE auto: en el ejemplo, «Escort» para Ford y «Gol - Kombi - Parati» para Volkswagen.
    La «categoría» —el nombre de la pieza— es la misma para todas: es lo que va antes de la
    primera marca."""
    if not descripcion:
        return []
    texto = separar_texto_pegado(str(descripcion))
    encontradas = list(_RE_MARCAS_VEHICULO.finditer(texto))
    if not encontradas:
        return []
    categoria = texto[:encontradas[0].start()].strip(" -,/") or None
    salida = []
    vistas = set()
    for i, m in enumerate(encontradas):
        escrita = m.group(1).upper()
        canonica = ALIAS_MARCA_VEHICULO.get(escrita, escrita)
        if canonica in vistas:
            continue          # «Ford ... Ford» es un solo Ford
        vistas.add(canonica)
        hasta = encontradas[i + 1].start() if i + 1 < len(encontradas) else len(texto)
        salida.append((canonica, categoria, texto[m.end():hasta].strip(" -,/") or None))
    return salida


# Marcas que se usan para despegar descripciones. Se dejan solo las de 5 letras o más y se
# excluyen las que además son palabras comunes del rubro: separar por "MAN" partiría MANGUERA
# en "MAN GUERA", y por "RAM" partiría RAMAL. Con las largas el riesgo desaparece y son
# justamente las que aparecen pegadas en las listas (VOLKSWAGEN, CHEVROLET, MITSUBISHI...).
_MARCAS_RIESGOSAS = {"BETA", "CASE", "HINO", "SEAT", "LADA", "TATA", "MINI", "HERO", "TVS"}


MARCAS_PARA_DESPEGAR = [m for m in MARCAS_VEHICULO
                        if len(m) >= 4 and m not in _MARCAS_RIESGOSAS and " " not in m]


# Las expresiones se arman UNA vez, al arrancar. Antes se compilaban las 164 de nuevo en cada
# fila: 332 µs por descripción, o sea 3,3 s en una lista de 10.000 filas — diez veces más que
# toda la importación junta.
_RE_PEGADO_MAYUS = re.compile(r'(?<=[a-záéíóúñ])(?=[A-ZÁÉÍÓÚÑ])')


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


# Se rodea la marca de espacios y después se colapsan los sobrantes. Es más simple y más
# robusto que exigir letra pegada de un lado o del otro: con "DespieceCHEVROLETCAPUCHON" hay
# que separar por IZQUIERDA y por DERECHA a la vez, y una condición sola nunca cubre las dos.
# El orden es de marca más larga a más corta, así "VOLKSWAGEN" gana antes de que pruebe "VW".
_RE_MARCAS_PEGADAS = re.compile(
    "(" + "|".join(re.escape(m) for m in sorted(MARCAS_PARA_DESPEGAR, key=len, reverse=True)) + ")"
) if MARCAS_PARA_DESPEGAR else None


_RE_ESPACIOS = re.compile(r'\s{2,}')


def separar_texto_pegado(texto):
    """Algunas listas de proveedor exportan varias columnas pegadas sin espacio en el medio:
    'Junta Tapa de CilindrosFORDTAUNUS COUPE' o 'PASTILLAS FRENOVOLKSWAGENGOL'.
    Esto las vuelve legibles separando en dos puntos:
      1) donde una minúscula toca una MAYÚSCULA (ahí se pegaron dos campos), y
      2) donde una marca de vehículo quedó pegada a la descripción.

    El punto 2 antes solo funcionaba si la descripción tenía minúsculas: pedía que el carácter
    anterior a la marca NO fuera mayúscula, así que en una lista escrita toda en mayúsculas
    —que son la mayoría— no separaba nada.

    Y un punto 3: «REF» pegado al final de la palabra anterior, cuando después viene ORIG.
    Ver _RE_REF_PEGADO."""
    if not texto:
        return texto
    t = str(texto).strip()
    t = _RE_REF_PEGADO.sub(r'\1 REF ', t)
    t = _RE_PEGADO_MAYUS.sub(' ', t)
    if _RE_MARCAS_PEGADAS is not None:
        t = _RE_MARCAS_PEGADAS.sub(r' \1 ', t)
    return _RE_ESPACIOS.sub(' ', t).strip()


def separar_por_marca_vehiculo(descripcion):
    """Parte una descripción en (categoría, marca del vehículo, resto), con la PRIMERA marca.
    Ejemplo: 'Junta Tapa de Cilindros FORD TAUNUS COUPE'
             -> ('Junta Tapa de Cilindros', 'FORD', 'TAUNUS COUPE')
    Es lo que permite armar el catálogo por vehículo sin cargar nada a mano: la relación
    pieza-vehículo ya venía en las listas de los proveedores, solo hay que leerla.

    «La primera» es la que aparece antes en el texto, que es la aplicación principal. Antes era
    la primera de la LISTA de marcas, que está ordenada por largo: en «BULBO ... PEUGEOT 405 -
    CITROEN ZX» ganaba cualquiera de las dos según cómo hubiera quedado el orden del set, y eso
    no es una decisión, es azar. Cuando la descripción nombra varios autos —el 19% de los
    casos— lo correcto no es elegir uno: para eso está marcas_vehiculo_en()."""
    tramos = marcas_vehiculo_en(descripcion)
    if not tramos:
        texto = separar_texto_pegado(str(descripcion)) if descripcion else ""
        return (texto.strip() or None), None, None
    marca, categoria, resto = tramos[0]
    return categoria, marca, resto


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
    texto = _normalizar_desc(descripcion)
    if not texto.strip():
        return "Sin clasificar"
    mejor = None   # (posición, -largo, familia)
    for familia, claves in FAMILIAS_REPUESTO.items():
        for clave in claves:
            pos = texto.find(f" {clave} ")
            if pos >= 0:
                candidato = (pos, -len(clave), familia)
                if mejor is None or candidato[:2] < mejor[:2]:
                    mejor = candidato
    return mejor[2] if mejor else "Sin clasificar"


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
    # Marcas de REPUESTO, que no son modelos de auto. Estaban saliendo primeras en el
    # desplegable «Modelo / motor»: DELCO encabezaba la lista de Ford con 951 apariciones y
    # NIPPONDENSO la de Toyota con 476, antes que COROLLA. El filtro de «aparece sobre todo
    # en esta marca» no las agarra porque un proveedor sí las nombra casi siempre junto al
    # mismo auto.
    "BOSCH", "VALEO", "DELCO", "DENSO", "NIPPONDENSO", "MAGNETI", "MAGNETTI", "MARELLI",
    "HITACHI", "LUCAS", "SIEMENS", "DELPHI", "JAEGER", "MASSER", "CAUPLAS", "WEBER", "SOLEX",
    "SKF", "NGK", "MANN", "VITRON", "TAILLOT", "PAIA", "WAHLER", "GATES", "SACHS", "MONROE",
    "FRAM", "BERU", "FACET", "PIERBURG", "MAHLE", "ELRING", "REINZ", "AJUSA", "CORTECO",
    "PAYEN", "TRW", "FERODO", "BREMBO", "NAKATA", "ILUMA", "DPB", "FISPA", "CBOSCH",
}


def es_nombre_de_modelo(token):
    """¿Esta palabra puede ser el nombre de un modelo, o es un número de parte?

    La diferencia que sí se puede medir es cuántos dígitos tiene. Un modelo lleva pocos —
    F-250, S-10, 4RUNNER, C20NE, XU7JP4— y un número de parte lleva muchos: A0091547202,
    M009T61671, EA011610461, SR0465N. Se revisaron a mano los 2.655 tokens del catálogo real
    que tienen cuatro dígitos o más, ordenados por cuánto aparecen, y no hay un solo modelo
    de verdad entre ellos; son todos números de Bosch, Valeo, Mitsubishi y Cummins.

    El precio de la regla: se pierden nombres de camión tipo «VW 11.000» cuando la lista los
    escribe pegados («VW11000EB»). Vale la pena: esto arma un desplegable para elegir, no una
    coincidencia de códigos, y de 5.670 «modelos» detectados 2.655 eran basura."""
    return sum(ch.isdigit() for ch in token) <= 3



def medidas_desde_descripcion(descripcion):
    """Lee las medidas que la descripción ya trae escritas. Devuelve solo lo que es SEGURO.

    En retenes, rulemanes, bujes y o\'rings la medida ES el código: el proveedor escribe
    «RETEN 35X52X7» y ahí están el diámetro interno, el externo y el ancho. Esos datos ya están
    cargados en la base, en el campo descripción, y hasta ahora había que volver a tipearlos a
    mano uno por uno para que sirvieran de algo.

    Sirven para algo importante: comparar_medidas() usa las medidas como prueba física. Si dos
    piezas miden distinto, el vínculo se veta por más que una lista diga que equivalen. O sea que
    llenar esto no agrega equivalencias — saca las falsas.

    Es deliberadamente CONSERVADOR. Solo se leen las formas que no tienen otra lectura posible:

      · tres números seguidos (35x52x7) -> interno, externo, ancho. Se exige interno < externo,
        que es como está construida cualquier pieza de estas; si no se cumple, no se lee nada,
        porque entonces esos números son otra cosa.
      · «22 ESTRIAS» -> cantidad de estrías.
      · «M24 X 1.5» -> diámetro y paso de rosca.

    DOS números sueltos (20x2.5) NO se leen: en un o\'ring eso es diámetro por espesor del cordón,
    no interno por externo, y cargarlo como interno/externo sería meter un dato falso en el lugar
    donde el sistema toma decisiones. Mejor no saber que saber mal."""
    if not descripcion:
        return {}
    texto = str(descripcion).upper().replace(",", ".")
    medidas = {}

    tres = re.search(r"(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*[X×]\s*(\d{1,3}(?:\.\d+)?)"
                     r"\s*[X×]\s*(\d{1,3}(?:\.\d+)?)(?![\d.])", texto)
    if tres:
        interno, externo, ancho = (float(tres.group(i)) for i in (1, 2, 3))
        # Cordura: una pieza real tiene el interno menor que el externo, y ninguna de estas
        # medidas pasa de 500 mm. Si no cierra, son números de otra cosa (un año, una potencia).
        if 0 < interno < externo <= 500 and 0 < ancho <= 500:
            medidas["diametro_interno"] = interno
            medidas["diametro_externo"] = externo
            medidas["ancho"] = ancho

    estrias = re.search(r"(\d{1,3})\s*ESTR[ÍI]AS?", texto)
    if estrias and 0 < int(estrias.group(1)) <= 60:
        medidas["cantidad_estrias"] = int(estrias.group(1))

    rosca = re.search(r"\bM\s?(\d{1,3}(?:\.\d+)?)\s*[X×]\s*(\d{1,2}(?:\.\d+)?)\b", texto)
    if rosca:
        diametro, paso = float(rosca.group(1)), rosca.group(2)
        if 0 < diametro <= 100:
            medidas["diametro_rosca_homocinetica"] = diametro
            medidas["paso_rosca"] = paso

    return medidas

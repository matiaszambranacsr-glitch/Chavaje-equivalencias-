"""Leer una lista de proveedor y entender qué es cada columna.

Dos problemas de verdad, los dos vistos en listas reales:
  - el archivo puede venir en Excel, CSV o PDF, con la codificación y el separador que sea;
  - puede no tener encabezado ninguno, y entonces hay que adivinar qué columna es el código,
    cuál el precio y cuál la descripción mirando los VALORES (adivinar_columnas_por_datos).
    De cinco listas reales, cuatro no traían encabezado.

diagnosticar_lista() simula la importación sobre una muestra y cuenta qué va a pasar con cada
fila, para poder avisar ANTES de cargar y no después."""
import hashlib
import os
import re
import unicodedata

from openpyxl import load_workbook
from datetime import date, datetime, time as dtime, timedelta

from .errores import anotar_error
from .codigos import (dividir_codigos, es_codigo_util, es_fecha_disfrazada, sanitizar,
                      valor_codigo, valor_o_vacio)

# En la app, lo que dura lo que el proceso vive aparte de cada pasada de Streamlit (ver
# del_proceso() en logica/base.py). Acá no hay pasadas: alcanza con un diccionario del módulo.
_DEL_PROCESO = {}


def del_proceso(nombre, crear):
    return _DEL_PROCESO.setdefault(nombre, crear())


def _decodificar_texto(crudo):
    """Pasa los bytes de un archivo de texto a string, probando las codificaciones que se usan.

    Antes se decodificaba solo como UTF-8 y, si el archivo venía en otra, la lectura fallaba
    entera con 'No se pudo leer el archivo'. El problema es que Excel en español guarda los CSV
    en Windows-1252, no en UTF-8: cualquier lista con una 'ó' o una 'ñ' —o sea, casi todas—
    era imposible de importar y no había forma de saber por qué.

    El orden importa: primero las que pueden fallar (UTF-8 detecta bytes inválidos), y latin-1
    al final porque acepta cualquier byte y nunca falla, así que si va antes gana siempre y
    deja los acentos mal."""
    for codificacion in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return crudo.decode(codificacion)
        except (UnicodeDecodeError, AttributeError) as _err:
            anotar_error("_decodificar_texto", _err)
            continue
    return crudo.decode("latin-1", errors="replace")


def _detectar_separador(texto):
    """Con qué carácter están separadas las columnas.

    Se mira solo el ENCABEZADO y las primeras filas, no el archivo entero: en una lista larga
    las descripciones traen comas ('FILTRO, ACEITE, FORD') y al contar sobre todo el texto la
    coma le ganaba al separador verdadero. Y se incluye la tabulación, que antes no se
    contemplaba: un archivo separado por tabs quedaba todo en una sola columna."""
    lineas_muestra = [l for l in texto.splitlines()[:15] if l.strip()]
    if not lineas_muestra:
        return ","
    mejor, mejor_puntaje = ",", -1
    for cand in ("\t", ";", ",", "|"):
        cuentas = [l.count(cand) for l in lineas_muestra]
        if not cuentas or max(cuentas) == 0:
            continue
        # Un separador de verdad aparece la MISMA cantidad de veces en todas las filas
        parejas = sum(1 for x in cuentas if x == cuentas[0])
        puntaje = cuentas[0] * 2 + parejas
        if puntaje > mejor_puntaje:
            mejor, mejor_puntaje = cand, puntaje
    return mejor


def huella_de_archivo(datos):
    """Huella del contenido del archivo. Reconoce la misma planilla aunque le cambien el nombre."""
    if not datos:
        return None
    return hashlib.sha256(datos).hexdigest()[:32]


def identidad_del_archivo(archivo):
    """Qué archivo es, por su CONTENIDO (subido) o por ruta + fecha + tamaño (en el teléfono).
    None si no se puede saber. Es lo que dice «cambió el archivo» aunque se llame igual."""
    if not archivo:
        return None
    if isinstance(archivo, str):
        try:
            _st = os.stat(archivo)
        except OSError:
            return None
        return ("ruta", os.path.abspath(archivo), _st.st_mtime_ns, _st.st_size)
    try:
        return ("datos", huella_de_archivo(archivo.getvalue()))
    except Exception as _err:
        anotar_error("identidad_del_archivo", _err)
        return None


# Libros de Excel ya leídos, por identidad del archivo: {identidad: {hoja: filas}}. Dura lo que
# el proceso (ver del_proceso()), no una pasada: la gracia es que el próximo toque no lo relea.
LIBROS_EN_MEMORIA = 2


def _libro_de_excel(archivo):
    """Todas las hojas del archivo, leídas UNA vez por archivo: {hoja: filas}.

    Antes cada toque en la pantalla de carga abría el libro dos veces enteras (una para contar
    las hojas y otra para la vista previa) y una tercera al importar. Medido con una lista de
    30.000 filas: 5,2 segundos por toque, cambiar un selector incluido. Ahora el primer toque
    lo lee y los demás lo sacan de acá.

    En modo read_only: es varias veces más rápido y gasta menos memoria. El problema que tenía
    (max_row = None en muchas listas reales, ver hojas_del_excel()) acá no importa, porque las
    filas se cuentan leyéndolas. Las filas se emparejan al mismo ancho: en read_only una fila
    termina en su última celda con algo, y la vista previa necesita una tabla pareja."""
    clave = identidad_del_archivo(archivo)
    guardados = del_proceso("libros_de_excel_leidos", dict)
    if clave is not None and clave in guardados:
        return guardados[clave]
    if not isinstance(archivo, str):
        archivo.seek(0)
    wb = load_workbook(archivo, data_only=True, read_only=True)
    try:
        libro = {}
        for ws in wb.worksheets:
            filas = [list(r) for r in ws.iter_rows(values_only=True)]
            while filas and all(v is None or str(v).strip() == "" for v in filas[-1]):
                filas.pop()
            ancho = max((len(f) for f in filas), default=0)
            for f in filas:
                if len(f) < ancho:
                    f.extend([None] * (ancho - len(f)))
            libro[ws.title] = filas
    finally:
        wb.close()
    if clave is not None:
        while len(guardados) >= LIBROS_EN_MEMORIA:
            guardados.pop(next(iter(guardados)), None)
        guardados[clave] = libro
    return libro


def leer_excel(archivo, nrows=None, hoja=None):
    """Lee un archivo Excel, CSV o PDF (subido o por ruta) y devuelve una lista de listas (filas)."""
    nombre = archivo if isinstance(archivo, str) else getattr(archivo, "name", "")
    nombre_lower = nombre.lower()
    # Volver al principio del archivo: esta función se llama primero para la vista previa y
    # después para la carga completa. Si el puntero quedó al final de la primera lectura, la
    # segunda leía vacío — de ahí que algunos archivos "se subieran mal" o salieran incompletos.
    if not isinstance(archivo, str):
        try:
            archivo.seek(0)
        except Exception as _err:
            anotar_error("leer_excel", _err)
            pass

    if nombre_lower.endswith((".csv", ".txt", ".tsv")):
        import csv as csv_module
        if isinstance(archivo, str):
            crudo = open(archivo, "rb").read()
        else:
            archivo.seek(0)
            crudo = archivo.read()
            if isinstance(crudo, str):
                crudo = crudo.encode("utf-8")

        texto = _decodificar_texto(crudo)
        delimitador = _detectar_separador(texto)
        filas = []
        for i, row in enumerate(csv_module.reader(texto.splitlines(), delimiter=delimitador)):
            filas.append(row)
            if nrows and i + 1 >= nrows:
                break
        return filas

    if nombre_lower.endswith(".pdf"):
        import pdfplumber
        filas = []
        with pdfplumber.open(archivo) as pdf:
            for pagina in pdf.pages:
                # extract_tables() en plural: antes se usaba extract_table() (singular), que
                # devuelve SOLO la primera tabla de cada página. En las listas de precios que
                # traen la tabla partida en varios bloques por hoja, se perdía casi todo.
                tablas = pagina.extract_tables() or []
                encontro_algo = False
                for tabla in tablas:
                    for row in tabla:
                        if row and any(celda not in (None, "") for celda in row):
                            filas.append([celda if celda is not None else "" for celda in row])
                            encontro_algo = True
                            if nrows and len(filas) >= nrows:
                                return filas
                if not encontro_algo:
                    # Muchos PDF de proveedor no tienen líneas de tabla: son columnas alineadas
                    # con espacios. Acá NO sirve partir el texto por «dos o más espacios»:
                    # extract_text() colapsa los espacios múltiples en uno solo, así que toda la
                    # fila vuelve como una sola celda y no entra ni un producto. Comprobado
                    # generando un PDF de ese formato: devolvía 0 filas.
                    #
                    # Lo que sí funciona es mirar dónde está cada palabra en la hoja: si entre
                    # el final de una y el comienzo de la siguiente hay un hueco grande, ahí
                    # cambia la columna. Es el mismo criterio que usa el ojo al leerlo.
                    try:
                        palabras = pagina.extract_words() or []
                    except Exception as _err:
                        anotar_error("leer_excel", _err)
                        palabras = []
                    renglones = {}
                    for w in palabras:
                        # Se agrupan por altura, redondeando: los caracteres de una misma línea
                        # nunca están exactamente a la misma altura.
                        clave = round(float(w["top"]) / 3)
                        renglones.setdefault(clave, []).append(w)

                    # Dónde EMPIEZA cada columna, mirando la página entera. Un umbral fijo de
                    # separación no alcanza: cuando una descripción larga llena su columna, el
                    # hueco con el precio es el de un espacio común y quedan pegados. Pero en
                    # estas listas las columnas están alineadas fila a fila, así que las
                    # posiciones donde arrancan las palabras se repiten — y esas repeticiones
                    # son los bordes de las columnas.
                    inicios = {}
                    for w in palabras:
                        x = round(float(w["x0"]) / 4) * 4
                        inicios[x] = inicios.get(x, 0) + 1
                    # Un borde de columna real aparece en CASI TODAS las filas, no en un tercio.
                    # Con el umbral bajo entraban como columna las posiciones donde arrancan
                    # palabras sueltas de la descripción, y la descripción terminaba partida en
                    # cinco pedazos. Se pide el 70% de los renglones.
                    minimo_filas = max(3, int(len(renglones) * 0.7))
                    bordes = sorted(x for x, veces in inicios.items() if veces >= minimo_filas)

                    for clave in sorted(renglones):
                        grupo = sorted(renglones[clave], key=lambda w: float(w["x0"]))
                        if bordes:
                            columnas_fila = {}
                            for w in grupo:
                                # A qué columna pertenece: el borde más cercano a su izquierda
                                x = float(w["x0"])
                                borde = max([b for b in bordes if b <= x + 3], default=bordes[0])
                                columnas_fila.setdefault(borde, []).append(w["text"])
                            celdas = [" ".join(columnas_fila[b]) for b in sorted(columnas_fila)]
                        else:
                            celdas, actual, fin_anterior = [], [], None
                            for w in grupo:
                                if fin_anterior is not None and float(w["x0"]) - fin_anterior > 8:
                                    celdas.append(" ".join(actual))
                                    actual = []
                                actual.append(w["text"])
                                fin_anterior = float(w["x1"])
                            if actual:
                                celdas.append(" ".join(actual))
                        celdas = [x.strip() for x in celdas if x.strip()]
                        if len(celdas) >= 2:
                            filas.append(celdas)
                            if nrows and len(filas) >= nrows:
                                return filas
        return filas

    libro = _libro_de_excel(archivo)
    if not libro:
        return []
    if hoja and hoja in libro:
        filas = libro[hoja]
    else:
        # Sin hoja elegida, se toma la que MÁS FILAS tiene, no la que quedó activa: la activa
        # es simplemente la que el proveedor tenía abierta al guardar, y muchas veces es la de
        # instrucciones o una en blanco.
        filas = max(libro.values(), key=len)
    # Copias de las filas: quien llama puede tocarlas, y lo guardado tiene que quedar intacto.
    return [list(f) for f in (filas[:nrows] if nrows else filas)]


def leer_numero(valor):
    """Lee un número de una celda de Excel, aguantando cómo lo escribe cada proveedor.

    El problema real: en Argentina el punto separa miles y la coma decimales ("1.234,56"), pero
    muchas listas vienen exportadas al revés ("1,234.56"), y otras traen el símbolo de peso,
    espacios o texto pegado ("$850.-"). Leerlo mal convierte $1.234,56 en $123.456: cien veces
    de más.

    Las reglas, en orden:
      1. Si están los DOS separadores, el que está más a la derecha es el decimal.
      2. Si hay uno solo y aparece VARIAS veces, es separador de miles ("12.345.678").
      3. Si hay uno solo y aparece una vez, decide cuántos dígitos lo siguen: tres significa
         miles ("1.234" son mil doscientos treinta y cuatro, no uno con doscientos treinta y
         cuatro), cualquier otra cantidad significa decimales ("1.50", "0,5").
    """
    if valor is None:
        return None
    if isinstance(valor, bool):
        return None
    # Una fecha no es un precio. openpyxl las devuelve como datetime, y una columna mal
    # elegida (la de «vigencia») cargaba cualquier cosa.
    if isinstance(valor, (datetime, date, dtime, timedelta)):
        return None
    if isinstance(valor, (int, float)):
        return float(valor) if valor == valor else None      # NaN no es un número

    texto = str(valor).strip()
    if not texto:
        return None
    # Notación científica: Excel muestra así los números largos, y al exportar a CSV queda
    # «1.5E+3». Sacando todo lo que no es dígito quedaba «1.53»: mil quinientos leído como 1,53.
    if re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?[eE][-+]?\d+", texto):
        try:
            return float(texto.replace(",", "."))
        except ValueError:
            return None
    # Negativo si hay un «-» ANTES del primer dígito: «$ -100» también es negativo, no solo
    # «-100». Uno después («850.-», «100-200») no lo es.
    negativo = bool(re.match(r"^[^\d]*-", texto))
    # Dos números en la misma celda no son un precio: «2 x 1.500» era 21.500, y «05/01/2024»
    # un número de ocho cifras. Solo se juntan si el espacio separa miles («1 234,56»).
    grupos = re.findall(r"\d[\d.,]*", texto)
    if len(grupos) > 1:
        entre = re.split(r"\d[\d.,]*", texto)[1:-1]
        miles_con_espacio = (all(e.strip(" \u00a0") == "" and e for e in entre)
                             and all(re.match(r"\d{3}(?!\d)", g) for g in grupos[1:]))
        if not miles_con_espacio:
            return None
    texto = re.sub(r'[^\d,.]', '', texto)
    texto = texto.strip(",.")               # se come el "$850.-" y el "1.234,-"
    if not texto or not any(ch.isdigit() for ch in texto):
        return None

    comas, puntos = texto.count(","), texto.count(".")

    if comas and puntos:
        # Regla 1: manda el de más a la derecha
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif comas or puntos:
        sep = "," if comas else "."
        if (comas + puntos) > 1:
            texto = texto.replace(sep, "")                    # Regla 2: miles
        else:
            decimales = len(texto.split(sep)[1])
            if decimales == 3:
                texto = texto.replace(sep, "")                # Regla 3: miles
            else:
                texto = texto.replace(sep, ".")               # Regla 3: decimales

    try:
        numero = float(texto)
    except ValueError as _err:
        anotar_error("leer_numero", _err)
        return None
    return -numero if negativo else numero


# Palabras que suelen titular cada columna en las listas de proveedor. Se buscan en el
# encabezado para sugerir el mapeo sin que haya que elegirlo a mano cada vez.
PISTAS_COLUMNAS = {
    "prov":   ["COD", "ART", "REF", "NRO", "N°", "NUMERO", "PIEZA", "PART", "ITEM", "SKU",
                "INVENTORY"],
    # El código de barras va aparte y NUNCA puede quedar como código principal. En el mostrador
    # se pide el número de parte ("150000-R"), no el EAN: si el EAN ocupa el lugar del código,
    # el número real del repuesto no queda cargado en ningún lado y no se puede buscar.
    "ean":    ["EAN", "BARRA", "BARCODE", "GTIN", "UPC"],
    # Sin «FABRICA» ni «APLIC» sueltos: «FABRICANTE» es la columna con el NOMBRE de la marca
    # («BOSCH», «SKF») y «APLICACION» es el auto al que va. Ninguna de las dos es un código, y
    # tomadas como código de fábrica colgaban cientos de filas de «BOSCH» o de «GOL 1.6»: una
    # equivalencia falsa por fila. El código de fábrica escrito con todas las letras sí vale.
    "oem":    ["OEM", "ORIG", "EQUIV", "CRUCE", "COD FABRICA", "CODIGO FABRICA",
                "COD DE FABRICA", "CODIGO DE FABRICA", "NRO FABRICA", "NRO DE FABRICA"],
    "desc":   ["DESC", "DETALLE", "PROD", "ARTICULO", "ARTÍCULO", "NOMBRE", "RUBRO"],
    "precio": ["PRECIO", "P.VENTA", "PVENTA", "P. VENTA", "IMPORTE", "VALOR", "LISTA",
                "COSTO", "NETO", "UNITARIO", "$"],
    "stock":  ["STOCK", "EXIST", "CANT", "DISPON", "SALDO", "DEPOSITO", "DEPÓSITO"],
}


# Títulos que tienen la pista adentro pero NO son esa columna. Probado con títulos reales:
#   · «DESCUENTO %» tiene «DESC» y quedaba como descripción: cada producto con «15» de nombre.
#   · «PESO NETO» tiene «NETO» y quedaba como precio: el repuesto costaba lo que pesa.
#   · «CANT. X BULTO» y «CANT. MINIMA» tienen «CANT» y pisaban el stock con la caja cerrada.
#   · «ORIGEN» (CHINA, BRASIL, NACIONAL) tiene «ORIG» y quedaba como código de fábrica: tres
#     «códigos» que unían entre sí a todos los productos del mismo país.
PISTAS_QUE_NO_SON = {
    "oem":    ["ORIGEN", "PROCEDENCIA", "FABRICANTE", "APLIC"],
    "desc":   ["DESCUENTO", "DESC %", "DESC%"],
    "precio": ["PESO", "KG", "DESCUENTO", "DTO", "BONIF", "ALICUOTA"],
    "stock":  ["BULTO", "MINIMA", "MINIMO", "X CAJA", "POR CAJA", "EMBALAJE", "PACK", "MULTIPLO"],
}


def _titulo_normalizado(x):
    """El título en mayúsculas, sin acentos, sin puntos y con los espacios de a uno: «Cód. Fábrica»
    y «COD FABRICA» son el mismo título."""
    if x is None:
        return ""
    t = unicodedata.normalize("NFKD", str(x).upper())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", t.replace(".", " ").replace("_", " ")).strip()


def _pista_en_titulo(pista, titulo):
    """La pista al PRINCIPIO de una palabra del título. Adentro de una palabra no vale: «ART»
    está en «PARTE» y «CANT» en «DESCANTE», y sin esto cualquier título largo caía en
    cualquier rol."""
    pista = _titulo_normalizado(pista) or pista
    return re.search(r"(?<![A-Z0-9])" + re.escape(pista), titulo) is not None


def adivinar_columnas(encabezado):
    """Sugiere qué columna es cada cosa mirando los títulos. Devuelve un dict con los índices.

    Gana la pista MÁS LARGA que coincida, y una columna no puede tener dos roles.
    Sin eso, un título como «ARTICULO» quedaba como código (por contener «ART») y a la vez como
    descripción (por «ARTICULO»), y terminaba importando la descripción como si fuera el código.
    Comparando el largo, «ARTICULO» le gana a «ART» y cada columna cae donde corresponde.

    Para precio y stock gana la PRIMERA columna que coincide: las listas suelen traer varias
    (costo, lista, con IVA, con descuento) y la primera es casi siempre la que corresponde."""
    titulos = [_titulo_normalizado(x) for x in encabezado]

    # Para cada columna, su mejor rol: el de la pista más larga que aparezca en el título
    mejor_rol = {}
    for i, titulo in enumerate(titulos):
        if not titulo:
            continue
        candidatos = []
        for clave, pistas in PISTAS_COLUMNAS.items():
            if any(_pista_en_titulo(n, titulo) for n in PISTAS_QUE_NO_SON.get(clave, ())):
                continue
            for pista in pistas:
                if _pista_en_titulo(pista, titulo):
                    # "EAN" pesa más que "COD" aunque midan lo mismo: un título como
                    # "CODIGO_EAN" tiene las dos, y sin esta prioridad el empate se resolvía a
                    # favor de "COD" y el código de barras terminaba ocupando el lugar del
                    # número de parte.
                    prioridad = 1 if clave == "ean" else 0
                    candidatos.append((prioridad, len(pista), clave))
        if candidatos:
            mejor_rol[i] = max(candidatos)[2]

    hallado = {"prov": None, "oem": None, "desc": None, "precio": None, "stock": None,
               "ean": None}
    for i, clave in mejor_rol.items():
        # La descripción también: la primera. Las listas que traen dos («DESCRIPCION» y
        # «DESCRIPCION ADICIONAL» o «DESC. RUBRO») ponen primero la del producto.
        if clave in ("precio", "stock", "desc"):
            if hallado[clave] is None:      # la primera manda
                hallado[clave] = i
        else:
            hallado[clave] = i              # la última manda

    # El código de barras no puede ocupar el lugar del código principal: en el mostrador se
    # pide el número de parte («150000-R»), no el EAN.
    # Y TAMPOCO el lugar del código de fábrica, que es lo que hacía antes cuando la lista no
    # traía OEM. La intención era buena —que escanear la caja encuentre el repuesto— pero el
    # lugar estaba mal: la columna de OEM es por donde se cruzan los proveedores, y el EAN es
    # de este proveedor y de nadie más. Cada fila quedaba con una equivalencia que no lleva a
    # ningún lado. Medido en la base real: 8.076 códigos de barras haciendo de código de
    # fábrica, 8.652 productos con esa equivalencia falsa, y CERO cruces de esa lista con
    # cualquier otra. Ahora el EAN va a su propia columna (productos.codigo_barras), que la
    # búsqueda también mira.
    if hallado["ean"] is not None and hallado["prov"] == hallado["ean"]:
        hallado["prov"] = None

    # El código de proveedor siempre tiene que apuntar a algo: si ningún título se reconoció,
    # la primera columna libre es la apuesta razonable.
    if hallado["prov"] is None:
        ocupadas = {v for k, v in hallado.items() if v is not None}
        hallado["prov"] = next((i for i in range(max(len(titulos), 1)) if i not in ocupadas), 0)
    if hallado["oem"] == hallado["prov"]:
        hallado["oem"] = None
    return hallado


def _perfil_de_columna(valores):
    """Mide una columna para poder adivinar qué es, sin depender del título."""
    llenos = [str(v).strip() for v in valores if v is not None and str(v).strip() != ""]
    if not llenos:
        return None
    distintos = len(set(llenos))
    numericos = sum(1 for v in llenos
                    if str(v).replace(".", "").replace(",", "").replace("-", "").isdigit())
    return {
        "llenado": len(llenos) / max(len(valores), 1),
        "unicidad": distintos / len(llenos),        # los códigos casi no se repiten
        "largo": sum(len(v) for v in llenos) / len(llenos),
        "espacios": sum(1 for v in llenos if " " in v) / len(llenos),
        "numerico": numericos / len(llenos),
        "muestra": llenos[:3],
    }


def adivinar_columnas_por_datos(filas_datos, ancho):
    """Deduce qué es cada columna mirando los VALORES, cuando la lista no trae títulos.

    Hace falta porque muchísimas listas de proveedor no tienen encabezado: arrancan directo en
    el primer producto. Sin títulos, la detección por palabras clave no tiene de dónde agarrarse
    y caía siempre en la columna 0 — que en estas listas está vacía, así que no entraba ni un
    producto.

    Lo que distingue a cada columna:
      descripción → es la de texto más largo y con espacios
      código      → casi no se repite (cada fila trae uno distinto)
      precio      → es numérica y SÍ se repite mucho (muchos productos valen lo mismo)
    Esa diferencia de repetición es la clave para separar el código del precio cuando los dos
    son números, que es el caso más difícil."""
    perfiles = {}
    for i in range(ancho):
        p = _perfil_de_columna([f[i] if i < len(f) else None for f in filas_datos])
        if p and p["llenado"] >= 0.3:
            perfiles[i] = p
    hallado = {"prov": None, "oem": None, "desc": None, "precio": None, "stock": None}
    if not perfiles:
        return hallado

    # Descripción: texto largo y con espacios
    candidatas_desc = {i: p for i, p in perfiles.items()
                       if p["largo"] >= 12 and p["espacios"] >= 0.5}
    if candidatas_desc:
        hallado["desc"] = max(candidatas_desc, key=lambda i: perfiles[i]["largo"])

    libres = [i for i in perfiles if i != hallado["desc"]]

    # Código: el más único de los que quedan
    if libres:
        hallado["prov"] = max(libres, key=lambda i: (perfiles[i]["unicidad"], -perfiles[i]["numerico"]))

    # Precio ANTES que el código de fábrica, y a propósito: es la columna numérica que queda.
    # Al revés, una lista de precios ordenada de menor a mayor tiene precios casi todos
    # distintos, así que pasaba por "código de fábrica" — y eso es lo peor que puede salir mal:
    # vincularía entre sí todos los productos que valen lo mismo.
    numericas = [i for i in libres if i != hallado["prov"] and perfiles[i]["numerico"] >= 0.9]
    if numericas:
        hallado["precio"] = min(numericas, key=lambda i: perfiles[i]["unicidad"])

    # Código de fábrica: solo si queda una columna muy única y que NO sea numérica pura.
    # Ante la duda se deja vacío: que falte es un inconveniente, que esté mal genera
    # equivalencias falsas, y eso ensucia la base para siempre.
    for i in libres:
        if i in (hallado["prov"], hallado["precio"]):
            continue
        p = perfiles[i]
        if p["unicidad"] > 0.8 and p["espacios"] < 0.5 and p["numerico"] < 0.9:
            hallado["oem"] = i
            break
    return hallado


def diagnosticar_lista(filas, header_row, idx_prov, idx_oem, idx_desc, muestra=300,
                       idx_ean=None):
    """Simula la importación sobre las primeras filas y cuenta qué va a pasar con cada una.

    Es la respuesta a «se carga mal y no sé por qué». Antes uno mapeaba las columnas, importaba,
    y recién después descubría que el 99% había salido con alarmas — sin ninguna pista de en qué
    paso se rompió. Esto muestra ANTES lo que la app entendió de cada columna, con ejemplos
    reales del archivo, para poder darse cuenta de un vistazo si el mapeo apunta a donde debe."""
    datos = filas[header_row + 1:header_row + 1 + muestra]
    total = len(datos)
    r = {
        "total": total, "vacias": 0, "sin_codigo": 0, "codigo_basura": 0,
        "ok": 0, "con_oem": 0, "sospechosas": [], "fechas": 0, "ejemplos_fechas": [],
        "ejemplos_prov": [], "ejemplos_oem": [], "ejemplos_desc": [],
        "columnas_desiguales": 0, "cientificos": 0, "ejemplos_cientificos": [],
    }
    if not total:
        return r

    ancho_encabezado = len([x for x in filas[header_row] if x is not None and str(x).strip()])

    for fila in datos:
        celdas = [x for x in fila if x is not None and str(x).strip() != ""]
        if not celdas:
            r["vacias"] += 1
            continue
        if ancho_encabezado and abs(len(celdas) - ancho_encabezado) > 2:
            r["columnas_desiguales"] += 1

        def celda(i, es_codigo=False):
            if i is None or i >= len(fila) or fila[i] is None:
                return ""
            if es_codigo:
                return valor_codigo(fila[i])
            return str(fila[i]).strip()

        # Fechas donde debería haber un código: Excel se las comió al guardar
        for i in (idx_prov, idx_oem):
            if i is not None and i < len(fila) and es_fecha_disfrazada(fila[i]):
                r["fechas"] += 1
                if len(r["ejemplos_fechas"]) < 5:
                    r["ejemplos_fechas"].append(str(fila[i])[:10])

        # Y el hermano silencioso de la fecha: el número largo que Excel escribió en notación
        # científica. La fecha se nota porque no parece un código; esto parece un código
        # perfecto. Se mira también la columna del código de barras, que es la que más sufre:
        # trece dígitos siempre pasan el largo a partir del cual Excel cambia de formato.
        for i in (idx_prov, idx_oem, idx_ean):
            if i is not None and i < len(fila) and excel_le_comio_digitos(fila[i]):
                r["cientificos"] += 1
                if len(r["ejemplos_cientificos"]) < 5:
                    r["ejemplos_cientificos"].append(str(fila[i])[:20])

        crudo_prov = celda(idx_prov, es_codigo=True)
        crudo_oem = celda(idx_oem, es_codigo=True)
        crudo_desc = celda(idx_desc)
        if len(r["ejemplos_prov"]) < 5 and crudo_prov:
            r["ejemplos_prov"].append(crudo_prov)
        if len(r["ejemplos_oem"]) < 5 and crudo_oem:
            r["ejemplos_oem"].append(crudo_oem)
        if len(r["ejemplos_desc"]) < 5 and crudo_desc:
            r["ejemplos_desc"].append(crudo_desc)

        if not crudo_prov:
            r["sin_codigo"] += 1
            continue
        codigos = dividir_codigos(crudo_prov)
        if not codigos:
            r["codigo_basura"] += 1
            if len(r["sospechosas"]) < 20:
                r["sospechosas"].append({
                    "Fila": filas.index(fila) + 1 if fila in filas else "?",
                    "Código leído": crudo_prov[:30],
                    "Motivo": "es un número suelto de 1 o 2 dígitos, o está vacío",
                })
            continue
        r["ok"] += 1
        if crudo_oem and dividir_codigos(crudo_oem):
            r["con_oem"] += 1
    return r

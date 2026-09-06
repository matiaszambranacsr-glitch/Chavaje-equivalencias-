"""Leer una lista de proveedor y entender qué es cada columna.

Dos problemas de verdad, los dos vistos en listas reales:
  - el archivo puede venir en Excel, CSV o PDF, con la codificación y el separador que sea;
  - puede no tener encabezado ninguno, y entonces hay que adivinar qué columna es el código,
    cuál el precio y cuál la descripción mirando los VALORES (adivinar_columnas_por_datos).
    De cinco listas reales, cuatro no traían encabezado.

diagnosticar_lista() simula la importación sobre una muestra y cuenta qué va a pasar con cada
fila, para poder avisar ANTES de cargar y no después."""
import re
import unicodedata

from openpyxl import load_workbook

from .errores import anotar_error
from .codigos import (dividir_codigos, es_codigo_util, es_fecha_disfrazada, sanitizar,
                      valor_codigo, valor_o_vacio)


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

    wb = load_workbook(archivo, data_only=True)
    if hoja and hoja in wb.sheetnames:
        ws = wb[hoja]
    else:
        # Sin hoja elegida, se toma la que MÁS FILAS tiene, no la que quedó activa: la activa
        # es simplemente la que el proveedor tenía abierta al guardar, y muchas veces es la de
        # instrucciones o una en blanco.
        ws = max(wb.worksheets, key=lambda w: w.max_row or 0)
    filas = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        filas.append(list(row))
        if nrows and i + 1 >= nrows:
            break
    return filas


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
    if isinstance(valor, (int, float)):
        return float(valor)

    texto = str(valor).strip()
    if not texto:
        return None
    negativo = texto.lstrip().startswith("-")
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
    "oem":    ["OEM", "ORIG", "EQUIV", "CRUCE", "FABRICA", "FÁBRICA", "APLIC"],
    "desc":   ["DESC", "DETALLE", "PROD", "ARTICULO", "ARTÍCULO", "NOMBRE", "RUBRO"],
    "precio": ["PRECIO", "P.VENTA", "PVENTA", "P. VENTA", "IMPORTE", "VALOR", "LISTA",
                "COSTO", "NETO", "UNITARIO", "$"],
    "stock":  ["STOCK", "EXIST", "CANT", "DISPON", "SALDO", "DEPOSITO", "DEPÓSITO"],
}


def adivinar_columnas(encabezado):
    """Sugiere qué columna es cada cosa mirando los títulos. Devuelve un dict con los índices.

    Gana la pista MÁS LARGA que coincida, y una columna no puede tener dos roles.
    Sin eso, un título como «ARTICULO» quedaba como código (por contener «ART») y a la vez como
    descripción (por «ARTICULO»), y terminaba importando la descripción como si fuera el código.
    Comparando el largo, «ARTICULO» le gana a «ART» y cada columna cae donde corresponde.

    Para precio y stock gana la PRIMERA columna que coincide: las listas suelen traer varias
    (costo, lista, con IVA, con descuento) y la primera es casi siempre la que corresponde."""
    titulos = [str(x).upper().strip() if x else "" for x in encabezado]

    # Para cada columna, su mejor rol: el de la pista más larga que aparezca en el título
    mejor_rol = {}
    for i, titulo in enumerate(titulos):
        if not titulo:
            continue
        candidatos = []
        for clave, pistas in PISTAS_COLUMNAS.items():
            for pista in pistas:
                if pista in titulo:
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
        if clave in ("precio", "stock"):
            if hallado[clave] is None:      # la primera manda
                hallado[clave] = i
        else:
            hallado[clave] = i              # la última manda

    # El código de barras se carga como un código MÁS del producto, no como el principal. Así
    # escanear la caja encuentra el repuesto, y el número de parte sigue siendo el que se busca
    # y se muestra.
    if hallado["ean"] is not None:
        if hallado["prov"] == hallado["ean"]:
            hallado["prov"] = None
        if hallado["oem"] is None:
            hallado["oem"] = hallado["ean"]

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


def diagnosticar_lista(filas, header_row, idx_prov, idx_oem, idx_desc, muestra=300):
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
        "columnas_desiguales": 0,
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

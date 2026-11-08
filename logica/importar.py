"""Importar una lista: leer el archivo, adivinar las columnas, huella del archivo.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================
# IMPORTAR UNA LISTA: leer el archivo y adivinar qué es cada columna
# ============================================================

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


def _pinta_columna(ejemplos, esperado):
    """¿Los valores de esta columna se parecen a lo que se espera de ella?"""
    if not ejemplos:
        return "⚠️ vacía", "no trajo ningún valor en las filas de muestra"
    if esperado == "codigo":
        limpios = [sanitizar(e) for e in ejemplos]
        if all(l.isdigit() and len(l) <= 2 for l in limpios if l):
            return "❌ no son códigos", "son números sueltos (¿cantidad? ¿número de orden?)"
        # Palabras sin ningún número que se repiten: «CHINA», «BRASIL», «NACIONAL» (la columna
        # de origen), o el rubro. Un código de repuesto casi siempre tiene algún dígito, y
        # nunca se repite fila tras fila.
        sin_digitos = [l for l in limpios if l and not any(ch.isdigit() for ch in l)]
        if (len(ejemplos) >= 4 and len(sin_digitos) >= 0.8 * len(ejemplos)
                and len(set(sin_digitos)) <= max(2, len(ejemplos) // 2)):
            return "❌ no son códigos", "son palabras que se repiten (¿origen? ¿rubro? ¿marca?)"
        if _parecen_precios(ejemplos):
            return "❌ parecen precios", "son importes con decimales, no códigos"
        # Lo que separa un código de una descripción no es el largo sino los ESPACIOS:
        # 'W712/94' y '036115561G' no tienen ninguno, 'FILTRO DE ACEITE FORD' tiene varios.
        # Mirando solo el largo, una descripción de 32 caracteres pasaba como código.
        con_frases = sum(1 for e in ejemplos if e.count(" ") >= 2)
        if con_frases >= len(ejemplos) / 2:
            return "❌ parece descripción", "los valores tienen varias palabras, no son códigos"
        largos = sum(1 for e in ejemplos if len(e) > 40)
        if largos >= len(ejemplos) / 2:
            return "❌ parece descripción", "los valores son frases largas, no códigos"
        if all(e.replace(".", "").replace(",", "").isdigit() and len(sanitizar(e)) <= 3
               for e in ejemplos if e):
            return "❌ no son códigos", "son números cortos (¿cantidad? ¿bulto?)"
        return "✅ parecen códigos", ""
    if esperado == "descripcion":
        # Una descripción real tiene más de una palabra
        sin_espacios = sum(1 for e in ejemplos if " " not in e)
        if sin_espacios >= len(ejemplos) / 2:
            return "⚠️ parecen códigos", "son una sola palabra, no descripciones"
        if all(len(e) <= 12 for e in ejemplos):
            return "⚠️ muy cortos", "parecen códigos, no descripciones"
        return "✅ parece descripción", ""
    return "✅", ""


def _perfil_de_columna(valores):
    """Mide una columna para poder adivinar qué es, sin depender del título."""
    llenos = [str(v).strip() for v in valores if v is not None and str(v).strip() != ""]
    if not llenos:
        return None
    distintos = len(set(llenos))
    numericos = sum(1 for v in llenos
                    if str(v).replace(".", "").replace(",", "").replace("-", "").isdigit())
    largos = {}      # sin collections: esto va también a nucleo/, que no lo importa
    for v in llenos:
        largos[len(v)] = largos.get(len(v), 0) + 1
    return {
        "llenado": len(llenos) / max(len(valores), 1),
        "unicidad": distintos / len(llenos),        # los códigos casi no se repiten
        "largo": sum(len(v) for v in llenos) / len(llenos),
        "espacios": sum(1 for v in llenos if " " in v) / len(llenos),
        "numerico": numericos / len(llenos),
        # Para separar un código numérico de un precio que tampoco se repite (una lista
        # ordenada por precio): los importes tienen forma de importe, y los códigos de un
        # proveedor suelen tener todos el mismo largo; los precios, no.
        "importes": _parecen_precios(llenos),
        "largo_fijo": max(largos.values()) / len(llenos),
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

    # Código: el más único de los que quedan, pero nunca uno con forma de importe, y entre dos
    # números que no se repiten, el de largo parejo. Sin esto, en una lista sin títulos con el
    # precio primero, ordenada de menor a mayor —precios que no se repiten— y códigos
    # numéricos, el precio salía como código y el código como precio (encontrado probando las
    # funciones que ninguna batería tocaba).
    if libres:
        hallado["prov"] = max(libres, key=lambda i: (not perfiles[i]["importes"],
                                                     perfiles[i]["unicidad"],
                                                     -perfiles[i]["numerico"],
                                                     perfiles[i]["largo_fijo"]))

    # Precio ANTES que el código de fábrica, y a propósito: es la columna numérica que queda.
    # Al revés, una lista de precios ordenada de menor a mayor tiene precios casi todos
    # distintos, así que pasaba por "código de fábrica" — y eso es lo peor que puede salir mal:
    # vincularía entre sí todos los productos que valen lo mismo.
    numericas = [i for i in libres if i != hallado["prov"] and perfiles[i]["numerico"] >= 0.9]
    if numericas:
        hallado["precio"] = min(numericas, key=lambda i: (not perfiles[i]["importes"],
                                                          perfiles[i]["unicidad"],
                                                          perfiles[i]["largo_fijo"]))

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


def adivinar_proveedor(nombre_archivo, marcas_conocidas=()):
    """Saca el nombre del proveedor del nombre del archivo.

    Las listas llegan como 'ILLINOIS 17 07 2026.xlsx' o 'Lista_MAHLE_agosto.xlsx': el proveedor
    está ahí escrito y no hay razón para volver a tipearlo cada vez. Primero se busca alguna de
    las marcas que ya existen en la base (lo más confiable); si no aparece ninguna, se limpian
    fechas, números y palabras de relleno y se toma lo que queda."""
    base = re.sub(r'\.[A-Za-z0-9]{2,5}$', '', str(nombre_archivo or "").strip())
    if not base:
        return ""
    texto = re.sub(r'[_\-]+', ' ', base).upper()

    for marca in sorted(marcas_conocidas, key=len, reverse=True):
        if marca and len(marca) >= 3 and marca.upper() in texto:
            return marca.upper()

    relleno = {"LISTA", "LISTAS", "PRECIOS", "PRECIO", "CATALOGO", "CATÁLOGO", "ACTUALIZADA",
               "ACTUALIZADO", "NUEVA", "NUEVO", "COPIA", "FINAL", "VIGENTE", "DE", "DEL", "LA",
               "EL", "Y", "CON", "SIN", "VENTA", "MAYORISTA", "XLSX", "XLS", "CSV", "PDF"}
    meses = {"ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO",
             "SEPTIEMBRE", "SETIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"}
    palabras = [p for p in re.split(r'[^A-ZÁÉÍÓÚÑ0-9]+', texto) if p]
    utiles = [p for p in palabras
              if not p.isdigit() and p not in relleno and p not in meses and len(p) >= 3]
    return " ".join(utiles[:2]) if utiles else ""


# ============================================================================================
# AVISOS DE BACKUP Y HUELLA DEL ARCHIVO IMPORTADO
# ============================================================================================
def estado_del_backup():
    """Qué se cargó desde el último backup. Devuelve un dict con lo que haga falta para avisar.

    Esto importa más acá que en un sistema normal: el hosting borra el disco cuando reinicia y
    la app se restaura desde la última copia del repositorio. Todo lo cargado después de esa
    copia se pierde, y uno se entera recién cuando busca un código y no aparece."""
    c.execute("SELECT COUNT(*) FROM productos")
    total = c.fetchone()[0]
    marca = obtener_config("ultimo_backup_fecha", "")

    if not marca:
        return {"hay_backup": False, "productos_nuevos": total, "importaciones": None,
                "dias": None, "urgente": total > 0}

    desde = int(obtener_config("ultimo_backup_productos", "0") or 0)
    c.execute("SELECT COUNT(*) FROM importaciones WHERE fecha > ?", (marca,))
    importaciones = c.fetchone()[0]
    try:
        dias = (datetime.now() - datetime.strptime(marca[:19], "%Y-%m-%d %H:%M:%S")).days
    except Exception as _err:
        anotar_error("estado_del_backup", _err)
        dias = None

    nuevos = max(total - desde, 0)
    # Se avisa por cualquiera de las tres: productos nuevos, listas importadas, o tiempo.
    # Una lista importada puede cambiar miles de precios sin sumar un solo producto, así que
    # contar solo los productos nuevos dejaría pasar justo el caso que más duele perder.
    urgente = nuevos >= 50 or importaciones >= 1 or (dias is not None and dias >= 14)
    return {"hay_backup": True, "productos_nuevos": nuevos, "importaciones": importaciones,
            "dias": dias, "urgente": urgente}


def marcar_backup_hecho():
    """Se llama al descargar un backup: deja la marca para poder avisar cuando se atrase."""
    c.execute("SELECT COUNT(*) FROM productos")
    guardar_config("ultimo_backup_productos", str(c.fetchone()[0]))
    guardar_config("ultimo_backup_fecha", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    invalidar_salud()


def marcar_backup_bajado():
    """El backup bajado a mano (los botones de Backup y config). Además de la marca de
    marcar_backup_hecho(), que también pone la copia de GitHub, deja la suya: con la copia
    frenada desde el 12/10 (ver se_puede_subir_sin_cifrar()) un backup en la compu es lo único
    que protege lo cargado de un reinicio, y la salud dice de cuándo es el último."""
    marcar_backup_hecho()
    guardar_config("ultimo_backup_bajado", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


# Archivos que genera la propia app. Reimportar uno de estos es un error que no da ningún
# aviso y ensucia la base: subir el filas_omitidas.xlsx crea una marca llamada "FILAS OMITIDAS"
# con los productos que justamente se habían descartado.
ARCHIVOS_QUE_GENERA_LA_APP = {
    "filas_omitidas": "las filas que se descartaron en una importación anterior",
    "codigos_basura": "los códigos basura que marcaste para borrar",
    "precios_frenados": "los precios que se frenaron por parecer un error",
    "precios_incoherentes": "el listado de precios que no cerraban",
    "vinculos_dudosos": "los vínculos que el análisis marcó como dudosos",
    "productos_sin_equivalencias": "el listado de productos sin vínculos",
    "datos_iniciales": "el backup de la base",
}


def es_archivo_generado_por_la_app(nombre_archivo):
    """¿Este archivo lo generó la app? Devuelve (sí/no, qué es).

    No es una restricción caprichosa: estos exports son listados de diagnóstico, no listas de
    proveedor. Importarlos vuelve a meter en la base justo lo que se había separado."""
    base = re.sub(r'\.[A-Za-z0-9]{2,5}$', '', str(nombre_archivo or "")).strip().lower()
    base = re.sub(r'[\s\-]+', '_', base)
    base = re.sub(r'_?\d{6,8}$', '', base)      # el sufijo de fecha que llevan algunos
    for clave, que_es in ARCHIVOS_QUE_GENERA_LA_APP.items():
        if base == clave or base.startswith(clave):
            return True, que_es
    return False, ""


def huella_de_archivo(datos):
    """Huella del contenido del archivo. Reconoce la misma planilla aunque le cambien el nombre."""
    if not datos:
        return None
    return hashlib.sha256(datos).hexdigest()[:32]


def importacion_previa(huella):
    """Si esta misma planilla ya se importó, devuelve cuándo y con qué marca."""
    if not huella:
        return None
    c.execute("""SELECT marca, archivo, fecha, filas_cargadas FROM importaciones
                 WHERE huella = ? ORDER BY fecha DESC LIMIT 1""", (huella,))
    fila = c.fetchone()
    return dict(fila) if fila else None


# DE CUÁNDO ES EL PRECIO. El buscador mostraba el precio sin fecha, y la lista de un proveedor
# puede tener meses: en la base real del 25/9, la de ILLINOIS era del 17/7 y la de MANNOL del
# 14/4, cargadas el mismo día que las otras. Lo pidió una revisión con ChatGPT («fecha de
# actualización de precio y stock» y «aviso cuando el usuario trabaja con datos
# desactualizados»). Desde estos días se avisa: con la inflación de 2026, una lista de dos
# meses ya cotiza por debajo.
DIAS_PARA_AVISAR_PRECIO_VIEJO = 60
_RE_FECHA_EN_EL_ARCHIVO = re.compile(r"(?<!\d)(\d{1,2})[ ._-](\d{1,2})[ ._-](\d{4}|\d{2})(?!\d)")


def fecha_de_la_lista(archivo, cargada):
    """(fecha, de dónde) de los precios de una lista: la que trae el nombre del archivo
    («ILLINOIS 17 07 2026.xlsx») si tiene sentido —no después de cargarla ni dos años antes—, y
    si no, el día en que se cargó. (None, "") si no se sabe ni eso."""
    try:
        dia_de_carga = datetime.strptime(str(cargada or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return None, ""
    for m in _RE_FECHA_EN_EL_ARCHIVO.finditer(str(archivo or "")):
        dia, mes, anio = (int(x) for x in m.groups())
        anio += 2000 if anio < 100 else 0
        try:
            fecha = date(anio, mes, dia)
        except ValueError:
            continue
        if dia_de_carga - timedelta(days=730) <= fecha <= dia_de_carga:
            return fecha, "de la lista"
    return dia_de_carga, "cargada"


def fecha_de_los_precios(hoy=None):
    """{marca en mayúsculas: {"fecha", "de_donde", "dias"}} según la última lista cargada de
    cada una. Una marca que nunca se cargó por una lista no está."""
    hoy = hoy or date.today()
    c.execute("""SELECT i.marca, i.archivo, i.fecha FROM importaciones i
                 WHERE i.fecha = (SELECT MAX(j.fecha) FROM importaciones j
                                  WHERE UPPER(j.marca) = UPPER(i.marca))""")
    salida = {}
    for r in c.fetchall():
        fecha, de_donde = fecha_de_la_lista(r["archivo"], r["fecha"])
        if fecha:
            salida[str(r["marca"]).upper()] = {"fecha": fecha, "de_donde": de_donde,
                                               "dias": (hoy - fecha).days}
    return salida


def texto_de_la_fecha_de_los_precios(marcas, hoy=None):
    """La línea que va abajo de los precios en el buscador, solo con las marcas que se ven.
    Lo viejo, en negrita y con ⚠️. «» si no hay ninguna marca con precio."""
    marcas = sorted({str(m) for m in marcas if m})
    if not marcas:
        return ""
    fechas = fecha_de_los_precios(hoy)
    partes = []
    for marca in marcas:
        f = fechas.get(marca.upper())
        if not f:
            partes.append(f"{marca}: sin fecha (no entró por una lista)")
            continue
        texto = (f"{marca}: {'lista del' if f['de_donde'] == 'de la lista' else 'cargada el'} "
                 f"{f['fecha']:%d/%m/%Y} (hace {f['dias']} días)")
        partes.append(f"**⚠️ {texto}**" if f["dias"] >= DIAS_PARA_AVISAR_PRECIO_VIEJO else texto)
    return "💲 Precios — " + " · ".join(partes)


# Con separador de miles («1.037,25») o sin él («1037.25», como exporta la planilla): antes
# solo la primera forma, y una columna de precios así pasaba por código.
_RE_IMPORTE = re.compile(r"^\$?\s*-?(?:\d{1,3}(?:[.,]\d{3})*|\d+)[.,]\d{2}$|^\$\s*\d")


def _parecen_precios(valores):
    """¿La mayoría de estos valores son importes («1.500,00», «$ 850», «12,50»)?"""
    valores = [str(v).strip() for v in valores if v is not None and str(v).strip()]
    if len(valores) < 3:
        return False
    return sum(1 for v in valores if _RE_IMPORTE.match(v)) >= 0.6 * len(valores)


def problemas_del_mapeo(filas, header_row, idx_prov, idx_oem, idx_precio, idx_stock,
                        muestra=300):
    """Lo que está mal en el mapeo elegido, ANTES de importar: [(grave, texto)].

    grave=True frena el botón de importar (la carga saldría rota seguro); False pide confirmar.
    Sale de errores vistos: el mapeo recordado por posición cuando el proveedor movió las
    columnas dejaba el PRECIO como código («1.500,00» como número de parte), y elegir la misma
    columna para precio y stock ponía el stock en $15.000."""
    problemas = []
    usados = {"precio": idx_precio, "stock": idx_stock}
    if idx_precio is not None and idx_precio == idx_stock:
        problemas.append((True, "**Precio y stock apuntan a la misma columna.** Uno de los dos "
                                 "está mal: elegí «Ninguna» en el que la lista no trae."))
    for nombre, idx in usados.items():
        if idx is not None and idx == idx_prov:
            problemas.append((True, f"**El código de proveedor y el {nombre} apuntan a la misma "
                                     "columna.** Revisá el mapeo de arriba."))
    datos = filas[header_row + 1:header_row + 1 + muestra]

    def valores(idx):
        if idx is None:
            return []
        return [str(f[idx]).strip() for f in datos
                if idx < len(f) and f[idx] is not None and str(f[idx]).strip()]

    for etiqueta, idx in (("código de proveedor", idx_prov), ("código de fábrica", idx_oem)):
        v = valores(idx)
        if not v:
            continue
        if _parecen_precios(v):
            problemas.append((False, f"La columna de **{etiqueta}** trae importes («{v[0]}»), "
                                      "no códigos. ¿No será la del precio?"))
        elif len(v) >= 20 and len(set(v)) <= 0.2 * len(v):
            _repes = collections.Counter(v).most_common(3)
            problemas.append((False, f"La columna de **{etiqueta}** repite casi siempre lo mismo "
                                      f"({', '.join(f'«{x}» {n} veces' for x, n in _repes)}): "
                                      "parece el rubro, el origen o la marca, no un código."))
    return problemas


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


def salto_de_precio_sospechoso(precio_viejo, precio_nuevo, tope_pct=200):
    """¿Este cambio de precio parece un error de la lista y no un aumento? (sospechoso, motivo).

    No mira solo el porcentaje: un salto de exactamente 100 o 1000 veces casi siempre es el
    separador de decimales mal leído, y conviene decirlo con esas palabras para que se entienda
    qué revisar."""
    if not tope_pct or precio_viejo is None or precio_nuevo is None:
        return False, None
    if precio_viejo <= 0 or precio_nuevo <= 0:
        return False, None
    razon = precio_nuevo / precio_viejo
    for factor, texto in ((1000, "mil"), (100, "cien"), (10, "diez")):
        if abs(razon - factor) / factor < 0.02:
            return True, f"quedó {texto} veces más caro — suele ser el separador de decimales"
        if abs(razon - 1 / factor) * factor < 0.02:
            return True, f"quedó {texto} veces más barato — suele ser el separador de decimales"
    # Se compara la RAZÓN, no el porcentaje, y a propósito.
    # Un aumento no tiene techo (+500%, +2000%), pero una baja no puede pasar de -100%: con un
    # límite del 200% en porcentaje, NINGUNA baja se frenaría nunca, ni siquiera un precio que
    # se divide por veinte. Mirando la razón, multiplicar por 3 y dividir por 3 pesan igual.
    factor = 1 + tope_pct / 100.0
    if razon > factor:
        return True, f"queda {miles(razon, 1)} veces más caro (+{(razon - 1) * 100:.0f}%)"
    if razon < 1 / factor:
        return True, f"queda {miles(1 / razon, 1)} veces más barato ({(razon - 1) * 100:.0f}%)"
    return False, None


def poner_precio_y_stock_de_la_lista(producto_id, precio, stock, tope_salto):
    """El precio y el stock que trae una fila de la lista, con el freno de saltos. Devuelve
    (frenado, cambio): frenado es (precio con que se comparó, motivo) si el precio NO se pisó
    —el stock sí—; cambio, si el precio cambió (va al historial).

    Estaba adentro del ciclo de la importación, en la pantalla (lo señaló una revisión con
    Gemini: «la lógica, en logica/»). El candado lo toma quien la llama (la importación ya lo
    tiene). La transacción es la de la importación: adentro de otra, transaccion() no abre una
    nueva; suelta, el historial y el precio van juntos."""
    if precio is None and stock is None:
        return None, False
    with transaccion():
        c.execute("SELECT precio FROM productos WHERE id = ?", (producto_id,))
        _f = c.fetchone()
        precio_viejo = _f["precio"] if _f else None
        # Si el precio guardado quedó en 0 (una lista vieja que lo pisó), el freno se compara con
        # el último precio de verdad: si no, cualquier número pasaba sin mirar.
        precio_ref = precio_viejo
        if precio is not None and not (precio_viejo and precio_viejo > 0):
            c.execute("SELECT precio FROM historial_precios WHERE producto_id = ? AND precio > 0 "
                      "ORDER BY id DESC LIMIT 1", (producto_id,))
            _h = c.fetchone()
            if _h:
                precio_ref = _h["precio"]
        raro, motivo = salto_de_precio_sospechoso(precio_ref, precio, tope_salto)
        if raro:
            # El producto se carga igual; lo único que no se pisa es el precio, para no cotizar con
            # un número roto.
            if stock is not None:
                c.execute("UPDATE productos SET stock = ? WHERE id = ?", (int(stock), producto_id))
            return (precio_ref, motivo), False
        cambio = precio is not None and precio_viejo != precio
        if cambio:
            c.execute("INSERT INTO historial_precios (producto_id, precio) VALUES (?, ?)",
                      (producto_id, precio))
        c.execute("UPDATE productos SET precio = COALESCE(?, precio), stock = COALESCE(?, stock) "
                  "WHERE id = ?", (precio, int(stock) if stock is not None else None, producto_id))
        return None, cambio


def aplicar_precios_frenados(frenados):
    """«💲 Aplicar igual» los precios que frenó la importación, después de que alguien los
    miró: cada uno va al historial y queda como precio. Todo o nada. Lo hacía la pantalla, sin
    volver a mirar el permiso; cargar listas es del administrador."""
    exigir_nivel("admin", "aplicar los precios que frenó la importación")
    aplicados = 0
    with db_lock, transaccion():
        for f in frenados:
            if f.get("Precio de la lista") is not None:
                c.execute("INSERT INTO historial_precios (producto_id, precio) VALUES (?, ?)",
                          (f["_id"], f["Precio de la lista"]))
                c.execute("UPDATE productos SET precio = ? WHERE id = ?",
                          (f["Precio de la lista"], f["_id"]))
                aplicados += 1
    return aplicados


def get_or_create_producto(raw, clean, desc, marca_id, imagen_url=None):
    # Un producto nuevo de una familia a la que ya se le puso nombre entra con la pieza: ver «QUÉ
    # PIEZA ES CADA FAMILIA DE CÓDIGOS». Los que ya estaban no se tocan (la descripción no se
    # pisa al volver a importar).
    _desc_original = desc
    desc = con_la_pieza_de_su_familia(raw, desc, marca_id)
    with transaccion():      # el producto y su descripción de antes: los dos o ninguno
        c.execute(
            "INSERT OR IGNORE INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) VALUES (?, ?, ?, ?)",
            (raw, clean, desc, marca_id)
        )
        if desc != _desc_original and c.rowcount:
            c.execute("INSERT OR IGNORE INTO descripciones_antes_de_la_familia (producto_id, "
                      "descripcion) VALUES (?, ?)", (c.lastrowid, _desc_original))
    if desc:
        c.execute(
            "UPDATE productos SET descripcion = ?, codigo_raw = ? "
            "WHERE codigo_clean = ? AND marca_id = ? AND (descripcion IS NULL OR descripcion = '')",
            (desc, raw, clean, marca_id)
        )
    if imagen_url:
        c.execute(
            "UPDATE productos SET imagen_url = ? WHERE codigo_clean = ? AND marca_id = ?",
            (imagen_url, clean, marca_id)
        )
    c.execute("SELECT id FROM productos WHERE codigo_clean = ? AND marca_id = ?", (clean, marca_id))
    return c.fetchone()[0]


# ============================================================================================
# DOS PRODUCTOS DE LA LISTA QUE SIN LOS SIGNOS SE ESCRIBEN IGUAL
# ============================================================================================
# El código limpio saca los signos para que «06A 905 115» y «06A905115» sean uno solo. Pero en la
# lista de IMPERIAL del 18/08 hay 210 pares de productos DISTINTOS que se distinguen por un signo:
# la junta H21A1/2"RF1,5 (de ½", $643) y la H21A12"RF1,5 (de 12", $48.209), la tuerca CAMBA111.4
# (5/32, $987) y la CAMBA11.14 (9/16, $11.073). Los dos renglones caían en el mismo producto, que
# se quedaba con la descripción del primero y el PRECIO DEL SEGUNDO: en la base del 12/10, «JTA
# PTFE HI-LON.2100 S150 1/2"» estaba a $48.209, 75 veces lo que vale, y la tuerca de 5/32 al
# precio de la de 9/16. Y los vínculos del segundo renglón se le colgaban al primero.
# Ahora el renglón escrito distinto que el producto —si la lista también trae el escrito como
# él— es otro producto: no le toca el precio ni los vínculos del primero, y entra APARTE, con un
# código limpio propio (ver codigo_de_la_variante()). Volver a importar la lista corrige los
# precios que quedaron mal (los que bajan mucho los para el freno, para mirarlos) y carga los
# 210 que faltaban: buscar CAM-A1781-030 traía la camisa +030.
# El mismo código escrito igual dos veces (la unidad y la caja) sigue como antes: queda el último
# y se avisa (ver codigos_con_dos_precios_en_la_misma_lista()).


def codigos_del_proveedor(celda):
    """Los códigos de proveedor de una celda, como los toma la importación: partidos (ver
    dividir_codigos()) o, si no se parte, la celda entera si es un código."""
    codigos = dividir_codigos(celda)
    if not codigos and celda and es_codigo_util(celda):
        codigos = [celda]
    return codigos


def _escrito(codigo):
    return re.sub(r"\s+", "", str(codigo or "")).upper()


def como_se_escribe_cada_codigo(celdas):
    """{código limpio: {cómo se escribe}} de la lista entera, antes de cargar nada: renglón
    por renglón no se puede saber si dos que caen en el mismo código limpio son el mismo código
    o dos productos. Sin los espacios ni las mayúsculas, que no distinguen nada."""
    formas = {}
    for celda in celdas:
        for raw in codigos_del_proveedor(celda):
            limpio = sanitizar(raw)
            if limpio:
                formas.setdefault(limpio, set()).add(_escrito(raw))
    return formas


# EL CÓDIGO LIMPIO DEL OTRO. Sin los signos son iguales, así que el limpio de siempre no sirve:
# lleva adelante ese mismo limpio —para encontrarlo al lado del primero— y después de MARCA_DE_
# VARIANTE, ocho letras sacadas de cómo está escrito. sanitizar() nunca devuelve esa marca: no
# puede chocar con ningún código de ninguna lista ni cruzarse con otra lista por el código.
MARCA_DE_VARIANTE = "~"


def codigo_de_la_variante(raw):
    """El código limpio de un producto que sin los signos se escribe igual que otro de su
    lista: «CAMA1781030~3F09A1C2». Siempre el mismo para la misma forma de escribirlo."""
    limpio = sanitizar(raw)
    if not limpio:
        return ""
    return (f"{limpio}{MARCA_DE_VARIANTE}"
            f"{hashlib.sha1(_escrito(raw).encode('utf-8')).hexdigest()[:8].upper()}")


def es_codigo_de_variante(codigo_clean):
    return MARCA_DE_VARIANTE in str(codigo_clean or "")


def variantes_cargadas(marca_id):
    """Los códigos limpios de variante que ya tiene una lista: así, si la lista nueva trae
    solo el segundo de un par, va a SU producto y no al primero."""
    c.execute("SELECT codigo_clean FROM productos WHERE marca_id = ? AND codigo_clean LIKE ?",
              (marca_id, f"%{MARCA_DE_VARIANTE}%"))
    return {r[0] for r in c.fetchall()}


def los_que_se_escriben_igual(codigo_clean):
    """Los productos que sin los signos se escriben igual que este código (el primero y los
    que entraron aparte), menos él mismo: para avisarlo en el buscador. Lista de filas con
    ID, Código, Marca, Descripción, Precio y Stock."""
    base = str(codigo_clean or "").split(MARCA_DE_VARIANTE)[0]
    if not base:
        return []
    c.execute("""SELECT p.id AS "ID", p.codigo_raw AS "Código", m.nombre AS "Marca",
                        p.descripcion AS "Descripción", p.precio AS "Precio",
                        p.stock AS "Stock", p.codigo_clean AS "_clean"
                 FROM productos p JOIN marcas m ON m.id = p.marca_id
                 WHERE p.codigo_clean >= ? AND p.codigo_clean < ? AND p.codigo_clean <> ?""",
              (base + MARCA_DE_VARIANTE, base + chr(ord(MARCA_DE_VARIANTE) + 1), codigo_clean))
    otros = filas_a_listas(c)
    if not otros and not es_codigo_de_variante(codigo_clean):
        return []
    if es_codigo_de_variante(codigo_clean):
        # El primero del par (con el limpio de siempre), de la misma lista que la variante.
        c.execute("""SELECT p.id AS "ID", p.codigo_raw AS "Código", m.nombre AS "Marca",
                            p.descripcion AS "Descripción", p.precio AS "Precio",
                            p.stock AS "Stock", p.codigo_clean AS "_clean"
                     FROM productos p JOIN marcas m ON m.id = p.marca_id
                     WHERE p.codigo_clean = ? AND p.marca_id IN
                           (SELECT marca_id FROM productos WHERE codigo_clean = ?)""",
                  (base, codigo_clean))
        otros = filas_a_listas(c) + otros
    return otros


def es_otro_producto_con_el_mismo_codigo(raw, producto_id, formas):
    """Si este código de la lista cae en un producto escrito distinto, y la lista trae también
    el código escrito como ese producto, es otro producto que sin los signos se escribe igual:
    devuelve cómo se escribe el producto (para decirlo). Si no, ''. `formas`: ver
    como_se_escribe_cada_codigo()."""
    de_la_lista = formas.get(sanitizar(raw), ())
    if len(de_la_lista) < 2:
        return ""
    fila = c.execute("SELECT codigo_raw FROM productos WHERE id = ?", (producto_id,)).fetchone()
    del_producto = fila[0] if fila else ""
    if _escrito(raw) != _escrito(del_producto) and _escrito(del_producto) in de_la_lista:
        return del_producto
    return ""


# ============================================================================================
# QUÉ PIEZA ES CADA FAMILIA DE CÓDIGOS
# ============================================================================================
# IMPERIAL escribe la descripción por el auto y la corta en 30 letras: «SUZUKI HATCH ST80
# M.Y64» (10-580/3A), «FIAT Motor FIRE 1,3 L» (CAM-A2090), «Chevrolet CORSA 1.0 L. VHC SO»
# (PP0720). La lista no trae rubro —se miró el Excel del 18/08: código, precio y descripción,
# nada más— y en esas familias casi ningún producto dice qué pieza es (en «CAM», 0 de 471), así
# que no hay de dónde deducirlo. En la copia de la base del 12/10 son unos 12.800 productos así
# (casi todos de IMPERIAL): no se encuentran escribiendo «camisas fire» y no se comparan con
# nada. Lo sabe el que trabaja con la lista: le pone nombre a la familia una vez («CAM» son
# camisas) y la app se lo suma a las descripciones de esa familia que no dicen qué pieza son,
# ahora y en las listas que entren después. Se deshace con un toque.
# Solo a las que no tienen rubro, no nombran una pieza y sí un auto o un motor: «WABCO COJINETE
# LISO», «Compresor de Aire KNORR» o una llave de la misma familia quedan como estaban.

_RE_FAMILIA_CON_LETRAS = re.compile(r"[A-Z]+")
_RE_FAMILIA_CON_NUMEROS = re.compile(r"(\d+)[-/]")
# Desde cuántos productos sin pieza se propone una familia, y qué parte de ella tienen que ser.
FAMILIA_MINIMA_PARA_PROPONER = 20
PARTE_SIN_PIEZA_PARA_PROPONER = 0.6
LARGO_MAXIMO_DE_LA_PIEZA = 30
# Para proponer va rápido (sin la firma: 43.000 firmas son 9 s); para cambiar descripciones se
# usa no_dice_que_pieza_es(), solo sobre la familia elegida.
_RE_PUNTOS_DE_SIGLA = re.compile(r"\b([A-Z])\.(?=[A-Z]\b)")


def familia_del_codigo(codigo):
    """La familia de un código: las letras del principio («CAM» de CAM-A2090, «PP» de PP0720) o
    el número antes del primer guion o barra («10-» de 10-580/3A). '' si no tiene."""
    cod = str(codigo or "").strip().upper()
    m = _RE_FAMILIA_CON_LETRAS.match(cod)
    if m:
        return m.group(0)
    m = _RE_FAMILIA_CON_NUMEROS.match(cod)
    return f"{m.group(1)}-" if m else ""


def no_dice_que_pieza_es(descripcion):
    """Sin rubro, sin ninguna palabra de pieza y nombrando un auto o un motor: «FIAT Motor FIRE
    1,3 L» sí; «WABCO COJINETE LISO» (tiene rubro) o «LLAVE T HEXAGONAL» (no nombra un auto),
    no."""
    f = firma_de_producto(descripcion or "")
    return bool(f) and f.get("familia") == "Sin clasificar" and not f.get("pieza") \
        and nombra_algun_auto(f)


def _parece_que_no_dice_que_pieza_es(descripcion, marcas_de_autos):
    texto = _RE_PUNTOS_DE_SIGLA.sub(r"\1", normalizar_texto(descripcion))
    palabras = set(re.split(r"[^A-Z0-9]+", texto))
    return (bool(palabras & marcas_de_autos)
            and clasificar_repuesto(descripcion or "") == "Sin clasificar")


def familias_sin_nombre(marca_id):
    """Las familias de códigos de una lista cuyos productos, casi todos, no dicen qué pieza son:
    [{"familia", "productos", "sin_pieza", "ejemplos", "pieza"}], la más grande primero.
    «pieza» es el nombre que ya se le puso, si se le puso. Ver FAMILIA_MINIMA_PARA_PROPONER."""
    _marcas = {m.replace(".", "") for mv in MARCAS_VEHICULO for m in mv.split()} | set(
        _MARCAS_DE_MOTORES) | {"VW", "MWM", "IKA", "INDENOR", "MAXION", "DEERE", "BENZ"}
    nombradas = dict(c.execute("SELECT familia, pieza FROM piezas_de_las_familias "
                               "WHERE marca_id = ?", (marca_id,)).fetchall())
    por_familia = {}
    for cod, desc in c.execute("SELECT codigo_raw, descripcion FROM productos WHERE marca_id = ?",
                               (marca_id,)).fetchall():
        fam = familia_del_codigo(cod)
        if not fam:
            continue
        f = por_familia.setdefault(fam, {"familia": fam, "productos": 0, "sin_pieza": 0,
                                         "ejemplos": [], "pieza": nombradas.get(fam, "")})
        f["productos"] += 1
        if _parece_que_no_dice_que_pieza_es(desc, _marcas):
            f["sin_pieza"] += 1
            if len(f["ejemplos"]) < 3:
                f["ejemplos"].append(f"{cod} «{(desc or '')[:40]}»")
    salida = [f for f in por_familia.values()
              if f["pieza"] or (
                  f["sin_pieza"] >= FAMILIA_MINIMA_PARA_PROPONER
                  and f["sin_pieza"] >= f["productos"] * PARTE_SIN_PIEZA_PARA_PROPONER)]
    return sorted(salida, key=lambda f: (not f["pieza"], -f["sin_pieza"], f["familia"]))


def _pieza_escrita(pieza):
    texto = re.sub(r"\s+", " ", normalizar_texto(pieza)).strip()
    if not texto or not re.fullmatch(r"[A-Z0-9 ./-]+", texto) or not re.search(r"[A-Z]{3}", texto):
        raise ValueError("Escribí qué pieza es, con letras: por ejemplo «CAMISA» o «AROS».")
    return texto[:LARGO_MAXIMO_DE_LA_PIEZA]


def _productos_de_la_familia(marca_id, familia):
    c.execute("SELECT id, codigo_raw, descripcion FROM productos WHERE marca_id = ? "
              "AND UPPER(codigo_raw) LIKE ?", (marca_id, familia.rstrip("-") + "%"))
    return [r for r in c.fetchall() if familia_del_codigo(r["codigo_raw"]) == familia]


def nombrar_familia(marca_id, familia, pieza):
    """Le pone nombre a una familia de códigos y se lo suma, adelante, a las descripciones de esa
    familia que no dicen qué pieza son (ver no_dice_que_pieza_es()). Si ya tenía otro nombre, lo
    cambia. Devuelve cuántas descripciones cambió. Solo administrador: reescribe descripciones."""
    exigir_nivel("admin", "ponerle nombre a una familia de códigos")
    pieza = _pieza_escrita(pieza)
    familia = str(familia or "").strip().upper()
    if not familia:
        raise ValueError("Falta la familia.")
    sacar_nombre_de_familia(marca_id, familia, anotar=False)
    cambios = []
    for r in _productos_de_la_familia(marca_id, familia):
        if no_dice_que_pieza_es(r["descripcion"]):
            cambios.append((r["id"], r["descripcion"], f"{pieza} {r['descripcion'] or ''}".strip()))
    with db_lock, transaccion():
        c.executemany("INSERT OR IGNORE INTO descripciones_antes_de_la_familia (producto_id, "
                      "descripcion) VALUES (?, ?)", [(i, antes) for i, antes, _ in cambios])
        c.executemany("UPDATE productos SET descripcion = ? WHERE id = ?",
                      [(nueva, i) for i, _, nueva in cambios])
        c.execute("INSERT OR REPLACE INTO piezas_de_las_familias (marca_id, familia, pieza, quien) "
                  "VALUES (?, ?, ?, ?)", (marca_id, familia, pieza, obtener_usuario_actual()))
        anotar_cambio("nombró una familia de códigos", "marca", marca_id,
                      detalle=f"{familia} → {pieza}: {len(cambios)} descripción(es)")
    return len(cambios)


def sacar_nombre_de_familia(marca_id, familia, anotar=True):
    """Deshace nombrar_familia(): cada descripción vuelve a la de antes y la familia queda sin
    nombre. Devuelve cuántas volvieron."""
    exigir_nivel("admin", "sacarle el nombre a una familia de códigos")
    ids = [r["id"] for r in _productos_de_la_familia(marca_id, familia)]
    with db_lock, transaccion():
        vueltas = 0
        for i in ids:
            fila = c.execute("SELECT descripcion FROM descripciones_antes_de_la_familia "
                             "WHERE producto_id = ?", (i,)).fetchone()
            if fila is None:
                continue
            c.execute("UPDATE productos SET descripcion = ? WHERE id = ?", (fila[0], i))
            c.execute("DELETE FROM descripciones_antes_de_la_familia WHERE producto_id = ?", (i,))
            vueltas += 1
        c.execute("DELETE FROM piezas_de_las_familias WHERE marca_id = ? AND familia = ?",
                  (marca_id, familia))
        if anotar:
            anotar_cambio("le sacó el nombre a una familia de códigos", "marca", marca_id,
                          detalle=f"{familia}: {vueltas} descripción(es) como estaban")
    return vueltas


def con_la_pieza_de_su_familia(codigo, descripcion, marca_id):
    """La descripción con el nombre de su familia adelante, si la familia lo tiene y la
    descripción no dice qué pieza es. Para lo que entra al importar (ver
    get_or_create_producto())."""
    familia = familia_del_codigo(codigo)
    if not familia or not marca_id:
        return descripcion
    fila = c.execute("SELECT pieza FROM piezas_de_las_familias WHERE marca_id = ? AND familia = ?",
                     (marca_id, familia)).fetchone()
    if not fila or not no_dice_que_pieza_es(descripcion):
        return descripcion
    return f"{fila[0]} {descripcion or ''}".strip()


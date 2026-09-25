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
        return True, f"queda {razon:.1f} veces más caro (+{(razon - 1) * 100:.0f}%)"
    if razon < 1 / factor:
        return True, f"queda {1 / razon:.1f} veces más barato ({(razon - 1) * 100:.0f}%)"
    return False, None


def get_or_create_producto(raw, clean, desc, marca_id, imagen_url=None):
    c.execute(
        "INSERT OR IGNORE INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) VALUES (?, ?, ?, ?)",
        (raw, clean, desc, marca_id)
    )
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

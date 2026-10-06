"""Las autopartes de seguridad homologadas (CHAS): el registro oficial de la Secretaría de
Industria, y tus marcas contra él.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================================================
# AUTOPARTES DE SEGURIDAD: EL REGISTRO DE CHAS
# ============================================================================================
# En Argentina, una autoparte de seguridad (frenos, cinturones, vidrios, luces, espejos,
# cubiertas…) solo se puede vender de reposición con su CHAS: el Certificado de Homologación de
# Autopartes de Seguridad (Decreto 779/95, Anexo C; Resolución 166/2019). La Secretaría de
# Industria publica cada mes el registro de los CHAS vigentes, en datos abiertos, gratis.
#
# Para el negocio sirve para una pregunta concreta: ¿la marca que vendo de pastillas, discos o
# lámparas tiene CHAS? Una que no figura puede ser un problema el día de una inspección o de un
# reclamo, y es una pregunta para hacerle al proveedor antes de comprarle.
#
# CÓMO SE LEE. El archivo se baja del portal (el CSV más reciente del dataset) o se sube a mano.
# Las columnas no se adivinan por posición: se buscan por nombre (marca, empresa o razón social,
# autoparte o producto, número de CHAS, fecha), porque el formato no está documentado en ningún
# lado que se pueda leer desde acá y puede cambiar. Después de cargarlo, la pantalla dice qué
# columna se usó para qué.
#
# LO QUE NO DICE. Que una marca de tu catálogo no aparezca no prueba que no tenga CHAS: muchas
# listas nombran al distribuidor y no a la marca del producto, o la escriben distinto. Por eso
# se muestra como «no figura», para preguntar, nunca como «no tiene».
URL_PORTAL_PRODUCCION = ("https://datos.produccion.gob.ar/api/3/action/package_show"
                         "?id=registro_de_chas_emitidos")
# El último archivo conocido, por si el portal no contesta.
URL_CHAS_CONOCIDO = ("https://cdn.produccion.gob.ar/cdn-secind/datos-abiertos-chas/"
                     "chas-emitidos-a-diciembre-2024.csv")
DIAS_ENTRE_ACTUALIZACIONES_DEL_CHAS = 30
# El registro entero son unos miles de renglones. Más de esto es otro archivo.
TAMANIO_MAXIMO_DEL_CHAS = 40 * 1024 * 1024
CONFIG_DEL_CHAS = "registro_chas"
MESES_EN_CASTELLANO = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
                       "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
                       "noviembre": 11, "diciembre": 12}
# Qué columna es cuál: la primera palabra que aparezca en el nombre de la columna, en este
# orden. «nro_chas» es el número antes que «chas» a secas; «marca» va sola porque es la clave.
COLUMNAS_DEL_CHAS = {
    "numero": ("nro_chas", "numero_chas", "n_chas", "chas_n", "nro_certificado",
               "numero_certificado", "certificado", "chas", "numero", "nro"),
    "empresa": ("razon_social", "empresa", "titular", "solicitante", "beneficiario",
                "fabricante", "importador", "denominacion_social"),
    "marca": ("marca",),
    "autoparte": ("autoparte", "elemento", "producto", "familia", "rubro", "categoria",
                  "tipo", "descripcion", "denominacion"),
    "detalle": ("modelo", "codigo", "referencia", "articulo", "variante", "detalle"),
    "fecha": ("fecha_emision", "fecha_de_emision", "emision", "fecha", "vigencia",
              "otorgamiento"),
}
# Las piezas que en el mostrador son de seguridad, para no preguntar por un filtro de aire.
# Orientativo: la lista oficial es el Anexo C del Decreto 779/95.
PIEZAS_DE_SEGURIDAD = (
    "PASTILLA", "CINTA DE FRENO", "CINTAS DE FRENO", "DISCO DE FRENO", "DISCOS DE FRENO",
    "CAMPANA DE FRENO", "TAMBOR DE FRENO", "LIQUIDO DE FRENO", "LIQUIDO FRENO",
    "BOMBA DE FRENO", "CILINDRO DE RUEDA", "FLEXIBLE DE FRENO", "MANGUERA DE FRENO",
    "ZAPATA", "CINTURON", "PARABRISAS", "ESPEJO", "OPTICA", "FAROL", "FARO", "LAMPARA", "BOCINA",
    "NEUMATICO", "LLANTA", "EXTREMO DE DIRECCION", "ROTULA",
    # El líquido de frenos como lo escriben las listas que vienen en inglés.
    "BRAKE FLUID", "DOT 3", "DOT 4", "DOT3", "DOT4", "DOT 5",
)
# «CUBIERTA» no está a propósito: en las listas también es la tapa de distribución.


def _nombre_de_columna(texto):
    return re.sub(r"[^a-z0-9]+", "_", normalizar_texto(texto).lower()).strip("_")


def columnas_del_chas(encabezado):
    """{campo: índice} de las columnas que se reconocen. Cada columna sirve para un solo campo,
    y la marca se busca primero: es la que no puede faltar."""
    nombres = [_nombre_de_columna(h) for h in encabezado]
    usadas, salida = set(), {}
    for campo in ("marca", "numero", "empresa", "autoparte", "detalle", "fecha"):
        for palabra in COLUMNAS_DEL_CHAS[campo]:
            i = next((i for i, n in enumerate(nombres)
                      if i not in usadas and (n == palabra or palabra in n.split("_")
                                              or n.startswith(palabra + "_")
                                              or ("_" in palabra and palabra in n))), None)
            if i is not None:
                salida[campo] = i
                usadas.add(i)
                break
    return salida


def leer_el_registro_chas(texto):
    """(filas, columnas, error). filas: [{numero, empresa, marca, autoparte, detalle, fecha}].
    columnas: {campo: nombre de la columna del archivo}, para mostrar qué se leyó."""
    texto = str(texto or "").lstrip("﻿")
    if not texto.strip():
        return [], {}, "El archivo está vacío."
    lector = csv.reader(io.StringIO(texto), delimiter=_detectar_separador(texto))
    encabezado = next(lector, [])
    columnas = columnas_del_chas(encabezado)
    if "marca" not in columnas and "empresa" not in columnas:
        return [], {}, ("No encontré una columna de marca ni de empresa. Las columnas del "
                        "archivo son: " + ", ".join(h.strip() for h in encabezado[:15]))
    filas = []
    for renglon in lector:
        if not any(x.strip() for x in renglon):
            continue
        fila = {campo: (renglon[i].strip() if i < len(renglon) else "")
                for campo, i in columnas.items()}
        if not (fila.get("marca") or fila.get("empresa")):
            continue
        filas.append({campo: fila.get(campo, "") for campo in COLUMNAS_DEL_CHAS})
    nombres = {campo: encabezado[i].strip() for campo, i in columnas.items()}
    if not filas:
        return [], nombres, "El archivo tiene el encabezado pero ningún renglón con marca."
    return filas, nombres, None


def guardar_el_registro_chas(filas, origen, columnas=None):
    """Reemplaza el registro guardado por estas filas, todo o nada, y anota de dónde vino."""
    with db_lock, transaccion():
        c.execute("DELETE FROM chas_emitidos")
        c.executemany("""INSERT INTO chas_emitidos (numero, empresa, marca, marca_norm,
                                                    autoparte, detalle, fecha)
                         VALUES (?, ?, ?, ?, ?, ?, ?)""",
                      [(f["numero"][:60], f["empresa"][:200], f["marca"][:120],
                        _nombre_normalizado(f["marca"] or f["empresa"]), f["autoparte"][:200],
                        f["detalle"][:200], f["fecha"][:20]) for f in filas])
    resumen = {"traido": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "origen": origen,
               "certificados": len(filas),
               "marcas": len({_nombre_normalizado(f["marca"] or f["empresa"]) for f in filas}),
               "columnas": columnas or {}}
    guardar_config(CONFIG_DEL_CHAS, json.dumps(resumen))
    del_proceso("marcas_con_chas", dict).clear()
    return resumen


def resumen_del_chas():
    """Lo que se anotó al guardar el registro ({} si nunca se cargó)."""
    try:
        return json.loads(obtener_config(CONFIG_DEL_CHAS, "") or "{}")
    except (ValueError, TypeError):
        return {}


def _mes_del_archivo(url):
    """(año, mes) de «chas-emitidos-a-diciembre-2024.csv», o (0, 0)."""
    nombre = normalizar_texto(str(url or "").rsplit("/", 1)[-1]).lower()
    m = re.search(r"([a-z]+)[-_ ]?(\d{4})", nombre)
    while m:
        if m.group(1) in MESES_EN_CASTELLANO:
            return int(m.group(2)), MESES_EN_CASTELLANO[m.group(1)]
        m = re.search(r"([a-z]+)[-_ ]?(\d{4})", nombre[m.end():])
    m = re.search(r"(20\d{2})[-_]?(\d{2})", nombre)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def archivo_mas_reciente_del_chas():
    """La URL del CSV más reciente según el portal, por el mes que dice su nombre; si el portal
    no contesta o no trae ninguno, el último conocido."""
    datos = _pedir_json(URL_PORTAL_PRODUCCION, tiempo_maximo=20)
    recursos = (((datos or {}).get("result") or {}).get("resources")
                if isinstance(datos, dict) else None) or []
    csvs = [str((r or {}).get("url") or "") for r in recursos
            if str((r or {}).get("url") or "").lower().endswith(".csv")
            or str((r or {}).get("format") or "").upper() == "CSV"]
    csvs = [u for u in csvs if u]
    if not csvs:
        return URL_CHAS_CONOCIDO
    return max(csvs, key=lambda u: (_mes_del_archivo(u), u))


def actualizar_el_registro_chas(forzar=False):
    """Baja el registro si pasaron DIAS_ENTRE_ACTUALIZACIONES_DEL_CHAS días (o si se fuerza).
    Para la tarea de fondo y para el botón. Devuelve el resumen, o None si no hacía falta.
    Levanta la excepción si falla: el que llama decide si avisa o la anota."""
    ultimo = resumen_del_chas()
    if not forzar and ultimo.get("traido"):
        try:
            hace = datetime.now() - datetime.strptime(ultimo["traido"][:19], "%Y-%m-%d %H:%M:%S")
            if hace < timedelta(days=DIAS_ENTRE_ACTUALIZACIONES_DEL_CHAS):
                return None
        except ValueError:
            pass
    url = archivo_mas_reciente_del_chas()
    respuesta = requests.get(url, timeout=(15, 90), stream=True,
                             headers={"User-Agent": "EquivalenciasElChavo/1.0"})
    respuesta.raise_for_status()
    crudo = b""
    for pedazo in respuesta.iter_content(256 * 1024):
        crudo += pedazo
        if len(crudo) > TAMANIO_MAXIMO_DEL_CHAS:
            raise ValueError("El archivo del registro es demasiado grande: no es el de siempre.")
    filas, columnas, error = leer_el_registro_chas(_decodificar_texto(crudo))
    if error:
        raise ValueError(error)
    return guardar_el_registro_chas(filas, url, columnas)


def cargar_el_registro_chas_a_mano(crudo, nombre=""):
    """El CSV bajado a mano del portal. (resumen, error)."""
    if len(crudo or b"") > TAMANIO_MAXIMO_DEL_CHAS:
        return None, "El archivo es demasiado grande para ser el registro de CHAS."
    filas, columnas, error = leer_el_registro_chas(_decodificar_texto(crudo or b""))
    if error:
        return None, error
    return guardar_el_registro_chas(filas, f"subido a mano: {nombre}".strip(), columnas), None


def _marcas_con_chas():
    """{marca normalizada: {"certificados", "autopartes": [las más frecuentes]}}. Guardado en
    el proceso hasta que se cargue otro registro."""
    guardado = del_proceso("marcas_con_chas", dict)
    if "mapa" not in guardado:
        c.execute("""SELECT marca_norm, autoparte, COUNT(*) AS n FROM chas_emitidos
                     WHERE marca_norm <> '' GROUP BY marca_norm, autoparte""")
        mapa = {}
        for r in c.fetchall():
            d = mapa.setdefault(r["marca_norm"], {"certificados": 0, "autopartes": []})
            d["certificados"] += r["n"]
            if r["autoparte"]:
                d["autopartes"].append((r["n"], r["autoparte"]))
        for d in mapa.values():
            d["autopartes"] = [a for _n, a in sorted(d["autopartes"], reverse=True)[:4]]
        guardado["mapa"] = mapa
    return guardado["mapa"]


def chas_de_la_marca(marca):
    """Lo que el registro tiene para esa marca de tu catálogo: {"marca_en_el_registro",
    "certificados", "autopartes"} o None. La misma marca, o una cuyas palabras empiezan con las
    de la otra («MANNOL» y «MANNOL LUBRICANTES»); nunca una adentro de otra palabra."""
    buscada = _nombre_normalizado(marca)
    if len(buscada) < 3:
        return None
    mapa = _marcas_con_chas()
    if buscada in mapa:
        return dict(mapa[buscada], marca_en_el_registro=buscada)
    for nombre, datos in mapa.items():
        if len(nombre) >= 3 and (buscada.startswith(nombre + " ")
                                 or nombre.startswith(buscada + " ")):
            return dict(datos, marca_en_el_registro=nombre)
    return None


def es_pieza_de_seguridad(descripcion):
    """Si la PIEZA es de seguridad: el nombre tiene que estar al principio (primera palabra, o
    segunda detrás de una sigla). Mirado en la base real: «Tecla faros antiniebla», «Portátil para lámpara» o
    «Llave de luces… doble faro» nombran un faro o una lámpara, pero la pieza es una tecla, un
    portátil o una llave. «MN DOT 4 (Líquido de frenos)» sí: el DOT 4 va segundo."""
    palabras = _nombre_normalizado(descripcion).split()
    # Segunda solo detrás de una sigla o un código («MN DOT 4»): detrás de una palabra
    # («TECLA faros») la pieza es la primera.
    segunda = bool(palabras) and (len(palabras[0]) <= 3 or any(ch.isdigit() for ch in palabras[0]))
    for desde in ((0, 1) if segunda else (0,)):
        resto = " ".join(palabras[desde:]) + " "
        if any(resto.startswith(p) and (resto[len(p)] in " S") for p in PIEZAS_DE_SEGURIDAD):
            return True
    return False


# Palabras que también son marcas en el registro pero que en una descripción no nombran a
# ninguna: «FRENO», «ORIGINAL», «UNIVERSAL»…
PALABRAS_QUE_NO_SON_MARCAS = {
    "AUTO", "AUTOS", "ORIGINAL", "UNIVERSAL", "STANDARD", "STANDAR", "PREMIUM", "FRENO",
    "FRENOS", "LUZ", "LUCES", "LAMPARA", "LAMPARAS", "ESPEJO", "ESPEJOS", "DISCO", "DISCOS",
    "PASTILLA", "PASTILLAS", "SPORT", "PLUS", "SUPER", "EXTRA", "LINEA", "TOTAL", "RACING",
    "CAJA", "JUEGO", "KIT", "LED", "HALOGENA", "XENON", "DELANTERO", "TRASERO", "DERECHO",
    "IZQUIERDO", "MOTOR", "IMPORTADO", "NACIONAL", "ARGENTINA",
}


def _patron_de_marcas_con_chas():
    """Una expresión con las marcas del registro, como palabras enteras, para encontrarlas
    adentro de una descripción. Guardada en el proceso, como el mapa."""
    guardado = del_proceso("marcas_con_chas", dict)
    if "patron" not in guardado:
        nombres = sorted((n for n in _marcas_con_chas()
                          if len(n) >= 4 and n not in PALABRAS_QUE_NO_SON_MARCAS),
                         key=len, reverse=True)
        guardado["patron"] = (re.compile(r"(?<![A-Z0-9])(" + "|".join(map(re.escape, nombres))
                                         + r")(?![A-Z0-9])") if nombres else None)
    return guardado["patron"]


def chas_de_la_pieza(marca, descripcion):
    """El CHAS que corresponde a un producto: el de la marca con que está cargado, o si no, el
    de una marca del registro que la descripción nombre («…zócalo Marelli»). Las listas de los
    distribuidores cargan todo con el nombre del distribuidor y la marca del producto va en el
    texto. {"marca_en_el_registro", "certificados", "autopartes"} o None."""
    chas = chas_de_la_marca(marca)
    if chas:
        return chas
    patron = _patron_de_marcas_con_chas()
    encontrada = patron.search(_nombre_normalizado(descripcion)) if patron else None
    if not encontrada:
        return None
    return dict(_marcas_con_chas()[encontrada.group(1)], marca_en_el_registro=encontrada.group(1))


def marcas_del_catalogo_contra_el_chas(limite=200):
    """Tus marcas (proveedores) que venden piezas de seguridad, con cuántas de esas piezas
    tienen un CHAS a la vista: por la marca con que están cargadas o por una marca del registro
    que nombra la descripción. Las que más piezas sin dato tienen, primero. Los códigos de
    fábrica (marcas de tipo OEM) no van: no son una marca que se homologue."""
    condicion = " OR ".join(["UPPER(p.descripcion) LIKE ?"] * len(PIEZAS_DE_SEGURIDAD))
    c.execute(f"""SELECT m.nombre AS marca, p.descripcion FROM productos p
                  JOIN marcas m ON m.id = p.marca_id
                  WHERE COALESCE(m.tipo, '') <> 'OEM' AND ({condicion})""",
              [f"%{p}%" for p in PIEZAS_DE_SEGURIDAD])
    por_marca = {}
    for r in c.fetchall():
        if not es_pieza_de_seguridad(r["descripcion"]):
            continue
        d = por_marca.setdefault(r["marca"], {"piezas": 0, "con": 0, "nombres": collections.Counter()})
        d["piezas"] += 1
        chas = chas_de_la_pieza(r["marca"], r["descripcion"])
        if chas:
            d["con"] += 1
            d["nombres"][chas["marca_en_el_registro"]] += 1
    filas = [{"Marca": marca, "Piezas de seguridad": d["piezas"],
              "Con CHAS a la vista": d["con"], "Sin dato": d["piezas"] - d["con"],
              "Marcas con CHAS que aparecen": ", ".join(n for n, _k in d["nombres"].most_common(5))}
             for marca, d in por_marca.items()]
    filas.sort(key=lambda f: (-f["Sin dato"], f["Marca"]))
    return filas[:limite]


def buscar_en_el_chas(texto, limite=50):
    """Los certificados cuya marca, empresa o autoparte nombra lo buscado."""
    palabra = f"%{_nombre_normalizado(texto)}%"
    if len(palabra) < 4:
        return []
    c.execute("""SELECT numero, marca, empresa, autoparte, detalle, fecha FROM chas_emitidos
                 WHERE marca_norm LIKE ? OR UPPER(empresa) LIKE ? OR UPPER(autoparte) LIKE ?
                 ORDER BY marca, autoparte LIMIT ?""", (palabra, palabra, palabra, limite))
    return [{"CHAS": r["numero"], "Marca": r["marca"], "Empresa": r["empresa"],
             "Autoparte": r["autoparte"], "Detalle": r["detalle"], "Fecha": r["fecha"]}
            for r in c.fetchall()]


def chas_en_los_resultados(resultados):
    """[(marca como figura en el registro, datos)] de las piezas de seguridad de estos
    resultados que tienen CHAS a la vista (ver chas_de_la_pieza()). Para la línea del
    buscador: solo dice lo que hay."""
    if not resumen_del_chas().get("certificados"):
        return []
    salida, vistas = [], set()
    for fila in resultados or []:
        marca = fila.get("Marca")
        if not marca or not es_pieza_de_seguridad(fila.get("Descripcion")):
            continue
        chas = chas_de_la_pieza(marca, fila.get("Descripcion"))
        if chas and chas["marca_en_el_registro"] not in vistas:
            vistas.add(chas["marca_en_el_registro"])
            salida.append((chas["marca_en_el_registro"], chas))
    return salida

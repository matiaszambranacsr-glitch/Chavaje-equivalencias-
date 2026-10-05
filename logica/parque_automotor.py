"""El parque automotor de verdad: qué autos circulan, según el registro automotor (DNRPA).

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""
import csv

# ============================================================================================
# EL PARQUE AUTOMOTOR: QUÉ AUTOS CIRCULAN (DNRPA)
# ============================================================================================
# La fuente: el registro automotor publica TODOS los meses, en el portal de datos abiertos del
# Ministerio de Justicia, cada trámite de cada Registro Seccional del país. Es oficial, gratuita
# y sin clave. Se usa el de TRANSFERENCIAS y no el de inscripciones iniciales: las iniciales son
# los 0 km desde 2018, y una casa de repuestos le vende al parque que circula —el Falcon, el
# 504, el Gol de 2009—, que es el que se compra y se vende usado.
#
# Para qué: «🚗 Los autos que más circulan, contra tu catálogo» (Para pedir) cruza los modelos
# más transferidos de la provincia con cuántos productos del catálogo los nombran. Ahí se ven los
# autos comunes para los que casi no hay nada cargado. No toca ninguna regla de equivalencias.
#
# Lo que NO se hace: del archivo oficial se leen solo marca, modelo, año y provincia. Trae datos
# de los titulares —localidad, género, año de nacimiento—; no se leen ni se guardan.
#
# El formato está en la documentación oficial del dataset (github.com/datos-justicia-argentina/
# dnrpa-transferencias-autos): CSV con comas, UTF-8, un archivo por mes
# «dnrpa-transferencias-autos-AAAAMM.csv». El portal es un CKAN, y la lista de archivos sale de
# su API estándar (package_show). Ver pruebas_de_las_fuentes.py.
URL_PORTAL_JUSTICIA = "https://datos.jus.gob.ar/api/3/action/package_show?id={dataset}"
DATASETS_DEL_PARQUE = ("transferencias-de-autos", "inscripciones-iniciales-de-autos")
_RE_ARCHIVO_DEL_MES = re.compile(r"dnrpa-[a-z-]+-(\d{6})\.csv$", re.I)
# Cada cuánto se vuelve a bajar: el DNRPA publica una vez por mes.
DIAS_ENTRE_ACTUALIZACIONES_DEL_PARQUE = 25
# Topes para no colgar el servidor con un archivo raro: renglones y minutos.
MAXIMO_RENGLONES_DEL_PARQUE = 600_000
MINUTOS_MAXIMOS_DEL_PARQUE = 8
# Las columnas que se leen. Nada más.
_COLUMNAS_DEL_PARQUE = ("automotor_marca_descripcion", "automotor_modelo_descripcion",
                        "automotor_anio_modelo", "registro_seccional_provincia")


def _nombre_normalizado(texto):
    """«MERCEDES-BENZ» → «MERCEDES BENZ»; sin acentos, mayúsculas, sin signos sueltos."""
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", normalizar_texto(texto))).strip()


def palabra_del_modelo(descripcion):
    """La palabra con que se nombra el modelo en un mostrador: la primera de la descripción del
    registro. «GOL TREND 1.6 PACK I» → «GOL», «208 ACTIVE 1.6» → «208», «S10 2.8 TDI» → «S10».
    Vacía si no hay ninguna que sirva."""
    for palabra in _nombre_normalizado(descripcion).split():
        if len(palabra) >= 2 and not re.fullmatch(r"\d[.,]?\d?", palabra):
            return palabra
    return ""


def archivo_mas_reciente_del_parque(dataset):
    """(url, «AAAAMM») del CSV mensual más reciente del dataset, según el portal; o (None, None).

    La respuesta del CKAN es {"success": true, "result": {"resources": [{"url": ..., "name":
    ..., "format": "CSV"}, ...]}}. Se elige por el AAAAMM del nombre del archivo, no por el
    orden de la lista ni por la fecha de modificación, que el portal no siempre completa."""
    datos = _pedir_json(URL_PORTAL_JUSTICIA.format(dataset=dataset), tiempo_maximo=20)
    recursos = ((datos or {}).get("result") or {}).get("resources") if isinstance(datos, dict) else None
    mejor = (None, None)
    for r in recursos or []:
        url = str((r or {}).get("url") or "")
        m = _RE_ARCHIVO_DEL_MES.search(url)
        if m and (mejor[1] is None or m.group(1) > mejor[1]):
            mejor = (url, m.group(1))
    return mejor


def contar_el_parque(renglones):
    """{(provincia, marca, palabra del modelo, año): cantidad} a partir de los renglones del CSV
    (texto, con el encabezado primero). Lee solo las columnas de _COLUMNAS_DEL_PARQUE."""
    lector = csv.reader(renglones)
    encabezado = [h.strip().lstrip("﻿").lower() for h in next(lector, [])]
    try:
        i_marca, i_modelo, i_anio, i_prov = (encabezado.index(c) for c in _COLUMNAS_DEL_PARQUE)
    except ValueError:
        return {}
    cuenta = collections.Counter()
    inicio = time.monotonic()
    for n, fila in enumerate(lector):
        if n >= MAXIMO_RENGLONES_DEL_PARQUE or (
                n % 5000 == 0 and time.monotonic() - inicio > MINUTOS_MAXIMOS_DEL_PARQUE * 60):
            break
        if n % 5000 == 0:
            ceder_al_mostrador()
        try:
            marca = _nombre_normalizado(fila[i_marca])
            modelo = palabra_del_modelo(fila[i_modelo])
            anio = int(fila[i_anio]) if str(fila[i_anio]).strip().isdigit() else None
            provincia = _nombre_normalizado(fila[i_prov]) or "SIN PROVINCIA"
        except IndexError:
            continue
        if marca and modelo:
            cuenta[(provincia, marca, modelo, anio)] += 1
    return cuenta


def _renglones_de(url):
    """Los renglones del CSV, de a uno y sin bajarlo entero a memoria."""
    respuesta = requests.get(url, stream=True, timeout=(15, 120),
                             headers={"User-Agent": "EquivalenciasElChavo/1.0"})
    respuesta.raise_for_status()
    for renglon in respuesta.iter_lines():
        if renglon:
            yield renglon.decode("utf-8", errors="replace")


def actualizar_parque_automotor(forzar=False):
    """Baja el último mes publicado y guarda los conteos. Para la tarea de fondo: sale a internet
    y puede tardar unos minutos. Devuelve un resumen, o None si no hacía falta.

    No hace falta si se bajó hace menos de DIAS_ENTRE_ACTUALIZACIONES_DEL_PARQUE días, ni
    tampoco si el mes más reciente del portal es el que ya está."""
    try:
        ultimo = json.loads(obtener_config("parque_automotor", "") or "{}")
    except (ValueError, TypeError):
        ultimo = {}
    if not forzar and ultimo.get("traido"):
        try:
            hace = datetime.now() - datetime.strptime(ultimo["traido"][:19], "%Y-%m-%d %H:%M:%S")
            if hace < timedelta(days=DIAS_ENTRE_ACTUALIZACIONES_DEL_PARQUE):
                return None
        except ValueError:
            pass
    for dataset in DATASETS_DEL_PARQUE:
        url, mes = archivo_mas_reciente_del_parque(dataset)
        if not url:
            continue
        if not forzar and ultimo.get("mes") == mes and ultimo.get("dataset") == dataset:
            guardar_config("parque_automotor", json.dumps(dict(ultimo, traido=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))))
            return None
        try:
            cuenta = contar_el_parque(_renglones_de(url))
        except Exception as _err:      # de red o de formato: se reintenta en la próxima vuelta
            anotar_error("actualizar_parque_automotor", _err)
            continue
        if not cuenta:
            continue
        guardar_el_parque(cuenta, mes)
        resumen = {"dataset": dataset, "mes": mes, "url": url,
                   "autos": sum(cuenta.values()),
                   "traido": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        guardar_config("parque_automotor", json.dumps(resumen))
        return resumen
    return None


def guardar_el_parque(cuenta, mes):
    """Reemplaza lo guardado por estos conteos, todo o nada."""
    with db_lock, transaccion():
        c.execute("DELETE FROM parque_automotor")
        c.executemany("INSERT INTO parque_automotor (mes, provincia, marca, modelo, anio, cantidad) "
                      "VALUES (?, ?, ?, ?, ?, ?)",
                      [(mes, p, m, mo, a, n) for (p, m, mo, a), n in cuenta.items()])


def provincias_del_parque():
    """[(provincia, autos)] de mayor a menor."""
    c.execute("SELECT provincia, SUM(cantidad) AS n FROM parque_automotor "
              "GROUP BY provincia ORDER BY n DESC")
    return [(r["provincia"], r["n"]) for r in c.fetchall()]


def _cuantos_productos_nombran(modelos):
    """{(marca, palabra): productos del catálogo que nombran ese modelo}, en UNA pasada.

    Nombrar el modelo es: la palabra está en la descripción, y además la marca —o la palabra
    es lo bastante propia como para no hacer falta: «PALIO» es de Fiat y de nadie más, «KA» o
    «208» solos no dicen nada—."""
    por_palabra = {}
    for marca, palabra in modelos:
        por_palabra.setdefault(palabra, []).append(marca)
    cuenta = collections.Counter()
    c.execute("SELECT descripcion FROM productos WHERE descripcion IS NOT NULL")
    for (desc,) in c.fetchall():
        texto = normalizar_texto(desc)
        palabras = set(re.findall(r"[A-Z0-9]+", texto)) & por_palabra.keys()
        if not palabras:
            continue
        marcas = {_nombre_normalizado(m) for m, _cat, _r in marcas_vehiculo_en(desc)}
        for palabra in palabras:
            for marca in por_palabra[palabra]:
                propia = len(palabra) >= 4 and not palabra.isdigit()
                if marca in marcas or propia:
                    cuenta[(marca, palabra)] += 1
    return cuenta


def autos_que_mas_circulan_contra_el_catalogo(provincia=None, limite=40):
    """Los modelos más transferidos (de la provincia, o de todo el país), con cuántos productos
    del catálogo los nombran. [] si todavía no se bajó el parque."""
    filtro, params = ("WHERE provincia = ?", [provincia]) if provincia else ("", [])
    c.execute(f"""SELECT marca, modelo, SUM(cantidad) AS n,
                         MIN(anio) AS desde, MAX(anio) AS hasta
                  FROM parque_automotor {filtro}
                  GROUP BY marca, modelo ORDER BY n DESC LIMIT ?""", params + [limite])
    filas = filas_a_listas(c)
    if not filas:
        return []
    # Recorrer el catálogo cuesta casi 2 s: se recuerda mientras no cambien ni el catálogo ni
    # el mes del parque. Del proceso (ver del_proceso()): lo comparten todas las sesiones.
    _memoria = del_proceso("autos_contra_el_catalogo", dict)
    _clave = (tuple((f["marca"], f["modelo"]) for f in filas), version_del_catalogo())
    if _clave not in _memoria:
        _memoria.clear()
        _memoria[_clave] = _cuantos_productos_nombran([(f["marca"], f["modelo"]) for f in filas])
    productos = _memoria[_clave]
    total_pais = sum(r["n"] for r in c.execute(
        "SELECT SUM(cantidad) AS n FROM parque_automotor" + (" WHERE provincia = ?" if provincia else ""),
        params).fetchall()) or 1
    # «Poco cargado» es contra los demás de la tabla, no un número fijo: la mediana de los
    # modelos más comunes. Con el catálogo real: Etios 91, Up 139 y Cronos 143 productos,
    # contra más de mil del Gol, el Palio, el Clio o el Fiesta.
    _cuantos = sorted(productos.get((f["marca"], f["modelo"]), 0) for f in filas)
    umbral = _cuantos[len(_cuantos) // 2] * 0.25
    salida = []
    for f in filas:
        n_prod = productos.get((f["marca"], f["modelo"]), 0)
        salida.append({
            "Marca": f["marca"], "Modelo": f["modelo"],
            "Se transfirieron": f["n"],
            "Del parque": f"{miles(f['n'] / total_pais * 100, 1)}%",
            "Años": (f"{f['desde']}–{f['hasta']}" if f["desde"] and f["hasta"] else "—"),
            "Productos que lo nombran": n_prod,
            "": "⚠️ poco cargado" if n_prod < umbral else "",
            "_n": f["n"], "_prod": n_prod,
        })
    return salida

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
# Y LOS 0 KM: el mismo registro publica las INSCRIPCIONES INICIALES (los patentamientos) con el
# mismo formato. No son el parque de hoy —un 0 km pasa años en el service del concesionario—,
# sino el de dentro de unos años: el Cronos o la Tera que hoy se patentan por miles son los que
# van a venir a buscar repuestos cuando se les venza la garantía. Se cuentan aparte y nunca se
# mezclan con las transferencias (antes las inscripciones eran el respaldo si las transferencias
# no se podían bajar, y eso contaba como «parque» autos que todavía no lo son).
#
# Lo que NO se hace: del archivo oficial se leen solo marca, modelo, año, provincia y la fecha
# del trámite. Trae datos de los titulares —localidad, género, año de nacimiento—; no se leen ni
# se guardan.
#
# El formato está en la documentación oficial de cada dataset (github.com/datos-justicia-
# argentina/dnrpa-transferencias-autos y …/dnrpa-inscripciones-iniciales-autos): CSV con comas,
# UTF-8, un archivo por mes «dnrpa-…-autos-AAAAMM.csv». El portal es un CKAN, y la lista de
# archivos sale de su API estándar (package_show). Ver pruebas_de_las_fuentes.py.
URL_PORTAL_JUSTICIA = "https://datos.jus.gob.ar/api/3/action/package_show?id={dataset}"
# Lo que se cuenta: {clave: (dataset del portal, tabla, clave de configuración)}.
CONTEOS_DEL_DNRPA = {
    "parque": ("transferencias-de-autos", "parque_automotor", "parque_automotor"),
    "0km": ("inscripciones-iniciales-de-autos", "patentamientos_0km", "patentamientos_0km"),
}
_RE_ARCHIVO_DEL_MES = re.compile(r"dnrpa-[a-z-]+-(\d{6})\.csv$", re.I)
# Cada cuánto se vuelve a bajar: el DNRPA publica una vez por mes.
DIAS_ENTRE_ACTUALIZACIONES_DEL_PARQUE = 25
# Topes para no colgar el servidor con un archivo raro: renglones y minutos.
MAXIMO_RENGLONES_DEL_PARQUE = 600_000
MINUTOS_MAXIMOS_DEL_PARQUE = 8
# Las columnas que se leen. Nada más. La fecha del trámite es opcional: sirve para decir de qué
# días son los datos, no para contar.
_COLUMNAS_DEL_PARQUE = ("automotor_marca_descripcion", "automotor_modelo_descripcion",
                        "automotor_anio_modelo", "registro_seccional_provincia")
_COLUMNA_DE_LA_FECHA = "tramite_fecha"


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


def contar_el_parque(renglones, rango=None):
    """{(provincia, marca, palabra del modelo, año): cantidad} a partir de los renglones del CSV
    (texto, con el encabezado primero). Lee solo las columnas de _COLUMNAS_DEL_PARQUE.

    Si se le pasa un dict en `rango`, le anota de qué días son los trámites («desde», «hasta»)
    y si se cortó por los topes («cortado»): es lo que la pantalla dice debajo de la tabla."""
    lector = csv.reader(renglones)
    encabezado = [h.strip().lstrip("\ufeff").lower() for h in next(lector, [])]
    try:
        i_marca, i_modelo, i_anio, i_prov = (encabezado.index(col) for col in _COLUMNAS_DEL_PARQUE)
    except ValueError:
        return {}
    i_fecha = encabezado.index(_COLUMNA_DE_LA_FECHA) if _COLUMNA_DE_LA_FECHA in encabezado else None
    fechas = set()
    cuenta = collections.Counter()
    inicio = time.monotonic()
    cortado = False
    for n, fila in enumerate(lector):
        if n >= MAXIMO_RENGLONES_DEL_PARQUE or (
                n % 5000 == 0 and time.monotonic() - inicio > MINUTOS_MAXIMOS_DEL_PARQUE * 60):
            cortado = True
            break
        if n % 5000 == 0:
            ceder_al_mostrador()
        try:
            marca = _nombre_normalizado(fila[i_marca])
            modelo = palabra_del_modelo(fila[i_modelo])
            anio = int(fila[i_anio]) if str(fila[i_anio]).strip().isdigit() else None
            provincia = _nombre_normalizado(fila[i_prov]) or "SIN PROVINCIA"
            if i_fecha is not None and re.fullmatch(r"\d{4}-\d{2}-\d{2}", fila[i_fecha][:10]):
                fechas.add(fila[i_fecha][:10])
        except IndexError:
            continue
        if marca and modelo:
            cuenta[(provincia, marca, modelo, anio)] += 1
    if rango is not None:
        rango.update({"desde": min(fechas, default=""), "hasta": max(fechas, default=""),
                      "cortado": cortado})
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
    """Baja el último mes publicado de las transferencias y de los 0 km, y guarda los conteos.
    Para la tarea de fondo: sale a internet y puede tardar unos minutos. Devuelve
    {clave: resumen} de lo que se bajó, o None si no hacía falta nada."""
    bajados = {}
    for clave in CONTEOS_DEL_DNRPA:
        try:
            resumen = _actualizar_un_conteo(clave, forzar)
        except Exception as _err:      # de red o de formato: se reintenta en la próxima vuelta
            anotar_error(f"actualizar_parque_automotor/{clave}", _err)
            resumen = None
        if resumen:
            bajados[clave] = resumen
    return bajados or None


def _actualizar_un_conteo(clave, forzar=False):
    """Uno de CONTEOS_DEL_DNRPA. El resumen, o None si no hacía falta o no se pudo.

    No hace falta si se bajó hace menos de DIAS_ENTRE_ACTUALIZACIONES_DEL_PARQUE días, ni
    tampoco si el mes más reciente del portal es el que ya está."""
    dataset, tabla, config = CONTEOS_DEL_DNRPA[clave]
    try:
        ultimo = json.loads(obtener_config(config, "") or "{}")
    except (ValueError, TypeError):
        ultimo = {}
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not forzar and ultimo.get("traido"):
        try:
            hace = datetime.now() - datetime.strptime(ultimo["traido"][:19], "%Y-%m-%d %H:%M:%S")
            if hace < timedelta(days=DIAS_ENTRE_ACTUALIZACIONES_DEL_PARQUE):
                return None
        except ValueError:
            pass
    url, mes = archivo_mas_reciente_del_parque(dataset)
    if not url:
        return None
    if not forzar and ultimo.get("mes") == mes and ultimo.get("dataset") == dataset:
        guardar_config(config, json.dumps(dict(ultimo, traido=ahora)))
        return None
    rango = {}
    cuenta = contar_el_parque(_renglones_de(url), rango)
    if not cuenta:
        return None
    guardar_el_parque(cuenta, mes, tabla)
    resumen = {"dataset": dataset, "mes": mes, "url": url, "autos": sum(cuenta.values()),
               "traido": ahora, **rango}
    guardar_config(config, json.dumps(resumen))
    return resumen


def guardar_el_parque(cuenta, mes, tabla="parque_automotor"):
    """Reemplaza lo guardado en esa tabla por estos conteos, todo o nada."""
    if tabla not in {t for _d, t, _c in CONTEOS_DEL_DNRPA.values()}:
        raise ValueError(f"tabla desconocida: {tabla}")
    with db_lock, transaccion():
        c.execute(f"DELETE FROM {tabla}")
        c.executemany(f"INSERT INTO {tabla} (mes, provincia, marca, modelo, anio, cantidad) "
                      "VALUES (?, ?, ?, ?, ?, ?)",
                      [(mes, p, m, mo, a, n) for (p, m, mo, a), n in cuenta.items()])


def resumen_del_conteo(clave):
    """Lo que se guardó la última vez que se bajó ese conteo ({} si nunca)."""
    try:
        return json.loads(obtener_config(CONTEOS_DEL_DNRPA[clave][2], "") or "{}")
    except (ValueError, TypeError):
        return {}


def provincias_del_parque():
    """[(provincia, autos)] de mayor a menor, de las transferencias y los 0 km juntos (es solo
    para el selector: una provincia con datos en cualquiera de los dos tiene que estar)."""
    c.execute("SELECT provincia, SUM(n) AS n FROM ("
              "  SELECT provincia, cantidad AS n FROM parque_automotor"
              "  UNION ALL SELECT provincia, cantidad AS n FROM patentamientos_0km) "
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
    return _modelos_contra_el_catalogo("parque", provincia, limite)


def cero_km_contra_el_catalogo(provincia=None, limite=40):
    """Los 0 km más patentados (de la provincia, o de todo el país), con cuántos productos del
    catálogo los nombran. [] si todavía no se bajaron."""
    return _modelos_contra_el_catalogo("0km", provincia, limite)


def _modelos_contra_el_catalogo(clave, provincia, limite):
    _dataset, tabla, _config = CONTEOS_DEL_DNRPA[clave]
    filtro, params = ("WHERE provincia = ?", [provincia]) if provincia else ("", [])
    c.execute(f"""SELECT marca, modelo, SUM(cantidad) AS n,
                         MIN(anio) AS desde, MAX(anio) AS hasta
                  FROM {tabla} {filtro}
                  GROUP BY marca, modelo ORDER BY n DESC LIMIT ?""", params + [limite])
    filas = filas_a_listas(c)
    if not filas:
        return []
    # Recorrer el catálogo cuesta casi 2 s: se recuerda mientras no cambien ni el catálogo ni
    # los modelos de la tabla. Del proceso (ver del_proceso()): lo comparten todas las sesiones.
    _memoria = del_proceso("autos_contra_el_catalogo", dict)
    _clave = (tuple((f["marca"], f["modelo"]) for f in filas), version_del_catalogo())
    if _clave not in _memoria:
        if len(_memoria) > 8:
            _memoria.clear()
        _memoria[_clave] = _cuantos_productos_nombran([(f["marca"], f["modelo"]) for f in filas])
    productos = _memoria[_clave]
    total = c.execute(f"SELECT SUM(cantidad) FROM {tabla} {filtro}", params).fetchone()[0] or 1
    # «Poco cargado» es contra los demás de la tabla, no un número fijo: la mediana de los
    # modelos más comunes. Con el catálogo real: Etios 91, Up 139 y Cronos 143 productos,
    # contra más de mil del Gol, el Palio, el Clio o el Fiesta.
    _cuantos = sorted(productos.get((f["marca"], f["modelo"]), 0) for f in filas)
    umbral = _cuantos[len(_cuantos) // 2] * 0.25
    salida = []
    for f in filas:
        n_prod = productos.get((f["marca"], f["modelo"]), 0)
        fila = {"Marca": f["marca"], "Modelo": f["modelo"]}
        if clave == "parque":
            fila.update({"Se transfirieron": f["n"],
                         "Del parque": f"{miles(f['n'] / total * 100, 1)}%",
                         "Años": (f"{f['desde']}–{f['hasta']}" if f["desde"] and f["hasta"]
                                  else "—")})
        else:
            fila.update({"Se patentaron": f["n"],
                         "De los 0 km": f"{miles(f['n'] / total * 100, 1)}%"})
        fila.update({"Productos que lo nombran": n_prod,
                     "": "⚠️ poco cargado" if n_prod < umbral else "",
                     "_n": f["n"], "_prod": n_prod})
        salida.append(fila)
    return salida


def marca_del_modelo(modelo):
    """La marca de un modelo escrito solo («Gol Trend» → «VOLKSWAGEN»), o None si no se puede
    saber sin adivinar. Para las fichas que tienen el modelo y no la marca: sin marca,
    «Repuestos por auto» no buscaba nada en el catálogo.

    Primero el registro automotor (los autos que de verdad existen con ese nombre); si todavía
    no se bajó, las descripciones del catálogo (en el pedazo de qué marca aparece el modelo).
    En los dos casos hace falta que una marca se lleve casi todo: «KA» es Ford, pero «C3» o
    «500» se usan para varias cosas y ahí se prefiere no decir nada."""
    palabra = palabra_del_modelo(modelo)
    if len(palabra) < 2 or palabra.isdigit():
        return None
    c.execute("""SELECT marca, SUM(cantidad) AS n FROM (
                     SELECT marca, modelo, cantidad FROM parque_automotor
                     UNION ALL SELECT marca, modelo, cantidad FROM patentamientos_0km)
                 WHERE modelo = ? GROUP BY marca ORDER BY n DESC""", (palabra,))
    del_registro = [(r["marca"], r["n"]) for r in c.fetchall()]
    if del_registro:
        return _la_que_se_lleva_casi_todo(del_registro, minimo=20)
    _memoria = del_proceso("marca_del_modelo", dict)
    _clave = (palabra, version_del_catalogo())
    if _clave not in _memoria:
        if len(_memoria) > 500:
            _memoria.clear()
        _patron = re.compile(r"(?<![A-Z0-9])" + re.escape(palabra) + r"(?![A-Z0-9])")
        cuenta = collections.Counter()
        _cond, _par = like_en_descripcion(f"%{palabra}%")
        c.execute(f"SELECT DISTINCT descripcion FROM productos p WHERE {_cond} LIMIT 5000", _par)
        for (desc,) in c.fetchall():
            for m, _cat, resto in marcas_vehiculo_en(desc):
                if _patron.search(normalizar_texto(separar_texto_pegado(resto or ""))):
                    cuenta[ALIAS_MARCA_VEHICULO.get(m.upper(), m.upper())] += 1
        _memoria[_clave] = _la_que_se_lleva_casi_todo(cuenta.most_common(), minimo=10)
    return _memoria[_clave]


def _la_que_se_lleva_casi_todo(conteos, minimo, parte=0.9):
    """La primera de [(marca, cantidad)] si tiene al menos `parte` del total y `minimo`."""
    total = sum(n for _m, n in conteos)
    if not conteos or conteos[0][1] < minimo or conteos[0][1] < parte * total:
        return None
    return conteos[0][0]

"""La base de datos: conexión, esquema, migraciones y el «todo o nada».

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================
# CONEXIÓN Y ESQUEMA
# ============================================================
ARCHIVO_SEMILLA = "datos_iniciales.db"
# LA COPIA DEL REPOSITORIO VA COMPRIMIDA. GitHub no acepta archivos de más de 100 MB, y la copia
# sin fotos de la base real ya pesa 60,6 MB —80,8 MB en el viaje, porque la API la manda en
# base64—: dos o tres listas más y la copia de seguridad deja de subirse justo cuando más hay
# para proteger. Comprimida pesa 11,2 MB. Se sigue leyendo la de siempre, sin comprimir, si es
# la única que hay; si están las dos, manda la comprimida, que es la que sube la app.
ARCHIVO_SEMILLA_COMPRIMIDA = ARCHIVO_SEMILLA + ".gz"
_SEMILLA_DESCOMPRIMIDA = "datos_iniciales_desde_gz.db"


def semilla_del_repositorio():
    """El archivo de copia que está en el repositorio (el comprimido si está), o None. Es el
    que tiene la fecha y el peso que importan; para ABRIRLO, ver ruta_de_la_semilla()."""
    for ruta in (ARCHIVO_SEMILLA_COMPRIMIDA, ARCHIVO_SEMILLA):
        if os.path.exists(ruta):
            return ruta
    return None


def ruta_de_la_semilla():
    """La copia del repositorio lista para abrir con sqlite, o None.

    Si la del repositorio está comprimida se descomprime al lado —una vez, y de nuevo solo si
    la comprimida es más nueva— escribiendo a un temporal y renombrando: un arranque que se
    corta a mitad de camino no puede dejar una base a medio escribir con el nombre bueno."""
    repo = semilla_del_repositorio()
    if repo != ARCHIVO_SEMILLA_COMPRIMIDA:
        return repo
    temporal = f"{_SEMILLA_DESCOMPRIMIDA}.{uuid.uuid4().hex}.tmp"
    try:
        if (not os.path.exists(_SEMILLA_DESCOMPRIMIDA)
                or os.path.getmtime(_SEMILLA_DESCOMPRIMIDA) < os.path.getmtime(repo)):
            with gzip.open(repo, "rb") as entrada, open(temporal, "wb") as salida:
                shutil.copyfileobj(entrada, salida)
            os.replace(temporal, _SEMILLA_DESCOMPRIMIDA)
        return _SEMILLA_DESCOMPRIMIDA
    except (OSError, EOFError, gzip.BadGzipFile) as _err:
        anotar_error("ruta_de_la_semilla", _err)
        try:
            os.remove(temporal)       # el que quedó a medio escribir
        except OSError:
            pass
        return ARCHIVO_SEMILLA if os.path.exists(ARCHIVO_SEMILLA) else None


# SQLite tiene un tope de variables por consulta: las compilaciones modernas aceptan 32.766,
# pero las viejas —y las que trae más de un hosting— cortan en 999. Se usa el número chico
# porque el costo de equivocarse es que la consulta falle entera en el servidor y no acá.
TOPE_VARIABLES_POR_CONSULTA = 900


def en_tandas(valores, usos_por_consulta=1, tope=TOPE_VARIABLES_POR_CONSULTA):
    """Parte una lista en pedazos que entren en UNA consulta, y devuelve (tanda, marcadores).

    Está en un solo lugar porque el mismo cálculo estaba escrito a mano en varias funciones,
    con tamaños distintos —una iba de a 500, otra de a 800— y eso es justo lo que se
    desincroniza con el tiempo.

    'usos_por_consulta' es cuántas VECES aparece la lista en la consulta, y es el detalle que
    a mano se olvida: si el mismo IN va dos veces —«... IN (…) OR … IN (…)»— cada valor gasta
    dos variables, así que en una tanda entran la mitad. Con 400 resultados y la lista repetida
    eran 803 variables contra un tope de 999: andaba, pero sin margen, y subir el tope de
    resultados de la búsqueda lo habría roto sin que nadie viera la relación.

        for tanda, marcadores in en_tandas(ids, usos_por_consulta=2):
            c.execute(f"... WHERE a IN ({marcadores}) OR b IN ({marcadores})", tanda + tanda)
    """
    valores = list(valores)
    por_tanda = max(1, tope // max(1, int(usos_por_consulta)))
    for inicio in range(0, len(valores), por_tanda):
        tanda = valores[inicio:inicio + por_tanda]
        yield tanda, ",".join("?" * len(tanda))


# CUIDADO AL AGREGAR LETRAS ACÁ: hay un techo y es duro. Cada par es un REPLACE() anidado
# adentro del anterior, y SQLite tiene un límite de anidamiento — medido en 3.45: **rompe a los
# 31** con «parser stack overflow». Y no son 31 libres: la consulta que envuelve la expresión
# gasta del mismo presupuesto, así que una expresión que anda suelta puede reventar adentro de
# un SELECT más grande. Está probado: con 28 pares anda sola y falla dentro de un COUNT().
# Por eso el tope propio es 20, con diez de margen, y auditar.py lo controla: pasarse rompe la
# búsqueda entera de la app en tiempo de ejecución, que es la peor forma de enterarse.
MAXIMO_REEMPLAZOS_SIN_ACENTOS = 20

# Las letras van elegidas por lo que aparece DE VERDAD en las listas cargadas, no por
# completitud: sobre el catálogo real había 80 productos con una letra que el SQL no
# normalizaba y Python sí —«SENSOR RPM cigüeñal», «CITROËN», «Conexão», «PÒINTER»—, y esos 80
# no se encontraban buscando CIGUENAL o CITROEN. Con estas cuatro se cubren 73.
_REEMPLAZOS_SIN_ACENTOS = [
    ("á", "A"), ("Á", "A"), ("é", "E"), ("É", "E"), ("í", "I"), ("Í", "I"),
    ("ó", "O"), ("Ó", "O"), ("ú", "U"), ("Ú", "U"), ("ñ", "N"), ("Ñ", "N"),
    ("ü", "U"), ("Ü", "U"),        # cigüeñal, el más caro de los que faltaban
    ("ê", "E"), ("Ê", "E"),        # listas brasileñas
    ("ë", "E"), ("Ë", "E"),        # CITROËN
    ("â", "A"), ("Â", "A"),        # Ângulo, en las listas brasileñas
]


def _sql_sin_acentos(columna):
    """Arma una expresión SQL que le saca los acentos a una columna (funciona con mayúscula
    y minúscula, porque SQLite no toca letras acentuadas al hacer UPPER()).

    Tiene que decir lo mismo que normalizar_texto() del lado de Python. Cuando no coinciden, el
    que busca escribe una cosa, la columna guardó otra, y el producto no aparece."""
    expr = f"UPPER({columna})"
    for viejo, nuevo in _REEMPLAZOS_SIN_ACENTOS:
        expr = f"REPLACE({expr},'{viejo}','{nuevo}')"
    return expr


def like_en_descripcion(patron, alias="p"):
    """Buscar un texto DENTRO de la descripción, rápido. Devuelve (condición, parámetros).

    Sacarle los acentos a la descripción en la consulta cuesta doce REPLACE() anidados POR
    FILA. Sobre el catálogo real son 170 ms cada vez, y hay pantallas que lo hacen cuatro o
    cinco veces seguidas: de ahí salían los 215 ms que tardaba en contestar un código de falla.

    La columna `productos.busqueda` ya tiene el texto normalizado y la mantienen los triggers,
    pero NO sirve sola: además de la descripción trae el código y el código de barras, así que
    buscar «FIAT» ahí también engancha un código que lo tenga adentro. Usarla de reemplazo
    cambiaría lo que la consulta significa.

    Por eso va de PREFILTRO y la condición exacta queda como confirmación: la columna barata
    descarta el 99% de las filas y los REPLACE corren solo sobre las pocas que pasaron. Medido
    sobre las 70.888 del catálogo real, con siete búsquedas distintas: 1.184 ms → 150 ms, y
    devuelve exactamente las mismas filas (se comparó fila por fila, no solo el total).

    El `IS NULL` del prefiltro no debería hacer falta —hay un relleno de una sola vez en
    crear_esquema() y triggers que la mantienen— pero sin él, una fila con la columna vacía
    desaparecería de los resultados sin ningún error a la vista, que es la peor forma de
    equivocarse."""
    condicion = (f"({alias}.busqueda IS NULL OR {alias}.busqueda LIKE ?) "
                 f"AND {_sql_sin_acentos(alias + '.descripcion')} LIKE ?")
    return condicion, [patron, patron]


# LA COPIA AUTOMÁTICA VA A UNA RAMA PROPIA, con un solo commit que se reemplaza cada vez.
# Antes iba a `main`, un commit nuevo por copia. Con 11 MB comprimidos por copia eso son 4 GB por
# año en el historial del repositorio si se sube una vez por día —y la idea ahora es subirla
# cada vez que hay cambios—: GitHub recomienda no pasar de 1 GB, y Streamlit clona el repositorio
# entero en cada arranque. Además cada copia en `main` es un commit que el que sube código tiene
# que traerse antes de poder subir el suyo. En su rama, reemplazada, pesa siempre una copia sola,
# y el código no se entera. Como Streamlit clona solo `main`, al arrancar la app la baja de ahí:
# ver bajar_la_copia_de_github(). Si en los secretos se pone otra rama (`github_rama`), se sube
# a esa como antes, con un commit por copia: a `main` no se le puede reemplazar el historial.
RAMA_DE_LA_COPIA = "copia-de-seguridad"
# Solo para probar: permite apuntar la app a un GitHub de mentira y ver la copia ir y volver
# sin tocar el de verdad. En el servidor no se define y es el de siempre.
API_DE_GITHUB = os.environ.get("EQUIVALENCIAS_API_DE_GITHUB", "https://api.github.com")
ARCHIVO_COPIA_BAJADA = "datos_desde_github.db"


def config_github():
    """Los datos para subir el backup solo. Devuelve None si no están configurados."""
    try:
        secretos = secretos_app()
        token = secretos.get("github_token")
        repo = secretos.get("github_repo")      # formato: "usuario/repositorio"
        if not token or not repo:
            # Pegadas al final de los secretos quedan ADENTRO de la última sección: en TOML,
            # todo lo que viene después de «[operador_passwords]» es de esa sección, y
            # arriba de todo no aparecen. Es lo primero que pasa al seguir «agregá estas dos
            # líneas», y la copia no subía sin ningún error a la vista. Se buscan también
            # adentro de cada sección.
            for _valor in list(secretos.values()):
                if hasattr(_valor, "get") and _valor.get("github_token") and _valor.get("github_repo"):
                    secretos = _valor
                    token, repo = _valor.get("github_token"), _valor.get("github_repo")
                    break
    except Exception as _err:
        anotar_error("config_github", _err)
        return None
    if not token or not repo or "/" not in str(repo):
        return None
    return {"token": str(token), "repo": str(repo),
            "rama": str(secretos.get("github_rama", RAMA_DE_LA_COPIA)),
            "archivo": str(secretos.get("github_archivo", ARCHIVO_SEMILLA_COMPRIMIDA))}


def bajar_la_copia_de_github():
    """Baja la última copia de la rama de copias y la deja lista para abrir. Devuelve la ruta,
    o None si no hay copia, no está configurado o algo falla: en ese caso se sigue con la del
    repositorio, si hay, como siempre.

    Se valida antes de usarla —que abra y tenga productos—, y se escribe a un temporal que se
    renombra al final: una bajada cortada no puede quedar con el nombre bueno."""
    cfg = config_github()
    if not cfg or cfg["rama"] != RAMA_DE_LA_COPIA:
        return None
    url = f"{API_DE_GITHUB}/repos/{cfg['repo']}/contents/{cfg['archivo']}"
    cabeceras = {"Authorization": f"Bearer {cfg['token']}",
                 # «raw» trae el archivo tal cual, hasta 100 MB; el de siempre corta en 1 MB
                 "Accept": "application/vnd.github.raw"}
    bajado = f"{ARCHIVO_COPIA_BAJADA}.{uuid.uuid4().hex}.bajando"
    abierto = f"{ARCHIVO_COPIA_BAJADA}.{uuid.uuid4().hex}.tmp"
    try:
        # Diez segundos para conectar: esto corre al arrancar, y con GitHub caído la app no
        # puede quedarse colgada esperándolo. Sin copia bajada sigue con la del repositorio.
        with requests.get(url, headers=cabeceras, params={"ref": cfg["rama"]},
                          timeout=(10, 60), stream=True) as r:
            if r.status_code != 200:
                if r.status_code != 404:       # 404 = todavía no se subió ninguna
                    anotar_error("bajar_la_copia_de_github", f"GitHub respondió {r.status_code}")
                return None
            with open(bajado, "wb") as salida:
                for pedazo in r.iter_content(1 << 20):
                    salida.write(pedazo)
        if cfg["archivo"].endswith(".gz"):
            with gzip.open(bajado, "rb") as entrada, open(abierto, "wb") as salida:
                shutil.copyfileobj(entrada, salida)
        else:
            os.replace(bajado, abierto)
        # immutable: solo mirar, sin los archivos de al lado que SQLite crea para una base en
        # modo WAL (si no, quedaban sueltos con el nombre del temporal).
        prueba = sqlite3.connect(f"file:{abierto}?mode=ro&immutable=1", uri=True)
        try:
            if not prueba.execute("SELECT COUNT(*) FROM productos").fetchone()[0]:
                return None
        finally:
            prueba.close()
        os.replace(abierto, ARCHIVO_COPIA_BAJADA)
        return ARCHIVO_COPIA_BAJADA
    except Exception as _err:
        anotar_error("bajar_la_copia_de_github", _err)
        return None
    finally:
        for sobra in (bajado, abierto):
            try:
                os.remove(sobra)
            except OSError:
                pass


def _restaurar_desde_semilla(conexion):
    """Streamlit Cloud borra el disco de la app cada vez que se redespliega o se reinicia, así
    que la base de datos se pierde. Los archivos del REPOSITORIO, en cambio, sí sobreviven
    (son parte del despliegue). Entonces: si la base está vacía y en el repositorio hay una
    copia llamada 'datos_iniciales.db', se restaura sola al arrancar.
    Para actualizar esa copia: bajar el backup desde Estadísticas → Backup y config, y subir
    ese archivo al repositorio de GitHub con el nombre 'datos_iniciales.db'. Si está
    configurada la subida automática, la app la sube sola cada vez que hay cambios a la rama
    copia-de-seguridad, y la baja de ahí al arrancar: ver vigilar_la_copia() y
    bajar_la_copia_de_github()."""
    try:
        cur = conexion.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='productos'")
        if cur.fetchone():
            cur.execute("SELECT COUNT(*) FROM productos")
            if cur.fetchone()[0] > 0:
                return False  # ya hay datos cargados: no se toca nada
        # La de la rama de copias primero: la sube la app sola cada vez que hay cambios, así
        # que es la más nueva. Se pregunta recién acá, con la base vacía, para no bajar 11 MB
        # en cada arranque que no los necesita.
        semilla = bajar_la_copia_de_github() or ruta_de_la_semilla()
        if not semilla:
            return False
        origen = sqlite3.connect(semilla)
        origen.backup(conexion)
        origen.close()
        return True
    except Exception as _err:
        anotar_error("_restaurar_desde_semilla", _err)
        return False


def _esquema_catalogo(c):
    """El corazón: marcas, productos, los vínculos entre ellos y el stock apartado.

    Se llama desde crear_esquema(), en orden: cada parte da por hecho que las anteriores ya
    corrieron."""
    c.execute("""CREATE TABLE IF NOT EXISTS marcas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE NOT NULL,
        tipo TEXT NOT NULL DEFAULT 'PROVEEDOR',
        url_ficha_template TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    columnas_marcas = [f[1] for f in c.execute("PRAGMA table_info(marcas)").fetchall()]
    if "url_ficha_template" not in columnas_marcas:
        c.execute("ALTER TABLE marcas ADD COLUMN url_ficha_template TEXT")

    c.execute("""CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_raw TEXT NOT NULL,
        codigo_clean TEXT NOT NULL,
        descripcion TEXT,
        marca_id INTEGER NOT NULL REFERENCES marcas(id) ON DELETE CASCADE,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(codigo_clean, marca_id)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS equivalencias (
        producto_a_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
        producto_b_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
        created_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (producto_a_id, producto_b_id)
    )""")

    # Qué repuesto le va a cada auto, según el catálogo del fabricante del repuesto.
    # Stock apartado al cotizar. Con varios atendiendo a la vez, vender dos veces la misma
    # pieza es cuestión de tiempo: uno cotiza 4 pastillas, el otro ve stock 4 y las vende.
    c.execute("""CREATE TABLE IF NOT EXISTS reservas_stock (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
        cantidad INTEGER NOT NULL,
        cliente TEXT,
        nota TEXT,
        reservado_por TEXT,
        estado TEXT DEFAULT 'activa',
        fecha TEXT DEFAULT (datetime('now'))
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_reservas_prod ON reservas_stock(producto_id, estado)")


def _esquema_mostrador(c):
    """Lo que pasa en el mostrador: consultas de clientes, aplicaciones por vehículo,
    importaciones, catálogos de proveedor y el historial de búsquedas.

    Se llama desde crear_esquema(), en orden: cada parte da por hecho que las anteriores ya
    corrieron."""
    c.execute("""CREATE TABLE IF NOT EXISTS consultas_cliente (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente TEXT,
        telefono TEXT,
        producto_id INTEGER REFERENCES productos(id) ON DELETE SET NULL,
        codigo_buscado TEXT,
        descripcion TEXT,
        cantidad INTEGER DEFAULT 1,
        precio_dicho REAL,
        nota TEXT,
        estado TEXT DEFAULT 'activa',
        atendio TEXT,
        fecha TEXT DEFAULT (datetime('now')),
        fecha_cierre TEXT
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_consultas_estado ON consultas_cliente(estado)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_consultas_tel ON consultas_cliente(telefono)")


    # QUÉ MOTORES SE LLEVAN ENTRE SÍ, PARA CADA TIPO DE PIEZA. No sale de ningún catálogo
    # técnico: sale de que un proveedor venda UN producto y en su descripción nombre varios
    # motores. Eso es el proveedor diciendo «esta pieza entra en los dos». Ver
    # aprender_motores_que_van_juntos().
    c.execute("""CREATE TABLE IF NOT EXISTS motores_compatibles (
        motor_a TEXT NOT NULL,
        motor_b TEXT NOT NULL,
        tipo_pieza TEXT NOT NULL DEFAULT '',
        veces INTEGER DEFAULT 1,
        PRIMARY KEY (motor_a, motor_b, tipo_pieza)
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_motores_compat "
              "ON motores_compatibles(tipo_pieza, motor_a, motor_b)")

    c.execute("""CREATE TABLE IF NOT EXISTS aplicaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        marca_auto TEXT NOT NULL,
        modelo_auto TEXT NOT NULL,
        motor TEXT,
        combustible TEXT,
        anio_desde INTEGER,
        anio_hasta INTEGER,
        codigo TEXT NOT NULL,
        codigo_clean TEXT,
        marca_repuesto TEXT,
        tipo_pieza TEXT,
        origen TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE (marca_auto, modelo_auto, motor, anio_desde, anio_hasta, codigo)
    )""")
    _cols_aplic = [f[1] for f in c.execute("PRAGMA table_info(aplicaciones)").fetchall()]
    if "tipo_pieza" not in _cols_aplic:
        c.execute("ALTER TABLE aplicaciones ADD COLUMN tipo_pieza TEXT")
    c.execute("CREATE INDEX IF NOT EXISTS idx_aplic_auto ON aplicaciones(marca_auto, modelo_auto)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_aplic_codigo ON aplicaciones(codigo_clean)")

    c.execute("""CREATE TABLE IF NOT EXISTS importaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        marca TEXT,
        archivo TEXT,
        filas_cargadas INTEGER,
        filas_omitidas INTEGER,
        fecha TEXT DEFAULT (datetime('now'))
    )""")
    # Huella del archivo importado, para reconocer la MISMA planilla aunque le hayan cambiado el
    # nombre. Reimportar la misma lista sin darse cuenta duplica el trabajo de revisión y puede
    # revivir precios viejos encima de los actualizados a mano.
    _cols_imp = [f[1] for f in c.execute("PRAGMA table_info(importaciones)").fetchall()]
    if "huella" not in _cols_imp:
        c.execute("ALTER TABLE importaciones ADD COLUMN huella TEXT")
    if "lote" not in _cols_imp:
        c.execute("ALTER TABLE importaciones ADD COLUMN lote TEXT")
    c.execute("CREATE INDEX IF NOT EXISTS idx_importaciones_huella ON importaciones(huella)")

    c.execute("""CREATE TABLE IF NOT EXISTS catalogos_externos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE NOT NULL,
        url TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS historial_busquedas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        termino TEXT NOT NULL,
        usuario TEXT,
        fecha TEXT DEFAULT (datetime('now'))
    )""")
    columnas_historial = [f[1] for f in c.execute("PRAGMA table_info(historial_busquedas)").fetchall()]
    if "usuario" not in columnas_historial:
        c.execute("ALTER TABLE historial_busquedas ADD COLUMN usuario TEXT")

    # Migraciones: agregar columnas nuevas si no existen todavía
    columnas_productos = [f[1] for f in c.execute("PRAGMA table_info(productos)").fetchall()]
    if "precio" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN precio REAL")
    if "stock" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN stock INTEGER")
    if "favorito" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN favorito INTEGER DEFAULT 0")
    if "imagen_url" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN imagen_url TEXT")
    if "imagen_orb_blob" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN imagen_orb_blob BLOB")
    # Estado del procesamiento visual de la foto: NULL = sin intentar, 'ok' = tiene descriptores,
    # 'sin_detalle' = se intentó y la foto no da (pieza lisa, borrosa), 'error' = falló el proceso.
    # Sin esto, una foto que no sirve quedaba "pendiente" para siempre: el botón de procesar
    # mostraba pendientes, se tocaba, no cambiaba nada, y volvía a mostrar lo mismo.
    if "imagen_orb_estado" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN imagen_orb_estado TEXT")
    # Recuerda que a ese código ya se le buscó foto en la ficha del proveedor y no había. Sin
    # esto, cada tanda volvía a golpear los mismos miles de códigos sin foto y nunca avanzaba.
    if "foto_busqueda_estado" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN foto_busqueda_estado TEXT")
    # Lo mismo pero para las EQUIVALENCIAS que publica la ficha del proveedor. Es la marca que
    # hace posible avanzar de a tandas: sin ella, cada tanda vuelve a leer las mismas primeras
    # fichas —la consulta ordena por stock y corta— y no llega nunca al resto del catálogo.
    # Guarda la fecha en que se consultó, no un sí/no, para poder volver a pasar dentro de unos
    # meses: una ficha puede publicar equivalencias nuevas.
    if "ficha_equiv_leida" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN ficha_equiv_leida TEXT")

    # Descripción y código ya pasados a mayúscula y sin acentos, guardados. Es solo velocidad,
    # pero de la que se nota: la búsqueda por texto le sacaba los acentos a cada fila EN EL
    # MOMENTO, con doce REPLACE() anidados por columna y por palabra. Sobre 44.000 productos
    # eso daba 1 segundo por búsqueda, y sobre 110.000 pasa de tres. Con la columna ya
    # calculada la misma búsqueda tarda 40 ms: veinticuatro veces menos.
    # Se mantiene con TRIGGERS y no desde el código a propósito. Hay más de veinte lugares que
    # insertan o cambian productos —importación, alta a mano, restaurar backup, despegar
    # descripciones, fusionar marcas— y alcanza con que uno se olvide para que esos productos
    # dejen de aparecer en las búsquedas por descripción, sin ningún error a la vista. El
    # trigger no se lo puede olvidar nadie.
    # EL CÓDIGO DE BARRAS, en su propia columna y no como si fuera un código de fábrica.
    # Antes no tenía dónde ir, así que la lista que lo traía lo cargaba en la columna de OEM.
    # Eso lo hacía buscable —que era la idea— pero al precio de inventar una equivalencia por
    # cada producto: el EAN es de ese proveedor y de nadie más, así que el vínculo no lleva a
    # ningún lado. En la base real son 8.076 códigos de barras haciendo de código de fábrica y
    # 8.652 productos con una equivalencia que no sirve para nada.
    # Con columna propia se consiguen las dos cosas: escanear la caja encuentra el repuesto, y
    # la red de equivalencias queda solo con códigos que de verdad comparten dos proveedores.
    if "codigo_barras" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN codigo_barras TEXT")
    c.execute("CREATE INDEX IF NOT EXISTS idx_codigo_barras ON productos(codigo_barras)")

    if "busqueda" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN busqueda TEXT")
    _expr_busqueda = (_sql_sin_acentos("COALESCE(descripcion,'') || ' ' || COALESCE(codigo_raw,'')"
                                        " || ' ' || COALESCE(codigo_barras,'')")
                      .replace("descripcion", "NEW.descripcion").replace("codigo_raw", "NEW.codigo_raw")
                      .replace("codigo_barras", "NEW.codigo_barras"))
    # Se borran y se vuelven a crear en vez de usar solo IF NOT EXISTS: la expresión cambió al
    # sumarle el código de barras, y con IF NOT EXISTS una base ya creada se quedaba para
    # siempre con la versión vieja del trigger, sin ningún error a la vista.
    c.execute("DROP TRIGGER IF EXISTS productos_busqueda_alta")
    c.execute("DROP TRIGGER IF EXISTS productos_busqueda_cambio")
    c.execute("""CREATE TRIGGER productos_busqueda_alta
                 AFTER INSERT ON productos BEGIN
                   UPDATE productos SET busqueda = """ + _expr_busqueda + """ WHERE id = NEW.id;
                 END""")
    # El "OF descripcion, codigo_raw" no es solo eficiencia: sin él, el UPDATE que hace el
    # propio trigger volvería a dispararlo. Al nombrar las columnas, escribir 'busqueda' no
    # cuenta como cambio y el trigger no se llama a sí mismo.
    c.execute("""CREATE TRIGGER productos_busqueda_cambio
                 AFTER UPDATE OF descripcion, codigo_raw, codigo_barras ON productos BEGIN
                   UPDATE productos SET busqueda = """ + _expr_busqueda + """ WHERE id = NEW.id;
                 END""")
    # Los productos que ya estaban cargados antes de que existiera esta columna.
    # OJO: acá va SOLO el caso «nunca se calculó». Volver a calcularla porque cambió la
    # normalización se hace en _datos_precargados_y_migraciones(), que corre al final: esto
    # pasa antes de que exista la tabla de configuración, y sin ella no hay dónde anotar que
    # ya se hizo, así que se repetiría en cada arranque.
    c.execute("SELECT COUNT(*) FROM productos WHERE busqueda IS NULL")
    if c.fetchone()[0]:
        c.execute("UPDATE productos SET busqueda = " + _expr_busqueda + " WHERE busqueda IS NULL")


def _esquema_fotos(c):
    """Las fotos de cada producto y los datos para compararlas visualmente.

    Se llama desde crear_esquema(), en orden: cada parte da por hecho que las anteriores ya
    corrieron."""
    # Se relee acá en vez de recibirla: cada parte del esquema tiene que poder mirarse sola,
    # y una lista de columnas es una consulta de microsegundos.
    columnas_productos = [f[1] for f in c.execute("PRAGMA table_info(productos)").fetchall()]
    c.execute("""CREATE TABLE IF NOT EXISTS producto_fotos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
        imagen_data TEXT,
        firma_blob BLOB,
        estado TEXT,
        origen TEXT,
        fuente TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_producto_fotos_prod ON producto_fotos(producto_id)")
    # Con qué versión del comparador se calculó cada firma. Cuando el comparador mejora, las
    # firmas viejas quedan sin los datos nuevos y la mejora no se aplica al catálogo que ya
    # tenías cargado — que es justo donde hace falta. Con esto se detectan y se recalculan.
    _cols_fotos = [f[1] for f in c.execute("PRAGMA table_info(producto_fotos)").fetchall()]
    if "firma_version" not in _cols_fotos:
        c.execute("ALTER TABLE producto_fotos ADD COLUMN firma_version INTEGER")
    # Miniatura chica aparte: la foto normal pesa bastante y la búsqueda la traía entera por
    # cada resultado, aunque en la tabla se vea en chiquito. Acá se guarda una versión liviana
    # solo para esas listas; la grande se sigue usando al ver el producto en Administrar.
    if "imagen_thumb" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN imagen_thumb TEXT")
    if "diametro_interno" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN diametro_interno REAL")
    if "diametro_externo" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN diametro_externo REAL")
    if "diametro_interno_cara_b" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN diametro_interno_cara_b REAL")
    if "diametro_externo_cara_b" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN diametro_externo_cara_b REAL")
    if "diametro_rosca_homocinetica" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN diametro_rosca_homocinetica REAL")
    if "diametro_copa" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN diametro_copa REAL")
    # La copa de una homocinética es cónica: mide distinto en la base que en la boca. Con un
    # solo diámetro no alcanzaba para distinguir dos copas que arrancan igual y terminan
    # distinto, y son justo las que no se pueden intercambiar.
    # Precio de costo, aparte del de venta. Con un solo precio no se puede saber el margen, y
    # sin margen la decisión de qué ofrecer entre tres equivalentes se toma a ojo: no siempre
    # conviene el más barato para el cliente.
    if "precio_costo" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN precio_costo REAL")

    if "diametro_copa_superior" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN diametro_copa_superior REAL")
    # El largo total es la medida que primero descarta: dos homocinéticas con las mismas estrías
    # y la misma copa pero distinto largo no entran en el mismo auto.
    if "largo_total" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN largo_total REAL")
    if "ancho" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN ancho REAL")
    if "paso_rosca" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN paso_rosca TEXT")
    if "cantidad_estrias" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN cantidad_estrias INTEGER")
    # QUIÉN FABRICA LA PIEZA, que es otra cosa que quién te la vende. Las 5 marcas de la tabla
    # `marcas` son proveedores —JL, MOTORARG, ILLINOIS, FISPA y el nodo de fábrica—, así que
    # hasta ahora la app no tenía dónde guardar que esa bomba es Bosch y esa otra es Masser. Y
    # es la primera pregunta del mostrador. Ver marca_de_repuesto_en(): sobre las 46.644
    # descripciones de proveedor está escrita en 13.705.
    # DÓNDE VA LA PIEZA: delantera/trasera, izquierda/derecha, superior/inferior. Es de los
    # datos que hacen que dos piezas NO sean intercambiables aunque todo lo demás coincida —el
    # caño superior del radiador no es el inferior— y estaba escrito en miles de descripciones
    # sin que lo leyera nadie. Ver posicion_desde_descripcion().
    if "posicion" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN posicion TEXT")
    # La cantidad de canales de una polea. Va con las medidas exactas, no con tolerancia: una
    # polea de 5 canales y una de 6 no se parecen «un 17%», son dos piezas distintas.
    if "cantidad_canales" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN cantidad_canales INTEGER")
    if "marca_repuesto" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN marca_repuesto TEXT")
        c.execute("CREATE INDEX IF NOT EXISTS idx_marca_repuesto ON productos(marca_repuesto)")
    # El ESPESOR de una junta y la CANTIDAD DE VÍAS de una ficha. Los dos estaban escritos en
    # la descripción de miles de productos y no los leía nadie, y los dos son de los que hacen
    # que dos piezas NO sean intercambiables aunque todo lo demás coincida.
    # Ver medidas_desde_descripcion() para los números.
    if "espesor" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN espesor REAL")
    if "cantidad_vias" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN cantidad_vias INTEGER")
    if "estrias_internas" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN estrias_internas INTEGER")
    if "estrias_externas" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN estrias_externas INTEGER")
    if "posicion_seguro" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN posicion_seguro TEXT")
    if "tiene_abs" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN tiene_abs INTEGER")
    if "ubicacion" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN ubicacion TEXT")
    if "veces_buscado" not in columnas_productos:
        c.execute("ALTER TABLE productos ADD COLUMN veces_buscado INTEGER DEFAULT 0")


def _esquema_vehiculos_y_mecanico(c):
    """La ficha del vehículo y todo el modo mecánico: patentes, historial de piezas,
    códigos de falla OBD-II, decodificación de VIN y los esquemas de despiece.

    Se llama desde crear_esquema(), en orden: cada parte da por hecho que las anteriores ya
    corrieron."""
    c.execute("""CREATE TABLE IF NOT EXISTS vehiculos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patente TEXT UNIQUE NOT NULL,
        cliente_nombre TEXT,
        cliente_telefono TEXT,
        marca_auto TEXT,
        modelo_auto TEXT,
        anio TEXT,
        motorizacion TEXT,
        km_registro INTEGER,
        km_actual INTEGER,
        km_actualizado_fecha TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    columnas_vehiculos_extra = [f[1] for f in c.execute("PRAGMA table_info(vehiculos)").fetchall()]
    # El número de motor grabado en el block. No es lo mismo que la motorización: «1.6 16v» es
    # el tipo de motor, y el número es el de ESE motor en particular.
    #
    # Importa cuando el auto tiene el motor cambiado, que en un taller pasa seguido: el VIN
    # dice una cosa y el motor que tiene puesto es otro. Buscando por el número de motor se
    # encuentra lo que de verdad lleva.
    if "numero_motor" not in columnas_vehiculos_extra:
        c.execute("ALTER TABLE vehiculos ADD COLUMN numero_motor TEXT")
        columnas_vehiculos_extra.append("numero_motor")
    c.execute("""CREATE INDEX IF NOT EXISTS idx_vehiculos_motor
                 ON vehiculos(numero_motor)""")
    if "anio" not in columnas_vehiculos_extra:
        c.execute("ALTER TABLE vehiculos ADD COLUMN anio TEXT")
    if "motorizacion" not in columnas_vehiculos_extra:
        c.execute("ALTER TABLE vehiculos ADD COLUMN motorizacion TEXT")
    # VIN en la ficha: permite entrar por el número de chasis además de por la patente, y hace
    # que el decodificador pueda devolver datos REALES del auto (no estimados) cuando ya pasó
    # por el mostrador. De paso, cada ficha con VIN + modelo le enseña el patrón a la app.
    if "vin" not in columnas_vehiculos_extra:
        c.execute("ALTER TABLE vehiculos ADD COLUMN vin TEXT")
    c.execute("CREATE INDEX IF NOT EXISTS idx_vehiculos_vin ON vehiculos(vin)")

    # Migración: instalaciones existentes que no tenían km_registro (km de cuando se cargó
    # el vehículo por primera vez, fijo, para poder calcular km recorridos).
    columnas_vehiculos = [f[1] for f in c.execute("PRAGMA table_info(vehiculos)").fetchall()]
    if "km_registro" not in columnas_vehiculos:
        c.execute("ALTER TABLE vehiculos ADD COLUMN km_registro INTEGER")
        # Para los vehículos que ya existían, se usa el km_actual que tengan como punto de partida
        # (es lo mejor que se puede hacer sin el dato original; a partir de ahora queda fijo).
        c.execute("UPDATE vehiculos SET km_registro = km_actual WHERE km_registro IS NULL")

    c.execute("""CREATE TABLE IF NOT EXISTS historial_piezas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vehiculo_id INTEGER NOT NULL REFERENCES vehiculos(id) ON DELETE CASCADE,
        producto_id INTEGER REFERENCES productos(id) ON DELETE SET NULL,
        descripcion_pieza TEXT NOT NULL,
        marca_pieza TEXT,
        codigo_pieza TEXT,
        km_instalacion INTEGER,
        fecha_instalacion TEXT DEFAULT (datetime('now')),
        vida_util_km INTEGER,
        nota TEXT
    )""")

    # Auditoría diaria de stock por muestreo aleatorio
    c.execute("""CREATE TABLE IF NOT EXISTS auditoria_diaria (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL,
        producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
        stock_sistema INTEGER,
        stock_contado INTEGER,
        diferencia INTEGER,
        resuelto INTEGER DEFAULT 0,
        UNIQUE(fecha, producto_id)
    )""")

    # ---- Modo Mecánico ----
    # fabricante = '' significa código genérico (estándar OBD-II, válido para cualquier auto).
    # Un mismo código (ej. P1105) puede repetirse con distinto fabricante, porque en los
    # códigos específicos de marca el mismo número significa cosas distintas según el auto.
    c.execute("""CREATE TABLE IF NOT EXISTS codigos_dtc (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT NOT NULL,
        fabricante TEXT NOT NULL DEFAULT '',
        descripcion TEXT NOT NULL,
        sistema TEXT,
        causas_posibles TEXT,
        UNIQUE(codigo, fabricante)
    )""")

    # Migración: las instalaciones que ya tenían la tabla vieja (sin columna fabricante,
    # con UNIQUE solo en codigo) se convierten al esquema nuevo sin perder datos cargados.
    columnas_dtc = [f[1] for f in c.execute("PRAGMA table_info(codigos_dtc)").fetchall()]
    if "fabricante" not in columnas_dtc:
        c.execute("ALTER TABLE codigos_dtc RENAME TO codigos_dtc_old")
        c.execute("""CREATE TABLE codigos_dtc (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL,
            fabricante TEXT NOT NULL DEFAULT '',
            descripcion TEXT NOT NULL,
            sistema TEXT,
            causas_posibles TEXT,
            UNIQUE(codigo, fabricante)
        )""")
        c.execute("""INSERT INTO codigos_dtc (codigo, fabricante, descripcion, sistema, causas_posibles)
                     SELECT codigo, '', descripcion, sistema, causas_posibles FROM codigos_dtc_old""")
        c.execute("DROP TABLE codigos_dtc_old")

    # Marca de «esto lo escribió alguien acá». Sin ella, la semilla del diccionario era de una
    # sola vez para siempre: entraba con INSERT OR IGNORE, así que corregir la descripción de un
    # código ya cargado no llegaba nunca a una base que ya existía. Un P0380 que decía
    # «bujía/circuito calefactor» —y por eso ofrecía bujías de nafta para un diesel— iba a
    # seguir diciendo eso en la base del negocio aunque acá se arreglara. Ahora la semilla
    # corrige los códigos que vinieron con la app, y NO toca los que cargó o editó el usuario.
    if "editado" not in columnas_dtc:
        c.execute("ALTER TABLE codigos_dtc ADD COLUMN editado INTEGER NOT NULL DEFAULT 0")

    c.execute("""CREATE TABLE IF NOT EXISTS fabricantes_vin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wmi TEXT UNIQUE NOT NULL,
        fabricante TEXT NOT NULL,
        pais TEXT
    )""")

    # Modelos por patrón VDS (posiciones 4 a 8 del VIN).
    # A diferencia del WMI, que es un registro internacional y siempre significa lo mismo, las
    # posiciones 4-8 las define CADA fabricante como quiere: no hay forma de deducir el modelo
    # de un VIN sin una base licenciada (TecDoc y similares, que son pagas). Lo que sí se puede
    # es que la app APRENDA: la primera vez lo cargás vos, y de ahí en más todo VIN con el mismo
    # patrón se autocompleta solo. Con el tiempo cubre los autos que realmente atendés.
    c.execute("""CREATE TABLE IF NOT EXISTS modelos_vin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wmi TEXT NOT NULL,
        vds TEXT NOT NULL,
        modelo TEXT NOT NULL,
        notas TEXT,
        veces INTEGER DEFAULT 1,
        UNIQUE (wmi, vds)
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_modelos_vin ON modelos_vin(wmi, vds)")
    _cols_modelos_vin = [f[1] for f in c.execute("PRAGMA table_info(modelos_vin)").fetchall()]
    if "motor" not in _cols_modelos_vin:
        c.execute("ALTER TABLE modelos_vin ADD COLUMN motor TEXT")

    # El motor por la 8ª posición del VIN.
    # En los VIN de Norteamérica esa posición es, POR NORMA, el código de motor. Fuera de
    # Norteamérica no hay norma, pero casi todos los fabricantes la usan igual para eso.
    # Se guarda aparte del modelo porque generaliza distinto: un mismo código de motor aparece
    # en varios modelos de la misma marca, así que aprendido una vez sirve para todos.
    c.execute("""CREATE TABLE IF NOT EXISTS motores_vin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wmi TEXT NOT NULL,
        codigo TEXT NOT NULL,
        motor TEXT NOT NULL,
        notas TEXT,
        veces INTEGER DEFAULT 1,
        UNIQUE (wmi, codigo)
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_motores_vin ON motores_vin(wmi, codigo)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_motores_vin_cod ON motores_vin(codigo)")

    c.execute("""CREATE TABLE IF NOT EXISTS esquemas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL,
        marca_auto TEXT,
        modelo_auto TEXT,
        sistema TEXT,
        descripcion TEXT,
        imagen_blob BLOB,
        imagen_nombre TEXT,
        generado_ia INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_esquemas_marca ON esquemas(marca_auto)")
    columnas_esquemas = [f[1] for f in c.execute("PRAGMA table_info(esquemas)").fetchall()]
    if "generado_ia" not in columnas_esquemas:
        c.execute("ALTER TABLE esquemas ADD COLUMN generado_ia INTEGER DEFAULT 0")

    # Catálogo de marca/vehículo para "Explorar por categoría", separado de los esquemas en sí:
    # permite precargar la estructura (Volkswagen > Gol Trend) sin necesidad de subir ya una imagen.
    c.execute("""CREATE TABLE IF NOT EXISTS esquemas_catalogo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        marca TEXT NOT NULL,
        modelo TEXT NOT NULL,
        UNIQUE(marca, modelo)
    )""")

    # Piezas marcadas dentro de un esquema (número/nombre + código), para poder buscarlas
    # directamente en el catálogo desde el diagrama — es lo que le da función de "despiece".
    c.execute("""CREATE TABLE IF NOT EXISTS esquema_puntos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        esquema_id INTEGER NOT NULL REFERENCES esquemas(id) ON DELETE CASCADE,
        numero TEXT,
        nombre_pieza TEXT NOT NULL,
        codigo TEXT,
        producto_id INTEGER REFERENCES productos(id) ON DELETE SET NULL,
        pos_x REAL,
        pos_y REAL,
        orden INTEGER DEFAULT 0
    )""")


def _esquema_gestion(c):
    """Administración del negocio: usuarios, papelera, configuración, precios, ventas,
    presupuestos, y las tablas de revisión de equivalencias.

    Se llama desde crear_esquema(), en orden: cada parte da por hecho que las anteriores ya
    corrieron."""
    c.execute("""CREATE TABLE IF NOT EXISTS alias_transferencia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        alias TEXT,
        cbu TEXT,
        titular TEXT,
        qr_real_blob BLOB
    )""")
    columnas_alias = [f[1] for f in c.execute("PRAGMA table_info(alias_transferencia)").fetchall()]
    if "qr_real_blob" not in columnas_alias:
        c.execute("ALTER TABLE alias_transferencia ADD COLUMN qr_real_blob BLOB")

    # Configuración simple de clave/valor (ej: encabezado/pie del mensaje de WhatsApp).
    c.execute("""CREATE TABLE IF NOT EXISTS configuracion (
        clave TEXT PRIMARY KEY,
        valor TEXT
    )""")

    # Contador de uso de las funciones de IA — para ver de un vistazo cuánto se usa cada una
    # y anticipar si alguna se está acercando a los límites gratuitos.
    c.execute("""CREATE TABLE IF NOT EXISTS uso_ia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        funcion TEXT NOT NULL,
        usuario TEXT,
        exito INTEGER,
        fecha TEXT DEFAULT (datetime('now'))
    )""")

    # Papelera: guarda una copia de lo que se borra (marcas, productos, combos, alias) para
    # poder restaurarlo si fue un error. No reemplaza el backup completo, es para el día a día.
    c.execute("""CREATE TABLE IF NOT EXISTS papelera (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT NOT NULL,
        datos_json TEXT NOT NULL,
        eliminado_por TEXT,
        eliminado_en TEXT DEFAULT (datetime('now'))
    )""")
    # Una línea que describe lo borrado, para poder listar la papelera sin abrir el JSON
    # entero — que en una marca grande son 10,6 MB por fila. Ver mover_a_papelera().
    if "resumen" not in [f[1] for f in c.execute("PRAGMA table_info(papelera)").fetchall()]:
        c.execute("ALTER TABLE papelera ADD COLUMN resumen TEXT")

    # Cuando un empleado busca algo y no hay stock (o le falta), lo marca acá para que el dueño
    # lo revise después y decida qué pedirle a cada proveedor. Un mismo producto pedido varias
    # veces por distintos empleados suma en "veces_solicitado" en vez de duplicar filas.
    c.execute("""CREATE TABLE IF NOT EXISTS pedidos_reposicion (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
        veces_solicitado INTEGER DEFAULT 1,
        ultimo_solicitado_por TEXT,
        ultima_fecha TEXT DEFAULT (datetime('now')),
        estado TEXT DEFAULT 'pendiente',
        UNIQUE(producto_id)
    )""")

    # Historial de precios: cada vez que se cambia el precio de un producto queda un registro,
    # para poder ver cómo fue variando en el tiempo.
    c.execute("""CREATE TABLE IF NOT EXISTS historial_precios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
        precio REAL,
        fecha TEXT DEFAULT (datetime('now'))
    )""")

    # Ventas registradas desde el mostrador: qué se llevó el cliente y qué había pedido.
    # Es la materia prima para descubrir equivalencias solas: si alguien pide el código A y
    # termina llevándose el B, eso es una equivalencia que pasó en la vida real, aunque no
    # figure en ningún catálogo.
    c.execute("""CREATE TABLE IF NOT EXISTS ventas_registradas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
        termino_pedido TEXT,
        codigo_pedido_clean TEXT,
        usuario TEXT,
        fecha TEXT DEFAULT (datetime('now'))
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas_registradas(fecha)")
    # Sin este, "cuándo se vendió por última vez este producto" recorría la tabla de ventas
    # ENTERA una vez por producto. Con el estante lleno eso es minutos de espera.
    c.execute("CREATE INDEX IF NOT EXISTS idx_ventas_prod ON ventas_registradas(producto_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ventas_codigo ON ventas_registradas(codigo_pedido_clean)")

    # Mapeo de columnas recordado por proveedor. Cada vez que se importa una lista hay que
    # volver a indicar qué columna es el código, cuál el precio, etc. Un error ahí es lo que
    # mete basura en la base (un producto con código "1" colgado de decenas de equivalencias),
    # así que conviene que la próxima vez venga preseleccionado como la vez que funcionó.
    c.execute("""CREATE TABLE IF NOT EXISTS mapeo_columnas (
        proveedor TEXT PRIMARY KEY,
        idx_prov INTEGER, idx_oem INTEGER, idx_desc INTEGER,
        idx_precio INTEGER, idx_stock INTEGER,
        buscar_oem_en_desc INTEGER DEFAULT 0,
        prov_es_oem INTEGER DEFAULT 0,
        fecha TEXT DEFAULT (datetime('now'))
    )""")
    _cols_mapeo = [f[1] for f in c.execute("PRAGMA table_info(mapeo_columnas)").fetchall()]
    if "idx_ean" not in _cols_mapeo:
        c.execute("ALTER TABLE mapeo_columnas ADD COLUMN idx_ean INTEGER")

    # Decisiones ya tomadas sobre un vínculo puntual. Sirve para dos cosas: que lo revisado no
    # vuelva a aparecer en la auditoría, y que lo rechazado no se vuelva a crear si más adelante
    # se importa de nuevo la misma lista del proveedor.
    c.execute("""CREATE TABLE IF NOT EXISTS equivalencias_revisadas (
        producto_a_id INTEGER NOT NULL,
        producto_b_id INTEGER NOT NULL,
        decision TEXT NOT NULL,
        revisado_por TEXT,
        fecha TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (producto_a_id, producto_b_id)
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_revisadas_decision ON equivalencias_revisadas(decision)")

    # Vínculos que llegaron de una lista de proveedor y esperan revisión. Una importación puede
    # generar miles de vínculos de una: si se cargaran solos, un error en la columna de código de
    # fábrica te ensucia la base entera sin que nadie se entere.
    c.execute("""CREATE TABLE IF NOT EXISTS equivalencias_pendientes (
        producto_a_id INTEGER NOT NULL,
        producto_b_id INTEGER NOT NULL,
        origen TEXT,
        lote TEXT,
        fecha TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (producto_a_id, producto_b_id)
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pendientes_lote ON equivalencias_pendientes(lote)")
    # Estos dos estaban 450 líneas MÁS ARRIBA, antes de que existiera la tabla. Con una base ya
    # creada no se notaba —la tabla venía de una versión anterior—, pero en una instalación nueva
    # la app no abría: "no such table: main.equivalencias_pendientes" apenas arrancaba.
    # Medido con 30.000 pendientes: buscar si un par ya está pendiente pasa de 0,75 ms a 0,01 ms.
    # No se nota en una consulta suelta; sí al recorrer miles analizando la cola.
    c.execute("""CREATE INDEX IF NOT EXISTS idx_pend_a
                 ON equivalencias_pendientes(producto_a_id)""")
    c.execute("""CREATE INDEX IF NOT EXISTS idx_pend_b
                 ON equivalencias_pendientes(producto_b_id)""")
    # Un pendiente de un producto que ya no existe no se puede revisar —la pantalla hace JOIN
    # con productos y no lo ve— pero sí se cuenta: el cartel del buscador, el selector de listas
    # y «Descartar TODO» hacen COUNT(*). `equivalencias` se limpia sola con ON DELETE CASCADE;
    # esta tabla no tiene claves foráneas, y de los seis lugares que borran productos solo la
    # fusión se acordaba de ella. En vez de arreglar cinco, se arregla acá: vale para esos cinco
    # y para el que se agregue mañana.
    # DROP y CREATE, no IF NOT EXISTS, por lo mismo que productos_busqueda_alta.
    c.execute("DROP TRIGGER IF EXISTS productos_sin_pendientes_colgando")
    c.execute("""CREATE TRIGGER productos_sin_pendientes_colgando
                 AFTER DELETE ON productos BEGIN
                   DELETE FROM equivalencias_pendientes
                    WHERE producto_a_id = OLD.id OR producto_b_id = OLD.id;
                 END""")

    # Evidencia que respalda cada equivalencia sugerida. La idea es NO cargar nada solo:
    # cada sugerencia llega al panel con el detalle de en qué se basa, para poder decidir
    # con fundamento en vez de a ciegas.
    c.execute("""CREATE TABLE IF NOT EXISTS evidencia_equivalencia (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_clean TEXT NOT NULL,
        producto_id INTEGER NOT NULL,
        tipo TEXT NOT NULL,
        detalle TEXT,
        fecha TEXT DEFAULT (datetime('now')),
        UNIQUE(codigo_clean, producto_id, tipo)
    )""")

    # Sugerencias que el dueño ya miró y descartó, para no volver a proponérselas.
    c.execute("""CREATE TABLE IF NOT EXISTS equivalencias_descartadas (
        codigo_clean TEXT NOT NULL,
        producto_id INTEGER NOT NULL,
        descartado_por TEXT,
        fecha TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (codigo_clean, producto_id)
    )""")

    # Cuentas de empleados creadas desde la propia app (además de las que se pueden cargar en
    # Streamlit Secrets) — así el dueño no depende de tocar la configuración de Streamlit Cloud
    # cada vez que entra o se va alguien del equipo. La contraseña nunca se guarda en texto plano.
    c.execute("""CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        rol TEXT NOT NULL DEFAULT 'operador',
        activo INTEGER DEFAULT 1,
        creado_en TEXT DEFAULT (datetime('now'))
    )""")

    # Mecánicos externos (no son empleados del local): tienen su propio login, pero solo ven
    # el portal de armar presupuestos — nunca las secciones internas del negocio.
    c.execute("""CREATE TABLE IF NOT EXISTS mecanicos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        activo INTEGER DEFAULT 1,
        creado_en TEXT DEFAULT (datetime('now'))
    )""")

    # Presupuestos armados por mecánicos externos: repuestos elegidos + su propia mano de obra.
    c.execute("""CREATE TABLE IF NOT EXISTS presupuestos_mecanico (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mecanico_id INTEGER NOT NULL REFERENCES mecanicos(id) ON DELETE CASCADE,
        cliente_nombre TEXT,
        items_json TEXT NOT NULL,
        mano_obra REAL DEFAULT 0,
        total REAL,
        creado_en TEXT DEFAULT (datetime('now'))
    )""")


# Los códigos DTC que se pueden ARMAR en vez de copiar. Buena parte del estándar genérico es
# sistemática: el mismo texto con el número de cilindro, el banco o el sensor cambiado. Copiarlos
# a mano de a uno es donde se cuelan los errores —y donde se cansa uno y corta en el cilindro 4,
# que es lo que había pasado: el diccionario llegaba hasta P0304 y un motor de 6 tira P0305 y
# P0306—. Generados, salen los doce cilindros y los dos bancos completos, siempre con el mismo
# texto.
def _dtc_sistematicos():
    """Las familias del estándar genérico que son una serie. Devuelve la lista de tuplas."""
    salida = []
    causa_electrica = "Cableado cortado o en corto, conector sucio/flojo, sensor o actuador dañado"

    # Fallo de encendido por cilindro: P0301 a P0312.
    for cil in range(1, 13):
        salida.append((f"P{300 + cil:04d}", f"Fallo de encendido detectado en el cilindro {cil}",
                       "Motor - Encendido",
                       "Bujía o cable de ese cilindro, bobina, inyector sucio, compresión baja"))
    # Circuito del inyector por cilindro: P0201 a P0212.
    for cil in range(1, 13):
        salida.append((f"P{200 + cil:04d}", f"Circuito del inyector — cilindro {cil}",
                       "Motor - Combustible", causa_electrica))
    # Bajo, alto y contribución de cada cilindro: desde P0261, de a tres por cilindro.
    # LA NUMERACIÓN VA EN DECIMAL, no en hexadecimal: después de P0269 viene P0270. Escribirla
    # con aritmética hexadecimal —que es la trampa natural, porque los códigos «parecen» hex—
    # da P026A, que no existe, y deja al cilindro 4 en adelante con códigos inventados.
    for cil in range(1, 9):
        base = 261 + (cil - 1) * 3
        salida.append((f"P0{base:03d}", f"Circuito del inyector del cilindro {cil} — señal baja",
                       "Motor - Combustible", causa_electrica))
        salida.append((f"P0{base + 1:03d}", f"Circuito del inyector del cilindro {cil} — señal alta",
                       "Motor - Combustible", causa_electrica))
        salida.append((f"P0{base + 2:03d}",
                       f"Contribución o balance del cilindro {cil} fuera de rango",
                       "Motor - Combustible",
                       "Inyector sucio o gastado, compresión despareja, fuga de admisión"))
    # Sonda lambda por banco y sensor: bloques de seis desde P0130.
    for banco in (1, 2):
        for sensor in (1, 2, 3):
            base = 130 + (banco - 1) * 20 + (sensor - 1) * 6
            donde = f"banco {banco} sensor {sensor}"
            salida.append((f"P0{base:03d}", f"Circuito del sensor de oxígeno, {donde}", "Emisiones",
                           causa_electrica))
            salida.append((f"P0{base + 1:03d}", f"Sensor de oxígeno con señal baja, {donde}",
                           "Emisiones", "Sonda gastada, mezcla pobre, fuga de escape antes de la sonda"))
            salida.append((f"P0{base + 2:03d}", f"Sensor de oxígeno con señal alta, {donde}",
                           "Emisiones", "Sonda gastada, mezcla rica, inyector con pérdida"))
            salida.append((f"P0{base + 3:03d}", f"Sensor de oxígeno con respuesta lenta, {donde}",
                           "Emisiones", "Sonda al final de su vida, contaminada por aceite o silicona"))
            salida.append((f"P0{base + 4:03d}",
                           f"Circuito del calefactor del sensor de oxígeno, {donde}", "Emisiones",
                           causa_electrica))
            salida.append((f"P0{base + 5:03d}",
                           f"Circuito del calefactor del sensor de oxígeno con señal baja, {donde}",
                           "Emisiones", causa_electrica))
    # Pérdida de comunicación entre módulos (U0xxx). En un auto moderno es de lo que más
    # aparece y el diccionario no tenía ninguno.
    for codigo, modulo in (("U0100", "el módulo de motor (ECM/PCM)"),
                           ("U0101", "el módulo de la caja (TCM)"),
                           ("U0121", "el módulo de frenos (ABS)"),
                           ("U0140", "el módulo de carrocería (BCM)"),
                           ("U0151", "el módulo del airbag"),
                           ("U0155", "el tablero de instrumentos"),
                           ("U0164", "el módulo de climatización"),
                           ("U0184", "el equipo de audio"),
                           ("U0199", "el módulo de puertas")):
        salida.append((codigo, f"Se perdió la comunicación con {modulo}", "Red / Comunicación",
                       "Red CAN cortada o en corto, módulo sin alimentación o sin masa, "
                       "batería baja, módulo dañado"))
    salida.append(("U0001", "Bus CAN de alta velocidad", "Red / Comunicación",
                   "Red CAN cortada o en corto, resistencias de terminación, módulo dañado"))
    salida.append(("U0073", "Bus de comunicación del módulo de control apagado",
                   "Red / Comunicación", "Corto en la red CAN, módulo que la tiene tomada"))
    salida.append(("U0401", "Datos inválidos recibidos del módulo de motor (ECM/PCM)",
                   "Red / Comunicación", "Módulo con falla interna, programación incorrecta"))
    # Correlación cigüeñal / árbol de levas: P0016 a P0019.
    # Es el código que más plata mueve del mostrador y no estaba: significa que la distribución
    # se corrió. El que atiende lee «correlación» y no sabe qué es; lo que hay que venderle es
    # el kit de distribución, que es exactamente lo que el catálogo tiene cargado.
    for codigo, donde in (("P0016", "banco 1, sensor de admisión"),
                          ("P0017", "banco 1, sensor de escape"),
                          ("P0018", "banco 2, sensor de admisión"),
                          ("P0019", "banco 2, sensor de escape")):
        salida.append((codigo,
                       f"La distribución se corrió: el cigüeñal y el árbol de levas no están "
                       f"en fase ({donde})",
                       "Motor - Distribución",
                       "Correa o cadena de distribución salteada o estirada, tensor flojo o "
                       "gastado, kit de distribución mal calzado, sensor de fase o de rotación "
                       "flojo, engranaje del variador (VVT) sucio"))
    # Bujías de precalentamiento por cilindro: P0671 a P0678. Es el código del diesel que no
    # arranca en frío. P0380 (el circuito en general) ya estaba; faltaba saber CUÁL.
    for cil in range(1, 9):
        salida.append((f"P0{670 + cil:03d}",
                       f"Circuito de la bujía incandescente (de precalentamiento) — cilindro {cil}",
                       "Motor - Arranque en frío (diesel)",
                       "Bujía incandescente quemada o con resistencia alta, relé o temporizador "
                       "de precalentamiento, cableado cortado"))
    # Presión del riel (common rail). El diesel moderno arranca y anda por esto.
    for codigo, texto, causa in (
            ("P0087", "Presión del riel o del sistema de combustible demasiado baja",
             "Filtro de combustible tapado, bomba de combustible gastada, regulador de presión, "
             "inyector con retorno excesivo, aire en el circuito"),
            ("P0088", "Presión del riel o del sistema de combustible demasiado alta",
             "Regulador de presión trabado, sensor de presión del riel desviado, retorno tapado"),
            ("P0089", "Regulador de presión de combustible fuera de rango",
             "Regulador de presión gastado o trabado, bomba de combustible que no da caudal"),
            ("P0093", "Fuga grande detectada en el sistema de combustible",
             "Cañería o retorno del inyector perdiendo, inyector con el asiento gastado"),
            ("P0094", "Fuga chica detectada en el sistema de combustible",
             "Cañería o retorno perdiendo de a poco, unión floja"),
            ("P0191", "Circuito del sensor de presión del riel fuera de rango",
             "Sensor de presión del riel desviado, conector sucio, cableado"),
            ("P0192", "Sensor de presión del riel con señal baja",
             "Sensor de presión del riel dañado, cable en corto a masa"),
            ("P0193", "Sensor de presión del riel con señal alta",
             "Sensor de presión del riel dañado, cable cortado o en corto a positivo")):
        salida.append((codigo, texto, "Motor - Combustible", causa))
    # Turbo. P0234 (sobrepresión) ya estaba suelto; faltaba la falta de presión, que es lo que
    # el cliente describe como «le falta fuerza».
    for codigo, texto, causa in (
            ("P0045", "Circuito de control de la geometría variable del turbo",
             "Actuador de la geometría variable trabado por carbón, válvula solenoide de vacío, "
             "cañería de vacío partida, cableado"),
            ("P0046", "Actuador de la geometría del turbo fuera de rango",
             "Geometría variable trabada, actuador gastado, vacío insuficiente"),
            ("P0299", "El turbo no da la presión esperada (subalimentación)",
             "Manguera de aire del intercooler suelta o partida, geometría variable trabada, "
             "filtro de aire tapado, turbo gastado, válvula de alivio perdiendo")):
        salida.append((codigo, texto, "Motor - Admisión / Turbo", causa))
    # Pedal del acelerador y mariposa electrónica (P2101 en adelante). En todo auto con
    # acelerador por cable eléctrico —o sea casi todo desde 2005— es de lo que más sale.
    for codigo, texto, causa in (
            ("P2101", "El cuerpo de mariposa no llega a la posición ordenada",
             "Cuerpo de mariposa sucio o con el motor quemado, conector flojo"),
            ("P2102", "Motor del cuerpo de mariposa — señal baja", causa_electrica),
            ("P2103", "Motor del cuerpo de mariposa — señal alta", causa_electrica),
            ("P2111", "El cuerpo de mariposa quedó trabado abierto",
             "Cuerpo de mariposa sucio o trabado por carbón, resorte de retorno vencido"),
            ("P2112", "El cuerpo de mariposa quedó trabado cerrado",
             "Cuerpo de mariposa sucio o trabado por carbón, motor del cuerpo quemado"),
            ("P2122", "Sensor del pedal del acelerador D — señal baja", causa_electrica),
            ("P2123", "Sensor del pedal del acelerador D — señal alta", causa_electrica),
            ("P2127", "Sensor del pedal del acelerador E — señal baja", causa_electrica),
            ("P2128", "Sensor del pedal del acelerador E — señal alta", causa_electrica),
            ("P2135", "Los dos sensores del cuerpo de mariposa no coinciden entre sí",
             "Cuerpo de mariposa con la pista gastada, conector con un pin flojo, masa común"),
            ("P2138", "Los dos sensores del pedal del acelerador no coinciden entre sí",
             "Pedal del acelerador con la pista gastada, conector flojo, masa común")):
        salida.append((codigo, texto, "Motor - Sensores/Admisión", causa))
    # Electroventilador y sus relés. El código que llega junto con «se calienta parado».
    for codigo, texto, causa in (
            ("P0691", "Relé del electroventilador 1 — señal baja",
             "Relé del electroventilador pegado o quemado, cable en corto a masa"),
            ("P0692", "Relé del electroventilador 1 — señal alta",
             "Relé del electroventilador quemado, cable cortado"),
            ("P0645", "Circuito del relé del embrague del compresor del aire acondicionado",
             "Relé del compresor quemado, bobina del embrague del compresor abierta, cableado")):
        salida.append((codigo, texto, "Refrigeración / Confort", causa))
    # Carga y bomba de combustible: dos que dejan el auto en la calle.
    for codigo, texto, causa in (
            ("P0622", "Circuito de control del campo del alternador",
             "Alternador con el regulador quemado, correa floja, cableado del alternador"),
            ("P0625", "Campo del alternador — señal baja", "Alternador o su regulador, cableado"),
            ("P0626", "Campo del alternador — señal alta", "Alternador o su regulador, cableado"),
            ("P0627", "Circuito de control de la bomba de combustible",
             "Bomba de combustible gastada, relé de bomba, cableado del tanque"),
            ("P0628", "Bomba de combustible — señal baja", "Relé de bomba, cable en corto a masa"),
            ("P0629", "Bomba de combustible — señal alta", "Relé de bomba, cable cortado")):
        salida.append((codigo, texto, "Eléctrico - Carga y combustible", causa))
    # Sonda lambda pegada. P0130 y familia dicen «circuito»; estos dicen que la sonda dejó de
    # moverse, que es el diagnóstico que termina en una sonda nueva.
    for codigo, texto in (("P2195", "Sonda de oxígeno pegada en pobre, banco 1 sensor 1"),
                          ("P2196", "Sonda de oxígeno pegada en rica, banco 1 sensor 1"),
                          ("P2197", "Sonda de oxígeno pegada en pobre, banco 2 sensor 1"),
                          ("P2198", "Sonda de oxígeno pegada en rica, banco 2 sensor 1")):
        salida.append((codigo, texto, "Emisiones",
                       "Sonda lambda contaminada o al final de su vida, fuga de escape antes de "
                       "la sonda, inyector con pérdida"))
    # Fallos de encendido que no son por cilindro.
    salida.append(("P0313", "Fallo de encendido con el nivel de combustible bajo",
                   "Motor - Encendido", "Poco combustible en el tanque, bomba de combustible que "
                   "pierde presión cuando queda poco"))
    salida.append(("P0316", "Fallo de encendido apenas arranca el motor", "Motor - Encendido",
                   "Bujías gastadas, bobina con fuga en frío, compresión baja, inyector sucio"))
    # Fuga de admisión: el código que explica media docena de síntomas sueltos.
    salida.append(("P2279", "Fuga de aire en el sistema de admisión", "Motor - Sensores/Admisión",
                   "Manguera de admisión partida, junta del múltiple soplada, cuerpo de mariposa "
                   "flojo, cañería de vacío suelta"))
    # Filtro de partículas (diesel moderno). Todavía no se vende acá, pero el código llega igual
    # y conviene que la app diga qué significa en vez de no encontrarlo.
    salida.append(("P2002", "Rendimiento del filtro de partículas por debajo del límite, banco 1",
                   "Emisiones (diesel)",
                   "Filtro de partículas saturado por no completar regeneraciones, sensor de "
                   "presión diferencial o sus cañerías tapadas, inyector con pérdida"))
    salida.append(("P2463", "Filtro de partículas — acumulación excesiva de hollín",
                   "Emisiones (diesel)",
                   "Muchos viajes cortos sin llegar a regenerar, sensor de presión diferencial, "
                   "válvula EGR pegada abierta"))
    # Sensores de velocidad de rueda (C0xxx), que es el código típico del ABS.
    for codigo, rueda in (("C0035", "delantera izquierda"), ("C0040", "delantera derecha"),
                          ("C0045", "trasera izquierda"), ("C0050", "trasera derecha")):
        salida.append((codigo, f"Circuito del sensor de velocidad de la rueda {rueda}",
                       "Frenos / ABS",
                       "Sensor sucio o dañado, corona dentada rota, cableado cortado por el "
                       "movimiento de la suspensión"))
    return salida


def _datos_precargados_y_migraciones(c):
    """Semillas que vienen con la app (códigos de falla, fabricantes por VIN) y las
    migraciones que ponen al día una base creada por una versión anterior.

    Está al final a propósito: todo esto necesita que las tablas ya existan.

    Se llama desde crear_esquema(), en orden: cada parte da por hecho que las anteriores ya
    corrieron."""
    c.execute("""CREATE TABLE IF NOT EXISTS combos_sugeridos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        disparador TEXT NOT NULL,
        item TEXT NOT NULL
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_combos_disp ON combos_sugeridos(disparador)")
    c.execute("SELECT COUNT(*) FROM combos_sugeridos")
    if c.fetchone()[0] == 0:
        c.executemany(
            "INSERT INTO combos_sugeridos (disparador, item) VALUES (?, ?)",
            [
                ("correa de distribucion", "Kit de distribución"),
                ("correa de distribucion", "Tensor de distribución"),
                ("correa de distribucion", "Bomba de agua"),
            ]
        )

    # Semilla inicial de códigos DTC genéricos (estándar OBD-II / SAE J2012, no específicos de
    # marca), verificados contra fuentes de referencia. Es un punto de partida — sumá o corregí
    # los que necesites desde la app. Los códigos P1xxx específicos de fabricante se cargan
    # aparte indicando la marca (ver Modo Mecánico → Códigos DTC).
    # Antes esto corría solo con la tabla vacía, así que quien ya tenía la app nunca recibía
    # los códigos nuevos — y el diccionario llegaba hasta el cilindro 4. Ahora va por versión.
    c.execute("SELECT valor FROM configuracion WHERE clave = 'semilla_dtc_version'")
    _fila_dtc = c.fetchone()
    if (_fila_dtc["valor"] if _fila_dtc else None) != SEMILLA_DTC_VERSION:
        seed_dtc = [
            ("P0010","Falla eléctrica en el actuador de posición A del árbol de levas, banco 1","Motor - Sensores/Admisión","Cableado cortado o en corto, conector sucio/flojo, sensor o actuador dañado"),
            ("P0011","Avance excesivo o mal desempeño en la posición A del árbol de levas, banco 1","Motor - Sensores/Admisión","Sensor descalibrado, obstrucción física, fuga, componente mecánico desgastado"),
            ("P0012","Retardo excesivo en la posición A del árbol de levas, banco 1","Motor - Sensores/Admisión","Sensor descalibrado, obstrucción física, fuga, componente mecánico desgastado"),
            ("P0013","Falla eléctrica en el actuador de posición B del árbol de levas, banco 1","Motor - Sensores/Admisión","Cableado cortado o en corto, conector sucio/flojo, sensor o actuador dañado"),
            ("P0014","Avance excesivo o mal desempeño en la posición B del árbol de levas, banco 1","Motor - Sensores/Admisión","Sensor descalibrado, obstrucción física, fuga, componente mecánico desgastado"),
            ("P0015","Retardo excesivo en la posición B del árbol de levas, banco 1","Motor - Sensores/Admisión","Sensor descalibrado, obstrucción física, fuga, componente mecánico desgastado"),
            ("P0020","Falla eléctrica en el actuador de posición A del árbol de levas, banco 2","Motor - Sensores/Admisión","Cableado cortado o en corto, conector sucio/flojo, sensor o actuador dañado"),
            ("P0021","Avance excesivo o mal desempeño en la posición A del árbol de levas, banco 2","Motor - Sensores/Admisión","Sensor descalibrado, obstrucción física, fuga, componente mecánico desgastado"),
            ("P0022","Retardo excesivo en la posición A del árbol de levas, banco 2","Motor - Sensores/Admisión","Sensor descalibrado, obstrucción física, fuga, componente mecánico desgastado"),
            ("P0030","Falla eléctrica en el calefactor del sensor de oxígeno, banco 1 sensor 1","Emisiones","Cableado cortado o en corto, conector sucio/flojo, sensor o actuador dañado"),
            ("P0031","Señal baja en el calefactor del sensor de oxígeno, banco 1 sensor 1","Emisiones","Cortocircuito a masa, sensor en mal estado, cableado dañado"),
            ("P0032","Señal alta en el calefactor del sensor de oxígeno, banco 1 sensor 1","Emisiones","Circuito abierto, cortocircuito a positivo, sensor en mal estado"),
            ("P0036","Falla eléctrica en el calefactor del sensor de oxígeno, banco 1 sensor 2","Emisiones","Cableado cortado o en corto, conector sucio/flojo, sensor o actuador dañado"),
            ("P0037","Señal baja en el calefactor del sensor de oxígeno, banco 1 sensor 2","Emisiones","Cortocircuito a masa, sensor en mal estado, cableado dañado"),
            ("P0038","Señal alta en el calefactor del sensor de oxígeno, banco 1 sensor 2","Emisiones","Circuito abierto, cortocircuito a positivo, sensor en mal estado"),
            ("P0050","Falla eléctrica en el calefactor del sensor de oxígeno, banco 2 sensor 1","Emisiones","Cableado cortado o en corto, conector sucio/flojo, sensor o actuador dañado"),
            ("P0051","Señal baja en el calefactor del sensor de oxígeno, banco 2 sensor 1","Emisiones","Cortocircuito a masa, sensor en mal estado, cableado dañado"),
            ("P0052","Señal alta en el calefactor del sensor de oxígeno, banco 2 sensor 1","Emisiones","Circuito abierto, cortocircuito a positivo, sensor en mal estado"),
            ("P0056","Falla eléctrica en el calefactor del sensor de oxígeno, banco 2 sensor 2","Emisiones","Cableado cortado o en corto, conector sucio/flojo, sensor o actuador dañado"),
            ("P0057","Señal baja en el calefactor del sensor de oxígeno, banco 2 sensor 2","Emisiones","Cortocircuito a masa, sensor en mal estado, cableado dañado"),
            ("P0058","Señal alta en el calefactor del sensor de oxígeno, banco 2 sensor 2","Emisiones","Circuito abierto, cortocircuito a positivo, sensor en mal estado"),
            ("P0070","Falla eléctrica en el sensor de temperatura de aire ambiente","Motor - Sensores/Admisión","Cableado cortado o en corto, conector sucio/flojo, sensor dañado"),
            ("P0071","Sensor de temperatura de aire ambiente fuera de rango","Motor - Sensores/Admisión","Sensor descalibrado, cableado dañado"),
            ("P0072","Señal baja en el sensor de temperatura de aire ambiente","Motor - Sensores/Admisión","Cortocircuito a masa, sensor en mal estado"),
            ("P0073","Señal alta en el sensor de temperatura de aire ambiente","Motor - Sensores/Admisión","Circuito abierto, sensor en mal estado"),
            ("P0074","Señal intermitente en el sensor de temperatura de aire ambiente","Motor - Sensores/Admisión","Conector flojo u oxidado, falso contacto"),
            ("P0100","Falla eléctrica en el medidor de caudal de aire (MAF)","Motor - Sensores/Admisión","Sensor sucio, cableado, conector"),
            ("P0101","Medidor de caudal de aire (MAF) fuera de rango","Motor - Sensores/Admisión","Filtro de aire sucio, fugas de vacío, sensor sucio"),
            ("P0102","Señal baja en el medidor de caudal de aire (MAF)","Motor - Sensores/Admisión","Cortocircuito a masa, sensor sucio o dañado"),
            ("P0103","Señal alta en el medidor de caudal de aire (MAF)","Motor - Sensores/Admisión","Circuito abierto, sensor dañado"),
            ("P0104","Señal intermitente en el medidor de caudal de aire (MAF)","Motor - Sensores/Admisión","Conector flojo u oxidado, falso contacto"),
            ("P0105","Falla eléctrica en el sensor de presión absoluta de múltiple / barométrica (MAP)","Motor - Sensores/Admisión","Manguera de vacío rota, sensor o cableado dañado"),
            ("P0106","Sensor MAP fuera de rango","Motor - Sensores/Admisión","Fuga de vacío, sensor descalibrado"),
            ("P0107","Señal baja en el sensor MAP","Motor - Sensores/Admisión","Cortocircuito a masa, sensor dañado"),
            ("P0108","Señal alta en el sensor MAP","Motor - Sensores/Admisión","Circuito abierto, sensor dañado"),
            ("P0109","Señal intermitente en el sensor MAP","Motor - Sensores/Admisión","Conector flojo u oxidado, falso contacto"),
            ("P0110","Falla eléctrica en el sensor de temperatura del aire de admisión (IAT)","Motor - Sensores/Admisión","Sensor o cableado en mal estado"),
            ("P0111","Sensor IAT fuera de rango","Motor - Sensores/Admisión","Sensor descalibrado, cableado dañado"),
            ("P0112","Señal baja en el sensor IAT","Motor - Sensores/Admisión","Cortocircuito a masa, sensor dañado"),
            ("P0113","Señal alta en el sensor IAT","Motor - Sensores/Admisión","Circuito abierto, sensor dañado"),
            ("P0114","Señal intermitente en el sensor IAT","Motor - Sensores/Admisión","Conector flojo u oxidado, falso contacto"),
            ("P0115","Falla eléctrica en el sensor de temperatura del refrigerante (ECT)","Motor - Sensores/Admisión","Sensor, conector, cableado"),
            ("P0116","Sensor ECT fuera de rango","Motor - Sensores/Admisión","Sensor descalibrado, nivel de refrigerante bajo"),
            ("P0117","Señal baja en el sensor ECT","Motor - Sensores/Admisión","Cortocircuito a masa, sensor dañado"),
            ("P0118","Señal alta en el sensor ECT","Motor - Sensores/Admisión","Circuito abierto, sensor dañado"),
            ("P0119","Señal intermitente en el sensor ECT","Motor - Sensores/Admisión","Conector flojo u oxidado, falso contacto"),
            ("P0120","Falla eléctrica en el sensor de posición del acelerador/pedal A (TPS)","Motor - Sensores/Admisión","Sensor TPS, cableado"),
            ("P0121","Sensor TPS A fuera de rango","Motor - Sensores/Admisión","Sensor descalibrado, cableado dañado"),
            ("P0122","Señal baja en el sensor TPS A","Motor - Sensores/Admisión","Cortocircuito a masa, sensor dañado"),
            ("P0123","Señal alta en el sensor TPS A","Motor - Sensores/Admisión","Circuito abierto, sensor dañado"),
            ("P0124","Señal intermitente en el sensor TPS A","Motor - Sensores/Admisión","Conector flojo u oxidado, falso contacto"),
            ("P0125","El refrigerante no llega a la temperatura necesaria para el lazo cerrado de combustible","Motor - Sensores/Admisión","Termostato pegado en abierto, sensor ECT"),
            ("P0128","Termostato: el refrigerante no alcanza la temperatura de regulación","Motor - Sensores/Admisión","Termostato pegado en abierto"),
            ("P0130","Falla eléctrica en el sensor de oxígeno, banco 1 sensor 1","Emisiones","Sonda lambda, cableado"),
            ("P0131","Voltaje bajo en el sensor de oxígeno, banco 1 sensor 1","Emisiones","Cortocircuito a masa, sonda en mal estado"),
            ("P0132","Voltaje alto en el sensor de oxígeno, banco 1 sensor 1","Emisiones","Circuito abierto, sonda en mal estado"),
            ("P0133","Respuesta lenta en el sensor de oxígeno, banco 1 sensor 1","Emisiones","Sonda envejecida o contaminada"),
            ("P0134","Sin actividad detectada en el sensor de oxígeno, banco 1 sensor 1","Emisiones","Sonda desconectada o sin actividad, cableado"),
            ("P0135","Falla eléctrica en el calefactor del sensor de oxígeno, banco 1 sensor 1","Emisiones","Calefactor de la sonda dañado, fusible, cableado"),
            ("P0136","Falla eléctrica en el sensor de oxígeno, banco 1 sensor 2","Emisiones","Sonda lambda, cableado"),
            ("P0137","Voltaje bajo en el sensor de oxígeno, banco 1 sensor 2","Emisiones","Cortocircuito a masa, sonda en mal estado"),
            ("P0138","Voltaje alto en el sensor de oxígeno, banco 1 sensor 2","Emisiones","Circuito abierto, sonda en mal estado"),
            ("P0140","Sin actividad detectada en el sensor de oxígeno, banco 1 sensor 2","Emisiones","Sonda desconectada o sin actividad, cableado"),
            ("P0141","Falla eléctrica en el calefactor del sensor de oxígeno, banco 1 sensor 2","Emisiones","Calefactor de la sonda dañado, fusible, cableado"),
            ("P0150","Falla eléctrica en el sensor de oxígeno, banco 2 sensor 1","Emisiones","Sonda lambda, cableado"),
            ("P0155","Falla eléctrica en el calefactor del sensor de oxígeno, banco 2 sensor 1","Emisiones","Calefactor de la sonda dañado, fusible, cableado"),
            ("P0170","Ajuste de mezcla fuera de rango, banco 1","Motor - Sensores/Admisión","Sonda O2, inyectores, fugas de vacío"),
            ("P0171","Mezcla demasiado pobre, banco 1","Motor - Sensores/Admisión","Fuga de vacío, inyector, sensor MAF"),
            ("P0172","Mezcla demasiado rica, banco 1","Motor - Sensores/Admisión","Inyector, presión de combustible, sensor O2"),
            ("P0173","Ajuste de mezcla fuera de rango, banco 2","Motor - Sensores/Admisión","Sonda O2, inyectores, fugas de vacío"),
            ("P0174","Mezcla demasiado pobre, banco 2","Motor - Sensores/Admisión","Fuga de vacío, inyector, sensor MAF"),
            ("P0175","Mezcla demasiado rica, banco 2","Motor - Sensores/Admisión","Inyector, presión de combustible, sensor O2"),
            ("P0200","Falla eléctrica general en el circuito de inyectores","Motor - Inyectores/Combustible","Inyector, cableado, módulo"),
            ("P0201","Falla eléctrica en el inyector del cilindro 1","Motor - Inyectores/Combustible","Inyector, cableado de ese cilindro"),
            ("P0202","Falla eléctrica en el inyector del cilindro 2","Motor - Inyectores/Combustible","Inyector, cableado de ese cilindro"),
            ("P0203","Falla eléctrica en el inyector del cilindro 3","Motor - Inyectores/Combustible","Inyector, cableado de ese cilindro"),
            ("P0204","Falla eléctrica en el inyector del cilindro 4","Motor - Inyectores/Combustible","Inyector, cableado de ese cilindro"),
            ("P0217","Sobretemperatura del motor","Motor - Encendido/Combustión","Refrigerante, bomba de agua, termostato"),
            ("P0230","Falla eléctrica en el circuito primario de la bomba de combustible","Motor - Inyectores/Combustible","Bomba, relé, cableado"),
            ("P0300","Fallos de encendido detectados en varios cilindros o aleatorios","Motor - Encendido/Combustión","Bujías, bobinas, compresión"),
            ("P0301","Fallo de encendido en el cilindro 1","Motor - Encendido/Combustión","Bujía, bobina, inyector de ese cilindro"),
            ("P0302","Fallo de encendido en el cilindro 2","Motor - Encendido/Combustión","Bujía, bobina, inyector de ese cilindro"),
            ("P0303","Fallo de encendido en el cilindro 3","Motor - Encendido/Combustión","Bujía, bobina, inyector de ese cilindro"),
            ("P0304","Fallo de encendido en el cilindro 4","Motor - Encendido/Combustión","Bujía, bobina, inyector de ese cilindro"),
            ("P0325","Falla eléctrica en el sensor de detonación (knock sensor), banco 1 o único","Motor - Encendido/Combustión","Sensor, cableado"),
            ("P0326","Sensor de detonación 1 fuera de rango","Motor - Encendido/Combustión","Sensor descalibrado, cableado"),
            ("P0327","Señal baja en el sensor de detonación 1","Motor - Encendido/Combustión","Cortocircuito a masa, sensor dañado"),
            ("P0328","Señal alta en el sensor de detonación 1","Motor - Encendido/Combustión","Circuito abierto, sensor dañado"),
            ("P0335","Falla eléctrica en el sensor de posición del cigüeñal (CKP)","Motor - Encendido/Combustión","Sensor CKP, cableado, tone wheel"),
            ("P0336","Sensor CKP fuera de rango","Motor - Encendido/Combustión","Sensor descalibrado, rueda fónica dañada"),
            ("P0340","Falla eléctrica en el sensor de posición del árbol de levas (CMP)","Motor - Encendido/Combustión","Sensor CMP, cableado"),
            ("P0341","Sensor CMP fuera de rango","Motor - Encendido/Combustión","Sensor descalibrado, cableado"),
            ("P0400","Falla en el caudal de recirculación de gases de escape (EGR)","Emisiones","Válvula EGR, conductos obstruidos"),
            ("P0401","Caudal insuficiente de EGR","Emisiones","Válvula EGR trabada cerrada, conducto obstruido"),
            ("P0402","Caudal excesivo de EGR","Emisiones","Válvula EGR trabada abierta"),
            ("P0420","Eficiencia del catalizador por debajo del umbral, banco 1","Emisiones","Catalizador, sonda lambda"),
            ("P0430","Eficiencia del catalizador por debajo del umbral, banco 2","Emisiones","Catalizador, sonda lambda"),
            ("P0440","Falla general en el sistema de control de emisiones evaporativas (EVAP)","Emisiones","Tapa de nafta, válvula, mangueras"),
            ("P0441","Caudal de purga EVAP incorrecto","Emisiones","Válvula de purga, mangueras obstruidas"),
            ("P0442","Fuga pequeña detectada en el sistema EVAP","Emisiones","Tapa de nafta floja, manguera con fisura"),
            ("P0446","Falla eléctrica en la válvula de ventilación del sistema EVAP","Emisiones","Válvula de venteo, cableado"),
            ("P0447","Circuito de ventilación EVAP abierto","Emisiones","Cableado cortado, válvula desconectada"),
            ("P0448","Circuito de ventilación EVAP en corto","Emisiones","Cableado en corto, válvula dañada"),
            ("P0451","Falla eléctrica en el sensor de presión del sistema EVAP","Emisiones","Sensor de presión, cableado"),
            ("P0452","Señal baja en el sensor de presión del sistema EVAP","Emisiones","Cortocircuito a masa, sensor dañado"),
            ("P0453","Señal alta en el sensor de presión del sistema EVAP","Emisiones","Circuito abierto, sensor dañado"),
            ("P0455","Fuga grande detectada en el sistema EVAP","Emisiones","Tapa de nafta, manguera desconectada"),
            ("P0456","Fuga muy pequeña detectada en el sistema EVAP","Emisiones","Tapa de nafta, fisura muy pequeña"),
            ("P0457","Fuga detectada, posible tapa de combustible floja o mal cerrada","Emisiones","Tapa de nafta floja, dañada o mal puesta"),
            ("P0461","Sensor de nivel de combustible fuera de rango","Motor - Inyectores/Combustible","Sensor de nivel, flotante"),
            ("P0462","Señal baja en el sensor de nivel de combustible","Motor - Inyectores/Combustible","Cortocircuito a masa, sensor dañado"),
            ("P0463","Señal alta en el sensor de nivel de combustible","Motor - Inyectores/Combustible","Circuito abierto, sensor dañado"),
            ("P0500","Falla eléctrica en el sensor de velocidad del vehículo (VSS)","Transmisión","Sensor VSS, cableado"),
            ("P0501","Sensor VSS fuera de rango","Transmisión","Sensor descalibrado, cableado"),
            ("P0505","Falla en el sistema de control de marcha lenta (IAC)","Motor - Sensores/Admisión","Válvula IAC, cuerpo de aceleración sucio"),
            ("P0506","RPM de marcha lenta por debajo de lo esperado","Motor - Sensores/Admisión","Válvula IAC, fuga de vacío"),
            ("P0507","RPM de marcha lenta por encima de lo esperado","Motor - Sensores/Admisión","Válvula IAC trabada, fuga de vacío grande"),
            ("P0600","Falla en el enlace serial de comunicaciones del módulo","Módulo de control / Eléctrico","Cableado del bus de datos, módulo"),
            ("P0601","Error de suma de verificación en la memoria del módulo de control","Módulo de control / Eléctrico","Módulo de control con falla interna"),
            ("P0700","Avería general en el sistema de control de la transmisión","Transmisión","Ver códigos específicos de la TCM"),
            ("P0701","Sistema de control de la transmisión fuera de rango","Transmisión","Sensor o solenoide de la transmisión"),
            ("P0705","Falla eléctrica en el sensor de rango de la transmisión (PRNDL)","Transmisión","Sensor, cableado"),
            ("P0710","Falla eléctrica en el sensor de temperatura del fluido de la transmisión","Transmisión","Sensor, cableado"),
            ("P0715","Falla eléctrica en el sensor de velocidad de entrada / turbina","Transmisión","Sensor, cableado"),
            ("P0720","Falla eléctrica en el sensor de velocidad de salida de la transmisión","Transmisión","Sensor, cableado"),
            ("P0730","Relación de engranes incorrecta","Transmisión","Solenoides de cambio, fluido bajo o degradado"),
            ("P0740","Falla en el circuito del embrague del convertidor de par","Transmisión","Solenoide TCC, cableado"),
            ("P0750","Falla en el solenoide de cambios A","Transmisión","Solenoide, cableado"),
            ("P0755","Falla en el solenoide de cambios B","Transmisión","Solenoide, cableado"),
            ("P0205","Falla eléctrica en el inyector del cilindro 5","Motor - Inyectores/Combustible","Inyector, cableado de ese cilindro"),
            ("P0206","Falla eléctrica en el inyector del cilindro 6","Motor - Inyectores/Combustible","Inyector, cableado de ese cilindro"),
            ("P0207","Falla eléctrica en el inyector del cilindro 7","Motor - Inyectores/Combustible","Inyector, cableado de ese cilindro"),
            ("P0208","Falla eléctrica en el inyector del cilindro 8","Motor - Inyectores/Combustible","Inyector, cableado de ese cilindro"),
            ("P0221","Sensor TPS B fuera de rango","Motor - Sensores/Admisión","Sensor descalibrado, cableado dañado"),
            ("P0222","Señal baja en el sensor TPS B","Motor - Sensores/Admisión","Cortocircuito a masa, sensor dañado"),
            ("P0223","Señal alta en el sensor TPS B","Motor - Sensores/Admisión","Circuito abierto, sensor dañado"),
            ("P0224","Señal intermitente en el sensor TPS B","Motor - Sensores/Admisión","Conector flojo u oxidado, falso contacto"),
            ("P0231","Señal baja en el circuito secundario de la bomba de combustible","Motor - Inyectores/Combustible","Cortocircuito a masa, bomba, relé"),
            ("P0232","Señal alta en el circuito secundario de la bomba de combustible","Motor - Inyectores/Combustible","Circuito abierto, bomba, relé"),
            ("P0234","Sobrepresión de sobrealimentación (turbo)","Motor - Sensores/Admisión","Válvula wastegate, actuador del turbo"),
            ("P0261","Señal baja en el inyector del cilindro 1","Motor - Inyectores/Combustible","Cortocircuito a masa, inyector dañado"),
            ("P0262","Señal alta en el inyector del cilindro 1","Motor - Inyectores/Combustible","Circuito abierto, inyector dañado"),
            ("P0330","Falla eléctrica en el sensor de detonación 2, banco 2","Motor - Encendido/Combustión","Sensor, cableado"),
            ("P0331","Sensor de detonación 2 fuera de rango","Motor - Encendido/Combustión","Sensor descalibrado, cableado"),
            ("P0339","Señal intermitente en el sensor CKP","Motor - Encendido/Combustión","Conector flojo u oxidado, falso contacto"),
            ("P0343","Señal alta en el sensor CMP","Motor - Encendido/Combustión","Circuito abierto, sensor dañado"),
            ("P0344","Señal intermitente en el sensor CMP","Motor - Encendido/Combustión","Conector flojo u oxidado, falso contacto"),
            ("P0350","Falla general en el circuito primario/secundario de bobina de encendido","Motor - Encendido/Combustión","Bobina, cableado, módulo"),
            ("P0351","Falla en la bobina de encendido A","Motor - Encendido/Combustión","Bobina, cableado"),
            ("P0352","Falla en la bobina de encendido B","Motor - Encendido/Combustión","Bobina, cableado"),
            ("P0353","Falla en la bobina de encendido C","Motor - Encendido/Combustión","Bobina, cableado"),
            ("P0354","Falla en la bobina de encendido D","Motor - Encendido/Combustión","Bobina, cableado"),
            ("P0370","Falla en la señal de referencia de sincronización de alta resolución A","Motor - Encendido/Combustión","Sensor, cableado, rueda fónica"),
            ("P0380","Circuito de la bujía incandescente (de precalentamiento) — motores diésel","Motor - Arranque en frío (diesel)","Bujía incandescente quemada o con resistencia alta, relé o temporizador de precalentamiento, cableado"),
            ("P0410","Falla en el sistema de inyección de aire secundario","Emisiones","Bomba de aire secundario, válvulas, mangueras"),
            ("P0411","Caudal incorrecto en la inyección de aire secundario","Emisiones","Bomba de aire secundario, fugas"),
            ("P0480","Falla eléctrica en el circuito de control del ventilador de enfriamiento 1","Motor - Sensores/Admisión","Relé, motor del ventilador, cableado"),
            ("P0481","Falla eléctrica en el circuito de control del ventilador de enfriamiento 2","Motor - Sensores/Admisión","Relé, motor del ventilador, cableado"),
            ("P0510","Falla en el interruptor de mariposa en posición cerrada","Motor - Sensores/Admisión","Interruptor, cableado"),
            ("P0520","Falla eléctrica en el circuito de presión de aceite del motor","Motor - Sensores/Admisión","Sensor, cableado"),
            ("P0521","Presión de aceite del motor fuera de rango","Motor - Sensores/Admisión","Sensor descalibrado, nivel de aceite"),
            ("P0522","Voltaje bajo en la señal de presión de aceite del motor","Motor - Sensores/Admisión","Cortocircuito a masa, sensor dañado"),
            ("P0523","Voltaje alto en la señal de presión de aceite del motor","Motor - Sensores/Admisión","Circuito abierto, sensor dañado"),
            ("P0530","Falla eléctrica en el sensor de presión del refrigerante de A/C","Motor - Sensores/Admisión","Sensor, cableado"),
            ("P0532","Voltaje bajo en el sensor de presión del refrigerante de A/C","Motor - Sensores/Admisión","Cortocircuito a masa, sensor dañado"),
            ("P0533","Voltaje alto en el sensor de presión del refrigerante de A/C","Motor - Sensores/Admisión","Circuito abierto, sensor dañado"),
            ("P0534","Pérdida de carga de refrigerante del A/C","Motor - Sensores/Admisión","Fuga en el circuito de A/C"),
            ("P0560","Falla en el voltaje del sistema","Módulo de control / Eléctrico","Batería, alternador, cableado"),
            ("P0562","Voltaje del sistema bajo","Módulo de control / Eléctrico","Batería descargada, alternador"),
            ("P0563","Voltaje del sistema alto","Módulo de control / Eléctrico","Regulador de tensión, alternador"),
            ("P0602","Módulo de control sin programar","Módulo de control / Eléctrico","Requiere programación con equipo de diagnóstico"),
            ("P0603","Falla en la memoria KAM (no borrable) del módulo de control","Módulo de control / Eléctrico","Módulo de control con falla interna"),
            ("P0604","Falla en la memoria RAM del módulo de control","Módulo de control / Eléctrico","Módulo de control con falla interna"),
            ("P0605","Falla en la memoria ROM del módulo de control","Módulo de control / Eléctrico","Módulo de control con falla interna"),
            ("P0606","Falla en el procesador del módulo de control (PCM)","Módulo de control / Eléctrico","Módulo de control con falla interna"),
            ("P0620","Falla eléctrica en el circuito de control del generador/alternador","Módulo de control / Eléctrico","Alternador, cableado, regulador"),
            ("P0630","VIN no programado o no coincide con el ECM/PCM","Módulo de control / Eléctrico","Requiere reprogramación con equipo de diagnóstico"),
            ("P0650","Falla eléctrica en el circuito de la luz indicadora de fallas (MIL)","Módulo de control / Eléctrico","Bombilla, cableado, módulo"),
            ("P0703","Falla en el circuito del interruptor de freno / convertidor de par B","Transmisión","Interruptor de freno, cableado"),
            ("P0706","Sensor de rango de la transmisión fuera de rango","Transmisión","Sensor PRNDL descalibrado, cableado"),
            ("P0725","Falla en el circuito de entrada de velocidad del motor","Transmisión","Sensor, cableado"),
            ("P0731","Relación de engranes incorrecta en primera marcha","Transmisión","Solenoides de cambio, fluido bajo o degradado"),
            ("P0732","Relación de engranes incorrecta en segunda marcha","Transmisión","Solenoides de cambio, fluido bajo o degradado"),
            ("P0733","Relación de engranes incorrecta en tercera marcha","Transmisión","Solenoides de cambio, fluido bajo o degradado"),
            ("P0734","Relación de engranes incorrecta en cuarta marcha","Transmisión","Solenoides de cambio, fluido bajo o degradado"),
            ("P0743","Problema eléctrico en el embrague del convertidor de par","Transmisión","Solenoide TCC, cableado"),
            ("P0745","Falla en el solenoide de control de presión de la transmisión","Transmisión","Solenoide, cableado, fluido"),
            ("P0760","Falla en el solenoide de cambios C","Transmisión","Solenoide, cableado"),
            ("P0765","Falla en el solenoide de cambios D","Transmisión","Solenoide, cableado"),
            ("P0770","Falla en el solenoide de cambios E","Transmisión","Solenoide, cableado"),
            ("P0850","Falla en el interruptor de posición de estacionamiento/neutro","Transmisión","Interruptor, cableado"),
        ]
        # Y las familias que son una serie —cilindro por cilindro, banco por banco— se arman
        # en vez de copiarse. Ver _dtc_sistematicos().
        seed_dtc = seed_dtc + _dtc_sistematicos()
        c.executemany(
            "INSERT INTO codigos_dtc (codigo, fabricante, descripcion, sistema, causas_posibles) "
            "VALUES (?, '', ?, ?, ?) "
            "ON CONFLICT(codigo, fabricante) DO UPDATE SET descripcion = excluded.descripcion, "
            "sistema = excluded.sistema, causas_posibles = excluded.causas_posibles "
            "WHERE codigos_dtc.editado = 0",
            seed_dtc
        )
        c.execute("INSERT INTO configuracion (clave, valor) VALUES ('semilla_dtc_version', ?) "
                  "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor", (SEMILLA_DTC_VERSION,))

    # Volver a normalizar la columna `busqueda` cuando cambió _sql_sin_acentos().
    # Los triggers arreglan lo que se toca de ahí en adelante, pero las filas ya cargadas se
    # quedan con la normalización vieja y dejan de encontrarse por lo nuevo, sin ningún error a
    # la vista: sobre el catálogo real eran 73 productos —«SENSOR RPM cigüeñal», «CITROËN»,
    # «Conexão»— que no aparecían buscando CIGUENAL ni CITROEN.
    c.execute("SELECT valor FROM configuracion WHERE clave = 'version_normalizacion'")
    _fila_norm = c.fetchone()
    if (_fila_norm["valor"] if _fila_norm else None) != VERSION_NORMALIZACION:
        c.execute("UPDATE productos SET busqueda = "
                  + _sql_sin_acentos("COALESCE(descripcion,'') || ' ' || COALESCE(codigo_raw,'')"
                                      " || ' ' || COALESCE(codigo_barras,'')"))
        c.execute("INSERT INTO configuracion (clave, valor) VALUES ('version_normalizacion', ?) "
                  "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                  (VERSION_NORMALIZACION,))

    # La cola de pendientes, al día con lo que ahora guarda guardar_equivalencias_pendientes().
    # Va acá y no en la tarea de fondo porque es SQL puro sobre una tabla chica: sobre la cola
    # real después de un descubrimiento —22.309 filas— tarda milésimas.
    # El orden importa: primero se borra la vuelta de los pares que tienen la ida, y recién ahí
    # se dan vuelta los que quedaron solos al revés; al revés chocarían con la clave primaria.
    # Lo rechazado y lo ya cargado se saca de la cola por lo mismo que ya no entra: preguntar
    # otra vez por algo que se decidió es hacer que la decisión no sirva.
    c.execute("SELECT valor FROM configuracion WHERE clave = 'version_cola_pendientes'")
    _fila_cola = c.fetchone()
    if (_fila_cola["valor"] if _fila_cola else None) != VERSION_COLA_PENDIENTES:
        c.execute("""DELETE FROM equivalencias_pendientes
                     WHERE producto_a_id > producto_b_id
                       AND EXISTS (SELECT 1 FROM equivalencias_pendientes e2
                                   WHERE e2.producto_a_id = equivalencias_pendientes.producto_b_id
                                     AND e2.producto_b_id = equivalencias_pendientes.producto_a_id)""")
        c.execute("""UPDATE equivalencias_pendientes
                     SET producto_a_id = producto_b_id, producto_b_id = producto_a_id
                     WHERE producto_a_id > producto_b_id""")
        c.execute("DELETE FROM equivalencias_pendientes WHERE producto_a_id = producto_b_id")
        c.execute("""DELETE FROM equivalencias_pendientes
                     WHERE EXISTS (SELECT 1 FROM equivalencias_revisadas r
                                   WHERE r.decision = 'rechazada'
                                     AND r.producto_a_id = equivalencias_pendientes.producto_a_id
                                     AND r.producto_b_id = equivalencias_pendientes.producto_b_id)""")
        c.execute("""DELETE FROM equivalencias_pendientes
                     WHERE EXISTS (SELECT 1 FROM equivalencias e
                                   WHERE (e.producto_a_id = equivalencias_pendientes.producto_a_id
                                          AND e.producto_b_id = equivalencias_pendientes.producto_b_id)
                                      OR (e.producto_a_id = equivalencias_pendientes.producto_b_id
                                          AND e.producto_b_id = equivalencias_pendientes.producto_a_id))""")
        c.execute("""DELETE FROM equivalencias_pendientes
                     WHERE NOT EXISTS (SELECT 1 FROM productos p
                                       WHERE p.id = equivalencias_pendientes.producto_a_id)
                        OR NOT EXISTS (SELECT 1 FROM productos p
                                       WHERE p.id = equivalencias_pendientes.producto_b_id)""")
        c.execute("INSERT INTO configuracion (clave, valor) VALUES ('version_cola_pendientes', ?) "
                  "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                  (VERSION_COLA_PENDIENTES,))

    # Lo mismo para las descripciones que entraron antes de que el separador aprendiera.
    # Ver VERSION_SEPARACION.
    c.execute("SELECT valor FROM configuracion WHERE clave = 'version_separacion'")
    _fila_sep = c.fetchone()
    if (_fila_sep["valor"] if _fila_sep else None) != VERSION_SEPARACION:
        c.execute("INSERT INTO configuracion (clave, valor) VALUES "
                  "('separacion_pendiente', '1') "
                  "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor")
        c.execute("INSERT INTO configuracion (clave, valor) VALUES ('version_separacion', ?) "
                  "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                  (VERSION_SEPARACION,))

    # Lo mismo para la marca del repuesto. Ver VERSION_MARCAS_REPUESTO.
    c.execute("SELECT valor FROM configuracion WHERE clave = 'version_marcas_repuesto'")
    _fila_mr = c.fetchone()
    if (_fila_mr["valor"] if _fila_mr else None) != VERSION_MARCAS_REPUESTO:
        c.execute("INSERT INTO configuracion (clave, valor) VALUES "
                  "('marcas_repuesto_pendientes', '1') "
                  "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor")
        c.execute("INSERT INTO configuracion (clave, valor) VALUES "
                  "('version_marcas_repuesto', ?) "
                  "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                  (VERSION_MARCAS_REPUESTO,))

    # Lo mismo para las aplicaciones. Ver VERSION_APLICACIONES.
    c.execute("SELECT valor FROM configuracion WHERE clave = 'version_aplicaciones'")
    _fila_apl = c.fetchone()
    if (_fila_apl["valor"] if _fila_apl else None) != VERSION_APLICACIONES:
        c.execute("INSERT INTO configuracion (clave, valor) VALUES "
                  "('aplicaciones_pendientes', '1') "
                  "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor")
        c.execute("INSERT INTO configuracion (clave, valor) VALUES ('version_aplicaciones', ?) "
                  "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                  (VERSION_APLICACIONES,))

    # El lector de medidas aprendió algo nuevo: hay que releer las descripciones. Igual que
    # abajo, acá solo se deja pedido. Ver VERSION_MEDIDAS.
    c.execute("SELECT valor FROM configuracion WHERE clave = 'version_medidas'")
    _fila_med = c.fetchone()
    if (_fila_med["valor"] if _fila_med else None) != VERSION_MEDIDAS:
        c.execute("INSERT INTO configuracion (clave, valor) VALUES ('medidas_pendientes', '1') "
                  "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor")
        c.execute("INSERT INTO configuracion (clave, valor) VALUES ('version_medidas', ?) "
                  "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                  (VERSION_MEDIDAS,))

    # Las reglas de confianza cambiaron: lo guardado quedó viejo. Acá solo se DEJA PEDIDO —los
    # 24.774 vínculos tardan 12,8 s y esto corre al abrir la app—; lo hace la tarea de fondo.
    # Ver VERSION_CONFIANZA.
    c.execute("SELECT valor FROM configuracion WHERE clave = 'version_confianza'")
    _fila_conf = c.fetchone()
    if (_fila_conf["valor"] if _fila_conf else None) != VERSION_CONFIANZA:
        c.execute("INSERT INTO configuracion (clave, valor) VALUES ('confianza_pendiente', '1') "
                  "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor")
        c.execute("INSERT INTO configuracion (clave, valor) VALUES ('version_confianza', ?) "
                  "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                  (VERSION_CONFIANZA,))

    # Fabricantes por WMI (los 3 primeros caracteres del VIN) precargados, para no tener que
    # ir cargándolos de a uno. Están los que circulan en Argentina: fabricación nacional,
    # importados de Brasil (mayoría del parque) y las marcas más comunes de otros orígenes.
    # Son editables desde la app: si alguno no coincide, se corrige ahí.
    # Antes esto solo corría con la tabla vacía, así que quien ya tenía la app nunca recibía los
    # WMI nuevos. Ahora se aplica una vez por versión de lista, con INSERT OR IGNORE: lo que vos
    # hayas cargado o corregido a mano NO se pisa nunca.
    c.execute("SELECT valor FROM configuracion WHERE clave = 'semilla_wmi_version'")
    _fila_sem = c.fetchone()
    if (_fila_sem["valor"] if _fila_sem else None) != SEMILLA_WMI_VERSION:
        seed_wmi = [
            # Argentina
            ('8AC', 'Mercedes-Benz Argentina', 'Argentina'),
            ('8AD', 'Peugeot Argentina', 'Argentina'),
            ('8AF', 'Ford Argentina', 'Argentina'),
            ('8AG', 'General Motors / Chevrolet Argentina', 'Argentina'),
            ('8AJ', 'Toyota Argentina', 'Argentina'),
            ('8AK', 'Suzuki Argentina', 'Argentina'),
            ('8AP', 'Fiat Argentina', 'Argentina'),
            ('8AW', 'Volkswagen Argentina', 'Argentina'),
            ('8A1', 'Renault Argentina', 'Argentina'),
            # Brasil
            ('935', 'Citroën Brasil', 'Brasil'),
            ('936', 'Peugeot Brasil', 'Brasil'),
            ('93H', 'Honda Brasil', 'Brasil'),
            ('93R', 'Toyota Brasil', 'Brasil'),
            ('93U', 'Audi Brasil', 'Brasil'),
            ('93V', 'Audi Brasil', 'Brasil'),
            ('93X', 'Mitsubishi Brasil', 'Brasil'),
            ('93Y', 'Renault Brasil', 'Brasil'),
            ('94D', 'Nissan Brasil', 'Brasil'),
            ('9BD', 'Fiat Brasil', 'Brasil'),
            ('9BF', 'Ford Brasil', 'Brasil'),
            ('9BG', 'General Motors / Chevrolet Brasil', 'Brasil'),
            ('9BM', 'Mercedes-Benz Brasil', 'Brasil'),
            ('9BR', 'Toyota Brasil', 'Brasil'),
            ('9BS', 'Scania Brasil', 'Brasil'),
            ('9BW', 'Volkswagen Brasil', 'Brasil'),
            # Chile
            ('8GD', 'Peugeot Chile', 'Chile'),
            ('8GG', 'Chevrolet Chile', 'Chile'),
            # Colombia
            ('9FB', 'Renault Colombia', 'Colombia'),
            # México
            ('3C4', 'Chrysler México', 'México'),
            ('3D3', 'Dodge México', 'México'),
            ('3FA', 'Ford México', 'México'),
            ('3FE', 'Ford México', 'México'),
            ('3G', 'General Motors México', 'México'),
            ('3H', 'Honda México', 'México'),
            ('3MZ', 'Mazda México', 'México'),
            ('3N', 'Nissan México', 'México'),
            ('3P3', 'Plymouth México', 'México'),
            ('3VW', 'Volkswagen México', 'México'),
            # Estados Unidos
            ('1B3', 'Dodge', 'Estados Unidos'),
            ('1C3', 'Chrysler', 'Estados Unidos'),
            ('1C6', 'Chrysler', 'Estados Unidos'),
            ('1D3', 'Dodge', 'Estados Unidos'),
            ('1FA', 'Ford', 'Estados Unidos'),
            ('1FB', 'Ford', 'Estados Unidos'),
            ('1FC', 'Ford', 'Estados Unidos'),
            ('1FD', 'Ford', 'Estados Unidos'),
            ('1FM', 'Ford (SUV)', 'Estados Unidos'),
            ('1FT', 'Ford (camionetas)', 'Estados Unidos'),
            ('1FU', 'Freightliner', 'Estados Unidos'),
            ('1FV', 'Freightliner', 'Estados Unidos'),
            ('1G', 'General Motors', 'Estados Unidos'),
            ('1GC', 'Chevrolet (camionetas)', 'Estados Unidos'),
            ('1GT', 'GMC (camionetas)', 'Estados Unidos'),
            ('1G1', 'Chevrolet', 'Estados Unidos'),
            ('1G2', 'Pontiac', 'Estados Unidos'),
            ('1G3', 'Oldsmobile', 'Estados Unidos'),
            ('1G4', 'Buick', 'Estados Unidos'),
            ('1G6', 'Cadillac', 'Estados Unidos'),
            ('1G8', 'Saturn', 'Estados Unidos'),
            ('1GM', 'Pontiac', 'Estados Unidos'),
            ('1GY', 'Cadillac', 'Estados Unidos'),
            ('1H', 'Honda', 'Estados Unidos'),
            ('1HD', 'Harley-Davidson (motos)', 'Estados Unidos'),
            ('1J4', 'Jeep', 'Estados Unidos'),
            ('1L', 'Lincoln', 'Estados Unidos'),
            ('1ME', 'Mercury', 'Estados Unidos'),
            ('1M1', 'Mack (camiones)', 'Estados Unidos'),
            ('1M2', 'Mack (camiones)', 'Estados Unidos'),
            ('1M3', 'Mack (camiones)', 'Estados Unidos'),
            ('1M4', 'Mack (camiones)', 'Estados Unidos'),
            ('1N', 'Nissan', 'Estados Unidos'),
            ('1NX', 'NUMMI (Toyota/GM)', 'Estados Unidos'),
            ('1P3', 'Plymouth', 'Estados Unidos'),
            ('1VW', 'Volkswagen', 'Estados Unidos'),
            ('1XK', 'Kenworth (camiones)', 'Estados Unidos'),
            ('1XP', 'Peterbilt (camiones)', 'Estados Unidos'),
            ('1YV', 'Mazda (AutoAlliance)', 'Estados Unidos'),
            ('1ZV', 'Ford (AutoAlliance)', 'Estados Unidos'),
            ('4F', 'Mazda', 'Estados Unidos'),
            ('4JG', 'Mercedes-Benz', 'Estados Unidos'),
            ('4M', 'Mercury', 'Estados Unidos'),
            ('4S', 'Subaru-Isuzu', 'Estados Unidos'),
            ('4T', 'Toyota', 'Estados Unidos'),
            ('4US', 'BMW', 'Estados Unidos'),
            ('4V1', 'Volvo (camiones)', 'Estados Unidos'),
            ('4V2', 'Volvo (camiones)', 'Estados Unidos'),
            ('4V4', 'Volvo (camiones)', 'Estados Unidos'),
            ('5F', 'Honda (Alabama)', 'Estados Unidos'),
            ('5L', 'Lincoln', 'Estados Unidos'),
            ('5N1', 'Nissan', 'Estados Unidos'),
            ('5NP', 'Hyundai', 'Estados Unidos'),
            ('5T', 'Toyota (camionetas)', 'Estados Unidos'),
            ('5YJ', 'Tesla', 'Estados Unidos'),
            ('538', 'Zero Motorcycles (motos)', 'Estados Unidos'),
            # Canadá
            ('2A4', 'Chrysler Canadá', 'Canadá'),
            ('2B3', 'Dodge Canadá', 'Canadá'),
            ('2B7', 'Dodge Canadá', 'Canadá'),
            ('2C3', 'Chrysler Canadá', 'Canadá'),
            ('2CN', 'CAMI (GM/Suzuki)', 'Canadá'),
            ('2D3', 'Dodge Canadá', 'Canadá'),
            ('2FA', 'Ford Canadá', 'Canadá'),
            ('2FB', 'Ford Canadá', 'Canadá'),
            ('2FC', 'Ford Canadá', 'Canadá'),
            ('2FM', 'Ford Canadá', 'Canadá'),
            ('2FT', 'Ford Canadá (camionetas)', 'Canadá'),
            ('2G', 'General Motors Canadá', 'Canadá'),
            ('2G1', 'Chevrolet Canadá', 'Canadá'),
            ('2G2', 'Pontiac Canadá', 'Canadá'),
            ('2G3', 'Oldsmobile Canadá', 'Canadá'),
            ('2G4', 'Buick Canadá', 'Canadá'),
            ('2HG', 'Honda Canadá', 'Canadá'),
            ('2HK', 'Honda Canadá', 'Canadá'),
            ('2HJ', 'Honda Canadá', 'Canadá'),
            ('2HM', 'Hyundai Canadá', 'Canadá'),
            ('2M', 'Mercury Canadá', 'Canadá'),
            ('2T', 'Toyota Canadá', 'Canadá'),
            ('2V4', 'Volkswagen Canadá', 'Canadá'),
            ('2V8', 'Volkswagen Canadá', 'Canadá'),
            # Alemania
            ('WAG', 'Neoplan (ómnibus)', 'Alemania'),
            ('WAU', 'Audi', 'Alemania'),
            ('WA1', 'Audi (SUV)', 'Alemania'),
            ('WBA', 'BMW', 'Alemania'),
            ('WBS', 'BMW M', 'Alemania'),
            ('WDA', 'Daimler', 'Alemania'),
            ('WDB', 'Mercedes-Benz', 'Alemania'),
            ('WDC', 'DaimlerChrysler', 'Alemania'),
            ('WDD', 'Mercedes-Benz', 'Alemania'),
            ('WDF', 'Mercedes-Benz (comerciales)', 'Alemania'),
            ('WEB', 'Evobus (ómnibus Mercedes)', 'Alemania'),
            ('WJM', 'Iveco Magirus', 'Alemania'),
            ('WF0', 'Ford Alemania', 'Alemania'),
            ('WMA', 'MAN (camiones)', 'Alemania'),
            ('WME', 'smart', 'Alemania'),
            ('WMW', 'MINI', 'Alemania'),
            ('WMX', 'Mercedes-AMG', 'Alemania'),
            ('WP0', 'Porsche', 'Alemania'),
            ('WP1', 'Porsche (SUV)', 'Alemania'),
            ('W0L', 'Opel', 'Alemania'),
            ('WUA', 'quattro GmbH (Audi)', 'Alemania'),
            ('WVG', 'Volkswagen (SUV/monovolumen)', 'Alemania'),
            ('WVW', 'Volkswagen', 'Alemania'),
            ('WV1', 'Volkswagen Comerciales', 'Alemania'),
            ('WV2', 'Volkswagen (furgones)', 'Alemania'),
            ('WV3', 'Volkswagen (camiones)', 'Alemania'),
            # Francia
            ('VF1', 'Renault', 'Francia'),
            ('VF2', 'Renault', 'Francia'),
            ('VF3', 'Peugeot', 'Francia'),
            ('VF4', 'Talbot', 'Francia'),
            ('VF6', 'Renault (camiones y ómnibus)', 'Francia'),
            ('VF7', 'Citroën', 'Francia'),
            ('VF8', 'Matra', 'Francia'),
            ('VLU', 'Scania Francia', 'Francia'),
            ('VN1', 'SOVAB (Renault)', 'Francia'),
            ('VNE', 'Irisbus', 'Francia'),
            ('VNK', 'Toyota Francia', 'Francia'),
            ('VNV', 'Renault-Nissan', 'Francia'),
            # España
            ('VSA', 'Mercedes-Benz España', 'España'),
            ('VSE', 'Suzuki España (Santana)', 'España'),
            ('VSK', 'Nissan España', 'España'),
            ('VSS', 'SEAT', 'España'),
            ('VSX', 'Opel España', 'España'),
            ('VS6', 'Ford España', 'España'),
            ('VS7', 'Citroën España', 'España'),
            ('VWA', 'Nissan España', 'España'),
            ('VWV', 'Volkswagen España', 'España'),
            # Italia
            ('ZAM', 'Maserati', 'Italia'),
            ('ZAP', 'Piaggio / Vespa / Gilera (motos)', 'Italia'),
            ('ZAR', 'Alfa Romeo', 'Italia'),
            ('ZCF', 'Iveco', 'Italia'),
            ('ZCG', 'Cagiva / MV Agusta (motos)', 'Italia'),
            ('ZDM', 'Ducati (motos)', 'Italia'),
            ('ZD4', 'Aprilia (motos)', 'Italia'),
            ('ZFA', 'Fiat', 'Italia'),
            ('ZFC', 'Fiat Veicoli Industriali', 'Italia'),
            ('ZFF', 'Ferrari', 'Italia'),
            ('ZGU', 'Moto Guzzi (motos)', 'Italia'),
            ('ZHW', 'Lamborghini', 'Italia'),
            ('ZLA', 'Lancia', 'Italia'),
            # Reino Unido
            ('SAL', 'Land Rover', 'Reino Unido'),
            ('SAJ', 'Jaguar', 'Reino Unido'),
            ('SAR', 'Rover', 'Reino Unido'),
            ('SB1', 'Toyota Reino Unido', 'Reino Unido'),
            ('SBM', 'McLaren', 'Reino Unido'),
            ('SCA', 'Rolls-Royce', 'Reino Unido'),
            ('SCB', 'Bentley', 'Reino Unido'),
            ('SCC', 'Lotus', 'Reino Unido'),
            ('SCF', 'Aston Martin', 'Reino Unido'),
            ('SDB', 'Peugeot Reino Unido', 'Reino Unido'),
            ('SFA', 'Ford Reino Unido', 'Reino Unido'),
            ('SHH', 'Honda Reino Unido', 'Reino Unido'),
            ('SHS', 'Honda Reino Unido', 'Reino Unido'),
            ('SJN', 'Nissan Reino Unido', 'Reino Unido'),
            ('SKF', 'Vauxhall', 'Reino Unido'),
            ('SMT', 'Triumph (motos)', 'Reino Unido'),
            # República Checa
            ('TMA', 'Hyundai República Checa', 'República Checa'),
            ('TMB', 'Škoda', 'República Checa'),
            ('TMT', 'Tatra (camiones)', 'República Checa'),
            # Hungría
            ('TRU', 'Audi Hungría', 'Hungría'),
            ('TSM', 'Suzuki Hungría', 'Hungría'),
            # Portugal
            ('TW1', 'Toyota Caetano', 'Portugal'),
            # Polonia
            ('SUF', 'Fiat Polonia', 'Polonia'),
            ('SUP', 'FSO-Daewoo', 'Polonia'),
            # Rumania
            ('UU1', 'Renault Dacia', 'Rumania'),
            # Eslovaquia
            ('U5Y', 'Kia Eslovaquia', 'Eslovaquia'),
            ('U6Y', 'Kia Eslovaquia', 'Eslovaquia'),
            # Austria
            ('VAG', 'Magna Steyr Puch', 'Austria'),
            ('VAN', 'MAN Austria', 'Austria'),
            ('VBK', 'KTM (motos)', 'Austria'),
            # Países Bajos
            ('XLB', 'Volvo (NedCar)', 'Países Bajos'),
            ('XLE', 'Scania Países Bajos', 'Países Bajos'),
            ('XLR', 'DAF (camiones)', 'Países Bajos'),
            ('XMC', 'Mitsubishi (NedCar)', 'Países Bajos'),
            # Bélgica
            ('YBW', 'Volkswagen Bélgica', 'Bélgica'),
            ('YCM', 'Mazda Bélgica', 'Bélgica'),
            # Suecia
            ('YS2', 'Scania (camiones)', 'Suecia'),
            ('YS3', 'Saab', 'Suecia'),
            ('YS4', 'Scania (ómnibus)', 'Suecia'),
            ('YV1', 'Volvo', 'Suecia'),
            ('YV4', 'Volvo', 'Suecia'),
            ('YV2', 'Volvo (camiones)', 'Suecia'),
            ('YV3', 'Volvo (ómnibus)', 'Suecia'),
            # Rusia
            ('XTA', 'Lada / AvtoVAZ', 'Rusia'),
            ('XTT', 'UAZ', 'Rusia'),
            ('X7L', 'Renault Rusia', 'Rusia'),
            # Serbia
            ('VX1', 'Zastava / Yugo', 'Serbia'),
            # Turquía
            ('NM0', 'Ford Turquía', 'Turquía'),
            ('NM4', 'Tofaş (Fiat Turquía)', 'Turquía'),
            ('NMT', 'Toyota Turquía', 'Turquía'),
            ('NLH', 'Hyundai Turquía', 'Turquía'),
            ('NLE', 'Mercedes-Benz Turquía (camiones)', 'Turquía'),
            # Japón
            ('JA', 'Isuzu', 'Japón'),
            ('JA3', 'Mitsubishi', 'Japón'),
            ('JA4', 'Mitsubishi', 'Japón'),
            ('JD', 'Daihatsu', 'Japón'),
            ('JF', 'Subaru', 'Japón'),
            ('JH', 'Honda', 'Japón'),
            ('JK', 'Kawasaki (motos)', 'Japón'),
            ('JL5', 'Mitsubishi Fuso (camiones)', 'Japón'),
            ('JMB', 'Mitsubishi', 'Japón'),
            ('JMY', 'Mitsubishi', 'Japón'),
            ('JMZ', 'Mazda', 'Japón'),
            ('JN', 'Nissan', 'Japón'),
            ('JS', 'Suzuki', 'Japón'),
            ('JT', 'Toyota', 'Japón'),
            ('JY', 'Yamaha (motos)', 'Japón'),
            # Corea del Sur
            ('KL', 'Daewoo / GM Corea', 'Corea del Sur'),
            ('KM', 'Hyundai', 'Corea del Sur'),
            ('KN', 'Kia', 'Corea del Sur'),
            ('KNM', 'Renault Samsung', 'Corea del Sur'),
            ('KPA', 'SsangYong', 'Corea del Sur'),
            ('KPT', 'SsangYong', 'Corea del Sur'),
            ('KM1', 'Hyosung (motos)', 'Corea del Sur'),
            ('KMY', 'Daelim (motos)', 'Corea del Sur'),
            # China
            ('LBE', 'Beijing Hyundai', 'China'),
            ('LDC', 'Dongfeng Peugeot Citroën', 'China'),
            ('LE4', 'Beijing Benz', 'China'),
            ('LFP', 'FAW', 'China'),
            ('LFV', 'FAW-Volkswagen', 'China'),
            ('LGB', 'Dongfeng', 'China'),
            ('LGX', 'BYD', 'China'),
            ('LJC', 'JAC', 'China'),
            ('LJ1', 'JAC', 'China'),
            ('LSG', 'Shanghai General Motors', 'China'),
            ('LSJ', 'MG / SAIC', 'China'),
            ('LSV', 'Shanghai Volkswagen', 'China'),
            ('LSY', 'Brilliance', 'China'),
            ('LTV', 'Toyota Tianjin', 'China'),
            ('LUC', 'GAC Honda', 'China'),
            ('LVS', 'Ford Chang An', 'China'),
            ('LVV', 'Chery', 'China'),
            ('LVZ', 'DFSK (Dongfeng Sokon)', 'China'),
            ('LZM', 'MAN China', 'China'),
            ('LZE', 'Isuzu Guangzhou', 'China'),
            ('LZG', 'Shaanxi (camiones)', 'China'),
            ('LZY', 'Yutong (ómnibus)', 'China'),
            ('LBB', 'Zhejiang Qianjiang / Keeway (motos)', 'China'),
            ('LCE', 'CFMOTO (motos)', 'China'),
            # India
            ('MAB', 'Mahindra', 'India'),
            ('MAC', 'Mahindra', 'India'),
            ('MA1', 'Mahindra', 'India'),
            ('MAJ', 'Ford India', 'India'),
            ('MAK', 'Honda India', 'India'),
            ('MAL', 'Hyundai India', 'India'),
            ('MAT', 'Tata', 'India'),
            ('MA3', 'Suzuki India (Maruti)', 'India'),
            ('MBH', 'Suzuki India (Maruti)', 'India'),
            ('MBJ', 'Toyota India', 'India'),
            ('MBR', 'Mercedes-Benz India', 'India'),
            ('MB1', 'Ashok Leyland', 'India'),
            ('MCA', 'Fiat India', 'India'),
            ('MDH', 'Nissan India', 'India'),
            ('MD2', 'Bajaj (motos)', 'India'),
            ('MEE', 'Renault India', 'India'),
            ('MEX', 'Volkswagen India', 'India'),
            # Indonesia
            ('MHF', 'Toyota Indonesia', 'Indonesia'),
            ('MHR', 'Honda Indonesia', 'Indonesia'),
            # Tailandia
            ('MLC', 'Suzuki Tailandia', 'Tailandia'),
            ('MLH', 'Honda Tailandia', 'Tailandia'),
            ('MMB', 'Mitsubishi Tailandia', 'Tailandia'),
            ('MMC', 'Mitsubishi Tailandia', 'Tailandia'),
            ('MMM', 'Chevrolet Tailandia', 'Tailandia'),
            ('MMT', 'Mitsubishi Tailandia', 'Tailandia'),
            ('MM8', 'Mazda Tailandia', 'Tailandia'),
            ('MNB', 'Ford Tailandia', 'Tailandia'),
            ('MNT', 'Nissan Tailandia', 'Tailandia'),
            ('MPA', 'Isuzu Tailandia', 'Tailandia'),
            ('MP1', 'Isuzu Tailandia', 'Tailandia'),
            ('MRH', 'Honda Tailandia', 'Tailandia'),
            ('MR0', 'Toyota Tailandia', 'Tailandia'),
            # Malasia
            ('PL1', 'Proton', 'Malasia'),
            # Filipinas
            ('PE1', 'Ford Filipinas', 'Filipinas'),
            ('PE3', 'Mazda Filipinas', 'Filipinas'),
            # Taiwán
            ('RFB', 'Kymco (motos)', 'Taiwán'),
            ('RFG', 'SYM (motos)', 'Taiwán'),
            # Sudáfrica
            ('AAV', 'Volkswagen Sudáfrica', 'Sudáfrica'),
            ('AC5', 'Hyundai Sudáfrica', 'Sudáfrica'),
            ('ADD', 'Hyundai Sudáfrica', 'Sudáfrica'),
            ('AFA', 'Ford Sudáfrica', 'Sudáfrica'),
            ('AHT', 'Toyota Sudáfrica', 'Sudáfrica'),
            # Australia
            ('6AB', 'MAN Australia', 'Australia'),
            ('6F4', 'Nissan Australia', 'Australia'),
            ('6F5', 'Kenworth Australia', 'Australia'),
            ('6FP', 'Ford Australia', 'Australia'),
            ('6G1', 'Holden (GM)', 'Australia'),
            ('6G2', 'Pontiac Australia', 'Australia'),
            ('6H8', 'Holden (GM)', 'Australia'),
            ('6MM', 'Mitsubishi Australia', 'Australia'),
            ('6T1', 'Toyota Australia', 'Australia'),
            # --- Agregados en la versión 3 de la semilla ---
            # Los que faltaban de marcas que sí circulan acá, y los WMI nuevos que las marcas
            # estrenaron en los últimos años (Mercedes W1K/W1N/W1V, BMW i, PSA VR3/VR7).
            # Solo van los que se pueden dar por seguros: un WMI equivocado hace que la app
            # afirme una marca que no es, y eso es peor que no saberla.
            ('19U', 'Acura', 'Estados Unidos'),
            ('19X', 'Honda', 'Estados Unidos'),
            ('5FN', 'Honda (SUV/monovolumen)', 'Estados Unidos'),
            ('5J6', 'Honda (SUV)', 'Estados Unidos'),
            ('5XY', 'Kia (SUV)', 'Estados Unidos'),
            ('7SA', 'Tesla', 'Estados Unidos'),
            ('JM1', 'Mazda', 'Japón'),
            ('LGW', 'Great Wall / Haval', 'China'),
            ('LRW', 'Tesla China', 'China'),
            ('LYV', 'Volvo China', 'China'),
            ('LZW', 'SAIC-GM-Wuling', 'China'),
            ('MNA', 'Ford Tailandia', 'Tailandia'),
            ('VR1', 'DS Automobiles', 'Francia'),
            ('VR3', 'Peugeot', 'Francia'),
            ('VR7', 'Citroën', 'Francia'),
            ('W1K', 'Mercedes-Benz', 'Alemania'),
            ('W1N', 'Mercedes-Benz (SUV)', 'Alemania'),
            ('W1V', 'Mercedes-Benz (utilitarios)', 'Alemania'),
            ('WB1', 'BMW Motorrad', 'Alemania'),
            ('WBY', 'BMW i', 'Alemania'),
        ]
        c.executemany(
            "INSERT OR IGNORE INTO fabricantes_vin (wmi, fabricante, pais) VALUES (?, ?, ?)",
            seed_wmi
        )
        c.execute("INSERT INTO configuracion (clave, valor) VALUES ('semilla_wmi_version', ?) "
                  "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor", (SEMILLA_WMI_VERSION,))

    columnas_equiv = [f[1] for f in c.execute("PRAGMA table_info(equivalencias)").fetchall()]
    if "verificada" not in columnas_equiv:
        c.execute("ALTER TABLE equivalencias ADD COLUMN verificada INTEGER DEFAULT 0")
    if "nivel" not in columnas_equiv:
        c.execute("ALTER TABLE equivalencias ADD COLUMN nivel TEXT DEFAULT 'Exacta'")
    if "nota" not in columnas_equiv:
        c.execute("ALTER TABLE equivalencias ADD COLUMN nota TEXT")
    # De qué importación salió cada vínculo. Antes se perdía: el lote solo existía mientras la
    # equivalencia estaba pendiente, y al aprobarla quedaba huérfana. Así no había manera de
    # responder "¿de dónde salió esto?" ni de deshacer una lista que resultó estar mal cargada
    # — la única salida era borrar de a uno, a mano, entre miles.
    if "lote" not in columnas_equiv:
        c.execute("ALTER TABLE equivalencias ADD COLUMN lote TEXT")
    c.execute("CREATE INDEX IF NOT EXISTS idx_eq_lote ON equivalencias(lote)")
    # Confianza guardada de cada vínculo. Se calcula una vez y queda, para que el buscador pueda
    # arrastrarla por la cadena sin recalcular nada en cada búsqueda.
    if "confianza" not in columnas_equiv:
        c.execute("ALTER TABLE equivalencias ADD COLUMN confianza INTEGER")

    # Códigos con muchos vínculos que YA revisaste y están bien. Hay repuestos que legítimamente
    # equivalen a decenas: un filtro común, una bujía que va en media gama. Sin esta lista, esos
    # códigos aparecían como problema en cada revisión y no había forma de sacarlos del aviso.
    # Códigos que el fabricante reemplazó por otros. NO es una equivalencia común: tiene
    # dirección. El viejo se deja de fabricar y el nuevo lo reemplaza, pero no al revés.
    c.execute("""CREATE TABLE IF NOT EXISTS reemplazos_codigo (
        codigo_viejo TEXT NOT NULL,
        codigo_viejo_clean TEXT NOT NULL,
        codigo_nuevo TEXT NOT NULL,
        codigo_nuevo_clean TEXT NOT NULL,
        marca TEXT,
        nota TEXT,
        cargado_por TEXT,
        fecha TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (codigo_viejo_clean, codigo_nuevo_clean)
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_reemp_viejo ON reemplazos_codigo(codigo_viejo_clean)")

    c.execute("""CREATE TABLE IF NOT EXISTS puentes_aprobados (
        producto_id INTEGER PRIMARY KEY REFERENCES productos(id) ON DELETE CASCADE,
        aprobado_por TEXT,
        nota TEXT,
        fecha TEXT DEFAULT (datetime('now'))
    )""")

    columnas_historial = [f[1] for f in c.execute("PRAGMA table_info(historial_busquedas)").fetchall()]
    if "sin_resultado" not in columnas_historial:
        c.execute("ALTER TABLE historial_busquedas ADD COLUMN sin_resultado INTEGER DEFAULT 0")

    c.execute("CREATE INDEX IF NOT EXISTS idx_codigo_clean ON productos(codigo_clean)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_marca_id ON productos(marca_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_eq_a ON equivalencias(producto_a_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_eq_b ON equivalencias(producto_b_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_vehiculo_patente ON vehiculos(patente)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_historial_vehiculo ON historial_piezas(vehiculo_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_auditoria_fecha ON auditoria_diaria(fecha)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_dtc_codigo ON codigos_dtc(codigo)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_vin_wmi ON fabricantes_vin(wmi)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_esquema_puntos ON esquema_puntos(esquema_id)")
    # Índices de las tablas más nuevas — se consultan seguido y no los tenían
    c.execute("CREATE INDEX IF NOT EXISTS idx_hist_busq_usuario ON historial_busquedas(usuario)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_hist_precios_prod ON historial_precios(producto_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pedidos_repo_estado ON pedidos_reposicion(estado)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_uso_ia_fecha ON uso_ia(fecha)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_presup_mecanico ON presupuestos_mecanico(mecanico_id)")


def crear_esquema(c):
    _esquema_catalogo(c)
    _esquema_mostrador(c)
    _esquema_fotos(c)
    _esquema_vehiculos_y_mecanico(c)
    _esquema_gestion(c)
    _datos_precargados_y_migraciones(c)




@st.cache_resource
def get_connection():
    """Conexión única y persistente entre reruns de Streamlit."""
    # isolation_level=None => autocommit: cada sentencia se confirma sola.
    #
    # Es importante y no es un detalle técnico. La conexión es UNA SOLA compartida por todos los
    # que usan la app al mismo tiempo (así la deja @st.cache_resource). Con el modo por defecto,
    # Python abre una transacción implícita y la deja abierta hasta el commit, así que las
    # operaciones de dos personas se mezclan en la MISMA transacción:
    #   · si uno confirma, confirma también la importación a medio hacer del otro;
    #   · y peor: si uno cancela, se pierde el trabajo que el otro ya había guardado.
    # Con autocommit eso no puede pasar. Donde hace falta que varias sentencias sean una sola
    # cosa, se usa el bloque transaccion() de abajo.
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # mejor concurrencia / menos bloqueos
    conn.execute("PRAGMA busy_timeout = 8000")  # esperar en vez de fallar si otro está escribiendo
    # No hace falta agrupar las importaciones en una transacción explícita para compensar: se
    # midió la importación real de 10.000 filas en los dos modos y tarda lo mismo (0,33 s contra
    # 0,36 s), porque en modo WAL confirmar es barato.
    # Si el disco se borró (pasa al redesplegar), recuperar desde la copia del repositorio.
    # Va antes de crear las tablas: después las migraciones ponen al día el esquema.
    st.session_state["_restaurado_de_semilla"] = _restaurar_desde_semilla(conn)
    c = conn.cursor()
    crear_esquema(c)
    conn.commit()
    return conn


# Se llama una vez para crear las tablas y correr las migraciones. La conexión que devuelve
# no se usa después: cada hilo abre la suya con el proxy de abajo.
get_connection()


class _ConexionPorSesion:
    """Una conexión propia para cada sesión, detrás de los mismos nombres `conn` y `c`.

    La app usaba UNA conexión y UN cursor compartidos por todos. Con un solo empleado no se
    nota; con dos usando la app a la vez, el proceso se cae con segmentation fault. Está
    medido: dos hilos consultando en paralelo sobre un cursor compartido revientan.

    Se probaron las dos alternativas con cuatro hilos haciendo 400 consultas cada uno:

        conexión compartida + cursor por hilo  ->  2 resultados cruzados
        conexión por hilo                      ->  0 fallos

    Por eso va conexión por hilo. Streamlit atiende cada sesión en su propio hilo, así que en
    la práctica es una conexión por sesión.

    Se arregla acá y no en las 400 consultas que usan `c`: estos objetos se llaman igual y se
    usan igual. Ningún otro código cambia. Es a propósito — tocar 400 lugares para esto es
    pedir un error tonto.
    """

    def __init__(self, ruta, al_crear=None):
        self._ruta = ruta
        self._al_crear = al_crear
        self._local = threading.local()

    @property
    def _real(self):
        propia = getattr(self._local, "conn", None)
        if propia is None:
            propia = sqlite3.connect(self._ruta, check_same_thread=False,
                                     isolation_level=None)
            propia.row_factory = sqlite3.Row
            # Los mismos PRAGMA en cada conexión: no se heredan, son por conexión.
            propia.execute("PRAGMA foreign_keys = ON")
            propia.execute("PRAGMA journal_mode = WAL")
            propia.execute("PRAGMA busy_timeout = 8000")
            self._local.conn = propia
            if self._al_crear:
                self._al_crear(propia)
        return propia

    def conexion_real(self):
        """La sqlite3.Connection de esta sesión, para las pocas APIs que no aceptan el proxy.

        backup() es una de ellas: pide una sqlite3.Connection de verdad como destino y con el
        proxy tira «TypeError: backup() argument 'target' must be sqlite3.Connection». Existe
        este método —y no se accede a _real desde afuera— para que quede escrito dónde y por
        qué se sale del proxy."""
        return self._real

    def cursor(self):
        return self._real.cursor()

    def execute(self, *a, **kw):
        return self._real.execute(*a, **kw)

    def executemany(self, *a, **kw):
        return self._real.executemany(*a, **kw)

    def executescript(self, *a, **kw):
        return self._real.executescript(*a, **kw)

    def commit(self):
        return self._real.commit()

    def rollback(self):
        return self._real.rollback()

    def close(self):
        propia = getattr(self._local, "conn", None)
        if propia is not None:
            propia.close()
            self._local.conn = None

    def backup(self, *a, **kw):
        return self._real.backup(*a, **kw)

    def iterdump(self):
        return self._real.iterdump()

    @property
    def row_factory(self):
        return self._real.row_factory

    @row_factory.setter
    def row_factory(self, valor):
        self._real.row_factory = valor

    @property
    def total_changes(self):
        return self._real.total_changes


class _CursorPorSesion:
    """El cursor de la conexión de esta sesión, detrás del nombre `c` de siempre."""

    def __init__(self, conexion):
        self._conexion = conexion
        self._local = threading.local()

    @property
    def _cursor(self):
        propio = getattr(self._local, "cursor", None)
        # Si la conexión del hilo se cerró y se rehízo, el cursor viejo ya no sirve
        if propio is None or getattr(self._local, "conn", None) is not self._conexion._real:
            propio = self._conexion.cursor()
            self._local.cursor = propio
            self._local.conn = self._conexion._real
        return propio

    def execute(self, *a, **kw):
        return self._cursor.execute(*a, **kw)

    def executemany(self, *a, **kw):
        return self._cursor.executemany(*a, **kw)

    def executescript(self, *a, **kw):
        return self._cursor.executescript(*a, **kw)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def fetchmany(self, *a, **kw):
        return self._cursor.fetchmany(*a, **kw)

    def __iter__(self):
        return iter(self._cursor)

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    @property
    def description(self):
        return self._cursor.description


# La conexión que devuelve get_connection() ya creó las tablas y corrió las migraciones. A
# partir de acá, cada hilo abre la suya contra el mismo archivo.
conn = _ConexionPorSesion(DB_PATH)
c = _CursorPorSesion(conn)


# ============================================================
# TODO O NADA: operaciones que son de varias sentencias
# ============================================================
@contextlib.contextmanager
def transaccion():
    """Varias sentencias que tienen que valer TODAS o NINGUNA.

    La conexión está en autocommit (ver get_connection): cada sentencia se confirma sola. Eso
    está bien para el 95% de la app —una consulta, un alta suelta— pero es un problema serio
    cuando una operación necesita varios pasos, porque si se corta en el medio los pasos que
    ya pasaron quedan guardados igual.

    No es teoría. Está medido cortando la operación a propósito en una base de prueba:

      · cerrar_reserva() descuenta el stock y DESPUÉS marca la reserva como vendida. Si se
        corta en el medio, el stock bajó pero la reserva sigue «activa»: el empleado la ve
        ahí, vuelve a cerrarla, y una reserva de 3 unidades descuenta 6. Stock inventado,
        en silencio, y encima al revés de como conviene (dice que hay menos de lo que hay).
      · fusionar_productos() pasa los vínculos al que queda, borra los del que se va y recién
        entonces borra el producto. Cortado antes del último paso, el producto duplicado
        sigue existiendo pero ya sin ninguna equivalencia: se perdieron y nadie avisó.

    Con este bloque, SQLite deshace sola la parte hecha y la base queda como estaba.

    Detalles de por qué está escrito así:

      · BEGIN IMMEDIATE y no BEGIN a secas: pide el candado de escritura desde el principio.
        Con BEGIN normal, SQLite lo pide recién en la primera escritura, y si en ese momento
        está ocupado la operación se cae a mitad de camino. Pidiéndolo antes, el busy_timeout
        de 8 segundos hace lo que uno espera: esperar el turno.
      · si ya hay una transacción abierta, este bloque no abre otra (SQLite no las anida) y
        deja que decida el de afuera. Así una función que la usa puede llamar a otra que
        también la usa sin romperse.
      · el COMMIT del final está condicionado a que la transacción siga abierta, porque algún
        conn.commit() suelto adentro del bloque la cierra antes; sin el condicional saltaría
        «cannot commit - no transaction is active».
      · NO toma db_lock a propósito: varias funciones ya hacen `with db_lock:` por fuera, y
        db_lock no es reentrante — tomarlo acá las colgaría.
      · atrapa BaseException y no Exception: un st.rerun() adentro del bloque es una excepción
        que no hereda de Exception, y sin esto se iría con la transacción abierta.
    """
    conexion = conn.conexion_real()
    if conexion.in_transaction:
        yield            # ya estamos adentro de otra: manda la de afuera
        return
    conexion.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        if conexion.in_transaction:
            try:
                conexion.execute("ROLLBACK")
            except sqlite3.Error:
                pass   # el error de arriba es el que hay que ver, no el de deshacer
        raise
    if conexion.in_transaction:
        conexion.execute("COMMIT")

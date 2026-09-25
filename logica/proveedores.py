"""El catálogo web del proveedor y las tandas que corren solas en segundo plano.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================================================
# CATÁLOGO WEB DEL PROVEEDOR (fotos y equivalencias)
# ============================================================================================
def descargar_imagen(url, tiempo_maximo=12, tamano_maximo_mb=8):
    """Baja una imagen de una dirección web. Devuelve (bytes, error)."""
    import requests
    try:
        respuesta = requests.get(url, timeout=tiempo_maximo, stream=True,
                                  headers={"User-Agent": "Mozilla/5.0 (compatible; EquivalenciasElChavo/1.0)"})
        if respuesta.status_code != 200:
            return None, f"respondió {respuesta.status_code}"
        tipo = respuesta.headers.get("Content-Type", "")
        if "image" not in tipo.lower():
            return None, "la dirección no devuelve una imagen"
        datos = b""
        for bloque in respuesta.iter_content(65536):
            datos += bloque
            if len(datos) > tamano_maximo_mb * 1024 * 1024:
                return None, "la imagen pesa demasiado"
        return datos, None
    except Exception as e:
        anotar_error("descargar_imagen", e)
        return None, type(e).__name__


def config_portal(nombre_marca):
    """Datos para entrar al portal de un proveedor. Salen de los secretos de Streamlit.

    Va en los secretos y no en la base por una razón concreta: la base se baja como backup y
    se sube a GitHub. Una contraseña ahí queda publicada. En los secretos no se descarga con
    el backup ni se ve desde la app.

    Formato en Settings → Secrets:

        [portal_FISPA]
        url_login   = "https://proveedor.com/login"
        usuario     = "tu_usuario"
        clave       = "tu_clave"
        campo_usuario = "email"       # el name= del input, mirá el formulario
        campo_clave   = "password"
        url_ficha   = "https://proveedor.com/producto/{codigo}"
    """
    try:
        secretos = secretos_app()
        cfg = secretos.get(f"portal_{(nombre_marca or '').strip().upper()}")
    except Exception as _err:
        anotar_error("config_portal", _err)
        return None
    if not cfg:
        return None
    try:
        datos = dict(cfg)
    except Exception as _err:
        anotar_error("config_portal", _err)
        return None
    if not all(datos.get(k) for k in ("url_login", "usuario", "clave", "url_ficha")):
        return None
    # Se revisa la dirección configurada ANTES de usarla: si la url_ficha apunta a algo que
    # pide mercadería, el portal queda deshabilitado en vez de andar tocándolo.
    ok_url, palabra = _url_solo_de_consulta(datos["url_ficha"])
    if not ok_url:
        datos["_bloqueado"] = (
            f"La dirección de ficha contiene «{palabra}», que suele significar pedir algo. "
            "Configurá la URL de consulta del producto, no la de compra."
        )
    datos.setdefault("campo_usuario", "usuario")
    datos.setdefault("campo_clave", "password")
    return datos


# Del proceso (ver del_proceso()), por lo mismo que _SESIONES_DE_CATALOGO. Guarda
# (sesión, cuándo se abrió): a diferencia de aquella, acá nada detecta una sesión vencida, y
# antes el vaciado de cada pasada la renovaba sin querer. Ahora se renueva a propósito, pasada
# MINUTOS_DE_SESION_DE_PORTAL. Una hora es un login por hora en vez de uno por toque.
_SESIONES_PORTAL = del_proceso("sesiones_de_portal", dict)
MINUTOS_DE_SESION_DE_PORTAL = 60

# Direcciones que en cualquier portal significan "hacer algo", no "mirar". La app entra con TU
# usuario: si por un error de código o una URL mal armada tocara una de estas, estaría pidiendo
# mercadería a tu nombre sin que nadie lo haya decidido.
_RUTAS_QUE_PIDEN = (
    "carrito", "cart", "pedido", "pedidos", "order", "orders", "comprar", "compra",
    "checkout", "add-to", "addto", "agregar", "añadir", "anadir", "cotiza", "presupuest",
    "reserva", "solicitar", "solicitud", "encargar", "confirmar", "pagar", "pago",
    "basket", "wishlist", "favorito", "alta", "crear", "nuevo", "eliminar", "borrar",
    "delete", "update", "editar", "modificar",
)


def _url_solo_de_consulta(url):
    """¿Esta dirección solo mira, o puede llegar a pedir algo? (ok, motivo)."""
    bajo = str(url or "").lower()
    for palabra in _RUTAS_QUE_PIDEN:
        if palabra in bajo:
            return False, palabra
    return True, ""


# Tope duro de consultas por sesión. No es por rendimiento: si algo entra en un bucle por un
# error, esto lo corta antes de que el proveedor vea miles de pedidos desde tu cuenta.
TOPE_CONSULTAS_PORTAL = 400
MINUTOS_VIDA_SESION = 20


def _mismo_dominio(url_a, url_b):
    """¿Las dos direcciones son del mismo sitio? Sirve para no mandar la sesión a otro lado."""
    from urllib.parse import urlparse
    try:
        a, b = urlparse(str(url_a)), urlparse(str(url_b))
    except Exception as _err:
        anotar_error("_mismo_dominio", _err)
        return False
    da, db = (a.netloc or "").lower(), (b.netloc or "").lower()
    if not da or not db:
        return False
    # Se acepta un subdominio del mismo sitio (catalogo.prov.com desde prov.com)
    return da == db or da.endswith("." + db) or db.endswith("." + da)


class SesionSoloLectura:
    """Una sesión del portal que FÍSICAMENTE no puede pedir nada.

    No alcanza con "acordarse de no hacer pedidos": alcanza con que alguien —o yo mismo en un
    cambio futuro— escriba un `.post()` sobre la sesión y ya estaría comprando con tu cuenta.
    Por eso la sesión queda envuelta acá después del login, y este objeto NO EXPONE post, put,
    delete ni patch. No es que estén desaconsejados: no existen. Si algún código los llama,
    revienta en el momento en vez de mandarle un pedido al proveedor.

    Y sobre los GET: aunque leer no debería cambiar nada, muchos portales viejos agregan al
    carrito con un simple enlace. Por eso también se rechazan las direcciones que dicen
    carrito, pedido, comprar y similares."""

    def __init__(self, sesion, dominio_permitido=""):
        self._sesion = sesion
        self._dominio = dominio_permitido
        self._consultas = 0
        self._abierta = time.time()
        self.visitadas = []          # queda el registro de todo lo que se abrió

    def _revisar(self, url, salto=""):
        ok, palabra = _url_solo_de_consulta(url)
        if not ok:
            raise PermissionError(
                f"Bloqueado{salto}: la dirección contiene «{palabra}», que en un portal suele "
                "significar pedir o modificar algo. La app solo puede consultar fichas."
            )
        # Que no salga del sitio del proveedor: si un redirect apunta a otro dominio, la
        # sesión —con tu usuario dentro— se iría a un servidor ajeno.
        if self._dominio and not _mismo_dominio(url, self._dominio):
            raise PermissionError(
                f"Bloqueado{salto}: la dirección apunta a otro sitio y la sesión solo puede "
                f"hablar con {self._dominio}."
            )

    def get(self, url, **kw):
        if time.time() - self._abierta > MINUTOS_VIDA_SESION * 60:
            raise PermissionError(
                f"La sesión con el portal se cerró sola a los {MINUTOS_VIDA_SESION} minutos. "
                "Volvé a entrar si necesitás seguir."
            )
        self._consultas += 1
        if self._consultas > TOPE_CONSULTAS_PORTAL:
            raise PermissionError(
                f"Se llegó al tope de {TOPE_CONSULTAS_PORTAL} consultas en esta sesión. "
                "Es un freno de seguridad: si algo se disparó solo, se corta acá."
            )
        self._revisar(url)

        # Las redirecciones se siguen A MANO, revisando cada salto. Dejar que requests las
        # siga solo es el agujero grande: una ficha puede redirigir a /carrito/agregar, y con
        # la sesión abierta eso sería un pedido hecho a tu nombre sin que nadie lo pidiera.
        kw["allow_redirects"] = False
        actual = url
        for _ in range(5):
            self.visitadas.append(actual)
            r = self._sesion.get(actual, **kw)
            destino = None
            if getattr(r, "status_code", 0) in (301, 302, 303, 307, 308):
                cabeceras = getattr(r, "headers", {}) or {}
                destino = cabeceras.get("Location") or cabeceras.get("location")
            if not destino:
                return r
            from urllib.parse import urljoin
            actual = urljoin(actual, destino)
            self._revisar(actual, " (en una redirección)")
        raise PermissionError("Demasiadas redirecciones seguidas; se corta por las dudas.")

    @property
    def headers(self):
        return self._sesion.headers

    def __getattr__(self, nombre):
        # Cualquier otro método —post, put, delete, request...— no existe a propósito.
        raise PermissionError(
            f"Bloqueado: la app no puede usar «{nombre}» sobre el portal del proveedor. "
            "La sesión es de solo lectura: solo puede abrir fichas para leer los autos."
        )


def sesion_de_portal(nombre_marca):
    """Entra al portal del proveedor y devuelve la sesión abierta. (sesion, error).

    La sesión se guarda en memoria: entrar una vez por marca y reusarla. Hacer login en cada
    producto es maltratar el servidor del proveedor y la forma más rápida de que te bloqueen.
    """
    cfg = config_portal(nombre_marca)
    if not cfg:
        return None, ("No hay portal configurado para esa marca. Se carga en "
                      "Settings → Secrets de Streamlit.")
    if cfg.get("_bloqueado"):
        return None, cfg["_bloqueado"]
    _guardada = _SESIONES_PORTAL.get(nombre_marca)
    if _guardada and time.time() - _guardada[1] < MINUTOS_DE_SESION_DE_PORTAL * 60:
        return _guardada[0], None

    sesion = requests.Session()
    sesion.headers.update({"User-Agent": "Mozilla/5.0 (compatible; EquivalenciasElChavo/1.0)"})
    try:
        # Se abre primero la página de login: muchos portales dejan ahí una cookie o un token
        # sin el cual rechazan el envío del formulario.
        previa = sesion.get(cfg["url_login"], timeout=20)
        datos = {cfg["campo_usuario"]: cfg["usuario"], cfg["campo_clave"]: cfg["clave"]}
        for extra in ("campo_extra_1", "campo_extra_2"):
            if cfg.get(extra) and cfg.get(extra + "_valor"):
                datos[cfg[extra]] = cfg[extra + "_valor"]
        # Token oculto tipo CSRF, si el formulario lo trae
        m = re.search(r'name=["\'](_token|csrf_token|authenticity_token|__RequestVerificationToken)'
                      r'["\'][^>]*value=["\']([^"\']+)', previa.text or "", re.I)
        if m:
            datos[m.group(1)] = m.group(2)

        r = sesion.post(cfg["url_login"], data=datos, timeout=25, allow_redirects=True)
        if r.status_code >= 400:
            return None, f"El portal respondió {r.status_code} al intentar entrar."
        # Señal de que el login falló: sigue mostrando el formulario
        texto = (r.text or "").lower()
        if cfg["campo_clave"].lower() in texto and "logout" not in texto and "salir" not in texto:
            return None, ("Entré pero parece que no aceptó el usuario o la clave: la respuesta "
                          "sigue mostrando el formulario de acceso. Revisá los datos y los "
                          "nombres de los campos.")
        # A partir de acá la sesión queda de solo lectura. El login fue lo único que necesitó
        # mandar datos, y ya se hizo.
        solo_lectura = SesionSoloLectura(sesion, cfg["url_login"])
        _SESIONES_PORTAL[nombre_marca] = (solo_lectura, time.time())
        return solo_lectura, None
    except Exception as e:
        anotar_error("sesion_de_portal", e)
        # Solo el TIPO de error, nunca el detalle: los mensajes de las librerías de red suelen
        # incluir la URL completa con los datos enviados, y ahí va la clave.
        return None, (f"No se pudo entrar al portal ({type(e).__name__}). Revisá la dirección "
                      "de acceso y la conexión.")


def autos_desde_ficha_del_portal(nombre_marca, codigo, tiempo_maximo=20):
    """Trae la ficha del producto en el portal del proveedor y saca a qué autos le va.

    Esto resuelve el problema de raíz: la descripción de la lista se corta y no entran todos
    los autos, pero la ficha del portal los tiene completos.

    Devuelve (lista de autos, error). No inventa nada: si la ficha no nombra autos conocidos,
    devuelve vacío."""
    sesion, error = sesion_de_portal(nombre_marca)
    if error:
        return [], error
    cfg = config_portal(nombre_marca)
    # El código se limpia ANTES de meterlo en la dirección. quote() escapa los espacios pero
    # deja pasar «?» y «&»: con un código así, alguien podría convertir una consulta en una
    # acción («ABC?accion=comprar»). Se dejan solo letras, números y los separadores que usan
    # los códigos de verdad.
    codigo_limpio = re.sub(r"[^A-Za-z0-9._/-]", "", str(codigo).strip())[:60]
    # Y sin «..»: con eso se sube de nivel en la dirección y se llega a otra parte del sitio.
    # Un código como «../../pedido/nuevo» convertiría una consulta en cualquier otra cosa.
    if ".." in codigo_limpio or codigo_limpio.startswith("/"):
        return [], "Ese código no se puede usar en una dirección: tiene barras o puntos dobles."
    if not codigo_limpio:
        return [], "El código tiene caracteres que no se pueden usar en una dirección."
    url = cfg["url_ficha"].replace("{codigo}", quote(codigo_limpio, safe=""))
    try:
        r = sesion.get(url, timeout=tiempo_maximo)
        if r.status_code == 404:
            return [], "El portal no tiene ficha para ese código."
        if r.status_code >= 400:
            return [], f"La ficha respondió {r.status_code}."
        html = r.text or ""
    except Exception as e:
        anotar_error("autos_desde_ficha_del_portal", e)
        return [], f"No se pudo leer la ficha: {type(e).__name__}: {e}"

    # Se saca el texto visible y se buscan marcas y modelos conocidos. Se limita a los que la
    # app ya conoce para no cargar como "auto" cualquier palabra de la página.
    texto = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    texto = re.sub(r"<[^>]+>", " ", texto)
    limpio = normalizar_texto(texto)

    encontrados = []
    for mv in MARCAS_VEHICULO:
        if f" {mv} " in f" {limpio} ":
            encontrados.append(mv)
    for w in set(re.split(r"[^A-Z0-9]+", limpio)):
        if len(w) >= 3 and w in MODELOS_CONOCIDOS:
            encontrados.append(w)
    return sorted(set(encontrados)), None


def guardar_autos_de_ficha(codigo, nombre_marca, autos, tipo_pieza=""):
    """Guarda como aplicaciones los autos que se leyeron de la ficha del portal."""
    if not autos:
        return 0
    filas = [{"marca_auto": a.split()[0], "modelo_auto": a, "motor": "", "combustible": "",
              "anio_desde": None, "anio_hasta": None, "codigo": codigo} for a in autos]
    return guardar_aplicaciones(filas, nombre_marca, "ficha del portal", tipo_pieza)


def buscar_imagen_en_ficha(url_ficha, tiempo_maximo=12, sesion=None):
    """Busca la foto del producto dentro de la ficha oficial del proveedor. Es la fuente más
    confiable que hay gratis: es la foto de ESE código, puesta por el propio proveedor.
    No existe ninguna base pública y gratuita de fotos por número de parte — la del rubro
    (TecDoc) es un servicio pago con licencia."""
    from urllib.parse import urljoin
    try:
        respuesta = _traer_pagina(url_ficha, tiempo_maximo=tiempo_maximo, sesion=sesion)
        if respuesta.status_code != 200:
            return None, f"la ficha respondió {respuesta.status_code}"
        html = respuesta.text
        candidatas = []
        for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.I):
            src = m.group(1)
            if any(x in src.lower() for x in ("logo", "icon", "sprite", "banner", "pixel", ".svg")):
                continue
            candidatas.append(urljoin(url_ficha, src))
        # Las fichas suelen tener la foto del producto en las primeras imágenes útiles
        for url_img in candidatas[:6]:
            datos, error = descargar_imagen(url_img)
            if datos and len(datos) > 8000:   # descarta íconos chiquitos
                return datos, None
        return None, "no encontré una foto de producto en esa ficha"
    except Exception as e:
        anotar_error("buscar_imagen_en_ficha", e)
        return None, type(e).__name__


def contar_fotos_por_bajar():
    """Productos cuya foto es un link externo (cargado desde Excel) y todavía no se bajó."""
    c.execute("""SELECT COUNT(*) FROM productos
                 WHERE imagen_url IS NOT NULL AND imagen_url LIKE 'http%'""")
    return c.fetchone()[0]


def _bajar_en_paralelo(tareas, funcion, hilos=6, progreso=None, cancelado=None):
    """Corre las bajadas en varios hilos a la vez y devuelve los resultados en orden de llegada.

    Por qué: cada foto es una espera de red de 1 a 3 segundos, y en fila india eso son 100 fotos
    en 3-5 minutos. La espera de una no impide empezar la otra, así que de a 6 en paralelo la
    misma tanda baja en menos de un minuto. Solo la parte de red va en hilos: escribir en la
    base se hace después, en el hilo principal, para no pelearse por el archivo.

    6 hilos y no 50 a propósito: es el sitio del proveedor el que atiende, y no corresponde
    martillarlo — además muchos cortan por exceso de pedidos y ahí no baja ninguna."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    resultados = []
    total = len(tareas)
    with ThreadPoolExecutor(max_workers=hilos) as pool:
        futuros = {pool.submit(funcion, t): t for t in tareas}
        for hechos, futuro in enumerate(as_completed(futuros), 1):
            tarea = futuros[futuro]
            try:
                datos, error = futuro.result()
            except Exception as e:
                anotar_error("_bajar_en_paralelo", e)
                datos, error = None, type(e).__name__
            resultados.append((tarea, datos, error))
            if progreso:
                progreso(hechos, total)
            if cancelado and cancelado():
                for f in futuros:
                    f.cancel()
                break
    return resultados


def bajar_fotos_pendientes(limite=200, progreso=None, hilos=6, liviano=True):
    """Baja las fotos que están como link externo y las guarda, con miniatura y firma visual."""
    c.execute("""SELECT id, imagen_url FROM productos
                 WHERE imagen_url IS NOT NULL AND imagen_url LIKE 'http%' LIMIT ?""", (limite,))
    pendientes = [(r["id"], r["imagen_url"]) for r in c.fetchall()]
    if not pendientes:
        return 0, []

    resultados = _bajar_en_paralelo(
        pendientes, lambda t: descargar_imagen(t[1]), hilos=hilos, progreso=progreso
    )

    bajadas, fallidas = 0, []
    for (pid, url), datos, error in resultados:
        if datos:
            try:
                actualizar_imagen_producto(pid, datos, origen="link", fuente=url, liviano=liviano)
                bajadas += 1
            except Exception as e:
                anotar_error("bajar_fotos_pendientes", e)
                fallidas.append((url, type(e).__name__))
        else:
            fallidas.append((url, error))
    return bajadas, fallidas


FILTROS_FOTOS = {
    "todos": ("", "todos los códigos"),
    "stock": (" AND stock > 0", "solo los que tienen stock"),
    "precio": (" AND precio IS NOT NULL AND precio > 0", "solo los que tienen precio cargado"),
}


def _condicion_filtro_fotos(filtro):
    return FILTROS_FOTOS.get(filtro, FILTROS_FOTOS["todos"])[0]


def contar_fotos_por_traer_de_catalogo(marca_id, filtro="todos"):
    """Cuántos códigos de esa marca faltan probar. No cuenta los que ya se probaron y no tenían
    foto: esos ya no se reintentan, si no la tanda nunca avanzaba."""
    c.execute(f"""SELECT COUNT(*) FROM productos
                  WHERE marca_id = ? AND imagen_url IS NULL
                    AND (foto_busqueda_estado IS NULL OR foto_busqueda_estado = 'error')
                    {_condicion_filtro_fotos(filtro)}""", (marca_id,))
    return c.fetchone()[0]


def reintentar_codigos_sin_foto(marca_id=None):
    """Vuelve a habilitar los códigos marcados como 'sin foto en la ficha', por si el proveedor
    la subió después o se cayó el sitio justo esa vez."""
    with db_lock:
        if marca_id:
            c.execute("UPDATE productos SET foto_busqueda_estado = NULL WHERE marca_id = ?", (marca_id,))
        else:
            c.execute("UPDATE productos SET foto_busqueda_estado = NULL")
        cambiados = c.rowcount
        conn.commit()
    return cambiados


def bajar_fotos_desde_catalogo(marca_id, limite=100, progreso=None, hilos=6, liviano=True,
                               cancelado=None, filtro="todos"):
    """Para los productos de una marca sin foto: entra a la ficha oficial del proveedor de cada
    código y trae la foto de ahí. Los códigos cuya ficha no tiene foto quedan marcados para no
    volver a consultarlos en cada tanda."""
    c.execute("SELECT nombre, url_ficha_template FROM marcas WHERE id = ?", (marca_id,))
    fila = c.fetchone()
    if not fila or not fila["url_ficha_template"]:
        return 0, [("", "esa marca no tiene cargada la dirección de su catálogo")], 0
    plantilla = fila["url_ficha_template"]
    # Si ese catálogo pide usuario y contraseña, se entra UNA vez y se reusa para toda la tanda.
    sesion = sesion_para_el_catalogo(fila["nombre"])

    c.execute(f"""SELECT id, codigo_raw FROM productos
                  WHERE marca_id = ? AND imagen_url IS NULL
                    AND (foto_busqueda_estado IS NULL OR foto_busqueda_estado = 'error')
                    {_condicion_filtro_fotos(filtro)}
                  ORDER BY (stock > 0) DESC, id
                  LIMIT ?""", (marca_id, limite))
    pendientes = [(r["id"], r["codigo_raw"]) for r in c.fetchall()]
    if not pendientes:
        return 0, [], 0

    def traer(tarea):
        _, codigo = tarea
        url_ficha = plantilla.replace("{codigo}", quote(str(codigo), safe=""))
        return buscar_imagen_en_ficha(url_ficha, sesion=sesion)

    resultados = _bajar_en_paralelo(pendientes, traer, hilos=hilos, progreso=progreso,
                                    cancelado=cancelado)

    bajadas, fallidas, sin_foto = 0, [], 0
    for (pid, codigo), datos, error in resultados:
        url_ficha = plantilla.replace("{codigo}", quote(str(codigo), safe=""))
        if datos:
            try:
                actualizar_imagen_producto(pid, datos, origen="ficha", fuente=url_ficha,
                                            liviano=liviano)
                bajadas += 1
                continue
            except Exception as e:
                anotar_error("bajar_fotos_desde_catalogo", e)
                error = type(e).__name__
        fallidas.append((codigo, error))
        # "no encontré una foto" es definitivo para ese código; un error de red no lo es
        definitivo = error and "no encontré" in str(error)
        with db_lock:
            c.execute("UPDATE productos SET foto_busqueda_estado = ? WHERE id = ?",
                      ("sin_foto" if definitivo else "error", pid))
            conn.commit()
        if definitivo:
            sin_foto += 1
    _si_falla_casi_todo_la_sesion_venció(fila["nombre"], sesion, len(fallidas), len(pendientes))
    return bajadas, fallidas, sin_foto


# --------------------------------------------------------------------------------------------
# CATÁLOGOS QUE PIDEN USUARIO Y CONTRASEÑA
# --------------------------------------------------------------------------------------------
# Muchos proveedores tienen la ficha detrás de un login. Sin esto, la app pide la página, el
# sitio le devuelve el formulario de ingreso, y de ahí no sale ni foto ni equivalencia: el
# catálogo entero queda afuera.
#
# LAS CREDENCIALES VAN EN LOS SECRETOS DE STREAMLIT Y NO EN LA BASE, y no es una preferencia:
# todo lo que se guarda en la tabla de configuración sale de la app por dos puertas —el backup
# que se sube solo al repositorio de GitHub, y el botón de bajar la base completa—. Una
# contraseña guardada ahí termina copiada en el repositorio. En los secretos no toca la base,
# así que no viaja en ninguna de las dos.
#
# En secrets.toml (panel de Streamlit Cloud → Settings → Secrets), una sección por marca, con
# el nombre de la marca tal como está cargada en la app:
#
#     [catalogo.MOTORARG]
#     url_login = "https://ejemplo.com/ingresar"
#     usuario = "micuenta@ejemplo.com"
#     clave = "loquesea"
#     campo_usuario = "email"        # cómo se llama el campo en el formulario (opcional)
#     campo_clave = "password"       # idem (opcional)
#     campos_extra = { recordar = "1" }   # cualquier otro campo que pida el formulario
#
# Los nombres de los campos se sacan mirando el formulario del proveedor: cada sitio los llama
# distinto y no hay forma de adivinarlos.
# Del proceso, no de cada pasada del script (ver del_proceso()): con «= {}» acá, cada toque
# empezaba con el diccionario vacío y la sesión «guardada» duraba una pasada. Cada tanda de
# fondo nueva y cada ficha pedida desde la pantalla era un login más contra el proveedor.
_SESIONES_DE_CATALOGO = del_proceso("sesiones_de_catalogo", dict)
_CANDADO_SESIONES = del_proceso("candado_de_sesiones_de_catalogo", threading.Lock)


def credenciales_de_catalogo(nombre_marca):
    """Lo que hay en los secretos para esa marca, o {}. Nunca falla.

    Leer st.secrets sin un secrets.toml levanta excepción —ver secretos_app()—, así que se pasa
    siempre por ahí y no por st.secrets directo."""
    try:
        todo = secretos_app().get("catalogo") or {}
        datos = todo.get(str(nombre_marca).strip().upper()) or {}
        if datos.get("usuario") and datos.get("clave") and datos.get("url_login"):
            return dict(datos)
    except Exception as _err:
        anotar_error("credenciales_de_catalogo", _err)
    return {}


def sesion_para_el_catalogo(nombre_marca, tiempo_maximo=12):
    """Una sesión de requests ya logueada para esa marca, o None si no hay credenciales.

    Se guarda y se reutiliza: una tanda son cientos de fichas, y loguearse en cada una sería
    cientos de ingresos contra el sitio del proveedor — que es justo la forma más rápida de que
    te bloqueen la cuenta.

    Si el login falla no se rompe nada: se devuelve None y la consulta sigue como antes, sin
    sesión. Lo más probable entonces es que la ficha conteste el formulario de ingreso y esa
    ficha quede como «no se pudo leer», que es exactamente lo que pasaba hasta ahora."""
    datos = credenciales_de_catalogo(nombre_marca)
    if not datos:
        return None
    clave_cache = str(nombre_marca).strip().upper()
    with _CANDADO_SESIONES:
        sesion = _SESIONES_DE_CATALOGO.get(clave_cache)
        if sesion is not None:
            return sesion
        try:
            sesion = requests.Session()
            sesion.headers.update(
                {"User-Agent": "Mozilla/5.0 (compatible; EquivalenciasElChavo/1.0)"})
            cuerpo = {datos.get("campo_usuario") or "usuario": datos["usuario"],
                      datos.get("campo_clave") or "password": datos["clave"]}
            cuerpo.update(dict(datos.get("campos_extra") or {}))
            r = sesion.post(datos["url_login"], data=cuerpo, timeout=tiempo_maximo,
                            allow_redirects=True)
            # 200 con el formulario devuelto también es un login fallido, pero eso no se puede
            # distinguir sin saber cómo es el sitio. Se guarda igual: si no entró, las fichas
            # van a fallar y se va a ver en «no se pudieron leer», que es información honesta.
            if r.status_code >= 400:
                anotar_error("sesion_para_el_catalogo",
                             Exception(f"{nombre_marca}: el ingreso respondió {r.status_code}"))
                return None
            _SESIONES_DE_CATALOGO[clave_cache] = sesion
            return sesion
        except Exception as _err:
            anotar_error("sesion_para_el_catalogo", _err)
            return None


def olvidar_sesion_de_catalogo(nombre_marca=None):
    """Tira la sesión guardada para que el próximo pedido vuelva a loguearse.

    Hace falta porque las sesiones vencen: el sitio corta a las pocas horas y desde ese momento
    todas las fichas contestan el formulario de ingreso. Sin esto, la sesión muerta quedaría
    guardada hasta que alguien reiniciara el servidor."""
    with _CANDADO_SESIONES:
        if nombre_marca is None:
            _SESIONES_DE_CATALOGO.clear()
        else:
            _SESIONES_DE_CATALOGO.pop(str(nombre_marca).strip().upper(), None)


def _si_falla_casi_todo_la_sesion_venció(nombre_marca, sesion, fallidas, total):
    """Tira la sesión guardada cuando la tanda falló casi entera.

    Las sesiones vencen: el sitio corta a las pocas horas y desde ese momento TODAS las fichas
    contestan el formulario de ingreso. Sin esto, la sesión muerta se seguiría usando hasta que
    alguien reiniciara el servidor, y con las tandas corriendo solas en segundo plano eso son
    miles de fichas marcadas como leídas sin haber leído nada.

    Se pide que haya fallado más del 80% y no simplemente «alguna»: en un catálogo normal
    siempre hay fichas que no existen o que no tienen foto, y tirar la sesión por eso
    significaría volver a loguearse en cada tanda."""
    if sesion is not None and total and fallidas > total * 0.8:
        olvidar_sesion_de_catalogo(nombre_marca)


def _traer_pagina(url, tiempo_maximo=12, sesion=None, **extra):
    """Pide una página con la sesión del proveedor si la hay, o suelta si no.

    Existe para que las dos funciones que leen fichas —la de fotos y la de equivalencias— usen
    exactamente el mismo camino. Eran dos requests.get() casi iguales, y agregarle el login a
    una sola habría dejado la otra afuera sin que se notara."""
    pedir = (sesion or requests).get
    cabeceras = {"User-Agent": "Mozilla/5.0 (compatible; EquivalenciasElChavo/1.0)"}
    return pedir(url, timeout=tiempo_maximo, headers=cabeceras, **extra)


def codigos_en_una_ficha(url_ficha, codigo_propio, tiempo_maximo=12, sesion=None):
    """Abre la ficha de un producto en el catálogo del proveedor y saca los OTROS códigos que
    aparecen ahí. Devuelve (lista de códigos, error).

    Las fichas de catálogo suelen listar las referencias cruzadas —«equivale a», «OEM», «cross
    reference»— que es justo la información que uno cargaría a mano código por código. Es la
    misma fuente que ya se usa para las fotos y para los autos; lo que faltaba era leer los
    números.

    No inventa: usa el mismo extractor conservador de siempre (extraer_codigos_de_texto), que
    descarta palabras sin números, años, cilindradas y códigos de motor. Y descarta el propio
    código, que obviamente está escrito en su ficha."""
    try:
        respuesta = _traer_pagina(url_ficha, tiempo_maximo=tiempo_maximo, sesion=sesion)
        if respuesta.status_code != 200:
            return [], f"la ficha respondió {respuesta.status_code}"
    except Exception as e:
        anotar_error("codigos_en_una_ficha", e)
        return [], type(e).__name__

    # Se sacan los scripts y estilos antes de mirar el texto: adentro hay identificadores y
    # números de versión que parecen códigos y no lo son.
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", respuesta.text)
    texto = re.sub(r"<[^>]+>", " ", html)
    texto = re.sub(r"\s+", " ", texto)

    propio = sanitizar(codigo_propio)
    encontrados, vistos = [], {propio}
    for candidato in extraer_codigos_de_texto(texto):
        limpio = sanitizar(candidato)
        if not limpio or limpio in vistos:
            continue
        malo, _motivo = codigo_sospechoso(candidato)
        if malo:
            continue
        vistos.add(limpio)
        encontrados.append(candidato)
    if not encontrados:
        return [], "no encontré códigos en la ficha"
    return encontrados, None


def equivalencias_desde_catalogo(marca_id, limite=50, progreso=None, cancelado=None, hilos=4,
                                  solo_no_leidos=False):
    """Recorre las fichas del catálogo digital de una marca y propone las equivalencias que
    encuentra escritas ahí. Devuelve (propuestas, fallidas, consultados).

    Las propuestas NO se cargan solas: van a la misma cola de revisión que todo lo demás. Una
    ficha puede listar accesorios, repuestos relacionados o el código de un kit, y eso no es una
    equivalencia — la diferencia la tiene que poner una persona mirando.

    Solo se proponen códigos que YA existan en tu catálogo. Proponer una equivalencia contra un
    código que no tenés cargado no le sirve a nadie: no lo podrías vender ni buscar."""
    c.execute("SELECT nombre, url_ficha_template FROM marcas WHERE id = ?", (marca_id,))
    fila = c.fetchone()
    if not fila or not fila["url_ficha_template"]:
        return [], [("", "esa marca no tiene cargada la dirección de su catálogo")], 0
    plantilla, nombre_marca = fila["url_ficha_template"], fila["nombre"]
    sesion = sesion_para_el_catalogo(nombre_marca)

    # Primero los que tienen stock: si algo va a salir del mostrador hoy, que sea eso lo que
    # tenga las equivalencias completas.
    # solo_no_leidos es lo que permite avanzar de a tandas sin repetir: lo usa la tarea del día.
    # A mano se deja en False porque ahí la intención suele ser volver a mirar lo importante.
    _filtro = " AND ficha_equiv_leida IS NULL" if solo_no_leidos else ""
    c.execute(f"""SELECT id, codigo_raw, codigo_clean FROM productos
                  WHERE marca_id = ?{_filtro}
                  ORDER BY (COALESCE(stock, 0) > 0) DESC, id LIMIT ?""",
              (marca_id, limite))
    pendientes = [(r["id"], r["codigo_raw"], r["codigo_clean"]) for r in c.fetchall()]
    if not pendientes:
        return [], [], 0

    def traer(tarea):
        _pid, codigo, _limpio = tarea
        # El código se limpia antes de meterlo en la dirección, igual que en el resto: sin esto
        # un código con «?» o «..» convertiría una consulta en otra cosa.
        seguro = re.sub(r"[^A-Za-z0-9._/-]", "", str(codigo).strip())[:60]
        if not seguro or ".." in seguro or seguro.startswith("/"):
            return None, "ese código no se puede usar en una dirección"
        return codigos_en_una_ficha(plantilla.replace("{codigo}", quote(seguro, safe="")),
                                    codigo, sesion=sesion)

    resultados = _bajar_en_paralelo(pendientes, traer, hilos=hilos, progreso=progreso,
                                    cancelado=cancelado)

    propuestas, fallidas = [], []
    for (pid, codigo, limpio), codigos, error in resultados:
        if error or not codigos:
            fallidas.append((codigo, error or "sin códigos"))
            continue
        for otro in codigos:
            otro_limpio = sanitizar(otro)
            c.execute("""SELECT p.id, p.codigo_raw, m.nombre AS marca FROM productos p
                         JOIN marcas m ON m.id = p.marca_id
                         WHERE p.codigo_clean = ? AND p.id <> ? LIMIT 1""", (otro_limpio, pid))
            destino = c.fetchone()
            if not destino:
                continue        # ese código no está en tu catálogo: no sirve proponerlo
            propuestas.append({
                "Código": codigo, "Marca": nombre_marca,
                "Equivale a": destino["codigo_raw"], "Marca del otro": destino["marca"],
                "_a": min(pid, destino["id"]), "_b": max(pid, destino["id"]),
            })

    # Queda anotado que a estos códigos ya se les leyó la ficha, hayan dado equivalencias o no.
    # El "no" también es información: sin anotarlo, la próxima tanda vuelve a golpear las mismas
    # fichas vacías y el recorrido no avanza nunca. Es el mismo problema que ya se arregló con
    # foto_busqueda_estado para las fotos.
    try:
        _ahora_txt = datetime.now().strftime("%Y-%m-%d")
        with db_lock:
            c.executemany("UPDATE productos SET ficha_equiv_leida = ? WHERE id = ?",
                          [(_ahora_txt, pid) for (pid, _c, _l), _x, _e in resultados])
            conn.commit()
    except sqlite3.OperationalError as _err:
        anotar_error("equivalencias_desde_catalogo/marcar", _err)

    _si_falla_casi_todo_la_sesion_venció(nombre_marca, sesion, len(fallidas), len(pendientes))
    return propuestas, fallidas, len(pendientes)


def guardar_equivalencias_de_catalogo(propuestas, marca):
    """Manda a revisión lo que se leyó de las fichas. Devuelve cuántas quedaron pendientes."""
    if not propuestas:
        return 0
    lote = f"CATÁLOGO {marca} · {datetime.now():%d/%m %H:%M}"
    rechazados = pares_rechazados()
    nuevas = [(p["_a"], p["_b"]) for p in propuestas
              if (p["_a"], p["_b"]) not in rechazados]
    if not nuevas:
        return 0
    with db_lock:
        c.executemany("""INSERT OR IGNORE INTO equivalencias_pendientes
                         (producto_a_id, producto_b_id, origen, lote)
                         VALUES (?, ?, 'ficha', ?)""",
                      [(a, b, lote) for a, b in nuevas])
        conn.commit()
    return len(nuevas)


# ============================================================================================
# LAS TANDAS QUE CORREN SOLAS, EN SEGUNDO PLANO
# ============================================================================================
# Traer fotos y equivalencias de las fichas del proveedor iba de a 15 por día, enganchado a las
# tareas del día. Con 500 productos eso alcanza; con 70.888 son trece años, y con medio millón
# no termina nunca. El límite no era el proveedor: era que la tanda corría DENTRO del dibujo de
# la pantalla, con el presupuesto de 6 segundos de las tareas del día, así que agrandarla
# significaba hacer esperar a alguien que entró a buscar un repuesto.
#
# Acá se corta ese nudo: la tanda se va a un hilo aparte. Nadie espera, así que puede ser tan
# grande como se quiera. Lo que la limita ahora es lo único que corresponde que la limite —el
# servidor del proveedor— y eso se elige a mano.
#
# Tres cosas la hacen segura:
#   · UNA sola a la vez en todo el proceso (_CANDADO_FONDO). Sin eso, cinco pestañas abiertas
#     son cinco tandas pidiéndole lo mismo al proveedor al mismo tiempo.
#   · Va de a subtandas chicas que van guardando. Si Streamlit Cloud apaga el servidor por
#     inactividad —pasa seguido— se pierde la subtanda en curso y nada más.
#   · Nunca toca `st`. Un hilo de fondo no tiene pantalla donde dibujar; llamar a st.* desde
#     ahí no muestra nada y ensucia el registro. Todo lo que tiene para contar lo deja anotado
#     en la configuración, y la pantalla lo lee de ahí.
TANDAS_DISPONIBLES = [15, 100, 500, 2000, 10000]
PRODUCTOS_POR_SUBTANDA = 50
MINUTOS_MAXIMO_DE_TANDA = 10

# Del proceso, no de la pasada: ver del_proceso(). Con «= threading.Lock()» acá, cada toque
# traía un candado nuevo y libre, y la regla de «una sola a la vez» no se cumplía nunca.
_CANDADO_FONDO = del_proceso("candado_de_la_tanda_de_fondo", threading.Lock)


def _cupo_de_hoy(clave, objetivo):
    """Cuánto queda del cupo diario de esa tarea. El contador se reinicia con el día."""
    hoy = datetime.now().strftime("%Y-%m-%d")
    if obtener_config("tanda_fondo_fecha", "") != hoy:
        guardar_config("tanda_fondo_fecha", hoy)
        guardar_config("tanda_fondo_fotos", "0")
        guardar_config("tanda_fondo_equiv", "0")
    try:
        return max(objetivo - int(obtener_config(clave, "0") or 0), 0)
    except ValueError:
        return objetivo


def _sumar_al_cupo(clave, cuantos):
    try:
        guardar_config(clave, str(int(obtener_config(clave, "0") or 0) + cuantos))
    except ValueError:
        guardar_config(clave, str(cuantos))


def _marca_con_mas_fichas_pendientes(que):
    """La marca a la que le falta más trabajo del tipo pedido, o None.

    Se elige la de más pendientes y no la primera: así el catálogo más grande —que es el que
    tarda años— avanza primero, en vez de repartir el esfuerzo entre listas chicas."""
    condicion = ("p.imagen_url IS NULL "
                 "AND (p.foto_busqueda_estado IS NULL OR p.foto_busqueda_estado = 'error')"
                 if que == "fotos" else "p.ficha_equiv_leida IS NULL")
    try:
        c.execute(f"""SELECT p.marca_id AS mid, m.nombre AS nombre, COUNT(*) AS faltan
                      FROM productos p JOIN marcas m ON m.id = p.marca_id
                      WHERE {condicion}
                        AND m.url_ficha_template IS NOT NULL AND m.url_ficha_template <> ''
                      GROUP BY p.marca_id ORDER BY faltan DESC LIMIT 1""")
        fila = c.fetchone()
    except sqlite3.OperationalError as _err:
        anotar_error("_marca_con_mas_fichas_pendientes", _err)
        return None
    return dict(fila) if fila else None


# CEDERLE EL PASO AL MOSTRADOR. La tarea de fondo y la pantalla que alguien está mirando se
# reparten el procesador: un hilo de Python no corre en paralelo con otro, se turnan. Medido:
# «Equivalencias sugeridas» analiza la lista del barrido en 4 s, y con la tarea de fondo al
# lado —que es justo después de importar, cuando uno entra a revisar— tardaba 19. La tarea de
# fondo no apura a nadie; la persona sí está esperando.
# Mientras hay una pantalla dibujándose, el hilo de fondo duerme un rato cada vez que pasa por
# ceder_al_mostrador(), que está puesto en sus bucles pesados. Con tope: si una pantalla
# termina en un st.stop() el «terminó» no se anota, y sin tope la tarea de fondo quedaría
# frenada para siempre por una marca perdida. Pasados SEGUNDOS_DE_PREFERENCIA vuelve a correr.
# Es una sola marca para todo el proceso, no una por sesión: con dos personas a la vez, que
# una termine libera a la tarea aunque la otra siga. Se prefirió simple a exacto.
SEGUNDOS_DE_PREFERENCIA = 20
_HILO_DE_FONDO = threading.local()


def ceder_al_mostrador():
    """Si esto corre en la tarea de fondo y alguien está esperando una pantalla, espera a que
    termine de dibujarse (con el tope de SEGUNDOS_DE_PREFERENCIA). En cualquier otro hilo no
    hace nada, así que se puede llamar desde funciones que también usa la pantalla.

    ESPERA y no «duerme un poco»: la primera versión dormía 50 ms por vuelta y la pantalla de
    revisión bajó de 19 s a 12,5, no a los 5 que tarda sola. Muestreando el hilo de fondo se vio
    por qué: seguía leyendo —las 24.774 filas de recalcular_confianzas(), las medidas de todo
    el catálogo— y una lectura grande compite fila por fila aunque el bucle de después ceda.
    Por eso también se llama antes de esas lecturas, no solo adentro de los bucles."""
    if not getattr(_HILO_DE_FONDO, "corriendo", False):
        return
    act = _actividad_del_mostrador()
    while (act["empezo"] > act["termino"]
           and time.monotonic() - act["empezo"] < SEGUNDOS_DE_PREFERENCIA):
        time.sleep(0.05)


def _trabajo_de_fondo():
    """El cuerpo del hilo. Va alternando fotos y equivalencias hasta gastar el cupo o el reloj.

    Alterna en vez de terminar una y después la otra para que prender las dos no signifique que
    la segunda no arranca hasta dentro de un mes."""
    arranque = time.time()
    try:
        objetivo_fotos = (int(obtener_config("tanda_fotos_diaria", "500") or 500)
                          if obtener_config("fotos_automaticas", "0") == "1" else 0)
        objetivo_equiv = (int(obtener_config("tanda_equiv_diaria", "500") or 500)
                          if obtener_config("equiv_ficha_automaticas", "0") == "1" else 0)
    except ValueError:
        objetivo_fotos = objetivo_equiv = 0

    # RESEPARAR LAS DESCRIPCIONES VA PRIMERO, y el orden no es casual: las medidas, el
    # combustible, la marca del repuesto y las aplicaciones se leen de la descripción.
    # Estaba escrito así y NO era así: el bloque había quedado después del de medidas, y
    # corriendo la tanda entera se vio —las medidas se leían del texto viejo, y al final
    # `medidas_pendientes` quedaba otra vez en «1» porque este bloque lo vuelve a pedir.
    # Funcionaba igual, en dos arranques en vez de uno, pero el comentario mentía.
    if _hay_que_hacerlo("separacion_pendiente"):
        try:
            _n_sep = reseparar_descripciones_viejas()
            guardar_config("descripciones_reseparadas", str(_n_sep))
            guardar_config("separacion_fecha", datetime.now().strftime("%Y-%m-%d %H:%M"))
            if _n_sep:
                # El texto cambió: hay que releerlo todo.
                for _marca in ("medidas_pendientes", "marcas_repuesto_pendientes",
                               "aplicaciones_pendientes"):
                    guardar_config(_marca, "1")
                    guardar_config(f"{_marca}_intentos", "0")
            _quedo_hecho("separacion_pendiente")
        except Exception as _err:
            # La bandera sigue prendida: se reintenta en el próximo arranque, hasta el tope.
            anotar_error("_trabajo_de_fondo/separacion", _err)

    # Lo primero de todo: el descubrimiento que dejó pendiente una importación. Va acá y no
    # adentro de la pantalla de importar porque tarda 110 segundos, y hacer esperar dos minutos
    # a alguien que subió una planilla desde el celular —con la pantalla que se apaga sola y el
    # navegador que puede cortar la conexión— es peor que avisarle que está corriendo.
    # Las medidas van ANTES que el repuntaje, y el orden no es casual: el puntaje usa las
    # medidas como prueba física, así que repuntuar primero sería repuntuar sin ellas y habría
    # que hacerlo dos veces. Ver VERSION_MEDIDAS.
    if _hay_que_hacerlo("medidas_pendientes"):
        try:
            _n_med = 0
            # Con tope de vueltas, no `while True`. Esto corre en un hilo de fondo: si alguna
            # vez el lector devuelve una medida que la escritura no deja guardada —una columna
            # que no existe, un valor que vuelve NULL—, la consulta devuelve las MISMAS filas
            # para siempre y el hilo queda girando sin que nadie lo vea. 2.000 por vuelta y
            # 100 vueltas son 200.000 productos, casi el triple del catálogo real.
            for _ in range(100):
                _tanda_med = productos_con_medidas_deducibles(limite=2000)
                if not _tanda_med:
                    break
                _aplicadas = aplicar_medidas_deducidas(_tanda_med)
                _n_med += _aplicadas
                if not _aplicadas:
                    # Hay filas para completar y no se completó ninguna: seguir es girar.
                    anotar_error("_trabajo_de_fondo/medidas",
                                 RuntimeError(f"{len(_tanda_med)} productos con medidas para "
                                              "leer y ninguno se pudo guardar"))
                    break
            guardar_config("medidas_completadas", str(_n_med))
            guardar_config("medidas_fecha", datetime.now().strftime("%Y-%m-%d %H:%M"))
            # Las medidas nuevas cambian el puntaje, así que se pide el repuntaje detrás.
            guardar_config("confianza_pendiente", "1")
            guardar_config("confianza_pendiente_intentos", "0")
            _quedo_hecho("medidas_pendientes")
        except Exception as _err:
            # La bandera sigue prendida: se reintenta en el próximo arranque, hasta el tope.
            anotar_error("_trabajo_de_fondo/medidas", _err)

    # Las aplicaciones: a qué auto le va cada pieza. Es lo más caro de las tres (55 s sobre
    # 70.888 descripciones: 32 s leerlas y 23 s escribirlas) y va después de las medidas porque
    # no se necesitan entre sí. Ver VERSION_APLICACIONES.
    # La marca del repuesto: es la más barata de las cuatro (una expresión regular por
    # descripción, sin consultas de por medio) así que va primero.
    if _hay_que_hacerlo("marcas_repuesto_pendientes"):
        try:
            _n_mr = completar_marcas_de_repuesto()
            guardar_config("marcas_repuesto_puestas", str(_n_mr))
            guardar_config("marcas_repuesto_fecha", datetime.now().strftime("%Y-%m-%d %H:%M"))
            _quedo_hecho("marcas_repuesto_pendientes")
        except Exception as _err:
            # La bandera sigue prendida: se reintenta en el próximo arranque, hasta el tope.
            anotar_error("_trabajo_de_fondo/marcas_repuesto", _err)

    if _hay_que_hacerlo("aplicaciones_pendientes"):
        try:
            aprender_motores_que_van_juntos()
            _apl_ded = aplicaciones_desde_descripciones()
            _n_apl = aplicar_aplicaciones_deducidas(_apl_ded) if _apl_ded else 0
            guardar_config("aplicaciones_deducidas", str(_n_apl))
            guardar_config("aplicaciones_fecha", datetime.now().strftime("%Y-%m-%d %H:%M"))
            if _n_apl:
                # Con las aplicaciones cargadas, el cruce por auto tiene con qué cruzar, así
                # que se corre ESE paso y nada más. La primera versión pedía el descubrimiento
                # completo y probándolo se vio el problema: eso larga también el barrido de
                # todo el catálogo, que no necesita las aplicaciones para nada, y la cola de
                # revisión pasaba de 3.185 a 22.235 de una vez. Que crezca así está bien
                # después de importar una lista —hay algo nuevo que mirar— pero no cuando lo
                # único que pasó es que la app se actualizó: nadie pidió 9.000 pares nuevos, y
                # abrir la app y encontrarlos parece que algo se rompió.
                # El barrido sigue corriendo después de cada importación, como siempre.
                try:
                    _por_auto = derivar_equivalencias_de_aplicaciones()
                    if _por_auto:
                        _n_auto = guardar_equivalencias_derivadas(
                            [(x["_a"], x["_b"]) for x in _por_auto],
                            f"CRUCE POR AUTO (automático) · {datetime.now():%d/%m %H:%M}")
                        guardar_config("aplicaciones_cruces", str(_n_auto))
                except Exception as _err:
                    anotar_error("_trabajo_de_fondo/cruce_por_auto", _err)
            _quedo_hecho("aplicaciones_pendientes")
        except Exception as _err:
            # La bandera sigue prendida: se reintenta en el próximo arranque, hasta el tope.
            anotar_error("_trabajo_de_fondo/aplicaciones", _err)

    # Después el repuntaje: es barato (12,8 s sobre 24.774 vínculos) y lo que más se nota,
    # porque el puntaje viejo lo está mostrando el buscador en cada búsqueda.
    # Ver VERSION_CONFIANZA.
    if _hay_que_hacerlo("confianza_pendiente"):
        try:
            _n_conf = recalcular_confianzas(limite=100000, solo_faltantes=False)
            guardar_config("confianza_repuntuada", str(_n_conf))
            guardar_config("confianza_fecha", datetime.now().strftime("%Y-%m-%d %H:%M"))
            _quedo_hecho("confianza_pendiente")
        except Exception as _err:
            # La bandera sigue prendida: se reintenta en el próximo arranque, hasta el tope.
            anotar_error("_trabajo_de_fondo/confianza", _err)

    if obtener_config("descubrimiento_pendiente", "") == "1":
        try:
            guardar_config("descubrimiento_pendiente", "0")
            hecho, quedo = descubrimiento_post_importacion()
            guardar_config("descubrimiento_ultimo",
                           " · ".join(hecho) if hecho else "nada nuevo para buscar")
            guardar_config("descubrimiento_fecha", datetime.now().strftime("%Y-%m-%d %H:%M"))
            if quedo:
                # Si no le alcanzó el tiempo, queda pedido de nuevo para la próxima vuelta.
                guardar_config("descubrimiento_pendiente", "1")
        except Exception as _err:
            anotar_error("_trabajo_de_fondo/descubrimiento", _err)

    while time.time() - arranque < MINUTOS_MAXIMO_DE_TANDA * 60:
        hizo_algo = False

        if _cupo_de_hoy("tanda_fondo_fotos", objetivo_fotos) > 0:
            marca = _marca_con_mas_fichas_pendientes("fotos")
            if marca:
                try:
                    cuantas = min(PRODUCTOS_POR_SUBTANDA,
                                  _cupo_de_hoy("tanda_fondo_fotos", objetivo_fotos))
                    traidas, _fall, _sin = bajar_fotos_desde_catalogo(
                        marca["mid"], limite=cuantas)
                    # Del cupo se descuenta lo que se CONSULTÓ de verdad, no lo que se pidió.
                    # No es lo mismo: si quedaban tres fichas y la subtanda es de cincuenta,
                    # cobrarle cincuenta al cupo del día tira a la basura cuarenta y siete
                    # consultas que nunca se hicieron. Una ficha sin foto sí cuenta —se le
                    # pidió igual al servidor del proveedor—, por eso van las fallidas adentro.
                    consultadas = traidas + len(_fall)
                    _sumar_al_cupo("tanda_fondo_fotos", consultadas)
                    if traidas:
                        _sumar_al_cupo("tanda_fondo_fotos_ok", traidas)
                    # Y el bucle sigue solo si esto AVANZÓ. Darlo por hecho porque había una
                    # marca pendiente deja girar el bucle diez minutos contra la base cuando la
                    # consulta que elige la marca y la que trae las fichas no miran exactamente
                    # lo mismo — hoy miran igual, pero con dos consultas separadas eso se
                    # desincroniza el día que alguien toque una sola de las dos.
                    hizo_algo = hizo_algo or consultadas > 0
                except Exception as _err:
                    anotar_error("_trabajo_de_fondo/fotos", _err)

        if _cupo_de_hoy("tanda_fondo_equiv", objetivo_equiv) > 0:
            marca = _marca_con_mas_fichas_pendientes("equiv")
            if marca:
                try:
                    cuantas = min(PRODUCTOS_POR_SUBTANDA,
                                  _cupo_de_hoy("tanda_fondo_equiv", objetivo_equiv))
                    props, _fall, consultados = equivalencias_desde_catalogo(
                        marca["mid"], limite=cuantas, solo_no_leidos=True)
                    _sumar_al_cupo("tanda_fondo_equiv", consultados)
                    if props:
                        guardadas = guardar_equivalencias_de_catalogo(props, marca["nombre"])
                        if guardadas:
                            _sumar_al_cupo("tanda_fondo_equiv_ok", guardadas)
                    hizo_algo = hizo_algo or consultados > 0
                except Exception as _err:
                    anotar_error("_trabajo_de_fondo/equiv", _err)

        if not hizo_algo:
            break       # no queda cupo, o no queda nada pendiente: no tiene sentido girar
    guardar_config("tanda_fondo_ultima", datetime.now().strftime("%Y-%m-%d %H:%M"))


INTENTOS_MAXIMOS_DE_FONDO = 5

# Cuántas filas se escriben con el candado tomado antes de soltarlo. La tarea de fondo escribe
# decenas de miles de filas, y tomar db_lock UNA vez para todas deja la pantalla de la otra
# persona esperando todo lo que dure.
# No es teoría: midiendo búsquedas desde otro hilo mientras corría la tanda completa, la peor
# tardó 23,78 SEGUNDOS. La mediana estaba perfecta —0,02 s— y por eso no se veía promediando;
# lo que hay que mirar es la peor, porque esa es la que tiene a alguien esperando en el
# mostrador. Soltando y volviendo a tomar cada 500 filas, la otra sesión se cuela en el medio.
FILAS_ANTES_DE_SOLTAR_EL_CANDADO = 500


def en_tandas_para_no_trabar(filas):
    """Parte una lista larga en pedazos, para escribir cada uno con el candado tomado aparte."""
    for arranque in range(0, len(filas), FILAS_ANTES_DE_SOLTAR_EL_CANDADO):
        ceder_al_mostrador()
        yield filas[arranque:arranque + FILAS_ANTES_DE_SOLTAR_EL_CANDADO]


def _hay_que_hacerlo(clave):
    """¿Corresponde hacer este trabajo de fondo? Cuenta el intento antes de empezar.

    Reemplaza a un `guardar_config(clave, "0")` puesto ANTES del trabajo, que era un agujero
    serio y silencioso. Si el proceso se muere en el medio —y en Streamlit Cloud se muere
    seguido: se redespliega, se reinicia, recicla el contenedor— la bandera ya estaba en «0» y
    NADIE la volvía a prender. Un proceso que muere no lanza una excepción, así que el `except`
    que la reponía nunca corría.

    Y no es hipotético, está en la base real: `aplicaciones_pendientes` dice «0» y
    `version_aplicaciones` dice «2», o sea «este trabajo ya se hizo». La tabla `aplicaciones`
    tiene 0 filas, y las claves `aplicaciones_deducidas` y `aplicaciones_fecha` —que se
    escriben recién al terminar— NO EXISTEN. Las 114.673 aplicaciones nunca se cargaron, ni una
    vez, y la búsqueda por vehículo viene trabajando sobre una tabla vacía sin que nada avise.

    Apagar la bandera antes tampoco protegía de nada: que no corran dos a la vez ya lo asegura
    `_CANDADO_FONDO`, que se toma en arrancar_tanda_de_fondo().

    El contador de intentos es el otro lado del cambio. Ahora la bandera queda prendida hasta
    que el trabajo termina bien, así que un trabajo que SIEMPRE falla se reintentaría en cada
    arranque para siempre, quemando 55 segundos por vez. A los cinco intentos se rinde y anota
    el error, que es lo que el usuario necesita ver."""
    if obtener_config(clave, "") != "1":
        return False
    try:
        intentos = int(obtener_config(f"{clave}_intentos", "0") or 0)
    except ValueError:
        intentos = 0
    if intentos >= INTENTOS_MAXIMOS_DE_FONDO:
        guardar_config(clave, "0")
        anotar_error(f"_trabajo_de_fondo/{clave}",
                     RuntimeError(f"se intentó {intentos} veces y nunca terminó; se deja de "
                                  "reintentar. Se puede volver a pedir a mano desde "
                                  "Administrar → Mantenimiento"))
        return False
    guardar_config(f"{clave}_intentos", str(intentos + 1))
    return True


def _quedo_hecho(clave):
    """El trabajo terminó bien: recién ACÁ se apaga la bandera y se olvidan los intentos."""
    guardar_config(clave, "0")
    guardar_config(f"{clave}_intentos", "0")


def arrancar_tanda_de_fondo():
    """Larga la tanda en un hilo aparte si corresponde. Devuelve si la largó.

    Se llama en cada dibujo de pantalla y casi siempre no hace nada: si ya hay una corriendo,
    si están las dos apagadas o si el cupo del día está gastado, vuelve enseguida."""
    if (obtener_config("fotos_automaticas", "0") != "1"
            and obtener_config("equiv_ficha_automaticas", "0") != "1"
            and obtener_config("descubrimiento_pendiente", "") != "1"
            # El repuntaje pendiente también la larga, aunque esté todo lo demás apagado: si no,
            # después de cambiar las reglas de confianza el puntaje viejo se quedaría para
            # siempre en la base de quien no tiene prendida ninguna tanda automática — que es
            # justo el caso normal. Ver VERSION_CONFIANZA.
            and obtener_config("confianza_pendiente", "") != "1"
            and obtener_config("medidas_pendientes", "") != "1"
            and obtener_config("aplicaciones_pendientes", "") != "1"
            and obtener_config("marcas_repuesto_pendientes", "") != "1"
            and obtener_config("separacion_pendiente", "") != "1"):
        return False

    # El candado se toma ACÁ y no adentro del hilo. Mirar si está tomado y después crear el
    # hilo deja una rendija entre las dos cosas: con dos pestañas abiertas al mismo tiempo,
    # las dos ven el candado libre y las dos crean un hilo. El de adentro no llegaba a hacer
    # trabajo de más —el segundo se iba enseguida— pero esta función devolvía «sí, la largué»
    # cuando no había largado nada, y probándola se veía. Tomándolo antes, la respuesta es la
    # verdad y no hay rendija.
    if not _CANDADO_FONDO.acquire(blocking=False):
        return False

    def correr():
        _HILO_DE_FONDO.corriendo = True      # ver ceder_al_mostrador()
        try:
            _trabajo_de_fondo()
        except Exception as _err:
            anotar_error("arrancar_tanda_de_fondo", _err)
        finally:
            _CANDADO_FONDO.release()

    try:
        threading.Thread(target=correr, daemon=True, name="tanda_de_fondo").start()
        return True
    except RuntimeError as _err:      # el proceso no deja crear más hilos
        # Si el hilo no arrancó hay que soltarlo a mano: nadie más lo va a hacer, y un candado
        # trabado para siempre deja la app sin bajar nada hasta que alguien reinicie el servidor.
        _CANDADO_FONDO.release()
        anotar_error("arrancar_tanda_de_fondo", _err)
        return False


def como_va_la_tanda_de_fondo():
    """Para la pantalla: cuánto falta de cada cosa y a qué ritmo va. Nunca falla."""
    resumen = {"corriendo": _CANDADO_FONDO.locked(),
               "ultima": obtener_config("tanda_fondo_ultima", "")}
    for clave, que in (("fotos", "fotos"), ("equiv", "equiv")):
        condicion = ("p.imagen_url IS NULL "
                     "AND (p.foto_busqueda_estado IS NULL OR p.foto_busqueda_estado = 'error')"
                     if que == "fotos" else "p.ficha_equiv_leida IS NULL")
        try:
            c.execute(f"""SELECT COUNT(*) AS faltan FROM productos p
                          JOIN marcas m ON m.id = p.marca_id
                          WHERE {condicion}
                            AND m.url_ficha_template IS NOT NULL
                            AND m.url_ficha_template <> ''""")
            resumen[f"faltan_{clave}"] = (c.fetchone() or {"faltan": 0})["faltan"] or 0
        except sqlite3.OperationalError as _err:
            anotar_error("como_va_la_tanda_de_fondo", _err)
            resumen[f"faltan_{clave}"] = 0
        try:
            resumen[f"hoy_{clave}"] = int(obtener_config(f"tanda_fondo_{clave}", "0") or 0)
            resumen[f"objetivo_{clave}"] = int(
                obtener_config(f"tanda_{'fotos' if clave == 'fotos' else 'equiv'}_diaria",
                               "500") or 500)
        except ValueError:
            resumen[f"hoy_{clave}"] = 0
            resumen[f"objetivo_{clave}"] = 500
    return resumen


def mostrar_avance_de_tanda(que, clave_config, unidad):
    """El selector de cuánto pedir por día y en qué anda, para las dos tandas de fondo.

    El número de días que falta es lo que hace que el selector signifique algo. «Automático»
    sin eso no dice si termina en una semana o en trece años — y con 70.888 productos a 15 por
    día eran trece años de verdad."""
    resumen = como_va_la_tanda_de_fondo()
    faltan = resumen.get(f"faltan_{que}", 0)
    hoy = resumen.get(f"hoy_{que}", 0)

    clave_widget = f"sel_{clave_config}"
    st.session_state.setdefault(clave_widget,
                                resumen.get(f"objetivo_{que}", 500))
    if st.session_state[clave_widget] not in TANDAS_DISPONIBLES:
        st.session_state[clave_widget] = 500
    st.select_slider(
        f"Cuántas {unidad} por día como máximo:", options=TANDAS_DISPONIBLES,
        key=clave_widget,
        on_change=lambda: guardar_config(clave_config,
                                          str(st.session_state[clave_widget])),
        help="Cada una es una consulta al sitio del proveedor. Subilo hasta donde ese sitio "
             "aguante sin cortarte: si empieza a fallar mucho, bajalo."
    )
    objetivo = int(st.session_state[clave_widget]) or 1

    if not faltan:
        st.caption("✅ No queda nada pendiente de las marcas con catálogo web cargado.")
        return
    dias = (faltan + objetivo - 1) // objetivo
    st.caption(
        f"Faltan **{faltan:,}** · hoy van {hoy:,} de {objetivo:,} · "
        + (f"a este ritmo, **{dias:,} día(s)**" if dias > 1 else "**termina hoy**")
        + (" · 🟢 corriendo ahora" if resumen.get("corriendo") else "")
        + (f" · última vez: {resumen['ultima']}" if resumen.get("ultima") else "")
    )
    # El aviso que hay que dar y no esconder: por ficha, un catálogo enorme no termina nunca,
    # y no es un problema del tamaño de la tanda sino de la cantidad de consultas.
    if dias > 60:
        st.warning(
            f"⚠️ A {objetivo:,} por día son **{dias:,} días**. Leer ficha por ficha tiene un "
            "techo que no lo arregla agrandar la tanda: son "
            f"{faltan:,} consultas al servidor del proveedor, y ese servidor te va a cortar "
            "mucho antes. Para un catálogo de este tamaño, lo que sirve es **pedirle al "
            "proveedor el archivo** (un Excel o un CSV con código, foto y equivalencias) y "
            "cargarlo por 📁 Cargar Excel: son cinco minutos en vez de meses."
        )

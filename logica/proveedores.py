"""El catálogo web del proveedor y las tandas que corren solas en segundo plano.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================================================
# CATÁLOGO WEB DEL PROVEEDOR (fotos y equivalencias)
# ============================================================================================
def direccion_interna(url):
    """¿La dirección apunta adentro del servidor o a una red privada? Devuelve el motivo, o "".

    Las fotos se bajan de links que escriben OTROS: el og:image de una ficha, la miniatura de
    una publicación de Mercado Libre, las <img> de un catálogo. Una página hecha a propósito
    puede poner ahí http://169.254.169.254/… (los datos internos del servidor en la nube) o
    http://localhost:… y la app iría a pedirlo. Se revisa adónde resuelve el nombre, no solo
    cómo está escrito: «algo.com» también puede resolver a 127.0.0.1.
    Para las pruebas con servidores falsos en la misma máquina existe
    EQUIVALENCIAS_PERMITIR_RED_LOCAL=1."""
    import ipaddress
    import socket
    from urllib.parse import urlparse
    if os.environ.get("EQUIVALENCIAS_PERMITIR_RED_LOCAL") == "1":
        return ""
    try:
        partes = urlparse(url)
        if partes.scheme not in ("http", "https") or not partes.hostname:
            return "la dirección no es http ni https"
        for info in socket.getaddrinfo(partes.hostname, partes.port or 443, proto=socket.IPPROTO_TCP):
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                    or ip.is_multicast or ip.is_unspecified):
                return f"la dirección apunta a una red interna ({ip})"
    except ValueError as _err:
        return f"la dirección no es válida ({type(_err).__name__})"
    except OSError:
        # No resuelve acá: o no existe —y el pedido va a fallar solo— o se sale por un proxy,
        # que es el que resuelve. En los dos casos no hay nada interno que proteger.
        return ""
    return ""


def descargar_imagen(url, tiempo_maximo=12, tamano_maximo_mb=8):
    """Baja una imagen de una dirección web. Devuelve (bytes, error).

    Las redirecciones se siguen a mano, revisando cada salto con direccion_interna(): si no, un
    link externo que redirige a una dirección interna pasaba el control igual."""
    import requests
    try:
        for _salto in range(6):
            _motivo = direccion_interna(url)
            if _motivo:
                return None, f"bloqueado: {_motivo}"
            respuesta = requests.get(url, timeout=tiempo_maximo, stream=True, allow_redirects=False,
                                      headers={"User-Agent": "Mozilla/5.0 (compatible; EquivalenciasElChavo/1.0)"})
            if respuesta.is_redirect and respuesta.headers.get("Location"):
                from urllib.parse import urljoin
                url = urljoin(url, respuesta.headers["Location"])
                respuesta.close()
                continue
            break
        else:
            return None, "demasiadas redirecciones"
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
        cfg = None
    try:
        datos = dict(cfg or {})
    except Exception as _err:
        anotar_error("config_portal", _err)
        datos = {}
    # LA DIRECCIÓN DE LA FICHA PUEDE ESTAR EN LA APP. Es la plantilla del catálogo de la marca
    # (Administrar → Marcas, o «Cargar un portal» con el link de un producto), que no es un
    # secreto: los secretos quedan solo para el usuario y la clave. Y un catálogo PÚBLICO,
    # como el de Wega, no necesita nada más que eso: sin usuario ni clave también es un portal.
    if not datos.get("url_ficha"):
        _plantilla = _plantilla_del_catalogo(nombre_marca)
        if _plantilla:
            datos["url_ficha"] = _plantilla
    if not datos.get("url_ficha"):
        return None
    if not all(datos.get(k) for k in ("url_login", "usuario", "clave")):
        datos = {"url_ficha": datos["url_ficha"], "publico": True,
                 "sin_espacios": datos.get("sin_espacios")}
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


def _plantilla_del_catalogo(nombre_marca):
    """La plantilla de la ficha cargada en la app para esa marca, o ""."""
    try:
        fila = c.execute("SELECT url_ficha_template FROM marcas WHERE nombre = ?",
                         (str(nombre_marca or "").strip().upper(),)).fetchone()
        return (fila["url_ficha_template"] or "").strip() if fila else ""
    except sqlite3.OperationalError as _err:
        anotar_error("_plantilla_del_catalogo", _err)
        return ""


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
    if cfg.get("publico"):
        # Sin usuario ni clave: no hay login que hacer. Si el catálogo tiene su usuario en
        # [catalogo.MARCA] —lo que ya usan las fotos—, se entra con ese. La sesión queda igual
        # de solo lectura que la de un portal con clave: los mismos frenos valen para todo.
        base = sesion_para_el_catalogo(nombre_marca) or requests.Session()
        base.headers.update({"User-Agent": "Mozilla/5.0 (compatible; EquivalenciasElChavo/1.0)"})
        solo_lectura = SesionSoloLectura(base, cfg["url_ficha"])
        _SESIONES_PORTAL[nombre_marca] = (solo_lectura, time.time())
        return solo_lectura, None

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


def _html_de_la_ficha_del_portal(nombre_marca, codigo, tiempo_maximo=20):
    """La página de la ficha de ese código en el portal del proveedor. (html, error).

    Una sola visita sirve para todo lo que se lee de la ficha —los autos y los productos que el
    portal muestra al lado—: pedirla dos veces sería el doble de consultas contra el portal."""
    sesion, error = sesion_de_portal(nombre_marca)
    if error:
        return "", error
    cfg = config_portal(nombre_marca)
    # url_de_la_ficha() limpia el código antes de meterlo en la dirección: sin «?», «&» ni
    # «..», con los que una consulta se podría convertir en otra cosa. Si algún portal quiere
    # los códigos con espacios pegados, se configura `sin_espacios = true`.
    if cfg.get("sin_espacios"):
        codigo = re.sub(r"\s+", "", str(codigo or ""))
    url = url_de_la_ficha(cfg["url_ficha"], codigo)
    if not url:
        return "", "Ese código no se puede usar en una dirección."
    try:
        r = sesion.get(url, timeout=tiempo_maximo)
        if r.status_code == 404:
            return "", "El portal no tiene ficha para ese código."
        if r.status_code >= 400:
            return "", f"La ficha respondió {r.status_code}."
        return r.text or "", None
    except Exception as e:
        anotar_error("_html_de_la_ficha_del_portal", e)
        return "", f"No se pudo leer la ficha: {type(e).__name__}"


def _texto_visible(html):
    """El texto que se ve en la página, sin scripts, estilos ni etiquetas."""
    texto = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html or "")
    texto = re.sub(r"<[^>]+>", " ", texto)
    return re.sub(r"\s+", " ", texto)


# De lo que sigue a cada marca en la página, cuántas palabras se miran para buscar el modelo.
# La última marca de la página no tiene otra después que le corte el tramo, y sin tope su
# «resto» llegaba hasta el pie de la página: menús, medidas, equivalencias.
PALABRAS_DESPUES_DE_LA_MARCA = 8


def _autos_del_texto(texto):
    """Los autos que nombra una página: [(marca, modelo)], con modelo "" si no dice cuál.

    Cada modelo va con la marca que lo precede —«CITROËN Jumper III · FIAT Ducato · PEUGEOT
    Boxer»—. Antes se juntaban todas las palabras conocidas sueltas y cada una se guardaba
    como un auto aparte: «BOXER» quedaba con marca BOXER, y también se guardaban como autos
    «APLICACIONES» o «DIAMETRO», que son títulos de la página. Esos datos después contaban en el
    análisis como «el fabricante lo da para el mismo auto», que es una prueba fuerte."""
    autos = []
    for marca, _cat, resto in marcas_vehiculo_en(texto or ""):
        palabras = [w.strip("./") for w in
                    re.split(r"[^A-Z0-9./]+", normalizar_texto(resto))[:PALABRAS_DESPUES_DE_LA_MARCA]]
        modelos = [w for w in palabras
                   if len(w) >= 3 and w in MODELOS_CONOCIDOS
                   and w not in _PALABRAS_DE_MARCA_DE_VEHICULO]
        autos.extend((marca, m) for m in modelos) if modelos else autos.append((marca, ""))
    return sorted(set(autos))


def _autos_para_mostrar(autos):
    return [f"{marca} {modelo}".strip() for marca, modelo in autos]


# --------------------------------------------------------------------------------------------
# LO QUE EL PORTAL MUESTRA JUNTO
# --------------------------------------------------------------------------------------------
# Un distribuidor como JL vende el mismo repuesto en varias marcas —el caño de Cauplas y el de
# otra marca, el sensor de Masser y el de Bosch— y en su portal la ficha de uno muestra los
# otros: «equivalentes», «otras marcas», «alternativas». Es lo que uno relacionaría a mano,
# escrito por alguien que conoce la pieza.
#
# NO DECIDE NADA SOLO, y a propósito: un portal no tiene todas las relaciones, y en la misma
# página suele haber cosas que no son equivalentes —«productos relacionados», el kit que la
# trae, lo último que se miró—. Por eso es UNA prueba más entre las de evidencia_cruzada():
# suma a favor, pero las medidas que no dan, el rubro distinto o el auto distinto la tumban
# igual que a cualquier otra.

# Más que esto nombrados en una sola ficha ya no es «el mismo repuesto en otras marcas»: es un
# listado, un menú o un buscador, y juntar todo con todo sería inventar relaciones.
MAXIMO_PRODUCTOS_POR_FICHA = 10

# Precios con signo o con coma decimal: «$ 10.450» o «10.450,00» no son el código 10450.
_RE_PRECIO_EN_PAGINA = re.compile(r"\$\s*[\d.,]+|\b\d{1,3}(?:\.\d{3})+(?:,\d+)?\b|\b\d+,\d{2}\b")
_RE_PEDAZO_DE_CODIGO = re.compile(r"[A-Za-z0-9][A-Za-z0-9./-]*")


def _normalizar_codigo_escrito(texto):
    return re.sub(r"\s+", " ", str(texto or "").strip().upper())


def productos_nombrados_en_la_pagina(texto, excluir_codigo_clean=""):
    """Los productos de TU catálogo cuyo código aparece escrito en ese texto. [(id, código)].

    Se busca al revés que de costumbre: en vez de adivinar qué es un código y después buscarlo,
    se prueban los pedazos del texto —de a una, dos y tres palabras— contra los códigos que ya
    están cargados. Así entran los códigos con espacios de JL («390 718 060», «CAU 4660»), que
    el extractor de siempre no toma como un solo código.

    Dos cuidados para no ver códigos donde hay otra cosa:
      · los pedazos de varias palabras cuentan solo si están escritos EXACTAMENTE como el código
        de la lista: «GOL 1.6» no es el código «GOL16» aunque sin espacios se lean igual;
      · un número suelto de menos de 6 cifras solo cuenta escrito igual que en la lista —si
        no, cualquier cantidad o año de la página sería un código—, y los precios se sacan
        antes."""
    texto = _RE_PRECIO_EN_PAGINA.sub(" ", texto or "")
    pedazos = _RE_PEDAZO_DE_CODIGO.findall(texto)
    candidatos = {}   # código limpio -> formas escritas
    for i in range(len(pedazos)):
        for n in (1, 2, 3):
            if i + n > len(pedazos):
                break
            escrito = " ".join(pedazos[i:i + n])
            limpio = sanitizar(escrito)
            if len(limpio) < 4 or not any(ch.isdigit() for ch in limpio):
                continue
            candidatos.setdefault(limpio, set()).add(_normalizar_codigo_escrito(escrito))
    candidatos.pop(excluir_codigo_clean or "", None)
    if not candidatos:
        return []
    encontrados = {}
    for _tanda, _marcas in en_tandas(list(candidatos)):
        c.execute(f"""SELECT id, codigo_raw, codigo_clean FROM productos
                      WHERE codigo_clean IN ({_marcas})""", _tanda)
        for r in c.fetchall():
            formas = candidatos[r["codigo_clean"]]
            if _normalizar_codigo_escrito(r["codigo_raw"]) not in formas:
                # Escrito distinto que en la lista: vale solo si en la página es UNA palabra
                # («03C906433A» o «03C-906-433-A») y no es un número corto.
                if not any(" " not in x for x in formas):
                    continue
                if r["codigo_clean"].isdigit() and len(r["codigo_clean"]) < 6:
                    continue
            if codigo_sospechoso(r["codigo_raw"])[0]:
                continue
            encontrados[r["id"]] = r["codigo_raw"]
    return sorted(encontrados.items())


# PORTALES YA CONOCIDOS, públicos y con una ficha por código. Solo entran los que se
# verificaron: la dirección de Wega es «…/catalogo/filtros/detalle/wo-161», el código en
# minúsculas y con el guion, y la página se arma en el servidor —las aplicaciones se leen sin
# JavaScript—. Los de Taranto, Illinois y FISPA no están porque sus catálogos se recorren por
# rubro o por auto, no tienen una ficha por código.
# Igual se prueban antes de guardarlos: una dirección conocida puede cambiar.
PORTALES_CONOCIDOS = {
    "WEGA": "https://www.wega.com.ar/catalogo/filtros/detalle/{codigo_minusculas}",
}


def portal_conocido(nombre_marca):
    """La plantilla ya conocida de esa marca, o "". Acepta «WEGA FILTROS» y parecidos."""
    nombre = str(nombre_marca or "").strip().upper()
    return next((pl for marca, pl in PORTALES_CONOCIDOS.items()
                 if nombre == marca or nombre.split()[:1] == [marca]), "")


def probar_plantilla_de_portal(plantilla, codigos, tiempo_maximo=15):
    """Abre la ficha de esos códigos con la plantilla y cuenta qué se pudo leer. Lista de dicts.

    Es para ver ANTES de guardar si el portal sirve: una dirección bien armada que devuelve la
    página vacía —el contenido lo arma JavaScript después— o la portada del sitio no le sirve a
    nadie, y eso no se nota hasta que la primera tanda vuelve sin nada."""
    ok_url, palabra = _url_solo_de_consulta(plantilla)
    if not ok_url:
        return [{"Código": "", "Resultado": f"❌ La dirección contiene «{palabra}», que suele "
                                            "significar pedir algo. Usá la de la ficha."}]
    sesion = requests.Session()
    sesion.headers.update({"User-Agent": "Mozilla/5.0 (compatible; EquivalenciasElChavo/1.0)"})
    solo_lectura = SesionSoloLectura(sesion, plantilla)
    salida = []
    for codigo, codigo_clean in codigos:
        fila = {"Código": codigo, "Resultado": "", "Autos": "", "Productos tuyos": 0}
        url = url_de_la_ficha(plantilla, codigo)
        if not url:
            fila["Resultado"] = "❌ ese código no se puede usar en una dirección"
            salida.append(fila)
            continue
        try:
            r = solo_lectura.get(url, timeout=tiempo_maximo)
        except Exception as e:
            anotar_error("probar_plantilla_de_portal", e)
            fila["Resultado"] = f"❌ no se pudo abrir ({type(e).__name__})"
            salida.append(fila)
            continue
        if r.status_code != 200:
            fila["Resultado"] = f"❌ la página respondió {r.status_code}"
            salida.append(fila)
            continue
        texto = _texto_visible(r.text or "")
        autos = _autos_del_texto(texto)
        nombrados = [pid for pid, _cod in productos_nombrados_en_la_pagina(texto, codigo_clean)]
        _autos_txt = _autos_para_mostrar(autos)
        fila["Autos"] = ", ".join(_autos_txt[:6]) + ("…" if len(_autos_txt) > 6 else "")
        fila["Productos tuyos"] = len(nombrados)
        if codigo_clean and codigo_clean not in sanitizar(texto):
            fila["Resultado"] = ("⚠️ la página abre pero no muestra el código: puede que arme "
                                 "el contenido con JavaScript, o que no sea la ficha")
        elif len(texto) < 300:
            fila["Resultado"] = "⚠️ la página casi no tiene texto"
        else:
            fila["Resultado"] = "✅ se lee la ficha"
        salida.append(fila)
    return salida


def cuantos_juntos_en_portales():
    """Cuántos pares vio juntos algún portal. Sirve para saber si el análisis quedó viejo."""
    try:
        return c.execute("SELECT COUNT(*) FROM productos_juntos_en_portal").fetchone()[0]
    except sqlite3.OperationalError as _err:
        anotar_error("cuantos_juntos_en_portales", _err)
        return 0


def leer_fichas_del_portal(marca_id, nombre_marca, cuantos=25, progreso=None, pausa=0.7):
    """Recorre las fichas del portal de esa marca que todavía no se leyeron. De cada ficha saca
    los autos (como hasta ahora) y los productos de tu catálogo que la ficha muestra al lado.

    Los pares que salen van a la cola de revisión en su propia lista, «PORTAL …», y además
    quedan anotados: si el mismo par llega por otro camino —el barrido, un código de fábrica—,
    el análisis lo cuenta como una prueba más a favor (ver evidencia_cruzada()).

    Devuelve un resumen: fichas leídas, con autos, con productos, listados descartados, pares
    nuevos para revisar, el nombre de la lista y el primer error si no se pudo entrar."""
    resumen = {"leidas": 0, "con_autos": 0, "con_productos": 0, "listados": 0,
               "sin_ficha": 0, "pares": 0, "nuevos": 0, "lote": "", "error": ""}
    _sesion, error = sesion_de_portal(nombre_marca)
    if error:
        resumen["error"] = error
        return resumen
    # Primero lo que tiene stock: si algo va a salir del mostrador hoy, que sea eso lo que
    # quede relacionado primero.
    c.execute("""SELECT p.id, p.codigo_raw, p.codigo_clean, p.descripcion FROM productos p
                 WHERE p.marca_id = ?
                   AND p.id NOT IN (SELECT producto_id FROM fichas_de_portal_leidas
                                     WHERE portal = ?)
                 ORDER BY (COALESCE(p.stock, 0) > 0) DESC, p.id LIMIT ?""",
              (marca_id, nombre_marca, int(cuantos)))
    pendientes = [dict(r) for r in c.fetchall()]
    pares, leidas = [], []
    fallas_seguidas = 0
    for i, prod in enumerate(pendientes):
        html, err = _html_de_la_ficha_del_portal(nombre_marca, prod["codigo_raw"])
        if err and ("tope" in err or "cerró sola" in err or "PermissionError" in err):
            resumen["error"] = err
            break
        # Solo «no hay ficha para ese código» queda anotado como leído: es una respuesta. Un
        # error de red o del servidor no lo es, y anotarlo dejaría esas fichas sin leer para
        # siempre. Si fallan varias seguidas, el portal está caído o la dirección está mal: se
        # corta en vez de seguir golpeando.
        if err and "no tiene ficha" not in err:
            fallas_seguidas += 1
            resumen["sin_ficha"] += 1
            if fallas_seguidas >= 5:
                resumen["error"] = f"{fallas_seguidas} fichas seguidas sin poder abrirse: {err}"
                break
        elif err:
            fallas_seguidas = 0
            resumen["sin_ficha"] += 1
            leidas.append((nombre_marca, prod["id"], None))
        else:
            fallas_seguidas = 0
            texto = _texto_visible(html)
            autos = _autos_del_texto(texto)
            if guardar_autos_de_ficha(prod["codigo_raw"], nombre_marca, autos):
                resumen["con_autos"] += 1
            nombrados = [pid for pid, _cod in productos_nombrados_en_la_pagina(
                texto, prod["codigo_clean"]) if pid != prod["id"]]
            if len(nombrados) > MAXIMO_PRODUCTOS_POR_FICHA:
                resumen["listados"] += 1
                nombrados = []
            elif nombrados:
                resumen["con_productos"] += 1
            pares.extend((min(prod["id"], o), max(prod["id"], o), prod["id"]) for o in nombrados)
            leidas.append((nombre_marca, prod["id"], len(nombrados)))
        resumen["leidas"] += 1
        if progreso:
            progreso((i + 1) / len(pendientes), f"{i + 1} de {len(pendientes)}...")
        if pausa:
            time.sleep(pausa)   # pausa entre pedidos, a propósito: ver el panel
    # Juntas: una ficha marcada como leída sin sus pares guardados no se vuelve a leer, y esos
    # pares se perderían para siempre.
    with transaccion():
        c.executemany("""INSERT OR REPLACE INTO fichas_de_portal_leidas
                         (portal, producto_id, productos_juntos) VALUES (?, ?, ?)""", leidas)
        c.executemany("""INSERT OR IGNORE INTO productos_juntos_en_portal
                         (producto_a_id, producto_b_id, portal, producto_origen_id)
                         VALUES (?, ?, ?, ?)""",
                      [(a, b, nombre_marca, o) for a, b, o in pares])
    resumen["pares"] = len({(a, b) for a, b, _o in pares})
    if pares:
        resumen["lote"] = f"PORTAL {nombre_marca} · {datetime.now():%d/%m %H:%M}"
        resumen["nuevos"] = guardar_equivalencias_pendientes(
            [(a, b) for a, b, _o in pares], "portal", resumen["lote"])
    return resumen


# --------------------------------------------------------------------------------------------
# CATÁLOGOS DE FABRICANTE, SOLOS
# --------------------------------------------------------------------------------------------
# Tus listas nombran piezas de fabricantes que no son proveedores tuyos: «BOMBA DE AGUA ... SKF
# VKPC85304», «BUJIA NAFTA ... NGK= BP5HS», «FILTRO ... MANN W 712/95». Esos fabricantes publican
# una ficha por código con los números originales y las equivalencias de otras marcas. Si en esa
# ficha aparece el código de OTRO producto tuyo —un número de fábrica, la misma pieza de otra
# marca—, es una relación escrita por el fabricante de la pieza.
#
# Igual que el portal del proveedor, NO DECIDE NADA SOLO: queda anotado en
# productos_juntos_en_portal como «CATÁLOGO SKF», suma a favor en evidencia_cruzada(), y los
# pares que no estaban van a la cola de revisión. Los vetos de siempre los tumban.
#
# Solo entran los fabricantes con UNA DIRECCIÓN POR CÓDIGO, verificada con fichas reales que
# publican los buscadores (el servidor donde se armó esto no llega a esos sitios):
#   · SKF:          automotive.skf.com/eur/es/product-catalogue/VKMA01250
#   · MANN-FILTER:  mann-filter.com/en/catalog/international/search-results/product.html/
#                   w712/95_mann-filter.html  (la barra del código es parte de la dirección)
#   · NGK (bujías): sparkplug-crossreference.com/convert/NGK_PN/BKR6E, una tabla de
#                   equivalencias de bujías por código NGK. No es de NGK: la ficha oficial lleva
#                   un número de stock que no sale del código.
# Quedaron afuera, a propósito, los que buscan con un formulario o muestran listados por rubro:
# FRAM, MAHLE, BOSCH, TARANTO, CORVEN, FISPA. Y ILLINOIS, que publica un PDF por juego con las
# piezas que trae adentro: juntaría cada juego con sus juntas, que no son equivalentes.

_RE_CODIGO_PARA_LA_DIRECCION = re.compile(r"[^A-Za-z0-9/-]")


def _codigo_para_la_direccion(codigo, conservar_barra=False):
    """El código listo para ir adentro de una dirección: sin espacios ni nada raro. Sin «..» y
    sin barras sueltas al principio, por lo mismo que url_de_la_ficha()."""
    limpio = _RE_CODIGO_PARA_LA_DIRECCION.sub("", str(codigo or ""))
    if not conservar_barra:
        limpio = limpio.replace("/", "")
    limpio = limpio.strip("/-")
    return "" if (not limpio or ".." in limpio or "//" in limpio) else limpio


CATALOGOS_DE_FABRICANTE = {
    "SKF": {
        # Sin letra al final: en «SKF VKMA 02410 A INA 530020310» la A es de lo que sigue.
        "cita": re.compile(r"\bSKF\b[\s:=.-]*(VK[A-Z]{1,4}\s?\d{4,5})\b"),
        "url": lambda cod: ("https://automotive.skf.com/eur/es/product-catalogue/"
                            + _codigo_para_la_direccion(cod).upper()),
        "sitio": "automotive.skf.com",
    },
    "MANN-FILTER": {
        "cita": re.compile(r"\bMANN(?:[\s-]*FILTER)?\b[\s:=.-]*"
                           r"([A-Z]{1,3}\s?\d{2,4}(?:/\d{1,3})?(?:\s?[A-Z]{1,2})?)\b"),
        "url": lambda cod: ("https://www.mann-filter.com/en/catalog/international/search-results/"
                            "product.html/"
                            + _codigo_para_la_direccion(cod, conservar_barra=True).lower()
                            + "_mann-filter.html"),
        "sitio": "mann-filter.com",
    },
    "NGK": {
        "cita": re.compile(r"\bNGK\b[\s:=.-]*([A-Z]{1,6}\d{1,2}[A-Z]{0,5}(?:-\d{1,2})?)\b"),
        "url": lambda cod: ("https://www.sparkplug-crossreference.com/convert/NGK_PN/"
                            + _codigo_para_la_direccion(cod).upper()),
        "sitio": "sparkplug-crossreference.com",
    },
}

# La pausa entre una ficha de catálogo y la siguiente. Sin tope por día (ver
# MINUTOS_DE_DESCANSO): la pausa corta queda para no pedirle diez fichas por segundo a un sitio
# ajeno, que es lo que dispara un bloqueo.
PAUSA_ENTRE_FICHAS_DE_CATALOGO = 0.3
# Con más de esto nombrados, la ficha es un listado y no la de una pieza: ver
# MAXIMO_PRODUCTOS_POR_FICHA. Acá es más alto porque la ficha de un fabricante lista a propósito
# todos los números originales de la pieza.
MAXIMO_PRODUCTOS_POR_FICHA_DE_FABRICANTE = 25
# Si un código lo citan muchos productos, no se juntan todos con todo lo de la ficha.
MAXIMO_QUE_LO_CITAN = 12


def _codigo_citado(codigo):
    """La forma con que se guarda un código citado: mayúsculas y sin espacios, con la barra."""
    return re.sub(r"\s+", "", str(codigo or "").upper())


def codigos_citados_en_tu_catalogo(nombre_catalogo):
    """{código: [ids de los productos que lo citan]} para ese fabricante, leyendo las
    descripciones de toda la base."""
    patron = CATALOGOS_DE_FABRICANTE[nombre_catalogo]["cita"]
    salida = {}
    c.execute("SELECT id, descripcion FROM productos WHERE descripcion LIKE ?",
              (f"%{nombre_catalogo.split('-')[0]}%",))
    for fila in c.fetchall():
        for cod in patron.findall(normalizar_texto(fila["descripcion"] or "")):
            salida.setdefault(_codigo_citado(cod), []).append(fila["id"])
    return salida


def leer_catalogo_de_fabricante(nombre_catalogo, cuantos=20, pausa=PAUSA_ENTRE_FICHAS_DE_CATALOGO,
                                progreso=None, sesion=None):
    """Lee las fichas del fabricante para los códigos que tus descripciones citan y todavía no
    se leyeron, primero los más citados. Devuelve un resumen como leer_fichas_del_portal().

    De cada ficha salen los productos tuyos que nombra. Se juntan con los que citan el código:
    «la bomba de FISPA que dice SKF VKPC85304» con el número original que la ficha de SKF lista.
    La ficha tiene que mostrar el código pedido; si no, no es la ficha (el sitio devolvió la
    portada o un buscador) y se anota como «sin ficha»."""
    cat = CATALOGOS_DE_FABRICANTE[nombre_catalogo]
    portal = f"CATÁLOGO {nombre_catalogo}"
    resumen = {"leidas": 0, "con_productos": 0, "listados": 0, "sin_ficha": 0, "pares": 0,
               "nuevos": 0, "lote": "", "error": "", "pendientes": 0, "fallidas": 0}
    citados = codigos_citados_en_tu_catalogo(nombre_catalogo)
    c.execute("SELECT codigo FROM fichas_de_catalogo_leidas WHERE catalogo = ?",
              (nombre_catalogo,))
    ya = {r[0] for r in c.fetchall()}
    ya |= _fallaron_hoy(f"catalogo:{nombre_catalogo}")      # esas, mañana
    faltan = sorted((cod for cod in citados if cod not in ya),
                    key=lambda cod: (-len(set(citados[cod])), cod))
    resumen["pendientes"] = len(faltan)
    if not faltan:
        return resumen
    if sesion is None:
        base = requests.Session()
        base.headers.update({"User-Agent": "Mozilla/5.0 (compatible; EquivalenciasElChavo/1.0)"})
        sesion = SesionSoloLectura(base, cat["url"]("X1"))
    pares, leidas, fallas_seguidas, fallas_de_red = [], [], 0, []
    tanda = faltan[:int(cuantos)]
    for i, cod in enumerate(tanda):
        url = cat["url"](cod)
        texto, err, foto = "", None, ""
        try:
            r = sesion.get(url, timeout=20)
            if r.status_code == 404:
                err = "sin ficha"
            elif r.status_code >= 400:
                err = f"respondió {r.status_code}"
            elif "pdf" in (r.headers.get("Content-Type") or "").lower():
                import io as _io
                import pdfplumber
                with pdfplumber.open(_io.BytesIO(r.content)) as _pdf:
                    texto = " ".join((pg.extract_text() or "") for pg in _pdf.pages[:5])
            else:
                texto = _texto_visible(r.text or "")
                foto = foto_principal_de_la_pagina(r.text or "", url)
        except PermissionError as e:
            resumen["error"] = str(e)
            break
        except Exception as e:
            anotar_error("leer_catalogo_de_fabricante", e)
            err = type(e).__name__
        if not err and sanitizar(cod) not in sanitizar(texto):
            err = "sin ficha"
        if err == "sin ficha":
            fallas_seguidas = 0
            resumen["sin_ficha"] += 1
            leidas.append((nombre_catalogo, cod, None))
        elif err:
            # Un error de red o del servidor no es una respuesta: no se anota como leído. Varios
            # seguidos quieren decir que el sitio está caído o nos está rechazando.
            fallas_seguidas += 1
            resumen["sin_ficha"] += 1
            resumen["fallidas"] += 1
            fallas_de_red.append((cod, err))
            if fallas_seguidas >= 5:
                resumen["error"] = f"{fallas_seguidas} fichas seguidas sin poder abrirse: {err}"
                break
        else:
            fallas_seguidas = 0
            los_que_citan = sorted(set(citados[cod]))[:MAXIMO_QUE_LO_CITAN]
            nombrados = [pid for pid, _c in productos_nombrados_en_la_pagina(texto, sanitizar(cod))
                         if pid not in los_que_citan]
            if len(nombrados) > MAXIMO_PRODUCTOS_POR_FICHA_DE_FABRICANTE:
                resumen["listados"] += 1
                nombrados = []
            elif nombrados:
                resumen["con_productos"] += 1
            pares.extend((min(a, b), max(a, b), a) for a in los_que_citan for b in nombrados)
            leidas.append((nombre_catalogo, cod, len(nombrados)))
            # La foto del fabricante, para los productos tuyos que citan el código y todavía no
            # tienen: es la misma pieza, y le sirve a la búsqueda por cámara.
            if foto:
                resumen["con_foto"] = resumen.get("con_foto", 0) + proponer_foto(los_que_citan,
                                                                                  foto)
        resumen["leidas"] += 1
        if progreso:
            progreso((i + 1) / len(tanda), f"{i + 1} de {len(tanda)}...")
        if pausa and i + 1 < len(tanda):
            time.sleep(pausa)
    # Lo que falló por la red tres días distintos se da por leído «sin ficha» (ver _anotar_fallas()).
    # Las que respondieron dejan de contar como fallidas; las rendidas siguen anotadas, que es lo
    # que usa «Reintentar las que fallaron».
    _fuente = f"catalogo:{nombre_catalogo}"
    _olvidar_fallas(_fuente, [cod for _n, cod, _j in leidas])
    leidas.extend((nombre_catalogo, cod, None) for cod in _anotar_fallas(_fuente, fallas_de_red))
    with transaccion():
        c.executemany("""INSERT OR REPLACE INTO fichas_de_catalogo_leidas
                         (catalogo, codigo, productos_juntos) VALUES (?, ?, ?)""", leidas)
        c.executemany("""INSERT OR IGNORE INTO productos_juntos_en_portal
                         (producto_a_id, producto_b_id, portal, producto_origen_id)
                         VALUES (?, ?, ?, ?)""",
                      [(a, b, portal, o) for a, b, o in pares])
    resumen["pares"] = len({(a, b) for a, b, _o in pares})
    if pares:
        resumen["lote"] = f"{portal} · {datetime.now():%d/%m %H:%M}"
        resumen["nuevos"] = guardar_equivalencias_pendientes(
            [(a, b) for a, b, _o in pares], "catalogo_fabricante", resumen["lote"])
    return resumen


def estado_de_los_catalogos_de_fabricante():
    """Para la pantalla: por fabricante, cuántos códigos citan tus listas, cuántos se leyeron y
    cuántos pares salieron. [dict]."""
    salida = []
    for nombre, cat in CATALOGOS_DE_FABRICANTE.items():
        citados = codigos_citados_en_tu_catalogo(nombre)
        fila = c.execute("""SELECT COUNT(*), SUM(productos_juntos > 0)
                            FROM fichas_de_catalogo_leidas WHERE catalogo = ?""",
                         (nombre,)).fetchone()
        pares = c.execute("SELECT COUNT(*) FROM productos_juntos_en_portal WHERE portal = ?",
                          (f"CATÁLOGO {nombre}",)).fetchone()[0]
        salida.append({"Fabricante": nombre, "Sitio": cat["sitio"],
                       "Códigos citados": len(citados),
                       "Productos que los citan": len({i for v in citados.values() for i in v}),
                       "Fichas leídas": fila[0] or 0, "Con productos tuyos": fila[1] or 0,
                       "Pares": pares,
                       "Pausado hasta": obtener_config(f"catalogo_pausado_{nombre}", "")})
    return salida


@st.cache_data(ttl=300, show_spinner=False)
def estado_de_los_catalogos_de_fabricante_guardado():
    """estado_de_los_catalogos_de_fabricante() con caché: lee las descripciones de toda la base
    tres veces, y el panel se dibuja en cada toque."""
    return estado_de_los_catalogos_de_fabricante()


def catalogos_de_fabricante_automaticos():
    """¿Se leen solos? Prendido de fábrica: no hace falta cargar nada, las direcciones son
    públicas y los códigos salen de tus descripciones. Se apaga en Administrar."""
    return obtener_config("catalogos_fabricante_automaticos", "1") == "1"


def _catalogo_de_fabricante_pausado(nombre):
    hasta = obtener_config(f"catalogo_pausado_{nombre}", "")
    return bool(hasta) and hasta > datetime.now().strftime("%Y-%m-%d %H:%M")


def tanda_de_catalogos_de_fabricante(cupo):
    """Una vuelta de la tarea de fondo: lee hasta `cupo` fichas, repartidas entre los
    fabricantes que no estén pausados. Devuelve cuántas quedaron RESUELTAS (con ficha o «sin
    ficha»): las que fallaron por la red no se anotan como leídas y vuelven a salir en la vuelta
    siguiente, así que contarlas dejaría a la tarea de fondo girando sobre ellas sin avanzar. Si
    más de la mitad de una tanda falla, ese sitio también se pausa. Si un sitio falla cinco veces
    seguidas, se pausa una hora: seguir golpeándolo no sirve y puede terminar en un bloqueo."""
    consultadas = 0
    for nombre in CATALOGOS_DE_FABRICANTE:
        if consultadas >= cupo:
            break
        if _catalogo_de_fabricante_pausado(nombre):
            continue
        ceder_al_mostrador()
        res = leer_catalogo_de_fabricante(nombre, cuantos=min(PRODUCTOS_POR_SUBTANDA,
                                                              cupo - consultadas))
        # Con max(): la ficha que corta la tanda (la quinta falla seguida) cuenta como fallida
        # pero no llega a contarse como leída, y la resta daba -1.
        consultadas += max(res["leidas"] - res.get("fallidas", 0), 0)
        if res["error"] or res.get("fallidas", 0) * 2 > res["leidas"]:
            guardar_config(f"catalogo_pausado_{nombre}",
                           (datetime.now() + timedelta(minutes=MINUTOS_DE_DESCANSO_SI_FALLA)
                            ).strftime("%Y-%m-%d %H:%M"))
    return consultadas


# --------------------------------------------------------------------------------------------
# MERCADO LIBRE
# --------------------------------------------------------------------------------------------
# Las publicaciones de autopartes traen el número de pieza, la marca y, en el título, las
# equivalencias con las que el vendedor quiere que lo encuentren: «Sensor Map Fispa 40011 Bosch
# 0261230027 Ford Fiesta». De ahí salen dos cosas:
#   · UNA PISTA MÁS para relacionar productos, igual que el portal del proveedor: si las
#     publicaciones de tu código nombran el código de otro producto tuyo, cuenta a favor en
#     evidencia_cruzada() como «MERCADO LIBRE», y el par va a revisión. No decide nada solo: el
#     que publica escribe lo que le conviene.
#   · EL PRECIO DE MERCADO: la mediana de lo que se publica con ese código, para ver qué precios
#     de tus listas quedaron atrasados o pasados.
#
# La búsqueda de Mercado Libre pide un token. Se saca con una aplicación de desarrollador
# (gratis, en developers.mercadolibre.com.ar → «Crear aplicación»), y sus datos van en los
# secretos de Streamlit, en su propia sección:
#
#     [mercadolibre]
#     client_id     = "1234567890"
#     client_secret = "abc..."
#
# En los secretos y no en la base: la base se sube a GitHub con cada copia.
ML_API = "https://api.mercadolibre.com"
ML_SITIO = "MLA"
PAUSA_ENTRE_BUSQUEDAS_DE_MERCADO_LIBRE = 0.15
_TOKEN_DE_MERCADO_LIBRE = del_proceso("token_de_mercado_libre", dict)


def config_mercado_libre():
    """{client_id, client_secret} de los secretos, o None si no está cargado."""
    try:
        cfg = dict(secretos_app().get("mercadolibre") or {})
    except Exception as _err:
        anotar_error("config_mercado_libre", _err)
        return None
    return cfg if cfg.get("client_id") and cfg.get("client_secret") else None


def token_de_mercado_libre():
    """(token, error). Se pide con los datos de la aplicación y se guarda en memoria hasta un
    minuto antes de que venza: pedir uno por búsqueda es maltratar el servicio."""
    cfg = config_mercado_libre()
    if not cfg:
        return None, ("Falta cargar la aplicación de Mercado Libre en los secretos "
                      "([mercadolibre] con client_id y client_secret).")
    guardado = _TOKEN_DE_MERCADO_LIBRE.get("token")
    if guardado and _TOKEN_DE_MERCADO_LIBRE.get("vence", 0) > time.time() + 60:
        return guardado, None
    try:
        r = requests.post(f"{ML_API}/oauth/token", timeout=20,
                          data={"grant_type": "client_credentials",
                                "client_id": cfg["client_id"],
                                "client_secret": cfg["client_secret"]},
                          headers={"Accept": "application/json"})
        datos = r.json() if r.content else {}
    except Exception as e:
        anotar_error("token_de_mercado_libre", e)
        return None, f"No se pudo pedir el token ({type(e).__name__})."
    if r.status_code != 200 or not datos.get("access_token"):
        # El mensaje de Mercado Libre, sin los datos que se mandaron.
        return None, (f"Mercado Libre no dio el token ({r.status_code}: "
                      f"{str(datos.get('message') or datos.get('error') or '')[:120]}). "
                      "Revisá el client_id y el client_secret.")
    _TOKEN_DE_MERCADO_LIBRE.update(token=datos["access_token"],
                                   vence=time.time() + int(datos.get("expires_in") or 3600))
    return datos["access_token"], None


def buscar_en_mercado_libre(texto, limite=20):
    """([publicaciones], error). Cada publicación: título, precio, moneda, link y atributos."""
    token, error = token_de_mercado_libre()
    if error:
        return [], error
    try:
        r = requests.get(f"{ML_API}/sites/{ML_SITIO}/search", timeout=20,
                         params={"q": str(texto or "")[:80], "limit": int(limite)},
                         headers={"Authorization": f"Bearer {token}"})
    except Exception as e:
        anotar_error("buscar_en_mercado_libre", e)
        return [], f"No se pudo buscar ({type(e).__name__})."
    if r.status_code in (401, 403):
        _TOKEN_DE_MERCADO_LIBRE.clear()
        return [], f"Mercado Libre rechazó la búsqueda ({r.status_code})."
    if r.status_code != 200:
        return [], f"Mercado Libre respondió {r.status_code}."
    salida = []
    for it in (r.json() or {}).get("results") or []:
        atributos = {str(a.get("id") or ""): str(a.get("value_name") or "")
                     for a in it.get("attributes") or []}
        salida.append({"titulo": str(it.get("title") or ""), "precio": it.get("price"),
                       "moneda": it.get("currency_id") or "", "link": it.get("permalink") or "",
                       "atributos": atributos,
                       "foto": _foto_grande_de_mercado_libre(it.get("thumbnail") or "")})
    return salida, None


def _foto_grande_de_mercado_libre(miniatura):
    """La miniatura de la búsqueda viene chica («…-I.jpg»); «-O» es la original. Y por https."""
    url = str(miniatura or "").strip()
    if not url.startswith(("http://", "https://")):
        return ""
    url = "https://" + url.split("://", 1)[1]
    return re.sub(r"-[A-Z]\.(jpg|jpeg|png|webp)$", r"-O.\1", url, flags=re.I)


def proponer_foto(producto_ids, url_foto):
    """Deja la foto de internet como la de esos productos, si todavía no tienen ninguna. La
    bajan después las tandas de fondo (ver bajar_fotos_pendientes()), que calculan la firma
    visual que usa la búsqueda por cámara. Nunca pisa una foto que ya estaba, y no se la pone a
    los códigos de fábrica, que no se muestran. Devuelve a cuántos se la puso."""
    ids = sorted({int(i) for i in producto_ids if i})
    if not ids or not str(url_foto or "").startswith("https://"):
        return 0
    puestas = 0
    for tanda, marcas in en_tandas(ids):
        c.execute(f"""UPDATE productos SET imagen_url = ?
                      WHERE id IN ({marcas}) AND imagen_url IS NULL
                        AND NOT EXISTS (SELECT 1 FROM producto_fotos f
                                        WHERE f.producto_id = productos.id)
                        AND marca_id NOT IN (SELECT id FROM marcas WHERE tipo = 'OEM')""",
                  [url_foto] + list(tanda))
        puestas += c.rowcount or 0
    if puestas:
        guardar_config("fotos_de_internet_pendientes", "1")
    return puestas


_RE_FOTO_PRINCIPAL = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)'
    r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)',
    re.I)


def foto_principal_de_la_pagina(html, url_de_la_pagina):
    """La foto que la página declara como principal (og:image, la de la vista previa de
    WhatsApp), con la dirección completa. "" si no declara ninguna."""
    from urllib.parse import urljoin
    m = _RE_FOTO_PRINCIPAL.search(html or "")
    if not m:
        return ""
    return urljoin(url_de_la_pagina, (m.group(1) or m.group(2) or "").strip())


def _codigo_sin_la_marca_pegada(codigo):
    """«40011FISPA» -> «40011»: como lo escribe cualquiera que no sea FISPA."""
    limpio = sanitizar(codigo)
    sub = _submarca_del_codigo(codigo)
    return limpio[:-len(sub)] if sub and limpio.endswith(sub) and len(limpio) > len(sub) else limpio


def publicaciones_de_tu_producto(publicaciones, codigo, marca):
    """Las publicaciones que son de ESE producto: el código aparece en el título o como número de
    pieza, y —si no es un código de fábrica— la marca también. Un código corto o genérico trae de
    todo, y sin este filtro el precio y las pistas serían de otras piezas."""
    cod = _codigo_sin_la_marca_pegada(codigo)
    marcas = {sanitizar(x) for x in (marca, _submarca_del_codigo(codigo)) if x}
    salida = []
    for pub in publicaciones:
        en_texto = sanitizar(pub["titulo"] + " " + " ".join(pub["atributos"].values()))
        numero = sanitizar(pub["atributos"].get("PART_NUMBER", "") + " "
                           + pub["atributos"].get("MPN", ""))
        if cod not in en_texto and cod not in numero:
            continue
        if marcas and not any(m and m in en_texto for m in marcas):
            continue
        salida.append(pub)
    return salida


def _mediana(valores):
    v = sorted(valores)
    if not v:
        return None
    return v[len(v) // 2] if len(v) % 2 else (v[len(v) // 2 - 1] + v[len(v) // 2]) / 2


def leer_mercado_libre(cuantos=30, pausa=PAUSA_ENTRE_BUSQUEDAS_DE_MERCADO_LIBRE, progreso=None):
    """Busca en Mercado Libre los productos que todavía no se buscaron —primero los que tenés
    en stock— y guarda las pistas y el precio de mercado. Devuelve un resumen."""
    resumen = {"buscados": 0, "con_publicaciones": 0, "con_productos": 0, "pares": 0,
               "nuevos": 0, "con_precio": 0, "lote": "", "error": ""}
    _token, error = token_de_mercado_libre()
    if error:
        resumen["error"] = error
        return resumen
    c.execute(f"""SELECT p.id, p.codigo_raw, p.codigo_clean, m.nombre AS marca, m.tipo AS tipo
                 FROM productos p JOIN marcas m ON m.id = p.marca_id
                 WHERE p.id NOT IN (SELECT producto_id FROM mercado_libre_leidos)
                   AND LENGTH(p.codigo_clean) >= 5
                   AND {_no_fallo_hoy("mercado_libre", "p.id")}
                 ORDER BY (COALESCE(p.stock, 0) > 0) DESC, (m.tipo = 'OEM'), p.id LIMIT ?""",
              (int(cuantos),))
    pendientes = [dict(r) for r in c.fetchall()]
    pares, leidos, fallas_seguidas, fallas_de_red = [], [], 0, []
    for i, prod in enumerate(pendientes):
        es_de_fabrica = prod["tipo"] == "OEM"
        marca = "" if es_de_fabrica else (_submarca_del_codigo(prod["codigo_raw"]) or prod["marca"])
        pubs, err = buscar_en_mercado_libre(
            f"{_codigo_sin_la_marca_pegada(prod['codigo_raw'])} {marca}".strip())
        if err:
            fallas_seguidas += 1
            fallas_de_red.append((prod["id"], err))
            if fallas_seguidas >= 5:
                resumen["error"] = err
                break
            continue
        fallas_seguidas = 0
        suyas = publicaciones_de_tu_producto(pubs, prod["codigo_raw"], marca)
        mediana, n_precios = None, 0
        if suyas:
            resumen["con_publicaciones"] += 1
            # La foto de la primera publicación que tenga, para la búsqueda por cámara.
            _foto = next((p["foto"] for p in suyas if p.get("foto")), "")
            if _foto and not es_de_fabrica:
                resumen["con_foto"] = resumen.get("con_foto", 0) + proponer_foto([prod["id"]], _foto)
            texto = " · ".join(p["titulo"] + " " + " ".join(p["atributos"].values())
                               for p in suyas)
            nombrados = [pid for pid, _c in productos_nombrados_en_la_pagina(
                texto, prod["codigo_clean"]) if pid != prod["id"]]
            if 0 < len(nombrados) <= MAXIMO_PRODUCTOS_POR_FICHA_DE_FABRICANTE:
                resumen["con_productos"] += 1
                pares.extend((min(prod["id"], o), max(prod["id"], o), prod["id"])
                             for o in nombrados)
            precios = [float(p["precio"]) for p in suyas
                       if p["moneda"] == "ARS" and isinstance(p["precio"], (int, float))
                       and p["precio"] > 0]
            # El precio sirve para lo que vendés, no para el número de fábrica.
            if len(precios) >= 2 and not es_de_fabrica:
                mediana, n_precios = _mediana(precios), len(precios)
                resumen["con_precio"] += 1
        leidos.append((prod["id"], len(suyas), mediana, n_precios))
        resumen["buscados"] += 1
        if progreso:
            progreso((i + 1) / len(pendientes), f"{i + 1} de {len(pendientes)}...")
        if pausa and i + 1 < len(pendientes):
            time.sleep(pausa)
    # Lo que falló tres días distintos se da por buscado, sin publicaciones (ver _anotar_fallas()).
    _olvidar_fallas("mercado_libre", [pid for pid, _p, _m, _n in leidos])
    leidos.extend((pid, None, None, 0) for pid in _anotar_fallas("mercado_libre", fallas_de_red))
    with transaccion():
        c.executemany("""INSERT OR REPLACE INTO mercado_libre_leidos
                         (producto_id, publicaciones, precio_mediano, precios) VALUES (?, ?, ?, ?)""",
                      leidos)
        c.executemany("""INSERT OR IGNORE INTO productos_juntos_en_portal
                         (producto_a_id, producto_b_id, portal, producto_origen_id)
                         VALUES (?, ?, 'MERCADO LIBRE', ?)""", pares)
    resumen["pares"] = len({(a, b) for a, b, _o in pares})
    if pares:
        resumen["lote"] = f"MERCADO LIBRE · {datetime.now():%d/%m %H:%M}"
        resumen["nuevos"] = guardar_equivalencias_pendientes(
            [(a, b) for a, b, _o in pares], "mercado_libre", resumen["lote"])
    return resumen


def precios_lejos_de_mercado_libre(veces=1.6, limite=200):
    """Tus productos cuyo precio de lista está a más de `veces` del que se publica en Mercado
    Libre, para un lado o para el otro. Primero los que tenés en stock y los más alejados."""
    try:
        c.execute("""SELECT p.codigo_raw AS "Código", m.nombre AS "Marca",
                            p.descripcion AS "Descripción", p.precio AS "Tu precio",
                            l.precio_mediano AS "Mercado Libre", l.precios AS "Publicaciones",
                            COALESCE(p.stock, 0) AS "Stock"
                     FROM mercado_libre_leidos l
                     JOIN productos p ON p.id = l.producto_id
                     JOIN marcas m ON m.id = p.marca_id
                     WHERE l.precio_mediano > 0 AND p.precio > 0""")
        filas = [dict(r) for r in c.fetchall()]
    except sqlite3.OperationalError as _err:
        anotar_error("precios_lejos_de_mercado_libre", _err)
        return []
    salida = []
    for f in filas:
        razon = f["Tu precio"] / f["Mercado Libre"]
        if razon >= veces or razon <= 1 / veces:
            f["Diferencia"] = (f"{miles(razon, 1)} veces más caro" if razon > 1
                               else f"{miles(1 / razon, 1)} veces más barato")
            f["_orden"] = max(razon, 1 / razon)
            salida.append(f)
    salida.sort(key=lambda f: (-(f["Stock"] > 0), -f["_orden"]))
    for f in salida:
        f.pop("_orden", None)
    return salida[:limite]


def mercado_libre_automatico():
    """¿Se busca solo? Sí, si la aplicación está cargada, salvo que se apague en Administrar."""
    return (config_mercado_libre() is not None
            and obtener_config("mercado_libre_automatico", "1") == "1")


def guardar_autos_de_ficha(codigo, nombre_marca, autos, tipo_pieza=""):
    """Guarda como aplicaciones los autos que se leyeron de la ficha del portal."""
    if not autos:
        return 0
    # Solo los que dicen el modelo: «le va a un FIAT» no sirve para buscar por vehículo, y como
    # aplicación de fábrica empataría con cualquier otro repuesto de cualquier Fiat.
    filas = [{"marca_auto": marca, "modelo_auto": modelo, "motor": "", "combustible": "",
              "anio_desde": None, "anio_hasta": None, "codigo": codigo}
             for marca, modelo in autos if modelo]
    if not filas:
        return 0
    return guardar_aplicaciones(filas, nombre_marca, "ficha del portal", tipo_pieza)


def buscar_imagen_en_ficha(url_ficha, tiempo_maximo=12, sesion=None, con_direccion=False):
    """Busca la foto del producto dentro de la ficha oficial del proveedor. Es la fuente más
    confiable que hay gratis: es la foto de ESE código, puesta por el propio proveedor.
    No existe ninguna base pública y gratuita de fotos por número de parte — la del rubro
    (TecDoc) es un servicio pago con licencia.

    Con con_direccion=True devuelve ((bytes, dirección de la imagen), error): en modo liviano lo
    que se guarda es el LINK, y tiene que ser el de la imagen, no el de la ficha. Con el de la
    ficha, el buscador mostraba una foto rota cada vez que faltaba la miniatura —después de
    cada reinicio, porque la copia no lleva miniaturas— y volver a bajarla daba «no es una
    imagen»."""
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
                return ((datos, url_img) if con_direccion else datos), None
        return None, "no encontré una foto de producto en esa ficha"
    except Exception as e:
        anotar_error("buscar_imagen_en_ficha", e)
        return None, type(e).__name__


# LO QUE FALLÓ POR LA RED: UNA VEZ POR DÍA Y HASTA TRES DÍAS. Un sitio que no contesta no dice
# nada de la ficha: mañana puede andar. Pero reintentarla en cada vuelta es bajar lo mismo una y
# otra vez, y con la carga sin tope por día eso es golpear al sitio sin parar. Cada falla suma
# un intento por día como mucho; al tercer día distinto que falla se deja de intentar y se marca
# como hecha en su propia tabla, así la tarea puede terminar. «Reintentar las que fallaron»
# (reintentar_descargas_fallidas()) las vuelve a habilitar.
INTENTOS_POR_DESCARGA = 3


def _anotar_fallas(fuente, fallas):
    """Anota [(clave, error)] que fallaron por la red. Suma un intento por día como mucho.
    Devuelve las claves que llegaron a INTENTOS_POR_DESCARGA: esas ya no se reintentan."""
    if not fallas:
        return []
    hoy = datetime.now().strftime("%Y-%m-%d")
    rendidas = []
    try:
        claves = [str(k) for k, _e in fallas]
        previas = {}
        for tanda, marcadores in en_tandas(claves, tope=TOPE_VARIABLES_POR_CONSULTA - 1):
            c.execute(f"""SELECT clave, intentos, fecha FROM descargas_fallidas
                          WHERE fuente = ? AND clave IN ({marcadores})""", [fuente, *tanda])
            previas.update({r["clave"]: (r["intentos"], r["fecha"]) for r in c.fetchall()})
        filas = []
        for clave, error in fallas:
            intentos, fecha = previas.get(str(clave), (0, ""))
            if fecha != hoy:
                intentos += 1
            filas.append((fuente, str(clave), intentos, str(error or "")[:200], hoy))
            if intentos >= INTENTOS_POR_DESCARGA:
                rendidas.append(clave)
        with db_lock, transaccion():
            c.executemany("""INSERT OR REPLACE INTO descargas_fallidas
                             (fuente, clave, intentos, error, fecha) VALUES (?, ?, ?, ?, ?)""",
                          filas)
    except sqlite3.OperationalError as _err:
        anotar_error("_anotar_fallas", _err)
    return rendidas


def _no_fallo_hoy(fuente, columna="id"):
    """Condición SQL: el producto no falló hoy por la red en esa fuente. Lo que falló hoy se
    reintenta mañana, no en la vuelta siguiente: si no, la tanda lo volvería a bajar cada
    minuto mientras avanza con lo demás."""
    return (f"{columna} NOT IN (SELECT CAST(clave AS INTEGER) FROM descargas_fallidas "
            f"WHERE fuente = '{fuente}' AND fecha = date('now', 'localtime'))")


def _fallaron_hoy(fuente):
    """Las claves que fallaron hoy en esa fuente (para las que no son productos)."""
    try:
        c.execute("""SELECT clave FROM descargas_fallidas
                     WHERE fuente = ? AND fecha = date('now', 'localtime')""", (fuente,))
        return {r[0] for r in c.fetchall()}
    except sqlite3.OperationalError as _err:
        anotar_error("_fallaron_hoy", _err)
        return set()


def _quedan_para_reintentar(prefijo):
    """¿Hay algo de esa fuente que falló HOY y se va a reintentar mañana?

    Solo lo de hoy: lo que falló otro día y sigue pendiente, la tarea ya lo habría vuelto a
    elegir. Contando cualquier fila, una que quedó huérfana —el producto se borró, o le
    cargaron la foto a mano— dejaba la tarea «descansando hasta mañana» todos los días, sin
    terminar nunca."""
    try:
        c.execute("""SELECT 1 FROM descargas_fallidas
                     WHERE fuente LIKE ? AND intentos < ?
                       AND fecha = date('now', 'localtime') LIMIT 1""",
                  (prefijo + "%", INTENTOS_POR_DESCARGA))
        return c.fetchone() is not None
    except sqlite3.OperationalError as _err:
        anotar_error("_quedan_para_reintentar", _err)
        return False


def _olvidar_fallas(fuente, claves):
    """Lo que bajó bien ya no cuenta como fallado."""
    if not claves:
        return
    try:
        with db_lock, transaccion():
            c.executemany("DELETE FROM descargas_fallidas WHERE fuente = ? AND clave = ?",
                          [(fuente, str(k)) for k in claves])
    except sqlite3.OperationalError as _err:
        anotar_error("_olvidar_fallas", _err)


def contar_descargas_fallidas():
    """{fuente: cuántas se dejaron de intentar}. Nunca falla."""
    try:
        c.execute("""SELECT fuente, COUNT(*) FROM descargas_fallidas
                     WHERE intentos >= ? GROUP BY fuente""", (INTENTOS_POR_DESCARGA,))
        return {r[0]: r[1] for r in c.fetchall()}
    except sqlite3.OperationalError as _err:
        anotar_error("contar_descargas_fallidas", _err)
        return {}


def reintentar_descargas_fallidas():
    """Vuelve a habilitar todo lo que se dejó de intentar por fallas de red, y reabre las tareas.
    Lo que ya bajó bien NO se toca: eso no se vuelve a bajar nunca. Devuelve cuántas habilitó."""
    tope = INTENTOS_POR_DESCARGA
    rendidas = ("SELECT CAST(clave AS INTEGER) FROM descargas_fallidas "
                "WHERE fuente = ? AND intentos >= ?")
    try:
        with db_lock, transaccion():
            n = c.execute("SELECT COUNT(*) FROM descargas_fallidas WHERE intentos >= ?",
                          (tope,)).fetchone()[0]
            c.execute("""UPDATE productos SET foto_busqueda_estado = NULL
                         WHERE foto_busqueda_estado = 'fallo'""")
            c.execute(f"""UPDATE productos SET foto_busqueda_estado = NULL
                          WHERE foto_busqueda_estado = 'link_roto' AND id IN ({rendidas})""",
                      ("foto_link", tope))
            c.execute(f"UPDATE productos SET ficha_equiv_leida = NULL WHERE id IN ({rendidas})",
                      ("equiv_ficha", tope))
            c.execute(f"DELETE FROM mercado_libre_leidos WHERE producto_id IN ({rendidas})",
                      ("mercado_libre", tope))
            c.execute("""DELETE FROM fichas_de_catalogo_leidas
                         WHERE EXISTS (SELECT 1 FROM descargas_fallidas d
                                       WHERE d.fuente = 'catalogo:' || catalogo
                                         AND d.clave = codigo AND d.intentos >= ?)""", (tope,))
            c.execute("DELETE FROM descargas_fallidas")
    except sqlite3.OperationalError as _err:
        anotar_error("reintentar_descargas_fallidas", _err)
        return 0
    buscar_lo_nuevo()
    return n


# Las fotos como link que todavía no se bajaron. Que el link esté en la ficha no alcanza para
# saberlo: en modo liviano la foto bajada se guarda como el MISMO link (ver
# agregar_foto_producto()), así que se miraba solo eso y cada tanda volvía a bajar las mismas y
# a sumarlas repetidas. Lo que dice si ya se bajó es que tenga fotos en producto_fotos. Y un link
# que no bajó queda marcado, para no reintentarlo en cada vuelta.
_FOTO_POR_BAJAR = f"""imagen_url IS NOT NULL AND imagen_url LIKE 'http%'
                     AND COALESCE(foto_busqueda_estado, '') <> 'link_roto'
                     AND {_no_fallo_hoy("foto_link")}
                     AND NOT EXISTS (SELECT 1 FROM producto_fotos f
                                     WHERE f.producto_id = productos.id)"""


def contar_fotos_por_bajar():
    """Productos cuya foto es un link externo (cargado desde Excel) y todavía no se bajó."""
    c.execute(f"SELECT COUNT(*) FROM productos WHERE {_FOTO_POR_BAJAR}")
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
    """Baja las fotos que están como link externo y las guarda, con miniatura y firma visual.

    Cada LINK se baja una sola vez aunque lo compartan varios productos: la foto de un catálogo
    de fabricante queda propuesta para todos los productos tuyos que citan ese código, y antes
    se bajaba la misma imagen una vez por cada uno."""
    c.execute(f"""SELECT DISTINCT imagen_url FROM productos WHERE {_FOTO_POR_BAJAR}
                  LIMIT ?""", (limite,))
    links = [r[0] for r in c.fetchall()]
    if not links:
        return 0, []
    por_link = {}
    for tanda, marcadores in en_tandas(links):
        c.execute(f"""SELECT id, imagen_url FROM productos WHERE {_FOTO_POR_BAJAR}
                        AND imagen_url IN ({marcadores})""", tanda)
        for r in c.fetchall():
            por_link.setdefault(r["imagen_url"], []).append(r["id"])

    def traer(tarea):
        datos, error = descargar_imagen(tarea[0])
        # El link es una PÁGINA y no una imagen: pasa con las fotos de ficha guardadas antes de
        # que se guardara el link de la imagen, y con links de producto pegados en un Excel. Se
        # busca la foto adentro, como en la ficha del proveedor (ver buscar_imagen_en_ficha()).
        if not datos and error and "no devuelve una imagen" in error \
                and not direccion_interna(tarea[0]):
            encontrada, _err = buscar_imagen_en_ficha(tarea[0], con_direccion=True)
            if encontrada:
                return encontrada, None
        if datos:
            return (datos, tarea[0]), None
        return None, error

    resultados = _bajar_en_paralelo(
        list(por_link.items()), traer, hilos=hilos, progreso=progreso
    )

    bajadas, fallidas, por_la_red, rotas = 0, [], [], []
    for (url, pids), datos, error in resultados:
        if datos:
            datos, url_imagen = datos
            for pid in pids:
                try:
                    actualizar_imagen_producto(pid, datos, origen="link", fuente=url_imagen,
                                               liviano=liviano)
                    if url_imagen != url:
                        # Salió de adentro de una página: el link de la ficha pasa a ser el de
                        # la imagen, que es lo que el buscador sabe mostrar.
                        with db_lock:
                            c.execute("UPDATE productos SET imagen_url = ? "
                                      "WHERE id = ? AND imagen_url = ?", (url_imagen, pid, url))
                            conn.commit()
                    bajadas += 1
                except Exception as e:
                    anotar_error("bajar_fotos_pendientes", e)
                    fallidas.append((url, type(e).__name__))
                    # Bajó pero no se pudo guardar (imagen dañada): se marca, para que la
                    # tanda no la vuelva a elegir en cada vuelta.
                    rotas.append(pid)
            _olvidar_fallas("foto_link", pids)
        else:
            fallidas.extend((url, error) for _p in pids)
            # Solo lo que es una respuesta —no existe, no es una imagen— es definitivo. Un corte
            # de red se reintenta otro día, hasta tres (ver _anotar_fallas()).
            if error and ("respondió 404" in error or "respondió 410" in error
                          or "no devuelve una imagen" in error or "bloqueado" in error):
                rotas.extend(pids)
            else:
                por_la_red.extend((pid, error) for pid in pids)
    rotas.extend(_anotar_fallas("foto_link", por_la_red))
    if rotas:
        with db_lock:
            c.executemany("UPDATE productos SET foto_busqueda_estado = 'link_roto' WHERE id = ?",
                          [(pid,) for pid in rotas])
            conn.commit()
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
    la subió después o se cayó el sitio justo esa vez.

    Solo esos: antes limpiaba el estado de TODOS los productos, y con eso también los links de
    fotos rotas —que la tanda volvía a bajar, cuando ya se sabía que no andaban— y el aviso
    decía «se rehabilitaron 70.888» cuando eran unos cientos. Reabre la tanda de fotos."""
    _cond = ("imagen_url IS NULL AND foto_busqueda_estado IN ('sin_foto', 'fallo')"
             + (" AND marca_id = ?" if marca_id else ""))
    with db_lock, transaccion():
        c.execute(f"UPDATE productos SET foto_busqueda_estado = NULL WHERE {_cond}",
                  (marca_id,) if marca_id else ())
        cambiados = c.rowcount
        c.execute("DELETE FROM descargas_fallidas WHERE fuente = 'foto_ficha'")
    if cambiados:
        guardar_config("terminado_fotos", "")
        guardar_config("descanso_fotos", "")
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
                    AND {_no_fallo_hoy("foto_ficha")}
                    {_condicion_filtro_fotos(filtro)}
                  ORDER BY (stock > 0) DESC, id
                  LIMIT ?""", (marca_id, limite))
    pendientes = [(r["id"], r["codigo_raw"]) for r in c.fetchall()]
    if not pendientes:
        return 0, [], 0

    def traer(tarea):
        _, codigo = tarea
        url_ficha = url_de_la_ficha(plantilla, codigo)
        if not url_ficha:
            return None, "ese código no se puede usar en una dirección"
        return buscar_imagen_en_ficha(url_ficha, sesion=sesion, con_direccion=True)

    resultados = _bajar_en_paralelo(pendientes, traer, hilos=hilos, progreso=progreso,
                                    cancelado=cancelado)

    bajadas, fallidas, sin_foto, por_la_red, bien = 0, [], 0, [], []
    for (pid, codigo), datos, error in resultados:
        url_ficha = url_de_la_ficha(plantilla, codigo)
        if datos:
            datos, url_imagen = datos
            try:
                actualizar_imagen_producto(pid, datos, origen="ficha", fuente=url_imagen,
                                            liviano=liviano)
                bajadas += 1
                bien.append(pid)
                continue
            except Exception as e:
                anotar_error("bajar_fotos_desde_catalogo", e)
                error = type(e).__name__
        fallidas.append((codigo, error))
        # «no encontré una foto» o «no hay ficha» son definitivos para ese código; un error de
        # red no lo es: se reintenta otro día, hasta tres (ver _anotar_fallas()).
        definitivo = not _falla_de_la_red(error)
        if not definitivo:
            por_la_red.append((pid, error))
        with db_lock:
            c.execute("UPDATE productos SET foto_busqueda_estado = ? WHERE id = ?",
                      ("sin_foto" if definitivo else "error", pid))
            conn.commit()
        if definitivo:
            sin_foto += 1
    rendidas = _anotar_fallas("foto_ficha", por_la_red)
    if rendidas:
        with db_lock:
            c.executemany("UPDATE productos SET foto_busqueda_estado = 'fallo' WHERE id = ?",
                          [(pid,) for pid in rendidas])
            conn.commit()
    _olvidar_fallas("foto_ficha", bien)
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
    guardada = _pagina_guardada(url) if not extra else None
    if guardada is not None:
        return guardada
    pedir = (sesion or requests).get
    cabeceras = {"User-Agent": "Mozilla/5.0 (compatible; EquivalenciasElChavo/1.0)"}
    respuesta = pedir(url, timeout=tiempo_maximo, headers=cabeceras, **extra)
    if not extra:
        _guardar_pagina(url, respuesta)
    return respuesta


# LA MISMA FICHA NO SE BAJA DOS VECES. Las fotos y las equivalencias leen la MISMA página del
# proveedor —la ficha de cada código—, y con las dos tareas prendidas cada ficha se pedía dos
# veces. Se guardan en memoria las últimas fichas leídas (sin scripts ni estilos, que es lo que
# más pesa y ninguna de las dos usa), un rato y con tope de tamaño: alcanza para que la segunda
# tarea encuentre la ficha que acaba de leer la primera (ver _trabajo_de_fondo(), que las hace
# ir por la misma marca).
PAGINAS_EN_MEMORIA = 400
MINUTOS_DE_PAGINA_EN_MEMORIA = 180
# Y un tope de TAMAÑO, no solo de cantidad: 400 páginas de hasta 1,5 MB podían ser 600 MB, y
# Streamlit Cloud tiene 1 GB para todo el proceso (lo señaló la revisión con Gemini). Con 40 MB
# entran de sobra las fichas de una tanda, que son las que se vuelven a pedir.
MB_DE_PAGINAS_EN_MEMORIA = 40
_PAGINAS_RECIENTES = del_proceso("paginas_recientes", dict)
_CANDADO_PAGINAS = del_proceso("candado_de_paginas_recientes", threading.Lock)


class _PaginaGuardada:
    """Lo que usan de la respuesta quienes leen fichas: el código y el texto."""
    def __init__(self, status_code, text, headers):
        self.status_code, self.text, self.headers = status_code, text, headers
        self.content = text.encode("utf-8", "ignore")


def _pagina_guardada(url):
    with _CANDADO_PAGINAS:
        guardada = _PAGINAS_RECIENTES.get(url)
    if guardada and time.time() - guardada[0] < MINUTOS_DE_PAGINA_EN_MEMORIA * 60:
        return guardada[1]
    return None


def _guardar_pagina(url, respuesta):
    try:
        tipo = (respuesta.headers.get("Content-Type") or "").lower()
        if respuesta.status_code not in (200, 404) or "html" not in tipo:
            return      # solo respuestas que dicen algo de la ficha; un 500 se reintenta
        texto = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", respuesta.text or "")
        if len(texto) > 1_500_000:
            return
        with _CANDADO_PAGINAS:
            _PAGINAS_RECIENTES[url] = (time.time(), _PaginaGuardada(
                respuesta.status_code, texto, {"Content-Type": tipo}))
            # Se sacan las más viejas (el dict guarda el orden de entrada) hasta volver a
            # entrar en los dos topes.
            _total = sum(len(p.text) for _t, p in _PAGINAS_RECIENTES.values())
            while _PAGINAS_RECIENTES and (
                    len(_PAGINAS_RECIENTES) > PAGINAS_EN_MEMORIA
                    or _total > MB_DE_PAGINAS_EN_MEMORIA * 1024 * 1024):
                _t, _vieja = _PAGINAS_RECIENTES.pop(next(iter(_PAGINAS_RECIENTES)))
                _total -= len(_vieja.text)
    except Exception as _err:
        anotar_error("_guardar_pagina", _err)


# ¿La plantilla del catálogo es la de un BUSCADOR y no la de una ficha? Ver _link_a_la_ficha().
_RE_PLANTILLA_DE_BUSQUEDA = re.compile(
    r"busc|search|query|consulta|filtro|[?&](?:q|s|k|term|texto|codigo)=\{", re.IGNORECASE)


def es_plantilla_de_busqueda(plantilla):
    return bool(_RE_PLANTILLA_DE_BUSQUEDA.search(str(plantilla or "")))


def _link_a_la_ficha(html_pagina, url_pagina, codigo_propio):
    """En una página de RESULTADOS, el link a la ficha de ese código, o None.

    Hace falta para los catálogos que no tienen una dirección por código sino un buscador
    (TARANTO, CRI-FA): la lista de resultados no trae los números originales, la ficha sí. Se
    toma el primer link cuyo texto o dirección tenga el código ENTERO —«2503» no es «250321»— y
    que se quede en el mismo sitio: un resultado no puede mandar a la app a otra parte."""
    from urllib.parse import urljoin, urlparse
    propio = sanitizar(codigo_propio)
    if not propio:
        return None
    sitio = urlparse(url_pagina).netloc
    for href, texto in re.findall(r'(?is)<a\s[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                                  html_pagina or ""):
        destino = urljoin(url_pagina, html.unescape(href)).split("#")[0]
        partes = urlparse(destino)
        if partes.scheme not in ("http", "https") or partes.netloc != sitio:
            continue
        if destino.rstrip("/") == url_pagina.split("#")[0].rstrip("/"):
            continue
        palabras = (re.split(r"[\s|,;:()\[\]]+", re.sub(r"<[^>]+>", " ", html.unescape(texto)))
                    + re.split(r"[/?&=]+", partes.path + "?" + partes.query))
        if any(sanitizar(p) == propio for p in palabras if p):
            return destino
    return None


def codigos_en_una_ficha(url_ficha, codigo_propio, tiempo_maximo=12, sesion=None,
                         seguir_resultado=False):
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
        # Con un buscador, la página es la lista de resultados: se sigue el link a la ficha.
        if seguir_resultado:
            ficha = _link_a_la_ficha(respuesta.text, url_ficha, codigo_propio)
            if not ficha:
                return [], "la búsqueda no encontró la ficha de ese código"
            _motivo_interno = direccion_interna(ficha)
            if _motivo_interno:
                return [], f"el resultado apunta a una dirección no permitida ({_motivo_interno})"
            respuesta = _traer_pagina(ficha, tiempo_maximo=tiempo_maximo, sesion=sesion)
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
    _filtro = (f" AND ficha_equiv_leida IS NULL AND {_no_fallo_hoy('equiv_ficha')}"
               if solo_no_leidos else "")
    c.execute(f"""SELECT id, codigo_raw, codigo_clean FROM productos
                  WHERE marca_id = ?{_filtro}
                  ORDER BY (COALESCE(stock, 0) > 0) DESC, id LIMIT ?""",
              (marca_id, limite))
    pendientes = [(r["id"], r["codigo_raw"], r["codigo_clean"]) for r in c.fetchall()]
    if not pendientes:
        return [], [], 0

    def traer(tarea):
        _pid, codigo, _limpio = tarea
        # url_de_la_ficha() limpia el código antes de meterlo en la dirección: sin eso un
        # código con «?» o «..» convertiría una consulta en otra cosa.
        url_ficha = url_de_la_ficha(plantilla, codigo)
        if not url_ficha:
            return None, "ese código no se puede usar en una dirección"
        return codigos_en_una_ficha(url_ficha, codigo, sesion=sesion,
                                    seguir_resultado=_de_busqueda)

    # Si la plantilla es un buscador, se entra al resultado: ver _link_a_la_ficha().
    _de_busqueda = es_plantilla_de_busqueda(plantilla)
    resultados = _bajar_en_paralelo(pendientes, traer, hilos=hilos, progreso=progreso,
                                    cancelado=cancelado)

    propuestas, fallidas = [], []
    for (pid, codigo, limpio), codigos, error in resultados:
        if error or not codigos:
            fallidas.append((codigo, error or "sin códigos"))
            continue
        for otro in codigos:
            otro_limpio = sanitizar(otro)
            # De OTRA marca: la ficha —y más la lista de resultados de un buscador— nombra los
            # otros productos de la misma marca (el juego que la trae, la versión nueva), y eso
            # no es una equivalencia.
            c.execute("""SELECT p.id, p.codigo_raw, m.nombre AS marca FROM productos p
                         JOIN marcas m ON m.id = p.marca_id
                         WHERE p.codigo_clean = ? AND p.id <> ? AND p.marca_id <> ?
                         LIMIT 1""", (otro_limpio, pid, marca_id))
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
    # La excepción es la falla de red: esa no dice nada de la ficha, así que queda sin leer y se
    # reintenta otro día, hasta tres (ver _anotar_fallas()).
    try:
        _ahora_txt = datetime.now().strftime("%Y-%m-%d")
        _red = [(pid, _e) for (pid, _c, _l), _x, _e in resultados if _falla_de_la_red(_e)]
        _rendidas = set(_anotar_fallas("equiv_ficha", _red))
        _sin_leer = {pid for pid, _e in _red} - _rendidas
        with db_lock:
            c.executemany("UPDATE productos SET ficha_equiv_leida = ? WHERE id = ?",
                          [(_ahora_txt, pid) for (pid, _c, _l), _x, _e in resultados
                           if pid not in _sin_leer])
            conn.commit()
        _olvidar_fallas("equiv_ficha", [pid for (pid, _c, _l), _x, _e in resultados
                                        if not _falla_de_la_red(_e)])
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
# grande como se quiera, y no tiene tope por día: corre hasta que no queda nada pendiente.
#
# Tres cosas la hacen segura:
#   · UNA sola a la vez en todo el proceso (_CANDADO_FONDO). Sin eso, cinco pestañas abiertas
#     son cinco tandas pidiéndole lo mismo al proveedor al mismo tiempo.
#   · Va de a subtandas chicas que van guardando. Si Streamlit Cloud apaga el servidor por
#     inactividad —pasa seguido— se pierde la subtanda en curso y nada más.
#   · Nunca toca `st`. Un hilo de fondo no tiene pantalla donde dibujar; llamar a st.* desde
#     ahí no muestra nada y ensucia el registro. Todo lo que tiene para contar lo deja anotado
#     en la configuración, y la pantalla lo lee de ahí.
PRODUCTOS_POR_SUBTANDA = 50

# SIN CUPO POR DÍA. Antes cada tarea tenía un tope diario (500 fotos, 150 fichas de catálogo,
# 200 búsquedas de Mercado Libre) y la tanda cortaba a los 10 minutos: con 70.888 productos eso
# eran meses. Ahora corre hasta terminar. Lo único que la frena es un descanso:
#   · MINUTOS_DE_DESCANSO si la tarea no encontró nada que hacer (para no volver a mirar la
#     base en cada toque de pantalla),
#   · MINUTOS_DE_DESCANSO_SI_FALLA si el sitio falló o rechazó (para no insistirle a un sitio
#     caído, que es la forma más rápida de que te bloquee).
MINUTOS_DE_DESCANSO = 30
MINUTOS_DE_DESCANSO_SI_FALLA = 60

# Si llega trabajo de estos mientras la tanda baja fotos, se corta y se vuelve a empezar: una
# lista recién importada no tiene que esperar a que terminen 70.000 fotos.
_TAREAS_QUE_VAN_PRIMERO = ("separacion_pendiente", "medidas_pendientes",
                           "marcas_repuesto_pendientes", "aplicaciones_pendientes",
                           "confianza_pendiente", "descubrimiento_pendiente")

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
        guardar_config("tanda_fondo_catalogos", "0")
        guardar_config("tanda_fondo_mercado_libre", "0")
    try:
        return max(objetivo - int(obtener_config(clave, "0") or 0), 0)
    except ValueError:
        return objetivo


def _sumar_al_cupo(clave, cuantos):
    try:
        guardar_config(clave, str(int(obtener_config(clave, "0") or 0) + cuantos))
    except ValueError:
        guardar_config(clave, str(cuantos))


def _falla_de_la_red(error):
    """¿El error es del sitio o de la red, y no una respuesta («no hay ficha», «sin códigos»)?"""
    error = str(error or "")
    return bool(error) and not any(x in error for x in ("sin códigos", "404", "no encontré",
                                                        "no se puede usar en una dirección",
                                                        "bloqueado"))


def _descansando(que):
    """¿Esa tarea está en su descanso (ver MINUTOS_DE_DESCANSO)?"""
    hasta = obtener_config(f"descanso_{que}", "")
    return bool(hasta) and hasta > datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _descansar(que, minutos=MINUTOS_DE_DESCANSO):
    guardar_config(f"descanso_{que}",
                   (datetime.now() + timedelta(minutes=minutos)).strftime("%Y-%m-%d %H:%M:%S"))


# UNA VEZ QUE TERMINA, NO SE REPITE. Cuando una tarea no encuentra nada pendiente queda
# «terminada» y la tanda de fondo ya no la vuelve a mirar: ni cada media hora, ni al importar una
# lista, ni al reiniciar el servidor. Se reabre solo cuando lo pedís (buscar_lo_nuevo(), el botón
# «🔄 Buscar lo nuevo»), o al prenderla, o —si lo elegiste— al importar una lista. Y al reabrirla
# no vuelve a bajar nada de lo que ya bajó: cada fuente anota lo hecho en su tabla (la foto en el
# producto, ficha_equiv_leida, fichas_de_catalogo_leidas, mercado_libre_leidos) y solo busca lo
# que falta.
# Cada tarea, con la fuente con que anota sus fallas de red (ver _anotar_fallas()).
TAREAS_DE_FONDO = {
    "fotos": ("📷 Fotos de las fichas del proveedor", "foto_ficha"),
    "equiv": ("🌐 Equivalencias de las fichas del proveedor", "equiv_ficha"),
    "catalogos": ("🏭 Catálogos de fabricantes", "catalogo:"),
    "mercado_libre": ("🛒 Mercado Libre", "mercado_libre"),
    "fotos_de_internet": ("🖼️ Fotos que dejaron esos sitios", "foto_link"),
    "firmas": ("🔍 Firmas visuales para la cámara", None),
}


def _terminada(que):
    return bool(obtener_config(f"terminado_{que}", ""))


def _dar_por_terminada(que):
    """No queda nada pendiente. Si hay algo que falló hoy por la red y se reintenta mañana,
    descansa hasta mañana en vez de terminar: si no, eso quedaría sin bajar para siempre."""
    fuente = TAREAS_DE_FONDO.get(que, ("", None))[1]
    if fuente and _quedan_para_reintentar(fuente):
        manana = (datetime.now() + timedelta(days=1)).replace(hour=0, minute=5, second=0)
        _descansar(que, int((manana - datetime.now()).total_seconds() // 60) + 1)
    else:
        guardar_config(f"terminado_{que}", datetime.now().strftime("%Y-%m-%d %H:%M"))


def buscar_lo_nuevo(tareas=None):
    """Reabre las tareas terminadas (todas, o las pedidas) y larga la tanda. Solo va a buscar lo
    que falta: lo ya bajado está anotado y no se vuelve a pedir."""
    for que in (tareas or TAREAS_DE_FONDO):
        guardar_config(f"terminado_{que}", "")
        guardar_config(f"descanso_{que}", "")
        if que == "fotos_de_internet":
            guardar_config("fotos_de_internet_pendientes", "1")
    return arrancar_tanda_de_fondo()


def prender_tarea_de_fondo(que, clave_config, prendida):
    """Para los interruptores: prenderla es pedirla, así que también la reabre."""
    guardar_config(clave_config, "1" if prendida else "0")
    if prendida:
        buscar_lo_nuevo([que])


def lo_nuevo_al_importar():
    """Después de importar una lista, ¿se buscan solas las fotos y fichas de lo nuevo? Apagado
    de fábrica: lo que ya terminó no arranca hasta que lo pidas."""
    if obtener_config("buscar_lo_nuevo_al_importar", "0") == "1":
        buscar_lo_nuevo()


def _tarea_prendida(que):
    """La tarea está prendida por el usuario, no terminó y no está descansando."""
    if que == "fotos":
        prendida = obtener_config("fotos_automaticas", "0") == "1"
    elif que == "equiv":
        prendida = obtener_config("equiv_ficha_automaticas", "0") == "1"
    elif que == "catalogos":
        prendida = catalogos_de_fabricante_automaticos()
    elif que == "mercado_libre":
        prendida = mercado_libre_automatico()
    else:
        prendida = True
    return prendida and not _terminada(que) and not _descansando(que)


def _le_faltan_equivalencias(marca_id):
    try:
        c.execute(f"""SELECT 1 FROM productos WHERE marca_id = ? AND ficha_equiv_leida IS NULL
                        AND {_no_fallo_hoy('equiv_ficha')} LIMIT 1""", (marca_id,))
        return c.fetchone() is not None
    except sqlite3.OperationalError as _err:
        anotar_error("_le_faltan_equivalencias", _err)
        return False


def _marca_con_mas_fichas_pendientes(que):
    """La marca a la que le falta más trabajo del tipo pedido, o None.

    Se elige la de más pendientes y no la primera: así el catálogo más grande —que es el que
    tarda años— avanza primero, en vez de repartir el esfuerzo entre listas chicas."""
    condicion = ("p.imagen_url IS NULL "
                 "AND (p.foto_busqueda_estado IS NULL OR p.foto_busqueda_estado = 'error') "
                 f"AND {_no_fallo_hoy('foto_ficha', 'p.id')}"
                 if que == "fotos" else
                 f"p.ficha_equiv_leida IS NULL AND {_no_fallo_hoy('equiv_ficha', 'p.id')}")
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


# Tope del cruce por auto cuando corre solo en la tanda de fondo: ver
# derivar_equivalencias_de_aplicaciones(). Hoy tarda menos de un minuto entero.
SEGUNDOS_DEL_CRUCE_POR_AUTO = 300


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
    """El cuerpo del hilo. Va alternando fotos, equivalencias, catálogos y Mercado Libre hasta
    que no queda nada pendiente. Devuelve True si cortó porque llegó trabajo de los que van
    primero (ver _TAREAS_QUE_VAN_PRIMERO), para que correr() la vuelva a largar.

    Alterna en vez de terminar una y después la otra para que prender las dos no signifique que
    la segunda no arranca hasta dentro de un mes."""
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
            # De punta a punta una vez, siguiendo cada tanda donde terminó la anterior (ver
            # medidas_deducibles_desde()). Al terminar queda todo mirado. Cada vuelta avanza
            # sí o sí, así que no puede girar sobre las mismas filas; el tope de vueltas y el
            # corte si no se guarda nada quedan igual, por las dudas: esto corre en un hilo de
            # fondo y si se trabara no lo vería nadie.
            _desde = 0
            for _ in range(100000):
                _tanda_med, _hasta = medidas_deducibles_desde(_desde, limite=2000)
                _aplicadas = aplicar_medidas_deducidas(_tanda_med) if _tanda_med else 0
                _n_med += _aplicadas
                if len(_tanda_med) < 2000 or _hasta <= _desde:
                    guardar_config("medidas_revisadas_hasta", str(_hasta))
                    break
                _desde = _hasta
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
            _hasta_apl = c.execute("SELECT COALESCE(MAX(id), 0) FROM productos").fetchone()[0]
            _apl_ded = aplicaciones_desde_descripciones()
            _n_apl = aplicar_aplicaciones_deducidas(_apl_ded) if _apl_ded else 0
            # Leídas todas: la próxima importación sigue desde acá (ver
            # descubrimiento_post_importacion()).
            guardar_config("aplicaciones_leidas_hasta", str(_hasta_apl))
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
                    _por_auto = derivar_equivalencias_de_aplicaciones(
                        solo_lo_nuevo=True, tope_segundos=SEGUNDOS_DEL_CRUCE_POR_AUTO)
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

    # Una lista enorme recién importada: su análisis va ANTES del descubrimiento (que puede
    # tardar dos minutos), porque quien la importó es probable que vaya derecho a revisarla.
    if obtener_config("lote_a_analizar", ""):
        try:
            ceder_al_mostrador()
            preparar_el_analisis_del_primer_lote()
        except Exception as _err:
            anotar_error("_trabajo_de_fondo/analisis_del_lote", _err)

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

    # El análisis de la lista que «Equivalencias sugeridas» muestra primero, para que al abrirla
    # ya esté hecho (ver preparar_el_analisis_del_primer_lote()). Va después del descubrimiento
    # porque ese agrega pares, y antes de las descargas porque es lo que alguien va a mirar.
    try:
        ceder_al_mostrador()
        preparar_el_analisis_del_primer_lote()
    except Exception as _err:
        anotar_error("_trabajo_de_fondo/analisis_del_lote", _err)

    # El dólar y la inflación oficiales (ver contexto_de_precios()): acá, por atrás, para que
    # los avisos y la importación los tengan sin salir a internet desde una pantalla. Si ya
    # están frescos no sale a ningún lado.
    try:
        contexto_de_precios()
    except Exception as _err:
        anotar_error("_trabajo_de_fondo/contexto_de_precios", _err)
    # El IPC de transporte: una vez por semana (ver actualizar_ipc_de_transporte()).
    try:
        actualizar_ipc_de_transporte()
    except Exception as _err:
        anotar_error("_trabajo_de_fondo/ipc_de_transporte", _err)
    # El parque automotor y los 0 km del DNRPA: una vez por mes (ver
    # actualizar_parque_automotor()).
    try:
        ceder_al_mostrador()
        actualizar_parque_automotor()
    except Exception as _err:
        anotar_error("_trabajo_de_fondo/parque_automotor", _err)

    # Lo ya aprobado, con las reglas de hoy: si la app cambió o cambiaron los vínculos. La
    # pantalla de sugeridas avisa lo que encuentre (ver revisar_lo_aprobado_por_atras()).
    try:
        revisar_lo_aprobado_por_atras()
    except Exception as _err:
        anotar_error("_trabajo_de_fondo/lo_aprobado", _err)

    # SIN CUPO POR DÍA NI TOPE DE TIEMPO: sigue mientras haya algo que hacer. Lo único que la
    # frena es que un sitio falle cinco veces seguidas (ver _descansar()).
    while True:
        hizo_algo = False
        # Si mientras tanto llegó trabajo de los de arriba —una lista importada, puntajes por
        # rehacer—, se vuelve a empezar para no hacerlo esperar a que termine esto. Ver correr()
        # en arrancar_tanda_de_fondo().
        if any(obtener_config(k, "") == "1" for k in _TAREAS_QUE_VAN_PRIMERO):
            guardar_config("tanda_fondo_ultima", datetime.now().strftime("%Y-%m-%d %H:%M"))
            return True

        _marca_de_las_fotos = None
        if _tarea_prendida("fotos"):
            marca = _marca_de_las_fotos = _marca_con_mas_fichas_pendientes("fotos")
            if not marca:
                _dar_por_terminada("fotos")
            else:
                try:
                    traidas, _fall, _sin = bajar_fotos_desde_catalogo(
                        marca["mid"], limite=PRODUCTOS_POR_SUBTANDA)
                    # Del cupo se descuenta lo que se CONSULTÓ de verdad, no lo que se pidió.
                    # No es lo mismo: si quedaban tres fichas y la subtanda es de cincuenta,
                    # cobrarle cincuenta al cupo del día tira a la basura cuarenta y siete
                    # consultas que nunca se hicieron. Una ficha sin foto sí cuenta —se le
                    # pidió igual al servidor del proveedor—, por eso van las fallidas adentro.
                    consultadas = traidas + len(_fall)
                    _sumar_al_cupo("tanda_fondo_fotos", consultadas)
                    if traidas:
                        _sumar_al_cupo("tanda_fondo_fotos_ok", traidas)
                    # Las que fallaron por la red quedan en 'error' y se vuelven a elegir: sin
                    # tope por día, si el sitio anda mal la tanda giraría sobre las mismas
                    # cincuenta. Si falla más de la mitad, descansa una hora.
                    if (len(_fall) - _sin) * 2 > consultadas:
                        _descansar("fotos", MINUTOS_DE_DESCANSO_SI_FALLA)
                    # Y el bucle sigue solo si esto AVANZÓ. Darlo por hecho porque había una
                    # marca pendiente deja girar el bucle diez minutos contra la base cuando la
                    # consulta que elige la marca y la que trae las fichas no miran exactamente
                    # lo mismo — hoy miran igual, pero con dos consultas separadas eso se
                    # desincroniza el día que alguien toque una sola de las dos.
                    hizo_algo = hizo_algo or traidas + _sin > 0
                    if not consultadas:
                        _descansar("fotos")
                except Exception as _err:
                    _descansar("fotos", MINUTOS_DE_DESCANSO_SI_FALLA)
                    anotar_error("_trabajo_de_fondo/fotos", _err)

        if _tarea_prendida("equiv"):
            # Si las fotos acaban de leer fichas de una marca y a esa le faltan equivalencias,
            # va por la misma: las fichas están en memoria y no se vuelven a pedir.
            marca = (_marca_de_las_fotos if _marca_de_las_fotos
                     and _le_faltan_equivalencias(_marca_de_las_fotos["mid"])
                     else _marca_con_mas_fichas_pendientes("equiv"))
            if not marca:
                _dar_por_terminada("equiv")
            else:
                try:
                    props, _fall, consultados = equivalencias_desde_catalogo(
                        marca["mid"], limite=PRODUCTOS_POR_SUBTANDA, solo_no_leidos=True)
                    _sumar_al_cupo("tanda_fondo_equiv", consultados)
                    if props:
                        guardadas = guardar_equivalencias_de_catalogo(props, marca["nombre"])
                        if guardadas:
                            _sumar_al_cupo("tanda_fondo_equiv_ok", guardadas)
                    hizo_algo = hizo_algo or consultados > 0
                    if not consultados:
                        _descansar("equiv")
                    elif sum(1 for _c, _e in _fall if _falla_de_la_red(_e)) * 2 > consultados:
                        # La ficha se anota como leída igual: con el sitio caído, sin este freno
                        # la tanda recorrería todo el catálogo marcándolo leído sin leer nada.
                        _descansar("equiv", MINUTOS_DE_DESCANSO_SI_FALLA)
                except Exception as _err:
                    _descansar("equiv", MINUTOS_DE_DESCANSO_SI_FALLA)
                    anotar_error("_trabajo_de_fondo/equiv", _err)

        # Los catálogos de fabricante (SKF, NGK, MANN-FILTER): ver
        # tanda_de_catalogos_de_fabricante(). Si no queda nada por leer —o están todos
        # pausados—, descansa: si no, la tarea se volvería a largar en cada toque de pantalla
        # para no hacer nada.
        if _tarea_prendida("catalogos"):
            try:
                consultadas = tanda_de_catalogos_de_fabricante(
                    PRODUCTOS_POR_SUBTANDA * len(CATALOGOS_DE_FABRICANTE))
                _sumar_al_cupo("tanda_fondo_catalogos", consultadas)
                hizo_algo = hizo_algo or consultadas > 0
                if not consultadas:
                    # Nada resuelto: si algún sitio quedó pausado es que falla, y se reintenta
                    # en una hora. Si no, no queda nada por leer.
                    if any(_catalogo_de_fabricante_pausado(n) for n in CATALOGOS_DE_FABRICANTE):
                        _descansar("catalogos", MINUTOS_DE_DESCANSO_SI_FALLA)
                    else:
                        _dar_por_terminada("catalogos")
            except Exception as _err:
                _descansar("catalogos", MINUTOS_DE_DESCANSO_SI_FALLA)
                anotar_error("_trabajo_de_fondo/catalogos", _err)

        # Las fotos que dejaron los catálogos de fabricante y Mercado Libre (ver proponer_foto()):
        # se bajan y se les calcula la firma visual, que es lo que usa la búsqueda por cámara.
        # En modo liviano: en la base queda el link y la miniatura, no la foto entera.
        if (obtener_config("fotos_de_internet_pendientes", "") == "1"
                and not _descansando("fotos_de_internet")):
            try:
                ceder_al_mostrador()
                _bajadas, _fallidas = bajar_fotos_pendientes(limite=PRODUCTOS_POR_SUBTANDA,
                                                             hilos=6)
                # Sin ninguna bajada —no quedaba nada, o todo lo que quedaba falló— se deja de
                # intentar: vuelve a prenderse cuando llegue una foto nueva.
                # Se apaga solo cuando no quedó NADA que intentar. Antes bastaba una tanda de 50
                # links que no bajara ninguno —todos vencidos del mismo proveedor, por ejemplo—
                # para apagarla con miles pendientes. Cada link que falla queda marcado (roto o
                # fallado hoy), así que seguir no gira sobre los mismos.
                if not _bajadas and not _fallidas:
                    guardar_config("fotos_de_internet_pendientes", "0")
                    if _quedan_para_reintentar("foto_link"):
                        guardar_config("fotos_de_internet_pendientes", "1")
                        _dar_por_terminada("fotos_de_internet")     # descansa hasta mañana
                hizo_algo = hizo_algo or _bajadas > 0 or bool(_fallidas)
            except Exception as _err:
                guardar_config("fotos_de_internet_pendientes", "0")
                anotar_error("_trabajo_de_fondo/fotos_de_internet", _err)

        # Mercado Libre, si la aplicación está cargada: ver leer_mercado_libre(). Si no avanzó
        # —nada pendiente— descansa; si Mercado Libre no responde o rechaza, descansa una hora.
        if _tarea_prendida("mercado_libre"):
            try:
                ceder_al_mostrador()
                _res_ml = leer_mercado_libre(cuantos=PRODUCTOS_POR_SUBTANDA)
                _sumar_al_cupo("tanda_fondo_mercado_libre", _res_ml["buscados"])
                hizo_algo = hizo_algo or _res_ml["buscados"] > 0
                if _res_ml["error"]:
                    _descansar("mercado_libre", MINUTOS_DE_DESCANSO_SI_FALLA)
                elif not _res_ml["buscados"]:
                    _dar_por_terminada("mercado_libre")
            except Exception as _err:
                _descansar("mercado_libre", MINUTOS_DE_DESCANSO_SI_FALLA)
                anotar_error("_trabajo_de_fondo/mercado_libre", _err)

        # Las fotos viejas sin firma visual (la que usa la cámara): antes se procesaban de a 20
        # por día, en las tareas del día. Solo cuenta como avance lo que quedó resuelto: las que
        # dan error se vuelven a elegir en la próxima vuelta, y contarlas dejaría girando el
        # bucle para siempre sobre las mismas 50 fotos rotas.
        if not _descansando("firmas") and not _terminada("firmas"):
            try:
                ceder_al_mostrador()
                _r_fir = migrar_imagenes_pendientes(limite=PRODUCTOS_POR_SUBTANDA)
                _hechas = sum(_r_fir.get(k, 0) for k in ("listas", "sin_detalle"))
                hizo_algo = hizo_algo or _hechas > 0
                if not _hechas:
                    _dar_por_terminada("firmas")
            except Exception as _err:
                _descansar("firmas", MINUTOS_DE_DESCANSO_SI_FALLA)
                anotar_error("_trabajo_de_fondo/firmas", _err)

        if not hizo_algo:
            break       # no queda nada pendiente: no tiene sentido girar
    guardar_config("tanda_fondo_ultima", datetime.now().strftime("%Y-%m-%d %H:%M"))
    return False


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
                                  "🗂️ Administrar → 🧹 Mantenimiento"))
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
    si está todo apagado o descansando, vuelve enseguida."""
    _cupo_de_hoy("tanda_fondo_fotos", 0)     # reinicia los contadores de «hoy van» con el día
    if (not _tarea_prendida("fotos")
            and not _tarea_prendida("equiv")
            and obtener_config("descubrimiento_pendiente", "") != "1"
            # El repuntaje pendiente también la larga, aunque esté todo lo demás apagado: si no,
            # después de cambiar las reglas de confianza el puntaje viejo se quedaría para
            # siempre en la base de quien no tiene prendida ninguna tanda automática — que es
            # justo el caso normal. Ver VERSION_CONFIANZA.
            and obtener_config("confianza_pendiente", "") != "1"
            and obtener_config("medidas_pendientes", "") != "1"
            and obtener_config("aplicaciones_pendientes", "") != "1"
            and obtener_config("marcas_repuesto_pendientes", "") != "1"
            and obtener_config("separacion_pendiente", "") != "1"
            and not _tarea_prendida("catalogos")
            and not _tarea_prendida("mercado_libre")
            and (obtener_config("fotos_de_internet_pendientes", "") != "1"
                 or _descansando("fotos_de_internet"))
            and (_descansando("firmas") or _terminada("firmas"))
            and not falta_preparar_el_analisis()):
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
            # Vuelve a arrancar mientras _trabajo_de_fondo() corte porque llegó trabajo nuevo
            # de los que van primero. Con tope, por si alguna bandera quedara prendida siempre.
            for _ in range(20):
                if not _trabajo_de_fondo():
                    break
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
    """Para la pantalla: cuánto falta de cada cosa y cuánto va hoy. Nunca falla."""
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
        except ValueError:
            resumen[f"hoy_{clave}"] = 0
        resumen[f"descanso_{clave}"] = (obtener_config(f"descanso_{clave}", "")
                                        if _descansando(clave) else "")
        resumen[f"terminado_{clave}"] = obtener_config(f"terminado_{clave}", "")
    return resumen


def mostrar_avance_de_tanda(que, unidad):
    """En qué anda una de las dos tandas de fondo (fotos o equivalencias de las fichas).

    Ya no hay selector de «cuántas por día»: corre sin tope hasta terminar. Lo que se muestra
    es cuánto falta, cuánto va hoy y, si está descansando, hasta cuándo — con un botón para que
    retome ya."""
    resumen = como_va_la_tanda_de_fondo()
    faltan = resumen.get(f"faltan_{que}", 0)
    hoy = resumen.get(f"hoy_{que}", 0)
    terminado = resumen.get(f"terminado_{que}", "")
    if terminado or not faltan:
        st.caption(f"✅ Terminado{' el ' + _fecha_corta(terminado) if terminado else ''}: no "
                   "se vuelve a correr hasta que lo pidas, y al pedirlo busca solo lo que falta"
                   + (f" ({miles(faltan)} ahora)." if faltan else "."))
        if terminado and st.button("🔄 Buscar lo nuevo", key=f"lo_nuevo_tanda_{que}"):
            buscar_lo_nuevo([que])
            st.rerun()
        return
    descanso = resumen.get(f"descanso_{que}", "")
    st.caption(
        f"Faltan **{miles(faltan)}** {unidad} · hoy van {miles(hoy)} · ⚡ sin tope por día"
        + (" · 🟢 corriendo ahora" if resumen.get("corriendo") else "")
        + (f" · 😴 retoma {_fecha_corta(descanso)}" if descanso else "")
        + (f" · última vez: {resumen['ultima']}" if resumen.get("ultima") else "")
    )
    if descanso and st.button("▶️ Retomar ahora", key=f"retomar_tanda_{que}"):
        guardar_config(f"descanso_{que}", "")
        arrancar_tanda_de_fondo()
        st.rerun()


def _fecha_corta(fecha):
    """«2026-09-28 14:30…» → «hoy 14:30», «mañana 00:05» o «28/09 14:30»."""
    fecha = str(fecha or "")
    if len(fecha) < 16:
        return fecha
    hoy = datetime.now()
    if fecha[:10] == hoy.strftime("%Y-%m-%d"):
        return f"hoy {fecha[11:16]}"
    if fecha[:10] == (hoy + timedelta(days=1)).strftime("%Y-%m-%d"):
        return f"mañana {fecha[11:16]}"
    return f"{fecha[8:10]}/{fecha[5:7]} {fecha[11:16]}"


def estado_de_las_tareas_de_fondo():
    """Para la pantalla: cada tarea automática, si está prendida, terminada o descansando, y
    cuántas cosas se dejaron de intentar porque fallaron tres días. [dict]."""
    rendidas = contar_descargas_fallidas()
    prendidas = {"fotos": obtener_config("fotos_automaticas", "0") == "1",
                 "equiv": obtener_config("equiv_ficha_automaticas", "0") == "1",
                 "catalogos": catalogos_de_fabricante_automaticos(),
                 "mercado_libre": mercado_libre_automatico()}
    corriendo = _CANDADO_FONDO.locked()
    filas = []
    for que, (nombre, fuente) in TAREAS_DE_FONDO.items():
        if not prendidas.get(que, True):
            estado = "⏸️ Apagada"
        elif _terminada(que):
            estado = f"✅ Terminada {_fecha_corta(obtener_config(f'terminado_{que}', ''))}"
        elif _descansando(que):
            estado = f"😴 Retoma {_fecha_corta(obtener_config(f'descanso_{que}', ''))}"
        elif que == "fotos_de_internet" and obtener_config("fotos_de_internet_pendientes",
                                                           "") != "1":
            estado = "✅ Al día"
        else:
            estado = "🟢 Corriendo" if corriendo else "⏳ En cola"
        fallidas = (sum(n for f, n in rendidas.items() if f.startswith(fuente))
                    if fuente else 0)
        filas.append({"Tarea": nombre, "Estado": estado, "Dejadas de intentar": fallidas})
    return filas


def mostrar_panel_de_carga_automatica():
    """El tablero de todo lo que se baja solo: en qué anda cada cosa, y los dos botones para
    pedirle que vuelva a buscar."""
    filas = estado_de_las_tareas_de_fondo()
    n_term = sum(f["Estado"].startswith("✅") for f in filas)
    n_corr = sum(f["Estado"].startswith(("🟢", "⏳")) for f in filas)
    with st.expander(f"⚡ Carga automática — {n_term} terminada(s)"
                     + (f", {n_corr} en curso" if n_corr else "")):
        ayuda(
            "Fotos, fichas, catálogos de fabricantes y Mercado Libre se bajan solos en segundo "
            "plano, **sin tope por día**, hasta terminar.\n\n"
            "**Cuando una termina, no se repite**: ni cada rato, ni al reiniciar la app. Se "
            "vuelve a correr solo si tocás **🔄 Buscar lo nuevo** (o si prendés la opción de "
            "abajo para cuando importás una lista). Y al volver a correr **no baja nada de lo "
            "que ya bajó**: cada foto, ficha y búsqueda queda anotada, y solo se pide lo que "
            "falta —por ejemplo, los productos de una lista nueva—.\n\n"
            "Lo que falla por la red (el sitio no contesta) se reintenta **una vez por día, "
            "hasta tres días**; después se deja de intentar y figura en «Dejadas de intentar». "
            "Con **♻️ Reintentar las que fallaron** se vuelven a probar solo esas.")
        # Una lista y no st.dataframe: son seis renglones, se leen mejor en el celular y la
        # tabla costaba 0,3 s en cada toque de Mantenimiento, donde este panel va arriba de todo.
        st.markdown("  \n".join(
            f"{f['Estado']} — **{f['Tarea']}**"
            + (f" · {miles(f['Dejadas de intentar'])} dejadas de intentar"
               if f["Dejadas de intentar"] else "")
            for f in filas))
        _c1, _c2 = st.columns(2)
        if _c1.button("🔄 Buscar lo nuevo", key="carga_auto_lo_nuevo", width="stretch",
                      help="Reabre las tareas terminadas. Solo busca lo que todavía no se bajó."):
            buscar_lo_nuevo()
            st.success("Listo: va a buscar solo lo que falta, en segundo plano.")
        _n_f = sum(f["Dejadas de intentar"] for f in filas)
        if _n_f and _c2.button(f"♻️ Reintentar las {miles(_n_f)} que fallaron",
                               key="carga_auto_reintentar", width="stretch"):
            reintentar_descargas_fallidas()
            st.success(f"Se van a volver a probar {miles(_n_f)}. Lo que ya bajó no se toca.")
        _al_importar = st.toggle(
            "Al importar una lista, buscar solo lo nuevo de esa lista",
            value=obtener_config("buscar_lo_nuevo_al_importar", "0") == "1",
            key="carga_auto_al_importar",
            help="Apagado: después de importar no arranca nada hasta que toques «Buscar lo "
                 "nuevo». Prendido: arranca solo, pero igual baja únicamente lo que falta.")
        if _al_importar != (obtener_config("buscar_lo_nuevo_al_importar", "0") == "1"):
            guardar_config("buscar_lo_nuevo_al_importar", "1" if _al_importar else "0")
        # El barrido de todo el catálogo es lo que más memoria pide: medido con 63 proveedores,
        # unos 2 GB. Con un catálogo así de grande, en el servidor gratis conviene apagarlo y
        # correrlo a mano (ver miga_hasta("Buscar equivalencias en TODO el catálogo de una")).
        _barrido = st.toggle(
            "Después de importar, barrer todo el catálogo buscando pares por descripción",
            value=obtener_config("barrido_automatico", "1") == "1",
            key="carga_auto_barrido",
            help="Es lo que más memoria usa de todo lo automático. Con muchos proveedores (más de "
                 "30 o 40) conviene apagarlo y correrlo a mano de vez en cuando: "
                 f"{miga_hasta('Buscar equivalencias en TODO el catálogo de una')}. Apagado, lo "
                 "demás de después de importar sigue igual.")
        if _barrido != (obtener_config("barrido_automatico", "1") == "1"):
            guardar_config("barrido_automatico", "1" if _barrido else "0")

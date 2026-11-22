"""Lógica: se carga una vez por proceso, en el mismo espacio de nombres que el resto de logica/
(ver orden.py). Usa sin importarlos los nombres de las partes anteriores."""
from datetime import timezone as _zona_utc

# ============================================================================================
# LOS MENSAJES: WHATSAPP, FACEBOOK E INSTAGRAM EN UNA BANDEJA
# ============================================================================================
# El dueño lo pidió así: «una sección de mensajes en la cual puedas vincular los mensajes de
# WhatsApp, Facebook, Instagram y demás, para que los podamos contestar directamente desde la
# página, que nos salten los chats todos ahí que no estén leídos y poder ir contestando». Los
# mensajes llegaban a tres aplicaciones distintas, en el teléfono de uno, y el que estaba en el
# mostrador no los veía.
#
# CÓMO LLEGA CADA UNO (lo dice Meta, no la app):
#   · Facebook (Messenger) e Instagram: con el permiso de la página («token»), la app le pregunta
#     a Meta cada tanto por las conversaciones de la página (GET /{página}/conversations). No
#     hace falta nada más que el permiso.
#   · WhatsApp: Meta NO deja preguntar. Los mensajes los AVISA, mandándolos a una dirección de
#     internet fija que tiene que contestar siempre. La app de Streamlit se duerme y cambia de
#     dirección, así que no puede ser ella: va un «relevo» chiquito y gratis (un Cloudflare
#     Worker, en integraciones/relevo_de_mensajes/) que recibe el aviso, controla que lo firmó
#     Meta, y lo guarda hasta que la app lo pasa a buscar. Contestar sí va directo a Meta.
#   · Meta no dice qué chat está leído: eso lo lleva la app (ver «LA BANDEJA»).
#
# LAS CLAVES, SOLO EN LOS SECRETOS DE STREAMLIT, en una sección [mensajes] (ver los pasos en
# Administrar → 💬 Mensajería y cobros). Nunca se muestran, nunca van en la dirección de un
# pedido —van en la cabecera Authorization, así un error de red que trae la dirección entera no
# las lleva— y los errores de Meta se dicen en castellano con su número, sin su texto.

# Los canales, con el nombre y el color con que se ven en la bandeja.
CANALES_DE_MENSAJES = {
    "whatsapp": {"nombre": "WhatsApp", "icono": "🟢"},
    "messenger": {"nombre": "Facebook", "icono": "🔵"},
    "instagram": {"nombre": "Instagram", "icono": "🟣"},
}
GRAPH_DE_META = "https://graph.facebook.com/v26.0"
# Cada cuánto se le pregunta a Meta y al relevo, como mucho. Lo largan las pantallas de los
# empleados (ver _lo_que_termino_otro() en app.py, que pasa cada 20 segundos): con la app sin
# nadie mirando no se pregunta nada, y al volver alguien llega todo lo que se juntó. Un minuto
# por el relevo: en el plan gratis de Cloudflare, mirar qué hay guardado se puede 1.000 veces
# por día, y con la app abierta doce horas son 720.
CADA_CUANTO_SE_MIRAN_LOS_MENSAJES = 60
# Meta deja contestar libremente hasta 24 horas después del último mensaje del cliente (en los
# tres canales). Después, en WhatsApp hace falta una plantilla aprobada, y en Facebook e
# Instagram, un permiso especial: la app no lo intenta y lo dice antes.
VENTANA_PARA_CONTESTAR = timedelta(hours=24)
# Lo más largo que deja mandar Meta en un mensaje de texto, en cada canal. Era una sola regla
# de 2.000 para los tres, y una cotización larga por WhatsApp (que acepta 4.096) no salía.
LARGO_MAXIMO_POR_CANAL = {"whatsapp": 4096, "messenger": 2000, "instagram": 1000}
# El chat abierto en «💬 Mensajes» queda «en curso» este rato: mientras tanto, la cotización y
# el presupuesto ofrecen mandárselo (ver chat_para_mandar()). Más, y un chat de la mañana
# aparecía en el presupuesto de otro cliente a la tarde.
MINUTOS_QUE_QUEDA_EN_CURSO_UN_CHAT = 30
TEXTO_FUERA_DE_LA_VENTANA = (
    "Pasaron más de 24 horas desde su último mensaje: Meta no deja contestar desde acá (es una "
    "regla de Meta, no de la app). Escribile desde el teléfono, o esperá a que vuelva a escribir.")
# Lo que no es texto (una foto, un audio): se dice qué es, y se mira en el teléfono.
_TEXTO_DE_CADA_TIPO = {
    "image": "📷 Foto", "audio": "🎤 Audio", "voice": "🎤 Audio", "video": "🎬 Video",
    "document": "📄 Archivo", "file": "📄 Archivo", "sticker": "🙂 Sticker",
    "location": "📍 Ubicación", "contacts": "👤 Contacto", "share": "🔗 Algo compartido",
    "story_mention": "📣 Te mencionó en una historia", "reaction": "👍 Reacción",
    "ig_reel": "🎬 Un reel", "template": "📋 Mensaje automático"}
# Lo que se suma a la respuesta con un toque (ver la pantalla): lo que más se contesta. El
# administrador las cambia por las suyas (el horario, la dirección) en Administrar → 💬
# Mensajería y cobros: ver respuestas_rapidas().
CLAVE_DE_LAS_RESPUESTAS_RAPIDAS = "respuestas_rapidas_de_los_chats"
RESPUESTAS_RAPIDAS = ["¡Hola! ¿En qué te ayudo?", "Sí, lo tenemos.",
                      "No lo tenemos ahora: te lo consigo y te aviso.",
                      "¿Me pasás marca, modelo y año del auto (o la patente)?",
                      "¿Me mandás una foto del repuesto o del código?",
                      "Te lo reservo: pasalo a buscar cuando quieras.", "¡Gracias!"]
TEXTO_DE_UN_ADJUNTO = "📎 Mandó algo que no es texto (foto, audio o archivo): miralo en el teléfono."
# Un mensaje larguísimo no llena la base: lo que pase de acá se corta.
_LARGO_QUE_SE_GUARDA = 4000

# Lo que dura lo que el proceso: el candado de la tanda, cuándo fue la última y cómo le fue a
# cada canal (ver del_proceso(): a este nivel, cada pasada crearía otro).
_BANDEJA = del_proceso("bandeja_de_mensajes",
                       lambda: {"candado": threading.Lock(), "ultima": None, "estado": {},
                                "propios": {}})


# ============================================================================================
# LA CONEXIÓN CON META
# ============================================================================================
_CLAVES_DE_LOS_MENSAJES = ("meta_token", "meta_pagina_id", "instagram", "whatsapp_token",
                           "whatsapp_numero_id", "relevo_url", "relevo_clave")


def config_de_los_mensajes():
    """Lo de la sección [mensajes] de los secretos, como textos ("" lo que falta). Nunca falla."""
    try:
        crudo = dict(secretos_app().get("mensajes") or {})
    except Exception as _err:          # noqa: BLE001 — sin secretos legibles no hay canales
        anotar_error("config_de_los_mensajes", _err)
        crudo = {}
    return {clave: str(crudo.get(clave) or "").strip() for clave in _CLAVES_DE_LOS_MENSAJES}


def canales_conectados(cfg=None):
    """Qué está puesto en los secretos (no si anda: eso lo dice probar_los_canales()).
    «whatsapp» es poder CONTESTAR por WhatsApp; «relevo», poder RECIBIR los de WhatsApp."""
    cfg = cfg or config_de_los_mensajes()
    meta = bool(cfg["meta_token"] and cfg["meta_pagina_id"])
    return {"messenger": meta,
            "instagram": meta and cfg["instagram"].lower() not in ("no", "false", "0"),
            "whatsapp": bool(cfg["whatsapp_token"] and cfg["whatsapp_numero_id"]),
            # Solo https: la clave del relevo viaja en la cabecera y no puede ir en claro.
            "relevo": bool(cfg["relevo_url"].lower().startswith("https://")
                           and cfg["relevo_clave"])}


def hay_mensajes_conectados(cfg=None):
    """Si hay de dónde traer mensajes: sin eso la bandeja de fondo no hace nada."""
    conectados = canales_conectados(cfg)
    return conectados["messenger"] or conectados["relevo"]


# Los errores de Meta que se entienden, por su número (y el «subcódigo», que va primero cuando
# dice algo más preciso que el código). El texto de Meta viene en inglés y a veces con datos
# del pedido: no se muestra.
_ERRORES_DE_META = (
    ({2018278, 2534022, 131047, 2018108}, "fuera", TEXTO_FUERA_DE_LA_VENTANA),
    ({190, 102, 463, 467}, "permiso",
     "El permiso de Meta (el «token») venció o no es válido: hay que generar uno nuevo y ponerlo "
     "en los secretos (ver Administrar → 💬 Mensajería y cobros)."),
    ({131030}, "prueba",
     "La cuenta de WhatsApp está en modo de prueba: solo se le puede escribir a los números "
     "anotados como de prueba en Meta."),
    ({131026, 551, 1545041}, "destino",
     "Ese cliente no puede recibir mensajes por este canal ahora (cambió de número, lo bloqueó o "
     "no tiene la aplicación)."),
    ({4, 17, 32, 613, 80006, 130429, 131048, 131056}, "freno",
     "Meta frenó por demasiados pedidos seguidos: probá de nuevo en unos minutos."),
    ({10, 200, 230, 299, 3, 2018065}, "falta_permiso",
     "A la app de Meta le falta un permiso para esto (ver los pasos en Administrar → 💬 "
     "Mensajería y cobros)."),
    ({100, 803}, "dato",
     "Meta no reconoce la página, el número o el destinatario: revisá los números puestos en "
     "los secretos."),
)


def error_de_meta_en_castellano(estado_http, error):
    """Un error de Meta para la pantalla: qué pasa y el número, nunca su texto."""
    error = error if isinstance(error, dict) else {}
    numeros = []
    for campo in ("error_subcode", "code"):
        try:
            numeros.append(int(error.get(campo)))
        except (TypeError, ValueError):
            continue
    for numero in numeros:
        for codigos, _tipo, texto in _ERRORES_DE_META:
            if numero in codigos:
                return f"{texto} (código {numero})"
    detalle = f"código {numeros[-1]}" if numeros else f"respuesta {int(estado_http or 0)}"
    return f"Meta no lo aceptó ({detalle})."


def _pedir_a_meta(metodo, ruta, token, params=None, cuerpo=None):
    """(datos, error) de un pedido a Meta. El permiso va en la cabecera, nunca en la dirección."""
    try:
        r = requests.request(metodo, f"{GRAPH_DE_META}/{str(ruta).lstrip('/')}", params=params,
                             json=cuerpo, timeout=15,
                             headers={"Authorization": f"Bearer {token}"})
    except Exception as _err:          # noqa: BLE001 — sin internet no hay mensajes, y se dice
        anotar_error("mensajes/meta", _err)
        return None, f"No se pudo hablar con Meta ({el_error_en_castellano(_err)})."
    try:
        datos = r.json() if r.content else {}
    except ValueError:
        datos = {}
    if not isinstance(datos, dict):
        datos = {}
    if r.status_code >= 400 or datos.get("error"):
        error = datos.get("error") if isinstance(datos.get("error"), dict) else {}
        anotar_error("mensajes/meta", RuntimeError(
            f"{metodo} {r.status_code} código {error.get('code')}/{error.get('error_subcode')}"))
        return None, error_de_meta_en_castellano(r.status_code, error)
    return datos, None


def _pedir_al_relevo(metodo, ruta, cfg, cuerpo=None):
    """(datos, error) de un pedido al relevo de WhatsApp. Su clave, en la cabecera."""
    try:
        r = requests.request(metodo, f"{cfg['relevo_url'].rstrip('/')}/{ruta}", json=cuerpo,
                             timeout=15, headers={"Authorization": f"Bearer {cfg['relevo_clave']}"})
    except Exception as _err:          # noqa: BLE001
        anotar_error("mensajes/relevo", _err)
        return None, f"No se pudo hablar con el relevo de WhatsApp ({el_error_en_castellano(_err)})."
    if r.status_code in (401, 403):
        return None, ("El relevo de WhatsApp no aceptó la clave: «relevo_clave» tiene que ser la "
                      "misma en los secretos y en el relevo.")
    if r.status_code != 200:
        return None, f"El relevo de WhatsApp respondió {int(r.status_code)}."
    try:
        datos = r.json() if r.content else {}
    except ValueError:
        return None, "El relevo de WhatsApp contestó algo que no se entiende."
    return (datos if isinstance(datos, dict) else {}), None


def _momento_utc(valor):
    """Una hora de Meta («2026-11-18T14:03:12+0000», segundos o milisegundos desde 1970) como la
    guarda la app: «2026-11-18 14:03:12», en UTC. Sin hora que se entienda, la de ahora."""
    try:
        if isinstance(valor, (int, float)) or str(valor or "").strip().isdigit():
            numero = float(valor)
            if numero > 1e11:          # milisegundos (Messenger e Instagram los mandan así)
                numero /= 1000
            return datetime.fromtimestamp(numero, _zona_utc.utc).strftime("%Y-%m-%d %H:%M:%S")
        texto = str(valor or "").strip()
        if texto:
            momento = datetime.strptime(re.sub(r"([+-]\d\d):?(\d\d)$", r"\1\2", texto),
                                        "%Y-%m-%dT%H:%M:%S%z")
            return momento.astimezone(_zona_utc.utc).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OverflowError, OSError):
        pass
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ============================================================================================
# LO QUE AVISA META: LEER UN AVISO (WEBHOOK)
# ============================================================================================
# El relevo guarda los avisos tal cual llegan. Uno puede traer varios mensajes, de WhatsApp
# («whatsapp_business_account») o de la página y de Instagram («page», «instagram»). Lo que no
# es un mensaje —«entregado», «leído», una reacción borrada— no se guarda.
def _como_lista(valor):
    """Lo que tendría que ser una lista, o [] si en el aviso vino otra cosa."""
    return valor if isinstance(valor, list) else []


def _texto_de_whatsapp(m):
    tipo = str(m.get("type") or "")
    if tipo == "text":
        return str((m.get("text") or {}).get("body") or "")
    if tipo == "button":
        return str((m.get("button") or {}).get("text") or "")
    if tipo == "interactive":
        dentro = m.get("interactive") or {}
        elegido = dentro.get("button_reply") or dentro.get("list_reply") or {}
        return str(elegido.get("title") or "")
    if tipo == "reaction":
        return f"{_TEXTO_DE_CADA_TIPO['reaction']} {str((m.get('reaction') or {}).get('emoji') or '')}".strip()
    nombre = _TEXTO_DE_CADA_TIPO.get(tipo)
    if not nombre:
        return TEXTO_DE_UN_ADJUNTO
    epigrafe = str((m.get(tipo) or {}).get("caption") or "") if isinstance(m.get(tipo), dict) else ""
    return f"{nombre}: {epigrafe}" if epigrafe else f"{nombre} (miralo en el teléfono)."


def _texto_de_messenger(mensaje):
    texto = str(mensaje.get("text") or "")
    if texto:
        return texto
    adjuntos = _como_lista(mensaje.get("attachments"))
    if adjuntos and isinstance(adjuntos[0], dict):
        nombre = _TEXTO_DE_CADA_TIPO.get(str(adjuntos[0].get("type") or ""))
        if nombre:
            return f"{nombre} (miralo en el teléfono)."
    return TEXTO_DE_UN_ADJUNTO


def mensajes_del_aviso(cuerpo):
    """Los mensajes de un aviso de Meta: [{canal, chat, nombre, id, texto, cuando, entra}]. No
    falla con un aviso raro: lo que no entiende lo saltea."""
    if isinstance(cuerpo, str):
        try:
            cuerpo = json.loads(cuerpo)
        except ValueError:
            return []
    if not isinstance(cuerpo, dict):
        return []
    salida = []
    objeto = str(cuerpo.get("object") or "")
    for entrada in _como_lista(cuerpo.get("entry")):
        if not isinstance(entrada, dict):
            continue
        if objeto == "whatsapp_business_account":
            for cambio in _como_lista(entrada.get("changes")):
                valor = cambio.get("value") if isinstance(cambio, dict) else None
                if not isinstance(valor, dict):
                    continue
                nombres = {str(ct.get("wa_id") or ""): str((ct.get("profile") or {}).get("name") or "")
                           for ct in _como_lista(valor.get("contacts")) if isinstance(ct, dict)}
                for m in _como_lista(valor.get("messages")):
                    if isinstance(m, dict) and m.get("id") and m.get("from"):
                        salida.append({"canal": "whatsapp", "chat": str(m["from"]),
                                       "nombre": nombres.get(str(m["from"]), ""),
                                       "id": str(m["id"]), "texto": _texto_de_whatsapp(m),
                                       "cuando": _momento_utc(m.get("timestamp")), "entra": True})
                # Con la «coexistencia» (el mismo número en la aplicación del teléfono y acá), lo
                # que se contesta desde el teléfono llega como eco: se suma al chat como nuestro.
                for m in _como_lista(valor.get("message_echoes")):
                    if isinstance(m, dict) and m.get("id") and m.get("to"):
                        salida.append({"canal": "whatsapp", "chat": str(m["to"]), "nombre": "",
                                       "id": str(m["id"]), "texto": _texto_de_whatsapp(m),
                                       "cuando": _momento_utc(m.get("timestamp")), "entra": False})
        elif objeto in ("page", "instagram"):
            canal = "messenger" if objeto == "page" else "instagram"
            for evento in _como_lista(entrada.get("messaging")):
                mensaje = (evento or {}).get("message") if isinstance(evento, dict) else None
                if not isinstance(mensaje, dict) or not mensaje.get("mid") or mensaje.get("is_deleted"):
                    continue
                eco = bool(mensaje.get("is_echo"))
                otro = (evento.get("recipient") if eco else evento.get("sender")) or {}
                if not otro.get("id"):
                    continue
                salida.append({"canal": canal, "chat": str(otro["id"]), "nombre": "",
                               "id": str(mensaje["mid"]), "texto": _texto_de_messenger(mensaje),
                               "cuando": _momento_utc(evento.get("timestamp")), "entra": not eco})
    return salida


# ============================================================================================
# GUARDAR LO QUE LLEGA
# ============================================================================================
def guardar_mensaje_de_afuera(m, contar_sin_leer=True):
    """Guarda un mensaje de un cliente (o uno nuestro mandado desde otro lado). Devuelve si era
    nuevo: el mismo mensaje traído dos veces —el relevo que reintenta, Meta que avisa y además
    se pregunta— entra una sola vez (UNIQUE(canal, externo_id))."""
    canal = str(m.get("canal") or "")
    if canal not in CANALES_DE_MENSAJES or not m.get("chat") or not m.get("id"):
        return False
    texto = str(m.get("texto") or "")[:_LARGO_QUE_SE_GUARDA]
    cuando = str(m.get("cuando") or _momento_utc(None))
    entra = 1 if m.get("entra") else 0
    with transaccion():
        c.execute("""INSERT INTO chats (canal, externo, nombre) VALUES (?, ?, ?)
                     ON CONFLICT(canal, externo) DO UPDATE SET
                         nombre = COALESCE(NULLIF(excluded.nombre, ''), chats.nombre)""",
                  (canal, str(m["chat"]), str(m.get("nombre") or "")[:120]))
        chat_id = c.execute("SELECT id FROM chats WHERE canal = ? AND externo = ?",
                            (canal, str(m["chat"]))).fetchone()[0]
        c.execute("""INSERT OR IGNORE INTO chat_mensajes (chat_id, canal, externo_id, entra, texto,
                                                          cuando, quien)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (chat_id, canal, str(m["id"])[:200], entra, texto, cuando,
                   None if entra else "desde otro lado"))
        if c.rowcount != 1:
            return False
        if entra:
            c.execute("""UPDATE chats SET sin_leer = sin_leer + ?,
                             ultimo_del_cliente_en = MAX(COALESCE(ultimo_del_cliente_en, ''), ?)
                         WHERE id = ?""", (1 if contar_sin_leer else 0, cuando, chat_id))
        else:
            # Lo contestaron desde el teléfono: ya está atendido, si es posterior a lo del cliente.
            c.execute("""UPDATE chats SET sin_leer = 0
                         WHERE id = ? AND COALESCE(ultimo_del_cliente_en, '') <= ?""",
                      (chat_id, cuando))
        c.execute("""UPDATE chats SET ultimo_texto = ?, ultimo_en = ?, ultimo_entra = ?
                     WHERE id = ? AND COALESCE(ultimo_en, '') <= ?""",
                  (texto[:200], cuando, entra, chat_id, cuando))
    return True


def _ids_propios(cfg):
    """Los números con que Meta nombra al negocio en las conversaciones: la página y su cuenta
    de Instagram. Lo que viene de uno de ellos es nuestro, no del cliente. La de Instagram se
    pregunta una vez por proceso."""
    propios = _BANDEJA["propios"]
    if propios.get("pagina") != cfg["meta_pagina_id"]:
        propios.clear()
        propios["pagina"] = cfg["meta_pagina_id"]
        datos, error = _pedir_a_meta("GET", cfg["meta_pagina_id"], cfg["meta_token"],
                                     params={"fields": "instagram_business_account"})
        if error:
            propios.clear()            # se vuelve a preguntar la próxima vez
        else:
            propios["instagram"] = str(((datos or {}).get("instagram_business_account") or {})
                                       .get("id") or "")
    return {cfg["meta_pagina_id"], propios.get("instagram") or cfg["meta_pagina_id"]}


def _traer_de_meta(canal, cfg):
    """(nuevos, error): las últimas conversaciones de la página en Facebook o en Instagram."""
    datos, error = _pedir_a_meta(
        "GET", f"{cfg['meta_pagina_id']}/conversations", cfg["meta_token"],
        params={"platform": canal, "limit": 25,
                "fields": "id,updated_time,participants,"
                          "messages.limit(20){id,message,from,created_time}"})
    if error:
        return 0, error
    propios = _ids_propios(cfg)
    # Lo de antes de conectar el canal entra como leído: si no, el primer día saltaban todas
    # las conversaciones viejas de la página como nuevas.
    primera_vez = not obtener_config(f"mensajes_desde_{canal}", "")
    nuevos = 0
    for conversacion in _como_lista((datos or {}).get("data")):
        if not isinstance(conversacion, dict) or not isinstance(conversacion.get("participants"), dict):
            continue
        participantes = _como_lista((conversacion.get("participants") or {}).get("data"))
        cliente = next((p for p in participantes
                        if isinstance(p, dict) and str(p.get("id") or "") not in propios), None)
        if not cliente or not cliente.get("id"):
            continue
        nombre = str(cliente.get("name") or cliente.get("username") or "")
        mensajes = [x for x in _como_lista((conversacion.get("messages") or {}).get("data"))
                    if isinstance(x, dict) and x.get("id")]
        for x in sorted(mensajes, key=lambda x: str(x.get("created_time") or "")):
            de = str((x.get("from") or {}).get("id") or "")
            if guardar_mensaje_de_afuera(
                    {"canal": canal, "chat": str(cliente["id"]), "nombre": nombre, "id": x["id"],
                     "texto": str(x.get("message") or "") or TEXTO_DE_UN_ADJUNTO,
                     "cuando": _momento_utc(x.get("created_time")), "entra": de not in propios},
                    contar_sin_leer=not primera_vez):
                nuevos += 1
    if primera_vez:
        guardar_config(f"mensajes_desde_{canal}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return nuevos, None


def _traer_del_relevo(cfg):
    """(nuevos, error): los avisos que juntó el relevo. Se le confirman recién después de
    guardados: si algo se corta en el medio, vuelven a venir, y entran una vez igual."""
    datos, error = _pedir_al_relevo("GET", "avisos", cfg)
    if error:
        return 0, error
    primera_vez = not obtener_config("mensajes_desde_relevo", "")
    nuevos, listos = 0, []
    for aviso in _como_lista((datos or {}).get("avisos"))[:200]:
        if not isinstance(aviso, dict) or not aviso.get("id"):
            continue
        try:
            leidos = mensajes_del_aviso(aviso.get("cuerpo"))
        except (TypeError, AttributeError, ValueError) as _err:
            # Un aviso que no se entiende se confirma igual: si no, volvería en cada vuelta.
            anotar_error("mensajes/aviso raro", _err)
            leidos = []
        for m in leidos:
            nuevos += guardar_mensaje_de_afuera(m, contar_sin_leer=not primera_vez)
        listos.append(str(aviso["id"]))
    if listos:
        _datos, error = _pedir_al_relevo("POST", "confirmar", cfg, cuerpo={"ids": listos})
    if primera_vez and not error:
        guardar_config("mensajes_desde_relevo", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return nuevos, error


def traer_mensajes_nuevos(cfg=None):
    """Trae lo nuevo de cada canal conectado. Devuelve {canal: (nuevos, error)} y deja anotado
    cómo le fue a cada uno, para la pantalla (ver estado_de_los_canales())."""
    cfg = cfg or config_de_los_mensajes()
    conectados = canales_conectados(cfg)
    resultado = {}
    for canal, conectado in (("messenger", conectados["messenger"]),
                             ("instagram", conectados["instagram"]),
                             ("relevo", conectados["relevo"])):
        if not conectado:
            continue
        try:
            resultado[canal] = (_traer_del_relevo(cfg) if canal == "relevo"
                                else _traer_de_meta(canal, cfg))
        except sqlite3.Error as _err:
            anotar_error(f"traer_mensajes_nuevos/{canal}", _err)
            resultado[canal] = (0, "No se pudo guardar en la base: probá en un rato.")
        _BANDEJA["estado"][canal] = {"cuando": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                     "nuevos": resultado[canal][0],
                                     "error": resultado[canal][1]}
    return resultado


def estado_de_los_canales():
    """{canal: {"cuando", "nuevos", "error"}} de la última vez que se trajo, en este proceso."""
    return dict(_BANDEJA["estado"])


def arrancar_la_bandeja_de_fondo():
    """Larga en un hilo aparte la vuelta por los canales, si toca. Devuelve si la largó.
    Se llama seguido y casi siempre vuelve enseguida: sin canales, con una vuelta corriendo o
    con la última hace menos de CADA_CUANTO_SE_MIRAN_LOS_MENSAJES segundos."""
    if os.environ.get("EQUIVALENCIAS_SIN_TAREAS_DE_FONDO") == "1":
        return False
    cfg = config_de_los_mensajes()
    if not hay_mensajes_conectados(cfg):
        return False
    # «Ninguna todavía» es None y no 0: time.monotonic() cuenta desde que se prendió la máquina,
    # y en una recién prendida (un servidor reiniciado, las de GitHub) vale menos de un minuto:
    # con 0, la primera vuelta se salteaba. Lo vio la prueba en GitHub.
    _ultima = _BANDEJA["ultima"]
    if _ultima is not None and time.monotonic() - _ultima < CADA_CUANTO_SE_MIRAN_LOS_MENSAJES:
        return False
    # El candado se toma acá, antes del hilo: dos pestañas juntas no largan dos vueltas (ver
    # arrancar_tanda_de_fondo()).
    if not _BANDEJA["candado"].acquire(blocking=False):
        return False
    _BANDEJA["ultima"] = time.monotonic()

    def correr():
        try:
            traer_mensajes_nuevos(cfg)
        except Exception as _err:      # noqa: BLE001 — un hilo de fondo no puede tirar la app
            anotar_error("arrancar_la_bandeja_de_fondo", _err)
        finally:
            _BANDEJA["candado"].release()

    try:
        threading.Thread(target=correr, daemon=True, name="bandeja_de_mensajes").start()
        return True
    except RuntimeError as _err:
        _BANDEJA["candado"].release()
        anotar_error("arrancar_la_bandeja_de_fondo", _err)
        return False


def traer_mensajes_ahora():
    """«🔄 Traer ahora»: la vuelta en el momento, esperando la que está corriendo si hay una.
    Devuelve {canal: (nuevos, error)}, o None si no se pudo tomar el turno."""
    exigir_nivel("empleado", "traer los mensajes")
    if not _BANDEJA["candado"].acquire(timeout=20):
        return None
    try:
        _BANDEJA["ultima"] = time.monotonic()
        return traer_mensajes_nuevos()
    finally:
        _BANDEJA["candado"].release()


# ============================================================================================
# LA BANDEJA
# ============================================================================================
# «Sin leer» lo lleva la app: cada mensaje nuevo de un cliente suma uno al chat, y se pone en
# cero cuando alguien lo abre en la bandeja o lo contesta (desde acá o desde el teléfono).
# «Sin contestar» es otra cosa: lo último del chat es del cliente, aunque alguien ya lo haya
# leído. Las dos se ven en la bandeja.
FILTROS_DE_LA_BANDEJA = {"todos": "Todos", "sin_leer": "🔴 Sin leer",
                         "sin_contestar": "⏳ Sin contestar"}


def chats_de_la_bandeja(filtro="todos", texto="", limite=60):
    """Los chats para la lista: los sin leer primero, después lo más nuevo."""
    donde, valores = ["1 = 1"], []
    if filtro == "sin_leer":
        donde.append("sin_leer > 0")
    elif filtro == "sin_contestar":
        donde.append("ultimo_entra = 1")
    if str(texto or "").strip():
        donde.append("(nombre LIKE ? OR externo LIKE ? OR ultimo_texto LIKE ?)")
        valores += [f"%{str(texto).strip()}%"] * 3
    # ultimo_quien: quién mandó lo último (para «Ana: …» en la lista; «desde otro lado» si se
    # contestó desde el teléfono).
    filas = c.execute(f"""SELECT id, canal, externo, nombre, ultimo_texto, ultimo_en, ultimo_entra,
                                 ultimo_del_cliente_en, sin_leer, leido_por,
                                 (SELECT m.quien FROM chat_mensajes m WHERE m.chat_id = chats.id
                                  ORDER BY m.cuando DESC, m.id DESC LIMIT 1) AS ultimo_quien
                          FROM chats WHERE {' AND '.join(donde)}
                          ORDER BY (sin_leer > 0) DESC, COALESCE(ultimo_en, '') DESC
                          LIMIT ?""", valores + [int(limite)]).fetchall()
    return [dict(f) for f in filas]


def el_chat(chat_id):
    fila = c.execute("SELECT * FROM chats WHERE id = ?", (int(chat_id),)).fetchone()
    return dict(fila) if fila else None


def mensajes_del_chat(chat_id, limite=80):
    """Los últimos `limite` mensajes del chat, del más viejo al más nuevo."""
    filas = c.execute("""SELECT id, entra, texto, cuando, quien FROM chat_mensajes
                         WHERE chat_id = ? ORDER BY cuando DESC, id DESC LIMIT ?""",
                      (int(chat_id), int(limite))).fetchall()
    return [dict(f) for f in reversed(filas)]


def respuestas_rapidas():
    """Las del administrador (una por renglón), o las de siempre si no puso ninguna."""
    propias = [x.strip() for x in str(obtener_config(CLAVE_DE_LAS_RESPUESTAS_RAPIDAS, "") or "")
               .splitlines() if x.strip()]
    return propias[:15] or list(RESPUESTAS_RAPIDAS)


def guardar_respuestas_rapidas(texto):
    """Las guarda (una por renglón, hasta 15 de hasta 300 letras). Vacío vuelve a las de
    siempre. Devuelve cuántas quedaron."""
    exigir_nivel("admin", "cambiar las respuestas rápidas de los chats")
    renglones = [x.strip()[:300] for x in str(texto or "").splitlines() if x.strip()][:15]
    guardar_config(CLAVE_DE_LAS_RESPUESTAS_RAPIDAS, "\n".join(renglones))
    anotar_cambio("cambió las respuestas rápidas", "configuración", CLAVE_DE_LAS_RESPUESTAS_RAPIDAS,
                  despues=renglones)
    return len(renglones)


def hace_cuanto_espera(momento, ahora=None):
    """«hace 5 min», «hace 2 h», «hace 3 días»: desde lo último del cliente (guardado en UTC)."""
    try:
        desde = datetime.strptime(str(momento or "")[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ""
    minutos = max(0, int(((ahora or datetime.now()) - desde).total_seconds() // 60))
    if minutos < 60:
        return f"hace {minutos} min"
    return f"hace {minutos // 60} h" if minutos < 48 * 60 else f"hace {minutos // 1440} días"


def texto_de_chat_para_markdown(texto):
    """Lo que escribió un cliente, listo para st.markdown: sin formato, sin enlaces ni imágenes
    (un «![](http://…)» suyo cargaría una imagen de afuera en la pantalla del empleado), sin
    fórmulas por dos «$», y con sus saltos de renglón."""
    escapado = texto_para_markdown(texto).replace("$", "\\$").replace("~", "\\~")
    return escapado.replace("\r\n", "\n").replace("\n", "  \n")


def nombre_del_chat(chat):
    """El nombre para mostrar: el que puso el cliente, o el canal y el final del número."""
    nombre = str((chat or {}).get("nombre") or "").strip()
    if nombre:
        return nombre
    canal = CANALES_DE_MENSAJES.get((chat or {}).get("canal"), {}).get("nombre", "Cliente")
    externo = str((chat or {}).get("externo") or "")
    return (f"+{externo}" if (chat or {}).get("canal") == "whatsapp" and externo.isdigit()
            else f"Cliente de {canal} …{externo[-4:]}")


def cuantos_chats_sin_leer():
    """Para la barra («💬 Mensajes · 3»). 0 si la base no contesta."""
    try:
        return int(c.execute("SELECT COUNT(*) FROM chats WHERE sin_leer > 0").fetchone()[0] or 0)
    except sqlite3.Error as _err:
        anotar_error("cuantos_chats_sin_leer", _err)
        return 0


def chats_sin_leer(limite=5):
    """(cuántos chats sin leer, [(ícono del canal, nombre, cuántos mensajes)] de los primeros).
    Solo lee, y nada de lo que escribieron: es lo que usa el asistente (ver «LO QUE PASA AHORA»
    en logica/asistente_datos.py)."""
    filas = c.execute("""SELECT canal, externo, nombre, sin_leer FROM chats WHERE sin_leer > 0
                         ORDER BY COALESCE(ultimo_en, '') DESC""").fetchall()
    return len(filas), [(CANALES_DE_MENSAJES.get(f["canal"], {}).get("icono", "💬"),
                         nombre_del_chat(dict(f)), int(f["sin_leer"]))
                        for f in filas[:int(limite)]]


def ultimo_mensaje_guardado():
    """El número del último mensaje guardado: desde ahí se avisa lo que llega (ver
    mensajes_nuevos_desde())."""
    try:
        return int(c.execute("SELECT COALESCE(MAX(id), 0) FROM chat_mensajes").fetchone()[0])
    except sqlite3.Error as _err:
        anotar_error("ultimo_mensaje_guardado", _err)
        return 0


def mensajes_nuevos_desde(desde_id, limite=5):
    """Los mensajes de clientes llegados después de `desde_id` y todavía sin leer: los que
    saltan como cartel. [{id, canal, nombre, texto}]."""
    filas = c.execute("""SELECT m.id, ch.canal, ch.externo, ch.nombre, m.texto
                         FROM chat_mensajes m JOIN chats ch ON ch.id = m.chat_id
                         WHERE m.id > ? AND m.entra = 1 AND ch.sin_leer > 0
                         ORDER BY m.id LIMIT ?""", (int(desde_id), int(limite))).fetchall()
    return [{"id": f["id"], "canal": f["canal"], "nombre": nombre_del_chat(dict(f)),
             "texto": f["texto"] or ""} for f in filas]


def buscar_el_codigo_del_mensaje(codigo):
    """El botón «🔍 Buscar …» de un chat (va como on_click): lo deja buscado en el Buscador, con
    sus equivalencias, y lleva ahí."""
    cb_ver_equivalencias(codigo)
    st.session_state["pagina_actual"] = PAGINAS[0]


def marcar_leido(chat_id, leido=True):
    """Lo abrió alguien (o lo vuelve a marcar sin leer, con leido=False)."""
    exigir_nivel("empleado", "marcar un chat como leído")
    if leido:
        c.execute("""UPDATE chats SET sin_leer = 0, leido_por = ?, leido_en = datetime('now')
                     WHERE id = ? AND sin_leer > 0""", (obtener_usuario_actual(), int(chat_id)))
    else:
        c.execute("UPDATE chats SET sin_leer = MAX(sin_leer, 1) WHERE id = ?", (int(chat_id),))


def borrar_chat(chat_id):
    """Borra el chat y todos sus mensajes (un cliente que pidió que se borren sus datos, o
    publicidad). Solo el administrador. En el registro de cambios queda que se borró, de qué
    canal y cuántos mensajes tenía, nunca lo que decían. Si vuelve a escribir, es un chat nuevo.
    Devuelve cuántos mensajes se borraron."""
    exigir_nivel("admin", "borrar un chat")
    chat = el_chat(chat_id)
    if not chat:
        return 0
    with transaccion():
        cuantos = c.execute("SELECT COUNT(*) FROM chat_mensajes WHERE chat_id = ?",
                            (chat["id"],)).fetchone()[0]
        c.execute("DELETE FROM chat_mensajes WHERE chat_id = ?", (chat["id"],))
        c.execute("DELETE FROM chats WHERE id = ?", (chat["id"],))
    anotar_cambio("borró un chat", "chat", chat["id"],
                  antes={"canal": chat["canal"], "mensajes": cuantos})
    return cuantos


def fuera_de_la_ventana(chat, ahora=None):
    """Si ya pasaron las 24 horas en que Meta deja contestar (ver VENTANA_PARA_CONTESTAR)."""
    texto = str((chat or {}).get("ultimo_del_cliente_en") or "")
    try:
        ultimo = datetime.strptime(texto[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return True
    return (ahora or datetime.now()) - ultimo > VENTANA_PARA_CONTESTAR


def recordatorio_del_chat(chat):
    """(id de la cuenta, mensaje) si el que escribe por WhatsApp es una cuenta corriente con algo
    vencido; si no, None. Cuando el taller que debe escribe para preguntar otra cosa, es el
    mejor momento para recordárselo: el chat está abierto y la respuesta es gratis (ver
    «📲 Cobrar lo vencido» en logica/mecanico.py)."""
    if (chat or {}).get("canal") != "whatsapp":
        return None
    cuenta = cuenta_del_telefono(chat.get("externo"))
    if not cuenta:
        return None
    estado = estado_de_cuenta(cuenta[0])
    if (estado["vencido"] or 0) < 1:
        return None
    return cuenta[0], mensaje_de_lo_vencido(cuenta[1], estado["saldo"], estado["vencido"])


def anotar_si_le_recordamos(chat, texto):
    """Lo que se le mandó a una cuenta llevaba el recordatorio: queda anotado, como con
    «✅ Ya se lo recordé» (no hace falta tocarlo después)."""
    recordatorio = recordatorio_del_chat(chat)
    if recordatorio and recordatorio[1] in str(texto or ""):
        marcar_recordatorio(recordatorio[0])


def lo_que_sabemos_del_numero(chat):
    """Si el que escribe por WhatsApp ya está en la app: los autos con ese teléfono y lo que
    pidió y está esperando. Se compara por los últimos 8 números (11 5555-6666, 5491155556666 y
    1555556666 son el mismo). [(qué, detalle)]."""
    if (chat or {}).get("canal") != "whatsapp":
        return []
    final = re.sub(r"\D", "", str(chat.get("externo") or ""))[-8:]
    if len(final) < 8:
        return []
    salida = []
    # Si es una cuenta corriente: quién es y cuánto debe (ver telefono_de_la_cuenta()).
    cuenta = cuenta_del_telefono(final)
    if cuenta:
        estado = estado_de_cuenta(cuenta[0])
        salida.append(("💳 Cuenta", f"{cuenta[1]} — debe ${miles(estado['saldo'], 0)}"
                                   + (f" (${miles(estado['vencido'], 0)} vencido)"
                                      if estado["vencido"] else "")))
    for fila in c.execute("""SELECT patente, cliente_nombre, cliente_telefono FROM vehiculos
                             WHERE cliente_telefono IS NOT NULL AND cliente_telefono <> ''
                             ORDER BY id DESC LIMIT 5000""").fetchall():
        if re.sub(r"\D", "", str(fila["cliente_telefono"]))[-8:] == final:
            salida.append(("🚗 Auto", f"{fila['patente']}"
                                      + (f" ({fila['cliente_nombre']})" if fila["cliente_nombre"] else "")))
    for fila in c.execute("""SELECT codigo_buscado, descripcion, telefono FROM consultas_cliente
                             WHERE estado = 'activa' AND telefono IS NOT NULL AND telefono <> ''
                             ORDER BY id DESC LIMIT 5000""").fetchall():
        if re.sub(r"\D", "", str(fila["telefono"]))[-8:] == final:
            salida.append(("⏳ Esperando", str(fila["codigo_buscado"] or fila["descripcion"] or "")))
    return salida[:8]


# Lo que en un mensaje parece un código de repuesto: letras y números juntos, de 4 o más, con
# al menos un número («W712/80», «PH5949», «90915-YZZE1»), y no la plata («$15000»). Para el
# botón que lo busca. El punto que cierra la oración no es del código: «…y el W712/80.» no se
# reconocía (se vio armando el presupuesto desde el chat).
_PARECE_UN_CODIGO = re.compile(r"(?<![\w/.$-])(?=[\w/.-]*\d)[A-Za-z0-9][\w/.-]{2,}[A-Za-z0-9]"
                               r"(?![\w/-]|\.[\w/-])")


def codigos_del_mensaje(texto, tope=3):
    """Los primeros `tope` pedazos de un mensaje que parecen un código (sin fechas, horas,
    teléfonos ni plata: lo que es solo números tiene que tener letras o una barra o un guion)."""
    vistos = []
    for pedazo in _PARECE_UN_CODIGO.findall(str(texto or "")):
        solo_numeros = re.fullmatch(r"\d+", pedazo)
        if solo_numeros and (not 4 <= len(pedazo) <= 7 or 1950 <= int(pedazo) <= 2040):
            continue                    # un teléfono, un año, un número largo
        if re.fullmatch(r"\d{1,2}[/.-]\d{1,2}([/.-]\d{2,4})?", pedazo):
            continue                    # una fecha
        if pedazo.upper() not in (v.upper() for v in vistos):
            vistos.append(pedazo)
        if len(vistos) >= tope:
            break
    return vistos


# ============================================================================================
# CONTESTAR
# ============================================================================================
def contestar_chat(chat_id, texto):
    """Manda la respuesta por el canal del chat. (True, None) o (False, por qué no)."""
    exigir_nivel("empleado", "contestar un mensaje")
    texto = str(texto or "").strip()
    if not texto:
        return False, "Escribí algo para mandar."
    chat = el_chat(chat_id)
    if not chat:
        return False, "Ese chat ya no está."
    largo = LARGO_MAXIMO_POR_CANAL.get(chat["canal"], 1000)
    if len(texto) > largo:
        return False, (f"Es muy largo para {CANALES_DE_MENSAJES[chat['canal']]['nombre']}: hasta "
                       f"{miles(largo)} letras (tiene {miles(len(texto))}). Partilo en dos.")
    if fuera_de_la_ventana(chat):
        return False, TEXTO_FUERA_DE_LA_VENTANA
    cfg = config_de_los_mensajes()
    conectados = canales_conectados(cfg)
    if chat["canal"] == "whatsapp":
        if not conectados["whatsapp"]:
            return False, ("Para contestar por WhatsApp faltan «whatsapp_token» y "
                           "«whatsapp_numero_id» en los secretos.")
        datos, error = _pedir_a_meta(
            "POST", f"{cfg['whatsapp_numero_id']}/messages", cfg["whatsapp_token"],
            cuerpo={"messaging_product": "whatsapp", "recipient_type": "individual",
                    "to": chat["externo"], "type": "text",
                    "text": {"preview_url": False, "body": texto}})
        mensaje_id = (((datos or {}).get("messages") or [{}])[0] or {}).get("id")
    else:
        if not conectados[chat["canal"]]:
            return False, ("Para contestar por Facebook o Instagram faltan «meta_token» y "
                           "«meta_pagina_id» en los secretos.")
        datos, error = _pedir_a_meta(
            "POST", f"{cfg['meta_pagina_id']}/messages", cfg["meta_token"],
            cuerpo={"recipient": {"id": chat["externo"]}, "messaging_type": "RESPONSE",
                    "message": {"text": texto}})
        mensaje_id = (datos or {}).get("message_id")
    if error:
        return False, error
    cuando = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with transaccion():
        c.execute("""INSERT OR IGNORE INTO chat_mensajes (chat_id, canal, externo_id, entra, texto,
                                                          cuando, quien)
                     VALUES (?, ?, ?, 0, ?, ?, ?)""",
                  (chat["id"], chat["canal"], str(mensaje_id or f"app-{uuid.uuid4().hex}"),
                   texto, cuando, obtener_usuario_actual()))
        c.execute("""UPDATE chats SET sin_leer = 0, ultimo_texto = ?, ultimo_en = ?,
                         ultimo_entra = 0, leido_por = ?, leido_en = ?
                     WHERE id = ?""",
                  (texto[:200], cuando, obtener_usuario_actual(), cuando, chat["id"]))
    return True, None


def probar_los_canales():
    """Para Administrar: pregunta a Meta y al relevo si anda cada cosa puesta en los secretos.
    [(canal, bien, qué dijo)]: el nombre de la página o del número, nunca una clave."""
    exigir_nivel("admin", "probar la conexión de los mensajes")
    cfg = config_de_los_mensajes()
    conectados = canales_conectados(cfg)
    salida = []
    if conectados["messenger"]:
        datos, error = _pedir_a_meta("GET", cfg["meta_pagina_id"], cfg["meta_token"],
                                     params={"fields": "name,instagram_business_account{username}"})
        salida.append(("Facebook", not error,
                       error or f"Página «{str((datos or {}).get('name') or '?')[:60]}»."))
        if conectados["instagram"] and not error:
            cuenta = (datos or {}).get("instagram_business_account") or {}
            salida.append(("Instagram", bool(cuenta),
                           f"Cuenta @{str(cuenta.get('username') or '?')[:40]}." if cuenta else
                           "La página no tiene una cuenta de Instagram profesional vinculada."))
    if conectados["whatsapp"]:
        datos, error = _pedir_a_meta("GET", cfg["whatsapp_numero_id"], cfg["whatsapp_token"],
                                     params={"fields": "display_phone_number,verified_name"})
        salida.append(("WhatsApp (contestar)", not error,
                       error or f"Número {str((datos or {}).get('display_phone_number') or '?')[:30]}"
                                f" ({str((datos or {}).get('verified_name') or '')[:60]})."))
    if conectados["relevo"]:
        datos, error = _pedir_al_relevo("GET", "avisos?solo_cuantos=1", cfg)
        salida.append(("WhatsApp (recibir, el relevo)", not error,
                       error or f"Anda: tiene {miles(int((datos or {}).get('cuantos') or 0))} "
                                "aviso(s) esperando."))
    return salida


# ============================================================================================
# DEL CHAT A LA COTIZACIÓN, Y DE VUELTA
# ============================================================================================
# El cliente pregunta por el chat «¿tenés el W712/80 y el PH5949?». Antes: copiar los códigos,
# buscarlos, armar la cotización en 📋 Lista WhatsApp, abrir WhatsApp en el teléfono, buscar al
# cliente y pegarla. Ahora el chat ofrece «📋 Cotizar estos códigos» (los suma a la lista), y la
# lista y el presupuesto del Buscador ofrecen «💬 Mandárselo a …» al chat que está en curso.
def sumar_codigos_a_la_lista(lista, codigos):
    """Suma a la lista de WhatsApp lo que se encuentre de cada código (como «➕ Agregar todos a
    la lista»). Devuelve los que no están cargados, que quedan anotados como búsqueda sin
    resultado."""
    no_estan = []
    for codigo in [str(x).strip() for x in codigos if str(x).strip()]:
        limpio = codigo_para_buscar(codigo)
        resultados = []
        if limpio:
            resultados, _variantes = buscar_con_variantes_del_cero(limpio, "Todas", 3)
        if not resultados:
            no_estan.append(codigo)
            if limpio:
                registrar_busqueda_sin_resultado(codigo)
            continue
        marcar_lo_que_no_es_lo_mismo(resultados)
        lista.append({"codigo_buscado": codigo, "resultados": resultados})
    return no_estan


def cotizar_los_codigos_del_chat(codigos):
    """«📋 Cotizar estos códigos» (va como on_click): los suma a la lista de WhatsApp y lleva
    ahí. El chat sigue en curso, para mandarle la cotización de vuelta."""
    lista = st.session_state.setdefault("lista_whatsapp", [])
    ya = {str(item.get("codigo_buscado") or "").upper() for item in lista}
    no_estan = sumar_codigos_a_la_lista(lista, [x for x in codigos if str(x).upper() not in ya])
    if no_estan:
        avisar("warning", "No están cargados: " + ", ".join(no_estan[:10])
               + ". Quedaron en 📊 Estadísticas → 🔎 Búsquedas sin resultado.")
    st.session_state["pagina_actual"] = PAGINAS[5]


# LO QUE PIDE EL CHAT, SEPARADO EN PEDIDOS. «Necesito pastillas delanteras y 2 amortiguadores
# traseros para un Gol 2015 1.6, y el W712/80»: tres pedidos —las pastillas, los dos
# amortiguadores y el código— para el mismo auto. Cada uno se busca en el catálogo y el que
# atiende elige cuál va o lo descarta; con lo elegido se arma el presupuesto, que vuelve a ese
# chat. Se lee acá, con el vocabulario de piezas de la app (FAMILIAS_REPUESTO) y el buscador:
# lo que escribe el cliente no sale a ningún servicio de afuera. Lo que no se entiende no se
# inventa: queda para buscarlo a mano.
#
# CÓMO SE BUSCA CADA PIEZA: el nombre en singular más el auto (modelo, motor y año), y la pieza
# tiene que estar en la descripción. Buscando la frase entera, «pastillas delanteras gol» traía
# «Tecla alza cristales delanteras Gol» (el buscador cuenta palabras, y «delanteras» y «gol» le
# ganaban a «pastillas»; se vio con la base real). El lado —delantero, trasero— solo ordena.
# Los modelos más comunes, por si la base todavía no los tiene en sus aplicaciones (una nueva).
MODELOS_COMUNES = frozenset({
    "GOL", "TREND", "VOYAGE", "SAVEIRO", "FOX", "SURAN", "POLO", "VENTO", "BORA", "GOLF",
    "PASSAT", "AMAROK", "VIRTUS", "NIVUS", "TAOS", "CORSA", "CLASSIC", "AGILE", "ONIX", "PRISMA",
    "CELTA", "ASTRA", "VECTRA", "CRUZE", "S10", "SPIN", "TRACKER", "AVEO", "MERIVA", "ZAFIRA",
    "MONTANA", "PALIO", "SIENA", "UNO", "DUNA", "FIORINO", "PUNTO", "IDEA", "STRADA", "CRONOS",
    "ARGO", "MOBI", "TORO", "DUCATO", "WEEKEND", "FIESTA", "FOCUS", "KA", "ECOSPORT", "RANGER",
    "MONDEO", "ESCORT", "F100", "KUGA", "TRANSIT", "206", "207", "208", "307", "308", "408",
    "3008", "PARTNER", "EXPERT", "BOXER", "C3", "C4", "BERLINGO", "XSARA", "CLIO", "MEGANE",
    "KANGOO", "LOGAN", "SANDERO", "DUSTER", "SYMBOL", "TWINGO", "FLUENCE", "CAPTUR", "KWID",
    "OROCH", "TRAFIC", "MASTER", "COROLLA", "HILUX", "ETIOS", "YARIS", "SW4", "CIVIC", "FIT",
    "CITY", "SENTRA", "MARCH", "VERSA", "KICKS", "FRONTIER", "TIIDA", "R12", "R19"})
_LADOS_DEL_PEDIDO = {"DELANTER": "DELANT", "TRASER": "TRAS", "IZQUIERD": "IZQ", "DERECH": "DER"}
_MOTOR_DEL_PEDIDO = re.compile(r"(\d\.\d|\d{1,2}V|TDI|HDI|TSI|JTD|MPI|TURBO|DIESEL|GNC)")
_ANIO_DEL_PEDIDO = re.compile(r"(19[5-9]\d|20[0-4]\d)")
_SEPARA_PEDIDOS = re.compile(r"[,;\n+]|\.(?=\s|$)|\s(?:Y|E|TAMBIEN|ADEMAS|MAS)\s")
# Lo que acompaña a la pieza y no es un detalle de ella: el relleno del chat, el lado, el auto.
_NO_ES_DETALLE = PALABRAS_DE_RELLENO | {
    "BUENAS", "BUEN", "DIA", "DIAS", "TARDES", "NOCHES", "PRECIO", "PRECIOS", "SALE", "SALEN",
    "VALE", "VALEN", "COTIZACION", "PRESUPUESTO", "QUERIA", "QUISIERA", "SABER", "GRACIAS",
    "TENDRAS", "TENDRIAS", "AUTO", "COCHE", "CAMIONETA", "MODELO", "ANO", "JUEGO", "JGO", "KIT",
    "PAR", "TODO", "TODOS", "LADO", "LADOS", "MARCA", "ORIGINAL", "BUENA", "BUENO"}
# Cuántos candidatos se ofrecen por pedido, y cuántos pedidos se leen de una vez.
CANDIDATOS_POR_PEDIDO = 5
PEDIDOS_DE_UN_CHAT = 8


_MARCAS_DEL_AUTO = frozenset(MARCAS_VEHICULO)
_UNEN_PALABRAS = {"DE", "DEL", "LA", "EL", "LOS", "LAS"}


def _en_singular(palabra):
    """«AMORTIGUADORES» → «AMORTIGUADOR»: las formas de las piezas suman solo una S al plural."""
    if len(palabra) > 4 and palabra.endswith("ES") and palabra[-3] in "RLNDZ":
        return palabra[:-2]
    return palabra[:-1] if len(palabra) > 3 and palabra.endswith("S") else palabra


def auto_del_texto(texto):
    """(modelos, motor, año) que nombra el texto: ["GOL"], ["1.6"], "2015"."""
    palabras = re.findall(r"[A-Z0-9]+(?:[.][0-9]+)?", normalizar_texto(str(texto or "")).upper())
    piezas = _BUSCADOR_DE_FAMILIAS[1]
    modelos, motor, anio = [], [], ""
    for p in palabras:
        if _ANIO_DEL_PEDIDO.fullmatch(p):
            anio = anio or p
        elif _MOTOR_DEL_PEDIDO.fullmatch(p):
            motor.append(p)
        elif (p in MODELOS_COMUNES or (len(p) >= 3 and not p.isdigit() and p in MODELOS_CONOCIDOS
                                       and p not in _NO_ES_DETALLE and p not in piezas)):
            modelos.append(p)
    return list(dict.fromkeys(modelos)), list(dict.fromkeys(motor)), anio


def pedidos_del_mensaje(texto):
    """Lo que pide el texto, separado: [dict] con tipo («codigo» o «pieza»), texto (lo que se
    entendió), buscar (lo que se le pide al catálogo), nucleo (las palabras que tiene que tener
    la descripción), lados, modelos, cantidad y auto (el auto del mensaje, para decirlo)."""
    modelos, motor, anio = auto_del_texto(texto)
    del_auto = modelos + motor + ([anio] if anio else [])
    auto = " ".join(del_auto)
    del_modelo = [m for m in modelos if m not in _MARCAS_DEL_AUTO]
    pedidos = []
    for codigo in codigos_del_mensaje(texto, tope=PEDIDOS_DE_UN_CHAT):
        # «pastillas para la F100»: en un pedido, F100 es la camioneta, no un código.
        if codigo.upper() in MODELOS_COMUNES:
            continue
        pedidos.append({"tipo": "codigo", "texto": codigo, "buscar": codigo, "nucleo": [],
                        "lados": [], "modelos": [], "cantidad": 1, "auto": auto})
    patron = _BUSCADOR_DE_FAMILIAS[0]
    no_se_tocan = set(del_auto) | MODELOS_COMUNES
    base = normalizar_texto(str(texto or "")).upper()
    for pedazo in _SEPARA_PEDIDOS.split(f" {base} "):
        # En singular, menos el auto («FOCUS» no es el plural de nada).
        palabras = [p if p in no_se_tocan or p in MODELOS_CONOCIDOS else _en_singular(p)
                    for p in _normalizar_desc(pedazo).split()]
        norm = f" {' '.join(palabras)} "
        lados = [p for p in palabras if any(p.startswith(k) for k in _LADOS_DEL_PEDIDO)]
        hasta = 0
        for m in patron.finditer(norm):
            if m.start() < hasta:      # «correa de ALTERNADOR»: ya es parte de la correa
                continue
            nucleo = [p for p in m.group(1).split() if p not in _UNEN_PALABRAS]
            dicho = m.group(1).split()
            hasta = m.end()
            # Las palabras que siguen y dicen qué pieza es («filtro de ACEITE»), hasta dos.
            sigue, sumadas = norm[m.end():].split(), 0
            for k, p in enumerate(sigue):
                if p in _UNEN_PALABRAS:
                    continue
                if (sumadas == 2 or p in _NO_ES_DETALLE or p.isdigit() or p in no_se_tocan
                        or p in _MARCAS_DEL_AUTO
                        or any(p.startswith(x) for x in _LADOS_DEL_PEDIDO)):
                    break
                nucleo.append(p)
                dicho.append(p)
                sumadas += 1
                hasta = m.end() + len(" ".join(sigue[:k + 1])) + 1
            cantidad = re.search(r"(?:^| )(\d{1,2}) $", norm[:m.start()])
            cantidad = int(cantidad.group(1)) if cantidad else 1
            pedidos.append({
                "tipo": "pieza", "texto": " ".join(dict.fromkeys(dicho + lados)).lower(),
                "buscar": " ".join(nucleo + del_auto), "nucleo": nucleo,
                "lados": [_LADOS_DEL_PEDIDO[k] for k in _LADOS_DEL_PEDIDO
                          if any(l.startswith(k) for l in lados)],
                "modelos": del_modelo, "auto": auto,
                "cantidad": min(cantidad, CANTIDAD_MAXIMA_POR_PEDIDO) if 1 <= cantidad <= 20 else 1})
    # El mismo pedido dos veces («las pastillas … sí, las pastillas»), una sola.
    unicos = list({p["buscar"]: p for p in pedidos}.values())
    return unicos[:PEDIDOS_DE_UN_CHAT]


def candidatos_del_pedido(pedido):
    """Lo que hay en el catálogo para un pedido: [dict] con ID, Marca, Codigo, Descripcion,
    Precio y Stock. Tienen que ser de la pieza pedida; primero los que nombran el auto, después
    los del lado pedido y lo que hay en stock (entre iguales, el orden del buscador)."""
    if pedido["tipo"] == "codigo":
        limpio = codigo_para_buscar(pedido["buscar"])
        filas = buscar_con_variantes_del_cero(limpio, "Todas", 3)[0] if limpio else []
    else:
        def orden(fila):
            desc = _normalizar_desc(fila.get("Descripcion"))
            return (not any(f" {m} " in desc for m in pedido["modelos"]),
                    -sum(l in desc for l in pedido["lados"]),
                    not (fila.get("Stock") or 0) > 0)
        filas = sorted((f for f in buscar_por_texto(pedido["buscar"])
                        if all(f" {n}" in _normalizar_desc(f.get("Descripcion"))
                               for n in pedido["nucleo"])), key=orden)
    # «para_el_auto»: si nombra el auto del mensaje. El que no lo nombra se ofrece igual (muchas
    # descripciones no dicen el auto), pero marcado, y no viene elegido.
    return [dict({k: f.get(k) for k in ("ID", "Marca", "Codigo", "Descripcion", "Precio", "Stock")},
                 para_el_auto=not pedido["modelos"] or any(
                     f" {m} " in _normalizar_desc(f.get("Descripcion")) for m in pedido["modelos"]))
            for f in filas if f.get("ID")][:CANDIDATOS_POR_PEDIDO]


def lo_que_pidio_el_cliente(chat_id):
    """Lo último que escribió el cliente: sus mensajes desde la última respuesta nuestra (si
    se le contestó último, los tres anteriores)."""
    mensajes = mensajes_del_chat(chat_id)
    ultimos = []
    for m in reversed(mensajes):
        if not m["entra"]:
            break
        ultimos.append(m["texto"] or "")
    if not ultimos:
        ultimos = [m["texto"] or "" for m in reversed(mensajes) if m["entra"]][:3]
    return "\n".join(reversed(ultimos))


def pedidos_y_candidatos(texto):
    """[(pedido, candidatos)] de `texto`, recordado mientras no cambie lo escrito ni el
    catálogo: se dibuja en cada toque de la pantalla."""
    return recordado_mientras_no_cambie(
        "_pedidos_y_candidatos", (texto, testigo_de_los_vinculos()),
        lambda: [(p, candidatos_del_pedido(p)) for p in pedidos_del_mensaje(texto)], cuantos=6)


# Lo que se elige para un pedido que no va.
DESCARTAR_EL_PEDIDO = "descartar"


def buscar_el_pedido_a_mano(tipo, texto):
    """«🔍 Buscarlo a mano» de un pedido que no se encontró (va como on_click): el código, con
    sus equivalencias; la pieza, por descripción. Ya buscado en el 🔍 Buscador."""
    if tipo == "codigo":
        buscar_el_codigo_del_mensaje(texto)
        return
    st.session_state["_pasar_a_descripcion"] = str(texto).lower()
    st.session_state["_sin_aviso_de_codigo"] = True
    st.session_state["pagina_actual"] = PAGINAS[0]


def mensaje_de_lo_que_no_hay(lo_que_falta):
    """«De lo que me pediste, ahora no tengo bomba de nafta y W712/80. ¿Querés que te lo
    consiga?»: para contestarle de un toque lo que no se encontró."""
    falta = [str(x) for x in lo_que_falta if str(x).strip()]
    if not falta:
        return ""
    lista = ", ".join(falta[:-1]) + (" y " if len(falta) > 1 else "") + falta[-1]
    return f"De lo que me pediste, ahora no tengo {lista}. ¿Querés que te lo consiga?"


def sumar_a_la_respuesta(clave, texto):
    """(Va como on_click.) Suma `texto` a lo escrito en la caja `clave`, después de lo que hay
    y una sola vez: «💳 Recordarle lo vencido», «✍️ Decirle lo que no hay»."""
    antes = str(st.session_state.get(clave) or "").rstrip()
    if texto and texto not in antes:
        st.session_state[clave] = f"{antes}\n\n{texto}".strip()


def armar_el_presupuesto_con_lo_pedido(chat_id, elegidos):
    """«🛒 Armar el presupuesto» (va como on_click): lo elegido de cada pedido va al presupuesto
    del 🔍 Buscador, con su cantidad. Desde un chat (`chat_id`), el chat queda en curso (para
    «💬 Mandárselo») y el cliente y su WhatsApp, listos para «📌 Guardar para seguirlo».

    `elegidos`: [(producto, cantidad)], cada uno el valor o la clave del campo que lo tiene. Con
    las claves se lee lo que quedó elegido al tocar: los args de un botón se arman en la pasada
    anterior."""
    chat = el_chat(chat_id) if chat_id else None
    if chat_id and not chat:
        return

    def valor(x):
        return st.session_state.get(x) if isinstance(x, str) else x
    sumados = 0
    for producto, cantidad in elegidos:
        producto, cantidad = valor(producto), valor(cantidad)
        if producto in (None, DESCARTAR_EL_PEDIDO):
            continue
        fila = c.execute("""SELECT p.id AS "ID", p.codigo_raw AS "Codigo", m.nombre AS "Marca",
                                   p.descripcion AS "Descripcion", p.precio AS "Precio"
                            FROM productos p JOIN marcas m ON m.id = p.marca_id
                            WHERE p.id = ?""", (int(producto),)).fetchone()
        if fila:
            sumar_al_presupuesto(dict(fila), max(1, int(cantidad or 1)))
            sumados += 1
    if not sumados:
        avisar("info", "No quedó nada elegido: todos los pedidos están descartados.")
        return
    st.session_state["exp_presupuesto_armado_item_s"] = True
    st.session_state["pagina_actual"] = PAGINAS[0]
    if not chat:
        avisar("success", f"🛒 {sumados} al presupuesto. Revisalo abajo.")
        return
    st.session_state["msj_chat_abierto"] = chat_id
    st.session_state["msj_chat_abierto_en"] = time.monotonic()
    st.session_state["presu_seguir_cliente"] = nombre_del_chat(chat)
    st.session_state["presu_seguir_tel"] = (str(chat["externo"]) if chat["canal"] == "whatsapp"
                                            else "")
    avisar("success", f"🛒 {sumados} al presupuesto, de lo que pidió {nombre_del_chat(chat)}. "
                      "Revisalo y «💬 Mandárselo».")


def mostrar_los_pedidos(texto, base, chat_id=None):
    """El panel de «🧩 Armar el presupuesto con lo que pide»: cada pedido de `texto` con lo que
    hay para elegir o descartar, y «🛒 Armar el presupuesto con lo elegido». `base` va en las
    claves; con `chat_id` (💬 Mensajes) lo que no hay se le contesta en ese chat, y sin él
    (pegado en el 🔍 Buscador) queda escrito para copiarlo."""
    _leido, _pedidos = texto, pedidos_y_candidatos(texto)
    if not _pedidos:
        st.caption("No encontré ninguna pieza ni ningún código en lo escrito.")
        return
    _autos = {p["auto"] for p, _ in _pedidos if p["auto"]}
    st.caption(("Lo que entendí de lo último que escribió" if chat_id else
                "Lo que entendí del pedido")
               + (f", para **{texto_para_markdown(' / '.join(sorted(_autos)))}**" if _autos
                  else "") + ". Elegí cuál va o descartalo.")
    # Las claves llevan la huella de lo leído: si escribe otra cosa, son pedidos nuevos y
    # no se quedan con lo elegido para los de antes.
    _huella = hashlib.md5(_leido.encode("utf-8")).hexdigest()[:8]
    _elegidos, _no_hay = [], []
    for _n, (_ped, _cands) in enumerate(_pedidos):
        _clave = f"{base}_{_huella}_{_n}"
        # Sin negritas: el rótulo es también lo que lee el lector de pantalla, y ahí las
        # «**» quedaban escritas.
        _titulo = (f"{_n + 1}. {texto_para_markdown(_ped['texto'])}"
                   + (" (código)" if _ped["tipo"] == "codigo" else ""))
        if not _cands:
            _col_que, _col_boton = st.columns([5, 2], vertical_alignment="center")
            _col_que.markdown(f"**{_titulo}** — no lo encontré en el catálogo"
                              + (" con esas palabras." if _ped["tipo"] == "pieza" else "."))
            _col_boton.button("🔍 Buscarlo a mano", key=f"a_mano_{_clave}",
                              on_click=buscar_el_pedido_a_mano,
                              args=(_ped["tipo"], _ped["buscar"]), width="stretch",
                              help="Lo deja buscado en el 🔍 Buscador, para mirarlo vos.")
            _no_hay.append(_ped["texto"])
            continue
        _por_id = {x["ID"]: x for x in _cands}
        _primero = _cands[0]
        _col_que, _col_cant = st.columns([5, 1], vertical_alignment="bottom")
        _opciones = list(_por_id) + [DESCARTAR_EL_PEDIDO]
        _col_que.selectbox(
            _titulo, _opciones, key=_clave, index=0 if _primero["para_el_auto"] else
            len(_opciones) - 1,
            # rótulo fijo: marca, código y descripción no cambian mientras se elige.
            format_func=lambda x, d=_por_id: "🗑️ Descartar este pedido"
            if x == DESCARTAR_EL_PEDIDO else (
                ("⚠️ " if not d[x]["para_el_auto"] else "")
                + f"{d[x]['Marca']} {d[x]['Codigo']} — "
                  f"{str(d[x]['Descripcion'] or '')[:70]}"))
        _col_cant.number_input("Cant.", 1, CANTIDAD_MAXIMA_POR_PEDIDO, _ped["cantidad"],
                               key=f"{_clave}_cant")
        _elegido = _por_id.get(st.session_state.get(_clave))
        if _elegido:
            st.caption(("⚠️ La descripción no dice que sea para ese auto: fijate antes de "
                        "ofrecerlo. · " if not _elegido["para_el_auto"] else "")
                       + (f"\\${miles(_elegido['Precio'])}" if _elegido["Precio"]
                          else "sin precio")
                       + (f" · stock {miles(_elegido['Stock'])}"
                          if _elegido["Stock"] is not None else ""))
        _elegidos.append((_clave, f"{_clave}_cant"))
    # Lo que no hay, contestado de un toque: a la caja de la respuesta (o a la de WhatsApp,
    # pasadas las 24 horas), sin borrar lo escrito. Pegado en el Buscador, para copiarlo.
    _chat_ped = el_chat(chat_id) if chat_id else None
    _caja_ped = None
    if _chat_ped:
        _caja_ped = ((f"msj_fuera_{chat_id}" if _chat_ped["canal"] == "whatsapp"
                      and str(_chat_ped["externo"]).isdigit() else None)
                     if fuera_de_la_ventana(_chat_ped) else f"msj_respuesta_{chat_id}")
    elif _no_hay:
        st.caption("Lo que no hay, para copiarlo y contestarle:")
        st.code(mensaje_de_lo_que_no_hay(_no_hay), language=None, wrap_lines=True)
    if _no_hay and _caja_ped:
        st.button("✍️ Decirle lo que no hay", key=f"msj_no_hay_{chat_id}",
                  on_click=sumar_a_la_respuesta,
                  args=(_caja_ped, mensaje_de_lo_que_no_hay(_no_hay)),
                  help="Le escribe en la respuesta lo que no se encontró, y si querés "
                       "que se lo consigas. Lo mandás vos.")
    if _elegidos:
        st.button("🛒 Armar el presupuesto con lo elegido", key=f"armar_{base}",
                  type="primary", width="stretch", on_click=armar_el_presupuesto_con_lo_pedido,
                  args=(chat_id, _elegidos),
                  help="Lo suma al presupuesto del 🔍 Buscador, con las cantidades"
                       + (", y el nombre y el WhatsApp del cliente listos para guardarlo; "
                          "desde ahí «💬 Mandárselo»." if chat_id else "."))


def pasar_al_pedido_pegado(texto):
    """«🧩 Son varias cosas: separarlas» del Buscador (va como on_click): lo buscado va a
    «🧩 Pegar el pedido de un cliente», abierto."""
    st.session_state["pedido_pegado"] = str(texto or "")
    st.session_state["exp_pedido_pegado"] = True


def chat_para_mandar():
    """El chat abierto en «💬 Mensajes», si ahora se le puede mandar algo: abierto hace menos
    de MINUTOS_QUE_QUEDA_EN_CURSO_UN_CHAT, dentro de las 24 horas de Meta y con su canal
    conectado para contestar. Si no, None."""
    chat_id = st.session_state.get("msj_chat_abierto")
    desde = st.session_state.get("msj_chat_abierto_en")
    if not chat_id or desde is None or not es_operador_o_admin():
        return None
    if time.monotonic() - desde > MINUTOS_QUE_QUEDA_EN_CURSO_UN_CHAT * 60:
        return None
    try:
        chat = el_chat(chat_id)
    except sqlite3.Error as _err:
        anotar_error("chat_para_mandar", _err)
        return None
    if not chat or fuera_de_la_ventana(chat):
        return None
    conectados = canales_conectados()
    return chat if conectados.get(chat["canal"]) else None


def mandar_al_chat(chat_id, texto):
    """«💬 Mandárselo a …» (va como on_click): lo manda y, si salió, vuelve al chat para verlo
    ahí; si no, dice por qué y se queda donde estaba."""
    try:
        ok, error = contestar_chat(chat_id, texto)
    except PermissionError as _err:
        ok, error = False, el_error_en_castellano(_err)
    if ok:
        avisar("success", "💬 Enviado: quedó en el chat.")
        st.session_state["msj_chat_abierto_en"] = time.monotonic()
        st.session_state["pagina_actual"] = PAGINAS[12]
    else:
        avisar("error", f"No se mandó: {error}")


def mostrar_boton_para_el_chat(texto, clave):
    """Si hay un chat en curso (ver chat_para_mandar()), el botón para mandarle `texto`."""
    chat = chat_para_mandar()
    if not chat:
        return
    canal = CANALES_DE_MENSAJES[chat["canal"]]["nombre"]
    largo = LARGO_MAXIMO_POR_CANAL.get(chat["canal"], 1000)
    nombre = nombre_del_chat(chat)
    nombre = nombre[:30] + ("…" if len(nombre) > 30 else "")
    demasiado = len(str(texto or "")) > largo
    st.button(f"💬 Mandárselo a {texto_de_chat_para_markdown(nombre)} por {canal}", key=clave,
              type="primary", width="stretch", disabled=demasiado,
              on_click=mandar_al_chat, args=(chat["id"], str(texto or "")),
              help=(f"Es muy largo para {canal}: tiene {miles(len(str(texto or '')))} letras y "
                    f"entran {miles(largo)}. Sacá algo, o mandá el PDF desde el teléfono."
                    if demasiado else "Lo manda al chat que abriste en 💬 Mensajes, y vuelve ahí."))

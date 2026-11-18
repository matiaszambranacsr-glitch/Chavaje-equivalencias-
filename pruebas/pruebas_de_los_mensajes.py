"""Pruebas de «💬 Mensajes»: WhatsApp, Facebook e Instagram en una bandeja (ver
logica/mensajes.py y pantallas/mensajes.py), y del relevo de WhatsApp
(integraciones/relevo_de_mensajes/worker.js, con Node si está).

Uso:
    python3 pruebas/pruebas_de_los_mensajes.py

Meta y el relevo son de mentira (se reemplaza `requests` en el espacio de nombres de la
lógica): nada sale a internet, y las claves son inventadas para la prueba. Lo que se controla:
  · leer los avisos de Meta (WhatsApp, la página, Instagram, los ecos, lo que no es texto);
  · traer lo nuevo: lo de antes de conectar entra como leído, el mismo mensaje entra una sola
    vez, y al relevo se le confirma recién después de guardar;
  · contestar: por el canal del chat, con el permiso en la cabecera, y nunca pasadas las 24 h;
  · las claves no aparecen en ningún error, ni en la pantalla, ni en los errores anotados;
  · quién ve la sección (el personal sí; el invitado, el taller y el depósito no), la cuenta
    de sin leer en la barra, el cartel que salta, abrir un chat, contestar y buscar un código;
  · el relevo: la firma de Meta, la clave de la app y lo que guarda.

Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Inventadas para la prueba: lo que se controla es que NO aparezcan en ningún lado.
CLAVES = {"meta_token": "TOKEN-META-SECRETO-123", "meta_pagina_id": "PAG1",
          "whatsapp_token": "TOKEN-WA-SECRETO-456", "whatsapp_numero_id": "NUM1",
          "relevo_url": "https://relevo.example", "relevo_clave": "CLAVE-RELEVO-789"}
SECRETAS = ("SECRETO-123", "SECRETO-456", "RELEVO-789")


def _entrar(at, usuario, clave):
    at.text_input(key="login_inicial_nombre").set_value(usuario)
    at.text_input(key="login_inicial_clave").set_value(clave)
    [b for b in at.button if "Ingresar con contraseña" in b.label][0].click().run()


class _Respuesta:
    def __init__(self, estado, datos):
        self.status_code = estado
        self._datos = datos
        self.content = json.dumps(datos).encode()

    def json(self):
        return self._datos


class MetaDeMentira:
    """Hace de Meta y del relevo. Anota cada pedido; `conversaciones`, `avisos` y `falla` se
    cambian desde la prueba."""

    def __init__(self):
        self.pedidos = []
        self.conversaciones = {"messenger": [], "instagram": []}
        self.avisos = []
        self.confirmados = []
        self.falla = None            # (estado, {"error": …}) o una excepción

    def request(self, metodo, url, params=None, json=None, timeout=None, headers=None):
        self.pedidos.append({"metodo": metodo, "url": url, "params": params or {},
                             "json": json, "headers": headers or {}})
        if isinstance(self.falla, Exception):
            raise self.falla
        if self.falla:
            return _Respuesta(*self.falla)
        if url.startswith("https://relevo.example/avisos"):
            if "solo_cuantos" in url:
                return _Respuesta(200, {"cuantos": len(self.avisos)})
            return _Respuesta(200, {"avisos": list(self.avisos)})
        if url == "https://relevo.example/confirmar":
            self.confirmados += json["ids"]
            self.avisos = [a for a in self.avisos if a["id"] not in json["ids"]]
            return _Respuesta(200, {"borrados": len(json["ids"])})
        if url.endswith("/PAG1/conversations"):
            return _Respuesta(200, {"data": self.conversaciones[params["platform"]]})
        if url.endswith("/PAG1") and metodo == "GET":
            return _Respuesta(200, {"id": "PAG1", "name": "Repuestos de Prueba",
                                    "instagram_business_account": {"id": "IG9",
                                                                   "username": "repuestos"}})
        if url.endswith("/NUM1/messages"):
            return _Respuesta(200, {"messages": [{"id": f"wamid.SALE{len(self.pedidos)}"}]})
        if url.endswith("/NUM1"):
            return _Respuesta(200, {"display_phone_number": "+54 9 11 5555-0000",
                                    "verified_name": "Repuestos de Prueba"})
        if url.endswith("/PAG1/messages"):
            return _Respuesta(200, {"recipient_id": json["recipient"]["id"],
                                    "message_id": f"m_SALE{len(self.pedidos)}"})
        return _Respuesta(404, {"error": {"code": 803}})

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)


def _aviso_de_whatsapp(mensajes, nombre="Juan Pérez", numero="5491155556666"):
    return {"object": "whatsapp_business_account", "entry": [{"id": "WABA", "changes": [{
        "field": "messages", "value": {
            "messaging_product": "whatsapp", "metadata": {"phone_number_id": "NUM1"},
            "contacts": [{"wa_id": numero, "profile": {"name": nombre}}],
            "messages": mensajes}}]}]}


def _hace(minutos):
    return int((datetime.now() - timedelta(minutes=minutos)).timestamp())


def probar():
    from streamlit.testing.v1 import AppTest
    fallas = []

    def esperar(nombre, real, esperado):
        if real != esperado:
            fallas.append(f"{nombre}: dio {real!r}, se esperaba {esperado!r}")

    def cierto(nombre, condicion, detalle=""):
        if not condicion:
            fallas.append(f"{nombre}" + (f" ({str(detalle)[:300]})" if detalle else ""))

    at = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
    at.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
    at.secrets["mensajes"] = dict(CLAVES)
    at.run()
    ns = sys.modules["logica"].todo_lo_de_la_logica()
    meta = MetaDeMentira()
    # Lo que la lógica ve como `requests` y como los secretos: AppTest pone los secretos solo
    # mientras corre la app, y acá también se llama a la lógica desde afuera.
    _g = ns["config_de_los_mensajes"].__globals__
    requests_de_verdad, secretos_de_verdad = _g["requests"], _g["secretos_app"]
    _g["requests"] = meta
    _g["secretos_app"] = lambda: {"admin_passwords": {"duenio": "clave-duenio-1"},
                                  "mensajes": dict(CLAVES)}
    c = ns["c"]
    try:
        # 1. LEER LOS AVISOS DE META.
        leidos = ns["mensajes_del_aviso"](json.dumps(_aviso_de_whatsapp([
            {"from": "5491155556666", "id": "wamid.A", "timestamp": str(_hace(5)),
             "type": "text", "text": {"body": "¿Tenés el W712/80?"}},
            {"from": "5491155556666", "id": "wamid.B", "timestamp": str(_hace(4)),
             "type": "image", "image": {"caption": "este"}},
            {"from": "5491155556666", "id": "wamid.C", "timestamp": str(_hace(3)),
             "type": "audio", "audio": {}}])))
        esperar("WhatsApp: tres mensajes, con el nombre y lo que no es texto dicho",
                [(m["canal"], m["chat"], m["nombre"], m["texto"], m["entra"]) for m in leidos],
                [("whatsapp", "5491155556666", "Juan Pérez", "¿Tenés el W712/80?", True),
                 ("whatsapp", "5491155556666", "Juan Pérez", "📷 Foto: este", True),
                 ("whatsapp", "5491155556666", "Juan Pérez", "🎤 Audio (miralo en el teléfono).",
                  True)])
        _pagina = ns["mensajes_del_aviso"]({"object": "page", "entry": [{"id": "PAG1", "messaging": [
            {"sender": {"id": "PSID7"}, "recipient": {"id": "PAG1"}, "timestamp": _hace(2) * 1000,
             "message": {"mid": "m_X", "text": "hola"}},
            {"sender": {"id": "PAG1"}, "recipient": {"id": "PSID7"}, "timestamp": _hace(1) * 1000,
             "message": {"mid": "m_Y", "text": "¿qué necesitás?", "is_echo": True}},
            {"sender": {"id": "PSID7"}, "recipient": {"id": "PAG1"}, "timestamp": _hace(1) * 1000,
             "read": {"watermark": 1}}]}]})
        esperar("la página: el del cliente entra, el eco es nuestro, «leído» no es un mensaje",
                [(m["canal"], m["chat"], m["entra"]) for m in _pagina],
                [("messenger", "PSID7", True), ("messenger", "PSID7", False)])
        esperar("un aviso que no se entiende no rompe nada",
                [ns["mensajes_del_aviso"](x) for x in ("{no es json", None, 7, {"entry": 5},
                                                       {"object": "page", "entry": [None]})],
                [[], [], [], [], []])
        esperar("la hora de Meta, en UTC como guarda la app",
                (ns["_momento_utc"]("2026-11-18T14:03:12+0000"),
                 ns["_momento_utc"]("2026-11-18T11:03:12-03:00")),
                ("2026-11-18 14:03:12", "2026-11-18 14:03:12"))

        # 2. TRAER LO NUEVO. La primera vez, lo de antes de conectar entra como leído.
        meta.conversaciones["messenger"] = [{"id": "t_1", "participants": {"data": [
            {"id": "PAG1", "name": "Repuestos"}, {"id": "PSID7", "name": "María *Gómez*"}]},
            "messages": {"data": [
                {"id": "m_viejo", "message": "¿abren el sábado?", "from": {"id": "PSID7"},
                 "created_time": (datetime.now() - timedelta(days=3)).strftime(
                     "%Y-%m-%dT%H:%M:%S+0000")}]}}]
        meta.avisos = [{"id": "m:1", "cuerpo": json.dumps(_aviso_de_whatsapp([
            {"from": "5491155556666", "id": "wamid.A", "timestamp": str(_hace(5)),
             "type": "text", "text": {"body": "¿Tenés el W712/80?"}}]))}]
        resultado = ns["traer_mensajes_nuevos"]()
        esperar("la primera vuelta trae de los tres lados sin errores",
                {k: v[1] for k, v in resultado.items()},
                {"messenger": None, "instagram": None, "relevo": None})
        esperar("lo de antes de conectar, como leído", ns["cuantos_chats_sin_leer"](), 0)
        esperar("al relevo se le confirma lo guardado", meta.confirmados, ["m:1"])
        # Lo que llega después sí salta. Y el mismo mensaje dos veces entra una vez.
        _nuevo = {"id": "m:2", "cuerpo": json.dumps(_aviso_de_whatsapp([
            {"from": "5491155556666", "id": "wamid.D", "timestamp": str(_hace(1)),
             "type": "text", "text": {"body": "¿y el PH5949? $15000, modelo 2015, 12/10"}}]))}
        meta.avisos = [_nuevo, dict(_nuevo, id="m:3"),
                       {"id": "m:4", "cuerpo": json.dumps(_aviso_de_whatsapp([
                           {"from": "5493415550000", "id": "wamid.E", "timestamp": str(_hace(1)),
                            "type": "text", "text": {"body": "hola"}}],
                           nombre="Pedro [link](http://x.example)", numero="5493415550000"))}]
        meta.conversaciones["messenger"][0]["messages"]["data"].append(
            {"id": "m_nuevo", "message": "¿tienen pastillas?", "from": {"id": "PSID7"},
             "created_time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+0000")})
        resultado = ns["traer_mensajes_nuevos"]()
        esperar("la segunda vuelta: 1 de Facebook y 2 de WhatsApp (el repetido, una vez)",
                {k: v[0] for k, v in resultado.items()},
                {"messenger": 1, "instagram": 0, "relevo": 2})
        esperar("tres chats sin leer", ns["cuantos_chats_sin_leer"](), 3)
        esperar("el relevo quedó vacío", meta.avisos, [])
        esperar("y lo que ya estaba no vuelve a entrar",
                {k: v[0] for k, v in ns["traer_mensajes_nuevos"]().items()},
                {"messenger": 0, "instagram": 0, "relevo": 0})
        _juan = c.execute("SELECT * FROM chats WHERE externo = '5491155556666'").fetchone()
        esperar("el chat de Juan: su nombre, lo último y un sin leer",
                (_juan["nombre"], _juan["sin_leer"], _juan["ultimo_entra"]),
                ("Juan Pérez", 1, 1))
        # El eco de algo contestado desde el teléfono: el chat queda atendido.
        _maria = c.execute("SELECT id FROM chats WHERE externo = 'PSID7'").fetchone()[0]
        ns["guardar_mensaje_de_afuera"]({"canal": "messenger", "chat": "PSID7", "id": "m_eco",
                                         "texto": "sí, tenemos", "entra": False,
                                         "cuando": ns["_momento_utc"](None)})
        esperar("contestado desde el teléfono, el chat deja de estar sin leer",
                c.execute("SELECT sin_leer, ultimo_entra FROM chats WHERE id = ?",
                          (_maria,)).fetchone()[:], (0, 0))

        # 3. CONTESTAR.
        meta.pedidos.clear()
        esperar("contestar a Juan por WhatsApp", ns["contestar_chat"](_juan["id"], "Sí, tenemos"),
                (True, None))
        _p = meta.pedidos[-1]
        esperar("va al número del negocio, al de Juan, con el permiso en la cabecera",
                (_p["metodo"], _p["url"], _p["json"]["to"], _p["json"]["text"]["body"],
                 _p["headers"].get("Authorization")),
                ("POST", "https://graph.facebook.com/v26.0/NUM1/messages", "5491155556666",
                 "Sí, tenemos", "Bearer TOKEN-WA-SECRETO-456"))
        cierto("el permiso nunca va en la dirección ni en lo que se manda",
               not any(s in json.dumps([p["url"], p["params"], p["json"]]) for p in meta.pedidos
                       for s in SECRETAS))
        esperar("lo mandado queda en el chat, como nuestro, y el chat atendido",
                c.execute("SELECT sin_leer, ultimo_entra, ultimo_texto FROM chats WHERE id = ?",
                          (_juan["id"],)).fetchone()[:], (0, 0, "Sí, tenemos"))
        esperar("contestar a María por Facebook va a la página, con RESPONSE",
                (ns["contestar_chat"](_maria, "Te espero"), meta.pedidos[-1]["url"],
                 meta.pedidos[-1]["json"]["messaging_type"],
                 meta.pedidos[-1]["json"]["recipient"]["id"]),
                ((True, None), "https://graph.facebook.com/v26.0/PAG1/messages", "RESPONSE",
                 "PSID7"))
        esperar("vacío o larguísimo no se manda",
                (ns["contestar_chat"](_juan["id"], "   ")[0],
                 ns["contestar_chat"](_juan["id"], "x" * 2001)[0]), (False, False))
        # Pasadas las 24 horas: ni se intenta.
        c.execute("UPDATE chats SET ultimo_del_cliente_en = datetime('now', '-25 hours') "
                  "WHERE id = ?", (_maria,))
        _antes = len(meta.pedidos)
        _r = ns["contestar_chat"](_maria, "hola")
        esperar("pasadas las 24 horas no se manda, y ni se le pregunta a Meta",
                (_r[0], "24 horas" in str(_r[1]), len(meta.pedidos)), (False, True, _antes))
        # Meta que lo rechaza: en castellano, con el número, sin su texto ni el permiso.
        meta.falla = (400, {"error": {"code": 190, "message":
                                      "Invalid OAuth token TOKEN-WA-SECRETO-456 for /NUM1"}})
        _r = ns["contestar_chat"](_juan["id"], "otra")
        cierto("el permiso vencido se dice en castellano, con el código y sin el texto de Meta",
               _r[0] is False and "código 190" in _r[1] and "venció" in _r[1]
               and not any(s in _r[1] for s in SECRETAS) and "Invalid" not in _r[1], _r)
        meta.falla = (400, {"error": {"code": 10, "error_subcode": 2018278}})
        _r = ns["contestar_chat"](_juan["id"], "otra")
        cierto("la ventana de 24 h que dice Meta se reconoce por el subcódigo",
               "24 horas" in _r[1] and "2018278" in _r[1], _r)
        meta.falla = ConnectionError("HTTPSConnectionPool(host='graph.facebook.com'): "
                                     "url /v26.0/NUM1/messages?access_token=TOKEN-WA-SECRETO-456")
        _r = ns["contestar_chat"](_juan["id"], "otra")
        cierto("sin internet: se dice, sin la dirección ni el permiso",
               _r[0] is False and "://" not in _r[1] and "access_token" not in _r[1]
               and not any(s in _r[1] for s in SECRETAS), _r)
        meta.falla = None
        _anotados = json.dumps(list(ns["_ULTIMOS_ERRORES"]), ensure_ascii=False)
        cierto("los errores anotados tampoco llevan los permisos",
               not any(s in _anotados for s in SECRETAS), _anotados[-400:])

        # 4. QUIÉN PUEDE: contestar y marcar es del personal (la segunda barrera, por si otro
        # camino llamara a la función).
        _g = ns["contestar_chat"].__globals__
        _adentro = _g["_nivel_de_quien_esta_adentro"]
        try:
            for _nivel in ("", "mecanico"):
                _g["_nivel_de_quien_esta_adentro"] = lambda n=_nivel: n
                for _nombre, _llamar in (("contestar", lambda: ns["contestar_chat"](_juan["id"], "x")),
                                         ("marcar leído", lambda: ns["marcar_leido"](_juan["id"])),
                                         ("traer ahora", lambda: ns["traer_mensajes_ahora"]())):
                    try:
                        _llamar()
                        fallas.append(f"«{_nivel or 'invitado'}» pudo {_nombre}")
                    except PermissionError:
                        pass
        finally:
            _g["_nivel_de_quien_esta_adentro"] = _adentro

        # 5. LO QUE AYUDA A CONTESTAR.
        esperar("los códigos de un mensaje: sin plata, años, fechas ni teléfonos",
                ns["codigos_del_mensaje"]("¿tenés el W712/80 y el PH5949? $15000, modelo 2015, "
                                          "cel 1155556666, el 12/10. También 90915-YZZE1"),
                ["W712/80", "PH5949", "90915-YZZE1"])
        c.execute("INSERT INTO vehiculos (patente, cliente_nombre, cliente_telefono) "
                  "VALUES ('AB123CD', 'Juan', '11 5555-6666')")
        esperar("el que escribe por WhatsApp y ya tiene un auto anotado",
                ns["lo_que_sabemos_del_numero"](dict(_juan)), [("🚗 Auto", "AB123CD (Juan)")])
        esperar("las 24 horas", (ns["fuera_de_la_ventana"]({"ultimo_del_cliente_en": ns["_momento_utc"](None)}),
                                 ns["fuera_de_la_ventana"]({"ultimo_del_cliente_en": "2020-01-01 10:00:00"}),
                                 ns["fuera_de_la_ventana"]({})), (False, True, True))
        esperar("el texto del cliente, sin formato, enlaces ni fórmulas",
                ns["texto_de_chat_para_markdown"]("**a** ![x](http://y.example/p.png) $1 y $2\nfin"),
                "\\*\\*a\\*\\* !\\[x\\](http://y.example/p.png) \\$1 y \\$2  \nfin")

        # 6. LA VUELTA DE FONDO: sola, una por vez, y no más de una por minuto.
        _sin_fondo = os.environ.pop("EQUIVALENCIAS_SIN_TAREAS_DE_FONDO", None)
        try:
            ns["_BANDEJA"]["ultima"] = None        # ninguna todavía
            _primera = ns["arrancar_la_bandeja_de_fondo"]()
            _segunda = ns["arrancar_la_bandeja_de_fondo"]()
            ns["_BANDEJA"]["candado"].acquire(timeout=20)
            ns["_BANDEJA"]["candado"].release()
            esperar("la vuelta de fondo arranca una vez y la segunda espera su minuto",
                    (_primera, _segunda), (True, False))
        finally:
            if _sin_fondo is not None:
                os.environ["EQUIVALENCIAS_SIN_TAREAS_DE_FONDO"] = _sin_fondo

        # 7. LA PANTALLA. El invitado no la ve.
        at.run()
        esperar("el invitado no tiene «💬 Mensajes» en la barra",
                any("Mensajes" in o for o in at.radio(key="pagina_actual").options), False)
        ns["crear_usuario"]("ana", "clave-ana-1", "operador")
        _entrar(at, "ana", "clave-ana-1")
        c.execute("UPDATE chats SET sin_leer = 2 WHERE externo = '5493415550000'")
        at.run()
        esperar("al personal le dice cuántos sin leer, en la pastilla",
                [o for o in at.radio(key="pagina_actual").options if "Mensajes" in o],
                ["💬 Mensajes · 1"])
        # Llega uno nuevo mientras está en otra pantalla: salta el cartel.
        ns["guardar_mensaje_de_afuera"]({"canal": "whatsapp", "chat": "5491155556666",
                                         "nombre": "Juan Pérez", "id": "wamid.NUEVO",
                                         "texto": "**urgente** [ver](http://x.example)",
                                         "entra": True, "cuando": ns["_momento_utc"](None)})
        at.run()
        _carteles = [t.value for t in at.toast]
        cierto("salta un cartel con el nombre y lo que escribió, escapado",
               any("Juan Pérez" in t and "\\*\\*urgente\\*\\*" in t and "\\[ver\\]" in t
                   for t in _carteles), _carteles)
        at.run()
        cierto("el cartel salta una sola vez", not any("urgente" in t.value for t in at.toast))
        at.session_state["pagina_actual"] = ns["PAGINAS"][12]
        at.run()
        cierto("la pantalla abre sin errores", not at.exception, at.exception)
        _botones = {b.key: b.label for b in at.button if str(b.key).startswith("msj_chat_")}
        esperar("un botón por chat", len(_botones), 3)
        _pedro = [lbl for lbl in _botones.values() if "Pedro" in lbl]
        cierto("el nombre del cliente va escapado en la lista (sin link)",
               _pedro and "\\[link\\]" in _pedro[0] and "](http" not in _pedro[0].replace("\\]", ""),
               _pedro)
        _clave_juan = f"msj_chat_{_juan['id']}"
        at.button(key=_clave_juan).click().run()
        esperar("abrir el chat lo marca leído",
                c.execute("SELECT sin_leer FROM chats WHERE id = ?", (_juan["id"],)).fetchone()[0], 0)
        _textos = [m.value for m in at.markdown]
        cierto("se ve la conversación", any("Tenés el W712/80" in t for t in _textos))
        cierto("y lo que trae el auto anotado con ese teléfono",
               any("AB123CD" in x.value for x in at.caption))
        _buscar = [b for b in at.button if str(b.key).startswith(f"msj_buscar_cod_{_juan['id']}")]
        esperar("los códigos que mandó, para buscarlos",
                sorted(b.label for b in _buscar), ["🔍 Buscar PH5949", "🔍 Buscar W712/80"])
        # Contestar desde la pantalla.
        meta.pedidos.clear()
        at.text_area(key=f"msj_respuesta_{_juan['id']}").input("Lo tengo, ¿te lo separo?")
        [b for b in at.button if b.label == "📤 Enviar"][0].click().run()
        esperar("desde la pantalla se manda por WhatsApp",
                [(p["url"], p["json"]["text"]["body"]) for p in meta.pedidos],
                [("https://graph.facebook.com/v26.0/NUM1/messages", "Lo tengo, ¿te lo separo?")])
        esperar("y la caja queda vacía para la próxima",
                at.text_area(key=f"msj_respuesta_{_juan['id']}").value, "")
        # Buscar el código lleva al Buscador con eso buscado.
        _b = [b for b in at.button if b.label == "🔍 Buscar W712/80"][0]
        _b.click().run()
        esperar("«🔍 Buscar» lleva al Buscador con el código",
                (at.session_state["pagina_actual"], at.text_input(key="busqueda_input").value),
                (ns["PAGINAS"][0], "W712/80"))
        _todo = json.dumps([str(e.value) for e in at.markdown] + [str(e.value) for e in at.caption]
                           + [str(e.value) for e in at.code], ensure_ascii=False)
        cierto("ningún permiso en la pantalla", not any(s in _todo for s in SECRETAS))

        # 8. ADMINISTRAR: probar la conexión dice el nombre de la página y del número, no las
        # claves. Y la sección de conectar no las muestra.
        [b for b in at.button if b.label == "Salir"][0].click().run()
        _entrar(at, "duenio", "clave-duenio-1")
        at.session_state["pagina_actual"] = ns["PAGINAS"][3]
        at.session_state["sub_admin"] = ns["SUB_ADMIN"][2]
        at.session_state["exp_conectar_canales"] = True
        at.run()
        _probar = [b for b in at.button if b.key == "probar_los_canales"]
        cierto("en Administrar está «🔌 Probar la conexión»", _probar, [b.key for b in at.button][:40])
        if _probar:
            _probar[0].click().run()
            _dichos = [x.value for x in at.success] + [x.value for x in at.error]
            cierto("dice la página, la cuenta de Instagram, el número y el relevo",
                   any("Repuestos de Prueba" in x for x in _dichos)
                   and any("@repuestos" in x for x in _dichos)
                   and any("5555-0000" in x for x in _dichos)
                   and any("relevo" in x for x in _dichos), _dichos)
            _todo = json.dumps(_dichos + [str(e.value) for e in at.code]
                               + [str(e.value) for e in at.markdown], ensure_ascii=False)
            cierto("y ninguna clave", not any(s in _todo for s in SECRETAS))
    finally:
        _g["requests"], _g["secretos_app"] = requests_de_verdad, secretos_de_verdad
    return fallas


# EL RELEVO, con Node: el mismo worker.js que se pega en Cloudflare, con un KV de mentira.
_PRUEBA_DEL_RELEVO = r"""
import relevo from "./worker.mjs";
const kv = new Map();
const AVISOS = {
  async put(k, v) { kv.set(k, v); }, async get(k) { return kv.has(k) ? kv.get(k) : null; },
  async delete(k) { kv.delete(k); },
  async list({ prefix }) { return { keys: [...kv.keys()].filter(k => k.startsWith(prefix)).map(name => ({ name })) }; },
};
const env = { AVISOS, VERIFICAR: "palabra-de-prueba", SECRETO_DE_LA_APP: "secreto-de-la-app",
              CLAVE_DEL_RELEVO: "clave-del-relevo-de-prueba" };
const firmar = async (cuerpo, secreto = env.SECRETO_DE_LA_APP) => {
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(secreto), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const b = new Uint8Array(await crypto.subtle.sign("HMAC", k, new TextEncoder().encode(cuerpo)));
  return "sha256=" + Array.from(b, x => x.toString(16).padStart(2, "0")).join("");
};
const pedir = (ruta, opciones = {}) => relevo.fetch(new Request("https://relevo.example" + ruta, opciones), env);
const salida = {};
let r = await pedir("/webhook?hub.mode=subscribe&hub.verify_token=palabra-de-prueba&hub.challenge=4242");
salida.verificar = [r.status, await r.text()];
r = await pedir("/webhook?hub.mode=subscribe&hub.verify_token=otra&hub.challenge=4242");
salida.verificar_mal = r.status;
const mensaje = JSON.stringify({ object: "whatsapp_business_account", entry: [{ changes: [{ value: { messages: [{ id: "wamid.1", from: "549", type: "text", text: { body: "hola" } }] } }] }] });
r = await pedir("/webhook", { method: "POST", body: mensaje, headers: { "X-Hub-Signature-256": await firmar(mensaje) } });
salida.aviso = [r.status, kv.size];
r = await pedir("/webhook", { method: "POST", body: mensaje, headers: { "X-Hub-Signature-256": await firmar(mensaje, "otro-secreto") } });
salida.firma_mala = [r.status, kv.size];
r = await pedir("/webhook", { method: "POST", body: mensaje });
salida.sin_firma = [r.status, kv.size];
const estados = JSON.stringify({ object: "whatsapp_business_account", entry: [{ changes: [{ value: { statuses: [{ id: "wamid.1", status: "read" }] } }] }] });
r = await pedir("/webhook", { method: "POST", body: estados, headers: { "X-Hub-Signature-256": await firmar(estados) } });
salida.solo_estados = [r.status, kv.size];
const enorme = "x".repeat(300 * 1024);
r = await pedir("/webhook", { method: "POST", body: enorme, headers: { "X-Hub-Signature-256": await firmar(enorme) } });
salida.enorme = [r.status, kv.size];
r = await pedir("/avisos");
salida.avisos_sin_clave = r.status;
r = await pedir("/avisos", { headers: { Authorization: "Bearer clave-del-relevo-de-prueb" } });
salida.avisos_clave_mala = r.status;
r = await pedir("/avisos", { headers: { Authorization: "Bearer clave-del-relevo-de-prueba" } });
const avisos = (await r.json()).avisos;
salida.avisos = [r.status, avisos.length, avisos[0].cuerpo === mensaje];
r = await pedir("/avisos?solo_cuantos=1", { headers: { Authorization: "Bearer clave-del-relevo-de-prueba" } });
salida.cuantos = (await r.json()).cuantos;
r = await pedir("/confirmar", { method: "POST", body: JSON.stringify({ ids: [avisos[0].id] }) });
salida.confirmar_sin_clave = [r.status, kv.size];
r = await pedir("/confirmar", { method: "POST", body: JSON.stringify({ ids: [avisos[0].id, "otra-cosa"] }), headers: { Authorization: "Bearer clave-del-relevo-de-prueba" } });
salida.confirmar = [r.status, kv.size];
const sinClave = { ...env, CLAVE_DEL_RELEVO: "" };
r = await relevo.fetch(new Request("https://relevo.example/avisos", { headers: { Authorization: "Bearer " } }), sinClave);
salida.relevo_sin_clave_puesta = r.status;
console.log(JSON.stringify(salida));
"""

_LO_QUE_TIENE_QUE_DAR_EL_RELEVO = {
    "verificar": [200, "4242"], "verificar_mal": 403, "aviso": [200, 1], "firma_mala": [401, 1],
    "sin_firma": [401, 1], "solo_estados": [200, 1], "enorme": [413, 1], "avisos_sin_clave": 401,
    "avisos_clave_mala": 401, "avisos": [200, 1, True], "cuantos": 1,
    "confirmar_sin_clave": [401, 1], "confirmar": [200, 0], "relevo_sin_clave_puesta": 401,
}


def probar_el_relevo(carpeta):
    """Las fallas del relevo, o None si no hay Node para correrlo."""
    if not shutil.which("node"):
        return None
    shutil.copy(os.path.join(RAIZ, "integraciones", "relevo_de_mensajes", "worker.js"),
                os.path.join(carpeta, "worker.mjs"))
    with open(os.path.join(carpeta, "prueba.mjs"), "w", encoding="utf-8") as f:
        f.write(_PRUEBA_DEL_RELEVO)
    r = subprocess.run(["node", "prueba.mjs"], cwd=carpeta, capture_output=True, text=True,
                       timeout=60)
    if r.returncode:
        return [f"el relevo no corrió: {(r.stderr or r.stdout)[-400:]}"]
    salida = json.loads(r.stdout.strip().splitlines()[-1])
    return [f"relevo, {k}: dio {salida.get(k)!r}, se esperaba {v!r}"
            for k, v in _LO_QUE_TIENE_QUE_DAR_EL_RELEVO.items() if salida.get(k) != v]


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_mensajes_")
    os.chdir(carpeta)
    sys.path.insert(0, RAIZ)
    try:
        fallas = probar()
        del_relevo = probar_el_relevo(carpeta)
        if del_relevo is None:
            # En GitHub siempre hay Node: si falta ahí, es una falla y no un «no se pudo».
            if os.environ.get("CI"):
                fallas.append("no hay Node para probar el relevo")
            else:
                print("   ⚪ sin Node: el relevo no se probó")
        else:
            fallas += del_relevo
        for f in fallas:
            print("   ✗", f)
        print("✅ mensajes: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(RAIZ)
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

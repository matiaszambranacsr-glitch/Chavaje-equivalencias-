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
import time
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
        self.numero = 0              # el número de cada mensaje mandado: Meta nunca lo repite

    def request(self, metodo, url, params=None, json=None, timeout=None, headers=None):
        # Lo que no va a Meta ni al relevo es de otra parte de la app (una tarea de fondo que
        # justo sale a internet): no se anota ni se contesta como Meta. En GitHub, con la base
        # nueva, una se colaba entre «contestar» y lo que se miraba de ese pedido.
        if not url.startswith(("https://graph.facebook.com/", "https://relevo.example/")):
            return _Respuesta(404, {})
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
            self.numero += 1
            return _Respuesta(200, {"messages": [{"id": f"wamid.SALE{self.numero}"}]})
        if url.endswith("/NUM1"):
            return _Respuesta(200, {"display_phone_number": "+54 9 11 5555-0000",
                                    "verified_name": "Repuestos de Prueba"})
        if url.endswith("/PAG1/messages"):
            self.numero += 1
            return _Respuesta(200, {"recipient_id": json["recipient"]["id"],
                                    "message_id": f"m_SALE{self.numero}"})
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
        _p = ([p for p in meta.pedidos if p["url"].endswith("/NUM1/messages")] or [{}])[-1]
        esperar("va al número del negocio, al de Juan, con el permiso en la cabecera",
                (_p.get("metodo"), _p.get("url"), (_p.get("json") or {}).get("to"),
                 ((_p.get("json") or {}).get("text") or {}).get("body"),
                 (_p.get("headers") or {}).get("Authorization")),
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
        esperar("vacío o larguísimo no se manda; el largo, el de cada canal",
                (ns["contestar_chat"](_juan["id"], "   ")[0],
                 ns["contestar_chat"](_juan["id"], "x" * 4097)[0],
                 ns["contestar_chat"](_maria, "x" * 2001)[0]), (False, False, False))
        _antes = len(meta.pedidos)
        esperar("por WhatsApp entra una cotización de 3.000 letras",
                ns["contestar_chat"](_juan["id"], "x" * 3000), (True, None))
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
            # Y borrar, tampoco el empleado: es del administrador.
            _g["_nivel_de_quien_esta_adentro"] = lambda: "operador"
            try:
                ns["borrar_chat"](_juan["id"])
                fallas.append("un empleado pudo borrar un chat")
            except PermissionError:
                pass
            for _nivel in ("", "mecanico"):
                _g["_nivel_de_quien_esta_adentro"] = lambda n=_nivel: n
                for _nombre, _llamar in (("contestar", lambda: ns["contestar_chat"](_juan["id"], "x")),
                                         ("marcar leído", lambda: ns["marcar_leido"](_juan["id"])),
                                         ("traer ahora", lambda: ns["traer_mensajes_ahora"]()),
                                         ("borrar un chat", lambda: ns["borrar_chat"](_juan["id"]))):
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
        # Si es una cuenta corriente con ese WhatsApp anotado: quién es y cuánto debe. Y el
        # saldo y el acceso van a su número.
        _cuenta_juan = ns["crear_mecanico"]("Taller De Juan")
        ns["guardar_telefono_de_la_cuenta"](_cuenta_juan, "11 5555-6666")
        c.execute("INSERT INTO movimientos_de_cuenta (mecanico_id, concepto, importe, vence, anulado) "
                  "VALUES (?, 'venta', 1000, date('now', '-40 days'), 0)", (_cuenta_juan,))
        esperar("el chat sabe que es la cuenta, y cuánto debe",
                ns["lo_que_sabemos_del_numero"](dict(_juan))[0],
                ("💳 Cuenta", "Taller De Juan — debe $1.000 ($1.000 vencido)"))
        esperar("el saldo y el acceso, al WhatsApp de la cuenta",
                ns["link_de_whatsapp"](ns["telefono_de_la_cuenta"](_cuenta_juan), "x"),
                "https://wa.me/5491155556666?text=x")
        try:
            _g["_nivel_de_quien_esta_adentro"] = lambda: "mecanico"
            ns["guardar_telefono_de_la_cuenta"](_cuenta_juan, "11 0000-0000")
            fallas.append("un taller pudo cambiar el teléfono de una cuenta")
        except PermissionError:
            pass
        finally:
            _g["_nivel_de_quien_esta_adentro"] = _adentro
        # COBRAR LO VENCIDO: la cuenta que debe vencido sale con su WhatsApp ya escrito; la que
        # debe pero no vencido, no. «✅ Ya se lo recordé» la pasa al final por una semana.
        esperar("el recordatorio, con el vencido y el total",
                ns["mensaje_de_lo_vencido"]("Taller De Juan", 1500, 1000),
                "Hola Taller De Juan! Te escribimos de El Chavo. En tu cuenta corriente hay "
                "$1.000 vencidos (el saldo total es $1.500). ¿Cuándo podés pasar a "
                "regularizarlo? ¡Gracias!")
        _al_dia = ns["crear_mecanico"]("Taller Al Día")
        c.execute("INSERT INTO movimientos_de_cuenta (mecanico_id, concepto, importe, vence, anulado) "
                  "VALUES (?, 'venta', 900, date('now', '+20 days'), 0)", (_al_dia,))
        _debe_mas = ns["crear_mecanico"]("Taller Que Debe Más")
        c.execute("INSERT INTO movimientos_de_cuenta (mecanico_id, concepto, importe, vence, anulado) "
                  "VALUES (?, 'venta', 5000, date('now', '-10 days'), 0)", (_debe_mas,))
        ns["conn"].commit()
        _para_recordar = lambda: [(x["Taller"], x["toca"], x["recordado_hace"])
                                  for x in ns["cuentas_para_recordar"]()]
        esperar("las que deben vencido, la que más debe primero; la que está al día, no",
                _para_recordar(), [("Taller Que Debe Más", True, None),
                                   ("Taller De Juan", True, None)])
        _juan_cobrar = [x for x in ns["cuentas_para_recordar"]() if x["ID"] == _cuenta_juan][0]
        esperar("el recordatorio va al WhatsApp de la cuenta, ya escrito",
                _juan_cobrar["link"], ns["link_de_whatsapp"]("11 5555-6666",
                ns["mensaje_de_lo_vencido"]("Taller De Juan", 1000, 1000)))
        cierto("y empieza con el número bien armado",
               _juan_cobrar["link"].startswith("https://wa.me/5491155556666?text=Hola%20Taller"),
               _juan_cobrar["link"][:60])
        esperar("la que no tiene WhatsApp anotado: WhatsApp pregunta a quién",
                [(x["tiene_whatsapp"], x["link"][:15]) for x in ns["cuentas_para_recordar"]()
                 if x["ID"] == _debe_mas], [(False, "https://wa.me/?")])
        ns["marcar_recordatorio"](_debe_mas)
        esperar("ya se lo recordé: hoy, y pasa al final",
                _para_recordar(), [("Taller De Juan", True, None),
                                   ("Taller Que Debe Más", False, 0)])
        cierto("queda en el registro de cambios",
               c.execute("SELECT COUNT(*) FROM registro_de_cambios WHERE accion = "
                         "'le recordó lo vencido'").fetchone()[0] == 1)
        c.execute("UPDATE mecanicos SET recordado_en = datetime('now', '-8 days') WHERE id = ?",
                  (_debe_mas,))
        esperar("a la semana vuelve a tocar", _para_recordar()[0], ("Taller Que Debe Más", True, 8))
        # En 💬 Mensajes: el chat de la que debe vencido trae su recordatorio; el de la que debe
        # sin vencer, no; por Instagram tampoco (el «número» no es un teléfono).
        ns["guardar_telefono_de_la_cuenta"](_al_dia, "11 4444-3333")
        esperar("el chat de una cuenta que debe, pero sin vencer: sin recordatorio",
                ns["recordatorio_del_chat"]({"canal": "whatsapp", "externo": "5491144443333"}), None)
        esperar("el de la que debe vencido, con el suyo",
                ns["recordatorio_del_chat"]({"canal": "whatsapp", "externo": "5491155556666"}),
                (_cuenta_juan, ns["mensaje_de_lo_vencido"]("Taller De Juan", 1000, 1000)))
        esperar("por Instagram, no", ns["recordatorio_del_chat"](
            {"canal": "instagram", "externo": "5491155556666"}), None)
        ns["guardar_telefono_de_la_cuenta"](_al_dia, "")
        for _nivel in ("mecanico", ""):
            try:
                _g["_nivel_de_quien_esta_adentro"] = lambda _n=_nivel: _n
                ns["marcar_recordatorio"](_cuenta_juan)
                fallas.append(f"«{_nivel or 'invitado'}» pudo anotar un recordatorio")
            except PermissionError:
                pass
            finally:
                _g["_nivel_de_quien_esta_adentro"] = _adentro
        c.execute("DELETE FROM movimientos_de_cuenta WHERE mecanico_id IN (?, ?)", (_al_dia, _debe_mas))
        ns["conn"].commit()
        ns["guardar_telefono_de_la_cuenta"](_cuenta_juan, "")
        esperar("sin teléfono, ya no la reconoce", ns["cuenta_del_telefono"]("5491155556666"), None)
        esperar("las 24 horas", (ns["fuera_de_la_ventana"]({"ultimo_del_cliente_en": ns["_momento_utc"](None)}),
                                 ns["fuera_de_la_ventana"]({"ultimo_del_cliente_en": "2020-01-01 10:00:00"}),
                                 ns["fuera_de_la_ventana"]({})), (False, True, True))
        esperar("el texto del cliente, sin formato, enlaces ni fórmulas",
                ns["texto_de_chat_para_markdown"]("**a** ![x](http://y.example/p.png) $1 y $2\nfin"),
                "\\*\\*a\\*\\* !\\[x\\](http://y.example/p.png) \\$1 y \\$2  \nfin")

        _ahora = datetime(2026, 11, 18, 15, 0, 0)
        esperar("hace cuánto espera",
                [ns["hace_cuanto_espera"](x, _ahora) for x in
                 ("2026-11-18 14:55:00", "2026-11-18 12:00:00", "2026-11-14 15:00:00", "")],
                ["hace 5 min", "hace 3 h", "hace 4 días", ""])
        # Las respuestas rápidas: las de siempre, las del negocio, y vacío vuelve a las de siempre.
        esperar("las respuestas rápidas de siempre", ns["respuestas_rapidas"](),
                list(ns["RESPUESTAS_RAPIDAS"]))
        esperar("guardar las del negocio", ns["guardar_respuestas_rapidas"](
            "  Abrimos de 8 a 18  \n\n Estamos en Av. Siempreviva 742 \n" + "x" * 400), 3)
        esperar("y se usan esas", ns["respuestas_rapidas"](),
                ["Abrimos de 8 a 18", "Estamos en Av. Siempreviva 742", "x" * 300])
        ns["guardar_respuestas_rapidas"]("")
        esperar("vacío vuelve a las de siempre", ns["respuestas_rapidas"](),
                list(ns["RESPUESTAS_RAPIDAS"]))
        try:
            _g["_nivel_de_quien_esta_adentro"] = lambda: "operador"
            ns["guardar_respuestas_rapidas"]("no")
            fallas.append("un empleado pudo cambiar las respuestas rápidas")
        except PermissionError:
            pass
        finally:
            _g["_nivel_de_quien_esta_adentro"] = _adentro

        # Los teléfonos, como los pide WhatsApp (54 9 …). Con «11 4567-8901» tal cual, el link
        # de los avisos de Vehículos iba a wa.me/1145678901: un número de Estados Unidos.
        esperar("los teléfonos de acá, como los pide WhatsApp",
                [ns["numero_para_whatsapp"](x) for x in (
                    "11 4567-8901", "011 15 4567-8901", "(011) 4567-8901", "0341 15 555-0000",
                    "341 555-0000", "02954 15 123456", "+54 9 11 4567-8901", "54 11 4567 8901",
                    "5491145678901", "0054 9 11 4567 8901", "15 4567-8901", "4567-8901", "", None)],
                ["5491145678901", "5491145678901", "5491145678901", "5493415550000",
                 "5493415550000", "5492954123456", "5491145678901", "5491145678901",
                 "5491145678901", "5491145678901", "", "", "", ""])
        esperar("el link: con número y texto, o sin número",
                (ns["link_de_whatsapp"]("11 4567-8901", "hola che"),
                 ns["link_de_whatsapp"]("15 4567-8901", "hola")),
                ("https://wa.me/5491145678901?text=hola%20che", "https://wa.me/?text=hola"))

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
        # Con CSS: el nombre de la opción no cambia nunca (si cambia, el navegador se queda sin
        # pantalla marcada y el toque siguiente vuelve a Ventas: ver cuenta_en_la_barra()).
        esperar("al personal le dice cuántos sin leer, en la pastilla (sin cambiarle el nombre)",
                ([o for o in at.radio(key="pagina_actual").options if "Mensajes" in o],
                 sum(m.value.count('content: " · 1"') for m in at.markdown)),
                (["💬 Mensajes"], 1))
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
        at.text_input(key="msj_numero_nuevo").input("0341 15 555-0000")
        at.text_area(key="msj_texto_nuevo").input("Hola! Ya llegó tu repuesto")
        at.run()
        _links_nuevo = [str(x.proto.url) for x in at.get("link_button")
                        if "Abrirlo en WhatsApp" in str(x.proto.label)]
        esperar("«✉️ Escribirle a un número nuevo» abre WhatsApp con el número y el texto",
                _links_nuevo, ["https://wa.me/5493415550000?text=Hola%21%20Ya%20lleg%C3%B3%20tu%20repuesto"])
        at.text_input(key="msj_numero_nuevo").input("15 555-0000")
        at.run()
        cierto("sin característica, dice cómo va", any("característica" in w.value for w in at.warning))
        at.text_input(key="msj_numero_nuevo").input("")
        at.run()
        _botones = {b.key: b.label for b in at.button if str(b.key).startswith("msj_chat_")}
        esperar("un botón por chat", len(_botones), 3)
        _maria_lbl = [lbl for lbl in _botones.values() if "María" in lbl]
        # Lo último de María lo mandó otro (la prueba, sin sesión: «Invitado»): la lista dice
        # quién, no «Vos:» como si lo hubiera mandado Ana.
        cierto("lo último de María dice quién lo mandó, no «Vos:»",
               _maria_lbl and "Invitado: Te espero" in _maria_lbl[0], _maria_lbl)
        _pedro = [lbl for lbl in _botones.values() if "Pedro" in lbl]
        cierto("Pedro espera respuesta: dice hace cuánto", _pedro and "hace " in _pedro[0], _pedro)
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
        # LA CUENTA QUE DEBE Y ESCRIBE: «💳 Recordarle lo vencido» pone el recordatorio en la
        # caja (sin borrar lo escrito, y una sola vez); mandado desde acá queda anotado solo.
        ns["guardar_telefono_de_la_cuenta"](_cuenta_juan, "11 5555-6666")
        c.execute("UPDATE mecanicos SET recordado_en = NULL WHERE id = ?", (_cuenta_juan,))
        ns["conn"].commit()
        at.session_state[f"msj_respuesta_{_juan['id']}"] = "Sí, lo tengo."
        at.run()
        _recordar = [b for b in at.button if b.key == f"msj_recordar_{_juan['id']}"]
        cierto("el chat de una cuenta que debe vencido tiene «💳 Recordarle lo vencido»", _recordar)
        if _recordar:
            _recordar[0].click().run()
            at.button(key=f"msj_recordar_{_juan['id']}").click().run()
            _texto_rec = ns["mensaje_de_lo_vencido"]("Taller De Juan", 1000, 1000)
            esperar("lo pone en la respuesta, después de lo escrito y una sola vez",
                    at.text_area(key=f"msj_respuesta_{_juan['id']}").value,
                    "Sí, lo tengo.\n\n" + _texto_rec)
            meta.pedidos.clear()
            [b for b in at.button if b.label == "📤 Enviar"][0].click().run()
            esperar("se manda y queda anotado como recordado",
                    (len(meta.pedidos), [x["recordado_hace"] for x in ns["cuentas_para_recordar"]()
                                         if x["ID"] == _cuenta_juan]), (1, [0]))
        ns["guardar_telefono_de_la_cuenta"](_cuenta_juan, "")
        at.run()
        cierto("si no es una cuenta, no está el botón",
               not [b for b in at.button if b.key == f"msj_recordar_{_juan['id']}"])
        # Lo que mandó Ana, en la lista de Ana, dice «Vos:».
        del at.session_state["msj_chat_abierto"]
        at.run()
        _juan_lbl = [b.label for b in at.button if b.key == f"msj_chat_{_juan['id']}"]
        cierto("lo que mandó Ana, en su lista, dice «Vos:»",
               _juan_lbl and "Vos: Sí, lo tengo" in _juan_lbl[0], _juan_lbl)
        at.button(key=f"msj_chat_{_juan['id']}").click().run()
        # DEL CHAT A LA COTIZACIÓN, Y DE VUELTA. «📋 Cotizar estos códigos» los suma a la lista
        # de WhatsApp (el que no está, se avisa) y lleva ahí.
        c.execute("INSERT OR IGNORE INTO marcas (nombre, tipo) VALUES ('MANN CHAT', 'PROVEEDOR')")
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio) "
                  "SELECT 'W712/80', 'W71280', 'FILTRO ACEITE', id, 12345 FROM marcas "
                  "WHERE nombre = 'MANN CHAT'")
        ns["conn"].commit()
        at.session_state["lista_whatsapp"] = []
        at.run()
        at.button(key=f"msj_cotizar_{_juan['id']}").click().run()
        esperar("«📋 Cotizar estos códigos» lleva a la lista con lo que está cargado",
                (at.session_state["pagina_actual"],
                 [x["codigo_buscado"] for x in at.session_state["lista_whatsapp"]]),
                (ns["PAGINAS"][5], ["W712/80"]))
        cierto("y avisa el que no está cargado", any("PH5949" in w.value for w in at.warning),
               [w.value for w in at.warning])
        _al_chat = [b for b in at.button if b.key == "wa_mandar_al_chat"]
        esperar("en la lista, el botón para mandársela a Juan",
                [b.label for b in _al_chat], ["💬 Mandárselo a Juan Pérez por WhatsApp"])
        meta.pedidos.clear()
        if _al_chat:
            _al_chat[0].click().run()
        _mandado = [p for p in meta.pedidos if p["url"].endswith("/NUM1/messages")]
        cierto("la cotización va al chat de Juan, con el código y el precio",
               len(_mandado) == 1 and "W712/80" in _mandado[0]["json"]["text"]["body"]
               and _mandado[0]["json"]["to"] == "5491155556666",
               [p["json"] for p in _mandado])
        esperar("y vuelve al chat para verla ahí", at.session_state["pagina_actual"],
                ns["PAGINAS"][12])
        # El presupuesto del Buscador, lo mismo.
        _id_mann = c.execute("SELECT id FROM productos WHERE codigo_raw = 'W712/80'").fetchone()[0]
        at.session_state["carrito"] = {_id_mann: {"codigo": "W712/80", "marca": "MANN CHAT",
                                                  "descripcion": "FILTRO ACEITE", "precio": 12345,
                                                  "cantidad": 2}}
        at.session_state["pagina_actual"] = ns["PAGINAS"][0]
        at.run()
        meta.pedidos.clear()
        _al_chat = [b for b in at.button if b.key == "presupuesto_al_chat"]
        cierto("el presupuesto del Buscador también ofrece mandárselo al chat", _al_chat)
        if _al_chat:
            _al_chat[0].click().run()
        _mandado = [p for p in meta.pedidos if p["url"].endswith("/NUM1/messages")]
        cierto("y va con el total",
               len(_mandado) == 1 and "TOTAL: $24.690" in _mandado[0]["json"]["text"]["body"],
               [p["json"] for p in _mandado])
        # Media hora después, el chat ya no está «en curso»: no aparece en el presupuesto.
        at.session_state["msj_chat_abierto_en"] = time.monotonic() - 31 * 60
        at.session_state["pagina_actual"] = ns["PAGINAS"][0]
        at.run()
        esperar("un chat de hace más de media hora no se ofrece",
                [b.key for b in at.button if b.key == "presupuesto_al_chat"], [])
        # Y pasadas las 24 horas de Meta, tampoco: no se le podría mandar.
        _ultimo_juan = c.execute("SELECT ultimo_del_cliente_en FROM chats WHERE id = ?",
                                 (_juan["id"],)).fetchone()[0]
        c.execute("UPDATE chats SET ultimo_del_cliente_en = datetime('now', '-25 hours') "
                  "WHERE id = ?", (_juan["id"],))
        at.session_state["msj_chat_abierto_en"] = time.monotonic()
        at.run()
        esperar("un chat pasadas las 24 horas no se ofrece",
                [b.key for b in at.button if b.key == "presupuesto_al_chat"], [])
        c.execute("UPDATE chats SET ultimo_del_cliente_en = ? WHERE id = ?",
                  (_ultimo_juan, _juan["id"]))
        at.session_state["msj_chat_abierto_en"] = time.monotonic()
        at.session_state["pagina_actual"] = ns["PAGINAS"][12]
        at.run()
        # Buscar el código lleva al Buscador con eso buscado.
        _b = [b for b in at.button if b.label == "🔍 Buscar W712/80"][0]
        _b.click().run()
        esperar("«🔍 Buscar» lleva al Buscador con el código",
                (at.session_state["pagina_actual"], at.text_input(key="busqueda_input").value),
                (ns["PAGINAS"][0], "W712/80"))
        _todo = json.dumps([str(e.value) for e in at.markdown] + [str(e.value) for e in at.caption]
                           + [str(e.value) for e in at.code], ensure_ascii=False)
        cierto("ningún permiso en la pantalla", not any(s in _todo for s in SECRETAS))

        # DEL CHAT AL PRESUPUESTO: lo que pide, separado en pedidos (los códigos y las piezas
        # dichas con palabras, para el auto que nombra), cada uno con lo del catálogo para elegir
        # o descartar, y con lo elegido el presupuesto, listo para mandárselo y seguirlo.
        c.execute("INSERT OR IGNORE INTO marcas (nombre, tipo) VALUES ('MARCA PEDIDO', 'PROVEEDOR')")
        _ids_ped = {}
        # Cargados al revés de como tienen que salir: el orden lo tiene que poner la app.
        for _cod, _desc, _precio in (
                ("TP1", "TAPA DE PASTILLA DELANTERA PARA GOL", 900),
                ("PF1", "PASTILLA DE FRENO DELANTERA VW GOL TREND 1.6", 30000),
                ("AM2", "AMORTIGUADOR DELANTERO FORD KA", 45000),
                ("AM1", "AMORTIGUADOR TRASERO VW GOL", 50000),
                ("PF2", "PASTILLA DE FRENO TRASERA VW GOL", 21000)):
            c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, "
                      "precio, stock) SELECT ?, ?, ?, id, ?, 4 FROM marcas "
                      "WHERE nombre = 'MARCA PEDIDO'", (_cod, _cod, _desc, _precio))
            _ids_ped[_cod] = c.lastrowid
        _pide = ("Hola! necesito pastillas delanteras y 2 amortiguadores traseros para un gol "
                 "2015 1.6, y el W712/80. Tambien una bomba de nafta")
        c.execute("INSERT INTO chat_mensajes (chat_id, canal, externo_id, entra, texto, cuando) "
                  "VALUES (?, 'whatsapp', 'pedido:1', 1, ?, datetime('now', '+1 minute'))",
                  (_juan["id"], _pide))
        ns["conn"].commit()
        esperar("lee lo último que escribió", ns["lo_que_pidio_el_cliente"](_juan["id"]), _pide)
        _peds = ns["pedidos_del_mensaje"](_pide)
        esperar("lo separa en pedidos, con la cantidad y el auto",
                [(p["texto"], p["cantidad"], p["auto"]) for p in _peds],
                [("W712/80", 1, "GOL 1.6 2015"), ("pastilla delantera", 1, "GOL 1.6 2015"),
                 ("amortiguador trasero", 2, "GOL 1.6 2015"), ("bomba de nafta", 1, "GOL 1.6 2015")])
        esperar("primero los del lado pedido",
                [x["Codigo"] for x in ns["candidatos_del_pedido"](
                    ns["pedidos_del_mensaje"]("pastillas delanteras para gol")[0])],
                ["PF1", "TP1", "PF2"])
        esperar("un saludo no es un pedido", ns["pedidos_del_mensaje"]("gracias!! nos vemos"), [])
        esperar("«correa de alternador» es una pieza, no dos; «4 bujías», cuatro",
                [(p["texto"], p["cantidad"]) for p in ns["pedidos_del_mensaje"](
                    "busco 4 bujias para el clio; tambien correa de alternador")],
                [("bujia", 4), ("correa alternador", 1)])
        at.session_state["carrito"] = {}
        at.session_state["msj_chat_abierto"] = _juan["id"]
        at.session_state["msj_chat_abierto_en"] = time.monotonic()
        at.session_state["pagina_actual"] = ns["PAGINAS"][12]
        at.run()
        _exp_ped = [e for e in at.expander if "Armar el presupuesto con lo que pide" in e.label]
        esperar("en el chat, «🧩 Armar el presupuesto con lo que pide (4)»",
                [e.label for e in _exp_ped], ["🧩 Armar el presupuesto con lo que pide (4)"])
        at.session_state[f"exp_presu_chat_{_juan['id']}"] = True
        at.run()
        _sel = {s.label: s for s in at.selectbox if str(s.key).startswith(
            f"pedido_chat_{_juan['id']}_")}
        esperar("un selector por pedido encontrado, y elegido el que es (la delantera, la trasera)",
                {k.split(". ", 1)[-1]: v.value for k, v in _sel.items()},
                {"W712/80 (código)": _id_mann, "pastilla delantera": _ids_ped["PF1"],
                 "amortiguador trasero": _ids_ped["AM1"]})
        cierto("lo que no está se dice, con «🔍 Buscarlo a mano»",
               any("bomba de nafta" in m.value and "no lo encontré" in m.value for m in at.markdown)
               and [b for b in at.button if str(b.key).startswith("a_mano_")])
        # «✍️ Decirle lo que no hay»: a la respuesta, después de lo escrito y una sola vez.
        at.session_state[f"msj_respuesta_{_juan['id']}"] = "Hola Juan!"
        at.session_state[f"exp_presu_chat_{_juan['id']}"] = True
        at.run()
        for _vez in range(2):
            at.session_state[f"exp_presu_chat_{_juan['id']}"] = True
            at.button(key=f"msj_no_hay_{_juan['id']}").click().run()
        esperar("«✍️ Decirle lo que no hay» lo pone en la respuesta",
                at.text_area(key=f"msj_respuesta_{_juan['id']}").value,
                "Hola Juan!\n\nDe lo que me pediste, ahora no tengo bomba de nafta. ¿Querés que te "
                "lo consiga?")
        at.session_state[f"msj_respuesta_{_juan['id']}"] = ""
        at.session_state[f"exp_presu_chat_{_juan['id']}"] = True
        at.run()
        _sel = {s.label: s for s in at.selectbox if str(s.key).startswith(
            f"pedido_chat_{_juan['id']}_")}
        _cant = [n for n in at.number_input if str(n.key).endswith("_cant")]
        esperar("con la cantidad que pidió", [n.value for n in _cant], [1, 1, 2])
        # El código lo descarta; lo demás va al presupuesto del Buscador. (AppTest cierra el
        # desplegable perezoso entre pasada y pasada: se lo vuelve a abrir.)
        at.session_state[f"exp_presu_chat_{_juan['id']}"] = True
        [v for k, v in _sel.items() if "W712" in k][0].set_value(ns["DESCARTAR_EL_PEDIDO"]).run()
        at.button(key=f"armar_pedido_chat_{_juan['id']}").click().run()
        esperar("arma el presupuesto con lo elegido, sin lo descartado",
                sorted((v["codigo"], v["cantidad"]) for v in at.session_state["carrito"].values()),
                [("AM1", 2), ("PF1", 1)])
        esperar("y lleva al Buscador con el cliente y su WhatsApp listos para seguirlo",
                (at.session_state["pagina_actual"], at.session_state["presu_seguir_cliente"],
                 at.session_state["presu_seguir_tel"]),
                (ns["PAGINAS"][0], "Juan Pérez", "5491155556666"))
        cierto("con «💬 Mandárselo» a ese chat",
               [b for b in at.button if b.key == "presupuesto_al_chat"])
        at.session_state["carrito"] = {}
        # «🔍 Buscarlo a mano»: la pieza que no se encontró queda buscada por descripción.
        at.session_state["pagina_actual"] = ns["PAGINAS"][12]
        at.session_state[f"exp_presu_chat_{_juan['id']}"] = True
        at.run()
        [b for b in at.button if str(b.key).startswith("a_mano_")][0].click().run()
        esperar("«🔍 Buscarlo a mano» la deja buscada por descripción en el Buscador",
                (at.session_state["pagina_actual"], at.session_state["modo_busqueda"],
                 at.text_input(key="texto_input").value),
                (ns["PAGINAS"][0], "Descripción", "bomba nafta gol 1.6 2015"))
        # LO QUE LLEGÓ AL WHATSAPP DEL TELÉFONO, pegado en el Buscador: lo mismo, sin chat.
        at.session_state["carrito"] = {}
        at.session_state["msj_chat_abierto"] = None
        at.session_state["presu_seguir_cliente"] = ""
        at.session_state["exp_pedido_pegado"] = True
        at.session_state["pedido_pegado"] = ("hola! 2 amortiguadores traseros para gol, y una "
                                             "bomba de nafta")
        at.run()
        _sel_p = [s for s in at.selectbox if str(s.key).startswith("pedido_pegado_")]
        esperar("pegado en el Buscador: el amortiguador elegido, con la cantidad",
                ([s.value for s in _sel_p],
                 [n.value for n in at.number_input if str(n.key).startswith("pedido_pegado_")]),
                ([_ids_ped["AM1"]], [2]))
        cierto("y lo que no hay, escrito para copiarlo",
               any("ahora no tengo bomba de nafta" in str(x.value) for x in at.code))
        at.session_state["exp_pedido_pegado"] = True
        at.button(key="armar_pedido_pegado").click().run()
        esperar("arma el presupuesto ahí mismo, sin tocar ningún chat ni el cliente a seguir",
                (sorted((v["codigo"], v["cantidad"]) for v in at.session_state["carrito"].values()),
                 at.session_state["pagina_actual"], at.session_state["msj_chat_abierto"],
                 at.session_state["presu_seguir_cliente"]),
                ([("AM1", 2)], ns["PAGINAS"][0], None, ""))
        # Y una frase con varias cosas buscada en la caja de siempre ofrece separarla.
        at.session_state["carrito"] = {}
        at.session_state["pedido_pegado"] = ""
        at.session_state["modo_busqueda"] = "Descripción"
        at.session_state["texto_input"] = "pastillas delanteras y 2 amortiguadores para el gol"
        at.run()
        _separar = [b for b in at.button if b.key == "separar_lo_buscado"]
        cierto("una frase con varias cosas ofrece «🧩 Son varias cosas: separarlas»", _separar)
        if _separar:
            _separar[0].click().run()
            esperar("y la pasa a «🧩 Pegar el pedido de un cliente», abierto",
                    (at.session_state["pedido_pegado"],
                     len([s for s in at.selectbox if str(s.key).startswith("pedido_pegado_")])),
                    ("pastillas delanteras y 2 amortiguadores para el gol", 2))
        at.session_state["texto_input"] = "filtro"
        at.run()
        esperar("una sola cosa no lo ofrece",
                [b.key for b in at.button if b.key == "separar_lo_buscado"], [])
        at.session_state["texto_input"] = ""
        at.session_state["pedido_pegado"] = ""
        at.session_state["modo_busqueda"] = "Código"

        # En la ficha del auto, un teléfono que no sirve para WhatsApp se dice (sin característica,
        # los avisos no sabrían a quién ir); uno que sirve, no.
        c.execute("INSERT INTO vehiculos (patente, cliente_nombre, cliente_telefono) "
                  "VALUES ('AC 111 BB', 'Sin Caract', '15 4567-8901'), "
                  "('AC 222 BB', 'Con Caract', '011 15 4567-8901')")
        ns["conn"].commit()
        at.session_state["pagina_actual"] = ns["PAGINAS"][6]
        at.run()
        _avisos_tel = {}
        for _pat in ("AC111BB", "AC222BB"):
            at.text_input(key="patente_buscar").input(_pat).run()
            _avisos_tel[_pat] = any("no sirve para WhatsApp" in w.value for w in at.warning)
        esperar("la ficha avisa el teléfono sin característica, y no el que está bien",
                _avisos_tel, {"AC111BB": True, "AC222BB": False})

        # 8. ADMINISTRAR: probar la conexión dice el nombre de la página y del número, no las
        # claves. Y la sección de conectar no las muestra.
        [b for b in at.button if b.label == "Salir"][0].click().run()
        _entrar(at, "duenio", "clave-duenio-1")
        at.session_state["pagina_actual"] = ns["PAGINAS"][3]
        at.session_state["sub_admin"] = ns["SUB_ADMIN"][2]
        at.session_state["exp_conectar_canales"] = True
        at.run()
        # El administrador borra el chat de Pedro: se va con sus mensajes, y en el registro de
        # cambios queda que se borró, sin lo que decía.
        _pedro_id = c.execute("SELECT id FROM chats WHERE externo = '5493415550000'").fetchone()[0]
        at.session_state["pagina_actual"] = ns["PAGINAS"][12]
        at.session_state["msj_chat_abierto"] = _pedro_id
        at.session_state["msj_chat_abierto_en"] = time.monotonic()
        at.run()
        _borrar = [b for b in at.button if b.key == f"msj_borrar_{_pedro_id}"]
        cierto("el administrador tiene «🗑️ Borrar este chat»", _borrar)
        if _borrar:
            _borrar[0].click().run()
        esperar("borrado, con sus mensajes",
                (c.execute("SELECT COUNT(*) FROM chats WHERE id = ?", (_pedro_id,)).fetchone()[0],
                 c.execute("SELECT COUNT(*) FROM chat_mensajes WHERE chat_id = ?",
                           (_pedro_id,)).fetchone()[0]), (0, 0))
        _registro = json.dumps([list(r) for r in c.execute(
            "SELECT * FROM registro_de_cambios WHERE accion = 'borró un chat'").fetchall()],
            ensure_ascii=False)
        cierto("en el registro: que se borró, sin lo que decía",
               "borró un chat" in _registro and "hola" not in _registro, _registro)
        at.session_state["pagina_actual"] = ns["PAGINAS"][3]
        at.session_state["sub_admin"] = ns["SUB_ADMIN"][2]
        at.session_state["exp_conectar_canales"] = True
        at.run()
        # COBRAR LO VENCIDO en la pantalla: la cuenta de Juan, con su botón al WhatsApp de la
        # cuenta y el «✅ Ya se lo recordé», que la anota.
        ns["guardar_telefono_de_la_cuenta"](_cuenta_juan, "11 5555-6666")
        at.session_state["sub_admin"] = ns["SUB_ADMIN"][6]
        at.session_state["exp_cobrar_vencido"] = True
        at.run()
        _recordarle = [b.proto.url for b in at.get("link_button")
                       if b.proto.label == "📲 Recordarle"]
        cierto("en 💳 Cuentas corrientes: «📲 Recordarle», al WhatsApp de la cuenta",
               any(u.startswith("https://wa.me/5491155556666?text=") for u in _recordarle),
               (_recordarle, [e.value for e in at.exception]))
        _ya = [b for b in at.button if b.key == f"cc_recordado_{_cuenta_juan}"]
        cierto("y «✅ Ya se lo recordé»", _ya)
        if _ya:
            _ya[0].click().run()
            esperar("que la anota", [x["recordado_hace"] for x in ns["cuentas_para_recordar"]()
                                     if x["ID"] == _cuenta_juan], [0])
        at.session_state["sub_admin"] = ns["SUB_ADMIN"][2]
        at.session_state["exp_conectar_canales"] = True
        at.run()
        # EL PEDIDO AL PROVEEDOR (📌 Para pedir): el WhatsApp del proveedor de la marca se anota
        # una vez y queda; y el link lleva el mensaje como quedó escrito (antes llevaba el armado,
        # sin lo que se le corregía).
        c.execute("INSERT OR IGNORE INTO marcas (nombre, tipo) VALUES ('BOSCH PRUEBA', 'PROVEEDOR')")
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, stock) "
                  "SELECT 'BP1', 'BP1', 'BUJIA', id, 0 FROM marcas WHERE nombre = 'BOSCH PRUEBA'")
        ns["solicitar_reposicion"](c.lastrowid)
        ns["conn"].commit()
        _pedido = [p for p in ns["listar_pedidos_reposicion"]() if p["Codigo"] == "BP1"][0]
        at.session_state["pagina_actual"] = ns["PAGINAS"][4]
        at.session_state["sub_stats"] = ns["SUB_STATS"][5]
        at.session_state[f"chk_pedido_{_pedido['ID']}"] = True
        at.run()
        _tel_prov = [t for t in at.text_input if str(t.key).startswith("wa_prov_")]
        _msg_prov = [t for t in at.text_area if str(t.key).startswith("msg_repo_")]
        cierto("en el pedido al proveedor: su WhatsApp y el mensaje", _tel_prov and _msg_prov,
               ([e.value for e in at.exception], [t.key for t in at.text_input][-5:]))
        if _tel_prov and _msg_prov:
            _tel_prov[0].set_value("11 4444-5555").run()
            esperar("el WhatsApp del proveedor queda guardado",
                    ns["whatsapp_del_proveedor"]("BOSCH PRUEBA"), "11 4444-5555")
            [t for t in at.text_area if str(t.key).startswith("msg_repo_")][0].set_value(
                "Necesito 4 BP1, urgente").run()
            _links_prov = [b.proto.url for b in at.get("link_button")
                           if "Mandárselo por WhatsApp (BOSCH PRUEBA)" in b.proto.label]
            esperar("el link va al proveedor, con el mensaje como quedó escrito", _links_prov,
                    [ns["link_de_whatsapp"]("11 4444-5555", "Necesito 4 BP1, urgente")])
        try:
            _g["_nivel_de_quien_esta_adentro"] = lambda: "mecanico"
            ns["guardar_whatsapp_del_proveedor"]("BOSCH PRUEBA", "11 0000-0000")
            fallas.append("un taller pudo cambiar el WhatsApp de un proveedor")
        except PermissionError:
            pass
        finally:
            _g["_nivel_de_quien_esta_adentro"] = _adentro
        # LAS GARANTÍAS (↩️ Devoluciones → 🔧 Garantías): lo fallado de BOSCH PRUEBA, con el
        # reclamo a su WhatsApp (el mismo número del pedido) y «📤 Ya se lo reclamé».
        _p_gar = c.execute("SELECT id FROM productos WHERE codigo_clean = 'BP1'").fetchone()[0]
        c.execute("UPDATE productos SET precio = 5000, stock = 5 WHERE id = ?", (_p_gar,))
        ns["conn"].commit()
        _v_gar, _ = ns["cerrar_venta"]([dict(ns["item_de_venta"](_p_gar, 1))], a_la_caja=True)
        ns["cobrar_venta"](_v_gar, "Efectivo")
        ns["devolver_de_una_venta"](c.execute("SELECT id FROM ventas_items WHERE venta_id = ?",
                                              (_v_gar,)).fetchone()[0], 1, "fallada", "no enciende")
        at.session_state["pagina_actual"] = ns["PAGINAS"][10]
        at.session_state["sub_devoluciones"] = ns["SUB_DEVOLUCIONES"][3]
        at.run()
        _reclamo = [b.proto.url for b in at.get("link_button")
                    if b.proto.label == "📲 Reclamárselo por WhatsApp"]
        cierto("en 🔧 Garantías, el reclamo va al WhatsApp del proveedor, con lo que volvió",
               len(_reclamo) == 1 and _reclamo[0].startswith("https://wa.me/5491144445555?text=")
               and "no%20enciende" in _reclamo[0],
               (_reclamo, [e.value for e in at.exception][:1]))
        _ya_gar = [b for b in at.button if str(b.key).startswith("garantia_reclamada_")]
        cierto("y «📤 Ya se lo reclamé»", _ya_gar)
        if _ya_gar:
            _ya_gar[0].click().run()
            esperar("que lo anota", [g["reclamo"] for g in ns["garantias"]()
                                     if g["codigo"] == "BP1"], ["reclamado"])
            cierto("y quedan «✅ Lo cambiaron…» y «🚫 No lo reconocieron»",
                   {b.label for b in at.button if str(b.key).startswith(("garantia_resuelta_",
                                                                         "garantia_rechazada_"))}
                   == {"✅ Lo cambiaron o lo acreditaron", "🚫 No lo reconocieron"})
        # EL RESUMEN DEL DÍA PARA EL DUEÑO (💵 Caja → cierre): el administrador anota el WhatsApp
        # del dueño una vez, y el resumen va ahí, escrito.
        at.session_state["pagina_actual"] = "💵 Caja"
        at.session_state["exp_ventas_cierre_caja_hoy"] = True
        at.run()
        _tel_duenio = [t for t in at.text_input if t.key == "wa_duenio"]
        _caja_res = [t for t in at.text_area if str(t.key).startswith("resumen_dia_")]
        cierto("en el cierre: el resumen y el WhatsApp del dueño", _tel_duenio and _caja_res,
               [e.value for e in at.exception][:1])
        if _tel_duenio and _caja_res:
            _tel_duenio[0].set_value("11 4444-7777").run()
            esperar("el WhatsApp del dueño queda guardado", ns["whatsapp_del_duenio"](),
                    "11 4444-7777")
            _al_duenio = [b.proto.url for b in at.get("link_button")
                          if b.proto.label == "📲 Mandárselo por WhatsApp"
                          and "5491144447777" in b.proto.url]
            cierto("y el resumen va a su número, con lo vendido",
                   len(_al_duenio) == 1 and "Vendido" in _al_duenio[0], _al_duenio)
        try:
            _g["_nivel_de_quien_esta_adentro"] = lambda: "operador"
            ns["guardar_whatsapp_del_duenio"]("11 0000-0000")
            fallas.append("un empleado pudo cambiar el WhatsApp del dueño")
        except PermissionError:
            pass
        finally:
            _g["_nivel_de_quien_esta_adentro"] = _adentro
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
    # Las tareas de fondo de la app, apagadas: la vuelta por los mensajes se prueba aparte (6),
    # y las demás no tienen nada que hacer acá.
    os.environ["EQUIVALENCIAS_SIN_TAREAS_DE_FONDO"] = "1"
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

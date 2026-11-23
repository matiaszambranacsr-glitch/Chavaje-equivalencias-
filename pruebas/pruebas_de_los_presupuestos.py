"""Los presupuestos para seguir: el que se manda se guarda con el cliente y su WhatsApp, y queda
en «📋 Presupuestos para seguir» hasta que vuelve o no lo quiere.

Uso:
    python3 pruebas/pruebas_de_los_presupuestos.py

Por qué: un presupuesto que se mandaba por WhatsApp y el cliente no contestaba se perdía —nadie
se acordaba de preguntarle—. Esto controla que se guarde (solo el personal), que toque
preguntar desde el día siguiente y de nuevo a los días, que el mensaje diga qué era, y que
«🛒 Volvió: armarlo» lo arme con los precios que se le pasaron (ver «LOS PRESUPUESTOS PARA
SEGUIR» en logica/ventas.py).

Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import os
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def probar():
    from streamlit.testing.v1 import AppTest
    fallas = []

    def esperar(que, dio, se_esperaba):
        if dio != se_esperaba:
            fallas.append(f"{que}: dio {dio!r}, se esperaba {se_esperaba!r}")

    at = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
    at.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
    at.run()
    at.text_input(key="login_inicial_nombre").set_value("duenio")
    at.text_input(key="login_inicial_clave").set_value("clave-duenio-1")
    [b for b in at.button if "Ingresar con contraseña" in b.label][0].click().run()
    ns = sys.modules["logica"].todo_lo_de_la_logica()
    c = ns["c"]
    at.session_state["modo_vista"] = ns["VISTAS"][1]

    c.execute("INSERT OR IGNORE INTO marcas (nombre, tipo) VALUES ('MARCA PRESU', 'PROVEEDOR')")
    ids = {}
    for codigo, precio in (("PR1", 1000), ("PR2", 2500)):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, "
                  "precio, stock) SELECT ?, ?, 'FILTRO', id, ?, 10 FROM marcas "
                  "WHERE nombre = 'MARCA PRESU'", (codigo, codigo, precio))
        ids[codigo] = c.lastrowid
    ns["conn"].commit()

    # 1. EN LA PANTALLA: el presupuesto del Buscador, «📌 Guardarlo para hacerle el seguimiento».
    # El precio que se le pasó (900, no el de lista) es el que queda.
    at.session_state["pagina_actual"] = ns["PAGINAS"][0]
    at.session_state["carrito"] = {
        ids["PR1"]: {"codigo": "PR1", "marca": "MARCA PRESU", "descripcion": "FILTRO",
                     "precio": 900.0, "cantidad": 2},
        ids["PR2"]: {"codigo": "PR2", "marca": "MARCA PRESU", "descripcion": "FILTRO",
                     "precio": 2500.0, "cantidad": 1}}
    at.run()
    _guardar = [b for b in at.button if b.key == "presu_seguir_guardar"]
    if not _guardar:
        fallas.append("en el presupuesto no está «📌 Guardar para seguirlo» "
                      f"({[e.value for e in at.exception][:1]})")
        return fallas
    at.text_input(key="presu_seguir_cliente").set_value("Juan Gómez")
    at.text_input(key="presu_seguir_tel").set_value("11 4567-8901")
    [b for b in at.button if b.key == "presu_seguir_guardar"][0].click().run()
    _lista = ns["presupuestos_para_seguir"]()
    esperar("guardado, con el cliente, el teléfono, el total y los precios que se le pasaron",
            [(p["cliente"], p["telefono"], p["total"],
              [(i["codigo"], i["cantidad"], i["precio"]) for i in p["items"]]) for p in _lista],
            [("Juan Gómez", "11 4567-8901", 4300.0, [("PR1", 2, 900.0), ("PR2", 1, 2500.0)])])
    esperar("y los campos quedan vacíos para el próximo",
            (at.text_input(key="presu_seguir_cliente").value,
             at.text_input(key="presu_seguir_tel").value), ("", ""))
    _id = _lista[0]["id"]

    # 2. CUÁNDO TOCA PREGUNTAR: recién mandado, no; al día siguiente, sí; preguntado, de nuevo a
    # los DIAS_PARA_VOLVER_A_PREGUNTAR.
    esperar("recién mandado no toca", _lista[0]["toca"], False)
    c.execute("UPDATE presupuestos_para_seguir SET creado_en = datetime('now', '-2 days') "
              "WHERE id = ?", (_id,))
    ns["conn"].commit()
    _p = ns["presupuestos_para_seguir"]()[0]
    esperar("a los dos días, toca", (_p["toca"], _p["hace"]), (True, 2))
    esperar("el mensaje dice qué era y pide respuesta",
            ("Hola Juan Gómez! Te escribimos de El Chavo por el presupuesto" in
             ns["mensaje_de_seguimiento"](_p),
             "(MARCA PRESU PR1, MARCA PRESU PR2, total $4.300). ¿Lo pudiste ver?" in
             ns["mensaje_de_seguimiento"](_p)), (True, True))
    esperar("el link va a su WhatsApp", _p["link"].startswith("https://wa.me/5491145678901?text="),
            True)

    # 2b. EL QUE YA CONTESTÓ POR EL CHAT no se pregunta: «💬 Te contestó: ver el chat». Se lo
    # reconoce por el número, escrito distinto en el presupuesto y en el chat.
    c.execute("INSERT INTO chats (canal, externo, nombre, ultimo_del_cliente_en) VALUES "
              "('whatsapp', '5491145678901', 'Juan', datetime('now', '-1 day'))")
    _chat = c.lastrowid
    ns["conn"].commit()
    _p = ns["presupuestos_para_seguir"]()[0]
    esperar("escribió por el chat después del presupuesto: no toca preguntar, toca leerlo",
            (_p["contesto"], _p["toca"]), (_chat, False))
    at.session_state["exp_presupuestos_para_seguir"] = True
    at.run()
    _ver = [b for b in at.button if b.key == f"presu_chat_{_id}"]
    cierto = (lambda que, ok: None if ok else fallas.append(que))
    cierto("en la lista, «💬 Te contestó: ver el chat»", _ver)
    if _ver:
        _ver[0].click().run()
        esperar("lleva a 💬 Mensajes con su chat abierto",
                (at.session_state["pagina_actual"], at.session_state["msj_chat_abierto"]),
                (ns["PAGINAS"][12], _chat))
    # Lo que escribió antes del presupuesto no cuenta.
    c.execute("UPDATE chats SET ultimo_del_cliente_en = datetime('now', '-3 days') WHERE id = ?",
              (_chat,))
    ns["conn"].commit()
    esperar("lo que escribió antes del presupuesto no es una respuesta",
            [(p["contesto"], p["toca"]) for p in ns["presupuestos_para_seguir"]()], [(None, True)])
    at.session_state["pagina_actual"] = ns["PAGINAS"][0]

    # 3. LA LISTA EN EL BUSCADOR: «📋 Presupuestos para seguir», con sus botones.
    at.session_state["carrito"] = {}
    at.session_state["exp_presupuestos_para_seguir"] = True
    at.run()
    _preguntarle = [b.proto.url for b in at.get("link_button")
                    if b.proto.label == "📲 Preguntarle si lo vio"]
    esperar("en el Buscador, «📲 Preguntarle si lo vio», a su WhatsApp", _preguntarle, [_p["link"]])
    _ya = [b for b in at.button if b.key == f"presu_preguntado_{_id}"]
    if _ya:
        _ya[0].click().run()
    esperar("«✅ Ya le pregunté»: deja de tocar por unos días",
            [p["toca"] for p in ns["presupuestos_para_seguir"]()], [False])
    c.execute("UPDATE presupuestos_para_seguir SET preguntado_en = datetime('now', ?) WHERE id = ?",
              (f"-{ns['DIAS_PARA_VOLVER_A_PREGUNTAR']} days", _id))
    ns["conn"].commit()
    esperar("y a los días vuelve a tocar", [p["toca"] for p in ns["presupuestos_para_seguir"]()],
            [True])

    # 3b. SI SUBIERON LOS PRECIOS: se dice cuánto, y dentro de la validez se arma con los que se
    # le pasaron; con el otro botón, con los de hoy.
    c.execute("UPDATE productos SET precio = 1100 WHERE id = ?", (ids["PR1"],))
    ns["conn"].commit()
    _p = ns["presupuestos_para_seguir"]()[0]
    esperar("subió el PR1 de 900 (lo que se le pasó) a 1.100: se dice cuánto",
            (_p["subio"], _p["subieron"], _p["total_hoy"], _p["vencido"]),
            (9, [("MARCA PRESU PR1", 22)], 4700.0, False))
    at.session_state["exp_presupuestos_para_seguir"] = True
    at.run()
    cierto("en la lista, «⚠️ Los precios subieron 9%»",
           any("subieron **9%**" in x.value for x in at.caption))
    cierto("y el otro botón: «con los precios de hoy»",
           [b for b in at.button if b.key == f"presu_volvio_otro_{_id}"
            and "de hoy" in b.label])
    # Pasada la validez, el mensaje lo dice y se arma con los de hoy.
    c.execute("UPDATE presupuestos_para_seguir SET creado_en = datetime('now', ?) WHERE id = ?",
              (f"-{ns['DIAS_DE_VALIDEZ_DEL_PRESUPUESTO']} days", _id))
    ns["conn"].commit()
    _p = ns["presupuestos_para_seguir"]()[0]
    esperar("vencido: el mensaje ofrece pasarlo actualizado",
            (_p["vencido"], "te lo pasamos actualizado" in ns["mensaje_de_seguimiento"](_p)),
            (True, True))

    # 4. «🛒 VOLVIÓ: ARMARLO»: pasada la validez, con los precios de hoy; y sale de la lista.
    at.session_state["exp_presupuestos_para_seguir"] = True
    at.run()
    _volvio = [b for b in at.button if b.key == f"presu_volvio_{_id}"]
    if not _volvio:
        fallas.append("no está «🛒 Volvió: armarlo»")
    else:
        _volvio[0].click().run()
        esperar("volvió pasada la validez: armado otra vez, con los precios de hoy",
                sorted((v["codigo"], v["cantidad"], v["precio"])
                       for v in (at.session_state["carrito"] or {}).values()),
                [("PR1", 2, 1100.0), ("PR2", 1, 2500.0)])
        esperar("y sale de la lista", ns["presupuestos_para_seguir"](), [])

    # 4b. Dentro de la validez, «Volvió: armarlo» respeta el precio que se le pasó, aunque haya
    # subido; con los de hoy, si se pide.
    for _con_hoy, _esperado in ((None, 900.0), (True, 1100.0)):
        _nuevo = ns["guardar_presupuesto_para_seguir"](
            "Pedro", "", {ids["PR1"]: {"codigo": "PR1", "marca": "MARCA PRESU", "precio": 900.0,
                                      "cantidad": 1}})
        at.session_state["carrito"] = {}
        ns["volver_a_armar_el_presupuesto"].__globals__["st"].session_state["carrito"] = {}
        _g_st = ns["volver_a_armar_el_presupuesto"].__globals__["st"]
        ns["volver_a_armar_el_presupuesto"](_nuevo, _con_hoy)
        esperar(f"dentro de la validez ({'con los de hoy' if _con_hoy else 'sin decir'})",
                [v["precio"] for v in _g_st.session_state["carrito"].values()], [_esperado])

    # 5. «🗑️ NO LO QUIERE» lo cierra; y solo el personal guarda (guarda el teléfono de un cliente).
    _otro = ns["guardar_presupuesto_para_seguir"]("Ana", "", {ids["PR1"]: {"codigo": "PR1",
                                                                         "precio": 1000.0,
                                                                         "cantidad": 1}})
    ns["marcar_presupuesto"](_otro, "no")
    esperar("no lo quiere: sale de la lista", ns["presupuestos_para_seguir"](), [])
    _g = ns["guardar_presupuesto_para_seguir"].__globals__
    _antes = (_g["_nivel_de_quien_esta_adentro"], _g["hay_claves_configuradas"])
    try:
        _g["hay_claves_configuradas"] = lambda: True
        for _nivel in ("", "mecanico"):
            _g["_nivel_de_quien_esta_adentro"] = lambda n=_nivel: n
            try:
                ns["guardar_presupuesto_para_seguir"]("X", "", {ids["PR1"]: {"cantidad": 1}})
                fallas.append(f"«{_nivel or 'invitado'}» pudo guardar un presupuesto para seguir")
            except PermissionError:
                pass
    finally:
        _g["_nivel_de_quien_esta_adentro"], _g["hay_claves_configuradas"] = _antes
    fallas += [f"se rompió: {e.value}" for e in at.exception][:2]
    return fallas


def main():
    os.environ["EQUIVALENCIAS_SIN_TAREAS_DE_FONDO"] = "1"
    carpeta = tempfile.mkdtemp(prefix="pruebas_presupuestos_")
    os.chdir(carpeta)
    sys.path.insert(0, RAIZ)
    try:
        fallas = probar()
        for f in fallas:
            print("   ✗", f[:300])
        print("✅ presupuestos: se guardan, toca preguntar a tiempo, y vuelven con sus precios"
              if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(RAIZ)
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

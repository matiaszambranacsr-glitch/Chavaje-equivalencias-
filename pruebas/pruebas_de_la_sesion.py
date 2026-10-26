"""Pruebas de la sesión con la app real (AppTest): salir no deja nada, y los permisos siguen a
la cuenta.

Uso:
    python3 pruebas/pruebas_de_la_sesion.py

Las dos las propuso una revisión con ChatGPT:
  · «login A → seleccionar cosas → logout → login B → comprobar que no aparece nada de A»;
  · «admin cambia el rol → misma sesión»: el nivel se guardaba al entrar y no se volvía a mirar.
Ver cerrar_sesion() y nivel_vigente_de_la_sesion() en logica/base.py.

Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import os
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _entrar(at, clave):
    at.text_input(key="login_inicial_clave").set_value(clave)
    [b for b in at.button if "Ingresar con contraseña" in b.label][0].click().run()


def probar():
    from streamlit.testing.v1 import AppTest
    fallas = []

    def esperar(nombre, real, esperado):
        if real != esperado:
            fallas.append(f"{nombre}: dio {real!r}, se esperaba {esperado!r}")

    at = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
    at.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
    at.run()
    ns = sys.modules["logica"].todo_lo_de_la_logica()
    ns["crear_usuario"]("ana", "clave-ana-1", "operador")

    # 1. Ana entra y deja cosas de ella en la sesión.
    _entrar(at, "clave-ana-1")
    esperar("Ana entró como operador", at.session_state["nivel_usuario"], "operador")
    at.session_state["busqueda_input"] = "W712/94"
    at.session_state["carrito"] = {1: {"codigo": "X", "marca": "Y", "descripcion": "",
                                       "precio": 10, "cantidad": 1}}
    at.session_state["lista_whatsapp"] = [{"codigo_buscado": "X", "resultados": []}]
    at.session_state["cuenta_elegida"] = {"id": 1, "nombre": "Taller", "desde": 0}
    at.session_state["sel_marca_vehiculo"] = "FORD (3 productos)"
    at.run()
    [b for b in at.button if b.label == "Salir"][0].click().run()
    quedaron = {k for k in at.session_state
                if k in ("carrito", "cuenta_elegida", "sel_marca_vehiculo",
                         "nivel_usuario", "admin_nombre")}
    esperar("después de Salir no queda nada de Ana", quedaron, set())
    # La caja de búsqueda no se borra: se VACÍA, que es lo que hace que el navegador la vacíe
    # (ver cerrar_sesion()).
    # Tiene que estar PUESTA en vacío: ausente, el navegador sigue mostrando lo de antes.
    # OJO: AppTest no tiene la memoria del navegador y vuelve a crear el campo vacío, así que
    # esto no alcanza para probarlo; lo que lo prueba es un navegador de verdad (hecho), y lo
    # que lo cuida es el control 6c de auditar.py.
    esperar("la caja de búsqueda puesta en vacío", at.session_state["busqueda_input"]
            if "busqueda_input" in at.session_state else "(ausente)", "")
    esperar("la lista de WhatsApp vacía", at.session_state["lista_whatsapp"], [])

    # 2. Entra el dueño: no ve nada de Ana.
    _entrar(at, "clave-duenio-1")
    esperar("el dueño entró como admin", (at.session_state["nivel_usuario"],
                                          at.session_state["admin_nombre"]), ("admin", "duenio"))
    esperar("el dueño no ve el presupuesto de Ana", "carrito" in at.session_state
            and bool(at.session_state["carrito"]), False)

    # 2b. Ir a otra pantalla y volver no borra lo que se estaba haciendo (lo señaló una
    # revisión con Gemini): la caja de búsqueda volvía vacía, con los resultados de antes abajo.
    # Ver recordar_lo_elegido_al_cambiar_de_pantalla().
    at.session_state["pagina_actual"] = "🔍 Buscador"
    at.run()
    at.text_input(key="busqueda_input").set_value("W712/94")
    [b for b in at.button if "Buscar equivalencias" in b.label][0].click().run()
    at.session_state["pagina_actual"] = "📊 Estadísticas"
    at.run()
    at.radio(key="sub_stats").set_value("📌 Para pedir").run()
    for pagina in ("🗂️ Administrar", "🛠️ Modo Mecánico", "🔍 Buscador"):
        at.session_state["pagina_actual"] = pagina
        at.run()
    esperar("al volver al buscador, lo escrito sigue ahí",
            at.text_input(key="busqueda_input").value, "W712/94")
    at.session_state["pagina_actual"] = "📊 Estadísticas"
    at.run()
    esperar("y en Estadísticas, la solapa que estaba", at.radio(key="sub_stats").value,
            "📌 Para pedir")
    esperar("sin errores al ir y venir", [e.value for e in at.exception], [])

    # 2d. La ayuda de cada pantalla: UN «ℹ️ Cómo funciona» plegado arriba, con para qué sirve
    # la sección, la solapa y la ayuda de la pantalla adentro, y nada de eso a la vista. La
    # ayuda de una parte de más abajo se queda en su parte. Lo pidió el dueño: menos ruido, todo
    # plegado. Ver «LA AYUDA DE CADA PANTALLA» en logica/interfaz.py.
    def _ayudas():
        return [e for e in at.expander if e.label == ns["TITULO_DE_LA_AYUDA"]]

    _solapa = ns["SUB_DEPOSITO"][0]
    at.session_state["pagina_actual"] = "📦 Depósito"
    at.session_state["sub_deposito"] = _solapa
    at.run()
    _arriba = _ayudas()[0].markdown[0].value if _ayudas() and _ayudas()[0].markdown else ""
    esperar("depósito: una sola ayuda", len(_ayudas()), 1)
    esperar("con la sección, la solapa y la pantalla adentro",
            [ns["PARA_QUE_SIRVE"]["📦 Depósito"] in _arriba,
             ns["PARA_QUE_SIRVE_LA_SOLAPA"][_solapa] in _arriba,
             "Acá llega lo que el mostrador pide" in _arriba], [True, True, True])
    esperar("y en ningún otro lado", sum(ns["PARA_QUE_SIRVE_LA_SOLAPA"][_solapa] in x.value
                                         for x in list(at.caption) + list(at.markdown)), 1)
    esperar("plegada", _ayudas()[0].proto.expanded if _ayudas() else None, False)
    at.session_state["pagina_actual"] = "📊 Estadísticas"
    at.run()
    at.radio(key="sub_stats").set_value("📌 Para pedir").run()
    _de_una_parte = "Hace falta haber importado precios de una misma marca"
    esperar("la de una parte no sube arriba", _de_una_parte in _ayudas()[0].markdown[0].value, False)
    esperar("se queda en su parte", any(_de_una_parte in a.markdown[0].value
                                        for a in _ayudas()[1:] if a.markdown), True)
    esperar("sin errores con las ayudas", [e.value for e in at.exception], [])

    # 2c. Una importación que se corta a la mitad no deja nada: corre entera adentro de una
    # transacción (ver pantallas/cargar_excel.py). No tenía prueba. Se corta en la segunda fila.
    with open("corte.csv", "w", encoding="utf-8") as f:
        f.write("Codigo;Descripcion;Precio;Stock\nCORTE1;FILTRO UNO;100;1\n"
                "CORTE2;FILTRO DOS;200;2\nCORTE3;FILTRO TRES;300;3\n")
    _g = ns["poner_precio_y_stock_de_la_lista"].__globals__
    _original = _g["poner_precio_y_stock_de_la_lista"]
    _llamadas = []

    def _se_corta(*args, **kwargs):
        _llamadas.append(1)
        if len(_llamadas) == 2:
            raise RuntimeError("corte de prueba a mitad de la lista")
        return _original(*args, **kwargs)

    def _lo_que_hay():
        c = ns["c"]
        return tuple(c.execute(q).fetchone()[0] for q in (
            "SELECT COUNT(*) FROM productos WHERE codigo_clean LIKE 'CORTE%'",
            "SELECT COUNT(*) FROM importaciones", "SELECT COUNT(*) FROM historial_precios"))
    _antes = _lo_que_hay()
    _g["poner_precio_y_stock_de_la_lista"] = _se_corta
    at.session_state["pagina_actual"] = "📁 Cargar Excel"
    at.run()
    _ruta = [x for x in at.radio if "Subir archivo" in x.options][0]
    _ruta.set_value([o for o in _ruta.options if o != "Subir archivo"][0]).run()
    [t for t in at.text_input if "Ruta completa" in t.label][0].set_value(
        os.path.abspath("corte.csv")).run()
    at.text_input(key="nombre_prov_carga").set_value("PRUEBACORTE").run()
    [b for b in at.button if "Procesar e importar" in b.label][0].click().run()
    esperar("cortada a la mitad, no queda nada de la lista", (len(_llamadas), _lo_que_hay()),
            (2, _antes))
    _g["poner_precio_y_stock_de_la_lista"] = _original
    [b for b in at.button if "Procesar e importar" in b.label][0].click().run()
    esperar("y entera, entra entera", _lo_que_hay(), (3, _antes[1] + 1, _antes[2] + 3))
    esperar("sin errores al importar", [e.value for e in at.exception], [])
    # En la app de internet la ruta se leería en el servidor, no en el teléfono: no se ofrece.
    _en_la_nube = _g["corre_en_streamlit_cloud"]
    _g["corre_en_streamlit_cloud"] = lambda: True
    at.run()
    esperar("en la app de internet no se ofrece leer por ruta",
            [r.options for r in at.radio if "Subir archivo" in r.options], [])
    _g["corre_en_streamlit_cloud"] = _en_la_nube
    [b for b in at.button if b.label == "Salir"][0].click().run()

    # 3. Ana vuelve a entrar; mientras está adentro le cambian el rol, y después la desactivan.
    _entrar(at, "clave-ana-1")
    c = ns["c"]
    c.execute("UPDATE usuarios SET rol = 'admin' WHERE nombre = 'ana'")
    ns["conn"].commit()
    at.run()
    esperar("con el rol nuevo, el permiso nuevo", at.session_state["nivel_usuario"], "admin")
    c.execute("UPDATE usuarios SET rol = 'operador' WHERE nombre = 'ana'")
    ns["conn"].commit()
    at.run()
    esperar("y al revés: se le bajan los permisos", at.session_state["nivel_usuario"], "operador")
    c.execute("UPDATE usuarios SET activo = 0 WHERE nombre = 'ana'")
    ns["conn"].commit()
    at.run()
    esperar("desactivada, la sesión se cierra",
            "nivel_usuario" in at.session_state, False)
    esperar("y lo dice", any("ya no está activa" in w.value for w in at.warning), True)
    esperar("sin errores en pantalla", [e.value for e in at.exception], [])

    # 4. Un taller ve su portal y nada más, aunque la sesión diga que está en Administrar.
    ns["crear_mecanico"]("Taller Sesión", "clave-taller-sesion-1")
    taller = ns["c"].execute("SELECT id FROM mecanicos WHERE nombre = 'Taller Sesión'").fetchone()[0]
    # En una sesión nueva: la barra de un taller ya no tiene Administrar (ver
    # PAGINAS_ABIERTAS), y AppTest no deja poner a mano un valor que la barra no ofrece.
    at = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
    at.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
    at.session_state["nivel_usuario"] = "mecanico"
    at.session_state["admin_nombre"] = "Taller Sesión"
    at.session_state["mecanico_id"] = taller
    at.session_state["pagina_actual"] = "🗂️ Administrar"
    at.run()
    textos = " ".join(m.value for m in at.markdown)
    esperar("el taller ve su portal", "Portal de mecánico" in textos, True)
    esperar("y no la administración", any(x in textos for x in ("Cuentas corrientes de los talleres",
                                                              "Usuarios", "Backup")), False)
    esperar("ni las pestañas del negocio", [b.label for b in at.button if "Administrar" in b.label], [])
    esperar("sin errores", [e.value for e in at.exception], [])

    # 5. La venta a medio armar sobrevive a una recarga, que para la app es una sesión nueva
    # sobre la misma base: al entrar se avisa, 🧾 Ventas ofrece recuperarla —con la cantidad, el
    # precio y el cliente que tenía— y, terminada, no queda nada guardado. A otro no se le
    # ofrece, y la de ayer tampoco. Ver «LA VENTA Y EL PRESUPUESTO A MEDIO ARMAR, A SALVO DE UNA
    # RECARGA».
    c, conn = ns["c"], ns["conn"]
    for nombre in ("rita", "beto"):
        ns["crear_usuario"](nombre, f"clave-{nombre}-1", "operador")
    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('PRUEBA VENTA', 'PROVEEDOR')")
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio, "
              "stock) VALUES ('V100', 'V100', 'FILTRO', ?, 1000, 5)", (c.lastrowid,))
    pid = c.lastrowid
    conn.commit()
    ventas = ns["PAGINAS"][9]

    def sesion_nueva(clave, pagina=None):
        nueva = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
        nueva.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
        nueva.run()
        _entrar(nueva, clave)
        if pagina:
            nueva.session_state["pagina_actual"] = pagina
            nueva.run()
        return nueva

    def guardada(quien):
        return c.execute("SELECT cliente FROM ventas_a_medio_armar WHERE usuario = ?",
                         (quien,)).fetchone()

    def ofrecida(sesion):
        return ([b.label for b in sesion.button if b.label == "↩️ Recuperarla"],
                [t.value for t in sesion.toast if "venta a medio armar" in t.value])

    vta = sesion_nueva("clave-rita-1", ventas)
    vta.session_state["venta_items"] = [dict(ns["item_de_venta"](pid, 3), precio=900.0)]
    vta.session_state["venta_cliente"] = "Juan"
    vta.run()
    esperar("se guarda la venta a medio armar", tuple(guardada("rita") or ()), ("Juan",))
    vta = sesion_nueva("clave-rita-1")                       # recargó la página
    esperar("al entrar, el aviso", len(ofrecida(vta)[1]), 1)
    vta.session_state["pagina_actual"] = ventas
    vta.run()
    esperar("una sesión nueva no la borra antes de contestar", bool(guardada("rita")), True)
    if not ofrecida(vta)[0]:
        fallas.append("🧾 Ventas no ofrece recuperar la venta a medio armar")
        return fallas
    [b for b in vta.button if b.label == "↩️ Recuperarla"][0].click().run()
    esperar("recuperada con su cantidad, su precio y el cliente",
            ([(x["producto_id"], x["cantidad"], x["precio"])
              for x in vta.session_state["venta_items"]], vta.session_state["venta_cliente"]),
            ([(pid, 3, 900.0)], "Juan"))
    otro = sesion_nueva("clave-beto-1", ventas)
    esperar("a otro no se le ofrece", ofrecida(otro), ([], []))
    [b for b in vta.button if b.label in ("✅ Terminar la venta", "📤 Mandar a la caja")][0] \
        .click().run()
    esperar("terminada, no queda guardada", guardada("rita"), None)
    c.execute("""INSERT INTO ventas_a_medio_armar (usuario, items, cliente, guardada)
                 VALUES ('rita', ?, '', datetime('now', 'localtime', '-1 day'))""",
              (f'[{{"producto_id": {pid}, "cantidad": 1, "precio": 1}}]',))
    conn.commit()
    esperar("la de ayer no se ofrece", ofrecida(sesion_nueva("clave-rita-1", ventas)), ([], []))
    # Y el presupuesto del Buscador, igual: lo destildado sigue destildado. Recuperar la venta
    # no lo borra: va aparte.
    presu = sesion_nueva("clave-rita-1", ns["PAGINAS"][0])
    presu.session_state["carrito"] = {pid: {"codigo": "V100", "marca": "PRUEBA VENTA",
                                            "descripcion": "FILTRO", "precio": 950,
                                            "cantidad": 2, "se_lleva": False}}
    presu.run()
    presu = sesion_nueva("clave-rita-1")                     # recargó la página
    esperar("al entrar, el aviso del presupuesto",
            len([t for t in presu.toast if "presupuesto a medio armar" in t.value]), 1)
    presu.session_state["pagina_actual"] = ns["PAGINAS"][0]
    presu.run()
    _rec = [b for b in presu.button if b.label == "↩️ Recuperarlo"]
    if not _rec:
        fallas.append("el 🔍 Buscador no ofrece recuperar el presupuesto a medio armar")
        return fallas
    _rec[0].click().run()
    esperar("el presupuesto recuperado, con su cantidad, su precio y lo destildado",
            {k: dict(v) for k, v in presu.session_state["carrito"].items()},
            {pid: {"codigo": "V100", "marca": "PRUEBA VENTA", "descripcion": "FILTRO",
                   "precio": 950, "cantidad": 2, "se_lleva": False}})
    esperar("sin errores en el presupuesto", [e.value for e in presu.exception], [])
    esperar("sin errores en la venta", [e.value for s_ in (vta, otro) for e in s_.exception], [])

    # 6. 🔗 Equivalencias sugeridas: cada lista arranca analizándose ENTERA —la tanda se fijaba
    # con la primera que se abría y al pasar al barrido quedaba en 400 de 6.586—, y lo que sale
    # del análisis (el plan, los abanicos, los grupos por motivo) no se vuelve a armar en cada
    # toque: con el barrido entero eran 899 ms por tildar una casilla.
    for nombre_l in ("LISTA UNO", "LISTA DOS"):
        c.execute("INSERT INTO marcas (nombre, tipo) VALUES (?, 'PROVEEDOR')", (nombre_l,))
    _m1, _m2 = [r[0] for r in c.execute("SELECT id FROM marcas WHERE nombre IN ('LISTA UNO', "
                                        "'LISTA DOS') ORDER BY nombre DESC")]
    for lote_s, cuantos_s, fecha_s in (("GRANDE · 01/10", 450, "2026-10-01"),
                                       ("CHICA · 02/10", 260, "2026-10-02")):
        for i in range(cuantos_s):
            ids_s = []
            for m_s, pref in ((_m1, "U"), (_m2, "D")):
                cod_s = f"{pref}{lote_s[:1]}{i}"
                c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
                          "VALUES (?, ?, ?, ?)", (cod_s, cod_s, f"FILTRO DE ACEITE MOTOR {i}", m_s))
                ids_s.append(c.lastrowid)
            c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, "
                      "lote, fecha) VALUES (?, ?, 'x', ?, ?)", (*sorted(ids_s), lote_s, fecha_s))
    conn.commit()
    rev = sesion_nueva("clave-duenio-1", [p for p in ns["PAGINAS"] if "Estadísticas" in p][0])
    rev.session_state["sub_stats"] = "🔗 Equivalencias sugeridas"
    rev.run()
    esperar("la primera lista, entera", rev.session_state["cuantos_pendientes"], 400)
    _sel = [s_ for s_ in rev.selectbox if s_.key == "lote_en_revision"][0]
    _sel.set_value([o for o in _sel.options if o.startswith("GRANDE")][0]).run()
    esperar("al pasar a la grande, también entera",
            (rev.session_state["cuantos_pendientes"],
             any("Analizados 450 de 450" in str(x.value) for x in rev.caption)), (1000, True))
    _g = ns["plan_de_la_lista"].__globals__
    _plan_original, _veces_plan = _g["plan_de_la_lista"], []
    _g["plan_de_la_lista"] = lambda *a, **k: _veces_plan.append(1) or _plan_original(*a, **k)
    try:
        rev.run()
        rev.run()
    finally:
        _g["plan_de_la_lista"] = _plan_original
    esperar("lo que sale del análisis no se rearma en cada toque", len(_veces_plan), 0)
    esperar("sin errores en la revisión", [e.value for e in rev.exception], [])

    # 7. 🕸️ Unidos a varias piezas distintas de una misma lista: se buscan, se mira uno y se le
    # corta un vínculo, que queda anotado como rechazado (ver unidos_a_piezas_distintas()).
    for nombre_l in ("HUB LISTA", "HUB OTRA"):
        c.execute("INSERT INTO marcas (nombre, tipo) VALUES (?, 'PROVEEDOR')", (nombre_l,))
    _ml, _mo = [r[0] for r in c.execute("SELECT id FROM marcas WHERE nombre IN ('HUB LISTA', "
                                        "'HUB OTRA') ORDER BY nombre")]
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) VALUES "
              "('U-1', 'U1', 'SONDA LAMBDA UNIVERSAL', ?)", (_mo,))
    _hub = c.lastrowid
    _piezas_l = []
    for cod_l, desc_l in (("H100", "SONDA LAMBDA FIAT SPORTAGE"), ("H200", "SONDA LAMBDA RENAULT KANGOO"),
                          ("H300", "SONDA LAMBDA FORD KA ZETEC")):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
                  "VALUES (?, ?, ?, ?)", (cod_l, cod_l, desc_l, _ml))
        _piezas_l.append(c.lastrowid)
        c.execute("INSERT INTO equivalencias (producto_a_id, producto_b_id, lote, confianza) "
                  "VALUES (?, ?, 'BARRIDO (automático) · 25/09', 84)", tuple(sorted((_hub, c.lastrowid))))
    conn.commit()
    adm = sesion_nueva("clave-duenio-1", [p for p in ns["PAGINAS"] if "Administrar" in p][0])
    adm.session_state["sub_admin"] = ns["SUB_ADMIN"][4]
    adm.session_state["sub_mantenimiento"] = ns["GRUPOS_MANTENIMIENTO"][1]
    adm.run()
    [b for b in adm.button if b.key == "btn_unidos_a_piezas"][0].click().run()
    esperar("los encuentra", any("1 producto(s)" in w.value for w in adm.warning), True)
    _corte = [m for m in adm.multiselect if str(m.key).startswith("cortar_unido_")][0]
    _corte.set_value([_piezas_l[1]]).run()
    [b for b in adm.button if b.key == "btn_cortar_unido"][0].click().run()
    _par = tuple(sorted((_hub, _piezas_l[1])))
    esperar("cortado y anotado como rechazado",
            (c.execute("SELECT COUNT(*) FROM equivalencias WHERE producto_a_id = ? AND "
                       "producto_b_id = ?", _par).fetchone()[0],
             (c.execute("SELECT decision FROM equivalencias_revisadas WHERE producto_a_id = ? AND "
                        "producto_b_id = ?", _par).fetchone() or [None])[0],
             adm.session_state["unidos_a_piezas"]), (0, "rechazada", []))
    esperar("sin errores en la limpieza", [e.value for e in adm.exception], [])
    return fallas


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_sesion_")
    os.chdir(carpeta)
    sys.path.insert(0, RAIZ)
    try:
        fallas = probar()
        for f in fallas:
            print("   ✗", f)
        print("✅ sesión: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(RAIZ)
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

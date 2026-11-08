"""Pruebas de la caja aparte: la venta que manda el vendedor espera en la caja, con su cartel,
hasta que se cobra (forma de pago, cuotas, descuento) o se pone a cuenta (con el límite).

Uso:
    python3 pruebas/pruebas_de_la_caja.py

Ver «LA CAJA APARTE» en logica/ventas.py. Corre en una carpeta temporal: nunca toca la base de
trabajo.
"""
import os
import shutil
import sys
import tempfile


def _cargar_la_logica(carpeta):
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, raiz)
    os.chdir(carpeta)
    import logica
    return logica


def probar(L):
    ns = L.todo_lo_de_la_logica()
    c, conn, st = ns["c"], ns["conn"], ns["st"]
    g = ns["cerrar_venta"].__globals__
    fallas = []

    def esperar(nombre, real, esperado):
        if real != esperado:
            fallas.append(f"{nombre}: dio {real!r}, se esperaba {esperado!r}")

    def uno(sql, *args):
        fila = c.execute(sql, args).fetchone()
        return fila[0] if fila else None

    st.session_state["admin_nombre"], st.session_state["nivel_usuario"] = "ana", "operador"
    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('PRUEBA', 'PROVEEDOR')")
    marca = c.lastrowid
    ids = {}
    for codigo, precio, stock in (("A1", 1000, 10), ("B1", 2500, 10), ("C1", 333, None)):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio, "
                  "stock) VALUES (?, ?, 'FILTRO', ?, ?, ?)", (codigo, codigo, marca, precio, stock))
        ids[codigo] = c.lastrowid
    conn.commit()
    item = lambda codigo, n=1: dict(ns["item_de_venta"](ids[codigo], n))
    stock = lambda codigo: uno("SELECT stock FROM productos WHERE id = ?", ids[codigo])
    ns["crear_mecanico"]("Taller Norte", "clave-norte-1")
    taller = uno("SELECT id FROM mecanicos WHERE nombre = 'Taller Norte'")
    g_adentro = g["_nivel_de_quien_esta_adentro"]
    g["_nivel_de_quien_esta_adentro"] = lambda: "admin"
    ns["configurar_cuenta_de_taller"](taller, 20000, 15, False, descuento=10)
    g["_nivel_de_quien_esta_adentro"] = g_adentro
    saldo = lambda: ns["estado_de_cuenta"](taller)["saldo"]

    # 1. La caja aparte está prendida de entrada.
    esperar("prendida de entrada", ns["caja_aparte"](), True)

    # 2. Mandada a la caja: el stock baja ya (se la lleva), queda esperando sin forma de pago,
    # y el cartel dice quién vendió, a qué cuenta, cuánto y a qué hora.
    v1, _ = ns["cerrar_venta"]([item("A1", 2), item("B1")], "Juan", a_la_caja=True)
    v2, _ = ns["cerrar_venta"]([item("A1")], mecanico_id=taller, a_la_caja=True)
    esperando = ns["ventas_a_cobrar"]()
    cartel = ns["el_cartel_de"](esperando[0])
    esperar("esperando en la caja",
            ([v["id"] for v in esperando], stock("A1"),
             uno("SELECT forma_de_pago || '/' || cobrada FROM ventas WHERE id = ?", v1),
             esperando[1]["cuenta"], "vendió ana" in cartel, "para Juan, de Mostrador" in cartel,
             "$4.500" in cartel, esperando[0]["hora"] in cartel and len(esperando[0]["hora"]) == 5,
             "para Taller Norte" in ns["el_cartel_de"](esperando[1])),
            ([v1, v2], 7, "/0", "Taller Norte", True, True, True, True, True))
    caja = ns["cierre_de_caja"]()
    esperar("lo que espera no cuenta en el cierre",
            (caja["ventas"], caja["total"], caja["a_cobrar"], caja["total_a_cobrar"]),
            (0, 0.0, 2, 5500.0))

    # 3. F10: cómo pagó, las cuotas y el descuento; lo que no sirve, no.
    cobrar = ns["cobrar_venta"]
    esperar("cobrar mal", [cobrar(v1, "Cheque")[0], cobrar(v1, "Tarjeta de crédito", 5)[0],
                           cobrar(v1, "Efectivo", 1, 60)[0], cobrar(v1, "Efectivo", 1, "mucho")[0],
                           cobrar(v1, "Efectivo", 1, -1)[0],
                           uno("SELECT cobrada FROM ventas WHERE id = ?", v1)],
            [False, False, False, False, False, 0])
    previsto = ns["total_con_descuento"](v1, 10)
    ok, texto = cobrar(v1, "Tarjeta de crédito", 3, 10)
    esperar("cobrada con crédito en 3 cuotas y 10% de descuento",
            (ok, previsto, uno("SELECT total FROM ventas WHERE id = ?", v1),
             uno("SELECT total_de_lista FROM ventas WHERE id = ?", v1),
             [r[0] for r in c.execute("SELECT precio FROM ventas_items WHERE venta_id = ? "
                                      "ORDER BY id", (v1,))],
             uno("SELECT forma_de_pago || '/' || cuotas || '/' || descuento || '/' || cobrada_por "
                 "FROM ventas WHERE id = ?", v1),
             "3 cuotas" in texto and "10% de descuento" in texto, cobrar(v1, "Efectivo")[0]),
            (True, 4050.0, 4050.0, 4500.0, [900.0, 2250.0], "Tarjeta de crédito/3/10.0/ana", True,
             False))
    comprobante = ns["texto_del_comprobante"](v1)
    caja = ns["cierre_de_caja"]()
    esperar("el comprobante y el cierre",
            ("Descuento 10% (era $4.500)" in comprobante,
             "TOTAL: $4.050 (Tarjeta de crédito, 3 cuotas)" in comprobante,
             "PENDIENTE" in ns["texto_del_comprobante"](v2),
             caja["ventas"], caja["total"], caja["por_forma"], caja["a_cobrar"]),
            (True, True, True, 1, 4050.0, [("Tarjeta de crédito", 1, 4050.0)], 1))

    # 4. Lo que espera no se devuelve: no se cobró. Cobrada, sí, con el precio del descuento.
    item_v1 = uno("SELECT id FROM ventas_items WHERE venta_id = ? ORDER BY id", v1)
    item_v2 = uno("SELECT id FROM ventas_items WHERE venta_id = ?", v2)
    ok_v2, texto_v2 = ns["devolver_de_una_venta"](item_v2, 1, "medida")
    ok, texto = ns["devolver_de_una_venta"](item_v1, 1, "medida")
    esperar("devolver: lo que espera no; lo cobrado, al precio cobrado",
            (ok_v2, "todavía no se cobró" in texto_v2, ok, "$900" in texto,
             uno("SELECT importe FROM ventas_devoluciones WHERE venta_item_id = ?", item_v1)),
            (False, True, True, True, 900.0))

    # 5. F11: a la cuenta de la venta, con el descuento de la cuenta y su plazo.
    ok, texto = ns["poner_a_cuenta"](v2)
    mov = c.execute("SELECT importe, concepto, vence FROM movimientos_de_cuenta WHERE mecanico_id = ?",
                    (taller,)).fetchone()
    from datetime import date, timedelta
    esperar("a cuenta del taller",
            (ok, uno("SELECT forma_de_pago || '/' || descuento || '/' || total FROM ventas "
                     "WHERE id = ?", v2), tuple(mov), saldo(),
             "a la cuenta de Taller Norte" in texto,
             "a la cuenta de Taller Norte" in ns["texto_del_comprobante"](v2)),
            (True, "A cuenta/10.0/900.0",
             (900.0, f"Venta #{v2}", (date.today() + timedelta(days=15)).isoformat()), 900.0, True,
             True))
    # Devolverla: se le acredita a la cuenta, no sale del cajón.
    ok, texto = ns["devolver_de_una_venta"](item_v2, 1, "medida")
    esperar("devolver de una venta a cuenta: se le acredita", (ok, "se le acredita" in texto, saldo()),
            (True, True, 0.0))

    # 6. Mostrador, a cuenta: hay que decir de quién. Y el límite: si no entra, no pasa nada
    # (ni el descuento): sigue esperando.
    v3, _ = ns["cerrar_venta"]([item("B1", 10)], a_la_caja=True)
    esperar("Mostrador sin cuenta", ns["poner_a_cuenta"](v3)[1], "Es de Mostrador: elegí a qué cuenta va.")
    ok, texto = ns["poner_a_cuenta"](v3, taller)
    esperar("no entra en el límite: sigue esperando, sin tocar nada",
            (ok, texto.startswith(ns["PASA_EL_LIMITE"]),
             uno("SELECT COALESCE(cobrada, 1) FROM ventas WHERE id = ?", v3),
             uno("SELECT total FROM ventas WHERE id = ?", v3),
             uno("SELECT precio FROM ventas_items WHERE venta_id = ?", v3),
             uno("SELECT COUNT(*) FROM movimientos_de_cuenta WHERE mecanico_id = ?", taller)),
            (False, True, 0, 25000.0, 2500.0, 2))
    # Con menos descuento de lo que pide la cuenta, o más del tope, se dice.
    esperar("descuento a cuenta de más", ns["poner_a_cuenta"](v3, taller, 95)[0], False)

    # 7. Anular una venta a cuenta anula el cargo; la que espera, se anula como cualquiera.
    v4, _ = ns["cerrar_venta"]([item("A1")], mecanico_id=taller, a_la_caja=True)
    ns["poner_a_cuenta"](v4, descuento=0)
    antes = saldo()
    g["_nivel_de_quien_esta_adentro"] = lambda: "admin"
    try:
        ok, _ = ns["anular_venta"](v4)
        ok3, _ = ns["anular_venta"](v3)
    finally:
        g["_nivel_de_quien_esta_adentro"] = g_adentro
    esperar("anular la venta a cuenta anula el cargo",
            (ok, antes, saldo(), ok3, [v["id"] for v in ns["ventas_a_cobrar"]()], stock("B1")),
            (True, 1000.0, 0.0, True, [], 9))

    # 8. El día de la caja es el día que se cobró.
    v5, _ = ns["cerrar_venta"]([item("C1", 3)], a_la_caja=True)
    c.execute("UPDATE ventas SET fecha = datetime('now', 'localtime', '-1 day') WHERE id = ?", (v5,))
    conn.commit()
    ayer = (date.today() - timedelta(days=1)).isoformat()
    antes_ayer = ns["cierre_de_caja"](ayer)["a_cobrar"]
    cobrar(v5, "Efectivo")
    esperar("vendida ayer, cobrada hoy: cuenta hoy",
            (antes_ayer, ns["cierre_de_caja"](ayer)["a_cobrar"],
             v5 in [v["id"] for v in ns["ventas_del_dia"]()], ns["efectivo_esperado"](), stock("C1")),
            (1, 0, True, 999.0, None))

    # 9. Sin la caja aparte, el vendedor cobra al terminar: como antes.
    g["_nivel_de_quien_esta_adentro"] = lambda: "admin"
    try:
        ns["cambiar_caja_aparte"](False)
    finally:
        g["_nivel_de_quien_esta_adentro"] = g_adentro
    v6, _ = ns["cerrar_venta"]([item("A1")], forma_de_pago="Transferencia")
    esperar("sin caja aparte", (ns["caja_aparte"](), uno("SELECT cobrada || forma_de_pago FROM ventas "
                                                        "WHERE id = ?", v6)),
            (False, "1Transferencia"))

    # 9b. Débito no tiene cuotas aunque se digan; crédito en un pago se lee sin «1 cuotas»; a
    # una cuenta desactivada, no.
    v_deb, _ = ns["cerrar_venta"]([item("A1")], a_la_caja=True)
    cobrar(v_deb, "Tarjeta de débito", 3)
    v_off, _ = ns["cerrar_venta"]([item("A1")], mecanico_id=taller, a_la_caja=True)
    c.execute("UPDATE mecanicos SET activo = 0 WHERE id = ?", (taller,))
    conn.commit()
    esperar("débito, crédito en un pago y una cuenta desactivada",
            (uno("SELECT cuotas FROM ventas WHERE id = ?", v_deb),
             ns["como_se_pago"]({"forma_de_pago": "Tarjeta de crédito", "cuotas": 1}),
             ns["poner_a_cuenta"](v_off)[1]),
            (1, "Tarjeta de crédito", "Esa cuenta no existe o está desactivada."))
    c.execute("UPDATE mecanicos SET activo = 1 WHERE id = ?", (taller,))
    conn.commit()

    # 9c. Lo de arriba de la caja: el cajón, otros medios, lo puesto a cuenta (que no es plata
    # que entró) y lo que espera.
    v_a, _ = ns["cerrar_venta"]([item("A1")], mecanico_id=taller, a_la_caja=True)
    ns["poner_a_cuenta"](v_a)
    esperar("lo de arriba de la caja", ns["resumen_de_la_caja"](),
            {"efectivo": 999.0, "otros_medios": 5150.0, "a_cuenta": 900.0, "ventas": 6,
             "esperando": 1, "total_esperando": 1000.0})

    # 9d. Lo que le avisa la app a quien vende: su venta cobrada o puesta a cuenta por el
    # cajero, y lo que pidió al depósito, entregado o que no había. Lo que hizo él mismo, no.
    # Ver novedades_de().
    nov = ns["novedades_de"]
    desde = uno("SELECT datetime('now', 'localtime', '-1 second')")
    v_n1, _ = ns["cerrar_venta"]([item("A1")], "Juan", a_la_caja=True)
    v_n2, _ = ns["cerrar_venta"]([item("B1")], mecanico_id=taller, a_la_caja=True)
    v_n3, _ = ns["cerrar_venta"]([item("A1")], "Pepe", a_la_caja=True)
    pedidos = []
    for codigo in ("A1", "B1"):
        ns["pedir_al_deposito"](ids[codigo], 1)
        pedidos.append(uno("SELECT MAX(id) FROM pedidos_deposito"))
    esperar("sin novedades mientras nadie hizo nada", nov("ana", desde), [])
    cobrar(v_n3, "Efectivo")                                   # la cobró ella misma
    st.session_state["admin_nombre"] = "beto"
    cobrar(v_n1, "Tarjeta de débito")
    ns["poner_a_cuenta"](v_n2)
    ns["entregar_pedido"](pedidos[0], "depo")
    ns["no_hay_en_el_deposito"](pedidos[1], "depo")
    st.session_state["admin_nombre"] = "ana"
    textos = [t for _, _, t in nov("ana", desde)]
    esperar("lo que terminó otro, una vez cada cosa",
            (len(textos), any(f"Se cobró tu venta #{v_n1}" in t for t in textos),
             any(f"Tu venta #{v_n2} quedó a cuenta de Taller Norte" in t for t in textos),
             any("Ya salió del depósito: 1× PRUEBA A1 (lo dio depo)" in t for t in textos),
             any("El depósito no lo encontró: 1× PRUEBA B1" in t for t in textos),
             any(f"#{v_n3}" in t for t in textos)),
            (4, True, True, True, True, False))
    esperar("al cajero no le llega lo de ana", nov("beto", desde), [])
    esperar("lo de antes de entrar, no", nov("ana", "2999-01-01 00:00:00"), [])

    # 9e. Lo que corre solo, cada pocos segundos (la caja cada 5, los avisos cada 20 por cada
    # vendedor), va por un índice que achica: con un COALESCE en el WHERE, la base recorría
    # todas las ventas de la historia a cada vuelta; y por (cobrada, anulada), que son casi
    # todas, tampoco achicaba. Se mira el plan de cada consulta que hacen.
    def pasos(hacer):
        hechas = []
        conn.conexion_real().set_trace_callback(hechas.append)
        hacer()
        conn.conexion_real().set_trace_callback(None)
        return [paso for sql in hechas if sql.lstrip().upper().startswith("SELECT")
                for *_, paso in c.execute("EXPLAIN QUERY PLAN " + sql).fetchall()]
    _caja, _avisos = pasos(ns["ventas_a_cobrar"]), pasos(lambda: nov("ana", desde))
    esperar("lo que corre solo, sin recorrer tablas enteras",
            [p for p in _caja + _avisos if p.startswith("SCAN")], [])
    esperar("los avisos, por quién vendió o pidió",
            [i for i in ("idx_ventas_de_quien", "idx_pedidos_deposito_de_quien")
             if not any(i in p for p in _avisos)], [])

    # 10. Quién puede: cobrar y poner a cuenta, un empleado; prender o apagar la caja, el
    # administrador.
    originales = (g["_nivel_de_quien_esta_adentro"], g["hay_claves_configuradas"])
    g["hay_claves_configuradas"] = lambda: True
    try:
        for nivel, empleado, admin in (("", False, False), ("mecanico", False, False),
                                       ("operador", True, False), ("admin", True, True)):
            g["_nivel_de_quien_esta_adentro"] = lambda n=nivel: n
            resultado = []
            for funcion, args in ((ns["cobrar_venta"], (999999, "Efectivo")),
                                  (ns["poner_a_cuenta"], (999999,)),
                                  (ns["cambiar_caja_aparte"], (True,))):
                try:
                    funcion(*args)
                    resultado.append(True)
                except PermissionError:
                    resultado.append(False)
            esperar(f"nivel «{nivel or 'invitado'}»: cobrar, a cuenta, prender la caja", resultado,
                    [empleado, empleado, admin])
    finally:
        g["_nivel_de_quien_esta_adentro"], g["hay_claves_configuradas"] = originales

    # QUE UNA VENTA NO SE GRABE POR ACCIDENTE (ver esa sección en logica/ventas.py): la misma
    # venta enseguida se reconoce, y la suya sin cobrar se deshace y vuelve armada.
    st.session_state["admin_nombre"], st.session_state["nivel_usuario"] = "ana", "operador"
    _it = [item("A1", 2)]
    _stock_a = stock("A1")
    v_r, _ = ns["cerrar_venta"](_it, a_la_caja=True)
    esperar("la misma venta, enseguida, se reconoce",
            (ns["venta_igual_reciente"](_it) or {}).get("id"), v_r)
    esperar("con otra cantidad, otra cuenta u otra persona, no",
            (ns["venta_igual_reciente"]([item("A1", 3)]),
             ns["venta_igual_reciente"](_it, mecanico_id=taller),
             ns["venta_igual_reciente"](_it, usuario="pepe")), (None, None, None))
    esperar("la suya, esperando en la caja: la puede deshacer",
            ns["puede_deshacer_su_venta"](v_r)[0], True)
    st.session_state["admin_nombre"] = "beto"
    esperar("la de otro, no", (ns["puede_deshacer_su_venta"](v_r)[0],
                               ns["deshacer_mi_venta"](v_r)[0]), (False, False))
    st.session_state["admin_nombre"] = "ana"
    ok_d, _, items_d = ns["deshacer_mi_venta"](v_r)
    esperar("deshecha: anulada, el stock vuelve, y vuelve armada con su cantidad",
            (ok_d, uno("SELECT anulada FROM ventas WHERE id = ?", v_r), stock("A1") - _stock_a,
             [(x["producto_id"], x["cantidad"], x["precio"]) for x in items_d]),
            (True, 1, 0, [(ids["A1"], 2, 1000.0)]))
    esperar("anulada, ya no cuenta como repetida", ns["venta_igual_reciente"](_it), None)
    # Cobrada no: deshacerla es sacar plata del cierre. De hace más de diez minutos, tampoco.
    v_c, _ = ns["cerrar_venta"](_it, forma_de_pago="Efectivo")
    v_v, _ = ns["cerrar_venta"]([item("B1")], a_la_caja=True)
    c.execute("UPDATE ventas SET fecha = datetime('now', 'localtime', '-11 minutes') WHERE id = ?",
              (v_v,))
    conn.commit()
    esperar("cobrada o vieja, la deshace solo el administrador",
            (ns["puede_deshacer_su_venta"](v_c)[0], ns["puede_deshacer_su_venta"](v_v)[0]),
            (False, False))
    st.session_state["nivel_usuario"] = "admin"
    esperar("el administrador, siempre", ns["puede_deshacer_su_venta"](v_v)[0], True)
    # Anotada «en el futuro» (si cambia el reloj del servidor): ni reciente ni para deshacer.
    st.session_state["nivel_usuario"] = "operador"
    v_fut, _ = ns["cerrar_venta"]([item("C1", 2)], a_la_caja=True)
    c.execute("UPDATE ventas SET fecha = datetime('now', 'localtime', '+3 hours') WHERE id = ?",
              (v_fut,))
    conn.commit()
    esperar("del futuro: ni repetida ni para deshacer",
            (ns["venta_igual_reciente"]([item("C1", 2)]), ns["puede_deshacer_su_venta"](v_fut)[0]),
            (None, False))
    st.session_state["nivel_usuario"] = "admin"

    # El freno de las contraseñas no traba la entrada si el último intento quedó «adelante» (si
    # cambia el reloj del servidor).
    _g_b = ns["_segundos_de_espera_por_intentos"].__globals__
    _cfg_antes = (ns["obtener_config"]("login_fallidos", "0"),
                  ns["obtener_config"]("login_ultimo_fallo", ""))
    ns["guardar_config"]("login_fallidos", "9")
    ns["guardar_config"]("login_ultimo_fallo", (ns["datetime"].now() + ns["timedelta"](hours=3))
                         .strftime("%Y-%m-%d %H:%M:%S"))
    esperar("el freno nunca espera más que su máximo",
            ns["_segundos_de_espera_por_intentos"]() <= _g_b["ESPERA_MAXIMA_POR_INTENTOS"] + 1, True)
    ns["guardar_config"]("login_fallidos", _cfg_antes[0])
    ns["guardar_config"]("login_ultimo_fallo", _cfg_antes[1])

    # CORREGIR UN COBRO (ver esa sección en logica/ventas.py): la forma de pago equivocada, o la
    # venta vuelta a la caja para cobrarla bien.
    st.session_state["nivel_usuario"] = "operador"
    _forma = lambda v: uno("SELECT forma_de_pago FROM ventas WHERE id = ?", v)
    _efectivo_antes = ns["efectivo_esperado"]()
    v_f, _ = ns["cerrar_venta"]([item("B1", 2)], a_la_caja=True)
    ns["cobrar_venta"](v_f, "Efectivo")
    ok_f, texto_f = ns["cambiar_como_se_pago"](v_f, "Transferencia")
    esperar("cambió cómo pagó: el monto igual, y el cajón ya no la espera",
            (ok_f, _forma(v_f), uno("SELECT total FROM ventas WHERE id = ?", v_f),
             ns["efectivo_esperado"]() - _efectivo_antes, "antes, Efectivo" in texto_f),
            (True, "Transferencia", 5000.0, 0.0, True))
    esperar("lo mismo otra vez no hace nada, y a cuenta no se elige acá",
            (ns["cambiar_como_se_pago"](v_f, "Transferencia")[0],
             ns["cambiar_como_se_pago"](v_f, "A cuenta")[0]), (False, False))
    ns["cambiar_como_se_pago"](v_f, "Tarjeta de crédito", 3)
    esperar("con cuotas", (_forma(v_f), uno("SELECT cuotas FROM ventas WHERE id = ?", v_f)),
            ("Tarjeta de crédito", 3))
    # Cobrada con un descuento equivocado: vuelve a la caja como estaba, y se cobra bien.
    v_d, _ = ns["cerrar_venta"]([item("A1", 3)], a_la_caja=True)
    ns["cobrar_venta"](v_d, "Efectivo", descuento=10)
    ok_d2, _ = ns["volver_a_la_caja"](v_d)
    esperar("vuelta a la caja: esperando, sin descuento, con el total de antes",
            (ok_d2, uno("SELECT cobrada FROM ventas WHERE id = ?", v_d),
             uno("SELECT descuento FROM ventas WHERE id = ?", v_d),
             uno("SELECT total FROM ventas WHERE id = ?", v_d),
             uno("SELECT precio FROM ventas_items WHERE venta_id = ?", v_d)),
            (True, 0, 0, 3000.0, 1000.0))
    esperar("y se cobra bien", ns["cobrar_venta"](v_d, "Efectivo", descuento=5)[0], True)
    # A cuenta por error: acá no se cambia la forma; vuelta a la caja, el cargo se anula.
    v_k, _ = ns["cerrar_venta"]([item("A1")], mecanico_id=taller, a_la_caja=True)
    _saldo_k = saldo()
    ns["poner_a_cuenta"](v_k)
    esperar("a cuenta: no se cambia la forma de pago desde acá",
            ns["cambiar_como_se_pago"](v_k, "Efectivo")[0], False)
    ns["volver_a_la_caja"](v_k)
    esperar("vuelta a la caja: el cargo de la cuenta, anulado",
            (saldo() - _saldo_k, uno("SELECT movimiento_id FROM ventas WHERE id = ?", v_k)),
            (0.0, None))
    # Lo de otro día, solo el administrador; con devoluciones, nadie.
    c.execute("UPDATE ventas SET cobrada_en = datetime('now', 'localtime', '-2 days') WHERE id = ?",
              (v_f,))
    conn.commit()
    _de_otro_dia = ns["puede_corregir_el_cobro"](v_f)
    st.session_state["nivel_usuario"] = "admin"
    esperar("de otro día: el empleado no, el administrador sí",
            (_de_otro_dia[0], ns["puede_corregir_el_cobro"](v_f)[0]), (False, True))
    ok_dv, _ = ns["devolver_de_una_venta"](
        uno("SELECT id FROM ventas_items WHERE venta_id = ?", v_d), 1, "medida")
    esperar("con devoluciones, nadie", (ok_dv, ns["puede_corregir_el_cobro"](v_d)[0]), (True, False))
    esperar("lo corregido queda a la vista, con quién",
            sorted((x["venta"], x["quien"]) for x in ns["cobros_corregidos"]()),
            sorted([(str(v_f), "ana")] * 2 + [(str(v_d), "ana"), (str(v_k), "ana")]))
    esperar("y la campanita se lo dice al administrador",
            any("se corrigieron 4 cobro" in p["titulo"] and p.get("solo_admin")
                for p in ns["diagnostico_de_salud"]()), True)

    # LA HORA DE ACÁ (ver esa sección en logica/base.py): se guarda en UTC y se muestra —y se
    # corta el día— en la de Argentina. Lo vendido a las 22:30 de acá es la 01:30 UTC del día
    # siguiente: iba a la caja de mañana, con la hora «01:30».
    import time as _t
    esperar("se guarda en UTC: Python y SQLite en la misma hora",
            (_t.strftime("%z"), uno("SELECT datetime('now', 'localtime') = datetime('now')")),
            ("+0000", 1))
    _diferencia = (ns["ahora_aca"]() - ns["datetime"].now()).total_seconds()
    esperar("ahora_aca(): tres horas menos", round(_diferencia / 3600), -3)
    esperar("fecha_legible(): con hora, la de acá; una fecha sola, tal cual",
            [ns["fecha_legible"](x) for x in ("2026-11-08 22:30:00", "2026-11-09 01:30",
                                              "2026-11-08")],
            ["08/11/2026 19:30", "08/11/2026 22:30", "08/11/2026"])
    st.session_state["admin_nombre"], st.session_state["nivel_usuario"] = "ana", "operador"
    v_noche, _ = ns["cerrar_venta"]([item("A1")], a_la_caja=True)
    ns["cobrar_venta"](v_noche, "Efectivo")
    c.execute("UPDATE ventas SET fecha = '2026-03-11 01:20:00', cobrada_en = '2026-03-11 01:30:00' "
              "WHERE id = ?", (v_noche,))
    conn.commit()
    _del_10 = {v["id"]: v["hora"] for v in ns["ventas_del_dia"]("2026-03-10")}
    _del_11 = {v["id"] for v in ns["ventas_del_dia"]("2026-03-11")}
    esperar("cobrada a las 22:30 de acá: en la caja de ese día, con su hora de acá",
            (_del_10.get(v_noche), v_noche in _del_11), ("22:20", False))
    esperar("y en el cierre de ese día", ns["cierre_de_caja"]("2026-03-10")["ventas"] >= 1, True)
    esperar("la hora corta, en la de acá",
            ns["hora_corta_aca"]("2026-03-11 01:30:00"), "10/03 22:30")
    for k in ("admin_nombre", "nivel_usuario"):
        st.session_state.pop(k, None)
    return fallas


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_caja_")
    try:
        fallas = probar(_cargar_la_logica(carpeta))
        for f in fallas:
            print("   ✗", f)
        print("✅ caja: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

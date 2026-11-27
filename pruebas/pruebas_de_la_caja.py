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
             (900.0, f"Venta #{v2}", (ns["hoy_aca"]() + timedelta(days=15)).isoformat()), 900.0, True,
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
    # El día de acá (ver «LA HORA DE ACÁ»): con date.today(), entre las 21 y las 24 de acá
    # «ayer» era hoy, y la prueba fallaba de noche.
    ayer = (ns["hoy_aca"]() - timedelta(days=1)).isoformat()
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
            {"efectivo": 999.0, "otros_medios": 5150.0, "salidas": 0.0, "en_el_cajon": 999.0,
             "a_cuenta": 900.0, "ventas": 6,
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
    # Ni se le anula el cargo desde la cuenta corriente: la venta seguiría «A cuenta» en la caja
    # sin que nadie la deba.
    _saldo_con_k = saldo()
    g["_nivel_de_quien_esta_adentro"] = lambda: "admin"
    try:
        _ok_cargo, _texto_cargo = ns["anular_movimiento_de_cuenta"](
            uno("SELECT movimiento_id FROM ventas WHERE id = ?", v_k))
    finally:
        g["_nivel_de_quien_esta_adentro"] = g_adentro
    esperar("el cargo de una venta a cuenta no se anula suelto: dice cómo",
            (_ok_cargo, f"venta #{v_k}" in _texto_cargo, saldo() == _saldo_con_k),
            (False, True, True))
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
    # Con centavos, el precio vuelve justo: guardado, no dividiendo (1.234,50 con 5% volvía en
    # 1.234,49: lo encontró pruebas_al_azar_de_la_caja.py). Y una venta de antes de guardarlo
    # vuelve como antes, dividiendo.
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio, "
              "stock) SELECT 'CENT1', 'CENT1', 'FILTRO', marca_id, 1234.5, 10 FROM productos "
              "WHERE id = ?", (ids["A1"],))
    _cent = c.lastrowid
    conn.commit()
    v_c, _ = ns["cerrar_venta"]([dict(ns["item_de_venta"](_cent, 1))], a_la_caja=True)
    ns["cobrar_venta"](v_c, "Efectivo", descuento=5)
    _con_5 = uno("SELECT precio FROM ventas_items WHERE venta_id = ?", v_c)
    ns["volver_a_la_caja"](v_c)
    v_v, _ = ns["cerrar_venta"]([item("A1", 2)], a_la_caja=True)
    c.execute("UPDATE ventas_items SET precio_de_lista = NULL WHERE venta_id = ?", (v_v,))
    conn.commit()
    ns["cobrar_venta"](v_v, "Efectivo", descuento=10)
    ns["volver_a_la_caja"](v_v)
    esperar("el descuento se deshace justo, al centavo; y en una venta de antes, dividiendo",
            (_con_5, uno("SELECT precio FROM ventas_items WHERE venta_id = ?", v_c),
             uno("SELECT total FROM ventas WHERE id = ?", v_c),
             uno("SELECT precio FROM ventas_items WHERE venta_id = ?", v_v)),
            (1172.77, 1234.5, 1234.5, 1000.0))
    ns["cobrar_venta"](v_c, "Efectivo")
    ns["cobrar_venta"](v_v, "Efectivo")

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
    # LAS GARANTÍAS: lo devuelto fallado (o dañado) queda para reclamarle al proveedor; lo que
    # no le iba (otra medida), no. Por reclamar → reclamado → resuelto, y lo cerrado sale.
    st.session_state["nivel_usuario"] = "operador"
    v_gar, _ = ns["cerrar_venta"]([item("A1", 2)], a_la_caja=True)
    ns["cobrar_venta"](v_gar, "Efectivo")
    _it_gar = uno("SELECT id FROM ventas_items WHERE venta_id = ?", v_gar)
    _texto_fallada = ns["devolver_de_una_venta"](_it_gar, 1, "fallada", "pierde aceite")[1]
    _texto_medida = ns["devolver_de_una_venta"](_it_gar, 1, "medida")[1]
    esperar("el aviso de lo fallado dice que queda para reclamar; el de otra medida, no",
            ("🔧 Garantías" in _texto_fallada, "🔧 Garantías" in _texto_medida), (True, False))
    _gar = ns["garantias"]()
    esperar("para reclamar: lo fallado, no lo de otra medida",
            [(x["codigo"], x["motivo"], x["detalle"], x["reclamo"]) for x in _gar],
            [("A1", "fallada", "pierde aceite", "")])
    _msj_gar = ns["mensaje_de_garantia"]("PRUEBA", _gar)
    esperar("el reclamo dice qué volvió, qué tenía y pide respuesta",
            ("1 × A1 (FILTRO): vino fallada, «pierde aceite»" in _msj_gar,
             _msj_gar.endswith("¿Cómo hacemos para el cambio o la nota de crédito? ¡Gracias!")),
            (True, True))
    # EL RESUMEN DEL DÍA PARA EL DUEÑO: lo vendido por forma de pago, lo devuelto y lo fallado
    # por reclamar; la ganancia, solo si se pide (la arma un administrador).
    _resumen = ns["resumen_del_dia"]()
    _renglones = _resumen.split("\n")
    esperar("el resumen del día: título, lo vendido y por forma de pago",
            (_renglones[0].startswith("📊 Resumen del "), _renglones[1].startswith("💵 Vendido: $"),
             any(r.startswith("   · Efectivo: $") for r in _renglones)), (True, True, True))
    esperar("y lo devuelto y lo fallado por reclamar",
            (any(r.startswith("↩️ Devuelto: $") for r in _renglones),
             "🔧 Garantías por reclamar al proveedor: 1" in _renglones), (True, True))
    c.execute("UPDATE ventas_items SET costo = precio / 2 WHERE costo IS NULL")
    conn.commit()
    esperar("la ganancia, solo si se pide",
            ("Ganancia" in ns["resumen_del_dia"](),
             "💰 Ganancia estimada: $" in ns["resumen_del_dia"](con_ganancia=True)), (False, True))
    # EL RESUMEN DE LA SEMANA: lo vendido contra la semana anterior, lo que más salió y lo que
    # más pidieron y no había (lo buscado sin resultado, también en los pedidos del chat).
    c.execute("INSERT INTO ventas (fecha, usuario, forma_de_pago, total, cobrada, anulada) "
              "VALUES (datetime('now', '-8 days'), 'ana', 'Efectivo', 1000, 1, 0)")
    for _t in ("bomba nafta gol", "bomba nafta gol", "kit embrague palio"):
        ns["registrar_busqueda_sin_resultado"](_t)
    conn.commit()
    _semana = ns["resumen_de_la_semana"]().split("\n")
    esperar("la semana: título, lo vendido y contra la anterior",
            (_semana[0].startswith("📊 Semana del "), _semana[1].startswith("💵 Vendido: $"),
             any("contra la semana anterior ($1.000)" in r for r in _semana)), (True, True, True))
    esperar("lo que más salió y lo que más pidieron y no había",
            (any(r.startswith("🏆 Lo que más salió: ") and "A1" in r for r in _semana),
             "🔎 Lo que más pidieron y no había: bomba nafta gol ×2, kit embrague palio"
             in _semana), (True, True))
    esperar("la ganancia de la semana, solo si se pide",
            ("Ganancia" in "\n".join(_semana),
             "💰 Ganancia estimada: $" in ns["resumen_de_la_semana"](con_ganancia=True)),
            (False, True))
    _id_medida = uno("SELECT id FROM ventas_devoluciones WHERE motivo = 'medida' "
                     "ORDER BY id DESC LIMIT 1")
    esperar("lo de otra medida no se puede reclamar", ns["marcar_reclamo"]([_id_medida],
                                                                            "reclamado"), 0)
    # Sin reclamar hace más de dos semanas: lo dice la campanita, y reclamado ya no.
    _aviso_gar = lambda: [p["titulo"] for p in ns["diagnostico_de_salud"]()
                          if "sin reclamarle al proveedor" in p["titulo"]]
    esperar("recién devuelta, la campanita no dice nada", _aviso_gar(), [])
    c.execute("UPDATE ventas_devoluciones SET fecha = datetime('now', '-20 days') WHERE id = ?",
              (_gar[0]["id"],))
    conn.commit()
    ns["invalidar_salud"]()
    esperar("a las dos semanas sin reclamar, sí", _aviso_gar(),
            ["1 devolución(es) fallada(s) sin reclamarle al proveedor"])
    esperar("reclamado", (ns["marcar_reclamo"]([_gar[0]["id"]], "reclamado"),
                          [x["reclamo"] for x in ns["garantias"]()]), (1, ["reclamado"]))
    ns["invalidar_salud"]()
    esperar("y reclamada, la campanita ya no", _aviso_gar(), [])
    ns["marcar_reclamo"]([_gar[0]["id"]], "resuelto")
    esperar("resuelto: sale de la lista, y queda entre los cerrados",
            (ns["garantias"](), [x["reclamo"] for x in ns["garantias"](con_las_cerradas=True)
                                 if x["id"] == _gar[0]["id"]]), ([], ["resuelto"]))
    _claves_antes = g["hay_claves_configuradas"]
    try:
        g["hay_claves_configuradas"] = lambda: True
        g["_nivel_de_quien_esta_adentro"] = lambda: "mecanico"
        ns["marcar_reclamo"]([_gar[0]["id"]], "")
        fallas.append("un taller pudo anotar un reclamo de garantía")
    except PermissionError:
        pass
    finally:
        g["_nivel_de_quien_esta_adentro"], g["hay_claves_configuradas"] = g_adentro, _claves_antes

    # LAS SALIDAS DE CAJA: se descuentan del cajón y del arqueo, salen en el resumen del día, y
    # las anula el administrador (o quien las anotó, en sus primeros minutos).
    cs = ns["c"]
    st.session_state["admin_nombre"], st.session_state["nivel_usuario"] = "ana", "operador"
    _hoy = ns["hoy_aca"]().isoformat()
    _cajon_antes = ns["efectivo_esperado"]()
    esperar("sin en qué, sin importe o de otro tipo, no",
            [ns["anotar_salida_de_caja"](t, q, i)[0] for t, q, i in (
                ("🧾 Gasto", "  ", 100), ("🧾 Gasto", "flete", 0), ("Regalo", "flete", 100),
                ("🧾 Gasto", "flete", "mucho"))], [False] * 4)
    ok_s, texto_s = ns["anotar_salida_de_caja"]("🧾 Gasto", "  flete   del cadete ", 150)
    esperar("anotada, con el concepto prolijo",
            (ok_s, texto_s.startswith("💸 Anotado: 🧾 Gasto de $150 (flete del cadete).")),
            (True, True))
    ns["anotar_salida_de_caja"]("🏦 Retiro", "retiro del dueño", 300)
    esperar("el cajón las descuenta", round(_cajon_antes - ns["efectivo_esperado"](), 2),
            450.0)
    _r = ns["resumen_de_la_caja"]()
    esperar("arriba de la caja: lo que entró en efectivo queda, el cajón baja",
            (_r["salidas"], round(_r["efectivo"] - _r["en_el_cajon"], 2)), (450.0, 450.0))
    esperar("y el arqueo cierra", ns["arquear_la_caja"](_hoy, ns["efectivo_esperado"]()),
            (True, "✅ Cierra justo."))
    _sal = ns["salidas_de_caja"]()
    esperar("las del día, la última primero",
            [(x["tipo"], x["importe"], x["usuario"]) for x in _sal],
            [("🏦 Retiro", 300.0, "ana"), ("🧾 Gasto", 150.0, "ana")])
    _resumen = ns["resumen_del_dia"]()
    esperar("en el resumen del día", ("💸 Salidas de caja: $450 (2)" in _resumen,
                                      "🧮 En el cajón tendría que haber: $" in _resumen),
            (True, True))
    st.session_state["admin_nombre"] = "beto"
    esperar("la de otro, no", ns["anular_salida_de_caja"](_sal[0]["id"])[0], False)
    st.session_state["admin_nombre"] = "ana"
    esperar("la propia, enseguida, sí; anulada, ya no",
            (ns["anular_salida_de_caja"](_sal[0]["id"])[0],
             ns["anular_salida_de_caja"](_sal[0]["id"])[0]), (True, False))
    esperar("y deja de descontarse", ns["total_de_salidas"](), 150.0)
    cs.execute("UPDATE salidas_de_caja SET fecha = datetime('now', '-60 minutes') WHERE id = ?",
               (_sal[1]["id"],))
    esperar("la propia de hace una hora, no", ns["anular_salida_de_caja"](_sal[1]["id"])[0],
            False)
    st.session_state["nivel_usuario"] = "admin"
    esperar("el administrador, sí", ns["anular_salida_de_caja"](_sal[1]["id"])[0], True)
    st.session_state["nivel_usuario"] = "operador"
    esperar("todo anulado", ns["total_de_salidas"](), 0.0)
    esperar("en el registro de cambios, las dos y sus anulaciones",
            cs.execute("SELECT COUNT(*) FROM registro_de_cambios WHERE accion IN "
                       "('salida de caja', 'anuló una salida de caja')").fetchone()[0], 4)
    ns["anotar_salida_de_caja"]("🚚 Pago a un proveedor", "contra entrega", 700,
                                dia="2020-01-01")
    esperar("la de otro día, aparte",
            (ns["total_de_salidas"](), ns["total_de_salidas"]("2020-01-01")), (0.0, 700.0))

    # EL CAMBIO DE APERTURA Y LOS BILLETES: uno por día (otra vez lo corrige), y contando los
    # billetes la app suma, resta el cambio y lo pasa al arqueo con el detalle.
    esperar("sin anotar, no hay", ns["cambio_de_apertura"](_hoy), None)
    esperar("negativo, sin número o disparatado, no",
            [ns["anotar_cambio_de_apertura"](x, _hoy)[0] for x in (-5, None, "mucho", 1e12)],
            [False] * 4)
    esperar("anotado", ns["anotar_cambio_de_apertura"](20000, _hoy),
            (True, "🪙 Cambio de apertura: $20.000."))
    ns["anotar_cambio_de_apertura"](15000, _hoy)
    esperar("otra vez lo corrige (uno por día), y queda en el registro",
            (ns["cambio_de_apertura"](_hoy), ns["cambio_de_apertura"]("2020-01-01"),
             cs.execute("SELECT COUNT(*) FROM aperturas_de_caja").fetchone()[0],
             cs.execute("SELECT COUNT(*) FROM registro_de_cambios WHERE accion = "
                        "'cambio de apertura'").fetchone()[0]), (15000.0, None, 1, 2))
    _conteo = {20000: 1, 1000: 2, 100: "3", 50: None, 10: -4}
    esperar("los billetes suman (los vacíos y los negativos no)",
            (ns["total_de_billetes"](_conteo, 350), ns["total_de_billetes"]({}, None)),
            (22650.0, 0.0))
    esperar("el detalle, del más grande al más chico",
            ns["detalle_de_billetes"]({100: 3, 20000: 1, 1000: 2, 500: 0}, 350),
            "1 × $20.000 · 2 × $1.000 · 3 × $100 · monedas $350")
    for _d in ns["DENOMINACIONES_DE_BILLETES"]:
        st.session_state.pop(f"billete_{_d}", None)
    st.session_state.update({"billete_20000": 1, "billete_1000": 2, "billete_monedas": 350})
    ns["pasar_los_billetes_al_arqueo"](_hoy)
    esperar("al arqueo: el total menos el cambio, y el detalle en la nota",
            (st.session_state["arqueo_contado"], st.session_state["arqueo_nota"]),
            (7350.0, "1 × $20.000 · 2 × $1.000 · monedas $350 (menos $15.000 de cambio)"))
    st.session_state.update({"billete_20000": 0, "billete_1000": 3, "billete_monedas": 0})
    ns["pasar_los_billetes_al_arqueo"]("2020-01-01")
    esperar("sin cambio anotado ese día, el total entero; y nunca negativo",
            (st.session_state["arqueo_contado"], st.session_state["arqueo_nota"]),
            (3000.0, "3 × $1.000"))
    ns["pasar_los_billetes_al_arqueo"](_hoy)
    esperar("menos que el cambio: cero", st.session_state["arqueo_contado"], 0.0)

    # EL OBJETIVO DEL MES: lo pone el administrador, se arrastra a los meses que siguen hasta
    # que lo cambie (0 lo saca), y el avance dice cuánto por día abierto falta para llegar.
    from datetime import date as _fecha
    esperar("sin objetivo, nada", (ns["objetivo_del_mes"](), ns["avance_del_objetivo"](),
                                   ns["renglon_del_objetivo"](None)), (None, None, ""))
    _claves_antes, _nivel_antes = g["hay_claves_configuradas"], g["_nivel_de_quien_esta_adentro"]
    try:
        g["hay_claves_configuradas"] = lambda: True
        g["_nivel_de_quien_esta_adentro"] = lambda: "operador"
        ns["guardar_objetivo_del_mes"](1000)
        fallas.append("un empleado pudo poner el objetivo de ventas")
    except PermissionError:
        pass
    finally:
        g["hay_claves_configuradas"], g["_nivel_de_quien_esta_adentro"] = (_claves_antes,
                                                                          _nivel_antes)
    st.session_state["nivel_usuario"] = "admin"
    esperar("negativo, sin número o disparatado, no",
            [ns["guardar_objetivo_del_mes"](x, "2025-01")[0]
             for x in (-1, "mucho", float("nan"), 1e13)], [False] * 4)
    esperar("puesto", ns["guardar_objetivo_del_mes"](2400000, "2025-01"),
            (True, "🎯 Objetivo de enero 2025: $2.400.000."))
    ns["guardar_objetivo_del_mes"](0, "2025-06")
    esperar("se arrastra a los meses que siguen, y en 0 se saca desde ese mes",
            [ns["objetivo_del_mes"](m) for m in ("2024-12", "2025-01", "2025-02", "2025-06",
                                                 "2025-09")],
            [None, 2400000.0, 2400000.0, None, None])
    esperar("en el registro de cambios",
            cs.execute("SELECT COUNT(*) FROM registro_de_cambios WHERE accion = "
                       "'cambió el objetivo de ventas'").fetchone()[0], 2)
    esperar("sin horario cargado, abre de lunes a sábado", ns["dias_que_se_abre"](),
            (0, 1, 2, 3, 4, 5))
    # Febrero de 2025 empieza un sábado: de lunes a sábado son 24 días; antes del lunes 10, 7.
    _av = ns["avance_del_objetivo"]("2025-02", hoy=_fecha(2025, 2, 10))
    esperar("sin vender nada: quedan 17 días, a $141.176 por día, atrasados",
            {k: _av[k] for k in ("vendido", "por_ciento", "falta", "quedan", "por_dia",
                                 "esperado", "cumplido")},
            {"vendido": 0.0, "por_ciento": 0.0, "falta": 2400000.0, "quedan": 17,
             "por_dia": 141176.0, "esperado": 700000.0, "cumplido": False})
    for _fecha_v, _total_v, _anulada_v in (("2025-02-05 15:00:00", 1000000, 0),
                                           ("2025-02-06 15:00:00", 500000, 1),
                                           ("2025-03-01 02:00:00", 300000, 0)):
        cs.execute("INSERT INTO ventas (fecha, usuario, forma_de_pago, total, cobrada, anulada) "
                   "VALUES (?, 'ana', 'Efectivo', ?, 1, ?)", (_fecha_v, _total_v, _anulada_v))
    _av = ns["avance_del_objetivo"]("2025-02", hoy=_fecha(2025, 2, 10))
    esperar("lo anulado no cuenta y la de las 23 del 28 (hora de acá) es de febrero",
            (_av["vendido"], _av["por_ciento"], _av["por_dia"]), (1000000.0, 41.7, 82353.0))
    esperar("el renglón del administrador, con la plata",
            ns["renglon_del_objetivo"](_av),
            "🎯 Objetivo del mes: 42% ($1.000.000 de $2.400.000) · quedan 17 día(s) "
            "abierto(s): $82.353 por día para llegar · vamos adelantados")
    esperar("el del empleado, sin la plata", ns["renglon_del_objetivo"](_av, con_plata=False),
            "🎯 Objetivo del mes: 42% · quedan 17 día(s) abierto(s) · vamos adelantados")
    ns["guardar_config"](ns["CLAVE_DEL_HORARIO"], "lun-vie 8:00-18:00")
    _av = ns["avance_del_objetivo"]("2025-02", hoy=_fecha(2025, 2, 10))
    esperar("con el horario, solo los días que abre",
            (ns["dias_que_se_abre"](), _av["quedan"], _av["esperado"]),
            ((0, 1, 2, 3, 4), 15, 600000.0))
    ns["guardar_config"](ns["CLAVE_DEL_HORARIO"], "")
    _av = ns["avance_del_objetivo"]("2025-02", hoy=_fecha(2025, 3, 15))
    esperar("el mes ya pasado: no quedan días, y lo que faltó",
            (_av["quedan"], _av["por_dia"], _av["vendido"]), (0, 1100000.0, 1300000.0))
    ns["guardar_objetivo_del_mes"](1000000, "2025-02")
    _av = ns["avance_del_objetivo"]("2025-02", hoy=_fecha(2025, 3, 15))
    esperar("cumplido", (_av["cumplido"], _av["falta"], ns["renglon_del_objetivo"](_av)),
            (True, 0.0, "🎉 ¡Objetivo del mes cumplido! $1.300.000 de $1.000.000 (130%)"))
    esperar("y en el resumen del día de ese mes",
            "🎉 ¡Objetivo del mes cumplido!" in ns["resumen_del_dia"]("2025-02-28"), True)
    esperar("el del mes que viene no se pisa", ns["objetivo_del_mes"]("2025-03"), 1000000.0)
    st.session_state["nivel_usuario"] = "operador"

    # LAS SEÑAS: entran a la caja el día que se dejan, por donde se pagaron; al retirar, la venta
    # cuenta solo lo que falta; anular la venta la deja esperando otra vez; devolverla la saca.
    def _forma(caja, f):
        return next((t for x, _, t in caja["por_forma"] if x == f), 0.0)
    _c0, _ef0 = ns["cierre_de_caja"](), ns["efectivo_esperado"]()
    esperar("sin nombre ni teléfono, sin qué, en cero, disparatada, de otra forma, o de un "
            "producto que no existe: no",
            [ns["anotar_sena"](*x)[0] for x in (
                ("", "", "kit", 100, "Efectivo"), ("Juan", "", "", 100, "Efectivo"),
                ("Juan", "", "kit", 0, "Efectivo"), ("Juan", "", "kit", 1e12, "Efectivo"),
                ("Juan", "", "kit", 100, "Bitcoin"), ("Juan", "", "", 100, "Efectivo", 999999))],
            [False] * 6)
    ok_s1, texto_s1, s1 = ns["anotar_sena"]("Juan", "11 4567-8901", "", 1500, "Efectivo",
                                            ids["B1"], pedir_al_proveedor=True)
    esperar("anotada, del catálogo: avisa al entrar y queda pedida al proveedor",
            (ok_s1, texto_s1), (True, "🔖 Seña de $1.500 (Efectivo) de Juan por PRUEBA B1. "
                                      "Cuando entre, la app avisa para escribirle. Quedó "
                                      "anotado como pedido al proveedor."))
    esperar("queda en lo que espera el cliente, y pedida",
            (tuple(c.execute("SELECT estado, nota FROM consultas_cliente WHERE id = (SELECT "
                             "consulta_id FROM senas WHERE id = ?)", (s1,)).fetchone()),
             uno("SELECT COUNT(*) FROM pedidos_a_proveedores WHERE producto_id = ?", ids["B1"])),
            (("activa", "Dejó $1.500 de seña"), 1))
    _, _, s2 = ns["anotar_sena"]("", "351 111-2222", "Óptica Fiat 147", 800, "Transferencia")
    _c1 = ns["cierre_de_caja"]()
    esperar("entra a la caja hoy, por donde se pagó",
            (round(_c1["total"] - _c0["total"], 2), round(_forma(_c1, "Efectivo")
                                                         - _forma(_c0, "Efectivo"), 2),
             round(_forma(_c1, "Transferencia") - _forma(_c0, "Transferencia"), 2),
             _c1["senas"] - _c0["senas"], round(ns["efectivo_esperado"]() - _ef0, 2)),
            (2300.0, 1500.0, 800.0, 2, 1500.0))
    esperar("cuáles se pueden descontar: por el producto o por el teléfono",
            ([x["id"] for x in ns["senas_para_la_venta"]([ids["B1"]])],
             [x["id"] for x in ns["senas_para_la_venta"]([ids["A1"]], "0351 15 111-2222")],
             ns["senas_para_la_venta"]([ids["A1"]])), ([s1], [s2], []))
    v1, _ = ns["cerrar_venta"]([item("B1")], "Juan", "Efectivo", senas=[s1])
    _c2 = ns["cierre_de_caja"]()
    esperar("al retirar: la venta vale entera, entra lo que falta, y la seña queda usada",
            (uno("SELECT total FROM ventas WHERE id = ?", v1),
             round(_forma(_c2, "Efectivo") - _forma(_c1, "Efectivo"), 2),
             round(_c2["senas_descontadas"] - _c1["senas_descontadas"], 2),
             tuple(c.execute("SELECT estado, venta_id FROM senas WHERE id = ?", (s1,)).fetchone()),
             uno("SELECT estado FROM consultas_cliente WHERE id = (SELECT consulta_id FROM senas "
                 "WHERE id = ?)", s1)),
            (2500.0, 1000.0, 1500.0, ("usada", v1), "vendida"))
    for _que_s, _hacer_s in (
            ("la misma seña otra vez", lambda: ns["cerrar_venta"]([item("B1")], "", "Efectivo",
                                                                   senas=[s1])),
            ("una seña más grande que la venta",
             lambda: ns["cerrar_venta"]([item("A1")], "", "Efectivo",
                                        senas=[ns["anotar_sena"]("Ana", "", "x", 3000,
                                                                 "Efectivo", ids["A1"])[2]])),
            ("una venta a cuenta con seña",
             lambda: ns["cerrar_venta"]([item("A1")], "", ns["A_CUENTA"], a_la_caja=True,
                                        senas=[s2]))):
        try:
            _hacer_s()
            fallas.append(f"se pudo vender con {_que_s}")
        except ValueError:
            pass
    s3 = uno("SELECT MAX(id) FROM senas WHERE cliente = 'Ana'")
    v2, _ = ns["cerrar_venta"]([item("A1", 4)], "Ana", a_la_caja=True, senas=[s3])
    _espera_v2 = next(v for v in ns["ventas_a_cobrar"]() if v["id"] == v2)
    esperar("en la caja: el cartel dice cuánto cobrar, y a cuenta no va",
            ("dejó $3.000 de seña: cobrar $1.000" in ns["el_cartel_de"](_espera_v2),
             ns["poner_a_cuenta"](v2, taller)[0]), (True, False))
    _c3 = ns["cierre_de_caja"]()
    ns["cobrar_venta"](v2, "Efectivo")
    esperar("cobrada: entra lo que falta",
            round(_forma(ns["cierre_de_caja"](), "Efectivo") - _forma(_c3, "Efectivo"), 2), 1000.0)
    esperar("el comprobante dice la seña y lo que pagó",
            ("Seña que ya dejaste: -$3.000 · A PAGAR: $1.000" in ns["texto_del_comprobante"](v2),
             ns["pdf_del_comprobante"](ns["una_venta"](v2))[:4]), (True, b"%PDF"))
    st.session_state["nivel_usuario"] = "admin"
    _c4 = ns["cierre_de_caja"]()
    ns["anular_venta"](v1)
    esperar("anulada la venta, la seña vuelve a esperar (y lo encargado también)",
            (tuple(c.execute("SELECT estado, venta_id FROM senas WHERE id = ?", (s1,)).fetchone()),
             uno("SELECT estado FROM consultas_cliente WHERE id = (SELECT consulta_id FROM senas "
                 "WHERE id = ?)", s1),
             round(_forma(ns["cierre_de_caja"](), "Efectivo") - _forma(_c4, "Efectivo"), 2)),
            (("activa", None), "activa", -1000.0))
    st.session_state["nivel_usuario"] = "operador"
    _c5 = ns["cierre_de_caja"]()
    esperar("devuelta: sale de la caja de hoy, por donde entró; dos veces, no",
            (ns["devolver_sena"](s1),
             round(_forma(ns["cierre_de_caja"](), "Efectivo") - _forma(_c5, "Efectivo"), 2),
             ns["cierre_de_caja"]()["senas_devueltas"] - _c5["senas_devueltas"],
             ns["devolver_sena"](s1)[0],
             uno("SELECT estado FROM consultas_cliente WHERE id = (SELECT consulta_id FROM senas "
                 "WHERE id = ?)", s1)),
            ((True, "↩️ Seña devuelta a Juan: $1.500 (Efectivo). Sale de la caja de hoy."),
             -1500.0, 1, False, "cancelada"))
    esperar("en el resumen del día",
            "🔖 Señas: entraron $" in ns["resumen_del_dia"](), True)
    esperar("las que esperan: la de la óptica", [x["id"] for x in ns["senas_activas"]()], [s2])
    # EL RECARGO POR CUOTAS: el administrador lo pone por cantidad de cuotas; la caja lo aplica
    # al cobrar con crédito en cuotas (sobre cada precio, como el descuento) y «volver a la caja»
    # lo saca.
    st.session_state["nivel_usuario"] = "admin"
    for _malo in ({1: 5}, {3: 150}, {5: 10}):
        try:
            ns["guardar_recargos_por_cuotas"](_malo)
            fallas.append(f"se guardó un recargo que no va: {_malo}")
        except ValueError:
            pass
    esperar("guardados: el 0 no queda",
            (ns["guardar_recargos_por_cuotas"]({3: 10, 6: 0, 12: 25}),
             ns["recargos_por_cuotas"]()), ({3: 10.0, 12: 25.0}, {3: 10.0, 12: 25.0}))
    esperar("solo con crédito y en las cuotas que tienen",
            [ns["recargo_por_cuotas"](f, n) for f, n in (("Tarjeta de crédito", 3),
                                                          ("Efectivo", 3),
                                                          ("Tarjeta de crédito", 6),
                                                          ("Tarjeta de crédito", 1))],
            [10.0, 0.0, 0.0, 0.0])
    st.session_state["nivel_usuario"] = "operador"
    v_r, _ = ns["cerrar_venta"]([item("A1", 2)], a_la_caja=True)
    esperar("antes de cobrar, la caja lo calcula", ns["total_con_descuento"](v_r, 0, 10), 2200.0)
    esperar("cobrada en 3 cuotas: con el recargo, en cada precio",
            (ns["cobrar_venta"](v_r, "Tarjeta de crédito", 3)[1],
             uno("SELECT total FROM ventas WHERE id = ?", v_r),
             uno("SELECT recargo FROM ventas WHERE id = ?", v_r),
             uno("SELECT precio FROM ventas_items WHERE venta_id = ?", v_r)),
            (f"💵 Venta #{v_r} cobrada: $2.200 (Tarjeta de crédito, 3 cuotas, con 10% de "
             "recargo).", 2200.0, 10.0, 1100.0))
    esperar("el comprobante lo dice",
            ("Recargo 10% por 3 cuotas (incluido en los precios)" in
             ns["texto_del_comprobante"](v_r), ns["pdf_del_comprobante"](ns["una_venta"](v_r))[:4]),
            (True, b"%PDF"))
    esperar("cambiar solo la forma, no: se cobró con recargo",
            ns["cambiar_como_se_pago"](v_r, "Efectivo")[0], False)
    esperar("volver a la caja lo saca, al centavo",
            (ns["volver_a_la_caja"](v_r)[0], uno("SELECT total FROM ventas WHERE id = ?", v_r),
             uno("SELECT recargo FROM ventas WHERE id = ?", v_r),
             uno("SELECT precio FROM ventas_items WHERE venta_id = ?", v_r)),
            (True, 2000.0, 0.0, 1000.0))
    ns["cobrar_venta"](v_r, "Tarjeta de crédito", 12, 10)
    esperar("con descuento y recargo: los dos, sobre el precio sin descuento",
            uno("SELECT total FROM ventas WHERE id = ?", v_r), 2250.0)
    esperar("en efectivo, sin recargo", (ns["volver_a_la_caja"](v_r)[0],
                                         ns["cobrar_venta"](v_r, "Efectivo", 3)[0],
                                         uno("SELECT total FROM ventas WHERE id = ?", v_r)),
            (True, True, 2000.0))
    c.execute("UPDATE senas SET fecha = datetime('now', '-40 days') WHERE id = ?", (s2,))
    esperar("la que nadie retira hace más de los días elegidos, a la campanita",
            ([x["id"] for x in ns["senas_sin_retirar"]()], ns["senas_sin_retirar"](60)),
            ([s2], []))
    ns["invalidar_salud"]()
    esperar("y la campanita lo dice",
            [p["titulo"] for p in ns["diagnostico_de_salud"]() if "sin retirar" in p["titulo"]],
            ["🔖 1 seña(s) sin retirar hace más de 30 días"])
    ns["anotar_salida_de_caja"]("🧾 Gasto", "artículos de limpieza", 120)
    esperar("y en el resumen de la semana, por tipo (lo anulado y lo de 2020, no)",
            [r for r in ns["resumen_de_la_semana"]().split("\n") if r.startswith("💸")],
            ["💸 Salidas de caja: 🧾 Gasto $120"])
    # EL MES POR VENDEDOR (ver ventas_por_vendedor()): por quien armó la venta, sin lo anulado
    # y con lo devuelto descontado a quien la había vendido; otro mes, aparte.
    def _venta_vieja(quien, total, fecha, anulada=0):
        cs.execute("INSERT INTO ventas (fecha, usuario, forma_de_pago, total, cobrada, anulada) "
                   "VALUES (?, ?, 'Efectivo', ?, 1, ?)", (fecha, quien, total, anulada))
        _v = cs.lastrowid
        cs.execute("INSERT INTO ventas_items (venta_id, producto_id, codigo, marca, cantidad, "
                   "precio) VALUES (?, NULL, 'X', 'X', 1, ?)", (_v, total))
        return _v, cs.lastrowid
    _vr, _ir = _venta_vieja("rosa", 1000, "2020-03-10 15:00:00")
    _venta_vieja("rosa", 3000, "2020-03-20 15:00:00")
    _venta_vieja("rosa", 5000, "2020-03-21 15:00:00", anulada=1)
    _venta_vieja("tito", 500, "2020-03-31 20:00:00")
    _venta_vieja("tito", 900, "2020-04-01 12:00:00")
    cs.execute("INSERT INTO ventas_devoluciones (venta_id, venta_item_id, cantidad, importe, "
               "usuario, fecha) VALUES (?, ?, 1, 200, 'beto', '2020-03-12 15:00:00')",
               (_vr, _ir))
    esperar("el mes por vendedor",
            [(x["Vendedor"], x["Ventas"], x["Vendido"], x["Devuelto"], x["Ticket promedio"])
             for x in ns["ventas_por_vendedor"]("2020-03-01", "2020-03-31")],
            [("rosa", 2, 3800.0, 200.0, 2000.0), ("tito", 1, 500.0, 0.0, 500.0)])
    # Los meses para elegir, su rango (el de este mes llega a hoy; febrero bisiesto, al 29) y
    # la comisión, con lo vendido el mes de antes.
    _d = ns["date"]
    esperar("los meses para elegir", ns["meses_para_elegir"](3, hoy=_d(2026, 1, 15)),
            ["2026-01", "2025-12", "2025-11"])
    esperar("el nombre del mes", ns["nombre_del_mes"]("2026-11"), "noviembre 2026")
    esperar("el rango del mes", (ns["rango_del_mes"]("2028-02", hoy=_d(2028, 5, 1)),
                                 ns["rango_del_mes"]("2026-12", hoy=_d(2026, 12, 9))),
            (("2028-02-01", "2028-02-29"), ("2026-12-01", "2026-12-09")))
    ns["guardar_comision_por_ciento"](5)
    esperar("la comisión anotada", ns["comision_por_ciento"](), 5.0)
    esperar("las comisiones de marzo",
            [(x["Vendedor"], x["Comisión"], x["Mes anterior"])
             for x in ns["comisiones_del_mes"]("2020-03", hoy=_d(2026, 1, 1))],
            [("rosa", 190.0, 0.0), ("tito", 25.0, 0.0)])
    esperar("y abril, con lo de marzo al lado",
            [(x["Vendedor"], x["Vendido"], x["Mes anterior"])
             for x in ns["comisiones_del_mes"]("2020-04", hoy=_d(2026, 1, 1))],
            [("tito", 900.0, 500.0)])
    try:
        ns["guardar_comision_por_ciento"](80)
        fallas.append("se pudo anotar una comisión de 80%")
    except ValueError:
        pass
    # La comisión propia de un vendedor; el que no tiene, la general. Y su liquidación, con
    # cada venta.
    ns["guardar_comision_de"]("rosa", 10)
    esperar("rosa con la suya, tito con la general",
            [(x["Vendedor"], x["%"], x["Comisión"])
             for x in ns["comisiones_del_mes"]("2020-03", hoy=_d(2026, 1, 1))],
            [("rosa", 10.0, 380.0), ("tito", 5.0, 25.0)])
    esperar("las ventas de rosa en marzo, con lo devuelto",
            [(x["dia"], x["total"], x["devuelto"])
             for x in ns["ventas_del_vendedor"]("2020-03-01", "2020-03-31", "rosa")],
            [("2020-03-10", 1000.0, 200.0), ("2020-03-20", 3000.0, 0)])
    _liq = ns["liquidacion_del_vendedor"]("2020-03", "rosa", hoy=_d(2026, 1, 1))
    esperar("la liquidación de rosa", _liq.split("\n"),
            ["🏆 Liquidación de marzo 2020 — rosa", "🧾 Ventas: 2 por $4.000",
             "↩️ Devuelto: $200", "💵 Vendido: $3.800", "💰 Comisión (10%): $380"])
    _pdf_liq = ns["liquidacion_para_descargar"]("2020-03", "rosa", hoy=_d(2026, 1, 1))()
    esperar("y su PDF", _pdf_liq[:4], b"%PDF")
    esperar("del que no vendió, nada",
            (ns["liquidacion_del_vendedor"]("2020-03", "nadie", hoy=_d(2026, 1, 1)),
             ns["liquidacion_para_descargar"]("2020-03", "nadie", hoy=_d(2026, 1, 1))()),
            ("", b""))
    ns["guardar_comision_de"]("rosa", None)
    esperar("sin la propia, vuelve a la general", ns["comision_de"]("rosa"), 5.0)
    _claves_antes = g["hay_claves_configuradas"]
    try:
        g["hay_claves_configuradas"] = lambda: True
        for _nivel in ("", "mecanico"):
            g["_nivel_de_quien_esta_adentro"] = lambda n=_nivel: n
            for _que, _hacer in (("cambiar la comisión", lambda: ns["guardar_comision_por_ciento"](
                                    3)),
                                 ("cambiar la comisión de uno",
                                  lambda: ns["guardar_comision_de"]("rosa", 3)),
                                 ("cambiar el objetivo de ventas en",
                                  lambda: ns["guardar_objetivo_del_mes"](3)),
                                 ("anotar una seña en",
                                  lambda: ns["anotar_sena"]("x", "", "y", 1, "Efectivo")),
                                 ("devolver una seña en", lambda: ns["devolver_sena"](1)),
                                 ("cambiar el recargo por cuotas en",
                                  lambda: ns["guardar_recargos_por_cuotas"]({3: 1})),
                                 ("anotar", lambda: ns["anotar_salida_de_caja"](
                                    "🧾 Gasto", "x", 1)),
                                 ("anotar el cambio de apertura en",
                                  lambda: ns["anotar_cambio_de_apertura"](1)),
                                 ("anular", lambda: ns["anular_salida_de_caja"](1))):
                try:
                    _hacer()
                    fallas.append(f"«{_nivel or 'invitado'}» pudo {_que} una salida de caja")
                except PermissionError:
                    pass
    finally:
        g["_nivel_de_quien_esta_adentro"], g["hay_claves_configuradas"] = g_adentro, _claves_antes
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

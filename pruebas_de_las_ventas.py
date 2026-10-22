"""Pruebas de las ventas del mostrador (🧾 Ventas).

Uso:
    python3 pruebas_de_las_ventas.py

Cerrar una venta descuenta el stock sin dejarlo negativo, guarda el precio de ese momento y
anota lo vendido para aprender equivalencias; todo o nada. Al terminar, con la patente y los km,
cada pieza queda en la ficha del auto, una sola vez. Anular devuelve al stock lo que se
descontó. Ver «VENTAS DEL MOSTRADOR» en logica/ventas.py.

Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import os
import shutil
import sys
import tempfile


def _cargar_la_logica(carpeta):
    raiz = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, raiz)
    os.chdir(carpeta)
    import logica
    return logica


def probar(L):
    ns = L.todo_lo_de_la_logica()
    c, conn, st = ns["c"], ns["conn"], ns["st"]
    g = ns["inflacion_desde"].__globals__
    fallas = []

    def esperar(nombre, real, esperado):
        if real != esperado:
            fallas.append(f"{nombre}: dio {real!r}, se esperaba {esperado!r}")

    def stock(pid):
        return c.execute("SELECT stock FROM productos WHERE id = ?", (pid,)).fetchone()[0]

    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('PRUEBA', 'PROVEEDOR')")
    marca = c.lastrowid
    ids = {}
    for codigo, desc, precio, st_ in (("F100", "FILTRO ACEITE VW GOL 1.6 (W712/94)", 10000, 5),
                                      ("J200", "JUNTA TAPA DE CILINDROS", 2500, None),
                                      ("B300", "BUJIA NGK BKR6E", 3000, 1)):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio, "
                  "stock) VALUES (?, ?, ?, ?, ?, ?)", (codigo, codigo, desc, marca, precio, st_))
        ids[codigo] = c.lastrowid
    conn.commit()
    item = ns["item_de_venta"]

    # 1. El nombre corto de la pieza, para que la ficha agrupe los cambios.
    esperar("nombre de la pieza",
            [ns["nombre_de_la_pieza"](d) for d in
             ("FILTRO ACEITE VW GOL 1.6 (W712/94)", "Filtro de aire Fiat Palio",
              "PASTILLA FRENO DEL. VW GOL", "KIT DE DISTRIBUCION GOL 1.6", "")],
            ["Filtro aceite", "Filtro de aire", "Pastilla freno", "Kit de distribucion", ""])

    # 2. Lo que no se puede vender no deja nada a medias.
    for nombre, items in (("vacía", []),
                          ("cantidad 0", [dict(item(ids["F100"]), cantidad=0)]),
                          ("precio negativo", [dict(item(ids["F100"]), precio=-1)]),
                          ("un producto que ya no está", [item(ids["F100"]),
                                                          dict(item(ids["J200"]), producto_id=999999)])):
        try:
            ns["cerrar_venta"](items)
            esperar(f"no se vende: {nombre}", "se vendió", "ValueError")
        except ValueError:
            pass
    esperar("y no quedó nada a medias", (c.execute("SELECT COUNT(*) FROM ventas").fetchone()[0],
                                         stock(ids["F100"])), (0, 5))

    # 3. La venta: el stock baja sin quedar negativo (y avisa), el sin stock cargado no se toca,
    # el precio es el de la pantalla, y lo vendido queda para aprender equivalencias.
    venta, avisos = ns["cerrar_venta"](
        [dict(item(ids["F100"], 2, "W712/94"), precio=9500), item(ids["J200"]),
         item(ids["B300"], 3)], "Juan", "Efectivo")
    esperar("la venta", tuple(c.execute("SELECT cliente, forma_de_pago, total, anulada FROM ventas "
                                        "WHERE id = ?", (venta,)).fetchone()),
            ("Juan", "Efectivo", 2 * 9500 + 2500 + 3 * 3000, 0))
    esperar("el stock", (stock(ids["F100"]), stock(ids["J200"]), stock(ids["B300"])), (3, None, 0))
    esperar("cuánto se descontó de cada uno",
            [r[0] for r in c.execute("SELECT stock_descontado FROM ventas_items WHERE venta_id = ? "
                                     "ORDER BY id", (venta,))], [2, 0, 1])
    esperar("el aviso de que no alcanzaba", len(avisos) == 1 and "B300" in avisos[0], True)
    esperar("lo que aprende: lo que pidió y lo que se llevó",
            [tuple(r) for r in c.execute("SELECT producto_id, termino_pedido FROM ventas_registradas "
                                         "ORDER BY id")],
            [(ids["F100"], "W712/94"), (ids["J200"], "J200"), (ids["B300"], "B300")])

    # 4. Al terminar: la patente y los km. Crea la ficha, anota cada pieza con su nombre, una
    # sola vez, con la vida útil de las otras veces.
    c.execute("INSERT INTO vehiculos (patente) VALUES ('ZZ999ZZ')")
    otro = c.lastrowid
    c.execute("INSERT INTO historial_piezas (vehiculo_id, descripcion_pieza, vida_util_km) "
              "VALUES (?, 'Filtro aceite', 10000)", (otro,))
    conn.commit()
    _items = [r[0] for r in c.execute("SELECT id FROM ventas_items WHERE venta_id = ? ORDER BY id",
                                      (venta,))]
    sin_km = ns["anotar_la_venta_en_el_auto"](venta, "AE 777 ZZ", "muchos")
    ok, texto, auto = ns["anotar_la_venta_en_el_auto"](
        venta, "ae 777 zz", 50000, {_items[1]: "Junta de tapa"}, "Juan", "351 555-4321")
    esperar("anotada en el auto", (sin_km[0], ok, "3 pieza(s)" in texto), (False, True, True))
    esperar("la ficha", tuple(c.execute("SELECT patente, km_actual, cliente_nombre FROM vehiculos "
                                        "WHERE id = ?", (auto,)).fetchone()),
            ("AE777ZZ", 50000, "Juan"))
    esperar("cada pieza, con su nombre, su producto y la vida útil de las otras veces",
            [tuple(r) for r in c.execute(
                "SELECT descripcion_pieza, producto_id, km_instalacion, vida_util_km, nota "
                "FROM historial_piezas WHERE vehiculo_id = ? ORDER BY id", (auto,))],
            [("Filtro aceite", ids["F100"], 50000, 10000, f"Venta #{venta}"),
             ("Junta de tapa", ids["J200"], 50000, None, f"Venta #{venta}"),
             ("Bujia", ids["B300"], 50000, None, f"Venta #{venta}")])
    esperar("una sola vez", ns["anotar_la_venta_en_el_auto"](venta, "AE777ZZ", 50000)[0], False)

    # Otra venta al mismo auto: con menos km se frena (casi siempre es un número mal tipeado),
    # confirmado entra; escrita la patente de otra forma, es la misma ficha.
    venta2, _ = ns["cerrar_venta"]([item(ids["F100"])])
    menos = ns["anotar_la_venta_en_el_auto"](venta2, "AE-777-ZZ", 40000)
    confirmado = ns["anotar_la_venta_en_el_auto"](venta2, "AE-777-ZZ", 40000,
                                                  aunque_tenga_menos_km=True)
    esperar("menos km: se frena, y confirmado entra en la misma ficha",
            (menos[0], "menos km" in menos[1], confirmado[0], confirmado[2],
             c.execute("SELECT COUNT(*) FROM vehiculos WHERE patente LIKE 'AE%'").fetchone()[0]),
            (False, True, True, auto, 1))

    # 5. Anular devuelve al stock lo que se descontó (no lo que se vendió de más), una vez. Y
    # saca de la ficha del auto lo que se anotó con ella —también lo anotado antes de que cada
    # pieza supiera de qué venta salió, por la nota— y lo que se aprendió de ella.
    c.execute("UPDATE historial_piezas SET venta_id = NULL WHERE id = (SELECT MIN(id) FROM "
              "historial_piezas WHERE venta_id = ?)", (venta,))
    conn.commit()
    ok_an, texto_an = ns["anular_venta"](venta)
    esperar("anulada: vuelve lo descontado", (ok_an, stock(ids["F100"]), stock(ids["J200"]),
                                              stock(ids["B300"]), ns["anular_venta"](venta)[0]),
            (True, 4, None, 1, False))
    esperar("anulada: sale de la ficha del auto y de lo aprendido, lo de la otra venta queda",
            ([r[0] for r in c.execute("SELECT nota FROM historial_piezas WHERE vehiculo_id = ?",
                                      (auto,))],
             c.execute("SELECT COUNT(*) FROM ventas_registradas WHERE venta_id = ?",
                       (venta,)).fetchone()[0],
             c.execute("SELECT COUNT(*) FROM ventas_registradas WHERE venta_id = ?",
                       (venta2,)).fetchone()[0],
             "3 pieza(s) de la ficha de AE777ZZ" in texto_an),
            ([f"Venta #{venta2}"], 0, 1, True))
    esperar("anulada no se anota en un auto",
            ns["anotar_la_venta_en_el_auto"](venta, "AB123CD", 1000)[0], False)
    _hoy = {v["id"]: v for v in ns["ventas_del_dia"]()}
    esperar("las de hoy, con sus ítems y la anulada marcada",
            (_hoy[venta]["anulada"], len(_hoy[venta]["items"]), _hoy[venta2]["patente"]),
            (1, 3, "AE777ZZ"))

    # 6. El presupuesto del buscador pasa a la venta, y la pantalla va a Ventas.
    st.session_state["carrito"] = {ids["F100"]: {"cantidad": 2}, ids["J200"]: {"cantidad": 1}}
    st.session_state["venta_items"] = [item(ids["F100"], 1)]
    ns["pasar_el_presupuesto_a_una_venta"]()
    esperar("del presupuesto a la venta",
            ([(x["producto_id"], x["cantidad"]) for x in st.session_state["venta_items"]],
             st.session_state["carrito"], st.session_state["pagina_actual"]),
            ([(ids["F100"], 3), (ids["J200"], 1)], {}, ns["PAGINAS"][9]))

    # Con la casilla «Se lleva»: pasa lo marcado, lo destildado queda en el presupuesto y sigue
    # destildado; sin nada marcado no se va a Ventas; sumarlo otra vez es que se lo lleva.
    st.session_state["venta_items"] = []
    st.session_state["pagina_actual"] = ns["PAGINAS"][0]
    st.session_state["carrito"] = {ids["F100"]: {"cantidad": 1}, ids["J200"]: {"cantidad": 2},
                                   ids["B300"]: {"cantidad": 1, "se_lleva": False}}
    st.session_state[f"se_lleva_{ids['J200']}"] = False
    ns["pasar_el_presupuesto_a_una_venta"]()
    esperar("solo lo que se lleva",
            ([x["producto_id"] for x in st.session_state["venta_items"]],
             sorted(st.session_state["carrito"]), ns["se_lleva"](ids["J200"]),
             ns["se_lleva"](ids["B300"]), st.session_state["pagina_actual"]),
            ([ids["F100"]], sorted([ids["J200"], ids["B300"]]), False, False, ns["PAGINAS"][9]))
    st.session_state["pagina_actual"] = ns["PAGINAS"][0]
    st.session_state.pop("_avisos", None)
    ns["pasar_el_presupuesto_a_una_venta"]()
    esperar("sin nada marcado, no pasa nada y avisa",
            (len(st.session_state["venta_items"]), len(st.session_state["carrito"]),
             st.session_state["pagina_actual"], [t for t, _ in st.session_state.get("_avisos", [])]),
            (1, 2, ns["PAGINAS"][0], ["warning"]))
    ns["sumar_al_presupuesto"]({"ID": ids["J200"], "Codigo": "J200", "Marca": "PRUEBA"})
    esperar("sumarlo otra vez lo marca", (ns["se_lleva"](ids["J200"]), ns["se_lleva"](ids["B300"]),
                                          st.session_state["carrito"][ids["J200"]]["cantidad"]),
            (True, False, 3))
    for clave in ("carrito", "venta_items", "_avisos"):
        st.session_state.pop(clave, None)

    # 8. LO 🔴 COMO REEMPLAZO, igual que «Se llevó»: sin confirmar no se vende; la pieza de
    # seguridad, ni confirmada. Y lo aprendido guarda el veredicto y cómo se vendió.
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio, "
              "precio_costo, stock) VALUES ('P400', 'P400', 'PASTILLA FRENO DEL. VW GOL', ?, "
              "5000, 6000, 2)", (marca,))
    ids["P400"] = c.lastrowid
    conn.commit()
    rojo = "🔴 no es la misma pieza"
    for nombre, it in (("🔴 sin confirmar", dict(item(ids["F100"]), veredicto=rojo)),
                       ("🔴 de seguridad, aunque se confirme",
                        dict(item(ids["P400"]), veredicto=rojo, confirmado=True))):
        try:
            ns["cerrar_venta"]([it])
            esperar(f"no se vende: {nombre}", "se vendió", "ValueError")
        except ValueError:
            pass
    st.session_state["venta_items"] = []
    ns["sumar_a_la_venta"]({"ID": ids["F100"]}, "OTRO-1", rojo, "cadena x", confirmado=True)
    ns["sumar_a_la_venta"]({"ID": ids["J200"]}, "OTRO-1", "🟡 probable", "cadena y")
    ns["sumar_a_la_venta"]({"ID": ids["J200"]}, "OTRO-1", "🟡 probable", "cadena y")
    esperar("sumar a la venta: con su veredicto, y otra vez suma la cantidad",
            [(x["producto_id"], x["cantidad"], x["veredicto"], x["confirmado"])
             for x in st.session_state["venta_items"]],
            [(ids["F100"], 1, rojo, True), (ids["J200"], 2, "🟡 probable", False)])
    # Y el campo de la cantidad se entera ANTES de dibujarse: si no, el navegador seguía
    # mostrando 1 y lo mandaba de vuelta (ver «LO QUE CAMBIA POR ATRÁS» en logica/interfaz.py).
    _campo = f"venta_cant_{ids['J200']}"
    st.session_state[_campo] = 1
    esperar("lo que cambia por atrás llega al campo",
            (ns["valor_del_campo"](_campo, 5), st.session_state[_campo],
             ns["valor_del_campo"](_campo, 5), ns["valor_del_campo"]("campo_nuevo_x", 7)),
            (None, 2, None, 7))
    st.session_state.pop(_campo, None)
    venta3, _ = ns["cerrar_venta"](st.session_state["venta_items"], "", "Transferencia")
    esperar("lo aprendido, como «Se llevó»: veredicto, cómo se vendió y la evidencia",
            [tuple(r) for r in c.execute("SELECT producto_id, termino_pedido, veredicto, como, "
                                         "evidencia FROM ventas_registradas WHERE venta_id = ? "
                                         "ORDER BY id", (venta3,))],
            [(ids["F100"], "OTRO-1", rojo, "alternativa", "cadena x"),
             (ids["J200"], "OTRO-1", "🟡 probable", "alternativa", "cadena y")])

    # 9. Lo que se terminó con la venta, lo que suele ir con lo vendido, y el cierre de caja.
    venta4, _ = ns["cerrar_venta"]([dict(item(ids["P400"]), cantidad=2), item(ids["J200"])],
                                   "", "Efectivo")
    esperar("lo que se terminó", ns["lo_que_se_termino"](venta4), [(ids["P400"], "PRUEBA P400")])
    esperar("el costo viaja con el ítem", item(ids["P400"])["costo"], 6000)
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio) "
              "VALUES ('K500', 'K500', 'KIT DE DISTRIBUCION GOL 1.6', ?, 30000), "
              "('A600', 'A600', 'BOMBA DE AGUA GOL 1.6', ?, 20000)", (marca, marca))
    conn.commit()
    kit = c.execute("SELECT id FROM productos WHERE codigo_raw = 'K500'").fetchone()[0]
    bomba = c.execute("SELECT id FROM productos WHERE codigo_raw = 'A600'").fetchone()[0]
    esperar("lo que suele ir con: lo que falta, y no lo que ya se lleva",
            (ns["lo_que_suele_ir_con_la_venta"]([item(kit)]),
             ns["lo_que_suele_ir_con_la_venta"]([item(kit), item(bomba)])),
            ([("PRUEBA K500", ["Bomba de agua"])], [("PRUEBA A600", ["Termostato"])]))
    caja = ns["cierre_de_caja"]()
    esperar("el cierre de caja: por forma de pago, lo anulado aparte",
            (caja["ventas"], caja["por_forma"], caja["anuladas"], caja["total_anulado"]),
            (3, [("Transferencia", 1, 15000.0), ("Efectivo", 1, 12500.0),
                 ("Sin decir", 1, 10000.0)], 1, 30500.0))
    esperar("y un día sin ventas", ns["cierre_de_caja"]("2001-01-01")["ventas"], 0)

    # 10. La ganancia, con el costo de ESE momento: si mañana cambia, la de hoy no se mueve.
    # Solo de lo que tiene costo cargado, y dice cuántos son.
    _ganancia = lambda: tuple(ns["cierre_de_caja"]()[k] for k in ("ganancia", "items_con_costo",
                                                                     "items"))
    esperar("la ganancia del día", _ganancia(), (-2000.0, 1, 5))
    c.execute("UPDATE productos SET precio_costo = 1 WHERE id = ?", (ids["P400"],))
    conn.commit()
    esperar("y no cambia con el costo de mañana", _ganancia(), (-2000.0, 1, 5))

    # 11. El comprobante para el cliente, en texto y en PDF; dice que no es una factura.
    _texto = ns["texto_del_comprobante"](venta4)
    esperar("el comprobante", (f"#{venta4}" in _texto, "TOTAL: $12.500 (Efectivo)" in _texto,
                               ns["NO_ES_FACTURA"] in _texto, "2× PRUEBA P400" in _texto,
                               ns["comprobante_para_descargar"](venta4)()[:5],
                               ns["texto_del_comprobante"](999999),
                               ns["comprobante_para_descargar"](999999)()),
            (True, True, True, True, b"%PDF-", "", b""))

    # 12. Escanear: el código de barras de UN producto se suma solo. Corto, con letras,
    # repetido en dos productos, o que no cierra (un número de fábrica mal cargado ahí), no.
    c.execute("UPDATE productos SET codigo_barras = '7791234567898' WHERE id = ?", (ids["F100"],))
    c.execute("UPDATE productos SET codigo_barras = '7790000000010' WHERE id IN (?, ?)",
              (ids["J200"], ids["B300"]))
    c.execute("UPDATE productos SET codigo_barras = '19011403' WHERE id = ?", (ids["P400"],))
    c.execute("UPDATE productos SET codigo_barras = '779123' WHERE id = ?", (kit,))
    conn.commit()
    barras = ns["producto_por_codigo_de_barras"]
    esperar("escanear", [barras(x) for x in ("7791234567898", " 7791234567898 ", "779123",
                                             "77912345678AB", "7790000000010", "19011403", "")],
            [ids["F100"], ids["F100"], None, None, None, None, None])

    # 13. Lo que más se vende: sin las anuladas, por unidades y por plata, día por día.
    mv = ns["lo_mas_vendido"](7)
    esperar("lo que más se vende",
            (mv["ventas"], mv["total"], mv["ticket_promedio"], mv["ganancia"], len(mv["por_dia"]),
             mv["por_dia"][-1][1], [p["codigo"] for p in mv["por_unidades"]],
             [p["codigo"] for p in mv["por_plata"]]),
            (3, 37500.0, 12500.0, -2000.0, 7, 37500.0, ["J200", "F100", "P400"],
             ["F100", "P400", "J200"]))

    # 14. DEVOLVER ALGO DE UNA VENTA: una cosa y una cantidad. Vuelve al stock salvo que no se
    # pueda volver a vender; la plata sale del cierre de hoy, por donde entró; lo vendido EN
    # LUGAR DE otro código y que no le iba baja ese vínculo; lo devuelto entero sale de lo
    # aprendido.
    def item_de(venta_id, pid):
        return c.execute("SELECT id FROM ventas_items WHERE venta_id = ? AND producto_id = ?",
                         (venta_id, pid)).fetchone()[0]
    devolver = ns["devolver_de_una_venta"]
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
              "VALUES ('OTRO-1', 'OTRO1', 'FILTRO ACEITE', ?)", (marca,))
    otro_1 = c.lastrowid
    c.execute("INSERT INTO equivalencias (producto_a_id, producto_b_id, confianza) "
              "VALUES (?, ?, 90)", (min(otro_1, ids["F100"]), max(otro_1, ids["F100"])))
    conn.commit()
    _stock_f, _stock_p = stock(ids["F100"]), stock(ids["P400"])
    _j_v4, _p_v4 = item_de(venta4, ids["J200"]), item_de(venta4, ids["P400"])
    esperar("lo que no se puede devolver",
            ["de 1 a 1" in devolver(_j_v4, 2, "no_le_iba")[1], devolver(_j_v4, 0, "no_le_iba")[0],
             devolver(_j_v4, 1, "inventado")[0], devolver(999999, 1, "otro")[0]],
            [True, False, False, False])
    ok_j, _ = devolver(_j_v4, 1, "no_le_iba")
    ok_p1, texto_p1 = devolver(_p_v4, 1, "fallada")
    ok_p2, _ = devolver(_p_v4, 1, "medida")
    ok_f, texto_f = devolver(item_de(venta3, ids["F100"]), 1, "medida", "otra rosca")
    esperar("devolver: el stock (lo fallado no vuelve; el sin stock cargado no se toca)",
            (ok_j, ok_p1, ok_p2, ok_f, stock(ids["J200"]), stock(ids["P400"]) - _stock_p,
             stock(ids["F100"]) - _stock_f, "no vuelve al stock" in texto_p1,
             devolver(_j_v4, 1, "otro")[0]),
            (True, True, True, True, None, 1, 1, True, False))
    esperar("devolver: lo vendido en lugar de otro código y que no le iba baja ese vínculo",
            (c.execute("SELECT confianza FROM equivalencias WHERE producto_a_id = ? AND "
                       "producto_b_id = ?", (min(otro_1, ids["F100"]),
                                             max(otro_1, ids["F100"]))).fetchone()[0]
             <= ns["TOPE_CON_VETO"], "bajó" in texto_f,
             c.execute("SELECT COUNT(*) FROM devoluciones WHERE codigo_pedido_clean = 'OTRO1'")
             .fetchone()[0],
             c.execute("SELECT COUNT(*) FROM ventas_registradas WHERE venta_id = ?",
                       (venta4,)).fetchone()[0]),
            (True, True, 1, 0))
    caja = ns["cierre_de_caja"]()
    esperar("devolver: la plata sale del cierre de hoy, por donde entró",
            (caja["total"], caja["devoluciones"], caja["total_devuelto"], caja["por_forma"],
             caja["ganancia"]),
            (37500.0 - 22500.0, 4, 22500.0,
             [("Sin decir", 1, 10000.0), ("Transferencia", 1, 5000.0), ("Efectivo", 1, 0.0)],
             -2000.0 + 2000.0))
    esperar("con devoluciones no se anula", ns["anular_venta"](venta4)[0], False)
    esperar("lo devuelto, en el comprobante",
            "(devueltos: 2)" in ns["texto_del_comprobante"](venta4), True)
    esperar("buscar una venta: por número, por el cliente de la ficha, por patente; nada con "
            "nada, y la anulada no",
            ([v["id"] for v in ns["buscar_ventas"](f"#{venta4}")],
             [v["id"] for v in ns["buscar_ventas"]("Juan")],
             [v["id"] for v in ns["buscar_ventas"]("ae 777 zz")], ns["buscar_ventas"]("  ")),
            ([venta4], [venta2], [venta2], []))

    # 15. El arqueo: lo contado contra el efectivo que dice el sistema.
    esperar("efectivo esperado", ns["efectivo_esperado"](), 0.0)
    _arq = ns["arquear_la_caja"](None, 100, "un vuelto de más")
    esperar("el arqueo", (_arq, ns["arquear_la_caja"](None, -1)[0],
                          ns["arquear_la_caja"](None, "mucho")[0],
                          [(a["efectivo_contado"], a["diferencia"], a["nota"])
                           for a in ns["arqueos_del_dia"]()]),
            ((True, "Sobran $100."), False, False, [(100.0, 100.0, "un vuelto de más")]))

    # 16. Lo que se va a terminar con lo que se vende: lo que quedó en 0 primero, lo que
    # alcanza para unos días después, lo que alcanza para más de una semana no; y si ya se
    # anotó para reponer. Con más efectivo en la caja, el arqueo cuenta la diferencia.
    c.execute("UPDATE productos SET stock = 6 WHERE id = ?", (kit,))
    conn.commit()
    ns["cerrar_venta"]([item(ids["B300"]), dict(item(kit), cantidad=5)], "", "Efectivo")
    _por_terminar = lambda: [(f["nombre"], f["stock"], f["alcanza_dias"], f["anotado"])
                             for f in ns["lo_que_se_va_a_terminar"]()]
    esperar("lo que se va a terminar", _por_terminar(),
            [("PRUEBA B300", 0, 0, False), ("PRUEBA K500", 1, 6, False)])
    ns["solicitar_reposicion"](ids["B300"])
    esperar("y ya anotado para reponer", _por_terminar()[0], ("PRUEBA B300", 0, 0, True))
    esperar("el arqueo con efectivo", (ns["efectivo_esperado"](),
                                       ns["arquear_la_caja"](None, 152500)),
            (153000.0, (True, "Faltan $500.")))
    st.session_state.pop("venta_items", None)

    # 7. Quién puede: vender y anotar, empleado; anular, administrador.
    originales = (g["_nivel_de_quien_esta_adentro"], g["hay_claves_configuradas"])
    g["hay_claves_configuradas"] = lambda: True
    try:
        for nivel, puede_vender, puede_anular in (("", False, False), ("mecanico", False, False),
                                                   ("operador", True, False), ("admin", True, True)):
            g["_nivel_de_quien_esta_adentro"] = lambda n=nivel: n
            resultado = []
            for funcion, args in ((ns["cerrar_venta"], ([item(ids["J200"])],)),
                                  (ns["anotar_la_venta_en_el_auto"], (999999, "AB123CD", 1)),
                                  (ns["anular_venta"], (999999,))):
                try:
                    funcion(*args)
                    resultado.append(True)
                except PermissionError:
                    resultado.append(False)
            esperar(f"nivel «{nivel or 'invitado'}»: vender, anotar, anular", resultado,
                    [puede_vender, puede_vender, puede_anular])
    finally:
        g["_nivel_de_quien_esta_adentro"], g["hay_claves_configuradas"] = originales
    return fallas


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_ventas_")
    try:
        fallas = probar(_cargar_la_logica(carpeta))
        for f in fallas:
            print("   ✗", f)
        print("✅ ventas: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

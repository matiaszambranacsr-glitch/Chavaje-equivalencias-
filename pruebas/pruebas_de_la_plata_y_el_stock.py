"""Pruebas de lo que mueve plata y stock y no tenía prueba.

Uso:
    python3 pruebas/pruebas_de_la_plata_y_el_stock.py

Apartar contra el stock libre, cerrar un apartado vendido o caído, fusionar dos productos
duplicados sin perder lo que apunta al que se va (los apartados activos, las ventas, los pedidos
al depósito), el mejor margen entre equivalentes, los pagos y cargos de las cuentas corrientes y
su resumen, y el presupuesto del mecánico.

Corre en una carpeta temporal: nunca toca la base de trabajo.
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
    fallas = []

    def esperar(nombre, real, esperado):
        if real != esperado:
            fallas.append(f"{nombre}: dio {real!r}, se esperaba {esperado!r}")

    def uno(sql, *args):
        fila = c.execute(sql, args).fetchone()
        return fila[0] if fila else None

    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('PRUEBA', 'PROVEEDOR')")
    marca = c.lastrowid
    ids = {}
    for codigo, precio, stock in (("A1", None, 5), ("B1", 9000, 2), ("C1", 100, None),
                                  ("D1", 100, None)):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio, "
                  "stock) VALUES (?, ?, 'FILTRO ACEITE', ?, ?, ?)",
                  (codigo, codigo, marca, precio, stock))
        ids[codigo] = c.lastrowid
    conn.commit()
    a, b = ids["A1"], ids["B1"]

    # 1. Apartar contra el stock LIBRE (el total menos lo apartado), y cerrar el apartado.
    ok1, _ = ns["reservar_stock"](a, 2, "Juan")
    ok2, msg2 = ns["reservar_stock"](a, 4, "Pedro")
    esperar("apartar: entra lo que hay libre, lo que no alcanza no",
            (ok1, ok2, ns["stock_libre_de_varios"]([a, None])),
            (True, False, {a: 3}))
    _apartados = ns["reservas_activas"]()
    esperar("lo apartado, a la vista", [(r["Código"], r["Apartadas"], r["Cliente"])
                                        for r in _apartados], [("A1", 2, "Juan")])
    ns["cerrar_reserva"](_apartados[0]["_id"], True)
    ns["reservar_stock"](a, 1, "Pedro")
    _otro = ns["reservas_activas"]()[0]["_id"]
    ns["cerrar_reserva"](_otro, False)
    esperar("vendido descuenta, caído solo libera, y dos veces no",
            (uno("SELECT stock FROM productos WHERE id = ?", a), ns["stock_libre_de_varios"]([a]),
             ns["cerrar_reserva"](_otro, True), uno("SELECT stock FROM productos WHERE id = ?", a)),
            (3, {a: 3}, False, 3))

    # 2. FUSIONAR DOS DUPLICADOS sin perder lo que apunta al que se va. La base lo borraba con
    # él (ON DELETE CASCADE): el apartado activo, la venta aprendida, el pedido al depósito, la
    # ficha del auto. Y los pendientes, aunque la función decía que no se perdían.
    ns["reservar_stock"](b, 1, "Ana")
    ns["registrar_venta"](b, "B1")
    ns["pedir_al_deposito"](b, 1, usuario="mostrador")
    venta, _ = ns["cerrar_venta"]([ns["item_de_venta"](b)])
    c.execute("INSERT INTO vehiculos (patente) VALUES ('AB123CD')")
    auto = c.lastrowid
    c.execute("INSERT INTO historial_piezas (vehiculo_id, producto_id, descripcion_pieza) "
              "VALUES (?, ?, 'Filtro aceite')", (auto, b))
    for pid in (a, b):
        ns["solicitar_reposicion"](pid)
    c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, lote) "
              "VALUES (?, ?, 'prueba', 'L1')", (min(b, ids["C1"]), max(b, ids["C1"])))
    c.execute("INSERT INTO equivalencias (producto_a_id, producto_b_id) VALUES (?, ?)",
              (min(b, ids["D1"]), max(b, ids["D1"])))
    conn.commit()
    esperar("se fusionó", ns["fusionar_productos"](b, a), True)
    esperar("lo que apuntaba al que se fue, ahora al que queda",
            (uno("SELECT COUNT(*) FROM reservas_stock WHERE producto_id = ? AND estado = 'activa'", a),
             uno("SELECT COUNT(*) FROM ventas_registradas WHERE producto_id = ?", a),
             uno("SELECT COUNT(*) FROM pedidos_deposito WHERE producto_id = ?", a),
             uno("SELECT producto_id FROM ventas_items WHERE venta_id = ?", venta),
             uno("SELECT producto_id FROM historial_piezas WHERE vehiculo_id = ?", auto),
             uno("SELECT COUNT(*) FROM pedidos_reposicion WHERE producto_id = ?", a)),
            (1, 2, 1, a, a, 1))
    esperar("los vínculos y los pendientes pasan, sin el producto que se fue",
            (uno("SELECT COUNT(*) FROM equivalencias WHERE producto_a_id = ? AND producto_b_id = ?",
                 min(a, ids["D1"]), max(a, ids["D1"])),
             uno("SELECT lote FROM equivalencias_pendientes WHERE producto_a_id = ? AND "
                 "producto_b_id = ?", min(a, ids["C1"]), max(a, ids["C1"])),
             uno("SELECT COUNT(*) FROM productos WHERE id = ?", b),
             uno("SELECT COUNT(*) FROM equivalencias_pendientes WHERE ? IN (producto_a_id, "
                 "producto_b_id)", b)),
            (1, "L1", 0, 0))
    esperar("el que queda: su stock, y el precio que le faltaba",
            tuple(c.execute("SELECT stock, precio FROM productos WHERE id = ?", (a,)).fetchone()),
            (3, 9000))

    # 3. El mejor margen entre equivalentes con stock: no cuenta lo que volvió, ni con menos de
    # dos para comparar, ni si dejan lo mismo.
    def fila(cod, precio, costo, stock=1, **extra):
        return dict({"Codigo": cod, "Marca": "M", "Precio": precio, "_costo": costo,
                     "Stock": stock, "Cadena": "— el buscado"}, **extra)
    margen = ns["mejor_margen_entre_equivalentes"]
    esperar("mejor margen",
            (margen([fila("X", 1000, 600), fila("Y", 1200, 700), fila("Z", 5000, 100, 0)]),
             margen([fila("X", 1000, 600), fila("Y", 2000, 100, Devuelto=True)]),
             margen([fila("X", 1000, 600), fila("Y", 900, 500)])),
            ({"codigo": "Y", "marca": "M", "ganancia": 500, "diferencia": 100}, None, None))

    # 4. Las cuentas corrientes: lo que no es un pago no entra, el cheque queda en cartera, y
    # el resumen pone primero al que más debe vencido.
    ns["crear_mecanico"]("Taller Norte", "clave-norte-1")
    ns["crear_mecanico"]("Taller Sur", "clave-sur-1")
    norte = uno("SELECT id FROM mecanicos WHERE nombre = 'Taller Norte'")
    sur = uno("SELECT id FROM mecanicos WHERE nombre = 'Taller Sur'")
    pago = ns["registrar_pago_de_cuenta"]
    esperar("pagos que no entran",
            [pago(norte, x, m, cheque_fecha=f)[0] for x, m, f in
             (("mucho", "Efectivo", None), (0, "Efectivo", None), (100, "Trueque", None),
              (100, "Cheque", None))], [False, False, False, False])
    esperar("cargos que no entran",
            [ns["cargar_a_la_cuenta"](norte, "x", v)[0] for v in ("mucho", 0, -5)],
            [False, False, False])
    c.execute("""INSERT INTO movimientos_de_cuenta (mecanico_id, concepto, importe, vence, usuario)
                 VALUES (?, 'viejo', 50000, date('now', '-40 days'), 'x'),
                        (?, 'nuevo', 80000, date('now', '+20 days'), 'x')""", (norte, sur))
    conn.commit()
    ok_ch, _ = pago(norte, 10000, "Cheque", cheque_fecha="2099-01-01")
    _estado = ns["estado_de_cuenta"](norte)
    esperar("el cheque descuenta ya y queda en cartera",
            (ok_ch, _estado["saldo"], _estado["cheques_en_cartera"]), (True, 40000.0, 10000.0))
    esperar("el resumen: primero el que debe vencido",
            [(x["Taller"], x["Vencido"] > 0) for x in ns["resumen_de_cuentas"]()],
            [("Taller Norte", True), ("Taller Sur", False)])
    # Todos los movimientos y todos los apartados, no los primeros 200: el resumen de la cuenta
    # escondía los viejos, y pasando los 200 apartados los más viejos no se podían cerrar.
    c.executemany("INSERT INTO movimientos_de_cuenta (mecanico_id, concepto, importe, usuario) "
                  "VALUES (?, 'repuesto', 100, 'x')", [(sur,)] * 250)
    c.executemany("INSERT INTO reservas_stock (producto_id, cantidad, cliente) VALUES (?, 1, ?)",
                  [(uno("SELECT MIN(id) FROM productos"), f"cliente {i}") for i in range(205)])
    conn.commit()
    _movs_sur = ns["movimientos_de_cuenta"](sur)
    esperar("la cuenta muestra todos los movimientos, y el saldo de arriba es el de todos",
            (len(_movs_sur), _movs_sur[0]["Saldo"]), (251, 80000.0 + 250 * 100))
    esperar("todos los apartados",
            sum(1 for r in ns["reservas_activas"]() if (r["Cliente"] or "").startswith("cliente ")),
            205)
    c.execute("DELETE FROM reservas_stock WHERE cliente LIKE 'cliente %'")
    conn.commit()

    # 5. El presupuesto del mecánico en PDF, y sumar al presupuesto del mostrador.
    _pdf = ns["generar_pdf_presupuesto_mecanico"](
        "Taller Norte", "Cliente", [{"codigo": "A1", "marca": "PRUEBA", "precio": 1000,
                                     "cantidad": 2}], 5000, 7000)
    esperar("el PDF del presupuesto", (_pdf[:5], len(_pdf) > 1000), (b"%PDF-", True))
    st.session_state.pop("carrito", None)
    _f = {"ID": a, "Codigo": "A1", "Marca": "PRUEBA", "Precio": 9000}
    ns["sumar_al_presupuesto"](_f)
    ns["sumar_al_presupuesto"](_f, 2)
    esperar("sumar al presupuesto: dos veces el mismo suma la cantidad",
            (len(st.session_state["carrito"]), st.session_state["carrito"][a]["cantidad"]), (1, 3))
    st.session_state.pop("carrito", None)

    # 6. EL COSTO CON LA BONIFICACIÓN DEL PROVEEDOR (ver datos.py): se calcula para lo que no
    # tiene costo, sigue al precio cuando entra un aumento, lo nuevo entra con su costo, lo
    # cargado a mano no se toca nunca, y sacarla saca solo lo calculado.
    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('BONIF', 'PROVEEDOR')")
    _mb = c.lastrowid
    _pb = {}
    for codigo, precio in (("BO1", 1000), ("BO2", 2000), ("BO3", None)):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio) "
                  "VALUES (?, ?, 'JUNTA', ?, ?)", (codigo, codigo, _mb, precio))
        _pb[codigo] = c.lastrowid
    conn.commit()
    ns["actualizar_precio_stock"](_pb["BO2"], 2000, None, costo=1500)
    _costo = lambda cod: tuple(c.execute("SELECT precio_costo, costo_origen FROM productos "
                                         "WHERE id = ?", (_pb[cod],)).fetchone())
    esperar("calcula lo que no tiene costo, y no toca lo cargado a mano",
            (ns["guardar_bonificacion_del_proveedor"](_mb, 30), _costo("BO1"), _costo("BO2"),
             _costo("BO3")),
            (1, (700.0, "bonificacion"), (1500.0, "mano"), (None, None)))
    ns["aumentar_precios_por_marca"](_mb, 10)
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio) "
              "VALUES ('BO4', 'BO4', 'JUNTA', ?, 500)", (_mb,))
    _pb["BO4"] = c.lastrowid
    conn.commit()
    esperar("sigue al aumento, y lo nuevo entra con su costo",
            (_costo("BO1"), _costo("BO2"), _costo("BO4")),
            ((770.0, "bonificacion"), (1500.0, "mano"), (350.0, "bonificacion")))
    esperar("sacarla saca solo lo calculado",
            (ns["guardar_bonificacion_del_proveedor"](_mb, None), _costo("BO1"), _costo("BO2")),
            (2, (None, None), (1500.0, "mano")))

    # 7. Qué tan completo está el catálogo (ver que_tan_completo_esta_el_catalogo()): por lista,
    # con la fila «Todas» al final. BONIF tiene 4 productos, 3 con precio y 1 con costo a mano.
    _completo = ns["que_tan_completo_esta_el_catalogo"]()
    _bonif = next(f for f in _completo if f["Marca"] == "BONIF")
    esperar("qué tan completo: lo de una lista, y «Todas» al final",
            ((_bonif["Productos"], _bonif["Precio"], _bonif["Costo"]), _completo[-1]["Marca"],
             _completo[-1]["Productos"] == sum(f["Productos"] for f in _completo[:-1])),
            ((4, 3, 1), "Todas", True))

    # 8. El historial de precios: lo atrasada que está cada lista (envejecimiento_de_precios())
    # y los códigos que vinieron dos veces con dos precios en la misma lista
    # (codigos_con_dos_precios_en_la_misma_lista()). Las dos miran solo los productos con dos
    # precios anotados o más; los de uno solo, que son casi todos, tienen que dar lo mismo.
    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('HISTO', 'PROVEEDOR')")
    _mh = c.lastrowid

    def _con_historial(codigo, *precios_y_dias):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio) "
                  "VALUES (?, ?, 'BUJIA', ?, ?)", (codigo, codigo, _mh, precios_y_dias[-1][0]))
        _pid = c.lastrowid
        for _precio, _hace in precios_y_dias:
            c.execute("INSERT INTO historial_precios (producto_id, precio, fecha) "
                      "VALUES (?, ?, datetime('now', ?))", (_pid, _precio, _hace))
        return _pid
    for i in range(25):          # subieron 10% de una lista a la otra, 30 días después
        _con_historial(f"H{i}", (1000, "-31 days"), (1100, "-1 days"))
    for i in range(5):           # un solo precio: no dicen nada del ritmo
        _con_historial(f"U{i}", (5000, "-1 days"))
    # La misma lista lo trajo dos veces, con dos precios: queda el último y se avisa. Y otro
    # con dos precios pero de dos listas distintas, que no es eso.
    _doble = _con_historial("D9", (100, "-1 days"), (500, "-1 days"))
    _con_historial("E9", (100, "-40 days"), (300, "-1 days"))
    conn.commit()
    _histo = next(f for f in ns["envejecimiento_de_precios"]() if f["Lista"] == "HISTO")
    esperar("la lista sube 10% por mes, con su propio historial",
            (round(_histo["_ritmo"] or 0, 3), _histo["_dias"]), (0.1, 1))
    esperar("dos precios en la misma lista: solo ese",
            [(f["ID"], f["Precios en la lista"]) for f in
             ns["codigos_con_dos_precios_en_la_misma_lista"]() if f["Marca"] == "HISTO"],
            [(_doble, " / ".join(ns["formato_precio"](x) for x in (100, 500)))])

    # 9. Elegir el precio de los que vinieron dos veces (ver elegir_el_precio_doble()):
    # cambiarlo lo guarda como un cambio a mano; dejar el que quedó no toca nada; los dos salen
    # de la lista. Si otro lo cambió mientras tanto, no se pisa. Y si otra lista lo vuelve a
    # traer doble, vuelve.
    _otro = _con_historial("D8", (200, "-1 days"), (900, "-1 days"))
    _tercero = _con_historial("D7", (50, "-1 days"), (70, "-1 days"))
    conn.commit()

    def _en_la_lista():
        return sorted(f["ID"] for f in ns["codigos_con_dos_precios_en_la_misma_lista"]()
                      if f["Marca"] == "HISTO")
    _precio = lambda pid: uno("SELECT precio FROM productos WHERE id = ?", pid)
    esperar("los tres para elegir", _en_la_lista(), sorted([_doble, _otro, _tercero]))
    esperar("cambiar a otro precio", ns["elegir_el_precio_doble"](_doble, 100, 500)[0], True)
    esperar("queda ese precio, con su renglón en el historial",
            (_precio(_doble), uno("SELECT COUNT(*) FROM historial_precios WHERE producto_id = ?",
                                  _doble)), (100, 3))
    esperar("dejar el que quedó", ns["elegir_el_precio_doble"](_otro, 900, 900)[0], True)
    esperar("no lo toca", (_precio(_otro), uno(
        "SELECT COUNT(*) FROM historial_precios WHERE producto_id = ?", _otro)), (900, 2))
    esperar("si otro lo cambió mientras tanto, no se pisa",
            (ns["elegir_el_precio_doble"](_tercero, 50, 60)[0], _precio(_tercero)), (False, 70))
    esperar("los elegidos salen de la lista", _en_la_lista(), [_tercero])
    c.execute("INSERT INTO historial_precios (producto_id, precio, fecha) VALUES "
              "(?, 500, datetime('now', '+1 hours')), (?, 990, datetime('now', '+1 hours'))",
              (_otro, _otro))
    conn.commit()
    esperar("otra lista lo trae doble: vuelve", _en_la_lista(), sorted([_otro, _tercero]))
    return fallas


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_plata_stock_")
    try:
        fallas = probar(_cargar_la_logica(carpeta))
        for f in fallas:
            print("   ✗", f)
        print("✅ plata y stock: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

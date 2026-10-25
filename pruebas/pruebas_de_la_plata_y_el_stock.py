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

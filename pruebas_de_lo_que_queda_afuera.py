"""Pruebas de lo que queda afuera: cada uno responde por lo que pidió al depósito.

Uso:
    python3 pruebas_de_lo_que_queda_afuera.py

Lo que el depósito entrega para Mostrador queda a nombre de quien lo pidió hasta que lo vende
en 🧾 Ventas (sin bajar el stock otra vez), se factura o vuelve al depósito con su clave. Lo de
un taller ya está en su cuenta: si vuelve, con su código de retiro o su clave, se le acredita.
Ver «LO QUE QUEDA AFUERA» en logica/deposito.py.

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
    fallas = []

    def esperar(nombre, real, esperado):
        if real != esperado:
            fallas.append(f"{nombre}: dio {real!r}, se esperaba {esperado!r}")

    def uno(sql, *args):
        fila = c.execute(sql, args).fetchone()
        return fila[0] if fila else None

    def como(persona, nivel="operador"):
        st.session_state["admin_nombre"] = persona
        st.session_state["nivel_usuario"] = nivel

    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('PRUEBA', 'PROVEEDOR')")
    marca = c.lastrowid
    ids = {}
    for codigo, precio, stock in (("A1", 1000, 5), ("B1", 500, None)):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio, "
                  "stock) VALUES (?, ?, 'FILTRO ACEITE', ?, ?, ?)",
                  (codigo, codigo, marca, precio, stock))
        ids[codigo] = c.lastrowid
    conn.commit()
    a, b = ids["A1"], ids["B1"]
    ns["crear_usuario"]("ana", "clave-ana-1", "operador")
    ns["crear_usuario"]("beto", "clave-beto-1", "operador")
    ns["crear_usuario"]("jefe", "clave-jefe-1", "admin")
    ns["crear_mecanico"]("Taller Norte", "clave-norte-1")
    ns["crear_mecanico"]("Taller Sur", "clave-sur-1")
    taller = uno("SELECT id FROM mecanicos WHERE nombre = 'Taller Norte'")
    stock = lambda pid: uno("SELECT stock FROM productos WHERE id = ?", pid)

    def pedir_y_entregar(pid, cantidad, persona, mecanico_id=None):
        como(persona)
        ns["pedir_al_deposito"](pid, cantidad, mecanico_id=mecanico_id, usuario=persona,
                                retiro_autorizado=True)
        pedido = uno("SELECT MAX(id) FROM pedidos_deposito")
        ns["entregar_pedido"](pedido, usuario="deposito")
        return pedido

    # 1. Lo entregado para Mostrador queda a nombre de quien lo pidió.
    p1 = pedir_y_entregar(a, 3, "ana")
    esperar("entregado: baja el stock y queda a nombre de ana",
            (stock(a), [(r["id"], r["queda"], r["quien"]) for r in ns["lo_que_tiene"](persona="ana")],
             ns["lo_que_tiene"](persona="beto"),
             uno("SELECT COUNT(*) FROM ventas_registradas WHERE pedido_id = ?", p1)),
            (2, [(p1, 3, "ana")], [], 1))

    # 2. Si ana lo vende en 🧾 Ventas, sale de lo que tiene y el stock NO baja otra vez; lo
    # aprendido al entregarlo pasa a ser lo de la venta (no se anota dos veces).
    como("ana")
    venta, _ = ns["cerrar_venta"]([dict(ns["item_de_venta"](a, 2, "W712"))])
    esperar("vendido de lo que tenía: el stock no baja dos veces",
            (stock(a), [r["queda"] for r in ns["lo_que_tiene"](persona="ana")],
             uno("SELECT stock_descontado FROM ventas_items WHERE venta_id = ?", venta),
             uno("SELECT COUNT(*) FROM ventas_registradas WHERE producto_id = ?", a),
             uno("SELECT termino_pedido FROM ventas_registradas WHERE pedido_id = ?", p1),
             uno("SELECT venta_id FROM ventas_registradas WHERE pedido_id = ?", p1)),
            (2, [1], 0, 1, "W712", venta))
    # Y si vende más de lo que tiene, lo que falta sale del stock.
    venta_b, _ = ns["cerrar_venta"]([dict(ns["item_de_venta"](a, 2))])
    esperar("vende más de lo que tiene: el resto baja del stock",
            (stock(a), ns["lo_que_tiene"](persona="ana"),
             uno("SELECT stock_descontado FROM ventas_items WHERE venta_id = ?", venta_b)),
            (1, [], 1))

    # 3. Anular devuelve a su nombre lo que había salido de lo que tenía (no al stock), y se
    # lleva solo lo aprendido de ESA venta: lo de la primera queda.
    ns["anular_venta"](venta_b)
    esperar("anulada: vuelve a estar a nombre de ana, y al stock solo lo que bajó",
            (stock(a), [r["queda"] for r in ns["lo_que_tiene"](persona="ana")],
             [r[0] for r in c.execute("SELECT venta_id FROM ventas_registradas "
                                      "WHERE producto_id = ?", (a,))]), (2, [1], [venta]))

    # 4. Para que vuelva al depósito hace falta SU clave (o la de un administrador).
    como("beto")
    devolver = ns["devolver_al_deposito"]
    esperar("con la clave de otro, sin clave, o de más, no vuelve",
            [devolver(p1, 1, "clave-beto-1")[0], devolver(p1, 1, "")[0],
             "de 1 a 1" in devolver(p1, 2, "clave-ana-1")[1],
             devolver(p1, 1, "clave-norte-1")[0]],
            [False, False, True, False])
    ok, texto = devolver(p1, 1, "clave-ana-1")
    esperar("con la clave de ana vuelve: el stock sube, ya no está a su nombre",
            (ok, stock(a), ns["lo_que_tiene"](persona="ana"),
             uno("SELECT devolvio || ' / ' || como || ' / ' || recibio "
                 "FROM devoluciones_al_deposito WHERE pedido_id = ?", p1),
             uno("SELECT COUNT(*) FROM ventas_registradas WHERE pedido_id = ?", p1),
             devolver(p1, 1, "clave-ana-1")[0]),
            (True, 3, [], "ana / su clave / beto", 1, False))

    # 5. Con la de un administrador también, y queda dicho; lo que vuelve entero sin haberse
    # vendido se lleva lo aprendido; sin stock cargado, el stock no se toca.
    p2 = pedir_y_entregar(b, 1, "ana")
    ok, texto = devolver(p2, 1, "clave-jefe-1")
    esperar("con la clave del administrador",
            (ok, "clave de administrador" in texto, stock(b),
             uno("SELECT COUNT(*) FROM ventas_registradas WHERE pedido_id = ?", p2)),
            (True, True, None, 0))

    # 6. Lo facturado ya no está afuera.
    p3 = pedir_y_entregar(a, 1, "ana")
    ns["marcar_facturado"]([p3])
    esperar("facturado: ya no está a su nombre ni vuelve",
            (ns["lo_que_tiene"](persona="ana"), devolver(p3, 1, "clave-ana-1")[0]), ([], False))

    # 7. Un taller: ya está cargado en su cuenta; si vuelve, con su código de retiro (que se
    # gasta) o su clave, se le acredita lo que se le había cargado.
    p4 = pedir_y_entregar(a, 2, "beto", mecanico_id=taller)
    saldo = lambda: ns["estado_de_cuenta"](taller)["saldo"]
    esperar("al taller: cargado en su cuenta, y está afuera a su nombre",
            (saldo(), [(r["queda"], r["quien"]) for r in ns["lo_que_tiene"](mecanico_id=taller)]),
            (2000.0, [(2, "Taller Norte")]))
    codigo, _ = ns["generar_codigo_de_retiro"](taller)
    esperar("con la clave de un empleado, la de otro taller o un código que no es, no",
            [devolver(p4, 1, "clave-beto-1")[0], devolver(p4, 1, "clave-sur-1")[0],
             devolver(p4, 1, "000000")[0]], [False, False, False])
    ok, texto = devolver(p4, 1, codigo)
    esperar("con su código de retiro: se acredita, y el código no sirve dos veces",
            (ok, saldo(), "1.000" in texto, devolver(p4, 1, codigo)[0],
             [(k[1], [(r["cantidad"], r["importe"]) for r in v])
              for k, v in ns["para_facturar"]().items() if k[0] == taller]),
            (True, 1000.0, True, False, [("Taller Norte", [(1, 1000.0)])]))
    ok, _ = devolver(p4, 1, "clave-norte-1")
    esperar("con la clave del taller, lo que queda: la cuenta en 0 y nada para facturar",
            (ok, saldo(), stock(a), [k for k in ns["para_facturar"]() if k[0] == taller]),
            (True, 0.0, 2, []))

    # 8. Quién tiene qué, y lo de cada cuenta.
    p5 = pedir_y_entregar(a, 1, "beto")
    esperar("quién tiene que devolver",
            [(g["quien"], g["unidades"], g["valor"]) for g in ns["quien_tiene_que_devolver"]()],
            [("beto", 1, 1000.0)])
    r_ana = ns["resumen_de_la_cuenta"](persona="ana")
    r_taller = ns["resumen_de_la_cuenta"](mecanico_id=taller)
    esperar("lo de cada cuenta",
            ([v["id"] for v in r_ana["ventas"]], r_ana["total"], r_ana["afuera"],
             len(r_taller["entregas"]), r_taller["total"], r_taller["devuelto"],
             r_taller["saldo"]),
            ([venta], 2000.0, [], 1, 2000.0, 2000.0, 0.0))
    como("beto", "operador")
    esperar("un empleado ve solo lo suyo", [x[1:] for x in ns["cuentas_para_mirar"]()],
            [("beto", None)])
    como("jefe", "admin")
    _todas = ns["cuentas_para_mirar"]()
    esperar("el administrador ve a todos", ({x[1] for x in _todas if x[1]} >= {"ana", "beto"},
                                            (None, taller) in [x[1:] for x in _todas]),
            (True, True))
    devolver(p5, 1, "clave-beto-1")
    for k in ("admin_nombre", "nivel_usuario"):
        st.session_state.pop(k, None)
    return fallas


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_afuera_")
    try:
        fallas = probar(_cargar_la_logica(carpeta))
        for f in fallas:
            print("   ✗", f)
        print("✅ lo que queda afuera: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

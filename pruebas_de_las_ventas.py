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

    # 5. Anular devuelve al stock lo que se descontó (no lo que se vendió de más), una vez.
    ok_an, _ = ns["anular_venta"](venta)
    esperar("anulada: vuelve lo descontado", (ok_an, stock(ids["F100"]), stock(ids["J200"]),
                                              stock(ids["B300"]), ns["anular_venta"](venta)[0]),
            (True, 4, None, 1, False))
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

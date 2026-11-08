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

    # 9. LO QUE FALTA CARGAR PARA VENDER (ver diagnostico_de_salud()): sin el WhatsApp del
    # negocio, sin alias y con una lista sin costo, la salud se lo dice al administrador (y a
    # nadie más); cargados el WhatsApp y la bonificación, esos avisos se van.
    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('SINCOSTO', 'PROVEEDOR')")
    _msc = c.lastrowid
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio) "
              "VALUES ('SC1', 'SC1', 'JUNTA', ?, 800)", (_msc,))
    conn.commit()

    def _config9():
        _pr = ns["diagnostico_de_salud"]()
        _wa = [p["solo_admin"] for p in _pr if "WhatsApp del negocio" in p["titulo"]]
        _alias = [p["solo_admin"] for p in _pr if "alias para cobrar" in p["titulo"]]
        _costo9 = any("sin costo" in p["titulo"] and "SINCOSTO" in p["detalle"] for p in _pr)
        return _wa, _alias, _costo9
    esperar("sin WhatsApp, sin alias y una lista sin costo: los tres avisos, al administrador",
            _config9(), ([True], [True], True))
    ns["guardar_config"]("whatsapp_del_negocio", "5491145678901")
    ns["guardar_bonificacion_del_proveedor"](_msc, 25)
    esperar("cargados el WhatsApp y la bonificación, esos dos se van", _config9(),
            ([], [True], False))

    # 10. UNA LISTA CHICA QUE NO CRUZA (ver salud_de_los_cruces()): una lista de 80 productos
    # con un par suelto esperando no es «equivalencias sin aprobar» ni una importación mal
    # hecha; una de 250 sin cruces sí es «aislada», y una de 250 con 20 esperando, «esperando».
    _ids10 = {}
    for _nombre, _cuantos in (("CHICA10", 80), ("AISLADA10", 250), ("ESPERA10", 250)):
        c.execute("INSERT INTO marcas (nombre, tipo) VALUES (?, 'PROVEEDOR')", (_nombre,))
        _m10 = c.lastrowid
        c.executemany("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
                      "VALUES (?, ?, 'JUNTA', ?)",
                      [(f"{_nombre}X{i}", f"{_nombre}X{i}", _m10) for i in range(_cuantos)])
        _ids10[_nombre] = [r[0] for r in c.execute(
            "SELECT id FROM productos WHERE marca_id = ? ORDER BY id", (_m10,))]
    c.executemany("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, "
                  "lote) VALUES (?, ?, 'prueba', 'PRUEBA 10')",
                  [(_ids10["CHICA10"][0], _ids10["ESPERA10"][-1])]
                  + [(x, _ids10["ESPERA10"][-2]) for x in _ids10["ESPERA10"][:20]])
    conn.commit()
    _res10 = ns["salud_de_los_cruces"]()[1]
    esperar("la lista chica no alarma; la grande sin cruces sí, y la que espera, como esperando",
            ("CHICA10" in _res10["listas_aisladas"] + _res10["listas_esperando"],
             "AISLADA10" in _res10["listas_aisladas"], "ESPERA10" in _res10["listas_esperando"]),
            (False, True, True))

    # 11. QUÉ PIEZA ES CADA FAMILIA DE CÓDIGOS (ver nombrar_familia()): 22 camisas de la familia
    # CAM que solo dicen el auto, una llave y un cojinete de la misma familia. Se propone CAM;
    # al nombrarla «camisa» cambian las 22 y no la llave ni el cojinete; lo nuevo de la familia
    # entra con el nombre, y sacarlo deja todo como estaba (lo nuevo también).
    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('FAMILIAS11', 'PROVEEDOR')")
    _m11 = c.lastrowid
    _fam11 = [(f"CAM-A20{i:02d}", f"FIAT Motor FIRE 1,{i % 9} L") for i in range(22)]
    _fam11 += [("CAM-LLAVE", "LLAVE T HEXAGONAL 19MM"), ("CAM-W1", "WABCO COJINETE LISO M.BENZ")]
    c.executemany("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
                  "VALUES (?, ?, ?, ?)", [(x, ns["sanitizar"](x), d, _m11) for x, d in _fam11])
    conn.commit()

    def _desc11(cod):
        return c.execute("SELECT descripcion FROM productos WHERE codigo_raw = ? AND marca_id = ?",
                         (cod, _m11)).fetchone()[0]
    _prop11 = {f["familia"]: f["sin_pieza"] for f in ns["familias_sin_nombre"](_m11)}
    esperar("se propone la familia CAM, con sus 22 que no dicen qué pieza son", _prop11,
            {"CAM": 22})
    esperar("nombrarla «camisa»: cambian las 22",
            ns["nombrar_familia"](_m11, "CAM", " camisa "), 22)
    esperar("la camisa dice que es una camisa; la llave y el cojinete, como estaban",
            (_desc11("CAM-A2003"), _desc11("CAM-LLAVE"), _desc11("CAM-W1")),
            ("CAMISA FIAT Motor FIRE 1,3 L", "LLAVE T HEXAGONAL 19MM",
             "WABCO COJINETE LISO M.BENZ"))
    ns["get_or_create_producto"]("CAM-NUEVA", "CAMNUEVA", "FIAT Motor FIRE 1,4 L", _m11)
    esperar("lo nuevo de la familia entra con el nombre", _desc11("CAM-NUEVA"),
            "CAMISA FIAT Motor FIRE 1,4 L")
    esperar("sacarle el nombre deja todo como estaba, lo nuevo también",
            (ns["sacar_nombre_de_familia"](_m11, "CAM"), _desc11("CAM-A2003"),
             _desc11("CAM-NUEVA")),
            (23, "FIAT Motor FIRE 1,3 L", "FIAT Motor FIRE 1,4 L"))
    try:
        ns["nombrar_familia"](_m11, "CAM", "  ")
        esperar("un nombre vacío no se acepta", "lo aceptó", "ValueError")
    except ValueError:
        pass

    # 12. LOS CÓDIGOS ADIVINADOS APROBADOS EN BLOQUE (ver codigos_adivinados_que_no_unen_nada()):
    # «120Amp», leído de las descripciones de una lista que no marca sus códigos, unía una
    # batería con dos soldadoras, y se aprobó con otros 300 en el mismo minuto: aparece. No
    # aparecen el aprobado de a uno, el verificado ni el que cuelga un solo producto ya cargado.
    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('ADIVINA12', 'PROVEEDOR')")
    _m12 = c.lastrowid
    _oem12 = c.execute("SELECT id FROM marcas WHERE tipo = 'OEM'").fetchone()
    _oem12 = _oem12[0] if _oem12 else ns["get_or_create_marca"]("OEM / FABRICA", "OEM")
    _prods12 = {}
    for _cod, _desc in [("BAT-120", "BATERIA 12v./120Amp."), ("SOL-120", "SOLDADORA MIG 120Amp."),
                        ("SOL-150", "SOLDADORA FLUX 120Amp. 150"),
                        ("STA-17A", "BOCALLAVE 3/8 HEXAG.17MM"), ("STA-17B", "BOCALLAVE 1/2 HEXAG.17MM"),
                        ("CRO-9", "LLAVE DE IMPACTO 1650Nm"), ("CRO-8", "LLAVE DE IMPACTO 3/4 1650Nm"),
                        ("NGK-1", "BUJIA NGK ZFR5Q-11 NO EXISTE MAS")]:
        _prods12[_cod] = ns["get_or_create_producto"](_cod, ns["sanitizar"](_cod), _desc, _m12)
    c.executemany("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
                  "VALUES (?, ?, ?, ?)", [(f"REL-{i}", f"REL{i}", f"RELLENO {i}", _m12)
                                          for i in range(300)])
    _ids12 = {}
    for _oc in ("120Amp", "HEXAG.17MM", "1650Nm", "ZFR5Q-11"):
        _ids12[_oc] = ns["get_or_create_producto"](_oc, ns["sanitizar"](_oc), "", _oem12)
    _vinc12 = [("120Amp", "BAT-120"), ("120Amp", "SOL-120"), ("120Amp", "SOL-150"),
               ("HEXAG.17MM", "STA-17A"), ("HEXAG.17MM", "STA-17B"),
               ("1650Nm", "CRO-9"), ("1650Nm", "CRO-8"), ("ZFR5Q-11", "NGK-1")]
    for _oc, _pc in _vinc12:
        _a, _b = sorted((_ids12[_oc], _prods12[_pc]))
        c.execute("INSERT INTO equivalencias (producto_a_id, producto_b_id, lote, verificada) "
                  "VALUES (?, ?, 'ADIVINA12 · lista.xlsx', ?)", (_a, _b, int(_oc == "1650Nm")))
    # La aprobación en bloque: todos en el mismo minuto, con 300 más de relleno.
    _bloque12 = [tuple(sorted((_ids12[_oc], _prods12[_pc]))) for _oc, _pc in _vinc12
                 if _pc != "STA-17B"] + [(100000 + i, 200000 + i) for i in range(300)]
    c.executemany("INSERT OR REPLACE INTO equivalencias_revisadas (producto_a_id, producto_b_id, "
                  "decision, revisado_por, fecha) VALUES (?, ?, 'ok', 'Chavo', "
                  "'2026-09-28 06:50:10')", _bloque12)
    # Uno de las bocallaves, aprobado de a uno otro día.
    c.execute("INSERT OR REPLACE INTO equivalencias_revisadas (producto_a_id, producto_b_id, "
              "decision, revisado_por, fecha) VALUES (?, ?, 'ok', 'Chavo', '2026-10-01 10:00:00')",
              tuple(sorted((_ids12["HEXAG.17MM"], _prods12["STA-17B"]))))
    conn.commit()
    _adv12 = {x["Código"]: (x["Productos"], x["Aprobados en bloque"])
              for x in ns["codigos_adivinados_que_no_unen_nada"]() if x["Lista"] == "ADIVINA12"}
    esperar("aprobado en bloque y uniendo tres: aparece; de a uno, verificado o uno solo, no",
            _adv12, {"120Amp": (3, 3)})

    # 13. EL QUE ENTRÓ APARTE POR ESCRIBIRSE IGUAL SIN LOS SIGNOS (ver codigo_de_la_variante()):
    # su código limpio no es el que da sanitizar() a propósito. «Limpiar y corregir» no lo
    # cuenta como desfasado ni lo «arregla»: lo fusionaría con el otro. Y el otro, que sí está
    # desfasado, se sigue arreglando.
    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('VARIANTE13', 'PROVEEDOR')")
    _m13 = c.lastrowid
    _var13 = ns["get_or_create_producto"]("CAM-A1781-030", ns["codigo_de_la_variante"]("CAM-A1781-030"),
                                          "CAMISA FIAT", _m13)
    _base13 = ns["get_or_create_producto"]("CAM-A1781+030", ns["sanitizar"]("CAM-A1781+030"),
                                           "CAMISA FIAT", _m13)
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
              "VALUES ('VIEJO-1', 'VIEJO1X', 'DESFASADO', ?)", (_m13,))
    conn.commit()
    _desf13 = {x["raw"] for x in ns["codigos_limpios_desfasados"]()
               if x["marca_id"] == _m13}
    esperar("desfasado el de verdad, no el que entró aparte", _desf13, {"VIEJO-1"})
    ns["reparar_codigos_limpios"]()
    esperar("arreglar no fusiona el que entró aparte",
            c.execute("SELECT COUNT(*) FROM productos WHERE id IN (?, ?)",
                      (_var13, _base13)).fetchone()[0], 2)
    esperar("el que está escrito igual sin los signos, en la lista del otro",
            [x["Código"] for x in ns["los_que_se_escriben_igual"](
                ns["codigo_de_la_variante"]("CAM-A1781-030"))], ["CAM-A1781+030"])
    # Lo que escribe la gente en cualquier buscador (ver codigo_para_buscar()): con los signos
    # del que entró aparte, ese; con los del otro o sin signos, el de siempre.
    esperar("qué se busca según cómo se escribe",
            [ns["codigo_para_buscar"](x) for x in ("CAM-A1781-030", "cam-a1781-030",
                                                    "CAM-A1781+030", "CAMA1781030")],
            [ns["codigo_de_la_variante"]("CAM-A1781-030")] * 2 + ["CAMA1781030"] * 2)

    # 14. LAS SOLAPAS DE «LIMPIAR Y CORREGIR» (ver SOLAPA_DE_LA_HERRAMIENTA): cada herramienta
    # en una, y la miga de los avisos la nombra. Una herramienta nueva sin solapa, falla acá.
    _de_limpiar = {t for t, g, *_ in ns["HERRAMIENTAS_MANTENIMIENTO"] if g == 1}
    esperar("cada herramienta de Limpiar y corregir tiene su solapa",
            (_de_limpiar - set(ns["SOLAPA_DE_LA_HERRAMIENTA"]),
             set(ns["SOLAPA_DE_LA_HERRAMIENTA"]) - _de_limpiar), (set(), set()))
    esperar("y la miga la nombra", "→ 💲 Precios →" in ns["miga_hasta"](
        "Precios que no cierran entre equivalentes"), True)

    # 15. EL PRECIO DE RELLENO (ver precios_de_relleno()): IMPERIAL pone 999.999 donde no tiene
    # precio, en micrómetros, carretillas y tuercas. Un precio repetido de verdad (el 930 de
    # ILLINOIS, el motor caro que viene en cinco versiones) no es relleno.
    _clases15 = ["TUERCA", "LLAVE", "DISCO", "PINCEL", "PIPETA", "CARRETILLA", "MICROMETRO",
                 "VARILLA", "BULON", "ARANDELA"]
    _lista15 = [(1000 + 37 * i, f"{_clases15[i % 10]} {i}") for i in range(300)]
    _lista15 += [(999999, f"{_clases15[i % 10]} SIN PRECIO {i}") for i in range(25)]
    _lista15 += [(930, f"JUNTA {i}") for i in range(30)]
    _lista15 += [(900000, f"MOTOR COMPLETO {i}") for i in range(25)]
    esperar("relleno: el 999.999 entre clases distintas, no el repetido de verdad",
            ns["precios_de_relleno"](_lista15), frozenset({999999.0}))
    esperar("en una lista chica no se busca", ns["precios_de_relleno"](_lista15[-60:]), frozenset())

    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('RELLENO15', 'PROVEEDOR')")
    _m15 = c.lastrowid
    _ids15 = []
    for _i, (_p, _d) in enumerate(_lista15):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio) "
                  "VALUES (?, ?, ?, ?, ?)", (f"R15-{_i}", f"R15{_i}", _d, _m15, _p))
        _ids15.append(c.lastrowid)
    _pipeta15 = _ids15[300]   # el primero de los de 999.999
    c.execute("INSERT INTO historial_precios (producto_id, precio) VALUES (?, 4100), (?, 999999)",
              (_pipeta15, _pipeta15))
    conn.commit()
    _en_base15 = [(r["precio"], r["productos"]) for r in
                  ns["precios_de_relleno_en_la_base"](segundos_de_memoria=0)
                  if r["marca_id"] == _m15]
    esperar("en la base: los 25 de 999.999 y nada más", _en_base15, [(999999.0, 25)])

    # El freno de saltos no compara contra el número de relleno: el primer precio de verdad
    # (3.000, 333 veces menos) se frenaba y quedaba el de mentira.
    _poner15 = ns["poner_precio_y_stock_de_la_lista"]
    _frenado15, _ = _poner15(_pipeta15, 3000, None, 200, de_relleno={999999.0})
    esperar("con el relleno sabido, el precio de verdad entra",
            (_frenado15, uno("SELECT precio FROM productos WHERE id = ?", _pipeta15)), (None, 3000))
    _otra15 = _ids15[301]
    _frenado15b, _ = _poner15(_otra15, 3000, None, 200)
    esperar("sin saberlo, se frena (es lo que pasaba)", _frenado15b is not None, True)

    # Dejarlos sin precio: los que quedan, y la marca se acuerda para la lista que venga
    # aunque traiga pocos.
    _n15 = ns["sacar_precios_de_relleno"](_m15, [999999.0])
    esperar("quedan sin precio los que tenían el relleno", _n15, 24)
    esperar("y no los otros", uno("SELECT COUNT(*) FROM productos WHERE marca_id = ? AND precio "
                                  "IS NULL", _m15), 24)
    esperar("la marca se acuerda", ns["precios_de_relleno_conocidos"](_m15), frozenset({999999.0}))
    esperar("ya no aparece en la base",
            [r for r in ns["precios_de_relleno_en_la_base"]() if r["marca_id"] == _m15], [])
    # Sin precio y con el 999.999 en el historial: el precio de verdad entra.
    _frenado15c, _ = _poner15(_ids15[302], 3500, None, 200,
                              de_relleno=ns["precios_de_relleno_conocidos"](_m15))
    c.execute("INSERT INTO historial_precios (producto_id, precio) VALUES (?, 999999)",
              (_ids15[303],))
    _frenado15d, _ = _poner15(_ids15[303], 3500, None, 200,
                              de_relleno=ns["precios_de_relleno_conocidos"](_m15))
    esperar("sin precio, el que llega entra aunque el historial tenga el relleno",
            (_frenado15c, _frenado15d), (None, None))
    esperar("la salud lo nombra y lleva a Limpiar",
            "→ 💲 Precios → 🧹 Precios de relleno" in ns["miga_hasta"]("Precios de relleno de una lista"),
            True)

    # 16. EL PRECIO QUE NO SIGUE LA MEDIDA (ver precios_que_no_siguen_la_medida()): la llave
    # Stanley de 1.1/4 a $424 entre la de 30 mm a $38.760 y la de 32 mm a $43.860.
    _med16 = ns["medida_de_la_descripcion"]
    esperar("la medida de la descripción",
            [_med16(d) for d in ("LLAVE COMBINADA ACODADA 1.1/4", "VARILLA ROSC. NAT. 20 mm",
                                 "PEUGEOT 404/504 DIESEL", "FORD FALCON 82/90",
                                 'DISCO FLAP Ø 4,5"', "JUNTA 1/2 Y 3/4",
                                 'JTA ESPIR. SW S.900 3"')],
            [(31.75, "LLAVE COMBINADA ACODADA #", "1.1/4"), (20.0, "VARILLA ROSC. NAT. #", "20 MM"),
             None, None, None, None, (76.2, "JTA ESPIR. SW S.900 #", '3"')])
    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('MEDIDA16', 'PROVEEDOR')")
    _m16 = c.lastrowid
    _ids16 = {}
    for _cod, _desc, _p in (("LL-28", "LLAVE ACODADA 28MM", 34000), ("LL-30", "LLAVE ACODADA 30MM", 38760),
                            ("LL-114", "LLAVE ACODADA 1.1/4", 423.7), ("LL-32", "LLAVE ACODADA 32MM", 43860),
                            ("LL-34", "LLAVE ACODADA 34MM", 47000),
                            # Otra familia que sube como corresponde, y una de tres medidas sola.
                            ("TU-14", "TUERCA 1/4", 100), ("TU-516", "TUERCA 5/16", 140),
                            ("TU-38", "TUERCA 3/8", 190), ("TU-716", "TUERCA 7/16", 250),
                            ("AR-14", "ARANDELA 1/4", 10), ("AR-516", "ARANDELA 5/16", 1),
                            ("AR-38", "ARANDELA 3/8", 12),
                            # Y la varilla de 20 mm al precio de la de 10 mm.
                            ("VA-18", "VARILLA 18 mm", 684671), ("VA-20", "VARILLA 20 mm", 174814),
                            ("VA-22", "VARILLA 22 mm", 1707536), ("VA-24", "VARILLA 24 mm", 2500000)):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio) "
                  "VALUES (?, ?, ?, ?, ?)", (_cod, _cod.replace("-", ""), _desc, _m16, _p))
        _ids16[_cod] = c.lastrowid
    conn.commit()

    def _fuera16():
        return sorted(x["Código"] for x in ns["precios_que_no_siguen_la_medida"](segundos_de_memoria=0)
                      if x["Marca"] == "MEDIDA16")
    esperar("salen la llave de 1.1/4 y la varilla de 20 mm, no la familia que sube ni la de tres",
            _fuera16(), ["LL-114", "VA-20"])
    ns["dar_por_bueno_el_precio_de_medida"](_ids16["VA-20"], 174814)
    esperar("la que se dio por buena no vuelve", _fuera16(), ["LL-114"])
    ns["corregir_el_precio_de_medida"](_ids16["LL-114"], 42370, 423.7)
    esperar("corregida: con su precio nuevo, en el historial, y ya no aparece",
            (uno("SELECT precio FROM productos WHERE id = ?", _ids16["LL-114"]),
             uno("SELECT precio FROM historial_precios WHERE producto_id = ? ORDER BY id DESC",
                 _ids16["LL-114"]), _fuera16()), (42370, 42370, []))
    esperar("si otro lo cambió mientras tanto, no se pisa",
            ns["corregir_el_precio_de_medida"](_ids16["LL-114"], 50000, 423.7)[0], False)
    # La que se dio por buena vuelve si una lista le cambia el precio.
    c.execute("UPDATE productos SET precio = 180000 WHERE id = ?", (_ids16["VA-20"],))
    conn.commit()
    esperar("con otro precio, vuelve", _fuera16(), ["VA-20"])
    esperar("la salud lleva a la solapa de precios",
            "→ 💲 Precios → 📏 Precios que no siguen" in ns["miga_hasta"]("Precios que no siguen la medida"),
            True)
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

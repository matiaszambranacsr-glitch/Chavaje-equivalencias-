"""Pruebas de lo que queda afuera: cada uno responde por lo que pidió, y vuelve escaneado.

Uso:
    python3 pruebas/pruebas_de_lo_que_queda_afuera.py

Lo que el depósito entrega para Mostrador queda a nombre de quien lo pidió hasta que lo vende
en 🧾 Ventas (sin bajar el stock otra vez), se factura o vuelve al depósito: escaneando la
etiqueta nuestra de cada pieza (no el código original de la caja), con la contraseña de quien
lo tiene, y lo recibe otra persona. Lo de un taller no vuelve: queda en su cuenta. Lo que se
termina queda anotado para reponer solo. Ver «LO QUE QUEDA AFUERA» y «EL CÓDIGO DE BARRAS
NUESTRO» en logica/deposito.py.

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

    def como(persona, nivel="operador"):
        st.session_state["admin_nombre"] = persona
        st.session_state["nivel_usuario"] = nivel

    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('PRUEBA', 'PROVEEDOR')")
    marca = c.lastrowid
    ids = {}
    for codigo, precio, stock in (("A1", 1000, 5), ("B1", 500, None), ("C1", 300, 1)):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio, "
                  "stock) VALUES (?, ?, 'FILTRO ACEITE', ?, ?, ?)",
                  (codigo, codigo, marca, precio, stock))
        ids[codigo] = c.lastrowid
    ean = "779" + "123456789"
    ean += ns["digito_verificador_gtin"](ean)
    c.execute("UPDATE productos SET codigo_barras = ? WHERE id = ?", (ean, ids["A1"]))
    conn.commit()
    a, b, cc = ids["A1"], ids["B1"], ids["C1"]
    ns["crear_usuario"]("ana", "clave-ana-1", "operador")
    ns["crear_usuario"]("beto", "clave-beto-1", "operador")
    ns["crear_usuario"]("jefe", "clave-jefe-1", "admin")
    ns["crear_mecanico"]("Taller Norte", "clave-norte-1")
    taller = uno("SELECT id FROM mecanicos WHERE nombre = 'Taller Norte'")
    stock = lambda pid: uno("SELECT stock FROM productos WHERE id = ?", pid)
    codigo = ns["codigo_nuestro"]
    ca, cb = codigo(a), codigo(b)

    def pedir_y_entregar(pid, cantidad, persona, mecanico_id=None):
        como(persona)
        ns["pedir_al_deposito"](pid, cantidad, mecanico_id=mecanico_id, usuario=persona,
                                retiro_autorizado=True)
        pedido = uno("SELECT MAX(id) FROM pedidos_deposito")
        ns["entregar_pedido"](pedido, usuario="deposito")
        return pedido

    # 1. El código nuestro: «CH» + el número + el dígito verificador. El lector puede mandar los
    # asteriscos del Code 39, minúsculas o espacios; un dígito mal leído no es nada.
    por_codigo = ns["producto_por_codigo_nuestro"]
    _dv = ca[-1]
    esperar("el código nuestro y cómo se lee",
            (ca == f"CH{a}-{ns['digito_verificador_gtin'](str(a))}", por_codigo(ca),
             por_codigo(f"*{ca.lower()}*"), por_codigo(f" CH 0{a} - {_dv} "),
             por_codigo(f"CH{a}-{(int(_dv) + 1) % 10}"), por_codigo("CH999999-" +
                                                                 ns["digito_verificador_gtin"]("999999")),
             por_codigo(ean), por_codigo("")),
            (True, a, a, a, None, None, None, None))

    # 2. Lo entregado para Mostrador queda a nombre de quien lo pidió.
    p1 = pedir_y_entregar(a, 3, "ana")
    esperar("entregado: baja el stock y queda a nombre de ana",
            (stock(a), [(r["id"], r["queda"], r["quien"]) for r in ns["lo_que_tiene"](persona="ana")],
             ns["lo_que_tiene"](persona="beto"),
             uno("SELECT COUNT(*) FROM ventas_registradas WHERE pedido_id = ?", p1)),
            (2, [(p1, 3, "ana")], [], 1))

    # 3. Si ana lo vende en 🧾 Ventas, sale de lo que tiene y el stock NO baja otra vez; lo
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
    venta_b, _ = ns["cerrar_venta"]([dict(ns["item_de_venta"](a, 2))])
    esperar("vende más de lo que tiene: el resto baja del stock",
            (stock(a), ns["lo_que_tiene"](persona="ana"),
             uno("SELECT stock_descontado FROM ventas_items WHERE venta_id = ?", venta_b)),
            (1, [], 1))
    ns["anular_venta"](venta_b)
    esperar("anulada: vuelve a estar a nombre de ana, y al stock solo lo que bajó",
            (stock(a), [r["queda"] for r in ns["lo_que_tiene"](persona="ana")],
             [r[0] for r in c.execute("SELECT venta_id FROM ventas_registradas "
                                      "WHERE producto_id = ?", (a,))]), (2, [1], [venta]))

    # 4. Qué es lo escaneado: el código ORIGINAL de la caja no sirve de control, lo que no es
    # un código nuestro tampoco, ni lo que nadie tiene afuera, ni una unidad de más.
    que_es = ns["que_es_lo_escaneado"]
    esperar("qué es lo escaneado",
            [que_es(ca), "ORIGINAL" in que_es(ean)[1], que_es(ean)[0],
             "no es un código nuestro" in que_es("hola")[1], "Nadie tiene" in que_es(cb)[1],
             "Ya se escanearon las 1" in que_es(ca, [ca])[1], que_es("")],
            [(a, ""), True, None, True, True, True, (None, "")])

    # 5. Vuelve al stock: lo escanea el depósito (beto) y pone la contraseña quien lo tiene.
    como("beto")
    devolver = ns["devolver_lo_escaneado"]
    esperar("de quién es lo escaneado", (ns["quienes_tienen_lo_escaneado"]([ca]),
                                         ns["quienes_tienen_lo_escaneado"]([ca, ca]),
                                         ns["quienes_tienen_lo_escaneado"]([])),
            (["ana"], [], []))
    _de_mas = devolver([ca, ca], "ana", "clave-ana-1")
    esperar("más unidades de las que tiene, otra clave, sin clave, la del taller, o algo que no "
            "es un código nuestro: no vuelve nada",
            [_de_mas[0], "tiene 1" in _de_mas[1] and "se escanearon 2" in _de_mas[1],
             devolver([ca], "ana", "clave-beto-1")[0], devolver([ca], "ana", "")[0],
             devolver([ca], "ana", "clave-norte-1")[0], devolver([ean], "ana", "clave-ana-1")[0],
             devolver([], "ana", "clave-ana-1")[0], stock(a)],
            [False, True, False, False, False, False, False, 2])
    # Quien lo tiene no se lo recibe a sí mismo, aunque ponga su clave.
    como("ana")
    _a_si_misma = devolver([ca], "ana", "clave-ana-1")
    esperar("nadie se devuelve a sí mismo",
            (_a_si_misma[0], "recibir el depósito" in _a_si_misma[1], stock(a)), (False, True, 2))
    como("beto")
    ok, texto = devolver([f"*{ca}*"], "ana", "clave-ana-1")
    esperar("escaneado y con la clave de ana: vuelve, el stock sube, ya no está a su nombre",
            (ok, stock(a), ns["lo_que_tiene"](persona="ana"),
             uno("SELECT devolvio || ' / ' || como || ' / ' || recibio || ' / ' || cantidad "
                 "FROM devoluciones_al_deposito WHERE pedido_id = ?", p1),
             uno("SELECT COUNT(*) FROM ventas_registradas WHERE pedido_id = ?", p1),
             devolver([ca], "ana", "clave-ana-1")[0]),
            (True, 3, [], "ana / su clave / beto / 1", 1, False))

    # 6. Con la de un administrador también, y queda dicho; lo que vuelve entero sin haberse
    # vendido se lleva lo aprendido (si vuelve una parte, lo aprendido queda: lo que sigue
    # afuera todavía se puede vender); sin stock cargado, el stock no se toca.
    p2 = pedir_y_entregar(b, 2, "ana")
    como("beto")
    ok, texto = devolver([cb], "ana", "clave-jefe-1")
    esperar("con la clave del administrador, una parte",
            (ok, "clave de administrador" in texto, stock(b),
             uno("SELECT COUNT(*) FROM ventas_registradas WHERE pedido_id = ?", p2),
             uno("SELECT devueltos FROM pedidos_deposito WHERE id = ?", p2)),
            (True, True, None, 1, 1))
    ok, texto = devolver([cb], "ana", "clave-jefe-1")
    esperar("y el resto: entero, sin lo aprendido",
            (ok, uno("SELECT COUNT(*) FROM ventas_registradas WHERE pedido_id = ?", p2),
             uno("SELECT devueltos FROM pedidos_deposito WHERE id = ?", p2)), (True, 0, 2))

    # 7. Si mientras tanto otro vendió o devolvió algo, no vuelve nada: ni la parte que sí
    # se podía.
    p3 = pedir_y_entregar(a, 1, "ana")
    p3b = pedir_y_entregar(b, 1, "ana")
    _plan = [(r, r["queda"]) for r in ns["lo_que_tiene"](persona="ana")]
    c.execute("UPDATE pedidos_deposito SET vendidos = 1 WHERE id = ?", (p3b,))
    conn.commit()
    _antes = (stock(a), uno("SELECT COUNT(*) FROM devoluciones_al_deposito"))
    try:
        ns["_devolver_lo_planeado"](_plan, "ana", "su clave", "beto")
        _choco = False
    except ValueError:
        _choco = True
    esperar("a la vez que otro: todo o nada",
            (_choco, (stock(a), uno("SELECT COUNT(*) FROM devoluciones_al_deposito")),
             uno("SELECT COALESCE(devueltos, 0) FROM pedidos_deposito WHERE id = ?", p3)),
            (True, _antes, 0))
    c.execute("UPDATE pedidos_deposito SET vendidos = 0 WHERE id = ?", (p3b,))
    conn.commit()

    # 8. Lo facturado ya no está afuera, ni vuelve.
    ns["marcar_facturado"]([p3, p3b])
    esperar("facturado: ya no está a su nombre ni vuelve",
            (ns["lo_que_tiene"](persona="ana"), que_es(ca)[0],
             devolver([ca], "ana", "clave-jefe-1")[0]), ([], None, False))

    # 9. LO DE UN TALLER NO VUELVE: queda en su cuenta, no está «afuera» a nombre de nadie, y
    # ni con su clave ni con la de quien lo pidió se descarga.
    p4 = pedir_y_entregar(a, 2, "beto", mecanico_id=taller)
    saldo = lambda: ns["estado_de_cuenta"](taller)["saldo"]
    como("ana")
    esperar("lo del taller no vuelve",
            (saldo(), ns["lo_que_tiene"](), que_es(ca)[0],
             devolver([ca], "Taller Norte", "clave-norte-1")[0],
             devolver([ca], "beto", "clave-beto-1")[0], saldo(), stock(a),
             [(k[1], [(r["cantidad"], r["importe"]) for r in v])
              for k, v in ns["para_facturar"]().items() if k[0] == taller],
             "devolver_al_deposito" in ns),
            (2000.0, [], None, False, False, 2000.0, 0,
             [("Taller Norte", [(2, 2000.0)])], False))

    # 10. Quién tiene qué, y lo de cada cuenta.
    c.execute("UPDATE productos SET stock = 5 WHERE id = ?", (a,))
    conn.commit()
    pedir_y_entregar(a, 2, "beto")
    esperar("quién tiene que devolver",
            [(g["quien"], g["unidades"], g["valor"]) for g in ns["quien_tiene_que_devolver"]()],
            [("beto", 2, 2000.0)])
    r_ana = ns["resumen_de_la_cuenta"](persona="ana")
    r_taller = ns["resumen_de_la_cuenta"](mecanico_id=taller)
    esperar("lo de cada cuenta",
            ([v["id"] for v in r_ana["ventas"]], r_ana["total"], r_ana["afuera"],
             len(r_taller["entregas"]), r_taller["total"], r_taller["saldo"],
             r_taller["afuera"], "devuelto" in r_taller),
            ([venta], 2000.0, [], 1, 2000.0, 2000.0, [], False))
    como("beto", "operador")
    esperar("un empleado ve solo lo suyo", [x[1:] for x in ns["cuentas_para_mirar"]()],
            [("beto", None)])
    como("jefe", "admin")
    _todas = ns["cuentas_para_mirar"]()
    esperar("el administrador ve a todos", ({x[1] for x in _todas if x[1]} >= {"ana", "beto"},
                                            (None, taller) in [x[1:] for x in _todas]),
            (True, True))

    # 11. «➕ Sumar a la venta» lo que se tiene del depósito, con su cantidad (lo que ya estaba
    # con menos sube); al cerrarla sale de lo que tiene sin bajar el stock otra vez.
    como("beto")
    st.session_state["venta_items"] = [dict(ns["item_de_venta"](b, 1)), dict(ns["item_de_venta"](a, 1))]
    _sumados = ns["sumar_lo_que_tengo_a_la_venta"]()
    esperar("sumar a la venta lo que tengo",
            (_sumados, sorted((x["producto_id"], x["cantidad"]) for x in st.session_state["venta_items"]),
             ns["sumar_lo_que_tengo_a_la_venta"]()),
            (1, sorted([(b, 1), (a, 2)]), 0))
    _stock_a = stock(a)
    ns["cerrar_venta"](st.session_state["venta_items"])
    esperar("vendido lo sumado: sale de lo que tiene, el stock no baja",
            (ns["lo_que_tiene"](persona="beto"), stock(a)), ([], _stock_a))
    st.session_state["venta_items"] = []

    # 12. Las etiquetas: un PDF con una por pieza (24 por hoja); nada, nada. Y que un lector
    # las pueda leer: la barra fina de por lo menos 0,25 mm (fpdf toma `w` como la GRUESA, el
    # triple; con 0,1 mm no las levantaba nadie), y el código entero adentro de la etiqueta
    # aunque el número sea largo.
    from fpdf import FPDF
    _barras, _code39 = [], FPDF.code39
    FPDF.code39 = lambda self, texto, x, y, w=1.5, h=5: (_barras.append((texto, x, w)),
                                                          _code39(self, texto, x, y, w, h))
    try:
        c.execute("UPDATE sqlite_sequence SET seq = 9999998 WHERE name = 'productos'")
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio) "
                  "VALUES ('LARGO', 'LARGO', 'X', ?, 1)", (marca,))
        largo = c.lastrowid
        conn.commit()
        _pdf = ns["pdf_de_etiquetas"]([(a, 20), (b, 5), (largo, 1)])
    finally:
        FPDF.code39 = _code39
    esperar("las barras se pueden leer y entran en la etiqueta",
            (len(_barras), _barras[-1][0], all(w / 3 >= 0.25 for _, _, w in _barras),
             all(6 <= x and x + 16 * len(t) * w / 3 <= 6 + 3 * 68 for t, x, w in _barras),
             all((x - 6) % 68 + 16 * len(t) * w / 3 <= 66 for t, x, w in _barras)),
            (26, f"*{codigo(largo)}*", True, True, True))
    _pdf = ns["pdf_de_etiquetas"]([(a, 20), (b, 5)])
    _hojas = _pdf.count(b"/Type /Page") - _pdf.count(b"/Type /Pages")
    esperar("las etiquetas", (_pdf[:4], _hojas, ns["pdf_de_etiquetas"]([]),
                              ns["pdf_de_etiquetas"]([(999999, 3)]),
                              ns["etiquetas_para_descargar"]([(a, 1)])()[:4]),
            (b"%PDF", 2, b"", b"", b"%PDF"))
    para_etiquetar = ns["productos_para_etiquetar"]
    esperar("buscar qué etiquetar: por código, por el principio, escaneando la caja o la nuestra",
            ([p["id"] for p in para_etiquetar("a1")], [p["id"] for p in para_etiquetar("A")][:1],
             [p["id"] for p in para_etiquetar(ean)], [p["id"] for p in para_etiquetar(cb)],
             para_etiquetar(""), para_etiquetar("ZZZ")),
            ([a], [a], [a], [b], [], []))

    # 13. LO QUE SE TERMINA QUEDA ANOTADO PARA REPONER, solo: al venderlo y al entregarlo el
    # depósito. Lo que ya estaba anotado no suma otra vez; lo que no lleva stock, nunca.
    como("ana")
    repo = lambda pid: c.execute("SELECT veces_solicitado, estado, ultimo_solicitado_por FROM "
                                 "pedidos_reposicion WHERE producto_id = ?", (pid,)).fetchone()
    ns["cerrar_venta"]([dict(ns["item_de_venta"](cc, 1))])
    _primera = tuple(repo(cc) or ())
    ns["cerrar_venta"]([dict(ns["item_de_venta"](cc, 1))])
    esperar("vendido hasta 0: anotado una vez",
            (stock(cc), _primera, tuple(repo(cc) or ())),
            (0, (1, "pendiente", "ana (se terminó)"), (1, "pendiente", "ana (se terminó)")))
    ns["marcar_pedido_resuelto"](uno("SELECT id FROM pedidos_reposicion WHERE producto_id = ?", cc))
    c.execute("UPDATE productos SET stock = 1 WHERE id = ?", (cc,))
    conn.commit()
    pedir_y_entregar(cc, 1, "ana")
    ns["cerrar_venta"]([dict(ns["item_de_venta"](b, 1))])
    esperar("entregado hasta 0 otra vez: vuelve a pendiente y suma; sin stock, no",
            (tuple(repo(cc) or ())[:2], repo(b), ns["anotar_lo_que_se_termino"]([a])),
            ((2, "pendiente"), None, []))
    # Si anotarlo falla, la venta ya está hecha: no se muestra como fallida (se cobraba dos
    # veces) y el error queda anotado.
    c.execute("UPDATE productos SET stock = 1 WHERE id = ?", (cc,))
    c.execute("ALTER TABLE pedidos_reposicion RENAME TO pedidos_reposicion_de_costado")
    conn.commit()
    try:
        _venta_igual, _ = ns["cerrar_venta"]([dict(ns["item_de_venta"](cc, 1))])
    except Exception as _err:
        _venta_igual = repr(_err)
    finally:
        c.execute("ALTER TABLE pedidos_reposicion_de_costado RENAME TO pedidos_reposicion")
        conn.commit()
    esperar("si anotar para reponer falla, la venta igual queda",
            (isinstance(_venta_igual, int),
             uno("SELECT COUNT(*) FROM ventas_items WHERE venta_id = ?", _venta_igual)), (True, 1))

    for k in ("admin_nombre", "nivel_usuario", "venta_items"):
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
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

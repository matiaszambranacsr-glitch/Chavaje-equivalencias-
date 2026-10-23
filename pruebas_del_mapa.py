"""Pruebas del mapa del depósito: el plano en letras, armarlo sin dibujar, dónde está cada cosa,
el recorrido caminando por el pasillo, la cola por piso y los del depósito.

Uso:
    python3 pruebas_del_mapa.py

Ver «EL MAPA DEL DEPÓSITO» en logica/mapa.py. Corre en una carpeta temporal: nunca toca la base
de trabajo.
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
    g = ns["leer_plano"].__wrapped__.__globals__
    fallas = []

    def esperar(nombre, real, esperado):
        if real != esperado:
            fallas.append(f"{nombre}: dio {real!r}, se esperaba {esperado!r}")

    def uno(sql, *args):
        fila = c.execute(sql, args).fetchone()
        return fila[0] if fila else None

    leer, rapido = ns["leer_plano"], ns["armado_rapido"]

    # 1. El plano en letras: estanterías, módulos (acostada: de izquierda a derecha; parada: de
    # arriba a abajo), la entrada, y lo que no se entiende, en palabras.
    p = leer("#####\n#AAA.\n#...B\n#@..B\n")
    esperar("el plano leído", (p["ancho"], p["alto"], list(p["estanterias"]), p["entrada"],
                               p["estanterias"]["A"]["acostada"],
                               [m for m in p["estanterias"]["A"]["modulos"]],
                               p["estanterias"]["B"]["acostada"],
                               [m for m in p["estanterias"]["B"]["modulos"]], p["errores"]),
            (5, 4, ["A", "B"], (1, 3), True, [((1, 1),), ((2, 1),), ((3, 1),)], False,
             [((4, 2),), ((4, 3),)], ()))
    raro = leer("a?a\n.A.")
    esperar("lo raro queda como pared y se dice; una letra en dos lugares, también",
            (raro["filas"][0], len(raro["errores"]), "«?»" in raro["errores"][0],
             "no es un rectángulo" in raro["errores"][1]), ("A#A", 2, True, True))
    esperar("más grande que 60 × 40: se corta y se dice",
            (leer("." * 70)["ancho"], "más grande" in leer("." * 70)["errores"][0]), (60, True))

    # 2. Armado rápido: filas de estanterías con pasillo alrededor, paredes y la entrada.
    r = rapido(3, 2, 5, 1)
    pr = leer(r)
    esperar("armado rápido 3 × 2 de 5 módulos",
            (pr["ancho"], pr["alto"], "".join(pr["estanterias"]), pr["entrada"],
             [len(e["modulos"]) for e in pr["estanterias"].values()], pr["errores"],
             r.splitlines()[2]),
            (15, 9, "ABCDEF", (7, 8), [5] * 6, (), "#.AAAAA.BBBBB.#"))
    for args, texto in (((3, 4, 20, 1), "entran hasta"), ((0, 1, 1, 1), "por lo menos 1"),
                        ((6, 6, 1, 1), "Hasta 35")):
        try:
            rapido(*args)
            fallas.append(f"armado rápido {args}: tenía que avisar")
        except ValueError as e:
            esperar(f"armado rápido {args}", texto in str(e), True)

    # 3. Retocar: sumar (con la primera letra libre, agrandando si hace falta), chocar, mover y
    # sacar.
    sumar, mover, sacar = ns["sumar_estanteria"], ns["mover_estanteria"], ns["sacar_estanteria"]
    t, letra = sumar(r, 2, 2, 3)
    esperar("sumar la G en la columna 2, fila 2", (letra, t.splitlines()[1]), ("G", "#GGG..........#"))
    t2, letra2 = sumar(t, 17, 3, 2, acostada=False)
    esperar("sumar parada afuera: agranda el plano", (letra2, leer(t2)["ancho"],
                                                      [l_[16] for l_ in t2.splitlines()[2:4]]),
            ("H", 17, ["H", "H"]))
    for args, texto in (((r, 3, 3, 2), "Choca con la A"), ((r, 1, 1, 2), "Choca con una pared"),
                        ((r, 60, 1, 5), "No entra"), ((r, 2, 2, 1, True, 1, "A"), "Ya hay una A")):
        try:
            sumar(*args)
            fallas.append(f"sumar {args[1:]}: tenía que avisar")
        except ValueError as e:
            esperar(f"sumar {args[1:]}", texto in str(e), True)
    esperar("mover la A una a la izquierda, y sacarla",
            (mover(r, "A", -1, 0).splitlines()[2], sacar(r, "A").splitlines()[2]),
            ("#AAAAA..BBBBB.#", "#.......BBBBB.#"))
    for args, texto in ((("A", -2, 0), "choca"), (("A", 0, -2), "choca"), (("Z", 1, 0), "No hay")):
        try:
            mover(r, *args)
            fallas.append(f"mover {args}: tenía que avisar")
        except ValueError as e:
            esperar(f"mover {args}", texto in str(e), True)

    # 4. Caminando por el pasillo, no en línea recta: de la entrada a la A hay que rodear la B.
    corto = "#######\n#.....#\n#.AAA.#\n#.....#\n#.BBB.#\n#..@..#\n#######"
    pc = leer(corto)
    _, _, total = ns["planear_el_recorrido"](corto, [pc["estanterias"]["A"]["modulos"][1]])
    esperar("de la entrada al medio de la A: 6 pasos rodeando la B (en recta eran 2)", total, 6)
    # La A está encerrada entre paredes: en línea recta queda a 2 de la entrada y la B a 5, pero
    # a la A no se llega.
    encerrada = "########\n#A#....#\n###.##B#\n#@.....#\n########"
    orden, _, _ = ns["planear_el_recorrido"](encerrada, [leer(encerrada)["estanterias"]["A"]["celdas"],
                                                         leer(encerrada)["estanterias"]["B"]["celdas"]])
    esperar("a la que no se llega caminando, al final", orden, [1, 0])
    paradas = [pr["estanterias"][l_]["modulos"][m] for l_, m in (("F", 4), ("A", 0), ("C", 0))]
    # Siempre a la más cercana de donde se está, que es lo que se pidió (no el recorrido más
    # corto de todos: acá F, A, C da 20 pasos y la más cercana cada vez, 22).
    orden, camino, total = ns["planear_el_recorrido"](r, paradas)
    orden2, _, total2 = ns["planear_el_recorrido"](r, paradas, por_cercania=False)
    esperar("por cercanía desde la entrada: F (6), C (12), A (4); en el orden dado, F, A, C",
            (orden, total, orden2, total2, camino[0], len(camino) == total + 1),
            ([0, 2, 1], 22, [0, 1, 2], 20, (7, 8), True))
    orden, _, _ = ns["planear_el_recorrido"](r, paradas, desde=pr["estanterias"]["C"]["modulos"][0])
    esperar("desde la C: la A y la C, que dan al mismo pasillo; después la F", orden, [1, 2, 0])
    esperar("ordenar por ubicación: A2 antes que A10, los números como números",
            sorted(["A10-1", "B-1", "A2-3-1", "A2-10", "zz", "A2-3"], key=ns["clave_de_ubicacion"]),
            ["A2-3", "A2-3-1", "A2-10", "A10-1", "B-1", "zz"])

    # 5. Cómo se escribe una ubicación.
    leer_u = ns["leer_ubicacion"]
    esperar("leer una ubicación", [leer_u("a 3 2"), leer_u("A/3/2"), leer_u(" B-12 "), leer_u("C"),
                                   leer_u("A-0"), leer_u("A-3-2-1"), leer_u(""),
                                   ns["texto_de_ubicacion"]("A", 3, 2), ns["texto_de_ubicacion"]("A")],
            [("A", 3, 2), ("A", 3, 2), ("B", 12, None), ("C", None, None), None, None, None,
             "A-3-2", "A"])

    # 6. Sin mapa, la ubicación de un producto es texto libre, como siempre.
    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('PRUEBA', 'PROVEEDOR')")
    marca = c.lastrowid
    ids = {}
    for codigo, stock in (("W712", 3), ("W713", 0), ("W714", 5), ("W715", None), ("DOS", 1)):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio, "
                  "stock) VALUES (?, ?, 'FILTRO', ?, 100, ?)", (codigo, codigo, marca, stock))
        ids[codigo] = c.lastrowid
    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('OTRA', 'PROVEEDOR')")
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio) "
              "VALUES ('DOS', 'DOS', 'OTRA MARCA', ?, 1)", (c.lastrowid,))
    ean = "779123456789"
    ean += ns["digito_verificador_gtin"](ean)
    c.execute("UPDATE productos SET codigo_barras = ? WHERE id = ?", (ean, ids["W714"]))
    conn.commit()
    ubicar = ns["ubicar_producto"]
    esperar("sin mapa: cualquier texto", (ubicar(ids["W715"], "estante del fondo")[0],
                                          uno("SELECT ubicacion FROM productos WHERE id = ?",
                                              ids["W715"]), ns["hay_mapa"]()),
            (True, "estante del fondo", False))

    # 7. Depósitos y pisos; el plano se guarda y sus letras pasan a ser estanterías con código
    # único en todos los depósitos.
    piso1, texto = ns["crear_deposito"]("Central")
    esperar("depósito con su planta baja", (bool(piso1), ns["crear_deposito"]("Central")[0],
                                            ns["crear_deposito"]("  ")[0]), (True, None, None))
    dep1 = uno("SELECT deposito_id FROM pisos WHERE id = ?", piso1)
    piso2, _ = ns["crear_piso"](dep1, "Primer piso")
    esperar("otro piso, sin repetir el nombre", (bool(piso2), ns["crear_piso"](dep1, "Primer piso")[0]),
            (True, None))
    esperar("guardar el plano", ns["guardar_plano"](piso1, r)[:2],
            (True, "💾 Plano guardado: 6 estantería(s) nueva(s)."))
    ns["guardar_plano"](piso2, rapido(1, 2, 3, 1))
    esperar("los códigos: en el primer piso, la A ya está: A2 y B2",
            [e["codigo"] for e in ns["estanterias_del_piso"](piso2).values()], ["A2", "B2"])
    esperar("un plano vacío no se guarda", ns["guardar_plano"](piso1, "  \n ")[0], False)

    # 8. Dónde está: el lugar del mapa, o None si no existe (módulo o estante de más).
    donde = ns["lugar_en_el_mapa"]
    d = donde("c 2 3")
    esperar("dónde está C-2-3", (d["texto"], d["celdas"], d["piso_id"], d["se_lee"]),
            ("C-2-3", ((3, 4),), piso1,
             "Central · Planta baja · estantería C, módulo 2, estante 3 (desde abajo)"))
    esperar("lo que no está en el mapa", [donde("C-6"), donde("C-1-5"), donde("Z-1"), donde(""),
                                          donde("A2-1")["piso_id"]], [None, None, None, None, piso2])
    esperar("hay mapa", ns["hay_mapa"](), True)

    # 9. Ubicar: con mapa, solo un lugar que existe, escrito como en el mapa, y queda en el
    # historial de la ficha.
    ok, texto = ubicar(ids["W712"], " a 3 2 ")
    esperar("ubicar W712 en A-3-2", (ok, uno("SELECT ubicacion FROM productos WHERE id = ?", ids["W712"]),
                                     uno("SELECT motivo FROM historial_de_medidas WHERE "
                                         "producto_id = ? AND campo = 'ubicacion'", ids["W712"]),
                                     "Central · Planta baja" in texto), (True, "A-3-2", "ubicado", True))
    esperar("con mapa, un lugar que no existe no", (ubicar(ids["W712"], "A-9")[0],
                                                    ubicar(ids["W712"], "estante del fondo")[0],
                                                    uno("SELECT ubicacion FROM productos WHERE id = ?",
                                                        ids["W712"])), (False, False, "A-3-2"))
    esperar("vacío le saca el lugar", (ubicar(ids["W715"], "")[0],
                                       uno("SELECT ubicacion FROM productos WHERE id = ?", ids["W715"])),
            (True, None))

    # 10. Qué es lo escaneado al ubicar: la etiqueta nuestra, la caja, un lugar, un código de un
    # solo producto; uno de varias marcas, no.
    que = ns["que_es_lo_escaneado_al_ubicar"]
    esperar("qué es lo escaneado", [que(ns["codigo_nuestro"](ids["W713"])), que(ean),
                                    que("B-1-1")[1]["texto"], que("w712"), que("DOS")[0],
                                    "más de un producto" in que("DOS")[1], que("nada-9")[0], que("")],
            [("producto", ids["W713"]), ("producto", ids["W714"]), "B-1-1",
             ("producto", ids["W712"]), None, True, None, (None, "")])

    # 11. Pegar una lista: lo que está bien se ubica, lo otro dice por qué.
    lista = "W713\tB-1-1\nW714; C-5-4\nDOS A-1-1\nW712 Z-1\nsolo\n\n"
    rev = ns["ubicar_de_una_lista"](lista)
    esperar("la lista revisada", [(f["Renglón"], f["Lugar"], bool(f["Problema"])) for f in rev],
            [(1, "B-1-1", False), (2, "C-5-4", False), (3, "A-1-1", True), (4, "Z-1", True),
             (5, "", True)])
    hecho = ns["ubicar_de_una_lista"](lista, guardar=True)
    esperar("guardada: solo las que estaban bien",
            ([f.get("Guardado") for f in hecho],
             [uno("SELECT ubicacion FROM productos WHERE id = ?", ids[k]) for k in ("W713", "W714")]),
            (["✅", "✅", None, None, None], ["B-1-1", "C-5-4"]))

    # 12. Lo que hay en una estantería, y sacarla o achicarla con cosas adentro se avisa.
    esperar("qué hay en la C", [(f["codigo_raw"], f["modulo"], f["nivel"])
                                for f in ns["productos_en"]("c")], [("W714", 5, 4)])
    esperar("cuántos hay en cada una", ns["cuantos_hay_en_cada_estanteria"](), {"A": 1, "B": 1, "C": 1})
    sin_c = sacar(r, "C")
    achicada = r.replace("CCCCC", "CCC..")
    esperar("lo que se perdería", (ns["lo_que_se_pierde_con"](piso1, sin_c),
                                   ns["lo_que_se_pierde_con"](piso1, achicada),
                                   ns["guardar_plano"](piso1, sin_c)[0],
                                   ns["lugar_en_el_mapa"]("C-5-4") is not None),
            ([("C", 1, "se saca del plano")],
             [("C", 1, "queda de 3 módulos y hay cosas más allá")], False, True))
    ok, _, _ = ns["guardar_plano"](piso1, achicada, aunque_se_pierdan=True)
    esperar("guardado igual: la C-5-4 ya no está en el mapa", (ok, ns["lugar_en_el_mapa"]("C-5-4")),
            (True, None))
    ns["guardar_plano"](piso1, r)

    # 13. El código y los estantes de una estantería: cambiar el código pasa lo ubicado al
    # código nuevo; lo que no sirve como código, no.
    est = ns["estanterias_del_piso"](piso1)
    ok, texto = ns["guardar_estanteria"](est["A"]["id"], "x", 6)
    esperar("A → X con 6 estantes", (ok, uno("SELECT ubicacion FROM productos WHERE id = ?", ids["W712"]),
                                     "pasaron de A a X" in texto,
                                     ns["lugar_en_el_mapa"]("X-1-6") is not None),
            (True, "X-3-2", True, True))
    esperar("códigos que no", [ns["guardar_estanteria"](est["B"]["id"], cod, niv)[0]
                               for cod, niv in (("X", 4), ("CH12", 4), ("A B", 4), ("B", 0),
                                                ("B", 21), ("B", "tres"))],
            [False] * 6)

    # 14. Cómo ordena la cola cada piso.
    esperar("elegir el orden", [ns["elegir_orden_de_la_cola"](piso1, "cercania", 2)[0],
                                ns["elegir_orden_de_la_cola"](piso1, "al azar")[0],
                                ns["elegir_orden_de_la_cola"](piso1, "cercania", 0)[0],
                                uno("SELECT orden_de_la_cola || '/' || minutos_de_cercania "
                                    "FROM pisos WHERE id = ?", piso1)],
            [True, False, False, "cercania/2.0"])

    # 15. La cola por piso: cada piso en su orden; por cercanía, desde lo último que entregó
    # ESE usuario hace menos de los minutos del piso; si no, desde la entrada. Lo que no tiene
    # lugar, al final.
    ubicar(ids["W713"], "F-4-1")
    ubicar(ids["W714"], "C-1-1")
    c.execute("UPDATE productos SET ubicacion = 'mesa' WHERE id = ?", (ids["W715"],))
    c.execute("UPDATE productos SET ubicacion = 'A2-1-1' WHERE id = ?",
              (uno("SELECT id FROM productos WHERE codigo_raw = 'DOS' AND descripcion = 'OTRA MARCA'"),))
    conn.commit()

    def pendiente(pid, ubicacion):
        return {"id": pid, "producto_id": pid, "ubicacion": ubicacion, "pedido_en": "2026-01-01"}

    cola = [pendiente(ids["W712"], "X-3-2"), pendiente(ids["W713"], "F-4-1"),
            pendiente(ids["W714"], "C-1-1"), pendiente(ids["W715"], "mesa"),
            pendiente(99, "A2-1-1")]
    esperar("lo de la A2 no es de la A", ([f["codigo_raw"] for f in ns["productos_en"]("A2")],
                                           ns["productos_en"]("A")), (["DOS"], []))
    ns["elegir_orden_de_la_cola"](piso1, "ubicacion")
    grupos = ns["la_cola_por_piso"](cola, usuario="dep")
    esperar("por piso; la planta baja por ubicación",
            [(gr["piso"], [i["donde"]["texto"] if i["donde"] else i["ubicacion"] for i in gr["items"]],
              [i["paso"] for i in gr["items"]]) for gr in grupos],
            [("Planta baja", ["C-1-1", "F-4-1", "X-3-2"], [1, 2, 3]),
             ("Primer piso", ["A2-1-1"], [1]), ("Sin lugar en el mapa", ["mesa"], [1])])
    ns["elegir_orden_de_la_cola"](piso1, "cercania", 1)
    orden_pb = lambda u="dep": [i["donde"]["texto"] for i in ns["la_cola_por_piso"](cola, usuario=u)[0]["items"]]
    # De la F, la X y la C quedan a 11 pasos: a igual distancia, la que se pidió primero.
    esperar("por cercanía, desde la entrada: F, X, C", orden_pb(), ["F-4-1", "X-3-2", "C-1-1"])
    # «dep» acaba de entregar algo de la X: sigue desde ahí. Para otro usuario, no.
    c.execute("""INSERT INTO pedidos_deposito (producto_id, cantidad, estado, resuelto_por,
                                               resuelto_en, pedido_por)
                 VALUES (?, 1, 'entregado', 'dep', datetime('now', 'localtime', '-20 seconds'), 'ana')""",
              (ids["W712"],))
    ultimo = c.lastrowid
    conn.commit()
    grupo = ns["la_cola_por_piso"](cola, usuario="dep")[0]
    esperar("recién entregado lo de la X: desde ahí (C, F, X)",
            (orden_pb(), grupo["desde"].startswith("desde X-3-2"), orden_pb("otro")),
            (["X-3-2", "C-1-1", "F-4-1"], True, ["F-4-1", "X-3-2", "C-1-1"]))
    c.execute("UPDATE pedidos_deposito SET resuelto_en = datetime('now', 'localtime', '-2 minutes') "
              "WHERE id = ?", (ultimo,))
    conn.commit()
    esperar("pasado el minuto: desde la entrada", orden_pb(), ["F-4-1", "X-3-2", "C-1-1"])
    ns["elegir_orden_de_la_cola"](piso1, "cercania", 5)
    esperar("con 5 minutos de margen, todavía desde la X", orden_pb(), ["X-3-2", "C-1-1", "F-4-1"])
    # Lo último fue en otro piso: en este se arranca de la entrada.
    c.execute("""INSERT INTO pedidos_deposito (producto_id, cantidad, estado, resuelto_por,
                                               resuelto_en)
                 VALUES (?, 1, 'entregado', 'dep', datetime('now', 'localtime'))""",
              (uno("SELECT id FROM productos WHERE descripcion = 'OTRA MARCA'"),))
    conn.commit()
    esperar("lo último fue en el primer piso: acá, desde la entrada", orden_pb(),
            ["F-4-1", "X-3-2", "C-1-1"])

    # 16. El dibujo: los códigos, lo resaltado con su número y el recorrido.
    svg = ns["svg_del_piso"](r, {"A": "X"}, [(((4, 2),), "1,3")], [(7, 8), (7, 7)])
    esperar("el dibujo", (svg.startswith("<svg"), ">X</text>" in svg, ">A</text>" in svg,
                          "#E8A33D" in svg, ">1,3</text>" in svg, "<polyline" in svg,
                          ">ENT</text>" in svg, ns["svg_del_piso"]("")),
            (True, True, False, True, True, True, True, ""))

    # 17. Dónde poner lo que no tiene lugar: lo que tiene stock o se vende, en lo libre más a
    # mano (cerca de la entrada, a la altura de la cintura). El mejor, E-5-2, ya está ocupado.
    ubicar(ids["W715"], "E-5-2")
    sugeridos = ns["lugares_sugeridos"]()
    esperar("lugares sugeridos", ([s["producto"] for s in sugeridos][:1],
                                  sugeridos[0]["lugar"] if sugeridos else None,
                                  all(ns["lugar_en_el_mapa"](s["lugar"]) for s in sugeridos),
                                  len({s["lugar"] for s in sugeridos}) == len(sugeridos),
                                  any(s["lugar"] in ("X-3-2", "F-4-1", "C-1-1") for s in sugeridos)),
            (["PRUEBA DOS"], "F-1-2", True, True, False))

    # El «📦 Armar pedido» del buscador: por piso, y adentro de cada uno por ubicación; lo que
    # no tiene lugar, al final.
    picking = ns["armar_lista_picking"]("W712, DOS, W713, W714, W715")
    esperar("armar pedido con el mapa",
            [(r["Codigo"], r["Ubicación"], r.get("Dónde")) for r in picking],
            [("W714", "C-1-1", "Central · Planta baja"), ("W715", "E-5-2", "Central · Planta baja"),
             ("W713", "F-4-1", "Central · Planta baja"), ("W712", "X-3-2", "Central · Planta baja"),
             ("DOS", "A2-1-1", "Central · Primer piso"), ("DOS", None, None)])

    # 18. Las etiquetas de los estantes: una por módulo y estante, con el lugar en las barras.
    from fpdf import FPDF
    barras, original = [], FPDF.code39
    FPDF.code39 = lambda self, texto, x, y, w=1.5, h=5: (barras.append(texto),
                                                         original(self, texto, x, y, w, h))
    try:
        pdf = ns["pdf_de_etiquetas_de_ubicaciones"]([est["B"]["id"]])
        vacio = ns["etiquetas_de_ubicaciones_para_descargar"]([999999])()
    finally:
        FPDF.code39 = original
    esperar("etiquetas de la B: 5 módulos × 4 estantes",
            (pdf[:4], len(barras), barras[:2], barras[-1], vacio), (b"%PDF", 20, ["*B-1-1*", "*B-1-2*"],
                                                                   "*B-5-4*", b""))

    # 19. Los del depósito: entran directo al depósito; el administrador nunca.
    ns["crear_usuario"]("dep", "clave-dep-1", "operador", solo_deposito=True)
    ns["crear_usuario"]("jefa", "clave-jefa-1", "admin", solo_deposito=True)
    st.session_state["admin_nombre"], st.session_state["nivel_usuario"] = "dep", "operador"
    del_dep = ns["es_del_deposito"]()
    st.session_state["admin_nombre"], st.session_state["nivel_usuario"] = "jefa", "admin"
    jefa = ns["es_del_deposito"]()
    id_dep = uno("SELECT id FROM usuarios WHERE nombre = 'dep'")
    id_jefa = uno("SELECT id FROM usuarios WHERE nombre = 'jefa'")
    # Aunque la base dijera que la administradora es del depósito, ve todo.
    c.execute("UPDATE usuarios SET solo_deposito = 1 WHERE id = ?", (id_jefa,))
    conn.commit()
    jefa = jefa or ns["es_del_deposito"]()
    c.execute("UPDATE usuarios SET solo_deposito = 0 WHERE id = ?", (id_jefa,))
    conn.commit()
    esperar("los del depósito", (del_dep, jefa, ns["cambiar_solo_deposito"](id_jefa, True),
                                 uno("SELECT solo_deposito FROM usuarios WHERE id = ?", id_jefa),
                                 ns["cambiar_solo_deposito"](id_dep, False),
                                 uno("SELECT solo_deposito FROM usuarios WHERE id = ?", id_dep),
                                 ns["PAGINAS_DEL_DEPOSITO"]),
            (True, False, False, 0, True, 0, ["📦 Depósito", "↩️ Devoluciones"]))
    for k in ("admin_nombre", "nivel_usuario"):
        st.session_state.pop(k, None)

    # 20. Quién puede: armar y ubicar, un empleado; borrar un piso o un depósito, el
    # administrador.
    originales = (g["_nivel_de_quien_esta_adentro"], g["hay_claves_configuradas"])
    g["hay_claves_configuradas"] = lambda: True
    try:
        for nivel, empleado, admin in (("", False, False), ("mecanico", False, False),
                                       ("operador", True, False), ("admin", True, True)):
            g["_nivel_de_quien_esta_adentro"] = lambda n=nivel: n
            resultado = []
            for funcion, args in ((ns["crear_deposito"], ("",)), (ns["guardar_plano"], (piso2, "")),
                                  (ns["ubicar_producto"], (ids["W712"], "X-3-2")),
                                  (ns["elegir_orden_de_la_cola"], (piso2, "?")),
                                  (ns["borrar_piso"], (999999,)), (ns["borrar_deposito"], (999999,))):
                try:
                    funcion(*args)
                    resultado.append(True)
                except PermissionError:
                    resultado.append(False)
            esperar(f"nivel «{nivel or 'invitado'}»: armar, ubicar, borrar", resultado,
                    [empleado] * 4 + [admin] * 2)
    finally:
        g["_nivel_de_quien_esta_adentro"], g["hay_claves_configuradas"] = originales

    # 21. Borrar el depósito se lleva sus pisos y estanterías; lo ubicado conserva su texto.
    ns["borrar_deposito"](dep1)
    esperar("borrado el depósito", (uno("SELECT COUNT(*) FROM pisos"), uno("SELECT COUNT(*) FROM estanterias"),
                                    uno("SELECT ubicacion FROM productos WHERE id = ?", ids["W712"]),
                                    ns["lugar_en_el_mapa"]("X-3-2"), ns["hay_mapa"]()),
            (0, 0, "X-3-2", None, False))
    return fallas


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_mapa_")
    try:
        fallas = probar(_cargar_la_logica(carpeta))
        for f in fallas:
            print("   ✗", f)
        print("✅ mapa del depósito: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

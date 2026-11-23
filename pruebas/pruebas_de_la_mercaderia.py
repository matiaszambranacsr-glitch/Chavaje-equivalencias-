"""«📦 Entró mercadería»: el stock propio, cargado escaneando o con el remito.

Uso:
    python3 pruebas/pruebas_de_la_mercaderia.py

Por qué: en la copia de la base real ningún producto tenía stock, y sin stock no andan «⏳ Anotar
que lo espera» con su «📲 Avisarle», el «sin stock» de los pedidos ni el orden por lo que hay.
Esto controla que escanear sume (dos veces, dos), que un código de varias marcas se elija, que
«✅ Sumar al stock» sume y lo anote, que la misma entrada no se sume dos veces sin querer, que
avise si alguien esperaba algo de lo que entró, que el remito se lea bien y que solo el personal
sume (ver «ENTRÓ MERCADERÍA: EL STOCK PROPIO» en logica/deposito.py). Y, del otro lado del
mostrador, que «🔁 Lo que suele llevar» muestre en Ventas lo que la cuenta compra siempre, y
que lo pedido al proveedor quede anotado, llegue solo al entrar y se reclame si no llega.

Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import os
import shutil
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def probar():
    from streamlit.testing.v1 import AppTest
    fallas = []

    def esperar(que, dio, se_esperaba):
        if dio != se_esperaba:
            fallas.append(f"{que}: dio {dio!r}, se esperaba {se_esperaba!r}")

    def cierto(que, ok, detalle=""):
        if not ok:
            fallas.append(f"{que} {str(detalle)[:200]}")

    at = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
    at.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
    at.run()
    at.text_input(key="login_inicial_nombre").set_value("duenio")
    at.text_input(key="login_inicial_clave").set_value("clave-duenio-1")
    [b for b in at.button if "Ingresar con contraseña" in b.label][0].click().run()
    ns = sys.modules["logica"].todo_lo_de_la_logica()
    c = ns["c"]

    for marca in ("MARCA ENTRA", "OTRA ENTRA"):
        c.execute("INSERT OR IGNORE INTO marcas (nombre, tipo) VALUES (?, 'PROVEEDOR')", (marca,))
    ids = {}
    for codigo, marca, stock in (("E1", "MARCA ENTRA", None), ("E2", "MARCA ENTRA", 3),
                                 ("DUP1", "MARCA ENTRA", None), ("DUP1", "OTRA ENTRA", None)):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, "
                  "precio, stock) SELECT ?, ?, 'FILTRO', id, 100, ? FROM marcas WHERE nombre = ?",
                  (codigo, codigo, stock, marca))
        ids[(codigo, marca)] = c.lastrowid
    ns["conn"].commit()
    e1, e2 = ids[("E1", "MARCA ENTRA")], ids[("E2", "MARCA ENTRA")]
    dup_otra = ids[("DUP1", "OTRA ENTRA")]
    # Ana espera un E1, que hoy no tiene stock.
    ns["anotar_consulta_cliente"]("Ana", "11 4567-8901", e1, "E1", "FILTRO", 1)

    at.session_state["pagina_actual"] = ns["PAGINAS"][8]
    at.session_state["sub_deposito"] = ns["SUB_DEPOSITO"][4]
    at.run()

    def escanear(codigo, cantidad=1):
        at.text_input(key="entro_codigo").set_value(codigo)
        at.number_input(key="entro_cant").set_value(cantidad)
        [b for b in at.button if b.label == "➕ Sumar"][0].click().run()

    # 1. ESCANEAR: suma, y lo mismo dos veces suma dos (y el campo de la cantidad lo muestra).
    if not [b for b in at.button if b.label == "➕ Sumar"]:
        return fallas + ["no está la solapa «📦 Entró mercadería» "
                         f"({[e.value for e in at.exception][:1]})"]
    escanear("E1", 2)
    escanear("e-1")              # escrito distinto, el mismo código
    esperar("escaneado dos veces: suma", at.session_state["entro_lista"], {str(e1): 3})
    esperar("y el campo de la cantidad lo muestra",
            at.number_input(key=f"entro_cant_{e1}").value, 3)
    escanear("NOEXISTE")
    cierto("lo que no está en el catálogo se dice",
           any("no está en el catálogo" in w.value for w in at.warning))
    # 2. UN CÓDIGO DE VARIAS MARCAS: se elige cuál entró.
    escanear("DUP1", 4)
    _cual = [s for s in at.selectbox if str(s.key).startswith("entro_cual_")]
    cierto("un código de dos marcas pregunta cuál entró", _cual)
    if _cual:
        _cual[0].set_value(dup_otra).run()
        at.button(key="entro_cual_si").click().run()
    esperar("y suma a la elegida", at.session_state["entro_lista"],
            {str(e1): 3, str(dup_otra): 4})

    # 3. «✅ SUMAR AL STOCK»: suma, lo anota, vacía la lista y avisa que Ana esperaba el E1.
    at.button(key="entro_sumar").click().run()
    esperar("sumado al stock (lo que no tenía stock arranca de cero)",
            [c.execute("SELECT stock FROM productos WHERE id = ?", (x,)).fetchone()[0]
             for x in (e1, dup_otra, e2)], [3, 4, 3])
    esperar("y anotado en el registro de cambios, uno por producto",
            c.execute("SELECT COUNT(*) FROM registro_de_cambios "
                      "WHERE accion = 'entró mercadería'").fetchone()[0], 2)
    esperar("la lista queda vacía", at.session_state["entro_lista"], {})
    cierto("avisa que alguien esperaba algo de lo que entró",
           any("esperaban algo de lo que entró" in x.value for x in at.info),
           [x.value for x in at.info])
    esperar("y Ana sale para avisarle",
            [x["Cliente"] for x in ns["consultas_que_ahora_hay_en_stock"]()], ["Ana"])

    # 4. LA MISMA ENTRADA OTRA VEZ: avisa, y no se suma sin decir que es otra.
    escanear("E1", 3)
    escanear("DUP1", 4)
    _cual = [s for s in at.selectbox if str(s.key).startswith("entro_cual_")]
    if _cual:
        _cual[0].set_value(dup_otra).run()
        at.button(key="entro_cual_si").click().run()
    cierto("la misma entrada otra vez: avisa que ya se sumó",
           any("ya se sumó al stock" in w.value for w in at.warning))
    esperar("y el botón queda frenado hasta decir que es otra",
            at.button(key="entro_sumar").disabled, True)
    at.checkbox(key="entro_igual").check().run()
    at.button(key="entro_sumar").click().run()
    esperar("dicho que es otra, se suma", c.execute(
        "SELECT stock FROM productos WHERE id = ?", (e1,)).fetchone()[0], 6)

    # 4b. EL CONTEO: escanear cada unidad la cuenta, y deja el stock en lo contado (con la
    # diferencia anotada); lo que no se contó queda como estaba.
    at.radio(key="entro_modo").set_value(ns["MODOS_DE_LA_ENTRADA"][1]).run()
    escanear("E2")
    escanear("E2")
    cierto("en el conteo, la diferencia a la vista (había 3, contado 2)",
           any("contado: 2 (-1)" in x.value for x in at.caption), [x.value for x in at.caption])
    at.button(key="entro_contar").click().run()
    esperar("el conteo deja el stock en lo contado, y lo demás como estaba",
            [c.execute("SELECT stock FROM productos WHERE id = ?", (x,)).fetchone()[0]
             for x in (e2, e1)], [2, 6])
    cierto("y dice qué cambió", any("MARCA ENTRA E2 3 → 2" in x.value for x in at.success),
           [x.value for x in at.success])
    esperar("anotado como conteo", c.execute(
        "SELECT antes, despues FROM registro_de_cambios WHERE accion = 'conteo de stock'")
        .fetchall() and [tuple(r) for r in c.execute(
            "SELECT antes, despues FROM registro_de_cambios WHERE accion = 'conteo de stock'")],
        [("3", "2")])
    at.radio(key="entro_modo").set_value(ns["MODOS_DE_LA_ENTRADA"][0]).run()

    # 4c. LO QUE SE ESTÁ POR TERMINAR: al ritmo al que se vende, con cuánto pedir.
    for _fecha, _cant, _anulada in (("-10 days", 20, 0), ("-40 days", 10, 0), ("-5 days", 50, 1),
                                    ("-90 days", 99, 0)):
        c.execute("INSERT INTO ventas (fecha, usuario, forma_de_pago, total, cobrada, anulada) "
                  "VALUES (datetime('now', ?), 'ana', 'Efectivo', 0, 1, ?)", (_fecha, _anulada))
        c.execute("INSERT INTO ventas_items (venta_id, producto_id, codigo, marca, cantidad, "
                  "precio) VALUES (?, ?, 'E1', 'MARCA ENTRA', ?, 100)", (c.lastrowid, e1, _cant))
    ns["conn"].commit()
    esperar("vendió 30 en 60 días (sin la anulada ni lo de hace 90) y quedan 6: alcanza 12 días, "
            "pedir 9 para cubrir 30",
            [(x["Codigo"], x["Vendidos"], x["Alcanza (días)"], x["Pedir"])
             for x in ns["se_esta_por_terminar"]()], [("E1", 30, 12, 9)])
    ns["invalidar_salud"]()
    esperar("con 12 días no avisa la campanita",
            [p["titulo"] for p in ns["diagnostico_de_salud"]() if "se terminan" in p["titulo"]], [])
    c.execute("UPDATE productos SET stock = 2 WHERE id = ?", (e1,))
    ns["conn"].commit()
    ns["invalidar_salud"]()
    esperar("con 2 (alcanza 4 días), la campanita lo dice",
            [p["titulo"] for p in ns["diagnostico_de_salud"]() if "se terminan" in p["titulo"]],
            ["🛒 1 producto(s) se terminan en menos de una semana"])
    c.execute("UPDATE productos SET stock = 6 WHERE id = ?", (e1,))
    ns["conn"].commit()
    at.session_state["pagina_actual"] = ns["PAGINAS"][4]
    at.session_state["sub_stats"] = "📌 Para pedir"
    at.run()
    _chk = [x for x in at.checkbox if x.key == f"chk_porterminar_{e1}"]
    cierto("en 📌 Para pedir, «🛒 Se está por terminar» con el E1", _chk)
    if _chk:
        _chk[0].check().run()
        cierto("y al marcarlo, el pedido al proveedor dice cuánto pedir",
               any("E1 (FILTRO) — quedan 6 — pedir 9" in t.value for t in at.text_area),
               [t.value for t in at.text_area][:2])

        # 4d. «📝 ANOTAR COMO PEDIDO»: queda en «🚚 Pedido y sin llegar», con lo que se pidió,
        # y la lista lo marca; anotarlo otra vez no lo duplica.
        _anotar = [b for b in at.button if (b.key or "").startswith("anotar_pedido_")]
        cierto("en el mensaje al proveedor, «📝 Anotar como pedido»", _anotar)
        if _anotar:
            _anotar[0].click().run()
            esperar("anotado como pedido",
                    [(x["Codigo"], x["Cantidad"], x["Llegaron"], x["Atrasado"])
                     for x in ns["pedidos_sin_llegar"]()], [("E1", 9, 0, False)])
            cierto("y avisa",
                   any("Anotado: 1 producto(s) pedidos a MARCA ENTRA" in str(x.value)
                       for x in at.success), [str(x.value)[:80] for x in at.success])
            cierto("y en «🛒 Se está por terminar» dice que ya está pedido",
                   any(x.key == f"chk_porterminar_{e1}" and "🚚 pedido el" in x.label
                       for x in at.checkbox))
            cierto("y se ve en «🚚 Pedido y sin llegar»",
                   any(b.key and b.key.startswith("llego_prov_") for b in at.button))
            [b for b in at.button if (b.key or "").startswith("anotar_pedido_")][0].click().run()
            esperar("anotado otra vez: no se duplica", len(ns["pedidos_sin_llegar"]()), 1)

    # 4e. LO QUE ENTRA LO DA POR LLEGADO: en partes, hasta completar lo pedido.
    _pp = {x["Codigo"]: x for x in ns["pedidos_sin_llegar"]()}
    if "E1" not in _pp:
        c.execute("INSERT INTO pedidos_a_proveedores (producto_id, cantidad) VALUES (?, 9)", (e1,))
    _, _, _llegaron = ns["sumar_al_stock"]({str(e1): 4})
    esperar("llegó una parte", _llegaron, ["MARCA ENTRA E1 (llegaron 4 de 9)"])
    esperar("y sigue pedido lo que falta",
            [(x["Codigo"], x["Llegaron"]) for x in ns["pedidos_sin_llegar"]()], [("E1", 4)])
    _, _, _llegaron = ns["sumar_al_stock"]({str(e1): 6})
    esperar("llegó el resto", _llegaron, ["MARCA ENTRA E1"])
    esperar("y ya no está pedido", ns["pedidos_sin_llegar"](), [])
    esperar("queda como llegado, con todo lo pedido",
            [tuple(f) for f in c.execute("SELECT estado, llegaron, llego_en IS NOT NULL FROM "
                                         "pedidos_a_proveedores WHERE producto_id = ?", (e1,))],
            [("llego", 9, 1)])
    _, _, _llegaron = ns["sumar_al_stock"]({str(e1): 1})
    esperar("lo que entra sin pedido no toca nada", _llegaron, [])

    # 4f. LO MARCADO CON «📌 PEDIR», AL ANOTARLO, SALE DE «🙋 PEDIDOS MARCADOS»; lo que no llega
    # en DIAS_PARA_RECLAMAR_EL_PEDIDO va a la campanita, con el mensaje para reclamarlo.
    ns["solicitar_reposicion"](e2)
    _marcado = ns["listar_pedidos_reposicion"]("pendiente")[0]["ID"]
    at.session_state["pagina_actual"] = ns["PAGINAS"][4]
    at.session_state["sub_stats"] = "📌 Para pedir"
    at.run()
    _chk_m = [x for x in at.checkbox if x.key == f"chk_pedido_{_marcado}"]
    cierto("en «🙋 Pedidos marcados», el E2", _chk_m)
    if _chk_m:
        _chk_m[0].check().run()
        _anotar = [b for b in at.button if (b.key or "").startswith("anotar_pedido_")]
        cierto("y su «📝 Anotar como pedido»", _anotar)
        if _anotar:
            _anotar[0].click().run()
    esperar("anotado lo marcado (el producto, no el número del pedido)",
            [(x["Codigo"], x["Cantidad"]) for x in ns["pedidos_sin_llegar"]()], [("E2", None)])
    esperar("y deja de estar marcado para pedir",
            [x["Codigo"] for x in ns["listar_pedidos_reposicion"]("pendiente")], [])
    c.execute("UPDATE pedidos_a_proveedores SET pedido_en = datetime('now', ?) "
              "WHERE producto_id = ? AND estado = 'pedido'",
              (f"-{ns['DIAS_PARA_RECLAMAR_EL_PEDIDO'] + 2} days", e2))
    ns["conn"].commit()
    esperar("uno de hoy, otra vez", ns["anotar_el_pedido_al_proveedor"]([(e1, 3)]), (1, 0))
    _atr = ns["pedidos_sin_llegar"]()
    esperar("el atrasado primero, y el de hoy sin reclamar",
            [(x["Codigo"], x["Atrasado"]) for x in _atr], [("E2", True), ("E1", False)])
    esperar("la campanita",
            [p["titulo"] for p in ns["diagnostico_de_salud"]() if "sin llegar" in p["titulo"]],
            [f"🚚 1 pedido(s) a proveedores sin llegar hace más de "
             f"{ns['DIAS_PARA_RECLAMAR_EL_PEDIDO']} días"])
    _reclamo = ns["mensaje_para_reclamar_el_pedido"](_atr[:1])
    cierto("el mensaje para reclamarlo", "- E2 (FILTRO) — pedido el " in _reclamo
           and _reclamo.startswith("Hola! Todavía no me llegó"), _reclamo)
    at.session_state["pagina_actual"] = ns["PAGINAS"][4]
    at.session_state["sub_stats"] = "📌 Para pedir"
    at.run()
    cierto("en 📌 Para pedir, «⏰ Reclamarle a MARCA ENTRA (1)»",
           any("Reclamarle a MARCA ENTRA (1)" in str(getattr(x, "label", "")) or
               "Reclamarle a MARCA ENTRA (1)" in str(x.proto) for x in at.get("link_button")),
           [str(x.proto)[:120] for x in at.get("link_button")][:3])
    _cancelar = [b for b in at.button if b.key == f"cancelar_prov_{_atr[0]['ID']}"]
    cierto("y su «🗑️ No va a venir»", _cancelar)
    if _cancelar:
        _cancelar[0].click().run()
    esperar("cancelado, ya no está pedido",
            [x["Codigo"] for x in ns["pedidos_sin_llegar"]()], ["E1"])
    _llego = [b for b in at.button if b.key == f"llego_prov_{_atr[1]['ID']}"]
    cierto("y el «✅ Llegó» del otro", _llego)
    if _llego:
        _llego[0].click().run()
    esperar("llegado a mano, tampoco", ns["pedidos_sin_llegar"](), [])
    esperar("y quedan así",
            [tuple(f) for f in c.execute("SELECT estado FROM pedidos_a_proveedores "
                                         "ORDER BY id DESC LIMIT 2")], [("llego",), ("cancelado",)])

    # 4g. CUÁNTO TARDA CADA PROVEEDOR: con lo llegado (2 y 4 días), lo cancelado aparte.
    for _dias, _orden in ((2, "ASC"), (4, "DESC")):
        c.execute(f"""UPDATE pedidos_a_proveedores SET pedido_en = datetime(llego_en, ?)
                      WHERE id = (SELECT id FROM pedidos_a_proveedores WHERE estado = 'llego'
                                  ORDER BY id {_orden} LIMIT 1)""", (f"-{_dias} days",))
    ns["conn"].commit()
    esperar("cuánto tarda cada proveedor", ns["cuanto_tarda_cada_proveedor"](),
            [{"Marca": "MARCA ENTRA", "Llegaron": 2, "Tarda (días)": 3.0,
              "El más lento (días)": 4.0, "Sin llegar": 0, "Cancelados": 1}])
    at.session_state["exp_cuanto_tarda"] = True
    at.run()
    cierto("y en 📌 Para pedir, la tabla con «3,0» días",
           any("3,0" in d.value.to_string() for d in at.dataframe),
           [d.value.to_string()[:200] for d in at.dataframe][:1])

    _filas = [["Artículo", "Descripción", "Cant."], ["E2", "FILTRO", "5"],
              ["NOPE", "X", "1"], ["DUP1", "FILTRO", "2"], ["E1", "FILTRO", "0"], ["", "", ""]]
    esperar("la columna de la cantidad, por su título",
            ns["_columna_que_dice"](_filas[0], r"CANT|UNID|CNT|QTY"), 2)
    esperar("el remito: lo que está se suma; lo que no, y lo de varias marcas, se dice",
            ns["leer_el_remito_de_entrada"](_filas, 0, 2), ([(e2, 5)], ["NOPE"], ["DUP1"]))

    # 5b. LO QUE SUELE LLEVAR la cuenta que se atiende, en 🧾 Ventas: a la vista y a un toque.
    _taller = ns["crear_mecanico"]("Taller Suele")
    for _dias in (3, 1):
        c.execute("INSERT INTO ventas (fecha, usuario, forma_de_pago, total, cobrada, anulada, "
                  "mecanico_id) VALUES (datetime('now', ?), 'ana', 'Cuenta', 0, 0, 0, ?)",
                  (f"-{_dias} days", _taller))
        c.execute("INSERT INTO ventas_items (venta_id, producto_id, codigo, marca, cantidad, "
                  "precio) VALUES (?, ?, 'E2', 'MARCA ENTRA', 1, 100)", (c.lastrowid, e2))
    ns["conn"].commit()
    at.session_state["cuenta_elegida"] = {"id": _taller, "nombre": "Taller Suele",
                                          "desde": time.time()}
    at.session_state["pagina_actual"] = ns["PAGINAS"][9]
    at.session_state["exp_lo_que_suele_llevar"] = True
    at.run()
    _suele = [b for b in at.button if b.key == f"suele_{e2}"]
    cierto("en 🧾 Ventas, «🔁 Lo que suele llevar» con el E2",
           _suele and any("Lo que suele llevar Taller Suele" in x.label for x in at.expander),
           [x.label for x in at.expander][:6])
    if _suele:
        _suele[0].click().run()
        esperar("y el ➕ lo suma a la venta",
                [(x["codigo"], x["cantidad"]) for x in at.session_state["venta_items"]],
                [("E2", 1)])
    at.session_state["cuenta_elegida"] = None
    at.session_state["venta_items"] = []

    # 6. SOLO EL PERSONAL suma al stock y anota o cierra los pedidos a los proveedores.
    _g = ns["sumar_al_stock"].__globals__
    _antes = (_g["_nivel_de_quien_esta_adentro"], _g["hay_claves_configuradas"])
    try:
        _g["hay_claves_configuradas"] = lambda: True
        for _nivel in ("", "mecanico"):
            _g["_nivel_de_quien_esta_adentro"] = lambda n=_nivel: n
            for _que, _hacer in (
                    ("sumar al stock", lambda: ns["sumar_al_stock"]({str(e2): 1})),
                    ("anotar un pedido al proveedor",
                     lambda: ns["anotar_el_pedido_al_proveedor"]([(e2, 1)])),
                    ("cerrar un pedido al proveedor",
                     lambda: ns["cerrar_el_pedido_al_proveedor"](1))):
                try:
                    _hacer()
                    fallas.append(f"«{_nivel or 'invitado'}» pudo {_que}")
                except PermissionError:
                    pass
    finally:
        _g["_nivel_de_quien_esta_adentro"], _g["hay_claves_configuradas"] = _antes
    fallas += [f"se rompió: {e.value}" for e in at.exception][:2]
    return fallas


def main():
    os.environ["EQUIVALENCIAS_SIN_TAREAS_DE_FONDO"] = "1"
    carpeta = tempfile.mkdtemp(prefix="pruebas_mercaderia_")
    os.chdir(carpeta)
    sys.path.insert(0, RAIZ)
    try:
        fallas = probar()
        for f in fallas:
            print("   ✗", f[:300])
        print("✅ mercadería: escanear suma, se elige la marca, se suma al stock una vez y avisa "
              "a quien esperaba" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(RAIZ)
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

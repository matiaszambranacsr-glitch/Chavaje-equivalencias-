"""«📦 Entró mercadería»: el stock propio, cargado escaneando o con el remito.

Uso:
    python3 pruebas/pruebas_de_la_mercaderia.py

Por qué: en la copia de la base real ningún producto tenía stock, y sin stock no andan «⏳ Anotar
que lo espera» con su «📲 Avisarle», el «sin stock» de los pedidos ni el orden por lo que hay.
Esto controla que escanear sume (dos veces, dos), que un código de varias marcas se elija, que
«✅ Sumar al stock» sume y lo anote, que la misma entrada no se sume dos veces sin querer, que
avise si alguien esperaba algo de lo que entró, que el remito se lea bien y que solo el personal
sume (ver «ENTRÓ MERCADERÍA: EL STOCK PROPIO» en logica/deposito.py).

Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import os
import shutil
import sys
import tempfile

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

    # 5. EL REMITO: el código y la cantidad, cotejados con el catálogo.
    _filas = [["Artículo", "Descripción", "Cant."], ["E2", "FILTRO", "5"],
              ["NOPE", "X", "1"], ["DUP1", "FILTRO", "2"], ["E1", "FILTRO", "0"], ["", "", ""]]
    esperar("la columna de la cantidad, por su título",
            ns["_columna_que_dice"](_filas[0], r"CANT|UNID|CNT|QTY"), 2)
    esperar("el remito: lo que está se suma; lo que no, y lo de varias marcas, se dice",
            ns["leer_el_remito_de_entrada"](_filas, 0, 2), ([(e2, 5)], ["NOPE"], ["DUP1"]))

    # 6. SOLO EL PERSONAL suma al stock.
    _g = ns["sumar_al_stock"].__globals__
    _antes = (_g["_nivel_de_quien_esta_adentro"], _g["hay_claves_configuradas"])
    try:
        _g["hay_claves_configuradas"] = lambda: True
        for _nivel in ("", "mecanico"):
            _g["_nivel_de_quien_esta_adentro"] = lambda n=_nivel: n
            try:
                ns["sumar_al_stock"]({str(e2): 1})
                fallas.append(f"«{_nivel or 'invitado'}» pudo sumar al stock")
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

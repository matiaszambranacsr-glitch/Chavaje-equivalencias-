"""Pruebas del buscador con la app real (AppTest): una búsqueda que falla no se confunde con
«no hay», una letra sola no busca, y cada búsqueda queda medida con su código.

Uso:
    python3 pruebas/pruebas_del_buscador.py

Lo propuso una revisión con ChatGPT: «distinguir “no hay datos” de “falló la búsqueda”», un
«request_id» por operación y métricas del buscador. Antes, una búsqueda que fallaba cortaba la
pantalla entera con el error técnico. Ver anotar_busqueda() en logica/salud.py.

Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import threading

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def probar():
    from streamlit.testing.v1 import AppTest
    fallas = []

    def esperar(nombre, real, esperado):
        if real != esperado:
            fallas.append(f"{nombre}: dio {real!r}, se esperaba {esperado!r}")

    at = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
    at.run()
    # La app arranca en lo primero de la barra (🧾 Ventas: ver ORDEN_DE_LAS_PAGINAS).
    at.session_state["pagina_actual"] = "🔍 Buscador"
    at.run()
    ns = sys.modules["logica"].todo_lo_de_la_logica()
    c, conn = ns["c"], ns["conn"]
    g = ns["inflacion_desde"].__globals__

    # 0. Lo que pediría la primera búsqueda se armó por atrás al entrar, y una sola vez por
    # proceso (ver dejar_listo_de_antemano()). Si la búsqueda tuviera que armarlo, contar las
    # palabras falla: con la copia real, eran 0,94 s de la primera búsqueda después de reiniciar.
    # Se mira la marca y no el hilo: con la base chica, el hilo ya puede haber terminado.
    _lanzado = g["del_proceso"]("lo_de_antemano_lanzado", threading.Event).is_set()
    for _h in [h for h in threading.enumerate() if h.name == "de_antemano"]:
        _h.join(60)
    ns["dejar_listo_de_antemano"]()
    esperar("se arma por atrás al entrar, una sola vez",
            (_lanzado, [h.name for h in threading.enumerate()].count("de_antemano")), (True, 0))
    # Se anota en vez de fallar: palabras_corregidas() ataja los errores y seguiría como si nada.
    _contar, _contadas = g["descripciones_por_palabra"], []
    g["descripciones_por_palabra"] = lambda version: _contadas.append(version) or _contar(version)
    try:
        ns["palabras_corregidas"]("bomba de agau")
    finally:
        g["descripciones_por_palabra"] = _contar
    esperar("y la búsqueda no lo arma de nuevo", _contadas, [])
    esperar("sin errores al armarlo", [e for e in g["_ULTIMOS_ERRORES"]
                                       if "antemano" in str(e)], [])
    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('PRUEBA', 'PROVEEDOR')")
    _marca_prueba = c.lastrowid
    # Y lo de «🚙 Repuestos por vehículo» de la marca que aparece elegida al entrar (la
    # primera): sus productos y sus modelos. Con un producto de FIAT, el que vuelve a armarlo
    # pide los de FIAT. Después se borra: las búsquedas de abajo cuentan resultados.
    _de_fiat = c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
                         "VALUES ('BAF1', 'BAF1', 'BOMBA DE AGUA FIAT PALIO 1.6', ?)",
                         (_marca_prueba,)).lastrowid
    conn.commit()
    _modelos_de, _pedidos = g["modelos_de_marca"], []
    g["modelos_de_marca"] = lambda m, v, *a: _pedidos.append(m) or _modelos_de(m, v, *a)
    try:
        g["del_proceso"]("lo_de_antemano_lanzado", threading.Event).clear()
        ns["dejar_listo_de_antemano"]()
        for _h in [h for h in threading.enumerate() if h.name == "de_antemano"]:
            _h.join(60)
    finally:
        g["modelos_de_marca"] = _modelos_de
    esperar("y los modelos de la marca que aparece elegida en 🚙 Repuestos por vehículo",
            _pedidos, ["FIAT"])
    c.execute("DELETE FROM productos WHERE id = ?", (_de_fiat,))
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
              "VALUES ('F100', 'F100', 'FILTRO DE ACEITE', ?)", (_marca_prueba,))
    conn.commit()

    def buscar(texto):
        at.text_input(key="busqueda_input").set_value(texto)
        [b for b in at.button if "Buscar equivalencias" in b.label][0].click().run()

    # 1. Una búsqueda que anda: queda medida.
    buscar("F100")
    resumen = g["resumen_de_las_busquedas"]()
    esperar("medida", (resumen.get("cuantas"), resumen.get("errores")), (1, 0))
    esperar("con sus resultados", resumen["todas"][-1]["resultados"] >= 1, True)

    # 2. Una que falla: no se cae la pantalla, dice «no se pudo consultar» con el código, y no
    # se anota como algo que falta.
    original = g["buscar_con_variantes_del_cero"]

    def ocupada(*a, **k):
        raise sqlite3.OperationalError("database is locked")
    g["buscar_con_variantes_del_cero"] = ocupada
    try:
        sin_resultado_antes = c.execute("SELECT COUNT(*) FROM historial_busquedas WHERE sin_resultado = 1"
                                        ).fetchone()[0]
        buscar("X999")
    finally:
        g["buscar_con_variantes_del_cero"] = original
    esperar("sin error técnico en pantalla", [e.value for e in at.exception], [])
    mensaje = [e.value for e in at.error if "no se pudo consultar" in e.value]
    esperar("dice que no se pudo consultar", len(mensaje), 1)
    codigo = g["resumen_de_las_busquedas"]()["todas"][-1]["codigo"]
    esperar("con el código para encontrarla", bool(mensaje) and codigo in mensaje[0], True)
    esperar("no se anotó como algo que falta",
            c.execute("SELECT COUNT(*) FROM historial_busquedas WHERE sin_resultado = 1").fetchone()[0],
            sin_resultado_antes)
    esperar("quedó como error", g["resumen_de_las_busquedas"]()["errores"], 1)

    # 2c. Un error de tipeo que no puede encontrar nada se corrige, y se dice (ver
    # palabras_corregidas()). Lo bien escrito, una abreviatura que está adentro de otra palabra
    # («FILT») o el nombre de una lista no se tocan.
    _marca = c.execute("SELECT id FROM marcas WHERE nombre = 'PRUEBA'").fetchone()[0]
    c.executemany("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
                  "VALUES (?, ?, ?, ?)",
                  [(f"BA{i}", f"BA{i}", f"BOMBA DE AGUA GOL 1.6 V{i}", _marca) for i in range(3)]
                  + [("BL1", "BL1", "BOMBA LAVA GOL", _marca)])
    conn.commit()
    _pc = ns["palabras_corregidas"]
    esperar("la palabra a un tecleo se corrige; lo que existe, no",
            [_pc(x) for x in ("bomba de agau gol", "bomba de agua gol", "filt aceite", "prueba",
                              "zzzzzz")],
            [{"AGAU": "AGUA"}, {}, {}, {}, {}])
    esperar("se cambia solo esa palabra",
            ns["texto_con_las_correcciones"]("Bomba de agau, Gol", {"AGAU": "AGUA"}),
            "Bomba de AGUA Gol")
    at.session_state["modo_busqueda"] = "Código"
    at.run()
    buscar("bomba de agau gol")
    esperar("en la pantalla: dice qué cambió", any("«agau» no está en ningún producto: se buscó "
                                                   "«agua»" in x.value for x in at.caption), True)
    esperar("y trae la bomba de agua primero",
            str(at.dataframe[0].value.iloc[0]["Descripcion"]).startswith("BOMBA DE AGUA GOL"), True)
    at.session_state["modo_busqueda"] = "Código"
    at.run()

    # 2d. En la tabla, «s/d» donde no se sabe el stock, y no el «None» de Streamlit; si todos
    # tienen dato, quedan números. Y el mensaje de «📲 Consultar por WhatsApp».
    _legible = ns["con_stock_legible"]
    esperar("stock legible", ([f["Stock"] for f in _legible([{"Stock": 0}, {"Stock": None},
                                                             {"Stock": 1500}])],
                              _legible([{"Stock": 3}])), (["0", "s/d", "1.500"], [{"Stock": 3}]))
    esperar("el mensaje para consultar",
            (ns["texto_para_consultar"]("02400", [{"Marca": "FISPA", "Codigo": "LEICJ010"}]),
             ns["texto_para_consultar"]("XYZ")),
            ("Hola! Busqué *02400* en la página y vi: FISPA LEICJ010. ¿Tienen alguno? ¿A cuánto?",
             "Hola! ¿Tienen *XYZ*? En la página no me apareció."))

    # 2e. Lo que se dibuja debajo de los resultados se recuerda mientras no cambien los
    # vínculos (ver recordado_mientras_no_cambie()): no se recalcula en cada toque, sí cuando
    # entra un producto o se agrega un vínculo, y de cada cosa se guardan las últimas 24.
    _veces = []
    _recordado = ns["recordado_mientras_no_cambie"]
    _testigo = ns["testigo_de_los_vinculos"]

    def _calcular():
        _veces.append(1)
        return [{"n": len(_veces)}]
    _antes = _testigo()
    _uno = _recordado("_prueba_memo", ("F100", _antes), _calcular)
    _dos = _recordado("_prueba_memo", ("F100", _antes), _calcular)
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
              "VALUES ('F200', 'F200', 'FILTRO DE AIRE', (SELECT id FROM marcas LIMIT 1))")
    c.execute("INSERT INTO equivalencias (producto_a_id, producto_b_id) VALUES "
              "((SELECT id FROM productos WHERE codigo_clean = 'F100'), ?)", (c.lastrowid,))
    conn.commit()
    _despues = _testigo()
    _tres = _recordado("_prueba_memo", ("F100", _despues), _calcular)
    esperar("recordado: una vez por clave, otra vez si cambian los vínculos",
            (_uno, _dos, _tres, len(_veces), _antes != _despues),
            ([{"n": 1}], [{"n": 1}], [{"n": 2}], 2, True))
    for i in range(30):
        _recordado("_prueba_memo", ("otro", i), lambda: 0)
    esperar("de cada cosa, las últimas 24", len(ns["st"].session_state["_prueba_memo"]), 24)

    # 2f. El número de la caja encuentra el código que la lista guardó con la marca pegada
    # («LEICJ057» → «LEICJ057LUCAS»), y lo dice. Si el número pelado es otro producto, se
    # muestra ese y sin aviso: pueden ser piezas distintas (ver buscar_con_variantes_del_cero()).
    _buscar = ns["buscar_con_variantes_del_cero"]

    def _el_buscado(r):
        return [f["Codigo"] for f in r if f.get("Cadena") == "— el buscado"]
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) VALUES "
              "('LEICJ057LUCAS', 'LEICJ057LUCAS', 'INYECTOR', (SELECT id FROM marcas LIMIT 1))")
    conn.commit()
    _r, _aviso = _buscar("LEICJ057")
    esperar("con la marca pegada: lo encuentra y lo dice",
            (_el_buscado(_r), "marca LUCAS pegada" in (_aviso or "")), (["LEICJ057LUCAS"], True))
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) VALUES "
              "('LEICJ057', 'LEICJ057', 'OTRA PIEZA', (SELECT id FROM marcas LIMIT 1))")
    conn.commit()
    _r, _aviso = _buscar("LEICJ057")
    esperar("si el número pelado existe, ese y sin aviso", (_el_buscado(_r), _aviso),
            (["LEICJ057"], None))
    # Y la marca escrita con el código, adelante o atrás: «NGK BKR6E», «6205 SKF», «LUCAS
    # LEICJ010» (con la marca que la lista pega atrás) y el nombre de una lista de dos letras.
    # Si lo que queda no es un código, nada: «SKF» puede ser el principio de un código real.
    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('JL', 'PROVEEDOR')")
    for _cod in ("BKR6E", "6205", "LEICJ010LUCAS", "MTA0030"):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
                  "VALUES (?, ?, 'PIEZA', (SELECT id FROM marcas WHERE nombre = "
                  "CASE WHEN ? = 'MTA0030' THEN 'JL' ELSE 'PRUEBA' END))", (_cod, _cod, _cod))
    conn.commit()
    esperar("la marca escrita con el código",
            [(_el_buscado(_buscar(ns["sanitizar"](t))[0]),
              "es la marca" in (_buscar(ns["sanitizar"](t))[1] or ""))
             for t in ("NGK BKR6E", "6205 SKF", "lucas LEICJ010", "JL MTA 0030", "SKF 9999")],
            [(["BKR6E"], True), (["6205"], True), (["LEICJ010LUCAS"], True),
             (["MTA0030"], True), ([], False)])

    # 2g. Lo que espera aprobación del código buscado se decide en el Buscador (ver «LO QUE
    # ESPERA APROBACIÓN, DESDE EL BUSCADOR»): el título lo cuenta, lo dudoso va de a uno con
    # «✅ Es la misma» —y la tabla lo trae enseguida—, lo casi seguro mal se descarta junto, y
    # el invitado no lo ve.
    _f100 = c.execute("SELECT id FROM productos WHERE codigo_clean = 'F100'").fetchone()[0]
    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('OTRA', 'PROVEEDOR')")
    _otra = c.lastrowid
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
              "VALUES ('OF1', 'OF1', 'FILTRO DE ACEITE', ?)", (_otra,))
    _of1 = c.lastrowid
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
              "VALUES ('OB7', 'OB7', 'BUJIA DE ENCENDIDO', ?)", (_otra,))
    _ob7 = c.lastrowid
    conn.commit()
    g["guardar_equivalencias_pendientes"]([(_f100, _of1), (_f100, _ob7)], "PRUEBA", "PRUEBA · 1")
    _esperan = g["lo_que_espera_aprobacion"]([_f100])
    esperar("lo que espera, con lo que dice el análisis",
            [(f["Codigo"], f["nivel"][:1], f["yo"]) for f in _esperan],
            [("OF1", "🟠", _f100), ("OB7", "🔴", _f100)])
    buscar("F100")
    esperar("el título lo cuenta",
            any("🔒 2 esperando aprobación" in x.label for x in at.expander), True)
    esperar("y dice cuántas de cada clase",
            [x.label.split(" — ", 1)[1].split(" · 🔒")[0] for x in at.expander
             if x.label.startswith("🔎 F100")], ["1 equivalencia (1 a revisar)"])
    at.session_state["esp_ver_F100"] = True
    at.run()
    [b for b in at.button if b.key == f"esp_si_{_f100}_{_of1}_F100"][0].click().run()
    esperar("aprobada desde el Buscador, y la tabla la trae",
            (c.execute("SELECT COUNT(*) FROM equivalencias WHERE producto_a_id = ? AND "
                       "producto_b_id = ?", (_f100, _of1)).fetchone()[0],
             g["cuantos_esperan_aprobacion"]([_f100]),
             [e.value for e in at.exception],
             "OF1" in [f["Codigo"] for f in at.session_state["ultima_busqueda_codigo"][0]["res"]]),
            (1, 1, [], True))
    [b for b in at.button if b.key == "esp_rojas_F100"][0].click().run()
    esperar("lo casi seguro mal, descartado y anotado",
            (g["cuantos_esperan_aprobacion"]([_f100]),
             c.execute("SELECT decision FROM equivalencias_revisadas WHERE producto_a_id = ? AND "
                       "producto_b_id = ?", (_f100, _ob7)).fetchone()[0]),
            (0, "rechazada"))
    esperar("la búsqueda no se anotó dos veces",
            c.execute("SELECT COUNT(*) FROM historial_busquedas WHERE termino = 'F100'"
                      ).fetchone()[0], 2)
    g["guardar_equivalencias_pendientes"]([(_f100, _ob7 + 0)], "PRUEBA", "PRUEBA · 2")
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
              "VALUES ('OF2', 'OF2', 'FILTRO DE ACEITE', ?)", (_otra,))
    g["guardar_equivalencias_pendientes"]([(_f100, c.lastrowid)], "PRUEBA", "PRUEBA · 2")
    at.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
    buscar("F100")
    esperar("el invitado no lo ve",
            [x.label for x in at.expander if "esperando" in x.label]
            + [b.key for b in at.button if str(b.key).startswith("esp_")], [])

    # 3. Los números: mediana y P95 de lo anotado.
    g["del_proceso"]("mediciones_de_busqueda", list).clear()
    for ms in range(1, 101):
        g["anotar_busqueda"]("código", "x", ms / 1000, 0 if ms % 4 == 0 else 3)
    r = g["resumen_de_las_busquedas"]()
    esperar("mediana", round(r["mediana_ms"]), 51)
    esperar("P95", round(r["p95_ms"]), 95)
    esperar("sin resultados", r["sin_resultados"], 25)
    esperar("la más lenta primero", round(r["lentas"][0]["ms"]), 100)

    # 3. 🕯️ ¿Qué bujía le va?: una Bosch que no está en las listas dice cómo es y trae las que
    # calzan, la del grado más cercano primero (la FR 7 DC es la NGK 6: la BKR5E está a uno, la BKR8E a dos); y lo mismo desde el
    # desplegable, por el código o por cómo es. Ver bujias_que_calzan_con().
    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('TARANTO', 'PROVEEDOR')")
    _mt = c.lastrowid
    for cod_b in ("BKR8E", "BKR5E", "BPR5E"):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, stock) "
                  "VALUES (?, ?, 'BUJIA NGK', ?, 2)", (cod_b, cod_b, _mt))
    conn.commit()
    buscar("FR 7 DC")
    esperar("buscando una bujía que no está, dice cuál es",
            any("es una **Bosch FR7DC**" in str(x.value) for x in at.info), True)
    esperar("y las que calzan, la del grado más cercano primero",
            [b.label for b in at.button if (b.key or "").startswith("bujia_nr_")],
            ["🔎 BKR5E", "🔎 BKR8E"])
    # El simulador vuelve a cerrar el desplegable perezoso en cada toque: se abre antes de cada uno.
    at.session_state["exp_que_bujia_le_va"] = True
    at.run()
    at.session_state["exp_que_bujia_le_va"] = True
    at.text_input(key="bujia_codigo_libre").set_value("bpr 6 e").run()
    esperar("desde el desplegable, por el código",
            [b.label for b in at.button if (b.key or "").startswith("bujia_libre_")], ["🔎 BPR5E"])
    at.session_state["exp_que_bujia_le_va"] = True
    at.text_input(key="bujia_codigo_libre").set_value("").run()
    _opcion = [o for o in at.selectbox(key="bujia_grupo").options if "hexágono 16" in o][0]
    at.session_state["exp_que_bujia_le_va"] = True
    at.selectbox(key="bujia_grupo").set_value(_opcion).run()
    esperar("y por cómo es",
            sorted(b.label for b in at.button if (b.key or "").startswith("bujia_grupo_l_")),
            ["🔎 BKR5E", "🔎 BKR8E"])
    esperar("la tabla de cruce, por cómo es y grado, con los códigos de cada lista",
            [(f["Cómo es"][:22], f["Grado (NGK)"], f.get("TARANTO")) for f in g["tabla_de_cruce_de_bujias"]()],
            [("M14, largo 19 mm, hexá", 5, "BKR5E"), ("M14, largo 19 mm, hexá", 8, "BKR8E"),
             ("M14, largo 19 mm, hexá", 5, "BPR5E")])
    esperar("sin errores", [e.value for e in at.exception], [])
    return fallas


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_buscador_")
    os.chdir(carpeta)
    sys.path.insert(0, RAIZ)
    try:
        fallas = probar()
        for f in fallas:
            print("   ✗", f)
        print("✅ buscador: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(RAIZ)
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

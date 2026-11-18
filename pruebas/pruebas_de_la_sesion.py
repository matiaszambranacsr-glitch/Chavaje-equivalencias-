"""Pruebas de la sesión con la app real (AppTest): salir no deja nada, y los permisos siguen a
la cuenta.

Uso:
    python3 pruebas/pruebas_de_la_sesion.py

Las dos las propuso una revisión con ChatGPT:
  · «login A → seleccionar cosas → logout → login B → comprobar que no aparece nada de A»;
  · «admin cambia el rol → misma sesión»: el nivel se guardaba al entrar y no se volvía a mirar.
Ver cerrar_sesion() y nivel_vigente_de_la_sesion() en logica/base.py.

Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from urllib.parse import quote

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _entrar(at, usuario, clave):
    at.text_input(key="login_inicial_nombre").set_value(usuario)
    at.text_input(key="login_inicial_clave").set_value(clave)
    [b for b in at.button if "Ingresar con contraseña" in b.label][0].click().run()


def probar():
    from streamlit.testing.v1 import AppTest
    fallas = []

    def esperar(nombre, real, esperado):
        if real != esperado:
            fallas.append(f"{nombre}: dio {real!r}, se esperaba {esperado!r}")

    at = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
    at.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
    at.run()
    ns = sys.modules["logica"].todo_lo_de_la_logica()
    ns["crear_usuario"]("ana", "clave-ana-1", "operador")

    # 1. Ana entra y deja cosas de ella en la sesión.
    _entrar(at, "ana", "clave-ana-1")
    esperar("Ana entró como operador", at.session_state["nivel_usuario"], "operador")
    at.session_state["busqueda_input"] = "W712/94"
    at.session_state["carrito"] = {1: {"codigo": "X", "marca": "Y", "descripcion": "",
                                       "precio": 10, "cantidad": 1}}
    at.session_state["lista_whatsapp"] = [{"codigo_buscado": "X", "resultados": []}]
    at.session_state["cuenta_elegida"] = {"id": 1, "nombre": "Taller", "desde": 0}
    at.session_state["sel_marca_vehiculo"] = "FORD (3 productos)"
    at.run()
    [b for b in at.button if b.label == "Salir"][0].click().run()
    quedaron = {k for k in at.session_state
                if k in ("carrito", "cuenta_elegida", "sel_marca_vehiculo",
                         "nivel_usuario", "admin_nombre")}
    esperar("después de Salir no queda nada de Ana", quedaron, set())
    # La caja de búsqueda no se borra: se VACÍA, que es lo que hace que el navegador la vacíe
    # (ver cerrar_sesion()).
    # Tiene que estar PUESTA en vacío: ausente, el navegador sigue mostrando lo de antes.
    # OJO: AppTest no tiene la memoria del navegador y vuelve a crear el campo vacío, así que
    # esto no alcanza para probarlo; lo que lo prueba es un navegador de verdad (hecho), y lo
    # que lo cuida es el control 6c de auditar.py.
    esperar("la caja de búsqueda puesta en vacío", at.session_state["busqueda_input"]
            if "busqueda_input" in at.session_state else "(ausente)", "")
    esperar("la lista de WhatsApp vacía", at.session_state["lista_whatsapp"], [])

    # 2. Entra el dueño: no ve nada de Ana.
    _entrar(at, "duenio", "clave-duenio-1")
    esperar("el dueño entró como admin", (at.session_state["nivel_usuario"],
                                          at.session_state["admin_nombre"]), ("admin", "duenio"))
    esperar("el dueño no ve el presupuesto de Ana", "carrito" in at.session_state
            and bool(at.session_state["carrito"]), False)

    # 2b. Ir a otra pantalla y volver no borra lo que se estaba haciendo (lo señaló una
    # revisión con Gemini): la caja de búsqueda volvía vacía, con los resultados de antes abajo.
    # Ver recordar_lo_elegido_al_cambiar_de_pantalla().
    at.session_state["pagina_actual"] = "🔍 Buscador"
    at.run()
    at.text_input(key="busqueda_input").set_value("W712/94")
    [b for b in at.button if "Buscar equivalencias" in b.label][0].click().run()
    at.session_state["pagina_actual"] = "📊 Estadísticas"
    at.run()
    at.radio(key="sub_stats").set_value("📌 Para pedir").run()
    for pagina in ("🗂️ Administrar", "🛠️ Modo Mecánico", "🔍 Buscador"):
        at.session_state["pagina_actual"] = pagina
        at.run()
    esperar("al volver al buscador, lo escrito sigue ahí",
            at.text_input(key="busqueda_input").value, "W712/94")
    at.session_state["pagina_actual"] = "📊 Estadísticas"
    at.run()
    esperar("y en Estadísticas, la solapa que estaba", at.radio(key="sub_stats").value,
            "📌 Para pedir")
    esperar("sin errores al ir y venir", [e.value for e in at.exception], [])

    # 2d. La ayuda de cada pantalla: UN «ℹ️ Cómo funciona» plegado arriba, con para qué sirve
    # la sección, la solapa y la ayuda de la pantalla adentro, y nada de eso a la vista. La
    # ayuda de una parte de más abajo se queda en su parte. Lo pidió el dueño: menos ruido, todo
    # plegado. Ver «LA AYUDA DE CADA PANTALLA» en logica/interfaz.py.
    def _ayudas():
        return [e for e in at.expander if e.label == ns["TITULO_DE_LA_AYUDA"]]

    _solapa = ns["SUB_DEPOSITO"][0]
    at.session_state["pagina_actual"] = "📦 Depósito"
    at.session_state["sub_deposito"] = _solapa
    at.run()
    _arriba = _ayudas()[0].markdown[0].value if _ayudas() and _ayudas()[0].markdown else ""
    esperar("depósito: una sola ayuda", len(_ayudas()), 1)
    esperar("con la sección, la solapa y la pantalla adentro",
            [ns["PARA_QUE_SIRVE"]["📦 Depósito"] in _arriba,
             ns["PARA_QUE_SIRVE_LA_SOLAPA"][_solapa] in _arriba,
             "Acá llega lo que el mostrador pide" in _arriba], [True, True, True])
    esperar("y en ningún otro lado", sum(ns["PARA_QUE_SIRVE_LA_SOLAPA"][_solapa] in x.value
                                         for x in list(at.caption) + list(at.markdown)), 1)
    esperar("plegada", _ayudas()[0].proto.expanded if _ayudas() else None, False)
    at.session_state["pagina_actual"] = "📊 Estadísticas"
    at.run()
    at.radio(key="sub_stats").set_value("📌 Para pedir").run()
    _de_una_parte = "Hace falta haber importado precios de una misma marca"
    esperar("la de una parte no sube arriba", _de_una_parte in _ayudas()[0].markdown[0].value, False)
    esperar("se queda en su parte", any(_de_una_parte in a.markdown[0].value
                                        for a in _ayudas()[1:] if a.markdown), True)
    esperar("sin errores con las ayudas", [e.value for e in at.exception], [])

    # 2c. Una importación que se corta a la mitad no deja nada: corre entera adentro de una
    # transacción (ver pantallas/cargar_excel.py). No tenía prueba. Se corta en la segunda fila.
    with open("corte.csv", "w", encoding="utf-8") as f:
        f.write("Codigo;Descripcion;Precio;Stock\nCORTE1;FILTRO UNO;100;1\n"
                "CORTE2;FILTRO DOS;200;2\nCORTE3;FILTRO TRES;300;3\n")
    _g = ns["poner_precio_y_stock_de_la_lista"].__globals__
    _original = _g["poner_precio_y_stock_de_la_lista"]
    _llamadas = []

    def _se_corta(*args, **kwargs):
        _llamadas.append(1)
        if len(_llamadas) == 2:
            raise RuntimeError("corte de prueba a mitad de la lista")
        return _original(*args, **kwargs)

    def _lo_que_hay():
        c = ns["c"]
        return tuple(c.execute(q).fetchone()[0] for q in (
            "SELECT COUNT(*) FROM productos WHERE codigo_clean LIKE 'CORTE%'",
            "SELECT COUNT(*) FROM importaciones", "SELECT COUNT(*) FROM historial_precios"))
    _antes = _lo_que_hay()
    _g["poner_precio_y_stock_de_la_lista"] = _se_corta
    at.session_state["pagina_actual"] = "📁 Cargar Excel"
    at.run()
    _ruta = [x for x in at.radio if "Subir archivo" in x.options][0]
    _ruta.set_value([o for o in _ruta.options if o != "Subir archivo"][0]).run()
    [t for t in at.text_input if "Ruta completa" in t.label][0].set_value(
        os.path.abspath("corte.csv")).run()
    at.text_input(key="nombre_prov_carga").set_value("PRUEBACORTE").run()
    [b for b in at.button if "Procesar e importar" in b.label][0].click().run()
    esperar("cortada a la mitad, no queda nada de la lista", (len(_llamadas), _lo_que_hay()),
            (2, _antes))
    _g["poner_precio_y_stock_de_la_lista"] = _original
    [b for b in at.button if "Procesar e importar" in b.label][0].click().run()
    esperar("y entera, entra entera", _lo_que_hay(), (3, _antes[1] + 1, _antes[2] + 3))
    esperar("sin errores al importar", [e.value for e in at.exception], [])

    # 2d. Dos productos de la lista que sin los signos se escriben igual (la tuerca CAMBA111.4 de
    # 5/32 y la CAMBA11.14 de 9/16, de IMPERIAL): cada uno con SU precio, el segundo aparte, con
    # su código limpio propio. Antes había uno solo, con la descripción del primero y el precio
    # del segundo. El mismo código escrito igual dos veces (la unidad y la caja) sigue como
    # antes: se avisa como repetido. Ver es_otro_producto_con_el_mismo_codigo() y
    # codigo_de_la_variante().
    def _importar(nombre, renglones):
        with open(nombre, "w", encoding="utf-8") as f:
            f.write("Codigo;Descripcion;Precio;Stock\n" + "".join(r + "\n" for r in renglones))
        [t for t in at.text_input if "Ruta completa" in t.label][0].set_value(
            os.path.abspath(nombre)).run()
        at.text_input(key="nombre_prov_carga").set_value("PRUEBACHOQUE").run()
        [b for b in at.button if "Procesar e importar" in b.label][0].click().run()

    def _precio(limpio):
        return [tuple(r) for r in ns["c"].execute(
            "SELECT descripcion, precio FROM productos WHERE codigo_clean = ?",
            (limpio,)).fetchall()]
    # Precios que el freno de saltos deja pasar (menos de 3 veces): con la junta de 12", 75
    # veces más cara, el freno la paraba, alguien tocaba «Aplicar igual» viendo la descripción
    # de la de 12" y la de ½" quedaba a ese precio.
    _tuercas = ["CAMBA111.4;TUERCA ZINC 5/32;987;1", "CAMBA11.14;TUERCA NAT 9/16;1873;1"]
    _importar("choque.csv", _tuercas + ["DOBLE-1;JUNTA UNIDAD;100;1", "DOBLE-1;JUNTA CAJA;900;1"])
    esperar("choque: la tuerca de 5/32 con su precio, y una sola", _precio("CAMBA1114"),
            [("TUERCA ZINC 5/32", 987.0)])
    esperar("y la de 9/16 entró aparte, con su precio", _precio(ns["codigo_de_la_variante"]("CAMBA11.14")),
            [("TUERCA NAT 9/16", 1873.0)])
    esperar("y lo dice", any("otro producto que" in w.value and "CAMBA11.14" in w.value
                             and "entró aparte" in w.value for w in at.warning), True)
    esperar("ninguna fila omitida",
            [w.value for w in at.warning if w.value.startswith("Se omitieron")], [])
    esperar("escrito igual dos veces: se avisa como repetido, como antes",
            any("más de una vez en la lista" in w.value and "DOBLE-1" in w.value
                for w in at.warning), True)
    # Volver a importar la lista corrige el precio que había quedado mal.
    ns["c"].execute("UPDATE productos SET precio = 1873 WHERE codigo_clean = 'CAMBA1114'")
    ns["conn"].commit()
    _importar("choque2.csv", _tuercas + ["OTRA-1;JUNTA;50;1"])
    esperar("reimportada: la de 5/32 vuelve a su precio", _precio("CAMBA1114"),
            [("TUERCA ZINC 5/32", 987.0)])
    esperar("y la de 9/16 sigue siendo una sola, aparte",
            ns["c"].execute("SELECT COUNT(*) FROM productos WHERE codigo_raw = 'CAMBA11.14'")
            .fetchone()[0], 1)
    # El frenado que vuelve a un precio que ya tuvo (ver precio_que_ya_tuvo()): la de 5/32 valía
    # 987, un choque le pisó 48.209, y la lista trae 987. El freno la para (49 veces), pero la
    # marca, y se aplica con un botón sin tocar los otros frenados.
    _pid_v = ns["c"].execute("SELECT id FROM productos WHERE codigo_clean = 'CAMBA1114'").fetchone()[0]
    ns["c"].execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio) "
                    "SELECT 'OTRA-3', 'OTRA3', 'JUNTA', marca_id, 100 FROM productos WHERE id = ?",
                    (_pid_v,))
    ns["c"].execute("UPDATE productos SET precio = 48209 WHERE id = ?", (_pid_v,))
    ns["c"].execute("INSERT INTO historial_precios (producto_id, precio) VALUES (?, 48209)", (_pid_v,))
    ns["conn"].commit()
    _importar("vuelve.csv", _tuercas + ["OTRA-3;JUNTA;5000;1"])
    _fr_v = at.session_state["precios_frenados_de_la_carga"]["filas"]
    esperar("dos frenados, y uno vuelve a un precio que ya tuvo",
            sorted((f["Código"], f["_vuelve"], f["Ya tuvo"][:7]) for f in _fr_v),
            [("CAMBA111.4", True, "$ 987, "), ("OTRA-3", False, "")])
    [b for b in at.button if b.key == "aplicar_frenados_que_vuelven"][0].click().run()
    esperar("aplicado el que vuelve; el otro sigue frenado y con su precio",
            (_precio("CAMBA1114"), [f["Código"] for f in
                                    at.session_state["precios_frenados_de_la_carga"]["filas"]],
             ns["c"].execute("SELECT precio FROM productos WHERE codigo_clean = 'OTRA3'").fetchone()[0]),
            ([("TUERCA ZINC 5/32", 987.0)], ["OTRA-3"], 100.0))
    at.session_state["precios_frenados_de_la_carga"] = None
    # Antes de importar, qué hace la lista con los precios (ver
    # lo_que_hace_la_lista_con_los_precios()): sin tocar nada.
    with open("previa.csv", "w", encoding="utf-8") as _f:
        _f.write("Codigo;Descripcion;Precio;Stock\nCAMBA111.4;TUERCA ZINC 5/32;1100;1\n"
                 "CAMBA11.14;TUERCA NAT 9/16;1873;1\nOTRA-3;JUNTA;5000;1\nNUEVO-9;ARANDELA;10;1\n")
    [t for t in at.text_input if "Ruta completa" in t.label][0].set_value(
        os.path.abspath("previa.csv")).run()
    at.text_input(key="nombre_prov_carga").set_value("PRUEBACHOQUE").run()
    at.session_state["exp_lo_que_hace_la_lista"] = True
    at.run()
    _vp = at.session_state["_lo_que_hace_la_lista"][1]
    esperar("la vista previa: uno sube, uno igual, uno frenado, uno nuevo",
            ({k: _vp[k] for k in ("comparados", "suben", "iguales", "frenaria", "nuevos")},
             [x["Cambio"] for x in _vp["subas"]]),
            ({"comparados": 2, "suben": 1, "iguales": 1, "frenaria": 1, "nuevos": 1}, ["+11%"]))
    esperar("y lo dice", any("**1 suben**" in m.value for m in at.markdown), True)
    esperar("sin tocar nada", _precio("CAMBA1114"), [("TUERCA ZINC 5/32", 987.0)])
    at.session_state["exp_lo_que_hace_la_lista"] = False
    at.run()
    # Y en el buscador: escrito con sus signos trae la de 9/16; sin ellos, la de 5/32, y avisa
    # que hay otra que se escribe igual.
    at.session_state["pagina_actual"] = "🔍 Buscador"
    at.run()

    def _buscar(codigo):
        at.text_input(key="busqueda_input").set_value(codigo)
        [b for b in at.button if "Buscar equivalencias" in b.label][0].click().run()
        _buscado = [f for x in at.session_state["ultima_busqueda_codigo"] for f in x["res"] or []
                    if f.get("Cadena") == "— el buscado"]
        return ([f["Codigo"] for f in _buscado],
                [i.value for i in at.info if "Sin los signos se escribe igual" in i.value])
    _cod, _aviso = _buscar("CAMBA11.14")
    esperar("con los signos, la de 9/16, y avisa de la de 5/32",
            (_cod, ["CAMBA111.4" in x for x in _aviso]), (["CAMBA11.14"], [True]))
    _cod, _aviso = _buscar("CAMBA1114")
    esperar("sin los signos, la de 5/32, y avisa de la de 9/16",
            (_cod, ["CAMBA11.14" in x for x in _aviso]), (["CAMBA111.4"], [True]))
    # Y en la venta, igual: antes traía la de 5/32 escribiendo la de 9/16.
    at.session_state["pagina_actual"] = ns["PAGINAS"][9]
    at.run()
    at.text_input(key="venta_buscar").set_value("CAMBA11.14")
    [b for b in at.button if "Buscar" in b.label and b.key != "refrescar_salud"][0].click().run()
    _vta = at.session_state["venta_resultados"][0] if "venta_resultados" in at.session_state else []
    esperar("en la venta, con los signos, la de 9/16 primero, y avisa de la otra",
            ([f.get("Codigo") for f in _vta][:1],
             "CAMBA111.4" in (at.session_state["venta_iguales"]
                              if "venta_iguales" in at.session_state else "")),
            (["CAMBA11.14"], True))
    # Los códigos de fábrica no se venden (ver «LOS CÓDIGOS DE FÁBRICA NO SE VENDEN» en
    # pantallas/ventas.py): van en una línea aparte, sin renglón ni ➕ a $0.
    _oem_v = ns["get_or_create_marca"]("OEM / FABRICA", "OEM")
    ns["c"].execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
                    "VALUES ('VW-0269', 'VW0269', 'TUERCA', ?)", (_oem_v,))
    _vw_v = ns["c"].lastrowid
    _cam_v = ns["c"].execute("SELECT id FROM productos WHERE codigo_clean = 'CAMBA1114'").fetchone()[0]
    ns["c"].execute("INSERT INTO equivalencias (producto_a_id, producto_b_id) VALUES (?, ?)",
                    (min(_vw_v, _cam_v), max(_vw_v, _cam_v)))
    ns["conn"].commit()

    def _vender_buscando(texto):
        at.text_input(key="venta_buscar").set_value(texto)
        [b for b in at.button if "Buscar" in b.label and b.key != "refrescar_salud"][0].click().run()
        return ([f["Codigo"] for f in at.session_state["venta_resultados"][0]],
                at.session_state["venta_de_fabrica"],
                [x.value for x in at.caption if x.value.startswith("🏭 Código de fábrica")])
    esperar("en la venta, el código de fábrica no es un renglón: va aparte",
            _vender_buscando("CAMBA111.4"),
            (["CAMBA111.4"], ["VW-0269"],
             ["🏭 Código de fábrica: VW-0269. No se venden: son la referencia que une a las "
              "marcas."]))
    esperar("y buscando el de fábrica, salen las marcas que lo tienen",
            _vender_buscando("VW-0269")[:2], (["CAMBA111.4"], ["VW-0269"]))
    # La lista en otra escala, avisada en la venta, que es donde se cobra (ver
    # escala_de_precios_por_marca()). Antes lo avisaban el buscador y WhatsApp, la venta no.
    _gv = ns["poner_precio_y_stock_de_la_lista"].__globals__
    _fuera_real, _escala_real = (_gv["marcas_con_precios_fuera_de_escala"],
                                 _gv["escala_de_precios_por_marca"])
    _gv["marcas_con_precios_fuera_de_escala"] = lambda: {"PRUEBACHOQUE"}
    _gv["escala_de_precios_por_marca"] = lambda *a, **k: {"PRUEBACHOQUE": {"factor": 1 / 15}}
    try:
        _id_vta = _vta[0]["ID"]
        at.session_state["venta_items"] = [ns["item_de_venta"](_id_vta, 1, "CAMBA11.14")]
        at.run()
        esperar("en la venta, la marca en otra escala se avisa en el renglón",
                [x.value for x in at.caption if "está en otra escala" in x.value],
                ["⚠️ La lista de PRUEBACHOQUE está en otra escala: cuesta 15 veces menos que lo "
                 "mismo en otras marcas. Revisá el precio antes de cobrar."])
        # Y en el presupuesto del buscador, de donde sale la venta o el WhatsApp.
        at.session_state["carrito"] = {_id_vta: {"codigo": "CAMBA11.14", "marca": "PRUEBACHOQUE",
                                                 "descripcion": "TUERCA", "precio": 1873,
                                                 "cantidad": 1}}
        at.session_state["pagina_actual"] = "🔍 Buscador"
        at.run()
        esperar("en el presupuesto también",
                any("PRUEBACHOQUE" in w.value and "otra escala" in w.value for w in at.warning),
                True)
        at.session_state["carrito"] = {}
    finally:
        _gv["marcas_con_precios_fuera_de_escala"] = _fuera_real
        _gv["escala_de_precios_por_marca"] = _escala_real
    # Sin precio (el 999.999 que la lista usa para decir que no lo tiene entra vacío: ver
    # precios_de_relleno()): la venta lo dice en el renglón, en vez de cobrarlo en 0 callada.
    ns["c"].execute("UPDATE productos SET precio = NULL WHERE id = ?", (_id_vta,))
    ns["conn"].commit()
    at.session_state["venta_items"] = [ns["item_de_venta"](_id_vta, 1, "CAMBA11.14")]
    at.session_state["pagina_actual"] = ns["PAGINAS"][9]
    at.run()
    esperar("en la venta, el que no tiene precio se avisa en el renglón",
            [x.value for x in at.caption if "Sin precio" in x.value],
            ["⚠️ Sin precio: la lista no lo trae. Ponelo antes de cobrar."])
    at.session_state["venta_items"] = []
    at.session_state["pagina_actual"] = "📁 Cargar Excel"
    at.run()
    esperar("sin errores con los choques", [e.value for e in at.exception], [])
    # En la app de internet la ruta se leería en el servidor, no en el teléfono: no se ofrece.
    _en_la_nube = _g["corre_en_streamlit_cloud"]
    _g["corre_en_streamlit_cloud"] = lambda: True
    at.run()
    esperar("en la app de internet no se ofrece leer por ruta",
            [r.options for r in at.radio if "Subir archivo" in r.options], [])
    _g["corre_en_streamlit_cloud"] = _en_la_nube
    [b for b in at.button if b.label == "Salir"][0].click().run()

    # 3. Ana vuelve a entrar; mientras está adentro le cambian el rol, y después la desactivan.
    _entrar(at, "ana", "clave-ana-1")
    c = ns["c"]
    c.execute("UPDATE usuarios SET rol = 'admin' WHERE nombre = 'ana'")
    ns["conn"].commit()
    at.run()
    esperar("con el rol nuevo, el permiso nuevo", at.session_state["nivel_usuario"], "admin")
    c.execute("UPDATE usuarios SET rol = 'operador' WHERE nombre = 'ana'")
    ns["conn"].commit()
    at.run()
    esperar("y al revés: se le bajan los permisos", at.session_state["nivel_usuario"], "operador")
    c.execute("UPDATE usuarios SET activo = 0 WHERE nombre = 'ana'")
    ns["conn"].commit()
    at.run()
    esperar("desactivada, la sesión se cierra",
            "nivel_usuario" in at.session_state, False)
    esperar("y lo dice", any("ya no está activa" in w.value for w in at.warning), True)
    esperar("sin errores en pantalla", [e.value for e in at.exception], [])

    # 4. Un taller ve su portal y nada más, aunque la sesión diga que está en Administrar.
    ns["crear_mecanico"]("Taller Sesión", "clave-taller-sesion-1")
    taller = ns["c"].execute("SELECT id FROM mecanicos WHERE nombre = 'Taller Sesión'").fetchone()[0]
    # En una sesión nueva: la barra de un taller ya no tiene Administrar (ver
    # PAGINAS_ABIERTAS), y AppTest no deja poner a mano un valor que la barra no ofrece.
    at = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
    at.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
    at.session_state["nivel_usuario"] = "mecanico"
    at.session_state["admin_nombre"] = "Taller Sesión"
    at.session_state["mecanico_id"] = taller
    at.session_state["pagina_actual"] = "🗂️ Administrar"
    at.run()
    textos = " ".join(m.value for m in at.markdown)
    esperar("el taller ve su portal", "Portal de mecánico" in textos, True)
    esperar("y no la administración", any(x in textos for x in ("Cuentas corrientes de los talleres",
                                                              "Usuarios", "Backup")), False)
    esperar("ni las pestañas del negocio", [b.label for b in at.button if "Administrar" in b.label], [])
    esperar("sin errores", [e.value for e in at.exception], [])

    # 4a. EL MODO MECÁNICO ES PARA CLIENTES CON CUENTA. Lo pidió el dueño: «si no ponés la
    # contraseña, la parte de los mecánicos no se tiene que ver, porque si no cualquiera se mete
    # en la página y la usa sin ser cliente nuestro». Sin contraseña no está en la barra ni se
    # llega poniéndolo a mano; el taller con cuenta lo tiene al lado de su portal, y lo ve como
    # lo veía el invitado: mira, no toca.
    mecanico, portal = ns["PAGINAS"][7], ns["PAGINA_DEL_PORTAL"]
    esperar("sin contraseña se ven el Buscador y la lista de WhatsApp",
            ns["PAGINAS_ABIERTAS"], ["🔍 Buscador", "📋 Lista WhatsApp"])
    esperar("la barra del taller: su portal y el Modo Mecánico",
            (at.radio(key="pagina_actual").options, at.radio(key="pagina_actual").value),
            ([portal, mecanico], portal))
    at.radio(key="pagina_actual").set_value(mecanico).run()
    esperar("el taller entra al Modo Mecánico, con sus solapas",
            (at.radio(key="sub_mec").options, [e.value for e in at.exception],
             "Portal de mecánico" in " ".join(m.value for m in at.markdown)),
            (ns["SUB_MEC"], [], False))
    esperar("y ahí mira, no toca",
            [b.label for b in at.button if "Guardar" in b.label or "Enseñar" in b.label], [])
    at.radio(key="pagina_actual").set_value(portal).run()
    esperar("y vuelve a su portal",
            "Portal de mecánico" in " ".join(m.value for m in at.markdown), True)
    # El que no entró: ni en la barra, ni poniéndolo a mano en la sesión, ni con el candado.
    invitado = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
    invitado.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
    invitado.run()
    esperar("sin contraseña, la barra no tiene el Modo Mecánico",
            invitado.radio(key="pagina_actual").options, ns["PAGINAS_ABIERTAS"])
    # En una sesión nueva, con eso ya puesto: AppTest no deja poner a mano un valor que la
    # barra no ofrece (como un link viejo, o una sesión que quedó de antes del cambio).
    invitado = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
    invitado.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
    invitado.session_state["pagina_actual"] = mecanico
    invitado.session_state["sub_mec"] = ns["SUB_MEC"][0]
    invitado.run()
    esperar("puesto a mano en la sesión, vuelve al Buscador y no dibuja nada de eso",
            (invitado.radio(key="pagina_actual").value,
             [r.key for r in invitado.radio if r.key == "sub_mec"],
             [e.value for e in invitado.exception]), ("🔍 Buscador", [], []))
    esperar("y «🔑 Ingresar» le dice al cliente dónde quedó",
            any("¿Sos taller o cliente?" in x.value and "Modo Mecánico" in x.value
                for x in invitado.caption), True)
    # Y EL CANDADO DE LA PANTALLA, por si se llega de otra forma: se le pone a mano en la barra
    # (como si un cambio futuro la volviera a ofrecer) y la pantalla igual no se dibuja.
    ns["PAGINAS_ABIERTAS"].append(mecanico)
    try:
        colado = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
        colado.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
        colado.session_state["pagina_actual"] = mecanico
        colado.run()
        esperar("llegando igual sin cuenta, la pantalla dice que es para clientes y corta",
                (colado.radio(key="pagina_actual").value,
                 # El cartel muestra el candado del texto como su ícono: se mira lo que sigue.
                 len([i for i in colado.info
                      if i.value and i.value in ns["TEXTO_MODO_MECANICO_CERRADO"]
                      and "es para los clientes del negocio" in i.value]),
                 [r.key for r in colado.radio if r.key == "sub_mec"],
                 [e.value for e in colado.exception]),
                (mecanico, 1, [], []))
    finally:
        ns["PAGINAS_ABIERTAS"].remove(mecanico)
    # El candado de la función, que es el que usa la pantalla: quién lo ve.
    import streamlit as st
    _estado = dict(st.session_state)
    try:
        _quien_lo_ve = {}
        for _quien, _nivel in (("invitado", None), ("taller", "mecanico"),
                               ("operador", "operador"), ("administrador", "admin")):
            st.session_state.clear()
            if _nivel:
                st.session_state["nivel_usuario"], st.session_state["admin_nombre"] = _nivel, "x"
            _quien_lo_ve[_quien] = ns["puede_ver_el_modo_mecanico"]()
    finally:
        st.session_state.clear()
        st.session_state.update(_estado)
    esperar("quién ve el Modo Mecánico", _quien_lo_ve,
            {"invitado": False, "taller": True, "operador": True, "administrador": True})

    # 4a''. QUÉ CLIENTES USAN SU CUENTA: desde que el Modo Mecánico es para clientes con cuenta,
    # el administrador ve cuándo entró cada una por última vez y cuántas veces. Entrar con la
    # contraseña mal no cuenta, y el que nunca entró figura vacío.
    _cuenta_i = ns["crear_mecanico"]("Taller Que Entra", "clave-del-que-entra-1")
    ns["crear_mecanico"]("Taller Que No Entra", "clave-del-que-no-entra-1")

    def _ingresos():
        return {m["Nombre"]: (m["Veces"], bool(m["Última vez que entró"]))
                for m in ns["listar_mecanicos"]() if m["Nombre"].startswith("Taller Que")}
    esperar("recién creadas, ninguna entró", _ingresos(),
            {"Taller Que Entra": (0, False), "Taller Que No Entra": (0, False)})
    for _clave_i, _veces in (("una-clave-que-no-es-1", 0), ("clave-del-que-entra-1", 1),
                             ("clave-del-que-entra-1", 2)):
        _sesion_i = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
        _sesion_i.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
        _sesion_i.run()
        _entrar(_sesion_i, str(_cuenta_i), _clave_i)
        esperar(f"entrando con «{_clave_i[:12]}…»: las veces que entró", _ingresos(),
                {"Taller Que Entra": (_veces, _veces > 0), "Taller Que No Entra": (0, False)})
    _ultima = next(m["Última vez que entró"] for m in ns["listar_mecanicos"]()
                   if m["Nombre"] == "Taller Que Entra")
    esperar("la última vez se lee como una fecha de acá (día/mes/año y hora)",
            bool(re.fullmatch(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}", _ultima)), True)

    # 4c. DEL AUTO AL PRESUPUESTO DEL TALLER. En «🚙 Repuestos por vehículo» el taller ve lo que
    # le entra a un auto; cada renglón tiene su «➕» que lo suma a su presupuesto, el código lo
    # lleva a SU portal (no tiene Buscador), y el precio es el que se le dice a un cliente: la
    # lista en otra escala, «precio a confirmar», y no se suma. Los números de fábrica, que no
    # se venden, tampoco.
    _f_ok = {"ID": 1, "Codigo": "AM100", "Marca": "BUENA", "Precio": 1500.0,
             "Descripcion": "AMORTIGUADOR  DELANTERO\nGOL"}
    _fuera_v = {"PORTAL OTRA ESCALA"}
    esperar("el ítem que va al presupuesto, con la descripción en un renglón",
            ns["item_para_el_presupuesto"](_f_ok, _fuera_v, {"OEM / FABRICA"}),
            {"codigo": "AM100", "marca": "BUENA", "descripcion": "AMORTIGUADOR DELANTERO GOL",
             "precio": 1500.0, "cantidad": 1})
    esperar("no se presupuesta: otra escala, sin precio, número de fábrica, sin código",
            [ns["item_para_el_presupuesto"]({**_f_ok, **_cambio}, _fuera_v, {"OEM / FABRICA"})
             for _cambio in ({"Marca": "PORTAL OTRA ESCALA"}, {"Precio": 0},
                             {"Marca": "OEM / FABRICA"}, {"Codigo": ""})], [None] * 4)
    esperar("la tabla del chasis trae el código como «Código»: también",
            ns["item_para_el_presupuesto"]({"Código": "X9", "Marca": "BUENA", "Precio": 10},
                                           set())["codigo"], "X9")
    _op = ns["repuestos_para_el_presupuesto"](
        [_f_ok, {**_f_ok, "Marca": "PORTAL OTRA ESCALA"}, {**_f_ok, "Codigo": "AM200"}], _fuera_v)
    esperar("lo que se ofrece para elegir: solo lo que se puede sumar, con su precio",
            list(_op), ["BUENA AM100 — AMORTIGUADOR DELANTERO GOL ($1.500)",
                        "BUENA AM200 — AMORTIGUADOR DELANTERO GOL ($1.500)"])
    import streamlit as st
    _estado_v = dict(st.session_state)
    try:
        st.session_state.clear()
        st.session_state["nivel_usuario"], st.session_state["admin_nombre"] = "mecanico", "x"
        st.session_state["elegidos_v"] = list(_op) + ["uno que no estaba en la lista"]
        ns["sumar_lo_elegido_al_presupuesto"]("elegidos_v", _op)
        ns["poner_en_el_presupuesto"]([_op["BUENA AM100 — AMORTIGUADOR DELANTERO GOL ($1.500)"]])
        esperar("sumar lo elegido: va al presupuesto, lo repetido suma una unidad, y la lista "
                "queda vacía",
                ([(i["codigo"], i["cantidad"])
                  for i in st.session_state["presupuesto_mecanico_items"]],
                 st.session_state["elegidos_v"]), ([("AM100", 2), ("AM200", 1)], []))
        esperar("y avisa dónde quedó",
                [a for a in st.session_state.get("_avisos", []) if "Mi portal" in a[1]] != [], True)
        # Para el taller la tabla dice «precio a confirmar»; en su escala, el precio.
        _g_v = ns["filas_con_el_precio_para_el_cliente"].__globals__
        _fuera_de_verdad = _g_v["marcas_con_precios_fuera_de_escala"]
        _g_v["marcas_con_precios_fuera_de_escala"] = lambda: _fuera_v
        try:
            _tabla = [_f_ok, {**_f_ok, "Marca": "PORTAL OTRA ESCALA", "Precio": 745.0}]
            esperar("al taller, el precio de la tabla como a un cliente",
                    [f["Precio"] for f in ns["filas_con_el_precio_para_el_cliente"](_tabla)],
                    ["$1.500", "precio a confirmar"])
            esperar("si no hay ninguna de esas listas, la tabla va tal cual",
                    ns["filas_con_el_precio_para_el_cliente"]([_f_ok])[0]["Precio"], 1500.0)
            # Lo hace quitar_id(), que es por donde salen casi todas las tablas (el Buscador
            # sin contraseña mostraba el número crudo). Y dos veces da lo mismo: una pantalla
            # puede llamarla y después pasar la tabla por quitar_id().
            esperar("quitar_id() ya lo trae como a un cliente",
                    [f["Precio"] for f in ns["quitar_id"](_tabla)],
                    ["$1.500", "precio a confirmar"])
            esperar("dos veces da lo mismo",
                    [f["Precio"] for f in ns["quitar_id"](
                        ns["filas_con_el_precio_para_el_cliente"](_tabla))],
                    ["$1.500", "precio a confirmar"])
            # Con el precio escrito, la columna es de texto: con la de números Streamlit
            # dibuja un triángulo de error en cada celda.
            esperar("la columna del precio escrito es de texto",
                    (ns["config_de_las_columnas"](ns["quitar_id"](_tabla))["Precio"]
                     ["type_config"]["type"],
                     ns["config_de_las_columnas"]([_f_ok])["Precio"]["type_config"]["type"]),
                    ("text", "number"))
            st.session_state["nivel_usuario"] = "operador"
            esperar("al personal, el número",
                    [f["Precio"] for f in ns["filas_con_el_precio_para_el_cliente"](_tabla)],
                    [1500.0, 745.0])
        finally:
            _g_v["marcas_con_precios_fuera_de_escala"] = _fuera_de_verdad
        # «🔎 código»: al taller lo lleva a su portal con el código buscado; al personal, no.
        st.session_state.clear()
        st.session_state["nivel_usuario"], st.session_state["admin_nombre"] = "mecanico", "x"
        st.session_state["pagina_actual"] = mecanico
        ns["cb_ver_equivalencias"]("AM100")
        esperar("tocar un código, el taller: a su portal, con eso buscado",
                (st.session_state.get("pagina_actual"),
                 st.session_state.get("_asis_para_el_portal"),
                 "ultima_busqueda_codigo" in st.session_state), (portal, "AM100", False))
        st.session_state.clear()
        st.session_state["nivel_usuario"], st.session_state["admin_nombre"] = "operador", "x"
        ns["cb_ver_equivalencias"]("AM100")
        esperar("y al personal le sigue buscando las equivalencias",
                ("ultima_busqueda_codigo" in st.session_state,
                 "_asis_para_el_portal" in st.session_state), (True, False))
    finally:
        st.session_state.clear()
        st.session_state.update(_estado_v)

    # 4a'. EL ORDEN DE LA BARRA: tres grupos de cuatro, con la rayita entre uno y otro para el
    # que tiene las doce; el invitado, el del depósito y el taller no tienen qué separar.
    esperar("el orden es de las doce pantallas, cada una una vez",
            (sorted(ns["ORDEN_DE_LAS_PAGINAS"]), [len(g) for g in ns["GRUPOS_DE_LA_BARRA"]]),
            (sorted(ns["PAGINAS"]), [4, 4, 4]))
    esperar("ventas y depósito primero, y la configuración al final",
            (ns["ORDEN_DE_LAS_PAGINAS"][:4], ns["ORDEN_DE_LAS_PAGINAS"][-1]),
            (["🧾 Ventas", "💵 Caja", "📦 Depósito", "↩️ Devoluciones"], "🗂️ Administrar"))
    esperar("dónde va la rayita, para cada barra",
            [ns["cortes_de_la_barra"](b) for b in (
                ns["ORDEN_DE_LAS_PAGINAS"], ns["PAGINAS_ABIERTAS"], ns["PAGINAS_DEL_DEPOSITO"],
                ns["PAGINAS_DEL_TALLER"])], [[4, 8], [], [], []])
    _rayitas = ns["rayitas_de_la_barra"](ns["ORDEN_DE_LAS_PAGINAS"])
    esperar("la rayita va después de la cuarta y de la octava",
            (":nth-child(4)" in _rayitas, ":nth-child(8)::after" in _rayitas,
             ":nth-child(12)" in _rayitas, ns["rayitas_de_la_barra"](ns["PAGINAS_ABIERTAS"])),
            (True, True, False, ""))

    # 4b. EN EL PORTAL, EL PRECIO ES EL QUE SE LE DICE A UN CLIENTE: la lista que está en otra
    # escala sale «precio a confirmar» y no se puede sumar al presupuesto (ver
    # renglon_del_portal()). Antes mostraba el número tal cual —TARANTO, quince veces más
    # barato— y el taller presupuestaba con eso.
    _fila_cara = {"Marca": "PORTAL OTRA ESCALA", "Codigo": "JT100", "Descripcion": "JUNTA TAPA",
                  "Precio": 1505}
    esperar("el renglón de una lista en otra escala",
            ns["renglon_del_portal"](_fila_cara, {"PORTAL OTRA ESCALA"}),
            ("PORTAL OTRA ESCALA - JT100 — JUNTA TAPA (precio a confirmar)", False))
    esperar("el de una lista en su escala",
            ns["renglon_del_portal"](_fila_cara, set()),
            ("PORTAL OTRA ESCALA - JT100 — JUNTA TAPA ($1.505)", True))
    esperar("sin precio no hay nada que confirmar: se suma en cero, como siempre",
            ns["renglon_del_portal"]({**_fila_cara, "Precio": 0}, {"PORTAL OTRA ESCALA"}),
            ("PORTAL OTRA ESCALA - JT100 — JUNTA TAPA (s/precio)", True))
    # Y SI HAY: el taller armaba el presupuesto sin saber si el repuesto estaba. Lo mismo que
    # ve cualquiera en el Buscador: lo libre si la fila lo trae, y la descripción con signos
    # de markdown, escapada.
    esperar("el renglón del portal dice si hay",
            [ns["renglon_del_portal"]({**_fila_cara, **_stock}, set(), True)[0].split(" · ")[-1]
             for _stock in ({"Stock": 3}, {"Stock": 0}, {"Stock": 5, "Libre": 2}, {"Stock": None})],
            ["🟢 **3** en stock", "🔴 sin stock", "🟢 **2** en stock", "⚪ stock s/d"])
    # Con más resultados de los que entran, primero los que se pueden presupuestar: con la base
    # real, los 20 que se veían de «junta tapa valvulas» eran todos «precio a confirmar».
    _muchos = ([{"Codigo": f"T{n}", "Marca": "PORTAL OTRA ESCALA", "Precio": 100} for n in range(25)]
               + [{"Codigo": f"B{n}", "Marca": "BUENA", "Precio": 100} for n in range(6)]
               + [{"Codigo": "S1", "Marca": "PORTAL OTRA ESCALA", "Precio": 0}])
    _vista, _quedan = ns["resultados_para_el_portal"](_muchos, {"PORTAL OTRA ESCALA"})
    esperar("portal: primero lo que se puede presupuestar, en su orden, y cuántos quedaron",
            ([f["Codigo"] for f in _vista[:8]], len(_vista), _quedan),
            (["B0", "B1", "B2", "B3", "B4", "B5", "S1", "T0"], 20, 12))
    esperar("portal: si entran todos, van como salieron",
            ([f["Codigo"] for f in ns["resultados_para_el_portal"](_muchos[20:], {"PORTAL OTRA ESCALA"})[0]][:3],
             ns["resultados_para_el_portal"](_muchos[20:], {"PORTAL OTRA ESCALA"})[1]),
            (["T20", "T21", "T22"], 0))
    esperar("y no rompe el texto una descripción con signos",
            ns["renglon_del_portal"]({**_fila_cara, "Descripcion": "JUNTA 1_8 *REF*"}, set())[0],
            "PORTAL OTRA ESCALA - JT100 — JUNTA 1\\_8 \\*REF\\* ($1.505)")
    ns["c"].execute("INSERT INTO marcas (nombre, tipo) VALUES ('PORTAL OTRA ESCALA', 'PROVEEDOR')")
    _marca_portal = ns["c"].lastrowid
    ns["c"].execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, "
                    "precio) VALUES ('JT100', 'JT100', 'JUNTA TAPA', ?, 1505)", (_marca_portal,))
    ns["conn"].commit()
    _gp = ns["mostrar_portal_mecanico"].__globals__
    _fuera_del_portal = _gp["marcas_con_precios_fuera_de_escala"]
    try:
        for _fuera, _texto, _apagado in (
                ({"PORTAL OTRA ESCALA"}, "(precio a confirmar)", True),
                (set(), "($1.505)", False)):
            _gp["marcas_con_precios_fuera_de_escala"] = lambda _f=_fuera: _f
            at.text_input(key="mec_busqueda").set_value("JT100").run()
            _renglon = [m.value for m in at.markdown if "JT100" in m.value]
            esperar(f"en el portal, con la lista {'en otra escala' if _apagado else 'bien'}: "
                    "lo que lee el taller", [_texto in x for x in _renglon], [True])
            esperar("y si lo puede sumar al presupuesto",
                    [b.disabled for b in at.button if b.key and b.key.startswith("add_mec_")],
                    [_apagado])
        esperar("el portal se dibuja sin errores", [e.value for e in at.exception], [])
    finally:
        _gp["marcas_con_precios_fuera_de_escala"] = _fuera_del_portal

    # 4c. EL PAPEL DEL COMPROBANTE se guarda al tocar el selector, y el selector muestra siempre
    # lo guardado. Antes comparaba, en cada pasada, lo que mostraba con lo guardado: con dos
    # pantallas abiertas, la de uno le pisaba sin querer lo que había elegido el otro.
    at = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
    at.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
    at.session_state["nivel_usuario"], at.session_state["admin_nombre"] = "admin", "duenio"
    at.session_state["pagina_actual"] = "🗂️ Administrar"
    at.session_state["sub_admin"] = "💬 Mensajería y cobros"
    at.run()
    _papel = at.radio(key="papel_del_comprobante_elegido")
    esperar("el selector del papel muestra lo guardado", (_papel.value, ns["papel_del_comprobante"]()),
            ("Hoja A4", "Hoja A4"))
    _papel.set_value("Ticket de 80 mm").run()
    esperar("al tocarlo se guarda, y lo dice",
            (ns["papel_del_comprobante"](), any("Ticket de 80 mm" in x.value for x in at.success)),
            ("Ticket de 80 mm", True))
    # Otro, desde su pantalla, lo vuelve a hoja: esta pantalla lo muestra y NO lo pisa.
    ns["guardar_config"]("papel_del_comprobante", "Hoja A4")
    ns["conn"].commit()
    at.run()
    esperar("si otro lo cambió, esta pantalla muestra lo nuevo y no lo pisa",
            (at.radio(key="papel_del_comprobante_elegido").value, ns["papel_del_comprobante"]()),
            ("Hoja A4", "Hoja A4"))
    at.run()
    esperar("ni en la pasada siguiente", ns["papel_del_comprobante"](), "Hoja A4")
    esperar("sin errores en la pantalla", [e.value for e in at.exception], [])

    # 4e. LA PÁGINA, SOLO CON CUENTA. El dueño pidió el Modo Mecánico solo para clientes «ya que
    # si no cualquiera se va a meter en la página y lo va a usar sin ser clientes nuestros»; con
    # el Buscador pasa lo mismo, y ahora lo decide él con una llave (🗂️ Administrar → 👥
    # Usuarios). Viene abierta. Cerrada, el que no entró ve SOLO el ingreso: ni la barra, ni el
    # Buscador, ni el asistente, ni «Continuar sin contraseña» —y tampoco poniéndose a mano una
    # pantalla en la sesión—. El personal y el taller con cuenta entran como siempre.
    def _visitante(**sesion):
        _v = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
        _v.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
        for _k, _valor in sesion.items():
            _v.session_state[_k] = _valor
        return _v.run()

    def _lo_que_ve(_v):
        return {"barra": [r.key for r in _v.radio if r.key == "pagina_actual"],
                "buscador": [w.key for w in _v.text_input if w.key == "busqueda_input"],
                "asistente": [b.key for b in _v.button if "asistente" in (b.key or "")],
                "seguir sin contraseña": [b.label for b in _v.button
                                          if "Continuar sin contraseña" in b.label],
                "ingreso": sorted(w.key for w in _v.text_input
                                  if (w.key or "").startswith("login_inicial")),
                "errores": [e.value[:120] for e in _v.exception]}

    _CERRADO = {"barra": [], "buscador": [], "asistente": [], "seguir sin contraseña": [],
                "ingreso": ["login_inicial_clave", "login_inicial_nombre"], "errores": []}
    esperar("la llave viene abierta",
            (ns["se_entra_solo_con_cuenta"](), _lo_que_ve(_visitante())["barra"],
             _lo_que_ve(_visitante())["buscador"]), (False, ["pagina_actual"], ["busqueda_input"]))
    # Solo el administrador la da vuelta: ni el operador ni el taller (y queda en el registro).
    # Acá no hay una sesión de Streamlit corriendo, y sin sesión exigir_nivel() deja pasar (es
    # como llaman las tareas de fondo): se le dice a mano quién está adentro.
    import streamlit as st
    _estado = dict(st.session_state)
    _g_nivel = ns["exigir_nivel"].__globals__
    _adentro_de_verdad = _g_nivel["_nivel_de_quien_esta_adentro"]
    try:
        for _nivel in ("operador", "mecanico", ""):
            _g_nivel["_nivel_de_quien_esta_adentro"] = lambda _n=_nivel: _n
            try:
                ns["cambiar_solo_con_cuenta"](True)
                _pudo = True
            except PermissionError:
                _pudo = False
            esperar(f"un «{_nivel or 'sin entrar'}» no puede cerrar la página",
                    (_pudo, ns["se_entra_solo_con_cuenta"]()), (False, False))
        _g_nivel["_nivel_de_quien_esta_adentro"] = lambda: "admin"
        st.session_state.clear()
        st.session_state["nivel_usuario"], st.session_state["admin_nombre"] = "admin", "duenio"
        ns["cambiar_solo_con_cuenta"](True)
        ns["conn"].commit()
    finally:
        _g_nivel["_nivel_de_quien_esta_adentro"] = _adentro_de_verdad
        st.session_state.clear()
        st.session_state.update(_estado)
    _anotado = ns["c"].execute("SELECT usuario, antes, despues FROM registro_de_cambios "
                               "WHERE entidad_id = ? ORDER BY id DESC LIMIT 1",
                               (ns["CLAVE_DE_SOLO_CON_CUENTA"],)).fetchone()
    esperar("el administrador sí, y queda anotado quién y qué",
            (ns["se_entra_solo_con_cuenta"](), tuple(_anotado) if _anotado else None),
            (True, ("duenio",) + ns["SIN_CONTRASENA_SE_VE"]))
    try:
        _v = _visitante()
        esperar("cerrada, el que no entró ve solo el ingreso", _lo_que_ve(_v), _CERRADO)
        esperar("y le dice para quién es y cómo pedir la cuenta",
                (any("hace falta una cuenta" in h.value for h in _v.subheader),
                 any("Pedila en el mostrador" in x.value for x in _v.caption)), (True, True))
        esperar("tampoco poniéndose a mano una pantalla en la sesión",
                [_lo_que_ve(_visitante(pagina_actual=_p)) for _p in
                 (ns["PAGINAS"][0], ns["PAGINAS"][5], ns["PAGINAS"][7], "🗂️ Administrar")],
                [_CERRADO] * 4)
        esperar("ni diciendo que ya eligió seguir sin contraseña",
                _lo_que_ve(_visitante(usuario_nombre="Invitado")), _CERRADO)
        esperar("la cuenta de páginas, que también usa el asistente, le da ninguna",
                ns["paginas_a_la_vista"](False), [])
        # Con la contraseña equivocada sigue afuera; con la buena, adentro y con toda la barra.
        _entrar(_v, "duenio", "no-es-esta")
        esperar("con la contraseña equivocada sigue viendo solo el ingreso",
                (_lo_que_ve(_v), any("incorrectos" in e.value for e in _v.error)),
                (_CERRADO, True))
        _entrar(_v, "duenio", "clave-duenio-1")
        esperar("el administrador entra, con toda la barra",
                (_v.radio(key="pagina_actual").options, [e.value for e in _v.exception]),
                (ns["ORDEN_DE_LAS_PAGINAS"], []))
        [b for b in _v.button if b.label == "Salir"][0].click().run()
        esperar("al salir, otra vez solo el ingreso", _lo_que_ve(_v), _CERRADO)
        _entrar(_v, str(taller), "clave-taller-sesion-1")
        esperar("el taller con cuenta entra, a su portal y su Modo Mecánico",
                (_v.radio(key="pagina_actual").options, [e.value for e in _v.exception]),
                (ns["PAGINAS_DEL_TALLER"], []))
        # Con el WhatsApp del negocio cargado, la cuenta se pide de un toque.
        _wa_antes = ns["obtener_config"]("whatsapp_del_negocio", "")
        ns["guardar_config"]("whatsapp_del_negocio", "5491145678901")
        try:
            esperar("con el WhatsApp del negocio cargado, se pide la cuenta por ahí",
                    [b.url[:28] for b in _visitante().get("link_button")
                     if "Pedir una cuenta" in b.label], ["https://wa.me/5491145678901?"])
        finally:
            ns["guardar_config"]("whatsapp_del_negocio", _wa_antes)
        # La pantalla del administrador: la llave está en 👥 Usuarios, marcada como está hoy, y
        # se abre con su botón (no al tocar la opción: cerrarla saca a todos los sin cuenta).
        _adm = _visitante(nivel_usuario="admin", admin_nombre="duenio",
                          pagina_actual="🗂️ Administrar", sub_admin=ns["SUB_ADMIN"][5])
        _llave = _adm.radio(key="llave_solo_con_cuenta")
        esperar("la llave, en 👥 Usuarios, marcada cerrada y sin nada para guardar",
                (_llave.value, [b.key for b in _adm.button if b.key == "guardar_solo_con_cuenta"],
                 [e.value for e in _adm.exception]), (ns["SIN_CONTRASENA_SE_VE"][1], [], []))
        _llave.set_value(ns["SIN_CONTRASENA_SE_VE"][0]).run()
        esperar("elegir la otra opción no la cambia: ofrece guardar",
                (ns["se_entra_solo_con_cuenta"](),
                 [b.key for b in _adm.button if b.key == "guardar_solo_con_cuenta"]),
                (True, ["guardar_solo_con_cuenta"]))
        _adm.button(key="guardar_solo_con_cuenta").click().run()
        esperar("con «Guardar» se abre, y el que no entró vuelve a ver el Buscador",
                (ns["se_entra_solo_con_cuenta"](), _lo_que_ve(_visitante())["buscador"],
                 [e.value for e in _adm.exception]), (False, ["busqueda_input"], []))
        # Sin ninguna contraseña la llave no hace nada: no habría con qué entrar.
        ns["guardar_config"](ns["CLAVE_DE_SOLO_CON_CUENTA"], "si")
        _g = ns["la_pagina_pide_cuenta"].__globals__
        _hay_de_verdad = _g["hay_claves_configuradas"]
        _g["hay_claves_configuradas"] = lambda: False
        try:
            esperar("sin ninguna contraseña configurada, la llave no cierra nada",
                    ns["la_pagina_pide_cuenta"](), False)
        finally:
            _g["hay_claves_configuradas"] = _hay_de_verdad
        # Si la base no contesta, se da por cerrada: es una llave de seguridad.
        ns["guardar_config"](ns["CLAVE_DE_SOLO_CON_CUENTA"], "")
        _config_de_verdad = _g["obtener_config"]

        def _no_contesta(*_a, **_k):
            raise sqlite3.OperationalError("database is locked")
        _g["obtener_config"] = _no_contesta
        try:
            esperar("si la base no contesta, la página se da por cerrada",
                    ns["se_entra_solo_con_cuenta"](), True)
        finally:
            _g["obtener_config"] = _config_de_verdad
    finally:
        ns["guardar_config"](ns["CLAVE_DE_SOLO_CON_CUENTA"], "")
        ns["conn"].commit()

    # 4f. EL ACCESO DE UN CLIENTE, LISTO PARA MANDAR. «🎲 Inventarle una contraseña» le da una
    # que se dicta sin errores y la muestra hasta «Ya se la pasé»; «📲 Mandarle cómo entrar» arma
    # el WhatsApp con la dirección y su usuario, SIN la contraseña (ver mensaje_de_acceso()).
    _inventadas = {ns["contrasena_para_dictar"]() for _ in range(200)}
    esperar("la contraseña inventada: «xxxx-xxxx», sin los signos que se confunden, y distinta "
            "cada vez",
            (len(_inventadas),
             all(re.fullmatch(r"[a-km-np-z2-9]{4}-[a-km-np-z2-9]{4}", x) for x in _inventadas),
             any(ch in x for x in _inventadas for ch in "0o1li")), (200, True, False))
    _cuenta_acceso = ns["crear_mecanico"]("Lubricentro Del Acceso")
    _msj = ns["mensaje_de_acceso"](_cuenta_acceso, "Lubricentro Del Acceso")
    esperar("el mensaje trae la dirección con su cuenta y su usuario",
            (f"?cuenta={_cuenta_acceso}" in _msj, f"*{_cuenta_acceso}*" in _msj,
             "Lubricentro Del Acceso" in _msj), (True, True, True))
    _adm = _visitante(nivel_usuario="admin", admin_nombre="duenio",
                      pagina_actual="🗂️ Administrar", sub_admin=ns["SUB_ADMIN"][5],
                      _mecanico_ultimo=_cuenta_acceso)
    esperar("sin portal todavía, no ofrece mandar cómo entrar (no podría entrar)",
            [b.label for b in _adm.get("link_button") if "Mandarle cómo entrar" in b.label], [])
    _adm.button(key="mecanico_inventar_clave").click().run()
    _mostrada = [x.value for x in _adm.code]
    esperar("la inventa, la guarda y la muestra una vez para copiar",
            (len(_mostrada), [e.value for e in _adm.exception]), (1, []))
    _clave_inventada = _mostrada[0] if _mostrada else ""
    esperar("con esa contraseña el cliente entra a lo suyo",
            ns["validar_password"](_clave_inventada, con_mecanicos=True,
                                   usuario=str(_cuenta_acceso))[1], "mecanico")
    _links = [b.url for b in _adm.get("link_button") if "Mandarle cómo entrar" in b.label]
    esperar("el WhatsApp lleva su cuenta, y la contraseña NO",
            (len(_links), all(f"cuenta%3D{_cuenta_acceso}" in u for u in _links),
             any(_clave_inventada and _clave_inventada in u for u in _links),
             any(quote(_clave_inventada) in u for u in _links)), (1, True, False, False))
    _ultimo = ns["c"].execute("SELECT accion, detalle, antes, despues FROM registro_de_cambios "
                              "WHERE entidad = 'taller' AND entidad_id = ? ORDER BY id DESC "
                              "LIMIT 1", (str(_cuenta_acceso),)).fetchone()
    esperar("queda anotado que se cambió, sin la contraseña",
            (_ultimo[0] if _ultimo else None,
             any(_clave_inventada in str(x or "") for x in (_ultimo or ()))),
            ("cambió la contraseña del portal", False))
    _adm.button(key="mecanico_ya_se_la_pase").click().run()
    esperar("con «Ya se la pasé» no se ve más, y el mensaje sigue a mano",
            ([x.value for x in _adm.code], "_acceso_recien_dado" in _adm.session_state,
             len([b for b in _adm.get("link_button") if "Mandarle cómo entrar" in b.label])),
            ([], False, 1))
    # La dirección del mensaje deja puesto su usuario, también con la página cerrada: es lo
    # que le llega al cliente, y si llegara vacío no sabría qué poner.
    for _cerrada in ("", "si"):
        ns["guardar_config"](ns["CLAVE_DE_SOLO_CON_CUENTA"], _cerrada)
        ns["conn"].commit()
        _con_link = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
        _con_link.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
        _con_link.query_params["cuenta"] = str(_cuenta_acceso)
        _con_link.run()
        esperar(f"el link del mensaje trae puesto su usuario (página {'cerrada' if _cerrada else 'abierta'})",
                ([w.value for w in _con_link.text_input if w.key == "login_inicial_nombre"],
                 [e.value for e in _con_link.exception]), ([str(_cuenta_acceso)], []))
        if _cerrada:
            _entrar(_con_link, str(_cuenta_acceso), _clave_inventada)
            esperar("y con la contraseña inventada entra a su portal",
                    (_con_link.radio(key="pagina_actual").options,
                     [e.value for e in _con_link.exception]), (ns["PAGINAS_DEL_TALLER"], []))
    ns["guardar_config"](ns["CLAVE_DE_SOLO_CON_CUENTA"], "")
    ns["conn"].commit()
    # Y si se elige otra cuenta antes de tocarlo, tampoco: no se le muestra la de otro.
    _adm.button(key="mecanico_inventar_clave").click().run()
    _adm.selectbox(key="cuenta_sel_gestionar").set_value(taller).run()
    esperar("eligiendo otra cuenta, la contraseña de la anterior no se ve más",
            ([x.value for x in _adm.code], "_acceso_recien_dado" in _adm.session_state),
            ([], False))

    # 4g. EL AUTO POR LA PATENTE. Lo pidió el dueño: «que los clientes puedan ingresar poniendo
    # la patente a ver qué cosas se le fueron cambiando al auto (opcional), ya que muchos
    # mecánicos no van a querer anotar todas las patentes». El taller le pone al presupuesto la
    # patente y el km si quiere, y «✅ Ya se lo puse» lo suma a lo que se le cambió al auto; el
    # dueño del auto lo ve con la patente sola desde «🔑 Ingresar» (también con la página
    # cerrada). Ver «EL TALLER ANOTA EN QUÉ AUTO LO PUSO» y «CON LA PATENTE SOLA».
    _items_g = [{"codigo": "W712/94", "marca": "MANN", "descripcion": "FILTRO DE ACEITE VW GOL",
                 "precio": 1500.0, "cantidad": 1},
                {"codigo": "BKR6E", "marca": "NGK", "descripcion": "BUJIA NGK", "precio": 900.0,
                 "cantidad": 4}]
    _portal = _visitante(nivel_usuario="mecanico", admin_nombre="Taller Sesión",
                         mecanico_id=taller, pagina_actual=ns["PAGINA_DEL_PORTAL"],
                         presupuesto_mecanico_items=[dict(x) for x in _items_g])
    esperar("en el presupuesto, la patente y el km son opcionales: sin ellas se guarda igual",
            ([w.key for w in _portal.text_input if w.key == "mec_patente"],
             _portal.checkbox(key="mec_ya_puesto").disabled, [e.value for e in _portal.exception]),
            (["mec_patente"], True, []))
    _portal.text_input(key="mec_cliente").set_value("Juan Pérez del Taller")
    _portal.text_input(key="mec_patente").set_value("ag-777-kl")
    _portal.number_input(key="mec_km").set_value(80000).run()
    esperar("con la patente de un auto sin nada, lo dice",
            any("Todavía no hay nada anotado en AG777KL" in x.value for x in _portal.caption), True)
    _portal.checkbox(key="mec_ya_puesto").check()
    [b for b in _portal.button if "Guardar presupuesto" in b.label][0].click().run()
    _auto_g = ns["c"].execute("SELECT id, cliente_nombre, km_actual FROM vehiculos WHERE "
                              "patente = 'AG777KL'").fetchone()
    _piezas_g = ns["c"].execute("SELECT descripcion_pieza, marca_pieza, km_instalacion, nota "
                                "FROM historial_piezas WHERE vehiculo_id = ? ORDER BY id",
                                (_auto_g[0] if _auto_g else -1,)).fetchall()
    esperar("«Ya se lo puse»: las piezas en el auto, con el km y qué taller las anotó",
            (len(_piezas_g), [p[1] for p in _piezas_g], {p[2] for p in _piezas_g},
             all("Lo anotó el taller Taller Sesión" in p[3] for p in _piezas_g),
             _auto_g[2] if _auto_g else None, [e.value for e in _portal.exception]),
            (2, ["MANN", "NGK"], {80000}, True, 80000, []))
    esperar("la ficha del auto no se lleva el nombre del cliente del taller",
            (_auto_g[1] or "") if _auto_g else None, "")
    _presu_g = ns["c"].execute("SELECT id, patente, km, anotado_en FROM presupuestos_mecanico "
                               "WHERE mecanico_id = ? ORDER BY id DESC LIMIT 1",
                               (taller,)).fetchone()
    esperar("el presupuesto queda con su patente y anotado una sola vez",
            (_presu_g[1], _presu_g[2], bool(_presu_g[3]),
             ns["anotar_presupuesto_en_el_auto"](taller, _presu_g[0])[0]),
            ("AG777KL", 80000, True, False))
    # Otro presupuesto, sin marcar «Ya se lo puse»: lo anota después, desde «Mis presupuestos».
    _portal.session_state["presupuesto_mecanico_items"] = [dict(_items_g[0])]
    _portal.run()
    _portal.text_input(key="mec_patente").set_value("AG777KL").run()
    esperar("con la patente, el taller ve lo que ya se le cambió a ese auto",
            any("ya se le cambió" in x.value and "MANN" in x.value for x in _portal.caption), True)
    [b for b in _portal.button if "Guardar presupuesto" in b.label][0].click().run()
    _id_g2 = ns["c"].execute("SELECT MAX(id) FROM presupuestos_mecanico WHERE mecanico_id = ?",
                             (taller,)).fetchone()[0]
    _portal.number_input(key=f"presu_km_{_id_g2}").set_value(70000)
    _portal.button(key=f"presu_anotar_{_id_g2}").click().run()
    esperar("después, con menos km que los anotados: lo frena y lo dice",
            (any("menos km" in w.value for w in _portal.warning),
             ns["c"].execute("SELECT anotado_en FROM presupuestos_mecanico WHERE id = ?",
                             (_id_g2,)).fetchone()[0]), (True, None))
    _portal.number_input(key=f"presu_km_{_id_g2}").set_value(None)
    _portal.button(key=f"presu_anotar_{_id_g2}").click().run()
    esperar("sin el km, se anota igual",
            (bool(ns["c"].execute("SELECT anotado_en FROM presupuestos_mecanico WHERE id = ?",
                                  (_id_g2,)).fetchone()[0]),
             ns["c"].execute("SELECT COUNT(*) FROM historial_piezas WHERE vehiculo_id = ?",
                             (_auto_g[0],)).fetchone()[0], [e.value for e in _portal.exception]),
            (True, 3, []))
    # LA VIDA ÚTIL DE REFERENCIA (ver VIDA_UTIL_DE_REFERENCIA): el taller no la escribe, y el
    # dueño del auto veía «⚪ Sin datos». Ahora el filtro de aceite y las bujías dicen cuánto
    # les falta, marcado «referencia general»; no se guarda en la base (si no, pasaría a ser
    # «la de otras veces»), y lo que no se cambia por km sigue «Sin datos».
    _auto_dict_g = ns["buscar_vehiculo"]("AG777KL")
    _piezas_estado_g = {e["Pieza"]: e for e in ns["estado_de_cada_pieza"](_auto_dict_g)}
    _filtro_g = next((e for n, e in _piezas_estado_g.items() if "aceite" in n.lower()), None)
    _bujia_g = next((e for n, e in _piezas_estado_g.items() if "buj" in n.lower()), None)
    esperar("con la vida útil de referencia, marcada, y sin guardarla en la base",
            (_filtro_g and (_filtro_g["Vida útil (km)"], _filtro_g["Cada (meses)"],
                            _filtro_g["Estado"][:1],
                            _filtro_g["Le falta"].endswith(ns["TEXTO_DE_REFERENCIA"])),
             _bujia_g and (_bujia_g["Vida útil (km)"], _bujia_g["Cada (meses)"]),
             ns["c"].execute("SELECT COUNT(*) FROM historial_piezas WHERE vehiculo_id = ? AND "
                             "(vida_util_km > 0 OR vida_util_meses > 0)",
                             (_auto_g[0],)).fetchone()[0]),
            ((10000, 12, "🟢", True), (30000, None), 0))
    # Con la vida útil anotada por una persona, manda esa, y sin la marca.
    ns["c"].execute("UPDATE historial_piezas SET vida_util_km = 15000 WHERE vehiculo_id = ? AND "
                    "descripcion_pieza = ?", (_auto_g[0], _filtro_g["Pieza"]))
    _anotada_g = next(e for e in ns["estado_de_cada_pieza"](_auto_dict_g)
                      if e["Pieza"] == _filtro_g["Pieza"])
    esperar("con la vida útil anotada, esa, sin «referencia»",
            (_anotada_g["Vida útil (km)"], ns["TEXTO_DE_REFERENCIA"] in _anotada_g["Le falta"]),
            (15000, False))
    ns["c"].execute("UPDATE historial_piezas SET vida_util_km = NULL WHERE vehiculo_id = ?",
                    (_auto_g[0],))
    ns["c"].execute("INSERT INTO historial_piezas (vehiculo_id, descripcion_pieza, km_instalacion) "
                    "VALUES (?, 'Sensor de pastillas', 80000)", (_auto_g[0],))
    _reten_g = next(e for e in ns["estado_de_cada_pieza"](_auto_dict_g)
                    if e["Pieza"] == "Sensor de pastillas")
    esperar("lo que no se cambia por km (el sensor de las pastillas) sigue sin datos",
            (_reten_g["Estado"], _reten_g["Le falta"]), ("⚪ Sin datos", "falta la vida útil"))
    ns["c"].execute("DELETE FROM historial_piezas WHERE vehiculo_id = ? AND "
                    "descripcion_pieza = 'Sensor de pastillas'", (_auto_g[0],))
    ns["conn"].commit()
    # Solo su taller lo anota: con otra cuenta adentro, ni llamando a la función.
    _otro_taller = ns["crear_mecanico"]("Otro Taller De La Patente", "clave-otro-taller-1")
    _presu_g3 = ns["guardar_presupuesto_mecanico"](taller, "", [dict(_items_g[1])], 0,
                                                   patente="AG777KL")
    _id_g3 = ns["c"].execute("SELECT MAX(id) FROM presupuestos_mecanico WHERE mecanico_id = ?",
                             (taller,)).fetchone()[0]
    esperar("con el número de otra cuenta, no es suyo",
            ns["anotar_presupuesto_en_el_auto"](_otro_taller, _id_g3)[0], False)
    _g_cuenta = ns["exigir_que_sea_su_cuenta"].__globals__
    _adentro_real = _g_cuenta["_nivel_de_quien_esta_adentro"]
    _estado_g = dict(st.session_state)
    try:
        _g_cuenta["_nivel_de_quien_esta_adentro"] = lambda: "mecanico"
        st.session_state["mecanico_id"] = _otro_taller
        try:
            ns["anotar_presupuesto_en_el_auto"](taller, _id_g3)
            _pudo_otro = True
        except PermissionError:
            _pudo_otro = False
        esperar("otro taller adentro no puede anotar el presupuesto de este", _pudo_otro, False)
    finally:
        _g_cuenta["_nivel_de_quien_esta_adentro"] = _adentro_real
        st.session_state.clear()
        st.session_state.update(_estado_g)
    # MIS AUTOS (ver autos_del_taller()): los que anotó, con lo próximo que le toca, lo urgente
    # primero; los de otro taller no. Un segundo auto con el aceite vencido (anotado hace 14
    # meses: la referencia es 12) tiene que quedar arriba.
    ns["c"].execute("INSERT INTO vehiculos (patente, marca_auto, modelo_auto, km_actual) "
                    "VALUES ('AH888MN', 'FIAT', 'Palio', 50000)")
    _auto_h = ns["c"].lastrowid
    ns["c"].execute("INSERT INTO historial_piezas (vehiculo_id, descripcion_pieza, km_instalacion, "
                    "fecha_instalacion) VALUES (?, 'Filtro aceite', 50000, "
                    "datetime('now', '-14 months'))", (_auto_h,))
    ns["c"].execute("INSERT INTO presupuestos_mecanico (mecanico_id, items_json, total, patente, "
                    "anotado_en) VALUES (?, '[]', 0, 'AH888MN', datetime('now', '-14 months'))",
                    (taller,))
    ns["conn"].commit()
    _mis_g = ns["autos_del_taller"](taller)
    esperar("mis autos: los que anotó, lo vencido primero, con lo próximo y sin nombres",
            ([a["Patente"] for a in _mis_g], _mis_g[0]["Estado"][:1] if _mis_g else None,
             _mis_g[0]["Lo próximo"] if _mis_g else None, _mis_g[0]["Auto"] if _mis_g else None,
             "Juan" in json.dumps(_mis_g, ensure_ascii=False)),
            (["AH888MN", "AG777KL"], "🔴", "Filtro aceite", "FIAT Palio", False))
    esperar("los autos de un taller no los ve otro",
            ns["autos_del_taller"](_otro_taller), [])
    _portal.session_state["exp_mis_autos"] = True
    _portal.run()
    esperar("en su portal, «🚗 Mis autos» los muestra y dice a cuántos les toca",
            (any("AH888MN" in list(d.value.get("Patente", [])) for d in _portal.dataframe),
             any("ya les toca o les toca pronto" in x.value for x in _portal.caption),
             [e.value for e in _portal.exception]), (True, True, []))
    # EL CARTEL PARA EL MOSTRADOR (ver generar_pdf_cartel_del_auto()): el QR, la dirección
    # tocable, y lo que dice según cómo entra el cliente.
    _cartel = ns["generar_pdf_cartel_del_auto"]()
    esperar("el cartel: un PDF con el QR y la dirección tocable de la consulta del auto",
            (_cartel[:4], b"/Subtype /Image" in _cartel,
             f"/URI ({ns['link_general_de_consulta']()})".encode() in _cartel),
            (b"%PDF", True, True))
    # Y que el QR impreso se lea de verdad y abra la consulta del auto (lo que hace el celular).
    import numpy as _np
    import cv2 as _cv2
    import pypdfium2 as _pdfium
    _hoja = _pdfium.PdfDocument(_cartel)[0].render(scale=2).to_pil()
    _leido, _, _ = _cv2.QRCodeDetector().detectAndDecode(
        _cv2.cvtColor(_np.array(_hoja), _cv2.COLOR_RGB2BGR))
    esperar("el QR del cartel, leído como lo lee el celular, abre la consulta del auto",
            _leido, ns["link_general_de_consulta"]())
    _como_sola = ns["como_entra_el_cliente"]()
    ns["guardar_config"](ns["CLAVE_DEL_AUTO_CON_LA_PATENTE_SOLA"], "no")
    _como_con_numeros = ns["como_entra_el_cliente"]()
    ns["guardar_config"](ns["CLAVE_DEL_AUTO_CON_LA_PATENTE_SOLA"], "")
    esperar("lo que dice el cartel sigue la opción del dueño",
            (_como_sola, "4 números" in _como_con_numeros), ("poné la patente", True))
    # Lo que ve el dueño del auto: lo del taller, sin el nombre de su cliente ni las notas.
    _publico_g, _ = ns["abrir_ficha_publica"]("AG777KL", solo_patente=True)
    _json_g = json.dumps(_publico_g, ensure_ascii=False, default=str)
    esperar("el dueño del auto ve lo que le cambió el taller, sin nombres ni notas",
            (len(_publico_g["historial"]) if _publico_g else None, "Juan" in _json_g,
             "Lo anotó" in _json_g, "Taller Sesión" in _json_g), (3, False, False, False))
    # «🚗 Ver mi auto» en «🔑 Ingresar»: abre su auto con la patente sola, y vuelve.
    for _cerrada_g in ("", "si"):
        ns["guardar_config"](ns["CLAVE_DE_SOLO_CON_CUENTA"], _cerrada_g)
        ns["conn"].commit()
        _dueno = _visitante()
        _dueno.text_input(key="ingreso_patente").set_value("ag 777 kl")
        [b for b in _dueno.button if b.label == "🔎 Ver mi auto"][0].click().run()
        _como = "cerrada" if _cerrada_g else "abierta"
        esperar(f"con la página {_como}, «Ver mi auto» con la patente sola abre su auto",
                (any("Tu auto en El Chavo" in m.value for m in _dueno.markdown),
                 any("Todo lo que se le cambió" in m.value for m in _dueno.markdown),
                 len(_dueno.dataframe) >= 1, [e.value for e in _dueno.exception]),
                (True, True, True, []))
        _dueno.button(key="volver_de_la_consulta").click().run()
        esperar(f"con la página {_como}, «Volver a la página» sale de su auto",
                (any("Tu auto en El Chavo" in m.value for m in _dueno.markdown),
                 "busqueda_input" in [w.key for w in _dueno.text_input],
                 "login_inicial_nombre" in [w.key for w in _dueno.text_input]),
                (False, not _cerrada_g, True))
    ns["guardar_config"](ns["CLAVE_DE_SOLO_CON_CUENTA"], "")
    # La opción la cambia solo el administrador: ni el operador, ni el taller, ni el que no
    # entró, aunque llamen a la función.
    _g_auto = ns["cambiar_como_se_ve_el_auto"].__globals__
    _adentro_auto = _g_auto["_nivel_de_quien_esta_adentro"]
    try:
        for _nivel_g in ("operador", "mecanico", ""):
            _g_auto["_nivel_de_quien_esta_adentro"] = lambda _n=_nivel_g: _n
            try:
                ns["cambiar_como_se_ve_el_auto"](False)
                _pudo_g = True
            except PermissionError:
                _pudo_g = False
            esperar(f"un «{_nivel_g or 'sin entrar'}» no puede cambiar cómo se ve el auto",
                    (_pudo_g, ns["se_ve_el_auto_con_la_patente_sola"]()), (False, True))
    finally:
        _g_auto["_nivel_de_quien_esta_adentro"] = _adentro_auto
    # Con la opción apagada, la patente sola no abre: pide además los 4 números.
    ns["guardar_config"](ns["CLAVE_DEL_AUTO_CON_LA_PATENTE_SOLA"], "no")
    ns["conn"].commit()
    try:
        _apagado = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
        _apagado.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
        _apagado.query_params["auto"] = "AG777KL"
        _apagado.run()
        esperar("apagada la patente sola, pide además los 4 números y no muestra el auto",
                (len(_apagado.text_input), len(_apagado.dataframe),
                 [e.value for e in _apagado.exception]), (2, 0, []))
        # La opción, en 👥 Usuarios: solo el administrador, con su botón.
        _adm_g = _visitante(nivel_usuario="admin", admin_nombre="duenio",
                            pagina_actual="🗂️ Administrar", sub_admin=ns["SUB_ADMIN"][5])
        _adm_g.radio(key="como_se_ve_el_auto").set_value(ns["COMO_SE_VE_EL_AUTO"][0]).run()
        esperar("elegir la opción no la cambia: ofrece guardar",
                (ns["se_ve_el_auto_con_la_patente_sola"](),
                 [b.key for b in _adm_g.button if b.key == "guardar_como_se_ve_el_auto"]),
                (False, ["guardar_como_se_ve_el_auto"]))
        _adm_g.button(key="guardar_como_se_ve_el_auto").click().run()
        esperar("con «Guardar», vuelve la patente sola (y queda anotado quién)",
                (ns["se_ve_el_auto_con_la_patente_sola"](),
                 ns["c"].execute("SELECT usuario FROM registro_de_cambios WHERE entidad_id = ? "
                                 "ORDER BY id DESC LIMIT 1",
                                 (ns["CLAVE_DEL_AUTO_CON_LA_PATENTE_SOLA"],)).fetchone()[0],
                 [e.value for e in _adm_g.exception]), (True, "duenio", []))
    finally:
        ns["guardar_config"](ns["CLAVE_DEL_AUTO_CON_LA_PATENTE_SOLA"], "")
        ns["conn"].commit()

    # 5. La venta a medio armar sobrevive a una recarga, que para la app es una sesión nueva
    # sobre la misma base: al entrar se avisa, 🧾 Ventas ofrece recuperarla —con la cantidad, el
    # precio y el cliente que tenía— y, terminada, no queda nada guardado. A otro no se le
    # ofrece, y la de ayer tampoco. Ver «LA VENTA Y EL PRESUPUESTO A MEDIO ARMAR, A SALVO DE UNA
    # RECARGA».
    c, conn = ns["c"], ns["conn"]
    for nombre in ("rita", "beto"):
        ns["crear_usuario"](nombre, f"clave-{nombre}-1", "operador")
    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('PRUEBA VENTA', 'PROVEEDOR')")
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio, "
              "stock) VALUES ('V100', 'V100', 'FILTRO', ?, 1000, 5)", (c.lastrowid,))
    pid = c.lastrowid
    conn.commit()
    ventas = ns["PAGINAS"][9]

    def sesion_nueva(clave, pagina=None):
        nueva = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
        nueva.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
        nueva.run()
        # Las claves de esta prueba son «clave-<usuario>-1»: el usuario sale de ahí.
        _entrar(nueva, clave.split("-")[1], clave)
        if pagina:
            nueva.session_state["pagina_actual"] = pagina
            nueva.run()
        return nueva

    def guardada(quien):
        return c.execute("SELECT cliente FROM ventas_a_medio_armar WHERE usuario = ?",
                         (quien,)).fetchone()

    def ofrecida(sesion):
        return ([b.label for b in sesion.button if b.label == "↩️ Recuperarla"],
                [t.value for t in sesion.toast if "venta a medio armar" in t.value])

    vta = sesion_nueva("clave-rita-1", ventas)
    vta.session_state["venta_items"] = [dict(ns["item_de_venta"](pid, 3), precio=900.0)]
    vta.session_state["venta_cliente"] = "Juan"
    vta.run()
    esperar("se guarda la venta a medio armar", tuple(guardada("rita") or ()), ("Juan",))
    vta = sesion_nueva("clave-rita-1")                       # recargó la página
    esperar("al entrar, el aviso", len(ofrecida(vta)[1]), 1)
    vta.session_state["pagina_actual"] = ventas
    vta.run()
    esperar("una sesión nueva no la borra antes de contestar", bool(guardada("rita")), True)
    if not ofrecida(vta)[0]:
        fallas.append("🧾 Ventas no ofrece recuperar la venta a medio armar")
        return fallas
    [b for b in vta.button if b.label == "↩️ Recuperarla"][0].click().run()
    esperar("recuperada con su cantidad, su precio y el cliente",
            ([(x["producto_id"], x["cantidad"], x["precio"])
              for x in vta.session_state["venta_items"]], vta.session_state["venta_cliente"]),
            ([(pid, 3, 900.0)], "Juan"))
    otro = sesion_nueva("clave-beto-1", ventas)
    esperar("a otro no se le ofrece", ofrecida(otro), ([], []))
    # QUE NO SE GRABE POR ACCIDENTE (ver esa sección en logica/ventas.py): el botón —o F9—
    # pregunta con el total, y graba recién el «Sí».
    def _de_rita():
        return c.execute("SELECT COUNT(*) FROM ventas WHERE usuario = 'rita' AND anulada = 0"
                         ).fetchone()[0]

    def _boton(clave):
        return [b for b in vta.button if b.key == clave]
    _ventas_antes = _de_rita()
    _boton("venta_terminar")[0].click().run()
    esperar("el botón solo pregunta: no graba nada",
            (_de_rita() - _ventas_antes, len(_boton("venta_confirmar_cierre")),
             any("$2.700" in m.value for m in vta.markdown)), (0, 1, True))
    # Si cambia algo mientras pregunta, vuelve a preguntar.
    vta.number_input(key=f"venta_cant_{pid}").set_value(2).run()
    esperar("cambió la cantidad: deja de preguntar", (len(_boton("venta_confirmar_cierre")),
                                                      len(_boton("venta_terminar"))), (0, 1))
    _boton("venta_terminar")[0].click().run()
    _boton("venta_confirmar_cierre")[0].click().run()
    esperar("con el «Sí», grabada", _de_rita() - _ventas_antes, 1)
    esperar("terminada, no queda guardada", guardada("rita"), None)
    # Me equivoqué: la suya, esperando en la caja, se deshace y vuelve armada.
    _boton("venta_deshacer_la_recien")[0].click().run()
    esperar("deshecha: vuelve armada como estaba, con el cliente",
            (_de_rita() - _ventas_antes,
             [(x["producto_id"], x["cantidad"], x["precio"]) for x in vta.session_state["venta_items"]],
             vta.session_state["venta_cliente"]), (0, [(pid, 2, 900.0)], "Juan"))
    _boton("venta_terminar")[0].click().run()
    _boton("venta_confirmar_cierre")[0].click().run()
    # La misma venta otra vez, enseguida (un doble toque, la página recargada): pide decir que
    # es otra.
    vta.session_state["venta_recien_cerrada"] = None
    vta.session_state["venta_items"] = [dict(ns["item_de_venta"](pid, 2), precio=900.0)]
    vta.run()
    _boton("venta_terminar")[0].click().run()
    esperar("la misma venta enseguida: lo dice y pide confirmarlo",
            ([b.label for b in _boton("venta_confirmar_cierre")],
             any("grabaste esta misma venta" in w.value for w in vta.warning)),
            (["🔁 Sí, es otra venta igual"], True))
    _boton("venta_volver_al_armado")[0].click().run()
    esperar("«Volver» no graba", (_de_rita() - _ventas_antes, len(_boton("venta_terminar"))), (1, 1))
    vta.session_state["venta_items"] = []
    vta.run()
    # CORREGIR UN COBRO desde la caja (ver esa sección en logica/ventas.py): la cajera marcó
    # «Efectivo» y era una transferencia.
    _vc = c.execute("SELECT MAX(id) FROM ventas WHERE usuario = 'rita' AND anulada = 0").fetchone()[0]
    c.execute("""UPDATE ventas SET cobrada = 1, forma_de_pago = 'Efectivo', cobrada_por = 'rita',
                        cobrada_en = datetime('now', 'localtime') WHERE id = ?""", (_vc,))
    conn.commit()
    vta.session_state["pagina_actual"] = ns["PAGINAS"][11]
    vta.session_state["exp_ventas_cierre_caja_hoy"] = True
    vta.run()
    vta.selectbox(key="cobro_a_corregir").set_value(_vc).run()
    esperar("la forma de pago arranca en la que tiene",
            vta.selectbox(key=f"cobro_forma_nueva_{_vc}").value, "Efectivo")
    vta.selectbox(key=f"cobro_forma_nueva_{_vc}").set_value("Transferencia").run()
    _boton("cobro_corregir_forma")[0].click().run()
    esperar("desde la caja: la forma de pago corregida, y a la vista con quién",
            (c.execute("SELECT forma_de_pago FROM ventas WHERE id = ?", (_vc,)).fetchone()[0],
             any("Efectivo → Transferencia" in d.value.to_string() and "rita" in d.value.to_string()
                 for d in vta.dataframe),
             [e.value for e in vta.exception]), ("Transferencia", True, []))
    vta.session_state["exp_ventas_cierre_caja_hoy"] = False
    vta.session_state["pagina_actual"] = ventas
    vta.run()
    c.execute("""INSERT INTO ventas_a_medio_armar (usuario, items, cliente, guardada)
                 VALUES ('rita', ?, '', datetime('now', 'localtime', '-1 day'))""",
              (f'[{{"producto_id": {pid}, "cantidad": 1, "precio": 1}}]',))
    conn.commit()
    esperar("la de ayer no se ofrece", ofrecida(sesion_nueva("clave-rita-1", ventas)), ([], []))
    # Y el presupuesto del Buscador, igual: lo destildado sigue destildado. Recuperar la venta
    # no lo borra: va aparte.
    presu = sesion_nueva("clave-rita-1", ns["PAGINAS"][0])
    presu.session_state["carrito"] = {pid: {"codigo": "V100", "marca": "PRUEBA VENTA",
                                            "descripcion": "FILTRO", "precio": 950,
                                            "cantidad": 2, "se_lleva": False}}
    presu.run()
    presu = sesion_nueva("clave-rita-1")                     # recargó la página
    esperar("al entrar, el aviso del presupuesto",
            len([t for t in presu.toast if "presupuesto a medio armar" in t.value]), 1)
    presu.session_state["pagina_actual"] = ns["PAGINAS"][0]
    presu.run()
    _rec = [b for b in presu.button if b.label == "↩️ Recuperarlo"]
    if not _rec:
        fallas.append("el 🔍 Buscador no ofrece recuperar el presupuesto a medio armar")
        return fallas
    _rec[0].click().run()
    esperar("el presupuesto recuperado, con su cantidad, su precio y lo destildado",
            {k: dict(v) for k, v in presu.session_state["carrito"].items()},
            {pid: {"codigo": "V100", "marca": "PRUEBA VENTA", "descripcion": "FILTRO",
                   "precio": 950, "cantidad": 2, "se_lleva": False}})
    esperar("sin errores en el presupuesto", [e.value for e in presu.exception], [])
    esperar("sin errores en la venta", [e.value for s_ in (vta, otro) for e in s_.exception], [])

    # 6. 🔗 Equivalencias sugeridas: cada lista arranca analizándose ENTERA —la tanda se fijaba
    # con la primera que se abría y al pasar al barrido quedaba en 400 de 6.586—, y lo que sale
    # del análisis (el plan, los abanicos, los grupos por motivo) no se vuelve a armar en cada
    # toque: con el barrido entero eran 899 ms por tildar una casilla.
    for nombre_l in ("LISTA UNO", "LISTA DOS"):
        c.execute("INSERT INTO marcas (nombre, tipo) VALUES (?, 'PROVEEDOR')", (nombre_l,))
    _m1, _m2 = [r[0] for r in c.execute("SELECT id FROM marcas WHERE nombre IN ('LISTA UNO', "
                                        "'LISTA DOS') ORDER BY nombre DESC")]
    for lote_s, cuantos_s, fecha_s in (("GRANDE · 01/10", 450, "2026-10-01"),
                                       ("CHICA · 02/10", 260, "2026-10-02")):
        for i in range(cuantos_s):
            ids_s = []
            for m_s, pref in ((_m1, "U"), (_m2, "D")):
                cod_s = f"{pref}{lote_s[:1]}{i}"
                c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
                          "VALUES (?, ?, ?, ?)", (cod_s, cod_s, f"FILTRO DE ACEITE MOTOR {i}", m_s))
                ids_s.append(c.lastrowid)
            c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, "
                      "lote, fecha) VALUES (?, ?, 'x', ?, ?)", (*sorted(ids_s), lote_s, fecha_s))
    conn.commit()
    rev = sesion_nueva("clave-duenio-1", [p for p in ns["PAGINAS"] if "Estadísticas" in p][0])
    rev.session_state["sub_stats"] = "🔗 Equivalencias sugeridas"
    rev.run()
    esperar("la primera lista, entera", rev.session_state["cuantos_pendientes"], 400)
    _sel = [s_ for s_ in rev.selectbox if s_.key == "lote_en_revision"][0]
    _sel.set_value([o for o in _sel.options if o.startswith("GRANDE")][0].split(" — ")[0]).run()
    esperar("al pasar a la grande, también entera",
            (rev.session_state["cuantos_pendientes"],
             any("Analizados 450 de 450" in str(x.value) for x in rev.caption)), (1000, True))
    _g = ns["plan_de_la_lista"].__globals__
    _plan_original, _veces_plan = _g["plan_de_la_lista"], []
    _g["plan_de_la_lista"] = lambda *a, **k: _veces_plan.append(1) or _plan_original(*a, **k)
    try:
        rev.run()
        rev.run()
    finally:
        _g["plan_de_la_lista"] = _plan_original
    esperar("lo que sale del análisis no se rearma en cada toque", len(_veces_plan), 0)
    # 🤖 El descarte automático: el administrador lo prende (y pide pasar la cola que ya está)
    # y lo apaga. Ver «LO QUE LA APP DESCARTA SOLA».
    [b for b in rev.button if b.key == "btn_descarte_automatico"][0].click().run()
    esperar("prendido, con la cola de ahora pedida",
            (ns["obtener_config"]("descarte_automatico_rojos", ""),
             ns["obtener_config"]("descarte_automatico_pendiente", "")), ("1", "1"))
    [b for b in rev.button if b.key == "btn_descarte_automatico"][0].click().run()
    esperar("y apagado", ns["obtener_config"]("descarte_automatico_rojos", ""), "0")
    # 🕯️ Las bujías que calzan: abierto muestra los grupos y se apaga desde ahí. Ver «LAS
    # BUJÍAS QUE CALZAN, RELACIONADAS SOLAS».
    _mb = [r[0] for r in c.execute("SELECT id FROM marcas WHERE nombre = 'LISTA UNO'")][0]
    for cod_b, desc_b in (("BKR5E", "BUJIA NGK FIAT"), ("BKR6E", "BUJIA NGK FORD")):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
                  "VALUES (?, ?, ?, ?)", (cod_b, cod_b, desc_b, _mb))
    conn.commit()
    rev.session_state["exp_bujias_que_calzan"] = True
    rev.run()
    esperar("el grupo de las dos bujías, a la vista",
            [(f["Calzan igual"], f["Bujías"]) for f in ns["grupos_de_bujias"]()],
            [("M14, largo 19 mm, hexágono 16 mm, asiento plano, común", 2)])
    # El clic del botón de adentro no se prueba acá: el simulador de Streamlit vuelve a cerrar
    # el desplegable perezoso al tocarlo. Lo que hace lo prueba pruebas_de_la_precision.py (82).
    _exp_b = [x for x in rev.expander if "Bujías que calzan" in x.label][0]
    esperar("abierto, con la tabla de los grupos y los dos botones",
            ("Calzan igual" in list(_exp_b.dataframe[0].value.columns),
             {b.key for b in _exp_b.button} >= {"btn_bujias_que_calzan", "btn_deshacer_bujias"}),
            (True, True))
    esperar("sin errores en la revisión", [e.value for e in rev.exception], [])

    # 7. 🕸️ Unidos a varias piezas distintas de una misma lista: se buscan, se mira uno y se le
    # corta un vínculo, que queda anotado como rechazado (ver unidos_a_piezas_distintas()).
    for nombre_l in ("HUB LISTA", "HUB OTRA"):
        c.execute("INSERT INTO marcas (nombre, tipo) VALUES (?, 'PROVEEDOR')", (nombre_l,))
    _ml, _mo = [r[0] for r in c.execute("SELECT id FROM marcas WHERE nombre IN ('HUB LISTA', "
                                        "'HUB OTRA') ORDER BY nombre")]
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) VALUES "
              "('U-1', 'U1', 'SONDA LAMBDA UNIVERSAL', ?)", (_mo,))
    _hub = c.lastrowid
    _piezas_l = []
    for cod_l, desc_l in (("H100", "SONDA LAMBDA FIAT SPORTAGE"), ("H200", "SONDA LAMBDA RENAULT KANGOO"),
                          ("H300", "SONDA LAMBDA FORD KA ZETEC")):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
                  "VALUES (?, ?, ?, ?)", (cod_l, cod_l, desc_l, _ml))
        _piezas_l.append(c.lastrowid)
        c.execute("INSERT INTO equivalencias (producto_a_id, producto_b_id, lote, confianza) "
                  "VALUES (?, ?, 'BARRIDO (automático) · 25/09', 84)", tuple(sorted((_hub, c.lastrowid))))
    conn.commit()
    adm = sesion_nueva("clave-duenio-1", [p for p in ns["PAGINAS"] if "Administrar" in p][0])
    adm.session_state["sub_admin"] = ns["SUB_ADMIN"][4]
    adm.session_state["sub_mantenimiento"] = ns["GRUPOS_MANTENIMIENTO"][1]
    adm.run()
    [b for b in adm.button if b.key == "btn_unidos_a_piezas"][0].click().run()
    esperar("los encuentra", any("1 producto(s)" in w.value for w in adm.warning), True)
    _corte = [m for m in adm.multiselect if str(m.key).startswith("cortar_unido_")][0]
    _corte.set_value([_piezas_l[1]]).run()
    [b for b in adm.button if b.key == "btn_cortar_unido"][0].click().run()
    _par = tuple(sorted((_hub, _piezas_l[1])))
    esperar("cortado y anotado como rechazado",
            (c.execute("SELECT COUNT(*) FROM equivalencias WHERE producto_a_id = ? AND "
                       "producto_b_id = ?", _par).fetchone()[0],
             (c.execute("SELECT decision FROM equivalencias_revisadas WHERE producto_a_id = ? AND "
                        "producto_b_id = ?", _par).fetchone() or [None])[0],
             adm.session_state["unidos_a_piezas"]), (0, "rechazada", []))
    esperar("sin errores en la limpieza", [e.value for e in adm.exception], [])

    # 9. LA COPIA FRENADA: el aviso trae el botón para bajar el backup ahí mismo, sin ir a
    # Backup y config (ver ACCIONES en la salud). Al administrador, y a nadie más.
    ns["guardar_config"]("copia_frenada_sin_cifrar", "2026-10-12 15:56:50")
    ns["invalidar_salud"]()

    def _bajar_backup(sesion):
        return [b.proto.label for b in sesion.get("download_button")
                if "Bajar un backup ahora" in b.proto.label]
    esperar("con la copia frenada, el administrador lo baja desde el aviso",
            _bajar_backup(sesion_nueva("clave-duenio-1")), ["⬇️ Bajar un backup ahora"])
    _rita = sesion_nueva("clave-rita-1")
    esperar("el operador (que entró) no", (_rita.session_state["nivel_usuario"],
                                           _bajar_backup(_rita)), ("operador", []))
    ns["guardar_config"]("copia_frenada_sin_cifrar", "")
    ns["invalidar_salud"]()
    esperar("sin la copia frenada, no está", _bajar_backup(sesion_nueva("clave-duenio-1")), [])

    # 10. LO NUEVO DE ESTA VERSIÓN (ver LO_NUEVO): al administrador una vez; «Entendido» lo
    # guarda, y no vuelve. Al operador, nunca.
    ns["guardar_config"]("lo_nuevo_visto", "")

    def _lo_nuevo(sesion):
        return any(m.value.startswith("**🆕 Lo nuevo**") for m in sesion.markdown)
    _adm_n = sesion_nueva("clave-duenio-1")
    esperar("el administrador ve lo nuevo", _lo_nuevo(_adm_n), True)
    _rita_n = sesion_nueva("clave-rita-1")
    esperar("el operador no", (_rita_n.session_state["nivel_usuario"], _lo_nuevo(_rita_n)),
            ("operador", False))
    [b for b in _adm_n.button if b.key == "lo_nuevo_entendido"][0].click().run()
    esperar("con «Entendido», no vuelve", (_lo_nuevo(_adm_n), _lo_nuevo(sesion_nueva("clave-duenio-1"))),
            (False, False))
    return fallas


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_sesion_")
    os.chdir(carpeta)
    sys.path.insert(0, RAIZ)
    try:
        fallas = probar()
        for f in fallas:
            print("   ✗", f)
        print("✅ sesión: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(RAIZ)
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

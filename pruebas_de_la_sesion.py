"""Pruebas de la sesión con la app real (AppTest): salir no deja nada, y los permisos siguen a
la cuenta.

Uso:
    python3 pruebas_de_la_sesion.py

Las dos las propuso una revisión con ChatGPT:
  · «login A → seleccionar cosas → logout → login B → comprobar que no aparece nada de A»;
  · «admin cambia el rol → misma sesión»: el nivel se guardaba al entrar y no se volvía a mirar.
Ver cerrar_sesion() y nivel_vigente_de_la_sesion() en logica/base.py.

Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import os
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.abspath(__file__))


def _entrar(at, clave):
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
    _entrar(at, "clave-ana-1")
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
    _entrar(at, "clave-duenio-1")
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
    # En la app de internet la ruta se leería en el servidor, no en el teléfono: no se ofrece.
    _en_la_nube = _g["corre_en_streamlit_cloud"]
    _g["corre_en_streamlit_cloud"] = lambda: True
    at.run()
    esperar("en la app de internet no se ofrece leer por ruta",
            [r.options for r in at.radio if "Subir archivo" in r.options], [])
    _g["corre_en_streamlit_cloud"] = _en_la_nube
    [b for b in at.button if b.label == "Salir"][0].click().run()

    # 3. Ana vuelve a entrar; mientras está adentro le cambian el rol, y después la desactivan.
    _entrar(at, "clave-ana-1")
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

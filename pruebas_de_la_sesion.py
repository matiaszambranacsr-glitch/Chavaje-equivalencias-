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

"""La app con miles de cuentas: buscarlas, crearlas de una vez, entrar, y que las pantallas no
se arrastren.

Uso:
    python3 pruebas/pruebas_de_muchas_cuentas.py

Lo pidió el dueño: «se van a sumar más de 2000 cuentas». Ver «CON MILES DE CUENTAS» en
logica/base.py y «ELEGIR UNA CUENTA ENTRE MILES» en logica/deposito.py.
Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import os
import shutil
import sys
import tempfile
import time

CUENTAS = 2000


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

    def sin_freno():
        ns["guardar_config"]("login_fallidos", "0")

    def _que_pasa(hacer):
        try:
            return hacer()
        except ValueError as e:
            return e

    st.session_state["admin_nombre"], st.session_state["nivel_usuario"] = "ana", "admin"
    try:
        # 1. MUCHAS DE UNA VEZ, pegadas de una planilla: con títulos, tabulaciones o punto y
        # coma, importes escritos como en la planilla, y lo que no entra dicho renglón por
        # renglón. Entran sin contraseña.
        pegado = ("Nombre\tCUIT\tLímite\tDescuento\tPlazo\n"
                  "Taller García\t20-11111111-2\t1.500.000\t10\t45\n"
                  "Lubricentro  Sosa\n"
                  "Repuestos Norte;;;5\n"
                  "Mecánica Ñandú; 30-71234567-1; 250000,50\n"
                  "Con CUIT malo\t20-11111111-3\n"
                  "\tsin nombre\n"
                  "Con descuento de más;;;95\n"
                  "taller garcia\n")
        hecho = ns["crear_cuentas_de_una_vez"](pegado)
        garcia = uno("SELECT id FROM mecanicos WHERE nombre = 'Taller García'")
        nandu = uno("SELECT id FROM mecanicos WHERE nombre = 'Mecánica Ñandú'")
        esperar("pegadas de la planilla: cuántas entran, cuáles ya estaban y cuáles no entran",
                (hecho["creadas"], hecho["ya_estaban"], [n for n, _q in hecho["con_problemas"]]),
                (4, ["taller garcia"], [6, 7, 8]))
        esperar("con su límite, descuento y plazo, su CUIT, y sin portal",
                (ns["configuracion_de_cuenta"](garcia), ns["obtener_config"](f"cuit_taller_{garcia}", ""),
                 ns["configuracion_de_cuenta"](nandu)["limite"],
                 uno("SELECT COUNT(*) FROM mecanicos WHERE password_hash <> ''"),
                 uno("SELECT nombre FROM mecanicos WHERE nombre LIKE 'Lubricentro%'")),
                ({"limite": 1500000.0, "dias_de_plazo": 45, "pide_codigo": False, "descuento": 10.0,
                  "cobra_mora": False}, "20111111112", 250000.5, 0, "Lubricentro Sosa"))
        esperar("pegadas otra vez: no se repite ninguna",
                ns["crear_cuentas_de_una_vez"](pegado)["creadas"], 0)

        # 2. UNA CUENTA SIN PORTAL se le vende y va a cuenta sin código de retiro (el código lo
        # genera el taller en su portal: no lo puede tener).
        c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('PRUEBA', 'PROVEEDOR')")
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio, "
                  "stock) VALUES ('MC1', 'MC1', 'FILTRO', ?, 1000, 50)", (c.lastrowid,))
        producto = c.lastrowid
        conn.commit()
        venta, _ = ns["cerrar_venta"]([dict(ns["item_de_venta"](producto, 2))], mecanico_id=garcia,
                                      a_la_caja=True)
        esperar("sin portal: no pide código, y la venta va a su cuenta con su descuento",
                (ns["autorizar_retiro"](garcia, ""), ns["poner_a_cuenta"](venta)[0],
                 ns["estado_de_cuenta"](garcia)["saldo"]), ((True, ""), True, 1800.0))

        # 3. DOS MIL MÁS, y el buscador.
        muchas = "\n".join(f"{('Taller', 'Lubricentro', 'Repuestos', 'Frenos')[i % 4]} "
                           f"{('Pérez', 'Gómez', 'Díaz', 'Ruiz', 'Acosta')[i % 5]} {i:04d}"
                           for i in range(CUENTAS))
        inicio = time.time()
        esperar("dos mil de una vez", ns["crear_cuentas_de_una_vez"](muchas)["creadas"], CUENTAS)
        esperar("y en un momento, no de a una contra todas las demás", time.time() - inicio < 10, True)
        buscar = ns["buscar_cuentas"]
        esperar("sin acentos y en cualquier orden: «gar taller» es Taller García",
                buscar("gar taller"), ([(garcia, "Taller García")], 1))
        esperar("con eñe y acento, escrito sin ellos", buscar("nandu mecanica"),
                ([(nandu, "Mecánica Ñandú")], 1))
        esperar("por su número de cuenta, con o sin #: primero esa",
                (buscar(str(garcia))[0][0], buscar(f"#{nandu}")[0][0]),
                ((garcia, "Taller García"), (nandu, "Mecánica Ñandú")))
        esperar("por el CUIT, con guiones o sin, o por una parte",
                (buscar("20-11111111-2")[0], buscar("1111111")[0][:1], buscar("30712345671")[0]),
                ([(garcia, "Taller García")], [(garcia, "Taller García")],
                 [(nandu, "Mecánica Ñandú")]))
        encontradas, cuantas = buscar("perez")
        esperar("muchas que calzan: unas pocas a la vista, y cuántas son",
                (len(encontradas), cuantas), (ns["CUENTAS_QUE_SE_MUESTRAN"], CUENTAS // 5))
        esperar("primero las que empiezan con lo escrito",
                [n for _i, n in buscar("frenos ru")[0]][0].startswith("Frenos Ruiz"), True)
        esperar("nada escrito, nada; y lo que no está, tampoco",
                (buscar("   "), buscar("zzzz no existe")), (([], 0), ([], 0)))
        inicio = time.time()
        for palabra in ("perez", "taller 0042", "lubri go", "1999", "zz"):
            buscar(palabra)
        esperar("buscar entre dos mil no se nota", time.time() - inicio < 0.5, True)
        esperar("las últimas que atendió quien está en la pantalla, la última primero",
                ns["cuentas_recientes"](), [(garcia, "Taller García")])

        # 4. EL RESUMEN DE TODAS LAS CUENTAS da lo mismo que cuenta por cuenta, en una consulta.
        import random
        azar = random.Random(5)
        ids = [f[0] for f in c.execute("SELECT id FROM mecanicos ORDER BY id LIMIT 300").fetchall()]
        for cuenta in ids[::3]:
            for _ in range(azar.randint(1, 5)):
                c.execute("""INSERT INTO movimientos_de_cuenta (mecanico_id, concepto, importe,
                                                               vence, medio, cheque_fecha, anulado)
                             VALUES (?, 'prueba', ?, date('now', ?), ?, date('now', ?), ?)""",
                          (cuenta, azar.choice([12000, 35000.5, -20000, 8000, -5000]),
                           f"{azar.randint(-60, 30)} days", azar.choice([None, "Cheque", "Efectivo"]),
                           f"{azar.randint(-10, 40)} days", azar.choice([0, 0, 0, 1])))
        conn.commit()
        inicio = time.time()
        resumen = ns["resumen_de_cuentas"]()
        tardo = time.time() - inicio
        distintas = []
        for fila in resumen:
            e = ns["estado_de_cuenta"](fila["ID"])
            if (round(fila["Saldo"], 2), round(fila["Vencido"], 2), fila["Límite"],
                    fila["Disponible"], fila["Cheques en cartera"]) != (
                    round(e["saldo"], 2), round(e["vencido"], 2), e["limite"] or None,
                    e["disponible"], e["cheques_en_cartera"] or None):
                distintas.append(fila["ID"])
        esperar("el resumen de todas, igual que cuenta por cuenta",
                (distintas, len(resumen) >= 100), ([], True))
        esperar("y rápido con dos mil cuentas", tardo < 1.0, True)

        # 5. EL INGRESO, con usuario y contraseña (ver «CADA UNO ENTRA CON SU USUARIO Y SU
        # CONTRASEÑA» en logica/base.py). Con dos mil cuentas no tarda: la contraseña se prueba
        # contra una sola. El taller entra con su número de cuenta o con el nombre de su cuenta.
        ns["crear_usuario"]("beto", "clave-de-beto-1")
        ns["cambiar_password_mecanico"](garcia, "clave-garcia-1")
        # Las dos mil con contraseña (un hash cualquiera: alcanza para medir): si se probara
        # contra todas serían dos minutos.
        c.execute("UPDATE mecanicos SET password_hash = ?, salt = ? WHERE password_hash = ''",
                  ("pbkdf2$100000$" + "ab" * 32, "cd" * 16))
        conn.commit()
        sin_freno()
        inicio = time.time()
        esperar("mal puesta, con dos mil cuentas con portal: no entra, y enseguida",
                ([ns["validar_password"]("cualquier-cosa", con_mecanicos=True, usuario=u)[1]
                  for u in ("beto", str(garcia), "Taller García", "nadie")], time.time() - inicio < 3),
                ([None] * 4, True))
        sin_freno()
        esperar("el taller entra con su número o con el nombre de su cuenta; el empleado, con el suyo",
                ([ns["validar_password"]("clave-garcia-1", con_mecanicos=True, usuario=u)[:2]
                  for u in (str(garcia), f"#{garcia}", "taller garcia", "TALLER GARCÍA")],
                 ns["validar_password"]("clave-de-beto-1", con_mecanicos=True, usuario="Beto")[:2]),
                ([("Taller García", "mecanico")] * 4, ("beto", "operador")))
        sin_freno()
        esperar("con el número de otra cuenta, o el usuario de otro, no entra",
                ([ns["validar_password"]("clave-garcia-1", con_mecanicos=True, usuario=u)[1]
                  for u in (str(nandu), "beto", "Mecánica Ñandú")],
                 ns["validar_password"]("clave-de-beto-1", con_mecanicos=True, usuario=str(garcia))[1]),
                ([None] * 3, None))
        # Dos con la misma contraseña no se cruzan: cada uno entra a lo suyo.
        ns["cambiar_password_mecanico"](nandu, "clave-garcia-1")
        sosa = ns["crear_mecanico"]("Taller Sosa nuevo", "clave-de-beto-1")
        sin_freno()
        esperar("la misma contraseña en dos talleres y en un empleado: cada uno entra a lo suyo",
                [ns["validar_password"](clave, con_mecanicos=True, usuario=u)[0]
                 for clave, u in (("clave-garcia-1", str(garcia)), ("clave-garcia-1", str(nandu)),
                                  ("clave-de-beto-1", str(sosa)), ("clave-de-beto-1", "beto"))],
                ["Taller García", "Mecánica Ñandú", "Taller Sosa nuevo", "beto"])
        sin_freno()
        esperar("una cuenta no va sin nombre",
                [isinstance(e, ValueError) for e in [_que_pasa(lambda: ns["crear_mecanico"]("", "x"))]],
                [True])
        ns["cambiar_password_mecanico"](sosa, "")
        esperar("sacarle el portal: la cuenta sigue, y ya no entra",
                (uno("SELECT activo FROM mecanicos WHERE id = ?", sosa),
                 ns["validar_password"]("clave-de-beto-1", con_mecanicos=True, usuario=str(sosa))[1],
                 ns["configuracion_de_cuenta"](sosa)["pide_codigo"]), (1, None, False))
        sin_freno()

        # 6. EN LA PANTALLA, con las dos mil. El buscador de «🧾 Atendiendo a», Cuentas
        # corrientes, Usuarios y «👥 Cada cuenta» se dibujan sin colgarse y sin la lista de dos
        # mil renglones.
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "app.py"), default_timeout=300)
        at.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
        at.run()
        at.text_input(key="login_inicial_nombre").set_value("duenio")
        at.text_input(key="login_inicial_clave").set_value("clave-duenio-1")
        [b for b in at.button if "Ingresar con contraseña" in b.label][0].click().run()
        at.session_state["pagina_actual"] = ns["PAGINAS"][0]
        at.run()
        esperar("«Atendiendo a»: el buscador en lugar de la lista de dos mil",
                ([x.key for x in at.selectbox if (x.key or "").startswith("cuenta_sel_")],
                 len([x for x in at.text_input if x.key == "cuenta_buscar_buscador"])), ([], 1))
        at.text_input(key="cuenta_buscar_buscador").set_value("gar taller").run()
        _redondeles = [x for x in at.radio if (x.key or "").startswith("cuenta_cual_buscador_")]
        esperar("se escribe una parte y queda la que calza, ya elegida",
                [(len(x.options), x.value) for x in _redondeles], [(1, garcia)])
        [b for b in at.button if b.key == "cuenta_ok_buscador"][0].click().run()
        esperar("y se la atiende", ((at.session_state["cuenta_elegida"] or {}).get("id"),
                                    [e.value for e in at.exception]), (garcia, []))
        at.text_input(key="cuenta_buscar_buscador").set_value("perez").run()
        _redondeles = [x for x in at.radio if (x.key or "").startswith("cuenta_cual_buscador_")]
        esperar("con muchas que calzan: unas pocas, ninguna elegida sola, y dice cuántas más hay",
                ([(len(x.options), x.value) for x in _redondeles],
                 any("más: escribí algo más" in x.value for x in at.caption)),
                ([(ns["CUENTAS_QUE_SE_MUESTRAN"], None)], True))
        for pagina, solapa, que in ((3, ns["SUB_ADMIN"][6], "Cuentas corrientes"),
                                    (3, ns["SUB_ADMIN"][5], "Usuarios")):
            at.session_state["pagina_actual"] = ns["PAGINAS"][pagina]
            at.session_state["sub_admin"] = solapa
            inicio = time.time()
            at.run()
            esperar(f"{que}, con dos mil cuentas: se dibuja, sin la lista de todas y sin tardar",
                    ([e.value for e in at.exception],
                     max([len(x.options) for x in at.selectbox] or [0]) < 100,
                     time.time() - inicio < 8), ([], True, True))
        esperar("Usuarios: el buscador para elegir la cuenta, y cuántas hay",
                (len([x for x in at.text_input if x.key == "cuenta_buscar_gestionar"]),
                 any("cuenta(s)" in x.value and "con portal" in x.value for x in at.caption)),
                (1, True))
        at.session_state["pagina_actual"] = ns["PAGINAS"][9]
        at.session_state["exp_cada_cuenta"] = True
        at.run()
        esperar("«👥 Cada cuenta»: las personas y un renglón para buscar el taller",
                ([e.value for e in at.exception],
                 [len(x.options) < 50 for x in at.selectbox if x.key == "venta_cuenta_sel"]),
                ([], [True]))

        # 7. EL INGRESO, EN LA PANTALLA: sin usuario no entra y lo pide; el taller entra con su
        # número de cuenta y su contraseña, y el link de su portal ya trae el número puesto.
        def pantalla_de_entrada():
            entrada = AppTest.from_file(os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), "app.py"), default_timeout=300)
            entrada.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
            return entrada
        entrada = pantalla_de_entrada().run()
        entrada.text_input(key="login_inicial_clave").set_value("clave-garcia-1")
        [b for b in entrada.button if "Ingresar con contraseña" in b.label][0].click().run()
        esperar("sin el usuario no entra, y le dice que lo ponga",
                ("nivel_usuario" in entrada.session_state
                 and entrada.session_state["nivel_usuario"] or None,
                 any("usuario" in x.value for x in entrada.error),
                 ns["obtener_config"]("login_fallidos", "0")), (None, True, "0"))
        entrada.text_input(key="login_inicial_nombre").set_value(str(garcia))
        entrada.text_input(key="login_inicial_clave").set_value("clave-garcia-1")
        [b for b in entrada.button if "Ingresar con contraseña" in b.label][0].click().run()
        esperar("con su número de cuenta y su contraseña, entra a su portal",
                (entrada.session_state["nivel_usuario"], entrada.session_state["mecanico_id"],
                 [e.value for e in entrada.exception]), ("mecanico", garcia, []))
        del_link = pantalla_de_entrada()
        del_link.query_params["cuenta"] = str(nandu)
        del_link.run()
        esperar("el link del portal trae el número de cuenta puesto como usuario",
                del_link.text_input(key="login_inicial_nombre").value, str(nandu))
        mal = pantalla_de_entrada().run()
        mal.text_input(key="login_inicial_nombre").set_value("duenio")
        mal.text_input(key="login_inicial_clave").set_value("clave-garcia-1")
        [b for b in mal.button if "Ingresar con contraseña" in b.label][0].click().run()
        esperar("el usuario de uno con la contraseña de otro: no entra",
                ("nivel_usuario" in mal.session_state and mal.session_state["nivel_usuario"] or None,
                 [x.value for x in mal.error]), (None, ["Usuario o contraseña incorrectos."]))
        sin_freno()
    finally:
        for k in ("admin_nombre", "nivel_usuario"):
            st.session_state.pop(k, None)
    return fallas


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_muchas_cuentas_")
    try:
        fallas = probar(_cargar_la_logica(carpeta))
        for f in fallas:
            print("   ✗", f)
        print("✅ muchas cuentas: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

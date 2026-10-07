"""Pruebas de los frenos: lo que la app hace cuando algo anda mal.

Uso:
    python3 pruebas_de_los_frenos.py

De la revisión con ChatGPT (puntos 59 a 78):
  · la base con daño: solo el administrador cambia cosas (ver TEXTO_DE_SOLO_LECTURA);
  · los avisos técnicos, solo para el administrador;
  · un proveedor que sigue caído: el descanso crece hasta un día (ver _descansar_por_falla());
  · el catálogo que se achica de golpe: aviso, y la copia buena no se pisa sola;
  · la copia de GitHub se baja y se prueba (ver verificar_la_copia_de_github()).

Corre en una carpeta temporal: nunca toca la base de trabajo, ni sale a internet (lo que
hablaría con GitHub se reemplaza por funciones de prueba).
"""
import os
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta


def _cargar_la_logica(carpeta):
    raiz = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, raiz)
    os.chdir(carpeta)
    import logica
    return logica


def probar(L):
    ns = L.todo_lo_de_la_logica()
    c, conn = ns["c"], ns["conn"]
    g = ns["inflacion_desde"].__globals__
    fallas = []

    def esperar(nombre, real, esperado):
        if real != esperado:
            fallas.append(f"{nombre}: dio {real!r}, se esperaba {esperado!r}")

    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('PRUEBA', 'PROVEEDOR')")
    marca = c.lastrowid
    for i in range(300):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio, "
                  "stock) VALUES (?, ?, 'FILTRO', ?, 1000, 2)", (f"F{i:04d}", f"F{i:04d}", marca))
    conn.commit()

    # 1. La base con daño: el empleado no cambia nada; el administrador sí.
    originales = {k: g[k] for k in ("_nivel_de_quien_esta_adentro", "hay_claves_configuradas",
                                    "es_admin", "config_github", "subir_backup_a_github",
                                    "bajar_la_copia_de_github")}
    g["hay_claves_configuradas"] = lambda: True

    def puede(nivel):
        g["_nivel_de_quien_esta_adentro"] = lambda: nivel
        try:
            ns["exigir_nivel"]("empleado", "cambiar precios")
            return True
        except PermissionError:
            return False
    try:
        esperar("sana: el empleado puede", puede("operador"), True)
        ns["guardar_config"]("base_danada", "07/10 10:00 — *** in database main ***")
        esperar("con daño: el empleado no", puede("operador"), False)
        esperar("con daño: el administrador sí", puede("admin"), True)
        g["es_admin"] = lambda: False
        esperar("con daño: solo lectura para el empleado", ns["modo_solo_lectura"](), True)
        g["es_admin"] = lambda: True
        esperar("con daño: no para el administrador", ns["modo_solo_lectura"](), False)

        # 2. Los avisos técnicos van marcados para el administrador; los demás no.
        problemas = ns["diagnostico_de_salud"]()
        dano = [p for p in problemas if "daño" in p["titulo"]]
        esperar("el aviso de la base con daño es solo para el administrador",
                [p["solo_admin"] for p in dano], [True])
        esperar("todos los avisos dicen para quién son",
                all("solo_admin" in p for p in problemas), True)
        ns["guardar_config"]("base_danada", "")
        esperar("arreglada: el empleado vuelve a poder", puede("operador"), True)
    finally:
        g.update({k: v for k, v in originales.items()
                  if k in ("_nivel_de_quien_esta_adentro", "hay_claves_configuradas", "es_admin")})

    # 3. El descanso por falla crece: 1 h, 2 h, 4 h… hasta un día; y vuelve a una hora si anduvo.
    t0 = datetime(2026, 10, 7, 10, 0)
    minutos, ahora = [], t0
    for _ in range(7):
        m = ns["_descansar_por_falla"]("prueba", ahora=ahora)
        minutos.append(m)
        ahora += timedelta(minutes=m + 5)        # falla otra vez apenas termina el descanso
    esperar("el descanso crece hasta un día", minutos, [60, 120, 240, 480, 960, 1440, 1440])
    esperar("después de andar bien, vuelve a una hora",
            ns["_descansar_por_falla"]("prueba", ahora=ahora + timedelta(days=3)), 60)

    # 4. El catálogo que se achica de golpe.
    ayer, hoy = date(2030, 1, 6), date(2030, 1, 7)
    esperar("la primera foto no avisa", ns["cambio_anormal_del_catalogo"](ayer)[0], [])
    c.execute("DELETE FROM productos WHERE id IN (SELECT id FROM productos LIMIT 250)")
    conn.commit()
    cambios, desde = ns["cambio_anormal_del_catalogo"](hoy)
    esperar("300 → 50 productos: avisa", (cambios[:1], desde), (["productos 300 → 50"], "06/01"))
    esperar("y las unidades en stock", any("stock" in x for x in cambios), True)
    esperar("una caída chica no avisa",
            ns["cambio_anormal_del_catalogo"](hoy + timedelta(days=1))[0], [])

    # 5. Y la copia buena no se pisa sola. Lo que habla con GitHub se reemplaza.
    subidas = []
    try:
        g["config_github"] = lambda: {"repo": "prueba/prueba", "token": "x", "rama": "otra",
                                      "archivo": "copia.db"}
        g["subir_backup_a_github"] = lambda datos, mensaje: (subidas.append(datos) or True, "ok")
        ns["guardar_config"]("huella_copia_github", "vieja")
        ns["guardar_config"]("productos_en_la_copia", "1000")
        ok, texto = ns["subir_la_copia_si_cambio"]()
        esperar("1000 → 50: no se sube sola", (ok, "bajó de 1.000 a 50" in texto, len(subidas)),
                (False, True, 0))
        ok, _ = ns["subir_la_copia_si_cambio"](aunque_no_haya_cambios=True)
        esperar("con el botón, sí", (ok, len(subidas)), (True, 1))
        esperar("y ahora cuenta desde la nueva", ns["obtener_config"]("productos_en_la_copia"), "50")

        # 6. La prueba de recuperación: baja la copia aparte y mira que sea la última.
        huella, datos = ns["copia_para_github"]("")

        def bajar(destino=None):
            with open(destino, "wb") as f:
                f.write(datos)
            return destino
        g["bajar_la_copia_de_github"] = bajar
        ns["guardar_config"]("huella_copia_github", huella)
        ok, detalle = ns["verificar_la_copia_de_github"]()
        esperar("la copia se puede recuperar", (ok, "50 productos" in detalle), (True, True))
        esperar("verificada hace un rato: no toca", ns["toca_verificar_la_copia"](), False)
        esperar("al día siguiente, sí",
                ns["toca_verificar_la_copia"](datetime.now() + timedelta(hours=25)), True)
        ns["guardar_config"]("huella_copia_github", "otra")
        ok, detalle = ns["verificar_la_copia_de_github"]()
        esperar("no es la última que se subió", (ok, "huella" in detalle), (False, True))
        esperar("falló: se reintenta en dos horas",
                ns["toca_verificar_la_copia"](datetime.now() + timedelta(hours=3)), True)
        g["bajar_la_copia_de_github"] = lambda destino=None: None
        esperar("no se pudo bajar", ns["verificar_la_copia_de_github"]()[0], False)
        ns["guardar_config"]("base_danada", "")
        problemas = ns["diagnostico_de_salud"]()
        esperar("el aviso de la copia que no se recupera",
                [p["solo_admin"] for p in problemas if "recuperación" in p["titulo"]], [True])
        esperar("y nada quedó tirado en la carpeta",
                [f for f in os.listdir(".") if f.endswith(".verificar")], [])
    finally:
        g.update(originales)

    # 7. El ingreso de los mecánicos pasa por el mismo freno de intentos que el resto.
    ns["crear_mecanico"]("Taller Freno", "clave-del-taller-7")
    ns["guardar_config"]("login_fallidos", "8")
    ns["guardar_config"]("login_ultimo_fallo", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    nombre, nivel, error = ns["validar_password"]("clave-del-taller-7", con_mecanicos=True)
    esperar("frenado: ni la clave correcta de un taller entra", (nivel, bool(error)), (None, True))
    ns["guardar_config"]("login_fallidos", "1")
    nombre, nivel, error = ns["validar_password"]("clave-del-taller-7", con_mecanicos=True)
    esperar("sin freno, el taller entra", (nombre, nivel), ("Taller Freno", "mecanico"))
    esperar("y acertar reinicia la cuenta de fallos", ns["obtener_config"]("login_fallidos"), "0")
    ns["validar_password"]("otra-clave-cualquiera", con_mecanicos=True)
    esperar("una clave equivocada cuenta como fallo", ns["obtener_config"]("login_fallidos"), "1")
    esperar("la clave de un taller no autoriza acciones adentro",
            ns["validar_password"]("clave-del-taller-7")[1], None)

    # 8. Los errores: sin datos sensibles, con categoría, renglón y código.
    tapado = ns["tapar_lo_sensible"](
        "GET https://api.x.com/v1?key=AIzaSyA1234567890abcdefghijk&q=filtro token=abc123 "
        "Authorization: Bearer ghp_ABCdef123456 https://ana:secreto@portal.com/x password=hola")
    esperar("lo sensible se tapa", [x for x in ("AIzaSyA123", "abc123", "ghp_ABCdef", "secreto",
                                                 "hola") if x in tapado], [])
    esperar("y lo demás queda", ("q=filtro" in tapado, "api.x.com" in tapado), (True, True))
    try:
        raise ValueError("algo con password=1234 adentro")
    except ValueError as _e:
        ns["anotar_error"]("prueba/renglon", _e, codigo="BUS-0001")
    ultimo = g["_ULTIMOS_ERRORES"][-1]
    esperar("el error anotado: tapado, con renglón y código",
            ("1234" in ultimo["detalle"], ultimo["lugar"].startswith("pruebas_de_los_frenos.py:"),
             ultimo["codigo"]), (False, True, "BUS-0001"))
    categorias = {d: ns["categoria_del_error"]({"donde": d, "tipo": tipo}) for d, tipo in (
        ("_trabajo_de_fondo/fotos", "ConnectionError"), ("cualquiera", "OperationalError"),
        ("vigilar_la_copia", "ValueError"), ("tasas_de_referencia", "KeyError"),
        ("nivel principal", "KeyError"), ("exigir_nivel", "PermissionError"))}
    esperar("cada error en su categoría", [v.split(" ", 1)[1] for v in categorias.values()],
            ["Internet y proveedores", "Base de datos", "Copias", "Internet y proveedores",
             "Pantallas y otros", "Ingreso y permisos"])
    esperar("el código de error se puede dictar",
            bool(__import__("re").fullmatch(r"BUS-[0-9A-F]{4}", ns["codigo_de_error"]("BUS"))), True)

    # 9. Las búsquedas viejas se borran; las del último año quedan.
    c.execute("INSERT INTO historial_busquedas (termino, usuario, fecha) VALUES "
              "('viejo', 'ana', datetime('now', '-400 days')), ('nuevo', 'ana', datetime('now'))")
    conn.commit()
    esperar("se borra la de hace más de un año", ns["borrar_busquedas_viejas"](), 1)
    esperar("queda la de hoy", [r[0] for r in c.execute("SELECT termino FROM historial_busquedas")],
            ["nuevo"])

    # 10. El mismo presupuesto dos veces seguidas (doble toque) se guarda una sola vez.
    taller = c.execute("SELECT id FROM mecanicos").fetchone()[0]
    items = [{"codigo": "F0001", "precio": 1000, "cantidad": 2}]
    for _ in range(3):
        ns["guardar_presupuesto_mecanico"](taller, "Juan", items, 500)
    ns["guardar_presupuesto_mecanico"](taller, "Juan", items, 800)
    esperar("doble toque: uno solo; otro distinto, sí",
            c.execute("SELECT COUNT(*) FROM presupuestos_mecanico").fetchone()[0], 2)

    # 11. La consistencia del catálogo encuentra lo que se le pone.
    c.execute("UPDATE productos SET descripcion = '' WHERE id = (SELECT MIN(id) FROM productos)")
    a, b = [r[0] for r in c.execute("SELECT id FROM productos LIMIT 2")]
    c.execute("INSERT INTO equivalencias (producto_a_id, producto_b_id, lote) VALUES (?, ?, 'X')", (a, b))
    c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id) VALUES (?, ?)", (a, b))
    conn.commit()
    chequeo = {r["Chequeo"]: r["Problemas"] for r in ns["chequear_integridad_bd"]()}
    esperar("sin descripción y pendiente ya aprobado",
            (chequeo["Productos sin descripción"], chequeo["Vínculos pendientes que ya están aprobados"],
             chequeo["Equivalencias de un producto consigo mismo"]), (1, 1, 0))
    return fallas


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_frenos_")
    try:
        fallas = probar(_cargar_la_logica(carpeta))
        for f in fallas:
            print("   ✗", f)
        print("✅ frenos: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

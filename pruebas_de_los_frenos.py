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
    total_antes = [p["Total"] if "Total" in p else p.get("total")
                   for p in ns["listar_presupuestos_mecanico"](taller)]
    c.execute("UPDATE productos SET precio = precio * 2")
    conn.commit()
    esperar("un presupuesto guardado no cambia si cambia el precio",
            [p["Total"] if "Total" in p else p.get("total")
             for p in ns["listar_presupuestos_mecanico"](taller)], total_antes)

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

    # 12. Cada cuenta con su clave: la contraseña sola dice quién entra.
    def repetida(funcion, *args):
        try:
            funcion(*args)
            return False
        except ValueError:
            return True
    esperar("un taller con la clave de otro taller", repetida(ns["crear_mecanico"], "Otro Taller",
                                                              "clave-del-taller-7"), True)
    esperar("un empleado con la clave de un taller", repetida(ns["crear_usuario"], "zoe",
                                                              "clave-del-taller-7"), True)
    esperar("con una clave nueva, sí", repetida(ns["crear_usuario"], "zoe", "clave-de-zoe-1"), False)
    zoe = c.execute("SELECT id FROM usuarios WHERE nombre = 'zoe'").fetchone()[0]
    esperar("cambiarle la clave a la de un taller, no",
            repetida(ns["cambiar_password_usuario"], zoe, "clave-del-taller-7"), True)
    esperar("volver a ponerle la suya, sí",
            repetida(ns["cambiar_password_usuario"], zoe, "clave-de-zoe-1"), False)

    # 13. Completar medidas no pisa lo que alguien cargó a mano mientras se revisaba.
    pid = c.execute("SELECT MAX(id) FROM productos").fetchone()[0]
    fila = {"_id": pid, "_nuevas": {"diametro_interno": 35, "ancho": 7}}
    c.execute("UPDATE productos SET diametro_interno = 40 WHERE id = ?", (pid,))
    conn.commit()
    esperar("se completa solo lo vacío", (ns["aplicar_medidas_deducidas"]([fila]),
            tuple(c.execute("SELECT diametro_interno, ancho FROM productos WHERE id = ?",
                            (pid,)).fetchone())), (1, (40, 7)))
    esperar("si ya está todo cargado, no cuenta como completado",
            ns["aplicar_medidas_deducidas"]([fila]), 0)

    # 14. El mismo remito no suma el stock dos veces.
    c.execute("UPDATE productos SET stock = 5 WHERE id = ?", (pid,))
    conn.commit()
    remito = [{"_producto_id": pid, "Cantidad": 3}, {"Código": "NO-ESTA", "Cantidad": 9}]
    esperar("el remito se suma una vez", (ns["aplicar_carga_remito"](remito),
                                          ns["aplicar_carga_remito"](remito)), (1, None))
    esperar("y el stock quedó en 5 + 3", c.execute("SELECT stock FROM productos WHERE id = ?",
                                                   (pid,)).fetchone()[0], 8)
    esperar("otro remito distinto, sí", ns["aplicar_carga_remito"](
        [{"_producto_id": pid, "Cantidad": 2}]), 1)

    # 15. Fusionar con un producto que otra sesión ya borró: no hace nada y lo dice.
    esperar("fusionar con uno que ya no está", ns["fusionar_productos"](999999, pid), False)

    # 15b. Precio, stock y costo: lo que otro cambió mientras se editaba no se pisa.
    c.execute("UPDATE productos SET precio = 1000, stock = 10, precio_costo = 600 WHERE id = ?",
              (pid,))
    conn.commit()

    def estado():
        return tuple(c.execute("SELECT precio, stock, precio_costo FROM productos WHERE id = ?",
                               (pid,)).fetchone())
    vio = {"precio_mostrado": 1000, "stock_mostrado": 10, "costo_mostrado": 600}
    # A abrió con 1000/10/600. B sube el precio a 1200. A cambia solo el stock a 12.
    c.execute("UPDATE productos SET precio = 1200 WHERE id = ?", (pid,))
    conn.commit()
    esperar("A guarda el stock: se guarda", ns["actualizar_precio_stock"](pid, 1000, 12, 600, **vio), True)
    esperar("y el precio de B queda", estado(), (1200, 12, 600))
    # B vende (stock 12 → 9). A, que todavía ve 12... cambia el precio a 1300.
    c.execute("UPDATE productos SET stock = 9 WHERE id = ?", (pid,))
    conn.commit()
    vio = {"precio_mostrado": 1200, "stock_mostrado": 12, "costo_mostrado": 600}
    esperar("A cambia el precio: se guarda", ns["actualizar_precio_stock"](pid, 1300, 12, 600, **vio), True)
    esperar("y el stock de la venta queda", estado(), (1300, 9, 600))
    # Los dos cambian el mismo campo: el segundo no pisa, y lo dice.
    c.execute("UPDATE productos SET precio_costo = 650 WHERE id = ?", (pid,))
    conn.commit()
    vio = {"precio_mostrado": 1300, "stock_mostrado": 9, "costo_mostrado": 600}
    esperar("los dos cambian el costo: no se pisa",
            ns["actualizar_precio_stock"](pid, 1300, 9, 700, **vio), "costo_cambio")
    esperar("queda el del otro", estado(), (1300, 9, 650))
    esperar("dos campos a la vez",
            ns["actualizar_precio_stock"](pid, 1400, 3, 650, precio_mostrado=1250, stock_mostrado=8,
                                          costo_mostrado=650), "precio_cambio,stock_cambio")

    # 16. IDA Y VUELTA DE UN BACKUP: lo que importa del negocio, backup, borrar todo, restaurar
    # y comparar tabla por tabla. Dos veces: el backup tal cual y como va a GitHub (comprimido y
    # cifrado). Y uno dañado no toca nada.
    import gzip
    import io
    criticas = {
        "productos": "SELECT id, codigo_clean, marca_id, precio, stock, descripcion FROM productos",
        "marcas": "SELECT id, nombre, tipo FROM marcas",
        "equivalencias": "SELECT producto_a_id, producto_b_id, lote FROM equivalencias",
        "pendientes": "SELECT producto_a_id, producto_b_id FROM equivalencias_pendientes",
        "usuarios": "SELECT id, nombre, rol, activo FROM usuarios",
        "mecanicos": "SELECT id, nombre, activo FROM mecanicos",
        "cuentas": "SELECT * FROM cuentas_de_taller",
        "presupuestos": "SELECT id, mecanico_id, items_json, total FROM presupuestos_mecanico",
    }

    def foto():
        return {k: sorted(tuple(r) for r in c.execute(q)) for k, q in criticas.items()}
    ns["configurar_cuenta_de_taller"](taller, 50000, 15, False, 10, cobra_mora=True)
    antes = foto()
    esperar("hay datos para probar", all(antes[k] for k in ("productos", "equivalencias",
                                                            "usuarios", "mecanicos", "cuentas")), True)
    crudo = ns["generar_backup_sin_fotos"]()
    g["secretos_app"] = lambda: {"clave_copia": "una-frase-de-prueba-larga"}
    try:
        como_en_github = ns["cifrar_copia"](gzip.compress(crudo))
        esperar("el de GitHub va cifrado", como_en_github[:4] != crudo[:4], True)
        for nombre, contenido in (("tal cual", crudo), ("comprimido y cifrado", como_en_github)):
            for tabla in ("equivalencias_pendientes", "equivalencias", "presupuestos_mecanico",
                          "cuentas_de_taller", "productos"):
                c.execute(f"DELETE FROM {tabla}")
            conn.commit()
            esperar(f"{nombre}: la base quedó vacía", c.execute(
                "SELECT COUNT(*) FROM productos").fetchone()[0], 0)
            control = ns["restaurar_backup"](io.BytesIO(contenido))
            esperar(f"{nombre}: restaurada y sana", (control["sana"], control["productos"]),
                    (True, len(antes["productos"])))
            esperar(f"{nombre}: integrity_check", c.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            despues = foto()
            esperar(f"{nombre}: todo igual que antes",
                    [k for k in criticas if despues[k] != antes[k]], [])
        # Un backup dañado (cortado a la mitad) no entra y no toca nada.
        try:
            ns["restaurar_backup"](io.BytesIO(crudo[:len(crudo) // 2]))
            entro = True
        except ValueError:
            entro = False
        esperar("uno cortado a la mitad no entra", entro, False)
        esperar("y la base sigue como estaba", foto() == antes, True)
    finally:
        g.update(originales)
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

"""Las horas en TODAS las pantallas: con todas las fechas guardadas a las 01:30 UTC (las 22:30 de
acá), en lo que se ve no puede aparecer «01:30» (la hora del servidor, sin pasar a la de acá) ni
«19:30» (pasada dos veces). Y la hora buena, «22:30», tiene que verse en las pantallas que
muestran fechas (si no, la prueba no estaría mirando nada).

Uso:
    python3 pruebas/pruebas_de_las_horas.py              (una base de prueba con datos)
    python3 pruebas/pruebas_de_las_horas.py --base <copia de la base real>

Por qué: la app guarda en UTC y muestra la hora de acá; las tablas convierten solas
(filas_legibles()) y los textos con fecha_legible(). En noviembre de 2026 se encontraron fechas
de textos con la hora del servidor y, al corregirlas, quince tablas quedaron seis horas atrás:
las pruebas miraban las funciones y no la pantalla. Esta mira la pantalla entera.

Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import os
import re
import shutil
import sqlite3
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Hoy a las 22:30 de acá (la 01:30 UTC de mañana): «hoy» para que entren también las ventas y
# el cierre del día, que muestran solo las de hoy. Se arma en probar(), con el reloj de la app.
NOCHE = None
_COLUMNAS_CON_HORA = re.compile(r"fecha\w*|\w+_en|cuando|momento|ultimo_ingreso|guardada")
_HORA_MAL = re.compile(r"\b(01:30|19:30)\b")
# Las que tienen que mostrar la hora buena con los datos que se cargan acá.
_TIENEN_QUE_MOSTRARLA = ("💵 Caja", "🗂️ Administrar → 💳 Cuentas corrientes",
                         "📊 Estadísticas → 📌 Para pedir",
                         "🗂️ Administrar → 🧹 Mantenimiento → 🩺 Estado y papelera",
                         "🚗 Vehículos → AB 999 HH")


def _todo_a_la_noche(c, noche):
    """Toda fecha con hora de toda tabla, a las 01:30 UTC. Los días solos (vencimientos,
    cheques) no se tocan. Las tablas que no se dejan corregir (el historial) se cambian igual:
    es una copia."""
    for (tabla,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' "
                              "AND name NOT LIKE 'sqlite_%'").fetchall():
        for col in c.execute(f"PRAGMA table_info('{tabla}')").fetchall():
            if not _COLUMNAS_CON_HORA.fullmatch(col[1]):
                continue
            consulta = (f"UPDATE '{tabla}' SET {col[1]} = ? "
                        f"WHERE {col[1]} IS NOT NULL AND length({col[1]}) > 10")
            try:
                c.execute(consulta, (noche,))
            except sqlite3.IntegrityError:
                for (disparador,) in c.execute("SELECT name FROM sqlite_master WHERE "
                                               "type='trigger' AND tbl_name = ?", (tabla,)).fetchall():
                    c.execute(f"DROP TRIGGER IF EXISTS '{disparador}'")
                c.execute(consulta, (noche,))


def _cargar_datos(ns, noche):
    """Lo que una base nueva no tiene: ventas, una cuenta con movimientos, un auto con una pieza,
    una consulta de un cliente que ahora hay, un chat."""
    c = ns["c"]
    c.execute("INSERT OR IGNORE INTO marcas (nombre, tipo) VALUES ('MARCA HORAS', 'PROVEEDOR')")
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, stock, precio) "
              "SELECT 'HOR1', 'HOR1', 'FILTRO DE HORAS', id, 5, 1000 FROM marcas "
              "WHERE nombre = 'MARCA HORAS'")
    producto = c.lastrowid
    cuenta = ns["crear_mecanico"]("Taller De Las Horas")
    c.execute("INSERT INTO movimientos_de_cuenta (mecanico_id, concepto, importe, anulado) "
              "VALUES (?, 'venta', 500, 0)", (cuenta,))
    c.execute("INSERT INTO ventas (fecha, usuario, forma_de_pago, total, cobrada, anulada, "
              "cobrada_en) VALUES (datetime('now'), 'duenio', 'Efectivo', 1500, 1, 0, "
              "datetime('now'))")
    c.execute("INSERT INTO ventas (fecha, usuario, forma_de_pago, total, cobrada, anulada) "
              "VALUES (datetime('now'), 'duenio', 'Efectivo', 900, 0, 0)")
    ns["anotar_consulta_cliente"]("Cliente De Las Horas", "11 4567-8901", producto_id=producto,
                                  codigo="HOR1", descripcion="FILTRO")
    auto = ns["get_or_create_vehiculo"]("AB 999 HH", "Dueño De Las Horas", "11 4567-8901",
                                        "VW", "Gol")
    c.execute("INSERT INTO historial_piezas (vehiculo_id, descripcion_pieza, km_instalacion) "
              "VALUES (?, 'Filtro de aceite', 50000)", (auto,))
    ns["guardar_mensaje_de_afuera"]({"canal": "whatsapp", "chat": "5491145678901",
                                     "nombre": "Chat De Las Horas", "id": "horas-1",
                                     "texto": "hola", "entra": True, "cuando": noche})
    c.execute("INSERT INTO papelera (tipo, resumen, eliminado_por, datos_json) "
              "VALUES ('producto', 'algo borrado', 'duenio', '{}')")


def _lo_que_se_ve(at):
    """(tipo, texto) de todo lo que hay en la pantalla: textos, botones, desplegables, opciones
    y tablas (como se dibujan, ya pasadas por filas_legibles())."""
    for tipo in ("markdown", "caption", "text", "info", "warning", "success", "error",
                 "subheader", "header", "title"):
        for e in getattr(at, tipo, []):
            yield tipo, str(e.value)
    for b in at.button:
        yield "botón", str(b.label)
    for e in at.expander:
        yield "desplegable", str(getattr(e, "label", ""))
    for s in list(at.selectbox) + list(at.radio):
        for o in (s.options or []):
            yield "opción", str(o)
    for d in at.dataframe:
        try:
            yield "tabla", d.value.to_string()
        except (AttributeError, ValueError):
            continue


def probar():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
    at.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
    at.run()
    at.text_input(key="login_inicial_nombre").set_value("duenio")
    at.text_input(key="login_inicial_clave").set_value("clave-duenio-1")
    [b for b in at.button if "Ingresar con contraseña" in b.label][0].click().run()
    ns = sys.modules["logica"].todo_lo_de_la_logica()
    from datetime import datetime, time
    noche = ns["utc_de_la_hora_de_aca"](datetime.combine(ns["hoy_aca"](), time(22, 30))
                                        ).strftime("%Y-%m-%d %H:%M:%S")
    _cargar_datos(ns, noche)
    _todo_a_la_noche(ns["c"], noche)
    ns["conn"].commit()
    mal, bien, rotas = {}, set(), []
    # Cada pantalla y solapa; además, cada grupo de 🧹 Mantenimiento (ahí está la papelera) y la
    # ficha del auto cargado en 🚗 Vehículos (lo cambiado, cuándo).
    lugares = []
    for pagina in ns["ORDEN_DE_LAS_PAGINAS"]:
        solapas, clave = ns["SOLAPAS_DE_LA_PAGINA"].get(pagina, ([None], None))
        for solapa in solapas:
            lugares.append((pagina, {clave: solapa} if clave else {},
                            pagina + (f" → {solapa}" if solapa else "")))
    _mant = ns["SUB_ADMIN"][4]
    for grupo in ns["GRUPOS_MANTENIMIENTO"]:
        lugares.append((ns["PAGINAS"][3], {"sub_admin": _mant, "sub_mantenimiento": grupo},
                        f"{ns['PAGINAS'][3]} → {_mant} → {grupo}"))
    lugares.append((ns["PAGINAS"][6], {"patente_buscar": "AB999HH"},
                    f"{ns['PAGINAS'][6]} → AB 999 HH"))
    # Dos pasadas: en el celular (lo que AppTest elige solo) y en la computadora. La prueba de
    # las pantallas mira solo el celular; acá también se ve si algo se rompe en la otra vista.
    _vistas = ns["VISTAS"]
    lugares = [(p, {"modo_vista": _vistas[0], **e}, d) for p, e, d in lugares] + [
        (p, {"modo_vista": _vistas[1], **e}, f"{d} (computadora)") for p, e, d in lugares]
    for pagina, estado, donde in lugares:
        at.session_state["pagina_actual"] = pagina
        for _clave, _valor in estado.items():
            at.session_state[_clave] = _valor
        at.run()
        if at.exception:
            rotas.append(donde)
            continue
        for tipo, texto in _lo_que_se_ve(at):
            if "22:30" in texto:
                bien.add(donde)
            for m in _HORA_MAL.finditer(texto):
                mal.setdefault(donde, set()).add(
                    f"[{tipo}] …{texto[max(0, m.start() - 60):m.end() + 15]}…"
                    .replace("\n", " "))
    fallas = [f"{donde}: hora mal: " + " | ".join(sorted(cosas)[:3])
              for donde, cosas in mal.items()]
    fallas += [f"{donde}: se rompió" for donde in rotas]
    fallas += [f"{donde}: no muestra la hora buena (22:30): la prueba no estaría mirando nada"
               for donde in _TIENEN_QUE_MOSTRARLA
               + tuple(f"{x} (computadora)" for x in _TIENEN_QUE_MOSTRARLA) if donde not in bien]
    return fallas, sorted(bien)


def main():
    os.environ["EQUIVALENCIAS_SIN_TAREAS_DE_FONDO"] = "1"
    carpeta = tempfile.mkdtemp(prefix="pruebas_horas_")
    if "--base" in sys.argv:
        shutil.copy(os.path.abspath(sys.argv[sys.argv.index("--base") + 1]),
                    os.path.join(carpeta, "equivalencias_app.db"))
    os.chdir(carpeta)
    sys.path.insert(0, RAIZ)
    try:
        fallas, bien = probar()
        for f in fallas:
            print("   ✗", f[:300])
        if "-v" in sys.argv:
            print("   la muestran:", ", ".join(bien))
        print(f"✅ horas: en ninguna pantalla con la hora del servidor ni corrida dos veces, en el "
              f"celular ni en la computadora ({len(bien)} muestran la de acá)"
              if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(RAIZ)
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

"""Pruebas del buscador con la app real (AppTest): una búsqueda que falla no se confunde con
«no hay», una letra sola no busca, y cada búsqueda queda medida con su código.

Uso:
    python3 pruebas_del_buscador.py

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

RAIZ = os.path.dirname(os.path.abspath(__file__))


def probar():
    from streamlit.testing.v1 import AppTest
    fallas = []

    def esperar(nombre, real, esperado):
        if real != esperado:
            fallas.append(f"{nombre}: dio {real!r}, se esperaba {esperado!r}")

    at = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
    at.run()
    ns = sys.modules["logica"].todo_lo_de_la_logica()
    c, conn = ns["c"], ns["conn"]
    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('PRUEBA', 'PROVEEDOR')")
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
              "VALUES ('F100', 'F100', 'FILTRO DE ACEITE', ?)", (c.lastrowid,))
    conn.commit()
    g = ns["inflacion_desde"].__globals__

    def buscar(texto):
        at.text_input(key="busqueda_input").set_value(texto)
        [b for b in at.button if "Buscar Equivalencias" in b.label][0].click().run()

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

    # 3. Los números: mediana y P95 de lo anotado.
    g["del_proceso"]("mediciones_de_busqueda", list).clear()
    for ms in range(1, 101):
        g["anotar_busqueda"]("código", "x", ms / 1000, 0 if ms % 4 == 0 else 3)
    r = g["resumen_de_las_busquedas"]()
    esperar("mediana", round(r["mediana_ms"]), 51)
    esperar("P95", round(r["p95_ms"]), 95)
    esperar("sin resultados", r["sin_resultados"], 25)
    esperar("la más lenta primero", round(r["lentas"][0]["ms"]), 100)
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

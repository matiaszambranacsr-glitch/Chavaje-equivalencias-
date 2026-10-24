"""Todas las pantallas y solapas se dibujan sin errores, para el administrador, un operador y
quien entra sin contraseña (AppTest).

Uso:
    python3 pruebas_de_las_pantallas.py

Antes este recorrido se armaba a mano en cada revisión, fuera del repositorio. Un error que
corta una pantalla poco usada (una solapa de Estadísticas, un grupo de Mantenimiento) no lo
agarraba ninguna otra prueba: cada una mira lo suyo. Dice además cuáles tardaron más.

Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import os
import shutil
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.abspath(__file__))


def probar():
    from streamlit.testing.v1 import AppTest
    fallas, tiempos = [], []

    at = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
    at.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
    at.run()
    ns = sys.modules["logica"].todo_lo_de_la_logica()
    ns["crear_usuario"]("ana", "clave-ana-1", "operador")

    def entrar(clave):
        at.text_input(key="login_inicial_clave").set_value(clave)
        [b for b in at.button if "Ingresar con contraseña" in b.label][0].click().run()

    def mirar(quien, donde):
        inicio = time.time()
        at.run()
        tiempos.append((time.time() - inicio, f"{quien}: {donde}"))
        for e in at.exception:
            fallas.append(f"{quien}: {donde}: {e.value[:200]}")

    def recorrer(quien):
        for pagina in ns["PAGINAS"]:
            at.session_state["pagina_actual"] = pagina
            if pagina not in ns["SOLAPAS_DE_LA_PAGINA"]:
                mirar(quien, pagina)
                continue
            solapas, clave = ns["SOLAPAS_DE_LA_PAGINA"][pagina]
            for solapa in solapas:
                at.session_state[clave] = solapa
                if solapa == ns["SUB_ADMIN"][4]:            # 🧹 Mantenimiento, por grupo
                    for grupo in ns["GRUPOS_MANTENIMIENTO"]:
                        at.session_state["sub_mantenimiento"] = grupo
                        mirar(quien, f"{pagina} → {solapa} → {grupo}")
                else:
                    mirar(quien, f"{pagina} → {solapa}")

    recorrer("sin contraseña")
    entrar("clave-ana-1")
    recorrer("operador")
    [b for b in at.button if b.label == "Salir"][0].click().run()
    entrar("clave-duenio-1")
    recorrer("administrador")
    tiempos.sort(reverse=True)
    return fallas, len(tiempos), tiempos[:3]


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_pantallas_")
    os.chdir(carpeta)
    sys.path.insert(0, RAIZ)
    try:
        fallas, cuantas, lentas = probar()
        for f in fallas:
            print("   ✗", f)
        print(f"✅ pantallas: las {cuantas} en verde (las más lentas: "
              + ", ".join(f"{d} {s:.1f} s" for s, d in lentas) + ")"
              if not fallas else f"{len(fallas)} falla(s) en {cuantas} pantallas")
        return 1 if fallas else 0
    finally:
        os.chdir(RAIZ)
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

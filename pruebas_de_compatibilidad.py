"""Pruebas de compatibilidad entre versiones: la base nueva con el programa anterior.

Uso:
    python3 pruebas_de_compatibilidad.py --base copia.db [--contra HEAD~1]

Qué prueba: la versión de hoy abre la base (y la migra: columnas, tablas y disparadores
nuevos); después, la versión `--contra` (por defecto, la anterior en git) abre ESA base
migrada y hace lo de todos los días: buscar, la ficha de un par, aprobar, corregir una medida,
anotar una venta, el tablero y exportar. Si algo falla, volver atrás un cambio dejaría la app
rota con la base de hoy.

Por qué existe: lo pidió una revisión con ChatGPT («recuperación con versión anterior del
programa: base nueva + programa anterior, y base antigua + programa nuevo»). La segunda mitad
la prueban las demás pruebas cada vez que abren una copia vieja de la base; esta, la primera,
que es la que importa para volver atrás una versión que salió mal. Sobre la copia de la base
real del 9/10, contra las dos versiones anteriores: todo anda.

Nunca toca la base de trabajo: copias en carpetas temporales y el programa viejo en un
worktree de git aparte, que se borra al terminar.
"""
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.abspath(__file__))
PASOS = ("buscar", "ficha", "aprobar", "medidas", "venta", "tablero", "exportar")


def _hacer_los_pasos(raiz, base, salida=None):
    """Corre los pasos con el programa de `raiz` sobre una copia de `base`. Con `salida`, deja
    ahí la base como quedó (migrada). Imprime un renglón por paso: «paso ok|FALLA detalle»."""
    carpeta = tempfile.mkdtemp(prefix="compat_")
    try:
        shutil.copy(base, os.path.join(carpeta, "equivalencias_app.db"))
        sys.path.insert(0, raiz)
        os.chdir(carpeta)
        import logica
        ns = logica.todo_lo_de_la_logica()
        c = ns["c"]
        c.execute("""SELECT e.producto_a_id, e.producto_b_id, p.codigo_clean FROM equivalencias e
                     JOIN productos p ON p.id = e.producto_a_id
                     ORDER BY e.producto_a_id, e.producto_b_id LIMIT 1""")
        fila = c.fetchone()
        a, b, codigo = (fila[0], fila[1], fila[2]) if fila else (None, None, "X")

        def venta():
            if ns["registrar_venta"].__code__.co_argcount >= 3:
                return ns["registrar_venta"](b, codigo, "🟢 equivalencia confirmada")
            return ns["registrar_venta"](b, codigo)
        hacer = {
            "buscar": lambda: len(ns["buscar_con_variantes_del_cero"](codigo)[0]),
            "ficha": lambda: ns["ficha_de_prueba"](a, b)["estado"] if a else "sin vínculos",
            "aprobar": lambda: ns["marcar_revision"]([(a, b)], "ok") if a else None,
            "medidas": lambda: ns["actualizar_medidas"](a, 35, 52, 7, None, None, None) if a else None,
            "venta": lambda: venta() if b else None,
            "tablero": lambda: (ns["tablero_de_calidad"]()["numeros"]["decididos"]
                                if "tablero_de_calidad" in ns else "no existía en esa versión"),
            "exportar": lambda: ns["exportar_catalogo_zip"]()[1].get("equivalencias"),
        }
        for paso in PASOS:
            try:
                print(f"{paso} ok {str(hacer[paso]())[:60]}", flush=True)
            except Exception as _err:     # noqa: BLE001 — es lo que se mide
                print(f"{paso} FALLA {type(_err).__name__}: {str(_err)[:200]}", flush=True)
        if salida:
            # Con la API de copia de SQLite y no copiando el archivo: lo último puede estar
            # todavía en el WAL de al lado.
            origen, destino = sqlite3.connect(os.path.join(carpeta, "equivalencias_app.db")), \
                sqlite3.connect(salida)
            origen.backup(destino)
            destino.close()
            origen.close()
    finally:
        os.chdir(RAIZ)
        shutil.rmtree(carpeta, ignore_errors=True)


def _correr(raiz, base, salida=None):
    """Los pasos en otro proceso (la lógica se carga una vez por proceso). {paso: renglón}."""
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--pasos", raiz, base]
                       + ([salida] if salida else []),
                       capture_output=True, text=True, timeout=3600, cwd=RAIZ)
    renglones = {x.split(" ", 1)[0]: x for x in r.stdout.splitlines()
                 if x.split(" ", 1)[0] in PASOS}
    if len(renglones) < len(PASOS):
        renglones["arranque"] = "arranque FALLA " + (r.stderr.strip().splitlines() or ["?"])[-1]
    return renglones


def main():
    if "--pasos" in sys.argv:
        i = sys.argv.index("--pasos")
        _hacer_los_pasos(*sys.argv[i + 1:i + 4])
        return 0
    if "--base" not in sys.argv:
        print(__doc__)
        return 2
    base = os.path.abspath(sys.argv[sys.argv.index("--base") + 1])
    contra = sys.argv[sys.argv.index("--contra") + 1] if "--contra" in sys.argv else "HEAD~1"
    carpeta = tempfile.mkdtemp(prefix="compat_viejo_")
    viejo = os.path.join(carpeta, "programa")
    fallas = []
    try:
        subprocess.run(["git", "worktree", "add", "-q", "--detach", viejo, contra], cwd=RAIZ,
                       check=True, capture_output=True)
        migrada = os.path.join(carpeta, "base_migrada.db")
        for titulo, raiz, entrada, salida in (("este programa con la base de antes", RAIZ, base, migrada),
                                              (f"el programa de {contra} con la base migrada", viejo,
                                               migrada, None)):
            renglones = _correr(raiz, entrada, salida)
            malos = [x for x in renglones.values() if " FALLA " in x]
            print(f"{'✅' if not malos else '❌'} {titulo}: "
                  + ", ".join(x.split(" ", 2)[0] + (" ✗" if " FALLA " in x else "")
                              for x in renglones.values()))
            fallas += [f"{titulo}: {x}" for x in malos]
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", viejo], cwd=RAIZ,
                       capture_output=True)
        shutil.rmtree(carpeta, ignore_errors=True)
    for f in fallas:
        print("   ✗", f)
    print("todo en verde" if not fallas else f"{len(fallas)} falla(s)")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())

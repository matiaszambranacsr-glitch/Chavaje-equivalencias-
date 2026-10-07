"""Cuánto tarda el buscador con mucha gente buscando a la vez, sobre una copia de la base real.

Uso:
    python3 medir_el_buscador.py --base copia.db [--personas 10,50,100] [--busquedas 20]

Lo propuso una revisión con ChatGPT: «no asumir que porque ahora responde rápido seguirá
respondiendo rápido con el catálogo completo». Cada «persona» es un hilo —como cada sesión de
Streamlit, que corre en el mismo proceso— y hace búsquedas por código (de códigos que existen,
al azar) y por texto (palabras de las descripciones). Mide el promedio, P95 y P99 de cada
búsqueda, los errores y los «database is locked».

Trabaja sobre una copia en una carpeta temporal: la base que se pasa no se toca.
"""
import argparse
import os
import random
import shutil
import sys
import tempfile
import threading
import time


def medir(ns, personas, busquedas, codigos, palabras):
    tiempos, errores, trabadas = [], [], [0]
    candado = threading.Lock()
    largada = threading.Barrier(personas)

    def persona(n):
        azar = random.Random(n)
        largada.wait()
        for i in range(busquedas):
            inicio = time.monotonic()
            try:
                if i % 4 == 3:
                    ns["buscar_por_texto"](" ".join(azar.sample(palabras, 2)), aflojar=False)
                else:
                    ns["buscar_con_variantes_del_cero"](azar.choice(codigos), "Todas", 3)
            except Exception as _err:
                with candado:
                    errores.append(f"{type(_err).__name__}: {_err}")
                    if "locked" in str(_err):
                        trabadas[0] += 1
                continue
            with candado:
                tiempos.append((time.monotonic() - inicio) * 1000)

    hilos = [threading.Thread(target=persona, args=(n,)) for n in range(personas)]
    inicio = time.monotonic()
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    total = time.monotonic() - inicio
    tiempos.sort()

    def p(x):
        return tiempos[min(len(tiempos) - 1, int(round(x * (len(tiempos) - 1))))] if tiempos else 0
    return {"personas": personas, "búsquedas": len(tiempos) + len(errores),
            "promedio_ms": sum(tiempos) / max(1, len(tiempos)), "p95_ms": p(0.95),
            "p99_ms": p(0.99), "errores": len(errores), "trabadas": trabadas[0],
            "por_segundo": (len(tiempos) + len(errores)) / total, "ejemplo_de_error": errores[:1]}


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--base", required=True)
    args.add_argument("--personas", default="10,50,100")
    args.add_argument("--busquedas", type=int, default=20)
    a = args.parse_args()
    raiz = os.path.dirname(os.path.abspath(__file__))
    carpeta = tempfile.mkdtemp(prefix="medir_buscador_")
    try:
        shutil.copy(a.base, os.path.join(carpeta, "equivalencias_app.db"))
        sys.path.insert(0, raiz)
        os.chdir(carpeta)
        import logica
        ns = logica.todo_lo_de_la_logica()
        c = ns["c"]
        c.execute("SELECT codigo_clean FROM productos ORDER BY RANDOM() LIMIT 2000")
        codigos = [r[0] for r in c.fetchall()]
        c.execute("SELECT descripcion FROM productos WHERE descripcion IS NOT NULL "
                  "ORDER BY RANDOM() LIMIT 500")
        palabras = sorted({w for r in c.fetchall() for w in r[0].upper().split()
                           if len(w) > 3 and w.isalpha()})
        c.execute("SELECT COUNT(*) FROM productos")
        print(f"Catálogo: {c.fetchone()[0]:,} productos".replace(",", "."))
        for personas in (int(x) for x in a.personas.split(",")):
            r = medir(ns, personas, a.busquedas, codigos, palabras)
            print(f"{r['personas']:>4} a la vez · {r['búsquedas']:>5} búsquedas · "
                  f"promedio {r['promedio_ms']:7.1f} ms · P95 {r['p95_ms']:7.1f} · "
                  f"P99 {r['p99_ms']:7.1f} · {r['por_segundo']:6.1f}/s · errores {r['errores']} "
                  f"(trabadas {r['trabadas']}) {r['ejemplo_de_error']}")
    finally:
        os.chdir(raiz)
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    main()

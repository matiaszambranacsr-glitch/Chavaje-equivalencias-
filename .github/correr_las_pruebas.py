"""Corre el auditor y todas las pruebas, y dice qué falló. Lo usa GitHub en cada subida (ver
.github/workflows/pruebas.yml), y se puede correr igual a mano:

    python .github/correr_las_pruebas.py

Antes la batería se corría a mano antes de cada subida, y un cambio hecho por otro lado llegaba
a la app sin pasar por nada (lo señaló una revisión con ChatGPT: «toda la batería antes de
publicar»). Las pruebas van de a varias a la vez, las más largas primero; cada una corre en su
propia carpeta temporal y no toca la base de trabajo.

Lo que necesita la base real (pruebas/pruebas_de_la_revision.py --base,
pruebas/pruebas_de_compatibilidad.py) no corre acá: GitHub no tiene la base. Eso se sigue
corriendo antes de publicar.
"""
import glob
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MINUTOS_POR_PRUEBA = 25
RENGLONES_DE_LO_QUE_FALLO = 40


def _las_pruebas():
    """[(nombre, comando)]: el auditor, cada pruebas/pruebas_*.py y las del núcleo. Las más largas
    primero (el tamaño del archivo alcanza como estimación): así no queda la más larga sola al
    final. Las que necesitan la base real corren sin ella."""
    pruebas = sorted(glob.glob(os.path.join(RAIZ, "pruebas", "pruebas_*.py")),
                     key=lambda p: -os.path.getsize(p))
    comandos = [("auditar.py", [sys.executable, "auditar.py"])]
    for ruta in pruebas:
        nombre = os.path.basename(ruta)
        if nombre == "pruebas_de_compatibilidad.py":
            continue            # sin --base no tiene con qué: necesita una copia de la base real
        comandos.append((nombre, [sys.executable, os.path.join("pruebas", nombre)]))
    comandos.append(("nucleo.pruebas", [sys.executable, "-m", "nucleo.pruebas"]))
    return comandos


def _correr(nombre, comando):
    inicio = time.time()
    try:
        r = subprocess.run(comando, cwd=RAIZ, capture_output=True, text=True,
                           timeout=MINUTOS_POR_PRUEBA * 60)
        dijo, errores, codigo = r.stdout or "", r.stderr or "", r.returncode
    except subprocess.TimeoutExpired as e:
        dijo = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        errores = f"SE PASÓ DE {MINUTOS_POR_PRUEBA} MINUTOS"
        codigo = -1
    return nombre, codigo, time.time() - inicio, dijo, errores


def main():
    comandos = _las_pruebas()
    a_la_vez = max(1, min(4, os.cpu_count() or 1))
    print(f"{len(comandos)} pruebas, de a {a_la_vez}", flush=True)
    inicio = time.time()
    resultados = []
    with ThreadPoolExecutor(max_workers=a_la_vez) as pool:
        for nombre, codigo, segundos, dijo, errores in pool.map(lambda x: _correr(*x), comandos):
            # Lo de stderr, después: ahí van los avisos de Streamlit, que no son de la prueba.
            resultados.append((nombre, codigo, dijo + errores))
            # El resumen, de lo que dijo la prueba («✅ … todo en verde», «3 falla(s)»), no
            # del último aviso de Streamlit.
            ultimo = next((r for r in reversed(dijo.strip().splitlines()) if r.strip()), "")
            ultimo = ultimo or next((r for r in reversed(errores.strip().splitlines())
                                     if r.strip()), "")
            print(f"{'✅' if codigo == 0 else '❌'} {nombre:42} {segundos:6.0f} s  {ultimo[:90]}",
                  flush=True)
    fallaron = [(n, s) for n, c, s in resultados if c != 0]
    for nombre, salida in fallaron:
        print(f"\n===== {nombre}: lo último que dijo =====")
        renglones = [r for r in salida.splitlines() if "ScriptRunContext" not in r]
        print("\n".join(renglones[-RENGLONES_DE_LO_QUE_FALLO:]))
    print(f"\n{len(comandos) - len(fallaron)} de {len(comandos)} en verde, "
          f"en {(time.time() - inicio) / 60:.1f} minutos")
    return 1 if fallaron else 0


if __name__ == "__main__":
    sys.exit(main())

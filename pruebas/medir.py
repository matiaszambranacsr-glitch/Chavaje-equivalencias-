"""Medir el buscador y la cola contra una copia de la base real, con salida corta.

    python pruebas/medir.py --base copia.db busquedas [--n 1500] [--guardar antes.json]
    python pruebas/medir.py --base copia.db busquedas --comparar antes.json
    python pruebas/medir.py --base copia.db cola [--guardar antes.json | --comparar antes.json]

«busquedas»: N búsquedas al azar (siempre las mismas: semilla fija) entre los productos de redes
de 3 o más; cuenta los resultados por estado de la ficha, el tiempo (promedio, p95, máximo) y
las más lentas. «cola»: el análisis de todas las listas pendientes, por nivel.
Con --guardar deja cada resultado en un json; con --comparar dice qué cambió y da ejemplos.
Es lo que antes se escribía a mano en cada cambio de reglas (ver «Para gastar pocos tokens» en
CLAUDE.md). Trabaja sobre una copia temporal: la base que se le pasa no se toca."""
import collections
import json
import os
import random
import shutil
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _argumento(nombre, defecto=None):
    return sys.argv[sys.argv.index(nombre) + 1] if nombre in sys.argv else defecto


def _cargar(base):
    carpeta = tempfile.mkdtemp(prefix="medir_")
    shutil.copy(base, os.path.join(carpeta, "equivalencias_app.db"))
    os.chdir(carpeta)
    sys.path.insert(0, RAIZ)
    # Sin los avisos de Streamlit corriendo suelto («missing ScriptRunContext»…): la salida
    # tiene que ser de dos renglones.
    import logging
    logging.disable(logging.WARNING)
    import logica
    return logica.todo_lo_de_la_logica(), carpeta


def busquedas(ns, n):
    c = ns["c"]
    raiz, tam = ns["_red_de_equivalencias"]()
    tipo = dict(c.execute("SELECT p.id, m.tipo FROM productos p JOIN marcas m ON m.id = p.marca_id"))
    codigo = dict(c.execute("SELECT id, codigo_clean FROM productos"))
    prods = sorted(p for p, r in raiz.items() if tam.get(r, 0) >= 3 and tipo.get(p) != "OEM")
    muestra = random.Random(7).sample(prods, min(n, len(prods)))
    salida, tiempos = {}, []
    for p in muestra:
        t = time.time()
        res, _ = ns["buscar_con_variantes_del_cero"](codigo[p], "Todas", 3)
        tiempos.append((time.time() - t, codigo[p]))
        for f in res:
            if f.get("Cadena") == "— el buscado" or f.get("Tipo") == "OEM":
                continue
            salida[f"{p}-{f['ID']}"] = [str(f.get("_estado") or "")[:2].strip() or "—",
                                        bool(f.get("_complementario")),
                                        f"{f.get('Marca')} {f.get('Codigo')}",
                                        str(f.get("_por_que_estado") or "")[:70]]
    tiempos.sort()
    ts = [t for t, _ in tiempos]
    print(f"{len(muestra)} búsquedas, {len(salida)} resultados: "
          f"{dict(collections.Counter(v[0] for v in salida.values()).most_common())}, "
          f"{sum(v[1] for v in salida.values())} complementarios")
    print(f"tiempo: promedio {sum(ts) / len(ts):.3f} s, p95 {ts[int(len(ts) * .95)]:.3f} s, "
          f"máximo {ts[-1]:.3f} s; las más lentas: "
          + ", ".join(f"{cod} {t:.2f}" for t, cod in tiempos[-5:][::-1]))
    return salida


def cola(ns):
    salida = {}
    for (lote,) in ns["c"].execute("SELECT DISTINCT lote FROM equivalencias_pendientes").fetchall():
        limpias, sospechosas, _rel = ns["analizar_lote_pendiente"](lote)
        for f in list(limpias) + list(sospechosas):
            salida[f"{f['a']}-{f['b']}"] = [ns["nivel_de_confianza"](f["confianza"])[0][:1],
                                            round(f["confianza"]),
                                            f"{f.get('marca_a')} {f['cod_a']} ↔ {f.get('marca_b')} {f['cod_b']}",
                                            ((f.get("alarmas") or [""])[0])[:70]]
    print(f"{len(salida)} pares: {dict(collections.Counter(v[0] for v in salida.values()).most_common())}")
    return salida


def comparar(antes, ahora):
    cambios = collections.Counter()
    ejemplos = collections.defaultdict(list)
    for k, v in ahora.items():
        if k in antes and antes[k][:2] != v[:2]:
            clave = f"{antes[k][0]} → {v[0]}" + (" (complementario)" if v[1] is True and antes[k][1] is not True else "")
            cambios[clave] += 1
            if len(ejemplos[clave]) < 3:
                ejemplos[clave].append(f"{v[2]} | {v[3]}")
    nuevos, idos = len(set(ahora) - set(antes)), len(set(antes) - set(ahora))
    print(f"cambios: {dict(cambios.most_common()) or 'ninguno'}; nuevos {nuevos}, ya no están {idos}")
    for clave, ej in ejemplos.items():
        for e in ej:
            print(f"   {clave}: {e}")


def main():
    base = _argumento("--base")
    if not base or not ({"busquedas", "cola"} & set(sys.argv)):
        print(__doc__)
        return 2
    guardar, contra = _argumento("--guardar"), _argumento("--comparar")
    guardar = guardar and os.path.abspath(guardar)
    contra = contra and os.path.abspath(contra)
    ns, carpeta = _cargar(os.path.abspath(base))
    try:
        datos = (busquedas(ns, int(_argumento("--n", "1500"))) if "busquedas" in sys.argv
                 else cola(ns))
        if guardar:
            with open(guardar, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False)
        if contra:
            with open(contra, encoding="utf-8") as f:
                comparar(json.load(f), datos)
    finally:
        os.chdir(RAIZ)
        shutil.rmtree(carpeta, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

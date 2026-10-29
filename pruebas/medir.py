"""Medir el buscador y la cola contra una copia de la base real, con salida corta.

    python pruebas/medir.py --base copia.db busquedas [--n 1500] [--guardar antes.json]
    python pruebas/medir.py --base copia.db busquedas --comparar antes.json
    python pruebas/medir.py --base copia.db cola [--guardar antes.json | --comparar antes.json]
    python pruebas/medir.py --base copia.db fichas [--n 2000] [--guardar … | --comparar …]
    python pruebas/medir.py --base copia.db texto [--n 1000] [--guardar … | --comparar …]
    python pruebas/medir.py --base copia.db toques [--n 10] [--guardar … | --comparar …]

«busquedas»: N búsquedas al azar (siempre las mismas: semilla fija) entre los productos de redes
de 3 o más; cuenta los resultados por estado de la ficha, el tiempo (promedio, p95, máximo) y
las más lentas. «cola»: el análisis de todas las listas pendientes, por nivel. «toques»: cuánto
tarda cada pantalla en un toque cualquiera (el segundo dibujo, que es lo que se repite todo el
día), como empleado, y la función donde más se va el tiempo en las N más lentas.
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


def fichas(ns, n):
    """El estado de la ficha de lo que decidió una persona, como si nadie lo hubiera decidido (en
    la copia: sin las decisiones guardadas, y a cada aprobado se le saca su vínculo directo
    mientras se mira). Lo rechazado no debería salir ✅ ni 🟡: sería un vínculo malo que el
    buscador da por bueno. Lo aprobado, cuanto más alto, mejor: es lo que se encuentra solo."""
    c, conn = ns["c"], ns["conn"]
    elegidos = {}
    for decision in ("rechazada", "ok"):
        pares = [tuple(r) for r in c.execute(
            "SELECT producto_a_id, producto_b_id FROM equivalencias_revisadas WHERE decision = ? "
            "AND producto_a_id < producto_b_id AND COALESCE(revisado_por, '') <> '🤖 la app'",
            (decision,))]
        elegidos[decision] = random.Random(7).sample(pares, min(n, len(pares)))
    c.execute("DELETE FROM equivalencias_revisadas")
    conn.commit()
    salida = {}
    for decision, pares in elegidos.items():
        for a, b in pares:
            fila = c.execute("SELECT * FROM equivalencias WHERE producto_a_id = ? AND "
                             "producto_b_id = ?", (a, b)).fetchone()
            if fila:
                c.execute("DELETE FROM equivalencias WHERE producto_a_id = ? AND producto_b_id = ?",
                          (a, b))
            ficha = ns["ficha_de_prueba"](a, b, liviana=True)
            if fila:
                c.execute(f"INSERT INTO equivalencias ({', '.join(fila.keys())}) VALUES "
                          f"({', '.join('?' * len(fila.keys()))})", tuple(fila))
            if ficha:
                salida[f"{a}-{b}"] = [ficha["estado"][:1], decision,
                                      f"{ficha['a'].get('marca', '')} {ficha['a'].get('codigo_raw', '')} ↔ "
                                      f"{ficha['b'].get('marca', '')} {ficha['b'].get('codigo_raw', '')}",
                                      "; ".join(ficha.get("falta") or [])[:70]]
        cuenta = collections.Counter(v[0] for v in salida.values() if v[1] == decision)
        print(f"{'rechazados' if decision == 'rechazada' else 'aprobados'}: {dict(cuenta.most_common())}")
    conn.commit()
    return salida


def texto(ns, n):
    """La búsqueda por descripción como se escribe en el mostrador: la pieza y dos palabras más
    de la descripción, en minúscula y en otro orden. En qué puesto sale el producto."""
    import re
    c = ns["c"]
    filas = [tuple(r) for r in c.execute(
        "SELECT p.id, p.descripcion FROM productos p JOIN marcas m ON m.id = p.marca_id "
        "WHERE m.tipo <> 'OEM' AND LENGTH(p.descripcion) > 15")]
    azar = random.Random(7)
    salida, tiempos = {}, []
    for pid, desc in azar.sample(filas, min(n, len(filas))):
        palabras = [w for w in re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}", desc)]
        if len(palabras) < 3:
            continue
        consulta = " ".join([palabras[0]] + azar.sample(palabras[1:], 2)).lower()
        t = time.time()
        res = ns["buscar_por_texto"](consulta)
        tiempos.append(time.time() - t)
        ids = [f.get("ID") for f in res]
        salida[str(pid)] = [ids.index(pid) + 1 if pid in ids else 0, consulta]
    puestos = [v[0] for v in salida.values()]
    tiempos.sort()
    print(f"{len(puestos)} consultas: primero {sum(p == 1 for p in puestos)}, entre los 5 primeros "
          f"{sum(1 <= p <= 5 for p in puestos)}, entre los 20 {sum(1 <= p <= 20 for p in puestos)}, "
          f"no aparece {puestos.count(0)}; tiempo promedio {sum(tiempos) / len(tiempos):.3f} s, "
          f"p95 {tiempos[int(len(tiempos) * .95)]:.3f} s")
    return salida


def toques(base, n):
    """{pantalla: segundos del segundo dibujo}, e imprime las n más lentas con dónde se va el
    tiempo (muestreando cada 10 ms el hilo que dibuja, como Muestreo en pruebas_de_las_pantallas).
    Se escribía a mano cada vez que se quería saber qué pantalla anda lenta con la base real."""
    import threading
    carpeta = tempfile.mkdtemp(prefix="medir_")
    shutil.copy(base, os.path.join(carpeta, "equivalencias_app.db"))
    os.environ["EQUIVALENCIAS_SIN_TAREAS_DE_FONDO"] = "1"
    os.chdir(carpeta)
    sys.path.insert(0, RAIZ)
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
    at.run()
    for hilo in [h for h in threading.enumerate() if h.name in ("de_antemano",
                                                                 "indice_de_busqueda")]:
        hilo.join()
    ns = sys.modules["logica"].todo_lo_de_la_logica()
    # Un empleado de prueba, solo en esta copia (que se borra al terminar).
    clave = f"clave-medir-{os.urandom(4).hex()}"
    ns["crear_usuario"](f"medir{clave[-4:]}", clave, "operador")
    at.text_input(key="login_inicial_clave").set_value(clave)
    [b for b in at.button if "Ingresar con contraseña" in b.label][0].click().run()
    cuenta, mirando, propio = collections.Counter(), [True], threading.get_ident()

    def mirar():
        # Solo el hilo que dibuja (el que viene de app.py): los de atrás —el índice de búsqueda,
        # el dólar— no son de la pantalla. Y la función más de adentro de logica/ o pantallas/,
        # sin el envoltorio de la base (datos.py:execute): lo que sirve es quién consulta.
        app, adentro = os.path.join(RAIZ, "app.py"), (os.path.join(RAIZ, "logica"),
                                                      os.path.join(RAIZ, "pantallas"))
        while mirando[0]:
            for hilo, marco in sys._current_frames().items():
                if hilo in (propio, threading.get_ident()):
                    continue
                arriba = marco
                while arriba and arriba.f_code.co_filename != app:
                    arriba = arriba.f_back
                if not arriba:
                    continue
                while marco and (not marco.f_code.co_filename.startswith(adentro)
                                 or marco.f_code.co_name in ("execute", "executemany",
                                                             "fetchall", "fetchone")):
                    marco = marco.f_back
                if marco:
                    cuenta[f"{os.path.basename(marco.f_code.co_filename)}:"
                           f"{marco.f_code.co_name}"] += 1
            time.sleep(0.01)
    threading.Thread(target=mirar, daemon=True).start()
    tiempos, donde = {}, {}

    def medir(nombre):
        at.run()
        cuenta.clear()
        inicio = time.perf_counter()
        at.run()
        tiempos[nombre] = round(time.perf_counter() - inicio, 2)
        donde[nombre] = cuenta.most_common(1)[0][0] if cuenta else ""
    try:
        for pagina in at.radio(key="pagina_actual").options:
            at.session_state["pagina_actual"] = pagina
            if pagina not in ns["SOLAPAS_DE_LA_PAGINA"]:
                medir(pagina)
                continue
            solapas, clave_solapa = ns["SOLAPAS_DE_LA_PAGINA"][pagina]
            for solapa in solapas:
                at.session_state[clave_solapa] = solapa
                if solapa == ns["SUB_ADMIN"][4]:
                    for grupo in ns["GRUPOS_MANTENIMIENTO"]:
                        at.session_state["sub_mantenimiento"] = grupo
                        medir(f"{pagina} → {solapa} → {grupo}")
                else:
                    medir(f"{pagina} → {solapa}")
    finally:
        mirando[0] = False
        os.chdir(RAIZ)
        shutil.rmtree(carpeta, ignore_errors=True)
    for nombre, segundos in sorted(tiempos.items(), key=lambda x: -x[1])[:n]:
        print(f"{segundos:5.2f} s  {nombre}  [{donde[nombre]}]")
    print(f"{len(tiempos)} pantallas, en total {sum(tiempos.values()):.1f} s")
    return tiempos


def comparar_toques(antes, ahora):
    cambios = sorted(((ahora[k] - antes[k], k) for k in ahora if k in antes
                      and abs(ahora[k] - antes[k]) >= 0.1), reverse=True)
    for dif, nombre in cambios[:10]:
        print(f"{dif:+5.2f} s  {nombre} ({antes[nombre]} → {ahora[nombre]})")
    print(f"en total: {sum(antes.values()):.1f} s → {sum(ahora.values()):.1f} s"
          + ("" if cambios else " · ninguna cambió 0,1 s o más"))


def comparar_puestos(antes, ahora):
    """Lo de «texto»: [puesto, consulta], con 0 si no aparece. Mejor es salir más arriba."""
    def peso(puesto):
        return puesto or 10 ** 6
    mejor = [k for k in ahora if k in antes and peso(ahora[k][0]) < peso(antes[k][0])]
    peor = [k for k in ahora if k in antes and peso(ahora[k][0]) > peso(antes[k][0])]
    print(f"mejoran {len(mejor)}, empeoran {len(peor)}, igual {len(ahora) - len(mejor) - len(peor)}")
    for nombre, claves in (("mejora", mejor), ("empeora", peor)):
        for k in claves[:4]:
            print(f"   {nombre}: «{ahora[k][1]}» del puesto {antes[k][0] or '—'} al {ahora[k][0] or '—'}")


def comparar(antes, ahora):
    if ahora and len(next(iter(ahora.values()))) == 2:
        return comparar_puestos(antes, ahora)
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
    if not base or not ({"busquedas", "cola", "fichas", "texto", "toques"} & set(sys.argv)):
        print(__doc__)
        return 2
    guardar, contra = _argumento("--guardar"), _argumento("--comparar")
    guardar = guardar and os.path.abspath(guardar)
    contra = contra and os.path.abspath(contra)
    if "toques" in sys.argv:
        datos = toques(os.path.abspath(base), int(_argumento("--n", "10")))
        if guardar:
            with open(guardar, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False)
        if contra:
            with open(contra, encoding="utf-8") as f:
                comparar_toques(json.load(f), datos)
        return 0
    ns, carpeta = _cargar(os.path.abspath(base))
    try:
        datos = (busquedas(ns, int(_argumento("--n", "1500"))) if "busquedas" in sys.argv
                 else fichas(ns, int(_argumento("--n", "2000"))) if "fichas" in sys.argv
                 else texto(ns, int(_argumento("--n", "1000"))) if "texto" in sys.argv
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

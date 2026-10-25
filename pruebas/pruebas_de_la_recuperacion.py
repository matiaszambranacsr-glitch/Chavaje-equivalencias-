"""Pruebas del modo recuperación: la app con la base dañada.

Uso:
    python3 pruebas/pruebas_de_la_recuperacion.py

Antes, con el archivo de la base dañado, la lógica no llegaba a cargar y la app no abría. Ver
«MODO RECUPERACIÓN» en logica/copias_y_mantenimiento.py. Corre en carpetas temporales: nunca
toca la base de trabajo.
"""
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CARGAR = ("import sys; sys.path.insert(0, %r); import logica; "
           "print('ILEGIBLE=' + repr(logica.todo_lo_de_la_logica()['BASE_ILEGIBLE']))" % RAIZ)


def _cargar_en(carpeta):
    """Carga la lógica en otro proceso (es una vez por proceso) y devuelve lo que dijo."""
    r = subprocess.run([sys.executable, "-c", _CARGAR], cwd=carpeta, capture_output=True,
                       text=True, timeout=300)
    return r.returncode, (r.stdout.strip().splitlines() or [""])[-1], r.stderr[-300:]


def probar():
    fallas = []

    def esperar(nombre, real, esperado):
        if real != esperado:
            fallas.append(f"{nombre}: dio {real!r}, se esperaba {esperado!r}")

    # 1. Con bytes al azar en lugar de la base, la lógica carga igual y lo dice.
    rota = tempfile.mkdtemp(prefix="pruebas_rec_rota_")
    try:
        with open(os.path.join(rota, "equivalencias_app.db"), "wb") as f:
            f.write(os.urandom(200_000))
        codigo, dijo, error = _cargar_en(rota)
        esperar("con la base dañada carga", (codigo, dijo.startswith("ILEGIBLE='") and
                                             dijo != "ILEGIBLE=''"), (0, True))
        if codigo:
            fallas.append(f"   {error}")
    finally:
        shutil.rmtree(rota, ignore_errors=True)

    # 2. Lo demás, en este proceso, con una base sana.
    carpeta = tempfile.mkdtemp(prefix="pruebas_rec_")
    os.chdir(carpeta)
    sys.path.insert(0, RAIZ)
    try:
        import logica
        ns = logica.todo_lo_de_la_logica()
        g = ns["inflacion_desde"].__globals__
        esperar("con la base sana, nada", ns["BASE_ILEGIBLE"], "")

        # Restaurar un backup devuelve el control de la base YA restaurada.
        c = ns["c"]
        c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('PRUEBA', 'PROVEEDOR')")
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
                  "VALUES ('P1', 'P1', 'PIEZA', ?)", (c.lastrowid,))
        ns["conn"].commit()
        copia = ns["generar_backup_sin_fotos"]()
        c.execute("DELETE FROM productos")
        ns["conn"].commit()
        # Lo guardado en el proceso que sale de la base (ver MEMORIAS_DE_LA_BASE): restaurada
        # otra base, seguía contestando con la de antes.
        _guardados = sys.modules["_equivalencias_el_chavo_del_proceso"].__dict__

        def _llenas():
            ns["cobertura_del_catalogo"]()
            ns["escala_de_precios_por_marca"]()
            ns["_marcas_con_chas"]()
            ns["cuanto_une_cada_par"]([])
            return _que_tienen()

        def _que_tienen():
            return {"cobertura": bool(_guardados.get("cobertura_del_catalogo")),
                    "escala": (_guardados.get("escala_de_precios") or {}).get("datos") is not None,
                    "chas": "mapa" in (_guardados.get("marcas_con_chas") or {}),
                    "red": bool(_guardados.get("red_de_equivalencias"))}
        _vacias = {"cobertura": False, "escala": False, "chas": False, "red": False}
        esperar("antes de restaurar, guardadas", _llenas(), {k: True for k in _vacias})
        import io
        control = ns["restaurar_backup"](io.BytesIO(copia))      # la copia vuelve en bytes
        esperar("restaurado y controlado", (control["sana"], control["productos"]), (True, 1))
        esperar("restaurar olvida lo guardado de la base anterior", _que_tienen(), _vacias)
        # Cada memoria del proceso dice si sale de la base: una nueva sin decidir no se olvidaría
        # al restaurar sin que nada avise.
        import glob
        import re
        _usadas = set()
        for _archivo in (glob.glob(os.path.join(RAIZ, "logica", "*.py"))
                         + glob.glob(os.path.join(RAIZ, "pantallas", "*.py"))
                         + [os.path.join(RAIZ, "app.py")]):
            with open(_archivo, encoding="utf-8") as _f:
                _usadas |= set(re.findall(r'del_proceso\(\s*"([a-z_]+)"', _f.read()))
        esperar("cada del_proceso() está en MEMORIAS_DE_LA_BASE o en MEMORIAS_QUE_NO_SON_DE_LA_BASE",
                sorted(_usadas - set(ns["MEMORIAS_DE_LA_BASE"])
                       - set(ns["MEMORIAS_QUE_NO_SON_DE_LA_BASE"])), [])
        esperar("y las listas no nombran ninguna que ya no exista",
                sorted((set(ns["MEMORIAS_DE_LA_BASE"]) | set(ns["MEMORIAS_QUE_NO_SON_DE_LA_BASE"]))
                       - _usadas), [])
        esperar("ocupada no es dañada",
                ns["es_una_base_danada"](sqlite3.OperationalError("database is locked")), False)
        esperar("dañada es dañada",
                ns["es_una_base_danada"](sqlite3.DatabaseError("file is not a database")), True)

        # El backup COMPLETO (con fotos) también se restaura, y con sus fotos (ver
        # generar_backup_completo()). No tenía prueba: el liviano sí.
        _pid = c.execute("SELECT id FROM productos").fetchone()[0]
        c.execute("INSERT INTO producto_fotos (producto_id, imagen_data, estado) "
                  "VALUES (?, ?, 'ok')", (_pid, b"\x89PNG foto de prueba"))
        ns["conn"].commit()
        completo = ns["generar_backup_completo"]()
        c.execute("DELETE FROM producto_fotos")
        c.execute("DELETE FROM productos")
        ns["conn"].commit()
        control = ns["restaurar_backup"](io.BytesIO(completo))
        esperar("el completo se restaura, con sus productos y sus fotos",
                (control["sana"], control["productos"],
                 c.execute("SELECT COUNT(*) FROM producto_fotos").fetchone()[0],
                 c.execute("SELECT imagen_data FROM producto_fotos").fetchone()[0]),
                (True, 1, 1, b"\x89PNG foto de prueba"))

        # La contraseña: la de administrador de los Secrets, con freno.
        g["secretos_app"] = lambda: {"admin_password": "clave-rec-1"}
        esperar("clave buena", g["clave_de_recuperacion_valida"]("clave-rec-1")[0], True)
        esperar("clave mala", g["clave_de_recuperacion_valida"]("otra")[0], False)
        for _ in range(6):
            g["clave_de_recuperacion_valida"]("otra")
        esperar("con el freno, ni la buena", g["clave_de_recuperacion_valida"]("clave-rec-1")[0],
                False)
        g["del_proceso"]("intentos_en_recuperacion", list).clear()
        g["secretos_app"] = lambda: {}
        esperar("sin claves configuradas, abierto", g["clave_de_recuperacion_valida"]("")[0], True)

        # Un archivo que no es una base: no se toca nada.
        db = g["DB_PATH"]
        antes = sorted(os.listdir("."))
        ok, aviso = g["reemplazar_la_base_danada"](b"esto no es una base" * 100)
        esperar("basura: no", ok, False)
        esperar("basura: no se movió nada", sorted(os.listdir(".")), antes)
        # Una base sana: queda en lugar de la otra, y la otra aparte.
        sana = os.path.join(carpeta, "sana.db")
        con = sqlite3.connect(sana)
        con.execute("CREATE TABLE productos (id INTEGER)")
        con.execute("INSERT INTO productos VALUES (1)")
        con.commit()
        con.close()
        with open(db, "rb") as f:
            vieja = f.read()
        _llenas()
        with open(sana, "rb") as f:
            ok, aviso = g["reemplazar_la_base_danada"](f.read())
        esperar("sana: sí", ok, True)
        esperar("y también olvida lo guardado de la base anterior", _que_tienen(), _vacias)
        apartadas = [n for n in os.listdir(".") if ".danada-" in n and not n.endswith(("-wal", "-shm"))]
        esperar("la vieja quedó aparte", len(apartadas), 1)
        with open(apartadas[0], "rb") as f:
            esperar("la vieja intacta", f.read() == vieja, True)
        esperar("la nueva en su lugar",
                sqlite3.connect(db).execute("SELECT COUNT(*) FROM productos").fetchone()[0], 1)
        esperar("la próxima pasada recarga la lógica", logica.cambio_algun_archivo(), True)
    finally:
        os.chdir(RAIZ)
        shutil.rmtree(carpeta, ignore_errors=True)
    return fallas


def main():
    fallas = probar()
    for f in fallas:
        print("   ✗", f)
    print("✅ recuperación: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())

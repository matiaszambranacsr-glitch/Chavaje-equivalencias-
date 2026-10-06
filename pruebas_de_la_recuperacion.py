"""Pruebas del modo recuperación: la app con la base dañada.

Uso:
    python3 pruebas_de_la_recuperacion.py

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

RAIZ = os.path.dirname(os.path.abspath(__file__))
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
        esperar("ocupada no es dañada",
                ns["es_una_base_danada"](sqlite3.OperationalError("database is locked")), False)
        esperar("dañada es dañada",
                ns["es_una_base_danada"](sqlite3.DatabaseError("file is not a database")), True)

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
        with open(sana, "rb") as f:
            ok, aviso = g["reemplazar_la_base_danada"](f.read())
        esperar("sana: sí", ok, True)
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

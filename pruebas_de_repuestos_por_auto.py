"""Pruebas de «Repuestos por auto»: qué productos le van a un auto según la descripción.

Uso:
    python3 pruebas_de_repuestos_por_auto.py

Por qué existe: la búsqueda era «la descripción contiene la marca y contiene el modelo», y con
los modelos cortos eso no sirve. Sobre el catálogo real, VW Gol traía 241 productos del Golf, el
Bora o el Polo; VW Up, 205 de 283 que no eran del Up; Peugeot 208, 176 de 377. Y escribir
«VOLKSWAGEN» se perdía los que dicen «VW». Ver _nombra_este_auto() en
logica/repuestos_por_auto.py.

Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import os
import shutil
import sys
import tempfile

# (descripción, ¿le va a un VW Gol?)
_GOL = [
    ("SENSOR DE TEMPERATURA VW GOL TREND 1.6", True),
    ("SENSOR DE TEMPERATURA VOLKSWAGEN GOL 1.4", True),
    ("Bulbo de temperatura. Gol - Saveiro - Santana 1.6 - Camiones VW 1999 en adelante.", True),
    ("CARCASA DE TERMOSTATO 97053Vw Gol Trend Voyage 1 6", True),
    ("SENSOR DE TEMPERATURA VW GOLF - PASSAT TDI", False),
    ("INYECTOR VOLKSWAGEN BORA GOLF BEETLE 2.0", False),
    ("BOMBA DE AGUA FIAT PALIO 1.4", False),
]
# (descripción, ¿le va a un Peugeot 208?)
_208 = [
    ("BOMBA DE AGUA PEUGEOT 208 1.5 8V", True),
    ("CUERPO MARIPOSA PEUGEOT 206 207 208 1.4 8V", True),
    ("FICHA DE INYECCION 71208 PEUGEOT 206", False),
    ("JUNTA PEUGEOT 206 - FIAT 208 MEDIDA", False),
]
# (descripción, ¿le va a un VW Up?)
_UP = [
    ("TERMOSTATO VOLKSWAGEN UP FOX GOL 1.0", True),
    ("AMORTIGUADOR VW AMAROK PICK UP", False),
    ("AMORTIGUADOR VW AMAROK PICK-UP 2.0", False),
]


def _cargar_la_logica(carpeta):
    raiz = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, raiz)
    os.chdir(carpeta)
    import logica
    return logica


def probar(L):
    ns = L.todo_lo_de_la_logica()
    fallas = []

    def esperar(nombre, real, esperado):
        if real != esperado:
            fallas.append(f"{nombre}: dio {real!r}, se esperaba {esperado!r}")

    for marca, modelo, casos in (("VOLKSWAGEN", "GOL", _GOL), ("VW", "GOL", _GOL),
                                 ("PEUGEOT", "208", _208), ("VOLKSWAGEN", "UP", _UP)):
        canon = ns["ALIAS_MARCA_VEHICULO"].get(marca, marca)
        for desc, va in casos:
            esperar(f"{marca} {modelo} ← «{desc}»", ns["_nombra_este_auto"](desc, canon, modelo), va)

    # De punta a punta, con la base: el catálogo y lo que se le puso a otros autos iguales.
    c = ns["c"]
    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('PRUEBA', 'PROVEEDOR')")
    mid = c.execute("SELECT id FROM marcas WHERE nombre = 'PRUEBA'").fetchone()[0]
    for i, (desc, _va) in enumerate(_GOL):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
                  "VALUES (?, ?, ?, ?)", (f"P{i}", f"P{i}", desc, mid))
    r = ns["repuestos_de_este_auto"]("VOLKSWAGEN", "GOL")
    esperar("catálogo del Gol", sorted(f["Descripcion"] for f in r["del_catalogo"]),
            sorted(d for d, va in _GOL if va))
    gol = ns["get_or_create_vehiculo"]("AA123BB", marca_auto="VW", modelo_auto="Gol Trend")
    golf = ns["get_or_create_vehiculo"]("AA123BC", marca_auto="Volkswagen", modelo_auto="Golf")
    ns["agregar_pieza_historial"](gol, "Bomba de agua", "SKF", "BA-1", 50000, 60000, "")
    ns["agregar_pieza_historial"](golf, "Bomba de agua", "SKF", "BA-2", 50000, 60000, "")
    r = ns["repuestos_de_este_auto"]("VOLKSWAGEN", "GOL")
    esperar("otros Gol: no cuenta el Golf", [f["Código"] for f in r["de_otros_iguales"]], ["BA-1"])

    # Sin la marca: se deduce del modelo, primero por el registro automotor.
    r = ns["repuestos_de_este_auto"]("", "GOL")
    esperar("sin marca y pocos productos: no adivina", r["marca_deducida"], "")
    for i in range(10):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
                  "VALUES (?, ?, ?, ?)", (f"F{i}", f"F{i}", f"FILTRO {i} VW GOL 1.6", mid))
    r = ns["repuestos_de_este_auto"]("", "GOL")
    esperar("sin marca, por el catálogo", (r["marca_deducida"], len(r["del_catalogo"])),
            ("VOLKSWAGEN", 14))
    c.executemany("INSERT INTO parque_automotor (mes, provincia, marca, modelo, anio, cantidad) "
                  "VALUES ('202608', 'X', ?, ?, 2010, ?)",
                  [("VOLKSWAGEN", "GOL", 500), ("FORD", "KA", 300), ("CITROEN", "C3", 50),
                   ("FIAT", "PALIO", 20), ("FIAT", "PALIO", 1), ("CHERY", "PALIO", 1)])
    esperar("marca por el registro", [ns["marca_del_modelo"](m) for m in
                                      ("Gol Trend 1.6", "ka", "Palio", "Corsa", "500")],
            ["VOLKSWAGEN", "FORD", "FIAT", None, None])
    return fallas


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_repuestos_")
    try:
        fallas = probar(_cargar_la_logica(carpeta))
        for f in fallas:
            print("   ✗", f)
        print("✅ repuestos por auto: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

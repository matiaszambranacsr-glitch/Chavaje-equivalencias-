"""Pruebas del registro de CHAS (autopartes de seguridad homologadas).

Uso:
    python3 pruebas_de_las_homologaciones.py

El formato del archivo oficial no está documentado en ningún lado que se pudiera leer desde
donde se programó, así que se prueba con varias formas razonables de escribir el encabezado
(con y sin acentos, con coma o punto y coma, en UTF-8 o en Windows-1252). Ver
logica/homologaciones.py.

Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import os
import shutil
import sys
import tempfile


def _cargar_la_logica(carpeta):
    raiz = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, raiz)
    os.chdir(carpeta)
    import logica
    return logica


_CSV_COMAS = ("Nro. CHAS,Razón Social,Marca,Autoparte,Modelo / Código,Fecha de Emisión\n"
              "C-0001,FRAS-LE ARGENTINA S.A.,FRAS-LE,PASTILLAS DE FRENO,PD/123,2024-03-01\n"
              "C-0002,FRAS-LE ARGENTINA S.A.,FRAS-LE,CINTAS DE FRENO,CF/9,2024-03-01\n"
              ",,,,,\n"
              "C-0003,LUBRICANTES SRL,MANNOL,LIQUIDO DE FRENOS,DOT4,2024-05-10\n"
              "C-0004,VALEOS SA,VALEOS,LAMPARAS,H4,2024-06-01\n"
              # Una marca que es una palabra común: no puede «aparecer» en cada descripción.
              "C-0005,FRENOS DEL OESTE SA,FRENO,PASTILLAS DE FRENO,,2024-07-01\n")
_CSV_PUNTO_Y_COMA = ("﻿N° de CHAS;EMPRESA;MARCA;Tipo de autoparte;Fecha\n"
                     "123;Frenos del Sur SRL;Frenosur;Discos de freno;01/02/2024\n")


def probar(L):
    ns = L.todo_lo_de_la_logica()
    c, conn = ns["c"], ns["conn"]
    g = ns["inflacion_desde"].__globals__
    fallas = []

    def esperar(nombre, real, esperado):
        if real != esperado:
            fallas.append(f"{nombre}: dio {real!r}, se esperaba {esperado!r}")

    # Las columnas, por nombre.
    esperar("columnas con acentos", ns["columnas_del_chas"](
        ["Nro. CHAS", "Razón Social", "Marca", "Autoparte", "Modelo / Código", "Fecha de Emisión"]),
        {"numero": 0, "empresa": 1, "marca": 2, "autoparte": 3, "detalle": 4, "fecha": 5})
    esperar("columnas en otro orden", ns["columnas_del_chas"](
        ["N° de CHAS", "EMPRESA", "MARCA", "Tipo de autoparte", "Fecha"]),
        {"numero": 0, "empresa": 1, "marca": 2, "autoparte": 3, "fecha": 4})
    # «Marca / Modelo» es la marca: se busca primero, si no se la quedaba el modelo.
    esperar("la marca antes que el modelo", ns["columnas_del_chas"](
        ["CHAS", "Marca / Modelo", "Autoparte"]).get("marca"), 1)
    filas, columnas, error = ns["leer_el_registro_chas"](_CSV_COMAS)
    esperar("leído: sin error", error, None)
    esperar("leído: renglones (sin el vacío)", len(filas), 5)
    esperar("leído: qué columna fue la marca", columnas.get("marca"), "Marca")
    esperar("leído: el primero", (filas[0]["numero"], filas[0]["marca"], filas[0]["autoparte"]),
            ("C-0001", "FRAS-LE", "PASTILLAS DE FRENO"))
    filas2, _c, error2 = ns["leer_el_registro_chas"](_CSV_PUNTO_Y_COMA)
    esperar("punto y coma con BOM", (error2, len(filas2), filas2[0]["marca"]),
            (None, 1, "Frenosur"))
    _f, _c, error3 = ns["leer_el_registro_chas"]("Columna A,Columna B\n1,2\n")
    esperar("sin marca ni empresa: dice qué columnas hay", "Columna A" in (error3 or ""), True)
    esperar("vacío", bool(ns["leer_el_registro_chas"]("")[2]), True)

    # A mano, en Windows-1252 (como lo guarda Excel en castellano).
    resumen, error = ns["cargar_el_registro_chas_a_mano"](_CSV_COMAS.encode("cp1252"), "chas.csv")
    esperar("a mano: sin error", error, None)
    esperar("a mano: certificados y marcas", (resumen["certificados"], resumen["marcas"]), (5, 4))
    esperar("a mano: guardado", c.execute("SELECT COUNT(*) FROM chas_emitidos").fetchone()[0], 5)
    esperar("a mano: la columna con acento se leyó bien",
            ns["resumen_del_chas"]()["columnas"].get("empresa"), "Razón Social")

    # Las marcas del catálogo contra el registro.
    esperar("FRAS-LE es FRAS LE", (ns["chas_de_la_marca"]("FRAS-LE") or {}).get("certificados"), 2)
    esperar("MANNOL LUBRICANTES es MANNOL",
            (ns["chas_de_la_marca"]("MANNOL LUBRICANTES") or {}).get("marca_en_el_registro"),
            "MANNOL")
    esperar("VALEO no es VALEOS", ns["chas_de_la_marca"]("VALEO"), None)
    esperar("muy corta, nada", ns["chas_de_la_marca"]("AB"), None)
    esperar("pastilla es de seguridad", ns["es_pieza_de_seguridad"]("PASTILLA DE FRENO GOL"), True)
    esperar("filtro no", ns["es_pieza_de_seguridad"]("FILTRO DE AIRE GOL"), False)
    esperar("líquido en inglés", ns["es_pieza_de_seguridad"]("Brake Fluid DOT-4 0,5L"), True)
    esperar("DOT 4 segundo", ns["es_pieza_de_seguridad"]("MN DOT 4 - 450 ml (Liquido de Frenos)"),
            True)
    esperar("lámparas en plural", ns["es_pieza_de_seguridad"]("LAMPARAS LED 11 WATTS"), True)
    # De la base real: nombran un faro o una lámpara, pero la pieza es otra.
    for no_es in ("Tecla faros antiniebla traseros. Peugeot 505.",
                  "Portatil para lampara 21 W. Conector con pinzas cromadas.",
                  "PORTALAMPARA INTERIOR VELERO",
                  "Llave de luces con reostato grande-Ford Falcon-Doble faro. Todos.",
                  "Lente para tecla iluminada. Faro antiniebla. Original"):
        esperar(f"no es de seguridad: {no_es[:25]}", ns["es_pieza_de_seguridad"](no_es), False)
    esperar("tapa de distribución no", ns["es_pieza_de_seguridad"]("CUBIERTA DISTRIBUCION"), False)
    for n_prod, (marca, desc) in enumerate((("FRAS-LE", "PASTILLA DE FRENO GOL"), ("FRAS-LE", "CINTA DE FRENO 147"),
                        ("DISCOS X", "DISCO DE FRENO VENT"), ("FILTROS Z", "FILTRO DE AIRE"),
                        # El distribuidor, con la marca del producto en el texto.
                        ("JL", "LAMPARA H4 12V 60/55W zocalo Valeos"),
                        ("JL", "LAMPARA H7 12V"), ("JL", "Tecla faros antiniebla"),
                        ("OEM / FABRICA", "PASTILLA DE FRENO ORIGINAL"))):
        mid = (c.execute("SELECT id FROM marcas WHERE nombre = ?", (marca,)).fetchone() or [None])[0]
        if mid is None:
            c.execute("INSERT INTO marcas (nombre, tipo) VALUES (?, ?)",
                      (marca, "OEM" if marca.startswith("OEM") else "PROVEEDOR"))
            mid = c.lastrowid
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
                  "VALUES (?, ?, ?, ?)", (f"P{n_prod}", f"P{n_prod}", desc, mid))
    conn.commit()
    contra = ns["marcas_del_catalogo_contra_el_chas"]()
    esperar("contra el registro: las de más piezas sin dato primero, sin la OEM",
            [(f["Marca"], f["Piezas de seguridad"], f["Con CHAS a la vista"],
              f["Marcas con CHAS que aparecen"]) for f in contra],
            [("DISCOS X", 1, 0, ""), ("JL", 2, 1, "VALEOS"), ("FRAS-LE", 2, 2, "FRAS LE")])
    esperar("en los resultados: solo las que tienen y venden piezas de seguridad",
            [m for m, _d in ns["chas_en_los_resultados"](
                [{"Marca": "FRAS-LE", "Descripcion": "PASTILLA DE FRENO"},
                 {"Marca": "MANNOL LUBRICANTES", "Descripcion": "ACEITE 5W30"},
                 {"Marca": "DISCOS X", "Descripcion": "DISCO DE FRENO"},
                 {"Marca": "JL", "Descripcion": "LAMPARA H4 zocalo Valeos"},
                 {"Marca": "JL", "Descripcion": "LAMPARA H1 Valeos"}])], ["FRAS LE", "VALEOS"])
    esperar("en la descripción, como palabra entera",
            ns["chas_de_la_pieza"]("JL", "LAMPARA H4 VALEOSX"), None)
    esperar("en la descripción, como palabra entera (adelante)",
            ns["chas_de_la_pieza"]("JL", "LAMPARA H4 XVALEOS"), None)
    esperar("una palabra común no es una marca",
            ns["chas_de_la_pieza"]("DISCOS X", "DISCO DE FRENO VENT"), None)
    esperar("buscar en el registro", [f["CHAS"] for f in ns["buscar_en_el_chas"]("fras le")],
            ["C-0002", "C-0001"])

    # El archivo más reciente del portal, por el mes del nombre.
    esperar("mes del archivo", ns["_mes_del_archivo"](
        "https://x/chas-emitidos-a-diciembre-2024.csv"), (2024, 12))
    portal = {"success": True, "result": {"resources": [
        {"url": "https://x/chas-emitidos-a-diciembre-2024.csv", "format": "CSV"},
        {"url": "https://x/chas-emitidos-a-marzo-2026.csv", "format": "CSV"},
        {"url": "https://x/diccionario.pdf", "format": "PDF"}]}}
    original = g["_pedir_json"]
    g["_pedir_json"] = lambda url, tiempo_maximo=4: portal
    esperar("el más reciente del portal", ns["archivo_mas_reciente_del_chas"](),
            "https://x/chas-emitidos-a-marzo-2026.csv")
    g["_pedir_json"] = lambda url, tiempo_maximo=4: None
    esperar("sin portal, el conocido", ns["archivo_mas_reciente_del_chas"](),
            ns["URL_CHAS_CONOCIDO"])

    # Bajarlo: solo si pasó un mes, o forzado; y un archivo gigante no se carga.
    import requests

    class _R:
        def __init__(self, cuerpo):
            self.cuerpo = cuerpo

        def raise_for_status(self):
            pass

        def iter_content(self, n):
            for i in range(0, len(self.cuerpo), n):
                yield self.cuerpo[i:i + n]
    pedidos = []
    requests_get = requests.get
    requests.get = lambda url, **k: pedidos.append(url) or _R(_CSV_PUNTO_Y_COMA.encode("utf-8"))
    try:
        esperar("recién cargado: no baja", ns["actualizar_el_registro_chas"](), None)
        esperar("forzado: baja", ns["actualizar_el_registro_chas"](forzar=True)["certificados"], 1)
        esperar("reemplazó el anterior", c.execute("SELECT COUNT(*) FROM chas_emitidos").fetchone()[0], 1)
        esperar("y se olvidó lo de antes", ns["chas_de_la_marca"]("FRAS-LE"), None)
        g["TAMANIO_MAXIMO_DEL_CHAS"] = 10
        try:
            ns["actualizar_el_registro_chas"](forzar=True)
            fallas.append("gigante: tendría que haber fallado")
        except ValueError:
            pass
        esperar("gigante: quedó el anterior", c.execute("SELECT COUNT(*) FROM chas_emitidos").fetchone()[0], 1)
    finally:
        requests.get = requests_get
        g["_pedir_json"] = original
    return fallas


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_chas_")
    try:
        fallas = probar(_cargar_la_logica(carpeta))
        for f in fallas:
            print("   ✗", f)
        print("✅ CHAS: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

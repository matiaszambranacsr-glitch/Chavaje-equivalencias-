"""Pruebas de la REVISIÓN de equivalencias: que las reglas no se equivoquen con pares conocidos.

Uso:
    python3 pruebas_de_la_revision.py                 # los pares de muestra, siempre
    python3 pruebas_de_la_revision.py --base copia.db # además, tus aprobaciones de esa base

Por qué existe: cada regla nueva del análisis («modelos distintos», «años distintos», «motores
distintos»…) se probó contra pares reales antes de subirla, pero con scripts sueltos que no
quedaban en ningún lado. La regla siguiente podía romper lo que la anterior había arreglado —o
bajar a rojo un par que aprobaste— y nadie se iba a enterar. Esto deja escrito lo que ya se sabe.

PARES DE MUESTRA: sacados de la cola real y revisados a mano, con lo que tienen que dar. «misma»
es que las descripciones concuerden; «distinta», que la app diga por qué son piezas distintas (un
motivo que tumba el par). Si se agrega una regla, se agregan acá los casos que la motivaron.

CON --base: arma una copia de la base en una carpeta temporal, pone todos los pares que
aprobaste como si recién llegaran —sin tus decisiones ni lo aprendido de ellas, para que no se
copien la respuesta— y los puntúa con el análisis de siempre. Falla si más del 1 % de lo aprobado
cae en 🔴. Hoy, sobre la base de prueba de 13.021 aprobados, caen 86 (0,7 %): son vínculos por
código cuyo código las reglas actuales ya no tomarían.

Nunca toca la base de trabajo: corre en una carpeta temporal, con una base propia.
"""
import os
import shutil
import sqlite3
import sys
import tempfile

# Los modelos de auto la app los aprende del catálogo (ver modelos_de_marca()): con una base
# vacía no reconoce ninguno. Los casos que dependen de eso se prueban solo con --base.
NECESITA_EL_CATALOGO = "necesita el catálogo"

# (descripción A, descripción B, lo que tiene que dar, de dónde salió[, NECESITA_EL_CATALOGO])
PARES_DE_MUESTRA = [
    # --- la misma pieza escrita distinto: tienen que concordar ---
    ("Jta.Tapa Cilindros Renault Master - Trafic - motor G9U 2463cc.",
     "Junta Tapa de Cilindros RENAULT (ESP 1.50mm) MASTER TRAFIC NISSAN : PRIMASTAR INTERSTAR - "
     "2,5 - G9U-720/724/730/750/754 (8200406743) (Metal Graf®)", "misma", "TARANTO / ILLINOIS"),
    ("Jta.Tapa Cil.ASTRA KADETT VECTRA",
     "Junta Tapa de Cilindros CHEVROLET MONZA KADETT ASTRA VECTRA ZAFIRA - 2,0/2,2 - "
     "C20NE/SEH/SER/NEF OHC", "misma", "TARANTO / ILLINOIS"),
    ("Jta.Carter DEUTZ F5L 913", "Junta para Cárter DEUTZ 913 TRACTOR 5 CIL. - 5,1 - F5L (3018944)",
     "misma", "TARANTO / ILLINOIS"),
    ("Sensor de rotacion Hyundai Accent Elantra .",
     "SENSOR DE ROTACION 30173 HYUNDAI EXCEL -ELANTRA -ACCENT 1 3 Y 1 15 16V", "misma",
     "CRI-FA / FISPA"),
    ("Sensor de presion de colector MAP Citroen Berlingo 1.4 1.8 Xsara Saxo",
     "SENSOR MAP 40005 CITROEN BERLINGO - C5 - SAXO - XSARA - XANTIA - XM", "misma",
     "CRI-FA / FISPA"),
    ("Junta Distribucion VW GOL 1000", "JTA T.DIST VOLKSWAGEN GOL 1000", "misma",
     "TARANTO / IMPERIAL"),
    ("Jta.Tapa Valv. Ford F100-150 91/", "JTA T.V. FORD F100 4.9", "misma", "abreviatura T.V."),
    ("Jta.Carter FIAT 1100", "JTA CARTER FIAT 128/147 1100/", "misma", "TARANTO / IMPERIAL"),
    ("Jta.Tapa Cil. MAXION LAND ROVER", "JTA T.C. MAXION ROVER 1.60 mm", "misma",
     "abreviatura T.C."),
    ("JUNTA BOMBA VACIO A BLOCK PERKINS", "JTA BBA VACIO PERKINS 1006", "misma", "abreviatura BBA"),
    ("JTA C.VEL. FORD F100", "Juntas para caja de velocidad FORD F100", "misma",
     "abreviatura C.VEL."),
    ("Jta.Tapa Cil. SUZUKI CULTUS G13B 1298CC 1996/...",
     "Junta Tapa de Cilindros SUZUKI SWIFT SAMURAI CULTUS SIDEKICK JIMNY BARINA - 1,3 - G13B/A/K",
     "misma", "motores de la misma familia"),

    # --- piezas distintas: la app tiene que decir por qué ---
    ("Jgo.Jtas. ROVER 214/216/218/414/416", "JTA T.C. ROVER 111/214 11/14K", "distinta",
     "juego de juntas contra junta suelta"),
    ("Juego de juntas para Caja de Velocidad FORD F350", "Jta.Tapa Valvulas FORD F350", "distinta",
     "juego contra junta suelta"),
    ("Sonda Lambda Planar Volkswagen Gol Fox Voyage 1.0 16 Saveiro 1.6 Suran",
     "SONDA LAMBDA LECS012 GM ASTRA 1 8 - CELTA 1 4 GLS - CORSA 1 0 - VW GOLF REF ORIG", "distinta",
     "misma marca, ningún modelo en común", NECESITA_EL_CATALOGO),
    ("Junta Caja JHON DEERE", "JTA T.C.J.DEERE 1550/9650-6081", "distinta",
     "caja contra tapa de cilindros"),
    ("Jta.Tapa Cil. HONDA CIVIC 1500 EW 1488CC 12V 1984/1989",
     "Junta Tapa de Cilindros HONDA CIVIC 2015/... - 1.5 - L15B8 (MLS)", "distinta",
     "años que no se cruzan"),
    ("Termostato carcasa termostática con sensor Ford Transit 2,0 2016/2022 .",
     "TERMOSTATO CON CARCASA 97024 FORD FOCUS ECOSPORT MONDEO III 2006-2007 TRANSIT 2004-2006",
     "distinta", "años que no se cruzan"),
    ("Jta.Carter DEUTZ F4L 913", "Junta para Cárter DEUTZ 913 TRACTOR 5 CIL. - 5,1 - F5L (3018944)",
     "distinta", "cuatro cilindros contra cinco"),
    ("Jta.Tapa Cil. HYUNDAI SONATA TCI TUCSON TCI D4EA 16V 2005/...",
     "Junta Tapa de Cilindros HYUNDAI SONATA 2007/... RONDO 2006/... MAGENTIS 2005/... - 2.0 - "
     "G4KA", "distinta", "diésel D4EA contra nafta G4KA"),
]


def _cargar_la_logica(carpeta):
    """La lógica de la app, con una base vacía en `carpeta`."""
    raiz = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, raiz)
    os.chdir(carpeta)
    import logica
    return logica


def probar_pares_de_muestra(logica, con_catalogo):
    """Devuelve (fallas, cuántos se probaron)."""
    fallas, probados = [], 0
    for desc_a, desc_b, esperado, origen, *extra in PARES_DE_MUESTRA:
        if NECESITA_EL_CATALOGO in extra and not con_catalogo:
            continue
        probados += 1
        fa, fb = logica.firma_de_producto(desc_a), logica.firma_de_producto(desc_b)
        ok, motivo = logica.firmas_compatibles(fa, fb)
        if esperado == "misma" and not ok:
            fallas.append(f"«{desc_a[:40]}» / «{desc_b[:40]}» ({origen}): tenían que concordar "
                          f"y dio «{motivo}»")
        if esperado == "distinta" and (ok or not motivo.startswith(
                logica._MOTIVOS_QUE_CONTRADICEN)):
            fallas.append(f"«{desc_a[:40]}» / «{desc_b[:40]}» ({origen}): tenían que ser piezas "
                          f"distintas y dio {'que concuerdan' if ok else f'«{motivo}»'}")
    return fallas, probados


def preparar_la_base_de_aprobaciones(ruta_base, destino):
    """Copia la base a `destino` con tus aprobaciones puestas como si recién llegaran: sin tus
    decisiones ni lo aprendido de ellas, para que el análisis no se copie la respuesta. Se hace
    ANTES de cargar la lógica, que abre la conexión al arrancar. Devuelve cuántos pares quedan."""
    shutil.copy(ruta_base, destino)
    con = sqlite3.connect(destino)
    aprobados = {(min(a, b), max(a, b)) for a, b in con.execute(
        "SELECT producto_a_id, producto_b_id FROM equivalencias_revisadas WHERE decision = 'ok'")}
    pares = [(a, b) for a, b in sorted(aprobados)
             if con.execute("SELECT COUNT(*) FROM productos WHERE id IN (?, ?)",
                            (a, b)).fetchone()[0] == 2]
    con.execute("DELETE FROM equivalencias_revisadas")
    con.executemany("DELETE FROM equivalencias WHERE MIN(producto_a_id, producto_b_id) = ? "
                    "AND MAX(producto_a_id, producto_b_id) = ?", pares)
    con.executemany("DELETE FROM equivalencias_pendientes WHERE MIN(producto_a_id, "
                    "producto_b_id) = ? AND MAX(producto_a_id, producto_b_id) = ?", pares)
    con.executemany("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, "
                    "lote) VALUES (?, ?, 'lista_proveedor', ?)",
                    [(a, b, LOTE_DE_LA_PRUEBA) for a, b in pares])
    con.commit()
    con.close()
    return len(pares)


LOTE_DE_LA_PRUEBA = "PRUEBA DE APROBACIONES"


def probar_aprobaciones(logica, cuantos):
    """Puntúa las aprobaciones preparadas. Devuelve (fallas, resumen)."""
    if not cuantos:
        return [], "la base no tiene aprobaciones con los dos productos cargados"
    limpias, sospechosas, relacionadas = logica.analizar_lote_pendiente(LOTE_DE_LA_PRUEBA,
                                                                        limite=None)
    todos = limpias + sospechosas + relacionadas
    rojos = [f for f in todos if (f.get("confianza") or 0) < 30]
    resumen = (f"{cuantos:,} aprobados: {len(limpias):,} limpios, {len(sospechosas):,} en "
               f"revisión, {len(rojos):,} en rojo ({100 * len(rojos) / cuantos:.1f} %)")
    fallas = []
    if len(rojos) > 0.01 * cuantos:
        fallas.append(f"más del 1 % de lo aprobado cae en rojo: {resumen}. Ejemplos: "
                      + "; ".join(f"{f.get('cod_a')} / {f.get('cod_b')}: "
                                  f"{(f.get('alarmas') or [''])[0][:70]}" for f in rojos[:5]))
    return fallas, resumen


def main():
    ruta_base = None
    if "--base" in sys.argv:
        ruta_base = os.path.abspath(sys.argv[sys.argv.index("--base") + 1])
    carpeta = tempfile.mkdtemp(prefix="pruebas_revision_")
    try:
        cuantos = (preparar_la_base_de_aprobaciones(
            ruta_base, os.path.join(carpeta, "equivalencias_app.db")) if ruta_base else 0)
        logica = _cargar_la_logica(carpeta)
        fallas, probados = probar_pares_de_muestra(logica, con_catalogo=bool(ruta_base))
        salteados = len(PARES_DE_MUESTRA) - probados
        print(f"{'✅' if not fallas else '❌'} pares de muestra: {probados - len(fallas)} de "
              f"{probados} bien" + (f" ({salteados} necesitan el catálogo: correlo con --base)"
                                    if salteados else ""))
        if ruta_base:
            f2, resumen = probar_aprobaciones(logica, cuantos)
            print(f"{'✅' if not f2 else '❌'} aprobaciones: {resumen}")
            fallas += f2
        for f in fallas:
            print("   ✗", f)
        print("todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

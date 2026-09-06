"""Núcleo portable del sistema de equivalencias de repuestos.

Es la lógica sola: no importa Streamlit ni depende de cómo esté armada la interfaz. Se puede
usar desde otro sistema —una API, un proceso de importación por lotes, otra app— trayendo el
paquete entero o un módulo suelto.

    errores.py        registro de errores ignorados. No depende de nada.
    codigos.py        limpiar y reconocer códigos; sacar el OEM de una descripción.
    vehiculos.py      marcas de auto, familias de repuesto, medidas desde el texto.
    planillas.py      leer Excel/CSV/PDF y adivinar qué es cada columna.
    equivalencias.py  el SQL recursivo que encadena saltos entre proveedores (SQLite).

Los cuatro primeros son funciones puras sobre strings y listas: se prueban sin base de datos.
Solo equivalencias.py necesita SQLite, y recibe el cursor por parámetro.

Dependencias externas: openpyxl (Excel) y, opcionalmente, pdfplumber (PDF). El resto es
biblioteca estándar.

Uso mínimo de punta a punta:

    import sqlite3
    from nucleo import planillas, codigos, equivalencias

    filas = planillas.leer_excel("lista_proveedor.xlsx")
    mapa  = planillas.adivinar_columnas(filas[0])
    if sum(1 for x in filas[0] if str(x).strip()) < 2:      # lista sin encabezado
        mapa = planillas.adivinar_columnas_por_datos(filas[1:60], len(filas[0]))

    con = equivalencias.preparar(sqlite3.connect("equivalencias.db"))
    ...  # cargar productos y vínculos con el mapeo de columnas
    resultados = equivalencias.buscar_por_codigo(con.cursor(), codigos.sanitizar("036115561G"))

Para sacar el código de fábrica de adentro de la descripción hace falta mirar la lista ENTERA
primero, no fila por fila — el porqué está en codigos.codigos_confiables_de_descripciones():

    pares  = [(descripcion, codigo_de_esa_fila) for ...]
    buenos, _ = codigos.codigos_confiables_de_descripciones(pares)
    oem = [x for x in codigos.extraer_codigos_de_texto(desc, codigo_propio=cod)
           if codigos.sanitizar(x) in buenos]
"""

from . import codigos, equivalencias, errores, planillas, vehiculos

__all__ = ["codigos", "equivalencias", "errores", "planillas", "vehiculos"]

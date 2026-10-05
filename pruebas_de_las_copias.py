"""Pruebas de la copia de seguridad: qué fotos sobreviven a un reinicio de la app.

Uso:
    python3 pruebas_de_las_copias.py

Por qué existe: la copia que la app sube a GitHub —con la que arranca después de cada reinicio
o actualización— les sacaba TODAS las fotos para no pasarse de los 100 MB. Las de internet se
volvían a bajar por su link, pero las subidas a mano no tienen link: se perdían. Pasó: se
subieron fotos, la app se actualizó, y la búsqueda por foto decía «no hay ninguna foto
cargada». Ver _sacar_las_fotos() en logica/calidad.py.

Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import io
import os
import shutil
import sqlite3
import sys
import tempfile


def _cargar_la_logica(carpeta):
    raiz = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, raiz)
    os.chdir(carpeta)
    import logica
    return logica


def _foto(color):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (300, 300), color)
    dibujo = ImageDraw.Draw(img)
    for i in range(0, 300, 23):           # algo de detalle, para que tenga firma
        dibujo.line((i, 0, 300 - i, 300), fill=(255 - i % 255, i % 255, 90), width=3)
        dibujo.ellipse((i % 200, (i * 7) % 200, i % 200 + 40, (i * 7) % 200 + 25),
                       outline=(0, 0, 0), width=2)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def probar(L):
    ns = L.todo_lo_de_la_logica()
    c = ns["c"]
    fallas = []

    def esperar(nombre, real, esperado):
        if real != esperado:
            fallas.append(f"{nombre}: dio {real!r}, se esperaba {esperado!r}")

    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('PRUEBA', 'PROVEEDOR')")
    mid = c.execute("SELECT id FROM marcas WHERE nombre = 'PRUEBA'").fetchone()[0]
    ids = []
    for i in range(3):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
                  "VALUES (?, ?, ?, ?)", (f"P{i}", f"P{i}", f"PIEZA {i}", mid))
        ids.append(c.lastrowid)
    ns["conn"].commit()
    propia, _ = ns["agregar_foto_producto"](ids[0], _foto((200, 30, 30)))                 # del teléfono
    ns["agregar_foto_producto"](ids[1], _foto((30, 200, 30)), origen="url",
                                fuente="https://proveedor.example/ficha")                   # elegida de una página
    ns["agregar_foto_producto"](ids[2], _foto((30, 30, 200)), origen="ficha",
                                fuente="https://proveedor.example/foto.jpg")                # traída sola
    c.execute("UPDATE productos SET imagen_url = 'https://proveedor.example/foto.jpg' WHERE id = ?",
              (ids[2],))
    ns["conn"].commit()

    copia = os.path.abspath("copia.db")
    with open(copia, "wb") as f:
        f.write(ns["generar_backup_sin_fotos"]())
    otra = sqlite3.connect(copia)
    esperar("fotos en la copia: las propias sí, la traída sola no",
            sorted(r[0] for r in otra.execute("SELECT origen FROM producto_fotos")),
            ["subida", "url"])
    esperar("la foto propia va entera, con su firma",
            otra.execute("SELECT imagen_data LIKE 'data:%', firma_blob IS NOT NULL "
                         "FROM producto_fotos WHERE origen = 'subida'").fetchone(),
            (1, int(c.execute("SELECT firma_blob IS NOT NULL FROM producto_fotos WHERE id = ?",
                              (propia,)).fetchone()[0])))
    esperar("la traída sola queda con su link",
            otra.execute("SELECT imagen_url FROM productos WHERE id = ?", (ids[2],)).fetchone()[0],
            "https://proveedor.example/foto.jpg")
    esperar("la ficha de la propia, sin la foto grande en la copia",
            otra.execute("SELECT imagen_url IS NULL, imagen_thumb IS NOT NULL FROM productos "
                         "WHERE id = ?", (ids[0],)).fetchone(), (1, 1))

    # Al restaurar, la foto propia vuelve a ser la de su ficha.
    ns["pedir_de_nuevo_las_fotos"](otra)
    esperar("restaurada: la ficha vuelve a tener su foto",
            otra.execute("SELECT imagen_url LIKE 'data:%' FROM productos WHERE id IN (?, ?) "
                         "ORDER BY id", (ids[0], ids[1])).fetchall(), [(1,), (1,)])
    otra.close()

    # El tope: si las propias no entran, quedan las más nuevas y se avisa cuántas no.
    g = ns["inflacion_desde"].__globals__
    tope = g["TOPE_FOTOS_PROPIAS_EN_LA_COPIA"]
    g["TOPE_FOTOS_PROPIAS_EN_LA_COPIA"] = 1
    try:
        ns["generar_backup_sin_fotos"]()
        esperar("tope: cuántas no entraron", ns["fotos_propias_fuera_de_la_copia"](), 2)
    finally:
        g["TOPE_FOTOS_PROPIAS_EN_LA_COPIA"] = tope
    ns["generar_backup_sin_fotos"]()
    esperar("sin tope: entran todas", ns["fotos_propias_fuera_de_la_copia"](), 0)
    return fallas


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_copias_")
    try:
        fallas = probar(_cargar_la_logica(carpeta))
        for f in fallas:
            print("   ✗", f)
        print("✅ copias: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

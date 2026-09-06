"""Arma el paquete nucleo/ sacando el código TEXTUAL de app.py.
No se reescribe nada a mano: se copian los segmentos exactos, así el paquete y la app dicen
literalmente lo mismo y no hay forma de que se separen por una transcripción."""
import ast, os, io

SRC = open("/home/user/Chavaje-equivalencias-/app.py", encoding="utf-8").read()
ARBOL = ast.parse(SRC)

BLOQUES = {}   # nombre -> texto exacto
for n in ARBOL.body:
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        BLOQUES[n.name] = ast.get_source_segment(SRC, n)
    elif isinstance(n, ast.Assign):
        for t in n.targets:
            if isinstance(t, ast.Name):
                BLOQUES[t.id] = ast.get_source_segment(SRC, n)

def comentario_previo(nombre):
    """Se lleva también el comentario que va JUSTO ARRIBA del bloque. Esos comentarios explican
    por qué la cosa está hecha así, que es lo único que no se puede deducir leyendo el código."""
    txt = BLOQUES[nombre]
    i = SRC.index(txt)
    antes = SRC[:i].rstrip("\n").split("\n")
    junta = []
    for linea in reversed(antes):
        if linea.startswith("#") or (linea.strip().startswith("#") and not linea.startswith(" " * 5)):
            junta.append(linea)
        elif linea.strip() == "" and junta:
            break
        else:
            break
    return "\n".join(reversed(junta))

def armar(nombres):
    partes = []
    for nm in nombres:
        if nm not in BLOQUES:
            raise SystemExit(f"falta en app.py: {nm}")
        prev = comentario_previo(nm)
        partes.append((prev + "\n" if prev else "") + BLOQUES[nm])
    return "\n\n\n".join(partes) + "\n"

def escribir(archivo, cabecera, nombres, extra=""):
    ruta = "/home/user/Chavaje-equivalencias-/nucleo/" + archivo
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(cabecera.rstrip() + "\n\n\n" + armar(nombres))
        if extra:
            f.write("\n\n" + extra.strip() + "\n")
    print(f"  {archivo}: {len(nombres)} bloques, {sum(1 for _ in open(ruta))} líneas")

# ---------------------------------------------------------------- errores
escribir("errores.py", '''"""Registro de los errores que la app decide ignorar.

Está aparte y sin dependencias porque lo usan todos los demás módulos: si esto importara algo,
ese algo no podría anotar sus propios errores."""
from datetime import datetime
''', ["MAXIMO_ERRORES_ANOTADOS", "_ULTIMOS_ERRORES", "anotar_error"], '''
def errores_anotados():
    """Los últimos errores ignorados, del más viejo al más nuevo. Para mostrarlos en una
    pantalla de diagnóstico sin tocar la lista de adentro."""
    return list(_ULTIMOS_ERRORES)
''')

# ---------------------------------------------------------------- codigos
escribir("codigos.py", '''"""Todo lo que tiene que ver con LIMPIAR y RECONOCER códigos de repuesto.

Es el corazón del sistema y no depende de nada: ni de la base, ni de la interfaz, ni de cómo se
leyó el archivo. Se puede probar con strings sueltos.

El orden importa: primero se decide si algo ES un código (sanitizar, es_codigo_util), después
se parte una celda que trae varios (dividir_codigos), y recién al final se intenta adivinar
códigos escondidos adentro de una descripción (extraer_codigos_de_texto), que es lo más
delicado porque ahí se está SUPONIENDO."""
import re
from collections import Counter

from .errores import anotar_error
''', ["es_fecha_disfrazada", "sanitizar", "LARGO_MINIMO_NUMERICO", "es_codigo_util",
      "_partir_por_barra", "dividir_codigos", "codigo_sospechoso",
      "TOPE_REPETICIONES_EN_DESCRIPCION", "codigos_confiables_de_descripciones",
      "_es_el_codigo_propio_con_texto", "extraer_codigos_de_texto",
      "normalizar_texto", "valor_o_vacio", "valor_codigo"])

# ---------------------------------------------------------------- vehiculos
escribir("vehiculos.py", '''"""Lo que sabe de AUTOS y de tipos de repuesto: marcas de vehículo, familias de pieza, y cómo
leer una descripción de proveedor para sacar de ahí el modelo, los años y las medidas.

Se usa para dos cosas distintas y conviene no confundirlas:
  - despegar texto que vino sin espacios ('DespieceCHEVROLETCAPUCHON'), que es limpieza y se
    puede aplicar siempre;
  - DEDUCIR datos (medidas, aplicaciones), que es suponer, y por eso cada función de acá es
    conservadora a propósito: ante la duda no devuelve nada."""
import re
import unicodedata

from .errores import anotar_error
from .codigos import normalizar_texto, sanitizar
''', ["MARCAS_VEHICULO", "_MARCAS_RIESGOSAS", "MARCAS_PARA_DESPEGAR", "_RE_PEGADO_MAYUS",
      "_RE_MARCAS_PEGADAS", "_RE_ESPACIOS", "separar_texto_pegado", "separar_por_marca_vehiculo",
      "FAMILIAS_REPUESTO", "_normalizar_desc", "clasificar_repuesto", "extraer_anios",
      "PALABRAS_NO_MODELO", "_RE_PIEZA_POR_MEDIDA", "medidas_desde_descripcion"])

# ---------------------------------------------------------------- planillas
escribir("planillas.py", '''"""Leer una lista de proveedor y entender qué es cada columna.

Dos problemas de verdad, los dos vistos en listas reales:
  - el archivo puede venir en Excel, CSV o PDF, con la codificación y el separador que sea;
  - puede no tener encabezado ninguno, y entonces hay que adivinar qué columna es el código,
    cuál el precio y cuál la descripción mirando los VALORES (adivinar_columnas_por_datos).
    De cinco listas reales, cuatro no traían encabezado.

diagnosticar_lista() simula la importación sobre una muestra y cuenta qué va a pasar con cada
fila, para poder avisar ANTES de cargar y no después."""
import re
import unicodedata

from .errores import anotar_error
from .codigos import (dividir_codigos, es_codigo_util, es_fecha_disfrazada, sanitizar,
                      valor_o_vacio)
''', ["_decodificar_texto", "_detectar_separador", "leer_excel", "leer_numero",
      "PISTAS_COLUMNAS", "adivinar_columnas", "_perfil_de_columna",
      "adivinar_columnas_por_datos", "diagnosticar_lista"])

# ---------------------------------------------------------------- equivalencias
# Acá sí hay que ADAPTAR, no solo copiar: en app.py estas funciones usan un cursor global 'c' y
# un candado 'db_lock' que son de la app. En el paquete reciben el cursor por parámetro, que es
# lo que permite usarlas desde otro sistema con su propia conexión.
def adaptar_a_cursor(texto, nombre):
    import re as _re
    # la firma pasa a recibir el cursor primero
    texto = texto.replace(f"def {nombre}(", f"def {nombre}(cur, ", 1)
    # se saca el 'with db_lock:' y se desindenta su bloque: el candado es de la app, no del núcleo
    lineas = texto.split("\n")
    salida, quitando = [], None
    for ln in lineas:
        if ln.strip() == "with db_lock:":
            quitando = len(ln) - len(ln.lstrip())
            continue
        if quitando is not None:
            if ln.strip() == "":
                salida.append(ln); continue
            ind = len(ln) - len(ln.lstrip())
            if ind > quitando:
                salida.append(ln[4:]); continue
            quitando = None
        salida.append(ln)
    texto = "\n".join(salida)
    texto = _re.sub(r'\bc\.execute\(', 'cur.execute(', texto)
    texto = _re.sub(r'\bc\.fetchall\(\)', 'cur.fetchall()', texto)
    texto = _re.sub(r'\bfilas_a_listas\(c\)', 'filas_a_listas(cur)', texto)
    return texto

CABECERA_EQ = '''"""La búsqueda de equivalencias: el SQL recursivo que encadena saltos entre proveedores.

Asume SQLite (usa WITH RECURSIVE y GLOB). Se necesitan tres tablas —marcas, productos,
equivalencias—; ESQUEMA las crea tal cual las espera la consulta.

A diferencia del resto del paquete, acá las funciones reciben el CURSOR por parámetro. En la app
original toman uno global; se cambió a propósito para que el otro sistema use su propia conexión
y su propio manejo de concurrencia (en la app el candado es de la app, no de la búsqueda).

Las dos formas de llegar de un producto a otro están explicadas adentro de buscar_por_codigo();
la segunda —mismo código bajo otra marca— es la que hace que dos listas de proveedores distintos
se crucen, y es lo que faltaba cuando la búsqueda "solo relacionaba dentro del mismo proveedor".
"""
from urllib.parse import quote

from .errores import anotar_error

ESQUEMA = """
CREATE TABLE IF NOT EXISTS marcas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    -- 'PROVEEDOR' o 'OEM'. El tipo ordena los resultados: el código de fábrica primero.
    tipo TEXT NOT NULL DEFAULT 'PROVEEDOR',
    url_ficha_template TEXT
);

CREATE TABLE IF NOT EXISTS productos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_raw TEXT NOT NULL,          -- como lo escribió el proveedor, para mostrar
    codigo_clean TEXT NOT NULL,        -- pasado por sanitizar(), para buscar
    descripcion TEXT,
    marca_id INTEGER NOT NULL REFERENCES marcas(id) ON DELETE CASCADE,
    precio REAL, precio_costo REAL, stock INTEGER DEFAULT 0,
    favorito INTEGER DEFAULT 0, imagen_url TEXT, imagen_thumb TEXT,
    -- el mismo código puede existir en varias marcas: son productos distintos a propósito
    UNIQUE(codigo_clean, marca_id)
);
CREATE INDEX IF NOT EXISTS idx_productos_clean ON productos(codigo_clean);

CREATE TABLE IF NOT EXISTS equivalencias (
    producto_a_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
    producto_b_id INTEGER NOT NULL REFERENCES productos(id) ON DELETE CASCADE,
    confianza INTEGER,                 -- 0..100; NULL en los vínculos viejos, se toma como 50
    verificada INTEGER DEFAULT 0,
    nivel TEXT, nota TEXT,
    PRIMARY KEY (producto_a_id, producto_b_id)
);
CREATE INDEX IF NOT EXISTS idx_eq_a ON equivalencias(producto_a_id);
CREATE INDEX IF NOT EXISTS idx_eq_b ON equivalencias(producto_b_id);
"""


def preparar(conexion):
    """Crea las tablas si no están y deja la conexión devolviendo filas por nombre de columna,
    que es lo que espera filas_a_listas()."""
    import sqlite3
    conexion.row_factory = sqlite3.Row
    conexion.executescript(ESQUEMA)
    return conexion
'''

cuerpo = "\n\n\n".join([
    BLOQUES["filas_a_listas"],
    (comentario_previo("buscar_por_codigo") + "\n" if comentario_previo("buscar_por_codigo") else "")
    + adaptar_a_cursor(BLOQUES["buscar_por_codigo"], "buscar_por_codigo"),
    adaptar_a_cursor(BLOQUES["equivalentes_mas_alla_del_tope"], "equivalentes_mas_alla_del_tope"),
])
with open("/home/user/Chavaje-equivalencias-/nucleo/equivalencias.py", "w", encoding="utf-8") as f:
    f.write(CABECERA_EQ.rstrip() + "\n\n\n" + cuerpo + "\n")
print("  equivalencias.py escrito")

# ---------------------------------------------------------------- ajustes de paquete
# app.py es UN archivo: todo comparte el mismo espacio de nombres y los imports están arriba de
# todo. Al partirlo en módulos hay que decir en cada uno qué usa, y mover alguna constante al
# módulo de quien realmente la usa. Se hace acá y no a mano para que regenerar el paquete
# vuelva a dar exactamente lo mismo.
D = "/home/user/Chavaje-equivalencias-/nucleo/"

# _RE_PIEZA_POR_MEDIDA venía junto a las medidas, pero el único que lo usa es codigo_sospechoso.
# Se muda a codigos.py: si se quedara en vehiculos.py, codigos tendría que importar de vehiculos
# y vehiculos ya importa de codigos — un import circular por una constante.
v = open(D + "vehiculos.py", encoding="utf-8").read().split("\n")
ini = next(i for i, l in enumerate(v) if l.startswith("# Piezas que se identifican POR SU MEDIDA"))
fin = next(i for i, l in enumerate(v) if l.startswith("    r'RULEMAN|RODAMIENTO"))
bloque = "\n".join(v[ini:fin + 1])
del v[ini:fin + 2]
open(D + "vehiculos.py", "w", encoding="utf-8").write("\n".join(v))

s = open(D + "codigos.py", encoding="utf-8").read()
s = s.replace("import re\nfrom collections import Counter\n",
              "import re\nimport unicodedata\nfrom collections import Counter\n", 1)
s = s.replace("    from collections import Counter\n    conteo = Counter()", "    conteo = Counter()", 1)
i = s.index("def codigo_sospechoso(")
j = s.rfind("\n\n\n", 0, i) + 3
open(D + "codigos.py", "w", encoding="utf-8").write(s[:j] + bloque.rstrip() + "\n\n\n" + s[j:])

e = open(D + "equivalencias.py", encoding="utf-8").read()
e = e.replace("from urllib.parse import quote", "import sqlite3\nfrom urllib.parse import quote", 1)
e = e.replace("    import sqlite3\n    conexion.row_factory", "    conexion.row_factory", 1)
open(D + "equivalencias.py", "w", encoding="utf-8").write(e)

p = open(D + "planillas.py", encoding="utf-8").read()
p = p.replace("import re\nimport unicodedata\n",
              "import re\nimport unicodedata\n\nfrom openpyxl import load_workbook\n", 1)
p = p.replace("                      valor_o_vacio)", "                      valor_codigo, valor_o_vacio)", 1)
open(D + "planillas.py", "w", encoding="utf-8").write(p)
print("  ajustes de paquete aplicados")

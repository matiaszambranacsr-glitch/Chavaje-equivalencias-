"""La búsqueda de equivalencias: el SQL recursivo que encadena saltos entre proveedores.

Asume SQLite (usa WITH RECURSIVE y GLOB). Se necesitan tres tablas —marcas, productos,
equivalencias—; ESQUEMA las crea tal cual las espera la consulta.

A diferencia del resto del paquete, acá las funciones reciben el CURSOR por parámetro. En la app
original toman uno global; se cambió a propósito para que el otro sistema use su propia conexión
y su propio manejo de concurrencia (en la app el candado es de la app, no de la búsqueda).

Las dos formas de llegar de un producto a otro están explicadas adentro de buscar_por_codigo();
la segunda —mismo código bajo otra marca— es la que hace que dos listas de proveedores distintos
se crucen, y es lo que faltaba cuando la búsqueda "solo relacionaba dentro del mismo proveedor".
"""
import sqlite3
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
    conexion.row_factory = sqlite3.Row
    conexion.executescript(ESQUEMA)
    return conexion


def filas_a_listas(cursor):
    """Convierte el resultado de un cursor (sqlite3.Row) en una lista de diccionarios."""
    return [dict(row) for row in cursor.fetchall()]


def buscar_por_codigo(cur, clean_code, marca_filtro="Todas", max_saltos=None):
    """Busca un código y todo lo que esté encadenado con él.

    La búsqueda es TRANSITIVA: si la lista A dice que el 1 equivale al 2, y la lista B dice que
    el 2 equivale al 3, buscar el 1 también trae el 3. Eso es lo que la hace potente, y también
    lo que la hace frágil: un solo vínculo mal cargado fusiona dos familias de repuestos que no
    tienen nada que ver, y a partir de ahí la búsqueda devuelve cosas que no entran.

    Por eso ahora se cuenta a cuántos SALTOS está cada resultado del código buscado. Un salto es
    un vínculo directo: alguien lo puso en la misma fila. Cinco saltos es una cadena larga donde
    cualquier eslabón puede estar mal. Con max_saltos se corta la cadena."""
    tope = int(max_saltos) if max_saltos else 99
    # La consulta arrastra, además de los saltos, la confianza del ESLABÓN MÁS DÉBIL del camino.
    # Es lo que faltaba para poder confiar en un resultado: no alcanza con saber que está a dos
    # saltos, hace falta saber si esos dos saltos son sólidos. Una cadena vale lo que su eslabón
    # más flojo, así que se va guardando el mínimo. Los vínculos viejos, todavía sin puntuar,
    # cuentan como 50 (ni a favor ni en contra) para no ensuciar el resultado.
    # Dos formas de llegar de un producto a otro, y hacían falta las dos:
    #
    #  1) por un VÍNCULO cargado (la lista del proveedor dijo que equivalen). Cuesta un salto.
    #
    #  2) porque son EL MISMO CÓDIGO cargado bajo dos marcas distintas. No cuesta salto: no es
    #     una suposición, es el mismo número. Esto es lo que faltaba, y es el caso más común
    #     entre listas de proveedores distintos: el proveedor A pone «036115561G» en su columna
    #     OEM, y el proveedor B usa ese mismo número COMO SU PROPIO código. Quedaban como dos
    #     productos separados —la base los separa por marca a propósito— y nada los unía, así
    #     que buscar el código de A no traía nunca el de B. De ahí lo de «solo relaciona dentro
    #     del mismo proveedor».
    #     Ojo que la búsqueda YA hacía esto al arrancar: la primera línea trae TODOS los
    #     productos con ese código, de cualquier marca. Lo que faltaba era seguir haciéndolo al
    #     avanzar por la cadena. Esto no agrega una suposición nueva, empareja el recorrido con
    #     el arranque.
    #
    # El salto por código igual NO se aplica a códigos genéricos. Un "1234" de una marca y un
    # "1234" de otra son casi seguro piezas distintas: los catálogos numeran de corrido y los
    # números chicos se repiten en todos. Un "036115561G" repetido en dos listas, en cambio, es
    # el mismo repuesto. El corte va en los puramente numéricos de menos de 6 dígitos y en
    # cualquier código de menos de 4 caracteres — lo distintivo se mantiene, lo genérico no
    # cruza. Es lo que evita que este atajo fusione familias que no tienen nada que ver.
    query = '''
    WITH RECURSIVE Red(id, saltos, peor, por_codigo) AS (
        SELECT id, 0, 100, 0 FROM productos WHERE codigo_clean = ?
        UNION
        SELECT CASE WHEN eq.producto_a_id = re.id THEN eq.producto_b_id ELSE eq.producto_a_id END,
               re.saltos + 1,
               MIN(re.peor, COALESCE(eq.confianza, 50)),
               0
        FROM equivalencias eq JOIN Red re ON (eq.producto_a_id = re.id OR eq.producto_b_id = re.id)
        WHERE re.saltos < ?
        UNION
        SELECT p2.id, re.saltos, re.peor, 1
        FROM Red re JOIN productos p1 ON p1.id = re.id
                    JOIN productos p2 ON p2.codigo_clean = p1.codigo_clean AND p2.id <> p1.id
        WHERE re.saltos < ?
          AND LENGTH(p1.codigo_clean) >= 4
          AND NOT (p1.codigo_clean GLOB '[0-9]*' AND NOT p1.codigo_clean GLOB '*[A-Z]*'
                   AND LENGTH(p1.codigo_clean) < 6)
    )
    SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
           m.nombre AS "Marca", m.tipo AS "Tipo", p.precio AS "Precio", p.stock AS "Stock",
           p.favorito AS "Favorito", COALESCE(p.imagen_thumb, p.imagen_url) AS "Imagen",
           p.precio_costo AS "_costo",
           m.url_ficha_template AS "_template", MIN(r.saltos) AS "_saltos",
           MAX(r.peor) AS "_peor",
           MIN(r.por_codigo) AS "_por_codigo"
    FROM Red r JOIN productos p ON p.id = r.id JOIN marcas m ON m.id = p.marca_id
    '''
    params = [clean_code, tope, tope]
    if marca_filtro and marca_filtro != "Todas":
        query += " WHERE UPPER(m.nombre) = ?"
        params.append(marca_filtro.upper())
    # El GROUP BY reemplaza al DISTINCT de antes: hace falta para quedarse con el camino MÁS
    # CORTO hasta cada producto, que es el que dice cuánto confiar.
    # Tope de resultados. Una red sana tiene entre 2 y 20 códigos; si devuelve cientos, es que
    # un código puente fusionó familias que no tienen relación, y mostrar 1.800 filas no ayuda
    # a nadie — solo tarda y tapa lo bueno. Se ordena por saltos, así lo primero es lo cercano.
    query += ' GROUP BY p.id ORDER BY MIN(r.saltos), m.tipo, m.nombre LIMIT 400;'

    cur.execute(query, params)
    res = filas_a_listas(cur)
    if not res:
        return res

    # Marca qué filas están verificadas con un link directo hacia el producto buscado,
    # y trae el nivel/nota de esa relación. Una sola consulta para todo el lote.
    cur.execute("SELECT id FROM productos WHERE codigo_clean = ?", (clean_code,))
    origenes = [r["id"] for r in cur.fetchall()]
    verificados_set = set()
    info_relacion = {}  # producto_id -> {"nivel": ..., "nota": ...}
    if origenes:
        result_ids = [f["ID"] for f in res]
        placeholders_o = ",".join("?" * len(origenes))
        placeholders_r = ",".join("?" * len(result_ids))
        cur.execute(
            f"""SELECT producto_a_id, producto_b_id, verificada, nivel, nota FROM equivalencias
                WHERE ((producto_a_id IN ({placeholders_o}) AND producto_b_id IN ({placeholders_r}))
                    OR (producto_b_id IN ({placeholders_o}) AND producto_a_id IN ({placeholders_r})))""",
            origenes + result_ids + origenes + result_ids
        )
        for a, b, verif, nivel, nota in cur.fetchall():
            if verif:
                verificados_set.add(a)
                verificados_set.add(b)
            otro_id = b if a in origenes else a
            if nivel or nota:
                info_relacion[otro_id] = {"nivel": nivel, "nota": nota}

    for fila in res:
        saltos = fila.pop("_saltos", 0) or 0
        peor = fila.pop("_peor", None)
        # Se distingue CÓMO se llegó. Un vínculo lo puso alguien (una lista, o a mano) y puede
        # estar mal; "mismo código" es que el número es idéntico en otra marca. Son dos tipos de
        # evidencia distintos y mezclarlos en la misma etiqueta escondía cuál es cuál: mostrarlo
        # deja decidir con el dato a la vista.
        por_codigo = fila.pop("_por_codigo", 0)
        fila["Cadena"] = ("— el buscado" if saltos == 0 else
                          "🔵 mismo código, otra marca" if por_codigo else
                          "🟢 directo" if saltos == 1 else
                          f"🟡 {saltos} saltos" if saltos <= 3 else
                          f"🔴 {saltos} saltos")
        # Lo que vale el camino entero: su eslabón más flojo. Un resultado a dos saltos por
        # vínculos sólidos es más confiable que uno directo colgado de un vínculo malo.
        if saltos and peor is not None:
            fila["Confianza"] = ("🟢 sólida" if peor >= 70 else
                                 "🟡 razonable" if peor >= 50 else
                                 "🟠 floja" if peor >= 30 else
                                 "🔴 muy débil")
        else:
            fila["Confianza"] = ""
        fila["Verificada"] = "✅" if fila["ID"] in verificados_set else ""
        rel = info_relacion.get(fila["ID"], {})
        fila["Nivel"] = rel.get("nivel") or ("Exacta" if fila["ID"] in verificados_set else "")
        fila["Nota"] = rel.get("nota") or ""
        template = fila.pop("_template", None)
        fila["Ficha"] = template.replace("{codigo}", quote(fila["Codigo"], safe="")) if template else ""
    return res


def equivalentes_mas_alla_del_tope(cur, clean_code, max_saltos):
    """Cuántos equivalentes quedan FUERA del límite de saltos elegido, y de qué marcas.

    El límite existe por una buena razón: cuanto más larga la cadena, más chance de que un
    eslabón esté mal. Pero cortando en silencio pasa esto: cada lista cita sus propios códigos de
    fábrica, esos se encadenan entre sí, y con el tope de 3 saltos se ven el proveedor propio y
    uno más — el resto queda invisible sin que nada lo diga. Visto desde el mostrador es igual a
    «no me relaciona los otros proveedores».

    Así que no se cambia el límite: se avisa que hay más y se ofrece verlo."""
    if not clean_code or not max_saltos:
        return 0, []
    consulta = """
    WITH RECURSIVE Red(id, saltos) AS (
        SELECT id, 0 FROM productos WHERE codigo_clean = ?
        UNION
        SELECT CASE WHEN eq.producto_a_id = re.id THEN eq.producto_b_id ELSE eq.producto_a_id END,
               re.saltos + 1
        FROM equivalencias eq JOIN Red re ON (eq.producto_a_id = re.id OR eq.producto_b_id = re.id)
        WHERE re.saltos < 12
        UNION
        SELECT p2.id, re.saltos
        FROM Red re JOIN productos p1 ON p1.id = re.id
                    JOIN productos p2 ON p2.codigo_clean = p1.codigo_clean AND p2.id <> p1.id
        WHERE re.saltos < 12
    )
    SELECT m.nombre AS marca, MIN(r.saltos) AS saltos
    FROM Red r JOIN productos p ON p.id = r.id JOIN marcas m ON m.id = p.marca_id
    GROUP BY p.id HAVING MIN(r.saltos) > ? LIMIT 400"""
    try:
        cur.execute(consulta, (clean_code, int(max_saltos)))
        filas = cur.fetchall()
    except sqlite3.OperationalError as _err:
        anotar_error("equivalentes_mas_alla_del_tope", _err)
        return 0, []
    marcas = sorted({f["marca"] for f in filas if f["marca"] != "OEM / FABRICA"})
    return len(filas), marcas

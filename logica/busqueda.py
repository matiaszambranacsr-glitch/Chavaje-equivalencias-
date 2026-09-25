"""La búsqueda de equivalencias, deshacer una importación, la confianza de cada vínculo y los códigos puente.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================================================
# BÚSQUEDA DE EQUIVALENCIAS (el corazón de la app)
# ============================================================================================
def filas_a_listas(cursor):
    """Convierte el resultado de un cursor (sqlite3.Row) en una lista de diccionarios."""
    return [dict(row) for row in cursor.fetchall()]


def buscar_con_variantes_del_cero(clean_code, marca_filtro="Todas", max_saltos=None,
                                  confianza_minima=None):
    """Busca el código y, SOLO si no encuentra nada, reintenta con y sin el cero de adelante.

    Devuelve (resultados, aviso). El aviso es para poder decirle a la persona que lo que está
    viendo no es exactamente lo que escribió.

    Por qué hace falta: los códigos de Bosch, Siemens y varios más arrancan con cero, y en el
    mostrador ese cero se pierde — al dictarlo por teléfono, al leerlo de una caja gastada, al
    copiarlo de un Excel que lo comió. En el catálogo real son 4.086 códigos que empiezan con
    cero, y 4.026 de ellos HOY no aparecen si se escribe sin él.

    Por qué el reintento es seguro: corre únicamente cuando la búsqueda exacta no devolvió
    nada. Hay 60 códigos del catálogo que, sin el cero, coinciden con otro código distinto —y
    la mitad son de otra familia de repuestos—, pero en esos casos la búsqueda exacta SÍ
    encuentra algo, así que el reintento no llega a correr nunca."""
    res = buscar_por_codigo(clean_code, marca_filtro, max_saltos, confianza_minima)
    if res or not clean_code:
        return res, None
    for variante in (clean_code.lstrip("0"), "0" + clean_code):
        if variante and variante != clean_code:
            res = buscar_por_codigo(variante, marca_filtro, max_saltos, confianza_minima)
            if res:
                return res, (f"No hay nada cargado como «{clean_code}», pero sí como "
                             f"«{variante}» — los códigos que empiezan con cero se escriben "
                             "de las dos formas. Confirmá que sea el mismo repuesto.")
    return [], None


def buscar_por_codigo(clean_code, marca_filtro="Todas", max_saltos=None, confianza_minima=None):
    """Busca un código y todo lo que esté encadenado con él.

    La búsqueda es TRANSITIVA: si la lista A dice que el 1 equivale al 2, y la lista B dice que
    el 2 equivale al 3, buscar el 1 también trae el 3. Eso es lo que la hace potente, y también
    lo que la hace frágil: un solo vínculo mal cargado fusiona dos familias de repuestos que no
    tienen nada que ver, y a partir de ahí la búsqueda devuelve cosas que no entran.

    Por eso ahora se cuenta a cuántos SALTOS está cada resultado del código buscado. Un salto es
    un vínculo directo: alguien lo puso en la misma fila. Cinco saltos es una cadena larga donde
    cualquier eslabón puede estar mal. Con max_saltos se corta la cadena.

    Y con confianza_minima se corta por otra cosa: cuánto vale el camino, no cuán largo es. Un
    resultado a dos saltos por vínculos sólidos es más confiable que uno directo colgado de un
    vínculo malo, así que limitar los saltos no alcanza para sacarse de encima lo dudoso."""
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
    # el mismo repuesto. El corte va en los puramente numéricos de menos de 8 dígitos y en
    # cualquier código de menos de 4 caracteres — lo distintivo se mantiene, lo genérico no
    # cruza. Es lo que evita que este atajo fusione familias que no tienen nada que ver.
    #
    # El corte estaba en 6 y se subió a 8 mirando el dato. En la base real hay 542 códigos que
    # aparecen en dos marcas o más, y separados por forma se ven dos poblaciones distintas:
    #   288 numéricos de 10 dígitos, 36 de 8, 10 de 12 y 185 con letras -> códigos de fábrica
    #       de verdad (Renault 7700274177, GM 93745292): es el mismo repuesto
    #    19 numéricos de 6 y 7 dígitos -> revisados uno por uno, los 19 son casualidad
    # Los 19 son el mismo choque: JL numera sus filtros de corrido y Taranto sus juntas
    # también, así que tarde o temprano coinciden. El 310007 de JL es un prefiltro de Focus y
    # el 310007 de Taranto una junta de tapa de cilindros de un Ford MAX. Buscando uno aparecía
    # el otro, y peor: se encadenaba toda la red del otro.
    # Seis dígitos es el largo de un número de catálogo; ocho ya es el de un código de fábrica.
    # El arranque mira las dos columnas: el código y el código de barras. Escanear la caja
    # tiene que traer el repuesto y toda su red de equivalencias, igual que si se hubiera
    # tecleado el número de parte. Antes eso funcionaba porque el EAN se cargaba como si fuera
    # un código de fábrica —con la equivalencia falsa que eso implicaba—; ahora vive en su
    # propia columna y la búsqueda la lee de ahí.
    # f-string para poder meter la columna opcional del fabricante. Las llaves que SQLite
    # usa no existen en esta consulta, así que no hay nada que escapar.
    _fabricante = campo_opcional_de_producto(c, "marca_repuesto", "Fabricante")
    query = f'''
    WITH RECURSIVE Red(id, saltos, peor, por_codigo) AS (
        SELECT id, 0, 100, 0 FROM productos WHERE codigo_clean = ? OR codigo_barras = ?
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
                   AND LENGTH(p1.codigo_clean) < 8)
    )
    SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
           m.nombre AS "Marca", m.tipo AS "Tipo",
           -- Quién FABRICA la pieza, que es otra cosa que la lista de quién te la vende. En el
           -- mostrador, entre cinco equivalentes, la pregunta es «¿cuál es el Bosch?».
           -- Ver marca_de_repuesto_en(): sale del final de la descripción, 13.705 productos.
           -- Va por campo_opcional_de_producto() y no directo: contra una base que todavía no
           -- tiene la columna, nombrarla acá tumba el buscador entero.
           {_fabricante},
           p.precio AS "Precio", p.stock AS "Stock",
           p.favorito AS "Favorito", COALESCE(p.imagen_thumb, p.imagen_url) AS "Imagen",
           p.precio_costo AS "_costo",
           m.url_ficha_template AS "_template", MIN(r.saltos) AS "_saltos",
           MAX(r.peor) AS "_peor",
           MIN(r.por_codigo) AS "_por_codigo"
    FROM Red r JOIN productos p ON p.id = r.id JOIN marcas m ON m.id = p.marca_id
    '''
    params = [clean_code, clean_code, tope, tope]
    if marca_filtro and marca_filtro != "Todas":
        query += " WHERE UPPER(m.nombre) = ?"
        params.append(marca_filtro.upper())
    # El GROUP BY reemplaza al DISTINCT de antes: hace falta para quedarse con el camino MÁS
    # CORTO hasta cada producto, que es el que dice cuánto confiar.
    # Tope de resultados. Una red sana tiene entre 2 y 20 códigos; si devuelve cientos, es que
    # un código puente fusionó familias que no tienen relación, y mostrar 1.800 filas no ayuda
    # a nadie — solo tarda y tapa lo bueno. Se ordena por saltos, así lo primero es lo cercano.
    query += ' GROUP BY p.id'
    # Filtro por lo que vale el camino, no por su largo. Son dos cosas distintas y hasta ahora
    # solo se podía controlar la segunda: un resultado a dos saltos por vínculos sólidos es más
    # confiable que uno directo colgado de un vínculo malo, y el control de saltos no distingue
    # eso. Va en HAVING y no en WHERE porque el valor sale del MAX() del grupo: es el peor
    # eslabón del camino más corto hasta ese producto.
    # El buscado (saltos = 0) nunca se filtra: es el código que se escribió, no un resultado.
    if confianza_minima:
        query += ' HAVING MIN(r.saltos) = 0 OR MAX(r.peor) >= ?'
        params.append(int(confianza_minima))
    query += ' ORDER BY MIN(r.saltos), m.tipo, m.nombre LIMIT 400;'

    with db_lock:
        c.execute(query, params)
        res = filas_a_listas(c)
        if not res:
            return res

        # Marca qué filas están verificadas con un link directo hacia el producto buscado,
        # y trae el nivel/nota de esa relación. Una sola consulta para todo el lote.
        # Los mismos orígenes que el arranque de la consulta de arriba, código de barras
        # incluido: si acá se buscara solo por codigo_clean, escanear una caja marcaría la
        # fila escaneada como un resultado más en vez de como «el buscado».
        c.execute("SELECT id FROM productos WHERE codigo_clean = ? OR codigo_barras = ?",
                  (clean_code, clean_code))
        origenes = [r["id"] for r in c.fetchall()]
        verificados_set = set()
        info_relacion = {}  # producto_id -> {"nivel": ..., "nota": ...}
        if origenes:
            result_ids = [f["ID"] for f in res]
            placeholders_o = ",".join("?" * len(origenes))
            placeholders_r = ",".join("?" * len(result_ids))
            c.execute(
                f"""SELECT producto_a_id, producto_b_id, verificada, nivel, nota FROM equivalencias
                    WHERE ((producto_a_id IN ({placeholders_o}) AND producto_b_id IN ({placeholders_r}))
                        OR (producto_b_id IN ({placeholders_o}) AND producto_a_id IN ({placeholders_r})))""",
                origenes + result_ids + origenes + result_ids
            )
            for a, b, verif, nivel, nota in c.fetchall():
                if verif:
                    verificados_set.add(a)
                    verificados_set.add(b)
                otro_id = b if a in origenes else a
                if nivel or nota:
                    info_relacion[otro_id] = {"nivel": nivel, "nota": nota}

        # A CUÁNTOS PRODUCTOS SE CUELGA CADA CÓDIGO DE FÁBRICA.
        # Un código de fábrica que cuelga UN SOLO producto no es una equivalencia: es el mismo
        # repuesto escrito de otra manera. Y la búsqueda lo mostraba como fila aparte, con
        # «🟢 directo», «🟢 sólida» y nivel «Exacta» — o sea, contándolo como si hubiera
        # encontrado el repuesto en otra marca.
        # No es un detalle de presentación. Medido sobre la base real (61.574 productos):
        # 12.060 productos —el 20% del catálogo— muestran hoy una equivalencia que no lleva a
        # ningún lado (8.652 de MOTORARG, 2.524 de FISPA, 884 de JL). En el caso de MOTORARG es
        # peor todavía: 8.076 de esos "códigos de fábrica" son el código de barras del propio
        # proveedor (todos empiezan con 7793960, que es su prefijo de GS1), así que no van a
        # coincidir nunca con la lista de nadie. De los 21.828 códigos de fábrica cargados,
        # solo 2.483 unen dos productos o más: esos son los que hacen el trabajo.
        # Desde el mostrador esto se ve exactamente como «no me hace las equivalencias»: se
        # busca un código, la app dice que encontró una coincidencia, y la coincidencia es el
        # mismo repuesto otra vez.
        ids_oem = [f["ID"] for f in res if f.get("Tipo") == "OEM"]
        grado_oem = {}
        for tanda, marcadores in en_tandas(ids_oem):
            c.execute(
                f"""SELECT p.id AS id,
                           (SELECT COUNT(*) FROM equivalencias e
                             WHERE e.producto_a_id = p.id OR e.producto_b_id = p.id) AS grado
                    FROM productos p WHERE p.id IN ({marcadores})""", tanda)
            grado_oem.update({r["id"]: r["grado"] for r in c.fetchall()})

    for fila in res:
        saltos = fila.pop("_saltos", 0) or 0
        peor = fila.pop("_peor", None)
        # Se distingue CÓMO se llegó. Un vínculo lo puso alguien (una lista, o a mano) y puede
        # estar mal; "mismo código" es que el número es idéntico en otra marca. Son dos tipos de
        # evidencia distintos y mezclarlos en la misma etiqueta escondía cuál es cuál: mostrarlo
        # deja decidir con el dato a la vista.
        por_codigo = fila.pop("_por_codigo", 0)
        # El código de fábrica que no lo tiene nadie más. Ver el conteo de grado_oem arriba:
        # cuelga un solo producto, así que no lleva a ninguna otra marca. Se muestra igual
        # —sirve para pedirlo, y el día que otro proveedor cargue ese mismo número se va a
        # encadenar solo— pero deja de presentarse como una equivalencia encontrada.
        sin_salida = fila.get("Tipo") == "OEM" and grado_oem.get(fila["ID"], 0) <= 1
        fila["_sin_salida"] = sin_salida
        fila["Cadena"] = ("— el buscado" if saltos == 0 else
                          "⚪ código de fábrica, nadie más lo tiene" if sin_salida else
                          "🔵 mismo código, otra marca" if por_codigo else
                          "🟢 directo" if saltos == 1 else
                          f"🟡 {saltos} saltos" if saltos <= 3 else
                          f"🔴 {saltos} saltos")
        # Lo que vale el camino entero: su eslabón más flojo. Un resultado a dos saltos por
        # vínculos sólidos es más confiable que uno directo colgado de un vínculo malo.
        # Al que no lleva a ningún lado no se le pone confianza: no hay nada que confiar.
        if saltos and peor is not None and not sin_salida:
            fila["Confianza"] = ("🟢 sólida" if peor >= 70 else
                                 "🟡 razonable" if peor >= 50 else
                                 "🟠 floja" if peor >= 30 else
                                 "🔴 muy débil")
        else:
            fila["Confianza"] = ""
        # Al que no lleva a ningún lado tampoco se le pone tilde ni nivel. El vínculo con su
        # propio código de fábrica está guardado como "Exacta" y es cierto, pero puesto al
        # lado del resultado se lee como «encontré el equivalente exacto», que es justo lo
        # contrario de lo que pasó.
        fila["Verificada"] = "✅" if fila["ID"] in verificados_set and not sin_salida else ""
        rel = info_relacion.get(fila["ID"], {})
        fila["Nivel"] = "" if sin_salida else (
            rel.get("nivel") or ("Exacta" if fila["ID"] in verificados_set else ""))
        fila["Nota"] = "" if sin_salida else (rel.get("nota") or "")
        template = fila.pop("_template", None)
        fila["Ficha"] = template.replace("{codigo}", quote(fila["Codigo"], safe="")) if template else ""
    return res


def el_mismo_numero_en_dos_piezas(res):
    """De los resultados, ¿el código buscado existe en dos marcas y son piezas DISTINTAS?

    Dos proveedores que numeran de corrido terminan chocando. En la base real hay 19 códigos
    numéricos de seis y siete dígitos que dos listas usan, y los 19 son casualidad: el 310007
    de JL es un prefiltro de Focus y el 310007 de Taranto una junta de tapa de cilindros de un
    Ford MAX.

    La búsqueda los muestra a los dos —y está bien, el número que se escribió es ese— pero los
    muestra iguales, los dos como «el buscado», con sus equivalentes mezclados en la misma
    lista. Sin decirlo, parece que son alternativas uno del otro.

    Devuelve la lista de esos resultados cuando son piezas distintas, y [] cuando no hay nada
    que aclarar (un solo producto, o dos que son la misma pieza en dos marcas)."""
    buscados = [f for f in res if f.get("Cadena") == "— el buscado"]
    if len(buscados) < 2 or len({f.get("Marca") for f in buscados}) < 2:
        return []
    # QUÉ FORMA TIENE UN CHOQUE DE CATÁLOGO, y por qué no se decide mirando la descripción.
    # Lo primero que probé fue comparar los nombres de las piezas, y marcaba 143 códigos de los
    # 542 compartidos cuando los choques de verdad son 19. Los otros 124 eran el mismo repuesto
    # descrito distinto: el 0280130039 de Bosch es «BULBO DE TEMPERATURA DE AGUA» para un
    # proveedor y «SENSOR INYEC» para el otro, y son la misma pieza.
    # Lo que sí separa las dos poblaciones es la FORMA DEL CÓDIGO, que es el mismo criterio con
    # el que la búsqueda decide si puede saltar de una marca a otra: los compartidos con letras
    # o con ocho dígitos o más son códigos de fábrica —el mismo repuesto—, y los numéricos
    # cortos son números de catálogo que chocaron. Medido: marca los 19 y ninguno más.
    clean = sanitizar(buscados[0].get("Codigo") or "")
    if not clean.isdigit() or len(clean) >= 8:
        return []
    return buscados


def equivalentes_mas_alla_del_tope(clean_code, max_saltos):
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
        SELECT id, 0 FROM productos WHERE codigo_clean = ? OR codigo_barras = ?
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
        c.execute(consulta, (clean_code, clean_code, int(max_saltos)))
        filas = c.fetchall()
    except sqlite3.OperationalError as _err:
        anotar_error("equivalentes_mas_alla_del_tope", _err)
        return 0, []
    marcas = sorted({f["marca"] for f in filas if f["marca"] != "OEM / FABRICA"})
    return len(filas), marcas


def incrementar_veces_buscado(clean_code):
    """Suma 1 al contador de búsquedas de un código (usado para la matriz ABC).
    Se llama únicamente desde el buscador público, no desde búsquedas internas de administración."""
    with db_lock:
        c.execute(
            "UPDATE productos SET veces_buscado = COALESCE(veces_buscado, 0) + 1 WHERE codigo_clean = ?",
            (clean_code,)
        )
        conn.commit()


def armar_lista_picking(codigos_texto):
    """Busca varios códigos a la vez y devuelve el resultado ordenado por ubicación en el
    depósito, para que el que arma el pedido camine en un solo recorrido en vez de ir y volver."""
    codigos = [sanitizar(x) for x in codigos_texto.split(",")]
    codigos = [x for x in codigos if x]
    if not codigos:
        return []
    # Por tandas y no todos de una: el pedido lo pega la persona, así que la cantidad de
    # códigos no tiene tope. Con una lista de 5.000 renglones (un pedido mensual exportado
    # del sistema del cliente) la consulta pedía 5.000 variables y en un SQLite compilado con
    # el tope habitual de 999 se cae con «too many SQL variables», justo en la pantalla que
    # se usa con el pedido ya armado. Probado: falla a los 999 y anda por tandas.
    resultado = []
    for tanda, marcadores in en_tandas(codigos):
        c.execute(f'''SELECT p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion", m.nombre AS "Marca",
                      p.ubicacion AS "Ubicación", p.stock AS "Stock"
                      FROM productos p JOIN marcas m ON m.id = p.marca_id
                      WHERE p.codigo_clean IN ({marcadores})''', tanda)
        resultado.extend(filas_a_listas(c))
    resultado.sort(key=lambda r: (not r["Ubicación"], r["Ubicación"] or ""))
    return resultado



def contar_codigos_con_decimal():
    c.execute(r"SELECT COUNT(*) FROM productos WHERE codigo_raw LIKE '%.0' AND codigo_raw GLOB '[0-9]*'")
    return c.fetchone()[0]


def codigos_limpios_desfasados(limite=None):
    """Productos cuyo codigo_clean guardado ya no es el que daría sanitizar() hoy.

    Cada vez que se arregla algo en sanitizar(), las filas que YA estaban importadas se quedan
    con el valor viejo. Y el valor viejo no es un detalle cosmético: codigo_clean es por donde
    busca la app, así que un producto con el limpio equivocado no aparece nunca, ni tipeando el
    código exacto que dice la caja.

    Pasó de verdad y así se encontró: se buscó «140E24», que está cargado, y no salió nada. El
    producto tenía guardado codigo_clean = '139999999999999999798673408', o sea 1,4 por diez a
    la 26 — la lectura como notación científica que se corrigió después. Sobre el catálogo real
    son 66 productos: 51 de notación científica (1984E0 guardado como «1984», 233900E010 como
    «2339000000000000») y 15 de otras causas. Los primeros son peores de lo que parece: además
    de no encontrarse, «1984E0» guardado como «1984» puede cruzarse con cualquier otra cosa que
    limpie a «1984»."""
    # Corre en CADA clic de «🧹 Limpiar y corregir», y recorría los 70.888 productos pasando
    # cada código por sanitizar(): 0,5 s en reposo y 7,4 s mientras trabaja la tarea de fondo
    # —cada fila que entrega SQLite espera su turno para el intérprete—. Dos cambios:
    #   · UNA fila con todo pegado (group_concat), que es una espera en vez de 70.888. Los
    #     separadores son los caracteres de control 30 y 31: se los saca del código crudo antes
    #     de pegar —sobre la base real no hay ninguno, y sanitizar() los descartaría igual— y el
    #     limpio no los puede tener.
    #   · lo que dio sanitizar() para cada código crudo se recuerda entre clics. Es exacto y no
    #     necesita testigo: si un código cambia, es otro código y se calcula de nuevo. Se
    #     olvida entero si cambia app.py, porque ahí puede haber cambiado sanitizar().
    c.execute("""SELECT group_concat(id || char(30) || marca_id || char(30)
                                     || REPLACE(REPLACE(codigo_raw, char(30), ''), char(31), '')
                                     || char(30) || COALESCE(codigo_clean, ''), char(31))
                 FROM productos WHERE codigo_raw IS NOT NULL""")
    juntos = c.fetchone()[0] or ""
    memoria = _lo_que_dio_sanitizar()
    salida = []
    for trozo in juntos.split("\x1f") if juntos else ():
        pid, marca_id, raw, guardado = trozo.split("\x1e")
        correcto = memoria.get(raw)
        if correcto is None:
            correcto = memoria[raw] = sanitizar(raw)
        if correcto and correcto != guardado:
            salida.append({"id": int(pid), "marca_id": int(marca_id),
                           "raw": raw, "guardado": guardado,
                           "correcto": correcto})
            if limite and len(salida) >= limite:
                break
    return salida


@st.cache_resource
def _memoria_de_sanitizar():
    return {"version": None, "valores": {}}


def _lo_que_dio_sanitizar():
    """{código crudo: lo que devuelve sanitizar()}, que sobrevive entre clics. Ver
    codigos_limpios_desfasados(). Se vacía si cambió el archivo donde está sanitizar()."""
    caja = _memoria_de_sanitizar()
    try:
        # El archivo de sanitizar() y no el de la app: desde que la app está partida, cambiar
        # otra parte no cambia lo que devuelve, y cambiar esa sí.
        version = os.path.getmtime(sanitizar.__code__.co_filename)
    except OSError:
        version = None
    if caja["version"] != version:
        caja["version"], caja["valores"] = version, {}
    return caja["valores"]


def reparar_codigos_limpios():
    """Recalcula el codigo_clean de los que quedaron desfasados. Devuelve cuántos se arreglaron.

    Si al corregirlo choca con otro producto de la misma marca —que es el mismo repuesto
    cargado dos veces— se fusionan, igual que en reparar_codigos_con_decimal(). En el catálogo
    real no choca ninguno, pero la base tiene UNIQUE(codigo_clean, marca_id) y sin esto la
    reparación se cortaría a la mitad con un IntegrityError."""
    pendientes = codigos_limpios_desfasados()
    arreglados = 0
    with db_lock, transaccion():
        for item in pendientes:
            try:
                c.execute("UPDATE productos SET codigo_clean = ? WHERE id = ?",
                          (item["correcto"], item["id"]))
                arreglados += 1
            except sqlite3.IntegrityError as _err:
                anotar_error("reparar_codigos_limpios", _err)
                c.execute("SELECT id FROM productos WHERE marca_id = ? AND codigo_clean = ? AND id <> ?",
                          (item["marca_id"], item["correcto"], item["id"]))
                bueno = c.fetchone()
                if bueno and fusionar_productos(item["id"], bueno["id"]):
                    arreglados += 1
    return arreglados


def reparar_codigos_con_decimal():
    """Arregla los códigos que quedaron con '.0' del final por venir de una celda numérica de
    Excel. Además de verse feo, los volvía imposibles de encontrar: '2776400.0' se limpiaba
    como '27764000' (con un cero de más) y nunca coincidía con el código real."""
    c.execute(r"""SELECT id, codigo_raw FROM productos
                  WHERE codigo_raw LIKE '%.0' AND codigo_raw GLOB '[0-9]*'""")
    filas = [(r["id"], r["codigo_raw"]) for r in c.fetchall()]
    arreglados = 0
    with db_lock:
        for pid, raw in filas:
            if not re.fullmatch(r"\d+\.0+", str(raw).strip()):
                continue
            nuevo_raw = str(raw).strip().split(".")[0]
            nuevo_clean = sanitizar(nuevo_raw)
            try:
                c.execute("UPDATE productos SET codigo_raw = ?, codigo_clean = ? WHERE id = ?",
                           (nuevo_raw, nuevo_clean, pid))
                arreglados += 1
            except sqlite3.IntegrityError as _err:
                anotar_error("reparar_codigos_con_decimal", _err)
                # En teoría no debería pasar: '2776400.0' y '2776400' se limpian al mismo
                # codigo_clean, así que la base nunca deja que existan los dos en la misma
                # marca. Si igual llegara a ocurrir, se fusionan en vez de dejar el '.0'.
                c.execute("SELECT marca_id FROM productos WHERE id = ?", (pid,))
                fila_marca = c.fetchone()
                if not fila_marca:
                    continue
                c.execute("SELECT id FROM productos WHERE marca_id = ? AND codigo_clean = ? AND id <> ?",
                           (fila_marca["marca_id"], nuevo_clean, pid))
                bueno = c.fetchone()
                if bueno and fusionar_productos(pid, bueno["id"]):
                    arreglados += 1
        conn.commit()
    return arreglados


# ============================================================================================
# DESHACER UNA IMPORTACIÓN
# ============================================================================================
def listar_importaciones_deshacibles(limite=40):
    """Importaciones que dejaron vínculos rastreables, con cuántos quedan vivos."""
    c.execute("""SELECT i.id AS "_id", i.marca AS "Marca", i.archivo AS "Archivo",
                        substr(i.fecha, 1, 16) AS "Fecha", i.filas_cargadas AS "Filas",
                        i.lote AS "_lote",
                        (SELECT COUNT(*) FROM equivalencias e WHERE e.lote = i.lote) AS "Vínculos vivos",
                        (SELECT COUNT(*) FROM equivalencias_pendientes ep WHERE ep.lote = i.lote)
                            AS "Sin revisar"
                 FROM importaciones i
                 WHERE i.lote IS NOT NULL
                 ORDER BY i.fecha DESC LIMIT ?""", (limite,))
    return filas_a_listas(c)


def previsualizar_deshacer(lote):
    """Qué se va a borrar si se deshace esta importación. Se mira ANTES de tocar nada.

    Los productos se cuentan aparte de los vínculos porque son cosas distintas: un producto que
    solo trajo esta lista se puede sacar sin problema, pero uno que además tiene precio, stock,
    ubicación o historial de ventas NO se toca aunque haya entrado con esta lista — borrarlo
    perdería datos que no vinieron de acá."""
    c.execute("SELECT COUNT(*) FROM equivalencias WHERE lote = ?", (lote,))
    vinculos = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM equivalencias_pendientes WHERE lote = ?", (lote,))
    pendientes = c.fetchone()[0]
    return {"vinculos": vinculos, "pendientes": pendientes, "lote": lote}


def deshacer_importacion(lote, borrar_pendientes=True):
    """Saca los vínculos que dejó una importación. Devuelve cuántos se borraron.

    Solo toca las equivalencias, nunca los productos: los precios, el stock, la ubicación y el
    historial que hayas cargado sobre esos productos se quedan donde están. Lo que se deshace
    es la parte peligrosa —los vínculos falsos— y eso es reversible sin perder trabajo."""
    if not lote:
        return 0, 0
    # Todo o nada: los vínculos y los pendientes de la misma lista se van juntos. Si se borran
    # los vínculos y quedan los pendientes, la lista deshecha vuelve a aparecer para aprobar.
    with db_lock, transaccion():
        c.execute("SELECT producto_a_id, producto_b_id FROM equivalencias WHERE lote = ?", (lote,))
        pares = [(r["producto_a_id"], r["producto_b_id"]) for r in c.fetchall()]
        c.execute("DELETE FROM equivalencias WHERE lote = ?", (lote,))
        borrados = c.rowcount
        pend = 0
        if borrar_pendientes:
            c.execute("DELETE FROM equivalencias_pendientes WHERE lote = ?", (lote,))
            pend = c.rowcount
    # Queda registrado el rechazo para que una reimportación de la misma lista no los reviva.
    # OJO con el valor: tiene que ser exactamente "rechazada" — es el que busca pares_rechazados().
    # Escrito de cualquier otra forma se guarda igual y no filtra nada, y encima en silencio.
    if pares:
        marcar_revision(pares, "rechazada")
    return borrados, pend



def origenes_de_los_vinculos_directos(producto_id, ids_resultado):
    """De qué lista salió cada vínculo directo del código buscado. {id_producto: lote}.

    Sirve en el momento de decidir: si un resultado raro salió de una lista que ya sabés que
    vino mal mapeada, no hace falta pensarlo más. Y si esa lista es un desastre entero, se
    deshace de una desde Mantenimiento en vez de ir corrigiendo de a un vínculo."""
    if not ids_resultado:
        return {}
    salida = {}
    # usos_por_consulta=2 porque la lista aparece en los dos IN.
    for tanda, marcadores in en_tandas(ids_resultado, usos_por_consulta=2):
        c.execute(f"""SELECT CASE WHEN producto_a_id = ? THEN producto_b_id ELSE producto_a_id END AS otro,
                             lote
                      FROM equivalencias
                      WHERE (producto_a_id = ? OR producto_b_id = ?)
                        AND lote IS NOT NULL
                        AND (producto_a_id IN ({marcadores}) OR producto_b_id IN ({marcadores}))""",
                  [producto_id, producto_id, producto_id] + tanda + tanda)
        salida.update({r["otro"]: r["lote"] for r in c.fetchall()})
    return salida


# ============================================================================================
# CONFIANZA DE CADA VÍNCULO
# ============================================================================================
def auditar_equivalencias_cargadas(limite=2000, tope_confianza=35, revisar=None):
    """Pasa el mismo análisis de confianza por las equivalencias YA cargadas.

    Es la herramienta que faltaba. El análisis de confianza solo miraba los vínculos pendientes
    de revisión, pero el problema grande está en los que YA entraron: miles cargados por
    importaciones viejas que nadie revisó. Sin esto, la única forma de encontrarlos era
    tropezarse con uno buscando un código.

    Devuelve los peores primero, con el motivo escrito.

    El ORDER BY por confianza guardada no es cosmético: hace que, si alguna vez hay que
    cortar, se corte por los mejores y no por los más viejos.

    Pero ya no se corta. El tope estaba en 8.000 sobre una base de 24.774 vínculos —dos tercios
    que no se revisaban nunca— y la pantalla decía «se revisaron 8.000 vínculos y ninguno quedó
    por debajo del umbral», que suena a «está todo bien» cuando faltaba el 68%. Revisarlos
    todos cuesta 10,5 s contra 3,9 s: el tope ahorraba seis segundos y escondía 16.774
    vínculos. `revisar=None` es todos; el parámetro queda por si alguna vez hace falta cortar
    a propósito."""
    ceder_al_mostrador()      # antes de la lectura grande. Ver ceder_al_mostrador().
    # SIN_CONTAR_EL_ESPEJO: acá se juzga el PAR. Con la relación anotada de ida y de vuelta,
    # el mismo vínculo se analizaba dos veces —cuesta el doble—, salía dos veces en la lista
    # de «los peores» y el «se revisaron N vínculos» de la pantalla decía el doble de los que
    # hay. Cortarlo sigue llevándose las dos filas: ver borrar_equivalencias_dudosas().
    c.execute(f"""SELECT e.producto_a_id AS a, e.producto_b_id AS b, e.lote,
                        pa.codigo_raw AS cod_a, pa.descripcion AS desc_a, pa.precio AS precio_a,
                        ma.nombre AS marca_a,
                        pb.codigo_raw AS cod_b, pb.descripcion AS desc_b, pb.precio AS precio_b,
                        mb.nombre AS marca_b, ma.tipo AS tipo_a, mb.tipo AS tipo_b
                 FROM equivalencias e
                 JOIN productos pa ON pa.id = e.producto_a_id
                 JOIN productos pb ON pb.id = e.producto_b_id
                 JOIN marcas ma ON ma.id = pa.marca_id
                 JOIN marcas mb ON mb.id = pb.marca_id
                 WHERE {SIN_CONTAR_EL_ESPEJO}
                 ORDER BY COALESCE(e.confianza, 50) ASC
                 LIMIT ?""", (revisar if revisar else -1,))
    filas = [dict(r) for r in c.fetchall()]
    if not filas:
        return [], 0

    medidas = cargar_medidas_de_varios([f["a"] for f in filas] + [f["b"] for f in filas])
    aprobados = puentes_aprobados_ids()
    patrones = aprender_de_las_decisiones()
    ventas_confirman = pares_confirmados_por_ventas()

    escalas = escalas_de_precio()
    _ya_juzgados = {}   # código -> ¿las reglas de hoy ya no lo tomarían? Cacheado: los 24.774
                        # vínculos se apoyan en muchos menos códigos distintos.
    # Lo mismo que en recalcular_confianzas(): a cuántos productos se cuelga cada código de
    # fábrica, contado de una sola vez para todo el lote.
    grados = {}
    try:
        c.execute("""SELECT p.id AS pid, COUNT(*) AS n FROM equivalencias eq
                     JOIN productos p ON p.id IN (eq.producto_a_id, eq.producto_b_id)
                     JOIN marcas m ON m.id = p.marca_id
                     WHERE m.tipo = 'OEM' GROUP BY p.id""")
        grados = {r["pid"]: r["n"] for r in c.fetchall()}
    except sqlite3.OperationalError as _err:
        anotar_error("auditar_equivalencias_cargadas", _err)

    dudosas = []
    for f in filas:
        ceder_al_mostrador()
        # Un vínculo de un código puente ya aprobado a mano no se vuelve a cuestionar
        if f["a"] in aprobados or f["b"] in aprobados:
            continue
        if f["tipo_a"] == "OEM":
            puente, id_puente = f["cod_a"], f["a"]
        elif f["tipo_b"] == "OEM":
            puente, id_puente = f["cod_b"], f["b"]
        else:
            puente, id_puente = None, None
        puntaje, senales = evaluar_equivalencia(
            f["desc_a"], f["desc_b"], medidas.get(f["a"]), medidas.get(f["b"]),
            f["precio_a"], f["precio_b"],
            marca_a=f["marca_a"], marca_b=f["marca_b"], patrones=patrones,
            vendido_como_reemplazo=ventas_confirman.get((min(f["a"], f["b"]),
                                                          max(f["a"], f["b"])), 0),
            codigo_puente=puente, productos_del_puente=grados.get(id_puente, 0),
            escalas=escalas
        )
        for lado in ("a", "b"):
            malo, _ = codigo_sospechoso(f[f"cod_{lado}"], f.get(f"desc_{lado}") or "")
            if malo:
                puntaje -= 35
        # EL CÓDIGO DE FÁBRICA QUE LAS REGLAS DE HOY YA NO TOMARÍAN. Es el mismo control que
        # hace el análisis de la cola de pendientes, y acá hace más falta todavía: estos
        # vínculos YA están cargados y el buscador los está usando hoy. Se cargaron con las
        # reglas de su momento, y las reglas cambiaron —los modelos de Mercedes, los camiones
        # Iveco, el «505REF», el «1995REF»—. Sin esto había que esperar a tropezarse con uno.
        # Medido sobre los 24.774 cargados: 681 cuelgan de un código que hoy no se tomaría, y
        # la auditoría marcaba 203. Los códigos son «CLA250», «CLS350», «505REF», «2002REF»,
        # «SCENIC2», «307REF»: modelos y años, no piezas.
        # Solo el lado del código de fábrica, por lo mismo que explica analizar_lote_pendiente():
        # preguntarle esto al código propio de un proveedor vetaba 12.508 de 24.774.
        for lado in ("a", "b"):
            if f.get(f"tipo_{lado}") != "OEM":
                continue
            _cod_oem = f[f"cod_{lado}"] or ""
            if _cod_oem and _cod_oem not in _ya_juzgados:
                _ya_juzgados[_cod_oem] = codigo_que_hoy_no_se_tomaria(_cod_oem)
            if _cod_oem and _ya_juzgados.get(_cod_oem):
                puntaje = min(puntaje, 15.0)
                senales.append(("mal", f"🧯 «{_cod_oem}» no es un código de fábrica: es un "
                                        "modelo, una medida o un año. Las reglas de hoy ya no "
                                        "lo tomarían"))
                break
        # Dos productos del MISMO proveedor. Es el mismo control que hace evidencia_cruzada(),
        # repetido acá porque esta función no la llama —serían 24.774 llamadas— y se puede
        # contestar con lo que el lote ya trae. Son 196 vínculos en la base real y ninguno es
        # una equivalencia: salen de una celda de código que traía dos cosas y una era un
        # pedazo de la descripción.
        if f["marca_a"] == f["marca_b"]:
            _sin_digitos = [f[f"cod_{lado}"] for lado in ("a", "b")
                            if not any(ch.isdigit() for ch in sanitizar(f[f"cod_{lado}"]))]
            _misma_desc = (f["desc_a"] or "").strip() == (f["desc_b"] or "").strip()
            if _sin_digitos or _misma_desc:
                puntaje = min(puntaje, 10.0)
                senales.append((
                    "mal",
                    f"🏷️ los dos son de {f['marca_a']} y "
                    + (f"«{_sin_digitos[0]}» no tiene ningún número: es un pedazo de la "
                       "descripción que quedó como código" if _sin_digitos else
                       "dicen exactamente lo mismo: es una fila leída dos veces")))
        puntaje = max(0.0, puntaje)
        if puntaje <= tope_confianza:
            dudosas.append({
                "Confianza": round(puntaje),
                "Código A": f["cod_a"], "Marca A": f["marca_a"],
                "Código B": f["cod_b"], "Marca B": f["marca_b"],
                "Por qué": " · ".join(t for tipo, t in senales if tipo == "mal") or
                            "el código no parece un código",
                "Vino de": (f["lote"] or "").split(" · ")[0],
                "_a": f["a"], "_b": f["b"],
            })
    dudosas.sort(key=lambda x: x["Confianza"])
    return dudosas[:limite], len(filas)


def faltan_por_puntuar():
    """Cuántos vínculos todavía no tienen confianza calculada."""
    try:
        c.execute("SELECT COUNT(*) FROM equivalencias WHERE confianza IS NULL")
        return c.fetchone()[0]
    except sqlite3.OperationalError as _err:
        anotar_error("faltan_por_puntuar", _err)
        return 0


def recalcular_confianzas(limite=20000, progreso=None, solo_faltantes=True):
    """Calcula y guarda la confianza de cada vínculo cargado.

    Se guarda en vez de calcularse al vuelo porque el buscador la necesita en CADA búsqueda:
    hacer el análisis completo ahí lo volvería lento. Así se hace una vez y queda.

    El 'solo_faltantes' es el arreglo de un bug que dejaba inútil todo este mecanismo: la
    consulta tomaba LIMIT filas de TODOS los vínculos, sin filtro y sin orden, así que siempre
    agarraba las mismas primeras. Correrla de nuevo repuntuaba esas y no avanzaba nunca sobre
    el resto. Medido sobre la base real: 24.774 vínculos, tres corridas de 2.000 cada una, y
    los sin puntuar quedaban clavados en 20.767 — el 84% del catálogo sin puntaje para siempre,
    por más veces que se tocara el botón.
    Y eso no era un detalle de una pantalla de mantenimiento: la confianza es lo que el buscador
    muestra en CADA resultado para decir cuánto confiar en el camino. Con el 84% de los vínculos
    contando como neutros, «una cadena vale lo que su eslabón más flojo» no medía nada.

    Con solo_faltantes se puntúa lo que falta y cada corrida avanza. En False vuelve a puntuar
    todo, que es lo que hace falta cuando cambió la evidencia (ventas nuevas, decisiones nuevas)
    y los puntajes viejos quedaron desactualizados."""
    ceder_al_mostrador()      # antes de la lectura grande. Ver ceder_al_mostrador().
    filtro = "WHERE e.confianza IS NULL" if solo_faltantes else ""
    c.execute(f"""-- FILA Y NO PAR: esta consulta ESCRIBE la confianza de cada fila. Si la
                  -- relación está anotada de ida y de vuelta hay que puntuar las dos, porque
                  -- la que quede sin puntuar cuenta como neutra en el buscador. Descartar el
                  -- espejo acá dejaría la mitad de los vínculos en NULL para siempre.
                  SELECT e.producto_a_id AS a, e.producto_b_id AS b,
                        pa.codigo_raw AS cod_a, pa.descripcion AS desc_a, pa.precio AS precio_a,
                        ma.nombre AS marca_a,
                        pb.codigo_raw AS cod_b, pb.descripcion AS desc_b, pb.precio AS precio_b,
                        mb.nombre AS marca_b, ma.tipo AS tipo_a, mb.tipo AS tipo_b
                 FROM equivalencias e
                 JOIN productos pa ON pa.id = e.producto_a_id
                 JOIN productos pb ON pb.id = e.producto_b_id
                 JOIN marcas ma ON ma.id = pa.marca_id
                 JOIN marcas mb ON mb.id = pb.marca_id
                 {filtro}
                 LIMIT ?""", (limite,))
    filas = [dict(r) for r in c.fetchall()]
    if not filas:
        return 0
    medidas = cargar_medidas_de_varios([f["a"] for f in filas] + [f["b"] for f in filas])
    patrones = aprender_de_las_decisiones()
    escalas = escalas_de_precio()
    # A cuántos productos se cuelga cada código de fábrica. Se cuenta de una sola vez para todo
    # el lote: preguntarlo vínculo por vínculo serían miles de consultas para el mismo dato.
    grados = {}
    try:
        c.execute("""SELECT p.id AS pid, COUNT(*) AS n FROM equivalencias eq
                     JOIN productos p ON p.id IN (eq.producto_a_id, eq.producto_b_id)
                     JOIN marcas m ON m.id = p.marca_id
                     WHERE m.tipo = 'OEM' GROUP BY p.id""")
        grados = {r["pid"]: r["n"] for r in c.fetchall()}
    except sqlite3.OperationalError as _err:
        anotar_error("recalcular_confianzas", _err)
    aprobados = puentes_aprobados_ids()
    ventas_confirman = pares_confirmados_por_ventas()
    _ya_juzgados = {}   # código -> ¿las reglas de hoy ya no lo tomarían? (cacheado)

    valores = []
    for i, f in enumerate(filas):
        ceder_al_mostrador()
        # Cuál de los dos lados es el código de fábrica que hace de puente (si alguno lo es).
        if f["tipo_a"] == "OEM":
            puente, id_puente = f["cod_a"], f["a"]
        elif f["tipo_b"] == "OEM":
            puente, id_puente = f["cod_b"], f["b"]
        else:
            puente, id_puente = None, None
        puntaje, _ = evaluar_equivalencia(
            f["desc_a"], f["desc_b"], medidas.get(f["a"]), medidas.get(f["b"]),
            f["precio_a"], f["precio_b"],
            marca_a=f["marca_a"], marca_b=f["marca_b"], patrones=patrones,
            vendido_como_reemplazo=ventas_confirman.get((min(f["a"], f["b"]),
                                                          max(f["a"], f["b"])), 0),
            codigo_puente=puente, productos_del_puente=grados.get(id_puente, 0),
            escalas=escalas
        )
        if f["a"] not in aprobados and f["b"] not in aprobados:
            for lado in ("a", "b"):
                malo, _ = codigo_sospechoso(f[f"cod_{lado}"], f.get(f"desc_{lado}") or "")
                if malo:
                    puntaje -= 35
            # El mismo control que hacen el análisis de la cola y la auditoría de los
            # cargados, y acá cierra el círculo: este puntaje es el GUARDADO, o sea el que el
            # buscador muestra en cada búsqueda. Si las tres partes no usan la misma regla,
            # la pantalla de auditoría dice que un vínculo está mal y el buscador lo sigue
            # mostrando como confiable. Solo el lado del código de fábrica: ver
            # analizar_lote_pendiente() para por qué preguntárselo al código propio de un
            # proveedor vetaba 12.508 de 24.774.
            for lado in ("a", "b"):
                if f.get(f"tipo_{lado}") != "OEM":
                    continue
                _cod_oem = f[f"cod_{lado}"] or ""
                if _cod_oem and _cod_oem not in _ya_juzgados:
                    _ya_juzgados[_cod_oem] = codigo_que_hoy_no_se_tomaria(_cod_oem)
                if _cod_oem and _ya_juzgados.get(_cod_oem):
                    puntaje = min(puntaje, 15.0)
                    break
        valores.append((max(0, min(100, round(puntaje))), f["a"], f["b"]))
        if progreso and i % 500 == 0:
            progreso(i, len(filas))

    with db_lock:
        c.executemany("UPDATE equivalencias SET confianza = ? "
                      "WHERE producto_a_id = ? AND producto_b_id = ?", valores)
        conn.commit()
    return len(valores)


def borrar_equivalencias_dudosas(pares):
    """Corta los vínculos elegidos y los deja anotados como rechazados.

    SE BORRAN LAS DOS DIRECCIONES, y ese es el arreglo de un vínculo que no se cortaba.
    Antes el DELETE normalizaba el par a (menor, mayor) y buscaba esa fila exacta. Un vínculo
    guardado al revés —id mayor primero, que es justo lo que existe mientras nadie corrió
    unificar_equivalencias_espejadas()— no coincidía con nada: el DELETE borraba cero filas y
    la pantalla decía «se cortaron N vínculos» igual, con marcar_revision() anotándolo como
    rechazado. El vínculo malo seguía ahí y la búsqueda seguía devolviéndolo.

    Reproducido con dos vínculos, uno guardado (5,3) y otro (7,9): el corte se llevaba el
    segundo y dejaba el primero intacto.

    Y borrar las dos direcciones no es de más: si la relación está espejada hay que llevarse
    las dos filas, porque la que quede sigue siendo el mismo vínculo para el buscador."""
    if not pares:
        return 0
    with db_lock:
        c.executemany("""DELETE FROM equivalencias
                         WHERE (producto_a_id = ? AND producto_b_id = ?)
                            OR (producto_a_id = ? AND producto_b_id = ?)""",
                      [(a, b, b, a) for a, b in pares])
        borrados = c.rowcount
        conn.commit()
    marcar_revision(list(pares), "rechazada")
    return borrados


# Un par es un par, se lo mire de A a B o de B a A. La tabla `equivalencias` puede tener las
# dos filas —pasa seguido, para eso está unificar_equivalencias_espejadas()— y cualquier
# consulta que cuente pares sin esto cuenta el doble.
# Se queda con la fila que va del id MENOR al mayor, salvo que la única que exista sea la otra:
# poner «producto_a_id < producto_b_id» a secas parece lo mismo y no lo es — esconde los pares
# que solo están anotados al revés, que es justo el caso que la herramienta de unificar todavía
# no tocó.
SIN_CONTAR_EL_ESPEJO = """(e.producto_a_id < e.producto_b_id
                           OR NOT EXISTS (SELECT 1 FROM equivalencias e2
                                          WHERE e2.producto_a_id = e.producto_b_id
                                            AND e2.producto_b_id = e.producto_a_id))"""


def contar_equivalencias_espejadas():
    """Cuántas equivalencias están guardadas dos veces, una en cada dirección."""
    c.execute("""SELECT COUNT(*) FROM equivalencias e
                 WHERE e.producto_a_id > e.producto_b_id
                   AND EXISTS (SELECT 1 FROM equivalencias e2
                               WHERE e2.producto_a_id = e.producto_b_id
                                 AND e2.producto_b_id = e.producto_a_id)""")
    return c.fetchone()[0]


def unificar_equivalencias_espejadas():
    """Deja una sola fila por equivalencia, siempre con el id menor primero.

    No cambia ninguna equivalencia: son exactamente las mismas, solo que estaban anotadas dos
    veces. La búsqueda nunca lo notó porque consulta las dos columnas con OR, pero los conteos
    sí: un código con 100 equivalencias reales figuraba con 200."""
    with db_lock:
        # Primero las que están espejadas (existe la pareja al revés): se borra la invertida
        c.execute("""DELETE FROM equivalencias
                     WHERE producto_a_id > producto_b_id
                       AND EXISTS (SELECT 1 FROM equivalencias e2
                                   WHERE e2.producto_a_id = equivalencias.producto_b_id
                                     AND e2.producto_b_id = equivalencias.producto_a_id)""")
        borradas = c.rowcount
        # Y las que quedaron sueltas al revés se dan vuelta, para que todas queden igual
        c.execute("""UPDATE equivalencias
                     SET producto_a_id = producto_b_id, producto_b_id = producto_a_id
                     WHERE producto_a_id > producto_b_id""")
        dadas_vuelta = c.rowcount
        c.execute("DELETE FROM equivalencias WHERE producto_a_id = producto_b_id")
        conn.commit()
    return borradas, dadas_vuelta


# ============================================================================================
# CÓDIGOS PUENTE: aprobar los buenos, encontrar los falsos
# ============================================================================================
def aprobar_puente(producto_id, nota=""):
    """Marca un código con muchos vínculos como revisado y correcto."""
    with db_lock:
        c.execute("""INSERT INTO puentes_aprobados (producto_id, aprobado_por, nota)
                     VALUES (?, ?, ?)
                     ON CONFLICT(producto_id) DO UPDATE SET nota = excluded.nota,
                        aprobado_por = excluded.aprobado_por, fecha = datetime('now')""",
                  (producto_id, obtener_usuario_actual(), (nota or "").strip() or None))
        conn.commit()
    return True


def desaprobar_puente(producto_id):
    with db_lock:
        c.execute("DELETE FROM puentes_aprobados WHERE producto_id = ?", (producto_id,))
        conn.commit()
    return c.rowcount


def puentes_aprobados_ids():
    try:
        c.execute("SELECT producto_id FROM puentes_aprobados")
        return {r["producto_id"] for r in c.fetchall()}
    except sqlite3.OperationalError as _err:
        anotar_error("puentes_aprobados_ids", _err)
        return set()


MARCAS_PARA_SER_UN_PUENTE = 2   # ver contar_codigos_puente()


def contar_codigos_puente(minimo=30, marcas_minimas=MARCAS_PARA_SER_UN_PUENTE):
    """Solo el conteo, sin traer los datos. Es lo que usa el chequeo de salud, que corre seguido:
    la consulta completa arma dos subconsultas por producto y no hace falta para un número.

    CUENTA LOS QUE TOCAN VARIAS MARCAS, no los que tienen muchos vínculos, y esa es toda la
    diferencia. Un puente es, por definición, un código que FUSIONA familias de proveedores
    distintos; si todos sus vínculos se quedan adentro de una sola marca, no está puenteando
    nada. Y hay un caso perfectamente sano que tiene decenas de vínculos en una sola marca: la
    tabla de referencias cruzadas que el propio proveedor publica. Un motor de arranque de FISPA
    lista 45 códigos de fábrica de Bosch, Delco, Valeo y Magneti Marelli en su descripción, y
    los 45 son ciertos.

    Sobre la base real, contando solo los vínculos, el aviso decía «31 códigos puente» en rojo,
    todos los días. Mirando la columna que importa: **30 de esos 31 tocan UNA sola marca** y son
    tablas de referencias cruzadas de motores de arranque y alternadores. El único de verdad es
    «CHAPA» —la palabra, cargada como código— con 76 vínculos y 2 marcas.
    Un aviso en rojo que grita 31 cuando hay 1 no es un aviso: es ruido que enseña a ignorar
    los avisos, incluso los que importan.
    La pantalla sigue mostrando todos, con la columna «Marcas distintas» al lado, porque
    mirarlos no hace daño; lo que cambia es de qué avisa la app sola."""
    c.execute("""SELECT COUNT(*) FROM productos p
                 WHERE (SELECT COUNT(*) FROM equivalencias e
                        WHERE e.producto_a_id = p.id OR e.producto_b_id = p.id) >= ?
                   AND (SELECT COUNT(DISTINCT m2.nombre) FROM equivalencias e
                          JOIN productos p2 ON p2.id = CASE WHEN e.producto_a_id = p.id
                                                            THEN e.producto_b_id ELSE e.producto_a_id END
                          JOIN marcas m2 ON m2.id = p2.marca_id
                        WHERE e.producto_a_id = p.id OR e.producto_b_id = p.id) >= ?
                   AND p.id NOT IN (SELECT producto_id FROM puentes_aprobados)""",
              (minimo, marcas_minimas))
    return c.fetchone()[0]


def invalidar_salud():
    """Fuerza a recalcular el chequeo de salud en el próximo refresco.

    Se llama después de cada acción que cambia los números: importar, unificar duplicadas,
    cortar vínculos, bajar un backup. Sin esto el aviso de arriba seguiría mostrando el
    problema durante tres minutos después de haberlo arreglado, y uno no sabría si funcionó."""
    # El chequeo es uno solo para todos (ver salud_compartida()): se tira el de todos.
    del_proceso("salud_compartida", dict).clear()


def salud_compartida(segundos_de_vida=180):
    """El chequeo de salud, UNO para todos los que usan la app. Devuelve {momento, problemas}.

    Se guardaba en la sesión de cada uno, así que cada persona que entraba lo calculaba de cero,
    aunque da lo mismo para todos: no mira quién pregunta. Medido con 15 personas entrando a la
    vez contra un servidor de un solo procesador, como el de Streamlit gratis: cada entrada
    costaba 1,4 s de procesador y el 40% era esto. Llegando juntas, la última esperaba 25 s.
    Ahora lo calcula la primera; las que llegan mientras tanto esperan ESE resultado en vez de
    calcular el suyo, y las siguientes lo reciben hecho hasta que pasen los tres minutos de
    siempre o alguien cambie algo (invalidar_salud())."""
    guardado = del_proceso("salud_compartida", dict)
    candado = del_proceso("candado_de_la_salud_compartida", threading.Lock)
    vigente = lambda: guardado.get("momento") and time.time() - guardado["momento"] <= segundos_de_vida
    if not vigente():
        with candado:
            if not vigente():         # otro la calculó mientras se esperaba el candado
                try:
                    problemas = diagnostico_de_salud()
                except Exception as _err:
                    anotar_error("salud_compartida", _err)
                    problemas = []
                guardado.update(momento=time.time(), problemas=problemas)
    return dict(guardado)


def productos_con_vinculos_esperando():
    """Por marca: cuántos de sus productos YA tienen equivalencias encontradas, esperando que
    alguien las apruebe. Devuelve {marca_id: cuántos}.

    Hace falta para no dar un diagnóstico falso. Las dos pantallas que explican «por qué esta
    lista no cruza con ninguna otra» miraban solo la tabla de equivalencias CARGADAS, y de ahí
    concluían «esta lista se importó sin la columna de código de fábrica». Sobre la base real
    eso era mentira y mandaba a reimportar una lista que estaba perfecta: ILLINOIS tiene 0
    vínculos cargados —por eso saltaba la alarma— y 2.367 productos con vínculos esperando
    revisión, más 632 códigos de fábrica que esa misma lista aportó. No le faltaba la columna:
    le faltaba que alguien entrara a aprobar lo que ya se había encontrado."""
    try:
        c.execute("""
            SELECT p.marca_id AS marca_id, COUNT(DISTINCT p.id) AS cuantos
            FROM productos p
            WHERE p.id IN (SELECT producto_a_id FROM equivalencias_pendientes
                           UNION SELECT producto_b_id FROM equivalencias_pendientes)
            GROUP BY p.marca_id""")
        return {f["marca_id"]: f["cuantos"] for f in c.fetchall()}
    except sqlite3.OperationalError as _err:
        anotar_error("productos_con_vinculos_esperando", _err)
        return {}


def salud_de_los_cruces():
    """Cuánto cruza de verdad tu catálogo entre proveedores, marca por marca.

    Existe porque «no me relaciona los proveedores» es un síntoma, no un diagnóstico, y desde la
    pantalla no se distingue de qué viene. Esto lo pone en números: para cada marca, cuántos de
    sus productos tienen algún vínculo y cuántos llegan a OTRA marca. Una lista con 3.000
    productos y CERO que crucen es una lista que se importó sin la columna de código de fábrica
    — y eso no se ve mirando resultados de a uno, se ve mirando la tabla entera.

    Se miran los vínculos DIRECTOS, no la cadena completa: es lo que se puede calcular de una
    sola pasada sobre todo el catálogo, y para saber si una lista quedó aislada alcanza."""
    try:
        c.execute("""
            WITH vecinos AS (
                SELECT eq.producto_a_id AS pid, p2.marca_id AS marca_vecina
                  FROM equivalencias eq JOIN productos p2 ON p2.id = eq.producto_b_id
                UNION ALL
                SELECT eq.producto_b_id AS pid, p1.marca_id AS marca_vecina
                  FROM equivalencias eq JOIN productos p1 ON p1.id = eq.producto_a_id
            )
            SELECT m.nombre AS "Marca", m.tipo AS "_tipo", m.id AS "_marca_id",
                   COUNT(DISTINCT p.id) AS "Productos",
                   COUNT(DISTINCT CASE WHEN v.pid IS NOT NULL THEN p.id END) AS "Con vínculo",
                   COUNT(DISTINCT CASE WHEN v.marca_vecina IS NOT NULL
                                        AND v.marca_vecina <> p.marca_id THEN p.id END)
                       AS "Cruzan a otra marca"
            FROM productos p
            JOIN marcas m ON m.id = p.marca_id
            LEFT JOIN vecinos v ON v.pid = p.id
            GROUP BY m.id ORDER BY COUNT(DISTINCT p.id) DESC""")
        filas = filas_a_listas(c)
    except sqlite3.OperationalError as _err:
        anotar_error("salud_de_los_cruces", _err)
        return [], {}

    # Los vínculos que esa lista YA tiene encontrados y sin aprobar. Sin esto el diagnóstico
    # de abajo era falso: ver productos_con_vinculos_esperando().
    esperando = productos_con_vinculos_esperando()
    resumen = {"productos": 0, "cruzan": 0, "listas_aisladas": [], "listas_esperando": []}
    for f in filas:
        f["% que cruza"] = (f"{f['Cruzan a otra marca'] * 100 // f['Productos']}%"
                             if f["Productos"] else "—")
        f["Esperando revisión"] = esperando.get(f["_marca_id"], 0)
        # El diagnóstico en palabras: es lo que convierte la tabla en algo accionable.
        if f["_tipo"] == "OEM":
            f["Qué pasa"] = "Códigos de fábrica: son el puente, no hace falta que crucen."
        elif not f["Cruzan a otra marca"] and f["Esperando revisión"]:
            # Este caso va ANTES que el de la lista aislada y no se cuenta como aislada: el
            # síntoma es el mismo —cero cruces— pero lo que hay que hacer es lo contrario.
            f["Qué pasa"] = (f"⏳ Todavía ninguno cruza, pero {f['Esperando revisión']:,} "
                              "producto(s) ya tienen equivalencias encontradas esperando que "
                              "las apruebes. No falta la columna: falta revisarlas.")
            resumen["listas_esperando"].append(f["Marca"])
        elif not f["Cruzan a otra marca"]:
            f["Qué pasa"] = ("⚠️ NINGUNO cruza. Esa lista se importó sin la columna de código "
                              "de fábrica, o esa columna quedó mal mapeada.")
            resumen["listas_aisladas"].append(f["Marca"])
        elif f["Cruzan a otra marca"] * 2 < f["Productos"]:
            f["Qué pasa"] = ("Cruza menos de la mitad: la lista trae el código de fábrica solo "
                              "en algunas filas.")
        else:
            f["Qué pasa"] = "Bien."
        if f["_tipo"] != "OEM":
            resumen["productos"] += f["Productos"]
            resumen["cruzan"] += f["Cruzan a otra marca"]
    return filas, resumen


TOPE_PRODUCTOS_POR_PUENTE = 5   # ver puentes_sospechosos()


def puentes_sospechosos(tope=TOPE_PRODUCTOS_POR_PUENTE, limite=60):
    """Códigos de fábrica que están uniendo repuestos que no tienen nada que ver.

    Son el peor daño posible en esta base, y el más difícil de ver: un solo código malo no
    devuelve un resultado de más, fusiona DOS FAMILIAS ENTERAS. Buscando una bobina de ignición
    aparecía un sensor de masa de aire de Mazda y un sensor de temperatura de Corolla, porque
    las tres descripciones nombraban la 4Runner y de ahí salió «4RUNNER» como si fuera un código.

    Fila por fila esto no se ve: cada vínculo suelto parece razonable. Se ve mirando el catálogo
    entero, que es lo que hace esta función.

    Se cruzan dos señales, porque ninguna sola alcanza —se midió sobre cinco listas reales:

      - CUÁNTOS productos cuelga. El 99,9% de los códigos de fábrica verdaderos unen 4 productos
        o menos: es el mismo repuesto en unos pocos proveedores. Los que unen 6 o más resultaron
        ser todos texto (F14000 el camión, AP2000 el motor, 1500-1800 la cilindrada).
      - DE QUÉ FAMILIA es lo que une. Un código real une repuestos de la misma familia; si une
        un filtro con un cilindro maestro, no es un código, es una palabra que las dos
        descripciones mencionan. Esta señal es la que no se degrada cuando el catálogo crece:
        un código de fábrica muy popular puede colgar veinte productos legítimamente, pero van
        a ser todos de la misma familia.

    Por eso NO se borra nada solo: se listan para que decida quien conoce los repuestos. Un
    corte automático se llevaría por delante los códigos populares de verdad, que son
    justamente los más valiosos."""
    try:
        c.execute("""
            SELECT p.id AS pid, p.codigo_raw AS "Código", COUNT(*) AS "Productos que une"
              FROM equivalencias eq
              JOIN productos p ON p.id IN (eq.producto_a_id, eq.producto_b_id)
              JOIN marcas m ON m.id = p.marca_id
             WHERE m.tipo = 'OEM'
             GROUP BY p.id HAVING COUNT(*) >= ?
             ORDER BY COUNT(*) DESC LIMIT ?""", (max(2, tope - 1), limite * 4))
        candidatos = filas_a_listas(c)
    except sqlite3.OperationalError as _err:
        anotar_error("puentes_sospechosos", _err)
        return []

    salida = []
    for cand in candidatos:
        try:
            c.execute("""
                SELECT p2.descripcion AS d, m2.nombre AS marca FROM equivalencias eq
                  JOIN productos p2 ON p2.id = CASE WHEN eq.producto_a_id = ?
                                                    THEN eq.producto_b_id ELSE eq.producto_a_id END
                  JOIN marcas m2 ON m2.id = p2.marca_id
                 WHERE ? IN (eq.producto_a_id, eq.producto_b_id)""", (cand["pid"], cand["pid"]))
            colgados = filas_a_listas(c)
        except sqlite3.OperationalError as _err:
            anotar_error("puentes_sospechosos", _err)
            continue
        # "Sin clasificar" no cuenta como familia: es no saber, no es una familia distinta.
        # Sin esta salvedad, 2H0919050B —un código de VW de verdad— daba tres familias solo
        # porque una de las descripciones no se pudo clasificar, y quedaba marcado como falso.
        # familia_para_comparar() y no clasificar_repuesto(): un kit cuelga de un código con
        # varias familias adentro y, contado como una, hace ver mezcla donde no la hay.
        familias = {familia_para_comparar(x["d"] or "") for x in colgados}
        familias = {f for f in familias if f and f != "Sin clasificar"}
        motivos = []
        if cand["Productos que une"] > tope:
            motivos.append(f"une {cand['Productos que une']} productos "
                           f"(un código real casi nunca pasa de {tope})")
        if len(familias) >= 3:
            motivos.append("mezcla " + ", ".join(sorted(familias)))
        if not motivos:
            continue
        cand["Por qué sospecha"] = "; ".join(motivos)
        cand["Familias"] = ", ".join(sorted(familias)) or "—"
        cand["Ejemplos"] = " | ".join(f"{x['marca']}: {(x['d'] or '')[:44]}" for x in colgados[:3])
        salida.append(cand)
        if len(salida) >= limite:
            break
    return salida


def borrar_puente(producto_oem_id):
    """Borra un código de fábrica falso y TODOS los vínculos que colgaban de él.

    Se borra el producto OEM entero y no vínculo por vínculo: el código no existe, así que
    dejarlo suelto sin vínculos solo ensucia la búsqueda por código. Los productos de los
    proveedores no se tocan — lo único que se pierde es la relación falsa entre ellos."""
    try:
        # Todo o nada: si se borran los vínculos pero no el producto OEM, queda un código de
        # fábrica falso suelto en el catálogo, que es exactamente lo que se quería sacar.
        with transaccion():
            c.execute("DELETE FROM equivalencias WHERE producto_a_id = ? OR producto_b_id = ?",
                      (producto_oem_id, producto_oem_id))
            borrados = c.rowcount
            c.execute("DELETE FROM productos WHERE id = ? AND marca_id IN "
                      "(SELECT id FROM marcas WHERE tipo = 'OEM')", (producto_oem_id,))
        return borrados
    except sqlite3.OperationalError as _err:
        anotar_error("borrar_puente", _err)
        return 0

"""Integridad de la base, copias de seguridad, restaurar y el mantenimiento que corre solo.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================================================
# INTEGRIDAD DE LA BASE, BACKUP Y RESTAURACIÓN
# ============================================================================================
def codigos_de_barras_mal_cargados():
    """Las listas cuyos «códigos de fábrica» son en realidad códigos de barras, y cuántos son.

    Es la parte curable del problema que reporta listas_que_no_cruzan(). Antes de que el EAN
    tuviera columna propia, la única forma de dejarlo buscable era cargarlo como código de
    fábrica, y eso deja una equivalencia por producto que no lleva a ningún lado.

    No alcanza con mirar un código suelto: un número de 13 dígitos puede ser un código de
    fábrica de verdad que todavía no tiene nadie más. Lo que lo delata es el conjunto — todos
    los de esa lista con el mismo prefijo de empresa—, así que la decisión se toma por LISTA y
    no por código, con el mismo criterio que usa la vista previa de la importación."""
    c.execute("""SELECT m.id AS marca_id, m.nombre AS marca FROM marcas m
                 WHERE m.tipo <> 'OEM' AND EXISTS (SELECT 1 FROM productos p WHERE p.marca_id = m.id)""")
    salida = []
    for prov in filas_a_listas(c):
        # En UNA fila (group_concat): son hasta 3.000 por lista y esto corre en el chequeo de
        # salud, o sea en cualquier pantalla cada tres minutos. Fila por fila, mientras trabaja
        # la tarea de fondo cada una espera su turno para el intérprete y la pantalla de
        # códigos de barras tardaba 1-2 s. Ver codigos_limpios_desfasados(). Los códigos
        # limpios no tienen caracteres de control, así que el 31 separa sin ambigüedad.
        c.execute("""SELECT group_concat(codigo, char(31)) FROM (
                         SELECT DISTINCT po.codigo_clean AS codigo
                         FROM productos p JOIN equivalencias e
                           ON e.producto_a_id = p.id OR e.producto_b_id = p.id
                         JOIN productos po ON po.id = CASE WHEN e.producto_a_id = p.id
                                                           THEN e.producto_b_id ELSE e.producto_a_id END
                         JOIN marcas mo ON mo.id = po.marca_id
                         WHERE p.marca_id = ? AND mo.tipo = 'OEM' LIMIT 3000)""",
                  (prov["marca_id"],))
        _juntos = c.fetchone()[0]
        _codigos_oem = _juntos.split("\x1f") if _juntos else []
        es_barras, prefijo, _ = columna_es_codigo_de_barras(_codigos_oem)
        if not es_barras:
            continue
        c.execute(_CONSULTA_BARRAS_MAL_CARGADOS.format(que="COUNT(*) AS cuantos"),
                  (prov["marca_id"],))
        fila = c.fetchone()
        cuantos = (fila["cuantos"] if fila else 0) or 0
        if cuantos:
            salida.append({"marca_id": prov["marca_id"], "Lista": prov["marca"],
                           "Códigos de barras cargados como código de fábrica": cuantos,
                           # Sin prefijo común quiere decir que se detectó por el dígito
                           # verificador: son códigos de barras de fábricas distintas.
                           "Empiezan con": (prefijo + "…" if prefijo else "prefijos varios"),
                           "Registrado en": pais_de_estos_codigos(_codigos_oem) or "—"})
    return salida


# El SQL va aparte porque lo usan las dos: la que cuenta y la que arregla. Si cada una tuviera
# el suyo, contarían una cosa y arreglarían otra en cuanto alguien tocara uno de los dos.
# Las tres condiciones: que sea un número largo (12 a 14 dígitos, la forma de un EAN o un UPC),
# que esté cargado bajo la marca OEM, y que cuelgue UN SOLO producto — o sea que no está
# sirviendo de puente entre dos proveedores. Si colgara dos, algo une y no se toca.
_CONSULTA_BARRAS_MAL_CARGADOS = """
    SELECT {que}
    FROM productos p
    JOIN equivalencias e ON e.producto_a_id = p.id OR e.producto_b_id = p.id
    JOIN productos po ON po.id = CASE WHEN e.producto_a_id = p.id
                                      THEN e.producto_b_id ELSE e.producto_a_id END
    JOIN marcas mo ON mo.id = po.marca_id
    WHERE p.marca_id = ?
      AND mo.tipo = 'OEM'
      AND LENGTH(po.codigo_clean) BETWEEN 12 AND 14
      AND po.codigo_clean NOT GLOB '*[^0-9]*'
      AND (SELECT COUNT(*) FROM equivalencias e2
            WHERE e2.producto_a_id = po.id OR e2.producto_b_id = po.id) = 1"""


def mover_codigos_de_barras_a_su_columna(marca_id):
    """Pasa los códigos de barras de esa lista a productos.codigo_barras y saca el vínculo falso.

    No se pierde nada: el número queda guardado en el producto —se puede escanear y la búsqueda
    lo encuentra— y lo que desaparece es el producto fantasma que lo representaba bajo la marca
    «OEM / FABRICA» junto con la equivalencia que salía de él, que es la que hacía creer que el
    repuesto tenía un equivalente.

    Devuelve (cuántos se movieron, cuántos ya tenían código de barras cargado)."""
    movidos = ya_tenian = 0
    with db_lock, transaccion():
        c.execute(_CONSULTA_BARRAS_MAL_CARGADOS.format(
            que="p.id AS prov_id, po.id AS oem_id, po.codigo_raw AS barras, p.codigo_barras AS tenia"),
            (marca_id,))
        for fila in filas_a_listas(c):
            if fila["tenia"]:
                ya_tenian += 1
            else:
                c.execute("UPDATE productos SET codigo_barras = ? WHERE id = ?",
                          (sanitizar(fila["barras"]), fila["prov_id"]))
            c.execute("DELETE FROM equivalencias WHERE producto_a_id = ? OR producto_b_id = ?",
                      (fila["oem_id"], fila["oem_id"]))
            c.execute("DELETE FROM productos WHERE id = ?", (fila["oem_id"],))
            movidos += 1
    return movidos, ya_tenian


# A partir de acá se decide por LISTA y no por código suelto. El número sale de la misma idea
# que columna_es_codigo_de_barras(): un código roto es una excepción, y si la excepción es la
# mayoría entonces no es una excepción — es otro sistema de numeración.
PROPORCION_PARA_DECIR_QUE_ES_ETIQUETA_PROPIA = 0.5


def codigos_de_barras_que_no_cierran(limite=200):
    """Los códigos de barras cargados que parecen mal copiados. Devuelve (filas, listas_propias).

    Un dígito cambiado en la planilla del proveedor deja un producto que no se va a poder
    escanear: la cámara lee el número de la caja, no coincide con el cargado, y el repuesto no
    aparece. Desde el mostrador se ve como «el escáner no anda».

    PERO ESO SOLO VALE SI LA ETIQUETA LA IMPRIMIÓ EL FABRICANTE. Un negocio que etiqueta su
    propia mercadería genera los números él mismo, y no tienen por qué cumplir la cuenta de
    GS1 — son códigos internos, y el escáner los encuentra perfecto porque la etiqueta se
    imprimió DESDE ese número: coinciden letra por letra, cierre la cuenta o no.

    Así que la decisión se toma por lista y no por código: si en una lista falla la mitad o más,
    eso no son errores de tipeo, es una numeración propia, y esa lista sale del control entera.
    Avisar ahí sería mandar a alguien a revisar miles de cajas que están bien.

    La segunda parte devuelta son justamente esas listas, para poder decirlo en pantalla en vez
    de callarse: que un control decida no mirar algo también hay que contarlo."""
    try:
        c.execute("""SELECT p.id, p.codigo_raw AS "Código", m.nombre AS "Lista",
                            p.codigo_barras AS "Código de barras", p.descripcion AS "Descripción"
                     FROM productos p JOIN marcas m ON m.id = p.marca_id
                     WHERE p.codigo_barras IS NOT NULL AND TRIM(p.codigo_barras) <> ''
                     ORDER BY m.nombre, p.codigo_raw""")
        filas = filas_a_listas(c)
    except sqlite3.OperationalError as _err:
        anotar_error("codigos_de_barras_que_no_cierran", _err)
        return [], []

    # El filtro va en Python y no en SQL porque la cuenta de GS1 no se escribe en SQLite sin
    # una tabla de pesos; igual son los que tienen código de barras cargado, no el catálogo.
    por_lista = {}
    for f in filas:
        cierra = codigo_de_barras_cierra(f["Código de barras"])
        if cierra is None:
            continue            # no tiene forma de código de barras: no es asunto de esta cuenta
        estado = por_lista.setdefault(f["Lista"], {"malos": [], "total": 0})
        estado["total"] += 1
        if cierra is False:
            estado["malos"].append(f)

    malos, propias = [], []
    for lista, estado in sorted(por_lista.items()):
        if not estado["malos"]:
            continue
        if (len(estado["malos"])
                >= estado["total"] * PROPORCION_PARA_DECIR_QUE_ES_ETIQUETA_PROPIA):
            propias.append({"Lista": lista, "Códigos": estado["total"]})
            continue
        malos.extend(estado["malos"])
    return malos[:limite], propias


def el_negocio_etiqueta_con_codigos_propios():
    """¿Este negocio imprime sus propias etiquetas? Se deduce de lo que ya está cargado.

    Cambia lo que hay que decirle a alguien que escanea algo que no aparece. Si el negocio
    usa etiquetas del fabricante, un código que arranca en 200-299 es de uso interno de OTRO
    comercio y no identifica ningún repuesto: escaneaste la etiqueta equivocada. Si el negocio
    imprime las suyas, ese mismo número es probablemente una etiqueta propia que todavía no se
    cargó, que es un consejo completamente distinto."""
    try:
        c.execute("""SELECT codigo_barras FROM productos
                     WHERE codigo_barras IS NOT NULL AND TRIM(codigo_barras) <> '' LIMIT 3000""")
        for fila in c.fetchall():
            if pais_del_codigo_de_barras(fila["codigo_barras"]) in GS1_NO_ES_UN_PAIS:
                return True
    except sqlite3.OperationalError as _err:
        anotar_error("el_negocio_etiqueta_con_codigos_propios", _err)
    return False


def cargar_codigos_de_barras_masivo(pares, marca_id=None, pisar=True):
    """Pega códigos de barras a productos que YA existen. No crea ni borra nada.

    Es la forma de traer una etiquetación que ya está hecha. Hasta ahora la única manera de
    cargar códigos de barras era reimportar la lista entera del proveedor con la columna
    mapeada, y eso toca todo lo demás: pisa precios, pisa stock, genera equivalencias nuevas y
    deja un lote de importación para revisar. Para pegarle un número a cada producto eso es una
    operación enorme al lado de lo que hace falta.

    Esto hace SOLO eso: busca el producto por su código de fábrica y le pone el código de
    barras. Si el código no está cargado, no lo inventa — lo informa. Un producto que no existe
    con un código de barras pegado no sirve para nada, y crear productos desde acá sería la
    forma más fácil de llenar el catálogo de fantasmas.

    `pares` es [(codigo_del_producto, codigo_de_barras), ...].
    `marca_id` acota a una lista: el mismo código de fábrica lo tienen varios proveedores, y sin
    acotar se le pegaría la misma etiqueta a los productos de todos.
    `pisar=False` respeta los que ya tienen uno cargado, para poder completar sin arriesgar.

    Devuelve un resumen con lo que pasó con cada fila, que es lo que hay que poder mirar antes
    de darlo por bueno."""
    resumen = {"puestos": 0, "sin_producto": [], "ya_tenian": [], "repetidos": [],
               "sin_cambio": 0, "ambiguos": [], "rotos_por_excel": []}
    if not pares:
        return resumen

    # PRIMERO lo que Excel rompió. Si el archivo trae la columna en notación científica, los
    # dígitos ya no están y reconstruirlos da un código plausible y equivocado. Frenar es lo
    # único correcto: ver excel_le_comio_digitos().
    rotos = {codigo for codigo, barras in pares if excel_le_comio_digitos(barras)}
    resumen["rotos_por_excel"] = [{"Código": codigo, "Vino como": barras}
                                  for codigo, barras in pares
                                  if excel_le_comio_digitos(barras)][:200]

    # Un mismo código de barras para dos productos distintos es un error de la planilla, y es
    # de los que no se ven: escanear esa etiqueta va a traer dos repuestos y nadie va a saber
    # cuál es. No se escriben: avisar después de haberlos puesto sería dejar el problema hecho.
    # Se comparan YA LIMPIOS: «779-396-0026946» y «7793960026946» son el mismo número, y
    # comparando el texto crudo pasarían como dos distintos.
    # Los que rompió Excel quedan afuera de esta cuenta: todos se reconstruyen al mismo número
    # y saldrían listados también como repetidos, que es dar dos diagnósticos del mismo
    # problema. El repetido de verdad es el que hay que poder ver.
    vistos = {}
    for codigo, barras in pares:
        limpio_b = sanitizar(barras)
        if limpio_b and codigo not in rotos:
            vistos.setdefault(limpio_b, []).append(codigo)
    duplicados = {b for b, cs in vistos.items() if len(cs) > 1}
    resumen["repetidos"] = [{"Código de barras": b, "Se lo pusiste a": ", ".join(cs[:6])}
                            for b, cs in vistos.items() if len(cs) > 1]

    with db_lock, transaccion():
        for codigo, barras in pares:
            limpio = sanitizar(codigo)
            barras_limpio = sanitizar(barras)
            if not limpio or not barras_limpio:
                continue
            if codigo in rotos or barras_limpio in duplicados:
                continue
            if marca_id:
                c.execute("SELECT id, codigo_barras FROM productos "
                          "WHERE codigo_clean = ? AND marca_id = ?", (limpio, marca_id))
            else:
                # p.id y p.codigo_barras CALIFICADOS, y no es cosmética: `id` existe en
                # productos y en marcas, así que sin el alias SQLite corta con «ambiguous
                # column name: id». Esta rama es la que corre cuando no se elige una lista —y
                # «— todas las listas —» es la PRIMERA opción del selector, o sea la que viene
                # puesta—, así que el camino por defecto de pegar códigos de barras en masa
                # nunca funcionó: se subía la planilla, se tildaba el candado, se apretaba el
                # botón y se caía la pantalla con un error crudo. Ni siquiera quedaba anotado,
                # porque la excepción no la atrapa nadie.
                # Los `AS` van a propósito: abajo se lee fila["id"] y fila["codigo_barras"].
                # Tranquiliza una cosa: reventaba en el primer SELECT, antes de cualquier
                # UPDATE, así que era «no anda», no «deja la base a medias».
                c.execute("SELECT p.id AS id, p.codigo_barras AS codigo_barras FROM productos p "
                          "JOIN marcas m ON m.id = p.marca_id "
                          "WHERE p.codigo_clean = ? AND m.tipo <> 'OEM'", (limpio,))
            filas = filas_a_listas(c)
            if not filas:
                resumen["sin_producto"].append({"Código": codigo, "Código de barras": barras})
                continue
            if len(filas) > 1 and not marca_id:
                # Sin elegir la lista, el mismo código de fábrica aparece en varios proveedores.
                resumen["ambiguos"].append({"Código": codigo, "Productos": len(filas)})
                continue
            for fila in filas:
                if fila["codigo_barras"] and not pisar:
                    resumen["ya_tenian"].append({"Código": codigo,
                                                  "Ya tenía": fila["codigo_barras"],
                                                  "Traía": barras})
                    continue
                if (fila["codigo_barras"] or "") == barras_limpio:
                    resumen["sin_cambio"] += 1
                    continue
                c.execute("UPDATE productos SET codigo_barras = ? WHERE id = ?",
                          (barras_limpio, fila["id"]))
                resumen["puestos"] += 1
    return resumen


# QUIÉN FABRICA LA PIEZA. No confundir con la marca de la tabla `marcas`, que es quién te la
# vende: JL, MOTORARG, ILLINOIS, FISPA. En el mostrador la primera pregunta suele ser «¿lo
# tenés en Bosch o en Masser?», y ese dato no estaba en ninguna columna.
#
# La lista es curada y no adivinada, y vale explicar por qué. Se midió, sobre las 46.644
# descripciones de proveedor, con qué frecuencia cada palabra aparece AL FINAL contra cuántas
# veces aparece en cualquier lado — una marca es una firma, va al final. Eso separa muy bien a
# MASSER (1,00), CAUPLAS (1,00), FLORIO (1,00) o MLH (0,98)… pero NO alcanza: BOSCH da 0,32 y
# MARELLI 0,59, porque también aparecen en el medio como referencia cruzada («REF ORIG BOSCH
# 0281002764»). Y al revés, RETENES da 0,68 y DIESEL 0,27 sin ser marcas de nada.
# O sea que la proporción sirve para DESCUBRIR candidatos, no para decidir. La decisión es una
# lista, como la de las marcas de vehículo.
#
# El nombre NO es MARCAS_DE_REPUESTO aunque sea lo que uno escribiría: ese nombre ya existe más
# abajo y es otra cosa —el conjunto de marcas que hay que DESPEGAR de un texto pegado—. Las dos
# definiciones a nivel módulo convivían sin romperse solo porque esta se usa antes de que la
# otra la pise, que es la clase de cosa que anda hasta el día que deja de andar.
MARCAS_QUE_FABRICAN_LA_PIEZA = [
    "MAGNETI MARELLI", "MAGNETI", "MARELLI", "BOSCH", "MASSER", "CAUPLAS", "METALGRAF",
    "DELPHI", "FLORIO", "WEBER", "SOLEX", "INDUMAG", "ARGELITE", "NGK", "RALUX", "AUTRONIC",
    "VUARAM", "RO-FIL", "ROFIL", "GALILEO", "THOMSON", "MLH", "MLS", "WAGNER", "VALEO",
    "SKF", "MANN", "SACHS", "MAHLE", "CORTECO", "VICTOR REINZ", "REINZ", "TARANTO",
    "LUCAS", "DENSO", "HENGST", "TRW", "FRAM", "WIX", "MONROE", "GABRIEL",
    # Estas nueve salieron de CONTAR, no de acordarse: se listaron las últimas palabras de las
    # 70.888 descripciones reales, se sacaron las que son marca de AUTO («FIAT», «RENAULT») y
    # las que son palabra de repuesto («DIESEL», «CILINDRO»), y quedaron estas, cada una
    # cerrando la descripción como la cierra un fabricante. Son 422 productos más.
    # DAYCO aparece 73 veces en el catálogo y NO está acá: ninguna de esas 73 la tiene al
    # final —siempre está en el medio de un kit— y esta lista solo lee el final.
    "PRESTOLITE", "KOBLA", "BOUGICORD", "HOLLEY", "TAILLOT", "INDIEL", "LOCX", "PAIA", "GATES",
]

# De más larga a más corta, para que «MAGNETI MARELLI» gane sobre «MARELLI».
_RE_MARCA_DE_REPUESTO = re.compile(
    r"(?:^|[\s\-/.,])(" + "|".join(re.escape(m) for m in
                                   sorted(MARCAS_QUE_FABRICAN_LA_PIEZA, key=len,
                                          reverse=True)) + r")\s*$",
    re.IGNORECASE)


def marca_de_repuesto_en(descripcion):
    """Quién fabrica la pieza, si la descripción lo dice al final. None si no.

    Se pide que esté AL FINAL a propósito, y es lo que la hace confiable: ahí es donde el
    proveedor firma la pieza. En el medio la misma marca aparece como referencia cruzada
    —«REF ORIG BOSCH 0281002764»— y ahí no quiere decir que la pieza sea Bosch, quiere decir
    que reemplaza a una que sí lo es.

    Medido sobre las 46.644 descripciones de proveedor: reconoce 13.705, encabezadas por
    MASSER (6.261), CAUPLAS (3.483), BOSCH (833), MLH (563) y MARELLI (555). En una muestra de
    14 al azar revisada a mano, 14 correctas."""
    if not descripcion:
        return None
    hallado = _RE_MARCA_DE_REPUESTO.search(str(descripcion).strip())
    return hallado.group(1).upper() if hallado else None


def reseparar_descripciones_viejas():
    """Vuelve a pasar el separador de texto pegado por las descripciones ya cargadas.

    separar_texto_pegado() corre al importar, pero fue aprendiendo después: las descripciones
    que entraron antes quedaron como vinieron. Sobre la base real son **12.255 de 70.888 que
    todavía cambiarían**, y lo que arregla casi siempre es lo mismo: el «REF ORIG» pegado a la
    palabra anterior, que se come lo que venía justo antes.

        antes: «…TOYOTA COROLLA 1 6 - 1 8REF ORIG…»
        ahora: «…TOYOTA COROLLA 1 6 - 1 8 REF ORIG…»

    Medido qué gana y qué pierde, sobre esas 12.255:

        combustible  +377   -6
        medidas       +68    0
        familia        +5    0
        fabricante     +1    0
        motor           0   -3

    Los 3 «motores perdidos» son en realidad el arreglo: antes se leía «YD25REF» —el motor
    pegado a REF— que no es ningún motor. Lo que se pierde es un dato equivocado.

    No se reprocesan los años, y vale aclararlo porque era lo que se esperaba ganar: sobre esta
    base, cero descripciones recuperan un año. La ganancia está en el combustible.

    La columna `busqueda` se mantiene sola: hay un trigger AFTER UPDATE OF descripcion."""
    cambiadas = 0
    try:
        c.execute("""SELECT id, descripcion FROM productos
                     WHERE descripcion IS NOT NULL AND descripcion <> ''""")
        filas = filas_a_listas(c)
    except sqlite3.OperationalError as _err:
        anotar_error("reseparar_descripciones_viejas", _err)
        return 0
    # El candado se suelta cada tanda: ver FILAS_ANTES_DE_SOLTAR_EL_CANDADO.
    for tanda in en_tandas_para_no_trabar(filas):
        with db_lock:
            for fila in tanda:
                separada = separar_texto_pegado(fila["descripcion"])
                if separada and separada != fila["descripcion"]:
                    c.execute("UPDATE productos SET descripcion = ? WHERE id = ?",
                              (separada, fila["id"]))
                    cambiadas += 1
            conn.commit()
    return cambiadas


def completar_marcas_de_repuesto():
    """Llena productos.marca_repuesto leyendo el final de cada descripción. Devuelve cuántos.

    Solo toca los que están vacíos: si alguien la corrigió a mano, no se la pisa."""
    ceder_al_mostrador()      # antes de la lectura grande. Ver ceder_al_mostrador().
    puestos = 0
    c.execute("""SELECT p.id, p.descripcion FROM productos p
                 JOIN marcas m ON m.id = p.marca_id
                 WHERE m.tipo <> 'OEM'
                   AND (p.marca_repuesto IS NULL OR p.marca_repuesto = '')
                   AND p.descripcion IS NOT NULL AND p.descripcion <> ''""")
    pendientes = filas_a_listas(c)
    # El candado se suelta cada tanda: ver FILAS_ANTES_DE_SOLTAR_EL_CANDADO.
    for tanda in en_tandas_para_no_trabar(pendientes):
        with db_lock:
            for fila in tanda:
                marca = marca_de_repuesto_en(fila["descripcion"])
                if marca:
                    c.execute("UPDATE productos SET marca_repuesto = ? WHERE id = ?",
                              (marca, fila["id"]))
                    puestos += 1
            conn.commit()
    return puestos


# DÓNDE VA LA PIEZA. Tres ejes, y de cada uno se toma un lado solo.
# Las abreviaturas van con punto, guion o final de texto a propósito, y esto costó una medición:
# «DEL» suelto es la preposición más común del español, y con ella «Junta Tapa de Cilindros
# FORD CORCEL PAMPA DEL REY» —que es el Ford Del Rey— quedaba como pieza DELANTERA. Exigiendo
# «DEL.» o «DEL-», los falsos positivos desaparecen: de 4.239 productos se baja a 3.528, y en
# una muestra de 16 al azar revisada a mano, 16 correctas.
FORMAS_DE_POSICION = {
    "DELANTERA": r"DELANTER[OA]S?|FRONTAL(?:ES)?|(?<![A-Z])DEL(?=[.\-]|\s*$)",
    "TRASERA":   r"TRASER[OA]S?|POSTERIOR(?:ES)?|(?<![A-Z])TRAS(?=[.\-]|\s*$)",
    "IZQUIERDA": r"IZQUIERD[OA]S?|(?<![A-Z])IZQ(?![A-Z])",
    "DERECHA":   r"DERECH[OA]S?|(?<![A-Z])DER(?![A-Z])",
    "SUPERIOR":  r"SUPERIOR(?:ES)?|(?<![A-Z])SUP(?=[.\-]|\s*$)",
    "INFERIOR":  r"INFERIOR(?:ES)?|(?<![A-Z])INF(?=[.\-]|\s*$)",
}
_RE_POSICION = {k: re.compile(v, re.IGNORECASE) for k, v in FORMAS_DE_POSICION.items()}
EJES_DE_POSICION = [("DELANTERA", "TRASERA"), ("IZQUIERDA", "DERECHA"),
                    ("SUPERIOR", "INFERIOR")]


# CON QUÉ ANDA EL AUTO. Las siglas valen tanto como la palabra: nadie escribe «diesel» al lado
# de «HDI», y «MPI» quiere decir nafta sin decirlo.
FORMAS_DE_DIESEL = (r"DIESEL|D[IÍ]ESEL|TURBODIESEL|TDI|HDI|CRDI|JTD|DCI|TDCI|CDI|MULTIJET|"
                    r"D4D|CTDI")
FORMAS_DE_NAFTA = r"NAFTA|NAFTERO|NAFTEROS|GASOLINA|MPFI|MPI|TFSI|TSI|GDI|FLEX"
_RE_DIESEL = re.compile(r"(?<![A-Z])(" + FORMAS_DE_DIESEL + r")(?![A-Z])", re.IGNORECASE)
_RE_NAFTA = re.compile(r"(?<![A-Z])(" + FORMAS_DE_NAFTA + r")(?![A-Z])", re.IGNORECASE)


# Forma de código de proveedor y no de modelo de auto: tres o más letras seguidas de números
# («LRA974», «ALTT150», «STRB014»), o letras y números alternados en dos grupos («D6RA32»).
_RE_FORMA_DE_CODIGO_DE_PROVEEDOR = re.compile(
    r"^[A-Z]{3,}\d{2,}[A-Z0-9]*$|^[A-Z]{1,3}\d{1,3}[A-Z]{1,3}\d", re.IGNORECASE)


# Los dos lugares donde la designación del motor está dicha sin ambigüedad: detrás de la
# palabra MOTOR, y detrás de la cilindrada entre guiones, que es como escriben estas listas
# («Junta Tapa de Cilindros CHEVROLET SPIN COBALT - 1.8 - N18XFN»).
_RE_MOTOR_TRAS_LA_PALABRA = re.compile(r"\bMOTOR(?:ES)?\s+([A-Z0-9][A-Z0-9.\-]{2,})",
                                       re.IGNORECASE)
_RE_MOTOR_TRAS_LA_CILINDRADA = re.compile(
    r"-\s*\d[.,]?\d?(?:/\d[.,]?\d?)*\s*-\s*([A-Z0-9][A-Z0-9.\-]{2,})", re.IGNORECASE)


# Cualquier palabra con pinta de código, para después preguntarle a parece_designacion_de_motor()
# cuál de ellas es un motor. Se usa para aprender qué motores conviven en una descripción.
_RE_TOKEN_DE_MOTOR = re.compile(r"[A-Z0-9][A-Z0-9.\-]{2,}", re.IGNORECASE)


def motor_desde_descripcion(descripcion):
    """La designación del motor, si la descripción la dice sin ambigüedad. None si no.

    No alcanza con buscar una palabra con forma de motor suelta en el texto, y medirlo lo dejó
    claro: eso da 2.109 productos y se cuelan cosas como «Y10I» —que es el Lancia Y10— o
    «JA0REF», que son dos pedazos pegados. Hace falta que el texto diga DÓNDE está el motor.

    Hay dos lugares donde lo dice sin dudar:
      · detrás de la palabra MOTOR: «Aro piston RENAULT Kangoo - Motor K7M - Nafta»;
      · detrás de la cilindrada entre guiones, que es la forma fija de estas listas:
        «Junta Tapa de Cilindros CHEVROLET SPIN COBALT - 1.8 - N18XFN».

    Las dos juntas dan 998 productos y 187 motores distintos, encabezados por F8Q (39), K9K
    (37), K7M (30) y TU5JP4 (30). En dos muestras de 10 y 14 al azar revisadas a mano, 24/24
    correctas.

    Si la descripción nombra DOS motores distintos no se devuelve ninguno: son listas que
    cubren varias motorizaciones y no se puede decir cuál es."""
    if not descripcion:
        return None
    texto = str(descripcion)
    hallados = set()
    for expresion in (_RE_MOTOR_TRAS_LA_PALABRA, _RE_MOTOR_TRAS_LA_CILINDRADA):
        for encontrado in expresion.finditer(texto):
            candidato = encontrado.group(1).upper()
            if parece_designacion_de_motor(candidato):
                hallados.add(candidato)
    return next(iter(hallados)) if len(hallados) == 1 else None


def parece_un_codigo_y_no_un_modelo(palabra, codigos_del_catalogo):
    """¿Esta «palabra» que parece un modelo de auto es en realidad un código de repuesto?

    Salió de mirar las 4.229 combinaciones marca+modelo que el extractor saca de las
    descripciones: «VOLVO LRA974», «IVECO ALTT150», «DAF STRB014», «FIAT D6RA32». Nadie busca
    repuestos «para un LRA974» — es el propio número del proveedor, que quedó adentro de la
    descripción y el extractor lo tomó por modelo. Y como aparece en decenas de descripciones,
    junta entre sí todo lo que lo nombre.

    DOS condiciones, y la segunda es la que importa. La primera es que la palabra exista como
    código en el catálogo. Sola no alcanza, y medirlo lo dejó claro: **«F1000» está cargado
    como código de un repuesto Y es una Ford F1000 de verdad**, así que con la primera
    condición a secas se perdía un modelo real. Lo mismo con «S16» (el Peugeot 306 S16) y
    «NV200» (el Nissan NV200).

    La segunda es la FORMA: tres o más letras seguidas de números, o letras y números alternados
    en dos grupos. «F1000» tiene una sola letra adelante y queda afuera del filtro, que es lo
    que se quería.

    Medido sobre la base real: saca 298 combinaciones y 1.909 filas, y en una muestra de 14 al
    azar revisada a mano no hay un solo modelo de verdad — son códigos de proveedor
    (KPV149, KTB764, IWP101), designaciones de motor (EW10J4RFN, DOHC16V) y dos modelos pegados
    entre sí («GOL-R19»), que tampoco son un modelo.

    Es la misma idea que parece_designacion_de_motor(), una vuelta más: preguntarle al catálogo
    en vez de adivinar."""
    if not palabra or not codigos_del_catalogo:
        return False
    limpio = sanitizar(palabra)
    return bool(limpio in codigos_del_catalogo
                and _RE_FORMA_DE_CODIGO_DE_PROVEEDOR.match(limpio))


def combustible_desde_descripcion(descripcion):
    """«diesel», «nafta» o None. None también cuando la descripción dice las dos cosas.

    Una pieza del 1.6 nafta no entra en el 1.9 diesel aunque el auto se llame igual, así que
    esto sirve de las dos maneras: como dato a la vista y para no cruzar por auto dos piezas
    que no se pueden reemplazar.

    Medido sobre las 46.644 descripciones de proveedor: 4.292 dicen diesel, 2.215 dicen nafta,
    y 129 dicen las dos —listas que cubren las dos versiones del mismo auto— y quedan sin
    decidir. En una muestra de 14 al azar revisada a mano, 14 correctas."""
    if not descripcion:
        return None
    texto = str(descripcion)
    es_diesel, es_nafta = bool(_RE_DIESEL.search(texto)), bool(_RE_NAFTA.search(texto))
    if es_diesel == es_nafta:
        return None      # ninguna, o las dos: no se puede decidir
    return "diesel" if es_diesel else "nafta"


def posicion_desde_descripcion(descripcion):
    """Dónde va la pieza, si la descripción lo dice sin ambigüedad. None si no.

    Si nombra LOS DOS lados de un eje —«delantero y trasero», un kit que trae ambos— devuelve
    None para ese eje: no se puede decir dónde va, y adivinar sería peor que no saber, porque
    esto alimenta un veto.

    Sirve para dos cosas. Como filtro y como dato a la vista —«¿el de adelante o el de
    atrás?» es media conversación del mostrador— y como PRUEBA FÍSICA: el caño superior del
    radiador no reemplaza al inferior, por más que los dos sean del mismo auto."""
    if not descripcion:
        return None
    texto = str(descripcion)
    presentes = {k for k, rx in _RE_POSICION.items() if rx.search(texto)}
    partes = []
    for uno, otro in EJES_DE_POSICION:
        tiene_uno, tiene_otro = uno in presentes, otro in presentes
        if tiene_uno and tiene_otro:
            return None      # nombra los dos: no se puede decidir
        if tiene_uno:
            partes.append(uno)
        elif tiene_otro:
            partes.append(otro)
    return "+".join(partes) or None


def codigo_base_sin_variante(codigo):
    """De «TC-687-20 2M» devuelve «TC-687-20»; de «JVL-168-28», «JVL-168». None si no queda nada.

    Casi todos los proveedores numeran las variantes de una misma pieza agregándole un sufijo
    corto al código: la junta de tapa de cilindros TC-687-20 viene en 1,50 / 1,60 / 1,70 mm y se
    llaman «TC-687-20 1M», «... 2M», «... 3M». Son la misma pieza en otra medida, no piezas
    distintas.

    Recorta TODOS los tramos cortos del final, no uno solo, mientras queden más de dos. Así
    «TC-687-20 2M» no queda en «TC-687-20» sino en «TC-687», porque en este catálogo el
    anteúltimo tramo también es de variante: «-20», «-MG» y «-11» son los materiales de la
    misma junta. Está medido: de los 350 grupos que se sueltan, 42 dependen del segundo
    recorte, y los 42 son la misma junta en otro material con el mismo espesor
    («TC-615-20 0M» con «TC-615-MG 0M», «TC-695-MG 2M» con «TC-695-11 2M»). Con un solo
    recorte se sueltan 287 en vez de 350.

    Nunca baja de DOS tramos, y ese piso es lo que evita que se pase de rosca: «JCA-123» se
    recortaría a «JCA», que es solo la sigla de la línea («Juego de juntas para Compresor de
    Aire») y la comparten kits de compresores distintos, que sí son piezas distintas. Con el
    piso, «JCA-123» y «JCA-121-15» quedan en bases distintas, que es lo correcto, y «JI-276»
    con «JI-276-R» —el mismo juego, con retenes— quedan en la misma."""
    u = re.sub(r"[\s\.]+", "-", (codigo or "").upper().strip())
    partes = [x for x in u.split("-") if x]
    while len(partes) > 2 and len(partes[-1]) <= 4:
        partes = partes[:-1]
    base = "-".join(partes)
    return base if any(ch.isdigit() for ch in base) else None


def son_variantes_de_la_misma_pieza(codigos):
    """¿Estos códigos de un mismo proveedor son la misma pieza en distintas medidas?

    Es la respuesta a una alarma que gritaba de más. «El código de fábrica X apunta a más de un
    producto del proveedor Y» resta 35 puntos, y la idea es buena: el fabricante tiene UNA pieza
    por número, así que dos productos del mismo proveedor colgando del mismo número quieren
    decir que alguno se cargó mal.

    Pero sobre la cola real la alarma saltaba en 557 grupos, y mirándolos: el número de FIAT
    7785351 cuelga «TC-615-MG 0M», «TC-615-MG 4M» y «TC-615-20 0M» —la misma junta de tapa de
    cilindros en 1,65 y 2,40 mm, en dos materiales—, y las tres entran en el mismo motor. No hay
    nada mal cargado; ILLINOIS vende la junta en varios espesores y las tres corresponden a ese
    número de fábrica.

    Con esta regla, de los 557 grupos se sueltan 350 y quedan marcados 207. Los que siguen
    marcados son los de verdad: el 7703061078 cuelga «2712800» (guarnición de bomba depresora)
    y «2627400» (arandela de fibra de tapa de válvula), que son dos piezas distintas y una de
    las dos está mal; y el 4JH1TC cuelga la junta de tapa de cilindros sola y el juego completo
    de reparación, que tampoco son equivalentes.

    Efecto en la cola de revisión, medido sobre los 3.185 pendientes reales:
        🟢 1.785 → 2.266     🟡 695 → 502     🔴 705 → 417
    y ninguno de los 2.266 verdes tiene una sola señal en contra ni una sola alarma.

    A propósito NO alcanza con que las descripciones arranquen igual: el compresor OHL355 cuelga
    JCA-120, JCA-121, JCA-122 y JCA-123, los cuatro descriptos «Juego de juntas para Compresor de
    Aire KNORR», y son cuatro kits distintos. Lo que distingue a una variante es el código."""
    bases = {codigo_base_sin_variante(x) for x in codigos}
    return len(bases) == 1 and None not in bases


PUNTAJE_QUE_NO_LLEGA_A_APROBAR_SOLO = 74.0   # el verde arranca en 75


def el_codigo_no_figura_entre_las_referencias(codigo, descripcion):
    """¿El «número de fábrica» se sacó del texto del vehículo en vez de la lista de referencias?

    ILLINOIS y varios más escriben la descripción con una forma fija: primero qué es la pieza y
    para qué autos, y al final los números de fábrica de verdad, entre paréntesis o detrás de
    «//». Cuando el número que quedó cargado como código de fábrica NO está en esa zona pero la
    zona existe y tiene otros números, lo que pasó es claro: el extractor lo levantó del texto
    del medio, donde van los motores y las designaciones de chasis.

    Ejemplos reales de la cola, todos hoy con 100 de confianza:
        «Junta para Cárter RENAULT CLIO … - 1,4/1,5/1,6 - K4M K4J K9K16V (8200………)»
         -> quedó cargado «K9K16V», que es el MOTOR; el número real está en el paréntesis.
        «Junta Tapa de Cilindros SCANIA … - 10,6/11,7 - 16… DSC12.01 (…)» -> «DSC12.01».
        «… PERKINS … 4.203/4-PA.203 …» -> «4-PA.203».

    NO BAJA A ROJO, BAJA A AMARILLO, y la diferencia importa. El objetivo es sacarlos del botón
    de «aprobar sin mirar», no darlos por perdidos. Revisando una muestra de 22 a mano, 17 eran
    designaciones de motor o de chasis y **5 eran números de fábrica reales con la marca pegada
    adelante** («AGCO SISU POWER836122282», «JOHN DEERER43413»). Con el castigo en rojo esas 5
    quedaban como basura; con el castigo en amarillo cuestan una mirada, que es lo que cuestan.

    Sobre la cola real toca 104 de los 2.560 vínculos que hoy se aprueban en bloque."""
    if not codigo or not descripcion:
        return False
    zona = " ".join([m.group(1) for m in re.finditer(r"\(([^)]*)\)", descripcion)]
                    + re.findall(r"//(.*)$", descripcion))
    if not zona:
        return False
    # La zona tiene que tener al menos un número con pinta de código; si son puras medidas
    # («ESP 1.50MM») no es una lista de referencias y no se puede concluir nada.
    if not any(any(ch.isdigit() for ch in t)
               for t in re.findall(r"[A-Z0-9][A-Z0-9./-]{4,}", zona.upper())):
        return False
    return sanitizar(codigo).upper() not in sanitizar(zona).upper()


def codigo_que_hoy_no_se_tomaria(codigo):
    """¿Es un código que las reglas de hoy ya NO aceptarían como código de fábrica?

    Es la pregunta que hace el control de puentes viejos, sacada a una función porque también
    hace falta al puntuar la cola de revisión. Y la forma de la pregunta importa: se le pasa el
    propio código como «conocido» para que NO se apliquen las formas ambiguas —esas existen
    para tirar designaciones de motor y se llevaban puestos códigos reales como «AT-05103R»—.
    Así solo quedan las formas que son texto sin discusión: un modelo de auto, un rango de
    años, una medida. Esas no dejan de serlo porque el proveedor las haya puesto en la columna
    del código."""
    limpio = sanitizar(codigo)
    if not limpio:
        return True
    return not extraer_codigos_de_texto(f"PIEZA {codigo} ORIG", minimo=1,
                                        codigos_conocidos={limpio})


def puentes_que_hoy_no_se_generarian(limite=400):
    """Códigos de fábrica que el extractor de HOY ya no sacaría de una descripción.

    Arreglar el extractor evita los puentes falsos que vienen. No arregla los que ya están, y
    esos son los que ensucian la búsqueda ahora mismo: cada vez que se le enseña a la app a
    reconocer un modelo o un motor, queda atrás una camada generada con las reglas viejas que
    nadie vuelve a revisar.

    Los encuentra sin inventar ningún criterio: le da la vuelta a cada código cargado, lo pone
    adentro de un texto y lo pasa por el MISMO extractor que se usa al importar. Si hoy no lo
    sacaría de una descripción, tampoco debería estar como código de fábrica.

    MIRA LAS DOS TABLAS, y esto es lo que fallaba en la primera versión: solo miraba
    `equivalencias` —los vínculos ya aprobados— y los códigos que generan el problema estaban
    casi todos en `equivalencias_pendientes`, esperando revisión. El usuario corría la limpieza,
    no encontraba nada, y los puentes falsos seguían ahí, en la cola. Un código que ensucia
    cuatro pendientes ensucia igual: son cuatro decisiones que hay que tomar por algo que no es
    un código.

    Un código malo que cuelga un solo producto no hace daño, así que se piden dos productos —y
    si son de dos listas distintas, peor, porque esa es la equivalencia falsa entre proveedores.
    """
    try:
        # Los vecinos de cada código, de las DOS tablas y en los dos sentidos. Va como CTE y no
        # repetido en la consulta para que las dos preguntas —cuántos une y qué une— salgan de
        # la misma definición: si se escriben dos veces, se despegan.
        c.execute("""
            WITH vecinos AS (
                SELECT producto_a_id AS ancla, producto_b_id AS otro, 1 AS cargada
                  FROM equivalencias
                UNION ALL
                SELECT producto_b_id, producto_a_id, 1 FROM equivalencias
                UNION ALL
                SELECT producto_a_id, producto_b_id, 0 FROM equivalencias_pendientes
                UNION ALL
                SELECT producto_b_id, producto_a_id, 0 FROM equivalencias_pendientes
            )
            SELECT po.id AS pid, po.codigo_raw AS "Código",
                   COUNT(DISTINCT v.otro) AS "Productos que une",
                   COUNT(DISTINCT p.marca_id) AS "Listas",
                   SUM(v.cargada) AS "Cargados",
                   SUM(1 - v.cargada) AS "Esperando revisión"
            FROM productos po
            JOIN marcas mo ON mo.id = po.marca_id
            JOIN vecinos v ON v.ancla = po.id
            JOIN productos p ON p.id = v.otro
            WHERE mo.tipo = 'OEM'
            GROUP BY po.id
            HAVING COUNT(DISTINCT v.otro) >= 2
            ORDER BY COUNT(DISTINCT v.otro) DESC""")
        candidatos = filas_a_listas(c)
    except sqlite3.OperationalError as _err:
        anotar_error("puentes_que_hoy_no_se_generarian", _err)
        return []

    salida = []
    for fila in candidatos:
        codigo = fila["Código"]
        # LA PREGUNTA EXACTA IMPORTA, y la primera versión hacía la equivocada.
        #
        # El extractor tiene dos juegos de reglas. Unas son AMBIGUAS: aciertan casi siempre,
        # pero la misma forma la tiene algún código de repuesto de verdad, así que dejan de
        # aplicarse en cuanto hay alguna señal de que eso ES un código. Las otras son texto sin
        # discusión: un modelo de auto no deja de serlo por nada.
        #
        # Preguntándole a secas, se aplican las ambiguas también, y el control marcaba como
        # falso a «AT-05103R» —un código real, que une dos motores paso a paso de la misma
        # aplicación Fiat/Renault— y a «BX8.4d», que es un zócalo de lámpara. Borrarlos habría
        # sacado vínculos buenos, que es exactamente lo que este control existe para no hacer.
        #
        # La pregunta correcta es más dura: «suponiendo que este código YA estuviera cargado en
        # la lista de un proveedor, ¿el extractor lo seguiría rechazando?». Así solo quedan las
        # formas que son texto sin discusión. Probado sobre 22 casos de la base real: respeta
        # los 8 códigos verdaderos y marca las 14 basuras, la familia «505REF» incluida.
        if not codigo_que_hoy_no_se_tomaria(codigo):
            continue
        # Un ejemplo de lo que está uniendo, que es lo que permite decidir sin salir a buscarlo.
        c.execute("""SELECT p.descripcion AS d, m.nombre AS marca FROM (
                         SELECT producto_a_id AS a, producto_b_id AS b FROM equivalencias
                         UNION ALL SELECT producto_b_id, producto_a_id FROM equivalencias
                         UNION ALL SELECT producto_a_id, producto_b_id FROM equivalencias_pendientes
                         UNION ALL SELECT producto_b_id, producto_a_id FROM equivalencias_pendientes
                     ) v JOIN productos p ON p.id = v.b
                       JOIN marcas m ON m.id = p.marca_id
                     WHERE v.a = ? LIMIT 2""", (fila["pid"],))
        ejemplos = filas_a_listas(c)
        fila["Une por ejemplo"] = " ↔ ".join(f"{x['marca']}: {(x['d'] or '')[:34]}"
                                              for x in ejemplos)
        salida.append(fila)
        if len(salida) >= limite:
            break
    return salida


def borrar_puente_y_sus_pendientes(producto_oem_id):
    """Saca un código de fábrica falso de las dos tablas. Devuelve (cargados, pendientes).

    borrar_puente() borra el producto OEM y sus vínculos aprobados, pero los pendientes que
    colgaban de él quedaban en la cola — y al aprobarlos volvían a crear exactamente el vínculo
    falso que se acababa de borrar."""
    pendientes = 0
    try:
        pendientes = rechazar_pendientes_de_producto(producto_oem_id)
    except Exception as _err:
        anotar_error("borrar_puente_y_sus_pendientes", _err)
    return borrar_puente(producto_oem_id), pendientes


def listas_que_no_cruzan():
    """Por cada proveedor: con cuántos otros proveedores cruza de verdad, y si no cruza, por qué.

    Es la respuesta a la pregunta que más se hace desde el mostrador: «¿por qué no me hace las
    equivalencias?». Hasta ahora había que adivinarlo. La búsqueda mostraba filas, la pantalla
    decía «2 coincidencias», y nadie veía que la segunda coincidencia era el mismo repuesto.

    La cuenta que importa no es cuántas equivalencias tiene una lista, es a cuántos productos de
    OTRO proveedor llega. Una lista puede tener 8.652 equivalencias cargadas y llegar a cero
    productos de otra marca: pasa cuando todos sus códigos de fábrica son suyos y de nadie más
    —el caso típico es que se haya mapeado la columna del código de barras— y es exactamente lo
    que se ve como «no relaciona nada».

    Devuelve una fila por proveedor, de peor a mejor."""
    c.execute("""
        SELECT m.id AS marca_id, m.nombre AS marca, COUNT(p.id) AS productos
        FROM marcas m JOIN productos p ON p.marca_id = m.id
        WHERE m.tipo <> 'OEM'
        GROUP BY m.id ORDER BY COUNT(p.id) DESC""")
    proveedores = filas_a_listas(c)

    esperando = productos_con_vinculos_esperando()

    filas = []
    for prov in proveedores:
        # Productos de esta lista que llegan a un producto de OTRO proveedor, sea directo o
        # pasando por un código de fábrica. Dos saltos alcanzan: proveedor -> código de
        # fábrica -> otro proveedor es el camino normal, y más lejos que eso ya no es evidencia.
        c.execute("""
            WITH mios AS (SELECT id FROM productos WHERE marca_id = ?),
                 vecinos AS (
                    SELECT mi.id AS mio,
                           CASE WHEN e.producto_a_id = mi.id THEN e.producto_b_id
                                ELSE e.producto_a_id END AS otro
                    FROM mios mi JOIN equivalencias e
                      ON e.producto_a_id = mi.id OR e.producto_b_id = mi.id),
                 segundos AS (
                    SELECT v.mio,
                           CASE WHEN e.producto_a_id = v.otro THEN e.producto_b_id
                                ELSE e.producto_a_id END AS otro
                    FROM vecinos v JOIN equivalencias e
                      ON e.producto_a_id = v.otro OR e.producto_b_id = v.otro)
            SELECT COUNT(DISTINCT t.mio) AS cruzan
            FROM (SELECT mio, otro FROM vecinos UNION SELECT mio, otro FROM segundos) t
            JOIN productos po ON po.id = t.otro
            JOIN marcas mo ON mo.id = po.marca_id
            WHERE mo.tipo <> 'OEM' AND mo.id <> ?""", (prov["marca_id"], prov["marca_id"]))
        cruzan = (c.fetchone() or {"cruzan": 0})["cruzan"] or 0

        # Los códigos de fábrica que esta lista aportó. Si son todos de la misma familia de
        # números largos, es la columna del código de barras.
        # El total va en su propia consulta y la muestra aparte: con LIMIT alcanzaba para
        # decidir si son códigos de barras, pero el número que se muestra en pantalla tiene
        # que ser el de verdad, no el del tope.
        # Los vínculos pendientes cuentan igual para esta pregunta: «qué códigos de fábrica
        # aportó esta lista» no depende de que alguien los haya aprobado todavía. Sin el UNION
        # la respuesta para una lista recién importada era 0, y de ahí salía el «se cargó sin
        # código de fábrica» que no era cierto.
        consulta_oem = """
            SELECT {que}
            FROM productos p JOIN (SELECT producto_a_id, producto_b_id FROM equivalencias
                                   UNION SELECT producto_a_id, producto_b_id
                                     FROM equivalencias_pendientes) e
              ON e.producto_a_id = p.id OR e.producto_b_id = p.id
            JOIN productos po ON po.id = CASE WHEN e.producto_a_id = p.id
                                              THEN e.producto_b_id ELSE e.producto_a_id END
            JOIN marcas mo ON mo.id = po.marca_id
            WHERE p.marca_id = ? AND mo.tipo = 'OEM'"""
        c.execute(consulta_oem.format(que="COUNT(DISTINCT po.codigo_clean) AS cuantos"),
                  (prov["marca_id"],))
        total_oem = (c.fetchone() or {"cuantos": 0})["cuantos"] or 0
        c.execute(consulta_oem.format(que="DISTINCT po.codigo_clean AS codigo")
                  + " LIMIT 3000", (prov["marca_id"],))
        codigos_oem = [r["codigo"] for r in c.fetchall()]
        es_barras, prefijo, _ = columna_es_codigo_de_barras(codigos_oem)

        # Los que ya tienen equivalencia encontrada y sin aprobar. Va primero de todo: el
        # síntoma es el mismo que el de una lista sin código de fábrica —cero cruces— y lo que
        # hay que hacer es lo contrario. Ver productos_con_vinculos_esperando().
        esperan = esperando.get(prov["marca_id"], 0)

        if cruzan:
            motivo = ""
        elif esperan:
            motivo = (f"{esperan:,} de sus productos YA tienen equivalencias encontradas, "
                      "esperando que las apruebes en Estadísticas → 🔗 Equivalencias "
                      "sugeridas. Mientras no se aprueben, la búsqueda no las usa")
        elif es_barras:
            _pais_pref = pais_de_estos_codigos(codigos_oem)
            _como = (f"empiezan todos con {prefijo}…"
                     + (f", el prefijo de una empresa de {_pais_pref}" if _pais_pref else "")
                     ) if prefijo else "cierran con su dígito verificador"
            motivo = (f"los códigos de fábrica de esta lista son códigos de barras ({_como}): "
                      f"no los tiene ningún otro proveedor")
        elif total_oem:
            motivo = ("los códigos de fábrica de esta lista no coinciden con los de ninguna "
                      "otra: puede ser que cada proveedor cite terminales distintas")
        else:
            motivo = "esta lista se cargó sin código de fábrica, así que no tiene con qué cruzar"

        filas.append({
            "Lista": prov["marca"],
            "Productos": prov["productos"],
            "Cruzan con otra marca": cruzan,
            "Esperando revisión": esperan,
            "Códigos de fábrica que aportó": total_oem,
            "Por qué no cruza": motivo,
            "_sin_cruce": not cruzan,
            "_solo_falta_revisar": bool(not cruzan and esperan),
        })
    return sorted(filas, key=lambda f: (f["Cruzan con otra marca"], -f["Productos"]))


TOPE_CODIGOS_ESCRITOS = 4000   # ver equivalencias_escritas_en_las_descripciones()


def equivalencias_escritas_en_las_descripciones(limite=TOPE_CODIGOS_ESCRITOS, progreso=None):
    """Los códigos de fábrica que el proveedor YA escribió en la descripción, cruzados contra el
    catálogo. Devuelve la lista de pares (id_a, id_b) que todavía no están ni cargados ni en la
    cola de revisión.

    Es el agujero que quedaba en el circuito de descubrimiento. Buscar el código de fábrica
    adentro del texto existía, pero SOLO en el momento de importar, detrás de una casilla que
    viene apagada («🔎 Buscar códigos de fábrica dentro de la descripción»). Si esa casilla no
    se tildó —y no se tildó— ese dato no se vuelve a mirar NUNCA: la descripción queda guardada
    con el número adentro y nadie lo lee otra vez.
    Y hay una razón de fondo para que tenga que ser retroactivo: el cruce solo existe cuando
    están las DOS listas. Una descripción de FISPA que cita «REF ORIG 0258006980» no vale nada
    hasta que se importa la lista de JL que vende ese Bosch — y para entonces la importación de
    FISPA ya pasó hace meses.

    SOLO se miran los códigos DECLARADOS por el proveedor: los que van después de «REF ORIG»,
    «//», «OEM», «EQUIVALE». Esa restricción es la decisión cara de esta función y está medida
    sobre las 70.888 descripciones reales:

        declarados     884 pares nuevos    1,1% entre familias distintas
        adivinados   2.154 pares nuevos    8,7% entre familias distintas
        (referencia: los 24.774 vínculos ya aprobados a mano dan 0,8%)

    O sea que lo declarado nace casi tan limpio como lo que aprobó una persona, y lo adivinado
    nace ocho veces más sucio. El motivo se ve mirando las descripciones: en «SONDA LAMBDA
    80045 AUDI A3» el 80045 es el número interno de ESE proveedor, y los números internos de
    dos proveedores chocan entre sí sin tener nada que ver — el MAF 126 de uno es de un Renault
    y el del otro de un Mercedes. Cuando el proveedor escribe «REF ORIG» no estamos adivinando:
    nos lo están diciendo.

    Nada se carga: todo va a la cola de revisión, igual que el resto del descubrimiento."""
    c.execute("SELECT codigo_clean, id, marca_id FROM productos WHERE codigo_clean IS NOT NULL "
              "AND codigo_clean <> ''")
    por_codigo = {}
    for fila in c.fetchall():
        por_codigo.setdefault(fila["codigo_clean"], []).append((fila["id"], fila["marca_id"]))

    # Los pares que ya están resueltos o ya esperando. Sin esto se vuelve a proponer todas las
    # veces lo mismo, que es lo que hacía que la cola pareciera crecer sin que nadie cargara nada.
    ya = set()
    for _tabla in ("equivalencias", "equivalencias_pendientes"):
        try:
            c.execute(f"SELECT producto_a_id, producto_b_id FROM {_tabla}")
            for _a, _b in c.fetchall():
                ya.add((min(_a, _b), max(_a, _b)))
        except sqlite3.OperationalError as _err:
            anotar_error("equivalencias_escritas_en_las_descripciones", _err)

    conocidos = set(por_codigo)
    c.execute("SELECT id, codigo_raw, descripcion, marca_id FROM productos "
              "WHERE descripcion IS NOT NULL AND descripcion <> ''")
    filas = c.fetchall()
    pares, vistos, mirados = [], set(), 0
    for fila in filas:
        mirados += 1
        if progreso and mirados % 5000 == 0:
            progreso(mirados, len(filas))
        for candidato in extraer_codigos_de_texto(fila["descripcion"],
                                                  codigo_propio=fila["codigo_raw"],
                                                  codigos_conocidos=conocidos,
                                                  solo_declarados=True):
            for otro_id, otra_marca in por_codigo.get(sanitizar(candidato), ()):
                # Del mismo proveedor no: son dos productos de su propio catálogo.
                if otro_id == fila["id"] or otra_marca == fila["marca_id"]:
                    continue
                par = (min(fila["id"], otro_id), max(fila["id"], otro_id))
                if par in ya or par in vistos:
                    continue
                vistos.add(par)
                pares.append(par)
                if len(pares) >= limite:
                    return _sin_los_kits(pares)
    return _sin_los_kits(pares)


def _sin_los_kits(pares):
    """Saca los pares que son «un kit y la pieza que trae adentro».

    guardar_equivalencias_pendientes() ya los descarta al guardar, pero si no se sacan ACÁ la
    pantalla queda mintiendo: dice «8 pares nuevos», uno los manda a la cola, no entra ninguno,
    y a la corrida siguiente vuelven a salir los mismos 8 para siempre. Se vio probando el
    barrido dos veces seguidas."""
    if not pares:
        return pares
    try:
        _kits = pares_de_kit_y_pieza(pares)
    except Exception as _err:
        anotar_error("_sin_los_kits", _err)
        return pares
    return [p for p in pares if p not in _kits]


def contar_huerfanos():
    """Cuántos productos no tienen ninguna equivalencia. Es lo que borraría depurar_huerfanos().

    Existe para poder decir el número ANTES de borrar. Medido sobre el catálogo real: 25.143 de
    61.574, el 41%. Ver depurar_huerfanos() para por qué eso no es basura."""
    c.execute("""SELECT COUNT(*) FROM productos
                 WHERE id NOT IN (SELECT producto_a_id FROM equivalencias)
                   AND id NOT IN (SELECT producto_b_id FROM equivalencias)""")
    return c.fetchone()[0]


def contar_con_equivalencia_muerta():
    """Productos de proveedor cuyos vínculos van TODOS a un código que no cuelga nada más.

    Es el agujero entre dos pantallas que decían cosas distintas del mismo producto. El
    buscador ya avisa «este código todavía no tiene equivalencias con otra marca» cuando lo
    único que aparece es su código de fábrica; contar_huerfanos(), en cambio, los daba por
    resueltos porque en la tabla de equivalencias SÍ tienen una fila.
    En el catálogo real son 12.060 productos además de los 31.947 que no tienen ninguna: la
    diferencia entre «el 68% del catálogo no cruza con nadie» y «el 48%».

    No se suman a lo que borra depurar_huerfanos(), a propósito: estos NO son filas de más.
    Tienen su código de fábrica cargado y el día que otro proveedor traiga ese mismo número se
    encadenan solos. Lo que hace falta con ellos es otra lista, no borrarlos."""
    c.execute("""
        SELECT COUNT(*) FROM productos p
        JOIN marcas m ON m.id = p.marca_id
        WHERE m.tipo <> 'OEM'
          AND EXISTS (SELECT 1 FROM equivalencias e
                       WHERE e.producto_a_id = p.id OR e.producto_b_id = p.id)
          AND NOT EXISTS (
                SELECT 1 FROM equivalencias e
                JOIN productos po ON po.id = CASE WHEN e.producto_a_id = p.id
                                                  THEN e.producto_b_id ELSE e.producto_a_id END
                JOIN marcas mo ON mo.id = po.marca_id
                WHERE (e.producto_a_id = p.id OR e.producto_b_id = p.id)
                  -- un vecino sirve si es el producto de OTRO PROVEEDOR —ahí la equivalencia
                  -- ya está hecha, aunque ese vecino no tenga ningún otro vínculo— o si es un
                  -- código de fábrica que cuelga algo más que a mí.
                  AND (mo.tipo <> 'OEM'
                       OR (SELECT COUNT(*) FROM equivalencias e2
                            WHERE e2.producto_a_id = po.id OR e2.producto_b_id = po.id) > 1))
    """)
    fila = c.fetchone()
    return (fila[0] if fila else 0) or 0


def depurar_huerfanos():
    """Borra productos que no tienen ninguna equivalencia vinculada (quedaron sueltos).

    OJO con lo que esto significa de verdad. «Sin equivalencia» NO quiere decir «cargado por
    error»: quiere decir que todavía nadie lo cruzó con nada. En el catálogo real son 25.143
    productos de 61.574 —el 41%—, casi todos perfectamente vendibles, con su precio y su stock.
    Borrarlos es tirar cuatro de cada diez repuestos del mostrador.
    Por eso la pantalla muestra el número antes de preguntar, en vez de ofrecer «limpiar»."""
    with db_lock:
        c.execute("""
            DELETE FROM productos
            WHERE id NOT IN (SELECT DISTINCT producto_a_id FROM equivalencias)
              AND id NOT IN (SELECT DISTINCT producto_b_id FROM equivalencias)
        """)
        borrados = c.rowcount
        conn.commit()
    return borrados


def chequear_integridad_bd():
    """Revisa la base en busca de datos rotos o inconsistentes — sobre todo útil para detectar
    algo que se haya colado antes de que ciertas protecciones existieran, o algo que se rompió
    a mano editando la base fuera de la app."""
    resultados = []

    c.execute("""SELECT COUNT(*) FROM productos p
                 WHERE p.marca_id NOT IN (SELECT id FROM marcas)""")
    n = c.fetchone()[0]
    resultados.append({"Chequeo": "Productos con una marca que ya no existe", "Problemas": n})

    c.execute("""SELECT COUNT(*) FROM equivalencias e
                 WHERE e.producto_a_id NOT IN (SELECT id FROM productos)
                    OR e.producto_b_id NOT IN (SELECT id FROM productos)""")
    n = c.fetchone()[0]
    resultados.append({"Chequeo": "Equivalencias que apuntan a un producto que ya no existe", "Problemas": n})

    c.execute("""SELECT COUNT(*) FROM productos
                 WHERE codigo_raw IS NULL OR TRIM(codigo_raw) = ''
                    OR codigo_clean IS NULL OR TRIM(codigo_clean) = ''""")
    n = c.fetchone()[0]
    resultados.append({"Chequeo": "Productos con código vacío", "Problemas": n})

    c.execute("SELECT COUNT(*) FROM productos WHERE precio IS NOT NULL AND precio < 0")
    n = c.fetchone()[0]
    resultados.append({"Chequeo": "Productos con precio negativo", "Problemas": n})

    c.execute("SELECT COUNT(*) FROM productos WHERE stock IS NOT NULL AND stock < 0")
    n = c.fetchone()[0]
    resultados.append({"Chequeo": "Productos con stock negativo", "Problemas": n})

    c.execute("""SELECT codigo_clean, marca_id, COUNT(*) AS repetidos FROM productos
                 GROUP BY codigo_clean, marca_id HAVING COUNT(*) > 1""")
    duplicados = c.fetchall()
    resultados.append({"Chequeo": "Códigos duplicados dentro de la misma marca", "Problemas": len(duplicados)})

    c.execute("""SELECT COUNT(*) FROM vehiculos
                 WHERE km_registro IS NOT NULL AND km_actual IS NOT NULL AND km_actual < km_registro""")
    n = c.fetchone()[0]
    resultados.append({"Chequeo": "Vehículos con km actual menor al km de registro", "Problemas": n})

    c.execute("""SELECT COUNT(*) FROM historial_piezas h
                 WHERE h.vehiculo_id NOT IN (SELECT id FROM vehiculos)""")
    n = c.fetchone()[0]
    resultados.append({"Chequeo": "Piezas de historial que apuntan a un vehículo que ya no existe", "Problemas": n})

    return resultados


def listar_productos_sin_equivalencias(marca_filtro="Todas", limite=None):
    """Devuelve productos que no tienen ninguna equivalencia vinculada, sin borrarlos."""
    query = """
        SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
               m.nombre AS "Marca", m.tipo AS "Tipo"
        FROM productos p JOIN marcas m ON m.id = p.marca_id
        WHERE p.id NOT IN (SELECT DISTINCT producto_a_id FROM equivalencias)
          AND p.id NOT IN (SELECT DISTINCT producto_b_id FROM equivalencias)
    """
    params = []
    if marca_filtro and marca_filtro != "Todas":
        query += " AND UPPER(m.nombre) = ?"
        params.append(marca_filtro.upper())
    query += " ORDER BY m.nombre, p.codigo_raw LIMIT ?"
    params.append(limite if limite else -1)
    c.execute(query, params)
    return filas_a_listas(c)


def restaurar_backup(archivo_subido):
    """Reemplaza la base de datos actual por un archivo .db subido.

    Se restaura con la API backup() de SQLite y NO sobrescribiendo el archivo a mano, que es
    como estaba antes. La diferencia importa y se comprobó:

    La base anda en modo WAL, así que los cambios recientes viven en un archivo aparte
    (.db-wal) hasta que se consolidan. Cerrar la propia conexión solo borra ese archivo si es
    la ÚLTIMA conexión abierta — y esta app abre una por sesión justamente para que puedan
    usarla dos personas a la vez. Con alguien más adentro, el .db-wal sobrevive, y al pisar el
    .db con los bytes del backup ese WAL viejo se aplica encima de la base nueva: quedan
    mezcladas dos bases distintas. Probado con una segunda sesión que había escrito 500 filas:
    la restauración terminaba "bien" y el PRAGMA integrity_check devolvía
    «NUMERIC value in productos.ubicacion». Corrupción silenciosa, y del archivo entero.
    Borrar el .db-wal a mano tampoco sirve: la otra sesión lo tiene abierto y se cae con
    «disk I/O error».

    backup() escribe A TRAVÉS de SQLite, así que el WAL queda coherente, la otra sesión sigue
    funcionando y la base reabre sana. Es el mismo mecanismo que ya usaba
    _restaurar_desde_semilla(); acá faltaba."""
    contenido = archivo_subido.read()
    temporal = DB_PATH + ".subido"
    with open(temporal, "wb") as f:
        f.write(contenido)
    try:
        origen = sqlite3.connect(temporal)
        # Si lo que subieron no es una base de SQLite, esto falla ACÁ, antes de tocar nada.
        origen.execute("PRAGMA schema_version")
        with db_lock:
            conn.commit()
            # conexion_real() y no conn: backup() no acepta el proxy por sesión.
            origen.backup(conn.conexion_real())
            conn.commit()
            # Y las migraciones OTRA VEZ. El backup trae su propio esquema, que es el que tenía
            # la app el día que se hizo: si desde entonces se agregó una columna, al restaurar
            # desaparece y no vuelve hasta que alguien reinicie la app. Está probado: con un
            # backup anterior a la columna «resumen», la papelera se cae con «no such column:
            # resumen» apenas se abre. Y no es solo la papelera — «productos.busqueda» es la
            # columna en la que se apoya el buscador por texto.
            # crear_esquema() se puede correr las veces que haga falta: es CREATE TABLE IF NOT
            # EXISTS y ALTERs condicionados a que la columna no esté.
            crear_esquema(conn.cursor())
            conn.commit()
        origen.close()
    finally:
        try:
            os.remove(temporal)
        except OSError as _err:
            anotar_error("restaurar_backup", _err)
    # El caché de Streamlit puede tener guardados conteos y consultas de la base anterior.
    st.cache_data.clear()
    # Y el del esquema: la base que acaba de entrar puede tener otras columnas, que es
    # exactamente el caso que _columnas_de_medidas_que_existen() existe para cubrir.
    _columnas_de_medidas_que_existen.cache_clear()
    st.session_state.pop("_analisis_lote", None)



def subir_backup_a_github(datos_db, mensaje=""):
    """Sube la copia de la base al repositorio, que es lo único que sobrevive a un reinicio.

    Esta es la solución de fondo al problema que veníamos midiendo. Hasta ahora la app podía
    decirte «se perderían 180 productos», pero arreglarlo era un trámite manual: bajar el
    backup, entrar a GitHub, subirlo con el nombre exacto. Cuando algo depende de que una
    persona se acuerde de hacer un trámite, tarde o temprano no se hace.

    Necesita dos datos en los secretos de Streamlit (Settings → Secrets):
        github_token = "ghp_..."         (un token con permiso de escritura en el repo)
        github_repo  = "usuario/repo"

    Si no están configurados no hace nada y lo dice: no es obligatorio, es una mejora.
    Devuelve (ok, mensaje)."""
    cfg = config_github()
    if not cfg:
        return False, ("Falta configurar `github_token` y `github_repo` en los secretos de "
                       "Streamlit. Sin eso el backup hay que subirlo a mano.")
    ok, texto = _subir_backup_a_github(cfg, datos_db, mensaje)
    # Se anota el resultado, sea cual sea. La subida diaria corre sola en
    # tareas_automaticas_del_dia(), y ahí un fallo no lo veía nadie: la app seguía como si
    # la copia estuviera, y el aviso de «no hay copia» quedaba igual que siempre, sin decir
    # que se estaba intentando y fallando. Ver diagnostico_de_salud().
    guardar_config("ultimo_backup_github_error",
                   "" if ok else f"{datetime.now():%d/%m %H:%M} — {texto}")
    return ok, texto


def _sha_en_github(cfg, url, cabeceras):
    """El sha del archivo que ya está en el repositorio, o None si no existe todavía.

    GitHub lo exige para reemplazar un archivo, y pedirlo como se pedía no alcanza con una
    base de datos: la API de contenidos, con el tipo de respuesta de siempre, devuelve el
    archivo entero en base64 y solo hasta 1 MB. La copia pesa decenas. El tipo
    «application/vnd.github.object» devuelve los datos del archivo sin el contenido, y el sha
    viene igual. Si aun así no aparece, se lista la carpeta: cada entrada trae su sha."""
    try:
        r = requests.get(url, headers={**cabeceras, "Accept": "application/vnd.github.object"},
                         params={"ref": cfg["rama"]}, timeout=20)
        if r.status_code == 404:
            return None
        if r.status_code == 200 and r.json().get("sha"):
            return r.json()["sha"]
        carpeta, _, nombre = cfg["archivo"].rpartition("/")
        r = requests.get(f"{API_DE_GITHUB}/repos/{cfg['repo']}/contents/{carpeta}",
                         headers=cabeceras, params={"ref": cfg["rama"]}, timeout=20)
        if r.status_code == 200 and isinstance(r.json(), list):
            for entrada in r.json():
                if entrada.get("name") == nombre:
                    return entrada.get("sha")
    except Exception as _err:
        anotar_error("_sha_en_github", _err)
    return None


LEEME_DE_LA_RAMA_DE_COPIAS = """Esta rama la escribe sola la app: guarda la ultima copia de la base de datos.

Cada copia REEMPLAZA a la anterior (un solo commit), para que el repositorio no engorde.
La app la baja sola cuando arranca con el disco vacio. No hace falta tocar nada aca.
Para bajarla a mano: el archivo de esta rama, descomprimido con cualquier programa de .gz,
es una base SQLite que se abre con la app (Backup y config -> Restaurar).
"""


def _subir_a_la_rama_de_copias(cfg, datos, mensaje, cabeceras):
    """Sube la copia como el ÚNICO commit de la rama de copias, reemplazando al anterior.

    Es la API de datos de git en vez de la de archivos: la de archivos solo sabe agregar
    commits encima. Acá se arma un commit sin padres con el archivo y un LEEME, y la rama se
    mueve a ese commit a la fuerza. El commit viejo queda sin nadie que lo apunte y GitHub lo
    limpia solo. Devuelve (ok, código de respuesta, detalle)."""
    import base64
    base = f"{API_DE_GITHUB}/repos/{cfg['repo']}/git"
    r = requests.post(f"{base}/blobs", headers=cabeceras, timeout=120,
                      json={"content": base64.b64encode(datos).decode(), "encoding": "base64"})
    if r.status_code != 201:
        return False, r.status_code, r.text[:200]
    r = requests.post(f"{base}/trees", headers=cabeceras, timeout=30, json={"tree": [
        {"path": cfg["archivo"], "mode": "100644", "type": "blob", "sha": r.json()["sha"]},
        {"path": "LEEME.txt", "mode": "100644", "type": "blob",
         "content": LEEME_DE_LA_RAMA_DE_COPIAS},
    ]})
    if r.status_code != 201:
        return False, r.status_code, r.text[:200]
    r = requests.post(f"{base}/commits", headers=cabeceras, timeout=30,
                      json={"message": mensaje, "tree": r.json()["sha"], "parents": []})
    if r.status_code != 201:
        return False, r.status_code, r.text[:200]
    commit = r.json()["sha"]
    r = requests.patch(f"{base}/refs/heads/{cfg['rama']}", headers=cabeceras, timeout=30,
                       json={"sha": commit, "force": True})
    if r.status_code == 422:        # la rama todavía no existe: la primera copia la crea
        r = requests.post(f"{base}/refs", headers=cabeceras, timeout=30,
                          json={"ref": f"refs/heads/{cfg['rama']}", "sha": commit})
    return r.status_code in (200, 201), r.status_code, r.text[:200]


def _subir_backup_a_github(cfg, datos_db, mensaje):
    import base64
    url = f"{API_DE_GITHUB}/repos/{cfg['repo']}/contents/{cfg['archivo']}"
    cabeceras = {"Authorization": f"Bearer {cfg['token']}",
                 "Accept": "application/vnd.github+json"}
    try:
        # Comprimida si el nombre lo dice. Ver ARCHIVO_SEMILLA_COMPRIMIDA.
        contenido = gzip.compress(datos_db, 6) if cfg["archivo"].endswith(".gz") else datos_db
        mensaje = mensaje or f"Backup automático {datetime.now():%Y-%m-%d %H:%M}"
        if cfg["rama"] == RAMA_DE_LA_COPIA:
            ok, codigo, texto_gh = _subir_a_la_rama_de_copias(cfg, contenido, mensaje, cabeceras)
            if ok:
                guardar_config("ultimo_backup_github",
                               datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                marcar_backup_hecho()
                return True, (f"Copia subida a {cfg['repo']}, rama «{cfg['rama']}», "
                              f"como `{cfg['archivo']}`.")
            if codigo in (401, 403):
                return False, ("GitHub rechazó el token. Revisá que tenga permiso de escritura "
                               f"(Contents: read and write) sobre {cfg['repo']}. ({texto_gh})")
            if codigo == 404:
                return False, (f"GitHub no encuentra {cfg['repo']}. Revisá el nombre. Si el "
                               "repo es privado, el token tiene que tener acceso.")
            return False, f"GitHub respondió {codigo}. {texto_gh}"

        # GitHub exige el sha del archivo que se reemplaza; si no existe todavía, se crea
        sha = _sha_en_github(cfg, url, cabeceras)
        cuerpo = {
            "message": mensaje,
            "content": base64.b64encode(contenido).decode(),
            "branch": cfg["rama"],
        }
        if sha:
            cuerpo["sha"] = sha
        r = requests.put(url, headers=cabeceras, json=cuerpo, timeout=90)
        if r.status_code in (200, 201):
            guardar_config("ultimo_backup_github",
                           datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            marcar_backup_hecho()
            return True, f"Backup subido a {cfg['repo']} como `{cfg['archivo']}`."
        detalle = ""
        try:
            detalle = r.json().get("message", "")
        except Exception as _err:
            anotar_error("subir_backup_a_github", _err)
            pass
        if r.status_code in (401, 403):
            return False, ("GitHub rechazó el token. Revisá que tenga permiso de escritura "
                           f"sobre {cfg['repo']}. ({detalle})")
        if r.status_code == 404:
            return False, (f"GitHub no encuentra {cfg['repo']} o la rama «{cfg['rama']}». "
                           "Revisá el nombre. Si el repo es privado, el token tiene que "
                           "tener acceso.")
        return False, f"GitHub respondió {r.status_code}. {detalle}"
    except Exception as e:
        anotar_error("subir_backup_a_github", e)
        return False, f"No se pudo conectar con GitHub: {type(e).__name__}: {e}"


def cuanto_perderias_si_reinicia():
    """Qué se pierde si el servidor reinicia ahora mismo. Devuelve None si no aplica.

    Este es el riesgo más grande de todos y hasta ahora se contaba en abstracto: «bajate un
    backup». Pero un aviso genérico se ignora; un número no.

    Cómo funciona el mecanismo: el servidor borra el disco al reiniciar, y la app se restaura
    sola desde el archivo `datos_iniciales.db` que está en el repositorio. Ese archivo NO se
    actualiza solo — hay que bajar el backup y subirlo a GitHub a mano. Todo lo cargado desde
    la última vez que se hizo eso está viviendo únicamente en un disco que se borra."""
    try:
        c.execute("SELECT COUNT(*) FROM productos")
        ahora_total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM equivalencias")
        eq_total = c.fetchone()[0]
    except sqlite3.OperationalError as _err:
        anotar_error("cuanto_perderias_si_reinicia", _err)
        return None

    # Con la subida automática a la rama de copias andando, lo que se perdería es lo de los
    # últimos MINUTOS_ENTRE_COPIAS como mucho: vigilar_la_copia() sube cualquier cambio. La
    # copia de esa rama no está en el disco —la app la baja al arrancar—, así que mirar solo el
    # archivo del repositorio diría «no hay copia» teniendo una de hace diez minutos.
    _cfg_gh = config_github()
    _ultima_gh = obtener_config("ultimo_backup_github", "") if _cfg_gh else ""
    if _cfg_gh and _cfg_gh["rama"] == RAMA_DE_LA_COPIA and _ultima_gh:
        try:
            _fecha_gh = datetime.strptime(_ultima_gh, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
        except ValueError:
            _fecha_gh = _ultima_gh
        return {"hay_semilla": True, "en_github": True, "productos_ahora": ahora_total,
                "productos_semilla": ahora_total, "en_riesgo": 0, "equivalencias_en_riesgo": 0,
                "fecha_semilla": _fecha_gh}

    semilla = ruta_de_la_semilla()
    if not semilla:
        # Sin copia en el repositorio se pierde TODO, no cero. Devolver ceros acá escondía
        # justamente el caso más grave.
        return {"hay_semilla": False, "productos_ahora": ahora_total, "productos_semilla": 0,
                "en_riesgo": ahora_total, "equivalencias_en_riesgo": eq_total,
                "fecha_semilla": ""}
    try:
        c.execute("SELECT COUNT(*) FROM productos")
        ahora = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM equivalencias")
        eq_ahora = c.fetchone()[0]

        origen = sqlite3.connect(f"file:{semilla}?mode=ro", uri=True)
        cur = origen.cursor()
        cur.execute("SELECT COUNT(*) FROM productos")
        en_semilla = cur.fetchone()[0]
        try:
            cur.execute("SELECT COUNT(*) FROM equivalencias")
            eq_semilla = cur.fetchone()[0]
        except sqlite3.OperationalError as _err:
            anotar_error("cuanto_perderias_si_reinicia", _err)
            eq_semilla = 0
        origen.close()
    except Exception as _err:
        anotar_error("cuanto_perderias_si_reinicia", _err)
        return None

    return {
        "hay_semilla": True,
        "productos_ahora": ahora, "productos_semilla": en_semilla,
        "en_riesgo": max(ahora - en_semilla, 0),
        "equivalencias_en_riesgo": max(eq_ahora - eq_semilla, 0),
        "fecha_semilla": datetime.fromtimestamp(
            os.path.getmtime(semilla_del_repositorio())).strftime("%d/%m/%Y"),
    }


# ============================================================================================
# MANTENIMIENTO QUE CORRE SOLO AL ABRIR
# ============================================================================================
def tareas_automaticas_del_dia(presupuesto_segundos=6):
    """El mantenimiento que nadie tiene por qué acordarse de hacer.

    Todo lo que veníamos llamando «automático» corría solo cuando alguien abría esa pantalla en
    particular. Si nadie entra a Mantenimiento en dos semanas, los vínculos nuevos quedan sin
    puntuar y las fotos sin procesar. Esto lo hace solo, una vez por día, en la primera visita
    de cualquiera.

    Dos cosas la hacen segura:
      · Corre UNA vez por día. Queda anotado en la configuración, así que no se repite aunque
        entren veinte personas.
      · Tiene presupuesto de tiempo. Se revisa el reloj entre tarea y tarea y se corta al
        llegar al límite: lo que quedó pendiente se hace mañana. Nadie va a esperar diez
        segundos por un mantenimiento que no pidió.
    """
    hoy = datetime.now().strftime("%Y-%m-%d")
    if obtener_config("ultimas_tareas_dia", "") == hoy:
        return None

    arranque = time.time()
    hecho = []

    def queda_tiempo():
        return time.time() - arranque < presupuesto_segundos

    # 1. Puntuar los vínculos que quedaron sin nota: es lo que usa el buscador
    if queda_tiempo():
        try:
            c.execute("SELECT COUNT(*) FROM equivalencias WHERE confianza IS NULL")
            if c.fetchone()[0]:
                n = recalcular_confianzas(limite=3000)
                if n:
                    hecho.append(f"{n:,} vínculo(s) puntuados")
        except Exception as _err:
            anotar_error("tareas_automaticas_del_dia", _err)
            pass

    # 2. Procesar fotos pendientes, de a poco
    if queda_tiempo():
        try:
            r = migrar_imagenes_pendientes(limite=20)
            if r.get("listas"):
                hecho.append(f"{r['listas']} foto(s) procesadas")
        except Exception as _err:
            anotar_error("tareas_automaticas_del_dia", _err)
            pass

    # 2b. Liberar las reservas viejas. Antes solo pasaba cuando alguien abría esa pantalla:
    # un presupuesto de hace un mes podía seguir bloqueando mercadería para siempre.
    if queda_tiempo():
        try:
            n_venc = vencer_reservas_viejas()
            if n_venc:
                hecho.append(f"{n_venc} reserva(s) vencida(s) liberadas")
        except Exception as _err:
            anotar_error("tareas/reservas_vencidas", _err)

    # 2c. Las equivalencias que salen de los reemplazos de código ya cargados. No hay nada que
    # investigar: el dato ya está, solo faltaba cruzarlo.
    if queda_tiempo():
        try:
            puenteadas = equivalencias_puenteadas_por_reemplazo(100)
            if puenteadas:
                n_p = guardar_equivalencias_derivadas(
                    [(x["_a"], x["_b"]) for x in puenteadas],
                    f"POR REEMPLAZO (automático) · {datetime.now():%d/%m}")
                if n_p:
                    hecho.append(f"{n_p} equivalencia(s) por cambio de código, a revisión")
        except Exception as _err:
            anotar_error("tareas/puenteadas", _err)

    # 3. Aprender modelos y motores de las fichas de vehículo cargadas
    if queda_tiempo():
        try:
            n_mod, n_mot = aprender_modelos_de_fichas_existentes()
            if n_mod or n_mot:
                hecho.append(f"{n_mod} modelo(s) y {n_mot} motor(es) de VIN aprendidos")
        except Exception as _err:
            anotar_error("tareas_automaticas_del_dia", _err)
            pass

    # 4. Las equivalencias que el mostrador ya confirmó: si vendiste el mismo reemplazo varias
    # veces, no tiene sentido esperar a que alguien entre a Mantenimiento a descubrirlo.
    if queda_tiempo():
        try:
            nuevas = [x for x in sustituciones_reales() if not x["_ya"]]
            if nuevas:
                n = guardar_equivalencias_derivadas(
                    [(x["_a"], x["_b"]) for x in nuevas],
                    f"CONFIRMADAS EN EL MOSTRADOR · {hoy}")
                if n:
                    hecho.append(f"{n} equivalencia(s) confirmadas por venta, a revisión")
        except Exception as _err:
            anotar_error("tareas_automaticas_del_dia", _err)
            pass

    # 5. Las fotos y las equivalencias de las fichas del proveedor YA NO VAN ACÁ.
    # Estaban como dos tandas de 15 por día, y 15 por día es trece años para 70.888 productos.
    # No se podían agrandar porque esto corre DENTRO del dibujo de la pantalla, con 6 segundos
    # de presupuesto: agrandar la tanda era hacer esperar a alguien que entró a buscar un
    # repuesto. Ahora van en un hilo aparte, donde nadie espera y el tamaño lo elige el usuario.
    # Ver arrancar_tanda_de_fondo().

    # 6. La copia a GitHub ya no va acá: ver vigilar_la_copia().

    guardar_config("ultimas_tareas_dia", hoy)
    guardar_config("ultimas_tareas_detalle", " · ".join(hecho) if hecho else "nada pendiente")
    return hecho


def informe_post_importacion(lote, nombre_prov, cargados):
    """Qué pasó realmente con la lista que se acaba de importar, sin salir a buscarlo.

    Hasta ahora la app decía «se importaron 6.900 filas» y ahí terminaba. Los problemas —los
    vínculos malos, los precios raros, los productos que el proveedor dejó de mandar— había que
    salir a buscarlos por Mantenimiento, y en la práctica nadie lo hace hasta que algo falla en
    el mostrador.

    Esto corre los mismos controles que ya existen, pero acotados a lo que ACABA de entrar, y
    junta el resultado en un solo lugar mientras uno todavía tiene la lista fresca."""
    informe = {"puntos": [], "vinculos_nuevos": 0, "rojos": 0, "pedidos_que_entraron": []}

    # Lo que te pidieron sin resultado y trajo ESTA lista. Va en el informe porque es el
    # momento: la persona está mirando qué entró. Después, se entera solo si va a buscarlo.
    try:
        c.execute("SELECT id FROM marcas WHERE UPPER(nombre) = UPPER(?)", (nombre_prov,))
        _fila_m = c.fetchone()
        if _fila_m:
            informe["pedidos_que_entraron"] = busquedas_fallidas_que_ahora_estan(_fila_m["id"])
    except Exception as _err:
        anotar_error("informe_post_importacion/pedidos", _err)

    try:
        c.execute("SELECT COUNT(*) FROM equivalencias_pendientes WHERE lote = ?", (lote,))
        pendientes = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM equivalencias WHERE lote = ?", (lote,))
        cargadas = c.fetchone()[0]
        informe["vinculos_nuevos"] = pendientes + cargadas
        # Separadas a propósito: no es lo mismo un vínculo cargado que uno esperando aprobación.
        # Sumarlos y decir "entraron" es mentir justo donde más caro sale creerlo.
        informe["cargadas"] = cargadas
        informe["pendientes"] = pendientes
    except sqlite3.OperationalError as _err:
        anotar_error("informe_post_importacion", _err)
        pendientes = cargadas = 0

    # Los vínculos que entraron, evaluados con el mismo análisis de siempre
    if pendientes:
        try:
            # Todos, no los primeros 600: el número sale a pantalla como «N de los 3.185
            # vínculos nuevos están casi seguro mal», y contarlo sobre una parte es dar un
            # número que no es. Los 3.185 de la lista de Illinois tardan 6,6 s.
            limpias, sospechosas, _relacionadas = analizar_lote_pendiente(lote, limite=None)
            rojos = [x for x in (limpias + sospechosas) if x.get("confianza", 50) < 30]
            informe["rojos"] = len(rojos)
            if rojos:
                informe["puntos"].append((
                    "alto",
                    f"{len(rojos)} de los {pendientes} vínculos nuevos están «casi seguro mal»",
                    "Se pueden descartar todos juntos, sin mirarlos de a uno.",
                    "Estadísticas → 🔗 Equivalencias sugeridas",
                ))
        except Exception as _err:
            anotar_error("informe_post_importacion", _err)
            pass

    # Códigos que no parecen códigos y entraron igual
    try:
        c.execute("""SELECT COUNT(*) FROM productos p JOIN marcas m ON m.id = p.marca_id
                     WHERE UPPER(m.nombre) = UPPER(?) AND LENGTH(p.codigo_clean) <= 3""",
                  (nombre_prov,))
        cortos = c.fetchone()[0]
        if cortos:
            informe["puntos"].append((
                "medio", f"{cortos} código(s) de 3 caracteres o menos en {nombre_prov.upper()}",
                "Suelen ser cantidades o números de orden que se colaron en la columna del código.",
                "Administrar → Mantenimiento → 🧹 Limpiar vínculos",
            ))
    except sqlite3.OperationalError as _err:
        anotar_error("informe_post_importacion", _err)
        pass

    # Productos de esta marca que dejaron de venir en las últimas listas
    try:
        c.execute("SELECT id FROM marcas WHERE UPPER(nombre) = UPPER(?)", (nombre_prov,))
        fila_marca = c.fetchone()
        if fila_marca:
            discont, _ = productos_probablemente_discontinuados(marca_id=fila_marca["id"])
            con_stock = [x for x in discont if (x.get("_stock") or 0) > 0]
            if con_stock:
                informe["puntos"].append((
                    "medio",
                    f"{len(con_stock)} producto(s) con stock no vinieron en esta lista",
                    "Si el proveedor dejó de mandarlos, es mercadería que conviene liquidar.",
                    "Estadísticas → Reposición → Puede que ya no se fabriquen",
                ))
    except Exception as _err:
        anotar_error("informe_post_importacion", _err)
        pass

    return informe


# Cuánto se le deja gastar al descubrimiento que corre solo después de importar. Es mucho más
# que el presupuesto de las tareas del día (6 s) a propósito: las tareas del día caen sobre
# alguien que abrió la app a buscar un repuesto y no pidió nada, y esto cae sobre alguien que
# acaba de subir una planilla de 26.000 filas y está mirando una barra de progreso.
PRESUPUESTO_DESCUBRIMIENTO = 120


def descubrimiento_post_importacion(presupuesto_segundos=PRESUPUESTO_DESCUBRIMIENTO):
    """Busca sola las relaciones nuevas que hasta ahora había que ir a pedir a mano.

    Este es el agujero más grande que quedaba: el trabajo que ENCUENTRA equivalencias
    —el barrido de todo el catálogo, las aplicaciones deducidas de las descripciones, el cruce
    por auto— existía y andaba, pero solo corría si alguien entraba a Estadísticas →
    Mantenimiento y apretaba el botón. Desde el mostrador nadie entra ahí. Así que en la
    práctica se importaba una lista, la app decía «entraron 6.900 filas», y las 8.661 relaciones
    que esas filas hacían posibles se quedaban sin buscar para siempre.

    Corre DESPUÉS de importar y no una vez por día por dos razones: es el único momento en que
    hay algo nuevo que encontrar, y es el único momento en que la persona ya está esperando.

    El orden no es casual, va de lo que enriquece a lo que consume:
      1. Las medidas escritas en la descripción. Primero porque es lo más barato y porque SACA
         vínculos falsos: con la medida cargada, todo lo que viene después tiene la prueba
         física para vetar.
      2. La marca del repuesto —quién fabrica la pieza—, que es el paso más barato de todos.
      3. Los códigos de fábrica que el proveedor ESCRIBIÓ en la descripción. Barato y limpio:
         si se acaba el presupuesto, que no sea este el que se pierda.
      4. Las aplicaciones que salen de las descripciones. Es dato nuevo sobre cada producto.
      5. Los motores que van juntos. Tiene que ir ANTES de los dos pasos que puntúan, porque
         el veto por motor lee esa tabla para decidir.
      6. El cruce por auto, que USA esas aplicaciones: si va antes, cruza con menos.
      7. El barrido de todo el catálogo, que es el más caro y el que más produce.

    Los pasos 2 y 5 llegaron tarde y por el mismo motivo: los dos vivían solo en el hilo de
    fondo, atados a una bandera de migración que se apaga una vez. Lo que entraba en la
    importación siguiente no los veía nunca.

    Medido sobre la base real (70.888 productos, cinco listas): 3 s las medidas, 2,6 s la marca
    del repuesto, 4 s los códigos escritos, 32 s + 17 s las aplicaciones, 0,6 s los motores,
    22 s el cruce por auto, 23 s el barrido. La tanda entera, cronometrada de punta a punta,
    tarda 86 s.

    Nada se carga como equivalencia: todo va a la cola de pendientes, igual que cuando se
    apretaba el botón a mano. Lo único que cambia es que ahora se busca.

    Si se acaba el presupuesto, lo que quedó se dice y se hace en la próxima importación — los
    pasos son independientes y ninguno pierde trabajo por cortarse antes de empezar.

    Devuelve (frases_de_lo_que_hizo, lo_que_quedó_sin_hacer)."""
    arranque = time.time()
    hecho, quedo = [], []

    def queda_tiempo():
        return time.time() - arranque < presupuesto_segundos

    # Las medidas que ya están escritas en la descripción. Va primero de todo porque es lo más
    # barato (2,7 s sobre 70.888 productos) y porque SACA vínculos falsos en vez de agregar:
    # con las medidas cargadas, los pasos siguientes ya cuentan con la prueba física.
    # Antes esto era un botón en Mantenimiento que había que saber apretar, y el resultado es
    # que sobre la base real había 0 medidas cargadas y 1.402 productos que las tenían escritas.
    if queda_tiempo():
        try:
            _completados = 0
            while queda_tiempo():
                _pend_med = productos_con_medidas_deducibles(limite=2000)
                if not _pend_med:
                    break
                _aplic = aplicar_medidas_deducidas(_pend_med)
                _completados += _aplic
                if not _aplic:
                    break      # ver el mismo caso en _trabajo_de_fondo()
            if _completados:
                hecho.append(f"{_completados:,} producto(s) con las medidas leídas de su "
                             "descripción")
        except Exception as _err:
            anotar_error("descubrimiento_post_importacion/medidas", _err)
    else:
        quedo.append("las medidas escritas en las descripciones")

    # QUIÉN FABRICA LA PIEZA, leída del final de la descripción. Es el paso más barato de todos
    # —una expresión regular por descripción, sin una sola consulta de por medio— y estaba
    # faltando acá por un motivo que no se ve mirando el código de a un pedazo:
    # completar_marcas_de_repuesto() solo corría en el hilo de fondo, atado a la bandera que
    # levanta la migración de VERSION_MARCAS_REPUESTO. Esa bandera se apaga una vez y no se
    # vuelve a prender. O sea que los productos que entran DESPUÉS —que son justamente los de
    # cada lista nueva— se quedaban con la columna vacía para siempre, y la columna
    # «Fabricante» del buscador aparecía en blanco para todo lo recién importado.
    # Solo toca los que están vacíos, así que correrlo de nuevo no pisa nada corregido a mano.
    if queda_tiempo():
        try:
            _n_mr = completar_marcas_de_repuesto()
            if _n_mr:
                guardar_config("marcas_repuesto_puestas", str(_n_mr))
                guardar_config("marcas_repuesto_fecha",
                               datetime.now().strftime("%Y-%m-%d %H:%M"))
                hecho.append(f"{_n_mr:,} producto(s) con la marca del repuesto leída de su "
                             "descripción")
        except Exception as _err:
            anotar_error("descubrimiento_post_importacion/marcas_repuesto", _err)
    else:
        quedo.append("la marca del repuesto")

    if queda_tiempo():
        try:
            _escritos = equivalencias_escritas_en_las_descripciones()
            if _escritos:
                _n = guardar_equivalencias_pendientes(
                    list(_escritos), "descripcion-declarada",
                    f"CÓDIGO ESCRITO EN LA DESCRIPCIÓN (automático) · {datetime.now():%d/%m %H:%M}")
                if _n:
                    hecho.append(f"{_n} par(es) de códigos que el proveedor escribió "
                                 "en la descripción, a revisión")
        except Exception as _err:
            anotar_error("descubrimiento_post_importacion/codigos_escritos", _err)
    else:
        quedo.append("los códigos de fábrica escritos en las descripciones")

    if queda_tiempo():
        try:
            _apl = aplicaciones_desde_descripciones()
            if _apl:
                _n = aplicar_aplicaciones_deducidas(_apl)
                if _n:
                    hecho.append(f"{_n:,} aplicación(es) deducidas de las descripciones")
        except Exception as _err:
            anotar_error("descubrimiento_post_importacion/aplicaciones", _err)
    else:
        quedo.append("las aplicaciones deducidas de las descripciones")

    # QUÉ MOTORES SE LLEVAN ENTRE SÍ. Va ACÁ, y el lugar importa: los dos pasos que siguen
    # —el cruce por auto y el barrido— puntúan con evaluar_equivalencia(), y el veto por motor
    # lee esta tabla. Aprenderlos después sería vetar pares que la lista recién importada acaba
    # de demostrar compatibles, y esos pares no vuelven: quedan descartados hasta la próxima
    # importación.
    # Mismo agujero que la marca del repuesto —solo se aprendía en el hilo de fondo, colgado de
    # la bandera de aplicaciones—, así que las descripciones nuevas no enseñaban nada.
    # Devuelve el TOTAL de pares que sabe, no los que agregó: la tabla se reescribe entera.
    if queda_tiempo():
        try:
            _n_mot = aprender_motores_que_van_juntos()
            if _n_mot:
                hecho.append(f"{_n_mot:,} par(es) de motores que el catálogo declara "
                             "compatibles, al día")
        except Exception as _err:
            anotar_error("descubrimiento_post_importacion/motores", _err)
    else:
        quedo.append("los motores que van juntos")

    if queda_tiempo():
        try:
            _der = derivar_equivalencias_de_aplicaciones()
            if _der:
                _n = guardar_equivalencias_derivadas(
                    [(x["_a"], x["_b"]) for x in _der],
                    f"CRUCE POR AUTO (automático) · {datetime.now():%d/%m %H:%M}")
                if _n:
                    hecho.append(f"{_n} equivalencia(s) por auto, a revisión")
        except Exception as _err:
            anotar_error("descubrimiento_post_importacion/por_auto", _err)
    else:
        quedo.append("el cruce por auto")

    if queda_tiempo():
        try:
            _todas = sugerir_entre_todas_las_marcas()
            if _todas:
                _n = guardar_equivalencias_pendientes(
                    [(x["_a"], x["_b"]) for x in _todas], "descripcion-todas",
                    f"BARRIDO (automático) · {datetime.now():%d/%m %H:%M}")
                if _n:
                    hecho.append(f"{_n} par(es) del barrido de todo el catálogo, a revisión")
        except Exception as _err:
            anotar_error("descubrimiento_post_importacion/barrido", _err)
    else:
        quedo.append("el barrido de todo el catálogo")

    # 4. Revisar los vínculos que YA están cargados. Es el único control que mira lo que la
    # búsqueda está devolviendo AHORA: los demás miran lo que todavía no entró. Acá se mide
    # nada más —cortar un vínculo es destructivo y lo decide una persona—, pero medirlo solo
    # es lo que hacía falta: hasta ahora había que apretar un botón para enterarse de que la
    # búsqueda venía devolviendo un resultado equivocado.
    if queda_tiempo():
        try:
            _dudosas, _revisadas = auditar_equivalencias_cargadas()
            guardar_config("dudosos_cargados", str(len(_dudosas)))
            guardar_config("dudosos_revisados", str(_revisadas))
            guardar_config("dudosos_fecha", datetime.now().strftime("%Y-%m-%d %H:%M"))
            if _dudosas:
                hecho.append(f"{len(_dudosas)} vínculo(s) ya cargados quedaron marcados como "
                             f"dudosos")
        except Exception as _err:
            anotar_error("descubrimiento_post_importacion/dudosos", _err)
    else:
        quedo.append("la revisión de los vínculos ya cargados")

    if hecho:
        invalidar_salud()
    return hecho, quedo


DIAS_VENCIMIENTO_RESERVA = 7


def vencer_reservas_viejas():
    """Libera las reservas que quedaron colgadas. Devuelve cuántas."""
    with db_lock:
        c.execute("""UPDATE reservas_stock SET estado = 'vencida'
                     WHERE estado = 'activa'
                       AND fecha < datetime('now', ?)""",
                  (f"-{DIAS_VENCIMIENTO_RESERVA} days",))
        n = c.rowcount
        conn.commit()
    return n

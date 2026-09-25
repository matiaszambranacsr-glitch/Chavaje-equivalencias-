"""Sustitución por medidas, comparación visual, fotos, auditoría de stock y ubicación en depósito.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================
# SUSTITUCIÓN POR MEDIDAS MECÁNICAS (retenes, o'rings, bujes)
# ============================================================
def buscar_por_medidas(diam_int=None, diam_ext=None, ancho=None, paso_rosca=None, estrias=None, tolerancia_pct=5,
                        estrias_internas=None, estrias_externas=None, posicion_seguro=None, tiene_abs="Cualquiera",
                        diam_int_cara_b=None, diam_ext_cara_b=None,
                        diam_rosca_homocinetica=None, diam_copa=None,
                        diam_copa_superior=None, largo_total=None):
    condiciones = []
    params = []

    def rango(valor, campo):
        if valor:
            tol = valor * tolerancia_pct / 100.0
            condiciones.append(f"p.{campo} BETWEEN ? AND ?")
            params.extend([valor - tol, valor + tol])

    rango(diam_int, "diametro_interno")
    rango(diam_ext, "diametro_externo")
    rango(diam_int_cara_b, "diametro_interno_cara_b")
    rango(diam_ext_cara_b, "diametro_externo_cara_b")
    rango(diam_rosca_homocinetica, "diametro_rosca_homocinetica")
    rango(diam_copa, "diametro_copa")
    rango(diam_copa_superior, "diametro_copa_superior")
    rango(largo_total, "largo_total")
    rango(ancho, "ancho")
    if paso_rosca:
        condiciones.append("UPPER(p.paso_rosca) = ?")
        params.append(paso_rosca.strip().upper())
    if estrias:
        condiciones.append("p.cantidad_estrias = ?")
        params.append(estrias)
    if estrias_internas:
        condiciones.append("p.estrias_internas = ?")
        params.append(estrias_internas)
    if estrias_externas:
        condiciones.append("p.estrias_externas = ?")
        params.append(estrias_externas)
    if posicion_seguro:
        condiciones.append("UPPER(p.posicion_seguro) = ?")
        params.append(posicion_seguro.strip().upper())
    if tiene_abs != "Cualquiera":
        condiciones.append("p.tiene_abs = ?")
        params.append(1 if tiene_abs == "Sí" else 0)

    if not condiciones:
        return []

    query = f"""SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion", m.nombre AS "Marca",
                p.diametro_interno AS "Diám. interno (cara A)", p.diametro_interno_cara_b AS "Diám. interno (cara B)",
                p.diametro_externo AS "Diám. externo (cara A)", p.diametro_externo_cara_b AS "Diám. externo (cara B)",
                p.diametro_rosca_homocinetica AS "Diám. rosca homocinética",
                p.diametro_copa AS "Diám. copa (base)",
                p.diametro_copa_superior AS "Diám. copa (boca)",
                p.largo_total AS "Largo total",
                p.ancho AS "Ancho",
                p.paso_rosca AS "Paso de rosca", p.cantidad_estrias AS "Estrías",
                p.estrias_internas AS "Estrías internas", p.estrias_externas AS "Estrías externas",
                p.posicion_seguro AS "Posición del seguro",
                CASE WHEN p.tiene_abs = 1 THEN 'Sí' WHEN p.tiene_abs = 0 THEN 'No' ELSE '' END AS "ABS",
                p.precio AS "Precio", p.stock AS "Stock"
                FROM productos p JOIN marcas m ON m.id = p.marca_id
                WHERE {" AND ".join(condiciones)} ORDER BY m.nombre LIMIT 100"""
    c.execute(query, params)
    return filas_a_listas(c)


def medidas_desde_descripcion(descripcion):
    """Lee las medidas que la descripción ya trae escritas. Devuelve solo lo que es SEGURO.

    En retenes, rulemanes, bujes y o\'rings la medida ES el código: el proveedor escribe
    «RETEN 35X52X7» y ahí están el diámetro interno, el externo y el ancho. Esos datos ya están
    cargados en la base, en el campo descripción, y hasta ahora había que volver a tipearlos a
    mano uno por uno para que sirvieran de algo.

    Sirven para algo importante: comparar_medidas() usa las medidas como prueba física. Si dos
    piezas miden distinto, el vínculo se veta por más que una lista diga que equivalen. O sea que
    llenar esto no agrega equivalencias — saca las falsas.

    Es deliberadamente CONSERVADOR. Solo se leen las formas que no tienen otra lectura posible:

      · tres números seguidos (35x52x7) -> interno, externo, ancho. Se exige interno < externo,
        que es como está construida cualquier pieza de estas; si no se cumple, no se lee nada,
        porque entonces esos números son otra cosa.
      · «22 ESTRIAS» -> cantidad de estrías.
      · «M24 X 1.5» -> diámetro y paso de rosca.

    DOS números sueltos (20x2.5) NO se leen: en un o\'ring eso es diámetro por espesor del cordón,
    no interno por externo, y cargarlo como interno/externo sería meter un dato falso en el lugar
    donde el sistema toma decisiones. Mejor no saber que saber mal."""
    if not descripcion:
        return {}
    texto = str(descripcion).upper().replace(",", ".")
    medidas = {}

    tres = re.search(r"(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*[X×]\s*(\d{1,3}(?:\.\d+)?)"
                     r"\s*[X×]\s*(\d{1,3}(?:\.\d+)?)(?![\d.])", texto)
    if tres:
        interno, externo, ancho = (float(tres.group(i)) for i in (1, 2, 3))
        # Cordura: una pieza real tiene el interno menor que el externo, y ninguna de estas
        # medidas pasa de 500 mm. Si no cierra, son números de otra cosa (un año, una potencia).
        if 0 < interno < externo <= 500 and 0 < ancho <= 500:
            medidas["diametro_interno"] = interno
            medidas["diametro_externo"] = externo
            medidas["ancho"] = ancho

    estrias = re.search(r"(\d{1,3})\s*ESTR[ÍI]AS?", texto)
    if estrias and 0 < int(estrias.group(1)) <= 60:
        medidas["cantidad_estrias"] = int(estrias.group(1))

    rosca = re.search(r"\bM\s?(\d{1,3}(?:\.\d+)?)\s*[X×]\s*(\d{1,2}(?:\.\d+)?)\b", texto)
    if rosca:
        diametro, paso = float(rosca.group(1)), rosca.group(2)
        if 0 < diametro <= 100:
            medidas["diametro_rosca_homocinetica"] = diametro
            medidas["paso_rosca"] = paso

    # EL ESPESOR DE LA JUNTA. Es de los datos más caros de errar que hay en el mostrador y
    # estaba escrito en la descripción sin que lo leyera nadie. Una junta de tapa de cilindros
    # de 1,50 mm y una de 1,70 son piezas distintas —cambian la relación de compresión— y para
    # todas las reglas de texto de la app son casi la misma fila:
    #     Junta Tapa de Cilindros ISUZU (ESP 1.50MM) TROOPER ...
    #     Junta Tapa de Cilindros ISUZU (ESP 1.60MM) TROOPER ...
    #     Junta Tapa de Cilindros ISUZU (ESP 1.70MM) TROOPER ...
    # Medido sobre la base real: 630 productos lo traen escrito, y hay 32 vínculos esperando
    # revisión que unen juntas de espesor distinto — uno de ellos propone el mismo código de
    # fábrica para 0,2 / 0,3 / 0,5 y 0,8 mm a la vez.
    # Se pide la palabra ESP y la unidad MM pegadas al número: así no se confunde con la
    # abreviatura «Esp.» de «especial», que aparece suelta y sin número.
    espesor = re.search(r"\bESP\.?\s*:?\s*(\d{1,2}(?:\.\d{1,2})?)\s*MM\b", texto)
    if espesor:
        valor = float(espesor.group(1))
        # Los 630 de la base van de 0,2 a 3 mm. El tope deja lugar de sobra sin dejar entrar
        # un número que sea otra cosa.
        if 0.05 <= valor <= 20:
            medidas["espesor"] = valor

    # LAS VÍAS DE LA FICHA. Mismo caso: un sensor de 2 polos y uno de 3 no son intercambiables,
    # y la descripción lo dice. En la base hay 483 productos que lo escriben y dos vínculos YA
    # CARGADOS que unen un sensor de rotación de 3 polos con uno de 2 —misma marca, mismo auto,
    # misma resistencia— que hoy el buscador ofrece como equivalentes.
    vias = re.search(r"\b(\d{1,2})\s*(?:VIAS|VÍAS|POLOS|PINES)\b", texto)
    if vias:
        cuantas = int(vias.group(1))
        if 1 <= cuantas <= 40:
            medidas["cantidad_vias"] = cuantas

    # LAS MEDIDAS ESCRITAS CON PALABRAS. Las listas de poleas y alternadores no escriben
    # «35x52x7»: escriben «Diametro interno 17mm - Diametro Externo 54 5mm - Cantidad de
    # canales 6». El lector de acá arriba solo entiende la forma corta, así que sobre la base
    # real esos 523 productos tenían las tres columnas vacías teniendo la medida a la vista.
    #
    # El «54 5mm» es 54,5: la importación se comió el separador decimal y dejó un espacio. Por
    # eso el decimal acepta coma, punto o espacio — pegado al «mm», que es lo que lo hace
    # seguro: sin esa ancla, cualquier «54 5» suelto de la descripción entraría como medida.
    for _campo, _etiqueta in (("diametro_interno", r"DI[AÁ]METRO\s+INTERNO"),
                              ("diametro_externo", r"DI[AÁ]METRO\s+EXTERNO"),
                              ("ancho", r"ANCHO")):
        if _campo in medidas:
            continue      # la forma corta manda: es la que trae la pieza medida de verdad
        _m = re.search(_etiqueta + r"\s+(\d{1,3})(?:[.,\s](\d{1,2}))?\s*MM",
                       texto, re.IGNORECASE)
        if _m:
            _valor = float(_m.group(1) + ("." + _m.group(2) if _m.group(2) else ""))
            if 0 < _valor < 500:
                medidas[_campo] = _valor

    # Los canales de una polea. Se pide «CANTIDAD DE CANALES N» con el número DETRÁS: en esta
    # misma lista hay «Polea de 4 canales 96 >», donde el número que sigue es un año, y tomando
    # el de atrás quedaba una polea de 96 canales.
    _canales = re.search(r"CANTIDAD\s+DE\s+CANALES\s+(\d{1,2})", texto, re.IGNORECASE)
    if _canales:
        _cuantos = int(_canales.group(1))
        if 1 <= _cuantos <= 20:
            medidas["cantidad_canales"] = _cuantos

    # Dónde va la pieza. Se lee de la descripción sin tocar, no del texto normalizado, porque
    # las abreviaturas dependen del punto y del guion: «DEL.» y «DEL-IZQ» se distinguen de la
    # preposición «del» justamente por eso.
    donde = posicion_desde_descripcion(descripcion)
    if donde:
        medidas["posicion"] = donde

    return medidas


# Cómo se nombra cada medida en la tabla de «qué se podría completar». Lo que no esté acá se
# muestra con el nombre de la columna. Ver productos_con_medidas_deducibles().
ETIQUETAS_DE_MEDIDA = {
    "diametro_interno": "int", "diametro_externo": "ext", "ancho": "ancho",
    "cantidad_estrias": "estrías", "diametro_rosca_homocinetica": "rosca",
    "paso_rosca": "paso", "espesor": "espesor", "cantidad_vias": "vías",
    "cantidad_canales": "canales", "posicion": "posición",
}


def productos_con_medidas_deducibles(limite=500):
    """Productos a los que se les puede leer la medida de la descripción y que todavía la tienen
    vacía. Nunca toca lo cargado a mano: si alguien ya midió la pieza, ese dato manda."""
    try:
        c.execute("""SELECT p.id AS "_id", p.codigo_raw AS "Código", m.nombre AS "Marca",
                            p.descripcion AS "Descripción",
                            p.diametro_interno, p.diametro_externo, p.ancho,
                            p.cantidad_estrias, p.diametro_rosca_homocinetica, p.paso_rosca,
                            p.espesor, p.cantidad_vias, p.cantidad_canales, p.posicion
                     FROM productos p JOIN marcas m ON m.id = p.marca_id
                     WHERE p.descripcion IS NOT NULL AND p.descripcion <> ''
                       AND (p.diametro_interno IS NULL OR p.diametro_externo IS NULL
                            OR p.ancho IS NULL OR p.cantidad_estrias IS NULL
                            OR p.espesor IS NULL OR p.cantidad_vias IS NULL
                            OR p.cantidad_canales IS NULL OR p.posicion IS NULL)""")
        filas = filas_a_listas(c)
    except sqlite3.OperationalError as _err:
        anotar_error("productos_con_medidas_deducibles", _err)
        return []

    salida = []
    for f in filas:
        ceder_al_mostrador()
        leidas = medidas_desde_descripcion(f["Descripción"])
        # Solo lo que está VACÍO hoy. Lo cargado a mano no se pisa nunca.
        nuevas = {k: v for k, v in leidas.items() if f.get(k) in (None, "")}
        if not nuevas:
            continue
        # Se recorre `nuevas` y no una lista escrita acá adentro, y el cambio salió de un
        # agujero real: la lista tenía ocho campos y medidas_desde_descripcion() ya devuelve
        # diez —se le sumaron `cantidad_canales` y `posicion`—, así que un producto al que solo
        # se le leía la posición aparecía en la tabla con «Se completaría» VACÍO. Y esa tabla es
        # lo único que la persona mira antes de apretar «Completar esas medidas»: se le estaba
        # pidiendo que aprobara un cambio que la pantalla no le mostraba.
        # El nombre de la columna como respaldo es a propósito: si mañana se lee un campo nuevo
        # y nadie le pone etiqueta, se verá feo, pero se verá.
        f["Se completaría"] = ", ".join(
            f"{ETIQUETAS_DE_MEDIDA.get(campo, campo)}={valor}"
            for campo, valor in nuevas.items())
        f["_nuevas"] = nuevas
        salida.append(f)
        if len(salida) >= limite:
            break
    return salida


def aplicar_medidas_deducidas(filas):
    """Escribe las medidas leídas. Devuelve cuántos productos se completaron."""
    hechos = 0
    with db_lock:
        for f in filas:
            nuevas = f.get("_nuevas") or {}
            if not nuevas:
                continue
            sets = ", ".join(f"{campo} = ?" for campo in nuevas)
            c.execute(f"UPDATE productos SET {sets} WHERE id = ?",
                      list(nuevas.values()) + [f["_id"]])
            hechos += 1
        conn.commit()
    return hechos


def actualizar_medidas(producto_id, diam_int, diam_ext, ancho, paso_rosca, estrias, ubicacion,
                        estrias_internas=None, estrias_externas=None, posicion_seguro=None, tiene_abs="Cualquiera",
                        diam_int_cara_b=None, diam_ext_cara_b=None,
                        diam_rosca_homocinetica=None, diam_copa=None,
                        diam_copa_superior=None, largo_total=None):
    tiene_abs_valor = None if tiene_abs == "Cualquiera" else (1 if tiene_abs == "Sí" else 0)
    with db_lock:
        c.execute(
            "UPDATE productos SET diametro_interno=?, diametro_externo=?, ancho=?, paso_rosca=?, "
            "cantidad_estrias=?, ubicacion=?, estrias_internas=?, estrias_externas=?, posicion_seguro=?, "
            "tiene_abs=?, diametro_interno_cara_b=?, diametro_externo_cara_b=?, "
            "diametro_rosca_homocinetica=?, diametro_copa=?, diametro_copa_superior=?, "
            "largo_total=? WHERE id=?",
            (diam_int or None, diam_ext or None, ancho or None, (paso_rosca.strip() or None) if paso_rosca else None,
             estrias or None, (ubicacion.strip() or None) if ubicacion else None,
             estrias_internas or None, estrias_externas or None,
             (posicion_seguro.strip() or None) if posicion_seguro else None, tiene_abs_valor,
             diam_int_cara_b or None, diam_ext_cara_b or None,
             diam_rosca_homocinetica or None, diam_copa or None,
             diam_copa_superior or None, largo_total or None, producto_id)
        )
        conn.commit()


# ============================================================
# COMPARACIÓN VISUAL DE PIEZAS
# ============================================================
# La idea: que puedas sacarle una foto a la pieza en el mostrador y encontrarla en el catálogo
# aunque la foto de referencia sea del sitio del proveedor — otro ángulo, otro fondo, y otro
# color de pieza (la misma pieza de dos marcas viene pintada distinta).
#
# Cómo se aguanta cada una de esas diferencias:
#   fondo   → se recorta la pieza y se tira el resto antes de comparar
#   color   → se compara en blanco y negro, y también contra el negativo de la foto
#   luz     → se empareja el contraste por zonas (CLAHE) en las dos fotos
#   ángulo  → los puntos ORB aguantan giro y escala, y RANSAC verifica que las coincidencias
#             sean geométricamente coherentes (la misma pieza vista distinto) y no casualidad
#   piezas lisas → cuando no hay textura para agarrarse, queda la silueta (momentos de Hu)
#
# Lo que NO puede: un cambio de punto de vista grande (de frente contra de costado) es otra
# imagen para cualquier método de estos. Para eso se cargan varias fotos del mismo producto.

FIRMA_VERSION = 4   # 4 suma los rasgos gruesos de forma (objetos, aspecto, llenado)
MAX_LADO = 640
ORB_FEATURES_CATALOGO = 500
ORB_FEATURES_CONSULTA = 800


def _cv():
    import cv2
    import numpy as np
    return cv2, np


def _recortar_objeto(img, cv2, np):
    """Se queda con la pieza y tira el fondo.

    Por qué importa: la foto del catálogo del proveedor suele estar sobre fondo blanco de
    estudio, y la que sacás vos en el mostrador tiene el mostrador, la caja, la mano. Si no se
    recorta, la mitad de los puntos que se comparan son del fondo, que no tienen nada que ver
    entre una foto y la otra, y el parecido real de la pieza queda tapado.

    Es conservador: si el recorte da un resultado raro (agarra casi toda la foto, o una esquina
    minúscula), se deja la imagen entera. Recortar mal es peor que no recortar."""
    alto, ancho = img.shape[:2]
    area_total = alto * ancho

    suave = cv2.GaussianBlur(img, (5, 5), 0)
    bordes = cv2.Canny(suave, 30, 110)
    bordes = cv2.dilate(bordes, np.ones((7, 7), np.uint8), iterations=2)

    contornos, _ = cv2.findContours(bordes, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contornos:
        return img, None

    mayor = max(contornos, key=cv2.contourArea)
    area = cv2.contourArea(mayor)
    if area < area_total * 0.04 or area > area_total * 0.92:
        return img, mayor  # el recorte no aporta, pero la silueta sí sirve

    x, y, w, h = cv2.boundingRect(mayor)
    margen_x, margen_y = int(w * 0.08), int(h * 0.08)
    x0 = max(x - margen_x, 0)
    y0 = max(y - margen_y, 0)
    x1 = min(x + w + margen_x, ancho)
    y1 = min(y + h + margen_y, alto)
    if (x1 - x0) < 40 or (y1 - y0) < 40:
        return img, mayor
    return img[y0:y1, x0:x1], mayor


def _rasgos_de_forma(img, contorno, cv2, np):
    """Tres datos gruesos de la foto que sirven para descartar rápido, y que los puntos ORB y
    los momentos de Hu no miran.

    El caso que motivó esto: buscando una rótula aparecía un juego de descarbonización. Son
    fotos que no se parecen en nada para una persona — una es UNA pieza compacta y la otra son
    QUINCE juntas planas desparramadas — pero la comparación no tenía forma de notarlo, porque
    ORB no encuentra textura en una rótula lisa y los momentos de Hu solo miran el contorno más
    grande, así que comparaba la rótula contra UNA de las juntas del juego.

      objetos → cuántas piezas separadas hay en la foto. Distingue 'una pieza' de 'un juego'.
      aspecto → qué tan alargada es (siempre ≥1, sin importar si está parada o acostada).
      llenado → cuánto de su recuadro ocupa. Una rótula llena casi todo; una junta plana o un
                soporte fino, mucho menos."""
    rasgos = {"objetos": 1, "aspecto": 1.0, "llenado": 1.0}
    alto, ancho = img.shape[:2]
    area_total = float(alto * ancho)

    try:
        suave = cv2.GaussianBlur(img, (5, 5), 0)
        bordes = cv2.dilate(cv2.Canny(suave, 30, 110), np.ones((7, 7), np.uint8), iterations=2)
        contornos, _ = cv2.findContours(bordes, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        # "Significativo" = al menos el 1% de la foto. Sin ese piso, cada mota de polvo del
        # mostrador contaría como una pieza más.
        grandes = [k for k in contornos if cv2.contourArea(k) > area_total * 0.01]
        rasgos["objetos"] = max(len(grandes), 1)
    except Exception as _err:
        anotar_error("_rasgos_de_forma", _err)
        pass

    if contorno is not None:
        try:
            (_, _), (w, h), _ = cv2.minAreaRect(contorno)
            if w > 0 and h > 0:
                rasgos["aspecto"] = float(max(w, h) / min(w, h))
            x, y, bw, bh = cv2.boundingRect(contorno)
            if bw > 0 and bh > 0:
                rasgos["llenado"] = float(min(cv2.contourArea(contorno) / (bw * bh), 1.0))
        except Exception as _err:
            anotar_error("_rasgos_de_forma", _err)
            pass
    return rasgos


def _penalizacion_por_rasgos(ra, rb):
    """Cuánto se castiga el parecido por diferencias gruesas de forma. Devuelve un multiplicador
    entre 0 y 1. Si alguna de las dos firmas es vieja y no tiene rasgos, no penaliza nada."""
    if not ra or not rb:
        return 1.0
    factor = 1.0

    # Una pieza suelta contra un juego de muchas: es el caso rótula vs descarbonización
    oa, ob = ra.get("objetos", 1), rb.get("objetos", 1)
    if min(oa, ob) <= 2 and max(oa, ob) >= 6:
        factor *= 0.12
    elif abs(oa - ob) >= 4:
        factor *= 0.5

    # Proporción: algo el doble de alargado que lo otro difícilmente sea la misma pieza
    aa, ab = ra.get("aspecto", 1.0), rb.get("aspecto", 1.0)
    razon = max(aa, ab) / max(min(aa, ab), 0.01)
    if razon > 2.5:
        factor *= 0.25
    elif razon > 1.7:
        factor *= 0.6

    # Cuánto llena su recuadro: separa lo macizo de lo plano o calado
    dif = abs(ra.get("llenado", 1.0) - rb.get("llenado", 1.0))
    if dif > 0.35:
        factor *= 0.4
    elif dif > 0.2:
        factor *= 0.75
    return factor


def _firma_de_forma(contorno, cv2, np):
    """Momentos de Hu de la silueta: describen la FORMA sin importar el tamaño, la rotación ni
    el color. Es lo único que queda cuando la pieza es lisa y no tiene textura para agarrarse
    (rótulas, rulemanes, bujes) — ahí los puntos característicos no dan nada."""
    if contorno is None:
        return None
    try:
        hu = cv2.HuMoments(cv2.moments(contorno)).flatten()
        # escala logarítmica: los valores crudos van de 1e-1 a 1e-60 y son incomparables
        return [float(-np.sign(v) * np.log10(abs(v) + 1e-30)) for v in hu]
    except Exception as _err:
        anotar_error("_firma_de_forma", _err)
        return None


def _preparar(imagen_bytes):
    """Deja la imagen lista para comparar: gris, recortada al objeto, a un tamaño común y con
    el contraste emparejado. Devuelve (imagen, silueta, rasgos) o (None, None, None)."""
    cv2, np = _cv()
    arr = np.frombuffer(imagen_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None, None, None

    escala_previa = 900 / max(img.shape[:2])
    if escala_previa < 1:
        img = cv2.resize(img, None, fx=escala_previa, fy=escala_previa, interpolation=cv2.INTER_AREA)

    # CLAHE ANTES de buscar el objeto: si la foto tiene poco contraste (pieza clara sobre fondo
    # claro, foto velada) sin esto no se detecta ningún borde y el recorte no recorta nada.
    img = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(img)

    recortada, contorno = _recortar_objeto(img, cv2, np)
    forma = _firma_de_forma(contorno, cv2, np)
    # Los rasgos se miden sobre la foto ENTERA, antes del recorte: el recorte se queda con la
    # pieza más grande, así que después del recorte un juego de 15 juntas parece una sola.
    rasgos = _rasgos_de_forma(img, contorno, cv2, np)

    escala = MAX_LADO / max(recortada.shape[:2])
    if escala < 1:
        recortada = cv2.resize(recortada, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)
    elif escala > 2:
        recortada = cv2.resize(recortada, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    # Segunda pasada de contraste, ya sobre el recorte: ahora que el fondo no está, el ajuste
    # se reparte sobre la pieza en vez de gastarse en el mostrador.
    return cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(recortada), forma, rasgos


def leer_codigo_de_barras(imagen_bytes):
    """Lee el código de barras o QR de una foto. Devuelve (lista de códigos, error).

    Es la forma más confiable de identificar un repuesto y no depende de nada que se pueda
    equivocar: no hay que reconocer la pieza, ni leer un grabado gastado, ni comparar siluetas.
    El código de la caja es exacto.

    Usa el lector que ya trae OpenCV, que la app instala igual para la comparación de fotos.
    Prueba con la imagen tal cual y también en escala de grises con el contraste emparejado:
    en el mostrador las fotos salen con poca luz y el negro del código se empasta."""
    # OJO: _cv() devuelve (cv2, np), no un tercer valor de error. Asumir lo contrario
    # reventaba con «not enough values to unpack» en la primera línea.
    try:
        cv2, np = _cv()
    except Exception as e:
        anotar_error("leer_codigo_de_barras", e)
        return [], f"No está disponible el lector de imágenes: {e}"
    try:
        img = cv2.imdecode(np.frombuffer(imagen_bytes, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return [], "No pude leer la imagen."

        alto, ancho = img.shape[:2]
        if max(alto, ancho) > 1600:
            escala = 1600 / max(alto, ancho)
            img = cv2.resize(img, (int(ancho * escala), int(alto * escala)))

        gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        versiones = [img, gris,
                     cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gris)]

        encontrados = []
        try:
            lector = cv2.barcode.BarcodeDetector()
            for v in versiones:
                ok, textos, _tipos, _puntos = lector.detectAndDecodeWithType(v)
                if ok:
                    encontrados += [t for t in textos if t and t.strip()]
                if encontrados:
                    break
        except Exception as _err:
            anotar_error("leer_codigo_de_barras", _err)
            pass

        if not encontrados:
            # Muchos proveedores usan QR en vez de barras
            try:
                qr = cv2.QRCodeDetector()
                for v in versiones:
                    texto, _p, _s = qr.detectAndDecode(v)
                    if texto and texto.strip():
                        encontrados.append(texto.strip())
                        break
            except Exception as _err:
                anotar_error("leer_codigo_de_barras", _err)
                pass

        if not encontrados:
            return [], ("No encontré ningún código de barras en la foto. Probá más cerca, con "
                        "buena luz y el código derecho, ocupando buena parte de la pantalla.")
        # Sin repetidos, conservando el orden
        vistos, salida = set(), []
        for t in encontrados:
            limpio = t.strip()
            if limpio not in vistos:
                vistos.add(limpio)
                salida.append(limpio)
        return salida, None
    except Exception as e:
        anotar_error("leer_codigo_de_barras", e)
        return [], f"No se pudo leer: {type(e).__name__}: {e}"


# El prefijo de un código de barras dice EN QUÉ PAÍS se registró la empresa que lo emitió.
# Es público, es fijo y no hace falta consultar nada: lo asigna GS1 y está en la norma.
# Sirve para dos cosas en el mostrador: saber si algo es nacional o importado sin mirar la caja,
# y darse cuenta de que una lista entera cargó códigos de barras como si fueran códigos de
# fábrica —todos con el mismo prefijo de empresa— que es el error que más vínculos muertos deja.
# OJO con lo que NO es un país: 020-029 y 200-299 son de uso interno del comercio (los que
# imprime la balanza del supermercado), y 977-979 son revistas y libros.
PREFIJOS_GS1 = [
    ((0, 19), "Estados Unidos y Canadá"), ((20, 29), "uso interno del comercio"),
    ((30, 39), "Estados Unidos"), ((40, 49), "uso interno del comercio"),
    ((50, 59), "cupón"), ((60, 139), "Estados Unidos y Canadá"),
    ((200, 299), "uso interno del comercio"),
    ((300, 379), "Francia"), ((380, 380), "Bulgaria"), ((383, 383), "Eslovenia"),
    ((385, 385), "Croacia"), ((387, 387), "Bosnia y Herzegovina"), ((389, 389), "Montenegro"),
    ((400, 440), "Alemania"), ((450, 459), "Japón"), ((460, 469), "Rusia"),
    ((470, 470), "Kirguistán"), ((471, 471), "Taiwán"), ((474, 474), "Estonia"),
    ((475, 475), "Letonia"), ((476, 476), "Azerbaiyán"), ((477, 477), "Lituania"),
    ((478, 478), "Uzbekistán"), ((479, 479), "Sri Lanka"), ((480, 480), "Filipinas"),
    ((481, 481), "Bielorrusia"), ((482, 482), "Ucrania"), ((484, 484), "Moldavia"),
    ((485, 485), "Armenia"), ((486, 486), "Georgia"), ((487, 487), "Kazajistán"),
    ((489, 489), "Hong Kong"), ((490, 499), "Japón"), ((500, 509), "Reino Unido"),
    ((520, 521), "Grecia"), ((528, 528), "Líbano"), ((529, 529), "Chipre"),
    ((530, 530), "Albania"), ((531, 531), "Macedonia del Norte"), ((535, 535), "Malta"),
    ((539, 539), "Irlanda"), ((540, 549), "Bélgica y Luxemburgo"), ((560, 560), "Portugal"),
    ((569, 569), "Islandia"), ((570, 579), "Dinamarca"), ((590, 590), "Polonia"),
    ((594, 594), "Rumania"), ((599, 599), "Hungría"), ((600, 601), "Sudáfrica"),
    ((603, 603), "Ghana"), ((608, 608), "Baréin"), ((609, 609), "Mauricio"),
    ((611, 611), "Marruecos"), ((613, 613), "Argelia"), ((616, 616), "Kenia"),
    ((618, 618), "Costa de Marfil"), ((619, 619), "Túnez"), ((621, 621), "Siria"),
    ((622, 622), "Egipto"), ((624, 624), "Libia"), ((625, 625), "Jordania"),
    ((626, 626), "Irán"), ((627, 627), "Kuwait"), ((628, 628), "Arabia Saudita"),
    ((629, 629), "Emiratos Árabes Unidos"), ((640, 649), "Finlandia"), ((690, 695), "China"),
    ((700, 709), "Noruega"), ((729, 729), "Israel"), ((730, 739), "Suecia"),
    ((740, 740), "Guatemala"), ((741, 741), "El Salvador"), ((742, 742), "Honduras"),
    ((743, 743), "Nicaragua"), ((744, 744), "Costa Rica"), ((745, 745), "Panamá"),
    ((746, 746), "República Dominicana"), ((750, 750), "México"), ((754, 755), "Canadá"),
    ((759, 759), "Venezuela"), ((760, 769), "Suiza"), ((770, 771), "Colombia"),
    ((773, 773), "Uruguay"), ((775, 775), "Perú"), ((777, 777), "Bolivia"),
    ((778, 779), "Argentina"), ((780, 780), "Chile"), ((784, 784), "Paraguay"),
    ((786, 786), "Ecuador"), ((789, 790), "Brasil"), ((800, 839), "Italia"),
    ((840, 849), "España"), ((850, 850), "Cuba"), ((858, 858), "Eslovaquia"),
    ((859, 859), "Chequia"), ((860, 860), "Serbia"), ((865, 865), "Mongolia"),
    ((867, 867), "Corea del Norte"), ((868, 869), "Turquía"), ((870, 879), "Países Bajos"),
    ((880, 880), "Corea del Sur"), ((884, 884), "Camboya"), ((885, 885), "Tailandia"),
    ((888, 888), "Singapur"), ((890, 890), "India"), ((893, 893), "Vietnam"),
    ((896, 896), "Pakistán"), ((899, 899), "Indonesia"), ((900, 919), "Austria"),
    ((930, 939), "Australia"), ((940, 949), "Nueva Zelanda"), ((955, 955), "Malasia"),
    ((958, 958), "Macao"), ((977, 977), "revista o publicación periódica"),
    ((978, 979), "libro (ISBN)"), ((980, 980), "comprobante de devolución"),
    ((981, 984), "cupón"), ((990, 999), "cupón"),
]


def pais_del_codigo_de_barras(codigo):
    """De qué país es el código de barras, por su prefijo GS1. '' si no se puede decir.

    El país es el de la empresa que REGISTRÓ el código, no el de la fábrica: un repuesto con
    779 lo vende una empresa argentina, aunque la pieza venga de China. Eso igual sirve — lo
    que se quiere saber en el mostrador es si lo consigue un proveedor local."""
    limpio = re.sub(r'\D', '', str(codigo or ""))
    if len(limpio) not in (8, 12, 13, 14):
        return ""
    if len(limpio) == 12:          # UPC-A: es EAN-13 con un cero adelante
        limpio = "0" + limpio
    if len(limpio) == 14:          # DUN-14 (la caja): el dígito de agrupación va adelante
        limpio = limpio[1:]
    try:
        prefijo = int(limpio[:3])
    except ValueError:
        return ""
    for (desde, hasta), pais in PREFIJOS_GS1:
        if desde <= prefijo <= hasta:
            return pais
    return ""


def pais_de_estos_codigos(valores):
    """El país que comparten estos códigos de barras, o '' si no hay uno solo claro.

    Se usa cuando se descubrió que una lista entera cargó códigos de barras como si fueran
    códigos de fábrica: poder decir «son de una empresa de Argentina» hace reconocible un
    número que si no es una tira de dígitos.

    Mira los códigos ENTEROS y no el prefijo común que devuelve columna_es_codigo_de_barras(),
    que sería lo cómodo, por una razón concreta: ese prefijo se corta de la cadena tal como
    está guardada, y un UPC-A de 12 dígitos es un EAN-13 con un cero adelante que ahí no está.
    Sobre el código entero eso ya lo resuelve pais_del_codigo_de_barras(); sobre el prefijo
    suelto, «045496» daría «uso interno del comercio» cuando en realidad es 004, Estados
    Unidos."""
    conteo = {}
    for v in valores:
        pais = pais_del_codigo_de_barras(v)
        if pais:
            conteo[pais] = conteo.get(pais, 0) + 1
    if not conteo:
        return ""
    pais, cuantos = max(conteo.items(), key=lambda kv: kv[1])
    # Si la lista mezcla países no se afirma ninguno: sería peor que no decir nada.
    return pais if cuantos >= sum(conteo.values()) * 0.7 else ""


# No todo prefijo es un país: estos cinco valores son usos especiales de la norma. Importan
# porque si un escaneo cae en uno de ellos, el número NO identifica un repuesto — es la
# etiqueta que imprimió una balanza, un cupón, o el ISBN del manual que estaba al lado. Sin
# esto, el mostrador lee «no está cargado» y se pone a buscar un producto que no existe.
GS1_NO_ES_UN_PAIS = {"uso interno del comercio", "cupón", "revista o publicación periódica",
                     "libro (ISBN)", "comprobante de devolución"}


def buscar_por_codigo_de_barras(codigo_leido):
    """Busca el código escaneado, probando también como código de producto.

    El EAN vive en productos.codigo_barras y buscar_por_codigo() arranca mirando esa columna
    además del código, así que escanear la caja trae el repuesto y toda su red de
    equivalencias. Antes el EAN se cargaba como si fuera un código de fábrica: andaba, pero
    dejaba una equivalencia falsa por producto."""
    clean = sanitizar(codigo_leido)
    if not clean:
        return [], None
    res = buscar_por_codigo(clean)
    if res:
        return res, None
    # Los EAN-13 a veces se cargan sin el dígito verificador, o con un 0 adelante. Y al revés:
    # si lo que se escaneó son los 12 dígitos sin el verificador, el que está cargado es el de
    # 13 — ese dígito no hay que adivinarlo, se calcula.
    _completo = (clean + digito_verificador_gtin(clean)
                 if len(clean) == 12 and clean.isdigit() else "")
    for variante in (clean[:-1], clean.lstrip("0"), "0" + clean, _completo):
        if variante and variante != clean:
            res = buscar_por_codigo(variante)
            if res:
                return res, f"Se encontró como «{variante}» (variante del código escaneado)."
    return [], None


def calcular_firma_visual(imagen_bytes, es_consulta=False):
    """Saca la 'huella' visual de una foto. Devuelve (blob, estado).

    Guarda los puntos característicos (ORB) Y la silueta. Para la foto que se está buscando
    guarda además la versión en negativo: una misma pieza en negro y en aluminio da gradientes
    invertidos, y ORB compara claro-contra-oscuro, así que sin el negativo no se reconocerían
    entre sí. Se guarda solo del lado de la consulta para no duplicar el peso del catálogo."""
    try:
        cv2, np = _cv()
    except Exception as _err:
        anotar_error("calcular_firma_visual", _err)
        return None, "error"

    try:
        img, forma, rasgos = _preparar(imagen_bytes)
        if img is None:
            return None, "error"

        n = ORB_FEATURES_CONSULTA if es_consulta else ORB_FEATURES_CATALOGO
        orb = cv2.ORB_create(nfeatures=n, scaleFactor=1.2, nlevels=10,
                             edgeThreshold=15, fastThreshold=12)
        kp, desc = orb.detectAndCompute(img, None)

        payload = {
            "v": FIRMA_VERSION,
            "forma": forma,
            "rasgos": rasgos,
            "dim": [int(img.shape[1]), int(img.shape[0])],
            "kp": np.float32([k.pt for k in kp]) if kp else None,
            "desc": desc,
        }

        if es_consulta:
            kp_i, desc_i = orb.detectAndCompute(cv2.bitwise_not(img), None)
            payload["kp_inv"] = np.float32([k.pt for k in kp_i]) if kp_i else None
            payload["desc_inv"] = desc_i

        tiene_textura = desc is not None and len(desc) >= 12
        if not tiene_textura and forma is None:
            return None, "sin_detalle"
        estado = "ok" if tiene_textura else "solo_forma"
        return pickle.dumps(payload, protocol=4), estado
    except Exception as _err:
        anotar_error("calcular_firma_visual", _err)
        return None, "error"


# Lo único que puede aparecer adentro de una firma visual: números de numpy y nada más.
# Importa que sea una lista cerrada. pickle no es un formato de datos: es una receta de
# construcción, y al leerlo puede fabricar CUALQUIER objeto de CUALQUIER módulo instalado,
# incluido os.system. Las firmas viven en la base, y la base entera se reemplaza desde
# Estadísticas → Restaurar backup con un archivo .db que sube una persona. O sea que el
# contenido de firma_blob no siempre lo escribió esta app: puede venir de un archivo de
# afuera. Con pickle.loads pelado, un .db preparado a mano ejecuta lo que quiera en el
# servidor apenas alguien entra a buscar por foto. Con esta lista, un blob así no llega a
# construirse: se corta en find_class y la foto queda marcada como ilegible, que es
# exactamente lo que ya pasaba con una firma corrupta.
FIRMAS_CLASES_PERMITIDAS = {
    ("numpy", "ndarray"),
    ("numpy", "dtype"),
    ("numpy", "float32"), ("numpy", "float64"),
    ("numpy", "uint8"), ("numpy", "int32"), ("numpy", "int64"),
    # numpy 2 renombró el módulo interno de "numpy.core" a "numpy._core". Van los dos porque
    # las firmas guardadas con la versión vieja se siguen leyendo con la nueva.
    ("numpy.core.multiarray", "_reconstruct"), ("numpy.core.multiarray", "scalar"),
    ("numpy._core.multiarray", "_reconstruct"), ("numpy._core.multiarray", "scalar"),
}


class _LectorDeFirmas(pickle.Unpickler):
    """Un lector de pickle que solo sabe armar arrays de numpy."""

    def find_class(self, modulo, nombre):
        if (modulo, nombre) in FIRMAS_CLASES_PERMITIDAS:
            return super().find_class(modulo, nombre)
        raise pickle.UnpicklingError(
            f"Una firma visual no puede contener {modulo}.{nombre}"
        )


def leer_firma_visual(blob):
    """pickle.loads, pero solo para lo que una firma visual puede tener adentro."""
    return _LectorDeFirmas(io.BytesIO(blob)).load()


def _cargar_firma(blob):
    """Lee una firma guardada. Acepta las viejas (que eran solo los descriptores sueltos) para
    no tener que rehacer todo el catálogo de golpe."""
    try:
        dato = leer_firma_visual(blob)
    except Exception as _err:
        anotar_error("_cargar_firma", _err)
        return None
    if isinstance(dato, dict) and dato.get("v"):
        return dato
    # Formato viejo: un array de descriptores pelado, sin puntos ni silueta
    return {"v": 1, "desc": dato, "kp": None, "forma": None}


def _parecido_de_forma(forma_a, forma_b):
    """0..100 según cuánto se parecen las siluetas."""
    if not forma_a or not forma_b:
        return 0.0
    try:
        # Solo los 3 primeros momentos, y con peso decreciente. Del cuarto en adelante son ruido
        # puro en fotos reales (el séptimo hasta cambia de signo si la pieza está espejada), y
        # metiéndolos la comparación daba cero siempre, incluso entre dos fotos de la misma pieza.
        pesos = (1.0, 0.7, 0.4)
        d = sum(w * abs(a - b) for w, a, b in zip(pesos, forma_a[:3], forma_b[:3]))
        return float(max(0.0, 100.0 * (1.0 - d / 2.5)))
    except Exception as _err:
        anotar_error("_parecido_de_forma", _err)
        return 0.0


def _puntaje_textura(desc_q, kp_q, desc_c, kp_c, cv2, np):
    """Cuenta coincidencias reales entre dos fotos y las verifica geométricamente.

    El filtro de Lowe saca las coincidencias ambiguas, y RANSAC exige además que todas caigan
    en una misma transformación coherente — o sea, que sean la misma pieza vista distinto, y no
    puntos sueltos que casualmente se parecen. Sin esa verificación, dos piezas metálicas
    cualesquiera dan decenas de 'coincidencias' y todo parece parecido a todo."""
    if desc_q is None or desc_c is None or len(desc_q) < 8 or len(desc_c) < 8:
        return 0.0, 0
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    try:
        matches = bf.knnMatch(desc_q, desc_c, k=2)
    except Exception as _err:
        anotar_error("_puntaje_textura", _err)
        return 0.0, 0

    buenos = [par[0] for par in matches if len(par) == 2 and par[0].distance < 0.78 * par[1].distance]
    if not buenos:
        return 0.0, 0

    inliers = 0
    if len(buenos) >= 8 and kp_q is not None and kp_c is not None:
        try:
            src = np.float32([kp_q[m.queryIdx] for m in buenos]).reshape(-1, 1, 2)
            dst = np.float32([kp_c[m.trainIdx] for m in buenos]).reshape(-1, 1, 2)
            _, mascara = cv2.findHomography(src, dst, cv2.RANSAC, 6.0, maxIters=2000)
            inliers = int(mascara.sum()) if mascara is not None else 0
        except Exception as _err:
            anotar_error("_puntaje_textura", _err)
            inliers = 0

    # Las verificadas valen; las no verificadas cuentan poco (pueden ser casualidad)
    efectivas = inliers + len(buenos) * 0.15
    denominador = max(min(len(desc_q), len(desc_c)), 1)
    return float(min(100.0, 130.0 * efectivas / denominador)), inliers


def comparar_firmas(firma_consulta, blob_catalogo):
    """Devuelve (parecido 0-100, coincidencias verificadas, parecido de forma 0-100)."""
    try:
        cv2, np = _cv()
    except Exception as _err:
        anotar_error("comparar_firmas", _err)
        return 0.0, 0, 0.0

    fc = _cargar_firma(blob_catalogo)
    if not fc:
        return 0.0, 0, 0.0

    mejor_textura, mejor_inliers = 0.0, 0
    versiones = [(firma_consulta.get("desc"), firma_consulta.get("kp"))]
    if firma_consulta.get("desc_inv") is not None:
        versiones.append((firma_consulta.get("desc_inv"), firma_consulta.get("kp_inv")))

    for desc_q, kp_q in versiones:
        p, inl = _puntaje_textura(desc_q, kp_q, fc.get("desc"), fc.get("kp"), cv2, np)
        if p > mejor_textura:
            mejor_textura, mejor_inliers = p, inl

    forma = _parecido_de_forma(firma_consulta.get("forma"), fc.get("forma"))

    factor = _penalizacion_por_rasgos(firma_consulta.get("rasgos"), fc.get("rasgos"))

    if mejor_textura >= 5:
        # Hay textura para agarrarse: manda eso, la forma solo desempata
        total = 0.78 * mejor_textura + 0.22 * forma
    else:
        # Pieza lisa (rótulas, rulemanes, bujes): no hay ningún detalle que verificar, solo la
        # silueta. Sola vale poco, y encima los momentos de Hu comparan un contorno contra otro
        # sin enterarse de si la otra foto es un juego de quince piezas. Por eso acá los rasgos
        # gruesos no descuentan: mandan. Si no coinciden, esto no es un candidato.
        if factor < 0.5:
            return 0.0, 0, round(forma, 1)
        total = 0.35 * forma
    return round(min(total * factor, 100.0), 1), mejor_inliers, round(forma, 1)



# ============================================================
# GUARDADO DE FOTOS (varias por producto)
# ============================================================

def agregar_foto_producto(producto_id, imagen_bytes, origen="subida", fuente=None,
                          hacer_principal=None, liviano=False):
    """Suma una foto más al producto. Devuelve (id_foto, estado).

    Un producto puede tener varias: la del catálogo del proveedor, la que sacaste vos, la de
    otra marca del mismo repuesto. Al buscar se compara contra TODAS y se queda con la mejor —
    que es lo único que realmente resuelve el cambio de ángulo, porque ninguna comparación
    reconoce una pieza de frente en una foto de costado."""
    from PIL import Image as PILImage
    import base64
    try:
        img = PILImage.open(io.BytesIO(imagen_bytes)).convert("RGB")
    except Exception as _err:
        anotar_error("agregar_foto_producto", _err)
        return None, "error"
    img.thumbnail((500, 500))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=82)
    comprimida = buffer.getvalue()

    firma, estado = calcular_firma_visual(comprimida)
    thumb = generar_miniatura(comprimida)

    if liviano and fuente:
        # Modo liviano: se guarda el LINK, no la imagen. La foto de 500px pesa unos 45 KB dentro
        # de la base; la miniatura, 4 KB. Con 8.000 productos eso es la diferencia entre una base
        # de 500 MB (que ya no entra en el backup de GitHub ni sobrevive un reinicio) y una de
        # 200 MB. La imagen grande la muestra el navegador desde el sitio del proveedor.
        data_uri = fuente
    else:
        data_uri = "data:image/jpeg;base64," + base64.b64encode(comprimida).decode("ascii")

    # Todo o nada: se guarda la foto y, si es la primera, pasa a ser la de la ficha.
    with db_lock, transaccion():
        c.execute("""INSERT INTO producto_fotos (producto_id, imagen_data, firma_blob, estado,
                                                 origen, fuente, firma_version)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (producto_id, data_uri, firma, estado, origen, fuente,
                   FIRMA_VERSION if firma else None))
        id_foto = c.lastrowid
        if hacer_principal is None:
            c.execute("SELECT imagen_url FROM productos WHERE id = ?", (producto_id,))
            fila = c.fetchone()
            hacer_principal = not (fila and fila["imagen_url"])
        if hacer_principal:
            c.execute("UPDATE productos SET imagen_url = ?, imagen_thumb = ?, imagen_orb_estado = ? "
                      "WHERE id = ?", (data_uri, thumb, estado, producto_id))
    return id_foto, estado


def listar_fotos_producto(producto_id):
    c.execute("""SELECT id, imagen_data, estado, origen, fuente, created_at
                 FROM producto_fotos WHERE producto_id = ? ORDER BY id""", (producto_id,))
    return [dict(r) for r in c.fetchall()]


def eliminar_foto_producto(id_foto):
    """Borra una foto. Si era la que se muestra en el buscador, la reemplaza por otra que quede."""
    c.execute("SELECT producto_id, imagen_data FROM producto_fotos WHERE id = ?", (id_foto,))
    fila = c.fetchone()
    if not fila:
        return False
    producto_id, data = fila["producto_id"], fila["imagen_data"]
    # Todo o nada: borrar la foto y elegir con cuál se reemplaza en la ficha es lo mismo.
    with db_lock, transaccion():
        c.execute("DELETE FROM producto_fotos WHERE id = ?", (id_foto,))
        c.execute("SELECT imagen_url FROM productos WHERE id = ?", (producto_id,))
        actual = c.fetchone()
        if actual and actual["imagen_url"] == data:
            c.execute("SELECT imagen_data, estado FROM producto_fotos WHERE producto_id = ? "
                      "ORDER BY id LIMIT 1", (producto_id,))
            reemplazo = c.fetchone()
            if reemplazo:
                c.execute("UPDATE productos SET imagen_url = ?, imagen_thumb = ?, imagen_orb_estado = ? "
                          "WHERE id = ?",
                          (reemplazo["imagen_data"], generar_miniatura_de_data_uri(reemplazo["imagen_data"]),
                           reemplazo["estado"], producto_id))
            else:
                c.execute("UPDATE productos SET imagen_url = NULL, imagen_thumb = NULL, "
                          "imagen_orb_estado = NULL WHERE id = ?", (producto_id,))
    return True


def generar_miniatura_de_data_uri(data_uri):
    """Miniatura de una foto guardada. Si lo guardado es un link (modo liviano), el link mismo
    hace de miniatura: la baja el navegador."""
    import base64
    if not data_uri:
        return None
    if not data_uri.startswith("data:"):
        return data_uri
    try:
        return generar_miniatura(base64.b64decode(data_uri.split(",", 1)[1]))
    except Exception as _err:
        anotar_error("generar_miniatura_de_data_uri", _err)
        return None


def contar_fotos_comparables():
    """(fotos listas, productos con al menos una foto lista, fotos sin procesar, fotos que no sirven)"""
    c.execute("SELECT COUNT(*), COUNT(DISTINCT producto_id) FROM producto_fotos WHERE firma_blob IS NOT NULL")
    listas, productos = c.fetchone()
    c.execute("SELECT COUNT(*) FROM producto_fotos WHERE firma_blob IS NULL AND (estado IS NULL OR estado = 'error')")
    pendientes = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM producto_fotos WHERE estado = 'sin_detalle'")
    no_sirven = c.fetchone()[0]
    return listas, productos, pendientes, no_sirven


def buscar_por_similitud_visual(imagen_bytes, top_n=8, minimo=8.0, progreso=None,
                                 familia=None):
    """Compara una foto contra todas las del catálogo y devuelve las más parecidas ordenadas.

    Son candidatos para revisar a mano, NUNCA una identificación confirmada: hay repuestos que
    de foto son idénticos y no son intercambiables (cambia el paso de rosca, la altura, el lado).
    Confirmá siempre por código o comparando la pieza física."""
    firma_consulta, estado = calcular_firma_visual(imagen_bytes, es_consulta=True)
    if firma_consulta is None:
        if estado == "error":
            return None, ("No se pudo procesar esa imagen. Puede estar dañada, o ser un formato que "
                          "el servidor no puede abrir.")
        return None, ("Esa foto no tiene nada de qué agarrarse para comparar: está muy borrosa, muy "
                      "oscura, o la pieza se confunde con el fondo. Probá de nuevo apoyándola sobre "
                      "un fondo liso de otro color, con buena luz y sin que salga movida.")
    firma_consulta = leer_firma_visual(firma_consulta)

    c.execute("SELECT COUNT(*) FROM producto_fotos WHERE firma_blob IS NOT NULL")
    total_fotos = c.fetchone()[0]
    if not total_fotos:
        return None, _mensaje_catalogo_visual_vacio()

    mejores = {}
    procesadas = 0
    # De a tandas: traer las firmas de todo el catálogo de una sola vez llenaría la memoria del
    # servidor con catálogos grandes y la app se reiniciaría en el medio de la búsqueda.
    c.execute("""SELECT f.id, f.producto_id, f.firma_blob, p.codigo_raw, p.descripcion,
                        p.precio, p.stock, m.nombre AS marca
                 FROM producto_fotos f
                 JOIN productos p ON p.id = f.producto_id
                 JOIN marcas m ON m.id = p.marca_id
                 WHERE f.firma_blob IS NOT NULL""")
    while True:
        tanda = c.fetchmany(200)
        if not tanda:
            break
        for fila in tanda:
            procesadas += 1
            if progreso and procesadas % 25 == 0:
                progreso(procesadas, total_fotos)
            # Filtro por tipo de pieza. Es lo que más ayuda y no sale de la foto: vos ya sabés
            # que estás buscando una rótula, así que no tiene sentido que la app te ofrezca un
            # juego de juntas. Descarta antes de comparar, así además va más rápido.
            if familia and clasificar_repuesto(fila["descripcion"]) != familia:
                continue
            try:
                puntaje, verificadas, forma = comparar_firmas(firma_consulta, fila["firma_blob"])
            except Exception as _err:
                anotar_error("buscar_por_similitud_visual", _err)
                continue
            pid = fila["producto_id"]
            if pid not in mejores or puntaje > mejores[pid]["Parecido"]:
                mejores[pid] = {
                    "ID": pid,
                    "Codigo": fila["codigo_raw"],
                    "Descripcion": fila["descripcion"],
                    "Marca": fila["marca"],
                    "Precio": fila["precio"],
                    "Stock": fila["stock"],
                    "Parecido": puntaje,
                    "Coincidencias": verificadas,
                    "Forma": forma,
                }

    resultados = [r for r in mejores.values() if r["Parecido"] >= minimo]
    resultados.sort(key=lambda r: (-r["Parecido"], -r["Coincidencias"]))
    if not resultados:
        return [], ("Ninguna foto del catálogo se parece lo suficiente. Puede ser que el producto no "
                    "esté cargado con foto, que la foto de referencia sea de un ángulo demasiado "
                    "distinto (cargale a ese producto una segunda foto del ángulo que usás vos), o "
                    "que la pieza sea lisa y sin marcas: en rótulas, rulemanes y bujes no hay "
                    "ningún detalle para agarrarse y esta búsqueda casi nunca sirve. Para esos "
                    "casos anda mucho mejor **📐 Buscar por medidas mecánicas**.")
    return resultados[:top_n], None


def _mensaje_catalogo_visual_vacio():
    c.execute("SELECT COUNT(*) FROM producto_fotos")
    fotos = c.fetchone()[0]
    if fotos:
        return (f"Hay {fotos} foto(s) en el catálogo pero ninguna procesada todavía. Tocá "
                "«🔄 Procesar fotos pendientes» acá arriba y volvé a intentar.")
    return ("Todavía no hay ninguna foto en el catálogo para comparar, así que el **paso 2 no "
            "puede encontrar nada**: compara tu foto contra las que estén cargadas, y no hay "
            "ninguna. Usá el **paso 3, buscar en internet**, que no necesita nada cargado.\n\n"
            "Las fotos se cargan desde Administrar → Medidas y fotos (subiendo la foto o pegando "
            "la dirección de la ficha del proveedor), o en tanda desde Estadísticas → "
            "Mantenimiento. "
            "Ojo: el *backup sin fotos* que se sube al repositorio no las lleva, así que después "
            "de un reinicio del hosting hay que volver a cargarlas.")


def nivel_de_parecido(fila):
    """Traduce el puntaje a algo que se pueda leer de un vistazo, sin dar falsa seguridad.

    Lo que manda son las coincidencias VERIFICADAS, no el porcentaje. Sin ninguna, el parecido
    salió solo de la silueta, y una silueta parecida no significa casi nada entre repuestos:
    antes eso podía llegar a mostrarse como «Media — mirala bien», que era prometer de más."""
    if fila["Coincidencias"] >= 25 and fila["Parecido"] >= 30:
        return "🟢 Fuerte — muchos detalles coinciden"
    if fila["Coincidencias"] >= 8:
        return "🟡 Media — mirala bien"
    if fila["Coincidencias"] >= 3:
        return "🟠 Floja — pocos detalles verificados"
    return "🔴 Solo la silueta — no confíes en esto"


def generar_miniatura(imagen_bytes, lado=110):
    """Versión chiquita de la foto, para las listas de resultados. La foto normal (400px) pesa
    unas 10 veces más y antes la búsqueda la traía entera por cada resultado, aunque en la tabla
    se vea del tamaño de una uña — con muchos resultados eso se nota, sobre todo en el celular."""
    from PIL import Image as PILImage
    import base64
    try:
        img = PILImage.open(io.BytesIO(imagen_bytes)).convert("RGB")
        img.thumbnail((lado, lado))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=70)
        return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception as _err:
        anotar_error("generar_miniatura", _err)
        return None


def actualizar_imagen_producto(producto_id, imagen_bytes, origen="subida", fuente=None,
                                liviano=False):
    """Guarda una foto del producto. Devuelve True si además quedó lista para la búsqueda visual.
    Se conserva el nombre de antes porque lo usan las bajadas en tanda."""
    _, estado = agregar_foto_producto(producto_id, imagen_bytes, origen=origen, fuente=fuente,
                                       liviano=liviano)
    return estado == "ok"


def eliminar_imagen_producto(producto_id):
    """Saca TODAS las fotos del producto."""
    # Todo o nada: si se borran las fotos y la ficha queda apuntando a una que ya no está,
    # el buscador muestra el hueco de una imagen rota.
    with db_lock, transaccion():
        c.execute("DELETE FROM producto_fotos WHERE producto_id = ?", (producto_id,))
        c.execute("UPDATE productos SET imagen_url = NULL, imagen_thumb = NULL, imagen_orb_blob = NULL, "
                   "imagen_orb_estado = NULL WHERE id = ?", (producto_id,))


def imagenes_de_una_direccion(url, maximo=8):
    """Trae las fotos que haya en una dirección web. Devuelve (lista de (url, bytes), error).

    Si la dirección apunta directo a una imagen, baja esa. Si es la página de un producto, saca
    las fotos de adentro: mira la imagen que la página declara como principal (og:image, la que
    usan WhatsApp y Facebook para la vista previa) y después las <img> normales, salteando
    logos, íconos y banners."""
    import requests
    from urllib.parse import urljoin

    try:
        cabecera = requests.head(url, timeout=8, allow_redirects=True,
                                 headers={"User-Agent": "Mozilla/5.0 (compatible; EquivalenciasElChavo/1.0)"})
        tipo = cabecera.headers.get("Content-Type", "")
    except Exception as _err:
        anotar_error("imagenes_de_una_direccion", _err)
        tipo = ""

    if "image" in tipo.lower() or url.lower().split("?")[0].endswith((".jpg", ".jpeg", ".png", ".webp")):
        datos, error = descargar_imagen(url)
        return ([(url, datos)], None) if datos else (None, error or "no se pudo bajar esa imagen")

    try:
        respuesta = requests.get(url, timeout=15,
                                 headers={"User-Agent": "Mozilla/5.0 (compatible; EquivalenciasElChavo/1.0)"})
        if respuesta.status_code != 200:
            return None, f"la página respondió {respuesta.status_code}"
        html = respuesta.text
    except Exception as e:
        anotar_error("imagenes_de_una_direccion", e)
        return None, f"no se pudo abrir la página ({type(e).__name__})"

    candidatas, vistas = [], set()

    def sumar(src):
        if not src or src.startswith("data:"):
            return
        if any(x in src.lower() for x in ("logo", "icon", "sprite", "banner", "pixel", "avatar",
                                          "placeholder", "loading", ".svg", ".gif")):
            return
        absoluta = urljoin(url, src)
        if absoluta not in vistas:
            vistas.add(absoluta)
            candidatas.append(absoluta)

    for m in re.finditer(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', html, re.I):
        sumar(m.group(1))
    for m in re.finditer(r'<img[^>]+?(?:data-src|data-original|src)=["\']([^"\']+)["\']', html, re.I):
        sumar(m.group(1))

    encontradas, errores = [], []
    for url_img in candidatas[:maximo * 3]:
        if len(encontradas) >= maximo:
            break
        datos, error = descargar_imagen(url_img)
        if datos and len(datos) > 8000:   # los íconos chiquitos no son fotos de producto
            encontradas.append((url_img, datos))
        elif error:
            errores.append(error)
    if encontradas:
        return encontradas, None
    return None, "no encontré ninguna foto de producto en esa página"


def migrar_imagenes_pendientes(limite=400):
    """Pone al día las firmas visuales: pasa las fotos viejas (que estaban sueltas en la ficha del
    producto) a la tabla de fotos, y calcula la firma de las que todavía no la tienen.
    Se saltea lo que ya se intentó y no dio, así el contador de pendientes no queda clavado."""
    import base64
    resumen = {"listas": 0, "sin_detalle": 0, "error": 0, "links": 0, "migradas": 0}

    # 1) Fotos que están en la ficha del producto pero todavía no en la tabla de fotos
    c.execute("""SELECT p.id, p.imagen_url FROM productos p
                 WHERE p.imagen_url IS NOT NULL AND p.imagen_url LIKE 'data:%'
                   AND NOT EXISTS (SELECT 1 FROM producto_fotos f WHERE f.producto_id = p.id)
                 LIMIT ?""", (limite,))
    for fila in c.fetchall():
        try:
            datos = base64.b64decode(fila["imagen_url"].split(",", 1)[1])
            firma, estado = calcular_firma_visual(datos)
            # Todo o nada: pasar la foto a la tabla y marcarle el estado al producto. El paso 1
            # se saltea lo que ya está en producto_fotos, así que una foto migrada a medias no
            # vuelve a pasar por acá nunca más.
            with db_lock, transaccion():
                c.execute("""INSERT INTO producto_fotos (producto_id, imagen_data, firma_blob, estado,
                                                         origen, firma_version)
                             VALUES (?, ?, ?, ?, 'migrada', ?)""",
                          (fila["id"], fila["imagen_url"], firma, estado,
                           FIRMA_VERSION if firma else None))
                c.execute("UPDATE productos SET imagen_orb_estado = ? WHERE id = ?", (estado, fila["id"]))
            resumen["migradas"] += 1
            resumen["listas" if estado == "ok" else ("sin_detalle" if estado == "sin_detalle" else "error")] += 1
        except Exception as _err:
            anotar_error("migrar_imagenes_pendientes", _err)
            resumen["error"] += 1

    # 2) Fotos ya en la tabla pero sin firma calculada
    c.execute("""SELECT id, producto_id, imagen_data FROM producto_fotos
                 WHERE (
                        (firma_blob IS NULL AND (estado IS NULL OR estado = 'error'))
                        OR COALESCE(firma_version, 0) < ?
                       )
                   AND imagen_data LIKE 'data:%' LIMIT ?""", (FIRMA_VERSION, limite))
    for fila in c.fetchall():
        try:
            datos = base64.b64decode(fila["imagen_data"].split(",", 1)[1])
            firma, estado = calcular_firma_visual(datos)
            with db_lock:
                c.execute("UPDATE producto_fotos SET firma_blob = ?, estado = ?, firma_version = ? "
                          "WHERE id = ?",
                          (firma, estado, FIRMA_VERSION if firma else None, fila["id"]))
                conn.commit()
            resumen["listas" if estado == "ok" else ("sin_detalle" if estado == "sin_detalle" else "error")] += 1
        except Exception as _err:
            anotar_error("migrar_imagenes_pendientes", _err)
            resumen["error"] += 1

    # 3) Miniaturas faltantes y fotos que son link externo (esas hay que bajarlas desde Mantenimiento)
    c.execute("""SELECT id, imagen_url FROM productos
                 WHERE imagen_url IS NOT NULL AND imagen_thumb IS NULL LIMIT ?""", (limite,))
    for fila in c.fetchall():
        url = fila["imagen_url"]
        try:
            if url.startswith("data:"):
                thumb = generar_miniatura_de_data_uri(url)
            else:
                thumb = url          # link externo: lo carga el navegador
                resumen["links"] += 1
            if thumb:
                with db_lock:
                    c.execute("UPDATE productos SET imagen_thumb = ? WHERE id = ?", (thumb, fila["id"]))
                    conn.commit()
        except Exception as _err:
            anotar_error("migrar_imagenes_pendientes", _err)
            continue
    return resumen


def contar_fotos_pendientes_de_firma():
    c.execute("""SELECT (SELECT COUNT(*) FROM productos p
                         WHERE p.imagen_url LIKE 'data:%'
                           AND NOT EXISTS (SELECT 1 FROM producto_fotos f WHERE f.producto_id = p.id))
                      + (SELECT COUNT(*) FROM producto_fotos
                         WHERE (firma_blob IS NULL AND (estado IS NULL OR estado = 'error'))
                            OR COALESCE(firma_version, 0) < ?)""", (FIRMA_VERSION,))
    return c.fetchone()[0]


@st.cache_resource
def _ejecutar_migracion_orb_una_vez():
    """Corre migrar_imagenes_pendientes() una sola vez por proceso (no en cada rerun de
    Streamlit), con el mismo patrón que ya usa get_connection() para la conexión a la base."""
    return migrar_imagenes_pendientes()


_ejecutar_migracion_orb_una_vez()


# ============================================================
# AUDITORÍA DIARIA DE STOCK POR MUESTREO
# ============================================================
def generar_auditoria_hoy(cantidad=8):
    """Genera (si no existe todavía) la muestra aleatoria de hoy, priorizando favoritos y productos con precio cargado."""
    hoy = datetime.now().strftime("%Y-%m-%d")
    with db_lock:
        c.execute("SELECT COUNT(*) FROM auditoria_diaria WHERE fecha = ?", (hoy,))
        if c.fetchone()[0] > 0:
            return False
        c.execute(
            "SELECT id, stock FROM productos WHERE favorito = 1 OR precio IS NOT NULL ORDER BY RANDOM() LIMIT ?",
            (cantidad,)
        )
        elegidos = c.fetchall()
        for row in elegidos:
            c.execute(
                "INSERT OR IGNORE INTO auditoria_diaria (fecha, producto_id, stock_sistema) VALUES (?, ?, ?)",
                (hoy, row["id"], row["stock"])
            )
        conn.commit()
    return True


def listar_auditoria_hoy():
    hoy = datetime.now().strftime("%Y-%m-%d")
    c.execute("""SELECT a.id AS "ID_auditoria", p.codigo_raw AS "Codigo", m.nombre AS "Marca",
                 a.stock_sistema AS "Stock sistema", a.stock_contado AS "Stock contado",
                 a.diferencia AS "Diferencia", a.resuelto AS "Resuelto"
                 FROM auditoria_diaria a JOIN productos p ON p.id = a.producto_id JOIN marcas m ON m.id = p.marca_id
                 WHERE a.fecha = ? ORDER BY a.resuelto ASC, p.codigo_raw""", (hoy,))
    return filas_a_listas(c)


def registrar_conteo_auditoria(auditoria_id, stock_contado):
    with db_lock:
        c.execute("SELECT stock_sistema FROM auditoria_diaria WHERE id = ?", (auditoria_id,))
        row = c.fetchone()
        diferencia = stock_contado - (row["stock_sistema"] or 0)
        c.execute(
            "UPDATE auditoria_diaria SET stock_contado=?, diferencia=?, resuelto=1 WHERE id=?",
            (stock_contado, diferencia, auditoria_id)
        )
        conn.commit()


# ============================================================
# UBICACIÓN EN DEPÓSITO (matriz ABC)
# ============================================================
def calcular_matriz_abc(limite=300):
    """Clasifica productos en A/B/C usando la frecuencia de búsqueda como indicador de rotación
    (no hay módulo de ventas en la app, así que esto es una aproximación de demanda)."""
    c.execute("""SELECT p.id AS "ID", p.codigo_raw AS "Codigo", m.nombre AS "Marca",
                 p.ubicacion AS "Ubicación", COALESCE(p.veces_buscado, 0) AS "Veces buscado"
                 FROM productos p JOIN marcas m ON m.id = p.marca_id
                 WHERE COALESCE(p.veces_buscado, 0) > 0 OR p.favorito = 1
                 ORDER BY COALESCE(p.veces_buscado, 0) DESC LIMIT ?""", (limite,))
    filas = filas_a_listas(c)
    total = len(filas)
    for i, f in enumerate(filas):
        if total <= 1 or i < max(1, round(total * 0.2)):
            f["Categoría"] = "A"
            f["Sugerencia"] = "Cerca de la entrada, a la altura de la cintura"
        elif i < round(total * 0.5):
            f["Categoría"] = "B"
            f["Sugerencia"] = "Zona intermedia"
        else:
            f["Categoría"] = "C"
            f["Sugerencia"] = "Estante superior o trasero"
    return filas

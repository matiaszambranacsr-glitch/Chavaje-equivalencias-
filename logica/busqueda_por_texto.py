"""Las descripciones con las columnas pegadas y la búsqueda por texto.

Salió de logica/descripciones.py, que con 5.400 renglones juntaba cinco temas.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================================================
# DESCRIPCIONES PEGADAS Y BÚSQUEDA POR TEXTO
# ============================================================================================
# Marcas que se usan para despegar descripciones. Se dejan solo las de 5 letras o más y se
# excluyen las que además son palabras comunes del rubro: separar por "MAN" partiría MANGUERA
# en "MAN GUERA", y por "RAM" partiría RAMAL. Con las largas el riesgo desaparece y son
# justamente las que aparecen pegadas en las listas (VOLKSWAGEN, CHEVROLET, MITSUBISHI...).
_MARCAS_RIESGOSAS = {"BETA", "CASE", "HINO", "SEAT", "LADA", "TATA", "MINI", "HERO", "TVS"}
# Las marcas de REPUESTO se despegan igual que las de auto. Las listas las pegan al código y
# eso se lleva puesto el código: «...MULTIPUNTO BOSCHF1003» daba el código de fábrica
# 'BOSCHF1003', y «MPFIMARELLIF1011» daba 'MPFIMARELLIF1011'. Los dos están cargados en la
# base como si fueran códigos de Bosch y de Marelli.
# MPFI, MPI y TBI no son marcas sino el tipo de inyección, pero se pegan igual y hacen el
# mismo daño, así que van en la misma bolsa.
_SIGLAS_PEGAJOSAS = {"MPFI", "TBI", "SPI", "GDI", "CRDI"}
MARCAS_PARA_DESPEGAR = [m for m in (set(MARCAS_VEHICULO) | MARCAS_DE_REPUESTO | _SIGLAS_PEGAJOSAS)
                        if len(m) >= 4 and m not in _MARCAS_RIESGOSAS and " " not in m]

# Las expresiones se arman UNA vez, al arrancar. Antes se compilaban las 164 de nuevo en cada
# fila: 332 µs por descripción, o sea 3,3 s en una lista de 10.000 filas — diez veces más que
# toda la importación junta.
_RE_PEGADO_MAYUS = re.compile(r'(?<=[a-záéíóúñ])(?=[A-ZÁÉÍÓÚÑ])')
# Se rodea la marca de espacios y después se colapsan los sobrantes. Es más simple y más
# robusto que exigir letra pegada de un lado o del otro: con "DespieceCHEVROLETCAPUCHON" hay
# que separar por IZQUIERDA y por DERECHA a la vez, y una condición sola nunca cubre las dos.
# El orden es de marca más larga a más corta, así "VOLKSWAGEN" gana antes de que pruebe "VW".
_RE_MARCAS_PEGADAS = re.compile(
    "(" + "|".join(re.escape(m) for m in sorted(MARCAS_PARA_DESPEGAR, key=len, reverse=True)) + ")"
) if MARCAS_PARA_DESPEGAR else None
_RE_ESPACIOS = re.compile(r'\s{2,}')

# LA MARCA CORTA PEGADA A UN NÚMERO: «19505VW PASSAT», «314GM Astra», «10127BMW», «FI-IWP041VW».
# MARCAS_PARA_DESPEGAR deja afuera las marcas de menos de cuatro letras a propósito: un «VW» o
# un «GM» sueltos se meten adentro de cualquier palabra y harían un desastre. Pero con un
# DÍGITO justo antes no hay ambigüedad: ninguna palabra del castellano tiene un número pegado
# adelante. Son 1.150 descripciones reales, casi todas de VW (680), GM (193) y BMW (186).
# Y no es solo cosmético: la descripción es de donde sale el código de fábrica, así que
# «FI-IWP041VW Gol» daba el código IWP041VW en vez de IWP041. Hay 5 así cargados en la base.
# Se pide que después de la marca venga algo que NO sea una letra, o una palabra en Mayúscula
# minúscula. Sin esa condición se rompen los errores de tipeo del proveedor —«109103PEUGOET»
# quedaba «109103 PEU GOET» y «LKTCN1007TOYOYA» quedaba «LKTCN1007 TOY OYA»—, que son 32.
_MARCAS_CORTAS_PEGADAS = sorted(
    [m for m in MARCAS_VEHICULO if 2 <= len(m) <= 3 and " " not in m], key=len, reverse=True)
_RE_MARCA_CORTA_TRAS_NUMERO = re.compile(
    r'(?<=\d)(' + "|".join(re.escape(m) for m in _MARCAS_CORTAS_PEGADAS)
    + r')(?=[^A-Za-zÁÉÍÓÚÑ]|[A-ZÁÉÍÓÚÑ][a-záéíóúñ])'
) if _MARCAS_CORTAS_PEGADAS else None

# EL MODELO CON LA CILINDRADA PEGADA: «CORSA1.4», «AMAROK2.0», «HILLUX2.4», «Siena1.0».
# Sale de la exportación del proveedor, que se come el espacio, y hace daño de dos maneras: el
# modelo deja de ser reconocible como modelo, y —peor— «CORSA1.4» tiene forma de código, así
# que se cargaba como código de fábrica. En la base real ese código llegó a colgar un tubo, una
# correa multicanal y un sensor MAP: tres repuestos que no tienen nada que ver, hermanados
# porque las tres descripciones nombran el mismo auto.
# Se piden CUATRO letras antes del número, y ahí está todo el cuidado: con menos se rompían las
# designaciones de zócalo y las medidas, que son iguales pero con una o dos letras —«W2x4.6d»,
# «BX8.2d», «SV8,5-8», «M14X1.5X42», «6mmx8mm x7,89mm»—. Medido sobre las 53.255 descripciones
# reales: separa 158 y no toca ninguna de esas.
_RE_MODELO_CON_CILINDRADA = re.compile(r'(?<=[A-Za-zÁÉÍÓÚÑáéíóúñ]{4})(?=\d[.,]\d)')


# «REF» de «REF. ORIG.» pegado a lo que viene antes. Es la forma de escribir de una de las
# listas y aparece 9.038 veces: «Passat 1 8 98REF ORIG 030121121B», «16VREF ORIG 0280155868».
# Hace daño dos veces:
#   · «98REF», «16VREF», «HDIREF», «PARTNERREF» se cuentan como si fueran modelos de auto y
#     ensucian el desplegable de la pantalla de vehículos;
#   · y sobre todo tapa el marcador: «REF ORIG» es el proveedor diciendo EXPLÍCITAMENTE cuál
#     es el código de fábrica, que es la mejor información que puede llegar. Pegado, el
#     marcador no se reconoce y el código que le sigue queda como una adivinanza más.
# Se pide que después venga ORIG/ORG/ORI/OEM para no partir un código que termine en REF por
# casualidad. Medido sobre las descripciones reales: de 9.038 casos, los 9.038 siguen esa
# forma, así que la condición no deja nada afuera y sí evita el accidente.
_RE_REF_PEGADO = re.compile(r'([A-Za-z0-9])REF(?=\s*\.?\s*(?:ORIG|ORG|ORI|OEM)\b)', re.I)


@functools.lru_cache(maxsize=MAXIMO_DESCRIPCIONES_RECORDADAS)
def _separar_texto_pegado_cacheado(texto):
    return _separar_texto_pegado(texto)


def separar_texto_pegado(texto):
    """Separa las columnas que la exportación pegó. Ver _separar_texto_pegado().

    Esta capa existe solo para el caché: lru_cache necesita un argumento hashable y acá llegan
    cosas que no lo son —None, y los valores que devuelve openpyxl al leer una celda—."""
    if not texto:
        return texto
    if isinstance(texto, str):
        return _separar_texto_pegado_cacheado(texto)
    return _separar_texto_pegado(texto)


def _separar_texto_pegado(texto):
    """Algunas listas de proveedor exportan varias columnas pegadas sin espacio en el medio:
    'Junta Tapa de CilindrosFORDTAUNUS COUPE' o 'PASTILLAS FRENOVOLKSWAGENGOL'.
    Esto las vuelve legibles separando en dos puntos:
      1) donde una minúscula toca una MAYÚSCULA (ahí se pegaron dos campos), y
      2) donde una marca de vehículo quedó pegada a la descripción.

    El punto 2 antes solo funcionaba si la descripción tenía minúsculas: pedía que el carácter
    anterior a la marca NO fuera mayúscula, así que en una lista escrita toda en mayúsculas
    —que son la mayoría— no separaba nada.

    Y dos puntos más: «REF» pegado al final de la palabra anterior cuando después viene ORIG
    (ver _RE_REF_PEGADO), y el modelo con la cilindrada pegada, «CORSA1.4»
    (ver _RE_MODELO_CON_CILINDRADA)."""
    if not texto:
        return texto
    t = str(texto).strip()
    t = _RE_REF_PEGADO.sub(r'\1 REF ', t)
    t = _RE_PEGADO_MAYUS.sub(' ', t)
    t = _RE_MODELO_CON_CILINDRADA.sub(' ', t)
    if _RE_MARCAS_PEGADAS is not None:
        t = _RE_MARCAS_PEGADAS.sub(r' \1 ', t)
    if _RE_MARCA_CORTA_TRAS_NUMERO is not None:
        t = _RE_MARCA_CORTA_TRAS_NUMERO.sub(r' \1 ', t)
    return _RE_ESPACIOS.sub(' ', t).strip()


@st.cache_data(show_spinner=False, max_entries=3)
def _contar_descripciones_pegadas(version):   # ver descripciones_por_palabra()
    c.execute("SELECT descripcion FROM productos WHERE descripcion IS NOT NULL")
    return sum(1 for r in c.fetchall()
               if separar_texto_pegado(r["descripcion"]) != r["descripcion"])


def contar_descripciones_pegadas():
    """Cuántas descripciones del catálogo están pegadas. TODAS, no una muestra.

    Antes miraba las primeras 3.000 filas y mostraba ese número. Sobre el catálogo real eso
    decía «al menos 1.682» cuando son 9.324 — y, peor, si en esas 3.000 no había ninguna la
    pantalla afirmaba «✅ Ninguna descripción con ese problema» con 50.000 filas sin mirar.
    Recorrer las 53.255 tarda 1,4 s y queda cacheado hasta que cambia el catálogo: el número
    exacto vale mucho más que el segundo que cuesta, porque de él depende que alguien decida
    correr el arreglo o no.

    Y se guarda en la base con la versión del catálogo con que se contó: el caché de Streamlit
    se pierde con cada reinicio del servidor —en Streamlit Cloud, seguido— y eran 1,9 s en la
    primera visita a «Limpiar y corregir» después de cada uno, para volver a contar lo mismo."""
    # Con la versión del separador: si cambian sus reglas, lo contado ya no vale.
    version = f"{version_del_catalogo()} · separador {VERSION_SEPARACION}"
    if obtener_config("pegadas_version", "") == version:
        try:
            return int(obtener_config("pegadas_cantidad", ""))
        except ValueError:
            pass
    n = _contar_descripciones_pegadas(version)
    guardar_config("pegadas_version", version)
    guardar_config("pegadas_cantidad", str(n))
    return n


def reparar_descripciones_pegadas():
    c.execute("SELECT id, descripcion FROM productos WHERE descripcion IS NOT NULL")
    # Se separa UNA vez por fila y se compara con el resultado guardado. Antes se llamaba dos
    # veces —una en la condición y otra en el valor— y son 53.255 filas: la mitad del trabajo
    # era tirarlo a la basura.
    cambios = []
    for fila in c.fetchall():
        nueva = separar_texto_pegado(fila["descripcion"])
        if nueva != fila["descripcion"]:
            cambios.append((nueva, fila["id"]))
    with db_lock:
        c.executemany("UPDATE productos SET descripcion = ? WHERE id = ?", cambios)
        conn.commit()
    return len(cambios)


def parece_una_descripcion(texto):
    """Si lo escrito en el buscador de CÓDIGOS es en realidad una descripción: solo palabras
    (ningún número), y no es un código cargado. «filtro aceite gol» o «mannol» sí —el nombre de
    una lista también se busca así, y aparecen todos sus productos—; «W712/94» o «filtro
    24058» no: esos los resuelve la búsqueda por código.
    En el catálogo real hay 77 códigos de solo letras («BAFAH», «BRAGS»): por eso se pregunta
    si existe antes de decidir. Una sola palabra de menos de cuatro letras se deja como código."""
    texto = (texto or "").strip()
    if not texto or "," in texto:
        return False
    palabras = [p for p in re.split(r"\s+", texto) if p]
    if re.search(r"\d", texto):
        # Con números, solo si son datos chicos de una descripción —«1.6», «4», «16V»— y hay
        # al menos dos palabras de verdad: «bomba agua gol 1.6», «ficha 4 vias». Un número
        # que parece código («24058», «W712/94») deja la búsqueda por código.
        if any(re.search(r"\d", p) and len(sanitizar(p)) >= 5 for p in palabras):
            return False
        if sum(1 for p in palabras if re.fullmatch(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}", p)) < 2:
            return False
    if len(palabras) == 1 and len(sanitizar(palabras[0])) < 4:
        return False
    limpio = sanitizar(texto)
    if not limpio or existe_el_codigo(limpio):
        return False
    return any(re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}", p) for p in palabras)


def marcas_que_nombra(palabra):
    """Los id de las listas (no los códigos de fábrica) cuyo nombre tiene esa palabra entera:
    «mannol» → MANNOL LUBRICANTES, «crifa» → CRI-FA. Palabras de tres letras o más: «JL» o
    «VW» solas engancharían cualquier cosa."""
    limpia = re.sub(r"[^A-Z0-9]", "", normalizar_texto(palabra))
    if len(limpia) < 3:
        return []
    c.execute("SELECT id, nombre FROM marcas WHERE tipo <> 'OEM'")
    salida = []
    for fila in c.fetchall():
        nombre = normalizar_texto(fila["nombre"] or "")
        palabras_del_nombre = {re.sub(r"[^A-Z0-9]", "", x) for x in re.split(r"\s+", nombre)}
        if limpia in palabras_del_nombre or limpia == re.sub(r"[^A-Z0-9]", "", nombre):
            salida.append(fila["id"])
    return salida


def buscar_por_texto(texto, aflojar=True):
    """Busca por descripción de forma flexible: cada palabra tiene que aparecer en algún lado
    (descripción o código), sin importar el orden ni las tildes. Así 'ruleman delantero gol'
    encuentra 'Gol 1.6 - Ruleman de rueda delantero', y 'rótula' encuentra 'ROTULA' aunque el
    catálogo la tenga cargada sin tilde (frecuente en listas de proveedores)."""
    palabras = [normalizar_texto(p.strip()) for p in texto.upper().split() if p.strip()]
    if not palabras:
        return []
    # Compara contra la columna 'busqueda', que ya tiene la descripción y el código en
    # mayúscula y sin acentos (la mantienen dos triggers, ver init_db). Antes se le sacaban los
    # acentos a cada fila acá mismo, con doce REPLACE() anidados por columna y por palabra:
    # 981 ms por búsqueda sobre 44.000 productos, y más de tres segundos sobre 110.000. Con la
    # columna guardada la misma búsqueda tarda 40 ms.
    # En vez de exigir que estén TODAS las palabras, se cuenta cuántas coinciden y se ordena
    # por eso. Así "junta tapa cilindro ford taunus" igual encuentra la que dice
    # "Junta Tapa de Cilindros FORD TAUNUS COUPE" aunque no diga exactamente lo mismo, y las
    # que más se parecen quedan arriba. Antes, si fallaba una sola palabra, no aparecía nada.
    puntajes = []
    params = []
    # EL NOMBRE DE LA MARCA TAMBIÉN CUENTA. En el mostrador se buscó «mannol» y no salió nada,
    # con 81 productos de MANNOL LUBRICANTES cargados: sus descripciones dicen «Extreme 5W-40 -
    # 4L», no la marca. Ver marcas_que_nombra().
    _marcas_por_palabra = {p: marcas_que_nombra(p) for p in palabras}
    for palabra in palabras:
        # También se compara contra el código sin guiones ni espacios: si alguien escribe
        # "TC421" o "tc-421", tiene que encontrar igual el producto cargado como "TC-421-15".
        # ESCAPE: sin esto, escribir «100%» o «f_ltro» devolvía 200 filas cualesquiera,
        # porque SQLite tomaba el % y el _ como comodines. Ver como_texto_en_like().
        ramas, suyos = [], []
        limpia = sanitizar(palabra)
        for columna, valor in (("p.busqueda", palabra), ("p.codigo_clean", limpia)):
            # Un LIKE '%%' coincide con TODO. Pasaba al buscar «%» o «_»: sanitizar() los deja
            # en nada, el patrón quedaba vacío y la búsqueda devolvía el catálogo entero.
            if not valor:
                continue
            ramas.append(f"{columna} LIKE ? ESCAPE '\\'")
            suyos.append(f"%{como_texto_en_like(valor)}%")
        if _marcas_por_palabra.get(palabra):
            ramas.append(f"p.marca_id IN ({','.join('?' * len(_marcas_por_palabra[palabra]))})")
            suyos.extend(_marcas_por_palabra[palabra])
        if not ramas:
            continue        # la palabra era solo símbolos: no aporta nada para buscar
        puntajes.append("(CASE WHEN " + " OR ".join(ramas) + " THEN 1 ELSE 0 END)")
        params.extend(suyos)
    if not puntajes:
        return []
    suma = " + ".join(puntajes)

    # Con una o dos palabras se piden todas (si no, aparece cualquier cosa). Con tres o más
    # alcanza con que coincida la mayoría: es lo que permite "interpretar" y no fallar por una.
    utiles = len(puntajes)
    minimo = utiles if utiles <= 2 else max(2, (utiles * 2) // 3)

    _fabricante = campo_opcional_de_producto(c, "marca_repuesto", "Fabricante")
    # Siempre al menos uno, para que el IN () no quede vacío.
    _codigos_escritos = [sanitizar(p) for p in palabras if sanitizar(p)] or [""]
    # UNA pasada por la tabla: las coincidencias se cuentan una vez (antes se calculaban en el
    # SELECT y otra vez en el WHERE), y se trae de una lo que llega al mínimo aflojado; el
    # mínimo de verdad se aplica después, sin volver a recorrer (ver el aflojado más abajo).
    # Medido con 63 proveedores (659.000 productos), mismos resultados: la mediana de 365 a
    # 333 ms y la peor de 594 a 450 ms (la que no encuentra todas las palabras: eran 2 pasadas).
    minimo_flojo = minimo - 1 if (utiles >= 2 and minimo > 1) else minimo
    query = f'''
    SELECT * FROM (
    SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
           m.nombre AS "Marca", m.tipo AS "Tipo",
           -- Quién FABRICA la pieza, que es otra cosa que la lista de quién te la vende. En el
           -- mostrador, entre cinco equivalentes, la pregunta es «¿cuál es el Bosch?».
           -- Ver marca_de_repuesto_en(): sale del final de la descripción, 13.705 productos.
           -- Va por campo_opcional_de_producto() y no directo: contra una base que todavía no
           -- tiene la columna, nombrarla acá tumba el buscador entero.
           {_fabricante},
           p.precio AS "Precio", p.stock AS "Stock",
           p.favorito AS "Favorito", ({suma}) AS _coincidencias,
           LENGTH(p.descripcion) AS _largo
    FROM productos p JOIN marcas m ON m.id = p.marca_id
    WHERE 1
      -- Los códigos de fábrica copian la descripción de la fila que los nombró: buscando
      -- «motor de arranque corsa» salía el arranque y, abajo, sus veinte números de Bosch con
      -- la misma descripción. No son algo que se venda: solo si se escribe el código exacto.
      AND (m.tipo <> 'OEM' OR p.codigo_clean IN ({",".join("?" * len(_codigos_escritos))}))
    ) WHERE _coincidencias >= ?
    ORDER BY _coincidencias DESC, _largo, "Marca" LIMIT 400;
    '''
    with db_lock:
        c.execute(query, params + _codigos_escritos + [minimo_flojo])
        todas = filas_a_listas(c)
        # Lo que llega al mínimo va primero por el orden; si no hay nada, queda lo aflojado.
        filas = [f for f in todas if f["_coincidencias"] >= minimo][:200]
        # Si pidiendo TODAS las palabras no aparece nada, se afloja y se pide una menos.
        # Con dos palabras se exigían las dos, y «rótula suspensión» devolvía CERO resultados
        # sobre un catálogo lleno de rótulas: ninguna descripción dice las dos cosas juntas.
        # Cero resultados es la peor respuesta posible —el de adelante concluye que no hay, y
        # hay— así que es mejor mostrar lo que coincide en parte y que decida la persona.
        # Con las palabras que CUENTAN, no con todas las escritas: «QQQZZZ °» son dos palabras
        # pero una sola útil, y aflojar a «0 coincidencias» devolvía 200 productos cualquiera
        # (lo encontró la revisión independiente del buscador). Nunca se pide menos de una.
        # aflojar=False es para el buscador de CÓDIGOS (ver «kit 22382» en buscador.py): ahí
        # una sola de las dos palabras traía 200 productos cualesquiera.
        if aflojar and not filas and utiles >= 2 and minimo > 1:
            filas = todas[:200]

    # Filtro por RUBRO. Contar palabras coincidentes no alcanza: buscando «bujía golf 1.4 tsi»
    # aparecían juntas de tapa y juegos de motor, porque coinciden en «golf», «1.4» y «tsi» —
    # o sea, en el AUTO, no en la pieza. Y el auto es lo de menos: nadie que pide una bujía se
    # lleva una junta porque va al mismo Golf.
    #
    # Si en el pedido se reconoce un rubro, se dejan solo los resultados de ESE rubro. Los que
    # no se pudieron clasificar se conservan: descartar lo que no se entiende es peor que
    # mostrarlo, porque las descripciones de proveedor son un desastre y muchas piezas legítimas
    # no caen en ninguna familia.
    familia_pedida = clasificar_repuesto(texto)
    if familia_pedida != "Sin clasificar":
        del_rubro, sin_clasificar, de_otro_rubro = [], [], []
        for f in filas:
            fam = clasificar_repuesto(f.get("Descripcion") or "")
            if fam == familia_pedida:
                del_rubro.append(f)
            elif fam == "Sin clasificar":
                sin_clasificar.append(f)
            else:
                de_otro_rubro.append(f)
        # Solo se descarta lo de otro rubro si quedó algo del rubro pedido; si no, es mejor
        # mostrar todo que dejar la pantalla vacía.
        if del_rubro:
            filas = del_rubro + sin_clasificar

    for f in filas:
        f.pop("_coincidencias", None)
        f.pop("_largo", None)
    return filas

"""El mapa del depósito: los depósitos, sus pisos y sus estanterías; dónde está cada repuesto, en
qué orden buscar lo que pidió el mostrador, y el dibujo con lo que hay que buscar resaltado.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================================================
# EL MAPA DEL DEPÓSITO
# ============================================================================================
# Lo pidió el dueño: «que sea fácil de armar los diseños de las estanterías y su ubicación, que
# te resalte dónde está cada repuesto, y que se pueda dividir en distintos pisos y depósitos».
# Hasta acá la ubicación era un texto suelto en cada producto, y en la base real no había
# ninguno cargado: el depósito buscaba de memoria.
#
#   · Cada DEPÓSITO tiene sus PISOS, y cada piso, su PLANO: un dibujo hecho con letras, un
#     renglón por fila, como en una hoja cuadriculada. Cada letra (A–Z, 1–9) es una estantería;
#     «.» es pasillo, «#» pared y «@» la entrada, de donde se arranca a buscar:
#
#         ###########
#         #AAAAA.BBB#
#         #.........#
#         #CCCCC.DDD#
#         #####@#####
#
#     No hace falta dibujarlo: «⚡ Armado rápido» lo arma con cuántas filas de estanterías hay
#     y de cuántos módulos, y «➕ Sumar una estantería» la pone donde se diga. Ver «ARMAR EL
#     PLANO SIN DIBUJAR».
#   · Cada casillero de una estantería a lo largo es un MÓDULO (de izquierda a derecha, o de
#     arriba a abajo si está parada), y cada módulo tiene ESTANTES de abajo hacia arriba. Así
#     se escribe la ubicación de un producto: «A-3-2» es la estantería A, módulo 3, estante 2.
#     Cada estantería tiene un código único en todos los depósitos («A», o «A2» si la A ya
#     está en otro piso), y la ubicación sigue siendo el mismo texto de siempre del producto.
#   · Las distancias son CAMINANDO por el pasillo (las estanterías y las paredes no se
#     atraviesan), no en línea recta: dos estanterías espalda con espalda están cerca en el
#     dibujo y lejos para el que camina.
PASILLO, PARED, ENTRADA = ".", "#", "@"
LETRAS_DE_ESTANTERIA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789"
# Columnas y filas como mucho: un galpón de 60 × 40 casilleros alcanza, y el dibujo se lee.
TAMANO_MAXIMO_DEL_PLANO = (60, 40)


@functools.lru_cache(maxsize=64)
def leer_plano(texto):
    """El plano de un piso, leído: dict con «filas» (una por renglón, todas del mismo ancho),
    «ancho», «alto», «estanterias» ({letra: celdas, caja, si está acostada y sus módulos}),
    «entrada» (la primera «@», o None) y «errores» (lo que no se entendió, en palabras).
    Guardado por texto: no lo modifiques, es compartido."""
    crudas = [f.rstrip() for f in str(texto or "").replace("\t", " ").replace("\r", "").split("\n")]
    while crudas and not crudas[0].strip():
        crudas.pop(0)
    while crudas and not crudas[-1].strip():
        crudas.pop()
    errores = []
    max_ancho, max_alto = TAMANO_MAXIMO_DEL_PLANO
    if len(crudas) > max_alto or any(len(f) > max_ancho for f in crudas):
        errores.append(f"El plano es más grande que {max_ancho} columnas por {max_alto} filas: "
                       "se cortó lo que sobra.")
        crudas = [f[:max_ancho] for f in crudas[:max_alto]]
    ancho = max((len(f) for f in crudas), default=0)
    filas, raros = [], set()
    for y, cruda in enumerate(crudas):
        fila = []
        for x, ch in enumerate(cruda.upper().ljust(ancho)):
            ch = PASILLO if ch == " " else ch
            if ch not in PASILLO + PARED + ENTRADA + LETRAS_DE_ESTANTERIA:
                if ch not in raros:
                    errores.append(f"«{ch}» (fila {y + 1}, columna {x + 1}) no es nada: las "
                                   "estanterías van con letras, el pasillo con «.», las paredes "
                                   "con «#» y la entrada con «@». Quedó como pared.")
                    raros.add(ch)
                ch = PARED
            fila.append(ch)
        filas.append("".join(fila))
    celdas_por_letra = {}
    for y, fila in enumerate(filas):
        for x, ch in enumerate(fila):
            if ch in LETRAS_DE_ESTANTERIA:
                celdas_por_letra.setdefault(ch, []).append((x, y))
    estanterias = {}
    for letra, celdas in sorted(celdas_por_letra.items()):
        x0, x1 = min(x for x, _ in celdas), max(x for x, _ in celdas)
        y0, y1 = min(y for _, y in celdas), max(y for _, y in celdas)
        acostada = (x1 - x0) >= (y1 - y0)
        if acostada:
            modulos = [tuple(cel for cel in celdas if cel[0] == x) for x in range(x0, x1 + 1)]
        else:
            modulos = [tuple(cel for cel in celdas if cel[1] == y) for y in range(y0, y1 + 1)]
        if len(celdas) != (x1 - x0 + 1) * (y1 - y0 + 1):
            errores.append(f"La {letra} no es un rectángulo lleno (¿está en dos lugares?): cada "
                           "estantería tiene que ser un solo bloque de su letra.")
        estanterias[letra] = {"letra": letra, "celdas": tuple(celdas), "caja": (x0, y0, x1, y1),
                              "acostada": acostada, "modulos": tuple(m for m in modulos if m)}
    entradas = [(x, y) for y, fila in enumerate(filas) for x, ch in enumerate(fila)
                if ch == ENTRADA]
    return {"filas": tuple(filas), "ancho": ancho, "alto": len(filas),
            "estanterias": estanterias, "entrada": entradas[0] if entradas else None,
            "errores": tuple(errores)}


def _se_camina(filas, celda):
    x, y = celda
    return 0 <= y < len(filas) and 0 <= x < len(filas[y]) and filas[y][x] in (PASILLO, ENTRADA)


def _accesos(filas, celdas):
    """Los casilleros de pasillo pegados a esas celdas: desde donde se alcanza lo que hay ahí."""
    adentro = set(celdas)
    return tuple(sorted({(x + dx, y + dy) for x, y in celdas
                         for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                         if (x + dx, y + dy) not in adentro and _se_camina(filas, (x + dx, y + dy))}))


@functools.lru_cache(maxsize=512)
def _recorrido_desde(plano_texto, fuentes):
    """{celda: (pasos, celda de la que se llega)} caminando por el pasillo desde `fuentes`
    (tupla de celdas de pasillo). Guardado: el mismo arranque en el mismo plano se pide en cada
    vuelta de la cola, que se actualiza sola."""
    filas = leer_plano(plano_texto)["filas"]
    pasos = {}
    cola = collections.deque()
    for celda in fuentes:
        if celda not in pasos and _se_camina(filas, celda):
            pasos[celda] = (0, None)
            cola.append(celda)
    while cola:
        x, y = cola.popleft()
        for vecina in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if vecina not in pasos and _se_camina(filas, vecina):
                pasos[vecina] = (pasos[(x, y)][0] + 1, (x, y))
                cola.append(vecina)
    return pasos


def _punto_de_partida(plano, desde=None):
    """De dónde se arranca: los casilleros de pasillo de `desde` (o pegados a él, si es una
    estantería); sin `desde`, la entrada; sin entrada, el primer pasillo de arriba a la
    izquierda. Tupla de celdas."""
    filas = plano["filas"]
    if desde:
        caminables = tuple(sorted(c_ for c_ in desde if _se_camina(filas, c_)))
        return caminables or _accesos(filas, desde)
    if plano["entrada"]:
        return (plano["entrada"],)
    for y, fila in enumerate(filas):
        for x, _ in enumerate(fila):
            if _se_camina(filas, (x, y)):
                return ((x, y),)
    return ()


def _pasos_hasta(plano_texto, fuentes, celdas):
    """(pasos, casillero al que se llega, camino) para ir de `fuentes` a lo que está en `celdas`.
    Si no se llega por el pasillo (la encerraron), en línea recta y bien al final: se busca
    igual, pero después de todo lo demás."""
    filas = leer_plano(plano_texto)["filas"]
    pasos = _recorrido_desde(plano_texto, fuentes)
    llegadas = [a for a in _accesos(filas, celdas) if a in pasos]
    if not llegadas:
        recta = min((abs(x - fx) + abs(y - fy) for x, y in celdas for fx, fy in fuentes),
                    default=0)
        return 10_000 + recta, None, []
    llegada = min(llegadas, key=lambda a: (pasos[a][0], a))
    camino, celda = [], llegada
    while celda is not None:
        camino.append(celda)
        celda = pasos[celda][1]
    return pasos[llegada][0], llegada, camino[::-1]


def planear_el_recorrido(plano_texto, paradas, desde=None, por_cercania=True):
    """En qué orden ir a buscar `paradas` (las celdas de cada una) en ese plano, y por dónde.
    por_cercania: siempre a la más cercana de donde se está (ver «LA COLA POR PISO»); si no,
    en el orden en que vienen. (orden: [índices], camino: [celdas], pasos en total)."""
    plano = leer_plano(plano_texto)
    fuentes = _punto_de_partida(plano, desde)
    pendientes = list(range(len(paradas)))
    orden, camino, total = [], [], 0
    while pendientes:
        if por_cercania:
            elegida = min(pendientes,
                          key=lambda i: (_pasos_hasta(plano_texto, fuentes, paradas[i])[0], i))
        else:
            elegida = pendientes[0]
        pasos, llegada, tramo = _pasos_hasta(plano_texto, fuentes, paradas[elegida])
        orden.append(elegida)
        pendientes.remove(elegida)
        if llegada is not None:
            total += pasos
            camino += tramo[1:] if camino else tramo
            fuentes = (llegada,)
    return orden, camino, total


def clave_de_ubicacion(texto):
    """Para ordenar por ubicación: la estantería (con los números como números: A2 antes que
    A10), el módulo y el estante. Lo que no se lee como ubicación, al final y por su texto."""
    leida = leer_ubicacion(texto)
    if not leida:
        return (1, [], 0, 0, str(texto or "").upper())
    codigo, modulo, nivel = leida
    partes = [(0, int(p), "") if p.isdigit() else (1, 0, p)
              for p in re.findall(r"\d+|\D+", codigo)]
    return (0, partes, modulo or 0, nivel or 0, "")


# ============================================================================================
# DEPÓSITOS, PISOS Y ESTANTERÍAS
# ============================================================================================
# Lo arma cualquier empleado: el que sabe dónde está cada estantería es el del depósito. Borrar
# un piso o un depósito entero, el administrador. Sacar del plano una estantería que tiene
# productos ubicados (o achicarla por debajo de un módulo usado) se avisa antes: esos productos
# quedarían con una ubicación que ya no está en el mapa.
def depositos_y_pisos():
    """[{id, nombre, pisos: [{id, nombre, plano, orden_de_la_cola, minutos_de_cercania}]}], en
    el orden en que se crearon."""
    c.execute("""SELECT d.id AS deposito_id, d.nombre AS deposito, p.id, p.nombre, p.plano,
                        p.orden_de_la_cola, p.minutos_de_cercania
                 FROM depositos d LEFT JOIN pisos p ON p.deposito_id = d.id
                 ORDER BY d.orden, d.id, p.orden, p.id""")
    salida = {}
    for r in c.fetchall():
        dep = salida.setdefault(r["deposito_id"], {"id": r["deposito_id"],
                                                   "nombre": r["deposito"], "pisos": []})
        if r["id"] is not None:
            dep["pisos"].append({"id": r["id"], "nombre": r["nombre"], "plano": r["plano"] or "",
                                 "deposito": r["deposito"], "deposito_id": r["deposito_id"],
                                 "orden_de_la_cola": r["orden_de_la_cola"] or "ubicacion",
                                 "minutos_de_cercania": float(r["minutos_de_cercania"] or 1)})
    return list(salida.values())


def hay_mapa():
    """¿Hay por lo menos una estantería en algún plano? Sin mapa, la ubicación de un producto
    sigue siendo un texto libre, como siempre."""
    c.execute("SELECT 1 FROM estanterias LIMIT 1")
    return c.fetchone() is not None


def crear_deposito(nombre):
    """Un depósito nuevo, con un primer piso vacío («Planta baja»). (id del piso, texto)."""
    exigir_nivel("empleado", "armar el depósito")
    nombre = " ".join(str(nombre or "").split())
    if not nombre:
        return None, "Escribí el nombre del depósito."
    with db_lock, transaccion():
        try:
            c.execute("""INSERT INTO depositos (nombre, orden)
                         VALUES (?, (SELECT COALESCE(MAX(orden), 0) + 1 FROM depositos))""",
                      (nombre,))
        except sqlite3.IntegrityError:
            return None, f"Ya hay un depósito «{nombre}»."
        deposito_id = c.lastrowid
        c.execute("INSERT INTO pisos (deposito_id, nombre, orden) VALUES (?, 'Planta baja', 1)",
                  (deposito_id,))
        piso_id = c.lastrowid
        anotar_cambio("creó un depósito", "deposito", deposito_id, despues={"nombre": nombre})
    return piso_id, f"🏬 Depósito «{nombre}» creado, con su planta baja."


def crear_piso(deposito_id, nombre):
    """Otro piso en ese depósito. (id del piso, texto)."""
    exigir_nivel("empleado", "armar el depósito")
    nombre = " ".join(str(nombre or "").split())
    if not nombre:
        return None, "Escribí el nombre del piso."
    with db_lock:
        try:
            c.execute("""INSERT INTO pisos (deposito_id, nombre, orden)
                         VALUES (?, ?, (SELECT COALESCE(MAX(orden), 0) + 1 FROM pisos
                                        WHERE deposito_id = ?))""",
                      (deposito_id, nombre, deposito_id))
        except sqlite3.IntegrityError:
            return None, f"Ese depósito ya tiene un piso «{nombre}»."
        piso_id = c.lastrowid
        anotar_cambio("creó un piso", "piso", piso_id, despues={"nombre": nombre})
        conn.commit()
    return piso_id, f"🏢 Piso «{nombre}» creado."


def borrar_piso(piso_id):
    """Borra el piso con sus estanterías (los productos conservan su ubicación escrita, que deja
    de estar en el mapa). Solo el administrador."""
    exigir_nivel("admin", "borrar un piso del depósito")
    with db_lock, transaccion():
        c.execute("SELECT nombre, plano FROM pisos WHERE id = ?", (piso_id,))
        antes = c.fetchone()
        c.execute("DELETE FROM estanterias WHERE piso_id = ?", (piso_id,))
        c.execute("DELETE FROM pisos WHERE id = ?", (piso_id,))
        anotar_cambio("borró un piso", "piso", piso_id, antes=dict(antes) if antes else None)


def borrar_deposito(deposito_id):
    """Borra el depósito con sus pisos y estanterías. Solo el administrador."""
    exigir_nivel("admin", "borrar un depósito")
    with db_lock, transaccion():
        c.execute("SELECT nombre FROM depositos WHERE id = ?", (deposito_id,))
        antes = c.fetchone()
        c.execute("DELETE FROM estanterias WHERE piso_id IN (SELECT id FROM pisos "
                  "WHERE deposito_id = ?)", (deposito_id,))
        c.execute("DELETE FROM pisos WHERE deposito_id = ?", (deposito_id,))
        c.execute("DELETE FROM depositos WHERE id = ?", (deposito_id,))
        anotar_cambio("borró un depósito", "deposito", deposito_id,
                      antes=dict(antes) if antes else None)


def estanterias_del_piso(piso_id):
    """{letra: {id, codigo, niveles}} de las estanterías de ese piso."""
    c.execute("SELECT id, letra, codigo, niveles FROM estanterias WHERE piso_id = ?", (piso_id,))
    return {r["letra"]: dict(r) for r in c.fetchall()}


def _codigo_libre(letra):
    """El código de una estantería nueva: su letra, o la letra con un número si ya está en otro
    piso («A2»). Los códigos no se repiten en ningún depósito: la ubicación de un producto es
    solo el código, el módulo y el estante."""
    for sufijo in [""] + [str(n) for n in range(2, 100)]:
        c.execute("SELECT 1 FROM estanterias WHERE codigo = ?", (letra + sufijo,))
        if c.fetchone() is None:
            return letra + sufijo
    return letra + uuid.uuid4().hex[:3].upper()


def productos_en(codigo):
    """Los productos ubicados en esa estantería (por su código): [dict] con id, código, marca,
    descripción, stock, ubicación, módulo y estante, por módulo y estante."""
    codigo = str(codigo or "").strip()
    if not codigo:
        return []
    c.execute("""SELECT p.id, p.codigo_raw, p.descripcion, p.stock, p.ubicacion,
                        m.nombre AS marca
                 FROM productos p JOIN marcas m ON m.id = p.marca_id
                 WHERE p.ubicacion LIKE ?""", (codigo + "%",))
    salida = []
    for r in c.fetchall():
        leida = leer_ubicacion(r["ubicacion"])
        if leida and leida[0] == codigo.upper():
            salida.append(dict(r, modulo=leida[1], nivel=leida[2]))
    return sorted(salida, key=lambda r: (r["modulo"] or 0, r["nivel"] or 0, r["codigo_raw"]))


def cuantos_hay_en_cada_estanteria():
    """{código de la estantería (en mayúsculas): cuántos productos tiene ubicados}, de una sola
    pasada por los productos con lugar."""
    c.execute("SELECT ubicacion FROM productos WHERE ubicacion IS NOT NULL AND TRIM(ubicacion) <> ''")
    cuantos = {}
    for r in c.fetchall():
        leida = leer_ubicacion(r["ubicacion"])
        if leida:
            cuantos[leida[0]] = cuantos.get(leida[0], 0) + 1
    return cuantos


def lo_que_se_pierde_con(piso_id, texto):
    """Lo que guardar ese plano dejaría fuera del mapa: [(código, cuántos productos, por qué)]
    de las estanterías que se sacan con productos adentro, o que se achican por debajo de un
    módulo que tiene algo."""
    plano = leer_plano(texto)
    salida = []
    for letra, e in estanterias_del_piso(piso_id).items():
        adentro = productos_en(e["codigo"])
        if not adentro:
            continue
        nueva = plano["estanterias"].get(letra)
        if nueva is None:
            salida.append((e["codigo"], len(adentro), "se saca del plano"))
            continue
        afuera = [p for p in adentro if (p["modulo"] or 0) > len(nueva["modulos"])]
        if afuera:
            salida.append((e["codigo"], len(afuera),
                           f"queda de {len(nueva['modulos'])} módulos y hay cosas más allá"))
    return salida


def guardar_plano(piso_id, texto, aunque_se_pierdan=False):
    """Guarda el plano de un piso: las letras nuevas pasan a ser estanterías (con su código, ver
    _codigo_libre()) y las que ya no están se borran. Si eso deja productos fuera del mapa, no
    guarda sin `aunque_se_pierdan`. (ok, texto, lo que se perdería)."""
    exigir_nivel("empleado", "armar el depósito")
    plano = leer_plano(texto)
    if not plano["filas"]:
        return False, "El plano está vacío: armalo con «⚡ Armado rápido» o dibujalo.", []
    perdidas = lo_que_se_pierde_con(piso_id, texto)
    if perdidas and not aunque_se_pierdan:
        return False, ("Así quedarían productos fuera del mapa: "
                       + "; ".join(f"la {cod} ({n} producto(s)) {por_que}"
                                   for cod, n, por_que in perdidas)
                       + ". Movelos antes, o guardalo igual."), perdidas
    limpio = "\n".join(plano["filas"])
    antes = estanterias_del_piso(piso_id)
    with db_lock, transaccion():
        c.execute("SELECT plano FROM pisos WHERE id = ?", (piso_id,))
        fila = c.fetchone()
        if fila is None:
            return False, "Ese piso ya no existe.", []
        c.execute("UPDATE pisos SET plano = ? WHERE id = ?", (limpio, piso_id))
        for letra, e in antes.items():
            if letra not in plano["estanterias"]:
                c.execute("DELETE FROM estanterias WHERE id = ?", (e["id"],))
        for letra in plano["estanterias"]:
            if letra not in antes:
                c.execute("INSERT INTO estanterias (piso_id, letra, codigo) VALUES (?, ?, ?)",
                          (piso_id, letra, _codigo_libre(letra)))
        anotar_cambio("cambió el plano", "piso", piso_id, antes={"plano": fila["plano"]},
                      despues={"plano": limpio})
    nuevas = [l_ for l_ in plano["estanterias"] if l_ not in antes]
    sacadas = [l_ for l_ in antes if l_ not in plano["estanterias"]]
    return True, ("💾 Plano guardado"
                  + (f": {len(nuevas)} estantería(s) nueva(s)" if nuevas else "")
                  + (f", {len(sacadas)} sacada(s)" if sacadas else "") + "."), perdidas


def guardar_estanteria(estanteria_id, codigo, niveles):
    """Cambia el código o los estantes de una estantería. Si cambia el código, los productos
    ubicados ahí pasan al código nuevo («A-3-2» → «X-3-2»), todo junto. (ok, texto)."""
    exigir_nivel("empleado", "armar el depósito")
    codigo = str(codigo or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{1,6}", codigo):
        return False, "El código va con letras y números, sin espacios ni guiones (hasta 6)."
    if re.fullmatch(rf"{PREFIJO_DEL_CODIGO_NUESTRO}\d.*", codigo):
        return False, (f"Un código que empieza con {PREFIJO_DEL_CODIGO_NUESTRO} y un número se "
                       "confunde con la etiqueta de un producto: elegí otro.")
    try:
        niveles = int(niveles)
    except (TypeError, ValueError):
        return False, "Los estantes tienen que ser un número."
    if not 1 <= niveles <= 20:
        return False, "Una estantería tiene de 1 a 20 estantes."
    c.execute("SELECT codigo, niveles FROM estanterias WHERE id = ?", (estanteria_id,))
    fila = c.fetchone()
    if fila is None:
        return False, "Esa estantería ya no está."
    viejo = fila["codigo"]
    adentro = productos_en(viejo) if viejo.upper() != codigo else []
    with db_lock, transaccion():
        try:
            c.execute("UPDATE estanterias SET codigo = ?, niveles = ? WHERE id = ?",
                      (codigo, niveles, estanteria_id))
        except sqlite3.IntegrityError:
            return False, f"Ya hay otra estantería con el código {codigo}."
        for p in adentro:
            c.execute("UPDATE productos SET ubicacion = ? WHERE id = ?",
                      (texto_de_ubicacion(codigo, p["modulo"], p["nivel"]), p["id"]))
        anotar_cambio("cambió una estantería", "estanteria", estanteria_id,
                      antes={"codigo": viejo, "niveles": fila["niveles"]},
                      despues={"codigo": codigo, "niveles": niveles},
                      detalle=f"{len(adentro)} producto(s) pasaron al código nuevo" if adentro else "")
    return True, (f"💾 Estantería {codigo}: {niveles} estante(s)"
                  + (f"; {len(adentro)} producto(s) pasaron de {viejo} a {codigo}." if adentro
                     else "."))


# Cómo ordena la cola cada piso. Ver «LA COLA POR PISO».
ORDENES_DE_LA_COLA = {"ubicacion": "📍 Por ubicación (A, B, C…)",
                      "cercania": "🧭 El más cerca del último que se entregó"}


def elegir_orden_de_la_cola(piso_id, modo, minutos=1):
    """Cómo ordena la cola ese piso, para todos los del depósito. (ok, texto)."""
    exigir_nivel("empleado", "elegir cómo se ordena la cola")
    if modo not in ORDENES_DE_LA_COLA:
        return False, "Ese orden no existe."
    try:
        minutos = float(minutos)
    except (TypeError, ValueError):
        return False, "Los minutos tienen que ser un número."
    if not 0.25 <= minutos <= 120:
        return False, "Entre un cuarto de minuto y dos horas."
    with db_lock:
        c.execute("UPDATE pisos SET orden_de_la_cola = ?, minutos_de_cercania = ? WHERE id = ?",
                  (modo, minutos, piso_id))
        conn.commit()
    return True, f"Ordenado: {ORDENES_DE_LA_COLA[modo]}."


# ============================================================================================
# ARMAR EL PLANO SIN DIBUJAR
# ============================================================================================
# Dibujar con letras es lo más flexible, pero no lo primero que se le ocurre a nadie. Para
# arrancar, «⚡ Armado rápido»: cuántas filas de estanterías, cuántas por fila, de cuántos
# módulos y qué tan ancho el pasillo, y sale el plano entero. Después se retoca: sumar una
# estantería en una columna y una fila (las del dibujo, que tiene los números al costado),
# moverla o sacarla. Todo devuelve el texto nuevo del plano: se ve en el dibujo antes de
# guardarlo.
def armado_rapido(hileras=3, por_hilera=2, modulos=5, pasillo=1, fondo=1):
    """Un plano con `hileras` filas de `por_hilera` estanterías de `modulos` módulos (y `fondo`
    casilleros de fondo), pasillos de `pasillo` de ancho entre todas, paredes alrededor y la
    entrada abajo en el medio. Las letras, de la A en adelante, de izquierda a derecha y de
    arriba a abajo. ValueError si no entra."""
    hileras, por_hilera, modulos = int(hileras), int(por_hilera), int(modulos)
    pasillo, fondo = int(pasillo), int(fondo)
    if min(hileras, por_hilera, modulos, pasillo, fondo) < 1:
        raise ValueError("Todo tiene que ser por lo menos 1.")
    if hileras * por_hilera > len(LETRAS_DE_ESTANTERIA):
        raise ValueError(f"Hasta {len(LETRAS_DE_ESTANTERIA)} estanterías por piso.")
    ancho = 2 + pasillo + por_hilera * (modulos + pasillo)
    alto = 2 + pasillo + hileras * (fondo + pasillo)
    max_ancho, max_alto = TAMANO_MAXIMO_DEL_PLANO
    if ancho > max_ancho or alto > max_alto:
        raise ValueError(f"Así queda de {ancho} × {alto} casilleros, y entran hasta "
                         f"{max_ancho} × {max_alto}: probá con menos módulos o menos filas.")
    grilla = [[PASILLO] * ancho for _ in range(alto)]
    for x in range(ancho):
        grilla[0][x] = grilla[-1][x] = PARED
    for y in range(alto):
        grilla[y][0] = grilla[y][-1] = PARED
    letras = iter(LETRAS_DE_ESTANTERIA)
    for h in range(hileras):
        y0 = 1 + pasillo + h * (fondo + pasillo)
        for e in range(por_hilera):
            x0 = 1 + pasillo + e * (modulos + pasillo)
            letra = next(letras)
            for y in range(y0, y0 + fondo):
                for x in range(x0, x0 + modulos):
                    grilla[y][x] = letra
    grilla[-1][ancho // 2] = ENTRADA
    return "\n".join("".join(f) for f in grilla)


def _grilla(texto):
    return [list(f) for f in leer_plano(texto)["filas"]]


def sumar_estanteria(texto, columna, fila, largo, acostada=True, fondo=1, letra=None):
    """Pone una estantería de `largo` módulos y `fondo` de fondo con la esquina de arriba a la
    izquierda en esa columna y fila (contando desde 1, como en el dibujo). Si se pasa del borde,
    el plano se agranda. Sin letra, la primera libre. (texto nuevo, letra); ValueError si choca
    con otra cosa."""
    grilla = _grilla(texto)
    usadas = {ch for f in grilla for ch in f if ch in LETRAS_DE_ESTANTERIA}
    letra = (str(letra or "").strip().upper()
             or next((l_ for l_ in LETRAS_DE_ESTANTERIA if l_ not in usadas), ""))
    if not letra or letra not in LETRAS_DE_ESTANTERIA:
        raise ValueError("No quedan letras libres en este piso." if not letra else
                         "La estantería va con una letra (A–Z) o un número (1–9).")
    if letra in usadas:
        raise ValueError(f"Ya hay una {letra} en este piso.")
    x0, y0, largo, fondo = int(columna) - 1, int(fila) - 1, int(largo), int(fondo)
    if x0 < 0 or y0 < 0 or largo < 1 or fondo < 1:
        raise ValueError("La columna, la fila, el largo y el fondo empiezan en 1.")
    ancho_e, alto_e = (largo, fondo) if acostada else (fondo, largo)
    nuevo_ancho = max(len(grilla[0]) if grilla else 0, x0 + ancho_e)
    nuevo_alto = max(len(grilla), y0 + alto_e)
    max_ancho, max_alto = TAMANO_MAXIMO_DEL_PLANO
    if nuevo_ancho > max_ancho or nuevo_alto > max_alto:
        raise ValueError(f"No entra: el plano llega hasta {max_ancho} × {max_alto}.")
    grilla = [f + [PASILLO] * (nuevo_ancho - len(f)) for f in grilla]
    grilla += [[PASILLO] * nuevo_ancho for _ in range(nuevo_alto - len(grilla))]
    for y in range(y0, y0 + alto_e):
        for x in range(x0, x0 + ancho_e):
            if grilla[y][x] != PASILLO:
                que = {PARED: "una pared", ENTRADA: "la entrada"}.get(grilla[y][x],
                                                                      f"la {grilla[y][x]}")
                raise ValueError(f"Choca con {que} en la columna {x + 1}, fila {y + 1}.")
            grilla[y][x] = letra
    return "\n".join("".join(f) for f in grilla), letra


def sacar_estanteria(texto, letra):
    """El plano sin esa estantería (queda pasillo)."""
    letra = str(letra or "").upper()
    return "\n".join(f.replace(letra, PASILLO) if letra else f
                     for f in leer_plano(texto)["filas"])


def mover_estanteria(texto, letra, columnas=0, filas=0):
    """La estantería corrida `columnas` a la derecha (negativo: a la izquierda) y `filas` para
    abajo (negativo: para arriba). Texto nuevo; ValueError si se sale o choca."""
    letra = str(letra or "").upper()
    grilla = _grilla(texto)
    celdas = [(x, y) for y, f in enumerate(grilla) for x, ch in enumerate(f) if ch == letra]
    if not celdas:
        raise ValueError(f"No hay ninguna {letra} en este piso.")
    for x, y in celdas:
        grilla[y][x] = PASILLO
    for x, y in celdas:
        nx, ny = x + int(columnas), y + int(filas)
        if not (0 <= ny < len(grilla) and 0 <= nx < len(grilla[ny])):
            raise ValueError("Así se sale del plano.")
        if grilla[ny][nx] != PASILLO:
            raise ValueError(f"Así choca en la columna {nx + 1}, fila {ny + 1}.")
        grilla[ny][nx] = letra
    return "\n".join("".join(f) for f in grilla)


# ============================================================================================
# DÓNDE ESTÁ CADA COSA
# ============================================================================================
# La ubicación de un producto es el texto de siempre (productos.ubicacion), escrito como en el
# mapa: «A-3-2» (estantería, módulo, estante), o «A-3», o «A». Se acepta como lo escriba
# cualquiera o lo mande el lector («a 3 2», «A/3/2»), y se guarda siempre igual. Con el mapa
# armado, a un producto solo se le pone un lugar que exista: un «A-9» en una A de 5 módulos es
# un error de tipeo, y el que va a buscar no lo encuentra.
_PATRON_DE_UBICACION = re.compile(
    r"\s*([A-Za-z0-9]{1,6})(?:\s*[-/ ]\s*(\d{1,3}))?(?:\s*[-/ ]\s*(\d{1,2}))?\s*")


def leer_ubicacion(texto):
    """(código de la estantería, módulo o None, estante o None) si `texto` se escribe como una
    ubicación del mapa; si no, None. No mira si la estantería existe (ver lugar_en_el_mapa())."""
    m = _PATRON_DE_UBICACION.fullmatch(str(texto or ""))
    if not m:
        return None
    modulo = int(m.group(2)) if m.group(2) else None
    nivel = int(m.group(3)) if m.group(3) else None
    if modulo == 0 or nivel == 0:
        return None
    return m.group(1).upper(), modulo, nivel


def texto_de_ubicacion(codigo, modulo=None, nivel=None):
    """«A-3-2», «A-3» o «A»: como se guarda una ubicación del mapa."""
    return "-".join(str(p) for p in (codigo, modulo, nivel) if p)


def lugar_en_el_mapa(texto):
    """Dónde queda en el mapa una ubicación escrita: dict con el depósito, el piso (y su plano),
    la estantería, el módulo, el estante, las celdas para resaltar, cómo se guarda («A-3-2») y
    cómo se lee («Central · Planta baja · estantería A, módulo 3, estante 2»). None si no es un
    lugar del mapa (o el módulo o el estante no existen)."""
    leida = leer_ubicacion(texto)
    if not leida:
        return None
    codigo, modulo, nivel = leida
    c.execute("""SELECT e.id, e.letra, e.codigo, e.niveles, p.id AS piso_id, p.nombre AS piso,
                        p.plano, d.id AS deposito_id, d.nombre AS deposito
                 FROM estanterias e JOIN pisos p ON p.id = e.piso_id
                 JOIN depositos d ON d.id = p.deposito_id
                 WHERE e.codigo = ?""", (codigo,))
    f = c.fetchone()
    if not f:
        return None
    estanteria = leer_plano(f["plano"])["estanterias"].get(f["letra"])
    if (not estanteria or (modulo and modulo > len(estanteria["modulos"]))
            or (nivel and nivel > (f["niveles"] or 1))):
        return None
    detalle = f"estantería {f['codigo']}" + (f", módulo {modulo}" if modulo else "") + (
        f", estante {nivel} (desde abajo)" if nivel else "")
    return {"deposito": f["deposito"], "deposito_id": f["deposito_id"], "piso": f["piso"],
            "piso_id": f["piso_id"], "plano": f["plano"], "estanteria_id": f["id"],
            "codigo": f["codigo"], "letra": f["letra"], "modulo": modulo, "nivel": nivel,
            "niveles": f["niveles"], "modulos": len(estanteria["modulos"]),
            "celdas": estanteria["modulos"][modulo - 1] if modulo else estanteria["celdas"],
            "texto": texto_de_ubicacion(f["codigo"], modulo, nivel),
            "se_lee": f"{f['deposito']} · {f['piso']} · {detalle}"}


def ubicar_producto(producto_id, texto, motivo="ubicado"):
    """Le pone lugar a un producto (vacío: se lo saca). Con el mapa armado tiene que ser un
    lugar del mapa, y se guarda escrito como en el mapa; sin mapa, cualquier texto, como
    siempre. Queda en el historial de la ficha. (ok, texto)."""
    exigir_nivel("empleado", "cambiar dónde está un producto")
    texto = " ".join(str(texto or "").split())
    donde = lugar_en_el_mapa(texto) if texto else None
    if texto and not donde and hay_mapa():
        return False, (f"«{texto}» no es un lugar del mapa. Se escribe estantería-módulo-estante "
                       "(«A-3-2»), y tiene que existir en «🏗️ Armar el depósito».")
    nuevo = donde["texto"] if donde else (texto or None)
    with db_lock, transaccion():
        c.execute("""SELECT p.ubicacion, p.codigo_raw, m.nombre AS marca FROM productos p
                     JOIN marcas m ON m.id = p.marca_id WHERE p.id = ?""", (producto_id,))
        f = c.fetchone()
        if f is None:
            return False, "Ese producto ya no está en el catálogo."
        if (f["ubicacion"] or None) != nuevo:
            c.execute("UPDATE productos SET ubicacion = ? WHERE id = ?", (nuevo, producto_id))
            c.execute("""INSERT INTO historial_de_medidas (producto_id, campo, antes, despues,
                                                           usuario, motivo)
                         VALUES (?, 'ubicacion', ?, ?, ?, ?)""",
                      (producto_id, f["ubicacion"] or None, nuevo, obtener_usuario_actual(),
                       motivo))
    return True, (f"📍 {f['marca']} {f['codigo_raw']} → "
                  + (donde["se_lee"] if donde else (nuevo or "sin lugar")))


def que_es_lo_escaneado_al_ubicar(texto):
    """Lo que se escaneó (o escribió) en «📍 Ubicar»: ("lugar", lugar_en_el_mapa()), ("producto",
    id) o (None, por qué no). Primero la etiqueta nuestra y el código de barras de la caja, que
    no se confunden con nada; después un lugar del mapa; y por último el código de fábrica, si es
    de un solo producto."""
    texto = str(texto or "").strip()
    if not texto:
        return None, ""
    producto_id = producto_por_codigo_nuestro(texto) or producto_por_codigo_de_barras(texto)
    if producto_id:
        return "producto", producto_id
    donde = lugar_en_el_mapa(texto)
    if donde:
        return "lugar", donde
    limpio = sanitizar(texto)
    if limpio:
        c.execute("SELECT id FROM productos WHERE codigo_clean = ? LIMIT 3", (limpio,))
        ids = [r["id"] for r in c.fetchall()]
        if len(ids) == 1:
            return "producto", ids[0]
        if ids:
            return None, (f"Hay más de un producto con el código {texto} (de distintas marcas): "
                          "escaneá la etiqueta nuestra o el código de barras de la caja.")
    return None, f"«{texto}» no es un lugar del mapa ni un producto."


def ubicar_de_una_lista(texto, guardar=False):
    """«📋 Pegar una lista»: un renglón por producto, el código y al final el lugar («W712
    A-3-2»; también separado por tabulación, coma o punto y coma, como sale de Excel). Devuelve
    [dict] con cada renglón, el producto, el lugar y el problema si lo hay; con `guardar`,
    además ubica los que están bien (los que tienen problema, no)."""
    salida = []
    for n, renglon in enumerate(str(texto or "").splitlines(), start=1):
        partes = re.split(r"[\t;,]+|\s+", renglon.strip())
        partes = [p for p in partes if p]
        if not partes:
            continue
        fila = {"Renglón": n, "Producto": "", "Lugar": "", "Problema": "", "_id": None,
                "_lugar": None}
        if len(partes) < 2:
            fila["Problema"] = "Falta el lugar (va al final del renglón)."
            salida.append(fila)
            continue
        que, valor = que_es_lo_escaneado_al_ubicar(" ".join(partes[:-1]))
        donde = lugar_en_el_mapa(partes[-1])
        if que != "producto":
            fila["Problema"] = valor if que is None else "Eso es un lugar, no un producto."
        elif not donde and hay_mapa():
            fila["Problema"] = f"«{partes[-1]}» no es un lugar del mapa."
        if que == "producto":
            c.execute("""SELECT p.codigo_raw, m.nombre AS marca FROM productos p
                         JOIN marcas m ON m.id = p.marca_id WHERE p.id = ?""", (valor,))
            f = c.fetchone()
            fila.update(Producto=f"{f['marca']} {f['codigo_raw']}", _id=valor)
        fila.update(Lugar=donde["texto"] if donde else partes[-1], _lugar=partes[-1])
        salida.append(fila)
    if guardar:
        for fila in salida:
            if not fila["Problema"]:
                ok, texto_ok = ubicar_producto(fila["_id"], fila["_lugar"])
                fila["Problema"] = "" if ok else texto_ok
                fila["Guardado"] = "✅" if ok else ""
    return salida


def pdf_de_etiquetas_de_ubicaciones(estanteria_ids):
    """Las etiquetas para pegar en cada estante: una por módulo y estante de esas estanterías,
    con el código de barras del lugar («A-3-2»). Escaneando la del estante y después lo que hay
    en él, «📍 Ubicar» pone todo en su lugar. b"" si no hay nada."""
    etiquetas = []
    for estanteria_id in estanteria_ids:
        c.execute("SELECT codigo FROM estanterias WHERE id = ?", (estanteria_id,))
        f = c.fetchone()
        donde = lugar_en_el_mapa(f["codigo"]) if f else None
        if not donde:
            continue
        for modulo in range(1, donde["modulos"] + 1):
            for nivel in range(1, (donde["niveles"] or 1) + 1):
                lugar = texto_de_ubicacion(donde["codigo"], modulo, nivel)
                etiquetas.append({"titulo": lugar,
                                  "detalle": f"{donde['deposito']} - {donde['piso']} - "
                                             f"modulo {modulo}, estante {nivel}",
                                  "barras": lugar})
    return pdf_de_etiquetas_con_barras(etiquetas)


def etiquetas_de_ubicaciones_para_descargar(estanteria_ids):
    """Para el botón de descarga: el PDF se arma al tocarlo (ver comprobante_para_descargar())."""
    ids = [int(i) for i in estanteria_ids]
    return lambda: pdf_de_etiquetas_de_ubicaciones(ids)


# Qué estante es más cómodo: el 2 y el 3 (a la altura de la cintura y el pecho), después el 1
# (el del piso) y después los de arriba, cada vez peor. Ver lugares_sugeridos().
def _incomodidad(nivel):
    return {1: 3, 2: 0, 3: 1}.get(nivel, 2 * nivel - 4)


def lugares_sugeridos(tope=15):
    """Dónde poner lo que no tiene lugar en el mapa: lo que más se vende (y si no, lo que tiene
    stock o más se busca), en los lugares libres más a mano —cerca de la entrada y a la altura
    de la cintura—, como la matriz ABC. Primero el primer depósito y su planta baja: un estante
    cerca de la entrada del primer piso no está más a mano que uno de abajo, porque antes hay que
    subir. [dict] con el producto, por qué va primero y el lugar sugerido. Es una sugerencia:
    hay que llevarlo ahí y confirmarlo."""
    ocupados = set()
    c.execute("SELECT ubicacion FROM productos WHERE ubicacion IS NOT NULL AND TRIM(ubicacion) <> ''")
    for r in c.fetchall():
        leida = leer_ubicacion(r["ubicacion"])
        if leida:
            ocupados.add(leida)
    libres = []
    for n_dep, dep in enumerate(depositos_y_pisos()):
        for n_piso, piso in enumerate(dep["pisos"]):
            plano = leer_plano(piso["plano"])
            if not plano["estanterias"]:
                continue
            arranque = _punto_de_partida(plano)
            for letra, e in estanterias_del_piso(piso["id"]).items():
                est = plano["estanterias"].get(letra)
                if not est:
                    continue
                for m, celdas in enumerate(est["modulos"], start=1):
                    pasos = _pasos_hasta(piso["plano"], arranque, celdas)[0]
                    for n in range(1, (e["niveles"] or 1) + 1):
                        if (e["codigo"].upper(), m, n) not in ocupados:
                            libres.append((n_dep, n_piso, pasos + 4 * _incomodidad(n),
                                           texto_de_ubicacion(e["codigo"], m, n), dep["nombre"]))
    if not libres:
        return []
    libres.sort()
    c.execute("""SELECT p.id, p.codigo_raw, p.descripcion, p.stock, p.ubicacion,
                        m.nombre AS marca, COALESCE(p.veces_buscado, 0) AS buscado,
                        (SELECT COUNT(*) FROM ventas_registradas v WHERE v.producto_id = p.id
                           AND v.fecha >= datetime('now', '-180 days')) AS vendidos
                 FROM productos p JOIN marcas m ON m.id = p.marca_id
                 WHERE COALESCE(p.stock, 0) > 0
                    OR p.id IN (SELECT producto_id FROM ventas_registradas
                                WHERE fecha >= datetime('now', '-180 days'))
                 ORDER BY vendidos DESC, buscado DESC, COALESCE(p.stock, 0) DESC, p.id
                 LIMIT ?""", (int(tope) * 20,))
    candidatos = [dict(r) for r in c.fetchall()]
    sin_lugar = [r for r in candidatos if not lugar_en_el_mapa(r["ubicacion"])][:int(tope)]
    salida = []
    for r, (_, _, _, lugar, deposito) in zip(sin_lugar, libres):
        salida.append({"producto_id": r["id"], "producto": f"{r['marca']} {r['codigo_raw']}",
                       "descripcion": (r["descripcion"] or "")[:40],
                       "por_que": (f"se vendió {r['vendidos']} vez/veces en 6 meses"
                                   if r["vendidos"] else
                                   f"tiene {miles(r['stock'] or 0)} en stock"),
                       "lugar": lugar, "deposito": deposito})
    return salida


# ============================================================================================
# LA COLA POR PISO
# ============================================================================================
# Lo pidió el dueño: «que se pueda seleccionar en cada piso/depósito que te los acomode por
# orden de ubicación, o porque sea el que queda más cerca del último pedido realizado en un
# determinado tiempo, por ejemplo 1 minuto». Cada piso elige el suyo (vale para todos los del
# depósito, ver elegir_orden_de_la_cola()):
#   · 📍 POR UBICACIÓN: A-1, A-2… B-1…: siempre igual, fácil de seguir con la vista.
#   · 🧭 EL MÁS CERCA DEL ÚLTIMO: si lo último que entregaste en ese piso fue hace menos de esos
#     minutos, seguís parado ahí: arranca por lo que tenés más cerca caminando, y después lo
#     más cerca de eso, y así. Si pasó más tiempo, volviste al mostrador: arranca desde la
#     entrada. Es de cada uno: dos chicos buscando a la vez no se pisan el «último».
# Lo que no tiene lugar en el mapa va aparte, al final, por lo que tenga escrito.
def _lo_ultimo_que_entrego(usuario, minutos):
    """Lo último que entregó `usuario` en los últimos `minutos`: (lugar_en_el_mapa(), hace cuántos
    segundos) o None. Solo lo ÚLTIMO: si fue en otro piso o sin lugar, en este se arranca de la
    entrada."""
    desde = (datetime.now() - timedelta(minutes=float(minutos))).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""SELECT d.resuelto_en, p.ubicacion FROM pedidos_deposito d
                 JOIN productos p ON p.id = d.producto_id
                 WHERE d.estado = 'entregado' AND d.resuelto_por = ? AND d.resuelto_en >= ?
                 ORDER BY d.resuelto_en DESC, d.id DESC LIMIT 1""", (usuario, desde))
    f = c.fetchone()
    if not f:
        return None
    donde = lugar_en_el_mapa(f["ubicacion"])
    if not donde:
        return None
    hace = (datetime.now() - datetime.strptime(f["resuelto_en"][:19], "%Y-%m-%d %H:%M:%S"))
    return donde, max(0, int(hace.total_seconds()))


def la_cola_por_piso(pendientes, usuario=None):
    """La cola del depósito partida por piso, cada uno en su orden: [dict] con el depósito, el
    piso, cómo ordena, desde dónde arranca, sus pedidos en orden (cada uno con «donde» y su
    número de «paso»), el camino y los pasos en total. Al final, si hay, lo que no tiene lugar
    en el mapa (piso_id None), por lo que tenga escrito."""
    usuario = usuario or obtener_usuario_actual()
    por_piso, sin_lugar = {}, []
    for p in pendientes:
        donde = lugar_en_el_mapa(p.get("ubicacion"))
        p = dict(p, donde=donde)
        if donde:
            por_piso.setdefault(donde["piso_id"], []).append(p)
        else:
            sin_lugar.append(p)
    pisos = {piso["id"]: piso for dep in depositos_y_pisos() for piso in dep["pisos"]}
    orden_de_los_pisos = list(pisos)
    grupos = []
    for piso_id in sorted(por_piso, key=lambda i: orden_de_los_pisos.index(i)
                          if i in orden_de_los_pisos else 0):
        piso, items = pisos[piso_id], por_piso[piso_id]
        modo = piso["orden_de_la_cola"] if piso["orden_de_la_cola"] in ORDENES_DE_LA_COLA else "ubicacion"
        desde, desde_texto = None, "desde la entrada"
        if modo == "cercania":
            ultimo = _lo_ultimo_que_entrego(usuario, piso["minutos_de_cercania"])
            if ultimo and ultimo[0]["piso_id"] == piso_id:
                desde = ultimo[0]["celdas"]
                desde_texto = (f"desde {ultimo[0]['texto']}, lo último que entregaste (hace "
                               f"{ultimo[1]} s)")
        else:
            items = sorted(items, key=lambda i: (clave_de_ubicacion(i["donde"]["texto"]),
                                                 i.get("pedido_en") or ""))
        orden, camino, total = planear_el_recorrido(piso["plano"],
                                                    [i["donde"]["celdas"] for i in items],
                                                    desde, por_cercania=modo == "cercania")
        items = [dict(items[i], paso=n) for n, i in enumerate(orden, start=1)]
        grupos.append({"piso_id": piso_id, "piso": piso["nombre"], "deposito": piso["deposito"],
                       "plano": piso["plano"], "modo": modo,
                       "minutos": piso["minutos_de_cercania"], "desde": desde_texto,
                       "items": items, "camino": camino, "pasos": total})
    if sin_lugar:
        sin_lugar.sort(key=lambda i: (not i.get("ubicacion"), clave_de_ubicacion(i.get("ubicacion")),
                                      i.get("pedido_en") or ""))
        grupos.append({"piso_id": None, "piso": "Sin lugar en el mapa", "deposito": "",
                       "plano": "", "modo": "ubicacion", "minutos": 0, "desde": "",
                       "items": [dict(i, paso=n) for n, i in enumerate(sin_lugar, start=1)],
                       "camino": [], "pasos": 0})
    return grupos


# ============================================================================================
# EL DIBUJO DEL PISO
# ============================================================================================
# Un SVG hecho a mano, sin librerías: el pasillo, las paredes, la entrada, cada estantería con
# sus módulos y su código, lo que hay que buscar resaltado con su número, y el recorrido.
# Los números de las columnas y las filas van al costado: son los de «➕ Sumar una estantería».
LEYENDA_DEL_MAPA = ("🟧 lo que hay que buscar (el número es el orden) · 🔵 por dónde ir · "
                    "ENT la entrada · los números del costado son las columnas y las filas")
COLORES_DEL_MAPA = {"fondo": "#1D2126", "pasillo": "#242830", "pared": "#4A4F57",
                    "estanteria": "#3A3F47", "borde": "#6B7380", "texto": "#ECEEF0",
                    "apagado": "#9BA3AC", "resaltado": "#E8A33D", "camino": "#4C8BF5",
                    "entrada": "#3FA34D"}


def svg_del_piso(plano_texto, codigos=None, resaltados=(), camino=(), celda=26):
    """El dibujo de un piso como texto SVG, para st.markdown(..., unsafe_allow_html=True).
    `codigos`: {letra: código de la estantería} (sin eso, la letra); `resaltados`: [(celdas,
    rótulo)] —lo que hay que buscar, con su número—; `camino`: las celdas del recorrido."""
    plano = leer_plano(plano_texto)
    if not plano["filas"]:
        return ""
    k = COLORES_DEL_MAPA
    codigos = codigos or {}
    margen = 18
    ancho, alto = margen + plano["ancho"] * celda + 2, margen + plano["alto"] * celda + 2

    def caja(x, y, w=1, h=1):
        return f'x="{margen + x * celda}" y="{margen + y * celda}" width="{w * celda}" height="{h * celda}"'

    def centro(x, y):
        return margen + x * celda + celda / 2, margen + y * celda + celda / 2

    partes = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho} {alto}" '
              f'style="width:100%;max-width:{ancho}px;height:auto;display:block" role="img" '
              f'aria-label="Plano del piso">',
              f'<rect x="0" y="0" width="{ancho}" height="{alto}" rx="8" style="fill:{k["fondo"]}"/>',
              f'<rect {caja(0, 0, plano["ancho"], plano["alto"])} style="fill:{k["pasillo"]}"/>']
    tamano_numero = max(8, int(celda * 0.38))
    for x in range(plano["ancho"]):
        if x == 0 or (x + 1) % 5 == 0:
            partes.append(f'<text x="{centro(x, 0)[0]:.0f}" y="{margen - 5}" text-anchor="middle" '
                          f'style="fill:{k["apagado"]};font-size:{tamano_numero}px">{x + 1}</text>')
    for y in range(plano["alto"]):
        if y == 0 or (y + 1) % 5 == 0:
            partes.append(f'<text x="{margen - 4}" y="{centro(0, y)[1] + 4:.0f}" text-anchor="end" '
                          f'style="fill:{k["apagado"]};font-size:{tamano_numero}px">{y + 1}</text>')
    for y, fila in enumerate(plano["filas"]):
        for x, ch in enumerate(fila):
            if ch == PARED:
                partes.append(f'<rect {caja(x, y)} style="fill:{k["pared"]}"/>')
            elif ch == ENTRADA:
                cx, cy = centro(x, y)
                partes.append(f'<rect {caja(x, y)} rx="4" style="fill:{k["entrada"]}"/>'
                              f'<text x="{cx:.0f}" y="{cy + tamano_numero / 2.6:.0f}" '
                              f'text-anchor="middle" style="fill:#fff;font-weight:700;'
                              f'font-size:{tamano_numero}px">ENT</text>')
    # Primero las estanterías, el recorrido y lo resaltado; las letras y los números, al final,
    # encima de todo: un módulo resaltado en el medio de la estantería tapaba su letra.
    letras = []
    for letra, e in plano["estanterias"].items():
        x0, y0, x1, y1 = e["caja"]
        partes.append(f'<rect {caja(x0, y0, x1 - x0 + 1, y1 - y0 + 1)} rx="3" '
                      f'style="fill:{k["estanteria"]};stroke:{k["borde"]};stroke-width:1.5"/>')
        for modulo in e["modulos"][1:]:
            mx, my = modulo[0]
            if e["acostada"]:
                partes.append(f'<line x1="{margen + mx * celda}" y1="{margen + y0 * celda + 3}" '
                              f'x2="{margen + mx * celda}" y2="{margen + (y1 + 1) * celda - 3}" '
                              f'style="stroke:{k["borde"]};stroke-width:1;opacity:.6"/>')
            else:
                partes.append(f'<line x1="{margen + x0 * celda + 3}" y1="{margen + my * celda}" '
                              f'x2="{margen + (x1 + 1) * celda - 3}" y2="{margen + my * celda}" '
                              f'style="stroke:{k["borde"]};stroke-width:1;opacity:.6"/>')
        cx = margen + (x0 + x1 + 1) * celda / 2
        cy = margen + (y0 + y1 + 1) * celda / 2
        letras.append(f'<text x="{cx:.0f}" y="{cy + celda * 0.2:.0f}" text-anchor="middle" '
                      f'style="fill:{k["texto"]};font-weight:700;font-size:{int(celda * 0.6)}px;'
                      f'paint-order:stroke;stroke:{k["fondo"]};stroke-width:3px">'
                      f'{html.escape(codigos.get(letra, letra))}</text>')
    if len(camino) > 1:
        puntos = " ".join(f"{centro(x, y)[0]:.0f},{centro(x, y)[1]:.0f}" for x, y in camino)
        partes.append(f'<polyline points="{puntos}" style="fill:none;stroke:{k["camino"]};'
                      f'stroke-width:3;stroke-dasharray:6 4;stroke-linecap:round;'
                      f'stroke-linejoin:round;opacity:.9"/>')
    # LO RESALTADO: el módulo entero pintado, con un borde que titila para encontrarlo de un
    # vistazo, y su número en una burbuja arriba, que no tapa la letra de la estantería.
    burbujas = []
    for celdas, rotulo in resaltados:
        if not celdas:
            continue
        xs, ys = [x for x, _ in celdas], [y for _, y in celdas]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        partes.append(f'<rect {caja(x0, y0, x1 - x0 + 1, y1 - y0 + 1)} rx="3" '
                      f'style="fill:{k["resaltado"]};stroke:#F2B658;stroke-width:2"/>'
                      f'<rect x="{margen + x0 * celda - 3}" y="{margen + y0 * celda - 3}" '
                      f'width="{(x1 - x0 + 1) * celda + 6}" height="{(y1 - y0 + 1) * celda + 6}" '
                      f'rx="5" style="fill:none;stroke:{k["resaltado"]};stroke-width:2.5">'
                      f'<animate attributeName="stroke-opacity" values="1;0.15;1" dur="1.4s" '
                      f'repeatCount="indefinite"/></rect>')
        cx = margen + (x0 + x1 + 1) * celda / 2
        arriba = margen + y0 * celda - celda * 0.05
        texto = html.escape(str(rotulo))
        radio = celda * (0.38 if len(texto) <= 2 else 0.5)
        burbujas.append(f'<circle cx="{cx:.0f}" cy="{arriba:.0f}" r="{radio:.0f}" '
                        f'style="fill:#14171B;stroke:#F2B658;stroke-width:2"/>'
                        f'<text x="{cx:.0f}" y="{arriba + celda * 0.15:.0f}" text-anchor="middle" '
                        f'style="fill:#F2B658;font-weight:700;font-size:{int(celda * 0.42)}px">'
                        f'{texto}</text>')
    partes += letras + burbujas
    partes.append("</svg>")
    return "".join(partes)

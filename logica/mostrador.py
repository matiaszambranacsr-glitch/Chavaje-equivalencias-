"""Lo del mostrador: motor y patente, consultas de clientes, stock, precios, fusionar duplicados.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================================================
# BÚSQUEDA POR NÚMERO DE MOTOR Y POR PATENTE
# ============================================================================================
def normalizar_numero_motor(texto):
    """Deja el número de motor comparable: sin espacios, guiones ni minúsculas.

    Los graban distinto según quién los copie: «4G15-AB1234», «4G15 AB 1234», «4g15ab1234».
    Sin normalizar, el mismo motor no se encuentra a sí mismo."""
    if not texto:
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(texto).upper())


# Caracteres que se confunden al leer un número grabado en el block. No es teoría: están
# estampados en metal, con grasa encima, muchas veces gastados, y se leen agachado con linterna.
_CONFUSIONES_MOTOR = [("0", "O"), ("0", "D"), ("1", "I"), ("1", "L"), ("5", "S"),
                      ("8", "B"), ("2", "Z"), ("6", "G"), ("4", "A"), ("7", "T")]


def variantes_numero_motor(numero, tope=40):
    """Las formas en que ese número pudo haberse leído mal. Devuelve una lista.

    Se cambia UN carácter por vez, no varios: con dos cambios simultáneos el número de
    combinaciones explota y empieza a coincidir con motores que no tienen nada que ver."""
    base = normalizar_numero_motor(numero)
    if len(base) < 4:
        return []
    salida = []
    for i, ch in enumerate(base):
        for a, b in _CONFUSIONES_MOTOR:
            otro = b if ch == a else (a if ch == b else None)
            if otro:
                v = base[:i] + otro + base[i+1:]
                if v not in salida:
                    salida.append(v)
        if len(salida) >= tope:
            break
    return salida[:tope]


def buscar_por_numero_motor(numero):
    """Busca vehículos por el número de motor. Devuelve (fichas, parciales).

    Se devuelven aparte las coincidencias PARCIALES porque el número de motor casi nunca se
    lee entero: está grabado en el block, con grasa encima y en una posición incómoda. Que
    coincidan los últimos 6 caracteres ya es una pista fuerte, pero no es lo mismo que una
    coincidencia exacta y no hay que mezclarlas."""
    limpio = normalizar_numero_motor(numero)
    if len(limpio) < 4:
        return [], []
    try:
        c.execute("""SELECT v.id AS "_id", v.patente AS "Patente", v.marca_auto AS "Marca",
                            v.modelo_auto AS "Modelo", v.anio AS "Año",
                            v.motorizacion AS "Motorización", v.numero_motor AS "N° de motor",
                            v.cliente_nombre AS "Cliente", v.km_actual AS "Km"
                     FROM vehiculos v
                     WHERE REPLACE(REPLACE(REPLACE(UPPER(COALESCE(v.numero_motor,'')),
                                                    ' ',''), '-',''), '.','') = ?
                     LIMIT 50""", (limpio,))
        exactas = filas_a_listas(c)

        c.execute("""SELECT v.id AS "_id", v.patente AS "Patente", v.marca_auto AS "Marca",
                            v.modelo_auto AS "Modelo", v.anio AS "Año",
                            v.motorizacion AS "Motorización", v.numero_motor AS "N° de motor",
                            v.cliente_nombre AS "Cliente"
                     FROM vehiculos v
                     WHERE COALESCE(v.numero_motor,'') <> ''
                       AND REPLACE(REPLACE(REPLACE(UPPER(v.numero_motor),
                                                    ' ',''), '-',''), '.','') LIKE ?
                     LIMIT 50""", (f"%{limpio}%",))
        parciales = [f for f in filas_a_listas(c)
                     if f["_id"] not in {x["_id"] for x in exactas}]

        # Si no apareció nada, se prueban las lecturas equivocadas más comunes: un 0 que era
        # una O, un 5 que era una S. Solo cuando no hay ningún resultado, para no ensuciar
        # una búsqueda que ya encontró lo que buscaba.
        if not exactas and not parciales:
            vistos = set()
            for variante in variantes_numero_motor(limpio):
                c.execute("""SELECT v.id AS "_id", v.patente AS "Patente",
                                    v.marca_auto AS "Marca", v.modelo_auto AS "Modelo",
                                    v.anio AS "Año", v.motorizacion AS "Motorización",
                                    v.numero_motor AS "N° de motor",
                                    v.cliente_nombre AS "Cliente"
                             FROM vehiculos v
                             WHERE REPLACE(REPLACE(REPLACE(UPPER(COALESCE(v.numero_motor,'')),
                                                            ' ',''), '-',''), '.','') = ?
                             LIMIT 5""", (variante,))
                for f in filas_a_listas(c):
                    if f["_id"] not in vistos:
                        vistos.add(f["_id"])
                        f["Por qué"] = f"leyendo «{variante}» en vez de «{limpio}»"
                        parciales.append(f)
        return exactas, parciales
    except sqlite3.OperationalError as _err:
        anotar_error("buscar_por_numero_motor", _err)
        return [], []


def autos_con_la_misma_familia_de_motor(numero, largo_prefijo=4):
    """Otros autos con un motor de la misma familia.

    El número de motor arranca con el código del modelo de motor —«4G15», «EA111»— y sigue con
    el serial de esa unidad. Los primeros caracteres son el TIPO de motor, y ahí está lo útil:
    si el motor es el mismo modelo, los repuestos son los mismos aunque sea otra unidad y otro
    auto."""
    limpio = normalizar_numero_motor(numero)
    if len(limpio) < largo_prefijo + 2:
        return []
    prefijo = limpio[:largo_prefijo]
    try:
        c.execute("""SELECT v.patente AS "Patente", v.marca_auto AS "Marca",
                            v.modelo_auto AS "Modelo", v.anio AS "Año",
                            v.motorizacion AS "Motorización", v.numero_motor AS "N° de motor"
                     FROM vehiculos v
                     WHERE COALESCE(v.numero_motor,'') <> ''
                       AND REPLACE(REPLACE(REPLACE(UPPER(v.numero_motor),
                                                    ' ',''), '-',''), '.','') LIKE ?
                       AND REPLACE(REPLACE(REPLACE(UPPER(v.numero_motor),
                                                    ' ',''), '-',''), '.','') <> ?
                     LIMIT 50""", (f"{prefijo}%", limpio))
        return filas_a_listas(c)
    except sqlite3.OperationalError as _err:
        anotar_error("autos_con_la_misma_familia_de_motor", _err)
        return []


def todo_lo_de_una_patente(patente):
    """De la patente a los repuestos, en un solo paso. Devuelve un diccionario con todo.

    Las piezas ya existían sueltas —buscar el vehículo, ver su historial, buscar repuestos por
    marca y modelo— pero había que ir juntándolas a mano en tres pantallas. En el mostrador
    eso no pasa: el cliente dice la patente y hay que contestarle.

    Importante y por eso el resultado dice de dónde salió cada cosa: si el auto no está en las
    fichas, la patente sola NO alcanza. En Argentina no hay ninguna base pública gratuita que
    traduzca patente a vehículo — las que existen cobran por consulta."""
    pat = (patente or "").strip().upper().replace(" ", "")
    salida = {"patente": pat, "vehiculo": None, "historial": [], "sugeridos": [],
              "por_motor": [], "consultas": []}
    if len(pat) < 6:
        return salida

    salida["vehiculo"] = buscar_vehiculo(pat)
    v = salida["vehiculo"]
    if not v:
        return salida

    # 1. Lo que YA se le puso a este auto. Es lo más confiable: no es un catálogo diciendo
    # qué debería entrar, es lo que alguien efectivamente le instaló.
    try:
        c.execute("""SELECT hp.descripcion_pieza AS "Pieza", hp.marca_pieza AS "Marca",
                            hp.codigo_pieza AS "Código", hp.km_instalacion AS "Km",
                            substr(hp.fecha_instalacion, 1, 10) AS "Cuándo",
                            p.precio AS "Precio hoy", p.stock AS "Stock"
                     FROM historial_piezas hp
                     LEFT JOIN productos p ON p.id = hp.producto_id
                     WHERE hp.vehiculo_id = ?
                     ORDER BY hp.fecha_instalacion DESC LIMIT 100""", (v["id"],))
        salida["historial"] = filas_a_listas(c)
    except sqlite3.OperationalError as _err:
        anotar_error("todo_lo_de_una_patente/historial", _err)

    # 2. Lo que le entra según marca, modelo, año y motor
    try:
        salida["sugeridos"] = repuestos_de_este_auto(
            v.get("marca_auto") or "", v.get("modelo_auto") or "", v.get("anio"),
            v.get("motorizacion") or "", v.get("vin") or "", limite=200)
    except Exception as _err:
        anotar_error("todo_lo_de_una_patente/sugeridos", _err)

    # 3. Si tiene número de motor, lo que se le puso a otros autos con ese mismo motor.
    # Cuando el motor está cambiado, esto vale más que la marca y el modelo del auto.
    if v.get("numero_motor"):
        try:
            salida["por_motor"] = autos_con_la_misma_familia_de_motor(v["numero_motor"])
        except Exception as _err:
            anotar_error("todo_lo_de_una_patente/motor", _err)

    # 4. Lo que este cliente preguntó antes
    if v.get("cliente_telefono") or v.get("cliente_nombre"):
        salida["consultas"] = historial_de_un_cliente(
            v.get("cliente_telefono") or v.get("cliente_nombre") or "")
    return salida


def repuestos_por_numero_motor(numero):
    """Qué repuestos se le pusieron a los autos que tienen ese motor.

    Es el punto: si el motor está cambiado, el VIN del auto no sirve para elegir repuestos —
    el motor manda. Buscando por el número se llega a lo que de verdad le entra."""
    exactas, _ = buscar_por_numero_motor(numero)
    if not exactas:
        return []
    ids = [v["_id"] for v in exactas]
    marcadores = ",".join("?" for _ in ids)
    try:
        c.execute(f"""SELECT DISTINCT p.codigo_raw AS "Código", m.nombre AS "Marca",
                             p.descripcion AS "Descripción", p.precio AS "Precio",
                             p.stock AS "Stock", hp.descripcion_pieza AS "Se puso como",
                             substr(hp.fecha_instalacion, 1, 10) AS "Cuándo"
                      FROM historial_piezas hp
                      LEFT JOIN productos p ON p.id = hp.producto_id
                      LEFT JOIN marcas m ON m.id = p.marca_id
                      WHERE hp.vehiculo_id IN ({marcadores})
                      ORDER BY hp.fecha_instalacion DESC LIMIT 100""", ids)
        return filas_a_listas(c)
    except sqlite3.OperationalError as _err:
        anotar_error("repuestos_por_numero_motor", _err)
        return []


# ============================================================================================
# CONSULTAS DE CLIENTES (lo que pidieron y no había)
# ============================================================================================
def anotar_consulta_cliente(cliente, telefono, producto_id=None, codigo="", descripcion="",
                            cantidad=1, precio=None, nota=""):
    """Guarda qué pidió un cliente que dijo que lo pensaba. Devuelve (ok, mensaje)."""
    if not (cliente or "").strip() and not (telefono or "").strip():
        return False, "Poné al menos el nombre o el teléfono, si no después no sabés de quién era."
    with db_lock:
        c.execute("""INSERT INTO consultas_cliente
                     (cliente, telefono, producto_id, codigo_buscado, descripcion, cantidad,
                      precio_dicho, nota, atendio)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  ((cliente or "").strip() or None, (telefono or "").strip() or None,
                   producto_id, (codigo or "").strip() or None,
                   (descripcion or "").strip()[:120] or None, int(cantidad or 1),
                   precio, (nota or "").strip() or None, obtener_usuario_actual()))
        conn.commit()
    return True, "Anotado. Aparece en «Consultas de clientes»."


def consultas_de_clientes(estado="activa", limite=200):
    """Lo que pidieron los clientes y todavía no se resolvió."""
    try:
        c.execute("""SELECT cc.id AS "_id", cc.cliente AS "Cliente", cc.telefono AS "Teléfono",
                            cc.codigo_buscado AS "Pidió", cc.descripcion AS "Descripción",
                            cc.cantidad AS "Cant.", cc.precio_dicho AS "Precio dicho",
                            cc.nota AS "Nota", cc.atendio AS "Atendió",
                            substr(cc.fecha, 1, 16) AS "Cuándo",
                            CAST(julianday('now') - julianday(cc.fecha) AS INTEGER) AS "Días",
                            p.stock AS "Stock hoy", p.precio AS "Precio hoy"
                     FROM consultas_cliente cc
                     LEFT JOIN productos p ON p.id = cc.producto_id
                     WHERE cc.estado = ?
                     ORDER BY cc.fecha DESC LIMIT ?""", (estado, limite))
        return filas_a_listas(c)
    except sqlite3.OperationalError as _err:
        anotar_error("consultas_de_clientes", _err)
        return []


def historial_de_un_cliente(texto):
    """Todo lo que preguntó o compró un cliente, buscando por nombre o teléfono.

    Sirve cuando vuelve: en vez de arrancar de cero, se ve qué le interesaba y a qué precio se
    lo cotizaron. También cuando llama y dice «soy el del Gol»."""
    patron = f"%{(texto or '').strip()}%"
    if len(patron) <= 2:
        return []
    try:
        c.execute("""SELECT cc.cliente AS "Cliente", cc.telefono AS "Teléfono",
                            cc.codigo_buscado AS "Pidió", cc.descripcion AS "Descripción",
                            cc.cantidad AS "Cant.", cc.precio_dicho AS "Le dijimos",
                            cc.estado AS "Qué pasó", substr(cc.fecha, 1, 16) AS "Cuándo",
                            p.precio AS "Precio hoy", p.stock AS "Stock hoy"
                     FROM consultas_cliente cc
                     LEFT JOIN productos p ON p.id = cc.producto_id
                     WHERE cc.cliente LIKE ? OR cc.telefono LIKE ?
                     ORDER BY cc.fecha DESC LIMIT 100""", (patron, patron))
        return filas_a_listas(c)
    except sqlite3.OperationalError as _err:
        anotar_error("historial_de_un_cliente", _err)
        return []


def cerrar_consulta(consulta_id, resultado):
    """El cliente volvió y compró, o no volvió.

    Los estados son los mismos que usan las reservas —'vendida' y 'cancelada'— a propósito:
    tener 'vendido' acá y 'vendida' allá es la clase de diferencia de una letra que después
    hace que una consulta no encuentre nada y nadie sepa por qué."""
    with db_lock:
        c.execute("""UPDATE consultas_cliente SET estado = ?, fecha_cierre = datetime('now')
                     WHERE id = ?""", (resultado, consulta_id))
        conn.commit()
    return True


def consultas_que_ahora_hay_en_stock():
    """Clientes esperando algo que en su momento no había y ahora sí. Son ventas a un llamado.

    Es el caso que más se pierde en el mostrador: entró la mercadería, nadie se acuerda quién
    la había pedido, y el cliente ya la compró en otro lado."""
    try:
        c.execute("""SELECT cc.id AS "_id", cc.cliente AS "Cliente", cc.telefono AS "Teléfono",
                            cc.codigo_buscado AS "Pidió", cc.cantidad AS "Quería",
                            p.stock AS "Hay ahora", p.precio AS "Precio hoy",
                            cc.precio_dicho AS "Le dijimos",
                            CAST(julianday('now') - julianday(cc.fecha) AS INTEGER) AS "Días"
                     FROM consultas_cliente cc
                     JOIN productos p ON p.id = cc.producto_id
                     WHERE cc.estado = 'activa'
                       AND COALESCE(p.stock, 0) >= COALESCE(cc.cantidad, 1)
                     ORDER BY cc.fecha LIMIT 100""")
        return filas_a_listas(c)
    except sqlite3.OperationalError as _err:
        anotar_error("consultas_que_ahora_hay_en_stock", _err)
        return []


# ============================================================================================
# STOCK Y RESERVAS
# ============================================================================================
def reservar_stock(producto_id, cantidad, cliente="", nota=""):
    """Aparta unidades para un presupuesto. Devuelve (ok, mensaje).

    No deja reservar más de lo que hay libre: eso convertiría la reserva en otra forma de
    prometer lo que no tenés, que es justo lo que se quiere evitar.

    EL CONTROL Y LA RESERVA VAN JUNTOS, y ese es todo el punto. Antes se preguntaba cuánto hay
    libre AFUERA del candado y solo el INSERT iba adentro, así que entre la pregunta y la
    respuesta se podía colar la otra sesión. Es exactamente el caso que la tabla de reservas
    existe para evitar —el de su propio comentario: «uno cotiza 4 pastillas, el otro ve stock 4
    y las vende»— y estaba abierto en la función que lo tenía que cerrar.

    Reproducido sobre una copia de la base real: stock 5, dos sesiones a la vez pidiendo 4 y 3.
    Las dos contestaban «se apartaron», y quedaban 7 unidades reservadas sobre 5.

    Con la lectura adentro de `db_lock` y de `transaccion()`, la segunda espera a la primera y
    recibe el «solo quedan N». BEGIN IMMEDIATE además pide el candado de escritura de SQLite
    desde el arranque, así que tampoco se cuela otro proceso, no solo otro hilo."""
    cantidad = int(cantidad or 0)
    if cantidad <= 0:
        return False, "La cantidad tiene que ser mayor que cero."
    with db_lock, transaccion():
        libre = stock_libre(producto_id)
        if libre is None:
            return False, "No encontré ese producto."
        if cantidad > libre:
            return False, (f"Solo quedan {libre} sin reservar. Si igual querés apartarlas, "
                           "primero liberá alguna reserva.")
        c.execute("""INSERT INTO reservas_stock (producto_id, cantidad, cliente, nota, reservado_por)
                     VALUES (?, ?, ?, ?, ?)""",
                  (producto_id, cantidad, (cliente or "").strip() or None,
                   (nota or "").strip() or None, obtener_usuario_actual()))
    return True, f"Se apartaron {cantidad} unidad(es)."


def stock_libre(producto_id):
    """Lo que queda realmente disponible: el stock menos lo reservado. None si no existe."""
    c.execute("SELECT stock FROM productos WHERE id = ?", (producto_id,))
    fila = c.fetchone()
    if not fila:
        return None
    try:
        c.execute("""SELECT COALESCE(SUM(cantidad), 0) FROM reservas_stock
                     WHERE producto_id = ? AND estado = 'activa'""", (producto_id,))
        reservado = c.fetchone()[0]
    except sqlite3.OperationalError as _err:
        anotar_error("stock_libre", _err)
        reservado = 0
    return max((fila["stock"] or 0) - reservado, 0)


def stock_libre_de_varios(ids):
    """Lo mismo que stock_libre() pero para muchos productos, con dos consultas por tanda.

    De a uno son dos consultas por producto. En una búsqueda que trae 50 equivalencias eso son
    200 idas a la base en CADA refresco de pantalla —o sea, cada vez que se toca cualquier botón
    de la sección—.

    Va de a 500 porque un IN (?, ?, ...) lleva un signo por producto y choca contra el tope de
    variables de SQLite, que en instalaciones viejas son 999. Sin las tandas, justo la búsqueda
    más grande —la que más falta hace— era la que fallaba."""
    ids = [int(i) for i in ids if i is not None]
    if not ids:
        return {}
    libres = {}
    for tanda, marcadores in en_tandas(ids):
        c.execute(f"SELECT id, COALESCE(stock, 0) AS stock FROM productos "
                  f"WHERE id IN ({marcadores})", tanda)
        total = {f["id"]: f["stock"] for f in c.fetchall()}
        try:
            c.execute(f"""SELECT producto_id, COALESCE(SUM(cantidad), 0) AS reservado
                          FROM reservas_stock
                          WHERE estado = 'activa' AND producto_id IN ({marcadores})
                          GROUP BY producto_id""", tanda)
            reservado = {f["producto_id"]: f["reservado"] for f in c.fetchall()}
        except sqlite3.OperationalError as _err:
            anotar_error("stock_libre_de_varios", _err)
            reservado = {}
        for i, v in total.items():
            libres[i] = max(v - reservado.get(i, 0), 0)
    return libres


def reservas_activas(limite=200):
    """Lo que está apartado ahora mismo."""
    try:
        c.execute("""SELECT r.id AS "_id", p.codigo_raw AS "Código", m.nombre AS "Marca",
                            p.descripcion AS "Descripción", r.cantidad AS "Apartadas",
                            p.stock AS "Stock total", r.cliente AS "Cliente",
                            r.reservado_por AS "Quién", substr(r.fecha, 1, 16) AS "Desde",
                            CAST(julianday('now') - julianday(r.fecha) AS INTEGER) AS "Días"
                     FROM reservas_stock r
                     JOIN productos p ON p.id = r.producto_id
                     JOIN marcas m ON m.id = p.marca_id
                     WHERE r.estado = 'activa'
                     ORDER BY r.fecha DESC LIMIT ?""", (limite,))
        return filas_a_listas(c)
    except sqlite3.OperationalError as _err:
        anotar_error("reservas_activas", _err)
        return []


def cerrar_reserva(reserva_id, vendida):
    """Se concretó la venta (descuenta del stock) o se cayó (solo libera)."""
    # Todo o nada: el descuento de stock y el cierre de la reserva son el mismo acto. Cortado
    # en el medio, el stock bajaba y la reserva quedaba «activa», así que el empleado la
    # cerraba otra vez y descontaba de nuevo. Probado: una reserva de 3 llegó a descontar 6.
    with db_lock, transaccion():
        c.execute("SELECT producto_id, cantidad FROM reservas_stock WHERE id = ? AND estado='activa'",
                  (reserva_id,))
        fila = c.fetchone()
        if not fila:
            return False
        if vendida:
            c.execute("UPDATE productos SET stock = MAX(COALESCE(stock,0) - ?, 0) WHERE id = ?",
                      (fila["cantidad"], fila["producto_id"]))
        c.execute("UPDATE reservas_stock SET estado = ? WHERE id = ?",
                  ("vendida" if vendida else "cancelada", reserva_id))
    return True


# ============================================================================================
# PRECIOS Y MÁRGENES
# ============================================================================================
def margen_de(precio_venta, precio_costo):
    """Cuánto queda de margen. Devuelve (porcentaje, pesos) o (None, None) si falta un dato.

    Se calcula sobre el PRECIO DE VENTA, que es como se mira el margen en el mostrador
    («de cada 100 que entran, me quedan 35»). Calcularlo sobre el costo da un número más
    grande y más lindo, pero no es el que sirve para decidir."""
    if not precio_venta or not precio_costo or precio_venta <= 0 or precio_costo <= 0:
        return None, None
    ganancia = precio_venta - precio_costo
    return (ganancia / precio_venta) * 100, ganancia


def agregar_margen(filas):
    """Le suma a cada resultado su margen, si están los dos precios.

    NO borra el costo de la fila, aunque el costo no se muestre. Estas filas son las mismas que
    quedan guardadas en session_state entre refrescos: al borrarles el costo, al segundo toque de
    cualquier botón ya no estaba, así que la columna Margen aparecía vacía y el aviso de «mejor
    margen» desaparecía. Sin error y sin aviso: se veía una vez y no volvía más.
    De que el costo no llegue a la pantalla se encarga quien la dibuja, sacando las claves que
    empiezan con guión bajo."""
    for f in filas:
        pct, pesos = margen_de(f.get("Precio"), f.get("_costo"))
        f["Margen"] = f"{pct:.0f}% (${pesos:,.0f})" if pct is not None else ""
    return filas


def mejor_margen_entre_equivalentes(res):
    """De los equivalentes con stock, cuál te deja más ganancia.

    No es lo mismo que el más barato: entre dos que sirven igual, el que te deja más margen
    puede ser el más caro para el cliente o el más barato. Este dato hoy no existía y la
    decisión se tomaba a ojo."""
    candidatos = [f for f in res
                  if (f.get("Stock") or 0) > 0 and f.get("Precio") and f.get("_costo")]
    if len(candidatos) < 2:
        return None
    def ganancia(f):
        return (f["Precio"] or 0) - (f["_costo"] or 0)
    mejor = max(candidatos, key=ganancia)
    peor = min(candidatos, key=ganancia)
    if ganancia(mejor) <= ganancia(peor):
        return None
    return {"codigo": mejor["Codigo"], "marca": mejor["Marca"],
            "ganancia": ganancia(mejor), "diferencia": ganancia(mejor) - ganancia(peor)}


# ============================================================================================
# FUSIONAR MARCAS Y PRODUCTOS DUPLICADOS
# ============================================================================================
def marcas_probablemente_duplicadas(limite=40):
    """Marcas que son la misma cargada dos veces. Devuelve pares para revisar.

    Pasa todo el tiempo: una lista viene como «MAHLE» y la siguiente como «MAHLE FILTER», o
    alguien la tipeó distinto. Quedan como dos proveedores separados, y ahí el buscador deja de
    encontrar equivalencias que en realidad existen — el mismo repuesto figura en dos lados sin
    ninguna relación entre sí.

    Se detecta por dos caminos, y ambos importan:
      · el NOMBRE se parece (una contiene a la otra, o difieren en pocas letras)
      · comparten CÓDIGOS: si dos marcas tienen los mismos códigos, son el mismo proveedor
        aunque se llamen distinto — que es el caso que ningún chequeo por nombre agarra."""
    c.execute("""SELECT m.id, m.nombre, COUNT(p.id) AS productos
                 FROM marcas m LEFT JOIN productos p ON p.marca_id = m.id
                 GROUP BY m.id HAVING COUNT(p.id) > 0""")
    marcas = [dict(r) for r in c.fetchall()]
    if len(marcas) < 2:
        return []

    salida = []
    for i, a in enumerate(marcas):
        for b in marcas[i + 1:]:
            na, nb = a["nombre"].upper().strip(), b["nombre"].upper().strip()
            motivo = None
            # Nombre: una contenida en la otra, o a un par de letras de distancia
            if na in nb or nb in na:
                motivo = "una contiene a la otra"
            elif _distancia_edicion(na.replace(" ", ""), nb.replace(" ", ""), tope=2) <= 2:
                motivo = "se escriben casi igual"

            # Códigos compartidos: la señal más fuerte, y la única que agarra los nombres
            # que no se parecen en nada
            c.execute("""SELECT COUNT(*) FROM productos pa
                         JOIN productos pb ON pa.codigo_clean = pb.codigo_clean
                         WHERE pa.marca_id = ? AND pb.marca_id = ?""", (a["id"], b["id"]))
            compartidos = c.fetchone()[0]
            menor = min(a["productos"], b["productos"])
            proporcion = compartidos / menor if menor else 0
            if proporcion >= 0.6 and compartidos >= 5:
                motivo = (f"comparten {compartidos} código(s): el "
                          f"{proporcion * 100:.0f}% de la más chica")
            if not motivo:
                continue
            salida.append({
                "Marca A": a["nombre"], "Productos A": a["productos"],
                "Marca B": b["nombre"], "Productos B": b["productos"],
                "Por qué": motivo, "Códigos en común": compartidos,
                "_ida": a["id"], "_idb": b["id"],
                "_peso": compartidos * 10 + (100 - abs(a["productos"] - b["productos"]) / 100),
            })
    salida.sort(key=lambda x: -x["_peso"])
    return salida[:limite]


def fusionar_productos(id_perdedor, id_ganador):
    """Junta dos productos que son el mismo en uno solo. Devuelve True si se fusionó.

    Hace falta porque productos tiene UNIQUE(codigo_clean, marca_id): si dos productos terminan
    con el mismo código en la misma marca, la base lo rechaza. Mover a la fuerza uno encima del
    otro tira IntegrityError y la operación se cae entera.

    Lo que NO se pierde: las equivalencias, los pendientes, las fotos y el precio y el stock que
    tuviera el que se va y le falte al que queda. Se descarta el registro duplicado, no los datos."""
    if id_perdedor == id_ganador:
        return False
    # Todo o nada: son varios pasos sobre varias tablas y el estado intermedio es basura.
    # Probado cortando el borrado final a propósito: el producto duplicado seguía existiendo
    # pero ya se le habían borrado TODAS las equivalencias. Se perdieron sin aviso.
    with transaccion():
        # Las equivalencias del que se va pasan al que queda, sin duplicar ni auto-vincular
        c.execute("""SELECT CASE WHEN producto_a_id = ? THEN producto_b_id ELSE producto_a_id END AS otro,
                            lote
                     FROM equivalencias WHERE producto_a_id = ? OR producto_b_id = ?""",
                  (id_perdedor, id_perdedor, id_perdedor))
        for fila in c.fetchall():
            otro = fila["otro"]
            if otro == id_ganador:
                continue
            c.execute("INSERT OR IGNORE INTO equivalencias (producto_a_id, producto_b_id, lote) "
                      "VALUES (?, ?, ?)", (min(otro, id_ganador), max(otro, id_ganador), fila["lote"]))
        c.execute("DELETE FROM equivalencias WHERE producto_a_id = ? OR producto_b_id = ?",
                  (id_perdedor, id_perdedor))

        for tabla, col_a, col_b in (("equivalencias_pendientes", "producto_a_id", "producto_b_id"),):
            try:
                c.execute(f"DELETE FROM {tabla} WHERE {col_a} = ? OR {col_b} = ?",
                          (id_perdedor, id_perdedor))
            except sqlite3.OperationalError as _err:
                anotar_error("fusionar_productos", _err)
                pass

        # Datos que el que queda podría no tener
        for tabla, columna in (("producto_fotos", "producto_id"), ("historial_precios", "producto_id")):
            try:
                c.execute(f"UPDATE {tabla} SET {columna} = ? WHERE {columna} = ?",
                          (id_ganador, id_perdedor))
            except sqlite3.OperationalError as _err:
                anotar_error("fusionar_productos", _err)
                pass
        c.execute("""UPDATE productos SET
                        precio = COALESCE(precio, (SELECT precio FROM productos WHERE id = ?)),
                        stock = COALESCE(stock, (SELECT stock FROM productos WHERE id = ?)),
                        descripcion = COALESCE(descripcion, (SELECT descripcion FROM productos WHERE id = ?))
                     WHERE id = ?""", (id_perdedor, id_perdedor, id_perdedor, id_ganador))
        c.execute("DELETE FROM productos WHERE id = ?", (id_perdedor,))
    return True


def fusionar_marcas(marca_origen_id, marca_destino_id):
    """Mueve todos los productos de una marca a otra y borra la marca origen.

    Devuelve (movidos, fusionados). Los que ya existían en la marca destino con el mismo código
    no se pueden mover —la base no admite dos veces el mismo código en una marca— así que se
    fusionan con el que ya estaba, conservando sus equivalencias. Antes esto no se contemplaba
    y la operación entera fallaba con IntegrityError, sin mover nada."""
    movidos = fusionados = 0
    # Todo o nada: mover miles de productos y borrar la marca vieja es UNA operación. Cortada
    # en el medio quedaban productos repartidos entre las dos marcas y la vieja todavía viva.
    with db_lock, transaccion():
        c.execute("SELECT id, codigo_clean FROM productos WHERE marca_id = ?", (marca_origen_id,))
        productos_origen = [(r["id"], r["codigo_clean"]) for r in c.fetchall()]
        for pid, clean in productos_origen:
            c.execute("SELECT id FROM productos WHERE marca_id = ? AND codigo_clean = ?",
                      (marca_destino_id, clean))
            existente = c.fetchone()
            if existente:
                fusionar_productos(pid, existente["id"])
                fusionados += 1
            else:
                c.execute("UPDATE productos SET marca_id = ? WHERE id = ?", (marca_destino_id, pid))
                movidos += 1
        c.execute("DELETE FROM marcas WHERE id = ?", (marca_origen_id,))
    return movidos, fusionados


def aumentar_precios_por_marca(marca_id, porcentaje):
    """Sube (o baja, con porcentaje negativo) todos los precios cargados de una marca."""
    with db_lock:
        c.execute(
            "UPDATE productos SET precio = ROUND(precio * (1 + ? / 100.0), 2) "
            "WHERE marca_id = ? AND precio IS NOT NULL",
            (porcentaje, marca_id)
        )
        afectados = c.rowcount
        conn.commit()
    return afectados


def listar_favoritos_stock_bajo(umbral=2):
    c.execute("""SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
                 m.nombre AS "Marca", p.precio AS "Precio", p.stock AS "Stock"
                 FROM productos p JOIN marcas m ON m.id = p.marca_id
                 WHERE p.favorito = 1 AND (p.stock IS NULL OR p.stock <= ?)
                 ORDER BY p.stock ASC, p.codigo_raw""", (umbral,))
    return filas_a_listas(c)


def registrar_busqueda_sin_resultado(termino):
    with db_lock:
        c.execute("INSERT INTO historial_busquedas (termino, usuario, sin_resultado) VALUES (?, ?, 1)",
                   (termino, obtener_usuario_actual()))
        conn.commit()

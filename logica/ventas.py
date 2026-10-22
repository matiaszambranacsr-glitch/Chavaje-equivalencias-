"""Las ventas del mostrador: armar la venta, cerrarla y, al terminar, anotarla en la ficha del auto
con la patente y los km.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================================================
# VENTAS DEL MOSTRADOR
# ============================================================================================
# Lo pidió el dueño: «una división nueva para ventas, y que cuando se termine la venta te diga si
# querés poner la patente y los km». Hasta acá «🛒 Se llevó» anotaba qué se vendió —para aprender
# equivalencias— pero sin cantidad, sin precio y sin descontar el stock; lo único que descontaba
# al vender era el depósito al entregar un pedido. Y la ficha del auto había que llenarla a mano,
# pieza por pieza: en la base real hay 0 fichas.
#
# Una venta acá:
#   · descuenta el stock como el depósito: nunca negativo, y si no alcanzaba queda anotado para
#     contarlo (ver entregar_pedido());
#   · anota cada cosa en ventas_registradas, como «Se llevó»: así sigue aprendiendo qué se vende
#     en lugar de qué (con lo que pidió el cliente, si se buscó otro código);
#   · guarda el precio y la descripción de ese momento: si mañana cambia la lista, la venta dice
#     lo que se cobró;
#   · al terminar, ofrece la patente y los km: crea o pone al día la ficha del auto y anota ahí
#     cada pieza, con un nombre corto y parejo (ver nombre_de_la_pieza()). Desde ese momento el
#     link del cliente, «A quién avisar» y «cuánto le falta» tienen datos sin cargar nada más.
# Cargarla a la cuenta de un taller no va acá: eso pide el código de retiro y el límite de
# crédito, y se hace pidiéndolo al depósito con la cuenta elegida.
FORMAS_DE_PAGO = ["Efectivo", "Transferencia", "Tarjeta de débito", "Tarjeta de crédito", "Otra"]

# Lo que sigue a «FILTRO», «CORREA», «PASTILLA»… y dice CUÁL es: el filtro de aceite y el de
# aire son piezas distintas y vencen distinto. Ver nombre_de_la_pieza().
_LO_QUE_DICE_CUAL_ES = {
    "ACEITE", "AIRE", "NAFTA", "COMBUSTIBLE", "GASOIL", "HABITACULO", "CABINA", "POLEN", "FRENO",
    "FRENOS", "DISTRIBUCION", "AGUA", "EMBRAGUE", "DIRECCION", "ALTERNADOR", "ACCESORIOS",
    "DENTADA", "POLY", "ENCENDIDO", "CALEFACCION", "RADIADOR", "TRANSMISION", "CAJA", "MOTOR",
    "DIFERENCIAL", "DELANTERA", "DELANTERAS", "DELANTERO", "DELANTEROS", "TRASERA", "TRASERAS",
    "TRASERO", "TRASEROS",
}


def nombre_de_la_pieza(descripcion):
    """Un nombre corto y parejo para la ficha del auto: «Filtro aceite», no «FILTRO ACEITE VW GOL
    1.6 8V (W712/94)». La ficha agrupa los cambios por este nombre para saber cuándo fue el
    último (ver estado_de_cada_pieza()): con la descripción entera, el mismo filtro de dos
    marcas eran dos piezas distintas. Sale de las mismas claves que las familias de repuestos
    (ver clasificar_repuesto()); en la pantalla se puede corregir antes de anotarlo."""
    texto = _normalizar_desc(descripcion)
    if not texto.strip():
        return ""
    patron, _ = _BUSCADOR_DE_FAMILIAS
    hallado = patron.search(texto)
    if not hallado:
        return " ".join(re.findall(r"[A-ZÑ]{3,}", texto)[:2]).capitalize()
    nombre = hallado.group(1)
    resto = texto[hallado.end():].split()
    if " " not in nombre and resto:
        if resto[0] in _LO_QUE_DICE_CUAL_ES:
            nombre += " " + resto[0]
        elif resto[0] in ("DE", "P", "PARA") and len(resto) > 1 and resto[1] in _LO_QUE_DICE_CUAL_ES:
            nombre += " " + resto[1]
    return nombre.capitalize()


def item_de_venta(producto_id, cantidad=1, pedido=""):
    """La fila de la venta para un producto del catálogo, con su precio de hoy, o None."""
    c.execute("""SELECT p.id, p.codigo_raw, p.descripcion, p.precio, p.precio_costo, p.stock,
                        m.nombre AS marca
                 FROM productos p JOIN marcas m ON m.id = p.marca_id WHERE p.id = ?""",
              (producto_id,))
    f = c.fetchone()
    if not f:
        return None
    return {"producto_id": f["id"], "codigo": f["codigo_raw"], "marca": f["marca"],
            "descripcion": f["descripcion"] or "", "precio": float(f["precio"] or 0),
            "costo": f["precio_costo"], "stock": f["stock"], "cantidad": int(cantidad),
            "pedido": (pedido or "").strip()}


def sumar_a_la_venta(fila, pedido="", veredicto=None, evidencia=None, confirmado=False):
    """Suma un resultado de la búsqueda a la venta que se está armando (o uno más, si ya
    estaba). `veredicto` y `evidencia` son los que tenía ese resultado (ver
    veredicto_de_la_equivalencia()): viajan con el ítem hasta cerrar_venta(), que frena lo 🔴
    sin confirmar y lo anota como lo anota «Se llevó». Devuelve el ítem, o None."""
    venta = st.session_state.setdefault("venta_items", [])
    ya = next((x for x in venta if x["producto_id"] == fila["ID"]), None)
    if ya:
        ya["cantidad"] += 1
        ya["confirmado"] = ya.get("confirmado") or confirmado
        # El campo de la cantidad guarda lo suyo: sin esto, el «+1» no se veía.
        st.session_state.pop(f"venta_cant_{fila['ID']}", None)
        return ya
    nuevo = item_de_venta(fila["ID"], 1, pedido)
    if nuevo:
        nuevo.update(veredicto=veredicto, evidencia=evidencia, confirmado=confirmado)
        venta.append(nuevo)
    return nuevo


def lo_que_se_termino(venta_id):
    """Lo vendido en esa venta que quedó con stock 0: [(producto_id, «marca código»)]. Para
    anotarlo para reponer ahí mismo (ver solicitar_reposicion())."""
    c.execute("""SELECT DISTINCT vi.producto_id, vi.marca, vi.codigo FROM ventas_items vi
                 JOIN productos p ON p.id = vi.producto_id
                 WHERE vi.venta_id = ? AND p.stock = 0 ORDER BY vi.id""", (venta_id,))
    return [(f["producto_id"], f"{f['marca']} {f['codigo']}") for f in c.fetchall()]


def lo_que_suele_ir_con_la_venta(items):
    """Para cada cosa de la venta, lo que suele cambiarse junto con ella y no está en la venta
    (ver lo_que_suele_ir_con()): [(«marca código», [nombres])]. Lo mismo que avisa «Se llevó»,
    antes de que se vaya el cliente."""
    textos = [normalizar_texto(it.get("descripcion") or "") for it in items]
    salida = []
    for it in items:
        # «Kit de distribución (si la mueve la correa)»: lo de entre paréntesis es para quien
        # atiende, no está en ninguna descripción.
        faltan = [n for n in lo_que_suele_ir_con(it["producto_id"])
                  if not any(normalizar_texto(re.sub(r"\(.*?\)", "", n)).strip() in t
                             for t in textos)]
        if faltan:
            salida.append((f"{it['marca']} {it['codigo']}", faltan))
    return salida


def cierre_de_caja(dia=None):
    """Lo que entró en un día (hoy, si no se dice): el total, por forma de pago y por quién
    atendió, y lo anulado aparte. Para cerrar la caja: contar la plata del cajón contra lo que
    dice «Efectivo», y las transferencias contra el banco. dict."""
    ventas = ventas_del_dia(dia)
    validas = [v for v in ventas if not v["anulada"]]

    def agrupar(campo, vacio):
        grupos = {}
        for v in validas:
            g = grupos.setdefault(v[campo] or vacio, [0, 0.0])
            g[0] += 1
            g[1] += v["total"] or 0
        return sorted(((k, n, round(t, 2)) for k, (n, t) in grupos.items()),
                      key=lambda x: -x[2])
    anuladas = [v for v in ventas if v["anulada"]]
    return {"ventas": len(validas), "total": round(sum(v["total"] or 0 for v in validas), 2),
            "por_forma": agrupar("forma_de_pago", "Sin decir"),
            "por_usuario": agrupar("usuario", "Sin decir"),
            "anuladas": len(anuladas),
            "total_anulado": round(sum(v["total"] or 0 for v in anuladas), 2)}


def cerrar_venta(items, cliente="", forma_de_pago="", usuario=None):
    """Cierra la venta. Devuelve (venta_id, avisos). Ver «VENTAS DEL MOSTRADOR».

    `items`: filas de item_de_venta() (con la cantidad y el precio que quedaron en la pantalla).
    Todo o nada: la venta, cada cosa vendida, el stock y lo aprendido van en una transacción.

    LO 🔴 COMO REEMPLAZO, IGUAL QUE «SE LLEVÓ». Un ítem que se sumó desde los resultados de otro
    código trae el veredicto que tenía ahí («veredicto», con su «evidencia»): si la app dice que
    no es la misma pieza, hay que haberlo confirmado («confirmado»), y si además es una pieza
    de seguridad no se vende como reemplazo (ver bloqueo_de_venta()). Se mira acá y no solo en
    la pantalla: si no, cualquier otro camino la vendía igual. Y lo aprendido queda como en
    registrar_venta(): con el veredicto, si se vendió como equivalente o como alternativa, y la
    evidencia de ese momento."""
    exigir_nivel("empleado", "cerrar una venta")
    if not items:
        raise ValueError("La venta no tiene nada.")
    limpios = []
    for it in items:
        try:
            cantidad, precio = int(it.get("cantidad") or 0), float(it.get("precio") or 0)
        except (TypeError, ValueError):
            raise ValueError(f"{it.get('codigo')}: la cantidad o el precio no es un número.")
        if not 1 <= cantidad <= CANTIDAD_MAXIMA_POR_PEDIDO:
            raise ValueError(f"{it.get('codigo')}: la cantidad va de 1 a "
                             f"{CANTIDAD_MAXIMA_POR_PEDIDO}.")
        if precio < 0:
            raise ValueError(f"{it.get('codigo')}: el precio no puede ser negativo.")
        veredicto = it.get("veredicto") or None
        if str(veredicto or "").startswith("🔴"):
            c.execute("SELECT descripcion FROM productos WHERE id = ?", (it["producto_id"],))
            _fila = c.fetchone()
            _bloqueo = bloqueo_de_venta(veredicto, _fila["descripcion"] if _fila else "")
            if _bloqueo == "bloqueada":
                raise ValueError(f"{it.get('codigo')}: {TEXTO_DE_VENTA_BLOQUEADA}")
            if _bloqueo == "confirmar" and not it.get("confirmado"):
                raise ValueError(f"{it.get('codigo')}: la app dice que no es la misma pieza "
                                 f"({veredicto}). Confirmalo primero.")
        limpios.append((int(it["producto_id"]), cantidad, round(precio, 2),
                        (it.get("pedido") or "").strip(), veredicto, it.get("evidencia") or None))
    usuario = usuario or obtener_usuario_actual()
    avisos = []
    with db_lock, transaccion():
        c.execute("""INSERT INTO ventas (usuario, cliente, forma_de_pago, total)
                     VALUES (?, ?, ?, ?)""",
                  (usuario, (cliente or "").strip(), forma_de_pago or "",
                   round(sum(x[1] * x[2] for x in limpios), 2)))
        venta_id = c.lastrowid
        for producto_id, cantidad, precio, pedido, veredicto, evidencia in limpios:
            c.execute("""SELECT p.stock, p.codigo_raw, p.descripcion, m.nombre AS marca
                         FROM productos p JOIN marcas m ON m.id = p.marca_id WHERE p.id = ?""",
                      (producto_id,))
            f = c.fetchone()
            if not f:
                raise ValueError("Uno de los productos ya no está en el catálogo.")
            # EL STOCK, COMO EL DEPÓSITO: nunca negativo, y si no alcanzaba se anota para
            # contarlo. Si se vendió, estaba: el número estaba mal.
            descontado = 0
            if f["stock"] is not None:
                descontado = min(cantidad, max(f["stock"], 0))
                c.execute("UPDATE productos SET stock = MAX(0, stock - ?) WHERE id = ?",
                          (cantidad, producto_id))
                if descontado < cantidad:
                    anotar_cambio("vendió con stock de menos", "producto", producto_id,
                                  {"stock": f["stock"]}, {"stock": 0},
                                  f"se vendieron {cantidad} y figuraban {f['stock']}: conviene "
                                  "contarlo", usuario=usuario)
                    avisos.append(f"{f['codigo_raw']}: se vendieron {cantidad} y figuraban "
                                  f"{f['stock']} en stock. Quedó en 0: conviene contarlo.")
            c.execute("""INSERT INTO ventas_items (venta_id, producto_id, codigo, marca,
                                                   descripcion, cantidad, precio, pedido,
                                                   stock_descontado)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (venta_id, producto_id, f["codigo_raw"], f["marca"], f["descripcion"],
                       cantidad, precio, pedido, descontado))
            # Lo que aprende de las ventas, como «Se llevó»: lo que pidió el cliente y lo que
            # se llevó. Ver descubrir_equivalencias_candidatas().
            _pedido = pedido or f["codigo_raw"]
            c.execute("""INSERT INTO ventas_registradas (producto_id, termino_pedido,
                                                         codigo_pedido_clean, usuario, veredicto,
                                                         como, evidencia, venta_id)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                      (producto_id, _pedido, sanitizar(_pedido), usuario, veredicto,
                       como_se_vende(veredicto), evidencia, venta_id))
    return venta_id, avisos


def anotar_la_venta_en_el_auto(venta_id, patente, km, piezas=None, cliente_nombre="",
                               telefono="", aunque_tenga_menos_km=False):
    """Al terminar la venta: la patente y los km. (ok, texto, vehiculo_id).

    Crea la ficha del auto o la pone al día con el km, y anota ahí cada cosa vendida con el
    nombre de pieza que quedó en la pantalla (`piezas`: {id del ítem: nombre}; si falta, ver
    nombre_de_la_pieza()) y la vida útil de las otras veces. Los km menos que los de la última
    vez se frenan: casi siempre es un número mal tipeado, y un km para atrás desarma la cuenta
    de cuánto le falta a todo lo demás. Una venta se anota en un solo auto, una sola vez."""
    exigir_nivel("empleado", "anotar una venta en la ficha de un auto")
    pat = patente_sin_espacios(patente)
    if len(pat) < 5:
        return False, "Escribí la patente completa.", None
    try:
        km = int(km)
    except (TypeError, ValueError):
        return False, "Los km tienen que ser un número.", None
    if not 0 <= km <= 2_000_000:
        return False, "Los km van de 0 a 2.000.000.", None
    c.execute("SELECT id, vehiculo_id, anulada FROM ventas WHERE id = ?", (venta_id,))
    venta = c.fetchone()
    if not venta or venta["anulada"]:
        return False, "Esa venta no existe o está anulada.", None
    if venta["vehiculo_id"]:
        return False, "Esa venta ya está anotada en la ficha de un auto.", None
    previo = buscar_vehiculo(pat)
    if (previo and previo.get("km_actual") is not None and km < previo["km_actual"]
            and not aunque_tenga_menos_km):
        return (False, f"Son menos km que los anotados la última vez "
                       f"({miles(previo['km_actual'])}). Revisá el número; si está bien, "
                       "confirmalo.", None)
    vehiculo_id = get_or_create_vehiculo(previo["patente"] if previo else pat,
                                         cliente_nombre or "", telefono or "", km_actual=km)
    c.execute("""SELECT id, producto_id, codigo, marca, descripcion FROM ventas_items
                 WHERE venta_id = ? ORDER BY id""", (venta_id,))
    items = [dict(f) for f in c.fetchall()]
    piezas = piezas or {}
    filas = []
    for it in items:
        nombre = (str(piezas.get(it["id"]) or "").strip() or nombre_de_la_pieza(it["descripcion"])
                  or it["codigo"] or "Pieza")
        filas.append((vehiculo_id, it["producto_id"], nombre, it["marca"] or "", it["codigo"] or "",
                      km, vida_util_de_las_otras_veces(nombre, vehiculo_id),
                      vida_util_de_las_otras_veces(nombre, vehiculo_id, "vida_util_meses"),
                      f"Venta #{venta_id}", venta_id))
    # Todo o nada, y el «una sola vez» adentro: dos toques seguidos no la anotan dos veces.
    with db_lock, transaccion():
        c.execute("UPDATE ventas SET vehiculo_id = ?, km = ? WHERE id = ? AND vehiculo_id IS NULL",
                  (vehiculo_id, km, venta_id))
        if c.rowcount != 1:
            return False, "Esa venta ya está anotada en la ficha de un auto.", None
        c.executemany("""INSERT INTO historial_piezas (vehiculo_id, producto_id, descripcion_pieza,
                                                      marca_pieza, codigo_pieza, km_instalacion,
                                                      vida_util_km, vida_util_meses, nota,
                                                      venta_id)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", filas)
    return (True, f"Anotado en la ficha de {pat}: {len(filas)} pieza(s) a los {miles(km)} km.",
            vehiculo_id)


def anular_venta(venta_id):
    """Anula una venta como si no hubiera pasado: devuelve al stock lo que se descontó, saca de
    la ficha del auto las piezas que se anotaron con ella y lo que la app aprendió de ella, y la
    marca anulada (no se borra: queda a la vista). Solo administrador. (ok, texto).

    Antes solo devolvía el stock: el auto seguía diciendo que se le puso la pieza, y «A quién
    avisar» y el link del cliente contaban desde un cambio que no pasó. Lo anotado antes de que
    cada pieza supiera de qué venta salió se reconoce por la nota «Venta #N» en ese auto."""
    exigir_nivel("admin", "anular una venta")
    with db_lock, transaccion():
        c.execute("""UPDATE ventas SET anulada = 1, anulada_por = ?
                     WHERE id = ? AND anulada = 0""", (obtener_usuario_actual(), venta_id))
        if c.rowcount != 1:
            return False, "Esa venta no existe o ya estaba anulada."
        c.execute("""SELECT producto_id, stock_descontado FROM ventas_items
                     WHERE venta_id = ? AND stock_descontado > 0 AND producto_id IS NOT NULL""",
                  (venta_id,))
        for f in c.fetchall():
            c.execute("UPDATE productos SET stock = COALESCE(stock, 0) + ? WHERE id = ?",
                      (f["stock_descontado"], f["producto_id"]))
        c.execute("""SELECT v.vehiculo_id, ve.patente FROM ventas v
                     LEFT JOIN vehiculos ve ON ve.id = v.vehiculo_id WHERE v.id = ?""",
                  (venta_id,))
        auto = c.fetchone()
        c.execute("""DELETE FROM historial_piezas
                     WHERE venta_id = ? OR (venta_id IS NULL AND vehiculo_id = ? AND nota = ?)""",
                  (venta_id, auto["vehiculo_id"], f"Venta #{venta_id}"))
        sacadas = c.rowcount
        c.execute("DELETE FROM ventas_registradas WHERE venta_id = ?", (venta_id,))
    return True, (f"Venta #{venta_id} anulada: lo que se había descontado volvió al stock"
                  + (f", y se sacaron {sacadas} pieza(s) de la ficha de {auto['patente']}"
                     if sacadas else "") + ".")


def ventas_del_dia(dia=None):
    """Las ventas de un día (hoy, si no se dice), la última primero, con sus ítems. [dict]."""
    dia = dia or datetime.now().strftime("%Y-%m-%d")
    c.execute("""SELECT v.id, substr(v.fecha, 12, 5) AS hora, v.usuario, v.cliente,
                        v.forma_de_pago, v.total, v.anulada, v.km, ve.patente
                 FROM ventas v LEFT JOIN vehiculos ve ON ve.id = v.vehiculo_id
                 WHERE substr(v.fecha, 1, 10) = ? ORDER BY v.id DESC""", (dia,))
    ventas = [dict(f) for f in c.fetchall()]
    for v in ventas:
        c.execute("""SELECT codigo, marca, descripcion, cantidad, precio FROM ventas_items
                     WHERE venta_id = ? ORDER BY id""", (v["id"],))
        v["items"] = [dict(f) for f in c.fetchall()]
    return ventas


def se_lleva(producto_id):
    """¿Está marcada la casilla «Se lleva» de este renglón del presupuesto? Marcada salvo que se
    la haya destildado. Ver pasar_el_presupuesto_a_una_venta()."""
    item = (st.session_state.get("carrito") or {}).get(producto_id) or {}
    return bool(st.session_state.get(f"se_lleva_{producto_id}", item.get("se_lleva", True)))


def pasar_el_presupuesto_a_una_venta():
    """Callback de «🧾 Pasar a una venta» en el presupuesto del buscador: lo que se estaba
    armando pasa a la venta, y la pantalla va a 🧾 Ventas. Como callback, porque la sección
    elegida es la clave de un widget ya dibujado (ver ir_a_donde_dice_el_aviso()).

    SOLO LO QUE SE LLEVA. Cada renglón tiene su casilla «Se lleva», marcada de entrada: si no se
    toca nada pasa todo, como antes. Lo que se destilda —el cliente pidió presupuesto de cuatro
    cosas y se lleva tres— no pasa y queda en el presupuesto, destildado, para mandarlo o
    vaciarlo después. Sin ninguna marcada no se va a Ventas: no hay nada que cobrar."""
    carrito = st.session_state.get("carrito") or {}
    elegidos = [pid for pid in carrito if se_lleva(pid)]
    if not elegidos:
        avisar("warning", "No hay nada marcado en «Se lleva»: marcá lo que se lleva el cliente.")
        return
    venta = st.session_state.setdefault("venta_items", [])
    for producto_id in elegidos:
        item = carrito.pop(producto_id)
        st.session_state.pop(f"cant_cart_{producto_id}", None)
        st.session_state.pop(f"se_lleva_{producto_id}", None)
        fila = item_de_venta(producto_id, item.get("cantidad") or 1)
        if not fila:
            continue
        ya = next((x for x in venta if x["producto_id"] == fila["producto_id"]), None)
        if ya:
            ya["cantidad"] += fila["cantidad"]
            # El campo de la cantidad en la pantalla guarda lo suyo: sin esto no se sumaba.
            st.session_state.pop(f"venta_cant_{fila['producto_id']}", None)
        else:
            venta.append(fila)
    # Lo que no se lleva queda destildado: si vuelve a la venta, que sea porque alguien lo marcó.
    for producto_id, item in carrito.items():
        item["se_lleva"] = False
        st.session_state.pop(f"se_lleva_{producto_id}", None)
    if carrito:
        avisar("info", f"Pasaron {len(elegidos)} a la venta. {len(carrito)} quedaron en el "
                       "presupuesto del 🔍 Buscador, sin marcar.")
    st.session_state["pagina_actual"] = PAGINAS[9]

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
        # El campo de la cantidad guarda lo suyo: se pone al día antes de dibujarse (ver «LO
        # QUE CAMBIA POR ATRÁS» en logica/interfaz.py). Sin esto, el «+1» no se veía.
        poner_en_el_campo(f"venta_cant_{fila['ID']}", ya["cantidad"])
        return ya
    nuevo = item_de_venta(fila["ID"], 1, pedido)
    if nuevo:
        nuevo.update(veredicto=veredicto, evidencia=evidencia, confirmado=confirmado)
        venta.append(nuevo)
    return nuevo


def sumar_lo_que_tengo_a_la_venta(persona=None):
    """«➕ Sumar a la venta» lo que `persona` (quien atiende) tiene del depósito sin vender: lo
    pidió para un cliente, y al cobrarlo no hace falta buscarlo otra vez. Cada producto queda en
    la venta con, por lo menos, lo que tiene (lo que ya estaba con más, queda como estaba). Al
    cerrarla sale de lo que tiene, sin bajar el stock otra vez (ver cerrar_venta()). Devuelve
    cuántos productos se sumaron o cambiaron."""
    por_producto = {}
    for r in lo_que_tiene(persona=persona or obtener_usuario_actual()):
        por_producto[r["producto_id"]] = por_producto.get(r["producto_id"], 0) + r["queda"]
    venta = st.session_state.setdefault("venta_items", [])
    cambiados = 0
    for producto_id, tiene in por_producto.items():
        tiene = min(tiene, CANTIDAD_MAXIMA_POR_PEDIDO)
        ya = next((x for x in venta if x["producto_id"] == producto_id), None)
        if ya is None:
            nuevo = item_de_venta(producto_id, tiene)
            if nuevo:
                venta.append(nuevo)
                cambiados += 1
        elif ya["cantidad"] < tiene:
            ya["cantidad"] = tiene
            poner_en_el_campo(f"venta_cant_{producto_id}", tiene)
            cambiados += 1
    return cambiados


def cambiar_cantidad_en_la_venta(producto_id, cuanto):
    """«➕ Uno más» y «➖ Uno menos» de un ítem de la venta (el menú del click derecho), entre 1
    y el máximo de un pedido. Va como on_click."""
    ya = next((x for x in st.session_state.get("venta_items") or []
               if x["producto_id"] == producto_id), None)
    if ya:
        ya["cantidad"] = max(1, min(CANTIDAD_MAXIMA_POR_PEDIDO, int(ya["cantidad"]) + cuanto))
        poner_en_el_campo(f"venta_cant_{producto_id}", ya["cantidad"])


def quitar_de_la_venta(producto_id):
    """«🗑️ Quitar» un ítem de la venta, con lo que guardan sus campos: si se vuelve a sumar,
    arranca de 1 y con su precio. Va como on_click."""
    venta = st.session_state.setdefault("venta_items", [])
    venta[:] = [x for x in venta if x["producto_id"] != producto_id]
    st.session_state.pop(f"venta_cant_{producto_id}", None)
    st.session_state.pop(f"venta_precio_{producto_id}", None)


def lo_que_se_termino(venta_id):
    """Lo vendido en esa venta que quedó con stock 0: [(producto_id, «marca código»)]. Para
    decir que se terminó y que ya quedó anotado para reponer (ver anotar_lo_que_se_termino())."""
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
    # Lo que espera en la caja todavía no entró: va aparte (ver «LA CAJA APARTE»).
    validas = [v for v in ventas if not v["anulada"] and v["cobrada"]]
    a_cobrar = [v for v in ventas if not v["anulada"] and not v["cobrada"]]
    # LO DEVUELTO ESE DÍA sale de ese día, por donde entró (la forma de pago de la venta) y de
    # quien lo devolvió: es lo que tiene que faltar en el cajón. Ver devolver_de_una_venta().
    devueltas = devoluciones_del_dia(dia)

    def agrupar(campo, vacio, campo_devolucion):
        grupos = {}
        for v in validas:
            g = grupos.setdefault(v[campo] or vacio, [0, 0.0])
            g[0] += 1
            g[1] += v["total"] or 0
        for d in devueltas:
            grupos.setdefault(d[campo_devolucion] or vacio, [0, 0.0])[1] -= d["importe"]
        return sorted(((k, n, round(t, 2)) for k, (n, t) in grupos.items()),
                      key=lambda x: -x[2])
    anuladas = [v for v in ventas if v["anulada"]]
    # LA GANANCIA, con el costo que tenía cada cosa al venderla, y solo de lo que tiene costo
    # cargado: cuántos lo tienen va al lado, para no leer «ganancia del día» donde es una parte.
    items = [it for v in validas for it in v["items"]]
    con_costo = [it for it in items if it.get("costo") is not None]
    total_devuelto = round(sum(d["importe"] for d in devueltas), 2)
    return {"ventas": len(validas),
            "total": round(sum(v["total"] or 0 for v in validas) - total_devuelto, 2),
            "ganancia": round(sum((it["precio"] - it["costo"]) * it["cantidad"]
                                  for it in con_costo)
                              - sum((d["precio"] - d["costo"]) * d["cantidad"]
                                    for d in devueltas if d["costo"] is not None), 2),
            "items": len(items), "items_con_costo": len(con_costo),
            "por_forma": agrupar("forma_de_pago", "Sin decir", "forma_de_pago"),
            "por_usuario": agrupar("usuario", "Sin decir", "usuario"),
            "devoluciones": len(devueltas), "total_devuelto": total_devuelto,
            "anuladas": len(anuladas),
            "total_anulado": round(sum(v["total"] or 0 for v in anuladas), 2),
            "a_cobrar": len(a_cobrar),
            "total_a_cobrar": round(sum(v["total"] or 0 for v in a_cobrar), 2)}


def cerrar_venta(items, cliente="", forma_de_pago="", usuario=None, mecanico_id=None,
                 a_la_caja=False):
    """Cierra la venta. Devuelve (venta_id, avisos). Ver «VENTAS DEL MOSTRADOR».

    `a_la_caja`: la venta queda esperando en la caja, sin forma de pago, hasta que el cajero
    la cobra o la pone a cuenta (ver «LA CAJA APARTE»). `mecanico_id`: la cuenta a la que se
    vendió (None: Mostrador). El stock baja igual ahora: el cliente se lleva la pieza.

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
        total = round(sum(x[1] * x[2] for x in limpios), 2)
        c.execute("""INSERT INTO ventas (usuario, cliente, forma_de_pago, total, cobrada,
                                         mecanico_id, total_de_lista)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (usuario, (cliente or "").strip(), "" if a_la_caja else (forma_de_pago or ""),
                   total, 0 if a_la_caja else 1, mecanico_id or None, total))
        venta_id = c.lastrowid
        for producto_id, cantidad, precio, pedido, veredicto, evidencia in limpios:
            c.execute("""SELECT p.stock, p.codigo_raw, p.descripcion, p.precio_costo,
                                m.nombre AS marca
                         FROM productos p JOIN marcas m ON m.id = p.marca_id WHERE p.id = ?""",
                      (producto_id,))
            f = c.fetchone()
            if not f:
                raise ValueError("Uno de los productos ya no está en el catálogo.")
            # LO QUE EL VENDEDOR YA TIENE DEL DEPÓSITO se vende primero: ya bajó del stock al
            # entregarlo, y bajarlo otra vez era vender dos y descontar cuatro. Deja de estar a su
            # nombre. Ver «LO QUE QUEDA AFUERA» en logica/deposito.py.
            de_la_mano, resto = [], cantidad
            for pedido_id, queda in lo_que_tiene_para_vender(usuario, producto_id):
                if resto <= 0:
                    break
                de_la_mano.append((pedido_id, min(queda, resto)))
                resto -= min(queda, resto)
            # EL STOCK, COMO EL DEPÓSITO: nunca negativo, y si no alcanzaba se anota para
            # contarlo. Si se vendió, estaba: el número estaba mal.
            descontado = 0
            if f["stock"] is not None and resto:
                descontado = min(resto, max(f["stock"], 0))
                c.execute("UPDATE productos SET stock = MAX(0, stock - ?) WHERE id = ?",
                          (resto, producto_id))
                if descontado < resto:
                    anotar_cambio("vendió con stock de menos", "producto", producto_id,
                                  {"stock": f["stock"]}, {"stock": 0},
                                  f"se vendieron {resto} y figuraban {f['stock']}: conviene "
                                  "contarlo", usuario=usuario)
                    avisos.append(f"{f['codigo_raw']}: se vendieron {resto} y figuraban "
                                  f"{f['stock']} en stock. Quedó en 0: conviene contarlo.")
            c.execute("""INSERT INTO ventas_items (venta_id, producto_id, codigo, marca,
                                                   descripcion, cantidad, precio, pedido,
                                                   stock_descontado, costo)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (venta_id, producto_id, f["codigo_raw"], f["marca"], f["descripcion"],
                       cantidad, precio, pedido, descontado, f["precio_costo"]))
            item_id = c.lastrowid
            # Lo que aprende de las ventas, como «Se llevó»: lo que pidió el cliente y lo que
            # se llevó. Ver descubrir_equivalencias_candidatas(). Lo que salió de la mano del
            # vendedor ya se había anotado al entregarlo: ese renglón pasa a ser el de esta
            # venta, en vez de anotarlo dos veces.
            _pedido = pedido or f["codigo_raw"]
            _aprendido = (_pedido, sanitizar(_pedido), usuario, veredicto,
                          como_se_vende(veredicto), evidencia, venta_id)
            for pedido_id, n in de_la_mano:
                c.execute("UPDATE pedidos_deposito SET vendidos = COALESCE(vendidos, 0) + ? "
                          "WHERE id = ?", (n, pedido_id))
                c.execute("""INSERT INTO ventas_del_deposito (venta_item_id, pedido_id, cantidad)
                             VALUES (?, ?, ?)""", (item_id, pedido_id, n))
                # Solo el renglón que todavía no es de ninguna venta: si una parte del pedido ya
                # se vendió antes, ese renglón es de aquella venta, y anular esta se lo llevaría.
                c.execute("""UPDATE ventas_registradas SET termino_pedido = ?,
                                    codigo_pedido_clean = ?, usuario = ?, veredicto = ?, como = ?,
                                    evidencia = ?, venta_id = ?
                             WHERE pedido_id = ? AND venta_id IS NULL""", _aprendido + (pedido_id,))
                if not c.rowcount:
                    c.execute("""INSERT INTO ventas_registradas
                                    (producto_id, termino_pedido, codigo_pedido_clean, usuario,
                                     veredicto, como, evidencia, venta_id, pedido_id)
                                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                              (producto_id,) + _aprendido + (pedido_id,))
            if resto:
                c.execute("""INSERT INTO ventas_registradas (producto_id, termino_pedido,
                                                             codigo_pedido_clean, usuario,
                                                             veredicto, como, evidencia, venta_id)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (producto_id,) + _aprendido)
    # Lo que se terminó con esta venta queda anotado para reponer solo (ver
    # anotar_lo_que_se_termino()).
    anotar_lo_que_se_termino([x[0] for x in limpios], usuario)
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
        # Con algo ya devuelto no: la plata de esa devolución ya salió de la caja de otro día,
        # y anularla la sacaría dos veces. Se devuelve lo que queda.
        if c.execute("SELECT 1 FROM ventas_devoluciones WHERE venta_id = ? LIMIT 1",
                     (venta_id,)).fetchone():
            return False, (f"La venta #{venta_id} tiene devoluciones: no se anula. Devolvé lo "
                           "que queda desde «↩️ Buscar una venta y devolver».")
        c.execute("""UPDATE ventas SET anulada = 1, anulada_por = ?
                     WHERE id = ? AND anulada = 0""", (obtener_usuario_actual(), venta_id))
        if c.rowcount != 1:
            return False, "Esa venta no existe o ya estaba anulada."
        # Si se había puesto a cuenta, el cargo de la cuenta también queda anulado: si no, el
        # taller seguía debiendo algo que no se llevó. Ver poner_a_cuenta().
        c.execute("""UPDATE movimientos_de_cuenta SET anulado = 1
                     WHERE id = (SELECT movimiento_id FROM ventas WHERE id = ?)""", (venta_id,))
        c.execute("""SELECT producto_id, stock_descontado FROM ventas_items
                     WHERE venta_id = ? AND stock_descontado > 0 AND producto_id IS NOT NULL""",
                  (venta_id,))
        for f in c.fetchall():
            c.execute("UPDATE productos SET stock = COALESCE(stock, 0) + ? WHERE id = ?",
                      (f["stock_descontado"], f["producto_id"]))
        # Lo que había salido de lo que el vendedor tenía del depósito vuelve a estar a su
        # nombre, no al stock: el stock no se había tocado. Ver «LO QUE QUEDA AFUERA».
        c.execute("""SELECT dd.pedido_id, dd.cantidad FROM ventas_del_deposito dd
                     JOIN ventas_items vi ON vi.id = dd.venta_item_id WHERE vi.venta_id = ?""",
                  (venta_id,))
        for f in c.fetchall():
            c.execute("UPDATE pedidos_deposito SET vendidos = MAX(0, COALESCE(vendidos, 0) - ?) "
                      "WHERE id = ?", (f["cantidad"], f["pedido_id"]))
        c.execute("""DELETE FROM ventas_del_deposito WHERE venta_item_id IN
                         (SELECT id FROM ventas_items WHERE venta_id = ?)""", (venta_id,))
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
    # El día de la caja es el día en que se cobró (la plata entra ese día); lo que espera en la
    # caja, el día en que se vendió.
    c.execute("""SELECT v.id, substr(v.fecha, 12, 5) AS hora, v.usuario, v.cliente,
                        v.forma_de_pago, v.total, v.anulada, v.km, ve.patente,
                        COALESCE(v.cobrada, 1) AS cobrada, v.cuotas,
                        COALESCE(v.descuento, 0) AS descuento, v.cobrada_por,
                        k.nombre AS cuenta
                 FROM ventas v LEFT JOIN vehiculos ve ON ve.id = v.vehiculo_id
                 LEFT JOIN mecanicos k ON k.id = v.mecanico_id
                 WHERE substr(COALESCE(v.cobrada_en, v.fecha), 1, 10) = ?
                 ORDER BY v.id DESC""", (dia,))
    ventas = [dict(f) for f in c.fetchall()]
    for v in ventas:
        c.execute("""SELECT id, codigo, marca, descripcion, cantidad, precio, costo,
                            COALESCE(devuelto, 0) AS devuelto
                     FROM ventas_items WHERE venta_id = ? ORDER BY id""", (v["id"],))
        v["items"] = [dict(f) for f in c.fetchall()]
    return ventas


def devoluciones_del_dia(dia=None):
    """Lo que se devolvió en un día (hoy, si no se dice), de ventas no anuladas: con la forma de
    pago de la venta (la plata vuelve por donde entró) y el precio y el costo del ítem. [dict]."""
    dia = dia or datetime.now().strftime("%Y-%m-%d")
    c.execute("""SELECT d.id, d.venta_id, d.cantidad, d.importe, d.motivo, d.usuario,
                        substr(d.fecha, 12, 5) AS hora, v.forma_de_pago, vi.marca, vi.codigo,
                        vi.precio, vi.costo
                 FROM ventas_devoluciones d JOIN ventas v ON v.id = d.venta_id
                 JOIN ventas_items vi ON vi.id = d.venta_item_id
                 WHERE substr(d.fecha, 1, 10) = ? AND v.anulada = 0 ORDER BY d.id""", (dia,))
    return [dict(f) for f in c.fetchall()]


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
            poner_en_el_campo(f"venta_cant_{fila['producto_id']}", ya["cantidad"])
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


def una_venta(venta_id):
    """Una venta con sus ítems y la patente, o None. Ver texto_del_comprobante()."""
    c.execute("""SELECT v.id, v.fecha, v.usuario, v.cliente, v.forma_de_pago, v.total, v.anulada,
                        v.km, ve.patente, COALESCE(v.cobrada, 1) AS cobrada, v.cuotas,
                        COALESCE(v.descuento, 0) AS descuento, v.total_de_lista, v.mecanico_id,
                        k.nombre AS cuenta
                 FROM ventas v LEFT JOIN vehiculos ve ON ve.id = v.vehiculo_id
                 LEFT JOIN mecanicos k ON k.id = v.mecanico_id WHERE v.id = ?""",
              (venta_id,))
    venta = c.fetchone()
    if not venta:
        return None
    venta = dict(venta)
    c.execute("""SELECT id, codigo, marca, descripcion, cantidad, precio,
                        COALESCE(devuelto, 0) AS devuelto
                 FROM ventas_items WHERE venta_id = ? ORDER BY id""", (venta_id,))
    venta["items"] = [dict(f) for f in c.fetchall()]
    return venta


# EL COMPROBANTE PARA EL CLIENTE: lo que se llevó y lo que pagó, por WhatsApp o en PDF. No es
# una factura y lo dice: la factura sale del sistema de facturación de la AFIP.
NO_ES_FACTURA = "Comprobante interno: no válido como factura."


def texto_del_comprobante(venta_id):
    """El comprobante de una venta, para mandarlo por WhatsApp. "" si no existe."""
    venta = una_venta(venta_id)
    if not venta:
        return ""
    lineas = [f"Tu compra en El Chavo — #{venta['id']} — {venta['fecha'][:16]}"]
    lineas += [f"{it['cantidad']}× {it['marca']} {it['codigo']} — "
               f"{(it['descripcion'] or '')[:40]} — ${miles(it['cantidad'] * it['precio'], 0)}"
               + (f" (devueltos: {it['devuelto']})" if it["devuelto"] else "")
               for it in venta["items"]]
    if venta["descuento"]:
        lineas.append(f"Descuento {como_porcentaje(venta['descuento'])}% (era "
                      f"${miles(venta['total_de_lista'] or 0, 0)})")
    lineas.append(f"TOTAL: ${miles(venta['total'] or 0, 0)}"
                  + (f" ({como_se_pago(venta)})" if venta["forma_de_pago"] else ""))
    if not venta["cobrada"] and not venta["anulada"]:
        lineas.append("PENDIENTE DE COBRO")
    if venta["anulada"]:
        lineas.append("ANULADA")
    lineas += ["", "¡Gracias por tu compra!", NO_ES_FACTURA]
    return "\n".join(lineas)


def comprobante_para_descargar(venta_id):
    """Para el botón de descarga: los datos de la venta se leen ahora, y el PDF se arma recién
    al tocar el botón (Streamlit lo corre en otro hilo, que no tiene que tocar la base). Así no
    se arma un PDF en cada toque de la pantalla, y si armarlo fallara, no se cae Ventas."""
    venta = una_venta(venta_id)
    return lambda: pdf_del_comprobante(venta)


def pdf_del_comprobante(venta):
    """El comprobante de una venta ya leída (ver una_venta()) en PDF, para imprimirlo o
    mandarlo. b"" si no hay venta."""
    from fpdf import FPDF
    if not venta:
        return b""

    def limpiar(texto):
        # Las fuentes básicas de fpdf2 no traen todo unicode: ver generar_pdf_cotizacion().
        return str(texto).replace("×", "x").encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, limpiar(f"El Chavo - Comprobante de venta #{venta['id']}"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    _fecha = datetime.strptime(venta["fecha"][:16], "%Y-%m-%d %H:%M")
    pdf.cell(0, 6, limpiar(f"Fecha: {_fecha:%d/%m/%Y %H:%M}"
                           + (f"   Cliente: {venta['cliente']}" if venta["cliente"] else "")
                           + (f"   Patente: {venta['patente']}" if venta["patente"] else "")),
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 10)
    for texto, ancho in (("Cant.", 15), ("Producto", 125), ("Importe", 40)):
        pdf.cell(ancho, 7, texto, border="B", align="R" if texto == "Importe" else "L")
    pdf.ln()
    pdf.set_font("Helvetica", "", 10)
    for it in venta["items"]:
        pdf.cell(15, 7, str(it["cantidad"]))
        # Más corta si lleva lo devuelto: la celda no corta, se pisaría con el importe.
        _largo = 40 if it["devuelto"] else 55
        pdf.cell(125, 7, limpiar(f"{it['marca']} {it['codigo']} - {(it['descripcion'] or '')[:_largo]}"
                                 + (f" (devueltos: {it['devuelto']})" if it["devuelto"] else "")))
        pdf.cell(40, 7, limpiar(f"${miles(it['cantidad'] * it['precio'], 0)}"), align="R")
        pdf.ln()
    pdf.set_font("Helvetica", "B", 12)
    if venta.get("descuento"):
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(140, 7, limpiar(f"Descuento {como_porcentaje(venta['descuento'])}% (era "
                                 f"${miles(venta.get('total_de_lista') or 0, 0)})"))
        pdf.ln()
        pdf.set_font("Helvetica", "B", 12)
    pdf.cell(140, 9, limpiar("TOTAL" + (f" ({como_se_pago(venta)})"
                                         if venta["forma_de_pago"] else "")), border="T")
    pdf.cell(40, 9, limpiar(f"${miles(venta['total'] or 0, 0)}"), border="T", align="R")
    pdf.ln(12)
    pdf.set_font("Helvetica", "I", 9)
    if not venta.get("cobrada", 1) and not venta["anulada"]:
        pdf.cell(0, 6, "PENDIENTE DE COBRO", new_x="LMARGIN", new_y="NEXT")
    if venta["anulada"]:
        pdf.cell(0, 6, "ANULADA", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, limpiar(NO_ES_FACTURA), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def producto_por_codigo_de_barras(texto):
    """El id del producto si `texto` es un código de barras que cierra (ver
    codigo_de_barras_cierra()) y lo tiene uno solo; si no, None. Para escanear en 🧾 Ventas y
    que se sume solo: el lector de la caja escribe los números y un Enter, como un teclado.
    Que cierre, y no solo que sean números: un código de fábrica tipeado a mano («19011403»)
    tiene que mostrar sus equivalencias, no sumarse solo porque algún producto tenga ese número
    mal cargado como código de barras."""
    numeros = re.sub(r"\s", "", str(texto or ""))
    if not (numeros.isdigit() and codigo_de_barras_cierra(numeros)):
        return None
    c.execute("SELECT id FROM productos WHERE codigo_barras = ? LIMIT 2", (numeros,))
    filas = c.fetchall()
    return filas[0]["id"] if len(filas) == 1 else None


def lo_mas_vendido(dias=30, tope=10):
    """Lo que entró en los últimos `dias` días (hoy incluido) y qué se vendió más, por unidades
    y por plata, sin las anuladas. La ganancia, con el costo de cada venta y solo de lo que lo
    tiene. dict."""
    hoy = datetime.now().date()
    desde = hoy - timedelta(days=int(dias) - 1)
    c.execute("""SELECT substr(fecha, 1, 10) AS dia, COUNT(*) AS ventas, SUM(total) AS total
                 FROM ventas WHERE anulada = 0 AND substr(fecha, 1, 10) >= ?
                 GROUP BY dia""", (desde.isoformat(),))
    del_dia = {f["dia"]: [f["ventas"], f["total"] or 0] for f in c.fetchall()}
    # Lo devuelto, el día que se devolvió: ver cierre_de_caja().
    c.execute("""SELECT substr(d.fecha, 1, 10) AS dia, SUM(d.importe) AS importe
                 FROM ventas_devoluciones d JOIN ventas v ON v.id = d.venta_id
                 WHERE v.anulada = 0 AND substr(d.fecha, 1, 10) >= ? GROUP BY dia""",
              (desde.isoformat(),))
    for f in c.fetchall():
        del_dia.setdefault(f["dia"], [0, 0])[1] -= f["importe"] or 0
    # Todos los días del período, también los que no hubo ventas: sin ellos el gráfico junta
    # un martes con el viernes y parece que se vendió todos los días.
    por_dia = [((desde + timedelta(days=i)).isoformat(),
                del_dia.get((desde + timedelta(days=i)).isoformat(), (0, 0))[1])
               for i in range(int(dias))]
    c.execute("""SELECT vi.marca, vi.codigo, MAX(vi.descripcion) AS descripcion,
                        SUM(vi.cantidad - COALESCE(vi.devuelto, 0)) AS unidades,
                        SUM((vi.cantidad - COALESCE(vi.devuelto, 0)) * vi.precio) AS plata,
                        SUM(CASE WHEN vi.costo IS NOT NULL
                                 THEN (vi.cantidad - COALESCE(vi.devuelto, 0))
                                      * (vi.precio - vi.costo) END) AS ganancia,
                        SUM(CASE WHEN vi.costo IS NOT NULL
                                 THEN (vi.cantidad - COALESCE(vi.devuelto, 0)) * vi.precio
                            END) AS plata_con_costo,
                        SUM(CASE WHEN p.precio_costo IS NOT NULL
                                 THEN (vi.cantidad - COALESCE(vi.devuelto, 0))
                                      * (vi.precio - p.precio_costo) END) AS ganancia_hoy,
                        COUNT(DISTINCT vi.venta_id) AS ventas
                 FROM ventas_items vi JOIN ventas v ON v.id = vi.venta_id
                      LEFT JOIN productos p ON p.id = vi.producto_id
                 WHERE v.anulada = 0 AND substr(v.fecha, 1, 10) >= ?
                 GROUP BY vi.producto_id, vi.marca, vi.codigo""", (desde.isoformat(),))
    productos = [dict(f) for f in c.fetchall()]
    ventas = sum(n for n, _ in del_dia.values())
    total = round(sum(t for _, t in del_dia.values()), 2)
    return {"desde": desde.isoformat(), "ventas": ventas, "total": total,
            "ticket_promedio": round(total / ventas, 2) if ventas else 0,
            "ganancia": round(sum(p["ganancia"] or 0 for p in productos), 2),
            "por_dia": por_dia,
            "por_unidades": sorted(productos, key=lambda p: (-p["unidades"], -p["plata"]))[:tope],
            "por_plata": sorted(productos, key=lambda p: (-p["plata"], -p["unidades"]))[:tope],
            "por_marca": ganancia_por_marca(productos)}


def ganancia_por_marca(productos):
    """Lo vendido y lo ganado por cada marca, la que más ganó primero: [{marca, unidades, plata,
    ganancia, margen, sin_costo}]. Lo pidió una revisión con Gemini («margen real por marca y
    proveedor»): el total del período no dice qué marca deja plata y cuál se vende mucho para
    ganar poco. La ganancia es con el costo que tenía cada cosa AL VENDERLA (queda guardado en
    la venta), así que un aumento de costo después no la cambia. El margen es sobre lo vendido
    que tiene costo; lo que se vendió sin costo cargado va aparte («sin_costo», en plata): con
    mucho de eso, el margen de la marca dice poco.

    «ganancia_hoy» es la otra cara, la que pidió la misma revisión («descontando las variaciones
    de costo por inflación»): lo que queda si hubiera que REPONER lo vendido al costo cargado
    hoy. Con precios que suben todos los meses, vender a $10.000 algo que costó $7.000 parece
    ganar $3.000; si reponerlo hoy cuesta $9.500, se ganó $500. None si no hay costo de hoy."""
    marcas = {}
    for p in productos:
        m = marcas.setdefault(p["marca"] or "—", {"marca": p["marca"] or "—", "unidades": 0,
                                                    "plata": 0.0, "ganancia": 0.0,
                                                    "con_costo": 0.0, "ganancia_hoy": None})
        m["unidades"] += p["unidades"] or 0
        m["plata"] += p["plata"] or 0
        m["ganancia"] += p["ganancia"] or 0
        m["con_costo"] += p["plata_con_costo"] or 0
        if p.get("ganancia_hoy") is not None:
            m["ganancia_hoy"] = (m["ganancia_hoy"] or 0) + p["ganancia_hoy"]
    salida = []
    for m in marcas.values():
        salida.append({"marca": m["marca"], "unidades": m["unidades"],
                       "plata": round(m["plata"], 2), "ganancia": round(m["ganancia"], 2),
                       "margen": (round(m["ganancia"] / m["con_costo"] * 100, 1)
                                  if m["con_costo"] else None),
                       "sin_costo": round(m["plata"] - m["con_costo"], 2),
                       "ganancia_hoy": (round(m["ganancia_hoy"], 2)
                                        if m["ganancia_hoy"] is not None else None)})
    return sorted(salida, key=lambda m: (-m["ganancia"], -m["plata"]))


# ============================================================================================
# DEVOLVER ALGO DE UNA VENTA
# ============================================================================================
# Hasta acá, lo que volvía se anotaba solo en la ficha de prueba de una equivalencia: no volvía
# al stock, no salía de la caja, y desde 🧾 Ventas lo único que había era anular la venta entera
# (y eso es de administrador). Ahora se devuelve una cosa y una cantidad:
#   · vuelve al stock, salvo que no se pueda volver a vender (fallada, llegó dañada, la
#     modificaron): ver NO_VUELVE_AL_STOCK;
#   · la plata sale del cierre de caja del día en que se devuelve, por donde entró;
#   · si se vendió EN LUGAR DE otro código, la app aprende como con «↩️ Anotar la devolución»
#     de la ficha de prueba: si no le iba, ese vínculo baja (ver registrar_devolucion());
#   · si vuelve todo lo de ese ítem, sale de la ficha del auto y de lo aprendido de la venta.
NO_VUELVE_AL_STOCK = frozenset({"fallada", "transporte", "modificacion"})


def buscar_ventas(texto, dias=180, tope=20):
    """Las ventas no anuladas de los últimos `dias` días que coinciden con `texto`: el número
    («#12» o «12»), el cliente, la patente o el teléfono del auto. La última primero, con sus
    ítems. [dict]."""
    t = (texto or "").strip()
    if not t:
        return []
    desde = (datetime.now().date() - timedelta(days=int(dias))).isoformat()
    numero = t.lstrip("#").strip()
    digitos = re.sub(r"\D", "", t)
    c.execute("""SELECT v.id FROM ventas v LEFT JOIN vehiculos ve ON ve.id = v.vehiculo_id
                 WHERE v.anulada = 0 AND substr(v.fecha, 1, 10) >= ?
                   AND (CAST(v.id AS TEXT) = ? OR v.cliente LIKE ? OR ve.cliente_nombre LIKE ?
                        OR ve.patente = ?
                        OR (length(?) >= 6 AND REPLACE(REPLACE(REPLACE(REPLACE(
                                ve.cliente_telefono, ' ', ''), '-', ''), '+', ''), '.', '')
                            LIKE '%' || ? || '%'))
                 ORDER BY v.id DESC LIMIT ?""",
              (desde, numero, f"%{t}%", f"%{t}%", patente_sin_espacios(t), digitos, digitos,
               int(tope)))
    return [una_venta(venta_id) for (venta_id,) in [tuple(f) for f in c.fetchall()]]


def devolver_de_una_venta(venta_item_id, cantidad, motivo, detalle=""):
    """Devuelve `cantidad` de un ítem de una venta, por `motivo` (uno de
    MOTIVOS_DE_DEVOLUCION). (ok, texto). Ver «DEVOLVER ALGO DE UNA VENTA»."""
    exigir_nivel("empleado", "devolver algo de una venta")
    if motivo not in MOTIVOS_DE_DEVOLUCION:
        return False, "Elegí por qué volvió."
    try:
        cantidad = int(cantidad)
    except (TypeError, ValueError):
        return False, "La cantidad tiene que ser un número."
    c.execute("""SELECT vi.id, vi.venta_id, vi.producto_id, vi.codigo, vi.marca, vi.cantidad,
                        vi.precio, vi.pedido, COALESCE(vi.devuelto, 0) AS devuelto, v.anulada,
                        COALESCE(v.cobrada, 1) AS cobrada, v.movimiento_id, v.mecanico_id,
                        p.codigo_clean, p.stock
                 FROM ventas_items vi JOIN ventas v ON v.id = vi.venta_id
                 LEFT JOIN productos p ON p.id = vi.producto_id WHERE vi.id = ?""",
              (venta_item_id,))
    it = c.fetchone()
    if not it:
        return False, "Ese ítem no existe."
    if it["anulada"]:
        return False, "Esa venta está anulada."
    if not it["cobrada"]:
        return False, ("Esa venta todavía no se cobró: está esperando en la caja. Si no la va a "
                       "pagar, que la anule un administrador.")
    queda = it["cantidad"] - it["devuelto"]
    if not 1 <= cantidad <= queda:
        return False, (f"De {it['marca']} {it['codigo']} se puede devolver de 1 a {queda}."
                       if queda else f"{it['marca']} {it['codigo']} ya se devolvió entero.")
    al_stock = (cantidad if it["producto_id"] is not None and it["stock"] is not None
                and motivo not in NO_VUELVE_AL_STOCK else 0)
    importe = round(cantidad * it["precio"], 2)
    entero = cantidad == queda
    with db_lock, transaccion():
        c.execute("""UPDATE ventas_items SET devuelto = COALESCE(devuelto, 0) + ?
                     WHERE id = ? AND COALESCE(devuelto, 0) + ? <= cantidad""",
                  (cantidad, venta_item_id, cantidad))
        if c.rowcount != 1:
            return False, "Eso ya se devolvió."
        c.execute("""INSERT INTO ventas_devoluciones (venta_id, venta_item_id, cantidad, importe,
                                                      motivo, detalle, stock_devuelto, usuario)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                  (it["venta_id"], venta_item_id, cantidad, importe, motivo,
                   (detalle or "").strip(), al_stock, obtener_usuario_actual()))
        if al_stock:
            c.execute("UPDATE productos SET stock = stock + ? WHERE id = ?",
                      (al_stock, it["producto_id"]))
        # Lo que se había puesto a cuenta vuelve a la cuenta, no al cajón: se le acredita.
        if it["movimiento_id"] and it["mecanico_id"]:
            c.execute("""INSERT INTO movimientos_de_cuenta (mecanico_id, concepto, importe,
                                                           medio, usuario)
                         VALUES (?, ?, ?, 'Devolución', ?)""",
                      (it["mecanico_id"], f"Devolución de la venta #{it['venta_id']}: "
                                          f"{cantidad}× {it['marca']} {it['codigo']}",
                       -importe, obtener_usuario_actual()))
        if entero and it["producto_id"] is not None:
            # No se le puso al auto, y no se vendió: sale de la ficha y de lo aprendido.
            c.execute("DELETE FROM historial_piezas WHERE venta_id = ? AND producto_id = ?",
                      (it["venta_id"], it["producto_id"]))
            c.execute("DELETE FROM ventas_registradas WHERE venta_id = ? AND producto_id = ?",
                      (it["venta_id"], it["producto_id"]))
    # LO QUE APRENDE, después y aparte (db_lock no se puede tomar dos veces): lo pedido solo si
    # se vendió EN LUGAR DE otro código; si era lo pedido mismo, cuenta para la calidad de la
    # marca pero no baja ningún vínculo. Ver registrar_devolucion().
    bajados = 0
    if it["producto_id"] is not None:
        pedido = it["pedido"] if sanitizar(it["pedido"] or "") not in ("", it["codigo_clean"]) else ""
        try:
            bajados = registrar_devolucion(it["producto_id"], pedido, motivo, detalle)
        except (PermissionError, ValueError) as _err:
            anotar_error("devolver_de_una_venta", _err)
    return True, (f"Devuelto: {cantidad} × {it['marca']} {it['codigo']} (${miles(importe, 0)}"
                  + (" se le acredita a la cuenta)" if it["movimiento_id"] else
                     " sale de la caja de hoy)")
                  + ("" if al_stock or it["stock"] is None else
                     ", y no vuelve al stock: no se puede volver a vender")
                  + (". El vínculo con lo que se había pedido bajó a «muy débil»"
                     if bajados else "") + ".")


def arquear_la_caja(dia, efectivo_contado, nota=""):
    """Anota lo que se contó en el cajón contra el efectivo que dice el cierre de caja de ese
    día (ver cierre_de_caja()). (ok, texto)."""
    exigir_nivel("empleado", "arquear la caja")
    try:
        contado = round(float(efectivo_contado), 2)
    except (TypeError, ValueError):
        return False, "Escribí cuánto efectivo hay."
    if contado < 0:
        return False, "El efectivo no puede ser negativo."
    dia = dia or datetime.now().strftime("%Y-%m-%d")
    esperado = efectivo_esperado(dia)
    with db_lock, transaccion():
        c.execute("""INSERT INTO arqueos_de_caja (dia, efectivo_esperado, efectivo_contado, nota,
                                                  usuario) VALUES (?, ?, ?, ?, ?)""",
                  (dia, esperado, contado, (nota or "").strip(), obtener_usuario_actual()))
    diferencia = round(contado - esperado, 2)
    return True, ("✅ Cierra justo." if not diferencia else
                  f"{'Sobran' if diferencia > 0 else 'Faltan'} ${miles(abs(diferencia), 0)}.")


def efectivo_esperado(dia=None):
    """Lo que tiene que haber en el cajón por las ventas de ese día: lo cobrado en efectivo
    menos lo devuelto de ventas en efectivo. Sin el cambio con el que se abrió."""
    return next((t for f, _, t in cierre_de_caja(dia)["por_forma"] if f == "Efectivo"), 0.0)


def resumen_de_la_caja(dia=None):
    """Lo de arriba de 💵 Caja, del día (hoy, si no se dice): lo que tiene que haber en el
    cajón, lo que entró por tarjeta o transferencia, lo puesto a cuenta (no es plata que entró)
    y lo que espera para cobrarse. dict."""
    caja = cierre_de_caja(dia)
    por_forma = {f: t for f, _, t in caja["por_forma"]}
    efectivo = por_forma.pop("Efectivo", 0.0)
    a_cuenta = por_forma.pop(A_CUENTA, 0.0)
    return {"efectivo": round(efectivo, 2), "otros_medios": round(sum(por_forma.values()), 2),
            "a_cuenta": round(a_cuenta, 2), "ventas": caja["ventas"],
            "esperando": caja["a_cobrar"], "total_esperando": caja["total_a_cobrar"]}


def arqueos_del_dia(dia=None):
    """Los arqueos de un día, el último primero. [dict]."""
    dia = dia or datetime.now().strftime("%Y-%m-%d")
    c.execute("""SELECT substr(fecha, 12, 5) AS hora, efectivo_esperado, efectivo_contado,
                        efectivo_contado - efectivo_esperado AS diferencia, nota, usuario
                 FROM arqueos_de_caja WHERE dia = ? ORDER BY id DESC""", (dia,))
    return [dict(f) for f in c.fetchall()]


def lo_que_se_va_a_terminar(dias=30, alcanza_menos_de=7):
    """Lo que se vende y se va a terminar: con lo vendido en los últimos `dias` días (sin lo
    devuelto) y el stock de hoy, para cuántos días alcanza. Solo lo que alcanza para menos de
    `alcanza_menos_de` días, lo que se termina antes primero. [dict]."""
    desde = (datetime.now().date() - timedelta(days=int(dias) - 1)).isoformat()
    c.execute("""SELECT vi.producto_id, MAX(vi.marca) AS marca, MAX(vi.codigo) AS codigo,
                        SUM(vi.cantidad - COALESCE(vi.devuelto, 0)) AS unidades, p.stock,
                        p.descripcion,
                        EXISTS (SELECT 1 FROM pedidos_reposicion pr
                                WHERE pr.producto_id = vi.producto_id
                                  AND pr.estado = 'pendiente') AS anotado
                 FROM ventas_items vi JOIN ventas v ON v.id = vi.venta_id
                 JOIN productos p ON p.id = vi.producto_id
                 WHERE v.anulada = 0 AND substr(v.fecha, 1, 10) >= ? AND p.stock IS NOT NULL
                 GROUP BY vi.producto_id HAVING unidades > 0""", (desde,))
    salida = []
    for f in c.fetchall():
        por_dia = f["unidades"] / int(dias)
        alcanza = max(f["stock"], 0) / por_dia
        if alcanza < alcanza_menos_de:
            salida.append({"producto_id": f["producto_id"],
                           "nombre": f"{f['marca']} {f['codigo']}",
                           "descripcion": f["descripcion"] or "", "stock": f["stock"],
                           "por_semana": round(por_dia * 7, 1), "alcanza_dias": int(alcanza),
                           "anotado": bool(f["anotado"])})
    return sorted(salida, key=lambda x: (x["alcanza_dias"], -x["por_semana"]))


# ============================================================================================
# LA CAJA APARTE
# ============================================================================================
# Lo pidió el dueño: «dividí la caja de las ventas: cada vez que se realiza una venta, al cajero
# le sale un cartel diciendo quién vendió, a qué cuenta se lo vendió, el monto total y la hora;
# con F10, que elija si lo pagó en efectivo, débito, crédito (con la cantidad de cuotas) o
# transferencia, con un descuento por porcentaje; y con F11, si estás seguro que querés
# ponérselo a cuenta a ese cliente».
#   · El vendedor arma la venta en 🧾 Ventas y la manda a la caja: el stock baja ahí (el cliente
#     se lleva la pieza) y la venta queda esperando, sin forma de pago, con la cuenta a la que se
#     vendió (la de «🧾 Atendiendo a», o Mostrador).
#   · En 💵 Caja aparece con su cartel. El cajero la cobra (ver cobrar_venta()) o la pone a
#     cuenta (ver poner_a_cuenta(), con el límite de crédito como en el depósito). Recién ahí
#     cuenta en el cierre de caja, el día que se cobró. Si se anula, el cargo de la cuenta
#     también; si se devuelve algo de una venta a cuenta, se le acredita a la cuenta.
#   · EL DESCUENTO baja el precio de cada cosa de la venta en ese porcentaje: así las
#     devoluciones, la ganancia y lo más vendido ya lo cuentan, sin hacer nada más. Lo que
#     costaba sin descuento queda en la venta y sale en el comprobante.
#   · Se puede apagar (💵 Caja → «La caja cobra aparte», el administrador): entonces el
#     vendedor cobra al terminar la venta, como antes.
FORMAS_DE_COBRO = ["Efectivo", "Tarjeta de débito", "Tarjeta de crédito", "Transferencia"]
CUOTAS_POSIBLES = [1, 2, 3, 6, 9, 12, 18, 24]
A_CUENTA = "A cuenta"
# Más descuento que esto en la caja es casi seguro un error de tipeo (50 en vez de 5). A cuenta,
# lo que tenga la cuenta, si es más.
DESCUENTO_MAXIMO_EN_LA_CAJA = 50.0


def caja_aparte():
    """¿La caja cobra aparte? Ver «LA CAJA APARTE»."""
    return obtener_config("caja_aparte", "1") == "1"


def cambiar_caja_aparte(valor):
    """Prende o apaga la caja aparte. Solo el administrador."""
    exigir_nivel("admin", "cambiar cómo se cobran las ventas")
    guardar_config("caja_aparte", "1" if valor else "0")
    anotar_cambio("prendió la caja aparte" if valor else "apagó la caja aparte", "caja", "")


def como_porcentaje(valor):
    """«10» y no «10,0»; «12,5» si tiene decimales."""
    valor = float(valor or 0)
    return miles(valor, 0 if valor.is_integer() else 1)


def como_se_pago(venta):
    """«Tarjeta de crédito, 3 cuotas», «a la cuenta de Taller Norte», «Efectivo»."""
    forma = venta.get("forma_de_pago") or ""
    if forma == "Tarjeta de crédito" and (venta.get("cuotas") or 1) > 1:
        return f"{forma}, {venta['cuotas']} cuotas"
    if forma == A_CUENTA and venta.get("cuenta"):
        return f"a la cuenta de {venta['cuenta']}"
    return forma


def ventas_a_cobrar():
    """Lo que espera en la caja, lo más viejo primero: [dict] con quién vendió, a qué cuenta,
    el total, la hora y lo que se lleva."""
    c.execute("""SELECT v.id, v.fecha, substr(v.fecha, 12, 5) AS hora, v.usuario, v.cliente,
                        v.total, v.mecanico_id, k.nombre AS cuenta
                 FROM ventas v LEFT JOIN mecanicos k ON k.id = v.mecanico_id
                 WHERE v.cobrada = 0 AND v.anulada = 0 ORDER BY v.id""")
    # «v.cobrada = 0» y no «COALESCE(v.cobrada, 1) = 0» (dan lo mismo: la vieja sin el dato
    # cuenta como cobrada): con el COALESCE la base recorría todas las ventas de la historia
    # cada 5 segundos, mientras la caja está abierta, en vez de usar idx_ventas_a_cobrar.
    ventas = [dict(f) for f in c.fetchall()]
    for v in ventas:
        c.execute("""SELECT codigo, marca, descripcion, cantidad, precio FROM ventas_items
                     WHERE venta_id = ? ORDER BY id""", (v["id"],))
        v["items"] = [dict(f) for f in c.fetchall()]
    return ventas


def el_cartel_de(venta):
    """Lo que le dice el cartel al cajero: quién vendió, a qué cuenta, el total y la hora."""
    para = (venta.get("cuenta") or (f"{venta['cliente']}, de Mostrador" if venta.get("cliente")
                                    else "Mostrador"))
    return (f"🧾 Venta #{venta['id']} — vendió {venta.get('usuario') or '¿?'} · para {para} · "
            f"${miles(venta.get('total') or 0, 0)} · {venta.get('hora') or ''}")


def total_con_descuento(venta_id, descuento):
    """Lo que queda la venta con ese descuento, redondeado como al cobrarla."""
    c.execute("SELECT cantidad, precio FROM ventas_items WHERE venta_id = ?", (venta_id,))
    return round(sum(f["cantidad"] * round(float(f["precio"] or 0)
                                           * (1 - float(descuento or 0) / 100), 2)
                     for f in c.fetchall()), 2)


def _descuento_valido(descuento, tope):
    try:
        descuento = round(float(descuento or 0), 2)
    except (TypeError, ValueError):
        raise ValueError("El descuento tiene que ser un número.")
    if not 0 <= descuento <= tope:
        raise ValueError(f"El descuento va de 0 a {miles(tope, 0)}%.")
    return descuento


def _aplicar_el_descuento(venta_id, descuento):
    """Adentro de la transacción del cobro: el precio de cada cosa, con el descuento; devuelve
    el total nuevo (el que llama lo guarda en la venta)."""
    if descuento:
        c.execute("""UPDATE ventas_items SET precio = ROUND(precio * (1 - ? / 100.0), 2)
                     WHERE venta_id = ?""", (descuento, venta_id))
    c.execute("SELECT COALESCE(SUM(cantidad * precio), 0) FROM ventas_items WHERE venta_id = ?",
              (venta_id,))
    return round(float(c.fetchone()[0]), 2)


def cobrar_venta(venta_id, forma_de_pago, cuotas=1, descuento=0):
    """F10: cobra una venta que espera en la caja. (ok, texto). Ver «LA CAJA APARTE»."""
    exigir_nivel("empleado", "cobrar una venta")
    if forma_de_pago not in FORMAS_DE_COBRO:
        return False, "Elegí cómo pagó."
    try:
        cuotas = int(cuotas or 1) if forma_de_pago == "Tarjeta de crédito" else 1
    except (TypeError, ValueError):
        return False, "Las cuotas tienen que ser un número."
    if cuotas not in CUOTAS_POSIBLES:
        return False, "Esa cantidad de cuotas no está."
    try:
        descuento = _descuento_valido(descuento, DESCUENTO_MAXIMO_EN_LA_CAJA)
    except ValueError as e:
        return False, str(e)
    with db_lock, transaccion():
        # Se marca cobrada SOLO si seguía esperando: dos cajeros con la misma venta en pantalla
        # no la cobran dos veces.
        c.execute("""UPDATE ventas SET cobrada = 1, forma_de_pago = ?, cuotas = ?, descuento = ?,
                            cobrada_por = ?, cobrada_en = datetime('now', 'localtime')
                     WHERE id = ? AND COALESCE(cobrada, 1) = 0 AND anulada = 0""",
                  (forma_de_pago, cuotas, descuento, obtener_usuario_actual(), venta_id))
        if c.rowcount != 1:
            return False, "Esa venta ya no está esperando en la caja (¿la cobró otro o se anuló?)."
        total = _aplicar_el_descuento(venta_id, descuento)
        c.execute("UPDATE ventas SET total = ? WHERE id = ?", (total, venta_id))
        if descuento:
            anotar_cambio("cobró con descuento", "venta", venta_id,
                          despues={"descuento": descuento, "total": total})
    return True, (f"💵 Venta #{venta_id} cobrada: ${miles(total, 0)} "
                  f"({como_se_pago({'forma_de_pago': forma_de_pago, 'cuotas': cuotas})}"
                  + (f", con {como_porcentaje(descuento)}% de descuento" if descuento else "") + ").")


def poner_a_cuenta(venta_id, mecanico_id=None, descuento=None):
    """F11: pone a cuenta una venta que espera en la caja (la cuenta a la que se vendió, o
    `mecanico_id`). Con el descuento de la cuenta si no se dice otro, el plazo de la cuenta y
    su límite de crédito, como al entregar el depósito. (ok, texto)."""
    exigir_nivel("empleado", "poner una venta a cuenta")
    c.execute("""SELECT mecanico_id FROM ventas
                 WHERE id = ? AND COALESCE(cobrada, 1) = 0 AND anulada = 0""", (venta_id,))
    fila = c.fetchone()
    if not fila:
        return False, "Esa venta ya no está esperando en la caja (¿la cobró otro o se anuló?)."
    mecanico_id = mecanico_id or fila["mecanico_id"]
    if not mecanico_id:
        return False, "Es de Mostrador: elegí a qué cuenta va."
    c.execute("SELECT nombre FROM mecanicos WHERE id = ? AND activo = 1", (mecanico_id,))
    cuenta = c.fetchone()
    if not cuenta:
        return False, "Esa cuenta no existe o está desactivada."
    config = configuracion_de_cuenta(mecanico_id)
    try:
        descuento = _descuento_valido(config["descuento"] if descuento is None else descuento,
                                      max(DESCUENTO_MAXIMO_EN_LA_CAJA, config["descuento"]))
    except ValueError as e:
        return False, str(e)
    usuario = obtener_usuario_actual()
    vence = (date.today() + timedelta(days=config["dias_de_plazo"])).isoformat()
    try:
        with db_lock, transaccion():
            c.execute("""UPDATE ventas SET cobrada = 1, forma_de_pago = ?, mecanico_id = ?,
                                descuento = ?, cobrada_por = ?,
                                cobrada_en = datetime('now', 'localtime')
                         WHERE id = ? AND COALESCE(cobrada, 1) = 0 AND anulada = 0""",
                      (A_CUENTA, mecanico_id, descuento, usuario, venta_id))
            if c.rowcount != 1:
                raise ValueError("Esa venta ya no está esperando en la caja (¿la cobró otro?).")
            total = _aplicar_el_descuento(venta_id, descuento)
            c.execute("UPDATE ventas SET total = ? WHERE id = ?", (total, venta_id))
            # EL LÍMITE, adentro del candado, como pedir_al_deposito(): con lo que ya debe y lo
            # que tiene pedido al depósito sin entregar, más los permisos vigentes.
            if config["limite"]:
                saldo = estado_de_cuenta(mecanico_id)["saldo"]
                pedido = _pendiente_de_la_cuenta(mecanico_id, config["descuento"])
                margen = margen_autorizado(mecanico_id)[0]
                if saldo + pedido + total > config["limite"] + margen + 0.005:
                    raise ValueError(f"{PASA_EL_LIMITE} de {cuenta['nombre']}: debe "
                                     f"{formato_precio(saldo)}, el límite es "
                                     f"{formato_precio(config['limite'])}"
                                     + (f" (más {formato_precio(margen)} de un permiso)"
                                        if margen else "")
                                     + f" y la venta es de {formato_precio(total)}. "
                                       f"{SE_PUEDE_PEDIR_PERMISO}")
            c.execute("""INSERT INTO movimientos_de_cuenta (mecanico_id, concepto, importe, vence,
                                                           usuario)
                         VALUES (?, ?, ?, ?, ?)""",
                      (mecanico_id, f"Venta #{venta_id}", total, vence, usuario))
            c.execute("UPDATE ventas SET movimiento_id = ? WHERE id = ?", (c.lastrowid, venta_id))
    except ValueError as e:
        return False, str(e)
    return True, (f"📒 Venta #{venta_id} a la cuenta de {cuenta['nombre']}: "
                  f"${miles(total, 0)}" + (f" (con {como_porcentaje(descuento)}% de descuento)"
                                           if descuento else "")
                  + f", vence el {vence[8:10]}/{vence[5:7]}.")


# ============================================================================================
# LO QUE LE AVISA LA APP A QUIEN VENDE
# ============================================================================================
# Con la caja aparte y el depósito, lo que arma el vendedor lo termina otro: el cajero cobra la
# venta (o la pone a cuenta) y el depósito entrega lo pedido, o no lo encuentra. El vendedor no
# se enteraba hasta ir a preguntar. Ahora le llega un cartel en la pantalla en la que esté, al
# rato (app.py pregunta cada 20 segundos: ver «LOS AVISOS DE LO QUE TERMINÓ OTRO»).
def novedades_de(usuario, desde):
    """Lo de `usuario` que terminó OTRO desde `desde` («AAAA-MM-DD HH:MM:SS», hora local, la de
    la base): sus ventas cobradas o puestas a cuenta en la caja, y lo que pidió al depósito y
    se entregó o no había. [(clave, momento, texto)], lo más viejo primero. Lo que hizo él
    mismo no se avisa: ya lo sabe."""
    if not usuario:
        return []
    novedades = []
    c.execute("""SELECT v.id, v.total, v.forma_de_pago, v.cuotas, v.cobrada_en,
                        m.nombre AS cuenta
                 FROM ventas v LEFT JOIN mecanicos m ON m.id = v.mecanico_id
                 WHERE v.usuario = ? AND v.cobrada = 1 AND v.anulada = 0 AND v.cobrada_en >= ?
                   AND COALESCE(v.cobrada_por, '') <> v.usuario""", (usuario, desde))
    for v in c.fetchall():
        if v["forma_de_pago"] == A_CUENTA:
            texto = (f"📒 Tu venta #{v['id']} quedó a cuenta de {v['cuenta'] or '¿?'}: "
                     f"${miles(v['total'], 0)}")
        else:
            texto = (f"💵 Se cobró tu venta #{v['id']}: ${miles(v['total'], 0)} "
                     f"({como_se_pago(dict(v))})")
        novedades.append((f"venta {v['id']}", v["cobrada_en"], texto))
    c.execute("""SELECT d.id, d.cantidad, d.estado, d.resuelto_en, d.resuelto_por,
                        p.codigo_raw, m.nombre AS marca
                 FROM pedidos_deposito d JOIN productos p ON p.id = d.producto_id
                 LEFT JOIN marcas m ON m.id = p.marca_id
                 WHERE d.pedido_por = ? AND d.estado IN ('entregado', 'no_hay')
                   AND d.resuelto_en >= ? AND COALESCE(d.resuelto_por, '') <> d.pedido_por""",
              (usuario, desde))
    for d in c.fetchall():
        que = f"{d['cantidad']}× {d['marca'] or ''} {d['codigo_raw']}".replace("  ", " ")
        texto = (f"📦 Ya salió del depósito: {que} (lo dio {d['resuelto_por'] or 'el depósito'})"
                 if d["estado"] == "entregado" else f"❌ El depósito no lo encontró: {que}")
        novedades.append((f"pedido {d['id']}", d["resuelto_en"], texto))
    return sorted(novedades, key=lambda n: n[1])


# ============================================================================================
# LA VENTA Y EL PRESUPUESTO A MEDIO ARMAR, A SALVO DE UNA RECARGA
# ============================================================================================
# La venta que se está armando, y el presupuesto del Buscador, vivían solo en la sesión del
# navegador: recargar la página, que el teléfono cierre la pestaña para hacer lugar o que se
# corte la conexión, y se perdían enteros, con el cliente esperando adelante. Lo propuso una
# revisión con Gemini («persistencia del carrito»). Se guarda lo de cada persona —lo último—,
# solo cuando cambia; al volver a entrar se avisa una vez, y 🧾 Ventas y el 🔍 Buscador ofrecen
# recuperarlo. Solo lo del día: lo de ayer, con los precios de ayer, ya no es un cliente
# esperando. La venta y el presupuesto van en tablas aparte a propósito: recuperar uno no tiene
# que borrar el otro, que todavía no se ofreció.

# Lo que se guarda de cada ítem de la venta: lo que tiene la fila (ver item_de_venta() y
# sumar_a_la_venta()). El veredicto y si se confirmó van también: sin ellos, una pieza que la app
# frena (🔴) se vendería sin preguntar después de recuperarla.
CAMPOS_DEL_ITEM_QUE_SE_GUARDAN = ("producto_id", "codigo", "marca", "descripcion", "precio",
                                  "cantidad", "pedido", "veredicto", "evidencia", "confirmado")
# Y del presupuesto (ver sumar_al_presupuesto()): «se_lleva» es lo destildado, que tiene que
# seguir destildado.
CAMPOS_DEL_PRESUPUESTO_QUE_SE_GUARDAN = ("codigo", "marca", "descripcion", "precio", "cantidad",
                                         "se_lleva")
# Dónde va cada cosa: (tabla, la firma de lo último guardado en la sesión).
_LO_QUE_SE_ARMA = {"venta": ("ventas_a_medio_armar", "_venta_guardada"),
                   "presupuesto": ("presupuestos_a_medio_armar", "_presupuesto_guardado")}


def _guardar_lo_armado(que, items, cliente=""):
    """Guarda `items` si cambiaron desde la última vez, o los borra si quedaron vacíos (se
    terminó o se quitó todo). Una sesión que todavía no armó nada no borra nada: es la que se
    recargó y todavía no recuperó lo anterior."""
    tabla, clave = _LO_QUE_SE_ARMA[que]
    firma = json.dumps([items, cliente], ensure_ascii=False, default=str, sort_keys=True)
    anterior = st.session_state.get(clave)
    if firma == anterior or (anterior is None and not items):
        return
    try:
        with db_lock, transaccion():
            if items:
                c.execute(f"""INSERT OR REPLACE INTO {tabla} (usuario, items, cliente, guardada)
                              VALUES (?, ?, ?, datetime('now', 'localtime'))""",
                          (obtener_usuario_actual(),
                           json.dumps(items, ensure_ascii=False, default=str), cliente))
            else:
                c.execute(f"DELETE FROM {tabla} WHERE usuario = ?", (obtener_usuario_actual(),))
    except sqlite3.Error as _err:
        anotar_error(f"guardar {que} a medio armar", _err)
        return
    st.session_state[clave] = firma


def guardar_lo_que_se_esta_armando():
    """La venta y el presupuesto de la sesión, si cambiaron. Va al final de cada vuelta (ver
    app.py)."""
    if solo_mirar():
        return
    _guardar_lo_armado("venta", [{k: it.get(k) for k in CAMPOS_DEL_ITEM_QUE_SE_GUARDAN}
                                 for it in st.session_state.get("venta_items") or []],
                       str(st.session_state.get("venta_cliente") or ""))
    _guardar_lo_armado("presupuesto",
                       [dict({k: it.get(k) for k in CAMPOS_DEL_PRESUPUESTO_QUE_SE_GUARDAN},
                             producto_id=pid)
                        for pid, it in (st.session_state.get("carrito") or {}).items()])


def _lo_armado(que):
    """Lo que dejó guardado quien está adentro, si es de hoy: {"items", "cliente", "hora",
    "total"}, o None."""
    tabla, _ = _LO_QUE_SE_ARMA[que]
    try:
        c.execute(f"""SELECT items, cliente, substr(guardada, 12, 5) AS hora FROM {tabla}
                      WHERE usuario = ? AND date(guardada) = date('now', 'localtime')""",
                  (obtener_usuario_actual(),))
        fila = c.fetchone()
        items = json.loads(fila["items"]) if fila else []
    except (sqlite3.Error, ValueError) as _err:
        anotar_error(f"{que} a medio armar", _err)
        return None
    if not items:
        return None
    return {"items": items, "cliente": fila["cliente"] or "", "hora": fila["hora"],
            "total": sum(float(x.get("precio") or 0) * int(x.get("cantidad") or 1)
                         for x in items)}


def la_venta_a_medio_armar():
    return _lo_armado("venta")


def el_presupuesto_a_medio_armar():
    return _lo_armado("presupuesto")


def recuperar_la_venta_a_medio_armar():
    """«↩️ Recuperarla»: vuelve a la venta de la sesión con la cantidad, el precio y el cliente
    que tenía, y el stock de ahora. Lo que ya no está en el catálogo queda afuera, y se dice.
    Va como on_click."""
    guardada = la_venta_a_medio_armar()
    if not guardada:
        return
    venta = st.session_state.setdefault("venta_items", [])
    afuera = []
    for it in guardada["items"]:
        if any(x["producto_id"] == it.get("producto_id") for x in venta):
            continue
        nuevo = item_de_venta(it.get("producto_id"), it.get("cantidad") or 1, it.get("pedido"))
        if not nuevo:
            afuera.append(f"{it.get('marca') or ''} {it.get('codigo') or ''}".strip())
            continue
        nuevo.update(precio=float(it.get("precio") or nuevo["precio"]),
                     veredicto=it.get("veredicto"), evidencia=it.get("evidencia"),
                     confirmado=bool(it.get("confirmado")))
        venta.append(nuevo)
        # Los campos de cantidad y precio arrancan de lo recuperado, no de lo que quedó en ellos.
        st.session_state.pop(f"venta_cant_{nuevo['producto_id']}", None)
        st.session_state.pop(f"venta_precio_{nuevo['producto_id']}", None)
    if guardada["cliente"] and not st.session_state.get("venta_cliente"):
        st.session_state["venta_cliente"] = guardada["cliente"]
    if afuera:
        avisar("warning", "Ya no están en el catálogo, quedaron afuera: " + ", ".join(afuera))


def recuperar_el_presupuesto_a_medio_armar():
    """«↩️ Recuperarlo»: vuelve al «🛒 Presupuesto en armado» con la cantidad y el precio que
    tenía (el que se le pasó al cliente) y lo destildado destildado. Lo que ya no está en el
    catálogo queda afuera, y se dice. Va como on_click."""
    guardado = el_presupuesto_a_medio_armar()
    if not guardado:
        return
    carrito = st.session_state.setdefault("carrito", {})
    afuera = []
    for it in guardado["items"]:
        pid = it.get("producto_id")
        if pid in carrito:
            continue
        if not item_de_venta(pid):
            afuera.append(f"{it.get('marca') or ''} {it.get('codigo') or ''}".strip())
            continue
        carrito[pid] = {k: it.get(k) for k in CAMPOS_DEL_PRESUPUESTO_QUE_SE_GUARDAN
                        if k != "se_lleva" or it.get(k) is not None}
        carrito[pid]["cantidad"] = int(it.get("cantidad") or 1)
        st.session_state.pop(f"cant_cart_{pid}", None)
        st.session_state.pop(f"se_lleva_{pid}", None)
    if afuera:
        avisar("warning", "Ya no están en el catálogo, quedaron afuera: " + ", ".join(afuera))


def descartar_la_venta_a_medio_armar():
    """«🗑️ Descartarla». Va como on_click."""
    exigir_nivel("empleado", "descartar una venta a medio armar")
    with db_lock, transaccion():
        c.execute("DELETE FROM ventas_a_medio_armar WHERE usuario = ?", (obtener_usuario_actual(),))


def descartar_el_presupuesto_a_medio_armar():
    """«🗑️ Descartarlo». Va como on_click. El Buscador está abierto sin sesión: el botón no
    se le muestra a quien mira, y esto lo vuelve a mirar (ver «🔒 El invitado mira, no toca»)."""
    exigir_nivel("empleado", "descartar un presupuesto a medio armar")
    with db_lock, transaccion():
        c.execute("DELETE FROM presupuestos_a_medio_armar WHERE usuario = ?",
                  (obtener_usuario_actual(),))

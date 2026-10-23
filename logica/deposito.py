"""El depósito: los pedidos que hace el mostrador, la cola del depósito y lo que queda para
facturar. Y el precio de cada cuenta, con su descuento.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================================================
# EL DEPÓSITO: DEL MOSTRADOR A LA CUENTA
# ============================================================================================
# Cómo se trabaja en el negocio, contado por el dueño: «cuando buscamos un código en el buscador
# tenemos un botón para pedir, les llega a una pantalla a los chicos del depósito, ellos lo
# buscan, lo dan de baja y ahí nos queda en cada cuenta independiente para poder facturarlo».
#
#   1. Mostrador: «📦 Pedir al depósito» en el resultado de la búsqueda, para Mostrador o para
#      la cuenta de un taller o mayorista (pedir_al_deposito()).
#   2. Depósito: «📦 Depósito» muestra lo pendiente ordenado por ubicación, para juntarlo en un
#      recorrido; «✅ Entregado» lo da de baja (entregar_pedido()) y «❌ No hay» lo manda a
#      la lista de reposición.
#   3. Al entregarlo: se descuenta el stock, se anota la venta, y si es para una cuenta se
#      carga en ella con su descuento. Queda en «🧾 Para facturar», por cuenta, hasta que se
#      marca facturado.
#
# EL DESCUENTO NO SE VE. A los talleres y mayoristas se les fía con un descuento sobre la lista,
# y el que viene a pagar no tiene que ver ese precio. Por eso se aplica SOLO al cargar en la
# cuenta: el buscador, la lista de WhatsApp, las cotizaciones y la pantalla del depósito siguen
# con el precio de lista. El importe con descuento aparece en la cuenta corriente (Administrar
# → 💳 Cuentas corrientes) y en «🧾 Para facturar».
ESTADOS_DEL_PEDIDO = {"pendiente": "⏳ pendiente", "entregado": "✅ entregado",
                      "no_hay": "❌ no había", "cancelado": "🚫 cancelado"}
# Lo que se puede pedir de una vez de un mismo código. Un 100 escrito de más vaciaría el stock.
CANTIDAD_MAXIMA_POR_PEDIDO = 50
NOMBRE_DEL_MOSTRADOR = "🧾 Mostrador (contado)"


def precio_de_la_cuenta(precio, descuento):
    """El precio de lista con el descuento de la cuenta, redondeado a centavos."""
    try:
        return round(float(precio or 0) * (1 - float(descuento or 0) / 100), 2)
    except (TypeError, ValueError):
        return 0.0


def cuentas_para_pedir():
    """[(mecanico_id, nombre)] de los talleres y mayoristas activos, por nombre. Para el
    selector «Para:» del pedido; Mostrador va aparte (id None)."""
    c.execute("SELECT id, nombre FROM mecanicos WHERE activo = 1 ORDER BY nombre")
    return [(r["id"], r["nombre"]) for r in c.fetchall()]


def _pendiente_de_la_cuenta(mecanico_id, descuento):
    """Lo que la cuenta ya tiene pedido al depósito y todavía no se entregó, con su descuento.
    Cuenta para el límite: sin esto, diez pedidos seguidos pasaban todos, porque el saldo
    recién sube cuando el depósito los entrega."""
    c.execute("""SELECT COALESCE(SUM(p.precio * d.cantidad), 0) FROM pedidos_deposito d
                 JOIN productos p ON p.id = d.producto_id
                 WHERE d.mecanico_id = ? AND d.estado = 'pendiente'""", (mecanico_id,))
    return precio_de_la_cuenta(c.fetchone()[0], descuento)


def pedir_al_deposito(producto_id, cantidad=1, mecanico_id=None, codigo_de_retiro="",
                      usuario="", nota="", retiro_autorizado=False, tanda=None):
    """El pedido del mostrador. Devuelve (True, aviso) o (False, por qué no).

    Si es para una cuenta que pide código de retiro, el código se pide y se gasta ACÁ, en el
    mostrador, que es donde está el que viene a buscar: el depósito no lo ve. Con
    retiro_autorizado ya se pidió una vez, al elegir la cuenta (ver autorizar_retiro()): así
    no hace falta un código nuevo por cada producto. El límite de crédito también se mira acá,
    contra el precio con descuento y sumando lo que ya está pedido."""
    exigir_nivel("empleado", "pedir algo al depósito")
    try:
        cantidad = int(cantidad)
    except (TypeError, ValueError):
        return False, "La cantidad no es un número."
    if not 1 <= cantidad <= CANTIDAD_MAXIMA_POR_PEDIDO:
        return False, f"La cantidad va de 1 a {CANTIDAD_MAXIMA_POR_PEDIDO}."
    with db_lock, transaccion():
        # EL PRECIO TAMBIÉN, ADENTRO: se leía antes de tomar el candado, y si mientras esperaba
        # el turno otro le cambiaba el precio (una lista nueva), el límite se miraba con el viejo
        # (lo señaló una revisión de código con ChatGPT).
        c.execute("SELECT precio FROM productos WHERE id = ?", (producto_id,))
        prod = c.fetchone()
        if not prod:
            return False, "Ese producto ya no está en el catálogo."
        # EL LÍMITE, ADENTRO DEL CANDADO. Se miraba antes de tomarlo: con $20.000 disponibles,
        # dos vendedores pidiendo $15.000 cada uno al mismo tiempo veían los dos «hay lugar» y
        # entraban los dos (lo señaló una revisión con ChatGPT). Mirado acá, el segundo ya ve el
        # pedido del primero. Ver pruebas_del_deposito.py.
        autorizacion_id = None
        if mecanico_id:
            config = configuracion_de_cuenta(mecanico_id)
            importe = precio_de_la_cuenta(prod["precio"], config["descuento"]) * cantidad
            estado = estado_de_cuenta(mecanico_id)
            pedido = _pendiente_de_la_cuenta(mecanico_id, config["descuento"])
            if config["limite"] and estado["saldo"] + pedido + importe > config["limite"] + 0.005:
                # CON UN PERMISO VIGENTE, el tope sube lo autorizado. Ver pedir_permiso_de_limite().
                margen, autorizacion_id = margen_autorizado(mecanico_id)
                if estado["saldo"] + pedido + importe > config["limite"] + margen + 0.005:
                    return False, (f"{PASA_EL_LIMITE} de la cuenta: debe "
                                   f"{formato_precio(estado['saldo'])}"
                                   + (f", tiene pedido sin entregar {formato_precio(pedido)}"
                                      if pedido else "")
                                   + f" y el límite es {formato_precio(config['limite'])}"
                                   + (f" (más {formato_precio(margen)} de un permiso)"
                                      if margen else "")
                                   + f". {SE_PUEDE_PEDIR_PERMISO}")
        if (mecanico_id and not retiro_autorizado
                and configuracion_de_cuenta(mecanico_id)["pide_codigo"]):
            codigo_id = _codigo_de_retiro_vigente(mecanico_id, codigo_de_retiro)
            if not codigo_id:
                return False, ("El código de retiro no es válido, ya se usó o venció. El taller "
                               "genera uno nuevo en su portal.")
            c.execute("UPDATE codigos_de_retiro SET usado_en = datetime('now', 'localtime') "
                      "WHERE id = ?", (codigo_id,))
        c.execute("""INSERT INTO pedidos_deposito (producto_id, cantidad, mecanico_id, nota,
                                                   pedido_por, tanda, autorizacion_id)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (producto_id, cantidad, mecanico_id or None, (nota or "").strip()[:200],
                   usuario or obtener_usuario_actual(), tanda, autorizacion_id))
    return True, "📦 Pedido al depósito. Lo ven en «📦 Depósito»."


def pedidos_pendientes():
    """Lo que el depósito tiene que buscar, ordenado por ubicación (lo que no tiene ubicación,
    al final) para juntarlo en un solo recorrido. Sin precios: no le hacen falta al depósito,
    y es la pantalla que puede estar a la vista de un cliente."""
    c.execute("""SELECT d.id, d.cantidad, d.nota, d.pedido_por, d.pedido_en, d.mecanico_id,
                        d.tanda, p.id AS producto_id, p.codigo_raw, p.descripcion, p.stock,
                        COALESCE(NULLIF(TRIM(p.ubicacion), ''), '') AS ubicacion,
                        m.nombre AS marca, k.nombre AS cuenta
                 FROM pedidos_deposito d
                 JOIN productos p ON p.id = d.producto_id
                 JOIN marcas m ON m.id = p.marca_id
                 LEFT JOIN mecanicos k ON k.id = d.mecanico_id
                 WHERE d.estado = 'pendiente'
                 ORDER BY ubicacion = '', ubicacion, d.pedido_en""")
    return [dict(r) for r in c.fetchall()]


def pendientes_por_pedido(pendientes=None):
    """Lo pendiente agrupado como se pidió: cada presupuesto mandado entero es un grupo, y cada
    producto pedido suelto es un grupo de uno. Los grupos por orden de llegada (el que pidió
    primero, primero); adentro de cada uno, por ubicación. [{"clave", "pedido_por", "cuenta",
    "pedido_en", "items"}]"""
    grupos = {}
    for p in pendientes if pendientes is not None else pedidos_pendientes():
        clave = p["tanda"] or f"solo-{p['id']}"
        grupo = grupos.setdefault(clave, {"clave": clave, "tanda": p["tanda"],
                                          "pedido_por": p["pedido_por"], "cuenta": p["cuenta"],
                                          "pedido_en": p["pedido_en"], "items": []})
        grupo["items"].append(p)
        grupo["pedido_en"] = min(grupo["pedido_en"] or "", p["pedido_en"] or "")
    return sorted(grupos.values(), key=lambda g: (g["pedido_en"] or "", g["clave"]))


def entregar_la_tanda(tanda, usuario=""):
    """«✅ Entregar todo» de un presupuesto pedido entero. Cada ítem va por entregar_pedido(), con
    su propio todo-o-nada: si uno ya lo había resuelto otro, los demás se entregan igual.
    Devuelve (cuántos se entregaron, cuántos no)."""
    c.execute("SELECT id FROM pedidos_deposito WHERE tanda = ? AND estado = 'pendiente'",
              (tanda,))
    ids = [r["id"] for r in c.fetchall()]
    hechos = sum(1 for i in ids if entregar_pedido(i, usuario)[0])
    return hechos, len(ids) - hechos


def entregar_pedido(pedido_id, usuario=""):
    """«✅ Entregado»: lo da de baja. Todo o nada: el pedido pasa a entregado, el stock baja (si
    el producto lleva stock), la venta queda anotada, y si es para una cuenta se carga en ella
    con su descuento. Devuelve (True, aviso) o (False, por qué no).

    Si dos personas del depósito lo tocan a la vez, el segundo encuentra el pedido ya
    entregado y no hace nada: se cambia de estado SOLO si seguía pendiente."""
    usuario = usuario or obtener_usuario_actual()
    with db_lock, transaccion():
        c.execute("""UPDATE pedidos_deposito SET estado = 'entregado', resuelto_por = ?,
                            resuelto_en = datetime('now', 'localtime')
                     WHERE id = ? AND estado = 'pendiente'""", (usuario, pedido_id))
        if c.rowcount != 1:
            return False, "Ese pedido ya no estaba pendiente (lo resolvió otra persona)."
        c.execute("""SELECT d.cantidad, d.mecanico_id, p.id AS producto_id, p.precio, p.stock,
                            p.codigo_raw, p.descripcion
                     FROM pedidos_deposito d JOIN productos p ON p.id = d.producto_id
                     WHERE d.id = ?""", (pedido_id,))
        f = c.fetchone()
        # EL STOCK NO QUEDA NEGATIVO, y que no alcance no se calla (lo pidió una revisión con
        # ChatGPT: «que SQLite/Python no decida solo»). Si el depósito encontró la pieza, la
        # pieza estaba: el número estaba mal. Se entrega igual, el stock queda en 0, y queda
        # anotado con cuánto faltaba para que alguien lo cuente.
        faltante = 0
        if f["stock"] is not None:
            faltante = max(0, f["cantidad"] - f["stock"])
            c.execute("UPDATE productos SET stock = MAX(0, stock - ?) WHERE id = ?",
                      (f["cantidad"], f["producto_id"]))
            if faltante:
                anotar_cambio("entregó con stock de menos", "producto", f["producto_id"],
                              {"stock": f["stock"]}, {"stock": 0},
                              f"se entregaron {f['cantidad']} y figuraban {f['stock']}: "
                              "conviene contarlo", usuario=usuario)
        # Con el pedido: si vuelve al depósito, lo aprendido se va con él; si se vende en
        # 🧾 Ventas, pasa a ser lo de esa venta. Ver «LO QUE QUEDA AFUERA».
        c.execute("""INSERT INTO ventas_registradas (producto_id, termino_pedido,
                                                     codigo_pedido_clean, usuario, pedido_id)
                     VALUES (?, ?, ?, ?, ?)""",
                  (f["producto_id"], f["codigo_raw"], sanitizar(f["codigo_raw"]), usuario,
                   pedido_id))
        precio_lista = float(f["precio"] or 0)
        descuento, importe, movimiento_id = 0.0, precio_lista * f["cantidad"], None
        if f["mecanico_id"]:
            config = configuracion_de_cuenta(f["mecanico_id"])
            descuento = config["descuento"]
            importe = precio_de_la_cuenta(precio_lista, descuento) * f["cantidad"]
            if importe > 0:
                vence = (date.today() + timedelta(days=config["dias_de_plazo"])).isoformat()
                c.execute("""INSERT INTO movimientos_de_cuenta
                                (mecanico_id, concepto, importe, vence, usuario)
                             VALUES (?, ?, ?, ?, ?)""",
                          (f["mecanico_id"],
                           f"{f['codigo_raw']} x{f['cantidad']} — "
                           f"{(f['descripcion'] or '')[:60]}".strip(" —"),
                           round(importe, 2), vence, usuario))
                movimiento_id = c.lastrowid
        c.execute("""UPDATE pedidos_deposito SET precio_lista = ?, descuento = ?, importe = ?,
                            movimiento_id = ? WHERE id = ?""",
                  (precio_lista, descuento, round(importe, 2), movimiento_id, pedido_id))
    olvidar_la_escala_de_precios()
    # Si con esto se terminó, queda anotado para reponer solo. Ver anotar_lo_que_se_termino().
    anotar_lo_que_se_termino([f["producto_id"]])
    return True, (f"✅ Entregado: {f['codigo_raw']} x{f['cantidad']}"
                  + (" — cargado en la cuenta." if movimiento_id else ".")
                  + (f" ⚠️ El stock decía {f['stock']}: quedó en 0, conviene contarlo."
                     if faltante else ""))


def no_hay_en_el_deposito(pedido_id, usuario=""):
    """«❌ No hay»: el pedido se cierra y el producto pasa a la lista de reposición."""
    with db_lock, transaccion():
        c.execute("""UPDATE pedidos_deposito SET estado = 'no_hay', resuelto_por = ?,
                            resuelto_en = datetime('now', 'localtime')
                     WHERE id = ? AND estado = 'pendiente'""",
                  (usuario or obtener_usuario_actual(), pedido_id))
        if c.rowcount != 1:
            return False, "Ese pedido ya no estaba pendiente."
        c.execute("SELECT producto_id FROM pedidos_deposito WHERE id = ?", (pedido_id,))
        producto_id = c.fetchone()["producto_id"]
    solicitar_reposicion(producto_id)
    return True, "❌ Anotado que no había: quedó en la lista para pedir."


def cancelar_pedido_del_deposito(pedido_id, usuario=""):
    """El mostrador se arrepintió antes de que el depósito lo entregue."""
    with db_lock, transaccion():
        c.execute("""UPDATE pedidos_deposito SET estado = 'cancelado', resuelto_por = ?,
                            resuelto_en = datetime('now', 'localtime')
                     WHERE id = ? AND estado = 'pendiente'""",
                  (usuario or obtener_usuario_actual(), pedido_id))
        return c.rowcount == 1


def para_facturar():
    """{cuenta: [renglones]} de lo entregado y todavía no facturado, cuenta por cuenta (la de
    Mostrador incluida). Cada renglón trae el precio de lista, el descuento y lo cobrado. Sin
    lo que volvió al depósito: lo que volvió entero no figura, y lo que volvió en parte figura
    con lo que queda (ver devolver_lo_escaneado())."""
    c.execute("""SELECT d.id, d.cantidad, d.resuelto_en, d.precio_lista, d.descuento, d.importe,
                        d.mecanico_id, COALESCE(d.devueltos, 0) AS devueltos, p.codigo_raw,
                        p.descripcion, m.nombre AS marca, k.nombre AS cuenta
                 FROM pedidos_deposito d
                 JOIN productos p ON p.id = d.producto_id
                 JOIN marcas m ON m.id = p.marca_id
                 LEFT JOIN mecanicos k ON k.id = d.mecanico_id
                 WHERE d.estado = 'entregado' AND d.facturado_en IS NULL
                   AND d.cantidad > COALESCE(d.devueltos, 0)
                 ORDER BY k.nombre IS NULL, k.nombre, d.resuelto_en""")
    salida = {}
    for r in c.fetchall():
        r = dict(r)
        if r["devueltos"]:
            queda = r["cantidad"] - r["devueltos"]
            r["importe"] = round(float(r["importe"] or 0) * queda / r["cantidad"], 2)
            r["cantidad"] = queda
        salida.setdefault((r["mecanico_id"], r["cuenta"] or NOMBRE_DEL_MOSTRADOR), []).append(r)
    return salida


def marcar_facturado(ids_de_pedidos):
    """Los pedidos entregados de esa lista dejan de figurar en «Para facturar»."""
    ids = [int(i) for i in ids_de_pedidos]
    if not ids:
        return 0
    with db_lock, transaccion():
        total = 0
        for tanda, marcadores in en_tandas(ids):
            c.execute(f"""UPDATE pedidos_deposito SET facturado_en = datetime('now', 'localtime')
                          WHERE id IN ({marcadores}) AND estado = 'entregado'
                            AND facturado_en IS NULL""", tanda)
            total += c.rowcount
    return total


def ultimos_pedidos_del_deposito(limite=30):
    """Los últimos resueltos, para ver qué se entregó y quién (sin precios)."""
    c.execute("""SELECT d.id, d.cantidad, d.estado, d.pedido_por, d.pedido_en, d.resuelto_por,
                        d.resuelto_en, p.codigo_raw, m.nombre AS marca, k.nombre AS cuenta
                 FROM pedidos_deposito d
                 JOIN productos p ON p.id = d.producto_id
                 JOIN marcas m ON m.id = p.marca_id
                 LEFT JOIN mecanicos k ON k.id = d.mecanico_id
                 WHERE d.estado <> 'pendiente'
                 ORDER BY d.resuelto_en DESC LIMIT ?""", (limite,))
    return [dict(r) for r in c.fetchall()]


# ============================================================================================
# LO QUE QUEDA AFUERA: CADA UNO RESPONDE POR LO QUE PIDIÓ
# ============================================================================================
# Lo pidió el dueño: «cuando se pida algo y no se venda, que quede cargado en la cuenta de cada
# persona que lo pidió y lo tenga que devolver con su código». Hasta acá, entregar era vender:
# el stock bajaba y lo entregado para Mostrador se daba por vendido, aunque el cliente se fuera
# sin llevarlo. La pieza quedaba afuera sin que nadie supiera quién la tenía. Y si el vendedor
# la cobraba después en 🧾 Ventas, el stock bajaba otra vez.
#
#   · Lo que el depósito entrega para Mostrador queda A NOMBRE DE QUIEN LO PIDIÓ hasta que se
#     vende en 🧾 Ventas (que usa primero lo que el vendedor ya tiene, sin bajar el stock otra
#     vez: ver cerrar_venta()), se factura («🧾 Para facturar») o vuelve al depósito.
#   · Para que vuelva hacen falta dos cosas: que el depósito ESCANEE EL CÓDIGO DE BARRAS
#     NUESTRO de cada unidad (ver «EL CÓDIGO DE BARRAS NUESTRO»), y la contraseña de quien lo
#     tiene, o la de un administrador, que queda anotado. Así nadie descarga lo que tiene otro, y
#     no vuelve al stock lo que no está en la mano.
#   · LO DE UN TALLER NO VUELVE. Lo pidió el dueño: «el mecánico no puede devolver, se van a
#     aprovechar y van a devolver cosas que nunca trajeron». Lo que se le entrega queda cargado
#     en su cuenta y es suyo; si algo está mal, lo arregla un administrador en la cuenta.
# Desde cuándo lo que sigue afuera se marca en rojo, y se le avisa a quien lo tiene en cualquier
# pantalla (ver app.py).
HORAS_PARA_AVISAR_LO_QUE_QUEDO_AFUERA = 24


def lo_que_tiene(persona=None):
    """Lo entregado para Mostrador que sigue afuera, lo más viejo primero: de todos o de un
    empleado (`persona`, el que lo pidió). [dict] con «queda» (lo que falta vender o devolver),
    «horas» desde que se entregó y «quien»."""
    filtro, args = ("AND d.pedido_por = ?", (persona,)) if persona is not None else ("", ())
    c.execute(f"""SELECT d.id, d.producto_id, d.cantidad, COALESCE(d.vendidos, 0) AS vendidos,
                         COALESCE(d.devueltos, 0) AS devueltos, d.pedido_por, d.resuelto_en,
                         p.codigo_raw, p.descripcion, p.precio, m.nombre AS marca
                  FROM pedidos_deposito d
                  JOIN productos p ON p.id = d.producto_id
                  JOIN marcas m ON m.id = p.marca_id
                  WHERE d.estado = 'entregado' AND d.mecanico_id IS NULL
                    AND d.facturado_en IS NULL
                    AND d.cantidad - COALESCE(d.vendidos, 0) - COALESCE(d.devueltos, 0) > 0
                    {filtro}
                  ORDER BY d.resuelto_en, d.id""", args)
    salida = []
    for r in c.fetchall():
        r = dict(r)
        r["queda"] = r["cantidad"] - r["vendidos"] - r["devueltos"]
        r["horas"] = round((minutos_entre(r["resuelto_en"]) or 0) / 60, 1)
        r["quien"] = r["pedido_por"] or "¿?"
        salida.append(r)
    return salida


def cuanto_hace(horas):
    """«menos de 1 h», «5 h», «3 días»: hace cuánto se entregó lo que sigue afuera."""
    horas = float(horas or 0)
    if horas < 1:
        return "menos de 1 h"
    return f"{int(horas)} h" if horas < 48 else f"{int(horas // 24)} días"


def quien_tiene_que_devolver():
    """Lo que está afuera, por persona: [dict] con cuántas cosas, cuántas unidades, lo que valen
    a precio de lista y cuántas horas tiene la más vieja. Lo que tiene más horas, primero."""
    grupos = {}
    for r in lo_que_tiene():
        g = grupos.setdefault(r["quien"], {"quien": r["quien"], "cosas": 0, "unidades": 0,
                                           "valor": 0.0, "horas": 0.0})
        g["cosas"] += 1
        g["unidades"] += r["queda"]
        g["valor"] += float(r["precio"] or 0) * r["queda"]
        g["horas"] = max(g["horas"], r["horas"])
    return sorted(grupos.values(), key=lambda g: -g["horas"])


def lo_que_tiene_para_vender(persona, producto_id):
    """[(pedido_id, cuántos)] de ese producto que `persona` tiene del depósito para Mostrador,
    lo más viejo primero: lo que 🧾 Ventas usa antes de bajar el stock (ver cerrar_venta())."""
    return [(r["id"], r["queda"]) for r in lo_que_tiene(persona=persona)
            if r["producto_id"] == producto_id]


# ============================================================================================
# EL CÓDIGO DE BARRAS NUESTRO
# ============================================================================================
# Lo pidió el dueño: que para que algo vuelva al stock, los del depósito «tengan que hacer un
# control escaneando el código de barras nuestro, no el original». El original de la caja no
# sirve de control: el mismo número está en cualquier caja igual, comprada en cualquier lado.
# El nuestro sale del número del producto en la app: «CH» + el número + un dígito verificador
# («CH1400-5»), en Code 39, que lee cualquier lector sin configurar nada. Existe solo para cada
# producto —no hay que cargar nada— y se imprime en etiquetas (ver pdf_de_etiquetas()): en el
# depósito, al entregar, y en «↩️ Devoluciones» para lo que ya está en el estante. El dígito
# verificador frena un número mal leído o mal tipeado: «CH1400-4» no es nada.
PREFIJO_DEL_CODIGO_NUESTRO = "CH"


def codigo_nuestro(producto_id):
    """El código de barras nuestro de un producto: «CH1400-5». Ver «EL CÓDIGO DE BARRAS
    NUESTRO»."""
    return f"{PREFIJO_DEL_CODIGO_NUESTRO}{int(producto_id)}-{digito_verificador_gtin(str(int(producto_id)))}"


def producto_por_codigo_nuestro(texto):
    """El id del producto si `texto` es un código nuestro bien leído —el lector puede mandar
    los asteriscos del Code 39, minúsculas o espacios—, y el producto existe. Si no, None."""
    m = re.fullmatch(rf"\*?\s*{PREFIJO_DEL_CODIGO_NUESTRO}\s*0*(\d{{1,9}})\s*-\s*(\d)\s*\*?",
                     str(texto or "").strip(), re.IGNORECASE)
    if not m or digito_verificador_gtin(m.group(1)) != m.group(2):
        return None
    c.execute("SELECT id FROM productos WHERE id = ?", (int(m.group(1)),))
    fila = c.fetchone()
    return fila["id"] if fila else None


def que_es_lo_escaneado(texto, ya_escaneados=()):
    """Lo que el depósito escaneó para devolver: (producto_id, "") si es un código nuestro de
    algo que alguien tiene afuera, y no se escanearon ya todas las que hay afuera
    (`ya_escaneados`, lo de antes en la misma tanda); si no, (None, por qué no)."""
    texto = str(texto or "").strip()
    if not texto:
        return None, ""
    producto_id = producto_por_codigo_nuestro(texto)
    if not producto_id:
        if producto_por_codigo_de_barras(texto) or re.fullmatch(r"\d{8,14}", texto):
            return None, ("Ese es el código ORIGINAL de la caja: para que vuelva al stock hay "
                          "que escanear la etiqueta nuestra (la que empieza con "
                          f"{PREFIJO_DEL_CODIGO_NUESTRO}).")
        return None, f"«{texto}» no es un código nuestro: revisá la etiqueta."
    afuera = sum(r["queda"] for r in lo_que_tiene() if r["producto_id"] == producto_id)
    ya = sum(1 for t in ya_escaneados or () if producto_por_codigo_nuestro(t) == producto_id)
    if ya < afuera:
        return producto_id, ""
    c.execute("""SELECT m.nombre AS marca, p.codigo_raw FROM productos p
                 JOIN marcas m ON m.id = p.marca_id WHERE p.id = ?""", (producto_id,))
    f = c.fetchone()
    if not afuera:
        return None, (f"Nadie tiene {f['marca']} {f['codigo_raw']} del depósito: no hay nada "
                      "que vuelva al stock.")
    # Una unidad de más es justo lo que no tiene que pasar: algo que no salió del depósito a
    # nombre de nadie volviendo al stock.
    return None, (f"Ya se escanearon las {afuera} de {f['marca']} {f['codigo_raw']} que hay "
                  "afuera: esta unidad no salió del depósito a nombre de nadie.")


def quienes_tienen_lo_escaneado(escaneos):
    """Quiénes tienen afuera TODO lo escaneado, con las cantidades: [persona]. De ahí sale de
    quién es lo que vuelve, sin elegirlo a mano cuando es uno solo."""
    por_producto = {}
    for texto in escaneos or []:
        producto_id = producto_por_codigo_nuestro(texto)
        if producto_id:
            por_producto[producto_id] = por_producto.get(producto_id, 0) + 1
    if not por_producto:
        return []
    tiene = {}
    for r in lo_que_tiene():
        tiene[(r["quien"], r["producto_id"])] = tiene.get((r["quien"], r["producto_id"]), 0) + r["queda"]
    return [persona for persona in sorted({q for q, _ in tiene}, key=str.lower)
            if all(tiene.get((persona, p), 0) >= n for p, n in por_producto.items())]


def _quien_devuelve(persona, codigo):
    """(cómo se identificó, quién) si `codigo` es la contraseña de `persona` o la de un
    administrador; (None, por qué no) si no. Ver «LO QUE QUEDA AFUERA»."""
    codigo = str(codigo or "").strip()
    if not hay_claves_configuradas():
        return "sin claves configuradas", obtener_usuario_actual()
    if not codigo:
        return None, f"Falta la contraseña de {persona}."
    nombre, nivel, error = validar_password(codigo)
    if error:
        return None, error
    if nivel == "admin":
        return "clave de administrador", nombre
    if nivel and nombre == persona:
        return "su clave", nombre
    return None, f"Esa contraseña no es de {persona}, que es quien lo tiene (ni de un administrador)."


def _devolver_lo_planeado(plan, persona, como, recibio):
    """La parte de devolver_lo_escaneado() que toca la base, todo o nada: ValueError si
    mientras tanto otro vendió o devolvió algo de eso."""
    with db_lock, transaccion():
        for r, n in plan:
            c.execute("""UPDATE pedidos_deposito SET devueltos = COALESCE(devueltos, 0) + ?
                         WHERE id = ? AND estado = 'entregado'
                           AND cantidad - COALESCE(vendidos, 0) - COALESCE(devueltos, 0) >= ?""",
                      (n, r["id"], n))
            if c.rowcount != 1:
                raise ValueError("Mientras tanto otra persona vendió o devolvió algo de eso: "
                                 "no volvió nada, probá de nuevo.")
            c.execute("UPDATE productos SET stock = stock + ? WHERE id = ? AND stock IS NOT NULL",
                      (n, r["producto_id"]))
            c.execute("""INSERT INTO devoluciones_al_deposito (pedido_id, cantidad, devolvio,
                                                               como, recibio)
                         VALUES (?, ?, ?, ?, ?)""", (r["id"], n, persona, como, recibio))
            # Lo aprendido al entregarlo se va con lo que vuelve entero sin haberse vendido.
            if n == r["cantidad"] - r["devueltos"] and not r["vendidos"]:
                c.execute("DELETE FROM ventas_registradas WHERE pedido_id = ? AND venta_id IS NULL",
                          (r["id"],))


def devolver_lo_escaneado(escaneos, persona, codigo):
    """Vuelve al stock lo que el depósito escaneó (una unidad por escaneo, con el código de
    barras nuestro) de lo que `persona` tiene afuera, con su contraseña o la de un
    administrador. Todo o nada: si una unidad no es de lo que tiene, no vuelve ninguna.
    (ok, texto). Ver «LO QUE QUEDA AFUERA»."""
    exigir_nivel("empleado", "recibir algo que vuelve al depósito")
    por_producto = {}
    for texto in escaneos or []:
        producto_id = producto_por_codigo_nuestro(texto)
        if not producto_id:
            return False, f"«{texto}» no es un código de barras nuestro: no vuelve nada."
        por_producto[producto_id] = por_producto.get(producto_id, 0) + 1
    if not por_producto:
        return False, "No se escaneó nada: escaneá la etiqueta nuestra de cada unidad."
    suyo = lo_que_tiene(persona=persona)
    plan = []
    for producto_id, n in por_producto.items():
        pedidos = [r for r in suyo if r["producto_id"] == producto_id]
        tiene = sum(r["queda"] for r in pedidos)
        if n > tiene:
            nombre = (f"{pedidos[0]['marca']} {pedidos[0]['codigo_raw']}" if pedidos
                      else codigo_nuestro(producto_id))
            return False, (f"{persona} tiene {tiene} de {nombre} y se escanearon {n}: no "
                           "vuelve nada. Revisá lo escaneado.")
        for r in pedidos:
            if n <= 0:
                break
            plan.append((r, min(r["queda"], n)))
            n -= min(r["queda"], n)
    como, quien = _quien_devuelve(persona, codigo)
    if not como:
        return False, quien
    recibio = obtener_usuario_actual()
    # Lo recibe OTRA persona: el que lo tiene no se lo devuelve a sí mismo desde su pantalla,
    # que es justo el control que no tiene que faltar. Un administrador sí puede.
    if como == "su clave" and recibio == persona:
        return False, (f"Lo tiene que recibir el depósito, no {persona}: que lo escanee alguien "
                       "del depósito con su usuario (o que ponga la contraseña un "
                       "administrador).")
    try:
        _devolver_lo_planeado(plan, persona, como, recibio)
    except ValueError as e:
        return False, str(e)
    unidades = sum(n for _, n in plan)
    return True, (f"↩️ Volvieron al stock {unidades} unidad(es) de {persona}: "
                  + ", ".join(f"{n}× {r['marca']} {r['codigo_raw']}" for r, n in plan)
                  + (f" ({como})." if como != "su clave" else "."))


def pdf_de_etiquetas(items):
    """Las etiquetas con el código de barras nuestro, para pegar en cada unidad: `items` es
    [(producto_id, cuántas)]. A4, tres columnas por ocho filas. b"" si no hay nada."""
    from fpdf import FPDF
    etiquetas = []
    for producto_id, cuantas in items:
        c.execute("""SELECT p.id, p.codigo_raw, p.descripcion, m.nombre AS marca
                     FROM productos p JOIN marcas m ON m.id = p.marca_id WHERE p.id = ?""",
                  (producto_id,))
        f = c.fetchone()
        if f:
            etiquetas += [dict(f)] * max(0, min(int(cuantas), CANTIDAD_MAXIMA_POR_PEDIDO * 4))
    if not etiquetas:
        return b""

    def limpiar(texto):
        return str(texto).encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(False)
    ancho, alto, columnas, filas = 66, 35, 3, 8
    for n, e in enumerate(etiquetas):
        if n % (columnas * filas) == 0:
            pdf.add_page()
        x = 6 + (n % columnas) * (ancho + 2)
        y = 8 + ((n // columnas) % filas) * (alto + 1)
        pdf.set_xy(x, y)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(ancho, 4, limpiar(f"{e['marca']} {e['codigo_raw']}")[:34])
        pdf.set_xy(x, y + 4)
        pdf.set_font("Helvetica", "", 7)
        pdf.cell(ancho, 4, limpiar((e["descripcion"] or "")[:44]))
        # LO QUE LEE UN LECTOR: fpdf toma `w` como la barra GRUESA (la fina es un tercio). Con
        # w=0.3 la fina quedaba en 0,1 mm y ningún lector la levantaba (probado decodificando el
        # PDF). Cada carácter de Code 39 ocupa 16 barras finas, más 10 de margen blanco a cada
        # lado: la fina, lo más cerca de 0,33 mm que entre en la etiqueta, y centrado.
        texto = f"*{codigo_nuestro(e['id'])}*"
        fina = min(0.33, (ancho - 2) / (16 * len(texto) + 20))
        largo = 16 * len(texto) * fina - fina
        pdf.code39(texto, x=x + (ancho - largo) / 2, y=y + 9, w=3 * fina, h=16)
        pdf.set_xy(x, y + 27)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(ancho, 4, codigo_nuestro(e["id"]))
    return bytes(pdf.output())


def productos_para_etiquetar(texto, tope=20):
    """Los productos para imprimirles la etiqueta nuestra: por su código (o el principio), por
    el código de barras ORIGINAL de la caja —se escanea la caja y sale la etiqueta— o por el
    nuestro. [dict] con id, marca, codigo_raw, descripcion y stock."""
    texto = str(texto or "").strip()
    if not texto:
        return []
    ids = [producto_por_codigo_nuestro(texto) or producto_por_codigo_de_barras(texto)]
    if not ids[0]:
        limpio = sanitizar(texto)
        if not limpio:
            return []
        # Por rango y no con LIKE: así usa el índice del código (LIKE no distingue mayúsculas
        # y no lo puede usar).
        c.execute("""SELECT id FROM productos WHERE codigo_clean >= ? AND codigo_clean < ?
                     ORDER BY codigo_clean = ? DESC, codigo_clean LIMIT ?""",
                  (limpio, limpio + "\uffff", limpio, int(tope)))
        ids = [r["id"] for r in c.fetchall()]
    salida = []
    for producto_id in ids:
        c.execute("""SELECT p.id, p.codigo_raw, p.descripcion, p.stock, m.nombre AS marca
                     FROM productos p JOIN marcas m ON m.id = p.marca_id WHERE p.id = ?""",
                  (producto_id,))
        f = c.fetchone()
        if f:
            salida.append(dict(f))
    return salida


def etiquetas_para_descargar(items):
    """Para el botón de descarga: el PDF se arma al tocarlo (ver comprobante_para_descargar())."""
    datos = [(int(p), int(n)) for p, n in items]
    return lambda: pdf_de_etiquetas(datos)


def resumen_de_la_cuenta(persona=None, mecanico_id=None, dias=30):
    """Lo de una cuenta en los últimos `dias` días: de un empleado, lo que vendió en 🧾 Ventas
    y lo que tiene del depósito; de un taller, lo que se llevó del depósito y lo que debe.
    dict."""
    desde = (datetime.now() - timedelta(days=int(dias))).strftime("%Y-%m-%d %H:%M:%S")
    if mecanico_id is not None:
        c.execute("""SELECT d.id, d.resuelto_en, d.cantidad, d.importe, p.codigo_raw,
                            p.descripcion, m.nombre AS marca
                     FROM pedidos_deposito d JOIN productos p ON p.id = d.producto_id
                     JOIN marcas m ON m.id = p.marca_id
                     WHERE d.mecanico_id = ? AND d.estado = 'entregado' AND d.resuelto_en >= ?
                     ORDER BY d.resuelto_en DESC""", (mecanico_id, desde))
        entregas = [dict(r) for r in c.fetchall()]
        return {"afuera": [], "entregas": entregas,
                "total": round(sum(float(e["importe"] or 0) for e in entregas), 2),
                "saldo": estado_de_cuenta(mecanico_id)["saldo"]}
    c.execute("""SELECT id, fecha, cliente, forma_de_pago, total FROM ventas
                 WHERE usuario = ? AND anulada = 0 AND fecha >= ? ORDER BY id DESC""",
              (persona, desde))
    ventas = [dict(r) for r in c.fetchall()]
    c.execute("""SELECT COALESCE(SUM(d.importe), 0) FROM ventas_devoluciones d
                 JOIN ventas v ON v.id = d.venta_id
                 WHERE v.usuario = ? AND v.anulada = 0 AND d.fecha >= ?""", (persona, desde))
    devuelto = round(float(c.fetchone()[0]), 2)
    return {"afuera": lo_que_tiene(persona=persona), "ventas": ventas,
            "total": round(sum(float(v["total"] or 0) for v in ventas), 2),
            "devuelto": devuelto}


def cuentas_para_mirar():
    """Las cuentas que se pueden mirar en «👥 Cada cuenta»: [(etiqueta, persona, mecanico_id)].
    El administrador ve a todos los empleados y talleres; un empleado, solo lo suyo."""
    yo = obtener_usuario_actual()
    if not es_admin():
        return [(f"👤 {yo} (vos)", yo, None)]
    c.execute("""SELECT nombre FROM usuarios WHERE activo = 1
                 UNION SELECT DISTINCT usuario FROM ventas WHERE usuario IS NOT NULL
                 UNION SELECT DISTINCT pedido_por FROM pedidos_deposito
                       WHERE mecanico_id IS NULL AND pedido_por IS NOT NULL""")
    personas = sorted({r[0] for r in c.fetchall() if r[0] and r[0] != "Invitado"} | {yo},
                      key=str.lower)
    return ([(f"👤 {p}" + (" (vos)" if p == yo else ""), p, None) for p in personas]
            + [(f"🔧 {nombre}", None, mid) for mid, nombre in cuentas_para_pedir()])


# ============================================================================================
# CUÁNTO TARDA EL DEPÓSITO
# ============================================================================================
# Desde que el mostrador lo pide hasta que el depósito lo da de baja (entregado o «no hay»).
# Las dos horas las pone la base (datetime('now', 'localtime')), así que no depende del reloj
# de cada computadora. Lo cancelado no cuenta: no lo fueron a buscar.
# En la cola, el que espera más que esto se marca: 🟡 desde el primero, 🔴 desde el segundo.
MINUTOS_PARA_AVISAR = (10, 20)


def minutos_entre(desde, hasta=None):
    """Minutos enteros entre dos «AAAA-MM-DD HH:MM:SS» (hasta=None: ahora). None si no se leen."""
    try:
        inicio = datetime.strptime(str(desde)[:19], "%Y-%m-%d %H:%M:%S")
        fin = (datetime.strptime(str(hasta)[:19], "%Y-%m-%d %H:%M:%S") if hasta
               else datetime.now())
    except (TypeError, ValueError):
        return None
    return max(0, int((fin - inicio).total_seconds() // 60))


def como_se_lee_la_espera(minutos):
    """«⏱️ <1 min», «⏱️ 7 min», «🟡 12 min», «🔴 1 h 05»."""
    if minutos is None:
        return ""
    marca = ("🔴" if minutos >= MINUTOS_PARA_AVISAR[1] else
             "🟡" if minutos >= MINUTOS_PARA_AVISAR[0] else "⏱️")
    texto = ("<1 min" if minutos < 1 else f"{minutos} min" if minutos < 60
             else f"{minutos // 60} h {minutos % 60:02d}")
    return f"{marca} {texto}"


def _resumen_de_tiempos(minutos):
    if not minutos:
        return {"cuantos": 0, "promedio": None, "mediana": None, "maximo": None, "a_tiempo": None}
    orden = sorted(minutos)
    medio = len(orden) // 2
    mediana = orden[medio] if len(orden) % 2 else (orden[medio - 1] + orden[medio]) / 2
    return {"cuantos": len(orden), "promedio": round(sum(orden) / len(orden), 1),
            "mediana": round(mediana, 1), "maximo": round(orden[-1], 1),
            "a_tiempo": round(100 * sum(1 for m in orden if m < MINUTOS_PARA_AVISAR[0])
                              / len(orden))}


def tiempos_del_deposito(dias=7):
    """{"hoy": resumen, "periodo": resumen, "por_persona": {quién: resumen}, "dias": dias}.
    Cada resumen: cuántos, promedio, mediana y máximo en minutos, y el % que tardó menos de
    MINUTOS_PARA_AVISAR[0]."""
    c.execute("""SELECT d.resuelto_por,
                        (julianday(d.resuelto_en) - julianday(d.pedido_en)) * 1440 AS minutos,
                        date(d.resuelto_en) = date('now', 'localtime') AS es_de_hoy
                 FROM pedidos_deposito d
                 WHERE d.estado IN ('entregado', 'no_hay') AND d.resuelto_en IS NOT NULL
                   AND d.resuelto_en >= datetime('now', 'localtime', ?)""",
              (f"-{int(dias)} days",))
    filas = [(r["resuelto_por"] or "¿?", max(0.0, float(r["minutos"] or 0)), r["es_de_hoy"])
             for r in c.fetchall()]
    personas = {}
    for quien, minutos, _hoy in filas:
        personas.setdefault(quien, []).append(minutos)
    return {"hoy": _resumen_de_tiempos([m for _q, m, hoy in filas if hoy]),
            "periodo": _resumen_de_tiempos([m for _q, m, _h in filas]),
            "por_persona": {q: _resumen_de_tiempos(ms) for q, ms in sorted(personas.items())},
            "dias": int(dias)}


# ============================================================================================
# A QUIÉN SE ESTÁ ATENDIENDO
# ============================================================================================
# La cuenta se elige UNA vez, antes de empezar a pedir o a armar el presupuesto, y queda para
# todo lo que sigue: cada «📦 Pedir» va a esa cuenta. Antes había que elegirla en cada producto,
# y si pedía código de retiro, un código nuevo por producto (el código es de un solo uso).
# Ahora el código se pide y se gasta al elegir la cuenta. Queda elegida hasta «Volver a
# Mostrador», hasta salir, o HORAS_DE_LA_CUENTA_ELEGIDA después: una computadora del mostrador
# que quedó con una cuenta abierta no puede seguir cargándole cosas toda la tarde.
HORAS_DE_LA_CUENTA_ELEGIDA = 3


def autorizar_retiro(mecanico_id, codigo):
    """Al elegir la cuenta: si pide código de retiro, lo valida y lo gasta. (True, "") o
    (False, por qué no)."""
    exigir_nivel("empleado", "autorizar un retiro a cuenta")
    if not configuracion_de_cuenta(mecanico_id)["pide_codigo"]:
        return True, ""
    with db_lock, transaccion():
        codigo_id = _codigo_de_retiro_vigente(mecanico_id, codigo)
        if not codigo_id:
            return False, ("El código de retiro no es válido, ya se usó o venció. El taller "
                           "genera uno nuevo en su portal.")
        c.execute("UPDATE codigos_de_retiro SET usado_en = datetime('now', 'localtime') "
                  "WHERE id = ?", (codigo_id,))
    return True, ""


def cuenta_elegida():
    """{"id", "nombre", "desde"} de la cuenta que se está atendiendo, o None (Mostrador)."""
    elegida = st.session_state.get("cuenta_elegida")
    if not elegida:
        return None
    if time.time() - elegida.get("desde", 0) > HORAS_DE_LA_CUENTA_ELEGIDA * 3600:
        st.session_state.pop("cuenta_elegida", None)
        return None
    return elegida


def nombre_de_la_cuenta_elegida():
    elegida = cuenta_elegida()
    return elegida["nombre"] if elegida else NOMBRE_DEL_MOSTRADOR


def _dejar_la_cuenta():
    st.session_state.pop("cuenta_elegida", None)


def mostrar_cuenta_elegida(clave):
    """«🧾 Atendiendo a: …», arriba del buscador y de la lista de WhatsApp. Un toque abre el
    recuadro para elegir la cuenta (y poner el código de retiro, si lo pide) o volver a
    Mostrador. Sin precios ni saldos: el cliente puede estar mirando."""
    elegida = cuenta_elegida()
    # Con clave: sin ella, Streamlit lo arma de nuevo al elegir la cuenta y se cerraba antes
    # de poder tocar «Atender a esta cuenta» (medido en el navegador).
    with st.popover(f"🧾 Atendiendo a: {nombre_de_la_cuenta_elegida().replace('🧾 ', '')}",
                    type="primary" if elegida else "secondary", key=f"cuenta_pop_{clave}"):
        nombres = dict(cuentas_para_pedir())
        if not nombres:
            st.caption(f"Todavía no hay cuentas: se crean en {miga_hasta('Usuarios')}, en "
                       "«Mecánicos externos».")
            return
        st.caption("Elegila antes de pedir o de armar el presupuesto: todo lo que pidas al "
                   "depósito va a esa cuenta, sin elegirla de nuevo en cada producto.")
        nueva = st.selectbox("Cuenta:", list(nombres), format_func=nombres.get, index=None,
                             placeholder="El taller o mayorista", key=f"cuenta_sel_{clave}")
        codigo = ""
        if nueva and configuracion_de_cuenta(nueva)["pide_codigo"]:
            codigo = st.text_input("Código de retiro", max_chars=6, key=f"cuenta_cod_{clave}",
                                   placeholder="6 números, del portal del taller",
                                   help="Se pide una sola vez, acá. Sirve para todo lo que se "
                                        "pida mientras esté elegida la cuenta.")
        if st.button("✅ Atender a esta cuenta", type="primary", disabled=not nueva,
                     key=f"cuenta_ok_{clave}", width="stretch"):
            ok, aviso = autorizar_retiro(nueva, codigo)
            if ok:
                st.session_state["cuenta_elegida"] = {"id": nueva, "nombre": nombres[nueva],
                                                      "desde": time.time()}
                st.session_state.pop(f"cuenta_cod_{clave}", None)
                st.rerun()
            st.error(aviso)
        if elegida:
            st.button(f"↩️ Volver a {NOMBRE_DEL_MOSTRADOR}", key=f"cuenta_fin_{clave}",
                      on_click=_dejar_la_cuenta, width="stretch")


def importe_para_la_cuenta(mecanico_id, items):
    """Lo que suman [(producto_id, cantidad)] para esa cuenta, con su descuento."""
    descuento = configuracion_de_cuenta(mecanico_id)["descuento"]
    total = 0.0
    for producto_id, cantidad in items:
        c.execute("SELECT precio FROM productos WHERE id = ?", (producto_id,))
        fila = c.fetchone()
        total += precio_de_la_cuenta((fila["precio"] if fila else 0) or 0, descuento) * cantidad
    return round(total, 2)


def _recordar_si_fue_por_el_limite(clave, items, pedidos, fallas):
    """Si algo no entró por el límite de crédito, se recuerda qué, para ofrecer pedir permiso
    (ver mostrar_permiso_si_hace_falta()); si entró todo, se olvida."""
    elegida = cuenta_elegida()
    faltan = [(pid, cant) for pid, cant in items if pid not in pedidos]
    if elegida and faltan and any(es_por_el_limite(f) for f in fallas):
        st.session_state[f"_limite_{clave}"] = {"mecanico_id": elegida["id"], "items": faltan}
    else:
        st.session_state.pop(f"_limite_{clave}", None)


def mostrar_permiso_si_hace_falta(clave):
    """El recuadro del permiso (ver mostrar_permiso_de_limite()), si lo último que se pidió con
    esta `clave` no entró por el límite y se sigue atendiendo a la misma cuenta."""
    bloqueo = st.session_state.get(f"_limite_{clave}")
    elegida = cuenta_elegida()
    if not bloqueo or not elegida or elegida["id"] != bloqueo["mecanico_id"]:
        return
    mid = bloqueo["mecanico_id"]
    mostrar_permiso_de_limite(mid, cuanto_pasa_del_limite(
        mid, importe_para_la_cuenta(mid, bloqueo["items"])), clave)


def pedir_lo_elegido_al_deposito(items, usuario="", nota="", clave=None):
    """[(producto_id, cantidad)] → pide cada uno para la cuenta elegida (o Mostrador).
    Devuelve (los que se pidieron, [por qué no, de los otros]). Con `clave`, si algo no entró
    por el límite, queda para ofrecer pedir permiso (ver mostrar_permiso_si_hace_falta())."""
    elegida = cuenta_elegida()
    pedidos, fallas = [], []
    # Varios juntos son una tanda: el depósito los ve como un solo pedido (ver
    # pendientes_por_pedido()). Uno solo no lleva tanda: es un pedido suelto.
    tanda = uuid.uuid4().hex[:12] if len(items) > 1 else None
    for producto_id, cantidad in items:
        ok, aviso = pedir_al_deposito(producto_id, cantidad, elegida["id"] if elegida else None,
                                      usuario=usuario, nota=nota, retiro_autorizado=True,
                                      tanda=tanda)
        (pedidos.append(producto_id) if ok else fallas.append(aviso))
    if clave:
        _recordar_si_fue_por_el_limite(clave, items, pedidos, fallas)
    return pedidos, fallas


def _hora_corta(fecha_y_hora):
    """«2026-10-06 14:32:10» → «14:32» si es de hoy, «06/10 14:32» si no."""
    texto = str(fecha_y_hora or "")
    if len(texto) < 16:
        return texto
    if texto[:10] == date.today().isoformat():
        return texto[11:16]
    return f"{texto[8:10]}/{texto[5:7]} {texto[11:16]}"


def mostrar_pedir_al_deposito(resultados, clave):
    """El botón «📦 Pedir al depósito» abajo del resultado de una búsqueda. Abre un recuadro chico:
    cuál (si hay varios), cuántos y una nota. Va a la cuenta que se está atendiendo («🧾
    Atendiendo a», arriba de todo): no se elige en cada producto. También suma al presupuesto.

    No muestra ningún precio: lo puede estar mirando el cliente del otro lado del mostrador, y
    el de la cuenta lleva el descuento (ver «EL DESCUENTO NO SE VE»)."""
    if not resultados or modo_solo_lectura():
        return
    with st.popover("📦 Pedir al depósito / 🛒 presupuesto", width="stretch",
                    key=f"dep_pop_{clave}"):
        rotulos = {f["ID"]: f"{f['Marca']} - {f['Codigo']}" for f in resultados}
        if len(rotulos) == 1:
            producto_id = next(iter(rotulos))
            st.caption(rotulos[producto_id])
        else:
            producto_id = st.selectbox("¿Cuál?", list(rotulos), format_func=rotulos.get,
                                       key=f"dep_cual_{clave}")
        cantidad = st.number_input("Cantidad", min_value=1, max_value=CANTIDAD_MAXIMA_POR_PEDIDO,
                                   value=1, step=1, key=f"dep_cant_{clave}")
        st.markdown(f"Para: **{texto_para_html(nombre_de_la_cuenta_elegida())}**")
        st.caption("Se cambia arriba, en «🧾 Atendiendo a».")
        nota = st.text_input("Nota para el depósito (opcional)", max_chars=200,
                             key=f"dep_nota_{clave}", placeholder="Ej.: lo espera en el mostrador")
        b_pedir, b_sumar = st.columns(2)
        if b_pedir.button("📦 Pedir", type="primary", key=f"dep_pedir_{clave}", width="stretch"):
            pedidos, fallas = pedir_lo_elegido_al_deposito([(producto_id, cantidad)], nota=nota,
                                                           clave=f"dep_{clave}")
            if pedidos:
                st.success("📦 Pedido al depósito. Lo ven en «📦 Depósito».")
            for falla in fallas:
                st.error(falla)
        # SI NO ENTRÓ POR EL LÍMITE: pedir permiso. Ver mostrar_permiso_de_limite().
        mostrar_permiso_si_hace_falta(f"dep_{clave}")
        # Como callback: el presupuesto se dibuja arriba de todo, antes que este botón, y sumado
        # recién al volver del botón no aparecía hasta el toque siguiente.
        b_sumar.button("🛒 Al presupuesto", key=f"dep_sumar_{clave}", width="stretch",
                       on_click=_sumar_desde_el_recuadro,
                       args=(next(f for f in resultados if f["ID"] == producto_id), cantidad,
                             clave))
        if st.session_state.pop(f"_sumado_{clave}", None):
            st.success("🛒 Sumado al presupuesto (arriba de todo, en «Presupuesto en armado»).")
        st.caption("No hace falta tocar «🛒 Se llevó»: la venta se anota sola cuando el depósito "
                   "lo entrega.")


def _sumar_desde_el_recuadro(fila, cantidad, clave):
    sumar_al_presupuesto(fila, cantidad)
    st.session_state[f"_sumado_{clave}"] = True


def pedir_uno_del_presupuesto(producto_id):
    """«📦» al lado de un ítem del presupuesto: pide solo ese, y sale del presupuesto. Para no
    mandarle al depósito diez productos de golpe cuando el cliente todavía está decidiendo."""
    item = st.session_state.get("carrito", {}).get(producto_id)
    if not item:
        return
    pedidos, fallas = pedir_lo_elegido_al_deposito([(producto_id, item["cantidad"])],
                                                   clave="presupuesto")
    if pedidos:
        st.session_state["carrito"].pop(producto_id, None)
        st.session_state.pop(f"cant_cart_{producto_id}", None)
        avisar("success", f"📦 {item['marca']} {item['codigo']} x{item['cantidad']} pedido al "
                          f"depósito, para {nombre_de_la_cuenta_elegida()}.")
    for falla in fallas:
        avisar("warning", falla)


def sumar_al_presupuesto(fila, cantidad=1):
    """Suma un resultado al «🛒 Presupuesto en armado» (o le suma cantidad si ya estaba)."""
    carrito = st.session_state.setdefault("carrito", {})
    if fila["ID"] in carrito:
        carrito[fila["ID"]]["cantidad"] += int(cantidad)
        st.session_state.pop(f"cant_cart_{fila['ID']}", None)
        # Sumarlo otra vez es que se lo lleva, aunque antes se lo hubiera destildado (ver
        # pasar_el_presupuesto_a_una_venta()).
        carrito[fila["ID"]]["se_lleva"] = True
        st.session_state.pop(f"se_lleva_{fila['ID']}", None)
        # Y los campos de la pantalla se ponen al día antes de dibujarse: ver «LO QUE CAMBIA
        # POR ATRÁS» en logica/interfaz.py.
        poner_en_el_campo(f"cant_cart_{fila['ID']}", carrito[fila["ID"]]["cantidad"])
        poner_en_el_campo(f"se_lleva_{fila['ID']}", True)
    else:
        carrito[fila["ID"]] = {"codigo": fila["Codigo"], "marca": fila["Marca"],
                               "descripcion": fila.get("Descripcion") or "",
                               "precio": fila.get("Precio") or 0, "cantidad": int(cantidad)}

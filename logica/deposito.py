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


def pedir_al_deposito(producto_id, cantidad=1, mecanico_id=None, codigo_de_retiro="",
                      usuario="", nota=""):
    """El pedido del mostrador. Devuelve (True, aviso) o (False, por qué no).

    Si es para una cuenta que pide código de retiro, el código se pide y se gasta ACÁ, en el
    mostrador, que es donde está el que viene a buscar: el depósito no lo ve. El límite de
    crédito también se mira acá, contra el precio con descuento."""
    try:
        cantidad = int(cantidad)
    except (TypeError, ValueError):
        return False, "La cantidad no es un número."
    if not 1 <= cantidad <= CANTIDAD_MAXIMA_POR_PEDIDO:
        return False, f"La cantidad va de 1 a {CANTIDAD_MAXIMA_POR_PEDIDO}."
    c.execute("SELECT precio FROM productos WHERE id = ?", (producto_id,))
    prod = c.fetchone()
    if not prod:
        return False, "Ese producto ya no está en el catálogo."
    if mecanico_id:
        config = configuracion_de_cuenta(mecanico_id)
        importe = precio_de_la_cuenta(prod["precio"], config["descuento"]) * cantidad
        estado = estado_de_cuenta(mecanico_id)
        if config["limite"] and estado["saldo"] + importe > config["limite"]:
            return False, (f"Pasa el límite de crédito de la cuenta: debe "
                           f"{formato_precio(estado['saldo'])} y el límite es "
                           f"{formato_precio(config['limite'])}.")
    with db_lock, transaccion():
        if mecanico_id and configuracion_de_cuenta(mecanico_id)["pide_codigo"]:
            codigo_id = _codigo_de_retiro_vigente(mecanico_id, codigo_de_retiro)
            if not codigo_id:
                return False, ("El código de retiro no es válido, ya se usó o venció. El taller "
                               "genera uno nuevo en su portal.")
            c.execute("UPDATE codigos_de_retiro SET usado_en = datetime('now', 'localtime') "
                      "WHERE id = ?", (codigo_id,))
        c.execute("""INSERT INTO pedidos_deposito (producto_id, cantidad, mecanico_id, nota,
                                                   pedido_por)
                     VALUES (?, ?, ?, ?, ?)""",
                  (producto_id, cantidad, mecanico_id or None, (nota or "").strip()[:200],
                   usuario or obtener_usuario_actual()))
    return True, "📦 Pedido al depósito. Lo ven en «📦 Depósito»."


def pedidos_pendientes():
    """Lo que el depósito tiene que buscar, ordenado por ubicación (lo que no tiene ubicación,
    al final) para juntarlo en un solo recorrido. Sin precios: no le hacen falta al depósito,
    y es la pantalla que puede estar a la vista de un cliente."""
    c.execute("""SELECT d.id, d.cantidad, d.nota, d.pedido_por, d.pedido_en, d.mecanico_id,
                        p.id AS producto_id, p.codigo_raw, p.descripcion, p.stock,
                        COALESCE(NULLIF(TRIM(p.ubicacion), ''), '') AS ubicacion,
                        m.nombre AS marca, k.nombre AS cuenta
                 FROM pedidos_deposito d
                 JOIN productos p ON p.id = d.producto_id
                 JOIN marcas m ON m.id = p.marca_id
                 LEFT JOIN mecanicos k ON k.id = d.mecanico_id
                 WHERE d.estado = 'pendiente'
                 ORDER BY ubicacion = '', ubicacion, d.pedido_en""")
    return [dict(r) for r in c.fetchall()]


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
        if f["stock"] is not None:
            c.execute("UPDATE productos SET stock = MAX(0, stock - ?) WHERE id = ?",
                      (f["cantidad"], f["producto_id"]))
        c.execute("""INSERT INTO ventas_registradas (producto_id, termino_pedido,
                                                     codigo_pedido_clean, usuario)
                     VALUES (?, ?, ?, ?)""",
                  (f["producto_id"], f["codigo_raw"], sanitizar(f["codigo_raw"]), usuario))
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
    return True, (f"✅ Entregado: {f['codigo_raw']} x{f['cantidad']}"
                  + (" — cargado en la cuenta." if movimiento_id else "."))


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
    Mostrador incluida). Cada renglón trae el precio de lista, el descuento y lo cobrado."""
    c.execute("""SELECT d.id, d.cantidad, d.resuelto_en, d.precio_lista, d.descuento, d.importe,
                        d.mecanico_id, p.codigo_raw, p.descripcion, m.nombre AS marca,
                        k.nombre AS cuenta
                 FROM pedidos_deposito d
                 JOIN productos p ON p.id = d.producto_id
                 JOIN marcas m ON m.id = p.marca_id
                 LEFT JOIN mecanicos k ON k.id = d.mecanico_id
                 WHERE d.estado = 'entregado' AND d.facturado_en IS NULL
                 ORDER BY k.nombre IS NULL, k.nombre, d.resuelto_en""")
    salida = {}
    for r in c.fetchall():
        salida.setdefault((r["mecanico_id"], r["cuenta"] or NOMBRE_DEL_MOSTRADOR), []).append(
            dict(r))
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
    c.execute("""SELECT d.id, d.cantidad, d.estado, d.resuelto_por, d.resuelto_en,
                        p.codigo_raw, m.nombre AS marca, k.nombre AS cuenta
                 FROM pedidos_deposito d
                 JOIN productos p ON p.id = d.producto_id
                 JOIN marcas m ON m.id = p.marca_id
                 LEFT JOIN mecanicos k ON k.id = d.mecanico_id
                 WHERE d.estado <> 'pendiente'
                 ORDER BY d.resuelto_en DESC LIMIT ?""", (limite,))
    return [dict(r) for r in c.fetchall()]


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
    cuál (si hay varios), cuántos, para quién y, si esa cuenta lo pide, el código de retiro.

    No muestra ningún precio: lo puede estar mirando el cliente del otro lado del mostrador, y
    el de la cuenta lleva el descuento (ver «EL DESCUENTO NO SE VE»)."""
    if not resultados:
        return
    with st.popover("📦 Pedir al depósito", width="stretch"):
        rotulos = {f["ID"]: f"{f['Marca']} - {f['Codigo']}" for f in resultados}
        if len(rotulos) == 1:
            producto_id = next(iter(rotulos))
            st.caption(rotulos[producto_id])
        else:
            producto_id = st.selectbox("¿Cuál?", list(rotulos), format_func=rotulos.get,
                                       key=f"dep_cual_{clave}")
        cantidad = st.number_input("Cantidad", min_value=1, max_value=CANTIDAD_MAXIMA_POR_PEDIDO,
                                   value=1, step=1, key=f"dep_cant_{clave}")
        nombres = dict([(None, NOMBRE_DEL_MOSTRADOR)] + cuentas_para_pedir())
        para = st.selectbox("Para:", list(nombres), format_func=nombres.get,
                            key=f"dep_para_{clave}",
                            help="Si es para la cuenta de un taller o mayorista, al entregarlo "
                                 "queda cargado en su cuenta, para facturar.")
        codigo = ""
        if para and configuracion_de_cuenta(para)["pide_codigo"]:
            codigo = st.text_input("Código de retiro", max_chars=6, key=f"dep_cod_{clave}",
                                   placeholder="6 números, del portal del taller")
        nota = st.text_input("Nota para el depósito (opcional)", max_chars=200,
                             key=f"dep_nota_{clave}", placeholder="Ej.: lo espera en el mostrador")
        if st.button("📦 Pedir", type="primary", key=f"dep_pedir_{clave}", width="stretch"):
            ok, aviso = pedir_al_deposito(producto_id, cantidad, para, codigo, nota=nota)
            (st.success if ok else st.error)(aviso)
        st.caption("No hace falta tocar «🛒 Se llevó»: la venta se anota sola cuando el depósito "
                   "lo entrega.")

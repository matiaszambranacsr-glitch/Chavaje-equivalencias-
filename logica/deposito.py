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


def el_aviso_del_pedido(pedido):
    """El cartel de un pedido que acaba de llegar al depósito: qué, cuánto, para quién y quién lo
    pidió. Sin precios, como todo lo del depósito."""
    return (f"📦 {pedido['cantidad']}× {pedido['marca']} {pedido['codigo_raw']} · para "
            f"{pedido.get('cuenta') or NOMBRE_DEL_MOSTRADOR} · pidió {pedido.get('pedido_por') or '¿?'}")


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
                vence = (hoy_aca() + timedelta(days=config["dias_de_plazo"])).isoformat()
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
    # La contraseña de quien lo tiene (se prueba contra él: ver «CADA UNO ENTRA CON SU USUARIO Y
    # SU CONTRASEÑA» en logica/base.py) o la de cualquier administrador.
    nombre, nivel, error = validar_password(codigo, usuario=persona, o_un_administrador=True)
    if error:
        return None, error
    if nivel == "admin":
        return "clave de administrador", nombre
    if nivel:
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
    [(producto_id, cuántas)]. b"" si no hay nada."""
    etiquetas = []
    for producto_id, cuantas in items:
        c.execute("""SELECT p.id, p.codigo_raw, p.descripcion, m.nombre AS marca
                     FROM productos p JOIN marcas m ON m.id = p.marca_id WHERE p.id = ?""",
                  (producto_id,))
        f = c.fetchone()
        if f:
            etiquetas += [{"titulo": f"{f['marca']} {f['codigo_raw']}",
                           "detalle": f["descripcion"] or "",
                           "barras": codigo_nuestro(f["id"])}
                          ] * max(0, min(int(cuantas), CANTIDAD_MAXIMA_POR_PEDIDO * 4))
    return pdf_de_etiquetas_con_barras(etiquetas)


def pdf_de_etiquetas_con_barras(etiquetas):
    """Una hoja A4 de etiquetas, tres columnas por ocho filas: cada una con su título, una línea
    de detalle y un código de barras Code 39 con el texto abajo. `etiquetas`: [{titulo,
    detalle, barras}]. La usan las de los productos y las de los estantes (ver
    pdf_de_etiquetas_de_ubicaciones()). b"" si no hay nada."""
    if not etiquetas:
        return b""
    from fpdf import FPDF

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
        pdf.cell(ancho, 4, limpiar(e["titulo"])[:34])
        pdf.set_xy(x, y + 4)
        pdf.set_font("Helvetica", "", 7)
        pdf.cell(ancho, 4, limpiar(e["detalle"])[:44])
        # LO QUE LEE UN LECTOR: fpdf toma `w` como la barra GRUESA (la fina es un tercio). Con
        # w=0.3 la fina quedaba en 0,1 mm y ningún lector la levantaba (probado decodificando el
        # PDF). Cada carácter de Code 39 ocupa 16 barras finas, más 10 de margen blanco a cada
        # lado: la fina, lo más cerca de 0,33 mm que entre en la etiqueta, y centrado.
        texto = f"*{e['barras']}*"
        fina = min(0.33, (ancho - 2) / (16 * len(texto) + 20))
        largo = 16 * len(texto) * fina - fina
        pdf.code39(texto, x=x + (ancho - largo) / 2, y=y + 9, w=3 * fina, h=16)
        pdf.set_xy(x, y + 27)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(ancho, 4, limpiar(e["barras"]))
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
                        date(d.resuelto_en, '-3 hours') = date('now', '-3 hours') AS es_de_hoy
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
# ELEGIR UNA CUENTA ENTRE MILES
# ============================================================================================
# Lo pidió el dueño: «hacé que las cuentas para vender tengan un buscador porque se van a sumar
# más de 2000 cuentas, sería una locura scrollear para encontrar cada una». La cuenta se elegía
# de una lista desplegable con todas: con diez talleres alcanza; con dos mil, no.
#   · Se escribe una parte del nombre —sin acentos, en cualquier orden, «gar taller» encuentra
#     «Taller García»—, el CUIT o el número de la cuenta, y quedan unas pocas para tocar.
#   · Sin escribir nada salen las últimas que atendió quien está en la pantalla: en el
#     mostrador casi siempre es uno de los de siempre.
#   · Con pocas cuentas (hasta CUENTAS_PARA_ELEGIR_SIN_BUSCAR) sigue la lista de antes: un
#     toque menos.
# Es una sola pieza (elegir_cuenta()) para todos los lugares donde se elige una: «🧾 Atendiendo
# a», poner a cuenta en la caja, «👥 Cada cuenta», Cuentas corrientes y los talleres de Usuarios.
CUENTAS_PARA_ELEGIR_SIN_BUSCAR = 12
# Pocas a la vista: en el celular, con más, el botón de abajo quedaba fuera de la pantalla.
CUENTAS_QUE_SE_MUESTRAN = 6


def cuits_de_las_cuentas():
    """{mecanico_id: CUIT} de las cuentas que lo tienen cargado (en su cuenta corriente, o de la
    primera factura que se les hizo)."""
    c.execute("SELECT clave, valor FROM configuracion WHERE clave LIKE 'cuit_taller_%'")
    cuits = {}
    for f in c.fetchall():
        numero = f["clave"][len("cuit_taller_"):]
        if numero.isdigit() and f["valor"]:
            cuits[int(numero)] = re.sub(r"\D", "", str(f["valor"]))
    return cuits


def buscar_cuentas(texto, cuentas=None, tope=CUENTAS_QUE_SE_MUESTRAN):
    """Las cuentas que calzan con lo escrito: ([(id, nombre)] las mejores primero, cuántas
    calzan en total). Todas las palabras tienen que estar en el nombre, sin importar acentos,
    mayúsculas ni el orden; un número busca también por CUIT y por número de cuenta. Primero la
    que tiene ese número, después las que empiezan con lo escrito, las que tienen una palabra
    que empieza así, y el resto; a igual puesto, por nombre."""
    cuentas = cuentas_para_pedir() if cuentas is None else cuentas
    palabras = normalizar_texto(texto).split()
    if not palabras:
        return [], 0
    entero = normalizar_texto(texto)
    numero = re.sub(r"[\s.\-]", "", str(texto or ""))
    numero = numero.lstrip("#") if numero.lstrip("#").isdigit() else ""
    cuits = cuits_de_las_cuentas() if numero else {}
    encontradas = []
    for cuenta_id, nombre in cuentas:
        limpio = normalizar_texto(nombre)
        por_nombre = all(p in limpio for p in palabras)
        por_numero = bool(numero) and (str(cuenta_id) == numero
                                       or (len(numero) >= 4 and numero in cuits.get(cuenta_id, "")))
        if not (por_nombre or por_numero):
            continue
        puesto = (0 if numero and str(cuenta_id) == numero
                  else 1 if limpio.startswith(entero)
                  else 2 if all(any(w.startswith(p) for w in limpio.split()) for p in palabras)
                  else 3)
        encontradas.append((puesto, limpio, cuenta_id, nombre))
    encontradas.sort()
    return [(i, n) for _p, _l, i, n in encontradas[:tope]], len(encontradas)


def cuentas_recientes(persona=None, tope=6):
    """[(id, nombre)] de las últimas cuentas activas que atendió esa persona (quien está en la
    pantalla, si no se dice): a las que les vendió o les pidió algo al depósito, la última
    primero."""
    persona = persona or obtener_usuario_actual()
    c.execute("""SELECT m.id, m.nombre, MAX(x.cuando) AS ultima FROM (
                     SELECT mecanico_id, fecha AS cuando FROM ventas
                     WHERE usuario = ? AND mecanico_id IS NOT NULL AND anulada = 0
                     UNION ALL
                     SELECT mecanico_id, pedido_en FROM pedidos_deposito
                     WHERE pedido_por = ? AND mecanico_id IS NOT NULL) x
                 JOIN mecanicos m ON m.id = x.mecanico_id AND m.activo = 1
                 GROUP BY m.id ORDER BY ultima DESC LIMIT ?""", (persona, persona, tope))
    return [(f["id"], f["nombre"]) for f in c.fetchall()]


def elegir_cuenta(clave, etiqueta="Cuenta:", cuentas=None, vacia="El taller o mayorista",
                  elegida=None):
    """El campo para elegir una cuenta: devuelve su id, o None si todavía no se eligió. Con
    pocas, la lista de siempre; con muchas, el buscador (ver «ELEGIR UNA CUENTA ENTRE MILES»).
    `cuentas`: [(id, nombre)] entre las que se elige (las activas, si no se dice). `elegida`: la
    que arranca elegida donde siempre hay una a la vista (Cuentas corrientes)."""
    cuentas = cuentas_para_pedir() if cuentas is None else cuentas
    nombres = dict(cuentas)
    if len(cuentas) <= CUENTAS_PARA_ELEGIR_SIN_BUSCAR:
        ids = list(nombres)
        return st.selectbox(etiqueta, ids, format_func=nombres.get,
                            index=ids.index(elegida) if elegida in nombres else None,
                            placeholder=vacia, key=f"cuenta_sel_{clave}")
    texto = st.text_input(f"🔎 {etiqueta}", key=f"cuenta_buscar_{clave}",
                          placeholder="Parte del nombre, CUIT o número de cuenta",
                          help=f"Hay {miles(len(cuentas))} cuentas: escribí una parte del nombre "
                               "(«gar taller» encuentra «Taller García»), el CUIT o el número. "
                               "Sin escribir nada, las últimas que atendiste.")
    if texto.strip():
        encontradas, cuantas = buscar_cuentas(texto, cuentas)
        if not encontradas:
            st.caption("No hay ninguna cuenta con eso. Probá con menos letras o con otra parte "
                       "del nombre.")
            return None
        titulo = "Encontradas:" if cuantas > 1 else "Encontrada:"
    else:
        encontradas = [x for x in cuentas_recientes() if x[0] in nombres]
        titulo = "Las últimas que atendiste:" if encontradas else "A la vista:"
        if elegida in nombres and elegida not in dict(encontradas):
            encontradas.insert(0, (elegida, nombres[elegida]))
        cuantas = len(encontradas)
        if not encontradas:
            return None
    opciones = [i for i, _n in encontradas]
    # Elegida sola la única que calza, o la que ya estaba: un toque menos.
    de_entrada = (0 if len(opciones) == 1 else opciones.index(elegida) if elegida in opciones
                  else None)
    # La clave lleva lo buscado: con una sola, el redondel se quedaba con la elegida de la
    # búsqueda anterior aunque ya no estuviera entre las de ahora.
    cual = st.radio(titulo, opciones, index=de_entrada,
                    format_func=lambda i: f"{nombres[i]}  ·  N.º {i}",
                    key=f"cuenta_cual_{clave}_{normalizar_texto(texto)}")
    if cuantas > len(encontradas):
        st.caption(f"…y {miles(cuantas - len(encontradas))} más: escribí algo más para "
                   "achicar la lista.")
    return cual


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


# LO QUE SUELE LLEVAR UNA CUENTA. Un taller compra casi siempre lo mismo (los filtros, las
# pastillas, el aceite de los autos que atiende), y cada vez había que buscarlo de nuevo. Con la
# cuenta elegida, «🔁 Lo que suele llevar» muestra lo que llevó dos veces o más en los últimos
# DIAS_DE_LO_QUE_SUELE_LLEVAR (en ventas a su nombre y en lo que el depósito le entregó), y se
# suma con un toque.
DIAS_DE_LO_QUE_SUELE_LLEVAR = 120


def lo_que_suele_llevar(mecanico_id, limite=8):
    """[dict] con ID, Marca, Codigo, Descripcion, Veces y Ultima (cuándo, como está guardado):
    lo que la cuenta llevó dos veces o más, lo de más veces primero."""
    hace = f"-{DIAS_DE_LO_QUE_SUELE_LLEVAR} days"
    filas = c.execute(
        """SELECT s.producto_id AS id, COUNT(*) AS veces, MAX(s.cuando) AS ultima
           FROM (SELECT vi.producto_id, v.fecha AS cuando FROM ventas_items vi
                 JOIN ventas v ON v.id = vi.venta_id
                 WHERE v.anulada = 0 AND v.mecanico_id = ? AND v.fecha >= datetime('now', ?)
                 UNION ALL
                 SELECT d.producto_id, COALESCE(d.resuelto_en, d.pedido_en) FROM pedidos_deposito d
                 WHERE d.estado = 'entregado' AND d.mecanico_id = ?
                   AND COALESCE(d.resuelto_en, d.pedido_en) >= datetime('now', ?)) s
           WHERE s.producto_id IS NOT NULL
           GROUP BY s.producto_id HAVING COUNT(*) >= 2
           ORDER BY veces DESC, ultima DESC LIMIT ?""",
        (int(mecanico_id), hace, int(mecanico_id), hace, int(limite))).fetchall()
    salida = []
    for f in filas:
        actual = item_de_venta(f["id"])
        if actual:
            salida.append({"ID": f["id"], "Marca": actual["marca"], "Codigo": actual["codigo"],
                           "Descripcion": actual["descripcion"], "Veces": f["veces"],
                           "Ultima": f["ultima"]})
    return salida


def sumar_lo_que_suele_llevar(producto_id):
    """«➕» de «🔁 Lo que suele llevar» (va como on_click): a la venta, uno más."""
    sumado = sumar_a_la_venta({"ID": int(producto_id)})
    if sumado:
        avisar("success", f"➕ Sumado: {sumado['marca']} {sumado['codigo']} "
                          f"(van {sumado['cantidad']}).")


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
        nueva = elegir_cuenta(clave, cuentas=list(nombres.items()))
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


def sumar_al_presupuesto_y_avisar(fila):
    """«🛒 Sumar al presupuesto» del menú del click derecho. Va como on_click."""
    sumar_al_presupuesto(fila)
    avisar("success", f"🛒 {fila['Marca']} {fila['Codigo']} sumado al presupuesto (arriba de "
                      "todo, en «Presupuesto en armado»).")


def quitar_del_presupuesto(producto_id):
    """«🗑️» de un ítem del presupuesto. También la cantidad que guardaba su campo: sin eso,
    volver a sumarlo lo traía con la cantidad vieja en vez de 1. Va como on_click."""
    st.session_state.get("carrito", {}).pop(producto_id, None)
    st.session_state.pop(f"cant_cart_{producto_id}", None)


def mostrar_mas_acciones_del_producto(fila, clave):
    """Lo que en el celular no entra en el renglón de un resultado, y en la computadora va en
    el menú del click derecho (ver «EL CLICK DERECHO» en logica/interfaz.py): sumarlo al
    presupuesto y ver dónde está. Va adentro de acciones_del_renglon()."""
    if es_celular():
        return
    if es_empleado_o_abierto() and not modo_solo_lectura():
        st.button("🛒 Sumar al presupuesto", key=f"al_presupuesto_{clave}",
                  on_click=sumar_al_presupuesto_y_avisar, args=(dict(fila),))
    if hay_mapa():
        st.button("📍 ¿Dónde está?", key=f"donde_{clave}", on_click=ver_donde_esta,
                  args=(fila["ID"],))


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


# ============================================================================================
# ENTRÓ MERCADERÍA: EL STOCK PROPIO
# ============================================================================================
# En la copia de la base real, ninguno de los 86.946 productos tenía stock: el stock entraba solo
# si la lista del proveedor traía esa columna (y ese es el stock del proveedor, no el del
# local), o leyendo la foto del remito con la IA, que necesita una clave. Sin stock no andan
# «⏳ Anotar que lo espera» con su «📲 Avisarle», el «sin stock» de los pedidos del chat ni el
# orden por lo que hay. «📦 Entró mercadería» lo carga sin IA: con el lector de códigos (o
# escribiendo el código) y la cantidad, o con el remito en Excel o CSV. Se arma una lista, se
# revisa, y «✅ Sumar al stock» la suma de una (y lo anota en el registro de cambios). Las
# ventas y lo entregado del depósito ya lo descuentan.
ENTRADAS_RECORDADAS = 50        # cuántas entradas sumadas se recuerdan, para no sumar dos veces
# EL CONTEO: para la primera carga (o para corregir), lo que importa es lo que hay, no lo que
# entró. Con «🔢 Conteo», escanear cada unidad la cuenta, y «✅ Dejar el stock en lo contado» lo
# deja así (con la diferencia anotada). Lo que no se contó queda como estaba.
MODOS_DE_LA_ENTRADA = ("➕ Entró (suma al stock)", "🔢 Conteo (deja lo contado)")


def productos_con_el_codigo(texto):
    """Los productos con ese código o código de barras, de las listas (no las referencias de
    fábrica, que no son algo que entra): [dict] con ID, Codigo, Marca, Descripcion y Stock."""
    limpio = sanitizar(str(texto or ""))
    if not limpio:
        return []
    return [dict(f) for f in c.execute(
        """SELECT p.id AS "ID", p.codigo_raw AS "Codigo", m.nombre AS "Marca",
                  p.descripcion AS "Descripcion", p.stock AS "Stock"
           FROM productos p JOIN marcas m ON m.id = p.marca_id
           WHERE (p.codigo_clean = ? OR p.codigo_barras = ?) AND m.tipo <> 'OEM'
           ORDER BY m.nombre LIMIT 20""", (limpio, limpio)).fetchall()]


def sumar_a_la_entrada(producto_id, cantidad=1):
    """Suma a la lista de lo que entró (en la sesión, hasta «✅ Sumar al stock»)."""
    lista = st.session_state.setdefault("entro_lista", {})
    clave = str(int(producto_id))
    lista[clave] = lista.get(clave, 0) + max(1, int(cantidad or 1))
    # El campo de la cantidad guarda lo suyo: escaneado otra vez, tiene que mostrar la nueva.
    poner_en_el_campo(f"entro_cant_{clave}", lista[clave])


def huella_de_la_entrada(lista):
    return hashlib.md5(json.dumps(sorted((str(k), int(v)) for k, v in lista.items()))
                       .encode()).hexdigest()[:16]


def cuando_se_sumo_la_entrada(lista):
    """Si esta misma entrada (los mismos productos y cantidades) ya se sumó: cuándo, o None.
    El mismo remito subido dos veces duplicaba el stock."""
    try:
        return json.loads(obtener_config("entradas_sumadas", "") or "{}").get(
            huella_de_la_entrada(lista))
    except ValueError:
        return None


def sumar_al_stock(lista):
    """Suma lo que entró al stock: `lista` es {producto_id: cantidad}. Devuelve (productos
    sumados, consultas de clientes que esperaban algo de esto y ahora tienen stock, lo que se
    le había pedido al proveedor y con esto llegó: ver dar_por_llegado_lo_que_entro())."""
    exigir_nivel("empleado", "sumar mercadería al stock")
    ya_estaban = {x["_id"] for x in consultas_que_ahora_hay_en_stock()}
    sumados = 0
    with db_lock, transaccion():
        for pid, cantidad in lista.items():
            fila = c.execute("SELECT stock FROM productos WHERE id = ?", (int(pid),)).fetchone()
            if not fila or int(cantidad or 0) <= 0:
                continue
            c.execute("UPDATE productos SET stock = COALESCE(stock, 0) + ? WHERE id = ?",
                      (int(cantidad), int(pid)))
            anotar_cambio("entró mercadería", "producto", pid, fila["stock"],
                          (fila["stock"] or 0) + int(cantidad))
            sumados += 1
        try:
            sumadas = json.loads(obtener_config("entradas_sumadas", "") or "{}")
        except ValueError:
            sumadas = {}
        sumadas[huella_de_la_entrada(lista)] = ahora_aca().strftime("%d/%m %H:%M")
        c.execute("INSERT INTO configuracion (clave, valor) VALUES ('entradas_sumadas', ?) "
                  "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                  (json.dumps(dict(list(sumadas.items())[-ENTRADAS_RECORDADAS:])),))
        llegaron = dar_por_llegado_lo_que_entro(lista)
    ahora = [x for x in consultas_que_ahora_hay_en_stock() if x["_id"] not in ya_estaban]
    return sumados, ahora, llegaron


def dejar_el_stock_en_lo_contado(lista):
    """El conteo: deja el stock de cada producto de `lista` ({producto_id: contado}) en lo
    contado. Devuelve ([(«MARCA CÓDIGO», había, hay)] de los que cambiaron, consultas de
    clientes que ahora tienen stock)."""
    exigir_nivel("empleado", "corregir el stock con un conteo")
    ya_estaban = {x["_id"] for x in consultas_que_ahora_hay_en_stock()}
    diferencias = []
    with db_lock, transaccion():
        for pid, contado in lista.items():
            fila = c.execute("""SELECT p.stock, p.codigo_raw, m.nombre AS marca FROM productos p
                                JOIN marcas m ON m.id = p.marca_id WHERE p.id = ?""",
                             (int(pid),)).fetchone()
            if not fila or int(contado) < 0 or fila["stock"] == int(contado):
                continue
            c.execute("UPDATE productos SET stock = ? WHERE id = ?", (int(contado), int(pid)))
            anotar_cambio("conteo de stock", "producto", pid, fila["stock"], int(contado))
            diferencias.append((f"{fila['marca']} {fila['codigo_raw']}", fila["stock"],
                                int(contado)))
    ahora = [x for x in consultas_que_ahora_hay_en_stock() if x["_id"] not in ya_estaban]
    return diferencias, ahora


def _columna_que_dice(titulos, patron):
    """La primera columna cuyo título encaja con `patron`, o None."""
    for i, t in enumerate(titulos):
        if re.search(patron, normalizar_texto(str(t or "")).upper()):
            return i
    return None


def leer_el_remito_de_entrada(filas, col_codigo, col_cantidad, desde=1):
    """Las filas del remito, cotejadas con el catálogo: (para sumar [(producto_id, cantidad)],
    no están [código], con varias marcas [código]). Las que tienen varias marcas con ese código
    se eligen a mano, de a una: sumar a ciegas a la primera era cargar stock a otra marca."""
    sumar, no_estan, varias = [], [], []
    for fila in filas[desde:]:
        if col_codigo >= len(fila) or not str(fila[col_codigo] or "").strip():
            continue
        codigo = str(fila[col_codigo]).strip()
        cantidad = leer_numero(fila[col_cantidad]) if col_cantidad < len(fila) else None
        if not cantidad or cantidad <= 0:
            continue
        encontrados = productos_con_el_codigo(codigo)
        if len(encontrados) == 1:
            sumar.append((encontrados[0]["ID"], int(round(cantidad))))
        elif encontrados:
            varias.append(codigo)
        else:
            no_estan.append(codigo)
    return sumar, no_estan, varias


def mostrar_entro_mercaderia():
    """La solapa «📦 Entró mercadería» del Depósito."""
    ayuda("Cargá lo que entró: **escaneá el código** (o escribilo) y la cantidad, y Enter; o "
          "**subí el remito** en Excel o CSV y elegí qué columna es el código y cuál la "
          "cantidad. Se arma la lista de abajo: revisala y tocá **«✅ Sumar al stock»**. Lo "
          "mismo escaneado dos veces suma dos. Si un código está en varias marcas, elegís cuál "
          "entró. Las ventas y lo entregado del depósito ya descuentan del stock. Si alguien "
          "esperaba algo de lo que entró, te avisa para que le escribas.\n\n"
          "**🔢 Conteo** (para la primera carga, o para corregir): escaneá cada unidad que hay "
          "y «✅ Dejar el stock en lo contado» lo deja así, con la diferencia anotada. Lo que "
          "no contaste queda como estaba.")
    lista = st.session_state.setdefault("entro_lista", {})
    modo = st.radio("Qué cargás:", MODOS_DE_LA_ENTRADA, key="entro_modo", horizontal=True,
                    help="«Entró» suma lo escaneado al stock. «Conteo» deja el stock en lo "
                         "contado (para la primera carga o para corregir): escaneá cada unidad, "
                         "y lo que no contaste queda como estaba.")
    contando = modo == MODOS_DE_LA_ENTRADA[1]
    with st.form("form_entro_mercaderia", clear_on_submit=True, border=False):
        _c1, _c2, _c3 = st.columns([4, 1, 1], vertical_alignment="bottom")
        codigo = _c1.text_input("Código (escaneado o escrito):", key="entro_codigo",
                                placeholder="Escaneá o escribí el código y Enter")
        cantidad = _c2.number_input("Cant.", 1, 9999, 1, key="entro_cant")
        sumar = _c3.form_submit_button("➕ Sumar", width="stretch")
    if sumar and str(codigo or "").strip():
        encontrados = productos_con_el_codigo(codigo)
        if len(encontrados) == 1:
            sumar_a_la_entrada(encontrados[0]["ID"], cantidad)
            st.success(f"➕ {encontrados[0]['Marca']} {encontrados[0]['Codigo']} × "
                       f"{miles(cantidad)}")
        elif encontrados:
            st.session_state["entro_elegir"] = {"codigo": str(codigo).strip(),
                                                "cantidad": int(cantidad),
                                                "opciones": [x["ID"] for x in encontrados]}
        else:
            st.warning(f"«{str(codigo).strip()}» no está en el catálogo. Si es nuevo, cargalo "
                       "con su lista en 📁 Cargar Excel.")
    _elegir = st.session_state.get("entro_elegir")
    if _elegir:
        _ops = {x["ID"]: x for x in productos_con_el_codigo(_elegir["codigo"])}
        st.info(f"«{_elegir['codigo']}» está en {len(_ops)} marcas: ¿cuál entró?")
        _cual = st.selectbox(
            "Cuál entró:", list(_ops), label_visibility="collapsed",
            key=f"entro_cual_{hashlib.md5(_elegir['codigo'].encode()).hexdigest()[:8]}",
            # rótulo fijo: marca, código y descripción.
            format_func=lambda x: f"{_ops[x]['Marca']} {_ops[x]['Codigo']} — "
                                  f"{str(_ops[x]['Descripcion'] or '')[:60]}")

        def _elegido(producto_id, cantidad_elegida):
            sumar_a_la_entrada(producto_id, cantidad_elegida)
            st.session_state.pop("entro_elegir", None)
        _e1, _e2 = st.columns(2)
        _e1.button("➕ Esa", key="entro_cual_si", type="primary", width="stretch",
                   on_click=_elegido, args=(_cual, _elegir["cantidad"]))
        _e2.button("Ninguna", key="entro_cual_no", width="stretch",
                   on_click=lambda: st.session_state.pop("entro_elegir", None))

    # EL REMITO EN EXCEL O CSV.
    _exp_remito = st.expander("📄 Subir el remito (Excel o CSV)", key="exp_entro_remito",
                              on_change="rerun")
    if _exp_remito.open:
        with _exp_remito:
            archivo = subir_archivo("El remito del proveedor:", ["xlsx", "xls", "csv", "txt"],
                                    "remito_de_entrada")
            filas = leer_excel(archivo) if archivo is not None else []
            filas = [f for f in filas if any(str(x or "").strip() for x in f)]
            if archivo is not None and not filas:
                st.warning("No se pudo leer nada en ese archivo.")
            elif filas:
                _huella = hashlib.md5(json.dumps(filas[:50], default=str).encode()).hexdigest()[:8]
                titulos = [str(x or "") for x in filas[0]]
                _opciones = list(range(len(titulos)))
                _rot = lambda i: f"{chr(65 + i) if i < 26 else i + 1}: {titulos[i][:30]}"  # noqa
                _cc, _cq = st.columns(2)
                col_cod = _cc.selectbox(
                    "Columna del código:", _opciones, key=f"entro_col_cod_{_huella}",
                    index=_columna_que_dice(titulos, r"COD|ARTIC|REFER|PARTE|ITEM") or 0,
                    format_func=_rot)  # rótulo fijo: los títulos del archivo
                col_cant = _cq.selectbox(
                    "Columna de la cantidad:", _opciones, key=f"entro_col_cant_{_huella}",
                    index=_columna_que_dice(titulos, r"CANT|UNID|CNT|QTY")
                    or min(1, len(_opciones) - 1), format_func=_rot)  # rótulo fijo
                para_sumar, no_estan, varias = leer_el_remito_de_entrada(filas, col_cod,
                                                                         col_cant)
                st.caption(f"De {miles(len(filas) - 1)} renglón(es): {miles(len(para_sumar))} "
                           f"encontrados, {miles(len(no_estan))} que no están en el catálogo y "
                           f"{miles(len(varias))} con varias marcas (esos, escaneados uno por "
                           "uno arriba).")
                if no_estan or varias:
                    st.caption("No están: " + ", ".join(no_estan[:15])
                               + (" …" if len(no_estan) > 15 else "")
                               + (" · Varias marcas: " + ", ".join(varias[:15]) if varias
                                  else ""))

                def _sumar_el_remito(renglones):
                    for pid, cant in renglones:
                        sumar_a_la_entrada(pid, cant)
                st.button(f"➕ Sumar los {miles(len(para_sumar))} a la lista",
                          key=f"entro_remito_{_huella}", disabled=not para_sumar,
                          on_click=_sumar_el_remito, args=(para_sumar,))

    # LA LISTA, PARA REVISAR ANTES DE SUMAR.
    if not lista:
        st.caption("Todavía no cargaste nada.")
        return
    st.markdown(f"**{'Lo contado' if contando else 'Lo que entró'}:** {miles(len(lista))} "
                f"producto(s), {miles(sum(lista.values()))} unidad(es)")
    datos = {}
    for tanda, marcadores in en_tandas([int(k) for k in lista]):      # un remito puede ser largo
        datos.update({str(f["id"]): f for f in c.execute(
            f"""SELECT p.id, p.codigo_raw, p.descripcion, p.stock, m.nombre AS marca
                FROM productos p JOIN marcas m ON m.id = p.marca_id
                WHERE p.id IN ({marcadores})""", tanda)})

    def _cambiar(pid):
        lista[pid] = int(st.session_state.get(f"entro_cant_{pid}") or 1)

    def _sacar(pid):
        lista.pop(pid, None)
    for pid in list(lista):
        f = datos.get(pid)
        if not f:
            lista.pop(pid, None)
            continue
        _r1, _r2, _r3 = st.columns([5, 2, 1], vertical_alignment="center")
        _r1.markdown(f"**{texto_para_markdown(f['marca'])} {texto_para_markdown(f['codigo_raw'])}**"
                     f" — {texto_para_markdown(str(f['descripcion'] or '')[:50])}")
        _hoy = miles(f["stock"]) if f["stock"] is not None else "sin cargar"
        _r1.caption(f"stock hoy: {_hoy}" + (
            f" → contado: {miles(lista[pid])}"
            + (f" ({'+' if lista[pid] > (f['stock'] or 0) else ''}"
               f"{miles(lista[pid] - (f['stock'] or 0))})"
               if f["stock"] is not None and lista[pid] != f["stock"] else "")
            if contando else ""))
        # Desde 0: en el conteo, lo que se buscó y no está se cuenta como cero.
        _r2.number_input("Cant.", 0, 9999, key=f"entro_cant_{pid}",
                         value=valor_del_campo(f"entro_cant_{pid}", lista[pid]),
                         label_visibility="collapsed", on_change=_cambiar, args=(pid,))
        _r3.button("🗑️", key=f"entro_sacar_{pid}", on_click=_sacar, args=(pid,),
                   help="Sacarlo de la lista.")
    if contando:
        _c_b1, _c_b2 = st.columns([3, 1])
        if _c_b1.button("✅ Dejar el stock en lo contado", key="entro_contar", type="primary",
                        width="stretch"):
            try:
                diferencias, esperaban = dejar_el_stock_en_lo_contado(dict(lista))
            except PermissionError as _err:
                st.error(el_error_en_castellano(_err))
            else:
                for pid in list(lista):
                    st.session_state.pop(f"entro_cant_{pid}", None)
                contados = len(lista)
                lista.clear()
                avisar("success", f"✅ Contados {miles(contados)} producto(s)"
                       + (": " + ", ".join(f"{q} {'—' if a is None else miles(a)} → {miles(h)}"
                                           for q, a, h in diferencias[:10])
                          + (" …" if len(diferencias) > 10 else "")
                          if diferencias else ", todo coincidía."))
                if esperaban:
                    avisar("info", f"📲 {miles(len(esperaban))} cliente(s) esperaban algo que "
                                   f"ahora hay: avisales en {miga_hasta('Para pedir')} → "
                                   "«📞 Consultas de clientes».")
                st.rerun()
        _c_b2.button("Vaciar", key="entro_vaciar_conteo", width="stretch",
                     on_click=lambda: st.session_state.get("entro_lista", {}).clear())
        return
    _cuando = cuando_se_sumo_la_entrada(lista)
    _igual = True
    if _cuando:
        st.warning(f"⚠️ Esta misma entrada ya se sumó al stock el {_cuando}: si la sumás de "
                   "nuevo, queda el doble.")
        _igual = st.checkbox("Es otra entrada igual: sumarla igual", key="entro_igual")
    _b1, _b2 = st.columns([3, 1])
    if _b1.button("✅ Sumar al stock", key="entro_sumar", type="primary", width="stretch",
                  disabled=not _igual):
        try:
            sumados, esperaban, llegaron = sumar_al_stock(dict(lista))
        except PermissionError as _err:
            st.error(el_error_en_castellano(_err))
        else:
            for pid in list(lista):
                st.session_state.pop(f"entro_cant_{pid}", None)
            lista.clear()
            st.session_state.pop("entro_igual", None)
            avisar("success", f"✅ Sumado al stock: {miles(sumados)} producto(s).")
            if llegaron:
                avisar("info", "🚚 De lo pedido a los proveedores: " + "; ".join(llegaron[:4])
                       + (f" y {miles(len(llegaron) - 4)} más" if len(llegaron) > 4 else "")
                       + f". Lo que falta sigue en {miga_hasta('Para pedir')} → «🚚 Pedido y "
                         "sin llegar».")
            if esperaban:
                avisar("info", f"📲 {miles(len(esperaban))} cliente(s) esperaban algo de lo que "
                               f"entró: avisales en {miga_hasta('Para pedir')} → «📞 Consultas "
                               "de clientes».")
            st.rerun()
    _b2.button("Vaciar", key="entro_vaciar", width="stretch",
               on_click=lambda: st.session_state.get("entro_lista", {}).clear())


# ============================================================================================
# LOS PEDIDOS A LOS PROVEEDORES
# ============================================================================================
# El mensaje al proveedor se armaba en «📌 Para pedir», se mandaba por WhatsApp y no quedaba en
# ningún lado: a la semana nadie se acordaba si el filtro que faltaba se había pedido, y se
# pedía dos veces o ninguna. «📝 Anotar como pedido» lo deja anotado; cuando entra por «📦 Entró
# mercadería» se da por llegado solo (lo que llega en partes, cuando llegó todo), y lo que no
# llegó en DIAS_PARA_RECLAMAR_EL_PEDIDO sale en la campanita con el mensaje para reclamarlo.
DIAS_PARA_RECLAMAR_EL_PEDIDO = 5
# Sin tilde: el auditor controla que lo que se escribe y lo que se busca coincida, y solo mira
# letras sin tilde (un «llegó» se le escapaba).
ESTADOS_DEL_PEDIDO_AL_PROVEEDOR = ("pedido", "llego", "cancelado")


def anotar_el_pedido_al_proveedor(items):
    """`items`: [(producto_id, cantidad o None)]. Lo que ya estaba pedido y sin llegar no se
    anota otra vez; lo que un empleado había marcado con «📌 Pedir» sale de «🙋 Pedidos
    marcados» (ya está pedido). Devuelve (anotados, ya estaban pedidos)."""
    exigir_nivel("empleado", "anotar un pedido al proveedor")
    anotados = ya = 0
    with db_lock, transaccion():
        for pid, cantidad in items:
            pid = int(pid)
            if c.execute("SELECT 1 FROM pedidos_a_proveedores WHERE producto_id = ? "
                         "AND estado = 'pedido'", (pid,)).fetchone():
                ya += 1
                continue
            if not c.execute("SELECT 1 FROM productos WHERE id = ?", (pid,)).fetchone():
                continue
            cantidad = int(cantidad) if cantidad and int(cantidad) > 0 else None
            c.execute("INSERT INTO pedidos_a_proveedores (producto_id, cantidad, pedido_por) "
                      "VALUES (?, ?, ?)", (pid, cantidad, obtener_usuario_actual()))
            c.execute("UPDATE pedidos_reposicion SET estado = 'resuelto' "
                      "WHERE producto_id = ? AND estado = 'pendiente'", (pid,))
            anotar_cambio("pidió al proveedor", "producto", pid, despues=cantidad)
            anotados += 1
    return anotados, ya


def anotar_el_pedido_y_avisar(marca, items):
    """«📝 Anotar como pedido» (va como on_click)."""
    try:
        anotados, ya = anotar_el_pedido_al_proveedor(items)
    except PermissionError as _err:
        error = el_error_en_castellano(_err)
    else:
        error = ""
    if error:
        avisar("error", error)
        return
    if anotados:
        avisar("success", f"📝 Anotado: {miles(anotados)} producto(s) pedidos a {marca}. Cuando "
                          "entren por «📦 Entró mercadería» se dan por llegados solos.")
    if ya:
        avisar("info", f"{miles(ya)} ya estaba(n) pedido(s) y sin llegar: no se anotó otra vez.")


def lo_pedido_sin_llegar():
    """{producto_id: (cuándo se pidió, como está guardado)} de lo pedido y sin llegar, para
    marcarlo en las listas de «📌 Para pedir» y no pedirlo dos veces."""
    return {f["producto_id"]: f["pedido_en"] for f in c.execute(
        "SELECT producto_id, MIN(pedido_en) AS pedido_en FROM pedidos_a_proveedores "
        "WHERE estado = 'pedido' GROUP BY producto_id")}


def pedidos_sin_llegar():
    """[dict] con ID, ProductoID, Marca, Codigo, Descripcion, Cantidad, Llegaron, Pedido (como
    está guardado), Dias y Atrasado: lo pedido y sin llegar, lo más viejo primero."""
    salida = []
    for f in c.execute(
            """SELECT pp.id, pp.producto_id, m.nombre AS marca, p.codigo_raw, p.descripcion,
                      pp.cantidad, COALESCE(pp.llegaron, 0) AS llegaron, pp.pedido_en,
                      CAST(julianday('now') - julianday(pp.pedido_en) AS INTEGER) AS dias
               FROM pedidos_a_proveedores pp
               JOIN productos p ON p.id = pp.producto_id
               JOIN marcas m ON m.id = p.marca_id
               WHERE pp.estado = 'pedido'
               ORDER BY pp.pedido_en, m.nombre, p.codigo_raw""").fetchall():
        salida.append({"ID": f["id"], "ProductoID": f["producto_id"], "Marca": f["marca"],
                       "Codigo": f["codigo_raw"], "Descripcion": f["descripcion"],
                       "Cantidad": f["cantidad"], "Llegaron": f["llegaron"],
                       "Pedido": f["pedido_en"], "Dias": f["dias"] or 0,
                       "Atrasado": (f["dias"] or 0) >= DIAS_PARA_RECLAMAR_EL_PEDIDO})
    return salida


def dar_por_llegado_lo_que_entro(lista):
    """Lo que entró ({producto_id: cantidad}) se descuenta de lo pedido: lo que completa lo
    pedido (o lo pedido sin cantidad) queda «llego». Lo llama sumar_al_stock(), adentro de su
    transacción. Devuelve [«MARCA CÓDIGO» o «MARCA CÓDIGO (llegaron 2 de 5)»]."""
    salida = []
    for pid, cantidad in lista.items():
        cantidad = int(cantidad or 0)
        if cantidad <= 0:
            continue
        for f in c.execute(
                """SELECT pp.id, pp.cantidad, COALESCE(pp.llegaron, 0) AS llegaron,
                          m.nombre AS marca, p.codigo_raw FROM pedidos_a_proveedores pp
                   JOIN productos p ON p.id = pp.producto_id
                   JOIN marcas m ON m.id = p.marca_id
                   WHERE pp.producto_id = ? AND pp.estado = 'pedido' ORDER BY pp.pedido_en""",
                (int(pid),)).fetchall():
            if cantidad <= 0:
                break
            llegaron = f["llegaron"] + cantidad
            completo = not f["cantidad"] or llegaron >= f["cantidad"]
            cantidad = llegaron - f["cantidad"] if f["cantidad"] and completo else 0
            c.execute("UPDATE pedidos_a_proveedores SET llegaron = ?, estado = ?, "
                      "llego_en = CASE WHEN ? THEN datetime('now') ELSE llego_en END "
                      "WHERE id = ?", (min(llegaron, f["cantidad"] or llegaron),
                                       "llego" if completo else "pedido", completo, f["id"]))
            salida.append(f"{f['marca']} {f['codigo_raw']}" + (
                "" if completo else f" (llegaron {miles(llegaron)} de {miles(f['cantidad'])})"))
    return salida


def cerrar_el_pedido_al_proveedor(pedido_id, llego=True):
    """«✅» (llegó, sin cargar el stock: para eso, «📦 Entró mercadería») o «🗑️» (no va a
    venir). Va como on_click."""
    exigir_nivel("empleado", "cerrar un pedido al proveedor")
    with db_lock, transaccion():
        c.execute("UPDATE pedidos_a_proveedores SET estado = ?, "
                  "llego_en = CASE WHEN ? THEN datetime('now') ELSE llego_en END "
                  "WHERE id = ? AND estado = 'pedido'",
                  ("llego" if llego else "cancelado", bool(llego), int(pedido_id)))


# CUÁNTO TARDA CADA PROVEEDOR, con lo que ya se anota: entre que se pidió y que llegó, en los
# últimos DIAS_DE_CUANTO_TARDA. Para saber a quién pedirle lo urgente y cuándo reclamar.
DIAS_DE_CUANTO_TARDA = 180


def cuanto_tarda_cada_proveedor():
    """[dict] por marca: Marca, Llegaron (productos), Tarda (días, en promedio), «El más lento»
    (días), «Sin llegar» y Cancelados. El que más tarda, primero."""
    filas = c.execute(
        """SELECT m.nombre AS marca,
                  SUM(pp.estado = 'llego') AS llegaron,
                  AVG(CASE WHEN pp.estado = 'llego'
                           THEN julianday(pp.llego_en) - julianday(pp.pedido_en) END) AS tarda,
                  MAX(CASE WHEN pp.estado = 'llego'
                           THEN julianday(pp.llego_en) - julianday(pp.pedido_en) END) AS lento,
                  SUM(pp.estado = 'pedido') AS sin_llegar,
                  SUM(pp.estado = 'cancelado') AS cancelados
           FROM pedidos_a_proveedores pp
           JOIN productos p ON p.id = pp.producto_id
           JOIN marcas m ON m.id = p.marca_id
           WHERE pp.pedido_en >= datetime('now', ?)
           GROUP BY m.nombre HAVING SUM(pp.estado = 'llego') > 0
           ORDER BY tarda DESC, m.nombre""", (f"-{DIAS_DE_CUANTO_TARDA} days",)).fetchall()
    return [{"Marca": f["marca"], "Llegaron": f["llegaron"],
             "Tarda (días)": round(f["tarda"], 1), "El más lento (días)": round(f["lento"], 1),
             "Sin llegar": f["sin_llegar"], "Cancelados": f["cancelados"]} for f in filas]


def mensaje_para_reclamar_el_pedido(pedidos):
    """El mensaje al proveedor por lo que no llegó (los de una marca)."""
    lineas = ["Hola! Todavía no me llegó esto que te pedí:"]
    for p in pedidos:
        falta = (p["Cantidad"] - p["Llegaron"]) if p["Cantidad"] else None
        lineas.append(f"- {p['Codigo']} ({p['Descripcion'] or ''})"
                      + (f" — faltan {falta}" if falta else "")
                      + f" — pedido el {dia_y_mes_de_aca(p['Pedido'])}")
    lineas.append("¿Me decís cuándo llega? Gracias.")
    return "\n".join(lineas)

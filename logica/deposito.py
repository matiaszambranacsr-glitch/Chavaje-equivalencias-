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
        pedido = _pendiente_de_la_cuenta(mecanico_id, config["descuento"])
        if config["limite"] and estado["saldo"] + pedido + importe > config["limite"] + 0.005:
            return False, (f"Pasa el límite de crédito de la cuenta: debe "
                           f"{formato_precio(estado['saldo'])}"
                           + (f", tiene pedido sin entregar {formato_precio(pedido)}"
                              if pedido else "")
                           + f" y el límite es {formato_precio(config['limite'])}.")
    with db_lock, transaccion():
        if (mecanico_id and not retiro_autorizado
                and configuracion_de_cuenta(mecanico_id)["pide_codigo"]):
            codigo_id = _codigo_de_retiro_vigente(mecanico_id, codigo_de_retiro)
            if not codigo_id:
                return False, ("El código de retiro no es válido, ya se usó o venció. El taller "
                               "genera uno nuevo en su portal.")
            c.execute("UPDATE codigos_de_retiro SET usado_en = datetime('now', 'localtime') "
                      "WHERE id = ?", (codigo_id,))
        c.execute("""INSERT INTO pedidos_deposito (producto_id, cantidad, mecanico_id, nota,
                                                   pedido_por, tanda)
                     VALUES (?, ?, ?, ?, ?, ?)""",
                  (producto_id, cantidad, mecanico_id or None, (nota or "").strip()[:200],
                   usuario or obtener_usuario_actual(), tanda))
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


def pedir_lo_elegido_al_deposito(items, usuario="", nota=""):
    """[(producto_id, cantidad)] → pide cada uno para la cuenta elegida (o Mostrador).
    Devuelve (los que se pidieron, [por qué no, de los otros])."""
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
            pedidos, fallas = pedir_lo_elegido_al_deposito([(producto_id, cantidad)], nota=nota)
            if pedidos:
                st.success("📦 Pedido al depósito. Lo ven en «📦 Depósito».")
            for falla in fallas:
                st.error(falla)
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
    pedidos, fallas = pedir_lo_elegido_al_deposito([(producto_id, item["cantidad"])])
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
    else:
        carrito[fila["ID"]] = {"codigo": fila["Codigo"], "marca": fila["Marca"],
                               "descripcion": fila.get("Descripcion") or "",
                               "precio": fila.get("Precio") or 0, "cantidad": int(cantidad)}

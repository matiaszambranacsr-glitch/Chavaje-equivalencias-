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
    # LAS SEÑAS (ver esa sección): entran el día que se dejan, por donde se pagaron, y la que se
    # devuelve sale el día que se devuelve. La venta en la que se descontó cuenta sin esa parte,
    # que ya había entrado: si no, la seña se contaba dos veces.
    senas_cobradas, senas_devueltas = senas_del_dia(dia)

    def agrupar(campo, vacio, campo_devolucion):
        grupos = {}
        for v in validas:
            g = grupos.setdefault(v[campo] or vacio, [0, 0.0])
            g[0] += 1
            g[1] += (v["total"] or 0) - (v.get("sena") or 0)
        for d in devueltas:
            grupos.setdefault(d[campo_devolucion] or vacio, [0, 0.0])[1] -= d["importe"]
        for s in senas_cobradas:
            grupos.setdefault(s[campo] or vacio, [0, 0.0])[1] += s["importe"]
        for s in senas_devueltas:
            grupos.setdefault(s[campo] or vacio, [0, 0.0])[1] -= s["importe"]
        return sorted(((k, n, round(t, 2)) for k, (n, t) in grupos.items()),
                      key=lambda x: -x[2])
    anuladas = [v for v in ventas if v["anulada"]]
    # LA GANANCIA, con el costo que tenía cada cosa al venderla, y solo de lo que tiene costo
    # cargado: cuántos lo tienen va al lado, para no leer «ganancia del día» donde es una parte.
    items = [it for v in validas for it in v["items"]]
    con_costo = [it for it in items if it.get("costo") is not None]
    total_devuelto = round(sum(d["importe"] for d in devueltas), 2)
    total_senas = round(sum(s["importe"] for s in senas_cobradas), 2)
    total_senas_devueltas = round(sum(s["importe"] for s in senas_devueltas), 2)
    senas_descontadas = round(sum(v.get("sena") or 0 for v in validas), 2)
    return {"ventas": len(validas),
            "total": round(sum(v["total"] or 0 for v in validas) - senas_descontadas
                           - total_devuelto + total_senas - total_senas_devueltas, 2),
            "senas": len(senas_cobradas), "total_senas": total_senas,
            "senas_devueltas": len(senas_devueltas),
            "total_senas_devueltas": total_senas_devueltas,
            "senas_descontadas": senas_descontadas,
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


# EL RESUMEN DEL DÍA PARA EL DUEÑO. El cierre se ve en la pantalla, pero el dueño no siempre
# está en el negocio a la hora de cerrar: preguntaba por WhatsApp «¿cómo vino el día?» y alguien
# tenía que leerle los números. Va escrito, al WhatsApp del dueño (anotado una vez, ver
# whatsapp_del_duenio()), con lo que importa al cerrar: lo vendido por forma de pago, lo
# devuelto, lo que quedó en la caja sin cobrar, lo vencido de las cuentas y lo fallado por
# reclamar. La ganancia, solo si lo arma un administrador (la ve solo él).
CLAVE_DEL_WHATSAPP_DEL_DUENIO = "whatsapp_del_duenio"


def whatsapp_del_duenio():
    return obtener_config(CLAVE_DEL_WHATSAPP_DEL_DUENIO, "") or ""


def guardar_whatsapp_del_duenio(telefono):
    """Lo cambia el administrador: es adónde van los números del negocio."""
    exigir_nivel("admin", "cambiar el WhatsApp del dueño")
    nuevo = str(telefono or "").strip()[:40]
    if nuevo != whatsapp_del_duenio():
        guardar_config(CLAVE_DEL_WHATSAPP_DEL_DUENIO, nuevo)
        anotar_cambio("cambió el WhatsApp del dueño", "configuración", "whatsapp_del_duenio",
                      despues=nuevo)


def resumen_del_dia(dia=None, con_ganancia=False):
    """El texto del resumen de `dia` (hoy, si no se dice), listo para WhatsApp."""
    caja = cierre_de_caja(dia)
    fecha = date.fromisoformat(dia) if dia else hoy_aca()
    plata = lambda x: f"${miles(x, 0)}"
    renglones = [f"📊 Resumen del {fecha:%d/%m} — El Chavo",
                 f"💵 Vendido: {plata(caja['total'])} en {miles(caja['ventas'])} venta(s)"]
    renglones += [f"   · {forma}: {plata(total)}" for forma, _n, total in caja["por_forma"]]
    if con_ganancia and caja["items_con_costo"]:
        renglones.append(f"💰 Ganancia estimada: {plata(caja['ganancia'])}"
                         + (f" (de {miles(caja['items_con_costo'])} de {miles(caja['items'])} "
                            "cosas, las que tienen costo)"
                            if caja["items_con_costo"] < caja["items"] else ""))
    if caja["devoluciones"]:
        renglones.append(f"↩️ Devuelto: {plata(caja['total_devuelto'])} "
                         f"({miles(caja['devoluciones'])})")
    if caja["senas"] or caja["senas_devueltas"] or caja["senas_descontadas"]:
        renglones.append("🔖 Señas: " + " · ".join(x for x in (
            f"entraron {plata(caja['total_senas'])} ({miles(caja['senas'])})"
            if caja["senas"] else "",
            f"devueltas {plata(caja['total_senas_devueltas'])}" if caja["senas_devueltas"] else "",
            f"descontadas al retirar {plata(caja['senas_descontadas'])}"
            if caja["senas_descontadas"] else "") if x))
    _salidas = [s for s in salidas_de_caja(dia) if not s["anulada"]]
    if _salidas:
        renglones.append(f"💸 Salidas de caja: {plata(sum(s['importe'] for s in _salidas))} "
                         f"({miles(len(_salidas))})")
        renglones.append(f"🧮 En el cajón tendría que haber: {plata(efectivo_esperado(dia))}")
    if caja["a_cobrar"]:
        renglones.append(f"⏳ Quedó en la caja sin cobrar: {plata(caja['total_a_cobrar'])} "
                         f"({miles(caja['a_cobrar'])})")
    if caja["anuladas"]:
        renglones.append(f"🚫 Anuladas: {miles(caja['anuladas'])} "
                         f"({plata(caja['total_anulado'])}, no cuentan)")
    # El objetivo del mes, al día del resumen (ver «EL OBJETIVO DEL MES»).
    try:
        _avance = avance_del_objetivo(fecha.strftime("%Y-%m"), hoy=fecha)
        if _avance:
            renglones.append(renglon_del_objetivo(_avance))
    except Exception as _err:
        anotar_error("resumen_del_dia: objetivo", _err)
    if len(caja["por_usuario"]) > 1:
        renglones.append("👤 " + " · ".join(f"{u}: {plata(t)}" for u, _n, t in caja["por_usuario"]))
    _turnos = renglon_de_los_turnos(dia)
    if _turnos:
        renglones.append(f"🔄 Turnos (arqueos): {_turnos}")
    # Lo que está esperando, no solo de hoy: es lo que el dueño tiene que saber al cerrar.
    try:
        vencidas = cuentas_para_recordar()
        if vencidas:
            renglones.append(f"💳 Cuentas con vencido: {plata(sum(r['Vencido'] for r in vencidas))} "
                             f"en {miles(len(vencidas))}")
        por_reclamar = [g for g in garantias() if not g["reclamo"]]
        if por_reclamar:
            renglones.append(f"🔧 Garantías por reclamar al proveedor: {miles(len(por_reclamar))}")
        # LO QUE VENCE: los cheques que ya se pueden depositar y, al administrador, lo que hay
        # que pagarles a los proveedores (ver «LOS CHEQUES PARA DEPOSITAR» y «LO QUE SE LE DEBE
        # A CADA PROVEEDOR»).
        cheques = [x for x in cheques_sin_depositar() if x["se_puede"]]
        if cheques:
            renglones.append(f"🏦 Cheques para depositar: {miles(len(cheques))} "
                             f"({plata(sum(x['importe'] for x in cheques))})")
        if con_ganancia:
            a_pagar = facturas_para_avisar()
            if a_pagar:
                vencido = sum(k["vencido"] for k in a_pagar)
                renglones.append("🧾 Proveedores para pagar: " + ", ".join(
                    k["proveedor"] for k in a_pagar[:3]) + (" …" if len(a_pagar) > 3 else "")
                    + (f" ({plata(vencido)} vencidos)" if vencido else
                       f" (vence en {DIAS_PARA_AVISAR_UNA_FACTURA} días o menos)"))
    except Exception as _err:          # el resumen sale igual, sin eso
        anotar_error("resumen_del_dia", _err)
    return "\n".join(renglones)


# EL RESUMEN DE LA SEMANA: lo del día dice cómo cerró la caja; para decidir qué comprar hace
# falta la semana. Lo vendido contra la semana anterior, lo que más salió, y sobre todo LO QUE
# MÁS PIDEN Y NO SE TIENE: lo buscado sin resultado (en el Buscador y en los pedidos del chat) y
# los clientes que esperan algo. Eso estaba repartido en tres pantallas y nadie lo juntaba.
DIAS_DE_LA_SEMANA_DEL_RESUMEN = 7


def resumen_de_la_semana(hasta=None, con_ganancia=False):
    """El texto del resumen de los 7 días que terminan en `hasta` (hoy, si no se dice), con la
    semana anterior al lado, listo para WhatsApp."""
    fin = date.fromisoformat(hasta) if hasta else hoy_aca()
    plata = lambda x: f"${miles(x, 0)}"

    def la_semana(ultimo):
        total = ganancia = 0.0
        ventas = 0
        vendidos = {}
        for i in range(DIAS_DE_LA_SEMANA_DEL_RESUMEN):
            dia = (ultimo - timedelta(days=i)).isoformat()
            caja = cierre_de_caja(dia)
            total += caja["total"]
            ganancia += caja["ganancia"]
            ventas += caja["ventas"]
            for v in ventas_del_dia(dia):
                if v["anulada"] or not v["cobrada"]:
                    continue
                for it in v["items"]:
                    clave = f"{it.get('marca') or ''} {it.get('codigo') or ''}".strip()
                    vendidos[clave] = vendidos.get(clave, 0) + int(it.get("cantidad") or 0)
        return total, ganancia, ventas, vendidos

    total, ganancia, ventas, vendidos = la_semana(fin)
    total_antes = la_semana(fin - timedelta(days=DIAS_DE_LA_SEMANA_DEL_RESUMEN))[0]
    desde = fin - timedelta(days=DIAS_DE_LA_SEMANA_DEL_RESUMEN - 1)
    renglones = [f"📊 Semana del {desde:%d/%m} al {fin:%d/%m} — El Chavo",
                 f"💵 Vendido: {plata(total)} en {miles(ventas)} venta(s)"]
    if total_antes:
        cambio = round((total / total_antes - 1) * 100)
        renglones.append(f"   {'📈' if cambio >= 0 else '📉'} {'+' if cambio >= 0 else ''}"
                         f"{cambio}% contra la semana anterior ({plata(total_antes)})")
    if con_ganancia and ganancia:
        renglones.append(f"💰 Ganancia estimada: {plata(ganancia)} (de lo que tiene costo)")
    # Lo que salió del cajón en la semana, por tipo (ver «LAS SALIDAS DE CAJA»).
    _por_tipo = c.execute(
        "SELECT tipo, SUM(importe) AS total FROM salidas_de_caja WHERE anulada = 0 "
        "AND dia BETWEEN ? AND ? GROUP BY tipo ORDER BY total DESC",
        (desde.isoformat(), fin.isoformat())).fetchall()
    if _por_tipo:
        renglones.append("💸 Salidas de caja: " + ", ".join(
            f"{f['tipo']} {plata(f['total'])}" for f in _por_tipo))
    mas_vendidos = sorted(vendidos.items(), key=lambda x: -x[1])[:5]
    if mas_vendidos:
        renglones.append("🏆 Lo que más salió: " + ", ".join(f"{q} ×{miles(n)}"
                                                           for q, n in mas_vendidos))
    try:
        sin_resultado = c.execute(
            """SELECT termino, COUNT(*) AS veces FROM historial_busquedas
               WHERE sin_resultado = 1 AND fecha >= datetime('now', ?)
               GROUP BY lower(termino) ORDER BY veces DESC, termino LIMIT 5""",
            (f"-{DIAS_DE_LA_SEMANA_DEL_RESUMEN} days",)).fetchall()
        if sin_resultado:
            renglones.append("🔎 Lo que más pidieron y no había: "
                             + ", ".join(f"{f['termino']}"
                                         + (f" ×{miles(f['veces'])}" if f["veces"] > 1 else "")
                                         for f in sin_resultado))
        esperan = c.execute("SELECT COUNT(*) FROM consultas_cliente "
                            "WHERE estado = 'activa'").fetchone()[0]
        if esperan:
            renglones.append(f"📞 Clientes esperando algo: {miles(esperan)}")
        presus = presupuestos_para_seguir()
        if presus:
            contestaron = sum(1 for p in presus if p["contesto"])
            renglones.append(f"📋 Presupuestos para seguir: {miles(len(presus))}"
                             + (f" ({miles(contestaron)} te contestaron)" if contestaron
                                else ""))
        vencidas = cuentas_para_recordar()
        if vencidas:
            renglones.append(f"💳 Cuentas con vencido: {plata(sum(r['Vencido'] for r in vencidas))} "
                             f"en {miles(len(vencidas))}")
    except Exception as _err:          # el resumen sale igual, sin eso
        anotar_error("resumen_de_la_semana", _err)
    return "\n".join(renglones)


def cerrar_venta(items, cliente="", forma_de_pago="", usuario=None, mecanico_id=None,
                 a_la_caja=False, telefono="", senas=()):
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
    sena_ids = sorted({int(s) for s in senas or ()})
    if sena_ids and forma_de_pago == A_CUENTA:
        raise ValueError("La seña se descuenta en una venta que se cobra, no en una a cuenta.")
    with db_lock, transaccion():
        total = round(sum(x[1] * x[2] for x in limpios), 2)
        # LA SEÑA que ya dejó (ver «LAS SEÑAS»): solo las que siguen esperando, y no más que la
        # venta. Dos vendedores con la misma seña en pantalla no la descuentan dos veces.
        sena = 0.0
        if sena_ids:
            filas_sena = c.execute(
                f"SELECT id, importe FROM senas WHERE estado = 'activa' AND id IN "
                f"({','.join('?' * len(sena_ids))})", sena_ids).fetchall()
            if len(filas_sena) != len(sena_ids):
                raise ValueError("Una de las señas ya no está esperando (¿la descontó otro o se "
                                 "devolvió?).")
            sena = round(sum(float(f["importe"]) for f in filas_sena), 2)
            if sena > total:
                raise ValueError(f"La seña (${miles(sena, 0)}) es más que la venta "
                                 f"(${miles(total, 0)}): sumá lo que se lleva, o devolvé la "
                                 "diferencia desde la caja.")
        c.execute("""INSERT INTO ventas (usuario, cliente, forma_de_pago, total, cobrada,
                                         mecanico_id, total_de_lista, cliente_telefono, sena)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (usuario, (cliente or "").strip(), "" if a_la_caja else (forma_de_pago or ""),
                   total, 0 if a_la_caja else 1, mecanico_id or None, total,
                   str(telefono or "").strip()[:40] or None, sena))
        venta_id = c.lastrowid
        if sena_ids:
            marcadores = ",".join("?" * len(sena_ids))
            c.execute(f"""UPDATE consultas_cliente SET estado = 'vendida',
                                 fecha_cierre = datetime('now')
                          WHERE estado = 'activa' AND id IN
                              (SELECT consulta_id FROM senas WHERE id IN ({marcadores}))""",
                      sena_ids)
            c.execute(f"""UPDATE senas SET estado = 'usada', venta_id = ?,
                                 resuelta_en = datetime('now'), resuelta_por = ?
                          WHERE id IN ({marcadores})""", [venta_id, usuario] + sena_ids)
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
                                                   stock_descontado, costo, precio_de_lista)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (venta_id, producto_id, f["codigo_raw"], f["marca"], f["descripcion"],
                       cantidad, precio, pedido, descontado, f["precio_costo"], precio))
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
    # Con factura electrónica, primero la nota de crédito: si no, ARCA sigue teniendo una venta
    # que en la caja ya no está (ver «LA FACTURA ELECTRÓNICA (ARCA)» en logica/facturas.py).
    if factura_vigente_de(venta_id):
        return False, (f"La venta #{venta_id} tiene factura electrónica: primero anulala con la "
                       "nota de crédito (en el cierre de caja).")
    return _anular_la_venta(venta_id)


def _anular_la_venta(venta_id):
    """El cuerpo de anular_venta(), sin mirar el permiso: lo usa también deshacer_mi_venta(),
    que mira el suyo."""
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
        # La seña que se había descontado vuelve a esperar: el cliente la dejó igual (ver «LAS
        # SEÑAS»), y lo que encargó también.
        c.execute("""UPDATE consultas_cliente SET estado = 'activa', fecha_cierre = NULL
                     WHERE estado = 'vendida' AND id IN
                         (SELECT consulta_id FROM senas WHERE venta_id = ? AND estado = 'usada')""",
                  (venta_id,))
        c.execute("""UPDATE senas SET estado = 'activa', venta_id = NULL, resuelta_en = NULL,
                            resuelta_por = NULL
                     WHERE venta_id = ? AND estado = 'usada'""", (venta_id,))
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
    dia = dia or hoy_aca().isoformat()
    # El día de la caja es el día en que se cobró (la plata entra ese día); lo que espera en la
    # caja, el día en que se vendió.
    c.execute("""SELECT v.id, substr(datetime(v.fecha, '-3 hours'), 12, 5) AS hora,
                        v.usuario, v.cliente,
                        v.forma_de_pago, v.total, v.anulada, v.km, ve.patente,
                        COALESCE(v.cobrada, 1) AS cobrada, v.cuotas,
                        COALESCE(v.descuento, 0) AS descuento, v.cobrada_por,
                        k.nombre AS cuenta, COALESCE(v.sena, 0) AS sena
                 FROM ventas v LEFT JOIN vehiculos ve ON ve.id = v.vehiculo_id
                 LEFT JOIN mecanicos k ON k.id = v.mecanico_id
                 WHERE date(COALESCE(v.cobrada_en, v.fecha), '-3 hours') = ?
                 ORDER BY v.id DESC""", (dia,))
    ventas = [dict(f) for f in c.fetchall()]
    for v in ventas:
        c.execute("""SELECT id, codigo, marca, descripcion, cantidad, precio, costo,
                            COALESCE(devuelto, 0) AS devuelto
                     FROM ventas_items WHERE venta_id = ? ORDER BY id""", (v["id"],))
        v["items"] = [dict(f) for f in c.fetchall()]
    return ventas


# EL MES POR VENDEDOR: el cierre dice quién vendió cuánto en un día; para las comisiones, o para
# ver quién atiende más, hacía falta sumar día por día. Por quien armó la venta (no quien la
# cobró), sin lo anulado y con lo devuelto descontado a quien la había vendido. Solo para el
# administrador (ver pantallas/caja.py).
def ventas_por_vendedor(desde, hasta):
    """[dict] entre dos días de acá («2026-11-01», inclusive): Vendedor, Ventas, Vendido (sin lo
    anulado, menos lo devuelto), Devuelto y «Ticket promedio». El que más vendió primero."""
    filas = c.execute(
        """SELECT COALESCE(NULLIF(v.usuario, ''), 'Sin decir') AS quien, COUNT(*) AS ventas,
                  SUM(v.total) AS total
           FROM ventas v
           WHERE v.anulada = 0 AND date(v.fecha, '-3 hours') BETWEEN ? AND ?
           GROUP BY quien""", (desde, hasta)).fetchall()
    devuelto = {f["quien"]: f["importe"] for f in c.execute(
        """SELECT COALESCE(NULLIF(v.usuario, ''), 'Sin decir') AS quien,
                  SUM(d.importe) AS importe
           FROM ventas_devoluciones d JOIN ventas v ON v.id = d.venta_id
           WHERE v.anulada = 0 AND date(d.fecha, '-3 hours') BETWEEN ? AND ?
           GROUP BY quien""", (desde, hasta))}
    salida = []
    for f in filas:
        dev = round(float(devuelto.get(f["quien"]) or 0), 2)
        vendido = round(float(f["total"] or 0) - dev, 2)
        salida.append({"Vendedor": f["quien"], "Ventas": f["ventas"], "Vendido": vendido,
                       "Devuelto": dev,
                       "Ticket promedio": round(float(f["total"] or 0) / f["ventas"], 2)
                       if f["ventas"] else 0.0})
    salida.sort(key=lambda x: -x["Vendido"])
    return salida


# Y LOS MESES ANTERIORES, con la comisión: se elige el mes (los últimos MESES_PARA_COMISIONES)
# en vez de tener que elegir su último día, y con el porcentaje de comisión anotado una vez
# (COMISION_MAXIMA como tope: más es un número mal escrito) sale cuánto le toca a cada uno.
NOMBRES_DE_LOS_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                        "agosto", "septiembre", "octubre", "noviembre", "diciembre")
MESES_PARA_COMISIONES = 12
COMISION_MAXIMA = 50


def meses_para_elegir(cuantos=MESES_PARA_COMISIONES, hoy=None):
    """[«2026-11», «2026-10», …]: este mes y los anteriores, el más nuevo primero."""
    hoy = hoy or hoy_aca()
    anio, mes, salida = hoy.year, hoy.month, []
    for _ in range(int(cuantos)):
        salida.append(f"{anio:04d}-{mes:02d}")
        anio, mes = (anio, mes - 1) if mes > 1 else (anio - 1, 12)
    return salida


def nombre_del_mes(mes):
    """«2026-11» → «noviembre 2026»."""
    anio, numero = (int(x) for x in str(mes).split("-")[:2])
    return f"{NOMBRES_DE_LOS_MESES[numero - 1]} {anio}"


def rango_del_mes(mes, hoy=None):
    """(desde, hasta) de un mes, en días de acá: el de este mes llega hasta hoy."""
    hoy = hoy or hoy_aca()
    anio, numero = (int(x) for x in str(mes).split("-")[:2])
    desde = date(anio, numero, 1)
    siguiente = date(anio + (numero == 12), numero % 12 + 1, 1)
    hasta = min(siguiente - timedelta(days=1), hoy)
    return desde.isoformat(), hasta.isoformat()


def comision_por_ciento():
    try:
        return max(0.0, min(float(obtener_config("comision_por_ciento", "0") or 0),
                            COMISION_MAXIMA))
    except ValueError:
        return 0.0


def guardar_comision_por_ciento(valor):
    """La anota el administrador; queda en el registro de cambios."""
    exigir_nivel("admin", "cambiar el porcentaje de comisión")
    nuevo = round(float(valor or 0), 2)
    if not 0 <= nuevo <= COMISION_MAXIMA:
        raise ValueError(f"La comisión tiene que ser entre 0 y {COMISION_MAXIMA}%.")
    antes = comision_por_ciento()
    if nuevo != antes:
        guardar_config("comision_por_ciento", str(nuevo))
        anotar_cambio("cambió el porcentaje de comisión", "configuración",
                      "comision_por_ciento", antes=antes, despues=nuevo)


# LA COMISIÓN DE CADA UNO: el que recién empieza y el encargado no siempre cobran lo mismo. Se
# anota la propia de un vendedor; el que no tiene, cobra la general.
def comisiones_propias():
    """{vendedor: porcentaje} de los que tienen una propia."""
    try:
        datos = json.loads(obtener_config("comisiones_por_vendedor", "") or "{}")
    except ValueError:
        return {}
    return {str(k): float(v) for k, v in (datos or {}).items()
            if isinstance(v, (int, float)) and 0 <= v <= COMISION_MAXIMA}


def comision_de(vendedor):
    """El porcentaje de ese vendedor: el propio, o el general."""
    return comisiones_propias().get(str(vendedor), comision_por_ciento())


def guardar_comision_de(vendedor, valor):
    """La propia de un vendedor; None la saca (vuelve a la general). La anota el administrador."""
    exigir_nivel("admin", "cambiar la comisión de un vendedor")
    vendedor = str(vendedor or "").strip()
    if not vendedor:
        raise ValueError("Elegí el vendedor.")
    propias = comisiones_propias()
    antes = propias.get(vendedor)
    if valor is None:
        propias.pop(vendedor, None)
    else:
        nuevo = round(float(valor), 2)
        if not 0 <= nuevo <= COMISION_MAXIMA:
            raise ValueError(f"La comisión tiene que ser entre 0 y {COMISION_MAXIMA}%.")
        propias[vendedor] = nuevo
    if propias.get(vendedor) != antes:
        guardar_config("comisiones_por_vendedor", json.dumps(propias, sort_keys=True))
        anotar_cambio("cambió la comisión de un vendedor", "configuración", vendedor,
                      antes=antes, despues=propias.get(vendedor))


def comisiones_del_mes(mes, hoy=None):
    """ventas_por_vendedor() del mes, con «%» (el de cada uno), «Comisión» (lo vendido por ese
    porcentaje) y «Mes anterior» (lo que vendió cada uno el mes de antes, entero)."""
    desde, hasta = rango_del_mes(mes, hoy)
    anterior_hasta = date.fromisoformat(desde) - timedelta(days=1)
    anterior = {x["Vendedor"]: x["Vendido"] for x in ventas_por_vendedor(
        anterior_hasta.replace(day=1).isoformat(), anterior_hasta.isoformat())}
    propias, general = comisiones_propias(), comision_por_ciento()
    salida = []
    for x in ventas_por_vendedor(desde, hasta):
        por_ciento = propias.get(x["Vendedor"], general)
        salida.append({**x, "%": por_ciento,
                       "Comisión": round(x["Vendido"] * por_ciento / 100, 2),
                       "Mes anterior": anterior.get(x["Vendedor"], 0.0)})
    return salida


def guardar_comision_y_avisar(vendedor, clave_del_campo, a_la_general=False):
    """«💾 Guardar» y «Usar la general» de la comisión propia (van como on_click)."""
    try:
        guardar_comision_de(vendedor, None if a_la_general
                            else st.session_state.get(clave_del_campo))
    except (PermissionError, ValueError) as _err:
        error = el_error_en_castellano(_err)
    else:
        error = ""
    if error:
        avisar("error", error)
    else:
        avisar("success", f"💰 {vendedor}: comisión de {como_porcentaje(comision_de(vendedor))}%"
                          + (" (la general)." if vendedor not in comisiones_propias() else "."))


# LA LIQUIDACIÓN DE UN VENDEDOR: lo del mes con cada venta, para dársela o mandársela y que
# pueda controlar de dónde sale el número (antes era un total dicho de palabra).
def ventas_del_vendedor(desde, hasta, vendedor):
    """Las ventas no anuladas de ese vendedor entre dos días de acá, la más vieja primero:
    [dict] con id, dia, cliente, total y devuelto."""
    return [dict(f) for f in c.execute(
        """SELECT v.id, date(v.fecha, '-3 hours') AS dia,
                  COALESCE(NULLIF(v.cliente, ''), k.nombre, '') AS cliente, v.total,
                  COALESCE((SELECT SUM(d.importe) FROM ventas_devoluciones d
                            WHERE d.venta_id = v.id
                              AND date(d.fecha, '-3 hours') BETWEEN ? AND ?), 0) AS devuelto
           FROM ventas v LEFT JOIN mecanicos k ON k.id = v.mecanico_id
           WHERE v.anulada = 0 AND COALESCE(NULLIF(v.usuario, ''), 'Sin decir') = ?
             AND date(v.fecha, '-3 hours') BETWEEN ? AND ?
           ORDER BY v.id""", (desde, hasta, str(vendedor), desde, hasta))]


def liquidacion_del_vendedor(mes, vendedor, hoy=None):
    """El texto de la liquidación del mes de un vendedor, para WhatsApp. "" si no vendió."""
    fila = next((x for x in comisiones_del_mes(mes, hoy) if x["Vendedor"] == vendedor), None)
    if not fila:
        return ""
    plata = lambda x: f"${miles(x, 0)}"
    renglones = [f"🏆 Liquidación de {nombre_del_mes(mes)} — {vendedor}",
                 f"🧾 Ventas: {miles(fila['Ventas'])} por {plata(fila['Vendido'] + fila['Devuelto'])}"]
    if fila["Devuelto"]:
        renglones.append(f"↩️ Devuelto: {plata(fila['Devuelto'])}")
    renglones.append(f"💵 Vendido: {plata(fila['Vendido'])}")
    if fila["%"]:
        renglones.append(f"💰 Comisión ({como_porcentaje(fila['%'])}%): {plata(fila['Comisión'])}")
    return "\n".join(renglones)


def liquidacion_para_descargar(mes, vendedor, hoy=None):
    """Para el botón de descarga: los datos se leen ahora y el PDF se arma al tocarlo, en otro
    hilo que no toca la base (ver comprobante_para_descargar())."""
    fila = next((x for x in comisiones_del_mes(mes, hoy) if x["Vendedor"] == vendedor), None)
    desde, hasta = rango_del_mes(mes, hoy)
    ventas = ventas_del_vendedor(desde, hasta, vendedor) if fila else []
    return lambda: pdf_de_la_liquidacion(mes, vendedor, fila, ventas, desde, hasta)


def pdf_de_la_liquidacion(mes, vendedor, fila, ventas, desde, hasta):
    """La liquidación del mes de un vendedor en PDF, con cada venta (los datos, ya leídos: ver
    liquidacion_para_descargar()). b"" si no vendió."""
    from fpdf import FPDF
    if not fila:
        return b""

    def limpiar(texto):
        return str(texto).encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 10, limpiar(f"El Chavo - Liquidación de {nombre_del_mes(mes)}"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, limpiar(f"Vendedor: {vendedor}   Del {desde[8:10]}/{desde[5:7]} al "
                           f"{hasta[8:10]}/{hasta[5:7]}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 10)
    for texto, ancho in (("Día", 22), ("Venta", 22), ("Cliente", 86), ("Total", 30),
                         ("Devuelto", 30)):
        pdf.cell(ancho, 7, texto, border="B", align="L" if texto in ("Día", "Venta", "Cliente")
                 else "R")
    pdf.ln()
    pdf.set_font("Helvetica", "", 10)
    for v in ventas:
        pdf.cell(22, 6, limpiar(f"{v['dia'][8:10]}/{v['dia'][5:7]}"))
        pdf.cell(22, 6, f"#{v['id']}")
        pdf.cell(86, 6, limpiar(str(v["cliente"] or "")[:42]))
        pdf.cell(30, 6, limpiar(f"${miles(v['total'] or 0, 0)}"), align="R")
        pdf.cell(30, 6, limpiar(f"${miles(v['devuelto'], 0)}" if v["devuelto"] else ""),
                 align="R")
        pdf.ln()
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    for texto, valor in (("Vendido (sin lo anulado y con lo devuelto descontado)",
                          fila["Vendido"]),) + (
            ((f"Comisión ({como_porcentaje(fila['%'])}%)", fila["Comisión"]),)
            if fila["%"] else ()):
        pdf.cell(150, 8, limpiar(texto), border="T")
        pdf.cell(40, 8, limpiar(f"${miles(valor, 0)}"), border="T", align="R")
        pdf.ln()
    return bytes(pdf.output())


def devoluciones_del_dia(dia=None):
    """Lo que se devolvió en un día (hoy, si no se dice), de ventas no anuladas: con la forma de
    pago de la venta (la plata vuelve por donde entró) y el precio y el costo del ítem. [dict]."""
    dia = dia or hoy_aca().isoformat()
    c.execute("""SELECT d.id, d.venta_id, d.cantidad, d.importe, d.motivo, d.usuario,
                        substr(datetime(d.fecha, '-3 hours'), 12, 5) AS hora, v.forma_de_pago,
                        vi.marca, vi.codigo,
                        vi.precio, vi.costo
                 FROM ventas_devoluciones d JOIN ventas v ON v.id = d.venta_id
                 JOIN ventas_items vi ON vi.id = d.venta_item_id
                 WHERE date(d.fecha, '-3 hours') = ? AND v.anulada = 0 ORDER BY d.id""", (dia,))
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
                        k.nombre AS cuenta, COALESCE(v.sena, 0) AS sena,
                        COALESCE(v.recargo, 0) AS recargo
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
    lineas = [f"Tu compra en El Chavo — #{venta['id']} — {fecha_legible(venta['fecha'][:16])}"]
    lineas += [f"{it['cantidad']}× {it['marca']} {it['codigo']} — "
               f"{(it['descripcion'] or '')[:40]} — ${miles(it['cantidad'] * it['precio'], 0)}"
               + (f" (devueltos: {it['devuelto']})" if it["devuelto"] else "")
               for it in venta["items"]]
    if venta["descuento"]:
        lineas.append(f"Descuento {como_porcentaje(venta['descuento'])}% (era "
                      f"${miles(venta['total_de_lista'] or 0, 0)})")
    if venta.get("recargo"):
        lineas.append(f"Recargo {como_porcentaje(venta['recargo'])}% por {venta['cuotas']} cuotas "
                      "(incluido en los precios)")
    lineas.append(f"TOTAL: ${miles(venta['total'] or 0, 0)}"
                  + (f" ({como_se_pago(venta)})" if venta["forma_de_pago"] else ""))
    if venta.get("sena"):
        lineas.append(f"Seña que ya dejaste: -${miles(venta['sena'], 0)} · A PAGAR: "
                      f"${miles((venta['total'] or 0) - venta['sena'], 0)}")
    if not venta["cobrada"] and not venta["anulada"]:
        lineas.append("PENDIENTE DE COBRO")
    if venta["anulada"]:
        lineas.append("ANULADA")
    lineas += ["", "¡Gracias por tu compra!", NO_ES_FACTURA]
    return "\n".join(lineas)


# EL TICKET DE 80 MM. El comprobante y la factura salían solo en hoja A4, y un mostrador con
# ticketera térmica imprimía una hoja entera —o nada— por cada venta. El dueño dejó la decisión
# en manos de la app («hacé todas las decisiones mías»): van los dos papeles, se elige una vez
# en 🗂️ Administrar → 💬 Mensajería y cobros, y los mismos botones de siempre bajan el PDF en
# ese papel. El ticket mide de alto lo que mide lo impreso: la ticketera corta donde termina
# la página, y una hoja con medio metro en blanco es medio metro de rollo tirado.
PAPELES_DEL_COMPROBANTE = ("Hoja A4", "Ticket de 80 mm")
ANCHO_DEL_TICKET, MARGEN_DEL_TICKET = 80, 4      # en mm: quedan 72 de ancho para imprimir
LADO_DEL_QR_EN_EL_TICKET = 34


def papel_del_comprobante():
    """En qué papel salen el comprobante y la factura: uno de PAPELES_DEL_COMPROBANTE."""
    papel = obtener_config("papel_del_comprobante", PAPELES_DEL_COMPROBANTE[0])
    return papel if papel in PAPELES_DEL_COMPROBANTE else PAPELES_DEL_COMPROBANTE[0]


def guardar_papel_del_comprobante(papel):
    """Lo elige cualquier empleado: es cómo imprime su mostrador, no un dato del negocio."""
    if papel not in PAPELES_DEL_COMPROBANTE:
        raise ValueError("Ese papel no existe: " + " o ".join(PAPELES_DEL_COMPROBANTE) + ".")
    exigir_nivel("empleado", "cambiar el papel de los comprobantes")
    guardar_config("papel_del_comprobante", papel)
    conn.commit()


def elegir_papel_del_comprobante(clave):
    """Lo que pasa al tocar el selector del papel (va como on_change): guarda lo elegido y lo
    dice. Como aviso al tocar, y no comparando lo que muestra el selector con lo guardado en
    cada pasada: Streamlit conserva lo que mostraba un campo aunque otro haya cambiado el valor
    en la base, y la pantalla abierta de uno le pisaba sin querer lo que había elegido el otro."""
    try:
        guardar_papel_del_comprobante(st.session_state.get(clave))
        aviso = ("success", "🖨️ Listo: el comprobante y la factura salen en "
                            f"«{papel_del_comprobante()}».")
    except (PermissionError, ValueError) as _err:
        aviso = ("error", el_error_en_castellano(_err))
    avisar(*aviso)


def pdf_de_ticket(partes):
    """Un PDF de 80 mm de ancho y del alto justo, para ticketera. `partes`, de arriba a abajo:
        ("centro", texto, tamaño, negrita)     centrado, en los renglones que haga falta
        ("texto", texto, tamaño, negrita)      a la izquierda, lo mismo
        ("par", izquierda, derecha, tamaño, negrita)   un texto y su importe a la derecha
        ("linea",)                             una raya de puntos
        ("espacio", mm)
        ("qr", lo que lleva adentro)           el QR, centrado
    Se dibuja dos veces: la primera, en una página larguísima, para saber cuánto mide."""
    from fpdf import FPDF

    def latin(texto):
        # Las fuentes básicas de fpdf2 no traen todo unicode: ver generar_pdf_cotizacion().
        return str(texto or "").replace("×", "x").encode("latin-1", "replace").decode("latin-1")

    ancho = ANCHO_DEL_TICKET - 2 * MARGEN_DEL_TICKET

    def dibujar(alto):
        pdf = FPDF(unit="mm", format=(ANCHO_DEL_TICKET, alto))
        pdf.set_auto_page_break(False)
        pdf.set_margins(MARGEN_DEL_TICKET, MARGEN_DEL_TICKET, MARGEN_DEL_TICKET)
        pdf.add_page()
        for parte in partes:
            que = parte[0]
            if que == "linea":
                y = pdf.get_y() + 1.2
                pdf.set_dash_pattern(dash=1, gap=1)
                pdf.line(MARGEN_DEL_TICKET, y, ANCHO_DEL_TICKET - MARGEN_DEL_TICKET, y)
                pdf.set_dash_pattern()
                pdf.set_y(y + 1.2)
            elif que == "espacio":
                pdf.set_y(pdf.get_y() + parte[1])
            elif que == "qr":
                import qrcode
                imagen = io.BytesIO()
                qrcode.make(parte[1]).save(imagen, format="PNG")
                imagen.seek(0)
                y = pdf.get_y() + 1
                pdf.image(imagen, x=(ANCHO_DEL_TICKET - LADO_DEL_QR_EN_EL_TICKET) / 2, y=y,
                          w=LADO_DEL_QR_EN_EL_TICKET)
                pdf.set_y(y + LADO_DEL_QR_EN_EL_TICKET + 1.5)
            elif que == "par":
                _que, izquierda, derecha, puntos, negrita = parte
                pdf.set_font("Helvetica", "B" if negrita else "", puntos)
                renglon = puntos * 0.42
                ancho_del_importe = pdf.get_string_width(latin(derecha)) + 1.5
                y = pdf.get_y()
                pdf.multi_cell(ancho - ancho_del_importe - 1, renglon, latin(izquierda),
                               align="L", new_x="LMARGIN", new_y="NEXT")
                y_al_terminar = max(pdf.get_y(), y + renglon)
                pdf.set_xy(MARGEN_DEL_TICKET + ancho - ancho_del_importe, y)
                pdf.cell(ancho_del_importe, renglon, latin(derecha), align="R")
                pdf.set_xy(MARGEN_DEL_TICKET, y_al_terminar)
            else:
                _que, texto, puntos, negrita = parte
                pdf.set_font("Helvetica", "B" if negrita else "", puntos)
                pdf.multi_cell(ancho, puntos * 0.42, latin(texto),
                               align="C" if que == "centro" else "L",
                               new_x="LMARGIN", new_y="NEXT")
        return pdf

    alto = dibujar(3000).get_y() + MARGEN_DEL_TICKET
    return bytes(dibujar(alto).output())


def ticket_del_comprobante(venta):
    """El comprobante de una venta ya leída (ver una_venta()), en ticket de 80 mm. Dice lo
    mismo que pdf_del_comprobante(). b"" si no hay venta."""
    if not venta:
        return b""
    _fecha = a_la_hora_de_aca(venta["fecha"]) or datetime.strptime(venta["fecha"][:16],
                                                                   "%Y-%m-%d %H:%M")
    partes = [("centro", "EL CHAVO", 13, True),
              ("centro", f"Comprobante de venta #{venta['id']}", 9, False),
              ("centro", f"{_fecha:%d/%m/%Y %H:%M}", 9, False)]
    if venta["cliente"]:
        partes.append(("texto", f"Cliente: {venta['cliente']}", 9, False))
    if venta["patente"]:
        partes.append(("texto", f"Patente: {venta['patente']}", 9, False))
    partes.append(("linea",))
    for it in venta["items"]:
        partes.append(("texto", f"{it['cantidad']} x {it['marca']} {it['codigo']}", 9, True))
        partes.append(("par", (it["descripcion"] or "")[:70]
                       + (f" (devueltos: {it['devuelto']})" if it["devuelto"] else ""),
                       f"${miles(it['cantidad'] * it['precio'], 0)}", 9, False))
    partes.append(("linea",))
    if venta.get("descuento"):
        partes.append(("texto", f"Descuento {como_porcentaje(venta['descuento'])}% (era "
                                f"${miles(venta.get('total_de_lista') or 0, 0)})", 9, False))
    if venta.get("recargo"):
        partes.append(("texto", f"Recargo {como_porcentaje(venta['recargo'])}% por "
                                f"{venta['cuotas']} cuotas (incluido en los precios)", 9, False))
    partes.append(("par", "TOTAL" + (f" ({como_se_pago(venta)})" if venta["forma_de_pago"]
                                      else ""), f"${miles(venta['total'] or 0, 0)}", 12, True))
    if venta.get("sena"):
        partes.append(("par", "Seña que ya dejó", f"-${miles(venta['sena'], 0)}", 9, False))
        partes.append(("par", "A PAGAR", f"${miles((venta['total'] or 0) - venta['sena'], 0)}",
                       12, True))
    if not venta.get("cobrada", 1) and not venta["anulada"]:
        partes.append(("centro", "PENDIENTE DE COBRO", 10, True))
    if venta["anulada"]:
        partes.append(("centro", "ANULADA", 10, True))
    partes += [("espacio", 2), ("centro", NO_ES_FACTURA, 8, False),
               ("centro", "¡Gracias por tu compra!", 9, False)]
    return pdf_de_ticket(partes)


def comprobante_para_descargar(venta_id):
    """Para el botón de descarga: los datos de la venta y el papel se leen ahora, y el PDF se
    arma recién al tocar el botón (Streamlit lo corre en otro hilo, que no tiene que tocar la
    base). Así no se arma un PDF en cada toque de la pantalla, y si armarlo fallara, no se cae
    Ventas. En hoja A4 o en ticket de 80 mm: ver papel_del_comprobante()."""
    venta = una_venta(venta_id)
    en_ticket = papel_del_comprobante() == PAPELES_DEL_COMPROBANTE[1]
    return lambda: ticket_del_comprobante(venta) if en_ticket else pdf_del_comprobante(venta)


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
    _fecha = a_la_hora_de_aca(venta["fecha"]) or datetime.strptime(venta["fecha"][:16],
                                                                   "%Y-%m-%d %H:%M")
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
    if venta.get("recargo"):
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(140, 7, limpiar(f"Recargo {como_porcentaje(venta['recargo'])}% por "
                                 f"{venta['cuotas']} cuotas (incluido en los precios)"))
        pdf.ln()
        pdf.set_font("Helvetica", "B", 12)
    pdf.cell(140, 9, limpiar("TOTAL" + (f" ({como_se_pago(venta)})"
                                         if venta["forma_de_pago"] else "")), border="T")
    pdf.cell(40, 9, limpiar(f"${miles(venta['total'] or 0, 0)}"), border="T", align="R")
    if venta.get("sena"):
        pdf.ln()
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(140, 7, limpiar("Seña que ya dejó"))
        pdf.cell(40, 7, limpiar(f"-${miles(venta['sena'], 0)}"), align="R")
        pdf.ln()
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(140, 9, "A PAGAR")
        pdf.cell(40, 9, limpiar(f"${miles((venta['total'] or 0) - venta['sena'], 0)}"),
                 align="R")
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
    hoy = hoy_aca()
    desde = hoy - timedelta(days=int(dias) - 1)
    c.execute("""SELECT date(fecha, '-3 hours') AS dia, COUNT(*) AS ventas, SUM(total) AS total
                 FROM ventas WHERE anulada = 0 AND date(fecha, '-3 hours') >= ?
                 GROUP BY dia""", (desde.isoformat(),))
    del_dia = {f["dia"]: [f["ventas"], f["total"] or 0] for f in c.fetchall()}
    # Lo devuelto, el día que se devolvió: ver cierre_de_caja().
    c.execute("""SELECT date(d.fecha, '-3 hours') AS dia, SUM(d.importe) AS importe
                 FROM ventas_devoluciones d JOIN ventas v ON v.id = d.venta_id
                 WHERE v.anulada = 0 AND date(d.fecha, '-3 hours') >= ? GROUP BY dia""",
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
                 WHERE v.anulada = 0 AND date(v.fecha, '-3 hours') >= ?
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


# Cuántas de las últimas de hoy se ofrecen a un toque en ↩️ Devoluciones → «De un cliente».
CUANTAS_VENTAS_DE_HOY = 5


def buscar_ventas(texto, dias=180, tope=20):
    """Las ventas no anuladas de los últimos `dias` días que coinciden con `texto`: el número
    («#12» o «12»), el cliente, la patente o el teléfono del auto. La última primero, con sus
    ítems. [dict]."""
    t = (texto or "").strip()
    if not t:
        return []
    desde = (hoy_aca() - timedelta(days=int(dias))).isoformat()
    numero = t.lstrip("#").strip()
    digitos = re.sub(r"\D", "", t)
    c.execute("""SELECT v.id FROM ventas v LEFT JOIN vehiculos ve ON ve.id = v.vehiculo_id
                 WHERE v.anulada = 0 AND date(v.fecha, '-3 hours') >= ?
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
                     if bajados else "")
                  # Que se sepa que queda para reclamar: si no, nadie entra a buscarlo.
                  + (". Queda para reclamárselo al proveedor en ↩️ Devoluciones → 🔧 Garantías"
                     if motivo in MOTIVOS_PARA_RECLAMAR else "") + ".")


# EL OBJETIVO DEL MES: el dueño sabía cuánto quería vender en el mes, pero nadie sabía cómo
# venía hasta sumar el cierre de cada día a fin de mes, cuando ya no había nada que hacer. Lo
# pone el administrador (queda hasta que lo cambie: el del mes que no tiene se arrastra del
# anterior), y la caja muestra la barra con lo vendido —como en «🏆 Ventas y comisiones por
# vendedor»: sin lo anulado y con lo devuelto descontado— y cuánto hay que vender por día abierto
# para llegar. Los días abiertos salen del horario de atención (el de la respuesta fuera de
# horario); sin horario, de lunes a sábado. Los feriados no los sabe.
OBJETIVO_MAXIMO = 1e11                       # más es un número mal escrito
DIAS_QUE_SE_ABRE_SIN_HORARIO = (0, 1, 2, 3, 4, 5)


def objetivos_de_ventas():
    """{«2026-11»: importe} como los dejó el administrador (0 = sin objetivo desde ese mes)."""
    try:
        datos = json.loads(obtener_config("objetivos_de_ventas", "") or "{}")
    except ValueError:
        return {}
    return {str(k): float(v) for k, v in (datos or {}).items()
            if re.fullmatch(r"\d{4}-\d{2}", str(k)) and isinstance(v, (int, float))
            and 0 <= v <= OBJETIVO_MAXIMO}


def objetivo_del_mes(mes=None):
    """El objetivo de ese mes (este, si no se dice): el anotado, o el del último mes anterior que
    tenga. None si no hay (o lo sacaron)."""
    mes = mes or hoy_aca().strftime("%Y-%m")
    anteriores = [k for k in objetivos_de_ventas() if k <= mes]
    if not anteriores:
        return None
    valor = objetivos_de_ventas()[max(anteriores)]
    return valor or None


def guardar_objetivo_del_mes(importe, mes=None):
    """(ok, texto). Lo pone el administrador; 0 o vacío lo saca. Queda en el registro."""
    exigir_nivel("admin", "cambiar el objetivo de ventas")
    mes = mes or hoy_aca().strftime("%Y-%m")
    try:
        nuevo = round(float(importe or 0), 0)
    except (TypeError, ValueError):
        return False, "Escribí cuánto querés vender en el mes."
    if nuevo < 0 or not nuevo <= OBJETIVO_MAXIMO:    # también el «nan»
        return False, "Revisá el número del objetivo."
    antes = objetivo_del_mes(mes)
    objetivos = objetivos_de_ventas()
    objetivos[mes] = nuevo
    guardar_config("objetivos_de_ventas", json.dumps(objetivos, sort_keys=True))
    anotar_cambio("cambió el objetivo de ventas", "configuración", mes, antes=antes,
                  despues=nuevo or None)
    return True, (f"🎯 Objetivo de {nombre_del_mes(mes)}: ${miles(nuevo, 0)}." if nuevo
                  else "🎯 Sin objetivo de ventas.")


def guardar_objetivo_y_avisar(clave_del_campo):
    """«💾 Guardar» del objetivo del mes (va como on_click)."""
    try:
        ok, texto = guardar_objetivo_del_mes(st.session_state.get(clave_del_campo))
    except PermissionError as _err:
        ok, texto = False, el_error_en_castellano(_err)
    avisar("success" if ok else "warning", texto)


def dias_que_se_abre():
    """Los días de la semana (lunes = 0) que abre el local, según el horario de atención."""
    dias = set()
    for d1, d2, _desde, _hasta in tramos_del_horario(respuesta_fuera_de_horario()["horario"]):
        dias.update(range(d1, d2 + 1) if d1 <= d2 else [*range(d1, 7), *range(0, d2 + 1)])
    return tuple(sorted(dias)) or DIAS_QUE_SE_ABRE_SIN_HORARIO


def avance_del_objetivo(mes=None, hoy=None):
    """None sin objetivo; si no, {objetivo, vendido, por_ciento, falta, quedan (días abiertos
    que quedan, con hoy), por_dia (lo que falta repartido en esos días), esperado (lo que a esta
    altura tendría que estar vendido, a ritmo parejo hasta ayer) y cumplido}."""
    hoy = hoy or hoy_aca()
    mes = mes or hoy.strftime("%Y-%m")
    objetivo = objetivo_del_mes(mes)
    if not objetivo:
        return None
    desde, hasta = rango_del_mes(mes, hoy)
    vendido = round(sum(x["Vendido"] for x in ventas_por_vendedor(desde, hasta)), 2)
    abre = set(dias_que_se_abre())
    primero = date.fromisoformat(desde)
    ultimo = date(primero.year + (primero.month == 12), primero.month % 12 + 1, 1) \
        - timedelta(days=1)
    dias_del_mes = [primero + timedelta(days=i) for i in range((ultimo - primero).days + 1)]
    abiertos = [d for d in dias_del_mes if d.weekday() in abre] or dias_del_mes
    pasados = sum(1 for d in abiertos if d < hoy)
    quedan = len(abiertos) - pasados
    falta = max(0.0, round(objetivo - vendido, 2))
    return {"objetivo": objetivo, "vendido": vendido,
            "por_ciento": round(vendido * 100 / objetivo, 1),
            "falta": falta, "quedan": quedan,
            "por_dia": round(falta / quedan, 0) if quedan else falta,
            "esperado": round(objetivo * pasados / len(abiertos), 0),
            "cumplido": vendido >= objetivo}


def renglon_del_objetivo(avance, con_plata=True):
    """El renglón de la barra (y del resumen del día): cuánto va, y cuánto por día para llegar.
    Sin `con_plata` (el empleado), solo el porcentaje y los días."""
    if not avance:
        return ""
    plata = lambda x: f"${miles(x, 0)}"
    if avance["cumplido"]:
        return ("🎉 ¡Objetivo del mes cumplido! " + (f"{plata(avance['vendido'])} de "
                f"{plata(avance['objetivo'])} " if con_plata else "")
                + f"({miles(avance['por_ciento'], 0)}%)")
    texto = f"🎯 Objetivo del mes: {miles(avance['por_ciento'], 0)}%"
    if con_plata:
        texto += f" ({plata(avance['vendido'])} de {plata(avance['objetivo'])})"
    if avance["quedan"]:
        texto += (f" · quedan {avance['quedan']} día(s) abierto(s)"
                  + (f": {plata(avance['por_dia'])} por día para llegar" if con_plata else ""))
    if avance["esperado"]:
        texto += (" · vamos adelantados" if avance["vendido"] >= avance["esperado"]
                  else " · vamos atrasados")
    return texto


# EL CAMBIO DE APERTURA Y LOS BILLETES. El arqueo pide el efectivo «sin el cambio con el que
# se abrió»: la cajera contaba todo el cajón y restaba de memoria, y el cambio no quedaba en
# ningún lado. Ahora el cambio de apertura se anota (uno por día), y en «💵 Contar los billetes»
# se carga cuántos hay de cada uno: la app suma, resta el cambio y pasa el número al arqueo, con
# el detalle de billetes en la nota.
DENOMINACIONES_DE_BILLETES = (20000, 10000, 2000, 1000, 500, 200, 100, 50, 20, 10)


def cambio_de_apertura(dia=None):
    """Con cuánto cambio se abrió la caja ese día (hoy, si no se dice), o None."""
    fila = c.execute("SELECT importe FROM aperturas_de_caja WHERE dia = ?",
                     (dia or hoy_aca().isoformat(),)).fetchone()
    return float(fila["importe"]) if fila else None


def anotar_cambio_de_apertura(importe, dia=None):
    """(ok, texto). Uno por día: anotarlo otra vez lo corrige (queda en el registro)."""
    exigir_nivel("empleado", "anotar el cambio de apertura")
    try:
        importe = round(float(importe), 2)
    except (TypeError, ValueError):
        return False, "Escribí con cuánto cambio se abrió."
    if importe < 0:
        return False, "El cambio no puede ser negativo."
    if not importe <= SALIDA_DE_CAJA_MAXIMA:  # también el «nan» que deja pasar float()
        return False, f"¿${miles(importe, 0)} de cambio? Revisá el número."
    dia = dia or hoy_aca().isoformat()
    antes = cambio_de_apertura(dia)
    with db_lock, transaccion():
        c.execute("INSERT INTO aperturas_de_caja (dia, importe, usuario) VALUES (?, ?, ?) "
                  "ON CONFLICT(dia) DO UPDATE SET importe = excluded.importe, "
                  "usuario = excluded.usuario, fecha = datetime('now')",
                  (dia, importe, obtener_usuario_actual()))
        anotar_cambio("cambio de apertura", "caja", dia, antes=antes, despues=importe)
    return True, f"🪙 Cambio de apertura: ${miles(importe, 0)}."


def total_de_billetes(conteo, monedas=0):
    """{denominación: cuántos} y las monedas en pesos → el total."""
    return round(sum(int(d) * max(0, int(n or 0)) for d, n in (conteo or {}).items())
                 + max(0.0, float(monedas or 0)), 2)


def detalle_de_billetes(conteo, monedas=0):
    """«3 × $20.000 · 2 × $1.000 · monedas $350», para la nota del arqueo."""
    partes = [f"{int(n)} × ${miles(int(d))}" for d, n in sorted(
        (conteo or {}).items(), key=lambda x: -int(x[0])) if int(n or 0) > 0]
    if float(monedas or 0) > 0:
        partes.append(f"monedas ${miles(float(monedas), 0)}")
    return " · ".join(partes)


def ultimo_cambio_de_apertura(antes_de=None):
    """(día, importe) del último cambio anotado antes de ese día (hoy, si no se dice), o None.
    El cambio suele ser siempre el mismo: la caja lo ofrece con un toque."""
    fila = c.execute("SELECT dia, importe FROM aperturas_de_caja WHERE dia < ? "
                     "ORDER BY dia DESC LIMIT 1",
                     (antes_de or hoy_aca().isoformat(),)).fetchone()
    return (fila["dia"], float(fila["importe"])) if fila else None


def anotar_el_mismo_cambio_y_avisar(importe, dia):
    """«🪙 El mismo que el …» (va como on_click)."""
    try:
        ok, texto = anotar_cambio_de_apertura(importe, dia)
    except PermissionError as _err:
        ok, texto = False, el_error_en_castellano(_err)
    avisar("success" if ok else "warning", texto)


def anotar_cambio_de_apertura_y_avisar(clave_del_campo, dia):
    """«💾 Anotar» del cambio de apertura (va como on_click)."""
    try:
        ok, texto = anotar_cambio_de_apertura(st.session_state.get(clave_del_campo), dia)
    except PermissionError as _err:
        ok, texto = False, el_error_en_castellano(_err)
    avisar("success" if ok else "warning", texto)


def pasar_los_billetes_al_arqueo(dia):
    """«Pasar al arqueo» (va como on_click): el total de los billetes contados, menos el cambio
    de apertura, va a «Efectivo contado», y el detalle a la nota."""
    conteo = {d: st.session_state.get(f"billete_{d}") or 0 for d in DENOMINACIONES_DE_BILLETES}
    monedas = st.session_state.get("billete_monedas") or 0
    total = total_de_billetes(conteo, monedas)
    cambio = cambio_de_apertura(dia) or 0.0
    st.session_state["arqueo_contado"] = max(0.0, round(total - cambio, 2))
    st.session_state["arqueo_nota"] = (detalle_de_billetes(conteo, monedas)
                                       + (f" (menos ${miles(cambio, 0)} de cambio)"
                                          if cambio else ""))[:200]


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
    dia = dia or hoy_aca().isoformat()
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
    menos lo devuelto de ventas en efectivo y menos lo que salió (ver «LAS SALIDAS DE CAJA»).
    Sin el cambio con el que se abrió."""
    cobrado = next((t for f, _, t in cierre_de_caja(dia)["por_forma"] if f == "Efectivo"), 0.0)
    return round(cobrado - total_de_salidas(dia), 2)


def resumen_de_la_caja(dia=None):
    """Lo de arriba de 💵 Caja, del día (hoy, si no se dice): lo que tiene que haber en el
    cajón, lo que entró por tarjeta o transferencia, lo puesto a cuenta (no es plata que entró)
    y lo que espera para cobrarse. dict."""
    caja = cierre_de_caja(dia)
    por_forma = {f: t for f, _, t in caja["por_forma"]}
    efectivo = por_forma.pop("Efectivo", 0.0)
    a_cuenta = por_forma.pop(A_CUENTA, 0.0)
    salidas = total_de_salidas(dia)
    # «efectivo» es lo que entró en efectivo; «en_el_cajon», lo que tiene que haber: menos lo
    # que salió (ver «LAS SALIDAS DE CAJA»).
    return {"efectivo": round(efectivo, 2), "otros_medios": round(sum(por_forma.values()), 2),
            "salidas": salidas, "en_el_cajon": round(efectivo - salidas, 2),
            "a_cuenta": round(a_cuenta, 2), "ventas": caja["ventas"],
            "esperando": caja["a_cobrar"], "total_esperando": caja["total_a_cobrar"]}


# LOS TURNOS DE CAJA: cuando la cajera de la mañana le deja la caja a la de la tarde, el arqueo
# de la noche daba la diferencia de todo el día, y un faltante de la mañana caía en la de la
# tarde. Ahora cada arqueo cierra el turno de quien lo hace: la diferencia de SU turno es lo que
# cambió desde el arqueo anterior del día (si la de la mañana dejó $100 de menos y a la noche
# faltan $100, la de la tarde no perdió nada). Si la misma persona vuelve a contar, los suyos se
# compensan. La plata que se saca entre turnos va como salida de caja (un retiro): así no cuenta
# como faltante.
# A quien le falta plata en VECES_CON_FALTANTE_PARA_AVISAR días del mes o más, la campanita se
# lo dice al administrador: una vez es un vuelto mal dado; seguido, hay que mirarlo.
VECES_CON_FALTANTE_PARA_AVISAR = 3


def cajeros_con_faltantes_seguidos(hoy=None):
    """Los de arqueos_por_cajero() del mes con faltante en VECES_CON_FALTANTE_PARA_AVISAR días
    o más."""
    hoy = hoy or hoy_aca()
    return [k for k in arqueos_por_cajero(hoy.replace(day=1).isoformat(), hoy.isoformat())
            if k["Con faltante"] >= VECES_CON_FALTANTE_PARA_AVISAR]


def turnos_del_dia(dia=None):
    """Los arqueos del día en orden, cada uno con «del_turno»: su diferencia menos la del arqueo
    anterior (lo que pasó en ese turno). [dict]."""
    turnos, anterior = [], 0.0
    for a in reversed(arqueos_del_dia(dia)):
        dif = round(float(a["diferencia"] or 0), 2)
        turnos.append({**a, "del_turno": round(dif - anterior, 2)})
        anterior = dif
    return turnos


def renglon_de_los_turnos(dia=None):
    """«ana: faltaron $100 · beto: sobraron $100», por quien contó (sumando sus turnos), si
    contaron dos o más. "" si no."""
    por_quien = {}
    for t in turnos_del_dia(dia):
        quien = t["usuario"] or "Sin decir"
        por_quien[quien] = round(por_quien.get(quien, 0.0) + t["del_turno"], 2)
    if len(por_quien) < 2:
        return ""
    return " · ".join(f"{q}: " + ("justo" if not d else
                                  f"{'sobraron' if d > 0 else 'faltaron'} ${miles(abs(d), 0)}")
                      for q, d in por_quien.items())


def arqueos_del_dia(dia=None):
    """Los arqueos de un día, el último primero. [dict]."""
    dia = dia or hoy_aca().isoformat()
    c.execute("""SELECT substr(datetime(fecha, '-3 hours'), 12, 5) AS hora, efectivo_esperado,
                        efectivo_contado,
                        efectivo_contado - efectivo_esperado AS diferencia, nota, usuario
                 FROM arqueos_de_caja WHERE dia = ? ORDER BY id DESC""", (dia,))
    return [dict(f) for f in c.fetchall()]


def lo_que_se_va_a_terminar(dias=30, alcanza_menos_de=7):
    """Lo que se vende y se va a terminar: con lo vendido en los últimos `dias` días (sin lo
    devuelto) y el stock de hoy, para cuántos días alcanza. Solo lo que alcanza para menos de
    `alcanza_menos_de` días, lo que se termina antes primero. [dict]."""
    desde = (hoy_aca() - timedelta(days=int(dias) - 1)).isoformat()
    c.execute("""SELECT vi.producto_id, MAX(vi.marca) AS marca, MAX(vi.codigo) AS codigo,
                        SUM(vi.cantidad - COALESCE(vi.devuelto, 0)) AS unidades, p.stock,
                        p.descripcion,
                        EXISTS (SELECT 1 FROM pedidos_reposicion pr
                                WHERE pr.producto_id = vi.producto_id
                                  AND pr.estado = 'pendiente') AS anotado
                 FROM ventas_items vi JOIN ventas v ON v.id = vi.venta_id
                 JOIN productos p ON p.id = vi.producto_id
                 WHERE v.anulada = 0 AND date(v.fecha, '-3 hours') >= ? AND p.stock IS NOT NULL
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
# LAS SALIDAS DE CAJA
# ============================================================================================
# Lo que tenía que haber en el cajón era «lo cobrado en efectivo menos lo devuelto», y no había
# cómo anotar la plata que sale: el flete que se paga al cadete, el proveedor que cobra contra
# entrega, el retiro del dueño a la tarde. Cada salida hacía que el arqueo dijera «Faltan $X»,
# y la diferencia de verdad (un vuelto mal dado) se perdía entre las que no lo eran. Ahora se
# anota con qué fue y quién, y el cajón y el arqueo la descuentan. Anularla: el administrador,
# o quien la anotó en sus primeros MINUTOS_PARA_DESHACER_LA_PROPIA (un número mal tipeado).
TIPOS_DE_SALIDA_DE_CAJA = ("🧾 Gasto", "🚚 Pago a un proveedor", "🏦 Retiro")
SALIDA_DE_CAJA_MAXIMA = 50_000_000      # más que esto es un número mal escrito


def anotar_salida_de_caja(tipo, concepto, importe, dia=None):
    """(ok, texto). `dia`: el de la caja (hoy, si no se dice)."""
    exigir_nivel("empleado", "anotar una salida de caja")
    concepto = " ".join(str(concepto or "").split())[:120]
    try:
        importe = round(float(importe), 2)
    except (TypeError, ValueError):
        return False, "Escribí cuánto salió."
    if tipo not in TIPOS_DE_SALIDA_DE_CAJA:
        return False, "Elegí qué fue: un gasto, un pago a un proveedor o un retiro."
    if not concepto:
        return False, "Escribí en qué se fue (ej.: flete del cadete)."
    if not 0 < importe <= SALIDA_DE_CAJA_MAXIMA:
        return False, "El importe tiene que ser más que cero."
    dia = dia or hoy_aca().isoformat()
    with db_lock, transaccion():
        c.execute("INSERT INTO salidas_de_caja (dia, tipo, concepto, importe, usuario) "
                  "VALUES (?, ?, ?, ?, ?)", (dia, tipo, concepto, importe,
                                              obtener_usuario_actual()))
        anotar_cambio("salida de caja", "caja", c.lastrowid, despues=importe,
                      detalle=f"{tipo}: {concepto}")
    queda = efectivo_esperado(dia)
    return True, (f"💸 Anotado: {tipo} de ${miles(importe, 0)} ({concepto}). En el cajón tendría "
                  f"que haber ${miles(queda, 0)}"
                  + (" (¿se abrió con cambio? lo cobrado en efectivo no alcanza)." if queda < 0
                     else "."))


def salidas_de_caja(dia=None):
    """Las salidas de un día (hoy, si no se dice), la última primero. [dict] con id, hora,
    tipo, concepto, importe, usuario, anulada, minutos (desde que se anotó)."""
    dia = dia or hoy_aca().isoformat()
    return [dict(f) for f in c.execute(
        """SELECT id, substr(datetime(fecha, '-3 hours'), 12, 5) AS hora, tipo, concepto,
                  importe, usuario, anulada,
                  CAST((julianday('now') - julianday(fecha)) * 1440 AS INTEGER) AS minutos
           FROM salidas_de_caja WHERE dia = ? ORDER BY id DESC""", (dia,))]


def total_de_salidas(dia=None):
    dia = dia or hoy_aca().isoformat()
    fila = c.execute("SELECT COALESCE(SUM(importe), 0) FROM salidas_de_caja "
                     "WHERE dia = ? AND anulada = 0", (dia,)).fetchone()
    return round(float(fila[0] or 0), 2)


def anular_salida_de_caja(salida_id):
    """(ok, texto): el administrador siempre; quien la anotó, en sus primeros minutos."""
    exigir_nivel("empleado", "anular una salida de caja")
    fila = c.execute("""SELECT usuario, anulada, importe, concepto,
                               (julianday('now') - julianday(fecha)) * 1440 AS minutos
                        FROM salidas_de_caja WHERE id = ?""", (int(salida_id),)).fetchone()
    if not fila or fila["anulada"]:
        return False, "Esa salida ya no está."
    if not es_admin() and (fila["usuario"] != obtener_usuario_actual()
                           or fila["minutos"] > MINUTOS_PARA_DESHACER_LA_PROPIA):
        return False, (f"Una salida la anula el administrador (o quien la anotó, en los primeros "
                       f"{MINUTOS_PARA_DESHACER_LA_PROPIA} minutos).")
    with db_lock, transaccion():
        c.execute("UPDATE salidas_de_caja SET anulada = 1, anulada_por = ? WHERE id = ?",
                  (obtener_usuario_actual(), int(salida_id)))
        anotar_cambio("anuló una salida de caja", "caja", salida_id, antes=fila["importe"],
                      detalle=fila["concepto"])
    return True, f"🚫 Anulada la salida de ${miles(fila['importe'], 0)} ({fila['concepto']})."


def anular_salida_y_avisar(salida_id):
    """El «🚫» de cada salida (va como on_click)."""
    try:
        ok, texto = anular_salida_de_caja(salida_id)
    except PermissionError as _err:
        ok, texto = False, el_error_en_castellano(_err)
    avisar("success" if ok else "warning", texto)


# ============================================================================================
# LAS GARANTÍAS: LO FALLADO, PARA RECLAMARLE AL PROVEEDOR
# ============================================================================================
# Lo que el cliente devuelve fallado (o dañado en el transporte) no vuelve al stock (ver
# NO_VUELVE_AL_STOCK), pero queda en el negocio y es plata: el proveedor lo cambia o lo
# acredita. Nadie le llevaba la cuenta, y lo que no se reclama a tiempo se pierde. Acá queda
# por marca, con el mensaje para el proveedor ya escrito (a su WhatsApp, ver
# whatsapp_del_proveedor()) y en qué quedó cada reclamo. «Hubo que modificarla» no entra: la
# pieza estaba bien.
MOTIVOS_PARA_RECLAMAR = frozenset({"fallada", "transporte"})
# Desde cuántos días sin reclamar lo dice la campanita: el proveedor no acepta cualquier fecha.
DIAS_PARA_AVISAR_UNA_GARANTIA = 14
ESTADOS_DEL_RECLAMO = {"": "⏳ Por reclamar", "reclamado": "📤 Reclamado",
                       "resuelto": "✅ Lo cambiaron o lo acreditaron",
                       "rechazado": "🚫 No lo reconocieron"}


def garantias(con_las_cerradas=False):
    """Lo devuelto por fallado o dañado, lo más viejo primero: [dict] con id, fecha (como está
    guardada), venta_id, marca, codigo, descripcion, cantidad, importe, motivo, detalle,
    reclamo ("" si falta reclamarlo), reclamo_en. Sin las cerradas (resueltas o rechazadas),
    salvo con_las_cerradas."""
    filtro = "" if con_las_cerradas else \
        " AND COALESCE(d.reclamo, '') NOT IN ('resuelto', 'rechazado')"
    c.execute(f"""SELECT d.id, d.fecha, d.venta_id, vi.marca, vi.codigo, vi.descripcion,
                         d.cantidad, d.importe, d.motivo, d.detalle,
                         COALESCE(d.reclamo, '') AS reclamo, d.reclamo_en
                  FROM ventas_devoluciones d JOIN ventas_items vi ON vi.id = d.venta_item_id
                  WHERE d.motivo IN ({','.join('?' * len(MOTIVOS_PARA_RECLAMAR))}){filtro}
                  ORDER BY d.fecha, d.id""", sorted(MOTIVOS_PARA_RECLAMAR))
    return [dict(f) for f in c.fetchall()]


def garantias_sin_reclamar_hace(dias=None):
    """Las que siguen por reclamar desde hace `dias` días o más (contados en la hora de acá;
    DIAS_PARA_AVISAR_UNA_GARANTIA si no se dice, que elige el administrador)."""
    dias = DIAS_PARA_AVISAR_UNA_GARANTIA if dias is None else dias
    salida = []
    for g in garantias():
        try:
            hace = (hoy_aca() - date.fromisoformat(dia_de_aca(g["fecha"]))).days
        except ValueError:
            continue
        if not g["reclamo"] and hace >= dias:
            salida.append(g)
    return salida


def mensaje_de_garantia(marca, filas):
    """El reclamo al proveedor, como lo escribiría el que atiende: qué volvió, cuándo se vendió
    y qué tenía."""
    renglones = [f"Hola! Te escribimos de El Chavo. Tenemos para devolverte en garantía estas "
                 f"piezas de {marca}:"]
    for f in filas:
        que = MOTIVOS_DE_DEVOLUCION.get(f["motivo"], "").split(" ", 1)[-1].split(" (")[0]
        renglones.append(f"- {f['cantidad']} × {f['codigo']}"
                         + (f" ({str(f['descripcion'])[:40]})" if f.get("descripcion") else "")
                         + f": {que.lower()}"
                         + (f", «{str(f['detalle'])[:80]}»" if f.get("detalle") else "")
                         + f" (devuelta el {dia_de_aca(f['fecha'])[8:10]}/"
                           f"{dia_de_aca(f['fecha'])[5:7]})")
    return "\n".join(renglones) + "\n¿Cómo hacemos para el cambio o la nota de crédito? ¡Gracias!"


def marcar_reclamo(devolucion_ids, estado):
    """Anota en qué quedó el reclamo de esas devoluciones (uno de ESTADOS_DEL_RECLAMO; "" vuelve
    a «por reclamar»). Lo hace el personal; queda en el registro de cambios. Devuelve cuántas."""
    exigir_nivel("empleado", "anotar un reclamo de garantía")
    if estado not in ESTADOS_DEL_RECLAMO:
        raise ValueError(f"Estado de reclamo desconocido: {estado}")
    ids = [int(i) for i in devolucion_ids or []]
    if not ids:
        return 0
    with db_lock:
        c.execute(f"""UPDATE ventas_devoluciones SET reclamo = ?, reclamo_en = datetime('now'),
                                                     reclamo_por = ?
                      WHERE id IN ({','.join('?' * len(ids))})
                        AND motivo IN ({','.join('?' * len(MOTIVOS_PARA_RECLAMAR))})""",
                  [estado or None, obtener_usuario_actual(), *ids, *sorted(MOTIVOS_PARA_RECLAMAR)])
        n = c.rowcount
        anotar_cambio("anotó un reclamo de garantía", "devolución", ",".join(map(str, ids)),
                      despues=ESTADOS_DEL_RECLAMO[estado])
        conn.commit()
    return n


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
    c.execute("""SELECT v.id, v.fecha, substr(datetime(v.fecha, '-3 hours'), 12, 5) AS hora,
                        v.usuario, v.cliente,
                        v.total, v.mecanico_id, k.nombre AS cuenta, COALESCE(v.sena, 0) AS sena
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
    sena = venta.get("sena") or 0
    return (f"🧾 Venta #{venta['id']} — vendió {venta.get('usuario') or '¿?'} · para {para} · "
            f"${miles(venta.get('total') or 0, 0)}"
            + (f" (🔖 dejó ${miles(sena, 0)} de seña: cobrar "
               f"${miles((venta.get('total') or 0) - sena, 0)})" if sena else "")
            + f" · {venta.get('hora') or ''}")


def total_con_descuento(venta_id, descuento, recargo=0):
    """Lo que queda la venta con ese descuento (y ese recargo por cuotas), redondeado como al
    cobrarla."""
    c.execute("SELECT cantidad, precio FROM ventas_items WHERE venta_id = ?", (venta_id,))
    return round(sum(f["cantidad"] * round(float(f["precio"] or 0)
                                           * (1 - float(descuento or 0) / 100)
                                           * (1 + float(recargo or 0) / 100), 2)
                     for f in c.fetchall()), 2)


# EL RECARGO POR CUOTAS: con tarjeta de crédito en cuotas el negocio cobra un recargo (lo que le
# cobra la tarjeta por financiar), y la cajera lo calculaba aparte con la calculadora: cada una
# con su número, y en la caja quedaba el precio sin recargo, así que el cierre no daba con el
# resumen de la tarjeta. El administrador anota el porcentaje de cada cantidad de cuotas (en
# 🗂️ Administrar → 💬 Mensajería y cobros); al cobrar con crédito en cuotas se aplica solo, y se
# ve antes de cobrar. Va como el descuento, sobre el precio de cada cosa: así la factura, la
# devolución (vuelve lo que pagó) y el comprobante cierran sin cuentas aparte. «Volver a la
# caja» lo saca, como al descuento. Las cuotas sin interés de una promoción: en 0.
# Y LAS CUENTAS CORRIENTES, CON EL SUYO: lo preguntó el dueño («los recargos cambian si es en una
# cuenta corriente o mostrador común»). Con «Las cuentas corrientes tienen otro recargo»
# prendido, la venta a una cuenta (la de «🧾 Atendiendo a») usa su tabla; apagado, la misma que
# el mostrador.
RECARGO_MAXIMO = 100.0
CLAVE_DE_LOS_RECARGOS = {False: "recargos_por_cuotas", True: "recargos_por_cuotas_cuentas"}
CLAVE_DE_OTRO_RECARGO_PARA_CUENTAS = "recargos_cuentas_aparte"


def cuentas_con_otro_recargo():
    """¿Las cuentas corrientes tienen su propia tabla de recargos?"""
    return obtener_config(CLAVE_DE_OTRO_RECARGO_PARA_CUENTAS, "") == "1"


def recargos_por_cuotas(de_cuenta=False, la_suya=False):
    """{cuotas: porcentaje} de las que tienen recargo (un pago, nunca): las del mostrador, o las
    de las cuentas corrientes si tienen la suya. `la_suya`: la tabla de las cuentas aunque esté
    apagada (para mostrarla en Administrar)."""
    de_cuenta = bool(de_cuenta) and (la_suya or cuentas_con_otro_recargo())
    try:
        datos = json.loads(obtener_config(CLAVE_DE_LOS_RECARGOS[de_cuenta], "") or "{}")
    except ValueError:
        return {}
    salida = {}
    for k, v in (datos or {}).items():
        try:
            cuotas, por_ciento = int(k), float(v)
        except (TypeError, ValueError):
            continue
        if cuotas in CUOTAS_POSIBLES and cuotas > 1 and 0 < por_ciento <= RECARGO_MAXIMO:
            salida[cuotas] = por_ciento
    return salida


def recargos_que_le_tocan(de_cuenta=False, mecanico_id=None):
    """La tabla de recargos de esa venta: la propia de la cuenta si tiene trato especial (ver
    «EL TRATO ESPECIAL DE UNA CUENTA»); si no, la de las cuentas o la del mostrador."""
    if mecanico_id:
        propios = trato_de_la_cuenta(mecanico_id)["recargos"]
        if propios is not None:
            return propios
    return recargos_por_cuotas(de_cuenta or bool(mecanico_id))


def recargo_por_cuotas(forma_de_pago, cuotas, de_cuenta=False, mecanico_id=None):
    """El porcentaje que se le suma a un cobro: solo con crédito y en cuotas que lo tengan. A una
    cuenta corriente, el de las cuentas (si lo tienen aparte), o el suyo (trato especial)."""
    if forma_de_pago != "Tarjeta de crédito":
        return 0.0
    return recargos_que_le_tocan(de_cuenta, mecanico_id).get(int(cuotas or 1), 0.0)


def texto_de_las_cuotas(total, de_cuenta=False, mecanico_id=None):
    """«💳 3 cuotas de $733 (total $2.200) · 12 cuotas de $208 (…)»: lo que el vendedor le dice
    al cliente que pregunta «¿y en cuotas?», con los recargos anotados (los de las cuentas, si
    es a una cuenta y las tienen aparte, o los de su trato especial). "" si no hay ninguno."""
    recargos = recargos_que_le_tocan(de_cuenta, mecanico_id)
    if not recargos or not total:
        return ""
    partes = []
    for cuotas, por_ciento in sorted(recargos.items()):
        con_recargo = round(float(total) * (1 + por_ciento / 100), 2)
        partes.append(f"{cuotas} cuotas de \\${miles(con_recargo / cuotas, 0)} (total "
                      f"\\${miles(con_recargo, 0)})")
    return "💳 Con crédito: " + " · ".join(partes)


def guardar_recargos_por_cuotas(recargos, de_cuenta=False, aparte=None):
    """{cuotas: porcentaje}; en 0 no tiene. `de_cuenta`: la tabla de las cuentas corrientes;
    `aparte` (True/False): si las cuentas usan la suya. Lo cambia el administrador; queda en el
    registro."""
    exigir_nivel("admin", "cambiar el recargo por cuotas")
    if aparte is not None and bool(aparte) != cuentas_con_otro_recargo():
        guardar_config(CLAVE_DE_OTRO_RECARGO_PARA_CUENTAS, "1" if aparte else "0")
        anotar_cambio("cambió si las cuentas tienen otro recargo", "configuración",
                      CLAVE_DE_OTRO_RECARGO_PARA_CUENTAS, antes=not aparte, despues=bool(aparte))
    nuevos = {}
    for k, v in (recargos or {}).items():
        cuotas, por_ciento = int(k), round(float(v or 0), 2)
        if cuotas not in CUOTAS_POSIBLES or cuotas <= 1:
            raise ValueError("El recargo es para 2 cuotas o más.")
        if not 0 <= por_ciento <= RECARGO_MAXIMO:
            raise ValueError(f"El recargo tiene que ser entre 0 y {miles(RECARGO_MAXIMO, 0)}%.")
        if por_ciento:
            nuevos[cuotas] = por_ciento
    antes = recargos_por_cuotas(de_cuenta, la_suya=True)
    if nuevos != antes:
        guardar_config(CLAVE_DE_LOS_RECARGOS[bool(de_cuenta)],
                       json.dumps({str(k): v for k, v in sorted(nuevos.items())}))
        anotar_cambio("cambió el recargo por cuotas", "configuración",
                      CLAVE_DE_LOS_RECARGOS[bool(de_cuenta)], antes=antes, despues=nuevos)
    return nuevos


def _texto_de_los_recargos(recargos):
    return (", ".join(f"{n} cuotas {como_porcentaje(p)}%" for n, p in sorted(recargos.items()))
            or "ninguno (todas sin interés)")


def guardar_recargos_y_avisar(claves, claves_cuentas=None, clave_aparte=None):
    """«💾 Guardar los recargos» (va como on_click): `claves` es {cuotas: clave del campo} del
    mostrador; `claves_cuentas`, las de las cuentas corrientes, y `clave_aparte`, la del tilde
    «Las cuentas corrientes tienen otro recargo»."""
    try:
        aparte = bool(st.session_state.get(clave_aparte)) if clave_aparte else None
        nuevos = guardar_recargos_por_cuotas(
            {n: st.session_state.get(k) or 0 for n, k in claves.items()}, aparte=aparte)
        texto = "💳 Recargo por cuotas: " + _texto_de_los_recargos(nuevos) + "."
        if aparte and claves_cuentas:
            de_cuentas = guardar_recargos_por_cuotas(
                {n: st.session_state.get(k) or 0 for n, k in claves_cuentas.items()},
                de_cuenta=True)
            texto += " Cuentas corrientes: " + _texto_de_los_recargos(de_cuentas) + "."
        elif clave_aparte:
            texto += " Las cuentas corrientes, el mismo."
        aviso = ("success", texto)
    except (PermissionError, ValueError) as _err:
        aviso = ("warning", el_error_en_castellano(_err))
    avisar(*aviso)


def _descuento_valido(descuento, tope):
    try:
        descuento = round(float(descuento or 0), 2)
    except (TypeError, ValueError):
        raise ValueError("El descuento tiene que ser un número.")
    if not 0 <= descuento <= tope:
        raise ValueError(f"El descuento va de 0 a {miles(tope, 0)}%.")
    return descuento


def _aplicar_el_descuento(venta_id, descuento, recargo=0):
    """Adentro de la transacción del cobro: el precio de cada cosa, con el descuento (y el
    recargo por cuotas); devuelve el total nuevo (el que llama lo guarda en la venta). Siempre
    desde el precio sin descuento (precio_de_lista; en las ventas de antes de guardarlo, el que
    tiene)."""
    if descuento or recargo:
        c.execute("""UPDATE ventas_items
                     SET precio = ROUND(COALESCE(precio_de_lista, precio) * (1 - ? / 100.0)
                                        * (1 + ? / 100.0), 2)
                     WHERE venta_id = ?""", (descuento or 0, recargo or 0, venta_id))
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
    # El de las cuentas corrientes si es a una cuenta, o el suyo (ver «EL RECARGO POR CUOTAS» y
    # «EL TRATO ESPECIAL DE UNA CUENTA»); y su descuento puede pasar el tope de la caja.
    _de_cuenta = c.execute("SELECT mecanico_id FROM ventas WHERE id = ?", (venta_id,)).fetchone()
    _mid = _de_cuenta["mecanico_id"] if _de_cuenta else None
    try:
        descuento = _descuento_valido(descuento, max(DESCUENTO_MAXIMO_EN_LA_CAJA,
                                                     descuento_al_cobrarle(_mid)))
    except ValueError as e:
        return False, str(e)
    recargo = recargo_por_cuotas(forma_de_pago, cuotas, de_cuenta=bool(_mid), mecanico_id=_mid)
    with db_lock, transaccion():
        # Se marca cobrada SOLO si seguía esperando: dos cajeros con la misma venta en pantalla
        # no la cobran dos veces.
        c.execute("""UPDATE ventas SET cobrada = 1, forma_de_pago = ?, cuotas = ?, descuento = ?,
                            recargo = ?, cobrada_por = ?, cobrada_en = datetime('now', 'localtime')
                     WHERE id = ? AND COALESCE(cobrada, 1) = 0 AND anulada = 0""",
                  (forma_de_pago, cuotas, descuento, recargo, obtener_usuario_actual(), venta_id))
        if c.rowcount != 1:
            return False, "Esa venta ya no está esperando en la caja (¿la cobró otro o se anuló?)."
        total = _aplicar_el_descuento(venta_id, descuento, recargo)
        c.execute("UPDATE ventas SET total = ? WHERE id = ?", (total, venta_id))
        if descuento:
            anotar_cambio("cobró con descuento", "venta", venta_id,
                          despues={"descuento": descuento, "total": total})
    return True, (f"💵 Venta #{venta_id} cobrada: ${miles(total, 0)} "
                  f"({como_se_pago({'forma_de_pago': forma_de_pago, 'cuotas': cuotas})}"
                  + (f", con {como_porcentaje(descuento)}% de descuento" if descuento else "")
                  + (f", con {como_porcentaje(recargo)}% de recargo" if recargo else "") + ").")


def poner_a_cuenta(venta_id, mecanico_id=None, descuento=None):
    """F11: pone a cuenta una venta que espera en la caja (la cuenta a la que se vendió, o
    `mecanico_id`). Con el descuento de la cuenta si no se dice otro, el plazo de la cuenta y
    su límite de crédito, como al entregar el depósito. (ok, texto)."""
    exigir_nivel("empleado", "poner una venta a cuenta")
    c.execute("""SELECT mecanico_id, COALESCE(sena, 0) AS sena FROM ventas
                 WHERE id = ? AND COALESCE(cobrada, 1) = 0 AND anulada = 0""", (venta_id,))
    fila = c.fetchone()
    if not fila:
        return False, "Esa venta ya no está esperando en la caja (¿la cobró otro o se anuló?)."
    if fila["sena"]:
        return False, (f"Tiene ${miles(fila['sena'], 0)} de seña descontados: se cobra lo que "
                       "falta (una venta con seña no va a cuenta).")
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
    vence = (hoy_aca() + timedelta(days=config["dias_de_plazo"])).isoformat()
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
        c.execute(f"""SELECT items, cliente, substr(datetime(guardada, '-3 hours'), 12, 5) AS hora
                       FROM {tabla}
                      WHERE usuario = ? AND date(guardada, '-3 hours') = date('now', '-3 hours')""",
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


# ============================================================================================
# LOS PRESUPUESTOS PARA SEGUIR
# ============================================================================================
# Un presupuesto que se manda por WhatsApp y el cliente no contesta se perdía: nadie se acordaba
# de preguntarle, y era una venta a un mensaje de distancia. Ahora, al mandarlo, se guarda con el
# nombre y el teléfono del cliente (📌 en el presupuesto del Buscador), y queda en «📋 Presupuestos
# para seguir»: hace cuántos días, el «¿lo pudiste ver?» ya escrito para su WhatsApp, y en qué
# quedó —volvió (se vuelve a armar, con los precios que se le pasaron) o no lo quiere—. Desde el
# día siguiente toca preguntar; preguntado, vuelve a tocar a los DIAS_PARA_VOLVER_A_PREGUNTAR.
DIAS_PARA_VOLVER_A_PREGUNTAR = 3
# LA VALIDEZ DEL PRESUPUESTO: con la inflación, «🛒 Volvió: armarlo» con los precios de hace dos
# semanas vendía por debajo de la lista de hoy, sin que nadie se diera cuenta. El mensaje dice
# hasta cuándo valen; pasados esos días se arma con los de hoy (y se puede respetar el de
# entonces a mano), y antes, si subieron, se dice cuánto.
DIAS_DE_VALIDEZ_DEL_PRESUPUESTO = 7
ESTADOS_DEL_PRESUPUESTO = {"abierto": "⏳ Esperando respuesta", "volvio": "✅ Volvió",
                           "no": "🗑️ No lo quiere"}


def guardar_presupuesto_para_seguir(cliente, telefono, carrito):
    """Guarda el presupuesto armado (el carrito del Buscador) para seguirlo. Devuelve su número.
    Lo hace el personal: el que entra sin cuenta arma y manda, pero no deja datos guardados."""
    exigir_nivel("empleado", "guardar un presupuesto para seguirlo")
    items = [{"producto_id": pid, **{k: it.get(k) for k in CAMPOS_DEL_PRESUPUESTO_QUE_SE_GUARDAN}}
             for pid, it in (carrito or {}).items()]
    if not items:
        raise ValueError("El presupuesto está vacío.")
    total = round(sum((it.get("precio") or 0) * (it.get("cantidad") or 1) for it in items), 2)
    cliente, telefono = str(cliente or "").strip()[:80], str(telefono or "").strip()[:40]
    with db_lock:
        # El mismo, al mismo cliente, una sola vez: mandado al chat ya queda guardado, y después
        # se tocaba «📌 Guardar» igual (o dos veces). «El mismo»: los mismos productos, con la
        # misma cantidad y el mismo precio (lo tildado para llevar no cuenta).
        def huella(lista):
            return sorted((str(it.get("producto_id")), int(it.get("cantidad") or 1),
                           round(float(it.get("precio") or 0), 2)) for it in lista)
        for f in c.execute("""SELECT id, items FROM presupuestos_para_seguir
                              WHERE estado = 'abierto' AND COALESCE(cliente, '') = ?
                                AND COALESCE(telefono, '') = ?""", (cliente, telefono)).fetchall():
            if huella(json.loads(f["items"] or "[]")) == huella(items):
                return f["id"]
        c.execute("""INSERT INTO presupuestos_para_seguir (usuario, cliente, telefono, items, total)
                     VALUES (?, ?, ?, ?, ?)""",
                  (obtener_usuario_actual(), cliente or None, telefono or None,
                   json.dumps(items), total))
        nuevo = c.lastrowid
        conn.commit()
    return nuevo


def presupuestos_para_seguir():
    """Los que esperan respuesta, lo más viejo primero: [dict] con id, cliente, telefono, items,
    total, creado_en (como está guardado), hace (días), toca (si toca preguntar), link (su
    WhatsApp con el mensaje) y contesto (el chat de 💬 Mensajes donde escribió después de
    mandárselo, o None). Los que contestaron primero, después los que tocan.

    EL QUE YA CONTESTÓ NO SE PREGUNTA: escribió por el chat después del presupuesto (o de la
    última vez que se le preguntó), así que lo que toca es leerlo, no mandarle «¿lo pudiste
    ver?» encima de su respuesta. Se reconoce por los últimos ocho dígitos del teléfono, como
    en el resto de la app."""
    chats = {}
    for ch in c.execute("""SELECT id, externo, ultimo_del_cliente_en FROM chats
                           WHERE canal = 'whatsapp' AND ultimo_del_cliente_en IS NOT NULL"""):
        fin = re.sub(r"\D", "", str(ch["externo"]))[-8:]
        if len(fin) == 8 and (fin not in chats or ch["ultimo_del_cliente_en"] > chats[fin][1]):
            chats[fin] = (ch["id"], ch["ultimo_del_cliente_en"])
    c.execute("""SELECT id, cliente, telefono, items, total, creado_en, usuario, preguntado_en,
                        CAST(julianday('now') - julianday(creado_en) AS INTEGER) AS hace,
                        CAST(julianday('now') - julianday(preguntado_en) AS INTEGER)
                            AS preguntado_hace
                 FROM presupuestos_para_seguir WHERE estado = 'abierto' ORDER BY creado_en, id""")
    salida = []
    for f in c.fetchall():
        p = dict(f)
        p["items"] = json.loads(p["items"] or "[]")
        fin = re.sub(r"\D", "", str(p["telefono"] or ""))[-8:]
        chat = chats.get(fin) if len(fin) == 8 else None
        desde = max(str(p["creado_en"] or ""), str(p["preguntado_en"] or ""))
        p["contesto"] = chat[0] if chat and str(chat[1]) > desde else None
        p["toca"] = (not p["contesto"] and p["hace"] >= 1
                     and (p["preguntado_hace"] is None
                          or p["preguntado_hace"] >= DIAS_PARA_VOLVER_A_PREGUNTAR))
        p["vencido"] = p["hace"] >= DIAS_DE_VALIDEZ_DEL_PRESUPUESTO
        p.update(lo_que_subio(p["items"]))
        p["link"] = link_de_whatsapp(p["telefono"], mensaje_de_seguimiento(p))
        salida.append(p)
    salida.sort(key=lambda p: (not p["contesto"], not p["toca"]))
    return salida


def lo_que_subio(items):
    """Cuánto cambiaron los precios de un presupuesto guardado: {total_hoy, subio (en %, del
    total; 0 si no subió), subieron [(«MARCA CÓDIGO», % de suba)]}. Lo que ya no está en el
    catálogo o no tiene precio hoy no cuenta."""
    antes = hoy = 0.0
    subieron = []
    for it in items or []:
        actual = item_de_venta(it.get("producto_id")) if it.get("producto_id") else None
        precio = float(it.get("precio") or 0)
        cantidad = int(it.get("cantidad") or 1)
        if not actual or not actual["precio"] or not precio:
            continue
        antes += precio * cantidad
        hoy += actual["precio"] * cantidad
        if actual["precio"] > precio * 1.005:
            subieron.append((f"{it.get('marca') or ''} {it.get('codigo') or ''}".strip(),
                             round((actual["precio"] / precio - 1) * 100)))
    return {"total_hoy": round(hoy, 2),
            "subio": round((hoy / antes - 1) * 100) if antes and hoy > antes * 1.005 else 0,
            "subieron": subieron}


def mensaje_de_seguimiento(presupuesto):
    """El «¿lo pudiste ver?», con qué era: lo primero del presupuesto y el total."""
    items = presupuesto.get("items") or []
    que = ", ".join(f"{it.get('marca') or ''} {it.get('codigo') or ''}".strip()
                    for it in items[:2]) + (f" y {len(items) - 2} más" if len(items) > 2 else "")
    nombre = str(presupuesto.get("cliente") or "").strip()
    return (f"Hola{(' ' + nombre) if nombre else ''}! Te escribimos de El Chavo por el presupuesto "
            f"que te pasamos el {dia_de_aca(presupuesto.get('creado_en'))[8:10]}/"
            f"{dia_de_aca(presupuesto.get('creado_en'))[5:7]} ({que}, total "
            f"${miles(presupuesto.get('total') or 0, 0)}). ¿Lo pudiste ver? "
            + ("Los precios pueden haber cambiado: si querés, te lo pasamos actualizado."
               if presupuesto.get("vencido") else "Si querés, te lo guardamos.")
            + " ¡Gracias!")


def marcar_presupuesto(presupuesto_id, que):
    """«preguntado» (se le preguntó: vuelve a tocar en unos días), «volvio» o «no» (se cierra).
    Lo hace el personal; queda en el registro de cambios."""
    exigir_nivel("empleado", "anotar el seguimiento de un presupuesto")
    if que not in ("preguntado", "volvio", "no"):
        raise ValueError(f"Seguimiento desconocido: {que}")
    with db_lock:
        if que == "preguntado":
            c.execute("UPDATE presupuestos_para_seguir SET preguntado_en = datetime('now') "
                      "WHERE id = ?", (int(presupuesto_id),))
        else:
            c.execute("UPDATE presupuestos_para_seguir SET estado = ?, cerrado_en = datetime('now') "
                      "WHERE id = ? AND estado = 'abierto'", (que, int(presupuesto_id)))
        anotar_cambio(f"seguimiento del presupuesto: {que}", "presupuesto", presupuesto_id)
        conn.commit()


def volver_a_armar_el_presupuesto(presupuesto_id, con_los_de_hoy=None):
    """«🛒 Volvió: armarlo» (va como on_click): vuelve al presupuesto del Buscador, con la
    cantidad que se le pasó, y el seguimiento se cierra como «volvió». El precio: el que se le
    pasó, salvo `con_los_de_hoy` (sin decir, pasada la validez: ver
    DIAS_DE_VALIDEZ_DEL_PRESUPUESTO). Lo que ya no está en el catálogo queda afuera, y se dice."""
    fila = c.execute("""SELECT items, CAST(julianday('now') - julianday(creado_en) AS INTEGER)
                               AS hace
                        FROM presupuestos_para_seguir WHERE id = ?""",
                     (int(presupuesto_id),)).fetchone()
    if not fila:
        return
    if con_los_de_hoy is None:
        con_los_de_hoy = (fila["hace"] or 0) >= DIAS_DE_VALIDEZ_DEL_PRESUPUESTO
    items = json.loads(fila["items"] or "[]")
    subas = lo_que_subio(items)
    carrito = st.session_state.setdefault("carrito", {})
    afuera = []
    for it in items:
        pid = it.get("producto_id")
        actual = item_de_venta(pid)
        if not actual:
            afuera.append(f"{it.get('marca') or ''} {it.get('codigo') or ''}".strip())
            continue
        carrito[pid] = {k: it.get(k) for k in CAMPOS_DEL_PRESUPUESTO_QUE_SE_GUARDAN}
        carrito[pid]["cantidad"] = int(it.get("cantidad") or 1)
        if con_los_de_hoy and actual["precio"]:
            carrito[pid]["precio"] = actual["precio"]
        st.session_state.pop(f"cant_cart_{pid}", None)
        st.session_state.pop(f"se_lleva_{pid}", None)
    marcar_presupuesto(presupuesto_id, "volvio")
    if con_los_de_hoy:
        como = "con los precios de hoy"
    elif subas["subio"]:
        como = (f"con los precios que se le pasaron (hoy están {subas['subio']}% más arriba: "
                + ", ".join(f"{q} +{s}%" for q, s in subas["subieron"][:3]) + ")")
    else:
        como = "con los precios que se le pasaron"
    avisar("success", f"🛒 El presupuesto volvió a armarse, {como}."
                      + (f" Ya no están en el catálogo: {', '.join(afuera)}." if afuera else ""))


def cuantos_presupuestos_para_seguir():
    return c.execute("SELECT COUNT(*) FROM presupuestos_para_seguir "
                     "WHERE estado = 'abierto'").fetchone()[0]


def guardar_el_presupuesto_para_seguir():
    """El «📌 Guardar» del presupuesto del Buscador (va como on_click): con el cliente y el
    teléfono escritos (si no hay nombre, el de la cuenta que se atiende), y deja los campos
    vacíos para el próximo."""
    cuenta = cuenta_elegida()
    cliente = (st.session_state.get("presu_seguir_cliente") or "").strip() or (
        cuenta["nombre"] if cuenta else "")
    problema = ""
    try:
        guardar_presupuesto_para_seguir(cliente, st.session_state.get("presu_seguir_tel"),
                                        st.session_state.get("carrito"))
    except (PermissionError, ValueError) as _err:
        problema = el_error_en_castellano(_err)
    if problema:
        avisar("warning", problema)
        return
    st.session_state["presu_seguir_cliente"] = ""
    st.session_state["presu_seguir_tel"] = ""
    avisar("success", "📌 Guardado en «📋 Presupuestos para seguir»"
                      + (f", para {cliente}" if cliente else "") + ". Si en un día no contestó, "
                      "ahí está el mensaje para preguntarle.")


# Cuántos se muestran de una vez: los que tocan primero.
MAXIMO_DE_PRESUPUESTOS_PARA_SEGUIR = 30


def mostrar_presupuestos_para_seguir():
    """Adentro de «📋 Presupuestos para seguir», en el Buscador."""
    lista = presupuestos_para_seguir()
    if not lista:
        st.caption("Ninguno esperando respuesta. 🎉")
        return
    _contestaron = sum(1 for p in lista if p["contesto"])
    st.caption(f"Toca preguntarles a {miles(sum(1 for p in lista if p['toca']))} de "
               f"{miles(len(lista))} (los mandados hace un día o más; a los ya preguntados, de "
               f"nuevo a los {DIAS_PARA_VOLVER_A_PREGUNTAR} días)."
               + (f" 💬 {miles(_contestaron)} te contestaron por el chat." if _contestaron else ""))
    for p in lista[:MAXIMO_DE_PRESUPUESTOS_PARA_SEGUIR]:
        with st.container(border=True, key=f"presu_seguir_{p['id']}"):
            _c1, _c2 = st.columns([3, 2], vertical_alignment="center")
            _c1.markdown(f"{'💬' if p['contesto'] else '🔴' if p['toca'] else '⚪'} "
                         f"**{texto_para_markdown(p['cliente'] or 'Sin nombre')}** · "
                         + ("hoy" if not p["hace"] else f"hace {miles(p['hace'])} día(s)")
                         + f" · \\${miles(p['total'] or 0, 0)}")
            _c1.caption(", ".join(f"{it.get('cantidad') or 1}× {it.get('marca') or ''} "
                                  f"{it.get('codigo') or ''}" for it in p["items"][:4])
                        + (f" y {len(p['items']) - 4} más" if len(p["items"]) > 4 else "")
                        + (f" · lo armó {p['usuario']}" if p.get("usuario") else "")
                        + ("" if numero_para_whatsapp(p["telefono"]) else
                           " · sin WhatsApp anotado"))
            if p["subio"]:
                _c1.caption(f"⚠️ Los precios subieron **{p['subio']}%** desde el presupuesto "
                            f"(hoy: \\${miles(p['total_hoy'], 0)})"
                            + (". Pasaron los "
                               f"{DIAS_DE_VALIDEZ_DEL_PRESUPUESTO} días de validez: se arma "
                               "con los de hoy." if p["vencido"] else "."))
            if p["contesto"]:
                _c2.button("💬 Te contestó: ver el chat", key=f"presu_chat_{p['id']}",
                           type="primary", width="stretch", on_click=abrir_el_chat,
                           args=(p["contesto"],),
                           help="Escribió por el chat después del presupuesto: leelo antes de "
                                "preguntarle.")
            else:
                _c2.link_button("📲 Preguntarle si lo vio"
                                if numero_para_whatsapp(p["telefono"])
                                else "📲 Preguntarle (elegís a quién)", p["link"],
                                width="stretch")
            _b1, _b2, _b3 = st.columns(3)
            _b1.button("✅ Ya le pregunté", key=f"presu_preguntado_{p['id']}", width="stretch",
                       on_click=marcar_presupuesto, args=(p["id"], "preguntado"))
            _b2.button("🛒 Volvió: armarlo", key=f"presu_volvio_{p['id']}", width="stretch",
                       on_click=volver_a_armar_el_presupuesto, args=(p["id"],),
                       help=("Vuelve al presupuesto de acá arriba, con los precios de hoy "
                             f"(pasaron los {DIAS_DE_VALIDEZ_DEL_PRESUPUESTO} días de validez), "
                             "para pasarlo a una venta." if p["vencido"] else
                             "Vuelve al presupuesto de acá arriba, con los precios que se le "
                             "pasaron, para pasarlo a una venta."))
            _b3.button("🗑️ No lo quiere", key=f"presu_no_{p['id']}", width="stretch",
                       on_click=marcar_presupuesto, args=(p["id"], "no"))
            # Si subieron, la otra forma a mano: respetar el precio vencido, o actualizar el
            # que todavía vale.
            if p["subio"]:
                st.button("🛒 Volvió, pero con los precios que se le pasaron" if p["vencido"]
                          else "🛒 Volvió, pero con los precios de hoy",
                          key=f"presu_volvio_otro_{p['id']}", width="stretch",
                          on_click=volver_a_armar_el_presupuesto,
                          args=(p["id"], not p["vencido"]))
    if len(lista) > MAXIMO_DE_PRESUPUESTOS_PARA_SEGUIR:
        st.caption(f"Y {miles(len(lista) - MAXIMO_DE_PRESUPUESTOS_PARA_SEGUIR)} más.")


# ============================================================================================
# QUE UNA VENTA NO SE GRABE POR ACCIDENTE
# ============================================================================================
# Lo pidió el dueño: «que lo de ventas sea más seguro de que no se grabe por accidente una
# venta». Había tres agujeros:
#   - F9 —o el botón grande y naranja del celular, tocado al pasar— la grababa de un saque.
#     Ahora el botón (y F9) pregunta «¿Terminar la venta?» con el total, y se graba recién con
#     «Sí». Si mientras tanto cambia algo (una cantidad, un precio, el cliente), vuelve a
#     preguntar: ver huella_de_la_venta().
#   - Nada frenaba grabar dos veces la misma: un doble toque, o la página recargada con la
#     venta recuperada (ver «LA VENTA Y EL PRESUPUESTO A MEDIO ARMAR»). Ahora la misma venta de
#     la misma persona, para la misma cuenta, dentro de dos minutos, pide decir que es otra:
#     ver venta_igual_reciente(). Está acá y no adentro de cerrar_venta(): dos ventas iguales
#     seguidas son legítimas (dos clientes que llevan la misma lata de aceite), y quien decide
#     es el que está vendiendo.
#   - El vendedor que se equivocaba no podía deshacerla: anular es del administrador. Ahora
#     puede deshacer la suya mientras espera en la caja y por diez minutos: todavía no entró
#     plata. Cobrada o puesta a cuenta, sigue siendo del administrador: deshacer una venta
#     cobrada es sacar plata del cierre. Ver deshacer_mi_venta().
SEGUNDOS_PARA_VENTA_REPETIDA = 120
MINUTOS_PARA_DESHACER_LA_PROPIA = 10


def huella_de_la_venta(items, cliente="", forma_de_pago="", mecanico_id=None):
    """Lo que, si cambia, hay que volver a confirmar: cada producto con su cantidad y su precio,
    el cliente, cómo paga y a qué cuenta."""
    return (tuple(sorted((int(it["producto_id"]), int(it.get("cantidad") or 0),
                          round(float(it.get("precio") or 0), 2)) for it in items)),
            (cliente or "").strip(), forma_de_pago or "", mecanico_id or None)


def venta_igual_reciente(items, usuario=None, mecanico_id=None,
                         segundos=SEGUNDOS_PARA_VENTA_REPETIDA):
    """La venta de esta misma persona, con los mismos productos, cantidades y precios y para la
    misma cuenta, grabada hace menos de `segundos` y no anulada: {"id", "hace"} (segundos), o
    None."""
    usuario = usuario or obtener_usuario_actual()
    lo_de_ahora = huella_de_la_venta(items)[0]
    c.execute("""SELECT id, CAST(strftime('%s', 'now', 'localtime') - strftime('%s', fecha)
                                 AS INTEGER) AS hace
                 FROM ventas
                 WHERE usuario = ? AND COALESCE(anulada, 0) = 0
                   AND COALESCE(mecanico_id, 0) = ?
                   AND fecha >= datetime('now', 'localtime', ?)
                   -- Lo «del futuro» no es reciente: pasa si cambia el reloj del servidor (la
                   -- app corre en UTC; con la hora de acá, lo de antes quedaría adelante).
                   AND fecha <= datetime('now', 'localtime', '+5 seconds')
                 ORDER BY id DESC""", (usuario, mecanico_id or 0, f"-{int(segundos)} seconds"))
    for v in c.fetchall():
        c.execute("SELECT producto_id, cantidad, precio FROM ventas_items WHERE venta_id = ?",
                  (v["id"],))
        if tuple(sorted((r[0], r[1], round(r[2], 2)) for r in c.fetchall())) == lo_de_ahora:
            return {"id": v["id"], "hace": max(0, v["hace"] or 0)}
    return None


def puede_deshacer_su_venta(venta_id):
    """(sí o no, por qué no) para el botón «↩️ Me equivoqué: deshacerla». El administrador
    siempre (anular_venta() mira lo demás); el resto, solo la suya, sin cobrar, sin poner a
    cuenta y de hace menos de diez minutos."""
    c.execute("""SELECT usuario, COALESCE(cobrada, 1) AS cobrada, COALESCE(anulada, 0) AS anulada,
                        movimiento_id,
                        (julianday('now', 'localtime') - julianday(fecha)) * 1440 AS minutos
                 FROM ventas WHERE id = ?""", (venta_id,))
    v = c.fetchone()
    if not v:
        return False, "Esa venta no existe."
    if v["anulada"]:
        return False, "Esa venta ya está anulada."
    if es_admin():
        return True, ""
    if v["usuario"] != obtener_usuario_actual():
        return False, "Es una venta de otra persona: la anula el administrador."
    if v["cobrada"] or v["movimiento_id"]:
        return False, ("Ya está cobrada o puesta a cuenta: para anularla, pedíselo al "
                       "administrador.")
    # Negativo es una venta anotada con otro reloj (si cambia el del servidor): no se sabe cuándo.
    if not 0 <= (v["minutos"] or 0) <= MINUTOS_PARA_DESHACER_LA_PROPIA:
        return False, (f"Pasaron más de {MINUTOS_PARA_DESHACER_LA_PROPIA} minutos: la anula el "
                       "administrador.")
    return True, ""


def _los_items_para_rearmar(venta_id):
    """Los ítems de una venta como los arma la pantalla (ver item_de_venta()), con la cantidad,
    el precio y el veredicto con que se vendieron: lo 🔴 ya se había confirmado al venderlo, y
    vuelve confirmado. Se leen ANTES de anularla: anular se lleva lo aprendido."""
    c.execute("""SELECT vi.producto_id, vi.cantidad, vi.precio, vi.pedido,
                        (SELECT vr.veredicto FROM ventas_registradas vr
                          WHERE vr.venta_id = vi.venta_id AND vr.producto_id = vi.producto_id
                          LIMIT 1) AS veredicto,
                        (SELECT vr.evidencia FROM ventas_registradas vr
                          WHERE vr.venta_id = vi.venta_id AND vr.producto_id = vi.producto_id
                          LIMIT 1) AS evidencia
                 FROM ventas_items vi
                 WHERE vi.venta_id = ? AND vi.producto_id IS NOT NULL ORDER BY vi.id""",
              (venta_id,))
    items = []
    for f in c.fetchall():
        it = item_de_venta(f["producto_id"], f["cantidad"], f["pedido"] or "")
        if it:
            it["precio"] = float(f["precio"] or 0)
            if f["veredicto"]:
                it.update(veredicto=f["veredicto"], evidencia=f["evidencia"],
                          confirmado=str(f["veredicto"]).startswith("🔴"))
            items.append(it)
    return items


def deshacer_mi_venta(venta_id):
    """«↩️ Me equivoqué»: anula la venta recién grabada si puede_deshacer_su_venta() lo deja.
    Como anular_venta(): el stock vuelve, la ficha del auto y lo aprendido se van, y la venta
    queda a la vista, marcada anulada y por quién. (ok, texto, los ítems para volver a armarla:
    lo más común es una cantidad o un precio mal puesto)."""
    exigir_nivel("empleado", "deshacer una venta")
    puede, por_que = puede_deshacer_su_venta(venta_id)
    if not puede:
        return False, por_que, []
    items = _los_items_para_rearmar(venta_id)
    ok, texto = _anular_la_venta(venta_id)
    if not ok:
        return False, texto, []
    anotar_cambio("deshizo su venta", "venta", venta_id, None, None,
                  "la grabó por error y la deshizo enseguida")
    return True, texto, items


# ============================================================================================
# CORREGIR UN COBRO
# ============================================================================================
# Lo pidió el dueño: «poder modificar si la cajera pasa algo mal, ya sea que se equivoca en el
# medio de pago o demás». Cobrada, una venta no se tocaba más: si la cajera marcaba «Efectivo»
# y era una transferencia, el cierre decía que en el cajón tenía que haber plata que no estaba,
# y el arqueo daba un faltante que no era. Dos correcciones:
#   - Cambiar cómo pagó (cambiar_como_se_pago()): no cambia el monto, solo por dónde entró.
#   - Volverla a la caja (volver_a_la_caja()): cobró la venta equivocada, se equivocó en el
#     descuento, o iba a cuenta y la cobró (o al revés). Vuelve a esperar como antes de
#     cobrarla —sin el descuento y, si estaba a cuenta, con el cargo de la cuenta anulado— y se
#     cobra bien.
# El empleado corrige los cobros del día; el administrador, cualquiera. Con devoluciones, no:
# la plata devuelta ya salió por esa forma de pago. Y cada corrección queda en el registro con
# el antes y el después, y en el cierre de caja de ese día, a la vista: cambiar «Efectivo» por
# «Transferencia» también es la forma de tapar un faltante del cajón.
CORRECCIONES_DEL_COBRO = ("corrigió cómo se pagó", "volvió una venta a la caja")


def puede_corregir_el_cobro(venta_id):
    """(sí o no, por qué no)."""
    c.execute("""SELECT COALESCE(cobrada, 1) AS cobrada, COALESCE(anulada, 0) AS anulada,
                        date(COALESCE(cobrada_en, fecha), '-3 hours') AS dia
                 FROM ventas WHERE id = ?""", (venta_id,))
    v = c.fetchone()
    if not v:
        return False, "Esa venta no existe."
    if v["anulada"]:
        return False, "Esa venta está anulada."
    if not v["cobrada"]:
        return False, "Todavía espera en la caja: no hay cobro que corregir."
    if c.execute("SELECT 1 FROM ventas_devoluciones WHERE venta_id = ? LIMIT 1",
                 (venta_id,)).fetchone():
        return False, ("Tiene devoluciones: la plata devuelta ya salió por esa forma de pago, y "
                       "no se corrige.")
    if es_admin():
        return True, ""
    if v["dia"] != hoy_aca().isoformat():
        return False, "Se cobró otro día: la corrige el administrador."
    return True, ""


def cambiar_como_se_pago(venta_id, forma_de_pago, cuotas=1):
    """Corrige la forma de pago (y las cuotas) de una venta cobrada. El monto no cambia. A cuenta
    no: eso es volverla a la caja y ponerla a cuenta, que mira el límite. (ok, texto)."""
    exigir_nivel("empleado", "corregir cómo se pagó una venta")
    if forma_de_pago not in FORMAS_DE_PAGO:
        return False, "Elegí cómo pagó."
    try:
        cuotas = int(cuotas or 1) if forma_de_pago == "Tarjeta de crédito" else 1
    except (TypeError, ValueError):
        return False, "Las cuotas tienen que ser un número."
    if cuotas not in CUOTAS_POSIBLES:
        return False, "Esa cantidad de cuotas no está."
    puede, por_que = puede_corregir_el_cobro(venta_id)
    if not puede:
        return False, por_que
    with db_lock, transaccion():
        c.execute("SELECT forma_de_pago, COALESCE(cuotas, 1) AS cuotas, movimiento_id, "
                  "COALESCE(recargo, 0) AS recargo FROM ventas WHERE id = ?", (venta_id,))
        antes = c.fetchone()
        if antes["movimiento_id"] or antes["forma_de_pago"] == A_CUENTA:
            return False, ("Está a cuenta: volvela a la caja y cobrala como corresponde (así "
                           "se anula el cargo de la cuenta).")
        # El recargo por cuotas está en el precio: cambiando solo la forma, el cliente que pagó
        # en efectivo quedaba con el recargo cobrado (ver «EL RECARGO POR CUOTAS»).
        if antes["recargo"]:
            return False, ("Se cobró con recargo por cuotas: volvela a la caja y cobrala como "
                           "corresponde (así se saca el recargo).")
        if antes["forma_de_pago"] == forma_de_pago and antes["cuotas"] == cuotas:
            return False, "Ya estaba así: no se cambió nada."
        c.execute("""UPDATE ventas SET forma_de_pago = ?, cuotas = ?
                     WHERE id = ? AND COALESCE(cobrada, 1) = 1 AND anulada = 0""",
                  (forma_de_pago, cuotas, venta_id))
        anotar_cambio(CORRECCIONES_DEL_COBRO[0], "venta", venta_id,
                      {"forma_de_pago": antes["forma_de_pago"], "cuotas": antes["cuotas"]},
                      {"forma_de_pago": forma_de_pago, "cuotas": cuotas})
    nuevo = como_se_pago({"forma_de_pago": forma_de_pago, "cuotas": cuotas})
    viejo = como_se_pago(dict(antes)) or "sin decir"
    return True, f"✏️ Venta #{venta_id}: ahora dice {nuevo} (antes, {viejo})."


def volver_a_la_caja(venta_id):
    """Deshace el cobro: la venta vuelve a esperar en la caja como antes de cobrarla, sin el
    descuento y, si estaba a cuenta, con el cargo de la cuenta anulado. El stock no se toca: el
    cliente igual se la llevó. (ok, texto)."""
    exigir_nivel("empleado", "volver una venta a la caja")
    puede, por_que = puede_corregir_el_cobro(venta_id)
    if not puede:
        return False, por_que
    # Con factura, el total ya está en ARCA: primero la nota de crédito. Cambiar cómo pagó sí se
    # puede, la factura no lo dice.
    if factura_vigente_de(venta_id):
        return False, ("Tiene factura electrónica: para volverla a la caja, primero anulá la "
                       "factura con la nota de crédito.")
    try:
        antes = _volver_a_la_caja(venta_id)
    except ValueError as e:
        return False, str(e)
    total = c.execute("SELECT total FROM ventas WHERE id = ?", (venta_id,)).fetchone()[0]
    return True, (f"↩️ Venta #{venta_id} de nuevo en la caja, por ${miles(total, 0)}"
                  + (" (sin el descuento)" if antes["descuento"] else "")
                  + (" (sin el recargo por cuotas)" if antes["recargo"] else "")
                  + (" y sin el cargo de la cuenta" if antes["movimiento_id"] else "")
                  + ": cobrala como corresponde.")


def _volver_a_la_caja(venta_id):
    """El cambio de volver_a_la_caja(), todo o nada. Devuelve cómo estaba."""
    with db_lock, transaccion():
        c.execute("""SELECT forma_de_pago, COALESCE(cuotas, 1) AS cuotas,
                            COALESCE(descuento, 0) AS descuento, movimiento_id, cobrada_por,
                            total, COALESCE(recargo, 0) AS recargo
                     FROM ventas WHERE id = ?""", (venta_id,))
        antes = c.fetchone()
        # El descuento se había aplicado al precio de cada cosa (ver _aplicar_el_descuento()):
        # cada renglón vuelve al precio sin descuento que tiene guardado. Dividiendo —lo que se
        # hacía, y lo que queda para las ventas de antes de guardarlo— el redondeo de ida y
        # vuelta se comía un centavo ($1.234,50 con 5% volvía en $1.234,49).
        if antes["descuento"] or antes["recargo"]:
            c.execute("""UPDATE ventas_items
                         SET precio = COALESCE(precio_de_lista,
                                               ROUND(precio / ((1 - ? / 100.0) * (1 + ? / 100.0)),
                                                     2))
                         WHERE venta_id = ?""", (antes["descuento"], antes["recargo"], venta_id))
        if antes["movimiento_id"]:
            c.execute("UPDATE movimientos_de_cuenta SET anulado = 1 WHERE id = ?",
                      (antes["movimiento_id"],))
        c.execute("SELECT COALESCE(SUM(cantidad * precio), 0) FROM ventas_items WHERE venta_id = ?",
                  (venta_id,))
        total = round(float(c.fetchone()[0]), 2)
        c.execute("""UPDATE ventas SET cobrada = 0, forma_de_pago = '', cuotas = 1, descuento = 0,
                            recargo = 0, cobrada_por = NULL, cobrada_en = NULL,
                            movimiento_id = NULL, total = ?
                     WHERE id = ? AND COALESCE(cobrada, 1) = 1 AND anulada = 0""",
                  (total, venta_id))
        if c.rowcount != 1:
            raise ValueError("Esa venta ya no está cobrada.")
        anotar_cambio(CORRECCIONES_DEL_COBRO[1], "venta", venta_id,
                      {"forma_de_pago": antes["forma_de_pago"], "cuotas": antes["cuotas"],
                       "descuento": antes["descuento"], "total": antes["total"],
                       "cobró": antes["cobrada_por"]},
                      {"total": total})
    return antes


def cobros_corregidos(dia=None):
    """Las correcciones de cobro de un día (hoy, si no se dice), la última primero: para el
    cierre de caja. [{hora, venta, que, antes, despues, quien}]."""
    dia = dia or hoy_aca().isoformat()
    huecos = ",".join("?" * len(CORRECCIONES_DEL_COBRO))
    c.execute(f"""SELECT substr(datetime(cuando, '-3 hours'), 12, 5) AS hora,
                         entidad_id AS venta, accion, antes,
                         despues, usuario
                  FROM registro_de_cambios
                  WHERE entidad = 'venta' AND accion IN ({huecos}) AND date(cuando, '-3 hours') = ?
                  ORDER BY id DESC""", (*CORRECCIONES_DEL_COBRO, dia))
    salida = []
    for r in c.fetchall():
        try:
            antes, despues = json.loads(r["antes"] or "{}"), json.loads(r["despues"] or "{}")
        except ValueError:
            antes, despues = {}, {}
        if r["accion"] == CORRECCIONES_DEL_COBRO[0]:
            que = (f"{como_se_pago(antes) or 'sin decir'} → {como_se_pago(despues)}")
        else:
            que = (f"volvió a la caja (estaba {como_se_pago(antes) or 'sin decir'}"
                   + (f", con {como_porcentaje(antes.get('descuento'))}% de descuento"
                      if antes.get("descuento") else "") + ")")
        salida.append({"hora": r["hora"], "venta": r["venta"], "que": que,
                       "quien": r["usuario"] or ""})
    return salida


# LA AGENDA DE CLIENTES DE MOSTRADOR: el que no tiene cuenta (paga en el momento) no quedaba en
# ningún lado como cliente: lo que esperaba estaba en «📞 Clientes que esperan», sus presupuestos
# en «Presupuestos para seguir», su auto en 🚗 Vehículos y sus compras, sin nombre ni teléfono.
# Cuando volvía, nadie sabía que ya había venido ni qué se le había dicho. Ahora la venta anota
# su teléfono (opcional), y con el teléfono se junta todo: lo que compró, lo que espera, sus
# presupuestos, sus autos, si es una cuenta y su chat de WhatsApp. El teléfono se compara como lo
# pide WhatsApp (ver numero_para_whatsapp()): «11 15 4567-8901» y «+54 9 11 4567 8901» son el
# mismo. Es del personal: el teléfono de un cliente no lo ve nadie más (ni el asistente lo dice).
COMPRAS_EN_LA_FICHA = 10
CLIENTES_EN_LA_AGENDA = 50
_SOLO_NUMEROS_SQL = ("REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE({col}, ' ', ''), '-', ''), "
                     "'(', ''), ')', ''), '+', ''), '.', '')")


def clave_del_telefono(telefono):
    """El teléfono para comparar: como lo pide WhatsApp (549…) si se entiende; si no, solo los
    números, si son 6 o más. '' si no hay teléfono."""
    numero = numero_para_whatsapp(telefono)
    if numero:
        return numero
    digitos = re.sub(r"\D", "", str(telefono or ""))
    return digitos if len(digitos) >= 6 else ""


def _lo_de_los_telefonos(clave=None):
    """[dict] lo que tiene un teléfono de cliente, con su «tipo» (compra, espera, presupuesto,
    auto) y su «clave». Con `clave`, solo lo de ese teléfono: la base filtra por los últimos 8
    números (así no se lee todo) y acá se confirma con la clave entera."""
    fin = clave[-8:] if clave else None
    filas = []
    for tipo, sql, columna in (
            ("compra", """SELECT id, fecha, cliente AS nombre, cliente_telefono AS telefono,
                                 total, mecanico_id
                          FROM ventas WHERE anulada = 0 AND COALESCE(cliente_telefono, '') != ''
                          {filtro}""", "cliente_telefono"),
            ("espera", """SELECT id, fecha, cliente AS nombre, telefono, codigo_buscado,
                                 descripcion, cantidad, estado
                          FROM consultas_cliente WHERE COALESCE(telefono, '') != '' {filtro}""",
             "telefono"),
            ("presupuesto", """SELECT id, creado_en AS fecha, cliente AS nombre, telefono, total,
                                      estado
                               FROM presupuestos_para_seguir WHERE COALESCE(telefono, '') != ''
                               {filtro}""", "telefono"),
            ("auto", """SELECT id, '' AS fecha, patente, cliente_nombre AS nombre,
                               cliente_telefono AS telefono, marca_auto, modelo_auto, anio
                        FROM vehiculos WHERE COALESCE(cliente_telefono, '') != '' {filtro}""",
             "cliente_telefono")):
        filtro = f"AND {_SOLO_NUMEROS_SQL.format(col=columna)} LIKE ?" if fin else ""
        c.execute(sql.format(filtro=filtro), (f"%{fin}",) if fin else ())
        filas += [{**dict(f), "tipo": tipo} for f in c.fetchall()]
    salida = []
    for f in filas:
        f["clave"] = clave_del_telefono(f["telefono"])
        if f["clave"] and (clave is None or f["clave"] == clave):
            salida.append(f)
    return salida


def _juntar_por_telefono(filas):
    """{clave: resumen}: el nombre y el teléfono más nuevos, cuántas compras y por cuánto, lo que
    espera, los presupuestos abiertos, las patentes y la última vez que se lo vio."""
    clientes = {}
    for f in sorted(filas, key=lambda x: x["fecha"] or ""):
        k = clientes.setdefault(f["clave"], {
            "clave": f["clave"], "nombre": "", "telefono": "", "compras": 0, "comprado": 0.0,
            "espera": 0, "presupuestos": 0, "autos": [], "ultima": ""})
        k["nombre"] = (f["nombre"] or "").strip() or k["nombre"]
        k["telefono"] = (f["telefono"] or "").strip() or k["telefono"]
        k["ultima"] = max(k["ultima"], f["fecha"] or "")
        if f["tipo"] == "compra":
            k["compras"] += 1
            k["comprado"] = round(k["comprado"] + float(f["total"] or 0), 2)
        elif f["tipo"] == "espera":
            k["espera"] += f["estado"] == "activa"
        elif f["tipo"] == "presupuesto":
            k["presupuestos"] += f["estado"] == "abierto"
        elif f["patente"] not in k["autos"]:
            k["autos"].append(f["patente"])
    return clientes


def agenda_de_clientes(texto="", tope=CLIENTES_EN_LA_AGENDA):
    """[resumen] de los clientes con teléfono, el que vino último primero. `texto`: un pedazo
    del teléfono, del nombre o de la patente."""
    exigir_nivel("empleado", "ver la agenda de clientes")
    clientes = list(_juntar_por_telefono(_lo_de_los_telefonos()).values())
    texto = str(texto or "").strip()
    if texto:
        digitos = re.sub(r"\D", "", texto)
        llano = normalizar_texto(texto).upper()
        patente = re.sub(r"[^A-Z0-9]", "", llano)
        clientes = [k for k in clientes
                    if (len(digitos) >= 4 and digitos in k["clave"])
                    or (llano and llano in normalizar_texto(k["nombre"]).upper())
                    or (len(patente) >= 3 and any(patente in re.sub(r"[^A-Z0-9]", "", a or "")
                                                  for a in k["autos"]))]
    clientes.sort(key=lambda k: k["ultima"], reverse=True)
    return clientes[:int(tope)]


def cliente_conocido(telefono):
    """El resumen de ese teléfono si ya vino (compró, espera algo, tiene presupuesto o auto);
    si no, None. Para avisar en la venta «ya vino»."""
    exigir_nivel("empleado", "ver la agenda de clientes")
    clave = clave_del_telefono(telefono)
    if not clave:
        return None
    return _juntar_por_telefono(_lo_de_los_telefonos(clave)).get(clave)


def ficha_del_cliente(telefono):
    """Todo lo de ese teléfono: {resumen, compras (las últimas, con lo que se llevó), espera,
    presupuestos, autos, cuenta (si es el teléfono de una cuenta), chat (su chat de WhatsApp,
    si hay), whatsapp (el link)}. None si no hay nada."""
    exigir_nivel("empleado", "ver la ficha de un cliente")
    clave = clave_del_telefono(telefono)
    if not clave:
        return None
    filas = _lo_de_los_telefonos(clave)
    if not filas:
        return None
    resumen = _juntar_por_telefono(filas)[clave]
    compras = sorted((f for f in filas if f["tipo"] == "compra"),
                     key=lambda f: (f["fecha"] or "", f["id"]), reverse=True)[:COMPRAS_EN_LA_FICHA]
    for compra in compras:
        c.execute("""SELECT cantidad, marca, codigo, descripcion FROM ventas_items
                     WHERE venta_id = ? ORDER BY id""", (compra["id"],))
        compra["items"] = [dict(i) for i in c.fetchall()]
    cuenta = next((m for m in c.execute(
        "SELECT id, nombre, telefono FROM mecanicos WHERE COALESCE(telefono, '') != ''")
                   if clave_del_telefono(m["telefono"]) == clave), None)
    chat = c.execute("SELECT id FROM chats WHERE canal = 'whatsapp' AND externo = ?",
                     (clave,)).fetchone()
    return {"resumen": resumen, "compras": compras,
            "espera": [f for f in filas if f["tipo"] == "espera" and f["estado"] == "activa"],
            "presupuestos": sorted((f for f in filas if f["tipo"] == "presupuesto"),
                                   key=lambda f: f["fecha"] or "", reverse=True)[:5],
            "autos": [f for f in filas if f["tipo"] == "auto"],
            "cuenta": dict(cuenta) if cuenta else None, "chat": chat["id"] if chat else None,
            "senas": [x for x in senas_activas() if clave_del_telefono(x["telefono"]) == clave],
            "whatsapp": link_de_whatsapp(resumen["telefono"])}


def usar_el_nombre_del_cliente(nombre):
    """«Usar ese nombre» en la venta (va como on_click)."""
    st.session_state["venta_cliente"] = nombre


def renglon_del_cliente(resumen):
    """«📇 Ya vino: Juan · 3 compras (\\$45.000) · espera 1 · AB123CD», para la pantalla (con el
    «$» escapado)."""
    partes = [f"📇 **Ya vino**: {texto_para_markdown(resumen['nombre'] or 'sin nombre')}"]
    if resumen["compras"]:
        partes.append(f"{miles(resumen['compras'])} compra(s) (\\${miles(resumen['comprado'], 0)})")
    if resumen["espera"]:
        partes.append(f"⏳ espera {miles(resumen['espera'])}")
    if resumen["presupuestos"]:
        partes.append(f"🧾 {miles(resumen['presupuestos'])} presupuesto(s) abierto(s)")
    if resumen["autos"]:
        partes.append("🚗 " + ", ".join(resumen["autos"][:3]))
    return " · ".join(partes)


def mostrar_la_ficha_del_cliente(telefono, donde):
    """La ficha de un cliente de mostrador (ver ficha_del_cliente()), en la agenda y en la venta.
    `donde` va en las claves de los botones: la misma ficha puede estar en los dos lados."""
    ficha = ficha_del_cliente(telefono)
    if not ficha:
        st.caption("Con ese teléfono no hay nada anotado todavía.")
        return
    r = ficha["resumen"]
    st.markdown(f"**📇 {texto_para_markdown(r['nombre'] or 'Sin nombre')}** · "
                f"{texto_para_markdown(r['telefono'])}"
                + (f" · la última vez, el {dia_y_mes_de_aca(r['ultima'])}" if r["ultima"]
                   else ""))
    _b1, _b2 = cols([1, 1], apilar_en_celular=False)
    _b1.link_button("📲 Escribirle por WhatsApp", ficha["whatsapp"], width="stretch")
    if ficha["chat"]:
        _b2.button("💬 Su chat", key=f"agenda_chat_{donde}_{r['clave']}", width="stretch",
                   on_click=abrir_el_chat, args=(ficha["chat"],))
    if ficha["cuenta"]:
        st.info(f"Es el teléfono de la cuenta **{texto_para_markdown(ficha['cuenta']['nombre'])}**"
                " (🗂️ Administrar → 💳 Cuentas corrientes).")
    if ficha["senas"]:
        st.markdown("**🔖 Señas que dejó**")
        for x in ficha["senas"]:
            st.markdown(f"- \\${miles(x['importe'], 0)} por {texto_para_markdown(x['que'])} "
                        f"(el {dia_y_mes_de_aca(x['fecha'])}, {x['forma_de_pago']})")
    if ficha["espera"]:
        st.markdown("**⏳ Lo que espera**")
        for e in ficha["espera"]:
            st.markdown(f"- {miles(e['cantidad'] or 1)}× "
                        f"{texto_para_markdown(e['codigo_buscado'] or '')} "
                        f"{texto_para_markdown((e['descripcion'] or '')[:50])}"
                        f" (desde el {dia_y_mes_de_aca(e['fecha'])})")
    if ficha["presupuestos"]:
        st.markdown("**🧾 Presupuestos**")
        for p in ficha["presupuestos"]:
            st.markdown(f"- {dia_y_mes_de_aca(p['fecha'])} · \\${miles(p['total'] or 0, 0)} · "
                        f"{ESTADOS_DEL_PRESUPUESTO.get(p['estado'], p['estado'])}")
    if ficha["autos"]:
        st.markdown("**🚗 Sus autos**")
        for a in ficha["autos"]:
            st.markdown(f"- **{texto_para_markdown(a['patente'])}** "
                        + texto_para_markdown(" ".join(str(x) for x in (
                            a["marca_auto"], a["modelo_auto"], a["anio"]) if x)))
    if ficha["compras"]:
        st.markdown(f"**🛒 Lo que compró** ({miles(r['compras'])} compra(s), "
                    f"\\${miles(r['comprado'], 0)} en total)")
        st.dataframe([{"Cuándo": dia_y_mes_de_aca(v["fecha"]), "#": v["id"],
                       "Qué": ", ".join(f"{i['cantidad']}× {i['marca'] or ''} {i['codigo'] or ''}"
                                        .strip() for i in v["items"]),
                       "Total": f"${miles(v['total'] or 0, 0)}"} for v in ficha["compras"]],
                     hide_index=True, width="stretch")


# LAS SEÑAS: el cliente encarga algo que no hay y deja una parte. Se anotaba en un papel o en el
# cuaderno: la plata entraba al cajón sin que el cierre lo supiera (el arqueo decía «Sobran»), y
# el día que retiraba nadie se acordaba de cuánto había dejado, o se le cobraba entero. Ahora:
#   · Se anota en 💵 Caja → «🔖 Señas» con quién, qué encargó (del catálogo o escrito), cuánto y
#     cómo pagó. Entra a la caja ese día, por esa forma de pago (ver cierre_de_caja()).
#   · Si es un producto del catálogo, queda también en lo que espera el cliente: cuando se carga
#     en «Entró mercadería» la app avisa para escribirle (ver «AVISARLE QUE LLEGÓ»). Y se puede
#     anotar como pedido al proveedor en el mismo paso.
#   · Al retirar, la venta ofrece descontarla (si lleva ese producto, o el teléfono es el de la
#     seña): la venta vale lo que vale, se cobra lo que falta, y el cierre de ese día cuenta solo
#     lo que falta (la seña ya había entrado). Anular la venta la vuelve a dejar esperando.
#   · Si no la retira, «↩️ Devolverla» la saca de la caja del día en que se devuelve.
SENA_MAXIMA = SALIDA_DE_CAJA_MAXIMA
# La seña que nadie retira ni se devuelve va a la campanita (ver diagnostico_de_salud()): es
# plata del cliente, y lo encargado quedó ocupando lugar.
DIAS_PARA_AVISAR_UNA_SENA = 30
ESTADOS_DE_LA_SENA = {"activa": "🔖 Esperando que retire", "usada": "✅ Descontada al retirar",
                      "reintegrada": "↩️ Devuelta"}


def anotar_sena(cliente, telefono, que, importe, forma_de_pago, producto_id=None,
                pedir_al_proveedor=False):
    """(ok, texto, id de la seña o None)."""
    exigir_nivel("empleado", "anotar una seña")
    cliente, telefono = str(cliente or "").strip()[:80], str(telefono or "").strip()[:40]
    if not cliente and not telefono:
        return False, "Poné el nombre o el teléfono: si no, después no sabés de quién es.", None
    producto = None
    if producto_id:
        producto = c.execute("""SELECT p.id, p.codigo_raw, p.descripcion, m.nombre AS marca
                                FROM productos p JOIN marcas m ON m.id = p.marca_id
                                WHERE p.id = ?""", (int(producto_id),)).fetchone()
        if not producto:
            return False, "Ese producto ya no está en el catálogo.", None
    que = (str(que or "").strip()
           or (f"{producto['marca']} {producto['codigo_raw']}" if producto else ""))[:120]
    if not que:
        return False, "Escribí qué encargó (o elegilo del catálogo).", None
    try:
        importe = round(float(importe), 2)
    except (TypeError, ValueError):
        return False, "Escribí cuánto dejó.", None
    if not importe > 0:
        return False, "La seña tiene que ser más que cero.", None
    if not importe <= SENA_MAXIMA:
        return False, f"¿${miles(importe, 0)} de seña? Revisá el número.", None
    if forma_de_pago not in FORMAS_DE_PAGO:
        return False, "Elegí cómo pagó la seña.", None
    usuario = obtener_usuario_actual()
    with db_lock, transaccion():
        consulta_id = None
        if producto:
            c.execute("""INSERT INTO consultas_cliente (cliente, telefono, producto_id,
                                                        codigo_buscado, descripcion, cantidad,
                                                        nota, atendio)
                         VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
                      (cliente or None, telefono or None, producto["id"], producto["codigo_raw"],
                       (producto["descripcion"] or "")[:120] or None,
                       f"Dejó ${miles(importe, 0)} de seña", usuario))
            consulta_id = c.lastrowid
        c.execute("""INSERT INTO senas (cliente, telefono, que, producto_id, consulta_id,
                                        importe, forma_de_pago, usuario)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                  (cliente or None, telefono or None, que, producto["id"] if producto else None,
                   consulta_id, importe, forma_de_pago, usuario))
        sena_id = c.lastrowid
        anotar_cambio("anotó una seña", "caja", sena_id,
                      despues={"importe": importe, "forma": forma_de_pago, "que": que})
    pedido = ""
    if producto and pedir_al_proveedor:
        anotados, ya = anotar_el_pedido_al_proveedor([(producto["id"], 1)])
        pedido = (" Quedó anotado como pedido al proveedor." if anotados else
                  " Ya estaba pedido al proveedor." if ya else "")
    return True, (f"🔖 Seña de ${miles(importe, 0)} ({forma_de_pago}) de {cliente or telefono} "
                  f"por {que}." + (" Cuando entre, la app avisa para escribirle." if producto
                                   else "") + pedido), sena_id


def senas_activas():
    """[dict] las que esperan que el cliente retire, la más vieja primero."""
    c.execute("""SELECT id, cliente, telefono, que, producto_id, importe, forma_de_pago,
                        usuario, fecha
                 FROM senas WHERE estado = 'activa' ORDER BY id""")
    return [dict(f) for f in c.fetchall()]


def senas_sin_retirar(dias=None):
    """Las que esperan hace más de `dias` (DIAS_PARA_AVISAR_UNA_SENA si no se dice) días."""
    hasta = (datetime.now() - timedelta(days=int(dias or DIAS_PARA_AVISAR_UNA_SENA))
             ).strftime("%Y-%m-%d %H:%M:%S")
    return [s for s in senas_activas() if (s["fecha"] or "") < hasta]


def senas_para_la_venta(producto_ids, telefono=""):
    """Las señas que se pueden descontar en esta venta: las de un producto que lleva, o las del
    mismo teléfono (ver clave_del_telefono())."""
    ids, clave = {int(p) for p in producto_ids or () if p}, clave_del_telefono(telefono)
    return [s for s in senas_activas()
            if (s["producto_id"] and s["producto_id"] in ids)
            or (clave and clave_del_telefono(s["telefono"]) == clave)]


def senas_del_dia(dia=None):
    """(las que se dejaron ese día, las que se devolvieron ese día): [dict] con importe,
    forma_de_pago y usuario (quien la recibió, o quien la devolvió). Ver cierre_de_caja()."""
    dia = dia or hoy_aca().isoformat()
    cobradas = [dict(f) for f in c.execute(
        """SELECT id, importe, forma_de_pago, usuario FROM senas
           WHERE date(fecha, '-3 hours') = ?""", (dia,))]
    devueltas = [dict(f) for f in c.execute(
        """SELECT id, importe, forma_de_pago, resuelta_por AS usuario FROM senas
           WHERE estado = 'reintegrada' AND date(resuelta_en, '-3 hours') = ?""", (dia,))]
    return cobradas, devueltas


def devolver_sena(sena_id):
    """No la va a retirar: se le devuelve y sale de la caja de hoy, por donde había entrado.
    (ok, texto)."""
    exigir_nivel("empleado", "devolver una seña")
    with db_lock, transaccion():
        fila = c.execute("SELECT importe, forma_de_pago, cliente, telefono, consulta_id "
                         "FROM senas WHERE id = ? AND estado = 'activa'", (int(sena_id),)
                         ).fetchone()
        if not fila:
            return False, "Esa seña ya no está esperando (¿se descontó o ya se devolvió?)."
        c.execute("""UPDATE senas SET estado = 'reintegrada', resuelta_en = datetime('now'),
                            resuelta_por = ? WHERE id = ?""",
                  (obtener_usuario_actual(), int(sena_id)))
        if fila["consulta_id"]:
            c.execute("""UPDATE consultas_cliente SET estado = 'cancelada',
                                fecha_cierre = datetime('now')
                         WHERE id = ? AND estado = 'activa'""", (fila["consulta_id"],))
        anotar_cambio("devolvió una seña", "caja", sena_id, antes={"importe": fila["importe"]})
    return True, (f"↩️ Seña devuelta a {fila['cliente'] or fila['telefono']}: "
                  f"${miles(fila['importe'], 0)} ({fila['forma_de_pago']}). Sale de la caja de "
                  "hoy.")


def anotar_sena_y_avisar():
    """«🔖 Anotar la seña» (va como on_click): lee los campos y, si se anotó, los vacía."""
    st_ = st.session_state
    producto_id = st_.get("sena_producto") if str(st_.get("sena_codigo") or "").strip() else None
    try:
        ok, texto, _ = anotar_sena(st_.get("sena_cliente"), st_.get("sena_telefono"),
                                   st_.get("sena_que"), st_.get("sena_importe"),
                                   st_.get("sena_forma"), producto_id,
                                   bool(st_.get("sena_pedir")))
    except PermissionError as _err:
        ok, texto = False, el_error_en_castellano(_err)
    if ok:
        for clave in ("sena_cliente", "sena_telefono", "sena_que", "sena_importe",
                      "sena_codigo", "sena_producto", "sena_pedir"):
            st_.pop(clave, None)
    avisar("success" if ok else "warning", texto)


def devolver_sena_y_avisar(sena_id):
    """«Sí, devolverla» (va como on_click)."""
    st.session_state.pop("sena_por_devolver", None)
    try:
        ok, texto = devolver_sena(sena_id)
    except PermissionError as _err:
        ok, texto = False, el_error_en_castellano(_err)
    avisar("success" if ok else "warning", texto)


# EL CIERRE DEL MES: el cierre de caja es de un día, y para el mes —lo que se le pasa al contador,
# lo que mira el dueño para decidir— había que sumar treinta cierres a mano, más las salidas y
# los arqueos. Junta los cierres de cada día del mes (los mismos números: devoluciones y señas
# incluidas), las salidas por tipo, los arqueos con sus diferencias por cajero (lo de los turnos de cada
# uno: ver «LOS TURNOS DE CAJA»), lo anulado, el mes anterior al lado, y cuándo se vende: por hora y
# por día de la semana, para decidir horarios y quién atiende. Para WhatsApp y en Excel, con una
# hoja por cosa. Solo el administrador.
NOMBRES_DE_LOS_DIAS_DE_LA_SEMANA = ("domingo", "lunes", "martes", "miércoles", "jueves",
                                    "viernes", "sábado")


def _dias_del_rango(desde, hasta):
    d, fin = date.fromisoformat(desde), date.fromisoformat(hasta)
    while d <= fin:
        yield d.isoformat()
        d += timedelta(days=1)


def cuando_se_vende(desde, hasta):
    """{por_hora: [(«09», ventas, total)], por_dia: [(«lunes», ventas, total)]} de las ventas sin
    anular entre dos días de acá, por la hora de acá en que se armaron."""
    filas = c.execute("""SELECT strftime('%H', fecha, '-3 hours') AS hora,
                                CAST(strftime('%w', fecha, '-3 hours') AS INTEGER) AS dia,
                                COUNT(*) AS ventas, COALESCE(SUM(total), 0) AS total
                         FROM ventas WHERE anulada = 0
                           AND date(fecha, '-3 hours') BETWEEN ? AND ?
                         GROUP BY hora, dia""", (desde, hasta)).fetchall()
    por_hora, por_dia = {}, {}
    for f in filas:
        h = por_hora.setdefault(f["hora"], [0, 0.0])
        h[0] += f["ventas"]
        h[1] += f["total"]
        d = por_dia.setdefault(f["dia"], [0, 0.0])
        d[0] += f["ventas"]
        d[1] += f["total"]
    # La semana desde el lunes, que es como se piensa en el mostrador.
    return {"por_hora": [(h, n, round(t, 2)) for h, (n, t) in sorted(por_hora.items())],
            "por_dia": [(NOMBRES_DE_LOS_DIAS_DE_LA_SEMANA[d], *(lambda x: (x[0], round(x[1], 2)))(
                por_dia[d])) for d in (1, 2, 3, 4, 5, 6, 0) if d in por_dia]}


def arqueos_por_cajero(desde, hasta):
    """[{Cajero, Arqueos, «Con diferencia», Faltó, Sobró}] por turnos (ver «LOS TURNOS DE CAJA»):
    a cada uno, lo que pasó en sus turnos de cada día; «Arqueos» son los días que contó. El que
    más faltó primero."""
    filas = c.execute("""SELECT dia, usuario, efectivo_contado - efectivo_esperado AS dif
                         FROM arqueos_de_caja WHERE dia BETWEEN ? AND ? ORDER BY dia, id""",
                      (desde, hasta)).fetchall()
    por_dia, anterior = {}, {}
    for f in filas:
        dif = round(float(f["dif"] or 0), 2)
        quien = f["usuario"] or "Sin decir"
        clave = (f["dia"], quien)
        por_dia[clave] = round(por_dia.get(clave, 0.0) + dif - anterior.get(f["dia"], 0.0), 2)
        anterior[f["dia"]] = dif
    cajeros = {}
    for (_dia, quien), dif in por_dia.items():
        k = cajeros.setdefault(quien, {"Cajero": quien, "Arqueos": 0, "Con diferencia": 0,
                                       "Con faltante": 0, "Faltó": 0.0, "Sobró": 0.0})
        k["Arqueos"] += 1
        k["Con diferencia"] += bool(dif)
        k["Con faltante"] += dif < 0
        k["Faltó" if dif < 0 else "Sobró"] = round(k["Faltó" if dif < 0 else "Sobró"]
                                                   + abs(dif), 2)
    return sorted(cajeros.values(), key=lambda k: (-k["Faltó"], k["Cajero"]))


# LOS GASTOS FIJOS Y LO QUE QUEDÓ: el cierre del mes decía lo que entró y la ganancia de lo
# vendido, pero no lo que quedó de verdad: faltaban el alquiler, la luz, los sueldos, el contador,
# que se pagan por fuera de la caja. Se anotan una vez (valen todos los meses hasta que se
# saquen) y el cierre resta, de la ganancia estimada, los gastos de la caja («🧾 Gasto» en las
# salidas) y los fijos. Lo que se paga desde el cajón va como salida, no como fijo: si no, se
# contaría dos veces. Cambiar un importe vale desde este mes; los anteriores no se mueven.
def mes_anterior(mes):
    anio, numero = (int(x) for x in str(mes).split("-")[:2])
    return f"{anio - (numero == 1):04d}-{(numero - 2) % 12 + 1:02d}"


def gastos_fijos_del_mes(mes=None):
    """[dict] id, concepto, importe, desde, hasta: los que valen ese mes (este, si no se dice)."""
    mes = mes or hoy_aca().strftime("%Y-%m")
    return [dict(f) for f in c.execute(
        """SELECT id, concepto, importe, desde, hasta FROM gastos_fijos
           WHERE desde <= ? AND (hasta IS NULL OR hasta >= ?) ORDER BY importe DESC, id""",
        (mes, mes))]


def _importe_del_gasto(importe):
    try:
        importe = round(float(importe), 2)
    except (TypeError, ValueError):
        raise ValueError("Escribí cuánto es por mes.")
    if not 0 < importe <= SALIDA_DE_CAJA_MAXIMA:
        raise ValueError("El gasto tiene que ser más que cero (y no disparatado).")
    return importe


def anotar_gasto_fijo(concepto, importe, mes=None):
    """Desde ese mes (este, si no se dice) en adelante. (ok, texto)."""
    exigir_nivel("admin", "anotar un gasto fijo")
    concepto = re.sub(r"\s+", " ", str(concepto or "")).strip()[:80]
    if not concepto:
        return False, "Escribí qué es (alquiler, luz, sueldos…)."
    try:
        importe = _importe_del_gasto(importe)
    except ValueError as e:
        return False, str(e)
    mes = mes or hoy_aca().strftime("%Y-%m")
    with db_lock:
        c.execute("INSERT INTO gastos_fijos (concepto, importe, desde, usuario) VALUES (?, ?, ?, ?)",
                  (concepto, importe, mes, obtener_usuario_actual()))
        anotar_cambio("anotó un gasto fijo", "configuración", c.lastrowid,
                      despues={"concepto": concepto, "importe": importe, "desde": mes})
        conn.commit()
    return True, f"💸 {concepto}: ${miles(importe, 0)} por mes, desde {nombre_del_mes(mes)}."


def cambiar_gasto_fijo(gasto_id, importe, mes=None):
    """El importe nuevo vale desde ese mes: el de antes queda para los meses anteriores. (ok,
    texto)."""
    exigir_nivel("admin", "cambiar un gasto fijo")
    try:
        importe = _importe_del_gasto(importe)
    except ValueError as e:
        return False, str(e)
    mes = mes or hoy_aca().strftime("%Y-%m")
    with db_lock, transaccion():
        g = c.execute("SELECT * FROM gastos_fijos WHERE id = ? AND (hasta IS NULL OR hasta >= ?)",
                      (int(gasto_id), mes)).fetchone()
        if not g:
            return False, "Ese gasto ya no está."
        if abs(float(g["importe"]) - importe) < 0.005:
            return False, "Ya era ese importe."
        if g["desde"] >= mes:
            c.execute("UPDATE gastos_fijos SET importe = ? WHERE id = ?", (importe, g["id"]))
        else:
            c.execute("UPDATE gastos_fijos SET hasta = ? WHERE id = ?", (mes_anterior(mes), g["id"]))
            c.execute("INSERT INTO gastos_fijos (concepto, importe, desde, hasta, usuario) "
                      "VALUES (?, ?, ?, ?, ?)",
                      (g["concepto"], importe, mes, g["hasta"], obtener_usuario_actual()))
        anotar_cambio("cambió un gasto fijo", "configuración", g["id"],
                      antes=float(g["importe"]), despues=importe)
    return True, f"💸 {g['concepto']}: ${miles(importe, 0)} por mes desde {nombre_del_mes(mes)}."


def sacar_gasto_fijo(gasto_id, mes=None):
    """Deja de contar desde ese mes (los anteriores lo siguen teniendo). (ok, texto)."""
    exigir_nivel("admin", "sacar un gasto fijo")
    mes = mes or hoy_aca().strftime("%Y-%m")
    with db_lock, transaccion():
        g = c.execute("SELECT * FROM gastos_fijos WHERE id = ? AND (hasta IS NULL OR hasta >= ?)",
                      (int(gasto_id), mes)).fetchone()
        if not g:
            return False, "Ese gasto ya no está."
        if g["desde"] >= mes:
            c.execute("DELETE FROM gastos_fijos WHERE id = ?", (g["id"],))
        else:
            c.execute("UPDATE gastos_fijos SET hasta = ? WHERE id = ?", (mes_anterior(mes), g["id"]))
        anotar_cambio("sacó un gasto fijo", "configuración", g["id"],
                      antes={"concepto": g["concepto"], "importe": g["importe"]})
    return True, f"💸 {g['concepto']}: ya no cuenta desde {nombre_del_mes(mes)}."


def anotar_gasto_fijo_y_avisar():
    """«➕ Anotar» de los gastos fijos (va como on_click): lee los campos y, si anotó, los vacía."""
    try:
        ok, texto = anotar_gasto_fijo(st.session_state.get("gasto_fijo_concepto"),
                                      st.session_state.get("gasto_fijo_importe"))
    except PermissionError as _err:
        ok, texto = False, el_error_en_castellano(_err)
    if ok:
        st.session_state.pop("gasto_fijo_concepto", None)
        st.session_state.pop("gasto_fijo_importe", None)
    avisar("success" if ok else "warning", texto)


def cambiar_gasto_fijo_y_avisar(gasto_id, clave_del_campo):
    """Al cambiar el importe de un gasto fijo (va como on_change)."""
    try:
        ok, texto = cambiar_gasto_fijo(gasto_id, st.session_state.get(clave_del_campo))
    except PermissionError as _err:
        ok, texto = False, el_error_en_castellano(_err)
    avisar("success" if ok else "warning", texto)


def sacar_gasto_fijo_y_avisar(gasto_id):
    """«🗑️» de un gasto fijo (va como on_click)."""
    try:
        ok, texto = sacar_gasto_fijo(gasto_id)
    except PermissionError as _err:
        ok, texto = False, el_error_en_castellano(_err)
    avisar("success" if ok else "warning", texto)


def cierre_del_mes(mes, hoy=None):
    """Todo lo del mes (el de ahora, hasta hoy): dict con desde, hasta, total, ventas, por_forma
    [(forma, total)], devuelto, señas (entraron, devueltas, descontadas), anuladas, ganancia e
    items_con_costo, salidas [(tipo, n, total)], arqueos (ver arqueos_por_cajero()), dias (los
    que vendieron), mejor_dia (día, total), anterior (el total del mes anterior) y cuando (ver
    cuando_se_vende())."""
    exigir_nivel("admin", "ver el cierre del mes")
    desde, hasta = rango_del_mes(mes, hoy)
    por_forma, por_dia = {}, {}
    suma = {k: 0.0 for k in ("total", "total_devuelto", "total_senas", "total_senas_devueltas",
                             "senas_descontadas", "total_anulado", "ganancia")}
    cuentas = {k: 0 for k in ("ventas", "anuladas", "items", "items_con_costo")}
    for dia in _dias_del_rango(desde, hasta):
        caja = cierre_de_caja(dia)
        for k in suma:
            suma[k] += caja[k]
        for k in cuentas:
            cuentas[k] += caja[k]
        for forma, _n, total in caja["por_forma"]:
            por_forma[forma] = por_forma.get(forma, 0.0) + total
        if caja["ventas"]:
            por_dia[dia] = caja["total"]
    salidas = [(f["tipo"] or "Sin decir", f["n"], round(float(f["total"]), 2)) for f in c.execute(
        """SELECT tipo, COUNT(*) AS n, SUM(importe) AS total FROM salidas_de_caja
           WHERE anulada = 0 AND dia BETWEEN ? AND ? GROUP BY tipo ORDER BY total DESC""",
        (desde, hasta))]
    anterior_hasta = date.fromisoformat(desde) - timedelta(days=1)
    anterior = round(sum(x["Vendido"] for x in ventas_por_vendedor(
        anterior_hasta.replace(day=1).isoformat(), anterior_hasta.isoformat())), 2)
    mejor = max(por_dia.items(), key=lambda x: x[1]) if por_dia else None
    # LO QUE QUEDÓ (ver «LOS GASTOS FIJOS Y LO QUE QUEDÓ»): la ganancia de lo vendido, menos los
    # gastos de la caja y los fijos del mes.
    gastos_fijos = gastos_fijos_del_mes(mes)
    total_fijos = round(sum(g["importe"] for g in gastos_fijos), 2)
    gastos_de_caja = round(sum(x for t, _n, x in salidas if t == TIPOS_DE_SALIDA_DE_CAJA[0]), 2)
    return {"mes": mes, "desde": desde, "hasta": hasta,
            "gastos_fijos": [(g["concepto"], g["importe"]) for g in gastos_fijos],
            "total_gastos_fijos": total_fijos, "gastos_de_caja": gastos_de_caja,
            "resultado": round(suma["ganancia"] - gastos_de_caja - total_fijos, 2),
            **{k: round(v, 2) for k, v in suma.items()}, **cuentas,
            "por_forma": sorted(((f, round(t, 2)) for f, t in por_forma.items() if round(t, 2)),
                                key=lambda x: -x[1]),
            "salidas": salidas, "total_salidas": round(sum(x[2] for x in salidas), 2),
            "arqueos": arqueos_por_cajero(desde, hasta), "dias": len(por_dia),
            "mejor_dia": mejor, "anterior": anterior,
            "cuando": cuando_se_vende(desde, hasta)}


def texto_del_cierre_del_mes(cierre, con_ganancia=False):
    """El cierre del mes para mandar por WhatsApp."""
    plata = lambda x: f"${miles(x, 0)}"
    r = [f"📅 Cierre de {nombre_del_mes(cierre['mes'])} — El Chavo"
         + (f" (hasta el {cierre['hasta'][8:10]}/{cierre['hasta'][5:7]})"
            if cierre["hasta"] < rango_del_mes(cierre["mes"], date(2100, 1, 1))[1] else ""),
         f"💵 Entró: {plata(cierre['total'])} en {miles(cierre['ventas'])} venta(s), "
         f"{miles(cierre['dias'])} día(s) con ventas"]
    r += [f"   · {forma}: {plata(total)}" for forma, total in cierre["por_forma"]]
    if cierre["anterior"]:
        r.append(f"📈 Mes anterior (vendido): {plata(cierre['anterior'])}")
    if cierre["mejor_dia"]:
        d, t = cierre["mejor_dia"]
        r.append(f"🏅 Mejor día: {d[8:10]}/{d[5:7]} con {plata(t)}")
    if con_ganancia and cierre["items_con_costo"]:
        r.append(f"💰 Ganancia estimada: {plata(cierre['ganancia'])} (de lo que tiene costo)")
        if cierre["total_gastos_fijos"] or cierre["gastos_de_caja"]:
            r.append(f"💸 Gastos: {plata(cierre['gastos_de_caja'])} de la caja y "
                     f"{plata(cierre['total_gastos_fijos'])} fijos")
            r.append(f"🧾 Lo que quedó: {plata(cierre['resultado'])}")
    if cierre["total_devuelto"]:
        r.append(f"↩️ Devuelto: {plata(cierre['total_devuelto'])}")
    if cierre["total_senas"] or cierre["senas_descontadas"]:
        r.append(f"🔖 Señas: entraron {plata(cierre['total_senas'])}, descontadas al retirar "
                 f"{plata(cierre['senas_descontadas'])}")
    if cierre["salidas"]:
        r.append(f"💸 Salidas de caja: {plata(cierre['total_salidas'])} ("
                 + ", ".join(f"{t}: {plata(x)}" for t, _n, x in cierre["salidas"]) + ")")
    if cierre["anuladas"]:
        r.append(f"🚫 Anuladas: {miles(cierre['anuladas'])} ({plata(cierre['total_anulado'])})")
    faltas = [a for a in cierre["arqueos"] if a["Faltó"] or a["Sobró"]]
    if faltas:
        r.append("🧮 Arqueos: " + " · ".join(
            f"{a['Cajero']}: " + ", ".join(x for x in (
                f"faltó {plata(a['Faltó'])}" if a["Faltó"] else "",
                f"sobró {plata(a['Sobró'])}" if a["Sobró"] else "") if x) for a in faltas))
    return "\n".join(r)


def excel_del_cierre_del_mes(mes, hoy=None, con_ganancia=False):
    """Los datos del Excel del mes, leídos ahora: {hoja: [dict]} para excel_de_varias_hojas()
    (Resumen, Ventas, Salidas, Señas, Arqueos y Devoluciones)."""
    cierre = cierre_del_mes(mes, hoy)
    desde, hasta = cierre["desde"], cierre["hasta"]
    resumen = [{"Qué": a, "Cuánto": b} for a, b in (
        [("Entró (total)", cierre["total"]), ("Ventas", cierre["ventas"])]
        + [(f"Por {f}", t) for f, t in cierre["por_forma"]]
        + [("Devuelto", cierre["total_devuelto"]), ("Señas que entraron", cierre["total_senas"]),
           ("Señas descontadas al retirar", cierre["senas_descontadas"]),
           ("Señas devueltas", cierre["total_senas_devueltas"]),
           ("Salidas de caja", cierre["total_salidas"]), ("Anuladas", cierre["anuladas"]),
           ("Mes anterior (vendido)", cierre["anterior"])]
        + ([("Ganancia estimada (de lo que tiene costo)", cierre["ganancia"]),
            ("Gastos de la caja", cierre["gastos_de_caja"]),
            ("Gastos fijos", cierre["total_gastos_fijos"]),
            ("Lo que quedó", cierre["resultado"])] if con_ganancia else []))]
    ventas = [{"Día": dia_de_aca(f["cuando"]), "#": f["id"], "Vendió": f["usuario"] or "",
               "Cliente": f["cliente"] or f["cuenta"] or "", "Pago": f["forma_de_pago"] or "",
               "Cuotas": f["cuotas"] or 1, "Descuento %": f["descuento"] or 0,
               "Recargo %": f["recargo"] or 0, "Seña": f["sena"] or 0, "Total": f["total"] or 0,
               "Anulada": "sí" if f["anulada"] else ""}
              for f in c.execute(
                  """SELECT v.id, COALESCE(v.cobrada_en, v.fecha) AS cuando, v.usuario, v.cliente,
                            k.nombre AS cuenta, v.forma_de_pago, v.cuotas, v.descuento,
                            v.recargo, v.sena, v.total, v.anulada
                     FROM ventas v LEFT JOIN mecanicos k ON k.id = v.mecanico_id
                     WHERE COALESCE(v.cobrada, 1) = 1
                       AND date(COALESCE(v.cobrada_en, v.fecha), '-3 hours') BETWEEN ? AND ?
                     ORDER BY v.id""", (desde, hasta))]
    salidas = [{"Día": f["dia"], "Tipo": f["tipo"] or "", "En qué": f["concepto"] or "",
                "Importe": f["importe"], "Quién": f["usuario"] or "",
                "Anulada": "sí" if f["anulada"] else ""} for f in c.execute(
        "SELECT * FROM salidas_de_caja WHERE dia BETWEEN ? AND ? ORDER BY id", (desde, hasta))]
    senas = [{"Día": dia_de_aca(f["fecha"]), "Cliente": f["cliente"] or f["telefono"] or "",
              "Qué": f["que"], "Importe": f["importe"], "Pago": f["forma_de_pago"],
              "Estado": ESTADOS_DE_LA_SENA.get(f["estado"], f["estado"]),
              "Venta": f["venta_id"] or ""} for f in c.execute(
        """SELECT * FROM senas WHERE date(fecha, '-3 hours') BETWEEN ? AND ?
              OR date(resuelta_en, '-3 hours') BETWEEN ? AND ? ORDER BY id""",
        (desde, hasta, desde, hasta))]
    arqueos = [{"Día": f["dia"], "Esperado": f["efectivo_esperado"],
                "Contado": f["efectivo_contado"],
                "Diferencia": round((f["efectivo_contado"] or 0) - (f["efectivo_esperado"] or 0),
                                    2), "Nota": f["nota"] or "", "Quién": f["usuario"] or ""}
               for f in c.execute("SELECT * FROM arqueos_de_caja WHERE dia BETWEEN ? AND ? "
                                  "ORDER BY id", (desde, hasta))]
    devoluciones = [{"Día": dia, "De la venta": d["venta_id"],
                     "Qué": f"{d['cantidad']}× {d['marca']} {d['codigo']}",
                     "Importe": d["importe"], "Pago": d["forma_de_pago"] or "",
                     "Quién": d["usuario"] or ""}
                    for dia in _dias_del_rango(desde, hasta) for d in devoluciones_del_dia(dia)]
    return {"Resumen": resumen, "Ventas": ventas, "Salidas": salidas, "Señas": senas,
            "Arqueos": arqueos, "Devoluciones": devoluciones,
            "Gastos fijos": [{"Qué": g, "Por mes": x} for g, x in cierre["gastos_fijos"]]}


def cierre_del_mes_para_descargar(mes, con_ganancia=False):
    """Para el botón de descarga: los datos se leen ahora; el Excel se arma al tocarlo."""
    hojas = excel_del_cierre_del_mes(mes, con_ganancia=con_ganancia)
    return lambda: excel_de_varias_hojas(hojas)


# LO QUE SE LE DEBE A CADA PROVEEDOR: la app sabía lo que te deben los talleres, pero no lo que
# vos le debés a cada proveedor: las facturas de compra estaban en una carpeta y el vencimiento,
# en la cabeza de alguien (o se pagaba tarde, con recargo, o dos veces). Se anota la factura con
# su vencimiento (si no se dice, a los DIAS_DE_PLAZO_DE_UN_PROVEEDOR) y lo que se le paga; los
# pagos van a lo más viejo, como en las cuentas de los talleres. El pago en efectivo sale del
# cajón: queda también como salida de caja «🚚 Pago a un proveedor», así el arqueo lo descuenta
# sin anotarlo dos veces. La campanita avisa lo vencido y lo que vence en
# DIAS_PARA_AVISAR_UNA_FACTURA días. Lo anota el administrador.
DIAS_DE_PLAZO_DE_UN_PROVEEDOR = 30
DIAS_PARA_AVISAR_UNA_FACTURA = 3
MEDIOS_DE_PAGO_A_PROVEEDOR = ("💵 Efectivo de la caja", "🏦 Transferencia", "🧾 Cheque propio",
                              "Otro")


def nombre_de_proveedor(texto):
    """«  distribuidora  norte » → «DISTRIBUIDORA NORTE»: el mismo proveedor escrito de dos
    maneras no queda como dos cuentas."""
    return re.sub(r"\s+", " ", str(texto or "")).strip().upper()[:80]


def proveedores_conocidos():
    """Los que ya tienen facturas o pagos, y las marcas de las listas: para elegir sin escribir."""
    nombres = {f[0] for f in c.execute("SELECT proveedor FROM facturas_de_proveedores "
                                       "UNION SELECT proveedor FROM pagos_a_proveedores")}
    nombres |= {nombre_de_proveedor(f[0]) for f in c.execute(
        "SELECT nombre FROM marcas WHERE tipo = 'PROVEEDOR'")}
    return sorted(n for n in nombres if n)


def _fecha_iso(valor, por_defecto):
    if not valor:
        return por_defecto
    if isinstance(valor, date):
        return valor.isoformat()
    return date.fromisoformat(str(valor)[:10]).isoformat()


def anotar_factura_de_proveedor(proveedor, importe, vence=None, numero="", fecha=None, nota=""):
    """(ok, texto)."""
    exigir_nivel("admin", "anotar una factura de un proveedor")
    proveedor = nombre_de_proveedor(proveedor)
    if not proveedor:
        return False, "Elegí o escribí el proveedor."
    try:
        importe = round(float(importe), 2)
    except (TypeError, ValueError):
        return False, "Escribí el importe de la factura."
    if not 0 < importe <= SALIDA_DE_CAJA_MAXIMA:
        return False, "El importe tiene que ser más que cero (y no disparatado)."
    try:
        fecha = _fecha_iso(fecha, hoy_aca().isoformat())
        vence = _fecha_iso(vence, (date.fromisoformat(fecha)
                                   + timedelta(days=DIAS_DE_PLAZO_DE_UN_PROVEEDOR)).isoformat())
    except ValueError:
        return False, "La fecha no se entiende."
    if vence < fecha:
        return False, "Vence antes de la fecha de la factura: revisalo."
    with db_lock:
        c.execute("""INSERT INTO facturas_de_proveedores (proveedor, numero, fecha, vence, importe,
                                                          nota, usuario)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (proveedor, str(numero or "").strip()[:40] or None, fecha, vence, importe,
                   str(nota or "").strip()[:200] or None, obtener_usuario_actual()))
        anotar_cambio("anotó una factura de un proveedor", "proveedor", c.lastrowid,
                      despues={"proveedor": proveedor, "importe": importe, "vence": vence})
        conn.commit()
    return True, (f"🧾 Factura de {proveedor} por ${miles(importe, 0)}, vence el "
                  f"{vence[8:10]}/{vence[5:7]}/{vence[:4]}.")


def anotar_pago_a_proveedor(proveedor, importe, medio, nota=""):
    """(ok, texto). El de «💵 Efectivo de la caja» es también una salida de caja de hoy."""
    exigir_nivel("admin", "anotar un pago a un proveedor")
    proveedor = nombre_de_proveedor(proveedor)
    if not proveedor:
        return False, "Elegí el proveedor."
    try:
        importe = round(float(importe), 2)
    except (TypeError, ValueError):
        return False, "Escribí cuánto le pagaste."
    if not 0 < importe <= SALIDA_DE_CAJA_MAXIMA:
        return False, "El importe tiene que ser más que cero (y no disparatado)."
    if medio not in MEDIOS_DE_PAGO_A_PROVEEDOR:
        return False, "Elegí cómo le pagaste."
    nota = str(nota or "").strip()[:200]
    dia, usuario = hoy_aca().isoformat(), obtener_usuario_actual()
    with db_lock, transaccion():
        salida_id = None
        if medio == MEDIOS_DE_PAGO_A_PROVEEDOR[0]:
            c.execute("INSERT INTO salidas_de_caja (dia, tipo, concepto, importe, usuario) "
                      "VALUES (?, ?, ?, ?, ?)",
                      (dia, TIPOS_DE_SALIDA_DE_CAJA[1],
                       f"{proveedor}" + (f": {nota}" if nota else ""), importe, usuario))
            salida_id = c.lastrowid
            anotar_cambio("salida de caja", "caja", salida_id, despues=importe,
                          detalle=f"{TIPOS_DE_SALIDA_DE_CAJA[1]}: {proveedor}")
        c.execute("""INSERT INTO pagos_a_proveedores (proveedor, importe, medio, dia, nota,
                                                      salida_id, usuario)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (proveedor, importe, medio, dia, nota or None, salida_id, usuario))
        anotar_cambio("anotó un pago a un proveedor", "proveedor", c.lastrowid,
                      despues={"proveedor": proveedor, "importe": importe, "medio": medio})
    return True, (f"💸 Pago a {proveedor}: ${miles(importe, 0)} ({medio})"
                  + (" — salió del cajón." if salida_id else "."))


def anular_movimiento_de_proveedor(tipo, movimiento_id):
    """`tipo`: «factura» o «pago». No se borra: queda anulado. Un pago en efectivo anula también
    su salida de caja. (ok, texto)."""
    exigir_nivel("admin", "anular algo de un proveedor")
    with db_lock, transaccion():
        if tipo == "factura":
            c.execute("UPDATE facturas_de_proveedores SET anulada = 1 WHERE id = ? AND anulada = 0",
                      (int(movimiento_id),))
        elif tipo == "pago":
            fila = c.execute("SELECT salida_id FROM pagos_a_proveedores WHERE id = ? AND anulado = 0",
                             (int(movimiento_id),)).fetchone()
            c.execute("UPDATE pagos_a_proveedores SET anulado = 1 WHERE id = ? AND anulado = 0",
                      (int(movimiento_id),))
            if c.rowcount == 1 and fila and fila["salida_id"]:
                c.execute("UPDATE salidas_de_caja SET anulada = 1, anulada_por = ? WHERE id = ?",
                          (obtener_usuario_actual(), fila["salida_id"]))
        else:
            return False, "No sé qué anular."
        if c.rowcount != 1:
            return False, "Eso ya estaba anulado."
        anotar_cambio(f"anuló {'una factura' if tipo == 'factura' else 'un pago'} de un proveedor",
                      "proveedor", movimiento_id)
    return True, "🚫 Anulado."


def cuentas_con_proveedores(hoy=None):
    """[{proveedor, debe, vencido, proximo (el vencimiento más cercano de lo que queda), abiertas
    (facturas con algo sin pagar)}], con lo pagado imputado a lo que vence primero. Lo vencido
    primero; los que no deben nada, no."""
    hoy = (hoy or hoy_aca()).isoformat()
    pagado = {f["proveedor"]: float(f["total"]) for f in c.execute(
        "SELECT proveedor, SUM(importe) AS total FROM pagos_a_proveedores WHERE anulado = 0 "
        "GROUP BY proveedor")}
    cuentas = {}
    for f in c.execute("SELECT proveedor, vence, importe FROM facturas_de_proveedores "
                       "WHERE anulada = 0 ORDER BY proveedor, vence, id"):
        k = cuentas.setdefault(f["proveedor"], {"proveedor": f["proveedor"], "debe": 0.0,
                                                "vencido": 0.0, "proximo": None, "abiertas": 0,
                                                "_resto": pagado.get(f["proveedor"], 0.0)})
        importe = float(f["importe"])
        cubierto = min(importe, k["_resto"])
        k["_resto"] -= cubierto
        queda = round(importe - cubierto, 2)
        if queda > 0:
            k["abiertas"] += 1
            if f["vence"] < hoy:
                k["vencido"] = round(k["vencido"] + queda, 2)
            if k["proximo"] is None:
                k["proximo"] = f["vence"]
    for proveedor, total in pagado.items():
        cuentas.setdefault(proveedor, {"proveedor": proveedor, "debe": 0.0, "vencido": 0.0,
                                       "proximo": None, "abiertas": 0, "_resto": total})
    salida = []
    for k in cuentas.values():
        facturado = sum(float(f[0]) for f in c.execute(
            "SELECT importe FROM facturas_de_proveedores WHERE anulada = 0 AND proveedor = ?",
            (k["proveedor"],)))
        k["debe"] = round(facturado - pagado.get(k["proveedor"], 0.0), 2)
        k.pop("_resto", None)
        if abs(k["debe"]) >= 0.01:
            salida.append(k)
    return sorted(salida, key=lambda k: (-k["vencido"], k["proximo"] or "9999", -k["debe"]))


def facturas_para_avisar(hoy=None, dias=None):
    """Las cuentas con algo vencido o que vence en `dias` (DIAS_PARA_AVISAR_UNA_FACTURA)."""
    hoy = hoy or hoy_aca()
    limite = (hoy + timedelta(days=int(dias if dias is not None
                                       else DIAS_PARA_AVISAR_UNA_FACTURA))).isoformat()
    return [k for k in cuentas_con_proveedores(hoy)
            if k["vencido"] or (k["proximo"] and k["proximo"] <= limite)]


def movimientos_con_el_proveedor(proveedor):
    """[dict] las facturas y los pagos de un proveedor, en orden, con el saldo después de cada
    uno: tipo, id, dia, que, importe (la factura suma, el pago resta), saldo, anulado."""
    proveedor = nombre_de_proveedor(proveedor)
    filas = [{"tipo": "factura", "id": f["id"], "dia": f["fecha"] or "",
              "que": f"Factura {f['numero'] or ''}".strip() + f" (vence {f['vence'][8:10]}/"
                     f"{f['vence'][5:7]})", "importe": float(f["importe"]),
              "anulado": bool(f["anulada"]), "orden": f["creada"]}
             for f in c.execute("SELECT * FROM facturas_de_proveedores WHERE proveedor = ?",
                                (proveedor,))]
    filas += [{"tipo": "pago", "id": f["id"], "dia": f["dia"] or "",
               "que": f"Pago ({f['medio']})" + (f": {f['nota']}" if f["nota"] else ""),
               "importe": -float(f["importe"]), "anulado": bool(f["anulado"]),
               "orden": f["creado"]}
              for f in c.execute("SELECT * FROM pagos_a_proveedores WHERE proveedor = ?",
                                 (proveedor,))]
    filas.sort(key=lambda f: (f["dia"], f["orden"] or "", f["tipo"] != "factura", f["id"]))
    saldo = 0.0
    for f in filas:
        if not f["anulado"]:
            saldo = round(saldo + f["importe"], 2)
        f["saldo"] = saldo
    return filas


def anotar_factura_y_avisar():
    """«🧾 Anotar la factura» (va como on_click): lee los campos y, si anotó, los vacía."""
    st_ = st.session_state
    try:
        ok, texto = anotar_factura_de_proveedor(st_.get("prov_factura_proveedor"),
                                                st_.get("prov_factura_importe"),
                                                st_.get("prov_factura_vence"),
                                                st_.get("prov_factura_numero"),
                                                st_.get("prov_factura_fecha"),
                                                st_.get("prov_factura_nota"))
    except PermissionError as _err:
        ok, texto = False, el_error_en_castellano(_err)
    if ok:
        for clave in ("prov_factura_importe", "prov_factura_numero", "prov_factura_nota"):
            st_.pop(clave, None)
    avisar("success" if ok else "warning", texto)


def anotar_pago_a_proveedor_y_avisar():
    """«💸 Anotar el pago» (va como on_click)."""
    st_ = st.session_state
    try:
        ok, texto = anotar_pago_a_proveedor(st_.get("prov_pago_proveedor"),
                                            st_.get("prov_pago_importe"),
                                            st_.get("prov_pago_medio"), st_.get("prov_pago_nota"))
    except PermissionError as _err:
        ok, texto = False, el_error_en_castellano(_err)
    if ok:
        for clave in ("prov_pago_importe", "prov_pago_nota"):
            st_.pop(clave, None)
    avisar("success" if ok else "warning", texto)


def anular_de_proveedor_y_avisar(tipo, movimiento_id):
    """«🚫» de una factura o un pago (va como on_click)."""
    try:
        ok, texto = anular_movimiento_de_proveedor(tipo, movimiento_id)
    except PermissionError as _err:
        ok, texto = False, el_error_en_castellano(_err)
    avisar("success" if ok else "warning", texto)

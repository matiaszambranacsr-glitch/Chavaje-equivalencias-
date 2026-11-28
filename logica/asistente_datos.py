"""Los datos del momento que contesta el asistente: ver «LO QUE PASA AHORA» abajo. Corre en el
mismo espacio de nombres que los otros archivos de logica/ (ver orden.py)."""

# ============================================================================================
# LO QUE PASA AHORA: LOS DATOS DEL MOMENTO, SOLO PARA QUIEN LOS VE EN SU PANTALLA
# ============================================================================================
# El dueño pidió un asistente «más inteligente, pero que siga sin ser una brecha de seguridad».
# Hasta acá explicaba, llevaba y buscaba: de lo que estaba pasando no sabía nada. Ahora contesta
# un puñado de preguntas con datos —cuánto se vendió, qué falta cobrar, qué espera el depósito,
# cuánto debe una cuenta, qué hay pendiente, qué chats hay sin leer (de quién, nunca lo que
# escribieron); al taller, cuánto debe y qué les toca a sus autos— con estas reglas, que son
# las que lo mantienen cerrado:
#  · Un grupo CERRADO de preguntas, cada una con su función de siempre (la misma que dibuja la
#    pantalla, así dice lo mismo que ella). Lo escrito solo elige cuál de estas preguntas es; con
#    lo escrito no se arma ninguna consulta. El nombre de una cuenta se busca con
#    buscar_cuentas(), en Python, entre las cuentas.
#  · Cada una está atada a la PANTALLA de donde sale el dato: si quien pregunta no la tiene en
#    su barra, no se le contesta con datos. El invitado no tiene ninguna; el del depósito, solo
#    lo del depósito; el taller, solo lo de SU cuenta (con exigir_que_sea_su_cuenta() adentro).
#  · Solo lee. No cobra, no manda, no cambia nada.
#  · Lo que sale de la base va escapado: un nombre con asteriscos o corchetes no arma negritas
#    ni links.
#  · Lo controla pruebas/pruebas_del_asistente.py: mirando este archivo, que solo llame a las
#    funciones de FUNCIONES_QUE_PUEDE_USAR, que no nombre la base, los secretos ni internet y
#    que no escriba en la sesión; y preguntando lo mismo con cada rol.
# Las únicas funciones de la app que usan estas respuestas: todas leen, ninguna cambia nada.
FUNCIONES_QUE_PUEDE_USAR = (
    "resumen_de_la_caja", "ventas_a_cobrar", "pedidos_pendientes", "pendientes_por_pedido",
    "buscar_cuentas", "estado_de_cuenta", "resumen_de_cuentas", "avisos_por_cliente",
    "autos_del_taller", "chats_sin_leer", "cuentas_para_recordar", "garantias", "hoy_aca",
    "miles", "texto_para_markdown", "presupuestos_para_seguir", "pedidos_sin_llegar",
    "cuentas_que_dejaron_de_venir", "avance_del_objetivo", "renglon_del_objetivo",
    "senas_activas", "senas_sin_retirar", "cheques_sin_depositar", "cuentas_con_proveedores",
    "facturas_para_avisar",
)
_DATO_VENTAS = re.compile(
    r"\bcuanto (se )?(vendi\w*|vend[ie]mos|vendio|recaud\w*|facturamos|hicimos|entro|hay en (la )?caja)\b"
    r"|\b(ventas?|caja|recaudacion) (de|del) (hoy|ayer|dia)\b"
    r"|\bcomo (va|viene|vamos|anda|fue|estuvo) (el dia|la caja|hoy|ayer)\b"
    r"|\b(vendimos|vendi|se vendio) (hoy|ayer)\b")
_POR_VENDEDOR = re.compile(r"\b(vendedor\w*|empleado\w*|cada uno|comision\w*)\b")
# «¿Cómo vamos con el objetivo?»: el número de la barra de la caja (ver «EL OBJETIVO DEL MES»).
# «Cómo pongo una meta» no: eso es la ficha de cómo se hace.
_DATO_OBJETIVO = re.compile(
    r"\b(como (vamos|va|venimos|viene|estamos|andamos)|cuanto (falta|nos falta|llevamos|va|"
    r"vamos))\b.{0,25}\b(objetivo|meta)\b|^(y )?(el )?(objetivo|meta)( del mes)?$")
# «¿Qué señas hay?», «¿cuántas señas sin retirar?». No «¿cómo anoto una seña?» (la ficha) ni
# «¿qué es una seña?»: van en plural o con lo que se pregunta pegado.
_DATO_SENAS = re.compile(
    r"\b(que|cuantas|cuales) senas\b|\bhay senas\b|\bplata (hay )?en senas\b"
    r"|\bsenas (activas|sin retirar|pendientes|que hay|que esperan)\b|^(y )?(las )?senas$")
# «¿Qué cheques hay para depositar?». No «¿cómo cargo un pago con cheque?» ni «ver los cheques
# para depositar» (las fichas: lo segundo es el título de una).
_DATO_CHEQUES = re.compile(
    r"^(que|cuantos|cuales|hay|tengo|tenemos)\b.{0,25}\bcheques\b"
    r"|^(y )?(los )?cheques( para depositar| sin depositar)?$")
# «¿Cuánto les debo a los proveedores?», «¿qué hay que pagarle a los proveedores?». No «¿cómo
# anoto un pago a un proveedor?» ni «lo que le debés a un proveedor» (el título de la ficha).
_DATO_PROVEEDORES = re.compile(
    r"\b(cuanto|que)\b.{0,25}\b(debo|debemos|pagar|pagarle|pagarles|vence|vencen)\b"
    r".{0,25}\bproveedor\w*|\bproveedor\w*\b.{0,20}\b(para pagar|a pagar|por pagar|vencid\w*)\b"
    r"|\bdeuda con (los |el )?proveedor\w*")
_DATO_Y_AYER = re.compile(r"^(y )?(ayer|el de ayer|y el de ayer)$")
_DATO_A_COBRAR = re.compile(
    r"\b(que|cuanto|cuantas|hay)\b.{0,20}\b(falta|faltan|espera|esperan|queda|quedan)\b.{0,15}"
    r"\bcobrar\b|\bsin cobrar\b|\b(ventas|cuanto|que hay) (a|por|para) cobrar\b")
_DATO_DEPOSITO = re.compile(
    r"\b(cuantos?|que hay|hay algo|hay|que (espera|falta|queda))\b.{0,25}\b(pedidos?|pendientes?|"
    r"para buscar|por buscar)\b.{0,20}\bdeposito\b|\bpedidos? pendientes?\b"
    r"|\b(que|cuanto) (hay|espera|falta) en el deposito\b"
    r"|\b(que|cuales|cuantos?) pedidos?\b.{0,25}\bdeposito\b"
    r"|\bhay (algo|pedidos?) (en|para|del) (el )?deposito\b")
_DATO_CUENTA = re.compile(
    r"^(cuanto|que) (nos )?(debe|adeuda|tiene de saldo)\s+(el |la |los |las )?(?P<quien>.+)$"
    r"|^(saldo|deuda|la cuenta) (de|del)\s+(?P<quien2>.+)$")
_DATO_MI_DEUDA = re.compile(
    r"\b(cuanto|que) (debo|tengo que pagar|le debo|les debo)\b|\bmi (saldo|deuda)\b"
    r"|\bcuanto (tengo|me queda) (disponible|de credito)\b")
_DATO_MIS_AUTOS = re.compile(
    r"\b(que|a que|a cuales?|cuales?)\b.{0,15}\b(autos?|coches?)\b.{0,25}\b(toca|tocan|vence|vencen|"
    r"vencid\w*|service|cambio)\b")
# «¿Hay mensajes sin leer?», «¿llegó algún mensaje?», «¿quién escribió?». No «¿cómo mando un
# WhatsApp?» ni «¿cómo contesto un mensaje?»: eso es explicar, y lo hacen las fichas.
_DATO_MENSAJES = re.compile(
    r"\b(mensajes?|chats?|whatsapps?|wasaps?)\b.{0,20}\b(sin leer|sin abrir|nuevos?|sin contestar|"
    r"sin responder|pendientes?)\b"
    r"|\b(hay|tenemos|tengo|llego|llegaron|entro|entraron)\b( algun| algunos| nuevos?)? "
    r"(mensajes?|chats?)\b"
    r"|\b(quien|alguien) (me |nos )?(escribio|escribieron|mando un mensaje)\b")
_DATO_PENDIENTE = re.compile(
    r"\b(que|algo) (tengo|hay|queda|quedo) (pendiente|para hacer|por hacer|que hacer)\b"
    r"|^(pendientes?|resumen del dia|como estamos|que hay para hoy)$|\bresumen del dia\b")


# Las pantallas de donde sale cada dato, por su nombre y no por su lugar en PAGINAS: el lugar no
# es el de la barra («_DEPOSITO» es 📁 Cargar Excel, no 📦 Depósito), y con el número se ataba
# el dato a otra pantalla sin que se notara.
_CAJA, _DEPOSITO, _ADMINISTRAR, _VEHICULOS = "💵 Caja", "📦 Depósito", "🗂️ Administrar", "🚗 Vehículos"
_MENSAJES = "💬 Mensajes"
_DEVOLUCIONES = "↩️ Devoluciones"
_BUSCADOR = "🔍 Buscador"
_ESTADISTICAS = "📊 Estadísticas"


def _asis_nombre(texto):
    """Un texto de la base, listo para la respuesta: sin formato de markdown (asteriscos,
    corchetes) ni fórmulas (dos «$»)."""
    return _asis_escapar(texto_para_markdown(texto))


def _asis_dato(texto, botones, nombre):
    """La respuesta de un dato: como las otras, con el nombre «dato:…» para lo que sigue
    («¿y ayer?»)."""
    return {**_asis_simple(texto, botones), "ficha": f"dato:{nombre}"}


def _asis_ir_a(pagina, contexto):
    """El botón para ir a la pantalla del dato, si quien pregunta la tiene."""
    if pagina in contexto["visibles"] and pagina != contexto.get("pagina"):
        return [(f"➡️ Llevame a {pagina}", "ir", f"pantalla:{pagina}")]
    return []


def _asis_plata(numero):
    return f"\\${miles(numero or 0, 0)}"


def _dato_de_las_ventas(contexto, ayer=False):
    dia = (hoy_aca() - timedelta(days=1)).isoformat() if ayer else None
    r = resumen_de_la_caja(dia)
    cobrado = r["efectivo"] + r["otros_medios"]
    partes = [f"**{'Ayer' if ayer else 'Hoy'}**: {miles(r['ventas'])} venta(s); entraron "
              f"**{_asis_plata(cobrado)}** ({_asis_plata(r['efectivo'])} en efectivo y "
              f"{_asis_plata(r['otros_medios'])} con tarjeta o transferencia)"]
    if r["a_cuenta"]:
        partes.append(f"a cuenta, {_asis_plata(r['a_cuenta'])}")
    if not ayer and r["esperando"]:
        partes.append(f"y esperan en la caja {miles(r['esperando'])} por "
                      f"{_asis_plata(r['total_esperando'])}")
    texto = "; ".join(partes) + "."
    if not ayer:
        texto += " (Preguntame «¿y ayer?».)"
    # Y cómo verlo en detalle: el cierre de caja, si lo tiene.
    cierre = fichas_del_asistente()["por_nombre"].get("como:cierre")
    botones = _asis_ir_a(_CAJA, contexto) + (
        [("📋 El cierre de caja", "ver", "como:cierre")]
        if cierre and _asis_se_puede(cierre, contexto) else [])
    return _asis_dato(texto, botones, "ventas_ayer" if ayer else "ventas")


def _dato_del_objetivo(contexto):
    """La barra del objetivo del mes: con la plata, al administrador; al empleado, el
    porcentaje (lo mismo que ve en la caja)."""
    admin = contexto.get("nivel") == "admin"
    avance = avance_del_objetivo()
    if not avance:
        texto = "🎯 Este mes no tiene objetivo de ventas." + (
            " Se pone en la caja, en «🎯 Objetivo del mes»." if admin else "")
    else:
        texto = renglon_del_objetivo(avance, con_plata=admin) + "."
    return _asis_dato(texto, _asis_ir_a(_CAJA, contexto), "objetivo")


def _dato_de_las_senas(contexto):
    """Las señas que esperan que el cliente retire (las de «🔖 Señas» en la caja): cuántas, la
    plata y la más vieja. El nombre del cliente sí (es personal); el teléfono, nunca."""
    todas = senas_activas()
    activas = [s for s in todas if s["tipo"] != "vale"]
    vales = [s for s in todas if s["tipo"] == "vale"]
    de_los_vales = (f" Además, **{miles(len(vales))}** vale(s) a favor sin usar, por "
                    f"**{_asis_plata(sum(s['importe'] or 0 for s in vales))}**." if vales else "")
    if not activas:
        return _asis_dato("✅ No hay señas esperando que el cliente retire." + de_los_vales,
                          _asis_ir_a(_CAJA, contexto), "senas")
    vieja, viejas = activas[0], senas_sin_retirar()
    texto = (f"🔖 Hay **{miles(len(activas))}** seña(s) esperando que el cliente retire, por "
             f"**{_asis_plata(sum(s['importe'] or 0 for s in activas))}**. La más vieja: "
             f"{_asis_nombre(vieja['que'])}"
             + (f", de {_asis_nombre(vieja['cliente'])}" if vieja.get("cliente") else "") + "."
             + (f" **{miles(len(viejas))}** hace más de {DIAS_PARA_AVISAR_UNA_SENA} días: "
                "avisales que pasen a buscarlo." if viejas else "") + de_los_vales)
    return _asis_dato(texto, _asis_ir_a(_CAJA, contexto), "senas")


def _dato_de_los_cheques(contexto):
    """Los cheques para depositar (los de «🏦 Cheques para depositar» en 💳 Cuentas corrientes):
    los que ya se pueden, la plata y el que vence primero."""
    todos = cheques_sin_depositar()
    ya = [x for x in todos if x["se_puede"]]
    despues = len(todos) - len(ya)
    if not ya:
        texto = "✅ No hay cheques para depositar hoy." + (
            f" Hay **{miles(despues)}** con fecha más adelante." if despues else "")
        return _asis_dato(texto, _asis_ir_a(_ADMINISTRAR, contexto), "cheques")
    primero = ya[0]
    vence = ("ya venció" if primero["vencido"]
             else "vence hoy" if primero["dias_para_vencer"] == 0
             else f"vence en {primero['dias_para_vencer']} día(s)")
    texto = (f"🏦 **{miles(len(ya))}** cheque(s) para depositar, por "
             f"**{_asis_plata(sum(x['importe'] for x in ya))}**. El primero, de "
             f"{_asis_nombre(primero['cuenta'])} ({_asis_plata(primero['importe'])}), {vence}."
             + (f" Hay **{miles(despues)}** más con fecha más adelante." if despues else ""))
    return _asis_dato(texto, _asis_ir_a(_ADMINISTRAR, contexto), "cheques")


def _dato_de_los_proveedores(contexto):
    """Lo que se les debe a los proveedores (lo de «🚚 Proveedores»): solo al administrador."""
    cuentas = cuentas_con_proveedores()
    if not cuentas:
        return _asis_dato("✅ No les debés nada a los proveedores (de lo anotado en «🚚 "
                          "Proveedores»).", _asis_ir_a(_ADMINISTRAR, contexto), "proveedores")
    vencido = sum(k["vencido"] for k in cuentas)
    proximos = sorted((k for k in cuentas if k["proximo"]), key=lambda k: k["proximo"])
    texto = (f"🧾 Les debés **{_asis_plata(sum(k['debe'] for k in cuentas))}** a "
             f"**{miles(len(cuentas))}** proveedor(es)"
             + (f"; vencido, **{_asis_plata(vencido)}**" if vencido else "") + "."
             + (f" Lo próximo que vence: {_asis_nombre(proximos[0]['proveedor'])}, el "
                f"{proximos[0]['proximo'][8:10]}/{proximos[0]['proximo'][5:7]}."
                if proximos else ""))
    return _asis_dato(texto, _asis_ir_a(_ADMINISTRAR, contexto), "proveedores")


def _dato_a_cobrar(contexto):
    espera = ventas_a_cobrar()
    if not espera:
        return _asis_dato("✅ No hay nada esperando en la caja.", [], "a_cobrar")
    vieja = espera[0]
    texto = (f"⏳ Esperan en la caja **{miles(len(espera))}** venta(s) por "
             f"**{_asis_plata(sum(v['total'] or 0 for v in espera))}**. La más vieja, la "
             f"#{vieja['id']} de las {vieja.get('hora') or '¿?'}"
             + (f", de {_asis_nombre(vieja['usuario'])}" if vieja.get("usuario") else "")
             + ".")
    return _asis_dato(texto, _asis_ir_a(_CAJA, contexto), "a_cobrar")


def _dato_del_deposito(contexto):
    pendientes = pedidos_pendientes()
    if not pendientes:
        return _asis_dato("✅ El depósito no tiene nada pendiente.", [], "deposito")
    grupos = pendientes_por_pedido(pendientes)
    texto = (f"📦 El depósito tiene **{miles(len(grupos))}** pedido(s) por buscar "
             f"({miles(len(pendientes))} producto(s)). El primero lo pidió "
             f"{_asis_nombre(grupos[0].get('pedido_por') or '¿?')}.")
    return _asis_dato(texto, _asis_ir_a(_DEPOSITO, contexto), "deposito")


def _dato_de_una_cuenta(quien, contexto):
    """Cuánto debe una cuenta. Si lo escrito no es ninguna cuenta, None: era otra pregunta
    («¿cuánto debe durar una correa?»), y sigue el camino de siempre."""
    encontradas, cuantas = buscar_cuentas(quien)
    if not encontradas:
        return None
    lineas = []
    for cuenta_id, nombre in encontradas[:3]:
        estado = estado_de_cuenta(cuenta_id)
        lineas.append(f"- **{_asis_nombre(nombre)}** (N.º {cuenta_id}): debe "
                      f"{_asis_plata(max(estado['saldo'], 0))}"
                      + (f", vencido {_asis_plata(estado['vencido'])}" if estado["vencido"] else "")
                      + (f"; le quedan {_asis_plata(estado['disponible'])} de crédito"
                         if estado["disponible"] is not None else ""))
    texto = "💳 " + ("Encontré estas:\n\n" if len(lineas) > 1 else "") + "\n".join(lineas)
    if cuantas > len(lineas):
        texto += f"\n\n…y {miles(cuantas - len(lineas))} más: escribí más del nombre."
    return _asis_dato(texto, _asis_ir_a(_ADMINISTRAR, contexto), "cuenta")


def _dato_de_mi_cuenta(contexto):
    estado = estado_de_cuenta(contexto["cuenta"])
    texto = (f"💳 Tu cuenta: debés **{_asis_plata(max(estado['saldo'], 0))}**"
             + (f", de eso vencido {_asis_plata(estado['vencido'])}" if estado["vencido"] else "")
             + (f"; te quedan {_asis_plata(estado['disponible'])} disponibles"
                if estado["disponible"] is not None else "")
             + ". Los movimientos están en tu portal, en «💳 Mi cuenta corriente».")
    return _asis_dato(texto, [], "mi_cuenta")


def _dato_de_mis_autos(contexto):
    autos = autos_del_taller(contexto["cuenta"])
    if not autos:
        return _asis_dato("Todavía no anotaste ningún auto. Poné la patente en el presupuesto y, "
                          "cuando lo hagas, «✅ Ya se lo puse».", [], "mis_autos")
    les_toca = [a for a in autos if a["Estado"][:1] in ("🔴", "🟡")]
    texto = (f"🚗 De tus {miles(len(autos))} autos anotados, "
             + (f"a **{miles(len(les_toca))}** ya les toca o les toca pronto:\n\n"
                + "\n".join(f"- **{_asis_nombre(a['Patente'])}**: "
                            f"{_asis_nombre(a['Lo próximo'])} — {a['Le falta']}"
                            for a in les_toca[:5])
                if les_toca else "a ninguno le toca nada todavía.")
             + "\n\nTodos, en tu portal, en «🚗 Mis autos».")
    return _asis_dato(texto, [], "mis_autos")


def _dato_de_los_mensajes(contexto):
    """Cuántos chats hay sin leer y de quién: los nombres, nunca lo que escribieron."""
    cuantos, primeros = chats_sin_leer()
    if not cuantos:
        return _asis_dato("✅ No hay mensajes sin leer.", _asis_ir_a(_MENSAJES, contexto),
                          "mensajes")
    lista = ", ".join(f"{icono} {_asis_nombre(nombre)} ({miles(n)})"
                      for icono, nombre, n in primeros)
    return _asis_dato(f"💬 **{miles(cuantos)}** chat(s) sin leer: {lista}"
                      + (" y más." if cuantos > len(primeros) else "."),
                      _asis_ir_a(_MENSAJES, contexto), "mensajes")


def _dato_de_lo_pendiente(contexto):
    """«¿Qué tengo pendiente?»: un renglón por lo que está esperando, de las pantallas que
    quien pregunta tiene."""
    visibles = contexto["visibles"]
    lineas, botones = [], []
    if _CAJA in visibles:
        r = resumen_de_la_caja()
        if r["esperando"]:
            lineas.append(f"⏳ **{miles(r['esperando'])}** venta(s) esperan en la caja "
                          f"({_asis_plata(r['total_esperando'])}).")
            botones += _asis_ir_a(_CAJA, contexto)
        if contexto.get("nivel") in ("operador", "admin"):
            _viejas = senas_sin_retirar()
            if _viejas:
                lineas.append(f"🔖 **{miles(len(_viejas))}** seña(s) sin retirar hace más de "
                              f"{DIAS_PARA_AVISAR_UNA_SENA} días: «🔖 Señas», en la caja.")
    if _ADMINISTRAR in visibles and contexto.get("nivel") in ("operador", "admin"):
        _cheques = [x for x in cheques_sin_depositar() if x["se_puede"]]
        if _cheques:
            lineas.append(f"🏦 **{miles(len(_cheques))}** cheque(s) para depositar: «🏦 Cheques "
                          "para depositar», en 💳 Cuentas corrientes.")
        if contexto.get("nivel") == "admin":
            _a_pagar = facturas_para_avisar()
            if _a_pagar:
                lineas.append(f"🧾 **{miles(len(_a_pagar))}** proveedor(es) para pagar (vencido "
                              f"o vence en {DIAS_PARA_AVISAR_UNA_FACTURA} días o menos): en «🚚 "
                              "Proveedores».")
    if _DEPOSITO in visibles:
        pendientes = pedidos_pendientes()
        if pendientes:
            lineas.append(f"📦 **{miles(len(pendientes_por_pedido(pendientes)))}** pedido(s) "
                          "esperan en el depósito.")
            botones += _asis_ir_a(_DEPOSITO, contexto)
    if _MENSAJES in visibles:
        sin_leer, _primeros = chats_sin_leer(limite=0)
        if sin_leer:
            lineas.append(f"💬 **{miles(sin_leer)}** chat(s) de clientes sin leer.")
            botones += _asis_ir_a(_MENSAJES, contexto)
    if _ADMINISTRAR in visibles:
        vencidas = cuentas_para_recordar()
        if vencidas:
            _tocan = sum(1 for r in vencidas if r["toca"])
            lineas.append(f"💳 **{miles(len(vencidas))}** cuenta(s) con saldo vencido"
                          + (f"; a {miles(_tocan)} toca recordárselo: «📲 Cobrar lo vencido», "
                             "en 💳 Cuentas corrientes." if _tocan else "."))
        # Cuántas, nunca quiénes ni sus teléfonos.
        _no_vienen = cuentas_que_dejaron_de_venir()
        if _no_vienen:
            lineas.append(f"😴 **{miles(len(_no_vienen))}** cuenta(s) que compraban seguido "
                          "dejaron de venir: «😴 Las cuentas que dejaron de venir», en 💳 "
                          "Cuentas corrientes.")
    # Guardan teléfonos de clientes: solo para el personal (el invitado y el taller no llegan
    # acá, ver dato_del_momento(); va explícito igual).
    if _BUSCADOR in visibles and contexto.get("nivel") in ("operador", "admin"):
        _presus = presupuestos_para_seguir()
        _tocan_p = sum(1 for p in _presus if p["toca"])
        _contestaron_p = sum(1 for p in _presus if p["contesto"])
        if _contestaron_p:
            lineas.append(f"💬 **{miles(_contestaron_p)}** cliente(s) te contestaron por el chat "
                          "sobre el presupuesto que se les mandó: «💬 Te contestó», en "
                          "«📋 Presupuestos para seguir».")
        if _tocan_p:
            lineas.append(f"📋 A **{miles(_tocan_p)}** cliente(s) les toca preguntarles por el "
                          "presupuesto que se les mandó: «📋 Presupuestos para seguir», en el "
                          "🔍 Buscador.")
        if _tocan_p or _contestaron_p:
            botones += _asis_ir_a(_BUSCADOR, contexto)
    # Lo pedido al proveedor que no llegó (ver «LOS PEDIDOS A LOS PROVEEDORES»): las marcas y
    # cuántos, nada de precios.
    if _ESTADISTICAS in visibles and contexto.get("nivel") in ("operador", "admin"):
        _atrasados = [x for x in pedidos_sin_llegar() if x["Atrasado"]]
        if _atrasados:
            lineas.append(f"🚚 **{miles(len(_atrasados))}** pedido(s) a proveedores sin llegar "
                          f"hace más de {DIAS_PARA_RECLAMAR_EL_PEDIDO} días: «⏰ Reclamarle», en "
                          "«🚚 Pedido y sin llegar» (📌 Para pedir).")
            botones += _asis_ir_a(_ESTADISTICAS, contexto)
    if _DEVOLUCIONES in visibles:
        _por_reclamar = [g for g in garantias() if not g["reclamo"]]
        if _por_reclamar:
            lineas.append(f"🔧 **{miles(len(_por_reclamar))}** devolución(es) falladas para "
                          "reclamarle al proveedor: «🔧 Garantías», en ↩️ Devoluciones.")
            botones += _asis_ir_a(_DEVOLUCIONES, contexto)
    if _VEHICULOS in visibles:
        avisar_a = avisos_por_cliente()
        if avisar_a:
            lineas.append(f"📞 A **{miles(len(avisar_a))}** cliente(s) les toca un cambio en su "
                          "auto: están en 🚗 Vehículos, arriba de todo.")
            botones += _asis_ir_a(_VEHICULOS, contexto)
    if not lineas:
        return _asis_dato("✅ Nada pendiente en tus pantallas.", [], "pendiente")
    return _asis_dato("**Lo que está esperando:**\n\n" + "\n".join(f"- {x}" for x in lineas),
                      botones[:3], "pendiente")


def dato_del_momento(llano, contexto):
    """Si lo preguntado es uno de los datos del momento y quien pregunta lo puede ver, la
    respuesta; si no, None (y sigue el camino de siempre). Ver «LO QUE PASA AHORA»."""
    nivel, visibles = contexto.get("nivel"), contexto["visibles"]
    if nivel == "invitado" or not visibles:
        return None
    if nivel == "taller":
        if not contexto.get("cuenta"):
            return None
        if _DATO_MI_DEUDA.search(llano):
            return _dato_de_mi_cuenta(contexto)
        if _DATO_MIS_AUTOS.search(llano):
            return _dato_de_mis_autos(contexto)
        return None
    if _CAJA in visibles:
        if _DATO_Y_AYER.match(llano) and contexto.get("ultima") == "dato:ventas":
            return _dato_de_las_ventas(contexto, ayer=True)
        if _DATO_OBJETIVO.search(llano):
            return _dato_del_objetivo(contexto)
        # «cuánto vendió cada vendedor» no es el número del día: es «🏆 El mes por vendedor».
        if _DATO_VENTAS.search(llano) and not _POR_VENDEDOR.search(llano):
            return _dato_de_las_ventas(contexto, ayer=" ayer" in f" {llano}")
        if _DATO_A_COBRAR.search(llano):
            return _dato_a_cobrar(contexto)
        # Llevan nombres de clientes: solo para el personal.
        if nivel in ("operador", "admin") and _DATO_SENAS.search(llano):
            return _dato_de_las_senas(contexto)
    if _ADMINISTRAR in visibles and nivel in ("operador", "admin"):
        if _DATO_CHEQUES.search(llano):
            return _dato_de_los_cheques(contexto)
        # Lo que se les debe a los proveedores: como la campanita, solo al administrador.
        if nivel == "admin" and _DATO_PROVEEDORES.search(llano):
            return _dato_de_los_proveedores(contexto)
    if _DEPOSITO in visibles and _DATO_DEPOSITO.search(llano):
        return _dato_del_deposito(contexto)
    if _MENSAJES in visibles and _DATO_MENSAJES.search(llano):
        return _dato_de_los_mensajes(contexto)
    if _DATO_PENDIENTE.search(llano):
        return _dato_de_lo_pendiente(contexto)
    if _ADMINISTRAR in visibles:
        hallado = _DATO_CUENTA.match(llano)
        if hallado:
            return _dato_de_una_cuenta(hallado.group("quien") or hallado.group("quien2"),
                                       contexto)
    return None



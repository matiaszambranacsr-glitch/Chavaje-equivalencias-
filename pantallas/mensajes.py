"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/."""

# ============================================================
# MENSAJES: los chats de WhatsApp, Facebook e Instagram, para contestar desde acá
# ============================================================
# Cómo llegan y se contestan, en logica/mensajes.py. La lista y la conversación se ponen al día
# solas cada 20 segundos (son partes que se redibujan solas, como los avisos de lo que terminó
# otro); la caja para escribir queda afuera de ellas, así lo que uno está escribiendo no se
# borra cuando llega algo.
if pagina == PAGINAS[12]:
    ayuda(
        "Acá llegan los mensajes de **WhatsApp** 🟢, **Facebook** 🔵 e **Instagram** 🟣 del "
        "negocio. Los **sin leer** van arriba con 🔴, y la pastilla de arriba dice cuántos hay "
        "(«💬 Mensajes · 3»); cuando llega uno nuevo salta un cartel en cualquier pantalla.\n\n"
        "Tocá un chat para abrirlo: queda leído para todos. **⏳ Sin contestar** son los que "
        "tienen lo último del cliente, aunque alguien ya los haya leído. Si el mensaje trae un "
        "código, el botón 🔍 lo busca en el Buscador.\n\n"
        "**🧩 Armar el presupuesto con lo que pide**: separa lo último que escribió (las piezas "
        "con el auto que nombra, y los códigos) y de cada una te muestra lo que hay para elegir "
        "o descartar. Con lo elegido arma el presupuesto del Buscador, con su nombre y su "
        "WhatsApp, listo para «💬 Mandárselo». Lo que no entiende, no lo inventa: lo buscás a "
        "mano.\n\n"
        "**Las 24 horas**: Meta deja contestar desde acá hasta 24 horas después del último "
        "mensaje del cliente; después hay que escribirle desde el teléfono. Fotos y audios se "
        "avisan, pero se miran en el teléfono.\n\n"
        "Conectar los canales lo hace un administrador, en 🗂️ Administrar → 💬 Mensajería y "
        "cobros: ahí está «📲 Conectar WhatsApp, Facebook e Instagram».")

    def _msj_abrir(chat_id):
        st.session_state["msj_chat_abierto"] = chat_id
        # Desde ahora, el chat está «en curso»: ver chat_para_mandar().
        st.session_state["msj_chat_abierto_en"] = time.monotonic()
        try:
            marcar_leido(chat_id)
        except (PermissionError, sqlite3.Error) as _err:
            anotar_error("mensajes/abrir", _err)

    def _msj_cerrar():
        st.session_state.pop("msj_chat_abierto", None)
        st.session_state.pop("msj_chat_abierto_en", None)

    def _msj_no_leido(chat_id):
        try:
            marcar_leido(chat_id, leido=False)
        except (PermissionError, sqlite3.Error) as _err:
            anotar_error("mensajes/no_leido", _err)
        _msj_cerrar()

    def _msj_borrar(chat_id):
        try:
            _aviso = ("success", f"🗑️ Chat borrado ({miles(borrar_chat(chat_id))} mensaje(s)).")
        except PermissionError as _err:
            _aviso = ("error", el_error_en_castellano(_err))
        avisar(*_aviso)
        _msj_cerrar()

    def _msj_hora(momento):
        return hora_corta_aca(momento) if momento else ""


    _abierto_msj = st.session_state.get("msj_chat_abierto")
    if _abierto_msj and not el_chat(_abierto_msj):
        _abierto_msj = None
        _msj_cerrar()
    # En el celular, con un chat abierto, solo el chat: los filtros, el buscador y los avisos lo
    # empujaban una pantalla para abajo (se vio en un teléfono simulado).
    _filtro_msj, _buscar_msj = "todos", ""
    if not (es_celular() and _abierto_msj):
        _conectados_msj = canales_conectados()
        if not (hay_mensajes_conectados() or _conectados_msj["whatsapp"]):
            st.info("📲 Todavía no está conectado ningún canal: los mensajes van a aparecer acá "
                    "cuando un administrador conecte WhatsApp, Facebook o Instagram.")
            if es_admin():
                st.button("📲 Conectar los canales →", key="msj_ir_a_conectar",
                          on_click=ir_a_donde_dice_el_aviso,
                          args=("🗂️ Administrar → 💬 Mensajería y cobros",))

        # Arriba: qué mostrar, buscar un chat y traer ya.
        _f1, _f2, _f3 = st.columns([3, 3, 2], vertical_alignment="bottom")
        _filtro_msj = _f1.radio("Mostrar:", list(FILTROS_DE_LA_BANDEJA), key="msj_filtro",
                                format_func=FILTROS_DE_LA_BANDEJA.get, horizontal=True)
        _buscar_msj = _f2.text_input("Buscar un chat:", key="msj_buscar",
                                     placeholder="Nombre, número o lo que escribió")
        if _f3.button("🔄 Traer ahora", key="msj_traer_ahora", width="stretch",
                      disabled=not hay_mensajes_conectados(),
                      help="Pregunta ya a Meta y al relevo (solo, lo hace cada minuto)."):
            try:
                with st.spinner("Trayendo los mensajes…"):
                    _traido = traer_mensajes_ahora()
            except PermissionError as _err:
                st.error(el_error_en_castellano(_err))
                _traido = {}
            if _traido is None:
                st.warning("Justo se estaban trayendo: tocá de nuevo en unos segundos.")
            else:
                _errores_msj = [f"{canal}: {error}" for canal, (_n, error) in _traido.items() if error]
                _nuevos_msj = sum(n for n, _e in _traido.values())
                if _errores_msj:
                    st.warning("⚠️ " + " · ".join(_errores_msj))
                st.toast(f"💬 {miles(_nuevos_msj)} mensaje(s) nuevo(s).")

        # Cómo le fue la última vez a cada canal: si uno falla, se dice acá y no en silencio.
        for _canal_msj, _estado_msj in estado_de_los_canales().items():
            if _estado_msj.get("error"):
                _nombre_canal = ("WhatsApp" if _canal_msj == "relevo"
                                 else CANALES_DE_MENSAJES[_canal_msj]["nombre"])
                st.warning(f"⚠️ {_nombre_canal}: {_estado_msj['error']} "
                           f"(última vez: {_msj_hora(_estado_msj['cuando'])}).")

        # ESCRIBIRLE A UN NÚMERO QUE NUNCA ESCRIBIÓ. Desde acá (la conexión de Meta) solo se
        # puede con una plantilla aprobada, que Meta cobra. Desde el WhatsApp del teléfono o de la
        # computadora es gratis: esto lo abre con el número y el texto, y se toca enviar. Si
        # contesta, el chat aparece en la bandeja.
        with st.expander("✉️ Escribirle a un número nuevo", key="exp_numero_nuevo"):
            _n1, _n2 = st.columns([1, 2])
            _numero_nuevo = _n1.text_input("Número:", key="msj_numero_nuevo",
                                           placeholder="11 4567-8901")
            _texto_nuevo = _n2.text_area("Mensaje:", key="msj_texto_nuevo", height=80,
                                         placeholder="Hola! Te escribimos de El Chavo…")
            if _numero_nuevo.strip():
                if not numero_para_whatsapp(_numero_nuevo):
                    st.warning("No entiendo ese número: va con la característica, por ejemplo "
                               "11 4567-8901 o 0341 15 555-0000.")
                else:
                    # La clave «walink__…» le dice al navegador de qué caja tomar el texto al
                    # tocarlo, aunque recién se haya escrito (ver AYUDAS_DEL_NAVEGADOR).
                    st.link_button("📱 Abrirlo en WhatsApp para mandarlo",
                                   link_de_whatsapp(_numero_nuevo, _texto_nuevo.strip()),
                                   type="primary", width="stretch",
                                   key="walink__msj_texto_nuevo")
                    st.caption(f"Va a +{numero_para_whatsapp(_numero_nuevo)}. Lo mandás vos desde "
                               "WhatsApp, gratis; cuando conteste, el chat aparece acá.")


    @st.fragment(run_every=20)
    def _msj_la_lista():
        arrancar_la_bandeja_de_fondo()
        try:
            _chats = chats_de_la_bandeja(_filtro_msj or "todos", _buscar_msj)
        except sqlite3.Error as _err:
            anotar_error("chats_de_la_bandeja", _err)
            st.warning("⏳ La base está ocupada: esperá unos segundos.")
            return
        if not _chats:
            st.caption({"sin_leer": "✅ No hay chats sin leer.",
                        "sin_contestar": "✅ No hay chats esperando respuesta."}
                       .get(_filtro_msj, "Todavía no llegó ningún mensaje."))
            return
        for _ch in _chats:
            _icono = CANALES_DE_MENSAJES.get(_ch["canal"], {}).get("icono", "💬")
            _vista = str(_ch["ultimo_texto"] or "").replace("\n", " ")
            _vista = _vista[:60] + ("…" if len(_vista) > 60 else "")
            # Quién contestó lo último: con varios atendiendo, «Vos:» para todos confundía.
            _quien = str(_ch.get("ultimo_quien") or "")
            _de_quien = "" if _ch["ultimo_entra"] else (
                "Vos: " if _quien == obtener_usuario_actual()
                else "Desde el teléfono: " if _quien == "desde otro lado"
                else f"{_quien}: " if _quien else "")
            _marca = f"🔴 {miles(_ch['sin_leer'])} · " if _ch["sin_leer"] else (
                "⏳ " if _ch["ultimo_entra"] else "")
            # Lo que espera respuesta dice hace cuánto: a la media hora ya es mucho.
            _cuando = (hace_cuanto_espera(_ch["ultimo_del_cliente_en"]) if _ch["ultimo_entra"]
                       else _msj_hora(_ch["ultimo_en"]))
            _etiqueta = (f"{_icono} {_marca}**{texto_de_chat_para_markdown(nombre_del_chat(_ch))}**"
                         f" · {_cuando}  \n"
                         f"{texto_de_chat_para_markdown(_de_quien + _vista)}")
            if st.button(_etiqueta, key=f"msj_chat_{_ch['id']}", width="stretch",
                         type="primary" if _ch["id"] == _abierto_msj else "secondary"):
                _msj_abrir(_ch["id"])
                st.rerun()

    @st.fragment(run_every=20)
    def _msj_la_conversacion(chat_id):
        _chat = el_chat(chat_id)
        if not _chat:
            return
        # Lo que llega mientras se lo está mirando ya está leído.
        if _chat["sin_leer"]:
            _msj_abrir(chat_id)
        _canal = CANALES_DE_MENSAJES.get(_chat["canal"], {})
        st.markdown(f"#### {_canal.get('icono', '💬')} "
                    f"{texto_de_chat_para_markdown(nombre_del_chat(_chat))}")
        _datos_chat = [f"por {_canal.get('nombre', '')}"]
        if _chat["canal"] == "whatsapp":
            _datos_chat.append(f"+{texto_para_markdown(_chat['externo'])}")
        for _que, _detalle in lo_que_sabemos_del_numero(_chat):
            _datos_chat.append(f"{_que}: {texto_de_chat_para_markdown(_detalle)}")
        st.caption(" · ".join(_datos_chat))
        _mensajes = mensajes_del_chat(chat_id)
        # Con pocos mensajes, del alto justo; con muchos, una caja que se desliza.
        with st.container(height=(360 if es_celular() else 430) if len(_mensajes) > 4 else "content",
                          key="msj_hilo"):
            for _m in _mensajes:
                with st.chat_message("user" if _m["entra"] else "assistant",
                                     avatar="🙂" if _m["entra"] else "🏪"):
                    st.markdown(texto_de_chat_para_markdown(_m["texto"]))
                    st.caption(_msj_hora(_m["cuando"]) + (
                        "" if _m["entra"] else f" · {texto_para_markdown(_m['quien'] or '')}"))
        # Los códigos que mandó el cliente en sus últimos mensajes, para buscarlos de un toque.
        _codigos = []
        for _m in reversed([m for m in _mensajes if m["entra"]][-3:]):
            for _cod in codigos_del_mensaje(_m["texto"]):
                if _cod.upper() not in (x.upper() for x in _codigos):
                    _codigos.append(_cod)
        if _codigos:
            _cols = st.columns(min(len(_codigos), 3) + 1)
            for _n, _cod in enumerate(_codigos[:3]):
                _cols[_n].button(f"🔍 Buscar {_cod}", key=f"msj_buscar_cod_{chat_id}_{_n}",
                                 on_click=buscar_el_codigo_del_mensaje, args=(_cod,), width="stretch",
                                 help="Lo busca en el 🔍 Buscador, con sus equivalencias.")
            # Todos juntos a la cotización, y de ahí «💬 Mandárselo» de vuelta a este chat.
            _cols[-1].button("📋 Cotizar estos códigos", key=f"msj_cotizar_{chat_id}",
                             on_click=cotizar_los_codigos_del_chat, args=(_codigos[:3],),
                             width="stretch",
                             help="Los suma a 📋 Lista WhatsApp; desde ahí se le manda la "
                                  "cotización a este chat con un toque.")

    def _mostrar_pedidos_del_chat(chat_id):
        _leido, _pedidos = pedidos_y_candidatos_del_chat(chat_id)
        _autos = {p["auto"] for p, _ in _pedidos if p["auto"]}
        st.caption("Lo que entendí de lo último que escribió"
                   + (f", para **{texto_para_markdown(' / '.join(sorted(_autos)))}**" if _autos
                      else "") + ". Elegí cuál va o descartalo.")
        # Las claves llevan la huella de lo leído: si escribe otra cosa, son pedidos nuevos y
        # no se quedan con lo elegido para los de antes.
        _huella = hashlib.md5(_leido.encode("utf-8")).hexdigest()[:8]
        _elegidos = []
        for _n, (_ped, _cands) in enumerate(_pedidos):
            _clave = f"pedido_chat_{chat_id}_{_huella}_{_n}"
            # Sin negritas: el rótulo es también lo que lee el lector de pantalla, y ahí las
            # «**» quedaban escritas.
            _titulo = (f"{_n + 1}. {texto_para_markdown(_ped['texto'])}"
                       + (" (código)" if _ped["tipo"] == "codigo" else ""))
            if not _cands:
                st.markdown(f"{_titulo} — no lo encontré en el catálogo"
                            + (" con esas palabras" if _ped["tipo"] == "pieza" else "")
                            + ": buscalo a mano en el 🔍 Buscador.")
                continue
            _por_id = {x["ID"]: x for x in _cands}
            _primero = _cands[0]
            _col_que, _col_cant = st.columns([5, 1], vertical_alignment="bottom")
            _opciones = list(_por_id) + [DESCARTAR_EL_PEDIDO]
            _col_que.selectbox(
                _titulo, _opciones, key=_clave, index=0 if _primero["para_el_auto"] else
                len(_opciones) - 1,
                # rótulo fijo: marca, código y descripción no cambian mientras se elige.
                format_func=lambda x, d=_por_id: "🗑️ Descartar este pedido"
                if x == DESCARTAR_EL_PEDIDO else (
                    ("⚠️ " if not d[x]["para_el_auto"] else "")
                    + f"{d[x]['Marca']} {d[x]['Codigo']} — "
                      f"{str(d[x]['Descripcion'] or '')[:70]}"))
            _col_cant.number_input("Cant.", 1, CANTIDAD_MAXIMA_POR_PEDIDO, _ped["cantidad"],
                                   key=f"{_clave}_cant")
            _elegido = _por_id.get(st.session_state.get(_clave))
            if _elegido:
                st.caption(("⚠️ La descripción no dice que sea para ese auto: fijate antes de "
                            "ofrecerlo. · " if not _elegido["para_el_auto"] else "")
                           + (f"\\${miles(_elegido['Precio'])}" if _elegido["Precio"]
                              else "sin precio")
                           + (f" · stock {miles(_elegido['Stock'])}"
                              if _elegido["Stock"] is not None else ""))
            _elegidos.append((_clave, f"{_clave}_cant"))
        if _elegidos:
            st.button("🛒 Armar el presupuesto con lo elegido", key=f"msj_armar_presu_{chat_id}",
                      type="primary", width="stretch", on_click=armar_el_presupuesto_del_chat,
                      args=(chat_id, _elegidos),
                      help="Lo suma al presupuesto del 🔍 Buscador, con el nombre y el WhatsApp "
                           "del cliente listos para guardarlo, y desde ahí «💬 Mandárselo».")

    # En la computadora, la lista a la izquierda y el chat a la derecha. En el celular, una
    # cosa por vez: la lista, y al tocar un chat, el chat con «← Volver».
    if es_celular():
        _lugar_lista = st.container() if not _abierto_msj else None
        _lugar_chat = st.container() if _abierto_msj else None
    else:
        _lugar_lista, _lugar_chat = st.columns([2, 3], gap="medium")
    if _lugar_lista is not None:
        with _lugar_lista:
            _msj_la_lista()
    if _lugar_chat is not None:
        with _lugar_chat:
            if not _abierto_msj:
                st.caption("Tocá un chat de la lista para verlo y contestarlo.")
            else:
                if es_celular():
                    st.button("← Volver a los chats", key="msj_volver", on_click=_msj_cerrar)
                _msj_la_conversacion(_abierto_msj)
                _chat_msj = el_chat(_abierto_msj)
                _clave_resp = f"msj_respuesta_{_abierto_msj}"

                def _msj_rapida(clave, eleccion):
                    _frase = st.session_state.get(eleccion)
                    if _frase:
                        _antes = str(st.session_state.get(clave) or "").rstrip()
                        st.session_state[clave] = f"{_antes} {_frase}".strip()
                    st.session_state[eleccion] = None

                def _msj_enviar(chat_id, clave):
                    _texto_enviado = st.session_state.get(clave)
                    try:
                        ok, error = contestar_chat(chat_id, _texto_enviado)
                    except PermissionError as _err:
                        ok, error = False, el_error_en_castellano(_err)
                    if ok:
                        anotar_si_le_recordamos(el_chat(chat_id), _texto_enviado)
                        st.session_state[clave] = ""
                        avisar("success", "📤 Enviado.")
                    else:
                        avisar("error", f"No se mandó: {error}")

                # LA CUENTA QUE DEBE VENCIDO y escribe: el recordatorio, a un toque, en la caja de
                # la respuesta (o en la de WhatsApp, pasadas las 24 horas). Mandado desde acá
                # queda anotado solo (ver anotar_si_le_recordamos()).
                _recordatorio = recordatorio_del_chat(_chat_msj)
                _fuera = fuera_de_la_ventana(_chat_msj)
                if _recordatorio:
                    def _msj_poner_recordatorio(clave, texto):
                        _antes = str(st.session_state.get(clave) or "").rstrip()
                        if texto not in _antes:
                            st.session_state[clave] = f"{_antes}\n\n{texto}".strip()
                    st.button("💳 Recordarle lo vencido", key=f"msj_recordar_{_abierto_msj}",
                              on_click=_msj_poner_recordatorio,
                              args=(f"msj_fuera_{_abierto_msj}" if _fuera else _clave_resp,
                                    _recordatorio[1]),
                              help="Pone en la respuesta el recordatorio de lo que debe "
                                   "vencido, ya escrito. Mandado desde acá queda anotado en "
                                   "💳 Cuentas corrientes → «📲 Cobrar lo vencido».")
                if _fuera:
                    st.warning(f"⏰ {TEXTO_FUERA_DE_LA_VENTANA}")
                    if _chat_msj["canal"] == "whatsapp" and str(_chat_msj["externo"]).isdigit():
                        # Lo que le quiere decir va escrito: en WhatsApp, solo tocar enviar.
                        _texto_fuera = st.text_area(
                            "Lo que le querés decir:", key=f"msj_fuera_{_abierto_msj}", height=80,
                            placeholder="Se abre en WhatsApp escrito, para mandarlo desde ahí")
                        st.link_button("📱 Abrir este chat en WhatsApp",
                                       f"https://wa.me/{_chat_msj['externo']}"
                                       + (f"?text={quote(_texto_fuera.strip())}"
                                          if _texto_fuera.strip() else ""),
                                       type="primary", width="stretch",
                                       key=f"walink__msj_fuera_{_abierto_msj}")
                    else:
                        # Facebook e Instagram: se contesta desde la bandeja de Meta.
                        st.link_button("📱 Abrir la bandeja de Meta",
                                       "https://business.facebook.com/latest/inbox/all",
                                       width="stretch")
                else:
                    # En el celular, plegadas: abiertas eran cuatro renglones antes de la caja.
                    _donde_rapidas = (st.popover("⚡ Respuestas rápidas", key="msj_pop_rapidas")
                                      if es_celular() else st.container())
                    _donde_rapidas.pills("Respuestas rápidas:", respuestas_rapidas(),
                                         key=f"{_clave_resp}_rapida", on_change=_msj_rapida,
                                         args=(_clave_resp, f"{_clave_resp}_rapida"),
                                         label_visibility="collapsed")
                    # SIN FORMULARIO: adentro de uno, lo escrito no le llega a la app hasta
                    # «📤 Enviar», y una respuesta rápida o «💳 Recordarle lo vencido» tocados
                    # en el medio lo borraban (se escribía «Hola! Te cuento:», se tocaba «¡Hola!
                    # ¿En qué te ayudo?» y quedaba solo eso; se vio en un navegador de verdad).
                    # Suelta, lo escrito viaja apenas se toca otra cosa.
                    st.text_area("Tu respuesta:", key=_clave_resp, height=90,
                                 max_chars=LARGO_MAXIMO_POR_CANAL.get(_chat_msj["canal"], 1000),
                                 placeholder="Escribí la respuesta y tocá 📤 Enviar")
                    st.button("📤 Enviar", key=f"msj_enviar_{_abierto_msj}", type="primary",
                              width="stretch", on_click=_msj_enviar,
                              args=(_abierto_msj, _clave_resp))
                # DEL CHAT AL PRESUPUESTO: lo que pidió, separado en pedidos, cada uno con lo
                # que hay en el catálogo para elegir o descartar (ver «LO QUE PIDE EL CHAT,
                # SEPARADO EN PEDIDOS» en logica/mensajes.py). Perezoso: buscar cada pedido
                # cuesta, y la mayoría de las veces se contesta sin abrirlo.
                _pedido_msj = lo_que_pidio_el_cliente(_abierto_msj)
                _cuantos_pedidos = len(pedidos_del_mensaje(_pedido_msj))
                if _cuantos_pedidos and es_operador_o_admin():
                    _exp_presu_chat = st.expander(
                        f"🧩 Armar el presupuesto con lo que pide ({_cuantos_pedidos})",
                        key=f"exp_presu_chat_{_abierto_msj}", on_change="rerun")
                    if _exp_presu_chat.open:
                        with _exp_presu_chat:
                            _mostrar_pedidos_del_chat(_abierto_msj)
                st.button("Marcar como no leído", key=f"msj_no_leido_{_abierto_msj}",
                          on_click=_msj_no_leido, args=(_abierto_msj,))
                # BORRAR EL CHAT: el cliente que pide que se borren sus datos, o publicidad. Solo
                # el administrador, y preguntando antes: no hay cómo traerlo de vuelta.
                if es_admin():
                    with st.popover("🗑️ Borrar este chat", key="msj_pop_borrar"):
                        st.markdown("Se borra el chat con **todos sus mensajes**, y no hay cómo "
                                    "traerlo de vuelta. Si vuelve a escribir, empieza uno nuevo.")
                        st.button("Sí, borrarlo", key=f"msj_borrar_{_abierto_msj}",
                                  type="primary", on_click=_msj_borrar, args=(_abierto_msj,))

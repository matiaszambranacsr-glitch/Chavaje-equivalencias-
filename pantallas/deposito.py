"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/."""

# ============================================================
# DEPÓSITO: lo que pidió el mostrador, y lo que queda para facturar
# ============================================================
# Cómo funciona, en logica/deposito.py («EL DEPÓSITO: DEL MOSTRADOR A LA CUENTA»).
if pagina == PAGINAS[8]:
    # Las solapas: lo de todos los días primero; el mapa, ubicar y armar, en
    # pantallas/deposito_mapa.py.
    sub_deposito = elegir_solapa(PAGINAS[8])

    if sub_deposito == SUB_DEPOSITO[0]:
        ayuda(
            "Acá llega lo que el mostrador pide con «📦 Pedir al depósito» en el buscador. "
            "**📍 Por ubicación** lo parte por piso, cada uno en su orden —por ubicación, o "
            "siempre lo más cerca de lo último que entregaste— y lo resalta en el mapa; lo que "
            "no tiene lugar, al entregarlo poné dónde estaba («📍 ¿Dónde está?») y la próxima "
            "vez sale en el mapa. **✅ Entregado** lo da de "
            "baja: descuenta el stock y, si es para la cuenta de un taller o un mayorista, lo carga "
            "en su cuenta (lo de un taller no vuelve); si es para Mostrador, queda **a nombre de "
            "quien lo pidió** hasta que lo venda en 🧾 Ventas o vuelva: lo recibe el depósito "
            "**escaneando la etiqueta nuestra** en ↩️ Devoluciones. Imprimí las etiquetas con "
            "**🏷️ Etiquetas** y pegá una en cada pieza que sale. Si se termina el stock, queda "
            "anotado para reponer solo. **❌ No hay** lo manda a 📊 Estadísticas → 📌 Para "
            "pedir. Se mide cuánto tarda cada uno, desde que se pide hasta que se da de baja: 🟡 "
            f"desde {MINUTOS_PARA_AVISAR[0]} minutos de espera, 🔴 desde {MINUTOS_PARA_AVISAR[1]}. "
            "Acá no se ven precios."
        )

        def _resolver_pedido(funcion, pedido_id, rotulo):
            """Callback de los botones: la clave de cada pedido deja de existir cuando se resuelve,
            así que el aviso se guarda en la sesión y se muestra arriba de la cola."""
            ok, aviso = funcion(pedido_id)
            st.session_state["_aviso_del_deposito"] = (ok, aviso if ok else f"{rotulo}: {aviso}")

        def _cancelar_pedido(pedido_id, rotulo):
            ok = cancelar_pedido_del_deposito(pedido_id)
            st.session_state["_aviso_del_deposito"] = (
                ok, f"🚫 Cancelado: {rotulo}." if ok else f"{rotulo}: ya no estaba pendiente.")

        with st.container(horizontal=True, gap="medium"):
            _sola = st.toggle("🔄 Que se actualice sola", value=True,
                              key="deposito_actualizar_sola",
                              help="Cada 20 segundos mira si llegaron pedidos nuevos, sin tocar "
                                   "nada.")
            st.toggle("🔊 Sonido", value=True, key="con_sonido_deposito",
                      help="Un pitido cuando llega un pedido nuevo.")

        def _entregar_todo(tanda, rotulo):
            hechos, no = entregar_la_tanda(tanda)
            st.session_state["_aviso_del_deposito"] = (
                not no, f"✅ {rotulo}: {hechos} ítem(s) entregados"
                        + (f"; {no} ya los había resuelto otra persona." if no else "."))

        def _guardar_lugar(producto_id, clave):
            """Callback del «📍 ¿Dónde está?» de un renglón sin lugar: lo aprende ahí mismo, y la
            próxima vez sale en el mapa. Ver ubicar_producto()."""
            ok, texto = ubicar_producto(producto_id, st.session_state.get(clave, ""))
            st.session_state["_aviso_del_deposito"] = (ok, texto)

        def _renglon_del_pedido(_p, mostrar_quien=True, hay_un_mapa=False):
            _rotulo = f"{_p['marca']} {_p['codigo_raw']} x{_p['cantidad']}"
            # Dónde está, en el mapa (ver lugar_en_el_mapa()): la cola por piso ya lo trae.
            _donde = _p["donde"] if "donde" in _p else lugar_en_el_mapa(_p["ubicacion"])
            _lugar = (_donde["texto"] if _donde else texto_para_html(_p["ubicacion"] or "")
                      or "sin ubicación")
            with st.container(border=True):
                _ca, _cb = st.columns([3, 2])
                _ca.markdown((f"**{_p['paso']}.** " if _p.get("paso") else "")
                             + f"📍 **{_lugar}** · "
                             f"**{texto_para_html(_p['marca'])} {texto_para_html(_p['codigo_raw'])}**"
                             f" × **{_p['cantidad']}**")
                _detalle = ([_donde["se_lee"]] if _donde else []) + [(_p["descripcion"] or "")[:90]]
                if mostrar_quien:
                    _detalle += [f"para {_p['cuenta'] or NOMBRE_DEL_MOSTRADOR}",
                                 f"pidió {_p['pedido_por'] or '¿?'} a las "
                                 f"{_hora_corta(_p['pedido_en'])}",
                                 f"esperando {como_se_lee_la_espera(minutos_entre(_p['pedido_en']))}"]
                if _p["stock"] is not None:
                    _detalle.append(f"stock: {_p['stock']}")
                _ca.caption(" · ".join(x for x in _detalle if x))
                if _p["nota"]:
                    _ca.info(f"📝 {_p['nota']}")
                # SIN LUGAR EN EL MAPA: el que lo va a buscar sabe dónde está; se anota ahí mismo.
                if hay_un_mapa and not _donde:
                    with _ca.popover("📍 ¿Dónde está?", key=f"pop_donde_{_p['id']}"):
                        st.text_input("Lugar (estantería-módulo-estante):",
                                      key=f"dep_lugar_{_p['id']}", placeholder="A-3-2")
                        st.button("💾 Guardar el lugar", key=f"dep_lugar_ok_{_p['id']}",
                                  on_click=_guardar_lugar,
                                  args=(_p["producto_id"], f"dep_lugar_{_p['id']}"))
                _b1, _b2, _b3 = _cb.columns(3)
                _b1.button("✅ Entregado", key=f"dep_ok_{_p['id']}", type="primary",
                           width="stretch", on_click=_resolver_pedido,
                           args=(entregar_pedido, _p["id"], _rotulo))
                _b2.button("❌ No hay", key=f"dep_no_{_p['id']}", width="stretch",
                           on_click=_resolver_pedido,
                           args=(no_hay_en_el_deposito, _p["id"], _rotulo))
                _b3.button("🚫", key=f"dep_x_{_p['id']}", width="stretch",
                           help="Cancelar: el mostrador ya no lo quiere.",
                           on_click=_cancelar_pedido, args=(_p["id"], _rotulo))

        def _cambiar_orden(piso_id, clave_modo, clave_minutos):
            """Callback del orden de un piso: queda guardado para todos los del depósito."""
            ok, texto = elegir_orden_de_la_cola(piso_id, st.session_state.get(clave_modo),
                                                st.session_state.get(clave_minutos, 1))
            if not ok:
                st.session_state["_aviso_del_deposito"] = (False, texto)

        def _cola_de_un_piso(_g, hay_un_mapa):
            """Lo que hay que buscar en un piso, en su orden y resaltado en el mapa. Ver «LA COLA
            POR PISO» en logica/mapa.py."""
            if _g["piso_id"] is None:
                if hay_un_mapa:
                    st.markdown(f"##### ❓ Sin lugar en el mapa: {len(_g['items'])}")
                    st.caption("Al entregarlo, poné dónde estaba con «📍 ¿Dónde está?»: la "
                               "próxima vez sale en el mapa.")
                for _p in _g["items"]:
                    _renglon_del_pedido(_p, hay_un_mapa=hay_un_mapa)
                return
            _pid = _g["piso_id"]
            st.markdown(f"##### 🏢 {texto_para_html(_g['deposito'])} · "
                        f"{texto_para_html(_g['piso'])}: {len(_g['items'])} para buscar")
            # El orden lo elige cada piso, para todos: se muestra el de la base, no el que quedó
            # en esta sesión (puede haberlo cambiado otro).
            _clave_modo, _clave_min = f"dep_orden_{_pid}", f"dep_minutos_{_pid}"
            st.session_state[_clave_modo] = _g["modo"]
            st.session_state[_clave_min] = float(_g["minutos"] or 1)
            _o1, _o2 = st.columns([3, 1])
            _o1.radio("Orden:", list(ORDENES_DE_LA_COLA), format_func=ORDENES_DE_LA_COLA.get,
                      key=_clave_modo, horizontal=True, label_visibility="collapsed",
                      on_change=_cambiar_orden, args=(_pid, _clave_modo, _clave_min))
            if _g["modo"] == "cercania":
                _o2.number_input("Minutos:", min_value=0.25, max_value=120.0, step=0.25,
                                 key=_clave_min, on_change=_cambiar_orden,
                                 args=(_pid, _clave_modo, _clave_min),
                                 help="Si lo último que entregaste en este piso fue hace menos "
                                      "que esto, seguís desde ahí; si no, desde la entrada.")
            st.caption(f"Arranca {_g['desde']}"
                       + (f" · el recorrido: unos {_g['pasos']} paso{'s' if _g['pasos'] != 1 else ''}"
                          if _g["pasos"] else ""))
            if st.toggle("🗺️ Ver en el mapa", value=True, key=f"dep_mapa_{_pid}"):
                _numeros = {}
                for _p in _g["items"]:
                    _numeros.setdefault(_p["donde"]["celdas"], []).append(str(_p["paso"]))
                _est_del_piso = estanterias_del_piso(_pid)
                st.markdown(svg_del_piso(_g["plano"],
                                         {l_: e["codigo"] for l_, e in _est_del_piso.items()},
                                         [(cel, ",".join(n)) for cel, n in _numeros.items()],
                                         _g["camino"],
                                         lados={l_: e["lados"] for l_, e in _est_del_piso.items()}),
                            unsafe_allow_html=True)
                st.caption(LEYENDA_DEL_MAPA)
            for _p in _g["items"]:
                _renglon_del_pedido(_p, hay_un_mapa=hay_un_mapa)

        # CÓMO SE ORDENA LA COLA. Por pedido: cada vendedor por separado, el que pidió primero
        # arriba; con cuatro vendedores mandando presupuestos de diez productos, por ubicación
        # quedaban cuarenta renglones mezclados y no se sabía qué era de quién. Por ubicación:
        # todo junto, partido por piso y en el orden de cada uno (ver «LA COLA POR PISO»), para
        # una sola vuelta. Con el mapa armado arranca por ubicación.
        _hay_mapa = hay_mapa()
        _vista_cola = st.segmented_control(
            "Ordenar:", ["🧾 Por pedido", "📍 Por ubicación"],
            default="📍 Por ubicación" if _hay_mapa else "🧾 Por pedido", required=True,
            key="deposito_vista", label_visibility="collapsed") or "🧾 Por pedido"

        @st.fragment(run_every=20 if _sola else None)
        def _cola_del_deposito():
            _aviso = st.session_state.pop("_aviso_del_deposito", None)
            if _aviso:
                (st.success if _aviso[0] else st.warning)(_aviso[1])
            _pendientes = pedidos_pendientes()
            # LO QUE LLEGA, CON SU CARTEL: como en la caja, cada pedido nuevo avisa arriba
            # (y con un pitido, si está prendido). Lo que ya estaba al entrar no avisa: se ve
            # en la lista.
            _vistos = st.session_state.get("deposito_vistos")
            for _p in _pendientes:
                if _vistos is not None and _p["id"] not in _vistos:
                    st.toast(el_aviso_del_pedido(_p), icon="📦", duration="long")
            st.session_state["deposito_vistos"] = (_vistos or set()) | {_p["id"] for _p in _pendientes}
            _grupos = pendientes_por_pedido(_pendientes)
            _esperas = [minutos_entre(_p["pedido_en"]) or 0 for _p in _pendientes]
            st.markdown(f"#### ⏳ Para buscar: {len(_pendientes)}"
                        + (f" en {len(_grupos)} pedido(s)" if len(_grupos) != len(_pendientes)
                           else "")
                        + (f" · el que más espera: {como_se_lee_la_espera(max(_esperas))}"
                           if _esperas else ""))
            if not _pendientes:
                st.caption("Nada pendiente. Lo que pidan desde el buscador aparece acá solo.")
            # LAS ETIQUETAS de lo que sale para Mostrador, una por unidad: sin la etiqueta nuestra
            # no puede volver al stock. Lo de un taller no vuelve: no lleva. Ver «EL CÓDIGO DE
            # BARRAS NUESTRO» en logica/deposito.py.
            _para_etiquetar = [(_p["producto_id"], _p["cantidad"]) for _p in _pendientes
                               if not _p["mecanico_id"]]
            if _para_etiquetar:
                st.download_button(
                    f"🏷️ Etiquetas de lo que sale para Mostrador "
                    f"({sum(n for _, n in _para_etiquetar)})",
                    data=etiquetas_para_descargar(_para_etiquetar), file_name="etiquetas.pdf",
                    mime="application/pdf", key="deposito_etiquetas",
                    help="Una por pieza, para pegarle antes de entregarla: si no se vende, vuelve "
                         "al stock escaneando esa etiqueta en ↩️ Devoluciones.")
            if _vista_cola == "📍 Por ubicación":
                for _g in la_cola_por_piso(_pendientes):
                    _cola_de_un_piso(_g, _hay_mapa)
                return
            for _g in _grupos:
                if len(_g["items"]) == 1:
                    _renglon_del_pedido(_g["items"][0], hay_un_mapa=_hay_mapa)
                    continue
                _quien = (f"{_g['pedido_por'] or '¿?'} para "
                          f"{_g['cuenta'] or NOMBRE_DEL_MOSTRADOR}")
                # Un recuadro por pedido, con sus renglones adentro: a la vista se nota qué es de
                # quién aunque haya varios pedidos seguidos.
                with st.container(border=True):
                    _gc1, _gc2 = st.columns([3, 1])
                    _gc1.markdown(f"**🧾 Pedido de {texto_para_html(_quien)}** — "
                                  f"{len(_g['items'])} ítem(s) · {_hora_corta(_g['pedido_en'])} · "
                                  f"esperando {como_se_lee_la_espera(minutos_entre(_g['pedido_en']))}")
                    _gc2.button("✅ Entregar todo", key=f"dep_todo_{_g['tanda']}", width="stretch",
                                on_click=_entregar_todo, args=(_g["tanda"], f"Pedido de {_quien}"))
                    for _p in _g["items"]:
                        _renglon_del_pedido(_p, mostrar_quien=False, hay_un_mapa=_hay_mapa)

        _cola_del_deposito()

        # CUÁNTO TARDA: desde que el mostrador lo pide hasta que el depósito lo da de baja. Ver
        # «CUÁNTO TARDA EL DEPÓSITO» en logica/deposito.py.
        _tiempos = tiempos_del_deposito(dias=7)

        def _min(valor):
            return "—" if valor is None else f"{miles(valor, 1)} min"

        _t1, _t2, _t3 = st.columns(3)
        _t1.metric("⏱️ Hoy, en promedio", _min(_tiempos["hoy"]["promedio"]),
                   help=f"{_tiempos['hoy']['cuantos']} pedido(s) resueltos hoy, desde que se "
                        "pidieron hasta que el depósito los dio de baja.")
        _t2.metric("Hoy, el más lento", _min(_tiempos["hoy"]["maximo"]))
        _t3.metric(f"Últimos {_tiempos['dias']} días (mediana)", _min(_tiempos["periodo"]["mediana"]),
                   help="La mediana: la mitad tardó menos que esto. No la mueve un pedido que quedó "
                        "olvidado una hora, como al promedio.")
        if seccion_plegable("⏱️ Tiempos del depósito, por persona", key="deposito_tiempos"):
            if not _tiempos["por_persona"]:
                st.caption("Todavía no hay pedidos resueltos en estos días.")
            else:
                st.caption(f"Últimos {_tiempos['dias']} días. «A tiempo» es lo que tardó menos de "
                           f"{MINUTOS_PARA_AVISAR[0]} minutos.")
                st.dataframe([{"Quién lo dio de baja": _q, "Pedidos": _r["cuantos"],
                               "Promedio": _min(_r["promedio"]), "Mediana": _min(_r["mediana"]),
                               "El más lento": _min(_r["maximo"]), "A tiempo": f"{_r['a_tiempo']}%"}
                              for _q, _r in _tiempos["por_persona"].items()]
                             + [{"Quién lo dio de baja": "Todos", "Pedidos": _tiempos["periodo"]["cuantos"],
                                 "Promedio": _min(_tiempos["periodo"]["promedio"]),
                                 "Mediana": _min(_tiempos["periodo"]["mediana"]),
                                 "El más lento": _min(_tiempos["periodo"]["maximo"]),
                                 "A tiempo": f"{_tiempos['periodo']['a_tiempo']}%"}],
                             hide_index=True, width="stretch")

        # LO QUE ESTÁ AFUERA, en una línea: el detalle y la vuelta al stock están en «↩️
        # Devoluciones», para que con muchos pedidos esta pantalla no se haga eterna.
        _quienes = quien_tiene_que_devolver()
        if _quienes:
            _af1, _af2 = st.columns([3, 1])
            _af1.caption(f"📦 Afuera sin vender: {sum(g['unidades'] for g in _quienes)} unidad(es) "
                         f"a nombre de {len(_quienes)} persona(s)"
                         + (" · 🔴 hay cosas de hace más de "
                            f"{HORAS_PARA_AVISAR_LO_QUE_QUEDO_AFUERA} h"
                            if max(g["horas"] for g in _quienes) >= HORAS_PARA_AVISAR_LO_QUE_QUEDO_AFUERA
                            else "") + ".")
            _af2.button("↩️ Recibir →", key="deposito_ir_a_devoluciones", width="stretch",
                        on_click=ir_a_donde_dice_el_aviso, args=("↩️ Devoluciones → 📦 Al depósito",))

        # PARA FACTURAR: con precios, y con el descuento de cada cuenta. Plegado: la pantalla del
        # depósito puede estar a la vista de un cliente, y el descuento no lo tiene que ver.
        _a_facturar = para_facturar()
        if seccion_plegable(f"🧾 Para facturar ({len(_a_facturar)} cuenta(s))",
                            key="deposito_para_facturar"):
            st.caption("Lo entregado que todavía no se facturó, cuenta por cuenta. «Desc.» es el "
                       "descuento de esa cuenta (Administrar → 💳 Cuentas corrientes); lo cargado "
                       "en la cuenta ya lo lleva.")
            if not _a_facturar:
                st.caption("Nada para facturar.")
            for (_mid, _cuenta), _renglones in _a_facturar.items():
                _total = sum(float(r["importe"] or 0) for r in _renglones)
                with st.container(border=True):
                    st.markdown(f"**{texto_para_html(_cuenta)}** — {len(_renglones)} renglón(es), "
                                f"**{formato_precio(_total)}**")
                    st.dataframe([{"Entregado": _hora_corta(r["resuelto_en"]),
                                   "Código": f"{r['marca']} {r['codigo_raw']}",
                                   "Descripción": (r["descripcion"] or "")[:60],
                                   "Cant.": r["cantidad"],
                                   "Lista c/u": formato_precio(r["precio_lista"] or 0),
                                   "Desc.": f"{miles(r['descuento'] or 0, 1)}%",
                                   "Importe": formato_precio(r["importe"] or 0)}
                                  for r in _renglones], hide_index=True, width="stretch")
                    if st.button("✔️ Marcar facturado", key=f"dep_fact_{_mid or 0}"):
                        _n = marcar_facturado([r["id"] for r in _renglones])
                        st.session_state["_aviso_del_deposito"] = (
                            True, f"🧾 {_cuenta}: {_n} renglón(es) marcados como facturados.")
                        st.rerun()

        if seccion_plegable("🕓 Lo último que se resolvió", key="deposito_ultimos"):
            _ultimos = ultimos_pedidos_del_deposito()
            if not _ultimos:
                st.caption("Todavía nada.")
            else:
                st.dataframe([{"Cuándo": _hora_corta(r["resuelto_en"]),
                               "Qué": f"{r['marca']} {r['codigo_raw']} x{r['cantidad']}",
                               "Para": r["cuenta"] or NOMBRE_DEL_MOSTRADOR,
                               "Cómo": ESTADOS_DEL_PEDIDO.get(r["estado"], r["estado"]),
                               "Tardó": (como_se_lee_la_espera(minutos_entre(r["pedido_en"],
                                                                             r["resuelto_en"]))
                                         if r["estado"] != "cancelado" else ""),
                               "Pidió": r["pedido_por"] or "",
                               "Lo resolvió": r["resuelto_por"] or ""}
                              for r in _ultimos], hide_index=True, width="stretch")

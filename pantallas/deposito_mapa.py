"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/.

📦 Depósito → 🗺️ Mapa, 📍 Ubicar y 🏗️ Armar el depósito. Corre después de pantallas/deposito.py,
que elige la solapa."""

# ============================================================
# DEPÓSITO → EL MAPA: dónde está cada cosa, ubicar y armar las estanterías
# ============================================================
# Cómo funciona, en logica/mapa.py («EL MAPA DEL DEPÓSITO»).
if pagina == PAGINAS[8] and sub_deposito in SUB_DEPOSITO[1:]:
    _depositos = depositos_y_pisos()
    _pisos = [p_ for d_ in _depositos for p_ in d_["pisos"]]
    _por_id = {p_["id"]: p_ for p_ in _pisos}

    def _nombre_del_piso(piso_id):
        p_ = _por_id[piso_id]
        return f"{p_['deposito']} · {p_['nombre']}"

    def _dibujar_piso(piso_id, resaltados=(), camino=()):
        """El plano de un piso con lo resaltado (ver svg_del_piso())."""
        _est = estanterias_del_piso(piso_id)
        st.markdown(svg_del_piso(_por_id[piso_id]["plano"],
                                 {l_: e["codigo"] for l_, e in _est.items()}, resaltados, camino,
                                 lados={l_: e["lados"] for l_, e in _est.items()}),
                    unsafe_allow_html=True)
        if resaltados:
            st.caption(LEYENDA_DEL_MAPA)

    if sub_deposito != SUB_DEPOSITO[3] and not any(p_["plano"] for p_ in _pisos):
        st.info("🏗️ Todavía no está armado el mapa del depósito. Se arma en un minuto: cuántas "
                "filas de estanterías hay y de cuántos módulos.")
        st.button("🏗️ Ir a armarlo", key="mapa_ir_a_armar",
                  on_click=ir_a_donde_dice_el_aviso,
                  args=("📦 Depósito → 🏗️ Armar el depósito",))

    # ---------- 🗺️ MAPA: dónde está un repuesto ----------
    elif sub_deposito == SUB_DEPOSITO[1]:
        _q_mapa = st.text_input("🔎 ¿Dónde está? Escribí o escaneá el código:",
                                key="mapa_buscar",
                                placeholder="Ej: W712, el código de la caja, CH1400-5 o A-3")
        _piso_elegido, _resaltar, _producto_mapa = None, [], None
        if _q_mapa.strip():
            _que, _valor = que_es_lo_escaneado_al_ubicar(_q_mapa)
            if _que == "lugar":
                _piso_elegido = _valor["piso_id"]
                _resaltar = [(_valor["celdas"], "📍")]
                st.success(f"📍 {_valor['se_lee']}")
            elif _que == "producto":
                _producto_mapa = _valor
            else:
                # Un código de varias marcas, o el principio de uno: que elija.
                _candidatos = {p_["id"]: p_ for p_ in productos_para_etiquetar(_q_mapa)}
                if not _candidatos:
                    st.caption(_valor or "No encontré ningún producto con eso.")
                else:
                    _producto_mapa = (next(iter(_candidatos)) if len(_candidatos) == 1 else
                                      st.selectbox("Cuál:", list(_candidatos), key="mapa_cual",
                                                   format_func=lambda i: (
                                                       f"{_candidatos[i]['marca']} "
                                                       f"{_candidatos[i]['codigo_raw']} — "
                                                       f"{(_candidatos[i]['descripcion'] or '')[:40]}")))
        if _producto_mapa:
            c.execute("""SELECT p.codigo_raw, p.descripcion, p.stock, p.ubicacion,
                                m.nombre AS marca
                         FROM productos p JOIN marcas m ON m.id = p.marca_id WHERE p.id = ?""",
                      (_producto_mapa,))
            _f = c.fetchone()
            _donde = lugar_en_el_mapa(_f["ubicacion"])
            _nombre = f"{_f['marca']} {_f['codigo_raw']}"
            if _donde:
                _piso_elegido = _donde["piso_id"]
                _resaltar = [(_donde["celdas"], "📍")]
                st.success(f"📍 **{texto_para_html(_nombre)}** está en **{_donde['texto']}** — "
                           f"{texto_para_html(_donde['se_lee'])}"
                           + (f" · stock: {miles(_f['stock'])}" if _f["stock"] is not None else ""))
            else:
                st.warning(f"**{texto_para_html(_nombre)}** todavía no tiene lugar en el mapa"
                           + (f" (dice «{texto_para_html(_f['ubicacion'])}»)" if _f["ubicacion"]
                              else "") + ". Si sabés dónde está, anotalo:")
                with st.form("form_mapa_ubicar"):
                    _m1, _m2 = cols([3, 1], apilar_en_celular=False)
                    _lugar_nuevo = _m1.text_input("Lugar (estantería-módulo-estante):",
                                                  placeholder="A-3-2")
                    _guardar_lugar = _m2.form_submit_button("💾 Guardar", width="stretch")
                if _guardar_lugar:
                    _ok_l, _texto_l = ubicar_producto(_producto_mapa, _lugar_nuevo)
                    if _ok_l:
                        avisar("success", _texto_l)
                        st.rerun()
                    st.warning(_texto_l)
        _con_plano = [p_["id"] for p_ in _pisos if p_["plano"]]
        # Lo encontrado lleva a su piso, una vez: después se puede mirar otro.
        if _piso_elegido in _con_plano and st.session_state.get("_mapa_lo_buscado") != _q_mapa:
            st.session_state["mapa_piso"] = _piso_elegido
            st.session_state["_mapa_lo_buscado"] = _q_mapa
        if st.session_state.get("mapa_piso") not in _con_plano:
            st.session_state["mapa_piso"] = _con_plano[0]
        _piso_mapa = st.selectbox("Piso:", _con_plano, key="mapa_piso",
                                  format_func=_nombre_del_piso)
        # Lo que hay que buscar ahora en este piso, con su número: el mismo de «⏳ Para buscar».
        _cola_aca = next((g for g in la_cola_por_piso(pedidos_pendientes())
                          if g["piso_id"] == _piso_mapa), None)
        _con_cola = bool(_cola_aca) and st.toggle(
            f"⏳ Mostrar lo que hay que buscar ({len(_cola_aca['items']) if _cola_aca else 0})",
            value=not _resaltar, key="mapa_con_la_cola")
        if _con_cola:
            _numeros = {}
            for _p in _cola_aca["items"]:
                _numeros.setdefault(_p["donde"]["celdas"], []).append(str(_p["paso"]))
            _resaltar = _resaltar + [(cel, ",".join(n)) for cel, n in _numeros.items()]
        _dibujar_piso(_piso_mapa, [r for r in _resaltar if _piso_elegido == _piso_mapa
                                   or r[1] != "📍"],
                      _cola_aca["camino"] if _con_cola else ())
        # Qué hay en cada estantería: para ordenar, contar o buscar algo sin el código.
        _estantes = estanterias_del_piso(_piso_mapa)
        if _estantes:
            with st.expander("📚 Qué hay en cada estantería", key="exp_hay_cada_estanteria"):
                _est_elegida = st.selectbox("Estantería (o lado):",
                                            sorted(cod for e in _estantes.values()
                                                   for cod in codigos_de(e)),
                                            key="mapa_estanteria")
                _adentro = productos_en(_est_elegida)
                if not _adentro:
                    st.caption("Todavía no tiene nada ubicado.")
                else:
                    st.dataframe([{"Lugar": r["ubicacion"],
                                   "Producto": f"{r['marca']} {r['codigo_raw']}",
                                   "Descripción": (r["descripcion"] or "")[:40],
                                   "Stock": "" if r["stock"] is None else miles(r["stock"])}
                                  for r in _adentro], hide_index=True, width="stretch",
                                 height=min(36 * (len(_adentro) + 1) + 3, 400))

    # ---------- 📍 UBICAR: escaneando el estante y después lo que hay en él ----------
    elif sub_deposito == SUB_DEPOSITO[2]:
        ayuda(
            "La forma rápida de cargar el mapa: **escaneá la etiqueta del estante** (o escribí "
            "«A-3-2») y después **todo lo que hay en él** —la etiqueta nuestra, el código de "
            "barras de la caja o el código—: cada uno queda en ese lugar. Escaneá otro estante y "
            "seguí. Las etiquetas de los estantes se imprimen abajo. También se puede pegar una "
            "lista de Excel, y la app sugiere dónde poner lo que más se vende."
        )
        _hechos = st.session_state.setdefault("ubicar_hechos", [])
        with st.form("form_ubicar_escanear", clear_on_submit=True):
            _u1, _u2 = cols([3, 1], apilar_en_celular=False)
            _leido_u = _u1.text_input("Escaneá el estante o un producto:", key="ubicar_escaneo",
                                      placeholder="A-3-2, y después lo que hay ahí")
            _sumar_u = _u2.form_submit_button("➕ Listo", width="stretch")
        if _sumar_u and _leido_u.strip():
            _que_u, _valor_u = que_es_lo_escaneado_al_ubicar(_leido_u)
            if _que_u == "lugar":
                st.session_state["ubicar_lugar"] = _valor_u["texto"]
            elif _que_u == "producto" and not st.session_state.get("ubicar_lugar"):
                st.warning("Primero escaneá el estante (o escribí el lugar): después, todo lo "
                           "que escanees queda ahí.")
            elif _que_u == "producto":
                c.execute("SELECT ubicacion FROM productos WHERE id = ?", (_valor_u,))
                _antes_u = (c.fetchone() or {"ubicacion": None})["ubicacion"]
                _ok_u, _texto_u = ubicar_producto(_valor_u, st.session_state["ubicar_lugar"])
                if _ok_u:
                    _hechos.insert(0, {"id": _valor_u, "antes": _antes_u, "texto": _texto_u})
                    del _hechos[30:]
                else:
                    st.warning(_texto_u)
            else:
                st.warning(_valor_u)
        _lugar_u = lugar_en_el_mapa(st.session_state.get("ubicar_lugar"))
        if _lugar_u:
            st.success(f"📍 Ahora todo va a **{_lugar_u['texto']}** — {_lugar_u['se_lee']}")
            if _lugar_u["piso_id"] in _por_id:
                _dibujar_piso(_lugar_u["piso_id"], [(_lugar_u["celdas"], "📍")])
        if _hechos:
            st.markdown(f"**Ubicados recién: {len(_hechos)}**")
            for _h in _hechos[:10]:
                st.caption(_h["texto"])
            if st.button("↩️ Deshacer el último", key="ubicar_deshacer"):
                _ultimo_u = _hechos[0]
                _ok_d, _texto_d = ubicar_producto(_ultimo_u["id"], _ultimo_u["antes"] or "")
                if _ok_d:
                    _hechos.pop(0)
                    avisar("success", f"↩️ Deshecho: {_texto_d}")
                    st.rerun()
                st.warning(_texto_d)

        with st.expander("📋 Pegar una lista (de Excel)", key="exp_pegar_lista_excel"):
            st.caption("Un renglón por producto: el código y al final el lugar, por ejemplo "
                       "«W712 A-3-2». Sirve copiar dos columnas de Excel y pegarlas acá.")
            _lista_u = st.text_area("Lista:", key="ubicar_lista", height=150,
                                    placeholder="W712 A-3-2\n0986AF0051 B-1-1")
            if _lista_u.strip():
                _revision = ubicar_de_una_lista(_lista_u)
                _bien = [f for f in _revision if not f["Problema"]]
                st.dataframe([{k: v for k, v in f.items() if not k.startswith("_")}
                              for f in _revision], hide_index=True, width="stretch",
                             height=min(36 * (len(_revision) + 1) + 3, 320))
                if _bien and st.button(f"💾 Ubicar los {len(_bien)} que están bien",
                                       key="ubicar_lista_guardar", type="primary"):
                    _hecho_lista = ubicar_de_una_lista(_lista_u, guardar=True)
                    avisar("success", f"📍 Ubicados: "
                           f"{sum(1 for f in _hecho_lista if f.get('Guardado'))} producto(s).")
                    st.rerun()

        with st.expander("🏷️ Etiquetas de los estantes", key="exp_etiquetas_estantes"):
            st.caption("Una por módulo y estante, con su código de barras: pegala en el estante "
                       "y escaneándola arriba todo lo que escanees después queda ahí.")
            _todas_est = {e["id"]: f"{_nombre_del_piso(p_['id'])} · {e['codigo']}"
                                   + (f" (lados {', '.join(codigos_de(e)[1:])})"
                                      if e["lados"] else "")
                          for p_ in _pisos for e in estanterias_del_piso(p_["id"]).values()}
            _elegidas_et = st.multiselect("Estanterías:", list(_todas_est),
                                          format_func=_todas_est.get, key="ubicar_etiquetas",
                                          placeholder="Elegí una o más")
            if _elegidas_et:
                st.download_button(f"🏷️ Bajar las etiquetas ({len(_elegidas_et)} estantería(s))",
                                   data=etiquetas_de_ubicaciones_para_descargar(_elegidas_et),
                                   file_name="etiquetas_de_los_estantes.pdf",
                                   mime="application/pdf", key="ubicar_etiquetas_pdf")

        with st.expander("💡 Dónde poner lo que no tiene lugar", key="exp_donde_poner_lo_no"):
            st.caption("Lo que más se vende (y si no, lo que tiene stock), en los lugares libres "
                       "más a mano: cerca de la entrada y a la altura de la cintura. Llevalo ahí "
                       "y confirmalo.")
            _sugeridos = lugares_sugeridos()
            if not _sugeridos:
                st.caption("Nada para sugerir: o todo lo que se mueve ya tiene lugar, o no "
                           "quedan lugares libres.")
            for _s in _sugeridos:
                _s1, _s2 = cols([4, 1], apilar_en_celular=False)
                _s1.markdown(f"**{texto_para_html(_s['producto'])}** → **{_s['lugar']}** "
                             f"<span style='opacity:.7'>· {texto_para_html(_s['descripcion'])} · "
                             f"{_s['por_que']}</span>", unsafe_allow_html=True)
                if _s2.button("📍 Ubicar ahí", key=f"ubicar_sugerido_{_s['producto_id']}",
                              width="stretch"):
                    _ok_s, _texto_s = ubicar_producto(_s["producto_id"], _s["lugar"])
                    avisar("success" if _ok_s else "warning", _texto_s)
                    st.rerun()

    # ---------- 🏗️ ARMAR EL DEPÓSITO ----------
    elif sub_deposito == SUB_DEPOSITO[3]:
        ayuda(
            "Primero el depósito y el piso; después el plano: **⚡ Armado rápido** lo arma con "
            "cuántas filas de estanterías hay y de cuántos módulos, y lo retocás sumando, moviendo "
            "o sacando estanterías. Cada **módulo** es un casillero a lo largo de la estantería "
            "(de izquierda a derecha, o de arriba a abajo si está parada) y cada uno tiene sus "
            "**estantes**, de abajo hacia arriba: la ubicación «A-3-2» es la estantería A, "
            "módulo 3, estante 2. Nada se guarda hasta tocar **💾 Guardar el plano**. Si te "
            "animás, también se dibuja a mano con letras: «.» pasillo, «#» pared, «@» entrada."
        )
        # El depósito y el piso: elegir uno, o crear uno nuevo.
        _NUEVO = 0
        _ids_dep = [d_["id"] for d_ in _depositos] + [_NUEVO]
        _nombres_dep = {d_["id"]: d_["nombre"] for d_ in _depositos}
        _a1, _a2 = cols([1, 1])
        valor_del_campo("armar_deposito", None)     # lo recién creado (ver poner_en_el_campo())
        if st.session_state.get("armar_deposito") not in _ids_dep:
            st.session_state["armar_deposito"] = _ids_dep[0]
        _dep_id = _a1.selectbox("Depósito:", _ids_dep, key="armar_deposito",
                                format_func=lambda i: _nombres_dep.get(i, "➕ Uno nuevo"))
        _piso_id = None
        if _dep_id == _NUEVO:
            with _a1.form("form_armar_deposito_nuevo"):
                _nombre_dep = st.text_input("Nombre del depósito:", placeholder="Ej: Central")
                _crear_dep = st.form_submit_button("➕ Crear el depósito")
            if _crear_dep:
                _nuevo_piso, _texto_dep = crear_deposito(_nombre_dep)
                if _nuevo_piso:
                    poner_en_el_campo("armar_deposito", next(
                        d_["id"] for d_ in depositos_y_pisos()
                        if any(p_["id"] == _nuevo_piso for p_ in d_["pisos"])))
                    poner_en_el_campo("armar_piso", _nuevo_piso)
                    avisar("success", _texto_dep)
                    st.rerun()
                st.warning(_texto_dep)
        else:
            _dep = next(d_ for d_ in _depositos if d_["id"] == _dep_id)
            _ids_piso = [p_["id"] for p_ in _dep["pisos"]] + [_NUEVO]
            valor_del_campo("armar_piso", None)
            if st.session_state.get("armar_piso") not in _ids_piso:
                st.session_state["armar_piso"] = _ids_piso[0]
            _piso_id = _a2.selectbox("Piso:", _ids_piso, key="armar_piso",
                                     format_func=lambda i: (_por_id[i]["nombre"] if i in _por_id
                                                            else "➕ Uno nuevo"))
            if _piso_id == _NUEVO:
                with _a2.form("form_armar_piso_nuevo"):
                    _nombre_piso = st.text_input("Nombre del piso:",
                                                 placeholder="Ej: Primer piso, Entrepiso")
                    _crear_piso = st.form_submit_button("➕ Crear el piso")
                if _crear_piso:
                    _nuevo_piso, _texto_piso = crear_piso(_dep_id, _nombre_piso)
                    if _nuevo_piso:
                        poner_en_el_campo("armar_piso", _nuevo_piso)
                        avisar("success", _texto_piso)
                        st.rerun()
                    st.warning(_texto_piso)
                _piso_id = None

        if _piso_id:
            _guardado = _por_id[_piso_id]["plano"]
            # EL BORRADOR: lo que se va armando, en la sesión hasta guardarlo. Así se prueba
            # tranquilo y se ve en el dibujo antes de que cambie para todos.
            _clave_borrador = f"armar_borrador_{_piso_id}"
            if _clave_borrador not in st.session_state:
                st.session_state[_clave_borrador] = _guardado
            _borrador = st.session_state[_clave_borrador]

            def _cambiar_borrador(texto):
                st.session_state[_clave_borrador] = texto
                poner_en_el_campo(f"plano_a_mano_{_piso_id}", texto)

            _leido = leer_plano(_borrador)
            for _error in _leido["errores"]:
                st.warning(_error)

            with st.expander("⚡ Armado rápido", expanded=not _leido["estanterias"], key="exp_armado_rapido"):
                st.caption("Filas de estanterías paralelas, con pasillo alrededor de cada una, "
                           "paredes y la entrada abajo. Después lo retocás.")
                with st.form("form_armado_rapido"):
                    _r1, _r2, _r3 = cols([1, 1, 1])
                    _hileras = _r1.number_input("Filas de estanterías:", 1, 12, 3, step=1)
                    _por_hilera = _r2.number_input("Estanterías por fila:", 1, 8, 2, step=1)
                    _modulos = _r3.number_input("Módulos de cada una:", 1, 20, 5, step=1)
                    _r4, _r5, _r6 = cols([1, 1, 1])
                    _pasillo = _r4.number_input("Ancho del pasillo:", 1, 4, 1, step=1)
                    _fondo = _r5.number_input("Fondo de cada estantería:", 1, 3, 1, step=1,
                                              help="2 si es de doble faz y se saca de los dos "
                                                   "lados.")
                    _estantes_rapido = _r6.number_input("Estantes de alto:", 1, 20, 4, step=1)
                    _usar_rapido = st.form_submit_button("⚡ Armar este plano", type="primary")
                if _usar_rapido:
                    try:
                        _cambiar_borrador(armado_rapido(_hileras, _por_hilera, _modulos,
                                                        _pasillo, _fondo))
                        st.session_state[f"armar_estantes_{_piso_id}"] = int(_estantes_rapido)
                        st.rerun()
                    except ValueError as _err:
                        st.warning(str(_err))

            st.markdown("**El plano**" + (" — ✏️ con cambios sin guardar"
                                          if _borrador != _guardado else ""))
            if _leido["filas"]:
                _est_armar = estanterias_del_piso(_piso_id)
                _codigos_armar = {l_: e["codigo"] for l_, e in _est_armar.items()}
                st.markdown(svg_del_piso(_borrador, _codigos_armar,
                                         lados={l_: e["lados"] for l_, e in _est_armar.items()}),
                            unsafe_allow_html=True)
                st.caption(f"{_leido['ancho']} columnas × {_leido['alto']} filas · "
                           f"{len(_leido['estanterias'])} estantería(s)"
                           + ("" if _leido["entrada"] else " · ⚠️ sin entrada («@»): se arranca "
                              "de arriba a la izquierda"))
            else:
                st.caption("Vacío: armalo con «⚡ Armado rápido» o sumá estanterías.")

            _t1, _t2 = cols([1, 1])
            with _t1.expander("➕ Sumar una estantería", key="exp_sumar_estanteria"):
                with st.form("form_sumar_estanteria"):
                    _e1, _e2 = cols([1, 1], apilar_en_celular=False)
                    _col_e = _e1.number_input("Columna:", 1, TAMANO_MAXIMO_DEL_PLANO[0], 2,
                                              step=1, help="La de los números de arriba.")
                    _fila_e = _e2.number_input("Fila:", 1, TAMANO_MAXIMO_DEL_PLANO[1], 2, step=1,
                                               help="La de los números del costado.")
                    _e3, _e4 = cols([1, 1], apilar_en_celular=False)
                    _largo_e = _e3.number_input("Módulos:", 1, TAMANO_MAXIMO_DEL_PLANO[0], 4,
                                                step=1)
                    _fondo_e = _e4.number_input("Fondo:", 1, 3, 1, step=1)
                    _acostada = st.radio("Cómo va:", ["↔️ Acostada (de izquierda a derecha)",
                                                      "↕️ Parada (de arriba a abajo)"],
                                         horizontal=True)
                    _sumar_e = st.form_submit_button("➕ Sumarla")
                if _sumar_e:
                    try:
                        _texto_e, _letra_e = sumar_estanteria(_borrador, _col_e, _fila_e, _largo_e,
                                                              _acostada.startswith("↔️"), _fondo_e)
                        _cambiar_borrador(_texto_e)
                        avisar("success", f"➕ Estantería {_letra_e} sumada (falta guardar).")
                        st.rerun()
                    except ValueError as _err:
                        st.warning(str(_err))
            with _t2.expander("↔️ Mover o sacar una", key="exp_mover_o_sacar"):
                if not _leido["estanterias"]:
                    st.caption("Todavía no hay estanterías.")
                else:
                    _letra_m = st.selectbox("Estantería:", list(_leido["estanterias"]),
                                            key=f"armar_mover_{_piso_id}",
                                            format_func=lambda l_: _codigos_armar.get(l_, l_))
                    _flechas = cols([1, 1, 1, 1, 1], apilar_en_celular=False)
                    for _i_f, (_rot, _dx, _dy) in enumerate((("⬅️", -1, 0), ("➡️", 1, 0),
                                                             ("⬆️", 0, -1), ("⬇️", 0, 1))):
                        if _flechas[_i_f].button(_rot, key=f"armar_flecha_{_i_f}", width="stretch"):
                            try:
                                _cambiar_borrador(mover_estanteria(_borrador, _letra_m, _dx, _dy))
                                st.rerun()
                            except ValueError as _err:
                                st.warning(str(_err))
                    if _flechas[4].button("🗑️", key="armar_sacar", width="stretch",
                                          help="Sacarla del plano (queda pasillo)."):
                        _cambiar_borrador(sacar_estanteria(_borrador, _letra_m))
                        st.rerun()

            with st.expander("✏️ Dibujarlo a mano", key="exp_dibujarlo_mano"):
                st.caption("Una letra por estantería (A–Z, 1–9), «.» pasillo, «#» pared, «@» "
                           "entrada. Cada renglón es una fila del depósito.")
                _clave_mano = f"plano_a_mano_{_piso_id}"
                _a_mano = st.text_area("Plano:", value=valor_del_campo(_clave_mano, _borrador),
                                       key=_clave_mano, height=260,
                                       label_visibility="collapsed")
                if _a_mano != _borrador and st.button("👀 Usar lo dibujado", key="armar_a_mano"):
                    st.session_state[_clave_borrador] = _a_mano
                    st.rerun()

            _g1, _g2 = cols([1, 1])
            if _borrador != _guardado:
                _perdidas = lo_que_se_pierde_con(_piso_id, _borrador)
                if _perdidas:
                    st.warning("Así quedarían productos fuera del mapa: "
                               + "; ".join(f"la {cod} ({n} producto(s)) {por_que}"
                                           for cod, n, por_que in _perdidas) + ".")
                if _g1.button("💾 Guardar el plano" + (" igual" if _perdidas else ""),
                              type="primary", key="armar_guardar", width="stretch"):
                    _ok_p, _texto_p, _ = guardar_plano(_piso_id, _borrador,
                                                       aunque_se_pierdan=bool(_perdidas))
                    if _ok_p:
                        # Los estantes del armado rápido, a las estanterías nuevas.
                        _estantes_nuevos = st.session_state.pop(f"armar_estantes_{_piso_id}",
                                                                None)
                        if _estantes_nuevos:
                            for _e in estanterias_del_piso(_piso_id).values():
                                guardar_estanteria(_e["id"], _e["codigo"], _estantes_nuevos)
                        avisar("success", _texto_p)
                        st.rerun()
                    st.warning(_texto_p)
                if _g2.button("↩️ Descartar los cambios", key="armar_descartar", width="stretch"):
                    _cambiar_borrador(_guardado)
                    st.rerun()

            # Los códigos y los estantes de cada estantería guardada.
            _est_guardadas = estanterias_del_piso(_piso_id)
            if _est_guardadas:
                with st.expander(f"🔤 Códigos y estantes ({len(_est_guardadas)} estantería(s))", key="exp_codigos_estantes_estanteria_s"):
                    st.caption("El código es lo que se escribe en la ubicación («A» en «A-3-2»): "
                               "si lo cambiás, lo que estaba ubicado ahí pasa al código nuevo. "
                               "Los estantes se cuentan de abajo hacia arriba.")
                    _cuantos = cuantos_hay_en_cada_estanteria()
                    with st.form(f"form_armar_codigos_{_piso_id}"):
                        _valores = {}
                        _h1, _h2, _h3 = cols([2, 2, 2], apilar_en_celular=False)
                        _h1.caption("En el plano")
                        _h2.caption("Código")
                        _h3.caption("Estantes")
                        for l_, e in sorted(_est_guardadas.items()):
                            _x1, _x2, _x3 = cols([2, 2, 2], apilar_en_celular=False)
                            _x1.markdown(f"**{l_}** · {miles(sum(_cuantos.get(cod.upper(), 0) for cod in codigos_de(e)))} "
                                         "producto(s)")
                            _valores[l_] = (
                                _x2.text_input("Código", e["codigo"], key=f"armar_cod_{e['id']}",
                                               label_visibility="collapsed", max_chars=6),
                                _x3.number_input("Estantes", 1, 20, int(e["niveles"] or 1),
                                                 key=f"armar_niv_{e['id']}",
                                                 label_visibility="collapsed"))
                        _guardar_cod = st.form_submit_button("💾 Guardar códigos y estantes")
                    if _guardar_cod:
                        _mensajes = [guardar_estanteria(_est_guardadas[l_]["id"], cod, niv)
                                     for l_, (cod, niv) in _valores.items()
                                     if (str(cod).strip().upper()
                                         != _est_guardadas[l_]["codigo"].upper()
                                         or int(niv) != _est_guardadas[l_]["niveles"])]
                        for _ok_t, _texto_t in _mensajes:
                            (st.success if _ok_t else st.warning)(_texto_t)
                        if not _mensajes:
                            st.caption("No había nada distinto para guardar.")

                # LOS CUATRO LADOS: cada lado de una línea con su propio código, como está
                # pintado en el depósito. Ver «LOS CUATRO LADOS» en logica/mapa.py.
                with st.expander("🧭 Los cuatro lados de cada estantería", key="exp_cuatro_lados_cada_estanteria"):
                    explicar("Si cada lado de una línea tiene su número o su letra, escribilo "
                             "acá (arriba, abajo, izquierda y derecha son los del dibujo).",
                             "Cada lado con código es un lugar más («B-3-2»): se llega por el "
                             "pasillo de ese lado y tiene sus propias etiquetas. Vacío: ese lado "
                             "no tiene. Si cambiás uno, lo ubicado ahí pasa al código nuevo; si "
                             "lo borrás, a la estantería, en el mismo módulo.",
                             en_expander=True)
                    with st.form(f"form_armar_lados_{_piso_id}"):
                        _lados_nuevos = {}
                        _encabezado = cols([1.4, 1, 1, 1, 1], apilar_en_celular=False)
                        _encabezado[0].caption("Estantería")
                        for _col_l, _nombre_l in zip(_encabezado[1:], LADOS.values()):
                            _col_l.caption(_nombre_l)
                        for l_, e in sorted(_est_guardadas.items()):
                            _fila_l = cols([1.4, 1, 1, 1, 1], apilar_en_celular=False)
                            _fila_l[0].markdown(f"**{e['codigo']}**")
                            _lados_nuevos[l_] = {
                                lado: _col_l.text_input(
                                    _nombre_l, e["lados"].get(lado, ""), max_chars=6,
                                    key=f"armar_lado_{e['id']}_{lado}",
                                    label_visibility="collapsed")
                                for _col_l, (lado, _nombre_l) in zip(_fila_l[1:], LADOS.items())}
                        _guardar_lados = st.form_submit_button("💾 Guardar los lados")
                    if _guardar_lados:
                        _mensajes_l = [guardar_lados(_est_guardadas[l_]["id"], cods)
                                       for l_, cods in _lados_nuevos.items()
                                       if {k_: v_.strip().upper() for k_, v_ in cods.items() if v_.strip()}
                                       != {k_: v_.upper() for k_, v_ in _est_guardadas[l_]["lados"].items()}]
                        # Todo bien: de nuevo, para que el dibujo de arriba ya los muestre.
                        if _mensajes_l and all(_ok_l for _ok_l, _ in _mensajes_l):
                            for _, _texto_l in _mensajes_l:
                                avisar("success", _texto_l)
                            st.rerun()
                        for _ok_l, _texto_l in _mensajes_l:
                            (st.success if _ok_l else st.warning)(_texto_l)
                        if not _mensajes_l:
                            st.caption("No había nada distinto para guardar.")

                # Cómo ordena la cola este piso (también se elige en «⏳ Para buscar»).
                with st.form(f"form_armar_orden_{_piso_id}"):
                    _o_actual = _por_id[_piso_id]["orden_de_la_cola"]
                    _modo_o = st.radio("Cómo ordena la cola este piso:",
                                       list(ORDENES_DE_LA_COLA),
                                       index=list(ORDENES_DE_LA_COLA).index(_o_actual)
                                       if _o_actual in ORDENES_DE_LA_COLA else 0,
                                       format_func=ORDENES_DE_LA_COLA.get)
                    _min_o = st.number_input("Minutos para seguir desde lo último entregado:",
                                             0.25, 120.0,
                                             float(_por_id[_piso_id]["minutos_de_cercania"]),
                                             step=0.25)
                    if st.form_submit_button("💾 Guardar el orden"):
                        _ok_o, _texto_o = elegir_orden_de_la_cola(_piso_id, _modo_o, _min_o)
                        (st.success if _ok_o else st.warning)(_texto_o)

            # Borrar, solo el administrador, y diciendo qué pasa con lo ubicado.
            if es_admin():
                with st.expander("🗑️ Borrar este piso o el depósito", key="exp_borrar_este_piso_o"):
                    _cuantos_b = cuantos_hay_en_cada_estanteria()
                    _ubicados = sum(_cuantos_b.get(cod.upper(), 0)
                                    for e in estanterias_del_piso(_piso_id).values()
                                    for cod in codigos_de(e))
                    st.caption(f"Los {miles(_ubicados)} producto(s) ubicados en este piso "
                               "conservan lo que tienen escrito, pero deja de estar en el mapa.")
                    _b1, _b2 = cols([1, 1])
                    if _b1.button(f"🗑️ Borrar el piso «{_por_id[_piso_id]['nombre']}»",
                                  key="armar_borrar_piso"):
                        borrar_piso(_piso_id)
                        avisar("success", "🗑️ Piso borrado.")
                        st.rerun()
                    if _b2.button(f"🗑️ Borrar el depósito «{_por_id[_piso_id]['deposito']}» entero",
                                  key="armar_borrar_deposito"):
                        borrar_deposito(_por_id[_piso_id]["deposito_id"])
                        avisar("success", "🗑️ Depósito borrado.")
                        st.rerun()

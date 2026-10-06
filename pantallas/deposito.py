"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/."""

# ============================================================
# DEPÓSITO: lo que pidió el mostrador, y lo que queda para facturar
# ============================================================
# Cómo funciona, en logica/deposito.py («EL DEPÓSITO: DEL MOSTRADOR A LA CUENTA»).
if pagina == PAGINAS[8]:
    ayuda(
        "Acá llega lo que el mostrador pide con «📦 Pedir al depósito» en el buscador. Está "
        "ordenado por **ubicación**, para juntarlo todo en una vuelta. **✅ Entregado** lo da de "
        "baja: descuenta el stock, anota la venta y, si es para la cuenta de un taller o un "
        "mayorista, lo carga en su cuenta. **❌ No hay** lo manda a 📊 Estadísticas → 📌 Para "
        "pedir. Acá no se ven precios."
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

    _sola = st.toggle("🔄 Que se actualice sola", value=True, key="deposito_actualizar_sola",
                      help="Cada 20 segundos mira si llegaron pedidos nuevos, sin tocar nada.")

    @st.fragment(run_every=20 if _sola else None)
    def _cola_del_deposito():
        _aviso = st.session_state.pop("_aviso_del_deposito", None)
        if _aviso:
            (st.success if _aviso[0] else st.warning)(_aviso[1])
        _pendientes = pedidos_pendientes()
        st.markdown(f"#### ⏳ Para buscar: {len(_pendientes)}")
        if not _pendientes:
            st.caption("Nada pendiente. Lo que pidan desde el buscador aparece acá solo.")
        for _p in _pendientes:
            _rotulo = f"{_p['marca']} {_p['codigo_raw']} x{_p['cantidad']}"
            with st.container(border=True):
                _ca, _cb = st.columns([3, 2])
                _ca.markdown(f"📍 **{texto_para_html(_p['ubicacion']) or 'sin ubicación'}** · "
                             f"**{texto_para_html(_p['marca'])} {texto_para_html(_p['codigo_raw'])}**"
                             f" × **{_p['cantidad']}**")
                _detalle = [(_p["descripcion"] or "")[:90],
                            f"para {_p['cuenta'] or NOMBRE_DEL_MOSTRADOR}",
                            f"pidió {_p['pedido_por'] or '¿?'} a las {_hora_corta(_p['pedido_en'])}"]
                if _p["stock"] is not None:
                    _detalle.append(f"stock: {_p['stock']}")
                _ca.caption(" · ".join(x for x in _detalle if x))
                if _p["nota"]:
                    _ca.info(f"📝 {_p['nota']}")
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

    _cola_del_deposito()

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
                           "Quién": r["resuelto_por"] or ""}
                          for r in _ultimos], hide_index=True, width="stretch")

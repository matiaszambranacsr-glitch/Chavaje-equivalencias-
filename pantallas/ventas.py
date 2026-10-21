"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/."""

# ============================================================
# VENTAS: cobrar, descontar el stock y anotarlo en la ficha del auto
# ============================================================
# Cómo funciona, en logica/ventas.py («VENTAS DEL MOSTRADOR»).
if pagina == PAGINAS[9]:
    ayuda(
        "Buscá lo que se lleva el cliente y sumalo; corregí la cantidad o el precio si hace "
        "falta. **✅ Terminar la venta** descuenta el stock (nunca queda negativo: si no "
        "alcanzaba, avisa para contarlo) y anota lo vendido, que es con lo que la app aprende "
        "qué se vende en lugar de qué. Al terminar te pregunta **la patente y los km**: con eso "
        "cada pieza queda en la ficha del auto, y el cliente ve en su link cuánto le falta a "
        "cada cosa. Para cargarlo a la cuenta de un taller, pedilo al depósito con la cuenta "
        "elegida."
    )
    venta_items = st.session_state.setdefault("venta_items", [])
    recien = st.session_state.get("venta_recien_cerrada")

    if recien:
        # LA VENTA RECIÉN TERMINADA: lo que pidió el dueño, la patente y los km.
        st.success(f"✅ Venta #{recien['id']} terminada: **${miles(recien['total'], 0)}**.")
        for _aviso in recien.get("avisos") or []:
            st.warning(f"⚠️ {_aviso}")
        anotada = recien.get("anotada")
        if not anotada:
            st.markdown("**🚗 ¿Querés anotar la patente y los km?**")
            st.caption("Así queda en la ficha del auto qué se le puso y a qué km, y la app sabe "
                       "cuándo le toca de nuevo.")
            with st.form("form_venta_al_auto"):
                _v1, _v2 = cols([1, 1])
                _pat_v = _v1.text_input("Patente:", placeholder="AB123CD", max_chars=12)
                _km_v = _v2.number_input("Km del auto hoy:", min_value=0, max_value=2_000_000,
                                         step=1000, value=None, placeholder="Ej: 87500")
                _v3, _v4 = cols([1, 1])
                _cli_v = _v3.text_input("Nombre del cliente (opcional):",
                                        value=recien.get("cliente") or "")
                _tel_v = _v4.text_input("Teléfono (opcional):",
                                        help="Para mandarle el link de su auto y avisarle "
                                             "cuando le toque.")
                st.caption("Cómo se va a llamar cada pieza en la ficha (corregilo si hace falta: "
                           "con el mismo nombre la app sabe cuándo fue el último cambio).")
                _piezas_v = {}
                for _it in recien["items"]:
                    _piezas_v[_it["id"]] = st.text_input(
                        f"{_it['marca']} {_it['codigo']}", value=nombre_de_la_pieza(_it["descripcion"]),
                        key=f"pieza_venta_{recien['id']}_{_it['id']}")
                _menos_v = st.checkbox("Son menos km que la última vez y están bien",
                                       key=f"menos_km_venta_{recien['id']}")
                _anotar_v = st.form_submit_button("💾 Anotar en la ficha del auto", type="primary")
            if _anotar_v:
                if _km_v is None:
                    st.warning("Escribí los km del auto.")
                else:
                    _ok_v, _texto_v, _vid_v = anotar_la_venta_en_el_auto(
                        recien["id"], _pat_v, _km_v, _piezas_v, _cli_v, _tel_v, _menos_v)
                    if _ok_v:
                        recien["anotada"] = {"texto": _texto_v, "vehiculo_id": _vid_v}
                        st.rerun()
                    st.warning(_texto_v)
            if st.button("No, gracias — nueva venta", key="venta_sin_patente"):
                st.session_state.pop("venta_recien_cerrada", None)
                st.rerun()
        else:
            st.success(f"🚗 {anotada['texto']}")
            _vehiculo_v = buscar_vehiculo_por_id(anotada["vehiculo_id"])
            _link_v = link_publico_del_auto(anotada["vehiculo_id"])
            _tel_cliente_v = re.sub(r"\D", "", (_vehiculo_v or {}).get("cliente_telefono") or "")
            _msj_v = (f"Hola {(_vehiculo_v or {}).get('cliente_nombre') or ''}! Gracias por tu "
                      f"compra. Acá podés ver lo que le pusimos a tu auto y cuánto le falta a "
                      f"cada cosa: {_link_v}").replace("Hola !", "Hola!")
            _w1, _w2 = cols([1, 1])
            _w1.link_button("📲 Mandarle el link de su auto",
                            (f"https://wa.me/{_tel_cliente_v}" if _tel_cliente_v
                             else "https://wa.me/") + "?text=" + quote(_msj_v), width="stretch")
            if _w2.button("➕ Nueva venta", type="primary", key="venta_nueva", width="stretch"):
                st.session_state.pop("venta_recien_cerrada", None)
                st.rerun()
    else:
        # ARMAR LA VENTA
        with st.form("form_buscar_para_vender", clear_on_submit=False):
            _q1, _q2 = cols([4, 1])
            _texto_vta = _q1.text_input("Código o descripción:", key="venta_buscar",
                                        placeholder="Ej: W712/94 o filtro aceite gol")
            _buscar_vta = _q2.form_submit_button("🔍 Buscar")
        if _buscar_vta and _texto_vta.strip():
            _clean_vta = sanitizar(_texto_vta)
            _res_vta = buscar_con_variantes_del_cero(_clean_vta, "Todas", 3)[0] if _clean_vta else []
            if not _res_vta:
                _res_vta = buscar_por_texto(_texto_vta)
            st.session_state["venta_resultados"] = ([dict(f) for f in _res_vta[:15]],
                                                    _texto_vta.strip())
        _resultados_vta, _pedido_vta = st.session_state.get("venta_resultados", ([], ""))
        if _resultados_vta:
            st.caption(f"{len(_resultados_vta)} resultado(s) para «{_pedido_vta}»: «➕» lo suma "
                       "a la venta.")
            for _f in _resultados_vta:
                _r1, _r2 = cols([5, 1], apilar_en_celular=False)
                _stock_f = _f.get("Stock")
                _r1.write(f"**{_f['Marca']} {_f['Codigo']}** — {(_f.get('Descripcion') or '')[:60]}"
                          f" · ${miles(_f.get('Precio') or 0, 0)}"
                          f" · stock {_stock_f if _stock_f is not None else 's/d'}")
                if _r2.button("➕", key=f"sumar_venta_{_f['ID']}"):
                    _ya = next((x for x in venta_items if x["producto_id"] == _f["ID"]), None)
                    if _ya:
                        _ya["cantidad"] += 1
                        # El campo de la cantidad guarda lo suyo: sin esto, el «+1» no se veía.
                        st.session_state.pop(f"venta_cant_{_f['ID']}", None)
                    else:
                        _nuevo = item_de_venta(_f["ID"], 1, _pedido_vta)
                        if _nuevo:
                            venta_items.append(_nuevo)
                    st.rerun()
        elif _buscar_vta:
            st.info("No encontré ese código ni esa descripción.")

        st.markdown("---")
        if not venta_items:
            st.info("La venta está vacía: buscá lo que se lleva el cliente, o pasá un "
                    "presupuesto del 🔍 Buscador con «🧾 Pasar a una venta».")
        else:
            st.markdown(f"**🧾 La venta ({len(venta_items)} ítem(s))**")
            for _it in list(venta_items):
                _k = _it["producto_id"]
                _c1, _c2, _c3, _c4 = cols([4, 1.2, 1.6, 0.7], apilar_en_celular=False)
                _c1.write(f"**{_it['marca']} {_it['codigo']}** — {(_it['descripcion'] or '')[:50]}")
                _it["cantidad"] = int(_c2.number_input(
                    "Cant.", min_value=1, max_value=CANTIDAD_MAXIMA_POR_PEDIDO,
                    value=int(_it["cantidad"]), step=1, key=f"venta_cant_{_k}",
                    label_visibility="collapsed"))
                _it["precio"] = float(_c3.number_input(
                    "Precio", min_value=0.0, value=float(_it["precio"]), step=100.0,
                    key=f"venta_precio_{_k}", label_visibility="collapsed"))
                if _c4.button("🗑️", key=f"venta_quitar_{_k}"):
                    venta_items.remove(_it)
                    st.session_state.pop(f"venta_cant_{_k}", None)
                    st.session_state.pop(f"venta_precio_{_k}", None)
                    st.rerun()
            _total_vta = sum(x["cantidad"] * x["precio"] for x in venta_items)
            st.markdown(f"### Total: ${miles(_total_vta, 0)}")
            _p1, _p2 = cols([1, 1])
            _cliente_vta = _p1.text_input("Cliente (opcional):", key="venta_cliente")
            _forma_vta = _p2.selectbox("Forma de pago:", FORMAS_DE_PAGO, key="venta_forma")
            if st.button("✅ Terminar la venta", type="primary", key="venta_terminar",
                         width="stretch"):
                try:
                    _id_vta, _avisos_vta = cerrar_venta(venta_items, _cliente_vta, _forma_vta)
                except (ValueError, PermissionError) as _err:
                    st.error(str(_err))
                else:
                    c.execute("""SELECT id, codigo, marca, descripcion FROM ventas_items
                                 WHERE venta_id = ? ORDER BY id""", (_id_vta,))
                    st.session_state["venta_recien_cerrada"] = {
                        "id": _id_vta, "total": _total_vta, "avisos": _avisos_vta,
                        "cliente": _cliente_vta, "items": [dict(f) for f in c.fetchall()]}
                    for _it in venta_items:
                        st.session_state.pop(f"venta_cant_{_it['producto_id']}", None)
                        st.session_state.pop(f"venta_precio_{_it['producto_id']}", None)
                    st.session_state["venta_items"] = []
                    st.session_state.pop("venta_resultados", None)
                    st.rerun()

    # LAS VENTAS DE HOY
    _hoy_vta = ventas_del_dia()
    _validas = [v for v in _hoy_vta if not v["anulada"]]
    with st.expander(f"📋 Ventas de hoy ({len(_validas)}) — ${miles(sum(v['total'] or 0 for v in _validas), 0)}"):
        if not _hoy_vta:
            st.caption("Todavía ninguna.")
        else:
            st.dataframe([{"#": v["id"], "Hora": v["hora"], "Total": f"${miles(v['total'] or 0, 0)}",
                           "Pago": v["forma_de_pago"], "Cliente": v["cliente"] or "",
                           "Patente": v["patente"] or "", "Km": v["km"] or "",
                           "Qué": ", ".join(f"{i['cantidad']}× {i['marca']} {i['codigo']}"
                                            for i in v["items"]),
                           "Estado": "🚫 anulada" if v["anulada"] else "",
                           "Atendió": v["usuario"] or ""} for v in _hoy_vta],
                         width="stretch", hide_index=True)
            if _validas:
                _a1, _a2 = cols([3, 1])
                _anular = _a1.selectbox("Anular una venta (devuelve el stock):",
                                        [v["id"] for v in _validas],
                                        format_func=lambda i: f"#{i}", key="venta_a_anular")
                if candado("anular una venta", _a2.button("🚫 Anular", key="venta_anular"),
                           "anular_una_venta"):
                    _ok_an, _texto_an = anular_venta(_anular)
                    avisar("success" if _ok_an else "warning", _texto_an)
                    st.rerun()

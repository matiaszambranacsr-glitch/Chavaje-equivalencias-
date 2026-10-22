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
        # LO QUE SE TERMINÓ con esta venta: anotarlo para reponer ahí mismo, no cuando venga
        # otro cliente a pedirlo. Ver solicitar_reposicion().
        _terminados = recien.get("terminados") or []
        if _terminados and not recien.get("repuestos"):
            _t1, _t2 = cols([3, 1])
            _t1.info(f"📦 Se terminó el stock de: **{', '.join(n for _, n in _terminados)}**.")
            if _t2.button("📋 Anotar para reponer", key="venta_reponer", width="stretch"):
                for _pid_t, _ in _terminados:
                    solicitar_reposicion(_pid_t)
                recien["repuestos"] = True
                avisar("success", f"📋 Anotado para reponer: {len(_terminados)} producto(s).")
                st.rerun()
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
            # Por código, los resultados son lo buscado y sus equivalencias: cada uno con el
            # veredicto del buscador (🟢🟡🟠🔴), que viaja con lo vendido. Por descripción
            # no hay nada pedido en lugar de qué: cada uno es lo que es.
            _filas_vta = [dict(f) for f in _res_vta[:15]]
            for _f in _filas_vta:
                _f["_veredicto"] = veredicto_de_la_equivalencia(_f)
                _f["_evidencia"] = evidencia_de_la_fila(_f)
            if not _res_vta:
                _filas_vta = [dict(f) for f in buscar_por_texto(_texto_vta)[:15]]
            st.session_state["venta_resultados"] = (_filas_vta, _texto_vta.strip())
            st.session_state.pop("venta_a_confirmar", None)
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
                _ver_f = _f.get("_veredicto")
                if _ver_f and _ver_f != "el que buscaste":
                    _r1.caption(_ver_f)
                # LO 🔴, COMO EN «SE LLEVÓ»: la pieza de seguridad no se vende en lugar de lo
                # pedido, y lo demás pide confirmarlo. Ver bloqueo_de_venta().
                _bloq_f = bloqueo_de_venta(_ver_f, _f.get("Descripcion"))
                _args_f = (_f, _pedido_vta, _ver_f, _f.get("_evidencia"))
                if _bloq_f == "bloqueada":
                    _r2.button("🛑", key=f"sumar_venta_{_f['ID']}", disabled=True,
                               help=TEXTO_DE_VENTA_BLOQUEADA)
                elif _r2.button("➕", key=f"sumar_venta_{_f['ID']}",
                                help=("La app dice que no es la misma pieza: pide confirmarlo."
                                      if _bloq_f else "Sumarlo a la venta.")):
                    if _bloq_f == "confirmar":
                        st.session_state["venta_a_confirmar"] = _f["ID"]
                    else:
                        sumar_a_la_venta(*_args_f)
                    st.rerun()
                if st.session_state.get("venta_a_confirmar") == _f["ID"]:
                    st.warning(f"⚠️ {_f['Marca']} {_f['Codigo']}: {_ver_f}. ¿Se la lleva igual?")
                    _cf1, _cf2 = cols([1, 1], apilar_en_celular=False)
                    if _cf1.button("Sí, se la lleva igual", key=f"confirmar_venta_{_f['ID']}"):
                        sumar_a_la_venta(*_args_f, confirmado=True)
                        st.session_state.pop("venta_a_confirmar", None)
                        st.rerun()
                    if _cf2.button("No", key=f"no_confirmar_venta_{_f['ID']}"):
                        st.session_state.pop("venta_a_confirmar", None)
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
                # Por debajo del costo: un precio mal tipeado, o un descuento que hace perder
                # plata. El costo lo ve el administrador; los demás, el aviso.
                if _it.get("costo") and _it["precio"] < float(_it["costo"]):
                    _c1.caption("⚠️ Por debajo del costo" + (
                        f" (${miles(_it['costo'], 0)})" if es_admin() else "") + ".")
                if _c4.button("🗑️", key=f"venta_quitar_{_k}"):
                    venta_items.remove(_it)
                    st.session_state.pop(f"venta_cant_{_k}", None)
                    st.session_state.pop(f"venta_precio_{_k}", None)
                    st.rerun()
            _total_vta = sum(x["cantidad"] * x["precio"] for x in venta_items)
            st.markdown(f"### Total: ${miles(_total_vta, 0)}")
            # LA VENTA INCOMPLETA, como avisa «Se llevó»: antes de que se vaya el cliente.
            for _que, _faltan in lo_que_suele_ir_con_la_venta(venta_items):
                st.info(f"💡 {_que} suele cambiarse junto con **{', '.join(_faltan)}**. "
                        "Preguntale al cliente si ya lo tiene.")
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
                        "cliente": _cliente_vta, "items": [dict(f) for f in c.fetchall()],
                        "terminados": lo_que_se_termino(_id_vta)}
                    for _it in venta_items:
                        st.session_state.pop(f"venta_cant_{_it['producto_id']}", None)
                        st.session_state.pop(f"venta_precio_{_it['producto_id']}", None)
                    st.session_state["venta_items"] = []
                    st.session_state.pop("venta_resultados", None)
                    st.rerun()

    # LAS VENTAS DEL DÍA Y EL CIERRE DE CAJA: hoy, o el día que se elija.
    _caja_hoy = cierre_de_caja()
    with st.expander(f"📋 Ventas y cierre de caja — hoy: {_caja_hoy['ventas']} · "
                     f"${miles(_caja_hoy['total'], 0)}"):
        _dia_vta = st.date_input("Día:", value=datetime.now().date(), key="venta_dia",
                                 max_value=datetime.now().date(), format="DD/MM/YYYY")
        _dia_txt = _dia_vta.strftime("%Y-%m-%d")
        _del_dia = ventas_del_dia(_dia_txt)
        _validas = [v for v in _del_dia if not v["anulada"]]
        _caja = cierre_de_caja(_dia_txt)
        if not _del_dia:
            st.caption("Ese día no hubo ventas.")
        else:
            st.markdown(f"**Total: ${miles(_caja['total'], 0)}** en {_caja['ventas']} venta(s)"
                        + (f" · {_caja['anuladas']} anulada(s) por ${miles(_caja['total_anulado'], 0)},"
                           " que no cuentan" if _caja["anuladas"] else ""))
            _k1, _k2 = cols([1, 1])
            _k1.caption("Por forma de pago — «Efectivo» es lo que tiene que haber en el cajón:")
            _k1.dataframe([{"Forma de pago": f, "Ventas": n, "Total": f"${miles(t, 0)}"}
                           for f, n, t in _caja["por_forma"]], width="stretch", hide_index=True)
            _k2.caption("Por quién atendió:")
            _k2.dataframe([{"Atendió": u, "Ventas": n, "Total": f"${miles(t, 0)}"}
                           for u, n, t in _caja["por_usuario"]], width="stretch", hide_index=True)
            _filas_dia = [{"#": v["id"], "Hora": v["hora"], "Total": v["total"] or 0,
                           "Pago": v["forma_de_pago"], "Cliente": v["cliente"] or "",
                           "Patente": v["patente"] or "", "Km": v["km"] or "",
                           "Qué": ", ".join(f"{i['cantidad']}× {i['marca']} {i['codigo']}"
                                            for i in v["items"]),
                           "Estado": "🚫 anulada" if v["anulada"] else "",
                           "Atendió": v["usuario"] or ""} for v in _del_dia]
            st.dataframe([dict(f, Total=f"${miles(f['Total'], 0)}") for f in _filas_dia],
                         width="stretch", hide_index=True)
            st.download_button("⬇️ Descargar las ventas del día (Excel)",
                               data=to_excel_bytes(_filas_dia),
                               file_name=f"ventas_{_dia_txt}.xlsx", key="venta_excel",
                               mime="application/vnd.openxmlformats-officedocument."
                                    "spreadsheetml.sheet")
            if _validas:
                _a1, _a2 = cols([3, 1])
                _anular = _a1.selectbox("Anular una venta (devuelve el stock y la saca de la "
                                        "ficha del auto):", [v["id"] for v in _validas],
                                        format_func=lambda i: f"#{i}", key="venta_a_anular")
                if candado("anular una venta", _a2.button("🚫 Anular", key="venta_anular"),
                           "anular_una_venta"):
                    _ok_an, _texto_an = anular_venta(_anular)
                    avisar("success" if _ok_an else "warning", _texto_an)
                    st.rerun()

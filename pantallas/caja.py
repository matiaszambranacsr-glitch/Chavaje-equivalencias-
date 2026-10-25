"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/."""

# ============================================================
# CAJA: lo que mandan los vendedores, para cobrarlo o ponerlo a cuenta, y el cierre
# ============================================================
# Cómo funciona, en logica/ventas.py («LA CAJA APARTE»).
if pagina == PAGINAS[11]:
    ayuda(
        "Lo que arman los vendedores en 🧾 Ventas llega acá, con un **cartel**: quién vendió, a "
        "qué cuenta, el total y la hora. Elegí cuál se cobra y tocá **💳 Cobrar (F10)**: cómo "
        "pagó —efectivo, débito, crédito con las cuotas, o transferencia— y, si hace falta, un "
        "**descuento** por porcentaje. **📒 A cuenta (F11)** se la pone a la cuenta del cliente, "
        "preguntando antes si estás seguro, con el descuento de la cuenta y su límite de "
        "crédito. Recién cobrada cuenta en el cierre de caja. Si el navegador usa F11 para la "
        "pantalla completa, tocá el botón."
    )
    # La caja aparte se puede apagar: entonces cobra cada vendedor al terminar la venta. Y el
    # sonido de lo que llega (ver «EL CLICK DERECHO, LAS TECLAS Y EL PITIDO» en logica/interfaz.py).
    with st.container(horizontal=True, gap="medium"):
        if es_admin():
            _caja_on = st.toggle("💵 La caja cobra aparte", value=caja_aparte(),
                                 key="caja_aparte_toggle",
                                 help="Apagada, cada vendedor cobra al terminar la venta en 🧾 "
                                      "Ventas.")
            if _caja_on != caja_aparte():
                cambiar_caja_aparte(_caja_on)
                st.rerun()
        st.toggle("🔊 Sonido", value=True, key="con_sonido_caja",
                  help="Un pitido cuando llega una venta a la caja.")
    if not caja_aparte():
        st.info("La caja no cobra aparte: cada vendedor cobra al terminar la venta en 🧾 Ventas. "
                "Lo que haya quedado esperando se cobra igual acá.")

    _ICONO_DE_LA_FORMA = {"Efectivo": "💵 Efectivo", "Tarjeta de débito": "💳 Débito",
                          "Tarjeta de crédito": "💳 Crédito", "Transferencia": "🏦 Transferencia"}

    @st.dialog("💳 Cobrar la venta")
    def _dialogo_cobrar(venta_id):
        """F10: cómo pagó, las cuotas si es con crédito y el descuento. Las claves llevan el
        número de la venta: el descuento de la anterior no pasa a la siguiente."""
        _v = next((v for v in ventas_a_cobrar() if v["id"] == venta_id), None)
        if not _v:
            st.warning("Esa venta ya no está esperando (¿la cobró otro?).")
            return
        st.markdown(f"**{el_cartel_de(_v)}**")
        _forma = st.radio("¿Cómo pagó?", FORMAS_DE_COBRO, horizontal=True,
                          format_func=_ICONO_DE_LA_FORMA.get, key=f"cobro_forma_{venta_id}")
        _cuotas = 1
        if _forma == "Tarjeta de crédito":
            _cuotas = st.selectbox("Cuotas:", CUOTAS_POSIBLES, key=f"cobro_cuotas_{venta_id}",
                                   format_func=lambda n: "1 pago" if n == 1 else f"{n} cuotas")
        _desc = st.number_input("Descuento (%):", min_value=0.0,
                                max_value=DESCUENTO_MAXIMO_EN_LA_CAJA, value=0.0, step=1.0,
                                key=f"cobro_descuento_{venta_id}")
        _total = total_con_descuento(venta_id, _desc)
        # «\$»: dos «$» en un mismo texto se leen como una fórmula y se pierden los dos.
        st.markdown(f"### Total: \\${miles(_total, 0)}")
        if _desc:
            st.caption(f"Era ${miles(_v['total'], 0)}: {como_porcentaje(_desc)}% menos.")
        if _forma == "Tarjeta de crédito" and _cuotas > 1:
            st.caption(f"{_cuotas} cuotas de ${miles(_total / _cuotas, 0)}")
        if _forma == "Efectivo":
            _paga = st.number_input("Paga con (para el vuelto):", min_value=0.0, value=None,
                                    step=100.0, key=f"cobro_paga_{venta_id}",
                                    placeholder=f"Ej: {miles(_total, 0)}")
            if _paga:
                st.markdown(f"**Vuelto: ${miles(_paga - _total, 0)}**" if _paga >= _total
                            else f"⚠️ Faltan ${miles(_total - _paga, 0)}.")
        if st.button(f"✅ Cobrar ${miles(_total, 0)}", type="primary", key=f"cobro_ok_{venta_id}",
                     width="stretch"):
            _ok_c, _texto_c = cobrar_venta(venta_id, _forma, _cuotas, _desc)
            if _ok_c:
                avisar("success", _texto_c)
                st.session_state["caja_recien"] = venta_id
                st.rerun()
            st.error(_texto_c)

    @st.dialog("📒 ¿Ponérselo a cuenta?")
    def _dialogo_a_cuenta(venta_id):
        """F11: «¿estás seguro que querés ponérselo a cuenta a ese cliente?», con lo que debe,
        su límite y el descuento de la cuenta."""
        _v = next((v for v in ventas_a_cobrar() if v["id"] == venta_id), None)
        if not _v:
            st.warning("Esa venta ya no está esperando (¿la cobró otro?).")
            return
        st.markdown(f"**{el_cartel_de(_v)}**")
        _mid = _v["mecanico_id"]
        if not _mid:
            _cuentas = dict(cuentas_para_pedir())
            if not _cuentas:
                st.warning(f"No hay cuentas: se crean en {miga_hasta('Usuarios')}.")
                return
            _mid = st.selectbox("Es de Mostrador: ¿a qué cuenta va?", list(_cuentas),
                                format_func=_cuentas.get, index=None,
                                placeholder="El taller o mayorista", key=f"cta_cual_{venta_id}")
            if not _mid:
                return
        c.execute("SELECT nombre FROM mecanicos WHERE id = ?", (_mid,))
        _nombre = c.fetchone()["nombre"]
        _config = configuracion_de_cuenta(_mid)
        _estado = estado_de_cuenta(_mid)
        _desc = st.number_input("Descuento (%):", min_value=0.0,
                                max_value=max(DESCUENTO_MAXIMO_EN_LA_CAJA, _config["descuento"]),
                                value=float(_config["descuento"]), step=1.0,
                                key=f"cta_descuento_{venta_id}_{_mid}",
                                help="El de la cuenta, si tiene; se puede cambiar.")
        _total = total_con_descuento(venta_id, _desc)
        st.warning(f"**¿Estás seguro que querés ponérselo a cuenta a {_nombre}?** "
                   f"${miles(_total, 0)}")
        st.caption(f"Debe hoy \\${miles(_estado['saldo'], 0)}"
                   + (f" · límite \\${miles(_estado['limite'], 0)}" if _estado["limite"] else
                      " · sin límite")
                   + f" · vence en {_config['dias_de_plazo']} días")
        _s1, _s2 = cols([1, 1], apilar_en_celular=False)
        if _s1.button("✅ Sí, a cuenta", type="primary", key=f"cta_ok_{venta_id}",
                      width="stretch"):
            _ok_a, _texto_a = poner_a_cuenta(venta_id, _mid, _desc)
            if _ok_a:
                avisar("success", _texto_a)
                st.session_state["caja_recien"] = venta_id
                st.rerun()
            st.error(_texto_a)
        if _s2.button("No", key=f"cta_no_{venta_id}", width="stretch"):
            st.rerun()

    # LO QUE ESPERA, con su cartel: se mira solo cada 5 segundos. Lo que llegó recién avisa
    # con un cartel que aparece arriba, aunque estés mirando otra cosa de esta pantalla.
    @st.fragment(run_every=5)
    def _lo_que_espera():
        # EL DÍA, DE UN VISTAZO: lo que tiene que haber en el cajón, lo que entró por otros
        # medios, lo puesto a cuenta y lo que espera. Ver resumen_de_la_caja().
        _r = resumen_de_la_caja()
        _m = cols([1, 1, 1, 1])
        _m[0].metric("💵 En el cajón", f"${miles(_r['efectivo'], 0)}",
                     help="Lo cobrado hoy en efectivo, menos lo devuelto: lo que tiene que haber "
                          "(sin el cambio con el que se abrió).")
        _m[1].metric("💳 Tarjeta y transferencia", f"${miles(_r['otros_medios'], 0)}")
        _m[2].metric("📒 A cuenta hoy", f"${miles(_r['a_cuenta'], 0)}")
        _m[3].metric("⏳ Esperando", f"{_r['esperando']} · ${miles(_r['total_esperando'], 0)}")
        _pendientes = ventas_a_cobrar()
        _vistas = st.session_state.setdefault("caja_vistas", [])
        for _v in _pendientes:
            if _v["id"] not in _vistas:
                st.toast(el_cartel_de(_v), icon="🔔", duration="long")
                _vistas.append(_v["id"])
        if not _pendientes:
            st.success("✅ No hay nada esperando en la caja.")
            return
        st.markdown(f"### ⏳ Esperando en la caja: {len(_pendientes)} · "
                    f"${miles(sum(v['total'] or 0 for v in _pendientes), 0)}")
        _ids = [v["id"] for v in _pendientes]
        if st.session_state.get("caja_elegida") not in _ids:
            st.session_state["caja_elegida"] = _ids[0]
        _por_id = {v["id"]: v for v in _pendientes}
        st.radio("Cuál se cobra:", _ids, key="caja_elegida", label_visibility="collapsed",
                 format_func=lambda i: el_cartel_de(_por_id[i]))
        _elegida = _por_id[st.session_state["caja_elegida"]]
        with st.container(border=True):
            st.markdown(f"**{el_cartel_de(_elegida)}**")
            st.dataframe([{"Qué": f"{it['cantidad']}× {it['marca']} {it['codigo']}",
                           "Descripción": (it["descripcion"] or "")[:50],
                           "Importe": f"${miles(it['cantidad'] * (it['precio'] or 0), 0)}"}
                          for it in _elegida["items"]], hide_index=True, width="stretch",
                         height=min(36 * (len(_elegida["items"]) + 1) + 3, 260))
            _b1, _b2 = cols([1, 1], apilar_en_celular=False)
            # La tecla va en el botón (shortcut=): Streamlit la dibuja al lado del nombre.
            # En el celular, sin tecla: no hay teclado.
            if _b1.button("💳 Cobrar", type="primary", key="caja_f10",
                          shortcut=None if es_celular() else "F10", width="stretch"):
                _dialogo_cobrar(_elegida["id"])
            if _b2.button("📒 A cuenta", key="caja_f11",
                          shortcut=None if es_celular() else "F11", width="stretch"):
                _dialogo_a_cuenta(_elegida["id"])

    _lo_que_espera()

    # EL COMPROBANTE DE LA QUE SE ACABA DE COBRAR: el cajero es el que se lo da al cliente.
    _recien = st.session_state.get("caja_recien")
    if _recien:
        with st.container(border=True, key="caja_comprobante"):
            st.markdown(f"**🧾 Comprobante de la venta #{_recien}**")
            _cc1, _cc2, _cc3 = cols([2, 2, 1])
            _cc1.download_button("📄 PDF para imprimir", data=comprobante_para_descargar(_recien),
                                 file_name=f"comprobante_{_recien}.pdf", mime="application/pdf",
                                 key="caja_comprobante_pdf", width="stretch")
            _cc2.link_button("📲 Mandarlo por WhatsApp",
                             "https://wa.me/?text=" + quote(texto_del_comprobante(_recien)),
                             width="stretch")
            if _cc3.button("Listo", key="caja_comprobante_listo", width="stretch"):
                st.session_state.pop("caja_recien", None)
                st.rerun()

    # LAS VENTAS DEL DÍA Y EL CIERRE DE CAJA: hoy, o el día que se elija. Lo cobrado cuenta
    # el día que se cobró; lo que espera, aparte.
    _caja_hoy = cierre_de_caja()
    # Perezoso: lo de adentro corre solo abierto (ver el de «📐 Buscar por medidas» en el Buscador).
    _exp_cierre = st.expander(f"📋 Ventas y cierre de caja — hoy: {_caja_hoy['ventas']} · "
                              f"${miles(_caja_hoy['total'], 0)}", key="exp_ventas_cierre_caja_hoy",
                              on_change="rerun")
    if _exp_cierre.open:
        with _exp_cierre:
            _dia_vta = st.date_input("Día:", value=datetime.now().date(), key="venta_dia",
                                     max_value=datetime.now().date(), format="DD/MM/YYYY")
            _dia_txt = _dia_vta.strftime("%Y-%m-%d")
            _del_dia = ventas_del_dia(_dia_txt)
            _validas = [v for v in _del_dia if not v["anulada"]]
            _caja = cierre_de_caja(_dia_txt)
            _devs_dia = devoluciones_del_dia(_dia_txt)
            if not _del_dia and not _devs_dia:
                st.caption("Ese día no hubo ventas.")
            else:
                st.markdown(f"**Total: \\${miles(_caja['total'], 0)}** en {_caja['ventas']} venta(s)"
                            + (f" · {_caja['anuladas']} anulada(s) por \\${miles(_caja['total_anulado'], 0)},"
                               " que no cuentan" if _caja["anuladas"] else "")
                            + (f" · {_caja['devoluciones']} devolución(es) por "
                               f"\\${miles(_caja['total_devuelto'], 0)}, ya descontadas"
                               if _caja["devoluciones"] else "")
                            + (f" · ⏳ {_caja['a_cobrar']} esperando en la caja por "
                               f"\\${miles(_caja['total_a_cobrar'], 0)}, que todavía no cuentan"
                               if _caja["a_cobrar"] else ""))
                # La ganancia la ve el administrador, como el margen del buscador.
                if es_admin() and _caja["items_con_costo"]:
                    st.markdown(f"💰 **Ganancia estimada: ${miles(_caja['ganancia'], 0)}**"
                                + (f" — de {_caja['items_con_costo']} de {_caja['items']} cosas "
                                   "vendidas, las que tienen costo cargado"
                                   if _caja["items_con_costo"] < _caja["items"] else ""))
                _k1, _k2 = cols([1, 1])
                _k1.caption("Por forma de pago — «Efectivo» es lo que tiene que haber en el cajón:")
                _k1.dataframe([{"Forma de pago": f, "Ventas": n, "Total": f"${miles(t, 0)}"}
                               for f, n, t in _caja["por_forma"]], width="stretch", hide_index=True)
                _k2.caption("Por quién atendió:")
                _k2.dataframe([{"Atendió": u, "Ventas": n, "Total": f"${miles(t, 0)}"}
                               for u, n, t in _caja["por_usuario"]], width="stretch", hide_index=True)
                _filas_dia = [{"#": v["id"], "Hora": v["hora"], "Total": v["total"] or 0,
                               "Pago": como_se_pago(v) if v["cobrada"] else "⏳ en la caja",
                               "Para": v["cuenta"] or v["cliente"] or "",
                               "Patente": v["patente"] or "", "Km": v["km"] or "",
                               "Qué": ", ".join(f"{i['cantidad']}× {i['marca']} {i['codigo']}"
                                                for i in v["items"]),
                               "Estado": "🚫 anulada" if v["anulada"] else "",
                               "Atendió": v["usuario"] or "",
                               "Cobró": v["cobrada_por"] or ""} for v in _del_dia]
                if _filas_dia:
                    st.dataframe([dict(f, Total=f"${miles(f['Total'], 0)}") for f in _filas_dia],
                                 width="stretch", hide_index=True)
                if _devs_dia:
                    st.caption("↩️ Lo devuelto ese día:")
                    st.dataframe([{"Hora": d["hora"], "De la venta": f"#{d['venta_id']}",
                                   "Qué": f"{d['cantidad']}× {d['marca']} {d['codigo']}",
                                   "Importe": f"-${miles(d['importe'], 0)}",
                                   "Pago": d["forma_de_pago"],
                                   "Por qué": MOTIVOS_DE_DEVOLUCION.get(d["motivo"], d["motivo"]),
                                   "Devolvió": d["usuario"] or ""} for d in _devs_dia],
                                 width="stretch", hide_index=True)
                st.download_button("⬇️ Descargar las ventas del día (Excel)",
                                   data=to_excel_bytes(_filas_dia),
                                   file_name=f"ventas_{_dia_txt}.xlsx", key="venta_excel",
                                   mime="application/vnd.openxmlformats-officedocument."
                                        "spreadsheetml.sheet")
                if _del_dia:
                    _cv1, _cv2 = cols([3, 1])
                    _comp_de = _cv1.selectbox("Comprobante de la venta:", [v["id"] for v in _del_dia],
                                              format_func=lambda i: f"#{i}",
                                              key="venta_comprobante_de")
                    _cv2.download_button("📄 PDF", data=comprobante_para_descargar(_comp_de),
                                         file_name=f"comprobante_{_comp_de}.pdf",
                                         mime="application/pdf", key="venta_comprobante_dia",
                                         width="stretch")
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
            # EL ARQUEO: lo que hay en el cajón contra lo que dice el sistema. Ver arquear_la_caja().
            st.markdown("**🧮 Arqueo: ¿cuánto efectivo hay en el cajón?**")
            st.caption(f"Según las ventas en efectivo (menos lo devuelto), tendría que haber "
                       f"**${miles(efectivo_esperado(_dia_txt), 0)}**, sin contar el cambio con el "
                       "que se abrió.")
            with st.form("form_arqueo"):
                _q1, _q2 = cols([1, 2])
                _contado = _q1.number_input("Efectivo contado:", min_value=0.0, step=100.0,
                                            value=None, placeholder="Ej: 45000",
                                            help="Sin el cambio con el que abriste la caja.")
                _nota_arq = _q2.text_input("Nota (opcional):", placeholder="Ej: faltan $500 de un vuelto")
                _arquear = st.form_submit_button("🧮 Guardar el arqueo")
            if _arquear:
                if _contado is None:
                    st.warning("Escribí cuánto efectivo contaste.")
                else:
                    _ok_arq, _texto_arq = arquear_la_caja(_dia_txt, _contado, _nota_arq)
                    avisar("success" if _ok_arq else "warning", f"🧮 {_texto_arq}")
                    st.rerun()
            _arqueos = arqueos_del_dia(_dia_txt)
            if _arqueos:
                st.dataframe([{"Hora": a["hora"], "Esperado": f"${miles(a['efectivo_esperado'], 0)}",
                               "Contado": f"${miles(a['efectivo_contado'], 0)}",
                               "Diferencia": (f"{'+' if a['diferencia'] > 0 else '-' if a['diferencia'] < 0 else ''}"
                                              f"${miles(abs(a['diferencia']), 0)}"),
                               "Nota": a["nota"] or "", "Contó": a["usuario"] or ""}
                              for a in _arqueos], width="stretch", hide_index=True)


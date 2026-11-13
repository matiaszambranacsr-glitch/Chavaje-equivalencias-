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
        # LA FACTURA, SI LA CAJERA QUIERE (ver «LA FACTURA ELECTRÓNICA (ARCA)» en
        # logica/facturas.py): apagada de entrada, nada se factura solo.
        _con_factura = False
        if configuracion_de_arca():
            _con_factura = st.toggle("🧾 Con factura electrónica", key=f"cobro_con_factura_{venta_id}",
                                     help="La hace en ARCA al cobrar. Si no, se puede hacer "
                                          "después, desde el comprobante o el cierre de caja.")
            if _con_factura:
                _cond_f, _doc_f, _nom_f = elegir_cliente_de_la_factura(f"cobro_{venta_id}", venta_id)
        if st.button(f"✅ Cobrar ${miles(_total, 0)}", type="primary", key=f"cobro_ok_{venta_id}",
                     width="stretch"):
            _ok_c, _texto_c = cobrar_venta(venta_id, _forma, _cuotas, _desc)
            if _ok_c:
                avisar("success", _texto_c)
                if _con_factura:
                    _ok_f, _texto_f = facturar_venta(venta_id, _cond_f, _doc_f, _nom_f)
                    avisar("success" if _ok_f else "warning", _texto_f)
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
            _mid = elegir_cuenta(f"cta_{venta_id}", "Es de Mostrador: ¿a qué cuenta va?",
                                 cuentas=list(_cuentas.items()))
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
        _m = fila_de_numeros(4)
        _m[0].metric("💵 En el cajón", f"${miles(_r['efectivo'], 0)}",
                     help="Lo cobrado hoy en efectivo, menos lo devuelto: lo que tiene que haber "
                          "(sin el cambio con el que se abrió).")
        # Corto: de a dos en el celular, «Tarjeta y transferencia» se cortaba en «transferen…».
        _m[1].metric("💳 Tarjeta y transf.", f"${miles(_r['otros_medios'], 0)}",
                     help="Lo cobrado hoy con tarjeta, transferencia o cualquier medio que no "
                          "sea efectivo.")
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
            mostrar_la_factura_de(_recien, "caja_recien")

    # LAS VENTAS DEL DÍA Y EL CIERRE DE CAJA: hoy, o el día que se elija. Lo cobrado cuenta
    # el día que se cobró; lo que espera, aparte.
    _caja_hoy = cierre_de_caja()
    # Perezoso: lo de adentro corre solo abierto (ver el de «📐 Buscar por medidas» en el Buscador).
    _exp_cierre = st.expander(f"📋 Ventas y cierre de caja — hoy: {_caja_hoy['ventas']} · "
                              f"${miles(_caja_hoy['total'], 0)}", key="exp_ventas_cierre_caja_hoy",
                              on_change="rerun")
    if _exp_cierre.open:
        with _exp_cierre:
            _dia_vta = st.date_input("Día:", value=hoy_aca(), key="venta_dia",
                                     max_value=hoy_aca(), format="DD/MM/YYYY")
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
                _corregidas = {int(x["venta"]) for x in cobros_corregidos(_dia_txt)
                               if str(x["venta"]).isdigit()}
                # Cuáles ya tienen factura, a la vista (la columna, solo si hay alguna).
                _facturadas = facturas_de_las_ventas(v["id"] for v in _del_dia)
                _filas_dia = [{"#": v["id"], "Hora": v["hora"], "Total": v["total"] or 0,
                               "Pago": como_se_pago(v) if v["cobrada"] else "⏳ en la caja",
                               **({"Factura": _facturadas.get(v["id"], "")} if _facturadas
                                  else {}),
                               "Para": v["cuenta"] or v["cliente"] or "",
                               "Patente": v["patente"] or "", "Km": v["km"] or "",
                               "Qué": ", ".join(f"{i['cantidad']}× {i['marca']} {i['codigo']}"
                                                for i in v["items"]),
                               "Estado": ("🚫 anulada" if v["anulada"]
                                          else "✏️ corregido" if v["id"] in _corregidas
                                          else ""),
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
                                   data=lambda: to_excel_bytes(_filas_dia),
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
                # CORREGIR UN COBRO (ver esa sección en logica/ventas.py): la cajera marcó otra
                # forma de pago, cobró la venta equivocada o se equivocó en el descuento.
                _cobradas = {v["id"]: v for v in _validas if v["cobrada"]}
                if _cobradas:
                    st.markdown("**✏️ Corregir un cobro**")
                    _co1, _co2 = cols([3, 2])
                    _corregir = _co1.selectbox(
                        "Venta:", list(_cobradas), key="cobro_a_corregir",
                        # Sin la forma de pago en el nombre: el navegador no le cambia el texto
                        # a la opción elegida, y después de corregirla seguía diciendo la vieja
                        # (se vio en una captura). Va abajo, al día.
                        format_func=lambda i: (f"#{i} · {_cobradas[i]['hora']} · "
                                               f"${miles(_cobradas[i]['total'] or 0, 0)}"
                                               + (f" · {_cobradas[i]['cuenta'] or _cobradas[i]['cliente']}"
                                                  if _cobradas[i]["cuenta"] or _cobradas[i]["cliente"]
                                                  else "")))
                    _que_corregir = _co2.radio("Qué hay que corregir:",
                                               ["💳 Cómo pagó", "↩️ Volverla a la caja"],
                                               key="cobro_que_corregir", horizontal=True)
                    _la_c = _cobradas[_corregir]
                    st.caption(f"Ahora dice: **{como_se_pago(_la_c) or 'sin decir'}**"
                               + (f" · la cobró {_la_c['cobrada_por']}" if _la_c["cobrada_por"]
                                  else ""))
                    _puede_c, _por_que_c = puede_corregir_el_cobro(_corregir)
                    if not _puede_c:
                        st.caption(f"🔒 {_por_que_c}")
                    elif _que_corregir == "💳 Cómo pagó":
                        _f1, _f2, _f3 = cols([2, 1, 1])
                        # Arranca en la que tiene: se ve qué se cambia. Una clave por venta, para
                        # que al elegir otra arranque en la suya.
                        _forma_c = _f1.selectbox(
                            "Pagó con:", FORMAS_DE_PAGO, key=f"cobro_forma_nueva_{_corregir}",
                            index=(FORMAS_DE_PAGO.index(_la_c["forma_de_pago"])
                                   if _la_c["forma_de_pago"] in FORMAS_DE_PAGO else 0))
                        _cuotas_c = _f2.selectbox("Cuotas:", CUOTAS_POSIBLES,
                                                  key=f"cobro_cuotas_nuevas_{_corregir}",
                                                  disabled=_forma_c != "Tarjeta de crédito")
                        if candado("corregir cómo se pagó",
                                   _f3.button("💾 Corregir", key="cobro_corregir_forma",
                                              width="stretch"),
                                   "cobro_corregir_forma_candado", nivel="empleado"):
                            _ok_c, _texto_c = cambiar_como_se_pago(_corregir, _forma_c, _cuotas_c)
                            avisar("success" if _ok_c else "warning", _texto_c)
                            st.rerun()
                    else:
                        st.caption("Vuelve a esperar en la caja como antes de cobrarla: sin el "
                                   "descuento y, si estaba a cuenta, sin el cargo de la cuenta. El "
                                   "stock no se toca. Después se cobra como corresponde.")
                        if candado("volver una venta a la caja",
                                   st.button("↩️ Volverla a la caja", key="cobro_volver_a_la_caja"),
                                   "cobro_volver_a_la_caja_candado", nivel="empleado"):
                            _ok_c, _texto_c = volver_a_la_caja(_corregir)
                            avisar("success" if _ok_c else "warning", _texto_c)
                            st.rerun()
                # LAS FACTURAS DEL DÍA (ver «LA FACTURA ELECTRÓNICA (ARCA)» en logica/facturas.py):
                # las hechas, y hacerle la factura a una venta ya cobrada o anularla con la nota
                # de crédito.
                _facturas_dia = facturas_del_dia(_dia_txt)
                if _facturas_dia or (configuracion_de_arca() and _cobradas):
                    st.markdown("**🧾 Facturas electrónicas**")
                if _facturas_dia:
                    # El total y el estado, pegados al comprobante: en el celular la tabla se
                    # corta a lo ancho y quedaban escondidos atrás del cliente y el CAE.
                    st.dataframe([{"Comprobante": nombre_del_comprobante(f["tipo"], f["punto_de_venta"],
                                                                         f["numero"]),
                                   "Total": formato_precio(f["total"]),
                                   "Estado": f["estado"]
                                   + ("" if f["ambiente"] == "produccion" else " (prueba)")
                                   + (" · traída de ARCA" if f["observaciones"] == TRAIDA_DE_ARCA
                                      else ""),
                                   "Venta": f"#{f['venta_id']}" if f["venta_id"] else "",
                                   "Cliente": f["nombre_receptor"] or "", "CAE": f["cae"] or ""}
                                  for f in _facturas_dia], width="stretch", hide_index=True)
                    # Cualquiera de las autorizadas, en PDF: las notas de crédito también (la
                    # de abajo muestra solo la factura vigente de una venta).
                    _autorizadas_dia = {f["id"]: f for f in _facturas_dia
                                        if f["estado"] == "autorizada"}
                    if _autorizadas_dia:
                        _b1, _b2 = cols([3, 1])
                        _fb = _b1.selectbox(
                            "Comprobante para bajar:", list(_autorizadas_dia),
                            key="factura_para_bajar", label_visibility="collapsed",
                            format_func=lambda i: (
                                nombre_del_comprobante(_autorizadas_dia[i]["tipo"],
                                                       _autorizadas_dia[i]["punto_de_venta"],
                                                       _autorizadas_dia[i]["numero"])
                                + f" · {formato_precio(_autorizadas_dia[i]['total'])}"))
                        _b2.download_button(
                            "📄 PDF", data=lambda _i=_fb: factura_para_descargar(_i),
                            file_name=f"comprobante_{_autorizadas_dia[_fb]['punto_de_venta']:05d}-"
                                      f"{_autorizadas_dia[_fb]['tipo']:03d}-"
                                      f"{_autorizadas_dia[_fb]['numero']:08d}.pdf",
                            mime="application/pdf", key="factura_bajar_pdf", width="stretch")
                if _cobradas and (configuracion_de_arca() or _facturas_dia):
                    _fv = st.selectbox("Factura de la venta:", list(_cobradas), key="factura_de_la_venta",
                                       format_func=lambda i: (f"#{i} · {_cobradas[i]['hora']} · "
                                                              f"${miles(_cobradas[i]['total'] or 0, 0)}"
                                                              + (f" · 🧾 {_facturadas[i]}"
                                                                 if i in _facturadas else "")))
                    mostrar_la_factura_de(_fv, f"cierre_{_fv}")
                    _vig = factura_vigente_de(_fv)
                    if _vig and _vig["estado"] == "autorizada" and configuracion_de_arca():
                        if candado("anular una factura",
                                   st.button("🧾 Anularla con nota de crédito",
                                             key="factura_nota_de_credito"),
                                   "factura_nota_de_credito_candado", nivel="empleado"):
                            _ok_n, _texto_n = nota_de_credito(_vig["id"])
                            avisar("success" if _ok_n else "warning", _texto_n)
                            st.rerun()
                # Lo corregido, a la vista de quien cierra la caja: quién, cuándo y qué.
                _corregidos = cobros_corregidos(_dia_txt)
                if _corregidos:
                    st.caption(f"✏️ Cobros corregidos ese día ({len(_corregidos)}), con quién y "
                               "cuándo:")
                    st.dataframe([{"Hora": x["hora"], "Venta": f"#{x['venta']}", "Qué": x["que"],
                                   "Corrigió": x["quien"]} for x in _corregidos],
                                 width="stretch", hide_index=True)
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


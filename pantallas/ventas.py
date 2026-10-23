"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/."""

# ============================================================
# VENTAS: cobrar, descontar el stock y anotarlo en la ficha del auto
# ============================================================
# Cómo funciona, en logica/ventas.py («VENTAS DEL MOSTRADOR»).
if pagina == PAGINAS[9]:
    ayuda(
        "Buscá lo que se lleva el cliente y sumalo; corregí la cantidad o el precio si hace "
        "falta. Con el lector de códigos de barras, escaneá la caja: si el código es de un solo "
        "producto, se suma solo. **✅ Terminar la venta** descuenta el stock (nunca queda negativo: si no "
        "alcanzaba, avisa para contarlo) y anota lo vendido, que es con lo que la app aprende "
        "qué se vende en lugar de qué. Al terminar te pregunta **la patente y los km**: con eso "
        "cada pieza queda en la ficha del auto, y el cliente ve en su link cuánto le falta a "
        "cada cosa. Con la **caja aparte**, la venta va a 💵 Caja con un cartel —quién vendió, "
        "a qué cuenta, el total y la hora— y la cobra el cajero; la cuenta es la de **«🧾 "
        "Atendiendo a»**."
    )
    venta_items = st.session_state.setdefault("venta_items", [])
    recien = st.session_state.get("venta_recien_cerrada")
    # LO QUE TENÉS DEL DEPÓSITO sin vender: está a tu nombre hasta que lo vendas acá o vuelva
    # al depósito, escaneado por el depósito. Ver «LO QUE QUEDA AFUERA» en logica/deposito.py.
    _tengo = lo_que_tiene(persona=obtener_usuario_actual())
    _tengo_por_producto = {}
    for _r in _tengo:
        _tengo_por_producto[_r["producto_id"]] = _tengo_por_producto.get(_r["producto_id"], 0) + _r["queda"]
    if _tengo:
        _tg1, _tg2 = cols([3, 1])
        _tg1.info("📦 **Tenés del depósito sin vender:** "
                  + ", ".join(f"{_r['queda']}× {_r['marca']} {_r['codigo_raw']}" for _r in _tengo[:8])
                  + (f" y {len(_tengo) - 8} más" if len(_tengo) > 8 else "")
                  + ". Si se venden acá, no se descuentan del stock otra vez; si no, llevalos al "
                    "depósito: lo recibe escaneando la etiqueta en ↩️ Devoluciones.")
        if _tg2.button("➕ Sumar a la venta", key="venta_sumar_lo_que_tengo", width="stretch",
                       help="Suma a esta venta todo lo que tenés del depósito, con su cantidad."):
            st.session_state.pop("venta_recien_cerrada", None)
            sumar_lo_que_tengo_a_la_venta()
            st.rerun()

    if recien:
        # LA VENTA RECIÉN TERMINADA: lo que pidió el dueño, la patente y los km. Con la caja
        # aparte, va a la caja: ahí la cobran (ver «LA CAJA APARTE»).
        if recien.get("a_la_caja"):
            st.success(f"📤 Venta #{recien['id']} mandada a la caja: **${miles(recien['total'], 0)}**"
                       + (f" para {recien['cuenta']}" if recien.get("cuenta") else "")
                       + ". La cobra la caja.")
        else:
            st.success(f"✅ Venta #{recien['id']} terminada: **${miles(recien['total'], 0)}**.")
        # EL COMPROBANTE para el cliente: por WhatsApp (a su número, si ya se anotó en la
        # ficha) o en PDF para imprimir. No es una factura y lo dice.
        _tel_comp = re.sub(r"\D", "", (buscar_vehiculo_por_id(recien["anotada"]["vehiculo_id"])
                                        or {}).get("cliente_telefono") or ""
                           ) if recien.get("anotada") else ""
        _cp1, _cp2 = cols([1, 1])
        _cp1.link_button("📲 Mandarle el comprobante por WhatsApp",
                         f"https://wa.me/{_tel_comp}?text=" + quote(texto_del_comprobante(recien["id"])),
                         width="stretch")
        _cp2.download_button("📄 Comprobante (PDF)", data=comprobante_para_descargar(recien["id"]),
                             file_name=f"comprobante_{recien['id']}.pdf", mime="application/pdf",
                             key="venta_comprobante_pdf", width="stretch")
        for _aviso in recien.get("avisos") or []:
            st.warning(f"⚠️ {_aviso}")
        # LO QUE SE TERMINÓ con esta venta ya quedó anotado para reponer, solo: ver
        # anotar_lo_que_se_termino().
        _terminados = recien.get("terminados") or []
        if _terminados:
            st.info(f"📦 Se terminó el stock de: **{', '.join(n for _, n in _terminados)}**. Ya "
                    "quedó anotado para reponer (📊 Estadísticas → 📌 Para pedir).")
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
        # ARMAR LA VENTA. A quién: Mostrador o la cuenta de un taller, la misma que en el
        # buscador (ver mostrar_cuenta_elegida()); va en el cartel de la caja.
        mostrar_cuenta_elegida("venta")
        # «📍 ¿Dónde está?» en el menú de cada producto, si el depósito tiene su mapa.
        _con_mapa = hay_mapa()
        # Se limpia al buscar: el lector de códigos de barras escribe encima de lo que haya.
        with st.form("form_buscar_para_vender", clear_on_submit=True):
            _q1, _q2 = cols([4, 1])
            _texto_vta = _q1.text_input(rotulo_de_accion("Código o descripción:",
                                                         "Código o descripción (F2):"),
                                        key="venta_buscar",
                                        placeholder="Ej: W712/94 o filtro aceite gol")
            _buscar_vta = _q2.form_submit_button("🔍 Buscar")
        # ESCANEAR Y LISTO: el código de barras de un solo producto se suma directo, sin
        # elegirlo de una lista. Ver producto_por_codigo_de_barras().
        _por_barras = producto_por_codigo_de_barras(_texto_vta) if _buscar_vta else None
        if _por_barras:
            _sumado = sumar_a_la_venta({"ID": _por_barras})
            if _sumado:
                avisar("success", f"📷 Sumado: {_sumado['marca']} {_sumado['codigo']} "
                                  f"(van {_sumado['cantidad']}).")
            st.session_state.pop("venta_resultados", None)
            st.rerun()
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
            st.caption(f"{len(_resultados_vta)} resultado(s) para «{_pedido_vta}».")
            # Cada renglón con su menú: en la computadora los botones salen con el click
            # derecho (ver «EL CLICK DERECHO» en logica/interfaz.py); en el celular, se ven.
            pista_del_click_derecho(
                "vta", "Click derecho sobre un producto: sumarlo a la venta, ver dónde está o "
                       "anotarlo para reponer.", "«➕» lo suma a la venta.")
            for _f in _resultados_vta:
                # LO 🔴, COMO EN «SE LLEVÓ»: la pieza de seguridad no se vende en lugar de lo
                # pedido, y lo demás pide confirmarlo. Ver bloqueo_de_venta().
                _ver_f = _f.get("_veredicto")
                _bloq_f = bloqueo_de_venta(_ver_f, _f.get("Descripcion"))
                _args_f = (_f, _pedido_vta, _ver_f, _f.get("_evidencia"))
                with renglon_con_menu(f"vta_{_f['ID']}"):
                    _r1, _r2 = cols([5, 1], apilar_en_celular=False)
                    _stock_f = _f.get("Stock")
                    _r1.write(f"**{_f['Marca']} {_f['Codigo']}** — {(_f.get('Descripcion') or '')[:60]}"
                              f" · ${miles(_f.get('Precio') or 0, 0)}"
                              f" · stock {_stock_f if _stock_f is not None else 's/d'}")
                    if _ver_f and _ver_f != "el que buscaste":
                        _r1.caption(_ver_f)
                    with acciones_del_renglon(_r2, f"vta_{_f['ID']}"):
                        if _bloq_f == "bloqueada":
                            st.button(rotulo_de_accion("🛑", "🛑 No se vende en lugar de lo pedido"),
                                      key=f"sumar_venta_{_f['ID']}", disabled=True,
                                      help=TEXTO_DE_VENTA_BLOQUEADA)
                        elif st.button(rotulo_de_accion("➕", "➕ Sumar a la venta"),
                                       key=f"sumar_venta_{_f['ID']}",
                                       help=("La app dice que no es la misma pieza: pide confirmarlo."
                                             if _bloq_f else "Sumarlo a la venta.")):
                            if _bloq_f == "confirmar":
                                st.session_state["venta_a_confirmar"] = _f["ID"]
                            else:
                                sumar_a_la_venta(*_args_f)
                            st.rerun()
                        # Lo que en el celular no entra en el renglón, solo en el menú.
                        if not es_celular():
                            if _con_mapa:
                                st.button("📍 ¿Dónde está?", key=f"donde_venta_{_f['ID']}",
                                          on_click=ver_donde_esta, args=(_f["ID"],))
                            st.button("📌 Anotar para reponer", key=f"repo_venta_{_f['ID']}",
                                      disabled=solo_mirar(), on_click=pedir_reposicion_y_avisar,
                                      args=(_f["ID"], f"{_f['Marca']} - {_f['Codigo']}", "venta"))
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
            mostrar_lo_anotado("venta")
        elif _buscar_vta:
            st.info("No encontré ese código ni esa descripción.")

        st.markdown("---")
        if not venta_items:
            st.info("La venta está vacía: buscá lo que se lleva el cliente, o pasá un "
                    "presupuesto del 🔍 Buscador con «🧾 Pasar a una venta».")
        else:
            st.markdown(f"**🧾 La venta ({len(venta_items)} ítem(s))**")
            pista_del_click_derecho("carrito_vta", "Click derecho sobre un ítem: uno más, uno "
                                                   "menos, dónde está o quitarlo.")
            for _it in list(venta_items):
                _k = _it["producto_id"]
                with renglon_con_menu(f"carrito_vta_{_k}"):
                    _c1, _c2, _c3, _c4 = cols([4, 1.2, 1.6, 0.7], apilar_en_celular=False)
                    _c1.write(f"**{_it['marca']} {_it['codigo']}** — {(_it['descripcion'] or '')[:50]}")
                    # Lo que cambió por atrás (escanear o «➕» otra vez): ver valor_del_campo().
                    _it["cantidad"] = int(_c2.number_input(
                        "Cant.", min_value=1, max_value=CANTIDAD_MAXIMA_POR_PEDIDO, step=1,
                        value=valor_del_campo(f"venta_cant_{_k}", int(_it["cantidad"])),
                        key=f"venta_cant_{_k}", label_visibility="collapsed"))
                    _it["precio"] = float(_c3.number_input(
                        "Precio", min_value=0.0, value=float(_it["precio"]), step=100.0,
                        key=f"venta_precio_{_k}", label_visibility="collapsed"))
                    if _tengo_por_producto.get(_k):
                        _c1.caption(f"📦 Tenés {_tengo_por_producto[_k]} del depósito: no se "
                                    "descuentan del stock otra vez.")
                    # Por debajo del costo: un precio mal tipeado, o un descuento que hace perder
                    # plata. El costo lo ve el administrador; los demás, el aviso.
                    if _it.get("costo") and _it["precio"] < float(_it["costo"]):
                        _c1.caption("⚠️ Por debajo del costo" + (
                            f" (${miles(_it['costo'], 0)})" if es_admin() else "") + ".")
                    with acciones_del_renglon(_c4, f"carrito_vta_{_k}"):
                        if not es_celular():
                            st.button("➕ Uno más", key=f"venta_mas_{_k}",
                                      disabled=_it["cantidad"] >= CANTIDAD_MAXIMA_POR_PEDIDO,
                                      on_click=cambiar_cantidad_en_la_venta, args=(_k, 1))
                            st.button("➖ Uno menos", key=f"venta_menos_{_k}",
                                      disabled=_it["cantidad"] <= 1,
                                      on_click=cambiar_cantidad_en_la_venta, args=(_k, -1))
                            if _con_mapa:
                                st.button("📍 ¿Dónde está?", key=f"venta_donde_{_k}",
                                          on_click=ver_donde_esta, args=(_k,))
                        st.button(rotulo_de_accion("🗑️", "🗑️ Quitar de la venta"),
                                  key=f"venta_quitar_{_k}", on_click=quitar_de_la_venta,
                                  args=(_k,))
            _total_vta = sum(x["cantidad"] * x["precio"] for x in venta_items)
            st.markdown(f"### Total: ${miles(_total_vta, 0)}")
            # LA VENTA INCOMPLETA, como avisa «Se llevó»: antes de que se vaya el cliente.
            for _que, _faltan in lo_que_suele_ir_con_la_venta(venta_items):
                st.info(f"💡 {_que} suele cambiarse junto con **{', '.join(_faltan)}**. "
                        "Preguntale al cliente si ya lo tiene.")
            _p1, _p2 = cols([1, 1])
            _cliente_vta = _p1.text_input("Cliente (opcional):", key="venta_cliente")
            # CON LA CAJA APARTE el vendedor no cobra: manda la venta a 💵 Caja, con la cuenta
            # de «🧾 Atendiendo a». Sin la caja aparte cobra él, como antes; con una cuenta
            # elegida, también puede ponerla a cuenta. Ver «LA CAJA APARTE».
            _cuenta_vta = cuenta_elegida()
            _con_caja = caja_aparte()
            if _con_caja:
                _forma_vta = ""
                _p2.caption("💵 **La cobra la caja**"
                            + (f", para {_cuenta_vta['nombre']}" if _cuenta_vta else "")
                            + ": ahí eligen cómo paga.")
            else:
                _forma_vta = _p2.selectbox(
                    "Forma de pago:", FORMAS_DE_PAGO + ([A_CUENTA] if _cuenta_vta else []),
                    key="venta_forma",
                    format_func=lambda f: (f"📒 A la cuenta de {_cuenta_vta['nombre']}"
                                           if f == A_CUENTA else f))
            if st.button("📤 Mandar a la caja" if _con_caja else "✅ Terminar la venta",
                         type="primary", key="venta_terminar", width="stretch",
                         shortcut=None if es_celular() else "F9"):
                try:
                    _id_vta, _avisos_vta = cerrar_venta(
                        venta_items, _cliente_vta, _forma_vta,
                        mecanico_id=_cuenta_vta["id"] if _cuenta_vta else None,
                        a_la_caja=_con_caja or _forma_vta == A_CUENTA)
                except (ValueError, PermissionError) as _err:
                    st.error(str(_err))
                else:
                    if _forma_vta == A_CUENTA:
                        _ok_cta, _texto_cta = poner_a_cuenta(_id_vta)
                        if not _ok_cta:
                            _avisos_vta.append(f"No se pudo poner a cuenta: {_texto_cta} "
                                               "Quedó esperando en 💵 Caja.")
                    c.execute("SELECT COALESCE(cobrada, 1) FROM ventas WHERE id = ?", (_id_vta,))
                    _sin_cobrar = not c.fetchone()[0]
                    c.execute("""SELECT id, codigo, marca, descripcion FROM ventas_items
                                 WHERE venta_id = ? ORDER BY id""", (_id_vta,))
                    st.session_state["venta_recien_cerrada"] = {
                        "id": _id_vta, "total": _total_vta, "avisos": _avisos_vta,
                        "cliente": _cliente_vta, "items": [dict(f) for f in c.fetchall()],
                        "terminados": lo_que_se_termino(_id_vta), "a_la_caja": _sin_cobrar,
                        "cuenta": _cuenta_vta["nombre"] if _cuenta_vta else ""}
                    for _it in venta_items:
                        st.session_state.pop(f"venta_cant_{_it['producto_id']}", None)
                        st.session_state.pop(f"venta_precio_{_it['producto_id']}", None)
                    st.session_state["venta_items"] = []
                    st.session_state.pop("venta_resultados", None)
                    st.rerun()

    # LA CAJA: el cierre de caja, el arqueo y lo que espera para cobrarse están en «💵 Caja».
    # Ver «LA CAJA APARTE» en logica/ventas.py.
    st.button("💵 La caja: cobrar y el cierre", key="venta_ir_a_la_caja",
              on_click=ir_a_donde_dice_el_aviso, args=("💵 Caja",))

    # DEVOLVER ALGO DE UNA VENTA: en su propia pantalla, «↩️ Devoluciones». Acá solo el botón.
    st.button("↩️ Devolver algo de una venta →", key="venta_ir_a_devolver",
              on_click=ir_a_donde_dice_el_aviso, args=("↩️ Devoluciones → 🧾 De un cliente",))

    # LO QUE SE VA A TERMINAR, con lo que se vende: para anotarlo antes de que falte. Ver
    # lo_que_se_va_a_terminar().
    _por_terminar = lo_que_se_va_a_terminar()
    with st.expander(f"📦 Lo que se va a terminar ({len(_por_terminar)})", key="exp_lo_va_terminar"):
        if not _por_terminar:
            st.caption("Con lo que se vendió en los últimos 30 días, nada se termina esta semana.")
        else:
            st.caption("Con lo que se vendió en los últimos 30 días (sin lo devuelto) y el stock "
                       "de hoy, esto alcanza para menos de una semana:")
            st.dataframe([{"Producto": f["nombre"], "Descripción": f["descripcion"][:40],
                           "Stock": f["stock"], "Se venden por semana": f["por_semana"],
                           "Alcanza para": ("ya no hay" if not f["alcanza_dias"] and not f["stock"]
                                            else f"{f['alcanza_dias']} día(s)"),
                           "Para reponer": "✅ anotado" if f["anotado"] else ""}
                          for f in _por_terminar], width="stretch", hide_index=True)
            _faltan_anotar = [f for f in _por_terminar if not f["anotado"]]
            if _faltan_anotar and st.button(f"📋 Anotar para reponer ({len(_faltan_anotar)})",
                                            key="venta_reponer_todo"):
                for f in _faltan_anotar:
                    solicitar_reposicion(f["producto_id"])
                avisar("success", f"📋 Anotado para reponer: {len(_faltan_anotar)} producto(s).")
                st.rerun()

    # LO QUE MÁS SE VENDE: el período que se elija, el total, el ticket promedio, las ventas de
    # cada día y lo que más sale, por unidades y por plata. La ganancia, solo el administrador.
    with st.expander("📊 Lo que más se vende", key="exp_lo_mas_vende"):
        _dias_mv = st.selectbox("Período:", [7, 30, 90, 365], index=1, key="venta_periodo",
                                format_func=lambda d: {7: "Última semana", 30: "Últimos 30 días",
                                                       90: "Últimos 3 meses",
                                                       365: "Último año"}[d])
        _mv = lo_mas_vendido(_dias_mv)
        if not _mv["ventas"]:
            st.caption("En ese período no hubo ventas.")
        else:
            _m = cols([1, 1, 1, 1] if es_admin() else [1, 1, 1])
            _m[0].metric("Ventas", miles(_mv["ventas"]))
            _m[1].metric("Total", f"${miles(_mv['total'], 0)}")
            _m[2].metric("Ticket promedio", f"${miles(_mv['ticket_promedio'], 0)}")
            if es_admin():
                _m[3].metric("Ganancia estimada", f"${miles(_mv['ganancia'], 0)}",
                             help="Con el costo que tenía cada cosa al venderla, y solo de lo "
                                  "que tiene costo cargado.")
            st.caption("Lo que entró cada día:")
            st.bar_chart({"Día": [datetime.strptime(d, "%Y-%m-%d") for d, _ in _mv["por_dia"]],
                          "Total": [t for _, t in _mv["por_dia"]]}, x="Día", y="Total",
                         height=220)

            def _tabla_mv(filas):
                return [dict({"Producto": f"{f['marca']} {f['codigo']}",
                              "Descripción": (f["descripcion"] or "")[:40],
                              "Unidades": f["unidades"], "Plata": f"${miles(f['plata'], 0)}"},
                             **({"Ganancia": (f"${miles(f['ganancia'], 0)}"
                                              if f["ganancia"] is not None else "sin costo")}
                                if es_admin() else {})) for f in filas]
            _t1, _t2 = cols([1, 1])
            _t1.caption("Lo que más unidades vende:")
            _t1.dataframe(_tabla_mv(_mv["por_unidades"]), width="stretch", hide_index=True)
            _t2.caption("Lo que más plata trae:")
            _t2.dataframe(_tabla_mv(_mv["por_plata"]), width="stretch", hide_index=True)

    # CADA CUENTA: lo de un empleado (lo que vendió y lo que tiene del depósito) o de un taller
    # (lo que se llevó y lo que debe: lo de un taller no vuelve). El administrador ve a todos;
    # un empleado, lo suyo. Ver resumen_de_la_cuenta().
    with st.expander("👥 Cada cuenta", key="exp_cada_cuenta"):
        _cuentas = cuentas_para_mirar()
        _ca1, _ca2 = cols([2, 1])
        _cual = _ca1.selectbox("Cuenta:", range(len(_cuentas)), key="venta_cuenta_sel",
                               format_func=lambda i: _cuentas[i][0])
        _dias_cta = _ca2.selectbox("Período:", [7, 30, 90, 365], index=1,
                                   key="venta_cuenta_periodo",
                                   format_func=lambda d: {7: "Última semana", 30: "Últimos 30 días",
                                                          90: "Últimos 3 meses",
                                                          365: "Último año"}[d])
        _, _persona_cta, _taller_cta = _cuentas[_cual]
        _cta = resumen_de_la_cuenta(persona=_persona_cta, mecanico_id=_taller_cta, dias=_dias_cta)
        if _taller_cta is None:
            _q = cols([1, 1, 1])
            _q[0].metric("Ventas", miles(len(_cta["ventas"])))
            _q[1].metric("Vendió", f"${miles(_cta['total'], 0)}")
            _q[2].metric("Le devolvieron", f"${miles(_cta['devuelto'], 0)}")
            if _cta["ventas"]:
                st.dataframe([{"#": v["id"], "Cuándo": f"{v['fecha'][8:10]}/{v['fecha'][5:7]} "
                                                       f"{v['fecha'][11:16]}",
                               "Cliente": v["cliente"] or "", "Pago": v["forma_de_pago"],
                               "Total": f"${miles(v['total'] or 0, 0)}"} for v in _cta["ventas"]],
                             width="stretch", hide_index=True)
        else:
            _q = cols([1, 1, 1])
            _q[0].metric("Retiros", miles(len(_cta["entregas"])))
            _q[1].metric("Se llevó", f"${miles(_cta['total'], 0)}")
            _q[2].metric("Debe hoy", f"${miles(_cta['saldo'], 0)}")
            if _cta["entregas"]:
                st.dataframe([{"Cuándo": f"{e['resuelto_en'][8:10]}/{e['resuelto_en'][5:7]} "
                                         f"{e['resuelto_en'][11:16]}",
                               "Qué": f"{e['cantidad']}× {e['marca']} {e['codigo_raw']}",
                               "Importe": f"${miles(e['importe'] or 0, 0)}"}
                              for e in _cta["entregas"]], width="stretch", hide_index=True)
        if _cta["afuera"]:
            st.caption("📦 Lo que tiene del depósito sin vender ni devolver:")
            st.dataframe([{"Qué": f"{r['queda']}× {r['marca']} {r['codigo_raw']}",
                           "Descripción": (r["descripcion"] or "")[:40],
                           "Desde": ("🔴 " if r["horas"] >= HORAS_PARA_AVISAR_LO_QUE_QUEDO_AFUERA
                                     else "") + "hace " + cuanto_hace(r["horas"])}
                          for r in _cta["afuera"]], width="stretch", hide_index=True)
        elif not (_cta.get("ventas") or _cta.get("entregas")):
            st.caption("En ese período no tiene movimientos, y no tiene nada del depósito afuera.")

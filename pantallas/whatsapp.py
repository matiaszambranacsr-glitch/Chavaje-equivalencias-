"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/."""

# ============================================================
# LISTA PARA WHATSAPP
# ============================================================
if pagina == PAGINAS[5]:
    st.subheader("Armar lista de productos para enviar por WhatsApp")
    ayuda(
        "Pegá los códigos que te pidió el cliente, o sumalos de a uno desde el 🔍 Buscador con "
        "«📋 Agregar a lista de WhatsApp». Acá se arma un mensaje agrupado por producto, con las "
        "equivalencias y precios de cada marca, para mandar por WhatsApp o como PDF."
    )

    if es_empleado_o_abierto():
        mostrar_cuenta_elegida("whatsapp")

    lista = st.session_state.lista_whatsapp

    # PEGAR EL PEDIDO. El cliente manda la lista por WhatsApp; buscarla código por código en el
    # buscador y sumar cada uno era el trabajo entero. Acá se pega y se suman todos de una.
    with st.form("form_pedido_whatsapp", clear_on_submit=True):
        _pedido = st.text_area(
            "¿Te mandaron una lista? Pegala acá:",
            placeholder="Un código por renglón, o separados por coma:\nW712/94\n036115561G",
            height=110)
        _sumar = st.form_submit_button("➕ Agregar todos a la lista", type="primary")
    if _sumar and _pedido.strip():
        _no_estan = []
        for _cod in [x.strip() for x in re.split(r"[,;\n]+", _pedido) if x.strip()]:
            _clean = sanitizar(_cod)
            _res = []
            if _clean:
                _res, _ = buscar_con_variantes_del_cero(_clean, "Todas", 3)
            if not _res:
                _no_estan.append(_cod)
                if _clean:
                    registrar_busqueda_sin_resultado(_cod)
                continue
            marcar_lo_que_no_es_lo_mismo(_res)
            lista.append({"codigo_buscado": _cod, "resultados": _res})
        if _no_estan:
            st.warning("No están cargados: " + ", ".join(_no_estan[:15])
                       + ("…" if len(_no_estan) > 15 else "")
                       + ". Quedaron en 📊 Estadísticas → 🔎 Búsquedas sin resultado.")

    if not lista:
        st.info("Todavía no hay nada en la lista: pegá el pedido arriba, o agregá productos "
                "desde el 🔍 Buscador.")
    else:
        # Al cliente va solo lo que se le puede ofrecer: ver filas_para_cotizar().
        lista_cotizar = [dict(item, resultados=filas_para_cotizar(item["resultados"]))
                         for item in lista]
        st.markdown(f"**{len(lista)} producto(s) en la lista:**")
        for i, item in enumerate(lista):
            colT, colX = st.columns([5, 1])
            _van = len(lista_cotizar[i]["resultados"])
            _afuera = len(item["resultados"]) - _van
            colT.write(f"{i + 1}. {item['codigo_buscado']} ({_van} para ofrecer"
                       + (f"; {_afuera} afuera: códigos de fábrica, kits o lo que no es "
                          "seguro" if _afuera else "") + ")")
            if colX.button("🗑️", key=f"quitar_wa_{i}"):
                lista.pop(i)
                st.rerun()

        st.markdown("---")
        incluir_precio = st.checkbox("Incluir precios en el mensaje", value=True)
        incluir_stock = st.checkbox("Incluir stock en el mensaje", value=False)
        # El estado viaja con el código: lo probable no sale igual que lo confirmado.
        marcar_a_confirmar = st.checkbox("Marcar «⚠️ a confirmar» lo que no está confirmado",
                                         value=True, key="wa_a_confirmar")

        # Armado del texto del mensaje, agrupado por producto buscado
        encabezado_wa = obtener_config("whatsapp_encabezado", "🔧 *Equivalencias El Chavo*")
        pie_wa = obtener_config("whatsapp_pie", "")
        # Para quién es, si se está atendiendo a una cuenta. Con precios de lista: el descuento
        # de la cuenta no va en la cotización (ver «EL DESCUENTO NO SE VE»).
        _para_wa = None
        if cuenta_elegida() and st.checkbox(f"Poner «Para: {cuenta_elegida()['nombre']}» en el "
                                            "mensaje", value=True, key="wa_para_la_cuenta"):
            _para_wa = cuenta_elegida()["nombre"]
        mensaje = armar_mensaje_de_cotizacion(lista_cotizar, encabezado_wa, pie_wa,
                                              incluir_precio, incluir_stock, _para_wa,
                                              marcar_a_confirmar)

        _fuera_wa = sorted({f.get("Marca") for item in lista_cotizar for f in item["resultados"]
                            if f.get("Precio")} & marcas_con_precios_fuera_de_escala())
        if _fuera_wa and incluir_precio:
            st.warning(f"⚠️ Los precios de **{', '.join(_fuera_wa)}** están en otra escala que "
                       "los de las demás marcas: revisalos antes de mandar la cotización (ver "
                       f"{miga_hasta('Marcas')} → 📏 Coeficiente de la lista).")
        st.text_area("Vista previa del mensaje:", value=mensaje, height=300)

        alias_disponibles = listar_alias_transferencia()
        alias_elegido = None
        qr_real_para_pdf = None
        if alias_disponibles:
            opciones_alias = ["Sin QR de transferencia"] + [a["Nombre"] for a in alias_disponibles]
            alias_sel = st.selectbox("Alias para el QR del PDF (opcional):", opciones_alias, key="alias_para_pdf")
            if alias_sel != "Sin QR de transferencia":
                alias_elegido = next(a for a in alias_disponibles if a["Nombre"] == alias_sel)
                if alias_elegido["TieneQrReal"]:
                    qr_real_para_pdf = obtener_qr_real(alias_elegido["ID"])
                    st.caption("✅ Se va a usar el QR real que subiste para este alias.")
                else:
                    st.caption("ℹ️ Este alias no tiene QR real cargado — se va a generar uno con el alias/CBU como texto.")
        else:
            st.caption(
                "Todavía no cargaste ningún alias/CBU — podés hacerlo en "
                f"**{miga_hasta('Mensajería y cobros')} → 💳 Alias para QR de transferencia** "
                "si querés que la cotización incluya uno."
            )

        import urllib.parse
        url_whatsapp = "https://wa.me/?text=" + urllib.parse.quote(mensaje)
        col_wa, col_pdf = st.columns(2)
        col_wa.link_button("📲 Abrir en WhatsApp", url_whatsapp, type="primary", width="stretch")
        pdf_bytes = pdf_con_cache("cotizacion", generar_pdf_cotizacion, lista_cotizar, incluir_precio,
                                   incluir_stock, alias_elegido, qr_real_para_pdf,
                                   marcar_a_confirmar)
        col_pdf.download_button(
            "📄 Descargar cotización (PDF)", data=pdf_bytes,
            file_name=f"cotizacion_{datetime.now():%Y%m%d_%H%M}.pdf",
            mime="application/pdf", width="stretch"
        )

        if st.button("🗑️ Vaciar toda la lista"):
            st.session_state.lista_whatsapp = []
            st.rerun()

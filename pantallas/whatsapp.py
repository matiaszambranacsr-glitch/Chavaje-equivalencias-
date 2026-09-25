"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/."""

# ============================================================
# LISTA PARA WHATSAPP
# ============================================================
if pagina == PAGINAS[5]:
    st.subheader("Armar lista de productos para enviar por WhatsApp")
    st.caption(
        "Buscá códigos en la pestaña Buscador y tocá '📋 Agregar a lista de WhatsApp'. "
        "Acá se arma un mensaje agrupado por producto, con las equivalencias y precios de cada marca."
    )

    lista = st.session_state.lista_whatsapp

    if not lista:
        st.info("Todavía no agregaste ningún producto a la lista. Andá a Buscador y agregá alguno.")
    else:
        st.markdown(f"**{len(lista)} producto(s) en la lista:**")
        for i, item in enumerate(lista):
            colT, colX = st.columns([5, 1])
            colT.write(f"{i + 1}. {item['codigo_buscado']} ({len(item['resultados'])} equivalencias)")
            if colX.button("🗑️", key=f"quitar_wa_{i}"):
                lista.pop(i)
                st.rerun()

        st.markdown("---")
        incluir_precio = st.checkbox("Incluir precios en el mensaje", value=True)
        incluir_stock = st.checkbox("Incluir stock en el mensaje", value=False)

        # Armado del texto del mensaje, agrupado por producto buscado
        encabezado_wa = obtener_config("whatsapp_encabezado", "🔧 *Equivalencias El Chavo*")
        pie_wa = obtener_config("whatsapp_pie", "")
        partes = [f"{encabezado_wa}\n"]
        for item in lista:
            partes.append(f"\n📦 *{item['codigo_buscado']}*")
            for fila in item["resultados"]:
                linea = f"  • {fila['Marca']}: {fila['Codigo']}"
                if fila.get("Descripcion"):
                    linea += f" - {fila['Descripcion']}"
                extras = []
                if incluir_precio and fila.get("Precio"):
                    extras.append(f"${fila['Precio']:,.0f}")
                if incluir_stock and fila.get("Stock") is not None:
                    extras.append(f"Stock: {fila['Stock']}")
                if extras:
                    linea += " (" + " · ".join(extras) + ")"
                partes.append(linea)
        if pie_wa.strip():
            partes.append(f"\n{pie_wa}")
        mensaje = "\n".join(partes)

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
                "Todavía no cargaste ningún alias/CBU — podés hacerlo en 'Administrar' → "
                "'💳 Alias para QR de transferencia' si querés que la cotización incluya uno."
            )

        import urllib.parse
        url_whatsapp = "https://wa.me/?text=" + urllib.parse.quote(mensaje)
        col_wa, col_pdf = st.columns(2)
        col_wa.link_button("📲 Abrir en WhatsApp", url_whatsapp, type="primary", width="stretch")
        pdf_bytes = pdf_con_cache("cotizacion", generar_pdf_cotizacion, lista, incluir_precio,
                                   incluir_stock, alias_elegido, qr_real_para_pdf)
        col_pdf.download_button(
            "📄 Descargar cotización (PDF)", data=pdf_bytes,
            file_name=f"cotizacion_{datetime.now():%Y%m%d_%H%M}.pdf",
            mime="application/pdf", width="stretch"
        )

        if st.button("🗑️ Vaciar toda la lista"):
            st.session_state.lista_whatsapp = []
            st.rerun()

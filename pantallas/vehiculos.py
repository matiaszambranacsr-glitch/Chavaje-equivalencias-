"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/."""

# ============================================================
# VEHÍCULOS (ficha digital / historial de piezas)
# ============================================================
if pagina == PAGINAS[6]:
    st.subheader("🚗 Ficha digital del vehículo")
    st.caption(
        "Registrá la patente de un cliente frecuente junto con las piezas que le fuiste cambiando. "
        "La app avisa cuándo una pieza ya recorrió casi toda su vida útil estimada."
    )

    vehiculos_atrasados = listar_vehiculos_atrasados()
    with st.expander(f"⚠️ Vehículos con mantenimiento atrasado ({len(vehiculos_atrasados)})", expanded=bool(vehiculos_atrasados)):
        if not vehiculos_atrasados:
            st.caption(
                "Ninguno detectado por ahora (o todavía no cargaste km de registro/actual en los vehículos)."
            )
        else:
            st.caption("Ordenados por urgencia — el que tiene la pieza más atrasada aparece primero.")
            for item in vehiculos_atrasados:
                v = item["vehiculo"]
                nombre_auto = f"{v.get('marca_auto') or ''} {v.get('modelo_auto') or ''}".strip()
                piezas_txt = ", ".join(f"{p['Pieza']} (x{p['Atraso estimado']})" for p in item["piezas_atrasadas"])
                colv1, colv2 = st.columns([4, 1])
                colv1.write(f"**{v['patente']}** {nombre_auto} — {v.get('cliente_nombre') or 'sin nombre'}")
                colv1.caption(f"Atrasado: {piezas_txt}")
                if colv2.button("👁️ Ver", key=f"ver_atrasado_{v['id']}"):
                    st.session_state["patente_buscar"] = v["patente"]
                    st.rerun()

    st.markdown("---")
    st.markdown("**Buscar / registrar un vehículo**")

    with st.expander("📷 Cargar por foto de cédula/título (con IA)"):
        st.caption(
            "Sacale una foto a la cédula verde/azul o al título. La IA lee patente, marca, modelo, "
            "año y motorización — **siempre revisá los datos antes de guardar**, un OCR puede "
            "confundir letras o números parecidos."
        )
        foto_cedula = subir_archivo("Foto de la cédula/título:", ["png", "jpg", "jpeg"], "cedula")
        cedula_ok = archivo_listo(foto_cedula, "foto de la cédula")
        if foto_cedula:
            boton_otro_archivo("cedula", "🗑️ Usar otra foto", key="otra_foto_cedula")
        if st.button("🔍 Leer datos", disabled=not cedula_ok):
            with st.spinner("Leyendo..."):
                datos_cedula, error_cedula = extraer_datos_cedula(foto_cedula.getvalue())
            if error_cedula:
                st.error(error_cedula)
            else:
                st.session_state["datos_cedula_leidos"] = datos_cedula
        if st.session_state.get("datos_cedula_leidos"):
            datos = st.session_state["datos_cedula_leidos"]
            st.json(datos)
            if st.button("✅ Usar estos datos"):
                st.session_state["cedula_pendiente"] = datos
                st.session_state.pop("datos_cedula_leidos", None)
                st.rerun()

    # Si se leyó una cédula, precargar los campos ANTES de crear los widgets — si se hace
    # después de que ya se dibujaron en pantalla, Streamlit tira un error.
    if "cedula_pendiente" in st.session_state:
        datos = st.session_state.pop("cedula_pendiente")
        if datos.get("patente"):
            st.session_state["patente_buscar"] = str(datos["patente"]).strip().upper()
        st.session_state["form_marca_auto"] = datos.get("marca") or ""
        st.session_state["form_modelo_auto"] = datos.get("modelo") or ""
        st.session_state["form_anio_auto"] = str(datos.get("anio") or "")
        st.session_state["form_motorizacion_auto"] = datos.get("motorizacion") or ""

    # El VIN que se resolvió a patente en la vuelta anterior se vuelca ACÁ, antes de dibujar el
    # campo. Escribirlo después de dibujado —que es lo que se hacía— Streamlit no lo permite:
    # tira StreamlitAPIException y corta la pantalla. Pasaba con solo pegar un chasis de 17.
    if "patente_pendiente" in st.session_state:
        st.session_state["patente_buscar"] = st.session_state.pop("patente_pendiente")

    patente_input = st.text_input(
        "Patente o VIN:", placeholder="Ej: AB123CD — o el chasis completo", key="patente_buscar"
    ).strip().upper()

    # Si lo que pegaron es un VIN de 17, se resuelve a la patente y se sigue como siempre.
    if len(re.sub(r"\s", "", patente_input)) == 17:
        ficha_por_vin = buscar_vehiculo_por_vin(patente_input)
        if ficha_por_vin:
            patente_input = ficha_por_vin["patente"]
            avisar("success", f"🔎 Ese chasis es la patente **{patente_input}**.")
            st.session_state["patente_pendiente"] = patente_input
            st.rerun()
        else:
            st.info(
                "Ese VIN no está en ninguna ficha todavía. Cargá la patente del auto y poné el "
                "VIN en los datos del vehículo: la próxima vez lo encontrás pegando el chasis."
            )

    if patente_input:
        vehiculo = buscar_vehiculo(patente_input)

        # LO QUE LA PATENTE DICE POR SÍ SOLA. No hay base pública que traduzca patente a
        # vehículo, pero el formato y la serie sí se leen sin consultar nada: si es Mercosur o
        # vieja, si es auto o moto, de qué provincia salió (las provinciales) y sobre todo en
        # qué años se patentó, que es lo que el mostrador pregunta siempre después del modelo.
        _lectura_pat = leer_patente(patente_input)
        if _lectura_pat["formato"]:
            _desde_pat, _hasta_pat, _de_donde = anio_probable_de_patente(patente_input)
            _partes_pat = [f"🪪 **{_lectura_pat['detalle']}**"]
            if _lectura_pat["provincia"]:
                _partes_pat.append(f"Salió de **{_lectura_pat['provincia']}**.")
            if _desde_pat and _hasta_pat and _desde_pat != _hasta_pat:
                _partes_pat.append(f"Patentado entre **{_desde_pat} y {_hasta_pat}** "
                                    f"— {_de_donde}.")
            elif _hasta_pat:
                _partes_pat.append(f"Patentado **hasta {_hasta_pat}** — {_de_donde}.")
            if not (vehiculo or {}).get("anio"):
                _partes_pat.append("Es una estimación: si sabés el año exacto, cargalo abajo y "
                                   "de paso la app afina la estimación para las próximas.")
            st.info(" ".join(_partes_pat))
            _anio_sugerido = (str(_desde_pat + (_hasta_pat - _desde_pat) // 2)
                              if _desde_pat and _hasta_pat else "")
        else:
            _anio_sugerido = ""
            if len(re.sub(r"[^A-Z0-9]", "", patente_input)) >= 6:
                st.caption("No reconozco el formato de esa patente. Las argentinas son "
                           "**AB 123 CD** (Mercosur), **ABC 123** (vieja) o **B 123 456** "
                           "(provincial, hasta 1994).")

        with st.expander("✏️ Datos del cliente / vehículo", expanded=(vehiculo is None)):
            with st.form("form_vehiculo"):
                cv1, cv2 = st.columns(2)
                cliente_nombre = cv1.text_input("Nombre del cliente", value=(vehiculo or {}).get("cliente_nombre") or "")
                cliente_tel = cv2.text_input("Teléfono", value=(vehiculo or {}).get("cliente_telefono") or "")
                cv3, cv4 = st.columns(2)
                marca_auto = cv3.text_input("Marca del auto", value=(vehiculo or {}).get("marca_auto") or "",
                                             key="form_marca_auto")
                modelo_auto = cv4.text_input("Modelo", value=(vehiculo or {}).get("modelo_auto") or "",
                                              key="form_modelo_auto")
                cv5, cv6, cv7 = cols(3)
                # El año que sugiere la patente va de placeholder, no de valor: es una
                # estimación y el que carga la ficha tiene que decidir si la toma.
                anio_auto = cv5.text_input("Año", value=(vehiculo or {}).get("anio") or "",
                                            key="form_anio_auto",
                                            placeholder=(f"≈ {_anio_sugerido}" if _anio_sugerido
                                                          else "Ej: 2012"))
                motorizacion_auto = cv6.text_input("Motorización", value=(vehiculo or {}).get("motorizacion") or "",
                                                    key="form_motorizacion_auto")
                km_actual_input = cv7.number_input(
                    "Km actual", min_value=0, step=1000,
                    value=int((vehiculo or {}).get("km_actual") or 0)
                )
                numero_motor_auto = st.text_input(
                    "N° de motor (opcional)", value=(vehiculo or {}).get("numero_motor") or "",
                    key="form_numero_motor",
                    placeholder="El grabado en el block, como esté",
                    help="Sirve cuando el auto tiene el motor cambiado: ahí el VIN lleva a los "
                         "repuestos equivocados y este número a los correctos. Se busca sin "
                         "importar espacios ni guiones."
                )
                vin_auto = st.text_input(
                    "VIN / número de chasis (opcional)", value=(vehiculo or {}).get("vin") or "",
                    key="form_vin_auto", max_chars=17,
                    help="Cargarlo sirve para dos cosas: podés encontrar este auto por el chasis "
                         "además de por la patente, y la app aprende sola qué modelo corresponde "
                         "a ese patrón de VIN, así el próximo auto igual se completa solo."
                ).strip().upper()
                guardar_vehiculo = st.form_submit_button("💾 Guardar vehículo", type="primary")
            if guardar_vehiculo:
                vin_limpio = re.sub(r"\s", "", vin_auto)
                if vin_limpio and len(vin_limpio) != 17:
                    st.warning("El VIN tiene que tener 17 caracteres — se guardó el resto sin él.")
                    vin_limpio = ""
                get_or_create_vehiculo(patente_input, cliente_nombre, cliente_tel, marca_auto, modelo_auto,
                                        km_actual_input or None, anio_auto, motorizacion_auto,
                                        vin=vin_limpio)
                # El número de motor se guarda aparte: get_or_create_vehiculo tiene ya ocho
                # parámetros y sumarle uno más es la forma de romper las diez llamadas que tiene.
                if (numero_motor_auto or "").strip():
                    with db_lock:
                        c.execute("""UPDATE vehiculos SET numero_motor = ?
                                     WHERE UPPER(patente) = UPPER(?)""",
                                  (numero_motor_auto.strip(), patente_input.strip()))
                        conn.commit()
                st.success(f"Vehículo {patente_input} guardado.")
                if vin_limpio and modelo_auto.strip():
                    st.caption(f"📚 De paso quedó aprendido que el patrón {vin_limpio[:3]}-"
                               f"{vin_limpio[3:8]} es un {modelo_auto.strip()}.")
                st.rerun()

        vehiculo = buscar_vehiculo(patente_input)
        if vehiculo:
            km_actual = vehiculo.get("km_actual")
            km_registro = vehiculo.get("km_registro")
            st.write(
                f"**{vehiculo.get('marca_auto') or ''} {vehiculo.get('modelo_auto') or ''}** — "
                f"Cliente: {vehiculo.get('cliente_nombre') or 'sin nombre'}"
            )

            km_calc = calcular_km_recorridos(vehiculo)
            mk1, mk2, mk3 = st.columns(3)
            mk1.metric("Km de registro", km_registro if km_registro is not None else "—")
            mk2.metric("Km actual", km_actual if km_actual is not None else "—")
            mk3.metric("Km recorridos", km_calc["km_recorridos"] if km_calc["km_recorridos"] is not None else "—")
            if km_calc["promedio_mensual"] is not None:
                st.caption(
                    f"📈 Promedio aproximado: **{km_calc['promedio_mensual']:,} km/mes** "
                    f"(en base a {km_calc['dias_transcurridos']} día(s) desde que se registró el vehículo)."
                )

            with st.expander("✏️ Corregir km de registro (solo si se cargó mal la primera vez)"):
                st.caption(
                    "El km de registro queda fijo automáticamente la primera vez que cargás el vehículo. "
                    "Usá esto solo para corregir un error de tipeo — cambiarlo afecta los cálculos de abajo."
                )
                nuevo_km_registro = st.number_input(
                    "Km de registro correcto", min_value=0, step=1000,
                    value=int(km_registro or 0), key="corregir_km_registro"
                )
                if st.button("💾 Corregir km de registro"):
                    actualizar_km_registro(vehiculo["id"], nuevo_km_registro or None)
                    avisar("success", "Km de registro actualizado.")
                    st.rerun()

            alertas = []
            if km_actual is not None:
                alertas = calcular_alertas_vehiculo(vehiculo["id"], km_actual)
                if alertas:
                    st.warning(f"⚠️ {len(alertas)} pieza(s) cerca de cumplir su vida útil estimada:")
                    st.dataframe(alertas, width="stretch", hide_index=True)
                else:
                    st.info("Sin alertas de mantenimiento por ahora.")

            st.markdown("---")
            st.markdown("**➕ Agregar pieza al historial**")
            with st.form("form_pieza", clear_on_submit=True):
                cp1, cp2 = st.columns(2)
                desc_pieza = cp1.text_input("Descripción de la pieza", placeholder="Ej: Kit de distribución")
                marca_pieza = cp2.text_input("Marca de la pieza", placeholder="Ej: SKF")
                cp3, cp4, cp5 = st.columns(3)
                codigo_pieza = cp3.text_input("Código (opcional)")
                km_instalacion = cp4.number_input("Km al instalarla", min_value=0, step=1000,
                                                    value=int(km_actual or 0))
                vida_util = cp5.number_input("Vida útil estimada (km, opcional)", min_value=0, step=5000, value=0)
                nota_pieza = st.text_input("Nota (opcional)")
                agregar_pieza = st.form_submit_button("➕ Agregar al historial", type="primary")
            if agregar_pieza:
                if not desc_pieza.strip():
                    st.warning("Completá la descripción de la pieza.")
                else:
                    agregar_pieza_historial(vehiculo["id"], desc_pieza, marca_pieza, codigo_pieza,
                                             km_instalacion or None, vida_util or None, nota_pieza)
                    avisar("success", "Pieza agregada al historial.")
                    st.rerun()

            st.markdown("---")
            st.markdown("**📋 Historial completo**")
            historial_vehiculo = listar_historial_vehiculo(vehiculo["id"])
            if historial_vehiculo:
                st.dataframe(quitar_id(historial_vehiculo), width="stretch", hide_index=True)
            else:
                st.caption("Todavía no hay piezas registradas para este vehículo.")

            st.markdown("---")
            st.markdown("**🔧 Proyección de mantenimiento**")
            st.caption(
                "Compara, para cada tipo de pieza con vida útil cargada, cuántas veces se cambió "
                "realmente contra cuántas veces debería haberse cambiado según los km recorridos "
                "totales desde que se registró el vehículo."
            )
            proyeccion = []
            # 'atrasadas' también se inicializa acá aunque más abajo siempre se asigne en las dos
            # ramas del else: si km_recorridos es None, nunca se asignaba, y el único motivo por
            # el que no explotaba es que "if proyeccion and atrasadas" corta antes de leerla.
            # Alcanzaba con dar vuelta esa condición para romper la ficha del vehículo.
            atrasadas = []
            if km_calc["km_recorridos"] is None:
                st.info(
                    "Para calcular esto hace falta el km de registro y el km actual del vehículo "
                    "(completá 'Kilometraje actual' arriba si todavía no lo cargaste)."
                )
            else:
                proyeccion = calcular_proyeccion_mantenimiento(vehiculo["id"], km_calc["km_recorridos"])
                if proyeccion:
                    atrasadas = [p for p in proyeccion if p["Atraso estimado"] > 0]
                    if atrasadas:
                        st.warning(f"⚠️ {len(atrasadas)} pieza(s) con cambios atrasados según el kilometraje:")
                    st.dataframe(proyeccion, width="stretch", hide_index=True)
                else:
                    st.caption("Todavía no hay piezas con vida útil cargada para proyectar.")
                    atrasadas = []

            st.markdown("---")
            st.markdown("**📤 Compartir con el cliente**")
            col_pdf, col_wa = st.columns(2)
            with col_pdf:
                st.download_button(
                    "📄 Descargar ficha en PDF",
                    data=pdf_con_cache("ficha_vehiculo", generar_pdf_ficha_vehiculo,
                                        vehiculo, km_calc, alertas, proyeccion, historial_vehiculo),
                    file_name=f"ficha_{vehiculo['patente']}.pdf",
                    mime="application/pdf",
                    width="stretch"
                )
            with col_wa:
                if proyeccion and atrasadas:
                    nombre_cliente = vehiculo.get("cliente_nombre") or ""
                    nombre_auto_msg = f"{vehiculo.get('marca_auto') or ''} {vehiculo.get('modelo_auto') or ''}".strip()
                    piezas_atrasadas_txt = ", ".join(p["Pieza"] for p in atrasadas)
                    mensaje_wa = (
                        f"Hola {nombre_cliente}! Te escribimos de El Chavo. Revisando el kilometraje de tu "
                        f"{nombre_auto_msg} ({vehiculo['patente']}), notamos que tenés atrasado el cambio de: "
                        f"{piezas_atrasadas_txt}. ¿Coordinamos un turno?"
                    ).strip()
                    tel_limpio = re.sub(r"\D", "", vehiculo.get("cliente_telefono") or "")
                    url_wa_vehiculo = (
                        f"https://wa.me/{tel_limpio}" if tel_limpio else "https://wa.me/"
                    ) + "?text=" + quote(mensaje_wa)
                    st.link_button("📲 Avisar atraso por WhatsApp", url_wa_vehiculo,
                                    type="primary", width="stretch")
                else:
                    st.caption("Sin atrasos detectados todavía para avisar por WhatsApp.")

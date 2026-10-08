"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/."""

# ============================================================
# BUSCADOR
# ============================================================
if pagina == PAGINAS[0]:
    def _guia_y_lo_que_espera_aprobacion():
        """La guía rápida y el cartel de lo que espera aprobación. Para el administrador en la
        computadora van arriba, como siempre; para los demás, AL FINAL de la página del buscador. Mirada en un celular
        de verdad, la caja de búsqueda quedaba tres pantallas abajo: estos dos, los avisos de
        salud abiertos y el encabezado completo iban antes. Quien atiende el mostrador entra
        a buscar un código, y el cartel de lo que espera aprobación explica los resultados:
        abajo de ellos también se entiende."""
        with st.expander("❓ Guía rápida — cómo usar esta app"):
            # Las secciones salen de PARA_QUE_SIRVE, el mismo renglón que se ve debajo del menú:
            # escritas aparte, la guía decía que Cargar Excel «arma las equivalencias sola»,
            # cuando quedan esperando aprobación —que es justo lo que explica que un código
            # recién importado no traiga sus equivalentes—.
            st.markdown(
                "**Cómo se trabaja, en tres pasos:**\n\n"
                "1. **📁 Cargar Excel** — subís la lista de precios de cada proveedor (Excel, CSV "
                "o PDF con tabla). Los productos y precios quedan buscables enseguida.\n"
                "2. **📊 Estadísticas → 🔗 Equivalencias sugeridas** — la app propone qué códigos "
                "de distintos proveedores son la misma pieza, y vos las aprobás (en bloque las "
                "limpias). **Hasta que no se aprueban, no aparecen al buscar.**\n"
                "3. **🔍 Buscador** — escribís el código que te piden y ves todas las marcas que "
                "sirven en su lugar, con precio, stock y qué tan segura es cada una (🟢 "
                "confirmada, 🟡 probable, 🟠 revisar). También sirve escribir palabras —«filtro "
                "aceite gol», «mannol»—: busca solo en las descripciones y las marcas.\n\n"
                "**Cada sección:**\n\n"
                + "\n".join(f"- **{_p}** — {PARA_QUE_SIRVE[_p]}" for _p in PAGINAS
                             if PARA_QUE_SIRVE.get(_p))
                + "\n\nLo que borra o configura algo pide la contraseña de administrador."
            )

        # Lo que está esperando aprobación se avisa ACÁ, no solo en Estadísticas. Mientras haya
        # vínculos sin aprobar, la búsqueda no cruza marcas: se busca un código de un proveedor y no
        # aparecen los equivalentes de los otros. Visto desde el mostrador eso se parece bastante a
        # «la app no relaciona proveedores», y no había nada en esta pantalla que lo explicara.
        # Solo a quien las puede aprobar: el que entró sin contraseña no llega a Estadísticas, y
        # para él era un cartel más sin nada que hacer. Ver es_empleado_o_abierto().
        _esperando = equivalencias_esperando_revision() if es_empleado_o_abierto() else 0
        if _esperando and es_celular():
            # Lo mismo en una línea: en el celular este cartel ocupaba media pantalla justo arriba
            # de la caja de búsqueda.
            st.warning(f"🔒 **{miles(_esperando)} equivalencia(s) esperando aprobación**: todavía no "
                       "aparecen al buscar. Se aprueban en Estadísticas → 🔗 Equivalencias sugeridas.")
        elif _esperando:
            st.warning(
                f"🔒 Hay **{miles(_esperando)} equivalencia(s) esperando aprobación**. Hasta que las "
                "apruebes no se usan: buscar un código no va a traer los equivalentes de las otras "
                "marcas. Se aprueban en bloque desde **Estadísticas → 🔗 Equivalencias sugeridas**."
            )
        if _esperando:
            st.button("🔗 Ir a aprobarlas →", key="ir_a_aprobar_sugeridas",
                      on_click=ir_a_donde_dice_el_aviso,
                      args=(miga_hasta("Equivalencias sugeridas"),))

    # Arriba de la caja de búsqueda solo para el administrador en la computadora: para quien
    # atiende el mostrador —en el celular o en la computadora— van al final. Medido en una
    # computadora de 1366x768: con los avisos de salud abiertos, esto y el encabezado, la caja
    # quedaba en la tercera pantalla; el cartel de «esperando aprobación» es una tarea que un
    # empleado no puede hacer.
    _guia_arriba = not es_celular() and es_admin()
    if _guia_arriba:
        _guia_y_lo_que_espera_aprobacion()

    # Si se tocó un botón de sugerencia rápida (favorito o búsqueda reciente), precargamos el
    # campo de búsqueda ANTES de crear el widget — si se hace después de creado, Streamlit tira error.
    if "sugerencia_busqueda" in st.session_state:
        st.session_state["busqueda_input"] = st.session_state.pop("sugerencia_busqueda")

    # A QUIÉN SE ATIENDE: se elige una vez, antes de pedir o de armar el presupuesto, y todo lo
    # que se pida al depósito va a esa cuenta. Ver «A QUIÉN SE ESTÁ ATENDIENDO» en
    # logica/deposito.py.
    if es_empleado_o_abierto():
        mostrar_cuenta_elegida("buscador")

    # El carrito arriba de todo: si está armándose un presupuesto, tiene que estar a la vista.
    # Escondido en otra pantalla, la gente se olvida de lo que ya sumó y lo suma dos veces.
    if st.session_state.get("carrito"):
        _cart = st.session_state["carrito"]
        _total = sum((x["precio"] or 0) * x["cantidad"] for x in _cart.values())
        with st.expander(f"🛒 Presupuesto en armado — {len(_cart)} ítem(s) · ${miles(_total, 0)}"
                         + (f" · para {cuenta_elegida()['nombre']}" if cuenta_elegida() else ""),
                          expanded=False):
            _pedir_de_a_uno = es_empleado_o_abierto()
            for _pid, _item in list(_cart.items()):
                if _pedir_de_a_uno:
                    ci1, ci2, ci4, ci3 = st.columns([5, 2, 1, 1])
                    # De a uno: el que atiende va pidiendo lo que el cliente ya confirmó, sin
                    # mandar el presupuesto entero (ver pedir_uno_del_presupuesto()).
                    ci4.button("📦", key=f"pedir_uno_cart_{_pid}",
                               help=f"Pedir solo este al depósito, para "
                                    f"{nombre_de_la_cuenta_elegida()}",
                               on_click=pedir_uno_del_presupuesto, args=(_pid,))
                else:
                    ci1, ci2, ci3 = st.columns([5, 2, 1])
                ci1.markdown(f"**{_item['marca']} {_item['codigo']}** — "
                              f"{(_item['descripcion'] or '')[:40]}")
                _nueva_cant = ci2.number_input("Cant.", min_value=1, value=_item["cantidad"],
                                                step=1, key=f"cant_cart_{_pid}",
                                                label_visibility="collapsed")
                if _nueva_cant != _item["cantidad"]:
                    st.session_state["carrito"][_pid]["cantidad"] = int(_nueva_cant)
                    st.rerun()
                if ci3.button("🗑️", key=f"quitar_cart_{_pid}"):
                    st.session_state["carrito"].pop(_pid, None)
                    # También la cantidad que quedó guardada del widget: sin esto, volver a
                    # sumar el mismo producto lo traía con la cantidad vieja en vez de 1.
                    st.session_state.pop(f"cant_cart_{_pid}", None)
                    st.rerun()

            _lineas = [f"{x['marca']} {x['codigo']} x{x['cantidad']} — "
                       f"${miles((x['precio'] or 0) * x['cantidad'], 0)}" for x in _cart.values()]
            # Con la cuenta elegida, el presupuesto dice para quién es. Los precios son los de
            # lista: el descuento de la cuenta no se ve (ver «EL DESCUENTO NO SE VE»).
            _texto = ((f"Para: {cuenta_elegida()['nombre']}\n\n" if cuenta_elegida() else "")
                      + "\n".join(_lineas) + f"\n\nTOTAL: ${miles(_total, 0)}")
            st.caption("Para copiar y mandar por WhatsApp:")
            st.code(_texto, language=None)
            # Pedir todo junto al depósito, para la cuenta elegida arriba (o Mostrador). Lo
            # pedido sale del presupuesto: tocarlo dos veces no lo pide dos veces.
            if _pedir_de_a_uno:
                st.caption("«📦» al lado de cada uno lo pide solo a ese. «Pedir todo» los manda "
                           "juntos: el depósito los ve como un solo pedido.")
            if _pedir_de_a_uno and st.button(
                    f"📦 Pedir todo al depósito — para {nombre_de_la_cuenta_elegida()}",
                    type="primary", key="pedir_todo_el_presupuesto"):
                _pedidos, _fallas = pedir_lo_elegido_al_deposito(
                    [(_pid, _item["cantidad"]) for _pid, _item in _cart.items()])
                for _pid in _pedidos:
                    st.session_state["carrito"].pop(_pid, None)
                    st.session_state.pop(f"cant_cart_{_pid}", None)
                if _pedidos:
                    avisar("success", f"📦 {len(_pedidos)} ítem(s) pedidos al depósito, para "
                                      f"{nombre_de_la_cuenta_elegida()}.")
                for _f in _fallas:
                    avisar("warning", _f)
                st.rerun()
            cb1, cb2 = st.columns(2)
            if cb1.button("🔒 Apartar todo el presupuesto"):
                _apartados, _fallaron = 0, []
                for _pid, _item in list(_cart.items()):
                    _ok, _msg = reservar_stock(_pid, _item["cantidad"], "presupuesto")
                    if _ok:
                        _apartados += 1
                        # Lo apartado sale del carrito. Si se quedara, tocar el botón otra vez
                        # —porque uno de los ítems falló, por ejemplo— volvía a apartar los que
                        # ya estaban apartados y el stock libre terminaba en cualquier cosa.
                        st.session_state["carrito"].pop(_pid, None)
                        st.session_state.pop(f"cant_cart_{_pid}", None)
                    else:
                        _fallaron.append(f"{_item['codigo']}: {_msg}")
                # Siempre se refresca: avisar() guarda el mensaje PARA el refresco. Sin refrescar,
                # el "Se apartaron N" quedaba guardado y no se mostraba nunca — justo cuando algún
                # ítem fallaba, que es cuando más importa saber qué sí se apartó.
                if _apartados:
                    avisar("success", f"Se apartaron {_apartados} ítem(s).")
                for _f in _fallaron:
                    avisar("warning", _f)
                st.rerun()
            if cb2.button("🗑️ Vaciar presupuesto"):
                st.session_state["carrito"] = {}
                st.rerun()

    # El escáner va PRIMERO, antes que la foto y las medidas. No es una preferencia de orden:
    # el código de barras es exacto, y todo lo demás —comparar siluetas, leer un grabado
    # gastado, medir— es aproximar. Poner primero lo confiable evita que alguien resuelva con
    # una adivinanza algo que la caja tenía escrito.
    with st.expander("📷 Escanear el código de barras de la caja"):
        explicar(
            "La forma más segura de identificar un repuesto: no hay nada que adivinar.",
            "El código de la caja es exacto. A diferencia de comparar fotos o leer un grabado, "
            "acá no hay interpretación posible: o lo lee o no lo lee.\n\nSacá la foto de cerca, "
            "con buena luz y el código derecho, ocupando buena parte de la pantalla. Sirve "
            "también para QR.", en_expander=True
        )
        foto_barras = st.camera_input("Apuntá al código de barras", key="cam_barras")
        if foto_barras is None:
            foto_barras = subir_archivo("...o subí una foto ya sacada:",
                                         ["jpg", "jpeg", "png"], "barras_archivo")
        if foto_barras is not None:
            datos_foto = foto_barras.getvalue() if hasattr(foto_barras, "getvalue") else foto_barras
            with st.spinner("Leyendo el código..."):
                codigos_leidos, err_barras = leer_codigo_de_barras(datos_foto)
            if err_barras:
                st.warning(err_barras)
            else:
                for cod_barra in codigos_leidos:
                    st.success(f"📷 Código leído: **`{cod_barra}`**")
                    # De dónde es se sabe sin consultar nada: lo dice el prefijo. Sirve para
                    # decidir si el repuesto lo consigue un proveedor local o hay que traerlo.
                    _pais_barra = pais_del_codigo_de_barras(cod_barra)
                    if _pais_barra and _pais_barra not in GS1_NO_ES_UN_PAIS:
                        st.caption(f"🌍 El código lo registró una empresa de **{_pais_barra}** "
                                    "(el país de quien lo emitió, no necesariamente el de la "
                                    "fábrica).")
                    res_barra, nota_barra = buscar_por_codigo_de_barras(cod_barra)
                    if nota_barra:
                        st.caption(nota_barra)
                    if res_barra:
                        st.success(f"✅ {len(res_barra)} coincidencia(s) — es una coincidencia "
                                    "exacta de código, no un parecido:")
                        st.dataframe(quitar_id(res_barra), width="stretch",
                                      hide_index=True)
                    elif _pais_barra in GS1_NO_ES_UN_PAIS:
                        # Qué decir acá depende de quién imprime las etiquetas, y es lo
                        # contrario en cada caso. Ver el_negocio_etiqueta_con_codigos_propios().
                        if el_negocio_etiqueta_con_codigos_propios():
                            st.warning(
                                f"El código `{cod_barra}` **no está cargado**. Es un código de "
                                "uso interno, del rango que usás para tus propias etiquetas, "
                                "así que lo más probable es que sea una etiqueta tuya que "
                                "todavía no le pegaste a ningún producto. Se cargan de a "
                                f"muchos en {miga_hasta('Cargar códigos de barras en masa')}."
                            )
                        else:
                            st.warning(
                                f"El código `{cod_barra}` no es el de un producto: es "
                                f"**{_pais_barra}**. Si es de uso interno lo imprimió un "
                                "comercio para sí mismo y no vale afuera; si es un libro o una "
                                "revista, escaneaste otra cosa. Buscá el código de barras del "
                                "repuesto, que suele estar en otra cara de la caja."
                            )
                    else:
                        st.warning(
                            f"El código `{cod_barra}` no está cargado en tu catálogo."
                        )
                        # El dígito verificador SOLO se menciona acá: cuando no se encontró.
                        # Si el repuesto apareció, el número está bien por definición —coincide
                        # con el cargado— cierre la cuenta o no, y avisar ahí sería decirle
                        # «está mal tipeado» a alguien que acaba de escanear su propia etiqueta
                        # y encontró lo que buscaba. Con un negocio que etiqueta su mercadería,
                        # eso sería un cartel de error en CADA escaneo.
                        if codigo_de_barras_cierra(cod_barra) is False:
                            st.caption(
                                "🔢 Además, ese número **no cierra con su dígito verificador**. "
                                "Si la etiqueta es del fabricante, está mal leída o mal "
                                "tipeada: probá de nuevo más cerca y con mejor luz. Si es una "
                                "etiqueta tuya, es normal que no cierre y no significa nada."
                            )
                        parecidos_barra = codigos_por_tipeo(sanitizar(cod_barra))
                        if parecidos_barra:
                            st.caption("Códigos parecidos que sí tenés:")
                            st.dataframe(
                                [{"Código": x["Codigo"], "Marca": x["Marca"],
                                  "Descripción": x["Descripcion"], "Stock": x["Stock"]}
                                 for x in parecidos_barra],
                                width="stretch", hide_index=True)
                        ajeno_barra = identificar_codigo_ajeno(sanitizar(cod_barra))
                        if ajeno_barra:
                            st.info(f"🏭 Según el catálogo de {ajeno_barra['marca']}, es "
                                     f"{ajeno_barra['tipo'] or 'una pieza'} para "
                                     f"{ajeno_barra['cantidad_autos']} auto(s).")

    if es_operador_o_admin():
        with st.expander("🖼️ Buscar por parecido visual (experimental)"):
            explicar(
                "Compará una foto contra el catálogo. Sirve para acortar candidatos, nunca para "
                "confirmar una venta.",
                "No hace falta que sea la misma foto: aguanta otro ángulo, otro fondo y otro color "
                "de pieza — se compara en blanco y negro, recortando el fondo.\n\nAun así es "
                "**mucho** menos confiable que un código exacto. Con piezas lisas sin marcas ni "
                "grabado (rótulas, rulemanes, bulones) rinde mal por más buena que sea la foto. "
                "Para esas, **📐 Buscar por medidas mecánicas** anda mucho mejor.", en_expander=True
            )

            fotos_listas, prod_con_foto, fotos_pendientes, fotos_no_sirven = contar_fotos_comparables()
            fotos_pendientes = max(fotos_pendientes, contar_fotos_pendientes_de_firma())
            st.caption(
                f"📊 {fotos_listas} foto(s) listas para comparar, sobre {prod_con_foto} producto(s)" +
                (f" — {fotos_pendientes} pendiente(s) de procesar" if fotos_pendientes else "") +
                (f" — {fotos_no_sirven} sin detalle suficiente" if fotos_no_sirven else "")
            )

            if fotos_listas == 0 and fotos_pendientes == 0:
                st.info(_mensaje_catalogo_visual_vacio())

            # Se procesa una tanda chica sola, cada vez que se abre este panel. Antes había que
            # acordarse de tocar el botón, y como el comparador fue mejorando, las fotos viejas
            # quedaban con la firma vieja sin que nadie se enterara: la mejora no llegaba nunca
            # al catálogo que ya estaba cargado. La tanda es de 25 a propósito, para que abrir
            # el panel no se cuelgue.
            if fotos_pendientes:
                with st.spinner(f"Poniendo al día {min(fotos_pendientes, 25)} foto(s)..."):
                    _r = migrar_imagenes_pendientes(limite=25)
                if _r["listas"]:
                    st.caption(f"🔄 Se pusieron al día {_r['listas']} foto(s) automáticamente.")
                fotos_listas, prod_con_foto, fotos_pendientes, fotos_no_sirven = contar_fotos_comparables()
                fotos_pendientes = max(fotos_pendientes, contar_fotos_pendientes_de_firma())

            st.checkbox(
                "🤖 Traer fotos solas, en segundo plano",
                value=obtener_config("fotos_automaticas", "0") == "1",
                key="fotos_auto_check",
                on_change=lambda: prender_tarea_de_fondo(
                    "fotos", "fotos_automaticas", st.session_state["fotos_auto_check"]),
                help="Mientras la app esté abierta, va trayendo fotos de las fichas del "
                     "proveedor en un hilo aparte: nadie espera. Sale a internet, por eso lo "
                     "elegís vos."
            )
            if obtener_config("fotos_automaticas", "0") == "1":
                mostrar_avance_de_tanda("fotos", "foto(s)")

            if fotos_pendientes and st.button(
                    f"🔄 Procesar las {fotos_pendientes} que faltan ahora"):
                with st.spinner("Procesando fotos..."):
                    r = migrar_imagenes_pendientes()
                partes = []
                if r["listas"]:
                    partes.append(f"{r['listas']} lista(s) para comparar")
                if r["sin_detalle"]:
                    partes.append(f"{r['sin_detalle']} sin detalle suficiente")
                if r["links"]:
                    partes.append(f"{r['links']} son links externos (se bajan en "
                                  f"{miga_hasta('Fotos')})")
                if r["error"]:
                    partes.append(f"{r['error']} con error")
                avisar("success", "Procesadas: " + (", ".join(partes) if partes else "no había nada pendiente") + ".")
                st.rerun()

            origen_visual = st.radio(
                "¿De dónde sale la foto a buscar?",
                ["📷 Subir una foto", "🔗 Pegar una dirección web"],
                horizontal=True, key="origen_foto_visual"
            )

            bytes_consulta = None

            if origen_visual.startswith("📷"):
                foto_visual = subir_archivo(
                    "Foto de la pieza:", ["png", "jpg", "jpeg"], "foto_visual",
                    label_visibility="collapsed"
                )
                if archivo_listo(foto_visual, "foto"):
                    bytes_consulta = foto_visual.getvalue()
                if foto_visual:
                    if st.button("🗑️ Usar otra foto", key="otra_foto_visual"):
                        olvidar_archivo("foto_visual")
                        st.session_state.pop("ocr_visual", None)
                        st.session_state.pop("resultado_visual", None)
                        st.rerun()
            else:
                ayuda(
                    "Pegá la dirección de la ficha del producto (la de tu proveedor, la de Mercado "
                    "Libre, la que sea) o la de la imagen sola. Se bajan las fotos de esa página y "
                    "elegís cuál usar — no hace falta guardar nada en el teléfono."
                )
                url_visual = st.text_input(
                    "Dirección web:", placeholder="https://...", key="url_foto_visual"
                ).strip()
                if st.button("⬇️ Traer fotos de esa dirección", disabled=not url_visual):
                    with st.spinner("Bajando..."):
                        encontradas, error_url = imagenes_de_una_direccion(url_visual)
                    if error_url:
                        st.error(error_url)
                        st.session_state.pop("fotos_de_url", None)
                    else:
                        st.session_state["fotos_de_url"] = encontradas
                        st.session_state.pop("foto_url_elegida", None)

                encontradas = st.session_state.get("fotos_de_url")
                if encontradas:
                    st.caption(f"Se encontraron {len(encontradas)} foto(s). Elegí la de la pieza:")
                    filas_img = st.columns(min(len(encontradas), 4))
                    for idx, (url_img, datos_img) in enumerate(encontradas[:8]):
                        with filas_img[idx % len(filas_img)]:
                            st.image(datos_img, width="stretch")
                            if st.button("Usar esta", key=f"usar_img_url_{idx}"):
                                st.session_state["foto_url_elegida"] = idx
                                st.rerun()
                    elegida = st.session_state.get("foto_url_elegida")
                    if elegida is not None and elegida < len(encontradas):
                        bytes_consulta = encontradas[elegida][1]
                        st.success(f"✅ Foto {elegida + 1} elegida.")

            # Si la IA ya reconoció qué tipo de pieza es, se propone solo. Es la señal que más
            # mejora la comparación y es la que menos cuesta: la foto ya se mandó igual.
            _datos_ocr = (st.session_state.get("ocr_visual") or (None, None))[0]
            _familias = ["No sé / buscar en todo"] + sorted(FAMILIAS_REPUESTO.keys())
            if _datos_ocr and _datos_ocr.get("tipo_pieza"):
                _sugerida = clasificar_repuesto(_datos_ocr["tipo_pieza"])
                if _sugerida in _familias and not st.session_state.get("familia_visual"):
                    st.session_state["familia_visual"] = _sugerida
                    st.caption(f"🤖 La IA vio que es «{_datos_ocr['tipo_pieza']}», así que preseleccioné "
                                f"**{_sugerida}**. Cambialo si no acertó.")

            familia_elegida = st.selectbox(
                "¿Qué tipo de pieza es? (recomendado)", _familias,
                key="familia_visual",
                help="Es lo que más mejora el resultado, y no sale de la foto: vos ya sabés qué "
                     "pieza tenés en la mano. Diciéndolo, la app deja de ofrecerte cosas de otro "
                     "rubro que apenas se parecen de silueta."
            )
            familia_filtro = None if familia_elegida.startswith("No sé") else familia_elegida

            # PRIMERO leer el código grabado, después comparar formas. El orden importa: casi
            # todo repuesto trae el código estampado, impreso o troquelado, y leerlo da una
            # respuesta EXACTA. Comparar siluetas es adivinar. Tener las dos cosas separadas en
            # pantallas distintas hacía que se usara la peor sin necesidad.
            if bytes_consulta is not None:
                st.markdown("**Paso 1 — buscar un código en la foto**")
                ayuda(
                    "Casi todas las piezas traen el código grabado, impreso en una etiqueta o "
                    "moldeado. Si se llega a leer, la respuesta es exacta y no hay nada que adivinar."
                )
                if st.button("🔤 Leer el código de la foto", key="leer_codigo_visual"):
                    with st.spinner("Leyendo la pieza..."):
                        datos_ocr, err_ocr = identificar_pieza_por_foto(bytes_consulta)
                    st.session_state["ocr_visual"] = (datos_ocr, err_ocr)

                datos_ocr, err_ocr = st.session_state.get("ocr_visual", (None, None))
                if err_ocr:
                    st.info(f"{err_ocr} — igual podés comparar por parecido más abajo.")
                elif datos_ocr:
                    cod_leido = (datos_ocr.get("codigo") or "").strip()
                    conf_ocr = (datos_ocr.get("confianza") or "s/d").strip().lower()
                    if not cod_leido:
                        st.warning(
                            "No se pudo leer ningún código en la foto. Probá con más luz y de más "
                            "cerca, buscando el lado donde esté grabado. Si la pieza no tiene "
                            "código visible, usá la comparación por parecido de acá abajo."
                        )
                    else:
                        st.success(f"Código leído: **`{cod_leido}`** (la IA lo da con confianza "
                                    f"{conf_ocr})")
                        res_ocr = buscar_por_codigo(sanitizar(cod_leido))
                        if res_ocr:
                            st.success(f"✅ Está en tu catálogo — {len(res_ocr)} coincidencia(s):")
                            st.dataframe(quitar_id(res_ocr), width="stretch", hide_index=True)
                            st.caption("Esto es una coincidencia exacta de código, no un parecido.")
                        else:
                            # El OCR se come una letra seguido: es exactamente el caso que
                            # resuelve la búsqueda por tipeo.
                            parecidos_ocr = codigos_por_tipeo(sanitizar(cod_leido),
                                                              de_una_foto=True)
                            if parecidos_ocr:
                                mostrar_parecidos_de_una_lectura(cod_leido, parecidos_ocr)
                            else:
                                st.info(f"«{cod_leido}» no figura en tu catálogo ni se parece a nada "
                                         "cargado. Podés probar la comparación por parecido.")
                _fotos_hay, _, _fotos_sin_procesar, _fotos_lisas = contar_fotos_comparables()
                st.markdown("**Paso 2 — comparar por parecido** (si no se pudo leer el código)")
                if not _fotos_hay:
                    # Decirlo ACÁ y no después de apretar el botón. El paso 2 compara contra las
                    # fotos del catálogo: con cero cargadas no puede dar nada, nunca, y dejar el
                    # botón como si fuera a servir hace perder el tiempo dos veces — una
                    # apretándolo y otra entendiendo por qué no salió nada.
                    # Y decir cuál de los tres casos es: «no hay ninguna» era mentira cuando
                    # había fotos sin procesar o que no sirven para comparar.
                    if _fotos_sin_procesar:
                        st.caption(f"⚠️ Hay {_fotos_sin_procesar} foto(s) en el catálogo que "
                                   "todavía no se procesaron: tocá «🔄 Procesar las … que faltan "
                                   "ahora», más arriba en este panel.")
                    elif _fotos_lisas:
                        st.caption(f"⚠️ Las {_fotos_lisas} foto(s) del catálogo no sirven para "
                                   "comparar: no tienen detalles para agarrarse (pieza lisa, "
                                   "fondo del mismo color, poca luz). Saltá al **paso 3**.")
                    else:
                        st.caption("⚠️ No hay ninguna foto cargada en el catálogo, así que este "
                                   "paso no va a encontrar nada. Saltá al **paso 3**, que no "
                                   "necesita fotos cargadas. Si ya habías subido fotos y no "
                                   "están, se perdieron en un reinicio de la app: desde esta "
                                   "versión las que subís vos quedan en la copia de seguridad.")

            if st.button("🖼️ Comparar con el catálogo", disabled=bytes_consulta is None,
                         type="primary", key="btn_comparar_visual"):
                barra_v = st.progress(0.0, text="Comparando...")
                res_visual, error_visual = buscar_por_similitud_visual(
                    bytes_consulta, familia=familia_filtro,
                    progreso=lambda i, t: barra_v.progress(min(i / max(t, 1), 1.0),
                                                           text=f"Comparando {i} de {t} fotos...")
                )
                barra_v.empty()
                st.session_state["resultado_visual"] = (res_visual, error_visual)

            res_visual, error_visual = st.session_state.get("resultado_visual", (None, None))
            if error_visual:
                st.info(error_visual)
            elif res_visual:
                st.warning(
                    f"⚠️ {len(res_visual)} candidato(s) ordenados de más a menos parecido. "
                    "NINGUNO está confirmado: hay repuestos que de foto son idénticos y no son "
                    "intercambiables (cambia el paso de rosca, la altura, el lado). "
                    "Verificá por código o comparando la pieza en la mano antes de vender."
                )
                filas_visual = []
                for r in res_visual:
                    filas_visual.append({
                        "Código": r["Codigo"], "Descripción": r["Descripcion"], "Marca": r["Marca"],
                        "Confianza": nivel_de_parecido(r), "Parecido": f"{r['Parecido']:.0f}",
                        "Detalles que coinciden": r["Coincidencias"],
                        "Precio": r["Precio"], "Stock": r["Stock"],
                    })
                st.dataframe(filas_visual, width="stretch", hide_index=True)
                explicar(
                    "Mirá sobre todo «Detalles que coinciden»: es el número que más dice.",
                    "Son los puntos de la pieza que además dieron geométricamente coherentes entre las "
                    "dos fotos. Muchos detalles y parecido alto = vale la pena "
                    "revisarla. Si el que buscabas no aparece, cargale a ese producto una segunda foto del "
                    "ángulo que usás vos y la próxima vez lo encuentra.", en_expander=True
                )

            # ---- Paso 3: preguntarle a internet ----
            # Va último a propósito, y es el que más falta hacía. Los dos pasos de arriba
            # dependen de algo que puede no estar: el código tiene que llegar a leerse, y la
            # comparación necesita que ALGUIEN haya cargado antes una foto de esa misma pieza.
            # Con el catálogo sin fotos, el paso 2 no puede encontrar nada nunca — y así está
            # una base recién armada.
            if bytes_consulta is not None:
                st.markdown("---")
                st.markdown("**Paso 3 — preguntarle a internet** (si no se pudo leer el código "
                            "ni hay foto para comparar)")
                explicar(
                    "Busca la pieza en internet a partir de la foto y después cruza lo que "
                    "encuentra contra TU catálogo.",
                    "Sale a buscar afuera —catálogos, tiendas, foros— por la forma, el material, "
                    "la cantidad de vías de la ficha, los caños, los dientes, los logos "
                    "parciales. Vuelve con qué pieza es, para qué autos, y con qué números se "
                    "vende, y te muestra las páginas que usó para que puedas chequearlo.\n\n"
                    "**Lo importante es qué se hace con esa respuesta.** Una IA inventa números "
                    "de pieza con total seguridad, y por el texto no hay forma de distinguir uno "
                    "inventado de uno real. Por los datos sí: como respuesta solo se muestran "
                    "los códigos que **están en tu catálogo** — si está cargado, alguien lo "
                    "vende. Los que no están van aparte, marcados como pista para chequear, "
                    "nunca mezclados con lo que tenés.\n\n"
                    "Sigue sin ser una confirmación. Es el punto de partida para buscar, no el "
                    "número para facturar.", en_expander=True
                )
                _pista = st.text_input(
                    "¿Sabés algo de la pieza? (opcional, pero ayuda mucho)",
                    placeholder="Ej: es de un Gol 1.6 nafta, va arriba del motor",
                    key="pista_internet",
                    help="Sin esto la IA tiene que adivinar también de qué auto es, que es la "
                         "mitad del problema."
                )
                if st.button("🌐 Buscar esta pieza en internet", key="btn_internet"):
                    with st.spinner("Buscando en internet..."):
                        _d_net, _e_net = identificar_pieza_por_internet(bytes_consulta, _pista)
                    st.session_state["net_visual"] = (_d_net, _e_net)

                _d_net, _e_net = st.session_state.get("net_visual", (None, None))
                if _e_net:
                    st.info(_e_net)
                elif _d_net:
                    _conf = str(_d_net.get("confianza") or "s/d").lower()
                    _icono = {"alta": "🟢", "media": "🟡", "baja": "🟠"}.get(_conf, "⚪")
                    st.markdown(f"**{_icono} La IA dice que es: "
                                f"{_d_net.get('tipo_pieza') or 'no lo pudo determinar'}** "
                                f"(confianza {_conf})")
                    if _d_net.get("descripcion"):
                        st.caption(_d_net["descripcion"])
                    if _d_net.get("por_que"):
                        st.caption(f"Por qué: {_d_net['por_que']}")
                    if _d_net.get("autos"):
                        st.caption("Autos: " + ", ".join(str(a) for a in _d_net["autos"][:8]))

                    _cruce = cruzar_con_el_catalogo_lo_de_internet(_d_net, familia=familia_filtro)

                    if _cruce["exactos"]:
                        st.success(
                            f"✅ **{len(_cruce['exactos'])} de esos números están en tu "
                            "catálogo.** Son códigos cargados, no una suposición de la IA — "
                            "pero que el número exista no prueba que sea ESTA pieza: "
                            "comparala en la mano antes de vender."
                        )
                        st.dataframe(quitar_id(_cruce["exactos"]), width="stretch", hide_index=True)
                    if _cruce["por_tipeo"]:
                        st.warning(
                            "🟡 Estos no están escritos igual, pero tenés códigos casi idénticos. "
                            "Suele ser el mismo número con los espacios puestos distinto "
                            "(«0 280 155 786» y «0280155786») o un dígito de diferencia:"
                        )
                        st.dataframe(
                            [{"Lo que dijo internet": x.get("_pedido", ""), "Código que tenés": x["Codigo"],
                              "Marca": x["Marca"], "Descripción": x["Descripcion"],
                              "Precio": x["Precio"], "Stock": x["Stock"]}
                             for x in _cruce["por_tipeo"]],
                            width="stretch", hide_index=True
                        )
                    if _cruce["por_texto"]:
                        st.info(
                            "Ningún código pegó, así que busqué en tu catálogo por la "
                            "descripción. Esto es lo más flojo de la pantalla — coincide el tipo "
                            "de pieza y el auto, nada más:"
                        )
                        st.dataframe(quitar_id(_cruce["por_texto"]), width="stretch", hide_index=True)
                    if not any((_cruce["exactos"], _cruce["por_tipeo"], _cruce["por_texto"])):
                        st.warning(
                            "No encontré nada tuyo que se corresponda. Si la identificación de "
                            "arriba te cierra, es una pieza que no tenés cargada."
                        )
                    if _cruce["no_los_tenes"]:
                        st.caption(
                            "**No los tenés cargados** (pista para pedirle al proveedor, sin "
                            "verificar): " + ", ".join(f"`{x}`" for x in _cruce["no_los_tenes"][:15])
                        )
                    if _d_net.get("fuentes"):
                        # seccion_plegable y no st.expander: todo esto ya vive adentro de uno,
                        # y Streamlit corta el renderizado si se anidan. Ver seccion_plegable().
                        if seccion_plegable(f"🔗 Las {len(_d_net['fuentes'])} página(s) que consultó",
                                            key="fuentes_internet"):
                            if _d_net.get("consultas"):
                                st.caption("Buscó: " + " · ".join(_d_net["consultas"][:6]))
                            for _f in _d_net["fuentes"][:12]:
                                st.markdown(f"- [{_f['titulo']}]({_f['url']})")
                    else:
                        st.caption("⚠️ No devolvió ninguna página de respaldo, así que esta "
                                    "identificación no se puede verificar. Tomala con pinzas.")

    def _ver_toda_la_cadena():
        """«Mostrarlas»: la misma búsqueda otra vez, con «Toda la cadena» (ver más abajo)."""
        st.session_state["saltos_busqueda"] = "Toda la cadena"
        st.session_state["_buscar_codigo_ya"] = True

    # UN SOLO BUSCADOR. Lo que se escribe en el de códigos y son solo palabras —«filtro aceite
    # gol», «rótula»— se busca por descripción, sin hacer cambiar de modo a nadie (ver
    # parece_una_descripcion()). El cambio se pide en una vuelta y se hace en la siguiente,
    # ANTES de dibujar el selector: Streamlit no deja cambiar un widget ya dibujado.
    _a_codigo = st.session_state.pop("_pasar_a_codigo", None)
    if _a_codigo:
        st.session_state["modo_busqueda"] = "Código"
        st.session_state["busqueda_input"] = _a_codigo
        st.session_state["_buscar_codigo_ya"] = True
    _a_descripcion = st.session_state.pop("_pasar_a_descripcion", None)
    if _a_descripcion:
        st.session_state["modo_busqueda"] = "Descripción"
        st.session_state["texto_input"] = _a_descripcion
        st.session_state["_buscar_texto_ya"] = True
    modo = st.radio("Buscar por:", ["Código", "Descripción"], horizontal=True, key="modo_busqueda")

    c.execute("SELECT nombre FROM marcas ORDER BY nombre")
    lista_marcas = ["Todas"] + [r["nombre"] for r in c.fetchall()]

    if modo == "Código":
        # EL CÓDIGO Y EL BOTÓN ARRIBA, LAS OPCIONES PLEGADAS. En el celular el formulario ocupaba
        # la pantalla entera —filtro de marca, tres opciones de distancia apiladas y una
        # casilla— y el resultado quedaba abajo de todo. Las opciones se tocan poco; el título
        # del desplegable dice cuáles están puestas, así un filtro elegido nunca queda escondido.
        opciones_saltos = OPCIONES_DE_SALTOS
        # Una marca que se borró o se fusionó no puede quedar elegida: el selector se rompería.
        if st.session_state.get("marca_filtro_busqueda") not in (None, *lista_marcas):
            st.session_state.pop("marca_filtro_busqueda", None)
        _marca_elegida = st.session_state.get("marca_filtro_busqueda", "Todas")
        _saltos_elegidos = st.session_state.get("saltos_busqueda", "Hasta 3 saltos (recomendado)")
        _resumen_opciones = " · ".join(
            ["todas las marcas" if _marca_elegida in (None, "Todas") else f"solo {_marca_elegida}",
             {1: "solo directos", 3: "hasta 3 saltos", None: "toda la cadena"}.get(
                 opciones_saltos.get(_saltos_elegidos, 3), "hasta 3 saltos")]
            + (["sin vínculos flojos"] if st.session_state.get("solo_confiables") else []))
        with st.form("form_buscar_codigo"):
            busqueda = st.text_input(
                "Código, marca o descripción (varios códigos, separados por coma):",
                placeholder="Ej: W712/94, 036115561G...",
                key="busqueda_input",
                help="Con un código busca sus equivalencias. Si escribís palabras —«filtro "
                     "aceite gol», «mannol»— busca en las descripciones y en las marcas."
            )
            buscar_click = st.form_submit_button("🔍 Buscar Equivalencias", type="primary",
                                                 width="stretch")
            with st.expander(f"⚙️ Opciones: {_resumen_opciones}"):
                marca_filtro = st.selectbox("Filtrar por marca:", lista_marcas,
                                            key="marca_filtro_busqueda")
                # La búsqueda encadena: el código buscado trae sus equivalentes, y los
                # equivalentes de esos, y así. Cuanto más larga la cadena, más chances de que
                # un eslabón esté mal y aparezcan cosas que no entran. Este control la corta.
                # Sin index=: el valor de arranque va en la sesión, porque «Mostrarlas» (ver
                # _ver_toda_la_cadena()) lo cambia desde ahí, y Streamlit no quiere las dos.
                st.session_state.setdefault("saltos_busqueda", "Hasta 3 saltos (recomendado)")
                etiqueta_saltos = st.radio(
                    "Qué tan lejos buscar:", list(opciones_saltos.keys()),
                    horizontal=True, key="saltos_busqueda",
                    help="«Directo» es lo que alguna lista puso en la misma fila que tu código. "
                         "Cada salto más se apoya en el vínculo anterior: si uno está mal "
                         "cargado, todo lo que cuelga de ahí también."
                )
                # Cortar por saltos y cortar por confianza son dos cosas distintas: la primera
                # mira cuán largo es el camino, la segunda cuánto vale. Un resultado a dos saltos
                # por vínculos sólidos es mejor que uno directo colgado de un vínculo malo.
                solo_confiables = st.checkbox(
                    "Esconder los que llegan por vínculos flojos", key="solo_confiables",
                    help="Deja fuera los resultados cuyo camino pasa por algún vínculo que el "
                         "análisis puntuó por debajo de 50 — códigos puente cortos o genéricos, "
                         "y los que cuelgan de un mismo código a media docena de productos. El "
                         "código que buscaste siempre se muestra."
                )
            max_saltos = opciones_saltos[etiqueta_saltos]

        # La búsqueda en sí (con sus efectos de una sola vez: guardar historial, contar
        # veces_buscado) se hace acá, solo cuando se tocó "Buscar". El resultado se guarda en
        # session_state y el DESPLIEGUE se hace más abajo, FUERA de este "if", para que los
        # botones de adentro (agregar a WhatsApp, favoritos, combos) sigan funcionando en los
        # reruns siguientes — si el despliegue dependiera de "buscar_click", cualquier otro botón
        # que se toque después haría que buscar_click vuelva a False y todo el bloque desaparezca
        # antes de que el click en el botón de adentro llegue a registrarse.
        # Y al revés: lo que vino del buscador de descripción porque era un código.
        buscar_click = buscar_click or st.session_state.pop("_buscar_codigo_ya", False)
        if buscar_click and parece_una_descripcion(busqueda):
            st.session_state["_pasar_a_descripcion"] = busqueda.strip()
            st.session_state.pop("ultima_busqueda_codigo", None)
            st.rerun()
        if buscar_click:
            # Sin sacar los repetidos, pegar "ABC, abc" dibujaba dos veces los mismos widgets
            # con la misma key —todas se arman con el código limpio— y Streamlit corta la app
            # entera con "multiple widgets with the same key". Y pegar una lista con un código
            # duplicado es lo más común del mundo.
            codigos_buscados, _ya_vistos = [], set()
            for _crudo in busqueda.split(","):
                _crudo = _crudo.strip()
                if not _crudo:
                    continue
                _clave_dedup = sanitizar(_crudo) or _crudo.upper()
                if _clave_dedup in _ya_vistos:
                    continue
                _ya_vistos.add(_clave_dedup)
                codigos_buscados.append(_crudo)
            if not codigos_buscados:
                st.info("Ingresá al menos un código válido para buscar.")
                st.session_state.pop("ultima_busqueda_codigo", None)
            else:
                guardar_busqueda(busqueda.strip())
                resultados_guardados = []
                for codigo_individual in codigos_buscados:
                    clean = sanitizar(codigo_individual)
                    if not clean:
                        resultados_guardados.append(
                            {"codigo_individual": codigo_individual, "clean": None, "res": None}
                        )
                        continue
                    # Si la búsqueda FALLA no es «no hay»: se dice distinto, con el código
                    # para encontrarla en Estado y papelera, y no se anota como algo que falta
                    # (lo señaló una revisión con ChatGPT). Antes un fallo cortaba la pantalla
                    # entera con el error técnico. Ver anotar_busqueda().
                    _t_busqueda = time.perf_counter()
                    res, aviso_cero = [], None
                    try:
                        res, aviso_cero = buscar_con_variantes_del_cero(
                            clean, marca_filtro, max_saltos,
                            confianza_minima=50 if solo_confiables else None)
                    except sqlite3.Error as _err_busqueda:
                        anotar_error("buscador", _err_busqueda)
                        resultados_guardados.append(
                            {"codigo_individual": codigo_individual, "clean": clean,
                             "res": None, "error": anotar_busqueda(
                                 "código", codigo_individual,
                                 time.perf_counter() - _t_busqueda, 0, _err_busqueda)})
                        continue
                    anotar_busqueda("código", codigo_individual, time.perf_counter() - _t_busqueda,
                                    len(res or []))
                    # Si se llegó por la variante del cero o por el código de barras, lo que
                    # sigue (autos, «hay más», contador) va con el código que se encontró: con
                    # el tipeado no encontraban nada.
                    _buscada = next((f for f in res or []
                                     if f.get("Cadena") == "— el buscado"), None)
                    if _buscada and sanitizar(_buscada["Codigo"]):
                        clean = sanitizar(_buscada["Codigo"])
                    if res:
                        incrementar_veces_buscado(clean)
                    elif not existe_el_codigo(clean) and not marcas_que_nombra(clean):
                        # Sin resultado porque el filtro de marca lo dejó afuera no es «no lo
                        # tenemos»: no va a la lista de lo que conviene pedir. Tampoco el
                        # nombre de una de las listas escrito en el buscador de códigos.
                        registrar_busqueda_sin_resultado(codigo_individual)
                    resultados_guardados.append(
                        {"codigo_individual": codigo_individual, "clean": clean, "res": res,
                         "aviso": aviso_cero}
                    )
                st.session_state["ultima_busqueda_codigo"] = resultados_guardados

        if st.session_state.get("ultima_busqueda_codigo"):
            catalogos = listar_catalogos_externos()
            total_codigos_buscados = len(st.session_state["ultima_busqueda_codigo"])
            for item in st.session_state["ultima_busqueda_codigo"]:
                codigo_individual = item["codigo_individual"]
                clean = item["clean"]
                res = item["res"]
                if not clean:
                    st.warning(f"🔎 {codigo_individual} — código no válido, se omitió.")
                    continue
                if item.get("error"):
                    st.error(f"⚠️ **{codigo_individual}: no se pudo consultar** — no quiere decir "
                             "que no esté. La base estaba ocupada o algo falló: tocá «Buscar» "
                             f"de nuevo. Si se repite, avisá con este código: `{item['error']}`.")
                    continue

                # EL KIT QUE APARECE ENTRE LOS RESULTADOS. Que esté en la tabla está
                # bien —el que atiende quiere verlo, es la venta más grande— pero la
                # tabla es la de equivalencias, o sea «esto lo podés vender en lugar de
                # lo que pediste», y un kit NO se puede vender en lugar de la pieza
                # suelta: trae otras cosas y cuesta otra plata. Al revés tampoco.
                # Así que se muestran, y se dice en la misma fila qué son. Se contesta
                # con los dos textos y nada más (ver _uno_trae_al_otro), sin una sola
                # consulta de más.
                marcar_lo_que_no_es_lo_mismo(res)

                # CUÁNTAS DE LAS COINCIDENCIAS SON DE VERDAD OTRO REPUESTO.
                # No es lo mismo "2 coincidencias" que "el que buscaste y su propio código de
                # fábrica". Antes se contaba todo junto y el cartel verde decía que había
                # encontrado algo cuando no había encontrado nada: en la base real le pasa a
                # 12.060 productos (el 20% del catálogo). Eso es lo que desde el mostrador se
                # ve como «no me hace las equivalencias».
                # Cuenta como alternativa de verdad lo que se puede vender en lugar del
                # buscado: otro producto, de otro proveedor. Los códigos de fábrica que no
                # cuelgan nada más (_sin_salida) no cuentan, y el buscado tampoco.
                # LOS CÓDIGOS DE FÁBRICA NO SON UN REPUESTO QUE SE VENDA. Sirven para unir las
                # listas de los proveedores y para buscar —el que pide «0001108033» encuentra el
                # arranque de LUCAS—, pero en la tabla eran ruido: un arranque que cita 53 números
                # de Bosch salía con 53 filas de «MOTOR DE ARRANQUE…» y «sin equivalencias».
                # Se esconden, salvo el que se buscó, y se pueden mostrar con una casilla.
                def _es_de_fabrica(f):
                    return f.get("Tipo") == "OEM" and f.get("Cadena") != "— el buscado"
                _de_fabrica = [f for f in res if _es_de_fabrica(f)]
                alternativas = [f for f in res
                                if f.get("Cadena") != "— el buscado" and not f.get("_sin_salida")
                                and not f.get("_complementario") and not _es_de_fabrica(f)]
                if not res and marcas_que_nombra(clean):
                    etiqueta_resultado = f"🏷️ {codigo_individual} — es una de tus listas"
                elif not res:
                    etiqueta_resultado = f"🔎 {codigo_individual} — sin resultados"
                elif alternativas:
                    etiqueta_resultado = (f"🔎 {codigo_individual} — {len(alternativas)} "
                                          f"equivalencia" + ("s" if len(alternativas) != 1 else ""))
                else:
                    etiqueta_resultado = f"🔎 {codigo_individual} — sin equivalencias todavía"

                with st.expander(etiqueta_resultado, expanded=(total_codigos_buscados == 1)):
                    if item.get("aviso"):
                        st.warning(item["aviso"])
                    # Una patente escrita en el buscador. Pasa: el cliente la dice y el que
                    # atiende la escribe donde está el cursor. En vez de «sin resultados», que
                    # es cierto pero no ayuda, se dice qué es y dónde se usa.
                    _pat_en_buscador = leer_patente(codigo_individual)
                    if not res and _pat_en_buscador["formato"]:
                        _d_b, _h_b, _ = anio_probable_de_patente(codigo_individual)
                        st.info(
                            f"🪪 Eso es una **patente argentina** ({_pat_en_buscador['detalle']})"
                            + (f", de **{_pat_en_buscador['provincia']}**"
                               if _pat_en_buscador["provincia"] else "")
                            + (f", patentada entre **{_d_b} y {_h_b}**." if _d_b and _h_b
                               else ".")
                            + "\n\nLas patentes se buscan en **🛠️ Modo Mecánico → 🔤 Por "
                              "patente**: si el auto está cargado, de ahí salen los repuestos "
                              "que le entran. Y si no está, se carga con una foto de la cédula."
                        )
                    # El mismo número en dos piezas distintas. Ver el_mismo_numero_en_dos_piezas().
                    _choque = el_mismo_numero_en_dos_piezas(res)
                    if _choque:
                        st.warning(
                            f"⚠️ **Hay {len(_choque)} productos con el código "
                            f"{codigo_individual}, y no son la misma pieza.** Es casualidad: "
                            "cada proveedor numera su catálogo de corrido y tarde o temprano "
                            "coinciden. Mirá la marca de cada fila.\n\n"
                            + "\n\n".join(f"· **{f['Marca']}** — {(f.get('Descripcion') or '')[:70]}"
                                            for f in _choque[:4])
                        )
                    if res:
                        if alternativas:
                            # Antes decía «1 equivalencia, sobre 10 filas en total» y se veían
                            # dos: las otras ocho eran códigos de fábrica, que no se muestran.
                            # Un renglón y no una caja verde: la caja ocupaba lo mismo que tres
                            # filas de la tabla, y la tabla es la respuesta.
                            _marcas_alt = sorted({f["Marca"] for f in alternativas})
                            st.markdown(
                                f"✅ :green[**{len(alternativas)} equivalencia(s)**"
                                + (f" en {len(_marcas_alt)} marca(s):] "
                                   f"{texto_para_markdown(', '.join(_marcas_alt[:6]))}"
                                   + ("…" if len(_marcas_alt) > 6 else "")
                                   if _marcas_alt else "]"))
                        else:
                            # Decirlo con todas las letras, y decir además qué hacer. Sin esto
                            # la pantalla mostraba dos filas y un tilde verde, y había que
                            # mirar la columna «Cadena» para darse cuenta de que la segunda
                            # fila era el mismo repuesto.
                            st.warning(
                                "🔗 **Este código todavía no tiene equivalencias con otra "
                                "marca.**"
                                + ((f" Cita {len(_de_fabrica)} código(s) de fábrica "
                                    f"(**{_de_fabrica[0]['Codigo']}**"
                                    + (", …" if len(_de_fabrica) > 1 else "")
                                    + "), pero por ahora ninguno está en la lista de otro "
                                    "proveedor.") if _de_fabrica else "")
                                + "\n\nSe puede cargar a mano desde **🔗 Vincular manual**, y "
                                "queda para siempre."
                            )

                        # Llegar al tope de 400 no es solo "hay muchos": según el criterio de la
                        # propia consulta, una red sana tiene entre 2 y 20 códigos. Cuatrocientos
                        # significa casi siempre que un código puente fusionó familias que no
                        # tienen relación. Truncar sin decirlo escondía justo esa señal.
                        if len(res) >= 400:
                            st.warning(
                                "⚠️ La lista se cortó en **400 resultados**. Una red sana tiene "
                                "entre 2 y 20 códigos: llegar a 400 casi siempre significa que "
                                "**un vínculo mal cargado unió familias que no tienen que ver**. "
                                "Conviene revisarlo con «Revisar la calidad de estos resultados» "
                                "acá abajo, o bajar el límite a «Solo los directos»."
                            )

                        # ¿Quedó algo afuera por el límite de saltos? El corte es sano —cuanto
                        # más larga la cadena, más chance de que un eslabón esté mal— pero cortar
                        # EN SILENCIO es lo que hace pensar que la app no relaciona proveedores:
                        # cada lista cita sus propios códigos de fábrica, esos se encadenan, y con
                        # 3 saltos se ve el proveedor propio y uno más. El resto existe y no se
                        # muestra. Así que se avisa y se ofrece verlo.
                        _mas, _marcas_mas = equivalentes_mas_alla_del_tope(
                            clean, max_saltos, marca_filtro,
                            50 if solo_confiables else None)
                        if _mas:
                            _de_quien = (" de " + ", ".join(_marcas_mas[:4])
                                          + (" y otras" if len(_marcas_mas) > 4 else "")
                                          ) if _marcas_mas else ""
                            # Un renglón y un botón, no un recuadro: era media pantalla del
                            # celular entre el «✅ N equivalencias» y las tarjetas.
                            _c_mas, _b_mas = st.columns([3, 1.3])
                            _c_mas.caption(f"🔗 Hay **{_mas} más**{_de_quien}, más lejos en la "
                                           "cadena.")
                            _b_mas.button("Mostrarlas", key=f"toda_la_cadena_{clean}",
                                          on_click=_ver_toda_la_cadena)

                        # LA TABLA VA PRIMERO. Se le guarda el lugar acá y se dibuja más abajo,
                        # después de los filtros que deciden qué muestra: los filtros quedan
                        # debajo de ella. Antes iban arriba, y con el resumen y las casillas la
                        # tabla —que es la respuesta— empezaba fuera de la pantalla.
                        _lugar_de_la_tabla = st.container()
                        _filtro1, _filtro2, _filtro3 = st.columns(3)
                        if _de_fabrica and not _filtro3.checkbox(
                                f"🏭 Mostrar los {len(_de_fabrica)} código(s) de fábrica",
                                key=f"ver_fabrica_{clean}",
                                help="Relacionan los productos entre sí y se pueden buscar, pero "
                                     "no son un repuesto que vendas."):
                            res = [f for f in res if not _es_de_fabrica(f)]

                        # Filtro de stock: un botón que ahorra scroll en cada consulta. Va
                        # antes de la tabla porque decide QUÉ se muestra, no cómo.
                        # Solo si filtra algo: con ninguno en stock —la mayoría de las listas
                        # no traen stock— o con todos, la casilla no cambia nada.
                        _n_con_stock = sum(1 for f in res if (f.get('Stock') or 0) > 0)
                        solo_stock = (0 < _n_con_stock < len(res)) and _filtro2.checkbox(
                            f"📦 Solo con stock ({_n_con_stock} de {len(res)})",
                            key=f"solo_stock_{clean}")
                        if solo_stock:
                            con_stock = [f for f in res if (f.get("Stock") or 0) > 0]
                            if con_stock:
                                res = con_stock
                            else:
                                # Antes se volvía a la lista completa sin decir nada: se tildaba
                                # "solo con stock" y aparecían igual los que no tienen, así que
                                # parecía que el filtro estaba roto.
                                st.info("Ninguno de estos tiene stock. Se muestran todos.")

                        # Copiar el código para pegarlo en facturación o WhatsApp. st.code trae
                        # el botón de copiar incorporado, así que no hace falta JavaScript.
                        if _filtro1.checkbox("📋 Códigos para copiar", key=f"copiar_{clean}"):
                            st.code("\n".join(f["Codigo"] for f in res), language=None)

                        # Stock libre = lo que hay menos lo apartado en presupuestos. Es el
                        # número que importa al prometerle algo a un cliente; el stock a secas
                        # puede estar comprometido con otro que ya lo cotizó.
                        #
                        # Va en una columna aparte y NUMÉRICA, y se calcula al dibujar. Antes se
                        # escribía "3 (de 4, el resto apartado)" encima de Stock, y estos
                        # diccionarios son los mismos que quedan guardados en session_state: al
                        # refresco siguiente Stock ya era un texto, el filtro de arriba hacía
                        # texto > 0 y la pantalla se cerraba con TypeError. Con una sola reserva
                        # activa alcanzaba con tocar cualquier botón, y el texto además se
                        # anidaba en cada vuelta: "3 (de 3 (de 4, el resto apartado)...".
                        try:
                            libres = stock_libre_de_varios([f["ID"] for f in res])
                        except Exception as _err:
                            anotar_error("stock libre de los resultados", _err)
                            libres = {}
                        hay_reservas = any(f["ID"] in libres
                                            and libres[f["ID"]] != (f.get("Stock") or 0)
                                            for f in res)
                        if hay_reservas:
                            st.caption("**Libre** es lo que queda sin apartar: es el número que "
                                       "se le puede prometer a un cliente.")

                        # El margen es información sensible: la ve el dueño y el administrador,
                        # no cualquiera que atienda el mostrador.
                        if es_admin():
                            # Sin los kits: comparar el margen de un kit contra el de la
                            # pieza suelta es comparar dos ventas distintas.
                            mejor_marg = mejor_margen_entre_equivalentes(
                                [f for f in res if not f.get("_complementario")])
                            agregar_margen(res)
                            if mejor_marg:
                                st.info(
                                    f"💰 **Mejor margen entre los que tenés en stock:** "
                                    f"{mejor_marg['marca']} {mejor_marg['codigo']} — te deja "
                                    f"${miles(mejor_marg['ganancia'], 0)} "
                                    f"(${miles(mejor_marg['diferencia'], 0)} más que el peor de la lista)."
                                )
                        puentes_res = puentes_en_el_resultado([f["ID"] for f in res])

                        # comparar precios a ojo cuando hay varias marcas equivalentes.
                        # El kit queda afuera de la comparación: casi siempre sale más caro que
                        # la pieza suelta, y coronarlo «el más barato» sería comparar dos cosas
                        # distintas. Al revés, la pieza suelta adentro de un kit tampoco.
                        # Ni la marca con la lista en otra escala: ver escala_de_precios_por_marca().
                        _fuera_escala = marcas_con_precios_fuera_de_escala()
                        candidatos_precio = [f for f in res
                                             if f.get("Precio") and (f.get("Stock") or 0) > 0
                                             and not f.get("_complementario")
                                             and f.get("Marca") not in _fuera_escala]
                        id_mas_barato = min(candidatos_precio, key=lambda f: f["Precio"])["ID"] if candidatos_precio else None
                        for f in res:
                            f["💰"] = "🏆 Más barato en stock" if f["ID"] == id_mas_barato else ""

                        # Acá se arma lo que se ve, SIN tocar las filas guardadas. Dos motivos,
                        # los dos aprendidos a los golpes:
                        #  · las claves con guión bajo son internas —el costo entre ellas— y no
                        #    salen ni a pantalla ni al Excel. Antes el costo se borraba de la
                        #    fila, y como la fila se reusa en el refresco siguiente, el margen
                        #    del administrador se veía una vez y después quedaba vacío;
                        #  · "Libre" se recalcula en cada vuelta. Si se escribiera en la fila, al
                        #    soltar la reserva la columna quedaría pegada con el número viejo
                        #    para siempre, porque nadie la vuelve a tocar.
                        mostrar = []
                        for f in res:
                            visible = {k: v for k, v in f.items() if not k.startswith("_")}
                            if hay_reservas:
                                visible["Libre"] = libres.get(f["ID"], f.get("Stock") or 0)
                            mostrar.append(visible)
                        mostrar = para_mostrar(quitar_id(mostrar))
                        # En el celular, tarjetas; la tabla queda a un toque. Ver
                        # mostrar_tarjetas_de_resultados(). En el lugar guardado arriba.
                        with _lugar_de_la_tabla:
                            if es_celular() and not st.toggle("📋 Ver como tabla",
                                                               key=f"como_tabla_{clean}"):
                                mostrar_tarjetas_de_resultados(mostrar)
                            else:
                                st.dataframe(
                                    mostrar, width="stretch", hide_index=True,
                                    column_order=columnas_que_dicen_algo(mostrar),
                                    column_config=CONFIG_COLUMNAS_RESULTADO,
                                )
                            # Debajo de los precios, que es donde se mira antes de cotizar.
                            _fuera_aca = sorted({f.get("Marca") for f in res
                                                 if f.get("Precio")} & _fuera_escala)
                            if _fuera_aca:
                                st.warning(
                                    f"⚠️ Los precios de **{', '.join(_fuera_aca)}** están en "
                                    "otra escala que los de las demás marcas (unas "
                                    + ", ".join(
                                        f"{miles(1 / escala_de_precios_por_marca()[_m]['factor'], 0)}"
                                        f" veces {'menos' if escala_de_precios_por_marca()[_m]['factor'] < 1 else 'más'}"
                                        for _m in _fuera_aca)
                                    + "): revisalos antes de cotizar. Se corrige con el "
                                    "coeficiente de la lista, en "
                                    f"{miga_hasta('Marcas')} → 📏 Coeficiente de la lista.")

                        # La pregunta que sigue siempre a «¿lo tenés?»: ¿le sirve al auto del
                        # cliente? La app tiene el dato en los catálogos de fabricante y no lo
                        # usaba acá. Contestar mal esto es lo más caro del mostrador: la pieza
                        # vuelve, y con ella se va la confianza.
                        autos_cod = autos_de_un_codigo(clean)
                        if autos_cod:
                            if seccion_plegable(
                                    f"🚗 ¿Le sirve a qué autos? ({len(autos_cod)} aplicaciones)",
                                    key=f"aplic_{clean}"):
                                cver1, cver2, cver3 = st.columns([2, 2, 1])
                                marca_ver = cver1.text_input("Marca del auto:",
                                                              key=f"ver_marca_{clean}",
                                                              placeholder="Ej: FORD").strip()
                                modelo_ver = cver2.text_input("Modelo:", key=f"ver_modelo_{clean}",
                                                               placeholder="Ej: FIESTA").strip()
                                anio_ver = cver3.number_input("Año:", min_value=0, max_value=2100,
                                                               value=0, step=1,
                                                               key=f"ver_anio_{clean}")
                                if marca_ver:
                                    sirve, motivo = le_sirve_a_este_auto(
                                        clean, marca_ver, modelo_ver, anio_ver or None)
                                    if sirve is True:
                                        st.success(f"✅ **Sí le sirve.** {motivo}")
                                    elif sirve is False:
                                        st.error(f"❌ **No según el catálogo.** {motivo}")
                                    else:
                                        st.info(motivo)
                                st.caption("Todos los autos para los que el fabricante da este código:")
                                st.dataframe(autos_cod, width="stretch", hide_index=True)

                        # Los avisos de calidad van DESPUÉS de la tabla, y agrupados en un solo
                        # desplegable. Antes iban arriba: dos alertas rojas y el explorador de
                        # caminos empujaban el resultado —que es a lo que uno vino— abajo de todo.
                        # La advertencia sigue estando, pero deja de tapar la respuesta.
                        _hay_indirectos = any(
                            f.get("Cadena", "").startswith(("🟡", "🔴")) for f in res)
                        # Sin ninguna equivalencia de otra marca, el «código puente» no arrastró
                        # nada: lo que cuelga son sus propios códigos de fábrica. El cartel rojo
                        # salía igual, abierto, abajo de «todavía no tiene equivalencias», y
                        # se contradecían (pasó con LRSC030140LUCAS, que cita 52 de Bosch).
                        if not alternativas:
                            puentes_res = []
                        if puentes_res or _hay_indirectos:
                            if seccion_plegable(
                                "⚠️ Revisar la calidad de estos resultados" if puentes_res
                                else "🧭 ¿Por qué apareció alguno de estos?",
                                key=f"calidad_{clean}", abierto=bool(puentes_res)
                            ):
                                # Aviso de contaminación. Va acá y no solo en Mantenimiento porque es
                                # justo en el momento de vender cuando importa saber que estos resultados
                                # pueden no ser reales.
                                # De qué lista salió cada vínculo directo. Se agrega solo si alguna
                                # importación dejó rastro; las equivalencias viejas no lo tienen.
                                id_buscado = next((f["ID"] for f in res if sanitizar(f["Codigo"]) == clean), None)
                                if id_buscado:
                                    origenes = origenes_de_los_vinculos_directos(
                                        id_buscado, [f["ID"] for f in res]
                                    )
                                    if origenes:
                                        for f in res:
                                            lote_f = origenes.get(f["ID"])
                                            f["Vino de"] = lote_f.split(" · ")[0] if lote_f else ""

                                # Además del código puente clásico: el vínculo suelto que está uniendo
                                # dos familias enteras. No lo detecta ningún otro control, porque no hay
                                # ningún código con muchos enlaces — es un solo eslabón mal puesto.
                                if id_buscado and len(res) >= 8:
                                    try:
                                        uniones = vinculos_que_unen_familias(id_buscado)
                                    except Exception as _err:
                                        anotar_error("nivel principal", _err)
                                        uniones = []
                                    if uniones and uniones[0]["Confianza del vínculo"] < 50:
                                        u = uniones[0]
                                        st.error(
                                            f"🔗 **Un solo vínculo está uniendo dos grupos de repuestos.** "
                                            f"«{u['Código A']}» ({u['Marca A']}) ↔ «{u['Código B']}» "
                                            f"({u['Marca B']}) separa {u['Separa']}, y su confianza es "
                                            f"{u['Confianza del vínculo']}/100.\n\n"
                                            "Cortando **ese solo vínculo** se separan las dos familias. "
                                            f"Está en **{miga_hasta('Vínculos que unen dos familias de repuestos')}**."
                                        )
                                if puentes_res:
                                    nombres = ", ".join(f"«{p['Código']}» ({p['Vínculos']} vínculos)"
                                                         for p in puentes_res[:3])
                                    st.error(
                                        f"🌉 **Ojo: estos resultados pasan por un código puente.** {nombres} "
                                        "está vinculado a demasiadas cosas, así que arrastra acá repuestos "
                                        "de otros rubros que no tienen nada que ver. Fijate la columna "
                                        "**Cadena**: lo marcado como 🟢 directo es lo confiable. "
                                        f"Para arreglarlo de raíz: **{miga_hasta('Códigos puente')}**."
                                    )

                                # ¿Por qué apareció este resultado? Muestra la cadena de vínculos que lo
                                # trajo, con el puntaje y la lista de origen de cada paso. Es lo que
                                # convierte "el camino es débil" en algo accionable: se ve cuál cortar.
                                # Sin expander anidado: Streamlit no los admite y tira excepción.
                                # Como este bloque YA está dentro de uno, va como subtítulo.
                                indirectos = [f for f in res if f.get("Cadena", "").startswith(("🟡", "🔴"))]
                                if id_buscado and indirectos:
                                    if True:
                                        st.markdown("**🧭 ¿Por qué apareció alguno de estos?**")
                                        etiquetas_por_que = {
                                            f"{f['Codigo']} ({f['Marca']}) — {f['Cadena']}, {f['Confianza']}": f["ID"]
                                            for f in indirectos
                                        }
                                        # La key lleva el código de ESTA vuelta. Era fija, y el
                                        # bloque está adentro del bucle que recorre los códigos
                                        # buscados: pidiendo dos a la vez ("P-1, Q-1") y abriendo
                                        # esta sección en los dos, Streamlit encontraba la misma
                                        # key repetida y cerraba la app entera. Y buscar varios
                                        # separados por coma es lo que el campo invita a hacer.
                                        elegido_pq = st.selectbox("Elegí un resultado:",
                                                                   list(etiquetas_por_que.keys()),
                                                                   key=f"por_que_resultado_{clean}")
                                        camino = camino_entre(id_buscado, etiquetas_por_que[elegido_pq])
                                        if not camino:
                                            st.caption("No pude reconstruir el camino.")
                                        else:
                                            st.caption(
                                                "Se muestra el camino MÁS confiable de los que existen. "
                                                "El paso con menor puntaje es el que decide si este "
                                                "resultado sirve o no."
                                            )
                                            peor_paso = min(camino, key=lambda x: x["Confianza"])
                                            for paso in camino:
                                                marca_paso = ("🔴" if paso is peor_paso and paso["Confianza"] < 50
                                                               else "🟢" if paso["Confianza"] >= 70
                                                               else "🟡")
                                                st.markdown(f"{marca_paso} **{paso['Paso']}** — "
                                                             f"{paso['Confianza']}/100 · {paso['Vino de']}")
                                            if peor_paso["Confianza"] < 50:
                                                st.warning(
                                                    f"El eslabón flojo es **{peor_paso['Paso']}** "
                                                    f"({peor_paso['Confianza']}/100). Cortando ese, este "
                                                    "resultado deja de aparecer."
                                                )
                                                if candado('cortar vínculos', st.button("✂️ Cortar ese vínculo", key=f"cortar_paso_debil_{clean}"), 'cortar_v_nculos_4'):
                                                    borrar_equivalencias_dudosas(
                                                        [(peor_paso["_a"], peor_paso["_b"])])
                                                    invalidar_salud()
                                                    avisar("success", "Vínculo cortado.")
                                                    st.rerun()

                                # Marca la opción más barata ENTRE LAS QUE TIENEN STOCK, para no tener que

                        # LA FICHA DE PRUEBA de un resultado: quién declara cada paso, las
                        # medidas lado a lado, lo que la contradice y lo que falta para darla por
                        # verificada. Plegada: se calcula solo si se abre. Ver ficha_de_prueba().
                        _origenes_ficha = [f["ID"] for f in res
                                           if f.get("Cadena") == "— el buscado"]
                        _para_ficha = [f for f in res if f.get("Cadena") != "— el buscado"
                                       and not f.get("_sin_salida")]
                        if _origenes_ficha and _para_ficha and seccion_plegable(
                                "🧾 Ficha de prueba: ¿por qué es equivalente?",
                                key=f"ficha_prueba_{clean}"):
                            _opciones_ficha = {
                                f"{f['Codigo']} ({f['Marca']}) — {veredicto_de_la_equivalencia(f)}":
                                    f["ID"] for f in _para_ficha}
                            _elegido_ficha = st.selectbox("Elegí un resultado:",
                                                          list(_opciones_ficha),
                                                          key=f"ficha_resultado_{clean}")
                            _destino_ficha = _opciones_ficha[_elegido_ficha]
                            mostrar_ficha_de_prueba(
                                el_buscado_mas_cercano(_origenes_ficha, _destino_ficha),
                                _destino_ficha, clave=clean)

                        # Botones de link aparte, para no depender de scrollear la tabla al costado en el celular.
                        # La key incluye el código buscado (clean) además del ID: si se buscan varios códigos
                        # a la vez y dos están vinculados entre sí, el mismo producto puede aparecer en más de
                        # un resultado — sin el prefijo de clean, la key se repetiría y Streamlit tira error.
                        con_ficha = [f for f in res if f.get("Ficha")]
                        if con_ficha:
                            for f in con_ficha:
                                st.link_button(
                                    f"🔗 Ver {f['Codigo']} ({f['Marca']}) en el sitio del proveedor",
                                    f["Ficha"], key=f"link_ficha_{clean}_{f['ID']}"
                                )

                        # Combos: piezas que suelen cambiarse junto con lo que se encontró
                        combos_encontrados = {}
                        for f in res:
                            for disp, items in buscar_combos_para_descripcion(f.get("Descripcion", "")).items():
                                combos_encontrados.setdefault(disp, set()).update(items)
                        if combos_encontrados:
                            st.markdown("**💡 Suelen cambiarse junto con esto:**")
                            for disp, items_set in combos_encontrados.items():
                                items = sorted(items_set)
                                st.caption(f"Relacionado con: {disp}")
                                item_cols = st.columns(len(items))
                                for col_item, item in zip(item_cols, items):
                                    if col_item.button(f"🔍 {item}", key=f"combo_{clean}_{disp}_{item}"):
                                        res_item = buscar_por_texto(item)
                                        if res_item:
                                            con_stock = any((r.get("Stock") or 0) > 0 for r in res_item)
                                            if not con_stock:
                                                st.error(f"⚠️ Tenés '{item}' cargado pero SIN STOCK en ningún proveedor.")
                                            st.dataframe(quitar_id(res_item), width="stretch", hide_index=True)
                                        else:
                                            st.error(f"⚠️ No tenés '{item}' cargado en la base — vas a necesitar pedirlo.")

                        # Lo que va con esto: las otras piezas del mismo trabajo, para el mismo
                        # motor, sacadas del catálogo. Ver lo_que_va_con().
                        _buscado_prov = next((f for f in res if f.get("Cadena") == "— el buscado"
                                              and f.get("Tipo") != "OEM"), None)
                        # Antes de vender, preguntá: ver versiones_para_preguntar().
                        if _buscado_prov:
                            _preguntas = versiones_para_preguntar(_buscado_prov["ID"])
                            if _preguntas:
                                st.info(
                                    f"❓ **Antes de vender, preguntá.** {_buscado_prov['Marca']} "
                                    "tiene otras versiones de esta pieza para el mismo auto, y se "
                                    "distinguen por:\n\n" + "\n".join(
                                        f"- **{_que}:** " + " · ".join(
                                            f"{_valor} → {', '.join(_cods[:4])}"
                                            + (f" y {len(_cods) - 4} más" if len(_cods) > 4 else "")
                                            for _valor, _cods in _vals.items())
                                        for _que, _vals in _preguntas)
                                    + "\n\nMirá la pieza vieja o preguntale al cliente.")

                        # Con un interruptor y no una caja: esta ya está adentro de una, y así
                        # además no se busca nada hasta que alguien lo pide.
                        if _buscado_prov and st.toggle(
                                "🧩 ¿Qué más lleva este trabajo, para el mismo motor?",
                                key=f"mismo_trabajo_{clean}_{_buscado_prov['ID']}"):
                            _trabajo, _complementos = lo_que_va_con(_buscado_prov["ID"])
                            if not _complementos:
                                st.caption("No es una pieza con complementos cargados (junta de "
                                           "tapa de cilindros, bomba de agua, termostato, bobina, "
                                           "bujías), o el catálogo no tiene otra pieza que diga "
                                           "el mismo motor.")
                            else:
                                st.caption(f"Para {_trabajo}. Del catálogo, por lo que dice cada "
                                           "descripción: la misma marca de auto, el mismo "
                                           "combustible y el mismo motor o la misma cilindrada. "
                                           "Confirmalo con el cliente antes de sumarlo.")
                                for _nombre_c, _filas_c in _complementos:
                                    st.markdown(f"**{_nombre_c}**")
                                    st.dataframe(quitar_id(_filas_c), width="stretch",
                                                 hide_index=True)

                        # Autopartes de seguridad: las marcas de estos resultados que tienen
                        # CHAS. Solo lo que hay: «no figura» se mira en Administrar → Marcas
                        # (ver chas_en_los_resultados()).
                        _con_chas = chas_en_los_resultados(res)
                        if _con_chas:
                            st.caption("🛡️ Con CHAS vigente (autoparte de seguridad homologada): "
                                       + " · ".join(f"**{texto_para_html(_m)}**"
                                                    + (f" ({texto_para_html(', '.join(_d['autopartes'][:2]))})"
                                                       if _d["autopartes"] else "")
                                                    for _m, _d in _con_chas[:6]))

                        col_dl, col_add = st.columns(2)
                        with col_dl:
                            st.download_button(
                                "⬇️ Descargar (Excel)",
                                data=to_excel_bytes(mostrar),
                                file_name=f"equivalencias_{clean}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key=f"dl_{clean}"
                            )
                        with col_add:
                            if st.button("📋 Agregar a lista de WhatsApp", key=f"add_wa_{clean}"):
                                st.session_state.lista_whatsapp.append({
                                    "codigo_buscado": codigo_individual,
                                    "resultados": res
                                })
                                st.success("Agregado a la lista.")
                            # Un botón que lleva, en vez de «andá a la pestaña Lista WhatsApp»:
                            # el que está atendiendo no tiene que buscarla en el menú.
                            if st.session_state.lista_whatsapp:
                                st.button(f"📋 Ir a la lista ({len(st.session_state.lista_whatsapp)}) →",
                                          key=f"ir_wa_{clean}", on_click=ir_a_donde_dice_el_aviso,
                                          args=(PAGINAS[5],))

                        # Kits: la pregunta del mostrador es «¿y el kit con las bujías?».
                        # Sale de las descripciones de las propias listas — cuando el proveedor
                        # arma un kit escribe adentro los códigos de lo que trae — así que no
                        # hay nada que cargar a mano. Va antes de «se lo llevó» porque es una
                        # decisión de venta, no de registro.
                        # Los kits de los doce primeros salen de UNA consulta y no de doce:
                        # cada una es un LIKE que barre las 70.888 descripciones, y esto corre
                        # en cada búsqueda del mostrador. Ver kits_que_traen_a_varios().
                        _kits, _contenido = [], []
                        _kits_por_producto = kits_que_traen_a_varios([_f["ID"] for _f in res[:12]])
                        for _f in res[:12]:
                            for _k in _kits_por_producto.get(_f["ID"], []):
                                if _k["ID"] not in {x["ID"] for x in _kits}:
                                    _kits.append(_k)
                            for _d in que_trae_este_kit(_f["ID"]):
                                if _d["ID"] not in {x["ID"] for x in _contenido}:
                                    _contenido.append(_d)
                        if _kits:
                            st.markdown("**📦 También viene en kit — no es lo mismo, es además**")
                            st.caption(
                                "Estos kits del catálogo traen adentro alguno de los códigos de "
                                "arriba. **No son equivalentes**: no se puede mandar el kit en "
                                "lugar de la pieza suelta ni al revés —trae otras cosas y cuesta "
                                "otra plata—. Se muestran porque suele ser la venta más grande y "
                                "le ahorra al cliente volver por la otra pieza."
                            )
                            st.dataframe([{k: v for k, v in f.items() if not k.startswith("_")}
                                          for f in _kits], width="stretch", hide_index=True)
                        if _contenido:
                            st.markdown("**🧩 Lo que trae el kit por separado — tampoco es lo mismo**")
                            ayuda(
                                "Si el cliente no quiere el kit entero, estas son las piezas "
                                "sueltas que nombra la descripción. Cada una es **una parte** "
                                "del kit, no un reemplazo del kit."
                            )
                            st.dataframe([{k: v for k, v in f.items() if not k.startswith("_")}
                                          for f in _contenido], width="stretch", hide_index=True)

                        st.markdown("**🛒 ¿Se lo llevó? / 📌 ¿Falta stock?**")
                        ayuda(
                            "Marcá cuál se llevó el cliente: con eso el sistema va aprendiendo qué "
                            "sirve para qué, y después te propone equivalencias nuevas en "
                            "📊 Estadísticas → 🔗 Equivalencias sugeridas. Si falta stock, «📌 Reponer» lo "
                            "anota en 📊 Estadísticas → 📌 Para pedir. «📦 Pedir al depósito» "
                            "le avisa al depósito que lo busque, y al entregarlo queda en la cuenta "
                            "del que se lo lleva."
                        )
                        def _rotulo_stock(f):
                            _s = f.get("Stock")
                            return (f"{f['Marca']} - {f['Codigo']} "
                                    f"(stock: {_s if _s is not None else 's/d'})")
                        # Hasta cinco, un par de botones por resultado: es un toque. Con más, un
                        # selector y los dos botones una sola vez. Mirado en un celular de verdad,
                        # una búsqueda de 62 resultados dejaba 124 botones del ancho de la
                        # pantalla uno abajo del otro, y la página medía 17 pantallas.
                        # En el celular las columnas se apilan: cada fila eran dos botones a lo
                        # ancho, y con cinco resultados, diez botones. Ahí el selector va desde dos.
                        if len(res) <= (1 if es_celular() else 5):
                            for fila_stock in res:
                                colr1, colr2, colr3 = st.columns([3, 1, 1])
                                colr1.write(_rotulo_stock(fila_stock))
                                colr2.button("🛒 Se llevó", key=f"vendido_{fila_stock['ID']}_{clean}",
                                              on_click=anotar_venta_y_avisar,
                                              args=(fila_stock["ID"], codigo_individual,
                                                    f"{fila_stock['Marca']} - {fila_stock['Codigo']}",
                                                    f"stock_{clean}"),
                                              help="Anota la venta para ir descubriendo equivalencias solas")
                                colr3.button("📌 Reponer", key=f"pedir_repo_{fila_stock['ID']}_{clean}",
                                              on_click=pedir_reposicion_y_avisar,
                                              args=(fila_stock["ID"], f"{fila_stock['Marca']} - {fila_stock['Codigo']}",
                                                    f"stock_{clean}"),
                                              help="Marcar para reposición")
                        else:
                            # Se elige por ID y no por el rótulo: dos productos con la misma
                            # marca, código y stock darían el mismo texto y uno taparía al otro.
                            _rotulos = {f["ID"]: _rotulo_stock(f) for f in res}
                            _elegido = st.selectbox(f"¿Cuál? ({len(res)} resultados)",
                                                    list(_rotulos), format_func=_rotulos.get,
                                                    key=f"cual_vendido_{clean}")
                            colr2, colr3 = st.columns(2)
                            colr2.button("🛒 Se llevó", key=f"vendido_elegido_{clean}",
                                          on_click=anotar_venta_y_avisar,
                                          args=(_elegido, codigo_individual, _rotulos[_elegido],
                                                f"stock_{clean}"),
                                          help="Anota la venta para ir descubriendo equivalencias solas")
                            colr3.button("📌 Reponer", key=f"pedir_elegido_{clean}",
                                          on_click=pedir_reposicion_y_avisar,
                                          args=(_elegido, _rotulos[_elegido], f"stock_{clean}"),
                                          help="Marcar para reposición")

                        mostrar_lo_anotado(f"stock_{clean}")
                        if es_empleado_o_abierto():
                            mostrar_pedir_al_deposito(res, clean)

                        # Marcar favoritos / editar precio y stock
                        if seccion_plegable("✏️ Marcar favorito / editar precio, costo y stock",
                                             key=f"editar_{clean}"):
                            for fila in res:
                                colF, colC, colP, colS, colG, colH = cols([0.5, 1.7, 1.1, 0.9, 0.7, 0.7])
                                es_fav = bool(fila.get("Favorito"))
                                nuevo_fav = colF.checkbox("⭐", value=es_fav, key=f"fav_{fila['ID']}_{clean}")
                                if nuevo_fav != es_fav:
                                    alternar_favorito(fila["ID"], nuevo_fav)
                                colC.write(f"{fila['Marca']} - {fila['Codigo']}")
                                # Con qué valores se abrió el editor: ver valor_con_que_se_abrio().
                                _k_precio = f"precio_{fila['ID']}_{clean}"
                                _k_stock = f"stock_{fila['ID']}_{clean}"
                                _k_costo = f"costo_{fila['ID']}_{clean}"
                                # De la base y no de `fila`: los resultados de la búsqueda
                                # quedan en memoria y pueden ser de hace un rato.
                                c.execute("SELECT precio, stock FROM productos WHERE id = ?",
                                          (fila["ID"],))
                                _en_la_base = c.fetchone() or {"precio": 0, "stock": 0}
                                _precio_visto = valor_con_que_se_abrio(
                                    _k_precio, float(_en_la_base["precio"] or 0))
                                _stock_visto = valor_con_que_se_abrio(
                                    _k_stock, int(_en_la_base["stock"] or 0))
                                nuevo_precio = colP.number_input(
                                    "Precio", key=_k_precio, min_value=0.0, step=100.0,
                                    label_visibility="collapsed"
                                )
                                nuevo_stock = colS.number_input(
                                    "Stock", key=_k_stock, min_value=0, step=1,
                                    label_visibility="collapsed"
                                )
                                if candado('tocar precios y stock', colG.button("💾", key=f"save_{fila['ID']}_{clean}"), 'tocar_precios_y_stock', nivel="empleado"):
                                    _nuevo_costo = st.session_state.get(_k_costo)
                                    _guardado = actualizar_precio_stock(
                                        fila["ID"], nuevo_precio, nuevo_stock, _nuevo_costo,
                                        stock_mostrado=_stock_visto, precio_mostrado=_precio_visto,
                                        costo_mostrado=st.session_state.get(f"_abierto_con_{_k_costo}"))
                                    if isinstance(_guardado, str):
                                        # Lo que otro cambió mientras se editaba NO se pisó. Lo
                                        # que hay ahora pasa a ser lo «mostrado»: guardar de nuevo
                                        # después del aviso es corregirlo a sabiendas.
                                        c.execute("SELECT precio, stock, precio_costo FROM productos "
                                                  "WHERE id = ?", (fila["ID"],))
                                        _ahora = c.fetchone()
                                        _que = {"precio_cambio": f"el precio (ahora {formato_precio(_ahora['precio'] or 0)})",
                                                "stock_cambio": f"el stock (ahora hay {_ahora['stock']})",
                                                "costo_cambio": f"el costo (ahora {formato_precio(_ahora['precio_costo'] or 0)})"}
                                        for _clave_ed in (_k_precio, _k_stock, _k_costo):
                                            ya_se_guardo(_clave_ed)
                                        st.warning(
                                            "Mientras editabas, alguien cambió "
                                            + " y ".join(_que[x] for x in _guardado.split(","))
                                            + ": eso NO se guardó, para no pisarlo. Lo demás sí. "
                                            "Al tocar algo el editor muestra lo que hay ahora; si "
                                            "igual querés tu valor, escribilo otra vez y guardá.")
                                    elif _guardado:
                                        for _clave_ed in (_k_precio, _k_stock, _k_costo):
                                            ya_se_guardo(_clave_ed)
                                        st.success("Guardado.")
                                    else:
                                        # Decirlo y no mentir un «Guardado»: el producto lo
                                        # borró la otra sesión mientras esta pantalla estaba
                                        # abierta.
                                        st.error("Ese producto ya no está en el catálogo: "
                                                 "alguien lo borró mientras tenías esta "
                                                 "pantalla abierta. Refrescá y fijate.")
                                if es_admin():
                                    c.execute("SELECT precio_costo FROM productos WHERE id = ?",
                                              (fila["ID"],))
                                    _fc = c.fetchone()
                                    valor_con_que_se_abrio(
                                        f"costo_{fila['ID']}_{clean}",
                                        float((_fc["precio_costo"] if _fc else 0) or 0))
                                    cc1, cc2 = st.columns([2, 3])
                                    cc1.number_input(
                                        "Costo", min_value=0.0, step=100.0,
                                        key=f"costo_{fila['ID']}_{clean}",
                                        help="Lo que te cuesta a vos. Solo lo ve el administrador."
                                    )
                                    _pct, _pesos = margen_de(nuevo_precio,
                                                              st.session_state.get(
                                                                  f"costo_{fila['ID']}_{clean}"))
                                    if _pct is not None:
                                        cc2.caption(f"Margen: **{_pct:.0f}%** "
                                                     f"(${miles(_pesos, 0)} por unidad)")
                                    else:
                                        cc2.caption("Cargá el costo para ver el margen.")

                                if colH.button("📈", key=f"hist_precio_{fila['ID']}_{clean}", help="Ver historial de precio"):
                                    st.session_state[f"mostrar_hist_{fila['ID']}"] = True
                                if st.session_state.get(f"mostrar_hist_{fila['ID']}"):
                                    historial_p = historial_precio_producto(fila["ID"])
                                    if historial_p:
                                        st.dataframe(historial_p, width="stretch", hide_index=True)
                                    else:
                                        st.caption("Todavía no hay cambios de precio registrados para este producto.")

                        if catalogos:
                            st.caption("Buscar este código también en:")
                            # OJO con el nombre: 'cols' es una función de esta app (arma columnas
                            # que se apilan bien en el celular). Llamar a la variable igual la
                            # pisaba a nivel global, y a partir de ahí cualquier cols(3) posterior
                            # reventaba con "'list' object is not callable". Solo saltaba cuando la
                            # marca tenía catálogo cargado, por eso era intermitente.
                            columnas_catalogos = st.columns(len(catalogos))
                            for col, cat in zip(columnas_catalogos, catalogos):
                                with col:
                                    st.link_button(f"🌐 {cat['nombre']}", cat["url"],
                                                    width="stretch", key=f"link_{cat['id']}_{clean}")
                    elif marcas_que_nombra(clean):
                        # El nombre de una lista en el buscador de CÓDIGOS. Pasó: «mannol», con
                        # 81 productos de MANNOL LUBRICANTES, y la pantalla decía que no había
                        # nada. Se muestran sus productos.
                        _de_la_marca = buscar_por_texto(codigo_individual)
                        _nombres_m = sorted({f["Marca"] for f in _de_la_marca}) or [clean]
                        st.info(f"🏷️ **«{codigo_individual}» es una de tus listas: "
                                f"{', '.join(_nombres_m)}** ({len(_de_la_marca)} producto(s)"
                                + (", se muestran los primeros" if len(_de_la_marca) > 12 else "")
                                + "). Para buscar adentro de ella, escribí la marca y lo que "
                                "buscás en «Por descripción» (por ejemplo «"
                                f"{codigo_individual.lower()} 5w40»).")
                        mostrar_lista_clickeable(_de_la_marca, f"marca_{clean}", limite=12)
                    else:
                        st.warning("No hay ningún producto con ese código exacto.")

                        # ¿Este código fue reemplazado por otro? Es la causa más tonta de
                        # perder una venta: la pieza existe, cambió de número, y se le dice al
                        # cliente que no se fabrica más.
                        _cadena_r = cadena_de_reemplazos(clean)
                        if _cadena_r:
                            _ultimo = _cadena_r[-1]
                            # La variable acá se llama codigo_individual: es el código que se
                            # está resolviendo en esta vuelta del bucle, no el texto del campo.
                            _ruta = " → ".join([str(codigo_individual).strip()] +
                                                [x["codigo"] for x in _cadena_r])
                            st.success(
                                f"🔄 **Ese código fue reemplazado.** {_ruta}\n\n"
                                f"El vigente es **{_ultimo['codigo']}**"
                                + (f" ({_ultimo['marca']})" if _ultimo["marca"] else "")
                                + (f". {_ultimo['nota']}" if _ultimo["nota"] else ".")
                            )
                            _res_nuevo = buscar_por_codigo(_ultimo["clean"])
                            if _res_nuevo:
                                st.dataframe(quitar_id(_res_nuevo), width="stretch",
                                              hide_index=True)
                            else:
                                st.caption("Tampoco tenés cargado el código nuevo.")

                        # Antes de darse por vencido: ¿lo conoce algún catálogo de fabricante?
                        # Ahí figura qué pieza es y a qué autos le va, y con eso se puede
                        # ofrecer un equivalente en vez de perder la venta.
                        ajeno = identificar_codigo_ajeno(clean)
                        if ajeno:
                            st.info(
                                f"🏭 **Ese código existe: es {ajeno['tipo'] or 'una pieza'} de "
                                f"{ajeno['marca']}**, y según su catálogo le va a "
                                f"{ajeno['cantidad_autos']} auto(s). No lo tenés cargado."
                            )
                            # Sin expander: este bloque ya está dentro del expander de
                            # resultados por código, y Streamlit no admite anidarlos.
                            if ajeno["autos"]:
                                if seccion_plegable(
                                        f"Ver a qué autos le va ({len(ajeno['autos'])})",
                                        key=f"autos_ajeno_{clean}"):
                                    st.dataframe(
                                        [{"Marca": a["marca_auto"], "Modelo": a["modelo_auto"],
                                          "Motor": a["motor"],
                                          "Años": f"{a['anio_desde'] or ''}-{a['anio_hasta'] or ''}"}
                                         for a in ajeno["autos"]],
                                        width="stretch", hide_index=True
                                    )
                            reemplazos = equivalentes_para_los_mismos_autos(clean)
                            if reemplazos:
                                st.success(
                                    f"✅ **Tenés {len(reemplazos)} repuesto(s) que sirven para los "
                                    "mismos autos**, según el catálogo de sus propios fabricantes:"
                                )
                                st.dataframe(reemplazos, width="stretch", hide_index=True)
                                st.caption(
                                    "Los que tienen stock van primero. Confirmá con el cliente "
                                    "el modelo y el año antes de cerrar: el catálogo dice a qué "
                                    "autos le va la pieza, no si es exactamente la que traía."
                                )

                        # Error de tipeo. Se muestra ANTES que las familias porque es lo más
                        # probable: en el mostrador se tipea rápido y se dan vuelta dos dígitos.
                        # Lo que ya había solo encontraba códigos que empiezan igual, así que
                        # W71249 por W71294 no daba nada aunque fuera el mismo filtro.
                        tipeos = codigos_por_tipeo(clean)
                        if tipeos:
                            # Son OTROS códigos: un 6205 y un 6206 son rulemanes distintos.
                            # Se ofrecen por si fue un error de tipeo, nunca como equivalencia
                            # (lo señaló una revisión con ChatGPT).
                            st.info(f"⌨️ ¿No será alguno de estos? Se escriben casi igual a lo que "
                                     f"pusiste ({len(tipeos)} encontrado(s)). **Son códigos "
                                     "distintos, no equivalencias**: confirmá que sea el que "
                                     "quería el cliente.")
                            st.dataframe(
                                [{"Código": t["Codigo"], "Marca": t["Marca"],
                                  "Descripción": t["Descripcion"], "Precio": t["Precio"],
                                  "Stock": t["Stock"],
                                  "Diferencia": "1 carácter" if t["_dist"] == 1 else "2 caracteres"}
                                 for t in tipeos],
                                width="stretch", hide_index=True
                            )

                        # Familias de códigos: pedís "TC-421" y en la base están "TC-421-15",
                        # "TC-421-20", etc. Antes esto no aparecía por ningún lado.
                        parecidos = buscar_codigos_parecidos(clean)
                        if parecidos:
                            st.info(
                                f"🔎 Pero hay {len(parecidos)} código(s) que empiezan igual o lo "
                                "contienen — puede ser una familia con variantes (espesor, lado, medida):"
                            )
                            for p in parecidos[:12]:
                                equivalentes_p = buscar_por_codigo(p["_clean"])
                                otros_p = [e for e in equivalentes_p if e["ID"] != p["ID"]]
                                resumen_p = (f"{len(otros_p)} equivalencia(s)" if otros_p
                                              else "sin equivalencias cargadas")
                                if seccion_plegable(f"🔎 {p['Marca']} · {p['Codigo']} — {resumen_p}",
                                                     key=f"detalle_{clean}_{p['ID']}"):
                                    if p.get("Descripcion"):
                                        st.caption(p["Descripcion"])
                                    if equivalentes_p:
                                        st.dataframe(quitar_id(equivalentes_p),
                                                      width="stretch", hide_index=True)
                                    else:
                                        st.caption("Todavía no tiene equivalencias cargadas.")
                                    st.button("🔎 Abrir este código como búsqueda",
                                               key=f"abrir_parecido_{p['ID']}",
                                               on_click=cb_ver_equivalencias, args=(p["Codigo"],))
                            if len(parecidos) > 12:
                                st.caption(f"(mostrando 12 de {len(parecidos)})")
                        else:
                            # Con lo escrito tal cual y no con el código limpio: «filtro 24058»
                            # limpio es «FILTRO24058», que no está en ningún lado; con las dos
                            # palabras aparece el 24058FISPA. Y sin aflojar: con una sola de las
                            # palabras, «kit 22382» traía 200 productos cualesquiera.
                            parcial = buscar_por_texto(codigo_individual, aflojar=False)
                            if parcial:
                                st.info("¿Quisiste decir alguno de estos? Tocá el código para ver sus equivalencias:")
                                mostrar_lista_clickeable(parcial, f"sug_{clean}", limite=12)
    else:
        # La voz la transcribe la IA, que se paga por uso: para empleados, como el resto de la
        # IA de la app. Ver es_empleado_o_abierto().
        if es_empleado_o_abierto():
            with st.expander("🎙️ Buscar por voz"):
                ayuda(
                    "Grabá diciendo lo que buscás — la IA lo transcribe y lo busca con el buscador de "
                    "siempre. No es un asistente que entienda pedidos complejos, es simplemente hablar "
                    "en vez de tipear."
                )
                audio_busqueda = st.audio_input("Grabar:", key="audio_busqueda_voz")
                if audio_busqueda and st.button("🔍 Transcribir y buscar"):
                    with st.spinner("Transcribiendo..."):
                        mime_audio = audio_busqueda.type or "audio/wav"
                        texto_voz, error_voz = transcribir_audio(audio_busqueda.getvalue(), mime_audio)
                    if error_voz:
                        st.error(error_voz)
                    else:
                        st.session_state["texto_desde_voz"] = texto_voz
                        st.rerun()

        # Precargar el texto transcripto ANTES de crear el widget del form — si se hace después
        # de que ya se dibujó en pantalla, Streamlit tira un error.
        if "texto_desde_voz" in st.session_state:
            st.session_state["texto_input"] = st.session_state.pop("texto_desde_voz")

        with st.form("form_buscar_texto"):
            texto = st.text_input(
                "Ingresá parte de una descripción:",
                placeholder="Ej: ruleman delantero gol (no hace falta el orden exacto)",
                key="texto_input"
            )
            buscar_texto_click = st.form_submit_button("🔍 Buscar por Descripción", type="primary")

        # Igual que en la búsqueda por código: los resultados se guardan en la sesión en vez de
        # depender de que el botón "Buscar" haya sido lo último que se tocó. Si no, al apretar
        # cualquier botón de adentro el bloque entero desaparece y el click se pierde.
        # Un código escrito acá —todo lo escrito son códigos cargados— va al buscador de
        # códigos, que es el que trae las equivalencias.
        if buscar_texto_click and texto.strip() and all(
                sanitizar(x) and existe_el_codigo(sanitizar(x))
                for x in texto.split(",") if x.strip()) and not parece_una_descripcion(texto):
            st.session_state["_pasar_a_codigo"] = texto.strip()
            st.session_state.pop("ultima_busqueda_texto", None)
            st.rerun()
        _desde_codigos = st.session_state.pop("_buscar_texto_ya", False)
        if _desde_codigos:
            st.caption("🔤 Eso no es un código, así que se buscó en las descripciones y las "
                       "marcas.")
        if buscar_texto_click or _desde_codigos:
            if not texto.strip():
                st.info("Ingresá un texto para buscar.")
                st.session_state.pop("ultima_busqueda_texto", None)
            elif len(re.sub(r"\W", "", texto)) < MINIMO_PARA_BUSCAR_POR_TEXTO:
                # Una letra sola trae 200 cosas que solo tienen esa letra (medido: «a» → 200).
                st.info(f"Escribí al menos {MINIMO_PARA_BUSCAR_POR_TEXTO} letras o números.")
                st.session_state.pop("ultima_busqueda_texto", None)
            else:
                guardar_busqueda(texto.strip())
                _t_busqueda = time.perf_counter()
                try:
                    _res_texto = buscar_por_texto(texto)
                except sqlite3.Error as _err_busqueda:
                    anotar_error("buscador", _err_busqueda)
                    _res_texto = None
                    st.error("⚠️ **No se pudo consultar** — no quiere decir que no esté. Tocá "
                             "«Buscar» de nuevo. Si se repite, avisá con este código: `"
                             + anotar_busqueda("texto", texto, time.perf_counter() - _t_busqueda,
                                               0, _err_busqueda) + "`.")
                    st.session_state.pop("ultima_busqueda_texto", None)
                if _res_texto is not None:
                    anotar_busqueda("texto", texto, time.perf_counter() - _t_busqueda,
                                    len(_res_texto))
                    st.session_state["ultima_busqueda_texto"] = {
                        "texto": texto.strip(), "res": _res_texto
                    }

        busqueda_texto_guardada = st.session_state.get("ultima_busqueda_texto")
        if busqueda_texto_guardada:
            res_texto = busqueda_texto_guardada["res"]
            texto_pedido = busqueda_texto_guardada["texto"]
            if res_texto:
                st.success(f"Se encontraron {len(res_texto)} coincidencia(s). 👆 Tocá una fila "
                           "para abrir ese código con todas sus equivalencias.")
                # Lo pedido que ningún resultado dice: «necesito pastillas delanteras para un
                # Corsa Classic 2012» trae cosas del Corsa Classic, y sin esto parecía que eran
                # pastillas. Ver palabras_que_no_aparecen().
                _faltan = palabras_que_no_aparecen(texto_pedido, res_texto)
                if _faltan:
                    st.warning("⚠️ Ninguno de estos dice " + " ni ".join(
                        f"«{x.lower()}»" for x in _faltan[:3]) + ": puede que no lo tengas "
                        "cargado. Se muestra lo que coincide con el resto.")
                # La fila se toca en la misma tabla. Antes abajo se repetía la lista entera como
                # botones —uno por resultado, con su descripción—, y en el celular la página
                # medía tres pantallas más para mostrar lo que la tabla ya decía.
                # Filtro por marca cuando el resultado mezcla varias: «sensor rotacion ford» son
                # 197 filas de cinco listas, y lo que se busca suele ser «¿qué tengo de FISPA?».
                # Lo sugirió la revisión de usabilidad con Gemini.
                _marcas_txt = {}
                for _f in res_texto:
                    _marcas_txt[_f["Marca"]] = _marcas_txt.get(_f["Marca"], 0) + 1
                _res_vista = res_texto
                if len(_marcas_txt) > 1:
                    _opciones_mt = ["Todas"] + sorted(_marcas_txt, key=lambda m: -_marcas_txt[m])
                    if st.session_state.get("filtro_marca_texto") not in _opciones_mt:
                        st.session_state.pop("filtro_marca_texto", None)
                    _marca_txt = st.selectbox(
                        "Marca:", _opciones_mt, key="filtro_marca_texto",
                        format_func=lambda m: (f"Todas ({len(res_texto)})" if m == "Todas"
                                               else f"{m} ({_marcas_txt[m]})"))
                    if _marca_txt != "Todas":
                        _res_vista = [f for f in res_texto if f["Marca"] == _marca_txt]
                _tabla_txt = para_mostrar(quitar_id(_res_vista))
                st.dataframe(_tabla_txt, width="stretch", hide_index=True,
                             column_order=columnas_que_dicen_algo(_tabla_txt),
                             column_config=CONFIG_COLUMNAS_RESULTADO,
                             key="tabla_resultados_texto", selection_mode="single-row",
                             on_select=functools.partial(
                                 abrir_la_fila_elegida, "tabla_resultados_texto", _res_vista))

                # La búsqueda por descripción solo hace coincidir texto: encuentra el producto,
                # pero no sus equivalentes. Acá se abre la red de equivalencias de cada resultado,
                # igual que hace la búsqueda por código, para no perder de vista las otras marcas.
                st.markdown("**🔗 Equivalencias de cada resultado**")
                st.caption("Cada uno abre las otras marcas que sirven, con precio y stock.")
                for fila_txt in res_texto[:15]:
                    clean_txt = sanitizar(fila_txt["Codigo"])
                    # Sin los códigos de fábrica: unen, pero no se venden (ver la búsqueda por
                    # código, más arriba).
                    equivalentes = [e for e in (buscar_por_codigo(clean_txt) if clean_txt else [])
                                    if e.get("Tipo") != "OEM" or e["ID"] == fila_txt["ID"]]
                    otros = [e for e in equivalentes if e["ID"] != fila_txt["ID"]]
                    resumen = (f"{len(otros)} equivalencia(s)" if otros else "sin equivalencias cargadas")
                    with st.expander(f"🔎 {fila_txt['Marca']} · {fila_txt['Codigo']} — {resumen}"):
                        if fila_txt.get("Descripcion"):
                            st.caption(fila_txt["Descripcion"])
                        if equivalentes:
                            candidatos_precio = [f for f in equivalentes
                                                  if f.get("Precio") and (f.get("Stock") or 0) > 0]
                            id_barato = (min(candidatos_precio, key=lambda f: f["Precio"])["ID"]
                                          if candidatos_precio else None)
                            for f in equivalentes:
                                f["💰"] = "🏆 Más barato en stock" if f["ID"] == id_barato else ""
                            _tabla_eq = para_mostrar(quitar_id(equivalentes))
                            st.dataframe(_tabla_eq, width="stretch", hide_index=True,
                                         column_order=columnas_que_dicen_algo(_tabla_eq),
                                         column_config=CONFIG_COLUMNAS_RESULTADO)
                        else:
                            st.caption("Este producto todavía no tiene equivalencias cargadas.")

                        # Carrito: ir juntando de varias búsquedas y armar el presupuesto al
                        # final. Sin esto había que anotar los códigos aparte y volver a
                        # buscarlos uno por uno.
                        # Mismos nombres que el resto de esta rama: acá el resultado de la
                        # vuelta es fila_txt y sus equivalentes están en 'otros'. Estaba escrito
                        # con 'res' y 'clean', que son de la búsqueda por CÓDIGO y acá no
                        # existen: entrar a "Descripción" tiraba NameError.
                        st.session_state.setdefault("carrito", {})
                        opciones_carrito = [fila_txt] + otros
                        cc1, cc2 = st.columns([3, 2])
                        agregar_cod = cc1.selectbox(
                            "🛒 Sumar al presupuesto:",
                            ["(elegir)"] + [f"{f['Marca']} {f['Codigo']}"
                                            for f in opciones_carrito],
                            key=f"al_carrito_{fila_txt['ID']}")
                        if agregar_cod != "(elegir)" and cc2.button(
                                "➕ Sumar", key=f"btn_carrito_{fila_txt['ID']}"):
                            elegido_c = next((f for f in opciones_carrito
                                               if f"{f['Marca']} {f['Codigo']}" == agregar_cod), None)
                            if elegido_c:
                                sumar_al_presupuesto(elegido_c)
                                avisar("success", f"{elegido_c['Codigo']} sumado al presupuesto.")
                                st.rerun()

                        # Anotar al cliente que se lo lleva pensando. Va acá porque el momento
                        # de anotarlo es este: si hay que ir a otra pantalla, no se hace.
                        # OJO con los nombres, lo mismo que avisa el bloque de abajo: acá
                        # estamos en la búsqueda por DESCRIPCIÓN, donde la fila de esta vuelta es
                        # fila_txt y sus equivalentes están en 'otros'. Este bloque estaba escrito
                        # con los nombres de la búsqueda por CÓDIGO ('res', 'clean'), que acá no
                        # existen: abrir esta sección tiraba NameError y se cortaba la pantalla.
                        # Las keys van por ID y no por código limpio, porque dos filas distintas
                        # pueden limpiar al mismo texto y ahí Streamlit corta por clave repetida.
                        if seccion_plegable("📞 El cliente lo va a pensar",
                                             key=f"consulta_{fila_txt['ID']}"):
                            st.caption(
                                "Queda anotado qué pidió y a qué precio se le dijo. Cuando "
                                "vuelva o llame, lo buscás por nombre o teléfono."
                            )
                            etq_cc = {f"{f['Marca']} {f['Codigo']}": f
                                      for f in [fila_txt] + otros}
                            cual_cc = st.selectbox("¿Qué le interesó?", list(etq_cc.keys()),
                                                    key=f"cual_cc_{fila_txt['ID']}")
                            k1, k2, k3 = st.columns([3, 3, 1])
                            nom_cc = k1.text_input("Nombre:", key=f"nom_cc_{fila_txt['ID']}",
                                                    placeholder="Cómo se llama")
                            tel_cc = k2.text_input("Teléfono:", key=f"tel_cc_{fila_txt['ID']}",
                                                    placeholder="Para avisarle")
                            cant_cc = k3.number_input("Cant.", min_value=1, value=1, step=1,
                                                       key=f"cant_cc_{fila_txt['ID']}")
                            nota_cc = st.text_input("Nota:", key=f"nota_cc_{fila_txt['ID']}",
                                                     placeholder="Ej: tiene un Gol 2012, "
                                                                 "consulta con el mecánico")
                            if st.button("📞 Anotar la consulta",
                                          key=f"btn_cc_{fila_txt['ID']}"):
                                _f = etq_cc[cual_cc]
                                ok_cc, msg_cc = anotar_consulta_cliente(
                                    nom_cc, tel_cc, _f["ID"], _f["Codigo"],
                                    _f.get("Descripcion") or "", cant_cc,
                                    _f.get("Precio"), nota_cc)
                                if ok_cc:
                                    avisar("success", msg_cc)
                                    st.rerun()
                                else:
                                    st.error(msg_cc)

                        # Apartar mientras el cliente lo piensa. Va acá y no en otra pantalla
                        # porque el momento de reservar es este: con el presupuesto recién hecho.
                        # OJO con los nombres: acá el código limpio es clean_txt y la lista es
                        # 'equivalentes'. Usar los de la búsqueda por código ('clean', 'res')
                        # tira NameError y corta el renderizado de toda la pantalla.
                        _para_apartar = equivalentes or [fila_txt]
                        if seccion_plegable("🔒 Apartar para un presupuesto",
                                             key=f"apartar_txt_{fila_txt['ID']}"):
                            # Una sola consulta para todos: preguntarlo de a uno eran dos
                            # consultas por fila para filtrar y dos más por fila para la etiqueta.
                            libres_ap = stock_libre_de_varios([f["ID"] for f in _para_apartar])
                            con_stock_ap = [f for f in _para_apartar
                                             if (libres_ap.get(f["ID"]) or 0) > 0]
                            if not con_stock_ap:
                                st.caption("Ninguno de estos tiene stock libre para apartar.")
                            else:
                                etq_ap = {
                                    f"{f['Marca']} {f['Codigo']} — {libres_ap[f['ID']]} libre(s)":
                                        f["ID"] for f in con_stock_ap
                                }
                                elegido_ap = st.selectbox("¿Cuál?", list(etq_ap.keys()),
                                                           key=f"cual_apartar_txt_{fila_txt['ID']}")
                                ap1, ap2 = st.columns([1, 3])
                                cant_ap = ap1.number_input(
                                    "Cantidad", min_value=1, value=1, step=1,
                                    key=f"cant_apartar_txt_{fila_txt['ID']}")
                                cliente_ap = ap2.text_input(
                                    "¿Para quién?", key=f"cliente_apartar_txt_{fila_txt['ID']}",
                                    placeholder="Nombre o patente, para saber a quién reclamarle")
                                if st.button("🔒 Apartar", key=f"btn_apartar_txt_{fila_txt['ID']}"):
                                    ok_ap, msg_ap = reservar_stock(
                                        etq_ap[elegido_ap], cant_ap, cliente_ap)
                                    if ok_ap:
                                        avisar("success", msg_ap)
                                        st.rerun()
                                    else:
                                        st.error(msg_ap)

                        st.markdown("**🛒 ¿Cuál se llevó el cliente?**")
                        st.caption(
                            "Marcá el que se lleva — vale también si se lleva un equivalente y no "
                            "el que apareció en la búsqueda. Así el sistema aprende esa relación."
                        )
                        for f in (equivalentes or [fila_txt]):
                            cv1, cv2 = st.columns([4, 1])
                            precio_txt = f"${miles(f['Precio'], 0)}" if f.get("Precio") else "s/precio"
                            cv1.write(f"{f['Marca']} - {f['Codigo']} ({precio_txt}, "
                                       f"stock: {f.get('Stock') if f.get('Stock') is not None else 's/d'})")
                            cv2.button("🛒 Se llevó", key=f"vendido_txt_{fila_txt['ID']}_{f['ID']}",
                                        on_click=anotar_venta_y_avisar,
                                        args=(f["ID"], texto_pedido, f"{f['Marca']} - {f['Codigo']}",
                                              f"txt_{fila_txt['ID']}"))
                        mostrar_lo_anotado(f"txt_{fila_txt['ID']}")
                if len(res_texto) > 15:
                    st.caption(f"(mostrando las primeras 15 de {len(res_texto)} — afiná la búsqueda "
                                "para ver menos resultados)")
            else:
                st.warning("No se encontraron productos con esa descripción.")

                # Antes de rendirse: entender qué pidió el cliente. En el mostrador nadie dice
                # un código, dice «pastillas para un Gol 1.6». De esa frase se puede sacar el
                # rubro y el auto, y con eso ofrecer algo en vez de nada.
                pedido = interpretar_pedido_hablado(texto_pedido)
                if pedido and (pedido["familia"] or pedido["marca_auto"]):
                    partes = []
                    if pedido["familia"]:
                        partes.append(f"**{pedido['familia']}**")
                    if pedido["marca_auto"]:
                        auto = pedido["marca_auto"]
                        if pedido["modelo"]:
                            auto += f" {pedido['modelo']}"
                        if pedido["cilindrada"]:
                            auto += f" {pedido['cilindrada']}"
                        partes.append(f"para un **{auto}**")
                    st.info("🤔 Entendí que buscás " + " ".join(partes) + ".")

                    alternativas = buscar_por_pieza_y_auto(
                        pedido["familia"], pedido["marca_auto"], pedido["modelo"],
                        pedido["cilindrada"])
                    if alternativas:
                        st.success(f"Esto es lo que tenés que puede servir ({len(alternativas)}):")
                        st.dataframe(quitar_id(alternativas), width="stretch",
                                      hide_index=True)
                        st.caption("Con stock primero. Confirmá el modelo y el año antes de cerrar.")
                    elif pedido["marca_auto"]:
                        # Aflojar el filtro: quizá no tenés ese rubro para ese auto, pero sí algo
                        sin_familia = buscar_por_pieza_y_auto(
                            None, pedido["marca_auto"], pedido["modelo"], pedido["cilindrada"])
                        if sin_familia:
                            st.info(
                                f"No tenés {pedido['familia'] or 'esa pieza'} para ese auto, pero "
                                f"sí {len(sin_familia)} repuesto(s) de otros rubros:"
                            )
                            st.dataframe(quitar_id(sin_familia[:20]),
                                          width="stretch", hide_index=True)

    with st.expander("📦 Armar pedido (ordenado por ubicación en depósito)"):
        ayuda(
            "Pegá varios códigos separados por coma — te devuelve la lista ordenada por ubicación "
            "en el depósito, para juntar todo en un solo recorrido en vez de ir y volver."
        )
        codigos_picking = st.text_input(
            "Códigos del pedido (separados por coma):",
            placeholder="Ej: W712/94, 036115561G, 24427...", key="picking_codigos"
        )
        if st.button("📦 Ordenar para picking"):
            if not codigos_picking.strip():
                st.info("Pegá al menos un código.")
            else:
                res_picking = armar_lista_picking(codigos_picking)
                if res_picking:
                    sin_ubicacion = [r for r in res_picking if not r["Ubicación"]]
                    st.success(f"Se encontraron {len(res_picking)} de los códigos pedidos:")
                    st.dataframe(res_picking, width="stretch", hide_index=True)
                    if sin_ubicacion:
                        st.caption(
                            f"⚠️ {len(sin_ubicacion)} producto(s) todavía no tienen ubicación cargada "
                            f"(aparecen al final) — cargala en {miga_hasta('Productos')} para que la próxima vez "
                            "el orden sea completo."
                        )
                else:
                    st.warning("No encontré ninguno de esos códigos en el catálogo.")

    with st.expander("📐 Buscar por medidas mecánicas (cuando no hay código ni equivalencia cargada)"):
        ayuda(
            "Para piezas de autos antiguos, importados o fuera de catálogo: medí la pieza rota con un "
            "calibre y buscá alternativas que compartan esas cotas, aunque no tengan equivalencia registrada."
        )
        cm1, cm2, cm3 = cols(3)
        m_diam_int = cm1.number_input("Diámetro interno (mm)", min_value=0.0, step=0.1, value=0.0, key="med_di")
        m_diam_ext = cm2.number_input("Diámetro externo (mm)", min_value=0.0, step=0.1, value=0.0, key="med_de")
        m_ancho = cm3.number_input("Ancho (mm)", min_value=0.0, step=0.1, value=0.0, key="med_an")
        cm4, cm5, cm6 = cols(3)
        m_paso = cm4.text_input("Paso de rosca (opcional)", key="med_paso", placeholder="Ej: M12x1.5")
        m_estrias = cm5.number_input("Cantidad de estrías (opcional)", min_value=0, step=1, value=0, key="med_estrias")
        m_tolerancia = cm6.slider("Tolerancia (%)", min_value=1, max_value=15, value=5, key="med_tol")

        st.markdown("**↔️ Segunda cara (opcional, para piezas con distinta medida de cada lado)**")
        ayuda(
            "Ej: un retén con labio interior de un diámetro de un lado y otro del otro, o un tensor "
            "con el interior escalonado (17mm de una cara, 8mm de la otra)."
        )
        cb1, cb2 = st.columns(2)
        m_diam_int_b = cb1.number_input("Diámetro interno cara B (mm)", min_value=0.0, step=0.1, value=0.0, key="med_di_b")
        m_diam_ext_b = cb2.number_input("Diámetro externo / labio exterior cara B (mm)", min_value=0.0, step=0.1,
                                         value=0.0, key="med_de_b")

        st.markdown("**🔩 Homocinéticas (opcional)**")
        ch1, ch2 = st.columns(2)
        m_estrias_int = ch1.number_input("Estrías internas", min_value=0, step=1, value=0, key="med_estrias_int")
        m_estrias_ext = ch2.number_input("Estrías externas", min_value=0, step=1, value=0, key="med_estrias_ext")
        ch3, ch4 = st.columns(2)
        m_seguro = ch3.text_input("Posición del seguro", key="med_seguro", placeholder="Ej: 1er ranura, a 12mm")
        m_abs = ch4.selectbox("¿Tiene ABS?", ["Cualquiera", "Sí", "No"], key="med_abs")
        ch5, ch6 = st.columns(2)
        m_rosca_homo = ch5.number_input("Diámetro de rosca (mm)", min_value=0.0, step=0.1, value=0.0, key="med_rosca_homo")
        m_largo_total = ch6.number_input(
            "Largo total (mm)", min_value=0.0, step=0.5, value=0.0, key="med_largo_total",
            help="De punta a punta — es la medida que más rápido descarta."
        )
        st.caption("La copa es cónica: cargá los dos diámetros si los tenés (base y boca).")
        ch7, ch8 = st.columns(2)
        m_copa = ch7.number_input("Diám. copa — base (mm)", min_value=0.0, step=0.1, value=0.0, key="med_copa")
        m_copa_sup = ch8.number_input("Diám. copa — boca / superior (mm)", min_value=0.0, step=0.1,
                                       value=0.0, key="med_copa_sup")

        if st.button("📐 Buscar por medidas"):
            res_medidas = buscar_por_medidas(
                m_diam_int or None, m_diam_ext or None, m_ancho or None,
                m_paso or None, m_estrias or None, m_tolerancia,
                m_estrias_int or None, m_estrias_ext or None, m_seguro or None, m_abs,
                m_diam_int_b or None, m_diam_ext_b or None,
                m_rosca_homo or None, m_copa or None,
                m_copa_sup or None, m_largo_total or None
            )
            if res_medidas:
                st.success(f"Se encontraron {len(res_medidas)} pieza(s) con medidas compatibles:")
                st.dataframe(quitar_id(res_medidas), width="stretch", hide_index=True)
            else:
                st.warning(
                    "Sin resultados. Puede ser que no haya piezas con esas medidas cargadas todavía — "
                    f"cargalas en {miga_hasta('Productos')} a medida que las vayas midiendo."
                )

    if es_operador_o_admin():
        with st.expander("📷 Identificar pieza por foto (con IA)"):
            st.caption(
                "Sacale una foto a la pieza o subí una que ya tengas. La IA busca un código visible "
                "y, si lo encuentra, lo busca directo en tu catálogo."
            )
            foto = recordar_archivo(st.file_uploader(
                "Foto de la pieza:", type=["png", "jpg", "jpeg"], key="foto_identificar_pieza",
                label_visibility="collapsed"
            ), "foto_pieza")
            foto_ok = archivo_listo(foto, "foto")
            if foto and st.button("🗑️ Usar otra foto", key="otra_foto_pieza"):
                olvidar_archivo("foto_pieza")
                st.rerun()
            if st.button("🔍 Identificar", disabled=not foto_ok):
                with st.spinner("Consultando..."):
                    datos_pieza, error = identificar_pieza_por_foto(foto.getvalue())
                if error:
                    st.error(error)
                elif datos_pieza:
                    st.session_state["datos_pieza_foto"] = datos_pieza
                    st.session_state["buscar_tipo_pieza_click"] = False

            if st.session_state.get("datos_pieza_foto"):
                datos_pieza = st.session_state["datos_pieza_foto"]
                codigo_detectado = (datos_pieza.get("codigo") or "").strip()
                confianza = (datos_pieza.get("confianza") or "").strip().lower()

                if codigo_detectado:
                    st.success(f"**Código detectado: `{codigo_detectado}`** (confianza de la IA: {confianza or 's/d'})")
                    if confianza in ("media", "baja"):
                        st.caption(
                            "⚠️ La propia IA no está muy segura de haber leído bien el código — "
                            "confirmalo mirando la pieza antes de vender."
                        )
                else:
                    st.warning("No se distinguió ningún código legible en la foto.")
                if datos_pieza.get("marca_visible"):
                    st.caption(f"Marca visible en la pieza: {datos_pieza['marca_visible']}")
                if datos_pieza.get("tipo_pieza"):
                    st.caption(f"Tipo de pieza (según la IA): {datos_pieza['tipo_pieza']}")

                if codigo_detectado:
                    clean_foto = sanitizar(codigo_detectado)
                    res_foto = buscar_por_codigo(clean_foto) if clean_foto else []
                    if res_foto:
                        incrementar_veces_buscado(clean_foto)
                        st.success(f"✅ Coincidencia CONFIRMADA en tu catálogo — {len(res_foto)} resultado(s):")
                        st.caption(
                            "Esto es un match exacto por código, con las equivalencias que ya tenés "
                            "cargadas — no es una suposición de la IA."
                        )
                        st.dataframe(quitar_id(res_foto), width="stretch", hide_index=True)
                    else:
                        st.info(
                            f"El código `{codigo_detectado}` no coincide con nada cargado — puede que la "
                            "IA haya leído mal algún carácter, o que sea un código que todavía no tenés."
                        )
                        # Los que se escriben casi igual, primero los que solo difieren en lo que
                        # se confunde al leer. Ver es_confusion_de_lectura().
                        _parecidos_foto = codigos_por_tipeo(clean_foto, de_una_foto=True)
                        if _parecidos_foto:
                            mostrar_parecidos_de_una_lectura(codigo_detectado, _parecidos_foto)
                        if datos_pieza.get("tipo_pieza") and st.button("🔍 Buscar por el tipo de pieza en vez del código"):
                            st.session_state["buscar_tipo_pieza_click"] = True

                if (not codigo_detectado or (codigo_detectado and st.session_state.get("buscar_tipo_pieza_click"))) \
                        and datos_pieza.get("tipo_pieza"):
                    if not codigo_detectado:
                        mostrar_tipo = st.button("🔍 Buscar por el tipo de pieza")
                    else:
                        mostrar_tipo = True
                    if mostrar_tipo:
                        tipo_pieza_texto = datos_pieza["tipo_pieza"]
                        res_tipo = buscar_por_texto(tipo_pieza_texto)
                        busqueda_usada = tipo_pieza_texto
                        if not res_tipo:
                            # La frase completa no encontró nada — reintenta con menos palabras
                            # (más amplio), por si tus descripciones no usan las mismas palabras
                            # exactas que eligió la IA (ej: "rótula de suspensión" vs "ROTULA DERECHA").
                            palabras_tipo = tipo_pieza_texto.split()
                            for n in range(len(palabras_tipo) - 1, 0, -1):
                                intento = " ".join(palabras_tipo[:n])
                                res_tipo = buscar_por_texto(intento)
                                if res_tipo:
                                    busqueda_usada = intento
                                    break
                        if res_tipo:
                            if busqueda_usada != tipo_pieza_texto:
                                st.caption(
                                    f"No encontré nada con \"{tipo_pieza_texto}\" completo — probé de nuevo "
                                    f"solo con \"{busqueda_usada}\" y esto apareció (todavía menos preciso, "
                                    "revisá con más cuidado):"
                                )
                            if len(res_tipo) > 1:
                                st.warning(
                                    f"⚠️ Encontré {len(res_tipo)} pieza(s) parecida(s) por palabras clave — "
                                    "NINGUNA está confirmada como la exacta, es solo una búsqueda por texto. "
                                    "Si son piezas como rótulas, retenes, etc. que varían por modelo de auto, "
                                    "comparalas físicamente (o por medidas, en '📐 Buscar por medidas mecánicas') "
                                    "antes de vender la que sea."
                                )
                            else:
                                st.info(
                                    "Encontré 1 coincidencia por palabras clave — tampoco está confirmada, "
                                    "revisala antes de vender."
                                )
                            st.dataframe(quitar_id(res_tipo)[:15], width="stretch", hide_index=True)
                            if len(res_tipo) > 15:
                                st.caption(f"Mostrando las primeras 15 de {len(res_tipo)} coincidencias.")
                        else:
                            st.caption("No encontré nada parecido en la base por ese tipo de pieza.")

    historial = historial_reciente()
    if historial:
        st.caption("🕘 Búsquedas recientes:")
        cols_hist = st.columns(min(len(historial), 5))
        for i, termino in enumerate(historial[:5]):
            if cols_hist[i % 5].button(termino, key=f"sugerencia_hist_{i}_{termino}", width="stretch"):
                st.session_state["sugerencia_busqueda"] = termino
                st.rerun()

    favoritos = listar_favoritos()
    if favoritos:
        with st.expander(f"⭐ Favoritos ({len(favoritos)})"):
            for fila_fav in favoritos[:8]:
                colf1, colf2 = st.columns([4, 1])
                colf1.write(f"{fila_fav.get('Codigo') or ''} — {fila_fav.get('Marca') or ''}")
                if colf2.button("🔍", key=f"sugerencia_fav_{fila_fav['ID']}"):
                    st.session_state["sugerencia_busqueda"] = fila_fav.get("Codigo") or ""
                    st.rerun()
            st.dataframe(quitar_id(favoritos), width="stretch", hide_index=True)

    if not _guia_arriba:
        _guia_y_lo_que_espera_aprobacion()      # ver la función: para el mostrador va al final

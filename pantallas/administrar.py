"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/."""

# ============================================================
# ADMINISTRAR
# ============================================================
def exportar_configuracion_txt():
    """Junta combos de repuestos, códigos DTC cargados y fabricantes VIN en un solo archivo de texto,
    para respaldo aparte de la base completa o para copiarle la configuración a otra sucursal."""
    lineas = []
    lineas.append(f"# Exportación de configuración — Equivalencias El Chavo — {datetime.now():%d/%m/%Y %H:%M}")
    lineas.append("")

    lineas.append("## COMBOS DE REPUESTOS RELACIONADOS (disparador;item)")
    for combo in listar_combos():
        for item in combo["items"]:
            lineas.append(f"{combo['disparador']};{item}")
    lineas.append("")

    lineas.append("## CÓDIGOS DTC (codigo;descripcion;sistema;causas;fabricante — mismo formato que la carga masiva)")
    c.execute("SELECT codigo, descripcion, sistema, causas_posibles, fabricante FROM codigos_dtc ORDER BY fabricante, codigo")
    for row in c.fetchall():
        lineas.append(f"{row['codigo']};{row['descripcion']};{row['sistema'] or ''};{row['causas_posibles'] or ''};{row['fabricante'] or ''}")
    lineas.append("")

    lineas.append("## FABRICANTES POR WMI - lector de VIN (wmi;fabricante;pais)")
    for f in listar_fabricantes_vin():
        lineas.append(f"{f['WMI']};{f['Fabricante']};{f.get('País') or ''}")

    return "\n".join(lineas)


if pagina == PAGINAS[3]:
    st.subheader("🗂️ Administrar")

    SUB_ADMIN = ["🏷️ Marcas", "📦 Productos", "💬 Mensajería y cobros", "🧩 Combos", "🧹 Mantenimiento", "👥 Usuarios"]
    if st.session_state.get("sub_admin") not in SUB_ADMIN:
        st.session_state["sub_admin"] = SUB_ADMIN[0]
    # El mismo buscador que adentro de Mantenimiento, pero acá arriba: el que entra por primera
    # vez no tiene por qué saber que las 36 herramientas viven detrás de una solapa que se
    # llama «Mantenimiento». Escribiendo «papelera» o «fotos» llega igual.
    # Estando YA en Mantenimiento no: ahí está el de adentro, y se veían los dos seguidos en la
    # misma pantalla —mismo texto de ayuda, dos cajas— sin que se entendiera cuál usar.
    if st.session_state["sub_admin"] != "🧹 Mantenimiento":
        buscador_de_herramientas("buscar_herramienta_admin",
                                  "¿Qué querés hacer? (buscá entre las herramientas)")

    st.radio("Sub-sección:", SUB_ADMIN, key="sub_admin", horizontal=True,
             label_visibility="collapsed")
    sub_admin = st.session_state["sub_admin"]

    c.execute("""SELECT m.id, m.nombre, m.tipo, COUNT(p.id) AS productos,
                        COALESCE(m.url_ficha_template, '') AS plantilla
                 FROM marcas m LEFT JOIN productos p ON p.marca_id = m.id
                 GROUP BY m.id ORDER BY m.nombre""")
    marcas_info = c.fetchall()

    if sub_admin == SUB_ADMIN[0]:
        if not marcas_info:
            st.info("Todavía no hay marcas cargadas.")
        else:
            # La dirección del catálogo web va en la tabla y no escondida en el selector de
            # abajo: «ya cargué el catálogo de tal marca y no figura» se contesta mirando acá,
            # sin tener que elegir marca por marca en el desplegable para ver cuál la tiene.
            tabla_marcas = [{"Marca": m["nombre"], "Tipo": m["tipo"],
                             "Productos cargados": m["productos"],
                             "Catálogo web": (m["plantilla"][:48] + "…") if len(m["plantilla"]) > 48
                                             else (m["plantilla"] or "—")}
                             for m in marcas_info]
            st.dataframe(tabla_marcas, width="stretch", hide_index=True)

            st.markdown("---")
            st.markdown("**🔗 Link a la ficha del proveedor (en vez de guardar la foto)**")
            explicar(
                "Por cada marca/proveedor podés cargar un patrón de URL con `{codigo}` donde va el "
                "código del producto.",
                "La app arma el link automáticamente para cada resultado de búsqueda, sin copiar "
                "ninguna imagen — así podés sumar Taranto y cualquier otro proveedor que uses, cada uno "
                "con su propio patrón. Ejemplo: `https://www.taranto.com.ar/busqueda?q={codigo}`"
            )
            nombres_para_link = [m["nombre"] for m in marcas_info]
            marca_link = st.selectbox("Marca:", nombres_para_link, key="marca_link_ficha")
            id_marca_link = next(m["id"] for m in marcas_info if m["nombre"] == marca_link)
            template_actual = next((m["plantilla"] for m in marcas_info
                                    if m["id"] == id_marca_link), "")
            # La clave lleva el id de la marca. Con una sola clave para todas, Streamlit se
            # queda con lo último tipeado y el `value` no se vuelve a mirar: cambiabas de marca
            # y el campo seguía mostrando el patrón de la anterior —parecía cargado cuando no lo
            # estaba— y si apretabas Guardar le copiabas a esta marca la dirección de la otra.
            nuevo_template = st.text_input(
                "Patrón de URL (usá {codigo} donde va el código):", value=template_actual,
                placeholder="https://www.taranto.com.ar/busqueda?q={codigo}",
                key=f"input_template_link_{id_marca_link}"
            )
            if st.button("💾 Guardar patrón de link"):
                if nuevo_template.strip() and "{codigo}" not in nuevo_template:
                    st.warning("El patrón tiene que incluir '{codigo}' en algún lado, si no todos los links quedan iguales.")
                else:
                    with db_lock:
                        c.execute("UPDATE marcas SET url_ficha_template = ? WHERE id = ?",
                                  (nuevo_template.strip() or None, id_marca_link))
                        conn.commit()
                    avisar("success", f"Patrón de link guardado para '{marca_link}'.")
                    st.rerun()

            st.markdown("---")
            duplicadas = marcas_probablemente_duplicadas()
            if duplicadas:
                st.markdown("**🔎 Marcas que parecen ser la misma**")
                explicar(
                    "Detectadas por el nombre o porque comparten códigos.",
                    "Una lista viene como «MAHLE» y la siguiente como «MAHLE FILTER», o alguien "
                    "la tipeó distinto. Quedan como dos proveedores separados y el buscador deja "
                    "de encontrar equivalencias que en realidad existen.\n\nLa señal más fuerte "
                    "no es el nombre sino los **códigos compartidos**: si dos marcas tienen los "
                    "mismos códigos son el mismo proveedor, aunque se llamen distinto. Ese caso "
                    "no lo agarra ningún chequeo por nombre."
                )
                st.dataframe(quitar_id(duplicadas), width="stretch", hide_index=True)
                st.caption(
                    "Fusionalas abajo, poniendo como origen la que quieras eliminar. Los "
                    "productos que existan en las dos se juntan conservando precio, stock y "
                    "equivalencias."
                )
                st.markdown("---")

            st.markdown("**🔀 Fusionar marcas duplicadas**")
            st.caption(
                "Útil cuando una marca quedó cargada con nombres distintos por error de tipeo "
                "(ej: 'MANN' y 'MANN FILTER'). Mueve todos los productos de una a la otra."
            )
            nombres_para_fusion = [m["nombre"] for m in marcas_info]
            colOrig, colDest = st.columns(2)
            marca_origen = colOrig.selectbox("Marca a eliminar (origen):", nombres_para_fusion, key="fusion_origen")
            marca_destino = colDest.selectbox("Marca a conservar (destino):", nombres_para_fusion, key="fusion_destino")
            if candado('fusionar marcas', st.button("🔀 Fusionar", disabled=(marca_origen == marca_destino)), 'fusionar_marcas'):
                id_origen = next(m["id"] for m in marcas_info if m["nombre"] == marca_origen)
                id_destino = next(m["id"] for m in marcas_info if m["nombre"] == marca_destino)
                movidos, fusionados = fusionar_marcas(id_origen, id_destino)
                detalle = f"{movidos} producto(s) movidos"
                if fusionados:
                    detalle += (f" y {fusionados} fusionados con los que ya existían "
                                 "en la marca destino con el mismo código")
                avisar("success", f"'{marca_origen}' se fusionó dentro de '{marca_destino}': "
                                   f"{detalle}.")
                invalidar_salud()
                st.rerun()

            st.markdown("---")
            st.markdown("**💲 Aumentar/bajar precios por porcentaje**")
            st.caption("Aplica el ajuste a todos los productos con precio cargado de la marca elegida.")
            marca_precio = st.selectbox("Marca:", nombres_para_fusion, key="marca_ajuste_precio")
            porcentaje = st.number_input("Porcentaje (usá negativo para bajar, ej: -5):", value=0.0, step=1.0)
            if candado('ajustar precios masivamente', st.button("💲 Aplicar ajuste de precios", disabled=(porcentaje == 0)), 'ajustar_precios_masivamente'):
                id_marca_precio = next(m["id"] for m in marcas_info if m["nombre"] == marca_precio)
                afectados = aumentar_precios_por_marca(id_marca_precio, porcentaje)
                st.success(f"Se ajustaron {afectados} precio(s) de '{marca_precio}' en {porcentaje:+.1f}%.")

            st.markdown("---")
            st.markdown("**Eliminar una marca** (borra también sus productos y equivalencias asociadas)")
            marca_a_borrar = st.selectbox("Elegí una marca", [m["nombre"] for m in marcas_info])
            confirmar = st.checkbox(f"Confirmo que quiero borrar '{marca_a_borrar}' y todo lo asociado")
            if candado('eliminar una marca', st.button("🗑️ Eliminar marca", disabled=not confirmar), 'eliminar_una_marca'):
                eliminar_marca_con_papelera(marca_a_borrar)
                avisar("success", f"Marca '{marca_a_borrar}' eliminada (podés restaurarla desde la papelera).")
                st.rerun()

        st.markdown("**Catálogos externos**")
        st.caption("Agregá los sitios de proveedores que querés que aparezcan como botones al buscar un código.")

        catalogos = listar_catalogos_externos()
        if catalogos:
            for cat in catalogos:
                colA, colB, colC = st.columns([2, 5, 1])
                colA.write(cat["nombre"])
                colB.write(cat["url"])
                if candado('borrar un catálogo externo', colC.button("🗑️", key=f"del_cat_{cat['id']}"), 'borrar_un_cat_logo_externo'):
                    eliminar_catalogo_externo(cat["id"])
                    st.rerun()
        else:
            st.caption("Todavía no agregaste ningún catálogo externo.")

        with st.form("nuevo_catalogo", clear_on_submit=True):
            colN, colU = st.columns(2)
            nombre_cat = colN.text_input("Nombre del proveedor", placeholder="Ej: Wega")
            url_cat = colU.text_input("URL del catálogo", placeholder="Ej: wegamotors.com")
            agregar = st.form_submit_button("➕ Agregar catálogo")
            if agregar:
                if not nombre_cat.strip() or not url_cat.strip():
                    st.warning("Completá nombre y URL.")
                else:
                    agregar_catalogo_externo(nombre_cat, url_cat)
                    avisar("success", f"'{nombre_cat}' agregado.")
                    st.rerun()

    if sub_admin == SUB_ADMIN[1]:
        # Antes del formulario manual: lo que ya se puede leer de las descripciones.
        # Cargar medidas a mano, una por una, no lo hace nadie con 20.000 productos; y
        # sin medidas cargadas el veto por medidas —la única prueba física que tiene el
        # sistema— no se usa nunca.
        with st.expander("🪄 Leer medidas de las descripciones"):
            explicar(
                "En retenes, rulemanes y bujes la medida ya está escrita en la "
                "descripción. Esto la lee y completa los campos vacíos.",
                "Solo lee lo que no tiene otra interpretación posible: los tres números "
                "seguidos (35x52x7 = interno, externo, ancho), las estrías y el paso de "
                "rosca. Dos números sueltos NO se leen: en un o'ring «20x2.5» es "
                "diámetro por espesor del cordón, no interno por externo, y cargarlo mal "
                "sería peor que no cargarlo.\n\n**Nunca pisa lo que cargaste a mano**: "
                "solo completa campos vacíos.\n\nPara qué sirve: las medidas son la "
                "única prueba física del sistema. Si dos piezas miden distinto, el "
                "vínculo se veta por más que una lista diga que equivalen. Esto no suma "
                "equivalencias — saca las falsas.",
                en_expander=True
            )
            if st.button("🔍 Ver qué se podría completar", key="btn_ver_medidas_desc"):
                st.session_state["medidas_deducidas"] = productos_con_medidas_deducibles()
            _deduc = st.session_state.get("medidas_deducidas")
            if _deduc is not None:
                if not _deduc:
                    st.info("No encontré medidas legibles en las descripciones que "
                            "tengan los campos vacíos.")
                else:
                    st.success(f"Se pueden completar **{len(_deduc)} producto(s)**. "
                               "Revisá la muestra antes de aplicar:")
                    st.dataframe(
                        [{k: v for k, v in f.items() if not k.startswith("_")}
                         for f in _deduc[:50]],
                        width="stretch", hide_index=True)
                    if st.button("✅ Completar esas medidas", type="primary",
                                  key="btn_aplicar_medidas_desc"):
                        _n = aplicar_medidas_deducidas(_deduc)
                        st.session_state.pop("medidas_deducidas", None)
                        avisar("success", f"Se completaron las medidas de {_n} producto(s).")
                        st.rerun()
        st.markdown("**Buscar y editar un producto puntual**")
        texto_prod = st.text_input("Buscar producto por código o descripción", key="admin_buscar")
        if texto_prod.strip():
            res_admin = buscar_por_texto(texto_prod)
            if not res_admin:
                clean_admin = sanitizar(texto_prod)
                if clean_admin:
                    res_admin = buscar_por_codigo(clean_admin)
            if res_admin:
                st.dataframe(res_admin, width="stretch", hide_index=True)
                st.caption(
                    "¿Necesitás borrar un producto? Está en '🧹 Mantenimiento' → separado a propósito "
                    "de la edición, para que un descuido acá no borre nada."
                )

                st.markdown("**📐 Cargar medidas mecánicas / ubicación en depósito**")
                opciones_prod = {f"{f['Codigo']} ({f['Marca']}) — ID {f['ID']}": f['ID'] for f in res_admin}
                elegido_label = st.selectbox("Elegí el producto a editar:", list(opciones_prod.keys()), key="sel_medidas")
                id_medidas = opciones_prod[elegido_label]
                c.execute(
                    "SELECT diametro_interno, diametro_externo, ancho, paso_rosca, cantidad_estrias, ubicacion, "
                    "estrias_internas, estrias_externas, posicion_seguro, tiene_abs, "
                    "diametro_interno_cara_b, diametro_externo_cara_b, "
                    "diametro_rosca_homocinetica, diametro_copa, diametro_copa_superior, largo_total "
                    "FROM productos WHERE id = ?", (id_medidas,)
                )
                actual = c.fetchone()
                em1, em2, em3 = cols(3)
                e_diam_int = em1.number_input("Diám. interno cara A (mm)", min_value=0.0, step=0.1,
                                               value=float(actual["diametro_interno"] or 0), key="e_di")
                e_diam_ext = em2.number_input("Diám. externo cara A (mm)", min_value=0.0, step=0.1,
                                               value=float(actual["diametro_externo"] or 0), key="e_de")
                e_ancho = em3.number_input("Ancho (mm)", min_value=0.0, step=0.1,
                                            value=float(actual["ancho"] or 0), key="e_an")
                em4, em5, em6 = cols(3)
                e_paso = em4.text_input("Paso de rosca", value=actual["paso_rosca"] or "", key="e_paso")
                e_estrias = em5.number_input("Cantidad de estrías", min_value=0, step=1,
                                              value=int(actual["cantidad_estrias"] or 0), key="e_estrias")
                e_ubicacion = em6.text_input("Ubicación en depósito", value=actual["ubicacion"] or "",
                                              placeholder="Ej: Pasillo 3, estante B", key="e_ubic")

                st.markdown("**↔️ Segunda cara (opcional)**")
                st.caption(
                    "Para piezas con distinta medida de cada lado — retenes con labio interior/exterior "
                    "escalonado, tensores con el interior de un diámetro de un lado y otro del otro, etc."
                )
                eb1, eb2 = st.columns(2)
                e_diam_int_b = eb1.number_input("Diám. interno cara B (mm)", min_value=0.0, step=0.1,
                                                 value=float(actual["diametro_interno_cara_b"] or 0), key="e_di_b")
                e_diam_ext_b = eb2.number_input("Diám. externo / labio exterior cara B (mm)", min_value=0.0, step=0.1,
                                                 value=float(actual["diametro_externo_cara_b"] or 0), key="e_de_b")

                st.markdown("**🔩 Homocinéticas**")
                eh1, eh2 = st.columns(2)
                e_estrias_int = eh1.number_input("Estrías internas", min_value=0, step=1,
                                                  value=int(actual["estrias_internas"] or 0), key="e_estrias_int")
                e_estrias_ext = eh2.number_input("Estrías externas", min_value=0, step=1,
                                                  value=int(actual["estrias_externas"] or 0), key="e_estrias_ext")
                eh3, eh4 = st.columns(2)
                e_seguro = eh3.text_input("Posición del seguro", value=actual["posicion_seguro"] or "",
                                           placeholder="Ej: 1er ranura, a 12mm", key="e_seguro")
                abs_actual = "Cualquiera" if actual["tiene_abs"] is None else ("Sí" if actual["tiene_abs"] else "No")
                e_abs = eh4.selectbox("¿Tiene ABS?", ["Cualquiera", "Sí", "No"],
                                       index=["Cualquiera", "Sí", "No"].index(abs_actual), key="e_abs")
                eh5, eh6 = st.columns(2)
                e_rosca_homo = eh5.number_input("Diámetro de rosca (mm)", min_value=0.0, step=0.1,
                                                 value=float(actual["diametro_rosca_homocinetica"] or 0), key="e_rosca_homo")
                e_largo_total = eh6.number_input(
                    "Largo total (mm)", min_value=0.0, step=0.5,
                    value=float(actual["largo_total"] or 0), key="e_largo_total",
                    help="De punta a punta. Es la medida que más rápido descarta: dos homocinéticas "
                         "con las mismas estrías y la misma copa pero distinto largo no entran en "
                         "el mismo auto."
                )
                explicar(
                    "La copa es cónica, así que se cargan sus dos diámetros:",
                    "el de la **base** (donde se une al eje) y el de la **boca** (el borde abierto). Con "
                    "uno solo no se distinguen dos copas que arrancan igual y terminan distinto — y son "
                    "justo esas las que no se pueden intercambiar."
                )
                eh7, eh8 = st.columns(2)
                e_copa = eh7.number_input("Diám. copa — base (mm)", min_value=0.0, step=0.1,
                                           value=float(actual["diametro_copa"] or 0), key="e_copa")
                e_copa_sup = eh8.number_input("Diám. copa — boca / superior (mm)", min_value=0.0, step=0.1,
                                               value=float(actual["diametro_copa_superior"] or 0),
                                               key="e_copa_sup")

                if st.button("💾 Guardar medidas y ubicación"):
                    actualizar_medidas(id_medidas, e_diam_int, e_diam_ext, e_ancho, e_paso, e_estrias, e_ubicacion,
                                        e_estrias_int, e_estrias_ext, e_seguro, e_abs,
                                        e_diam_int_b, e_diam_ext_b, e_rosca_homo, e_copa,
                                        e_copa_sup, e_largo_total)
                    st.success("Guardado.")

                st.markdown("**📷 Fotos del producto**")
                explicar(
                    "Cargá varias del mismo producto, y cuanto más distintas entre sí, mejor.",
                    "De frente, de costado, la de la ficha del proveedor. Ninguna comparación "
                    "reconoce una pieza de frente en una foto sacada de costado, así que la única "
                    "forma de cubrir los dos ángulos es tener los dos."
                )

                fotos_actuales = listar_fotos_producto(id_medidas)
                if fotos_actuales:
                    etiquetas_estado = {
                        "ok": "🟢 lista para comparar",
                        "sin_detalle": "🟡 se ve, pero no sirve para comparar",
                        "error": "🔴 no se pudo procesar",
                    }
                    columnas_fotos = st.columns(min(len(fotos_actuales), 4))
                    for idx_f, foto in enumerate(fotos_actuales):
                        with columnas_fotos[idx_f % len(columnas_fotos)]:
                            st.image(foto["imagen_data"], width="stretch")
                            st.caption(etiquetas_estado.get(foto["estado"], "⚪ sin procesar"))
                            if st.button("🗑️", key=f"del_foto_{foto['id']}", help="Borrar esta foto"):
                                eliminar_foto_producto(foto["id"])
                                st.rerun()
                else:
                    st.caption("Todavía sin fotos.")

                origen_foto_nueva = st.radio(
                    "Agregar una foto:", ["📷 Subir", "🔗 Desde una dirección web"],
                    horizontal=True, key="origen_foto_producto"
                )

                if origen_foto_nueva.startswith("📷"):
                    foto_producto = subir_archivo(
                        "Foto (se guarda comprimida y aparece en la columna 'Imagen' del buscador):",
                        ["png", "jpg", "jpeg"], "foto_producto"
                    )
                    producto_foto_ok = archivo_listo(foto_producto, "foto")
                    if foto_producto:
                        boton_otro_archivo("foto_producto", "🗑️ Usar otra foto", key="otra_foto_producto")
                    if st.button("💾 Agregar esta foto", disabled=not producto_foto_ok):
                        _, estado_foto = agregar_foto_producto(id_medidas, foto_producto.getvalue())
                        if estado_foto == "ok":
                            st.success("Foto agregada y lista para la búsqueda por parecido.")
                        elif estado_foto == "sin_detalle":
                            st.warning(
                                "Foto agregada — se va a ver en el buscador, pero **no sirve para "
                                "comparar por parecido**: no tiene detalles distintivos suficientes "
                                "(pieza lisa, fondo del mismo tono, poca luz o movida). Para que "
                                "sirva, sacala apoyada sobre un fondo liso de OTRO color, con buena "
                                "luz, y que se lea el grabado o la marca de la pieza."
                            )
                        else:
                            st.error("No se pudo procesar esa imagen. Probá con otra.")
                        olvidar_archivo("foto_producto")
                        st.rerun()
                else:
                    st.caption(
                        "Pegá la dirección de la ficha del proveedor o la de la imagen directa. Se "
                        "bajan las fotos de esa página y elegís cuáles guardar."
                    )
                    url_foto_prod = st.text_input(
                        "Dirección web:", placeholder="https://...", key="url_foto_producto"
                    ).strip()
                    if st.button("⬇️ Traer fotos de esa dirección", disabled=not url_foto_prod,
                                 key="btn_traer_fotos_prod"):
                        with st.spinner("Bajando..."):
                            halladas, error_ph = imagenes_de_una_direccion(url_foto_prod)
                        if error_ph:
                            st.error(error_ph)
                            st.session_state.pop("fotos_url_producto", None)
                        else:
                            st.session_state["fotos_url_producto"] = halladas
                            st.rerun()

                    halladas = st.session_state.get("fotos_url_producto")
                    if halladas:
                        st.caption(f"{len(halladas)} foto(s) encontradas — guardá las que sean de la pieza:")
                        cols_ph = st.columns(min(len(halladas), 4))
                        for idx_h, (url_h, datos_h) in enumerate(halladas[:8]):
                            with cols_ph[idx_h % len(cols_ph)]:
                                st.image(datos_h, width="stretch")
                                if st.button("💾 Guardar", key=f"guardar_foto_url_{idx_h}"):
                                    _, est_h = agregar_foto_producto(
                                        id_medidas, datos_h, origen="url", fuente=url_h
                                    )
                                    if est_h == "ok":
                                        st.success("Guardada y lista para comparar.")
                                    elif est_h == "sin_detalle":
                                        st.warning("Guardada, pero sin detalle suficiente para comparar.")
                                    else:
                                        st.error("No se pudo procesar esa imagen.")
                                    st.rerun()
                        if st.button("✖️ Cerrar estas fotos", key="cerrar_fotos_url_prod"):
                            st.session_state.pop("fotos_url_producto", None)
                            st.rerun()

                if fotos_actuales and st.button("🗑️ Sacar TODAS las fotos de este producto"):
                    eliminar_imagen_producto(id_medidas)
                    avisar("success", "Fotos eliminadas.")
                    st.rerun()
            else:
                st.info("Sin resultados.")

        st.markdown("**🧩 Productos sin equivalencias**")
        st.caption(
            "Esta sección puede ser pesada, así que se calcula solo cuando la pedís (no en cada búsqueda)."
        )

        if "mostrar_huerfanos" not in st.session_state:
            st.session_state.mostrar_huerfanos = False

        col_ver, col_ocultar = st.columns(2)
        if col_ver.button("📋 Mostrar productos sin equivalencias"):
            st.session_state.mostrar_huerfanos = True
            st.rerun()
        if st.session_state.mostrar_huerfanos and col_ocultar.button("🙈 Ocultar"):
            st.session_state.mostrar_huerfanos = False
            st.rerun()

        if st.session_state.mostrar_huerfanos:
            total_sin_eq = contar_huerfanos()
            st.write(f"Total: **{total_sin_eq}** producto(s) sin ninguna equivalencia.")

            if total_sin_eq == 0:
                st.info("¡Todos los productos tienen al menos una equivalencia! 🎉")
            else:
                c.execute("SELECT nombre FROM marcas ORDER BY nombre")
                marcas_para_filtro = ["Todas"] + [r["nombre"] for r in c.fetchall()]
                marca_filtro_huerfanos = st.selectbox("Filtrar por marca:", marcas_para_filtro, key="filtro_huerfanos")
                cantidad_mostrar = st.selectbox("Mostrar en pantalla:", [25, 50, 100], index=0,
                                                 help="La descarga en Excel siempre incluye todo, esto es solo lo que se dibuja en pantalla.")

                # Sin tope: el botón de al lado dice «Descargar lista completa» y con 2.000
                # sobre 34.457 huérfanos esa lista no era completa. Traerlos todos: 0,1 s.
                pendientes_completo = listar_productos_sin_equivalencias(
                    marca_filtro_huerfanos, limite=None)
                if pendientes_completo:
                    st.download_button(
                        "⬇️ Descargar lista completa (Excel)",
                        data=to_excel_bytes(quitar_id(pendientes_completo)),
                        file_name="productos_sin_equivalencias.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    pendientes = pendientes_completo[:cantidad_mostrar]
                    st.caption(f"Mostrando {len(pendientes)} de {len(pendientes_completo)}.")
                    for fila in pendientes:
                        colC, colM, colB = st.columns([3, 2, 1.2])
                        colC.write(f"{fila['Codigo']}" + (f" — {fila['Descripcion']}" if fila.get('Descripcion') else ""))
                        colM.write(fila['Marca'])
                        if colB.button("🔗 Usar", key=f"usar_huerfano_{fila['ID']}"):
                            st.session_state["vincular_pendiente"] = {
                                "cod_a": fila["Codigo"],
                                "marca_a": fila["Marca"],
                                "desc_a": fila.get("Descripcion") or ""
                            }
                            avisar("success", "Cargado. Andá a la pestaña '🔗 Vincular manual' para completar el Código B.")
                            st.rerun()
                else:
                    st.info("Sin resultados para esa marca.")

    if sub_admin == SUB_ADMIN[2]:
        st.markdown("**💬 Texto del mensaje de WhatsApp**")
        st.caption(
            "Personalizá el encabezado y el pie del mensaje que se arma en 'Lista WhatsApp' — por "
            "ejemplo para poner el nombre real de tu local, un teléfono de contacto, horarios, etc."
        )
        encabezado_actual = obtener_config("whatsapp_encabezado", "🔧 *Equivalencias El Chavo*")
        pie_actual = obtener_config("whatsapp_pie", "")
        nuevo_encabezado = st.text_input("Encabezado del mensaje:", value=encabezado_actual, key="wa_encabezado_in")
        nuevo_pie = st.text_area("Pie del mensaje (opcional):", value=pie_actual, key="wa_pie_in",
                                  placeholder="Ej: 📍 Av. Siempreviva 742 - Horario: L a V 9 a 18hs")
        if candado('cambiar los textos que salen en los mensajes', st.button("💾 Guardar textos del mensaje"), 'cambiar_los_textos_que_salen_en_lo'):
            guardar_config("whatsapp_encabezado", nuevo_encabezado.strip() or "🔧 *Equivalencias El Chavo*")
            guardar_config("whatsapp_pie", nuevo_pie.strip())
            avisar("success", "Guardado.")
            st.rerun()

        st.markdown("---")
        st.markdown("**💳 Alias para QR de transferencia**")
        explicar(
            "Cargá los alias/CBU que usás (Mercado Pago, distintos bancos, etc.).",
            "Al armar una cotización en 'Lista WhatsApp' vas a poder elegir cuál de estos usar para "
            "el QR del PDF. Si subís el QR real que te da tu banco/Mercado Pago/MODO, se usa ese "
            "(funciona de verdad para transferir). Si no subís nada, se genera uno con el alias/CBU "
            "como texto plano — sirve para no tipear a mano, pero no lo van a reconocer como QR de "
            "pago."
        )
        alias_cargados = listar_alias_transferencia()
        if alias_cargados:
            st.dataframe(
                [{k: v for k, v in a.items() if k not in ("ID", "TieneQrReal")} | {"QR real": "✅" if a["TieneQrReal"] else "—"}
                 for a in alias_cargados],
                width="stretch", hide_index=True
            )

        opciones_alias_edit = ["➕ Nuevo alias..."] + [f"{a['Nombre']} (editar)" for a in alias_cargados]
        alias_opcion_edit = st.selectbox("Elegí qué hacer:", opciones_alias_edit, key="alias_opcion_edit")
        alias_actual = None
        if alias_opcion_edit != "➕ Nuevo alias...":
            nombre_buscar = alias_opcion_edit.replace(" (editar)", "")
            alias_actual = next(a for a in alias_cargados if a["Nombre"] == nombre_buscar)

        cae1, cae2 = st.columns(2)
        nombre_alias_in = cae1.text_input("Nombre (ej: Mercado Pago, Banco Galicia)",
                                           value=(alias_actual or {}).get("Nombre", ""), key="alias_nombre_in")
        alias_in = cae2.text_input("Alias", value=(alias_actual or {}).get("Alias", ""), key="alias_alias_in")
        cae3, cae4 = st.columns(2)
        cbu_in = cae3.text_input("CBU/CVU (opcional)", value=(alias_actual or {}).get("CBU", ""), key="alias_cbu_in")
        titular_in = cae4.text_input("Titular (opcional)", value=(alias_actual or {}).get("Titular", ""), key="alias_titular_in")

        archivo_qr_real = subir_archivo(
            "QR real (opcional — el que te dio tu banco/Mercado Pago/MODO):",
            ["png", "jpg", "jpeg"], "qr_real"
        )
        if archivo_qr_real:
            archivo_listo(archivo_qr_real, "QR")
            boton_otro_archivo("qr_real", "🗑️ Usar otro QR", key="otro_qr_real")
        if alias_actual and alias_actual["TieneQrReal"]:
            st.caption("✅ Este alias ya tiene un QR real cargado. Subí uno nuevo para reemplazarlo.")

        cbtn1, cbtn2, cbtn3 = st.columns(3)
        if cbtn1.button("💾 Guardar alias"):
            if not nombre_alias_in.strip() or not alias_in.strip():
                st.warning("Completá al menos el nombre y el alias.")
            else:
                guardar_alias_transferencia(
                    nombre_alias_in, alias_in, cbu_in, titular_in,
                    alias_id=(alias_actual["ID"] if alias_actual else None),
                    qr_real_bytes=(archivo_qr_real.getvalue() if archivo_qr_real else None)
                )
                avisar("success", "Alias guardado.")
                st.rerun()
        if candado('sacar el QR de cobro', alias_actual and alias_actual["TieneQrReal"] and cbtn2.button("🗑️ Sacar el QR real"), 'sacar_el_qr_de_cobro'):
            eliminar_qr_real(alias_actual["ID"])
            avisar("success", "QR real eliminado — vuelve a usar el de texto plano.")
            st.rerun()
        if candado('eliminar los datos de cobro', alias_actual and cbtn3.button("🗑️ Eliminar este alias"), 'eliminar_los_datos_de_cobro'):
            eliminar_alias_transferencia(alias_actual["ID"])
            avisar("success", "Alias eliminado.")
            st.rerun()

    if sub_admin == SUB_ADMIN[3]:
        st.markdown("**🧩 Combos de repuestos relacionados**")
        st.caption(
            "Cuando alguien busca un producto cuya descripción contenga el 'disparador', la app va a "
            "sugerir estos ítems relacionados con un botón para buscarlos también. Ej: disparador "
            "'correa de distribucion' → ítems 'Kit de distribución', 'Tensor', 'Bomba de agua'."
        )
        combos_actuales = listar_combos()
        if combos_actuales:
            st.dataframe(
                [{"Disparador": c_["disparador"], "Ítems sugeridos": ", ".join(c_["items"])} for c_ in combos_actuales],
                width="stretch", hide_index=True
            )
        disparador_edit = st.text_input(
            "Disparador (palabra/frase que aparece en la descripción del producto):",
            placeholder="Ej: correa de distribucion", key="combo_disparador"
        )
        items_edit = st.text_area(
            "Ítems sugeridos (uno por línea):",
            placeholder="Kit de distribución\nTensor de distribución\nBomba de agua",
            key="combo_items", height=100
        )
        cc1, cc2 = st.columns(2)
        if cc1.button("💾 Guardar combo"):
            if not disparador_edit.strip() or not items_edit.strip():
                st.warning("Completá el disparador y al menos un ítem.")
            else:
                guardar_combo(disparador_edit, items_edit.strip().splitlines())
                avisar("success", f"Combo para '{disparador_edit.strip()}' guardado.")
                st.rerun()
        if candado('eliminar un combo', cc2.button("🗑️ Eliminar combo (según el disparador de arriba)"), 'eliminar_un_combo'):
            eliminar_combo(disparador_edit)
            avisar("success", f"Combo para '{disparador_edit.strip()}' eliminado.")
            st.rerun()

    if sub_admin == SUB_ADMIN[4]:
        st.markdown("**🗑️ Eliminar un producto puntual**")
        st.caption(
            "Separado a propósito de la edición de medidas/fotos, para que buscar y editar un producto "
            "no te deje el botón de borrar a mano por accidente."
        )
        texto_prod_borrar = st.text_input("Buscar el producto a borrar (por código o descripción):", key="mant_buscar_borrar")
        if texto_prod_borrar.strip():
            res_borrar = buscar_por_texto(texto_prod_borrar)
            if not res_borrar:
                clean_borrar = sanitizar(texto_prod_borrar)
                if clean_borrar:
                    res_borrar = buscar_por_codigo(clean_borrar)
            if res_borrar:
                opciones_borrar = {f"{f['Codigo']} ({f['Marca']}) — ID {f['ID']}": f['ID'] for f in res_borrar}
                elegido_borrar_label = st.selectbox("Elegí el producto a eliminar:", list(opciones_borrar.keys()),
                                                     key="mant_sel_borrar")
                id_a_borrar = opciones_borrar[elegido_borrar_label]
                st.caption(
                    "Se borran también sus equivalencias con otros productos, pero quedan "
                    "guardadas con él en la papelera: si lo restaurás, vuelve **con** sus vínculos."
                )
                confirmar_borrado = st.checkbox(f"Confirmo que quiero borrar '{elegido_borrar_label}'",
                                                 key="mant_confirmar_borrar")
                if candado('eliminar un producto', st.button("🗑️ Eliminar producto", disabled=not confirmar_borrado), 'eliminar_un_producto'):
                    _n_vinc = borrar_producto_con_papelera(id_a_borrar)
                    avisar("success", "Producto eliminado. Podés restaurarlo desde la papelera, "
                                      f"más abajo, con sus {_n_vinc or 0} vínculo(s).")
                    st.rerun()
            else:
                st.caption("Sin resultados.")

        st.markdown("---")
        # Mantenimiento quedó con 15 herramientas apiladas en un solo scroll interminable.
        # Se agrupan por lo que uno viene a hacer, no por el orden en que se fueron sumando:
        # así se entra directo a lo que se necesita en vez de bajar buscándolo.
        # Un selector guardado en la sesión, NO st.tabs. Dos motivos, los dos se veían:
        #   · st.tabs no recuerda en qué pestaña estabas: cada vez que apretás un botón la
        #     página se vuelve a dibujar y volvés a la primera. Con las pantallas de
        #     mantenimiento, donde uno aprieta un botón tras otro, eso es insoportable —
        #     «cada vez que aprieto una opción me manda para atrás».
        #   · el título de cada pestaña era g[0], o sea el PRIMER CARÁCTER del nombre: se
        #     veían cuatro emojis sueltos («🧹 🧠 📷 🩺») en vez de los nombres.
        # Es el mismo cambio que ya se había hecho en la navegación principal, por lo mismo.
        if st.session_state.get("sub_mantenimiento") not in GRUPOS_MANTENIMIENTO:
            st.session_state["sub_mantenimiento"] = GRUPOS_MANTENIMIENTO[0]
        # Va antes del selector de grupo porque resuelve lo que ningún grupo resuelve: sabés
        # qué querés hacer y no te acordás en cuál estaba.
        buscador_de_herramientas("buscar_herramienta")

        st.radio("Grupo:", GRUPOS_MANTENIMIENTO, key="sub_mantenimiento", horizontal=True,
                 label_visibility="collapsed")
        _grupo_mant = st.session_state["sub_mantenimiento"]

        # EL ÍNDICE DEL GRUPO. Dice QUÉ HAY antes de bajar a buscarlo, que es lo que convierte
        # un scroll largo en una lista que se lee de un vistazo. Y la línea de al lado de cada
        # nombre es lo que hace que la pantalla se explique sola: sin eso, «🧯 Puentes que hoy
        # ya no se generarían» solo lo entiende el que lo programó.
        _del_grupo = herramientas_del_grupo(GRUPOS_MANTENIMIENTO.index(_grupo_mant))
        if _del_grupo:
            st.caption(f"{len(_del_grupo)} herramienta(s) en este grupo:")
            _cols_ind = st.columns(2)
            for _i, (_t, _g, _q, _) in enumerate(_del_grupo):
                _cols_ind[_i % 2].markdown(
                    f"**{_t}**  \n<span style='opacity:.7;font-size:.85em'>"
                    f"{texto_para_html(_q)}</span>", unsafe_allow_html=True)
            st.markdown("---")

        if _grupo_mant == GRUPOS_MANTENIMIENTO[1]:
            st.markdown("**🌉 Códigos puente — los que rompen la búsqueda**")
            explicar(
                "Códigos vinculados a demasiadas cosas. Cortar uno limpia miles de resultados falsos.",
                "La búsqueda encadena: trae los equivalentes de tu código, y los de esos, y así. "
                "Un código mal vinculado no ensucia solo su fila: **fusiona todas las familias que "
                "toca**.\n\nUn filtro legítimo puede tener 10 o 15 equivalencias entre marcas. Si "
                "aparece con 200, casi seguro se cargó mal y quedó de puente entre repuestos que no "
                "tienen nada que ver."
            )
            st.session_state.setdefault("minimo_puente", 15)
            minimo_puente = st.select_slider(
                "Mostrar los que tengan más de:", options=[15, 30, 50, 100, 200],
                key="minimo_puente"
            )
            puentes = codigos_puente(int(minimo_puente))
            if puentes:
                st.warning(f"⚠️ {len(puentes)} código(s) con más de {minimo_puente} vínculos.")
                st.caption(
                    "Mirá la columna «Marcas distintas»: un repuesto real se vincula con unas pocas "
                    "marcas. Uno que toca 20 marcas distintas casi nunca es legítimo."
                )
                st.dataframe(puentes, width="stretch", hide_index=True)
                st.caption(
                    "Si alguno de estos está bien —hay repuestos que legítimamente equivalen a "
                    "decenas—, aprobalo y deja de aparecer acá y en el aviso del buscador."
                )
                cod_aprobar = st.text_input("Código a APROBAR (está bien así):",
                                             key="cod_aprobar_puente").strip()
                if cod_aprobar:
                    c.execute("SELECT id, codigo_raw, descripcion FROM productos WHERE codigo_clean = ?",
                              (sanitizar(cod_aprobar),))
                    obj_ap = c.fetchone()
                    if not obj_ap:
                        st.error("No encontré ese código.")
                    else:
                        nota_ap = st.text_input("Nota (opcional):", key="nota_aprobar_puente",
                                                 placeholder="Ej: filtro común, va en toda la gama")
                        if st.button(f"✅ Aprobar {obj_ap['codigo_raw']} — sus vínculos están bien"):
                            aprobar_puente(obj_ap["id"], nota_ap)
                            invalidar_salud()
                            avisar("success", f"{obj_ap['codigo_raw']} quedó aprobado: no vuelve a "
                                               "aparecer como código puente.")
                            st.rerun()

                aprobados = puentes_aprobados_ids()
                if aprobados:
                    c.execute(f"""SELECT p.codigo_raw AS "Código", p.descripcion AS "Descripción",
                                         pa.nota AS "Nota", substr(pa.fecha,1,10) AS "Aprobado el",
                                         p.id AS "_id"
                                  FROM puentes_aprobados pa JOIN productos p ON p.id = pa.producto_id
                                  ORDER BY pa.fecha DESC""")
                    lista_ap = filas_a_listas(c)
                    with st.expander(f"✅ Códigos puente aprobados ({len(lista_ap)})"):
                        st.dataframe(quitar_id(lista_ap), width="stretch", hide_index=True)
                        quitar_ap = st.text_input("Código a desaprobar (volver a vigilarlo):",
                                                   key="cod_desaprobar").strip()
                        if quitar_ap and st.button("↩️ Volver a vigilarlo"):
                            c.execute("SELECT id FROM productos WHERE codigo_clean = ?",
                                      (sanitizar(quitar_ap),))
                            f_des = c.fetchone()
                            if f_des and desaprobar_puente(f_des["id"]):
                                invalidar_salud()
                                avisar("success", f"{quitar_ap} vuelve a vigilarse.")
                                st.rerun()
                            else:
                                st.warning("No estaba aprobado.")

                cod_cortar = st.text_input(
                    "Código al que cortarle TODOS los vínculos:", key="cod_cortar_puente",
                    help="El producto no se borra: queda en la base con su precio y su stock. Lo único "
                         "que se corta son las equivalencias, que es lo que está mal."
                ).strip()
                if cod_cortar:
                    clean_cortar = sanitizar(cod_cortar)
                    c.execute("SELECT id, codigo_raw, descripcion FROM productos WHERE codigo_clean = ?",
                              (clean_cortar,))
                    objetivo = c.fetchone()
                    if not objetivo:
                        st.error("No encontré ese código.")
                    else:
                        red = tamano_de_la_red(objetivo["id"])
                        st.info(f"**{objetivo['codigo_raw']}** — {objetivo['descripcion'] or 'sin descripción'}. "
                                 f"Hoy está encadenado con {red}{'+' if red >= 500 else ''} producto(s).")
                        if candado('cortar vínculos', st.button(f"✂️ Cortar todos los vínculos de {objetivo['codigo_raw']}"), 'cortar_v_nculos_3'):
                            n = cortar_vinculos_de(objetivo["id"])
                            invalidar_salud()
                            avisar("success", f"Se cortaron {n} vínculo(s). El producto quedó en la base.")
                            st.rerun()
            else:
                st.caption(f"✅ Ningún código con más de {minimo_puente} vínculos.")
            # LOS QUE QUEDARON DE ANTES. Cada vez que se le enseña a la app a reconocer un
            # modelo o un motor, queda atrás una camada de códigos generados con las reglas
            # viejas que nadie vuelve a revisar. Arreglar el extractor evita los que vienen;
            # esto encuentra los que ya están, sin inventar ningún criterio: les da la vuelta y
            # los pasa por el mismo extractor de hoy.
            st.markdown("**🧯 Puentes que hoy ya no se generarían**")
            explicar(
                "Códigos de fábrica cargados que la app de hoy ya no sacaría de una "
                "descripción, porque aprendió que son modelos o motores.",
                "Es la lista de lo que quedó de antes. La app fue aprendiendo a reconocer "
                "modelos de auto («SUPER5», «308HDI»), designaciones de motor («6PF-305», "
                "«C1J-C1L») y listas de modelos, pero lo que ya estaba cargado se quedó "
                "adentro.\n\n"
                "No hay criterio nuevo acá: a cada código cargado se le da la vuelta y se lo "
                "pasa por el **mismo** extractor que se usa al importar. Si hoy no lo sacaría "
                "de un texto, tampoco debería estar como código de fábrica.\n\n"
                "Mira **las dos colas**: los vínculos ya aprobados y los que están esperando "
                "revisión. La primera versión de esto solo miraba los aprobados, y los códigos "
                "que hacen el daño estaban casi todos en la cola de pendientes — se corría la "
                "limpieza, no aparecía nada, y los puentes falsos seguían ahí.\n\n"
                "Uno que cuelga un solo producto no hace daño, así que se piden dos."
            )
            if st.button("🧯 Buscar los que quedaron de antes", key="btn_puentes_viejos"):
                with st.spinner("Pasando cada código por el extractor de hoy..."):
                    st.session_state["puentes_viejos"] = puentes_que_hoy_no_se_generarian()
            _pv = st.session_state.get("puentes_viejos")
            if _pv is not None:
                if not _pv:
                    st.success("No quedó ninguno: todos los códigos de fábrica cargados que "
                               "unen dos listas los reconocería el extractor de hoy.")
                else:
                    _carg = sum(x.get("Cargados") or 0 for x in _pv)
                    _pend = sum(x.get("Esperando revisión") or 0 for x in _pv)
                    st.warning(
                        f"**{len(_pv)} código(s) que hoy no se generarían**, uniendo "
                        f"{_carg} vínculo(s) ya cargados y {_pend} esperando revisión."
                    )
                    st.dataframe([{k: v for k, v in x.items() if k != "pid"} for x in _pv],
                                  width="stretch", hide_index=True)
                    st.download_button(
                        "⬇️ Bajarlos en Excel antes de decidir",
                        data=to_excel_bytes([{k: v for k, v in x.items() if k != "pid"}
                                              for x in _pv]),
                        file_name="puentes_viejos.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                    st.caption(
                        "Se borra el código de fábrica, los vínculos que colgaban de él **y los "
                        "pendientes que generaba** — si no, al aprobar la cola se vuelve a crear "
                        "exactamente el vínculo que se acaba de borrar. **Los productos no se "
                        "tocan**: precios, stock e historial quedan igual."
                    )
                    if st.checkbox("Miré la lista y entiendo qué se borra", key="conf_p_viejos"):
                        if candado("borrar los puentes viejos",
                                    st.button(f"🗑️ Borrar los {len(_pv)}", type="primary",
                                               key="btn_borrar_p_viejos"),
                                    "borrar_los_puentes_viejos"):
                            _tot = _tot_p = 0
                            for _x in _pv:
                                _a, _b = borrar_puente_y_sus_pendientes(_x["pid"])
                                _tot += _a
                                _tot_p += _b
                            st.session_state.pop("puentes_viejos", None)
                            invalidar_salud()
                            avisar("ok", f"Se borraron {len(_pv)} código(s) de fábrica falsos, "
                                          f"{_tot} vínculo(s) cargados y {_tot_p} pendiente(s). "
                                          "Los productos quedaron intactos.")
                            st.rerun()
            st.markdown("---")

            st.markdown("**🔗 Vínculos que unen dos familias de repuestos**")
            explicar(
                "Dos grupos sanos pegados por un solo vínculo malo. Cortándolo se separan.",
                "Es el caso que ningún otro control agarra: los filtros por un lado y los "
                "amortiguadores por el otro, perfectamente legítimos entre sí, unidos por UN "
                "vínculo mal cargado.\n\nNingún código tiene muchos enlaces, así que no aparece "
                "como código puente. Pero ese eslabón solo sostiene toda la unión."
            )
            cod_red = st.text_input("Código desde el que analizar la red:", key="cod_red_familias",
                                     placeholder="Poné uno de los que te devuelve resultados raros"
                                     ).strip()
            if cod_red:
                c.execute("SELECT id, codigo_raw FROM productos WHERE codigo_clean = ?",
                          (sanitizar(cod_red),))
                obj_red = c.fetchone()
                if not obj_red:
                    st.error("No encontré ese código.")
                else:
                    with st.spinner("Analizando la red..."):
                        uniones = vinculos_que_unen_familias(obj_red["id"])
                    if not uniones:
                        st.success("✅ Ningún vínculo suelto está uniendo grupos grandes en esta red.")
                    else:
                        st.warning(f"⚠️ {len(uniones)} vínculo(s) sostienen la unión de dos grupos. "
                                    "Los más equilibrados y de menor confianza van primero.")
                        st.dataframe(quitar_id(uniones), width="stretch", hide_index=True)
                        etiquetas_u = {
                            f"{u['Código A']} ↔ {u['Código B']} (separa {u['Separa']}, "
                            f"confianza {u['Confianza del vínculo']})": (u["_a"], u["_b"])
                            for u in uniones
                        }
                        elegido_u = st.selectbox("¿Cuál cortar?", list(etiquetas_u.keys()),
                                                  key="union_a_cortar")
                        if candado('cortar vínculos', st.button("✂️ Cortar ese vínculo"), 'cortar_v_nculos_2'):
                            n = borrar_equivalencias_dudosas([etiquetas_u[elegido_u]])
                            invalidar_salud()
                            avisar("success", "Se cortó el vínculo. Las dos familias quedaron separadas.")
                            st.rerun()
            st.markdown("**🔍 Revisar los vínculos que YA están cargados**")
            explicar(
                "El análisis de confianza mira los vínculos pendientes de revisión, pero el problema "
                "grande está en los que ya entraron:",
                "los que cargaron importaciones viejas que nadie revisó. Esto les pasa el mismo "
                "análisis y te muestra los peores. Hasta ahora la única forma de encontrarlos era "
                "tropezarse con uno buscando un código.\n\n"
                "**Vuelve a mirar TODO cada vez que lo corrés, con las reglas de hoy.** No queda "
                "nada marcado como «ya revisado»: los vínculos se cargaron con las reglas de su "
                "momento y las reglas fueron cambiando, así que uno que pasaba limpio hace un mes "
                "puede no pasar hoy. En la base actual son 24.774 vínculos y tarda 12 segundos."
            )
            # Lo mismo de arriba pero del lado del puntaje GUARDADO, que es el que ve el
            # buscador en cada búsqueda: cuando cambian las reglas queda viejo, y el repuntaje
            # lo hace la tarea de fondo. Ver VERSION_CONFIANZA.
            if obtener_config("confianza_pendiente", "") == "1":
                st.info(
                    "⏳ Las reglas de confianza cambiaron y los puntajes guardados todavía son "
                    "los viejos. Se están recalculando solos en segundo plano — el análisis de "
                    "acá abajo ya usa las reglas nuevas igual, porque recalcula al vuelo."
                )
            elif obtener_config("confianza_fecha", ""):
                st.caption(
                    f"Puntajes guardados al día: se repuntuaron "
                    f"{int(obtener_config('confianza_repuntuada', '0') or 0):,} vínculo(s) el "
                    f"{obtener_config('confianza_fecha', '')}."
                )
            # Lo que ya se midió solo después de la última importación. Sin esto, el número
            # existía pero no lo veía nadie hasta apretar un botón que tarda 11 s.
            _dud_prev = obtener_config("dudosos_cargados", "")
            if _dud_prev:
                _rev_prev = obtener_config("dudosos_revisados", "0")
                _fec_prev = obtener_config("dudosos_fecha", "")
                if _dud_prev == "0":
                    st.success(f"✅ En la última importación se revisaron {int(_rev_prev):,} "
                                f"vínculos y ninguno quedó por debajo del umbral ({_fec_prev}).")
                else:
                    st.warning(f"⚠️ En la última importación ({_fec_prev}) quedaron "
                                f"**{int(_dud_prev)} vínculo(s) con evidencia en contra** de "
                                f"{int(_rev_prev):,} revisados. Analizalos acá para verlos y "
                                "decidir cuáles cortar.")
            if st.button("🔎 Analizar los vínculos cargados"):
                with st.spinner("Analizando..."):
                    st.session_state["dudosas_cargadas"] = auditar_equivalencias_cargadas()

            if st.session_state.get("dudosas_cargadas"):
                dudosas, revisadas = st.session_state["dudosas_cargadas"]
                if not dudosas:
                    # No decir «está todo bien»: este control mira la CONFIANZA de cada vínculo
                    # y no si el código que los une es un código. Un modelo de auto cargado como
                    # código de fábrica une repuestos que comparten auto, y por eso saca buena
                    # confianza — pasa este control con el mejor puntaje y sigue estando mal.
                    # Decirlo importa: alguien vio este cartel en verde, entendió «no hay nada
                    # que limpiar», y los puentes falsos seguían ahí arriba en la misma pantalla.
                    st.success(f"✅ Se revisaron {revisadas:,} vínculos y ninguno quedó por debajo del "
                                "umbral de confianza.")
                    st.caption("Ojo: esto mide la **confianza** de cada vínculo, no si el "
                                "código que los unió es un código de verdad.")
                    explicar(
                        "Un puente falso puede pasar este control con el mejor puntaje.",
                        "Un modelo de auto o un número de motor cargado como código de fábrica "
                        "une repuestos que comparten el mismo auto — y compartir auto es "
                        "justamente lo que sube la confianza. Así que sale en verde acá y sigue "
                        "estando mal.\n\nPara eso están **🌉 Códigos puente** y **🧯 Puentes "
                        "que hoy ya no se generarían**, más arriba en esta misma pantalla."
                    )
                else:
                    st.warning(
                        f"⚠️ De {revisadas:,} vínculos revisados, **{len(dudosas)} tienen evidencia en "
                        "contra**. Están ordenados de peor a mejor, con el motivo al lado."
                    )
                    st.dataframe(quitar_id(dudosas), width="stretch", hide_index=True)
                    st.download_button(
                        "⬇️ Bajarlos en Excel antes de decidir",
                        data=to_excel_bytes(quitar_id(dudosas)),
                        file_name="vinculos_dudosos.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    # Las opciones se arman a partir de cuántos hay, y el valor por defecto se
                    # elige de esa misma lista. Con value=min(25, N) y N=7, el valor 7 podía no
                    # estar entre las opciones y Streamlit tira excepción: es el mismo error que
                    # ya rompió la carga de fotos una vez.
                    opciones_cortar = sorted({n for n in (10, 25, 50, 100, len(dudosas))
                                               if n <= len(dudosas)}) or [len(dudosas)]
                    st.session_state.setdefault("cuantos_dudosos", opciones_cortar[0])
                    if st.session_state["cuantos_dudosos"] not in opciones_cortar:
                        st.session_state["cuantos_dudosos"] = opciones_cortar[0]
                    cuantos_cortar = st.select_slider(
                        "Cortar los peores:", options=opciones_cortar, key="cuantos_dudosos"
                    )
                    st.caption(
                        "Se cortan los vínculos, NO los productos: precios, stock e historial quedan "
                        "como están. Y quedan anotados como rechazados, así que una reimportación de "
                        "la misma lista no los vuelve a crear."
                    )
                    if st.checkbox("Miré la lista y entiendo qué se corta", key="confirmar_dudosas"):
                        if candado('cortar vínculos', st.button(f"✂️ Cortar los {cuantos_cortar} peores", type="primary"), 'cortar_v_nculos'):
                            pares = [(x["_a"], x["_b"]) for x in dudosas[:int(cuantos_cortar)]]
                            n = borrar_equivalencias_dudosas(pares)
                            st.session_state.pop("dudosas_cargadas", None)
                            invalidar_salud()
                            avisar("success", f"Se cortaron {n} vínculo(s). Los productos quedaron intactos.")
                            st.rerun()
            st.markdown("**💲 Precios que no cierran entre equivalentes**")
            explicar(
                "Dos repuestos que hacen lo mismo pueden costar distinto según la marca, pero no ocho "
                "veces distinto.",
                "Cuando pasa, una de dos cosas está mal — y las dos cuestan plata: o el **precio** "
                "(columna equivocada, separador de decimales al revés), o la **equivalencia** (los "
                "vinculó una lista mal cargada y no son la misma pieza)."
            )
            st.session_state.setdefault("factor_precio_raro", 8)
            factor_precio = st.select_slider(
                "Mostrar los que se diferencien más de:", options=[4, 6, 8, 15, 30],
                format_func=lambda x: f"{x} veces", key="factor_precio_raro"
            )
            incoherentes = precios_incoherentes_entre_equivalentes(int(factor_precio))
            if incoherentes:
                st.warning(f"⚠️ {len(incoherentes)} par(es) de equivalentes con precios muy distintos.")
                st.dataframe(quitar_id(incoherentes), width="stretch", hide_index=True)
                st.download_button(
                    "⬇️ Bajar la lista en Excel",
                    data=to_excel_bytes(quitar_id(incoherentes)),
                    file_name="precios_incoherentes.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                st.caption(
                    "Revisá primero los de arriba. Si el precio está bien, entonces lo que está mal "
                    "es el vínculo: cortalo desde «Vincular manual» o con los códigos puente de acá abajo."
                )
            else:
                st.caption(f"✅ Ningún par de equivalentes se diferencia más de {factor_precio} veces.")
            st.markdown("**🗑️ Códigos que son solo un número suelto**")
            explicar(
                "Códigos de 1 o 2 caracteres ('1', '12', '1S'). Casi siempre son cantidades coladas.",
                "Como la app vincula todo lo que aparece en la misma fila, el '1' de una lista queda "
                "como equivalente del '1' de otra, y por ahí se cuelan equivalencias entre repuestos "
                "que no tienen nada que ver.\n\nLas listas nuevas ya los filtran solas; esto limpia "
                "lo que quedó de antes."
            )
            cantidad_basura = contar_codigos_basura()
            if cantidad_basura:
                st.warning(f"⚠️ Hay {cantidad_basura} producto(s) con un código así.")
                muestra_basura = listar_codigos_basura(limite=200)
                with st.expander(f"👀 Ver los primeros {len(muestra_basura)} antes de borrar"):
                    st.dataframe(muestra_basura, width="stretch", hide_index=True)
                    st.download_button(
                        "⬇️ Descargar la lista completa",
                        data=to_excel_bytes(listar_codigos_basura(limite=100000)),
                        file_name="codigos_basura.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                st.caption(
                    "Al borrarlos se van también las equivalencias que colgaban de ellos. Esto NO va a "
                    "la papelera: bajate la lista de arriba si querés dejar constancia."
                )
                if st.checkbox("Ya revisé la lista y entiendo que se borran definitivamente",
                                key="confirmar_borrar_basura"):
                    if candado('borrar códigos basura', st.button(f"🗑️ Borrar los {cantidad_basura} códigos y sus equivalencias"), 'borrar_c_digos_basura'):
                        borrados = borrar_codigos_basura()
                        invalidar_salud()
                        avisar("success", f"Se borraron {borrados} producto(s) con código basura.")
                        st.rerun()
            else:
                st.caption("✅ Ningún código de 1 o 2 dígitos en la base.")
            st.markdown("**🔢 Códigos que quedaron con '.0'**")
            st.caption(
                "Cuando una lista de Excel trae el código como número, llega con un decimal pegado "
                "(2776400.0). Además de verse mal, eso los volvía imposibles de encontrar: al buscarlos "
                "quedaban con un cero de más. Esto los deja como corresponde."
            )
            cantidad_decimal = contar_codigos_con_decimal()
            # Códigos que no se encuentran ni tipeándolos exactos, porque el codigo_clean
            # guardado quedó viejo. Va antes que el del '.0' porque es el que más duele: el
            # producto está cargado, con precio y stock, y el buscador jura que no existe.
            _desfasados = codigos_limpios_desfasados()
            st.markdown("**🔎 Códigos que el buscador no encuentra**")
            if not _desfasados:
                st.caption("✅ Todos los códigos se buscan por donde corresponde.")
            else:
                st.warning(
                    f"⚠️ Hay **{len(_desfasados)}** producto(s) cargados que NO aparecen al "
                    "buscarlos, ni escribiendo el código exacto: quedaron guardados con una "
                    "versión vieja del código de búsqueda."
                )
                st.dataframe(
                    [{"Código": x["raw"], "Se busca como": x["guardado"],
                      "Debería buscarse como": x["correcto"]} for x in _desfasados[:25]],
                    width="stretch", hide_index=True)
                if len(_desfasados) > 25:
                    st.caption(f"…y {len(_desfasados) - 25} más.")
                if candado('recalcular códigos de búsqueda', st.button(f"🔧 Arreglar esos {len(_desfasados)} códigos"), 'recalcular_c_digos_de_b_squeda'):
                    _n = reparar_codigos_limpios()
                    avisar("success", f"Se arreglaron {_n} código(s). Ya se pueden buscar.")
                    invalidar_salud()
                    st.rerun()

            st.markdown("**🔢 Códigos con el '.0' de Excel**")
            if cantidad_decimal:
                st.warning(f"⚠️ Hay {cantidad_decimal} producto(s) con el código terminado en '.0'.")
                if candado('reescribir códigos de todo el catálogo', st.button(f"🔧 Arreglar los {cantidad_decimal} códigos"), 'reescribir_c_digos_de_todo_el_cat_'):
                    arreglados = reparar_codigos_con_decimal()
                    # Sin el refresco, el cartel de arriba seguía mostrando el número viejo
                    # y parecía que el botón no hacía nada. El aviso se guarda para que
                    # sobreviva al refresco.
                    avisar("success", f"Se arreglaron {arreglados} código(s) terminados en '.0'.")
                    invalidar_salud()
                    st.rerun()
            else:
                st.caption("✅ Ningún código con ese problema.")
            st.markdown("**📝 Descripciones con las columnas pegadas**")
            st.caption(
                "Algunas listas exportan varias columnas sin espacio entre medio "
                "(«Junta Tapa de CilindrosFORDTAUNUS»). Esto las separa para que se lean."
            )
            pegadas = contar_descripciones_pegadas()
            if pegadas:
                st.warning(f"⚠️ Hay {pegadas:,} descripción(es) con ese problema.")
                if candado('reescribir las descripciones de todo el catálogo', st.button("🔧 Separar las descripciones pegadas"), 'reescribir_las_descripciones_de_to'):
                    arregladas = reparar_descripciones_pegadas()
                    st.success(f"Se separaron {arregladas} descripción(es).")
            else:
                st.caption("✅ Ninguna descripción con ese problema.")

        if _grupo_mant == GRUPOS_MANTENIMIENTO[2]:
            st.markdown("**🎯 Puntuar los vínculos para el buscador**")
            try:
                sin_puntuar = faltan_por_puntuar()
                c.execute("SELECT COUNT(*) FROM equivalencias")
                total_eq = c.fetchone()[0]
            except sqlite3.OperationalError as _err:
                anotar_error("nivel principal", _err)
                sin_puntuar = total_eq = 0
            explicar(
                "Le pone puntaje a cada vínculo y lo guarda.",
                "El buscador lo usa para decirte, en cada resultado, qué tan sólido es el camino por el "
                "que llegó: **una cadena vale lo que su eslabón más flojo**. Un resultado a dos saltos "
                "por vínculos buenos es más confiable que uno directo colgado de un vínculo malo."
            )
            if sin_puntuar:
                st.info(f"Hay {sin_puntuar:,} vínculo(s) sin puntuar de {total_eq:,}. "
                         "Mientras tanto cuentan como neutros.")
            if candado('puntuar los vínculos', total_eq and st.button("🎯 Calcular la confianza de los vínculos que faltan"), 'puntuar_los_v_nculos'):
                barra_conf = st.progress(0.0, text="Puntuando...")
                # Va por tandas hasta terminar, no una sola de tamaño fijo. Antes se hacía una
                # tanda y listo, y con más vínculos que el tope quedaban miles sin puntuar por
                # más veces que se tocara el botón: el botón decía "todos" y no era cierto.
                pendientes = sin_puntuar
                hechos = 0
                while True:
                    n = recalcular_confianzas(limite=2000, solo_faltantes=True)
                    if not n:
                        break
                    hechos += n
                    barra_conf.progress(min(hechos / max(pendientes, 1), 1.0),
                                        text=f"Puntuando {hechos:,} de {pendientes:,}...")
                    if hechos >= pendientes:
                        break
                barra_conf.empty()
                invalidar_salud()
                avisar("success", f"Se puntuaron {hechos:,} vínculo(s). El buscador ya lo está "
                                  "usando.")
                st.rerun()
            if candado('volver a puntuar todos los vínculos', total_eq and st.button("♻️ Volver a puntuar TODO", help="Los puntajes cambian cuando aparece evidencia nueva " "—ventas que confirman un reemplazo, decisiones que " "tomaste al revisar—. Esto los recalcula de cero."), 'volver_a_puntuar_todos_los_v_nculo'):
                barra_re = st.progress(0.0, text="Recalculando...")
                n = recalcular_confianzas(
                    limite=max(total_eq, 1), solo_faltantes=False,
                    progreso=lambda i, t: barra_re.progress(min(i / max(t, 1), 1.0),
                                                            text=f"Recalculando {i:,} de {t:,}..."))
                barra_re.empty()
                invalidar_salud()
                avisar("success", f"Se recalcularon {n:,} vínculo(s).")
                st.rerun()
            st.markdown("**🧾 Equivalencias que confirmó el mostrador**")
            explicar(
                "Cada venta guarda qué código te pidieron y cuál le vendiste.",
                "Cuando son distintos y se repite, eso es una equivalencia confirmada en la práctica: "
                "alguien decidió que servía, el cliente se lo llevó y no volvió a reclamar. Pesa más "
                "que cualquier lista de proveedor — una lista dice lo que el proveedor cree, esto es lo "
                "que pasó."
            )
            try:
                sustituciones = sustituciones_reales()
            except sqlite3.OperationalError as _err:
                anotar_error("nivel principal", _err)
                sustituciones = []
            if not sustituciones:
                st.caption(
                    "Todavía no hay ninguna repetida. Aparecen solas a medida que vendés reemplazos: "
                    "hace falta que la misma sustitución se dé al menos dos veces, porque una sola "
                    "puede ser un error de tipeo."
                )
            else:
                sin_vincular = [x for x in sustituciones if not x["_ya"]]
                st.dataframe(quitar_id(sustituciones), width="stretch", hide_index=True)
                if sin_vincular:
                    st.warning(
                        f"⚠️ {len(sin_vincular)} de estas sustituciones **todavía no están cargadas "
                        "como equivalencia**. Son ventas que ya hiciste: el buscador debería "
                        "encontrarlas solo la próxima vez."
                    )
                    if st.button(f"📥 Mandar esas {len(sin_vincular)} a revisión"):
                        lote_v = f"CONFIRMADAS EN EL MOSTRADOR · {datetime.now():%d/%m %H:%M}"
                        n = guardar_equivalencias_derivadas(
                            [(x["_a"], x["_b"]) for x in sin_vincular], lote_v)
                        invalidar_salud()
                        avisar("success", f"{n} equivalencia(s) quedaron para revisar.")
                        st.rerun()
                else:
                    st.success("✅ Todas las sustituciones repetidas ya están cargadas.")
            st.markdown("**📚 Lo que la app aprendió de tus decisiones**")
            explicar(
                "Cada vez que aprobás o descartás un vínculo, esa decisión queda guardada.",
                "Acá se ve qué patrones sacó de eso y los está usando para puntuar los vínculos nuevos. "
                "Se muestra a propósito: un sistema que aprende a escondidas no se puede corregir."
            )
            patrones_vistos = aprender_de_las_decisiones()
            if not patrones_vistos["marcas"]:
                st.caption(
                    f"Todavía no hay patrones. Llevás {patrones_vistos['total']} decisión(es) "
                    f"revisadas; hacen falta al menos {MINIMO_PARA_APRENDER} sobre una misma "
                    "combinación de marcas para sacar una conclusión. Con menos, la regla sería peor "
                    "que no tener regla."
                )
            else:
                filas_patron = []
                for (ma, mb), d in sorted(patrones_vistos["marcas"].items(),
                                           key=lambda x: -x[1]["decisiones"]):
                    if d["tasa_ok"] >= 0.85:
                        efecto = "✅ suma confianza"
                    elif d["tasa_ok"] <= 0.20:
                        efecto = "❌ resta confianza"
                    else:
                        efecto = "— sin efecto (ni claro que sí ni que no)"
                    filas_patron.append({
                        "Marcas": f"{ma} ↔ {mb}",
                        "Revisados": d["decisiones"],
                        "Aprobaste": f"{d['tasa_ok']*100:.0f}%",
                        "Efecto en los vínculos nuevos": efecto,
                    })
                st.dataframe(filas_patron, width="stretch", hide_index=True)
                st.caption(
                    "Si algún patrón no te cierra, corregilo revisando algunos vínculos de esa "
                    "combinación al revés: la app se reajusta sola con las decisiones nuevas."
                )
        if _grupo_mant == GRUPOS_MANTENIMIENTO[0]:
            st.markdown("**🏭 Catálogo de aplicaciones (qué repuesto le va a cada auto)**")
            explicar(
                "El catálogo que dice a qué auto le va cada repuesto. NGK, Bosch, Mann y SKF "
                "publican el suyo gratis.",
                "Es distinto de una lista de precios: una lista dice cuánto cuesta un código, un "
                "catálogo de aplicaciones dice **a qué auto le va**.\n\nBuscalo en el sitio del "
                "fabricante como «catálogo de aplicaciones» y subilo acá. Con esto, buscar por VIN "
                "o por vehículo deja de adivinar desde las descripciones del proveedor."
            )
            try:
                c.execute("""SELECT marca_repuesto AS "Marca", COUNT(*) AS "Aplicaciones",
                                    COUNT(DISTINCT marca_auto) AS "Marcas de auto",
                                    COUNT(DISTINCT codigo) AS "Códigos"
                             FROM aplicaciones GROUP BY marca_repuesto ORDER BY 2 DESC""")
                ya_cargadas = filas_a_listas(c)
            except sqlite3.OperationalError as _err:
                anotar_error("nivel principal", _err)
                ya_cargadas = []
            if ya_cargadas:
                st.dataframe(ya_cargadas, width="stretch", hide_index=True)

            # LAS QUE SALEN DE TU PROPIO CATÁLOGO, sin subir nada. Va ARRIBA del archivo a
            # propósito: el que llega acá con la tabla vacía no necesita salir a buscar el PDF
            # de NGK, necesita apretar un botón. Sobre las descripciones reales salen 114.673
            # aplicaciones de 87 marcas de auto.
            #
            # Y sobre todo: esto es la SALIDA DE EMERGENCIA. La deducción la hace sola la tarea
            # de fondo, pero hasta ahora no había forma de pedirla a mano, así que si el hilo
            # se moría a la mitad —que es lo que venía pasando— la tabla quedaba en cero para
            # siempre y el usuario no tenía ningún botón que apretar.
            st.caption("O sin subir nada, deduciéndolas de las descripciones que ya tenés:")
            _cd1, _cd2 = cols([2, 3])
            if _cd1.button("🧠 Deducir de mis descripciones", key="deducir_aplic_a_mano",
                            help="Lee las descripciones del catálogo y saca a qué auto le va "
                                 "cada pieza. Tarda cerca de un minuto."):
                with st.spinner("Leyendo las descripciones..."):
                    try:
                        _ded = aplicaciones_desde_descripciones()
                        _n_ded = aplicar_aplicaciones_deducidas(_ded) if _ded else 0
                        guardar_config("aplicaciones_deducidas", str(_n_ded))
                        guardar_config("aplicaciones_fecha",
                                       datetime.now().strftime("%Y-%m-%d %H:%M"))
                        _quedo_hecho("aplicaciones_pendientes")
                        invalidar_salud()
                        avisar("success", f"Se dedujeron {_n_ded:,} aplicaciones de tus "
                                          "descripciones.")
                    except Exception as _err:
                        anotar_error("deducir_aplicaciones_a_mano", _err)
                        st.error(f"No se pudo: {type(_err).__name__}: {_err}")
                st.rerun()
            _cd2.caption("Son las que la app puede sacar sola de lo que ya importaste. "
                         "No reemplazan al catálogo del fabricante: lo complementan.")

            arch_aplic = subir_archivo("Catálogo de aplicaciones (.pdf o .xlsx):",
                                        ["pdf", "xlsx", "csv"], "aplicaciones")
            ca_m, ca_t = cols(2)
            marca_aplic = ca_m.text_input("¿De qué marca de repuesto es este catálogo?",
                                           placeholder="Ej: NGK, Bosch, Mann", key="marca_aplic").strip()
            # El tipo de pieza no es un dato decorativo: es lo que después permite cruzar catálogos
            # sin mezclar una bujía con un filtro por el solo hecho de ir al mismo auto.
            tipo_aplic = ca_t.selectbox(
                "¿Qué tipo de pieza trae?", ["(elegir)"] + sorted(FAMILIAS_REPUESTO.keys()),
                key="tipo_aplic",
                help="Importante: con esto la app puede después cruzar los catálogos de dos "
                     "fabricantes y deducir equivalencias, sin confundir rubros distintos."
            )
            tipo_aplic = "" if tipo_aplic == "(elegir)" else tipo_aplic
            if arch_aplic:
                archivo_listo(arch_aplic, "catálogo")
                boton_otro_archivo("aplicaciones", "🗑️ Usar otro", key="otro_aplic")
                if st.button("🔎 Leer el catálogo", disabled=not (marca_aplic and tipo_aplic)):
                    with st.spinner("Leyendo... en un PDF grande puede tardar un rato"):
                        try:
                            tablas = tablas_de_archivo(arch_aplic)
                            apps = []
                            for tabla in tablas:
                                # OJO con el nombre: 'cols' es una función de esta app. Llamar así a
                                # la variable la pisa a nivel global y cualquier cols(3) posterior
                                # revienta. Ya pasó antes; por eso la auditoría lo chequea.
                                posiciones = detectar_columnas_aplicaciones(tabla)
                                apps += parsear_catalogo_aplicaciones(
                                    tabla, posiciones["modelo"], posiciones["motor"],
                                    posiciones["comb"], posiciones["anios"], posiciones["codigo"]
                                )
                        except Exception as e:
                            anotar_error("nivel principal", e)
                            apps = []
                            st.error(f"No se pudo leer: {type(e).__name__}: {e}")
                    if apps:
                        st.session_state["aplic_leidas"] = apps
                        if len({a["marca_auto"] for a in apps}) < 2:
                            st.warning(
                                "⚠️ Se reconoció una sola marca de auto. Si este archivo en realidad "
                                "es una **lista de precios**, no va acá: cargala en "
                                "**📁 Cargar Excel**."
                            )
                        marcas_detectadas = sorted({a["marca_auto"] for a in apps})
                        st.success(f"Se reconocieron {len(apps):,} aplicaciones de "
                                   f"{len(marcas_detectadas)} marca(s) de auto.")
                        st.caption("Revisá esta muestra antes de guardar:")
                        st.dataframe(apps[:40], width="stretch", hide_index=True)
                    elif arch_aplic:
                        st.warning(
                            "No reconocí aplicaciones en ese archivo. Esta lectura espera la forma "
                            "habitual de estos catálogos: la marca del auto sola en una fila, y "
                            "debajo modelo, motorización, años y código."
                        )

            if st.session_state.get("aplic_leidas"):
                apps_pend = st.session_state["aplic_leidas"]
                if st.button(f"💾 Guardar las {len(apps_pend):,} aplicaciones", type="primary"):
                    n = guardar_aplicaciones(apps_pend, marca_aplic,
                                              getattr(arch_aplic, "name", "catálogo"), tipo_aplic)
                    st.session_state.pop("aplic_leidas", None)
                    invalidar_salud()
                    avisar("success", f"Se guardaron {n:,} aplicaciones de {marca_aplic.upper()}.")
                    st.rerun()

            # Un índice arriba de todo: son seis formas distintas de generar equivalencias y
            # cada una necesita cosas distintas. Sin este resumen hay que bajar leyendo panel
            # por panel para saber cuál se puede usar hoy.
            st.markdown("### 🔗 Generar equivalencias")
            # Con valor inicial: si la consulta falla, el índice tiene que dibujarse igual en
            # vez de tumbar la pantalla entera por un contador.
            marcas_con_tipo = 0
            _n_desc = _n_med = _n_reemp = 0
            try:
                c.execute("""SELECT COUNT(DISTINCT marca_repuesto) FROM aplicaciones
                             WHERE COALESCE(tipo_pieza,'') <> ''""")
                marcas_con_tipo = c.fetchone()[0]
            except sqlite3.OperationalError as _err:
                anotar_error("nivel principal", _err)
                marcas_con_tipo = 0
            try:
                c.execute("SELECT COUNT(*) FROM productos WHERE COALESCE(descripcion,'') <> ''")
                _n_desc = c.fetchone()[0]
                c.execute(f"SELECT COUNT(*) FROM productos WHERE {CAMPOS_MEDIDAS[0][0]} IS NOT NULL")
                _n_med = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM reemplazos_codigo")
                _n_reemp = c.fetchone()[0]
            except sqlite3.OperationalError as _err:
                anotar_error("nivel principal", _err)
                pass
            _n_portales = sum(1 for _m in (filas_a_listas(c.execute(
                "SELECT nombre FROM marcas")) or []) if config_portal(_m["nombre"]))

            st.dataframe([
                {"Método": "🔤 Por descripción",
                 "Qué necesita": "dos proveedores con descripciones",
                 "Estado": f"listo — {_n_desc:,} productos con descripción" if _n_desc > 50
                            else "faltan productos con descripción"},
                {"Método": "📐 Por medidas",
                 "Qué necesita": "3 o más medidas cargadas, en marcas distintas",
                 "Estado": f"listo — {_n_med:,} con medidas" if _n_med > 5
                            else "todavía no hay medidas cargadas"},
                {"Método": "🔄 Por cambio de número",
                 "Qué necesita": "reemplazos cargados a mano",
                 "Estado": f"listo — {_n_reemp} reemplazo(s)" if _n_reemp
                            else "cargá reemplazos en «Códigos reemplazados»"},
                {"Método": "🏭 Cruzando catálogos",
                 "Qué necesita": "2 catálogos de fabricante del mismo tipo de pieza",
                 "Estado": f"listo — {marcas_con_tipo} marca(s)" if marcas_con_tipo >= 2
                            else f"tenés {marcas_con_tipo}, hacen falta 2"},
                {"Método": "🔐 Autos del portal",
                 "Qué necesita": "usuario del portal en los secretos",
                 "Estado": f"listo — {_n_portales} portal(es)" if _n_portales
                            else "sin configurar"},
                {"Método": "🧾 Confirmadas por venta",
                 "Qué necesita": "usar «Se llevó» en el mostrador",
                 "Estado": "corre solo, una vez por día"},
            ], width="stretch", hide_index=True)
            st.caption("Cada método está en un panel más abajo. Todos mandan a revisión: "
                       "ninguno carga equivalencias directo.")
            st.markdown("---")

            # Cada panel con SU condición. Estaban los cinco dentro de «si hay 2 catálogos
            # de fabricante», y cuatro no los necesitan: medidas, reemplazos, portal y
            # descripciones andan sin ningún catálogo cargado. Así quedaban invisibles.
            st.markdown("**📐 Equivalencias por medidas**")
            explicar(
                "La evidencia más fuerte que hay: no es texto, es la pieza física.",
                "Las medidas se venían usando solo para verificar un vínculo que ya "
                "existía. Pero en retenes, o'rings, rulemanes y bujes la medida **es** la "
                "identidad: un 35x52x7 de un proveedor y un 35x52x7 de otro son el mismo "
                "repuesto, sin importar cómo se llame el código ni cómo esté escrita la "
                "descripción.\n\nSe piden al menos 3 medidas coincidentes: con una sola "
                "—el diámetro interno, por ejemplo— coincidirían piezas completamente "
                "distintas que casualmente miden lo mismo. Y se compara igual el nombre de "
                "la pieza, porque una arandela y un retén pueden medir exactamente igual."
            )
            if st.button("📐 Buscar equivalencias por medidas"):
                with st.spinner("Comparando medidas..."):
                    st.session_state["deriv_med"] = derivar_equivalencias_por_medidas()
            _dm = st.session_state.get("deriv_med")
            if _dm is not None:
                if not _dm:
                    st.info(
                        "No salió ninguna. Hacen falta productos con al menos 3 medidas "
                        "cargadas, de marcas distintas. Se cargan en la ficha de cada "
                        "producto o al importar, si la lista trae columnas de medidas."
                    )
                else:
                    st.success(f"{len(_dm)} par(es) con las mismas medidas.")
                    st.dataframe(quitar_id(_dm), width="stretch", hide_index=True)
                    if st.button(f"📥 Mandar las {len(_dm)} a revisión", key="env_med"):
                        _n = guardar_equivalencias_derivadas(
                            [(x["_a"], x["_b"]) for x in _dm],
                            f"POR MEDIDAS · {datetime.now():%d/%m %H:%M}")
                        st.session_state.pop("deriv_med", None)
                        invalidar_salud()
                        avisar("success", f"{_n} equivalencia(s) para revisar.")
                        st.rerun()
            st.markdown("---")

            st.markdown("**🔄 Reunir lo que separó un cambio de número**")
            explicar(
                "Cuando el fabricante cambia el número, la cadena se parte en dos islas.",
                "Tenés un producto vinculado al código de fábrica viejo y otro al nuevo. "
                "Son el mismo repuesto, pero para la app quedaron sin relación.\n\nLos "
                "reemplazos que cargaste ya sabían que el viejo y el nuevo son lo mismo: "
                "esto usa ese dato para volver a unirlos."
            )
            try:
                _pu = equivalencias_puenteadas_por_reemplazo()
            except Exception as _err:
                anotar_error("nivel principal", _err)
                _pu = []
            if not _pu:
                st.caption(
                    "Nada para reunir. Aparece cuando cargues reemplazos y tengas productos "
                    "de los dos códigos."
                )
            else:
                st.success(f"{len(_pu)} par(es) que el cambio de número había separado.")
                st.dataframe(quitar_id(_pu), width="stretch", hide_index=True)
                if st.button(f"📥 Mandar los {len(_pu)} a revisión", key="env_puente"):
                    _n = guardar_equivalencias_derivadas(
                        [(x["_a"], x["_b"]) for x in _pu],
                        f"POR REEMPLAZO DE CÓDIGO · {datetime.now():%d/%m %H:%M}")
                    invalidar_salud()
                    avisar("success", f"{_n} equivalencia(s) para revisar.")
                    st.rerun()
            st.markdown("---")

            st.markdown("**🔐 Traer autos del portal del proveedor**")
            explicar(
                "Para cuando la descripción se corta y no entran todos los autos.",
                "La ficha del portal tiene la lista completa; la celda de Excel no. Con "
                "esos autos cargados, la app puede vincular productos de dos proveedores "
                "aunque sus descripciones no compartan ni un modelo.\n\n**Configuración**, "
                "en Settings → Secrets de Streamlit:\n\n```\n[portal_FISPA]\n"
                'url_login = "https://proveedor.com/login"\nusuario = "tu_usuario"\n'
                'clave = "tu_clave"\ncampo_usuario = "email"\ncampo_clave = "password"\n'
                'url_ficha = "https://proveedor.com/producto/{codigo}"\n```\n\n'
                "Los nombres de `campo_usuario` y `campo_clave` son los `name=` del "
                "formulario de acceso del portal.\n\n**Va en los secretos y no en la base** "
                "por una razón concreta: la base se baja como backup y se sube a GitHub. "
                "Una clave ahí queda publicada.\n\n**La app no puede pedir nada.** La "
                "sesión que se abre es de solo lectura: los métodos para enviar datos "
                "(post, put, delete) directamente no existen en ella, así que ni un error "
                "de programación podría mandar un pedido. Y las direcciones que dicen "
                "carrito, pedido, comprar o checkout se rechazan aunque sean de solo "
                "consulta, porque hay portales que agregan al carrito con un simple enlace."
            )
            st.info(
                "🔒 **La app solo puede leer fichas.** No puede hacer pedidos, ni reservas, "
                "ni modificar nada en el portal del proveedor. Está bloqueado por diseño, "
                "no por configuración: nadie puede activarlo sin querer."
            )
            try:
                c.execute("""SELECT m.id, m.nombre, COUNT(p.id) AS n FROM marcas m
                             JOIN productos p ON p.marca_id = m.id
                             GROUP BY m.id ORDER BY n DESC""")
                _marcas_portal = filas_a_listas(c)
            except sqlite3.OperationalError as _err:
                anotar_error("nivel principal", _err)
                _marcas_portal = []
            _con_portal = [x for x in _marcas_portal if config_portal(x["nombre"])]
            if not _con_portal:
                st.caption(
                    "Todavía no hay ningún portal configurado. Mientras tanto, fijate si el "
                    "proveedor deja **exportar el catálogo a Excel** desde su portal: bajarlo "
                    "y cargarlo por «Cargar Excel» es más simple y más confiable que esto."
                )
            else:
                _et_p = {f"{x['nombre']} ({x['n']:,} productos)": x for x in _con_portal}
                _sel_p = st.selectbox("Proveedor:", list(_et_p.keys()), key="portal_marca")
                _marca_p = _et_p[_sel_p]
                _cuantos = st.select_slider("Traer fichas de:", options=[10, 25, 50, 100],
                                             format_func=lambda x: f"{x} productos",
                                             key="portal_cuantos")
                st.caption(
                    "Se hace de a tandas chicas y con una pausa entre pedidos. No es "
                    "lentitud: golpear el servidor del proveedor a máxima velocidad es la "
                    "forma más rápida de que te bloqueen la cuenta."
                )
                if st.button("🔐 Entrar y traer las fichas"):
                    _sesion, _err = sesion_de_portal(_marca_p["nombre"])
                    if _err:
                        st.error(_err)
                    else:
                        c.execute("""SELECT p.codigo_raw, p.codigo_clean FROM productos p
                                     WHERE p.marca_id = ?
                                       AND p.codigo_clean NOT IN
                                           (SELECT codigo_clean FROM aplicaciones
                                             WHERE codigo_clean IS NOT NULL)
                                     LIMIT ?""", (_marca_p["id"], int(_cuantos)))
                        _pendientes = [(r["codigo_raw"], r["codigo_clean"])
                                        for r in c.fetchall()]
                        if not _pendientes:
                            st.info("Todos los productos de esa marca ya tienen autos cargados.")
                        else:
                            _barra = st.progress(0.0, text="Trayendo fichas...")
                            _con, _sin = 0, 0
                            for _i, (_cod, _cl) in enumerate(_pendientes):
                                _autos, _e2 = autos_desde_ficha_del_portal(
                                    _marca_p["nombre"], _cod)
                                if _autos:
                                    guardar_autos_de_ficha(_cod, _marca_p["nombre"], _autos)
                                    _con += 1
                                else:
                                    _sin += 1
                                _barra.progress((_i + 1) / len(_pendientes),
                                                 text=f"{_i + 1} de {len(_pendientes)}...")
                                time.sleep(0.7)   # pausa entre pedidos, a propósito
                            _barra.empty()
                            invalidar_salud()
                            avisar("success",
                                   f"Se trajeron autos de {_con} ficha(s). "
                                   f"{_sin} no tenían autos reconocibles.")
                            st.rerun()
            st.markdown("---")

            st.markdown("**🔤 Vincular dos proveedores por la descripción**")
            explicar(
                "Para las listas que NO traen el código de fábrica, que son la mayoría.",
                "Sin esa columna, la app no puede generar ninguna equivalencia: es la "
                "limitación de fondo que arrastramos. Esto la resuelve comparando lo que dicen "
                "las descripciones.\n\nSe exige coincidencia en el **nombre de la pieza** —no "
                "solo en el auto—, y que no se contradigan la **posición** ni la "
                "**cilindrada**. Ese control es el que evita el error grave: «CAPUCHON BUJIA "
                "CRUZE» y «ANILLO BUJIA CRUZE» comparten el rubro y el auto, y son piezas "
                "distintas.\n\nComo todo lo deducido, va a la cola de revisión: el sistema de "
                "confianza las evalúa igual que a cualquier otra."
            )
            try:
                c.execute("""SELECT m.id, m.nombre, COUNT(p.id) AS n FROM marcas m
                             JOIN productos p ON p.marca_id = m.id
                             WHERE COALESCE(p.descripcion,'') <> ''
                             GROUP BY m.id HAVING n >= 20 ORDER BY n DESC""")
                _marcas_desc = filas_a_listas(c)
            except sqlite3.OperationalError as _err:
                anotar_error("nivel principal", _err)
                _marcas_desc = []
            if len(_marcas_desc) < 2:
                st.caption("Hacen falta al menos dos marcas con descripciones cargadas.")
            else:
                _et = {f"{x['nombre']} ({x['n']:,} productos)": x["id"] for x in _marcas_desc}
                cd1, cd2 = cols(2)
                _ma = cd1.selectbox("Proveedor A:", list(_et.keys()), key="desc_marca_a")
                _mb = cd2.selectbox("Proveedor B:", list(_et.keys()),
                                     index=min(1, len(_et) - 1), key="desc_marca_b")
                # El tope no es solo lentitud: es que las filas que quedan afuera son SIEMPRE
                # las mismas —las últimas de cada lista— y no se comparan nunca. Callarlo hace
                # creer que se revisó todo. Sobre una lista real de 25.875 productos son casi
                # 22.000 que no entran, o sea el 85% del proveedor.
                _cuenta = {x["id"]: x["n"] for x in _marcas_desc}
                _grandes = [(nombre, _cuenta.get(mid, 0)) for nombre, mid in
                            ((_ma, _et[_ma]), (_mb, _et[_mb]))
                            if _cuenta.get(mid, 0) > TOPE_PRODUCTOS_POR_COMPARACION]
                if _grandes:
                    st.warning(
                        "⚠️ " + " y ".join(f"**{n.split(' (')[0]}** tiene {c:,} productos"
                                            for n, c in _grandes)
                        + f", y esta comparación mira las primeras "
                          f"{TOPE_PRODUCTOS_POR_COMPARACION:,} de cada una. El resto no se "
                          "compara nunca, porque son siempre las mismas filas las que quedan "
                          "afuera.\n\nPara recorrer el catálogo entero sin tope, usá "
                          "**🧠 Buscar equivalencias en TODO el catálogo de una**, más abajo."
                    )
                if st.button("🔤 Buscar equivalencias por descripción",
                              disabled=(_ma == _mb)):
                    with st.spinner("Comparando descripciones..."):
                        st.session_state["deriv_desc"] = derivar_equivalencias_por_descripcion(
                            _et[_ma], _et[_mb])
                _dd = st.session_state.get("deriv_desc")
                if _dd is not None:
                    if not _dd:
                        st.info(
                            "No salió ninguna. Puede ser que las descripciones de esos dos "
                            "proveedores sean muy distintas entre sí, o que ya estén vinculados."
                        )
                    else:
                        st.success(f"Se encontraron {len(_dd)} posibles equivalencias.")
                        st.dataframe(quitar_id(_dd), width="stretch", hide_index=True)
                        st.caption(
                            "Mirá la columna «Por qué» antes de mandarlas: dice exactamente en "
                            "qué coinciden. Si ves algo que no cierra, avisame y ajusto el criterio."
                        )
                        if st.button(f"📥 Mandar las {len(_dd)} a revisión", type="primary"):
                            _lote_d = f"POR DESCRIPCIÓN · {_ma[:14]}↔{_mb[:14]} · {datetime.now():%d/%m %H:%M}"
                            _n = guardar_equivalencias_derivadas(
                                [(x["_a"], x["_b"]) for x in _dd], _lote_d)
                            st.session_state.pop("deriv_desc", None)
                            invalidar_salud()
                            avisar("success", f"{_n} equivalencia(s) quedaron para revisar.")
                            st.rerun()
            st.markdown("---")


            if marcas_con_tipo >= 2:
                st.markdown("**🔗 Equivalencias deducidas cruzando catálogos**")
                explicar(
                    "Si dos fabricantes dicen que sus piezas van al mismo auto, son intercambiables.",
                    "Ninguna lista de proveedor te lo dice: sale de cruzar catálogos que ya "
                    "tenés.\n\nSolo se cruzan códigos del **mismo tipo de pieza**, de fabricantes "
                    "**distintos**, y que coincidan en **varios autos** — con uno solo podría ser "
                    "casualidad."
                )
                if st.button("🔗 Buscar equivalencias entre catálogos"):
                    with st.spinner("Cruzando..."):
                        st.session_state["derivadas"] = derivar_equivalencias_de_aplicaciones()
                derivadas = st.session_state.get("derivadas")
                if derivadas is not None:
                    if not derivadas:
                        st.info(
                            "No salió ninguna. Puede ser que los catálogos cargados sean de tipos de "
                            "pieza distintos, o que sus códigos todavía no estén en tus listas."
                        )
                    else:
                        st.success(f"Se dedujeron {len(derivadas)} equivalencia(s) posibles.")
                        st.dataframe(quitar_id(derivadas), width="stretch", hide_index=True)
                        st.caption(
                            "No se cargan directo: van a la cola de revisión, donde el análisis de "
                            "confianza las evalúa como a cualquier otra. Por buena que sea la "
                            "deducción, sigue siendo una deducción."
                        )
                        if st.button(f"📥 Mandar las {len(derivadas)} a revisión", type="primary"):
                            lote_der = f"CATÁLOGOS DE FABRICANTE · {datetime.now():%d/%m %H:%M}"
                            n = guardar_equivalencias_derivadas(
                                [(x["_a"], x["_b"]) for x in derivadas], lote_der)
                            st.session_state.pop("derivadas", None)
                            invalidar_salud()
                            avisar("success", f"{n} equivalencia(s) quedaron para revisar.")
                            st.rerun()
                st.markdown("---")

        if _grupo_mant == GRUPOS_MANTENIMIENTO[5]:
            st.markdown("**🔀 ¿Cuánto cruza tu catálogo entre proveedores?**")
            explicar(
                "Marca por marca: cuántos productos tienen vínculo y cuántos llegan a otra "
                "marca. Una lista con cero que crucen quedó aislada.",
                "«No me relaciona los proveedores» puede venir de varias cosas y desde la "
                "pantalla se ven todas iguales. Esto lo pone en números.\n\nUna lista con miles "
                "de productos y CERO que crucen es una lista que se importó sin la columna de "
                "código de fábrica, o con esa columna mal mapeada. Eso no se ve mirando "
                "resultados de a uno; se ve mirando la tabla entera.\n\nSe cuentan los vínculos "
                "directos, que es lo que se puede calcular de una pasada sobre todo el catálogo. "
                "Para saber si una lista quedó aislada, alcanza."
            )
            if st.button("🔀 Medir los cruces"):
                with st.spinner("Contando..."):
                    st.session_state["salud_cruces"] = salud_de_los_cruces()
            _sc = st.session_state.get("salud_cruces")
            if _sc is not None:
                _filas_sc, _res_sc = _sc
                if not _filas_sc:
                    st.info("Todavía no hay productos cargados.")
                else:
                    _tot = _res_sc["productos"] or 1
                    _pct = _res_sc["cruzan"] * 100 // _tot
                    (st.error if _pct < 25 else st.warning if _pct < 60 else st.success)(
                        f"**{_pct}% de tus productos de proveedor cruzan a otra marca** "
                        f"({_res_sc['cruzan']:,} de {_res_sc['productos']:,})."
                    )
                    # Antes que el cartel de «reimportá»: una lista que ya tiene todo
                    # encontrado y sin aprobar da el mismo cero, y mandarla a reimportar es
                    # hacer perder una tarde por nada. Ver productos_con_vinculos_esperando().
                    if _res_sc.get("listas_esperando"):
                        _esp_n = sum(f["Esperando revisión"] for f in _filas_sc
                                     if f["Marca"] in _res_sc["listas_esperando"])
                        st.warning(
                            "**No hace falta reimportar nada: "
                            + ", ".join(_res_sc["listas_esperando"][:12])
                            + (" y otras" if len(_res_sc["listas_esperando"]) > 12 else "")
                            + f" ya tienen las equivalencias encontradas.** Son {_esp_n:,} "
                              "producto(s) esperando que alguien las apruebe en Estadísticas → "
                              "🔗 Equivalencias sugeridas. Hasta que no se aprueben, la búsqueda "
                              "no las usa y la columna de arriba sigue en cero."
                        )
                    if _res_sc["listas_aisladas"]:
                        st.error(
                            "**Estas listas están aisladas** — ninguno de sus productos cruza a "
                            "otra marca: " + ", ".join(_res_sc["listas_aisladas"][:12])
                            + (" y otras." if len(_res_sc["listas_aisladas"]) > 12 else ".")
                            + " Volvé a importarlas indicando bien la columna de código de "
                              "fábrica (OEM), que es la única que las une con el resto."
                        )
                    st.dataframe([{k: v for k, v in f.items() if not k.startswith("_")}
                                  for f in _filas_sc],
                                 width="stretch", hide_index=True)
            st.markdown("---")

        if _grupo_mant == GRUPOS_MANTENIMIENTO[0]:
            st.markdown("**📝 Códigos de fábrica que el proveedor escribió en la descripción**")
            explicar(
                "Recorre las descripciones ya cargadas y busca los códigos que el proveedor "
                "marcó con «REF ORIG», «//» u «OEM», y que además tenés en el catálogo.",
                "Buscar el código de fábrica adentro del texto ya existía, pero **solo en el "
                "momento de importar**, detrás de una casilla que viene apagada. Si esa casilla "
                "no se tildó, ese dato no se vuelve a mirar nunca más: la descripción queda "
                "guardada con el número adentro y nadie lo lee otra vez.\n\n"
                "Y aunque se tilde, igual hace falta correrlo después: el cruce solo existe "
                "cuando están las DOS listas. Una descripción que cita «REF ORIG 0258006980» no "
                "sirve de nada hasta que se importe la lista que vende ese Bosch — y para "
                "entonces la importación de la primera ya pasó hace meses.\n\n"
                "**Solo toma los códigos DECLARADOS**, no los que se podrían adivinar. La "
                "diferencia está medida sobre tu base: los declarados dan 1,1% de pares entre "
                "familias distintas y los adivinados 8,7% (los vínculos que vos ya aprobaste a "
                "mano dan 0,8%). El motivo es simple: en «SONDA LAMBDA 80045 AUDI A3» el 80045 "
                "es el número interno de ESE proveedor, y choca con el número interno de otro "
                "sin tener nada que ver.\n\n"
                "No carga nada solo: todo va a la cola de pendientes."
            )
            if st.button("📝 Buscar los códigos escritos"):
                with st.spinner("Leyendo las descripciones del catálogo..."):
                    st.session_state["sug_escritos"] = equivalencias_escritas_en_las_descripciones()
            _st_escritos = st.session_state.get("sug_escritos")
            if _st_escritos is not None:
                if not _st_escritos:
                    st.info("No encontré pares nuevos. Si ya corriste esto antes, o tus listas "
                            "no escriben el código de fábrica en la descripción, es esperable.")
                else:
                    st.success(f"**{len(_st_escritos)} par(es) nuevos** que el proveedor dejó "
                                "escritos en la descripción.")
                    if len(_st_escritos) >= TOPE_CODIGOS_ESCRITOS:
                        st.warning(
                            f"⚠️ Se cortó en **{TOPE_CODIGOS_ESCRITOS:,} pares**, así que hay "
                            "más. Mandá estos a la cola, resolvelos, y volvé a correrlo."
                        )
                    _muestra_esc = []
                    for _a, _b in _st_escritos[:60]:
                        c.execute("""SELECT p.codigo_raw AS cod, p.descripcion AS des,
                                            m.nombre AS marca
                                     FROM productos p JOIN marcas m ON m.id = p.marca_id
                                     WHERE p.id IN (?, ?)""", (_a, _b))
                        _dos = filas_a_listas(c)
                        if len(_dos) == 2:
                            _muestra_esc.append({
                                "Marca": _dos[0]["marca"], "Código": _dos[0]["cod"],
                                "Descripción": (_dos[0]["des"] or "")[:60],
                                "Marca equivalente": _dos[1]["marca"],
                                "Código equivalente": _dos[1]["cod"],
                                "Su descripción": (_dos[1]["des"] or "")[:60],
                            })
                    if _muestra_esc:
                        st.caption(f"Muestra de {len(_muestra_esc)} de los {len(_st_escritos)}:")
                        st.dataframe(_muestra_esc, width="stretch", hide_index=True)
                    if st.button(f"📥 Mandar los {len(_st_escritos)} a la cola de pendientes",
                                 type="primary", key="mandar_sug_escritos"):
                        _n = guardar_equivalencias_pendientes(
                            list(_st_escritos), "descripcion-declarada",
                            f"escritos-{datetime.now().strftime('%d/%m %H:%M')}")
                        st.session_state.pop("sug_escritos", None)
                        avisar("ok", f"Listo: {_n} par(es) a la cola. Se aprueban en "
                                     "Estadísticas → 🔗 Equivalencias sugeridas.")
                        st.rerun()
            st.markdown("---")

            st.markdown("**🧠 Buscar equivalencias en TODO el catálogo de una**")
            explicar(
                "Lo mismo que comparar dos proveedores por descripción, pero recorriendo todas "
                "las marcas juntas en una sola pasada.",
                "Comparar de a dos proveedores funciona, pero con cinco cargados hay diez "
                "combinaciones para correr de a una, y con ocho son veintiocho. Nadie las corre "
                "todas, así que la mitad de los cruces posibles no se busca nunca.\n\n"
                "Si dos productos son o no el mismo repuesto lo decide exactamente el mismo "
                "criterio de siempre —posición, cilindrada, siglas, sustantivo principal y que "
                "coincida el auto—, así que no hay dos reglas distintas conviviendo.\n\n"
                "Lo único distinto es cómo elige qué pares mirar: comparar todo contra todo "
                "serían seis mil millones de pares sobre un catálogo de 110.000 productos. En "
                "vez de eso mira solo los que comparten alguna palabra POCO COMÚN, que quedan "
                "en unos ciento cincuenta mil y se resuelven en segundos.\n\n"
                "No carga nada solo: todo va a la cola de pendientes."
            )
            if st.button("🧠 Buscar en todo el catálogo"):
                with st.spinner("Comparando descripciones de todas las marcas..."):
                    st.session_state["sug_todas"] = sugerir_entre_todas_las_marcas()
            _st_todas = st.session_state.get("sug_todas")
            if _st_todas is not None:
                if not _st_todas:
                    st.info("No encontré pares nuevos. Si ya corriste esto antes, o tus listas "
                            "usan descripciones muy distintas entre sí, es esperable.")
                else:
                    st.success(f"**{len(_st_todas)} par(es) propuestos** entre marcas distintas.")
                    # Llegar al tope significa que hay más y no se están mostrando. Callarlo es
                    # lo que hacía creer que eso era todo lo que había: con el tope en 600 y la
                    # lista de Illinois cargada salían 787 pares y se veían 600.
                    if len(_st_todas) >= TOPE_SUGERENCIAS_TODAS:
                        st.warning(
                            f"⚠️ Se cortó en **{TOPE_SUGERENCIAS_TODAS:,} pares**, así que hay "
                            "más. Mandá estos a la cola, aprobalos o descartalos, y volvé a "
                            "correrlo: los que ya resolviste no vuelven a salir."
                        )
                    st.dataframe([{k: v for k, v in x.items() if not k.startswith("_")}
                                  for x in _st_todas],
                                 width="stretch", hide_index=True)
                    _pares_t = [(x["_a"], x["_b"]) for x in _st_todas]
                    if st.button(f"📥 Mandar los {len(_st_todas)} a la cola de pendientes",
                                 type="primary", key="mandar_sug_todas"):
                        _n = guardar_equivalencias_pendientes(
                            _pares_t, "descripcion-todas",
                            f"todas-{datetime.now().strftime('%d/%m %H:%M')}")
                        st.session_state.pop("sug_todas", None)
                        avisar("ok", f"Listo: {_n} par(es) a la cola. Se aprueban en "
                                     "Estadísticas → 🔗 Equivalencias sugeridas.")
                        st.rerun()
            st.markdown("---")

        if _grupo_mant == GRUPOS_MANTENIMIENTO[1]:
            st.markdown("**🕵️ Puentes falsos: códigos que unen repuestos que no tienen nada que ver**")
            explicar(
                "Busca códigos de fábrica que estén fusionando familias enteras de repuestos, "
                "y te deja borrarlos de a uno.",
                "Es el peor daño que puede tener esta base y el más difícil de ver. Un solo "
                "código malo no agrega un resultado de más: fusiona DOS FAMILIAS ENTERAS. Pasó "
                "de verdad acá — buscando una bobina de ignición aparecían un sensor de masa de "
                "aire de Mazda y un sensor de temperatura de Corolla, porque las tres "
                "descripciones nombraban la 4Runner y de ahí salió «4RUNNER» como si fuera un "
                "código de fábrica.\n\nMirando los resultados de a uno no se nota: cada vínculo "
                "suelto parece razonable. Se nota mirando el catálogo entero.\n\nSe cruzan dos "
                "señales, porque ninguna sola alcanza:\n\n"
                "- **cuántos productos cuelga**: el 99,9% de los códigos de fábrica verdaderos "
                "unen 4 o menos, porque son el mismo repuesto en unos pocos proveedores;\n"
                "- **de qué familia es lo que une**: un código real une repuestos de la misma "
                "familia. Si une un filtro con un cilindro maestro, no es un código, es una "
                "palabra que las dos descripciones mencionan.\n\n"
                "No borra nada solo, a propósito: un corte automático se llevaría por delante "
                "los códigos populares de verdad, que son los más valiosos. Decidís vos."
            )
            if st.button("🕵️ Buscar puentes falsos"):
                with st.spinner("Revisando todo el catálogo..."):
                    st.session_state["puentes_falsos"] = puentes_sospechosos()
            _pf = st.session_state.get("puentes_falsos")
            if _pf is not None:
                if not _pf:
                    st.success("No encontré ningún código de fábrica uniendo cosas que no van "
                               "juntas. La base está limpia de puentes falsos.")
                else:
                    st.warning(f"**{len(_pf)} código(s) sospechoso(s).** Mirá los ejemplos de "
                               "cada uno: si lo que une no tiene nada que ver entre sí, borralo.")
                    for _p in _pf:
                        with st.expander(f"🔗 {_p['Código']} — {_p['Por qué sospecha']}"):
                            st.caption(f"Familias que toca: {_p['Familias']}")
                            st.write(_p["Ejemplos"])
                            if candado('borrar un código de fábrica falso', st.button("🗑️ Borrar este puente y sus vínculos", key=f"borrar_puente_{_p['pid']}"), 'borrar_un_c_digo_de_f_brica_falso'):
                                _n = borrar_puente(_p["pid"])
                                # La lista guardada queda vieja apenas se borra uno: si no se
                                # saca de ahí, el botón sigue apareciendo y al tocarlo de nuevo
                                # no borra nada, que es la peor forma de no funcionar.
                                st.session_state["puentes_falsos"] = [
                                    x for x in _pf if x["pid"] != _p["pid"]]
                                avisar("ok", f"Listo: se borró «{_p['Código']}» y los {_n} "
                                             "vínculos falsos que colgaban de él.")
                                st.rerun()
            st.markdown("---")

        if _grupo_mant == GRUPOS_MANTENIMIENTO[0]:
            # Leer las equivalencias que el propio proveedor publica en su catálogo web. Es la
            # misma fuente que ya se usa para las fotos y para los autos de cada ficha; lo que
            # faltaba era leer los números cruzados que la ficha lista.
            c.execute("""SELECT m.id, m.nombre, COUNT(p.id) AS productos
                         FROM marcas m JOIN productos p ON p.marca_id = m.id
                         WHERE m.url_ficha_template IS NOT NULL AND m.url_ficha_template <> ''
                         GROUP BY m.id ORDER BY productos DESC""")
            marcas_con_ficha = [dict(r) for r in c.fetchall()]

            st.markdown("**🌐 Leer equivalencias del catálogo digital del proveedor**")
            explicar(
                "Entra a la ficha de cada código en la web del proveedor y trae los códigos "
                "cruzados que estén publicados ahí.",
                "Muchas fichas listan las referencias cruzadas —«equivale a», «OEM», «cross "
                "reference»—, que es justo lo que uno cargaría a mano código por código.\n\n"
                "Hace falta que la marca tenga cargada la **dirección de su catálogo** en "
                "Administrar → Marcas, con `{codigo}` donde va el número.\n\n"
                "Dos límites que conviene saber de entrada: si la ficha arma su contenido con "
                "JavaScript, lo que llega es la página vacía y no se lee nada — no todos los "
                "catálogos se dejan; y solo se proponen códigos que YA tengas cargados, porque "
                "una equivalencia contra algo que no tenés no se puede ni vender ni buscar.\n\n"
                "Nada se carga solo: todo va a la misma cola de revisión. Una ficha también "
                "lista accesorios y kits, y eso no es una equivalencia."
            )
            if not marcas_con_ficha:
                # Se nombran las marcas que SÍ tenés cargadas. «Ninguna marca tiene cargada la
                # dirección» se lee como «la app no ve mi lista» cuando en realidad la ve: lo
                # que falta es la dirección web, que es otra cosa que la lista de productos.
                try:
                    c.execute("""SELECT m.nombre, COUNT(p.id) AS n
                                 FROM marcas m JOIN productos p ON p.marca_id = m.id
                                 WHERE m.tipo <> 'OEM'
                                 GROUP BY m.id ORDER BY n DESC LIMIT 8""")
                    _sin_dir = [f"{r['nombre']} ({r['n']:,} productos)" for r in c.fetchall()]
                except sqlite3.OperationalError as _err:
                    anotar_error("catálogo digital", _err)
                    _sin_dir = []
                st.info(
                    "Ninguna marca tiene cargada la **dirección web** de su catálogo. Es otra "
                    "cosa que la lista de productos: la lista ya está cargada, lo que falta es "
                    "el link a la ficha de cada código.\n\n"
                    + ("Tus proveedores cargados: " + ", ".join(_sin_dir) + ".\n\n"
                       if _sin_dir else "")
                    + "Se carga en Administrar → 🏷️ Marcas, en «patrón de link»: ahí la tabla "
                      "tiene una columna **Catálogo web** que dice cuáles ya lo tienen."
                )
            else:
                # Qué catálogos tienen usuario y contraseña cargados. Sin esto, configurarlos es
                # invisible: se carga el secreto en el panel de Streamlit y no hay forma de
                # saber desde la app si quedó bien escrito el nombre de la marca —que tiene que
                # coincidir exactamente— hasta que una tanda entera falla.
                _con_clave = [m["nombre"] for m in marcas_con_ficha
                              if credenciales_de_catalogo(m["nombre"])]
                _sin_clave = [m["nombre"] for m in marcas_con_ficha
                              if not credenciales_de_catalogo(m["nombre"])]
                if _con_clave:
                    st.caption("🔐 Entran con usuario y contraseña: "
                               + ", ".join(f"**{x}**" for x in _con_clave)
                               + (f" · sin contraseña: {', '.join(_sin_clave)}"
                                  if _sin_clave else ""))
                    if st.button("🔄 Volver a entrar al catálogo", key="relogin_catalogo",
                                  help="Si las fichas empezaron a fallar todas juntas, lo más "
                                       "probable es que haya vencido la sesión. Esto la tira y "
                                       "la próxima consulta vuelve a ingresar."):
                        olvidar_sesion_de_catalogo()
                        avisar("ok", "Listo: la próxima consulta vuelve a ingresar al catálogo.")
                with st.expander("🔐 ¿El catálogo pide usuario y contraseña?"):
                    st.markdown(
                        "Se puede, y **la contraseña no se guarda en la app**: va en los "
                        "secretos de Streamlit. Es a propósito — todo lo que se guarda en la "
                        "app sale en el backup automático al repositorio y en el botón de bajar "
                        "la base, así que una contraseña guardada ahí terminaría copiada en el "
                        "repositorio.\n\n"
                        "En el panel de Streamlit Cloud → **Settings → Secrets**, una sección "
                        "por marca, con el nombre **igual** a como está cargada acá:\n\n"
                        "```toml\n"
                        "[catalogo.MOTORARG]\n"
                        'url_login = "https://ejemplo.com/ingresar"\n'
                        'usuario = "micuenta@ejemplo.com"\n'
                        'clave = "loquesea"\n'
                        'campo_usuario = "email"     # cómo llama el sitio al campo\n'
                        'campo_clave = "password"\n'
                        "```\n\n"
                        "Los dos nombres de campo salen de mirar el formulario de ingreso del "
                        "proveedor: cada sitio los llama distinto y no se pueden adivinar.\n\n"
                        "**Avisale al proveedor.** Sos cliente y tenés acceso, pero muchos "
                        "catálogos prohíben en sus condiciones consultarlos de forma "
                        "automatizada, y cientos de consultas seguidas pueden hacer que te "
                        "corten el usuario. Pedir permiso —o directamente el archivo— suele ser "
                        "más rápido que todo esto."
                    )

                # Lo mismo que con las fotos: son miles de fichas y sentarse a esperar no es
                # opción, así que puede avanzar solo de a 15 por día. Sale a internet, por eso
                # se elige a mano. Al lado va cuánto falta, que es lo que dice si sirve
                # prenderlo: sin el número, «automático» no se sabe si termina en una semana o
                # en dos años.
                st.checkbox(
                    "🤖 Leer las fichas solas, en segundo plano",
                    value=obtener_config("equiv_ficha_automaticas", "0") == "1",
                    key="equiv_ficha_auto_check",
                    on_change=lambda: guardar_config(
                        "equiv_ficha_automaticas",
                        "1" if st.session_state["equiv_ficha_auto_check"] else "0"),
                    help="Mientras la app esté abierta, va leyendo fichas del catálogo del "
                         "proveedor en un hilo aparte y manda a revisión las equivalencias que "
                         "encuentre escritas ahí. Avanza siempre sobre códigos nuevos."
                )
                if obtener_config("equiv_ficha_automaticas", "0") == "1":
                    mostrar_avance_de_tanda("equiv", "tanda_equiv_diaria", "ficha(s)")

                opciones_mf = {f"{m['nombre']} ({m['productos']} códigos)": m["id"]
                               for m in marcas_con_ficha}
                elegida_mf = st.selectbox("Marca:", list(opciones_mf.keys()),
                                           key="marca_equiv_catalogo")
                # El valor por defecto va por session_state y no por value=: con key= puesto,
                # Streamlit ignora value= a partir del segundo dibujo y el slider parece que
                # "no obedece". Es la misma forma que usa el resto de la app.
                st.session_state.setdefault("tanda_equiv_catalogo", 25)
                cuantos_mf = st.select_slider(
                    "Cuántas fichas consultar en esta tanda:", options=[10, 25, 50, 100, 200],
                    key="tanda_equiv_catalogo",
                    help="Cada ficha es una consulta al sitio del proveedor. De a poco primero, "
                         "para ver si ese catálogo se deja leer antes de pedirle 200 páginas.")
                if st.button("🌐 Leer las fichas y proponer equivalencias"):
                    barra_mf = st.progress(0.0)
                    with st.spinner("Consultando el catálogo del proveedor..."):
                        _props, _falla, _consult = equivalencias_desde_catalogo(
                            opciones_mf[elegida_mf], limite=int(cuantos_mf),
                            progreso=lambda hechos, total: barra_mf.progress(
                                min(hechos / max(total, 1), 1.0)))
                    barra_mf.empty()
                    st.session_state["equiv_catalogo"] = {
                        "propuestas": _props, "fallidas": _falla,
                        "consultados": _consult, "marca": elegida_mf.split(" (")[0]}
                _ec = st.session_state.get("equiv_catalogo")
                if _ec is not None:
                    st.caption(f"Se consultaron {_ec['consultados']} ficha(s); "
                               f"{len(_ec['fallidas'])} no se pudieron leer.")
                    if not _ec["propuestas"]:
                        st.info(
                            "No salió ninguna equivalencia. O ese catálogo no publica las "
                            "referencias cruzadas, o arma la página con JavaScript y llega "
                            "vacía, o los códigos que lista todavía no están en tus listas."
                        )
                        if _ec["fallidas"]:
                            st.dataframe(
                                [{"Código": cod, "Qué pasó": err}
                                 for cod, err in _ec["fallidas"][:30]],
                                width="stretch", hide_index=True)
                    else:
                        st.success(f"Se encontraron **{len(_ec['propuestas'])} equivalencia(s)** "
                                   "publicadas en las fichas.")
                        st.dataframe(
                            [{k: v for k, v in x.items() if not k.startswith("_")}
                             for x in _ec["propuestas"][:100]],
                            width="stretch", hide_index=True)
                        if st.button(f"📥 Mandar las {len(_ec['propuestas'])} a revisión",
                                      type="primary", key="btn_equiv_catalogo_guardar"):
                            _n = guardar_equivalencias_de_catalogo(_ec["propuestas"], _ec["marca"])
                            st.session_state.pop("equiv_catalogo", None)
                            invalidar_salud()
                            avisar("success", f"{_n} equivalencia(s) quedaron para revisar.")
                            st.rerun()
            st.markdown("---")

        if _grupo_mant == GRUPOS_MANTENIMIENTO[5]:
            # CUÁNTO ATRASADOS ESTÁN LOS PRECIOS. Va acá, al lado de las importaciones, porque
            # lo que se hace con este número es pedir la lista nueva.
            st.markdown("**⏳ Qué tan atrasada está cada lista**")
            explicar(
                "Los días que pasaron desde la última carga y, si la importaste más de una vez, "
                "a qué ritmo viene aumentando.",
                "No usa ningún índice ni ninguna consulta: sale de tu propio historial de "
                "precios. La app ya guarda cada cambio, así que puede medir cuánto aumentó ESE "
                "proveedor entre tus importaciones y cruzarlo con los días que pasaron.\n\n"
                "El ritmo sale de la MEDIANA y no del promedio a propósito: en cada lista hay "
                "siempre un puñado de productos que pasan de 100 a 100.000 porque cambió la "
                "unidad, y con el promedio esos pocos deciden el número de toda la lista.\n\n"
                "Hace falta haber importado la misma lista al menos dos veces. Con una sola, la "
                "app te dice los días y nada más — y aprende sola en la próxima."
            )
            _envejecidas = envejecimiento_de_precios()
            if _envejecidas:
                st.dataframe(quitar_id(_envejecidas), width="stretch", hide_index=True)
                _peor = _envejecidas[0]
                if _peor["_ritmo"] is not None and _peor["_atraso"] >= 0.05:
                    st.warning(
                        f"⏳ **Los precios de {_peor['Lista']} estarían "
                        f"{_peor['Estarían atrasados']} abajo.** La lista tiene "
                        f"{_peor['_dias']} días y viene subiendo {_peor['Sube por mes']} por "
                        "mes. Cada venta de esa lista se hace con esa diferencia en contra."
                    )
                elif all(x["_ritmo"] is None for x in _envejecidas):
                    st.caption(
                        "Todavía no puedo medir el ritmo de ninguna lista: hace falta haber "
                        "importado la misma al menos dos veces. Los días sí valen."
                    )

                # El contexto de afuera, que es lo único que esta app va a buscar a internet
                # además de los catálogos de los proveedores. No decide nada: el ritmo con el
                # que se decide sigue siendo el de TUS importaciones. Sirve para dos cosas que
                # el historial propio no puede contestar: si el proveedor viene subiendo por
                # debajo de la inflación —o sea que está quedando barato y conviene comprarle
                # ahora— y cuánto se movió el dólar, que es lo que manda en lo importado.
                _ctx = contexto_de_precios()
                if _ctx:
                    _lineas = []
                    _d = _ctx.get("dolar") or {}
                    # Las claves son TEXTO y no números: esto pasa por json para guardarse en
                    # la base, y JSON no tiene claves numéricas — al volver, el 30 es "30".
                    # Buscándolo como número no se encuentra nunca y la línea no aparecía.
                    _var = _d.get("variacion") or {}
                    if _var.get("30") is not None:
                        _lineas.append(
                            f"El **dólar oficial** subió "
                            f"{_var['30'] * 100:.1f}% en los últimos 30 días"
                            + (f" y {_var['90'] * 100:.1f}% en 90"
                               if _var.get("90") is not None else "")
                            + f" (al {_d.get('fecha', 'sin fecha')}).")
                    _i = _ctx.get("ipc") or {}
                    if _i.get("variacion") is not None:
                        _lineas.append(
                            f"La **inflación** del último mes publicado por el INDEC "
                            f"({_i.get('mes', '')[:7]}) fue {_i['variacion'] * 100:.1f}%.")
                        # La comparación que sirve: quién sube menos que la inflación.
                        _baratas = [x["Lista"] for x in _envejecidas
                                    if x["_ritmo"] is not None
                                    and x["_ritmo"] < _i["variacion"] - 0.01]
                        if _baratas:
                            _lineas.append(
                                "Vienen subiendo **por debajo** de eso: "
                                + ", ".join(f"**{x}**" for x in _baratas)
                                + " — ese proveedor está quedando barato.")
                    if _lineas:
                        st.info("🌎 " + "  \n".join(_lineas)
                                + ("\n\n⚠️ Son los últimos datos que pude traer, no los de hoy: "
                                   "ahora mismo no llego a internet."
                                   if _ctx.get("viejos") else ""))
            st.markdown("---")

            st.markdown("**↩️ Deshacer una importación**")
            explicar(
                "Saca de una todos los vínculos que dejó una lista.",
                "Es la red de seguridad que faltaba: hasta ahora, si una lista venía mal mapeada, la "
                "única salida era borrar de a uno entre miles. **Los productos no se tocan**: precios, "
                "stock, ubicación e historial quedan como están. Se deshace solo la parte peligrosa, "
                "que son los vínculos."
            )
            importaciones = listar_importaciones_deshacibles()
            if importaciones:
                st.dataframe(quitar_id(importaciones), width="stretch", hide_index=True)
                etiquetas_imp = {
                    f"{i['Marca']} · {i['Archivo']} · {i['Fecha']} "
                    f"({i['Vínculos vivos']} vivos, {i['Sin revisar']} sin revisar)": i["_lote"]
                    for i in importaciones if (i["Vínculos vivos"] or i["Sin revisar"])
                }
                if etiquetas_imp:
                    elegida_imp = st.selectbox("¿Cuál deshacer?", list(etiquetas_imp.keys()),
                                                key="importacion_deshacer")
                    lote_elegido = etiquetas_imp[elegida_imp]
                    previo = previsualizar_deshacer(lote_elegido)
                    st.warning(
                        f"Se van a borrar **{previo['vinculos']} vínculo(s) ya cargados** y "
                        f"**{previo['pendientes']} sin revisar**. Quedan registrados como rechazados, "
                        "así que si volvés a importar la misma lista no se vuelven a crear solos."
                    )
                    if st.checkbox("Entiendo que esto borra esos vínculos", key="confirmar_deshacer_imp"):
                        if candado('deshacer una importación', st.button("↩️ Deshacer esta importación", type="primary"), 'deshacer_una_importaci_n'):
                            nv, npd = deshacer_importacion(lote_elegido)
                            invalidar_salud()
                            avisar("success", f"Se deshicieron {nv} vínculo(s) cargados y {npd} pendientes.")
                            st.rerun()
            else:
                st.caption(
                    "Todavía no hay importaciones con origen registrado. Las listas que importes de "
                    "acá en adelante van a poder deshacerse; las anteriores no guardaron de dónde "
                    "venía cada vínculo."
                )

        if _grupo_mant == GRUPOS_MANTENIMIENTO[1]:
            espejadas = contar_equivalencias_espejadas()
            if espejadas:
                st.markdown("---")
                st.markdown("**🔁 Equivalencias anotadas dos veces**")
                st.warning(
                    f"⚠️ Hay {espejadas:,} equivalencia(s) guardadas por duplicado: la misma relación "
                    "anotada en las dos direcciones (A↔B y B↔A). No son vínculos distintos, es la "
                    "misma información dos veces."
                )
                explicar(
                    "No cambia lo que encuentra el buscador —consulta las dos columnas igual—, pero sí "
                    "infla todos los conteos:",
                    "un código con 100 equivalencias reales figura con 200, y el control de precios lista "
                    "cada par dos veces. Unificarlas no borra ninguna equivalencia, solo deja una sola fila "
                    "por cada una."
                )
                if st.button("🔁 Unificar duplicadas"):
                    borradas, vueltas = unificar_equivalencias_espejadas()
                    invalidar_salud()
                    avisar("success", f"Se unificaron {borradas:,} duplicadas "
                                       f"y se ordenaron {vueltas:,}.")
                    st.rerun()

        if _grupo_mant == GRUPOS_MANTENIMIENTO[4]:
            st.markdown("**📷 Traer fotos de productos en tanda**")
            st.caption(
                "En vez de cargarlas de a una. No existe ninguna base pública y gratuita de fotos por "
                "número de parte (la del rubro, TecDoc, es paga), así que las dos fuentes confiables son: "
                "el link que ya venga en tu lista, o la ficha del propio proveedor."
            )

            modo_liviano = st.checkbox(
                "Modo liviano (recomendado): guardar el link de la foto, no la foto entera",
                value=True, key="fotos_modo_liviano",
                help="La foto se sigue viendo y se sigue pudiendo buscar por parecido, porque la firma "
                     "visual y la miniatura sí se guardan. Lo que no se guarda es la imagen grande: "
                     "esa la trae el navegador desde el sitio del proveedor."
            )
            kb_por_foto = peso_estimado_por_foto(modo_liviano)

            pendientes_url = contar_fotos_por_bajar()
            if pendientes_url:
                st.info(f"Hay {pendientes_url} producto(s) con la foto como link externo, sin bajar.")
                # OJO: en select_slider el value TIENE que ser uno de los options. Antes acá iba
                # min(500, pendientes) y con 347 pendientes tiraba excepción y se caía toda la
                # pestaña de Mantenimiento — de ahí que la carga de fotos apareciera "rota".
                opciones_url = [100, 250, 500, 1000, 2000]
                st.session_state.setdefault("cuantas_fotos_url", 500)
                cuantas_url = st.select_slider("¿Cuántas bajar?", options=opciones_url,
                                                key="cuantas_fotos_url")
                if st.button(f"⬇️ Bajar {cuantas_url} fotos de esos links"):
                    barra = st.progress(0.0, text="Bajando fotos...")
                    bajadas, fallidas = bajar_fotos_pendientes(
                        int(cuantas_url), liviano=modo_liviano,
                        progreso=lambda i, t: barra.progress(i / max(t, 1), text=f"Foto {i} de {t}...")
                    )
                    barra.empty()
                    st.success(f"Se bajaron {bajadas} foto(s).")
                    if fallidas:
                        with st.expander(f"⚠️ {len(fallidas)} no se pudieron bajar"):
                            for url_f, motivo in fallidas[:30]:
                                st.caption(f"- {str(url_f)[:60]}: {motivo}")
            else:
                st.caption("✅ No hay fotos pendientes de bajar desde links.")

            c.execute("""SELECT m.id, m.nombre, COUNT(p.id) AS sin_foto
                         FROM marcas m JOIN productos p ON p.marca_id = m.id
                         WHERE m.url_ficha_template IS NOT NULL AND m.url_ficha_template <> ''
                           AND p.imagen_url IS NULL
                           AND (p.foto_busqueda_estado IS NULL OR p.foto_busqueda_estado = 'error')
                         GROUP BY m.id HAVING sin_foto > 0 ORDER BY sin_foto DESC""")
            marcas_con_catalogo = [dict(r) for r in c.fetchall()]

            if marcas_con_catalogo:
                st.markdown("**Traerlas desde la ficha del proveedor**")
                opciones_mc = {f"{m['nombre']} ({m['sin_foto']} por probar)": m["id"] for m in marcas_con_catalogo}
                elegida_mc = st.selectbox("Marca:", list(opciones_mc.keys()), key="marca_fotos_catalogo")
                id_marca_fotos = opciones_mc[elegida_mc]

                etiquetas_filtro = {
                    "stock": "Solo los que tienen stock",
                    "precio": "Solo los que tienen precio cargado",
                    "todos": "Todos los códigos de la marca",
                }
                filtro_fotos = st.radio(
                    "¿Para cuáles traer foto?", list(etiquetas_filtro.keys()),
                    format_func=lambda k: etiquetas_filtro[k], key="filtro_fotos_catalogo",
                    help="Traer foto de TODO un catálogo de miles de códigos llena la base y hace que "
                         "el backup ya no entre en GitHub. Empezar por los que tienen stock cubre lo "
                         "que realmente movés."
                )
                faltan_marca = contar_fotos_por_traer_de_catalogo(id_marca_fotos, filtro_fotos)
                faltan_todos = contar_fotos_por_traer_de_catalogo(id_marca_fotos, "todos")
                if filtro_fotos != "todos":
                    st.caption(f"Con ese filtro quedan {faltan_marca:,} de {faltan_todos:,} códigos.")

                explicar(
                    "Entra a la ficha de cada código y busca la foto ahí.",
                    "Ahora va de a 6 fichas a la vez en vez de una por una, así que rinde bastante más. Los "
                    "códigos cuya ficha no tiene foto quedan marcados y no se vuelven a consultar, para que "
                    "cada tanda avance de verdad."
                )

                cf_a, cf_b = st.columns(2)
                with cf_a:
                    st.session_state.setdefault("tanda_fotos_catalogo", 500)
                    tanda_fotos = st.select_slider(
                        "Fotos por tanda:", options=[100, 250, 500, 1000, 2000],
                        key="tanda_fotos_catalogo"
                    )
                with cf_b:
                    st.session_state.setdefault("hilos_fotos", 6)
                    hilos_fotos = st.select_slider(
                        "Fichas a la vez:", options=[3, 6, 10, 15], key="hilos_fotos",
                        help="Más rápido, pero es el sitio del proveedor el que atiende: si te pasás "
                             "puede empezar a rechazar los pedidos y no baja ninguna."
                    )

                mb_estimados = faltan_marca * kb_por_foto / 1024
                st.caption(
                    f"Cada foto ocupa unos {kb_por_foto} KB en la base "
                    f"({'modo liviano' if modo_liviano else 'guardando la imagen entera'}). "
                    f"Las {faltan_marca:,} de este filtro serían unos {mb_estimados:,.0f} MB."
                )
                if mb_estimados > 80:
                    st.warning(
                        f"⚠️ {mb_estimados:,.0f} MB no entran en el backup de GitHub (tope 100 MB), y "
                        "como el hosting borra el disco al reiniciar y restaura desde ahí, esas fotos "
                        "se te van a perder en cada reinicio. "
                        + ("Probá con «solo los que tienen stock»: es lo que realmente movés."
                            if filtro_fotos == "todos" else
                            "Aun con el filtro es mucho: convendría traerlas de a poco, empezando por "
                            "las marcas que más vendés.")
                    )

                en_curso = st.session_state.get("bajada_fotos_en_curso")

                bc1, bc2 = st.columns(2)
                if not en_curso:
                    if bc1.button(f"🌐 Traer una tanda de {tanda_fotos}", type="primary"):
                        st.session_state["bajada_fotos_en_curso"] = {
                            "marca_id": id_marca_fotos, "restantes": int(tanda_fotos),
                            "bajadas": 0, "sin_foto": 0, "fallos": 0, "hasta_terminar": False,
                        }
                        st.rerun()
                    if bc2.button(f"♾️ Seguir hasta terminar las {faltan_marca:,}",
                                   disabled=not faltan_marca):
                        st.session_state["bajada_fotos_en_curso"] = {
                            "marca_id": id_marca_fotos, "restantes": faltan_marca,
                            "bajadas": 0, "sin_foto": 0, "fallos": 0, "hasta_terminar": True,
                        }
                        st.rerun()
                else:
                    if st.button("⏹️ Detener", type="primary"):
                        st.session_state.pop("bajada_fotos_en_curso", None)
                        st.rerun()
                    if en_curso["marca_id"] != id_marca_fotos:
                        # Si no se avisa, cambiar de marca en el selector deja la bajada colgada:
                        # el bloque de abajo no corre, no se refresca sola, y parece que se trabó.
                        c.execute("SELECT nombre FROM marcas WHERE id = ?", (en_curso["marca_id"],))
                        otra = c.fetchone()
                        st.warning(
                            f"Hay una bajada en curso de **{otra['nombre'] if otra else 'otra marca'}** "
                            f"({en_curso['bajadas']} foto(s) hasta ahora). Volvé a elegir esa marca para "
                            "que siga, o tocá Detener."
                        )

                # La bajada se hace en pedazos, y entre pedazo y pedazo la pantalla se refresca. Si se
                # hiciera todo de un saque, una tanda de 2.000 fotos serían 20 minutos con la pantalla
                # colgada — y el navegador o el hosting cortan la conexión mucho antes de eso.
                if en_curso and en_curso["marca_id"] == id_marca_fotos:
                    # Pedazos chicos a propósito: entre pedazo y pedazo es cuando se puede tocar
                    # "Detener", así que con tandas grandes el botón tardaría un minuto en responder.
                    pedazo = min(en_curso["restantes"], 90)
                    barra2 = st.progress(
                        0.0, text=f"Consultando fichas... (llevamos {en_curso['bajadas']} foto(s))"
                    )
                    bajadas2, fallidas2, sin_foto2 = bajar_fotos_desde_catalogo(
                        id_marca_fotos, pedazo, liviano=modo_liviano, hilos=int(hilos_fotos),
                        filtro=filtro_fotos,
                        progreso=lambda i, t: barra2.progress(min(i / max(t, 1), 1.0),
                                                              text=f"Ficha {i} de {t}...")
                    )
                    barra2.empty()
                    en_curso["bajadas"] += bajadas2
                    en_curso["sin_foto"] += sin_foto2
                    en_curso["fallos"] += max(len(fallidas2) - sin_foto2, 0)
                    procesadas = bajadas2 + len(fallidas2)
                    en_curso["restantes"] -= max(procesadas, 1)

                    if procesadas == 0 or en_curso["restantes"] <= 0:
                        st.session_state.pop("bajada_fotos_en_curso", None)
                        st.success(
                            f"Listo: {en_curso['bajadas']} foto(s) traídas, "
                            f"{en_curso['sin_foto']} código(s) sin foto en la ficha, "
                            f"{en_curso['fallos']} con error de red."
                        )
                        if fallidas2:
                            with st.expander(f"Ver los últimos {min(len(fallidas2), 30)} que no salieron"):
                                for cod_f, motivo in fallidas2[:30]:
                                    st.caption(f"- {cod_f}: {motivo}")
                    else:
                        st.session_state["bajada_fotos_en_curso"] = en_curso
                        st.caption(
                            f"Van {en_curso['bajadas']} foto(s) — quedan unas {en_curso['restantes']:,}. "
                            "Dejá esta pantalla abierta; sigue sola."
                        )
                        st.rerun()
            else:
                st.caption(
                    "Para traer fotos del catálogo hace falta cargar la dirección de la ficha de la marca "
                    "en Administrar → Marcas."
                )

            c.execute("SELECT COUNT(*) FROM productos WHERE foto_busqueda_estado = 'sin_foto'")
            marcados_sin_foto = c.fetchone()[0]
            if marcados_sin_foto:
                st.caption(
                    f"🔕 {marcados_sin_foto:,} código(s) quedaron marcados como «la ficha no tiene foto» "
                    "y ya no se vuelven a consultar."
                )
                if st.button("🔄 Volver a probar esos códigos"):
                    avisar("success", f"Se rehabilitaron {reintentar_codigos_sin_foto()} código(s).")
                    st.rerun()

        if _grupo_mant == GRUPOS_MANTENIMIENTO[3]:
            # LA PARTE QUE SE ARREGLA SOLA. Si el problema es que entró la columna del
            # código de barras, no hace falta reimportar nada: el número ya está cargado,
            # solo está en el lugar equivocado. Se mueve a la columna que le corresponde y
            # se saca el vínculo falso que arrastraba.
            _barras_mal = codigos_de_barras_mal_cargados()
            if _barras_mal:
                st.markdown("**🏷️ Códigos de barras cargados como código de fábrica**")
                st.dataframe(
                    [{k: v for k, v in f.items() if k != "marca_id"} for f in _barras_mal],
                    width="stretch", hide_index=True)
                st.caption(
                    "Se pueden pasar a su lugar sin reimportar: el número queda guardado en "
                    "el producto —se sigue pudiendo escanear y buscar— y lo que desaparece "
                    "es la equivalencia que no llevaba a ningún lado."
                )
                for _lista in _barras_mal:
                    _n = _lista["Códigos de barras cargados como código de fábrica"]
                    if candado(f"mover los códigos de barras de {_lista['Lista']}",
                                st.button(f"🏷️ Arreglar los {_n:,} de {_lista['Lista']}",
                                           key=f"barras_{_lista['marca_id']}"),
                                f"barras_{_lista['marca_id']}"):
                        _mov, _ya = mover_codigos_de_barras_a_su_columna(_lista["marca_id"])
                        avisar("success",
                                f"Se movieron {_mov:,} código(s) de barras a su columna y se "
                                f"sacaron {_mov:,} vínculo(s) que no llevaban a ningún lado."
                                + (f" {_ya:,} producto(s) ya tenían uno cargado y se respetó."
                                   if _ya else ""))
                        st.rerun()

            # PEGARLE LOS CÓDIGOS DE BARRAS A LO QUE YA ESTÁ CARGADO.
            # El caso es el del negocio que ya etiquetó toda su mercadería: los números existen
            # y están pegados en las cajas, lo que falta es que la app los sepa. Antes la única
            # forma era reimportar la lista entera del proveedor con la columna mapeada, que
            # pisa precios, pisa stock y genera un lote de equivalencias para revisar.
            st.markdown("**🏷️ Cargar códigos de barras en masa**")
            explicar(
                "Subís dos columnas —código del producto y código de barras— y se pegan. No "
                "toca nada más.",
                "Es para cuando ya tenés la mercadería etiquetada y lo que falta es que la app "
                "lo sepa. **No se tocan precios, ni stock, ni equivalencias, ni se crea ningún "
                "producto**: solo se le pega el número al que ya está cargado.\n\n"
                "El archivo puede ser Excel o CSV, con encabezado o sin él. Si un código no "
                "está en el catálogo se informa y no se inventa nada: un producto fantasma con "
                "una etiqueta pegada no le sirve a nadie.\n\n"
                "**Conviene elegir la lista.** El mismo código de fábrica lo usan varios "
                "proveedores, y sin elegir no hay forma de saber a cuál de todos va esa "
                "etiqueta."
            )
            _arch_barras = subir_archivo("Archivo con código y código de barras:",
                                          ["xlsx", "xls", "csv", "txt"], "arch_barras_masivo")
            if _arch_barras is not None:
                try:
                    _filas_b = leer_excel(_arch_barras, nrows=100000)
                except Exception as _err:
                    anotar_error("carga masiva de barras", _err)
                    _filas_b = []
                if not _filas_b:
                    st.error("No pude leer ese archivo.")
                else:
                    _anchos = max(len(f) for f in _filas_b[:50])
                    _cols = [f"Columna {i + 1}" + (f" — «{_filas_b[0][i]}»"
                                                    if i < len(_filas_b[0]) and _filas_b[0][i]
                                                    else "")
                             for i in range(_anchos)]
                    cB1, cB2 = st.columns(2)
                    _i_cod = cB1.selectbox("Columna del código del producto:", range(_anchos),
                                            format_func=lambda i: _cols[i], key="bm_cod")
                    _i_bar = cB2.selectbox("Columna del código de barras:", range(_anchos),
                                            format_func=lambda i: _cols[i],
                                            index=min(1, _anchos - 1), key="bm_bar")
                    _saltar = st.checkbox("La primera fila es el encabezado", value=True,
                                           key="bm_encabezado")
                    c.execute("""SELECT m.id, m.nombre, COUNT(p.id) AS n FROM marcas m
                                 JOIN productos p ON p.marca_id = m.id
                                 WHERE m.tipo <> 'OEM' GROUP BY m.id ORDER BY n DESC""")
                    _marcas_b = filas_a_listas(c)
                    _opc_b = {"— todas las listas (más riesgoso) —": None}
                    _opc_b.update({f"{m['nombre']} ({m['n']:,})": m["id"] for m in _marcas_b})
                    _marca_b = _opc_b[st.selectbox("¿De qué lista son estos códigos?",
                                                    list(_opc_b.keys()), key="bm_marca")]
                    _pisar = st.checkbox("Pisar los que ya tengan un código de barras cargado",
                                          value=True, key="bm_pisar")

                    _pares_b = []
                    for _f in (_filas_b[1:] if _saltar else _filas_b):
                        if _i_cod < len(_f) and _i_bar < len(_f):
                            _c1 = valor_codigo(_f[_i_cod])
                            _c2 = valor_codigo(_f[_i_bar])
                            if _c1 and _c2:
                                _pares_b.append((_c1, _c2))
                    _rotos_prev = [(a, b) for a, b in _pares_b if excel_le_comio_digitos(b)]
                    if _rotos_prev:
                        st.error(
                            f"🛑 **Excel se comió los dígitos de {len(_rotos_prev):,} código(s) "
                            f"de barras.** Vienen escritos como `{_rotos_prev[0][1]}` y el "
                            "número entero ya no está en el archivo: no hay forma de "
                            "recuperarlo desde acá, y reconstruirlo daría un código que parece "
                            "válido y está mal.\n\n"
                            "**Cómo se arregla:** volvé a exportar el archivo con esa columna "
                            "como **texto**. En Excel: seleccionás la columna → clic derecho → "
                            "Formato de celdas → Texto, y recién ahí guardás. Si el archivo "
                            "salió de otro sistema, bajalo como CSV y **no lo abras con Excel** "
                            "antes de subirlo — abrirlo y guardarlo es lo que los rompe.\n\n"
                            "Esas filas no se van a cargar. El resto sí."
                        )
                    st.caption(f"{len(_pares_b):,} fila(s) con los dos datos"
                                + (f", {len(_pares_b) - len(_rotos_prev):,} cargables."
                                   if _rotos_prev else "."))
                    if _pares_b:
                        st.dataframe([{"Código": a, "Código de barras": b,
                                        "¿Cierra la cuenta?":
                                            {True: "sí", False: "no", None: "no es un EAN"}[
                                                codigo_de_barras_cierra(b)]}
                                       for a, b in _pares_b[:8]],
                                      width="stretch", hide_index=True)
                        if candado("cargar códigos de barras en masa",
                                    st.button(f"🏷️ Pegar los {len(_pares_b):,} códigos de barras",
                                               type="primary", key="bm_aplicar"),
                                    "bm_aplicar_candado"):
                            _res = cargar_codigos_de_barras_masivo(_pares_b, _marca_b, _pisar)
                            _partes = [f"{_res['puestos']:,} código(s) de barras cargados"]
                            if _res["sin_cambio"]:
                                _partes.append(f"{_res['sin_cambio']:,} ya estaban igual")
                            if _res["ya_tenian"]:
                                _partes.append(f"{len(_res['ya_tenian']):,} se respetaron")
                            avisar("success", " · ".join(_partes) + ".")
                            st.session_state["bm_resultado"] = _res
                            st.rerun()
            _res_b = st.session_state.get("bm_resultado")
            if _res_b:
                if _res_b.get("rotos_por_excel"):
                    st.error(
                        f"🛑 {len(_res_b['rotos_por_excel'])} código(s) NO se cargaron porque "
                        "Excel se comió sus dígitos al guardar el archivo. Volvé a exportar esa "
                        "columna como texto.")
                    st.dataframe(_res_b["rotos_por_excel"][:50], width="stretch",
                                  hide_index=True)
                # Lo que NO entró es lo que hay que mirar, así que va desplegado y con el
                # archivo para bajar: son las etiquetas que quedaron sin producto.
                if _res_b["repetidos"]:
                    st.error(
                        f"⚠️ **{len(_res_b['repetidos'])} código(s) de barras repetidos** en el "
                        "archivo: el mismo número en más de un producto. Escanear esa etiqueta "
                        "va a traer varios repuestos y no hay forma de saber cuál es. **No se "
                        "cargaron**: corregilos en el archivo y volvé a subirlo.")
                    st.dataframe(_res_b["repetidos"][:50], width="stretch", hide_index=True)
                if _res_b["ambiguos"]:
                    st.warning(
                        f"{len(_res_b['ambiguos'])} código(s) existen en más de una lista y se "
                        "saltearon. Volvé a subir el archivo eligiendo la lista.")
                if _res_b["sin_producto"]:
                    st.warning(f"{len(_res_b['sin_producto'])} código(s) del archivo no están "
                                "en el catálogo. No se creó ninguno.")
                    st.dataframe(_res_b["sin_producto"][:50], width="stretch", hide_index=True)
                    st.download_button(
                        "⬇️ Bajar los que no encontró",
                        data=to_excel_bytes(_res_b["sin_producto"]),
                        file_name="codigos_sin_producto.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                if st.button("Listo", key="bm_cerrar"):
                    st.session_state.pop("bm_resultado", None)
                    st.rerun()
            st.markdown("---")

            # Los que ya están en su columna pero con un dígito cambiado: el escáner no los
            # va a encontrar nunca, y desde el mostrador se ve como «el escáner no anda».
            _barras_rotos, _barras_propias = codigos_de_barras_que_no_cierran()
            if _barras_propias:
                # Decirlo, no callarlo: que un control decida NO mirar una lista es información.
                st.caption(
                    "🏷️ No se controla el dígito verificador de "
                    + ", ".join(f"**{x['Lista']}** ({x['Códigos']:,})" for x in _barras_propias)
                    + ": ahí la mayoría de los códigos no cumple la cuenta de GS1, así que son "
                      "etiquetas propias del negocio y no del fabricante. Esas se escanean "
                      "perfecto igual —la etiqueta se imprimió desde ese número— y revisarlas "
                      "sería mandar a mirar cajas que están bien."
                )
            if _barras_rotos:
                st.markdown("**🔢 Códigos de barras que no cierran con su dígito verificador**")
                explicar(
                    "Están cargados, pero con un dígito cambiado: escanear la caja no los va a "
                    "encontrar.",
                    "El último dígito de un código de barras es una cuenta sobre los otros doce. "
                    "Si no da, el número está mal copiado en la lista del proveedor.\n\n"
                    "**No se corrigen solos a propósito**: cambiar un dígito para que la cuenta "
                    "cierre da OTRO código de barras, que puede ser el de un producto distinto. "
                    "Hay que mirar la caja y corregirlo a mano en la ficha del producto."
                )
                st.dataframe(quitar_id(_barras_rotos), width="stretch", hide_index=True)
                st.caption(f"{len(_barras_rotos)} producto(s). Son los que el escáner no "
                            "encuentra aunque el repuesto esté cargado.")

        if _grupo_mant == GRUPOS_MANTENIMIENTO[5]:
            st.markdown("**🔗 Listas que no cruzan con ninguna otra**")
            explicar(
                "Por qué una lista no genera equivalencias con las demás, con el motivo escrito.",
                "La búsqueda cruza dos listas cuando las dos citan el **mismo código de "
                "fábrica**. Si una lista no lo trae, o trae otra cosa en esa columna, se carga "
                "perfecto —precios, stock, búsqueda por descripción— pero no se junta con "
                "nadie.\n\n"
                "Lo difícil era darse cuenta: la lista puede tener miles de equivalencias "
                "cargadas y que **ninguna** llegue a otro proveedor, porque van todas a su "
                "propio código y ahí se terminan. En la búsqueda eso se ve como un resultado "
                "de más, no como un problema.\n\n"
                "**La columna que importa es «Cruzan con otra marca».** Si dice 0, esa lista "
                "hoy no sirve para responder «¿qué otra marca me sirve?»."
            )
            if st.button("🔗 Ver por qué no cruzan"):
                _cruces = listas_que_no_cruzan()
                # Las que solo esperan revisión van aparte de las que están de verdad
                # aisladas: el síntoma es el mismo y lo que hay que hacer es lo contrario.
                _esperan = [f for f in _cruces if f["_solo_falta_revisar"]]
                _mudas = [f for f in _cruces if f["_sin_cruce"] and not f["_solo_falta_revisar"]]
                if not _mudas and not _esperan:
                    st.success("✅ Todas las listas cruzan con alguna otra.")
                if _esperan:
                    st.warning(
                        "⏳ **No hace falta reimportar "
                        + ", ".join(f["Lista"] for f in _esperan)
                        + f"**: {sum(f['Esperando revisión'] for f in _esperan):,} "
                          "producto(s) ya tienen las equivalencias encontradas y esperan que "
                          "alguien las apruebe en Estadísticas → 🔗 Equivalencias sugeridas."
                    )
                if _mudas:
                    st.warning(
                        f"⚠️ {len(_mudas)} lista(s) no llegan a ningún producto de otro "
                        f"proveedor: {', '.join(f['Lista'] for f in _mudas)}."
                    )
                st.dataframe(
                    [{k: v for k, v in f.items() if not k.startswith("_")} for f in _cruces],
                    width="stretch", hide_index=True,
                    column_config={"Cruzan con otra marca": st.column_config.NumberColumn(
                        "Cruzan con otra marca",
                        help="Productos de esa lista que llegan a un producto de OTRO proveedor. "
                             "Es la cuenta que dice si la lista sirve para buscar equivalencias."
                    )}
                )
                if _mudas:
                    explicar(
                        "Se arregla volviendo a importar la lista con la columna correcta.",
                        "En **📁 Cargar Excel**, al volver a subir la misma lista, elegí en "
                        "«Código OEM / Equivalente» la columna del código original de la "
                        "terminal. Si la lista no la trae, dejala en «Ninguna» y activá "
                        "«buscar el código de fábrica dentro de la descripción».\n\n"
                        "**Reimportar no duplica nada**: los productos se reconocen por su "
                        "código y se actualizan, no se cargan de nuevo."
                    )

            st.markdown("**🔍 Salud de los datos**")
            st.caption(
                "Revisa la base en busca de cosas rotas o inconsistentes — útil para detectar corrupción "
                "de datos antes de encontrártela buscando un producto."
            )
            if st.button("🔍 Revisar salud de los datos"):
                reporte_salud = chequear_integridad_bd()
                total_problemas = sum(r["Problemas"] for r in reporte_salud)
                if total_problemas == 0:
                    st.success("✅ Todo en orden, no se encontró ningún problema.")
                else:
                    st.warning(f"⚠️ Se encontraron {total_problemas} problema(s) en total.")
                st.dataframe(
                    [r for r in reporte_salud],
                    width="stretch", hide_index=True,
                    column_config={"Problemas": st.column_config.NumberColumn(
                        "Problemas", help="0 está bien; más de 0 conviene revisarlo"
                    )}
                )
            st.markdown("**Limpieza de la base**")
            # El número va ANTES del botón, y a propósito. El texto de antes decía «códigos
            # cargados por error» y ofrecía borrarlos sin decir cuántos eran: sobre el catálogo
            # real son 25.143 de 61.574, el 41%, casi todos repuestos vendibles que
            # simplemente todavía no cruzó nadie. Ese botón no limpiaba, vaciaba el negocio.
            _sueltos = contar_huerfanos()
            c.execute("SELECT COUNT(*) FROM productos")
            _todos = c.fetchone()[0] or 1
            _porcentaje = _sueltos * 100 // _todos
            st.caption(
                "Un producto «sin equivalencia» es uno que todavía NO cruzaste con ningún otro "
                "código. No quiere decir que esté mal cargado: puede tener precio, stock y "
                "venderse igual. Borralos solo si sabés que entraron por una importación fallida."
            )
            if not _sueltos:
                st.caption("✅ No hay productos sin equivalencias.")
            else:
                (st.warning if _porcentaje >= 20 else st.info)(
                    f"Hay **{_sueltos:,}** producto(s) sin ninguna equivalencia, de {_todos:,} "
                    f"— el {_porcentaje}% del catálogo."
                )
                # Y los que tienen una equivalencia que no lleva a ningún lado. El buscador ya
                # se los marca así; sin decirlo acá también, las dos pantallas contaban
                # distinto el mismo producto.
                _muertos = contar_con_equivalencia_muerta()
                if _muertos:
                    st.info(
                        f"➕ Otros **{_muertos:,}** tienen una equivalencia cargada que **no "
                        "lleva a ningún lado**: el único código vinculado es su propio código "
                        "de fábrica, que todavía no tiene nadie más. El buscador ya se los "
                        "marca así.\n\n"
                        "**A esos no los borres.** Se resuelven solos cuando entre otra lista "
                        "que traiga el mismo código de fábrica, o con **🧠 Buscar equivalencias "
                        "en todo el catálogo** (Mantenimiento → Calidad), que los cruza por "
                        "descripción."
                    )
                # Una casilla además de la contraseña, como en «Eliminar marca» y «Eliminar
                # producto». Acá hace más falta que en ninguna: son 34.457 productos —el 48%
                # del catálogo, casi todos vendibles y con precio— detrás de un solo botón, y
                # no hay papelera para esto. La contraseña sola protege de que lo toque quien
                # no debe; la casilla protege del dedo equivocado del que sí puede.
                _confirmar_sueltos = st.checkbox(
                    f"Confirmo que quiero borrar {_sueltos:,} productos y que esto NO se puede "
                    "deshacer", key="confirmar_borrar_sueltos")
                if candado('borrar productos sin equivalencias',
                            st.button(f"🧹 Borrar esos {_sueltos:,} productos",
                                       disabled=not _confirmar_sueltos),
                            'borrar_productos_sin_equivalencias'):
                    borrados = depurar_huerfanos()
                    avisar("success", f"Se borraron {borrados:,} producto(s) sin equivalencias.")
                    st.rerun()
            st.markdown("**🗑️ Papelera**")
            explicar(
                "Cuando borrás una marca entera, un combo, un alias de transferencia o un producto "
                "puntual (por ID), queda acá guardado por si te equivocaste.",
                "Se borra en forma permanente solo cuando vos lo pedís o pasan más de 30 días. "
                "(Fusionar marcas y restaurar un backup completo siguen siendo irreversibles — esos no "
                "pasan por acá.)"
            )
            # El resultado de restaurar va ANTES de mirar si quedó algo. Estaba adentro del
            # «else» de abajo, y restaurar lo ÚLTIMO que había deja la papelera vacía: el cartel
            # no salía, quedaba guardado en la sesión, y aparecía la próxima vez que alguien
            # borrara algo — un «Restaurado con 61 vínculos» que ya no tenía nada que ver.
            resultado_papelera = st.session_state.pop("resultado_papelera", None)
            if resultado_papelera:
                tipo_res, msg_res = resultado_papelera
                (st.success if tipo_res == "ok" else st.error)(msg_res)
            items_papelera = listar_papelera()
            if not items_papelera:
                st.caption("La papelera está vacía.")
            else:
                iconos_tipo = {"combo": "🧩", "alias": "💳", "producto": "📦", "marca": "🏷️"}
                for item in items_papelera:
                    colp1, colp2, colp3 = st.columns([3, 1, 1])
                    icono = iconos_tipo.get(item["Tipo"], "🗑️")
                    colp1.write(
                        f"{icono} {item['Tipo'].capitalize()}: **{item['Detalle']}** — "
                        f"eliminado por {item['Eliminado por'] or 'alguien'} el {item['Fecha']}"
                    )
                    colp2.button("↩️ Restaurar", key=f"restaurar_papelera_{item['ID']}",
                                  on_click=cb_restaurar_papelera, args=(item["ID"],))
                    colp3.button("🗑️", key=f"borrar_papelera_{item['ID']}", help="Borrar en forma permanente, sin restaurar",
                                  on_click=borrar_papelera_definitivo, args=(item["ID"],))

                st.caption("También se limpia sola: lo que lleva más de 30 días acá se borra en forma permanente.")
                st.button("🧹 Vaciar ahora lo de más de 30 días", on_click=vaciar_papelera_antigua, args=(30,))

        if sub_admin == SUB_ADMIN[5]:
            if not pedir_password_admin("gestionar usuarios"):
                pass
            else:
                st.markdown("**👤 Empleados (admin / operador)**")
                explicar(
                    "Cuentas creadas desde acá, sin necesidad de tocar la configuración de Streamlit Cloud.",
                    "'Admin' puede todo, incluso borrar y configurar. 'Operador' puede usar las funciones "
                    "de IA y cargar cosas, pero no borrar ni configurar nada sensible."
                )
                usuarios_actuales = listar_usuarios()
                if usuarios_actuales:
                    st.dataframe(usuarios_actuales, width="stretch", hide_index=True)

                cu1, cu2 = st.columns(2)
                nombre_nuevo_usuario = cu1.text_input("Nombre:", key="nuevo_usuario_nombre")
                password_nuevo_usuario = cu2.text_input("Contraseña:", type="password", key="nuevo_usuario_pass")
                rol_nuevo_usuario = st.selectbox("Rol:", ["operador", "admin"], key="nuevo_usuario_rol")
                if st.button("➕ Crear empleado"):
                    if not nombre_nuevo_usuario.strip() or not password_nuevo_usuario:
                        st.warning("Completá nombre y contraseña.")
                    else:
                        try:
                            crear_usuario(nombre_nuevo_usuario, password_nuevo_usuario, rol_nuevo_usuario)
                            avisar("success", f"Empleado '{nombre_nuevo_usuario}' creado.")
                            st.rerun()
                        except sqlite3.IntegrityError as _err:
                            anotar_error("nivel principal", _err)
                            st.error("Ya existe un empleado con ese nombre.")

                if usuarios_actuales:
                    st.markdown("**Gestionar un empleado existente**")
                    opciones_usuario = {u["Nombre"]: u["ID"] for u in usuarios_actuales}
                    usuario_elegido = st.selectbox("Elegí un empleado:", list(opciones_usuario.keys()), key="sel_usuario_gestionar")
                    usuario_id_sel = opciones_usuario[usuario_elegido]
                    cug1, cug2, cug3 = cols(3)
                    nueva_pass_usuario = cug1.text_input("Nueva contraseña (opcional):", type="password", key="usuario_nueva_pass")
                    if cug1.button("💾 Cambiar contraseña"):
                        if nueva_pass_usuario:
                            cambiar_password_usuario(usuario_id_sel, nueva_pass_usuario)
                            st.success("Contraseña actualizada.")
                        else:
                            st.warning("Escribí la nueva contraseña primero.")
                    usuario_activo_actual = next(u["Activo"] == "Sí" for u in usuarios_actuales if u["ID"] == usuario_id_sel)
                    if cug2.button("🚫 Desactivar" if usuario_activo_actual else "✅ Reactivar"):
                        activar_desactivar_usuario(usuario_id_sel, not usuario_activo_actual)
                        st.rerun()
                    if cug3.button("🗑️ Eliminar empleado"):
                        eliminar_usuario(usuario_id_sel)
                        avisar("success", "Empleado eliminado.")
                        st.rerun()

                st.markdown("---")
                st.markdown("**🔧 Mecánicos externos**")
                st.caption(
                    "Cuentas separadas para mecánicos que no son empleados tuyos — solo ven su propio "
                    "portal para armar presupuestos con su mano de obra, nunca las secciones internas."
                )
                mecanicos_actuales = listar_mecanicos()
                if mecanicos_actuales:
                    st.dataframe(mecanicos_actuales, width="stretch", hide_index=True)

                cm1, cm2 = st.columns(2)
                nombre_nuevo_mecanico = cm1.text_input("Nombre:", key="nuevo_mecanico_nombre")
                password_nuevo_mecanico = cm2.text_input("Contraseña:", type="password", key="nuevo_mecanico_pass")
                if st.button("➕ Crear mecánico"):
                    if not nombre_nuevo_mecanico.strip() or not password_nuevo_mecanico:
                        st.warning("Completá nombre y contraseña.")
                    else:
                        try:
                            crear_mecanico(nombre_nuevo_mecanico, password_nuevo_mecanico)
                            avisar("success", f"Mecánico '{nombre_nuevo_mecanico}' creado.")
                            st.rerun()
                        except sqlite3.IntegrityError as _err:
                            anotar_error("nivel principal", _err)
                            st.error("Ya existe un mecánico con ese nombre.")

                if mecanicos_actuales:
                    st.markdown("**Gestionar un mecánico existente**")
                    opciones_mecanico = {m["Nombre"]: m["ID"] for m in mecanicos_actuales}
                    mecanico_elegido = st.selectbox("Elegí un mecánico:", list(opciones_mecanico.keys()), key="sel_mecanico_gestionar")
                    mecanico_id_sel = opciones_mecanico[mecanico_elegido]
                    cmg1, cmg2 = st.columns(2)
                    mecanico_activo_actual = next(m["Activo"] == "Sí" for m in mecanicos_actuales if m["ID"] == mecanico_id_sel)
                    if cmg1.button("🚫 Desactivar" if mecanico_activo_actual else "✅ Reactivar", key="toggle_mecanico"):
                        activar_desactivar_mecanico(mecanico_id_sel, not mecanico_activo_actual)
                        st.rerun()
                    if cmg2.button("🗑️ Eliminar mecánico"):
                        eliminar_mecanico(mecanico_id_sel)
                        avisar("success", "Mecánico eliminado.")
                        st.rerun()

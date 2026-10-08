"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/."""

# ============================================================
# CARGAR EXCEL
# ============================================================
if pagina == PAGINAS[2]:
    # Como las demás secciones (ver seccion_permitida()): con contraseñas, pide la de
    # administrador; sin ninguna configurada, avisa y deja pasar. Antes pedía una contraseña que
    # no existía y no había forma de importar hasta configurar los secretos.
    if not seccion_permitida("admin", "cargar listas de proveedores"):
        pass
    else:
        st.subheader("Cargar nueva planilla (.xlsx / .csv / .pdf)")

        # El proveedor casi siempre está en el nombre del archivo ("ILLINOIS 17 07 2026.xlsx").
        # Se propone solo, pero queda editable: nunca se pisa lo que la persona haya escrito.
        # Lo que SÍ se vuelve a proponer es lo que propuso la app, cuando llega otro archivo
        # (ver más abajo, donde se nota el cambio). Antes la primera sugerencia quedaba pegada:
        # «Usar otro archivo», subir la de MAHLE, y la importación salía como ILLINOIS, con el
        # mapeo de columnas de ILLINOIS encima.
        if st.session_state.pop("_resugerir_proveedor", False):
            st.session_state.pop("nombre_prov_carga", None)
        _nombre_del_archivo = (st.session_state.get("_nombre_archivo_de_la_carga")
                               or (st.session_state.get("_archivo_lista") or {}).get("nombre"))
        if _nombre_del_archivo and not st.session_state.get("nombre_prov_carga"):
            c.execute("SELECT nombre FROM marcas")
            _marcas_conocidas = [r["nombre"] for r in c.fetchall()]
            _sugerido_prov = adivinar_proveedor(_nombre_del_archivo, _marcas_conocidas)
            if _sugerido_prov:
                st.session_state["nombre_prov_carga"] = _sugerido_prov
                st.session_state["_proveedor_sugerido"] = _sugerido_prov

        nombre_prov = st.text_input(
            "Nombre de la Marca / Proveedor:", placeholder="Ej: Mahle, Bosch, Mann...",
            key="nombre_prov_carga",
            help="Se propone solo a partir del nombre del archivo. Corregilo si no acertó."
        )

        metodo = st.radio(
            "¿Cómo querés indicar el archivo?",
            ["Subir archivo", "Escribir la ruta en el teléfono"],
            horizontal=True,
            help="Si el botón de subir no responde en el navegador del celular, usá la opción de ruta."
        )

        archivo = None

        if metodo == "Subir archivo":
            # La primera subida que llegue bien queda guardada, así no se pierde si el widget
            # se vacía por un refresco o un corte de conexión (el clásico "lo subo y no lo toma").
            # .txt y .tsv también: muchos proveedores exportan así, y hasta ahora el selector
            # ni siquiera los dejaba elegir aunque la app sabe leerlos.
            archivo = subir_archivo("Seleccioná el archivo",
                                     ["xlsx", "xlsm", "csv", "txt", "tsv", "pdf"], "lista")
            if archivo:
                ca1, ca2 = st.columns([3, 1])
                with ca1:
                    archivo_listo(archivo, "archivo")
                with ca2:
                    boton_otro_archivo("lista")

                # ¿Es un archivo que generó la propia app? Importarlo mete de vuelta lo que
                # se había separado a propósito.
                _generado, _que_es = es_archivo_generado_por_la_app(getattr(archivo, "name", ""))
                if _generado:
                    st.error(
                        f"🔄 **Este archivo lo generó la propia app**: es {_que_es}. "
                        "No es una lista de proveedor.\n\n"
                        "Importarlo vuelve a meter en la base justo lo que se había separado, y "
                        "además crea una marca con el nombre del archivo. Si en tus marcas ves "
                        "algo como «FILAS OMITIDAS», salió de acá."
                    )

                # ¿Esta misma planilla ya se importó? Se compara el CONTENIDO, no el nombre:
                # el archivo suele llegar renombrado y así se reconoce igual.
                previa = importacion_previa(huella_de_archivo(archivo.getvalue()))
                if previa:
                    st.warning(
                        f"🔁 Esta misma planilla ya se importó el "
                        f"**{str(previa['fecha'])[:16]}** como **{previa['marca']}** "
                        f"({previa['filas_cargadas']} filas). Si la volvés a importar vas a "
                        "revisar de nuevo los mismos vínculos, y los precios que hayas corregido "
                        "a mano desde entonces se pisan con los de esta lista."
                    )
            else:
                archivo_listo(None, "archivo")
            if archivo and archivo.name.lower().endswith(".pdf"):
                ayuda(
                    "📄 PDF: funciona mejor con catálogos que tienen tablas reales (no una imagen escaneada). "
                    "Revisá bien la vista previa antes de importar, el resultado puede variar según el PDF."
                )
        else:
            st.caption(
                "Ejemplo: /storage/emulated/0/Download/lista.xlsx "
                "(si el archivo está en Descargas, esa es la ruta de siempre)."
            )
            ruta_archivo = st.text_input("Ruta completa del archivo en el teléfono:",
                                          placeholder="/storage/emulated/0/Download/lista.xlsx")
            EXTENSIONES_OK = (".xlsx", ".xlsm", ".csv", ".txt", ".tsv", ".pdf")
            if ruta_archivo:
                import os
                if not os.path.isfile(ruta_archivo):
                    st.error("No se encontró un archivo en esa ruta. Revisá que esté bien escrita.")
                elif not ruta_archivo.lower().endswith(EXTENSIONES_OK):
                    st.error("El archivo debe terminar en " + ", ".join(EXTENSIONES_OK))
                else:
                    archivo = ruta_archivo

        # ¿Llegó OTRO archivo? Lo que se eligió para el anterior no vale para este: la fila de
        # títulos y la hoja se vuelven a detectar, y el proveedor se vuelve a proponer si lo
        # había puesto la app. Antes quedaban pegados: la lista de ZETA con dos renglones de
        # tapa dejaba «fila 3», la siguiente (sin tapa) se leía desde la fila 3, y sus dos
        # primeros productos se perdían como si fueran los títulos.
        _identidad = identidad_del_archivo(archivo)
        if _identidad is not None and _identidad != st.session_state.get("_archivo_de_la_carga"):
            _habia_otro = st.session_state.get("_archivo_de_la_carga") is not None
            st.session_state["_archivo_de_la_carga"] = _identidad
            st.session_state["_nombre_archivo_de_la_carga"] = os.path.basename(
                archivo if isinstance(archivo, str) else getattr(archivo, "name", ""))
            for _k in ("fila_encabezado", "hoja_excel", "importar_con_dudas"):
                st.session_state.pop(_k, None)
            _prov_ahora = st.session_state.get("nombre_prov_carga") or ""
            if not _prov_ahora.strip() or (
                    _habia_otro and _prov_ahora == st.session_state.get("_proveedor_sugerido")):
                st.session_state["_resugerir_proveedor"] = True
                st.rerun()

        # --- Mapeo dinámico de columnas ---
        # OJO: estos valores por defecto NO son decorativos. Los selectores se crean adentro de
        # un "else" (solo si el archivo tiene columnas), pero el bloque de importar está afuera:
        # sin estas líneas, un archivo sin columnas hace que el importador rompa con NameError.
        todas_filas = None
        idx_prov = idx_oem = 0
        idx_desc = None
        idx_precio = idx_stock = None
        tope_salto = 200
        _problemas_del_mapeo = []

        hoja_elegida = None
        if archivo:
            # Selector de hoja. Antes se leía siempre la que quedó activa al guardar el archivo,
            # que muchas veces es la de instrucciones o una en blanco: la lista no se importaba
            # y no había ninguna señal de por qué.
            hojas = hojas_del_excel(archivo)
            if len(hojas) > 1:
                etiquetas_hojas = {f"{n} ({f} filas)": n for n, f in hojas}
                sugerida = max(hojas, key=lambda h: h[1])[0]
                indice_sug = [n for n, _ in hojas].index(sugerida)
                elegida_lbl = st.selectbox(
                    f"El archivo tiene {len(hojas)} hojas — ¿cuál es la lista?",
                    list(etiquetas_hojas.keys()), index=indice_sug, key="hoja_excel",
                    help="Se propone la que más filas tiene."
                )
                hoja_elegida = etiquetas_hojas[elegida_lbl]
            try:
                todas_filas = leer_excel(archivo, nrows=200, hoja=hoja_elegida)
                if isinstance(archivo, object) and not isinstance(archivo, str):
                    archivo.seek(0)
            except Exception as e:
                anotar_error("nivel principal", e)
                st.error(f"No se pudo leer el archivo: {e}")
                todas_filas = None

        if todas_filas:
            # Detectar automáticamente la fila de encabezado como punto de partida
            # Fila de títulos: la detecta mirando la forma de la tabla, no solo esta fila.
            # Queda EDITABLE porque ninguna detección acierta siempre, y equivocarse acá arruina
            # toda la importación: desalinea el mapeo y mete las filas de arriba como productos.
            header_auto = detectar_fila_encabezado(todas_filas)
            header_row = st.number_input(
                "Fila donde están los títulos de las columnas:",
                min_value=1, max_value=max(len(todas_filas), 1), value=header_auto + 1,
                step=1, key="fila_encabezado",
                help="Se detecta sola. Corregila si la vista previa no muestra los títulos "
                     "correctos en la primera fila."
            ) - 1
            encabezado = todas_filas[header_row]
            preview_filas = todas_filas[header_row:header_row + 6]

            st.write("Vista previa (primeras filas detectadas):")
            # Todo como texto: una columna que mezcla números y textos —la de MOTORARG trae
            # 140000 y 150000-R en la misma— no se puede convertir a tabla tal cual, y
            # Streamlit dejaba un error largo en el registro en cada importación antes de
            # arreglarlo solo. Para mirar alcanza, y así se ve exactamente lo que dice la celda.
            st.dataframe([["" if v is None else str(v) for v in fila] for fila in preview_filas],
                         width="stretch")

            if len(encabezado) < 1:
                st.error("El archivo no tiene ninguna columna con datos.")
            else:
                st.markdown("**Mapeo de columnas** — revisá que coincida con tu archivo (se sugiere automáticamente):")
                sugerido = adivinar_columnas(encabezado)
                # Si el encabezado no tiene títulos de verdad (la lista arranca directo en los
                # datos), se deduce mirando los valores. Sin esto la detección caía en la
                # columna 0, que en muchas listas está vacía, y no entraba ni un producto.
                titulos_utiles = sum(1 for x in encabezado
                                     if x is not None and str(x).strip() and not str(x).strip()[0].isdigit())
                if titulos_utiles < 2:
                    por_datos = adivinar_columnas_por_datos(
                        todas_filas[header_row + 1:header_row + 60], len(encabezado)
                    )
                    if por_datos["prov"] is not None:
                        sugerido = por_datos
                        st.info(
                            "ℹ️ Esta lista no trae títulos de columna, así que deduje qué es cada "
                            "una mirando los datos. **Revisá la tabla de más abajo** antes de importar."
                        )
                idx_prov_auto = sugerido["prov"]
                # Si ninguna columna parece de OEM, se deja en "Ninguna" y decide la persona.
                # Antes se asumía la columna 1 —la segunda, fuera lo que fuera—: en una lista sin
                # OEM esa es la DESCRIPCIÓN, así que se cargaban productos con códigos como
                # "FILTROACEITEVW" bajo la marca OEM y se les colgaban equivalencias. Además de
                # ensuciar la base, tapaba justo lo que hace falta para cruzar proveedores: en
                # vez de un código de fábrica real —el único puente entre dos listas— quedaba un
                # texto que no coincide con nada.
                idx_oem_auto = sugerido["oem"]
                idx_desc_auto = sugerido["desc"]
                idx_ean_auto = sugerido.get("ean")
                idx_precio_sug, idx_stock_sug = sugerido["precio"], sugerido["stock"]

                opciones_cols = [f"Columna {i}: {str(v)[:20] if v else '(sin título)'}"
                                  for i, v in enumerate(encabezado)]

                # Si ya se importó una lista de este proveedor, se arranca con el mismo mapeo
                # que funcionó la vez anterior en vez de tener que acertarle de nuevo.
                # Pero por TÍTULO, no por posición: si el proveedor agregó o movió una columna,
                # «la columna 2» ya es otra. Antes se aplicaba igual, y con la lista nueva el
                # código de proveedor quedaba apuntando al PRECIO: se importaban «1.500,00»
                # como números de parte. Ahora cada columna recordada se busca por su título;
                # la que no aparece se deja a la detección automática.
                mapeo_previo = reubicar_mapeo_por_titulos(leer_mapeo_columnas(nombre_prov),
                                                          encabezado)
                def _valido(indice):
                    return indice if (indice is not None and 0 <= indice < len(opciones_cols)) else None
                # Y si aun así no cuadra con los datos (el código cae en una columna de
                # importes, o de palabras repetidas), se deja de lado: pasa con los mapeos
                # guardados antes de recordar los títulos, que solo tienen la posición.
                if mapeo_previo and problemas_del_mapeo(
                        todas_filas, header_row, mapeo_previo["idx_prov"], mapeo_previo["idx_oem"],
                        mapeo_previo["idx_precio"], mapeo_previo["idx_stock"]):
                    st.info(
                        f"💾 Había un mapeo guardado para **{nombre_prov.strip().upper()}**, pero "
                        "no cuadra con este archivo (las columnas cambiaron). Usé la detección "
                        "automática: revisá el mapeo antes de importar."
                    )
                    mapeo_previo = None
                if mapeo_previo:
                    if mapeo_previo["_como"] == "igual":
                        st.success(
                            f"💾 Se recordó cómo mapeaste las columnas la última vez que importaste "
                            f"una lista de **{nombre_prov.strip().upper()}** ({mapeo_previo['fecha'][:10]}). "
                            "Ya viene preseleccionado — revisá que coincida con este archivo."
                        )
                    else:
                        st.info(
                            f"💾 Las columnas de **{nombre_prov.strip().upper()}** cambiaron de "
                            "lugar desde la última importación: ubiqué las que recordaba por su "
                            "título" + (f" (no encontré: {', '.join(mapeo_previo['_faltan'])})"
                                        if mapeo_previo["_faltan"] else "")
                            + ". Revisá el mapeo antes de importar."
                        )
                    if _valido(mapeo_previo["idx_prov"]) is not None:
                        idx_prov_auto = mapeo_previo["idx_prov"]
                    if "idx_oem" not in mapeo_previo["_faltan_claves"]:
                        idx_oem_auto = _valido(mapeo_previo["idx_oem"])
                    if "idx_desc" not in mapeo_previo["_faltan_claves"]:
                        idx_desc_auto = _valido(mapeo_previo["idx_desc"])
                    if (mapeo_previo.get("idx_ean") is not None
                            and "idx_ean" not in mapeo_previo["_faltan_claves"]):
                        idx_ean_auto = _valido(mapeo_previo["idx_ean"])

                c_p, c_o, c_d = cols(3)
                with c_p:
                    idx_prov = st.selectbox("Código Proveedor:", range(len(opciones_cols)),
                                             format_func=lambda x: opciones_cols[x], index=idx_prov_auto)
                with c_o:
                    opciones_oem = [None] + list(range(len(opciones_cols)))
                    idx_oem = st.selectbox(
                        "Código OEM / Equivalente:", opciones_oem,
                        format_func=lambda x: "Ninguna (la lista no lo trae)" if x is None else opciones_cols[x],
                        index=opciones_oem.index(idx_oem_auto),
                        help="Si la lista no tiene columna de OEM, elegí 'Ninguna': los productos se "
                             "cargan igual y quedan buscables, solo que sin equivalencia."
                    )
                with c_d:
                    opciones_desc = [None] + list(range(len(opciones_cols)))
                    idx_default_desc = opciones_desc.index(idx_desc_auto) if idx_desc_auto is not None else 0
                    idx_desc = st.selectbox("Descripción (opcional):", opciones_desc,
                                             format_func=lambda x: "Ninguna" if x is None else opciones_cols[x],
                                             index=idx_default_desc)

                c_pr, c_st = cols(2)
                opciones_num = [None] + list(range(len(opciones_cols)))
                # El mapeo que ya funcionó con este proveedor manda; si no hay, lo detectado
                # por el título de la columna.
                idx_precio_auto = (_valido(mapeo_previo["idx_precio"]) if mapeo_previo else None)
                if idx_precio_auto is None:
                    idx_precio_auto = idx_precio_sug
                idx_stock_auto = (_valido(mapeo_previo["idx_stock"]) if mapeo_previo else None)
                if idx_stock_auto is None:
                    idx_stock_auto = idx_stock_sug
                if idx_stock_auto is not None and idx_stock_auto == idx_precio_auto:
                    idx_stock_auto = None
                with c_pr:
                    idx_precio = st.selectbox(
                        "Precio (opcional):", opciones_num,
                        format_func=lambda x: "Ninguna" if x is None else opciones_cols[x],
                        index=opciones_num.index(idx_precio_auto) if idx_precio_auto is not None else 0,
                        help="Si la elegís, la lista actualiza los precios al importar."
                    )
                with c_st:
                    idx_stock = st.selectbox(
                        "Stock (opcional):", opciones_num,
                        format_func=lambda x: "Ninguna" if x is None else opciones_cols[x],
                        index=opciones_num.index(idx_stock_auto) if idx_stock_auto is not None else 0
                    )

                # El código de barras tiene su propio lugar. Antes no lo tenía y terminaba en la
                # columna de OEM, que es por donde se cruzan los proveedores: ahí adentro no
                # cruza con nadie —es de este proveedor y de nadie más— y deja una equivalencia
                # falsa por cada fila. Guardado acá se puede escanear la caja y encontrar el
                # repuesto, sin ensuciar la red de equivalencias.
                idx_ean = st.selectbox(
                    "Código de barras / EAN (opcional):", opciones_num,
                    format_func=lambda x: "Ninguna" if x is None else opciones_cols[x],
                    index=opciones_num.index(idx_ean_auto) if idx_ean_auto is not None else 0,
                    help="Se guarda pegado al producto para poder escanearlo. NO genera "
                         "equivalencias: el código de barras es de este proveedor solamente."
                )

                if idx_precio is not None:
                    st.session_state.setdefault("tope_salto_precio", 200)
                    tope_salto = st.select_slider(
                        "Frenar precios que cambien más de:",
                        options=[50, 100, 200, 400, 800, 0],
                        format_func=lambda x: "No frenar ninguno" if x == 0 else f"{x}%",
                        key="tope_salto_precio",
                        help="Un precio que se multiplica o se divide de golpe casi nunca es un "
                             "aumento: es la columna equivocada, el separador de decimales al "
                             "revés, o un precio por bulto donde iba el unitario. Los que superen "
                             "este límite se cargan igual como producto, pero el precio queda "
                             "frenado para que lo mires vos."
                    )
                else:
                    tope_salto = 200

                # Lo que seguro está mal en el mapeo, con palabras. Ver problemas_del_mapeo().
                _problemas_del_mapeo = problemas_del_mapeo(todas_filas, header_row, idx_prov,
                                                           idx_oem, idx_precio, idx_stock)
                for _grave, _texto in _problemas_del_mapeo:
                    (st.error if _grave else st.warning)(("🛑 " if _grave else "⚠️ ") + _texto)

                # --- Diagnóstico ANTES de importar ---
                # Es la respuesta a "se carga mal y no sé por qué": muestra qué entendió la app
                # de cada columna con valores reales del archivo, y cuántas filas se van a
                # perder y por qué motivo. Todo esto antes se descubría después de importar.
                st.markdown("**🔎 Qué está entendiendo la app de tu lista**")
                diag = diagnosticar_lista(todas_filas, header_row, idx_prov, idx_oem, idx_desc,
                                           idx_ean=idx_ean)

                if diag["total"] == 0:
                    st.error(
                        "No hay ninguna fila de datos debajo de los títulos. Revisá la fila de "
                        "encabezado de más arriba: si apunta a la última fila con texto, no queda "
                        "nada para importar."
                    )
                else:
                    resumen = []
                    for etiqueta, idx, tipo in (("Código de proveedor", idx_prov, "codigo"),
                                                 ("Código de fábrica", idx_oem, "codigo"),
                                                 ("Descripción", idx_desc, "descripcion")):
                        if idx is None:
                            resumen.append({"Campo": etiqueta, "Columna": "— sin asignar",
                                            "Diagnóstico": "", "Ejemplos del archivo": ""})
                            continue
                        clave = {"Código de proveedor": "ejemplos_prov",
                                 "Código de fábrica": "ejemplos_oem",
                                 "Descripción": "ejemplos_desc"}[etiqueta]
                        estado, motivo = _pinta_columna(diag[clave], tipo)
                        resumen.append({
                            "Campo": etiqueta,
                            "Columna": opciones_cols[idx] if idx < len(opciones_cols) else str(idx),
                            "Diagnóstico": estado + (f" — {motivo}" if motivo else ""),
                            "Ejemplos del archivo": " · ".join(diag[clave][:3]) or "(vacío)",
                        })
                    st.dataframe(resumen, width="stretch", hide_index=True)

                    d1, d2, d3 = cols(3)
                    d1.metric("Filas que entran", miles(diag["ok"]))
                    d2.metric("Sin código", miles(diag["sin_codigo"] + diag["codigo_basura"]))
                    d3.metric("Con código de fábrica", miles(diag["con_oem"]))

                    porcentaje_ok = diag["ok"] / max(diag["total"], 1)
                    if porcentaje_ok < 0.5:
                        st.error(
                            f"🔴 Solo entrarían {diag['ok']} de {diag['total']} filas de la muestra. "
                            "Eso casi siempre significa que el mapeo apunta a la columna equivocada "
                            "o que la fila de encabezado está mal. **Mirá los ejemplos de arriba**: "
                            "si en «Código de proveedor» ves descripciones o cantidades en vez de "
                            "códigos, ahí está el problema. No importes así."
                        )
                    elif diag["codigo_basura"]:
                        st.warning(
                            f"⚠️ {diag['codigo_basura']} fila(s) tienen en la columna de código algo "
                            "que no es un código (números sueltos de 1 o 2 dígitos). Se van a saltear."
                        )
                    else:
                        st.success(f"✅ Entrarían {diag['ok']} de {diag['total']} filas de la muestra.")

                    # Antes que cualquier otra cosa: avisar si este archivo no es una lista de
                    # precios sino un catálogo de aplicaciones. Importarlo acá carga los modelos
                    # de auto como códigos de repuesto, y eso ensucia la base entera.
                    es_aplic, motivo_aplic = parece_catalogo_de_aplicaciones(todas_filas)
                    if es_aplic:
                        st.error(
                            "🏭 **Esto no parece una lista de precios, sino un catálogo de "
                            f"aplicaciones** ({motivo_aplic}).\n\n"
                            "Si lo importás acá, se van a cargar los **modelos de auto como si "
                            "fueran códigos de repuesto** (A4, Q3, Golf...) y los años como "
                            "precios.\n\n"
                            "Este archivo va en "
                            f"**{miga_hasta('Catálogo de aplicaciones')}**: ahí se lee bien y "
                            "sirve para que la búsqueda por vehículo sepa qué repuesto le va a "
                            "cada auto."
                        )
                        st.button("🏭 Ir al catálogo de aplicaciones →", key="ir_catalogo_aplic",
                                  on_click=ir_a_donde_dice_el_aviso,
                                  args=(miga_hasta("Catálogo de aplicaciones"),))

                    # Una lista sin columna de código de fábrica no puede cruzar con otras por
                    # sí sola. Pero muchas listas de acá SÍ traen el código de fábrica, metido
                    # adentro del texto de la descripción — es la única forma de vincularlas.
                    # Este aviso antes decía que no convenía ni intentarlo. Estaba escrito
                    # cuando el extractor tomaba rangos de años y motorizaciones, y desalentaba
                    # justo lo único que funciona en estas listas. Ahora, en vez de advertir en
                    # abstracto, se mide sobre ESTE archivo y se dice qué va a pasar: es un dato
                    # que la persona puede verificar mirando la muestra, no una opinión.
                    if idx_oem is None:
                        _muestra = todas_filas[header_row + 1:header_row + 400]
                        _con_codigo, _ejemplos = 0, []
                        if idx_desc is not None:
                            _pares = [(valor_o_vacio(f[idx_desc]) if idx_desc < len(f) else "",
                                       valor_o_vacio(f[idx_prov]) if idx_prov < len(f) else "")
                                      for f in _muestra]
                            _conocidos = codigos_del_catalogo(version_del_catalogo())
                            _estricta = not la_lista_declara_codigos(_pares)
                            _confiables, _ = codigos_confiables_de_descripciones(
                                _pares, codigos_conocidos=_conocidos,
                                declarados_o_conocidos=_estricta)
                            for _txt, _cod in _pares:
                                _hall = [c for c in extraer_codigos_de_texto(
                                            _txt, codigo_propio=_cod, codigos_conocidos=_conocidos,
                                            declarados_o_conocidos=_estricta)
                                         if sanitizar(c) in _confiables]
                                if _hall:
                                    _con_codigo += 1
                                    if len(_ejemplos) < 4:
                                        _ejemplos.append(f"«{_txt[:44]}» → **{', '.join(_hall[:2])}**")
                        if _con_codigo:
                            st.info(
                                "🔗 **Esta lista no trae columna de código de fábrica**, pero en "
                                f"**{_con_codigo} de las primeras {len(_muestra)} filas** el código "
                                "aparece adentro de la descripción. Activá abajo «buscar el código "
                                "de fábrica dentro de la descripción» y con eso puede cruzar con "
                                "las listas de otros proveedores.\n\n"
                                + "\n\n".join(_ejemplos)
                            )
                        else:
                            st.warning(
                                "🔗 **Esta lista no trae columna de código de fábrica** y tampoco "
                                "encontré códigos dentro de las descripciones, así que no puede "
                                "generar equivalencias: cada fila es un producto suelto con su "
                                "precio. Eso está perfecto para **cargar y actualizar precios**, "
                                "y para que aparezca en la búsqueda por código y por descripción."
                            )
                    else:
                        # LA COLUMNA ESTÁ, PERO ¿ES LA QUE PARECE?
                        # Elegir la columna equivocada como código de fábrica no da error: la
                        # importación sale bien, carga miles de equivalencias, y ninguna sirve.
                        # Es peor que no tener la columna, porque la app queda diciendo que
                        # encontró equivalentes. Con la lista de MOTORARG pasó exactamente eso:
                        # entró la columna de código de barras y quedaron 8.652 productos con
                        # una equivalencia que no lleva a ningún lado. Se avisa ACÁ, antes de
                        # importar, que es el único momento en que se arregla barato.
                        _muestra_oem = [f[idx_oem] for f in todas_filas[header_row + 1:header_row + 400]
                                        if idx_oem < len(f)]
                        _es_barras, _prefijo, (_cuantos, _total_oem) = columna_es_codigo_de_barras(_muestra_oem)
                        if _es_barras:
                            st.error(
                                f"🏷️ **La columna «{opciones_cols[idx_oem]}» parece el código de "
                                f"barras, no el código de fábrica.** "
                                + (f"{_cuantos} de {_total_oem} valores de la muestra son "
                                   f"números de 12 a 14 dígitos que empiezan todos igual "
                                   f"(**{_prefijo}…**), que es el prefijo de empresa del código "
                                   f"de barras"
                                   + (f", registrado en {pais_de_estos_codigos(_muestra_oem)}"
                                      if pais_de_estos_codigos(_muestra_oem) else "")
                                   if _prefijo else
                                   f"{_cuantos} de {_total_oem} valores de la muestra **cierran "
                                   f"con el dígito verificador de un código de barras**. No "
                                   f"arrancan todos igual porque son productos de fábricas "
                                   f"distintas, pero la cuenta de GS1 les da bien: un código de "
                                   f"fábrica de verdad no cierra esa cuenta más que por azar")
                                + ".\n\n"
                                "**Por qué importa:** el código de barras es de este proveedor "
                                "solo. Ninguna otra lista lo va a traer, así que **no va a "
                                "cruzar con nadie**: se van a cargar miles de equivalencias que "
                                "en la búsqueda no llevan a ningún lado.\n\n"
                                "**Qué hacer:** fijate si la lista trae otra columna con el "
                                "código original / OEM / de la terminal (los de fábrica suelen "
                                "tener letras, o son más cortos, y no arrancan todos igual) y "
                                "elegí esa. Si no la trae, dejá la columna en «— ninguna —» y "
                                "activá «buscar el código de fábrica dentro de la descripción»."
                            )

                    if diag["cientificos"]:
                        st.error(
                            f"🛑 **{diag['cientificos']} código(s) llegaron con los dígitos "
                            f"comidos** (por ejemplo: "
                            f"{', '.join(diag['ejemplos_cientificos'][:3])}). Excel muestra los "
                            "números de más de once dígitos en notación científica y, al "
                            "guardar, escribe lo que muestra: de `7793960026946` queda "
                            "`7.79396E+12` y los últimos siete dígitos ya no están en el "
                            "archivo.\n\n"
                            "**Es peor que una fecha mal leída**, porque no se nota: "
                            "reconstruirlo da `7793960000000`, que tiene trece dígitos y parece "
                            "un código de barras perfecto. Se cargaría sin una queja y después "
                            "el escáner no encontraría nada, sin ninguna pista de por qué.\n\n"
                            "**Cómo arreglarlo:** volvé a exportar con esa columna en formato "
                            "**Texto**, o pedí el archivo en .csv y **no lo abras con Excel** "
                            "antes de subirlo — abrirlo y guardarlo es lo que los rompe."
                        )

                    if diag["fechas"]:
                        st.error(
                            f"📅 **{diag['fechas']} código(s) llegaron convertidos en fecha** "
                            f"(por ejemplo: {', '.join(diag['ejemplos_fechas'][:3])}). "
                            "Esto lo hace Excel solo: códigos como «12-15», «3/8» o «8-10» los "
                            "toma por fechas al guardar el archivo, y ya no hay forma de saber "
                            "cuál era el original.\n\n"
                            "**Cómo arreglarlo:** pedile la lista al proveedor en **.csv**, o abrí "
                            "el Excel, seleccioná la columna de códigos, ponela en formato "
                            "**Texto** y volvé a pegar los datos. Estas filas se van a saltear: "
                            "es preferible eso a cargar un código inventado que nunca va a coincidir."
                        )

                    if diag["columnas_desiguales"] > diag["total"] * 0.3:
                        st.warning(
                            f"⚠️ {diag['columnas_desiguales']} fila(s) tienen bastantes menos "
                            "columnas que el encabezado. Suele pasar cuando la planilla trae "
                            "subtítulos por rubro en el medio, o cuando la fila de encabezado "
                            "elegida no es la correcta."
                        )
                    if diag["vacias"]:
                        st.caption(f"({diag['vacias']} fila(s) vacías, se ignoran solas)")

                st.markdown("---")
                st.markdown("**Cuando la lista no trae el código de fábrica**")
                buscar_oem_en_desc = st.checkbox(
                    "🔎 Buscar códigos de fábrica dentro de la descripción",
                    value=bool(mapeo_previo["buscar_oem_en_desc"]) if mapeo_previo else False,
                    help="Muchas listas meten el OEM en el texto ('... ORIG 6Q0407365'). Esto lo saca de ahí. "
                         "Es conservador a propósito: ante la duda no lo toma, para no ensuciar la base."
                )
                prov_es_oem = st.checkbox(
                    "🏭 El código del proveedor YA es el código de fábrica",
                    value=bool(mapeo_previo["prov_es_oem"]) if mapeo_previo else False,
                    help="Para listas donde el proveedor usa directamente el código original. Se carga "
                         "también como OEM y quedan vinculados, así engancha con las listas de otros proveedores."
                )

                if buscar_oem_en_desc and idx_desc is not None:
                    muestras = []
                    # Los códigos ya cargados, UNA vez. Adentro del bucle eran hasta 60
                    # recorridas completas de la tabla de productos solo para saber si el caché
                    # seguía vigente.
                    _conocidos_muestra = codigos_del_catalogo(version_del_catalogo())
                    # El mismo filtro que la importación: tira los códigos que se repiten en
                    # muchas filas (el modelo del camión, no el repuesto). Sin esto, la muestra
                    # mostraba códigos que después la importación descartaba: «DEUTZ
                    # F6L913/BF6L913» decía «detecta F6L913» y pedía que uno lo revisara.
                    _pares_muestra = [
                        (valor_o_vacio(f[idx_desc]) if idx_desc < len(f) else "",
                         valor_o_vacio(f[idx_prov]) if idx_prov is not None and idx_prov < len(f) else "")
                        for f in todas_filas[header_row + 1:]]
                    _estricta_muestra = not la_lista_declara_codigos(_pares_muestra)
                    _confiables_muestra, _ = codigos_confiables_de_descripciones(
                        _pares_muestra, codigos_conocidos=_conocidos_muestra,
                        declarados_o_conocidos=_estricta_muestra)
                    if _estricta_muestra:
                        ayuda("Esta lista casi nunca marca el código de fábrica («REF ORIG», "
                              "«Nº», «//»), así que de la descripción se toman solo los "
                              "marcados y los que ya son el código de otra lista. Lo demás "
                              "que parece un código acá suele ser una medida o un motor.")
                    for fila_prev in todas_filas[header_row + 1:header_row + 60]:
                        texto_desc = valor_o_vacio(fila_prev[idx_desc]) if idx_desc < len(fila_prev) else ""
                        cod_fila = (valor_o_vacio(fila_prev[idx_prov])
                                    if idx_prov is not None and idx_prov < len(fila_prev) else "")
                        # Con el mismo criterio que la importación real: si esta muestra
                        # detectara con otras reglas, mostraría algo distinto de lo que va a
                        # pasar, que es exactamente lo que la muestra existe para evitar.
                        hallados = [x for x in extraer_codigos_de_texto(
                                        texto_desc, codigo_propio=cod_fila,
                                        codigos_conocidos=_conocidos_muestra,
                                        declarados_o_conocidos=_estricta_muestra)
                                    if sanitizar(x) in _confiables_muestra]
                        if hallados:
                            muestras.append({"Descripción": texto_desc[:60], "Detecta": ", ".join(hallados)})
                        if len(muestras) >= 8:
                            break
                    if muestras:
                        st.caption("Así quedaría (muestra de las primeras filas) — revisá antes de importar. "
                                   "Al importar se cuentan las repeticiones sobre la lista entera, "
                                   "así que alguno de estos todavía puede quedar afuera:")
                        st.dataframe(muestras, width="stretch", hide_index=True)
                    else:
                        st.caption("En las primeras filas no encontré códigos dentro de la descripción.")
                elif buscar_oem_en_desc and idx_desc is None:
                    st.warning("Para buscar códigos en la descripción, elegí primero la columna de descripción.")

        st.markdown("**🔒 Antes de importar: ¿qué hacemos con las equivalencias?**")
        cargar_directo = st.radio(
            "Equivalencias de esta lista:",
            ["Mandarlas a revisar (recomendado)", "Cargarlas directo"],
            key="modo_carga_equivalencias", label_visibility="collapsed",
            help="Una lista puede generar miles de vínculos de una sola vez."
        ) == "Cargarlas directo"
        if cargar_directo:
            st.warning(
                "⚠️ Se van a cargar sin revisar. Si la columna de código de fábrica tiene algún "
                "error, esos vínculos equivocados quedan en la base y después es difícil encontrarlos. "
                "Usalo solo con listas de proveedores en las que confiés plenamente."
            )
        else:
            explicar(
                "Los productos y precios se cargan igual y quedan buscables enseguida.",
                "Lo único que espera son las **equivalencias**: te esperan en Estadísticas → 🔗 "
                "Equivalencias sugeridas, ya separadas entre las limpias y las que tienen algo raro."
            )

        # Un mapeo roto seguro (precio y stock en la misma columna) no deja importar; uno
        # dudoso (el código parece un precio) pide confirmarlo. Es el único momento en que
        # corregirlo es barato: después hay que deshacer la lista entera.
        _graves = [t for g, t in _problemas_del_mapeo if g]
        _importar_igual = True
        if _problemas_del_mapeo and not _graves:
            _importar_igual = st.checkbox("Revisé los avisos del mapeo y quiero importar igual",
                                          key="importar_con_dudas")
        procesar = st.button("📥 Procesar e Importar Lista", type="primary",
                             disabled=bool(_graves) or not _importar_igual)
        if _graves:
            st.caption("🛑 Corregí el mapeo de columnas de arriba para poder importar.")

        if procesar:
            if not archivo:
                st.warning("Indicá un archivo primero (subilo o escribí su ruta).")
            elif not nombre_prov.strip():
                st.warning("Ingresá el nombre de la marca / proveedor.")
            elif not todas_filas:
                st.warning("No se pudo leer el archivo, revisá el formato.")
            elif len(encabezado) < 1:
                st.warning("El archivo no tiene ninguna columna con datos.")
            else:
                try:
                    # La MISMA fila que se eligió arriba. Si acá se volviera a detectar por
                    # separado, la vista previa y la carga real podrían leer filas distintas y
                    # uno importaría algo diferente de lo que vio.
                    header_row = max(0, st.session_state.get("fila_encabezado", 1) - 1)

                    # Releer completo (leer_excel con nrows=200 antes era solo para la vista previa)
                    # La MISMA hoja que se eligió arriba: si acá se releyera sin ese dato, se
                    # importaría una hoja distinta de la que se vio en la vista previa.
                    todas_filas_completas = leer_excel(archivo, hoja=hoja_elegida)
                    filas_datos = todas_filas_completas[header_row + 1:]

                    # Antes de cargar nada: si se van a buscar códigos en la descripción, hay
                    # que contarlos sobre la lista ENTERA primero. Fila por fila es imposible
                    # saber si 'CLA200' es un código o el modelo del auto; recién mirando las
                    # 25.000 filas juntas se ve que aparece 15 veces y el código de verdad 2.
                    oem_desc_confiables, oem_desc_conteo = set(), {}
                    oem_desc_descartados = 0
                    # Los códigos que ya están cargados. Se leen UNA vez, antes del candado y
                    # antes del bucle: adentro se consultan por cada token de cada fila.
                    codigos_ya_cargados = codigos_del_catalogo(version_del_catalogo())
                    oem_desc_estricta = False
                    if buscar_oem_en_desc and idx_desc is not None:
                        _pares_desc = [
                            (valor_o_vacio(f[idx_desc]) if idx_desc < len(f) else "",
                             valor_o_vacio(f[idx_prov]) if idx_prov is not None and idx_prov < len(f) else "")
                            for f in filas_datos]
                        oem_desc_estricta = not la_lista_declara_codigos(_pares_desc)
                        oem_desc_confiables, oem_desc_conteo = codigos_confiables_de_descripciones(
                            _pares_desc, codigos_conocidos=codigos_ya_cargados,
                            declarados_o_conocidos=oem_desc_estricta)

                    cargados = 0
                    cargados_sin_equiv = 0
                    omitidos = 0
                    descartados_cortos = 0
                    precios_actualizados = 0
                    precios_frenados = []
                    precios_en_cero = 0
                    # El mismo código dos veces en la lista con precios distintos («AB-123»
                    # por unidad y «AB123» por caja de 10): el segundo pisaba al primero, o
                    # el freno lo paraba sin decir por qué. Ahora se avisa con ejemplos.
                    _precio_en_esta_lista, repetidos_con_otro_precio = {}, []
                    filas_omitidas = []
                    eq_batch = set()  # inserción en lote: se acumulan los pares y se insertan todos juntos al final
                    _pares_de_la_lista = set()   # todo lo que la lista declara, nuevo o no
                    _descripciones_que_trae = {}   # id -> la descripción de ESTA lista
                    _ids_de_la_lista = set()   # los productos DISTINTOS que tocó: ver el cartel del final
                    _ids_con_codigo_de_fabrica = set()
                    progreso = st.progress(0, text="Procesando filas...")
                    total = len(filas_datos)

                    # Todo el trabajo de escritura va con el candado tomado, para que ninguna otra
                    # persona pueda buscar/escribir a mitad de una importación larga y quede todo trabado.
                    # Y en UNA transacción: antes cada sentencia se confirmaba sola, así que si la
                    # carga se cortaba en la fila 12.000 (una celda rara, el navegador que se
                    # cierra, la app que se reinicia) quedaban 12.000 precios pisados, ningún
                    # vínculo y ningún registro de la importación para poder deshacerla.
                    # Ahora o entra la lista entera o no entra nada.
                    with db_lock, transaccion():
                        prov_id = get_or_create_marca(nombre_prov, "PROVEEDOR")
                        oem_id = get_or_create_marca("OEM / FABRICA", "OEM")
                        # El coeficiente de la lista de este proveedor, si se cargó uno: ver
                        # guardar_coeficiente_de_lista(). Sin esto, corregir la escala una
                        # vez no alcanzaba: la lista siguiente volvía a traer los crudos.
                        _coef_lista = coeficiente_de_lista(prov_id)

                        for n, fila in enumerate(filas_datos):
                            def celda(idx):
                                return fila[idx] if idx is not None and idx < len(fila) else None

                            raw_p_cell = valor_codigo(celda(idx_prov))
                            raw_o_cell = valor_codigo(celda(idx_oem)) if idx_oem is not None else ""
                            desc = separar_texto_pegado(valor_o_vacio(celda(idx_desc)))

                            # OJO con el fallback: antes, si dividir_codigos no devolvía nada se
                            # usaba la celda cruda igual — así que un '1' suelto entraba lo mismo.
                            # Ahora la celda cruda también tiene que pasar el filtro.
                            codigos_prov = dividir_codigos(raw_p_cell)
                            if not codigos_prov and raw_p_cell and es_codigo_util(raw_p_cell):
                                codigos_prov = [raw_p_cell]
                            codigos_oem = dividir_codigos(raw_o_cell)
                            if not codigos_oem and raw_o_cell and es_codigo_util(raw_o_cell):
                                codigos_oem = [raw_o_cell]

                            # Para poder avisar al final cuántos se filtraron por ser números sueltos
                            if raw_p_cell and not codigos_prov:
                                descartados_cortos += 1
                            if raw_o_cell and not codigos_oem:
                                descartados_cortos += 1

                            # Si la lista no trae OEM, se intenta sacarlo de la descripción.
                            # Solo se aceptan los que no se repiten por toda la lista: ver
                            # codigos_confiables_de_descripciones() y el conteo de más arriba.
                            # Y si la lista casi nunca marca el código de fábrica, solo los
                            # que marcó («REF ORIG», «Nº», «//») o que ya son el código de otra
                            # lista: ver la_lista_declara_codigos(). Lo que se deja afuera se
                            # sigue encontrando, porque el buscador busca también en las
                            # descripciones (ver buscar_por_texto()).
                            if not codigos_oem and buscar_oem_en_desc and desc:
                                _cands = extraer_codigos_de_texto(
                                    desc, codigo_propio=raw_p_cell,
                                    codigos_conocidos=codigos_ya_cargados,
                                    declarados_o_conocidos=oem_desc_estricta)
                                codigos_oem = [c for c in _cands
                                               if sanitizar(c) in oem_desc_confiables]
                                if not codigos_oem and _cands:
                                    oem_desc_descartados += 1

                            # Sin código de proveedor no hay nada que cargar: esa fila sí se omite
                            if not codigos_prov:
                                omitidos += 1
                                filas_omitidas.append({"Proveedor": raw_p_cell, "OEM": raw_o_cell,
                                                        "Descripcion": desc, "Motivo": "sin código de proveedor"})
                                if total and n % 25 == 0:
                                    progreso.progress(min((n + 1) / total, 1.0))
                                continue

                            precio_fila = leer_numero(celda(idx_precio)) if idx_precio is not None else None
                            # Un precio de 0 o negativo no es un precio: es «consultar», «sin
                            # stock» o una celda vacía que el Excel guardó como 0. Antes pisaba el
                            # precio real, y como el freno de saltos no mira los ceros, pasaba
                            # sin aviso: el repuesto quedaba a $0 en el mostrador.
                            if precio_fila is not None and precio_fila <= 0:
                                precios_en_cero += 1
                                precio_fila = None
                            if precio_fila is not None and _coef_lista != 1:
                                precio_fila = round(precio_fila * _coef_lista, 2)
                            stock_fila = leer_numero(celda(idx_stock)) if idx_stock is not None else None

                            # El código de barras de esta fila, si la lista lo trae. Va pegado
                            # al producto y no genera ninguna equivalencia: ver el selector de
                            # arriba y adivinar_columnas().
                            barras_fila = sanitizar(valor_codigo(celda(idx_ean))) if idx_ean is not None else ""

                            # Los códigos de una misma celda se vinculan entre sí más abajo
                            # —son dos números del mismo producto— y ahí está el agujero por el
                            # que entró la peor basura de la base: cuando la celda se parte y
                            # uno de los pedazos no es un código sino una palabra suelta
                            # («PVC», «SPR», «SOPORTE», «CHAPA», «GOMA»), esa palabra queda
                            # como un producto que se repite en decenas de filas y termina
                            # uniéndolas a todas. El «CHAPA» de una lista real colgaba 76
                            # cables distintos.
                            # Se reconocen por no tener NINGÚN dígito. En las 70.888 filas del
                            # catálogo real hay 14 códigos así, y los que son de verdad son
                            # herramientas sueltas (HGONIOMETRO, APLIGAL) que no necesitan
                            # equivalencias con nada.
                            ids_prov = []
                            ids_prov_sin_digitos = set()
                            for raw_p in codigos_prov:
                                clean_p = sanitizar(raw_p)
                                if clean_p:
                                    pid_nuevo = get_or_create_producto(raw_p, clean_p, desc, prov_id)
                                    ids_prov.append(pid_nuevo)
                                    # Lo que dice ESTA lista: ver fichas_que_cambiaron().
                                    if desc:
                                        _descripciones_que_trae.setdefault(pid_nuevo, desc)
                                    if not any(ch.isdigit() for ch in clean_p):
                                        ids_prov_sin_digitos.add(pid_nuevo)
                                    if barras_fila:
                                        c.execute("UPDATE productos SET codigo_barras = ? "
                                                  "WHERE id = ?", (barras_fila, pid_nuevo))
                                    if precio_fila is not None:
                                        _antes_en_lista = _precio_en_esta_lista.get(pid_nuevo)
                                        if _antes_en_lista is not None and _antes_en_lista != precio_fila:
                                            repetidos_con_otro_precio.append(
                                                f"{raw_p} ({formato_precio(_antes_en_lista)} y {formato_precio(precio_fila)})")
                                        _precio_en_esta_lista.setdefault(pid_nuevo, precio_fila)
                                    if precio_fila is not None or stock_fila is not None:
                                        c.execute("SELECT precio FROM productos WHERE id = ?", (pid_nuevo,))
                                        _f = c.fetchone()
                                        precio_viejo = _f["precio"] if _f else None
                                        # Si el precio guardado quedó en 0 (una lista vieja que lo
                                        # pisó), el freno se compara con el último precio de
                                        # verdad: si no, cualquier número pasaba sin mirar.
                                        precio_ref = precio_viejo
                                        if precio_fila is not None and not (precio_viejo and precio_viejo > 0):
                                            c.execute("SELECT precio FROM historial_precios "
                                                      "WHERE producto_id = ? AND precio > 0 "
                                                      "ORDER BY id DESC LIMIT 1", (pid_nuevo,))
                                            _h = c.fetchone()
                                            if _h:
                                                precio_ref = _h["precio"]
                                        raro, motivo = salto_de_precio_sospechoso(
                                            precio_ref, precio_fila, tope_salto
                                        )
                                        if raro:
                                            # El producto se carga igual; lo único que no se pisa
                                            # es el precio, para no cotizar con un número roto.
                                            precios_frenados.append({
                                                "Código": raw_p, "Descripción": (desc or "")[:60],
                                                "Precio actual": precio_ref,
                                                "Precio de la lista": precio_fila,
                                                "Motivo": motivo,
                                                "_id": pid_nuevo,
                                            })
                                            if stock_fila is not None:
                                                c.execute("UPDATE productos SET stock = ? WHERE id = ?",
                                                          (int(stock_fila), pid_nuevo))
                                        else:
                                            if precio_fila is not None and precio_viejo != precio_fila:
                                                c.execute("INSERT INTO historial_precios (producto_id, precio) "
                                                          "VALUES (?, ?)", (pid_nuevo, precio_fila))
                                                precios_actualizados += 1
                                            c.execute(
                                                "UPDATE productos SET "
                                                "precio = COALESCE(?, precio), stock = COALESCE(?, stock) "
                                                "WHERE id = ?",
                                                (precio_fila,
                                                 int(stock_fila) if stock_fila is not None else None,
                                                 pid_nuevo)
                                            )

                            if not ids_prov:
                                omitidos += 1
                                filas_omitidas.append({"Proveedor": raw_p_cell, "OEM": raw_o_cell,
                                                        "Descripcion": desc, "Motivo": "código de proveedor no válido"})
                                if total and n % 25 == 0:
                                    progreso.progress(min((n + 1) / total, 1.0))
                                continue

                            # El código del proveedor ES el de fábrica: se carga también como OEM
                            # para que enganche con las listas de otros proveedores.
                            if prov_es_oem:
                                for raw_p in codigos_prov:
                                    clean_p = sanitizar(raw_p)
                                    if clean_p and clean_p not in {sanitizar(x) for x in codigos_oem}:
                                        codigos_oem.append(raw_p)

                            ids_oem = []
                            for raw_o in codigos_oem:
                                clean_o = sanitizar(raw_o)
                                if clean_o:
                                    ids_oem.append(get_or_create_producto(raw_o, clean_o, desc, oem_id))

                            # ANTES: sin OEM se descartaba la fila entera y el producto ni se cargaba.
                            # Ahora el producto queda cargado igual (buscable por código y por
                            # descripción), solo que sin equivalencia hasta que aparezca de otra lista
                            # o se vincule a mano.
                            _ids_de_la_lista.update(ids_prov)
                            if not ids_oem:
                                cargados_sin_equiv += len(ids_prov)
                                # aunque no haya OEM, los códigos de la misma celda se vinculan entre sí
                                for pid in ids_prov:
                                    for pid2 in ids_prov:
                                        if (pid2 != pid and pid not in ids_prov_sin_digitos
                                                and pid2 not in ids_prov_sin_digitos):
                                            eq_batch.add((min(pid, pid2), max(pid, pid2)))
                                if total and n % 25 == 0:
                                    progreso.progress(min((n + 1) / total, 1.0))
                                continue

                            # Cada par se guarda UNA sola vez, siempre con el id menor primero.
                            # Antes se agregaban las dos direcciones —(a,b) y (b,a)—, y como la
                            # clave primaria es el par ordenado, quedaban dos filas por cada
                            # equivalencia. Eso duplicaba la tabla, contaba doble los vínculos de
                            # cada código (los "códigos puente" mostraban 200 donde había 100) y
                            # hacía que el control de precios listara cada par dos veces.
                            # La búsqueda nunca lo notó porque consulta las dos columnas con OR.
                            _ids_con_codigo_de_fabrica.update(ids_prov)
                            for pid in ids_prov:
                                for oid in ids_oem:
                                    if pid != oid:
                                        eq_batch.add((min(pid, oid), max(pid, oid)))
                                for pid2 in ids_prov:
                                    if (pid2 != pid and pid not in ids_prov_sin_digitos
                                            and pid2 not in ids_prov_sin_digitos):
                                        eq_batch.add((min(pid, pid2), max(pid, pid2)))

                            cargados += 1
                            if total and n % 25 == 0:
                                progreso.progress(min((n + 1) / total, 1.0))

                        # Inserción en lote: mucho más rápido que insertar de a un vínculo por vez
                        if eq_batch:
                            # No revivir vínculos que ya fueron rechazados en una revisión
                            # anterior, NI volver a preguntar por los que ya están cargados.
                            # Lo segundo faltaba, y es lo que pasa cada vez que un proveedor
                            # manda su lista nueva de precios: reimportando la de FISPA que ya
                            # estaba, quedaron 13.943 vínculos «esperando revisión» y 13.756 ya
                            # eran equivalencias aprobadas. El informe de la importación encima
                            # decía «539 de los 13.943 vínculos nuevos están casi seguro mal».
                            # Mismo criterio que guardar_equivalencias_pendientes().
                            _pares_de_la_lista = set(eq_batch)
                            rechazados_antes = pares_rechazados()
                            ya_cargados = pares_ya_cargados()
                            _vinculos_ya_cargados = len(eq_batch & ya_cargados)
                            eq_batch = {p for p in eq_batch
                                        if p not in rechazados_antes and p not in ya_cargados}
                            # Los que ya esperaban revisión de una lista anterior tampoco se
                            # cuentan como nuevos: la cola se queda con la fila vieja (INSERT OR
                            # IGNORE), así que el cartel decía «N nuevos» con pares que no eran
                            # de esta lista, y «deshacer esta lista» no los sacaba.
                            _ya_pendientes = pares_ya_pendientes() if not cargar_directo else set()
                            _vinculos_ya_pendientes = len(eq_batch & _ya_pendientes)
                            eq_batch -= _ya_pendientes
                        else:
                            _vinculos_ya_cargados = 0
                            _vinculos_ya_pendientes = 0
                        # El nombre del lote se arma SIEMPRE, vayan los vínculos a revisión o
                        # directo: es la etiqueta que después permite deshacer toda la lista.
                        # Con año y segundos: con solo «día/mes hora:minuto», dos listas del mismo
                        # proveedor importadas en el mismo minuto (o la del año pasado el mismo
                        # día) quedaban con la misma etiqueta, y deshacer una se llevaba la otra.
                        _nombre_arch = (os.path.basename(archivo) if isinstance(archivo, str)
                                        else getattr(archivo, "name", "lista"))
                        lote_importacion = (f"{nombre_prov.upper()} · {_nombre_arch} · "
                                             f"{datetime.now():%d/%m/%Y %H:%M:%S}")
                        if eq_batch:
                            if cargar_directo:
                                c.executemany(
                                    "INSERT OR IGNORE INTO equivalencias (producto_a_id, producto_b_id, created_at, lote) "
                                    "VALUES (?, ?, datetime('now'), ?)",
                                    [(a, b, lote_importacion) for a, b in eq_batch]
                                )
                            else:
                                c.executemany(
                                    "INSERT OR IGNORE INTO equivalencias_pendientes "
                                    "(producto_a_id, producto_b_id, origen, lote) VALUES (?, ?, 'lista_proveedor', ?)",
                                    [(a, b, lote_importacion) for a, b in eq_batch]
                                )

                        try:
                            _huella = huella_de_archivo(archivo.getvalue())
                        except Exception as _err:
                            anotar_error("nivel principal", _err)
                            _huella = None
                        c.execute(
                            "INSERT INTO importaciones (marca, archivo, filas_cargadas, filas_omitidas, huella, lote) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            (nombre_prov.upper(), getattr(archivo, "name", str(archivo)),
                             cargados, omitidos, _huella, lote_importacion)
                        )

                    progreso.empty()

                    # CADA NÚMERO CON SU NOMBRE. 'cargados' NO es «filas leídas»: es la
                    # cantidad de filas que además generaron una equivalencia. Importando la
                    # lista de Illinois —6.900 filas— el cartel decía «Se leyeron 2391 fila(s)»,
                    # que es un tercio de la verdad, y encima en la misma frase que decía que los
                    # productos ya estaban cargados. El que importa se queda pensando que perdió
                    # 4.500 filas.
                    _total_filas = len(filas_datos)
                    _con_equiv = cargados
                    # Productos DISTINTOS. Era «filas con equivalencia» + «códigos sin
                    # equivalencia», que mezcla unidades y cuenta dos veces un código que la
                    # lista repite: importando la de IMPERIAL decía «se leyeron 43.303 filas y
                    # quedaron cargados 43.347 productos» —más productos que filas— y la marca
                    # quedó con 43.101.
                    _productos = len(_ids_de_la_lista)
                    _resumen = (f"Se leyeron **{miles(_total_filas)} fila(s)** y quedaron cargados "
                                f"**{miles(_productos)} producto(s)**"
                                + (f", {miles(omitidos)} fila(s) se saltearon" if omitidos else "")
                                + ".")
                    if cargar_directo:
                        st.success(_resumen + f" {miles(_con_equiv)} de esas filas traían además un "
                                              "código de fábrica y ya generaron equivalencias.")
                    else:
                        # En verde y con la palabra "equivalencia" parecía que ya estaban puestas.
                        # No lo están: van a la cola de revisión, y hasta que se aprueben la
                        # búsqueda NO cruza marcas. Decirlo mal es lo que hace que alguien importe
                        # tres listas, busque un código y crea que la app no relaciona proveedores.
                        # Y se cuentan los vínculos NUEVOS, no las filas con código de fábrica:
                        # reimportando la lista de FISPA, que ya estaba, decía «las 4.446 filas
                        # quedaron esperando tu aprobación» con casi todo ya aprobado de antes.
                        _ya_txt = (f" Otros {miles(_vinculos_ya_cargados)} ya estaban cargados de "
                                   "antes y siguen funcionando." if _vinculos_ya_cargados else "")
                        if _vinculos_ya_pendientes:
                            _ya_txt += (f" Y {miles(_vinculos_ya_pendientes)} ya esperaban revisión "
                                        "de una lista anterior.")
                        if eq_batch:
                            st.warning(
                                _resumen + f" Los precios ya están, **pero {miles(len(eq_batch))} "
                                "vínculo(s) nuevos todavía NO**: quedaron esperando tu "
                                "aprobación, y hasta que los apruebes buscar esos códigos no va "
                                "a traer los equivalentes de otras marcas." + _ya_txt
                            )
                        else:
                            st.success(_resumen + " Los precios ya están, y esta lista no trajo "
                                       "vínculos nuevos para revisar." + _ya_txt)
                    # EL PROVEEDOR CAMBIÓ DE EQUIVALENTE SIN AVISAR: la lista anterior decía
                    # ABC123 = XYZ456 y esta dice ABC123 = XYZ999. El vínculo viejo queda (no se
                    # borra nada solo), pero se avisa: puede ser una corrección del proveedor o
                    # un error de la lista nueva. Ver equivalentes_que_la_lista_dejo_de_declarar().
                    try:
                        _cambios = equivalentes_que_la_lista_dejo_de_declarar(
                            nombre_prov, lote_importacion, _ids_de_la_lista, _pares_de_la_lista)
                    except sqlite3.Error as _err:
                        anotar_error("importar/cambios de equivalente", _err)
                        _cambios = {"codigos": 0}
                    if _cambios["codigos"]:
                        st.warning(
                            f"🔀 **{miles(_cambios['codigos'])} código(s) de {nombre_prov} ya no "
                            "dicen lo mismo que en la lista anterior**: antes los vinculaba con un "
                            "número y esta lista no. **No se borró nada**: los vínculos viejos "
                            "siguen cargados. Si el proveedor los corrigió, buscá el código y "
                            "cortá el viejo; si la que está mal es esta lista, no hagas nada."
                            + (f" {miles(_cambios['sin_ninguno'])} de ellos ahora no traen "
                               "ningún número: si son muchos, fijate si la columna de códigos "
                               "de fábrica quedó elegida." if _cambios["sin_ninguno"] else ""))
                        st.dataframe(_cambios["ejemplos"], hide_index=True, width="stretch")
                    # LA FICHA QUE CAMBIÓ: el producto ya estaba y esta lista lo describe con
                    # otra medida, otro lado u otra tensión. La descripción guardada no se pisa
                    # (nunca se pisó): se avisa. Ver fichas_que_cambiaron().
                    try:
                        _fichas = fichas_que_cambiaron(_descripciones_que_trae)
                    except sqlite3.Error as _err:
                        anotar_error("importar/fichas que cambiaron", _err)
                        _fichas = {"cambiaron": 0}
                    if _fichas["cambiaron"]:
                        st.warning(
                            f"📝 **{miles(_fichas['cambiaron'])} producto(s) de {nombre_prov} "
                            "vienen con otra ficha**: una medida, el lado o la tensión no son los "
                            "que estaban guardados. **No se cambió nada**: la app sigue con la "
                            "descripción de antes. Mirá cuál es la buena; si es la nueva, "
                            "corregila a mano en el producto.")
                        st.dataframe(_fichas["ejemplos"], hide_index=True, width="stretch")
                    # Los números del chequeo de salud cambiaron: que se recalculen
                    invalidar_salud()

                    # Puntuar los vínculos que acaban de entrar, para que el buscador ya los
                    # use. Antes había que acordarse de tocar «Calcular la confianza».
                    try:
                        recalcular_confianzas(limite=4000)
                    except Exception as _err:
                        anotar_error("nivel principal", _err)
                        pass

                    # Informe de lo que pasó con ESTA lista, mientras se la tiene fresca
                    try:
                        _inf = informe_post_importacion(lote_importacion, nombre_prov, cargados)
                    except Exception as _err:
                        anotar_error("nivel principal", _err)
                        _inf = {"puntos": [], "vinculos_nuevos": 0}
                    if _inf.get("pedidos_que_entraron"):
                        _ped = _inf["pedidos_que_entraron"]
                        st.success(
                            f"📞 **Esta lista trajo {len(_ped)} código(s) que te habían pedido y "
                            "no tenías.** "
                            + ", ".join(f"{x['Buscado']} ({x['Veces']} vez/veces)" for x in _ped[:6])
                            + (" y más" if len(_ped) > 6 else "")
                            + ". Están en Estadísticas → 🔎 Búsquedas sin resultado.")
                    if _inf["puntos"]:
                        st.markdown("#### 🔎 Qué conviene revisar de esta lista")
                        for nivel, titulo, detalle, donde in _inf["puntos"]:
                            (st.error if nivel == "alto" else st.warning)(
                                f"**{titulo}**\n\n{detalle}\n\n📍 {donde}")
                    elif _inf.get("analisis_por_atras"):
                        st.info(f"🔎 Los {miles(_inf['analisis_por_atras'])} vínculos nuevos se están "
                                 "analizando por atrás (en una lista así de grande tarda un "
                                 "rato). Cuando abras Estadísticas → 🔗 Equivalencias sugeridas "
                                 "ya vas a ver cuáles están casi seguro mal.")
                    elif _inf.get("pendientes"):
                        st.info(f"🔎 Se revisaron {_inf['pendientes']} vínculo(s) y ninguno "
                                 "disparó alarmas. Siguen esperando tu aprobación.")
                    elif _inf["vinculos_nuevos"]:
                        st.info(f"✅ Entraron {_inf['vinculos_nuevos']} vínculo(s) y ninguno "
                                 "disparó alarmas.")
                    # Y ahora la parte que antes había que ir a pedir a mano: buscar las
                    # relaciones que esta lista hace posibles. Va acá y no en las tareas del día
                    # porque es el único momento en que hay algo nuevo que encontrar, y el único
                    # en que la persona ya está esperando. Ver descubrimiento_post_importacion().
                    # Se PIDE el descubrimiento, no se espera. Tarda 110 segundos sobre el
                    # catálogo real, y hacer esperar dos minutos a alguien que acaba de subir
                    # una planilla desde el celular —con la pantalla que se apaga sola y el
                    # navegador que puede cortar— era la peor parte de haberlo automatizado.
                    # Lo levanta el hilo de fondo, que ya existe. Ver _trabajo_de_fondo().
                    try:
                        guardar_config("descubrimiento_pendiente", "1")
                        # Las fotos y fichas de lo nuevo: solo si lo elegiste (ver
                        # lo_nuevo_al_importar()). Lo que ya terminó no arranca solo.
                        lo_nuevo_al_importar()
                        arrancar_tanda_de_fondo()
                        st.info("🧠 **Se están buscando solas las relaciones nuevas de esta "
                                 "lista.** Corre por atrás: podés seguir usando la app.")
                        explicar(
                            "Tarda un par de minutos y no hay que esperarlo.",
                            "Se corren tres cosas sobre TODO el catálogo, no solo sobre esta "
                            "lista: el barrido de descripciones entre todas las marcas, las "
                            "aplicaciones que se deducen de las descripciones, y el cruce por "
                            "auto.\n\nCuando termine, lo nuevo aparece en Estadísticas → "
                            "🔗 Equivalencias sugeridas. Nada se carga solo: hasta que lo "
                            "apruebes, buscar un código no trae esos equivalentes."
                        )
                    except Exception as _err:
                        anotar_error("nivel principal", _err)

                    # Recordar el mapeo que funcionó, para la próxima lista de este proveedor
                    guardar_mapeo_columnas(nombre_prov, idx_prov, idx_oem, idx_desc,
                                            idx_precio, idx_stock, buscar_oem_en_desc, prov_es_oem,
                                            idx_ean=idx_ean, encabezado=encabezado)
                    if not cargar_directo and eq_batch:
                        st.info(
                            f"🔒 {len(eq_batch)} vínculo(s) quedaron **esperando tu revisión** — todavía "
                            "no están cargados como equivalencias. Andá a Estadísticas → "
                            "🔗 Equivalencias sugeridas para aprobarlos (podés hacerlo en bloque)."
                        )
                    # Productos distintos, y sin los que en OTRA fila de la lista sí trajeron código
                    # de fábrica. Sumaba de a código por fila: con la de JL decía «25.916 sin
                    # código de fábrica» al lado de «quedaron cargados 25.912 producto(s)».
                    _sin_codigo = len(_ids_de_la_lista - _ids_con_codigo_de_fabrica)
                    if _sin_codigo:
                        st.info(
                            f"📦 Además se cargaron {miles(_sin_codigo)} producto(s) que no traían código "
                            "de fábrica. Quedan buscables por código y por descripción; les va a aparecer "
                            "la equivalencia sola cuando el mismo código llegue desde la lista de otro "
                            "proveedor, o podés vincularlos a mano desde 'Vincular manual'."
                        )
                    olvidar_la_escala_de_precios()
                    if precios_actualizados:
                        st.success(f"💲 Se actualizaron {precios_actualizados} precio(s)."
                                   + (f" Con el coeficiente de la lista: ×{miles(_coef_lista)}."
                                      if _coef_lista != 1 else ""))

                    # Los frenados se muestran AFUERA de este bloque (ver más abajo). Adentro no
                    # servía: este bloque solo corre en el toque de «Procesar», así que al
                    # tildar «Revisé la lista» la página se redibujaba sin él y el botón de
                    # aplicarlos no llegaba a aparecer nunca. Probado: 30 precios frenados,
                    # checkbox tildado, cero botones.
                    if precios_frenados:
                        st.session_state["precios_frenados_de_la_carga"] = {
                            "lote": lote_importacion, "filas": precios_frenados}
                    else:
                        st.session_state.pop("precios_frenados_de_la_carga", None)
                    if repetidos_con_otro_precio:
                        st.warning(
                            f"🔁 {miles(len(repetidos_con_otro_precio))} código(s) aparecen **más de una "
                            "vez en la lista con precios distintos** (suele ser la unidad y la caja, "
                            "o dos presentaciones). Quedó uno solo de los precios: revisalos. "
                            "Ejemplos: " + ", ".join(repetidos_con_otro_precio[:5])
                        )
                    if precios_en_cero:
                        st.caption(
                            f"🧹 {miles(precios_en_cero)} fila(s) traían el precio en 0 o negativo "
                            "(«consultar», sin precio). Se cargaron sin tocar el precio que ya "
                            "tenían: un 0 no es un precio."
                        )

                    if descartados_cortos:
                        st.caption(
                            f"🧹 Se ignoraron {descartados_cortos} valor(es) de las columnas de código "
                            "por ser un número suelto de 1 o 2 dígitos (cantidad, número de orden, "
                            "bulto). No son códigos y ensuciaban las equivalencias."
                        )
                    if oem_desc_descartados:
                        _repes = sorted(((v, k) for k, v in oem_desc_conteo.items()
                                         if v > TOPE_REPETICIONES_EN_DESCRIPCION), reverse=True)[:6]
                        st.caption(
                            f"🧹 En {oem_desc_descartados} fila(s) encontré algo parecido a un código "
                            "dentro de la descripción pero no lo cargué, porque el mismo texto se "
                            f"repite en más de {TOPE_REPETICIONES_EN_DESCRIPCION} productos de esta "
                            "lista: es la motorización, el modelo o una muletilla, no un código."
                            + (" Los más repetidos: "
                               + ", ".join(f"{c} ({v} veces)" for v, c in _repes) if _repes else "")
                        )
                    if omitidos:
                        st.warning(f"Se omitieron {omitidos} filas porque no tenían código de proveedor.")
                        st.dataframe(filas_omitidas, width="stretch")
                        st.download_button(
                            "⬇️ Descargar filas omitidas",
                            data=to_excel_bytes(filas_omitidas),
                            file_name="filas_omitidas.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )

                    # Detección de posibles duplicados / errores de tipeo dentro de la marca recién cargada
                    sospechosos = detectar_posibles_duplicados(prov_id)
                    if sospechosos is None:
                        st.caption(
                            "ℹ️ La marca tiene demasiados códigos cargados como para revisar duplicados "
                            "automáticamente sin demorar la página."
                        )
                    elif sospechosos:
                        st.warning(
                            f"⚠️ Encontré {len(sospechosos)} par(es) de códigos muy parecidos dentro de "
                            f"'{nombre_prov}' — podrían ser errores de tipeo. Revisalos:"
                        )
                        st.dataframe(sospechosos, width="stretch", hide_index=True)
                except Exception as e:
                    anotar_error("nivel principal", e)
                    st.error(f"Error procesando la lista: {e}")

        _frenados = st.session_state.get("precios_frenados_de_la_carga")
        if _frenados:
            _filas_fr = _frenados["filas"]
            st.warning(
                f"🛑 {miles(len(_filas_fr))} precio(s) de la última lista quedaron **sin actualizar** "
                "porque el cambio no parece un aumento sino un error de la lista. El producto se "
                "cargó igual; lo único que no se tocó es el precio."
            )
            st.dataframe(_filas_fr[:100], width="stretch", hide_index=True,
                         column_config={"_id": None})
            st.download_button(
                "⬇️ Bajar la lista completa de precios frenados",
                data=to_excel_bytes([{k: v for k, v in f.items() if k != "_id"}
                                     for f in _filas_fr]),
                file_name="precios_frenados.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="bajar_precios_frenados"
            )
            st.caption("Si mirás la lista y los precios están bien (por ejemplo, hubo un aumento "
                       "fuerte de verdad), aplicalos igual desde acá.")
            _cf1, _cf2 = st.columns(2)
            _revisado = _cf1.checkbox("Revisé la lista y los precios de la planilla son correctos",
                                      key="confirmar_precios_frenados")
            if _cf1.button(f"💲 Aplicar igual esos {miles(len(_filas_fr))} precios",
                           disabled=not _revisado, key="aplicar_precios_frenados"):
                with db_lock, transaccion():
                    for f in _filas_fr:
                        if f["Precio de la lista"] is not None:
                            c.execute("INSERT INTO historial_precios (producto_id, precio) "
                                      "VALUES (?, ?)", (f["_id"], f["Precio de la lista"]))
                            c.execute("UPDATE productos SET precio = ? WHERE id = ?",
                                      (f["Precio de la lista"], f["_id"]))
                st.session_state.pop("precios_frenados_de_la_carga", None)
                st.session_state.pop("confirmar_precios_frenados", None)
                invalidar_salud()
                st.success(f"💲 Se aplicaron {miles(len(_filas_fr))} precio(s).")
            elif _cf2.button("🙈 Dejar los precios como estaban", key="descartar_precios_frenados"):
                st.session_state.pop("precios_frenados_de_la_carga", None)
                st.rerun()

        st.markdown("---")
        st.markdown("**📄 Cargar remito por foto (con IA)**")
        explicar(
            "Sacale una foto o subí una imagen del remito/factura de un proveedor.",
            "La IA lee los ítems y te arma una lista para revisar — no toca el stock hasta que vos "
            "confirmes. Solo actualiza cantidad de los códigos que ya existen en tu catálogo; los "
            "que no coincidan con nada, los tenés que cargar por 'Vincular manual' o con un Excel "
            "nuevo."
        )
        foto_remito = subir_archivo("Foto del remito:", ["png", "jpg", "jpeg"], "remito")
        remito_ok = archivo_listo(foto_remito, "foto del remito")
        if foto_remito:
            boton_otro_archivo("remito", "🗑️ Usar otra foto", key="otra_foto_remito")
        if st.button("🔍 Leer remito", disabled=not remito_ok):
            with st.spinner("Leyendo remito..."):
                items_leidos, error_remito = leer_remito_por_foto(foto_remito.getvalue())
            if error_remito:
                st.error(error_remito)
            elif not items_leidos:
                st.warning("No se pudo leer ningún ítem en esa imagen.")
            else:
                st.session_state["items_remito"] = cotejar_items_remito(items_leidos)

        if st.session_state.get("items_remito"):
            items_actuales = st.session_state["items_remito"]
            coinciden = [i for i in items_actuales if i["_producto_id"]]
            no_coinciden = [i for i in items_actuales if not i["_producto_id"]]
            st.success(f"Se leyeron {len(items_actuales)} ítem(s) — {len(coinciden)} coinciden con tu catálogo.")
            st.dataframe(
                [{k: v for k, v in i.items() if not k.startswith("_")} for i in items_actuales],
                width="stretch", hide_index=True
            )
            if no_coinciden:
                st.caption(
                    f"⚠️ {len(no_coinciden)} ítem(s) no coinciden con ningún código cargado — "
                    "revisá si están mal leídos o si son productos nuevos para vos."
                )
            colr1, colr2 = st.columns(2)
            if coinciden and colr1.button(f"💾 Sumar stock de los {len(coinciden)} que coinciden"):
                _cuando_remito = cuando_se_sumo_el_remito(items_actuales)
                actualizados = aplicar_carga_remito(items_actuales)
                if actualizados is None:
                    st.warning(f"Este mismo remito ya se sumó al stock el {_cuando_remito}: no "
                               "se suma dos veces. Si de verdad llegó dos veces la misma "
                               "mercadería, cargá el stock a mano desde el buscador.")
                else:
                    st.success(f"Stock actualizado en {actualizados} producto(s).")
                    st.session_state.pop("items_remito", None)
                    st.rerun()
            if colr2.button("🗑️ Descartar esta lectura"):
                st.session_state.pop("items_remito", None)
                st.rerun()

"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/.

🗂️ Administrar → 🧹 Mantenimiento → 🏷️ Códigos de barras: sus herramientas, en el orden
en que se muestran. Corre después de pantallas/mantenimiento.py, que elige el grupo."""

# ============================================================
# MANTENIMIENTO → CÓDIGOS DE BARRAS
# ============================================================
if pagina == PAGINAS[3]:
    if sub_admin == SUB_ADMIN[4]:
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
                ayuda(
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

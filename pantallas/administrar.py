"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/."""

# ============================================================
# ADMINISTRAR
# ============================================================
# La solapa «🧹 Mantenimiento» está aparte: pantallas/mantenimiento.py y un archivo por grupo.
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

    # SUB_ADMIN está en logica/interfaz.py, con las demás listas de navegación.
    if st.session_state.get("sub_admin") not in SUB_ADMIN:
        st.session_state["sub_admin"] = SUB_ADMIN[0]
    # El mismo buscador que adentro de Mantenimiento, pero acá arriba: el que entra por primera
    # vez no tiene por qué saber que las herramientas viven detrás de una solapa que se llama
    # «Mantenimiento». Escribiendo «papelera» o «fotos» llega igual.
    # Estando YA en Mantenimiento no: ahí está el de adentro, y se veían los dos seguidos en la
    # misma pantalla —mismo texto de ayuda, dos cajas— sin que se entendiera cuál usar.
    if st.session_state["sub_admin"] != "🧹 Mantenimiento":
        buscador_de_herramientas("buscar_herramienta_admin",
                                  "¿Qué querés hacer? (buscá entre las herramientas)")

    sub_admin = elegir_solapa(PAGINAS[3])

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
                "con su propio patrón. Ejemplo: `https://www.taranto.com.ar/busqueda?q={codigo}`\n\n"
                "**Más fácil:** pegá directamente el link de la ficha de un producto de esa marca "
                "y la app encuentra sola dónde va el código. Si el sitio lo escribe distinto que "
                "la lista, también sirven `{codigo_pegado}` (sin guiones ni espacios), "
                "`{codigo_minusculas}` y `{codigo_pegado_minusculas}`.\n\n"
                "**Si el sitio no tiene una dirección por código sino un buscador** (TARANTO, "
                "CRI-FA), pegá la dirección de la búsqueda con `{codigo}` en lugar del texto "
                "buscado: la app entra al resultado de ese código y lee su ficha. Con eso, la "
                "tarea de fondo trae los números originales que la lista no trae, y los pares "
                "que hoy quedan dudosos se deciden solos."
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
                _plantilla_ok = nuevo_template.strip()
                if _plantilla_ok and not any(f in _plantilla_ok
                                             for f in FORMAS_DEL_CODIGO_EN_LA_URL):
                    # Pegaron el link de la ficha de un producto en vez del patrón: se busca
                    # el código de la lista en el link y se arma solo. Ver
                    # plantilla_desde_un_ejemplo().
                    _plantilla_ok, _cod_ej, _err_ej = plantilla_desde_un_ejemplo(
                        _plantilla_ok, [r["codigo_raw"] for r in c.execute(
                            "SELECT codigo_raw FROM productos WHERE marca_id = ?",
                            (id_marca_link,)).fetchall()])
                    if _err_ej:
                        st.warning("El patrón tiene que incluir '{codigo}' donde va el código, "
                                   "o ser el link de la ficha de un producto de esta marca. "
                                   + _err_ej)
                        _plantilla_ok = None
                if _plantilla_ok is None:
                    pass
                else:
                    with db_lock:
                        c.execute("UPDATE marcas SET url_ficha_template = ? WHERE id = ?",
                                  (_plantilla_ok or None, id_marca_link))
                        conn.commit()
                    avisar("success", f"Patrón de link guardado para '{marca_link}'"
                                      + (f": `{_plantilla_ok}`" if _plantilla_ok else "") + ".")
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
                ayuda(
                    "Fusionalas abajo, poniendo como origen la que quieras eliminar. Los "
                    "productos que existan en las dos se juntan conservando precio, stock y "
                    "equivalencias."
                )
                st.markdown("---")

            st.markdown("**🔀 Fusionar marcas duplicadas**")
            ayuda(
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
            st.markdown("**📏 Coeficiente de la lista**")
            explicar(
                "Por cuánto se multiplica el precio de la lista de un proveedor, cada vez que se "
                "importa.",
                "Muchos distribuidores publican un precio de lista fijo y aparte un coeficiente "
                "que cambia cada mes. Si la lista entra sin él, todos sus precios quedan en otra "
                "escala: en la base real, una junta de tapa de TARANTO figuraba a $1.505 y la "
                "misma de ILLINOIS a $24.140. Y eso no se queda en la lista: se cotiza así por "
                "WhatsApp, esa marca sale «🏆 más barata» y «a quién conviene comprarle» la "
                "recomienda.\n\n"
                "La app lo detecta comparando cada marca con sus equivalentes de los OTROS "
                "proveedores (la mediana, con al menos 30 comparaciones contra dos o más), y "
                "sugiere el coeficiente que la pone en línea. **Lo decidís vos**: el sugerido es "
                "una estimación.\n\n"
                "Queda guardado y se aplica en cada importación de esa marca. Con la casilla, "
                "también lleva a la nueva escala lo que ya está cargado —y su historial, para "
                "que no parezca un aumento—."
            )
            _escala = escala_de_precios_por_marca()
            _marcas_coef = [m for m in marcas_info if m["tipo"] != "OEM"]
            _tabla_escala = []
            for _m in _marcas_coef:
                _d = _escala.get(_m["nombre"])
                if not _d:
                    continue
                _tabla_escala.append({
                    "Marca": _m["nombre"],
                    "Cuesta, contra sus equivalentes": f"×{miles(_d['factor'], 2)}",
                    "Comparaciones": _d["comparaciones"],
                    "Contra": ", ".join(_d["contra"][:4]),
                    "Coeficiente": f"×{miles(coeficiente_de_lista(_m['id']), 2)}",
                    "": "⚠️ fuera de escala" if _d["fuera"] else "",
                })
            if _tabla_escala:
                st.dataframe(_tabla_escala, width="stretch", hide_index=True)
            _fuera_nombres = [t["Marca"] for t in _tabla_escala if t[""]]
            _nombres_coef = [m["nombre"] for m in _marcas_coef]
            _marca_coef = st.selectbox(
                "Marca:", _nombres_coef, key="marca_coeficiente",
                index=_nombres_coef.index(_fuera_nombres[0]) if _fuera_nombres else 0)
            _id_coef = next(m["id"] for m in _marcas_coef if m["nombre"] == _marca_coef)
            _actual = coeficiente_de_lista(_id_coef)
            _d_coef = _escala.get(_marca_coef)
            _sugerido = round(_actual / _d_coef["factor"], 2) if _d_coef and _d_coef["fuera"] else None
            if _sugerido:
                st.warning(f"**{_marca_coef}** está fuera de escala: cuesta ×"
                           f"{miles(_d_coef['factor'], 2)} lo que sus equivalentes. Sugerido: "
                           f"**×{miles(_sugerido, 2)}**.")
            # Las listas en dólares: el coeficiente es el dólar oficial del día, y se actualiza
            # solo en cada importación (ver coeficiente_de_lista()).
            _dolar_hoy, _dolar_fecha, _dolar_fuente = dolar_guardado()
            _en_dolares = st.checkbox(
                "💵 Esta lista viene en dólares: usar el dólar oficial del día"
                + (f" (hoy ${miles(_dolar_hoy, 2)}, al {_dolar_fecha})" if _dolar_hoy else ""),
                value=lista_en_dolares(_id_coef), key=f"coef_dolares_{_id_coef}",
                disabled=not _dolar_hoy and not lista_en_dolares(_id_coef),
                help=("El dólar se trae solo, por atrás, del oficial minorista controlado con el "
                      "de referencia del BCRA" + (f" (último: {_dolar_fuente})." if _dolar_fuente
                                                  else ". Todavía no se pudo traer.")))
            _nuevo_coef = st.number_input(
                "Coeficiente (1 = la lista tal cual):", min_value=0.001,
                value=float(_dolar_hoy if (_en_dolares and _dolar_hoy) else (_sugerido or _actual)),
                step=0.1, format="%.3f", key=f"coef_valor_{_id_coef}_{_en_dolares}",
                disabled=bool(_en_dolares and _dolar_hoy))
            _a_lo_cargado = st.checkbox("Llevar también los precios que ya están cargados a la "
                                        "nueva escala", value=True, key="coef_a_lo_cargado")
            if candado('cambiar el coeficiente de una lista',
                       st.button("📏 Guardar el coeficiente",
                                 disabled=(abs(_nuevo_coef - _actual) < 1e-9
                                           and _en_dolares == lista_en_dolares(_id_coef))),
                       'cambiar_el_coeficiente_de_una_lista'):
                _n_coef = guardar_coeficiente_de_lista(_id_coef, _nuevo_coef, _a_lo_cargado,
                                                       en_dolares=_en_dolares)
                invalidar_salud()
                avisar("success", f"Coeficiente de {_marca_coef}: ×{miles(_nuevo_coef, 2)}. "
                                  + (f"Se llevaron {miles(_n_coef)} precio(s) a la nueva escala."
                                     if _a_lo_cargado else
                                     "Se aplica desde la próxima importación."))
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
            # Escribir el nombre, no tildar una casilla: es la operación más destructiva de la
            # app y una casilla se tilda sin leer (lo pidió una revisión con ChatGPT).
            confirmar = st.text_input(
                f"Para confirmar, escribí el nombre de la marca ({marca_a_borrar}):",
                key="confirmar_borrar_marca").strip().upper() == str(marca_a_borrar).strip().upper()
            if candado('eliminar una marca', st.button("🗑️ Eliminar marca", disabled=not confirmar), 'eliminar_una_marca'):
                eliminar_marca_con_papelera(marca_a_borrar)
                avisar("success", f"Marca '{marca_a_borrar}' eliminada (podés restaurarla desde la papelera).")
                st.rerun()

        # AUTOPARTES DE SEGURIDAD: el registro oficial de CHAS contra tus marcas. Ver
        # «AUTOPARTES DE SEGURIDAD: EL REGISTRO DE CHAS» en logica/homologaciones.py.
        _chas = resumen_del_chas()
        if seccion_plegable("🛡️ Autopartes de seguridad: ¿tus marcas tienen CHAS?"
                            + (f" ({miles(_chas['certificados'])} certificados cargados)"
                               if _chas.get("certificados") else ""),
                            key="marcas_chas"):
            explicar(
                "El registro oficial de la Secretaría de Industria: qué marcas tienen el "
                "certificado para vender frenos, luces, vidrios, cinturones o cubiertas de "
                "reposición.",
                "Una autoparte de seguridad solo se puede vender con su **CHAS** (Certificado de "
                "Homologación de Autopartes de Seguridad, Decreto 779/95 y Resolución 166/2019). "
                "La Secretaría de Industria publica cada mes los vigentes, gratis. La app lo baja "
                "sola una vez por mes; también se puede bajar ahora, o subir el CSV del portal "
                "a mano.\n\n**«No figura» no quiere decir «no tiene»**: muchas listas nombran "
                "al distribuidor y no a la marca del producto, o la escriben distinto. Es una "
                "pregunta para hacerle al proveedor.",
                en_expander=True)
            if _chas.get("certificados"):
                st.caption(f"Cargado el {_chas.get('traido', '')[:16]}: "
                           f"{miles(_chas['certificados'])} certificados de "
                           f"{miles(_chas.get('marcas', 0))} marcas. Columnas leídas: "
                           + ", ".join(f"{k} = «{v}»" for k, v in
                                       (_chas.get("columnas") or {}).items()))
            else:
                st.caption("Todavía no se cargó el registro.")
            _ch1, _ch2 = st.columns(2)
            if es_empleado_o_abierto() and _ch1.button("🌐 Bajar el registro ahora",
                                                      key="chas_bajar"):
                with st.spinner("Bajando el registro de CHAS…"):
                    try:
                        _r = actualizar_el_registro_chas(forzar=True)
                        avisar("success", f"Registro de CHAS cargado: {miles(_r['certificados'])} "
                                          "certificados.")
                        st.rerun()
                    except Exception as _err:
                        anotar_error("actualizar_el_registro_chas", _err)
                        st.warning("No se pudo bajar el registro "
                                   f"({type(_err).__name__}). Probá subiendo el CSV a mano: "
                                   "se baja de datos.produccion.gob.ar, «Registro de CHAS "
                                   "Emitidos».")
            if es_empleado_o_abierto():
                _arch_chas = _ch2.file_uploader("…o subí el CSV del portal", type=["csv"],
                                                key="chas_archivo")
                if _arch_chas is not None and st.button("📥 Cargar ese archivo",
                                                        key="chas_cargar"):
                    _r, _e = cargar_el_registro_chas_a_mano(_arch_chas.getvalue(),
                                                            _arch_chas.name)
                    if _e:
                        st.error(_e)
                    else:
                        avisar("success", f"Registro de CHAS cargado: "
                                          f"{miles(_r['certificados'])} certificados.")
                        st.rerun()
            if _chas.get("certificados"):
                _contra = marcas_del_catalogo_contra_el_chas()
                _sin = sum(f["Sin dato"] for f in _contra)
                st.markdown(f"**Tus proveedores con piezas de seguridad: {len(_contra)}** — "
                            f"{miles(_sin)} pieza(s) sin un CHAS a la vista.")
                st.caption("«Con CHAS a la vista»: la marca con que está cargada, o una marca "
                           "del registro que nombra la descripción, tiene CHAS. «Sin dato» es "
                           "para preguntarle al proveedor qué marca es y si la tiene.")
                st.dataframe(_contra, hide_index=True, width="stretch")
                _q_chas = st.text_input("Buscar en el registro (marca, empresa o autoparte):",
                                        key="chas_buscar", placeholder="Ej: FRAS-LE, pastilla")
                if _q_chas.strip():
                    _encontrados = buscar_en_el_chas(_q_chas)
                    if _encontrados:
                        st.dataframe(_encontrados, hide_index=True, width="stretch")
                    else:
                        st.caption("No figura en el registro.")

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
                    "¿Necesitás borrar un producto? Está en **🗂️ Administrar → 🧹 Mantenimiento**, "
                    "arriba de todo («🗑️ Eliminar un producto puntual»): separado a propósito "
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
                ayuda(
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
                    "La copa es cónica: se cargan sus dos diámetros, el de la base y el de la boca.",
                    "La **base** es donde se une al eje; la **boca**, el borde abierto. Con "
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
                        # Lleva directo a Vincular manual con el Código A puesto, en vez de
                        # decir «andá a la pestaña…». Como on_click, por lo mismo que
                        # ir_a_donde_dice_el_aviso(): el menú ya se dibujó en esta pasada.
                        colB.button("🔗 Usar", key=f"usar_huerfano_{fila['ID']}",
                                    on_click=usar_para_vincular,
                                    args=(fila["Codigo"], fila["Marca"],
                                          fila.get("Descripcion") or ""))
                else:
                    st.info("Sin resultados para esa marca.")

    if sub_admin == SUB_ADMIN[2]:
        st.markdown("**💬 Texto del mensaje de WhatsApp**")
        ayuda(
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
        ayuda(
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

    if sub_admin == SUB_ADMIN[5]:
        # seccion_permitida() y no pedir_password_admin(): sin ninguna contraseña todavía,
        # acá es donde se crea la primera, y pedir una que no existe era un callejón sin
        # salida (el aviso de «la app no tiene contraseña» manda justo acá).
        if not seccion_permitida("admin", "gestionar usuarios"):
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
            ayuda(
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
                # Si debe plata, no: la cuenta corriente se lista por los mecánicos que existen,
                # y borrándolo su deuda desaparecería de la pantalla.
                _saldo_mecanico = estado_de_cuenta(mecanico_id_sel)["saldo"]
                if _saldo_mecanico:
                    cmg2.caption(f"Tiene saldo en su cuenta corriente (${miles(_saldo_mecanico, 0)}): "
                                 "no se puede eliminar. Desactivalo.")
                elif cmg2.button("🗑️ Eliminar mecánico"):
                    eliminar_mecanico(mecanico_id_sel)
                    avisar("success", "Mecánico eliminado.")
                    st.rerun()

    # La cuenta corriente de cada taller: ver «CUENTA CORRIENTE DE LOS TALLERES» en
    # logica/mecanico.py. Los talleres son los mecánicos de «👥 Usuarios».
    if sub_admin == SUB_ADMIN[6]:
        st.markdown("**💳 Cuentas corrientes de los talleres**")
        explicar(
            "Lo que cada taller se lleva fiado y lo que va pagando, con plazo, límite y cheques.",
            "Para cargarle algo a la cuenta hace falta el **código de retiro** que el taller genera "
            "en su portal (6 cifras, un solo uso, 24 horas): así nadie retira a su nombre "
            "diciendo «vengo de parte de». Se puede apagar por taller, en su configuración.\n\n"
            "Los talleres son los mecánicos de **👥 Usuarios**: el que no tiene usuario no tiene "
            "portal ni código."
        )
        _talleres = {m["Nombre"]: m["ID"] for m in listar_mecanicos()}
        if not _talleres:
            st.info("Todavía no hay ningún taller. Se crean en 👥 Usuarios → Mecánicos externos.")
        else:
            _resumen_cc = resumen_de_cuentas()
            if _resumen_cc:
                _cc1, _cc2, _cc3 = st.columns(3)
                _cc1.metric("A cobrar", f"${miles(sum(max(0, r['Saldo']) for r in _resumen_cc), 0)}")
                _cc2.metric("Vencido", f"${miles(sum(r['Vencido'] for r in _resumen_cc), 0)}")
                _cc3.metric("Cheques en cartera",
                            f"${miles(sum(r['Cheques en cartera'] or 0 for r in _resumen_cc), 0)}")
                st.dataframe(quitar_id(_resumen_cc), width="stretch", hide_index=True)

            _taller = st.selectbox("Taller:", list(_talleres), key="cc_taller")
            _mid = _talleres[_taller]
            _estado = estado_de_cuenta(_mid)
            _config = configuracion_de_cuenta(_mid)
            _e1, _e2, _e3 = st.columns(3)
            _e1.metric("Saldo", f"${miles(_estado['saldo'], 0)}")
            _e2.metric("Vencido", f"${miles(_estado['vencido'], 0)}")
            _e3.metric("Disponible", "sin límite" if _estado["disponible"] is None
                       else f"${miles(_estado['disponible'], 0)}")
            if _estado["cheques_cuantos"]:
                st.caption(f"🧾 {_estado['cheques_cuantos']} cheque(s) en cartera por "
                           f"${miles(_estado['cheques_en_cartera'], 0)}, todavía sin cobrar.")

            with st.form(f"cc_cargo_{_mid}", clear_on_submit=True):
                st.markdown("**➕ Cargar a la cuenta**")
                _concepto = st.text_input("Qué se llevó:", placeholder="Ej: junta tapa 271205 x1")
                _importe = st.number_input("Importe ($):", min_value=0.0, step=100.0)
                if _config["descuento"]:
                    st.caption(f"Esta cuenta tiene {miles(_config['descuento'], 1)}% de "
                               "descuento. Lo que se pide al depósito se carga ya descontado; "
                               "acá se carga el importe tal cual lo escribas.")
                _codigo = (st.text_input("Código de retiro (6 cifras):", max_chars=6)
                           if _config["pide_codigo"] else "")
                _pasar = (st.checkbox("Cargar igual aunque pase el límite")
                          if _config["limite"] else False)
                if st.form_submit_button("➕ Cargar", type="primary"):
                    _ok, _aviso = cargar_a_la_cuenta(_mid, _concepto, _importe, _codigo,
                                                     usuario=obtener_usuario_actual(),
                                                     pasar_el_limite=_pasar)
                    if _ok:
                        avisar("success", _aviso)
                        st.rerun()
                    else:
                        st.error(_aviso)

            with st.form(f"cc_pago_{_mid}", clear_on_submit=True):
                st.markdown("**💵 Registrar un pago**")
                _importe_p = st.number_input("Importe ($):", min_value=0.0, step=100.0,
                                             key=f"cc_importe_pago_{_mid}")
                _medio = st.selectbox("Cómo pagó:", MEDIOS_DE_PAGO)
                _fecha_cheque = st.date_input("Fecha del cheque (si es cheque):",
                                              value=date.today(), key=f"cc_fecha_cheque_{_mid}")
                _concepto_p = st.text_input("Nota (opcional):", key=f"cc_nota_pago_{_mid}")
                if st.form_submit_button("💵 Registrar pago"):
                    _ok, _aviso = registrar_pago_de_cuenta(_mid, _importe_p, _medio, _concepto_p,
                                                           _fecha_cheque,
                                                           usuario=obtener_usuario_actual())
                    if _ok:
                        avisar("success", _aviso)
                        st.rerun()
                    else:
                        st.error(_aviso)

            # VERIFICAR UN CHEQUE antes de recibirlo: ver consultar_cheque(). Afuera del
            # formulario del pago porque un formulario no admite otro botón.
            with st.container(border=True):
                st.markdown("**🔎 Verificar un cheque en el BCRA**")
                st.caption("Antes de recibirlo: si está denunciado como robado, extraviado o "
                           "adulterado. No dice si tiene fondos. Consulta oficial y gratuita.")
                _bancos = bancos_del_bcra()
                _vc1, _vc2 = st.columns([3, 2])
                if _bancos:
                    _nombres_b = {f"{n} ({cod})": cod for cod, n in _bancos}
                    _banco_sel = _vc1.selectbox("Banco del cheque:", list(_nombres_b),
                                                key=f"cc_banco_cheque_{_mid}", index=None,
                                                placeholder="Elegí el banco…")
                    _cod_banco = _nombres_b.get(_banco_sel)
                else:
                    _cod_banco = _vc1.number_input(
                        "Código del banco (las 3 primeras cifras de abajo del cheque):",
                        min_value=0, step=1, key=f"cc_cod_banco_{_mid}")
                _nro_cheque = _vc2.text_input("Número del cheque:", key=f"cc_nro_cheque_{_mid}")
                if st.button("🔎 Verificar", key=f"cc_verificar_cheque_{_mid}",
                             disabled=not (_cod_banco and _nro_cheque.strip())):
                    with st.spinner("Consultando al BCRA…"):
                        _ch, _err_ch = consultar_cheque(_cod_banco, _nro_cheque)
                    if _err_ch:
                        st.warning(_err_ch)
                    elif _ch["denunciado"]:
                        st.error(
                            f"🚫 **El cheque {_nro_cheque} está DENUNCIADO** en el BCRA"
                            + (f" ({_ch['banco']}, {_ch['fecha']})" if _ch["banco"] else "")
                            + ". " + "; ".join(str(_causal) for _suc, _cta, _causal in _ch["detalles"] if _causal)
                            + ". No lo recibas.")
                    else:
                        st.success(f"✅ El cheque {_nro_cheque} no figura como denunciado en el "
                                   "BCRA. (No dice si tiene fondos.)")

            _movs = movimientos_de_cuenta(_mid)
            if _movs:
                st.markdown("**📒 Movimientos**")
                st.dataframe(quitar_id(_movs), width="stretch", hide_index=True)
                _mensaje_cc = (f"Hola! Te escribimos de El Chavo. El saldo de tu cuenta corriente "
                               f"es ${miles(_estado['saldo'], 0)}"
                               + (f", de los que ${miles(_estado['vencido'], 0)} ya vencieron"
                                  if _estado["vencido"] else "") + ". ¡Gracias!")
                st.link_button("📲 Mandarle el saldo por WhatsApp",
                               "https://wa.me/?text=" + quote(_mensaje_cc))
                _anulables = {f"{m['Fecha']} — {m['Concepto']} — "
                              f"${miles((m['Debe'] or m['Haber'] or 0), 0)}": m["ID"]
                              for m in _movs if "(ANULADO)" not in m["Concepto"]}
                if _anulables:
                    _a_anular = st.selectbox("Anular un movimiento (queda a la vista, tachado):",
                                             list(_anulables), key=f"cc_anular_sel_{_mid}")
                    if candado("anular un movimiento de cuenta corriente",
                               st.button("🚫 Anular ese movimiento", key=f"cc_anular_{_mid}"),
                               f"cc_anular_{_mid}"):
                        anular_movimiento_de_cuenta(_anulables[_a_anular])
                        avisar("success", "Movimiento anulado.")
                        st.rerun()

            # INTERÉS POR MORA con la tasa del BCRA: ver «INTERÉS POR MORA» en
            # logica/mecanico.py. Plegado con un interruptor y no con un expander: el expander
            # corre su contenido aunque esté cerrado, y esto puede salir a internet.
            if not _config["cobra_mora"]:
                st.caption("📈 Sin recargo por mora: se prende en «⚙️ Configuración de la "
                           "cuenta», si a este taller se le cobra.")
            elif seccion_plegable("📈 Interés por mora (tasa del BCRA)", key=f"cc_mora_{_mid}"):
                _cfg_mora = configuracion_de_la_mora()
                _tasas = tasas_de_referencia()
                if not _tasas:
                    st.warning("Todavía no se pudo traer ninguna tasa del BCRA.")
                    if st.button("🔄 Traer las tasas del BCRA", key=f"cc_tasas_{_mid}"):
                        with st.spinner("Consultando al BCRA…"):
                            tasas_de_referencia(forzar=True)
                        st.rerun()
                else:
                    _claves_t = [k for k, _n, _p in TASAS_DE_REFERENCIA if k in _tasas]
                    _m1, _m2 = st.columns([3, 1])
                    _ref = _m1.selectbox(
                        "Tasa de referencia:", _claves_t,
                        index=(_claves_t.index(_cfg_mora["referencia"])
                               if _cfg_mora["referencia"] in _claves_t else 0),
                        format_func=lambda k: (f"{_tasas[k]['nombre']} — "
                                               f"{miles(_tasas[k]['tna'], 2)}% TNA"
                                               + (f" (al {_tasas[k]['fecha']})"
                                                  if _tasas[k].get("fecha") else "")),
                        key=f"cc_mora_ref_{_mid}")
                    _puntos = _m2.number_input("+ puntos:", min_value=0.0, max_value=200.0,
                                               step=1.0, value=_cfg_mora["puntos"],
                                               key=f"cc_mora_puntos_{_mid}",
                                               help="Lo que se suma a la tasa del BCRA.")
                    if (_ref, _puntos) != (_cfg_mora["referencia"], _cfg_mora["puntos"]):
                        if candado("cambiar la tasa del interés por mora",
                                   st.button("💾 Usar esta tasa para todas las cuentas",
                                             key=f"cc_mora_guardar_{_mid}"),
                                   f"cc_mora_guardar_{_mid}"):
                            guardar_configuracion_de_la_mora(_ref, _puntos)
                            avisar("success", "Tasa del interés por mora guardada.")
                            st.rerun()
                    _tna, _origen = tasa_de_mora()
                    _calc = interes_por_mora(_mid, _tna)
                    st.caption(f"Con {_origen}: **{miles(_tna, 2)}% anual**, interés simple "
                               "por días sobre lo vencido e impago de cada cargo (los pagos van "
                               "a lo más viejo)."
                               + (f" Ya se cobró hasta el {_calc['desde']:%d/%m/%Y}."
                                  if _calc["desde"] else ""))
                    if not _calc["renglones"]:
                        st.success("No hay saldo vencido sin cobrar: no corresponde interés.")
                    else:
                        st.dataframe(_calc["renglones"], hide_index=True, width="stretch")
                        st.markdown(f"**Interés a hoy: ${miles(_calc['total'], 0)}**")
                        if candado("cargar el interés por mora",
                                   st.button("➕ Cargar el interés a la cuenta",
                                             key=f"cc_mora_cargar_{_mid}"),
                                   f"cc_mora_cargar_{_mid}"):
                            # En el movimiento, la tasa en corto: el valor ya va en la TNA.
                            _ok, _aviso = cargar_el_interes_por_mora(
                                _mid, _tna, f"{_origen.split(' (')[0]}, BCRA",
                                usuario=obtener_usuario_actual())
                            avisar("success" if _ok else "warning", _aviso)
                            st.rerun()

            with st.expander(f"⚙️ Configuración de la cuenta de {_taller}"):
                _limite = st.number_input("Límite de crédito ($, 0 = sin límite):", min_value=0.0,
                                          step=1000.0, value=float(_config["limite"]),
                                          key=f"cc_limite_{_mid}")
                _plazo = st.number_input("Días de plazo para pagar:", min_value=0, step=1,
                                         value=int(_config["dias_de_plazo"]),
                                         key=f"cc_plazo_{_mid}")
                _pide = st.checkbox("Pedir el código de retiro para cargarle algo",
                                    value=_config["pide_codigo"], key=f"cc_pide_{_mid}")
                # El descuento de la cuenta: ver «EL DESCUENTO NO SE VE» en logica/deposito.py.
                _descuento = st.number_input(
                    "Descuento sobre la lista (%):", min_value=0.0, max_value=DESCUENTO_MAXIMO,
                    step=1.0, value=float(_config["descuento"]), key=f"cc_descuento_{_mid}",
                    help="Lo que se pide al depósito para esta cuenta se carga con este "
                         "descuento. No se ve en el buscador, ni en WhatsApp, ni en las "
                         "cotizaciones, ni en el depósito: solo en la cuenta y en «🧾 Para "
                         "facturar».")
                _cobra_mora = st.checkbox(
                    "Cobrarle recargo por pagar tarde (interés por mora)",
                    value=_config["cobra_mora"], key=f"cc_cobra_mora_{_mid}",
                    help="Prendido, aparece «📈 Interés por mora» con lo que corresponde "
                         "sobre lo vencido. Apagado, a esta cuenta no se le calcula ni se le "
                         "carga nada.")
                if _descuento:
                    st.caption(f"Ejemplo: un repuesto de lista {formato_precio(10000)} se le "
                               f"carga a {formato_precio(precio_de_la_cuenta(10000, _descuento))}.")
                if candado("cambiar la configuración de una cuenta corriente",
                           st.button("💾 Guardar configuración", key=f"cc_guardar_{_mid}"),
                           f"cc_guardar_{_mid}"):
                    configurar_cuenta_de_taller(_mid, _limite, _plazo, _pide, _descuento,
                                                _cobra_mora)
                    avisar("success", "Configuración guardada.")
                    st.rerun()

                # CÓMO ESTÁ EN EL SISTEMA FINANCIERO: ver situacion_en_el_bcra(). Sirve para
                # decidir el límite: un taller en situación 3 o peor con algún banco no es
                # alguien a quien fiarle mucho.
                st.markdown("**🏦 Su situación en el BCRA (Central de Deudores)**")
                _cuit_guardado = obtener_config(f"cuit_taller_{_mid}", "")
                _cuit = st.text_input("CUIT o CUIL del taller:", value=_cuit_guardado,
                                      key=f"cc_cuit_{_mid}", placeholder="20-12345678-9")
                if _cuit.strip() and not cuit_valido(_cuit):
                    st.caption("⚠️ Ese CUIT no es válido: el último dígito no da.")
                if st.button("🏦 Consultar", key=f"cc_consultar_bcra_{_mid}",
                             disabled=not cuit_valido(_cuit)):
                    if cuit_valido(_cuit) != cuit_valido(_cuit_guardado):
                        guardar_config(f"cuit_taller_{_mid}", cuit_valido(_cuit))
                    with st.spinner("Consultando al BCRA…"):
                        _sit, _err_sit = situacion_en_el_bcra(_cuit)
                        _hist, _err_hist = historia_en_el_bcra(_cuit)
                        _rech, _err_rech = cheques_rechazados_en_el_bcra(_cuit)
                    if _err_sit:
                        st.warning(_err_sit)
                    elif not _sit["deudas"]:
                        st.success("✅ No tiene deudas informadas en el sistema financiero.")
                    else:
                        _peor = _sit["peor"]
                        _graves = sorted({o for *_x, o in _sit["deudas"] if o})
                        (st.success if _peor <= 1 and not _graves else
                         st.warning if _peor <= 2 else st.error)(
                            f"{_sit['nombre'] or 'Ese CUIT'} — peor situación: **{_peor} "
                            f"({SITUACIONES_DEL_BCRA.get(_peor, '?')})**, al período "
                            f"{_sit['periodo']}."
                            + (f" Ojo: **{', '.join(_graves)}**." if _graves else ""))
                        st.dataframe([{"Entidad": e, "Situación": s_,
                                       "Deuda (miles de $)": miles(m, 1),
                                       "Días de atraso": d, "Observaciones": o or "—"}
                                      for e, s_, m, d, o in _sit["deudas"]],
                                     width="stretch", hide_index=True)
                    # Cómo viene: ver historia_en_el_bcra().
                    if _hist and _hist["meses"]:
                        _malos = [(m_, p_) for m_, p_, _t in _hist["meses"] if p_ >= 2]
                        st.caption(
                            f"📅 Últimos {len(_hist['meses'])} meses: "
                            + (f"en situación 2 o peor en {len(_malos)} (la última vez en "
                               f"{_malos[-1][0]}, situación {_malos[-1][1]})"
                               if _malos else "siempre en situación 1 (normal)")
                            + {"empeoró": ". **Viene empeorando.**",
                               "mejoró": ". Viene mejorando.", "igual": ".", "": "."}[
                                _hist["tendencia"]])
                    # Los cheques que libró y le rechazaron: ver cheques_rechazados_en_el_bcra().
                    if _err_rech and not _err_sit:
                        st.caption(f"Cheques rechazados: {_err_rech}")
                    elif _rech is not None and not _rech["cheques"]:
                        st.caption("🧾 No tiene cheques rechazados informados.")
                    elif _rech:
                        (st.error if _rech["sin_pagar"] else st.info)(
                            f"🧾 {len(_rech['cheques'])} cheque(s) rechazado(s)"
                            + (f", **{_rech['sin_pagar']} sin pagar** por "
                               f"{formato_precio(_rech['monto_sin_pagar'])}"
                               if _rech["sin_pagar"] else ", todos pagados") + ".")
                        st.dataframe([{"Rechazado el": f_, "Por": c_, "Cheque N°": n_,
                                       "Monto": formato_precio(m_),
                                       "Pagado": "✅" if p_ else "❌ no"}
                                      for f_, c_, n_, m_, p_ in _rech["cheques"]],
                                     width="stretch", hide_index=True)

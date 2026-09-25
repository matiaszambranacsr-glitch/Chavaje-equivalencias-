"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/."""

# ============================================================
# MODO MECÁNICO
# ============================================================
if pagina == PAGINAS[7]:
    st.subheader("🛠️ Modo Mecánico")

    # Ordenadas por cómo se usan: primero identificar el auto (patente, chasis, motor), después
    # consultarlo. Antes «Códigos DTC» quedaba segundo, entre dos formas de identificar el auto.
    SUB_MEC = ["🔤 Por patente", "🔢 Chasis / VIN", "⚙️ Número de motor", "🚙 Repuestos por vehículo", "📖 Códigos DTC",
               "🗺️ Esquemas", "🧮 Conversor de unidades"]
    if st.session_state.get("sub_mec") not in SUB_MEC:
        st.session_state["sub_mec"] = SUB_MEC[0]
    st.radio("Sub-sección:", SUB_MEC, key="sub_mec", horizontal=True,
             label_visibility="collapsed")
    sub_mec = st.session_state["sub_mec"]

    # -------- Diccionario de códigos OBD2 / DTC --------
    if sub_mec == SUB_MEC[4]:
        st.caption(
            f"Diccionario de códigos de falla OBD2/DTC. Arranca con {contar_dtc()} códigos genéricos "
            "estándar (no específicos de marca) — sumá los que te falten con el formulario de abajo. "
            "Los códigos P1xxx u otros específicos de fabricante se cargan indicando la marca, porque "
            "el mismo número puede significar algo distinto según el auto."
        )
        fabricantes_dtc = ["Todos", "Genérico"] + listar_fabricantes_dtc()
        cdb1, cdb2 = st.columns([2, 1])
        codigo_buscar = cdb1.text_input("Buscar código:", placeholder="Ej: P0301 o P1105", key="dtc_buscar")
        filtro_fab_dtc = cdb2.selectbox("Fabricante:", fabricantes_dtc, key="dtc_filtro_fab")
        if codigo_buscar.strip():
            res_dtc = buscar_dtc(codigo_buscar, filtro_fab_dtc)
            if res_dtc:
                st.dataframe(res_dtc, width="stretch", hide_index=True)
                # DEL CÓDIGO AL REPUESTO. El diccionario decía qué significa la falla y ahí
                # terminaba: el que atiende leía «bujía, bobina, inyector» y salía a buscar
                # cada una a mano. Esto cruza las palabras del propio código con las
                # descripciones del catálogo que ya está cargado — sin ninguna base nueva.
                cdt1, cdt2 = cols(2)
                _auto_dtc = cdt1.text_input("¿De qué auto? (opcional)", key="dtc_marca_auto",
                                             placeholder="Ej: FIAT").strip()
                _modelo_dtc = cdt2.text_input("Modelo (opcional)", key="dtc_modelo_auto",
                                               placeholder="Ej: PALIO").strip()
                _reps_dtc = repuestos_para_el_dtc(codigo_buscar, _auto_dtc, _modelo_dtc)
                if _reps_dtc:
                    st.markdown("**🔧 Lo que tenés para arreglar eso**")
                    st.caption(
                        "Sale de cruzar las piezas que nombra el código con las descripciones "
                        "de tu catálogo. Es una ayuda para no ir a buscar cada una a mano, no "
                        "un diagnóstico: el código dice por dónde empezar, no qué cambiar."
                    )
                    for _grupo in _reps_dtc:
                        with st.expander(f"{_grupo['pieza']} — {len(_grupo['productos'])} "
                                          f"en tu catálogo"):
                            st.dataframe(_grupo["productos"], width="stretch", hide_index=True)
                elif _auto_dtc or _modelo_dtc:
                    st.caption("No encontré en tu catálogo ninguna de las piezas que nombra "
                               "ese código para ese auto. Probá sin el modelo.")
            else:
                st.warning("No tengo ese código cargado todavía (con ese filtro de fabricante). Podés agregarlo abajo.")

        with st.expander("➕ Agregar / corregir un código"):
            st.caption("Dejá 'Fabricante' vacío si es un código genérico (P0xxx). Completalo si es específico de una marca (ej: Ford, Toyota).")
            with st.form("form_dtc", clear_on_submit=True):
                cd1, cd2, cd3 = st.columns(3)
                nuevo_codigo = cd1.text_input("Código (ej: P0301)")
                nuevo_fabricante = cd2.text_input("Fabricante (opcional)", placeholder="Ej: Ford")
                nuevo_sistema = cd3.text_input("Sistema (ej: Motor, Transmisión)")
                nueva_desc = st.text_input("Descripción")
                nuevas_causas = st.text_input("Causas posibles (opcional)")
                guardar_dtc_btn = st.form_submit_button("💾 Guardar código", type="primary")
            if guardar_dtc_btn:
                if not nuevo_codigo.strip() or not nueva_desc.strip():
                    st.warning("Completá al menos el código y la descripción.")
                else:
                    agregar_dtc(nuevo_codigo, nueva_desc, nuevo_sistema, nuevas_causas, nuevo_fabricante)
                    etiqueta_fab = f" ({nuevo_fabricante.strip()})" if nuevo_fabricante.strip() else " (genérico)"
                    avisar("success", f"Código {nuevo_codigo.upper()}{etiqueta_fab} guardado.")
                    st.rerun()

        with st.expander("📋 Carga masiva de códigos (pegar texto)"):
            st.caption(
                "Un código por línea, formato: `codigo;descripción;sistema;causas;fabricante` "
                "(sistema, causas y fabricante son opcionales — dejá fabricante vacío para códigos genéricos)."
            )
            texto_dtc = st.text_area("Pegá los códigos acá:", height=150, key="dtc_masivo",
                                      placeholder="P0455;Fuga grande en sistema EVAP;Emisiones;Tapa de nafta, manguera\n"
                                                   "P1105;Solenoide de presión de combustible;Motor;;Chrysler")
            if candado('importar códigos de falla', st.button("📥 Importar códigos"), 'importar_c_digos_de_falla'):
                cargados_dtc = importar_dtc_masivo(texto_dtc)
                avisar("success", f"Se cargaron/actualizaron {cargados_dtc} código(s).")
                st.rerun()

    # Definidas acá porque las usan las dos vistas de esquemas de más abajo.
    CATEGORIAS_ESQUEMA = [
        "Motor", "Refrigeración", "Retenes y juntas", "Frenos", "Suspensión", "Dirección",
        "Transmisión", "Embrague", "Correas y distribución", "Eléctrico", "Combustible",
        "Escape", "Aire acondicionado", "Otro"
    ]

    def mostrar_lista_esquemas(lista_esq):
        if not lista_esq:
            st.caption("No hay esquemas cargados acá todavía.")
            return
        for esq in lista_esq:
            titulo_expander = f"🗺️ {esq['titulo']}" + (" 🤖 (orientativo, generado por IA)" if esq.get("generado_ia") else "")
            with st.expander(titulo_expander):
                if esq.get("generado_ia"):
                    st.warning(
                        "🤖 Esta imagen fue generada por IA como referencia orientativa — "
                        "NO es una foto real de este vehículo. No la uses para identificar piezas con precisión."
                    )
                if esq.get("descripcion"):
                    st.write(esq["descripcion"])
                img_bytes = obtener_imagen_esquema(esq["id"])
                puntos = listar_puntos_esquema(esq["id"])
                if img_bytes:
                    imagen_a_mostrar = imagen_esquema_lista_para_mostrar(
                        img_bytes, firma_de_puntos(puntos), puntos
                    )
                    st.image(imagen_a_mostrar, width="stretch")
                    if any(p.get("pos_x") is not None for p in puntos):
                        st.caption("Los números marcados en la foto corresponden a la lista de piezas de abajo.")

                # Piezas marcadas en el esquema, con búsqueda directa por código
                if puntos:
                    st.markdown("**🔩 Piezas de este esquema**")
                    for punto in puntos:
                        etiqueta = f"{punto['numero']}. " if punto.get("numero") else ""
                        cp1, cp2 = st.columns([3, 1])
                        cp1.write(f"{etiqueta}{punto['nombre_pieza']}" + (f" — `{punto['codigo']}`" if punto.get("codigo") else ""))
                        if punto.get("codigo"):
                            if cp2.button("🔍 Buscar", key=f"buscar_punto_{punto['id']}"):
                                clean_punto = sanitizar(punto["codigo"])
                                res_punto = buscar_por_codigo(clean_punto) if clean_punto else []
                                if not res_punto:
                                    res_punto = buscar_por_texto(punto["nombre_pieza"])
                                if res_punto:
                                    st.dataframe(quitar_id(res_punto), width="stretch", hide_index=True)
                                else:
                                    st.error(f"No encontré '{punto['codigo']}' ni '{punto['nombre_pieza']}' en la base.")
                        if es_admin():
                            cp2.button("🗑️", key=f"del_punto_{punto['id']}",
                                        on_click=eliminar_punto_esquema, args=(punto["id"],))

                if es_operador_o_admin():
                    if seccion_plegable("➕ Agregar pieza a este esquema",
                                         key=f"agregar_pieza_{esq['id']}"):
                        if img_bytes:
                            st.caption(
                                "Mirá la foto de arriba y estimá en qué parte está la pieza: "
                                "0% = borde izquierdo/superior, 100% = borde derecho/inferior."
                            )
                        cpp1, cpp2, cpp3 = st.columns([1, 2, 2])
                        num_punto = cpp1.text_input("N°", key=f"num_punto_{esq['id']}", placeholder="1")
                        nombre_punto = cpp2.text_input("Nombre de la pieza", key=f"nombre_punto_{esq['id']}")
                        codigo_punto = cpp3.text_input("Código (opcional)", key=f"codigo_punto_{esq['id']}")
                        marcar_posicion = st.checkbox(
                            "Marcar posición en la foto", value=bool(img_bytes), key=f"marcar_pos_{esq['id']}",
                            disabled=not img_bytes
                        )
                        pos_x_punto, pos_y_punto = None, None
                        if marcar_posicion and img_bytes:
                            cpx, cpy = st.columns(2)
                            pos_x_punto = cpx.slider("Posición horizontal (%)", 0, 100, 50, key=f"posx_{esq['id']}")
                            pos_y_punto = cpy.slider("Posición vertical (%)", 0, 100, 50, key=f"posy_{esq['id']}")
                            vista_previa = generar_imagen_con_marcadores(
                                img_bytes,
                                puntos + [{"numero": num_punto or "?", "pos_x": pos_x_punto, "pos_y": pos_y_punto}]
                            )
                            st.image(vista_previa, width="stretch", caption="Vista previa de dónde quedaría el marcador")
                        if st.button("💾 Agregar pieza", key=f"agregar_punto_{esq['id']}"):
                            if not nombre_punto.strip():
                                st.warning("Completá el nombre de la pieza.")
                            else:
                                vinculado = agregar_punto_esquema(
                                    esq["id"], num_punto, nombre_punto, codigo_punto, pos_x_punto, pos_y_punto
                                )
                                if codigo_punto.strip() and not vinculado:
                                    st.info(
                                        "Pieza agregada. El código no coincide con ningún producto cargado "
                                        "todavía, pero igual queda guardado como referencia."
                                    )
                                else:
                                    st.success("Pieza agregada.")
                                st.rerun()

                    if st.button("🗑️ Eliminar este esquema", key=f"del_esq_{esq['id']}"):
                        eliminar_esquema(esq["id"])
                        st.rerun()

    # -------- Por patente (lo primero, porque es lo que más se usa) --------
    if sub_mec == SUB_MEC[0]:
        st.subheader("🔤 Todo lo de un auto, por la patente")
        explicar(
            "El cliente dice la patente y sale todo: qué auto es y qué le entra.",
            "Junta en una pantalla lo que antes había que ir a buscar a tres: la ficha del "
            "auto, lo que ya se le puso, lo que le entra según marca y modelo, y lo que "
            "preguntó ese cliente antes.\n\n**Funciona con los autos que están en tus "
            "fichas.** En Argentina no hay ninguna base pública gratuita que traduzca patente "
            "a vehículo: las que existen cobran por consulta. Así que la patente sola, de un "
            "auto que nunca cargaste, no alcanza."
        )
        _pat = st.text_input("Patente:", key="buscar_por_patente",
                             placeholder="AA123BB o ABC123").strip()
        if _pat:
            _todo = todo_lo_de_una_patente(_pat)
            _v = _todo["vehiculo"]
            # Lo que la patente dice SOLA, esté o no cargado el auto. No hay base pública que
            # traduzca patente a vehículo, pero el formato y la serie se leen sin consultar
            # nada: de qué provincia salió y entre qué años se patentó. Con el auto cargado es
            # un dato de más; sin el auto cargado es lo único que hay, y no es poco — en el
            # mostrador la pregunta que sigue al modelo es siempre «¿de qué año?».
            _lec = leer_patente(_pat)
            if _lec["formato"]:
                _d_pat, _h_pat, _origen_pat = anio_probable_de_patente(_pat)
                _txt = [f"🪪 {_lec['detalle']}"]
                if _lec["provincia"]:
                    _txt.append(f"Salió de **{_lec['provincia']}**.")
                if _d_pat and _h_pat:
                    _txt.append(f"Patentado entre **{_d_pat} y {_h_pat}** — {_origen_pat}.")
                elif _h_pat:
                    _txt.append(f"Patentado **hasta {_h_pat}** — {_origen_pat}.")
                st.info(" ".join(_txt))
            if not _v:
                st.warning(f"No hay ningún auto cargado con la patente **{_todo['patente']}**.")
                st.caption(
                    "Se carga una vez y queda para siempre: la próxima vez que venga ese "
                    "cliente, con la patente sale todo."
                )
                # LA FORMA GRATIS DE QUE LA PATENTE SIRVA. No hay ninguna base pública que
                # traduzca dominio a vehículo —las que hay cobran por consulta— pero el dato
                # completo está impreso en el papel que el cliente lleva en la guantera. Una
                # foto, una vez, y la ficha queda cargada con marca, modelo, año, motor y
                # chasis: de ahí en más la patente sola alcanza.
                st.markdown("**📷 Cargalo con una foto de la cédula**")
                explicar(
                    "Sacale una foto a la cédula verde (o al título) y la app carga la ficha.",
                    "Es lo que reemplaza a la consulta de dominio, que no existe gratis. Y de "
                    "paso trae dos datos que ninguna consulta te da: el número de motor y el "
                    "de chasis, que son los que después dejan buscar por VIN cuando el auto "
                    "tiene el motor cambiado.\n\nNada se guarda solo: los datos salen a un "
                    "formulario para que los revises antes de aceptar."
                )
                _foto_ced = subir_archivo("Foto de la cédula:", ["png", "jpg", "jpeg"],
                                           f"cedula_{_todo['patente']}")
                if st.button("🔎 Leer la cédula", disabled=not archivo_listo(_foto_ced, "foto")):
                    with st.spinner("Leyendo la cédula..."):
                        _datos_ced, _err_ced = leer_cedula_por_foto(_foto_ced.getvalue())
                    if _err_ced:
                        st.error(_err_ced)
                    else:
                        st.session_state["cedula_leida"] = _datos_ced
                _ced = st.session_state.get("cedula_leida")
                if _ced:
                    st.success("Esto leí. Corregí lo que haga falta y guardalo:")
                    with st.form("form_cedula"):
                        _cc1, _cc2, _cc3 = cols(3)
                        _f_dom = _cc1.text_input("Patente", value=_ced.get("dominio") or _pat)
                        _f_mar = _cc2.text_input("Marca", value=_ced.get("marca") or "")
                        _f_mod = _cc3.text_input("Modelo", value=_ced.get("modelo") or "")
                        _cc4, _cc5, _cc6 = cols(3)
                        _f_anio = _cc4.text_input("Año", value=_ced.get("anio") or "")
                        _f_mot = _cc5.text_input("N° de motor", value=_ced.get("motor") or "")
                        _f_vin = _cc6.text_input("N° de chasis (VIN)",
                                                  value=_ced.get("chasis") or "")
                        _f_cli = st.text_input("Titular / cliente", value=_ced.get("titular") or "")
                        if st.form_submit_button("💾 Guardar la ficha", type="primary"):
                            get_or_create_vehiculo(
                                _f_dom, cliente_nombre=_f_cli, marca_auto=_f_mar,
                                modelo_auto=_f_mod, anio=_f_anio, vin=_f_vin)
                            # El número de motor va aparte, igual que en la ficha de arriba:
                            # get_or_create_vehiculo() ya tiene ocho parámetros.
                            if _f_mot.strip():
                                with db_lock:
                                    c.execute("""UPDATE vehiculos SET numero_motor = ?
                                                 WHERE UPPER(patente) = UPPER(?)""",
                                              (_f_mot.strip(), _f_dom.strip()))
                                    conn.commit()
                            st.session_state.pop("cedula_leida", None)
                            avisar("success", f"Ficha de **{_f_dom}** guardada. Ahora la patente "
                                              "sola te trae todo.")
                            st.rerun()
            else:
                st.success(
                    f"🚗 **{_v.get('marca_auto') or ''} {_v.get('modelo_auto') or ''}** "
                    f"{_v.get('anio') or ''}"
                    + (f" · {_v['motorizacion']}" if _v.get("motorizacion") else "")
                    + (f" · motor N° {_v['numero_motor']}" if _v.get("numero_motor") else "")
                    + (f"\n\nCliente: **{_v['cliente_nombre']}**" if _v.get("cliente_nombre") else "")
                    + (f" · {_v['cliente_telefono']}" if _v.get("cliente_telefono") else "")
                )
                if _v.get("km_actual"):
                    st.caption(f"Último kilometraje registrado: {_v['km_actual']:,} km")

                if _todo["historial"]:
                    st.markdown("**🔧 Lo que YA se le puso a este auto**")
                    st.caption(
                        "Es lo más confiable que hay: no es un catálogo diciendo qué debería "
                        "entrar, es lo que alguien efectivamente le instaló."
                    )
                    st.dataframe(_todo["historial"], width="stretch", hide_index=True)

                # LO QUE LE ENTRA, y de dónde salió cada cosa. repuestos_de_este_auto()
                # devuelve las cuatro fuentes SEPARADAS a propósito —una es un hecho y otra una
                # coincidencia de texto— y acá se estaba dibujando el diccionario entero de una:
                # la pantalla decía «7 repuesto(s)» (las 7 claves del diccionario) y la tabla
                # mostraba los nombres de las listas en vez de los repuestos. Los 200 productos
                # que le entran a un Palio 2001 estaban ahí y no se veían.
                _sug = _todo["sugeridos"] if isinstance(_todo["sugeridos"], dict) else {}
                _fuentes = [
                    ("de_este_auto", "🔧 Ya se le puso a ESTE auto",
                     "Certeza total: alguien se lo instaló."),
                    ("de_otros_iguales", "🚗 Se le puso a otro auto del mismo modelo",
                     "Evidencia del mostrador, no de un catálogo."),
                    ("del_fabricante", "🏭 El fabricante del repuesto lo da para este auto",
                     "Sale del catálogo de aplicaciones, no de una coincidencia de texto."),
                    ("del_catalogo", "📋 Lo dice la descripción del catálogo",
                     "Es lo más amplio y lo menos seguro: depende de cómo escriba cada "
                     "proveedor."),
                ]
                if any(_sug.get(k) for k, _t, _a in _fuentes):
                    # LA PREGUNTA DEL MOSTRADOR. El cliente no pide «todo lo que le entra al
                    # auto», pide una pieza. Filtra por palabras sobre todas las columnas, así
                    # sirve tanto «junta tapa» como un pedazo del código.
                    _que_pieza = st.text_input(
                        "¿Qué pieza necesita?", key=f"pieza_de_{_todo['patente']}",
                        placeholder="junta de tapa, bujía, amortiguador delantero…"
                    ).strip().upper()
                    _palabras_pieza = [w for w in re.split(r'\s+', _que_pieza) if w]
                    # Con la pieza escrita se vuelve a preguntar, porque el filtro tiene que
                    # entrar en la CONSULTA: el catálogo de este auto viene cortado en los
                    # primeros 200 y filtrar esos 200 por «junta de tapa» no encuentra nada
                    # aunque el catálogo tenga 1.855 para este auto. Ver repuestos_de_este_auto.
                    if _palabras_pieza:
                        try:
                            _sug = repuestos_de_este_auto(
                                _v.get("marca_auto") or "", _v.get("modelo_auto") or "",
                                _v.get("anio"), _v.get("motorizacion") or "",
                                _v.get("vin") or "", limite=200, pieza=_que_pieza)
                        except Exception as _err:
                            anotar_error("repuestos por pieza", _err)

                    def _filtrar_por_pieza(filas):
                        if not _palabras_pieza:
                            return filas
                        salida_f = []
                        for fila_r in filas:
                            texto_fila = " ".join(str(x) for x in fila_r.values()).upper()
                            if all(w in texto_fila for w in _palabras_pieza):
                                salida_f.append(fila_r)
                        return salida_f

                    for _clave, _titulo, _ayuda in _fuentes:
                        _filas_fuente = _filtrar_por_pieza(_sug.get(_clave) or [])
                        if not _filas_fuente:
                            continue
                        st.markdown(f"**{_titulo}**")
                        _cuantos = len(_sug.get(_clave) or [])
                        st.caption(_ayuda + (
                            f" Mostrando {len(_filas_fuente)} de {_cuantos}."
                            if _palabras_pieza else f" {_cuantos} repuesto(s)."))
                        st.dataframe(quitar_id(_filas_fuente[:200]), width="stretch",
                                     hide_index=True)
                    if _palabras_pieza and not any(
                            _filtrar_por_pieza(_sug.get(k) or []) for k, _t, _a in _fuentes):
                        st.warning(
                            f"Ninguno de los repuestos que le entran a este auto dice "
                            f"«{_que_pieza}». Probá con una palabra sola, o buscalo por código "
                            "en el 🔍 Buscador."
                        )
                    if _sug.get("total_catalogo", 0) > len(_sug.get("del_catalogo") or []):
                        st.caption(
                            f"El catálogo tiene {_sug['total_catalogo']:,} repuestos para este "
                            f"auto y acá se listan los primeros "
                            f"{len(_sug.get('del_catalogo') or []):,}: escribí qué pieza "
                            "necesitás para achicar la lista."
                        )

                if _todo["por_motor"]:
                    st.markdown("**⚙️ Otros autos con el mismo modelo de motor**")
                    st.caption(
                        "Si este auto tiene el motor cambiado, esto vale más que la marca y el "
                        "modelo: los repuestos van con el motor, no con la carrocería."
                    )
                    st.dataframe(_todo["por_motor"], width="stretch", hide_index=True)

                if _todo["consultas"]:
                    st.markdown("**📞 Lo que este cliente preguntó antes**")
                    st.dataframe(_todo["consultas"], width="stretch", hide_index=True)

                if not _todo["historial"] and not _todo["sugeridos"]:
                    st.info(
                        "El auto está cargado pero todavía no tiene repuestos asociados. Se "
                        "van sumando solos a medida que se le cargan piezas en la ficha."
                    )

    # -------- Número de motor --------
    if sub_mec == SUB_MEC[2]:
        st.subheader("⚙️ Buscar por número de motor")
        explicar(
            "Para cuando el auto tiene el motor cambiado y el VIN ya no sirve.",
            "El número de motor está grabado en el block y es de ESE motor en particular. No "
            "es lo mismo que la motorización: «1.6 16v» es el tipo, el número es cuál.\n\n"
            "En un taller el motor cambiado pasa seguido: el chasis dice una cosa y el motor "
            "puesto es otro. Ahí el VIN te lleva a los repuestos equivocados y el número de "
            "motor te lleva a los que de verdad le entran.\n\nSe busca sin importar espacios, "
            "guiones ni mayúsculas: el mismo motor se anota de tres formas distintas según "
            "quién lo copie."
        )
        _nm = st.text_input("Número de motor:", key="buscar_num_motor",
                            placeholder="Como está grabado, con o sin guiones").strip()
        if _nm:
            if len(normalizar_numero_motor(_nm)) < 4:
                st.warning("Poné al menos 4 caracteres: con menos, coincide con cualquier cosa.")
            else:
                _ex, _par = buscar_por_numero_motor(_nm)
                if _ex:
                    st.success(f"✅ {len(_ex)} vehículo(s) con ese número de motor exacto:")
                    st.dataframe(quitar_id(_ex), width="stretch", hide_index=True)
                    _reps = repuestos_por_numero_motor(_nm)
                    if _reps:
                        st.markdown("**🔧 Lo que se le puso a ese motor:**")
                        st.caption(
                            "Esto es lo más confiable que hay: no es un catálogo diciendo qué "
                            "debería entrar, es lo que alguien efectivamente le instaló."
                        )
                        st.dataframe(_reps, width="stretch", hide_index=True)
                    else:
                        st.caption("Todavía no hay repuestos cargados en la ficha de ese auto.")
                if _par:
                    st.info(
                        f"🔎 {len(_par)} coincidencia(s) **parcial(es)**. El número de motor casi "
                        "nunca se lee entero: está grabado en el block, con grasa encima y en "
                        "una posición incómoda."
                    )
                    if any(x.get("Por qué") for x in _par):
                        st.caption(
                            "Algunas salieron de probar lecturas equivocadas comunes —un 0 que "
                            "era una O, un 5 que era una S—. La columna «Por qué» lo aclara."
                        )
                    st.dataframe(quitar_id(_par), width="stretch", hide_index=True)

                if _ex or _par:
                    _fam = autos_con_la_misma_familia_de_motor(_nm)
                    if _fam:
                        st.markdown("**🔩 Otros autos con un motor de la misma familia:**")
                        st.caption(
                            "El número arranca con el modelo de motor y sigue con el serial de "
                            "esa unidad. Si el modelo es el mismo, los repuestos son los mismos "
                            "aunque sea otro auto."
                        )
                        st.dataframe(_fam, width="stretch", hide_index=True)
                if not _ex and not _par:
                    st.warning(
                        "No hay ningún vehículo con ese número de motor. Se carga en la ficha "
                        "del auto, en **🚙 Repuestos por vehículo**."
                    )
                    st.caption(
                        "Si el auto no está cargado todavía, el número de motor solo no alcanza "
                        "para saber qué repuestos lleva: no existe una base pública que lo "
                        "traduzca. Lo que sirve es cargar la ficha una vez."
                    )

    # -------- Chasis / VIN (pantalla única) --------
    if sub_mec == SUB_MEC[1]:
        panel_vin(clave="vin_mec")

        st.markdown("---")
        st.markdown("**⚙️ Lo que la app fue aprendiendo**")
        st.caption(
            "Estas tablas son tuyas: se llenan solas con cada ficha de vehículo que cargues con "
            "VIN, y con lo que le enseñes arriba. Acá se revisan y se corrigen."
        )

        c.execute("""SELECT COUNT(*) FROM vehiculos WHERE vin IS NOT NULL AND LENGTH(vin) = 17
                     AND ((modelo_auto IS NOT NULL AND modelo_auto <> '')
                          OR (motorizacion IS NOT NULL AND motorizacion <> ''))""")
        fichas_con_vin = c.fetchone()[0]
        if fichas_con_vin:
            st.caption(f"Tenés {fichas_con_vin} ficha(s) de vehículo con VIN cargado.")
            if st.button("📚 Aprender modelos y motores de esas fichas"):
                n_mod, n_mot = aprender_modelos_de_fichas_existentes()
                avisar("success", f"Se aprendieron {n_mod} modelo(s) y {n_mot} motor(es) de tus fichas.")
                st.rerun()

        fabricantes_cargados = listar_fabricantes_vin()
        with st.expander(f"🏭 Fabricantes por WMI ({len(fabricantes_cargados)})"):
            st.caption(
                "Los 3 primeros caracteres del VIN. Vienen 328 cargados de la lista pública "
                "internacional; podés corregir o agregar los que falten."
            )
            if fabricantes_cargados:
                st.dataframe(fabricantes_cargados, width="stretch", hide_index=True)
            with st.form("form_wmi_admin", clear_on_submit=True):
                cw1, cw2, cw3 = st.columns(3)
                nuevo_wmi = cw1.text_input("WMI (3 caracteres)", max_chars=3)
                nuevo_fabricante = cw2.text_input("Fabricante")
                nuevo_pais_vin = cw3.text_input("País")
                if st.form_submit_button("💾 Guardar WMI"):
                    if len(nuevo_wmi.strip()) != 3 or not nuevo_fabricante.strip():
                        st.warning("El WMI debe tener 3 caracteres y el fabricante es obligatorio.")
                    else:
                        agregar_fabricante_vin(nuevo_wmi, nuevo_fabricante, nuevo_pais_vin)
                        avisar("success", f"WMI {nuevo_wmi.upper()} guardado.")
                        st.rerun()

        modelos_cargados = listar_modelos_vin()
        with st.expander(f"🚗 Modelos aprendidos ({len(modelos_cargados)})"):
            if modelos_cargados:
                st.dataframe(modelos_cargados, width="stretch", hide_index=True)
                cbm1, cbm2 = st.columns(2)
                wmi_borrar = cbm1.text_input("WMI a borrar", max_chars=3, key="wmi_borrar_modelo")
                vds_borrar = cbm2.text_input("Patrón (VDS) a borrar", max_chars=5, key="vds_borrar_modelo")
                if st.button("🗑️ Borrar ese patrón", disabled=not (wmi_borrar and vds_borrar)):
                    if olvidar_modelo_vin(wmi_borrar, vds_borrar):
                        st.success("Patrón borrado.")
                    else:
                        st.warning("No encontré ese patrón.")
                    st.rerun()
            else:
                st.caption(
                    "Todavía ninguno. Cada ficha de vehículo que cargues con VIN y modelo suma uno."
                )

        motores_cargados = listar_motores_vin()
        with st.expander(f"⚙️ Motores aprendidos ({len(motores_cargados)})"):
            st.caption(
                "La 8ª posición del VIN es el código de motor. Es el patrón que mejor rinde: el "
                "mismo código se repite en toda la gama de la marca, así que enseñarlo una vez "
                "sirve para los otros modelos."
            )
            if motores_cargados:
                st.dataframe(motores_cargados, width="stretch", hide_index=True)
                cbt1, cbt2 = st.columns(2)
                wmi_bm = cbt1.text_input("WMI a borrar", max_chars=3, key="wmi_borrar_motor")
                cod_bm = cbt2.text_input("Código (8ª posición)", max_chars=1, key="cod_borrar_motor")
                if st.button("🗑️ Borrar ese motor", disabled=not (wmi_bm and cod_bm)):
                    if olvidar_motor_vin(wmi_bm, cod_bm):
                        st.success("Borrado.")
                    else:
                        st.warning("No encontré ese código.")
                    st.rerun()
            else:
                st.caption("Todavía ninguno.")

    if sub_mec == SUB_MEC[3]:
        st.markdown("**🚙 Repuestos por vehículo**")
        st.caption(
            "Buscá lo que le entra a un auto entrando por marca y modelo, en vez de por código. "
            "Sale de las descripciones de tus propias listas — o sea que crece solo cada vez que "
            "importás un proveedor nuevo."
        )

        version_catalogo = version_del_catalogo()
        disponibles = marcas_vehiculo_disponibles(version_catalogo)

        # Guardar lo que dicen las descripciones, en vez de releerlas cada vez. Además de que
        # buscar por vehículo pase a andar para esos productos, la app ya cruza los que le
        # sirven a los mismos autos: llenar esta tabla genera equivalencias nuevas sola.
        with st.expander("🪄 Leer de las descripciones a qué auto le va cada repuesto"):
            explicar(
                "Las listas ya dicen el auto («JUNTA TAPA FORD TAUNUS 1969/78»). Esto lo guarda "
                "para poder buscar por vehículo.",
                "El modelo no se adivina: tiene que ser uno que la app ya reconoce como modelo "
                "de esa marca, mirando en cuántas marcas distintas aparece cada palabra en TU "
                "catálogo. Un ASTRA aparece casi solo en Chevrolet y es un modelo; un BOMBA "
                "aparece en todas y no lo es. Si el modelo no está confirmado así, esa fila no "
                "se genera — con un modelo inventado la app cruzaría piezas que no van "
                "juntas.\n\nQuedan marcadas como **deducidas**, para distinguirlas de las que "
                "vinieron del catálogo de un fabricante y poder revisarlas aparte.",
                en_expander=True
            )
            if st.button("🔍 Ver qué se podría cargar", key="btn_ver_aplic_desc"):
                st.session_state["aplic_deducidas"] = aplicaciones_desde_descripciones()
            _apl = st.session_state.get("aplic_deducidas")
            if _apl is not None:
                if not _apl:
                    st.info("No encontré descripciones con una marca y un modelo reconocibles "
                            "que no estén ya cargados.")
                else:
                    st.success(f"Se pueden cargar **{len(_apl)} aplicación(es)**. Revisá la "
                               "muestra antes de aplicar:")
                    st.dataframe([{k: v for k, v in f.items() if not k.startswith("_")}
                                  for f in _apl[:50]],
                                 width="stretch", hide_index=True)
                    if st.button("✅ Cargar esas aplicaciones", type="primary",
                                  key="btn_aplicar_aplic_desc"):
                        _n = aplicar_aplicaciones_deducidas(_apl)
                        st.session_state.pop("aplic_deducidas", None)
                        avisar("success", f"Se cargaron {_n} aplicación(es) deducidas.")
                        st.rerun()

        if not disponibles:
            st.info(
                "Todavía no se detectó ninguna marca de vehículo en las descripciones del catálogo. "
                "Aparecen solas a medida que vas importando listas de proveedores."
            )
        else:
            etiquetas_marcas = [f"{m} ({n} productos)" for m, n in disponibles]
            mapa_marcas = {f"{m} ({n} productos)": m for m, n in disponibles}

            st.info(
                "🔢 ¿Tenés el número de chasis? Andá a **🛠️ Modo Mecánico → 🔢 Chasis / VIN**: "
                "pegás el VIN y te da directamente los repuestos que lleva ese auto, sin tener "
                "que elegir marca y modelo acá a mano."
            )

            etiqueta_elegida = st.selectbox("Marca del vehículo:", etiquetas_marcas,
                                             key="sel_marca_vehiculo")
            marca_elegida = mapa_marcas[etiqueta_elegida]
            por_categoria = catalogo_por_vehiculo(marca_elegida, version_catalogo)

            if not por_categoria:
                st.caption("No se pudo separar la categoría de esas descripciones.")
            else:
                # El modelo sale de una lista detectada del propio catálogo, y el año filtra
                # usando los rangos que traen las descripciones ("1974/81", "1998/...").
                # Es lo más parecido a un catálogo de aplicaciones que se puede armar sin
                # comprar una base licenciada: cubre lo que vos vendés, no todo el mercado.
                modelos_detectados = modelos_de_marca(marca_elegida, version_catalogo)
                cmv1, cmv2 = cols(2)
                with cmv1:
                    if modelos_detectados:
                        opciones_mod = ["Todos los modelos"] + [f"{m} ({n})" for m, n in modelos_detectados[:120]]
                        mapa_mod = {f"{m} ({n})": m for m, n in modelos_detectados[:120]}

                        if st.session_state.get("sel_modelo_vehiculo") not in opciones_mod:
                            # Cambió la marca y el modelo guardado ya no existe: sin esto el
                            # selector tira excepción y se cae la pantalla.
                            st.session_state.pop("sel_modelo_vehiculo", None)

                        mod_etiqueta = st.selectbox("Modelo / motor:", opciones_mod, key="sel_modelo_vehiculo")
                        modelo_elegido = mapa_mod.get(mod_etiqueta)
                    else:
                        modelo_elegido = None
                        st.caption("No se detectaron modelos para esta marca.")
                with cmv2:
                    anio_filtro = st.number_input(
                        "Año del vehículo (0 = cualquiera):", min_value=0, max_value=2030,
                        value=0, step=1, key="anio_vehiculo_filtro",
                        help="Usa los rangos que traen las descripciones. Lo que no aclara años "
                             "se muestra igual, marcado aparte."
                    )

                filtro_modelo = st.text_input(
                    "Además, filtrar por texto (opcional):",
                    key="filtro_modelo_vehiculo", placeholder="Ej: 1.6, inyección, turbo..."
                ).strip().upper()

                categorias = sorted(por_categoria.keys(), key=lambda k: -len(por_categoria[k]))
                opciones_cat = ["Todas las categorías"] + [f"{c_} ({len(por_categoria[c_])})"
                                                            for c_ in categorias]
                mapa_cat = {f"{c_} ({len(por_categoria[c_])})": c_ for c_ in categorias}
                cat_etiqueta = st.selectbox("Categoría (opcional):", opciones_cat,
                                             key="sel_categoria_vehiculo")

                if cat_etiqueta == "Todas las categorías":
                    items = [x for lista in por_categoria.values() for x in lista]
                else:
                    items = list(por_categoria[mapa_cat[cat_etiqueta]])

                if modelo_elegido:
                    # Como PALABRA y no como subcadena. Desde que el desplegable ofrece los
                    # modelos que son números —206, 307, 405— buscarlos adentro del texto
                    # engancha cualquier número de parte que los contenga: pedir el 206 traía
                    # 1.554 productos y 100 eran filas de Citroën con el código 9662063280.
                    # Sobre el texto despegado, para no perder el «307REF ORIG» de una de las
                    # listas, que como palabra suelta tampoco daría.
                    _re_modelo = re.compile(rf'(?<![A-Z0-9]){re.escape(modelo_elegido)}(?![A-Z0-9])')
                    items = [x for x in items
                             if _re_modelo.search(x.get("_texto")
                                                   or (x["Descripcion"] or "").upper())]
                if filtro_modelo:
                    palabras = [p for p in filtro_modelo.split() if p]
                    items = [x for x in items
                             if all(p in (x["Descripcion"] or "").upper() for p in palabras)]

                # El año separa en tres grupos: sirve, no sirve, y "la descripción no lo aclara"
                sin_dato_anio = []
                if anio_filtro:
                    coinciden, sin_dato = [], []
                    for x in items:
                        r = sirve_para_anio(x["Descripcion"], int(anio_filtro))
                        if r is True:
                            coinciden.append(x)
                        elif r is None:
                            sin_dato.append(x)
                    items, sin_dato_anio = coinciden, sin_dato

                hay_filtro = modelo_elegido or filtro_modelo or anio_filtro or \
                    cat_etiqueta != "Todas las categorías"
                if not hay_filtro:
                    st.info(
                        f"Hay {len(items)} repuesto(s) de **{marca_elegida}**. Elegí el modelo "
                        "(o escribí el año) para achicar la lista."
                    )
                    items = items[:25]
                else:
                    resumen_filtro = " · ".join(filter(None, [
                        marca_elegida, modelo_elegido,
                        f"año {int(anio_filtro)}" if anio_filtro else None,
                    ]))
                    st.success(f"**{len(items)}** repuesto(s) para {resumen_filtro}")

                if items:
                    st.caption("👆 Tocá un código para ver todas sus equivalencias:")
                    for it in items[:30]:
                        cvv1, cvv2 = st.columns([1.2, 3])
                        cvv1.button(f"🔎 {it['Codigo']}", key=f"veh_{it['ID']}",
                                     on_click=cb_ver_equivalencias, args=(it["Codigo"],))
                        precio_v = f"${it['Precio']:,.0f}" if it.get("Precio") else "s/precio"
                        stock_v = it.get("Stock")
                        detalle = it.get("_aplicacion") or it.get("Descripcion") or ""
                        desde_a, hasta_a = extraer_anios(it["Descripcion"])
                        anios_txt = ""
                        if desde_a:
                            anios_txt = f" · {desde_a}–{hasta_a if hasta_a else 'en adelante'}"
                        cvv2.caption(f"**{it['_categoria']}**{anios_txt} · {detalle[:64]}  \n"
                                      f"{it['Marca']} · {precio_v} · stock "
                                      f"{stock_v if stock_v is not None else 's/d'}")
                    if len(items) > 30:
                        st.caption(f"(mostrando 30 de {len(items)})")
                elif hay_filtro:
                    st.warning("Ningún repuesto coincide con esa combinación.")

                if sin_dato_anio:
                    with st.expander(f"❔ {len(sin_dato_anio)} repuesto(s) que no aclaran el año "
                                      "(pueden servir igual)"):
                        st.caption(
                            "La descripción no dice para qué años es, así que no se puede afirmar "
                            "ni descartar. Se muestran aparte para que decidas vos."
                        )
                        for it in sin_dato_anio[:20]:
                            csd1, csd2 = st.columns([1.2, 3])
                            csd1.button(f"🔎 {it['Codigo']}", key=f"vehsd_{it['ID']}",
                                         on_click=cb_ver_equivalencias, args=(it["Codigo"],))
                            csd2.caption(f"**{it['_categoria']}** · "
                                          f"{(it.get('_aplicacion') or '')[:64]}")
                        if len(sin_dato_anio) > 20:
                            st.caption(f"(mostrando 20 de {len(sin_dato_anio)})")

            esquemas_veh = esquemas_de_vehiculo(marca_elegida)
            if esquemas_veh:
                st.markdown("---")
                st.markdown(f"**🗺️ Esquemas cargados de {marca_elegida}**")
                for e in esquemas_veh[:10]:
                    st.caption(f"• {e['titulo']} — {e['modelo_auto'] or ''} {e['sistema'] or ''}")
                st.caption("Se ven completos, con las piezas marcadas, en la sección Esquemas.")


    if sub_mec == SUB_MEC[5]:
        st.caption(
            "Diagramas organizados por Marca › Vehículo › Sistema, donde cada pieza marcada tiene "
            "su código vinculado al catálogo — así se busca directo desde el dibujo, ya sea en el "
            "taller o en el mostrador de una casa de repuestos. Las imágenes las tenés que subir vos."
        )
        modo_esq = st.radio(
            "¿Cómo lo buscás?", ["📂 Explorar por categoría", "🔎 Buscar por texto"],
            horizontal=True, key="modo_esquemas"
        )

        if modo_esq.startswith("📂"):
            marcas_esq = listar_marcas_esquemas()
            if not marcas_esq:
                st.info("Todavía no hay esquemas cargados con marca definida. Subí el primero más abajo.")
            else:
                marca_sel = st.selectbox("Marca:", marcas_esq, key="esq_marca_sel")
                modelos_esq = listar_modelos_esquemas(marca_sel)
                if not modelos_esq:
                    st.caption(f"No hay vehículos cargados todavía para {marca_sel}.")
                else:
                    modelo_sel = st.selectbox("Vehículo / modelo:", modelos_esq, key="esq_modelo_sel")
                    sistemas_esq = listar_sistemas_esquemas(marca_sel, modelo_sel)
                    if not sistemas_esq:
                        st.caption("No hay esquemas con sistema/parte definida para este vehículo.")
                    else:
                        sistema_sel = st.selectbox("Sistema / parte:", sistemas_esq, key="esq_sistema_sel")
                        mostrar_lista_esquemas(listar_esquemas_por_categoria(marca_sel, modelo_sel, sistema_sel))
        else:
            filtro_esq = st.text_input("Buscar esquema (título, marca, modelo o sistema):", key="esq_filtro")
            mostrar_lista_esquemas(listar_esquemas(filtro_esq))

        st.markdown("---")
        if not pedir_password_admin("subir esquemas nuevos"):
            pass
        else:
            marcas_existentes = listar_marcas_esquemas()

            st.markdown("**🚗 Precargar marca / vehículo (sin imagen todavía)**")
            st.caption(
                "Dejá lista la estructura del árbol aunque todavía no tengas ningún esquema para subir — "
                "va a aparecer en 'Explorar por categoría' apenas la guardes."
            )
            cp1, cp2 = st.columns(2)
            if marcas_existentes:
                marca_pre_opcion = cp1.selectbox("Marca", marcas_existentes + ["➕ Nueva marca..."], key="pre_marca_opcion")
                marca_pre = cp1.text_input("Nombre de la nueva marca", key="pre_marca_nueva") \
                    if marca_pre_opcion == "➕ Nueva marca..." else marca_pre_opcion
            else:
                marca_pre = cp1.text_input("Marca", key="pre_marca_sola")
            modelo_pre = cp2.text_input("Vehículo / modelo", placeholder="Ej: Corsa", key="pre_modelo")
            if st.button("➕ Precargar"):
                if not marca_pre.strip() or not modelo_pre.strip():
                    st.warning("Completá marca y modelo.")
                else:
                    agregar_vehiculo_catalogo(marca_pre, modelo_pre)
                    st.success(f"{marca_pre.strip()} {modelo_pre.strip()} precargado.")
                    for k in ["pre_marca_nueva", "pre_marca_sola", "pre_modelo"]:
                        st.session_state.pop(k, None)
                    st.rerun()

            precargados = listar_catalogo_precargado()
            if precargados:
                with st.expander(f"📋 Ver / borrar precargados sin esquema todavía ({len(precargados)})"):
                    for pv in precargados:
                        colp1, colp2 = st.columns([4, 1])
                        colp1.write(f"{pv['marca']} — {pv['modelo']}")
                        colp2.button("🗑️", key=f"del_precarga_{pv['marca']}_{pv['modelo']}",
                                      on_click=eliminar_vehiculo_catalogo, args=(pv["marca"], pv["modelo"]))

            st.markdown("---")
            st.markdown("**➕ Subir un esquema nuevo**")
            marcas_existentes = listar_marcas_esquemas()  # puede haber cambiado si acabás de precargar una
            titulo_esq = st.text_input("Título", placeholder="Ej: Esquema eléctrico bomba de combustible", key="esq_titulo")
            ce1, ce2 = st.columns(2)
            if marcas_existentes:
                marca_opcion = ce1.selectbox("Marca", marcas_existentes + ["➕ Nueva marca..."], key="esq_marca_opcion")
                marca_esq = ce1.text_input("Nombre de la nueva marca", key="esq_marca_nueva") \
                    if marca_opcion == "➕ Nueva marca..." else marca_opcion
            else:
                marca_esq = ce1.text_input("Marca del auto", key="esq_marca_sola")
            modelos_para_marca = listar_modelos_esquemas(marca_esq) if marca_esq else []
            if modelos_para_marca:
                modelo_opcion = ce2.selectbox("Vehículo / modelo", modelos_para_marca + ["➕ Nuevo modelo..."], key="esq_modelo_opcion")
                modelo_esq = ce2.text_input("Nombre del nuevo modelo", key="esq_modelo_nuevo") \
                    if modelo_opcion == "➕ Nuevo modelo..." else modelo_opcion
            else:
                modelo_esq = ce2.text_input("Vehículo / modelo", placeholder="Ej: Gol Trend", key="esq_modelo_solo")
            sistema_opcion = st.selectbox("Sistema / parte:", CATEGORIAS_ESQUEMA, key="esq_sistema_opcion")
            sistema_esq = st.text_input("Especificá el sistema/parte:", key="esq_sistema_nuevo") \
                if sistema_opcion == "Otro" else sistema_opcion
            desc_esq = st.text_input("Descripción (opcional)", key="esq_desc")

            origen_imagen = st.radio(
                "¿De dónde sale la imagen?",
                ["📷 Subir foto real", "🤖 Generar orientativo con IA (sin foto real)"],
                key="esq_origen_imagen"
            )

            archivo_esq = None
            imagen_generada_bytes = None
            if origen_imagen.startswith("📷"):
                archivo_esq = subir_archivo("Imagen del esquema", ["png", "jpg", "jpeg"], "esquema")
                if archivo_esq:
                    archivo_listo(archivo_esq, "imagen")
                    boton_otro_archivo("esquema", "🗑️ Usar otra imagen", key="otra_img_esquema")
            else:
                explicar(
                    "Para cuando no tenés el auto físico enfrente (útil en el mostrador de una casa de "
                    "repuestos):",
                    "la IA arma un dibujo genérico de referencia, **no una foto real de ese vehículo**. "
                    "Sirve para orientar, no para identificar piezas con precisión milimétrica. Usa Gemini, "
                    "con una API key configurada por separado del resto de las funciones."
                )
                motorizacion_ia = st.text_input("Motorización", placeholder="Ej: 1.6 MSI Nafta", key="esq_motorizacion_ia")
                boton_label = "🔄 Generar otra vez" if st.session_state.get("esq_preview_ia") else "🤖 Generar imagen orientativa"
                if st.button(boton_label):
                    if not marca_esq.strip() or not modelo_esq.strip():
                        st.warning("Completá marca y modelo antes de generar.")
                    else:
                        with st.spinner("Generando..."):
                            img_ia, error_ia = generar_esquema_orientativo_ia(
                                marca_esq, modelo_esq, motorizacion_ia,
                                sistema_esq if sistema_opcion == "Otro" else sistema_opcion
                            )
                        if error_ia:
                            st.error(error_ia)
                        else:
                            st.session_state["esq_preview_ia"] = img_ia
                            st.rerun()
                if st.session_state.get("esq_preview_ia"):
                    st.image(st.session_state["esq_preview_ia"], width="stretch",
                              caption="Vista previa — orientativo, no es una foto real")
                    imagen_generada_bytes = st.session_state["esq_preview_ia"]

            subir_esq_btn = st.button("📥 Guardar esquema", type="primary")
            if subir_esq_btn:
                imagen_final = archivo_esq.getvalue() if archivo_esq else imagen_generada_bytes
                nombre_final = archivo_esq.name if archivo_esq else "generado_ia.jpg"
                if not titulo_esq.strip() or not imagen_final or not marca_esq.strip() or not modelo_esq.strip():
                    st.warning("Completá título, marca, modelo, y subí o generá una imagen.")
                elif sistema_opcion == "Otro" and not sistema_esq.strip():
                    st.warning("Especificá el sistema/parte.")
                else:
                    guardar_esquema(titulo_esq, marca_esq, modelo_esq, sistema_esq, desc_esq,
                                     imagen_final, nombre_final, generado_ia=(imagen_generada_bytes is not None))
                    st.success("Esquema guardado.")
                    st.session_state.pop("esq_preview_ia", None)
                    for k in ["esq_titulo", "esq_marca_nueva", "esq_modelo_nuevo", "esq_sistema_nuevo",
                              "esq_desc", "esq_motorizacion_ia"]:
                        st.session_state.pop(k, None)
                    olvidar_archivo("esquema")
                    st.rerun()

    # -------- Conversor de unidades --------
    if sub_mec == SUB_MEC[6]:
        st.caption("Conversiones rápidas de unidades que se usan seguido en manuales de taller antiguos o importados.")

        categoria_conv = st.radio("Categoría:", ["Torque", "Presión", "Longitud"], horizontal=True, key="conv_categoria")

        if categoria_conv == "Torque":
            direccion = st.radio("Convertir:", ["lb-ft → Nm", "Nm → lb-ft", "lb-in → Nm", "Nm → lb-in"],
                                  key="conv_torque_dir")
            valor = st.number_input("Valor a convertir:", min_value=0.0, step=0.1, key="conv_torque_valor")
            factores = {
                "lb-ft → Nm": (valor * 1.35582, "Nm"),
                "Nm → lb-ft": (valor / 1.35582, "lb-ft"),
                "lb-in → Nm": (valor * 0.112985, "Nm"),
                "Nm → lb-in": (valor / 0.112985, "lb-in"),
            }
            resultado, unidad = factores[direccion]
            st.metric("Resultado", f"{resultado:.2f} {unidad}")

        elif categoria_conv == "Presión":
            direccion = st.radio("Convertir:", ["PSI → Bar", "Bar → PSI", "PSI → kPa", "kPa → PSI"],
                                  key="conv_presion_dir")
            valor = st.number_input("Valor a convertir:", min_value=0.0, step=0.1, key="conv_presion_valor")
            factores = {
                "PSI → Bar": (valor * 0.0689476, "Bar"),
                "Bar → PSI": (valor / 0.0689476, "PSI"),
                "PSI → kPa": (valor * 6.89476, "kPa"),
                "kPa → PSI": (valor / 6.89476, "PSI"),
            }
            resultado, unidad = factores[direccion]
            st.metric("Resultado", f"{resultado:.2f} {unidad}")

        else:  # Longitud
            direccion = st.radio("Convertir:", ["Pulgadas → mm", "mm → Pulgadas", "Pulgadas → cm", "cm → Pulgadas"],
                                  key="conv_longitud_dir")
            valor = st.number_input("Valor a convertir:", min_value=0.0, step=0.1, key="conv_longitud_valor")
            factores = {
                "Pulgadas → mm": (valor * 25.4, "mm"),
                "mm → Pulgadas": (valor / 25.4, "pulgadas"),
                "Pulgadas → cm": (valor * 2.54, "cm"),
                "cm → Pulgadas": (valor / 2.54, "pulgadas"),
            }
            resultado, unidad = factores[direccion]
            st.metric("Resultado", f"{resultado:.3f} {unidad}")

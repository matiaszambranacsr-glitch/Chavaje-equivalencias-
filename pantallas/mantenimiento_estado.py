"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/.

🗂️ Administrar → 🧹 Mantenimiento → 🩺 Estado y papelera: sus herramientas, en el orden
en que se muestran. Corre después de pantallas/mantenimiento.py, que elige el grupo."""

# ============================================================
# MANTENIMIENTO → ESTADO Y PAPELERA
# ============================================================
if pagina == PAGINAS[3]:
    if sub_admin == SUB_ADMIN[4]:
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
                        f"({miles(_res_sc['cruzan'])} de {miles(_res_sc['productos'])})."
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
                            + f" ya tienen las equivalencias encontradas.** Son {miles(_esp_n)} "
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

        if _grupo_mant == GRUPOS_MANTENIMIENTO[5]:
            # CUÁNTO ATRASADOS ESTÁN LOS PRECIOS. Va acá, al lado de las importaciones, porque
            # lo que se hace con este número es pedir la lista nueva.
            st.markdown("**⏳ Qué tan atrasada está cada lista**")
            explicar(
                "Los días que pasaron desde la última carga, la inflación oficial desde entonces "
                "y, si la importaste más de una vez, a qué ritmo viene aumentando.",
                "El ritmo sale de tu propio historial de precios: la app guarda cada cambio, así "
                "que puede medir cuánto aumentó ESE proveedor entre tus importaciones y cruzarlo "
                "con los días que pasaron.\n\n"
                "Con una sola importación no hay ritmo propio, y para eso está la **inflación "
                "del INDEC** desde la última carga: cuenta los meses enteros ya publicados, así "
                "que es un piso —el INDEC publica cada mes a mediados del siguiente—.\n\n"
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
                elif _peor["_atraso"] >= 0.05:
                    # Sin ritmo propio, con la inflación oficial: ver inflacion_desde().
                    st.warning(
                        f"⏳ **Desde la última carga de {_peor['Lista']} la inflación oficial "
                        f"fue {_peor['Inflación desde la última carga (INDEC)']}.** Es un piso: "
                        "sus precios están, como mínimo, eso abajo.")
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
                            f"{miles(_var['30'] * 100, 1)}% en los últimos 30 días"
                            + (f" y {miles(_var['90'] * 100, 1)}% en 90"
                               if _var.get("90") is not None else "")
                            + f" (al {_d.get('fecha', 'sin fecha')}"
                            + (f"; {_d['fuente']}" if _d.get("fuente") else "") + ").")
                    _i = _ctx.get("ipc") or {}
                    if _i.get("variacion") is not None:
                        _lineas.append(
                            f"La **inflación** del último mes publicado por el INDEC "
                            f"({_i.get('mes', '')[:7]}) fue {miles(_i['variacion'] * 100, 1)}%.")
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
                # La prueba en vivo de las fuentes de afuera: ver probar_fuentes_de_afuera().
                if st.button("🔌 Probar las fuentes de afuera", key="probar_fuentes",
                             help="INDEC, BCRA, dólar minorista y NHTSA: una consulta a cada "
                                  "una, para ver si contestan desde el servidor."):
                    with st.spinner("Consultando…"):
                        st.dataframe(probar_fuentes_de_afuera(), width="stretch",
                                     hide_index=True)
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
                        + f"**: {miles(sum(f['Esperando revisión'] for f in _esperan))} "
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
            ayuda(
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
            ayuda(
                "Un producto «sin equivalencia» es uno que todavía NO cruzaste con ningún otro "
                "código. No quiere decir que esté mal cargado: puede tener precio, stock y "
                "venderse igual. Borralos solo si sabés que entraron por una importación fallida."
            )
            if not _sueltos:
                st.caption("✅ No hay productos sin equivalencias.")
            else:
                (st.warning if _porcentaje >= 20 else st.info)(
                    f"Hay **{miles(_sueltos)}** producto(s) sin ninguna equivalencia, de {miles(_todos)} "
                    f"— el {_porcentaje}% del catálogo."
                )
                # Y los que tienen una equivalencia que no lleva a ningún lado. El buscador ya
                # se los marca así; sin decirlo acá también, las dos pantallas contaban
                # distinto el mismo producto.
                _muertos = contar_con_equivalencia_muerta()
                if _muertos:
                    st.info(
                        f"➕ Otros **{miles(_muertos)}** tienen una equivalencia cargada que **no "
                        "lleva a ningún lado**: el único código vinculado es su propio código "
                        "de fábrica, que todavía no tiene nadie más. El buscador ya se los "
                        "marca así.\n\n"
                        "**A esos no los borres.** Se resuelven solos cuando entre otra lista "
                        "que traiga el mismo código de fábrica, o con **"
                        f"{miga_hasta('Buscar equivalencias en TODO el catálogo de una')}**, "
                        "que los cruza por descripción."
                    )
                # Una casilla además de la contraseña, como en «Eliminar marca» y «Eliminar
                # producto». Acá hace más falta que en ninguna: son 34.457 productos —el 48%
                # del catálogo, casi todos vendibles y con precio— detrás de un solo botón, y
                # no hay papelera para esto. La contraseña sola protege de que lo toque quien
                # no debe; la casilla protege del dedo equivocado del que sí puede.
                _confirmar_sueltos = st.checkbox(
                    f"Confirmo que quiero borrar {miles(_sueltos)} productos y que esto NO se puede "
                    "deshacer", key="confirmar_borrar_sueltos")
                if candado('borrar productos sin equivalencias',
                            st.button(f"🧹 Borrar esos {miles(_sueltos)} productos",
                                       disabled=not _confirmar_sueltos),
                            'borrar_productos_sin_equivalencias'):
                    borrados = depurar_huerfanos()
                    avisar("success", f"Se borraron {miles(borrados)} producto(s) sin equivalencias.")
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

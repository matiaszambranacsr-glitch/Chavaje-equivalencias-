"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/.

🗂️ Administrar → 🧹 Mantenimiento → 🧹 Limpiar y corregir: sus herramientas, en el orden
en que se muestran. Corre después de pantallas/mantenimiento.py, que elige el grupo."""

# ============================================================
# MANTENIMIENTO → LIMPIAR Y CORREGIR
# ============================================================
if pagina == PAGINAS[3]:
    if sub_admin == SUB_ADMIN[4]:
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
                ayuda(
                    "Mirá la columna «Marcas distintas»: un repuesto real se vincula con unas pocas "
                    "marcas. Uno que toca 20 marcas distintas casi nunca es legítimo."
                )
                st.dataframe(puentes, width="stretch", hide_index=True)
                ayuda(
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

            # El número de verdad con la marca pegada adelante. No es un puente falso —el número
            # es el de la pieza— así que no se borra: se le saca la marca. Ver
            # codigos_de_fabrica_con_la_marca_pegada().
            st.markdown("**🏷️ Códigos de fábrica con la marca pegada**")
            explicar(
                "Números de fábrica que quedaron escritos con la marca adelante: "
                "«POWER836120129», «DEERER43413», «BENZ3120150080».",
                "ILLINOIS escribe «AGCO SISU POWER836120129» o «JOHN DEERER43413» y al "
                "exportar se pierde el espacio. El número es el de la pieza, pero así escrito "
                "no lo tiene ninguna otra lista, así que no une nada.\n\n"
                "Corregir le saca la marca. Si el número limpio ya estaba cargado —ILLINOIS "
                "suele escribirlo dos veces en la misma fila— se juntan los dos en uno, con "
                "sus vínculos y los pendientes. **Nada se borra**: el producto de fábrica "
                "queda con el número bien escrito."
            )
            if st.button("🏷️ Buscar códigos con la marca pegada", key="btn_marca_pegada"):
                st.session_state["marca_pegada"] = codigos_de_fabrica_con_la_marca_pegada()
            _mp = st.session_state.get("marca_pegada")
            if _mp is not None:
                if not _mp:
                    st.success("No quedó ninguno.")
                else:
                    st.warning(f"**{len(_mp)} código(s) con la marca pegada**, de los que "
                               f"{sum(1 for x in _mp if x['Ya existe'])} ya estaban cargados "
                               "bien escritos.")
                    st.dataframe([{k: v for k, v in x.items() if k != "pid"} for x in _mp],
                                  width="stretch", hide_index=True)
                    if candado("corregir los códigos con la marca pegada",
                                st.button(f"🏷️ Corregir los {len(_mp)}", type="primary",
                                           key="btn_corregir_marca_pegada"),
                                "corregir_marca_pegada"):
                        _hechos = sum(1 for x in _mp
                                      if corregir_codigo_con_la_marca_pegada(x["pid"], x["Número"]))
                        st.session_state.pop("marca_pegada", None)
                        invalidar_salud()
                        avisar("ok", f"Se corrigieron {_hechos} código(s) de fábrica.")
                        st.rerun()
            st.markdown("---")

            # La otra mitad de lo de arriba: los que cuelgan de UN solo producto. Ver
            # codigos_adivinados_que_no_unen_nada().
            st.markdown("**🧽 Códigos adivinados que no unen nada**")
            explicar(
                "Medidas, motores y herramientas que entraron como código de fábrica, leídos de "
                "la descripción de una lista que nunca marca el código de fábrica.",
                "Pasa con listas como la de IMPERIAL: en «RET DIST FORD 1.4 TDCI 40x55x» o "
                "«BOCALLAVE 1/2 ESTR.32MM» la importación leía «40x55x» y «ESTR.32MM» como "
                "códigos de fábrica. Ahora ya no los toma, pero los que entraron antes siguen "
                "ahí, y cada uno es un par más en la cola de revisión.\n\n"
                "Aparece solo el que cumple todo: une productos de una sola lista, esa lista "
                "casi nunca marca el código de fábrica («REF ORIG», «Nº», «//»), el código "
                "está escrito sin marcar en la descripción, no es el código de otro "
                "proveedor, y ninguno de sus vínculos está aprobado.\n\n"
                "**No se pierde la búsqueda**: si alguien escribe ese número, el buscador lo "
                "encuentra igual adentro de la descripción."
            )
            if st.button("🧽 Buscarlos", key="btn_adivinados"):
                with st.spinner("Mirando cada código de fábrica y de dónde salió..."):
                    st.session_state["codigos_adivinados"] = codigos_adivinados_que_no_unen_nada()
            _adv = st.session_state.get("codigos_adivinados")
            if _adv is not None:
                if not _adv:
                    st.success("No hay ninguno: cada código de fábrica cargado une algo, o lo "
                               "marcó el proveedor.")
                else:
                    _adv_pend = sum(x.get("Esperando revisión") or 0 for x in _adv)
                    _adv_listas = sorted({x["Lista"] for x in _adv})
                    st.warning(
                        f"**{len(_adv):,} código(s) adivinados** de {', '.join(_adv_listas)}, "
                        f"con {_adv_pend:,} par(es) esperando revisión que se van con ellos."
                    )
                    st.dataframe([{k: v for k, v in x.items() if k != "pid"} for x in _adv],
                                  width="stretch", hide_index=True)
                    st.download_button(
                        "⬇️ Bajarlos en Excel antes de decidir",
                        data=to_excel_bytes([{k: v for k, v in x.items() if k != "pid"}
                                              for x in _adv]),
                        file_name="codigos_adivinados.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="dl_adivinados")
                    st.caption("Se borra el código de fábrica y los pendientes que colgaban de "
                               "él. **Los productos no se tocan**: precios, stock e historial "
                               "quedan igual.")
                    if st.checkbox("Miré la lista y entiendo qué se borra", key="conf_adivinados"):
                        if candado("borrar los códigos adivinados",
                                    st.button(f"🗑️ Borrar los {len(_adv):,}", type="primary",
                                               key="btn_borrar_adivinados"),
                                    "borrar_los_codigos_adivinados"):
                            _barra_adv = st.progress(0.0, text="Borrando...")
                            _tot_adv = 0
                            for _i_adv, _x in enumerate(_adv):
                                _tot_adv += borrar_puente_y_sus_pendientes(_x["pid"])[1]
                                if _i_adv % 50 == 0:
                                    _barra_adv.progress((_i_adv + 1) / len(_adv),
                                                        text=f"Borrando... {_i_adv + 1:,} de "
                                                             f"{len(_adv):,}")
                            _barra_adv.empty()
                            st.session_state.pop("codigos_adivinados", None)
                            invalidar_salud()
                            avisar("ok", f"Se borraron {len(_adv):,} código(s) adivinados y "
                                          f"{_tot_adv:,} pendiente(s). Los productos quedaron "
                                          "intactos.")
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
                "Les pasa el análisis de confianza a los vínculos que ya están cargados y te "
                "muestra los peores.",
                "El análisis mira solo lo que espera revisión, pero el problema grande está en lo "
                "que ya entró: lo que cargaron importaciones viejas que nadie revisó. Sin esto, la "
                "única forma de encontrarlos es tropezarse con uno buscando un código.\n\n"
                "**Vuelve a mirar TODO cada vez que lo corrés, con las reglas de hoy.** No queda "
                "nada marcado como «ya revisado»: los vínculos se cargaron con las reglas de su "
                "momento y las reglas fueron cambiando, así que uno que pasaba limpio hace un mes "
                "puede no pasar hoy. Tarda unos segundos."
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
                ayuda(
                    "Revisá primero los de arriba. Si el precio está bien, entonces lo que está mal "
                    "es el vínculo: buscá uno de los dos códigos en el 🔍 Buscador, abrí «🧭 ¿Por qué "
                    "apareció alguno de estos?» y tocá «✂️ Cortar ese vínculo». Si el mismo código "
                    "aparece en muchos pares, es un puente: "
                    f"{miga_hasta('Códigos puente')}."
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
            ayuda(
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
                    "No cambia lo que encuentra el buscador, pero sí infla todos los conteos.",
                    "El buscador consulta las dos columnas igual. Pero un código con 100 equivalencias "
                    "reales figura con 200, y el control de precios lista "
                    "cada par dos veces. Unificarlas no borra ninguna equivalencia, solo deja una sola fila "
                    "por cada una."
                )
                if st.button("🔁 Unificar duplicadas"):
                    borradas, vueltas = unificar_equivalencias_espejadas()
                    invalidar_salud()
                    avisar("success", f"Se unificaron {borradas:,} duplicadas "
                                       f"y se ordenaron {vueltas:,}.")
                    st.rerun()

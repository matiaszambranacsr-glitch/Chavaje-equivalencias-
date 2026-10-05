"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/.

🗂️ Administrar → 🧹 Mantenimiento → 📷 Fotos: sus herramientas, en el orden
en que se muestran. Corre después de pantallas/mantenimiento.py, que elige el grupo."""

# ============================================================
# MANTENIMIENTO → FOTOS
# ============================================================
if pagina == PAGINAS[3]:
    if sub_admin == SUB_ADMIN[4]:
        if _grupo_mant == GRUPOS_MANTENIMIENTO[4]:
            st.markdown("**📷 Traer fotos de productos en tanda**")
            ayuda(
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
                    "Va de a varias fichas a la vez (lo elegís abajo, en «Fichas a la vez»). Los "
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

            c.execute("""SELECT COUNT(*) FROM productos WHERE imagen_url IS NULL
                         AND foto_busqueda_estado IN ('sin_foto', 'fallo')""")
            marcados_sin_foto = c.fetchone()[0]
            if marcados_sin_foto:
                st.caption(
                    f"🔕 {marcados_sin_foto:,} código(s) quedaron marcados como «la ficha no tiene foto» "
                    "(o fallaron tres días) y ya no se vuelven a consultar."
                )
                if st.button("🔄 Volver a probar esos códigos"):
                    avisar("success", f"Se rehabilitaron {reintentar_codigos_sin_foto()} código(s).")
                    st.rerun()

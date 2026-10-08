"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/.

🗂️ Administrar → 🧹 Mantenimiento → 🧠 Calidad y aprendizaje: sus herramientas, en el orden
en que se muestran. Corre después de pantallas/mantenimiento.py, que elige el grupo."""

# ============================================================
# MANTENIMIENTO → CALIDAD Y APRENDIZAJE
# ============================================================
if pagina == PAGINAS[3]:
    if sub_admin == SUB_ADMIN[4]:
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
                st.info(f"Hay {miles(sin_puntuar)} vínculo(s) sin puntuar de {miles(total_eq)}. "
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
                                        text=f"Puntuando {miles(hechos)} de {miles(pendientes)}...")
                    if hechos >= pendientes:
                        break
                barra_conf.empty()
                invalidar_salud()
                avisar("success", f"Se puntuaron {miles(hechos)} vínculo(s). El buscador ya lo está "
                                  "usando.")
                st.rerun()
            if candado('volver a puntuar todos los vínculos', total_eq and st.button("♻️ Volver a puntuar TODO", help="Los puntajes cambian cuando aparece evidencia nueva " "—ventas que confirman un reemplazo, decisiones que " "tomaste al revisar—. Esto los recalcula de cero."), 'volver_a_puntuar_todos_los_v_nculo'):
                barra_re = st.progress(0.0, text="Recalculando...")
                n = recalcular_confianzas(
                    limite=max(total_eq, 1), solo_faltantes=False,
                    progreso=lambda i, t: barra_re.progress(min(i / max(t, 1), 1.0),
                                                            text=f"Recalculando {miles(i)} de {miles(t)}..."))
                barra_re.empty()
                invalidar_salud()
                avisar("success", f"Se recalcularon {miles(n)} vínculo(s).")
                st.rerun()
            # DE DÓNDE SALEN LOS VÍNCULOS: lo que aporta cada origen y cuántos productos quedan
            # unidos solo por pistas. Ver vinculos_por_origen().
            if seccion_plegable("🧭 De dónde salen los vínculos", key="vinculos_por_origen"):
                try:
                    _por_origen, _solo_pistas = vinculos_por_origen()
                except sqlite3.Error as _err:
                    anotar_error("vinculos_por_origen", _err)
                    _por_origen, _solo_pistas = [], 0
                st.dataframe(_por_origen, width="stretch", hide_index=True)
                st.caption(
                    "**Fuente** es quien conoce la pieza y lo declara (la lista del proveedor, el "
                    "catálogo del fabricante, una persona); **pista**, que se parecen las "
                    "descripciones o van en el mismo auto. "
                    + (f"**{miles(_solo_pistas)} producto(s)** están unidos a otros solo por "
                       "pistas: ninguno de sus vínculos lo declara una fuente."
                       if _solo_pistas else "Todos los productos vinculados tienen al menos "
                                            "un vínculo que declara una fuente."))
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
                ayuda(
                    "Si algún patrón no te cierra, corregilo revisando algunos vínculos de esa "
                    "combinación al revés: la app se reajusta sola con las decisiones nuevas."
                )

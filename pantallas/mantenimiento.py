"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/.

🗂️ Administrar → 🧹 Mantenimiento: lo de arriba de todo (borrar un producto puntual, el
buscador de herramientas, lo que corre solo) y la elección del grupo. Cada grupo está en su
propio archivo, mantenimiento_<grupo>.py: antes eran 2.500 renglones en administrar.py, con
las herramientas de un mismo grupo repartidas en tramos intercalados con las de otros."""

# ============================================================
# MANTENIMIENTO
# ============================================================
if pagina == PAGINAS[3]:
    if sub_admin == SUB_ADMIN[4]:
        st.markdown("**🗑️ Eliminar un producto puntual**")
        ayuda(
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
        # Arriba de los grupos: es lo que corre solo, y el lugar donde se le pide que vuelva a
        # buscar. Ver mostrar_panel_de_carga_automatica().
        mostrar_panel_de_carga_automatica()

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

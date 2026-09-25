"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/."""

# ============================================================
# VINCULAR MANUAL
# ============================================================
def vincular_grupo_equivalencias(productos_info, nivel, nota, verificar):
    """Crea (o reutiliza) cada producto de la lista y los vincula a TODOS entre sí — así se puede
    armar de una un grupo de equivalencias con productos de varios proveedores distintos,
    en vez de tener que ir vinculando de a pares."""
    ids = []
    with db_lock:
        for p in productos_info:
            clean = sanitizar(p["codigo"])
            marca_id = get_or_create_marca(p["marca"])
            pid = get_or_create_producto(
                p["codigo"].strip(), clean, p.get("descripcion", "").strip(),
                marca_id, p.get("imagen_url", "").strip() or None
            )
            ids.append(pid)
        v = 1 if verificar else 0
        # Cada par UNA vez. Recorría i contra j y j contra i, así que tres productos dejaban
        # seis filas —las dos direcciones de cada par— y la pantalla decía «6 relaciones
        # creadas» cuando eran tres. Era el otro lugar de donde salían las equivalencias
        # anotadas dos veces.
        hechos = set()
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                par = (min(ids[i], ids[j]), max(ids[i], ids[j]))
                if ids[i] == ids[j] or par in hechos:
                    continue
                _guardar_equivalencia_una_vez(par[0], par[1], v, nivel, nota.strip())
                hechos.add(par)
        conn.commit()
    return len(set(ids)), len(hechos)


if pagina == PAGINAS[1]:
    st.subheader("Vincular varios códigos como equivalentes")

    # Antes de vincular a mano conviene saber POR QUÉ no están relacionados: puede que ya lo
    # estén y no se vean por el límite de saltos, que el vínculo esté esperando aprobación, o
    # que alguien lo haya rechazado. Vincular a mano sin mirar eso tapa el problema de fondo.
    with st.expander("🔎 ¿Por qué estos dos códigos no se relacionan?"):
        st.caption("Poné un código de cada proveedor y te digo qué está pasando con ese par.")
        dg1, dg2 = cols(2)
        _diag_a = dg1.text_input("Un código:", key="diag_a", placeholder="El de un proveedor")
        _diag_b = dg2.text_input("El otro:", key="diag_b", placeholder="El del otro proveedor")
        if st.button("Revisar el par", disabled=not (_diag_a.strip() and _diag_b.strip())):
            for _nivel, _texto in diagnostico_par(_diag_a, _diag_b):
                {"ok": st.success, "aviso": st.warning,
                 "error": st.error}.get(_nivel, st.info)(_texto)

    explicar(
        "Armá un grupo de códigos — de la marca/proveedor que sea, se pueden mezclar — y "
        "vinculalos todos entre sí de una sola vez.",
        "Antes había que hacerlo de a pares; ahora si tenés 5 productos de 5 proveedores "
        "distintos que son lo mismo, los sumás todos a la tanda y los vinculás juntos."
    )

    c.execute("SELECT id, nombre FROM marcas ORDER BY nombre")
    nombres_marcas = [m["nombre"] for m in c.fetchall()]

    if "grupo_equivalencia" not in st.session_state:
        st.session_state["grupo_equivalencia"] = []

    # Si se vino desde "Productos sin equivalencias" (pestaña Administrar) con un código para
    # precargar, hay que fijar estos valores ANTES de crear los widgets de abajo — si se hace
    # después de que ya se dibujaron en pantalla, Streamlit tira un error.
    if "vincular_pendiente" in st.session_state:
        pendiente = st.session_state.pop("vincular_pendiente")
        st.session_state["nuevo_codigo_grupo"] = pendiente.get("cod_a", "")
        st.session_state["nueva_desc_grupo"] = pendiente.get("desc_a", "")
        if pendiente.get("marca_a") in nombres_marcas:
            st.session_state["nueva_marca_opcion_grupo"] = pendiente["marca_a"]

    st.markdown("**➕ Agregar un código a la tanda**")
    cg1, cg2 = st.columns(2)
    nuevo_codigo = cg1.text_input("Código", key="nuevo_codigo_grupo")
    marca_opcion = cg2.selectbox("Marca", nombres_marcas + ["➕ Nueva marca..."], key="nueva_marca_opcion_grupo")
    nueva_marca = st.text_input("Nombre de la nueva marca", key="nueva_marca_texto_grupo") \
        if marca_opcion == "➕ Nueva marca..." else marca_opcion
    cg3, cg4 = st.columns(2)
    nueva_desc = cg3.text_input("Descripción (opcional)", key="nueva_desc_grupo")
    nueva_img = cg4.text_input("URL de foto (opcional)", key="nueva_img_grupo", placeholder="https://...")

    if st.button("➕ Agregar a la tanda"):
        clean = sanitizar(nuevo_codigo)
        if not clean:
            st.warning("Completá el código.")
        elif not nueva_marca or not nueva_marca.strip():
            st.warning("Completá la marca.")
        else:
            ya_esta = any(
                sanitizar(it["codigo"]) == clean and it["marca"].strip().upper() == nueva_marca.strip().upper()
                for it in st.session_state["grupo_equivalencia"]
            )
            if ya_esta:
                st.warning("Ese código con esa marca ya está en la tanda.")
            else:
                st.session_state["grupo_equivalencia"].append({
                    "codigo": nuevo_codigo.strip(), "marca": nueva_marca.strip(),
                    "descripcion": nueva_desc.strip(), "imagen_url": nueva_img.strip()
                })
                for k in ["nuevo_codigo_grupo", "nueva_desc_grupo", "nueva_img_grupo"]:
                    st.session_state.pop(k, None)
                st.rerun()

    grupo = st.session_state["grupo_equivalencia"]
    if grupo:
        st.markdown(f"**📋 Tanda actual ({len(grupo)} código{'s' if len(grupo) != 1 else ''}):**")
        for i, it in enumerate(grupo):
            colg1, colg2 = st.columns([5, 1])
            colg1.write(f"{it['marca']}: {it['codigo']}" + (f" — {it['descripcion']}" if it['descripcion'] else ""))
            colg2.button("🗑️", key=f"quitar_grupo_{i}",
                          on_click=quitar_item_lista_sesion, args=("grupo_equivalencia", i))

        st.markdown("---")
        nivel_equiv = st.selectbox(
            "Nivel de equivalencia (aplica a todo el grupo):",
            ["Exacta", "Reemplazo con modificación", "Solo alternativa de menor calidad"],
            help="Qué tan intercambiables son en la práctica."
        )
        nota_tecnica = st.text_input(
            "Nota técnica (opcional, aplica a todo el grupo):",
            placeholder="Ej: Equivale pero requiere cambiar la ficha eléctrica"
        )
        verificar = st.checkbox("✅ Marcar como verificada", value=True,
                                 help="Verificada = confirmaste vos mismo que son intercambiables.")

        if len(grupo) < 2:
            st.info("Agregá al menos 2 códigos a la tanda para poder vincularlos.")
        elif st.button(f"🔗 Vincular los {len(grupo)} códigos entre sí", type="primary"):
            cantidad_prod, cantidad_pares = vincular_grupo_equivalencias(grupo, nivel_equiv, nota_tecnica, verificar)
            st.success(f"Listo: {cantidad_prod} productos quedaron vinculados entre sí ({cantidad_pares} relaciones creadas).")
            st.session_state["grupo_equivalencia"] = []
            st.rerun()
    else:
        st.caption("Todavía no agregaste ningún código a la tanda.")

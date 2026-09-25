"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/."""

# ============================================================
# ESTADÍSTICAS
# ============================================================
if pagina == PAGINAS[4]:
    st.subheader("📊 Estadísticas")

    if st.session_state.get("sub_stats") not in SUB_STATS:
        st.session_state["sub_stats"] = SUB_STATS[0]
    st.radio("Sub-sección:", SUB_STATS, key="sub_stats", horizontal=True,
             label_visibility="collapsed")
    sub_stats = st.session_state["sub_stats"]

    if sub_stats == SUB_STATS[0]:
        st.subheader("Estadísticas generales")

        c.execute("SELECT COUNT(*) FROM marcas")
        total_marcas = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM productos")
        total_productos = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM equivalencias")
        total_equiv = c.fetchone()[0]

        m1, m2, m3 = st.columns(3)
        m1.metric("Marcas registradas", total_marcas)
        m2.metric("Códigos cargados", total_productos)
        m3.metric("Vínculos de equivalencia", total_equiv // 2 if total_equiv else 0)

        st.markdown("---")
        c.execute("""SELECT m.nombre, COUNT(p.id) AS productos
                     FROM marcas m LEFT JOIN productos p ON p.marca_id = m.id
                     GROUP BY m.id ORDER BY productos DESC LIMIT 15""")
        top_marcas = c.fetchall()
        if top_marcas:
            st.markdown("---")
            st.markdown("**📊 Top marcas por cantidad de códigos cargados**")
            chart_data = {"Marca": [t["nombre"] for t in top_marcas],
                           "Productos": [t["productos"] for t in top_marcas]}
            st.bar_chart(chart_data, x="Marca", y="Productos")

        st.markdown("---")
        st.markdown("**🤖 Uso de las funciones de IA (últimos 30 días)**")
        st.caption(
            "Las primeras 4 funciones usan una API key; en el peor caso fallan por límite de uso y "
            "hay que reintentar. 'Generar imagen orientativa' usa una key aparte, configurada por separado."
        )
        uso_ia_actual = resumen_uso_ia()
        if uso_ia_actual:
            st.dataframe(uso_ia_actual, width="stretch", hide_index=True)
        else:
            st.caption("Todavía no se usó ninguna función de IA.")

    if sub_stats == SUB_STATS[1]:
        st.markdown("**Historial de importaciones**")
        c.execute("""SELECT marca AS Marca, archivo AS Archivo, filas_cargadas AS Cargadas,
                     filas_omitidas AS Omitidas, fecha AS Fecha FROM importaciones
                     ORDER BY fecha DESC LIMIT 20""")
        imports = filas_a_listas(c)
        if imports:
            st.dataframe(imports, width="stretch", hide_index=True)
        else:
            st.caption("Todavía no se registraron importaciones.")

    if sub_stats == SUB_STATS[2]:
        cantidad_fotos, mb_fotos = peso_de_las_fotos()
        c.execute("SELECT COUNT(*) FROM productos")
        total_prod_backup = c.fetchone()[0]

        st.markdown("**🗄️ Backup de la base**")

        # Lo primero: cuánto se perdería HOY. Es la diferencia entre lo que hay en el disco (que
        # se borra) y lo que hay en el repositorio (que sobrevive).
        _riesgo = None
        try:
            _riesgo = cuanto_perderias_si_reinicia()
        except Exception as _err:
            anotar_error("nivel principal", _err)
            pass
        if _riesgo:
            if not _riesgo["hay_semilla"]:
                st.error(
                    f"🔴 **No hay copia en el repositorio.** Tenés "
                    f"{_riesgo['productos_ahora']:,} producto(s) viviendo solo en el disco del "
                    "servidor, que se borra en cada reinicio. **Hoy un reinicio borra todo.**"
                )
            elif _riesgo["en_riesgo"]:
                st.warning(
                    f"⚠️ **{_riesgo['en_riesgo']:,} producto(s) y "
                    f"{_riesgo['equivalencias_en_riesgo']:,} vínculo(s) viven solo en el disco.**\n\n"
                    f"La copia del repositorio es del {_riesgo['fecha_semilla']} y tiene "
                    f"{_riesgo['productos_semilla']:,} productos; hoy tenés "
                    f"{_riesgo['productos_ahora']:,}. Si el servidor reinicia, esa diferencia "
                    "se pierde."
                )
            elif _riesgo.get("en_github"):
                st.success(
                    f"✅ **La copia en GitHub se actualiza sola.** Cada {MINUTOS_ENTRE_COPIAS} "
                    "minutos la app mira si cambió algo y, si cambió, la sube. Si el servidor se "
                    f"reinicia, se pierde como mucho lo de los últimos {MINUTOS_ENTRE_COPIAS} "
                    f"minutos. Última copia subida: {_riesgo['fecha_semilla']}."
                )
            else:
                st.success(
                    f"✅ La copia del repositorio está al día ({_riesgo['productos_semilla']:,} "
                    f"productos, del {_riesgo['fecha_semilla']}). Un reinicio no te haría perder nada."
                )
            # Si están los secretos de GitHub, se puede resolver de un botón en vez de a mano.
            _cfg_gh = config_github()
            if _cfg_gh:
                st.info(
                    f"🔗 **Subida automática configurada** hacia `{_cfg_gh['repo']}`. "
                    "No hace falta bajar nada ni entrar a GitHub."
                )
                _ult_gh = obtener_config("ultimo_backup_github", "")
                if _ult_gh:
                    st.caption(f"Última subida automática: {_ult_gh}")
                _err_gh = obtener_config("ultimo_backup_github_error", "")
                if _err_gh:
                    st.error(f"⚠️ El último intento de subir la copia falló: {_err_gh}")
                if st.button("☁️ Subir el backup al repositorio ahora", type="primary"):
                    with st.spinner("Armando la copia y subiéndola..."):
                        _ok, _msg = subir_la_copia_si_cambio(aunque_no_haya_cambios=True)
                    if _ok:
                        invalidar_salud()
                        avisar("success", f"☁️ {_msg}")
                        st.rerun()
                    else:
                        st.error(_msg)
            else:
                explicar(
                    "Se puede automatizar: que la app suba el backup sola al repositorio.",
                    "En **Settings → Secrets** de Streamlit Cloud, agregá estas dos líneas:\n\n"
                    "```\ngithub_token = \"ghp_tu_token\"\ngithub_repo = \"usuario/repositorio\"\n"
                    "```\n\nEl token se saca en GitHub → Settings → Developer settings → "
                    "Personal access tokens, con permiso de escritura (`Contents: read and "
                    "write`) sobre ese repositorio.\n\nCon eso configurado la copia se sube sola "
                    f"cada vez que hay cambios (se mira cada {MINUTOS_ENTRE_COPIAS} minutos), "
                    "a una rama aparte, `copia-de-seguridad`, y si el servidor se reinicia la "
                    "app la baja sola al arrancar. También aparece un botón para subirla ya. "
                    "Mientras no lo configures, hay que hacerlo a mano como hasta ahora."
                )

            # Con la subida automática andando, esto ya no corresponde: nadie tiene que subir
            # nada a mano.
            if not _cfg_gh:
                explicar(
                    "Bajar el backup no alcanza: hay que subirlo al repositorio.",
                    "El servidor borra su disco cada vez que la app se reinicia o se "
                    "redespliega. Lo único que sobrevive son los archivos del **repositorio de "
                    "GitHub**, porque son parte del despliegue.\n\nPor eso el backup se restaura "
                    "solo desde un archivo llamado `datos_iniciales.db` que tiene que estar ahí. "
                    "Bajarlo a tu teléfono te sirve a vos, pero **no protege a la app**: hasta que "
                    "ese archivo no esté en GitHub, un reinicio se lleva todo lo cargado desde la "
                    "última vez.\n\n**Los pasos:** bajá el backup de acá abajo → entrá al "
                    "repositorio en GitHub → subí el archivo con el nombre exacto "
                    "`datos_iniciales.db`, reemplazando el que está."
                )
            st.markdown("---")

        if cantidad_fotos:
            st.error(
                "🔴 **Importante sobre las fotos.** El hosting borra el disco cada vez que la app se "
                "reinicia o se redespliega, y al arrancar se restaura sola desde el `datos_iniciales.db` "
                "del repositorio. Ese archivo lo genera el **backup sin fotos**, que las saca a "
                "propósito para no pasarse del límite de GitHub. Resultado: **cada reinicio te borra "
                "todas las fotos**, y por eso la búsqueda por parecido aparece sin nada para comparar."
            )
            with st.expander("¿Y entonces qué hago con las fotos?"):
                st.markdown(
                    "- **Si son pocas y el archivo entra en GitHub (menos de 100 MB):** usá el "
                    "**backup completo** de acá abajo y subilo al repositorio renombrado a "
                    "`datos_iniciales.db`. Ahí sí sobreviven los reinicios.\n"
                    "- **Si ya no entra:** subí el backup sin fotos (para no perder el catálogo) y "
                    "recuperá las fotos después desde **Mantenimiento → Traer fotos en tanda**, que "
                    "las vuelve a bajar de las fichas de los proveedores sin cargarlas a mano.\n"
                    "- **Lo más prolijo a futuro:** guardar las fotos por dirección web en vez de "
                    "adentro de la base, y dejar cargada la dirección del catálogo de cada marca en "
                    "**Administrar → Marcas**. Así el backup queda liviano y las fotos se vuelven a "
                    "traer solas."
                )

        if mb_fotos > 60:
            st.warning(
                f"⚠️ Las fotos ({cantidad_fotos} productos) ocupan unos {mb_fotos:,.0f} MB. "
                "GitHub no acepta archivos de más de 100 MB, así que para la copia del repositorio "
                "conviene usar el **backup sin fotos** de acá abajo."
            )
        elif cantidad_fotos:
            st.caption(f"Las fotos de {cantidad_fotos} producto(s) ocupan {mb_fotos:,.1f} MB de la base.")

        cbk1, cbk2 = st.columns(2)
        with cbk1:
            st.markdown("*Completo (con fotos)*")
            if st.button("🗄️ Preparar backup completo"):
                with st.spinner("Armando..."):
                    st.session_state["backup_bytes"] = generar_backup_completo()
            if "backup_bytes" in st.session_state:
                st.download_button(
                    f"⬇️ Descargar ({len(st.session_state['backup_bytes'])/(1024*1024):,.0f} MB)",
                    data=st.session_state["backup_bytes"],
                    file_name=f"equivalencias_backup_{datetime.now():%Y%m%d}.db",
                    on_click=marcar_backup_hecho
                )
        with cbk2:
            st.markdown("*Liviano (sin fotos) — para el repositorio*")
            if st.button("🪶 Preparar backup sin fotos"):
                with st.spinner("Armando..."):
                    st.session_state["backup_liviano"] = generar_backup_sin_fotos()
            if "backup_liviano" in st.session_state:
                st.download_button(
                    f"⬇️ Descargar ({len(st.session_state['backup_liviano'])/(1024*1024):,.1f} MB)",
                    data=st.session_state["backup_liviano"],
                    file_name="datos_iniciales.db",
                    help="Ya viene con el nombre listo para subir al repositorio",
                    on_click=marcar_backup_hecho
                )
                st.caption(
                    f"Lleva los {total_prod_backup} productos con precios, equivalencias, vehículos e "
                    "historial. ⚠️ **No lleva las fotos**: si restaurás desde este archivo hay que "
                    "volver a traerlas desde Mantenimiento."
                )

        st.markdown("---")
        st.markdown("**📦 Exportar configuración (sin el catálogo de productos)**")
        st.caption(
            "Combos de repuestos, códigos DTC y fabricantes por WMI en un solo archivo de texto — útil "
            "como respaldo liviano aparte del backup completo, o para copiarle la configuración a otra "
            "sucursal sin duplicar todo el catálogo de productos."
        )
        st.download_button(
            "⬇️ Descargar configuración (.txt)",
            data=exportar_configuracion_txt(),
            file_name=f"configuracion_{datetime.now():%Y%m%d}.txt",
            mime="text/plain"
        )

        st.markdown("---")
        st.markdown("**🛡️ Copia permanente (para que no se borre nunca más)**")
        explicar(
            "El servidor borra el disco de la app cada vez que se redespliega o se reinicia — por "
            "eso se pierde la base.",
            "Pero los archivos que están en el repositorio de GitHub **sí** sobreviven, porque "
            "forman parte del despliegue. Con esto se aprovecha eso:"
        )
        st.markdown("""
1. Tocá **🪶 Preparar backup sin fotos** acá arriba y descargalo (ya viene con el nombre correcto).
2. Subilo al repositorio de GitHub, al lado de `app.py`.

Listo: cada vez que el servidor borre el disco, la app se levanta sola con esos datos.
Repetí los 2 pasos cada tanto (una vez por semana, o después de cargar una lista grande).

**¿Por qué sin fotos?** Porque son lo que más pesa y GitHub rechaza archivos de más de 100 MB.
Sin ellas el archivo queda chico, y las fotos se vuelven a traer solas desde
Administrar → Mantenimiento.
        """)
        _en_repo = semilla_del_repositorio()
        if _en_repo:
            try:
                marca_tiempo = datetime.fromtimestamp(os.path.getmtime(_en_repo))
                peso = os.path.getsize(_en_repo) / (1024 * 1024)
                st.success(f"✅ Hay una copia en el repositorio ({peso:,.1f} MB, del {marca_tiempo:%d/%m/%Y}).")
            except Exception as _err:
                anotar_error("nivel principal", _err)
                st.success("✅ Hay una copia en el repositorio.")
        else:
            st.warning(
                "⚠️ Todavía no hay ninguna copia en el repositorio. Mientras no la subas, cada "
                "redespliegue borra todo lo cargado."
            )

        st.markdown("---")
        st.markdown("**♻️ Restaurar desde un backup**")
        st.caption(
            "⚠️ Esto reemplaza TODA la base actual por la del archivo que subas. "
            "Usalo si el hosting se reinició y perdiste datos, o para volver a un backup anterior."
        )
        archivo_restaurar = subir_archivo("Subí un archivo .db de backup:", ["db"], "restaurar")
        if archivo_restaurar:
            archivo_listo(archivo_restaurar, "backup")
            boton_otro_archivo("restaurar", "🗑️ Usar otro backup", key="otro_backup")
        confirmar_restore = st.checkbox("Entiendo que esto borra los datos actuales y los reemplaza")
        if candado('restaurar un backup', st.button("♻️ Restaurar backup", disabled=not (archivo_restaurar and confirmar_restore)), 'restaurar_un_backup'):
            restaurar_backup(archivo_restaurar)
            avisar("success", "Backup restaurado. Recargando...")
            st.rerun()

    if sub_stats == SUB_STATS[3]:
        st.markdown("**🧮 Auditoría diaria de stock (muestreo aleatorio)**")
        st.caption(
            "Todas las mañanas se puede generar una lista corta de productos al azar (priorizando favoritos "
            "y los que tienen precio cargado) para contarlos a mano en 5 minutos y detectar descalces antes de que se acumulen."
        )
        cant_auditoria = st.number_input("Cantidad de productos a auditar hoy:", min_value=3, max_value=20, value=8, step=1)
        if st.button("🎲 Generar auditoría de hoy"):
            generada = generar_auditoria_hoy(cant_auditoria)
            if generada:
                avisar("success", "Auditoría de hoy generada.")
                st.rerun()
            else:
                st.info("Ya había una auditoría generada para hoy (ver abajo).")

        auditoria_hoy = listar_auditoria_hoy()
        if auditoria_hoy:
            for item in auditoria_hoy:
                colA1, colA2, colA3 = st.columns([3, 1.5, 1])
                colA1.write(f"**{item['Codigo']}** ({item['Marca']}) — sistema: {item['Stock sistema']}")
                if item["Resuelto"]:
                    signo = "✅ OK" if item["Diferencia"] == 0 else f"⚠️ Diferencia: {item['Diferencia']:+d}"
                    colA2.write(f"Contado: {item['Stock contado']} — {signo}")
                else:
                    contado = colA2.number_input("Contado", min_value=0, step=1, key=f"conteo_{item['ID_auditoria']}",
                                                  label_visibility="collapsed")
                    if colA3.button("💾", key=f"guardar_conteo_{item['ID_auditoria']}"):
                        registrar_conteo_auditoria(item["ID_auditoria"], contado)
                        st.rerun()
        else:
            st.caption("Todavía no generaste la auditoría de hoy.")

        st.markdown("---")
        st.markdown("**📦 Matriz ABC — ubicación sugerida en depósito**")
        st.caption(
            "Como la app no tiene un módulo de ventas, la rotación se aproxima con la cantidad de veces que "
            "se buscó cada código. Los más buscados (A) conviene tenerlos más a mano."
        )
        matriz = calcular_matriz_abc()
        if matriz:
            st.dataframe(quitar_id(matriz), width="stretch", hide_index=True)
            st.caption("Para cargar o corregir la ubicación de un producto, andá a la pestaña 'Administrar'.")
        else:
            st.caption("Todavía no hay suficientes búsquedas registradas para armar la matriz.")

    if sub_stats == SUB_STATS[4]:
        st.markdown("**🔎 Códigos buscados sin resultado**")
        st.caption("Qué te están pidiendo los clientes que todavía no tenés cargado.")
        # Lo primero, lo que YA ESTÁ: de todo lo de esta pantalla es lo único que es una venta
        # a un llamado de distancia. Ver busquedas_fallidas_que_ahora_estan().
        _ya_estan = busquedas_fallidas_que_ahora_estan()
        if _ya_estan:
            st.success(f"✅ **{len(_ya_estan)} de los códigos que te pidieron y no tenías YA "
                       "ESTÁN cargados.** Entraron con alguna lista después de que los "
                       "buscaron. Si te acordás quién los pidió, es un llamado.")
            st.dataframe(_ya_estan, width="stretch", hide_index=True)
        fallidas = listar_busquedas_sin_resultado()
        if fallidas:
            _ya = {sanitizar(x["Buscado"]) for x in _ya_estan}
            for f in fallidas:
                f["¿Hoy?"] = "✅ ya está" if sanitizar(f["Buscado"]) in _ya else "—"
            st.dataframe(fallidas, width="stretch", hide_index=True)
        else:
            st.caption("Sin registros todavía.")

    if sub_stats == SUB_STATS[5]:
        st.markdown("**⏳ Lo que se va a acabar**")
        explicar(
            "Calculado con el ritmo real de venta de cada producto y el stock que queda.",
            "La reposición hasta ahora era 100% manual: alguien tenía que acordarse de tocar "
            "«Pedir». Y de lo que uno no se acuerda es justamente de lo que se vende parejo "
            "todos los días — el filtro común que nadie mira hasta que un cliente lo pide y no "
            "está.\n\nSe ignora lo que se vendió una o dos veces: con eso no se puede calcular "
            "un ritmo, es ruido."
        )
        cq1, cq2 = cols(2)
        st.session_state.setdefault("dias_aviso_quiebre", 21)
        dias_aviso = cq1.select_slider("Avisar cuando queden menos de:",
                                        options=[7, 14, 21, 30, 60],
                                        format_func=lambda x: f"{x} días",
                                        key="dias_aviso_quiebre")
        st.session_state.setdefault("min_ventas_quiebre", 3)
        min_ventas = cq2.select_slider("Contar solo lo vendido al menos:",
                                        options=[3, 5, 10, 20],
                                        format_func=lambda x: f"{x} veces",
                                        key="min_ventas_quiebre")
        try:
            por_quebrar = productos_por_quebrar(int(dias_aviso), int(min_ventas))
        except sqlite3.OperationalError as _err:
            anotar_error("nivel principal", _err)
            por_quebrar = []
        if not por_quebrar:
            st.success("✅ Nada a punto de quebrarse, según lo que se vendió estos meses.")
        else:
            sin_stock = [x for x in por_quebrar if x["Stock"] <= 0]
            if sin_stock:
                st.error(f"🔴 {len(sin_stock)} producto(s) que se venden seguido están **en cero**.")
            st.dataframe(quitar_id(por_quebrar), width="stretch", hide_index=True)
            etiquetas_q = {f"{x['Código']} ({x['Marca']}) — {x['Se acaba en']}": x["_id"]
                           for x in por_quebrar}
            elegidos_q = st.multiselect("Marcar para pedir:", list(etiquetas_q.keys()),
                                         key="quiebre_a_pedir", placeholder="Elegí uno o más")
            if elegidos_q and st.button(f"📌 Marcar {len(elegidos_q)} para reposición"):
                for e in elegidos_q:
                    solicitar_reposicion(etiquetas_q[e])
                avisar("success", f"{len(elegidos_q)} producto(s) marcados para pedir.")
                st.rerun()

        st.markdown("---")
        # Lo que marcaron para pedir va acá arriba, pegado a «lo que se va a acabar»: es lo
        # que se viene a buscar a esta pantalla. Estaba al final, después de los aumentos,
        # los clavos y los códigos reemplazados; en el celular, casi cinco pantallas abajo.
        st.markdown("**🙋 Pedidos marcados por empleados**")
        st.caption(
            "Cuando alguien busca algo y toca '📌 Pedir' en el buscador, aparece acá para que decidas "
            "qué comprarle a cada proveedor."
        )
        pedidos = listar_pedidos_reposicion("pendiente")
        seleccionados = []
        if pedidos:
            for p in pedidos:
                colp1, colp2, colp3 = st.columns([4, 1, 1])
                stock_txt = p["Stock actual"] if p["Stock actual"] is not None else "s/d"
                marcado = colp1.checkbox(
                    f"{p['Marca']} - {p['Codigo']} — {p['Descripcion'] or ''} "
                    f"(stock: {stock_txt}, pedido {p['Veces pedido']}x, último: {p['Último en pedirlo']})",
                    key=f"chk_pedido_{p['ID']}"
                )
                if marcado:
                    seleccionados.append(p)
                # on_click en vez de "if boton: accion + st.rerun()": el callback corre ANTES de
                # que Streamlit refresque la página, así la lista ya sale actualizada sin tener que
                # forzar un st.rerun() — que es lo que hacía perder la pestaña y volver al inicio.
                colp2.button("✅", key=f"resuelto_{p['ID']}", help="Marcar como resuelto",
                              on_click=marcar_pedido_resuelto, args=(p["ID"],))
                colp3.button("🗑️", key=f"descartar_{p['ID']}", help="Descartar (no hace falta pedirlo)",
                              on_click=descartar_pedido_reposicion, args=(p["ID"],))
        else:
            st.caption("Ningún empleado marcó nada para pedir todavía.")

        st.markdown("---")
        st.markdown("**📦 Favoritos con poco stock**")
        umbral_stock = st.number_input("Alertar cuando el stock sea menor o igual a:", min_value=0, value=2, step=1,
                                        key="umbral_para_pedir")
        stock_bajo = listar_favoritos_stock_bajo(umbral_stock)
        if stock_bajo:
            for f in stock_bajo:
                stock_txt_f = f["Stock"] if f["Stock"] is not None else "s/d"
                marcado_f = st.checkbox(
                    f"{f['Marca']} - {f['Codigo']} — {f['Descripcion'] or ''} (stock: {stock_txt_f})",
                    key=f"chk_stockbajo_{f['ID']}"
                )
                if marcado_f:
                    seleccionados.append(f)
        else:
            st.caption("Ningún favorito con stock bajo por ahora.")

        if seleccionados:
            st.markdown("---")
            st.markdown(f"**📲 Armar mensaje para el proveedor ({len(seleccionados)} ítem(s) elegidos)**")
            por_marca = {}
            for item in seleccionados:
                por_marca.setdefault(item["Marca"], []).append(item)
            for marca, items in por_marca.items():
                lineas_msg = [f"Hola! Necesito reponer estos productos de {marca}:"]
                for it in items:
                    stock_it = it.get("Stock actual", it.get("Stock"))
                    lineas_msg.append(
                        f"- {it['Codigo']} ({it.get('Descripcion') or ''}) — "
                        f"quedan {stock_it if stock_it is not None else 's/d'}"
                    )
                mensaje_reposicion = "\n".join(lineas_msg)
                with st.expander(f"📨 {marca} ({len(items)} ítem(s))"):
                    st.text_area("Mensaje:", value=mensaje_reposicion, height=120, key=f"msg_repo_{marca}")
                    url_wa_repo = "https://wa.me/?text=" + quote(mensaje_reposicion)
                    st.link_button(f"📲 Abrir WhatsApp para {marca}", url_wa_repo, key=f"wa_repo_{marca}")

        st.markdown("---")
        st.markdown("**📈 Cuánto te aumentó cada proveedor**")
        explicar(
            "Medido sobre tu propio historial de precios, no sobre lo que dicen las listas.",
            "La app viene guardando cada cambio de precio y solo lo mostraba producto por "
            "producto. Pero la pregunta que importa no es cuánto aumentó un filtro, sino cuánto "
            "aumentó el proveedor: con eso se decide a quién comprarle y con quién hay que "
            "hablar.\n\nSe usa la **mediana**, no el promedio: un solo precio mal cargado —de "
            "esos que llegan con el separador de decimales al revés— alcanza para inflar un "
            "promedio y hacer parecer que un proveedor aumentó 400%."
        )
        st.session_state.setdefault("meses_variacion", 6)
        meses_var = st.select_slider("Comparar contra los precios de hace:",
                                      options=[3, 6, 12, 24],
                                      format_func=lambda x: f"{x} meses",
                                      key="meses_variacion")
        try:
            variacion = variacion_de_precios_por_marca(int(meses_var))
        except sqlite3.OperationalError as _err:
            anotar_error("nivel principal", _err)
            variacion = []
        if not variacion:
            st.caption(
                "Hace falta haber importado precios de una misma marca en dos momentos "
                "distintos para poder comparar. Aparece solo a medida que vas cargando listas."
            )
        else:
            st.dataframe(quitar_id(variacion), width="stretch", hide_index=True)
            st.caption("Ordenado de mayor a menor aumento.")

        st.markdown("---")
        st.markdown("**💰 A quién conviene comprarle**")
        explicar(
            "Comparando solo repuestos que son equivalentes entre sí.",
            "Comparar el precio promedio de dos marcas no dice nada: una puede vender frenos "
            "caros y la otra filtros baratos. Acá cada comparación es entre dos códigos que "
            "hacen el mismo trabajo, y solo se usan los vínculos con confianza razonable — si "
            "la equivalencia es dudosa, la comparación de precios también lo es."
        )
        try:
            conviene = quien_conviene_por_rubro()
        except sqlite3.OperationalError as _err:
            anotar_error("nivel principal", _err)
            conviene = []
        if not conviene:
            st.caption(
                "Hace falta tener el mismo repuesto de dos marcas distintas, vinculados entre sí "
                "y con precio cargado en los dos."
            )
        else:
            st.dataframe(quitar_id(conviene), width="stretch", hide_index=True)

        st.markdown("---")
        st.markdown("**🧊 Clavos: lo que no se mueve**")
        explicar(
            "Stock que hace meses no se vende. Es plata dormida en el estante.",
            "Se cruza el stock con la última venta de cada producto. Ordenado por **plata "
            "parada** —precio por cantidad—, no por cuántos días lleva: 40 unidades de algo "
            "barato molestan menos que 2 de algo caro.\n\nLo que nunca se vendió cuenta solo "
            "si hace rato que está cargado: un producto que entró la semana pasada todavía no "
            "tuvo su chance."
        )
        st.session_state.setdefault("dias_clavo", 180)
        _dias_clavo = st.select_slider("Sin vender desde hace más de:",
                                        options=[90, 180, 365, 730],
                                        format_func=lambda x: f"{x} días" if x < 365
                                                              else f"{x // 365} año(s)",
                                        key="dias_clavo")
        try:
            _clavos = productos_estancados(int(_dias_clavo))
        except Exception as _err:
            anotar_error("nivel principal", _err)
            _clavos = []
        if not _clavos:
            st.success("✅ Nada estancado con ese criterio.")
        else:
            _plata = sum(x["Plata parada"] or 0 for x in _clavos)
            st.warning(f"⚠️ {len(_clavos)} producto(s) con **${_plata:,.0f}** inmovilizados.")
            st.dataframe(quitar_id([{k: v for k, v in x.items() if not k.startswith("_")}
                                     for x in _clavos]),
                          width="stretch", hide_index=True)
            st.caption(
                "Sirve para decidir una liquidación, o para priorizarlos cuando alguien pide "
                "un equivalente y tenés varios que sirven igual."
            )

        st.markdown("---")
        st.markdown("**🔄 Códigos reemplazados por el fabricante**")
        explicar(
            "Cuando un código deja de fabricarse y lo reemplaza otro.",
            "No es una equivalencia común: tiene dirección. El viejo se discontinúa y el nuevo "
            "lo reemplaza, pero no al revés.\n\nCargarlo evita la forma más tonta de perder "
            "una venta: alguien busca el código viejo, no aparece, y se le dice al cliente que "
            "no se fabrica más — cuando en realidad existe con otro número.\n\nSigue la cadena "
            "completa: si A fue reemplazado por B y B por C, buscando A te lleva hasta C."
        )
        cr1, cr2 = cols(2)
        _viejo = cr1.text_input("Código viejo:", key="reemp_viejo",
                                 placeholder="El que ya no se fabrica").strip()
        _nuevo = cr2.text_input("Lo reemplaza:", key="reemp_nuevo",
                                 placeholder="El código vigente").strip()
        _nota_r = st.text_input("Nota (opcional):", key="reemp_nota",
                                 placeholder="Ej: cambia el largo de rosca, revisar antes")
        if st.button("💾 Guardar el reemplazo", disabled=not (_viejo and _nuevo)):
            _ok_r, _msg_r = guardar_reemplazo(_viejo, _nuevo, "", _nota_r)
            if _ok_r:
                avisar("success", _msg_r)
                st.rerun()
            else:
                st.error(_msg_r)
        try:
            c.execute("""SELECT codigo_viejo AS "Ya no se fabrica",
                                codigo_nuevo AS "Lo reemplaza", nota AS "Nota",
                                substr(fecha, 1, 10) AS "Cargado"
                         FROM reemplazos_codigo ORDER BY fecha DESC LIMIT 200""")
            _lista_r = filas_a_listas(c)
        except sqlite3.OperationalError as _err:
            anotar_error("nivel principal", _err)
            _lista_r = []
        if _lista_r:
            st.dataframe(_lista_r, width="stretch", hide_index=True)

        st.markdown("---")
        st.markdown("**🚫 Puede que ya no se fabriquen**")
        explicar(
            "Códigos que faltaron en las últimas listas del proveedor.",
            "Cuando llega una lista nueva, los productos que vienen se actualizan y los que no "
            "vienen quedan intactos. Si un código faltó en las últimas listas, casi seguro el "
            "proveedor lo discontinuó o le cambió el número — pero en la base sigue figurando "
            "con su precio viejo.\n\nEso cuesta de dos formas: se cotiza algo que ya no existe "
            "y el cliente se va cuando no llega, y el stock muerto ocupa lugar sin que nadie lo "
            "note.\n\n**No son certezas.** Un producto puede faltar en una lista simplemente "
            "porque el proveedor lo mandó aparte. Son candidatos para que los mires."
        )
        st.session_state.setdefault("listas_discont", 2)
        listas_disc = st.select_slider(
            "Considerar discontinuado si faltó en las últimas:",
            options=[2, 3, 4, 5], format_func=lambda x: f"{x} listas",
            key="listas_discont",
            help="Con 2 aparecen más candidatos y más falsos; con 4 o 5, solo los que "
                 "vienen faltando hace rato."
        )
        try:
            discont, revisados_disc = productos_probablemente_discontinuados(
                listas_seguidas=int(listas_disc))
        except sqlite3.OperationalError as _err:
            anotar_error("nivel principal", _err)
            discont, revisados_disc = [], 0

        if not revisados_disc:
            st.caption(
                "Hace falta haber importado al menos 2 listas de una misma marca para poder "
                "comparar. Con una sola no hay con qué."
            )
        elif not discont:
            st.success(f"✅ De {revisados_disc:,} producto(s) revisados, ninguno faltó en las "
                        f"últimas {listas_disc} listas.")
        else:
            con_stock = [x for x in discont if (x["_stock"] or 0) > 0]
            if con_stock:
                st.warning(
                    f"⚠️ {len(con_stock)} de estos **tienen stock**. Si el proveedor ya no los "
                    "manda, eso es mercadería que conviene liquidar antes de que quede muerta."
                )
            st.dataframe(quitar_id([{k: v for k, v in x.items() if not k.startswith("_")}
                                     for x in discont]),
                          width="stretch", hide_index=True)
            st.download_button(
                "⬇️ Bajar la lista en Excel",
                data=to_excel_bytes([{k: v for k, v in x.items() if not k.startswith("_")}
                                      for x in discont]),
                file_name="posibles_discontinuados.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            st.caption(
                "Antes de dar de baja alguno, confirmalo con el proveedor: puede haberle "
                "cambiado el número y seguir existiendo con otro código."
            )

        st.markdown("---")
        if _ULTIMOS_ERRORES and es_admin():
            st.markdown("**🐞 Errores que la app se tragó**")
            explicar(
                f"{len(_ULTIMOS_ERRORES)} cosa(s) fallaron sin que nadie se enterara.",
                "Hay muchos lugares donde algo puede fallar y la app sigue igual: una tabla "
                "que todavía no existe, una función opcional que no está. Son a propósito.\n\n"
                "Pero si ahí se esconde un bug real, sin este registro nadie se entera nunca. "
                "Acá quedan anotados los últimos, con dónde y qué pasó.\n\nQue aparezcan cosas "
                "acá no significa que algo esté roto. Lo que importa es si el mismo error se "
                "repite muchas veces, o si aparece justo cuando algo no funcionó."
            )
            from collections import Counter as _Cnt
            _repetidos = _Cnt((e["donde"], e["tipo"]) for e in _ULTIMOS_ERRORES)
            st.dataframe(
                [{"Veces": v, "Dónde": d, "Tipo": t} for (d, t), v in _repetidos.most_common(15)],
                width="stretch", hide_index=True)
            if seccion_plegable("Ver el detalle de los últimos", key="detalle_errores"):
                st.dataframe(list(reversed(_ULTIMOS_ERRORES))[:40],
                              width="stretch", hide_index=True)
            st.markdown("---")

        st.markdown("**📞 Consultas de clientes**")
        explicar(
            "Lo que preguntó cada cliente y todavía no se resolvió.",
            "En el mostrador esto se anota en un papel y se pierde: el cliente dijo que lo "
            "consultaba y volvía, y cuando vuelve nadie se acuerda qué pidió ni qué precio se "
            "le dio.\n\nAcá queda con nombre, teléfono, qué pieza y a cuánto se la cotizó. "
            "Cuando llama y dice «soy el del Gol», lo buscás y tenés todo."
        )
        _ahora_hay = consultas_que_ahora_hay_en_stock()
        if _ahora_hay:
            st.success(
                f"📦 **{len(_ahora_hay)} cliente(s) esperando algo que AHORA hay en stock.** "
                "Es una venta a un llamado de distancia."
            )
            st.dataframe(quitar_id(_ahora_hay), width="stretch", hide_index=True)
            st.markdown("")

        _esperando = consultas_de_clientes()
        if not _esperando:
            st.caption("No hay consultas pendientes.")
        else:
            st.dataframe(quitar_id(_esperando), width="stretch", hide_index=True)
            _etq_cerr = {f"{x['Cliente'] or x['Teléfono'] or 'sin nombre'} — {x['Pidió']} "
                          f"({x['Días']} día/s)": x["_id"] for x in _esperando}
            _sel_cerr = st.selectbox("Cerrar una consulta:", list(_etq_cerr.keys()),
                                      key="cerrar_consulta")
            cq1, cq2 = cols(2)
            if cq1.button("✅ Vino y compró"):
                cerrar_consulta(_etq_cerr[_sel_cerr], "vendida")
                avisar("success", "Cerrada como vendida.")
                st.rerun()
            if cq2.button("🚶 No volvió"):
                cerrar_consulta(_etq_cerr[_sel_cerr], "cancelada")
                avisar("success", "Cerrada.")
                st.rerun()

        _buscar_cli = st.text_input("🔍 Buscar un cliente por nombre o teléfono:",
                                     key="buscar_cliente",
                                     placeholder="Llamó y no sabés qué había pedido")
        if _buscar_cli and len(_buscar_cli.strip()) > 2:
            _hist = historial_de_un_cliente(_buscar_cli)
            if _hist:
                st.dataframe(_hist, width="stretch", hide_index=True)
            else:
                st.caption("No hay nada anotado de ese cliente.")
        st.markdown("---")

        st.markdown("**🔒 Stock apartado en presupuestos**")
        explicar(
            "Lo que está reservado y todavía no se vendió.",
            "Con varios atendiendo a la vez, vender dos veces la misma pieza es cuestión de "
            "tiempo: uno cotiza 4 pastillas, el otro ve stock 4 y las vende.\n\nEl buscador "
            "muestra el stock **libre** cuando hay algo apartado, así nadie promete lo que ya "
            f"está comprometido. Las reservas de más de {DIAS_VENCIMIENTO_RESERVA} días se "
            "liberan solas: un presupuesto que nadie contestó no puede seguir bloqueando "
            "mercadería para siempre."
        )
        _vencidas = vencer_reservas_viejas()
        if _vencidas:
            st.caption(f"🔓 Se liberaron {_vencidas} reserva(s) que pasaron los "
                        f"{DIAS_VENCIMIENTO_RESERVA} días.")
        _reservas = reservas_activas()
        if not _reservas:
            st.caption("No hay nada apartado ahora mismo.")
        else:
            st.dataframe(quitar_id(_reservas), width="stretch", hide_index=True)
            _etq = {f"{r['Código']} ({r['Marca']}) — {r['Apartadas']} u. "
                    f"para {r['Cliente'] or 'sin nombre'}": r["_id"] for r in _reservas}
            _elegida = st.selectbox("Cerrar una reserva:", list(_etq.keys()), key="reserva_cerrar")
            rc1, rc2 = cols(2)
            if rc1.button("✅ Se vendió (descontar del stock)"):
                cerrar_reserva(_etq[_elegida], vendida=True)
                avisar("success", "Reserva cerrada y stock descontado.")
                st.rerun()
            if rc2.button("🔓 Se cayó (liberar sin descontar)"):
                cerrar_reserva(_etq[_elegida], vendida=False)
                avisar("success", "Reserva liberada.")
                st.rerun()

    if sub_stats == SUB_STATS[6]:
        st.markdown("**🔍 Revisar las equivalencias que ya están cargadas**")
        explicar(
            "Pasa las mismas alarmas por todo lo que se cargó antes (listas viejas, vínculos hechos "
            "a mano).",
            "Lo que marques como correcto no vuelve a aparecer; lo que borres queda descartado para "
            "siempre, aunque vuelvas a importar la misma lista."
        )
        if st.button("🔍 Auditar lo ya cargado"):
            with st.spinner("Revisando..."):
                st.session_state["resultado_auditoria"] = auditar_equivalencias_existentes()

        resultado_aud = st.session_state.get("resultado_auditoria")
        if resultado_aud:
            ma1, ma2, ma3, ma4 = st.columns(4)
            ma1.metric("Vínculos revisados", resultado_aud["total_revisados"])
            ma2.metric("Códigos raros", len(resultado_aud.get("codigos_malos", [])))
            ma3.metric("Conflictos", len(resultado_aud["conflictos"]))
            ma4.metric("Medidas que no dan", len(resultado_aud["por_medidas"]))

            if resultado_aud.get("quedo_corta"):
                st.warning(
                    f"⚠️ **La revisión quedó corta.** Se miraron {resultado_aud['total_revisados']:,} "
                    f"de {resultado_aud['total_en_base']:,} vínculos que hay cargados. Resolvé estos "
                    "y volvé a auditar para seguir con el resto — todavía puede haber problemas sin ver."
                )

            # 1) Códigos que no parecen códigos: lo que deja una importación mal mapeada.
            #    Va primero porque un solo producto basura ensucia decenas de vínculos.
            if resultado_aud.get("codigos_malos"):
                st.markdown("**🚫 Códigos que no parecen códigos de repuesto**")
                st.caption(
                    "Suelen venir de una importación donde la columna del código en realidad tenía "
                    "medidas, cantidades o pedazos de la descripción. Cortarles los vínculos limpia "
                    "el problema; el producto queda por si lo querés corregir a mano."
                )
                for cm in resultado_aud["codigos_malos"][:25]:
                    cc1, cc2 = st.columns([3, 1])
                    cc1.markdown(f"**{texto_para_html(cm['marca'])}** · `{cm['codigo']}` "
                                  f"— {texto_para_html(cm['motivo'])}  \n"
                                  f"<small>{cm['vinculos']} vínculo(s)</small>", unsafe_allow_html=True)
                    cc2.button("✂️ Cortar sus vínculos", key=f"cortar_malo_{cm['id']}",
                                on_click=cb_auditoria_cortar_todos, args=(cm["id"],))
                if len(resultado_aud["codigos_malos"]) > 25:
                    st.caption(f"(mostrando 25 de {len(resultado_aud['codigos_malos'])})")
                st.markdown("---")

            # 2) Productos basura: lo primero a resolver, porque un solo producto mal cargado
            #    puede estar ensuciando cientos de códigos a la vez.
            if resultado_aud["productos_sospechosos"]:
                st.markdown("**🚩 Productos con muchísimos vínculos (revisalos primero)**")
                explicar(
                    "Una pieza real rara vez equivale a más de 10 códigos de fábrica.",
                    "Si un producto tiene decenas, casi siempre es basura de una importación mal mapeada — "
                    "por ejemplo un código '1' que quedó de una columna equivocada. Cortarle los vínculos "
                    "de una limpia el problema entero."
                )
                # Sin desplegables: Streamlit los cierra en cada refresco, y como cada botón
                # provoca uno, se cerraba la ventana justo cuando estabas revisando.
                for p in resultado_aud["productos_sospechosos"][:15]:
                    desc = texto_para_html(p["descripcion"]) or "_(sin descripción)_"
                    ps1, ps2 = st.columns([3, 1])
                    ps1.markdown(f"**{texto_para_html(p['marca'])}** · `{p['codigo']}` — {desc}  \n"
                                  f"<small>vinculado a {p['cantidad']} códigos distintos</small>",
                                  unsafe_allow_html=True)
                    ps2.button(f"✂️ Cortar {p['cantidad']}",
                                key=f"cortar_todo_{p['id']}", type="primary",
                                on_click=cb_auditoria_cortar_todos, args=(p["id"],),
                                help="El producto queda; solo se cortan todas sus equivalencias")
                if len(resultado_aud["productos_sospechosos"]) > 15:
                    st.caption(f"(mostrando 15 de {len(resultado_aud['productos_sospechosos'])})")
                st.markdown("---")

            # 2) Conflictos agrupados: un código de fábrica apuntando a varios productos
            if resultado_aud["conflictos"]:
                st.markdown("**⚠️ Un código de fábrica apuntando a varios productos del mismo proveedor**")
                st.caption(
                    "Acá se ven juntos todos los productos a los que apunta cada código, para poder "
                    "comparar y cortar el que sobra. Normalmente uno tiene descripción real y el otro "
                    "es el que quedó mal."
                )
                total_conf = len(resultado_aud["conflictos"])
                por_pag_conf = 8
                pags_conf = (total_conf - 1) // por_pag_conf + 1
                if pags_conf > 1:
                    pag_conf = st.number_input(
                        f"Página (de {pags_conf}) — {por_pag_conf} conflictos por página:",
                        min_value=1, max_value=pags_conf, value=1, step=1, key="pagina_conflictos"
                    )
                else:
                    pag_conf = 1
                desde_conf = (int(pag_conf) - 1) * por_pag_conf
                for g in resultado_aud["conflictos"][desde_conf:desde_conf + por_pag_conf]:
                    st.markdown(f"**⚠️ {g['codigo_oem']} → {len(g['productos'])} productos "
                                 f"de {g['marca_proveedor']}**")
                    if g["descripcion_oem"]:
                        st.caption(g["descripcion_oem"])
                    for p in g["productos"]:
                        desc = texto_para_html(p["descripcion"]) or "⚠️ _(sin descripción — sospechoso)_"
                        marca_ok = " · ya revisado" if p["revisado_ok"] else ""
                        cg1, cg2, cg3 = st.columns([3, 1, 1])
                        cg1.markdown(f"**`{p['codigo']}`** — {desc}  \n"
                                      f"<small>{p['vinculos_totales']} vínculos en total{marca_ok}</small>",
                                      unsafe_allow_html=True)
                        cg2.button("🗑️ Cortar", key=f"cortar_par_{g['codigo_oem']}_{p['id']}",
                                    on_click=cb_auditoria_eliminar, args=(p["par"][0], p["par"][1]),
                                    help="Corta solo este vínculo")
                        cg3.button("✅ Dejar", key=f"dejar_par_{g['codigo_oem']}_{p['id']}",
                                    on_click=cb_auditoria_dejar, args=([p["par"]],),
                                    help="Es correcto; no volver a marcarlo")
                    st.markdown("")
                st.markdown("---")

            # 3) Medidas contradictorias
            if resultado_aud["por_medidas"]:
                st.markdown("**📐 Vínculos donde las medidas cargadas no coinciden**")
                for m in resultado_aud["por_medidas"][:30]:
                    st.markdown(f"**{m['marca_a']} `{m['cod_a']}`** — {m['desc_a'] or '_(sin descripción)_'}  \n"
                                 f"**{m['marca_b']} `{m['cod_b']}`** — {m['desc_b'] or '_(sin descripción)_'}")
                    st.caption(f"📐 {m['detalle']}")
                    mb1, mb2 = st.columns(2)
                    mb1.button("✅ Está bien, dejalo", key=f"med_ok_{m['a']}_{m['b']}",
                                on_click=cb_auditoria_dejar, args=([(m["a"], m["b"])],))
                    mb2.button("🗑️ Borrar el vínculo", key=f"med_del_{m['a']}_{m['b']}",
                                on_click=cb_auditoria_eliminar, args=(m["a"], m["b"]))
                if len(resultado_aud["por_medidas"]) > 30:
                    st.caption(f"(mostrando 30 de {len(resultado_aud['por_medidas'])})")

            if (not resultado_aud["conflictos"] and not resultado_aud["por_medidas"]
                    and not resultado_aud["productos_sospechosos"]
                    and not resultado_aud.get("codigos_malos")):
                st.success("✅ No se encontró nada sospechoso entre los vínculos ya cargados.")

        st.markdown("---")

        lotes_pendientes = resumen_lotes_pendientes()
        if lotes_pendientes:
            total_pendientes = sum(l["cantidad"] for l in lotes_pendientes)
            st.markdown("**📄 Vínculos de listas de proveedor esperando revisión**")
            explicar(
                "Estos llegaron al importar una lista y todavía NO están cargados.",
                "Se separan solos entre los que no tienen nada raro y los que dispararon alguna alarma, "
                "para que apruebes en bloque los limpios y mires con lupa solo los pocos sospechosos."
            )

            with st.expander(f"🧹 Descartar TODO lo pendiente ({total_pendientes:,} vínculos de "
                              f"{len(lotes_pendientes)} lista(s))"):
                st.warning(
                    "Borra de una todos los vínculos que están esperando revisión, de todas las listas. "
                    "**Los productos y precios no se tocan** — solo se descartan las equivalencias "
                    "pendientes. Es lo que conviene cuando una importación quedó mal mapeada: descartás "
                    "todo y volvés a importar con las columnas correctas."
                )
                confirmar_todo = st.checkbox("Confirmo que quiero descartar todo lo pendiente",
                                              key="confirmar_descartar_todo")
                if st.button("🧹 Descartar todo", disabled=not confirmar_todo, type="primary"):
                    borrados = 0
                    for l in lotes_pendientes:
                        borrados += rechazar_pendientes(l["lote"], None)
                    avisar("success", f"Se descartaron {borrados:,} vínculo(s) pendientes.")
                    st.rerun()

            # Una lista por vez, elegida con un selector. Antes cada lista estaba dentro de un
            # desplegable, y como Streamlit los cierra al refrescar la pantalla, cada botón que
            # tocabas te cerraba la ventana entera — imposible revisar 300 vínculos así.
            opciones_lotes = {f"{l['lote']} — {l['cantidad']} vínculo(s)": l for l in lotes_pendientes}
            etiqueta_lote = st.selectbox("Lista a revisar:", list(opciones_lotes.keys()),
                                          key="lote_en_revision")
            lote_info = opciones_lotes[etiqueta_lote]

            total_lote = contar_pendientes_del_lote(lote_info["lote"])
            ca1, ca2 = st.columns([2, 1])
            with ca1:
                # Arranca en la opción que cubre la lista ENTERA. Estaba fijo en 1.000, y
                # con 3.185 pendientes eso son tres vueltas para ver una lista que se analiza
                # entera en 6,6 s — y dos tercios que, si nadie cambia de tanda, no se miran.
                _opciones_tanda = [400, 1000, 2500, 5000, 10000, 25000, 100000]
                st.session_state.setdefault(
                    "cuantos_pendientes",
                    next((o for o in _opciones_tanda if o >= total_lote), _opciones_tanda[-1]))
                cuantos = st.select_slider(
                    "¿Cuántos analizar por vez?",
                    options=_opciones_tanda,
                    key="cuantos_pendientes",
                    help="Analizar más tarda un poco más, pero te evita repetir la vuelta muchas veces."
                )
            paginas_lote = max((total_lote - 1) // int(cuantos) + 1, 1)
            with ca2:
                tanda_lote = st.number_input(
                    f"Tanda (de {paginas_lote}):", min_value=1, max_value=paginas_lote,
                    value=1, step=1, key=f"tanda_lote_{lote_info['lote']}"
                ) if paginas_lote > 1 else 1

            # EL ANÁLISIS SE GUARDA, y no es un lujo: tarda 5,2 s sobre los 3.185 pendientes
            # reales y estaba corriendo en CADA dibujado de esta pantalla. Mover el slider de
            # «cuántos analizar», cambiar de tanda o tildar un checkbox volvía a analizar todo
            # de cero — 5 segundos de reloj de arena por tocar una casilla.
            #
            # La clave incluye el total de pendientes del lote, y eso es lo que lo invalida
            # solo: aprobar o descartar cambia ese número, así que el análisis se rehace justo
            # cuando dejó de valer y no antes. Lo que se hace en OTRO lote no lo toca, y está
            # bien: el análisis de éste sigue siendo cierto.
            _clave_analisis = (lote_info["lote"], int(cuantos),
                               (int(tanda_lote) - 1) * int(cuantos), total_lote)
            _guardado = st.session_state.get("_analisis_lote")
            if _guardado and _guardado.get("clave") == _clave_analisis:
                limpias, sospechosas, relacionadas = _guardado["resultado"]
            else:
                with st.spinner("Analizando..."):
                    limpias, sospechosas, relacionadas = analizar_lote_pendiente(
                        lote_info["lote"], limite=int(cuantos),
                        desde=(int(tanda_lote) - 1) * int(cuantos)
                    )
                st.session_state["_analisis_lote"] = {
                    "clave": _clave_analisis,
                    "resultado": (limpias, sospechosas, relacionadas),
                }
            analizados = len(limpias) + len(sospechosas) + len(relacionadas)
            st.caption(f"Analizados {analizados:,} de {total_lote:,} vínculo(s) de esta lista." +
                       (f" Quedan {total_lote - analizados:,} — cambiá de tanda para verlos."
                        if total_lote > analizados else ""))

            # El kit y la pieza que trae adentro no son una equivalencia, así que no se
            # preguntan de a uno: van en una línea y se descartan juntos. El buscador igual
            # ofrece el kit cuando alguien busca la pieza suelta.
            if relacionadas:
                st.info(
                    f"📦 **{len(relacionadas)} par(es) son un kit y una pieza que viene "
                    "adentro.** No son equivalentes —no se puede vender una en lugar de la "
                    "otra— así que no te los pongo a decidir de a uno. El buscador te ofrece "
                    "el kit igual cuando buscás la pieza suelta."
                )
                with st.expander(f"Ver los {len(relacionadas)}"):
                    st.dataframe(
                        [{"Código A": x.get("cod_a"), "Marca A": x.get("marca_a"),
                          "Código B": x.get("cod_b"), "Marca B": x.get("marca_b"),
                          "Relación": x.get("relacion", "")} for x in relacionadas[:200]],
                        width="stretch", hide_index=True)
                if st.button(f"🚫 Descartar esos {len(relacionadas)}",
                              key=f"desc_rel_{lote_info['lote']}"):
                    _pares_rel = [(x["a"], x["b"]) for x in relacionadas]
                    _n = rechazar_pendientes(lote_info["lote"], _pares_rel)
                    invalidar_salud()
                    avisar("success", f"Se descartaron {_n} par(es) de kit y pieza.")
                    st.rerun()

            # Se agrupa por confianza, no por "tiene alarma / no tiene". Con 397 alarmas planas
            # había que mirarlas de a una; así se ve de una que la mayoría es descartable y solo
            # un puñado merece atención.
            patrones_ui = aprender_de_las_decisiones()
            todos_evaluados = limpias + sospechosas
            por_nivel = {"🟢": [], "🟡": [], "🟠": [], "🔴": []}
            for x in todos_evaluados:
                por_nivel[nivel_de_confianza(x.get("confianza", 50))[0][:1]].append(x)

            mn1, mn2, mn3, mn4 = st.columns(4)
            mn1.metric("🟢 Muy probables", len(por_nivel["🟢"]))
            mn2.metric("🟡 Probables", len(por_nivel["🟡"]))
            mn3.metric("🟠 Dudosas", len(por_nivel["🟠"]))
            mn4.metric("🔴 Casi seguro mal", len(por_nivel["🔴"]))

            # Cuando el problema es UN producto que aparece en decenas de pendientes, se resuelve
            # de una. Antes había que aprobar o descartar cada vínculo por separado, aunque los
            # cincuenta dijeran exactamente lo mismo.
            culpables = productos_que_mas_ensucian(lote_info["lote"])
            if culpables:
                total_culpa = sum(x["Pendientes que genera"] for x in culpables)
                st.warning(
                    f"🎯 **{len(culpables)} producto(s) con código dudoso generan {total_culpa} "
                    "de estos pendientes.** Resolvelos de una en vez de vínculo por vínculo."
                )
                st.dataframe(quitar_id(culpables), width="stretch", hide_index=True)
                etiquetas_culpa = {
                    f"{x['Código']} ({x['Marca']}) — {x['Pendientes que genera']} pendientes": x["_id"]
                    for x in culpables
                }
                elegido_culpa = st.selectbox("¿Cuál resolver?", list(etiquetas_culpa.keys()),
                                              key=f"culpable_{lote_info['lote']}")
                cc1, cc2 = st.columns(2)
                if cc1.button("🚫 Descartar TODOS sus pendientes", key=f"desc_culpa_{lote_info['lote']}"):
                    n = rechazar_pendientes_de_producto(etiquetas_culpa[elegido_culpa],
                                                         lote_info["lote"])
                    invalidar_salud()
                    avisar("success", f"Se descartaron {n} vínculo(s) de una.")
                    st.rerun()
                if cc2.button("✅ El código está bien, no volver a marcarlo",
                               key=f"ok_culpa_{lote_info['lote']}"):
                    aprobar_puente(etiquetas_culpa[elegido_culpa], "código validado a mano")
                    invalidar_salud()
                    avisar("success", "Anotado: ese código deja de marcarse como problema.")
                    st.rerun()

            if por_nivel["🔴"]:
                muestra_mal = por_nivel["🔴"][:8]
                with st.expander(f"🔴 Ver por qué las {len(por_nivel['🔴'])} peores están mal"):
                    for x in muestra_mal:
                        st.markdown(f"**{x['cod_a']}** ({x['marca_a']}) ↔ "
                                     f"**{x['cod_b']}** ({x['marca_b']}) — {x['confianza']:.0f}/100")
                        for tipo, texto in x.get("senales", []):
                            st.caption(("❌ " if tipo == "mal" else "✅ ") + texto)
                        for _ev in x.get("evidencia", []):
                            st.caption("✅ " + _ev)

            ml1, ml2 = st.columns(2)
            ml1.metric("Sin nada raro", len(limpias))
            ml2.metric("Con alguna alarma", len(sospechosas))

            if analizados and len(sospechosas) / analizados > 0.7:
                st.error(
                    "🔴 Más del 70% de esta lista dispara alarmas. Eso no es que tengas mala suerte: "
                    "casi siempre significa que la importación quedó **mal mapeada** — la columna que "
                    "se tomó como código en realidad traía cantidades, medidas o pedazos de la "
                    "descripción. Antes de revisar de a uno, conviene descartar toda la lista y "
                    "volver a importarla revisando bien el mapeo de columnas."
                )

            bl1, bl2 = st.columns(2)
            pares_limpios = []
            for x in limpias:
                pares_limpios.extend([(x["a"], x["b"]), (x["b"], x["a"])])
            bl1.button(f"✅ Aprobar los {len(limpias)} sin alarmas",
                        key=f"apr_limpias_{lote_info['lote']}", type="primary",
                        disabled=not limpias,
                        on_click=aprobar_pendientes, args=(lote_info["lote"], pares_limpios))
            bl2.button("🚫 Descartar toda esta lista",
                        key=f"rec_lote_{lote_info['lote']}",
                        on_click=rechazar_pendientes, args=(lote_info["lote"], None),
                        help="Los productos y precios quedan; solo se descartan los vínculos")

            # Descartar en bloque los que el análisis ya dio por perdidos. Sin esto, la app
            # marcaba cientos como «casi seguro mal» y después te los hacía resolver de a uno,
            # que es exactamente lo que el análisis venía a evitar.
            if por_nivel["🔴"]:
                pares_rojos = []
                for x in por_nivel["🔴"]:
                    pares_rojos.extend([(x["a"], x["b"]), (x["b"], x["a"])])
                st.error(
                    f"🔴 Hay **{len(por_nivel['🔴'])} vínculos «casi seguro mal»** en esta tanda. "
                    "No hace falta mirarlos de a uno: el análisis ya tiene evidencia en contra de "
                    "todos (rubros distintos, medidas que no dan, o tu propio historial)."
                )
                if st.button(f"🚫 Descartar los {len(por_nivel['🔴'])} marcados 🔴",
                              key=f"rec_rojos_{lote_info['lote']}", type="primary"):
                    rechazar_pendientes(lote_info["lote"], pares_rojos)
                    invalidar_salud()
                    avisar("success", f"Se descartaron {len(por_nivel['🔴'])} vínculo(s) de una.")
                    st.rerun()

            # Y cuando tu propio historial es contundente sobre una combinación de marcas,
            # ofrecer resolver TODA esa combinación de una vez.
            combinaciones = {}
            for x in limpias + sospechosas:
                clave = tuple(sorted((x.get("marca_a", ""), x.get("marca_b", ""))))
                combinaciones.setdefault(clave, []).append(x)
            for (ma, mb), items in sorted(combinaciones.items(), key=lambda t: -len(t[1])):
                dato = patrones_ui["marcas"].get((ma, mb)) if patrones_ui else None
                if not dato or dato["tasa_ok"] > 0.05 or dato["decisiones"] < 50:
                    continue
                pares_comb = []
                for x in items:
                    pares_comb.extend([(x["a"], x["b"]), (x["b"], x["a"])])
                st.warning(
                    f"📚 **De {dato['decisiones']:,} vínculos {ma}↔{mb} que revisaste, descartaste "
                    f"el {(1-dato['tasa_ok'])*100:.0f}%.** En esta tanda hay {len(items)} más de "
                    "esa misma combinación. Si van a terminar igual, resolvelos de una."
                )
                if st.button(f"🚫 Descartar los {len(items)} de {ma}↔{mb}",
                              key=f"rec_comb_{lote_info['lote']}_{ma}_{mb}"):
                    rechazar_pendientes(lote_info["lote"], pares_comb)
                    invalidar_salud()
                    avisar("success", f"Se descartaron {len(items)} vínculo(s) de {ma}↔{mb}.")
                    st.rerun()
                break   # de a una combinación por vez, para no llenar la pantalla

            if limpias:
                with st.expander(f"Ver los {len(limpias)} sin alarmas"):
                    st.dataframe(
                        [{"Código A": x["cod_a"], "Marca A": x["marca_a"],
                           "Código B": x["cod_b"], "Marca B": x["marca_b"]} for x in limpias[:500]],
                        width="stretch", hide_index=True
                    )
                    if len(limpias) > 500:
                        st.caption(f"Se muestran 500 de {len(limpias)}; el botón de aprobar los toma a todos.")

            if sospechosas:
                st.markdown("---")
                # «Con algo raro» no es cierto para todos: el corte lo decide el PUNTAJE, y un
                # vínculo puede quedar abajo de 55 sin ninguna alarma, solo porque no encontró
                # evidencia a favor. Sobre la lista de Illinois son 285 de 595. Llamarlos a
                # todos «raros» manda a buscar un problema que en la mitad no existe: lo que
                # les falta es respaldo, que es otra cosa y se revisa distinto.
                _con_alarma = [x for x in sospechosas if x.get("alarmas")]
                _sin_respaldo = len(sospechosas) - len(_con_alarma)
                st.warning(
                    f"⚠️ **{len(sospechosas)} vínculo(s) para revisar.** "
                    + (f"{len(_con_alarma)} tienen alguna alarma concreta"
                       + (f" y {_sin_respaldo} no tienen ninguna: simplemente no se encontró "
                          "evidencia a favor (ni medidas, ni catálogo, ni parecido de "
                          "descripción), así que quedaron con poco puntaje."
                          if _sin_respaldo else ".")
                       if _con_alarma else
                       "Ninguno tiene una alarma concreta: lo que les falta es evidencia a "
                       "favor, así que quedaron con poco puntaje.")
                )
                # De a tandas por pantalla: con cientos, la página se vuelve imposible de usar
                por_pagina = st.radio("Mostrar de a:", [10, 25, 50], horizontal=True,
                                       key="sosp_por_pagina")
                paginas = (len(sospechosas) - 1) // por_pagina + 1
                if paginas > 1:
                    if "_ir_a_pagina_sospechosas" in st.session_state:
                        st.session_state["pagina_sospechosas"] = min(
                            st.session_state.pop("_ir_a_pagina_sospechosas"), paginas)
                    pagina_sosp = st.number_input(
                        f"Página (de {paginas}) — cada una trae {por_pagina}:",
                        min_value=1, max_value=paginas, value=1, step=1, key="pagina_sospechosas"
                    )
                else:
                    pagina_sosp = 1
                desde = (int(pagina_sosp) - 1) * por_pagina

                # Agrupados por MOTIVO, no uno debajo del otro. Cuando 40 vínculos fallan por lo
                # mismo —"«1S» es demasiado corto"— repetir la explicación 40 veces obliga a
                # scrollear y a decidir 40 veces algo que es una sola decisión. Agrupados, se lee
                # el motivo una vez y se resuelve el grupo entero.
                # Y ordenados por motivo ANTES de cortar en páginas: si no, cada página de 10
                # traía de todo un poco y agrupar dentro de ella no juntaba casi nada. Primero
                # el motivo con el peor vínculo, como antes iba primero el peor vínculo. Con los
                # datos reales, de a 10: ILLINOIS pasa de 315 decisiones a 45, BARRIDO de 205
                # a 52. El tamaño de la página sigue siendo el que eligió el que revisa.
                def _tipo(x):
                    return tipo_de_alarma(x["alarmas"][0] if x["alarmas"] else "")
                _peor_del_tipo, _total_del_tipo = {}, {}
                for x in sospechosas:
                    _t = _tipo(x)
                    _peor_del_tipo[_t] = min(_peor_del_tipo.get(_t, 100), x["confianza"])
                    _total_del_tipo[_t] = _total_del_tipo.get(_t, 0) + 1
                _por_tipo = sorted(sospechosas, key=lambda x: (_peor_del_tipo[_tipo(x)], _tipo(x),
                                                                x["confianza"]))
                pagina_actual = _por_tipo[desde:desde + por_pagina]

                por_motivo = {}
                for s in pagina_actual:
                    por_motivo.setdefault(_tipo(s), []).append(s)

                _lote_rev = lote_info["lote"]
                _decididas = decisiones_del_lote(_lote_rev)

                def _boton_aplicar(donde):
                    """El botón de aplicar lo marcado. Arriba y abajo de los grupos: en el
                    celular, después de marcar el último, el de arriba queda pantallas atrás."""
                    _b = sum(1 for q in _decididas.values() if q == "bien")
                    _m = len(_decididas) - _b
                    if not _decididas:
                        if donde == "arriba":
                            st.caption("Marcá cada grupo (o cada vínculo) y aplicá todo junto con "
                                       "un solo botón: una espera en vez de una por grupo.")
                        return
                    st.button(f"💾 Aplicar lo marcado: ✅ {_b} bien · 🚫 {_m} a descartar",
                              type="primary", key=f"aplicar_decisiones_{donde}",
                              on_click=aplicar_decisiones, args=(_lote_rev,))
                    if donde == "arriba":
                        st.caption("Nada se guarda hasta tocar «Aplicar». Lo marcado se mantiene "
                                   "aunque cambies de página.")

                _boton_aplicar("arriba")
                for motivo, items in por_motivo.items():
                    peor_grupo = min(x["confianza"] for x in items)
                    icono = "🔴" if peor_grupo < 30 else "🟠" if peor_grupo < 55 else "🟡"
                    _de_cuantos = (f" (de {_total_del_tipo[motivo]} con este motivo)"
                                   if _total_del_tipo[motivo] > len(items) else "")
                    st.markdown(f"{icono} **{motivo}** — {len(items)} vínculo(s){_de_cuantos}")

                    _pares_grupo = [(x["a"], x["b"]) for x in items]
                    # El selector del grupo muestra lo que tienen sus pares: si todos tienen lo
                    # mismo, eso; si no, «—» y abajo cuántos se decidieron de a uno.
                    _clave_g = f"dec_grupo_{_lote_rev}_{desde}_{por_pagina}_{abs(hash(motivo))}"
                    _hay = {_decididas.get(par) for par in _pares_grupo}
                    st.session_state[_clave_g] = (_ROTULO_DE_LA_DECISION[_hay.pop()]
                                                  if len(_hay) == 1 else "—")
                    st.radio(f"¿Qué hacés con {'estos ' + str(len(items)) if len(items) > 1 else 'este'}?",
                             list(DECISIONES_DE_REVISION), key=_clave_g, horizontal=True,
                             on_change=anotar_decision, args=(_lote_rev, _clave_g, _pares_grupo))
                    if len(_hay) > 1 or (len(_hay) == 1 and st.session_state[_clave_g] == "—"
                                         and any(_decididas.get(par) for par in _pares_grupo)):
                        _b_g = sum(1 for par in _pares_grupo if _decididas.get(par) == "bien")
                        _m_g = sum(1 for par in _pares_grupo if _decididas.get(par) == "mal")
                        st.caption(f"Decididos de a uno: ✅ {_b_g} · 🚫 {_m_g} · "
                                   f"sin decidir {len(items) - _b_g - _m_g}")

                    with st.expander(f"Ver los {len(items)} uno por uno" if len(items) > 1
                                     else "Ver el detalle"):
                        for s in items:
                            st.markdown(f"**{s['marca_a']} {s['cod_a']} ↔ "
                                         f"{s['marca_b']} {s['cod_b']}** · {s['confianza']:.0f}/100")
                            # La del título ya se leyó arriba; si el título es el motivo sin
                            # el detalle («espesor» y no «espesor: 3 vs 5»), el detalle va acá.
                            for i_al, alarma in enumerate(s["alarmas"]):
                                if i_al or alarma != motivo:
                                    st.caption(f"   {alarma}")
                            if len(items) > 1:
                                _clave_p = f"dec_{_lote_rev}_{s['a']}_{s['b']}"
                                st.session_state[_clave_p] = _ROTULO_DE_LA_DECISION[
                                    _decididas.get((s["a"], s["b"]))]
                                st.radio("Este:", list(DECISIONES_DE_REVISION), key=_clave_p,
                                         horizontal=True, label_visibility="collapsed",
                                         on_change=anotar_decision,
                                         args=(_lote_rev, _clave_p, [(s["a"], s["b"])]))
                            st.markdown("")
                    st.markdown("")
                _boton_aplicar("abajo")
                # Marcar y pasar a la página siguiente es el ritmo de la revisión, y en el celular
                # el «+» del número de página es chico y quedó varias pantallas más arriba.
                if paginas > 1 and int(pagina_sosp) < paginas:
                    def _a_la_pagina_siguiente():
                        # A otra clave: la del número de página ya se dibujó en esta pasada. Se
                        # vuelca antes de dibujarlo, en la próxima (ver arriba).
                        st.session_state["_ir_a_pagina_sospechosas"] = int(pagina_sosp) + 1
                    st.button(f"➡️ Página siguiente ({int(pagina_sosp) + 1} de {paginas})",
                              key="pagina_sospechosas_siguiente", on_click=_a_la_pagina_siguiente)
            st.markdown("---")

        st.markdown("**🛒 Equivalencias que aparecieron solas en el mostrador**")
        explicar(
            "Cuando un cliente pide un código y termina llevándose otro, eso es una equivalencia "
            "que pasó de verdad.",
            "**Nada se carga solo, nunca**: acá se juntan las sugerencias con el detalle de en qué "
            "se basa cada una, y una persona decide. Están ordenadas por cuánto respaldo tienen — "
            "mirá primero las verdes, y desconfiá de las que tengan evidencia en contra."
        )

        cfg1, cfg2 = cols(2)
        min_veces_cfg = cfg1.number_input("Mostrar cuando se repitió al menos:", min_value=1, value=2, step=1,
                                           key="cfg_min_veces",
                                           help="Con 1 vas a ver más sugerencias, pero también más ruido.")
        dias_cfg = cfg2.number_input("Mirar los últimos (días):", min_value=7, value=180, step=30,
                                      key="cfg_dias_equiv")

        candidatas = descubrir_equivalencias_candidatas(int(min_veces_cfg), int(dias_cfg))

        if not candidatas:
            c.execute("SELECT COUNT(*) FROM ventas_registradas")
            ventas_totales = c.fetchone()[0]
            if ventas_totales == 0:
                st.info(
                    "Todavía no hay ventas marcadas. Cuando busques algo en el Buscador y el cliente "
                    "se lleve una pieza, tocá '🛒 Se llevó' — con eso se empieza a alimentar esto."
                )
            else:
                st.caption(
                    f"Hay {ventas_totales} venta(s) registrada(s), pero todavía no se repitió ningún "
                    "caso lo suficiente como para sugerirlo (o ya están todos cargados como equivalentes)."
                )
        else:
            st.success(f"{len(candidatas)} sugerencia(s) para revisar:")
            marcas_disponibles = [m["nombre"] for m in
                                   c.execute("SELECT nombre FROM marcas ORDER BY nombre").fetchall()]

            for cand in candidatas:
                etiqueta_origen = ("marcado en el mostrador" if cand["origen"] == "mostrador"
                                    else "deducida: se vendió justo después de buscar eso sin resultado")
                with st.expander(
                    f"{cand['confianza']}  ·  {cand['codigo_pedido']} → {cand['codigo_vendido']} "
                    f"({cand['marca_vendida']}) — pasó {cand['veces']} vez/veces"
                ):
                    st.write(f"**Pidieron:** {cand['codigo_pedido']}")
                    st.write(f"**Se llevaron:** {cand['codigo_vendido']} ({cand['marca_vendida']}) "
                              f"{cand['descripcion']}")

                    st.markdown("**En qué se basa esto:**")
                    nombres_evidencia = {
                        "catalogo_oficial": "🌐 Aparece en la ficha oficial del proveedor",
                        "catalogo_no_lo_lista": "🌐 NO aparece en la ficha oficial",
                        "lista_proveedor": "📄 Venían relacionados en una lista del proveedor",
                        "medidas": "📐 Las medidas mecánicas coinciden",
                        "medidas_no_coinciden": "📐 Las medidas NO coinciden",
                        "mostrador": "🛒 Se repitió en el mostrador",
                    }
                    for ev in cand["evidencias"]:
                        st.caption(f"- {nombres_evidencia.get(ev['tipo'], ev['tipo'])}: {ev['detalle']}")
                    st.caption(f"({etiqueta_origen})")

                    # Verificación contra el catálogo del proveedor: la evidencia más fuerte,
                    # porque no depende de que nadie opine — el código está escrito en la
                    # página del proveedor o no está.
                    c.execute("""SELECT m.url_ficha_template, p.codigo_raw
                                 FROM productos p JOIN marcas m ON m.id = p.marca_id
                                 WHERE p.id = ?""", (cand["producto_id"],))
                    info_ficha = c.fetchone()
                    tiene_catalogo = bool(info_ficha and info_ficha["url_ficha_template"])
                    if st.button("🌐 Verificar en el catálogo del proveedor",
                                  key=f"verif_{cand['codigo_clean']}_{cand['producto_id']}",
                                  disabled=not tiene_catalogo,
                                  help=("Abre la ficha oficial y fija si el código pedido aparece ahí"
                                        if tiene_catalogo else
                                        f"La marca {cand['marca_vendida']} no tiene cargada la dirección "
                                        "de su catálogo (se carga en Administrar → Marcas)")):
                        url_ficha = info_ficha["url_ficha_template"].replace(
                            "{codigo}", quote(info_ficha["codigo_raw"], safe="")
                        )
                        with st.spinner("Consultando la ficha del proveedor..."):
                            encontrado, detalle_verif = verificar_en_catalogo_oficial(
                                cand["codigo_pedido"], url_ficha
                            )
                        if encontrado is True:
                            guardar_evidencia(cand["codigo_clean"], cand["producto_id"],
                                               "catalogo_oficial", detalle_verif)
                            st.success("✅ " + detalle_verif)
                        elif encontrado is False:
                            guardar_evidencia(cand["codigo_clean"], cand["producto_id"],
                                               "catalogo_no_lo_lista", detalle_verif)
                            st.warning("⚠️ " + detalle_verif)
                        else:
                            st.info(detalle_verif)

                    marca_nueva = None
                    if not cand["pedido_ya_cargado"]:
                        st.warning(
                            f"El código '{cand['codigo_pedido']}' no está cargado como producto. "
                            "Si confirmás, se crea con la marca que elijas y recién ahí se vinculan."
                        )
                        marca_nueva = st.selectbox(
                            "Marca para el código nuevo:", marcas_disponibles,
                            key=f"marca_cand_{cand['codigo_clean']}_{cand['producto_id']}"
                        ) if marcas_disponibles else None

                    cb1, cb2 = st.columns(2)
                    if cb1.button("✅ Confirmar equivalencia",
                                   key=f"conf_cand_{cand['codigo_clean']}_{cand['producto_id']}",
                                   type="primary"):
                        ok, error_conf = confirmar_candidata(
                            cand["codigo_clean"], cand["producto_id"], cand["codigo_pedido"], marca_nueva
                        )
                        if ok:
                            st.success("Equivalencia cargada. Ya aparece al buscar cualquiera de los dos códigos.")
                        else:
                            st.error(error_conf)
                    cb2.button("🚫 No es equivalente",
                                key=f"desc_cand_{cand['codigo_clean']}_{cand['producto_id']}",
                                on_click=descartar_candidata,
                                args=(cand["codigo_clean"], cand["producto_id"]),
                                help="No se vuelve a sugerir")

        st.markdown("---")
        st.markdown("**🛒 Últimas ventas marcadas**")
        c.execute("""SELECT v.fecha AS "Fecha", v.termino_pedido AS "Pidieron",
                            p.codigo_raw AS "Se llevaron", m.nombre AS "Marca", v.usuario AS "Empleado"
                     FROM ventas_registradas v
                     JOIN productos p ON p.id = v.producto_id
                     JOIN marcas m ON m.id = p.marca_id
                     ORDER BY v.id DESC LIMIT 25""")
        ultimas_ventas = filas_a_listas(c)
        if ultimas_ventas:
            st.dataframe(ultimas_ventas, width="stretch", hide_index=True)
        else:
            st.caption("Todavía no se marcó ninguna venta.")

"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/."""

# ============================================================
# ESTADÍSTICAS
# ============================================================
if pagina == PAGINAS[4]:
    st.subheader("📊 Estadísticas")

    sub_stats = elegir_solapa(PAGINAS[4])

    if sub_stats == SUB_STATS[0]:
        st.subheader("Estadísticas generales")

        c.execute("SELECT COUNT(*) FROM marcas")
        total_marcas = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM productos")
        total_productos = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM equivalencias")
        total_equiv = c.fetchone()[0]

        m1, m2, m3 = st.columns(3)
        m1.metric("Marcas registradas", miles(total_marcas))
        m2.metric("Códigos cargados", miles(total_productos))
        m3.metric("Vínculos de equivalencia", miles(total_equiv // 2 if total_equiv else 0))

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
            # Horizontal y de mayor a menor: parado, los nombres salían girados y cortados
            # («MANNOL LUBRIC…»). Lo señaló la revisión con Gemini.
            st.bar_chart(chart_data, x="Marca", y="Productos", horizontal=True,
                         sort="-Productos")

        # Solo si se usó: una sección entera para decir «todavía nada» era ruido.
        uso_ia_actual = resumen_uso_ia()
        if uso_ia_actual:
            st.markdown("---")
            st.markdown("**🤖 Uso de las funciones de IA (últimos 30 días)**")
            ayuda(
                "Cada fila es una función que usó la IA, con cuántas veces falló. Un error casi "
                "siempre es el límite de uso de la clave: se reintenta más tarde. «Generar imagen "
                "orientativa» usa una clave aparte, que se configura por separado."
            )
            st.dataframe(uso_ia_actual, width="stretch", hide_index=True)

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

    # La copia de la base es TODO: precios, clientes, teléfonos, usuarios. Solo administrador.
    if sub_stats == SUB_STATS[2] and seccion_permitida("admin", "copias de la base"):
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
                    f"{miles(_riesgo['productos_ahora'])} producto(s) viviendo solo en el disco del "
                    "servidor, que se borra en cada reinicio. **Hoy un reinicio borra todo.**"
                )
            elif _riesgo["en_riesgo"]:
                st.warning(
                    f"⚠️ **{miles(_riesgo['en_riesgo'])} producto(s) y "
                    f"{miles(_riesgo['equivalencias_en_riesgo'])} vínculo(s) viven solo en el disco.**\n\n"
                    f"La copia del repositorio es del {_riesgo['fecha_semilla']} y tiene "
                    f"{miles(_riesgo['productos_semilla'])} productos; hoy tenés "
                    f"{miles(_riesgo['productos_ahora'])}. Si el servidor reinicia, esa diferencia "
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
                    f"✅ La copia del repositorio está al día ({miles(_riesgo['productos_semilla'])} "
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
                    "En **Settings → Secrets** de Streamlit Cloud, agregá estas dos líneas "
                    "ARRIBA DE TODO (antes de cualquier renglón entre corchetes):\n\n"
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
                    "recuperá las fotos después desde "
                    f"**{miga_hasta('Traer fotos de productos en tanda')}**, que las vuelve a bajar de las fichas de los proveedores sin cargarlas a mano.\n"
                    "- **Lo más prolijo a futuro:** guardar las fotos por dirección web en vez de "
                    "adentro de la base, y dejar cargada la dirección del catálogo de cada marca en "
                    "**🗂️ Administrar → 🏷️ Marcas**. Así el backup queda liviano y las fotos se vuelven a "
                    "traer solas."
                )

        if mb_fotos > 60:
            st.warning(
                f"⚠️ Las fotos ({cantidad_fotos} productos) ocupan unos {miles(mb_fotos, 0)} MB. "
                "GitHub no acepta archivos de más de 100 MB, así que para la copia del repositorio "
                "conviene usar el **backup sin fotos** de acá abajo."
            )
        elif cantidad_fotos:
            st.caption(f"Las fotos de {cantidad_fotos} producto(s) ocupan {miles(mb_fotos, 1)} MB de la base.")

        cbk1, cbk2 = st.columns(2)
        with cbk1:
            st.markdown("*Completo (con fotos)*")
            if st.button("🗄️ Preparar backup completo"):
                with st.spinner("Armando..."):
                    st.session_state["backup_bytes"] = generar_backup_completo()
            if "backup_bytes" in st.session_state:
                st.download_button(
                    f"⬇️ Descargar ({miles(len(st.session_state['backup_bytes'])/(1024*1024), 0)} MB)",
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
                    f"⬇️ Descargar ({miles(len(st.session_state['backup_liviano'])/(1024*1024), 1)} MB)",
                    data=st.session_state["backup_liviano"],
                    file_name="datos_iniciales.db",
                    help="Ya viene con el nombre listo para subir al repositorio",
                    on_click=marcar_backup_hecho
                )
                st.caption(
                    f"Lleva los {total_prod_backup} productos con precios, equivalencias, vehículos e "
                    "historial. ⚠️ **No lleva las fotos**: si restaurás desde este archivo hay que "
                    f"volver a traerlas desde {miga_hasta('Traer fotos de productos en tanda')}.\n\n"
                    "🔒 **No lo subas a un repositorio público**: lleva tus precios, clientes y "
                    "usuarios, y cualquiera lo podría bajar. Para la copia automática usá un "
                    "repositorio privado y `clave_copia` en los secretos (se sube cifrada)."
                )

        st.markdown("---")
        st.markdown("**📦 Exportar configuración (sin el catálogo de productos)**")
        ayuda(
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
                st.success(f"✅ Hay una copia en el repositorio ({miles(peso, 1)} MB, del {marca_tiempo:%d/%m/%Y}).")
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
        archivo_restaurar = subir_archivo(
            "Subí un archivo .db de backup (o la copia .gz de GitHub, cifrada o no):",
            ["db", "gz"], "restaurar")
        if archivo_restaurar:
            archivo_listo(archivo_restaurar, "backup")
            boton_otro_archivo("restaurar", "🗑️ Usar otro backup", key="otro_backup")
        confirmar_restore = st.checkbox("Entiendo que esto borra los datos actuales y los reemplaza")
        if candado('restaurar un backup', st.button("♻️ Restaurar backup", disabled=not (archivo_restaurar and confirmar_restore)), 'restaurar_un_backup'):
            try:
                restaurar_backup(archivo_restaurar)
            except ValueError as _err_rest:
                st.error(f"No se restauró nada: {_err_rest}.")
            else:
                avisar("success", "Backup restaurado. Recargando...")
                st.rerun()

    if sub_stats == SUB_STATS[3]:
        st.markdown("**🧮 Auditoría diaria de stock (muestreo aleatorio)**")
        ayuda(
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
        ayuda(
            "Lo que más rota (A) conviene tenerlo más a mano. La rotación sale de lo que se "
            "vendió en los últimos seis meses —lo que se anota con «🛒 Se llevó» en el "
            "buscador— y, entre los que se vendieron igual, de cuántas veces se buscó."
        )
        matriz = calcular_matriz_abc()
        if matriz:
            st.dataframe(quitar_id(matriz), width="stretch", hide_index=True)
            st.caption("Para cargar o corregir la ubicación de un producto: "
                       f"{miga_hasta('Productos')} → buscalo → «📐 Cargar medidas mecánicas / "
                       "ubicación en depósito».")
        else:
            st.caption("Todavía no hay ventas ni búsquedas registradas para armar la matriz.")

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

        st.markdown("**🎯 Qué te conviene cargar o pedir**")
        explicar(
            "Lo que te pidieron y no tenías, con qué hacer en cada caso.",
            "Mira tu propia base por cada código que se buscó sin resultado:\n\n"
            "- **🔗 Lo tenés con otro número**: otro producto lo nombra en su descripción "
            "(«… REF ORIG 0280155929»). Falta el vínculo, no la pieza: buscalo en «Vincular "
            "manual».\n"
            "- **⌨️ ¿Error de tipeo?**: hay un código que se escribe casi igual.\n"
            "- **🛒 No lo tenés**: no aparece en ningún lado y lo pidieron más de una vez. Es "
            "para pedirle al proveedor.\n\n"
            "Lo pedido una sola vez y sin ninguna pista no se muestra: todavía no dice nada."
        )
        st.session_state.setdefault("dias_que_conviene", 90)
        _dias_qc = st.select_slider("De los últimos:", options=[30, 90, 180, 365],
                                    format_func=lambda x: f"{x} días", key="dias_que_conviene")
        _qc = que_conviene_cargar_o_pedir(_dias_qc)
        if _qc:
            st.dataframe(_qc, width="stretch", hide_index=True)
        else:
            st.caption("Nada para hacer por ahora.")

        st.markdown("**🔎 Todo lo buscado sin resultado**")
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
            "Sin esto, la reposición depende de que alguien se acuerde de tocar «📌 Pedir». Y "
            "de lo que uno no se acuerda es justamente de lo que se vende parejo "
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
            ayuda(
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
            st.warning(f"⚠️ {len(_clavos)} producto(s) con **${miles(_plata, 0)}** inmovilizados.")
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
        # Los que las listas ya traen escritos se cargan solos una vez por día; esto es para no
        # esperar después de importar una lista nueva.
        if st.button("📝 Leer los «reemplaza a» de las descripciones", key="leer_reemplazos"):
            _n_rd = cargar_reemplazos_de_las_descripciones()
            avisar("success", f"{_n_rd} reemplazo(s) nuevos leídos de las descripciones."
                   if _n_rd else "No había reemplazos nuevos escritos en las descripciones.")
            st.rerun()
        try:
            c.execute("""SELECT codigo_viejo AS "Ya no se fabrica",
                                codigo_nuevo AS "Lo reemplaza", nota AS "Nota",
                                COALESCE(cargado_por, '') AS "Cargó",
                                substr(fecha, 1, 10) AS "Cargado"
                         FROM reemplazos_codigo ORDER BY fecha DESC LIMIT 200""")
            _lista_r = filas_a_listas(c)
        except sqlite3.OperationalError as _err:
            anotar_error("nivel principal", _err)
            _lista_r = []
        if _lista_r:
            st.dataframe(_lista_r, width="stretch", hide_index=True)

        st.markdown("---")
        st.markdown("**💲 Tus precios contra Mercado Libre**")
        explicar(
            "Los productos cuyo precio de lista está lejos de lo que se publica.",
            f"Sale de buscar tus códigos en Mercado Libre ({miga_hasta('Mercado Libre')}): de las publicaciones que son de ese producto se toma el precio "
            "mediano. Un precio de lista muy por debajo suele ser una lista vieja que nadie "
            "actualizó; uno muy por encima, una pieza que no vas a vender.\n\n"
            "**Es una referencia, no una verdad**: en Mercado Libre se publica con envío, con "
            "comisión y a veces con la unidad distinta (un juego contra una pieza)."
        )
        st.session_state.setdefault("ml_veces", 1.6)
        _veces_ml = st.select_slider("A partir de cuántas veces de diferencia:",
                                     options=[1.3, 1.6, 2.0, 3.0], key="ml_veces")
        _lejos_ml = precios_lejos_de_mercado_libre(_veces_ml)
        if _lejos_ml:
            st.dataframe(_lejos_ml, width="stretch", hide_index=True)
        else:
            st.caption("Todavía no hay precios de Mercado Libre para comparar, o ninguno está "
                       "tan lejos." if config_mercado_libre() else
                       f"Hace falta activar Mercado Libre en {miga_hasta('Mercado Libre')}.")

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
            st.success(f"✅ De {miles(revisados_disc)} producto(s) revisados, ninguno faltó en las "
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
        # Lo ya cargado que hoy se vetaría va antes que lo que falta revisar: eso ya está
        # saliendo en el buscador.
        mostrar_aviso_de_lo_aprobado()
        lotes_pendientes = resumen_lotes_pendientes()
        if lotes_pendientes:
            total_pendientes = sum(l["cantidad"] for l in lotes_pendientes)
            st.markdown("**📄 Vínculos de listas de proveedor esperando revisión**")
            explicar(
                "Estos llegaron al importar una lista y todavía NO están cargados.",
                "Se separan solos entre los que no tienen nada raro y los que dispararon alguna alarma, "
                "para que apruebes en bloque los limpios y mires con lupa solo los pocos sospechosos."
            )

            with st.expander(f"🧹 Descartar TODO lo pendiente ({miles(total_pendientes)} vínculos de "
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
                    avisar("success", f"Se descartaron {miles(borrados)} vínculo(s) pendientes.")
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
                _opciones_tanda = OPCIONES_DE_TANDA_DEL_LOTE
                st.session_state.setdefault("cuantos_pendientes", tanda_que_cubre(total_lote))
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
            # Y los pares vistos juntos en un portal: leer fichas no cambia este lote, pero
            # le agrega pruebas a favor a pares que ya estaban acá.
            _clave_analisis = clave_del_analisis_de_lote(
                lote_info["lote"], cuantos, (int(tanda_lote) - 1) * int(cuantos), total_lote)
            _guardado = esperar_el_analisis_en_preparacion()
            _clave_vieja = (_guardado or {}).get("clave") or ()
            if _guardado and _clave_vieja == _clave_analisis:
                limpias, sospechosas, relacionadas = _guardado["resultado"]
            elif (len(_clave_vieja) == len(_clave_analisis)
                    and _clave_vieja[:3] == _clave_analisis[:3]
                    and _clave_vieja[4:] == _clave_analisis[4:]
                    and total_lote < _clave_vieja[3]
                    # Solo si esa tanda cubría la lista entera: si no, al decidir entran pares
                    # de la tanda siguiente que el recorte no analiza, y quedaban sin verse.
                    and _clave_vieja[2] == 0 and _clave_vieja[3] <= _clave_vieja[1]
                    and _guardado.get("recortes", 0) < RECORTES_ANTES_DE_REANALIZAR):
                # SOLO SE SACAN LOS QUE YA SE DECIDIERON. Aprobar o descartar un par bajaba
                # el total y rehacía el análisis entero: 3,7 s sobre la cola real por cada
                # decisión, con el mismo resultado para todos los demás pares. Ahora se sacan
                # los que ya no están pendientes y el resto queda como estaba (0,8 s). Cada
                # RECORTES_ANTES_DE_REANALIZAR decisiones se rehace entero, por lo poco que lo
                # decidido le cambia a lo aprendido de los demás.
                _siguen = pares_pendientes_del_lote(lote_info["lote"])
                limpias, sospechosas, relacionadas = (
                    [x for x in _lista if (x["a"], x["b"]) in _siguen]
                    for _lista in _guardado["resultado"])
                guardar_analisis_de_lote({
                    "clave": _clave_analisis,
                    "resultado": (limpias, sospechosas, relacionadas),
                    "recortes": _guardado.get("recortes", 0) + _clave_vieja[3] - total_lote,
                })
            else:
                with st.spinner("Analizando..."):
                    limpias, sospechosas, relacionadas = analizar_lote_pendiente(
                        lote_info["lote"], limite=int(cuantos),
                        desde=(int(tanda_lote) - 1) * int(cuantos)
                    )
                guardar_analisis_de_lote({
                    "clave": _clave_analisis,
                    "resultado": (limpias, sospechosas, relacionadas),
                })
            analizados = len(limpias) + len(sospechosas) + len(relacionadas)
            st.caption(f"Analizados {miles(analizados)} de {miles(total_lote)} vínculo(s) de esta lista." +
                       (f" Quedan {miles(total_lote - analizados)} — cambiá de tanda para verlos."
                        if total_lote > analizados else ""))

            # El kit y la pieza que trae adentro no son una equivalencia, así que no se
            # preguntan de a uno: van en una línea y se descartan juntos. El buscador igual
            # ofrece el kit cuando alguien busca la pieza suelta.
            if relacionadas:
                st.info(
                    f"📦 **{len(relacionadas)} par(es) son un kit y una pieza que viene "
                    "adentro, o un accesorio y su pieza** (el capuchón y la bobina en la que "
                    "monta). No son equivalentes —no se puede vender una en lugar de la "
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
                    avisar("success", f"Se descartaron {_n} par(es) de kit o accesorio y pieza.")
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
            mn1.metric("🟢 Muy probables", miles(len(por_nivel["🟢"])))
            mn2.metric("🟡 Probables", miles(len(por_nivel["🟡"])))
            mn3.metric("🟠 Dudosas", miles(len(por_nivel["🟠"])))
            mn4.metric("🔴 Casi seguro mal", miles(len(por_nivel["🔴"])))

            # 🧭 EL PLAN. Ver plan_de_la_lista(): qué conviene hacer primero y cuánto trabajo
            # lleva cada paso, para no tener que descubrirlo recorriendo la pantalla.
            _plan = plan_de_la_lista(limpias, sospechosas, relacionadas)
            if _plan:
                with st.expander("🧭 Cómo resolver esta lista, paso a paso", expanded=True):
                    st.dataframe(_plan, width="stretch", hide_index=True)
                    ayuda("De arriba hacia abajo: cada paso achica lo que queda para los "
                          "siguientes. Los que dicen «1 toque» no necesitan mirar par por "
                          "par; los de muestra, solo los que la app elige al azar.")

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
            ml1.metric("Sin nada raro", miles(len(limpias)))
            ml2.metric("Con alguna alarma", miles(len(sospechosas)))

            # Solo en una lista IMPORTADA: ahí sí que casi todo dispare alarmas dice que el mapeo
            # de columnas salió mal. En las automáticas (el barrido de todo el catálogo, el cruce
            # por auto) es lo esperable —se proponen muchos pares para que la revisión filtre— y
            # el consejo de «descartá toda la lista» hacía tirar las 2.558 limpias con el resto.
            if (analizados and len(sospechosas) / analizados > 0.7
                    and lote_info.get("origen") == "lista_proveedor"):
                st.error(
                    "🔴 Más del 70% de esta lista dispara alarmas. Eso no es que tengas mala suerte: "
                    "casi siempre significa que la importación quedó **mal mapeada** — la columna que "
                    "se tomó como código en realidad traía cantidades, medidas o pedazos de la "
                    "descripción. Antes de revisar de a uno, conviene descartar toda la lista y "
                    "volver a importarla revisando bien el mapeo de columnas."
                )

            # APROBAR POR GRUPOS, CON UNA MUESTRA DE CONTROL. Ver muestra_de_control(). Antes lo
            # único que había era «Aprobar los N sin alarmas», a ciegas: nadie sabía cuántos de
            # esos N estaban mal hasta que un cliente se llevaba la pieza equivocada.
            _lote_m = lote_info["lote"]
            _candidatas_m = limpias + sospechosas
            _clave_parecidos = f"_parecidos_{_lote_m}"
            # Los descartes con motivo de la revisión de a uno (ver aplicar_decisiones()): se
            # buscan ahora, contra el análisis nuevo, que ya no tiene a los descartados.
            _por_buscar = st.session_state.get("_buscar_parecidos", {}).pop(_lote_m, None)
            if _por_buscar:
                _hallados_rev = parecidos_de_varios(_por_buscar, _candidatas_m)
                if _hallados_rev:
                    st.session_state[_clave_parecidos] = _hallados_rev
            if st.session_state.get(_clave_parecidos):
                _par_info = st.session_state[_clave_parecidos]
                _filas_par = [f for grupo_p in _par_info for f in grupo_p["filas"]]
                st.info(f"🧠 **Aprendí de lo que descartaste:** hay {len(_filas_par)} par(es) más "
                        "con el mismo problema. Miralos y, si coincidís, descartalos de una.")
                for grupo_p in _par_info:
                    st.caption(f"{grupo_p['motivo']} — como «{grupo_p['ejemplo']}»:")
                    st.dataframe([{"Código A": f["cod_a"], "Marca A": f["marca_a"],
                                   "Descripción A": (f.get("desc_a") or "")[:60],
                                   "Código B": f["cod_b"], "Marca B": f["marca_b"],
                                   "Descripción B": (f.get("desc_b") or "")[:60]}
                                  for f in grupo_p["filas"][:200]],
                                 width="stretch", hide_index=True)
                _pp1, _pp2 = st.columns(2)
                if _pp1.button(f"🚫 Descartar esos {len(_filas_par)} también", type="primary",
                               key=f"desc_parecidos_{_lote_m}"):
                    _n_par = 0
                    for grupo_p in _par_info:
                        _n_par += rechazar_pendientes(
                            _lote_m, [p for f in grupo_p["filas"]
                                      for p in ((f["a"], f["b"]), (f["b"], f["a"]))],
                            motivo=grupo_p["clave_motivo"])
                    st.session_state.pop(_clave_parecidos, None)
                    invalidar_salud()
                    avisar("success", f"Se descartaron {_n_par} par(es) con el mismo problema.")
                    st.rerun()
                if _pp2.button("Dejarlos como están", key=f"dejar_parecidos_{_lote_m}"):
                    st.session_state.pop(_clave_parecidos, None)
                    st.rerun()

            def _panel_de_muestra(lote, clave_g, filas, candidatas, clave_parecidos, nombre):
                """La muestra de control de un grupo: el avance, los pares por mirar de a 10, y el veredicto
                con aprobar o descartar el resto. La usan los grupos por par de listas y los grupos por
                motivo de la revisión. Ver muestra_de_control()."""
                _por_par_g = {(f["a"], f["b"]): f for f in filas}
                clave_g = clave_vigente_de_la_muestra(clave_g, list(_por_par_g))
                if "|vuelta " in clave_g:
                    nombre = f"{nombre} ({clave_g.rsplit('|', 1)[1]})"
                _muestra = muestra_de_control(clave_g, list(_por_par_g))
                _estado_m = estado_de_la_muestra(_muestra)
                _sin_mirar = [p for p in _muestra if _estado_m[p] == "pendiente"]
                _bien_m = sum(1 for p in _muestra if _estado_m[p] == "bien")
                _mal_m = sum(1 for p in _muestra if _estado_m[p] == "mal")
                # Lo que se aprueba o descarta con esta muestra son los que estaban cuando se
                # sorteó. Los que entraron después esperan su propia muestra: ver
                # clave_vigente_de_la_muestra().
                _al_sortear = pares_al_sortear(clave_g)
                _resto = [p for p in _por_par_g if p not in set(_muestra) and p in _al_sortear]
                _entraron_despues = [p for p in _por_par_g
                                     if p not in _al_sortear and p not in set(_muestra)]
                st.progress((_bien_m + _mal_m) / max(len(_muestra), 1),
                            text=f"Muestra: {_bien_m + _mal_m} de {len(_muestra)} revisados · "
                                 f"✅ {_bien_m} bien · 🚫 {_mal_m} mal")

                # Los que quedan por mirar, de a 10 y en un formulario: marcar no recarga la
                # pantalla, y todo se guarda junto con un botón.
                _a_mirar = [p for p in _sin_mirar if p in _por_par_g][:10]
                if _a_mirar:
                    # La primera opción dice para qué es: el selector va sin rótulo, al lado
                    # de la decisión, y con «—» solo no se entendía.
                    _opciones_mot = (["Si está mal: ¿por qué? (opcional)"]
                                     + list(MOTIVOS_DE_RECHAZO.values()))
                    _clave_de_motivo = {v: k for k, v in MOTIVOS_DE_RECHAZO.items()}
                    with st.form(key=f"form_muestra_{abs(hash(clave_g))}"):
                        st.caption(f"Quedan {len(_sin_mirar)} de la muestra. Marcá estos "
                                   f"{len(_a_mirar)} y guardá.")
                        for _i_m, _par in enumerate(_a_mirar):
                            _f = _por_par_g[_par]
                            # Compacto: cada par eran cinco renglones y diez pares, dos
                            # pantallas. La decisión y el motivo van en la misma fila.
                            st.markdown(f"**{_i_m + 1}.** {_f['marca_a']} **{_f['cod_a']}** ↔ "
                                        f"{_f['marca_b']} **{_f['cod_b']}**")
                            # En negrita, los datos con números que el otro no dice.
                            _da, _db = (_f.get('desc_a') or '')[:160], (_f.get('desc_b') or '')[:160]
                            st.caption(f"A: {resaltar_lo_que_difiere(_da, _db)}  \n"
                                       f"B: {resaltar_lo_que_difiere(_db, _da)}")
                            _cd, _cm = st.columns([1, 1])
                            _cd.radio("¿Son la misma pieza?", ["—", "✅ Bien", "🚫 Mal"],
                                      key=f"m_dec_{_par[0]}_{_par[1]}", horizontal=True,
                                      label_visibility="collapsed")
                            _cm.selectbox("Si está mal, ¿por qué?", _opciones_mot,
                                          key=f"m_mot_{_par[0]}_{_par[1]}",
                                          label_visibility="collapsed",
                                          help="Solo si está mal: el motivo enseña a la revisión.")
                        _guardar_m = st.form_submit_button("💾 Guardar lo marcado",
                                                           type="primary")
                    if _guardar_m:
                        _bien_ahora, _mal_ahora = [], {}
                        for _par in _a_mirar:
                            _dec = st.session_state.get(f"m_dec_{_par[0]}_{_par[1]}")
                            if _dec == "✅ Bien":
                                _bien_ahora.append(_par)
                            elif _dec == "🚫 Mal":
                                _mot = _clave_de_motivo.get(
                                    st.session_state.get(f"m_mot_{_par[0]}_{_par[1]}"))
                                _mal_ahora.setdefault(_mot, []).append(_par)
                        if _bien_ahora:
                            aprobar_pendientes(lote, [p for a, b in _bien_ahora
                                                         for p in ((a, b), (b, a))])
                        _rechazados_m = []
                        for _mot, _pares_mot in _mal_ahora.items():
                            rechazar_pendientes(lote, [p for a, b in _pares_mot
                                                          for p in ((a, b), (b, a))],
                                                motivo=_mot)
                            if _mot:
                                _rechazados_m.extend((_mot, _por_par_g[_par])
                                                     for _par in _pares_mot)
                        _muestra_set = set(_muestra)
                        _parecidos_nuevos = parecidos_de_varios(
                            _rechazados_m, [f for f in candidatas
                                            if (f["a"], f["b"]) not in _muestra_set])
                        if _parecidos_nuevos:
                            st.session_state[clave_parecidos] = _parecidos_nuevos
                        invalidar_salud()
                        _n_mal = sum(len(v) for v in _mal_ahora.values())
                        avisar("success", f"Guardado: ✅ {len(_bien_ahora)} bien · 🚫 {_n_mal} mal.")
                        st.rerun()
                elif _sin_mirar:
                    st.caption("Los que faltan de la muestra ya no están en esta tanda: los "
                               "resolvió otra persona o cambió el análisis.")

                if _entraron_despues:
                    st.info(
                        f"➕ **{miles(len(_entraron_despues))} par(es) entraron a este grupo después "
                        "de sortear la muestra** —una prueba nueva los subió, o llegaron con "
                        "otra tanda—. Esta muestra no habla de ellos, así que no se aprueban con "
                        "ella: cuando termines con los de esta muestra, van a tener la suya.")

                # EL VEREDICTO, cuando la muestra está completa.
                _revisados_m = _bien_m + _mal_m
                if not _a_mirar and _revisados_m:
                    _p_m, _tope_m, _n_tope_m = estimacion_de_errores(_mal_m, _revisados_m,
                                                                     len(_resto))
                    _pares_resto = [p for a, b in _resto for p in ((a, b), (b, a))]
                    if not _resto:
                        st.success(f"✅ El grupo entero ya está revisado ({_revisados_m} pares).")
                    elif se_puede_aprobar_el_resto(_mal_m, _revisados_m):
                        (st.success if _mal_m == 0 else st.warning)(
                            (f"✅ **Ningún error en {_revisados_m}.** " if _mal_m == 0 else
                             f"🟡 **{_mal_m} error(es) en {_revisados_m}.** ")
                            + f"Del resto del grupo se puede esperar como mucho {_tope_m:.0%} "
                            f"mal —unos {_n_tope_m} de {miles(len(_resto))}—. Alcanza para aprobarlo.")
                    elif _mal_m * 2 < _revisados_m and _tope_m <= 0.25:
                        st.warning(
                            f"🟡 **{_mal_m} error(es) en {_revisados_m}.** Todavía no alcanza: "
                            f"en el resto podría haber hasta {_tope_m:.0%} mal (unos "
                            f"{_n_tope_m} de {miles(len(_resto))}). Mirá "
                            f"{TAMANO_DE_LA_MUESTRA} más: si no aparecen errores nuevos, se "
                            "habilita la aprobación.")
                    else:
                        st.error(
                            f"🔴 **{_mal_m} errores en {_revisados_m}.** Aprobar el resto a "
                            f"ciegas metería alrededor de {miles(_p_m * len(_resto), 0)} vínculos "
                            "malos. Mejor revisarlos uno por uno abajo, o mirar 30 más para "
                            "ver si los errores se concentran en algo que se pueda descartar "
                            "de una.")
                    if _resto:
                        _v1, _v2 = st.columns(2)
                        if se_puede_aprobar_el_resto(_mal_m, _revisados_m) and _v1.button(
                                f"✅ Aprobar los {miles(len(_resto))} que quedan del grupo",
                                type="primary" if _mal_m == 0 else "secondary",
                                key=f"apr_resto_{abs(hash(clave_g))}"):
                            _n_ap = aprobar_pendientes(lote, _pares_resto)
                            invalidar_salud()
                            avisar("success", f"Se aprobaron {miles(_n_ap)} vínculo(s) del grupo "
                                              f"{nombre}.")
                            st.rerun()
                        if _v2.button(f"➕ Mirar {TAMANO_DE_LA_MUESTRA} más",
                                      key=f"ampliar_{abs(hash(clave_g))}"):
                            muestra_de_control(clave_g, list(_por_par_g), ampliar=True)
                            st.rerun()
                        if _mal_m >= 2 and _mal_m * 2 >= _revisados_m:
                            if st.button(f"🚫 Descartar los {miles(len(_resto))} que quedan del grupo",
                                         key=f"rec_resto_{abs(hash(clave_g))}"):
                                rechazar_pendientes(lote, _pares_resto)
                                invalidar_salud()
                                avisar("success", f"Se descartó el resto del grupo {nombre}.")
                                st.rerun()

            _grupos_m = grupos_de_limpias(limpias)
            if _grupos_m:
                st.markdown("**🎯 Aprobar las limpias por grupos, con una muestra de control**")
                explicar(
                    "Revisás 30 pares al azar de un grupo y, según cuántos estén mal, aprobás "
                    "el resto de una.",
                    "«Sin alarmas» no quiere decir «bien»: quiere decir que el análisis no "
                    "encontró nada en contra. Cuántos están mal de verdad solo se sabe "
                    "mirando.\n\n"
                    "Cada grupo son las limpias entre dos listas. La app elige unas cuantas al "
                    "azar —30, 50 u 80 según el tamaño del grupo; siempre las mismas, aunque "
                    "recargues o "
                    "las mire otra persona— y vos marcás cada una. Con lo que salga, la app "
                    "te dice cuántos errores se pueden esperar en el resto y te deja aprobarlo "
                    "entero de un toque.\n\n"
                    "Cuando marcás uno como malo y decís por qué, la app busca en la lista los "
                    "que tienen el mismo problema y te los ofrece para descartar juntos."
                )
                # Se elige por el PAR DE LISTAS y no por el rótulo: el rótulo lleva la cantidad,
                # y al guardar la muestra la cantidad cambia. Elegido por el rótulo, el
                # selector dejaba de encontrar lo elegido y saltaba al grupo más grande, con la
                # persona a mitad de la muestra de otro.
                _por_grupo = {(ma, mb, fr): filas_g for ma, mb, filas_g, fr in _grupos_m}
                _clave_sel_g = f"grupo_muestra_{_lote_m}"
                if st.session_state.get(_clave_sel_g) not in _por_grupo:
                    st.session_state.pop(_clave_sel_g, None)
                _elegido_g = st.selectbox(
                    "Grupo:", list(_por_grupo), key=_clave_sel_g,
                    format_func=lambda g: (f"{g[0]} ↔ {g[1]}"
                                           + {"alta": " · confianza alta",
                                              "media": " · confianza media"}.get(g[2], "")
                                           + f" — {miles(len(_por_grupo[g]))} limpias"))
                _ma_g, _mb_g, _fr_g = _elegido_g
                _filas_g = _por_grupo[_elegido_g]
                _clave_g = clave_de_grupo(_lote_m, _ma_g, _mb_g, _fr_g)
                if _fr_g:
                    st.caption(
                        "Este par de listas es grande y se partió en dos: las de confianza "
                        f"alta ({CONFIANZA_ALTA} o más) y las de confianza media. Cada una tiene "
                        "su muestra, así los errores de las de confianza media no se esconden "
                        "entre miles de las otras.")
                _panel_de_muestra(_lote_m, _clave_g, _filas_g, _candidatas_m, _clave_parecidos,
                                  f"{_ma_g} ↔ {_mb_g}"
                                  + (f" (confianza {_fr_g})" if _fr_g else ""))
                st.markdown("---")

            # 🪭 LOS ABANICOS: un producto con varios candidatos distintos en otra lista. Se
            # eligen a mano, de a un producto: ver abanicos_para_elegir().
            _abanicos = abanicos_para_elegir(limpias, sospechosas)
            # Primero los fáciles: los que ya tienen una sugerida (ver pieza_sugerida_del_abanico())
            # y, entre esos, los de menos opciones. Antes iban primero los de más candidatos, que
            # son justo los más difíciles, y el avance se sentía nulo.
            _abanicos.sort(key=lambda a: (pieza_sugerida_del_abanico(a) is None,
                                          len(candidatos_por_pieza(a))))
            if _abanicos:
                st.markdown(f"**🪭 Elegí cuál es la equivalente** — {len(_abanicos)} producto(s)")
                explicar(
                    "Productos que coinciden con varios productos distintos de otra lista. "
                    "Como mucho uno es el mismo: elegilo.",
                    "Pasa cuando una descripción es vaga —«Jta.Tapa Cil. TOYOTA HILUX», sin "
                    "motor— o nombra muchos autos, y encaja con varias piezas de la otra lista. "
                    "Ninguna regla puede elegir entre ellas; una persona sí.\n\n"
                    "Cada opción es una pieza con todas sus variantes (la misma junta en otro "
                    "material o espesor); si el producto dice su espesor, se aprueban solo las "
                    "de ese espesor. Marcá la que es la misma pieza y tildá «Ya lo miré» para "
                    "descartar las demás. Si no tildás, solo se aprueba la marcada y el resto "
                    "queda para después.\n\n"
                    "La marcada con ⭐ viene ya elegida: es la que mejor coincide —más modelo, "
                    "motor y cilindrada en común— y le gana a todas las demás. Si no es, sacala."
                )
                _por_pag_ab = 5
                _pags_ab = (len(_abanicos) - 1) // _por_pag_ab + 1
                _pag_ab = (st.number_input(f"Página (de {_pags_ab}):", min_value=1,
                                           max_value=_pags_ab, value=1, step=1,
                                           key=f"pag_abanicos_{_lote_m}")
                           if _pags_ab > 1 else 1)
                _estos_ab = _abanicos[(int(_pag_ab) - 1) * _por_pag_ab:int(_pag_ab) * _por_pag_ab]
                with st.form(key=f"form_abanicos_{_lote_m}_{_pag_ab}"):
                    for _i_ab, _ab in enumerate(_estos_ab):
                        _prod = _ab["producto"]
                        st.markdown(f"**{_prod['marca']} {_prod['cod']}** — "
                                    f"{len(_ab['candidatos'])} candidatos en {_ab['marca_otra']}")
                        st.caption((_prod.get("desc") or "")[:160])
                        # Lo que distingue a cada opción, a la vista: ver tabla_del_abanico().
                        st.dataframe(tabla_del_abanico(_ab), width="stretch", hide_index=True)
                        _opciones_ab = {}
                        for _base, _filas_b in candidatos_por_pieza(_ab):
                            _f = _filas_b[0]
                            _lado_o = "b" if _f["a"] == _prod["id"] else "a"
                            _opciones_ab[_base] = (
                                f"{_f[f'cod_{_lado_o}']}"
                                + (f" (+{len(_filas_b) - 1} variantes)" if len(_filas_b) > 1 else "")
                                + f" — {(_f.get(f'desc_{_lado_o}') or '')[:80]}")
                        _sugerida_ab = pieza_sugerida_del_abanico(_ab)
                        if _sugerida_ab in _opciones_ab:
                            _opciones_ab[_sugerida_ab] = "⭐ " + _opciones_ab[_sugerida_ab]
                        st.multiselect("Las que son la misma pieza:", list(_opciones_ab),
                                       placeholder="Elegí la o las que son la misma pieza…",
                                       default=[_sugerida_ab] if _sugerida_ab in _opciones_ab
                                       else [],
                                       format_func=lambda k, o=_opciones_ab: o[k],
                                       key=f"ab_sel_{_prod['id']}_{_ab['marca_otra']}")
                        st.checkbox("Ya lo miré: las que no marqué no son",
                                    key=f"ab_listo_{_prod['id']}_{_ab['marca_otra']}")
                        st.markdown("")
                    _guardar_ab = st.form_submit_button("💾 Guardar estos", type="primary")
                if _guardar_ab:
                    _n_ap_ab = _n_rec_ab = 0
                    for _ab in _estos_ab:
                        _k = f"{_ab['producto']['id']}_{_ab['marca_otra']}"
                        _bases_sel = set(st.session_state.get(f"ab_sel_{_k}") or [])
                        _sel = {(f["a"], f["b"]) for _base, _filas_b in candidatos_por_pieza(_ab)
                                if _base in _bases_sel for f in _filas_b}
                        _listo = st.session_state.get(f"ab_listo_{_k}")
                        if _sel:
                            _n_ap_ab += aprobar_pendientes(_lote_m, [p for a, b in _sel
                                                                     for p in ((a, b), (b, a))])
                        if _listo:
                            _resto_ab = [(f["a"], f["b"]) for f in _ab["candidatos"]
                                         if (f["a"], f["b"]) not in _sel]
                            if _resto_ab:
                                _n_rec_ab += rechazar_pendientes(
                                    _lote_m, [p for a, b in _resto_ab for p in ((a, b), (b, a))],
                                    motivo="otra_pieza")
                    invalidar_salud()
                    avisar("success", f"Guardado: ✅ {_n_ap_ab} aprobado(s) · 🚫 {_n_rec_ab} "
                                      "descartado(s).")
                    st.rerun()
                st.markdown("---")

            pares_limpios = []
            for x in limpias:
                pares_limpios.extend([(x["a"], x["b"]), (x["b"], x["a"])])
            with st.expander("Otras acciones sobre toda la lista"):
                st.caption("Aprobar sin muestra es aprobar a ciegas: nadie sabe cuántos están "
                           "mal. Conviene usar la muestra de arriba.")
                bl1, bl2 = st.columns(2)
                bl1.button(f"✅ Aprobar los {len(limpias)} sin alarmas, sin muestra",
                            key=f"apr_limpias_{lote_info['lote']}",
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
                    f"📚 **De {miles(dato['decisiones'])} vínculos {ma}↔{mb} que revisaste, descartaste "
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

            # Los que están en revisión SOLO por el abanico se eligen arriba, en «Elegí cuál es
            # la equivalente»: acá serían cientos de pares sueltos con el mismo motivo.
            sospechosas = [x for x in sospechosas
                           if not (x.get("alarmas") and all(a.startswith("🪭")
                                                            for a in x["alarmas"]))]
            # 📋 PARA REVISAR, POR MOTIVO. Ver grupos_por_motivo(). Antes la única forma era la
            # lista de abajo, de a 10 por página: con 8.000 pares en revisión, eso no se termina.
            _grupos_mot = grupos_por_motivo(sospechosas)
            if _grupos_mot:
                st.markdown("---")
                st.markdown(f"**📋 Para revisar, por motivo** — {miles(len(sospechosas))} par(es) "
                            f"en {len(_grupos_mot)} motivo(s)")
                explicar(
                    "Los pares en revisión agrupados por el motivo. Los que el texto contradice "
                    "se descartan de una; los dudosos, con una muestra.",
                    "**🚫 Se descartan**: los dos textos dicen que son piezas distintas —otro "
                    "auto, otro motor, otra cantidad de cilindros, junta de cárter contra junta "
                    "de tapa—, o las medidas no dan. Mirá los ejemplos y descartá el grupo "
                    "entero.\n\n"
                    "**🎯 Con muestra**: la app no pudo decidir —«nada dice que sean la misma "
                    "pieza», el precio, un código que apunta a dos productos—. Se resuelven igual "
                    "que las limpias: mirás una muestra y, según lo que salga, aprobás o "
                    "descartás el resto.\n\n"
                    "Abajo sigue la lista de a uno, para el que quiera ir par por par."
                )
                _etiqueta_rec = {"descartar": "🚫 Descartar el grupo", "muestra": "🎯 Con muestra"}
                st.dataframe([{"Motivo": m, "Pares": len(fs), "Qué conviene": _etiqueta_rec[r]}
                              for m, r, fs in _grupos_mot],
                             width="stretch", hide_index=True)
                _por_motivo_g = {m: (r, fs) for m, r, fs in _grupos_mot}
                _clave_sel_mot = f"motivo_elegido_{_lote_m}"
                if st.session_state.get(_clave_sel_mot) not in _por_motivo_g:
                    st.session_state.pop(_clave_sel_mot, None)
                _motivo_g = st.selectbox(
                    "Motivo:", list(_por_motivo_g), key=_clave_sel_mot,
                    format_func=lambda m: f"{m} — {miles(len(_por_motivo_g[m][1]))} "
                                          f"({_etiqueta_rec[_por_motivo_g[m][0]]})")
                _rec_g, _filas_mot = _por_motivo_g[_motivo_g]
                if _rec_g == "descartar":
                    import random as _random
                    _ejemplos = _random.Random(_motivo_g).sample(_filas_mot, min(8, len(_filas_mot)))
                    st.caption("Ejemplos al azar del grupo:")
                    st.dataframe([{"A": f"{f['marca_a']} {f['cod_a']} — {(f.get('desc_a') or '')[:60]}",
                                   "B": f"{f['marca_b']} {f['cod_b']} — {(f.get('desc_b') or '')[:60]}",
                                   "Por qué": (f["alarmas"][0] if f.get("alarmas") else "")[:80]}
                                  for f in _ejemplos], width="stretch", hide_index=True)
                    _dm1, _dm2 = st.columns(2)
                    if _dm1.button(f"🚫 Descartar los {miles(len(_filas_mot))}", type="primary",
                                   key=f"desc_motivo_{_lote_m}_{abs(hash(_motivo_g))}"):
                        _n_dm = rechazar_pendientes(
                            _lote_m, [p for f in _filas_mot for p in ((f["a"], f["b"]), (f["b"], f["a"]))],
                            motivo=motivo_de_rechazo_del_grupo(_motivo_g))
                        invalidar_salud()
                        avisar("success", f"Se descartaron {miles(_n_dm)} par(es) de «{_motivo_g}».")
                        st.rerun()
                    _mirar_antes = _dm2.checkbox("Prefiero mirar una muestra antes",
                                                 key=f"muestra_motivo_{_lote_m}_{abs(hash(_motivo_g))}")
                else:
                    _mirar_antes = True
                if _mirar_antes:
                    _panel_de_muestra(_lote_m, f"{_lote_m}|motivo|{_motivo_g}", _filas_mot,
                                      _candidatas_m, _clave_parecidos, f"«{_motivo_g}»")

            if sospechosas:
                st.markdown("---")
                st.markdown("**🔎 De a uno**")
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
                    # El «¿por qué?» del descarte: con él, la app busca los parecidos (ver
                    # aplicar_decisiones()). Opcional: descartar sin decirlo sigue andando.
                    if st.session_state[_clave_g] == "🚫 Descartar":
                        _clave_mg = f"mot_{_clave_g}"
                        _motivos_rev = motivos_del_lote(_lote_rev)
                        _ya_mot = {(_motivos_rev.get(par) or (None,))[0] for par in _pares_grupo}
                        st.session_state[_clave_mg] = (MOTIVOS_DE_RECHAZO.get(_ya_mot.pop(), "—")
                                                       if len(_ya_mot) == 1 else "—")
                        st.selectbox("¿Por qué? (opcional: sirve para encontrar los parecidos)",
                                     ["—"] + list(MOTIVOS_DE_RECHAZO.values()), key=_clave_mg,
                                     on_change=anotar_motivo, args=(_lote_rev, _clave_mg, items))
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
                                if st.session_state[_clave_p] == "🚫 Descartar":
                                    _clave_mp = f"mot_{_clave_p}"
                                    st.session_state[_clave_mp] = MOTIVOS_DE_RECHAZO.get(
                                        (motivos_del_lote(_lote_rev).get((s["a"], s["b"]))
                                         or (None,))[0], "—")
                                    st.selectbox("¿Por qué?", ["—"] + list(MOTIVOS_DE_RECHAZO.values()),
                                                 key=_clave_mp, on_change=anotar_motivo,
                                                 args=(_lote_rev, _clave_mp, [s]))
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

        # QUÉ TAN BIEN ACIERTA LA APP, con tus decisiones. Plegado: se mira de vez en cuando,
        # y lo que se viene a hacer acá es revisar. Ver aciertos_de_la_revision().
        with st.expander("📏 ¿Qué tan bien acierta la app? (medido con lo que decidiste)"):
            _ac = aciertos_de_la_revision()
            if _ac["muestras"]:
                st.markdown("**Muestras de control** — pares «limpios» sorteados al azar que "
                            "revisaste de a uno. Es la medida más honesta.")
                st.dataframe(_ac["muestras"], width="stretch", hide_index=True)
                st.caption("«Mal en el grupo (hasta)»: con 95 % de seguridad, el grupo entero "
                           "no tiene más mal que eso. Con 0 mal en 30, igual puede haber hasta "
                           "11 %: mirar más achica el margen.")
            else:
                st.info("Todavía no revisaste ninguna muestra de control. Cuando lo hagas, acá "
                        "vas a ver cuántos de los «limpios» estaban mal de verdad.")
            if _ac["por_banda"]:
                st.markdown("**Por confianza** — lo que decidiste según cómo lo había puntuado "
                            "la app. Incluye lo aprobado en bloque, así que el verde sale mejor "
                            "de lo que es.")
                st.dataframe(_ac["por_banda"], width="stretch", hide_index=True)
            if _ac["por_alarma"]:
                st.markdown("**Por alarma** — de lo que cada alarma mandó a revisión, cuánto "
                            "aprobaste igual. Si una se equivoca seguido, avisá: es una regla "
                            "para ajustar.")
                st.dataframe(_ac["por_alarma"], width="stretch", hide_index=True)
            if not _ac["con_datos"]:
                st.caption("La confianza y la alarma de cada par se anotan al decidir desde "
                           "esta versión: las tablas por confianza y por alarma se van a ir "
                           "llenando a medida que revises.")

        # LOS CONTROLES DE LO YA CARGADO VAN DESPUÉS de la revisión de las listas. Estaban
        # arriba de todo, y lo que se viene a hacer a esta pantalla —revisar lo que espera
        # aprobación— quedaba tercero, abajo de dos botones que se usan de vez en cuando.
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
            ma1.metric("Vínculos revisados", miles(resultado_aud["total_revisados"]))
            ma2.metric("Códigos raros", miles(len(resultado_aud.get("codigos_malos", []))))
            ma3.metric("Conflictos", miles(len(resultado_aud["conflictos"])))
            ma4.metric("Medidas que no dan", miles(len(resultado_aud["por_medidas"])))

            if resultado_aud.get("quedo_corta"):
                st.warning(
                    f"⚠️ **La revisión quedó corta.** Se miraron {miles(resultado_aud['total_revisados'])} "
                    f"de {miles(resultado_aud['total_en_base'])} vínculos que hay cargados. Resolvé estos "
                    "y volvé a auditar para seguir con el resto — todavía puede haber problemas sin ver."
                )

            # 1) Códigos que no parecen códigos: lo que deja una importación mal mapeada.
            #    Va primero porque un solo producto basura ensucia decenas de vínculos.
            if resultado_aud.get("codigos_malos"):
                st.markdown("**🚫 Códigos que no parecen códigos de repuesto**")
                ayuda(
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
                st.markdown("**🚩 Productos con vínculos que no son la misma pieza (revisalos primero)**")
                explicar(
                    "Muchos vínculos no es malo: lo malo es que no cuadren entre sí.",
                    "Una sonda que va en 60 autos y cita 7 originales tiene, con razón, muchos "
                    "equivalentes. Lo que aparece acá es otra cosa: un producto pegado a piezas "
                    "de otro rubro o de autos que no tienen nada que ver —casi siempre basura de "
                    "una importación mal mapeada—. Un vínculo cuadra seguro si los dos citan el "
                    "mismo código original, y los que ya marcaste como correctos no cuentan.\n\n"
                    "«Cortar los que no cuadran» deja los buenos; «Cortar todos» limpia el "
                    "producto entero."
                )
                # Sin desplegables: Streamlit los cierra en cada refresco, y como cada botón
                # provoca uno, se cerraba la ventana justo cuando estabas revisando.
                for p in resultado_aud["productos_sospechosos"][:15]:
                    # La descripción cortada: las de FISPA traen 60 autos y ocupaban una
                    # pantalla entera de celular cada una.
                    _desc_p = p["descripcion"] or ""
                    desc = (texto_para_html(_desc_p[:140] + ("…" if len(_desc_p) > 140 else ""))
                            or "_(sin descripción)_")
                    _malos = p["no_cuadran"]
                    _rubros = ", ".join(f"{r} ({n})" for r, n in p["rubros"].most_common(3))
                    st.markdown(
                        f"**{texto_para_html(p['marca'])}** · `{p['codigo']}` — {desc}  \n"
                        f"<small>**{len(_malos)} de sus {p['cantidad']} vínculos no cuadran**"
                        + (f" · rubros de sus vínculos: {texto_para_html(_rubros)}" if _rubros else "")
                        + (f" · y {p['cantidad_oem']} original(es)" if p.get("cantidad_oem") else "")
                        + "</small>", unsafe_allow_html=True)
                    for v, motivo in _malos[:3]:
                        _dv = v["descripcion"] or ""
                        st.caption(f"✗ {v['marca']} · {v['codigo']} — {_dv[:70]}"
                                   f"{'…' if len(_dv) > 70 else ''} — {motivo}")
                    if len(_malos) > 3:
                        st.caption(f"… y {len(_malos) - 3} más que no cuadran.")
                    ps1, ps2 = st.columns(2)
                    ps1.button(f"✂️ Cortar los {len(_malos)} que no cuadran",
                               key=f"cortar_malos_{p['id']}", type="primary",
                               on_click=cb_auditoria_cortar_pares,
                               args=([v["par"] for v, _m in _malos],),
                               help="Quedan los vínculos que sí son la misma pieza")
                    ps2.button(f"✂️ Cortar todos ({p['total']})",
                               key=f"cortar_todo_{p['id']}",
                               on_click=cb_auditoria_cortar_todos, args=(p["id"],),
                               help="El producto queda; se cortan TODAS sus equivalencias, "
                                    "las de los códigos originales también")
                    st.markdown("")
                if len(resultado_aud["productos_sospechosos"]) > 15:
                    st.caption(f"(mostrando 15 de {len(resultado_aud['productos_sospechosos'])})")
                st.markdown("---")

            # 2) Conflictos agrupados: un código de fábrica apuntando a varios productos
            if resultado_aud["conflictos"]:
                st.markdown("**⚠️ Un código de fábrica apuntando a varios productos del mismo proveedor**")
                ayuda(
                    "Acá se ven juntos todos los productos a los que apunta cada código, para poder "
                    "comparar y cortar el que sobra. Normalmente uno tiene descripción real y el otro "
                    "es el que quedó mal.\n\nSolo salen los que NO pueden ser la misma pieza: "
                    "otro rubro, otros autos, un juego contra una pieza suelta. Que un original "
                    "apunte a dos productos de la misma lista es normal cuando la lista trae dos "
                    "fabricantes (FISPA y LUCAS en la de FISPA), y esos no se muestran."
                )
                if resultado_aud.get("originales_con_parecidos"):
                    st.caption(f"✅ Otros {miles(resultado_aud['originales_con_parecidos'])} "
                               "originales apuntan a varios productos que sí son la misma pieza: "
                               "no hace falta revisarlos.")
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
                    if g.get("motivo"):
                        st.caption(f"❗ {g['motivo']}")
                    if g["descripcion_oem"]:
                        _do = g["descripcion_oem"]
                        st.caption(_do[:140] + ("…" if len(_do) > 140 else ""))
                    for p in g["productos"]:
                        _dp = p["descripcion"] or ""
                        desc = (texto_para_html(_dp[:140] + ("…" if len(_dp) > 140 else ""))
                                or "⚠️ _(sin descripción — sospechoso)_")
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
        if not st.session_state.get("reglas_de_hoy_arriba"):
            mostrar_revision_de_lo_aprobado()

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
                        url_ficha = url_de_la_ficha(info_ficha["url_ficha_template"],
                                                    info_ficha["codigo_raw"])
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

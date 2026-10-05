"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/.

🗂️ Administrar → 🧹 Mantenimiento → 🔎 Encontrar equivalencias: sus herramientas, en el orden
en que se muestran. Corre después de pantallas/mantenimiento.py, que elige el grupo."""

# ============================================================
# MANTENIMIENTO → ENCONTRAR EQUIVALENCIAS
# ============================================================
if pagina == PAGINAS[3]:
    if sub_admin == SUB_ADMIN[4]:
        if _grupo_mant == GRUPOS_MANTENIMIENTO[0]:
            st.markdown("**🏭 Catálogo de aplicaciones (qué repuesto le va a cada auto)**")
            explicar(
                "El catálogo que dice a qué auto le va cada repuesto. NGK, Bosch, Mann y SKF "
                "publican el suyo gratis.",
                "Es distinto de una lista de precios: una lista dice cuánto cuesta un código, un "
                "catálogo de aplicaciones dice **a qué auto le va**.\n\nBuscalo en el sitio del "
                "fabricante como «catálogo de aplicaciones» y subilo acá. Con esto, buscar por VIN "
                "o por vehículo deja de adivinar desde las descripciones del proveedor."
            )
            try:
                c.execute("""SELECT marca_repuesto AS "Marca", COUNT(*) AS "Aplicaciones",
                                    COUNT(DISTINCT marca_auto) AS "Marcas de auto",
                                    COUNT(DISTINCT codigo) AS "Códigos"
                             FROM aplicaciones GROUP BY marca_repuesto ORDER BY 2 DESC""")
                ya_cargadas = filas_a_listas(c)
            except sqlite3.OperationalError as _err:
                anotar_error("nivel principal", _err)
                ya_cargadas = []
            if ya_cargadas:
                st.dataframe(ya_cargadas, width="stretch", hide_index=True)

            # LAS QUE SALEN DE TU PROPIO CATÁLOGO, sin subir nada. Va ARRIBA del archivo a
            # propósito: el que llega acá con la tabla vacía no necesita salir a buscar el PDF
            # de NGK, necesita apretar un botón. Sobre las descripciones reales salen 114.673
            # aplicaciones de 87 marcas de auto.
            #
            # Y sobre todo: esto es la SALIDA DE EMERGENCIA. La deducción la hace sola la tarea
            # de fondo, pero hasta ahora no había forma de pedirla a mano, así que si el hilo
            # se moría a la mitad —que es lo que venía pasando— la tabla quedaba en cero para
            # siempre y el usuario no tenía ningún botón que apretar.
            st.caption("O sin subir nada, deduciéndolas de las descripciones que ya tenés:")
            _cd1, _cd2 = cols([2, 3])
            if _cd1.button("🧠 Deducir de mis descripciones", key="deducir_aplic_a_mano",
                            help="Lee las descripciones del catálogo y saca a qué auto le va "
                                 "cada pieza. Tarda cerca de un minuto."):
                with st.spinner("Leyendo las descripciones..."):
                    try:
                        _ded = aplicaciones_desde_descripciones()
                        _n_ded = aplicar_aplicaciones_deducidas(_ded) if _ded else 0
                        guardar_config("aplicaciones_deducidas", str(_n_ded))
                        guardar_config("aplicaciones_fecha",
                                       datetime.now().strftime("%Y-%m-%d %H:%M"))
                        _quedo_hecho("aplicaciones_pendientes")
                        invalidar_salud()
                        avisar("success", f"Se dedujeron {_n_ded:,} aplicaciones de tus "
                                          "descripciones.")
                    except Exception as _err:
                        anotar_error("deducir_aplicaciones_a_mano", _err)
                        st.error(f"No se pudo: {type(_err).__name__}: {_err}")
                st.rerun()
            _cd2.caption("Son las que la app puede sacar sola de lo que ya importaste. "
                         "No reemplazan al catálogo del fabricante: lo complementan.")

            arch_aplic = subir_archivo("Catálogo de aplicaciones (.pdf o .xlsx):",
                                        ["pdf", "xlsx", "csv"], "aplicaciones")
            ca_m, ca_t = cols(2)
            marca_aplic = ca_m.text_input("¿De qué marca de repuesto es este catálogo?",
                                           placeholder="Ej: NGK, Bosch, Mann", key="marca_aplic").strip()
            # El tipo de pieza no es un dato decorativo: es lo que después permite cruzar catálogos
            # sin mezclar una bujía con un filtro por el solo hecho de ir al mismo auto.
            tipo_aplic = ca_t.selectbox(
                "¿Qué tipo de pieza trae?", ["(elegir)"] + sorted(FAMILIAS_REPUESTO.keys()),
                key="tipo_aplic",
                help="Importante: con esto la app puede después cruzar los catálogos de dos "
                     "fabricantes y deducir equivalencias, sin confundir rubros distintos."
            )
            tipo_aplic = "" if tipo_aplic == "(elegir)" else tipo_aplic
            if arch_aplic:
                archivo_listo(arch_aplic, "catálogo")
                boton_otro_archivo("aplicaciones", "🗑️ Usar otro", key="otro_aplic")
                if st.button("🔎 Leer el catálogo", disabled=not (marca_aplic and tipo_aplic)):
                    with st.spinner("Leyendo... en un PDF grande puede tardar un rato"):
                        try:
                            tablas = tablas_de_archivo(arch_aplic)
                            apps = []
                            for tabla in tablas:
                                # OJO con el nombre: 'cols' es una función de esta app. Llamar así a
                                # la variable la pisa a nivel global y cualquier cols(3) posterior
                                # revienta. Ya pasó antes; por eso la auditoría lo chequea.
                                posiciones = detectar_columnas_aplicaciones(tabla)
                                apps += parsear_catalogo_aplicaciones(
                                    tabla, posiciones["modelo"], posiciones["motor"],
                                    posiciones["comb"], posiciones["anios"], posiciones["codigo"]
                                )
                        except Exception as e:
                            anotar_error("nivel principal", e)
                            apps = []
                            st.error(f"No se pudo leer: {type(e).__name__}: {e}")
                    if apps:
                        st.session_state["aplic_leidas"] = apps
                        if len({a["marca_auto"] for a in apps}) < 2:
                            st.warning(
                                "⚠️ Se reconoció una sola marca de auto. Si este archivo en realidad "
                                "es una **lista de precios**, no va acá: cargala en "
                                "**📁 Cargar Excel**."
                            )
                        marcas_detectadas = sorted({a["marca_auto"] for a in apps})
                        st.success(f"Se reconocieron {len(apps):,} aplicaciones de "
                                   f"{len(marcas_detectadas)} marca(s) de auto.")
                        st.caption("Revisá esta muestra antes de guardar:")
                        st.dataframe(apps[:40], width="stretch", hide_index=True)
                    elif arch_aplic:
                        st.warning(
                            "No reconocí aplicaciones en ese archivo. Esta lectura espera la forma "
                            "habitual de estos catálogos: la marca del auto sola en una fila, y "
                            "debajo modelo, motorización, años y código."
                        )

            if st.session_state.get("aplic_leidas"):
                apps_pend = st.session_state["aplic_leidas"]
                if st.button(f"💾 Guardar las {len(apps_pend):,} aplicaciones", type="primary"):
                    n = guardar_aplicaciones(apps_pend, marca_aplic,
                                              getattr(arch_aplic, "name", "catálogo"), tipo_aplic)
                    st.session_state.pop("aplic_leidas", None)
                    invalidar_salud()
                    avisar("success", f"Se guardaron {n:,} aplicaciones de {marca_aplic.upper()}.")
                    st.rerun()

            # Un índice arriba de todo: son seis formas distintas de generar equivalencias y
            # cada una necesita cosas distintas. Sin este resumen hay que bajar leyendo panel
            # por panel para saber cuál se puede usar hoy.
            st.markdown("### 🔗 Generar equivalencias")
            # Con valor inicial: si la consulta falla, el índice tiene que dibujarse igual en
            # vez de tumbar la pantalla entera por un contador.
            marcas_con_tipo = 0
            _n_desc = _n_med = _n_reemp = 0
            try:
                c.execute("""SELECT COUNT(DISTINCT marca_repuesto) FROM aplicaciones
                             WHERE COALESCE(tipo_pieza,'') <> ''""")
                marcas_con_tipo = c.fetchone()[0]
            except sqlite3.OperationalError as _err:
                anotar_error("nivel principal", _err)
                marcas_con_tipo = 0
            try:
                c.execute("SELECT COUNT(*) FROM productos WHERE COALESCE(descripcion,'') <> ''")
                _n_desc = c.fetchone()[0]
                c.execute(f"SELECT COUNT(*) FROM productos WHERE {CAMPOS_MEDIDAS[0][0]} IS NOT NULL")
                _n_med = c.fetchone()[0]
                c.execute("SELECT COUNT(*) FROM reemplazos_codigo")
                _n_reemp = c.fetchone()[0]
            except sqlite3.OperationalError as _err:
                anotar_error("nivel principal", _err)
                pass
            _n_portales = sum(1 for _m in (filas_a_listas(c.execute(
                "SELECT nombre FROM marcas WHERE tipo <> 'OEM'")) or [])
                if config_portal(_m["nombre"]))

            st.dataframe([
                {"Método": "🔤 Por descripción",
                 "Qué necesita": "dos proveedores con descripciones",
                 "Estado": f"listo — {_n_desc:,} productos con descripción" if _n_desc > 50
                            else "faltan productos con descripción"},
                {"Método": "📐 Por medidas",
                 "Qué necesita": "3 o más medidas cargadas, en marcas distintas",
                 "Estado": f"listo — {_n_med:,} con medidas" if _n_med > 5
                            else "todavía no hay medidas cargadas"},
                {"Método": "🔄 Por cambio de número",
                 "Qué necesita": "reemplazos cargados a mano",
                 "Estado": f"listo — {_n_reemp} reemplazo(s)" if _n_reemp
                            else "cargá reemplazos en «Códigos reemplazados»"},
                {"Método": "🏭 Cruzando catálogos",
                 "Qué necesita": "2 catálogos de fabricante del mismo tipo de pieza",
                 "Estado": f"listo — {marcas_con_tipo} marca(s)" if marcas_con_tipo >= 2
                            else f"tenés {marcas_con_tipo}, hacen falta 2"},
                {"Método": "🔐 Portal del proveedor",
                 "Qué necesita": "el link de la ficha de un producto (y la clave, si pide)",
                 "Estado": f"listo — {_n_portales} portal(es)" if _n_portales
                            else "sin configurar"},
                {"Método": "🧾 Confirmadas por venta",
                 "Qué necesita": "usar «Se llevó» en el mostrador",
                 "Estado": "corre solo, una vez por día"},
            ], width="stretch", hide_index=True)
            st.caption("Cada método está en un panel más abajo. Todos mandan a revisión: "
                       "ninguno carga equivalencias directo.")
            st.markdown("---")

            # Cada panel con SU condición. Estaban los cinco dentro de «si hay 2 catálogos
            # de fabricante», y cuatro no los necesitan: medidas, reemplazos, portal y
            # descripciones andan sin ningún catálogo cargado. Así quedaban invisibles.
            st.markdown("**📐 Equivalencias por medidas**")
            explicar(
                "La evidencia más fuerte que hay: no es texto, es la pieza física.",
                "Las medidas se venían usando solo para verificar un vínculo que ya "
                "existía. Pero en retenes, o'rings, rulemanes y bujes la medida **es** la "
                "identidad: un 35x52x7 de un proveedor y un 35x52x7 de otro son el mismo "
                "repuesto, sin importar cómo se llame el código ni cómo esté escrita la "
                "descripción.\n\nSe piden al menos 3 medidas coincidentes: con una sola "
                "—el diámetro interno, por ejemplo— coincidirían piezas completamente "
                "distintas que casualmente miden lo mismo. Y se compara igual el nombre de "
                "la pieza, porque una arandela y un retén pueden medir exactamente igual."
            )
            if st.button("📐 Buscar equivalencias por medidas"):
                with st.spinner("Comparando medidas..."):
                    st.session_state["deriv_med"] = derivar_equivalencias_por_medidas()
            _dm = st.session_state.get("deriv_med")
            if _dm is not None:
                if not _dm:
                    st.info(
                        "No salió ninguna. Hacen falta productos con al menos 3 medidas "
                        "cargadas, de marcas distintas. Se cargan en la ficha de cada "
                        "producto o al importar, si la lista trae columnas de medidas."
                    )
                else:
                    st.success(f"{len(_dm)} par(es) con las mismas medidas.")
                    st.dataframe(quitar_id(_dm), width="stretch", hide_index=True)
                    if st.button(f"📥 Mandar las {len(_dm)} a revisión", key="env_med"):
                        _n = guardar_equivalencias_derivadas(
                            [(x["_a"], x["_b"]) for x in _dm],
                            f"POR MEDIDAS · {datetime.now():%d/%m %H:%M}")
                        st.session_state.pop("deriv_med", None)
                        invalidar_salud()
                        avisar("success", f"{_n} equivalencia(s) para revisar.")
                        st.rerun()
            st.markdown("---")

            st.markdown("**🔄 Reunir lo que separó un cambio de número**")
            explicar(
                "Cuando el fabricante cambia el número, la cadena se parte en dos islas.",
                "Tenés un producto vinculado al código de fábrica viejo y otro al nuevo. "
                "Son el mismo repuesto, pero para la app quedaron sin relación.\n\nLos "
                "reemplazos que cargaste ya sabían que el viejo y el nuevo son lo mismo: "
                "esto usa ese dato para volver a unirlos."
            )
            try:
                _pu = equivalencias_puenteadas_por_reemplazo()
            except Exception as _err:
                anotar_error("nivel principal", _err)
                _pu = []
            if not _pu:
                st.caption(
                    "Nada para reunir. Aparece cuando cargues reemplazos y tengas productos "
                    "de los dos códigos."
                )
            else:
                st.success(f"{len(_pu)} par(es) que el cambio de número había separado.")
                st.dataframe(quitar_id(_pu), width="stretch", hide_index=True)
                if st.button(f"📥 Mandar los {len(_pu)} a revisión", key="env_puente"):
                    _n = guardar_equivalencias_derivadas(
                        [(x["_a"], x["_b"]) for x in _pu],
                        f"POR REEMPLAZO DE CÓDIGO · {datetime.now():%d/%m %H:%M}")
                    invalidar_salud()
                    avisar("success", f"{_n} equivalencia(s) para revisar.")
                    st.rerun()
            st.markdown("---")

            st.markdown("**🔐 Portal del proveedor: autos y productos que muestra juntos**")
            explicar(
                "Para cuando la descripción se corta, y para relacionar lo que el proveedor ya "
                "relacionó.",
                "De cada ficha del portal se sacan dos cosas:\n\n"
                "- **Los autos.** La ficha tiene la lista completa; la celda de Excel no. Con "
                "esos autos cargados, la app puede vincular productos de dos proveedores "
                "aunque sus descripciones no compartan ni un modelo.\n"
                "- **Los productos que muestra al lado.** Un distribuidor como JL vende el "
                "mismo repuesto en varias marcas, y en la ficha de uno muestra los otros. "
                "Esos pares van a revisión en su propia lista («PORTAL …») y además cuentan "
                "como una prueba a favor cuando el mismo par llega por otro camino.\n\n"
                "**No decide solo.** Un portal no tiene todas las relaciones, y en la misma "
                "página puede haber «productos relacionados» que no son la misma pieza. Es "
                "una prueba más: si las medidas, el rubro o el auto dicen otra cosa, el par "
                "se descarta igual. Una ficha que nombra más de "
                f"{MAXIMO_PRODUCTOS_POR_FICHA} productos tuyos es un listado y no cuenta.\n\n"
                "**Cargarlo es pegar un link.** Abrí en el navegador la ficha de cualquier "
                "producto de ese proveedor, copiá la dirección y pegala en «➕ Cargar un "
                "portal», acá abajo. La app encuentra el código en el link, arma la dirección "
                "para todos los demás y la prueba antes de guardarla. Si el portal no pide "
                "contraseña —como el de Wega— no hace falta nada más.\n\n"
                "**Si pide usuario y clave**, eso va aparte, en Settings → Secrets de "
                "Streamlit (la dirección de la ficha ya la tiene la app):\n\n```\n[portal_JL]\n"
                'url_login = "https://proveedor.com/login"\nusuario = "tu_usuario"\n'
                'clave = "tu_clave"\ncampo_usuario = "email"\ncampo_clave = "password"\n```\n\n'
                "El nombre después de `portal_` es la marca tal como está cargada en la app "
                "(la de la lista del proveedor). Los nombres de `campo_usuario` y "
                "`campo_clave` son los `name=` del formulario de acceso del portal.\n\n"
                "**Va en los secretos y no en la base** "
                "por una razón concreta: la base se baja como backup y se sube a GitHub. "
                "Una clave ahí queda publicada.\n\n**La app no puede pedir nada.** La "
                "sesión que se abre es de solo lectura: los métodos para enviar datos "
                "(post, put, delete) directamente no existen en ella, así que ni un error "
                "de programación podría mandar un pedido. Y las direcciones que dicen "
                "carrito, pedido, comprar o checkout se rechazan aunque sean de solo "
                "consulta, porque hay portales que agregan al carrito con un simple enlace."
            )
            st.info(
                "🔒 **La app solo puede leer fichas.** No puede hacer pedidos, ni reservas, "
                "ni modificar nada en el portal del proveedor. Está bloqueado por diseño, "
                "no por configuración: nadie puede activarlo sin querer."
            )
            try:
                c.execute("""SELECT m.id, m.nombre, COUNT(p.id) AS n,
                                    COALESCE(m.url_ficha_template, '') AS plantilla
                             FROM marcas m
                             JOIN productos p ON p.marca_id = m.id
                             WHERE m.tipo <> 'OEM'
                             GROUP BY m.id ORDER BY n DESC""")
                _marcas_portal = filas_a_listas(c)
            except sqlite3.OperationalError as _err:
                anotar_error("nivel principal", _err)
                _marcas_portal = []

            # ➕ CARGAR UN PORTAL: pegar el link de la ficha de un producto. Ver
            # plantilla_desde_un_ejemplo() y probar_plantilla_de_portal().
            with st.expander("➕ Cargar un portal", expanded=not any(
                    config_portal(x["nombre"]) for x in _marcas_portal)):
                _faltan_conocidos = [m for m in PORTALES_CONOCIDOS
                                     if not any(portal_conocido(x["nombre"])
                                                == PORTALES_CONOCIDOS[m]
                                                for x in _marcas_portal)]
                if _faltan_conocidos:
                    st.caption(
                        f"Portales que ya conozco: {', '.join(_faltan_conocidos)}. Todavía no "
                        "tenés su lista cargada; cuando la cargues, aparecen acá listos para "
                        "probar sin pegar nada.")
                if not _marcas_portal:
                    st.caption("Primero cargá la lista de algún proveedor.")
                else:
                    _et_nuevo = {f"{x['nombre']} ({x['n']:,} productos)"
                                 + (" · ya tiene portal" if x["plantilla"] else ""): x
                                 for x in _marcas_portal}
                    _marca_n = _et_nuevo[st.selectbox("Proveedor:", list(_et_nuevo),
                                                      key="portal_nuevo_marca")]
                    _link_n = st.text_input(
                        "Link de la ficha de UN producto de ese proveedor:",
                        placeholder="https://www.proveedor.com.ar/producto/FAP-2033",
                        key=f"portal_nuevo_link_{_marca_n['id']}",
                        help="Abrilo en el navegador, en la web del proveedor, y copiá la "
                             "dirección de arriba. Tiene que ser un producto que esté en tu "
                             "lista de ese proveedor.")
                    _cod_n = st.text_input(
                        "Código de ese producto (solo si la app no lo encuentra sola):",
                        key=f"portal_nuevo_cod_{_marca_n['id']}")
                    # Wega y los demás de PORTALES_CONOCIDOS no necesitan el link: la dirección
                    # ya se sabe. Se prueba igual antes de guardarla.
                    _conocido_n = portal_conocido(_marca_n["nombre"])
                    _usar_conocido = False
                    if _conocido_n and not _link_n:
                        st.caption(f"Ya conozco el portal de {_marca_n['nombre']}: "
                                   f"`{_conocido_n}`. No hace falta pegar nada.")
                        _usar_conocido = st.button(f"🔎 Probar el portal de {_marca_n['nombre']}",
                                                   key="portal_conocido_probar")
                    if _usar_conocido:
                        _a_probar_c = [(r["codigo_raw"], r["codigo_clean"]) for r in c.execute(
                            """SELECT codigo_raw, codigo_clean FROM productos WHERE marca_id = ?
                               ORDER BY (COALESCE(stock, 0) > 0) DESC, RANDOM() LIMIT 2""",
                            (_marca_n["id"],)).fetchall()]
                        with st.spinner("Abriendo las fichas..."):
                            _prueba_c = probar_plantilla_de_portal(_conocido_n, _a_probar_c)
                        st.session_state["portal_nuevo"] = {
                            "marca_id": _marca_n["id"], "nombre": _marca_n["nombre"],
                            "plantilla": _conocido_n, "prueba": _prueba_c}
                    if st.button("🔎 Probar", key="portal_nuevo_probar", disabled=not _link_n):
                        if _cod_n.strip():
                            _codigos_n = [_cod_n.strip()]
                        else:
                            _codigos_n = [r["codigo_raw"] for r in c.execute(
                                "SELECT codigo_raw FROM productos WHERE marca_id = ?",
                                (_marca_n["id"],)).fetchall()]
                        _plantilla_n, _cod_hallado, _err_n = plantilla_desde_un_ejemplo(
                            _link_n, _codigos_n)
                        if _err_n:
                            st.session_state.pop("portal_nuevo", None)
                            st.warning(_err_n)
                        else:
                            # Se prueba con el del ejemplo y con otro de la lista, con stock si
                            # hay: que ande con uno solo puede ser casualidad.
                            _otro_n = c.execute(
                                """SELECT codigo_raw, codigo_clean FROM productos
                                   WHERE marca_id = ? AND codigo_clean <> ?
                                   ORDER BY (COALESCE(stock, 0) > 0) DESC, RANDOM() LIMIT 1""",
                                (_marca_n["id"], sanitizar(_cod_hallado))).fetchone()
                            _a_probar = [(_cod_hallado, sanitizar(_cod_hallado))] + (
                                [(_otro_n["codigo_raw"], _otro_n["codigo_clean"])]
                                if _otro_n else [])
                            with st.spinner("Abriendo las fichas..."):
                                _prueba_n = probar_plantilla_de_portal(_plantilla_n, _a_probar)
                            st.session_state["portal_nuevo"] = {
                                "marca_id": _marca_n["id"], "nombre": _marca_n["nombre"],
                                "plantilla": _plantilla_n, "prueba": _prueba_n}
                    _nuevo = st.session_state.get("portal_nuevo")
                    if _nuevo and _nuevo["marca_id"] == _marca_n["id"]:
                        st.markdown(f"Dirección para cada producto: `{_nuevo['plantilla']}`")
                        st.dataframe(_nuevo["prueba"], width="stretch", hide_index=True)
                        _anda = any(f["Resultado"].startswith("✅") for f in _nuevo["prueba"])
                        if not _anda:
                            st.caption(
                                "Ninguna ficha se pudo leer bien. Probá con el link de otro "
                                "producto, o con el de la búsqueda del sitio "
                                "(«…/buscar?q=FAP2033»). Si igual no anda, el sitio arma la "
                                "página con JavaScript y no se puede leer así.")
                        if st.button("💾 Guardar el portal", key="portal_nuevo_guardar",
                                     type="primary" if _anda else "secondary"):
                            with db_lock:
                                c.execute("UPDATE marcas SET url_ficha_template = ? WHERE id = ?",
                                          (_nuevo["plantilla"], _nuevo["marca_id"]))
                                conn.commit()
                            olvidar_sesion_de_catalogo(_nuevo["nombre"])
                            _SESIONES_PORTAL.pop(_nuevo["nombre"], None)
                            st.session_state.pop("portal_nuevo", None)
                            avisar("success",
                                   f"Portal de {_nuevo['nombre']} guardado. Ya se puede leer "
                                   "abajo, y además sirve para las fotos y para el link a la "
                                   "ficha en el buscador.")
                            st.rerun()
            _con_portal = [x for x in _marcas_portal if config_portal(x["nombre"])]
            if not _con_portal:
                st.caption(
                    "Todavía no hay ningún portal cargado: empezá por «➕ Cargar un portal». "
                    "Y fijate si el proveedor deja **exportar el catálogo a Excel** desde su "
                    "portal: bajarlo y cargarlo por «Cargar Excel» es todavía más confiable."
                )
            else:
                _et_p = {f"{x['nombre']} ({x['n']:,} productos) · "
                         + ("público" if config_portal(x["nombre"]).get("publico")
                            else "con usuario y clave"): x
                         for x in _con_portal}
                _sel_p = st.selectbox("Proveedor:", list(_et_p.keys()), key="portal_marca")
                _marca_p = _et_p[_sel_p]
                try:
                    _leidas_p = c.execute(
                        """SELECT COUNT(*), SUM(productos_juntos > 0),
                                  SUM(productos_juntos IS NULL)
                           FROM fichas_de_portal_leidas WHERE portal = ?""",
                        (_marca_p["nombre"],)).fetchone()
                    _pares_p = c.execute(
                        "SELECT COUNT(*) FROM productos_juntos_en_portal WHERE portal = ?",
                        (_marca_p["nombre"],)).fetchone()[0]
                except sqlite3.OperationalError as _err:
                    anotar_error("portal/avance", _err)
                    _leidas_p, _pares_p = (0, 0, 0), 0
                if _leidas_p and _leidas_p[0]:
                    st.caption(
                        f"Leídas {_leidas_p[0]:,} de {_marca_p['n']:,} fichas · "
                        f"{int(_leidas_p[1] or 0):,} mostraban otros productos tuyos · "
                        f"{_pares_p:,} pares vistos juntos"
                        + (f" · {int(_leidas_p[2]):,} sin ficha" if _leidas_p[2] else ""))
                _cuantos = st.select_slider("Leer fichas de:", options=[10, 25, 50, 100, 200],
                                             format_func=lambda x: f"{x} productos",
                                             key="portal_cuantos")
                ayuda(
                    "Se hace de a tandas chicas y con una pausa entre pedidos. No es "
                    "lentitud: golpear el servidor del proveedor a máxima velocidad es la "
                    "forma más rápida de que te bloqueen la cuenta. Cada tanda sigue donde "
                    "quedó la anterior."
                )
                if st.button("🔐 Entrar y leer las fichas"):
                    _barra = st.progress(0.0, text="Entrando al portal...")
                    _res = leer_fichas_del_portal(
                        _marca_p["id"], _marca_p["nombre"], int(_cuantos),
                        progreso=lambda f, t: _barra.progress(f, text=t))
                    _barra.empty()
                    if _res["error"] and not (_res["leidas"] - _res["sin_ficha"]):
                        st.error(_res["error"])
                    elif not _res["leidas"]:
                        st.info("Ya se leyeron todas las fichas de esa marca.")
                    else:
                        invalidar_salud()
                        _msj = (f"Se leyeron {_res['leidas']} ficha(s): {_res['con_autos']} con "
                                f"autos y {_res['con_productos']} que muestran otros productos "
                                "tuyos.")
                        if _res["nuevos"]:
                            _msj += (f" **{_res['nuevos']} par(es) nuevos para revisar** en "
                                     f"«{_res['lote']}».")
                        elif _res["pares"]:
                            _msj += (f" Los {_res['pares']} par(es) ya estaban cargados o para "
                                     "revisar: ahí cuentan como una prueba más a favor.")
                        if _res["sin_ficha"]:
                            _msj += f" {_res['sin_ficha']} no se pudieron abrir."
                        if _res["listados"]:
                            _msj += (f" {_res['listados']} ficha(s) nombraban demasiados "
                                     "productos y se tomaron como listados.")
                        if _res["error"]:
                            _msj += f" Se cortó antes: {_res['error']}"
                        avisar("success", _msj)
                        st.rerun()
            st.markdown("---")

            st.markdown("**🏭 Catálogos de fabricantes: se leen solos**")
            explicar(
                "SKF, MANN-FILTER y las bujías NGK, por los códigos que tus listas citan.",
                "Tus listas nombran piezas de fabricantes que no son proveedores tuyos: «BOMBA "
                "DE AGUA … SKF VKPC85304», «BUJIA … NGK= BP5HS», «REF ORIG MANN P 716». Esos "
                "fabricantes publican una ficha por código con los números originales y las "
                "equivalencias de otras marcas. La app abre la ficha de cada código citado y, si "
                "ahí aparece el código de otro producto tuyo, los anota como «el catálogo de SKF "
                "los muestra juntos».\n\n"
                "**No decide nada solo**: suma como una prueba a favor, y los pares que no "
                "estaban van a revisión en su propia lista («CATÁLOGO …»).\n\n"
                "No hay que cargar nada: las direcciones son públicas. Corre en segundo plano, "
                "**sin tope por día**, hasta leer todo lo pendiente. Si un sitio no responde "
                "cinco veces seguidas —o falla más de la mitad de una tanda—, se pausa una "
                "hora y retoma solo.\n\n"
                "FRAM, MAHLE, BOSCH, TARANTO y CORVEN no están porque sus catálogos buscan con un "
                "formulario, sin una dirección por código. Si encontrás el link de la ficha de "
                "alguno, cargalo arriba en «➕ Cargar un portal»."
            )
            _auto_cat = st.toggle("Leerlos solos en segundo plano",
                                  value=catalogos_de_fabricante_automaticos(),
                                  key="catalogos_fabricante_toggle")
            if _auto_cat != catalogos_de_fabricante_automaticos():
                prender_tarea_de_fondo("catalogos", "catalogos_fabricante_automaticos", _auto_cat)
                st.rerun()
            try:
                st.dataframe(estado_de_los_catalogos_de_fabricante_guardado(),
                             hide_index=True, width="stretch")
            except Exception as _err:
                anotar_error("panel de catálogos de fabricante", _err)
            if st.button("🏭 Leer una tanda ahora", key="leer_catalogos_ahora"):
                _barra_c = st.progress(0.0, text="Leyendo catálogos...")
                _res_c = {"leidas": 0, "pares": 0, "nuevos": 0, "errores": []}
                for _i_c, _nombre_c in enumerate(CATALOGOS_DE_FABRICANTE):
                    _barra_c.progress(_i_c / len(CATALOGOS_DE_FABRICANTE),
                                      text=f"{_nombre_c}...")
                    _r_c = leer_catalogo_de_fabricante(_nombre_c, cuantos=10)
                    for _k in ("leidas", "pares", "nuevos"):
                        _res_c[_k] += _r_c[_k]
                    if _r_c["error"]:
                        _res_c["errores"].append(f"{_nombre_c}: {_r_c['error']}")
                _barra_c.empty()
                estado_de_los_catalogos_de_fabricante_guardado.clear()
                invalidar_salud()
                avisar("success" if not _res_c["errores"] else "warning",
                       f"Se leyeron {_res_c['leidas']} ficha(s); {_res_c['pares']} par(es) "
                       f"vistos juntos, {_res_c['nuevos']} nuevos para revisar."
                       + (" No respondieron: " + "; ".join(_res_c["errores"])
                          if _res_c["errores"] else ""))
                st.rerun()
            st.markdown("---")

            st.markdown("**🛒 Mercado Libre: pistas y precio de mercado**")
            explicar(
                "Busca tus códigos en Mercado Libre: relaciona productos y trae el precio que "
                "se publica.",
                "Las publicaciones de autopartes traen el número de pieza y, en el título, las "
                "equivalencias con las que el vendedor quiere que lo encuentren. De cada código "
                "tuyo se miran solo las publicaciones donde el código aparece de verdad (y la "
                "marca, si no es un código de fábrica), y de ahí salen:\n\n"
                "- **Pistas para relacionar**: si nombran el código de otro producto tuyo, "
                "cuenta como una prueba a favor («las publicaciones de Mercado Libre los muestran "
                "juntos») y el par va a revisión. No decide nada solo.\n"
                "- **El precio de mercado**: la mediana de lo publicado, para ver en Estadísticas "
                "→ 📌 Para pedir qué precios de tus listas quedaron atrasados.\n\n"
                "**Cómo se activa (una sola vez):** entrá a developers.mercadolibre.com.ar con tu "
                "cuenta, «Crear aplicación» (es gratis), y copiá el *App ID* y la *Secret Key* en "
                "Settings → Secrets de Streamlit, en su propia sección, al final de todo:\n\n"
                "```toml\n[mercadolibre]\nclient_id = \"el App ID\"\n"
                "client_secret = \"la Secret Key\"\n```\n\n"
                "Van en los secretos y no en la app porque la base se sube a GitHub con cada "
                "copia. Después corre solo, **sin tope por día**, hasta buscar todo el catálogo: "
                "primero lo que tenés en stock. Si Mercado Libre rechaza, descansa una hora."
            )
            if not config_mercado_libre():
                st.info("Todavía no está cargada la aplicación de Mercado Libre: mirá «ℹ️» "
                        "arriba para activarla.")
            else:
                _auto_ml = st.toggle("Buscar solo en segundo plano",
                                     value=obtener_config("mercado_libre_automatico", "1") == "1",
                                     key="mercado_libre_toggle")
                if _auto_ml != (obtener_config("mercado_libre_automatico", "1") == "1"):
                    prender_tarea_de_fondo("mercado_libre", "mercado_libre_automatico", _auto_ml)
                    st.rerun()
                try:
                    _ml = c.execute("""SELECT COUNT(*), SUM(publicaciones > 0),
                                              SUM(precio_mediano IS NOT NULL)
                                       FROM mercado_libre_leidos""").fetchone()
                    _ml_pares = c.execute("""SELECT COUNT(*) FROM productos_juntos_en_portal
                                             WHERE portal = 'MERCADO LIBRE'""").fetchone()[0]
                    st.caption(f"Buscados: {_ml[0] or 0:,} · con publicaciones suyas: "
                               f"{_ml[1] or 0:,} · con precio de mercado: {_ml[2] or 0:,} · "
                               f"pares vistos juntos: {_ml_pares:,}")
                except sqlite3.OperationalError as _err:
                    anotar_error("panel de Mercado Libre", _err)
                _prueba_ml = st.text_input("Probar con un código:", key="ml_prueba",
                                           placeholder="Ej: 40011 fispa")
                if _prueba_ml and st.button("🔍 Buscar", key="ml_probar"):
                    _pubs, _err_ml = buscar_en_mercado_libre(_prueba_ml)
                    if _err_ml:
                        st.error(_err_ml)
                    else:
                        st.dataframe([{"Título": p["titulo"], "Precio": p["precio"],
                                       "Nº de pieza": p["atributos"].get("PART_NUMBER", ""),
                                       "Marca": p["atributos"].get("BRAND", ""),
                                       "Link": p["link"]} for p in _pubs],
                                     hide_index=True, width="stretch")
                if st.button("🛒 Buscar una tanda ahora", key="ml_tanda"):
                    _barra_ml = st.progress(0.0, text="Buscando en Mercado Libre...")
                    _res_ml = leer_mercado_libre(
                        cuantos=30, progreso=lambda f, t: _barra_ml.progress(f, text=t))
                    _barra_ml.empty()
                    if _res_ml["error"] and not _res_ml["buscados"]:
                        st.error(_res_ml["error"])
                    else:
                        invalidar_salud()
                        avisar("success",
                               f"Se buscaron {_res_ml['buscados']}: {_res_ml['con_publicaciones']} "
                               f"con publicaciones suyas, {_res_ml['con_precio']} con precio de "
                               f"mercado, {_res_ml['nuevos']} par(es) nuevos para revisar.")
                        st.rerun()
            st.markdown("---")

            st.markdown("**🔤 Vincular dos proveedores por la descripción**")
            explicar(
                "Para las listas que NO traen el código de fábrica, que son la mayoría.",
                "Sin esa columna, la app no puede generar ninguna equivalencia: es la "
                "limitación de fondo que arrastramos. Esto la resuelve comparando lo que dicen "
                "las descripciones.\n\nSe exige coincidencia en el **nombre de la pieza** —no "
                "solo en el auto—, y que no se contradigan la **posición** ni la "
                "**cilindrada**. Ese control es el que evita el error grave: «CAPUCHON BUJIA "
                "CRUZE» y «ANILLO BUJIA CRUZE» comparten el rubro y el auto, y son piezas "
                "distintas.\n\nComo todo lo deducido, va a la cola de revisión: el sistema de "
                "confianza las evalúa igual que a cualquier otra."
            )
            try:
                c.execute("""SELECT m.id, m.nombre, COUNT(p.id) AS n FROM marcas m
                             JOIN productos p ON p.marca_id = m.id
                             WHERE COALESCE(p.descripcion,'') <> ''
                             GROUP BY m.id HAVING n >= 20 ORDER BY n DESC""")
                _marcas_desc = filas_a_listas(c)
            except sqlite3.OperationalError as _err:
                anotar_error("nivel principal", _err)
                _marcas_desc = []
            if len(_marcas_desc) < 2:
                st.caption("Hacen falta al menos dos marcas con descripciones cargadas.")
            else:
                _et = {f"{x['nombre']} ({x['n']:,} productos)": x["id"] for x in _marcas_desc}
                cd1, cd2 = cols(2)
                _ma = cd1.selectbox("Proveedor A:", list(_et.keys()), key="desc_marca_a")
                _mb = cd2.selectbox("Proveedor B:", list(_et.keys()),
                                     index=min(1, len(_et) - 1), key="desc_marca_b")
                # El tope no es solo lentitud: es que las filas que quedan afuera son SIEMPRE
                # las mismas —las últimas de cada lista— y no se comparan nunca. Callarlo hace
                # creer que se revisó todo. Sobre una lista real de 25.875 productos son casi
                # 22.000 que no entran, o sea el 85% del proveedor.
                _cuenta = {x["id"]: x["n"] for x in _marcas_desc}
                _grandes = [(nombre, _cuenta.get(mid, 0)) for nombre, mid in
                            ((_ma, _et[_ma]), (_mb, _et[_mb]))
                            if _cuenta.get(mid, 0) > TOPE_PRODUCTOS_POR_COMPARACION]
                if _grandes:
                    st.warning(
                        "⚠️ " + " y ".join(f"**{n.split(' (')[0]}** tiene {c:,} productos"
                                            for n, c in _grandes)
                        + f", y esta comparación mira las primeras "
                          f"{TOPE_PRODUCTOS_POR_COMPARACION:,} de cada una. El resto no se "
                          "compara nunca, porque son siempre las mismas filas las que quedan "
                          "afuera.\n\nPara recorrer el catálogo entero sin tope, usá "
                          "**🧠 Buscar equivalencias en TODO el catálogo de una**, más abajo."
                    )
                if st.button("🔤 Buscar equivalencias por descripción",
                              disabled=(_ma == _mb)):
                    with st.spinner("Comparando descripciones..."):
                        st.session_state["deriv_desc"] = derivar_equivalencias_por_descripcion(
                            _et[_ma], _et[_mb])
                _dd = st.session_state.get("deriv_desc")
                if _dd is not None:
                    if not _dd:
                        st.info(
                            "No salió ninguna. Puede ser que las descripciones de esos dos "
                            "proveedores sean muy distintas entre sí, o que ya estén vinculados."
                        )
                    else:
                        st.success(f"Se encontraron {len(_dd)} posibles equivalencias.")
                        st.dataframe(quitar_id(_dd), width="stretch", hide_index=True)
                        st.caption(
                            "Mirá la columna «Por qué» antes de mandarlas: dice exactamente en "
                            "qué coinciden. Si ves algo que no cierra, avisame y ajusto el criterio."
                        )
                        if st.button(f"📥 Mandar las {len(_dd)} a revisión", type="primary"):
                            _lote_d = f"POR DESCRIPCIÓN · {_ma[:14]}↔{_mb[:14]} · {datetime.now():%d/%m %H:%M}"
                            _n = guardar_equivalencias_derivadas(
                                [(x["_a"], x["_b"]) for x in _dd], _lote_d)
                            st.session_state.pop("deriv_desc", None)
                            invalidar_salud()
                            avisar("success", f"{_n} equivalencia(s) quedaron para revisar.")
                            st.rerun()
            st.markdown("---")


            if marcas_con_tipo >= 2:
                st.markdown("**🔗 Equivalencias deducidas cruzando catálogos**")
                explicar(
                    "Si dos fabricantes dicen que sus piezas van al mismo auto, son intercambiables.",
                    "Ninguna lista de proveedor te lo dice: sale de cruzar catálogos que ya "
                    "tenés.\n\nSolo se cruzan códigos del **mismo tipo de pieza**, de fabricantes "
                    "**distintos**, y que coincidan en **varios autos** — con uno solo podría ser "
                    "casualidad."
                )
                if st.button("🔗 Buscar equivalencias entre catálogos"):
                    with st.spinner("Cruzando..."):
                        st.session_state["derivadas"] = derivar_equivalencias_de_aplicaciones()
                derivadas = st.session_state.get("derivadas")
                if derivadas is not None:
                    if not derivadas:
                        st.info(
                            "No salió ninguna. Puede ser que los catálogos cargados sean de tipos de "
                            "pieza distintos, o que sus códigos todavía no estén en tus listas."
                        )
                    else:
                        st.success(f"Se dedujeron {len(derivadas)} equivalencia(s) posibles.")
                        st.dataframe(quitar_id(derivadas), width="stretch", hide_index=True)
                        ayuda(
                            "No se cargan directo: van a la cola de revisión, donde el análisis de "
                            "confianza las evalúa como a cualquier otra. Por buena que sea la "
                            "deducción, sigue siendo una deducción."
                        )
                        if st.button(f"📥 Mandar las {len(derivadas)} a revisión", type="primary"):
                            lote_der = f"CATÁLOGOS DE FABRICANTE · {datetime.now():%d/%m %H:%M}"
                            n = guardar_equivalencias_derivadas(
                                [(x["_a"], x["_b"]) for x in derivadas], lote_der)
                            st.session_state.pop("derivadas", None)
                            invalidar_salud()
                            avisar("success", f"{n} equivalencia(s) quedaron para revisar.")
                            st.rerun()
                st.markdown("---")

        if _grupo_mant == GRUPOS_MANTENIMIENTO[0]:
            st.markdown("**📝 Códigos de fábrica que el proveedor escribió en la descripción**")
            explicar(
                "Recorre las descripciones ya cargadas y busca los códigos que el proveedor "
                "marcó con «REF ORIG», «//» u «OEM», y que además tenés en el catálogo.",
                "Buscar el código de fábrica adentro del texto ya existía, pero **solo en el "
                "momento de importar**, detrás de una casilla que viene apagada. Si esa casilla "
                "no se tildó, ese dato no se vuelve a mirar nunca más: la descripción queda "
                "guardada con el número adentro y nadie lo lee otra vez.\n\n"
                "Y aunque se tilde, igual hace falta correrlo después: el cruce solo existe "
                "cuando están las DOS listas. Una descripción que cita «REF ORIG 0258006980» no "
                "sirve de nada hasta que se importe la lista que vende ese Bosch — y para "
                "entonces la importación de la primera ya pasó hace meses.\n\n"
                "**Solo toma los códigos DECLARADOS**, no los que se podrían adivinar. La "
                "diferencia está medida sobre tu base: los declarados dan 1,1% de pares entre "
                "familias distintas y los adivinados 8,7% (los vínculos que vos ya aprobaste a "
                "mano dan 0,8%). El motivo es simple: en «SONDA LAMBDA 80045 AUDI A3» el 80045 "
                "es el número interno de ESE proveedor, y choca con el número interno de otro "
                "sin tener nada que ver.\n\n"
                "No carga nada solo: todo va a la cola de pendientes."
            )
            if st.button("📝 Buscar los códigos escritos"):
                with st.spinner("Leyendo las descripciones del catálogo..."):
                    st.session_state["sug_escritos"] = equivalencias_escritas_en_las_descripciones()
            _st_escritos = st.session_state.get("sug_escritos")
            if _st_escritos is not None:
                if not _st_escritos:
                    st.info("No encontré pares nuevos. Si ya corriste esto antes, o tus listas "
                            "no escriben el código de fábrica en la descripción, es esperable.")
                else:
                    st.success(f"**{len(_st_escritos)} par(es) nuevos** que el proveedor dejó "
                                "escritos en la descripción.")
                    if len(_st_escritos) >= TOPE_CODIGOS_ESCRITOS:
                        st.warning(
                            f"⚠️ Se cortó en **{TOPE_CODIGOS_ESCRITOS:,} pares**, así que hay "
                            "más. Mandá estos a la cola, resolvelos, y volvé a correrlo."
                        )
                    _muestra_esc = []
                    for _a, _b in _st_escritos[:60]:
                        c.execute("""SELECT p.codigo_raw AS cod, p.descripcion AS des,
                                            m.nombre AS marca
                                     FROM productos p JOIN marcas m ON m.id = p.marca_id
                                     WHERE p.id IN (?, ?)""", (_a, _b))
                        _dos = filas_a_listas(c)
                        if len(_dos) == 2:
                            _muestra_esc.append({
                                "Marca": _dos[0]["marca"], "Código": _dos[0]["cod"],
                                "Descripción": (_dos[0]["des"] or "")[:60],
                                "Marca equivalente": _dos[1]["marca"],
                                "Código equivalente": _dos[1]["cod"],
                                "Su descripción": (_dos[1]["des"] or "")[:60],
                            })
                    if _muestra_esc:
                        st.caption(f"Muestra de {len(_muestra_esc)} de los {len(_st_escritos)}:")
                        st.dataframe(_muestra_esc, width="stretch", hide_index=True)
                    if st.button(f"📥 Mandar los {len(_st_escritos)} a la cola de pendientes",
                                 type="primary", key="mandar_sug_escritos"):
                        _n = guardar_equivalencias_pendientes(
                            list(_st_escritos), "descripcion-declarada",
                            f"escritos-{datetime.now().strftime('%d/%m %H:%M')}")
                        st.session_state.pop("sug_escritos", None)
                        avisar("ok", f"Listo: {_n} par(es) a la cola. Se aprueban en "
                                     "Estadísticas → 🔗 Equivalencias sugeridas.")
                        st.rerun()
            st.markdown("---")

            st.markdown("**🧠 Buscar equivalencias en TODO el catálogo de una**")
            explicar(
                "Lo mismo que comparar dos proveedores por descripción, pero recorriendo todas "
                "las marcas juntas en una sola pasada.",
                "Comparar de a dos proveedores funciona, pero con cinco cargados hay diez "
                "combinaciones para correr de a una, y con ocho son veintiocho. Nadie las corre "
                "todas, así que la mitad de los cruces posibles no se busca nunca.\n\n"
                "Si dos productos son o no el mismo repuesto lo decide exactamente el mismo "
                "criterio de siempre —posición, cilindrada, siglas, sustantivo principal y que "
                "coincida el auto—, así que no hay dos reglas distintas conviviendo.\n\n"
                "Lo único distinto es cómo elige qué pares mirar: comparar todo contra todo "
                "serían miles de millones de pares sobre un catálogo de casi cien mil productos. En "
                "vez de eso mira solo los que comparten alguna palabra POCO COMÚN, que quedan "
                "en unos ciento cincuenta mil y se resuelven en segundos.\n\n"
                "No carga nada solo: todo va a la cola de pendientes."
            )
            if st.button("🧠 Buscar en todo el catálogo"):
                with st.spinner("Comparando descripciones de todas las marcas..."):
                    st.session_state["sug_todas"] = sugerir_entre_todas_las_marcas()
            _st_todas = st.session_state.get("sug_todas")
            if _st_todas is not None:
                if not _st_todas:
                    st.info("No encontré pares nuevos. Si ya corriste esto antes, o tus listas "
                            "usan descripciones muy distintas entre sí, es esperable.")
                else:
                    st.success(f"**{len(_st_todas)} par(es) propuestos** entre marcas distintas.")
                    # Llegar al tope significa que hay más y no se están mostrando. Callarlo es
                    # lo que hacía creer que eso era todo lo que había: con el tope en 600 y la
                    # lista de Illinois cargada salían 787 pares y se veían 600.
                    if len(_st_todas) >= TOPE_SUGERENCIAS_TODAS:
                        st.warning(
                            f"⚠️ Se cortó en **{TOPE_SUGERENCIAS_TODAS:,} pares**, así que hay "
                            "más. Mandá estos a la cola, aprobalos o descartalos, y volvé a "
                            "correrlo: los que ya resolviste no vuelven a salir."
                        )
                    st.dataframe([{k: v for k, v in x.items() if not k.startswith("_")}
                                  for x in _st_todas],
                                 width="stretch", hide_index=True)
                    _pares_t = [(x["_a"], x["_b"]) for x in _st_todas]
                    if st.button(f"📥 Mandar los {len(_st_todas)} a la cola de pendientes",
                                 type="primary", key="mandar_sug_todas"):
                        _n = guardar_equivalencias_pendientes(
                            _pares_t, "descripcion-todas",
                            f"todas-{datetime.now().strftime('%d/%m %H:%M')}")
                        st.session_state.pop("sug_todas", None)
                        avisar("ok", f"Listo: {_n} par(es) a la cola. Se aprueban en "
                                     "Estadísticas → 🔗 Equivalencias sugeridas.")
                        st.rerun()
            st.markdown("---")

        if _grupo_mant == GRUPOS_MANTENIMIENTO[0]:
            # Leer las equivalencias que el propio proveedor publica en su catálogo web. Es la
            # misma fuente que ya se usa para las fotos y para los autos de cada ficha; lo que
            # faltaba era leer los números cruzados que la ficha lista.
            c.execute("""SELECT m.id, m.nombre, COUNT(p.id) AS productos
                         FROM marcas m JOIN productos p ON p.marca_id = m.id
                         WHERE m.url_ficha_template IS NOT NULL AND m.url_ficha_template <> ''
                         GROUP BY m.id ORDER BY productos DESC""")
            marcas_con_ficha = [dict(r) for r in c.fetchall()]

            st.markdown("**🌐 Leer equivalencias del catálogo digital del proveedor**")
            explicar(
                "Entra a la ficha de cada código en la web del proveedor y trae los códigos "
                "cruzados que estén publicados ahí.",
                "Muchas fichas listan las referencias cruzadas —«equivale a», «OEM», «cross "
                "reference»—, que es justo lo que uno cargaría a mano código por código.\n\n"
                "Hace falta que la marca tenga cargada la **dirección de su catálogo** en "
                "Administrar → Marcas, con `{codigo}` donde va el número.\n\n"
                "Dos límites que conviene saber de entrada: si la ficha arma su contenido con "
                "JavaScript, lo que llega es la página vacía y no se lee nada — no todos los "
                "catálogos se dejan; y solo se proponen códigos que YA tengas cargados, porque "
                "una equivalencia contra algo que no tenés no se puede ni vender ni buscar.\n\n"
                "Nada se carga solo: todo va a la misma cola de revisión. Una ficha también "
                "lista accesorios y kits, y eso no es una equivalencia."
            )
            if not marcas_con_ficha:
                # Se nombran las marcas que SÍ tenés cargadas. «Ninguna marca tiene cargada la
                # dirección» se lee como «la app no ve mi lista» cuando en realidad la ve: lo
                # que falta es la dirección web, que es otra cosa que la lista de productos.
                try:
                    c.execute("""SELECT m.nombre, COUNT(p.id) AS n
                                 FROM marcas m JOIN productos p ON p.marca_id = m.id
                                 WHERE m.tipo <> 'OEM'
                                 GROUP BY m.id ORDER BY n DESC LIMIT 8""")
                    _sin_dir = [f"{r['nombre']} ({r['n']:,} productos)" for r in c.fetchall()]
                except sqlite3.OperationalError as _err:
                    anotar_error("catálogo digital", _err)
                    _sin_dir = []
                st.info(
                    "Ninguna marca tiene cargada la **dirección web** de su catálogo. Es otra "
                    "cosa que la lista de productos: la lista ya está cargada, lo que falta es "
                    "el link a la ficha de cada código.\n\n"
                    + ("Tus proveedores cargados: " + ", ".join(_sin_dir) + ".\n\n"
                       if _sin_dir else "")
                    + "Se carga en Administrar → 🏷️ Marcas, en «patrón de link»: ahí la tabla "
                      "tiene una columna **Catálogo web** que dice cuáles ya lo tienen."
                )
            else:
                # Qué catálogos tienen usuario y contraseña cargados. Sin esto, configurarlos es
                # invisible: se carga el secreto en el panel de Streamlit y no hay forma de
                # saber desde la app si quedó bien escrito el nombre de la marca —que tiene que
                # coincidir exactamente— hasta que una tanda entera falla.
                _con_clave = [m["nombre"] for m in marcas_con_ficha
                              if credenciales_de_catalogo(m["nombre"])]
                _sin_clave = [m["nombre"] for m in marcas_con_ficha
                              if not credenciales_de_catalogo(m["nombre"])]
                if _con_clave:
                    st.caption("🔐 Entran con usuario y contraseña: "
                               + ", ".join(f"**{x}**" for x in _con_clave)
                               + (f" · sin contraseña: {', '.join(_sin_clave)}"
                                  if _sin_clave else ""))
                    if st.button("🔄 Volver a entrar al catálogo", key="relogin_catalogo",
                                  help="Si las fichas empezaron a fallar todas juntas, lo más "
                                       "probable es que haya vencido la sesión. Esto la tira y "
                                       "la próxima consulta vuelve a ingresar."):
                        olvidar_sesion_de_catalogo()
                        avisar("ok", "Listo: la próxima consulta vuelve a ingresar al catálogo.")
                with st.expander("🔐 ¿El catálogo pide usuario y contraseña?"):
                    st.markdown(
                        "Se puede, y **la contraseña no se guarda en la app**: va en los "
                        "secretos de Streamlit. Es a propósito — todo lo que se guarda en la "
                        "app sale en el backup automático al repositorio y en el botón de bajar "
                        "la base, así que una contraseña guardada ahí terminaría copiada en el "
                        "repositorio.\n\n"
                        "En el panel de Streamlit Cloud → **Settings → Secrets**, una sección "
                        "por marca, con el nombre **igual** a como está cargada acá:\n\n"
                        "```toml\n"
                        "[catalogo.MOTORARG]\n"
                        'url_login = "https://ejemplo.com/ingresar"\n'
                        'usuario = "micuenta@ejemplo.com"\n'
                        'clave = "loquesea"\n'
                        'campo_usuario = "email"     # cómo llama el sitio al campo\n'
                        'campo_clave = "password"\n'
                        "```\n\n"
                        "Los dos nombres de campo salen de mirar el formulario de ingreso del "
                        "proveedor: cada sitio los llama distinto y no se pueden adivinar.\n\n"
                        "**Avisale al proveedor.** Sos cliente y tenés acceso, pero muchos "
                        "catálogos prohíben en sus condiciones consultarlos de forma "
                        "automatizada, y cientos de consultas seguidas pueden hacer que te "
                        "corten el usuario. Pedir permiso —o directamente el archivo— suele ser "
                        "más rápido que todo esto."
                    )

                # Lo mismo que con las fotos: son miles de fichas y sentarse a esperar no es
                # opción, así que avanza solo, sin tope por día. Sale a internet, por eso
                # se elige a mano. Al lado va cuánto falta, que es lo que dice si sirve
                # prenderlo: sin el número, «automático» no se sabe si termina en una semana o
                # en dos años.
                st.checkbox(
                    "🤖 Leer las fichas solas, en segundo plano",
                    value=obtener_config("equiv_ficha_automaticas", "0") == "1",
                    key="equiv_ficha_auto_check",
                    on_change=lambda: prender_tarea_de_fondo(
                        "equiv", "equiv_ficha_automaticas",
                        st.session_state["equiv_ficha_auto_check"]),
                    help="Mientras la app esté abierta, va leyendo fichas del catálogo del "
                         "proveedor en un hilo aparte y manda a revisión las equivalencias que "
                         "encuentre escritas ahí. Avanza siempre sobre códigos nuevos."
                )
                if obtener_config("equiv_ficha_automaticas", "0") == "1":
                    mostrar_avance_de_tanda("equiv", "ficha(s)")

                opciones_mf = {f"{m['nombre']} ({m['productos']} códigos)": m["id"]
                               for m in marcas_con_ficha}
                elegida_mf = st.selectbox("Marca:", list(opciones_mf.keys()),
                                           key="marca_equiv_catalogo")
                # El valor por defecto va por session_state y no por value=: con key= puesto,
                # Streamlit ignora value= a partir del segundo dibujo y el slider parece que
                # "no obedece". Es la misma forma que usa el resto de la app.
                st.session_state.setdefault("tanda_equiv_catalogo", 25)
                cuantos_mf = st.select_slider(
                    "Cuántas fichas consultar en esta tanda:", options=[10, 25, 50, 100, 200],
                    key="tanda_equiv_catalogo",
                    help="Cada ficha es una consulta al sitio del proveedor. De a poco primero, "
                         "para ver si ese catálogo se deja leer antes de pedirle 200 páginas.")
                # Lo ya leído no se vuelve a pedir, salvo que lo pidas: antes a mano se releían
                # siempre las primeras fichas (las de stock), y cada tanda bajaba lo mismo.
                _releer_mf = st.checkbox(
                    "Volver a leer también las fichas ya leídas", key="releer_equiv_catalogo",
                    help="Solo si el proveedor actualizó su catálogo. Si no, cada tanda sigue "
                         "donde quedó la anterior.")
                if st.button("🌐 Leer las fichas y proponer equivalencias"):
                    barra_mf = st.progress(0.0)
                    with st.spinner("Consultando el catálogo del proveedor..."):
                        _props, _falla, _consult = equivalencias_desde_catalogo(
                            opciones_mf[elegida_mf], limite=int(cuantos_mf),
                            solo_no_leidos=not _releer_mf,
                            progreso=lambda hechos, total: barra_mf.progress(
                                min(hechos / max(total, 1), 1.0)))
                    barra_mf.empty()
                    st.session_state["equiv_catalogo"] = {
                        "propuestas": _props, "fallidas": _falla,
                        "consultados": _consult, "marca": elegida_mf.split(" (")[0]}
                _ec = st.session_state.get("equiv_catalogo")
                if _ec is not None and not _ec["consultados"]:
                    st.success("✅ Ya se leyeron todas las fichas de esta marca: no hay nada "
                               "nuevo que pedir. Tildá «Volver a leer» si el proveedor "
                               "actualizó su catálogo.")
                elif _ec is not None:
                    st.caption(f"Se consultaron {_ec['consultados']} ficha(s); "
                               f"{len(_ec['fallidas'])} no se pudieron leer.")
                    if not _ec["propuestas"]:
                        st.info(
                            "No salió ninguna equivalencia. O ese catálogo no publica las "
                            "referencias cruzadas, o arma la página con JavaScript y llega "
                            "vacía, o los códigos que lista todavía no están en tus listas."
                        )
                        if _ec["fallidas"]:
                            st.dataframe(
                                [{"Código": cod, "Qué pasó": err}
                                 for cod, err in _ec["fallidas"][:30]],
                                width="stretch", hide_index=True)
                    else:
                        st.success(f"Se encontraron **{len(_ec['propuestas'])} equivalencia(s)** "
                                   "publicadas en las fichas.")
                        st.dataframe(
                            [{k: v for k, v in x.items() if not k.startswith("_")}
                             for x in _ec["propuestas"][:100]],
                            width="stretch", hide_index=True)
                        if st.button(f"📥 Mandar las {len(_ec['propuestas'])} a revisión",
                                      type="primary", key="btn_equiv_catalogo_guardar"):
                            _n = guardar_equivalencias_de_catalogo(_ec["propuestas"], _ec["marca"])
                            st.session_state.pop("equiv_catalogo", None)
                            invalidar_salud()
                            avisar("success", f"{_n} equivalencia(s) quedaron para revisar.")
                            st.rerun()
            st.markdown("---")

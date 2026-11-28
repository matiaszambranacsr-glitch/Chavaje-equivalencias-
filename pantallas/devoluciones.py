"""Pantalla: se ejecuta en cada toque desde app.py, en el mismo espacio de nombres que app.py
(ver pantallas/__init__.py). Por eso usa sin importarlos los nombres de app.py y de logica/."""

# ============================================================
# DEVOLUCIONES: lo que vuelve al depósito, lo que devuelve un cliente y las etiquetas
# ============================================================
# Cómo funciona, en logica/deposito.py («LO QUE QUEDA AFUERA» y «EL CÓDIGO DE BARRAS NUESTRO»)
# y en logica/ventas.py («DEVOLVER ALGO DE UNA VENTA»). Aparte de 🧾 Ventas y 📦 Depósito: lo
# pidió el dueño, porque con muchos pedidos, adentro de ellas, la pantalla se hacía eterna.
if pagina == PAGINAS[10]:
    sub_dvl = elegir_solapa(PAGINAS[10])

    def _hace(horas):
        return (("🔴 " if horas >= HORAS_PARA_AVISAR_LO_QUE_QUEDO_AFUERA else "")
                + "hace " + cuanto_hace(horas))

    # ---------- LO QUE VUELVE AL DEPÓSITO: escaneando la etiqueta nuestra ----------
    if sub_dvl == SUB_DEVOLUCIONES[0]:
        ayuda(
            "Lo que el depósito entregó para Mostrador queda a nombre de quien lo pidió hasta "
            "que lo vende. Si no se vende, vuelve acá: **escaneá la etiqueta nuestra** (la que "
            f"empieza con {PREFIJO_DEL_CODIGO_NUESTRO}) **de cada pieza**, una por una; el código "
            "original de la caja no sirve, porque está en cualquier caja igual. La app se da "
            "cuenta sola de quién es; después pone su contraseña quien lo tiene (o un "
            "administrador) y vuelve al stock. Lo recibe el depósito con su usuario: nadie se "
            "devuelve a sí mismo. **Lo de un taller no vuelve**: queda en su cuenta."
        )
        _quienes = quien_tiene_que_devolver()
        if not _quienes:
            st.success("Nadie tiene nada del depósito afuera: no hay nada para recibir.")
            st.session_state["dvl_escaneos"] = []
        else:
            # Una fila por persona, no por pieza: con muchos pedidos, el detalle va aparte.
            st.dataframe([{"Quién": g["quien"], "Cosas": g["cosas"], "Unidades": g["unidades"],
                           "La más vieja": _hace(g["horas"])} for g in _quienes],
                         hide_index=True, width="stretch",
                         height=min(36 * (len(_quienes) + 1) + 3, 260))
            _escaneos = st.session_state.setdefault("dvl_escaneos", [])
            # El lector escribe el código y un Enter: eso manda el formulario, que queda vacío
            # para la pieza siguiente.
            with st.form("form_dvl_escanear", clear_on_submit=True):
                _e1, _e2 = cols([3, 1], apilar_en_celular=False)
                _leido = _e1.text_input("Escaneá la etiqueta nuestra de cada pieza:",
                                        key="dvl_escaneo",
                                        placeholder=f"{PREFIJO_DEL_CODIGO_NUESTRO}1400-5")
                _sumar = _e2.form_submit_button("➕ Sumar", width="stretch")
            if _sumar and _leido.strip():
                _pid_e, _por_que = que_es_lo_escaneado(_leido, _escaneos)
                if _pid_e:
                    _escaneos.append(codigo_nuestro(_pid_e))
                else:
                    st.warning(_por_que)
            if _escaneos:
                _nombres = {codigo_nuestro(r["producto_id"]): f"{r['marca']} {r['codigo_raw']}"
                            for r in lo_que_tiene()}
                _cuantas = {}
                for _t in _escaneos:
                    _cuantas[_t] = _cuantas.get(_t, 0) + 1
                st.markdown(f"**Escaneado: {len(_escaneos)} pieza(s)**")
                st.dataframe([{"Qué": _nombres.get(_t, _t), "Etiqueta": _t, "Piezas": _n}
                              for _t, _n in _cuantas.items()], hide_index=True,
                             width="stretch", height=min(36 * (len(_cuantas) + 1) + 3, 260))
                _s1, _s2 = cols([1, 1], apilar_en_celular=False)
                if _s1.button("↩️ Sacar la última", key="dvl_sacar_ultima", width="stretch"):
                    _escaneos.pop()
                    st.rerun()
                if _s2.button("🗑️ Empezar de nuevo", key="dvl_empezar_de_nuevo",
                              width="stretch"):
                    st.session_state["dvl_escaneos"] = []
                    st.rerun()
                _candidatos = quienes_tienen_lo_escaneado(_escaneos)
                _persona = None
                if len(_candidatos) == 1:
                    _persona = _candidatos[0]
                    st.markdown(f"Es de **{texto_para_html(_persona)}**.")
                elif _candidatos:
                    _persona = st.selectbox("Lo tienen varios: ¿de quién es?", _candidatos,
                                            key="dvl_persona")
                else:
                    st.warning("Nadie tiene todo eso junto: recibí lo de cada persona por "
                               "separado (sacá lo que no es de la misma).")
                if _persona:
                    with st.form("form_dvl_devolver"):
                        _clave_dvl = st.text_input(
                            f"Contraseña de {_persona} (o de un administrador):",
                            type="password",
                            help="La pone quien lo tiene: así nadie descarga lo que tiene otro. "
                                 "La de un administrador también sirve, y queda anotado.")
                        _vuelve = st.form_submit_button(
                            f"↩️ Vuelven al stock ({len(_escaneos)})", type="primary")
                    if _vuelve:
                        _ok_dvl, _texto_dvl = devolver_lo_escaneado(_escaneos, _persona,
                                                                    _clave_dvl)
                        if _ok_dvl:
                            st.session_state["dvl_escaneos"] = []
                            avisar("success", _texto_dvl)
                            st.rerun()
                        st.warning(_texto_dvl)
            # El detalle de una persona, aparte: con muchos pedidos, la lista entera de todos
            # era la pantalla que «explota».
            with st.expander("🔎 Qué tiene cada uno", key="exp_tiene_cada_uno"):
                _de_quien = st.selectbox("Persona:", [g["quien"] for g in _quienes],
                                         key="dvl_detalle_de")
                _suyo = lo_que_tiene(persona=_de_quien)
                st.dataframe([{"Qué": f"{r['queda']}× {r['marca']} {r['codigo_raw']}",
                               "Descripción": (r["descripcion"] or "")[:40],
                               "Etiqueta": codigo_nuestro(r["producto_id"]),
                               "Desde": _hace(r["horas"])} for r in _suyo],
                             hide_index=True, width="stretch",
                             height=min(36 * (len(_suyo) + 1) + 3, 320))

    # ---------- LO QUE DEVUELVE UN CLIENTE: ver «DEVOLVER ALGO DE UNA VENTA» ----------
    if sub_dvl == SUB_DEVOLUCIONES[1]:
        _q_dev = st.text_input("Número de venta, cliente, patente o teléfono:",
                               key="venta_buscar_dev", placeholder="Ej: 12, Juan, AB123CD")
        # LAS DE HOY, a un toque: lo que vuelve suele ser de una venta del mismo día («me
        # llevé el que no era»), y había que preguntar el número o el nombre para buscarla.
        if not _q_dev.strip():
            _hoy_dev = [v for v in ventas_del_dia() if not v["anulada"]][:CUANTAS_VENTAS_DE_HOY]
            if _hoy_dev:
                st.caption("O una de las últimas de hoy:")
                for _vh in _hoy_dev:
                    st.button(f"#{_vh['id']} · {_vh['hora']} · "
                              f"{_vh['cliente'] or _vh['cuenta'] or _vh['patente'] or 'Mostrador'}"
                              f" · ${miles(_vh['total'] or 0, 0)}",
                              key=f"dev_de_hoy_{_vh['id']}", width="stretch",
                              on_click=lambda _i=_vh["id"]: st.session_state.update(
                                  venta_buscar_dev=f"#{_i}"))
        if _q_dev.strip():
            _encontradas = buscar_ventas(_q_dev)
            if not _encontradas:
                st.caption("No encontré ninguna venta de los últimos 6 meses con eso.")
            else:
                _por_id = {v["id"]: v for v in _encontradas}
                _vsel = st.selectbox(
                    "Venta:", list(_por_id), key="venta_dev_sel",
                    format_func=lambda i: (  # rótulo fijo: fecha, cliente y total de la venta
                                           f"#{i} — {fecha_legible(_por_id[i]['fecha'][:16])[:16]}"
                                           f" — {_por_id[i]['cliente'] or _por_id[i]['patente'] or 'sin nombre'}"
                                           f" — ${miles(_por_id[i]['total'] or 0, 0)}"))
                _v = _por_id[_vsel]
                st.dataframe([{"Qué": f"{it['marca']} {it['codigo']}",
                               "Descripción": (it["descripcion"] or "")[:40],
                               "Cantidad": it["cantidad"], "Devuelto": it["devuelto"] or "",
                               "Precio": f"${miles(it['precio'], 0)}"} for it in _v["items"]],
                             width="stretch", hide_index=True)
                _devolvibles = {it["id"]: it for it in _v["items"]
                                if it["cantidad"] - it["devuelto"] > 0}
                if not _devolvibles:
                    st.caption("De esta venta ya se devolvió todo.")
                else:
                    with st.form("form_devolver"):
                        _d1, _d2 = cols([3, 1])
                        # Lo que ya volvió está en la tabla de arriba, no en el rótulo: «(quedan
                        # 2)» cambiaba con cada devolución, y en el navegador un rótulo que cambia
                        # vuelve el selector a la primera opción en el toque siguiente (ver
                        # cuenta_en_la_barra()).
                        _it_dev = _d1.selectbox(
                            "Qué vuelve:", list(_devolvibles),
                            format_func=lambda i: (  # rótulo fijo: lo que se llevó
                                                   f"{_devolvibles[i]['marca']} "
                                                   f"{_devolvibles[i]['codigo']} (se llevó "
                                                   f"{_devolvibles[i]['cantidad']})"))
                        _cant_dev = _d2.number_input("Cuántos:", min_value=1, value=1, step=1)
                        _mot_dev = st.selectbox("¿Por qué volvió?", list(MOTIVOS_DE_DEVOLUCION),
                                                format_func=MOTIVOS_DE_DEVOLUCION.get)
                        _det_dev = st.text_input("Qué pasó (opcional):",
                                                 placeholder="Ej.: la rosca era más chica")
                        # CON FACTURA, LA NOTA DE CRÉDITO POR LO DEVUELTO: si no, ARCA sigue
                        # teniendo vendido lo que volvió (ver nota_de_credito()). Tildada de
                        # entrada: la factura ya se hizo; destildarla es decidirlo a propósito.
                        _fact_dev = factura_vigente_de(_v["id"]) if configuracion_de_arca() else None
                        _con_nc = False
                        if _fact_dev and _fact_dev["estado"] == "autorizada":
                            _con_nc = st.checkbox(
                                "🧾 Con nota de crédito por lo devuelto", value=True,
                                help="La venta tiene la " + nombre_del_comprobante(
                                    _fact_dev["tipo"], _fact_dev["punto_de_venta"],
                                    _fact_dev["numero"]) + ": la nota anula esa parte en ARCA.")
                        # EL VALE A FAVOR (ver esa sección en logica/ventas.py): la plata queda en
                        # el cajón y el cliente se lleva otra cosa después.
                        _en_vale = (st.checkbox(
                            "🎟️ En un vale a favor (no le devolvés la plata)", key="dev_en_vale",
                            help="Queda un vale con número por lo devuelto: en otra compra se "
                                 "descuenta escribiendo ese número (o su teléfono). Si lleva "
                                 "menos, lo que sobra queda en otro vale.")
                                    if _v.get("forma_de_pago") != A_CUENTA else False)
                        st.caption("Vuelve al stock salvo que no se pueda volver a vender "
                                   "(fallada, dañada o modificada), y la plata sale de la caja "
                                   "de hoy (o queda en el vale). Si se vendió en lugar de otro "
                                   "código y no le iba, la app lo aprende.")
                        _devolver = st.form_submit_button("↩️ Devolver", type="primary")
                    if _devolver:
                        _ok_dev, _texto_dev = devolver_de_una_venta(_it_dev, _cant_dev, _mot_dev,
                                                                   _det_dev, en_vale=_en_vale)
                        if _ok_dev:
                            avisar("success", f"↩️ {_texto_dev}")
                            if _con_nc:
                                _it_nc = _devolvibles[_it_dev]
                                _ok_nc, _texto_nc = nota_de_credito(
                                    _fact_dev["id"], _it_nc["precio"] * _cant_dev,
                                    renglones=[[_cant_dev, f"{_it_nc['marca']} {_it_nc['codigo']}"
                                                f" - {_it_nc['descripcion'] or ''}",
                                                _it_nc["precio"]]])
                                avisar("success" if _ok_nc else "warning", _texto_nc)
                            st.rerun()
                        st.warning(_texto_dev)

    # ---------- LAS ETIQUETAS: ver «EL CÓDIGO DE BARRAS NUESTRO» ----------
    if sub_dvl == SUB_DEVOLUCIONES[2]:
        ayuda("Para pegar en cada pieza que sale del depósito para Mostrador: sin la etiqueta "
              "nuestra no puede volver al stock. Las de lo que el depósito tiene para buscar "
              "salen también en 📦 Depósito.")
        st.markdown("**De un producto**")
        _q_et = st.text_input("Código del producto, o escaneá la caja:",
                              key="dvl_etiqueta_buscar", placeholder="Ej: W712, 7891234567895")
        if _q_et.strip():
            _prods = {p["id"]: p for p in productos_para_etiquetar(_q_et)}
            if not _prods:
                st.caption("No encontré ningún producto con eso.")
            else:
                _et1, _et2 = cols([3, 1])
                _pid_et = _et1.selectbox(
                    "Producto:", list(_prods), key="dvl_etiqueta_producto",
                    format_func=lambda i: (  # rótulo fijo: imprimir etiquetas no mueve el stock
                                           f"{_prods[i]['marca']} {_prods[i]['codigo_raw']} — "
                                           f"{(_prods[i]['descripcion'] or '')[:40]}"
                                           + (f" · stock {_prods[i]['stock']}"
                                              if _prods[i]["stock"] is not None else "")))
                _n_et = _et2.number_input("Cuántas:", min_value=1,
                                          max_value=CANTIDAD_MAXIMA_POR_PEDIDO * 4, value=1,
                                          step=1, key="dvl_etiqueta_cuantas")
                st.download_button(
                    f"🏷️ Etiquetas de {_prods[_pid_et]['codigo_raw']} ({int(_n_et)})",
                    data=etiquetas_para_descargar([(_pid_et, _n_et)]),
                    file_name=f"etiquetas_{codigo_nuestro(_pid_et)}.pdf",
                    mime="application/pdf", key="dvl_etiqueta_pdf")
                st.caption(f"Su código: **{codigo_nuestro(_pid_et)}**")
        st.markdown("**De lo que está afuera**")
        _afuera = lo_que_tiene()
        if not _afuera:
            st.caption("Nada afuera.")
        else:
            st.download_button(
                f"🏷️ Una por cada pieza que está afuera ({sum(r['queda'] for r in _afuera)})",
                data=etiquetas_para_descargar([(r["producto_id"], r["queda"]) for r in _afuera]),
                file_name="etiquetas_lo_que_esta_afuera.pdf", mime="application/pdf",
                key="dvl_etiquetas_afuera",
                help="Por si alguna se despegó o se entregó sin etiqueta.")
        # LOS CARTELES DE PRECIO: ver esa sección en logica/deposito.py.
        st.markdown("**💲 Carteles de precio**")
        _modo_k = st.radio("Carteles de:", ["Los que elijo",
                                            "Los que cambiaron de precio con la última lista"],
                           horizontal=True, key="carteles_modo",
                           help="Para la góndola y el mostrador: marca y código, el precio "
                                "grande, la fecha y el código de barras nuestro (se cobra "
                                "escaneando el cartel). Tres por siete en una hoja A4.")
        _ids_k, _archivo_k, _elijo_k = [], "carteles_de_precio.pdf", _modo_k == "Los que elijo"
        if _elijo_k:
            _q_k = st.text_input("Código del producto, o escaneá la caja:", key="carteles_buscar",
                                 placeholder="Ej: W712, 7891234567895")
            if _q_k.strip():
                _prods_k = {p["id"]: p for p in productos_para_etiquetar(_q_k)}
                if not _prods_k:
                    st.caption("No encontré ningún producto con eso.")
                else:
                    _k1, _k2 = cols([3, 1], abajo=True)
                    _k1.selectbox("Producto:", list(_prods_k), key="carteles_producto",
                                  format_func=lambda i: (  # rótulo fijo: el producto no cambia
                                      f"{_prods_k[i]['marca']} {_prods_k[i]['codigo_raw']} — "
                                      f"{(_prods_k[i]['descripcion'] or '')[:40]}"))
                    _k2.button("➕ Sumar", key="carteles_sumar", width="stretch",
                               on_click=sumar_al_cartel, args=("carteles_producto",))
            _ids_k = list(st.session_state.get("carteles_elegidos") or [])
        else:
            _marcas_k = marcas_con_precios_nuevos()
            if not _marcas_k:
                st.caption("Todavía ninguna lista cambió precios: sale cuando se vuelve a cargar "
                           "la lista de una marca.")
            else:
                _por_id_k = {m["marca_id"]: m for m in _marcas_k}
                _k1, _k2 = cols([3, 2], abajo=True)
                _mid_k = _k1.selectbox(
                    "Marca:", list(_por_id_k), key="carteles_marca",
                    format_func=lambda i: (  # rótulo fijo: cambia solo al cargar otra lista
                        f"{_por_id_k[i]['marca']} — lista del "
                        f"{_por_id_k[i]['fecha'][8:10]}/{_por_id_k[i]['fecha'][5:7]}"))
                _con_stock_k = _k2.toggle("Solo lo que hay en stock", value=True,
                                          key="carteles_con_stock")
                _m_k = _por_id_k[_mid_k]
                st.caption(f"Con la última lista cambiaron {miles(_m_k['cambiaron'])} "
                           f"precio(s); {miles(_m_k['con_stock'])} de lo que hay en stock.")
                _ids_k = [f["id"] for f in precios_nuevos_de_la_marca(_mid_k, _con_stock_k)]
                _archivo_k = f"carteles_{sanitizar(_m_k['marca']) or _mid_k}.pdf"
        if _ids_k:
            _carteles_k, _fuera_k, _sin_precio_k = carteles_de_precio(_ids_k)
            if _fuera_k:
                st.warning(f"Los de **{', '.join(_fuera_k)}** no salen: su lista está en otra "
                           "escala que las demás, y ese precio no es el de venta.")
            if _elijo_k:
                st.caption(" · ".join(k["titulo"] for k in _carteles_k)
                           + (f" · {_sin_precio_k} sin precio (no sale)" if _sin_precio_k
                              else ""))
            elif _sin_precio_k:
                st.caption(f"{_sin_precio_k} sin precio no salen.")
            _d1, _d2 = cols([3, 1], abajo=True)
            _d1.download_button(f"💲 Carteles de precio ({len(_carteles_k)})",
                                data=carteles_para_descargar(_carteles_k),
                                file_name=_archivo_k, mime="application/pdf",
                                key="carteles_pdf", disabled=not _carteles_k, width="stretch")
            if _elijo_k:
                _d2.button("🗑️ Vaciar", key="carteles_vaciar", width="stretch",
                           on_click=vaciar_los_carteles)

    # ---------- LAS GARANTÍAS: ver «LAS GARANTÍAS» en logica/ventas.py ----------
    if sub_dvl == SUB_DEVOLUCIONES[3]:
        ayuda("Lo que un cliente devolvió fallado o dañado no vuelve al stock: se le reclama al "
              "proveedor. Acá queda por marca, con el reclamo listo para mandarle por WhatsApp. "
              "Después de mandarlo, «📤 Ya se lo reclamé»; cuando lo cambian o lo acreditan, "
              "«✅ Lo cambiaron o lo acreditaron».")
        _gar = garantias(con_las_cerradas=st.toggle("Ver también los cerrados",
                                                    key="garantias_cerradas"))
        if not _gar:
            st.success("✅ No hay nada fallado para reclamar.")
        else:
            _por_marca_gar = {}
            for _g in _gar:
                _por_marca_gar.setdefault(_g["marca"] or "Sin marca", []).append(_g)
            _sin_reclamar = [g for g in _gar if not g["reclamo"]]
            st.caption(f"{miles(len(_sin_reclamar))} devolución(es) por reclamar, por "
                       f"\\${miles(sum(g['importe'] for g in _sin_reclamar), 0)} (lo que se le "
                       "devolvió al cliente). Lo más viejo primero: el proveedor no acepta "
                       "cualquier fecha.")
            for _marca_g, _filas_g in _por_marca_gar.items():
                # Las claves sin espacios ni signos (el navegador busca la caja por su clave,
                # ver «walink__» en AYUDAS_DEL_NAVEGADOR) y con la marca: cada una, lo suyo.
                _id_g = (re.sub(r"[^0-9A-Za-z_]", "_", _marca_g)
                         + "_" + hashlib.md5(_marca_g.encode()).hexdigest()[:6])
                _pend_g = [f for f in _filas_g if not f["reclamo"]]
                _recl_g = [f for f in _filas_g if f["reclamo"] == "reclamado"]
                with st.container(border=True, key=f"garantia_{_id_g}"):
                    st.markdown(f"**{texto_para_markdown(_marca_g)}**"
                                + (f" · {miles(len(_pend_g))} por reclamar" if _pend_g else "")
                                + (f" · {miles(len(_recl_g))} reclamada(s), esperando respuesta"
                                   if _recl_g else ""))
                    st.dataframe([{
                        "Devuelta": f["fecha"], "Venta": f"#{f['venta_id']}",
                        "Código": f["codigo"], "Descripción": (f["descripcion"] or "")[:40],
                        "Cant.": f["cantidad"],
                        "Qué tenía": MOTIVOS_DE_DEVOLUCION.get(f["motivo"], f["motivo"]),
                        "Detalle": f["detalle"] or "",
                        "Reclamo": ESTADOS_DEL_RECLAMO.get(f["reclamo"], f["reclamo"])
                                   + (f" ({fecha_legible(f['reclamo_en'])})"
                                      if f["reclamo"] and f["reclamo_en"] else "")}
                        for f in _filas_g], width="stretch", hide_index=True)
                    if _pend_g:
                        # El reclamo, como el pedido al proveedor (ver «📌 Para pedir»): se
                        # puede corregir, va lo corregido, y la caja se renueva si cambia lo que
                        # hay que reclamar (la huella en la clave).
                        _texto_g = mensaje_de_garantia(_marca_g, _pend_g)
                        _clave_g = (f"garantia_msg_{_id_g}_"
                                    + hashlib.md5(_texto_g.encode()).hexdigest()[:8])
                        _msg_g = st.text_area("Reclamo:", value=_texto_g, height=130,
                                              key=_clave_g) or _texto_g
                        _clave_tel_g = f"wa_prov_gar_{_id_g}"
                        st.session_state.setdefault(_clave_tel_g, whatsapp_del_proveedor(_marca_g))
                        _tel_g = st.text_input(
                            f"WhatsApp del proveedor de {_marca_g}:", key=_clave_tel_g,
                            placeholder="Ej.: 11 4567-8901 (queda guardado para la próxima)",
                            on_change=lambda _m=_marca_g, _k=_clave_tel_g:
                                guardar_whatsapp_del_proveedor(_m, st.session_state.get(_k)))
                        _g1, _g2 = st.columns(2)
                        _g1.link_button(f"📲 Reclamárselo por WhatsApp"
                                        if numero_para_whatsapp(_tel_g)
                                        else "📲 Abrir WhatsApp (elegís a quién)",
                                        link_de_whatsapp(_tel_g, _msg_g), width="stretch",
                                        key=f"walink__{_clave_g}")
                        _g2.button("📤 Ya se lo reclamé", key=f"garantia_reclamada_{_id_g}",
                                   width="stretch", on_click=marcar_reclamo,
                                   args=([f["id"] for f in _pend_g], "reclamado"))
                    if _recl_g:
                        _r1, _r2 = st.columns(2)
                        _r1.button("✅ Lo cambiaron o lo acreditaron",
                                   key=f"garantia_resuelta_{_id_g}", width="stretch",
                                   on_click=marcar_reclamo,
                                   args=([f["id"] for f in _recl_g], "resuelto"))
                        _r2.button("🚫 No lo reconocieron", key=f"garantia_rechazada_{_id_g}",
                                   width="stretch", on_click=marcar_reclamo,
                                   args=([f["id"] for f in _recl_g], "rechazado"))

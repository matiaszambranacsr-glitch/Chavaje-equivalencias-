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
            with st.expander("🔎 Qué tiene cada uno"):
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
        if _q_dev.strip():
            _encontradas = buscar_ventas(_q_dev)
            if not _encontradas:
                st.caption("No encontré ninguna venta de los últimos 6 meses con eso.")
            else:
                _por_id = {v["id"]: v for v in _encontradas}
                _vsel = st.selectbox(
                    "Venta:", list(_por_id), key="venta_dev_sel",
                    format_func=lambda i: (f"#{i} — {_por_id[i]['fecha'][8:10]}/"
                                           f"{_por_id[i]['fecha'][5:7]} {_por_id[i]['fecha'][11:16]}"
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
                        _it_dev = _d1.selectbox(
                            "Qué vuelve:", list(_devolvibles),
                            format_func=lambda i: (f"{_devolvibles[i]['marca']} "
                                                   f"{_devolvibles[i]['codigo']} (quedan "
                                                   f"{_devolvibles[i]['cantidad'] - _devolvibles[i]['devuelto']})"))
                        _cant_dev = _d2.number_input("Cuántos:", min_value=1, value=1, step=1)
                        _mot_dev = st.selectbox("¿Por qué volvió?", list(MOTIVOS_DE_DEVOLUCION),
                                                format_func=MOTIVOS_DE_DEVOLUCION.get)
                        _det_dev = st.text_input("Qué pasó (opcional):",
                                                 placeholder="Ej.: la rosca era más chica")
                        st.caption("Vuelve al stock salvo que no se pueda volver a vender "
                                   "(fallada, dañada o modificada), y la plata sale de la caja "
                                   "de hoy. Si se vendió en lugar de otro código y no le iba, la "
                                   "app lo aprende.")
                        _devolver = st.form_submit_button("↩️ Devolver", type="primary")
                    if _devolver:
                        _ok_dev, _texto_dev = devolver_de_una_venta(_it_dev, _cant_dev, _mot_dev,
                                                                   _det_dev)
                        if _ok_dev:
                            avisar("success", f"↩️ {_texto_dev}")
                            st.rerun()
                        st.warning(_texto_dev)

    # ---------- LAS ETIQUETAS: ver «EL CÓDIGO DE BARRAS NUESTRO» ----------
    if sub_dvl == SUB_DEVOLUCIONES[2]:
        st.caption("Para pegar en cada pieza que sale del depósito para Mostrador: sin la "
                   "etiqueta nuestra no puede volver al stock. Las de lo que el depósito tiene "
                   "para buscar salen también en 📦 Depósito.")
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
                    format_func=lambda i: (f"{_prods[i]['marca']} {_prods[i]['codigo_raw']} — "
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

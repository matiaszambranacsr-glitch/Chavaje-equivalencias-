"""Los repuestos que le van a un auto, y el lector de VIN con su panel.

Salió de logica/descripciones.py, que con 5.400 renglones juntaba cinco temas.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================================================
# REPUESTOS POR AUTO Y LECTOR DE VIN
# ============================================================================================
def buscar_aplicaciones(marca_auto, modelo="", anio=None, limite=200):
    """Los códigos que un catálogo de aplicaciones dice que le van a este auto.

    A diferencia de buscar por la descripción del proveedor, acá el dato lo puso el fabricante
    del repuesto: si NGK dice que a un Fiat Argo 1.3 le va la U5443, le va."""
    condiciones = ["UPPER(marca_auto) LIKE ?"]
    params = [f"%{(marca_auto or '').strip().upper()}%"]
    if modelo:
        condiciones.append("UPPER(modelo_auto) LIKE ?")
        params.append(f"%{modelo.strip().upper()}%")
    if anio:
        # Se descarta solo lo que declara OTRO rango; lo que no aclara años se deja pasar
        condiciones.append("(anio_desde IS NULL OR anio_desde <= ?)")
        params.append(int(anio))
        condiciones.append("(anio_hasta IS NULL OR anio_hasta >= ?)")
        params.append(int(anio))
    c.execute(f"""SELECT a.codigo AS "Código", a.marca_repuesto AS "Marca del repuesto",
                         a.marca_auto AS "Marca auto", a.modelo_auto AS "Modelo",
                         a.motor AS "Motor",
                         COALESCE(a.anio_desde, '') || '-' || COALESCE(a.anio_hasta, '') AS "Años",
                         (SELECT COUNT(*) FROM productos p
                           WHERE p.codigo_clean = a.codigo_clean) AS "En tu catálogo"
                  FROM aplicaciones a
                  WHERE {" AND ".join(condiciones)}
                  ORDER BY a.marca_repuesto, a.modelo_auto LIMIT ?""", params + [limite])
    return filas_a_listas(c)


def repuestos_de_este_auto(marca_auto, modelo="", anio=None, motor="", vin="", limite=500,
                            pieza=""):
    """Los códigos que le corresponden a ESTE auto. Es lo que hace falta en el mostrador: el VIN
    dice qué auto es, pero lo que se vende son códigos.

    IMPORTANTE sobre de dónde sale cada cosa. No existe una tabla pública que diga qué repuesto
    lleva cada auto — eso es una base de aplicaciones licenciada (TecDoc y similares) y se paga.
    Lo que sí hay es información propia del negocio, y se usa en este orden de confianza:

      1. Lo que YA se le puso a ESTE auto (por VIN o patente). Certeza total: alguien lo instaló.
      2. Lo que se le puso a OTROS autos del MISMO modelo. Evidencia real del mostrador.
      3. Lo que dicen las descripciones del catálogo del proveedor ('... FORD FIESTA 1.6 2010/15').
         Es lo más amplio y lo menos seguro: depende de cómo escriba cada proveedor.

    Devuelve un dict con las tres listas por separado, a propósito: mezclarlas escondería que
    una es un hecho y la otra una coincidencia de texto."""
    marca_auto = (marca_auto or "").strip().upper()
    modelo = (modelo or "").strip().upper()
    motor = (motor or "").strip().upper()
    vin = re.sub(r'\s', '', (vin or "").strip().upper())
    resultado = {"de_este_auto": [], "de_otros_iguales": [], "del_catalogo": [],
                 "del_fabricante": [], "modelo_usado": modelo, "sin_datos": True,
                 "marca_deducida": ""}
    # Una ficha con el modelo y sin la marca no buscaba nada en el catálogo: la marca se
    # deduce del modelo cuando no hay dudas (ver marca_del_modelo()).
    if modelo and not marca_auto:
        try:
            marca_auto = resultado["marca_deducida"] = marca_del_modelo(modelo) or ""
        except sqlite3.OperationalError as _err:
            anotar_error("repuestos_de_este_auto/marca_del_modelo", _err)

    # Fuente nueva y la más confiable de las que no son propias: el catálogo de aplicaciones
    # del fabricante del repuesto. No es una coincidencia de texto, es el fabricante diciendo
    # a qué auto le va su pieza.
    try:
        resultado["del_fabricante"] = buscar_aplicaciones(marca_auto, modelo, anio)
    except sqlite3.OperationalError as _err:
        anotar_error("repuestos_de_este_auto", _err)
        resultado["del_fabricante"] = []

    # --- 1. Lo que ya se le puso a este auto ---
    vehiculo_id = None
    if len(vin) == 17:
        c.execute("SELECT id FROM vehiculos WHERE vin = ?", (vin,))
        f = c.fetchone()
        vehiculo_id = f["id"] if f else None
    if vehiculo_id:
        c.execute("""SELECT h.descripcion_pieza AS "Pieza", h.codigo_pieza AS "Código",
                            h.marca_pieza AS "Marca", h.km_instalacion AS "Km",
                            substr(h.fecha_instalacion, 1, 10) AS "Fecha", h.producto_id AS "_pid"
                     FROM historial_piezas h WHERE h.vehiculo_id = ?
                     ORDER BY h.fecha_instalacion DESC""", (vehiculo_id,))
        resultado["de_este_auto"] = filas_a_listas(c)

    # --- 2. Lo que se le puso a otros autos del mismo modelo ---
    if modelo:
        # El modelo como palabra entera, igual que en el catálogo: con LIKE, la ficha de un
        # Golf contaba como un Gol (ver _nombra_este_auto()).
        _patron_modelo = re.compile(
            r"(?<![A-Z0-9])" + r"[\s\-/.]*".join(map(re.escape, normalizar_texto(modelo).split()))
            + r"(?![A-Z0-9])")
        _marca_canon = ALIAS_MARCA_VEHICULO.get(marca_auto, marca_auto)
        c.execute("""SELECT id, marca_auto, modelo_auto FROM vehiculos
                     WHERE UPPER(COALESCE(modelo_auto,'')) LIKE ? AND id IS NOT ?""",
                  (f"%{modelo.split()[0]}%", vehiculo_id))
        iguales = [f["id"] for f in c.fetchall()
                   if _patron_modelo.search(normalizar_texto(f["modelo_auto"] or ""))
                   and (not marca_auto or normalizar_texto(ALIAS_MARCA_VEHICULO.get(
                       (f["marca_auto"] or "").strip().upper(),
                       (f["marca_auto"] or "").strip().upper())) == normalizar_texto(_marca_canon)
                        or not (f["marca_auto"] or "").strip())]
        # Por tandas (ver en_tandas()), y se suman por código: el mismo repuesto puede
        # aparecer en más de una tanda.
        por_codigo = {}
        for tanda, marcadores in en_tandas(iguales):
            c.execute(f"""SELECT h.descripcion_pieza AS "Pieza", h.codigo_pieza AS "Código",
                                 h.marca_pieza AS "Marca", h.vehiculo_id AS "_vid"
                          FROM historial_piezas h
                          WHERE h.vehiculo_id IN ({marcadores})
                            AND h.codigo_pieza IS NOT NULL AND h.codigo_pieza <> ''""", tanda)
            for f in filas_a_listas(c):
                fila = por_codigo.setdefault(f["Código"].upper(), {
                    "Pieza": f["Pieza"], "Código": f["Código"], "Marca": f["Marca"],
                    "Veces": 0, "_autos": set()})
                fila["Veces"] += 1
                fila["_autos"].add(f["_vid"])
        resultado["de_otros_iguales"] = sorted(
            ({"Pieza": f["Pieza"], "Código": f["Código"], "Marca": f["Marca"],
              "Veces": f["Veces"], "Autos": len(f["_autos"])} for f in por_codigo.values()),
            key=lambda f: (-f["Autos"], -f["Veces"]))
        del resultado["de_otros_iguales"][100:]

    # --- 3. El catálogo, por lo que dicen las descripciones ---
    if marca_auto:
        # Todas las formas de escribir la marca: «VOLKSWAGEN» en la consulta se perdía los
        # productos que dicen «VW». El SQL es solo el prefiltro; quién le va de verdad lo
        # decide _nombra_este_auto().
        marca_canon = ALIAS_MARCA_VEHICULO.get(marca_auto, marca_auto)
        escrituras = ESCRITURAS_DE_MARCA.get(marca_canon) or [marca_auto]
        condiciones = ["p.descripcion IS NOT NULL",
                       "(" + " OR ".join(["UPPER(p.descripcion) LIKE ?"] * len(escrituras)) + ")"]
        params = [f"%{e}%" for e in escrituras]
        if modelo:
            condiciones.append("UPPER(p.descripcion) LIKE ?")
            params.append(f"%{modelo.split()[0]}%")
        # QUÉ PIEZA, y va en la CONSULTA y no después. Un auto con 1.855 repuestos en el
        # catálogo se lista cortado en los primeros 200, así que filtrar el resultado por
        # «junta de tapa» buscaba adentro de 200 que casi nunca son juntas. Filtrando en la
        # consulta, los 200 que quedan son los de esa pieza.
        for _palabra_pieza in re.split(r'\s+', (pieza or "").strip()):
            # Sin acentos de los dos lados: las listas escriben «INYECCION» y el que pregunta
            # escribe «inyección». normalizar_texto() hace lo mismo que el SQL de al lado.
            _limpia_pieza = normalizar_texto(_palabra_pieza)
            if len(_limpia_pieza) >= 3:
                _cond, _par = like_en_descripcion(f"%{_limpia_pieza}%")
                condiciones.append(_cond)
                params.extend(_par)
        c.execute(f"""SELECT p.id AS "ID", p.codigo_raw AS "Código", p.descripcion AS "Descripcion",
                             m.nombre AS "Marca", p.precio AS "Precio", p.stock AS "Stock"
                      FROM productos p JOIN marcas m ON m.id = p.marca_id
                      WHERE {" AND ".join(condiciones)}
                      LIMIT 20000""", params)
        candidatos = [f for f in filas_a_listas(c)
                      if _nombra_este_auto(f["Descripcion"], marca_canon, modelo)]

        # La cilindrada es lo que más afina ("1.6", "2.0"): si el motor la trae, se usa para
        # filtrar, pero solo descartando lo que declara OTRA cilindrada — lo que no dice nada
        # se deja pasar, porque la mayoría de las listas no la aclaran.
        cilindrada = None
        if motor:
            m_cil = re.search(r'\d[.,]\d', motor)
            cilindrada = m_cil.group(0).replace(",", ".") if m_cil else None

        filtrados = []
        for f in candidatos:
            desc = (f["Descripcion"] or "").upper()
            if anio:
                sirve = sirve_para_anio(f["Descripcion"], int(anio))
                if sirve is False:
                    continue
                f["Año"] = "✅ coincide" if sirve else "— no aclara"
            if cilindrada:
                otras = set(re.findall(r'\d[.,]\d', desc))
                if otras and cilindrada not in {o.replace(",", ".") for o in otras}:
                    continue
                f["Motor"] = "✅ coincide" if cilindrada in desc else "— no aclara"
            f["Categoría"] = clasificar_repuesto(f["Descripcion"])
            filtrados.append(f)

        filtrados.sort(key=lambda x: (x.get("Año") != "✅ coincide",
                                       x.get("Motor") != "✅ coincide",
                                       x["Categoría"]))
        resultado["del_catalogo"] = filtrados[:limite]
        resultado["total_catalogo"] = len(filtrados)

    resultado["sin_datos"] = not (resultado["de_este_auto"] or resultado["de_otros_iguales"]
                                   or resultado["del_catalogo"] or resultado["del_fabricante"])
    return resultado


def _nombra_este_auto(descripcion, marca, modelo):
    """Si la descripción nombra ESE auto: la marca (por cualquiera de sus escrituras) y el
    modelo como palabra entera.

    Antes era «la descripción contiene el texto», y con modelos cortos eso no sirve: «GOL» está
    adentro de «GOLF», «UP» adentro de «PICK UP» y «208» adentro de «71208». Medido sobre el
    catálogo real: «VW» Gol traía 241 productos del Golf, el Bora o el Polo; VW Up, 205 de 283 que
    no eran del Up; Peugeot 208, 176 de 377.

    Un modelo que lleva NÚMEROS («208», «C3», «S10», «500») tiene que estar en el pedazo de la
    descripción que le toca a esa marca o antes de la primera marca (ver marcas_vehiculo_en()):
    un número suelto en otro lado es una medida o un código. Uno de letras («GOL», «KA»,
    «PALIO») alcanza con que esté como palabra en cualquier lado, porque las listas ponen el
    modelo antes que la marca («Gol - Saveiro … Camiones VW») o lo pegan al de otra («SEAT,
    SURAN, GOL TREND»), y exigir el pedazo de la marca perdía 118 productos del Gol que sí son."""
    if not descripcion:
        return False
    marcas = [(normalizar_texto(ALIAS_MARCA_VEHICULO.get(m.upper(), m.upper())), cat, resto)
              for m, cat, resto in marcas_vehiculo_en(descripcion)]
    propias = [resto or "" for m, _cat, resto in marcas if m == normalizar_texto(marca)]
    if not propias and _marca_pegada_en(descripcion, marca):
        # La lista pegó la marca al código de adelante («97053Vw Gol», «LEIHTF30CSFord
        # Fiesta»): marcas_vehiculo_en() no la ve, pero está. Se busca el modelo en toda la
        # descripción.
        marcas, propias = [(normalizar_texto(marca), descripcion, descripcion)], [descripcion]
    if not propias:
        return False
    if not modelo:
        return True
    palabras = re.split(r"\s+", normalizar_texto(modelo).strip())
    patron = re.compile(r"(?<![A-Z0-9])" + r"[\s\-/.]*".join(map(re.escape, palabras))
                        + r"(?![A-Z0-9])")
    if re.search(r"\d", modelo):
        pedazos = propias + [marcas[0][1] or ""]
        return any(patron.search(normalizar_texto(separar_texto_pegado(x))) for x in pedazos)
    texto = re.sub(r"PICK[\s\-]*UP", " ", normalizar_texto(separar_texto_pegado(descripcion)))
    return bool(patron.search(texto))


def _marca_pegada_en(descripcion, marca):
    """Si la marca está en la descripción aunque venga pegada a un código: después de un número
    («97053Vw»), o escrita con mayúscula inicial después de letras («LEIHTF30CSFord»)."""
    for escritura in ESCRITURAS_DE_MARCA.get(marca) or [marca]:
        if re.search(r"(?<![A-Za-z])" + re.escape(escritura) + r"(?![A-Za-z])", descripcion, re.I):
            return True
        titulo = escritura.title()
        if re.search(re.escape(titulo) + r"(?![a-z])", descripcion):
            return True
    return False


def panel_vin(clave="vin", mostrar_ensenar=True):
    """La ÚNICA pantalla de VIN de la app. Antes había dos (una en el Buscador y otra en Modo
    Mecánico) que hacían casi lo mismo y ninguna terminaba en lo que hace falta: los códigos.
    Esta identifica el auto y va derecho a qué repuestos lleva."""
    explicar(
        "Pegá el número de chasis y te dice qué repuestos lleva ese auto.",
        "Del VIN salen con certeza el fabricante, el país y el año. El modelo y el motor no "
        "están normalizados: los aprende la app de tus propias fichas, o se los enseñás una "
        "vez."
    )
    vin_txt = st.text_input("VIN / número de chasis (17 caracteres):",
                             placeholder="Ej: 9BWZZZ377VT004251", key=f"{clave}_texto").strip().upper()
    if not vin_txt:
        return None

    d = decodificar_vin(vin_txt)
    if not d["valido"]:
        st.error(d["error"])
        return None

    # --- Qué auto es ---
    fab = d.get("fabricante") or "(fabricante no cargado)"
    if d.get("fabricante_por_prefijo"):
        fab += " (por familia de WMI)"
    linea = f"**{fab}** · {d['pais']}"
    if d.get("anio_estimado"):
        linea += f" · año {d['anio_estimado']}" if d.get("anio_preciso") else f" · año ~{d['anio_estimado']}"
    if d.get("modelo"):
        linea += f" · **{d['modelo']}**"
    if d.get("motor"):
        linea += f" · motor {d['motor']}"
    st.success(linea)

    # Este bloque esperaba un booleano que la app nunca seteaba: el mensaje no salía nunca.
    # Ahora se calcula de verdad, con la cuenta de la norma ISO 3779.
    if d.get("corregido"):
        st.warning(
            "✏️ **Se corrigieron letras que un VIN no puede tener:** "
            + "; ".join(d["corregido"])
            + f". Quedó **{d['vin']}**.\n\nLa norma prohíbe la I, la O y la Q justamente "
              "porque se confunden con 1 y 0, así que la corrección es segura."
        )
    _dv = d.get("digito_verificador")
    if _dv == "mal":
        st.error("❌ " + d.get("mensaje_digito", "") +
                  "\n\nBuscar repuestos con un VIN mal copiado es buscar los del auto equivocado.")
    elif _dv == "ok":
        st.caption("✅ " + d.get("mensaje_digito", ""))
    elif _dv == "no_aplica" and d.get("mensaje_digito"):
        st.caption("ℹ️ " + d["mensaje_digito"])

    # Si el modelo no lo sabemos, se ofrece preguntarle a la base pública de la NHTSA. Es
    # gratis y sin clave. No se consulta sola en cada búsqueda: sería pegarle a un servidor
    # ajeno cada vez que alguien tipea un VIN, y la mayoría ya están resueltos acá.
    if not d.get("modelo"):
        st.caption(
            "El modelo no está en la norma del VIN, así que hay que aprenderlo. Se puede "
            "preguntar a la base pública de la NHTSA (gratis, del gobierno de EE.UU.)."
        )
        if st.button("🌐 Preguntar a la base pública", key=f"nhtsa_{clave}"):
            with st.spinner("Consultando..."):
                _dn, _en = consultar_vin_en_nhtsa(d["vin"])
            st.session_state[f"nhtsa_res_{clave}"] = (_dn, _en)
        _guardado = st.session_state.get(f"nhtsa_res_{clave}")
        if _guardado:
            _dn, _en = _guardado
            if _en:
                st.warning(_en)
            elif _dn:
                st.success(
                    f"🌐 **{_dn['marca']} {_dn['modelo']}** {_dn['anio']}"
                    + (f" · motor {_dn['motor']}" if _dn["motor"] else "")
                    + (f" · {_dn['carroceria']}" if _dn["carroceria"] else "")
                    + (f"\n\nFabricado en {_dn['planta']}." if _dn["planta"] else "")
                )
                st.caption(
                    "Esto viene de una base ajena y **no se guardó**. Si es correcto, "
                    "confirmalo y queda aprendido para todos los VIN de ese patrón."
                )
                if st.button("✅ Es correcto, guardarlo", key=f"nhtsa_ok_{clave}"):
                    _modelo_n = " ".join(x for x in [_dn["marca"], _dn["modelo"]] if x)
                    aprender_modelo_de_vin(d["vin"], _modelo_n, _dn.get("marca") or "",
                                            _dn.get("motor") or "")
                    st.session_state.pop(f"nhtsa_res_{clave}", None)
                    avisar("success", f"Aprendido: ese patrón es un {_modelo_n}.")
                    st.rerun()

    ficha = d.get("vehiculo")
    if ficha:
        st.info(f"🎯 Este chasis ya está en tus fichas: patente **{ficha.get('patente')}**"
                 + (f" — cliente {ficha['cliente_nombre']}" if ficha.get("cliente_nombre") else ""))

    anio_usar = d.get("anio_estimado")
    if d.get("anio_alternativo"):
        # El código de año se repite cada 30. Elegir mal acá filtra los repuestos correctos.
        anio_usar = st.radio(
            "El VIN no permite saber cuál de los dos años es — elegí (miralo en la cédula):",
            sorted({d["anio_estimado"], d["anio_alternativo"]}), horizontal=True,
            key=f"{clave}_anio"
        )

    # --- Lo que importa: los códigos ---
    marca_para_buscar = None
    if d.get("fabricante"):
        marca_para_buscar = next(
            (mv for mv in MARCAS_VEHICULO if mv in d["fabricante"].upper()), None
        )

    if not marca_para_buscar:
        st.warning(
            "No puedo buscar repuestos porque no sé de qué marca es este WMI. "
            "Cargalo abajo en «Enseñar» y la próxima vez sale solo."
        )
    else:
        # OJO con value= junto a key=: Streamlit ignora el value y usa lo que haya en la sesión,
        # que arranca vacío. Por eso el modelo que el VIN reconocía ("Fiesta") aparecía en el
        # cartel verde pero el campo quedaba en blanco, y la búsqueda terminaba trayendo TODOS
        # los repuestos de la marca en vez de los del modelo.
        # Se siembra en session_state, y solo cuando cambia el VIN, para no pisar una corrección.
        clave_modelo = f"{clave}_modelo_manual"
        if st.session_state.get(f"{clave}_vin_previo") != vin_txt:
            st.session_state[clave_modelo] = d.get("modelo") or ""
            st.session_state[f"{clave}_vin_previo"] = vin_txt
        st.session_state.setdefault(clave_modelo, d.get("modelo") or "")

        modelo_manual = st.text_input(
            "Modelo (corregilo si hace falta):", key=clave_modelo,
            help="Se completa solo con lo que reconoce del VIN. Corregilo si no acertó; si lo "
                 "dejás vacío, busca todos los repuestos de la marca."
        ).strip()

        motor_reconocido = d.get("motor") or ""
        if motor_reconocido:
            st.caption(f"⚙️ Filtrando además por motor **{motor_reconocido}** "
                        "(se usa la cilindrada para afinar el catálogo).")

        r = repuestos_de_este_auto(
            marca_para_buscar, modelo_manual, anio_usar, d.get("motor") or "", vin_txt
        )
        _mostrar_repuestos_del_auto(r, marca_para_buscar, modelo_manual, anio_usar, clave)

    if mostrar_ensenar:
        with st.expander("✏️ Enseñarle a la app este auto (para que la próxima salga solo)"):
            _formulario_ensenar_vin(d, clave)
    return d


def _mostrar_repuestos_del_auto(r, marca, modelo, anio, clave):
    """Muestra los códigos separados por fuente. Van separados a propósito: uno es un hecho
    (se lo pusiste a este auto) y el otro es una coincidencia de texto en una descripción.
    Mezclarlos haría parecer que todos valen lo mismo, y no es así."""
    if r["de_este_auto"]:
        st.markdown("#### 🎯 Ya se le puso a ESTE auto")
        st.caption("Certeza total: alguien lo instaló y quedó registrado en la ficha.")
        st.dataframe([{k: v for k, v in f.items() if not k.startswith("_")}
                       for f in r["de_este_auto"]], width="stretch", hide_index=True)

    if r["de_otros_iguales"]:
        st.markdown("#### 🔁 Se le puso a otros autos del mismo modelo")
        st.caption(
            "Evidencia real de tu mostrador: estos códigos se instalaron en autos iguales. "
            "«Autos» es en cuántos distintos — mientras más, más confiable."
        )
        st.dataframe(r["de_otros_iguales"], width="stretch", hide_index=True)

    if r.get("del_fabricante"):
        st.markdown(f"#### 🏭 Según el catálogo del fabricante ({len(r['del_fabricante'])})")
        explicar(
            "Esto no es una coincidencia de texto: es el fabricante del repuesto diciendo a qué "
            "auto le va su pieza.",
            "Es lo más confiable después de lo que ya le pusiste vos. La columna «En tu catálogo» "
            "dice si ese código está cargado en tus listas."
        )
        st.dataframe(r["del_fabricante"], width="stretch", hide_index=True)

    if r["del_catalogo"]:
        total = r.get("total_catalogo", len(r["del_catalogo"]))
        st.markdown(f"#### 📚 Del catálogo, según las descripciones ({total} código(s))")
        st.caption(
            "Sale de que la descripción del proveedor menciona esta marca y modelo. Es lo más "
            "amplio y lo menos seguro: depende de cómo escriba cada proveedor. "
            + (f"Se filtró por año {anio} descartando lo que declara otro rango. " if anio else "")
            + "Confirmá por código antes de vender."
        )
        # Antes acá el filtro listaba el texto crudo previo a la marca en cada descripción, así
        # que con varios proveedores salían cientos de opciones casi iguales ("JUNTA TAPA DE
        # CILINDROS", "JUNTA DE TAPA CIL.", "JUEGO JUNTA TAPA"...) y no servía para encontrar
        # nada. Ahora son ~20 familias fijas, con la cantidad al lado.
        conteo = {}
        for f in r["del_catalogo"]:
            conteo[f["Categoría"]] = conteo.get(f["Categoría"], 0) + 1
        orden_familias = sorted(conteo, key=lambda k: (-conteo[k], k))
        etiquetas = {f"{k} ({conteo[k]})": k for k in orden_familias}

        cf1, cf2 = st.columns([2, 1])
        with cf1:
            elegidas_lbl = st.multiselect("Tipo de pieza:", list(etiquetas.keys()),
                                           key=f"{clave}_cats",
                                           placeholder="Todas — o elegí una o varias")
        with cf2:
            texto_filtro = st.text_input("Buscar en estos resultados:", key=f"{clave}_txt",
                                          placeholder="Ej: delantero, 1.6, kit").strip()

        elegidas = {etiquetas[e] for e in elegidas_lbl}
        filas = [f for f in r["del_catalogo"] if not elegidas or f["Categoría"] in elegidas]
        if texto_filtro:
            # Todas las palabras tienen que estar, sin importar el orden ni los acentos: así
            # "kit delantero" encuentra "Kit de rodamiento delantero" igual.
            palabras = [normalizar_texto(x) for x in texto_filtro.split() if x.strip()]
            filas = [f for f in filas
                     if all(pal in normalizar_texto(f"{f['Código']} {f['Descripcion']}")
                            for pal in palabras)]
        st.caption(f"Mostrando {len(filas)} de {len(r['del_catalogo'])}.")
        st.dataframe(quitar_id(filas), width="stretch", hide_index=True)
        st.download_button(
            "⬇️ Bajar estos códigos en Excel",
            data=to_excel_bytes(quitar_id(filas)),
            file_name=f"repuestos_{marca}_{modelo or 'todos'}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{clave}_dl"
        )
        if total > len(r["del_catalogo"]):
            st.caption(f"(mostrando {len(r['del_catalogo'])} de {total} — afiná el modelo para ver menos)")

    if r["sin_datos"]:
        st.warning(
            f"No encontré repuestos para **{marca} {modelo}**. Puede ser que en tu catálogo las "
            "descripciones lo escriban distinto (probá con otra forma del modelo, o dejá el modelo "
            "vacío para ver todo lo de la marca), o que todavía no tengas cargada esa lista."
        )


def _formulario_ensenar_vin(d, clave):
    """Cargar el modelo y el motor de este patrón, una sola vez."""
    st.caption(
        f"Patrón `{d['wmi']}`-`{d['vds']}` · 8ª posición `{d['codigo_motor']}`. "
        "El modelo se guarda por el patrón; el motor por la 8ª posición, que vale para toda la marca."
    )
    if not d.get("fabricante"):
        cw1, cw2 = st.columns(2)
        nuevo_fab = cw1.text_input("Fabricante de este WMI:", key=f"{clave}_fab")
        nuevo_pais = cw2.text_input("País:", value=d["pais"], key=f"{clave}_pais")
        if st.button("💾 Guardar fabricante", key=f"{clave}_guardar_fab"):
            if nuevo_fab.strip():
                agregar_fabricante_vin(d["wmi"], nuevo_fab, nuevo_pais)
                avisar("success", f"WMI {d['wmi']} guardado.")
                st.rerun()
            else:
                st.warning("Escribí el fabricante.")

    with st.form(f"{clave}_form_ensenar", clear_on_submit=True):
        ce1, ce2 = st.columns(2)
        mod_in = ce1.text_input("Modelo", value=d.get("modelo") or "", placeholder="Ej: FIESTA")
        mot_in = ce2.text_input("Motor", value=d.get("motor") or "", placeholder="Ej: 1.6 16V nafta")
        nota_in = st.text_input("Nota (opcional)", placeholder="Ej: 5 puertas")
        alcance = st.radio("El MODELO, ¿para qué VIN vale?",
                           ["Este patrón exacto (5 caracteres)", "Toda la familia (3 caracteres)"],
                           horizontal=True)
        if st.form_submit_button("💾 Guardar", type="primary"):
            hechos = []
            if mod_in.strip():
                largo = 5 if alcance.startswith("Este") else 3
                enseniar_modelo_vin(d["wmi"], d["vds"][:largo], mod_in, nota_in)
                hechos.append(f"modelo {mod_in.strip()}")
            if mot_in.strip():
                enseniar_motor_vin(d["wmi"], d["codigo_motor"], mot_in, nota_in)
                hechos.append(f"motor {mot_in.strip()}")
            if hechos:
                avisar("success", "Guardado: " + " y ".join(hechos) + ".")
                st.rerun()
            else:
                st.warning("Escribí al menos el modelo o el motor.")


def esquemas_de_vehiculo(marca_vehiculo):
    c.execute("""SELECT id, titulo, marca_auto, modelo_auto, sistema FROM esquemas
                 WHERE UPPER(marca_auto) LIKE ? ORDER BY titulo""", (f"%{marca_vehiculo}%",))
    return [dict(r) for r in c.fetchall()]

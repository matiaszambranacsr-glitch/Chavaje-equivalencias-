"""El diagnóstico de salud del catálogo y por qué dos códigos no se relacionan.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================================================
# DIAGNÓSTICO DE SALUD DEL CATÁLOGO
# ============================================================================================
def envejecimiento_de_precios():
    """Cuánto atrasada está la lista de cada proveedor, medido con TU propio historial.

    En Argentina una lista de precios de hace dos meses no es una lista de precios: es un dato
    viejo con el que se vende perdiendo. Pero «hace dos meses» no dice cuánto perdés — depende
    de cuánto aumentó ESE proveedor.

    No hace falta ningún índice ni ninguna consulta: la app ya guarda cada cambio de precio en
    historial_precios. Con eso se mide a qué ritmo aumenta cada lista, se lo compara con los
    días que pasaron desde la última importación, y sale un número que sirve: «la lista de
    MOTORARG tiene 45 días y viene subiendo 9% por mes, así que estos precios están 13% abajo».

    El ritmo sale de la MEDIANA y no del promedio, a propósito: en cada importación hay siempre
    un puñado de productos que pasan de 100 a 100.000 porque cambió la unidad o se corrigió un
    error de carga, y con el promedio esos pocos deciden el número de toda la lista.

    Devuelve una lista por proveedor, ordenada por lo que más atrasado está."""
    try:
        c.execute("""
            WITH cambios AS (
                SELECT hp.producto_id, p.marca_id, hp.precio, hp.fecha,
                       LAG(hp.precio) OVER (PARTITION BY hp.producto_id ORDER BY hp.fecha) AS antes,
                       LAG(hp.fecha)  OVER (PARTITION BY hp.producto_id ORDER BY hp.fecha) AS fecha_antes
                FROM historial_precios hp
                JOIN productos p ON p.id = hp.producto_id
            )
            SELECT marca_id,
                   precio, antes,
                   julianday(fecha) - julianday(fecha_antes) AS dias
            FROM cambios
            WHERE antes IS NOT NULL AND antes > 0 AND precio > 0
              AND julianday(fecha) - julianday(fecha_antes) >= 1""")
        cambios = filas_a_listas(c)
    except sqlite3.OperationalError as _err:
        anotar_error("envejecimiento_de_precios", _err)
        cambios = []

    ritmo_por_marca = {}
    por_marca = {}
    for x in cambios:
        por_marca.setdefault(x["marca_id"], []).append(x)
    for marca_id, filas in por_marca.items():
        mensuales = []
        for x in filas:
            try:
                razon = x["precio"] / x["antes"]
                # A ritmo mensual: un 4% en 15 días no es lo mismo que un 4% en 90.
                mensuales.append(razon ** (30.0 / max(x["dias"], 1.0)) - 1)
            except (ZeroDivisionError, OverflowError, ValueError):
                continue
        if len(mensuales) >= 20:
            mensuales.sort()
            ritmo_por_marca[marca_id] = mensuales[len(mensuales) // 2]

    try:
        # COUNT(DISTINCT ...) y no COUNT: el LEFT JOIN con el historial multiplica la fila del
        # producto por cada cambio de precio que tenga, así que contando a secas un proveedor
        # con dos importaciones aparece con el doble de productos.
        c.execute("""SELECT m.id, m.nombre, COUNT(DISTINCT p.id) AS productos,
                            MAX(hp.fecha) AS ultima,
                            COUNT(DISTINCT CASE WHEN p.precio IS NOT NULL THEN p.id END) AS con_precio
                     FROM marcas m
                     JOIN productos p ON p.marca_id = m.id
                     LEFT JOIN historial_precios hp ON hp.producto_id = p.id
                     WHERE m.tipo <> 'OEM'
                     GROUP BY m.id""")
        marcas = filas_a_listas(c)
    except sqlite3.OperationalError as _err:
        anotar_error("envejecimiento_de_precios", _err)
        return []

    hoy = datetime.now()
    ipc = ipc_guardado()
    salida = []
    for m in marcas:
        if not m["con_precio"]:
            continue
        dias = None
        if m["ultima"]:
            try:
                # Nunca negativo: una fecha adelantada —el reloj de la máquina, o una lista
                # cargada con fecha futura— no significa que los precios sean del futuro.
                dias = max((hoy - datetime.strptime(str(m["ultima"])[:19],
                                                     "%Y-%m-%d %H:%M:%S")).days, 0)
            except ValueError:
                dias = None
        ritmo = ritmo_por_marca.get(m["id"])
        atraso = (((1 + ritmo) ** (dias / 30.0) - 1) if (ritmo is not None and dias) else None)
        # La inflación oficial desde la última carga: con UNA sola importación no hay ritmo
        # propio, y «tiene 40 días» no decía cuánto. Es un piso (ver inflacion_desde()).
        inflacion, _hasta = inflacion_desde(m["ultima"], ipc)
        salida.append({
            "Lista": m["nombre"], "Productos con precio": m["con_precio"],
            "Días desde la última carga": dias,
            "Sube por mes": (f"{miles(ritmo * 100, 1)}%" if ritmo is not None else "—"),
            "Estarían atrasados": (f"{atraso * 100:.0f}%" if atraso else
                                   f"≈{inflacion * 100:.0f}% (inflación)" if inflacion else "—"),
            "Inflación desde la última carga (INDEC)": (
                f"{miles(inflacion * 100, 1)}% (a {_hasta})" if inflacion is not None else "—"),
            "_atraso": atraso or inflacion or 0, "_dias": dias or 0, "_ritmo": ritmo,
        })
    salida.sort(key=lambda x: (-x["_atraso"], -x["_dias"]))
    return salida




# Las tareas que corren solas, por atrás, y que nadie mira mientras corren: por dónde
# empiezan los «donde» de sus errores, y con qué nombre se muestran.
TAREAS_QUE_SE_VIGILAN = (("_trabajo_de_fondo", "trabajo de fondo"), ("vigilar_la_copia", "copia a GitHub"),
                   ("subir_backup", "copia a GitHub"), ("bajar_fotos", "fotos de las fichas"),
                   ("buscar_imagen_en_ficha", "fotos de las fichas"),
                   ("descargar_imagen", "fotos de las fichas"),
                   ("actualizar_parque_automotor", "parque automotor (DNRPA)"),
                   ("contexto_de_precios", "dólar e inflación"),
                   ("actualizar_ipc_de_transporte", "IPC de transporte"),
                   ("actualizar_el_registro_chas", "registro de CHAS"))
# Desde cuántas veces se avisa. Una sola es un sitio que no contestó justo esa vez.
FALLAS_PARA_AVISAR = 5


def errores_de_las_tareas_de_fondo():
    """[(tarea, cuántas veces, el último error)] de las tareas automáticas que fallaron al menos
    FALLAS_PARA_AVISAR veces desde que arrancó el servidor, de la que más a la que menos."""
    por_tarea = {}
    for e in list(_ULTIMOS_ERRORES):
        nombre = next((n for prefijo, n in TAREAS_QUE_SE_VIGILAN
                       if str(e.get("donde", "")).startswith(prefijo)), None)
        if nombre:
            cuantos, _ = por_tarea.get(nombre, (0, None))
            por_tarea[nombre] = (cuantos + 1, e)
    return sorted(((t, n, e) for t, (n, e) in por_tarea.items() if n >= FALLAS_PARA_AVISAR),
                  key=lambda x: -x[1])


def diagnostico_de_salud():
    """Corre todos los controles de mantenimiento de una y devuelve solo lo que necesita atención.

    Por qué: los controles se fueron sumando de a uno y quedaron repartidos en distintas
    pantallas de Mantenimiento. Ninguno avisa solo, así que hay que acordarse de entrar y mirar
    los siete — y en la práctica nadie lo hace hasta que algo ya salió mal. Esto los junta en un
    solo lugar y aparece cuando hay algo para revisar.

    Cada punto trae a dónde ir y qué pasa si no se toca, porque un número suelto no dice nada."""
    problemas = []

    def sumar(nivel, titulo, detalle, donde):
        problemas.append({"nivel": nivel, "titulo": titulo, "detalle": detalle, "donde": donde})

    # LAS TAREAS AUTOMÁTICAS QUE VIENEN FALLANDO. Sus errores se anotaban (anotar_error()) y
    # se veían solo entrando a buscarlos: las 5.063 fotos de FISPA fallaron por el certificado
    # sin que ningún aviso lo dijera. Ver errores_de_las_tareas_de_fondo().
    try:
        for _tarea, _cuantos, _ultimo in errores_de_las_tareas_de_fondo()[:2]:
            sumar("medio", f"La tarea automática «{_tarea}» falló {_cuantos} veces",
                  f"Lo último: {_ultimo['tipo']} ({_ultimo['detalle'][:90]}), el "
                  f"{_ultimo['cuando']}. La app sigue andando, pero eso no se está haciendo.",
                  "🗂️ Administrar → 🧹 Mantenimiento → 🩺 Estado y papelera")
    except Exception as _err:
        anotar_error("diagnostico_de_salud/errores_de_fondo", _err)

    # LA BASE DAÑADA. Lo anota la subida de la copia (ver la_base_esta_sana()), que en ese caso
    # no sube nada para no pisar la última copia buena.
    try:
        _danada = obtener_config("base_danada", "")
        if _danada:
            sumar("alto", "🧯 La base tiene daño y la copia a GitHub quedó frenada",
                  f"El control de integridad falló ({_danada}). La última copia buena de GitHub "
                  "está intacta. Bajá un backup ahora y restaurá desde la copia de GitHub o "
                  "desde un backup anterior.",
                  miga_hasta("Backup y config"))
    except Exception as _err:
        anotar_error("diagnostico_de_salud/base_danada", _err)

    # LA COPIA EN UN REPOSITORIO PÚBLICO. Es lo más grave que puede decir esta lista: la base
    # entera —precios, clientes, teléfonos, usuarios— descargable por cualquiera. Lo anota el
    # hilo que sube la copia (ver _anotar_si_el_repositorio_es_publico()); acá solo se lee.
    try:
        if obtener_config("repo_copia_publico", "") == "1":
            if not clave_de_la_copia():
                sumar("alto", "🔓 La copia de tu base se sube SIN CIFRAR a un repositorio PÚBLICO",
                      "Cualquiera puede bajarla de GitHub: precios, clientes, teléfonos, patentes "
                      "y usuarios. Poné el repositorio en privado (GitHub → Settings → General → "
                      "Change visibility) y agregá en los secretos una línea "
                      "clave_copia = \"una frase larga\" para que la copia viaje cifrada.",
                      miga_hasta("Backup y config"))
            else:
                sumar("medio", "El repositorio de la copia es público",
                      "La copia ya se sube cifrada, pero las anteriores al cifrado siguen en el "
                      "historial de la rama «copia-de-seguridad». Poné el repositorio en privado "
                      "(GitHub → Settings → General → Change visibility).",
                      miga_hasta("Backup y config"))
    except Exception as _err:
        anotar_error("diagnostico_de_salud/repo_publico", _err)

    # Lo primero de todo: clientes esperando algo que ahora hay. Es lo único de esta lista
    # que es plata a un llamado de distancia, y lo que más rápido se pierde: entra la
    # mercadería, nadie se acuerda quién la pidió, y el cliente ya la compró en otro lado.
    try:
        esperando = consultas_que_ahora_hay_en_stock()
        if esperando:
            sumar("alto", f"{len(esperando)} cliente(s) esperando algo que YA hay",
                  "Preguntaron por algo que en ese momento no tenías y ahora está en stock. "
                  "Un llamado y es una venta. Es lo que más rápido se enfría.",
                  f"{miga_hasta('Para pedir')} → 📞 Consultas de clientes")
    except Exception as _err:
        anotar_error("diagnostico_de_salud/consultas", _err)

    # Los vínculos ya cargados con evidencia en contra. Va arriba porque es el único punto de
    # esta lista que describe algo que la búsqueda está devolviendo MAL ahora mismo: no es
    # trabajo pendiente, es un resultado equivocado que alguien ya puede estar leyendo. El
    # número lo deja medido descubrimiento_post_importacion() después de cada importación; acá
    # solo se lee, porque medirlo cuesta 11 s y esto corre en todas las pantallas.
    try:
        _dud = int(obtener_config("dudosos_cargados", "0") or 0)
        if _dud:
            _rev = int(obtener_config("dudosos_revisados", "0") or 0)
            sumar("alto", f"{_dud} vínculo(s) YA cargados tienen evidencia en contra",
                  f"De {miles(_rev)} vínculos revisados después de la última importación "
                  f"({obtener_config('dudosos_fecha', 'sin fecha')}). No son sugerencias "
                  "esperando: están activos, y la búsqueda los está devolviendo. Se ven de peor "
                  "a mejor, con el motivo al lado, y se cortan los peores de una.",
                  miga_hasta("Revisar los vínculos que YA están cargados"))
    except (TypeError, ValueError) as _err:
        anotar_error("diagnostico_de_salud/dudosos", _err)

    # Los precios viejos. Es el único punto de esta lista que cuesta plata en CADA venta, no
    # cuando algo sale mal: vender con una lista de hace dos meses es vender perdiendo la
    # diferencia, y nadie se entera hasta que repone.
    try:
        for _vieja in envejecimiento_de_precios():
            if _vieja["_ritmo"] is not None and _vieja["_atraso"] >= 0.05:
                sumar("alto",
                      f"Los precios de {_vieja['Lista']} estarían "
                      f"{_vieja['Estarían atrasados']} abajo",
                      f"Esa lista se cargó hace {_vieja['_dias']} días y viene subiendo "
                      f"{_vieja['Sube por mes']} por mes — medido con tus propias "
                      f"importaciones, no con ningún índice. Pedile la lista nueva al "
                      f"proveedor.",
                      miga_hasta("Importaciones"))
            elif _vieja["_ritmo"] is None and (_vieja["_dias"] >= 60 or _vieja["_atraso"] >= 0.05):
                _inf_txt = _vieja.get("Inflación desde la última carga (INDEC)") or "—"
                sumar("medio",
                      f"La lista de {_vieja['Lista']} tiene {_vieja['_dias']} días"
                      + (f": la inflación oficial desde entonces fue {_inf_txt}"
                         if _inf_txt != "—" else ""),
                      "Todavía no la importaste dos veces, así que no puedo medir cuánto "
                      "sube ese proveedor"
                      + (" —la inflación del INDEC es un piso de cuánto quedó abajo—"
                         if _inf_txt != "—" else "")
                      + ". Con la próxima importación la app va a saber a qué ritmo aumenta.",
                      miga_hasta("Qué tan atrasada está cada lista"))
    except Exception as _err:
        anotar_error("diagnostico_de_salud/precios viejos", _err)

    try:
        clavos = productos_estancados(365)
        if len(clavos) >= 10:
            plata = sum(x["Plata parada"] or 0 for x in clavos)
            sumar("medio", f"${miles(plata, 0)} inmovilizados en {len(clavos)} producto(s)",
                  "Hace más de un año que no se venden y siguen ocupando estante. No es "
                  "urgente, pero es plata dormida que conviene mirar antes de la próxima compra.",
                  f"{miga_hasta('Para pedir')} → 🧊 Clavos: lo que no se mueve")
    except Exception as _err:
        anotar_error("diagnostico_de_salud/clavos", _err)

    try:
        gratis = equivalencias_puenteadas_por_reemplazo(50)
        if gratis:
            sumar("bajo", f"{len(gratis)} equivalencia(s) esperando, sin trabajo",
                  "Salen de los reemplazos de código que ya cargaste: son productos que el "
                  "cambio de número dejó separados. No hay que investigar nada, solo aprobarlas.",
                  miga_hasta("Reunir lo que separó un cambio de número"))
    except Exception as _err:
        anotar_error("diagnostico_de_salud/puenteadas", _err)

    # LOS CÓDIGOS DE BARRAS CARGADOS COMO CÓDIGO DE FÁBRICA. La app sabía detectarlos desde
    # hace rato —codigos_de_barras_mal_cargados() devuelve la lista y el número— y tenía el
    # botón que los arregla, pero no avisaba NUNCA: había que entrar a la herramienta a mirar.
    # Sobre la base real son 8.319 de MOTORARG, y cada uno arrastra una equivalencia que no
    # lleva a ningún lado: 8.319 de las 24.774 equivalencias cargadas, UNA DE CADA TRES.
    # Va en alto por eso, y porque no se arregla solo a propósito: el arreglo borra productos,
    # y lo que borra tiene que decidirlo una persona.
    try:
        _mal_barras = codigos_de_barras_mal_cargados()
        if _mal_barras:
            _total_b = sum(x["Códigos de barras cargados como código de fábrica"]
                           for x in _mal_barras)
            _listas_b = ", ".join(x["Lista"] for x in _mal_barras[:4])
            sumar("alto",
                  f"{miles(_total_b)} código(s) de barras cargados como código de fábrica",
                  f"En {_listas_b} lo que se importó en la columna del código original son "
                  "códigos de barras. Cada uno deja una equivalencia que no lleva a ningún "
                  "lado, y son las que hacen que el buscador prometa un equivalente que no "
                  "existe. El arreglo es un botón: el número pasa a la columna de código de "
                  "barras —se sigue escaneando y buscando igual— y desaparece el producto "
                  "fantasma que lo representaba.",
                  miga_hasta("Códigos de barras cargados como código de fábrica"))
    except Exception as _err:
        anotar_error("diagnostico_de_salud/barras_mal_cargados", _err)

    try:
        puentes = contar_codigos_puente(30)
        if puentes:
            sumar("alto", f"{puentes} código(s) puente",
                  "Están vinculados a decenas de repuestos DE VARIAS MARCAS y fusionan familias "
                  "que no tienen relación. Es lo que hace que el buscador devuelva cosas que no "
                  "entran. (Un código con muchos vínculos pero todos de una sola marca no entra "
                  "acá: esa es la tabla de referencias cruzadas del propio proveedor, y está "
                  "bien.)",
                  miga_hasta("Códigos puente"))
    except Exception as _err:
        anotar_error("diagnostico_de_salud", _err)
        pass

    # Listas que quedaron aisladas: es la causa más común de «la app no relaciona los
    # proveedores», y hasta ahora no avisaba nada. Una lista entera sin un solo producto que
    # cruce no es mala suerte, es una importación sin la columna de código de fábrica.
    try:
        _filas_cr, _res_cr = salud_de_los_cruces()
        if _res_cr.get("listas_aisladas"):
            _cuales = ", ".join(_res_cr["listas_aisladas"][:6])
            if len(_res_cr["listas_aisladas"]) > 6:
                _cuales += f" y {len(_res_cr['listas_aisladas']) - 6} más"
            sumar("alto",
                  f"{len(_res_cr['listas_aisladas'])} lista(s) no cruzan con ninguna otra marca",
                  f"Ninguno de los productos de {_cuales} está vinculado a otra marca. Buscando "
                  "un código de esas listas no van a aparecer los equivalentes de los demás "
                  "proveedores. Casi siempre es que se importaron sin indicar la columna de "
                  "código de fábrica (OEM), que es la única que las une con el resto.",
                  miga_hasta("¿Cuánto cruza tu catálogo entre proveedores?"))
        # El mismo síntoma con la causa opuesta, y va aparte porque lo que hay que hacer es
        # otra cosa: acá las equivalencias ya están encontradas y lo que falta es aprobarlas.
        # Mandar a reimportar una lista que está bien es hacer perder una tarde.
        if _res_cr.get("listas_esperando"):
            _cuales_e = ", ".join(_res_cr["listas_esperando"][:6])
            if len(_res_cr["listas_esperando"]) > 6:
                _cuales_e += f" y {len(_res_cr['listas_esperando']) - 6} más"
            _cuantos_e = sum(f["Esperando revisión"] for f in _filas_cr
                             if f["Marca"] in _res_cr["listas_esperando"])
            sumar("alto",
                  f"{_cuales_e}: las equivalencias están encontradas y sin aprobar",
                  f"{miles(_cuantos_e)} producto(s) de esa(s) lista(s) ya tienen equivalencias "
                  "esperando revisión. Hasta que no se aprueben, buscar uno de sus códigos no "
                  "muestra los equivalentes de los otros proveedores — la lista está bien "
                  "importada, lo que falta es revisarlas.",
                  miga_hasta("Equivalencias sugeridas"))
    except Exception as _err:
        anotar_error("diagnostico_de_salud", _err)
        pass

    try:
        espejadas = contar_equivalencias_espejadas()
        if espejadas:
            sumar("medio", f"{miles(espejadas)} equivalencias anotadas dos veces",
                  "La misma relación guardada en las dos direcciones. No cambia lo que encuentra "
                  "el buscador, pero duplica todos los conteos.",
                  miga_hasta("Equivalencias anotadas dos veces"))
    except Exception as _err:
        anotar_error("diagnostico_de_salud", _err)
        pass

    try:
        basura = contar_codigos_basura()
        if basura:
            sumar("alto", f"{basura} código(s) que son un número suelto",
                  "Entraron cantidades o números de orden en la columna del código. Cada uno "
                  "vincula entre sí repuestos que no tienen nada que ver.",
                  miga_hasta("Códigos que son solo un número suelto"))
    except Exception as _err:
        anotar_error("diagnostico_de_salud", _err)
        pass

    try:
        con_punto = contar_codigos_con_decimal()
        if con_punto:
            sumar("medio", f"{con_punto} código(s) terminados en '.0'",
                  "Excel los guardó como número. Se encuentran igual, pero el código que se "
                  "muestra y se copia en un presupuesto está mal.",
                  miga_hasta("Códigos que quedaron con '.0'"))
    except Exception as _err:
        anotar_error("diagnostico_de_salud", _err)
        pass

    try:
        # El SIN_ESPEJO no es adorno: el aviso dice «par(es)» y contaba FILAS. La misma
        # relación anotada de ida y de vuelta —que es exactamente lo que cuenta
        # contar_equivalencias_espejadas(), y para lo que hay una herramienta entera— se
        # contaba dos veces. Reproducido con dos productos y las dos filas: el aviso decía
        # «2 par(es)» habiendo uno solo. Ver precios_incoherentes_entre_equivalentes(), que
        # tenía el mismo agujero y ahí se VEÍA: el par aparecía dos veces en la tabla, con
        # las columnas dadas vuelta.
        # Una lista entera en otra escala va en su propio aviso (abajo), con el remedio que le
        # corresponde: contada acá, eran 1.570 «pares» de TARANTO que tapaban los de verdad.
        _fuera = sorted(marcas_con_precios_fuera_de_escala())
        _sin_fuera = (" AND ma.nombre NOT IN (" + ",".join("?" * len(_fuera)) + ")"
                      " AND mb.nombre NOT IN (" + ",".join("?" * len(_fuera)) + ")"
                      if _fuera else "")
        c.execute(f"""SELECT COUNT(*) FROM equivalencias e
                     JOIN productos pa ON pa.id = e.producto_a_id
                     JOIN productos pb ON pb.id = e.producto_b_id
                     JOIN marcas ma ON ma.id = pa.marca_id
                     JOIN marcas mb ON mb.id = pb.marca_id
                     WHERE {SIN_CONTAR_EL_ESPEJO} AND pa.precio > 0 AND pb.precio > 0
                       AND MAX(pa.precio, pb.precio) / MIN(pa.precio, pb.precio) >= 8
                       {_sin_fuera}""", _fuera + _fuera)
        precios = c.fetchone()[0]
        for _marca in _fuera:
            _d = escala_de_precios_por_marca()[_marca]
            _cuanto = (f"{miles(1 / _d['factor'], 0)} veces menos" if _d["factor"] < 1
                       else f"{miles(_d['factor'], 0)} veces más")
            sumar("alto", f"Los precios de {_marca} están en otra escala",
                  f"Cuestan {_cuanto} que los mismos repuestos de "
                  f"{', '.join(_d['contra'][:4])} ({miles(_d['comparaciones'])} comparaciones). "
                  "Casi seguro la lista necesita un coeficiente o está vieja: hasta "
                  "corregirlo, se cotiza mal.",
                  f"{miga_hasta('Marcas')} → 📏 Coeficiente de la lista")
        _dos = len(codigos_con_dos_precios_en_la_misma_lista())
        if _dos:
            sumar("medio", f"{miles(_dos)} código(s) vinieron dos veces en la lista con precios "
                           "distintos",
                  "Quedó el último renglón, sin que nadie eligiera: puede ser la unidad contra "
                  "la caja, o dos productos que se escriben casi igual.",
                  miga_hasta("Códigos que vinieron dos veces con precios distintos"))
        if precios:
            sumar("alto", f"{precios} par(es) de equivalentes con precios muy distintos",
                  "O el precio está mal cargado, o no son la misma pieza. Cualquiera de las dos "
                  "cuesta plata: o cotizás mal, o vendés algo que no entra.",
                  miga_hasta("Precios que no cierran entre equivalentes"))
    except Exception as _err:
        anotar_error("diagnostico_de_salud", _err)
        pass

    try:
        c.execute("SELECT COUNT(*) FROM equivalencias_pendientes")
        pendientes = c.fetchone()[0]
        if pendientes > 500:
            sumar("medio", f"{miles(pendientes)} vínculos esperando revisión",
                  "Mientras no se revisen no están cargados, así que el buscador no los usa.",
                  miga_hasta("Equivalencias sugeridas"))
    except Exception as _err:
        anotar_error("diagnostico_de_salud", _err)
        pass

    try:
        c.execute("SELECT COUNT(*) FROM equivalencias WHERE confianza IS NULL")
        sin_punt = c.fetchone()[0]
        if sin_punt > 200:
            sumar("medio", f"{miles(sin_punt)} vínculos sin puntuar",
                  "El buscador no puede decirte qué tan sólido es el camino de cada resultado "
                  "hasta que se calculen. Es un solo botón.",
                  miga_hasta("Puntuar los vínculos para el buscador"))
    except sqlite3.OperationalError as _err:
        anotar_error("diagnostico_de_salud", _err)
        pass

    try:
        c.execute("SELECT COUNT(*) FROM aplicaciones")
        if c.fetchone()[0] == 0:
            c.execute("SELECT COUNT(*) FROM productos")
            if c.fetchone()[0] > 500:
                # ALTO y no medio, y el texto cambió: la app puede deducir 114.673
                # aplicaciones de las descripciones que YA tiene, sin importar nada. Decir
                # «varios fabricantes los publican gratis» mandaba a buscar planillas afuera
                # cuando el dato estaba adentro, y con la tabla vacía la búsqueda por vehículo
                # —una pantalla entera— no tiene con qué trabajar.
                sumar("alto", "La búsqueda por vehículo no tiene datos",
                      "La tabla que dice qué repuesto le va a cada auto está VACÍA, así que "
                      "«🚙 Repuestos por vehículo» y el cruce por auto no tienen con qué "
                      "trabajar. No hace falta conseguir nada afuera: la app las deduce de las "
                      "descripciones que ya tenés. Se deja pedido solo al abrir la app y lo "
                      "hace la tarea de fondo; si sigue en cero, corrélo a mano.",
                      miga_hasta("Catálogo de aplicaciones"))
    except sqlite3.OperationalError as _err:
        anotar_error("diagnostico_de_salud", _err)
        pass

    try:
        quiebres = productos_por_quebrar(dias_aviso=14)
        en_cero = [x for x in quiebres if x["Stock"] <= 0]
        if en_cero:
            sumar("alto", f"{len(en_cero)} producto(s) que se venden seguido están sin stock",
                  "Se venden todos los meses y están en cero. Un cliente los va a pedir y no "
                  "van a estar.",
                  f"{miga_hasta('Para pedir')} → ⏳ Lo que se va a acabar")
        elif quiebres:
            sumar("medio", f"{len(quiebres)} producto(s) se acaban en menos de 2 semanas",
                  "Según el ritmo con que se vienen vendiendo y el stock que queda.",
                  f"{miga_hasta('Para pedir')} → ⏳ Lo que se va a acabar")
    except sqlite3.OperationalError as _err:
        anotar_error("diagnostico_de_salud", _err)
        pass

    # La subida automática configurada y FALLANDO. Va antes que «no hay copia» porque dice
    # algo que ese aviso no: que se está intentando, por qué no anda, y que no hay que ir a
    # configurar nada sino arreglar lo que dice GitHub. Antes el fallo de la subida diaria no
    # lo veía nadie.
    try:
        _err_gh = obtener_config("ultimo_backup_github_error", "")
        if _err_gh and config_github():
            sumar("alto", "La copia automática a GitHub está fallando",
                  f"La app intenta subir la copia sola y GitHub la rechaza: {_err_gh}. "
                  "Mientras tanto la copia del repositorio no se actualiza.",
                  miga_hasta("Backup y config"))
    except Exception as _err:
        anotar_error("diagnostico_de_salud/backup_github", _err)

    # El número concreto de lo que se perdería. Un aviso genérico se ignora; «perdés 3.412
    # productos» no.
    try:
        riesgo = cuanto_perderias_si_reinicia()
        if riesgo and not riesgo["hay_semilla"] and riesgo.get("productos_ahora", 0) > 100:
            sumar("alto", "No hay copia en el repositorio",
                  "El servidor borra el disco al reiniciar y se restaura desde "
                  "`datos_iniciales.db`, que no está. Hoy un reinicio borra TODO.",
                  miga_hasta("Backup y config"))
        elif riesgo and riesgo["en_riesgo"] > 200:
            sumar("alto", f"{miles(riesgo['en_riesgo'])} productos viven solo en el disco",
                  f"La copia del repositorio es del {riesgo['fecha_semilla']} y tiene "
                  f"{miles(riesgo['productos_semilla'])}; hoy tenés {miles(riesgo['productos_ahora'])}. "
                  "Si el servidor reinicia, la diferencia se pierde.",
                  miga_hasta("Backup y config"))
    except Exception as _err:
        anotar_error("diagnostico_de_salud", _err)
        pass

    bk = estado_del_backup()
    if bk["urgente"]:
        if not bk["hay_backup"]:
            sumar("alto", "Nunca se bajó un backup",
                  "El servidor borra el disco al reiniciar y restaura desde la última copia. "
                  "Hoy podrías perder todo lo cargado.",
                  miga_hasta("Backup y config"))
        else:
            partes = []
            if bk["productos_nuevos"]:
                partes.append(f"{miles(bk['productos_nuevos'])} productos nuevos")
            if bk["importaciones"]:
                partes.append(f"{bk['importaciones']} lista(s) importadas")
            if bk["dias"]:
                partes.append(f"{bk['dias']} día(s)")
            sumar("alto", "Backup atrasado",
                  "Desde el último hay " + ", ".join(partes) +
                  ". Si el servidor reinicia ahora, eso se pierde.",
                  miga_hasta("Backup y config"))

    orden = {"alto": 0, "medio": 1}
    problemas.sort(key=lambda x: orden.get(x["nivel"], 2))
    return problemas


# ============================================================================================
# POR QUÉ DOS CÓDIGOS NO SE RELACIONAN
# ============================================================================================
def diagnostico_par(codigo_a, codigo_b):
    """Por qué estos dos códigos NO aparecen relacionados. Devuelve una lista de conclusiones.

    Existe porque «no me relaciona los proveedores» puede venir de seis cosas distintas y desde
    afuera se ven todas iguales: que un código no esté cargado, que el vínculo esté esperando
    aprobación, que alguien lo haya rechazado antes, que estén conectados pero más lejos que el
    límite de saltos, o que sencillamente ninguna lista los haya puesto nunca en la misma fila.
    Adivinar cuál de las seis es, mirando la pantalla, no se puede. Esto lo dice."""
    limpio_a, limpio_b = sanitizar(codigo_a), sanitizar(codigo_b)
    pasos = []
    if not limpio_a or not limpio_b:
        return [("error", "Escribí los dos códigos.")]
    if limpio_a == limpio_b:
        return [("ok", "Son el mismo código: ya se encuentran entre sí.")]

    def donde_esta(limpio, crudo):
        c.execute("""SELECT p.id, p.codigo_raw, m.nombre AS marca FROM productos p
                     JOIN marcas m ON m.id = p.marca_id WHERE p.codigo_clean = ?""", (limpio,))
        return [dict(r) for r in c.fetchall()]

    filas_a, filas_b = donde_esta(limpio_a, codigo_a), donde_esta(limpio_b, codigo_b)
    for crudo, filas in ((codigo_a, filas_a), (codigo_b, filas_b)):
        if not filas:
            # ¿Está cargado con otra puntuación? Se busca por parecido del código limpio.
            c.execute("""SELECT p.codigo_raw, m.nombre AS marca FROM productos p
                         JOIN marcas m ON m.id = p.marca_id
                         WHERE p.codigo_clean LIKE ? LIMIT 5""",
                      (f"%{sanitizar(crudo)[:6]}%",))
            parecidos = [f"{r['codigo_raw']} ({r['marca']})" for r in c.fetchall()]
            pasos.append(("error",
                          f"**{crudo}** no está cargado en la base."
                          + (f" Parecidos que sí están: {', '.join(parecidos)}."
                             if parecidos else
                             " No hay ninguno parecido: esa lista no se importó, o el código "
                             "viene escrito distinto en el Excel.")))
    if not filas_a or not filas_b:
        return pasos

    pasos.append(("info", f"**{codigo_a}** está en: " +
                  ", ".join(sorted({f["marca"] for f in filas_a})) +
                  f". **{codigo_b}** está en: " +
                  ", ".join(sorted({f["marca"] for f in filas_b})) + "."))

    ids_a = {f["id"] for f in filas_a}
    ids_b = {f["id"] for f in filas_b}

    # ¿A qué distancia están, sin ningún límite?
    marcadores_a = ",".join("?" * len(ids_a))
    consulta = f"""
    WITH RECURSIVE Red(id, saltos) AS (
        SELECT id, 0 FROM productos WHERE id IN ({marcadores_a})
        UNION
        SELECT CASE WHEN eq.producto_a_id = re.id THEN eq.producto_b_id ELSE eq.producto_a_id END,
               re.saltos + 1
        FROM equivalencias eq JOIN Red re ON (eq.producto_a_id = re.id OR eq.producto_b_id = re.id)
        WHERE re.saltos < 12
        UNION
        SELECT p2.id, re.saltos
        FROM Red re JOIN productos p1 ON p1.id = re.id
                    JOIN productos p2 ON p2.codigo_clean = p1.codigo_clean AND p2.id <> p1.id
        WHERE re.saltos < 12
    )
    SELECT MIN(saltos) AS saltos FROM Red WHERE id IN ({",".join("?" * len(ids_b))})"""
    try:
        c.execute(consulta, list(ids_a) + list(ids_b))
        fila = c.fetchone()
        distancia = fila["saltos"] if fila else None
    except sqlite3.OperationalError as _err:
        anotar_error("diagnostico_par", _err)
        distancia = None

    if distancia is not None:
        pasos.append(("ok", f"**Sí están relacionados**, a {distancia} salto(s) de distancia."))
        if distancia > 3:
            pasos.append(("aviso",
                          f"Pero el buscador viene con el límite en **3 saltos**, y estos están "
                          f"a {distancia}. Por eso no aparecen: hay que poner **Toda la cadena** "
                          "en «Qué tan lejos buscar»."))
        return pasos

    # No están relacionados. ¿Por qué?
    try:
        c.execute("""SELECT COUNT(*) AS n FROM equivalencias_pendientes
                     WHERE (producto_a_id IN ({}) AND producto_b_id IN ({}))
                        OR (producto_b_id IN ({}) AND producto_a_id IN ({}))""".format(
                  marcadores_a, ",".join("?" * len(ids_b)),
                  marcadores_a, ",".join("?" * len(ids_b))),
                  list(ids_a) + list(ids_b) + list(ids_a) + list(ids_b))
        esperando = c.fetchone()["n"]
    except sqlite3.OperationalError as _err:
        anotar_error("diagnostico_par", _err)
        esperando = 0
    if esperando:
        pasos.append(("aviso",
                      "El vínculo **existe pero está esperando aprobación**. Andá a "
                      f"{miga_hasta('Equivalencias sugeridas')} y aprobalo."))
        return pasos

    rechazados = pares_rechazados()
    if any((a, b) in rechazados or (b, a) in rechazados for a in ids_a for b in ids_b):
        pasos.append(("aviso",
                      "Este par fue **rechazado** en una revisión anterior, así que la app no lo "
                      "vuelve a proponer. Si en realidad sí equivalen, vinculalos a mano acá "
                      "abajo."))
        return pasos

    pasos.append(("error",
                  "**Ninguna lista los puso nunca en la misma fila**, y no comparten ningún "
                  "código de fábrica. La app no tiene de dónde deducir que son lo mismo: sin un "
                  "dato en común, no hay nada que relacionar. Si vos sabés que equivalen, "
                  "vinculalos a mano acá abajo y la cadena hace el resto."))
    return pasos


def camino_entre(origen_id, destino_id, tope_nodos=3000):
    """Por qué cadena de vínculos este resultado llegó hasta acá. Devuelve la lista de pasos.

    Es lo que faltaba para que todo lo demás sirva. El buscador ya avisaba «el camino es débil»,
    pero no decía DÓNDE: había que salir a buscar el eslabón malo a mano. Ahora muestra la
    cadena completa, con el puntaje y la lista de origen de cada paso, así se ve de una cuál
    cortar.

    Se busca el camino MÁS CONFIABLE, no el más corto: si hay dos maneras de llegar, la que
    pasa por vínculos sólidos es la que hay que mostrar — es la que decide si el resultado
    sirve o no."""
    if origen_id == destino_id:
        return []
    import heapq
    # Dijkstra maximizando el peor eslabón: el costo de un camino es su vínculo más flojo
    mejor = {origen_id: 100}
    previo = {}
    monton = [(-100, origen_id)]
    visitados = set()
    while monton and len(visitados) < tope_nodos:
        peor_neg, nodo = heapq.heappop(monton)
        if nodo in visitados:
            continue
        visitados.add(nodo)
        if nodo == destino_id:
            break
        c.execute("""SELECT CASE WHEN producto_a_id = ? THEN producto_b_id ELSE producto_a_id END
                            AS otro, COALESCE(confianza, 50) AS conf, lote
                     FROM equivalencias
                     WHERE producto_a_id = ? OR producto_b_id = ?""", (nodo, nodo, nodo))
        for fila in c.fetchall():
            otro, conf = fila["otro"], fila["conf"]
            if otro in visitados:
                continue
            nuevo_peor = min(-peor_neg, conf)
            if nuevo_peor > mejor.get(otro, -1):
                mejor[otro] = nuevo_peor
                previo[otro] = (nodo, conf, fila["lote"])
                heapq.heappush(monton, (-nuevo_peor, otro))

    if destino_id not in previo and destino_id != origen_id:
        return []

    # Se reconstruye el camino desde el final
    pasos = []
    actual = destino_id
    while actual != origen_id:
        anterior, conf, lote = previo[actual]
        pasos.append((anterior, actual, conf, lote))
        actual = anterior
    pasos.reverse()

    ids = {x for paso in pasos for x in paso[:2]}
    marcadores = ",".join("?" * len(ids))
    c.execute(f"""SELECT p.id, p.codigo_raw, p.descripcion, m.nombre AS marca
                  FROM productos p JOIN marcas m ON m.id = p.marca_id
                  WHERE p.id IN ({marcadores})""", list(ids))
    info = {r["id"]: r for r in c.fetchall()}

    salida = []
    for a, b, conf, lote in pasos:
        if a not in info or b not in info:
            continue
        salida.append({
            "Paso": f"{info[a]['codigo_raw']} ({info[a]['marca']}) → "
                     f"{info[b]['codigo_raw']} ({info[b]['marca']})",
            "Confianza": conf,
            "Vino de": (lote or "—").split(" · ")[0],
            "_a": a, "_b": b,
        })
    return salida


def _red_de(producto_id, tope=2000):
    """Trae la red completa de equivalencias conectada a un producto: nodos y aristas."""
    c.execute("""WITH RECURSIVE Red(id) AS (
                     SELECT ?
                     UNION
                     SELECT CASE WHEN e.producto_a_id = r.id THEN e.producto_b_id
                                 ELSE e.producto_a_id END
                     FROM equivalencias e JOIN Red r
                       ON (e.producto_a_id = r.id OR e.producto_b_id = r.id)
                 )
                 SELECT id FROM Red LIMIT ?""", (producto_id, tope))
    nodos = [r["id"] for r in c.fetchall()]
    if len(nodos) < 3:
        return nodos, []
    marcadores = ",".join("?" * len(nodos))
    c.execute(f"""SELECT producto_a_id AS a, producto_b_id AS b, COALESCE(confianza, 50) AS conf
                  FROM equivalencias
                  WHERE producto_a_id IN ({marcadores}) AND producto_b_id IN ({marcadores})""",
              nodos * 2)
    aristas = [(r["a"], r["b"], r["conf"]) for r in c.fetchall()]
    return nodos, aristas


def _vinculos_que_parten_la_red(nodos, aristas):
    """Encuentra los vínculos que, si se cortan, parten la red en dos.

    Es el caso que ni los códigos puente ni el puntaje individual detectan: dos familias de
    repuestos perfectamente legítimas —los filtros por un lado, los frenos por el otro— unidas
    por UN solo vínculo mal cargado. Ningún código tiene muchos enlaces, así que no aparece como
    puente; y el vínculo malo puede tener un puntaje mediano, así que tampoco salta solo.
    Pero es el único que sostiene la unión: cortándolo, las dos familias se separan.

    Se usa el algoritmo de Tarjan, que los encuentra todos en una sola pasada. Buscarlos
    probando de a uno —cortar y ver si se desconecta— sería inviable en una red grande."""
    vecinos = {n: [] for n in nodos}
    for a, b, conf in aristas:
        if a in vecinos and b in vecinos:
            vecinos[a].append((b, conf))
            vecinos[b].append((a, conf))

    orden, bajo = {}, {}
    contador = [0]
    puentes = []

    for raiz in nodos:
        if raiz in orden:
            continue
        # Recorrido sin recursión: una red grande haría explotar la pila
        pila = [(raiz, None, iter(vecinos[raiz]))]
        orden[raiz] = bajo[raiz] = contador[0]
        contador[0] += 1
        while pila:
            nodo, padre, iterador = pila[-1]
            avanzo = False
            for vecino, conf in iterador:
                if vecino == padre:
                    continue
                if vecino not in orden:
                    orden[vecino] = bajo[vecino] = contador[0]
                    contador[0] += 1
                    pila.append((vecino, nodo, iter(vecinos[vecino])))
                    avanzo = True
                    break
                bajo[nodo] = min(bajo[nodo], orden[vecino])
            if not avanzo:
                pila.pop()
                if pila:
                    arriba = pila[-1][0]
                    bajo[arriba] = min(bajo[arriba], bajo[nodo])
                    if bajo[nodo] > orden[arriba]:
                        conf = next((cf for v, cf in vecinos[nodo] if v == arriba), 50)
                        puentes.append((arriba, nodo, conf))
    return puentes


def _tamano_del_lado(inicio, excluido, vecinos, tope=5000):
    """Cuántos nodos quedan de un lado si se corta un vínculo."""
    visto = {inicio}
    pila = [inicio]
    while pila and len(visto) < tope:
        n = pila.pop()
        for v, _ in vecinos.get(n, []):
            if (n, v) == excluido or (v, n) == excluido or v in visto:
                continue
            visto.add(v)
            pila.append(v)
    return len(visto)


def vinculos_que_unen_familias(producto_id, minimo_lado=3):
    """Los vínculos que están uniendo dos grupos grandes que quizá no tengan relación.

    Solo interesan los que dejan grupos GRANDES de los dos lados: si al cortar queda un producto
    suelto de un lado, eso es normal (una punta de la cadena). Si quedan 20 y 25, ese vínculo
    está sosteniendo la unión de dos familias enteras — y vale la pena mirarlo."""
    nodos, aristas = _red_de(producto_id)
    if len(nodos) < 6:
        return []
    puentes = _vinculos_que_parten_la_red(nodos, aristas)
    if not puentes:
        return []

    vecinos = {n: [] for n in nodos}
    for a, b, conf in aristas:
        if a in vecinos and b in vecinos:
            vecinos[a].append((b, conf))
            vecinos[b].append((a, conf))

    salida = []
    for a, b, conf in puentes:
        lado_a = _tamano_del_lado(a, (a, b), vecinos)
        lado_b = len(nodos) - lado_a
        if min(lado_a, lado_b) < minimo_lado:
            continue
        c.execute("""SELECT p.id, p.codigo_raw, p.descripcion, m.nombre AS marca
                     FROM productos p JOIN marcas m ON m.id = p.marca_id WHERE p.id IN (?, ?)""",
                  (a, b))
        info = {r["id"]: r for r in c.fetchall()}
        if a not in info or b not in info:
            continue
        salida.append({
            "Código A": info[a]["codigo_raw"], "Marca A": info[a]["marca"],
            "Código B": info[b]["codigo_raw"], "Marca B": info[b]["marca"],
            "Separa": f"{lado_a} y {lado_b} productos",
            "Confianza del vínculo": conf,
            "_equilibrio": min(lado_a, lado_b),
            "_a": a, "_b": b,
        })
    # Primero los más equilibrados y de menor confianza: son los más sospechosos
    salida.sort(key=lambda x: (-x["_equilibrio"], x["Confianza del vínculo"]))
    return salida


def codigos_puente(minimo=15, limite=100):
    """Códigos vinculados a demasiadas cosas. Son los que rompen la búsqueda.

    Como la búsqueda es transitiva, un código mal vinculado no ensucia solo su fila: fusiona
    todas las familias que toca. Un filtro de aceite legítimo puede tener 10 o 15 equivalencias
    entre marcas; si aparece con 200, casi seguro es un código que se cargó mal (una cantidad,
    un número de orden, o una columna corrida) y quedó de puente entre repuestos que no tienen
    nada que ver. Cortar UNO de estos limpia miles de resultados falsos de una.

    Se ordena por MARCAS DISTINTAS y recién después por cantidad de vínculos, por el mismo
    motivo que explica contar_codigos_puente(): un código con 60 vínculos que se quedan todos
    adentro de una marca es, casi siempre, la tabla de referencias cruzadas que el propio
    proveedor publica, y no puentea nada.
    Honestidad sobre la medición: HOY este orden no cambia nada. Sobre la base real el único
    puente de verdad («CHAPA», 2 marcas) también es el que más vínculos tiene —76—, así que
    encabezaba la lista igual. El orden está por el día que aparezca un puente con 20 vínculos
    repartidos en 5 marcas: ese hace mucho más daño que 60 vínculos adentro de una sola, y
    ordenado por vínculos quedaría abajo de treinta motores de arranque inofensivos."""
    c.execute("""SELECT p.id AS "ID", p.codigo_raw AS "Código", p.descripcion AS "Descripción",
                        m.nombre AS "Marca",
                        (SELECT COUNT(*) FROM equivalencias e
                          WHERE e.producto_a_id = p.id OR e.producto_b_id = p.id) AS "Vínculos",
                        (SELECT COUNT(DISTINCT m2.nombre) FROM equivalencias e
                          JOIN productos p2 ON p2.id = CASE WHEN e.producto_a_id = p.id
                                                            THEN e.producto_b_id ELSE e.producto_a_id END
                          JOIN marcas m2 ON m2.id = p2.marca_id
                          WHERE e.producto_a_id = p.id OR e.producto_b_id = p.id) AS "Marcas distintas"
                 FROM productos p JOIN marcas m ON m.id = p.marca_id
                 WHERE "Vínculos" >= ?
                   AND p.id NOT IN (SELECT producto_id FROM puentes_aprobados)
                 ORDER BY "Marcas distintas" DESC, "Vínculos" DESC LIMIT ?""", (minimo, limite))
    return filas_a_listas(c)


def puentes_en_el_resultado(ids_resultado, umbral=15):
    """De los productos que trajo una búsqueda, cuáles son códigos puente sospechosos.

    Hace falta además del control de saltos, y no en lugar de él: un código puente NO está lejos,
    está a un salto de todo. Al vincularse con cientos de cosas crea atajos, así que dos repuestos
    que no tienen nada que ver quedan a dos saltos uno del otro. Limitar la distancia sirve para
    cadenas largas, pero contra un puente no alcanza — hay que verlo y cortarlo."""
    if not ids_resultado:
        return []
    salida = []
    for tanda, marcadores in en_tandas(ids_resultado):
        c.execute(f"""SELECT p.id AS "ID", p.codigo_raw AS "Código", p.descripcion AS "Descripción",
                             (SELECT COUNT(*) FROM equivalencias e
                               WHERE e.producto_a_id = p.id OR e.producto_b_id = p.id) AS "Vínculos"
                      FROM productos p WHERE p.id IN ({marcadores})
                        AND "Vínculos" >= ?
                        AND p.id NOT IN (SELECT producto_id FROM puentes_aprobados)
                      ORDER BY "Vínculos" DESC""",
                  tanda + [umbral])
        salida.extend(filas_a_listas(c))
    salida.sort(key=lambda x: -x["Vínculos"])
    return salida


def tamano_de_la_red(producto_id, tope=500):
    """Cuántos productos quedan encadenados a este. Si da cientos, la red está contaminada."""
    c.execute("""WITH RECURSIVE Red(id) AS (
                     SELECT ?
                     UNION
                     SELECT CASE WHEN eq.producto_a_id = re.id THEN eq.producto_b_id
                                 ELSE eq.producto_a_id END
                     FROM equivalencias eq JOIN Red re
                       ON (eq.producto_a_id = re.id OR eq.producto_b_id = re.id)
                 )
                 SELECT COUNT(*) FROM (SELECT id FROM Red LIMIT ?)""", (producto_id, tope))
    return c.fetchone()[0]


def cortar_vinculos_de(producto_id):
    """Corta TODAS las equivalencias de un código, sin borrar el producto."""
    with db_lock:
        c.execute("DELETE FROM equivalencias WHERE producto_a_id = ? OR producto_b_id = ?",
                  (producto_id, producto_id))
        borrados = c.rowcount
        conn.commit()
    return borrados


def listar_codigos_basura(limite=200):
    """Productos ya cargados cuyo código no es un código.

    Dos casos, los dos de importaciones viejas:

    · Códigos de 1 o 2 caracteres ('1', '12', '07', '1S'). Arrastran equivalencias falsas: todos
      los '1' de todas las listas terminaron vinculados entre sí.

    · Productos cuyo código ES su propia descripción ("FILTRO ACEITE VW"). Salían de que el
      importador, cuando no encontraba una columna de OEM, asumía la columna 1 —que en una lista
      sin OEM suele ser la descripción— y cargaba el texto como si fuera un código de fábrica.
      No coinciden con nada, y encima ocupan el lugar del código OEM real, que es el único puente
      entre las listas de dos proveedores distintos. El importador ya no lo hace; esto es para
      encontrar los que quedaron de antes."""
    # Se incluyen TODOS los de 1 o 2 caracteres, tengan letra o no. Antes solo se limpiaban los
    # puramente numéricos, así que un "1S" quedaba en la base generando cientos de pendientes.
    c.execute("""SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
                 m.nombre AS "Marca",
                 (SELECT COUNT(*) FROM equivalencias e
                   WHERE e.producto_a_id = p.id OR e.producto_b_id = p.id) AS "Vinculos"
                 FROM productos p JOIN marcas m ON m.id = p.marca_id
                 WHERE LENGTH(p.codigo_clean) <= 2
                    OR (p.descripcion IS NOT NULL AND p.descripcion <> ''
                        AND p.codigo_raw = p.descripcion AND LENGTH(p.codigo_clean) > 8)
                 ORDER BY "Vinculos" DESC LIMIT ?""", (limite,))
    return [dict(r) for r in c.fetchall()]


def contar_codigos_basura():
    c.execute("SELECT COUNT(*) FROM productos WHERE LENGTH(codigo_clean) <= 2")
    return c.fetchone()[0]


def borrar_codigos_basura():
    """Borra esos productos. Las equivalencias falsas que colgaban de ellos se van solas por el
    ON DELETE CASCADE — que es justamente el punto de la limpieza.
    No van a la papelera a propósito: restaurarlos sería volver a meter la basura, y la lista de
    lo que se borra se puede bajar en Excel desde la pantalla antes de confirmar."""
    items = listar_codigos_basura(limite=100000)
    if not items:
        return 0
    with db_lock:
        c.executemany("DELETE FROM productos WHERE id = ?", [(i["ID"],) for i in items])
        conn.commit()
    return len(items)


# ============================================================================================
# FUENTES OFICIALES DE AFUERA: INDEC Y BCRA
# ============================================================================================
# Las únicas fuentes de afuera de la app que no son el catálogo de un proveedor. Todas públicas,
# sin clave y sin costo, y la app funciona igual sin ellas:
#   · el IPC del INDEC, por la API de series de tiempo de datos.gob.ar (el Estado argentino),
#     y si no contesta, el mismo dato republicado por argentinadatos;
#   · el dólar: el oficial minorista día por día de argentinadatos, CONTROLADO contra el de
#     referencia del BCRA (api.bcra.gob.ar). Si se separan más de un 15%, se usa el del BCRA.
# Para qué: cuánto atrasada está una lista contra la inflación, cuánto aumentó cada proveedor
# contra la inflación, y el coeficiente de las listas que vienen en dólares.
URL_DOLAR_OFICIAL = "https://api.argentinadatos.com/v1/cotizaciones/dolares/oficial"
URL_DOLAR_BCRA = ("https://api.bcra.gob.ar/estadisticascambiarias/v1.0/Cotizaciones/USD"
                  "?fechadesde={desde}&fechahasta={hasta}")
# El NIVEL del IPC nacional (índice, base dic-2016 = 100), y como respaldo la serie que había:
# esa es la VARIACIÓN mensual, no el índice, y se la dividía como si fuera el índice —1,9%
# contra 2,42% daba una «inflación» de −21,5%, que es lo que quedó guardado en la base real—.
# Ahora se reconoce qué trae cada serie por sus valores (ver _variaciones_del_ipc()).
SERIES_IPC_INDEC = ("148.3_INIVELNAL_DICI_M_26", "145.3_INGNACUAL_DICI_M_38")
URL_IPC_INDEC = ("https://apis.datos.gob.ar/series/api/series"
                 "?ids={serie}&limit=40&sort=desc&format=json")
# Una inflación mensual fuera de esto no es un dato: es una serie leída al revés.
INFLACION_MENSUAL_CREIBLE = (-0.05, 0.30)


def _pedir_json(url, tiempo_maximo=4):
    """Trae un JSON de afuera, o None. Nunca levanta excepción ni tarda más de unos segundos.

    El tope de tiempo es lo importante: esto se llama desde una pantalla, y una API que no
    contesta no puede dejar colgada la app de alguien que entró a buscar un repuesto."""
    try:
        r = requests.get(url, timeout=tiempo_maximo,
                         headers={"User-Agent": "EquivalenciasElChavo/1.0"})
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as _err:      # de red, de JSON, de lo que sea: acá nada puede romper
        anotar_error("_pedir_json", _err)
        return None


# Cada cuánto se vuelve a preguntar, y cuánto se espera después de un fallo. El segundo número
# es el que importa: sin él, con internet caído la app reintentaba en cada dibujo de pantalla y
# se comía cuatro segundos por vez.
HORAS_CONTEXTO_FRESCO = 6
MINUTOS_ANTES_DE_REINTENTAR = 30


def _serie_del_dolar_bcra(dias=100):
    """[(fecha, cotización)] del dólar de referencia del BCRA, o [].

    La respuesta es {"results": [{"fecha": "2026-09-26", "detalle": [{"codigoMoneda": "USD",
    "tipoCotizacion": 1530.5, ...}]}, ...]}. Se lee a la defensiva: lo que no tenga esa forma
    no cuenta."""
    hasta = datetime.now()
    datos = _pedir_json(URL_DOLAR_BCRA.format(
        desde=(hasta - timedelta(days=dias)).strftime("%Y-%m-%d"),
        hasta=hasta.strftime("%Y-%m-%d")), tiempo_maximo=6)
    resultados = datos.get("results") if isinstance(datos, dict) else None
    if isinstance(resultados, dict):        # con un solo día viene sin la lista
        resultados = [resultados]
    serie = []
    for r in resultados or []:
        try:
            for d in r.get("detalle") or []:
                if str(d.get("codigoMoneda", "")).upper() == "USD" and float(d["tipoCotizacion"]) > 0:
                    serie.append((str(r["fecha"])[:10], float(d["tipoCotizacion"])))
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
    return sorted(serie)


def _dolar_oficial():
    """El dólar oficial de hoy y cuánto subió en 30, 60 y 90 días. {} si no se pudo.

    El de argentinadatos es el minorista, que es el que usan las listas en dólares; el del BCRA
    es el de referencia (mayorista), un poco más bajo. Se controla uno con el otro: si se
    separan más de un 15%, alguno está mal leído, y se usa el del BCRA, que es la fuente."""
    datos = _pedir_json(URL_DOLAR_OFICIAL)
    # Vienen como [{"fecha": "2026-09-16", "compra": .., "venta": ..}, ...].
    serie = []
    for x in (datos if isinstance(datos, list) else []):
        try:
            serie.append((str(x["fecha"])[:10], float(x["venta"])))
        except (KeyError, TypeError, ValueError):
            continue
    serie = sorted(s for s in serie if s[1] > 0)
    bcra = _serie_del_dolar_bcra()
    fuente = "argentinadatos (minorista), controlado con el BCRA" if bcra else "argentinadatos"
    if bcra and (not serie or abs(serie[-1][1] / bcra[-1][1] - 1) > 0.15):
        serie, fuente = bcra, "BCRA (referencia)"
    if not serie:
        return {}
    hoy_f, hoy_v = serie[-1]
    salida = {"fecha": hoy_f, "venta": hoy_v, "variacion": {}, "fuente": fuente}
    for dias in (30, 60, 90):
        objetivo = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
        # El último día con cotización ANTERIOR o igual al objetivo: los fines de semana y
        # feriados no cotizan, y buscar la fecha exacta no devolvería nada uno de cada tres días.
        previos = [v for f, v in serie if f <= objetivo and v > 0]
        if previos:
            salida["variacion"][str(dias)] = hoy_v / previos[-1] - 1
    return salida


def _variaciones_del_ipc(valores):
    """{mes: variación mensual} a partir de lo que traiga la serie, o {} si no se le cree.

    La serie puede traer el ÍNDICE (miles: base 100 en 2016) o la VARIACIÓN mensual (como
    fracción, 0,019, o como porcentaje, 1,9). Se reconoce por los valores y no por el nombre de
    la serie: así un cambio de serie del lado del INDEC no vuelve a dar una inflación de −21%.
    Si algún mes queda fuera de INFLACION_MENSUAL_CREIBLE, no se le cree a nada."""
    valores = sorted((f, v) for f, v in valores if v is not None)
    if len(valores) < 2:
        return {}
    if all(v > 50 for _f, v in valores):                     # el índice
        variaciones = {f: v / ant - 1 for (_fa, ant), (f, v) in zip(valores, valores[1:]) if ant}
    elif all(abs(v) < 1 for _f, v in valores):               # variación como fracción
        variaciones = dict(valores)
    elif all(abs(v) < 40 for _f, v in valores):              # variación como porcentaje
        variaciones = {f: v / 100 for f, v in valores}
    else:
        return {}
    bajo, alto = INFLACION_MENSUAL_CREIBLE
    if not variaciones or any(not bajo <= v <= alto for v in variaciones.values()):
        return {}
    return variaciones


def _ipc_de_la_serie(serie):
    """{"mensual": {mes: fracción}, "mes", "variacion", "serie"} de UNA serie del INDEC en la
    API de series de tiempo, o {} si no contesta o no se le cree (ver _variaciones_del_ipc())."""
    datos = _pedir_json(URL_IPC_INDEC.format(serie=serie), tiempo_maximo=6)
    filas = datos.get("data") if isinstance(datos, dict) else None
    valores = []
    for fila in filas if isinstance(filas, list) else []:
        try:
            if fila[1] is not None:
                valores.append((str(fila[0])[:7], float(fila[1])))
        except (IndexError, TypeError, ValueError):
            continue
    mensual = _variaciones_del_ipc(valores)
    if not mensual:
        return {}
    ultimo = max(mensual)
    return {"mensual": mensual, "mes": ultimo, "variacion": mensual[ultimo], "serie": serie}


def _inflacion_mensual_indec():
    """La inflación mes por mes del INDEC: {"mensual": {mes: fracción}, "mes", "variacion"}
    con el último mes publicado. {} si no se pudo o no se le cree.

    OJO con el desfasaje: el INDEC publica el dato de un mes a mediados del siguiente, así que
    esto siempre va una o dos semanas atrás."""
    for serie in SERIES_IPC_INDEC:
        ipc = _ipc_de_la_serie(serie)
        if ipc:
            return ipc
    return _inflacion_de_argentinadatos()


# El respaldo, si la API del Estado no contesta: argentinadatos (la misma que da el dólar)
# republica la inflación mensual del INDEC como [{"fecha": "2026-08-31", "valor": 1.9}, ...],
# en porcentaje. No es el INDEC, así que va último y se dice de dónde vino. Se toman solo los
# últimos meses: la serie empieza en los años cuarenta y trae la hiperinflación del 89, que con
# razón no pasa el control de _variaciones_del_ipc().
URL_INFLACION_ARGENTINADATOS = "https://api.argentinadatos.com/v1/finanzas/indices/inflacion"


def _inflacion_de_argentinadatos():
    datos = _pedir_json(URL_INFLACION_ARGENTINADATOS, tiempo_maximo=6)
    valores = []
    for x in (datos if isinstance(datos, list) else []):
        try:
            if re.fullmatch(r"\d{4}-\d{2}", str(x["fecha"])[:7]):
                valores.append((str(x["fecha"])[:7], float(x["valor"])))
        except (KeyError, TypeError, ValueError):
            continue
    # Los últimos tres años, por fecha y no por cantidad: una serie corta no tiene que
    # arrastrar el 89.
    desde = f"{int(max(valores)[0][:4]) - 3}{max(valores)[0][4:]}" if valores else ""
    mensual = _variaciones_del_ipc([(m, v) for m, v in valores if m > desde])
    if not mensual:
        return {}
    ultimo = max(mensual)
    return {"mensual": mensual, "mes": ultimo, "variacion": mensual[ultimo],
            "serie": "argentinadatos (republica el INDEC)"}


# EL IPC DE TRANSPORTE. El INDEC publica el IPC por división, y una es «Transporte»: el
# combustible, la compra de autos y —lo que importa acá— el mantenimiento y los repuestos. Para
# comparar cuánto aumentó un proveedor de repuestos es mejor vara que el nivel general, que
# mezcla alimentos y alquileres.
#
# Desde donde se programó esto la API no contestaba, y el código de una serie no se inventa: en
# vez de escribirlo a mano, se lo pide al BUSCADOR de la misma API (/search, documentado en
# github.com/datosgobar/series-tiempo-ar-api), y se elige por lo que dice la serie de sí misma:
# del INDEC, mensual, nacional, de transporte, y que no sea la variación INTERANUAL (un 40%
# interanual leído como mensual sería un desastre) ni la incidencia. Se prefiere el índice.
URL_BUSCAR_SERIES = "https://apis.datos.gob.ar/series/api/search/?q={q}&limit=50"
_BUSQUEDA_IPC_TRANSPORTE = "precios al consumidor transporte nacional"
_REGIONES_DEL_IPC = {"GBA", "PAMPEANA", "NORESTE", "NOROESTE", "CUYO", "PATAGONIA", "REGION"}
DIAS_ENTRE_ACTUALIZACIONES_DEL_TRANSPORTE = 7


def _es_el_ipc_de_transporte(resultado):
    """Si un resultado del buscador es la serie mensual nacional del IPC de transporte."""
    campo = (resultado or {}).get("field") or {}
    dataset = (resultado or {}).get("dataset") or {}
    texto = normalizar_texto(" ".join(str(x or "") for x in (
        campo.get("description"), campo.get("title"), campo.get("units"), dataset.get("title"))))
    palabras = set(re.findall(r"[A-Z0-9]+", texto.replace("_", " ")))
    fuente = normalizar_texto(str(dataset.get("source") or ""))
    return bool(
        campo.get("id")
        and "TRANSPORTE" in palabras
        and ("NACIONAL" in palabras or "NAC" in palabras)
        and ("CONSUMIDOR" in palabras or "IPC" in palabras)
        and not palabras & _REGIONES_DEL_IPC
        and not palabras & {"INTERANUAL", "INCIDENCIA", "PONDERACION", "PONDERADOR"}
        and str(campo.get("frequency") or "R/P1M") == "R/P1M"
        and (not fuente or "INDEC" in fuente or "ESTADISTICA Y CENSOS" in fuente))


def serie_del_ipc_de_transporte():
    """El código de la serie según el buscador oficial, o None. El índice primero; entre
    iguales, la que llega más lejos."""
    datos = _pedir_json(URL_BUSCAR_SERIES.format(q=quote(_BUSQUEDA_IPC_TRANSPORTE)),
                        tiempo_maximo=8)
    resultados = datos.get("data") if isinstance(datos, dict) else None
    candidatas = [r for r in (resultados if isinstance(resultados, list) else [])
                  if _es_el_ipc_de_transporte(r)]
    if not candidatas:
        return None
    candidatas.sort(key=lambda r: (
        "INDICE" in normalizar_texto(str(r["field"].get("units") or "")),
        str(r["field"].get("time_index_end") or "")), reverse=True)
    return str(candidatas[0]["field"]["id"])


def ipc_de_transporte_guardado():
    """Lo último que se trajo del IPC de transporte, SIN salir a internet ({} si nada creíble).
    Con la misma forma que ipc_guardado(): sirve tal cual para inflacion_desde()."""
    try:
        guardado = json.loads(obtener_config("ultimo_ipc_transporte", "") or "{}")
    except (ValueError, TypeError):
        return {}
    if not isinstance(guardado.get("mensual"), dict) or not _variaciones_del_ipc(
            list(guardado["mensual"].items())):
        return {}
    return guardado


def actualizar_ipc_de_transporte(forzar=False):
    """Para la tarea de fondo: busca la serie (la primera vez, o si dejó de contestar) y trae
    sus valores. Devuelve lo guardado, o None si no hacía falta o no se pudo."""
    guardado = ipc_de_transporte_guardado()
    if not forzar and guardado.get("_traido"):
        try:
            hace = datetime.now() - datetime.strptime(guardado["_traido"][:19], "%Y-%m-%d %H:%M:%S")
            if hace < timedelta(days=DIAS_ENTRE_ACTUALIZACIONES_DEL_TRANSPORTE):
                return None
        except ValueError:
            pass
    nuevo = _ipc_de_la_serie(guardado["serie"]) if guardado.get("serie") else {}
    if not nuevo:
        serie = serie_del_ipc_de_transporte()
        nuevo = _ipc_de_la_serie(serie) if serie else {}
    if not nuevo:
        return None
    nuevo["_traido"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    guardar_config("ultimo_ipc_transporte", json.dumps(nuevo))
    return nuevo


def ipc_guardado():
    """Lo último que se trajo del INDEC, SIN salir a internet ({} si nada creíble). Es lo que
    usan los avisos del día, que corren en cada pantalla."""
    try:
        guardado = json.loads(obtener_config("ultimo_ipc", "") or "{}")
    except (ValueError, TypeError):
        return {}
    # Lo guardado antes del arreglo tiene solo el último mes, y puede ser el −21,5%.
    if not isinstance(guardado.get("mensual"), dict) or not _variaciones_del_ipc(
            list(guardado["mensual"].items())):
        return {}
    return guardado


def inflacion_desde(fecha, ipc=None):
    """(inflación acumulada desde esa fecha, hasta qué mes) según el INDEC, o (None, None).

    Cuenta los meses ENTEROS después del de la fecha: lo de adentro del mes de la fecha no se
    sabe cuánto fue, y es mejor quedarse corto que inventar. Va hasta el último mes publicado,
    que está una o dos semanas atrás: es un piso, no el número exacto."""
    ipc = ipc if ipc is not None else ipc_guardado()
    mensual = (ipc or {}).get("mensual") or {}
    if not mensual or not fecha:
        return None, None
    desde = str(fecha)[:7]
    meses = sorted(m for m in mensual if m > desde)
    if not meses:
        return 0.0, max(mensual)
    acumulada = 1.0
    for m in meses:
        acumulada *= 1 + mensual[m]
    return acumulada - 1, meses[-1]


def contexto_de_precios():
    """El dólar oficial y la inflación, juntos y sin poder fallar. {} si no hay nada que decir.

    Es lo único que esta app va a buscar afuera además de los catálogos de los proveedores, y
    no decide nada: lo que dice a qué ritmo aumenta un proveedor sigue siendo TU historial de
    importaciones. Esto contesta las dos cosas que el historial propio no puede — si el
    proveedor viene subiendo por debajo de la inflación (está quedando barato) y cuánto se movió
    el dólar, que es lo que manda en lo importado.

    El guardado va en la tabla de configuración y NO en st.cache_data, por dos razones que se
    probaron:

      · st.cache_data también cachea el FALLO. Si justo cuando se pide no hay internet, el {}
        vacío queda seis horas guardado y la pantalla no dice nada aunque la conexión haya
        vuelto a los dos minutos.
      · El caché de Streamlit se pierde cuando se reinicia el servidor, que en Streamlit Cloud
        pasa seguido. Guardado en la base, lo último que se supo sobrevive.

    Y si hoy no se puede, se muestra lo último que se supo con la fecha de cuándo fue, que es
    más útil que no decir nada. Se marca como viejo para no hacerlo pasar por de hoy."""
    ahora = datetime.now()
    salida = {}
    _guardados = {}
    for clave, config in (("dolar", "ultimo_dolar"), ("ipc", "ultimo_ipc")):
        try:
            crudo = obtener_config(config, "")
            _guardados[clave] = json.loads(crudo) if crudo else None
        except (ValueError, TypeError):
            _guardados[clave] = None

    def esta_fresco(guardado):
        if not guardado or not guardado.get("_traido"):
            return False
        # El IPC guardado antes del arreglo (sin la serie mes por mes) no vale: se trae de nuevo.
        if "variacion" in guardado and "mes" in guardado and "mensual" not in guardado:
            return False
        try:
            visto = datetime.strptime(guardado["_traido"][:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return False
        return (ahora - visto).total_seconds() < HORAS_CONTEXTO_FRESCO * 3600

    # Si todo lo guardado está fresco no se sale a internet, y si hace poco falló tampoco:
    # reintentar en cada dibujo de pantalla cuesta cuatro segundos por vez.
    frescos = all(esta_fresco(_guardados[k]) for k in ("dolar", "ipc"))
    espera = obtener_config("contexto_reintentar_despues", "")
    en_penitencia = bool(espera) and espera > ahora.strftime("%Y-%m-%d %H:%M:%S")

    if not frescos and not en_penitencia:
        fallo = False
        for clave, config, traer in (("dolar", "ultimo_dolar", _dolar_oficial),
                                     ("ipc", "ultimo_ipc", _inflacion_mensual_indec)):
            if esta_fresco(_guardados[clave]):
                continue
            try:
                nuevo = traer()
            except Exception as _err:          # nada de acá puede romper una pantalla
                anotar_error("contexto_de_precios", _err)
                nuevo = {}
            if nuevo:
                nuevo["_traido"] = ahora.strftime("%Y-%m-%d %H:%M:%S")
                _guardados[clave] = nuevo
                guardar_config(config, json.dumps(nuevo))
            else:
                fallo = True
        if fallo:
            guardar_config("contexto_reintentar_despues",
                           (ahora + timedelta(minutes=MINUTOS_ANTES_DE_REINTENTAR)
                            ).strftime("%Y-%m-%d %H:%M:%S"))

    for clave in ("dolar", "ipc"):
        if _guardados[clave]:
            salida[clave] = _guardados[clave]
            if not esta_fresco(_guardados[clave]):
                salida.setdefault("viejos", []).append(clave)
    return salida


# LOS CHEQUES DENUNCIADOS Y LA CENTRAL DE DEUDORES DEL BCRA. Dos APIs oficiales, públicas y
# sin clave, para las cuentas corrientes de los talleres: antes de recibir un cheque, si está
# denunciado (robado, extraviado, adulterado); antes de fiarle a alguien, cómo está en el
# sistema financiero. Se consultan SOLO cuando alguien aprieta el botón, con el dato que
# escribió: nada sale solo. Formato: documentación oficial del BCRA (Cheques Denunciados v1.0,
# Central de Deudores v1.0). Ver pruebas_de_las_fuentes.py.
URL_BCRA_BANCOS = "https://api.bcra.gob.ar/cheques/v1.0/entidades"
URL_BCRA_CHEQUE = "https://api.bcra.gob.ar/cheques/v1.0/denunciados/{entidad}/{numero}"
URL_BCRA_DEUDAS = "https://api.bcra.gob.ar/CentralDeDeudores/v1.0/Deudas/{cuit}"
# Las otras dos consultas de la misma API (especificación OpenAPI oficial, «Central de Deudores
# v1.0»): los últimos 24 meses, y los cheques rechazados del CUIT —los que libró él—.
URL_BCRA_HISTORIA = "https://api.bcra.gob.ar/CentralDeDeudores/v1.0/Deudas/Historicas/{cuit}"
URL_BCRA_RECHAZADOS = ("https://api.bcra.gob.ar/CentralDeDeudores/v1.0/Deudas/"
                       "ChequesRechazados/{cuit}")
# Lo que el banco marca sobre una deuda además de la situación. El orden es el de la gravedad:
# el concurso o la quiebra primero.
OBSERVACIONES_DEL_BCRA = (("situacionJuridica", "concurso o quiebra"), ("procesoJud", "en juicio"),
                          ("irrecDisposicionTecnica", "irrecuperable por disposición técnica"),
                          ("refinanciaciones", "refinanciada"),
                          ("recategorizacionOblig", "recategorizada por el banco"),
                          ("enRevision", "en revisión"))
SITUACIONES_DEL_BCRA = {1: "normal", 2: "riesgo bajo / con seguimiento especial",
                        3: "riesgo medio / con problemas", 4: "riesgo alto / alto riesgo de "
                        "insolvencia", 5: "irrecuperable", 6: "irrecuperable por disposición técnica"}


def _pedir_al_bcra(url, tiempo_maximo=8):
    """(estado HTTP, JSON o None). Como _pedir_json(), pero dice el estado: en estas dos APIs un
    404 no es una falla, es la respuesta («no figura»)."""
    try:
        r = requests.get(url, timeout=tiempo_maximo,
                         headers={"User-Agent": "EquivalenciasElChavo/1.0"})
        try:
            cuerpo = r.json()
        except ValueError:
            cuerpo = None
        return r.status_code, cuerpo
    except Exception as _err:
        anotar_error("_pedir_al_bcra", _err)
        return None, None


def cuit_valido(cuit):
    """El CUIT/CUIL de 11 cifras, limpio, si su dígito verificador da; si no, None."""
    limpio = re.sub(r"\D", "", str(cuit or ""))
    if len(limpio) != 11:
        return None
    pesos = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    resto = 11 - sum(int(d) * p for d, p in zip(limpio, pesos)) % 11
    verificador = 0 if resto == 11 else 9 if resto == 10 else resto
    return limpio if verificador == int(limpio[10]) else None


def bancos_del_bcra():
    """[(código, nombre)] de las entidades que emiten cheques, según el BCRA. Se recuerda 30
    días en la configuración; [] si nunca se pudo traer."""
    try:
        guardado = json.loads(obtener_config("bancos_del_bcra", "") or "{}")
    except (ValueError, TypeError):
        guardado = {}
    fresco = False
    try:
        fresco = (datetime.now() - datetime.strptime(guardado.get("traido", "")[:19],
                                                     "%Y-%m-%d %H:%M:%S")) < timedelta(days=30)
    except ValueError:
        pass
    if not fresco:
        estado, cuerpo = _pedir_al_bcra(URL_BCRA_BANCOS)
        bancos = []
        for b in ((cuerpo or {}).get("results") or []) if estado == 200 else []:
            try:
                bancos.append((int(b["codigoEntidad"]), str(b["denominacion"]).strip()))
            except (KeyError, TypeError, ValueError):
                continue
        if bancos:
            guardado = {"bancos": sorted(bancos, key=lambda x: x[1]),
                        "traido": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            guardar_config("bancos_del_bcra", json.dumps(guardado))
    return [tuple(b) for b in guardado.get("bancos") or []]


def consultar_cheque(codigo_entidad, numero):
    """¿Está denunciado ese cheque? ({"denunciado", "banco", "fecha", "detalles"}, error).

    detalles: [(sucursal, cuenta, causal)]. Si el BCRA contesta que no lo tiene, denunciado es
    False: no prueba que el cheque tenga fondos, solo que nadie lo denunció."""
    try:
        entidad, numero = int(codigo_entidad), int(re.sub(r"\D", "", str(numero)))
    except (TypeError, ValueError):
        return None, "Falta el banco o el número del cheque."
    estado, cuerpo = _pedir_al_bcra(URL_BCRA_CHEQUE.format(entidad=entidad, numero=numero))
    if estado == 404:
        return {"denunciado": False, "banco": "", "fecha": "", "detalles": []}, None
    if estado != 200 or not isinstance(cuerpo, dict):
        return None, ("No se pudo consultar al BCRA" + (f" (respondió {estado})" if estado
                                                        else "") + ". Probá en un rato.")
    r = cuerpo.get("results") or {}
    detalles = []
    for d in r.get("detalles") or []:
        if isinstance(d, dict):
            detalles.append((d.get("sucursal"), d.get("numeroCuenta"), d.get("causal") or ""))
    return {"denunciado": bool(r.get("denunciado")), "banco": r.get("denominacionEntidad") or "",
            "fecha": r.get("fechaProcesamiento") or "", "detalles": detalles}, None


def _periodo_legible(periodo):
    """«202608» o «2026-08» → «2026-08». La especificación dice solo que es texto, y los
    ejemplos que circulan traen las dos formas: se muestra igual venga como venga."""
    cifras = re.sub(r"\D", "", str(periodo or ""))
    return f"{cifras[:4]}-{cifras[4:6]}" if len(cifras) >= 6 else str(periodo or "")


def _consulta_de_deudores(url, cuit):
    """(resultado, error) de una consulta de la Central de Deudores por CUIT. 404 es «no figura»
    y devuelve ({}, None): no es una falla."""
    limpio = cuit_valido(cuit)
    if not limpio:
        return None, "El CUIT no es válido (revisá las 11 cifras: el último dígito no da)."
    estado, cuerpo = _pedir_al_bcra(url.format(cuit=limpio))
    if estado == 404:
        return {}, None
    if estado != 200 or not isinstance(cuerpo, dict):
        return None, ("No se pudo consultar al BCRA" + (f" (respondió {estado})" if estado
                                                        else "") + ". Probá en un rato.")
    return (cuerpo.get("results") if isinstance(cuerpo.get("results"), dict) else {}), None


def situacion_en_el_bcra(cuit):
    """Cómo está ese CUIT en el sistema financiero, según la Central de Deudores del BCRA:
    ({"nombre", "periodo", "peor", "deudas": [(entidad, situación, monto en miles, días de
    atraso, observaciones)]}, error). Sin deudas informadas, deudas es [] y peor es 0.

    Las observaciones son lo que el banco marca además de la situación (ver
    OBSERVACIONES_DEL_BCRA): un concurso preventivo puede convivir con una situación 1 en una
    tarjeta, y es lo primero que hay que saber antes de fiarle."""
    r, error = _consulta_de_deudores(URL_BCRA_DEUDAS, cuit)
    if r is None:
        return None, error
    periodos = sorted((p for p in r.get("periodos") or [] if isinstance(p, dict)),
                      key=lambda p: _periodo_legible(p.get("periodo")))
    ultimo = periodos[-1] if periodos else {}
    deudas = []
    for e in ultimo.get("entidades") or []:
        try:
            deudas.append((str(e.get("entidad") or "").strip(), int(e.get("situacion") or 0),
                           float(e.get("monto") or 0), int(e.get("diasAtrasoPago") or 0),
                           ", ".join(texto for campo, texto in OBSERVACIONES_DEL_BCRA
                                     if e.get(campo) is True)))
        except (AttributeError, TypeError, ValueError):
            continue
    return {"nombre": str(r.get("denominacion") or "").strip(),
            "periodo": _periodo_legible(ultimo.get("periodo")),
            "peor": max((d[1] for d in deudas), default=0), "deudas": deudas}, None


def historia_en_el_bcra(cuit):
    """Los últimos 24 meses del CUIT en la Central de Deudores: ({"meses": [(período, peor
    situación, deuda total en miles)] del más viejo al más nuevo, "tendencia": «empeoró»,
    «mejoró», «igual» o ""}, error).

    La tendencia compara la peor situación del último período con la peor de los seis
    anteriores: un 3 hace un año que ya volvió a 1 no es lo mismo que un 1 que pasó a 3."""
    r, error = _consulta_de_deudores(URL_BCRA_HISTORIA, cuit)
    if r is None:
        return None, error
    meses = {}
    for p in r.get("periodos") or []:
        if not isinstance(p, dict) or not p.get("periodo"):
            continue
        peor, total = 0, 0.0
        for e in p.get("entidades") or []:
            try:
                peor = max(peor, int(e.get("situacion") or 0))
                total += float(e.get("monto") or 0)
            except (AttributeError, TypeError, ValueError):
                continue
        meses[_periodo_legible(p["periodo"])] = (peor, total)
    lista = [(m, peor, total) for m, (peor, total) in sorted(meses.items())]
    tendencia = ""
    if len(lista) >= 2:
        antes = max(peor for _m, peor, _t in lista[-7:-1])
        ahora = lista[-1][1]
        tendencia = "empeoró" if ahora > antes else "mejoró" if ahora < antes else "igual"
    return {"meses": lista, "tendencia": tendencia}, None


def cheques_rechazados_en_el_bcra(cuit):
    """Los cheques que libró ese CUIT y le rechazaron, según la Central de Deudores: ({"cheques":
    [(fecha de rechazo, causal, número, monto, pagado)] del más nuevo al más viejo, "sin_pagar",
    "monto_sin_pagar"}, error). Sin cheques rechazados, la lista va vacía.

    Es la otra cara de «🔎 Verificar un cheque»: aquella dice si UN cheque está denunciado; esta,
    si el taller tiene la costumbre de librar cheques sin fondos."""
    r, error = _consulta_de_deudores(URL_BCRA_RECHAZADOS, cuit)
    if r is None:
        return None, error
    cheques = []
    for causal in r.get("causales") or []:
        if not isinstance(causal, dict):
            continue
        for entidad in causal.get("entidades") or []:
            for d in (entidad or {}).get("detalle") or []:
                try:
                    cheques.append((str(d.get("fechaRechazo") or "")[:10],
                                    str(causal.get("causal") or "").strip().capitalize(),
                                    str(int(float(d.get("nroCheque") or 0))),
                                    float(d.get("monto") or 0), bool(d.get("fechaPago"))))
                except (AttributeError, TypeError, ValueError):
                    continue
    cheques.sort(reverse=True)
    sin_pagar = [ch for ch in cheques if not ch[4]]
    return {"cheques": cheques, "sin_pagar": len(sin_pagar),
            "monto_sin_pagar": sum(ch[3] for ch in sin_pagar)}, None


# Un VIN de muestra que la NHTSA usa en su propia documentación (un Honda Accord 2003): sirve
# para saber si la base responde sin mandarle el de ningún cliente.
VIN_DE_MUESTRA = "1HGCM82633A004352"
CUIT_DE_MUESTRA = "33693450239"


def probar_fuentes_de_afuera():
    """Consulta cada fuente de afuera UNA vez y dice si contesta, cuánto tardó y qué trajo.
    [{"Fuente", "Estado", "Tardó", "Trajo"}]. Para apretar a mano: sale a internet.

    Las lecturas se probaron con respuestas de muestra (pruebas_de_las_fuentes.py), porque desde
    donde se programaron estas APIs no se llegaba. Esto es la prueba en vivo, en el servidor."""
    filas = []

    def medir(nombre, funcion, resumen):
        inicio = time.monotonic()
        try:
            resultado = funcion()
        except Exception as _err:
            anotar_error("probar_fuentes_de_afuera", _err)
            resultado = None
        tardo = f"{miles(time.monotonic() - inicio, 1)} s"
        texto = resumen(resultado) if resultado else ""
        filas.append({"Fuente": nombre, "Estado": "✅ contesta" if texto else "❌ no contesta",
                      "Tardó": tardo, "Trajo": texto or "—"})

    medir("INDEC — inflación (datos.gob.ar)", _inflacion_mensual_indec,
          lambda r: f"{r['mes']}: {miles(r['variacion'] * 100, 1)}% (serie {r['serie']})")
    medir("INDEC — IPC de transporte (buscador de datos.gob.ar)",
          lambda: _ipc_de_la_serie(serie_del_ipc_de_transporte() or ""),
          lambda r: f"{r['mes']}: {miles(r['variacion'] * 100, 1)}% (serie {r['serie']})")
    medir("BCRA — dólar de referencia (api.bcra.gob.ar)", _serie_del_dolar_bcra,
          lambda r: f"{r[-1][0]}: ${miles(r[-1][1], 2)}")
    medir("Dólar oficial minorista (argentinadatos)",
          lambda: _pedir_json(URL_DOLAR_OFICIAL),
          lambda r: (f"{r[-1].get('fecha')}: ${miles(float(r[-1].get('venta')), 2)}"
                     if isinstance(r, list) and r and r[-1].get("venta") else ""))
    for _nombre, (_dataset, _t, _c) in (("transferencias", CONTEOS_DEL_DNRPA["parque"]),
                                         ("0 km", CONTEOS_DEL_DNRPA["0km"])):
        medir(f"DNRPA — {_nombre} (datos.jus.gob.ar)",
              lambda _d=_dataset: archivo_mas_reciente_del_parque(_d),
              lambda r: f"último mes publicado: {r[1]}" if r and r[1] else "")
    medir("BCRA — bancos para verificar cheques (api.bcra.gob.ar)",
          lambda: _pedir_al_bcra(URL_BCRA_BANCOS),
          lambda r: (f"{len((r[1] or {}).get('results') or [])} bancos" if r and r[0] == 200 else ""))
    medir("Inflación de respaldo (argentinadatos)", _inflacion_de_argentinadatos,
          lambda r: f"{r['mes']}: {miles(r['variacion'] * 100, 1)}%")
    # Con el CUIT de un organismo público (la AFIP), nunca el de un cliente: alcanza con saber
    # si contesta. 404 («no figura») también es contestar.
    medir("BCRA — Central de Deudores (api.bcra.gob.ar)",
          lambda: _pedir_al_bcra(URL_BCRA_DEUDAS.format(cuit=CUIT_DE_MUESTRA)),
          lambda r: (f"contesta ({r[0]})" if r and r[0] in (200, 404) else ""))
    medir("Secretaría de Industria — registro de CHAS (datos.produccion.gob.ar)",
          lambda: _pedir_json(URL_PORTAL_PRODUCCION, tiempo_maximo=20),
          lambda r: (f"último archivo: {archivo_mas_reciente_del_chas().rsplit('/', 1)[-1]}"
                     if isinstance(r, dict) and r.get("success") else ""))
    medir("NHTSA — lector de VIN (vpic.nhtsa.dot.gov)",
          lambda: consultar_vin_en_nhtsa(VIN_DE_MUESTRA)[0],
          lambda r: f"{r.get('marca')} {r.get('modelo')} {r.get('anio')}")
    # El auto de muestra es el mismo del VIN de muestra: un Honda Accord 2003.
    medir("NHTSA — campañas y reclamos (api.nhtsa.gov)",
          lambda: fallas_reportadas("HONDA", "ACCORD", 2003)[0],
          lambda r: (f"{len(r['campanias'])} campaña(s), {miles(r['reclamos'])} reclamo(s)"
                     if r.get("campanias") or r.get("reclamos") else ""))
    return filas


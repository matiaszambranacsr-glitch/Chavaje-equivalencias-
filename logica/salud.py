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
        salida.append({
            "Lista": m["nombre"], "Productos con precio": m["con_precio"],
            "Días desde la última carga": dias,
            "Sube por mes": (f"{ritmo * 100:.1f}%" if ritmo is not None else "—"),
            "Estarían atrasados": (f"{atraso * 100:.0f}%" if atraso else "—"),
            "_atraso": atraso or 0, "_dias": dias or 0, "_ritmo": ritmo,
        })
    salida.sort(key=lambda x: (-x["_atraso"], -x["_dias"]))
    return salida


# La única fuente de afuera de toda la app que no es el catálogo de un proveedor. Son dos APIs
# públicas, sin clave y sin costo: argentinadatos publica el dólar oficial del BCRA día por día,
# y datos.gob.ar publica el IPC del INDEC. Se usan para una sola cosa —poner en contexto cuánto
# atrasada está una lista de precios— y la app funciona igual sin ellas.
URL_DOLAR_OFICIAL = "https://api.argentinadatos.com/v1/cotizaciones/dolares/oficial"
URL_IPC_INDEC = ("https://apis.datos.gob.ar/series/api/series"
                 "?ids=145.3_INGNACUAL_DICI_M_38&limit=5&sort=desc&format=json")


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


def _dolar_oficial():
    """El dólar oficial de hoy y cuánto subió en 30, 60 y 90 días. {} si no se pudo."""
    datos = _pedir_json(URL_DOLAR_OFICIAL)
    if not isinstance(datos, list):
        return {}
    # Vienen como [{"fecha": "2026-09-16", "compra": .., "venta": ..}, ...].
    serie = []
    for x in datos:
        try:
            serie.append((str(x["fecha"])[:10], float(x["venta"])))
        except (KeyError, TypeError, ValueError):
            continue
    if not serie:
        return {}
    serie.sort()
    hoy_f, hoy_v = serie[-1]
    if hoy_v <= 0:
        return {}
    salida = {"fecha": hoy_f, "venta": hoy_v, "variacion": {}}
    for dias in (30, 60, 90):
        objetivo = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
        # El último día con cotización ANTERIOR o igual al objetivo: los fines de semana y
        # feriados no cotizan, y buscar la fecha exacta no devolvería nada uno de cada tres días.
        previos = [v for f, v in serie if f <= objetivo and v > 0]
        if previos:
            salida["variacion"][str(dias)] = hoy_v / previos[-1] - 1
    return salida


def _inflacion_mensual_indec():
    """La última variación mensual del IPC del INDEC, como fracción. {} si no se pudo.

    OJO con el desfasaje: el INDEC publica el dato de un mes a mediados del siguiente, así que
    esto siempre va una o dos semanas atrás. Por eso el ritmo con el que se decide algo sigue
    siendo el de historial_precios —tus propias importaciones—, y esto es solo el contexto."""
    datos = _pedir_json(URL_IPC_INDEC)
    filas = datos.get("data") if isinstance(datos, dict) else None
    if not isinstance(filas, list):
        return {}
    valores = []
    for fila in filas:
        try:
            if fila[1] is not None:
                valores.append((str(fila[0])[:10], float(fila[1])))
        except (IndexError, TypeError, ValueError):
            continue
    if len(valores) < 2:
        return {}
    valores.sort()
    v_ant, (f_ult, v_ult) = valores[-2][1], valores[-1]
    if not v_ant:
        return {}
    return {"mes": f_ult, "variacion": v_ult / v_ant - 1}


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

    # Lo primero de todo: clientes esperando algo que ahora hay. Es lo único de esta lista
    # que es plata a un llamado de distancia, y lo que más rápido se pierde: entra la
    # mercadería, nadie se acuerda quién la pidió, y el cliente ya la compró en otro lado.
    try:
        esperando = consultas_que_ahora_hay_en_stock()
        if esperando:
            sumar("alto", f"{len(esperando)} cliente(s) esperando algo que YA hay",
                  "Preguntaron por algo que en ese momento no tenías y ahora está en stock. "
                  "Un llamado y es una venta. Es lo que más rápido se enfría.",
                  "Estadísticas → Reposición → Consultas de clientes")
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
                  f"De {_rev:,} vínculos revisados después de la última importación "
                  f"({obtener_config('dudosos_fecha', 'sin fecha')}). No son sugerencias "
                  "esperando: están activos, y la búsqueda los está devolviendo. Se ven de peor "
                  "a mejor, con el motivo al lado, y se cortan los peores de una.",
                  "Administrar → Mantenimiento → 🧹 Limpiar vínculos")
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
                      "Estadísticas → Importaciones")
            elif _vieja["_ritmo"] is None and _vieja["_dias"] >= 60:
                sumar("medio",
                      f"La lista de {_vieja['Lista']} tiene {_vieja['_dias']} días",
                      "Todavía no la importaste dos veces, así que no puedo medir cuánto "
                      "sube: con la próxima importación la app va a saber a qué ritmo "
                      "aumenta y te va a avisar sola.",
                      "Estadísticas → Importaciones")
    except Exception as _err:
        anotar_error("diagnostico_de_salud/precios viejos", _err)

    try:
        clavos = productos_estancados(365)
        if len(clavos) >= 10:
            plata = sum(x["Plata parada"] or 0 for x in clavos)
            sumar("medio", f"${plata:,.0f} inmovilizados en {len(clavos)} producto(s)",
                  "Hace más de un año que no se venden y siguen ocupando estante. No es "
                  "urgente, pero es plata dormida que conviene mirar antes de la próxima compra.",
                  "Estadísticas → Reposición → Clavos")
    except Exception as _err:
        anotar_error("diagnostico_de_salud/clavos", _err)

    try:
        gratis = equivalencias_puenteadas_por_reemplazo(50)
        if gratis:
            sumar("bajo", f"{len(gratis)} equivalencia(s) esperando, sin trabajo",
                  "Salen de los reemplazos de código que ya cargaste: son productos que el "
                  "cambio de número dejó separados. No hay que investigar nada, solo aprobarlas.",
                  "Administrar → Mantenimiento → Calidad → Reunir lo que separó un cambio de número")
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
                  f"{_total_b:,} código(s) de barras cargados como código de fábrica",
                  f"En {_listas_b} lo que se importó en la columna del código original son "
                  "códigos de barras. Cada uno deja una equivalencia que no lleva a ningún "
                  "lado, y son las que hacen que el buscador prometa un equivalente que no "
                  "existe. El arreglo es un botón: el número pasa a la columna de código de "
                  "barras —se sigue escaneando y buscando igual— y desaparece el producto "
                  "fantasma que lo representaba.",
                  "Administrar → Mantenimiento → 🏷️ Códigos de barras → "
                  "🏷️ Códigos de barras cargados como código de fábrica")
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
                  "Administrar → Mantenimiento → 🧹 Limpiar y corregir → Códigos puente")
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
                  "Administrar → Mantenimiento → ¿Cuánto cruza tu catálogo?")
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
                  f"{_cuantos_e:,} producto(s) de esa(s) lista(s) ya tienen equivalencias "
                  "esperando revisión. Hasta que no se aprueben, buscar uno de sus códigos no "
                  "muestra los equivalentes de los otros proveedores — la lista está bien "
                  "importada, lo que falta es revisarlas.",
                  "Estadísticas → 🔗 Equivalencias sugeridas")
    except Exception as _err:
        anotar_error("diagnostico_de_salud", _err)
        pass

    try:
        espejadas = contar_equivalencias_espejadas()
        if espejadas:
            sumar("medio", f"{espejadas:,} equivalencias anotadas dos veces",
                  "La misma relación guardada en las dos direcciones. No cambia lo que encuentra "
                  "el buscador, pero duplica todos los conteos.",
                  "Administrar → Mantenimiento → Equivalencias anotadas dos veces")
    except Exception as _err:
        anotar_error("diagnostico_de_salud", _err)
        pass

    try:
        basura = contar_codigos_basura()
        if basura:
            sumar("alto", f"{basura} código(s) que son un número suelto",
                  "Entraron cantidades o números de orden en la columna del código. Cada uno "
                  "vincula entre sí repuestos que no tienen nada que ver.",
                  "Administrar → Mantenimiento → Códigos que son solo un número suelto")
    except Exception as _err:
        anotar_error("diagnostico_de_salud", _err)
        pass

    try:
        con_punto = contar_codigos_con_decimal()
        if con_punto:
            sumar("medio", f"{con_punto} código(s) terminados en '.0'",
                  "Excel los guardó como número. Se encuentran igual, pero el código que se "
                  "muestra y se copia en un presupuesto está mal.",
                  "Administrar → Mantenimiento → Códigos que quedaron con '.0'")
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
        c.execute(f"""SELECT COUNT(*) FROM equivalencias e
                     JOIN productos pa ON pa.id = e.producto_a_id
                     JOIN productos pb ON pb.id = e.producto_b_id
                     WHERE {SIN_CONTAR_EL_ESPEJO} AND pa.precio > 0 AND pb.precio > 0
                       AND MAX(pa.precio, pb.precio) / MIN(pa.precio, pb.precio) >= 8""")
        precios = c.fetchone()[0]
        if precios:
            sumar("alto", f"{precios} par(es) de equivalentes con precios muy distintos",
                  "O el precio está mal cargado, o no son la misma pieza. Cualquiera de las dos "
                  "cuesta plata: o cotizás mal, o vendés algo que no entra.",
                  "Administrar → Mantenimiento → Precios que no cierran")
    except Exception as _err:
        anotar_error("diagnostico_de_salud", _err)
        pass

    try:
        c.execute("SELECT COUNT(*) FROM equivalencias_pendientes")
        pendientes = c.fetchone()[0]
        if pendientes > 500:
            sumar("medio", f"{pendientes:,} vínculos esperando revisión",
                  "Mientras no se revisen no están cargados, así que el buscador no los usa.",
                  "Estadísticas → 🔗 Equivalencias sugeridas")
    except Exception as _err:
        anotar_error("diagnostico_de_salud", _err)
        pass

    try:
        c.execute("SELECT COUNT(*) FROM equivalencias WHERE confianza IS NULL")
        sin_punt = c.fetchone()[0]
        if sin_punt > 200:
            sumar("medio", f"{sin_punt:,} vínculos sin puntuar",
                  "El buscador no puede decirte qué tan sólido es el camino de cada resultado "
                  "hasta que se calculen. Es un solo botón.",
                  "Administrar → Mantenimiento → Puntuar los vínculos")
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
                      "Administrar → Mantenimiento → 🔎 Encontrar equivalencias → "
                      "🏭 Catálogo de aplicaciones (qué repuesto le va a cada auto)")
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
                  "Estadísticas → Reposición → Lo que se va a acabar")
        elif quiebres:
            sumar("medio", f"{len(quiebres)} producto(s) se acaban en menos de 2 semanas",
                  "Según el ritmo con que se vienen vendiendo y el stock que queda.",
                  "Estadísticas → Reposición → Lo que se va a acabar")
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
                  "Estadísticas → Backup y config")
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
                  "Estadísticas → Backup y config")
        elif riesgo and riesgo["en_riesgo"] > 200:
            sumar("alto", f"{riesgo['en_riesgo']:,} productos viven solo en el disco",
                  f"La copia del repositorio es del {riesgo['fecha_semilla']} y tiene "
                  f"{riesgo['productos_semilla']:,}; hoy tenés {riesgo['productos_ahora']:,}. "
                  "Si el servidor reinicia, la diferencia se pierde.",
                  "Estadísticas → Backup y config")
    except Exception as _err:
        anotar_error("diagnostico_de_salud", _err)
        pass

    bk = estado_del_backup()
    if bk["urgente"]:
        if not bk["hay_backup"]:
            sumar("alto", "Nunca se bajó un backup",
                  "El servidor borra el disco al reiniciar y restaura desde la última copia. "
                  "Hoy podrías perder todo lo cargado.",
                  "Estadísticas → Backup y config")
        else:
            partes = []
            if bk["productos_nuevos"]:
                partes.append(f"{bk['productos_nuevos']:,} productos nuevos")
            if bk["importaciones"]:
                partes.append(f"{bk['importaciones']} lista(s) importadas")
            if bk["dias"]:
                partes.append(f"{bk['dias']} día(s)")
            sumar("alto", "Backup atrasado",
                  "Desde el último hay " + ", ".join(partes) +
                  ". Si el servidor reinicia ahora, eso se pierde.",
                  "Estadísticas → Backup y config")

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
                      "Estadísticas → 🔗 Equivalencias sugeridas y aprobalo."))
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

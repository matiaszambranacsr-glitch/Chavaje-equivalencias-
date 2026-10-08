"""La evidencia que junta cada par (evidencia_cruzada) y las equivalencias que se deducen
de medidas, descripciones, aplicaciones y reemplazos.

Salió de logica/descripciones.py, que con 5.400 renglones juntaba cinco temas.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================================================
# LA EVIDENCIA DE CADA PAR Y LAS EQUIVALENCIAS QUE SE DEDUCEN
# ============================================================================================
_RE_MUESCAS_EN_EL_CODIGO = re.compile(r"[- ](\d)M$")
_RE_ESPESOR_EN_MM = re.compile(r"(?i)ESP\.?:?\s*\(?\s*\d[.,]\d{1,2}\s*MM")
# Sin \b adelante: FISPA lo pega a lo de antes, «… 2 0NGK= BKR5EY», «3 ELECTRODOSNGK= BKUR5…».
# Con el «=» se busca en cualquier lado; sin él, que NGK sea una palabra.
# «NKG» es como FISPA escribe NGK a veces: «REF ORIG NKG 94951 LZKAR7D-9D».
_RE_NGK_EN_LA_DESCRIPCION = re.compile(
    r"N(?:GK|KG)\s*=\s*([A-Z]{1,6}\d{1,2}[A-Z0-9-]*)"
    r"|(?<![A-Z])N(?:GK|KG)\s*:?\s*(?:\d{4,6}\s+)?([A-Z]{1,6}\d{1,2}[A-Z0-9-]*)")
# Y en las de moto de FISPA el número de NGK es la referencia original, sin decir NGK: «BUJIA
# NAFTA MOTO LSPC6HSA … REF. ORIG: C6HSA». Con forma de bujía —letras, grado, letras: C6HSA,
# B7ES, CR8EH-9—, que un número de fábrica de un auto (7700…) no tiene.
_RE_NGK_COMO_REFERENCIA_ORIGINAL = re.compile(
    r"\bREF\s?\.?\s?ORIG\.?\s*:?\s*([A-Z]{1,5}\d{1,2}[A-Z]{1,4}(?:-\d{1,2}[A-Z]{0,2})?)(?![A-Z0-9])")


def _muescas_de_la_junta(producto):
    """Las muescas que marca el código de una junta de tapa («580107-1M», «TC-242-20 5M»)."""
    if "CIL" not in (producto.get("descripcion") or "").upper():
        return None
    m = _RE_MUESCAS_EN_EL_CODIGO.search((producto.get("codigo_raw") or "").upper().strip())
    return m.group(1) if m else None


def _codigo_ngk(producto):
    """El número de NGK de una bujía: el que la descripción declara («NGK= ZFR6F11»), o el
    código de TARANTO, que vende las NGK con su número (la J de adelante es el juego de 4:
    JBPR5ES es la BPR5ES). None si no es una bujía o no lo dice."""
    desc = (producto.get("descripcion") or "").upper()
    if "BUJIA" not in _normalizar_desc(desc):
        return None
    m = _RE_NGK_EN_LA_DESCRIPCION.search(desc) or _RE_NGK_COMO_REFERENCIA_ORIGINAL.search(desc)
    if m:
        return sanitizar(next(g for g in m.groups() if g))
    if (producto.get("marca") or "").upper() == "TARANTO":
        codigo = sanitizar(producto.get("codigo_raw") or "")
        return codigo[1:] if codigo.startswith("J") and len(codigo) > 4 else codigo or None
    return None


class _NadaQueBuscar(Exception):
    """Para saltear una consulta que se sabe vacía sin anidar otro nivel de if."""


def _codigos_con_aplicaciones_de_fabrica():
    """Los códigos que tienen alguna aplicación que NO sea deducida. Ver evidencia_cruzada()."""
    try:
        return {r[0] for r in c.execute("""SELECT DISTINCT codigo_clean FROM aplicaciones
                                           WHERE COALESCE(origen, '') <> 'deducida'""")}
    except sqlite3.OperationalError as _err:
        anotar_error("_codigos_con_aplicaciones_de_fabrica", _err)
        return set()


def _pares_vinculados():
    try:
        return {(min(r[0], r[1]), max(r[0], r[1]))
                for r in c.execute("SELECT producto_a_id, producto_b_id FROM equivalencias")}
    except sqlite3.OperationalError as _err:
        anotar_error("_pares_vinculados", _err)
        return set()


def _codigos_con_reemplazo():
    try:
        return {r[0] for r in c.execute("SELECT codigo_viejo_clean FROM reemplazos_codigo")}
    except sqlite3.OperationalError as _err:
        anotar_error("_codigos_con_reemplazo", _err)
        return set()


def _pares_de_portales():
    salida = {}
    try:
        for r in c.execute("""SELECT producto_a_id, producto_b_id, portal
                              FROM productos_juntos_en_portal"""):
            salida.setdefault((r[0], r[1]), [])
            if r[2] not in salida[(r[0], r[1])]:
                salida[(r[0], r[1])].append(r[2])
    except sqlite3.OperationalError as _err:
        anotar_error("_pares_de_portales", _err)
    return salida


def precargar_para_evidencia(ids, medidas=None):
    """Trae de una vez los productos (y sus medidas) que evidencia_cruzada() va a pedir de a
    dos. Solo sirve dentro de recordando_lo_de_cada_producto(). Sobre la lista de FISPA eran
    27.000 consultas de a dos productos; ahora son unas pocas de a mil."""
    memoria = getattr(_MEMORIA_DEL_ANALISIS, "datos", None)
    if memoria is None or not ids:
        return
    for tanda, marcas in en_tandas(list(ids)):
        c.execute(f"""SELECT p.id, p.codigo_raw, p.codigo_clean, p.descripcion, p.precio,
                             p.marca_id, m.nombre AS marca, m.tipo AS tipo, {COLUMNAS_MEDIDAS}
                      FROM productos p JOIN marcas m ON m.id = p.marca_id
                      WHERE p.id IN ({marcas})""", tanda)
        for r in c.fetchall():
            memoria[("producto_ev", r["id"])] = dict(r)
    if medidas is not None:
        for i in ids:
            memoria[("medidas_ev", i)] = medidas.get(i)

    # Los autos que la base sabe de cada producto (ver _autos_guardados_en_la_base()): eran dos
    # consultas por producto —15.700 llamadas en la lista de FISPA—. Se traen por tandas con los
    # mismos topes (200 por código, 100 por producto).
    productos = [memoria[("producto_ev", i)] for i in ids if ("producto_ev", i) in memoria]
    por_codigo, por_producto = {}, {}
    codigos = list({p["codigo_clean"] for p in productos if p.get("codigo_clean")})
    try:
        for tanda, marcas in en_tandas(codigos):
            for r in c.execute(f"""SELECT DISTINCT codigo_clean, marca_auto, modelo_auto
                                   FROM aplicaciones WHERE codigo_clean IN ({marcas})""", tanda):
                filas = por_codigo.setdefault(r["codigo_clean"], [])
                if len(filas) < 200:
                    filas.append((r["marca_auto"], r["modelo_auto"]))
        for tanda, marcas in en_tandas(list(ids)):
            for r in c.execute(f"""SELECT DISTINCT hp.producto_id, v.marca_auto, v.modelo_auto
                                   FROM historial_piezas hp JOIN vehiculos v
                                     ON v.id = hp.vehiculo_id
                                   WHERE hp.producto_id IN ({marcas})""", tanda):
                filas = por_producto.setdefault(r["producto_id"], [])
                if len(filas) < 100:
                    filas.append((r["marca_auto"], r["modelo_auto"]))
    except sqlite3.OperationalError as _err:
        anotar_error("precargar_para_evidencia", _err)
        return
    for p in productos:
        autos = set()
        for campos in por_codigo.get(p.get("codigo_clean"), []) + por_producto.get(p["id"], []):
            for campo in campos:
                autos.update(w for w in normalizar_texto(campo or "").split() if len(w) >= 3)
        memoria[("autos", p["id"], p.get("codigo_clean"))] = frozenset(autos)


def evidencia_cruzada(id_a, id_b, cuenta_palabras=None, total_descripciones=None,
                      rubros_oem=None):
    """Corre TODOS los métodos sobre un mismo par y cuenta cuántos coinciden.

    Es la mejora de precisión más grande que faltaba. Hasta ahora cada método trabajaba solo:
    el de descripciones proponía sus pares, el de medidas los suyos, el de catálogos los suyos,
    y todos caían en la misma cola con el mismo peso. Pero no valen lo mismo.

    Que DOS métodos independientes lleguen al mismo par es muchísimo más fuerte que uno solo:
    que dos descripciones se parezcan puede ser casualidad, que además midan igual y encima
    el fabricante las dé para el mismo auto, no.

    Y al revés, lo que más precisión gana: los VETOS. Si las medidas se contradicen, no importa
    cuántos métodos digan que sí — no es la misma pieza. Antes eso era una alarma más entre
    varias; acá tumba el par.

    rubros_oem es lo de rubros_de_los_codigos_de_fabrica(), para no tomarle al código de
    fábrica el rubro de la fila que lo nombró primero. Quien llama en un bucle lo pasa hecho.

    Devuelve (a_favor, vetos, veredicto)."""
    # Si el análisis los precargó (ver precargar_para_evidencia()), no se consultan de nuevo:
    # eran dos de las ocho consultas que se hacían por par.
    _memoria = getattr(_MEMORIA_DEL_ANALISIS, "datos", None) or {}
    filas = {i: _memoria[("producto_ev", i)] for i in (id_a, id_b)
             if ("producto_ev", i) in _memoria}
    if len(filas) < 2:
        c.execute(f"""SELECT p.id, p.codigo_raw, p.codigo_clean, p.descripcion, p.precio,
                             p.marca_id, m.nombre AS marca, m.tipo AS tipo, {COLUMNAS_MEDIDAS}
                      FROM productos p JOIN marcas m ON m.id = p.marca_id
                      WHERE p.id IN (?, ?)""", (id_a, id_b))
        filas = {r["id"]: dict(r) for r in c.fetchall()}
    if id_a not in filas or id_b not in filas:
        return [], ["uno de los dos productos ya no existe"], "🔴 no se puede evaluar"
    pa, pb = filas[id_a], filas[id_b]

    a_favor, vetos = [], []

    # 0. DOS PRODUCTOS DEL MISMO PROVEEDOR. Un catálogo no lista dos veces la misma pieza
    # para que elijas: si aparecen vinculados y además dicen exactamente lo mismo, es una fila
    # leída dos veces —la celda del código traía dos cosas y una no era un código—. Son 196
    # vínculos en la base real, todos de la misma lista, y salen de pedazos de la descripción
    # que quedaron como código: «PVC», «SPR», «SOPORTE», «CHAPA».
    if pa["marca_id"] == pb["marca_id"]:
        _sin_digitos = [x["codigo_raw"] for x in (pa, pb)
                        if not any(ch.isdigit() for ch in (x["codigo_clean"] or ""))]
        if _sin_digitos:
            vetos.append(f"🏷️ los dos son de {pa['marca']} y «{_sin_digitos[0]}» no tiene ningún "
                          "número: es un pedazo de la descripción que quedó como código")
        elif (pa["descripcion"] or "").strip() == (pb["descripcion"] or "").strip():
            vetos.append(f"🏷️ los dos son de {pa['marca']} y tienen la misma descripción: es "
                          "una fila de la lista leída dos veces, no dos repuestos equivalentes")

    # 1. Medidas. Es el único método que puede VETAR: si las medidas se contradicen, no hay
    # descripción ni catálogo que lo arregle.
    if ("medidas_ev", id_a) in _memoria and ("medidas_ev", id_b) in _memoria:
        medidas = {id_a: _memoria[("medidas_ev", id_a)], id_b: _memoria[("medidas_ev", id_b)]}
    else:
        medidas = cargar_medidas_de_varios([id_a, id_b])
    coinciden, detalle_med = comparar_medidas(medidas.get(id_a), medidas.get(id_b))
    if coinciden is True:
        a_favor.append(f"📐 las medidas coinciden ({detalle_med})")
    elif coinciden is False:
        vetos.append(f"📐 {detalle_med}")

    # Las MUESCAS de la junta de tapa: «471408-4M» (TARANTO) contra «TC-242-20 5M» (ILLINOIS)
    # son dos espesores del mismo motor. Las dos listas usan la marca de fábrica (3M es 1,30 mm
    # en las dos). Solo si alguna no dice el espesor en milímetros: si lo dicen las dos, manda
    # el espesor (ver comparar_medidas()).
    _mu_a, _mu_b = _muescas_de_la_junta(pa), _muescas_de_la_junta(pb)
    if (_mu_a and _mu_b and _mu_a != _mu_b
            and not (_RE_ESPESOR_EN_MM.search(pa.get("descripcion") or "")
                     and _RE_ESPESOR_EN_MM.search(pb.get("descripcion") or ""))):
        vetos.append(f"📐 NO coinciden: muescas de espesor: {_mu_a}M vs {_mu_b}M")
    # La BUJÍA por su número de NGK: «ZFR6F» (TARANTO, que usa el de NGK como código) contra
    # «NGK= BKR5EY» (FISPA) son dos bujías distintas aunque vayan a los mismos autos.
    _ngk_a, _ngk_b = _codigo_ngk(pa), _codigo_ngk(pb)
    _mismo_ngk = bool(_ngk_a and _ngk_b
                      and (_ngk_a.startswith(_ngk_b) or _ngk_b.startswith(_ngk_a)))
    if _ngk_a and _ngk_b and not _mismo_ngk:
        vetos.append(f"🔤 bujías distintas: NGK {_ngk_a} vs NGK {_ngk_b}")
    elif _mismo_ngk:
        # El mismo número de NGK es la misma bujía, y cada lista anota los autos que quiere:
        # «ZFR6F» (TARANTO, Fiat E.Torq) contra «NGK= ZFR6F11» (FISPA, Honda) salía en rojo por
        # «autos distintos». Como con un código en común, lo del auto no la contradice.
        a_favor.append(f"🔢 el mismo número de NGK ({_ngk_a})")
    # El número de uno es el del CONJUNTO donde va el otro: el kit de reparación y la bomba que
    # repara, la tapa de flotante y la bomba que la lleva. Ver numero_del_conjunto_donde_va().
    _del_conjunto = el_numero_de_uno_es_el_conjunto_del_otro(
        pa.get("codigo_raw"), pa.get("descripcion"), pa.get("tipo"),
        pb.get("codigo_raw"), pb.get("descripcion"), pb.get("tipo"))
    if _del_conjunto:
        vetos.append(f"🧰 {_del_conjunto}")

    # 2. Descripción
    fa = firma_de_producto(pa["descripcion"], id_a, pa["codigo_clean"])
    fb = firma_de_producto(pb["descripcion"], id_b, pb["codigo_clean"])
    # Copia, no se toca la firma: es la misma para todos los que la piden. Ver
    # firma_de_producto().
    _rub_a = rubro_del_codigo_frente_a(rubros_oem, id_a, pa["descripcion"], pb["descripcion"])
    _rub_b = rubro_del_codigo_frente_a(rubros_oem, id_b, pb["descripcion"], pa["descripcion"])
    if fa and _rub_a:
        fa = dict(fa, familia=_rub_a)
    if fb and _rub_b:
        fb = dict(fb, familia=_rub_b)
    # El conteo de palabras del catálogo entero se puede pasar hecho, y hay que pasarlo cuando
    # se llama a esto en un bucle. Cada llamada cuesta un COUNT + SUM(LENGTH(...)) sobre toda
    # la tabla para saber si el caché sigue vigente, más deserializar el diccionario de 100.000
    # palabras. Son 34 ms; parece nada hasta que se revisan 400 vínculos de una importación:
    # la pantalla de «Equivalencias sugeridas» tardaba 37 segundos y 13 eran esto.
    if cuenta_palabras is None or total_descripciones is None:
        cuenta_palabras, total_descripciones = cuantas_veces_aparece_cada_palabra()
    _cuenta, _total = cuenta_palabras, total_descripciones
    ok_desc, motivo_desc = firmas_compatibles(fa, fb, cuenta_palabras=_cuenta,
                                              total_descripciones=_total)
    # EL KIT DEL LADO DEL NÚMERO DE FÁBRICA NO CUENTA. El producto de fábrica se crea copiando la
    # descripción de la fila que trajo el número, y si esa fila era el kit de reparación que
    # CITA el número del aforador, el nodo «parece» un kit: «1J0919051B» con la descripción del
    # KIT20000A contra el aforador 23127, que es justamente la pieza de ese número. Al revés sí
    # vale: el número del filtro (el nodo describe el filtro) contra la bomba con kit.
    if motivo_desc.startswith("juegos distintos: un kit vs la pieza suelta"):
        for _p, _f in ((pa, fa), (pb, fb)):
            if (_p.get("tipo") or "").upper() == "OEM" and (_f or {}).get("kit"):
                motivo_desc = "el número de fábrica lo trajo un kit que lo cita"
    aviso_desc = ""
    # Antes del rubro: ¿uno viene adentro del otro? Es cierto que los rubros no coinciden —una
    # bujía no es un juego de cables— y aun así «rubros distintos» no describe lo que pasa. Ver
    # _uno_trae_al_otro(): sobre los 208 vínculos con rubros distintos que hay cargados, 126
    # son de esta clase.
    _kit_de = _uno_trae_al_otro(pa.get("descripcion"), pa.get("codigo_raw"),
                                 pb.get("descripcion"), pb.get("codigo_raw"),
                                 pa.get("tipo"), pb.get("tipo"))
    # El número de uno escrito en la descripción del otro, sin que ninguno sea el nodo de un
    # código de fábrica: la lista lo cita como su equivalente («… // T36042», «REF ORIG T7148»).
    # El kit que nombra entre paréntesis lo que trae no llega acá como prueba: ver
    # _uno_trae_al_otro(), que lo separa antes.
    if ("OEM" not in {(pa.get("tipo") or "").upper(), (pb.get("tipo") or "").upper()}
            and _unidos_por_codigo(pa, pb) and not _kit_de):
        a_favor.append("🔢 el código de uno está escrito en la descripción del otro")
    if ok_desc:
        a_favor.append(f"🔤 las descripciones concuerdan ({motivo_desc})")
        # El espesor solo no prueba que sea la misma pieza (ver el final de
        # comparar_medidas()), pero cuando las descripciones ya dicen que es la misma junta del
        # mismo auto, que además midan igual confirma que es la MISMA VARIANTE: de las tres
        # juntas de un motor, la del mismo espesor. «Jta.Tapa Cil. CHEVROLET CORSA ESP 1,00MM»
        # contra «Junta Tapa de Cilindros CHEVROLET (ESP 1.00MM) CORSA...» es eso.
        # Solo el espesor: la posición y las vías salen del mismo texto que ya se comparó.
        if coinciden is None and detalle_med.startswith("Solo coinciden en espesor:"):
            a_favor.append("📐 el espesor coincide: es la misma variante")
    elif _kit_de:
        vetos.append(f"📦 no son equivalentes: {_kit_de}. El buscador te lo ofrece igual, "
                      "como kit, cuando buscás la pieza suelta")
    elif fa and fb and fa["familia"] != "Sin clasificar" and fb["familia"] != "Sin clasificar":
        # Con el código de uno escrito en la descripción del otro, el rubro no contradice: el
        # número dice cuál es. «Despiece JOHN DEERE TAPA CAJA DE VELOCIDAD // T36042» (ILLINOIS)
        # contra «JTA T-36042 TAPA CAJA CAMBIOS» (IMPERIAL) es la misma junta, y salía en rojo
        # porque una quedaba en «Caja y diferencial» y la otra en «Juntas y retenes». El kit que
        # nombra lo que trae ya se separó arriba (ver _uno_trae_al_otro()).
        _citado = "OEM" not in {(pa.get("tipo") or "").upper(), (pb.get("tipo") or "").upper()} \
            and _unidos_por_codigo(pa, pb)
        if fa["familia"] != fb["familia"] and not _citado:
            vetos.append(f"🧩 rubros distintos: «{fa['familia']}» y «{fb['familia']}»")
        elif (motivo_desc.startswith(_MOTIVOS_QUE_CONTRADICEN)
              and not (motivo_desc.startswith(_MOTIVOS_DEL_AUTO)
                       and (_unidos_por_codigo(pa, pb) or _mismo_ngk))):
            vetos.append(f"🔤 {motivo_desc}")
        elif motivo_desc.startswith(_MOTIVOS_QUE_AVISAN):
            aviso_desc = motivo_desc

    # 3. El catálogo del fabricante: ¿los da para el mismo auto?
    _con_fabrica = _recordado(("codigos_con_aplicaciones_de_fabrica",),
                              _codigos_con_aplicaciones_de_fabrica)
    try:
        if pa["codigo_clean"] not in _con_fabrica or pb["codigo_clean"] not in _con_fabrica:
            raise _NadaQueBuscar()
        # Las deducidas quedan afuera por lo mismo que en analizar_lote_pendiente(): esta vía
        # cuenta como UNA de las tres evidencias que fuerzan el puntaje a 90, y una aplicación
        # deducida de la descripción no es un tercer camino independiente — es el mismo texto
        # que ya miran las señales de descripción, con el cartel de «lo dice el fabricante».
        c.execute("""SELECT COUNT(*) FROM aplicaciones a JOIN aplicaciones b
                       ON a.marca_auto = b.marca_auto AND a.modelo_auto = b.modelo_auto
                     WHERE a.codigo_clean = ? AND b.codigo_clean = ?
                       AND a.marca_repuesto <> b.marca_repuesto
                       AND COALESCE(a.origen, '') <> 'deducida'
                       AND COALESCE(b.origen, '') <> 'deducida'""",
                  (pa["codigo_clean"], pb["codigo_clean"]))
        autos_juntos = c.fetchone()[0]
        if autos_juntos:
            a_favor.append(f"🏭 dos fabricantes los dan para {autos_juntos} auto(s) en común")
    except _NadaQueBuscar:
        pass
    except sqlite3.OperationalError as _err:
        anotar_error("evidencia_cruzada", _err)
        pass

    # 4. El mostrador: ¿ya se vendió uno en lugar del otro?
    veces = _recordado(("ventas_ev",), pares_confirmados_por_ventas).get(
        (min(id_a, id_b), max(id_a, id_b)), 0)
    if veces >= 2:
        a_favor.append(f"🧾 ya lo vendiste como reemplazo {veces} vez(ces)")
    # Y lo que VOLVIÓ porque no le iba: gana sobre todo lo de arriba. Ver registrar_devolucion().
    _devuelto = _recordado(("devueltos_ev",), pares_devueltos).get(
        (min(id_a, id_b), max(id_a, id_b)), 0)
    if _devuelto:
        vetos.append(f"↩️ lo devolvieron {_devuelto} vez(ces) porque no le iba")

    # 5. Un código de fábrica compartido
    if (min(id_a, id_b), max(id_a, id_b)) in _recordado(("vinculados_ev",), _pares_vinculados):
        a_favor.append("🔗 ya están vinculados en la base")

    # 6. Reemplazo de código declarado. Solo se sigue la cadena de los códigos que figuran en
    # la tabla de reemplazos: era una consulta por par aunque la tabla estuviera vacía.
    _con_reemplazo = _recordado(("codigos_con_reemplazo",), _codigos_con_reemplazo)
    for viejo, nuevo in ((pa["codigo_clean"], pb["codigo_clean"]),
                         (pb["codigo_clean"], pa["codigo_clean"])):
        if viejo not in _con_reemplazo:
            continue
        if any(x["clean"] == nuevo for x in cadena_de_reemplazos(viejo)):
            a_favor.append("🔄 el fabricante reemplazó uno por el otro")
            break

    # 7. Precio: no confirma nada por sí solo, pero una diferencia enorme sí desmiente.
    # Igual que en evaluar_equivalencia(), la diferencia se mide contra lo TÍPICO entre esos
    # dos proveedores. Dos listas pueden estar en escalas completamente distintas —una
    # desactualizada, otra sin IVA— y entonces TODAS las parejas entre ellas se diferencian por
    # el mismo factor. Sobre las listas reales el precio mediano de un proveedor es $1.350 y el
    # de otro $37.610: 28 veces. Con el umbral fijo en 15, este veto tumbaba a 15 puntos casi
    # todas las parejas entre esos dos, y un veto no admite discusión — el par se iba a revisión
    # manual aunque fuera la misma bobina con el mismo texto.
    # Acá pesa más que en evaluar_equivalencia() justamente porque VETA en vez de descontar.
    if pa["precio"] and pb["precio"] and pa["precio"] > 0 and pb["precio"] > 0:
        razon, esperada, razon_real = comparar_precios(
            pa["precio"], pa["marca"], pb["precio"], pb["marca"], escalas_de_precio())
        if razon_real >= 15:
            vetos.append(texto_de_precios_que_no_cierran(razon, esperada))

    # 8. El portal de un proveedor los muestra juntos: en la ficha de uno está el código del
    # otro. Un distribuidor que vende la misma pieza en varias marcas —JL— lo pone ahí para
    # que el cliente elija. Cuenta como UNA prueba, igual que las demás: los vetos de arriba la
    # tumban si las medidas, el rubro o el auto dicen otra cosa, porque en la misma página
    # también puede haber «productos relacionados» que no son la misma pieza.
    _portales = _recordado(("portales_ev",), _pares_de_portales).get(
        (min(id_a, id_b), max(id_a, id_b)), [])
    if _portales:
        # Los catálogos de fabricante se guardan como «CATÁLOGO SKF»: ver
        # leer_catalogo_de_fabricante().
        _de = [f"el catálogo de {p.split(' ', 1)[1]}" if p.startswith("CATÁLOGO ")
               else "las publicaciones de Mercado Libre" if p == "MERCADO LIBRE"
               else f"el portal de {p}" for p in _portales]
        _verbo = "muestran" if len(_de) > 1 or _de[0].startswith("las ") else "muestra"
        a_favor.append(f"🌐 {', '.join(_de)} los {_verbo} juntos")

    if vetos:
        veredicto = "🔴 hay evidencia en contra"
    elif len(a_favor) >= 3:
        veredicto = "🟢 confirmada por varios métodos"
    elif len(a_favor) == 2:
        veredicto = "🟡 dos métodos coinciden"
    elif len(a_favor) == 1:
        veredicto = "🟠 un solo método, conviene mirarla"
    else:
        # Con el porqué, si las descripciones dicen algo para desconfiar: la revisión lo muestra
        # en vez de «nada dice que sean la misma pieza» (ver _MOTIVOS_QUE_AVISAN).
        veredicto = "⚪ sin evidencia a favor" + (f" · {aviso_desc}" if aviso_desc else "")
    return a_favor, vetos, veredicto


# LA FICHA DE PRUEBA DE UNA EQUIVALENCIA. El puntaje junta todo en un número y el buscador lo
# dice en una frase; esto lo abre: quién declara cada paso, qué medidas coinciden, qué la
# contradice y quién la comprobó. Lo propuso una revisión con ChatGPT: «limpia no es
# confirmada; cada equivalencia tiene que tener su ficha, y sin una fuente primaria no puede
# ser VERIFICADA». La fuente primaria es la que conoce la pieza y lo declara —la lista de un
# proveedor, el catálogo de un fabricante, una persona con la pieza en la mano—; que se
# parezcan las descripciones o que vayan en el mismo auto son pistas. Ver respaldo_del_origen().
#
# Las medidas no pueden ser obligatorias: las tiene cargadas el 1 o 2 % del catálogo (sobre la
# base real del 7/10, 1.142 productos con diámetro interno de 86.946). Se muestran las que
# importan para esa clase de pieza como «para confirmar en la mano», y la que se contradice sí
# tumba la equivalencia, como siempre.
_PIEZAS_Y_SUS_MEDIDAS = (
    (r"\b(HOMOCINETICA|TRIPOIDE|SEMIEJE)", "homocinética",
     ("cantidad_estrias", "diametro_rosca_homocinetica", "diametro_externo")),
    (r"\b(RULEMAN|RODAMIENTO|CRAPODINA|COLLARIN)", "rodamiento",
     ("diametro_interno", "diametro_externo", "ancho")),
    (r"\bRETEN", "retén", ("diametro_interno", "diametro_externo", "ancho")),
    (r"\bBUJIA", "bujía", ("paso_rosca", "largo_total")),
    (r"\bFILTRO", "filtro", ("diametro_externo", "diametro_interno", "largo_total", "paso_rosca")),
    (r"\bCORREA", "correa", ("cantidad_canales", "largo_total", "ancho")),
    (r"\b(POLEA|TENSOR)", "polea o tensor", ("cantidad_canales", "diametro_externo", "ancho")),
    (r"\b(PASTILLA|ZAPATA)", "pastilla o zapata", ("largo_total", "ancho", "espesor", "posicion")),
    (r"\b(DISCO DE FRENO|CAMPANA)", "disco o campana", ("diametro_externo", "espesor", "posicion")),
    (r"\bABS\b", "sensor de ABS", ("cantidad_vias", "posicion")),
    (r"\b(JUNTA|JTA)\b", "junta", ("espesor",)),
    (r"\b(FICHA|CONECTOR|SENSOR|SONDA|BOBINA|BULBO|INTERRUPTOR)", "pieza eléctrica",
     ("cantidad_vias",)),
    (r"\b(AMORTIGUADOR|PARRILLA|BRAZO|ROTULA|BIELETA|EXTREMO|MAZA|OPTICA|FARO|ESPEJO)",
     "pieza que va de un lado", ("posicion",)),
)
# Las que se comparan por igualdad y no con tolerancia: ver comparar_medidas().
_MEDIDAS_EXACTAS = (("paso_rosca", "paso de rosca"), ("cantidad_estrias", "estrías"),
                    ("cantidad_vias", "vías de la ficha"), ("cantidad_canales", "canales de la polea"),
                    ("posicion", "posición"))
# Desde acá un vínculo es «sólido» en el buscador. Ver buscar_por_codigo().
CONFIANZA_SOLIDA = 70


# QUÉ TAN GRAVE ES VENDERLA MAL, aparte de cuánta evidencia haya. Lo propuso una revisión con
# ChatGPT: «una equivalencia puede tener evidencia excelente y ser una pieza crítica».
# Crítica: las autopartes de seguridad (es_pieza_de_seguridad(), la lista del Decreto 779/95
# que usa el CHAS). Alta: la que si está mal rompe el motor.
_RE_RIESGO_ALTO = re.compile(r"\b(?:CORREA|KIT|TENSOR|CADENA)\s+(?:DE\s+)?DISTRIB"
                             r"|\bBOMBA\s+(?:DE\s+)?ACEITE"
                             r"|\b(?:JUNTA|JTA)\s+(?:DE\s+)?TAPA\s+(?:DE\s+)?CIL")


# Cada cuántos meses se vuelve a mirar una equivalencia según su riesgo. El resto, solo si
# algo la contradice. Ver ficha_de_prueba().
MESES_DE_VIGENCIA_POR_RIESGO = {"🛑": 6, "🟠": 12}


def riesgo_de_la_pieza(*descripciones):
    """(nivel, por qué) de la pieza: 🛑 crítico, 🟠 alto o 🟢 normal."""
    if any(es_pieza_de_seguridad(d) for d in descripciones if d):
        return "🛑 crítico", "es una pieza de seguridad: si está mal, falla en la calle"
    if any(_RE_RIESGO_ALTO.search(_normalizar_desc(d)) for d in descripciones if d):
        return "🟠 alto", "si está mal, puede romper el motor"
    return "🟢 normal", ""


def que_pieza_es(*descripciones):
    """(nombre de la clase de pieza, las medidas que la identifican), por la descripción."""
    for descripcion in descripciones:
        texto = _normalizar_desc(descripcion)
        for patron, nombre, campos in _PIEZAS_Y_SUS_MEDIDAS:
            if re.search(patron, texto):
                return nombre, campos
    return None, ()


def _unidad_confundida(va, vb):
    """« (¿mm contra cm?)» si una medida es diez veces la otra, o 25,4 (pulgadas). Es la pista
    de un dato mal cargado, no de otra pieza: lo pidió una revisión con ChatGPT («25,4 mm contra
    25,4 cm»). La app no convierte unidades: las medidas se leen en milímetros."""
    chica, grande = sorted((va, vb))
    if not chica:
        return ""
    razon = grande / chica
    if abs(razon - 10) <= 0.2:
        return " (¿una en mm y la otra en cm?)"
    if abs(razon - 25.4) <= 0.5:
        return " (¿una en pulgadas?)"
    return ""


def medidas_lado_a_lado(med_a, med_b, campos_que_importan=(), tolerancia_pct=3):
    """Cada medida de los dos productos con su estado: igual, dentro de la tolerancia, falta o
    distinta. Las que importan para esa pieza salen aunque no las tenga ninguno de los dos."""
    med_a, med_b = med_a or {}, med_b or {}
    exactas = dict(_MEDIDAS_EXACTAS)
    filas = []
    for campo, etiqueta in list(CAMPOS_MEDIDAS) + list(_MEDIDAS_EXACTAS):
        va, vb = med_a.get(campo), med_b.get(campo)
        # Vacío o en cero es «no se midió»: comparar_medidas() tampoco compara un cero.
        va = None if va in (None, "", 0) else va
        vb = None if vb in (None, "", 0) else vb
        importa = campo in campos_que_importan
        if va is None and vb is None:
            if importa:
                filas.append({"Medida": etiqueta, "A": "—", "B": "—", "Importa": "sí",
                              "Estado": "❓ no la tiene ninguno"})
            continue
        if va is None or vb is None:
            estado = f"❓ falta en {'A' if va is None else 'B'}"
        elif campo in exactas:
            estado = ("✅ igual" if str(va).strip().upper() == str(vb).strip().upper()
                      else "❌ distinta")
        else:
            try:
                fa, fb = float(va), float(vb)
            except (TypeError, ValueError):     # una medida cargada como texto
                fa = fb = None
            if fa is None:
                estado = "✅ igual" if str(va).strip() == str(vb).strip() else "❌ distinta"
            elif fa == fb:
                estado = "✅ igual"
            elif abs(fa - fb) <= diferencia_que_se_acepta(campo, fa, fb, tolerancia_pct):
                estado = f"≈ dentro de la tolerancia ({abs(fa - fb):g} mm)".replace(".", ",")
            else:
                estado = f"❌ distinta ({abs(fa - fb):g} mm)".replace(".", ",") + _unidad_confundida(fa, fb)
        filas.append({"Medida": etiqueta, "A": "—" if va is None else va,
                      "B": "—" if vb is None else vb, "Importa": "sí" if importa else "",
                      "Estado": estado})
    return filas


def _fuente_del_paso(lote, verificada):
    """El nombre de quien declara un paso. Dos importaciones de la misma lista son UNA fuente."""
    if verificada:
        return "a mano"
    return (lote or "").split(" · ")[0].strip().upper() or "—"


def numeros_en_comun(id_a, id_b, tope=12):
    """Los códigos que unen a los dos en dos pasos, con quién declara cada mitad.

    Es la forma más común de una equivalencia entre dos proveedores: los dos citan el mismo
    número de fábrica. Cuantos más números distintos compartan, más difícil que sea casualidad.
    Las fuentes se cuentan por nombre: la lista de FISPA importada tres veces es una fuente."""
    vecinos = {}
    for pid in (id_a, id_b):
        c.execute("""SELECT CASE WHEN producto_a_id = ? THEN producto_b_id ELSE producto_a_id END
                            AS x, lote, COALESCE(verificada, 0) AS v
                     FROM equivalencias WHERE producto_a_id = ? OR producto_b_id = ?""",
                  (pid, pid, pid))
        vecinos[pid] = {r["x"]: (r["lote"], r["v"]) for r in c.fetchall()}
    comunes = sorted(set(vecinos[id_a]) & set(vecinos[id_b]))
    if not comunes:
        return []
    marcadores = ",".join("?" * len(comunes[:tope]))
    c.execute(f"""SELECT p.id, p.codigo_raw, m.nombre AS marca FROM productos p
                  JOIN marcas m ON m.id = p.marca_id WHERE p.id IN ({marcadores})""",
              comunes[:tope])
    nombres = {r["id"]: f"{r['codigo_raw']} ({r['marca']})" for r in c.fetchall()}
    salida = []
    for x in comunes[:tope]:
        mitades = [vecinos[id_a][x], vecinos[id_b][x]]
        respaldos = [respaldo_del_origen(lote, v) for lote, v in mitades]
        salida.append({"Número": nombres.get(x, str(x)),
                       "Fuentes": " + ".join(_fuente_del_paso(lote, v) for lote, v in mitades),
                       "Las dos mitades con fuente": "sí" if all(r[0] for r in respaldos) else "no",
                       "_fuentes": {_fuente_del_paso(lote, v) for lote, v in mitades},
                       "_primarias": all(r[0] for r in respaldos)})
    return salida


def el_buscado_mas_cercano(origenes, destino):
    """De los productos con el código buscado —puede estar cargado en varias marcas—, el que se
    une a `destino`: primero el que tiene un vínculo directo, después el que tiene alguna cadena.

    Sin esto la ficha salía «sin cadena» para un resultado directo: el buscado de una marca no
    tenía vínculos, y el resultado colgaba del mismo número cargado en otra."""
    origenes = list(dict.fromkeys(origenes))
    if len(origenes) <= 1:
        return origenes[0] if origenes else None
    marcadores = ",".join("?" * len(origenes))
    c.execute(f"""SELECT CASE WHEN producto_b_id = ? THEN producto_a_id ELSE producto_b_id END
                         AS origen
                  FROM equivalencias
                  WHERE (producto_a_id IN ({marcadores}) AND producto_b_id = ?)
                     OR (producto_b_id IN ({marcadores}) AND producto_a_id = ?)""",
              [destino] + origenes + [destino] + origenes + [destino])
    directos = {r["origen"] for r in c.fetchall()}
    for o in origenes:
        if o in directos:
            return o
    return next((o for o in origenes if camino_entre(o, destino)), origenes[0])


_ORDEN_DE_LOS_ESTADOS = ("✅ VERIFICADA", "🟡 PROBABLE", "🟠 CANDIDATA", "⚪ SIN CADENA",
                         "🔴 CON CONTRADICCIONES")


def _evaluar_la_cadena(pasos):
    """(estado, falta) de una cadena de vínculos, sin mirar todavía lo que la contradice."""
    falta = []
    sin_fuente = [p for p in pasos if not p["_primaria"]]
    flojos = [p for p in pasos if not p["_verificada"] and p["Confianza"] < CONFIANZA_SOLIDA]
    for p in sin_fuente:
        falta.append(f"una fuente que declare {p['Paso']} — hoy: {p['Respaldo']}")
    if len(pasos) > 1:
        falta.append(f"una fuente que nombre los dos códigos juntos: hoy llega por "
                     f"{len(pasos) - 1} código(s) en el medio")
    for p in flojos:
        falta.append(f"que {p['Paso']} sea sólido: tiene {p['Confianza']}/100 y sólido es "
                     f"{CONFIANZA_SOLIDA} o más (mirá sus señales en Revisar vínculos)")
    # Un CAMBIO DE NÚMERO no es una equivalencia técnica: el nuevo reemplaza al viejo, pero no
    # siempre al revés ni en todas las aplicaciones (lo marcó la misma revisión).
    for p in pasos:
        if not p["_verificada"] and (p["_lote"] or "").upper().startswith("POR REEMPLAZO"):
            falta.append(f"{p['Paso']} es un cambio de número del fabricante: el nuevo "
                         "reemplaza al viejo, no siempre al revés; confirmá que sirva en este auto")
    return ("🟠 CANDIDATA" if sin_fuente else "🟡 PROBABLE" if falta else "✅ VERIFICADA"), falta


def ficha_de_prueba(id_a, id_b, tolerancia_pct=3):
    """Todo lo que sostiene —o no— que A y B son la misma pieza, y el estado que sale de eso.

    Estados, de mejor a peor:
      ✅ VERIFICADA — un vínculo directo que declara una fuente (o que una persona comprobó),
                      sólido, y nada que la contradiga;
      🟡 PROBABLE   — todos los pasos tienen fuente, pero llega por un código en el medio o el
                      vínculo no es sólido;
      🟠 CANDIDATA  — algún paso es solo una pista (se parecen las descripciones, el mismo auto);
      ⚪ SIN CADENA — no hay vínculos entre los dos (a lo sumo, el mismo número en otra marca);
      🔴 CON CONTRADICCIONES — las medidas, el rubro, la posición o el motor dicen que no.
    «Falta» dice qué la llevaría a VERIFICADA. None si alguno de los dos ya no existe."""
    c.execute(f"""SELECT p.id, p.codigo_raw, p.codigo_clean, p.descripcion, m.nombre AS marca,
                         m.tipo AS tipo,
                         {campo_opcional_de_producto(c, "imagen_thumb", "foto")}
                  FROM productos p JOIN marcas m ON m.id = p.marca_id WHERE p.id IN (?, ?)""",
              (id_a, id_b))
    info = {r["id"]: dict(r) for r in c.fetchall()}
    if id_a not in info or id_b not in info or id_a == id_b:
        return None
    pa, pb = info[id_a], info[id_b]
    # La pieza se toma de la descripción de un proveedor y no del código de fábrica, que copia
    # la de la fila que lo trajo primero.
    _descs = [p["descripcion"] for p in (pa, pb) if (p["tipo"] or "").upper() != "OEM"] or \
             [pa["descripcion"], pb["descripcion"]]
    pieza, campos_de_la_pieza = que_pieza_es(*_descs)
    ficha = {"a": pa, "b": pb, "rubro": familia_para_comparar(_descs[0]), "pieza": pieza}

    # La cadena, paso por paso, con quién declara cada uno y si alguien lo revisó. Se miran
    # dos: el vínculo directo, si lo hay, y la cadena más confiable (la que muestra el
    # buscador). No siempre coinciden —un directo flojo del barrido y una cadena sólida por el
    # número de fábrica— y la ficha se queda con la que mejor la sostiene.
    cadenas = []
    c.execute("""SELECT COALESCE(confianza, 50) AS conf, lote, COALESCE(verificada, 0) AS v
                 FROM equivalencias WHERE producto_a_id = ? AND producto_b_id = ?""",
              (min(id_a, id_b), max(id_a, id_b)))
    directo = c.fetchone()
    if directo:
        cadenas.append([{"Paso": f"{pa['codigo_raw']} ({pa['marca']}) → "
                                 f"{pb['codigo_raw']} ({pb['marca']})",
                         "Confianza": directo["conf"],
                         "Vino de": (directo["lote"] or "—").split(" · ")[0],
                         "_lote": directo["lote"], "_verificada": bool(directo["v"]),
                         "_a": id_a, "_b": id_b}])
    mejor_camino = camino_entre(id_a, id_b)
    if mejor_camino and len(mejor_camino) > 1:
        cadenas.append(mejor_camino)
    for paso in (p for pasos in cadenas for p in pasos):
        paso["_primaria"], paso["Respaldo"] = respaldo_del_origen(paso["_lote"],
                                                                  paso["_verificada"])
        c.execute("""SELECT e.nota, r.decision, r.revisado_por, r.fecha, r.por_que
                     FROM equivalencias e LEFT JOIN equivalencias_revisadas r
                       ON r.producto_a_id = e.producto_a_id AND r.producto_b_id = e.producto_b_id
                     WHERE e.producto_a_id = ? AND e.producto_b_id = ?""",
                  (min(paso["_a"], paso["_b"]), max(paso["_a"], paso["_b"])))
        fila = c.fetchone()
        paso["Revisión"] = ""
        paso["_nota"] = (fila["nota"] or "") if fila else ""
        paso["_fecha_revision"] = ""
        paso["_por_que"] = (fila["por_que"] or "") if fila else ""
        if fila and fila["decision"] == "ok":
            paso["Revisión"] = (f"aprobado por {fila['revisado_por'] or 'alguien'}"
                                f" el {(fila['fecha'] or '')[:10]}")
            paso["_fecha_revision"] = (fila["fecha"] or "")[:10]
    evaluadas = [(_evaluar_la_cadena(pasos), pasos) for pasos in cadenas]
    evaluadas.sort(key=lambda x: _ORDEN_DE_LOS_ESTADOS.index(x[0][0]))
    (estado, falta), pasos = evaluadas[0] if evaluadas else (
        ("⚪ SIN CADENA", ["es el mismo número en otra marca, pero ninguna lista ni catálogo "
                          "dice que sea la misma pieza" if pa["codigo_clean"] == pb["codigo_clean"]
                          else "no hay ningún vínculo entre los dos"]), [])
    ficha["pasos"] = pasos
    ficha["numeros_en_comun"] = numeros_en_comun(id_a, id_b)
    ficha["fuentes"] = sorted({_fuente_del_paso(p["_lote"], p["_verificada"])
                               for pasos_ in cadenas for p in pasos_ if p["_primaria"]}
                              | {f for n in ficha["numeros_en_comun"] if n["_primarias"]
                                 for f in n["_fuentes"]})
    ficha["comprobaciones"] = list(dict.fromkeys(
        parte.strip() for pasos_ in cadenas for p in pasos_
        for parte in p["_nota"].split(" · ") if parte.strip().startswith("✋")))

    # Las medidas, una por una.
    medidas = cargar_medidas_de_varios([id_a, id_b])
    ficha["medidas"] = medidas_lado_a_lado(medidas.get(id_a), medidas.get(id_b),
                                           campos_de_la_pieza, tolerancia_pct)
    ficha["para_medir"] = [m["Medida"] for m in ficha["medidas"]
                           if m["Importa"] and m["Estado"].startswith("❓")]

    # Lo que volvió, en los dos sentidos (se pidió A y se llevó B, o al revés). Ver
    # registrar_devolucion(): la que volvió porque no le iba ya está entre los vetos.
    c.execute("""SELECT d.motivo, d.detalle, d.usuario, substr(d.fecha, 1, 10) AS fecha
                 FROM devoluciones d JOIN productos p ON p.codigo_clean = d.codigo_pedido_clean
                 WHERE (d.producto_id = ? AND p.id = ?) OR (d.producto_id = ? AND p.id = ?)
                 ORDER BY d.fecha DESC""", (id_b, id_a, id_a, id_b))
    ficha["devoluciones"] = [
        f"↩️ {MOTIVOS_DE_DEVOLUCION.get(r['motivo'], r['motivo'])} — {r['usuario'] or 'alguien'}, "
        f"{r['fecha']}" + (f": {r['detalle']}" if r["detalle"] else "") for r in c.fetchall()]

    # Lo que la contradice. El precio no prueba nada a favor y en contra solo avisa: dos listas
    # pueden estar en escalas distintas. Ver evidencia_cruzada(), punto 7.
    a_favor, vetos, _ = evidencia_cruzada(id_a, id_b)
    ficha["a_favor"] = a_favor
    ficha["contradicciones"] = [v for v in vetos if not v.startswith("💲")]
    ficha["avisos"] = [v for v in vetos if v.startswith("💲")]

    if ficha["contradicciones"]:
        estado = "🔴 CON CONTRADICCIONES"
        falta = ["que no haya nada en contra: con esto, no es la misma pieza hasta que alguien "
                 "la compare en la mano"]
    # EL RIESGO Y QUÉ HACER: aparte del estado. Una pieza de seguridad bien respaldada igual
    # se mira antes de venderla, salvo que alguien ya la haya comprobado en la mano.
    ficha["riesgo"], ficha["por_que_riesgo"] = riesgo_de_la_pieza(*_descs)
    _comprobada = bool(ficha["comprobaciones"]) or (pasos and all(p["_verificada"] for p in pasos))
    ficha["accion"] = (
        "" if _comprobada or ficha["riesgo"].startswith("🟢") else
        "comparala con la pieza en la mano antes de venderla" if ficha["riesgo"].startswith("🛑")
        else "mirá las medidas o la pieza antes de venderla")

    # LA EXPLICACIÓN MÍNIMA: lo que la sostiene, en una línea. El detalle va abajo. Lo pidió la
    # misma revisión: «para el mostrador no mostraría 20 datos».
    resumen = []
    if pasos and len(pasos) == 1 and pasos[0]["_primaria"]:
        resumen.append(pasos[0]["Respaldo"])
    _n_comunes = sum(1 for n in ficha["numeros_en_comun"] if n["_primarias"])
    if _n_comunes:
        resumen.append(f"🔢 los dos citan {_n_comunes} número(s) de fábrica")
    _iguales = sum(1 for m in ficha["medidas"] if m["Estado"].startswith(("✅", "≈")))
    if _iguales:
        resumen.append(f"📐 {_iguales} medida(s) iguales")
    resumen += [x for x in a_favor if x.startswith(("🏭", "🔄", "🌐"))][:1]
    if ficha["comprobaciones"]:
        resumen.append("✋ comprobada en la mano")
    ficha["resumen"] = resumen

    # CUÁNDO SE MIRÓ POR ÚLTIMA VEZ, y si para su riesgo ya toca volver a mirarla. Lo pidió una
    # revisión con ChatGPT («fecha de vigencia» y «revisión basada en riesgo»): una pieza de
    # seguridad se vuelve a mirar cada 6 meses, una que rompe el motor cada 12, y el resto solo si
    # algo la contradice. Las fechas son la de la revisión de cada paso y la de la comprobación
    # en la mano.
    fechas = [p["_fecha_revision"] for p in pasos if p.get("_fecha_revision")]
    for nota in ficha["comprobaciones"]:
        m = re.search(r"(\d{2})/(\d{2})/(\d{4})", nota)
        if m:
            fechas.append(f"{m.group(3)}-{m.group(2)}-{m.group(1)}")
    ficha["ultima_revision"] = max(fechas) if fechas else ""
    ficha["meses_sin_revisar"] = None
    if ficha["ultima_revision"]:
        try:
            _desde = datetime.strptime(ficha["ultima_revision"], "%Y-%m-%d")
            ficha["meses_sin_revisar"] = max(0, (datetime.now() - _desde).days // 30)
        except ValueError:
            pass
    _vigencia = MESES_DE_VIGENCIA_POR_RIESGO.get(ficha["riesgo"][:1])
    if (_vigencia and ficha["meses_sin_revisar"] is not None
            and ficha["meses_sin_revisar"] >= _vigencia and estado.startswith("✅")):
        falta.append(f"volver a mirarla: se revisó hace {ficha['meses_sin_revisar']} meses y "
                     f"para una pieza de riesgo {ficha['riesgo'][2:]} toca cada {_vigencia}")
        estado = "🟡 PROBABLE"

    if not estado.startswith(("✅", "🔴")):
        falta.append("o comprobarla con la pieza en la mano"
                     + (f" (medir: {', '.join(ficha['para_medir'])})" if ficha["para_medir"]
                        else ""))
    ficha["estado"], ficha["falta"] = estado, falta
    return ficha


def comprobar_en_la_mano(id_a, id_b, como):
    """Anota que alguien comparó las dos piezas en la mano: quién, cuándo y qué miró.

    Es la validación física de la ficha de prueba. Si ya hay un vínculo directo se le pone la
    marca y se le suma la nota, sin tocar de qué lista vino; si no lo hay —llegaban por un
    código en el medio—, se crea uno directo, verificado. Devuelve la nota que quedó."""
    exigir_nivel("empleado", "marcar una equivalencia como comprobada")
    # « · » es lo que separa las notas de un mismo vínculo: adentro de una, partiría la nota.
    como = (como or "").replace(" · ", ", ").strip()
    if not como:
        raise ValueError("Escribí qué miraste: la medida, la rosca, la ficha…")
    a, b = min(id_a, id_b), max(id_a, id_b)
    nota = (f"✋ Comprobada en la mano por {obtener_usuario_actual()} el "
            f"{datetime.now():%d/%m/%Y}: {como}")
    with db_lock, transaccion():
        c.execute("SELECT nota FROM equivalencias WHERE producto_a_id = ? AND producto_b_id = ?",
                  (a, b))
        fila = c.fetchone()
        if fila:
            c.execute("""UPDATE equivalencias SET verificada = 1,
                                nota = CASE WHEN COALESCE(nota, '') = '' THEN ?
                                            ELSE nota || ' · ' || ? END
                         WHERE producto_a_id = ? AND producto_b_id = ?""", (nota, nota, a, b))
        else:
            c.execute("""INSERT INTO equivalencias
                             (producto_a_id, producto_b_id, created_at, verificada, nivel, nota, lote)
                         VALUES (?, ?, datetime('now'), 1, 'Exacta', ?, ?)""",
                      (a, b, nota, f"COMPROBADA EN LA MANO · {datetime.now():%d/%m/%Y %H:%M}"))
    marcar_revision([(a, b)], "ok")
    return nota


def derivar_equivalencias_por_medidas(minimo_medidas=3, limite=400):
    """Encuentra equivalencias cruzando las MEDIDAS cargadas, entre marcas distintas.

    Las medidas se venían usando solo para verificar un vínculo que ya existía. Pero en varias
    familias la medida ES la identidad de la pieza: un retén 35x52x7 de un proveedor y uno
    35x52x7 de otro son el mismo repuesto, y no hace falta que las descripciones se parezcan
    ni que compartan un código.

    Es la evidencia más fuerte que hay: no es texto ni interpretación, es la pieza física.

    Se piden al menos 3 medidas coincidentes. Con una sola —por ejemplo, solo el diámetro
    interno— coincidirían piezas completamente distintas que casualmente miden lo mismo."""
    campos = [cn for cn, _ in CAMPOS_MEDIDAS]
    seleccion = ", ".join(f"p.{cn}" for cn in campos)
    c.execute(f"""SELECT p.id, p.codigo_raw, p.descripcion, p.marca_id, m.nombre AS marca,
                         p.precio, p.stock, {seleccion}, p.paso_rosca, p.cantidad_estrias
                  FROM productos p JOIN marcas m ON m.id = p.marca_id""")
    productos = [dict(r) for r in c.fetchall()]

    # Se agrupa por la combinación exacta de medidas. Sin agrupar habría que comparar todos
    # contra todos; agrupando, los que comparten medidas caen juntos y el resto ni se mira.
    grupos = {}
    for f in productos:
        valores = tuple(round(f[cn], 2) if f[cn] is not None else None for cn in campos)
        cuantas = sum(1 for v in valores if v is not None)
        if cuantas < minimo_medidas:
            continue
        clave = valores + ((f["paso_rosca"] or "").strip().upper(),
                           (f["cantidad_estrias"] or "").strip().upper())
        grupos.setdefault(clave, []).append(f)

    ya = set()
    c.execute("SELECT producto_a_id, producto_b_id FROM equivalencias")
    for r in c.fetchall():
        ya.add((r["producto_a_id"], r["producto_b_id"]))
    rechazados = pares_rechazados()

    salida = []
    for clave, miembros in grupos.items():
        # Solo interesa si hay al menos dos MARCAS distintas: dos códigos de la misma marca
        # con las mismas medidas suelen ser presentaciones del mismo producto, no equivalentes
        # que aporten algo.
        if len({f["marca_id"] for f in miembros}) < 2:
            continue
        for i, pa in enumerate(miembros):
            for pb in miembros[i + 1:]:
                if pa["marca_id"] == pb["marca_id"]:
                    continue
                par = (min(pa["id"], pb["id"]), max(pa["id"], pb["id"]))
                if par in ya or par in rechazados:
                    continue
                # Aun con las medidas iguales, dos rubros distintos no son la misma pieza:
                # una arandela y un separador pueden medir exactamente lo mismo.
                # Con las medidas iguales igual hay que mirar la pieza: una arandela y un
                # retén pueden medir exactamente lo mismo. Y no alcanza con comparar el rubro
                # —«ARANDELA DE COBRE» queda sin clasificar y se colaba—, así que se compara
                # también el sustantivo principal de la descripción.
                fa = firma_de_producto(pa["descripcion"] or "")
                fb = firma_de_producto(pb["descripcion"] or "")
                if not fa or not fb:
                    continue
                if ("Sin clasificar" not in (fa["familia"], fb["familia"])
                        and fa["familia"] != fb["familia"]):
                    continue
                if fa["cabeza"] and fb["cabeza"] and fa["cabeza"] != fb["cabeza"]:
                    if not (fa["cabeza"] in fb["cabeza"] or fb["cabeza"] in fa["cabeza"]):
                        continue
                detalle = ", ".join(
                    f"{eti} {clave[j]}" for j, (cn, eti) in enumerate(CAMPOS_MEDIDAS)
                    if clave[j] is not None
                )
                salida.append({
                    "Código A": pa["codigo_raw"], "Marca A": pa["marca"],
                    "Descripción A": (pa["descripcion"] or "")[:40],
                    "Código B": pb["codigo_raw"], "Marca B": pb["marca"],
                    "Descripción B": (pb["descripcion"] or "")[:40],
                    "Medidas que coinciden": detalle[:70],
                    "_a": pa["id"], "_b": pb["id"],
                })
                if len(salida) >= limite:
                    return salida
    return salida


def equivalencias_puenteadas_por_reemplazo(limite=300):
    """Vincula lo que quedó separado porque el fabricante cambió el número.

    Caso concreto: tenés A vinculado al código de fábrica viejo, y B vinculado al nuevo. Son
    el mismo repuesto, pero para la app son dos islas sin relación, porque el cambio de número
    partió la cadena al medio.

    Los reemplazos que cargaste a mano ya sabían que el viejo y el nuevo son lo mismo. Esto
    usa ese dato para volver a unir lo que el cambio de número separó."""
    try:
        c.execute("SELECT codigo_viejo_clean, codigo_nuevo_clean FROM reemplazos_codigo")
        cadenas = [(r["codigo_viejo_clean"], r["codigo_nuevo_clean"]) for r in c.fetchall()]
    except sqlite3.OperationalError as _err:
        anotar_error("equivalencias_puenteadas_por_reemplazo", _err)
        return []
    if not cadenas:
        return []

    ya = set()
    c.execute("SELECT producto_a_id, producto_b_id FROM equivalencias")
    for r in c.fetchall():
        ya.add((r["producto_a_id"], r["producto_b_id"]))
    rechazados = pares_rechazados()

    salida = []
    for viejo, nuevo in cadenas:
        c.execute("""SELECT p.id, p.codigo_raw, m.nombre AS marca, p.descripcion
                     FROM productos p JOIN marcas m ON m.id = p.marca_id
                     WHERE p.codigo_clean = ?""", (viejo,))
        de_viejo = [dict(r) for r in c.fetchall()]
        c.execute("""SELECT p.id, p.codigo_raw, m.nombre AS marca, p.descripcion
                     FROM productos p JOIN marcas m ON m.id = p.marca_id
                     WHERE p.codigo_clean = ?""", (nuevo,))
        de_nuevo = [dict(r) for r in c.fetchall()]
        for pa in de_viejo:
            for pb in de_nuevo:
                par = (min(pa["id"], pb["id"]), max(pa["id"], pb["id"]))
                if pa["id"] == pb["id"] or par in ya or par in rechazados:
                    continue
                salida.append({
                    "Código A": pa["codigo_raw"], "Marca A": pa["marca"],
                    "Código B": pb["codigo_raw"], "Marca B": pb["marca"],
                    "Por qué": f"el fabricante reemplazó {pa['codigo_raw']} por {pb['codigo_raw']}",
                    "_a": pa["id"], "_b": pb["id"],
                })
                if len(salida) >= limite:
                    return salida
    return salida


# Antes 4.000, que sobre la lista de JL —25.975 productos— dejaba afuera el 85%, y siempre
# las mismas filas: las últimas de cada lista no se comparaban NUNCA, corrieras la comparación
# las veces que la corrieras. Medido con las listas reales, sin tope el peor cruce (JL de
# 25.975 contra Illinois de 6.898) tarda 16,5 s contra 4,4 s, y JL x MOTORARG pasa de 11
# sugerencias a 400. Queda un número igual, pero uno que ninguna lista de proveedor alcanza.
TOPE_PRODUCTOS_POR_COMPARACION = 50000  # ver derivar_equivalencias_por_descripcion()


def derivar_equivalencias_por_descripcion(marca_a_id=None, marca_b_id=None,
                                          limite=2000,
                                          tope_productos=TOPE_PRODUCTOS_POR_COMPARACION,
                                          por_producto=3):
    """Vincula productos de DOS proveedores distintos comparando lo que dicen sus descripciones.

    Es la respuesta al problema de fondo: la mayoría de las listas no traen el código de
    fábrica, y sin esa columna la app no generaba ninguna equivalencia. Con esto, dos
    proveedores que describen la misma pieza para el mismo auto quedan vinculados.

    Se compara solo dentro del mismo rubro. Eso no es una optimización: es lo que evita que
    esto se convierta en otra fábrica de vínculos falsos, y de paso hace la comparación
    manejable —sin agrupar, serían millones de pares—."""
    if not marca_a_id or not marca_b_id or marca_a_id == marca_b_id:
        return []

    productos = {}
    for mid in (marca_a_id, marca_b_id):
        c.execute("""SELECT p.id, p.codigo_raw, p.codigo_clean, p.descripcion, p.precio,
                            p.stock, m.nombre AS marca
                     FROM productos p JOIN marcas m ON m.id = p.marca_id
                     WHERE p.marca_id = ? AND COALESCE(p.descripcion,'') <> ''
                     LIMIT ?""", (mid, tope_productos))
        productos[mid] = [dict(r) for r in c.fetchall()]

    # Las firmas ya calculadas, si el barrido de todo el catálogo las dejó en el caché: son
    # los mismos productos y la misma cuenta, y sacarlas de vuelta cuesta 15 s. Lo que no esté
    # —un catálogo de fábrica, que el barrido no mira— se calcula acá.
    _fichas = firmas_de_todo_el_catalogo(version_del_catalogo())[1]

    # Se agrupa por rubro antes de comparar: solo tiene sentido cruzar filtros con filtros
    por_rubro = {mid: {} for mid in productos}
    for mid, filas in productos.items():
        for f in filas:
            _guardada = _fichas.get(f["id"])
            firma = (_guardada[0] if _guardada else
                     firma_de_producto(f["descripcion"], f["id"], f.get("codigo_clean")))
            if not firma or firma["familia"] == "Sin clasificar":
                continue
            f["_firma"] = firma
            por_rubro[mid].setdefault(firma["familia"], []).append(f)

    _cuenta_pal, _total_desc = cuantas_veces_aparece_cada_palabra()
    ya_vinculados = set()
    c.execute("SELECT producto_a_id, producto_b_id FROM equivalencias")
    for r in c.fetchall():
        ya_vinculados.add((r["producto_a_id"], r["producto_b_id"]))
    rechazados = pares_rechazados()

    salida = []
    for familia in set(por_rubro[marca_a_id]) & set(por_rubro[marca_b_id]):
        for pa in por_rubro[marca_a_id][familia]:
            # Los mejores candidatos de ESTE producto, no todos. Un termostato de Ford puede
            # coincidir con quince del otro proveedor, y esos quince tapan al resto del
            # catálogo: se llega al tope mostrando siempre lo mismo. Se guardan los que más
            # autos comparten, que son los más probables.
            candidatos = []
            for pb in por_rubro[marca_b_id][familia]:
                par = (min(pa["id"], pb["id"]), max(pa["id"], pb["id"]))
                if par in ya_vinculados or par in rechazados:
                    continue
                ok, motivo = firmas_compatibles(pa["_firma"], pb["_firma"],
                                                cuenta_palabras=_cuenta_pal,
                                                total_descripciones=_total_desc)
                if not ok:
                    continue
                fuerza = fuerza_de_la_coincidencia(pa["_firma"], pb["_firma"])
                candidatos.append((fuerza, pb, motivo))
            # De mayor a menor fuerza. Antes ordenaba solo por marcas de auto compartidas y
            # empataba casi todo en 1: ver fuerza_de_la_coincidencia().
            candidatos.sort(key=lambda x: x[0], reverse=True)
            for _fuerza, pb, motivo in candidatos[:por_producto]:
                salida.append({
                    "Código A": pa["codigo_raw"], "Marca A": pa["marca"],
                    "Descripción A": (pa["descripcion"] or "")[:44],
                    "Código B": pb["codigo_raw"], "Marca B": pb["marca"],
                    "Descripción B": (pb["descripcion"] or "")[:44],
                    "Rubro": familia, "Por qué": motivo,
                    "_a": pa["id"], "_b": pb["id"],
                })
                if len(salida) >= limite:
                    return salida
    return salida


RELLENO_EN_NOMBRE_DE_PIEZA = {"DE", "LA", "EL", "CON", "SIN", "PARA", "POR", "DEL", "EN", "LOS",
                       "LAS", "UN", "UNA", "MM", "CM", "TIPO", "JUEGO", "JGO", "KIT", "COMPLETO",
                       "REF", "ORIG"}
# El nombre es específico a propósito: más abajo hay un _PALABRAS_DE_RELLENO que es OTRA cosa
# —las muletillas de un pedido hablado, «necesito», «dame»— y dos constantes casi homónimas a
# mil líneas de distancia son una edición equivocada esperando pasar.


# Cómo abrevian los proveedores el nombre de la pieza. No están inventadas: salieron de contar
# las palabras que entran al nombre en las 61.574 descripciones reales — «JTA» aparece 4.836
# veces, «JTAS» 2.456, «CIL» 2.115. Sin esto, «CABLE BUJIA» y «KIT CAB Y BUJ» son dos cosas
# distintas para la app, y el vínculo correcto entre ellas queda marcado como sospechoso.
ABREVIATURAS_DE_PIEZA = {
    "JTA": "JUNTA", "JTAS": "JUNTA", "JUNTAS": "JUNTA", "JGO": "JUEGO", "JGOS": "JUEGO",
    "CIL": "CILINDRO", "CILS": "CILINDRO", "CILINDROS": "CILINDRO",
    "CAB": "CABLE", "CABLES": "CABLE", "BUJ": "BUJIA", "BUJIAS": "BUJIA",
    "CPO": "CUERPO", "INY": "INYECCION", "INYEC": "INYECCION", "INYECTO": "INYECCION",
    "BBA": "BOMBA", "BOMBAS": "BOMBA", "TEMP": "TEMPERATURA", "MULT": "MULTIPLE",
    "ELECTROV": "ELECTROVENTILADOR", "ELECTROVENT": "ELECTROVENTILADOR",
    "ACEL": "ACELERADOR", "DISTRIB": "DISTRIBUCION", "REFRIG": "REFRIGERACION",
    "ALTERN": "ALTERNADOR", "ARRANQ": "ARRANQUE", "SENS": "SENSOR", "SENSORES": "SENSOR",
    "VALV": "VALVULA", "VALVULAS": "VALVULA", "TAPAS": "TAPA", "CANOS": "CANO",
    "RET": "RETEN", "RETENES": "RETEN", "TERM": "TERMOSTATO", "AMORT": "AMORTIGUADOR",
    "PAST": "PASTILLA", "PASTILLAS": "PASTILLA", "FILT": "FILTRO", "FILTROS": "FILTRO",
    "INTERRUP": "INTERRUPTOR", "REGUL": "REGULADOR", "PRES": "PRESION",
    "COMB": "COMBUSTIBLE", "IGNIC": "IGNICION", "ROTAC": "ROTACION", "DETONAC": "DETONACION",
    # Salidas de comparar las dos listas de juntas, que abrevian distinto la misma pieza:
    # Taranto escribe «Jta.Tapa Cilind.Ford» e Illinois «Junta Tapa de Cilindros FORD».
    "CILIND": "CILINDRO", "CILINDRICO": "CILINDRO", "CILIN": "CILINDRO", "JTO": "JUEGO",
    "JUEGOS": "JUEGO", "VAL": "VALVULA", "VALV": "VALVULA", "VALVS": "VALVULA",
    "ADMIS": "ADMISION", "ESCAP": "ESCAPE",
    # Las de IMPERIAL, contadas en su lista: «M.ESC», «M.ADM», «T.DIST», «SAL.AGUA», «T.VALVUL».
    "ESC": "ESCAPE", "ADM": "ADMISION", "ADMISI": "ADMISION", "DIST": "DISTRIBUCION",
    "DISTR": "DISTRIBUCION", "DISTRI": "DISTRIBUCION", "VALVUL": "VALVULA", "SAL": "SALIDA",
    "VEL": "VELOCIDAD", "BSE": "BASE", "TRANSM": "TRANSMISION", "DELANT": "DELANTERO",
    "TRAS": "TRASERO", "SUPL": "SUPLEMENTO", "SUPLEM": "SUPLEMENTO", "REPAR": "REPARACION",
    "COLEC": "COLECTOR", "COLECT": "COLECTOR", "ASPIR": "ASPIRACION", "COMPRES": "COMPRESOR",
    # «Jta.Tapa Difer.tipo 34 FORD TRANSIT» es la tapa del diferencial: sin expandir, era una
    # «junta tapa» de Transit y concordaba con la de tapa de cilindros.
    "DIFER": "DIFERENCIAL", "DIFERENC": "DIFERENCIAL",
}


def _nombre_de_la_pieza(descripcion, aceptar_codigos=False):
    """Las palabras que nombran LA PIEZA, sin los códigos y con las abreviaturas expandidas.

    Se corta apenas aparece una marca de auto o un año, porque de ahí en adelante la descripción
    deja de hablar de la pieza y empieza a listar para qué autos sirve.

    Los tokens con dígitos se descartan: son el número de parte o una medida, no el nombre. Eran
    el 73% de las palabras distintas que entraban acá (LEIHTT09SCFIAT, 64033, LSPKR6E), y como
    nunca coinciden entre dos proveedores solo servían para bajar el parecido de vínculos que
    estaban bien. Si al sacarlos no queda nada, se vuelve a armar con ellos: un nombre flojo es
    mejor que ninguno, porque sin nombre el parecido da 0 y eso también marca de más.

    Medido sobre los 24.774 vínculos reales: los marcados como «nombre de pieza muy distinto»
    bajan de 963 a 608, y los pocos que dejan de marcarse —revisados uno por uno— eran todos
    vínculos correctos («CABLE DE BUJIA» contra «KIT CAB Y BUJ»)."""
    # «VW» y «GM» ya están en MARCAS_VEHICULO; queda «MB», que no vale la pena agregar allá
    # porque como palabra suelta aparece adentro de descripciones que no hablan de Mercedes.
    marcas_auto = set(MARCAS_VEHICULO) | {"MB"}
    palabras = []
    for palabra in re.split(r'[^A-Z0-9]+', normalizar_texto(descripcion or "")):
        if not palabra:
            continue
        if palabra in marcas_auto or re.fullmatch(r'(19|20)\d{2}', palabra):
            break
        if any(ch.isdigit() for ch in palabra) and not aceptar_codigos:
            continue
        palabra = ABREVIATURAS_DE_PIEZA.get(palabra, palabra)
        if len(palabra) >= 3 and palabra not in RELLENO_EN_NOMBRE_DE_PIEZA:
            palabras.append(palabra)
        if len(palabras) >= 4:
            break
    if not palabras and not aceptar_codigos:
        return _nombre_de_la_pieza(descripcion, aceptar_codigos=True)
    return set(palabras)


def _parecido_nombre_pieza(desc_a, desc_b):
    """Cuánto se parecen los NOMBRES DE LA PIEZA de dos descripciones, de 0 a 1."""
    pieza_a, pieza_b = _nombre_de_la_pieza(desc_a), _nombre_de_la_pieza(desc_b)
    if not pieza_a or not pieza_b:
        return 0.0
    return len(pieza_a & pieza_b) / len(pieza_a | pieza_b)


def _mejores_primero(pares):
    """Ordena las sugerencias por cuánto se parecen, de mejor a peor.

    Sin esto salían en el orden en que se recorre el índice de palabras, o sea al azar. Daba lo
    mismo cuando eran 807; con 5.597 no da lo mismo: nadie revisa 5.597 de una sentada, y el que
    revisa las primeras cincuenta tiene que estar viendo las cincuenta mejores, no cincuenta
    cualesquiera. Ordena por el modelo compartido primero, después la cilindrada, el nombre de
    la pieza y la marca del auto — ver fuerza_de_la_coincidencia()."""
    return sorted(pares, key=lambda x: x.get("_fuerza") or (0, 0, 0, 0), reverse=True)


# Las firmas del catálogo, producto por producto, para no rehacerlas: ver
# firmas_de_todo_el_catalogo(). Es de cada pasada de la lógica a propósito: si cambia el código
# pueden cambiar las reglas de la firma, y ahí hay que rehacerlas todas.
_FIRMAS_DEL_CATALOGO = {}


def firmas_de_todo_el_catalogo(version):
    """(índice de palabras, fichas) de todos los productos de proveedor. Cacheado por catálogo.

    Es lo caro del barrido y lo único que no cambia entre una corrida y la siguiente: leer las
    46.644 descripciones y sacarles la firma tarda 15,2 s, contra 3 s que cuesta comparar. Sin
    caché, apretar el botón dos veces cuesta dos veces lo mismo aunque no se haya tocado nada.
    Guardado ocupa 17 MB y volver a leerlo 0,4 s, así que la segunda corrida pasa de 19 a 4 s.

    El testigo va SIN guion bajo a propósito: ver descripciones_por_palabra().

    SE REHACE SOLO LO QUE CAMBIÓ. Antes el testigo cambiaba con cada importación y se rehacían
    todas: con 60 proveedores eran 151 s y 1,7 GB después de CADA lista, para cambiar las
    firmas de 10.000 productos de 659.000. Ahora se guarda la firma de cada producto con su
    descripción, y se rehace solo si el producto es nuevo, cambió su descripción o su marca, o
    le aparecieron autos nuevos (aplicaciones de su código, o el taller le puso la pieza a un
    auto: ver autos_de_todas_las_fuentes()).

    Tampoco va más en st.cache_data: ese caché guarda una copia serializada y devuelve otra en
    cada llamada, o sea el doble de memoria, y serializar 1,7 GB tarda más que armarlo. Lo que
    devuelve es el mismo objeto para todos, y nadie lo modifica."""
    guardado = _FIRMAS_DEL_CATALOGO.get("ultimo")
    if guardado and guardado["version"] == version:
        return guardado["resultado"]
    ceder_al_mostrador()      # antes de la lectura grande. Ver ceder_al_mostrador().
    from collections import defaultdict
    previas = guardado["por_producto"] if guardado else {}
    try:
        hasta_aplic = c.execute("SELECT COALESCE(MAX(id), 0) FROM aplicaciones").fetchone()[0]
        hasta_taller = c.execute("SELECT COALESCE(MAX(id), 0) FROM historial_piezas").fetchone()[0]
        codigos_con_autos_nuevos, productos_con_autos_nuevos = set(), set()
        if guardado:
            c.execute("SELECT DISTINCT codigo_clean FROM aplicaciones WHERE id > ?",
                      (guardado["hasta_aplic"],))
            codigos_con_autos_nuevos = {r[0] for r in c.fetchall()}
            c.execute("SELECT DISTINCT producto_id FROM historial_piezas WHERE id > ?",
                      (guardado["hasta_taller"],))
            productos_con_autos_nuevos = {r[0] for r in c.fetchall()}
        # Con un cursor propio y de a pedazos, no todo junto: 600.000 productos en memoria a la
        # vez eran casi 1 GB de pico. El cursor `c` no sirve para esto porque la firma hace sus
        # propias consultas en el medio (los autos de cada producto) y lo reiniciaría.
        lector = conn.conexion_real().cursor()
        lector.execute("""SELECT p.id, p.codigo_raw, p.codigo_clean, p.descripcion, p.marca_id,
                                 m.nombre AS marca
                          FROM productos p JOIN marcas m ON m.id = p.marca_id
                          WHERE m.tipo <> 'OEM' AND COALESCE(p.descripcion, '') <> ''
                          ORDER BY p.id""")
    except sqlite3.OperationalError as _err:
        anotar_error("firmas_de_todo_el_catalogo", _err)
        return {}, {}

    def _productos():
        while True:
            pedazo = lector.fetchmany(2000)
            if not pedazo:
                return
            for fila in pedazo:
                yield dict(fila)

    indice, ficha, por_producto = defaultdict(list), {}, {}
    for prod in _productos():
        # Lo que tiene que seguir igual para no rehacerla. Para los que no tienen rubro se
        # guarda solo esto y no el producto entero: son la mitad del catálogo y no se usan.
        clave = (prod["descripcion"], prod["marca_id"], prod["codigo_raw"])
        previa = previas.get(prod["id"])
        if (previa and previa[0] == clave
                and prod["codigo_clean"] not in codigos_con_autos_nuevos
                and prod["id"] not in productos_con_autos_nuevos):
            por_producto[prod["id"]] = previa
            _clave, firma, prod, palabras = previa
        else:
            ceder_al_mostrador()
            firma = firma_de_producto(prod["descripcion"], prod["id"], prod.get("codigo_clean"))
            if not firma or firma["familia"] == "Sin clasificar":
                por_producto[prod["id"]] = (clave, None, None, ())
                continue
            palabras = tuple({p for p in re.split(r'[^A-Z0-9]+',
                                                  normalizar_texto(prod["descripcion"]))
                              if len(p) >= 3})
            por_producto[prod["id"]] = (clave, firma, prod, palabras)
        if firma is None:
            continue
        ficha[prod["id"]] = (firma, prod)
        for palabra in palabras:
            indice[palabra].append(prod["id"])
    resultado = (dict(indice), ficha)
    _FIRMAS_DEL_CATALOGO["ultimo"] = {"version": version, "resultado": resultado,
                                      "por_producto": por_producto,
                                      "hasta_aplic": hasta_aplic, "hasta_taller": hasta_taller}
    return resultado


# Sobre el catálogo real salen 8.122, así que 8.000 volvía a cortar justo como cortaba 600
# antes y 2.000 después. Traerlos todos no cuesta nada —lo caro es compararlos, y eso ya está
# hecho— y ahora además se ordenan antes de cortar, así que si alguna vez se llega al tope lo
# que queda afuera son los peores. Ver sugerir_entre_todas_las_marcas().
TOPE_SUGERENCIAS_TODAS = 20000  # ver sugerir_entre_todas_las_marcas()


def sugerir_entre_todas_las_marcas(limite=TOPE_SUGERENCIAS_TODAS, tope_palabra=250,
                                   solo_desde_id=0):
    """Lo mismo que derivar_equivalencias_por_descripcion(), pero de UNA VEZ para todo el
    catálogo en vez de elegir dos proveedores a mano.

    Por qué hace falta: con cinco proveedores cargados hay diez combinaciones para correr de a
    una, y con ocho son veintiocho. Nadie las corre todas, así que la mitad de los cruces
    posibles no se buscan nunca.

    La decisión de si dos productos son el mismo repuesto NO se toma acá: se delega en
    firmas_compatibles(), que es la que ya venía haciéndolo y sabe mirar la posición, la
    cilindrada, las siglas y el sustantivo principal. Duplicar ese criterio sería peor que no
    tenerlo — dos reglas parecidas que con el tiempo dejan de decir lo mismo.

    Lo único que aporta esta función es cómo ELEGIR qué pares mirar sin comparar todo contra
    todo. Con 110.000 productos serían seis mil millones de pares. En vez de eso se arma un
    índice de palabras POCO COMUNES: las que aparecen en pocos productos. Una palabra que está
    en miles no distingue nada; una que está en uno solo no puede emparejar; sirven las del
    medio. Comparando únicamente los pares que comparten alguna de esas queda del orden de
    ciento cincuenta mil, y se resuelve en segundos.

    DÓNDE CORTAR ESE «POCO COMÚN» ES LA DECISIÓN MÁS CARA DE ACÁ, y estaba en 40 sin haberla
    medido. Corrido sobre el catálogo real, cambiando solo ese número:

        40   →    807 sugerencias   15,9 s   confianza media 51,5   1% por debajo de 40
        100  →  2.280               16,2 s   confianza media 52,4   2%
        250  →  5.597               18,8 s   confianza media 61,4   1%
        500  → 11.899               26,4 s   confianza media 45,4   41%  ← se rompe

    O sea que con 40 se estaban perdiendo siete de cada ocho relaciones buenas por tres
    segundos, y que el límite de verdad está entre 250 y 500: pasando de ahí entran los pares
    que solo comparten la marca del auto y dos palabras genéricas («INTERRUPTOR STOP FORD»
    contra otro «INTERRUPTOR STOP FORD» de otro modelo), y 4 de cada 10 nacen ya en rojo.

    El tiempo casi no se mueve entre 40 y 250 porque lo caro no es comparar: es leer las 46.644
    descripciones y sacarles la firma (15,2 s de los 18,8). Eso ahora va cacheado por versión
    del catálogo —ver firmas_de_todo_el_catalogo()—, así que la segunda corrida tarda 4 s.

    Nada se carga solo: todo va a la cola de pendientes para que lo apruebe una persona.

    El tope no ahorra tiempo: el recorrido cuesta lo mismo con tope o sin él (19 s sobre 70.888
    productos), porque lo caro es armar el índice y comparar, no guardar el resultado. Lo único
    que hace el tope es esconder pares. Estuvo en 200 y cortaba de verdad —de 284 pares reales
    se veían 84—, se subió a 600 y volvió a cortar en cuanto entró una lista más: con Illinois
    cargada salen 787 y se veían 600. Ahora está en 2.000, y si alguna vez se llega, la
    pantalla lo dice en vez de callárselo.

    solo_desde_id: solo los pares donde al menos uno es un producto con id mayor, o sea lo que
    trajeron las listas importadas desde la última vez. Es como corre solo después de importar
    (ver descubrimiento_post_importacion()); el botón de Administrar lo hace entero.

    CADA PAR SE MIRA UNA VEZ SIN ANOTAR LOS YA VISTOS. Antes se guardaba cada par mirado en un
    conjunto para no repetirlo: con 60 proveedores eran 17 millones de pares y 1,7 GB solo de
    ese conjunto —la tanda llegó a 3,6 GB, más de lo que tiene el servidor—. Ahora un par se
    mira en la primera palabra rara que comparten, y en las demás se saltea: da los mismos
    pares sin guardar ninguno."""
    import bisect
    indice, ficha = firmas_de_todo_el_catalogo(version_del_catalogo())
    if not ficha:
        return []

    _cuenta_pal, _total_desc = cuantas_veces_aparece_cada_palabra()
    raras = {p: ids for p, ids in indice.items() if 2 <= len(ids) <= tope_palabra}
    # El número de cada palabra rara, y las de cada producto en orden: con eso se sabe cuál es
    # la primera que comparten dos productos (ver _primera_en_comun()).
    raras_de = {}
    for rango, ids in enumerate(raras.values()):
        for pid in ids:
            raras_de.setdefault(pid, []).append(rango)
    salida = []
    for rango, ids in enumerate(raras.values()):
        ceder_al_mostrador()
        # Los ids vienen en orden (ver firmas_de_todo_el_catalogo()): los nuevos están al final.
        primero_nuevo = bisect.bisect_right(ids, solo_desde_id) if solo_desde_id else 1
        for j in range(max(primero_nuevo, 1), len(ids)):
            for i in range(j):
                a, b = ids[i], ids[j]
                if _primera_en_comun(raras_de[a], raras_de[b]) != rango:
                    continue
                firma_a, prod_a = ficha[a]
                firma_b, prod_b = ficha[b]
                # Del mismo proveedor no: son dos productos de su catálogo, no equivalentes.
                if prod_a["marca_id"] == prod_b["marca_id"]:
                    continue
                ok, motivo = firmas_compatibles(firma_a, firma_b,
                                                cuenta_palabras=_cuenta_pal,
                                                total_descripciones=_total_desc)
                if not ok:
                    continue
                # Un filtro MÁS, que solo hace falta acá. Comparando de a dos proveedores,
                # firmas_compatibles() alcanza porque el recorrido ya va por familia y se queda
                # con los tres mejores de cada producto. Barriendo TODO el catálogo entran
                # muchísimos más pares y ahí se ve que su control del sustantivo principal es
                # demasiado permisivo: deja pasar SENSOR contra SENSOR, y así proponía un sensor
                # MAP contra un sensor de velocidad de caja, un sensor ABS contra uno de
                # temperatura, y una ficha de 4 vías contra una de 2. Todos comparten la primera
                # palabra y el auto, y son piezas distintas.
                # Se midió: sin esto, de cada diez propuestas acertaba dos; con esto, nueve.
                # Se comparan las primeras palabras de cada descripción —las que nombran la
                # pieza, antes de que empiece a listar autos— y se pide que sean casi las mismas.
                if _parecido_nombre_pieza(prod_a["descripcion"], prod_b["descripcion"]) < 0.5:
                    continue
                # Acá el AUTO no puede faltar, y esto también es propio de este recorrido.
                # firmas_compatibles() exige que coincidan solo cuando las DOS descripciones
                # nombran alguno: si una no nombra ninguno, deja pasar, porque no se puede
                # descartar por falta de dato. Comparando de a dos proveedores eso está bien.
                # Acá no: el 36% de los productos no nombra ninguna marca de auto, así que esa
                # excepción se aplicaba a un tercio del catálogo y emparejaba por el nombre de
                # la pieza sola. De ahí salía un «SENSOR ABS» de VW Golf contra uno de BMW X5.
                # Con tantos pares candidatos, "no hay dato" tiene que ser un no.
                if not (firma_a["autos"] and firma_b["autos"] and (firma_a["autos"] & firma_b["autos"])):
                    continue
                salida.append({
                    "Código A": prod_a["codigo_raw"], "Marca A": prod_a["marca"],
                    "Descripción A": (prod_a["descripcion"] or "")[:44],
                    "Código B": prod_b["codigo_raw"], "Marca B": prod_b["marca"],
                    "Descripción B": (prod_b["descripcion"] or "")[:44],
                    "Rubro": firma_a["familia"], "Por qué": motivo,
                    "_a": a, "_b": b,
                    # Para poder mostrar primero lo mejor. Se calcula acá, que es donde las dos
                    # firmas ya están a mano: pedirlas de vuelta al final costaría el doble.
                    "_fuerza": fuerza_de_la_coincidencia(firma_a, firma_b),
                })
    # Se ordena ANTES de cortar. Cortando al llegar al tope, lo que quedaba afuera no eran los
    # peores: eran los que el recorrido del índice tocaba último, o sea cualquiera.
    return _mejores_primero(salida)[:limite]


def _primera_en_comun(rangos_a, rangos_b):
    """El primer número que está en las dos listas ordenadas. Ver sugerir_entre_todas_las_marcas()."""
    i = j = 0
    while i < len(rangos_a) and j < len(rangos_b):
        if rangos_a[i] == rangos_b[j]:
            return rangos_a[i]
        if rangos_a[i] < rangos_b[j]:
            i += 1
        else:
            j += 1
    return None


def derivar_equivalencias_de_aplicaciones(limite=500, minimo_autos=2, solo_lo_nuevo=False,
                                           tope_segundos=None):
    """Deduce equivalencias cruzando los catálogos de aplicaciones de distintos fabricantes.

    El razonamiento: si NGK dice que su bujía U2003 va en un Palio 1.0 2003-2006, y Bosch dice
    que la suya va en EXACTAMENTE el mismo auto, las dos hacen el mismo trabajo. Son
    equivalentes, y ninguna lista de proveedor te lo iba a decir — es información que sale de
    cruzar dos catálogos que ya tenés.

    Tres condiciones, y las tres importan:
      · MISMO tipo de pieza. Sin esto se cruzaría una bujía con un filtro por ir al mismo auto,
        que es exactamente el error que venimos limpiando.
      · Fabricantes DISTINTOS. Dos códigos de la misma marca para el mismo auto suelen ser
        variantes (la común y la de platino), no equivalentes entre sí.
      · Coincidir en varios autos, no en uno. Una coincidencia suelta puede ser casualidad;
        que dos códigos vayan juntos en varios modelos ya es un patrón.

    Y DOS MÁS QUE HACEN FALTA DESDE QUE LAS APLICACIONES SE DEDUCEN DE LAS DESCRIPCIONES.
    Antes esta tabla se llenaba solo con el catálogo que mandaba un fabricante —unos cientos de
    filas— y ahora se llena leyendo las 70.888 descripciones, o sea 52.534 aplicaciones. Con
    eso, «mismo tipo de pieza y mismo auto» deja de alcanzar:
      · el «fabricante» no puede ser OEM / FABRICA. Esa marca no es el catálogo de nadie: son
        los códigos de fábrica que la app dedujo, y cruzarlos por aplicación propone el mismo
        vínculo que ya hace el puente por código, pero sin la certeza del número.
      · el tipo de pieza que se guarda es la FAMILIA (21 en total), así que «misma familia y
        mismo auto» mete en la misma bolsa todas las sondas lambda de ese auto — que se
        diferencian en los cables, el largo y la ficha. Se le pide además que las dos
        descripciones se parezcan, con el mismo criterio de siempre.
    Medido sobre el catálogo real: 32.768 candidatos, 1.987 al sacar los de OEM / FABRICA y
    146 al pedirles además que las descripciones coincidan. Lo que se va es justo eso: cinco
    sondas lambda distintas colgadas del mismo código de Bosch por ir a los mismos 13 autos.

    No las carga: las deja como pendientes para que pasen por la misma revisión que el resto.

    SOLO LO NUEVO (solo_lo_nuevo=True), que es como corre solo después de cada importación.
    El cruce es de todos contra todos dentro de cada auto, así que crece con el CUADRADO del
    catálogo: hoy son 53 millones de combinaciones, y con 60 proveedores serían 1.800 millones
    —«FORD FIESTA» sola tendría 12.000 filas—. Medido así, el paso no terminó en 12 minutos
    y trababa todo lo que venía después. Y encima era trabajo tirado: repetido entero devuelve
    los mismos mejores pares, que ya estaban en revisión. Ahora cruza solo los códigos con
    aplicaciones nuevas, o que llegaron en productos nuevos, contra todo el resto; el botón de
    Administrar sigue haciendo el cruce entero.

    tope_segundos corta la consulta si se pasa (devuelve [] y lo anota): un solo SELECT no se
    puede frenar desde afuera, y el presupuesto de la tanda solo se mira ENTRE pasos."""
    desde_aplic = desde_prod = 0
    hasta_aplic = c.execute("SELECT COALESCE(MAX(id), 0) FROM aplicaciones").fetchone()[0]
    hasta_prod = c.execute("SELECT COALESCE(MAX(id), 0) FROM productos").fetchone()[0]
    if solo_lo_nuevo:
        desde_aplic = int(obtener_config("aplicaciones_cruzadas_hasta", "0") or 0)
        desde_prod = int(obtener_config("productos_cruzados_por_auto_hasta", "0") or 0)
        if desde_aplic >= hasta_aplic and desde_prod >= hasta_prod:
            return []
    # La primera vez (sin marca) es el cruce entero, como el botón.
    incremental = solo_lo_nuevo and (desde_aplic or desde_prod)
    filtro_nuevos = ("""AND a.codigo_clean IN (
                            SELECT codigo_clean FROM aplicaciones WHERE id > ?
                            UNION SELECT codigo_clean FROM productos WHERE id > ?)"""
                     if incremental else "")
    orden = "a.codigo_clean <> b.codigo_clean" if incremental else "a.codigo_clean < b.codigo_clean"
    parametros = (([desde_aplic, desde_prod] if incremental else [])
                  + [minimo_autos, limite * 4 if incremental else limite])
    try:
        with consulta_con_tope(tope_segundos):
            candidatos = _candidatos_por_auto(filtro_nuevos, orden, parametros)
    except sqlite3.OperationalError as _err:
        if "interrupt" not in str(_err).lower():
            raise
        anotar_error("derivar_equivalencias_de_aplicaciones/tope", _err)
        candidatos = None
    if solo_lo_nuevo:
        # También si se cortó: si no, cada tanda volvería a intentar el mismo cruce entero,
        # gastaría el tope completo y se cortaría otra vez, para siempre. Lo que quedó sin
        # cruzar lo hace el botón de Administrar.
        guardar_config("aplicaciones_cruzadas_hasta", str(hasta_aplic))
        guardar_config("productos_cruzados_por_auto_hasta", str(hasta_prod))
    if candidatos is None:
        return []
    if incremental:
        # El par (a, b) y el (b, a) salen los dos cuando los dos códigos son nuevos.
        vistos, unicos = set(), []
        for x in candidatos:
            clave = tuple(sorted((x["cod_a"], x["cod_b"])))
            if clave not in vistos:
                vistos.add(clave)
                unicos.append(x)
        candidatos = unicos[:limite]
    return _equivalencias_de_candidatos_por_auto(candidatos)


def _candidatos_por_auto(filtro_nuevos, orden, parametros):
    """El cruce de aplicaciones: ver derivar_equivalencias_de_aplicaciones()."""
    c.execute(f"""SELECT a.codigo_clean AS cod_a, a.marca_repuesto AS marca_a,
                        b.codigo_clean AS cod_b, b.marca_repuesto AS marca_b,
                        COUNT(DISTINCT a.marca_auto || '|' || a.modelo_auto || '|' || a.motor) AS autos
                 FROM aplicaciones a
                 JOIN aplicaciones b
                   ON a.marca_auto = b.marca_auto
                  AND a.modelo_auto = b.modelo_auto
                  -- EL MOTOR CONTRADICE SOLO SI LOS DOS LO SABEN, igual que las medidas
                  -- físicas. Con `a.motor = b.motor` a secas, llenar esta columna EMPEORA las
                  -- cosas en vez de mejorarlas: el que declara su motor deja de cruzar con el
                  -- que no lo declara, y son la enorme mayoría. Medido al agregar el lector de
                  -- motores —4.880 filas de 112.764 quedaron con motor—: con la comparación
                  -- estricta se pierden 84.862 pares candidatos que antes cruzaban bien, sin
                  -- ganar nada a cambio. Un dato parcial comparado por igualdad estricta es
                  -- peor que no tener el dato.
                  -- …y tampoco contradice si alguna lista declara que esos dos motores se
                  -- llevan para ESTE tipo de pieza. Las bujías del TU5JP4 y las del EW10 son
                  -- las mismas y cada proveedor escribe los motores que se le ocurren; sin
                  -- esta excepción el veto separaba piezas que sí se reemplazan.
                  -- Ver aprender_motores_que_van_juntos().
                  AND (a.motor = b.motor OR COALESCE(a.motor,'') = ''
                       OR COALESCE(b.motor,'') = ''
                       OR EXISTS (SELECT 1 FROM motores_compatibles mc
                                  WHERE mc.tipo_pieza = COALESCE(a.tipo_pieza,'')
                                    AND mc.motor_a = MIN(a.motor, b.motor)
                                    AND mc.motor_b = MAX(a.motor, b.motor)))
                  -- El combustible, por el mismo motivo que el motor: una pieza del 1.6 nafta
                  -- no entra en el 1.9 diesel aunque el auto se llame igual. Con COALESCE
                  -- porque las filas viejas lo tienen en NULL y en SQL dos NULL nunca son
                  -- iguales: sin esto, esas filas dejarían de cruzarse entre ellas.
                  AND COALESCE(a.combustible,'') = COALESCE(b.combustible,'')
                  -- Igualdad directa y no con COALESCE: a.tipo_pieza nunca es vacío (ver el
                  -- WHERE), así que da lo mismo, y así usa idx_aplic_auto_pieza y solo cruza
                  -- piezas del mismo tipo. Son 14 veces menos combinaciones que recorrer.
                  AND b.tipo_pieza = a.tipo_pieza
                  AND a.marca_repuesto <> b.marca_repuesto
                  AND {orden}
                 WHERE COALESCE(a.tipo_pieza,'') <> ''
                   AND a.marca_repuesto <> 'OEM / FABRICA'
                   AND b.marca_repuesto <> 'OEM / FABRICA'
                   {filtro_nuevos}
                 GROUP BY a.codigo_clean, b.codigo_clean
                 HAVING autos >= ?
                 ORDER BY autos DESC LIMIT ?""", parametros)
    return filas_a_listas(c)


def _equivalencias_de_candidatos_por_auto(candidatos):
    """Los candidatos del cruce, llevados a productos del catálogo y filtrados por descripción."""

    # Solo sirven los que además existen en el catálogo propio: proponer una equivalencia entre
    # dos códigos que no tenés cargados no le sirve a nadie.
    # Los productos se buscan de a tandas y no de a uno: eran dos consultas por candidato, o
    # sea 65.536 consultas sobre los 32.768 candidatos del catálogo real.
    codigos = sorted({x["cod_a"] for x in candidatos} | {x["cod_b"] for x in candidatos})
    productos = {}
    for tanda, marcadores in en_tandas(codigos):
        c.execute(f"""SELECT p.id, p.codigo_raw, p.codigo_clean, p.descripcion,
                             m.nombre AS marca, m.tipo
                      FROM productos p JOIN marcas m ON m.id = p.marca_id
                      WHERE p.codigo_clean IN ({marcadores})""", tanda)
        for fila in c.fetchall():
            productos.setdefault(fila["codigo_clean"], dict(fila))

    _cuenta_pal, _total_desc = cuantas_veces_aparece_cada_palabra()
    firmas = {}

    def _firma(prod):
        if prod["id"] not in firmas:
            firmas[prod["id"]] = firma_de_producto(prod["descripcion"], prod["id"],
                                                    prod["codigo_clean"])
        return firmas[prod["id"]]

    salida = []
    for x in candidatos:
        pa, pb = productos.get(x["cod_a"]), productos.get(x["cod_b"])
        if not pa or not pb or pa["id"] == pb["id"]:
            continue
        if "OEM" in (pa["tipo"], pb["tipo"]):
            continue
        # Que además las descripciones digan que es la misma pieza. Ver el docstring: la
        # familia sola mete en la misma bolsa cinco sondas distintas del mismo auto.
        ok, _motivo = firmas_compatibles(_firma(pa), _firma(pb),
                                         cuenta_palabras=_cuenta_pal,
                                         total_descripciones=_total_desc)
        if not ok:
            continue
        salida.append({
            "Código A": pa["codigo_raw"], "Marca A": pa["marca"],
            "Código B": pb["codigo_raw"], "Marca B": pb["marca"],
            "Coinciden en": f"{x['autos']} auto(s)",
            "Según": f"{x['marca_a']} y {x['marca_b']}",
            "_a": pa["id"], "_b": pb["id"],
        })
    return salida


def guardar_equivalencias_derivadas(pares, lote):
    """Deja las equivalencias deducidas como PENDIENTES, no cargadas.

    A propósito: por más buena que sea la deducción, sigue siendo una deducción. Pasa por la
    misma revisión que todo lo demás, y ahí el sistema de confianza la evalúa como a cualquier
    otra."""
    # Esta era la única de las dos que ya miraba los rechazos y ordenaba el par. Ahora las dos
    # pasan por el mismo lugar, que además descarta lo que ya está cargado.
    return guardar_equivalencias_pendientes(pares, "catalogos_fabricante", lote)

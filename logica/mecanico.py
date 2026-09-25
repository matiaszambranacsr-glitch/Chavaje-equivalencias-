"""Modo mecánico: códigos OBD2, lector de VIN y visor de esquemas.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================
# MODO MECÁNICO — DICCIONARIO DE CÓDIGOS OBD2 / DTC
# ============================================================
def buscar_dtc(codigo, fabricante_filtro="Todos"):
    codigo = codigo.strip().upper()
    query = """SELECT codigo AS "Código",
               CASE WHEN fabricante = '' THEN 'Genérico' ELSE fabricante END AS "Fabricante",
               descripcion AS "Descripción", sistema AS "Sistema",
               causas_posibles AS "Causas posibles" FROM codigos_dtc
               WHERE (codigo = ? OR codigo LIKE ?)"""
    params = [codigo, f"%{codigo}%"]
    if fabricante_filtro == "Genérico":
        query += " AND fabricante = ''"
    elif fabricante_filtro and fabricante_filtro != "Todos":
        query += " AND fabricante = ?"
        params.append(fabricante_filtro)
    query += " ORDER BY fabricante, codigo"
    c.execute(query, params)
    return filas_a_listas(c)


# Las piezas que nombra un código de falla. Es el vocabulario del catálogo, no una lista nueva:
# se buscan estas palabras en el texto del código y de sus causas, y con eso se busca en las
# descripciones de los productos.
PIEZAS_QUE_NOMBRA_UN_DTC = {
    "BUJIA": ("BUJIA", "BUJIAS"),
    # «CABLE» solo no sirve: «cableado cortado o en corto» es la causa de CASI TODOS los
    # códigos eléctricos del diccionario, así que cualquier falla del ventilador o del pedal
    # terminaba ofreciendo cables de bujía. El cable de bujía se nombra con las dos palabras.
    "CABLE DE BUJIA": ("CABLE DE BUJIA", "CABLES DE BUJIA", "CABLE DE ENCENDIDO"),
    "BOBINA": ("BOBINA",),
    "INYECTOR": ("INYECTOR",),
    "SONDA LAMBDA": ("SONDA", "LAMBDA", "OXIGENO"),
    "SENSOR DE DETONACION": ("DETONACION",),
    "SENSOR DE ROTACION / CIGÜEÑAL": ("ROTACION", "CIGUENAL"),
    "SENSOR DE ARBOL DE LEVAS": ("LEVAS", "FASE"),
    "SENSOR MAP": ("MAP",),
    "SENSOR DE MASA DE AIRE": ("MASA DE AIRE", "MAF", "CAUDALIMETRO"),
    "SENSOR DE TEMPERATURA": ("TEMPERATURA",),
    "CUERPO DE MARIPOSA": ("MARIPOSA",),
    "VALVULA EGR": ("EGR",),
    "VALVULA CANISTER / EVAP": ("CANISTER", "EVAP", "PURGA"),
    "TERMOSTATO": ("TERMOSTATO",),
    "BOMBA DE COMBUSTIBLE": ("BOMBA DE COMBUSTIBLE", "BOMBA DE NAFTA"),
    "FILTRO DE COMBUSTIBLE": ("FILTRO DE COMBUSTIBLE", "FILTRO DE NAFTA"),
    "CATALIZADOR": ("CATALIZADOR",),
    # «VELOCIDAD» sola trae las cajas de velocidad, así que va la frase entera.
    "SENSOR DE VELOCIDAD / ABS": ("ABS", "SENSOR DE VELOCIDAD"),
    "SENSOR DE PRESION DE ACEITE": ("PRESION DE ACEITE",),
    "MOTOR PASO A PASO": ("PASO A PASO", "RALENTI"),
    "SOLENOIDE DE CAJA": ("SOLENOIDE",),
    # Las que entraron con los códigos nuevos. Cada palabra está elegida contra el catálogo
    # real, no por lo que suena bien: «TURBO» y «COMPRESOR» se probaron y quedaron afuera
    # porque traían 965 y 324 productos que no son la pieza (las aplicaciones dicen «2.0 TD» y
    # hay caños «al turbocompresor»). «DISTRIBUCION» en cambio trae los 603 kits y nada más.
    "KIT DE DISTRIBUCION": ("DISTRIBUCION",),
    "BUJIA INCANDESCENTE": {"dtc": ("BUJIA INCANDESCENTE", "INCANDESCENTE"),
                            "catalogo": ("INCANDESCENTE",)},
    "ELECTROVENTILADOR": ("ELECTROVENTILADOR",),
    "ALTERNADOR": ("ALTERNADOR",),
    "BOMBA DE AGUA": ("BOMBA DE AGUA",),
    "FILTRO DE AIRE": ("FILTRO DE AIRE",),
    # Acá el código y el catálogo no se llaman igual: la norma dice «ventilador del radiador»
    # (P0480) y el mostrador lo pide como «electroventilador». Cuando pasa eso, van separadas
    # las palabras que hay que leer EN EL CÓDIGO y las que hay que buscar EN EL CATÁLOGO —
    # «VENTILADOR» a secas trae 253 productos que no son eso.
    "ELECTROVENTILADOR": {"dtc": ("ELECTROVENTILADOR", "VENTILADOR DEL RADIADOR",
                                  "VENTILADOR DE ENFRIAMIENTO"),
                          "catalogo": ("ELECTROVENTILADOR",)},
}


# Con qué arranca la descripción de un ACCESORIO de la pieza, que no es la pieza. La junta de
# la tapa de distribución nombra la distribución, pero al que le saltó un P0016 hay que
# venderle el kit. Antes salían primero las juntas porque la regla era «la palabra aparece en
# los primeros 12 caracteres», y «JUNTA DISTRIBUCION» la cumple igual que «KIT DE DISTRIBUCION».
# No se esconden —a veces la junta es justo lo que falta— pero van después.
_ACCESORIO_DE_LA_PIEZA = ("JUNTA", "JUNTAS", "JTA", "JTAS", "EMPAQUETADURA", "ARANDELA",
                          "ARANDELAS", "ARAND", "TORNILLO", "BULON", "TUERCA", "CANO",
                          "MANGUERA", "FICHA", "RETEN", "RTEN", "RESORTE", "CHAVETA", "SOPORTE",
                          "ACCESORIO", "PRECINTO", "ABRAZADERA", "GRAMPA", "TAPA", "CAPUCHON",
                          "PERNO", "SEPARADOR", "BUJE", "DESPIECE", "KIT DE JUNTAS",
                          "GUARNICION", "O'RING", "ORING", "JGO", "JUEGO DE JUNTAS", "TAPON",
                          "VALVULA DE PURGA DE JUNTA")
# Se mira el ARRANQUE de la descripción y no la primera palabra cortada por espacios, porque
# muchas listas escriben «Jta.Distribucion» y «ARAND. ASIENTO INYECTOR» todo pegado.
_RE_ACCESORIO = re.compile(r'(' + "|".join(sorted(_ACCESORIO_DE_LA_PIEZA, key=len, reverse=True))
                           + r')(?![A-Z])')


def repuestos_para_el_dtc(codigo, marca_auto="", modelo="", limite=8):
    """Qué de lo que TENÉS puede arreglar ese código de falla.

    El diccionario de códigos decía qué significa la falla y ahí terminaba: el que atiende leía
    «fallo de encendido en el cilindro 6 — bujía, bobina, inyector» y tenía que ir a buscar cada
    una de esas piezas al buscador, a mano, una por una.

    Esto lo hace solo. No es una base nueva ni una consulta paga: son las palabras del propio
    código cruzadas con las descripciones del catálogo que ya está cargado. Si además se sabe
    el auto, se filtra por eso.

    Devuelve [{pieza, productos:[...]}] ordenado por lo que más probablemente sea."""
    filas = buscar_dtc(codigo)
    if not filas:
        return []
    texto = normalizar_texto(" ".join(
        f"{f.get('Descripción') or ''} {f.get('Causas posibles') or ''}" for f in filas))

    salida = []
    for nombre_pieza, _config in PIEZAS_QUE_NOMBRA_UN_DTC.items():
        # Casi siempre el código y el catálogo usan las mismas palabras y alcanza con una lista.
        palabras_dtc = _config["dtc"] if isinstance(_config, dict) else _config
        palabras = _config["catalogo"] if isinstance(_config, dict) else _config
        # Como PALABRA y no como subcadena: «CABLE» está adentro de «CABLEADO», que es la causa
        # de casi todos los códigos eléctricos, así que buscando la subcadena todos los códigos
        # del diccionario ofrecían cables de bujía.
        if not any(re.search(rf'(?<![A-ZÁÉÍÓÚÑ]){re.escape(normalizar_texto(p))}'
                             rf'(?![A-ZÁÉÍÓÚÑ])', texto)
                   for p in palabras_dtc):
            continue
        condiciones = ["p.descripcion IS NOT NULL", "m.tipo <> 'OEM'"]
        params = []
        # Cualquiera de las formas de nombrar esa pieza: una lista dice SONDA LAMBDA y otra
        # SENSOR DE OXIGENO.
        _trozos, _pars = [], []
        for _pal in palabras:
            _cond, _par = like_en_descripcion(f"%{normalizar_texto(_pal)}%")
            _trozos.append(f"({_cond})")
            _pars.extend(_par)
        condiciones.append("(" + " OR ".join(_trozos) + ")")
        params.extend(_pars)
        for _texto in (marca_auto, modelo):
            if _texto:
                _cond, _par = like_en_descripcion(f"%{normalizar_texto(_texto)}%")
                condiciones.append(_cond)
                params.extend(_par)
        try:
            c.execute(f"""SELECT p.codigo_raw AS "Código", m.nombre AS "Marca",
                                 p.descripcion AS "Descripción", p.precio AS "Precio",
                                 p.stock AS "Stock"
                          FROM productos p JOIN marcas m ON m.id = p.marca_id
                          WHERE {" AND ".join(condiciones)}
                          ORDER BY (p.stock IS NULL OR p.stock <= 0), p.precio
                          LIMIT ?""", params + [limite * 12])
            productos = filas_a_listas(c)
        except sqlite3.OperationalError as _err:
            anotar_error("repuestos_para_el_dtc", _err)
            continue
        # Lo mismo del lado del catálogo, y además primero lo que EMPIEZA con esa palabra: en
        # una descripción el nombre de la pieza va adelante, así que «BUJIA NGK FIAT PALIO» es
        # una bujía y «ARANDELA CAPUCHON BUJIAS» es otra cosa que la nombra.
        _patrones = [re.compile(rf'(?<![A-ZÁÉÍÓÚÑ]){re.escape(normalizar_texto(p))}'
                                rf'(?![A-ZÁÉÍÓÚÑ])') for p in palabras]
        _filtrados = []
        for prod in productos:
            _desc_norm = normalizar_texto(prod.get("Descripción") or "")
            _m = next((pat.search(_desc_norm) for pat in _patrones if pat.search(_desc_norm)), None)
            if _m:
                # Tres escalones y no dos: la palabra al principio de todo («BOMBA DE
                # COMBUSTIBLE …») antes que la palabra adentro de otro nombre («FILTRO BOMBA DE
                # COMBUSTIBLE»), y esa antes que la que aparece al final, en las aplicaciones
                # («TERMOSTATO ASTRA … catalizador», que no es un catalizador).
                prod["_al_principio"] = 0 if _m.start() == 0 else (1 if _m.start() <= 12 else 2)
                prod["_accesorio"] = bool(_RE_ACCESORIO.match(_desc_norm))
                _filtrados.append(prod)
        # Se piden doce veces más filas de las que se van a mostrar y se corta DESPUÉS de
        # ordenar. Es la diferencia entre mostrar la pieza y mostrar su junta: el SQL ordena por
        # precio, la junta siempre sale más barata que la pieza, y con el LIMIT puesto en la
        # consulta las ocho filas que llegaban eran ocho juntas — la pieza de verdad no entraba
        # nunca. Un P0016 ofrecía un o-ring de la tapa en vez del kit de distribución.
        _filtrados.sort(key=lambda x: (x.pop("_al_principio"),
                                        bool(x.pop("_accesorio")),
                                        (x.get("Stock") or 0) <= 0))
        _filtrados = _filtrados[:limite]
        if _filtrados:
            # Dónde nombra el código a esta pieza. El texto arranca con la descripción de la
            # falla y sigue con las causas escritas de la más probable a la menos; ordenar por
            # esa posición pone arriba lo que hay que cambiar primero. Antes el orden era el
            # del diccionario, que no quiere decir nada: un P0016 mostraba dos sensores antes
            # que el kit de distribución.
            _hallados = [(m.start(), m.end() - m.start()) for m in
                         (re.search(rf'(?<![A-ZÁÉÍÓÚÑ]){re.escape(normalizar_texto(w))}'
                                    rf'(?![A-ZÁÉÍÓÚÑ])', texto) for w in palabras_dtc) if m]
            _donde = min((h[0] for h in _hallados), default=10 ** 6)
            # Cuál es el nombre más largo que enganchó, para desempatar. «Bujía incandescente»
            # y «bujía» arrancan en el mismo lugar del texto, y a un código de precalentamiento
            # hay que ofrecerle la incandescente primero, no las bujías de nafta.
            _largo = max((h[1] for h in _hallados if h[0] == _donde), default=0)
            salida.append({"pieza": nombre_pieza, "productos": _filtrados,
                            "_donde": _donde, "_largo": _largo})
    salida.sort(key=lambda x: (x["_donde"], -x["_largo"]))
    for _g in salida:
        _g.pop("_donde", None)
        _g.pop("_largo", None)
    return salida


def agregar_dtc(codigo, descripcion, sistema, causas, fabricante=""):
    codigo = codigo.strip().upper()
    fabricante = fabricante.strip()
    with db_lock:
        # editado = 1: lo que se carga o corrige desde la app queda protegido de la semilla.
        c.execute(
            "INSERT INTO codigos_dtc (codigo, fabricante, descripcion, sistema, causas_posibles, "
            "editado) VALUES (?, ?, ?, ?, ?, 1) "
            "ON CONFLICT(codigo, fabricante) DO UPDATE SET descripcion=excluded.descripcion, "
            "sistema=excluded.sistema, causas_posibles=excluded.causas_posibles, editado=1",
            (codigo, fabricante, descripcion.strip(), sistema.strip(), causas.strip())
        )
        conn.commit()


def importar_dtc_masivo(texto):
    """Importa códigos DTC pegados como texto, una línea por código:
    codigo;descripcion;sistema;causas;fabricante (fabricante es opcional, vacío = código genérico)."""
    cargados = 0
    with db_lock:
        for linea in texto.strip().splitlines():
            partes = [p.strip() for p in linea.split(";")]
            if len(partes) < 2 or not partes[0]:
                continue
            codigo = partes[0].upper()
            descripcion = partes[1]
            sistema = partes[2] if len(partes) > 2 else ""
            causas = partes[3] if len(partes) > 3 else ""
            fabricante = partes[4] if len(partes) > 4 else ""
            c.execute(
                "INSERT INTO codigos_dtc (codigo, fabricante, descripcion, sistema, "
                "causas_posibles, editado) VALUES (?, ?, ?, ?, ?, 1) "
                "ON CONFLICT(codigo, fabricante) DO UPDATE SET descripcion=excluded.descripcion, "
                "sistema=excluded.sistema, causas_posibles=excluded.causas_posibles, editado=1",
                (codigo, fabricante, descripcion, sistema, causas)
            )
            cargados += 1
        conn.commit()
    return cargados


def contar_dtc():
    c.execute("SELECT COUNT(*) FROM codigos_dtc")
    return c.fetchone()[0]


def listar_fabricantes_dtc():
    c.execute("SELECT DISTINCT fabricante FROM codigos_dtc WHERE fabricante != '' ORDER BY fabricante")
    return [r["fabricante"] for r in c.fetchall()]


# ============================================================
# MODO MECÁNICO — LECTOR DE VIN
# ============================================================
# Primer carácter del VIN = región/país de fabricación (estándar ISO 3779, dato genérico).
PAISES_VIN = {
    # Primer carácter del VIN = región. Es lo más grueso; abajo se afina con dos caracteres.
    "1": "Estados Unidos", "4": "Estados Unidos", "5": "Estados Unidos",
    "2": "Canadá", "3": "México / Centroamérica",
    "6": "Australia / Oceanía", "7": "Nueva Zelanda / Oceanía",
    "8": "Sudamérica", "9": "Brasil / Sudamérica", "0": "Sudamérica",
    "A": "África", "B": "África", "C": "África", "D": "África", "E": "África",
    "F": "África", "G": "África", "H": "África",
    "J": "Japón", "K": "Corea del Sur", "L": "China", "M": "India / Asia del Sur",
    "N": "Turquía / Asia occidental", "P": "Filipinas / Asia", "R": "Taiwán / Asia",
    "S": "Reino Unido", "T": "Europa central", "U": "Europa del este",
    "V": "Francia / España", "W": "Alemania", "X": "Rusia / Europa del este",
    "Y": "Suecia / Finlandia", "Z": "Italia",
}
# Con los DOS primeros caracteres se distingue mucho mejor: "8" solo dice Sudamérica, pero
# "8A" es Argentina y "8B" Chile. Se usa esto primero y, si no está, se cae al de una letra.
PAISES_VIN_2 = {
    # --- Sudamérica ---
    "8A": "Argentina", "8B": "Argentina", "8C": "Argentina", "8D": "Argentina",
    "8E": "Argentina",
    "8F": "Chile", "8G": "Chile", "8H": "Chile", "8J": "Chile",
    "8K": "Ecuador", "8L": "Ecuador", "8M": "Ecuador",
    "8S": "Perú", "8T": "Perú",
    "8X": "Venezuela", "8Y": "Venezuela", "8Z": "Venezuela",
    "9A": "Brasil", "9B": "Brasil", "9C": "Brasil", "9D": "Brasil", "9E": "Brasil",
    "93": "Brasil", "94": "Brasil", "95": "Brasil", "96": "Brasil", "97": "Brasil",
    "98": "Brasil", "99": "Brasil",
    "9F": "Colombia", "9G": "Colombia", "9H": "Colombia",
    "9L": "Paraguay", "9M": "Paraguay",
    "9U": "Uruguay", "9V": "Uruguay",
    "9X": "Venezuela",
    # --- Norteamérica ---
    "1G": "Estados Unidos", "1F": "Estados Unidos", "2F": "Canadá", "2G": "Canadá",
    "3F": "México", "3G": "México", "3N": "México", "3V": "México",
    # --- Europa ---
    "SA": "Reino Unido", "SB": "Reino Unido", "SC": "Reino Unido", "SD": "Reino Unido",
    "SE": "Reino Unido", "SF": "Reino Unido", "SH": "Reino Unido", "SJ": "Reino Unido",
    "SK": "Reino Unido", "SL": "Reino Unido", "SM": "Reino Unido",
    "SU": "Polonia", "SN": "Alemania (este)",
    "TM": "República Checa", "TN": "República Checa", "TR": "Hungría", "TS": "Hungría",
    "TW": "Portugal", "TY": "Portugal", "TC": "Suiza", "TD": "Suiza",
    "UU": "Rumania", "U5": "Eslovaquia", "U6": "Eslovaquia",
    "VA": "Austria", "VN": "Francia", "VF": "Francia", "VG": "Francia", "VL": "Francia",
    "VS": "España", "VT": "España", "VV": "España", "VW": "España", "VX": "Serbia",
    "WA": "Alemania", "WB": "Alemania", "WD": "Alemania", "WE": "Alemania",
    "WF": "Alemania", "WJ": "Alemania", "WM": "Alemania", "WP": "Alemania",
    "WU": "Alemania", "WV": "Alemania", "W0": "Alemania",
    "XL": "Países Bajos", "XM": "Países Bajos", "XT": "Rusia", "XU": "Rusia",
    "XW": "Rusia / Uzbekistán", "X4": "Rusia", "X7": "Rusia",
    "YB": "Bélgica", "YC": "Bélgica", "YE": "Bélgica",
    "YK": "Finlandia", "YS": "Suecia", "YT": "Suecia", "YV": "Suecia", "Y6": "Ucrania",
    "ZA": "Italia", "ZB": "Italia", "ZC": "Italia", "ZD": "Italia", "ZF": "Italia",
    "ZG": "Italia", "ZH": "Italia", "ZJ": "Italia", "ZK": "Italia", "ZL": "Italia",
    "ZO": "Italia",
    # --- Asia ---
    "JA": "Japón", "JD": "Japón", "JF": "Japón", "JH": "Japón", "JK": "Japón",
    "JL": "Japón", "JM": "Japón", "JN": "Japón", "JS": "Japón", "JT": "Japón",
    "JY": "Japón",
    "KL": "Corea del Sur", "KM": "Corea del Sur", "KN": "Corea del Sur",
    "KP": "Corea del Sur",
    "LA": "China", "LB": "China", "LC": "China", "LD": "China", "LE": "China",
    "LF": "China", "LG": "China", "LH": "China", "LJ": "China", "LK": "China",
    "LL": "China", "LM": "China", "LP": "China", "LS": "China", "LT": "China",
    "LU": "China", "LV": "China", "LZ": "China", "L4": "China", "L5": "China",
    "MA": "India", "MB": "India", "MC": "India", "MD": "India", "ME": "India",
    "MH": "Indonesia", "MJ": "Indonesia", "ML": "Tailandia", "MM": "Tailandia",
    "MN": "Tailandia", "MP": "Tailandia", "MR": "Tailandia",
    "NL": "Turquía", "NM": "Turquía", "NA": "Irán", "NC": "Turquía",
    "PE": "Filipinas", "PL": "Malasia", "PN": "Malasia", "PP": "Singapur",
    "RF": "Taiwán", "RA": "Taiwán", "RL": "Taiwán",
    # --- África y Oceanía ---
    "AA": "Sudáfrica", "AC": "Sudáfrica", "AD": "Sudáfrica", "AF": "Sudáfrica",
    "AH": "Sudáfrica",
    "6A": "Australia", "6F": "Australia", "6G": "Australia", "6H": "Australia",
    "6M": "Australia", "6T": "Australia", "6U": "Australia",
    "7A": "Nueva Zelanda",
}
# Código de año en la 10ª posición del VIN (estándar, cíclico cada 30 años).
ANIOS_VIN = {
    "A": 1980, "B": 1981, "C": 1982, "D": 1983, "E": 1984, "F": 1985, "G": 1986, "H": 1987,
    "J": 1988, "K": 1989, "L": 1990, "M": 1991, "N": 1992, "P": 1993, "R": 1994, "S": 1995,
    "T": 1996, "V": 1997, "W": 1998, "X": 1999, "Y": 2000,
    "1": 2001, "2": 2002, "3": 2003, "4": 2004, "5": 2005, "6": 2006, "7": 2007, "8": 2008, "9": 2009,
}


# Para el dígito verificador del VIN: cada letra vale un número. No es arbitrario, es la norma
# ISO 3779 y es igual en todo el mundo.
_VALOR_LETRA_VIN = {
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
    "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7, "R": 9,
    "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9,
}
_PESOS_VIN = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)


def corregir_confusiones_vin(vin):
    """Arregla las letras que un VIN NO puede tener. Devuelve (corregido, qué se cambió).

    La norma prohíbe I, O y Q justamente porque se confunden con 1 y 0. Así que si alguien
    escribió una, es seguro que copió mal: no hay ambigüedad posible.

    Antes la app rechazaba el VIN y listo. Pero el VIN se copia a mano de una chapita, y ese
    es el error más común que existe: rechazarlo obliga a tipear todo de nuevo sin decir dónde
    estaba el problema."""
    original = re.sub(r"[\s\-]", "", (vin or "").strip().upper())
    cambios = []
    salida = []
    for i, ch in enumerate(original):
        if ch == "I":
            salida.append("1"); cambios.append(f"la I de la posición {i+1} → 1")
        elif ch == "O":
            salida.append("0"); cambios.append(f"la O de la posición {i+1} → 0")
        elif ch == "Q":
            salida.append("0"); cambios.append(f"la Q de la posición {i+1} → 0")
        else:
            salida.append(ch)
    return "".join(salida), cambios


def digito_verificador_vin(vin):
    """Calcula qué debería tener el VIN en la posición 9.

    Es una cuenta sobre los otros 16 caracteres. Si no coincide, hay un error de copia en
    alguna parte — y se detecta ANTES de buscar, en vez de dar resultados de otro auto."""
    if len(vin) != 17:
        return None
    total = 0
    for i, ch in enumerate(vin):
        if ch.isdigit():
            valor = int(ch)
        elif ch in _VALOR_LETRA_VIN:
            valor = _VALOR_LETRA_VIN[ch]
        else:
            return None
        total += valor * _PESOS_VIN[i]
    resto = total % 11
    return "X" if resto == 10 else str(resto)


def verificar_vin(vin):
    """¿El VIN está bien copiado? Devuelve (estado, mensaje).

    estado: 'ok', 'mal', o 'no_aplica'.

    IMPORTANTE y por eso no se rechaza sin más: el dígito verificador es **obligatorio en
    Estados Unidos y Canadá** (VIN que empieza con 1 a 5), pero en el resto del mundo es
    opcional y muchísimos fabricantes no lo usan. Un auto brasileño o argentino puede tener un
    VIN perfectamente válido que no pase esta cuenta.

    Por eso: si empieza con 1-5 y no da, es un error de copia casi seguro. Si empieza con otra
    cosa, se avisa y nada más."""
    esperado = digito_verificador_vin(vin)
    if esperado is None:
        return "no_aplica", ""
    real = vin[8]
    if real == esperado:
        return "ok", "El dígito verificador da bien: el VIN está bien copiado."
    norteamericano = vin[0] in "12345"
    if norteamericano:
        return "mal", (f"El dígito verificador no da: la posición 9 dice «{real}» y tendría que "
                       f"decir «{esperado}». En los VIN de Estados Unidos y Canadá este dígito "
                       "es obligatorio, así que hay un carácter mal copiado.")
    return "no_aplica", (f"El dígito verificador no da ({real} en vez de {esperado}), pero fuera "
                         "de Estados Unidos y Canadá muchos fabricantes no lo usan. Puede estar "
                         "perfecto igual — tomalo como una señal para revisar, no como un error.")


URL_VPIC = "https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvalues/{vin}?format=json"


def consultar_vin_en_nhtsa(vin, tiempo_maximo=12):
    """Le pregunta a la base pública de la NHTSA qué auto es ese VIN. (datos, error).

    Es gratis, no pide clave ni registro, y es la base oficial del gobierno de Estados Unidos.
    Resuelve el hueco que la app tenía: el modelo y el motor no están en la norma del VIN, así
    que hasta ahora había que enseñárselos uno por uno.

    Lo que hay que saber antes de confiar: la cobertura es excelente para autos vendidos en
    Estados Unidos y buena para los fabricantes globales, pero **muchos modelos hechos para el
    mercado argentino o brasileño no están**. Un Gol o un Palio pueden volver vacíos. Por eso
    lo que devuelve se ofrece para confirmar, nunca se guarda solo."""
    limpio = re.sub(r"[^A-HJ-NPR-Z0-9]", "", (vin or "").upper())
    if len(limpio) != 17:
        return None, "El VIN tiene que tener 17 caracteres."
    try:
        r = requests.get(URL_VPIC.format(vin=quote(limpio)), timeout=tiempo_maximo,
                         headers={"User-Agent": "EquivalenciasElChavo/1.0"})
        if r.status_code >= 400:
            return None, f"La base de la NHTSA respondió {r.status_code}."
        cuerpo = r.json()
    except Exception as e:
        anotar_error("consultar_vin_en_nhtsa", e)
        return None, f"No se pudo consultar ({type(e).__name__}). Puede ser la conexión."

    filas = (cuerpo or {}).get("Results") or []
    if not filas:
        return None, "La base no devolvió nada para ese VIN."
    d = filas[0]

    def limpiar(clave):
        v = (d.get(clave) or "").strip()
        # La API devuelve textos como "Not Applicable" cuando no sabe: no son datos
        if v.lower() in ("", "not applicable", "0", "null", "none"):
            return ""
        return v

    motor = " ".join(x for x in [
        limpiar("DisplacementL") and f"{limpiar('DisplacementL')}L",
        limpiar("EngineCylinders") and f"{limpiar('EngineCylinders')}cil",
        limpiar("FuelTypePrimary"),
    ] if x)

    datos = {
        "marca": limpiar("Make"),
        "modelo": limpiar("Model"),
        "anio": limpiar("ModelYear"),
        "motor": motor,
        "carroceria": limpiar("BodyClass"),
        "planta": " ".join(x for x in [limpiar("PlantCity"), limpiar("PlantCountry")] if x),
        "fabricante": limpiar("Manufacturer"),
        "aviso": limpiar("ErrorText"),
    }
    if not datos["marca"] and not datos["modelo"]:
        return None, ("La base no conoce ese VIN. Es normal en modelos hechos para "
                      "Sudamérica: la cobertura fuerte es de autos del mercado de "
                      "Estados Unidos.")
    return datos, None


def decodificar_vin(vin):
    vin = re.sub(r'\s', '', vin.strip().upper())
    resultado = {"vin": vin, "valido": False}
    if len(vin) != 17:
        resultado["error"] = "El VIN debe tener 17 caracteres."
        return resultado
    if any(ch in vin for ch in ("I", "O", "Q")):
        # Se corrige en vez de rechazar: esas letras no existen en un VIN, así que quien las
        # escribió copió mal un 1 o un 0. Rechazar obliga a tipear los 17 de nuevo.
        vin, cambios = corregir_confusiones_vin(vin)
        resultado["vin"] = vin
        resultado["corregido"] = cambios

    resultado["valido"] = True
    estado_dv, msg_dv = verificar_vin(vin)
    resultado["digito_verificador"] = estado_dv
    resultado["mensaje_digito"] = msg_dv
    wmi = vin[:3]
    resultado["wmi"] = wmi
    resultado["pais"] = PAISES_VIN_2.get(vin[:2]) or PAISES_VIN.get(vin[0], "Desconocido / no cargado")

    # Primero el WMI exacto de 3; si no está, el prefijo de 2. El orden importa y no es un
    # detalle: 'JA' es Isuzu pero 'JA3' es Mitsubishi, y '1H' es Honda mientras que '1HD' es
    # Harley-Davidson. Si se buscara el prefijo primero, esos casos darían la marca equivocada.
    resultado["fabricante"] = None
    resultado["fabricante_por_prefijo"] = False
    for clave, es_prefijo in ((wmi, False), (wmi[:2], True)):
        c.execute("SELECT fabricante, pais FROM fabricantes_vin WHERE wmi = ?", (clave,))
        fila = c.fetchone()
        if fila:
            resultado["fabricante"] = fila["fabricante"]
            resultado["fabricante_por_prefijo"] = es_prefijo
            if fila["pais"]:
                resultado["pais"] = fila["pais"]
            break

    # --- Modelo: NO sale del VIN, sale de lo que se haya enseñado ---
    # Las posiciones 4-8 (VDS) las define cada fabricante a su gusto, no hay norma que diga qué
    # significan. Así que se busca el patrón exacto y, si no está, uno más corto (4-7 y 4-6):
    # muchos fabricantes usan los primeros caracteres para la carrocería y los últimos para el
    # motor o el equipamiento, así que un patrón corto suele acertar la familia del modelo.
    vds = vin[3:8]
    resultado["vds"] = vds
    resultado["modelo"] = None
    resultado["modelo_exacto"] = False
    resultado["motor"] = None
    resultado["motor_origen"] = None
    for largo in (5, 4, 3):
        c.execute("SELECT vds, modelo, motor, notas FROM modelos_vin WHERE wmi = ? AND vds = ?",
                  (wmi, vds[:largo]))
        m = c.fetchone()
        if m:
            resultado["modelo"] = m["modelo"]
            resultado["modelo_notas"] = m["notas"]
            resultado["modelo_exacto"] = (largo == 5)
            if m["motor"]:
                resultado["motor"] = m["motor"]
                resultado["motor_origen"] = ("patrón exacto de este modelo" if largo == 5
                                              else "patrón de la familia del modelo")
            break

    # --- Motor por la 8ª posición ---
    # Es la posición que la norma de Norteamérica reserva para el código de motor, y que casi
    # todos los fabricantes usan para lo mismo aunque afuera no sea obligatorio. Generaliza
    # mejor que el modelo: el mismo código suele repetirse en toda la gama de la marca.
    # Solo se usa si el patrón del modelo no trajo ya un motor, que es más específico.
    codigo_motor = vin[7]
    resultado["codigo_motor"] = codigo_motor
    resultado["motor_por_norma"] = vin[0] in "12345"
    if not resultado["motor"]:
        c.execute("SELECT motor, notas FROM motores_vin WHERE wmi = ? AND codigo = ?",
                  (wmi, codigo_motor))
        mm = c.fetchone()
        if mm:
            resultado["motor"] = mm["motor"]
            resultado["motor_notas"] = mm["notas"]
            resultado["motor_origen"] = f"código «{codigo_motor}» en la 8ª posición"

    # --- Año: se puede ser preciso en los VIN de Norteamérica ---
    # El código de la 10ª posición se repite cada 30 años (la "D" sirve para 1983 y 2013).
    # Pero en los VIN emitidos para Norteamérica (país 1 a 5) hay una regla que lo desambigua:
    # si el 7° carácter es LETRA, el vehículo es del ciclo 2010 en adelante; si es NÚMERO, del
    # ciclo 1980-2009. Fuera de Norteamérica esa regla no se aplica (VW, por ejemplo, usa
    # 'ZZZ' en esas posiciones), así que ahí se muestran las dos posibilidades.
    letra_anio = vin[9]
    base_anio = ANIOS_VIN.get(letra_anio)
    resultado["anio_estimado"] = None
    resultado["anio_alternativo"] = None
    resultado["anio_preciso"] = False
    if base_anio:
        tope = datetime.now().year + 1
        es_norteamerica = vin[0] in "12345"
        if es_norteamerica:
            anio = base_anio + 30 if vin[6].isalpha() else base_anio
            if anio <= tope:
                resultado["anio_estimado"] = anio
                resultado["anio_preciso"] = True
        if not resultado["anio_preciso"]:
            candidatos = [a for a in sorted({base_anio, base_anio + 30}) if a <= tope]
            if candidatos:
                resultado["anio_estimado"] = candidatos[-1]
                if len(candidatos) > 1:
                    resultado["anio_alternativo"] = candidatos[0]

    # --- Dígito verificador (9ª posición) ---
    # Obligatorio en Norteamérica: se calcula con el resto del VIN, así que si no coincide es
    # porque hay un carácter mal tipeado. Sirve para no buscar repuestos de un auto equivocado.
    resultado["digito_verificador"] = None
    if vin[0] in "12345":
        valores = {**{str(d): d for d in range(10)},
                   "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
                   "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7, "R": 9,
                   "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9}
        pesos = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]
        try:
            suma = sum(valores[ch] * peso for ch, peso in zip(vin, pesos))
            esperado = "X" if suma % 11 == 10 else str(suma % 11)
            resultado["digito_verificador"] = (vin[8] == esperado)
        except KeyError as _err:
            anotar_error("decodificar_vin", _err)
            resultado["digito_verificador"] = None

    # --- Lo más confiable de todo: que el auto ya esté en una ficha ---
    # Si este VIN exacto ya pasó por el mostrador, no hay nada que estimar: el modelo, el año y
    # el motor son los que cargó una persona mirando el auto. Eso pisa cualquier deducción, y
    # además trae la patente, el dueño y el historial de piezas.
    ficha = buscar_vehiculo_por_vin(vin)
    if ficha:
        resultado["vehiculo"] = ficha
        if ficha.get("modelo_auto"):
            resultado["modelo"] = ficha["modelo_auto"]
            resultado["modelo_exacto"] = True
            resultado["modelo_notas"] = f"de la ficha de la patente {ficha.get('patente') or '—'}"
        if ficha.get("motorizacion"):
            resultado["motor"] = ficha["motorizacion"]
            resultado["motor_origen"] = f"ficha de la patente {ficha.get('patente') or '—'}"
        if ficha.get("anio") and str(ficha["anio"]).strip().isdigit():
            resultado["anio_estimado"] = int(str(ficha["anio"]).strip())
            resultado["anio_alternativo"] = None
            resultado["anio_preciso"] = True

    return resultado


def agregar_fabricante_vin(wmi, fabricante, pais):
    wmi = wmi.strip().upper()
    with db_lock:
        c.execute(
            "INSERT INTO fabricantes_vin (wmi, fabricante, pais) VALUES (?, ?, ?) "
            "ON CONFLICT(wmi) DO UPDATE SET fabricante=excluded.fabricante, pais=excluded.pais",
            (wmi, fabricante.strip(), pais.strip())
        )
        conn.commit()


def enseniar_modelo_vin(wmi, vds, modelo, notas=None):
    """Guarda que este patrón de VIN corresponde a este modelo. La próxima vez se autocompleta."""
    wmi, vds = wmi.strip().upper(), vds.strip().upper()
    if not wmi or not vds or not modelo.strip():
        return False
    with db_lock:
        c.execute("""INSERT INTO modelos_vin (wmi, vds, modelo, notas) VALUES (?, ?, ?, ?)
                     ON CONFLICT(wmi, vds) DO UPDATE SET modelo = excluded.modelo,
                        notas = excluded.notas, veces = veces + 1""",
                  (wmi, vds, modelo.strip(), (notas or "").strip() or None))
        conn.commit()
    return True


def olvidar_modelo_vin(wmi, vds):
    with db_lock:
        c.execute("DELETE FROM modelos_vin WHERE wmi = ? AND vds = ?",
                  (wmi.strip().upper(), vds.strip().upper()))
        conn.commit()
    return c.rowcount


def listar_modelos_vin():
    c.execute("""SELECT m.wmi AS "WMI", m.vds AS "Patrón (VDS)", m.modelo AS "Modelo",
                        COALESCE(f.fabricante, '—') AS "Fabricante", m.notas AS "Notas"
                 FROM modelos_vin m LEFT JOIN fabricantes_vin f ON f.wmi = m.wmi
                 ORDER BY f.fabricante, m.modelo""")
    return filas_a_listas(c)


def listar_fabricantes_vin():
    c.execute("""SELECT wmi AS "WMI", fabricante AS "Fabricante", pais AS "País"
                 FROM fabricantes_vin ORDER BY fabricante""")
    return filas_a_listas(c)


# ============================================================
# MODO MECÁNICO — VISOR DE ESQUEMAS
# ============================================================
def guardar_esquema(titulo, marca_auto, modelo_auto, sistema, descripcion, imagen_bytes, imagen_nombre, generado_ia=False):
    with db_lock:
        c.execute(
            "INSERT INTO esquemas (titulo, marca_auto, modelo_auto, sistema, descripcion, imagen_blob, "
            "imagen_nombre, generado_ia) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (titulo.strip(), marca_auto.strip(), modelo_auto.strip(), sistema.strip(), descripcion.strip(),
             imagen_bytes, imagen_nombre, 1 if generado_ia else 0)
        )
        conn.commit()


# Pistas de piezas típicas en inglés por sistema, para ayudar al modelo gratuito (Flux) a acertar
# mejor el contenido — sin esto tiende a dibujar cualquier cosa genérica de "auto".
PARTES_TIPICAS_POR_SISTEMA = {
    "Motor": "engine block, pistons, cylinder head, timing chain, oil pan",
    "Refrigeración": "radiator, water pump, thermostat, coolant hoses, coolant expansion tank, cooling fan",
    "Retenes y juntas": "crankshaft seal, camshaft seal, gaskets, o-rings",
    "Frenos": "brake disc, brake caliper, brake pads, brake drum, brake hose",
    "Suspensión": "shock absorber, coil spring, control arm, ball joint, stabilizer bar",
    "Dirección": "steering rack, tie rod, steering column, power steering pump",
    "Transmisión": "gearbox, clutch disc, driveshaft, CV joint",
    "Embrague": "clutch disc, clutch pressure plate, release bearing, clutch cable",
    "Correas y distribución": "timing belt, timing belt tensioner, timing belt kit, pulleys",
    "Eléctrico": "alternator, starter motor, battery, wiring harness, fuse box",
    "Combustible": "fuel pump, fuel filter, fuel injectors, fuel tank, fuel lines",
    "Escape": "exhaust manifold, muffler, catalytic converter, exhaust pipe",
    "Aire acondicionado": "AC compressor, condenser, evaporator, AC hoses",
}

# Nombre del sistema en inglés, para no mezclar español dentro de un prompt en inglés.
SISTEMA_EN = {
    "Motor": "engine", "Refrigeración": "cooling", "Retenes y juntas": "seals and gaskets",
    "Frenos": "brake", "Suspensión": "suspension", "Dirección": "steering",
    "Transmisión": "transmission", "Embrague": "clutch", "Correas y distribución": "timing belt",
    "Eléctrico": "electrical", "Combustible": "fuel", "Escape": "exhaust",
    "Aire acondicionado": "air conditioning",
}


def generar_esquema_orientativo_ia(marca, modelo, motorizacion, sistema):
    """Genera una imagen orientativa/genérica (NO una foto real del vehículo) con Gemini.
    Requiere que la generación de imágenes esté habilitada en la API key correspondiente.
    Usa una key APARTE de la del resto de las funciones de IA (identificar_pieza_por_foto,
    extraer_datos_cedula, transcribir_audio, leer_remito_por_foto) — así, aunque esas otras se usen
    mucho y choquen contra el límite gratuito, nunca pueden generar un cobro por sí solas: la única
    key con facturación habilitada es esta, y solo la usa esta función."""
    from google import genai
    from PIL import Image as PILImage

    api_key = secretos_app().get("gemini_api_key_imagenes")
    if not api_key:
        return None, (
            "No configuraste 'gemini_api_key_imagenes' en Streamlit Cloud (Settings → Secrets). "
            "A propósito es una key distinta de 'gemini_api_key', separada solo para esta función."
        )

    sistema_en = SISTEMA_EN.get(sistema, sistema)
    pistas = PARTES_TIPICAS_POR_SISTEMA.get(sistema, "")
    pistas_txt = f" Mostrá específicamente: {pistas}." if pistas else ""
    prompt = (
        f"Genera un diagrama técnico de despiece ('exploded view') en estilo línea/dibujo técnico "
        f"(como los planos de catálogos de repuestos), mostrando ÚNICAMENTE los componentes del sistema "
        f"de {sistema_en} de un automóvil {marca} {modelo} {motorizacion}.{pistas_txt} No dibujes la "
        f"carrocería completa del auto — solo estas piezas mecánicas, separadas entre sí (vista "
        f"explosionada), unidas por líneas finas, sobre fondo blanco liso, en blanco y negro o con líneas "
        f"oscuras simples. IMPORTANTE: no incluyas números, letras, flechas de referencia, texto ni logos "
        f"de ninguna marca dentro del dibujo — esos se agregan después por separado. Es una referencia "
        f"orientativa general de cómo se relacionan las piezas entre sí, no necesita ser exacto a ese "
        f"modelo puntual."
    )
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model="gemini-2.5-flash-image", contents=[prompt])
        for part in response.candidates[0].content.parts:
            if getattr(part, "inline_data", None) is not None:
                img = PILImage.open(io.BytesIO(part.inline_data.data)).convert("RGB")
                salida = io.BytesIO()
                img.save(salida, format="JPEG", quality=90)
                registrar_uso_ia("Generar imagen orientativa (paga)", True)
                return salida.getvalue(), None
        registrar_uso_ia("Generar imagen orientativa (paga)", False)
        return None, "Gemini no devolvió ninguna imagen para ese pedido."
    except Exception as e:
        anotar_error("generar_esquema_orientativo_ia", e)
        registrar_uso_ia("Generar imagen orientativa (paga)", False)
        texto_error = str(e)
        if "RESOURCE_EXHAUSTED" in texto_error or "429" in texto_error or "quota" in texto_error.lower():
            return None, (
                "Esta función no está habilitada en la API key configurada (el error dice 'limit: 0' "
                "para ese modelo). Hay que habilitarla en aistudio.google.com para la key "
                "'gemini_api_key_imagenes'. El resto de las funciones de IA usan una key distinta y "
                "separada, así que no se ven afectadas por esto."
            )
        return None, f"Error generando la imagen: {texto_error}"


def listar_marcas_esquemas():
    """Marcas con esquemas ya cargados, UNIDAS con las precargadas en el catálogo (sin imagen todavía)."""
    c.execute("""SELECT marca_auto AS marca FROM esquemas WHERE marca_auto IS NOT NULL AND TRIM(marca_auto) != ''
                 UNION
                 SELECT marca FROM esquemas_catalogo
                 ORDER BY marca""")
    return [r["marca"] for r in c.fetchall()]


def listar_modelos_esquemas(marca):
    c.execute("""SELECT modelo_auto AS modelo FROM esquemas
                 WHERE marca_auto = ? AND modelo_auto IS NOT NULL AND TRIM(modelo_auto) != ''
                 UNION
                 SELECT modelo FROM esquemas_catalogo WHERE marca = ?
                 ORDER BY modelo""", (marca, marca))
    return [r["modelo"] for r in c.fetchall()]


def listar_sistemas_esquemas(marca, modelo):
    c.execute("""SELECT DISTINCT sistema FROM esquemas
                 WHERE marca_auto = ? AND modelo_auto = ? AND sistema IS NOT NULL AND TRIM(sistema) != ''
                 ORDER BY sistema""", (marca, modelo))
    return [r["sistema"] for r in c.fetchall()]


def listar_esquemas_por_categoria(marca, modelo, sistema):
    c.execute("""SELECT id, titulo, descripcion, generado_ia FROM esquemas
                 WHERE marca_auto = ? AND modelo_auto = ? AND sistema = ? ORDER BY titulo""",
              (marca, modelo, sistema))
    return [dict(r) for r in c.fetchall()]


def agregar_vehiculo_catalogo(marca, modelo):
    with db_lock:
        c.execute("INSERT OR IGNORE INTO esquemas_catalogo (marca, modelo) VALUES (?, ?)",
                   (marca.strip(), modelo.strip()))
        conn.commit()


def eliminar_vehiculo_catalogo(marca, modelo):
    with db_lock:
        c.execute("DELETE FROM esquemas_catalogo WHERE marca = ? AND modelo = ?", (marca, modelo))
        conn.commit()


def listar_catalogo_precargado():
    """Marca/modelo precargados sin ningún esquema real cargado todavía (candidatos a borrar)."""
    c.execute("""SELECT marca, modelo FROM esquemas_catalogo ec
                 WHERE NOT EXISTS (
                     SELECT 1 FROM esquemas e WHERE e.marca_auto = ec.marca AND e.modelo_auto = ec.modelo
                 ) ORDER BY marca, modelo""")
    return [dict(r) for r in c.fetchall()]


def listar_esquemas(texto_filtro=""):
    if texto_filtro.strip():
        like = f"%{texto_filtro.strip().upper()}%"
        c.execute("""SELECT id, titulo, marca_auto, modelo_auto, sistema, descripcion, generado_ia FROM esquemas
                     WHERE UPPER(titulo) LIKE ? OR UPPER(marca_auto) LIKE ? OR UPPER(modelo_auto) LIKE ?
                        OR UPPER(sistema) LIKE ?
                     ORDER BY marca_auto, modelo_auto""", (like, like, like, like))
    else:
        c.execute("SELECT id, titulo, marca_auto, modelo_auto, sistema, descripcion, generado_ia FROM esquemas "
                   "ORDER BY marca_auto, modelo_auto")
    return [dict(row) for row in c.fetchall()]


def obtener_imagen_esquema(esquema_id):
    c.execute("SELECT imagen_blob FROM esquemas WHERE id = ?", (esquema_id,))
    row = c.fetchone()
    return row["imagen_blob"] if row else None


def eliminar_esquema(esquema_id):
    with db_lock:
        c.execute("DELETE FROM esquemas WHERE id = ?", (esquema_id,))
        conn.commit()


def agregar_punto_esquema(esquema_id, numero, nombre_pieza, codigo, pos_x=None, pos_y=None):
    """Agrega una pieza marcada dentro de un esquema. Si el código coincide con un producto
    ya cargado, lo vincula (producto_id); si no, igual guarda el código como texto de referencia.
    pos_x/pos_y son porcentajes (0-100) de dónde está la pieza en la imagen, para dibujar el marcador."""
    codigo = (codigo or "").strip()
    producto_id = None
    if codigo:
        clean = sanitizar(codigo)
        if clean:
            c.execute("SELECT id FROM productos WHERE codigo_clean = ? LIMIT 1", (clean,))
            fila = c.fetchone()
            if fila:
                producto_id = fila["id"]
    with db_lock:
        c.execute("SELECT COALESCE(MAX(orden), 0) + 1 FROM esquema_puntos WHERE esquema_id = ?", (esquema_id,))
        siguiente_orden = c.fetchone()[0]
        c.execute(
            "INSERT INTO esquema_puntos (esquema_id, numero, nombre_pieza, codigo, producto_id, pos_x, pos_y, orden) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (esquema_id, (numero or "").strip(), nombre_pieza.strip(), codigo, producto_id, pos_x, pos_y, siguiente_orden)
        )
        conn.commit()
    return producto_id is not None


def listar_puntos_esquema(esquema_id):
    c.execute("""SELECT id, numero, nombre_pieza, codigo, producto_id, pos_x, pos_y FROM esquema_puntos
                 WHERE esquema_id = ? ORDER BY orden""", (esquema_id,))
    return [dict(r) for r in c.fetchall()]


@st.cache_data(show_spinner=False, max_entries=40)
def imagen_esquema_lista_para_mostrar(imagen_bytes, firma_puntos, _puntos):
    """Dibuja los marcadores sobre la imagen y guarda el resultado en caché. Sin esto, cada
    refresco de pantalla vuelve a redibujar la imagen entera con Pillow — aunque el desplegable
    esté cerrado, porque Streamlit igual arma el contenido.
    El caché se invalida solo cuando cambia la imagen (se compara su contenido) o cuando cambian
    los puntos marcados ('firma_puntos'). '_puntos' va con guion bajo adelante para que Streamlit
    no intente usarlo como clave: es una lista de diccionarios y no le sirve para comparar."""
    return generar_imagen_con_marcadores(imagen_bytes, _puntos)


def firma_de_puntos(puntos):
    """Resumen corto de los puntos, para usar como clave de caché."""
    return tuple((p["id"], p.get("numero"), p.get("pos_x"), p.get("pos_y")) for p in puntos)


def generar_imagen_con_marcadores(imagen_bytes, puntos):
    """Dibuja círculos numerados sobre la imagen real, en las posiciones (%) que cargó el admin.
    Si la imagen está corrupta, devuelve la original sin marcadores en vez de romper la pantalla."""
    from PIL import Image, ImageDraw, UnidentifiedImageError

    puntos_con_pos = [p for p in puntos if p.get("pos_x") is not None and p.get("pos_y") is not None]
    if not puntos_con_pos:
        return imagen_bytes

    try:
        img = Image.open(io.BytesIO(imagen_bytes)).convert("RGB")
        ancho, alto = img.size
        draw = ImageDraw.Draw(img)
        radio = max(min(ancho, alto) // 40, 12)

        for i, p in enumerate(puntos_con_pos, start=1):
            x = int(p["pos_x"] / 100 * ancho)
            y = int(p["pos_y"] / 100 * alto)
            etiqueta = p.get("numero") or str(i)
            draw.ellipse([x - radio, y - radio, x + radio, y + radio], fill=(232, 163, 61), outline=(20, 20, 20), width=2)
            bbox = draw.textbbox((0, 0), etiqueta)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text((x - tw / 2, y - th / 2 - bbox[1]), etiqueta, fill=(20, 20, 20))

        salida = io.BytesIO()
        img.save(salida, format="JPEG", quality=90)
        return salida.getvalue()
    except (UnidentifiedImageError, OSError) as _err:
        anotar_error("generar_imagen_con_marcadores", _err)
        return imagen_bytes


def eliminar_punto_esquema(punto_id):
    with db_lock:
        c.execute("DELETE FROM esquema_puntos WHERE id = ?", (punto_id,))
        conn.commit()


def guardar_presupuesto_mecanico(mecanico_id, cliente_nombre, items, mano_obra):
    total = sum(it["precio"] * it["cantidad"] for it in items) + mano_obra
    with db_lock:
        c.execute(
            "INSERT INTO presupuestos_mecanico (mecanico_id, cliente_nombre, items_json, mano_obra, total) "
            "VALUES (?, ?, ?, ?, ?)",
            (mecanico_id, cliente_nombre.strip(), json.dumps(items, ensure_ascii=False), mano_obra, total)
        )
        conn.commit()
    return total


def listar_presupuestos_mecanico(mecanico_id):
    c.execute("""SELECT id AS "ID", cliente_nombre AS "Cliente", items_json, mano_obra AS "Mano de obra",
                 total AS "Total", creado_en AS "Fecha" FROM presupuestos_mecanico
                 WHERE mecanico_id = ? ORDER BY id DESC""", (mecanico_id,))
    return filas_a_listas(c)


def generar_pdf_presupuesto_mecanico(nombre_mecanico, cliente_nombre, items, mano_obra, total):
    from fpdf import FPDF

    def limpiar(texto):
        return str(texto).encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Presupuesto", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, limpiar(f"Mecánico: {nombre_mecanico}"), new_x="LMARGIN", new_y="NEXT")
    if cliente_nombre:
        pdf.cell(0, 6, limpiar(f"Cliente: {cliente_nombre}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Fecha: {datetime.now():%d/%m/%Y %H:%M}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Repuestos", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for it in items:
        subtotal = it["precio"] * it["cantidad"]
        linea = f"- {it['codigo']} ({it['marca']}) x{it['cantidad']} - ${subtotal:,.0f}"
        pdf.multi_cell(0, 6, limpiar(linea), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, limpiar(f"Mano de obra: ${mano_obra:,.0f}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, limpiar(f"TOTAL: ${total:,.0f}"), new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


def mostrar_portal_mecanico():
    """Portal separado para mecánicos externos — no ven ninguna de las pestañas internas del
    negocio, solo esto: buscar repuestos, armar su presupuesto con su propia mano de obra, y
    ver sus presupuestos guardados anteriormente (nunca los de otros mecánicos)."""
    mostrar_avisos_pendientes()
    mecanico_id = st.session_state.get("mecanico_id")
    nombre_mecanico = st.session_state.get("admin_nombre", "")
    st.markdown(f"### 🔧 Portal de mecánico — {nombre_mecanico}")
    st.caption(
        "Buscá repuestos del catálogo, armá tu presupuesto con tu propia mano de obra, y mandaselo "
        "al cliente. Solo ves tus propios presupuestos guardados, no los de otros mecánicos."
    )

    if "presupuesto_mecanico_items" not in st.session_state:
        st.session_state["presupuesto_mecanico_items"] = []

    st.markdown("**🔍 Buscar repuesto**")
    texto_busqueda_mec = st.text_input("Código o descripción:", key="mec_busqueda")
    if texto_busqueda_mec.strip():
        clean_mec = sanitizar(texto_busqueda_mec)
        resultados_mec = buscar_por_codigo(clean_mec) if clean_mec else []
        if not resultados_mec:
            resultados_mec = buscar_por_texto(texto_busqueda_mec)
        if resultados_mec:
            for fila in resultados_mec[:20]:
                colm1, colm2, colm3 = st.columns([3, 1, 1])
                precio_txt = f"${fila['Precio']:,.0f}" if fila.get("Precio") else "s/precio"
                colm1.write(f"{fila['Marca']} - {fila['Codigo']} — {fila.get('Descripcion') or ''} ({precio_txt})")
                cantidad_mec = colm2.number_input("Cant.", min_value=1, value=1, step=1,
                                                    key=f"cant_mec_{fila['ID']}", label_visibility="collapsed")
                if colm3.button("➕", key=f"add_mec_{fila['ID']}"):
                    st.session_state["presupuesto_mecanico_items"].append({
                        "codigo": fila["Codigo"], "marca": fila["Marca"],
                        "descripcion": fila.get("Descripcion") or "",
                        "precio": float(fila.get("Precio") or 0), "cantidad": int(cantidad_mec)
                    })
                    st.rerun()
        else:
            st.caption("Sin resultados.")

    items_actuales = st.session_state["presupuesto_mecanico_items"]
    st.markdown("---")
    st.markdown(f"**📋 Presupuesto actual ({len(items_actuales)} ítem(s))**")
    if items_actuales:
        subtotal_repuestos = 0.0
        for i, it in enumerate(items_actuales):
            subtotal_item = it["precio"] * it["cantidad"]
            subtotal_repuestos += subtotal_item
            coli1, coli2 = st.columns([4, 1])
            coli1.write(f"{it['marca']} - {it['codigo']} x{it['cantidad']} — ${subtotal_item:,.0f}")
            coli2.button("🗑️", key=f"quitar_mec_{i}",
                          on_click=quitar_item_lista_sesion, args=("presupuesto_mecanico_items", i))

        cliente_nombre_mec = st.text_input("Nombre del cliente (opcional):", key="mec_cliente")
        mano_obra_mec = st.number_input("Mano de obra ($):", min_value=0.0, step=500.0, key="mec_mano_obra")
        total_mec = subtotal_repuestos + mano_obra_mec
        st.metric("Total", f"${total_mec:,.0f}")

        colb1, colb2, colb3 = st.columns(3)
        if colb1.button("💾 Guardar presupuesto", type="primary"):
            guardar_presupuesto_mecanico(mecanico_id, cliente_nombre_mec, items_actuales, mano_obra_mec)
            st.success("Presupuesto guardado.")
            st.session_state["presupuesto_mecanico_items"] = []
            st.rerun()

        pdf_bytes_mec = pdf_con_cache(
            "presupuesto_mecanico", generar_pdf_presupuesto_mecanico,
            nombre_mecanico, cliente_nombre_mec, items_actuales, mano_obra_mec, total_mec
        )
        colb2.download_button("📄 PDF", data=pdf_bytes_mec, file_name="presupuesto.pdf", mime="application/pdf")

        mensaje_mec = f"Presupuesto de {nombre_mecanico}:\n"
        for it in items_actuales:
            mensaje_mec += f"- {it['codigo']} ({it['marca']}) x{it['cantidad']} — ${it['precio']*it['cantidad']:,.0f}\n"
        mensaje_mec += f"Mano de obra: ${mano_obra_mec:,.0f}\nTOTAL: ${total_mec:,.0f}"
        url_wa_mec = "https://wa.me/?text=" + quote(mensaje_mec)
        colb3.link_button("📲 WhatsApp", url_wa_mec)
    else:
        st.caption("Todavía no agregaste ningún repuesto al presupuesto.")

    st.markdown("---")
    st.markdown("**📁 Mis presupuestos anteriores**")
    anteriores = listar_presupuestos_mecanico(mecanico_id)
    if anteriores:
        for p in anteriores[:20]:
            with st.expander(f"{p['Fecha']} — {p['Cliente'] or 'sin nombre'} — ${p['Total']:,.0f}"):
                items_p = json.loads(p["items_json"])
                for it in items_p:
                    st.write(f"- {it['codigo']} ({it['marca']}) x{it['cantidad']} — ${it['precio']*it['cantidad']:,.0f}")
                st.write(f"Mano de obra: ${p['Mano de obra']:,.0f}")
    else:
        st.caption("Todavía no guardaste ningún presupuesto.")

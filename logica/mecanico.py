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
    # Acá el código y el catálogo no se llaman igual: la norma dice «ventilador del radiador»
    # (P0480) y el mostrador lo pide como «electroventilador». Cuando pasa eso, van separadas
    # las palabras que hay que leer EN EL CÓDIGO y las que hay que buscar EN EL CATÁLOGO —
    # «VENTILADOR» a secas trae 253 productos que no son eso. (Estaba dos veces: Python se
    # quedaba con esta, en el lugar de la primera.)
    "ELECTROVENTILADOR": {"dtc": ("ELECTROVENTILADOR", "VENTILADOR DEL RADIADOR",
                                  "VENTILADOR DE ENFRIAMIENTO"),
                          "catalogo": ("ELECTROVENTILADOR",)},
    "ALTERNADOR": ("ALTERNADOR",),
    "BOMBA DE AGUA": ("BOMBA DE AGUA",),
    "FILTRO DE AIRE": ("FILTRO DE AIRE",),
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
    exigir_nivel("empleado", "cargar un código de falla")
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
    exigir_nivel("empleado", "cargar códigos de falla")
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
# MODO MECÁNICO — CONVERSOR DE UNIDADES
# ============================================================
# Todo sale de seis DEFINICIONES, no de mediciones: son exactas por norma (la libra y el pie
# internacionales de 1959, el kilogramo fuerza de la CGPM, el galón y la milla de EE.UU.), así
# que la cuenta no tiene redondeos escondidos. Antes cada factor estaba escrito a mano y con
# seis cifras (1.35582); ahora se arma de estas, y una prueba compara contra valores conocidos.
_LIBRA_FUERZA_EN_N = 4.4482216152605
_PIE_EN_M = 0.3048
_PULGADA_EN_M = 0.0254
_KILOGRAMO_FUERZA_EN_N = 9.80665
_GALON_EEUU_EN_L = 3.785411784
_MILLA_EN_KM = 1.609344
_PSI_EN_PA = _LIBRA_FUERZA_EN_N / _PULGADA_EN_M ** 2          # 6.894,757…
_HP_EN_W = 550 * _PIE_EN_M * _LIBRA_FUERZA_EN_N               # 745,699… (HP mecánico)
_CV_EN_W = 75 * _KILOGRAMO_FUERZA_EN_N                        # 735,49875 (el CV de acá)

# Por categoría: (unidad A, unidad B, factor, suma) quiere decir B = A × factor + suma, y se
# ofrecen las dos direcciones. Las que se agregaron son las que traen los manuales que se usan
# acá: los japoneses dan el torque en kgf·m y kgf·cm, los manómetros viejos marcan kg/cm², los
# autos importados de EE.UU. vienen en millas y galones, y la potencia se dice en CV o en HP,
# que NO son lo mismo (el HP es 1,4 % más).
CONVERSIONES_DE_TALLER = {
    "Torque": (("lb-ft", "Nm", _LIBRA_FUERZA_EN_N * _PIE_EN_M, 0.0),
               ("lb-in", "Nm", _LIBRA_FUERZA_EN_N * _PULGADA_EN_M, 0.0),
               ("kgf·m", "Nm", _KILOGRAMO_FUERZA_EN_N, 0.0),
               ("kgf·cm", "Nm", _KILOGRAMO_FUERZA_EN_N / 100, 0.0)),
    "Presión": (("PSI", "Bar", _PSI_EN_PA / 1e5, 0.0),
                ("PSI", "kPa", _PSI_EN_PA / 1e3, 0.0),
                ("kg/cm²", "Bar", _KILOGRAMO_FUERZA_EN_N * 1e4 / 1e5, 0.0),
                ("kg/cm²", "PSI", _KILOGRAMO_FUERZA_EN_N * 1e4 / _PSI_EN_PA, 0.0)),
    "Longitud": (("Pulgadas", "mm", _PULGADA_EN_M * 1e3, 0.0),
                 ("Pulgadas", "cm", _PULGADA_EN_M * 1e2, 0.0),
                 ("Millas", "km", _MILLA_EN_KM, 0.0)),
    "Volumen": (("Galones (EE.UU.)", "Litros", _GALON_EEUU_EN_L, 0.0),
                ("Onzas líquidas (EE.UU.)", "ml", _GALON_EEUU_EN_L * 1e3 / 128, 0.0)),
    "Potencia": (("HP", "kW", _HP_EN_W / 1e3, 0.0),
                 ("CV", "kW", _CV_EN_W / 1e3, 0.0),
                 ("HP", "CV", _HP_EN_W / _CV_EN_W, 0.0)),
    "Temperatura": (("°C", "°F", 9 / 5, 32.0),),
}


def direcciones_de_conversion(categoria):
    """«lb-ft → Nm», «Nm → lb-ft»… en el orden de la tabla. Ver CONVERSIONES_DE_TALLER."""
    salida = []
    for a, b, _f, _s in CONVERSIONES_DE_TALLER[categoria]:
        salida += [f"{a} → {b}", f"{b} → {a}"]
    return salida


def convertir_unidad(valor, categoria, direccion):
    """(resultado, unidad) para una de las direcciones_de_conversion(). Ver
    CONVERSIONES_DE_TALLER."""
    de, _, a = direccion.partition(" → ")
    for u1, u2, factor, suma in CONVERSIONES_DE_TALLER[categoria]:
        if (u1, u2) == (de, a):
            return valor * factor + suma, a
        if (u2, u1) == (de, a):
            return (valor - suma) / factor, a
    raise KeyError(direccion)


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
# "8A" es Argentina y "8F" Chile. Se usa esto primero y, si no está, se cae al de una letra.
# Revisada el 16/10/2026 contra varias tablas de ISO 3779 (las fuentes no coinciden en todos
# los bordes, así que solo se tocó donde coinciden todas): Austria es VA a VE —con una sola
# letra un VIN VBK… de KTM decía «Francia / España»—, y Ecuador empieza en 8L, así que 8K no
# es Ecuador (casi todas lo dan a Chile, 8F-8K).
PAISES_VIN_2 = {
    # --- Sudamérica ---
    "8A": "Argentina", "8B": "Argentina", "8C": "Argentina", "8D": "Argentina",
    "8E": "Argentina",
    "8F": "Chile", "8G": "Chile", "8H": "Chile", "8J": "Chile", "8K": "Chile",
    "8L": "Ecuador", "8M": "Ecuador", "8N": "Ecuador", "8P": "Ecuador", "8R": "Ecuador",
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
    "VA": "Austria", "VB": "Austria", "VC": "Austria", "VD": "Austria", "VE": "Austria",
    "VN": "Francia", "VF": "Francia", "VG": "Francia", "VL": "Francia",
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
        return None, f"No se pudo consultar ({el_error_en_castellano(e)}). Puede ser la conexión."

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

    # El dígito verificador (9ª posición) ya quedó arriba, con verificar_vin(). Acá había una
    # segunda cuenta que lo PISABA: dejaba None o True/False donde la pantalla espera "ok",
    # "mal" o "no_aplica", así que el «❌ el VIN está mal copiado» no salía nunca, ni en un VIN
    # de Estados Unidos con un carácter cambiado. Lo encontró el control 6e de auditar.py.

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
    exigir_nivel("empleado", "cargar un fabricante del VIN")
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
    exigir_nivel("empleado", "enseñarle un modelo al lector de VIN")
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
    exigir_nivel("empleado", "borrar un modelo aprendido del VIN")
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
# MODO MECÁNICO — CAMPAÑAS DE SEGURIDAD Y FALLAS REPORTADAS (NHTSA)
# ============================================================
# La NHTSA (el organismo de seguridad vial del gobierno de EE.UU.) publica, gratis y sin clave,
# dos cosas por marca, modelo y año:
#   · las CAMPAÑAS de seguridad (recalls): el defecto, qué puede pasar y cómo se arregla;
#   · los RECLAMOS de los dueños, con el componente que falló.
# Para el negocio sirve lo segundo sobre todo: el componente con más reclamos es la pieza que
# más se rompe en ese auto, la que conviene tener en stock y la que el mecánico va a mirar
# primero. Los dos son del mercado de EE.UU.: valen para los autos que se venden allá con el
# mismo nombre (Ranger, Cruze, Tracker, Corolla, Renegade, Compass, Kicks, Frontier, Civic,
# CR-V, Tucson, Sportage, 500, Sprinter, Taos, Tiguan…). Un Gol, un Palio o un 208 no están.
# Se consulta solo cuando se aprieta el botón, y lo traído queda un día en memoria.
URL_NHTSA_CAMPANIAS = ("https://api.nhtsa.gov/recalls/recallsByVehicle?make={marca}"
                       "&model={modelo}&modelYear={anio}")
URL_NHTSA_RECLAMOS = ("https://api.nhtsa.gov/complaints/complaintsByVehicle?make={marca}"
                      "&model={modelo}&modelYear={anio}")
URL_NHTSA_MODELOS = ("https://api.nhtsa.gov/products/vehicle/models?modelYear={anio}"
                     "&make={marca}&issueType=c")
HORAS_DE_LO_TRAIDO_DE_LA_NHTSA = 24
# Corto: el botón «🌐 Consultar» dice «probá en un rato», y un rato son cinco minutos.
MINUTOS_SIN_REINTENTAR_LA_NHTSA = 5
# Cómo se llaman allá las marcas que acá se escriben distinto.
MARCAS_PARA_LA_NHTSA = {"VW": "VOLKSWAGEN", "MERCEDES BENZ": "MERCEDES-BENZ",
                        "MERCEDES": "MERCEDES-BENZ", "CHEV": "CHEVROLET", "CHEVY": "CHEVROLET"}
# El componente, en castellano. Se mira la primera que aparece, de la más específica a la más
# general: «PARKING BRAKE» es freno de mano antes que frenos, «ENGINE AND ENGINE COOLING» es
# motor. La NHTSA escribe el componente como «SISTEMA:PARTE:PIEZA».
COMPONENTES_EN_CASTELLANO = [
    ("AIR BAG", "Airbags"), ("SEAT BELT", "Cinturones de seguridad"),
    ("PARKING BRAKE", "Freno de mano"), ("BRAKE", "Frenos"), ("STEERING", "Dirección"),
    ("SUSPENSION", "Suspensión"), ("POWER TRAIN", "Caja y transmisión"),
    ("ENGINE COOLING", "Motor y refrigeración"), ("ENGINE", "Motor"),
    ("FUEL", "Sistema de combustible"), ("EXHAUST", "Escape"),
    ("ELECTRICAL", "Sistema eléctrico"), ("LIGHTING", "Luces"), ("TIRE", "Cubiertas"),
    ("WHEEL", "Ruedas y llantas"), ("STRUCTURE", "Carrocería y estructura"),
    ("VISIBILITY", "Visibilidad (limpiaparabrisas, espejos, vidrios)"),
    ("SPEED CONTROL", "Acelerador y control de velocidad"),
    ("LATCHES", "Cerraduras y trabas"), ("SEAT", "Asientos"),
    ("COLLISION", "Asistencias de manejo"), ("BACK OVER", "Cámara y sensores de retroceso"),
    ("STABILITY CONTROL", "Control de estabilidad"), ("HYBRID", "Sistema híbrido"),
    ("EQUIPMENT", "Equipamiento"),
]


def componente_en_castellano(texto):
    """«SERVICE BRAKES, HYDRAULIC:FOUNDATION COMPONENTS» → «Frenos». None si no se reconoce."""
    sistema = str(texto or "").upper().split(":")[0]
    return next((castellano for clave, castellano in COMPONENTES_EN_CASTELLANO
                 if clave in sistema), None)


def _componentes_del_reclamo(texto):
    """Los componentes de un reclamo, en castellano y sin repetir. La NHTSA los manda en un
    solo texto separado por comas, y algunos nombres llevan coma adentro («SERVICE BRAKES,
    HYDRAULIC»): un pedazo que solo no se reconoce se descarta."""
    salida = []
    for pedazo in str(texto or "").split(","):
        nombre = componente_en_castellano(pedazo)
        if nombre and nombre not in salida:
            salida.append(nombre)
    return salida or ["Otro"]


def _sin_signos(texto):
    return re.sub(r"[^A-Z0-9]", "", str(texto or "").upper())


def marca_para_la_nhtsa(marca):
    marca = re.sub(r"\s+", " ", str(marca or "").upper()).strip()
    return MARCAS_PARA_LA_NHTSA.get(marca, marca)


def _de_la_nhtsa(url):
    """Lo mismo que _pedir_json(), guardado un día por URL: la NHTSA es un servidor ajeno.

    Si no contestó, eso también se recuerda, MINUTOS_SIN_REINTENTAR_LA_NHTSA. La lista de
    modelos se pide al dibujar la pantalla con «🇺🇸 Campañas…» abierto, y sin esto, con la
    NHTSA sin contestar, cada toque en «🚙 Repuestos por vehículo» esperaba los 10 s otra vez
    (lo mismo pasaba con los bancos del BCRA: ver bancos_del_bcra())."""
    guardado = del_proceso("lo_traido_de_la_nhtsa", dict)
    previo = guardado.get(url)
    if previo and time.time() - previo[0] < (HORAS_DE_LO_TRAIDO_DE_LA_NHTSA * 3600
                                             if previo[1] is not None
                                             else MINUTOS_SIN_REINTENTAR_LA_NHTSA * 60):
        return previo[1]
    respuesta = _pedir_json(url, tiempo_maximo=10)
    guardado[url] = (time.time(), respuesta)
    return respuesta


def _resultados(respuesta):
    """La lista de resultados: las campañas la mandan en «results», los reclamos también, y
    alguna versión vieja en «Results»."""
    if not isinstance(respuesta, dict):
        return None
    lista = respuesta.get("results", respuesta.get("Results"))
    return lista if isinstance(lista, list) else None


def _campo(fila, *nombres):
    """El primer campo que exista, sin importar mayúsculas: las campañas vienen con
    «Component», los reclamos con «components»."""
    por_nombre = {str(k).lower(): v for k, v in (fila or {}).items()}
    for nombre in nombres:
        valor = por_nombre.get(nombre.lower())
        if valor not in (None, ""):
            return valor
    return None


def modelos_en_la_nhtsa(marca, anio):
    """Los modelos de esa marca y año que la NHTSA tiene, o None si no contesta."""
    resultados = _resultados(_de_la_nhtsa(URL_NHTSA_MODELOS.format(
        marca=quote(marca_para_la_nhtsa(marca)), anio=int(anio))))
    if resultados is None:
        return None
    return sorted({str(_campo(r, "model") or "").strip().upper() for r in resultados} - {""})


def el_mismo_modelo(modelo, modelos):
    """El modelo de la lista de la NHTSA que es el nuestro, o None. Igual sin signos («F150» y
    «F-150»), o uno cuyas PALABRAS empiezan con las del otro («CRUZE» y «CRUZE LIMITED»). Por
    palabras y no por letras: el Gol no es el Golf."""
    buscado = _sin_signos(modelo)
    if not buscado:
        return None
    for m in modelos or []:
        if _sin_signos(m) == buscado:
            return m
    palabras = [_sin_signos(p) for p in str(modelo).split() if _sin_signos(p)]
    parecidos = []
    for m in modelos or []:
        otras = [_sin_signos(p) for p in str(m).split() if _sin_signos(p)]
        corto = min(len(palabras), len(otras))
        if corto and palabras[:corto] == otras[:corto]:
            parecidos.append(m)
    return min(parecidos, key=len) if parecidos else None


def fallas_reportadas(marca, modelo, anio):
    """(datos, error). datos: {"campanias": [...], "reclamos": cuántos, "por_componente":
    [(componente, reclamos, con_choque, con_incendio)] de más a menos}.

    Cada campaña: número, fecha, componente (en castellano y el original), resumen,
    consecuencia, solución y si la NHTSA dice que no hay que usar el auto hasta arreglarlo.
    Los textos vienen en inglés: así los publica la NHTSA."""
    try:
        anio = int(anio)
    except (TypeError, ValueError):
        return None, "Falta el año."
    marca_n = marca_para_la_nhtsa(marca)
    if not marca_n or not str(modelo or "").strip():
        return None, "Falta la marca o el modelo."
    pedido = dict(marca=quote(marca_n), modelo=quote(str(modelo).strip().upper()), anio=anio)
    campanias_r = _resultados(_de_la_nhtsa(URL_NHTSA_CAMPANIAS.format(**pedido)))
    reclamos_r = _resultados(_de_la_nhtsa(URL_NHTSA_RECLAMOS.format(**pedido)))
    if campanias_r is None and reclamos_r is None:
        return None, "La NHTSA no contestó. Puede ser la conexión: probá en un rato."
    campanias = []
    for r in campanias_r or []:
        original = str(_campo(r, "Component") or "")
        campanias.append({
            "numero": str(_campo(r, "NHTSACampaignNumber") or ""),
            "fecha": str(_campo(r, "ReportReceivedDate") or "")[:10],
            "componente": componente_en_castellano(original) or "Otro",
            "componente_original": original,
            "resumen": str(_campo(r, "Summary") or ""),
            "consecuencia": str(_campo(r, "Consequence") or ""),
            "solucion": str(_campo(r, "Remedy") or ""),
            "no_usar": bool(_campo(r, "parkIt")),
        })
    conteo = {}
    for r in reclamos_r or []:
        for nombre in _componentes_del_reclamo(_campo(r, "components", "Component")):
            fila = conteo.setdefault(nombre, [0, 0, 0])
            fila[0] += 1
            fila[1] += 1 if _campo(r, "crash") in (True, "Y", "Yes", "true") else 0
            fila[2] += 1 if _campo(r, "fire") in (True, "Y", "Yes", "true") else 0
    por_componente = sorted(((n, *v) for n, v in conteo.items()), key=lambda x: (-x[1], x[0]))
    return {"campanias": campanias, "reclamos": len(reclamos_r or []),
            "por_componente": por_componente, "marca": marca_n,
            "modelo": str(modelo).strip().upper(), "anio": anio}, None


def mostrar_fallas_reportadas(marca, modelo, anio, clave):
    """El recuadro «🇺🇸 Campañas y fallas reportadas (NHTSA)» de un auto. No sale a internet
    hasta que se aprieta el botón."""
    if not (marca and modelo and anio):
        return
    if not seccion_plegable("🇺🇸 Campañas de seguridad y fallas más reportadas (NHTSA)",
                            key=f"nhtsa_fallas_{clave}"):
        return
    st.caption("De la NHTSA, el organismo de seguridad vial de EE.UU.: gratis y oficial. Vale "
               "para los modelos que se venden allá con el mismo nombre (Ranger, Cruze, "
               "Corolla, Renegade, Kicks, Civic, Tucson…); un Gol o un Palio no están.")
    modelo_us = str(modelo).strip().upper()
    modelos = modelos_en_la_nhtsa(marca, anio)
    if modelos:
        igual = el_mismo_modelo(modelo_us, modelos)
        if not igual:
            st.info(f"La NHTSA no tiene un {marca_para_la_nhtsa(marca)} «{modelo_us}» {anio}. "
                    "Si allá se llama distinto, elegilo:")
        modelo_us = st.selectbox("Modelo en EE.UU.:", modelos,
                                 index=modelos.index(igual) if igual else None,
                                 placeholder="Elegí el modelo",
                                 key=f"nhtsa_modelo_{clave}_{_sin_signos(marca)}_{anio}")
    if not modelo_us:
        return
    # Lo traído se guarda con el auto que se consultó: si después se cambia el modelo o el año,
    # no queda a la vista el resultado de otro.
    consultado = (marca_para_la_nhtsa(marca), modelo_us, int(anio))
    if st.button("🌐 Consultar", key=f"nhtsa_consultar_{clave}"):
        with st.spinner("Consultando a la NHTSA…"):
            st.session_state[f"nhtsa_fallas_res_{clave}"] = (
                consultado, fallas_reportadas(marca, modelo_us, anio))
    guardado = st.session_state.get(f"nhtsa_fallas_res_{clave}")
    if not guardado or guardado[0] != consultado:
        return
    datos, error = guardado[1]
    if error:
        st.warning(error)
        return
    st.markdown(f"**{datos['marca']} {datos['modelo']} {datos['anio']}** — "
                f"{len(datos['campanias'])} campaña(s) de seguridad · "
                f"{miles(datos['reclamos'])} reclamo(s) de dueños")
    if datos["por_componente"]:
        st.markdown("**🔧 Lo que más falla, según los reclamos** (la pieza a tener en stock y "
                    "a mirar primero):")
        st.dataframe([{"Componente": n, "Reclamos": r, "Con choque": ch, "Con incendio": fu}
                      for n, r, ch, fu in datos["por_componente"][:12]],
                     hide_index=True, width="stretch")
    for camp in datos["campanias"]:
        with st.container(border=True):
            st.markdown(f"**{'⛔ ' if camp['no_usar'] else '⚠️ '}{camp['componente']}** · "
                        f"campaña {camp['numero']} · {camp['fecha']}"
                        + (" · **la NHTSA dice no usarlo hasta arreglarlo**"
                           if camp["no_usar"] else ""))
            st.caption(f"{camp['componente_original']}\n\n{camp['resumen']}\n\n"
                       f"Solución: {camp['solucion']}")
    if not datos["campanias"] and not datos["reclamos"]:
        st.caption("Sin campañas ni reclamos para ese modelo y año.")


# ============================================================
# MODO MECÁNICO — VISOR DE ESQUEMAS
# ============================================================
def guardar_esquema(titulo, marca_auto, modelo_auto, sistema, descripcion, imagen_bytes, imagen_nombre, generado_ia=False):
    exigir_nivel("empleado", "subir un esquema")
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
    exigir_nivel("empleado", "precargar un vehículo de los esquemas")
    with db_lock:
        c.execute("INSERT OR IGNORE INTO esquemas_catalogo (marca, modelo) VALUES (?, ?)",
                   (marca.strip(), modelo.strip()))
        conn.commit()


def eliminar_vehiculo_catalogo(marca, modelo):
    exigir_nivel("empleado", "sacar un vehículo de los esquemas")
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
    exigir_nivel("empleado", "eliminar un esquema")
    with db_lock:
        c.execute("DELETE FROM esquemas WHERE id = ?", (esquema_id,))
        conn.commit()


def agregar_punto_esquema(esquema_id, numero, nombre_pieza, codigo, pos_x=None, pos_y=None):
    """Agrega una pieza marcada dentro de un esquema. Si el código coincide con un producto
    ya cargado, lo vincula (producto_id); si no, igual guarda el código como texto de referencia.
    pos_x/pos_y son porcentajes (0-100) de dónde está la pieza en la imagen, para dibujar el marcador."""
    exigir_nivel("empleado", "marcar una pieza en un esquema")
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
    exigir_nivel("empleado", "sacar una pieza de un esquema")
    with db_lock:
        c.execute("DELETE FROM esquema_puntos WHERE id = ?", (punto_id,))
        conn.commit()


def guardar_presupuesto_mecanico(mecanico_id, cliente_nombre, items, mano_obra):
    """Guarda el presupuesto y devuelve el total. El MISMO presupuesto guardado hace menos de dos
    minutos no se guarda otra vez: un doble toque en «Guardar» (o un toque mientras la pantalla
    todavía se estaba dibujando, que Streamlit vuelve a correr) dejaba dos iguales (lo señaló
    una revisión con ChatGPT)."""
    exigir_que_sea_su_cuenta(mecanico_id, "guardar un presupuesto", "empleado")
    total = sum(it["precio"] * it["cantidad"] for it in items) + mano_obra
    items_json = json.dumps(items, ensure_ascii=False)
    # Con transaccion() (BEGIN IMMEDIATE) y no solo con db_lock, que es de ESTE proceso: si
    # otro proceso guarda el mismo presupuesto, este espera a que termine y lo ve, en vez de
    # mirar, no encontrar nada y guardar otro (lo señaló una revisión de código con ChatGPT;
    # ver pruebas_de_los_frenos.py, 10).
    with db_lock, transaccion():
        c.execute("""SELECT 1 FROM presupuestos_mecanico
                     WHERE mecanico_id = ? AND COALESCE(cliente_nombre, '') = ? AND items_json = ?
                       AND mano_obra = ? AND creado_en >= datetime('now', '-2 minutes')""",
                  (mecanico_id, cliente_nombre.strip(), items_json, mano_obra))
        if c.fetchone():
            return total
        c.execute(
            "INSERT INTO presupuestos_mecanico (mecanico_id, cliente_nombre, items_json, mano_obra, total) "
            "VALUES (?, ?, ?, ?, ?)",
            (mecanico_id, cliente_nombre.strip(), items_json, mano_obra, total)
        )
    return total


def listar_presupuestos_mecanico(mecanico_id):
    exigir_que_sea_su_cuenta(mecanico_id, "ver los presupuestos", None)
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
        linea = f"- {it['codigo']} ({it['marca']}) x{it['cantidad']} - ${miles(subtotal, 0)}"
        pdf.multi_cell(0, 6, limpiar(linea), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, limpiar(f"Mano de obra: ${miles(mano_obra, 0)}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, limpiar(f"TOTAL: ${miles(total, 0)}"), new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


# ============================================================
# CUENTA CORRIENTE DE LOS TALLERES
# ============================================================
# Lo que cada taller se lleva fiado y lo que va pagando, con plazo, límite y cheques diferidos.
# Y el CÓDIGO DE RETIRO: el taller lo genera en su portal (un solo uso, 24 horas) y se lo da a
# quien manda a buscar; sin él, el mostrador no puede cargarle nada a su cuenta. Es la forma
# práctica de lo que otra IA proponía como «OTP o biometría para retirar a nombre de un
# taller»: alguien que se presenta diciendo «vengo de parte de Pérez» no alcanza.
VIGENCIA_DEL_CODIGO_DE_RETIRO_HORAS = 24
MEDIOS_DE_PAGO = ["Efectivo", "Transferencia", "Cheque", "Otro"]


def _hash_del_codigo(codigo, salt):
    return hashlib.sha256(f"{salt}:{codigo}".encode()).hexdigest()


def configuracion_de_cuenta(mecanico_id):
    """{limite, dias_de_plazo, pide_codigo, descuento, cobra_mora}. Sin configurar: sin
    límite, 30 días, pide código, sin descuento y sin recargo por mora."""
    c.execute("SELECT limite, dias_de_plazo, pide_codigo, descuento, cobra_mora "
              "FROM cuentas_de_taller WHERE mecanico_id = ?", (mecanico_id,))
    f = c.fetchone()
    return {"limite": float(f["limite"] or 0) if f else 0.0,
            "dias_de_plazo": (int(f["dias_de_plazo"]) if f and f["dias_de_plazo"] is not None
                              else 30),
            "pide_codigo": bool(f["pide_codigo"]) if f else True,
            "descuento": float(f["descuento"] or 0) if f else 0.0,
            "cobra_mora": bool(f["cobra_mora"]) if f else False}


# El descuento más alto que se acepta. Un 100% es regalar, y un 1.000% escrito de más daría
# cargos negativos: la cuenta quedaría a favor del taller.
DESCUENTO_MAXIMO = 90.0


def configurar_cuenta_de_taller(mecanico_id, limite, dias_de_plazo, pide_codigo, descuento=None,
                                cobra_mora=None):
    """Guarda la configuración. descuento=None y cobra_mora=None dejan lo que tenía."""
    exigir_nivel("admin", "cambiar la configuración de una cuenta")
    antes = configuracion_de_cuenta(mecanico_id)
    if descuento is None:
        descuento = antes["descuento"]
    descuento = min(DESCUENTO_MAXIMO, max(0.0, float(descuento or 0)))
    if cobra_mora is None:
        cobra_mora = antes["cobra_mora"]
    with db_lock:
        c.execute("""INSERT INTO cuentas_de_taller (mecanico_id, limite, dias_de_plazo, pide_codigo,
                                                    descuento, cobra_mora)
                     VALUES (?, ?, ?, ?, ?, ?)
                     ON CONFLICT(mecanico_id) DO UPDATE SET limite = excluded.limite,
                        dias_de_plazo = excluded.dias_de_plazo,
                        pide_codigo = excluded.pide_codigo,
                        descuento = excluded.descuento,
                        cobra_mora = excluded.cobra_mora""",
                  (mecanico_id, max(0.0, float(limite or 0)), max(0, int(dias_de_plazo or 0)),
                   1 if pide_codigo else 0, descuento, 1 if cobra_mora else 0))
        despues = configuracion_de_cuenta(mecanico_id)
        if despues != antes:
            anotar_cambio("configuró la cuenta", "taller", mecanico_id,
                          {k: v for k, v in antes.items() if despues[k] != v},
                          {k: v for k, v in despues.items() if antes[k] != v})
        conn.commit()


def estado_de_cuenta(mecanico_id):
    """Saldo, vencido, disponible y cheques en cartera de un taller.

    VENCIDO: los pagos se imputan a lo más viejo, así que lo vencido es lo que queda del saldo
    después de descontar los cargos que todavía no vencieron (y nunca más que el saldo)."""
    exigir_que_sea_su_cuenta(mecanico_id, "ver el estado de la cuenta", None)
    c.execute("""SELECT COALESCE(SUM(importe), 0) AS saldo,
                        COALESCE(SUM(CASE WHEN importe > 0 AND vence >= date('now', 'localtime')
                                          THEN importe END), 0) AS a_vencer
                 FROM movimientos_de_cuenta WHERE mecanico_id = ? AND anulado = 0""",
              (mecanico_id,))
    f = c.fetchone()
    saldo, a_vencer = float(f["saldo"]), float(f["a_vencer"])
    config = configuracion_de_cuenta(mecanico_id)
    c.execute("""SELECT COALESCE(SUM(-importe), 0) AS total, COUNT(*) AS cuantos
                 FROM movimientos_de_cuenta
                 WHERE mecanico_id = ? AND anulado = 0 AND medio = 'Cheque'
                   AND cheque_fecha > date('now', 'localtime')""", (mecanico_id,))
    ch = c.fetchone()
    return {"saldo": saldo,
            "vencido": max(0.0, min(saldo, saldo - a_vencer)),
            "limite": config["limite"],
            "disponible": (config["limite"] - saldo) if config["limite"] else None,
            "cheques_en_cartera": float(ch["total"]), "cheques_cuantos": int(ch["cuantos"])}


def movimientos_de_cuenta(mecanico_id, limite=200):
    """Los movimientos, del más nuevo al más viejo, con el saldo después de cada uno."""
    exigir_que_sea_su_cuenta(mecanico_id, "ver los movimientos de la cuenta", None)
    c.execute("""SELECT id, fecha, concepto, importe, vence, medio, cheque_fecha, usuario, anulado
                 FROM movimientos_de_cuenta WHERE mecanico_id = ? ORDER BY id""", (mecanico_id,))
    filas, saldo = [], 0.0
    for f in c.fetchall():
        if not f["anulado"]:
            saldo += f["importe"]
        filas.append({
            "ID": f["id"], "Fecha": (f["fecha"] or "")[:16],
            "Concepto": (f["concepto"] or "") + (" (ANULADO)" if f["anulado"] else ""),
            "Debe": f["importe"] if f["importe"] > 0 else None,
            "Haber": -f["importe"] if f["importe"] < 0 else None,
            "Saldo": saldo,
            "Vence / cheque": f["vence"] or (f"cheque al {f['cheque_fecha']}"
                                             if f["cheque_fecha"] else (f["medio"] or "")),
            "Cargó": f["usuario"] or ""})
    return list(reversed(filas))[:limite]


def generar_codigo_de_retiro(mecanico_id):
    """Un código nuevo de 6 cifras para este taller; los anteriores sin usar dejan de valer.
    Devuelve (código, hasta cuándo vale). El código no se guarda: solo su hash."""
    exigir_que_sea_su_cuenta(mecanico_id, "generar un código de retiro", "empleado")
    import secrets
    codigo = f"{secrets.randbelow(1_000_000):06d}"
    salt = secrets.token_hex(8)
    vence = (datetime.now() + timedelta(hours=VIGENCIA_DEL_CODIGO_DE_RETIRO_HORAS)
             ).strftime("%Y-%m-%d %H:%M:%S")
    with db_lock:
        with transaccion():
            c.execute("""UPDATE codigos_de_retiro SET vence = datetime('now', 'localtime')
                         WHERE mecanico_id = ? AND usado_en IS NULL""", (mecanico_id,))
            c.execute("""INSERT INTO codigos_de_retiro (mecanico_id, codigo_hash, salt, vence)
                         VALUES (?, ?, ?, ?)""",
                      (mecanico_id, _hash_del_codigo(codigo, salt), salt, vence))
    return codigo, vence[:16]


def _codigo_de_retiro_vigente(mecanico_id, codigo):
    """El id del código si es de este taller, no se usó y no venció. None si no."""
    codigo = re.sub(r"\D", "", str(codigo or ""))
    if len(codigo) != 6:
        return None
    c.execute("""SELECT id, codigo_hash, salt FROM codigos_de_retiro
                 WHERE mecanico_id = ? AND usado_en IS NULL
                   AND vence > datetime('now', 'localtime')""", (mecanico_id,))
    for f in c.fetchall():
        if hmac.compare_digest(f["codigo_hash"], _hash_del_codigo(codigo, f["salt"])):
            return f["id"]
    return None


def cargar_a_la_cuenta(mecanico_id, concepto, importe, codigo_de_retiro="", usuario="",
                       pasar_el_limite=False):
    """Carga lo que se llevó a la cuenta del taller. Devuelve (True, aviso) o (False, por qué no).

    Pide el código de retiro si la cuenta lo pide (así viene por defecto), y lo gasta: el
    mismo código no sirve para dos retiros. Si el cargo pasa el límite de crédito, no lo hace
    salvo con un permiso vigente (ver pedir_permiso_de_limite()) o si un administrador lo pide
    explícitamente (pasar_el_limite)."""
    try:
        importe = round(float(importe), 2)
    except (TypeError, ValueError):
        return False, "El importe no es un número."
    if importe <= 0:
        return False, "El importe tiene que ser mayor que cero."
    if pasar_el_limite:
        # Pasarlo sin un permiso, solo un administrador: el resto lo pide. Hasta acá «Cargar igual
        # aunque pase el límite» lo podía tildar cualquier empleado que entrara a la pantalla.
        exigir_nivel("admin", "pasar el límite de crédito sin un permiso")
    with db_lock:
        with transaccion():
            # EL LÍMITE, ADENTRO DEL CANDADO Y DE LA TRANSACCIÓN (BEGIN IMMEDIATE), como en
            # pedir_al_deposito(). Se miraba antes: con $90.000 de deuda y $100.000 de límite,
            # ocho cargos de $8.000 al mismo tiempo veían todos «hay lugar» y entraban todos
            # (medido: la deuda quedaba en $154.000). Lo señaló una revisión de código con
            # ChatGPT. Ver pruebas_de_las_cuentas.py.
            config = configuracion_de_cuenta(mecanico_id)
            estado = estado_de_cuenta(mecanico_id)
            # Lo pedido al depósito y todavía sin entregar también cuenta, como en
            # pedir_al_deposito(): se carga a la cuenta cuando se entrega.
            pedido = (_pendiente_de_la_cuenta(mecanico_id, config["descuento"])
                      if config["limite"] else 0.0)
            autorizacion_id = None
            if (config["limite"] and estado["saldo"] + pedido + importe > config["limite"] + 0.005
                    and not pasar_el_limite):
                margen, autorizacion_id = margen_autorizado(mecanico_id)
                if estado["saldo"] + pedido + importe > config["limite"] + margen + 0.005:
                    return False, (f"{PASA_EL_LIMITE}: debe ${miles(estado['saldo'], 0)}"
                                   + (f", tiene pedido sin entregar ${miles(pedido, 0)}"
                                      if pedido else "")
                                   + f", el límite es ${miles(config['limite'], 0)}"
                                   + (f" (más ${miles(margen, 0)} de un permiso)" if margen else "")
                                   + f" y esto suma ${miles(importe, 0)}. {SE_PUEDE_PEDIR_PERMISO}")
            vence = (date.today() + timedelta(days=config["dias_de_plazo"])).isoformat()
            codigo_id = None
            if config["pide_codigo"]:
                codigo_id = _codigo_de_retiro_vigente(mecanico_id, codigo_de_retiro)
                if not codigo_id:
                    return False, ("El código de retiro no es válido, ya se usó o venció. El "
                                   "taller genera uno nuevo en su portal.")
            c.execute("""INSERT INTO movimientos_de_cuenta
                            (mecanico_id, concepto, importe, vence, usuario, autorizacion_id)
                         VALUES (?, ?, ?, ?, ?, ?)""",
                      (mecanico_id, (concepto or "").strip() or "Repuestos", importe, vence,
                       usuario, autorizacion_id))
            movimiento_id = c.lastrowid
            if codigo_id:
                c.execute("""UPDATE codigos_de_retiro SET usado_en = datetime('now', 'localtime'),
                                    movimiento_id = ? WHERE id = ?""", (movimiento_id, codigo_id))
            pasa = config["limite"] and estado["saldo"] + pedido + importe > config["limite"] + 0.005
            if pasa and pasar_el_limite:
                anotar_cambio("pasó el límite sin permiso", "cuenta", mecanico_id,
                              detalle=f"cargo de ${miles(importe, 0)}: {(concepto or '').strip()}",
                              usuario=usuario or None)
    aviso = f"Cargado: ${miles(importe, 0)}, vence el {vence}."
    if pasa:
        aviso += (" Quedó por encima del límite de crédito, con el permiso que había."
                  if autorizacion_id else " Quedó por encima del límite de crédito.")
    return True, aviso


def registrar_pago_de_cuenta(mecanico_id, importe, medio, concepto="", cheque_fecha=None,
                             usuario=""):
    """Un pago del taller. Con cheque diferido, la fecha del cheque queda anotada: el pago
    descuenta ya, y aparece en «cheques en cartera» hasta esa fecha."""
    exigir_nivel("empleado", "registrar un pago de una cuenta")
    try:
        importe = round(float(importe), 2)
    except (TypeError, ValueError):
        return False, "El importe no es un número."
    if importe <= 0:
        return False, "El importe tiene que ser mayor que cero."
    if medio not in MEDIOS_DE_PAGO:
        return False, "Elegí cómo pagó."
    if isinstance(cheque_fecha, (tuple, list)):
        cheque_fecha = cheque_fecha[0] if cheque_fecha else None
    if medio == "Cheque" and not cheque_fecha:
        return False, "Poné la fecha del cheque: hasta esa fecha queda en cartera, sin cobrar."
    with db_lock:
        c.execute("""INSERT INTO movimientos_de_cuenta
                        (mecanico_id, concepto, importe, medio, cheque_fecha, usuario)
                     VALUES (?, ?, ?, ?, ?, ?)""",
                  (mecanico_id, (concepto or "").strip() or f"Pago ({medio.lower()})", -importe,
                   medio, str(cheque_fecha) if (medio == "Cheque" and cheque_fecha) else None,
                   usuario))
        conn.commit()
    return True, f"Pago registrado: ${miles(importe, 0)}."


def anular_movimiento_de_cuenta(movimiento_id):
    """No se borra: queda tachado («ANULADO») para que se vea qué pasó."""
    exigir_nivel("admin", "anular un movimiento de cuenta")
    with db_lock:
        c.execute("SELECT mecanico_id, concepto, importe FROM movimientos_de_cuenta WHERE id = ?",
                  (movimiento_id,))
        antes = c.fetchone()
        c.execute("UPDATE movimientos_de_cuenta SET anulado = 1 WHERE id = ?", (movimiento_id,))
        anotar_cambio("anuló movimiento de cuenta", "movimiento", movimiento_id,
                      antes=dict(antes) if antes else None)
        conn.commit()


# ============================================================
# PASAR EL LÍMITE CON PERMISO
# ============================================================
# Lo pidió el dueño: cuando el límite de crédito frena una venta, el que atiende puede pedir
# permiso para seguir vendiendo, y solo un administrador —el que tiene todos los permisos— lo
# da. Hasta acá no había término medio: el pedido al depósito no pasaba nunca, y en Cuentas
# corrientes «Cargar igual aunque pase el límite» lo podía tildar cualquier empleado.
#
# UN PERMISO ES UN MONTO DE MÁS PARA UNA CUENTA, POR UN RATO: mientras vale, el tope de esa
# cuenta es el límite más lo autorizado. Así sirve igual para un cargo suelto que para un
# presupuesto de diez ítems pedido de una vez (cada ítem se mira contra el mismo tope), y no se
# puede estirar: lo vendido con él ya suma a la deuda. Vencido, el tope vuelve a ser el límite.
# Lo que se vendió gracias a uno queda con su número (autorizacion_id) en el cargo o el pedido.
HORAS_QUE_VALE_UN_PERMISO = 24
PASA_EL_LIMITE = "Pasa el límite de crédito"
SE_PUEDE_PEDIR_PERMISO = "Se le puede pedir permiso a un administrador."


def es_por_el_limite(aviso):
    """¿Ese «no» es por el límite de crédito (y entonces se puede pedir permiso)?"""
    return str(aviso or "").startswith(PASA_EL_LIMITE)


def margen_autorizado(mecanico_id):
    """(cuánto de más se autorizó y sigue vigente, el número del permiso más nuevo o None).
    No toma el candado: se llama adentro de las transacciones que miran el límite."""
    c.execute("""SELECT id, importe FROM permisos_de_credito
                 WHERE mecanico_id = ? AND estado = 'autorizada'
                   AND vence > datetime('now', 'localtime')
                 ORDER BY id DESC""", (mecanico_id,))
    filas = c.fetchall()
    return round(sum(float(r["importe"]) for r in filas), 2), (filas[0]["id"] if filas else None)


def cuanto_pasa_del_limite(mecanico_id, importe):
    """Cuánto le falta de tope a esta cuenta para `importe` más, contando lo pedido sin entregar
    y los permisos vigentes. 0 si entra. Es lo que se sugiere pedir."""
    config = configuracion_de_cuenta(mecanico_id)
    if not config["limite"]:
        return 0.0
    saldo = estado_de_cuenta(mecanico_id)["saldo"]
    pedido = _pendiente_de_la_cuenta(mecanico_id, config["descuento"])
    margen = margen_autorizado(mecanico_id)[0]
    return round(max(0.0, saldo + pedido + float(importe or 0) - config["limite"] - margen), 2)


def puede_autorizar_limites():
    """Solo el administrador; o cualquiera si la app todavía no tiene contraseñas (abierta a
    propósito, con el aviso de siempre: ver seccion_permitida())."""
    return es_admin() or not hay_claves_configuradas()


def pedir_permiso_de_limite(mecanico_id, importe, motivo, usuario=""):
    """El que atiende pide permiso para vender `importe` de más a esa cuenta. (True, aviso) o
    (False, por qué no). Un pedido por cuenta a la vez: el segundo no se suma, dice cuál espera."""
    exigir_nivel("empleado", "pedir permiso para pasar el límite de crédito")
    try:
        importe = round(float(importe), 2)
    except (TypeError, ValueError):
        return False, "El monto no es un número."
    if importe <= 0:
        return False, "Decí cuánto de más hace falta."
    motivo = (motivo or "").strip()
    if not motivo:
        return False, "Decí por qué: es lo que lee el que lo autoriza."
    if not configuracion_de_cuenta(mecanico_id)["limite"]:
        return False, "Esa cuenta no tiene límite de crédito: no hace falta permiso."
    quien = usuario or obtener_usuario_actual()
    with db_lock, transaccion():
        c.execute("""SELECT importe, pedido_por, pedido_en FROM permisos_de_credito
                     WHERE mecanico_id = ? AND estado = 'pendiente'
                       AND pedido_en > datetime('now', 'localtime', ?)""",
                  (mecanico_id, f"-{HORAS_QUE_VALE_UN_PERMISO} hours"))
        ya = c.fetchone()
        if ya:
            return False, (f"Ya hay un pedido sin contestar para esta cuenta: ${miles(ya['importe'], 0)}"
                           f", de {ya['pedido_por'] or 'alguien'} a las {str(ya['pedido_en'])[11:16]}.")
        c.execute("""INSERT INTO permisos_de_credito (mecanico_id, importe, motivo, pedido_por)
                     VALUES (?, ?, ?, ?)""", (mecanico_id, importe, motivo[:300], quien))
        anotar_cambio("pidió permiso para pasar el límite", "cuenta", mecanico_id,
                      detalle=f"${miles(importe, 0)} de más: {motivo[:300]}", usuario=quien)
    return True, ("🙋 Pedido. Lo ve un administrador arriba de todo y en Administrar → 💳 Cuentas "
                  "corrientes; cuando lo autorice, volvé a tocar el botón.")


def contestar_permiso_de_limite(autorizacion_id, autorizar, nota="", importe=None, usuario=""):
    """Un administrador lo autoriza (por lo pedido o por `importe`) o no. Vale
    HORAS_QUE_VALE_UN_PERMISO desde ahora. Solo lo que sigue esperando y es de las últimas
    HORAS_QUE_VALE_UN_PERMISO: lo contestado por otro, o lo muy viejo, no se toca."""
    exigir_nivel("admin", "autorizar a pasar el límite de crédito")
    quien = usuario or obtener_usuario_actual()
    if importe is not None:
        try:
            importe = round(float(importe), 2)
        except (TypeError, ValueError):
            return False, "El monto no es un número."
        if autorizar and importe <= 0:
            return False, "Para autorizar, un monto mayor que cero."
    with db_lock, transaccion():
        c.execute("""UPDATE permisos_de_credito
                     SET estado = ?, resuelto_por = ?, resuelto_en = datetime('now', 'localtime'),
                         nota = ?, importe = COALESCE(?, importe),
                         vence = CASE WHEN ? THEN datetime('now', 'localtime', ?) END
                     WHERE id = ? AND estado = 'pendiente'
                       AND pedido_en > datetime('now', 'localtime', ?)""",
                  ("autorizada" if autorizar else "rechazada", quien, (nota or "").strip()[:300],
                   importe if autorizar else None, 1 if autorizar else 0,
                   f"+{HORAS_QUE_VALE_UN_PERMISO} hours", autorizacion_id,
                   f"-{HORAS_QUE_VALE_UN_PERMISO} hours"))
        if c.rowcount != 1:
            return False, ("Ese pedido ya no está esperando: lo contestó otro, o es de hace más de "
                           f"{HORAS_QUE_VALE_UN_PERMISO} horas (que lo pidan de nuevo).")
        c.execute("SELECT mecanico_id, importe, vence FROM permisos_de_credito WHERE id = ?",
                  (autorizacion_id,))
        fila = c.fetchone()
        anotar_cambio("autorizó pasar el límite" if autorizar else "no autorizó pasar el límite",
                      "cuenta", fila["mecanico_id"],
                      detalle=f"permiso {autorizacion_id}: ${miles(fila['importe'], 0)}"
                              + (f" · {nota.strip()}" if (nota or "").strip() else ""),
                      usuario=quien)
    if autorizar:
        return True, (f"✅ Autorizado: ${miles(fila['importe'], 0)} de más, hasta el "
                      f"{fila['vence'][8:10]}/{fila['vence'][5:7]} a las {fila['vence'][11:16]}.")
    return True, "🚫 No autorizado. Lo ve el que lo pidió."


def permisos_de_limite(mecanico_id=None, solo_esperando=False, limite=30):
    """Los pedidos de permiso, del más nuevo al más viejo, con la cuenta, si sigue esperando, si
    está vigente y en cuántas ventas se usó."""
    c.execute(f"""SELECT a.id, a.mecanico_id, k.nombre AS cuenta, a.importe, a.motivo, a.pedido_por,
                         a.pedido_en, a.estado, a.resuelto_por, a.resuelto_en, a.nota, a.vence,
                         (a.estado = 'pendiente'
                          AND a.pedido_en > datetime('now', 'localtime', ?)) AS esperando,
                         (a.estado = 'autorizada'
                          AND a.vence > datetime('now', 'localtime')) AS vigente,
                         (SELECT COUNT(*) FROM movimientos_de_cuenta m
                          WHERE m.autorizacion_id = a.id AND m.anulado = 0)
                         + (SELECT COUNT(*) FROM pedidos_deposito d
                            WHERE d.autorizacion_id = a.id AND d.estado <> 'cancelado') AS usos
                  FROM permisos_de_credito a LEFT JOIN mecanicos k ON k.id = a.mecanico_id
                  WHERE (? IS NULL OR a.mecanico_id = ?)
                  {"AND a.estado = 'pendiente' AND a.pedido_en > datetime('now', 'localtime', ?)"
                   if solo_esperando else "AND ? IS NULL"}
                  ORDER BY a.id DESC LIMIT ?""",
              (f"-{HORAS_QUE_VALE_UN_PERMISO} hours", mecanico_id, mecanico_id,
               f"-{HORAS_QUE_VALE_UN_PERMISO} hours" if solo_esperando else None, limite))
    return [dict(r) for r in c.fetchall()]


def cuantos_permisos_esperando():
    c.execute("""SELECT COUNT(*) FROM permisos_de_credito
                 WHERE estado = 'pendiente' AND pedido_en > datetime('now', 'localtime', ?)""",
              (f"-{HORAS_QUE_VALE_UN_PERMISO} hours",))
    return c.fetchone()[0]


def _hora_del_permiso(fecha_y_hora):
    texto = str(fecha_y_hora or "")
    return (texto[11:16] if texto[:10] == date.today().isoformat()
            else f"{texto[8:10]}/{texto[5:7]} {texto[11:16]}")


def mostrar_permiso_de_limite(mecanico_id, exceso, clave):
    """Abajo de un «Pasa el límite»: cómo está el permiso de esa cuenta y, si no hay uno
    esperando, el recuadro para pedirlo. `exceso` es lo que se sugiere pedir."""
    ultimo = (permisos_de_limite(mecanico_id=mecanico_id, limite=1) or [None])[0]
    if ultimo and ultimo["esperando"]:
        st.info(f"⏳ Se pidió permiso por ${miles(ultimo['importe'], 0)} a las "
                f"{_hora_del_permiso(ultimo['pedido_en'])} y todavía no lo contestaron. Lo "
                "autoriza un administrador; cuando lo haga, volvé a tocar el botón.")
        if puede_autorizar_limites():
            mostrar_contestar_permiso(ultimo, f"{clave}_ya")
        return
    if ultimo and ultimo["vigente"]:
        st.success(f"✅ {ultimo['resuelto_por'] or 'Un administrador'} autorizó "
                   f"${miles(ultimo['importe'], 0)} de más, hasta las "
                   f"{_hora_del_permiso(ultimo['vence'])}. Con esto todavía no alcanza: se "
                   "puede pedir más.")
    elif ultimo and ultimo["estado"] == "rechazada" and str(ultimo["resuelto_en"] or "")[:10] == \
            date.today().isoformat():
        st.warning(f"🚫 {ultimo['resuelto_por'] or 'Un administrador'} no lo autorizó a las "
                   f"{_hora_del_permiso(ultimo['resuelto_en'])}"
                   + (f": {ultimo['nota']}" if ultimo["nota"] else "") + ".")
    with st.form(f"permiso_limite_{clave}", clear_on_submit=True):
        st.markdown("**🙋 Pedir permiso para pasar el límite**")
        monto = st.number_input("¿Cuánto de más hace falta? ($)", min_value=0.0, step=1000.0,
                                value=float(-(-max(exceso, 0) // 100) * 100))
        motivo = st.text_input("¿Por qué? (lo lee el que autoriza)", max_chars=300,
                               placeholder="Ej.: paga el viernes, cliente de hace años")
        if st.form_submit_button("🙋 Pedir permiso a un administrador", type="primary"):
            try:
                ok, aviso = pedir_permiso_de_limite(mecanico_id, monto, motivo)
            except PermissionError as _err:
                ok, aviso = False, str(_err)
            (st.success if ok else st.error)(aviso)


def _contestar_desde_la_pantalla(autorizacion_id, autorizar, clave):
    try:
        ok, aviso = contestar_permiso_de_limite(
            autorizacion_id, autorizar, st.session_state.get(f"nota_permiso_{clave}", ""),
            st.session_state.get(f"monto_permiso_{clave}") if autorizar else None)
    except PermissionError as _err:
        ok, aviso = False, str(_err)
    avisar("success" if ok else "error", aviso)


def mostrar_contestar_permiso(permiso, clave):
    """Autorizar (por lo pedido o por otro monto) o no. Solo se dibuja para quien puede: ver
    puede_autorizar_limites(). La función vuelve a mirarlo igual."""
    _m, _n = st.columns([1, 2])
    _m.number_input("Monto ($)", min_value=0.0, step=1000.0, value=float(permiso["importe"]),
                    key=f"monto_permiso_{clave}")
    _n.text_input("Nota (opcional)", max_chars=300, key=f"nota_permiso_{clave}")
    _si, _no = st.columns(2)
    _si.button("✅ Autorizar", type="primary", key=f"si_permiso_{clave}", width="stretch",
               on_click=_contestar_desde_la_pantalla, args=(permiso["id"], True, clave))
    _no.button("🚫 No autorizar", key=f"no_permiso_{clave}", width="stretch",
               on_click=_contestar_desde_la_pantalla, args=(permiso["id"], False, clave))


def mostrar_permisos_de_limite():
    """En Cuentas corrientes: lo que espera respuesta, con la cuenta como está hoy, y los
    últimos contestados con en cuántas ventas se usaron."""
    esperando = permisos_de_limite(solo_esperando=True)
    if esperando:
        st.markdown(f"**🙋 {len(esperando)} pedido(s) de permiso para pasar el límite**")
        for p in esperando:
            with st.container(border=True):
                _estado = estado_de_cuenta(p["mecanico_id"])
                _config = configuracion_de_cuenta(p["mecanico_id"])
                st.markdown(f"**{p['cuenta'] or 'Cuenta borrada'}** — "
                            f"${miles(p['importe'], 0)} de más · lo pidió "
                            f"{p['pedido_por'] or 'alguien'} a las "
                            f"{_hora_del_permiso(p['pedido_en'])}")
                st.caption(f"Por qué: {p['motivo']}  \nHoy debe \\${miles(_estado['saldo'], 0)} "
                           f"(vencido \\${miles(_estado['vencido'], 0)}), el límite es "
                           f"\\${miles(_config['limite'], 0)} y tiene pedido sin entregar "
                           f"\\${miles(_pendiente_de_la_cuenta(p['mecanico_id'], _config['descuento']), 0)}.")
                if puede_autorizar_limites():
                    mostrar_contestar_permiso(p, f"lista_{p['id']}")
                else:
                    st.caption("🔒 Lo autoriza un administrador (el que tiene todos los permisos).")
    historial = [p for p in permisos_de_limite(limite=40) if not p["esperando"]]
    if historial and st.toggle("📜 Los últimos permisos contestados", key="permisos_historial"):
        st.dataframe([{"Cuenta": p["cuenta"], "Monto": p["importe"],
                       "Estado": ("✅ vigente" if p["vigente"] else
                                  "✅ vencido" if p["estado"] == "autorizada" else
                                  "🚫 no" if p["estado"] == "rechazada" else "⌛ sin contestar"),
                       "Pidió": p["pedido_por"], "Por qué": p["motivo"],
                       "Contestó": p["resuelto_por"], "Cuándo": p["resuelto_en"],
                       "Nota": p["nota"], "Ventas con el permiso": p["usos"]}
                      for p in historial], width="stretch", hide_index=True)


# ============================================================
# INTERÉS POR MORA (con la tasa del BCRA)
# ============================================================
# A los talleres se les fía, y con inflación un saldo vencido que se paga tres meses tarde se
# paga con plata que vale menos. La app sugiere el interés con una tasa oficial y pública —la
# del BCRA que se elija (ver tasas_de_referencia() en logica/salud.py)— más los puntos que se
# quieran sumar. Nunca lo carga sola: se mira y se carga con un botón.
# CUENTA POR CUENTA: solo a las que tienen prendido el recargo (ver configurar_cuenta_de_taller()).
#
# CÓMO SE CALCULA. Interés simple por días, solo sobre lo VENCIDO E IMPAGO de cada cargo: los
# pagos se imputan a los cargos más viejos (como «Vencido» en estado_de_cuenta()), y lo que
# queda de cada cargo después de su vencimiento genera saldo × TNA × días / 365.
# NO SE COBRA DOS VECES. Al cargarlo queda un movimiento «Interés por mora…»; el cálculo
# siguiente cuenta desde la fecha del último que no esté anulado. Si se anula, esos días
# vuelven a contar solos: no hay una fecha guardada aparte que se desincronice.
PREFIJO_DEL_INTERES = "Interés por mora"
CONFIG_DE_LA_MORA = "tasa_de_mora"


def configuracion_de_la_mora():
    """{"referencia": clave de TASAS_DE_REFERENCIA, "puntos": lo que se suma a la TNA}."""
    try:
        cfg = json.loads(obtener_config(CONFIG_DE_LA_MORA, "") or "{}")
    except (ValueError, TypeError):
        cfg = {}
    return {"referencia": cfg.get("referencia") or TASAS_DE_REFERENCIA[0][0],
            "puntos": float(cfg.get("puntos") or 0)}


def guardar_configuracion_de_la_mora(referencia, puntos):
    exigir_nivel("admin", "cambiar la tasa del interés por mora")
    anotar_cambio("cambió la tasa de mora", "configuración", "tasa_de_mora",
                  configuracion_de_la_mora(), {"referencia": referencia, "puntos": puntos})
    guardar_config(CONFIG_DE_LA_MORA, json.dumps(
        {"referencia": referencia, "puntos": min(200.0, max(0.0, float(puntos or 0)))}))


def tasa_de_mora():
    """(TNA en %, de dónde sale) o (None, por qué no). Si la elegida no vino, la primera que
    haya, y lo dice."""
    cfg = configuracion_de_la_mora()
    tasas = tasas_de_referencia()
    elegida = tasas.get(cfg["referencia"])
    if not elegida:
        elegida = next((tasas[k] for k, _n, _p in TASAS_DE_REFERENCIA if k in tasas), None)
    if not elegida:
        return None, "No se pudo traer ninguna tasa del BCRA todavía."
    tna = round(elegida["tna"] + cfg["puntos"], 2)
    origen = (f"{elegida['nombre']} del BCRA ({miles(elegida['tna'], 2)}% TNA"
              + (f", al {elegida['fecha']}" if elegida.get("fecha") else "") + ")"
              + (f" + {miles(cfg['puntos'], 2)} puntos" if cfg["puntos"] else ""))
    return tna, origen


def _interes_cobrado_hasta(mecanico_id):
    c.execute("""SELECT MAX(date(fecha)) FROM movimientos_de_cuenta
                 WHERE mecanico_id = ? AND anulado = 0 AND concepto LIKE ?""",
              (mecanico_id, PREFIJO_DEL_INTERES + "%"))
    valor = c.fetchone()[0]
    try:
        return date.fromisoformat(valor) if valor else None
    except ValueError:
        return None


def interes_por_mora(mecanico_id, tna, hoy=None):
    """{"total", "desde": hasta dónde ya se cobró (o None), "renglones": [{"Cargo", "Venció",
    "Cuenta desde", "Días", "Impago", "Interés"}]}. Ver «INTERÉS POR MORA»."""
    hoy = hoy or date.today()
    c.execute("""SELECT COALESCE(SUM(-importe), 0) FROM movimientos_de_cuenta
                 WHERE mecanico_id = ? AND anulado = 0 AND importe < 0""", (mecanico_id,))
    pagos = float(c.fetchone()[0])
    # Antes de la consulta de los cargos: usa el mismo cursor, y en el medio pisaba su
    # resultado (medido: el interés daba siempre cero).
    cobrado_hasta = _interes_cobrado_hasta(mecanico_id)
    c.execute("""SELECT fecha, concepto, importe, vence FROM movimientos_de_cuenta
                 WHERE mecanico_id = ? AND anulado = 0 AND importe > 0
                 ORDER BY COALESCE(vence, substr(fecha, 1, 10)), id""", (mecanico_id,))
    renglones, total = [], 0.0
    for f in c.fetchall():
        cubre = min(pagos, float(f["importe"]))
        pagos -= cubre
        impago = float(f["importe"]) - cubre
        try:
            vencio = date.fromisoformat(str(f["vence"] or "")[:10])
        except ValueError:
            continue
        if impago < 0.01 or vencio >= hoy:
            continue
        desde = max(vencio, cobrado_hasta) if cobrado_hasta else vencio
        dias = (hoy - desde).days
        if dias <= 0:
            continue
        interes = impago * float(tna) / 100 * dias / 365
        total += interes
        renglones.append({"Cargo": (f["concepto"] or "")[:60], "Venció": vencio.isoformat(),
                          "Cuenta desde": desde.isoformat(), "Días": dias,
                          "Impago": round(impago, 2), "Interés": round(interes, 2)})
    return {"total": round(total, 2), "desde": cobrado_hasta, "renglones": renglones}


def cargar_el_interes_por_mora(mecanico_id, tna, origen="", usuario="", hoy=None):
    """Carga en la cuenta el interés calculado hoy. (True, aviso) o (False, por qué no). Se
    vuelve a calcular adentro, con el candado, por si alguien cargó otro pago mientras tanto."""
    exigir_nivel("admin", "cargar el interés por mora")
    hoy = hoy or date.today()
    if not configuracion_de_cuenta(mecanico_id)["cobra_mora"]:
        return False, ("Esta cuenta no tiene recargo por mora: se prende en «⚙️ Configuración "
                       "de la cuenta».")
    with db_lock, transaccion():
        calculo = interes_por_mora(mecanico_id, tna, hoy)
        if calculo["total"] < 1:
            return False, "No hay interés para cargar: no hay saldo vencido sin cobrar."
        vence = (hoy + timedelta(days=configuracion_de_cuenta(mecanico_id)["dias_de_plazo"]))
        c.execute("""INSERT INTO movimientos_de_cuenta (mecanico_id, fecha, concepto, importe,
                                                        vence, usuario)
                     VALUES (?, ?, ?, ?, ?, ?)""",
                  (mecanico_id, f"{hoy.isoformat()} {datetime.now():%H:%M:%S}",
                   f"{PREFIJO_DEL_INTERES} al {hoy:%d/%m/%Y} — TNA {miles(tna, 2)}%"
                   + (f" ({origen})" if origen else ""),
                   calculo["total"], vence.isoformat(), usuario))
        anotar_cambio("cargó interés por mora", "taller", mecanico_id,
                      despues={"importe": calculo["total"], "tna": tna}, usuario=usuario or None)
    return True, f"Interés cargado: ${miles(calculo['total'], 0)}, vence el {vence.isoformat()}."


def resumen_de_cuentas():
    """Una fila por taller con movimientos o con la cuenta configurada, los que más deben
    vencido primero."""
    c.execute("""SELECT id, nombre FROM mecanicos WHERE id IN (
                    SELECT mecanico_id FROM movimientos_de_cuenta
                    UNION SELECT mecanico_id FROM cuentas_de_taller)""")
    salida = []
    for f in c.fetchall():
        e = estado_de_cuenta(f["id"])
        salida.append({"ID": f["id"], "Taller": f["nombre"], "Saldo": e["saldo"],
                       "Vencido": e["vencido"], "Límite": e["limite"] or None,
                       "Disponible": e["disponible"],
                       "Cheques en cartera": e["cheques_en_cartera"] or None})
    salida.sort(key=lambda x: (-x["Vencido"], -x["Saldo"]))
    return salida


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
                precio_txt = f"${miles(fila['Precio'], 0)}" if fila.get("Precio") else "s/precio"
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
            coli1.write(f"{it['marca']} - {it['codigo']} x{it['cantidad']} — ${miles(subtotal_item, 0)}")
            coli2.button("🗑️", key=f"quitar_mec_{i}",
                          on_click=quitar_item_lista_sesion, args=("presupuesto_mecanico_items", i))

        cliente_nombre_mec = st.text_input("Nombre del cliente (opcional):", key="mec_cliente")
        mano_obra_mec = st.number_input("Mano de obra ($):", min_value=0.0, step=500.0, key="mec_mano_obra")
        total_mec = subtotal_repuestos + mano_obra_mec
        st.metric("Total", f"${miles(total_mec, 0)}")

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
            mensaje_mec += f"- {it['codigo']} ({it['marca']}) x{it['cantidad']} — ${miles(it['precio']*it['cantidad'], 0)}\n"
        mensaje_mec += f"Mano de obra: ${miles(mano_obra_mec, 0)}\nTOTAL: ${miles(total_mec, 0)}"
        url_wa_mec = "https://wa.me/?text=" + quote(mensaje_mec)
        colb3.link_button("📲 WhatsApp", url_wa_mec)
    else:
        st.caption("Todavía no agregaste ningún repuesto al presupuesto.")

    st.markdown("---")
    st.markdown("**💳 Mi cuenta corriente**")
    _estado_cc = estado_de_cuenta(mecanico_id)
    _cm1, _cm2, _cm3 = st.columns(3)
    _cm1.metric("Saldo", f"${miles(_estado_cc['saldo'], 0)}")
    _cm2.metric("Vencido", f"${miles(_estado_cc['vencido'], 0)}")
    _cm3.metric("Disponible", "sin límite" if _estado_cc["disponible"] is None
                else f"${miles(_estado_cc['disponible'], 0)}")
    st.caption("Para que alguien retire repuestos a tu nombre y se carguen a tu cuenta, generá "
               "un código y dáselo: vale una sola vez y por "
               f"{VIGENCIA_DEL_CODIGO_DE_RETIRO_HORAS} horas. Sin el código, en el mostrador no "
               "se puede cargar nada a tu cuenta.")
    if st.button("🔑 Generar código de retiro", key="mec_generar_codigo"):
        _codigo_r, _vence_r = generar_codigo_de_retiro(mecanico_id)
        st.session_state["mec_codigo_retiro"] = (_codigo_r, _vence_r)
    if st.session_state.get("mec_codigo_retiro"):
        _codigo_r, _vence_r = st.session_state["mec_codigo_retiro"]
        st.success(f"Tu código de retiro: **{_codigo_r}** — vale hasta el {_vence_r}, una sola "
                   "vez. Si generás otro, este deja de valer.")
    _movs_mec = movimientos_de_cuenta(mecanico_id, limite=30)
    if _movs_mec:
        st.dataframe(quitar_id(_movs_mec), width="stretch", hide_index=True)
    else:
        st.caption("Todavía no hay movimientos en tu cuenta.")

    st.markdown("---")
    st.markdown("**📁 Mis presupuestos anteriores**")
    anteriores = listar_presupuestos_mecanico(mecanico_id)
    if anteriores:
        for p in anteriores[:20]:
            with st.expander(f"{p['Fecha']} — {p['Cliente'] or 'sin nombre'} — ${miles(p['Total'], 0)}", key=f"exp_presupuesto_{p['ID']}"):
                items_p = json.loads(p["items_json"])
                for it in items_p:
                    st.write(f"- {it['codigo']} ({it['marca']}) x{it['cantidad']} — ${miles(it['precio']*it['cantidad'], 0)}")
                st.write(f"Mano de obra: ${miles(p['Mano de obra'], 0)}")
    else:
        st.caption("Todavía no guardaste ningún presupuesto.")


# ============================================================================================
# LA CONSULTA DEL CLIENTE: su auto, sin entrar a la app
# ============================================================================================
def mostrar_consulta_publica_del_auto(patente="", clave=""):
    """La página que abre el link «?auto=PATENTE&clave=…» (ver link_publico_del_auto()), o
    «?auto=» solo, para entrar con la patente y los últimos 4 números del teléfono. No muestra
    nada más del negocio: app.py corta después de esto. Ver «LO QUE VE EL CLIENTE DE SU AUTO»
    en logica/vehiculos.py."""
    st.markdown("### 🚗 Tu auto en El Chavo")
    st.caption("Lo que le pusimos a tu auto y cuánto le falta a cada cosa.")
    # El km que escribe el cliente se lee antes de dibujar su campo: la cuenta de abajo lo usa.
    # Ver resumen_publico_del_auto().
    _km_cliente = st.session_state.get("km_del_cliente")
    # Con los 4 números, lo que ya entró queda en la sesión: cada toque vuelve a correr la
    # página, y sin esto el cliente volvía al formulario apenas escribía su km.
    _entro = st.session_state.get("_consulta_publica")
    resumen, motivo = None, ""
    if patente and clave:
        resumen, motivo = abrir_ficha_publica(patente, clave=clave, km_de_hoy=_km_cliente)
    elif _entro:
        resumen, motivo = abrir_ficha_publica(_entro["patente"],
                                              ultimos_del_telefono=_entro["ultimos"],
                                              km_de_hoy=_km_cliente)
    if resumen is None:
        if motivo:
            st.warning(motivo)
        with st.form("form_consulta_publica"):
            _pat = st.text_input("Patente:", value=patente_sin_espacios(patente),
                                 placeholder="AB123CD", max_chars=10)
            _ultimos = st.text_input("Últimos 4 números del teléfono que dejaste en el negocio:",
                                     max_chars=4, placeholder="1234")
            _ver = st.form_submit_button("🔎 Ver mi auto", type="primary")
        if _ver:
            resumen, motivo = abrir_ficha_publica(_pat, ultimos_del_telefono=_ultimos)
            if resumen is None:
                st.warning(motivo)
            else:
                st.session_state["_consulta_publica"] = {"patente": _pat, "ultimos": _ultimos}
        if resumen is None:
            st.caption("Si tenés el link que te mandó el negocio, con eso entrás directo.")
            return

    st.markdown(f"**{resumen['patente']}**" + (f" — {resumen['auto']}" if resumen["auto"] else ""))
    if resumen["km_anotado"] is not None:
        _k1, _k2 = st.columns(2)
        _k1.metric("Km anotado", miles(resumen["km_anotado"]),
                   help=f"La última vez que pasó por el negocio ({resumen['km_anotado_el']}).")
        if resumen["km_del_cliente"]:
            _k2.metric("Km de hoy", miles(resumen["km_hoy"]), help="El que escribiste abajo.")
        elif resumen["km_por_dia"]:
            _k2.metric("Km hoy (estimado)", miles(resumen["km_hoy"]),
                       help=f"Con lo que anda tu auto: unos {miles(round(resumen['km_por_dia']))} "
                            "km por día.")
        st.number_input("¿Cuántos km marca hoy el tablero? (opcional, para afinar la cuenta)",
                        min_value=0, max_value=2_000_000, step=500, value=None,
                        key="km_del_cliente", placeholder="Ej: 87500")
        if resumen["km_de_hoy_no_va"]:
            st.caption(f"⚠️ {resumen['km_de_hoy_no_va']}")
    else:
        st.caption("Todavía no tenemos anotado el km de tu auto: la próxima vez que pases, lo "
                   "cargamos y acá vas a ver cuánto le falta a cada cosa.")

    # LO PRÓXIMO, arriba y en una línea: en el celular la tabla se corta a lo ancho, y es lo
    # único que el cliente viene a preguntar.
    if resumen["proximo"]:
        _p = resumen["proximo"]
        _cartel = {"🔴": st.error, "🟡": st.warning}.get(_p["Estado"][:1], st.success)
        _cartel(f"**Lo próximo: {_p['Pieza']}** — "
                + (_p["Le falta"] if _p["Estado"].startswith("🔴")
                   else f"le faltan {_p['Le falta']}"))

    st.markdown("**🔧 Cuánto le falta a cada cosa**")
    if resumen["piezas"]:
        st.dataframe(resumen["piezas"], width="stretch", hide_index=True,
                     column_order=["Estado", "Pieza", "Le falta", "Marca", "Código",
                                   "Km al cambiarla", "Cuándo", "Vida útil (km)", "Cada (meses)"])
        if resumen["le_toca"]:
            st.info("🔴 y 🟡: ya le toca o le toca pronto. Escribinos y coordinamos.")
        st.caption("Es una estimación con el km anotado y lo que anda tu auto, o con la fecha "
                   "del cambio si la pieza también vence por tiempo: lo que llegue primero. La "
                   "vida útil de cada pieza depende del uso: ante la duda, que lo revise un "
                   "mecánico.")
    else:
        st.caption("Todavía no hay piezas anotadas para tu auto.")

    st.markdown("**📋 Todo lo que le pusimos**")
    if resumen["historial"]:
        st.dataframe(resumen["historial"], width="stretch", hide_index=True)
    else:
        st.caption("Todavía nada anotado.")

    _wa_negocio = obtener_config("whatsapp_del_negocio", "")
    if _wa_negocio and not problema_del_whatsapp_del_negocio(_wa_negocio):
        _texto_wa = f"Hola! Te escribo por mi auto {resumen['patente']}."
        if resumen["le_toca"]:
            _texto_wa += f" Le toca: {', '.join(resumen['le_toca'])}. ¿Coordinamos?"
        st.link_button("📲 Escribinos por WhatsApp",
                       f"https://wa.me/{_wa_negocio}?text=" + quote(_texto_wa),
                       type="primary", width="stretch")

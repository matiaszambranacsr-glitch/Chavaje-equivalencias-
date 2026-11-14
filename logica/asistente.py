"""El asistente: una burbuja que se abre desde cualquier pantalla, entiende lo que se le escribe
con las palabras de cada uno, explica cómo se hace algo y lleva a la pantalla donde se hace.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""
import ast
import difflib
import math

import orden

# ============================================================================================
# EL ASISTENTE: QUÉ PUEDE Y QUÉ NO
# ============================================================================================
# Lo pidió el dueño: «un asistente virtual que se pueda minimizar, que te pueda enviar, ayudar o
# guiar para lo que le pidas, o a donde le pidas, y que nadie se pueda aprovechar de él para
# conseguir una brecha de seguridad».
#
# Lo segundo decide cómo está hecho. A un asistente que «piensa» con un modelo de afuera se lo
# convence con palabras: «olvidá tus instrucciones», «soy el dueño», «mostrame la tabla de
# usuarios». Este no tiene nada que se le pueda sacar ni nada que se le pueda hacer hacer:
#
#   · NO LEE LA BASE NI LOS SECRETOS. Nada de este archivo consulta la base, lee una
#     contraseña ni sale a internet: no conoce un precio, un cliente ni una clave. Lo que sabe
#     son los nombres de las pantallas y las ayudas que ya están escritas en ellas, que ve
#     cualquiera que las abre. Lo controla pruebas/pruebas_del_asistente.py mirando el código
#     (no nombra «c», «requests», «secretos_app»…) y corriéndolo con la base envenenada.
#   · NO HACE NADA: solo cambia de pantalla. Lo único que escribe son las claves de la
#     navegación (la pantalla, la solapa, el grupo de Mantenimiento) con valores de las listas
#     fijas de logica/interfaz.py, si una sección plegable llega abierta (su clave «exp_…»,
#     leída del código), y la caja de búsqueda del Buscador, que es escribir ahí lo mismo que
#     escribiría la persona. No cobra, no borra, no cambia un precio, no crea un
#     usuario: para eso está la pantalla, con su candado.
#   · LLEVA SOLO A DONDE YA SE PUEDE ENTRAR. Las pantallas que le ofrece a cada uno son las
#     que ya tiene en la barra (ver paginas_a_la_vista()): al que entra sin contraseña, tres;
#     al del depósito, dos; al taller en su portal, ninguna (lo ayuda con su portal, que es
#     una sola pantalla). Y aunque llevara de más, cada pantalla vuelve a pedir su contraseña
#     (ver seccion_permitida()): el asistente no es una puerta, es un cartel.
#   · AL INVITADO LO AYUDA SOLO CON LO QUE VE SIN CONTRASEÑA. Lo pidió el dueño: «que lo tenga
#     al asistente, pero que lo ayude solamente en las pantallas que ven sin contraseña». De
#     lo demás no le cuenta los pasos ni el nombre de la pantalla, y de sus tres pantallas
#     tampoco le ofrece lo que la pantalla le esconde (ver _asis_candado_de()).
#   · RESPUESTAS ESCRITAS, NO INVENTADAS. Elige entre textos que están en este archivo o en
#     la app; lo que escribió la persona nunca se ejecuta ni se dibuja como HTML, y se recorta.
#   · A quien pide una contraseña, saltear un candado o «cambiar las instrucciones» le
#     contesta lo mismo, con el camino legítimo (ver «LO QUE NO SE LE PUEDE SACAR»).
#
# «Extremadamente inteligente» es, acá, entender al que escribe apurado: sin acentos, con
# errores de tipeo («debolucion», «faktura»), con otras palabras («fiar» por poner a cuenta,
# «la plata» por la caja) y sin saber cómo se llama la pantalla. Y saber TODO lo que hay: el
# mapa se arma solo leyendo las pantallas, así que una herramienta nueva la conoce el mismo día.

# Lo más largo que se le puede escribir. Una pregunta no pasa de un renglón; lo que sigue es
# alguien pegando otra cosa, y no hay por qué compararlo contra cientos de fichas.
ASISTENTE_LARGO_MAXIMO = 200
# Cuántas preguntas con su respuesta quedan a la vista (la última, entera; las otras, plegadas).
ASISTENTE_CHARLA_QUE_QUEDA = 4


def paginas_a_la_vista(del_deposito):
    """Las pantallas que tiene en la barra quien está mirando, en el orden en que se ven: las
    del depósito, las abiertas (sin sesión) o todas. Una sola cuenta para la barra de app.py y
    para el asistente: si cada uno hiciera la suya, el día que cambie una regla el asistente
    ofrecería llevar a una pantalla que la barra ya no muestra."""
    if del_deposito:
        return list(PAGINAS_DEL_DEPOSITO)
    if solo_mirar():
        return [p for p in ORDEN_DE_LAS_PAGINAS if p in PAGINAS_ABIERTAS]
    return list(ORDEN_DE_LAS_PAGINAS)


# ============================================================================================
# LO QUE SABE EL ASISTENTE: EL MAPA DE LA APP, ARMADO SOLO
# ============================================================================================
# Cada cosa que sabe es una «ficha»: un título, palabras con las que se la busca, un texto y un
# destino. Salen de cinco lugares, y cuatro se arman solos:
#   · las pantallas y sus solapas (PARA_QUE_SIRVE, PARA_QUE_SIRVE_LA_SOLAPA);
#   · los grupos y las herramientas de Mantenimiento (HERRAMIENTAS_MANTENIMIENTO);
#   · cada sección plegable de cada pantalla («📋 Cargar muchas cuentas de una vez», «⚡ Armado
#     rápido»…), leyendo el código de pantallas/: en qué pantalla y en qué solapa está sale de
#     los «if pagina == PAGINAS[n]» y «if sub_x == SUB_X[n]» que la rodean;
#   · cada ayuda escrita en una pantalla (las «ℹ️ Cómo funciona»), de la misma lectura;
#   · y los «cómo hago» de más abajo, escritos a mano, para lo de todos los días.
# Un destino es {"pagina", "solapa", "grupo", "herramienta", "seccion", "abrir"}: nombres de las
# listas de navegación —y, en «abrir», la clave «exp_…» de una sección plegable leída del
# código de la pantalla—, nunca un texto libre.

# Lo que se junta de las pantallas: qué llamada es un título de sección y cuál una ayuda.
_ASIS_TITULOS = ("expander", "seccion_plegable", "popover", "dialog")
_ASIS_AYUDAS = ("ayuda", "explicar")
# Las listas de solapas por su nombre en el código, para entender «sub_admin == SUB_ADMIN[5]».
_ASIS_LISTAS = {"PAGINAS": lambda: PAGINAS, "SUB_STATS": lambda: SUB_STATS,
                "SUB_ADMIN": lambda: SUB_ADMIN, "SUB_MEC": lambda: SUB_MEC,
                "SUB_DEVOLUCIONES": lambda: SUB_DEVOLUCIONES,
                "SUB_DEPOSITO": lambda: SUB_DEPOSITO,
                "GRUPOS_MANTENIMIENTO": lambda: GRUPOS_MANTENIMIENTO}
# Lo cosechado y el índice, por la fecha de los archivos de pantallas/. Es «de cada pasada» del
# código a propósito, y no de del_proceso(): sale de este archivo y de logica/interfaz.py, así
# que cuando se recarga el código tiene que armarse de nuevo. No lo usa ningún hilo de fondo.
_ASIS_MEMORIA = {}


def _asis_texto_del_codigo(nodo):
    """El texto de un argumento escrito en el código: una cadena, una f-cadena (lo variable
    queda como «…») o varias sumadas. None si no es un texto."""
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return nodo.value
    if isinstance(nodo, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) and isinstance(v.value, str)
                       else "…" for v in nodo.values)
    if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, ast.Add):
        return ((_asis_texto_del_codigo(nodo.left) or "…")
                + (_asis_texto_del_codigo(nodo.right) or "…"))
    return None


def _asis_lugar_de(condicion, lugar):
    """El lugar que agrega un «if»: {"PAGINAS": 3, "SUB_ADMIN": 5}. Mira las comparaciones
    «nombre == LISTA[n]» y «nombre in LISTA[a:]» (esta última no fija solapa: son varias)."""
    nuevo = dict(lugar)
    for parte in ast.walk(condicion):
        if not (isinstance(parte, ast.Compare) and len(parte.comparators) == 1
                and isinstance(parte.ops[0], ast.Eq)):
            continue
        derecha = parte.comparators[0]
        if (isinstance(derecha, ast.Subscript) and isinstance(derecha.value, ast.Name)
                and derecha.value.id in _ASIS_LISTAS and isinstance(derecha.slice, ast.Constant)
                and isinstance(derecha.slice.value, int)):
            nuevo[derecha.value.id] = derecha.slice.value
    return nuevo


# Las preguntas con que una pantalla decide si muestra algo: lo de adentro de «if
# es_empleado_o_abierto():» o de «if not solo_mirar():» no lo ve quien entró sin contraseña.
_ASIS_SOLO_EL_PERSONAL = {"es_empleado_o_abierto": "empleado", "es_operador_o_admin": "empleado",
                          "es_admin": "admin"}


def _asis_pregunta_del_candado(nodo):
    """El nombre de la función si el nodo es «es_admin()», «solo_mirar()»… (sin argumentos)."""
    return (getattr(nodo.func, "id", None)
            if isinstance(nodo, ast.Call) and not nodo.args else None)


def _asis_candado_de(condicion, con_candado):
    """Quién ve lo de adentro de un «if», y quién lo de su «else»: ("empleado" | "admin" |
    None, lo mismo). Mira la condición sola o las partes de un «a and b»: la pregunta misma
    («if es_admin():», «if not solo_mirar():») o una variable que se armó con una
    (`con_candado`: «_parecido_aca = … if es_operador_o_admin() else None» y más abajo «if
    _parecido_aca is not None:»). Ante la duda, del personal: de más no le muestra nada a
    nadie. Y que no se le escape ninguna lo mira la prueba, con la pantalla dibujada para un
    invitado."""
    partes = (condicion.values if isinstance(condicion, ast.BoolOp)
              and isinstance(condicion.op, ast.And) else [condicion])
    adentro = None
    for parte in partes:
        quien = _ASIS_SOLO_EL_PERSONAL.get(_asis_pregunta_del_candado(parte))
        if (isinstance(parte, ast.UnaryOp) and isinstance(parte.op, ast.Not)
                and _asis_pregunta_del_candado(parte.operand) == "solo_mirar"):
            quien = "empleado"
        variable = parte.left if isinstance(parte, ast.Compare) else parte
        if isinstance(variable, ast.Name) and variable.id in con_candado:
            quien = con_candado[variable.id]
        if quien and adentro != "admin":
            adentro = quien
    return adentro, ("empleado" if _asis_pregunta_del_candado(condicion) == "solo_mirar"
                     else None)


def _asis_con_candado(lugar, quien):
    """El lugar con ese candado puesto (el de administrador no se afloja a empleado)."""
    if not quien or lugar.get("_quien") == "admin":
        return lugar
    return {**lugar, "_quien": quien}


def _asis_andar(nodo, lugar, seccion, plegables, sale):
    """Recorre el código de una pantalla anotando títulos y ayudas con dónde están.
    `plegables` es lo que se va sabiendo del archivo: {variable: título del plegable que
    guarda} y, en «candados», {variable: quién ve lo que depende de ella}."""
    con_candado = plegables.setdefault("candados", {})
    if isinstance(nodo, ast.If):
        del_cuerpo, del_si_no = _asis_candado_de(nodo.test, con_candado)
        adentro = _asis_con_candado(_asis_lugar_de(nodo.test, lugar), del_cuerpo)
        for hijo in nodo.body:
            _asis_andar(hijo, adentro, seccion, plegables, sale)
        for hijo in nodo.orelse:
            _asis_andar(hijo, _asis_con_candado(lugar, del_si_no), seccion, plegables, sale)
        return
    if isinstance(nodo, ast.Assign):
        # Una variable armada preguntando quién está («a, b = (… if es_operador_o_admin() else
        # …)»): lo que después dependa de ella es de ese personal.
        preguntas = {_asis_pregunta_del_candado(parte) for parte in ast.walk(nodo.value)}
        quien = ("admin" if "es_admin" in preguntas
                 else "empleado" if preguntas & (set(_ASIS_SOLO_EL_PERSONAL) | {"solo_mirar"})
                 else None)
        if quien:
            for destino in nodo.targets:
                for nombre in ast.walk(destino):
                    if isinstance(nombre, ast.Name):
                        con_candado[nombre.id] = quien
    if isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Call):
        # «x = st.expander(…, on_change="rerun")» y más abajo «with x:»: el plegable perezoso.
        titulo = _asis_titulo_de(nodo.value)
        if titulo and len(nodo.targets) == 1 and isinstance(nodo.targets[0], ast.Name):
            plegables[nodo.targets[0].id] = titulo
    if isinstance(nodo, (ast.With, ast.FunctionDef)):
        adentro = seccion
        if isinstance(nodo, ast.With):
            for item in nodo.items:
                expr = item.context_expr
                titulo = (_asis_titulo_de(expr) if isinstance(expr, ast.Call)
                          else plegables.get(expr.id) if isinstance(expr, ast.Name) else None)
                if isinstance(titulo, str) and titulo:
                    adentro = titulo
        else:
            # «@st.dialog("💳 Cobrar la venta")» arriba de una función.
            for decorador in nodo.decorator_list:
                titulo = _asis_titulo_de(decorador) if isinstance(decorador, ast.Call) else None
                if titulo:
                    adentro = titulo
        for hijo in ast.iter_child_nodes(nodo):
            _asis_andar(hijo, lugar, adentro, plegables, sale)
        return
    if isinstance(nodo, ast.Call):
        nombre = getattr(nodo.func, "attr", None) or getattr(nodo.func, "id", None)
        if nombre in _ASIS_TITULOS or nombre == "subheader":
            titulo = _asis_titulo_de(nodo) or (
                _asis_texto_del_codigo(nodo.args[0]) if nodo.args else None)
            if titulo:
                # Un plegable se abre tocando el título; un subtítulo o una ventana, no.
                sale.append(("seccion" if nombre in ("expander", "seccion_plegable")
                             else "titulo", titulo, dict(lugar), None,
                             _asis_clave_para_abrir(nodo)))
        elif nombre in _ASIS_AYUDAS and nodo.args:
            texto = _asis_texto_del_codigo(nodo.args[0])
            if texto:
                sale.append(("ayuda", texto, dict(lugar), seccion, None))
    for hijo in ast.iter_child_nodes(nodo):
        _asis_andar(hijo, lugar, seccion, plegables, sale)


def _asis_titulo_de(llamada):
    """El título de un st.expander(…), seccion_plegable(…), st.popover(…) o st.dialog(…)."""
    nombre = getattr(llamada.func, "attr", None) or getattr(llamada.func, "id", None)
    if nombre in _ASIS_TITULOS and llamada.args:
        return _asis_texto_del_codigo(llamada.args[0])
    return None


def _asis_clave_para_abrir(llamada):
    """La clave de un st.expander(…, key="exp_…", on_change="rerun"): con esa forma, si está
    abierto o cerrado vive en la sesión con esa clave, y poniéndola en True se llega con la
    sección ya abierta. Solo las claves fijas que empiezan con «exp_»; None en los demás."""
    if getattr(llamada.func, "attr", None) != "expander":
        return None
    puestos = {k.arg: k.value for k in llamada.keywords}
    clave, al_cambiar = puestos.get("key"), puestos.get("on_change")
    if (isinstance(clave, ast.Constant) and isinstance(clave.value, str)
            and clave.value.startswith("exp_") and isinstance(al_cambiar, ast.Constant)
            and al_cambiar.value == "rerun"):
        return clave.value
    return None


def _asis_titulo_limpio(titulo):
    """«⭐ Favoritos (…)» → «⭐ Favoritos»: sin lo variable ni lo que le cuelga. None si lo que
    queda no dice nada («…  ·  … → …», «Ver los …»)."""
    entero = str(titulo or "")
    limpio = re.split(r"\s*[(—:·]?\s*…", entero)[0].strip(" (—:·-")
    if limpio != entero.strip():
        # Cortado: sin las palabras que quedaron colgando («…de la cuenta de», «— hoy»), y si
        # lo que queda es «Ver los primeros», no es el nombre de nada.
        limpio = re.sub(r"(\s+(—|de|del|la|las|los|el|a|con|por|hoy))+$", "", limpio).strip(" —")
        if _sin_emoji(limpio).startswith("ver "):
            return None
    return limpio if len(_sin_emoji(limpio)) >= 8 else None


def _asis_frases_enteras(texto):
    """De una ayuda con partes variables («🟡 desde … minutos»), las frases que se leen enteras."""
    texto = re.sub(r"\s+", " ", str(texto or "")).strip()
    if "…" not in texto:
        return texto
    frases = [f for f in re.split(r"(?<=[.!?:])\s+", texto) if "…" not in f]
    return " ".join(frases).strip()


def _asis_cosecha():
    """Lo que dicen las pantallas de sí mismas: [(qué, texto, destino, sección, clave para
    abrirla, quién lo ve)]. Se lee una vez por proceso (y de nuevo si cambia un archivo de
    pantallas/): son unos 15.000 renglones."""
    carpeta = os.path.join(orden.AQUI, "pantallas")
    rutas = [os.path.join(carpeta, nombre) for nombre in orden.PANTALLAS]
    huella = tuple(os.path.getmtime(r) for r in rutas if os.path.exists(r))
    if _ASIS_MEMORIA.get("huella") == huella:
        return _ASIS_MEMORIA["cosecha"]
    sale = []
    for ruta in rutas:
        try:
            with open(ruta, encoding="utf-8") as archivo:
                arbol = ast.parse(archivo.read())
        except (OSError, SyntaxError):
            continue            # una pantalla que no se pudo leer: el asistente sabe menos
        crudo = []
        for nodo in arbol.body:
            _asis_andar(nodo, {}, None, {}, crudo)
        for que, texto, lugar, seccion, abrir in crudo:
            destino = _asis_destino_del_lugar(lugar)
            if destino:
                sale.append((que, texto, destino, seccion, abrir, lugar.get("_quien", "")))
    _ASIS_MEMORIA.clear()
    _ASIS_MEMORIA.update(huella=huella, cosecha=sale)
    return sale


def _asis_destino_del_lugar(lugar):
    """{"PAGINAS": 3, "SUB_ADMIN": 4, "GRUPOS_MANTENIMIENTO": 1} → el destino con nombres."""
    if "PAGINAS" not in lugar or not 0 <= lugar["PAGINAS"] < len(PAGINAS):
        return None
    pagina = PAGINAS[lugar["PAGINAS"]]
    destino = {"pagina": pagina}
    solapas = SOLAPAS_DE_LA_PAGINA.get(pagina)
    if solapas:
        nombre_de_la_lista = next((n for n, lista in _ASIS_LISTAS.items()
                                   if lista() is solapas[0]), None)
        n = lugar.get(nombre_de_la_lista)
        if n is not None and 0 <= n < len(solapas[0]):
            destino["solapa"] = solapas[0][n]
    n = lugar.get("GRUPOS_MANTENIMIENTO")
    if n is not None and 0 <= n < len(GRUPOS_MANTENIMIENTO):
        destino["solapa"] = "🧹 Mantenimiento"
        destino["grupo"] = GRUPOS_MANTENIMIENTO[n]
    return destino


def _asis_destino_de(nombre):
    """El destino de una pantalla, una solapa, un grupo o una herramienta, por su nombre (como
    miga_hasta()). ValueError si no existe: una ficha que no lleva a ningún lado no se carga."""
    for pagina in PAGINAS:
        if _es_el_mismo_nombre(nombre, pagina):
            return {"pagina": pagina}
    for pagina, (solapas, _clave) in SOLAPAS_DE_LA_PAGINA.items():
        for solapa in solapas:
            if _es_el_mismo_nombre(nombre, solapa):
                return {"pagina": pagina, "solapa": solapa}
    for grupo in GRUPOS_MANTENIMIENTO:
        if _es_el_mismo_nombre(nombre, grupo):
            return {"pagina": "🗂️ Administrar", "solapa": "🧹 Mantenimiento", "grupo": grupo}
    for titulo, grupo, *_ in HERRAMIENTAS_MANTENIMIENTO:
        if _es_el_mismo_nombre(nombre, titulo):
            return {"pagina": "🗂️ Administrar", "solapa": "🧹 Mantenimiento",
                    "grupo": GRUPOS_MANTENIMIENTO[grupo], "herramienta": titulo}
    raise ValueError(f"el asistente no conoce ningún lugar «{nombre}»")


def camino_del_asistente(destino):
    """El destino escrito como una miga, con la sección entre comillas al final si la tiene
    (la arma con los nombres de las listas, y con miga_hasta() si es una herramienta)."""
    if destino.get("herramienta"):
        tramos = [miga_hasta(destino["herramienta"])]
    else:
        tramos = [destino["pagina"]] + [destino[k] for k in ("solapa", "grupo") if destino.get(k)]
    if destino.get("seccion"):
        tramos.append(f"«{destino['seccion']}»")
    return " → ".join(tramos)


# ============================================================================================
# LOS «CÓMO HAGO» DEL ASISTENTE
# ============================================================================================
# Lo de todos los días, escrito a mano: (nombre, título, palabras con que se pregunta, los
# pasos, dónde se hace, quién puede). Las palabras son las del mostrador —«fiar», «la plata»,
# «el ticket»—, no las de la pantalla: para las de la pantalla ya está el mapa de arriba.
# Cada «botón entre comillas» de los pasos tiene que existir escrito así en la app: lo controla
# pruebas/pruebas_del_asistente.py, y si un botón cambia de nombre la prueba dice cuál.
# «Dónde» es el nombre de una pantalla, una solapa, un grupo o una herramienta (None: se hace
# desde cualquier pantalla). «Quién»: "" cualquiera que vea esa pantalla; "empleado" si está en
# una pantalla abierta pero hay que entrar para hacerlo; "admin" si adentro pide un
# administrador; "taller" si es del portal del taller (que es una sola pantalla, sin barra: no
# hay a dónde llevar), y entonces lo ve el taller y nadie más.
COMO_HAGO_DEL_ASISTENTE = (
    # ---- vender y cobrar ----
    ("vender", "Hacer una venta",
     "vender venta vendo despachar cargar venta nueva cliente lleva mostrador terminar f9 "
     "cantidad sumar agregar quitar uno menos",
     "Buscá lo que se lleva el cliente y sumalo; corregí la cantidad o el precio si hace falta "
     "(con el lector, escaneá la caja). Arriba, en «🧾 Atendiendo a», elegís la cuenta si es de "
     "un taller. Para cerrar, «✅ Terminar la venta» —o «📤 Mandar a la caja» si cobra otra "
     "persona—: también con F9. Pregunta con el total antes de grabar.",
     "🧾 Ventas", ""),
    ("cobrar", "Cobrar una venta",
     "cobrar cobro cobranza pago pagar efectivo debito credito tarjeta cuotas transferencia "
     "qr f10 medio forma como pago",
     "Lo que mandan los vendedores llega con un cartel. Elegí la venta y tocá «💳 Cobrar (F10)»: "
     "«¿Cómo pagó?» —efectivo, débito, crédito con las cuotas o transferencia— y, si hace "
     "falta, un descuento por porcentaje. Recién cobrada cuenta en el cierre.",
     "💵 Caja", ""),
    ("a_cuenta", "Poner una venta a la cuenta del cliente (fiar)",
     "fiar fiado cuenta corriente anotar deber debe llevar sin pagar f11 a cuenta credito taller",
     "En la caja, elegí la venta y tocá «📒 A cuenta (F11)»: pregunta si estás seguro y la "
     "carga en la cuenta de ese cliente, con su descuento y controlando su límite de crédito. "
     "La cuenta es la que el vendedor eligió en «🧾 Atendiendo a».",
     "💵 Caja", ""),
    ("cierre", "Cerrar la caja (el arqueo del día)",
     "cierre cerrar caja arqueo arquear contar plata dinero efectivo dia total vendido "
     "vendi hoy ayer anteriores historial quien vendio recaudacion planilla zeta",
     "Abajo de la caja, abrí «📋 Ventas y cierre de caja»: están las ventas del día con quién "
     "vendió, cómo se pagó cada una y los totales (con «Día:» se mira otro día). Contá el "
     "efectivo, escribilo y tocá «🧮 Guardar el arqueo»: queda anotado con la diferencia. Las "
     "ventas del día se bajan en Excel desde ahí.",
     "💵 Caja", ""),
    ("corregir_cobro", "Corregir un cobro mal cargado",
     "corregir equivoque equivocado error mal cobrado cambiar medio forma pago anular cobro "
     "deshacer volver caja cajera",
     "En «📋 Ventas y cierre de caja», abajo, está «✏️ Corregir un cobro»: elegís la venta y "
     "cambiás cómo pagó, o tocás «↩️ Volverla a la caja» para cobrarla de nuevo (vuelve sin el "
     "descuento y sin el cargo en la cuenta). Cada corrección queda anotada con quién la hizo.",
     "💵 Caja", ""),
    ("sin_stock", "Vender algo que figura sin stock",
     "negativo cero figura vender igual alcanza falta agotado",
     "Se vende igual: el stock nunca queda negativo, y si no alcanzaba la app avisa para "
     "contarlo. Para que quede anotado para comprar, «📌 Anotar para reponer».",
     "🧾 Ventas", ""),
    ("deshacer_venta", "Deshacer una venta que mandé por error",
     "deshacer anular cancelar venta equivocada error mande recuperar",
     "Mientras la venta espera en la caja, quien la armó la puede deshacer desde Ventas: "
     "vuelve armada para corregirla. Si ya se cobró, se corrige en la caja («✏️ Corregir un "
     "cobro») o se devuelve en Devoluciones.",
     "🧾 Ventas", ""),
    ("factura", "Hacer una factura electrónica (ARCA)",
     "factura facturar facturacion electronica arca afip comprobante fiscal cae cuit a b c "
     "consumidor final responsable inscripto monotributo",
     "La factura se hace solo cuando se pide. Al cobrar, prendé «🧾 Con factura electrónica» y "
     "completá el cliente (con el CUIT trae de ARCA el nombre y la condición). Si ya se cobró, "
     "se factura después desde «📋 Ventas y cierre de caja». Para que ande hace falta el "
     "certificado de ARCA cargado (lo hace un administrador).",
     "💵 Caja", ""),
    ("nota_credito", "Anular una factura (nota de crédito)",
     "nota credito anular factura devolver facturado nc",
     "Una factura no se borra: se anula con una nota de crédito. Sale sola al devolver algo de "
     "una venta facturada (por lo devuelto), y también se puede pedir desde la factura en "
     "«📋 Ventas y cierre de caja».",
     "💵 Caja", ""),
    ("certificado_arca", "Cargar el certificado de ARCA",
     "certificado arca afip clave fiscal configurar factura electronica csr homologacion "
     "produccion webservice",
     "Abrí «🔑 No tengo el certificado: armarlo paso a paso»: la app arma la clave y el pedido "
     "para subir a ARCA, y te dice qué pegar en la configuración. Primero se prueba en "
     "homologación.",
     "💬 Mensajería y cobros", "admin"),
    ("contador", "Bajar los comprobantes del mes para el contador",
     "contador contadora planilla mes comprobantes facturas excel iva exportar",
     "Donde está la configuración de ARCA se elige el mes y se baja el Excel con todas las "
     "facturas y notas de crédito.",
     "💬 Mensajería y cobros", "admin"),
    ("descuento", "Hacer un descuento",
     "descuento rebaja bonificacion porcentaje precio especial menos",
     "Al cobrar («💳 Cobrar (F10)») se pone un descuento por porcentaje para esa venta. El "
     "descuento fijo de un taller o mayorista se carga una vez en su cuenta («⚙️ Configuración "
     "de la cuenta») y se aplica solo.",
     "💵 Caja", ""),
    ("comprobante", "Imprimir o mandar el comprobante de una venta",
     "comprobante ticket recibo imprimir impresion pdf papel remito boleta",
     "Al terminar la venta aparece «📄 Comprobante (PDF)». De una venta anterior, en la caja: "
     "«📋 Ventas y cierre de caja».",
     "🧾 Ventas", ""),
    ("presupuesto", "Armar un presupuesto o una cotización",
     "presupuesto cotizacion cotizar precio pasar lista cliente pidio cuanto sale armar",
     "Dos caminos. En el Buscador, en cada resultado, «📦 Pedir al depósito / 🛒 presupuesto» lo "
     "suma al «🛒 Presupuesto en armado» de arriba. O pegá todos los códigos que pidió el "
     "cliente en la Lista WhatsApp: arma el mensaje con las marcas y los precios, y el PDF.",
     "📋 Lista WhatsApp", "empleado"),
    # ---- devoluciones ----
    ("devolucion_cliente", "Devolver algo que trajo un cliente",
     "devolucion devolver devuelve cliente trajo cambio cambiar garantia reintegro plata "
     "vuelta fallado",
     "Buscá la venta, elegí qué devuelve y tocá «↩️ Devolver»: vuelve al stock si se puede "
     "vender, y la plata sale de la caja de hoy. Si la venta tenía factura, hace la nota de "
     "crédito por lo devuelto.",
     "🧾 De un cliente", ""),
    ("devolucion_deposito", "Devolver al depósito lo que se pidió y no se vendió",
     "devolver deposito no vendio sobro quedo afuera volver stock etiqueta escanear recibir",
     "Lo que el depósito entregó para Mostrador queda a nombre de quien lo pidió. Si no se "
     "vende, escaneá la etiqueta nuestra de cada pieza; después pone su contraseña quien lo "
     "tiene y vuelve al stock. Lo recibe el depósito: nadie se devuelve a sí mismo.",
     "📦 Al depósito", ""),
    ("etiquetas", "Imprimir etiquetas",
     "etiqueta etiquetas imprimir codigo barras pegar pieza estante rotulo",
     "Las de las piezas, acá: de un producto (también escaneando la caja) o de todo lo que "
     "está afuera. Las de los estantes del depósito están en Depósito, en «🏷️ Etiquetas de los "
     "estantes».",
     "🏷️ Etiquetas", ""),
    # ---- depósito ----
    ("pedir_deposito", "Pedirle un repuesto al depósito",
     "pedir deposito traer bajar pedido mostrador necesito que me traigan",
     "Buscá el repuesto en el Buscador y, en el resultado, tocá «📦 Pedir al depósito / 🛒 "
     "presupuesto». Le llega al depósito al instante; cuando lo entrega te avisa un cartel.",
     "🔍 Buscador", "empleado"),
    ("entregar", "Entregar lo que pidió el mostrador",
     "entregar entregado entrega pedido preparar buscar cola pendiente dar baja no hay falta",
     "Están los pedidos en el orden de cada piso, con el lugar resaltado en el mapa. «✅ "
     "Entregado» lo da de baja y descuenta el stock; «❌ No hay» lo manda a la lista de lo que "
     "hay que pedir. Si no tenía lugar, «📍 ¿Dónde está?» lo anota para la próxima.",
     "⏳ Para buscar", ""),
    ("donde_esta", "Saber dónde está guardado un repuesto",
     "donde esta guardado ubicacion estante estanteria lugar encontrar mapa plano pasillo",
     "Escribí o escaneá el código y se resalta en el plano. En los resultados del Buscador y "
     "en la venta también está «📍 ¿Dónde está?».",
     "🗺️ Mapa", ""),
    ("ubicar", "Ponerle lugar a los repuestos (cargar el mapa)",
     "ubicar ubicacion poner lugar guardar acomodar estante cargar mapa escanear sin lugar",
     "Escaneá la etiqueta del estante (o escribí «A-3-2») y después todo lo que hay en él: "
     "cada cosa queda en ese lugar. También se pega una lista de Excel, y la app sugiere dónde "
     "poner lo que más se vende.",
     "📍 Ubicar", ""),
    ("armar_deposito", "Armar el plano del depósito",
     "armar plano deposito estanterias dibujar pisos modulos agregar estanteria mover sacar",
     "Primero el depósito y el piso; después «⚡ Armado rápido» lo arma con cuántas filas de "
     "estanterías hay, y se retoca sumando, moviendo o sacando. Nada se guarda hasta tocar "
     "«💾 Guardar el plano».",
     "🏗️ Armar el depósito", ""),
    # ---- buscar ----
    ("buscar", "Buscar un repuesto: su precio y sus equivalencias",
     "buscar equivalencia equivalente reemplazo reemplaza sirve otra marca alternativa "
     "codigo repuesto cruce igual precio",
     "Escribí el código (o varios, separados por coma) y «🔍 Buscar equivalencias»: salen "
     "todas las marcas que sirven en su lugar, con precio y stock. Si escribís palabras —«filtro "
     "aceite gol»— busca por descripción. F2 lleva a la caja de búsqueda.\n\n"
     "También me lo podés pedir a mí: escribí «buscar» y el código.",
     "🔍 Buscador", ""),
    ("ver_stock", "Ver cuánto stock hay de un repuesto, o apartarlo",
     "stock hay queda quedan tengo existencia disponible libre apartar separar reservar "
     "guardar cliente",
     "Buscalo: cada resultado dice el precio y el stock, y «Libre» es lo que queda sin "
     "apartar. Para guardarle uno a un cliente, «🔒 Apartar» en el resultado.",
     "🔍 Buscador", "empleado"),
    ("no_encuentro", "No aparece un código que busco",
     "no aparece encuentro encuentra existe sale codigo falta cargar sin resultado nada",
     "Probá sin puntos ni espacios, o por descripción. Si de verdad no está, queda anotado "
     "solo en «Búsquedas sin resultado» para cargarlo o pedirlo. Si está pero el buscador no "
     "lo relaciona con otro, en Vincular manual está «🔎 ¿Por qué estos dos códigos no se "
     "relacionan?».",
     "🔎 Búsquedas sin resultado", ""),
    ("no_esta", "No encuentro el repuesto que busco",
     "no aparece encuentro encuentra existe sale codigo falta sin resultado nada",
     "Probá el código sin puntos ni espacios, o escribí qué es —«filtro aceite gol»— y busca "
     "por la descripción. Si tenés la pieza en la mano, por sus medidas. Y si no aparece, "
     "consultalo en el mostrador: puede que todavía no esté cargado.",
     "🔍 Buscador", ""),
    ("medidas", "Buscar un repuesto por sus medidas",
     "medidas medida diametro largo alto rosca milimetros mm sin codigo medir",
     "En el Buscador, abajo, abrí «📐 Buscar por medidas mecánicas (cuando no hay código ni "
     "equivalencia cargada)» y poné las medidas que tengas.",
     "🔍 Buscador", ""),
    ("bujia", "Saber qué bujía le va",
     "bujia bujias ngk bosch champion grado termico encendido",
     "En el Buscador, abajo, abrí «🕯️ ¿Qué bujía le va? (por el código de cualquier marca o "
     "por cómo es)».",
     "🔍 Buscador", ""),
    ("escanear", "Buscar escaneando el código de barras",
     "escanear escaner lector codigo barras camara pistola",
     "Con el lector, escaneá directo en la caja de búsqueda. Con la cámara del celular, en el "
     "Buscador abrí «📷 Escanear el código de barras de la caja».",
     "🔍 Buscador", ""),
    ("foto", "Reconocer una pieza por una foto",
     "foto imagen reconocer identificar pieza sacar camara ia inteligencia artificial que es",
     "En el Buscador, abajo, abrí «📷 Identificar pieza por foto (con IA)»: sacale una foto y "
     "dice qué pieza es, para buscarla.",
     "🔍 Buscador", ""),
    ("voz", "Buscar hablando",
     "voz hablar hablando dictar microfono audio decir",
     "En el Buscador, abrí «🎙️ Buscar por voz» y decí el código o la pieza.",
     "🔍 Buscador", ""),
    ("vincular", "Decir que dos códigos son el mismo repuesto",
     "vincular unir relacionar equivalentes a mano dos codigos son lo mismo cargar equivalencia",
     "Armá un grupo de códigos —de la marca que sea— y vinculalos todos entre sí de una vez.",
     "🔗 Vincular manual", ""),
    ("aprobar", "Aprobar las equivalencias que encontró la app",
     "aprobar aprobacion sugeridas pendientes revisar equivalencias encontro cola descartar",
     "Están las que la app encontró sola, con por qué las propone. Aprobalas o descartalas: "
     "hasta entonces no aparecen al buscar.",
     "🔗 Equivalencias sugeridas", ""),
    # ---- cuentas ----
    ("crear_cuenta", "Crear la cuenta de un taller, un mayorista o un cliente",
     "crear cuenta nueva alta taller mayorista cliente mecanico agregar sumar dar",
     "En «🔧 Mecánicos externos: talleres, mayoristas y clientes con cuenta» poné el nombre y "
     "«➕ Crear la cuenta». La contraseña es opcional: solo si va a entrar a su portal. Para "
     "muchas juntas, «📋 Cargar muchas cuentas de una vez (pegadas de Excel)».",
     "👥 Usuarios", "admin"),
    ("cuenta_corriente", "Ver cuánto debe un cliente o registrar que pagó",
     "deuda saldo cuenta corriente pago pagar registrar cobrar taller movimientos "
     "resumen estado",
     "Buscá la cuenta por una parte del nombre, el CUIT o el número. Ahí están sus "
     "«📒 Movimientos», «➕ Cargar a la cuenta» y «💵 Registrar un pago».",
     "💳 Cuentas corrientes", ""),
    ("limite", "Cambiar el límite, el descuento o el plazo de una cuenta",
     "limite credito tope descuento plazo dias vencimiento interes mora tasa bcra punitorio "
     "configurar cuenta",
     "Elegí la cuenta y abrí «⚙️ Configuración de la cuenta»: el límite de crédito, el "
     "descuento, los días de plazo para pagar y el interés por mora (con «🔄 Traer las tasas "
     "del BCRA» se usa la tasa oficial).",
     "💳 Cuentas corrientes", ""),
    ("codigo_retiro", "El código de retiro de un taller",
     "codigo retiro seis cifras retirar autorizar taller llevar cargar cuenta",
     "Para cargarle algo a la cuenta de un taller que tiene portal hace falta su código de "
     "retiro: lo genera el taller en su portal («🔑 Generar código de retiro»), vale una sola "
     "vez, y lo dicta en el mostrador. Una cuenta sin portal no lo pide.",
     "💳 Cuentas corrientes", ""),
    ("cheque", "Verificar un cheque",
     "cheque cheques denunciado robado bcra banco verificar rechazado",
     "En la cuenta del cliente está «🔎 Verificar un cheque en el BCRA»: dice si está "
     "denunciado, con los datos del Banco Central.",
     "💳 Cuentas corrientes", ""),
    ("portal", "Que un taller entre a ver su cuenta",
     "portal taller entrar ver cuenta link acceso cliente contrasena numero",
     "El taller entra con su número de cuenta como usuario y la contraseña que le pongas en "
     "«Gestionar un mecánico existente». Sin contraseña la cuenta sirve igual para venderle, "
     "pero no entra.",
     "👥 Usuarios", "admin"),
    # ---- usuarios y entrar ----
    ("crear_usuario", "Crear el usuario de un empleado",
     "crear usuario empleado nuevo alta vendedor cajero cajera operador administrador "
     "permiso nivel",
     "En «👤 Empleados (admin / operador)» poné el nombre de usuario (con el que va a entrar), "
     "la contraseña y el nivel, y «➕ Crear empleado». Para que vea solo el depósito, en "
     "«Gestionar un empleado existente»: «📦 Que vea solo el depósito».",
     "👥 Usuarios", "admin"),
    ("contrasena", "Cambiar una contraseña (o me la olvidé)",
     "contrasena clave password olvide olvido cambiar nueva resetear blanquear perdi",
     "Las contraseñas no se pueden ver —ni yo ni nadie—: se cambian. Un administrador entra a "
     "«Gestionar un empleado existente», elige a la persona y le pone una nueva.",
     "👥 Usuarios", "admin"),
    ("entrar", "Entrar con mi usuario, o salir",
     "entrar ingresar login iniciar sesion loguear salir cerrar desloguear usuario taller "
     "cuenta portal numero",
     "Arriba a la derecha, «🔑 Ingresar»: tu usuario y tu contraseña (un taller, su número de "
     "cuenta). Para salir, tocá tu nombre («👤») y «Salir». La sesión se cierra sola después "
     "de unas horas sin uso.",
     None, ""),
    # ---- listas, precios y productos ----
    ("cargar_lista", "Cargar la lista de precios de un proveedor",
     "cargar subir importar lista precios proveedor excel planilla csv pdf actualizar nueva",
     "Subí el archivo (Excel, CSV o PDF): la app reconoce las columnas y antes de importar "
     "«💲 Qué hace esta lista con tus precios» dice cuántos suben y bajan, sin tocar nada.",
     "📁 Cargar Excel", "admin"),
    ("remito", "Cargar la mercadería que llegó (sumar stock)",
     "mercaderia llego llegada remito entrada ingreso sumar stock recibir proveedor compra "
     "factura proveedor reponer cargar",
     "Abajo de todo está «📄 Cargar remito por foto (con IA)»: sacale una foto al remito del "
     "proveedor, la app lee los ítems y suma el stock de los que coinciden con tu catálogo "
     "(revisalos antes). El stock de un solo producto se corrige en Administrar, en Productos.",
     "📁 Cargar Excel", "admin"),
    ("deshacer_lista", "Deshacer una lista que se importó mal",
     "deshacer importacion lista mal cargada revertir volver atras borrar",
     "En «↩️ Deshacer una importación» elegís cuál y vuelve todo a como estaba antes.",
     "🩺 Estado y papelera", "admin"),
    ("aumentar", "Aumentar los precios de una marca por porcentaje",
     "aumentar subir bajar precios porcentaje aumento marca inflacion remarcar actualizar",
     "Elegí la marca o el proveedor: ahí se cambian todos sus precios por un porcentaje.",
     "🏷️ Marcas", "admin"),
    ("corregir_producto", "Corregir un producto: precio, stock, medidas o foto",
     "corregir cambiar editar modificar producto precio stock cantidad descripcion foto "
     "articulo",
     "Buscá el producto y se abre para corregirlo: el precio, el stock, las medidas, dónde "
     "está y las fotos.",
     "📦 Productos", ""),
    ("escala", "La lista de un proveedor está en otra escala (el coeficiente)",
     "coeficiente escala multiplicar multiplica lista precios bajos baratos ridiculos otra "
     "moneda dolar",
     "Si los precios de una lista hay que multiplicarlos para que sean los de venta, se le "
     "pone el coeficiente a ese proveedor: muestra ejemplos de la misma pieza en otro "
     "proveedor para comparar. La venta y el presupuesto avisan cuando una lista está en otra "
     "escala.",
     "🏷️ Marcas", "admin"),
    ("unir_marcas", "Unir dos marcas que son la misma",
     "unir fusionar juntar marcas repetidas duplicadas misma mal escrita",
     "Elegí la marca repetida y unila con la buena: los productos pasan todos a una sola.",
     "🏷️ Marcas", "admin"),
    ("combos", "Armar un combo de repuestos que se venden juntos",
     "combo combos kit juntos conjunto ofrecer sugerir",
     "Un combo junta repuestos que se venden juntos, para ofrecerlos al buscar uno.",
     "🧩 Combos", ""),
    # ---- stock y compras ----
    ("reponer", "Saber qué hay que pedirle al proveedor",
     "pedir comprar reponer reposicion falta faltante stock bajo acaba termina proveedor "
     "pedido compra anotar",
     "Está lo que se va a acabar, a quién conviene comprarle, lo que no se mueve, y el "
     "mensaje armado para el proveedor. Lo que falta se anota desde el Buscador («📌 Reponer») "
     "o desde la venta («📌 Anotar para reponer») y aparece acá.",
     "📌 Para pedir", ""),
    ("tendencias", "Ver lo que más se busca en Mercado Libre",
     "mercado libre ml meli tendencias busca gente demanda moda semana",
     "Arriba de todo está lo que más se busca en Mercado Libre en repuestos esta semana, "
     "contra tu catálogo: lo que no tenés va primero.",
     "📌 Para pedir", ""),
    ("contar_stock", "Contar el stock (inventario)",
     "contar inventario stock control auditoria recuento diferencia",
     "Dice qué productos conviene contar hoy para controlar el stock de a poco, sin cerrar el "
     "negocio.",
     "🧮 Auditoría y depósito", ""),
    ("mas_vendido", "Ver lo que más se vende",
     "mas vendido vende ranking mejores productos salida rotacion",
     "En Ventas, abajo, abrí «📊 Lo que más se vende». Lo que no se mueve está en Para pedir.",
     "🧾 Ventas", ""),
    # ---- copias ----
    ("backup", "Hacer una copia de la base (backup) o restaurarla",
     "backup copia seguridad respaldo guardar base bajar descargar restaurar recuperar "
     "perdio",
     "Se baja una copia de la base a tu computadora, se deja guardada, o se restaura una. "
     "Pide un administrador: la base tiene todo.",
     "💾 Backup y config", "admin"),
    ("papelera", "Recuperar algo que se borró",
     "recuperar borre borrado papelera eliminar eliminado sin querer volver",
     "Lo que se borra va a la papelera y se recupera desde ahí.",
     "🩺 Estado y papelera", "admin"),
    # ---- autos ----
    ("ficha_auto", "Cargar o ver la ficha de un auto",
     "ficha auto vehiculo patente cliente historial cambio aceite service km kilometros "
     "mantenimiento",
     "Registrá la patente con las piezas que se le fueron cambiando («➕ Agregar al "
     "historial»). La app avisa cuándo a una pieza le toca el cambio, y «🔗 Link para que el "
     "cliente vea su auto» se lo muestra al cliente. Al terminar una venta, la patente y los "
     "km la anotan sola.",
     "🚗 Vehículos", ""),
    ("avisar_service", "Avisarle a un cliente que le toca un cambio",
     "avisar aviso cliente toca service cambio aceite vencido atrasado recordatorio mensaje "
     "vida util",
     "Arriba están los autos con una pieza que ya pasó su vida útil o que llega en los "
     "próximos días, con un solo mensaje por cliente. Después de mandarlo, «✅ Ya le avisé» lo "
     "saca de la lista por un tiempo.",
     "🚗 Vehículos", ""),
    ("link_auto", "Mandarle al cliente el link para ver su auto",
     "link cliente auto vea ver qr compartir mandar ficha celular",
     "En la ficha del auto, abrí «🔗 Link para que el cliente vea su auto»: ve desde el "
     "celular qué se le puso y cuánto le falta a cada cosa, sin su nombre ni su teléfono. Va "
     "también en el QR de la ficha en PDF.",
     "🚗 Vehículos", ""),
    ("patente", "Saber qué auto es por la patente",
     "patente dominio chapa que auto es identificar",
     "Escribí la patente: dice qué auto es y qué se le puso.",
     "🔤 Por patente", ""),
    ("vin", "Leer un número de chasis (VIN)",
     "vin chasis numero bastidor leer decodificar marca modelo ano",
     "Pegá el número de chasis y dice la marca, el modelo y el año.",
     "🔢 Chasis / VIN", ""),
    ("dtc", "Saber qué significa un código de falla",
     "falla codigo dtc escaner error motor check engine luz testigo p0",
     "Escribí el código que dio el escáner: dice qué significa y qué pieza revisar.",
     "📖 Códigos DTC", ""),
    ("repuestos_auto", "Ver qué repuestos le van a un auto",
     "repuestos auto modelo marca le va sirve aplicacion que lleva vehiculo",
     "Elegí la marca y el modelo y aparecen los repuestos que le van.",
     "🚙 Repuestos por vehículo", ""),
    ("conversor", "Convertir unidades (torque, presión, pulgadas)",
     "convertir conversor unidades torque presion pulgadas milimetros libras psi bar nm "
     "newton kilos pasar",
     "Pasa torque, presión y medidas de un sistema al otro.",
     "🧮 Conversor de unidades", ""),
    # ---- mensajes ----
    ("whatsapp", "Armar una lista de repuestos y mandarla por WhatsApp",
     "whatsapp wasap mandar enviar mensaje cotizacion cotizar presupuesto pedir pedido lista "
     "pdf varios codigos",
     "Pegá los códigos —uno por renglón o separados por coma— y tocá «➕ Agregar todos a la "
     "lista». Se arma el mensaje con las equivalencias y los precios de cada marca, para "
     "mandar por WhatsApp o bajar como PDF.",
     "📋 Lista WhatsApp", ""),
    ("alias", "Cambiar el alias de cobro o el texto del mensaje",
     "alias cbu transferencia qr texto mensaje whatsapp saludo firma cobro datos",
     "Ahí está el texto del mensaje de WhatsApp y el alias para cobrar por transferencia.",
     "💬 Mensajería y cobros", "admin"),
    # ---- el portal del taller (lo ve el taller, en su portal, y nadie más) ----
    ("portal_buscar", "Buscar un repuesto y su precio",
     "buscar repuesto codigo precio stock equivalencia marca descripcion",
     "Arriba, en «🔍 Buscar repuesto», escribí el código o qué es: salen las marcas con su "
     "precio. También me lo podés pedir a mí: escribí «buscar» y el código.",
     None, "taller"),
    ("portal_presupuesto", "Armar un presupuesto para mi cliente",
     "presupuesto cotizacion cotizar armar cliente mano obra sumar agregar cantidad pdf "
     "whatsapp mandar enviar guardar total",
     "Buscá cada repuesto, poné la cantidad y sumalo con «➕». Abajo, en «📋 Presupuesto "
     "actual», agregá el nombre del cliente y tu mano de obra: se guarda con «💾 Guardar "
     "presupuesto» y se manda con «📄 PDF» o «📲 WhatsApp».",
     None, "taller"),
    ("portal_cuenta", "Ver cuánto debo (mi cuenta corriente)",
     "deuda saldo cuenta corriente vencido disponible limite credito movimientos pagar "
     "pago estado resumen",
     "En «💳 Mi cuenta corriente» están el saldo, lo vencido y lo que te queda disponible, "
     "con los últimos movimientos. Los pagos los anota el negocio cuando los recibe.",
     None, "taller"),
    ("portal_codigo", "Generar un código de retiro",
     "codigo retiro retirar mandar alguien empleado cadete buscar llevar autorizar nombre "
     "generar",
     "Para que alguien retire repuestos a tu nombre, tocá «🔑 Generar código de retiro» y "
     "pasale el código: vale una sola vez y por unas horas, y si generás otro el anterior "
     "deja de valer. Sin el código, en el mostrador no se carga nada a tu cuenta.",
     None, "taller"),
    ("portal_anteriores", "Ver mis presupuestos anteriores",
     "anteriores guardados historial presupuestos viejos pasados ver mis",
     "Abajo de todo, en «📁 Mis presupuestos anteriores», están los que guardaste, con sus "
     "repuestos y la mano de obra. Solo ves los tuyos.",
     None, "taller"),
    ("portal_contrasena", "Cambiar la contraseña de mi portal",
     "contrasena clave password cambiar olvide olvido nueva",
     "La contraseña del portal te la cambia el negocio: pedila en el mostrador. Yo no la "
     "tengo ni la puedo ver.",
     None, "taller"),
    # ---- la app ----
    ("teclas", "Los atajos del teclado",
     "teclas atajos teclado f1 f2 f9 f10 f11 rapido click derecho mouse",
     "F1 me abre y me minimiza; F2 va a la caja de búsqueda de la pantalla; F9 termina la "
     "venta o la manda a la caja; en la caja, F10 cobra y F11 pone a cuenta. En la "
     "computadora, el click derecho sobre un producto abre sus botones.",
     None, "empleado"),
    ("teclas_de_todos", "Las teclas: F1 y F2",
     "teclas atajos teclado f1 f2 rapido",
     "F1 me abre y me minimiza, y F2 va a la caja de búsqueda de la pantalla.",
     None, ""),
    ("vista", "Cambiar entre la vista de celular y la de computadora",
     "vista celular computadora telefono pantalla chica grande modo se ve mal",
     "La app elige sola según desde dónde entres. Si no acertó, cambiala en «Vista:»: en la "
     "computadora está tocando tu nombre, arriba; en el celular, al pie de la página.",
     None, ""),
    ("avisos", "Ver los avisos del día (la campanita)",
     "avisos aviso campanita campana notificaciones alerta pendientes novedades salud",
     "Arriba, la campanita 🔔 junta lo que hay que mirar hoy: copias, importaciones, "
     "correcciones de la caja. Cada aviso tiene su botón para ir.",
     None, "empleado"),
    ("problema", "La app anda lenta o salió un error",
     "lenta lento tarda demora cuelga colgo colgada error falla fallo anda funciona rompio "
     "trabo traba cargando problema bug blanco internet conexion corto cayo wifi senal",
     "Si una pantalla tarda, esperá a que termine la barrita de arriba antes de tocar de "
     "nuevo. Si sale un cartel de error con un código, pasáselo a la gente del negocio: con "
     "ese código se encuentra qué pasó.",
     None, ""),
    ("recuperar", "Se recargó la página y perdí lo que estaba armando",
     "recargo recarga refresco actualizo f5 perdi perdio borro venta armando presupuesto "
     "recuperar medio",
     "No se pierde. La venta a medio armar queda guardada: al volver a Ventas aparece con "
     "«↩️ Recuperarla». Y el presupuesto, en el Buscador, con «↩️ Recuperarlo».",
     "🧾 Ventas", ""),
    ("fotos", "Ponerle fotos a los productos",
     "fotos foto imagen imagenes productos cargar bajar subir",
     "Las fotos se bajan solas de los catálogos, y a mano se le pone una a cada producto en "
     "Administrar, en Productos.",
     "📷 Fotos", ""),
    ("barras", "Cargar los códigos de barras",
     "codigo barras ean cargar asociar lector",
     "Acá se le enseña a la app qué código de barras tiene cada producto, para vender y "
     "buscar escaneando.",
     "🏷️ Códigos de barras", ""),
)


# ============================================================================================
# ENTENDER LO QUE SE LE ESCRIBE AL ASISTENTE
# ============================================================================================
# Nadie escribe como dice la pantalla. Para comparar, cada palabra se lleva a su «raíz»
# («cobrando», «cobré», «cobros» → «cobr»), las que no dicen nada se sacan, las que quieren
# decir lo mismo se igualan, y la que está mal escrita se cambia por la más parecida de las que
# el asistente conoce. Después cada ficha suma puntos por las palabras que comparte, y pesan
# más las raras («arqueo») que las que están en todos lados («cuenta»).

# No dicen de qué se habla (pero algunas dicen qué se quiere: ver _ASIS_PIDE_IR).
_ASIS_PALABRAS_VACIAS = frozenset("""
a al algo ahi aca alla asi con cual cuales cuando de del desde e el ella en entre era es esa ese
eso esta este esto estoy fue ha hay la las le les lo los me mi mis muy ni nos o os para pero
por que se si sin sobre son su sus te tu tus un una uno unas unos y ya yo vos usted
como donde quiero queria quisiera necesito necesitaria puedo podes podria podrias puede hago
hacer hace hacen hacemos haces hacerlo tengo tenes tiene tenemos hay ser estar
favor porfa porfavor gracias hola buenas che decime dame explicame ayudame ayuda
cuanto cuanta cuantos cuantas
""".split())

# Palabras que para el mostrador son la misma cosa. Cada grupo se iguala a su primera palabra.
_ASIS_SINONIMOS = (
    "plata dinero efectivo guita pesos monto importe",
    "fiar fiado fio fia fiale fiarle fiaron",
    "cuenta ctacte",
    "cliente clienta taller mayorista comprador",
    "contrasena clave password pass pin",
    "factura facturar facturacion fiscal",
    "arca afip",
    "devolver devolucion devuelve devuelvo devolvio devuelto devuelta reintegro reintegrar",
    "comprobante ticket recibo boleta",
    "imprimir impresion impresora imprime imprimi imprimo papel",
    "celular telefono movil",
    "computadora compu pc notebook",
    "auto vehiculo coche camioneta",
    "repuesto pieza articulo producto",
    "copia backup respaldo",
    "borrar eliminar",
    "cambiar modificar editar corregir arreglar",
    "crear nuevo nueva alta agregar sumar",
    "lista listado planilla excel",
    "proveedor distribuidor fabrica",
    "deposito almacen galpon",
    "buscar busco busca encontrar encuentro encuentra localizar",
    "ubicacion lugar estante estanteria",
    "equivalencia equivalente reemplazo alternativa cruce",
    "vender venta vendi vendio vendo vende vendido despachar",
    "cobrar cobro cobranza",
    "pedir pedido pido pide piden pidio pidieron encargar",
    "usuario empleado vendedor cajero cajera operador",
    "whatsapp wasap wsp guasap",
    "descuento rebaja bonificacion",
    "mensaje texto",
    "error equivocacion equivoque equivoco equivocado equivocar mal",
    "arqueo cierre cerrar",
)

# Palabras que se cambian enteras, antes de sacarles la raíz: «¿cuánto sale?» es preguntar el
# precio, pero «sale» y «salir» tienen la misma raíz, y contestaba cómo se sale de la sesión.
_ASIS_QUIERE_DECIR = {"sale": "precio", "salen": "precio", "cuesta": "precio",
                      "cuestan": "precio", "vale": "precio", "valen": "precio",
                      "costo": "precio", "debo": "deuda", "debe": "deuda", "deben": "deuda"}

# Las terminaciones que se le sacan a una palabra (ya sin el plural), de la más larga a la más
# corta. «an» y «en» —«cobran», «venden»— solo si quedan cuatro letras: «orden» no es un verbo.
_ASIS_TERMINACIONES = ("imiento", "amiento", "acion", "mente", "iendo", "ando", "aron", "ieron",
                       "amos", "emos", "imos", "ada", "ado", "ida", "ido", "aba", "ia", "ar",
                       "er", "ir", "an", "en", "a", "o", "e")
# El pronombre pegado al verbo: «fiarle», «ponerlo», «devolvérselo»; y «llevame», «decime».
_ASIS_PRONOMBRE_PEGADO = re.compile(r"^(.{2,}[aei]r)(se)?(lo|la|le|los|las|les|me|nos)$")
_ASIS_PEGADO_AL_VOS = re.compile(r"^(.{3,}[aei])me$")


def _asis_raiz(palabra):
    """«cobrando», «cobros», «cobrarle» → «cobr». Los números y los códigos quedan como están."""
    if len(palabra) <= 3 or any(caracter.isdigit() for caracter in palabra):
        return palabra
    pegado = _ASIS_PRONOMBRE_PEGADO.match(palabra) or _ASIS_PEGADO_AL_VOS.match(palabra)
    if pegado:
        palabra = pegado.group(1)
    if palabra.endswith("es") and len(palabra) >= 6:
        palabra = palabra[:-2]
    elif palabra.endswith("s") and len(palabra) >= 4:
        palabra = palabra[:-1]
    for terminacion in _ASIS_TERMINACIONES:
        if (palabra.endswith(terminacion)
                and len(palabra) - len(terminacion) >= (4 if terminacion in ("an", "en") else 3)):
            return palabra[:-len(terminacion)]
    return palabra


def _asis_iguales():
    """{raíz: la raíz de su grupo de sinónimos}."""
    iguales = {}
    for grupo in _ASIS_SINONIMOS:
        raices = [_asis_raiz(p) for p in grupo.split()]
        for raiz in raices:
            iguales.setdefault(raiz, raices[0])
    return iguales


_ASIS_IGUALES = _asis_iguales()


def _asis_palabras(texto, conocidas=None, raices=()):
    """Las raíces de lo que dice un texto, sin acentos ni signos, igualados los sinónimos.

    Con `conocidas` (las de una pregunta, {palabra entera: su raíz}, y `raices`, las raíces
    que están en alguna ficha): la que no se conoce se cambia por la más parecida —«faktura» → «factura», «kobrar» → «cobrar»—. Se compara la
    palabra entera y no la raíz: en cuatro letras, una sola distinta ya es otra palabra."""
    limpio = _sin_emoji(str(texto or ""))
    # «holaaaa», «graciasss»: tres o más letras iguales seguidas son una.
    limpio = re.sub(r"([a-z])\1{2,}", r"\1", limpio)
    palabras = []
    for palabra in limpio.split():
        # Una letra suelta no dice nada («zzz» queda en «z»); un número suelto, sí.
        if palabra in _ASIS_PALABRAS_VACIAS or (len(palabra) == 1 and not palabra.isdigit()):
            continue
        palabra = _ASIS_QUIERE_DECIR.get(palabra, palabra)
        raiz = _asis_raiz(palabra)
        if (conocidas is not None and palabra not in conocidas and len(palabra) >= 5
                and raiz not in raices
                and not any(caracter.isdigit() for caracter in palabra)):
            parecidas = difflib.get_close_matches(palabra, conocidas, n=1, cutoff=0.8)
            raiz = conocidas[parecidas[0]] if parecidas else raiz
        palabras.append(_ASIS_IGUALES.get(raiz, raiz))
    return palabras


def _asis_ficha(nombre, tipo, titulo, claves, texto, destino, quien=""):
    return {"nombre": nombre, "tipo": tipo, "titulo": titulo, "texto": texto, "claves": claves,
            "destino": destino, "quien": quien,
            "_titulo": set(_asis_palabras(titulo)), "_claves": set(_asis_palabras(claves)),
            "_texto": set(_asis_palabras(texto))}


def fichas_del_asistente():
    """Todo lo que sabe, armado una vez por proceso: {"fichas", "por_nombre", "peso" de cada
    raíz, "vocablos": {palabra entera: su raíz}, "raices": las que están en alguna ficha}."""
    cosecha = _asis_cosecha()
    if "indice" in _ASIS_MEMORIA:
        return _ASIS_MEMORIA["indice"]
    fichas = []
    for pagina in PAGINAS:
        fichas.append(_asis_ficha(f"pantalla:{pagina}", "pantalla", pagina, "",
                                  PARA_QUE_SIRVE.get(pagina, ""), {"pagina": pagina}))
    for pagina, (solapas, _clave) in SOLAPAS_DE_LA_PAGINA.items():
        for solapa in solapas:
            fichas.append(_asis_ficha(f"solapa:{solapa}", "solapa", solapa, "",
                                      PARA_QUE_SIRVE_LA_SOLAPA.get(solapa, ""),
                                      {"pagina": pagina, "solapa": solapa}))
    for grupo in GRUPOS_MANTENIMIENTO:
        fichas.append(_asis_ficha(f"grupo:{grupo}", "grupo", grupo, "",
                                  "Un grupo de herramientas de Mantenimiento.",
                                  _asis_destino_de(grupo)))
    for titulo, _grupo, que_hace, claves in HERRAMIENTAS_MANTENIMIENTO:
        fichas.append(_asis_ficha(f"herramienta:{titulo}", "herramienta", titulo, claves,
                                  que_hace, _asis_destino_de(titulo)))
    for nombre, titulo, claves, pasos, donde, quien in COMO_HAGO_DEL_ASISTENTE:
        fichas.append(_asis_ficha(f"como:{nombre}", "como", titulo, claves, pasos,
                                  _asis_destino_de(donde) if donde else None, quien))
    # Las secciones que se pueden dejar abiertas al llegar: {(pantalla, título): clave}. Un
    # «cómo hago» cuyo PRIMER botón nombrado es una de su pantalla («📋 Ventas y cierre de
    # caja», en el del arqueo) llega con ella abierta. El primero y no cualquiera: el de crear
    # una cuenta nombra al final «Cargar muchas cuentas», y no es a eso a lo que se va.
    se_abren = {(destino["pagina"], _asis_titulo_limpio(texto)): abrir
                for que, texto, destino, _seccion, abrir, _quien in cosecha
                if abrir and _asis_titulo_limpio(texto)}
    # Y las que una pantalla abierta le muestra solo al personal: {(pantalla, título): quién}.
    # Un «cómo hago» que nombra una («🎙️ Buscar por voz») es de ese mismo personal: al
    # invitado no se le explica algo que en su pantalla no está.
    del_personal = {(destino["pagina"], _asis_titulo_limpio(texto)): quien
                    for que, texto, destino, _seccion, _abrir, quien in cosecha
                    if quien and que != "ayuda" and _asis_titulo_limpio(texto)}
    for ficha in fichas:
        if ficha["tipo"] == "como" and ficha["destino"]:
            nombrados = re.findall(r"«([^»]+)»", ficha["texto"])
            clave = se_abren.get((ficha["destino"]["pagina"],
                                  _asis_titulo_limpio((nombrados or [""])[0])))
            if clave:
                ficha["destino"] = {**ficha["destino"], "abrir": clave}
            for nombrado in nombrados:
                quien = del_personal.get((ficha["destino"]["pagina"],
                                          _asis_titulo_limpio(nombrado)))
                if quien and ficha["quien"] != "admin":
                    ficha["quien"] = quien
    vistas = {ficha["titulo"] for ficha in fichas}
    for que, texto, destino, seccion, abrir, quien in cosecha:
        if que in ("seccion", "titulo"):
            titulo = _asis_titulo_limpio(texto)
            if not titulo or titulo in vistas:
                continue
            vistas.add(titulo)
            fichas.append(_asis_ficha(
                f"seccion:{titulo}", "seccion", titulo, "",
                "Es una sección de esa pantalla: se abre tocando su título."
                if que == "seccion" else "Está en esa pantalla, con ese título.",
                {**destino, "seccion": titulo, **({"abrir": abrir} if abrir else {})}, quien))
        else:
            entero = _asis_frases_enteras(texto)
            if len(entero) < 60:
                continue
            donde = {**destino, **({"seccion": _asis_titulo_limpio(seccion)}
                                   if _asis_titulo_limpio(seccion) else {})}
            titulo = "Cómo funciona " + camino_del_asistente(donde)
            if titulo in vistas:
                titulo += " (sigue)"
            vistas.add(titulo)
            fichas.append(_asis_ficha(f"ayuda:{len(fichas)}", "ayuda", titulo, "", entero, donde,
                                      quien))
    # Cuánto pesa cada palabra: las que están en pocas fichas dicen más.
    en_cuantas = collections.Counter()
    for ficha in fichas:
        en_cuantas.update(ficha["_titulo"] | ficha["_claves"] | ficha["_texto"])
    peso = {palabra: math.log(1 + len(fichas) / veces) for palabra, veces in en_cuantas.items()}
    # Las palabras enteras que conoce, con su raíz: contra ellas se corrige lo mal escrito.
    enteras = {}
    for texto in [" ".join(_ASIS_SINONIMOS)] + [
            f"{f['titulo']} {f['claves']} {f['texto']}" for f in fichas]:
        for palabra in _sin_emoji(texto).split():
            if len(palabra) >= 4 and palabra not in _ASIS_PALABRAS_VACIAS:
                enteras.setdefault(palabra, _asis_raiz(palabra))
    indice = {"fichas": fichas, "por_nombre": {f["nombre"]: f for f in fichas}, "peso": peso,
              "vocablos": enteras, "raices": frozenset(peso) | frozenset(_ASIS_IGUALES)}
    _ASIS_MEMORIA["indice"] = indice
    return indice


# Cuánto vale una palabra según dónde aparece en la ficha (y un poco más si además está en el
# título: «factura» está en las claves de cuatro fichas, pero una sola se llama «Hacer una
# factura»), y cada clase de ficha: las escritas a mano para lo de todos los días van primero;
# una ayuda larga nombra de todo y vale menos.
_ASIS_VALE = (("_claves", 3.0), ("_titulo", 2.6), ("_texto", 1.0))
_ASIS_ADEMAS_EN_EL_TITULO = 0.6
_ASIS_CLASE = {"como": 1.15, "pantalla": 1.05, "solapa": 1.05, "grupo": 0.95,
               "herramienta": 1.0, "seccion": 1.0, "ayuda": 0.8}


def fichas_que_responden(pregunta, pagina_actual=None):
    """Las fichas que mejor responden, de mayor a menor: [(qué tan bien, ficha)].

    «Qué tan bien» es cuánto de lo preguntado cubre la ficha, pesando las palabras: 1 es que
    todas las palabras están en sus claves (pasa de 1 si además están en el título). La
    pantalla en la que se está desempata a favor, y entre dos iguales va primero la que está
    antes en la lista (lo de todos los días)."""
    indice = fichas_del_asistente()
    palabras = list(dict.fromkeys(
        _asis_palabras(pregunta, indice["vocablos"], indice["raices"])))
    if not palabras:
        return []
    total = sum(indice["peso"].get(p, 3.0) for p in palabras) * _ASIS_VALE[0][1]
    puntuadas = []
    for orden_de_la_ficha, ficha in enumerate(indice["fichas"]):
        puntos = 0.0
        for palabra in palabras:
            vale = next((v for campo, v in _ASIS_VALE if palabra in ficha[campo]), 0.0)
            if vale and palabra in ficha["_titulo"] and palabra in ficha["_claves"]:
                vale += _ASIS_ADEMAS_EN_EL_TITULO
            puntos += vale * indice["peso"].get(palabra, 3.0)
        if not puntos:
            continue
        acierto = puntos / total * _ASIS_CLASE.get(ficha["tipo"], 1.0)
        # El título entero nombrado («cierre de caja», «para pedir») es lo que se busca.
        if ficha["_titulo"] and ficha["_titulo"] <= set(palabras):
            acierto += 0.25
        if pagina_actual and ficha["destino"] and ficha["destino"]["pagina"] == pagina_actual:
            acierto += 0.03
        puntuadas.append((acierto, ficha["tipo"] != "como", orden_de_la_ficha, ficha))
    puntuadas.sort(key=lambda fila: (-fila[0], fila[1], fila[2]))
    return [(acierto, ficha) for acierto, _clase, _orden, ficha in puntuadas]


def ficha_que_se_llama(nombre):
    """La pantalla, la solapa o el grupo que se llama así («caja», «para pedir», «usuarios»),
    o None. Igual primero; después, el principio de un nombre largo."""
    lugares = [f for f in fichas_del_asistente()["fichas"]
               if f["tipo"] in ("pantalla", "solapa", "grupo")]
    llano = _sin_emoji(nombre)
    return (next((f for f in lugares if _sin_emoji(f["titulo"]) == llano), None)
            or next((f for f in lugares if _es_el_mismo_nombre(nombre, f["titulo"])), None))


# ============================================================================================
# LO QUE NO SE LE PUEDE SACAR AL ASISTENTE
# ============================================================================================
# No hay nada que sacarle —no conoce una sola clave—, pero quien lo intenta merece una
# respuesta clara, la misma siempre, y el camino legítimo si lo que quería era legítimo.
# Se mira antes que nada, sobre el texto sin acentos y en minúsculas.

# Pedir que le digan o le muestren una contraseña, una clave o un secreto.
_ASIS_PIDE_UN_SECRETO = re.compile(
    r"\b(decime|deci|dame|pasame|mostrame|mostra|muestrame|ver|saber|averigua\w*|cual es|cuales "
    r"son|lista\w*|revela\w*|recupera\w*|lee\w*|imprimi\w*|exporta\w*|adivina\w*)\b.{0,40}"
    r"\b(contrasenas?|claves?|passwords?|pass|pin|tokens?|secretos?|secrets?|credencial\w*|"
    r"api ?keys?|hash\w*|certificados? privad\w*|clave privada)\b"
    r"|\b(contrasenas?|claves?|passwords?)\b.{0,25}\bde(l| la| los| las)? "
    r"(admin\w*|duen\w*|jef\w*|otr\w*|todos|cajer\w*|emplead\w*|usuarios?)\b")
# Pedir saltear un candado, subir de nivel o romper algo.
_ASIS_PIDE_SALTEAR = re.compile(
    r"\b(saltea\w*|salta\w*|evita\w*|esquiva\w*|burla\w*|bypass\w*|hacke\w*|jacke\w*|crackea\w*|"
    r"rompe\w*|vulnera\w*|desactiva\w*|deshabilita\w*|apaga\w*|saca\w*|quita\w*|sin)\b.{0,30}"
    r"\b(candados?|contrasenas?|claves?|passwords?|login|permisos?|seguridad|bloqueos?|"
    r"frenos?|limites?|proteccion\w*|autenticacion|control\w*)\b"
    r"|\b(hacerme|haceme|ser|soy|volverme|convertirme|entrar como|pasar a|dame permisos? de|"
    r"dame acceso de|nivel de)\b.{0,12}\b(admin\w*|duen\w*|root|superusuario)\b"
    r"|\b(inyeccion|injection|sql|xss|exploit\w*|vulnerabilidad\w*|brecha\w*|payload|"
    r"puerta trasera|backdoor|fuerza bruta|keylogger|malware|phishing)\b"
    r"|\b(drop|delete from|union select|insert into|update \w+ set)\b|<script|javascript:|"
    r"\bselect\b.{0,40}\bfrom\b|"
    r"\bor 1 ?= ?1\b")
# Querer cambiarle «las instrucciones».
_ASIS_PIDE_OTRO_PAPEL = re.compile(
    r"\b(ignora\w*|olvida\w*|desobedec\w*|omiti\w*|anula\w*)\b.{0,30}\b(instruccion\w*|reglas?|"
    r"anterior\w*|indicacion\w*|limites?|restriccion\w*|todo)\b"
    r"|\b(system prompt|prompt|jailbreak|modo desarrollador|developer mode|modo dios|dan mode|"
    r"modo administrador|modo debug|sin restricciones|sin filtros?)\b"
    r"|\b(actua|actuar|comportate|hace de cuenta|fingi|simula|pretende)\b.{0,25}\b(como|que "
    r"sos|que eres|ser)\b"
    r"|\b(sos|eres) ahora\b|\ba partir de ahora\b|\btus instrucciones\b|\brepeti\w* (todo )?lo "
    r"(de arriba|anterior)\b")

ASISTENTE_NO_SECRETOS = (
    "🔒 **No tengo contraseñas ni claves, y no hay forma de que te las diga**: no las conozco. "
    "La app no guarda ninguna contraseña escrita; ni el dueño las puede ver.\n\n"
    "Si te olvidaste la tuya, un administrador te pone una nueva.")
ASISTENTE_NO_SALTEA = (
    "🛡️ **Eso no lo puedo hacer, ni yo ni nadie desde acá.** No cambio permisos ni salteo "
    "ningún candado: solo explico y llevo a las pantallas que ya tenés. Cada pantalla pide su "
    "contraseña por su cuenta, y los permisos los da un administrador.\n\n"
    "Sin entrar se puede mirar el Buscador, la Lista WhatsApp y el Modo Mecánico.")
ASISTENTE_NO_CAMBIA = (
    "🤖 Soy un asistente de respuestas fijas: no tengo instrucciones escondidas que se puedan "
    "cambiar, ni acceso a los datos del negocio. Te puedo explicar cómo se hace algo o "
    "llevarte a una pantalla.")


def lo_que_no_se_le_saca(pregunta):
    """La respuesta fija si lo que se pide es una clave, saltear un candado o cambiarle el
    papel: ("secreto" | "saltear" | "papel", texto). None si es una pregunta cualquiera."""
    llano = unicodedata.normalize("NFKD", str(pregunta or "")).encode("ascii", "ignore").decode()
    llano = re.sub(r"\s+", " ", llano.lower())
    if _ASIS_PIDE_OTRO_PAPEL.search(llano):
        return "papel", ASISTENTE_NO_CAMBIA
    if _ASIS_PIDE_UN_SECRETO.search(llano):
        return "secreto", ASISTENTE_NO_SECRETOS
    if _ASIS_PIDE_SALTEAR.search(llano):
        return "saltear", ASISTENTE_NO_SALTEA
    return None


def limpiar_lo_escrito(texto):
    """Lo que se le escribió, listo para comparar: un renglón, sin signos de control, recortado."""
    texto = "".join(ch if ch.isprintable() else " " for ch in str(texto or ""))
    return re.sub(r"\s+", " ", texto).strip()[:ASISTENTE_LARGO_MAXIMO]


def _asis_para_buscar(texto):
    """Lo que va a la caja del Buscador: letras, números y los signos de un código. Es lo mismo
    que escribirlo ahí a mano; se limpia igual, porque además se muestra en el botón."""
    return re.sub(r"\s+", " ", re.sub(r"[^0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ ./,+#-]", " ",
                                      str(texto or ""))).strip()[:60]


# ============================================================================================
# LA RESPUESTA DEL ASISTENTE
# ============================================================================================
# responder_del_asistente() no toca nada: recibe lo escrito y lo que ve quien pregunta, y
# devuelve qué decir y qué botones ofrecer. Llevar a un lugar es otro paso (ver
# llevar_con_el_asistente()), que vuelve a mirar si ese lugar se puede.
#
# Una respuesta es {"texto", "botones": [(rótulo, qué, cuál)], "ir": ficha o None,
# "buscar": texto o None}. «qué» es "ir" (cuál: el nombre de una ficha), "ver" (mostrar esa
# ficha), "buscar" (cuál: lo que se busca) o "preguntar" (cuál: una pregunta de ejemplo).

# Con estas palabras adelante se pide que lo lleven, no que le expliquen.
_ASIS_PIDE_IR = re.compile(
    r"^(por favor |che |quiero |necesito |queria |me |podes |podrias )*"
    r"(llevame|lleva me|llevar|llevarme|lleveme|ir|irme|anda|andate|vamos|vayamos|abri|abrir|"
    r"abrime|abrirme|mostrame|mostrar|muestrame|mandame|enviame|dirigime|guiame)\b"
    r"( a| al| a la| a los| a las| en| la| el| los| las| lo| hasta| hacia| donde)*"
    r"\s+(?P<resto>.+)$")
# «buscar W712», «equivalencia de PH5949», «precio del 271205», «tenés GP1?».
_ASIS_PIDE_BUSCAR = re.compile(
    r"^(por favor |che |quiero |necesito |me )*"
    r"(buscar|busca|buscame|equivalencias?|equivalentes?|reemplazos?|precio|stock|"
    r"cuanto sale|cuanto cuesta|cuanto vale|tenes|tienen|hay)"
    r"( de| del| de la| para| para el| el| la| un| una| codigo| el codigo)*\s+(?P<resto>.+)$")
_ASIS_SALUDO = re.compile(r"^(hola+|buenas+|buen dia|buenos dias|buenas tardes|buenas noches|"
                          r"que tal|como va|como andas|hey|ey)\b")
_ASIS_GRACIAS = re.compile(r"^(muchas |mil )?(gracias+|genial|perfecto|buenisimo|joya|listo|"
                           r"barbaro|dale gracias|ok gracias)\b")
_ASIS_SI = re.compile(r"^(si|sip|dale|ok|oka|okey|bueno|de una|hacelo|llevame|llevame ahi|ir|"
                      r"vamos|ahi|eso|ese|esa|andá|anda|por favor)$")
_ASIS_INDICE = re.compile(r"^(indice|temas|los temas|lista de temas|todos los temas|que temas "
                          r"hay|que sabes|todo lo que sabes|que preguntas hay|preguntas "
                          r"frecuentes|faq|ver todo|mostrame todo lo que sabes)$")
_ASIS_VOLVER = re.compile(r"^(volver|volve|volveme|volvamos|atras|para atras|regresar|"
                          r"regresa|donde estaba|a donde estaba|volver atras|volver a donde "
                          r"estaba)$")
_ASIS_QUE_SOS = re.compile(r"\b(quien sos|que sos|quien eres|que eres|como te llamas|sos un "
                           r"robot|sos una persona|sos humano|sos ia|sos una ia)\b")
_ASIS_QUE_HACES = re.compile(r"^(ayuda|ayudame|help|que podes hacer|que sabes hacer|que haces|"
                             r"para que servis|como funcionas|como te uso|que te puedo pedir|"
                             r"que te puedo preguntar|opciones|menu)$")
_ASIS_NOVEDADES = re.compile(r"\b(que hay de nuevo|novedad\w*|lo nuevo|que cambio|que "
                             r"cambiaron|ultimos cambios|ultimas mejoras|que agregaron|que "
                             r"tiene de nuevo|actualizacion\w*)\b")
_ASIS_ACA = re.compile(r"\b(aca|esta pantalla|esta pagina|esta seccion|esta solapa|donde "
                       r"estoy|en que pantalla estoy)\b")
# Una patente argentina (AB123CD o ABC123) y algo con pinta de código de repuesto.
_ASIS_PATENTE = re.compile(r"^(?:[A-Za-z]{2}\s?\d{3}\s?[A-Za-z]{2}|[A-Za-z]{3}\s?\d{3})$")
_ASIS_CODIGO = re.compile(r"^(?=.*\d)[0-9A-Za-z][0-9A-Za-z./+-]{3,24}$")
_ASIS_FALLA = re.compile(r"^[PCBUpcbu][0-9A-Fa-f]{4}$")      # P0300, U0100: del escáner
# Las teclas se llaman como un código («F10»): son una pregunta, no una búsqueda.
_ASIS_TECLA = re.compile(r"^f\d{1,2}$", re.I)

# Qué tan bien tiene que responder una ficha para contestar con ella sin preguntar, y desde
# cuánto se ofrece como «¿será esto?».
ASISTENTE_SEGURO = 0.5
ASISTENTE_QUIZAS = 0.22
# Y para llevar sin preguntar cuando se pidió «llevame a…» con otras palabras que el nombre.
ASISTENTE_PARA_IR_SOLO = 0.62


def _asis_se_puede(ficha, contexto):
    """¿Quien pregunta ve la pantalla de esa ficha, y puede hacer lo que dice? Las que no tienen
    destino (la vista, entrar) son de todos; lo que pide entrar, de quien entró; lo del portal
    del taller, del taller."""
    nivel = contexto.get("nivel")
    if nivel == "taller":
        # El taller en su portal: lo de su portal, y lo que es de todos y no lleva a ningún lado.
        return ficha["quien"] == "taller" or (not ficha["quien"] and not ficha["destino"])
    if ficha["quien"] == "taller" or (ficha["quien"] and nivel == "invitado"):
        return False
    return not ficha["destino"] or ficha["destino"]["pagina"] in (contexto.get("visibles") or ())


def _asis_boton_ir(ficha):
    destino = ficha["destino"]
    donde = destino.get("herramienta") or destino.get("grupo") or destino.get("solapa") \
        or destino["pagina"]
    return (f"➡️ Llevame a {donde[:44]}", "ir", ficha["nombre"])


def _asis_escapar(texto):
    """Para st.markdown: dos «$» en un texto se leen como una fórmula."""
    return re.sub(r"(?<!\\)\$", r"\\$", str(texto or ""))


def _asis_respuesta_de(ficha, contexto):
    """Lo que se dice de una ficha a quien la puede ver: el título, el texto, el camino."""
    texto = f"**{ficha['titulo']}**\n\n{_asis_escapar(ficha['texto'])}"
    botones = []
    if ficha["destino"]:
        texto += f"\n\n📍 {camino_del_asistente(ficha['destino'])}"
        botones.append(_asis_boton_ir(ficha))
    if ficha["quien"] == "admin" and contexto.get("nivel") != "admin":
        texto += ("\n\n🔒 Adentro pide un administrador: la pantalla le va a pedir su usuario "
                  "y su contraseña.")
    return {"texto": texto, "botones": botones, "ir": None, "buscar": None,
            "ficha": ficha["nombre"]}


def _asis_simple(texto, botones=()):
    return {"texto": texto, "botones": list(botones), "ir": None, "buscar": None, "ficha": None}


# Con qué ayuda al taller en su portal, dicho en una frase.
ASISTENTE_LO_DEL_PORTAL = ("buscar un repuesto, armar un presupuesto, tu cuenta corriente y el "
                           "código de retiro")


def _asis_lo_abierto(contexto):
    """Las pantallas de quien pregunta, en una frase: «🔍 Buscador, 📋 Lista WhatsApp y 🛠️ Modo
    Mecánico»."""
    visibles = list(contexto.get("visibles") or [])
    if len(visibles) < 2:
        return "".join(visibles) or "lo que está abierto"
    return ", ".join(visibles[:-1]) + " y " + visibles[-1]


def _asis_no_se_puede(ficha, contexto):
    """Para quien no ve esa pantalla: con qué SÍ se lo puede ayudar, sin los pasos de lo otro
    ni el nombre de la pantalla. Al invitado, además, ejemplos de lo suyo para tocar."""
    if contexto.get("nivel") == "invitado":
        return _asis_simple(
            f"🔒 Sin entrar te ayudo con **{_asis_lo_abierto(contexto)}**. Lo demás es del "
            "personal del negocio: si sos del negocio, entrá con tu usuario y tu contraseña "
            "(«🔑 Ingresar», arriba).",
            [(e, "preguntar", e) for e in ejemplos_del_asistente(contexto)[:3]])
    if contexto.get("nivel") == "taller":
        return _asis_simple(
            f"🔒 Desde tu portal te ayudo con **{ASISTENTE_LO_DEL_PORTAL}**. Lo demás es del "
            "negocio.",
            [(e, "preguntar", e) for e in ejemplos_del_asistente(contexto)[:3]])
    return _asis_simple(f"🔒 Con tu usuario no tenés esa pantalla: ves "
                        f"{_asis_lo_abierto(contexto)}. Eso lo hace otra persona del negocio.")


def ejemplos_del_asistente(contexto):
    """Tres o cuatro preguntas de ejemplo, de lo que quien pregunta puede hacer, empezando por
    la pantalla en la que está."""
    indice = fichas_del_asistente()
    comos = [f for f in indice["fichas"] if f["tipo"] == "como"
             and (f["destino"] or f["quien"] == "taller") and _asis_se_puede(f, contexto)]
    comos.sort(key=lambda f: bool(f["destino"])
               and f["destino"]["pagina"] != contexto.get("pagina"))
    return [f["titulo"] for f in comos[:4]]


def temas_del_asistente(contexto):
    """Todo lo que quien pregunta puede preguntarle, por pantalla: [(pantalla, [títulos])]. Lo
    del portal del taller va como «Tu portal»; lo que no es de ninguna, «En cualquier pantalla»."""
    grupos = {}
    for ficha in fichas_del_asistente()["fichas"]:
        if ficha["tipo"] == "como" and _asis_se_puede(ficha, contexto):
            donde = (ficha["destino"]["pagina"] if ficha["destino"]
                     else "Tu portal" if ficha["quien"] == "taller" else "En cualquier pantalla")
            grupos.setdefault(donde, []).append(ficha["titulo"])
    orden_de_las_pantallas = ["Tu portal"] + list(contexto.get("visibles") or [])
    return sorted(grupos.items(), key=lambda par: (
        orden_de_las_pantallas.index(par[0]) if par[0] in orden_de_las_pantallas else 99))


def responder_del_asistente(pregunta, contexto):
    """Qué contesta el asistente. No toca nada: ni la sesión, ni la base, ni la pantalla.

    `contexto`: {"visibles": las pantallas que quien pregunta tiene en la barra, "pagina": en
    cuál está, "nivel": "invitado" | "operador" | "admin", "ultima": el nombre de la ficha de la
    respuesta anterior, "volver": la pantalla de la que lo sacó la última vez}."""
    visibles = list(contexto.get("visibles") or [])
    contexto = {**contexto, "visibles": visibles}
    escrito = limpiar_lo_escrito(pregunta)
    if not escrito:
        return _asis_simple("Escribime qué querés hacer o a dónde querés ir.")
    if not _sin_emoji(escrito):          # «?», «…», un emoji solo
        escrito = "ayuda"
    no = lo_que_no_se_le_saca(escrito)
    if no:
        botones = []
        if no[0] == "secreto":
            ficha = fichas_del_asistente()["por_nombre"]["como:contrasena"]
            if _asis_se_puede(ficha, contexto):
                botones.append(("🔑 Cómo se cambia una contraseña", "ver", ficha["nombre"]))
        return _asis_simple(no[1], botones)
    llano = _sin_emoji(" " + escrito)
    indice = fichas_del_asistente()

    # «sí», «dale», «llevame»: a donde decía la respuesta anterior.
    if _ASIS_SI.match(llano) and contexto.get("ultima"):
        ficha = indice["por_nombre"].get(contexto["ultima"])
        if ficha and ficha["destino"] and _asis_se_puede(ficha, contexto):
            return {**_asis_simple(f"Te llevo a {camino_del_asistente(ficha['destino'])}."),
                    "ir": ficha["nombre"]}
    # Al invitado se le habla de lo suyo: los ejemplos no nombran la caja ni las cuentas. Y al
    # taller, de su portal.
    invitado = contexto.get("nivel") == "invitado"
    if contexto.get("nivel") == "taller" and (
            (_ASIS_SALUDO.match(llano) and len(llano.split()) <= 4) or _ASIS_QUE_SOS.search(llano)
            or _ASIS_QUE_HACES.match(llano) or _ASIS_ACA.search(llano)):
        return _asis_simple(
            f"🤖 Soy el asistente. En tu portal te ayudo con {ASISTENTE_LO_DEL_PORTAL}: te "
            "explico cómo se hace y te busco un repuesto («buscar W712/75»). No veo tu cuenta "
            "ni tus datos: eso lo ves vos, en tu pantalla.",
            [(e, "preguntar", e) for e in ejemplos_del_asistente(contexto)])
    # «temas»: todo lo que se le puede preguntar, por pantalla.
    if _ASIS_INDICE.match(llano):
        return _asis_simple(
            "Esto es lo que te puedo explicar. Escribime cualquiera, con tus palabras:\n\n"
            + "\n".join(f"- **{donde}**: " + " · ".join(titulos)
                        for donde, titulos in temas_del_asistente(contexto)))
    # «volver»: a la pantalla de la que lo sacó.
    if _ASIS_VOLVER.match(llano):
        anterior = indice["por_nombre"].get(f"pantalla:{contexto.get('volver')}")
        if anterior and _asis_se_puede(anterior, contexto):
            return {**_asis_simple(f"Volvemos a {anterior['titulo']}."),
                    "ir": anterior["nombre"]}
        return _asis_simple("Todavía no te llevé a ningún lado. Decime a dónde querés ir.")
    if _ASIS_SALUDO.match(llano) and len(llano.split()) <= 4:
        return _asis_simple(
            ("¡Hola! 👋 Te ayudo a buscar un repuesto y lo que sirve en su lugar, a armar la "
             "lista para pedir por WhatsApp o a identificar un auto. Decime qué necesitás."
             if invitado else
             "¡Hola! 👋 Decime qué querés hacer —«cobrar una venta», «dónde cargo una lista»— o "
             "a dónde querés ir, y te explico o te llevo."),
            [(e, "preguntar", e) for e in ejemplos_del_asistente(contexto)])
    if _ASIS_GRACIAS.match(llano):
        return _asis_simple("¡De nada! Acá estoy cuando me necesites. 🙌")
    if _ASIS_QUE_SOS.search(llano):
        return _asis_simple(
            (f"🤖 Soy el asistente de la app. Sin entrar te ayudo con {_asis_lo_abierto(contexto)}: "
             "te explico cómo se usan, te llevo y te busco un repuesto. No veo datos ni "
             "contraseñas."
             if invitado else
             "🤖 Soy el asistente de la app. Conozco todas las pantallas y cómo se hace cada "
             "cosa, y te llevo a donde me pidas. No veo los datos del negocio ni las "
             "contraseñas: solo sé dónde está cada cosa."))
    if _ASIS_QUE_HACES.match(llano):
        return _asis_simple(
            (f"Sin entrar te ayudo con **{_asis_lo_abierto(contexto)}**:\n\n"
             "- **Buscar un repuesto**: «buscar W712/75», o el código solo.\n"
             "- **Explicarte**: «¿qué bujía le va?», «¿cómo busco por medidas?».\n"
             "- **Llevarte**: «llevame al modo mecánico», «códigos de falla».\n\n"
             "Escribí como te salga: entiendo sin acentos y con errores."
             if invitado else
             "Me podés pedir tres cosas:\n\n"
             "- **Que te lleve**: «llevame a la caja», «abrí cuentas corrientes».\n"
             "- **Que te explique**: «¿cómo hago una devolución?», «¿dónde cambio un precio?».\n"
             "- **Que busque un repuesto**: «buscar W712/75».\n\n"
             "Después de llevarte, «volver» te trae de nuevo, y «temas» lista todo lo que sé. "
             "Escribí como te salga: entiendo sin acentos y con errores."),
            [(e, "preguntar", e) for e in ejemplos_del_asistente(contexto)])

    # «¿qué hay de nuevo?»: lo último de LO_NUEVO, para quien entró (cuenta cómo se trabaja
    # adentro: al invitado, no).
    if _ASIS_NOVEDADES.search(llano) and visibles:
        if contexto.get("nivel") == "invitado":
            return _asis_no_se_puede(None, contexto)
        return _asis_simple("**Lo último que se sumó:**\n\n" + "\n".join(
            f"- {_asis_escapar(texto)} *({donde})*" for texto, donde in LO_NUEVO[:4]))
    # «¿qué puedo hacer acá?»: la pantalla en la que está.
    if _ASIS_ACA.search(llano) and contexto.get("pagina") in visibles:
        pagina = contexto["pagina"]
        texto = f"Estás en **{pagina}**. {_asis_escapar(PARA_QUE_SIRVE.get(pagina, ''))}"
        solapas = SOLAPAS_DE_LA_PAGINA.get(pagina)
        if solapas:
            texto += "\n\nTiene estas solapas: " + ", ".join(solapas[0]) + "."
        aca = [f for f in indice["fichas"] if f["tipo"] == "como" and f["destino"]
               and f["destino"]["pagina"] == pagina and _asis_se_puede(f, contexto)][:4]
        return _asis_simple(texto, [(f["titulo"], "ver", f["nombre"]) for f in aca])

    # «buscar W712/75», o un código solo. Lo buscado va como se escribió (con sus mayúsculas,
    # sus puntos y sus barras): por eso se mira palabra por palabra, sin sacarle los signos.
    palabras_escritas = [p.strip("¿?¡!\"'«»()") or "·" for p in escrito.split()]
    con_signos = " ".join(
        unicodedata.normalize("NFKD", p).encode("ascii", "ignore").decode().lower() or "·"
        for p in palabras_escritas)
    pide_buscar = _ASIS_PIDE_BUSCAR.match(con_signos)
    lo_buscado = None
    if pide_buscar:
        resto = pide_buscar.group("resto").split()
        while len(resto) > 1 and resto[0] in ("stock", "precio", "de", "del", "el", "la",
                                              "codigo", "un", "una"):
            resto = resto[1:]
        lo_buscado = _asis_para_buscar(" ".join(palabras_escritas[-len(resto):]))
    elif (len(palabras_escritas) == 1 and _ASIS_CODIGO.match(palabras_escritas[0])
          and not _ASIS_TECLA.match(palabras_escritas[0])):
        lo_buscado = _asis_para_buscar(palabras_escritas[0])
    del_portal = contexto.get("nivel") == "taller"
    if lo_buscado and (PAGINAS[0] in visibles or del_portal):
        # Con un número adentro es un código. Sin número, solo si dijo «buscar» (o «equivalencia
        # de») y lo que sigue no es algo que el asistente sepa explicar: «buscar por medidas» y
        # «buscar hablando» son preguntas; «buscar filtro de aceite gol», una búsqueda. «Hay
        # que pedir…» no es buscar nada.
        tiene_codigo = any(ch.isdigit() for ch in lo_buscado)
        antes = r"^(por favor |che |quiero |necesito |me )*"
        dijo_buscar = bool(pide_buscar) and bool(re.match(antes + "(busc|equi|reem)", con_signos))
        # Preguntar el precio de algo es buscarlo, se llame como se llame: «filtro de aceite»
        # comparte palabras con la ficha del auto, y no es eso lo que se pregunta.
        pregunta_el_precio = bool(pide_buscar) and bool(re.match(
            antes + "(precio|cuanto (sale|cuesta|vale))", con_signos))
        del_resto = fichas_que_responden(lo_buscado, contexto.get("pagina"))
        if tiene_codigo or pregunta_el_precio or (
                dijo_buscar and (not del_resto or del_resto[0][0] < ASISTENTE_SEGURO)):
            botones = [(f"🔍 Buscar «{lo_buscado}»", "buscar", lo_buscado)]
            if del_portal:
                return {**_asis_simple(
                    f"Lo busco arriba, en «🔍 Buscar repuesto»: «{lo_buscado}». Ahí salen las "
                    "marcas con su precio.", botones),
                    "buscar": lo_buscado if pide_buscar else None}
            if (_ASIS_FALLA.match(lo_buscado) and "🛠️ Modo Mecánico" in visibles
                    and not pide_buscar):
                botones.insert(0, ("📖 Ver qué significa ese código de falla", "ir",
                                   "solapa:📖 Códigos DTC"))
                return _asis_simple(
                    f"«{lo_buscado}» parece un código de falla del escáner. Lo miro en el Modo "
                    "Mecánico, o lo busco como código de repuesto.", botones)
            if (_ASIS_PATENTE.match(lo_buscado) and "🛠️ Modo Mecánico" in visibles
                    and not pide_buscar):
                botones.insert(0, ("🔤 Ver ese auto por la patente", "ir", "solapa:🔤 Por patente"))
                return _asis_simple(
                    f"«{lo_buscado}» parece una patente. La miro en el Modo Mecánico, o la "
                    "busco como código de repuesto.", botones)
            return {**_asis_simple(
                f"Lo busco en el 🔍 Buscador: «{lo_buscado}». Ahí salen las equivalencias, el "
                "precio y el stock.", botones), "buscar": lo_buscado if pide_buscar else None}

    pide_ir = _ASIS_PIDE_IR.match(llano)
    pedido = pide_ir.group("resto") if pide_ir else escrito
    # El nombre de una pantalla o de una solapa, solo: es pedir ir. «caja», «para pedir».
    nombrada = ficha_que_se_llama(pedido)
    if nombrada:
        if not _asis_se_puede(nombrada, contexto):
            return _asis_no_se_puede(nombrada, contexto)
        return {**_asis_respuesta_de(nombrada, contexto), "ir": nombrada["nombre"]}
    mejores = fichas_que_responden(pedido, contexto.get("pagina"))
    if pide_ir and (not mejores or mejores[0][0] < ASISTENTE_QUIZAS):
        mejores = fichas_que_responden(escrito, contexto.get("pagina")) or mejores
    if not mejores or mejores[0][0] < ASISTENTE_QUIZAS:
        if _ASIS_SI.match(llano):
            return _asis_simple("¿Sí a qué? 🙂 Decime qué querés hacer o a dónde querés ir.")
        botones = [(e, "preguntar", e) for e in ejemplos_del_asistente(contexto)[:3]]
        if (PAGINAS[0] in visibles or del_portal) and _asis_para_buscar(escrito):
            botones.insert(0, (f"🔍 Buscar «{_asis_para_buscar(escrito)[:30]}» como repuesto",
                               "buscar", _asis_para_buscar(escrito)))
        return _asis_simple(
            "No encontré nada con esas palabras. Probá decirlo de otra forma, con una o dos "
            "palabras —" + ("«bujía», «medidas», «patente»" if invitado
                           else "«presupuesto», «código de retiro», «saldo»" if del_portal
                           else "«devolución», «lista de precios», «backup»")
            + "—, o mirá estos ejemplos.", botones)

    acierto, primera = mejores[0]
    if not _asis_se_puede(primera, contexto):
        # Si entre lo suyo hay una respuesta casi tan buena, es esa: «un presupuesto», para el
        # invitado, es la lista de WhatsApp. Casi tan buena y no cualquiera: a «cómo creo un
        # usuario» no se le contesta cómo se entra. Si no la hay, con qué sí se lo ayuda.
        otra = next(((a, f) for a, f in mejores if _asis_se_puede(f, contexto)), None)
        if not otra or otra[0] < max(ASISTENTE_SEGURO, acierto * 0.7):
            return _asis_no_se_puede(primera, contexto)
        acierto, primera = otra
    # Las otras que podrían ser: van como botones. Una ayuda del mismo lugar no suma nada.
    parecidas = [f for a, f in mejores[:9]
                 if f is not primera and _asis_se_puede(f, contexto)
                 and a >= max(ASISTENTE_QUIZAS, acierto * 0.6)
                 and not (f["tipo"] == "ayuda" and f["destino"] == primera["destino"])][:3]
    if acierto < ASISTENTE_SEGURO:
        return _asis_simple(
            "No estoy seguro de qué buscás. ¿Es alguna de estas?",
            [(f["titulo"][:60], "ver", f["nombre"]) for f in [primera] + parecidas])
    respuesta = _asis_respuesta_de(primera, contexto)
    # «llevame a…»: va directo si está claro a dónde. Si no, la respuesta con su botón.
    if pide_ir and primera["destino"] and acierto >= ASISTENTE_PARA_IR_SOLO:
        respuesta["ir"] = primera["nombre"]
    respuesta["botones"] += [(f["titulo"][:60], "ver", f["nombre"]) for f in parecidas]
    return respuesta


# ============================================================================================
# LA BURBUJA DEL ASISTENTE
# ============================================================================================
# Una burbuja 🤖 fija abajo a la izquierda (a la derecha está el botón de Streamlit). Se abre
# en un panel con la caja para escribir arriba —en el celular, abajo la taparía el teclado— y
# se minimiza con «➖» o sola al llevar a una pantalla, para que se vea a dónde llevó. Es una
# parte que se redibuja sola (st.fragment): preguntar no vuelve a armar la pantalla de atrás,
# que puede ser Estadísticas con sus consultas. Solo al llevar se redibuja todo.
#
# Lo que queda en la sesión: «_asis_abierto» y «_asis_charla» (las últimas preguntas con su
# respuesta). No se guarda en la base ni sale de la sesión: al salir se borra con todo.

def _asis_contexto():
    """Lo que ve quien pregunta, calculado en el momento con las mismas reglas que la barra. Si
    no se puede saber (la base ocupada), no ve nada: el asistente explica pero no lleva."""
    nivel_de_la_sesion = st.session_state.get("nivel_usuario")
    try:
        if nivel_de_la_sesion == "mecanico":
            visibles = []            # el portal del taller no tiene barra: ver app.py
        else:
            visibles = paginas_a_la_vista(es_del_deposito())
    except Exception as _err:        # noqa: BLE001 — ante la duda, a ningún lado
        anotar_error("asistente/paginas_a_la_vista", _err)
        visibles = []
    charla = st.session_state.get("_asis_charla") or []
    return {"visibles": visibles, "pagina": st.session_state.get("pagina_actual"),
            "nivel": ("taller" if nivel_de_la_sesion == "mecanico" else "admin" if es_admin()
                      else "invitado" if solo_mirar() else "operador"),
            "ultima": charla[-1]["r"].get("ficha") if charla else None,
            "volver": st.session_state.get("_asis_volver")}


def llevar_con_el_asistente(nombre_de_la_ficha):
    """Lleva a donde dice una ficha, si quien pregunta tiene esa pantalla. Devuelve el camino,
    o None si no llevó. Es lo único del asistente que cambia algo, y lo que cambia son las
    claves de la navegación, con nombres de las listas de logica/interfaz.py. Va en un
    on_click o un on_submit: Streamlit no deja tocar la clave de un widget ya dibujado."""
    ficha = fichas_del_asistente()["por_nombre"].get(str(nombre_de_la_ficha))
    if not ficha or not ficha["destino"]:
        return None
    destino = ficha["destino"]
    if destino["pagina"] not in _asis_contexto()["visibles"]:
        return None
    camino = camino_del_asistente({k: v for k, v in destino.items() if k != "seccion"})
    if st.session_state.get("pagina_actual") != destino["pagina"]:
        st.session_state["_asis_volver"] = st.session_state.get("pagina_actual")
    ir_a_donde_dice_el_aviso(camino)
    st.session_state["pagina_actual"] = destino["pagina"]
    if str(destino.get("abrir") or "").startswith("exp_"):
        st.session_state[destino["abrir"]] = True       # la sección plegable, ya abierta
    return camino_del_asistente(destino)


def buscar_con_el_asistente(lo_buscado):
    """Lleva al Buscador con eso escrito y buscado: lo mismo que escribirlo ahí (ver
    «_pasar_a_codigo» en pantallas/buscador.py). Al taller, en su portal, se lo escribe en la
    caja de búsqueda del portal. Devuelve dónde quedó buscado (para el cartel), o None."""
    lo_buscado = _asis_para_buscar(lo_buscado)
    contexto = _asis_contexto()
    if not lo_buscado:
        return None
    if contexto["nivel"] == "taller":
        # El portal la pone en su caja antes de dibujarla (ver mostrar_portal_mecanico()).
        st.session_state["_asis_para_el_portal"] = lo_buscado
        return f"«🔍 Buscar repuesto», arriba, con «{lo_buscado}» buscado"
    if PAGINAS[0] not in contexto["visibles"]:
        return None
    st.session_state["_pasar_a_codigo"] = lo_buscado
    st.session_state["pagina_actual"] = PAGINAS[0]
    return f"🔍 Buscador, con «{lo_buscado}» buscado"


def _asis_anotar(pregunta, respuesta):
    charla = st.session_state.setdefault("_asis_charla", [])
    st.session_state["_asis_vueltas"] = st.session_state.get("_asis_vueltas", 0) + 1
    charla.append({"p": limpiar_lo_escrito(pregunta), "r": respuesta})
    del charla[:-ASISTENTE_CHARLA_QUE_QUEDA]


def _asis_se_fue(a_donde):
    """Después de llevar: se minimiza, para que se vea la pantalla, y lo dice un cartel."""
    st.session_state["_asis_abierto"] = False
    st.session_state["_asis_redibujar_todo"] = True
    # El cartel sale en la pasada que dibuja la pantalla nueva: dicho acá, se pierde al redibujar.
    st.session_state["_asis_cartel"] = f"🤖 Te llevé a {a_donde}"


def preguntarle_al_asistente(pregunta=None):
    """Lo que pasa al mandarle algo (on_submit de la caja, o el botón de un ejemplo)."""
    if pregunta is None:
        pregunta = st.session_state.get("asis_pregunta")
    pregunta = limpiar_lo_escrito(pregunta if isinstance(pregunta, str)
                                  else getattr(pregunta, "text", "") or "")
    if not pregunta:
        return
    respuesta = responder_del_asistente(pregunta, _asis_contexto())
    _asis_anotar(pregunta, respuesta)
    if respuesta["ir"]:
        a_donde = llevar_con_el_asistente(respuesta["ir"])
        if a_donde:
            _asis_se_fue(a_donde)
    elif respuesta["buscar"]:
        buscado = buscar_con_el_asistente(respuesta["buscar"])
        if buscado:
            _asis_se_fue(buscado)


def _asis_toco(que, cual):
    """El botón de una respuesta: ir, ver otra ficha, buscar o preguntar un ejemplo."""
    if que == "ir":
        a_donde = llevar_con_el_asistente(cual)
        if a_donde:
            _asis_se_fue(a_donde)
    elif que == "buscar":
        buscado = buscar_con_el_asistente(cual)
        if buscado:
            _asis_se_fue(buscado)
    elif que == "ver":
        contexto = _asis_contexto()
        ficha = fichas_del_asistente()["por_nombre"].get(str(cual))
        if ficha and _asis_se_puede(ficha, contexto):
            _asis_anotar(ficha["titulo"], _asis_respuesta_de(ficha, contexto))
    elif que == "preguntar":
        preguntarle_al_asistente(str(cual))


def _asis_abrir_o_minimizar(abierto):
    st.session_state["_asis_abierto"] = abierto


def _asis_borrar_la_charla():
    st.session_state.pop("_asis_charla", None)


@st.fragment
def mostrar_el_asistente():
    """La burbuja y, abierta, el panel. Se llama una vez por pasada, desde app.py."""
    if st.session_state.pop("_asis_redibujar_todo", False):
        st.rerun()              # llevó a otra pantalla: se redibuja todo, no solo la burbuja
    cartel = st.session_state.pop("_asis_cartel", None)
    if cartel:
        st.toast(cartel)
    if not st.session_state.get("_asis_abierto"):
        with st.container(key="asistente_minimizado"):
            st.button("🤖", key="asis_abrir", on_click=_asis_abrir_o_minimizar, args=(True,),
                      help="Asistente (F1): preguntale cómo se hace algo, o pedile que te lleve.")
        return
    with st.container(key="asistente_abierto"):
        # En un renglón también en el celular: con st.columns el «➖» pasaba abajo, a lo ancho.
        with st.container(key="asis_cabecera", horizontal=True, wrap=False,
                          horizontal_alignment="distribute", vertical_alignment="center"):
            st.markdown("**🤖 Asistente**")
            st.button("➖", key="asis_minimizar", on_click=_asis_abrir_o_minimizar,
                      args=(False,), help="Minimizar (F1). La charla queda para cuando vuelvas.")
        st.chat_input("¿Qué querés hacer, o a dónde vamos?", key="asis_pregunta",
                      max_chars=ASISTENTE_LARGO_MAXIMO, on_submit=preguntarle_al_asistente)
        charla = st.session_state.get("_asis_charla") or []
        if not charla:
            st.markdown("Preguntame cómo se hace algo, o pedime que te lleve. Por ejemplo:")
            for n, ejemplo in enumerate(ejemplos_del_asistente(_asis_contexto())):
                st.button(ejemplo, key=f"asis_ejemplo_{n}", on_click=_asis_toco,
                          args=("preguntar", ejemplo), width="stretch")
            return
        ultima = charla[-1]
        st.markdown(f"<div class='asis-pregunta'>{texto_para_html(ultima['p'])}</div>",
                    unsafe_allow_html=True)
        st.markdown(ultima["r"]["texto"])
        for n, (rotulo, que, cual) in enumerate(ultima["r"]["botones"]):
            st.button(rotulo, key=f"asis_boton_{st.session_state.get('_asis_vueltas', 0)}_{n}", on_click=_asis_toco,
                      args=(que, cual), width="stretch",
                      type="primary" if que in ("ir", "buscar") and n == 0 else "secondary")
        if len(charla) > 1:
            anteriores = st.expander("Lo anterior", key="asis_lo_anterior")
            with anteriores:
                for vuelta in reversed(charla[:-1]):
                    st.markdown(f"<div class='asis-pregunta'>{texto_para_html(vuelta['p'])}"
                                "</div>", unsafe_allow_html=True)
                    st.markdown(vuelta["r"]["texto"])
                st.button("🧹 Borrar la charla", key="asis_borrar",
                          on_click=_asis_borrar_la_charla)

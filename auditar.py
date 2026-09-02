"""Auditoría estática de app.py. Busca los errores que Streamlit y SQLite solo muestran
en ejecución, cuando ya es tarde."""
import ast
import re
import sys
from collections import defaultdict, Counter

ARCHIVO = sys.argv[1] if len(sys.argv) > 1 else "app.py"
SRC = open(ARCHIVO, encoding="utf-8").read()
ARBOL = ast.parse(SRC)
LINEAS = SRC.splitlines()
problemas = []


def reportar(nivel, linea, texto):
    problemas.append((nivel, linea, texto))


def literal(nodo):
    try:
        return ast.literal_eval(nodo)
    except Exception:
        return None


def es_st(nodo, nombres):
    return (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
            and nodo.func.attr in nombres)


WIDGETS = {"text_input", "number_input", "selectbox", "multiselect", "radio", "checkbox",
           "slider", "select_slider", "text_area", "file_uploader", "button", "download_button",
           "date_input", "time_input", "color_picker", "toggle", "form_submit_button",
           "camera_input", "data_editor", "pills", "segmented_control"}

# ============ 1. Claves de widget duplicadas ============
# Streamlit corta la app entera con "multiple widgets with the same key".
# Se le asigna a cada widget la lista de ramas if/else que lo contienen. Dos widgets con la
# misma clave en ramas EXCLUYENTES del mismo if nunca coexisten, así que no son un problema —
# sin esto la auditoría marcaba como error un if/else legítimo.
rama_de = {}


def _recorrer(nodo, camino):
    """Anota, para cada widget, en qué ramas de if/else quedó metido.

    Va de afuera hacia adentro, y cada nivel más profundo pisa al anterior: lo que importa es
    la rama MÁS INTERNA. La versión anterior usaba setdefault, así que ganaba la marca de
    afuera (vacía) y todos los widgets parecían estar en la misma rama."""
    if es_st(nodo, WIDGETS):
        rama_de[id(nodo)] = camino
    if isinstance(nodo, ast.If):
        for hijo in nodo.body:
            _recorrer(hijo, camino + [(id(nodo), "T")])
        for hijo in nodo.orelse:
            _recorrer(hijo, camino + [(id(nodo), "F")])
        for hijo in ast.iter_child_nodes(nodo.test):
            _recorrer(hijo, camino)
        return
    for hijo in ast.iter_child_nodes(nodo):
        _recorrer(hijo, camino)


_recorrer(ARBOL, [])


def _excluyentes(a, b):
    """True si estos dos widgets nunca pueden coexistir: están en ramas opuestas del mismo if."""
    da, db = dict(rama_de.get(id(a), [])), dict(rama_de.get(id(b), []))
    return any(k in db and db[k] != v for k, v in da.items())


claves = defaultdict(list)
nodos_clave = defaultdict(list)
for n in ast.walk(ARBOL):
    if es_st(n, WIDGETS):
        for kw in n.keywords:
            if kw.arg == "key":
                v = literal(kw.value)
                if isinstance(v, str):
                    claves[v].append((n.lineno, n.func.attr))
                    nodos_clave[v].append(n)
for clave, usos in claves.items():
    if len(usos) < 2:
        continue
    nodos = nodos_clave[clave]
    if all(_excluyentes(a, b) for i, a in enumerate(nodos) for b in nodos[i+1:]):
        continue    # están en ramas que nunca corren juntas
    detalle = ", ".join(f"L{l} ({w})" for l, w in usos)
    reportar("ERROR", usos[0][0], f"clave de widget repetida '{clave}': {detalle}")

# ============ 2. Widgets prohibidos dentro de st.form ============
# Dentro de un form solo vale form_submit_button; un st.button adentro tira excepción.
class BuscarForms(ast.NodeVisitor):
    def visit_With(self, nodo):
        es_form = any(es_st(item.context_expr, {"form"}) for item in nodo.items)
        if es_form:
            for hijo in ast.walk(nodo):
                if es_st(hijo, {"button"}):
                    reportar("ERROR", hijo.lineno, "st.button dentro de un st.form "
                             "(solo se permite form_submit_button)")

                if es_st(hijo, {"file_uploader"}) and any(
                        k.arg == "on_change" for k in hijo.keywords):
                    reportar("AVISO", hijo.lineno, "file_uploader con on_change dentro de un form")
        self.generic_visit(nodo)


BuscarForms().visit(ARBOL)

# ============ 3. value= que no está en options= ============
for n in ast.walk(ARBOL):
    if es_st(n, {"select_slider", "selectbox", "radio", "multiselect"}):
        kw = {k.arg: k.value for k in n.keywords if k.arg}
        opts = literal(kw["options"]) if "options" in kw else (
            literal(n.args[1]) if len(n.args) > 1 else None)
        if "value" in kw and opts is not None:
            v = literal(kw["value"])
            if v is not None and v not in opts:
                reportar("ERROR", n.lineno, f"st.{n.func.attr} value={v!r} no está en options")
            elif v is None:
                reportar("AVISO", n.lineno, f"st.{n.func.attr} con value= calculado y options fijas")
        if "value" in kw and "key" in kw:
            reportar("AVISO", n.lineno, f"st.{n.func.attr} usa value= y key= a la vez")
        if "index" in kw and opts is not None:
            i = literal(kw["index"])
            if isinstance(i, int) and not (-len(opts) <= i < len(opts)):
                reportar("ERROR", n.lineno, f"st.{n.func.attr} index={i} fuera de options")

# ============ 4. number_input con value fuera de min/max ============
for n in ast.walk(ARBOL):
    if es_st(n, {"number_input", "slider"}):
        kw = {k.arg: literal(k.value) for k in n.keywords if k.arg}
        mn, mx, v = kw.get("min_value"), kw.get("max_value"), kw.get("value")
        if isinstance(v, (int, float)) and isinstance(mn, (int, float)) and v < mn:
            reportar("ERROR", n.lineno, f"st.{n.func.attr} value={v} < min_value={mn}")
        if isinstance(v, (int, float)) and isinstance(mx, (int, float)) and v > mx:
            reportar("ERROR", n.lineno, f"st.{n.func.attr} value={v} > max_value={mx}")

# ============ 5. Variables asignadas solo en una rama y usadas afuera ============
class Ambito(ast.NodeVisitor):
    def __init__(self):
        self.asig = defaultdict(list); self.usos = defaultdict(list); self.prof = 0
    def visit_FunctionDef(self, n): pass
    visit_AsyncFunctionDef = visit_FunctionDef
    def _rama(self, n):
        self.prof += 1; self.generic_visit(n); self.prof -= 1
    visit_If = _rama; visit_Try = _rama; visit_For = _rama; visit_While = _rama
    def visit_Name(self, n):
        destino = self.asig if isinstance(n.ctx, ast.Store) else self.usos
        destino[n.id].append((n.lineno, self.prof))


amb = Ambito(); amb.visit(ARBOL)

# Nombres que se asignan en las DOS ramas de un mismo if/else: siempre quedan definidos, no hay
# riesgo. Sin esto la auditoría marcaba media docena de if/else perfectamente sanos.
cubiertos = set()
for n in ast.walk(ARBOL):
    if isinstance(n, ast.If) and n.orelse:
        def _asignados(cuerpo):
            r = set()
            for h in cuerpo:
                for x in ast.walk(h):
                    if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store):
                        r.add(x.id)
            return r
        cubiertos |= _asignados(n.body) & _asignados(n.orelse)

# Nombres ligados por 'except X as e' o por una comprensión: viven en otro ámbito, no aplica
ligados_aparte = set()
for n in ast.walk(ARBOL):
    if isinstance(n, ast.ExceptHandler) and n.name:
        ligados_aparte.add(n.name)
    if isinstance(n, ast.comprehension):
        for x in ast.walk(n.target):
            if isinstance(x, ast.Name):
                ligados_aparte.add(x.id)

for nombre, asigs in amb.asig.items():
    if nombre.startswith("_") or nombre.isupper():
        continue
    if nombre in cubiertos or nombre in ligados_aparte:
        continue
    pa = min(p for _, p in asigs); la = min(l for l, _ in asigs)
    for lu, pu in amb.usos.get(nombre, []):
        if pu < pa and lu > la:
            reportar("REVISAR", lu, f"'{nombre}' se asigna solo dentro de una rama (L{la}) "
                                     f"y se usa afuera")
            break

# ============ 6. Variables que pisan funciones del módulo ============
funcs_modulo = {n.name for n in ARBOL.body if isinstance(n, ast.FunctionDef)}
class Pisadas(ast.NodeVisitor):
    def visit_FunctionDef(self, n): pass
    def visit_Name(self, n):
        if isinstance(n.ctx, ast.Store) and n.id in funcs_modulo:
            reportar("ERROR", n.lineno, f"la variable '{n.id}' pisa la función global del mismo nombre")


Pisadas().visit(ARBOL)

# ============ 7. Columnas SQL que no existen ============
# Un INSERT o un UPDATE contra una columna que no está en el CREATE TABLE no falla al escribir
# el código ni al abrir la app: revienta con "no such column" recién cuando alguien toca ese
# botón, que puede ser meses después. Es el mismo tipo de bug que el de los valores de texto:
# no da síntoma hasta que da el peor síntoma.


def _partir_columnas(cuerpo):
    """Corta la definición de la tabla por las comas de nivel 0.

    No sirve cortar por líneas: hay tablas con varias columnas en el mismo renglón
    (`idx_prov INTEGER, idx_oem INTEGER`) y así se perdían todas menos la primera, lo que hacía
    que después el chequeo marcara como inexistentes columnas que existían. Tampoco sirve cortar
    por cualquier coma: `DEFAULT (datetime('now'))` y `PRIMARY KEY (a, b)` traen las suyas."""
    piezas, prof, actual = [], 0, []
    for ch in cuerpo:
        if ch == "(":
            prof += 1
        elif ch == ")":
            prof -= 1
        if ch == "," and prof == 0:
            piezas.append("".join(actual))
            actual = []
        else:
            actual.append(ch)
    piezas.append("".join(actual))
    return piezas


columnas = defaultdict(set)
for m in re.finditer(r'CREATE TABLE(?:\s+IF NOT EXISTS)?\s+(\w+)\s*\((.*?)\)\s*"""', SRC, re.S):
    tabla = m.group(1)
    for t in _partir_columnas(m.group(2)):
        t = t.strip()
        if not t or t.upper().startswith(("PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "CONSTRAINT")):
            continue
        col = t.split()[0].strip('"')
        if col.isidentifier():
            columnas[tabla].add(col)
for m in re.finditer(r'ALTER TABLE (\w+) ADD COLUMN (\w+)', SRC):
    columnas[m.group(1)].add(m.group(2))

# El SQL se busca SOLO adentro de literales de texto. Barriendo el archivo entero, el `.*?` del
# UPDATE ... SET se comía el código Python que venía después del string y se inventaba columnas
# ("productos.limite", "productos.progreso") que en realidad eran variables locales.
_SQL = [(n.value, n.lineno) for n in ast.walk(ARBOL)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and len(n.value) > 10]

for texto, linea in _SQL:
    for m in re.finditer(r'INSERT\s+(?:OR\s+\w+\s+)?INTO\s+(\w+)\s*\(([^)]*)\)', texto, re.I | re.S):
        tabla = m.group(1)
        if tabla not in columnas:
            continue
        for col in m.group(2).split(","):
            col = col.strip().strip('"')
            if col and col.isidentifier() and col not in columnas[tabla]:
                reportar("ERROR", linea, f"INSERT INTO {tabla}: la columna '{col}' no existe")
    for m in re.finditer(r'UPDATE\s+(\w+)\s+SET\s+(.*?)(?:\bWHERE\b|$)', texto, re.I | re.S):
        tabla = m.group(1)
        if tabla not in columnas:
            continue
        for asig in re.finditer(r'([A-Za-z_]\w*)\s*=', m.group(2)):
            if asig.group(1) not in columnas[tabla]:
                reportar("ERROR", linea,
                         f"UPDATE {tabla}: la columna '{asig.group(1)}' no existe")

# ============ 8. except silenciosos en funciones que escriben ============
for n in ast.walk(ARBOL):
    if isinstance(n, ast.ExceptHandler):
        if n.type is None:
            reportar("AVISO", n.lineno, "except desnudo (atrapa hasta Ctrl-C)")

# ============ 8b. Mensajes que el rerun borra antes de que se lean ============
MSG = {"success", "info", "warning", "error"}
def _expr_st(nodo, attrs):
    return (isinstance(nodo, ast.Expr) and isinstance(nodo.value, ast.Call)
            and isinstance(nodo.value.func, ast.Attribute)
            and nodo.value.func.attr in attrs
            and isinstance(nodo.value.func.value, ast.Name)
            and nodo.value.func.value.id == "st")

for n in ast.walk(ARBOL):
    for campo in ("body", "orelse", "finalbody"):
        cuerpo = getattr(n, campo, None)
        if isinstance(cuerpo, list):
            for a, b in zip(cuerpo, cuerpo[1:]):
                if _expr_st(a, MSG) and _expr_st(b, {"rerun"}):
                    reportar("ERROR", a.lineno,
                             f"st.{a.value.func.attr}() justo antes de st.rerun(): el refresco "
                             "borra el mensaje. Usar avisar()")

# ============ 8c. Valores de texto que tienen que coincidir entre escritura y lectura ============
# El caso que motivó esto: deshacer_importacion guardaba la decisión como "rechazado" y
# pares_rechazados() busca "rechazada". Se guardaba bien, no fallaba nada, y simplemente no
# filtraba: el bug más caro de encontrar, porque no da ningún síntoma.
VALORES_PAREADOS = {
    "decision": {"ok", "rechazada"},
    "estado": {"ok", "sin_detalle", "error", "solo_forma", "pendiente", "resuelto",
               # de las reservas de stock
               "activa", "vencida", "vendida", "cancelada"},
    "foto_busqueda_estado": {"sin_foto", "error"},
    "origen": {"lista_proveedor", "manual", "subida", "url", "ficha", "link", "migrada", "deducida"},
}
for campo, permitidos in VALORES_PAREADOS.items():
    # se buscan literales comparados o asignados a ese campo en SQL
    # El (?<![a-z_]) evita que "estado" enganche también a "foto_busqueda_estado", que es otro
    # campo con sus propios valores: sin eso la auditoría inventaba errores que no existían.
    for m in re.finditer(rf"(?<![a-z_]){campo}\s*=\s*'([a-z_]+)'", SRC):
        if m.group(1) not in permitidos:
            linea = SRC[:m.start()].count("\n") + 1
            reportar("ERROR", linea,
                     f"'{m.group(1)}' no es un valor válido de {campo} "
                     f"(esperados: {', '.join(sorted(permitidos))})")

# Y además: textos sueltos que se parecen MUCHO a un valor válido sin serlo. El bug real fue
# marcar_revision(pares, "rechazado") cuando el valor bueno es "rechazada" — una sola letra.
# No está en un SQL, así que el chequeo de arriba no lo ve: hay que mirar los literales.
TODOS_VALIDOS = {v for vals in VALORES_PAREADOS.values() for v in vals}


def _dist(a, b, tope=2):
    if abs(len(a) - len(b)) > tope:
        return tope + 1
    ant = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        act = [i]
        for j, cb in enumerate(b, 1):
            act.append(min(ant[j] + 1, act[j - 1] + 1, ant[j - 1] + (ca != cb)))
        if min(act) > tope:
            return tope + 1
        ant = act
    return ant[-1]


# Solo se miran los textos que se PASAN a una función o se comparan, no las claves de un
# diccionario ni los nombres de columna: ahí "pendientes" o "migradas" son plurales legítimos
# y marcarlos llenaba la auditoría de ruido.
literales_en_riesgo = []
for nodo in ast.walk(ARBOL):
    if isinstance(nodo, ast.Call):
        for arg in list(nodo.args) + [k.value for k in nodo.keywords]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                literales_en_riesgo.append(arg)
    if isinstance(nodo, ast.Compare):
        for lado in [nodo.left] + list(nodo.comparators):
            if isinstance(lado, ast.Constant) and isinstance(lado.value, str):
                literales_en_riesgo.append(lado)

for nodo in literales_en_riesgo:
    txt = nodo.value
    if txt in TODOS_VALIDOS or not txt or " " in txt or not txt.islower() or len(txt) < 4:
        continue
    for bueno in TODOS_VALIDOS:
        if _dist(txt, bueno) == 1:
            reportar("ERROR", nodo.lineno,
                     f'"{txt}" se parece a "{bueno}" por una sola letra — '
                     "¿es el valor que espera el resto del código?")
            break

# ============ 8d. Paredes de texto en la interfaz ============
# En el celular una explicación de 300 caracteres empuja los botones fuera de la pantalla y hay
# que scrollear para llegar a lo que uno vino a hacer. Para eso está explicar(): resumen corto
# a la vista y el detalle a un toque. Este chequeo evita que vuelvan a crecer.
for nodo in ast.walk(ARBOL):
    # Solo captions e info: son texto explicativo, y ahí la pared molesta todos los días.
    # Los warning y error avisan de un problema puntual y sí necesitan explicar qué pasó y qué
    # hacer — marcarlos empujaría a recortar justo el mensaje que hace falta leer entero.
    if not (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
            and nodo.func.attr in ("caption", "info")):
        continue
    if not nodo.args:
        continue
    try:
        texto = ast.literal_eval(nodo.args[0])
    except Exception:
        continue        # f-strings: llevan datos, no son texto fijo
    if isinstance(texto, str) and len(texto) > 300:
        reportar("AVISO", nodo.lineno,
                 f"st.{nodo.func.attr} con {len(texto)} caracteres fijos — conviene explicar() "
                 "(resumen corto + detalle desplegable)")

# El resumen de explicar() tiene que entrar en una línea del celular
for nodo in ast.walk(ARBOL):
    if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name) and nodo.func.id == "explicar":
        if len(nodo.args) < 2:
            reportar("ERROR", nodo.lineno, "explicar() necesita resumen y detalle")
            continue
        try:
            resumen = ast.literal_eval(nodo.args[0])
        except Exception:
            continue
        if isinstance(resumen, str) and len(resumen) > 170:
            reportar("AVISO", nodo.lineno,
                     f"el resumen de explicar() tiene {len(resumen)} caracteres; "
                     "va lo corto arriba y lo largo adentro")

# ============ 8e. Contenedores anidados ============
# Un expander adentro de otro deja dos cajas anidadas: en el celular hay que tocar dos veces
# para leer tres renglones. Las versiones viejas de Streamlit directamente lo rechazaban con una
# excepción que cortaba el renderizado; las de ahora (probado con la 1.63) lo dejan pasar, así
# que esto va como AVISO y no como ERROR — marcarlo de rojo sería mentir sobre lo que hace.
# Igual conviene verlo: los dos expanders pueden estar a 200 líneas de distancia y así, leyendo,
# no hay forma de darse cuenta.
def _es_contenedor(item, nombre):
    return (isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Attribute)
            and item.context_expr.func.attr == nombre)


def _funciones_que_abren(nombre):
    """Funciones del módulo que abren ese contenedor, contando las que lo abren a través de otra.

    Sin esto el chequeo solo veía los `with st.expander` escritos a la vista, y se le escapaba el
    caso que más pasa en este archivo: explicar() abre un expander adentro, así que llamarla
    dentro de otro expander es exactamente el mismo error prohibido — pero leyendo el código no
    se parece en nada, porque en la línea dice `explicar(...)` y no `st.expander(...)`."""
    mods = {n.name: n for n in ARBOL.body if isinstance(n, ast.FunctionDef)}

    def _abre_sin_red(fn):
        """Abrirlo adentro de un try/except no cuenta: esa función ya sabe caerse con gracia.

        Es lo que hace explicar(): intenta el expander y, si no puede porque ya está adentro de
        otro, baja a un popover. Marcarla igual sería marcar código que anda —y una auditoría
        que marca lo que anda se deja de mirar."""
        protegidos = set()
        for x in ast.walk(fn):
            if isinstance(x, ast.Try):
                for h in x.body:
                    for y in ast.walk(h):
                        protegidos.add(id(y))
        return any(es_st(x, {nombre}) and id(x) not in protegidos for x in ast.walk(fn))

    abren = {nom for nom, fn in mods.items() if _abre_sin_red(fn)}
    # Repetir hasta que no cambie: si A llama a B y B abre el contenedor, A también lo abre.
    while True:
        nuevas = {nom for nom, fn in mods.items() if nom not in abren
                  and any(isinstance(x, ast.Call) and isinstance(x.func, ast.Name)
                          and x.func.id in abren for x in ast.walk(fn))}
        if not nuevas:
            return abren
        abren |= nuevas


class _BuscaAnidados(ast.NodeVisitor):
    def __init__(self, nombre):
        self.nombre = nombre
        self.pila = []
        self.abren = _funciones_que_abren(nombre)

    def _avisar(self, linea, que):
        reportar("AVISO", linea,
                 f"{que} dentro de un st.{self.nombre} (el de afuera está en L{self.pila[-1]}) "
                 f"— quedan dos cajas anidadas y en el celular molesta")

    def visit_FunctionDef(self, nodo):
        # El cuerpo de una función arranca sin contexto: que se la llame desde adentro de un
        # expander se marca en la llamada, no acá. Si no, cualquier función con un expander
        # propio quedaba marcada por cada lugar del que se la llama.
        guardado, self.pila = self.pila, []
        self.generic_visit(nodo)
        self.pila = guardado

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_With(self, nodo):
        hay = any(_es_contenedor(i, self.nombre) for i in nodo.items)
        if hay and self.pila:
            self._avisar(nodo.lineno, f"st.{self.nombre}")
        if hay:
            self.pila.append(nodo.lineno)
        self.generic_visit(nodo)
        if hay:
            self.pila.pop()

    def visit_Call(self, nodo):
        if isinstance(nodo.func, ast.Name) and self.pila:
            if nodo.func.id in self.abren:
                self._avisar(nodo.lineno, f"{nodo.func.id}(), que abre un st.{self.nombre},")
            # explicar() sabe acomodarse —con en_expander=True manda el detalle a un popover, que
            # se abre encima y no agrega otro nivel— pero hay que avisarle: sola no se entera de
            # dónde la llamaron.
            elif (self.nombre == "expander" and nodo.func.id == "explicar"
                  and not any(k.arg == "en_expander" for k in nodo.keywords)):
                reportar("AVISO", nodo.lineno,
                         f"explicar() adentro del st.expander de L{self.pila[-1]}: pasale "
                         "en_expander=True y el detalle va a un popover en vez de anidar "
                         "otra caja")
        self.generic_visit(nodo)


_BuscaAnidados("expander").visit(ARBOL)

# ============ 8f. session_state escrito después de dibujar su widget ============
# Streamlit no deja tocar st.session_state["x"] una vez que ya se dibujó el widget con key="x":
# tira StreamlitAPIException y se corta la pantalla. En el archivo ya hay dos comentarios
# avisando de esto —"precargar ANTES de crear el widget"— justamente porque ya pasó. El patrón
# correcto es guardar el valor en OTRA clave y volcarlo al principio de la vuelta siguiente.
_keys_widget = {}
for n in ast.walk(ARBOL):
    if es_st(n, WIDGETS):
        for kw in n.keywords:
            if kw.arg == "key" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                _keys_widget.setdefault(kw.value.value, n.lineno)


def _clave_session_state(nodo):
    """Devuelve la clave de un st.session_state["algo"] literal, o None."""
    if (isinstance(nodo, ast.Subscript) and isinstance(nodo.value, ast.Attribute)
            and nodo.value.attr == "session_state"
            and isinstance(nodo.slice, ast.Constant) and isinstance(nodo.slice.value, str)):
        return nodo.slice.value
    return None


for n in ast.walk(ARBOL):
    if isinstance(n, (ast.Assign, ast.AugAssign)):
        for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
            k = _clave_session_state(t)
            if k and k in _keys_widget and n.lineno > _keys_widget[k]:
                reportar("ERROR", n.lineno,
                         f"st.session_state[{k!r}] se escribe después de dibujar su widget "
                         f"(L{_keys_widget[k]}) — Streamlit lo prohíbe. Guardarlo en otra clave "
                         "y volcarlo antes del widget, como se hace con 'sugerencia_busqueda'")

# ============ 8g. avisar() sin refresco que lo muestre ============
# avisar() GUARDA el mensaje para el refresco siguiente; lo muestra mostrar_avisos_pendientes(),
# que corre arriba de todo. Si en esa rama no hay st.rerun(), el mensaje no aparece ahora: queda
# esperando a que la persona toque cualquier otra cosa, y para entonces ya no significa nada.
# En una rama donde no se va a refrescar, el mensaje va con st.success() directo.
# Dónde vive cada sentencia: en qué lista está, en qué posición y de quién es esa lista.
# Hace falta para poder mirar hacia AFUERA: el st.rerun() que salva a un avisar() casi nunca es
# su hermano directo —el avisar suele estar adentro de un `if hubo_algo:` y el rerun, después
# del if. Mirando solo la lista propia, esos quedaban marcados sin estar mal.
_ubicacion = {}
for n in ast.walk(ARBOL):
    for campo in ("body", "orelse", "finalbody"):
        cuerpo = getattr(n, campo, None)
        if isinstance(cuerpo, list):
            for i, sent in enumerate(cuerpo):
                _ubicacion[id(sent)] = (cuerpo, i, n)


def _hay_rerun_despues(sent):
    """True si algún st.rerun() puede correr después de esta sentencia, en su bloque o afuera."""
    actual = sent
    while id(actual) in _ubicacion:
        cuerpo, i, dueño = _ubicacion[id(actual)]
        if any(es_st(x, {"rerun", "experimental_rerun"})
               for s in cuerpo[i:] for x in ast.walk(s)):
            return True
        if isinstance(dueño, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return False    # más afuera ya es otra corrida, no esta
        actual = dueño
    return False


for n in ast.walk(ARBOL):
    if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Name) and n.value.func.id == "avisar"):
        continue
    if not _hay_rerun_despues(n):
        reportar("ERROR", n.lineno,
                 "avisar() sin ningún st.rerun() después: el mensaje queda guardado para el "
                 "refresco siguiente y no se muestra. Acá va st.success()/st.warning() directo")

# ============ 8h. Bloques copiados a otra rama, con los nombres de la rama vieja ============
# El caso que motivó esto: el carrito se copió de la búsqueda por código a la búsqueda por
# descripción y quedó usando 'res' y 'clean', que en esa rama no existen (ahí se llaman
# res_texto y clean_txt). Compila perfecto, y recién al entrar a "Descripción" tira NameError y
# la sección entera queda en blanco.
#
# El intento anterior de agarrarlo fue un chequeo de ámbitos y daba falsos positivos, porque
# decidir qué nombre es visible dónde en un archivo con este anidamiento no se puede sin un
# analizador completo. La vuelta que sí funciona es mucho más chica: no preguntarse si el nombre
# está definido, sino si TODAS sus asignaciones están en ramas que NUNCA corren junto con el
# uso. Si el único lugar donde se asigna es la rama 'if' y se lo usa en el 'else', no hay caso
# posible en que llegue definido — no es una sospecha, es seguro. Sobre este archivo no marca
# nada de lo que está bien, y sobre la versión con el bug marcaba las dos líneas exactas.
_rama_nombre = {}


def _recorrer_nombres(nodo, camino):
    """Igual que el recorrido de las claves de widget, pero anotando TODOS los nombres."""
    if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        return      # adentro de una función manda su propio ámbito, no este
    if isinstance(nodo, ast.Name):
        _rama_nombre[id(nodo)] = camino
    if isinstance(nodo, ast.If):
        for hijo in ast.iter_child_nodes(nodo.test):
            _recorrer_nombres(hijo, camino)
        for hijo in nodo.body:
            _recorrer_nombres(hijo, camino + [(id(nodo), "T")])
        for hijo in nodo.orelse:
            _recorrer_nombres(hijo, camino + [(id(nodo), "F")])
        return
    for hijo in ast.iter_child_nodes(nodo):
        _recorrer_nombres(hijo, camino)


_recorrer_nombres(ARBOL, [])
_asignados_en, _usados_en = defaultdict(list), defaultdict(list)
for n in ast.walk(ARBOL):
    if isinstance(n, ast.Name) and id(n) in _rama_nombre:
        (_asignados_en if isinstance(n.ctx, ast.Store) else _usados_en)[n.id].append(n)


def _ramas_opuestas(a, b):
    """True si estos dos nodos están en ramas opuestas del mismo if: nunca corren los dos."""
    da, db = dict(_rama_nombre[id(a)]), dict(_rama_nombre[id(b)])
    return any(k in db and db[k] != v for k, v in da.items())


for nombre, usos in _usados_en.items():
    asignaciones = _asignados_en.get(nombre)
    if not asignaciones or nombre in ligados_aparte:
        continue
    for uso in usos:
        if all(_ramas_opuestas(uso, a) for a in asignaciones):
            reportar("ERROR", uso.lineno,
                     f"\'{nombre}\' se usa acá, pero todas sus asignaciones están en ramas que "
                     "nunca corren con esta: NameError al entrar a esta sección. ¿Es un bloque "
                     "copiado de otra rama, donde la variable se llama distinto?")
            break

# NOTA sobre lo que esta auditoría todavía NO puede detectar
# El mismo bloque copiado, pero donde el nombre viejo SÍ existe también en la rama nueva con
# otro significado: ahí no hay NameError, hay datos de otra búsqueda mostrados como si fueran
# de esta. No falla, no avisa, y está mal. Eso hay que mirarlo a mano al copiar un bloque.

# ============ 9. Argumentos por defecto mutables ============
for n in ast.walk(ARBOL):
    if isinstance(n, ast.FunctionDef):
        for d in n.args.defaults + [x for x in n.args.kw_defaults if x]:
            if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                reportar("AVISO", n.lineno, f"{n.name}() tiene un default mutable")

# ============ 10. Firmas: llamadas con argumentos que no existen ============
# Solo las funciones del MÓDULO. Las anidadas se llaman dentro de su propio ámbito y pueden
# repetir nombre con otra firma: comparar contra ellas daba errores que no existían.
firmas = {n.name: n for n in ARBOL.body if isinstance(n, ast.FunctionDef)}
anidadas = {n.name for n in ast.walk(ARBOL)
            if isinstance(n, ast.FunctionDef) and n.name not in firmas}
for n in ast.walk(ARBOL):
    if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id in firmas and n.func.id not in anidadas):
        f = firmas[n.func.id]
        if f.args.kwarg:
            continue
        validos = {a.arg for a in f.args.args} | {a.arg for a in f.args.kwonlyargs}
        for kw in n.keywords:
            if kw.arg and kw.arg not in validos:
                reportar("ERROR", n.lineno, f"{n.func.id}({kw.arg}=...) no existe en la firma")
        if len(n.args) > len(f.args.args) and not f.args.vararg:
            reportar("REVISAR", n.lineno,
                     f"{n.func.id}() recibe {len(n.args)} posicionales, la firma acepta {len(f.args.args)}")

# ============ 11. Nombres usados y nunca definidos ============
definidas = {n.name for n in ast.walk(ARBOL) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
conocidas = set(definidas) | set(dir(__builtins__))
for n in ast.walk(ARBOL):
    if isinstance(n, (ast.Assign, ast.AugAssign, ast.For)):
        objetivos = n.targets if isinstance(n, ast.Assign) else [getattr(n, "target", None)]
        for t in objetivos:
            if t is None: continue
            for x in ast.walk(t):
                if isinstance(x, ast.Name): conocidas.add(x.id)
    if isinstance(n, ast.comprehension):
        for x in ast.walk(n.target):
            if isinstance(x, ast.Name): conocidas.add(x.id)
    if isinstance(n, (ast.Import, ast.ImportFrom)):
        for a in n.names: conocidas.add((a.asname or a.name).split(".")[0])
    if isinstance(n, ast.FunctionDef):
        for a in n.args.args + n.args.kwonlyargs: conocidas.add(a.arg)
        if n.args.vararg: conocidas.add(n.args.vararg.arg)
        if n.args.kwarg: conocidas.add(n.args.kwarg.arg)
    if isinstance(n, ast.ExceptHandler) and n.name: conocidas.add(n.name)
    if isinstance(n, ast.withitem) and n.optional_vars:
        for x in ast.walk(n.optional_vars):
            if isinstance(x, ast.Name): conocidas.add(x.id)
usados = {n.id for n in ast.walk(ARBOL) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
for falta in sorted(usados - conocidas):
    reportar("ERROR", 0, f"nombre usado y nunca definido: '{falta}'")

# ============ 12. Funciones definidas y nunca usadas ============
llamados = {n.func.id for n in ast.walk(ARBOL) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
referidos = {n.id for n in ast.walk(ARBOL) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
for nombre in sorted(funcs_modulo - llamados - referidos):
    if not nombre.startswith("_") and nombre in firmas:
        reportar("AVISO", firmas[nombre].lineno, f"función '{nombre}' definida y nunca usada")

# ============ Resultado ============
orden = {"ERROR": 0, "REVISAR": 1, "AVISO": 2}
problemas.sort(key=lambda x: (orden[x[0]], x[1]))
cuenta = Counter(p[0] for p in problemas)
print(f"{ARCHIVO} — {len(LINEAS)} líneas")
print(f"ERROR: {cuenta['ERROR']}   REVISAR: {cuenta['REVISAR']}   AVISO: {cuenta['AVISO']}\n")
for nivel, linea, texto in problemas:
    ubic = f"L{linea}" if linea else "  "
    print(f"[{nivel:7}] {ubic:>7}  {texto}")
    if linea and nivel == "ERROR":
        print(f"                    {LINEAS[linea - 1].strip()[:95]}")
sys.exit(1 if cuenta["ERROR"] else 0)

"""Auditoría estática de app.py. Busca los errores que Streamlit y SQLite solo muestran
en ejecución, cuando ya es tarde."""
import ast
import copy
import re
import sqlite3
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


_PADRES = {}


def _ancestros(nodo):
    """Los nodos que contienen a este, de adentro hacia afuera."""
    if not _PADRES:
        for n in ast.walk(ARBOL):
            for hijo in ast.iter_child_nodes(n):
                _PADRES[id(hijo)] = n
    actual = nodo
    while id(actual) in _PADRES:
        actual = _PADRES[id(actual)]
        yield actual


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
# Lo mismo vale para try/except: si el nombre se asigna en el try Y en el except, salga como
# salga queda definido. Sin esto, el patrón normal de "probar la consulta y si falla dejar el
# diccionario vacío" quedaba marcado como riesgo, que es justamente lo contrario.
for n in ast.walk(ARBOL):
    if isinstance(n, ast.Try) and n.handlers:
        def _asignados_try(cuerpo):
            r = set()
            for h in cuerpo:
                for x in ast.walk(h):
                    if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store):
                        r.add(x.id)
            return r
        en_try = _asignados_try(n.body)
        for manejador in n.handlers:
            en_try &= _asignados_try(manejador.body)
        cubiertos |= en_try

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

# ============ 7b. Índices creados antes que su tabla ============
# CREATE INDEX ... ON tabla revienta si la tabla todavía no existe. Con una base ya creada no se
# nota —la tabla viene de una versión anterior—, así que el error aparece SOLO en una instalación
# nueva: la app no abre y dice "no such table". Es de los peores porque no lo ve nadie que ya
# tenga la app andando, justamente los que la prueban.
# Pasó de verdad: idx_pend_a se creaba 450 líneas antes que equivalencias_pendientes.
_creada_en = {}
for m in re.finditer(r'CREATE TABLE(?:\s+IF NOT EXISTS)?\s+(\w+)', SRC):
    _creada_en.setdefault(m.group(1), SRC[:m.start()].count("\n") + 1)
for m in re.finditer(r'CREATE INDEX(?:\s+IF NOT EXISTS)?\s+(\w+)\s+ON\s+(\w+)', SRC, re.S):
    _indice, _tabla = m.group(1), m.group(2)
    _linea = SRC[:m.start()].count("\n") + 1
    _linea_tabla = _creada_en.get(_tabla)
    if _linea_tabla and _linea < _linea_tabla:
        reportar("ERROR", _linea,
                 f"el índice {_indice} se crea acá, pero la tabla {_tabla} recién se crea en "
                 f"L{_linea_tabla}: con una base nueva la app no abre («no such table»). "
                 "El índice va junto a su tabla")

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
# .get("x") / .pop("x") / .setdefault("x") son claves de diccionario, no valores de estado.
# Formalmente son argumentos de una llamada, así que se colaban igual: informe.get("pendientes")
# quedaba marcado por parecerse a "pendiente". Ese es el tipo de falso positivo que hace que
# alguien deje de leer la auditoría.
_METODOS_DE_CLAVE = {"get", "pop", "setdefault"}

literales_en_riesgo = []
for nodo in ast.walk(ARBOL):
    if isinstance(nodo, ast.Call):
        if (isinstance(nodo.func, ast.Attribute) and nodo.func.attr in _METODOS_DE_CLAVE):
            continue
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


# Adentro de un callback (on_click/on_change) la regla no aplica: el callback corre ANTES de que
# la pantalla se vuelva a dibujar, así que en ese momento el widget todavía no existe. Sin esta
# salvedad, un callback escrito más abajo que su widget quedaba marcado sin estar mal.
_callbacks = set()
for n in ast.walk(ARBOL):
    if isinstance(n, ast.Call):
        for kw in n.keywords:
            if kw.arg in ("on_click", "on_change") and isinstance(kw.value, ast.Name):
                _callbacks.add(kw.value.id)
_lineas_callback = set()
for n in ARBOL.body:
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in _callbacks:
        for x in ast.walk(n):
            if hasattr(x, "lineno"):
                _lineas_callback.add(x.lineno)

for n in ast.walk(ARBOL):
    if isinstance(n, (ast.Assign, ast.AugAssign)):
        for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
            k = _clave_session_state(t)
            if k and k in _keys_widget and n.lineno > _keys_widget[k] \
                    and n.lineno not in _lineas_callback:
                reportar("ERROR", n.lineno,
                         f"st.session_state[{k!r}] se escribe después de dibujar su widget "
                         f"(L{_keys_widget[k]}) — Streamlit lo prohíbe. Guardarlo en otra clave "
                         "y volcarlo antes del widget, como se hace con 'sugerencia_busqueda'")

# ============ 8f-bis. Claves fijas adentro de un bucle ============
# Un widget con key literal metido en un for se dibuja con la MISMA clave en cada vuelta. Con una
# sola vuelta no se nota nunca; con dos, Streamlit corta la app entera. El caso real: el bloque
# "¿por qué apareció este resultado?" está adentro del bucle que recorre los códigos buscados, y
# el campo de búsqueda invita explícitamente a pedir varios separados por coma — así que
# alcanzaba con buscar dos y abrir esa sección en los dos.
# No hay forma de que esto esté bien: si el bucle da dos vueltas, revienta.
for n in ast.walk(ARBOL):
    if not es_st(n, WIDGETS):
        continue
    clave = next((k.value for k in n.keywords if k.arg == "key"), None)
    if not (isinstance(clave, ast.Constant) and isinstance(clave.value, str)):
        continue
    bucle = None
    for padre in _ancestros(n):
        if isinstance(padre, (ast.For, ast.While)):
            bucle = padre
            break
        if isinstance(padre, (ast.FunctionDef, ast.AsyncFunctionDef)):
            break
    if bucle is not None:
        reportar("ERROR", n.lineno,
                 f"st.{n.func.attr} con key fija {clave.value!r} adentro del bucle de L"
                 f"{bucle.lineno}: en la segunda vuelta la clave se repite y Streamlit corta la "
                 "app. La key tiene que llevar algo que cambie en cada vuelta")

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

# ============ 8i. Borrarle datos a las filas que quedan guardadas ============
# El bug más difícil de ver de todo el archivo fue este. Las listas de resultados se guardan en
# st.session_state y se REUSAN en cada refresco: son los mismos diccionarios, no una copia.
# agregar_margen() les borraba "_costo" para que el costo no saliera en la tabla, y funcionaba
# —la primera vez—. A partir del segundo toque de cualquier botón el costo ya no estaba, así que
# la columna Margen quedaba vacía y el aviso de «mejor margen» desaparecía. Sin error, sin aviso:
# se veía una vez y no volvía más.
# Lo que hay que hacer es sacar lo que no va A LA HORA DE DIBUJAR, sobre una copia.
#
# Se mira SOLO el cuerpo de la pantalla. Adentro de una función, las filas son las que acaba de
# traer la consulta y sacarles una clave interna antes de devolverlas está perfecto: marcarlo
# llenaba la auditoría de funciones sanas.
def _borra_una_clave(nodo):
    """pop('algo') sobre un diccionario. lista.pop(i) saca un elemento de una lista y está bien:
    sin esta distinción el chequeo marcaba el botón de quitar de la lista de WhatsApp."""
    return (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
            and nodo.func.attr == "pop" and nodo.args
            and isinstance(nodo.args[0], ast.Constant) and isinstance(nodo.args[0].value, str))


def _sin_entrar_a_funciones(raiz):
    for nodo in ast.iter_child_nodes(raiz):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        yield nodo
        yield from _sin_entrar_a_funciones(nodo)


_EN_PANTALLA = list(_sin_entrar_a_funciones(ARBOL))


def _menciona_sesion(nodo, conocidos):
    for x in ast.walk(nodo):
        if isinstance(x, ast.Attribute) and x.attr == "session_state":
            return True
        if isinstance(x, ast.Name) and x.id in conocidos:
            return True
    return False


# Qué nombres de la pantalla salieron de session_state (incluido el rebote
# `for item in guardadas:` y después `res = item["res"]`).
_de_sesion = set()
for _ in range(3):
    for nodo in _EN_PANTALLA:
        if isinstance(nodo, ast.Assign) and len(nodo.targets) == 1 \
                and isinstance(nodo.targets[0], ast.Name) \
                and _menciona_sesion(nodo.value, _de_sesion):
            _de_sesion.add(nodo.targets[0].id)
        if isinstance(nodo, ast.For) and isinstance(nodo.target, ast.Name) \
                and _menciona_sesion(nodo.iter, _de_sesion):
            _de_sesion.add(nodo.target.id)

# Funciones que le borran claves a las filas que reciben
_vacian_lo_que_reciben = set()
for _fn in ARBOL.body:
    if not isinstance(_fn, ast.FunctionDef):
        continue
    _params = {a.arg for a in _fn.args.args}
    _filas = {x.target.id for x in ast.walk(_fn)
              if isinstance(x, ast.For) and isinstance(x.target, ast.Name)
              and isinstance(x.iter, ast.Name) and x.iter.id in _params}
    for x in ast.walk(_fn):
        if _borra_una_clave(x) and isinstance(x.func.value, ast.Name) and x.func.value.id in _filas:
            _vacian_lo_que_reciben.add(_fn.name)

for nodo in _EN_PANTALLA:
    # 1) pop() directo sobre una fila que salió de la sesión
    if _borra_una_clave(nodo) and isinstance(nodo.func.value, ast.Name) \
            and nodo.func.value.id in _de_sesion:
        reportar("ERROR", nodo.lineno,
                 f"'{nodo.func.value.id}' salió de session_state y se le está borrando una "
                 "clave: se reusa en cada refresco, así que del segundo en adelante ese dato ya "
                 "no está y nada lo avisa. Sacala al dibujar, sobre una copia")
    # 2) una función que vacía las filas que recibe, llamada con datos de la sesión
    if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name) \
            and nodo.func.id in _vacian_lo_que_reciben:
        for arg in nodo.args:
            if isinstance(arg, ast.Name) and arg.id in _de_sesion:
                reportar("ERROR", nodo.lineno,
                         f"{nodo.func.id}() le borra claves a las filas que recibe, y "
                         f"'{arg.id}' salió de session_state: del segundo refresco en adelante "
                         "esos datos ya no están. Que las saque quien dibuja, sobre una copia")


# ============ 8j. Funciones usadas antes de estar definidas ============
# El caso real: se agregó anotar_error() y se conectó a 143 lugares, entre ellos dentro de
# get_connection(), que corre al arrancar. Pero anotar_error quedó definida DESPUÉS de esa
# llamada. Compila perfecto y revienta con NameError al abrir la app.
#
# Solo importa para lo que se ejecuta al nivel del módulo: adentro de una función, el orden
# no importa porque para cuando se llama ya está todo definido.
_defs_por_nombre = {}
for _n in ARBOL.body:
    if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        _defs_por_nombre.setdefault(_n.name, _n.lineno)

_llamadas_al_arrancar = []
for _n in ARBOL.body:
    if isinstance(_n, ast.Expr) and isinstance(_n.value, ast.Call):
        _fn = getattr(_n.value.func, "id", None)
        if _fn:
            _llamadas_al_arrancar.append((_fn, _n.lineno))
    elif isinstance(_n, ast.Assign):
        for _x in ast.walk(_n):
            if isinstance(_x, ast.Call) and getattr(_x.func, "id", None):
                _llamadas_al_arrancar.append((_x.func.id, _n.lineno))

for _fn, _linea in _llamadas_al_arrancar:
    _cuerpo = next((x for x in ARBOL.body
                    if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == _fn), None)
    if _cuerpo is None:
        continue
    # Qué otras funciones del archivo usa esa función
    for _x in ast.walk(_cuerpo):
        if not (isinstance(_x, ast.Call) and getattr(_x.func, "id", None)):
            continue
        _usada = _x.func.id
        _def_linea = _defs_por_nombre.get(_usada)
        if _def_linea and _def_linea > _linea:
            reportar("ERROR", _def_linea,
                     f"'{_usada}' se define acá pero {_fn}() la usa al arrancar (L{_linea}): "
                     "NameError al abrir la app")

# Y la llamada misma. Lo de arriba mira qué usa por dentro la función que corre al arrancar,
# pero no si ESA función está definida más abajo, y en este archivo todo lo que no está adentro
# de una función corre de arriba hacia abajo en cada dibujo —las pantallas incluidas—. Pasó:
# se agregó `_actividad_del_mostrador()["empezo"] = ...` arriba de todo, con la función
# definida 11.000 líneas más abajo. NameError al abrir la app, y este control no lo veía.
def _llamadas_fuera_de_funciones(nodo):
    for _hijo in ast.iter_child_nodes(nodo):
        if isinstance(_hijo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(_hijo, ast.Call) and isinstance(_hijo.func, ast.Name):
            yield _hijo
        yield from _llamadas_fuera_de_funciones(_hijo)


for _llamada in _llamadas_fuera_de_funciones(ARBOL):
    _def_linea = _defs_por_nombre.get(_llamada.func.id)
    if _def_linea and _def_linea > _llamada.lineno:
        reportar("ERROR", _llamada.lineno,
                 f"'{_llamada.func.id}()' se llama acá, al nivel del módulo, y se define recién "
                 f"en la línea {_def_linea}: NameError al abrir la app")


# ============ 8k. Índices de menú repetidos o faltantes ============
# El caso real, y me pasó dos veces: se agrega una pestaña al principio de la lista y todos
# los índices de abajo quedan corridos. Dos ramas con el mismo índice significa que una
# pantalla es inalcanzable, y nadie se entera hasta que alguien la busca y no está.
import collections as _col

for _lista in re.findall(r'^\s*(\w+) = \[([^\]]*?)\]\s*$', SRC, re.M | re.S):
    _nombre, _cuerpo = _lista
    if not re.search(rf'{_nombre}\[\d+\]', SRC):
        continue
    _cuantos = len([x for x in re.split(r'",\s*"', _cuerpo) if x.strip()])
    _usados = [int(x) for x in re.findall(rf'== {_nombre}\[(\d+)\]', SRC)]
    if not _usados:
        continue
    # Lo que hay que detectar es el índice que NO SE USA, no el repetido. Un índice repetido
    # es legítimo: mantenimiento reparte sus 36 herramientas en seis grupos SIN mover el
    # código de lugar, o sea con varios `if grupo == GRUPOS[n]:` salteados a lo largo de la
    # pantalla. Mover mil líneas para agrupar distinto es mucho más peligroso que repetir una
    # guarda, y el barrido de pantallas no distingue una cosa de la otra.
    # El corrimiento de índices —que es el error real— igual se ve: si se agrega una opción al
    # principio, el último índice deja de usarse, y eso es lo que se reporta.
    _faltan = [i for i in range(_cuantos) if i not in _usados]
    if _faltan and len(_usados) >= 2:
        reportar("ERROR", 0,
                 f"{_nombre}: hay {_cuantos} opciones pero el índice {_faltan} no se usa "
                 "en ninguna rama — esa pantalla no se puede abrir (¿se agregó una opción "
                 "y se corrieron los índices?)")

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
# Las clases también definen un nombre. Faltaban, así que la primera clase que apareciera en el
# archivo se reportaba como "nombre usado y nunca definido".
definidas = {n.name for n in ast.walk(ARBOL)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
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
    # La lambda va en la misma bolsa que el def: sus parámetros son nombres definidos.
    # Sin esto, cualquier lambda con un parámetro de nombre nuevo se reportaba como ERROR
    # ("nombre usado y nunca definido: 'kv'"). Venía andando de casualidad: las lambdas que ya
    # había usaban x, f, i, t — nombres que además existen sueltos en otro lado del archivo.
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        for a in n.args.args + n.args.kwonlyargs + n.args.posonlyargs: conocidas.add(a.arg)
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

# ============ 12b. Dos definiciones con el mismo nombre ============
# Python no se queja: la segunda def pisa a la primera y listo. Pero la primera queda muerta, y
# lo que la llamaba termina ejecutando la otra —con otros parámetros y otro significado— y
# revienta recién cuando alguien entra a esa pantalla.
# Pasó de verdad acá: había dos nivel_de_confianza(), una que recibía la lista de evidencias y
# otra que recibía un puntaje. La de evidencias nunca corrió, y la pantalla de equivalencias
# sugeridas se caía con "'>=' not supported between instances of 'list' and 'int'" apenas
# aparecía una candidata con evidencia.
_definiciones = defaultdict(list)
for n in ARBOL.body:
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        _definiciones[n.name].append(n.lineno)
for nombre, lineas in _definiciones.items():
    if len(lineas) > 1:
        reportar("ERROR", lineas[0],
                 f"'{nombre}' está definido {len(lineas)} veces (L"
                 + ", L".join(str(x) for x in lineas)
                 + "): la última pisa a las anteriores. Todo lo que llame a las de arriba va a "
                   "ejecutar la de abajo, con los parámetros de otra cosa")


# ============ 12c. Un except que se llama a sí mismo ============
# Una función que en su propio manejador de errores se vuelve a llamar a sí misma con los
# mismos datos entra en recursión infinita: si el cuerpo falló una vez, va a fallar igual la
# segunda, y la tercera. Y el RecursionError que sale de ahí no lo agarra nadie, porque los
# que llaman esperan ValueError, sqlite3.Error o lo que sea que la función maneja — así que
# tumba la pantalla entera.
# Pasó de verdad acá: anotar_error(), la función que registra los errores que la app decide
# ignorar y cuyo docstring dice "NUNCA puede fallar", tenía en su except un
# anotar_error("anotar_error", _err). Era la única función capaz de voltear la app, y lo hacía
# justo cuando algo ya había salido mal.
for _f in ast.walk(ARBOL):
    if not isinstance(_f, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    for _h in ast.walk(_f):
        if not isinstance(_h, ast.ExceptHandler):
            continue
        for _c in ast.walk(_h):
            if isinstance(_c, ast.Call) and isinstance(_c.func, ast.Name) and _c.func.id == _f.name:
                reportar("ERROR", _c.lineno,
                         f"'{_f.name}' se llama a sí misma dentro de su propio except: si el "
                         "cuerpo falla, el reintento falla igual y se repite para siempre. El "
                         "RecursionError no lo agarra el que llamó y se cae la pantalla")


# ============ 12d. Tope de trabajo que siempre agarra lo mismo ============
# Un LIMIT sin ORDER BY devuelve "las que la base tenga a mano", que en SQLite es el orden de
# inserción. Para una vista previa está bien. El problema es cuando el LIMIT es un TOPE DE
# TRABAJO —la función lee un lote, lo procesa y lo GUARDA—: ahí lo que queda afuera no es "el
# resto", es siempre EL MISMO resto, y no se procesa nunca por más veces que se corra.
# Pasó de verdad acá dos veces:
#   · recalcular_confianzas() tomaba LIMIT filas de todos los vínculos: correrla de nuevo
#     repuntuaba las mismas y el 84% del catálogo quedaba sin puntaje para siempre;
#   · auditar_equivalencias_cargadas() revisaba las primeras 8.000 de 24.774, o sea las más
#     viejas en vez de las más sospechosas.
# Para no marcar lo que anda, se pide que se cumpla TODO:
#   · la consulta tiene LIMIT y no tiene ORDER BY;
#   · la función además ESCRIBE (UPDATE/INSERT/DELETE): si solo lee, el tope es de pantalla;
#   · y la consulta no excluye lo ya hecho (IS NULL, NOT EXISTS, NOT IN), que es justamente
#     como se escribe un lote que sí avanza.
def _escribe_en_la_base(nodo):
    for x in ast.walk(nodo):
        if isinstance(x, ast.Constant) and isinstance(x.value, str):
            t = x.value.upper().lstrip()
            if t.startswith(("UPDATE ", "INSERT ", "DELETE ")):
                return True
    return False


for _f in ast.walk(ARBOL):
    if not isinstance(_f, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    if not _escribe_en_la_base(_f):
        continue
    for _n in ast.walk(_f):
        if not isinstance(_n, ast.Constant) or not isinstance(_n.value, str):
            continue
        _sql = _n.value.upper()
        if "SELECT" not in _sql or "LIMIT" not in _sql:
            continue
        if any(x in _sql for x in ("ORDER BY", "IS NULL", "NOT EXISTS", "NOT IN", "GROUP BY")):
            continue
        # LIMIT 1 es buscar UN registro, no un lote: cualquiera de los que coinciden sirve.
        if re.search(r'LIMIT\s+1\s*$', _sql.strip()) or "LIMIT 1 " in _sql:
            continue
        reportar("REVISAR", _n.lineno,
                 f"'{_f.name}' lee un lote con LIMIT y sin ORDER BY, y después escribe: lo que "
                 "queda afuera del tope es siempre lo mismo y no se procesa nunca")


# ============ 13. El mapa del principio contra las secciones de verdad ============
# app.py arranca con un índice de sus secciones. Un índice a mano se desactualiza en el primer
# cambio y entonces es peor que no tenerlo: manda a buscar cosas donde ya no están. Esto lo
# compara con los encabezados reales y avisa si se separaron.
_encabezados = []
for _i, _l in enumerate(LINEAS):
    if (re.match(r'^# ={10,}$', _l.rstrip()) and _i + 2 < len(LINEAS)
            and re.match(r'^# [A-ZÁÉÍÓÚÑ]', LINEAS[_i + 1])
            and re.match(r'^# ={10,}$', LINEAS[_i + 2].rstrip())):
        _encabezados.append(LINEAS[_i + 1][2:].strip())
_doc = ast.get_docstring(ARBOL) or ""
if _encabezados and "CÓMO ESTÁ ORGANIZADO" in _doc:
    _listadas = [l.strip()[2:].strip() for l in _doc.splitlines() if l.strip().startswith("·")]
    _faltan = [x for x in _encabezados if x not in _listadas]
    _sobran = [x for x in _listadas if x not in _encabezados]
    if _faltan:
        reportar("AVISO", 1, "el mapa del principio no nombra estas secciones: "
                             + "; ".join(_faltan[:4]) + (" …" if len(_faltan) > 4 else ""))
    if _sobran:
        reportar("AVISO", 1, "el mapa del principio nombra secciones que ya no existen: "
                             + "; ".join(_sobran[:4]) + (" …" if len(_sobran) > 4 else ""))
    if _listadas and not _faltan and not _sobran and _listadas != _encabezados:
        reportar("AVISO", 1, "el mapa del principio tiene las secciones en otro orden que el "
                             "archivo")



# ============ 14. El mismo bloque escrito dos veces seguidas ============
# Copiar y pegar un bloque, editar la copia y olvidarse de borrar el original no da error: el
# segundo pasa igual y no se nota. Pasó acá: descartar_candidata() hacía dos veces exactamente
# el mismo INSERT OR REPLACE, uno abajo del otro. Como era OR REPLACE el resultado era el
# mismo, así que nunca se iba a ver; pero si la sentencia repetida hubiera sido un INSERT
# común, o un UPDATE que suma, el efecto se aplicaba dos veces.
# Se pide que sean sentencias SEGUIDAS y de más de una línea, para no marcar repeticiones
# legítimas (dos `st.write("")` para separar, dos veces el mismo `continue`).
_bloques = []
for _x in ast.walk(ARBOL):
    for _campo, _val in ast.iter_fields(_x):
        if isinstance(_val, list) and _val and isinstance(_val[0], ast.stmt):
            _bloques.append(_val)
for _cuerpo in _bloques:
    for _a, _b in zip(_cuerpo, _cuerpo[1:]):
        if _a.end_lineno - _a.lineno < 1:
            continue              # una sola línea: repetirla casi siempre es a propósito
        _ta = "\n".join(l.strip() for l in LINEAS[_a.lineno - 1:_a.end_lineno])
        _tb = "\n".join(l.strip() for l in LINEAS[_b.lineno - 1:_b.end_lineno])
        if _ta and _ta == _tb:
            reportar("ERROR", _b.lineno,
                     f"este bloque es idéntico al de la línea {_a.lineno}, justo arriba: "
                     "quedó una copia sin borrar")


# ============ 15. Operación de varios pasos sin transaccion() ============
# La conexión está en autocommit: cada sentencia se confirma sola. Una función que escribe en
# VARIAS tablas y se corta en el medio deja la base a mitad de camino, y eso se vio de verdad:
#   · cerrar_reserva() descontaba el stock y después marcaba la reserva; cortada en el medio,
#     el empleado la cerraba otra vez y una reserva de 3 unidades descontaba 6;
#   · fusionar_productos() borraba los vínculos del duplicado y después el duplicado; cortada
#     en el medio, el producto seguía ahí y sus equivalencias no.
# Para eso está el bloque transaccion(). Esto marca a las que escriben en dos tablas distintas
# y no lo usan. Se dejan afuera:
#   · las que arman el esquema o corren migraciones (van una vez, al arrancar, y sin usuarios);
#   · las que escriben en OTRA base (generar_backup_sin_fotos abre su propio archivo).
_TABLAS_SQL = re.compile(
    r'\b(?:insert\s+(?:or\s+\w+\s+)?into|update|delete\s+from|replace\s+into)\s+'
    r'([a-z_][a-z_0-9]*)', re.I)
_SIN_TRANSACCION_OK = ("_esquema_", "_datos_precargados", "crear_esquema", "_migracion",
                       "generar_backup", "restaurar_")

def _tablas_que_escribe(nodo):
    tablas = {}
    for x in ast.walk(nodo):
        if not (isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute)
                and x.func.attr in ("execute", "executemany") and x.args):
            continue
        a = x.args[0]
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            texto = a.value
        elif isinstance(a, ast.JoinedStr):
            texto = " ".join(p.value for p in a.values if isinstance(p, ast.Constant))
        else:
            continue
        for m in _TABLAS_SQL.finditer(" ".join(texto.split())):
            # «ON CONFLICT ... DO UPDATE SET» hace que el patrón lea «set» como si fuera una
            # tabla. No es la única palabra reservada que puede caer ahí.
            nombre = m.group(1).lower()
            if nombre not in ("set", "or", "into", "from", "table", "index", "trigger", "view"):
                tablas.setdefault(nombre, x.lineno)
    return tablas

def _usa_transaccion(nodo):
    for x in ast.walk(nodo):
        if isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id == "transaccion":
            return True
    return False

for _f in ast.walk(ARBOL):
    if not isinstance(_f, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    if _f.name.startswith(_SIN_TRANSACCION_OK) or _usa_transaccion(_f):
        continue
    _tablas = _tablas_que_escribe(_f)
    if len(_tablas) >= 2:
        reportar("REVISAR", _f.lineno,
                 f"'{_f.name}' escribe en {len(_tablas)} tablas ({', '.join(sorted(_tablas))}) "
                 "y no usa transaccion(): si se corta en el medio, la base queda a medias")



# ============ 16. Caché de una consulta sin forma de saber que la base cambió ============
# @st.cache_data guarda el resultado según los ARGUMENTOS. Si la función lee la base y no
# recibe ningún argumento que cambie cuando cambia la base, el resultado se congela hasta que
# se reinicia la app.
# El testigo hay que elegirlo con cuidado, y eso esto NO lo puede revisar: el catálogo por
# vehículo tenía uno —COUNT(*) de productos— pero no alcanzaba, porque «reparar descripciones
# pegadas» reescribe miles de descripciones sin mover el contador ni un número, y la pantalla
# seguía mostrando los modelos viejos (ahora usa version_del_catalogo(), que además suma el
# largo de las descripciones). Lo que sí se puede revisar es el caso grueso: que no haya
# ningún testigo. Se acepta un ttl, o un parámetro cuyo nombre hable de versión o testigo.
_TESTIGO = re.compile(r'version|versión|testigo|firma|hash|sello', re.I)
for _f in ast.walk(ARBOL):
    if not isinstance(_f, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    _cacheada = False
    _tiene_ttl = False
    for _d in _f.decorator_list:
        _call = _d if isinstance(_d, ast.Call) else None
        _attr = (_call.func if _call else _d)
        if isinstance(_attr, ast.Attribute) and _attr.attr == "cache_data":
            _cacheada = True
            if _call and any(k.arg == "ttl" for k in _call.keywords):
                _tiene_ttl = True
    if not _cacheada or _tiene_ttl:
        continue
    _lee_la_base = any(isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute)
                       and x.func.attr in ("execute", "executemany")
                       for x in ast.walk(_f))
    if not _lee_la_base:
        continue
    _args = [a.arg for a in _f.args.args + _f.args.kwonlyargs]
    if not any(_TESTIGO.search(a) for a in _args):
        reportar("REVISAR", _f.lineno,
                 f"'{_f.name}' está cacheada y lee la base, pero no recibe ningún testigo de "
                 "versión ni tiene ttl: el resultado queda congelado hasta reiniciar la app")



# ============ 17. st.rerun() o st.stop() adentro de una transacción ============
# Las dos cortan el script lanzando una excepción que NO hereda de Exception (RerunException y
# StopException heredan de BaseException). transaccion() las atrapa —a propósito, para no
# dejar la transacción abierta— y deshace todo. O sea: refrescar la pantalla en el medio de un
# `with transaccion():` tira abajo, en silencio, lo que se acababa de guardar. Hay que cerrar
# el bloque primero y recién después refrescar.
for _w in ast.walk(ARBOL):
    if not isinstance(_w, ast.With):
        continue
    if not any(isinstance(_i.context_expr, ast.Call)
               and isinstance(_i.context_expr.func, ast.Name)
               and _i.context_expr.func.id == "transaccion" for _i in _w.items):
        continue
    for _x in ast.walk(_w):
        if (isinstance(_x, ast.Call) and isinstance(_x.func, ast.Attribute)
                and _x.func.attr in ("rerun", "stop")
                and isinstance(_x.func.value, ast.Name) and _x.func.value.id == "st"):
            reportar("ERROR", _x.lineno,
                     f"st.{_x.func.attr}() adentro del transaccion() que abre la línea "
                     f"{_w.lineno}: deshace lo que se guardó, y sin avisar")



# ============ 18. LIMIT sobre el PREFILTRO y no sobre el resultado ============
# Traer «las primeras N filas» y recién después decidir cuáles sirven no devuelve las primeras
# N buenas: devuelve las buenas que haya entre las primeras N cualesquiera. Y no avisa.
# Pasó acá: catalogo_por_vehiculo() traía LIMIT 4000 filas cuya descripción contuviera el
# nombre de la marca, y después confirmaba una por una. Para MAN, que por texto engancha con
# MANGUERA, MANIJA y ALEMANIA, el tope se llenaba de mangueras y los productos de MAN de
# verdad quedaban afuera: la pantalla salía vacía con el dato cargado.
# Marca las consultas con LIMIT, sin ORDER BY, cuyas filas se filtran después en Python.
for _f in ast.walk(ARBOL):
    if not isinstance(_f, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    _con_limit = []
    for _n in ast.walk(_f):
        # También las f-string: la consulta con el WHERE armado aparte es justamente la forma
        # en que estaba escrita la que tenía el error.
        if isinstance(_n, ast.Constant) and isinstance(_n.value, str):
            _texto = _n.value
        elif isinstance(_n, ast.JoinedStr):
            _texto = " ".join(_p.value for _p in _n.values
                              if isinstance(_p, ast.Constant) and isinstance(_p.value, str))
        else:
            continue
        _sql = " ".join(_texto.split()).upper()
        if "SELECT" not in _sql or not re.search(r'\bLIMIT\b', _sql) or "ORDER BY" in _sql:
            continue
        # Igual que en el control 12: si la consulta ya excluye lo hecho (IS NULL, NOT EXISTS,
        # NOT IN), el LIMIT es una tanda de trabajo que avanza, no un prefiltro que recorta.
        if any(x in _sql for x in ("IS NULL", "NOT EXISTS", "NOT IN")):
            continue
        # LIMIT 1 es traer UN registro por clave, no una tanda.
        if re.search(r'\bLIMIT\s+1\b', _sql):
            continue
        # Y se pide un LIKE: la firma del error es un filtro APROXIMADO en SQL, un tope, y la
        # comprobación exacta después en Python. Cuando el WHERE ya es exacto (marca_id = ?),
        # el tope es un presupuesto de trabajo a propósito, no un recorte accidental.
        if "LIKE" not in _sql:
            continue
        _con_limit.append(_n.lineno)
    if not _con_limit:
        continue
    # ¿se descartan filas después, en un for sobre el resultado?
    # Un `continue` adentro de un except es saltear un error, no filtrar el resultado.
    _en_except = {id(_x) for _h in ast.walk(_f) if isinstance(_h, ast.ExceptHandler)
                  for _x in ast.walk(_h)}
    _descarta = False
    for _n in ast.walk(_f):
        if not isinstance(_n, ast.For):
            continue
        for _x in ast.walk(_n):
            if isinstance(_x, ast.Continue) and id(_x) not in _en_except:
                _descarta = True
    if _descarta:
        reportar("REVISAR", _con_limit[0],
                 f"'{_f.name}' corta con LIMIT y después descarta filas en Python: el tope cae "
                 "sobre el prefiltro, así que lo que sirve puede quedar afuera del corte")



# ============ 19. Acción destructiva sin candado ============
# La app deja entrar sin contraseña a propósito: el mostrador la usa así. Por eso lo que borra
# o reescribe se protege de a una, con pedir_password_admin(). Y por eso mismo se olvida: el
# candado estaba puesto en «eliminar una marca», «eliminar un producto» y «deshacer una
# importación», y faltaba en «separar las descripciones pegadas», que reescribe el catálogo
# entero. Probado con la app de verdad: alguien que entró con «Continuar», sin contraseña,
# apretó una vez y reescribió 9.147 descripciones.
# Esto marca las llamadas destructivas hechas desde la pantalla (fuera de cualquier función)
# que no tengan un pedir_password_admin() o un es_admin() arriba.
# «depurar_» está en la lista por un motivo concreto: depurar_huerfanos() borra los productos
# que no tienen ninguna equivalencia, que en el catálogo real son 25.143 de 61.574 — el 41%.
# El nombre no suena destructivo y por eso casi se pasa por alto.
_DESTRUCTIVAS = re.compile(r'^(eliminar_|borrar_|vaciar_|fusionar_|deshacer_|reparar_|depurar_|'
                           r'aumentar_precios|crear_usuario|cambiar_password|importar_dtc_masivo|'
                           r'restaurar_backup|restaurar_de_papelera|recalcular_confianzas|'
                           r'actualizar_precio_stock)')
# Vale cualquiera de los dos candados, y no es lo mismo:
#   · pedir_password_admin() para lo que borra o configura;
#   · pedir_password_operador_o_admin() para el precio y el stock, que es trabajo de todos los
#     días. Pedir la contraseña de administrador ahí rompería el mostrador; no pedir nada
#     dejaba los precios abiertos a cualquiera que entrara con «Continuar».
_padres = {}
for _n in ast.walk(ARBOL):
    for _h in ast.iter_child_nodes(_n):
        _padres[_h] = _n


def _tiene_candado(nodo):
    """¿Hay un if con pedir_password_admin()/es_admin() por encima, sin salir de la pantalla?"""
    x = nodo
    while x in _padres:
        x = _padres[x]
        if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return True       # adentro de una función: no es un botón de pantalla
        if isinstance(x, ast.If):
            prueba = ast.dump(x.test)
            # candado() es el envoltorio que además RECUERDA el clic entre corridas; ver
            # por qué hace falta en su docstring.
            if any(k in prueba for k in ("candado", "pedir_password_admin", "es_admin",
                                         "pedir_password_operador_o_admin",
                                         "es_operador_o_admin")):
                return True
    return False


for _n in ast.walk(ARBOL):
    if (isinstance(_n, ast.Call) and isinstance(_n.func, ast.Name)
            and _DESTRUCTIVAS.match(_n.func.id) and not _tiene_candado(_n)):
        reportar("ERROR", _n.lineno,
                 f"{_n.func.id}() se dispara desde la pantalla sin candado: cualquiera que "
                 "entre con «Continuar» puede hacerlo. Falta pedir_password_admin() o, si es "
                 "trabajo de mostrador, pedir_password_operador_o_admin()")



# ============ 20. Guardián que no guarda: hasattr(st, "secrets") ============
# El atributo `secrets` de Streamlit existe SIEMPRE; lo que falla es leerlo. Sin un
# secrets.toml en el servidor, el primer acceso levanta StreamlitSecretNotFoundError, así que
# `st.secrets.get("x") if hasattr(st, "secrets") else None` no protege nada: entra por la rama
# de la izquierda y explota igual.
# Estaba escrito así en los ocho lugares que leen secrets, y uno de ellos era validar_password():
# en un servidor sin secrets.toml, apretar «Ingresar con contraseña» tiraba la excepción en
# pantalla en vez de decir «contraseña incorrecta», y con ella caía cualquier candado de
# administrador. Lo que sí funciona es intentar leer y atrapar, que es lo que hace
# secretos_app().
for _n in ast.walk(ARBOL):
    if (isinstance(_n, ast.Call) and isinstance(_n.func, ast.Name) and _n.func.id == "hasattr"
            and len(_n.args) == 2 and isinstance(_n.args[1], ast.Constant)
            and _n.args[1].value == "secrets"):
        reportar("ERROR", _n.lineno,
                 'hasattr(st, "secrets") no protege nada: el atributo existe siempre y lo que '
                 "falla es leerlo. Usar secretos_app()")



# ============ 21. fetch() en la misma expresión que otra llamada ============
# El cursor es UNO SOLO y compartido. Si en la misma expresión hay un c.fetchone() y además
# una llamada a otra función de la app, el orden de evaluación decide quién usa el cursor
# primero — y Python evalúa de izquierda a derecha, así que esto:
#
#     return descripciones_por_palabra(version), c.fetchone()[0]
#
# ejecuta la función ANTES del fetch, la función hace sus propias consultas sobre el mismo
# cursor, y para cuando llega el fetchone() ya está leyendo otro resultado. Devuelve None y
# el error aparece lejos, en quien usaba el valor. Pasó exactamente así y dejó sin funcionar
# todas las sugerencias por descripción.
# La forma segura es siempre la misma: fetch primero, a una variable, y después llamar.
# Solo importan las funciones que USAN el cursor: si no lo tocan, el orden da igual.
_FUNCIONES_DEL_ARCHIVO = set()
for _f in ast.walk(ARBOL):
    if not isinstance(_f, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    if any(isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute)
           and x.func.attr in ("execute", "executemany", "fetchone", "fetchall")
           for x in ast.walk(_f)):
        _FUNCIONES_DEL_ARCHIVO.add(_f.name)
for _n in ast.walk(ARBOL):
    if not isinstance(_n, (ast.Return, ast.Assign)):
        continue
    _valor = _n.value
    if _valor is None:
        continue
    # En una comprensión, el iterable se evalúa PRIMERO, así que `for r in c.fetchall()`
    # está a salvo aunque el cuerpo llame a otra cosa.
    _iterables = {id(g.iter) for x in ast.walk(_valor)
                  if isinstance(x, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp))
                  for g in x.generators}
    _hay_fetch = any(isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute)
                     and x.func.attr.startswith("fetch") and id(x) not in _iterables
                     for x in ast.walk(_valor))
    if not _hay_fetch:
        continue
    _otras = [x.func.id for x in ast.walk(_valor)
              if isinstance(x, ast.Call) and isinstance(x.func, ast.Name)
              and x.func.id in _FUNCIONES_DEL_ARCHIVO]
    if _otras:
        reportar("ERROR", _n.lineno,
                 f"c.fetch...() en la misma expresión que {_otras[0]}(): el cursor es "
                 "compartido y la función corre primero, así que el fetch lee otro resultado. "
                 "Guardar el fetch en una variable antes")


# ============ 22. Una cuenta que en realidad es una muestra ============
# Una función que se llama contar_algo() devuelve un número que la pantalla muestra como si
# fuera EL número. Si adentro hay un LIMIT, no lo es: es lo que encontró en las primeras filas.
# Pasó con contar_descripciones_pegadas(), que miraba 3.000 de 53.255 y decía «al menos 1.682»
# cuando eran 9.324 — y si en esas 3.000 no había ninguna, la pantalla afirmaba «Ninguna
# descripción con ese problema» con cincuenta mil filas sin mirar. Una cuenta parcial que se
# presenta como total es peor que no tener la cuenta: hace tomar la decisión equivocada.
for _n in ast.walk(ARBOL):
    if not isinstance(_n, ast.FunctionDef):
        continue
    if not re.match(r'^_?(contar|cuantos|cuantas|faltan|total)_', _n.name):
        continue
    _cuerpo = "\n".join(LINEAS[_n.lineno - 1:_n.end_lineno])
    if re.search(r'\bLIMIT\s+[?\d]', _cuerpo, re.I):
        reportar("REVISAR", _n.lineno,
                 f"'{_n.name}' devuelve una cuenta pero la consulta tiene LIMIT: lo que sale es "
                 "una muestra, y la pantalla la va a mostrar como si fuera el total")


# ============ 23. CREATE TRIGGER IF NOT EXISTS con el cuerpo armado en el código ============
# El IF NOT EXISTS mira solo el NOMBRE. Si el cuerpo del trigger cambia, la base que ya lo tiene
# se queda con la versión vieja para siempre y sin ningún error a la vista: los datos nuevos se
# calculan con la fórmula de antes. Pasó al sumarle el código de barras a 'busqueda'.
# La forma segura es DROP TRIGGER IF EXISTS + CREATE TRIGGER, que cuesta nada y siempre deja la
# versión de este código.
for _i, _linea in enumerate(LINEAS, 1):
    if not re.search(r'CREATE\s+TRIGGER\s+IF\s+NOT\s+EXISTS', _linea, re.I):
        continue
    _nombre = re.search(r'CREATE\s+TRIGGER\s+IF\s+NOT\s+EXISTS\s+(\w+)', _linea, re.I)
    _nombre = _nombre.group(1) if _nombre else "?"
    _hay_drop = any(re.search(r'DROP\s+TRIGGER\s+IF\s+EXISTS\s+' + re.escape(_nombre), l, re.I)
                    for l in LINEAS[max(0, _i - 12):_i])
    if not _hay_drop:
        reportar("REVISAR", _i,
                 f"CREATE TRIGGER IF NOT EXISTS '{_nombre}' sin DROP antes: si alguna vez cambia "
                 "el cuerpo, las bases que ya existen se quedan con la versión vieja en silencio")


# ============ 24. Una función cara adentro de un bucle ============
# st.cache_data esconde el costo. Una función cacheada NO es gratis: para saber si el caché
# sigue vigente hay que calcular el testigo —acá es version_del_catalogo(), que hace un
# COUNT + SUM(LENGTH(...)) sobre la tabla entera— y después deserializar lo guardado.
# Son 34 ms. Parece nada hasta que la llamada está adentro de un bucle: la pantalla de
# «Equivalencias sugeridas» revisa 400 vínculos y tardaba 37 segundos, de los cuales 13 eran
# 400 recorridas completas de productos para volver a leer el mismo diccionario.
# La solución siempre es la misma: calcularlo UNA vez antes del bucle y pasarlo.
_CARAS = {"version_del_catalogo", "cuantas_veces_aparece_cada_palabra"}
for _f in ast.walk(ARBOL):
    if isinstance(_f, ast.FunctionDef):
        for _d in _f.decorator_list:
            _txt = ast.dump(_d)
            if "cache_data" in _txt or "cache_resource" in _txt:
                _CARAS.add(_f.name)
# Solo molesta cuando NO se le pasa nada de la vuelta actual del bucle: ahí la llamada
# devuelve siempre lo mismo y está de más. Si recibe una variable —modelos_de_marca(marca,
# _version_cat), imagen_esquema_lista_para_mostrar(img_bytes, ...)— está bien donde está:
# depende de la iteración, o el testigo ya se calculó una sola vez afuera.
def _no_depende_del_bucle(llamada):
    for _a in list(llamada.args) + [k.value for k in llamada.keywords]:
        if not isinstance(_a, ast.Call):
            return False
    return True


for _n in ast.walk(ARBOL):
    if not isinstance(_n, (ast.For, ast.While)):
        continue
    for _cuerpo in _n.body:
        for _x in ast.walk(_cuerpo):
            if (isinstance(_x, ast.Call) and isinstance(_x.func, ast.Name)
                    and _x.func.id in _CARAS and _no_depende_del_bucle(_x)):
                reportar("REVISAR", _x.lineno,
                         f"{_x.func.id}() adentro de un bucle y sin nada que dependa de la "
                         "vuelta: aunque esté cacheada, cada llamada recalcula el testigo del "
                         "caché —una recorrida entera de la tabla— y deserializa el resultado. "
                         "Calcularla una vez antes del bucle")


# ============ 25. Dos funciones que hacen exactamente lo mismo ============
# Pasó con contar_huerfanos() y contar_productos_sin_equivalencias(): la misma consulta, dos
# nombres, dos pantallas. No es solo código de más — el día que una se corrige y la otra no,
# dos pantallas muestran números distintos del mismo dato y no hay forma de saber cuál creer.
# Las dos consultas no eran idénticas carácter por carácter —una tenía DISTINCT y otro
# sangrado—, así que comparar el texto tal cual no las encontraba. Se comparan normalizando lo
# que no cambia el significado: espacios de más adentro de los strings, mayúsculas, y el
# DISTINCT de un SELECT que ya no puede repetir filas.
class _NormalizarTextos(ast.NodeTransformer):
    def visit_Constant(self, nodo):
        if isinstance(nodo.value, str):
            v = re.sub(r'\s+', ' ', nodo.value).strip().upper()
            v = re.sub(r'\s+', ' ', re.sub(r'\bDISTINCT\b', '', v)).strip()
            return ast.copy_location(ast.Constant(value=v), nodo)
        return nodo


_CUERPOS = {}
for _n in ast.walk(ARBOL):
    if not isinstance(_n, ast.FunctionDef) or len(_n.body) < 2:
        continue
    _cuerpo = _n.body[1:] if isinstance(_n.body[0], ast.Expr) and isinstance(
        getattr(_n.body[0], "value", None), ast.Constant) else _n.body
    if len(_cuerpo) < 2:
        continue
    _huella = "\n".join(ast.dump(_NormalizarTextos().visit(copy.deepcopy(_x))) for _x in _cuerpo)
    if _huella in _CUERPOS:
        reportar("REVISAR", _n.lineno,
                 f"'{_n.name}' tiene el mismo cuerpo que '{_CUERPOS[_huella]}': dos nombres "
                 "para lo mismo terminan diciendo números distintos cuando se corrige una sola")
    else:
        _CUERPOS[_huella] = _n.name


# ============ 26. Un caché que nunca se refresca ============
# Streamlit NO hashea los parámetros que empiezan con guion bajo: es su forma de decir «esto no
# entra en la clave del caché». Así que una función cacheada que recibe el testigo del catálogo
# como '_version' se calcula UNA sola vez y después devuelve siempre lo mismo, pase lo que pase
# con la base. Estaba pasando en cinco funciones a la vez: se importaba una lista nueva y la
# pantalla de vehículos seguía mostrando los modelos viejos, y el extractor seguía sin conocer
# los códigos recién cargados, hasta reiniciar la app.
# Es un error que no se ve nunca leyendo la función: se ve en el nombre del parámetro.
# Un '_' sí está bien cuando el argumento no se puede hashear y al lado va su huella —una lista
# de puntos con su firma—, así que se pide que el nombre no suene a testigo.
_TESTIGOS = ("version", "testigo", "catalogo", "cuenta", "total", "fecha", "lote")
for _n in ast.walk(ARBOL):
    if not isinstance(_n, ast.FunctionDef):
        continue
    _cacheada = any(
        (isinstance(_d, ast.Call) and isinstance(_d.func, ast.Attribute)
         and _d.func.attr in ("cache_data", "cache_resource"))
        or (isinstance(_d, ast.Attribute) and _d.attr in ("cache_data", "cache_resource"))
        for _d in _n.decorator_list)
    if not _cacheada:
        continue
    for _arg in _n.args.args:
        if not _arg.arg.startswith("_"):
            continue
        if any(_t in _arg.arg.lower() for _t in _TESTIGOS):
            reportar("ERROR", _n.lineno,
                     f"'{_n.name}' está cacheada y su parámetro '{_arg.arg}' empieza con guion "
                     "bajo: Streamlit no lo hashea, así que ese caché no se refresca NUNCA. "
                     "Sacale el guion bajo")


# ============ 27) La cadena de REPLACE() de _sql_sin_acentos tiene un techo duro ============
# Cada par de _REEMPLAZOS_SIN_ACENTOS es un REPLACE() anidado adentro del anterior, y SQLite
# tiene un límite de anidamiento: medido en 3.45, revienta a los 31 con «parser stack overflow».
# Y no son 31 libres — la consulta que envuelve la expresión gasta del mismo presupuesto, así
# que con 28 pares la expresión anda suelta y falla adentro de un COUNT(). Pasarse no da un
# error al escribir el código: rompe la búsqueda entera de la app en tiempo de ejecución, que
# es exactamente la forma en que nadie se entera hasta que un cliente está esperando.
# Por eso el tope propio es 20, con diez de margen sobre el límite real.
for _n in ast.walk(ARBOL):
    if not (isinstance(_n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "_REEMPLAZOS_SIN_ACENTOS"
                    for t in _n.targets)):
        continue
    if not isinstance(_n.value, ast.List):
        continue
    _cuantos = len(_n.value.elts)
    _tope = 20
    for _m in ast.walk(ARBOL):
        if (isinstance(_m, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "MAXIMO_REEMPLAZOS_SIN_ACENTOS"
                        for t in _m.targets)
                and isinstance(_m.value, ast.Constant)):
            _tope = _m.value.value
    if _cuantos > _tope:
        reportar("ERROR", _n.lineno,
                 f"_REEMPLAZOS_SIN_ACENTOS tiene {_cuantos} pares y el tope es {_tope}. Cada uno "
                 "es un REPLACE() anidado y SQLite revienta a los 31 con «parser stack "
                 "overflow» — antes si la expresión va adentro de otra consulta. Pasarse rompe "
                 "TODA la búsqueda por texto en tiempo de ejecución")


# ============ 28) pickle.loads suelto es ejecución de código, no lectura de datos ============
# pickle no es un formato de datos: es una receta de construcción. Al leerlo puede fabricar
# cualquier objeto de cualquier módulo instalado, os.system incluido. Está comprobado en esta
# misma base: un blob armado a mano ejecuta lo que quiera apenas alguien lo lee.
# En esta app los únicos pickles son las firmas visuales, y viven adentro de la base — que se
# reemplaza entera desde Estadísticas → Restaurar backup con un .db que sube una persona. O
# sea que el contenido puede venir de afuera. Se leen con leer_firma_visual(), que solo sabe
# armar arrays de numpy. Si alguien vuelve a poner un pickle.loads pelado, vuelve el agujero.
for _n in ast.walk(ARBOL):
    if not (isinstance(_n, ast.Call) and isinstance(_n.func, ast.Attribute)
            and _n.func.attr in ("loads", "load")):
        continue
    _duenio = _n.func.value
    if not (isinstance(_duenio, ast.Name) and "pickle" in _duenio.id.lower()):
        continue
    reportar("ERROR", _n.lineno,
             f"pickle.{_n.func.attr}() suelto. pickle no lee datos: construye objetos, y con un "
             "blob preparado a mano eso es ejecutar código en el servidor. Las firmas visuales "
             "salen de la base, y la base se reemplaza con un archivo que sube el usuario. "
             "Usá leer_firma_visual(), que solo acepta arrays de numpy")


# ============ 29) El texto de la base no entra crudo en un markdown con HTML prendido ============
# Los proveedores usan «<» para decir «hasta tal año» («Master 98<»), y cuando lo que sigue es
# una letra —«1997<REF ORIG VW...»— el navegador lee el principio de una etiqueta y se traga
# todo hasta el próximo «>». Medido en la base real: 1.435 productos y 265.805 caracteres que
# desaparecían de la pantalla, justo la parte que dice a qué autos entra la pieza.
# Los campos de acá abajo son texto que vino de un Excel ajeno. Entre acentos graves no hace
# falta (markdown los escribe literales); en negrita o sueltos, sí.
_CAMPOS_DE_LA_BASE = ("descripcion", "marca", "motivo", "titulo_producto", "observaciones")
for _n in ast.walk(ARBOL):
    if not isinstance(_n, ast.Call):
        continue
    if not any(isinstance(k, ast.keyword) and k.arg == "unsafe_allow_html"
               and isinstance(k.value, ast.Constant) and k.value.value is True
               for k in _n.keywords):
        continue
    for _j in ast.walk(_n):
        if not isinstance(_j, ast.JoinedStr):
            continue
        _trozos = [LINEAS[_v.lineno - 1] for _v in _j.values
                   if isinstance(_v, ast.FormattedValue) and _v.lineno <= len(LINEAS)]
        for _v in _j.values:
            if not isinstance(_v, ast.FormattedValue):
                continue
            _txt = ast.unparse(_v.value)
            if "texto_para_html" in _txt:
                continue
            if not any(f"'{cmp}'" in _txt or f'"{cmp}"' in _txt for cmp in _CAMPOS_DE_LA_BASE):
                continue
            # Entre acentos graves markdown ya lo escribe literal.
            _linea = LINEAS[_v.lineno - 1] if _v.lineno <= len(LINEAS) else ""
            _pos = _linea.find("{" + _txt)
            if _pos > 0 and _linea[_pos - 1] == "`":
                continue
            reportar("ERROR", _v.lineno,
                     f"'{_txt}' es texto de la base y entra crudo en un markdown con HTML "
                     "prendido. Un «<» seguido de letra —«1997<REF ORIG VW...»— se come el "
                     "resto de la descripción en pantalla. Envolvelo en texto_para_html()")


# ============ 30) El índice de mantenimiento no puede mentir ============
# Arriba de cada grupo de mantenimiento se lista lo que hay adentro, y el buscador de
# herramientas busca sobre esa misma lista. Los dos salen de HERRAMIENTAS_MANTENIMIENTO, que
# es una tabla escrita a mano: si alguien agrega una herramienta a la pantalla y no la anota,
# queda invisible para el buscador —peor que antes, porque ahora el índice dice cuántas hay—;
# y si cambia un título y no lo cambia en la tabla, el índice nombra algo que no existe.
_reg = None
for _n in ast.walk(ARBOL):
    if (isinstance(_n, ast.Assign)
            and any(getattr(_t, "id", None) == "HERRAMIENTAS_MANTENIMIENTO" for _t in _n.targets)):
        try:
            _reg = ast.literal_eval(_n.value)
        except Exception:
            _reg = None
if _reg is not None:
    _en_tabla = {_h[0]: _h[1] for _h in _reg}
    # Los títulos que la pantalla dibuja de verdad, con el grupo en el que caen.
    _ini = _fin = None
    for _i, _l in enumerate(LINEAS):
        if _l.startswith("    if sub_admin == SUB_ADMIN[4]:"):
            _ini = _i
        elif _ini is not None and _l.startswith("        if sub_admin == SUB_ADMIN[5]:"):
            _fin = _i
            break
    if _ini is not None and _fin is not None:
        _g, _en_pantalla = None, {}
        for _i in range(_ini, _fin):
            _m = re.match(r'\s*if _grupo_mant == GRUPOS_MANTENIMIENTO\[(\d+)\]', LINEAS[_i])
            if _m:
                _g = int(_m.group(1))
            _m2 = re.match(r'\s*st\.markdown\("\*\*(.+?)\*\*"\)', LINEAS[_i])
            if _m2 and _g is not None:
                _en_pantalla[_m2.group(1)] = (_g, _i + 1)
        for _t, (_g, _ln) in _en_pantalla.items():
            if _t not in _en_tabla:
                reportar("ERROR", _ln,
                         f"la herramienta «{_t}» está en la pantalla y no en "
                         "HERRAMIENTAS_MANTENIMIENTO: no la va a encontrar el buscador ni la "
                         "va a listar el índice del grupo")
            elif _en_tabla[_t] != _g:
                reportar("ERROR", _ln,
                         f"«{_t}» se dibuja en el grupo {_g} y la tabla dice {_en_tabla[_t]}: "
                         "el índice la va a listar en un grupo y no va a estar ahí")
        for _t, _g in _en_tabla.items():
            if _t not in _en_pantalla:
                reportar("ERROR", 0,
                         f"HERRAMIENTAS_MANTENIMIENTO nombra «{_t}» y esa herramienta no se "
                         "dibuja en ningún lado: el índice promete algo que no está")


# ============ 30a) Una consulta que nombra una columna que no existe ============
# El error real: «SELECT v.marca, v.modelo FROM historial_piezas hp JOIN vehiculos v ...»
# cuando las columnas se llaman marca_auto y modelo_auto. La consulta estaba adentro de un
# try/except OperationalError que la tapaba, así que NUNCA anduvo y nadie se enteró: la fuente
# de autos «lo que este taller le puso a cada auto» no aportaba nada desde siempre. Se vio
# contando los errores que la app se traga — 254 en una sola corrida de la tarea de fondo.
# Se construye el mapa de columnas desde los CREATE TABLE y los ALTER TABLE del propio archivo,
# y después se miran las referencias «alias.columna» de cada consulta.
# Es a propósito CONSERVADOR: solo se juzga un alias cuya tabla se conoce entera, y se saltean
# las consultas con subconsultas o CTE, donde un alias puede ser una tabla armada al vuelo.
_COLS_DE_TABLA = {}
for _m in re.finditer(r'CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\n\s*\)"""', SRC, re.S):
    _tabla, _cuerpo = _m.group(1), _m.group(2)
    _cols = set()
    for _linea in _cuerpo.split(","):
        _linea = _linea.strip()
        _mm = re.match(r'(\w+)\s+(INTEGER|TEXT|REAL|BLOB|NUMERIC)', _linea, re.I)
        if _mm:
            _cols.add(_mm.group(1).lower())
    if _cols:
        _COLS_DE_TABLA.setdefault(_tabla.lower(), set()).update(_cols)
for _m in re.finditer(r'ALTER TABLE (\w+) ADD COLUMN (\w+)', SRC):
    _COLS_DE_TABLA.setdefault(_m.group(1).lower(), set()).add(_m.group(2).lower())

_SQL_LITERALES = [n.value for n in ast.walk(ARBOL)
                  if isinstance(n, ast.Constant) and isinstance(n.value, str)
                  and re.search(r'\bSELECT\b', n.value, re.I)]
for _sql in _SQL_LITERALES:
    if re.search(r'\bWITH\b|\(\s*SELECT\b', _sql, re.I):
        continue          # CTE o subconsulta: el alias puede no ser una tabla
    _alias = {}
    for _m in re.finditer(r'\b(?:FROM|JOIN)\s+(\w+)\s+(?:AS\s+)?(\w+)\b', _sql, re.I):
        _t, _a = _m.group(1).lower(), _m.group(2).lower()
        if _a in ("on", "where", "group", "order", "limit", "join", "left", "inner", "set",
                  "using", "and", "or"):
            continue
        if _t in _COLS_DE_TABLA:
            _alias[_a] = _t
    if not _alias:
        continue
    for _m in re.finditer(r'\b(\w+)\.(\w+)\b', _sql):
        _a, _col = _m.group(1).lower(), _m.group(2).lower()
        if _a not in _alias:
            continue
        if _col in _COLS_DE_TABLA[_alias[_a]] or _col == "rowid":
            continue
        reportar("ERROR", 0,
                 f"una consulta pide «{_m.group(1)}.{_m.group(2)}» y la tabla "
                 f"«{_alias[_a]}» no tiene esa columna. Si está adentro de un try/except la "
                 "consulta falla en silencio y esa parte no anda nunca")
        break


# ============ 30b) Un decorador que nombra algo definido más abajo ============
# El decorador se EVALÚA al importar el archivo, de arriba hacia abajo. Si nombra una constante
# que está definida cien líneas después, la app no arranca: NameError apenas se abre, con la
# pantalla en blanco. Pasó de verdad con @functools.lru_cache(maxsize=MAXIMO_...) puesto arriba
# de una función que estaba antes que la constante, y el auditor no lo veía: el chequeo que
# controla el orden mira las LLAMADAS al arrancar, no los decoradores.
_DEF_EN_LINEA = {}
for _n in ARBOL.body:
    if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        _DEF_EN_LINEA.setdefault(_n.name, _n.lineno)
    elif isinstance(_n, ast.Assign):
        for _t in _n.targets:
            if isinstance(_t, ast.Name):
                _DEF_EN_LINEA.setdefault(_t.id, _n.lineno)
for _n in ARBOL.body:
    if not isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        continue
    for _d in _n.decorator_list:
        for _x in ast.walk(_d):
            if not isinstance(_x, ast.Name):
                continue
            _donde = _DEF_EN_LINEA.get(_x.id)
            if _donde and _donde > _d.lineno:
                reportar("ERROR", _d.lineno,
                         f"el decorador de '{_n.name}' nombra '{_x.id}', que se define recién "
                         f"en la línea {_donde}. Los decoradores se evalúan al importar: la app "
                         "no arranca, NameError con la pantalla en blanco")


# ============ 31) Los decoradores que el paquete nucleo se come ============
# nucleo/generar.py copia el CUERPO de cada función a los módulos del paquete, y el decorador
# queda afuera. Con @st.cache_data da igual —el paquete corre sin Streamlit— pero con
# @functools.lru_cache no: la función queda sin cachear en nucleo y hace el doble de trabajo
# que en app.py, sin que nadie se entere. Pasó con separar_texto_pegado().
# El generador tiene un ajuste que se lo devuelve; esto controla que ese ajuste siga estando.
_CON_LRU = [n.name for n in ast.walk(ARBOL)
            if isinstance(n, ast.FunctionDef)
            and any("lru_cache" in ast.unparse(d) for d in n.decorator_list)]
if _CON_LRU:
    try:
        _GEN = open("nucleo/generar.py", encoding="utf-8").read()
    except OSError:
        _GEN = ""
    if _GEN:
        for _fn in _CON_LRU:
            # ¿el generador lo lleva al paquete?
            if f'"{_fn}"' not in _GEN:
                continue
            if "lru_cache" not in _GEN:
                reportar("ERROR", 0,
                         f"'{_fn}' usa @functools.lru_cache y nucleo/generar.py lo copia al "
                         "paquete sin el decorador: en nucleo va a quedar sin caché y "
                         "haciendo el doble de trabajo que en app.py")
                break


# ============ 32) Leer el archivo .db a mano estando en modo WAL ============
# La base anda en WAL: lo que se escribió desde el último checkpoint vive en el .db-wal, no
# adentro del .db. Copiar o leer el archivo crudo entrega una base vieja, y puede entregar una
# base que ni siquiera tiene las tablas — medido: 5.000 filas commiteadas, el .db crudo pesaba
# 4.096 bytes y al abrirlo daba «no such table: productos».
# Pasó en los dos sentidos: primero al restaurar (se arregló con backup()) y después se
# descubrió que el botón de bajar el backup completo seguía haciendo open(DB_PATH,"rb").
# Cualquier copia de la base se hace con la API backup() de SQLite.
for _i, _l in enumerate(LINEAS, 1):
    _limpia = _l.split("#")[0]
    if "DB_PATH" in _limpia and re.search(r"open\s*\(\s*DB_PATH", _limpia):
        reportar("ERROR", _i,
                 "lee el archivo de la base directamente estando en modo WAL: lo escrito "
                 "desde el último checkpoint está en el .db-wal y no entra en esa copia. "
                 "Usar conn.backup(destino) sobre un archivo temporal, como generar_backup_completo()")


# ============ 33) Un archivo temporal con nombre fijo ============
# La app está hecha para que la usen dos personas a la vez (una conexión por sesión). Un
# temporal con nombre fijo es de una sola persona: si los dos tocan el mismo botón, el segundo
# le borra el archivo al primero mientras SQLite lo escribe.
# Medido con el nombre fijo que tenía generar_backup_completo(), cuatro pedidos a la vez:
# fallaron los cuatro, todas las veces — «disk I/O error», «no such table: productos» y
# FileNotFoundError. Con un nombre único por llamada, los cuatro devuelven la base entera.
for _i, _l in enumerate(LINEAS, 1):
    _limpia = _l.split("#")[0]
    if "gettempdir()" in _limpia and re.search(r"gettempdir\(\)\s*,\s*[\"']", _limpia):
        reportar("ERROR", _i,
                 "arma un archivo temporal con un nombre fijo, y dos sesiones a la vez se lo "
                 "pisan entre ellas. Usar _ruta_temporal_de_backup(), que le pone un nombre "
                 "distinto a cada llamada")


# ============ 34) Una tupla desarmada que el paquete nucleo no se puede llevar ============
# nucleo/generar.py copia bloques POR NOMBRE. Una asignación de dos nombres a la vez
# —`a, b = f()`— solo se puede pedir por uno de los dos, así que la línea entera queda afuera
# o entra sin que el otro nombre exista, y el paquete revienta con un NameError al importar.
# Pasó con `_RE_FAMILIAS, _FAMILIA_DE_LA_FORMA = _armar_buscador_de_familias()`.
# Esto marca las asignaciones múltiples a nivel módulo que el generador sí lleva.
try:
    _GEN34 = open("nucleo/generar.py", encoding="utf-8").read()
except OSError:
    _GEN34 = ""
if _GEN34:
    for _n in ARBOL.body:
        if not isinstance(_n, ast.Assign):
            continue
        _destinos = [d for d in _n.targets if isinstance(d, (ast.Tuple, ast.List))]
        if not _destinos:
            continue
        _nombres = [e.id for d in _destinos for e in d.elts if isinstance(e, ast.Name)]
        if any(f'"{x}"' in _GEN34 for x in _nombres):
            reportar("ERROR", _n.lineno,
                     "asignación de varios nombres a la vez que nucleo/generar.py copia: el "
                     "generador lleva bloques por nombre y se va a llevar medio renglón. "
                     "Guardar el resultado en UN solo nombre y desarmarlo adentro de quien "
                     f"lo usa ({', '.join(_nombres)})")


# ============ 35) Preparar de verdad cada consulta contra el esquema del propio archivo =====
# El chequeo 30a compara `alias.columna` contra el mapa de columnas, y es útil, pero solo ve lo
# que está calificado. Lo que se le escapa es la columna SIN alias en una consulta con JOIN:
#     SELECT id, codigo_barras FROM productos p JOIN marcas m ON m.id = p.marca_id
# `id` está en las dos tablas, así que SQLite corta con «ambiguous column name: id». Esa
# consulta es la rama que corre cuando no se elige una lista al pegar códigos de barras en
# masa, y «— todas las listas —» es la PRIMERA opción del selector: el camino por defecto de
# esa herramienta nunca funcionó, y ni siquiera quedaba anotado, porque la excepción no la
# atrapa nadie.
#
# Así que en vez de razonar sobre el texto, se arma el esquema ejecutando los CREATE TABLE y
# ALTER TABLE que están en el propio archivo, y se PREPARA cada consulta literal con EXPLAIN.
# Lo que SQLite acepta, pasa; lo que no, es un error de verdad. No hace falta la base real.
#
# Los pedazos de SQL que se concatenan o se formatean en tiempo de ejecución no se pueden
# preparar y se saltean: dan «incomplete input» o «unrecognized token {». Medido sobre app.py:
# de 541 consultas literales, 51 son pedazos —los 51 se saltean— y el resto prepara limpio.
# Sobre el archivo con el bug adentro, este control devolvía exactamente 1 hallazgo, el bueno.
_ES_SQL = re.compile(r"^\s*(SELECT|INSERT|UPDATE|DELETE|WITH|CREATE|ALTER)\b", re.I)
_NO_SE_PUEDE_PREPARAR = ("incomplete input", "unrecognized token", "near \"{\"")
_LITERALES_SQL = [(n.lineno, n.value) for n in ast.walk(ARBOL)
                  if isinstance(n, ast.Constant) and isinstance(n.value, str)
                  and _ES_SQL.match(n.value)]
_MEM = sqlite3.connect(":memory:")
for _ln, _sql in _LITERALES_SQL:
    if _sql.strip().upper().startswith(("CREATE", "ALTER")):
        try:
            _MEM.execute(_sql)
        except sqlite3.Error:
            pass     # migraciones condicionadas, tablas temporales de un rename: no son del esquema
for _ln, _sql in _LITERALES_SQL:
    if _sql.strip().upper().startswith(("CREATE", "ALTER", "PRAGMA")):
        continue
    try:
        _MEM.execute("EXPLAIN " + _sql)
    except sqlite3.OperationalError as _err:
        _texto = str(_err)
        if any(x in _texto for x in _NO_SE_PUEDE_PREPARAR):
            continue     # es un pedazo que se completa en tiempo de ejecución
        reportar("ERROR", _ln,
                 f"SQLite no acepta esta consulta contra el esquema del propio archivo: "
                 f"«{_texto}». Una columna que está en dos tablas del JOIN hay que calificarla "
                 "con el alias, y una que no existe hay que arreglarla")
    except sqlite3.Error:
        pass


# ============ 36) El mismo nombre a nivel módulo, definido dos veces ============
# Python no se queja: la segunda asignación pisa a la primera, y todo lo que se ejecutó en el
# medio se quedó con la vieja. Anda perfecto hasta el día que alguien mueve una línea.
# Pasó de verdad: se agregó MARCAS_DE_REPUESTO (la lista de quién FABRICA la pieza) sin ver que
# ya existía MARCAS_DE_REPUESTO más abajo (el conjunto de marcas que hay que despegar de un
# texto). Las dos convivieron sin romperse solo porque la primera se usa antes de que la
# segunda la pise. Y encima nucleo/generar.py copia bloques POR NOMBRE: con el nombre repetido
# se lleva cualquiera de los dos.
_ASIGNADOS = defaultdict(list)
for _n in ARBOL.body:
    if isinstance(_n, ast.Assign):
        for _t in _n.targets:
            if isinstance(_t, ast.Name):
                _ASIGNADOS[_t.id].append(_n.lineno)
for _nombre, _lineas in _ASIGNADOS.items():
    if len(_lineas) > 1 and _nombre.isupper():
        reportar("ERROR", _lineas[-1],
                 f"«{_nombre}» se define dos veces a nivel módulo (líneas "
                 f"{', '.join(str(x) for x in _lineas)}). La segunda pisa a la primera y "
                 "nucleo/generar.py, que copia bloques por nombre, se lleva cualquiera de las "
                 "dos. Renombrar una")


# ============ 37) Contar PARES de equivalencias contando filas ============
# La tabla `equivalencias` puede tener la misma relación anotada en las dos direcciones —pasa
# seguido, para eso existe unificar_equivalencias_espejadas()—. Una consulta que sale de
# `equivalencias` y engancha `productos` DOS VECES está mirando el par, no la fila, y si no
# descarta el espejo cuenta el doble.
# No es teórico: el aviso de salud de «precios que no cierran» decía «N par(es)» contando filas,
# y precios_incoherentes_entre_equivalentes() mostraba el mismo par dos veces en la tabla, con
# las columnas dadas vuelta. Reproducido con dos productos y las dos filas: decía 2, había 1.
# Se pide SIN_CONTAR_EL_ESPEJO y no «a_id < b_id» porque lo segundo esconde los pares que solo
# están anotados al revés — se probó, y perdía uno de cada dos.
_DOS_VECES_PRODUCTOS = re.compile(
    r"FROM\s+equivalencias\s+e\b(?:.|\n)*?JOIN\s+productos\s+\w+(?:.|\n)*?"
    r"JOIN\s+productos\s+\w+", re.I)


def _texto_de_sql(nodo):
    """El SQL de un literal o de un f-string, con los huecos como «{NOMBRE}».

    Hace falta el f-string: al meter la condición en una constante, la consulta pasa a ser un
    f-string con el nombre adentro de las llaves, y ahí el nombre ya NO está en ningún
    ast.Constant —vive en un FormattedValue—, así que el control se disparaba sobre la consulta
    ya arreglada."""
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return nodo.value
    if isinstance(nodo, ast.JoinedStr):
        partes = []
        for _p in nodo.values:
            if isinstance(_p, ast.Constant) and isinstance(_p.value, str):
                partes.append(_p.value)
            elif isinstance(_p, ast.FormattedValue):
                partes.append("{" + (_p.value.id if isinstance(_p.value, ast.Name) else "?") + "}")
        return "".join(partes)
    return None


def _textos_sql(raiz):
    """Cada cadena del archivo UNA vez. Un f-string se devuelve entero y no se entra adentro:
    sus pedazos son ast.Constant y, mirados sueltos, les falta justamente el hueco."""
    pila, salida = [raiz], []
    while pila:
        _nodo = pila.pop()
        if isinstance(_nodo, ast.JoinedStr):
            salida.append((_nodo.lineno, _texto_de_sql(_nodo)))
            continue
        if isinstance(_nodo, ast.Constant) and isinstance(_nodo.value, str):
            salida.append((_nodo.lineno, _nodo.value))
            continue
        pila.extend(ast.iter_child_nodes(_nodo))
    return salida


for _ln, _sql in _textos_sql(ARBOL):
    if not _sql:
        continue
    if not _DOS_VECES_PRODUCTOS.search(_sql):
        continue
    if "SIN_CONTAR_EL_ESPEJO" in _sql or "producto_a_id < " in _sql:
        continue
    # La salida: una consulta que de verdad mira la FILA y no el par lo dice adentro del SQL.
    # recalcular_confianzas() es el caso — escribe una confianza por fila, y si la relación
    # está espejada hay que puntuar las dos.
    if "FILA Y NO PAR" in _sql:
        continue
    reportar("REVISAR", _ln,
             "esta consulta sale de «equivalencias» y engancha «productos» dos veces: está "
             "mirando un PAR. Si la tabla tiene la relación anotada de ida y de vuelta, cuenta "
             "el doble. Meter {SIN_CONTAR_EL_ESPEJO} en el WHERE, o decir por qué no hace falta")


# ============ 38) Una función que confirma, llamada adentro de transaccion() ============
# transaccion() promete «todo o nada», pero un conn.commit() adentro del bloque la cierra antes
# de tiempo, y lo que viene después ya no se deshace si falla. transaccion() lo tolera a
# propósito —no revienta al final—, así que el error no se ve: se ve la base a medio hacer.
# Pasó de verdad: eliminar_marca_con_papelera() llamaba a mover_a_papelera(), que hace commit,
# adentro de su transacción. Probado cortando justo antes del DELETE: la marca seguía en la base
# Y quedaba una copia en la papelera. Este control, pasado por el archivo de ese momento,
# devuelve exactamente ese caso y ningún otro.
# Mira las llamadas DIRECTAS a funciones de módulo que tienen un .commit() adentro.
_CON_COMMIT = {n.name for n in ARBOL.body
               if isinstance(n, ast.FunctionDef)
               and any(isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute)
                       and x.func.attr == "commit" for x in ast.walk(n))}
for _n in ast.walk(ARBOL):
    if not isinstance(_n, ast.With):
        continue
    if not any(isinstance(_i.context_expr, ast.Call)
               and getattr(_i.context_expr.func, "id", "") == "transaccion" for _i in _n.items):
        continue
    for _m in ast.walk(_n):
        if not isinstance(_m, ast.Call):
            continue
        if isinstance(_m.func, ast.Name) and _m.func.id in _CON_COMMIT:
            reportar("ERROR", _m.lineno,
                     f"«{_m.func.id}()» hace conn.commit() y se llama adentro de "
                     "transaccion(): el commit cierra la transacción antes de tiempo y lo que "
                     "sigue ya no es «todo o nada». Usar una variante que no confirme")
        elif isinstance(_m.func, ast.Attribute) and _m.func.attr == "commit":
            reportar("ERROR", _m.lineno,
                     "conn.commit() adentro de transaccion(): cierra la transacción antes de "
                     "tiempo. El commit lo hace transaccion() al salir del bloque")


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

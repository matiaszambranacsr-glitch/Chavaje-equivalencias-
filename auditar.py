"""Auditoría estática de app.py. Busca los errores que Streamlit y SQLite solo muestran
en ejecución, cuando ya es tarde."""
import ast
import re
import sys
from collections import defaultdict, Counter

SRC = open("app.py", encoding="utf-8").read()
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
columnas = defaultdict(set)
for m in re.finditer(r'CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\n\s*\)"""', SRC, re.S):
    tabla, cuerpo = m.group(1), m.group(2)
    for linea in cuerpo.split("\n"):
        t = linea.strip().strip(",")
        if not t or t.upper().startswith(("PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "CONSTRAINT")):
            continue
        col = t.split()[0].strip('"')
        if col.isidentifier():
            columnas[tabla].add(col)
for m in re.finditer(r'ALTER TABLE (\w+) ADD COLUMN (\w+)', SRC):
    columnas[m.group(1)].add(m.group(2))

# ============ 8. except silenciosos en funciones que escriben ============
for n in ast.walk(ARBOL):
    if isinstance(n, ast.ExceptHandler):
        cuerpo_texto = "".join(LINEAS[n.lineno - 1:(n.end_lineno or n.lineno)])
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

# ============ 8e. Contenedores anidados que Streamlit prohíbe ============
# st.expander dentro de otro expander tira StreamlitAPIException y CORTA el renderizado ahí:
# la mitad de abajo de la pantalla no se dibuja. Es un error que no se ve leyendo el código
# porque los dos expanders pueden estar a 200 líneas de distancia.
def _es_contenedor(item, nombre):
    return (isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Attribute)
            and item.context_expr.func.attr == nombre)


class _BuscaAnidados(ast.NodeVisitor):
    def __init__(self, nombre):
        self.nombre = nombre
        self.pila = []

    def visit_With(self, nodo):
        hay = any(_es_contenedor(i, self.nombre) for i in nodo.items)
        if hay and self.pila:
            reportar("ERROR", nodo.lineno,
                     f"st.{self.nombre} dentro de otro st.{self.nombre} "
                     f"(el de afuera está en L{self.pila[-1]}) — Streamlit lo prohíbe y corta "
                     "el renderizado")
        if hay:
            self.pila.append(nodo.lineno)
        self.generic_visit(nodo)
        if hay:
            self.pila.pop()


_BuscaAnidados("expander").visit(ARBOL)

# NOTA sobre lo que esta auditoría NO puede detectar
# Un bloque copiado de un contexto a otro —donde las variables se llaman distinto— compila
# perfecto y revienta con NameError recién al abrir esa sección. Intenté un chequeo de ámbitos
# para agarrarlo y da falsos positivos: en un archivo con este nivel de anidamiento no se puede
# decidir con certeza qué nombre es visible dónde sin un analizador completo. Una auditoría que
# marca cosas que están bien se deja de mirar, así que prefiero no tenerlo.
# Al copiar un bloque de una sección a otra, revisar a mano los nombres de las variables.

# ============ 8f. Funciones usadas antes de estar definidas ============
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
# Se cuentan también las CLASES. Sin esto, definir una clase y usarla se reportaba como
# "nombre usado y nunca definido": un falso positivo, y esos son los que hacen que alguien
# deje de mirar la auditoría.
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
print(f"app.py — {len(LINEAS)} líneas")
print(f"ERROR: {cuenta['ERROR']}   REVISAR: {cuenta['REVISAR']}   AVISO: {cuenta['AVISO']}\n")
for nivel, linea, texto in problemas:
    ubic = f"L{linea}" if linea else "  "
    print(f"[{nivel:7}] {ubic:>7}  {texto}")
    if linea and nivel == "ERROR":
        print(f"                    {LINEAS[linea - 1].strip()[:95]}")
sys.exit(1 if cuenta["ERROR"] else 0)

"""«⏱️ Los tiempos de la página»: cada plazo de la app, a elección del administrador.

Uso:
    python3 pruebas/pruebas_de_los_tiempos.py

Por qué: lo pidió el dueño («lo de los pedidos, en vez de 5 días que sean 7, y así con todo»).
Esto controla que cada tiempo de la lista exista y se use, que ningún tiempo nuevo del código
quede afuera sin decir por qué, que lo elegido se aplique de verdad (en la lógica, en la
campanita y en el asistente), que sobreviva a un reinicio, que no se pueda poner fuera de rango
ni con el 🔴 antes que el 🟡, que «Todos como venían» vuelva a lo de siempre y que solo el
administrador lo cambie (ver «LOS TIEMPOS QUE ELIGE EL ADMINISTRADOR» en logica/interfaz.py).

Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import glob
import json
import os
import re
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Los tiempos del código que NO elige el administrador, y por qué. Uno nuevo que no esté acá ni
# en la lista de la app hace fallar la prueba: hay que decidir si es del negocio (va a la lista)
# o técnico (va acá, con el motivo).
TIEMPOS_TECNICOS = {
    "SEGUNDOS_ENTRE_REVISIONES_A_MANO": "cada cuánto mira la tanda de fondo",
    "HORAS_ENTRE_VERIFICACIONES": "verificación de links de afuera",
    "HORAS_PARA_REINTENTAR_LA_VERIFICACION": "verificación de links de afuera",
    "SEGUNDOS_ANTES_DE_LA_PRIMERA_COPIA": "arranque del vigía de la copia",
    "SEGUNDOS_ENTRE_MIRADAS": "el vigía de la copia",
    "MINUTOS_DE_FRENO_EN_RECUPERACION": "modo recuperación",
    "DIAS_DE_LA_SEMANA_DEL_RESUMEN": "una semana es una semana",
    "MINUTOS_ENTRE_REVISIONES_DE_LO_APROBADO": "tanda de fondo",
    "HORAS_QUE_DURA_EL_ANALISIS": "memoria de un cálculo",
    "SEGUNDOS_PARA_ARCA": "cuánto se espera a ARCA",
    "DIAS_ENTRE_ACTUALIZACIONES_DEL_CHAS": "fuente de afuera",
    "DIAS_ENTRE_ACTUALIZACIONES_DEL_PARQUE": "fuente de afuera",
    "MINUTOS_MAXIMOS_DEL_PARQUE": "fuente de afuera",
    "DIAS_ENTRE_ACTUALIZACIONES_DEL_TRANSPORTE": "fuente de afuera",
    "HORAS_DE_LO_TRAIDO_DE_LA_NHTSA": "fuente de afuera",
    "MINUTOS_SIN_REINTENTAR_LA_NHTSA": "fuente de afuera",
    "MINUTOS_QUE_SE_RECUERDA_UNA_RESPUESTA": "memoria de un cálculo",
    "MINUTOS_PARA_REINTENTAR_UNA_CADENA": "catálogos de proveedores",
    "MINUTOS_DE_SESION_DE_PORTAL": "catálogos de proveedores",
    "MINUTOS_VIDA_SESION": "catálogos de proveedores",
    "MINUTOS_DE_PAGINA_EN_MEMORIA": "catálogos de proveedores",
    "MINUTOS_DE_DESCANSO": "catálogos de proveedores",
    "MINUTOS_DE_DESCANSO_SI_FALLA": "catálogos de proveedores",
    "MINUTOS_DE_DESCANSO_MAXIMO": "catálogos de proveedores",
    "SEGUNDOS_DE_PREFERENCIA": "catálogos de proveedores",
    "SEGUNDOS_DEL_CRUCE_POR_AUTO": "catálogos de proveedores",
    "DIAS_DE_CONTEOS": "comparación interna de la salud",
    "HORAS_CONTEXTO_FRESCO": "fuente de afuera",
    "MINUTOS_ANTES_DE_REINTENTAR": "fuente de afuera",
    "HORAS_DE_LAS_TASAS": "fuente de afuera (BCRA)",
}
_RE_TIEMPO_DEL_CODIGO = re.compile(
    r"^((?:DIAS|HORAS|MINUTOS|SEGUNDOS)_[A-Z_]+|[A-Z][A-Z_]*_(?:DIAS|HORAS|MINUTOS|SEGUNDOS))"
    r" = [\d(]", re.M)


def probar():
    from streamlit.testing.v1 import AppTest
    fallas = []

    def esperar(que, dio, se_esperaba):
        if dio != se_esperaba:
            fallas.append(f"{que}: dio {dio!r}, se esperaba {se_esperaba!r}")

    def cierto(que, ok, detalle=""):
        if not ok:
            fallas.append(f"{que} {str(detalle)[:200]}")

    at = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
    at.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
    at.run()
    at.text_input(key="login_inicial_nombre").set_value("duenio")
    at.text_input(key="login_inicial_clave").set_value("clave-duenio-1")
    [b for b in at.button if "Ingresar con contraseña" in b.label][0].click().run()
    ns = sys.modules["logica"].todo_lo_de_la_logica()
    c, conn = ns["c"], ns["conn"]
    lista = ns["TIEMPOS_QUE_ELIGE_EL_ADMINISTRADOR"]
    ahora, de_siempre = ns["tiempo_de_ahora"], ns["tiempo_de_siempre"]

    # 1. CADA TIEMPO DE LA LISTA EXISTE, ES UN NÚMERO ENTERO EN SU RANGO, Y SE USA.
    fuente = {ruta: open(ruta, encoding="utf-8").read()
              for ruta in glob.glob(os.path.join(RAIZ, "logica", "*.py"))
              + glob.glob(os.path.join(RAIZ, "pantallas", "*.py")) + [os.path.join(RAIZ, "app.py")]}
    claves = [t[1] for t in lista]
    esperar("ningún tiempo repetido", len(claves), len(set(claves)))
    for grupo, clave, que, unidad, minimo, maximo in lista:
        try:
            valor = de_siempre(clave)
        except KeyError:
            fallas.append(f"«{clave}» no existe en la app")
            continue
        cierto(f"«{clave}»: entero entre {minimo} y {maximo}",
               isinstance(valor, int) and minimo <= valor <= maximo, valor)
        cierto(f"«{clave}»: con su unidad", unidad in ("segundos", "minutos", "horas", "días"),
               unidad)
        nombre = clave.split("[")[0]
        usos = sum(len(re.findall(rf"\b{nombre}\b", texto)) for texto in fuente.values())
        # La definición y el renglón de la lista no cuentan.
        cierto(f"«{clave}» se usa en algún lado", usos >= 3, usos)

    # 2. NINGÚN TIEMPO DEL CÓDIGO QUEDA AFUERA SIN DECIR POR QUÉ.
    del_codigo = {m.group(1) for ruta, texto in fuente.items() if "/logica/" in ruta
                  for m in _RE_TIEMPO_DEL_CODIGO.finditer(texto)}
    elegibles = {k.split("[")[0] for k in claves}
    esperar("tiempos del código que no están ni en la lista ni entre los técnicos",
            sorted(del_codigo - elegibles - set(TIEMPOS_TECNICOS)), [])
    esperar("técnicos que ya no existen (sacarlos de la prueba)",
            sorted(set(TIEMPOS_TECNICOS) - del_codigo), [])

    # 3. LO ELEGIDO SE APLICA: un pedido de hace 6 días está atrasado con 5, y no con 7.
    c.execute("INSERT OR IGNORE INTO marcas (nombre, tipo) VALUES ('MARCA TIEMPO', 'PROVEEDOR')")
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio) "
              "SELECT 'T1', 'T1', 'FILTRO', id, 100 FROM marcas WHERE nombre = 'MARCA TIEMPO'")
    t1 = c.lastrowid
    c.execute("INSERT INTO pedidos_a_proveedores (producto_id, cantidad, pedido_en) "
              "VALUES (?, 1, datetime('now', '-6 days'))", (t1,))
    conn.commit()
    _atrasado = lambda: [x["Atrasado"] for x in ns["pedidos_sin_llegar"]()]  # noqa: E731
    esperar("con los 5 días de siempre, atrasado", _atrasado(), [True])
    _cambio = ns["guardar_los_tiempos"]({"DIAS_PARA_RECLAMAR_EL_PEDIDO": 7})
    esperar("lo que cambió, dicho", _cambio,
            ["Un pedido al proveedor está atrasado (⏰ y campanita) a los 7 días"])
    esperar("con 7, todavía no", _atrasado(), [False])
    esperar("y la campanita no lo dice",
            [p["titulo"] for p in ns["diagnostico_de_salud"]() if "sin llegar" in p["titulo"]], [])
    _resp = ns["responder_del_asistente"](
        "no llego lo que le pedi al proveedor",
        {"visibles": list(ns["ORDEN_DE_LAS_PAGINAS"]), "pagina": ns["PAGINAS"][0],
         "nivel": "admin"})
    cierto("el asistente dice los 7 días, sin dejar la marca a la vista",
           "en 7 días" in _resp["texto"] and "{" not in _resp["texto"], _resp["texto"])
    esperar("se guarda solo lo distinto de lo de siempre",
            json.loads(ns["obtener_config"]("tiempos_elegidos", "{}")),
            {"DIAS_PARA_RECLAMAR_EL_PEDIDO": 7})
    esperar("queda anotado en el registro de cambios",
            [tuple(f) for f in c.execute(
                "SELECT entidad_id, antes, despues FROM registro_de_cambios "
                "WHERE accion = 'cambió un tiempo de la página'")],
            [("DIAS_PARA_RECLAMAR_EL_PEDIDO", "5", "7")])

    # 4. UNA PARTE DE UN PAR (el 🟡 del depósito) y el orden entre los dos.
    ns["guardar_los_tiempos"]({"MINUTOS_PARA_AVISAR[0]": 15})
    # (ns es la foto de los nombres de cuando se armó: lo de ahora está en el módulo).
    esperar("el 🟡 a los 15, el 🔴 como estaba", sys.modules["logica"].MINUTOS_PARA_AVISAR,
            (15, 20))
    for nuevos, que in (({"MINUTOS_PARA_AVISAR[0]": 25}, "el 🟡 después del 🔴"),
                        ({"MINUTOS_PARA_AVISAR[1]": 15}, "el 🔴 igual al 🟡"),
                        ({"DIAS_PARA_RECLAMAR_EL_PEDIDO": 0}, "cero días"),
                        ({"DIAS_PARA_RECLAMAR_EL_PEDIDO": 91}, "más que el máximo"),
                        ({"DIAS_QUE_AVISA_LO_QUE_SE_TERMINA": 20}, "la campanita más que la lista")):
        try:
            ns["guardar_los_tiempos"](nuevos)
            fallas.append(f"se pudo guardar {que}")
        except ValueError:
            pass
    esperar("lo que no se pudo guardar no cambió nada",
            (sys.modules["logica"].MINUTOS_PARA_AVISAR, ahora("DIAS_PARA_RECLAMAR_EL_PEDIDO")),
            ((15, 20), 7))

    # 5. SOBREVIVE A UN REINICIO: con los de siempre puestos a mano (como al arrancar), el
    # toque siguiente de la app vuelve a poner los elegidos. Y lo guardado a mano fuera de
    # rango no cuenta.
    g = ns["guardar_los_tiempos"].__globals__
    g["DIAS_PARA_RECLAMAR_EL_PEDIDO"], g["MINUTOS_PARA_AVISAR"] = 5, (10, 20)
    at.run()
    esperar("después de reiniciar, lo elegido",
            (g["DIAS_PARA_RECLAMAR_EL_PEDIDO"], g["MINUTOS_PARA_AVISAR"]), (7, (15, 20)))
    ns["guardar_config"]("tiempos_elegidos", json.dumps(
        {"DIAS_PARA_RECLAMAR_EL_PEDIDO": 7, "MINUTOS_PARA_AVISAR[0]": 15,
         "DIAS_EN_LA_PAPELERA": 0, "HORAS_QUE_VALE_UN_PERMISO": "mucho", "NO_EXISTE": 3}))
    esperar("lo guardado que no sirve no cuenta", ns["tiempos_elegidos"](),
            {"DIAS_PARA_RECLAMAR_EL_PEDIDO": 7, "MINUTOS_PARA_AVISAR[0]": 15})

    # 6. LA PAPELERA, con su tiempo: lo de hace 10 días queda con 30, y no con 5.
    for dias in (10, 40):
        c.execute("INSERT INTO papelera (tipo, datos_json, eliminado_en) "
                  "VALUES ('prueba', '{}', datetime('now', ?))", (f"-{dias} days",))
    conn.commit()
    esperar("la papelera con los 30 de siempre", ns["vaciar_papelera_antigua"](), 1)
    ns["guardar_los_tiempos"]({"DIAS_EN_LA_PAPELERA": 5})
    esperar("y con 5", ns["vaciar_papelera_antigua"](), 1)

    # 7. EN LA PANTALLA: 👥 Usuarios → «⏱️ Los tiempos de la página», cambiar uno y guardar.
    at.session_state["pagina_actual"] = "🗂️ Administrar"
    at.session_state["sub_admin"] = "👥 Usuarios"
    at.session_state["exp_tiempos_de_la_pagina"] = True
    at.run()
    _caja = [x for x in at.number_input
             if (x.key or "").startswith("tiempo_DIAS_PARA_RECLAMAR_EL_PEDIDO_")]
    cierto("la caja del tiempo del pedido, con lo elegido y la marca de cambiado",
           _caja and _caja[0].value == 7 and "✏️" in _caja[0].label,
           [(x.key, x.value, x.label) for x in _caja])
    esperar("una caja por tiempo", len([x for x in at.number_input
                                       if (x.key or "").startswith("tiempo_")]), len(lista))
    if _caja:
        _caja[0].set_value(9)
        [b for b in at.button if "Guardar los tiempos" in b.label][0].click().run()
        esperar("guardado desde la pantalla", ahora("DIAS_PARA_RECLAMAR_EL_PEDIDO"), 9)
        cierto("y lo dice", any("Guardado" in str(x.value) for x in at.success),
               [str(x.value)[:80] for x in at.success])
        _caja = [x for x in at.number_input
                 if (x.key or "").startswith("tiempo_DIAS_PARA_RECLAMAR_EL_PEDIDO_")]
        esperar("la caja muestra lo nuevo", [x.value for x in _caja], [9])
    _como_venian = [b for b in at.button if b.key == "tiempos_como_venian"]
    cierto("«↩️ Todos como venían», con algo cambiado", _como_venian)
    if _como_venian:
        _como_venian[0].click().run()
        esperar("todos como venían",
                [t[1] for t in lista if ahora(t[1]) != de_siempre(t[1])], [])
        esperar("y no queda nada guardado",
                json.loads(ns["obtener_config"]("tiempos_elegidos", "{}")), {})
        cierto("y ya no está el botón", not [b for b in at.button
                                             if b.key == "tiempos_como_venian"])

    # 8. SOLO EL ADMINISTRADOR los cambia.
    _antes = (g["_nivel_de_quien_esta_adentro"], g["hay_claves_configuradas"])
    try:
        g["hay_claves_configuradas"] = lambda: True
        for nivel in ("", "mecanico", "operador"):
            g["_nivel_de_quien_esta_adentro"] = lambda n=nivel: n
            try:
                ns["guardar_los_tiempos"]({"DIAS_PARA_RECLAMAR_EL_PEDIDO": 8})
                fallas.append(f"«{nivel or 'invitado'}» pudo cambiar los tiempos")
            except PermissionError:
                pass
    finally:
        g["_nivel_de_quien_esta_adentro"], g["hay_claves_configuradas"] = _antes
    esperar("y nadie más lo cambió", ahora("DIAS_PARA_RECLAMAR_EL_PEDIDO"), 5)
    fallas += [f"se rompió: {e.value}" for e in at.exception][:2]
    return fallas


def main():
    os.environ["EQUIVALENCIAS_SIN_TAREAS_DE_FONDO"] = "1"
    carpeta = tempfile.mkdtemp(prefix="pruebas_tiempos_")
    os.chdir(carpeta)
    sys.path.insert(0, RAIZ)
    try:
        fallas = probar()
        for f in fallas:
            print("   ✗", f[:300])
        print("✅ tiempos: cada uno existe y se usa, se aplica, sobrevive al reinicio y solo lo "
              "cambia el administrador" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(RAIZ)
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

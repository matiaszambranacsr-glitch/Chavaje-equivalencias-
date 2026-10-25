"""Todas las pantallas y solapas se dibujan sin errores, para el administrador, un operador y
quien entra sin contraseña (AppTest); y sin sesión la barra tiene solo las secciones abiertas.

Uso:
    python3 pruebas/pruebas_de_las_pantallas.py

Antes este recorrido se armaba a mano en cada revisión, fuera del repositorio. Un error que
corta una pantalla poco usada (una solapa de Estadísticas, un grupo de Mantenimiento) no lo
agarraba ninguna otra prueba: cada una mira lo suyo. Dice además cuáles tardaron más.

Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import os
import shutil
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def probar():
    from streamlit.testing.v1 import AppTest
    fallas, tiempos = [], []

    at = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
    at.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
    at.run()
    ns = sys.modules["logica"].todo_lo_de_la_logica()
    ns["crear_usuario"]("ana", "clave-ana-1", "operador")

    def entrar(clave):
        at.text_input(key="login_inicial_clave").set_value(clave)
        [b for b in at.button if "Ingresar con contraseña" in b.label][0].click().run()

    def mirar(quien, donde):
        inicio = time.time()
        at.run()
        tiempos.append((time.time() - inicio, f"{quien}: {donde}"))
        for e in at.exception:
            fallas.append(f"{quien}: {donde}: {e.value[:200]}")

    def recorrer(quien):
        # Las de la barra de cada uno: sin sesión, solo las abiertas (ver PAGINAS_ABIERTAS).
        for pagina in at.radio(key="pagina_actual").options:
            at.session_state["pagina_actual"] = pagina
            if pagina not in ns["SOLAPAS_DE_LA_PAGINA"]:
                mirar(quien, pagina)
                continue
            solapas, clave = ns["SOLAPAS_DE_LA_PAGINA"][pagina]
            for solapa in solapas:
                at.session_state[clave] = solapa
                if solapa == ns["SUB_ADMIN"][4]:            # 🧹 Mantenimiento, por grupo
                    for grupo in ns["GRUPOS_MANTENIMIENTO"]:
                        at.session_state["sub_mantenimiento"] = grupo
                        mirar(quien, f"{pagina} → {solapa} → {grupo}")
                else:
                    mirar(quien, f"{pagina} → {solapa}")

    if at.radio(key="pagina_actual").options != ns["PAGINAS_ABIERTAS"]:
        fallas.append(f"sin sesión, la barra: {at.radio(key='pagina_actual').options}")
    # Y en una búsqueda con resultados, nada de lo del mostrador: ni apagado ni con candado.
    c, conn = ns["c"], ns["conn"]
    ns["guardar_config"]("whatsapp_del_negocio", "5491145678901")
    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('PRUEBA', 'PROVEEDOR')")
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio, "
              "stock) VALUES ('F100', 'F100', 'FILTRO DE ACEITE', ?, 1000, 3)", (c.lastrowid,))
    conn.commit()
    at.session_state["pagina_actual"] = ns["PAGINAS"][0]
    at.run()
    at.text_input(key="busqueda_input").set_value("F100")
    [b for b in at.button if "Buscar equivalencias" in b.label][0].click().run()
    del_mostrador = [b.label for b in at.button
                     if any(x in b.label for x in ("Se llevó", "Reponer", "Apartar", "Pedir al"))]
    con_candado = [x.value for x in at.caption if x.value == ns["TEXTO_SOLO_MIRAR"]]
    if del_mostrador or con_candado or not any("F100" in m.value for m in at.markdown):
        fallas.append(f"sin sesión, en el buscador: {del_mostrador} {con_candado}")

    def consultar():
        """Los «📲 Consultar por WhatsApp» que hay en la pantalla: [(rótulo, link)]."""
        return [(e.proto.label, e.proto.url) for e in at.get("link_button")
                if "Consultar por WhatsApp" in e.proto.label]
    # Sin sesión, preguntarle al negocio por WhatsApp, con lo que buscó ya escrito; y si no
    # hay nada con ese código, también.
    _wa = consultar()
    if len(_wa) != 1 or "wa.me/5491145678901" not in _wa[0][1] or "F100" not in _wa[0][1]:
        fallas.append(f"sin sesión, consultar por WhatsApp: {_wa}")
    at.text_input(key="busqueda_input").set_value("ZZ999")
    [b for b in at.button if "Buscar equivalencias" in b.label][0].click().run()
    if len(consultar()) != 1:
        fallas.append(f"sin sesión y sin resultados, consultar por WhatsApp: {consultar()}")
    # Un error de tipeo: el código que se escribe casi igual se ofrece como botón, y tocarlo
    # lo busca (ver codigos_por_tipeo()).
    at.text_input(key="busqueda_input").set_value("F101")
    [b for b in at.button if "Buscar equivalencias" in b.label][0].click().run()
    _tipeo = [b for b in at.button if (b.key or "").startswith("tipeo_F101_")]
    if [b.label for b in _tipeo] != ["🔎 F100"]:
        fallas.append(f"el código casi igual, como botón: {[b.label for b in _tipeo]}")
    else:
        _tipeo[0].click().run()
        if not any("F100" in str(m.value) for m in list(at.markdown) + list(at.caption)):
            fallas.append("tocar el código casi igual no lo busca")
    recorrer("sin contraseña")
    entrar("clave-ana-1")
    if len(at.radio(key="pagina_actual").options) != len(ns["PAGINAS"]):
        fallas.append("con sesión, la barra no tiene todas las secciones")
    at.session_state["pagina_actual"] = ns["PAGINAS"][0]
    at.run()
    at.text_input(key="busqueda_input").set_value("F100")
    [b for b in at.button if "Buscar equivalencias" in b.label][0].click().run()
    if consultar():
        fallas.append("con sesión no hace falta «Consultar por WhatsApp»")
    # El presupuesto se manda derecho por WhatsApp, con lo que tiene y el total.
    _f100 = c.execute("SELECT id FROM productos WHERE codigo_clean = 'F100'").fetchone()[0]
    at.session_state["carrito"] = {_f100: {"codigo": "F100", "marca": "PRUEBA", "descripcion": "",
                                           "precio": 1000, "cantidad": 2}}
    at.run()
    _presu = [e.proto.url for e in at.get("link_button")
              if e.proto.label == "📲 Mandar el presupuesto por WhatsApp"]
    if len(_presu) != 1 or "F100" not in _presu[0] or "TOTAL" not in _presu[0]:
        fallas.append(f"el presupuesto por WhatsApp: {_presu}")
    at.session_state["carrito"] = {}
    recorrer("operador")
    [b for b in at.button if b.label == "Salir"][0].click().run()
    entrar("clave-duenio-1")
    recorrer("administrador")
    tiempos.sort(reverse=True)
    return fallas, len(tiempos), tiempos[:3]


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_pantallas_")
    os.chdir(carpeta)
    sys.path.insert(0, RAIZ)
    try:
        fallas, cuantas, lentas = probar()
        for f in fallas:
            print("   ✗", f)
        print(f"✅ pantallas: las {cuantas} en verde (las más lentas: "
              + ", ".join(f"{d} {s:.1f} s" for s, d in lentas) + ")"
              if not fallas else f"{len(fallas)} falla(s) en {cuantas} pantallas")
        return 1 if fallas else 0
    finally:
        os.chdir(RAIZ)
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

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
import threading
import time
from collections import Counter

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Muestreo:
    """Con --base, dónde se va el tiempo de cada pantalla: cada 20 ms se mira qué renglón del
    código de la app está corriendo el guion (el más adentro de logica/ o pantallas/). La
    medición decía «🧾 Ventas 9,0 s» y no por qué: había que perfilar a mano, y aislada tardaba
    0,1 s. Ahora cada lenta dice su renglón."""
    def __init__(self):
        self.cuenta, self.prendido = Counter(), "--base" in sys.argv
        if self.prendido:
            threading.Thread(target=self._mirar, daemon=True).start()

    def _mirar(self):
        propio = threading.get_ident()
        while True:
            for hilo, marco in sys._current_frames().items():
                if hilo == propio:
                    continue
                while marco and not marco.f_code.co_filename.startswith(
                        (os.path.join(RAIZ, "logica"), os.path.join(RAIZ, "pantallas"), "<")):
                    marco = marco.f_back
                if marco:
                    self.cuenta[f"{os.path.basename(marco.f_code.co_filename)}:"
                                f"{marco.f_code.co_name}:{marco.f_lineno}"] += 1
            time.sleep(0.02)

    def donde(self):
        """El renglón que más se vio desde la última vez, y vuelve a contar."""
        lo_mas = self.cuenta.most_common(1)
        self.cuenta.clear()
        return f" [{lo_mas[0][0]}]" if lo_mas else ""


def probar():
    from streamlit.testing.v1 import AppTest
    fallas, tiempos, abiertos = [], [], set()
    muestreo = Muestreo()

    at = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
    at.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
    at.run()
    ns = sys.modules["logica"].todo_lo_de_la_logica()
    # Con --base, la copia puede tener ya esa contraseña (de una medición anterior).
    clave_ana = ("clave-ana-1" if "--base" not in sys.argv
                 else f"clave-medir-{os.urandom(4).hex()}")
    ns["crear_usuario"](f"ana{clave_ana[-4:]}", clave_ana, "operador")

    def entrar(clave):
        at.text_input(key="login_inicial_clave").set_value(clave)
        [b for b in at.button if "Ingresar con contraseña" in b.label][0].click().run()

    def mirar(quien, donde):
        muestreo.donde()
        inicio = time.time()
        at.run()
        tiempos.append((time.time() - inicio, f"{quien}: {donde}{muestreo.donde()}"))
        for e in at.exception:
            fallas.append(f"{quien}: {donde}: {e.value[:200]}")
        # Lo de adentro de un desplegable perezoso (on_change="rerun") no corre mientras está
        # cerrado: se abren todos y se mira otra vez, para que no quede código sin recorrer.
        # Se reconocen porque guardan si están abiertos en su clave («exp_…»), en False.
        cerrados = [k for k in at.session_state
                    if str(k).startswith("exp_") and at.session_state[k] is False]
        if cerrados:
            for k in cerrados:
                at.session_state[k] = True
            at.run()
            abiertos.update(cerrados)
            for e in at.exception:
                fallas.append(f"{quien}: {donde} (con lo plegado abierto): {e.value[:200]}")
            for k in cerrados:
                at.session_state[k] = False

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
    # Con la ficha del proveedor y un catálogo cargados, para ver que sin sesión no salen. Y
    # una búsqueda de otro visitante, para ver que no se le muestra a este.
    # OR IGNORE y el id buscado: con --base la copia puede tener ya una marca PRUEBA.
    c.execute("INSERT OR IGNORE INTO marcas (nombre, tipo, url_ficha_template) VALUES "
              "('PRUEBA', 'PROVEEDOR', 'https://proveedor.example/{codigo}')")
    _marca_prueba = c.execute("SELECT id FROM marcas WHERE nombre = 'PRUEBA'").fetchone()[0]
    c.execute("INSERT INTO catalogos_externos (nombre, url) VALUES "
              "('Catálogo de prueba', 'https://catalogo.example/?q={codigo}')")
    c.execute("INSERT INTO historial_busquedas (termino, usuario) VALUES ('OTRO777', 'Invitado')")
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio, "
              "stock) VALUES ('F100', 'F100', 'FILTRO DE ACEITE', ?, 1000, 3)", (_marca_prueba,))
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

    def del_proveedor():
        """Lo que le dice al que mira a quién le compra el negocio: [rótulos]."""
        return ([e.proto.label for e in at.get("link_button")
                 if "sitio del proveedor" in e.proto.label]
                + [x.value for x in at.caption if "Buscar este código también en" in x.value])
    if del_proveedor():
        fallas.append(f"sin sesión, los links al proveedor: {del_proveedor()}")
    _recientes = [b.label for b in at.button if (b.key or "").startswith("sugerencia_hist_")]
    if "OTRO777" in _recientes or "F100" not in _recientes:
        fallas.append(f"sin sesión, las búsquedas recientes de esta visita: {_recientes}")

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
    # Con --base, la base real tiene otros códigos parecidos a F101: alcanza con que F100 esté.
    if ([b.label for b in _tipeo] != ["🔎 F100"] if "--base" not in sys.argv
            else "🔎 F100" not in [b.label for b in _tipeo]):
        fallas.append(f"el código casi igual, como botón: {[b.label for b in _tipeo]}")
    else:
        _tipeo[0].click().run()
        if not any("F100" in str(m.value) for m in list(at.markdown) + list(at.caption)):
            fallas.append("tocar el código casi igual no lo busca")
    recorrer("sin contraseña")
    entrar(clave_ana)
    if len(at.radio(key="pagina_actual").options) != len(ns["PAGINAS"]):
        fallas.append("con sesión, la barra no tiene todas las secciones")
    at.session_state["pagina_actual"] = ns["PAGINAS"][0]
    at.run()
    at.text_input(key="busqueda_input").set_value("F100")
    [b for b in at.button if "Buscar equivalencias" in b.label][0].click().run()
    if consultar():
        fallas.append("con sesión no hace falta «Consultar por WhatsApp»")
    if not del_proveedor():
        fallas.append("con sesión tienen que estar los links al proveedor")
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
    if len(abiertos) < 5:
        fallas.append(f"se abrieron pocos desplegables perezosos: {sorted(abiertos)}")
    return fallas, len(tiempos), tiempos[:10 if "--base" in sys.argv else 3]


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_pantallas_")
    # Con --base, una copia de la base real: para ver cuáles son las lentas de verdad (con la
    # base chica de la prueba todas tardan poco). Sin la tarea de fondo, que con una base
    # recién copiada se pone a repuntuar todo y ensucia los tiempos.
    if "--base" in sys.argv:
        shutil.copy(os.path.abspath(sys.argv[sys.argv.index("--base") + 1]),
                    os.path.join(carpeta, "equivalencias_app.db"))
        os.environ["EQUIVALENCIAS_SIN_TAREAS_DE_FONDO"] = "1"
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

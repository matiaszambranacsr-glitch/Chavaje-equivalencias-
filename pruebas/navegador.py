"""Lo que corre en el navegador y las otras pruebas no ven: con la app de verdad y un Chromium.

Uso:
    python3 pruebas/navegador.py [--python <el Python que tiene Streamlit>]

El JavaScript de AYUDAS_DEL_NAVEGADOR (logica/interfaz.py) no lo corre AppTest: el cursor en la
caja de búsqueda al entrar a cada pantalla, F2, el menú del click derecho y los textos de
Streamlit pasados al castellano se probaban a mano con un navegador, y si un cambio los rompía
nadie se enteraba (estaba en «Sin prueba automática todavía» de CONTRATOS.md). Esto levanta la
app con una base de prueba y los recorre.

Necesita Playwright y Chromium; si no están, lo dice y no falla. No corre en GitHub (no hay
navegador): se corre a mano antes de publicar un cambio que toque el JavaScript o las pantallas
de Ventas y el Buscador. --python es el que tiene Streamlit, si no es el mismo que corre esto
(Playwright y Streamlit pueden estar instalados en dos Python distintos).

Corre en una carpeta temporal: nunca toca la base de trabajo. La contraseña de la base de prueba
se inventa en cada corrida y se borra con la carpeta.
"""
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMIUM = "/opt/pw-browsers/chromium"

# La base de prueba: un empleado y dos productos para buscar. Corre con el Python de la app.
PREPARAR = r"""
import os, sys
sys.path.insert(0, sys.argv[1])
os.chdir(sys.argv[2])
import logica
ns = logica.todo_lo_de_la_logica()
c, conn = ns["c"], ns["conn"]
c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('PRUEBA', 'PROVEEDOR')")
marca = c.lastrowid
for codigo, desc in (("F100", "FILTRO DE ACEITE GOL"), ("F200", "FILTRO DE AIRE GOL")):
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio, "
              "stock) VALUES (?, ?, ?, ?, 1000, 5)", (codigo, codigo, desc, marca))
conn.commit()
ns["crear_usuario"]("navegador", sys.argv[3], "admin")
"""


def _puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _argumento(nombre, defecto=None):
    return sys.argv[sys.argv.index(nombre) + 1] if nombre in sys.argv else defecto


def _esperar(pagina, extra=1.5):
    """Hasta que Streamlit termina de dibujar (se va el «Running…»), y un poco más."""
    time.sleep(0.8)
    for _ in range(120):
        if not pagina.locator('[data-testid="stStatusWidget"]').count():
            break
        time.sleep(0.5)
    time.sleep(extra)


def _foco(pagina):
    """La clave (st-key-…) del campo que tiene el cursor, o «nada»."""
    return pagina.evaluate("""() => {
        const a = document.activeElement;
        const k = a && a.closest('[class*="st-key-"]');
        return k ? [...k.classList].find(c => c.startsWith('st-key-')) : 'nada'; }""")


def _ir(pagina, seccion):
    pagina.locator(".st-key-nav_principal label").filter(has_text=seccion).first.click()
    _esperar(pagina, 2)


def _hasta(condicion, segundos=8):
    final = time.time() + segundos
    while time.time() < final:
        if condicion():
            return True
        time.sleep(0.25)
    return condicion()


def probar(url, clave):
    from playwright.sync_api import sync_playwright
    fallas = []
    with sync_playwright() as pw:
        navegador = pw.chromium.launch(
            **({"executable_path": CHROMIUM} if os.path.exists(CHROMIUM) else {}))
        pagina = navegador.new_page(viewport={"width": 1300, "height": 1100})
        pagina.goto(url, wait_until="networkidle", timeout=180000)
        _esperar(pagina, 3)
        pagina.get_by_text("🔑 Ingresar").first.click()
        _esperar(pagina, 0.5)
        pagina.locator(".st-key-login_inicial_clave input").fill(clave)
        pagina.get_by_role("button", name="Ingresar con contraseña").click()
        _esperar(pagina, 3)

        # 1. Al entrar se arranca en Ventas, con el cursor en su caja de búsqueda: el lector
        # de códigos de barras escanea derecho.
        if not _hasta(lambda: _foco(pagina) == "st-key-venta_buscar"):
            fallas.append(f"al entrar a Ventas el cursor no está en la búsqueda: {_foco(pagina)}")

        # 2. El menú del click derecho sobre un resultado, y Escape lo cierra.
        caja = pagina.locator(".st-key-venta_buscar input")
        caja.fill("F100")
        caja.press("Enter")
        _esperar(pagina, 2)
        renglon = pagina.locator('[class*="st-key-conmenu_vta_"]').first
        if not renglon.count():
            fallas.append("buscando F100 en Ventas no aparece ningún resultado")
        else:
            renglon.click(button="right", position={"x": 30, "y": 12})
            opciones = pagina.locator(".menu-del-renglon button").all_inner_texts()
            if not any("Sumar a la venta" in o for o in opciones):
                fallas.append("el click derecho no abre el menú con «Sumar a la venta»: "
                              f"{opciones}")
            pagina.keyboard.press("Escape")
            if pagina.locator(".menu-del-renglon").count():
                fallas.append("Escape no cierra el menú del click derecho")

        # 3. F2 vuelve a la caja de búsqueda desde cualquier lado.
        pagina.evaluate("() => document.activeElement && document.activeElement.blur()")
        if _foco(pagina) == "st-key-venta_buscar":
            fallas.append("no se pudo sacar el cursor de la búsqueda para probar F2")
        pagina.keyboard.press("F2")
        if not _hasta(lambda: _foco(pagina) == "st-key-venta_buscar", 3):
            fallas.append(f"F2 no lleva el cursor a la búsqueda: {_foco(pagina)}")

        # 4. En el Buscador, el cursor también en su caja.
        _ir(pagina, "🔍 Buscador")
        if not _hasta(lambda: _foco(pagina) == "st-key-busqueda_input"):
            fallas.append(f"al entrar al Buscador el cursor no está en la búsqueda: "
                          f"{_foco(pagina)}")

        # 5. Los textos de Streamlit en castellano: el recuadro para subir un archivo, que en
        # Streamlit 1.65 dice «Upload» y «200MB per file» (antes, «Browse files» y «Drag and
        # drop file here»). El ícono se llama «upload», en minúscula: ese queda.
        _ir(pagina, "📁 Cargar Excel")
        recuadros = " ".join(
            pagina.locator('[data-testid="stFileUploader"]').all_inner_texts())
        if not recuadros:
            fallas.append("no está el recuadro para subir un archivo en «📁 Cargar Excel»")
        elif (any(x in recuadros for x in ("Upload", "Browse files", "per file", "Limit"))
              or "Elegir archivo" not in recuadros or "por archivo" not in recuadros):
            fallas.append(f"el recuadro para subir un archivo no está en castellano: "
                          f"{recuadros[:120]!r}")
        navegador.close()
    return fallas


def main():
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("⏭️ navegador: no está Playwright en este Python, no se prueba")
        return 0
    python_app = _argumento("--python", sys.executable)
    carpeta = tempfile.mkdtemp(prefix="pruebas_navegador_")
    clave = secrets.token_hex(8)
    servidor = None
    try:
        subprocess.run([python_app, "-c", PREPARAR, RAIZ, carpeta, clave], check=True,
                       capture_output=True, timeout=300)
        puerto = _puerto_libre()
        servidor = subprocess.Popen(
            [python_app, "-m", "streamlit", "run", os.path.join(RAIZ, "app.py"),
             "--server.port", str(puerto), "--server.headless", "true"],
            cwd=carpeta, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=dict(os.environ, EQUIVALENCIAS_SIN_TAREAS_DE_FONDO="1"))
        url = f"http://127.0.0.1:{puerto}/"
        for _ in range(60):
            try:
                urllib.request.urlopen(url, timeout=2)
                break
            except OSError:
                time.sleep(1)
        fallas = probar(url, clave)
        for f in fallas:
            print("   ✗", f)
        print("✅ navegador: el cursor al entrar, el click derecho, F2 y los textos en castellano"
              if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        if servidor:
            servidor.terminate()
            try:
                servidor.wait(timeout=10)
            except subprocess.TimeoutExpired:
                servidor.kill()
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

"""Abre la app como la abriría una persona, y si Streamlit la puso a dormir, la despierta.

Streamlit Community Cloud apaga las apps gratis que pasan un rato sin visitas (hoy son 12
horas). Una app dormida muestra un cartel con un botón en vez de la app, y la primera persona
que entra a la mañana tiene que tocarlo y esperar a que arranque. Además, al volver, el
servidor arranca con el disco vacío y la base se restaura desde la copia de seguridad.

Lo corre .github/workflows/mantener_despierta.yml cada pocas horas. Si la app no aparece,
termina con error: GitHub le manda un mail al dueño del repositorio, y eso sirve de alarma
de «la app está caída».

Para probarlo a mano:  URL_DE_LA_APP=https://... python .github/despertar_la_app.py
"""
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

URL = os.environ.get("URL_DE_LA_APP", "https://elchavo.streamlit.app/")
MINUTOS_PARA_ARRANCAR = 4     # despertar una app dormida tarda uno o dos minutos


def se_ve_la_app(pagina):
    # Streamlit Cloud muestra la app adentro de un marco: se busca en todos.
    for marco in pagina.frames:
        try:
            if marco.locator('[data-testid="stApp"]').count():
                return True
        except Exception:
            pass      # un marco que se está recargando: se mira en la próxima vuelta
    return False


def contar_lo_que_se_ve(pagina):
    """Cuando falla, qué había en la pantalla: sin esto el error dice «no apareció» y nada
    más, y no hay forma de saber si era un cartel nuevo, un pedido de login o la app rota.
    La captura queda en los archivos de la corrida (Actions → la corrida → Artifacts)."""
    try:
        print("Título:", pagina.title(), "| dirección:", pagina.url)
        for marco in pagina.frames:
            try:
                texto = marco.locator("body").inner_text(timeout=5_000)
            except Exception as error:
                texto = f"(no se pudo leer: {error})"
            print(f"--- marco {marco.url}\n{texto[:1500]}")
        pagina.screenshot(path="lo_que_se_vio.png", full_page=True)
    except Exception as error:
        print("No se pudo mirar la página:", error)


def main():
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page()
        pagina.goto(URL, wait_until="domcontentloaded", timeout=120_000)
        pagina.wait_for_timeout(8_000)
        if "errors/not_found" in pagina.url:
            # Streamlit contesta lo mismo para las dos cosas, así que no se puede saber cuál es.
            print(f"Streamlit dice que no hay acceso a {URL} o que no existe. O la app es "
                  "privada (en Streamlit: Share → que la pueda ver cualquiera), o la dirección "
                  "es otra (cambiarla en la variable URL_DE_LA_APP del repositorio).")
            navegador.close()
            sys.exit(1)
        # Botón o enlace: el cartel de Streamlit cambió de forma más de una vez.
        boton = pagina.locator("button, a").filter(
            has_text=re.compile(r"get this app back up|wake (it|the app) (back )?up", re.I))
        if boton.count():
            print("La app estaba dormida: despertándola.")
            boton.first.click()
        hasta = time.time() + MINUTOS_PARA_ARRANCAR * 60
        while time.time() < hasta and not se_ve_la_app(pagina):
            pagina.wait_for_timeout(5_000)
        if not se_ve_la_app(pagina):
            print(f"La app no apareció en {MINUTOS_PARA_ARRANCAR} minutos: {URL}")
            contar_lo_que_se_ve(pagina)
            navegador.close()
            sys.exit(1)
        # Un rato con la sesión abierta, como una visita de verdad.
        pagina.wait_for_timeout(20_000)
        print("La app está andando.")
        navegador.close()


if __name__ == "__main__":
    main()

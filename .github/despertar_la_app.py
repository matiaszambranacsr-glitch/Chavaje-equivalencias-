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


def main():
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page()
        pagina.goto(URL, wait_until="domcontentloaded", timeout=120_000)
        pagina.wait_for_timeout(8_000)
        boton = pagina.get_by_role("button", name=re.compile("get this app back up", re.I))
        if boton.count():
            print("La app estaba dormida: despertándola.")
            boton.first.click()
        hasta = time.time() + MINUTOS_PARA_ARRANCAR * 60
        while time.time() < hasta and not se_ve_la_app(pagina):
            pagina.wait_for_timeout(5_000)
        if not se_ve_la_app(pagina):
            print(f"La app no apareció en {MINUTOS_PARA_ARRANCAR} minutos: {URL}")
            navegador.close()
            sys.exit(1)
        # Un rato con la sesión abierta, como una visita de verdad.
        pagina.wait_for_timeout(20_000)
        print("La app está andando.")
        navegador.close()


if __name__ == "__main__":
    main()

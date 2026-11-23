"""Lo que corre en el navegador y las otras pruebas no ven: con la app de verdad y un Chromium.

Uso:
    python3 pruebas/navegador.py [--python <el Python que tiene Streamlit>]
    python3 pruebas/navegador.py --barrido --base <copia de la base real> [--python …]

--barrido no corre los pasos de siempre: entra como administrador a una COPIA de esa base y
recorre todas las pantallas y solapas en un teléfono simulado, diciendo en cuáles algo se sale
de la pantalla o un botón quedó aplastado (ver barrer_en_el_telefono()). Al final abre también
los paneles que llegan cerrados y tienen campos lado a lado (los pedidos del chat y lo pegado en
el Buscador). Con CAPTURAS_DEL_BARRIDO=<carpeta> guarda una captura de cada uno, para mirarlas.

El JavaScript de AYUDAS_DEL_NAVEGADOR (logica/interfaz.py) no lo corre AppTest: el cursor en la
caja de búsqueda al entrar a cada pantalla, F2, el menú del click derecho y los textos de
Streamlit pasados al castellano se probaban a mano con un navegador, y si un cambio los rompía
nadie se enteraba (estaba en «Sin prueba automática todavía» de CONTRATOS.md). Esto levanta la
app con una base de prueba y los recorre.

Necesita Playwright y Chromium; si no están, lo dice y no falla (con --sin-saltear, sí falla:
es como lo corre GitHub, que instala los dos, para que un día sin navegador no pase por verde).
Corre en GitHub en cada subida, en su propio trabajo (.github/workflows/pruebas.yml), desde que
el asistente rompió el cursor de Ventas y nadie se enteró: hasta ahí se corría solo a mano.
--python es el que tiene Streamlit, si no es el mismo que corre esto (Playwright y Streamlit
pueden estar instalados en dos Python distintos).

Corre en una carpeta temporal: nunca toca la base de trabajo. La contraseña de la base de prueba
se inventa en cada corrida y se borra con la carpeta.
"""
import os
import re
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
# Un chat de WhatsApp con un mensaje recién llegado, para contestarlo (ver el paso 7b).
ns["guardar_mensaje_de_afuera"]({"canal": "whatsapp", "chat": "5491145678901",
                                 "nombre": "Cliente Del Navegador", "id": "nav-1",
                                 "texto": "hola, tenés el F100?", "entra": True, "cuando": None})
# Y un pedido con palabras, para armar el presupuesto con lo que pide (ver el paso 7b).
ns["guardar_mensaje_de_afuera"]({"canal": "whatsapp", "chat": "5491145678901",
                                 "nombre": "Cliente Del Navegador", "id": "nav-2",
                                 "texto": "y 2 filtros de aire, y un filtro de aceite para el gol",
                                 "entra": True,
                                 "cuando": None})
conn.commit()
ns["crear_usuario"]("navegador", sys.argv[3], "admin")
# WhatsApp «conectado» con datos inventados, para que esté la caja de la respuesta. Nunca sale
# nada: la prueba no toca «📤 Enviar», y las tareas de fondo están apagadas.
os.makedirs(".streamlit", exist_ok=True)
with open(os.path.join(".streamlit", "secrets.toml"), "w") as f:
    f.write('[mensajes]\nwhatsapp_token = "inventado-para-la-prueba"\nwhatsapp_numero_id = "0"\n')
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


def probar(url, clave, carpeta):
    from playwright.sync_api import sync_playwright
    import sqlite3
    fallas = []

    def _base(consulta):
        with sqlite3.connect(os.path.join(carpeta, "equivalencias_app.db")) as con:
            return con.execute(consulta).fetchone()[0]
    with sync_playwright() as pw:
        navegador = pw.chromium.launch(
            **({"executable_path": CHROMIUM} if os.path.exists(CHROMIUM) else {}))
        pagina = navegador.new_page(viewport={"width": 1300, "height": 1100})
        pagina.goto(url, wait_until="networkidle", timeout=180000)
        _esperar(pagina, 3)
        pagina.get_by_text("🔑 Ingresar").first.click()
        _esperar(pagina, 0.5)
        pagina.locator(".st-key-login_inicial_nombre input").fill("navegador")
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

        # 4. La venta de todos los días, con el teclado: sumar F100 con el click derecho, F9
        # con el cursor en la búsqueda (Streamlit solo no atiende sus teclas ahí) PREGUNTA, con
        # el total a la vista, y no graba nada; Enter es el «Sí» y la manda a la caja (ver «QUE
        # UNA VENTA NO SE GRABE POR ACCIDENTE» en logica/ventas.py). En la caja, F10 abre
        # «Cobrar la venta», otro F10 no abre otra encima, y cobrar la deja cobrada.
        _ir(pagina, "🧾 Ventas")
        caja = pagina.locator(".st-key-venta_buscar input")
        caja.fill("F100")
        caja.press("Enter")
        _esperar(pagina, 2)
        pagina.locator('[class*="st-key-conmenu_vta_"]').first.click(
            button="right", position={"x": 30, "y": 12})
        pagina.locator(".menu-del-renglon button").filter(has_text="Sumar a la venta").first.click()
        _esperar(pagina, 2)
        pagina.keyboard.press("F2")
        pagina.keyboard.press("F9")
        _esperar(pagina, 2)
        if not _hasta(lambda: pagina.locator(".st-key-venta_por_cerrar_caja").count() == 1, 4):
            fallas.append("F9 no pregunta si mandar la venta a la caja")
        elif _base("SELECT COUNT(*) FROM ventas"):
            fallas.append("F9 solo, sin el «Sí», ya grabó la venta")
        pagina.keyboard.press("Enter")
        _esperar(pagina, 3)
        if not _hasta(lambda: _base("SELECT COUNT(*) FROM ventas WHERE cobrada = 0") == 1):
            fallas.append("F9 y Enter no mandaron la venta a la caja")
        else:
            _ir(pagina, "💵 Caja")
            pagina.keyboard.press("F10")
            _esperar(pagina, 2)
            dialogos = pagina.locator('[role="dialog"]')
            if not dialogos.count() or "Cobrar la venta" not in dialogos.first.inner_text():
                fallas.append("F10 no abre «Cobrar la venta» en la caja")
            else:
                pagina.keyboard.press("F10")
                _esperar(pagina, 1)
                if pagina.locator('[role="dialog"]').count() > 1:
                    fallas.append("un segundo F10 abre otra ventana encima")
                dialogos.first.get_by_role("button", name="Cobrar").last.click()
                _esperar(pagina, 3)
                if not _hasta(lambda: _base("SELECT COUNT(*) FROM ventas WHERE cobrada = 1")
                              == 1):
                    fallas.append("cobrar desde la ventana de F10 no deja la venta cobrada")

        # 5. En el Buscador, el cursor también en su caja.
        _ir(pagina, "🔍 Buscador")
        if not _hasta(lambda: _foco(pagina) == "st-key-busqueda_input"):
            fallas.append(f"al entrar al Buscador el cursor no está en la búsqueda: "
                          f"{_foco(pagina)}")
        # Y en «📦 Entró mercadería», en la caja del código: el lector escanea derecho, y con
        # Enter lo suma a la lista y la caja queda lista para el siguiente.
        _ir(pagina, "Depósito")
        pagina.locator("[class*='st-key-sub_'] label").filter(has_text="Entró mercadería").first.click()
        _esperar(pagina, 2)
        if not _hasta(lambda: _foco(pagina) == "st-key-entro_codigo"):
            fallas.append("al entrar a «📦 Entró mercadería» el cursor no está en el código: "
                          f"{_foco(pagina)}")
        else:
            pagina.keyboard.type("F100", delay=20)
            pagina.keyboard.press("Enter")
            _esperar(pagina, 2)
            if not _hasta(lambda: pagina.locator('[class*="st-key-entro_cant_"]').count() == 1):
                fallas.append("en «📦 Entró mercadería», escanear y Enter no lo suma a la lista")
            elif pagina.locator(".st-key-entro_codigo input").input_value():
                fallas.append("después de sumarlo, la caja del código no quedó vacía")

        # 6. Los textos de Streamlit en castellano: el recuadro para subir un archivo, que en
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

        # 7. F1 abre el asistente con el cursor en su caja para escribir, y otro F1 lo
        # minimiza (ver «LA BURBUJA DEL ASISTENTE» en logica/asistente.py).
        pagina.keyboard.press("F1")
        if not _hasta(lambda: pagina.locator(".st-key-asistente_abierto").count() == 1):
            fallas.append("F1 no abre el asistente")
        elif not _hasta(lambda: pagina.evaluate(
                "() => !!(document.activeElement && document.activeElement.closest("
                "'.st-key-asistente_abierto'))")):
            fallas.append("al abrir el asistente con F1 el cursor no queda en su caja")
        else:
            pagina.keyboard.press("F1")
            if not _hasta(lambda: pagina.locator(".st-key-asistente_minimizado").count() == 1):
                fallas.append("un segundo F1 no minimiza el asistente")
            # Y Escape, escribiéndole, también lo minimiza.
            pagina.keyboard.press("F1")
            if _hasta(lambda: pagina.locator(".st-key-asistente_abierto textarea").count() == 1):
                pagina.locator(".st-key-asistente_abierto textarea").focus()
                pagina.keyboard.press("Escape")
                if not _hasta(lambda: pagina.locator(
                        ".st-key-asistente_minimizado").count() == 1):
                    fallas.append("Escape no minimiza el asistente")

        # 7b. 💬 MENSAJES, dos cosas que la prueba sin navegador no ve:
        #  · Abrir un chat sin leer cambia la cuenta de la pastilla («· 1»). Iba en el nombre de
        #    la opción, y el navegador se quedaba sin ninguna pantalla marcada: el toque
        #    siguiente volvía a 🧾 Ventas (ver cuenta_en_la_barra()).
        #  · Lo escrito en la respuesta no se pierde al tocar una respuesta rápida. La caja
        #    estaba en un formulario y lo escrito no llegaba hasta «📤 Enviar»: «Hola! Te
        #    cuento:» + «¡Hola! ¿En qué te ayudo?» quedaba en la frase sola.
        _marcada = """() => { const i = document.querySelector('.st-key-nav_principal input:checked');
            return i ? i.closest('label').innerText : null; }"""
        _ir(pagina, "Mensajes")
        _cuenta = pagina.evaluate("""() => { const p = [...document.querySelectorAll(
            '.st-key-nav_principal label p')].find(p => p.innerText.includes('Mensajes'));
            return p ? getComputedStyle(p, '::after').content : null; }""")
        if '· 1' not in str(_cuenta):
            fallas.append(f"la pastilla de 💬 Mensajes no dice «· 1» sin leer: {_cuenta!r}")
        pagina.get_by_role("button", name="Cliente Del Navegador").first.click()
        _esperar(pagina, 2)
        respuesta = pagina.locator('textarea[aria-label="Tu respuesta:"]')
        if not _hasta(lambda: "Mensajes" in str(pagina.evaluate(_marcada))):
            fallas.append("al abrir un chat sin leer, la barra queda sin pantalla marcada: "
                          f"{pagina.evaluate(_marcada)!r}")
        if not _hasta(lambda: respuesta.count() == 1):
            fallas.append("en 💬 Mensajes, al abrir el chat no está la caja de la respuesta")
        else:
            respuesta.click()
            respuesta.type("Hola! Te cuento:", delay=15)
            pagina.locator('[class*="st-key-msj_respuesta_"][class*="_rapida"] button').first.click()
            _esperar(pagina, 1)
            if not respuesta.count():
                fallas.append("en 💬 Mensajes, tocar una respuesta rápida saca de la pantalla: "
                              f"quedó en {pagina.evaluate(_marcada)!r}")
            elif not _hasta(lambda: respuesta.input_value().startswith("Hola! Te cuento: ")
                            and len(respuesta.input_value()) > len("Hola! Te cuento: ")):
                fallas.append("en 💬 Mensajes, tocar una respuesta rápida borra lo escrito: "
                              f"quedó {respuesta.input_value()!r}")
        #  · Y el link de WhatsApp lleva lo recién escrito aunque no se haya salido de la caja:
        #    se escribía «te pido 4 unidades», se tocaba directo el link y WhatsApp se abría con
        #    el texto de antes (ver «walink__» en AYUDAS_DEL_NAVEGADOR). Nada sale a internet.
        pagina.context.route("https://wa.me/**", lambda r: r.fulfill(body="ok"))
        pagina.locator(".st-key-exp_numero_nuevo summary").first.click()
        _esperar(pagina, 1)
        numero = pagina.locator(".st-key-msj_numero_nuevo input")
        numero.fill("11 4567-8901")
        numero.press("Enter")
        _esperar(pagina, 2)
        mensaje = pagina.locator(".st-key-msj_texto_nuevo textarea")
        link = pagina.locator(".st-key-walink__msj_texto_nuevo a")
        if not (mensaje.count() and _hasta(lambda: link.count() == 1)):
            fallas.append("en «✉️ Escribirle a un número nuevo» no aparece el link de WhatsApp")
        else:
            mensaje.click()
            mensaje.type("te pido 4 unidades", delay=10)
            with pagina.context.expect_page() as nueva:
                link.click()
            _url = nueva.value.url
            nueva.value.close()
            if _url != "https://wa.me/5491145678901?text=te%20pido%204%20unidades":
                fallas.append("el link de WhatsApp no lleva lo recién escrito: abrió " + _url)

        #  · «🧩 Armar el presupuesto con lo que pide» (el F100, los filtros de aire y el de
        #    aceite, que también es el F100): se descarta un pedido y se cambia la cantidad de
        #    otro sin salir del campo, y se toca directo «🛒 Armar». Lo que va es lo que se ve en ese momento (el botón lee los
        #    campos al tocarlo: sus args se arman en la pasada anterior, con lo de antes).
        pagina.locator('[class*="st-key-exp_presu_chat_"] summary').first.click()
        _selec = pagina.locator('[class*="st-key-pedido_chat_"]:not([class*="_cant"])')
        if not _hasta(lambda: _selec.count() == 3, 15):
            fallas.append("en el chat, «🧩 Armar el presupuesto con lo que pide» no muestra los "
                          f"tres pedidos (el F100, el filtro de aire y el de aceite): "
                          f"{_selec.count()}")
        else:
            # Antes a la vista: Playwright mueve la pantalla al tocar, y el selector se cierra
            # solo cuando la página se mueve (una persona no mueve la página al tocar).
            _selec.nth(1).evaluate("e => e.scrollIntoView({block: 'center'})")
            _esperar(pagina, 1)
            _selec.nth(1).locator('button[aria-haspopup="listbox"]').click()
            pagina.get_by_role("option", name="🗑️ Descartar este pedido").click()
            _esperar(pagina, 2)
            _cant = pagina.locator('[class*="st-key-pedido_chat_"][class*="_cant"] input').nth(2)
            _cant.fill("3")
            pagina.get_by_role("button", name="🛒 Armar el presupuesto con lo elegido").click()
            _armado = pagina.locator(".st-key-exp_presupuesto_armado_item_s summary")
            if not _hasta(lambda: _armado.count() == 1, 15):
                fallas.append("«🛒 Armar el presupuesto con lo elegido» no lleva al presupuesto "
                              f"del Buscador: quedó en {pagina.evaluate(_marcada)!r}")
            elif "1 ítem(s) · $4.000" not in _armado.inner_text():
                # El F100 ×1 (el código) y ×3 (el filtro de aceite) van juntos: ×4.
                fallas.append("el presupuesto armado desde el chat no es el F100 ×4 (sin el "
                              f"descartado): {_armado.inner_text()!r}")

        # 7c. 📁 CARGAR EXCEL: la fila de los títulos es la de CADA archivo. Al cambiar de lista,
        # la app borraba la clave del campo, pero el navegador seguía mostrando el número de la
        # lista anterior y lo mandaba de vuelta: la segunda se importaba desde la fila de la
        # primera y sus primeros productos se perdían como títulos. Ahora la clave lleva la
        # huella del archivo. La prueba sin navegador no lo ve.
        _con_tapa = os.path.join(carpeta, "lista_con_tapa.csv")
        _sin_tapa = os.path.join(carpeta, "lista_sin_tapa.csv")
        with open(_con_tapa, "w", encoding="utf-8") as f:
            f.write("LISTA DE PRECIOS ZETA;;\nVigencia noviembre;;\nCodigo;Descripcion;Precio\n"
                    + "".join(f"Z{i};FILTRO {i};{100 + i}\n" for i in range(1, 9)))
        with open(_sin_tapa, "w", encoding="utf-8") as f:
            f.write("Codigo;Descripcion;Precio\n"
                    + "".join(f"Y{i};BUJIA {i};{200 + i}\n" for i in range(1, 9)))
        _ir(pagina, "Cargar Excel")
        _fila = pagina.locator('[class*="st-key-fila_encabezado"] input')
        pagina.locator('[class*="st-key-_up_lista_"] input[type="file"]').set_input_files(_con_tapa)
        if not _hasta(lambda: _fila.count() == 1, 15):
            fallas.append("en 📁 Cargar Excel, al subir la lista no aparece la fila de los títulos")
        else:
            _fila_1 = _fila.input_value()
            # La otra lista, subida directo encima (sin «🗑️ Usar otro archivo», que borra el
            # campo y así lo limpiaba): es lo que pasaba.
            pagina.locator('[class*="st-key-_up_lista_"] input[type="file"]').set_input_files(
                _sin_tapa)
            _hasta(lambda: _fila.count() == 1 and _fila.input_value() != _fila_1, 15)
            _fila_2 = _fila.input_value() if _fila.count() else None
            if (_fila_1, _fila_2) != ("3", "1"):
                fallas.append("en 📁 Cargar Excel, la fila de los títulos no es la de cada lista: "
                              f"con tapa {_fila_1}, la siguiente sin tapa {_fila_2} "
                              "(tenía que ser 3 y 1)")

        # 8. EN UN TELÉFONO, sin contraseña, que es como lo abre un cliente. Un teléfono
        # simulado de verdad (táctil): achicando la ventana de la computadora lo del celular no
        # se aplica, y así se pasó por alto que la burbuja del asistente salía de 16 x 54
        # —app.py estira todos los botones a lo ancho—. Y después de buscar, la pantalla baja
        # sola hasta lo encontrado: el formulario ocupa la pantalla y los resultados quedan abajo.
        telefono = navegador.new_context(**pw.devices["Pixel 7"])
        celular = telefono.new_page()
        celular.goto(url, wait_until="networkidle", timeout=180000)
        _esperar(celular, 3)
        burbuja = celular.locator(".st-key-asis_abrir button:visible")
        medida = burbuja.first.bounding_box() if burbuja.count() else None
        if not medida:
            fallas.append("en el teléfono no está la burbuja del asistente")
        elif abs(medida["width"] - medida["height"]) > 2 or medida["width"] < 64:
            # Redonda y grande: el dueño la pidió más grande en el celular («no se ve
            # prácticamente»), y es de 68 px; con 54 se perdía.
            fallas.append("en el teléfono la burbuja del asistente no es redonda o es chica: "
                          f"{medida['width']:.0f} x {medida['height']:.0f}")
        else:
            _letra = celular.evaluate("""() => { const p = document.querySelector(
                '.st-key-asis_abrir button p'); return p ? parseFloat(getComputedStyle(p).fontSize) : 0; }""")
            _abajo = celular.evaluate("""() => { const b = document.querySelector(
                '.st-key-asis_abrir button'); const r = b.getBoundingClientRect();
                return window.innerHeight - r.bottom; }""")
            if _letra < 32 or _abajo < 12:
                fallas.append(f"en el teléfono el 🤖 es chico ({_letra:.0f} px) o la burbuja "
                              f"queda pegada al borde ({_abajo:.0f} px)")
        celular.locator(".st-key-busqueda_input input").fill("F100")
        celular.get_by_role("button", name="Buscar equivalencias").first.tap()
        _esperar(celular, 2)

        def _donde_quedo_lo_encontrado():
            return celular.evaluate("""() => {
                const r = document.querySelector('[class*="st-key-exp_resultado_"]');
                return r ? r.getBoundingClientRect().top / window.innerHeight : null; }""")
        if not _hasta(lambda: _donde_quedo_lo_encontrado() is not None
                      and 0 <= _donde_quedo_lo_encontrado() < 0.6):
            fallas.append("en el teléfono, después de buscar la pantalla no baja hasta lo "
                          f"encontrado: quedó en {_donde_quedo_lo_encontrado()} de la pantalla")
        telefono.close()
        navegador.close()
    return fallas


# EL BARRIDO EN EL TELÉFONO. «Probar en el celular» achicando la ventana de la computadora no
# prueba el celular: lo que app.py le cambia al teléfono (los botones a lo ancho, las columnas
# apiladas) no se aplica, y así la burbuja del asistente salió aplastada sin que nadie la viera.
# Esto usa un teléfono simulado de verdad —táctil, con su navegador— y mide en vez de mirar:
# en cada pantalla, lo que se sale por un costado sin estar en algo que se desliza, la página
# que se corre de costado, y los botones de la app más angostos o más bajos que un dedo.
_MEDIR_LA_PANTALLA = """() => {
  const ancho = window.innerWidth, main = document.querySelector('[data-testid="stMain"]');
  const seVe = e => { const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden'; };
  const seDesliza = e => { for (let x = e.parentElement; x && x !== document.body; x = x.parentElement) {
    const s = getComputedStyle(x);
    if ((s.overflowX === 'auto' || s.overflowX === 'scroll') && x.scrollWidth > x.clientWidth + 2) return true;
    if (x.getAttribute('data-testid') === 'stDataFrame') return true; } return false; };
  const nombre = e => (e.innerText || e.getAttribute('aria-label') || e.tagName).trim()
    .replace(/\\s+/g, ' ').slice(0, 34);
  const fuera = [], chicos = [];
  document.querySelectorAll('[data-testid="stMain"] button, [data-testid="stMain"] input, ' +
      '[data-testid="stMain"] [data-testid="stMarkdownContainer"], ' +
      '[data-testid="stMain"] [data-testid="stMetric"], [data-testid="stMain"] [data-testid="stAlert"], ' +
      '[data-testid="stMain"] [data-testid="stExpander"]').forEach(e => {
    if (!seVe(e)) return;
    const r = e.getBoundingClientRect();
    if ((r.right > ancho + 3 || r.left < -3) && !seDesliza(e))
      fuera.push(nombre(e) + ' (de ' + Math.round(r.left) + ' a ' + Math.round(r.right) + ' px)');
    if (e.tagName === 'BUTTON' && (r.width < 40 || r.height < 30) &&
        e.closest('.stButton, .stDownloadButton, .stFormSubmitButton, .stLinkButton'))
      chicos.push(nombre(e) + ' (' + Math.round(r.width) + ' x ' + Math.round(r.height) + ')');
  });
  return {corrida: Math.max(main ? main.scrollWidth - main.clientWidth : 0,
                            document.documentElement.scrollWidth - ancho),
          fuera: fuera.slice(0, 5), chicos: [...new Set(chicos)].slice(0, 5),
          rota: [...document.querySelectorAll('[data-testid="stException"]')]
                  .map(e => e.innerText.slice(0, 120))}; }"""


def barrer_en_el_telefono(url, clave):
    """Recorre todas las pantallas y solapas, entrando como administrador, en un teléfono
    simulado. Imprime una línea por pantalla y devuelve las que tienen algo."""
    from playwright.sync_api import sync_playwright
    barra, solapas_de = ".st-key-nav_principal [role='radiogroup'] label", \
        "[class*='st-key-sub_'] [role='radiogroup'] label"
    con_algo = []
    with sync_playwright() as pw:
        navegador = pw.chromium.launch(
            **({"executable_path": CHROMIUM} if os.path.exists(CHROMIUM) else {}))
        pagina = navegador.new_context(**pw.devices["Pixel 7"]).new_page()
        pagina.goto(url, wait_until="networkidle", timeout=180000)
        _esperar(pagina, 3)
        pagina.get_by_text("🔑 Ingresar").first.tap()
        _esperar(pagina, 0.5)
        pagina.locator(".st-key-login_inicial_nombre input").fill("navegador")
        pagina.locator(".st-key-login_inicial_clave input").fill(clave)
        pagina.get_by_role("button", name="Ingresar con contraseña").tap()
        _esperar(pagina, 5)
        for entendido in pagina.get_by_role("button", name="Entendido").all():
            entendido.tap()
            _esperar(pagina, 1)
        capturas = os.environ.get("CAPTURAS_DEL_BARRIDO")

        def revisar(donde, problemas=()):
            medido = pagina.evaluate(_MEDIR_LA_PANTALLA)
            problemas = (
                list(problemas)
                + ([f"la página se corre {medido['corrida']} px de costado"]
                   if medido["corrida"] > 3 else [])
                + [f"se sale de la pantalla: {x}" for x in medido["fuera"]]
                + [f"botón aplastado: {x}" for x in medido["chicos"]]
                + [f"la pantalla se rompió: {x}" for x in medido["rota"]])
            print(("   ✗ " if problemas else "   ✓ ") + donde)
            for problema in problemas:
                print("       ", problema)
            if problemas:
                con_algo.append(donde)
            if capturas:
                pagina.screenshot(path=os.path.join(
                    capturas, re.sub(r"\W+", "_", donde).strip("_")[:80] + ".png"), full_page=True)

        for seccion in [x.strip() for x in pagina.locator(barra).all_inner_texts()]:
            pagina.locator(barra).filter(has_text=seccion).first.tap()
            _esperar(pagina, 2)
            for solapa in [x.strip() for x in pagina.locator(solapas_de).all_inner_texts()] or [""]:
                if solapa:
                    pagina.locator(solapas_de).filter(has_text=solapa).first.tap()
                    _esperar(pagina, 2)
                revisar(seccion + (f" → {solapa}" if solapa else ""))

        # LOS PANELES QUE LLEGAN CERRADOS, con selectores y cantidades lado a lado: el recorrido
        # de arriba los ve cerrados. El chat y el pedido son los de PREPARAR.
        def abrir_los_pedidos_del_chat():
            pagina.locator(barra).filter(has_text="Mensajes").first.tap()
            _esperar(pagina, 2)
            pagina.get_by_role("button", name="Cliente Del Navegador").first.tap()
            _esperar(pagina, 2)
            pagina.locator('[class*="st-key-exp_presu_chat_"] summary').first.tap()
            _esperar(pagina, 3)

        def abrir_el_pedido_pegado():
            pagina.locator(barra).filter(has_text="Buscador").first.tap()
            _esperar(pagina, 2)
            pagina.locator(".st-key-exp_pedido_pegado summary").first.tap()
            _esperar(pagina, 2)
            caja = pagina.locator(".st-key-pedido_pegado textarea")
            caja.fill("necesito 2 filtros de aire para el gol, un filtro de aceite y el F100")
            caja.evaluate("e => e.blur()")
            _esperar(pagina, 3)

        def abrir_los_tiempos():
            pagina.locator(barra).filter(has_text="Administrar").first.tap()
            _esperar(pagina, 2)
            pagina.locator(solapas_de).filter(has_text="Usuarios").first.tap()
            _esperar(pagina, 2)
            pagina.locator(".st-key-exp_tiempos_de_la_pagina summary").first.tap()
            _esperar(pagina, 3)

        for donde, abrir in (
                ("🗂️ Administrar → 👥 Usuarios → ⏱️ Los tiempos de la página", abrir_los_tiempos),
                ("💬 Mensajes → 🧩 Armar el presupuesto con lo que pide",
                 abrir_los_pedidos_del_chat),
                ("🔍 Buscador → 🧩 Pegar el pedido de un cliente", abrir_el_pedido_pegado)):
            try:
                abrir()
                revisar(donde)
            except Exception as error:      # que no se abra también es algo que decir
                revisar(donde, [f"no se pudo abrir: {str(error).splitlines()[0][:120]}"])
        navegador.close()
    return con_algo


def main():
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("⏭️ navegador: no está Playwright en este Python, no se prueba")
        return 1 if "--sin-saltear" in sys.argv else 0
    python_app = _argumento("--python", sys.executable)
    carpeta = tempfile.mkdtemp(prefix="pruebas_navegador_")
    clave = secrets.token_hex(8)
    servidor = None
    try:
        # --barrido: sobre una COPIA de la base que se le pasa, que se borra con la carpeta. El
        # usuario «navegador» y su contraseña inventada quedan solo en esa copia.
        if "--barrido" in sys.argv:
            shutil.copy(_argumento("--base"), os.path.join(carpeta, "equivalencias_app.db"))
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
        if "--barrido" in sys.argv:
            con_algo = barrer_en_el_telefono(url, clave)
            print(f"📱 el barrido en el teléfono: {len(con_algo)} pantalla(s) con algo"
                  if con_algo else "✅ el barrido en el teléfono: nada se sale ni queda aplastado")
            return 1 if con_algo else 0
        fallas = probar(url, clave, carpeta)
        for f in fallas:
            print("   ✗", f)
        print("✅ navegador: el cursor al entrar, el click derecho, F1, F2, F9, F10, los "
              "textos en castellano y el teléfono"
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

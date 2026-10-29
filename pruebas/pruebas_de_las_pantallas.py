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
import re
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
                # Solo el hilo que corre la pantalla (el que viene de app.py). El índice de la
                # búsqueda por texto se arma en otro hilo la primera vez, y sus renglones se le
                # anotaban a la pantalla que estuviera abierta («Repuestos por vehículo
                # [armar_el_indice_de_busqueda] 3,6 s»).
                _arriba = marco
                while _arriba and _arriba.f_code.co_filename != os.path.join(RAIZ, "app.py"):
                    _arriba = _arriba.f_back
                if not _arriba:
                    continue
                # Sin el envoltorio de la base (datos.py:execute): lo que sirve es quién consulta.
                while marco and (not marco.f_code.co_filename.startswith(
                        (os.path.join(RAIZ, "logica"), os.path.join(RAIZ, "pantallas"), "<"))
                        or marco.f_code.co_name in ("execute", "executemany", "fetchall")):
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


_RE_FECHA_CRUDA = re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?(\.\d+)?)?$")
_RE_FECHA_EN_TEXTO = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_tablas_vistas = set()


def _ids_de_los_botones(at, prefijo):
    """Los productos de los botones cuya clave empieza con `prefijo` («citan_P716_123» → «123»)."""
    return {(b.key or "").rsplit("_", 1)[-1] for b in at.button
            if (b.key or "").startswith(prefijo)}


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
        _tablas_en_castellano(quien, donde)
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
            _tablas_en_castellano(quien, f"{donde} (con lo plegado abierto)")
            for e in at.exception:
                fallas.append(f"{quien}: {donde} (con lo plegado abierto): {e.value[:200]}")
            for k in cerrados:
                at.session_state[k] = False

    def _tablas_en_castellano(quien, donde):
        # Lo que el navegador dibuja como imagen y nadie lee en voz alta: un vacío sale «None»,
        # en gris y en inglés, y una fecha como la guarda la base (ver «LAS TABLAS, COMO SE
        # LEEN ACÁ»). Una vez por tabla y columna.
        for _d in at.dataframe:
            try:
                _df = _d.value
            except Exception:
                continue
            for _col in getattr(_df, "columns", []):
                for _v in list(_df[_col].head(200)):
                    _mal = ("«None»" if _v is None or (isinstance(_v, float) and _v != _v)
                            else "la fecha como la base"
                            if isinstance(_v, str) and _RE_FECHA_CRUDA.match(_v.strip()) else "")
                    if _mal and (donde.split(" (")[0], _col) not in _tablas_vistas:
                        _tablas_vistas.add((donde.split(" (")[0], _col))
                        fallas.append(f"{quien}: {donde}: la columna «{_col}» muestra {_mal} "
                                      f"({_v!r})")
                        break
        # Y en los textos: «última vez: 2026-10-25 22:21» (ver fecha_legible()).
        for _tipo in ("markdown", "caption", "info", "warning", "error", "success"):
            for _el in getattr(at, _tipo, []):
                _txt = str(getattr(_el, "value", ""))
                _hay = None if _txt.lstrip().startswith("<") else _RE_FECHA_EN_TEXTO.search(_txt)
                if _hay and (donde.split(" (")[0], _tipo, _txt[:40]) not in _tablas_vistas:
                    _tablas_vistas.add((donde.split(" (")[0], _tipo, _txt[:40]))
                    fallas.append(f"{quien}: {donde}: un {_tipo} dice la fecha como la base: "
                                  f"«…{_txt[max(0, _hay.start() - 40):_hay.end()]}»")

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
    # Con --base, en la base real dos descripciones nombran F101 («Despiece FIAT F101»): eso es
    # la respuesta, y los que se escriben casi igual quedan plegados. Se abren y ahí está.
    if "--base" in sys.argv and not _tipeo:
        for _plegado in [t for t in at.toggle if t.key == "tipeos_plegados_F101"]:
            _plegado.set_value(True).run()
        _tipeo = [b for b in at.button if (b.key or "").startswith("tipeo_F101_")]
    if ([b.label for b in _tipeo] != ["🔎 F100"] if "--base" not in sys.argv
            else "🔎 F100" not in [b.label for b in _tipeo]):
        fallas.append(f"el código casi igual, como botón: {[b.label for b in _tipeo]}")
    else:
        _elegido = _tipeo[0].label.replace("🔎 ", "")
        _tipeo[0].click().run()
        if not any(_elegido in str(m.value) for m in list(at.markdown) + list(at.caption)):
            fallas.append("tocar el código casi igual no lo busca")
    # Por descripción, lo que no nombra el auto pedido va aparte y plegado (ver
    # nivel_del_auto()): «bomba de agua k4m» no mezcla las bombas de cualquier auto.
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) VALUES "
              "('BAK4M', 'BAK4M', 'BOMBA DE AGUA RENAULT CLIO 1.6 16V K4M', ?), "
              "('BAPAL', 'BAPAL', 'BOMBA DE AGUA FIAT PALIO 1.3', ?)", (_marca_prueba,) * 2)
    conn.commit()
    # Con su equivalente de otra lista: con uno o dos resultados, sus equivalencias se abren solas.
    _bak4m = c.execute("SELECT id FROM productos WHERE codigo_clean = 'BAK4M'").fetchone()[0]
    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('OTRA PRUEBA', 'PROVEEDOR')")
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) VALUES "
              "('EQK4M', 'EQK4M', 'BOMBA DE AGUA', ?)", (c.lastrowid,))
    c.execute("INSERT INTO equivalencias (producto_a_id, producto_b_id) VALUES (?, ?)",
              (min(_bak4m, c.lastrowid), max(_bak4m, c.lastrowid)))
    conn.commit()
    at.session_state["modo_busqueda"] = "Descripción"
    at.run()
    at.text_input(key="texto_input").set_value("bomba de agua k4m")
    [b for b in at.button if "Buscar por descripción" in b.label][0].click().run()
    if "--base" not in sys.argv and not any("EQK4M" in str(d.value) for d in at.dataframe):
        fallas.append("por descripción, con un solo resultado sus equivalencias no se abren")
    _aparte = [e for e in at.expander if "que no dicen «k4m»" in e.label]
    if (not any("con todo lo pedido" in x.value for x in at.success) or len(_aparte) != 1
            or any("BAPAL" in str(d.value) for d in at.dataframe)):
        fallas.append(f"por descripción, lo que no nombra el auto: {[e.label for e in _aparte]}")
    _tablas_antes = len(at.dataframe)
    at.session_state["exp_texto_aparte"] = True
    at.run()
    # Con --base, lo apartado son 200 de la base real y el de prueba puede no entrar.
    if (len(at.dataframe) <= _tablas_antes if "--base" in sys.argv
            else not any("BAPAL" in str(d.value) for d in at.dataframe)):
        fallas.append("por descripción, abrir «Otros … que no dicen» no muestra la tabla")
    at.session_state["exp_texto_aparte"] = False
    # Y el filtro por rubro, con cuántos de cada uno: «clio k4m» trae la bomba y el filtro.
    # Seis o más: con menos no se ofrece filtrar.
    c.executemany("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) VALUES "
                  "(?, ?, ?, ?)", [("FAK4M", "FAK4M", "FILTRO DE AIRE RENAULT CLIO K4M", _marca_prueba)]
                  + [(f"FK{i}", f"FK{i}", f"FILTRO DE ACEITE RENAULT CLIO K4M {i}", _marca_prueba)
                     for i in range(4)])
    conn.commit()
    at.text_input(key="texto_input").set_value("clio k4m")
    [b for b in at.button if "Buscar por descripción" in b.label][0].click().run()
    _rubros = [x for x in at.selectbox if x.key == "filtro_rubro_texto"]
    if not _rubros or not any(o.startswith("Filtros (") for o in _rubros[0].options):
        fallas.append(f"por descripción, el filtro por rubro: {[x.options for x in _rubros]}")
    else:
        _rubros[0].set_value("Filtros").run()
        _tabla = [d for d in at.dataframe if "FAK4M" in str(d.value)]
        if not _tabla or "BAK4M" in str(_tabla[0].value):
            fallas.append("por descripción, elegir el rubro no deja solo los de ese rubro")
        at.session_state["filtro_rubro_texto"] = "Todos"
    # Y el motor: «termostato tu5jp4» ofrece la misma búsqueda con el auto, y el botón la hace.
    c.execute("INSERT INTO aplicaciones (marca_auto, modelo_auto, codigo, codigo_clean, origen) "
              "VALUES ('PEUGEOT', 'PARTNER', 'TU0', 'TU0', 'deducida')")
    c.executemany("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) VALUES "
                  "(?, ?, ?, ?)", [(f"TU{i}", f"TU{i}", f"TERMOSTATO PEUGEOT PARTNER 1.6 16V "
                                    f"TU5JP4 {i}", _marca_prueba) for i in range(1, 6)])
    conn.commit()
    ns["_MODELOS_CACHE"]["lista"] = None
    at.text_input(key="texto_input").set_value("termostato tu5jp4")
    [b for b in at.button if "Buscar por descripción" in b.label][0].click().run()
    _por_motor = [b for b in at.button if (b.key or "").startswith("motor_sug_")]
    if not _por_motor:
        fallas.append("por descripción, el motor no ofrece buscar por el auto")
    else:
        _otra = _por_motor[0].label.replace("🔎 ", "")
        _por_motor[0].click().run()
        if (at.session_state["texto_input"] != _otra
                or not any("coincidencia" in x.value for x in at.success)):
            fallas.append(f"por descripción, el botón del motor no busca «{_otra}»")
    # Y un código que no está, de una familia que sí: «mfla 260» no trae lo que dice 260 suelto
    # (un motor Ford); ofrece los de la familia, el más cercano primero (ver «UN NÚMERO PEDIDO
    # QUE NO DICE NINGUNO» en buscar_por_texto()).
    c.executemany("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) VALUES "
                  "(?, ?, ?, ?)", [("MFLA 258", "MFLA258", "CONECTOR MASSER", _marca_prueba),
                                   ("MFLA 272", "MFLA272", "CONECTOR MASSER", _marca_prueba),
                                   ("FM260", "FM260", "JUNTA MOTOR FORD 225/260/289", _marca_prueba)])
    conn.commit()
    at.text_input(key="texto_input").set_value("mfla 260")
    [b for b in at.button if "Buscar por descripción" in b.label][0].click().run()
    _cerca = [b for b in at.button if (b.key or "").startswith("cercano_txt_")]
    if (not _cerca or "MFLA 258" not in _cerca[0].label
            or any("coincidencia" in x.value for x in at.success)
            or not any("que no dicen «mfla 260»" in e.label for e in at.expander)):
        fallas.append(f"por descripción, un código que no está: {[b.label for b in _cerca]}")
    at.session_state["modo_busqueda"] = "Código"
    # Un código que no está, pero que una descripción tuya nombra: «REF ORIG MANN P716».
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) VALUES "
              "('FC14100', 'FC14100', 'FILTRO COMBUSTIBLE REF ORIG MANN P716', ?)", (_marca_prueba,))
    conn.commit()
    at.session_state["pagina_actual"] = ns["PAGINAS"][0]
    at.run()
    at.text_input(key="busqueda_input").set_value("P716")
    [b for b in at.button if "Buscar equivalencias" in b.label][0].click().run()
    if (not any("lo nombran en la descripción" in x.value for x in at.success)
            or not [b for b in at.button if (b.key or "").startswith("citan_P716_")]):
        fallas.append("un código que una descripción nombra: no se ofrece")
    elif _ids_de_los_botones(at, "citan_P716_") & _ids_de_los_botones(at, "sug_P716_"):
        # El mismo producto en «lo nombran» y en «¿quisiste decir?». Con la base real, abajo
        # puede haber OTROS productos que dicen P716 de otra forma: esos sí van.
        fallas.append("un código que una descripción nombra: aparece dos veces")
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
    # ⚡ La revisión de a uno: la tarjeta con los dos productos, y «✅ Son la misma pieza»
    # aprueba ese par y pasa al siguiente (ver cola_de_revision_de_a_uno()).
    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('UNO A UNO', 'PROVEEDOR')")
    _m_u = c.lastrowid
    _ids_u = []
    for _cod, _desc in (("UA1", "FILTRO ACEITE FIAT DUNA"), ("UB1", "FILTRO ACEITE FIAT DUNA 1.4"),
                        ("UA2", "FILTRO ACEITE FIAT UNO"), ("UB2", "FILTRO ACEITE FIAT UNO 1.3")):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
                  "VALUES (?, ?, ?, ?)", (_cod, _cod, _desc, _marca_prueba if _cod[1] == "A" else _m_u))
        _ids_u.append(c.lastrowid)
    c.executemany("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, lote) "
                  "VALUES (?, ?, 'lista_proveedor', 'DE A UNO EN PANTALLA')",
                  [(_ids_u[0], _ids_u[1]), (_ids_u[2], _ids_u[3])])
    # Y otra lista más nueva, que va primera en el selector: decidir no tiene que mandar ahí
    # (el selector elegía por el rótulo con la cantidad, y cada decisión la cambiaba).
    c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, lote, "
              "fecha) VALUES (?, ?, 'lista_proveedor', 'OTRA LISTA MAS NUEVA', '2099-01-01')",
              (_ids_u[0], _ids_u[3]))
    conn.commit()
    # Lo decidido antes con los avisos de esos pares (ver «LO QUE DECIDISTE CON CADA AVISO»):
    # la tarjeta lo tiene que mostrar.
    _avisos_u = {a for f in sum(ns["analizar_lote_pendiente"]("DE A UNO EN PANTALLA")[:2], [])
                 for a in ns["_avisos_que_cuentan"](f)}
    ns["guardar_config"](ns["LO_DECIDIDO_CON_CADA_AVISO"], ns["json"].dumps(
        {"version": ns["VERSION_CONFIANZA"], "forma": ns["FORMA_DE_LO_DECIDIDO"],
         "avisos": {a: [7, 1] for a in _avisos_u}}))
    at.session_state["pagina_actual"] = "📊 Estadísticas"
    at.session_state["sub_stats"] = "🔗 Equivalencias sugeridas"
    at.run()
    _lotes_u = [o for o in (at.selectbox(key="lote_en_revision").options
                            if any(x.key == "lote_en_revision" for x in at.selectbox) else [])
                if o.startswith("DE A UNO EN PANTALLA")]
    if not _lotes_u:
        fallas.append("de a uno: la lista de prueba no aparece para revisar")
    else:
        at.selectbox(key="lote_en_revision").set_value("DE A UNO EN PANTALLA").run()
        at.toggle(key="de_a_uno_DE A UNO EN PANTALLA").set_value(True).run()
        _si = [b for b in at.button if b.key == "de_a_uno_si"]
        if not _si or not any("FILTRO ACEITE FIAT" in x.value for x in at.caption):
            fallas.append("de a uno: no se ve la tarjeta con los dos productos")
        elif not any("📒 Antes" in x.value and "aprobaste 7 de 8" in x.value for x in at.markdown):
            fallas.append("de a uno: la tarjeta no dice lo que decidiste antes con esos avisos")
        elif not any("🔍 Solo en" in x.value and "1.4" in x.value for x in at.markdown):
            fallas.append("de a uno: la tarjeta no dice lo que dice uno solo (el 1.4)")
        else:
            _si[0].click().run()
            if c.execute("SELECT COUNT(*) FROM equivalencias_pendientes WHERE lote = "
                         "'DE A UNO EN PANTALLA'").fetchone()[0] != 1:
                fallas.append("de a uno: «Son la misma pieza» no aprobó el par")
            elif not any("quedan 1 en la cola" in x.value for x in at.markdown):
                fallas.append("de a uno: después de decidir no pasa al siguiente")
            else:
                # Y «↩️ Deshacer» lo vuelve a la cola, primero (ver deshacer_de_a_uno()).
                _deshacer = [b for b in at.button if b.key == "de_a_uno_deshacer"]
                if _deshacer:
                    _deshacer[0].click().run()
                if (not _deshacer or c.execute(
                        "SELECT COUNT(*) FROM equivalencias_pendientes WHERE lote = "
                        "'DE A UNO EN PANTALLA'").fetchone()[0] != 2
                        or not any("quedan 2 en la cola" in x.value for x in at.markdown)
                        or not any("Deshecho" in x.value for x in at.info)):
                    fallas.append("de a uno: «↩️ Deshacer» no vuelve el par a la cola")
    # 💲 Los códigos que vinieron dos veces con dos precios: la tarjeta con un botón por precio
    # (ver elegir_el_precio_doble()). «Cambiar a» guarda ese precio y el código sale de la
    # lista. Con la base real hay otros antes, y no se toca nada: solo que esté la tarjeta.
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio) "
              "VALUES ('DOBLE1', 'DOBLE1', 'JUNTA TAPA DE CILINDROS', ?, 500)", (_marca_prueba,))
    _doble = c.lastrowid
    c.executemany("INSERT INTO historial_precios (producto_id, precio) VALUES (?, ?)",
                  [(_doble, 100), (_doble, 500)])
    conn.commit()
    _solapas_adm, _clave_adm = ns["SOLAPAS_DE_LA_PAGINA"]["🗂️ Administrar"]
    at.session_state["pagina_actual"] = "🗂️ Administrar"
    at.session_state[_clave_adm] = ns["SUB_ADMIN"][4]
    at.session_state["sub_mantenimiento"] = ns["GRUPOS_MANTENIMIENTO"][1]
    at.run()
    _cambiar = [b for b in at.button
                if (b.key or "").startswith("dos_precios_") and "Cambiar a" in b.label]
    if not _cambiar:
        fallas.append("💲 dos precios: no está la tarjeta para elegir el precio")
    elif "--base" not in sys.argv:
        if not any("DOBLE1" in x.value for x in at.markdown):
            fallas.append("💲 dos precios: la tarjeta no muestra el código")
        _cambiar[0].click().run()
        if c.execute("SELECT precio FROM productos WHERE id = ?", (_doble,)).fetchone()[0] != 100:
            fallas.append("💲 dos precios: «Cambiar a» no guardó el precio")
        elif (any("DOBLE1" in x.value for x in at.markdown)
              or not any("Cambió a" in x.value and "No queda ninguno" in x.value
                         for x in at.success)):
            fallas.append("💲 dos precios: después de elegir sigue en la lista, o no lo dice")
    at.session_state["pagina_actual"] = ns["PAGINAS"][0]
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
        # Las más lentas también cuando algo falla: con --base es lo que se viene a buscar, y
        # algunas pruebas de la base chica no se cumplen con la base real (P716 aparece en más
        # listas), así que antes no se veían nunca.
        _lentas = ", ".join(f"{d} {s:.1f} s" for s, d in lentas)
        print(f"✅ pantallas: las {cuantas} en verde (las más lentas: {_lentas})" if not fallas
              else f"{len(fallas)} falla(s) en {cuantas} pantallas (las más lentas: {_lentas})")
        return 1 if fallas else 0
    finally:
        os.chdir(RAIZ)
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

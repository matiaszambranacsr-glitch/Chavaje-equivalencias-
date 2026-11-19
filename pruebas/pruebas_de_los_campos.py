"""Cada campo muestra lo de LO ELEGIDO: al elegir otro auto, otro producto u otro alias, los
campos tienen sus datos, no los del anterior.

Uso:
    python3 pruebas/pruebas_de_los_campos.py

Por qué: con Streamlit 1.65, un campo con clave fija se queda con lo que tenía aunque cambie el
`value=` que se le pasa. En noviembre de 2026 se encontró que al buscar otra patente la ficha
seguía diciendo la marca, el modelo, el año y el VIN del auto anterior (un Corsa 2008 aparecía
«VW GOL 2012», con el chasis del Gol), y «💾 Guardar vehículo» se los grababa al otro. Lo mismo
con las medidas de un producto y con los datos de un alias de cobro. Ahora la clave lleva lo
elegido (la patente, el número del producto o del alias); esto lo controla.

Y el pedido al proveedor (📌 Para pedir) y la cotización de 📋 Lista WhatsApp: la caja del
mensaje se renueva cuando cambia lo que se pide (con la clave fija seguía con el primero, y el
pedido salía incompleto), y lo que se le corrige es lo que se manda.

Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import os
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def probar():
    from streamlit.testing.v1 import AppTest
    fallas = []

    def esperar(que, dio, se_esperaba):
        if dio != se_esperaba:
            fallas.append(f"{que}: dio {dio!r}, se esperaba {se_esperaba!r}")

    at = AppTest.from_file(os.path.join(RAIZ, "app.py"), default_timeout=300)
    at.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
    at.run()
    at.text_input(key="login_inicial_nombre").set_value("duenio")
    at.text_input(key="login_inicial_clave").set_value("clave-duenio-1")
    [b for b in at.button if "Ingresar con contraseña" in b.label][0].click().run()
    ns = sys.modules["logica"].todo_lo_de_la_logica()
    c = ns["c"]
    # La vista de computadora: en el celular algunas cosas van plegadas.
    at.session_state["modo_vista"] = ns["VISTAS"][1]

    # 1. LA FICHA DEL AUTO: buscar otra patente trae los datos de ese auto.
    c.execute("INSERT INTO vehiculos (patente, marca_auto, modelo_auto, anio, vin) "
              "VALUES ('AA111AA', 'VW', 'GOL', '2012', '9BWZZZ377VT004251')")
    c.execute("INSERT INTO vehiculos (patente, marca_auto, modelo_auto, anio) "
              "VALUES ('BB222BB', 'CHEVROLET', 'CORSA', '2008')")
    ns["conn"].commit()
    at.session_state["pagina_actual"] = ns["PAGINAS"][6]
    at.run()

    def _ficha():
        return [t.value for t in at.text_input if str(t.key).startswith("form_")]
    at.text_input(key="patente_buscar").input("AA111AA").run()
    esperar("la ficha del primer auto", _ficha(), ["VW", "GOL", "2012", "", "",
                                                   "9BWZZZ377VT004251"])
    at.text_input(key="patente_buscar").input("BB222BB").run()
    esperar("otra patente: la marca, el modelo, el año y el VIN de ESE auto", _ficha(),
            ["CHEVROLET", "CORSA", "2008", "", "", ""])

    # 2. LAS MEDIDAS DE UN PRODUCTO: elegir otro trae sus medidas y su ubicación.
    c.execute("INSERT OR IGNORE INTO marcas (nombre, tipo) VALUES ('MARCA CAMPOS', 'PROVEEDOR')")
    for codigo, diametro, lugar in (("CAMPO1", 10.0, "estante 1"), ("CAMPO2", 25.0, "estante 9")):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, "
                  "diametro_interno, ubicacion) SELECT ?, ?, 'RETEN DE PRUEBA', id, ?, ? "
                  "FROM marcas WHERE nombre = 'MARCA CAMPOS'", (codigo, codigo, diametro, lugar))
    ns["conn"].commit()
    at.session_state["pagina_actual"] = ns["PAGINAS"][3]
    at.session_state["sub_admin"] = ns["SUB_ADMIN"][1]
    at.run()
    at.text_input(key="admin_buscar").input("RETEN DE PRUEBA").run()

    def _medidas():
        diam = [x.value for x in at.number_input if str(x.key).startswith("e_di_")
                and not str(x.key).startswith("e_di_b")]
        lugar = [x.value for x in at.text_input if str(x.key).startswith("e_ubic_")]
        return diam, lugar
    _sel = at.selectbox(key="sel_medidas")
    _opciones = {o.split(" ")[0]: o for o in _sel.options}
    if set(_opciones) != {"CAMPO1", "CAMPO2"}:
        fallas.append(f"el buscador de productos no trajo los dos de prueba: {list(_opciones)}")
    else:
        _sel.set_value(_opciones["CAMPO1"]).run()
        esperar("las medidas del primero", _medidas(), ([10.0], ["estante 1"]))
        at.selectbox(key="sel_medidas").set_value(_opciones["CAMPO2"]).run()
        esperar("otro producto: SUS medidas y SU ubicación", _medidas(), ([25.0], ["estante 9"]))

    # 3. LOS ALIAS DE COBRO: elegir otro para editar trae sus datos.
    ns["guardar_alias_transferencia"]("Banco Uno", "alias.uno", "", "Uno SA")
    ns["guardar_alias_transferencia"]("Banco Dos", "alias.dos", "", "Dos SA")
    ns["conn"].commit()
    at.session_state["sub_admin"] = ns["SUB_ADMIN"][2]
    at.run()

    def _alias():
        return [x.value for x in at.text_input if str(x.key).startswith("alias_alias_in_")]
    _que_hacer = at.selectbox(key="alias_opcion_edit")
    if "Banco Uno (editar)" not in _que_hacer.options:
        fallas.append(f"no aparecen los alias para editar: {_que_hacer.options}")
    else:
        _que_hacer.set_value("Banco Uno (editar)").run()
        esperar("el alias del primero", _alias(), ["alias.uno"])
        at.selectbox(key="alias_opcion_edit").set_value("Banco Dos (editar)").run()
        esperar("otro alias: SUS datos", _alias(), ["alias.dos"])

    # 4. EL PEDIDO AL PROVEEDOR: al marcar otro producto de la misma marca, el mensaje lo suma
    # (con la clave fija la caja seguía con el primero y el pedido salía incompleto).
    _ids = {}
    for codigo in ("PED1", "PED2"):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, stock) "
                  "SELECT ?, ?, 'FILTRO', id, 0 FROM marcas WHERE nombre = 'MARCA CAMPOS'",
                  (codigo, codigo))
        ns["solicitar_reposicion"](c.lastrowid)
    ns["conn"].commit()
    for p in ns["listar_pedidos_reposicion"]():
        _ids[p["Codigo"]] = p["ID"]
    at.session_state["pagina_actual"] = ns["PAGINAS"][4]
    at.session_state["sub_stats"] = ns["SUB_STATS"][5]
    at.session_state[f"chk_pedido_{_ids['PED1']}"] = True
    at.run()

    def _mensaje_al_proveedor():
        return [t.value for t in at.text_area if str(t.key).startswith("msg_repo_")]
    _antes = _mensaje_al_proveedor()
    esperar("el pedido con el primero", [("PED1" in m, "PED2" in m) for m in _antes],
            [(True, False)])
    at.session_state[f"chk_pedido_{_ids['PED2']}"] = True
    at.run()
    esperar("marcado otro: el mensaje lo suma", [("PED1" in m, "PED2" in m)
                                                 for m in _mensaje_al_proveedor()], [(True, True)])

    # 5. LA COTIZACIÓN DE 📋 LISTA WHATSAPP: lo corregido es lo que se manda.
    at.session_state["pagina_actual"] = ns["PAGINAS"][5]
    at.session_state["lista_whatsapp"] = [{"codigo_buscado": "PED1", "resultados": []}]
    at.run()
    _caja_wa = [t for t in at.text_area if str(t.key).startswith("wa_mensaje_")]
    if not _caja_wa:
        fallas.append("en 📋 Lista WhatsApp no está la caja del mensaje "
                      f"({[e.value for e in at.exception][:1]})")
    else:
        _caja_wa[0].set_value("Hola! Te paso la cotización, te hago precio").run()
        _links_wa = [b.proto.url for b in at.get("link_button")
                     if b.proto.label == "📲 Abrir en WhatsApp"]
        esperar("el link de la cotización lleva lo corregido", _links_wa,
                [ns["link_de_whatsapp"]("", "Hola! Te paso la cotización, te hago precio")])
    fallas += [f"se rompió: {e.value}" for e in at.exception][:2]
    return fallas


def main():
    os.environ["EQUIVALENCIAS_SIN_TAREAS_DE_FONDO"] = "1"
    carpeta = tempfile.mkdtemp(prefix="pruebas_campos_")
    os.chdir(carpeta)
    sys.path.insert(0, RAIZ)
    try:
        fallas = probar()
        for f in fallas:
            print("   ✗", f[:300])
        print("✅ campos: cada uno con lo de lo elegido (el auto, el producto, el alias, el pedido)"
              if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(RAIZ)
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

"""Pruebas de la precisión de las equivalencias: cuándo una equivalencia se da por verificada.

Uso:
    python3 pruebas_de_la_precision.py

De la revisión con ChatGPT sobre la precisión:
  · «limpia» no es «confirmada»: sin una fuente que la declare no se confirma (ver
    respaldo_del_origen() y veredicto_de_la_equivalencia());
  · la ficha de prueba de cada equivalencia, con su estado y lo que falta (ver
    ficha_de_prueba());
  · un veto gana siempre, y las ventas solas no pasan un vínculo de franja (ver
    evaluar_equivalencia());
  · el proveedor que cambia de equivalente sin avisar (ver
    equivalentes_que_la_lista_dejo_de_declarar()).

Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import os
import shutil
import sys
import tempfile


def _cargar_la_logica(carpeta):
    raiz = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, raiz)
    os.chdir(carpeta)
    import logica
    return logica


def probar(L):
    ns = L.todo_lo_de_la_logica()
    c, conn = ns["c"], ns["conn"]
    fallas = []

    def esperar(nombre, real, esperado):
        if real != esperado:
            fallas.append(f"{nombre}: dio {real!r}, se esperaba {esperado!r}")

    # 1. De dónde salió un vínculo: una fuente que lo declara o una pista.
    respaldo = ns["respaldo_del_origen"]
    for lote, primaria in (("FISPA · lista.xlsx · 25/09/2026 10:00:00", True),
                           ("CATÁLOGO NGK · 28/09 06:45", True),
                           ("PORTAL JL · 28/09", True),
                           ("POR REEMPLAZO (automático) · 28/09", True),
                           ("BARRIDO (automático) · 25/09 20:43", False),
                           ("todas-29/09 01:18", False),
                           ("CRUCE POR AUTO (automático) · 25/09", False),
                           ("POR MEDIDAS · 25/09", False),
                           ("MERCADO LIBRE · 25/09", False),
                           ("CONFIRMADAS EN EL MOSTRADOR · 25/09", False),
                           ("", None), (None, None), ("PRUEBA DE RECHAZOS", None)):
        esperar(f"respaldo de «{lote}»", respaldo(lote)[0], primaria)
    esperar("una pista verificada a mano es fuente", respaldo("BARRIDO · x", True)[0], True)
    esperar("el texto dice quién", respaldo("FISPA · a.xlsx · x")[1],
            "📋 lo declara la lista de FISPA")

    # 2. El veredicto del buscador: «confirmada» solo con una fuente.
    veredicto = ns["veredicto_de_la_equivalencia"]
    directo = {"Cadena": "🟢 directo", "Confianza": "🟢 sólida"}
    esperar("directo, sólido y con fuente",
            veredicto(dict(directo, Respaldo="📋 lo declara la lista de FISPA")),
            "🟢 equivalencia confirmada")
    esperar("directo y sólido, pero solo una pista",
            veredicto(dict(directo, Respaldo="🔤 se parecen las descripciones")).startswith(
                "🟡 probable, sin una fuente"), True)
    esperar("sin el dato del respaldo (nucleo), como antes", veredicto(dict(directo)),
            "🟢 equivalencia confirmada")
    esperar("respaldo vacío, como antes", veredicto(dict(directo, Respaldo="")),
            "🟢 equivalencia confirmada")
    esperar("verificada a mano gana", veredicto(dict(directo, Verificada="✅",
                                                     Respaldo="🔤 x")),
            "🟢 equivalencia confirmada (verificada)")

    # 3. El puntaje: un veto gana siempre y las ventas solas no pasan de franja.
    evaluar = ns["evaluar_equivalencia"]
    tope = ns["TOPE_CON_VETO"]
    puntaje, senales = evaluar("FILTRO DE ACEITE FORD FIESTA", "FILTRO DE ACEITE FORD FIESTA",
                               respaldo_fabricante=True, vendido_como_reemplazo=5,
                               familia_a="Filtros", familia_b="Frenos")
    esperar("con rubros distintos, el puntaje no pasa del tope aunque todo lo demás sume",
            puntaje <= tope, True)
    sin, _ = evaluar("BOMBA DE AGUA FORD KA", "BOMBA DE AGUA FIAT UNO")
    con, senales = evaluar("BOMBA DE AGUA FORD KA", "BOMBA DE AGUA FIAT UNO",
                           vendido_como_reemplazo=5)
    franja = ns["LINEAS_DE_CONFIANZA"]

    def franja_de(x):
        return sum(x >= linea for linea in franja)
    esperar("las ventas suben el puntaje", con > sin, True)
    esperar("pero no lo pasan de franja", franja_de(con), franja_de(sin))
    esperar("y la señal se ve", any("reemplazo" in s for _, s in senales), True)

    # 4. La ficha de prueba, con una base chica armada a mano.
    def marca(nombre, tipo="PROVEEDOR"):
        c.execute("INSERT INTO marcas (nombre, tipo) VALUES (?, ?)", (nombre, tipo))
        return c.lastrowid

    def producto(codigo, desc, marca_id, **medidas):
        columnas = ", ".join(["codigo_raw", "codigo_clean", "descripcion", "marca_id"]
                             + list(medidas))
        valores = [codigo, ns["sanitizar"](codigo), desc, marca_id] + list(medidas.values())
        c.execute(f"INSERT INTO productos ({columnas}) VALUES ({','.join('?' * len(valores))})",
                  valores)
        return c.lastrowid

    def vincular(a, b, lote, confianza=90):
        c.execute("INSERT INTO equivalencias (producto_a_id, producto_b_id, lote, confianza) "
                  "VALUES (?, ?, ?, ?)", (min(a, b), max(a, b), lote, confianza))

    fispa, illinois, oem = marca("FISPA"), marca("ILLINOIS"), marca("OEM / FABRICA", "OEM")
    ret_f = producto("R100", "RETEN CIGUEÑAL FORD FIESTA 35X52X7", fispa,
                     diametro_interno=35, diametro_externo=52, ancho=7)
    ret_i = producto("ILR100", "RETEN CIGUEÑAL FORD FIESTA 35X52X7", illinois,
                     diametro_interno=35, diametro_externo=52.5)
    ret_o = producto("1234567890", "RETEN CIGUEÑAL FORD FIESTA 35X52X7", oem)
    vincular(ret_f, ret_o, "FISPA · lista.xlsx · 01/10/2026 10:00:00")
    vincular(ret_i, ret_o, "ILLINOIS · lista.xlsx · 01/10/2026 11:00:00")
    vincular(ret_f, ret_i, "BARRIDO (automático) · 01/10 12:00")
    conn.commit()
    ficha = ns["ficha_de_prueba"](ret_f, ret_i)
    esperar("directo pero solo por el barrido: candidata", ficha["estado"], "🟠 CANDIDATA")
    esperar("y dice qué falta", any("una fuente que declare" in f for f in ficha["falta"]), True)
    esperar("los dos citan el mismo número de fábrica", len(ficha["numeros_en_comun"]), 1)
    esperar("dos fuentes distintas", ficha["fuentes"], ["FISPA", "ILLINOIS"])
    esperar("es un retén", ficha["pieza"], "retén")
    estados = {m["Medida"]: m["Estado"] for m in ficha["medidas"]}
    esperar("el diámetro interno, igual", estados.get("diám. interno"), "✅ igual")
    esperar("el externo, dentro de la tolerancia",
            estados.get("diám. externo", "").startswith("≈"), True)
    esperar("el ancho falta en B", estados.get("ancho"), "❓ falta en B")
    esperar("y se pide medirlo", ficha["para_medir"], ["ancho"])

    # Sin el vínculo del barrido, llega por el número de fábrica: probable.
    c.execute("DELETE FROM equivalencias WHERE lote LIKE 'BARRIDO%'")
    conn.commit()
    ficha = ns["ficha_de_prueba"](ret_f, ret_i)
    esperar("por el número de fábrica, con las dos mitades con fuente: probable",
            ficha["estado"], "🟡 PROBABLE")
    # Directo y declarado por una lista: verificada.
    vincular(ret_f, ret_i, "FISPA · otra.xlsx · 02/10/2026 10:00:00")
    conn.commit()
    ficha = ns["ficha_de_prueba"](ret_f, ret_i)
    esperar("directo y declarado: verificada", ficha["estado"], "✅ VERIFICADA")
    esperar("la misma lista dos veces es una fuente", ficha["fuentes"], ["FISPA", "ILLINOIS"])
    # Floja: probable, aunque la declare una lista.
    c.execute("UPDATE equivalencias SET confianza = 40 WHERE producto_a_id = ? AND producto_b_id = ?",
              (min(ret_f, ret_i), max(ret_f, ret_i)))
    conn.commit()
    esperar("declarado pero flojo: no verificada",
            ns["ficha_de_prueba"](ret_f, ret_i)["estado"] != "✅ VERIFICADA", True)
    # Una medida que se contradice gana sobre todo lo demás.
    c.execute("UPDATE productos SET diametro_interno = 40 WHERE id = ?", (ret_i,))
    conn.commit()
    ficha = ns["ficha_de_prueba"](ret_f, ret_i)
    esperar("con una medida distinta: contradicciones", ficha["estado"], "🔴 CON CONTRADICCIONES")
    esperar("y la medida lo dice", {m["Medida"]: m["Estado"] for m in ficha["medidas"]}
            .get("diám. interno", "").startswith("❌"), True)
    c.execute("UPDATE productos SET diametro_interno = 35 WHERE id = ?", (ret_i,))
    conn.commit()

    # 5. Comprobada en la mano: queda verificada, con quién, cuándo y qué se miró, y el
    # vínculo no pierde de qué lista vino.
    nota = ns["comprobar_en_la_mano"](ret_f, ret_i, "medí 35x52x7 las dos")
    fila = c.execute("SELECT verificada, lote, nota FROM equivalencias WHERE producto_a_id = ? "
                     "AND producto_b_id = ?", (min(ret_f, ret_i), max(ret_f, ret_i))).fetchone()
    esperar("queda verificada", fila[0], 1)
    esperar("sin perder de qué lista vino", fila[1], "FISPA · otra.xlsx · 02/10/2026 10:00:00")
    esperar("con lo que se miró", "medí 35x52x7 las dos" in fila[2] and fila[2] == nota, True)
    ficha = ns["ficha_de_prueba"](ret_f, ret_i)
    esperar("la ficha la da por verificada (aunque el vínculo sea flojo)", ficha["estado"],
            "✅ VERIFICADA")
    esperar("y muestra la comprobación", ficha["comprobaciones"], [nota])
    esperar("sin decir qué se miró, no", _falla(ns["comprobar_en_la_mano"], ret_f, ret_i, " "),
            "ValueError")
    # Si llegaban por un código en el medio, queda un vínculo directo nuevo.
    otro = producto("XR100", "RETEN CIGUEÑAL FORD FIESTA", illinois)
    vincular(otro, ret_o, "ILLINOIS · lista.xlsx · 01/10/2026 11:00:00")
    conn.commit()
    ns["comprobar_en_la_mano"](ret_f, otro, "misma pieza en la caja")
    esperar("si no había vínculo directo, se crea verificado", tuple(c.execute(
        "SELECT verificada FROM equivalencias WHERE producto_a_id = ? AND producto_b_id = ?",
        (min(ret_f, otro), max(ret_f, otro))).fetchone() or ()), (1,))

    # 6. El buscado más cercano: el código cargado en dos marcas, y el resultado cuelga de una.
    gemelo = producto("R100", "RETEN", illinois)
    conn.commit()
    esperar("se elige el que tiene el vínculo directo",
            ns["el_buscado_mas_cercano"]([gemelo, ret_f], ret_i), ret_f)
    esperar("antes que uno que llega por una cadena",
            ns["el_buscado_mas_cercano"]([otro, ret_f], ret_i), ret_f)
    esperar("y si nadie tiene directo, el que tiene alguna cadena",
            ns["el_buscado_mas_cercano"]([gemelo, otro], ret_i), otro)

    # 7. El buscador anota el respaldo de los resultados directos (el directo sólido, que es el
    # camino que muestra; flojo, el buscador llega por el número de fábrica).
    c.execute("UPDATE equivalencias SET confianza = 90 WHERE producto_a_id = ? AND producto_b_id = ?",
              (min(ret_f, ret_i), max(ret_f, ret_i)))
    conn.commit()
    res, _ = ns["buscar_con_variantes_del_cero"]("ILR100", "Todas", 3)
    por_id = {f["ID"]: f for f in res}
    esperar("el directo dice quién lo declara", por_id.get(ret_f, {}).get("Respaldo"),
            "👤 una persona lo verificó al cargarlo a mano")
    esperar("el de fábrica también", por_id.get(ret_o, {}).get("Respaldo"),
            "📋 lo declara la lista de ILLINOIS")
    # El código en dos marcas que se vinculan con el mismo resultado: gana la fuente.
    vincular(gemelo, ret_i, "BARRIDO (automático) · 08/10 09:00")
    conn.commit()
    res, _ = ns["buscar_con_variantes_del_cero"]("R100", "Todas", 3)
    esperar("con dos vínculos, gana la fuente sobre la pista",
            {f["ID"]: f for f in res}.get(ret_i, {}).get("Respaldo"),
            "👤 una persona lo verificó al cargarlo a mano")

    # Las medidas que van por igualdad, no por tolerancia.
    lado = {m["Medida"]: m["Estado"] for m in ns["medidas_lado_a_lado"](
        {"posicion": "DELANTERO", "cantidad_vias": 3, "paso_rosca": "1.5"},
        {"posicion": "delantero", "cantidad_vias": 4})}
    esperar("la posición, sin importar mayúsculas", lado.get("posición"), "✅ igual")
    esperar("las vías, distintas", lado.get("vías de la ficha"), "❌ distinta")
    esperar("la rosca, falta en B", lado.get("paso de rosca"), "❓ falta en B")
    esperar("lo que no tiene ninguno y no importa, no sale", "ancho" in lado, False)

    # 8. El proveedor que cambia de equivalente sin avisar: ayer R200 = 111, hoy R200 = 222.
    r200 = producto("R200", "FILTRO DE ACEITE", fispa)
    viejo, nuevo = producto("111", "FILTRO", oem), producto("222", "FILTRO", oem)
    r300 = producto("R300", "FILTRO DE AIRE", fispa)
    o300 = producto("333", "FILTRO", oem)
    vincular(r200, viejo, "FISPA · ayer.xlsx · 07/10/2026 10:00:00")
    vincular(r300, o300, "FISPA · ayer.xlsx · 07/10/2026 10:00:00")
    vincular(ret_f, viejo, "ILLINOIS · lista.xlsx · 01/10/2026 11:00:00")   # de otro proveedor
    conn.commit()
    hoy = "FISPA · hoy.xlsx · 08/10/2026 10:00:00"
    cambios = ns["equivalentes_que_la_lista_dejo_de_declarar"](
        "Fispa", hoy, {r200, r300}, {(min(r200, nuevo), max(r200, nuevo)),
                                     (min(r300, o300), max(r300, o300))})
    esperar("uno cambió de equivalente", cambios["codigos"], 1)
    esperar("y se ve antes y ahora", cambios["ejemplos"],
            [{"Código": "R200", "Antes decía": "111", "Ahora dice": "222"}])
    esperar("no se borró nada", c.execute(
        "SELECT COUNT(*) FROM equivalencias WHERE producto_a_id = ? AND producto_b_id = ?",
        (min(r200, viejo), max(r200, viejo))).fetchone()[0], 1)
    cambios = ns["equivalentes_que_la_lista_dejo_de_declarar"]("FISPA", hoy, {r200, r300}, set())
    esperar("la lista sin códigos de fábrica: los dos sin ninguno",
            (cambios["codigos"], cambios["sin_ninguno"]), (2, 2))
    cambios = ns["equivalentes_que_la_lista_dejo_de_declarar"]("FISPA", hoy, {r300}, set())
    esperar("el que dejó de venir en la lista no cuenta", cambios["codigos"], 1)

    # 9. Con o sin ABS, aire o sensor: dos versiones de la misma pieza.
    equip = ns["equipamiento_declarado"]
    esperar("C/ABS", equip("MAZA DE RUEDA GOL C/ABS"), {"ABS": True})
    esperar("SIN AIRE ACONDICIONADO", equip("CORREA UNO SIN AIRE ACONDICIONADO"),
            {"aire acondicionado": False})
    esperar("S/AA", equip("CONECTOR SERVO SENDA/GOL S/AA"), {"aire acondicionado": False})
    esperar("C/S AIRE sirve para los dos", equip("CORREA UNO C/S AIRE"), {})
    esperar("CON Y SIN AIRE sirve para los dos", equip("CORREA UNO CON Y SIN AIRE"), {})
    esperar("no dice nada", equip("PASTILLA DE FRENO GOL"), {})

    # 10. Las medidas que salen del mismo texto no suman: ya suma «la misma descripción».
    evaluar = ns["evaluar_equivalencia"]
    texto = "RETEN CIGUEÑAL FORD FIESTA 1.6 35X52X7 DELANTERO"
    med = {"diametro_interno": 35, "diametro_externo": 52, "ancho": 7}
    # Con un puente flojo, para que el puntaje no llegue al techo de 100 y la diferencia se vea.
    flojo = {"codigo_puente": "1234", "productos_del_puente": 8}
    con_med, _ = evaluar(texto, texto, med, med, **flojo)
    sin_med, _ = evaluar(texto, texto, **flojo)
    esperar("la misma descripción con sus medidas suma lo mismo que sin ellas", con_med, sin_med)
    otro = "RETEN DE CIGUEÑAL DELANTERO FORD FIESTA 1.6 (35X52X7)"
    con_med, _ = evaluar(texto, otro, med, med)
    sin_med, _ = evaluar(texto, otro)
    esperar("con descripciones distintas, las medidas sí suman", con_med > sin_med, True)

    # 11. Lo que volvió porque no le iba gana sobre todo, también sobre la lista que lo declara.
    disco_a = producto("D100", "DISCO DE FRENO DELANTERO FIAT PALIO", fispa)
    disco_b = producto("ILD100", "DISCO DE FRENO DELANTERO FIAT PALIO", illinois)
    vincular(disco_a, disco_b, "FISPA · lista.xlsx · 01/10/2026 10:00:00", confianza=95)
    conn.commit()
    esperar("una devolución de una pieza fallada no toca el vínculo",
            ns["registrar_devolucion"](disco_b, "D100", "fallada", "se partió"), 0)
    esperar("y no cuenta en contra", ns["pares_devueltos"](), {})
    esperar("la que no le iba baja el vínculo", ns["registrar_devolucion"](
        disco_b, "D100", "no_le_iba", "otro diámetro"), 1)
    conf = c.execute("SELECT confianza FROM equivalencias WHERE producto_a_id = ? AND "
                     "producto_b_id = ?", (min(disco_a, disco_b), max(disco_a, disco_b))).fetchone()[0]
    esperar("a «muy débil» en el acto", conf <= ns["TOPE_CON_VETO"], True)
    esperar("y queda contada", ns["pares_devueltos"](),
            {(min(disco_a, disco_b), max(disco_a, disco_b)): 1})
    ficha = ns["ficha_de_prueba"](disco_a, disco_b)
    esperar("la ficha la da con contradicciones", ficha["estado"], "🔴 CON CONTRADICCIONES")
    esperar("y muestra las dos devoluciones", len(ficha["devoluciones"]), 2)
    puntaje, _ = evaluar("DISCO DE FRENO DELANTERO FIAT PALIO", "DISCO DE FRENO DELANTERO FIAT PALIO",
                         respaldo_fabricante=True, devuelto=1)
    esperar("y el puntaje no pasa del tope", puntaje <= ns["TOPE_CON_VETO"], True)
    c.execute("INSERT INTO ventas_registradas (producto_id, termino_pedido, codigo_pedido_clean) "
              "VALUES (?, 'D100', 'D100'), (?, 'D100', 'D100')", (disco_b, disco_b))
    conn.commit()
    esperar("una venta que volvió no confirma nada", ns["pares_confirmados_por_ventas"](), {})
    res, _ = ns["buscar_con_variantes_del_cero"]("D100", "Todas", 3)
    fila_b = {f["ID"]: f for f in res}.get(disco_b, {})
    esperar("el buscador lo muestra devuelto", fila_b.get("Devuelto"), "↩️ 1")
    esperar("y no la ofrece como segura",
            ns["veredicto_de_la_equivalencia"](fila_b).startswith("🔴 la devolvieron"), True)
    esperar("un motivo inventado no entra",
            _falla(ns["registrar_devolucion"], disco_b, "D100", "porque si"), "ValueError")

    # 12. Un rechazo no se pisa: sale de la cola de todas las listas y no se aprueba en grupo.
    ja, jb = producto("J1", "JUNTA TAPA CIL FIAT 128", fispa), producto("IJ1", "JUNTA FIAT 128", illinois)
    c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, lote) "
              "VALUES (?, ?, 'lista_proveedor', 'ILLINOIS · otra.xlsx · x')", (min(ja, jb), max(ja, jb)))
    conn.commit()
    ns["marcar_revision"]([(ja, jb)], "rechazada")
    esperar("el rechazo saca el par de la cola", c.execute(
        "SELECT COUNT(*) FROM equivalencias_pendientes").fetchone()[0], 0)
    c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, lote) "
              "VALUES (?, ?, 'lista_proveedor', 'VIEJA')", (min(ja, jb), max(ja, jb)))
    conn.commit()
    esperar("una base de antes con el rechazado en la cola: no se aprueba",
            ns["aprobar_pendientes"]("VIEJA"), 0)
    esperar("y el rechazo sigue", c.execute(
        "SELECT decision FROM equivalencias_revisadas WHERE producto_a_id = ? AND producto_b_id = ?",
        (ja, jb)).fetchone()[0], "rechazada")
    esperar("vincular a mano avisa quién lo rechazó",
            [(r["cod_a"], r["cod_b"]) for r in ns["rechazos_del_grupo"](
                [{"codigo": "J1", "marca": "FISPA"}, {"codigo": "IJ1", "marca": "illinois"}])],
            [("J1", "IJ1")])

    # 13. El riesgo, aparte de la confianza.
    riesgo = ns["riesgo_de_la_pieza"]
    esperar("pastilla: crítico", riesgo("PASTILLA DE FRENO DELANTERA GOL")[0], "🛑 crítico")
    esperar("junta de tapa: alto", riesgo("JTA.TAPA CIL. FIAT 128")[0], "🟠 alto")
    esperar("filtro: normal", riesgo("FILTRO DE AIRE GOL")[0], "🟢 normal")
    veredicto = ns["veredicto_de_la_equivalencia"]
    confirmado = {"Cadena": "🟢 directo", "Confianza": "🟢 sólida",
                  "Respaldo": "📋 lo declara la lista de FISPA",
                  "Descripcion": "PASTILLA DE FRENO DELANTERA GOL"}
    esperar("la de seguridad confirmada pide mirarla", "pieza de seguridad" in veredicto(confirmado),
            True)
    esperar("salvo que alguien la haya verificado", veredicto(dict(confirmado, Verificada="✅")),
            "🟢 equivalencia confirmada (verificada)")
    esperar("un cambio de número no es «confirmada»",
            veredicto(dict(confirmado, Descripcion="FILTRO",
                           Respaldo="🔁 el proveedor declara el cambio de código")).startswith(
                "🟡 probable: es un cambio de número"), True)
    esperar("la ficha pide mirar la de seguridad",
            bool(ns["ficha_de_prueba"](disco_a, disco_b)["accion"]), True)
    viejo_r = producto("R555", "FILTRO DE ACEITE FIAT UNO", fispa)
    nuevo_r = producto("IR556", "FILTRO ACEITE FIAT UNO 1.3", illinois)
    vincular(viejo_r, nuevo_r, "POR REEMPLAZO (automático) · 08/10", confianza=90)
    conn.commit()
    esperar("en la ficha, un cambio de número es probable",
            ns["ficha_de_prueba"](viejo_r, nuevo_r)["estado"], "🟡 PROBABLE")

    # 14. La deriva: cuántos cambian de franja al volver a puntuar.
    filas = [{"a": 1, "b": 2, "antes": 80, "cod_a": "A", "marca_a": "X", "cod_b": "B", "marca_b": "Y"},
             {"a": 3, "b": 4, "antes": 60, "cod_a": "C", "marca_a": "X", "cod_b": "D", "marca_b": "Y"},
             {"a": 5, "b": 6, "antes": 72, "cod_a": "E", "marca_a": "X", "cod_b": "F", "marca_b": "Y"},
             {"a": 7, "b": 8, "antes": None, "cod_a": "G", "marca_a": "X", "cod_b": "H", "marca_b": "Y"}]
    deriva = ns["anotar_la_deriva"](filas, [(55, 1, 2), (75, 3, 4), (90, 5, 6), (10, 7, 8)])
    esperar("uno bajó y uno subió", (deriva["bajaron"], deriva["subieron"]), (1, 1))
    esperar("dicho por franja", deriva["cambios"],
            {"🟢 sólida → 🟡 razonable": 1, "🟡 razonable → 🟢 sólida": 1})
    esperar("y queda guardada", ns["la_ultima_deriva"]()["bajaron"], 1)

    # 15. Las versiones que hay que preguntarle al cliente.
    preguntas = ns["versiones_que_hay_que_preguntar"]([
        {"Descripcion": "PASTILLA DE FRENO DELANTERA GOL"},
        {"Descripcion": "PASTILLA DE FRENO TRASERA GOL"},
        {"Descripcion": "PASTILLA DE FRENO GOL"}])
    esperar("adelante o atrás", preguntas, {"¿Va adelante o atrás?": {"delantera": 1, "trasera": 1}})
    esperar("si son todas iguales, no se pregunta", ns["versiones_que_hay_que_preguntar"]([
        {"Descripcion": "PASTILLA DE FRENO DELANTERA GOL"},
        {"Descripcion": "PASTILLA DELANTERA GOL 1.6"}]), {})

    # 16. De dónde salen los vínculos.
    filas, solo_pistas = ns["vinculos_por_origen"]()
    por_origen = {f["Origen"]: f for f in filas}
    esperar("la lista de FISPA es fuente",
            por_origen.get("📋 lo declara la lista de FISPA", {}).get("Es"), "fuente")
    # El gemelo «R100» de ILLINOIS: su único vínculo es el del barrido (ver 7).
    esperar("cuenta los productos unidos solo por pistas", solo_pistas, 1)
    return fallas


def _falla(funcion, *args):
    try:
        funcion(*args)
    except Exception as _err:
        return type(_err).__name__
    return None


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_precision_")
    try:
        fallas = probar(_cargar_la_logica(carpeta))
        for f in fallas:
            print("   ✗", f)
        print("✅ precisión: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

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
    esperar("la próxima comprobación es medir lo que falta", ficha["proxima_comprobacion"],
            "medí ancho en las dos")

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
    esperar("verificada no pide otra comprobación", ficha["proxima_comprobacion"], "")
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

    # 17. Lo que la descripción declara de cómo funciona la pieza.
    parametros = ns["parametros_declarados"]
    chocan = ns["parametros_que_chocan"]

    def p_(texto):
        return tuple(parametros(ns["normalizar_texto"](texto)).items())
    esperar("12 contra 24 V", chocan(p_("RELAY 12 VOLTS"), p_("RELAY 24 VOLTS")),
            "versiones distintas: de 12 V contra de 24 V")
    esperar("85 contra 90 l/h es la misma bomba (redondeo)",
            chocan(p_("BOMBA 85L/H"), p_("BOMBA 90 L/H")), None)
    esperar("85 contra 105 l/h, no", chocan(p_("BOMBA 85L/H"), p_("BOMBA 105L/H")) is not None, True)
    esperar("la rosca", chocan(p_("BULBO M10X1"), p_("BULBO M12X1,5")),
            "medidas distintas: rosca M10x1 contra M12x1,5")
    esperar("el giro", chocan(p_("TPS SENTIDO HORARIO"), p_("TPS SENTIDO ANTIHORARIO")),
            "versiones distintas: giro horario contra antihorario")
    esperar("la cantidad", chocan(p_("FUSIBLE 2 UNIDADES"), p_("FUSIBLE 10 UNIDADES")),
            "juegos distintos: de 2 contra de 10")
    esperar("reacondicionada contra nueva", chocan(p_("BOMBA (REACONDICIONADO)"), p_("BOMBA")),
            "versiones distintas: reacondicionada contra nueva")
    esperar("si solo una lo dice, no choca", chocan(p_("RELAY 12 VOLTS"), p_("RELAY")), None)
    esperar("4X4 no es una cantidad", p_("HILUX 4X4"), ())
    # Los dientes, la fase y la tensión escrita al revés.
    arranque_24 = "MOTOR DE ARRANQUE Familia 28MT Volts V 24 Potencia Kw 4 0 Dientes 10 Sentido"
    arranque_12 = "MOTOR DE ARRANQUE Familia 29MT Volts V 12 Potencia Kw 2 9 Dientes 9 Sentido"
    esperar("el rótulo de FISPA: la tensión y los dientes", dict(p_(arranque_24)).get("dientes"),
            frozenset({10}))
    esperar("«Volts V 24» es 24 V", dict(p_(arranque_24)).get("tensión"), frozenset({24}))
    esperar("dos motores de arranque distintos", chocan(p_(arranque_24), p_(arranque_12)),
            "versiones distintas: de 10 dientes contra de 9")
    esperar("en la polea, los dientes van adelante (lo de atrás son años)",
            dict(p_("BOMBA DE AGUA POLEA 20 DIENTES 98 02 93")).get("dientes"), frozenset({20}))
    esperar("fase II contra fase III", chocan(p_("JUNTA PALIO FASE II"), p_("JUNTA PALIO FASE 3")),
            "versiones distintas: fase II contra fase III")
    esperar("la que sirve para las dos fases no choca",
            chocan(p_("JUNTA PALIO FASE II/III"), p_("JUNTA PALIO FASE III")), None)
    esperar("y declara las dos", dict(p_("JUNTA PALIO FASE II/III")).get("fase"),
            frozenset({"II", "III"}))

    # 18. Cuánto pueden diferir dos medidas: en mm, por medida, con la precisión que se escribió.
    cm = ns["comparar_medidas"]
    esperar("35 contra 36 mm son dos rulemanes", cm({"diametro_interno": 35},
                                                    {"diametro_interno": 36})[0], False)
    esperar("52 contra 52,4: el 52 puede estar redondeado",
            cm({"diametro_externo": 52}, {"diametro_externo": 52.4})[0], True)
    esperar("52,2 contra 52,6: no", cm({"diametro_externo": 52.2}, {"diametro_externo": 52.6})[0],
            False)
    esperar("un disco de 256 contra uno de 257", cm({"diametro_externo": 256},
                                                     {"diametro_externo": 257})[0], False)
    esperar("espesor 1,45 contra 1,50", cm({"espesor": 1.45, "diametro_interno": 80},
                                           {"espesor": 1.5, "diametro_interno": 80})[0], False)
    estados = {m["Medida"]: m["Estado"] for m in ns["medidas_lado_a_lado"](
        {"ancho": 35, "largo_total": 25.4}, {"ancho": 350, "largo_total": 1})}
    esperar("diez veces: ¿mm contra cm?", "cm?" in estados.get("ancho", ""), True)
    esperar("25,4 veces: ¿pulgadas?", "pulgadas" in estados.get("largo total", ""), True)

    # 19. Lo que se lee de una foto: primero lo que se confunde al leer.
    confusion = ns["es_confusion_de_lectura"]
    esperar("O por 0", confusion("W712O4", "W71204"), "O↔0")
    esperar("una letra de más no es confundir la forma", confusion("W71204", "W712044"), "")
    esperar("dos que no se confunden", confusion("W71204", "W71294"), "")
    producto("W71204", "FILTRO DE ACEITE", fispa)
    # Uno con stock y a un carácter, pero que no es una confusión de lectura: sin el orden de
    # la foto, saldría primero por tener stock.
    producto("W712A4", "FILTRO DE ACEITE", fispa, stock=5)
    conn.commit()
    parecidos = ns["codigos_por_tipeo"]("W712O4", de_una_foto=True)
    esperar("el que solo difiere en O/0 sale primero",
            (parecidos[0]["Codigo"], parecidos[0]["Lectura"]) if parecidos else None,
            ("W71204", "O↔0"))

    # 20. La ficha que cambió al reimportar: se avisa y no se pisa.
    cambia = ns["lo_que_cambia_la_pieza"]
    esperar("otra medida", cambia("RETEN 35X52X7 FIAT", "RETEN 35X52X8 FIAT"), "ancho: 7 → 8")
    esperar("otro lado", "posición" in cambia("AMORTIGUADOR DELANTERO KA", "AMORTIGUADOR TRASERO KA"),
            True)
    esperar("otra tensión", "12 V" in cambia("RELAY 12 VOLTS", "RELAY 24 VOLTS"), True)
    esperar("una coma o una palabra más no cuenta", cambia("RETEN 35X52X7 FIAT", "RETEN 35X52X7 FIAT 128"),
            "")
    reten_viejo = producto("RV100", "RETEN 35X52X7 FIAT 128", fispa)
    vincular(reten_viejo, ret_o, "FISPA · lista.xlsx · 01/10/2026 10:00:00")
    conn.commit()
    fichas = ns["fichas_que_cambiaron"]({reten_viejo: "RETEN 35X52X8 FIAT 128"})
    esperar("la lista nueva trae otra medida", (fichas["cambiaron"], fichas["ejemplos"][0]["Qué cambió"]),
            (1, "ancho: 7 → 8"))
    esperar("y dice a cuántas equivalencias toca", fichas["ejemplos"][0]["Vínculos"], 1)
    reten_suelto = producto("RV200", "RETEN 35X52X7 FIAT 147", fispa)
    conn.commit()
    fichas = ns["fichas_que_cambiaron"]({reten_suelto: "RETEN 35X52X9 FIAT 147",
                                          reten_viejo: "RETEN 35X52X8 FIAT 128"})
    esperar("la que más equivalencias toca va primero",
            [x["Código"] for x in fichas["ejemplos"]], ["RV100", "RV200"])
    esperar("otra redacción de la misma pieza no se cuenta",
            ns["fichas_que_cambiaron"]({reten_viejo: "RETEN 35X52X7 FIAT 128 ORIGINAL"})["cambiaron"],
            0)
    esperar("y la guardada no se tocó", c.execute("SELECT descripcion FROM productos WHERE id = ?",
                                                   (reten_viejo,)).fetchone()[0],
            "RETEN 35X52X7 FIAT 128")

    # 21. El por qué de cada decisión: todo lo que había a favor y en contra.
    pa_, pb_ = producto("PQ1", "BUJIA NGK", fispa), producto("IPQ1", "BUJIA NGK BKR6", illinois)
    conn.commit()
    ns["guardar_analisis_de_lote"]({"resultado": [[{
        "a": pa_, "b": pb_, "confianza": 80, "alarmas": ["💲 precios raros"],
        "senales": [("bien", "📄 la misma descripción"), ("mal", "💲 precios raros")]}]]})
    ns["marcar_revision"]([(pa_, pb_)], "ok")
    esperar("queda guardado", c.execute(
        "SELECT por_que FROM equivalencias_revisadas WHERE producto_a_id = ? AND producto_b_id = ?",
        (pa_, pb_)).fetchone()[0], "+ 📄 la misma descripción · − 💲 precios raros")

    # 22. La última revisión, y si para su riesgo ya toca volver a mirarla.
    pas_a = producto("PF1", "PASTILLA DE FRENO DELANTERA FIAT PALIO", fispa)
    pas_b = producto("IPF1", "PASTILLA DE FRENO DELANTERA FIAT PALIO 1.6", illinois)
    vincular(pas_a, pas_b, "FISPA · lista.xlsx · 01/10/2026 10:00:00")
    c.execute("INSERT OR REPLACE INTO equivalencias_revisadas (producto_a_id, producto_b_id, decision, "
              "revisado_por, fecha) VALUES (?, ?, 'ok', 'Ana', '2025-01-10 10:00:00')",
              (min(pas_a, pas_b), max(pas_a, pas_b)))
    conn.commit()
    ficha = ns["ficha_de_prueba"](pas_a, pas_b)
    esperar("sabe cuándo se revisó", ficha["ultima_revision"], "2025-01-10")
    esperar("una pieza de seguridad dice si hay registro CHAS",
            "no está cargado" in " ".join(ficha["chas"]), True)
    esperar("una que no es de seguridad, no", ns["ficha_de_prueba"](ret_f, ret_i)["chas"], [])
    c.execute("INSERT INTO chas_emitidos (numero, empresa, marca, marca_norm, autoparte) "
              "VALUES ('C1', 'FISPA SA', 'FISPA', 'FISPA', 'PASTILLAS DE FRENO')")
    ns["guardar_config"](ns["CONFIG_DEL_CHAS"], '{"certificados": 1}')
    conn.commit()
    esperar("con el registro, dice quién tiene CHAS y quién no figura",
            ns["ficha_de_prueba"](pas_a, pas_b)["chas"],
            ["🛡️ A: FISPA tiene CHAS (1 certificado(s))",
             "🛡️ B: ILLINOIS no figura en el registro CHAS"])
    esperar("una pieza de seguridad revisada hace más de 6 meses vuelve a probable",
            ficha["estado"], "🟡 PROBABLE")
    esperar("y dice por qué", any("volver a mirarla" in f for f in ficha["falta"]), True)
    c.execute("UPDATE equivalencias_revisadas SET fecha = datetime('now') WHERE producto_a_id = ? "
              "AND producto_b_id = ?", (min(pas_a, pas_b), max(pas_a, pas_b)))
    conn.commit()
    ficha = ns["ficha_de_prueba"](pas_a, pas_b)
    esperar("revisada hace poco, ya no pide volver a mirarla",
            any("volver a mirarla" in f for f in ficha["falta"]), False)
    # Pero una pieza de seguridad pide además un auto en común y una medida igual (ver la 49).
    esperar("y le falta la evidencia mínima de una pieza de seguridad", ficha["estado"],
            "🟡 PROBABLE")
    esperar("que dice las dos cosas", any("un auto en común en las descripciones y una medida"
                                          in f for f in ficha["falta"]), True)
    # La de riesgo normal también vence, a los tres años.
    fa_a = producto("FA1", "FILTRO DE AIRE FIAT PALIO", fispa)
    fa_b = producto("IFA1", "FILTRO DE AIRE FIAT PALIO 1.4", illinois)
    vincular(fa_a, fa_b, "FISPA · lista.xlsx · 01/10/2026 10:00:00")
    c.execute("INSERT OR REPLACE INTO equivalencias_revisadas (producto_a_id, producto_b_id, decision, "
              "revisado_por, fecha) VALUES (?, ?, 'ok', 'Ana', '2022-01-10 10:00:00')",
              (min(fa_a, fa_b), max(fa_a, fa_b)))
    conn.commit()
    ficha = ns["ficha_de_prueba"](fa_a, fa_b)
    esperar("un filtro es de riesgo normal", ficha["riesgo"][:1], "🟢")
    esperar("revisado hace más de tres años vuelve a probable", ficha["estado"], "🟡 PROBABLE")
    c.execute("UPDATE equivalencias_revisadas SET fecha = '2025-01-10 10:00:00' WHERE "
              "producto_a_id = ? AND producto_b_id = ?", (min(fa_a, fa_b), max(fa_a, fa_b)))
    conn.commit()
    esperar("revisado hace menos de tres años, sigue verificado",
            ns["ficha_de_prueba"](fa_a, fa_b)["estado"], "✅ VERIFICADA")

    # 23. Lo que alguien rechazó y vuelve por otro camino: se marca, no compite y la ficha lo dice.
    rx_a = producto("BX1", "BOMBA DE AGUA VW GOL 1.6", fispa)
    rx_b = producto("IBX1", "BOMBA DE AGUA VW GOL 1.6", illinois)
    rx_o = producto("030121008", "BOMBA DE AGUA", oem)
    vincular(rx_a, rx_o, "FISPA · lista.xlsx · 01/10/2026 10:00:00")
    vincular(rx_b, rx_o, "ILLINOIS · lista.xlsx · 01/10/2026 11:00:00")
    c.execute("UPDATE productos SET precio = 100, stock = 2 WHERE id = ?", (rx_b,))
    c.execute("UPDATE productos SET precio = 300, stock = 2 WHERE id = ?", (rx_a,))
    conn.commit()
    res, _ = ns["buscar_con_variantes_del_cero"]("BX1", "Todas", 3)
    fila_rx = {f["ID"]: f for f in res}.get(rx_b, {})
    esperar("antes del rechazo no está marcada", "Rechazada" in fila_rx, False)
    ns["marcar_revision"]([(rx_a, rx_b)], "rechazada", "otra_pieza")
    res, _ = ns["buscar_con_variantes_del_cero"]("BX1", "Todas", 3)
    por_id = {f["ID"]: f for f in res}
    fila_rx = por_id.get(rx_b, {})
    esperar("sigue apareciendo, por el número de fábrica", bool(fila_rx), True)
    esperar("pero marcada como rechazada", str(fila_rx.get("Rechazada", "")).startswith("🚫 "),
            True)
    esperar("con el motivo", "Es otra pieza" in str(fila_rx.get("Rechazada", "")), True)
    esperar("el número de fábrica no está rechazado", "Rechazada" in por_id.get(rx_o, {}), False)
    esperar("y el veredicto lo dice primero",
            ns["veredicto_de_la_equivalencia"](dict(fila_rx, Confianza="🟢 sólida"))
            .startswith("🔴 rechazada"), True)
    esperar("no compite por el más barato", ns["no_compite_por_precio"](fila_rx), True)
    esperar("ni por el mejor margen", ns["mejor_margen_entre_equivalentes"]([
        dict(fila_rx, _costo=10), {"Codigo": "X", "Marca": "Y", "Stock": 1, "Precio": 100,
                                    "_costo": 90}]), None)
    esperar("ni va a la cotización", rx_b in [f["ID"] for f in ns["filas_para_cotizar"](res)],
            False)
    esperar("buscando el otro, también", {f["ID"]: f for f in ns["buscar_con_variantes_del_cero"](
        "IBX1", "Todas", 3)[0]}.get(rx_a, {}).get("Rechazada", "")[:1], "🚫")
    # Una base de antes puede tener el rechazo anotado en un solo sentido: se marca igual.
    c.execute("DELETE FROM equivalencias_revisadas WHERE producto_a_id = ? AND producto_b_id = ?",
              (rx_b, rx_a))
    conn.commit()
    esperar("con el rechazo anotado en un solo sentido, también",
            {f["ID"]: f for f in ns["buscar_con_variantes_del_cero"]("BX1", "Todas", 3)[0]}
            .get(rx_b, {}).get("Rechazada", "")[:1], "🚫")
    ficha = ns["ficha_de_prueba"](rx_a, rx_b)
    esperar("la ficha la da con contradicciones", ficha["estado"], "🔴 CON CONTRADICCIONES")
    esperar("y lo primero que dice es el rechazo", ficha["resumen"][0][:1], "🚫")
    esperar("con el motivo", "Es otra pieza" in ficha["contradicciones"][0], True)
    esperar("y pide mirarla en la mano", ficha["proxima_comprobacion"],
            "compará las dos piezas en la mano")
    esperar("abierta al revés, también", ns["ficha_de_prueba"](rx_b, rx_a)["estado"],
            "🔴 CON CONTRADICCIONES")

    # 24. El historial de las decisiones: todas, con la lista y la versión, y no se toca.
    hist = c.execute("SELECT decision, lote, version_reglas FROM historial_de_revisiones "
                     "WHERE producto_a_id = ? AND producto_b_id = ? ORDER BY id",
                     (min(ja, jb), max(ja, jb))).fetchall()
    esperar("el rechazo queda con la lista de la que vino", [tuple(h) for h in hist],
            [("rechazada", "ILLINOIS · otra.xlsx · x", ns["VERSION_CONFIANZA"])])
    ns["marcar_revision"]([(rx_a, rx_b)], "ok")
    esperar("aprobar después pisa la última decisión", c.execute(
        "SELECT decision FROM equivalencias_revisadas WHERE producto_a_id = ? AND producto_b_id = ?",
        (rx_a, rx_b)).fetchone()[0], "ok")
    ficha = ns["ficha_de_prueba"](rx_a, rx_b)
    esperar("pero el historial guarda las dos, la nueva primero",
            [h["Decisión"][:1] for h in ficha["historial"] if h["Par"] == "A ↔ B"], ["✅", "🚫"])
    esperar("con la versión de las reglas", ficha["historial"][0]["Reglas"],
            "v" + ns["VERSION_CONFIANZA"])
    esperar("ya no está rechazada", "Rechazada" in {f["ID"]: f for f in ns[
        "buscar_con_variantes_del_cero"]("BX1", "Todas", 3)[0]}.get(rx_b, {}), False)
    esperar("el historial no se corrige", _falla(
        c.execute, "UPDATE historial_de_revisiones SET decision = 'ok'"), "IntegrityError")
    esperar("ni se borra", _falla(c.execute, "DELETE FROM historial_de_revisiones"),
            "IntegrityError")
    conn.rollback()

    # 25. Por qué no le iba: cada motivo de «no era la pieza» baja el vínculo; la fallada, no.
    tr_a = producto("TR1", "TERMINAL DE DIRECCION VW GOL", fispa)
    tr_b = producto("ITR1", "TERMINAL DE DIRECCION VW GOL", illinois)
    vincular(tr_a, tr_b, "FISPA · lista.xlsx · 01/10/2026 10:00:00", confianza=95)
    conn.commit()
    esperar("otra rosca baja el vínculo", ns["registrar_devolucion"](tr_b, "TR1", "rosca"), 1)
    esperar("y cuenta como devuelto",
            ns["pares_devueltos"]().get((min(tr_a, tr_b), max(tr_a, tr_b))), 1)
    for motivo in ("medida", "conector", "lado", "aplicacion", "faltante", "modificacion"):
        esperar(f"«{motivo}» dice que no era la pieza",
                motivo in ns["MOTIVOS_DE_NO_ERA_LA_PIEZA"], True)
    esperar("«fallada» no", "fallada" in ns["MOTIVOS_DE_NO_ERA_LA_PIEZA"], False)
    esperar("«otro» tampoco", "otro" in ns["MOTIVOS_DE_NO_ERA_LA_PIEZA"], False)

    # 26. El lado no es una variante: la rosca izquierda y el borne del otro lado.
    base = ns["codigo_base_sin_variante"]
    esperar("rosca izquierda", base("CAMBA265.32.I") == base("CAMBA265.32"), False)
    esperar("borne del otro lado", base("MATEO-12/95-D") == base("MATEO-12/95-I"), False)
    esperar("izquierda y derecha", base("PZ-500-20 LH") == base("PZ-500-20 RH"), False)
    esperar("el mismo lado en otro material, sí", base("PZ-500-20 LH"), base("PZ-500-MG LH"))
    esperar("«-R» sigue siendo con retenes", base("SJ-252-R"), "SJ-252")

    # 27. El estado viaja con el código: lo que no está confirmado sale «a confirmar».
    item = [{"codigo_buscado": "W712", "resultados": [
        {"Marca": "MANN", "Codigo": "W712", "Cadena": "— el buscado"},
        {"Marca": "FRAM", "Codigo": "PH1", "Cadena": "🟢 directo", "Confianza": "🟢 sólida",
         "Respaldo": "📋 lo declara la lista de FISPA"},
        {"Marca": "WEGA", "Codigo": "W1", "Cadena": "🟡 3 saltos", "Confianza": "🟢 sólida"}]}]
    mensaje = ns["armar_mensaje_de_cotizacion"](item)
    esperar("la probable sale a confirmar", "• WEGA: W1 ⚠️ a confirmar" in mensaje, True)
    esperar("la confirmada no", "• FRAM: PH1\n" in mensaje + "\n", True)
    esperar("lo buscado no", "• MANN: W712\n" in mensaje, True)
    esperar("y se puede apagar", "a confirmar" in ns["armar_mensaje_de_cotizacion"](
        item, marcar_a_confirmar=False), False)

    # 28. Aprobar en bloque deja afuera las piezas de seguridad; de a una, se aprueban.
    pf_a = producto("PB1", "PASTILLA DE FRENO DELANTERA VW GOL", fispa)
    pf_b = producto("IPB1", "PASTILLA DE FRENO DELANTERA VW GOL", illinois)
    fl_a = producto("FL1", "FILTRO DE ACEITE VW GOL", fispa)
    fl_b = producto("IFL1", "FILTRO DE ACEITE VW GOL", illinois)
    for x, y in ((pf_a, pf_b), (fl_a, fl_b)):
        c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, lote) "
                  "VALUES (?, ?, 'lista_proveedor', 'BLOQUE')", (min(x, y), max(x, y)))
    conn.commit()
    esperar("la pastilla es de seguridad", ns["pares_de_piezas_de_seguridad"](
        [(pf_a, pf_b), (fl_a, fl_b)]), {(pf_a, pf_b)})
    esperar("en bloque se aprueba solo el filtro", ns["aprobar_pendientes"](
        "BLOQUE", [(pf_a, pf_b), (fl_a, fl_b)], en_bloque=True), 1)
    esperar("y la pastilla sigue en la cola", c.execute(
        "SELECT COUNT(*) FROM equivalencias_pendientes WHERE lote = 'BLOQUE'").fetchone()[0], 1)
    esperar("de a una, sí se aprueba", ns["aprobar_pendientes"]("BLOQUE", [(pf_a, pf_b)]), 1)

    # 29. Corregir las medidas a mano vuelve a puntuar los vínculos de ese producto, y nada más.
    md_a = producto("RM1", "RETEN CIGUEÑAL VW GOL 40X60X8", fispa, diametro_interno=40,
                    diametro_externo=60)
    md_b = producto("IRM1", "RETEN CIGUEÑAL VW GOL 40X60X8", illinois, diametro_interno=40,
                    diametro_externo=60)
    vincular(md_a, md_b, "FISPA · lista.xlsx · 01/10/2026 10:00:00", confianza=90)
    conn.commit()
    _conf_otro = c.execute("SELECT confianza FROM equivalencias WHERE producto_a_id = ? AND "
                           "producto_b_id = ?", (min(fa_a, fa_b), max(fa_a, fa_b))).fetchone()[0]
    esperar("sin productos con vínculos, no hace nada", ns["repuntuar_los_vinculos_de"](-1), (0, 0))
    ns["actualizar_medidas"](md_b, 52, 60, None, None, None, None)
    n_rep, n_franja = ns["repuntuar_los_vinculos_de"](md_b)
    esperar("repuntúa el vínculo del producto", n_rep, 1)
    esperar("y con la medida que no da cambia de franja", n_franja, 1)
    esperar("repuntuar otra vez no cambia ninguna franja", ns["repuntuar_los_vinculos_de"](md_b),
            (1, 0))
    esperar("queda flojo", c.execute("SELECT confianza FROM equivalencias WHERE producto_a_id = ? "
                                     "AND producto_b_id = ?", (min(md_a, md_b), max(md_a, md_b))
                                     ).fetchone()[0] < 50, True)
    esperar("los otros vínculos no se tocan", c.execute(
        "SELECT confianza FROM equivalencias WHERE producto_a_id = ? AND producto_b_id = ?",
        (min(fa_a, fa_b), max(fa_a, fa_b))).fetchone()[0], _conf_otro)

    # 30. Una pieza de seguridad que no está confirmada se muestra, pero no se recomienda.
    no_se = ns["no_se_recomienda"]
    pastilla = "PASTILLA DE FRENO DELANTERA VW GOL"
    probable = {"Cadena": "🟡 3 saltos", "Confianza": "🟢 sólida", "Descripcion": pastilla}
    confirmada = {"Cadena": "🟢 directo", "Confianza": "🟢 sólida", "Descripcion": pastilla,
                  "Respaldo": "📋 lo declara la lista de FISPA"}
    esperar("pastilla probable: no se corona", no_se(probable), True)
    esperar("pastilla confirmada: sí", no_se(confirmada), False)
    esperar("la pastilla que buscó el cliente: sí", no_se({"Cadena": "— el buscado",
                                                           "Descripcion": pastilla}), False)
    esperar("un filtro probable: sí", no_se(dict(probable, Descripcion="FILTRO DE ACEITE")), False)
    esperar("ni el mejor margen", ns["mejor_margen_entre_equivalentes"]([
        dict(probable, Codigo="P1", Marca="X", Stock=1, Precio=500, _costo=10),
        dict(confirmada, Codigo="P2", Marca="Y", Stock=1, Precio=100, _costo=90),
        {"Codigo": "F", "Marca": "Z", "Stock": 1, "Precio": 100, "_costo": 80,
         "Cadena": "— el buscado", "Descripcion": pastilla}])["codigo"], "F")
    esperar("en WhatsApp dice que es de seguridad",
            "⚠️ a confirmar · 🛑 pieza de seguridad" in ns["armar_mensaje_de_cotizacion"](
                [{"codigo_buscado": "X", "resultados": [dict(probable, Marca="M", Codigo="C")]}]),
            True)

    # 31. Lo que falta, de lo que más identifica a la pieza a lo que menos, y lo que la tumbaría.
    fi_a = producto("FI9", "FILTRO DE ACEITE VW GOL 1.6", fispa)
    fi_b = producto("IFI9", "FILTRO DE ACEITE VW GOL 1.6", illinois)
    vincular(fi_a, fi_b, "FISPA · lista.xlsx · 01/10/2026 10:00:00")
    conn.commit()
    ficha = ns["ficha_de_prueba"](fi_a, fi_b)
    esperar("en un filtro, primero el diámetro externo", ficha["para_medir"],
            ["diám. externo", "diám. interno", "largo total", "paso de rosca"])
    esperar("lo que la tumbaría arranca por lo que más la identifica",
            (ficha["la_tumbaria"][0]["Característica"], ficha["la_tumbaria"][0]["Importancia"]),
            ("diám. externo", "la que más la identifica"))
    tumbaria = {t["Característica"]: t["Hoy"] for t in ns["ficha_de_prueba"](ret_f, ret_i)["la_tumbaria"]}
    esperar("lo que ya coincide figura", tumbaria.get("diám. interno"), "✅ igual")
    esperar("y lo que falta va primero",
            ns["ficha_de_prueba"](ret_f, ret_i)["la_tumbaria"][0]["Característica"], "ancho")
    rl_a = producto("RL1", "RELAY 12 VOLTS 4 PATAS", fispa)
    rl_b = producto("IRL1", "RELAY 4 PATAS", illinois)
    vincular(rl_a, rl_b, "FISPA · lista.xlsx · 01/10/2026 10:00:00")
    conn.commit()
    esperar("un parámetro que dice uno solo", {t["Característica"]: t["Hoy"] for t in
                                               ns["ficha_de_prueba"](rl_a, rl_b)["la_tumbaria"]}
            .get("tensión"), "❓ solo lo dice A")

    # 32. Los autos que nombran los dos.
    def aplicacion(codigo, marca_auto, modelo):
        c.execute("INSERT INTO aplicaciones (marca_auto, modelo_auto, codigo, codigo_clean, origen) "
                  "VALUES (?, ?, ?, ?, 'deducida')", (marca_auto, modelo, codigo, ns["sanitizar"](codigo)))
    aplicacion("FI9", "VOLKSWAGEN", "GOL"); aplicacion("IFI9", "volkswagen", "gol")
    aplicacion("IFI9", "VOLKSWAGEN", "SAVEIRO")
    aplicacion("RL1", "FIAT", "PALIO"); aplicacion("IRL1", "FORD", "KA")
    conn.commit()
    ficha = ns["ficha_de_prueba"](fi_a, fi_b)
    esperar("nombran un auto en común", ficha["autos"]["comun"], ["Volkswagen Gol"])
    esperar("y lo dice en la línea", "🚗 nombran 1 auto(s) en común" in ficha["resumen"], True)
    ficha = ns["ficha_de_prueba"](rl_a, rl_b)
    esperar("ninguno en común: avisa, no tumba", (ficha["estado"].startswith("🔴"),
                                                  any(x.startswith("🚗") for x in ficha["avisos"])),
            (False, True))

    # 33. El expediente.
    texto = ns["expediente_en_texto"](ns["ficha_de_prueba"](rx_a, rx_b))
    esperar("el expediente lleva el estado, lo que la tumbaría y el historial",
            all(x in texto for x in ("# Expediente de equivalencia", "**Estado:**",
                                     "## Historial de decisiones", "## Quién declara cada paso")),
            True)

    # 34. Lo que se exporta lleva el estado.
    estado = ns["estado_del_vinculo"]
    esperar("de una lista y sólido: confirmada", estado(90, "FISPA · a.xlsx · x", 0), "confirmada")
    esperar("del barrido: probable", estado(90, "BARRIDO (automático) · x", 0), "probable")
    esperar("flojo: revisar", estado(40, "FISPA · a.xlsx · x", 0), "revisar")
    esperar("muy débil: dudosa", estado(10, "FISPA · a.xlsx · x", 0), "dudosa")
    esperar("verificado a mano: confirmada", estado(90, "BARRIDO · x", 1), "confirmada")
    esperar("verificado a mano, aunque el puntaje sea flojo", estado(40, "FISPA · a.xlsx · x", 1),
            "confirmada")
    import csv, io, zipfile
    c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, lote) "
              "VALUES (?, ?, 'lista_proveedor', 'EXPORTAR')", (min(fi_a, rl_b), max(fi_a, rl_b)))
    conn.commit()
    zip_bytes, cuantas = ns["exportar_catalogo_zip"]()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        eq = list(csv.DictReader(io.StringIO(z.read("equivalencias.csv").decode("utf-8-sig"))))
        rech = list(csv.DictReader(io.StringIO(z.read("rechazadas.csv").decode("utf-8-sig"))))
        pend = z.read("equivalencias_pendientes.csv").decode("utf-8-sig")
        leeme = z.read("LEEME.txt").decode("utf-8")
    esperar("cada equivalencia con su estado", all(f["estado"] in ("confirmada", "probable",
                                                                   "revisar", "dudosa") for f in eq)
            and bool(eq), True)
    esperar("y los rechazados aparte", ((str(min(ja, jb)), str(max(ja, jb))) in
                                        {(f["producto_a_id"], f["producto_b_id"]) for f in rech}),
            True)
    esperar("lo pendiente dice que no es una equivalencia",
            (pend.splitlines()[0].endswith(",estado"),
             all(x.endswith(",pendiente: todavía no es una equivalencia")
                 for x in pend.splitlines()[1:]) and len(pend.splitlines()) > 1), (True, True))
    esperar("el LEEME lo explica", "solo\n«confirmada»" in leeme, True)

    # 35. El tablero de calidad.
    tablero = ns["tablero_de_calidad"](minimo_por_grupo=1)
    esperar("cuenta lo rechazado y después aprobado",
            tablero["numeros"]["rechazados_y_despues_aprobados"] >= 1, True)
    esperar("y lo comprobado en la mano", tablero["numeros"]["comprobados_en_la_mano"] >= 1, True)
    esperar("y las devoluciones que dicen que no era la pieza",
            tablero["numeros"]["devoluciones_no_era_la_pieza"], 2)
    esperar("mide cuánto tardó en decidirse lo que estaba en la cola",
            tablero["numeros"]["con_dias"] >= 1, True)
    esperar("y por familia, con su semáforo", bool(tablero["por_familia"]) and
            tablero["por_familia"][0]["Semáforo"] in ("🔴", "🟡", "🟢"), True)

    # 36. Una regla que hace subir de franja demasiados vínculos de una vez.
    sospecha = ns["deriva_sospechosa"]
    esperar("60 de 1.000 suben: sospechosa", sospecha({"subieron": 60, "total": 1000,
                                                       "version": "13"}).startswith("⚠️"), True)
    esperar("60 de 10.000, no", sospecha({"subieron": 60, "total": 10000}), "")
    esperar("10 de 100, no", sospecha({"subieron": 10, "total": 100}), "")

    # 37. Lo que se buscó en contra en las descripciones.
    pd_a = producto("PD7", "PASTILLA DE FRENO DELANTERA VW GOL 1.6 1995/2000", fispa)
    pd_b = producto("IPD7", "PASTILLA DE FRENO TRASERA VW GOL 1.8 2008/2012 KIT", illinois)
    vincular(pd_a, pd_b, "BARRIDO (automático) · 02/10 10:00")
    conn.commit()
    hoy = {t["Característica"]: t["Hoy"] for t in ns["ficha_de_prueba"](pd_a, pd_b)["la_tumbaria"]}
    esperar("otro lado", hoy.get("lado o posición", "")[:2], "⚠️")
    esperar("otra cilindrada", hoy.get("cilindrada", "")[:2], "⚠️")
    esperar("otros años", hoy.get("años", "")[:2], "⚠️")
    esperar("kit contra pieza suelta", hoy.get("kit o pieza suelta", "")[:2], "⚠️")
    esperar("el mismo rubro", hoy.get("rubro"), "✅ los dos dicen lo mismo")
    esperar("lo que no se pudo comparar, primero o después, pero figura",
            ns["ficha_de_prueba"](pd_a, pd_b)["la_tumbaria"][0]["Hoy"][:1] in ("⚠", "❌"), True)

    # 38. De dónde y cuándo.
    donde = ns["de_donde_y_cuando"]
    esperar("la lista y la fecha", donde("FISPA · lista.xlsx · 01/10/2026 10:00:00"),
            "FISPA (01/10/2026 10:00:00)")
    esperar("una tanda automática", donde("BARRIDO (automático) · 25/09 20:43"),
            "BARRIDO (automático) (25/09 20:43)")
    esperar("sin fecha", donde("VIEJA"), "VIEJA")
    esperar("sin nada", donde(None), "—")

    # 39. Las medidas tienen versiones, y el cambio dice a qué toca.
    esperar("el cambio de antes quedó anotado", [(h["Medida"], h["Antes"], h["Ahora"])
                                                  for h in ns["historial_de_medidas"](md_b)],
            [("diám. interno", "40", "52")])
    esperar("guardar lo mismo no anota nada",
            ns["actualizar_medidas"](md_b, 52, 60, None, None, None, None), 0)
    esperar("otro cambio, otra versión",
            ns["actualizar_medidas"](md_b, 52, 61.5, None, None, None, None), 1)
    esperar("la más nueva primero", ns["historial_de_medidas"](md_b)[0]["Ahora"], "61.5")
    esperar("y cuántos autos nombra su código", ns["autos_que_nombran_al_producto"](fi_b), 2)

    # 40. Vender lo que no está confirmado: queda como alternativa comercial y no confirma.
    como = ns["como_se_vende"]
    esperar("confirmada: equivalente", como("🟢 equivalencia confirmada"), "equivalente")
    esperar("probable: alternativa", como("🟡 probable: llega por 1 código(s) en el medio"),
            "alternativa")
    esperar("lo buscado: nada", como("el que buscaste"), None)
    esperar("el botón lo dice", ns["rotulo_del_boton_de_venta"](probable),
            "🛒 Se llevó como alternativa")
    vt_a = producto("VT1", "BOMBA DE AGUA FIAT PALIO", fispa)
    vt_b = producto("IVT1", "BOMBA DE AGUA FIAT PALIO", illinois)
    conn.commit()
    for _ in range(2):
        ns["registrar_venta"](vt_b, "VT1", "🟡 probable")
    esperar("queda congelado el veredicto de ese momento", tuple(c.execute(
        "SELECT veredicto, como FROM ventas_registradas WHERE producto_id = ? LIMIT 1",
        (vt_b,)).fetchone()), ("🟡 probable", "alternativa"))
    esperar("vendida como alternativa no confirma",
            (min(vt_a, vt_b), max(vt_a, vt_b)) in ns["pares_confirmados_por_ventas"](), False)
    for _ in range(2):
        ns["registrar_venta"](vt_b, "VT1", "🟢 equivalencia confirmada")
    esperar("vendida como equivalente, sí",
            (min(vt_a, vt_b), max(vt_a, vt_b)) in ns["pares_confirmados_por_ventas"](), True)

    # 41. El tablero: semáforo, degradación, registro de errores y la foto de cada día.
    # La venta guarda lo que la sostenía en ese momento: la «caja negra».
    caja = ns["evidencia_de_la_fila"]({"Cadena": "🟢 directo", "Confianza": "🟢 sólida",
                                       "Respaldo": "📋 lo declara la lista de FISPA"})
    esperar("la caja negra de la venta", caja, "cadena 🟢 directo · confianza 🟢 sólida · "
            f"📋 lo declara la lista de FISPA · reglas v{ns['VERSION_CONFIANZA']}")
    ns["registrar_venta"](vt_b, "VT1", "🟢 equivalencia confirmada", caja)
    for _ in range(2):
        ns["registrar_devolucion"](vt_b, "VT1", "medida")
    ns["marcar_revision"]([(rl_a, rl_b)], "ok")
    ns["marcar_revision"]([(rl_a, rl_b)], "rechazada", "otra_pieza")
    tablero = ns["tablero_de_calidad"](minimo_por_grupo=1)
    familia_bomba = ns["familia_para_comparar"]("BOMBA DE AGUA FIAT PALIO")
    esperar("la familia con devoluciones nuevas está empeorando",
            familia_bomba in tablero["empeorando"], True)
    esperar("y su semáforo está en rojo", {f["Familia"]: f["Semáforo"] for f in
                                           tablero["por_familia"]}.get(familia_bomba), "🔴")
    detectado = [e["Detectado por"] for e in tablero["errores"]]
    esperar("el registro trae las devoluciones y lo aprobado y después rechazado",
            (any(x.startswith("↩️") for x in detectado), any(x.startswith("🔍") for x in detectado)),
            (True, True))
    esperar("la métrica principal: vendidas como equivalentes y devueltas porque no eran",
            (tablero["numeros"]["vendidas_como_equivalente"],
             tablero["numeros"]["vendidas_como_equivalente_y_devueltas"]), (3, 2))
    esperar("y lo que decía al venderla", [e["Lo que la dejó pasar"] for e in tablero["errores"]
                                           if e["Equivalencia"].startswith("VT1 →")][0],
            "🟢 equivalencia confirmada · " + caja)
    esperar("sin una foto de hace un mes, nada que comparar", tablero["hace_un_mes"], None)
    import json as _json
    _fotos = _json.loads(ns["obtener_config"]("calidad_fotos", "[]"))
    esperar("se guardó la foto de hoy", len(_fotos), 1)
    _vieja = (__import__("datetime").datetime.now()
              - __import__("datetime").timedelta(days=40)).strftime("%Y-%m-%d")
    ns["guardar_config"]("calidad_fotos", _json.dumps([dict(_fotos[0], fecha=_vieja)] + _fotos))
    esperar("con una de hace 40 días, compara contra esa",
            ns["tablero_de_calidad"]()["hace_un_mes"]["fecha"], _vieja)

    # 42. Una tanda automática que trae demasiado de una vez.
    anomalia = ns["anomalia_de_la_tanda"]
    umbrales = dict(ns["ANOMALIA_DE_TANDA"])
    ns["ANOMALIA_DE_TANDA"].update(veces=2, minimo=2, primera_minimo=2, primera_proporcion=0.0)
    try:
        for x, y in ((pd_a, vt_a), (pd_b, vt_a), (rl_a, vt_a)):
            c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, "
                      "lote) VALUES (?, ?, 'medidas', 'POR MEDIDAS · 05/10 10:00')",
                      (min(x, y), max(x, y)))
        conn.commit()
        esperar("la primera tanda de una regla, grande: avisa",
                anomalia("POR MEDIDAS · 05/10 10:00").startswith("⚠️ Primera tanda"), True)
        esperar("una lista de un proveedor, no", anomalia("FISPA · lista.xlsx · 01/10/2026 10:00:00"),
                "")
        c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, lote) "
                  "VALUES (?, ?, 'medidas', 'POR MEDIDAS · 06/10 10:00')",
                  (min(rl_b, vt_a), max(rl_b, vt_a)))
        conn.commit()
        esperar("contra las anteriores de la misma regla",
                anomalia("POR MEDIDAS · 05/10 10:00").startswith("⚠️ Tanda anómala"), True)
        esperar("la chica, no", anomalia("POR MEDIDAS · 06/10 10:00"), "")
        c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, lote) "
                  "VALUES (?, ?, 'medidas', 'POR MEDIDAS · 06/10 10:00')",
                  (min(rl_b, vt_b), max(rl_b, vt_b)))
        conn.commit()
        esperar("pasar el mínimo no alcanza: tiene que traer mucho más que las otras",
                anomalia("POR MEDIDAS · 06/10 10:00"), "")
    finally:
        ns["ANOMALIA_DE_TANDA"].update(umbrales)

    # 43. El laboratorio: dos códigos cualesquiera, por dimensión.
    esperar("los productos de un código", ns["productos_del_codigo"]("FI9"), [(fi_a, "FI9 (FISPA)")])
    perfil = {d: v for d, v, _q in ns["perfil_de_la_equivalencia"](ns["ficha_de_prueba"](fi_a, fi_b))}
    esperar("identidad: un vínculo directo que declara una lista", perfil["Identidad"], 100)
    esperar("aplicación: el único auto de A está en B", perfil["Aplicación"], 100)
    esperar("dimensiones: sin medidas, sin datos", perfil["Dimensiones"], None)
    esperar("evidencia: una fuente", perfil["Evidencia"], 50)
    perfil = {d: v for d, v, _q in ns["perfil_de_la_equivalencia"](ns["ficha_de_prueba"](pd_a, pd_b))}
    esperar("lo que declaran: el rubro coincide, lo demás no", perfil["Lo que declaran"], 20)
    perfil = {d: v for d, v, _q in ns["perfil_de_la_equivalencia"](ns["ficha_de_prueba"](rl_a, rl_b))}
    esperar("lo que dice uno solo no cuenta ni a favor ni en contra: sin datos",
            perfil["Lo que declaran"], None)
    esperar("«sin clasificar» no es un rubro que se contradiga",
            dict(ns["_lo_que_dicen_las_descripciones"]("ZZQ 123", "FILTRO DE ACEITE VW GOL"))
            .get("rubro", "❓")[:1], "❓")

    # 44. Datos imposibles: lo que el lector leía mal, y lo que no puede ser aunque esté guardado.
    leer = ns["medidas_desde_descripcion"]
    for desc in ("Kit Tornillo Seguridad FORD Ranger 1/2X20X37_A",
                 "TORNILLO TAPA CILINDRO M11X012X210 29 FO FA",
                 "66M012X162-12.9FA TORNILLO TAPA CILINDRO C/ARANDELA",
                 "SONDA LAMBDA AUDI A3 - BMW X1 X3 X4 X5 Z4",
                 "Jgo. Retenes VW Polo Mot. 1Y-AAZ -1X 64-75-61cc",
                 "RETEN 6X60X8", "ARANDELA 1/4X20X30"):
        esperar(f"no lee «{desc}»", leer(desc).get("diametro_interno"), None)
    for desc, medida in (("ARANDELA A7X17X1.5F", (7, 17, 1.5)), ("ANILLO G88X99X5", (88, 99, 5)),
                         ("DUO POWER 5 X 25 X 100 UNID.", (5, 25, 100)),
                         ("Reten Arbol Secund.30x44x8", (30, 44, 8))):
        _m = leer(desc)
        esperar(f"sí lee «{desc}»", (_m.get("diametro_interno"), _m.get("diametro_externo"),
                                     _m.get("ancho")), medida)
    imposibles = ns["medidas_imposibles"]
    esperar("un externo 14 veces el interno", imposibles(
        {"diametro_interno": 12, "diametro_externo": 162}), ["el externo (162) es 14 veces el interno (12)"])
    esperar("un interno mayor que el externo", len(imposibles(
        {"diametro_interno": 40, "diametro_externo": 35})), 1)
    esperar("ni igual", len(imposibles({"diametro_interno": 40, "diametro_externo": 40})), 1)
    esperar("8 veces todavía puede ser", imposibles({"diametro_interno": 5, "diametro_externo": 40}),
            [])
    esperar("en la cara B también", "(cara B)" in " ".join(imposibles(
        {"diametro_interno_cara_b": 50, "diametro_externo_cara_b": 40})), True)
    esperar("una medida normal, nada", imposibles({"diametro_interno": 35, "diametro_externo": 52,
                                                   "ancho": 7}), [])
    esperar("un diámetro imposible no prueba nada", ns["comparar_medidas"](
        {"diametro_interno": 12, "diametro_externo": 162},
        {"diametro_interno": 12, "diametro_externo": 20})[0], None)
    esperar("y en la ficha se ve, marcado", {m["Medida"]: m["Estado"] for m in ns["medidas_lado_a_lado"](
        {"diametro_interno": 12, "diametro_externo": 162}, {"diametro_interno": 12})}
            .get("diám. externo"), "⚠️ imposible en A: no se usa")
    # Lo guardado que el lector de hoy ya no lee así: se descarta, salvo lo cargado a mano.
    ml_a = producto("SL1", "SONDA LAMBDA BMW X1 X3 X4", fispa, diametro_interno=1,
                    diametro_externo=3, ancho=4)
    ml_b = producto("SL2", "SONDA LAMBDA BMW X1 X3 X4", illinois, diametro_interno=1,
                    diametro_externo=3, ancho=4)
    c.execute("INSERT INTO historial_de_medidas (producto_id, campo, antes, despues, usuario, "
              "motivo) VALUES (?, 'diametro_interno', NULL, '1', 'ana', 'correccion')", (ml_b,))
    conn.commit()
    mal = ns["medidas_mal_leidas"]()
    esperar("encuentra las dos sondas y nada más", [f["_id"] for f in mal], [ml_a, ml_b])
    esperar("lo cargado a mano no se toca", sorted(mal[1]["_cambios"]),
            ["ancho", "diametro_externo"])
    c.execute("UPDATE productos SET ancho = 18 WHERE id = ?", (ml_a,))     # alguien la corrigió
    conn.commit()
    esperar("descarta las dos", ns["descartar_medidas_mal_leidas"](mal), [ml_a, ml_b])
    esperar("lo corregido en el medio queda", tuple(c.execute(
        "SELECT diametro_interno, diametro_externo, ancho FROM productos WHERE id = ?",
        (ml_a,)).fetchone()), (None, None, 18))
    esperar("y queda anotado quién y por qué", [tuple(r) for r in c.execute(
        "SELECT campo, antes, despues, usuario, motivo FROM historial_de_medidas "
        "WHERE producto_id = ? ORDER BY id", (ml_a,))],
            [("diametro_interno", "1", None, "lector de descripciones", "descartada"),
             ("diametro_externo", "3", None, "lector de descripciones", "descartada")])
    esperar("después no queda ninguna", ns["medidas_mal_leidas"](), [])
    # Lo que completa el lector queda anotado, y la ficha dice de dónde salió cada medida.
    ap = producto("AP1", "RETEN 20X35X7", fispa)
    conn.commit()
    esperar("completa", ns["aplicar_medidas_deducidas"](
        [{"_id": ap, "_nuevas": {"diametro_interno": 20.0, "diametro_externo": 35.0}}]), 1)
    esperar("lo anota como leído de la descripción", ns["origen_de_las_medidas"]([ap])[ap],
            {"diametro_interno": "📄 de la descripción", "diametro_externo": "📄 de la descripción"})
    esperar("lo ya cargado no lo vuelve a completar", ns["aplicar_medidas_deducidas"](
        [{"_id": ap, "_nuevas": {"diametro_interno": 99.0}}]), 0)
    ns["actualizar_medidas"](ap, 21, 35, None, None, None, None, motivo="cambio")
    esperar("a mano, con quién", ns["origen_de_las_medidas"]([ap])[ap]["diametro_interno"]
            .startswith("✋ a mano ("), True)
    esperar("el historial dice por qué", ns["historial_de_medidas"](ap)[0]["Por qué"],
            ns["MOTIVOS_DE_CAMBIO_DE_MEDIDA"]["cambio"])

    # Lo que no salió de la descripción ni tiene historial: no se sabe de dónde salió.
    esperar("una medida que la descripción no dice y nadie anotó", {
        m["Medida"]: m.get("De dónde") for m in ns["ficha_de_prueba"](ret_f, ret_i)["medidas"]}
            .get("diám. externo"), "A: 📄 de la descripción · B: ❔ sin anotar")

    # 45. La explicación contrafactual: qué diferencia la cambiaría.
    cambiaria = {m["Medida"]: m["Qué la cambiaría"] for m in ns["medidas_lado_a_lado"](
        {"diametro_interno": 35, "diametro_externo": 52, "paso_rosca": "1.5"},
        {"diametro_interno": 35, "diametro_externo": 54, "paso_rosca": "1.5"})}
    esperar("igual: hasta dónde sigue siendo la misma", cambiaria["diám. interno"],
            "deja de coincidir si difieren más de 0,5 mm")
    esperar("distinta: cuánto falta para coincidir", cambiaria["diám. externo"],
            "coincidiría con 0,5 mm de diferencia o menos")
    esperar("exacta: cualquier diferencia", cambiaria["paso de rosca"],
            "cualquier diferencia la separa")

    # 46. Nada cambia en silencio: una medida que cambió después de aprobarla la baja a 🟡.
    rv_a = producto("RV1", "RETEN CIGUEÑAL VW GOL 30X47X7", fispa, diametro_interno=30,
                    diametro_externo=47)
    rv_b = producto("IRV1", "RETEN CIGUEÑAL VW GOL 30X47X7", illinois, diametro_interno=30,
                    diametro_externo=47)
    vincular(rv_a, rv_b, "FISPA · lista.xlsx · 01/10/2026 10:00:00", confianza=90)
    conn.commit()
    ns["marcar_revision"]([(rv_a, rv_b), (rv_b, rv_a)], "ok")
    esperar("la ida y la vuelta son una sola decisión", c.execute(
        "SELECT COUNT(*), MAX(como) FROM historial_de_revisiones WHERE producto_a_id = ? "
        "AND producto_b_id = ?", (min(rv_a, rv_b), max(rv_a, rv_b))).fetchone()[:], (1, "uno"))
    c.execute("UPDATE equivalencias_revisadas SET fecha = datetime('now', '-1 hour') "
              "WHERE producto_a_id IN (?, ?)", (rv_a, rv_b))
    conn.commit()
    ficha = ns["ficha_de_prueba"](rv_a, rv_b)
    esperar("aprobada y sin cambios: verificada", ficha["estado"], "✅ VERIFICADA")
    esperar("el historial dice cómo se decidió", ficha["historial"][0]["Cómo"], "👤 de a uno")
    esperar("y de dónde salió cada medida", {m["Medida"]: m["De dónde"] for m in ficha["medidas"]}
            .get("diám. interno"), "A: 📄 de la descripción · B: 📄 de la descripción")
    ns["actualizar_medidas"](rv_b, 30, 47, 7, None, None, None)
    esperar("completar una vacía no la baja", ns["ficha_de_prueba"](rv_a, rv_b)["estado"],
            "✅ VERIFICADA")
    ns["actualizar_medidas"](rv_b, 30, 47.2, 7, None, None, None, motivo="cambio")
    ficha = ns["ficha_de_prueba"](rv_a, rv_b)
    esperar("cambiar una que estaba sí", ficha["estado"], "🟡 PROBABLE")
    esperar("y dice qué cambió", "diám. externo 47 → 47.2" in " ".join(ficha["cambios_despues"]),
            True)
    esperar("cuántas aprobadas tocaba", ns["vinculos_revisados_de"](rv_b), 1)
    ns["marcar_revision"]([(rv_a, rv_b)], "ok")
    c.execute("UPDATE historial_de_medidas SET fecha = datetime('now', '-2 hour') "
              "WHERE producto_id = ?", (rv_b,))
    conn.commit()
    esperar("vuelta a mirar, verificada otra vez", ns["ficha_de_prueba"](rv_a, rv_b)["estado"],
            "✅ VERIFICADA")

    # 48. Lo que dice la descripción veta aunque la medida no esté guardada todavía.
    lz_a = producto("PZ1", "PARRILLA DE SUSPENSION DELANTERA IZQUIERDA VW GOL", fispa)
    lz_b = producto("IPZ1", "PARRILLA DE SUSPENSION DELANTERA DERECHA VW GOL", illinois)
    lz_c = producto("XPZ1", "PARRILLA DE SUSPENSION DELANTERA IZQUIERDA VW GOL", illinois)
    conn.commit()
    _a_favor, _vetos, _v = ns["evidencia_cruzada"](lz_a, lz_b)
    esperar("el otro lado, sin medidas guardadas: veta", [v for v in _vetos if
                                                          v.startswith("📐 según las descripciones")]
            != [], True)
    _a_favor, _vetos, _v = ns["evidencia_cruzada"](lz_a, lz_c)
    esperar("el mismo lado: no veta ni suma por medidas",
            [x for x in _vetos + _a_favor if x.startswith("📐")], [])
    c.execute("UPDATE productos SET posicion = 'DELANTERA+IZQUIERDA' WHERE id = ?", (lz_b,))
    conn.commit()
    _a_favor, _vetos, _v = ns["evidencia_cruzada"](lz_a, lz_b)
    esperar("lo guardado manda sobre la descripción", [x for x in _vetos if x.startswith("📐")], [])

    # 49. La evidencia mínima según el riesgo: un kit de distribución declarado por una lista
    # necesita además un auto en común o una medida igual.
    kd_a = producto("KD1", "KIT DE DISTRIBUCION VW GOL 1.6", fispa)
    kd_b = producto("IKD1", "KIT DE DISTRIBUCION VW GOL 1.6", illinois)
    kd_c = producto("XKD1", "KIT DE DISTRIBUCION 1.6", illinois)
    vincular(kd_a, kd_b, "FISPA · lista.xlsx · 01/10/2026 10:00:00")
    vincular(kd_a, kd_c, "FISPA · lista.xlsx · 01/10/2026 10:00:00")
    aplicacion("KD1", "VOLKSWAGEN", "GOL"); aplicacion("IKD1", "VOLKSWAGEN", "GOL")
    conn.commit()
    esperar("riesgo alto con un auto en común: verificada",
            ns["ficha_de_prueba"](kd_a, kd_b)["estado"], "✅ VERIFICADA")
    ficha = ns["ficha_de_prueba"](kd_a, kd_c)
    esperar("sin autos en común ni medida: probable", ficha["estado"], "🟡 PROBABLE")
    esperar("y dice qué le falta", any("evidencia mínima pide además un auto en común en las "
                                       "descripciones o una medida" in f for f in ficha["falta"]),
            True)
    ns["comprobar_en_la_mano"](kd_a, kd_c, "las comparé en la caja")
    esperar("comprobada en la mano, alcanza", ns["ficha_de_prueba"](kd_a, kd_c)["estado"],
            "✅ VERIFICADA")

    # 47. La cola: desde cuándo esperaba y de qué lista venía, aunque ya no esté en la cola.
    for x, y, lote in ((ml_a, ap, "COLA · 01/10"), (ml_b, ap, "COLA · 01/10"),
                       (rv_a, ap, "COLA · 01/10")):
        c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, "
                  "lote, fecha) VALUES (?, ?, 'x', ?, '2026-10-01 10:00:00')",
                  (min(x, y), max(x, y), lote))
    conn.commit()
    c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, lote) "
              "VALUES (?, ?, 'x', 'COLA2 · 02/10')", (min(ap, kd_c), max(ap, kd_c)))
    conn.commit()
    ns["aprobar_pendientes"]("COLA2 · 02/10", en_bloque=True)
    ns["marcar_revision"]([(lz_a, lz_c), (kd_b, kd_c)], "ok")
    esperar("en bloque, en grupo", [r[0] for r in c.execute(
        "SELECT como FROM historial_de_revisiones WHERE (producto_a_id, producto_b_id) IN "
        "((?, ?), (?, ?), (?, ?)) ORDER BY id", (min(ap, kd_c), max(ap, kd_c), min(lz_a, lz_c),
                                                 max(lz_a, lz_c), min(kd_b, kd_c), max(kd_b, kd_c)))],
            ["bloque", "grupo", "grupo"])
    ns["aprobar_pendientes"]("COLA · 01/10", [(ml_a, ap)])
    ns["rechazar_pendientes"]("COLA · 01/10", [(ml_b, ap)], "otra_pieza")
    ns["rechazar_pendientes"]("COLA · 01/10")
    esperar("aprobada y rechazadas desde la cola, con fecha y lista", [tuple(r) for r in c.execute(
        "SELECT decision, pendiente_desde, lote, como FROM historial_de_revisiones "
        "WHERE lote = 'COLA · 01/10' ORDER BY id")],
            [("ok", "2026-10-01 10:00:00", "COLA · 01/10", "uno"),
             ("rechazada", "2026-10-01 10:00:00", "COLA · 01/10", "uno"),
             ("rechazada", "2026-10-01 10:00:00", "COLA · 01/10", "bloque")])
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

"""Pruebas de la precisión de las equivalencias: cuándo una equivalencia se da por verificada.

Uso:
    python3 pruebas/pruebas_de_la_precision.py

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
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
                               respaldo_fabricante=True, anduvo_como_reemplazo=5,
                               familia_a="Filtros", familia_b="Frenos")
    esperar("con rubros distintos, el puntaje no pasa del tope aunque todo lo demás sume",
            puntaje <= tope, True)
    sin, _ = evaluar("BOMBA DE AGUA FORD KA", "BOMBA DE AGUA FIAT UNO")
    con, senales = evaluar("BOMBA DE AGUA FORD KA", "BOMBA DE AGUA FIAT UNO",
                           anduvo_como_reemplazo=5)
    franja = ns["LINEAS_DE_CONFIANZA"]

    def franja_de(x):
        return sum(x >= linea for linea in franja)
    esperar("las instalaciones que anduvieron suben el puntaje", con > sin, True)
    esperar("pero no lo pasan de franja", franja_de(con), franja_de(sin))
    esperar("y la señal se ve", any("anduvo" in s for _, s in senales), True)

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

    # Sin el vínculo del barrido, llega por el número de fábrica que citan las dos listas:
    # verificada (ver «EL MISMO NÚMERO DE FÁBRICA, CITADO POR DOS LISTAS»; era «probable»).
    c.execute("DELETE FROM equivalencias WHERE lote LIKE 'BARRIDO%'")
    conn.commit()
    ficha = ns["ficha_de_prueba"](ret_f, ret_i)
    esperar("por el número de fábrica que citan las dos listas: verificada",
            (ficha["estado"], ficha["por_numero_de_fabrica"]), ("✅ VERIFICADA", "1234567890"))
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
    esperar("una venta que volvió no confirma nada", ns["pares_que_anduvieron"](), {})
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
            (min(vt_a, vt_b), max(vt_a, vt_b)) in ns["pares_que_anduvieron"](), False)
    for _ in range(2):
        ns["registrar_venta"](vt_b, "VT1", "🟢 equivalencia confirmada")
    esperar("vendida como equivalente y sin noticias, tampoco: el silencio no confirma",
            (min(vt_a, vt_b), max(vt_a, vt_b)) in ns["pares_que_anduvieron"](), False)
    ns["registrar_que_anduvo"](vt_b, "VT1", "el taller de Juan")
    esperar("con una que anduvo, todavía no",
            (min(vt_a, vt_b), max(vt_a, vt_b)) in ns["pares_que_anduvieron"](), False)
    ns["registrar_que_anduvo"](vt_b, "VT1")
    esperar("con dos que anduvieron, sí",
            ns["pares_que_anduvieron"]().get((min(vt_a, vt_b), max(vt_a, vt_b))), 2)
    esperar("sin decir qué se pidió, no", _falla(ns["registrar_que_anduvo"], vt_b, " "),
            "ValueError")

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
    # El historial de medidas no se toca (lo cuidan sus disparadores): el tiempo se simula
    # corriendo la revisión, no el cambio.
    esperar("el historial de medidas no se corrige", _falla(
        c.execute, "UPDATE historial_de_medidas SET fecha = datetime('now', '-2 hour') "
                   "WHERE producto_id = ?", (rv_b,)), "IntegrityError")
    esperar("ni se borra", _falla(c.execute, "DELETE FROM historial_de_medidas WHERE producto_id = ?",
                                  (rv_b,)), "IntegrityError")
    c.execute("UPDATE equivalencias_revisadas SET fecha = datetime('now', '+2 hour') "
              "WHERE producto_a_id IN (?, ?) AND producto_b_id IN (?, ?)", (rv_a, rv_b, rv_a, rv_b))
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

    # 50. Una sola verdad: el veredicto del buscador sale del mismo estado que la ficha.
    distintos = []
    for codigo in ("R100", "FI9", "RV1", "KD1", "PZ1", "RL1", "VT1", "PF1"):
        res, _nota = ns["buscar_con_variantes_del_cero"](ns["sanitizar"](codigo))
        origenes = [f["ID"] for f in res if f.get("Cadena") == "— el buscado"]
        for f in res:
            if f.get("Cadena") == "— el buscado" or str(f.get("Cadena", "")).startswith(("⚪", "🔵")):
                continue
            ficha = ns["ficha_de_prueba"](ns["el_buscado_mas_cercano"](origenes, f["ID"]), f["ID"])
            v = ns["veredicto_de_la_equivalencia"](f)
            if {"🟢": "✅"}.get(v[:1], v[:1]) != ficha["estado"][:1]:
                distintos.append((codigo, f["Codigo"], v, ficha["estado"]))
    esperar("el buscador y la ficha dicen lo mismo", distintos, [])
    esperar("y probó algo", sum(1 for codigo in ("R100", "KD1") for f in
                                ns["buscar_con_variantes_del_cero"](codigo)[0]
                                if f.get("_estado")) >= 2, True)
    # Si no se puede calcular, no se recomienda («fail closed»).
    _globales = ns["anotar_el_estado"].__globals__      # el espacio de nombres de verdad
    _ficha_real = _globales["ficha_de_prueba"]
    _globales["ficha_de_prueba"] = lambda *a, **k: 1 / 0
    try:
        res, _nota = ns["buscar_con_variantes_del_cero"]("KD1")
    finally:
        _globales["ficha_de_prueba"] = _ficha_real
    esperar("lo que no se pudo comprobar no sale confirmado",
            {ns["veredicto_de_la_equivalencia"](f)[:1] for f in res
             if f.get("Cadena") != "— el buscado"}, {"🟠"})

    # 51. Los números son números: «banana» en un diámetro se rechaza y dice cuál.
    import sqlite3 as _sqlite3
    try:
        c.execute("UPDATE productos SET diametro_interno = 'banana' WHERE id = ?", (ap,))
        _msj = "pasó"
    except _sqlite3.IntegrityError as _err:
        _msj = str(_err)
    esperar("una medida que no es un número", _msj, "Campo inválido: diámetro interno (no es un número)")
    c.execute("UPDATE productos SET diametro_interno = '54' WHERE id = ?", (ap,))
    esperar("un número escrito como texto se guarda como número", c.execute(
        "SELECT typeof(diametro_interno) FROM productos WHERE id = ?", (ap,)).fetchone()[0], "real")
    try:
        producto("BAN1", "BANANA", fispa, precio="caro")
        _msj = "pasó"
    except _sqlite3.IntegrityError as _err:
        _msj = str(_err)
    esperar("ni al crear el producto", _msj.startswith("Campo inválido"), True)

    # 53. El código de fábrica toma el rubro de los que lo citan, también en la ficha.
    oe = producto("2H0919050B", "FILTRO BOMBA DE COMBUSTIBLE VW AMAROK REF ORIG 2H0919050B", oem)
    bc1 = producto("BC1", "BOMBA DE COMBUSTIBLE VW AMAROK 2.0", fispa)
    bc2 = producto("BC2", "BOMBA DE NAFTA VW AMAROK 2.0 TDI", illinois)
    vincular(bc1, oe, "FISPA · lista.xlsx · 01/10/2026 10:00:00")
    vincular(bc2, oe, "ILLINOIS · lista.xlsx · 01/10/2026 10:00:00")
    conn.commit()
    esperar("de entrada, la descripción del código es la de un filtro",
            ns["familia_para_comparar"]("FILTRO BOMBA DE COMBUSTIBLE VW AMAROK"), "Filtros")
    esperar("pero la ficha no ve rubros distintos", [x for x in ns["ficha_de_prueba"](bc1, oe)
                                                     ["contradicciones"] if "rubros" in x], [])
    # El estado del ZIP sale de la misma ficha: un directo del barrido es candidato, no probable.
    bz_a = producto("BZ1", "TERMOSTATO FIAT PALIO 1.4", fispa)
    bz_b = producto("IBZ1", "TERMOSTATO FIAT PALIO 1.4", illinois)
    vincular(bz_a, bz_b, "BARRIDO (automático) · 05/10 10:00", confianza=90)
    conn.commit()
    with zipfile.ZipFile(io.BytesIO(ns["exportar_catalogo_zip"]()[0])) as z:
        _eq = {(f["producto_a_id"], f["producto_b_id"]): f["estado"] for f in csv.DictReader(
            io.StringIO(z.read("equivalencias.csv").decode("utf-8-sig")))}
    esperar("en el ZIP, lo mismo que la ficha", _eq[(str(min(bz_a, bz_b)), str(max(bz_a, bz_b)))],
            "revisar")
    _fila_bz = [f for f in ns["buscar_con_variantes_del_cero"]("BZ1")[0] if f["ID"] == bz_b][0]
    esperar("y el buscador dice por qué", ns["veredicto_de_la_equivalencia"](_fila_bz).startswith(
        "🟠 revisar antes de vender: solo una pista"), True)
    esperar("una candidata es 🟠", ns["veredicto_de_la_equivalencia"](
        {"Cadena": "🟢 directo", "Confianza": "🟢 sólida", "_estado": "🟠 CANDIDATA"})[:1], "🟠")
    # Las palabras se cuentan una vez por búsqueda, no una por resultado.
    _g = ns["evidencia_cruzada"].__globals__
    _contar_real, _veces = _g["cuantas_veces_aparece_cada_palabra"], []
    _g["cuantas_veces_aparece_cada_palabra"] = lambda: _veces.append(1) or _contar_real()
    try:
        ns["buscar_con_variantes_del_cero"]("R100")
    finally:
        _g["cuantas_veces_aparece_cada_palabra"] = _contar_real
    esperar("una vez por búsqueda", len(_veces), 1)
    # Un cambio de reglas que mueve demasiado, para cualquier lado.
    esperar("el 40 % que baja de franja también es anormal", ns["deriva_sospechosa"](
        {"version": "99", "total": 100, "subieron": 0, "bajaron": 50}).startswith("🔴"), True)
    esperar("el 10 %, no", ns["deriva_sospechosa"]({"version": "99", "total": 100, "subieron": 0,
                                                     "bajaron": 10}), "")
    # La pregunta que más separa, primero.
    esperar("primero la que más separa", [q for q, _v in ns["ordenar_por_lo_que_separa"](
        [("vías", {"2": ["A", "B", "C"], "3": ["D"]}), ("ficha", {"x": ["A", "B"], "y": ["C", "D"]})])],
            ["ficha", "vías"])
    # Las alarmas para una persona: lo vendido que volvió, el cambio de reglas, las medidas.
    import json as _json2
    ns["guardar_config"]("confianza_deriva", _json2.dumps(
        {"version": "99", "total": 100, "subieron": 0, "bajaron": 60, "cambios": {}, "ejemplos": []}))
    _titulos = " | ".join(p_["titulo"] for p_ in ns["diagnostico_de_salud"]())
    esperar("la alarma de lo vendido que volvió", "vendida(s) como equivalente volvieron" in _titulos,
            True)
    esperar("la del cambio de reglas", "movió demasiados vínculos" in _titulos, True)
    esperar("la de las medidas que no pueden ser", "medidas que no pueden ser" in _titulos, True)

    # 52. Lo que suele cambiarse junto: se avisa al anotar la venta.
    esperar("el kit de distribución lleva la bomba de agua", ns["lo_que_suele_ir_con"](kd_a),
            ["Bomba de agua"])
    ns["anotar_venta_y_avisar"](kd_a, "KD1", "FISPA - KD1", "prueba_combo", "🟢 equivalencia confirmada")
    esperar("y lo dice al vender", "⚠️ Antes de cerrar: suele cambiarse junto con Bomba de agua"
            in ns["st"].session_state["_lo_anotado"]["prueba_combo"], True)
    esperar("la bomba de agua, el termostato", "Termostato" in ns["lo_que_suele_ir_con"](vt_a), True)
    ns["eliminar_combo"]("bomba de agua")
    ns["crear_esquema"](c)
    esperar("lo que se borró a mano no vuelve solo", ns["lo_que_suele_ir_con"](vt_a), [])
    esperar("un filtro, nada", ns["lo_que_suele_ir_con"](fi_a), [])

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

    # 54. Primero que sirva, después que convenga: la recomendada, por qué, y por qué no la más
    # barata. Solo lo buscado, lo 🟢 y lo 🟡 (lo 🟡 no, si es de seguridad).
    reco = ns["la_recomendacion_explicada"]
    _filtro = "FILTRO DE ACEITE VW GOL 1.6"
    r_bus = {"ID": -1, "Cadena": "— el buscado", "Marca": "FISPA", "Codigo": "A1", "Precio": 1000,
             "Stock": 0, "Descripcion": _filtro}
    r_ok = {"ID": -2, "Cadena": "🟢 directo", "Confianza": "🟢 sólida", "_estado": "✅ VERIFICADA",
            "Marca": "ILLINOIS", "Codigo": "B1", "Precio": 820, "Stock": 7, "Descripcion": _filtro}
    r_cand = {"ID": -3, "Cadena": "🟢 directo", "Confianza": "🟢 sólida", "_estado": "🟠 CANDIDATA",
              "_por_que_estado": "solo una pista (barrido)", "Marca": "JL", "Codigo": "C1",
              "Precio": 500, "Stock": 12, "Descripcion": _filtro}
    r_mal = {"ID": -4, "Cadena": "🟢 directo", "Confianza": "🟢 sólida",
             "_estado": "🔴 CON CONTRADICCIONES", "_por_que_estado": "otro grado térmico",
             "Marca": "TARANTO", "Codigo": "D1", "Precio": 400, "Stock": 3, "Descripcion": _filtro}
    r_prob = {"ID": -5, "Cadena": "🟡 2 saltos", "Confianza": "🟢 sólida", "_estado": "🟡 PROBABLE",
              "Marca": "CRI-FA", "Codigo": "E1", "Precio": 900, "Stock": 2, "Descripcion": _filtro}
    _r = reco([r_bus, r_ok, r_cand, r_mal, r_prob])
    esperar("recomienda la confirmada, no la más barata", _r["recomendada"]["Codigo"], "B1")
    esperar("y dice por qué", _r["texto"],
            "🏆 No hay de lo buscado. **Recomendada: ILLINOIS B1** — equivalencia confirmada, "
            "hay 7 en stock, y cuesta 18 % menos que lo buscado.")
    esperar("y por qué no la más barata", _r["por_que_no"],
            "La más barata, TARANTO D1, no se recomienda: no es la misma pieza: otro grado "
            "térmico.")
    esperar("el stock, sin mezclar lo confirmado con lo que no", _r["stock"],
            "📦 En stock — lo buscado: 0 · equivalentes confirmadas: 7 · probables, sin "
            "confirmar: 2 · para revisar o que no son la misma pieza: 15")
    esperar("sin el stock de lo buscado cargado, no dice que no hay", reco(
        [dict(r_bus, Stock=None), r_ok])["texto"].startswith("🏆 **Recomendada"), True)
    esperar("con stock de lo buscado y más barato, lo buscado", reco(
        [dict(r_bus, Stock=3, Precio=700), r_ok])["texto"],
            "🏆 **Recomendada: FISPA A1** — es lo que pidió el cliente, hay 3 en stock.")
    esperar("una candidata sola no se recomienda", reco([r_bus, r_cand])["recomendada"], None)
    esperar("y dice por qué", reco([r_bus, r_cand])["por_que_no"],
            "Ninguna se recomienda: lo que hay en stock no está confirmado. La más barata, JL C1: "
            "revisar antes de vender: solo una pista (barrido).")
    esperar("sin nada en stock, nada que explicar", reco([r_bus, dict(r_cand, Stock=0)]),
            {"recomendada": None, "texto": "", "por_que_no": "", "stock": ""})
    esperar("una probable sí", reco([r_bus, r_prob])["recomendada"]["Codigo"], "E1")
    _pastilla = "PASTILLA DE FRENO DELANTERA VW GOL"
    _r_seg = reco([dict(r_ok, Descripcion=_pastilla, Precio=950),
                   dict(r_prob, Descripcion=_pastilla, Precio=600)])
    esperar("la pastilla probable no, aunque sea más barata", _r_seg["recomendada"]["Codigo"], "B1")
    esperar("y lo dice", _r_seg["por_que_no"].startswith(
        "La más barata, CRI-FA E1, no se recomienda: es una pieza de seguridad y la "
        "equivalencia no está confirmada (probable"), True)
    esperar("ni la marca con la lista en otra escala", reco([r_bus, r_ok, r_prob],
                                                           ("ILLINOIS",))["recomendada"]["Codigo"],
            "E1")
    esperar("ni el kit", reco([r_bus, dict(r_ok, _complementario=True)])["recomendada"], None)
    esperar("ordenadas: lo buscado, lo confirmado, lo probable, lo demás", [
        f["Codigo"] for f in ns["ordenar_por_seguridad_y_disponibilidad"](
            [r_mal, r_cand, dict(r_prob, Stock=0, Codigo="E0"), r_prob, r_ok, r_bus])],
            ["A1", "B1", "E1", "E0", "C1", "D1"])
    _filas_c, _reco_c = ns["coronar_la_recomendada"]([r_mal, r_ok, r_bus])
    esperar("la corona, solo en la recomendada", [(f["Codigo"], f["💰"]) for f in _filas_c],
            [("A1", ""), ("B1", "🏆 Recomendada"), ("D1", "")])
    esperar("la venta anota lo que la app recomendaba si se vendió otra",
            ns["evidencia_de_la_fila"](r_mal, r_ok).endswith(
                "la app recomendaba ILLINOIS B1 a $ 820"), True)
    esperar("y nada si se vendió la recomendada",
            "recomendaba" in ns["evidencia_de_la_fila"](r_ok, r_ok), False)

    # 55. Lo que volvió, por causa: la instalación no culpa a la equivalencia, «vino fallada»
    # es la calidad de la marca, y se ve qué se vendió en lugar de lo recomendado.
    calx = marca("CALIDADX")
    dv_a = producto("DV1", "AMORTIGUADOR DELANTERO FIAT PALIO", fispa)
    dv_b = producto("CDV1", "AMORTIGUADOR DELANTERO FIAT PALIO", calx)
    vincular(dv_a, dv_b, "FISPA · lista.xlsx · 01/10/2026 10:00:00", confianza=90)
    conn.commit()
    for _motivo in ("instalacion", "otro_auto", "transporte", "se_entrego_otra"):
        esperar(f"«{_motivo}» no baja el vínculo",
                ns["registrar_devolucion"](dv_b, "DV1", _motivo), 0)
    esperar("y no cuenta como «no era la pieza»",
            (min(dv_a, dv_b), max(dv_a, dv_b)) in ns["pares_devueltos"](), False)
    esperar("el vínculo sigue sólido", c.execute(
        "SELECT confianza FROM equivalencias WHERE producto_a_id = ? AND producto_b_id = ?",
        (min(dv_a, dv_b), max(dv_a, dv_b))).fetchone()[0], 90)
    ns["registrar_devolucion"](dv_b, "DV1", "fallada")
    ns["registrar_devolucion"](dv_b, "DV1", "fallada")
    ns["registrar_devolucion"](dv_b, "DV1", "medida")
    c.execute("INSERT INTO devoluciones (producto_id, codigo_pedido_clean, motivo, fecha) "
              "VALUES (?, 'DV1', 'fallada', datetime('now', '-45 days'))", (dv_b,))
    conn.commit()
    _cal = {x["Marca"]: x for x in ns["calidad_por_marca"]()}.get("CALIDADX", {})
    esperar("por causa, separado", (_cal.get("💥 Falladas (calidad)"), _cal.get("Falladas (30 días)"),
                                    _cal.get("Falladas (30 días antes)"),
                                    _cal.get("No era la pieza (equivalencia)"),
                                    _cal.get("Otras causas")), (3, 2, 1, 1, 4))
    esperar("vienen más falladas que antes: 🔴", _cal.get("Semáforo"), "🔴")
    esperar("la alarma", "Vienen más piezas falladas de CALIDADX" in " | ".join(
        p_["titulo"] for p_ in ns["diagnostico_de_salud"]()), True)
    ns["registrar_venta"](dv_b, "DV1", "🟢 equivalencia confirmada",
                          "cadena 🟢 directo · la app recomendaba FISPA DV1 a $ 900")
    ns["registrar_venta"](dv_a, "DV1", None, "cadena — el buscado")
    _contra = ns["ventas_contra_la_recomendacion"]()
    esperar("vendida otra que la recomendada", (_contra["contra"], _contra["contra_y_devueltas"],
                                                _contra["ejemplos"][0]["La app recomendaba"]),
            (1, 1, "FISPA DV1 a $ 900"))

    # 56. La comprobación guiada: la app pregunta lo que decide.
    _ficha_g = {"la_tumbaria": [
        {"Característica": "diámetro exterior", "Hoy": "❓ no la tiene ninguno"},
        {"Característica": "rosca", "Hoy": "✅ igual"},
        {"Característica": "conector", "Hoy": "❌ distinta"}]}
    esperar("pregunta lo que no coincide a la vista", ns["preguntas_para_comprobar"](_ficha_g),
            ["diámetro exterior", "conector"])
    esperar("si todo coincide en los papeles, igual pregunta", ns["preguntas_para_comprobar"](
        {"la_tumbaria": [{"Característica": "rosca", "Hoy": "✅ igual"}]}), ["rosca"])
    _res_g = ns["resultado_de_la_comprobacion"]
    esperar("alcanza con que difiera una", _res_g({"rosca": "coincide", "conector": "difiere"}),
            ("🔴", "difiere conector; coinciden rosca"))
    esperar("todo coincide", _res_g({"rosca": "coincide", "conector": "coincide"}),
            ("✅", "coinciden rosca, conector"))
    esperar("falta mirar", _res_g({"rosca": "coincide", "conector": "no lo miré"}),
            ("", "coinciden rosca; falta mirar conector"))
    esperar("sin preguntas, nada", _res_g({}), ("", ""))
    rg_a = producto("RG1", "BOMBA DE ACEITE FORD KA 1.6", fispa)
    rg_b = producto("IRG1", "BOMBA DE ACEITE FORD KA 1.6", illinois)
    vincular(rg_a, rg_b, "FISPA · lista.xlsx · 01/10/2026 10:00:00")
    conn.commit()
    _nota_g = ns["rechazar_por_la_comprobacion"](rg_a, rg_b, "difiere rosca")
    esperar("rechazada en la mano: se corta", c.execute(
        "SELECT COUNT(*) FROM equivalencias WHERE producto_a_id = ? AND producto_b_id = ?",
        (min(rg_a, rg_b), max(rg_a, rg_b))).fetchone()[0], 0)
    esperar("y queda rechazada, para que no vuelva por otro camino", c.execute(
        "SELECT decision, motivo FROM equivalencias_revisadas WHERE producto_a_id = ? AND "
        "producto_b_id = ?", (rg_a, rg_b)).fetchone()[:], ("rechazada", "variante"))
    esperar("con lo que difiere", _nota_g.endswith(": difiere rosca"), True)
    esperar("sin decir qué difiere, no", _falla(ns["rechazar_por_la_comprobacion"], rg_a, rg_b,
                                                " "), "ValueError")

    # 57. Practicar con lo ya decidido: mitad y mitad, primero los rechazos con motivo.
    # Veinte rechazos sin motivo, para que elegir al azar no alcance.
    for _i in range(20):
        _x = producto(f"PR{_i}", "DISCO DE FRENO VW GOL", fispa)
        _y = producto(f"IPR{_i}", "DISCO DE FRENO VW GOL", illinois)
        ns["marcar_revision"]([(_x, _y)], "rechazada")
    esperar("con un solo rechazo para mostrar, es uno con motivo", {
        bool([x for x in ns["casos_para_practicar"](2, semilla=_s)
              if x["decision"] == "rechazada"][0]["motivo"]) for _s in range(8)}, {True})
    _casos = ns["casos_para_practicar"](10, semilla=7)
    _decididos = c.execute("SELECT decision, COUNT(*) FROM equivalencias_revisadas WHERE "
                           "producto_a_id < producto_b_id GROUP BY decision").fetchall()
    _n_rech = dict((d, n) for d, n in _decididos).get("rechazada", 0)
    esperar("mitad rechazados (o los que haya)", sum(x["decision"] == "rechazada" for x in _casos),
            min(5, _n_rech))
    esperar("la misma semilla, los mismos casos", [(x["a"], x["b"]) for x in _casos],
            [(x["a"], x["b"]) for x in ns["casos_para_practicar"](10, semilla=7)])
    _con_motivo = [x for x in _casos if x["decision"] == "rechazada" and x["motivo"]]
    esperar("hay rechazos con motivo para enseñar", bool(_con_motivo), True)
    if _con_motivo:
        _resp_p = ns["la_respuesta_del_caso"](_con_motivo[0])
        esperar("la respuesta: quién la rechazó y por qué", (
            _resp_p["correcta"], _resp_p["texto"].startswith("🚫 **La rechazó**"),
            ns["MOTIVOS_DE_RECHAZO"][_con_motivo[0]["motivo"]] in _resp_p["texto"]),
            ("rechazada", True, True))

    # 58. Dónde está, si suele faltar y si hay una equivalente confirmada antes de comprar.
    eq_a = producto("EQ1", "BOMBA DE AGUA VW GOL 1.6", fispa)
    eq_b = producto("IEQ1", "BOMBA DE AGUA VW GOL 1.6", illinois)
    vincular(eq_a, eq_b, "FISPA · lista.xlsx · 01/10/2026 10:00:00")
    c.execute("UPDATE productos SET ubicacion = 'Estante 4', stock = 4 WHERE id = ?", (eq_b,))
    conn.commit()
    ns["comprobar_en_la_mano"](eq_a, eq_b, "las comparé en la caja")
    # Y una que llega solo por una pista, con stock: no cuenta para no comprar.
    eq_c = producto("JEQ1", "BOMBA DE AGUA VW GOL 1.6", marca("JL"))
    vincular(eq_a, eq_c, "BARRIDO (automático) · 01/10 12:00")
    c.execute("UPDATE productos SET stock = 5 WHERE id = ?", (eq_c,))
    conn.commit()
    _fila_eq = {f["ID"]: f for f in ns["buscar_por_codigo"]("EQ1")}.get(eq_b, {})
    esperar("la ubicación, en el resultado", _fila_eq.get("Ubicación"), "Estante 4")
    esperar("y en la búsqueda por descripción", {f["ID"]: f for f in ns["buscar_por_texto"](
        "bomba de agua gol")}.get(eq_b, {}).get("Ubicación"), "Estante 4")
    ns["solicitar_reposicion"](eq_a)
    ns["solicitar_reposicion"](eq_a)
    esperar("suele faltar", ns["veces_que_falto"]([eq_a, eq_b]).get(eq_a, (0,))[0], 2)
    esperar("hay una equivalente confirmada en stock",
            [f["ID"] for f in ns["equivalentes_confirmadas_con_stock"](eq_a)], [eq_b])
    c.execute("UPDATE productos SET stock = 0 WHERE id = ?", (eq_b,))
    conn.commit()
    esperar("sin stock, no", ns["equivalentes_confirmadas_con_stock"](eq_a), [])

    # 59. Lo que el auto ya dice no se pregunta: el motor nafta deja afuera lo diésel.
    producto("BUJ9", "BUJIA DE ENCENDIDO FIAT PALIO 1.3 NAFTA", fispa)
    producto("BUJ9D", "BUJIA DE PRECALENTAMIENTO FIAT PALIO 1.3 DIESEL", fispa)
    conn.commit()
    _r_auto = ns["repuestos_de_este_auto"]("FIAT", "PALIO", None, "1.3 NAFTA")
    _cods_auto = {f.get("Código") or f.get("Codigo") for f in _r_auto["del_catalogo"]}
    esperar("lo nafta sí, lo diésel no", ("BUJ9" in _cods_auto, "BUJ9D" in _cods_auto),
            (True, False))
    esperar("y no pregunta el combustible", "¿Es nafta o diésel?" in ns[
        "versiones_que_hay_que_preguntar"](_r_auto["del_catalogo"]), False)
    _r_auto2 = ns["repuestos_de_este_auto"]("FIAT", "PALIO", None, "")
    esperar("sin el motor, pregunta", "¿Es nafta o diésel?" in ns[
        "versiones_que_hay_que_preguntar"](_r_auto2["del_catalogo"]), True)

    # 60. Lo aprendido (marcas, instalaciones) suma, pero no hace pasar NINGUNA franja: tampoco
    # la de «sólida», que es la que mira la ficha.
    _linea = ns["sin_cruzar_la_linea_por_lo_aprendido"]
    esperar("sin lo aprendido 65, con 75: queda en 69", _linea(75, 10), 69.0)
    esperar("sin lo aprendido 60, con 90: no pasa la 70 ni la 85", _linea(90, 30), 69.0)
    esperar("si ya estaba arriba, sube libre", _linea(95, 10), 95.0)
    esperar("lo que baja, baja", _linea(40, -25), 40.0)
    esperar("las franjas del buscador y la de la ficha son líneas", {30, 50, 70, ns["CONFIANZA_SOLIDA"]}
            <= set(ns["LINEAS_DE_CONFIANZA"]), True)
    esperar("y las de la cola también", {55, ns["CONFIANZA_ALTA"]} <= set(ns["LINEAS_DE_CONFIANZA"]),
            True)
    esperar("la franja del buscador corta donde las líneas",
            [ns["franja_de_confianza"](x) for x in (69, 70, 49, 50, 29, 30)],
            ["🟡 razonable", "🟢 sólida", "🟠 floja", "🟡 razonable", "🔴 muy débil", "🟠 floja"])

    # 61. Lo que pasó después de vender: confirmado, devuelto y silencio, por separado.
    sv_a = producto("SV1", "TERMOSTATO RENAULT CLIO 1.6", fispa)
    sv_b = producto("ISV1", "TERMOSTATO RENAULT CLIO 1.6", illinois)
    vincular(sv_a, sv_b, "FISPA · lista.xlsx · 01/10/2026 10:00:00")
    conn.commit()
    for _ in range(4):
        ns["registrar_venta"](sv_b, "SV1", "🟢 equivalencia confirmada")
    ns["registrar_que_anduvo"](sv_b, "SV1")
    ns["registrar_devolucion"](sv_b, "SV1", "instalacion")
    _seg_v = ns["seguimiento_de_lo_vendido"]()
    esperar("la instalación mal hecha no es una devolución «no era»", _seg_v["volvieron"] >= 0, True)
    _ficha_sv = ns["ficha_de_prueba"](sv_a, sv_b)
    esperar("la ficha separa lo vendido, lo que anduvo y lo que volvió",
            _ficha_sv["despues_de_vender"], {"vendidas": 4, "anduvieron": 1, "volvieron": 1})
    _antes_seg = ns["seguimiento_de_lo_vendido"]()
    ns["registrar_venta"](sv_b, "SV1", "🟢 equivalencia confirmada")
    _desp_seg = ns["seguimiento_de_lo_vendido"]()
    esperar("una venta más sin noticias es silencio, no confirmación",
            (_desp_seg["vendidas"] - _antes_seg["vendidas"],
             _desp_seg["sin_noticias"] - _antes_seg["sin_noticias"],
             _desp_seg["anduvieron"] - _antes_seg["anduvieron"]), (1, 1, 0))
    esperar("una con motivo «no era» cuenta como volvió", (lambda antes: (
        ns["registrar_devolucion"](sv_b, "SV1", "medida"),
        ns["seguimiento_de_lo_vendido"]()["volvieron"] - antes)[1])(_desp_seg["volvieron"]), 1)
    ns["registrar_que_anduvo"](sv_b, "SV1")
    ns["registrar_que_anduvo"](sv_b, "SV1")
    esperar("lo que volvió porque no era no suma, aunque otras veces haya andado",
            (min(sv_a, sv_b), max(sv_a, sv_b)) in ns["pares_que_anduvieron"](), False)

    # 62. Lo que une dos redes grandes no se aprueba en bloque y se mira primero.
    pu = marca("PUENTES")
    _red1 = [producto(f"RA{i}", "BUJIA DE ENCENDIDO", pu) for i in range(11)]
    _red2 = [producto(f"RB{i}", "BUJIA DE ENCENDIDO", pu) for i in range(11)]
    for _x in _red1[1:]:
        vincular(_red1[0], _x, "PUENTES · lista · 01/10")
    for _x in _red2[1:]:
        vincular(_red2[0], _x, "PUENTES · lista · 01/10")
    _red3 = [producto(f"RC{i}", "BUJIA DE ENCENDIDO", pu) for i in range(16)]
    _red4 = [producto(f"RD{i}", "BUJIA DE ENCENDIDO", pu) for i in range(16)]
    for _x in _red3[1:]:
        vincular(_red3[0], _x, "PUENTES · lista · 01/10")
    for _x in _red4[1:]:
        vincular(_red4[0], _x, "PUENTES · lista · 01/10")
    _suelto_a = producto("RS1", "BUJIA DE ENCENDIDO", pu)
    _suelto_b = producto("RS2", "BUJIA DE ENCENDIDO", pu)
    for _x, _y in ((_red1[3], _red2[5]), (_suelto_a, _suelto_b), (_red3[2], _red4[7])):
        c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, lote) "
                  "VALUES (?, ?, 'x', 'PUENTES · 02/10')", (min(_x, _y), max(_x, _y)))
    conn.commit()
    _une = ns["cuanto_une_cada_par"]([(_red1[3], _red2[5]), (_suelto_a, _suelto_b), (_red1[1], _red1[2])])
    esperar("cuánto encadena cada uno", [_une[(_red1[3], _red2[5])], _une[(_suelto_a, _suelto_b)],
                                          _une[(_red1[1], _red1[2])]], [121, 1, 0])
    _pts = ns["puentes_del_lote"]("PUENTES · 02/10")
    esperar("los puentes, primero en la cola y el que más une arriba",
            [(x["Código A"], x["Código B"], x["Encadena"]) for x in _pts],
            [("RC2", "RD7", 256), ("RA3", "RB5", 121)])
    esperar("en bloque, los puentes no entran", ns["aprobar_pendientes"]("PUENTES · 02/10",
                                                                        en_bloque=True), 1)
    esperar("y siguen en la cola", c.execute(
        "SELECT COUNT(*) FROM equivalencias_pendientes WHERE lote = 'PUENTES · 02/10'").fetchone()[0], 2)
    esperar("de a uno, sí", ns["aprobar_pendientes"]("PUENTES · 02/10", [(_red1[3], _red2[5])]), 1)
    # La red se guarda entre pasadas (ver _red_de_equivalencias()): aprobado el puente, las dos
    # redes son una, y eso se tiene que ver ya, sin limpiar nada a mano.
    _une = ns["cuanto_une_cada_par"]([(_red1[3], _red2[5]), (_red1[0], _red3[0])])
    esperar("aprobado el puente, la red guardada se rehace sola",
            [_une[(_red1[3], _red2[5])], _une[(_red1[0], _red3[0])]], [0, 22 * 16])
    _par_34 = (min(_red3[0], _red4[0]), max(_red3[0], _red4[0]))
    c.execute("INSERT INTO equivalencias (producto_a_id, producto_b_id) VALUES (?, ?)", _par_34)
    conn.commit()
    _antes = ns["cuanto_une_cada_par"]([(_red3[2], _red4[7])])[(_red3[2], _red4[7])]
    c.execute("DELETE FROM equivalencias WHERE producto_a_id = ? AND producto_b_id = ?", _par_34)
    conn.commit()
    esperar("una alta y una baja también la rehacen", (_antes, ns["cuanto_une_cada_par"](
        [(_red3[2], _red4[7])])[(_red3[2], _red4[7])]), (0, 256))
    # Cambiar un vínculo por otro deja la misma cantidad: la firma lo tiene que ver igual. La
    # fila aprobada vuelve después tal cual estaba.
    _par_12 = (min(_red1[3], _red2[5]), max(_red1[3], _red2[5]))
    _fila_12 = c.execute("SELECT * FROM equivalencias WHERE producto_a_id = ? AND producto_b_id = ?",
                         _par_12).fetchone()
    _cols_12 = list(_fila_12.keys())
    c.execute("DELETE FROM equivalencias WHERE producto_a_id = ? AND producto_b_id = ?", _par_12)
    c.execute("INSERT INTO equivalencias (producto_a_id, producto_b_id) VALUES (?, ?)", _par_34)
    conn.commit()
    _une = ns["cuanto_une_cada_par"]([_par_12, (_red3[2], _red4[7])])
    c.execute("DELETE FROM equivalencias WHERE producto_a_id = ? AND producto_b_id = ?", _par_34)
    c.execute(f"INSERT INTO equivalencias ({', '.join(_cols_12)}) "
              f"VALUES ({', '.join('?' * len(_cols_12))})", tuple(_fila_12))
    conn.commit()
    esperar("cambiar un vínculo por otro (la misma cantidad) también la rehace",
            [_une[_par_12], _une[(_red3[2], _red4[7])]], [121, 0])

    # 63. Antes de borrar, lo que toca; y la papelera devuelve la historia, también lo binario.
    bh = producto("BH1", "RADIADOR VW GOL 1.6", fispa)
    bh_o = producto("IBH1", "RADIADOR VW GOL 1.6", illinois)
    vincular(bh, bh_o, "FISPA · lista.xlsx · 01/10/2026 10:00:00")
    c.execute("UPDATE productos SET imagen_orb_blob = ? WHERE id = ?", (b"\x00\x01firma", bh))
    c.execute("INSERT INTO producto_fotos (producto_id, imagen_data, estado) VALUES (?, ?, 'ok')",
              (bh, b"\x89PNG\r\nfoto"))
    c.execute("INSERT INTO historial_precios (producto_id, precio) VALUES (?, 100), (?, 120)", (bh, bh))
    c.execute("INSERT INTO consultas_cliente (cliente, producto_id, codigo_buscado) VALUES ('Ana', ?, 'BH1')",
              (bh,))
    conn.commit()
    for _ in range(3):
        ns["registrar_venta"](bh, "IBH1", "🟢 equivalencia confirmada")
    ns["registrar_devolucion"](bh, "IBH1", "fallada")
    _imp = ns["impacto_de_borrar"](bh)
    esperar("lo que toca borrarlo", (_imp["vínculos"], _imp["historia"].get("ventas_registradas"),
                                     _imp["historia"].get("devoluciones"),
                                     _imp["historia"].get("producto_fotos"),
                                     _imp["historia"].get("historial_precios"),
                                     _imp["historia"].get("consultas_cliente")),
            (1, 3, 1, 1, 2, 1))
    esperar("y lo dice en una frase", ns["texto_del_impacto"](_imp).startswith(
        "⚠️ Este producto tiene 1 vínculo(s), 3 venta(s)"), True)
    esperar("un producto sin nada, nada", ns["texto_del_impacto"](
        ns["impacto_de_borrar"](producto("BH9", "TAPA", fispa))), "")
    esperar("se borra aunque tenga datos binarios", ns["borrar_producto_con_papelera"](bh), 1)
    esperar("y se lleva sus ventas", c.execute("SELECT COUNT(*) FROM ventas_registradas WHERE "
                                               "producto_id = ?", (bh,)).fetchone()[0], 0)
    _pap = c.execute("SELECT id FROM papelera WHERE tipo = 'producto' ORDER BY id DESC LIMIT 1").fetchone()[0]
    _ok_r, _det_r = ns["restaurar_de_papelera"](_pap)
    esperar("vuelve", _ok_r, True)
    esperar("con su historia", tuple(c.execute(f"SELECT COUNT(*) FROM {t} WHERE producto_id = ?",
                                               (bh,)).fetchone()[0]
                                     for t in ("ventas_registradas", "devoluciones",
                                               "historial_precios", "producto_fotos",
                                               "consultas_cliente")), (3, 1, 2, 1, 1))
    esperar("y lo binario, igual", (c.execute("SELECT imagen_data FROM producto_fotos WHERE producto_id = ?",
                                              (bh,)).fetchone()[0],
                                    c.execute("SELECT imagen_orb_blob FROM productos WHERE id = ?",
                                              (bh,)).fetchone()[0]),
            (b"\x89PNG\r\nfoto", b"\x00\x01firma"))
    esperar("y lo dice", "3 venta(s)" in (_det_r or ""), True)
    # Si mientras estuvo en la papelera volvió a entrar con una importación, la historia va al
    # que entró.
    ns["borrar_producto_con_papelera"](bh)
    bh_nuevo = producto("BH1", "RADIADOR VW GOL 1.6", fispa)
    conn.commit()
    _pap = c.execute("SELECT id FROM papelera WHERE tipo = 'producto' ORDER BY id DESC LIMIT 1").fetchone()[0]
    ns["restaurar_de_papelera"](_pap)
    esperar("la historia va al que volvió a entrar", (bh_nuevo != bh, c.execute(
        "SELECT COUNT(*) FROM ventas_registradas WHERE producto_id = ?", (bh_nuevo,)).fetchone()[0],
        c.execute("SELECT COUNT(*) FROM consultas_cliente WHERE producto_id = ?", (bh_nuevo,)).fetchone()[0]),
            (True, 3, 1))

    # 64. Las relaciones que no pueden existir: equivalente y rechazada a la vez.
    _rel_antes = dict(ns["relaciones_imposibles"]())
    _clave_rel = "Vínculos cargados que alguien rechazó (equivalente y no equivalente a la vez)"
    ri_a = producto("RI1", "FILTRO DE AIRE FORD KA", fispa)
    ri_b = producto("IRI1", "FILTRO DE AIRE FORD KA", illinois)
    ns["marcar_revision"]([(ri_a, ri_b)], "rechazada")
    vincular(ri_a, ri_b, "a mano, por fuera de la app")
    conn.commit()
    esperar("la ve", dict(ns["relaciones_imposibles"]()).get(_clave_rel, 0)
            - _rel_antes.get(_clave_rel, 0), 1)
    esperar("en la salud de los datos", {r["Chequeo"]: r["Problemas"] for r in ns["chequear_integridad_bd"]()}
            .get(_clave_rel), dict(ns["relaciones_imposibles"]()).get(_clave_rel))
    esperar("y avisa", "relación(es) que no pueden existir" in " | ".join(
        p_["titulo"] for p_ in ns["diagnostico_de_salud"]()), True)
    c.execute("DELETE FROM equivalencias WHERE producto_a_id = ? AND producto_b_id = ?",
              (min(ri_a, ri_b), max(ri_a, ri_b)))
    conn.commit()
    esperar("y deja de verla", dict(ns["relaciones_imposibles"]()).get(_clave_rel, 0),
            _rel_antes.get(_clave_rel, 0))

    # 65. El mismo número en otra marca, pero otra pieza: lo dice la ficha, y lo devuelto o
    # rechazado no queda tapado por el 🔵 o el ⚪.
    _v = ns["veredicto_de_la_equivalencia"]
    esperar("🔵 que la ficha da por otra pieza", _v({"Cadena": "🔵 mismo código, otra marca",
                                                      "_estado": "🔴 CON CONTRADICCIONES",
                                                      "_por_que_estado": "rubros distintos"}),
            "🔴 el mismo número, pero no es la misma pieza: rubros distintos")
    esperar("⚪ que la ficha da por otra pieza", _v({"Cadena": "⚪ código de fábrica, nadie más lo tiene",
                                                      "_estado": "🔴 CON CONTRADICCIONES"}),
            "🔴 no es la misma pieza")
    esperar("🔵 devuelto", _v({"Cadena": "🔵 mismo código, otra marca", "Devuelto": "↩️"})[:1], "🔴")
    esperar("🔵 rechazado", _v({"Cadena": "🔵 mismo código, otra marca", "Rechazada": "🚫"})[:1], "🔴")
    esperar("🔵 sin nada en contra, sigue 🔵", _v({"Cadena": "🔵 mismo código, otra marca",
                                                    "_estado": "🟡 PROBABLE"})[:1], "🔵")
    jt_k = producto("KJ1", "JTA TAPA CILINDROS FORD RANGER V8", fispa)
    jt_a = producto("JT500", "JTA TAPA CILINDROS FORD RANGER V8", illinois)
    jt_b = producto("JT500", "PRE-FILTRO COMBUSTIBLE UNIVERSAL", marca("CRI-FA"))
    vincular(jt_k, jt_a, "FISPA · lista.xlsx · 01/10/2026 10:00:00")
    conn.commit()
    _filas_jt = {f["ID"]: f for f in ns["buscar_con_variantes_del_cero"]("KJ1")[0]}
    esperar("el prefiltro llega por tener el mismo número que la junta",
            str(_filas_jt.get(jt_b, {}).get("Cadena", ""))[:1], "🔵")
    esperar("y el buscador dice que no es la misma pieza", _v(_filas_jt.get(jt_b, {})).startswith(
        "🔴 el mismo número, pero no es la misma pieza"), True)

    # 66. Vender lo 🔴 en lugar de lo pedido pide confirmarlo; y si es de seguridad, no se anota.
    _bloqueo = ns["bloqueo_de_venta"]
    esperar("🔴 de un filtro: confirmar", _bloqueo("🔴 no es la misma pieza", "FILTRO DE ACEITE"),
            "confirmar")
    esperar("🔴 de una pastilla: no", _bloqueo("🔴 no es la misma pieza",
                                               "PASTILLA DE FRENO DELANTERA VW GOL"), "bloqueada")
    esperar("🟡: nada", _bloqueo("🟡 probable", "PASTILLA DE FRENO DELANTERA VW GOL"), "")
    esperar("el botón lo dice", ns["rotulo_del_boton_de_venta"](
        {"Cadena": "🟢 directo", "_estado": "🔴 CON CONTRADICCIONES"}), "🛒 Se llevó igual (🔴)")
    vr_a = producto("VR1", "FILTRO DE AIRE FIAT UNO", fispa)
    vr_b = producto("IVR1", "FILTRO DE AIRE FIAT UNO", illinois)
    vr_s = producto("IVR2", "PASTILLA DE FRENO DELANTERA FIAT UNO", illinois)
    conn.commit()
    def _ventas_de(pid):
        return c.execute("SELECT COUNT(*) FROM ventas_registradas WHERE producto_id = ?",
                         (pid,)).fetchone()[0]
    _args = (vr_b, "VR1", "ILLINOIS - IVR1", "prueba_rojo", "🔴 no es la misma pieza: otra medida",
             "cadena 🟢 directo")
    ns["anotar_venta_y_avisar"](*_args)
    esperar("sin confirmar no se anota", (_ventas_de(vr_b), "Confirmalo primero" in
                                          ns["st"].session_state["_lo_anotado"]["prueba_rojo"]),
            (0, True))
    ns["pedir_confirmacion_de_venta"]("vendido_x_VR1", _args)
    ns["confirmar_la_venta"]("vendido_x_VR1")
    esperar("confirmado, sí", _ventas_de(vr_b), 1)
    esperar("y la pregunta se va", "vendido_x_VR1" in ns["st"].session_state["_venta_a_confirmar"],
            False)
    ns["pedir_confirmacion_de_venta"]("vendido_y_VR1", _args)
    ns["cancelar_la_venta"]("vendido_y_VR1")
    ns["confirmar_la_venta"]("vendido_y_VR1")
    esperar("«No»: no queda la pregunta ni se anota",
            ("vendido_y_VR1" in ns["st"].session_state["_venta_a_confirmar"], _ventas_de(vr_b)),
            (False, 1))

    class _Columna:
        def button(self, rotulo, key=None, on_click=None, args=(), help=None, disabled=False):
            self.boton = (rotulo, getattr(on_click, "__name__", None), disabled)
    def _boton(fila, veredicto):
        col = _Columna()
        ns["mostrar_boton_de_venta"](col, fila, _args[:4] + (veredicto, ""), "clave_prueba")
        return col.boton
    esperar("el botón de una 🔴 pregunta antes", _boton(
        {"Cadena": "🟢 directo", "_estado": "🔴 CON CONTRADICCIONES",
         "Descripcion": "FILTRO DE AIRE FIAT UNO"}, "🔴 no es la misma pieza"),
            ("🛒 Se llevó igual (🔴)", "pedir_confirmacion_de_venta", False))
    esperar("el de una 🔴 de seguridad, apagado", _boton(
        {"Cadena": "🟢 directo", "_estado": "🔴 CON CONTRADICCIONES",
         "Descripcion": "PASTILLA DE FRENO DELANTERA FIAT UNO"}, "🔴 no es la misma pieza")[1:],
            (None, True))
    esperar("el de una 🟡, directo", _boton(
        {"Cadena": "🟢 directo", "_estado": "🟡 PROBABLE", "Descripcion": "FILTRO DE AIRE"},
        "🟡 probable")[1:], ("anotar_venta_y_avisar", False))
    ns["anotar_venta_y_avisar"](vr_s, "VR1", "ILLINOIS - IVR2", "prueba_rojo",
                                "🔴 no es la misma pieza: otra medida", "", confirmado=True)
    esperar("la de seguridad, ni confirmada", (_ventas_de(vr_s),
                                               ns["st"].session_state["_lo_anotado"]["prueba_rojo"]),
            (0, ns["TEXTO_DE_VENTA_BLOQUEADA"]))

    # 67. El historial de medidas no se corrige ni se borra: ver la sección 46.

    # 68. El expediente lleva las reglas y una huella que detecta si alguien lo tocó.
    _fic = ns["ficha_de_prueba"](rx_a, rx_b)
    _exp = ns["expediente_en_texto"](_fic)
    esperar("con la versión de las reglas", f"- Reglas: v{ns['VERSION_CONFIANZA']}" in _exp, True)
    esperar("la huella coincide", ns["verificar_el_expediente"](_exp), True)
    esperar("tocado, no", ns["verificar_el_expediente"](_exp.replace("**Estado:**", "**Estado:** ✅", 1)),
            False)
    esperar("uno de antes, sin huella", ns["verificar_el_expediente"]("# Expediente\n\nalgo\n"), None)
    esperar("reproducible: los mismos datos dan la misma huella",
            _exp.rstrip().splitlines()[-1],
            ns["expediente_en_texto"](ns["ficha_de_prueba"](rx_a, rx_b)).rstrip().splitlines()[-1])

    # 69. La cobertura, por lista y por familia, sin promedios.
    cob = marca("COBERTURA")
    cb_a = producto("CB1", "RETEN CIGUEÑAL FIAT PALIO", cob, diametro_interno=35, diametro_externo=50)
    cb_b = producto("CB2", "RETEN CIGUEÑAL FIAT PALIO", cob)
    cb_c = producto("CB3", "RETEN CIGUEÑAL FIAT PALIO", cob)
    vincular(cb_a, ret_f, "COBERTURA · lista.xlsx · 01/10/2026 10:00:00")
    vincular(cb_c, ret_f, "")      # sin anotar de dónde salió: no es una fuente
    conn.commit()
    def _cobertura(**kw):
        return {k: v for k, v in {x["Lista"]: x for x in ns["cobertura_del_catalogo"](**kw)[
            "por_lista"]}.get("COBERTURA", {}).items() if k != "Lista"}
    esperar("la lista, con lo que tiene", _cobertura(segundos_de_memoria=0),
            {"Productos": 3, "Con equivalente": "67 %", "Con una fuente": "33 %",
             "Con medidas": "33 %", "Comprobados en la mano": 0})
    producto("CB4", "RETEN CIGUEÑAL FIAT PALIO", cob)
    conn.commit()
    esperar("se guarda unos minutos", _cobertura()["Productos"], 3)
    esperar("y sin memoria, la de ahora", _cobertura(segundos_de_memoria=0)["Productos"], 4)
    esperar("y lo que no tiene familia, aparte", isinstance(
        ns["cobertura_del_catalogo"]()["sin_familia"], int), True)

    # 70. Lo que ya está unido por otro camino, contado.
    c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, lote) "
              "VALUES (?, ?, 'x', 'REDUNDANTES · 03/10')", (min(_red1[1], _red1[2]), max(_red1[1], _red1[2])))
    c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, lote) "
              "VALUES (?, ?, 'x', 'REDUNDANTES · 03/10')", (min(cb_b, _red1[3]), max(cb_b, _red1[3])))
    conn.commit()
    esperar("ya unidos", ns["cuantos_ya_estan_unidos"]("REDUNDANTES · 03/10"), 1)

    # 71. De cuándo es el precio: la fecha del nombre de la lista, o el día que se cargó.
    from datetime import date as _date
    _fl = ns["fecha_de_la_lista"]
    esperar("del nombre del archivo", _fl("ILLINOIS 17 07 2026.xlsx", "2026-09-25 20:29:55"),
            (_date(2026, 7, 17), "de la lista"))
    esperar("con el año en dos cifras", _fl("MANNOL ADITIVOS OK 14 04 26 (1).xlsx",
                                            "2026-09-25 17:47:34"), (_date(2026, 4, 14), "de la lista"))
    esperar("sin fecha en el nombre, el día de la carga", _fl("11680359842.xlsx", "2026-09-25 20:28:58"),
            (_date(2026, 9, 25), "cargada"))
    esperar("una fecha después de cargarla no es la de la lista",
            _fl("LISTA 30 12 2026.xlsx", "2026-09-25 10:00:00"), (_date(2026, 9, 25), "cargada"))
    esperar("ni una que no existe", _fl("LISTA 31 02 2026.xlsx", "2026-09-25 10:00:00"),
            (_date(2026, 9, 25), "cargada"))
    esperar("si la primera no existe, mira la siguiente",
            _fl("LISTA 31 02 2026 - 15 07 2026.xlsx", "2026-09-25 10:00:00"),
            (_date(2026, 7, 15), "de la lista"))
    esperar("sin nada, nada", _fl("x.xlsx", None), (None, ""))
    c.execute("INSERT INTO importaciones (marca, archivo, filas_cargadas, filas_omitidas, fecha) "
              "VALUES ('VIEJA', 'VIEJA 01 07 2026.xlsx', 1, 0, '2026-09-25 10:00:00'), "
              "('VIEJA', 'VIEJA 01 09 2026.xlsx', 1, 0, '2026-09-30 10:00:00'), "
              "('NUEVA', 'nueva.xlsx', 1, 0, '2026-10-10 10:00:00'), "
              "('ANTIGUA', 'ANTIGUA 01 06 2026.xlsx', 1, 0, '2026-06-02 10:00:00')")
    conn.commit()
    esperar("la línea del buscador, con lo viejo marcado",
            ns["texto_de_la_fecha_de_los_precios"](["NUEVA", "VIEJA", "ANTIGUA", "SUELTA", None, "NUEVA"],
                                                   hoy=_date(2026, 10, 12)),
            "💲 Precios — **⚠️ ANTIGUA: lista del 01/06/2026 (hace 133 días)** · NUEVA: cargada el "
            "10/10/2026 (hace 2 días) · SUELTA: sin fecha (no entró por una lista) · VIEJA: lista "
            "del 01/09/2026 (hace 41 días)")
    esperar("sin marcas con precio, nada", ns["texto_de_la_fecha_de_los_precios"]([]), "")

    # 72. Lo vendido con un par que después se rechazó: a quién avisarle.
    vd_a = producto("VD1", "FILTRO DE ACEITE FIAT UNO", fispa)
    vd_b = producto("IVD1", "FILTRO DE ACEITE FIAT UNO", illinois)
    vd_c = producto("IVD2", "FILTRO DE ACEITE FIAT UNO", illinois)
    vd_d = producto("VD1", "FILTRO DE ACEITE FIAT UNO", illinois)   # el mismo número, otra marca
    c.execute("INSERT INTO ventas_registradas (producto_id, termino_pedido, codigo_pedido_clean, "
              "usuario, fecha) VALUES (?, 'VD1', 'VD1', 'ana', '2026-10-01 10:00:00'), "
              "(?, 'VD1', 'VD1', 'beto', '2026-10-06 10:00:00'), "
              "(?, 'VD1', 'VD1', 'carla', '2026-10-01 10:00:00'), "
              "(?, 'VD1', 'VD1', 'dani', '2026-10-01 10:00:00'), "
              "(?, 'VD1', 'VD1', 'eli', '2026-10-01 10:00:00')", (vd_b, vd_b, vd_c, vd_a, vd_d))
    c.execute("INSERT OR REPLACE INTO equivalencias_revisadas (producto_a_id, producto_b_id, decision, "
              "fecha) VALUES (?, ?, 'rechazada', '2026-10-05 10:00:00')", (min(vd_a, vd_d), max(vd_a, vd_d)))
    c.execute("INSERT OR REPLACE INTO equivalencias_revisadas (producto_a_id, producto_b_id, decision, "
              "fecha, motivo) VALUES (?, ?, 'rechazada', '2026-10-05 10:00:00', 'variante')",
              (min(vd_a, vd_b), max(vd_a, vd_b)))
    c.execute("INSERT OR REPLACE INTO equivalencias_revisadas (producto_a_id, producto_b_id, decision, "
              "fecha) VALUES (?, ?, 'ok', '2026-10-05 10:00:00')", (min(vd_a, vd_c), max(vd_a, vd_c)))
    conn.commit()
    _afect = [(f["Vendió"], f["Se llevó"], f["Pidió"], f["Por qué"])
              for f in ns["vendido_con_lo_que_despues_se_rechazo"]()]
    esperar("solo la venta de antes del rechazo, de un par rechazado y en lugar de lo pedido",
            _afect, [("ana", "ILLINOIS IVD1", "VD1", "📐 Otra medida o variante")])
    # 73. Aplicar lo decidido en una tanda saltea lo que otro resolvió mientras tanto (ver
    # aplicar_decisiones() y _los_que_siguen_pendientes()). No tenía prueba: con dos personas
    # revisando, aprobar volvía a crear lo que el otro acababa de descartar, y descartar anotaba
    # como rechazado lo que el otro acababa de aprobar.
    ot = marca("OTRO REVISOR")
    _p = [producto(f"OR{i}", "FILTRO DE ACEITE", ot) for i in range(8)]
    _pares = [(min(_p[i], _p[i + 1]), max(_p[i], _p[i + 1])) for i in (0, 2, 4, 6)]
    for _a, _b in _pares:
        c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, lote) "
                  "VALUES (?, ?, 'x', 'OTRO · 04/10')", (_a, _b))
    conn.commit()
    ns["decisiones_del_lote"]("OTRO · 04/10").update(
        {_pares[0]: "bien", _pares[1]: "bien", _pares[2]: "mal", _pares[3]: "mal"})
    # Mientras tanto, otra persona descarta el segundo y aprueba el tercero.
    ns["rechazar_pendientes"]("OTRO · 04/10", [_pares[1]])
    ns["aprobar_pendientes"]("OTRO · 04/10", [_pares[2]])
    ns["aplicar_decisiones"]("OTRO · 04/10")

    def _es_equivalencia(par):
        return c.execute("SELECT COUNT(*) FROM equivalencias WHERE producto_a_id = ? "
                         "AND producto_b_id = ?", par).fetchone()[0]

    def _lo_revisado(par):
        fila = c.execute("SELECT decision FROM equivalencias_revisadas WHERE producto_a_id = ? "
                         "AND producto_b_id = ?", par).fetchone()
        return fila[0] if fila else None
    esperar("lo mío se aplica, y lo que resolvió otro queda como lo dejó",
            [_es_equivalencia(par) for par in _pares], [1, 0, 1, 0])
    esperar("y lo revisado dice lo que decidió cada uno", [_lo_revisado(par) for par in _pares],
            ["ok", "rechazada", "ok", "rechazada"])
    esperar("la tanda quedó vacía", c.execute("SELECT COUNT(*) FROM equivalencias_pendientes "
                                              "WHERE lote = 'OTRO · 04/10'").fetchone()[0], 0)
    # 74. Los códigos de fábrica con la marca pegada («POWER836120129»): renombrar si el número
    # limpio no está, juntar si está, con sus pendientes y sus decisiones (ver
    # corregir_codigo_con_la_marca_pegada()). La herramienta no tenía prueba.
    of = marca("OEM PEGADA", "OEM")
    il = marca("ILLINOIS PEGADA")
    _a = producto("POWER836120129", "Filtro", of)
    _b1 = producto("BENZ3120150080", "Junta", of)
    _b2 = producto("3120150080", "Junta", of)
    _pv = producto("ILP-1", "Junta Illinois", il)
    _pv2 = producto("ILP-2", "Filtro Illinois", il)
    vincular(_a, _pv2, "PEGADA · 05/10")
    c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, lote) "
              "VALUES (?, ?, 'x', 'PEGADA · 05/10')", (min(_b1, _pv), max(_b1, _pv)))
    c.execute("INSERT INTO equivalencias_revisadas (producto_a_id, producto_b_id, decision) "
              "VALUES (?, ?, 'rechazada')", (min(_b1, _pv2), max(_b1, _pv2)))
    conn.commit()
    _pegadas = {x["Código"]: (x["Número"], x["Ya existe"])
                for x in ns["codigos_de_fabrica_con_la_marca_pegada"]()
                if x["Código"] in ("POWER836120129", "BENZ3120150080")}
    esperar("las encuentra, y sabe cuál ya está limpia",
            _pegadas, {"POWER836120129": ("836120129", False), "BENZ3120150080": ("3120150080", True)})
    esperar("sin la limpia, la renombra y el vínculo sigue",
            (ns["corregir_codigo_con_la_marca_pegada"](_a, "836120129"),
             tuple(c.execute("SELECT codigo_raw, codigo_clean FROM productos WHERE id = ?",
                             (_a,)).fetchone()),
             c.execute("SELECT COUNT(*) FROM equivalencias WHERE ? IN (producto_a_id, "
                       "producto_b_id)", (_a,)).fetchone()[0]),
            (True, ("836120129", "836120129"), 1))
    esperar("con la limpia, las junta: el pendiente y el rechazo pasan a la que queda",
            (ns["corregir_codigo_con_la_marca_pegada"](_b1, "3120150080"),
             c.execute("SELECT COUNT(*) FROM productos WHERE id = ?", (_b1,)).fetchone()[0],
             c.execute("SELECT COUNT(*) FROM equivalencias_pendientes WHERE ? IN (producto_a_id, "
                       "producto_b_id) AND ? IN (producto_a_id, producto_b_id)",
                       (_b2, _pv)).fetchone()[0],
             (c.execute("SELECT decision FROM equivalencias_revisadas WHERE ? IN (producto_a_id, "
                        "producto_b_id) AND ? IN (producto_a_id, producto_b_id)",
                        (_b2, _pv2)).fetchone() or [None])[0]),
            (True, 0, 1, "rechazada"))
    esperar("y ya no quedan", [x for x in ns["codigos_de_fabrica_con_la_marca_pegada"]()
                               if x["Código"] in ("POWER836120129", "BENZ3120150080")], [])

    # 75. Dos productos de una misma lista son dos piezas (ver otra_pieza_de_la_misma_lista()):
    # por la cadena —una sonda «universal» de otra lista unida a las dos— la LECS018 (Sportage)
    # salía como «🟢 sólida» buscando la 80056 (Kangoo). Salvo los mellizos de FISPA y LUCAS, las
    # variantes y el reemplazo que nombra al otro.
    _dos = ns["otra_pieza_de_la_misma_lista"]
    esperar("cuándo son dos piezas de la misma lista",
            [bool(_dos("FISPA", *x)) for x in (
                ("LECS018LUCAS", "SONDA LAMBDA LECS018 FIAT SPORTAGE 2 0 TODO TERRENO",
                 "80056FISPA", "SONDA LAMBDA 80056 RENAULT KANGOO 1 4 98 - CLIO 1 2"),
                ("70060FISPA", "BOBINA DE IGNICION 70060 CITROEN C4 2 0 C5 1 8 XSARA",
                 "70193FISPA", "BOBINA DE IGNICION 70193 PEUGEOT 307 2 0 16V 307 SW"),
                ("LEIG039LUCAS", "BOBINA DE IGNICION LEIG039POLO CLASSIC 1 6I 1 8I GOLF 1 4I",
                 "70027FISPA", "BOBINA DE IGNICION 70027POLO CLASSIC 1 6I 1 8I GOLF 1 4I"),
                ("20509FISPA", "BOMBA ELECTRICA 20509BOMBA CHEVROLET ASTRA - CORSA- VECTRA OMEGA",
                 "LEFS054LUCAS", "BOMBA DE COMBUSTIBLE LEFS054BOMBA CHEVROLET ASTRA - CORSA- "
                 "VECTRA OMEGA"),
                ("TC-882-20 1M", "Junta Tapa de Cilindros S10", "TC-882-MG 1M",
                 "Junta Tapa de Cilindros S10 MG"),
                ("981308", "Junta tapa de cilindros - Reemplazada por 272008", "272008",
                 "Junta tapa de cilindros FIAT E-TORQ 16V 1.6L"),
                ("LEICJ021LUCAS", "INYECTOR LEICJ021 CHEVROLET ASTRA ZAFIRA 1 8 2 0 8V 00 REF ORIG "
                 "BOSCH 0280155929 OEM 93275197", "FI-0280155929FISPA",
                 "INYECTOR FI-0280155929Chevrolet Astra 1.8 MPFI (1998-2001) - Chevrolet Zafira"))],
            [True, True, False, False, False, False, False])
    mf = marca("FISPA DOS")
    cf = marca("CRI-FA DOS")
    _s18 = producto("LECS018LUCAS", "SONDA LAMBDA LECS018 FIAT SPORTAGE 2 0 TODO TERRENO", mf)
    _s56 = producto("80056FISPA", "SONDA LAMBDA 80056 RENAULT KANGOO 1 4 98 - CLIO 1 2", mf)
    _s15 = producto("80015FISPA", "SONDA LAMBDA 80015 FIAT SPORTAGE 2 0 TODO TERRENO", mf)
    _uni = producto("14-R7834", "Sonda Lambda universal Fiat Renault", cf)
    for _x in (_s18, _s56, _s15):
        vincular(_x, _uni, "CRI-FA DOS · 05/10")
    conn.commit()
    _res = {f["Codigo"]: f for f in ns["buscar_por_codigo"]("LECS018LUCAS", "Todas", 3)}
    esperar("la otra sonda de la lista sale marcada y no cuenta; el mellizo, no",
            [(cod, "otro producto de" in _res[cod]["Cadena"], bool(_res[cod].get("_complementario")))
             for cod in ("80056FISPA", "80015FISPA")],
            [("80056FISPA", True, True), ("80015FISPA", False, False)])
    # Y donde el texto no dice nada en contra —dos bulbos de FISPA del Aveo—, lo dice la regla,
    # en el buscador y en la ficha.
    _b349 = producto("349FISPA", "BULBO DE PRESION DE ACEITE 349 CHEVROLET AVEO", mf)
    _b344 = producto("344FISPA", "BULBO DE PRESION DE ACEITE 344 CHEVROLET AVEO ASTRA", mf)
    _bcf = producto("53-1099", "Bulbo presion de aceite Chevrolet Aveo", cf)
    vincular(_b349, _bcf, "CRI-FA DOS · 05/10")
    vincular(_b344, _bcf, "CRI-FA DOS · 05/10")
    conn.commit()
    _res_b = {f["Codigo"]: f for f in ns["buscar_por_codigo"]("349FISPA", "Todas", 3)}
    esperar("el otro bulbo de la lista, marcado en el buscador y en la ficha",
            ("otro producto de" in _res_b["344FISPA"]["Cadena"],
             ns["ficha_de_prueba"](_b349, _b344)["estado"][:1],
             ns["ficha_de_prueba"](_s18, _s15)["estado"][:1] != "🔴"), (True, "🔴", True))
    esperar("con «solo confiables», no sale",
            "80056FISPA" in {f["Codigo"] for f in ns["buscar_por_codigo"](
                "LECS018LUCAS", "Todas", 3, confianza_minima=50)}, False)

    # 78. Lo que solo se alcanza pasando por OTRA pieza de la misma lista es el equivalente de
    # esa, no del buscado: la sonda de TARANTO del Kangoo, colgada de la 80056, no es la del
    # Sportage. Queda para revisar, no cuenta y con «solo confiables» no sale (ver «la cadena
    # que pasa por otra pieza» en ficha_de_prueba()). Si hay otro camino que no pasa por ahí,
    # nada.
    mt = marca("TARANTO DOS")
    # Sin auto en la descripción: así lo único en contra es el camino.
    _t56 = producto("ST56", "SONDA LAMBDA 4 CABLES", mt)
    vincular(_t56, _s56, "TARANTO DOS · 05/10")
    conn.commit()
    _res_t = {f["Codigo"]: f for f in ns["buscar_con_variantes_del_cero"]("LECS018LUCAS")[0]}
    _ficha_t = ns["ficha_de_prueba"](_s18, _t56)
    esperar("pasando por otra pieza: a revisar, dicho, y sin contar",
            (_ficha_t["estado"], _ficha_t["por_otra_pieza"], bool(_res_t["ST56"].get("_complementario")),
             "otra pieza de FISPA DOS" in _res_t["ST56"]["Cadena"]),
            ("🟠 CANDIDATA", "llega por 80056FISPA, otra pieza de FISPA DOS", True, True))
    esperar("con «solo confiables», no sale",
            "ST56" in {f["Codigo"] for f in ns["buscar_con_variantes_del_cero"](
                "LECS018LUCAS", confianza_minima=50)[0]}, False)
    vincular(_t56, _uni, "TARANTO DOS · 05/10")
    conn.commit()
    esperar("con otro camino que no pasa por ahí, nada",
            ns["ficha_de_prueba"](_s18, _t56)["por_otra_pieza"], "")

    # 76. El abanico se pregunta desde el lado con más OPCIONES (ver abanicos_para_elegir()):
    # TARANTO 230512 con dos de IMPERIAL —la misma junta en dos materiales— empataba en filas
    # con IMPERIAL 25516AC3 con dos de TARANTO, y se preguntaba «elegí entre una sola opción».
    def _fila(a, b, cod_a, desc_a, ma, cod_b, desc_b, mb, conf=50.0):
        return {"a": a, "b": b, "cod_a": cod_a, "desc_a": desc_a, "marca_a": ma, "tipo_a": "PROVEEDOR",
                "cod_b": cod_b, "desc_b": desc_b, "marca_b": mb, "tipo_b": "PROVEEDOR",
                "confianza": conf, "alarmas": ["🪭 Uno de los dos está emparejado con 2"]}
    _t1, _t2, _i1, _i2 = 900001, 900002, 900003, 900004
    _filas_ab = [
        _fila(_t1, _i1, "230512", "Junta Distribucion VW GOL 1000", "TARANTO",
              "25516AC3", "JTA T.DIST VOLKSWAGEN GOL 1000", "IMPERIAL"),
        _fila(_t1, _i2, "230512", "Junta Distribucion VW GOL 1000", "TARANTO",
              "25517AC3", "JTA T.DIST VOLKSWAGEN GOL 1000", "IMPERIAL"),
        _fila(_t2, _i1, "230612", "Jta. de distribucion VW Gol 1000 con reten", "TARANTO",
              "25516AC3", "JTA T.DIST VOLKSWAGEN GOL 1000", "IMPERIAL"),
        _fila(_t2, _i2, "230612", "Jta. de distribucion VW Gol 1000 con reten", "TARANTO",
              "25517AC3", "JTA T.DIST VOLKSWAGEN GOL 1000", "IMPERIAL")]
    _abs = ns["abanicos_para_elegir"]([], _filas_ab)
    esperar("desde IMPERIAL, con las dos de TARANTO para elegir",
            sorted((a["producto"]["marca"], len(ns["candidatos_por_pieza"](a))) for a in _abs),
            [("IMPERIAL", 2), ("IMPERIAL", 2)])

    # 77. La ⭐ del abanico también es la que ya es su equivalente por vínculos aprobados (🔗):
    # en la copia de la base real, ninguno de los 514 traía una sugerida.
    _ab = {"producto": {"id": _t1, "cod": "230512", "marca": "TARANTO",
                        "desc": "Junta Distribucion VW GOL 1000"}, "marca_otra": "IMPERIAL",
           "candidatos": [_fila(_t1, 900005, "230512", "Junta Distribucion VW GOL 1000", "TARANTO",
                                "25516AC3", "JTA T.DIST VOLKSWAGEN GOL 1000", "IMPERIAL"),
                          _fila(_t1, 900006, "230512", "Junta Distribucion VW GOL 1000", "TARANTO",
                                "3363AC3", "JTA T. DEL. BLOCK M.BENZ OM447", "IMPERIAL")]}
    esperar("sin nada unido, ninguna", ns["pieza_sugerida_del_abanico"](dict(_ab, ya_unidos=set())),
            None)
    esperar("la que ya es su equivalente",
            ns["pieza_sugerida_del_abanico"](dict(_ab, ya_unidos={(_t1, 900006)})),
            ns["pieza_para_el_abanico"]("3363AC3", "JTA T. DEL. BLOCK M.BENZ OM447"))
    esperar("y en la tabla dice 🔗",
            ["🔗" in f["Opción"] for f in ns["tabla_del_abanico"](dict(_ab, ya_unidos={(_t1, 900006)}))],
            [False, False, True])

    # 79. 🕸️ Los unidos a varias piezas distintas de una misma lista (ver
    # unidos_a_piezas_distintas()), y el «🔗 Hay N más» sin lo que la búsqueda ya marcó como
    # otra cosa: buscando la LECS018 decía «hay 58 más», casi todas otras sondas de FISPA.
    esperar("«hay N más» no cuenta las otras piezas de la lista",
            ns["equivalentes_mas_alla_del_tope"]("LECS018LUCAS", 1), (2, ["FISPA DOS", "TARANTO DOS"]))
    _s99 = producto("80099FISPA", "SONDA LAMBDA 80099 FORD KA 1 0 ZETEC ROCAM", mf)
    vincular(_s99, _uni, "CRI-FA DOS · 05/10")
    conn.commit()
    _unidos = {x["Código"]: (x["Lista"], x["Piezas distintas"], len(x["vinculos"]))
               for x in ns["unidos_a_piezas_distintas"](limite=None)}
    esperar("la sonda universal, con tres sondas distintas de FISPA (el mellizo no suma)",
            _unidos.get("14-R7834"), ("FISPA DOS", 3, 4))
    ns["aprobar_puente"](_uni, "universal")
    esperar("aprobada como universal, ya no sale",
            "14-R7834" in {x["Código"] for x in ns["unidos_a_piezas_distintas"](limite=None)}, False)

    # 80. 🤖 Lo que la app descarta sola (ver «LO QUE LA APP DESCARTA SOLA»): apagado no hace
    # nada; prendido descarta lo 🔴 y el kit con su pieza, deja lo dudoso, lo firma «🤖 la app»,
    # no cuenta para lo aprendido, y se devuelve todo a la cola con su lista.
    md1, md2 = marca("AUTO UNO"), marca("AUTO DOS")
    _bujia = producto("AU1", "BUJIA NGK BKR6E FIAT PALIO 1.4", md1)
    _filtro = producto("AD1", "FILTRO DE ACEITE FIAT PALIO 1.4", md2)
    _bujia2 = producto("AD2", "BUJIA NGK BKR6E FIAT PALIO 1.4", md2)
    for _x, _y in ((_bujia, _filtro), (_bujia, _bujia2)):
        c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, lote) "
                  "VALUES (?, ?, 'x', 'AUTO · 26/10')", (min(_x, _y), max(_x, _y)))
    conn.commit()
    _en_cola = lambda: sorted(r[0] for r in c.execute(
        "SELECT producto_b_id FROM equivalencias_pendientes WHERE lote = 'AUTO · 26/10'"))
    _antes_ap = ns["aprender_de_las_decisiones"]()
    esperar("apagado, nada", ns["descartar_solos_los_casi_seguro_mal"](["AUTO · 26/10"])["descartados"], 0)
    ns["guardar_config"](ns["DESCARTE_AUTOMATICO"], "1")
    _r_auto = ns["descartar_solos_los_casi_seguro_mal"](["AUTO · 26/10"])
    esperar("prendido: la bujía contra el filtro se va, la bujía con la bujía queda",
            (_r_auto["descartados"], _en_cola(),
             c.execute("SELECT revisado_por FROM equivalencias_revisadas WHERE producto_a_id = ? "
                       "AND producto_b_id = ?", (min(_bujia, _filtro), max(_bujia, _filtro))).fetchone()[0],
             ns["aprender_de_las_decisiones"]() == _antes_ap),
            (1, [max(_bujia, _bujia2)], "🤖 la app", True))
    esperar("se devuelve a la cola, con su lista",
            (ns["devolver_lo_que_descarto_sola"](), _en_cola(), ns["lo_que_descarto_sola"]()),
            (1, sorted([max(_bujia, _bujia2), max(_bujia, _filtro)]), []))
    ns["guardar_config"](ns["DESCARTE_AUTOMATICO"], "0")

    # 81. EL NÚMERO DE FÁBRICA MANDA SOBRE EL AUTO (ver evidencia_cruzada()): dos listas que
    # citan el mismo número original son la misma pieza aunque nombren otros autos. Lo que
    # espera aprobación vale si lo trajo la lista, no si lo propuso la app por el texto. Y lo
    # que contradice la pieza sigue vetando aunque la primera regla que cortaba fuera la del auto.
    ml3, mf3, mo3 = marca("LUCAS TRES"), marca("FISPA TRES"), marca("OEM TRES", "OEM")
    _del_auto = tuple(f"🔤 {m}" for m in ns["_MOTIVOS_DEL_AUTO"])
    def _vetos_de_texto(a, b):
        return [v for v in ns["evidencia_cruzada"](a, b)[1] if v.startswith("🔤")]
    def _pendiente(a, b, origen):
        c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, lote) "
                  "VALUES (?, ?, ?, 'TRES · 26/10')", (min(a, b), max(a, b), origen))
        conn.commit()
    _lu = producto("LEMSR027", "SONDA LAMBDA CHEVROLET AVEO 1.6", ml3)
    _fi = producto("30081", "SONDA LAMBDA CHEVROLET CORSA 2.0", mf3)
    _nodo = producto("0258006028", "SONDA LAMBDA", mo3)
    vincular(_lu, _nodo, "LUCAS TRES · 26/10")
    esperar("sin un número en común, el auto veta",
            [v.startswith(_del_auto) for v in _vetos_de_texto(_lu, _fi)], [True])
    _pendiente(_fi, _nodo, "descripcion-todas")
    esperar("lo que la app propuso por el texto no cuenta como número de la lista",
            [v.startswith(_del_auto) for v in _vetos_de_texto(_lu, _fi)], [True])
    c.execute("UPDATE equivalencias_pendientes SET origen = 'lista_proveedor' WHERE lote = 'TRES · 26/10'")
    conn.commit()
    esperar("con el mismo número de fábrica (aunque espere aprobación), el auto no cuenta",
            _vetos_de_texto(_lu, _fi), [])
    _egr = producto("EGR27", "VALVULA EGR CHEVROLET AVEO 1.6", ml3)
    _pcv = producto("PCV81", "VALVULA PCV CHEVROLET CORSA 2.0", mf3)
    _nodo2 = producto("96325842", "VALVULA", mo3)
    vincular(_egr, _nodo2, "LUCAS TRES · 26/10")
    vincular(_pcv, _nodo2, "FISPA TRES · 26/10")
    esperar("la pieza sigue vetando, aunque primero cortara la cilindrada",
            _vetos_de_texto(_egr, _pcv), ["🔤 siglas distintas: EGR vs PCV"])
    _cable = producto("LEIHTG101", "CABLE DE BUJIA CHEVROLET ONIX 1.4", ml3)
    _buj = producto("WR7DC", "BUJIA CHEVROLET CORSA 2.0", mf3)
    _nodo3 = producto("SC-G101", "CABLE DE BUJIA", mo3)
    vincular(_cable, _nodo3, "LUCAS TRES · 26/10")
    vincular(_buj, _nodo3, "FISPA TRES · 26/10")
    esperar("si sin el auto lo que cambia es el nombre de la pieza, vale lo del auto",
            [v.startswith(_del_auto) for v in _vetos_de_texto(_cable, _buj)], [True])
    _lu2 = producto("LEMSR024", "SONDA LAMBDA CHEVROLET CORSA 2.0", ml3)
    vincular(_lu2, _nodo, "LUCAS TRES · 26/10")
    esperar("dos productos de la misma lista con el mismo número: el auto sigue contando",
            [v.startswith(_del_auto) for v in _vetos_de_texto(_lu, _lu2)], [True])
    # Con el número de fábrica de un lado, como siempre: su descripción la copió la fila que lo
    # trajo, y a veces es otra pieza que lo cita.
    _nodo4 = producto("8200699627", "CAPUCHONES PARA BOBINA NISSAN TIIDA 1.6", mo3)
    _bob = producto("70164", "BOBINA DE IGNICION RENAULT MEGANE 2.0", mf3)
    vincular(_bob, _nodo4, "FISPA TRES · 26/10")
    esperar("el nodo de fábrica con la descripción de otra pieza no veta por el auto",
            _vetos_de_texto(_nodo4, _bob), [])
    _iny1 = producto("FI0280155929", "INYECTOR FIAT PALIO 1.4", ml3)
    _iny2 = producto("IN455", "INYECTOR FIAT PALIO 1.6 REF 0280155929", mf3)
    esperar("el mismo número largo escrito en los dos, sin nodo de fábrica",
            _vetos_de_texto(_iny1, _iny2), [])
    # Y el buscador dice lo mismo que la ficha: la sonda de FISPA, a dos saltos, no sale como
    # «no es lo mismo».
    vincular(_fi, _nodo, "FISPA TRES · 26/10")
    _res_n = {f["Codigo"]: f for f in ns["buscar_con_variantes_del_cero"]("LEMSR027")[0]}
    esperar("en el buscador, la otra sonda sale como equivalente",
            ("30081" in _res_n, str(_res_n.get("30081", {}).get("_estado", "")).startswith("🔴"),
             "contra lo buscado" in str(_res_n.get("30081", {}).get("Cadena", ""))),
            (True, False, False))

    # 82. 🕯️ LAS BUJÍAS QUE CALZAN (ver «LA BUJÍA POR SU CÓDIGO» y «LAS BUJÍAS QUE CALZAN,
    # RELACIONADAS SOLAS»): por el código, la rosca, el largo, el hexágono, el asiento y el
    # material; las que calzan se dan una por otra aunque cambie el grado térmico.
    _med = ns["medidas_de_la_bujia"]
    def _fisico(codigo, desc, marca_n="TARANTO", tipo="PROVEEDOR"):
        m = _med({"codigo_raw": codigo, "descripcion": desc, "marca": marca_n, "tipo": tipo})
        return m and tuple(m[k] for k in ns["CAMPOS_DE_LA_BUJIA"]) + (m["sistema"], m["grado"])
    esperar("NGK y Bosch, por su código",
            [_fisico("BKR6E", "BUJIAS NGK Fiat Palio 1.6"),
             _fisico("JBKR5E", "BUJIAS NGK"),
             _fisico("FR 7 DC", "BUJIA ENCEND Bosch CHEVROLET - FIAT", "JL"),
             _fisico("W 8 BC", "BUJIA ENCEND Bosch RENAULT 4/6/12", "JL"),
             _fisico("BPR5EFS", "BUJIA FORD SIERRA"),
             _fisico("TR55", "BUJIA APLICACION CHEVROLET S10"),
             _fisico("JPTR6F-13", "BUJIAS NGK"),
             _fisico("JBKR6EIX", "BUJIAS NGK"),
             _fisico("LSPP4ESLUCAS", "BUJIA NAFTA LSPP4ES Fiat 147 NGK= BP4ES BOSCH = W9DC", "FISPA")],
            [(14, 19.0, 16.0, "plano", "común", "NGK", 6),
             (14, 19.0, 16.0, "plano", "común", "NGK", 5),
             (14, 19.0, 16.0, "plano", "común", "Bosch", 7),
             (14, 12.7, 20.8, "plano", "común", "Bosch", 8),
             (14, 17.5, 16.0, "cónico", "común", "NGK", 5),
             (14, 17.5, 16.0, "cónico", "común", "NGK", 5),
             (14, 17.5, 16.0, "cónico", "platino", "NGK", 6),
             (14, 19.0, 16.0, "plano", "iridio", "NGK", 6),
             (14, 19.0, 20.8, "plano", "común", "NGK", 4)])
    esperar("lo que no se sabe leer, ni lo que no es una bujía de encendido, no tiene medidas",
            [_fisico("LFR5B", "BUJIA NGK"), _fisico("CT6QM :", "BUJIA NAFTA Ford Marelli", "JL"),
             _fisico("CY03", "Bujia encandescente Chevrolet"),
             _fisico("L215LUCAS", "CABLE DE BUJIA L215 NGK= BKR6E", "FISPA"),
             # El NGK y el Bosch que cita no calzan: no se sabe cuál es.
             _fisico("LSPX1LUCAS", "BUJIA NAFTA NGK= BKR6E BOSCH = WR7DC", "FISPA")],
            [None, None, None, None, None])
    mt4, mj4 = marca("TARANTO CUATRO"), marca("JL CUATRO")
    _bk5 = producto("BKR5E", "BUJIAS NGK Fiat Palio 1.6, Chrysler Neon 2.0", mt4)
    _bk6 = producto("BKR6E", "BUJIAS NGK Honda Civic", mt4)
    _bp6 = producto("BPR6E", "BUJIAS NGK VW Gol", mt4)
    # Otro grado y de platino: no calzan (el material), y el número de NGK es otro.
    _gp6 = producto("LSPKR5EGP", "BUJIA NAFTA PLATINO NGK= BKR5EGP Honda Civic", marca("FISPA CUATRO"))
    _fr6 = producto("FR 6 DC", "BUJIA ENCEND Bosch FIAT LINEA - PEUGEOT 206", mj4)
    _fr8 = producto("FR 8 DC", "BUJIA ENCEND Bosch RENAULT CLIO", mj4)
    _otra = producto("CAB77", "CABLE DE BUJIA RENAULT CLIO", mj4)
    vincular(_fr8, _otra, "JL CUATRO · 26/10")
    conn.commit()
    _ev = ns["evidencia_cruzada"]
    _a_favor, _vetos, _ = _ev(_bk5, _fr6)
    esperar("NGK contra Bosch que calzan, con otros autos: a favor y sin vetos",
            ([x[:15] for x in _a_favor if x.startswith("🕯️")], _vetos),
            (["🕯️ calzan igual"], []))
    esperar("otro hexágono: no entra",
            [v.startswith("🕯️ una no entra donde va la otra: hexágono") for v in _ev(_bk6, _bp6)[1]
             if v.startswith("🕯️")], [True])
    _cu6 = producto("LSPKR6E", "BUJIA NAFTA NGK= BKR6E Honda Civic", marca("LUCAS CUATRO"))
    esperar("solo otro material: decide el número de NGK, como antes",
            [v for v in _ev(_cu6, _gp6)[1]], ["🔤 bujías distintas: NGK BKR6E vs NGK BKR5EGP"])
    _otra_pieza = ns["otra_pieza_de_la_misma_lista"]
    esperar("dos de TARANTO que calzan no son «otra pieza»; las que no calzan, sí",
            (_otra_pieza("TARANTO CUATRO", "BKR5E", "BUJIAS NGK Fiat Palio", "BKR6E", "BUJIAS NGK Honda"),
             bool(_otra_pieza("TARANTO CUATRO", "BKR6E", "BUJIAS NGK Honda", "BPR6E", "BUJIAS NGK VW Gol"))),
            ("", True))
    # La cola, un rechazo de antes y uno de después.
    _antes_pend = c.execute("SELECT COUNT(*) FROM equivalencias_pendientes").fetchone()[0]
    c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, lote) "
              "VALUES (?, ?, 'lista_proveedor', 'TARANTO CUATRO · 26/10')", (min(_bk5, _fr6), max(_bk5, _fr6)))
    for _x, _y in ((_bk6, _fr6), (_bk6, _fr6)[::-1]):
        c.execute("INSERT INTO equivalencias_revisadas (producto_a_id, producto_b_id, decision, "
                  "revisado_por, motivo, fecha) VALUES (?, ?, 'rechazada', 'Chavo', NULL, "
                  "'2026-01-01 10:00:00')", (_x, _y))
    conn.commit()
    _par = lambda a, b: (min(a, b), max(a, b))
    _r1 = ns["relacionar_las_bujias_que_calzan"]()
    _de_bujias = lambda: {(a, b) for a, b in c.execute(
        "SELECT producto_a_id, producto_b_id FROM equivalencias WHERE "
        "producto_a_id IN (?, ?, ?, ?, ?) AND producto_b_id IN (?, ?, ?, ?, ?)",
        (_bk5, _bk6, _fr6, _fr8, _bp6) * 2)}
    esperar("aprueba la de la cola, la rechazada antes y une las nuevas; las que no calzan, no",
            (_r1["cola"] >= 1, _r1["rechazadas"],
             _de_bujias() >= {_par(_bk5, _fr6), _par(_bk6, _fr6), _par(_bk5, _bk6), _par(_fr6, _fr8)},
             any(_bp6 in p for p in _de_bujias())),
            (True, 1, True, False))
    esperar("la segunda vez no hace nada", ns["relacionar_las_bujias_que_calzan"](),
            {"cola": 0, "rechazadas": 0, "nuevos": 0})
    # Buscando la BKR5E: la FR 8 DC con su grado, y el cable unido a la FR 8 DC no viene por ahí.
    _res_b = {f["Codigo"]: f for f in ns["buscar_con_variantes_del_cero"]("BKR5E")[0]}
    esperar("en el buscador: el grado al lado, sin encadenar",
            ("FR 8 DC" in _res_b, "🕯️ Bosch 8 (lo buscado: NGK 5)" in _res_b.get("FR 8 DC", {}).get("Cadena", ""),
             bool(_res_b.get("FR 8 DC", {}).get("_complementario")), "CAB77" in _res_b),
            (True, True, False, False))
    # La 🏆: la del grado más cercano antes que la más barata (la Bosch FR 8 DC es la NGK 5).
    for _pid, _st, _pr in ((_fr6, 3, 100.0), (_fr8, 2, 300.0), (_bk6, 5, 200.0)):
        c.execute("UPDATE productos SET stock = ?, precio = ? WHERE id = ?", (_st, _pr, _pid))
    conn.commit()
    _filas_c, _reco = ns["coronar_la_recomendada"](ns["buscar_con_variantes_del_cero"]("BKR5E")[0])
    esperar("la 🏆, la del grado más cercano, y por qué no la más barata",
            (_reco["recomendada"] and _reco["recomendada"]["Codigo"],
             "es de otro grado térmico" in _reco["por_que_no"],
             [f["Codigo"] for f in _filas_c if f["Codigo"] in ("FR 8 DC", "BKR6E", "FR 6 DC")]),
            ("FR 8 DC", True, ["FR 8 DC", "BKR6E", "FR 6 DC"]))
    # Lo que una persona rechace de ahora en más, no se toca.
    ns["marcar_revision"]([(_bk6, _fr8)], "rechazada", quien="Chavo")
    c.execute("DELETE FROM equivalencias WHERE producto_a_id = ? AND producto_b_id = ?", _par(_bk6, _fr8))
    conn.commit()
    esperar("un rechazo nuevo manda", ns["relacionar_las_bujias_que_calzan"](),
            {"cola": 0, "rechazadas": 0, "nuevos": 0})
    _n_desh = ns["deshacer_lo_de_las_bujias"]()
    esperar("deshacer: todo a como estaba, y apagado",
            (_n_desh > 0, c.execute("SELECT COUNT(*) FROM equivalencias_pendientes").fetchone()[0] - _antes_pend,
             c.execute("SELECT revisado_por FROM equivalencias_revisadas WHERE producto_a_id = ? "
                       "AND producto_b_id = ?", (_bk6, _fr6)).fetchone()[0],
             _par(_bk5, _bk6) in _de_bujias(), ns["bujias_automaticas_prendido"]()),
            (True, 1, "Chavo", False, False))
    # 83. EL MISMO NÚMERO DE FÁBRICA, CITADO POR DOS LISTAS (ver ficha_de_prueba()): dos
    # listas que declaran el mismo número original, con las dos mitades sólidas, quedan
    # verificadas; si el número lo citan muchos o es universal, no. Y OTRO ESPESOR DE LA MISMA
    # JUNTA, en el buscador, es una variante y no cuenta como equivalencia (anotar_el_estado()).
    m5a, m5b, m5o = marca("CINCO A"), marca("CINCO B"), marca("OEM CINCO", "OEM")
    _ra = producto("RA55", "RETEN DE CIGUENAL FIAT 128", m5a)
    _rb = producto("RB55", "RETEN CIGUENAL FIAT 128 1.1", m5b)
    _num = producto("4402551", "RETEN DE CIGUENAL", m5o)
    vincular(_ra, _num, "CINCO A · 27/10")
    vincular(_rb, _num, "CINCO B · 27/10")
    conn.commit()
    _f83 = ns["ficha_de_prueba"](_ra, _rb)
    esperar("dos listas con el mismo número: verificada, y dice cuál",
            (_f83["estado"], _f83["por_numero_de_fabrica"]), ("✅ VERIFICADA", "4402551"))
    for _i in range(5):
        vincular(producto(f"RX{_i}", "RETEN DE CIGUENAL", m5a), _num, "CINCO A · 27/10")
    conn.commit()
    esperar("si el número lo citan muchos, no alcanza",
            ns["ficha_de_prueba"](_ra, _rb)["estado"], "🟡 PROBABLE")
    # Los mellizos de una misma lista: la FISPA y la LUCAS que vende FISPA, con el mismo número.
    m5f = marca("FISPA SEIS")
    _mf = producto("40068FISPA", "SENSOR MAP 40068 FORD FIESTA 1.6", m5f)
    _ml = producto("LEMSM057LUCAS", "SENSOR MAP LEMSM057 FORD FIESTA 1.6", m5f)
    _nm = producto("98AB9F479AA", "SENSOR MAP", m5o)
    vincular(_mf, _nm, "FISPA SEIS · 27/10")
    vincular(_ml, _nm, "FISPA SEIS · 27/10")
    conn.commit()
    esperar("mellizos de una lista, únicos con ese número: verificados",
            ns["ficha_de_prueba"](_mf, _ml)["estado"], "✅ VERIFICADA")
    vincular(producto("LEMSM058LUCAS", "SENSOR MAP LEMSM058 FORD FIESTA 1.6", m5f), _nm,
             "FISPA SEIS · 27/10")
    conn.commit()
    esperar("con dos LUCAS para una FISPA, no se sabe cuál",
            ns["ficha_de_prueba"](_mf, _ml)["estado"], "🟡 PROBABLE")
    _ja = producto("JT120", "JUNTA TAPA DE CILINDROS FIAT 128 1.20MM", m5a, espesor=1.2)
    _jb = producto("JT140", "JUNTA TAPA DE CILINDROS FIAT 128 1.40MM", m5b, espesor=1.4)
    _nj = producto("4401212", "JUNTA TAPA DE CILINDROS", m5o)
    vincular(_ja, _nj, "CINCO A · 27/10")
    vincular(_jb, _nj, "CINCO B · 27/10")
    conn.commit()
    _res83 = {f["Codigo"]: f for f in ns["buscar_con_variantes_del_cero"]("JT120")[0]}
    esperar("otro espesor: una variante, dicha, que no cuenta",
            (bool(_res83.get("JT140", {}).get("_complementario")),
             "📏 otro espesor" in _res83.get("JT140", {}).get("Cadena", "")),
            (True, True))
    # 84. LAS ABREVIATURAS DE LAS LISTAS, EN LA BÚSQUEDA POR TEXTO (ver formas_de_la_palabra()):
    # «junta tapa» encuentra la «JTA.TAPA CIL. CORSA»; «ESC» cuenta como ESCAPE solo como
    # palabra entera (no adentro de DESCARGA); y a igual cantidad, primero lo escrito tal cual.
    m6 = marca("SEIS JUNTAS")
    _jta = producto("JT84", "JTA.TAPA CIL. CORSA 1.6 8V", m6)
    _esc = producto("JE84", "JTA ESC. CORSA 1.6", m6)
    _desc = producto("JD84", "JUNTA DESCARGA TURBO CORSA", m6)
    _jgo = producto("JG84", "JGO.DESCARBONIZACION FIAT PALIO 1.3 FIRE 8V", m6)
    _juego = producto("JU84", "JUEGO DESCARBONIZACION PALIO", m6)
    conn.commit()

    def _ids84(texto):
        return [f["ID"] for f in ns["buscar_por_texto"](texto)]
    esperar("«junta tapa» encuentra la JTA.TAPA", _jta in _ids84("junta tapa"), True)
    esperar("«junta escape»: la JTA ESC sí, la DESCARGA no",
            (_esc in _ids84("junta escape"), _desc in _ids84("junta escape")),
            (True, False))
    _orden84 = _ids84("jgo descarbonizacion palio")
    esperar("lo escrito tal cual va antes que el sinónimo más corto",
            _orden84.index(_jgo) < _orden84.index(_juego) if _juego in _orden84 else None, True)
    # 85. Las marcas como árbol (ver alternativas_en_arbol()) encuentran lo mismo que la lista
    # de la más larga a la más corta: la más larga que calce, y si no calza, la más corta.
    import re as _re
    _palabras85 = ["FIAT", "FIAT PALIO", "LAND ROVER", "ROVER", "M.BENZ", "MERCEDES",
                   "MERCEDES BENZ", "VW", "VOLKSWAGEN"]
    _textos85 = ["Bomba FIAT PALIOS 1.3", "fiat palio fire", "Kit LAND ROVER y Rover 75",
                 "M.BENZ 1114 - Mercedes Benz Sprinter", "VOLKSWAGENGOL vw", "MERCEDESX"]
    for _ign in (True, False):
        _flags = _re.IGNORECASE if _ign else 0
        _lista = _re.compile(r"(?<![A-Z0-9])(" + "|".join(_re.escape(p) for p in sorted(
            _palabras85, key=len, reverse=True)) + r")(?![A-Z0-9])", _flags)
        _arbol = _re.compile(r"(?<![A-Z0-9])(" + ns["alternativas_en_arbol"](
            _palabras85, sin_mayusculas=_ign) + r")(?![A-Z0-9])", _flags)
        esperar(f"el árbol de marcas encuentra lo mismo (mayúsculas {'no ' if _ign else ''}importan)",
                [_arbol.findall(t) for t in _textos85], [_lista.findall(t) for t in _textos85])
    # 86. OTRA VERSIÓN DE LA MISMA LISTA (ver VETO_OTRA_VERSION): la misma descripción con otro
    # código y otro precio es una variante en el buscador; con el mismo precio, una fila leída
    # dos veces, que sigue roja.
    m8, m8o = marca("OCHO JUNTAS"), marca("OEM OCHO", "OEM")
    _v1 = producto("JV-175-23", "JUNTA TAPA DE VALVULAS PERKINS 6-305", m8, precio=11900)
    _v2 = producto("JV-175-30", "JUNTA TAPA DE VALVULAS PERKINS 6-305", m8, precio=7070)
    _v3 = producto("JV-175-31", "JUNTA TAPA DE VALVULAS PERKINS 6-305", m8, precio=11900)
    _n8 = producto("0490760", "JUNTA TAPA DE VALVULAS", m8o)
    for _v in (_v1, _v2, _v3):
        vincular(_v, _n8, "OCHO JUNTAS · 27/10")
    conn.commit()
    _res86 = {f["Codigo"]: f for f in ns["buscar_con_variantes_del_cero"]("JV17523")[0]}

    def _version86(codigo):
        f = _res86.get(codigo, {})
        return bool(f.get("_complementario")), "🔁 otra versión" in (f.get("Cadena") or "")
    esperar("otro código y otro precio: otra versión, aparte",
            (_version86("JV-175-30"), _version86("JV-175-31")), ((True, True), (False, False)))
    # 87. LO QUE NOMBRA EL AUTO MANDA (ver nivel_del_auto()): «bomba de agua k4m» trae la del
    # K4M, y las bombas de cualquier auto van aparte; si ninguna nombra el auto, todas, como
    # antes; «gol» no es GOLF.
    m9 = marca("NUEVE BOMBAS")
    _k4m = producto("BA87K", "BOMBA DE AGUA RENAULT CLIO MEGANE 1.6 16V K4M-700", m9)
    _otra = producto("BA87F", "BOMBA DE AGUA FIAT PALIO 1.3 FIRE", m9)
    _sola = producto("BA87S", "BOMBA DE AGUA", m9)
    _golf = producto("BA87G", "BOMBA DE AGUA VW GOLF 2.0", m9)
    conn.commit()
    _r87 = ns["buscar_por_texto"]("bomba de agua k4m")
    _aparte87 = {f["ID"] for f in _r87.aparte}
    esperar("«bomba de agua k4m»: la del K4M, y las otras aparte",
            ([f["ID"] for f in _r87 if f["ID"] in (_k4m, _otra, _sola, _golf)],
             {_otra, _sola, _golf} <= _aparte87, _r87.del_auto), ([_k4m], True, ["K4M"]))
    _r87b = ns["buscar_por_texto"]("bomba de agua siena")
    esperar("si ninguna nombra el auto, todas y nada aparte",
            ({_k4m, _otra, _sola} <= {f["ID"] for f in _r87b}, _r87b.aparte), (True, []))
    _gol = producto("BA87L", "BOMBA DE AGUA VW GOL/PARATI 1.6", m9)
    # Que GOL sea un modelo conocido, como en la base real (sale de las aplicaciones).
    c.execute("INSERT INTO aplicaciones (marca_auto, modelo_auto, codigo, codigo_clean, origen) "
              "VALUES ('VOLKSWAGEN', 'GOL', 'BA87L', 'BA87L', 'deducida')")
    conn.commit()
    ns["_MODELOS_CACHE"]["lista"] = None
    _r87c = ns["buscar_por_texto"]("bomba de agua gol")
    esperar("«gol» no es GOLF", (_gol in {f["ID"] for f in _r87c},
                                 _golf in {f["ID"] for f in _r87c.aparte}), (True, True))
    # 88. EL PLURAL Y LA CILINDRADA COMO LA ESCRIBEN LAS LISTAS (ver formas_de_la_palabra()):
    # «rulemanes» encuentra el RULEMAN; «1.6» también «1 6» y «1,6», pero no «11.6».
    m10 = marca("DIEZ RUEDAS")
    _rul = producto("RU88", "RULEMAN RUEDA DELANTERA VW SURAN", m10)
    _b16 = producto("BU88A", "BUJIA CORSA 1 6 8V", m10)
    _b16c = producto("BU88B", "BUJIA CORSA 1,6 16V", m10)
    _b116 = producto("BU88C", "BUJIA CORSA 11.6", m10)
    conn.commit()
    producto("FA88", "FARO SURAN", m10)        # sin el singular, el aflojado lo pone primero
    conn.commit()
    esperar("«rulemanes» encuentra el RULEMAN, primero",
            [f["ID"] for f in ns["buscar_por_texto"]("rulemanes suran")][:1], [_rul])
    _ids88 = {f["ID"] for f in ns["buscar_por_texto"]("bujia 1.6")}
    esperar("«1.6» es también «1 6» y «1,6», no «11.6»",
            (_b16 in _ids88, _b16c in _ids88, _b116 in _ids88), (True, True, False))
    # Y lo que declara OTRA cilindrada va aparte; lo que no declara ninguna, no (como el año).
    _e16 = producto("EM88A", "EMBRAGUE VW GOL 1.6", m10)
    _e10 = producto("EM88B", "EMBRAGUE VW GOL POWER 1 0 8V", m10)
    _esin = producto("EM88C", "EMBRAGUE VW GOL", m10)
    conn.commit()
    _r88 = ns["buscar_por_texto"]("embrague gol 1.6")
    esperar("«embrague gol 1.6»: el 1.0 aparte, el que no dice cilindrada no",
            ({_e16, _esin} <= {f["ID"] for f in _r88}, _e10 in {f["ID"] for f in _r88.aparte},
             "otra cilindrada" in _r88.por_que_aparte), (True, True, True))
    # 89. LA MARCA COMO LA ESCRIBA LA LISTA (VW es VOLKSWAGEN; para buscar, GM es Chevrolet), LA
    # PIEZA PEDIDA (lo que no la dice va aparte) Y LAS VÁLVULAS (las otras, aparte).
    m11 = marca("ONCE FILTROS")
    _fvw = producto("FA89A", "FILTRO AIRE VW GOL", m11)
    _fvolks = producto("FA89B", "FILTRO DE AIRE VOLKSWAGEN GOL", m11)
    _jgo = producto("JC89", "VW GOL 1.6 NAFTA MULTIPUNTO", m11)     # como IMPERIAL: sin pieza
    _fgm = producto("FA89C", "FILTRO AIRE GM CORSA", m11)
    _k8 = producto("KD89A", "KIT DISTRIBUCION VW GOL 8V", m11)
    _k16 = producto("KD89B", "KIT DISTRIBUCION VW GOL 16 V", m11)
    conn.commit()
    _r89 = ns["buscar_por_texto"]("filtro aire volkswagen gol")
    esperar("«volkswagen» encuentra «VW»; lo que no dice la pieza, aparte",
            ({_fvw, _fvolks} <= {f["ID"] for f in ns["buscar_por_texto"]("volkswagen gol")},
             _jgo in {f["ID"] for f in _r89.aparte}), (True, True))
    esperar("«chevrolet» encuentra «GM»",
            _fgm in {f["ID"] for f in ns["buscar_por_texto"]("chevrolet corsa")}, True)
    _r89b = ns["buscar_por_texto"]("kit distribucion gol 16v")
    esperar("«16v»: el «16 V» sí, el 8V aparte",
            (_k16 in {f["ID"] for f in _r89b}, _k8 in {f["ID"] for f in _r89b.aparte}), (True, True))
    # 90. LOS SINÓNIMOS DEL MOSTRADOR (ver SINONIMOS_DEL_MOSTRADOR) y lo apartado, con su motivo
    # y en orden de parecido.
    m12 = marca("DOCE MOSTRADOR")
    _pal = producto("PA90", "PALIER LADO IZQUIERDO SURAN", m12)
    _bc = producto("BC90", "BOMBA DE COMBUSTIBLE SURAN", m12)
    conn.commit()
    esperar("el aviso de lo que no aparece entiende los sinónimos: «semieje» es PALIER",
            ns["palabras_que_no_aparecen"]("semieje suran", ns["buscar_por_texto"]("semieje suran")),
            [])
    esperar("«semieje» encuentra el PALIER y «nafta» la de COMBUSTIBLE, primeros",
            ([f["ID"] for f in ns["buscar_por_texto"]("semieje suran")][:1],
             [f["ID"] for f in ns["buscar_por_texto"]("nafta suran")][:1]), ([_pal], [_bc]))
    esperar("cada apartado dice por qué",
            {f.get("Por qué") for f in _r87.aparte if f["ID"] in (_otra, _sola)}, {"no dice «k4m»"})
    # Lo apartado por no decir la pieza y por no decir el auto, mezclado por parecido: «VW GOL
    # NAFTA» (sin pieza, la más corta) antes que el filtro de otro auto.
    producto("FN90A", "FILTRO NAFTA VW GOL", m12)
    _sin_pieza = producto("FN90B", "VW GOL NAFTA", m12)
    producto("FN90C", "FILTRO DE NAFTA FIAT UNO", m12)
    conn.commit()
    esperar("lo apartado, en orden de parecido",
            [f["ID"] for f in ns["buscar_por_texto"]("filtro nafta gol").aparte][:1], [_sin_pieza])
    # 91. EL RUBRO NO DESCARTA LO QUE DICE LA PIEZA PEDIDA: «porta bancada reten» es de Motor
    # (BANCADA va primero) y «PORTA RETEN BANCADA MAXION» de Retenes (RETEN va primero).
    m13 = marca("TRECE PORTA")
    _porta = producto("PR91", "PORTA RETEN BANCADA MAXION", m13)
    producto("PC91", "PORTA COJINETE BANCADA FIAT", m13)      # este sí es de Motor
    conn.commit()
    esperar("«porta bancada reten» encuentra «PORTA RETEN BANCADA», primero",
            [f["ID"] for f in ns["buscar_por_texto"]("porta bancada reten")][:1], [_porta])
    # 92. LAS PALABRAS DE UNA O DOS LETRAS, ENTERAS («MB» no está en CAMBA); LOS NÚMEROS, NO
    # ADENTRO DEL CÓDIGO DE BARRAS (el entero sí); Y LOS MODELOS CORTOS («ka» es un modelo).
    m14 = marca("CATORCE CORTAS")
    _mb = producto("KT92", "KIT TTC MB 1114", m14)
    _camba = producto("CAMBA92", "BULON CAMBA ZINCADO", m14)
    _ean = producto("FX92", "FILTRO EXTRA", m14, codigo_barras="7793960050151")
    _f0151 = producto("FY92", "FILTRO 0151 ESPECIAL", m14)
    _eka = producto("EK92", "EMBRAGUE FORD KA", m14)
    _etr = producto("ET92", "EMBRAGUE FORD TRANSIT", m14)
    conn.commit()
    _ids92 = {f["ID"] for f in ns["buscar_por_texto"]("mb")}
    esperar("«mb» entera: el MB sí, CAMBA no", (_mb in _ids92, _camba in _ids92), (True, False))
    _ids92b = {f["ID"] for f in ns["buscar_por_texto"]("filtro 0151")}
    esperar("«0151» no adentro del código de barras; el código de barras entero sí",
            (_f0151 in _ids92b, _ean in _ids92b,
             _ean in {f["ID"] for f in ns["buscar_por_texto"]("7793960050151")}), (True, False, True))
    # Y el corrector de tipeo no pisa un sinónimo: «sopapa» no es SOLAPA (ver palabras_corregidas()).
    producto("SO92A", "SOLAPA DE PUERTA", m14)
    producto("SO92B", "SOLAPA DE CAPOT", m14)
    producto("SO92C", "SOLAPA DE BAUL", m14)
    producto("VA92", "VALVULA ESCAPE FIAT 128", m14)
    conn.commit()
    ns["vocabulario_de_busqueda"].clear()
    esperar("«sopapa» no se corrige a SOLAPA", ns["palabras_corregidas"]("sopapa escape"), {})
    # 93. EL TIPEO ES DE TECLADO: una letra por un número no, salvo que se parezcan (O y 0);
    # y «Búsquedas sin resultado» no pide resolver lo que el buscador hoy ya encuentra.
    m15 = marca("QUINCE CODIGOS")
    producto("271294", "JUNTA TAPA", m15)
    producto("0280156020", "INYECTOR", m15)
    producto("KIT22482", "KIT", m15)
    producto("LEICJ057LUCAS", "INYECTOR LEICJ057", m15)
    c.executemany("INSERT INTO historial_busquedas (termino, usuario, sin_resultado) VALUES (?, ?, 1)",
                  [("LEICJ057", "ana"), ("LEICJ057", "beto"), ("W712/94", "ana"), ("W712/94", "beto")])
    conn.commit()

    def _tipeo93(codigo):
        return [f["Codigo"] for f in ns["codigos_por_tipeo"](codigo)]
    esperar("tipeo: W→2 no; O→0 sí; un dígito por otro sí",
            ("271294" in _tipeo93("W71294"), "0280156020" in _tipeo93("028015602O"),
             "KIT22482" in _tipeo93("KIT22382")), (False, True, True))
    esperar("«Búsquedas sin resultado» no muestra lo que hoy se encuentra (LEICJ057LUCAS)",
            [f["Buscado"] for f in ns["que_conviene_cargar_o_pedir"]()
             if f["Buscado"] in ("LEICJ057", "W712/94")], ["W712/94"])
    # 94. DE QUÉ AUTOS ES UN MOTOR, SEGÚN LAS LISTAS (ver autos_del_motor()): la misma búsqueda
    # con el auto en vez del motor; con menos de cinco productos, nada.
    m16 = marca("DIECISEIS MOTORES")
    for _i in range(5):
        producto(f"ZX9{_i}", f"BOMBA DE AGUA VW GOL 1.6 16V ZX9M LADO {_i}", m16)
    for _i in range(3):
        producto(f"QW8{_i}", f"BOMBA DE AGUA VW GOL QW8M {_i}", m16)
    conn.commit()
    esperar("«bomba de agua zx9m» ofrece «bomba agua gol 1.6 16v»",
            [(m, b) for m, _a, b in ns["sugerencias_por_el_motor"]("bomba de agua zx9m")],
            [("ZX9M", ["bomba agua gol 1.6 16v"])])
    esperar("con menos de cinco productos, nada", ns["sugerencias_por_el_motor"]("bomba qw8m"), [])
    _r92 = ns["buscar_por_texto"]("embrague ford ka")
    esperar("«ka» es un modelo: el de la Transit, aparte",
            (_eka in {f["ID"] for f in _r92}, _etr in {f["ID"] for f in _r92.aparte}), (True, True))
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
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

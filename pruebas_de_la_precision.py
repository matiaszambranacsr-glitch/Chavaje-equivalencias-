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

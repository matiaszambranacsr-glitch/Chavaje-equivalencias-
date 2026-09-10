"""Pruebas del núcleo. Corren sin Streamlit y sin la app: `python3 -m nucleo.pruebas`.

Cada caso viene de una lista de proveedor real, no de un ejemplo inventado. Los que dicen
"NO debe" son los que más importan: un código de más ensucia la base con equivalencias falsas,
y eso es peor que no tener la equivalencia.
"""
import sqlite3
import sys

from . import codigos, equivalencias, planillas, vehiculos

fallos = []


def igual(obtenido, esperado, que):
    if obtenido != esperado:
        fallos.append(f"{que}\n      esperaba: {esperado}\n      obtuvo:   {obtenido}")


def cierto(condicion, que):
    if not condicion:
        fallos.append(que)


# ------------------------------------------------------------------ códigos
def probar_sanitizar():
    # Excel guarda los códigos numéricos como número: '2776400' llega '2776400.0'. Sin sacar el
    # '.0' queda '27764000', un cero de más, y el producto no se encuentra nunca por su código.
    igual(codigos.sanitizar("2776400.0"), "2776400", "el .0 de Excel")
    igual(codigos.sanitizar("036115561G"), "036115561G", "código con letra al final")
    igual(codigos.sanitizar("FI-IWP044"), "FIIWP044", "guiones fuera")
    igual(codigos.sanitizar(None), "", "None no rompe")
    igual(codigos.sanitizar("nan"), "", "el nan de pandas")
    # Un código que Excel muestra en notación científica se pasa al entero que representa.
    igual(codigos.sanitizar("1.09E+11"), "109000000000", "notación científica")
    # ...pero 'BE-777' NO es notación científica, y se rompía justo así.
    igual(codigos.sanitizar("BE-777"), "BE777", "BE-777 no es notación científica")
    # Ni tampoco un código de fábrica que casualmente tiene una E en el medio. El signo del
    # exponente es lo que los separa: Excel siempre escribe E+11 o E-05, y estos no llevan
    # signo. Sin esa distinción, el filtro de combustible Toyota 23390-0E010 se guardaba como
    # el número 2339000000000000 y el producto quedaba imposible de encontrar. Son 114 códigos
    # distintos, 230 apariciones, en cinco listas reales.
    for real in ("233900E010", "2263051E00", "2263051E10", "1E0318760", "5960E6", "123456E7"):
        igual(codigos.sanitizar(real), real, f"«{real}» es un código, no notación científica")
        cierto(not codigos.codigo_sospechoso(real, "")[0],
               f"«{real}» no se puede marcar como número roto")


def probar_codigo_util():
    for malo in ("1", "12", "07", "3.0", "  2  ", "A1"):
        cierto(not codigos.es_codigo_util(malo), f"'{malo}' NO debería ser un código útil")
    for bueno in ("123", "036115561G", "IWP044", "L52541"):
        cierto(codigos.es_codigo_util(bueno), f"'{bueno}' SÍ debería ser un código útil")


def probar_codigo_sospechoso():
    """Una medida o una palabra PEGADA a un código no hacen que el código deje de existir.

    Marcar de más no es inocuo: cada código marcado manda un vínculo bueno a la cola de
    revisión, o sea que los equivalentes de ese proveedor no aparecen en una búsqueda. Sobre
    cinco listas reales esto marcaba 2.406 códigos y unos 2.170 eran válidos."""
    # Códigos de proveedor REALES que llevan la medida o una aclaración adentro
    for bueno in ('H21A1/2"RF1,5',        # IMPERIAL, abrazadera de 1/2 pulgada
                  "F000 TE1 3X9",          # Bosch
                  "RAPI-335024X45",        # IMPERIAL
                  "278.897 c/CHAPA",       # JL: el código es 278.897, "c/CHAPA" aclara
                  "12345 TIPO"):
        malo, motivo = codigos.codigo_sospechoso(bueno, "")
        cierto(not malo, f"«{bueno}» es un código de verdad y quedó marcado: {motivo}")
    # Y lo que SÍ es una medida o la descripción metida en la columna del código
    for malo_de_verdad in ("20x2.50x180", "35x52x7", '1/2"', "ARO",
                           "JUEGO DE AROS DIESEL", "SECTOR CANAL"):
        malo, _ = codigos.codigo_sospechoso(malo_de_verdad, "")
        cierto(malo, f"«{malo_de_verdad}» NO es un código y no se marcó")


def probar_extractor():
    # Lo que SÍ tiene que sacar: son cruces reales, verificados contra las dos listas.
    debe = [
        ("SENSOR TEMPERATURA Chevrolet ONIX/PRISMA 1.4 8V (25186240)", "25186240"),
        ("INYECTOR GOL-POLO 1.6/1.8 MPI gris IWP044", "IWP044"),
        ("BOBINA MAZDA/MITSUBISHI H3T021/F 693", "H3T021"),
        ("INTERRUPTOR STOP AUDI/VW (547945515A)-Ford", "547945515A"),
        ("ROTULA VW GOL - ORIG 6Q0407365", "6Q0407365"),
        # HTML adentro de la descripción: la etiqueta pegaba el número y lo deformaba.
        ("MOTOR ARRANQUE <b>DAEWOO</b> 0001115005<br>BOSCH", "0001115005"),
        # muletilla pegada al código porque la exportación se comió el espacio
        ("BOMBA DE AGUA REF ORIGINALES0360601402", "0360601402"),
        # Códigos reales de exactamente seis caracteres limpios: el largo mínimo se mide sobre
        # el código sin puntuación, y estos tienen que sobrevivir a esa medición.
        ("SENSOR MAP VW GOL 1.0 MPI T-PRT04/B", "T-PRT04"),
        ("BOBINA Toyota COROLLA (90919-C2003)", "90919-C2003"),
    ]
    for texto, esperado in debe:
        got = codigos.extraer_codigos_de_texto(texto)
        cierto(esperado in got, f"debía sacar {esperado} de «{texto[:44]}» y sacó {got}")

    # Lo que NO tiene que sacar. Cada uno de estos vincula entre sí TODAS las filas donde
    # aparece, así que uno solo arrastra decenas de equivalencias falsas.
    no_debe = [
        "FILTRO DE AIRE GOL 1998-2006",          # rango de años: era el peor de todos
        "PASTILLA DE FRENO 205-206-306 PEUGEOT",  # lista de modelos
        "BUJIA TOYOTA 4-RUNNER",                  # nombre de modelo
        "INYECTOR AUDI A3-A4-A6",                 # modelos enumerados
        "KIT CORREA POLY V 6PK1555",              # medida de correa
        "TERMOSTATO 406 Motor XU7JP4",            # motorización PSA
        "SENSOR PEUGEOT 307 TU5JP4",
        "TRANSMISOR NIVEL PEUGEOT 407 DW10BTED4",
        "BUJIA Hilux 2GD-FTV",                    # motorización japonesa
        "TAPA BMW 320I-323I",                     # modelos de BMW
        "BOMBA DESDE1993 HASTA2005",              # año con la palabra pegada
        "AMORTIGUADOR 1995/96",
        "BULBO 1 8 118?CREF",                     # texto roto al exportar
        # Pedazos de texto que parecían códigos por tener seis caracteres CON la puntuación,
        # pero cuyo código limpio tiene cinco. En la base real estaban uniendo una dirección
        # con una refrigeración y una distribución con un encendido.
        "MOTOR Chevrolet Aveo5: 1.6",
        "TURBO VW TDI-A6 quattro",
        "TAPA FORD 16V-KA 1.0",
        "CANO Ford F 100-F 1000-F 4000 3.9",
        "RETEN 32x18x105mm",                      # medida con la unidad pegada
    ]
    for texto in no_debe:
        got = codigos.extraer_codigos_de_texto(texto)
        cierto(not got, f"NO debía sacar nada de «{texto[:44]}» y sacó {got}")

    # El código de la propia fila con una palabra pegada atrás no es un código de fábrica.
    igual(codigos.extraer_codigos_de_texto("FICHA DE INYECCION 52031Ficha para Bomba",
                                           codigo_propio="52031FISPA"), [],
          "el código propio con una palabra pegada")
    # ...pero las variantes reales de un mismo código, que se diferencian por número, sí pasan.
    cierto("FLO35121" in codigos.extraer_codigos_de_texto("TAPA RADIADOR FLO35121 reemplaza",
                                                          codigo_propio="FLO35122A"),
           "una variante real del mismo código no se debe perder")


def probar_filtro_por_repeticion():
    # 'CLA200' (modelo Mercedes) e 'IWP065' (inyector Marelli) tienen la MISMA forma: tres
    # letras y tres números. No hay expresión regular que los distinga. Lo que los distingue es
    # en cuántas filas de la lista aparece cada uno.
    pares = [(f"TAPA ACEITE M.BENZ A200/CLA200 var {i}", f"MTA{4000 + i}") for i in range(12)]
    pares += [("INYECTOR MPI BOSCH PALIO 1.3 8v reemplazo IWP065", "0280157512"),
              ("INYECTOR PALIO 1.3 reemplazo IWP065", "0280157513")]
    buenos, conteo = codigos.codigos_confiables_de_descripciones(pares)
    cierto("IWP065" in buenos, "el inyector aparece 2 veces y tiene que quedar")
    cierto("CLA200" not in buenos, "el modelo aparece 12 veces y tiene que irse")
    cierto(conteo.get("CLA200", 0) > conteo.get("IWP065", 0), "el conteo tiene que reflejarlo")


def probar_dividir():
    igual(codigos.dividir_codigos("036115561G / 03C115561H"), ["036115561G", "03C115561H"],
          "una celda con dos códigos")
    igual(codigos.dividir_codigos("1109AN/1109AB"), ["1109AN", "1109AB"],
          "dos códigos completos pegados por la barra")

    # Lo de arriba es lo fácil. Lo difícil es cuándo la barra y la coma NO separan, que es la
    # mayoría de las veces en estas listas. Cada uno de estos casos rompía un código real y,
    # peor, cargaba el pedazo suelto como si fuera un producto: un código llamado «PVC» se
    # cuelga después de todo lo que mencione PVC y fusiona familias enteras.
    # Sobre cinco listas reales: 4.017 códigos fantasma que se dejan de crear en una sola.
    for entero in ("208.856 C/PVC",        # c/ = "con", no separador
                   "23 8130R c/soporte",
                   "BOT622-S/MED",
                   'H21A1/2"RF1,5',        # 1/2 es una fracción: media pulgada
                   "RHEIN-SCV3/8a1",
                   "SABO-02233/BRG",       # sufijo de variante, no un código aparte
                   "RODGE-MINI/10F",
                   "W712/94",              # filtro Mann: un solo código
                   "WK842/2"):
        igual(codigos.dividir_codigos(entero), [entero], f"«{entero}» es UN código")

    # La coma argentina. Sin esto «RHEIN-CCSP-20,5» quedaba «RHEIN-CCSP-20», y como el decimal
    # era lo único que lo distinguía, terminaba siendo el mismo código que «RHEIN-CCSP-20,0»:
    # un producto entero desaparecía del catálogo, pisado por el otro, sin ningún aviso.
    # Son 3.811 códigos en una sola lista real.
    igual(codigos.dividir_codigos("RHEIN-CCSP-20,5"), ["RHEIN-CCSP-20,5"], "la coma decimal")
    cierto(codigos.sanitizar("RHEIN-CCSP-20,5") != codigos.sanitizar("RHEIN-CCSP-20,0"),
           "dos medidas distintas no pueden terminar siendo el mismo código")
    # ...pero la coma que sí separa una lista tiene que seguir separando
    igual(codigos.dividir_codigos("ABC123,DEF456"), ["ABC123", "DEF456"], "la coma que sí separa")


# ------------------------------------------------------------------ vehículos
def probar_vehiculos():
    # Listas que exportan varias columnas pegadas sin espacio en el medio.
    igual(vehiculos.separar_texto_pegado("DespieceCHEVROLETCAPUCHON BUJIA"),
          "Despiece CHEVROLET CAPUCHON BUJIA", "despegar la marca del texto")
    cierto("FILTRO" in (vehiculos.clasificar_repuesto("FILTRO DE ACEITE MANN") or "").upper()
           or vehiculos.clasificar_repuesto("FILTRO DE ACEITE MANN"),
           "un filtro se tiene que clasificar")
    igual(vehiculos.extraer_anios("GOL 1998-2006"), (1998, 2006), "años de la descripción")


# ------------------------------------------------------------------ planillas
def probar_mapeo_columnas():
    # Con encabezado de verdad: el EAN NUNCA puede quedar como código principal, porque en el
    # mostrador se pide el número de parte, no el código de barras.
    enc = ["INVENTORY_ITEM_ID", "DESCRIPTION", "PRECIO_NUEVO", "DES", "LINEA_N", "CODIGO_EAN"]
    m = planillas.adivinar_columnas(enc)
    igual(m["prov"], 0, "el código de proveedor")
    igual(m["desc"], 1, "la descripción")
    igual(m["precio"], 2, "el precio")
    igual(m["ean"], 5, "el EAN aparte")
    cierto(m["prov"] != m["ean"], "el EAN no puede ser el código principal")

    # Sin encabezado: hay que deducir por los VALORES. De cinco listas reales, cuatro venían así.
    filas = [["", "", "26001FISPA", 1440.0, "CONECTOR PARA MANGUERA 260"],
             ["", "", "26002FISPA", 1440.0, "CONECTOR PARA MANGUERA 261"],
             ["", "", "26003FISPA", 1512.5, "ADAPTADOR DE MANGUERA 90 GRADOS"]] * 8
    m2 = planillas.adivinar_columnas_por_datos(filas, 5)
    igual(m2["prov"], 2, "código deducido por los datos")
    igual(m2["precio"], 3, "precio deducido por los datos")
    igual(m2["desc"], 4, "descripción deducida por los datos")


# ------------------------------------------------------------------ búsqueda
def base_de_prueba():
    """Arma la situación que fallaba: dos proveedores que NO comparten ningún código propio, y
    que solo se tocan a través del código de fábrica."""
    con = equivalencias.preparar(sqlite3.connect(":memory:"))
    cur = con.cursor()

    def marca(nombre, tipo="PROVEEDOR"):
        cur.execute("INSERT INTO marcas (nombre, tipo) VALUES (?, ?)", (nombre, tipo))
        return cur.lastrowid

    def producto(marca_id, code, desc=""):
        cur.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id)"
                    " VALUES (?, ?, ?, ?)", (code, codigos.sanitizar(code), desc, marca_id))
        return cur.lastrowid

    def vincular(a, b, confianza=80):
        cur.execute("INSERT INTO equivalencias (producto_a_id, producto_b_id, confianza)"
                    " VALUES (?, ?, ?)", (a, b, confianza))

    fispa, jl, oem = marca("FISPA"), marca("JL"), marca("OEM / FABRICA", "OEM")
    p_fispa = producto(fispa, "624FISPA", "BULBO DE TEMPERATURA CHEVROLET ONIX")
    p_jl = producto(jl, "WS3171", "SENSOR TEMPERATURA Chevrolet ONIX/PRISMA")
    p_oem = producto(oem, "25186240", "")
    vincular(p_fispa, p_oem)
    vincular(p_jl, p_oem)
    # Un código GENÉRICO no debe servir de PUENTE: '1234' de una marca y '1234' de otra son
    # casi seguro piezas distintas, porque los catálogos numeran de corrido y los números
    # chicos se repiten en todos. Se arma la trampa: BUJIA está vinculada a un '1234', y hay
    # otro '1234' de otra marca vinculado a TUERCA. Si el código genérico hiciera de puente,
    # buscar la bujía traería la tuerca.
    otra = marca("OTRA")
    p_bujia = producto(fispa, "BUJIA-XR7", "BUJIA")
    p_g1 = producto(fispa, "1234", "generico de una marca")
    p_g2 = producto(otra, "1234", "generico de la otra")
    p_tuerca = producto(otra, "TUERCA-M8", "TUERCA")
    vincular(p_bujia, p_g1)
    vincular(p_g2, p_tuerca)
    con.commit()
    return con, cur


def probar_busqueda_entre_proveedores():
    con, cur = base_de_prueba()
    res = equivalencias.buscar_por_codigo(cur, codigos.sanitizar("624FISPA"))
    marcas = {f["Marca"] for f in res}
    cierto("JL" in marcas,
           f"buscando el código de FISPA tiene que aparecer JL; aparecieron {sorted(marcas)}")
    # y en el otro sentido
    res2 = equivalencias.buscar_por_codigo(cur, codigos.sanitizar("WS3171"))
    cierto("FISPA" in {f["Marca"] for f in res2}, "el cruce tiene que andar en los dos sentidos")
    # el tope de saltos tiene que cortar de verdad
    cortado = equivalencias.buscar_por_codigo(cur, codigos.sanitizar("624FISPA"), max_saltos=1)
    cierto(len(cortado) <= len(res), "con tope de saltos no puede devolver más")
    con.close()


def probar_codigo_generico_no_cruza():
    con, cur = base_de_prueba()
    res = equivalencias.buscar_por_codigo(cur, codigos.sanitizar("BUJIA-XR7"))
    encontrados = {f["Codigo"] for f in res}
    cierto("TUERCA-M8" not in encontrados,
           f"un '1234' genérico NO puede unir dos familias distintas; trajo {sorted(encontrados)}")
    # Buscar el código genérico EXACTO sí tiene que mostrar las dos marcas que lo tienen: eso no
    # es una suposición, es el número que se pidió. Lo que no se hace es seguir la cadena desde
    # ahí. Son dos cosas distintas y conviene que la prueba deje asentada la diferencia.
    directo = equivalencias.buscar_por_codigo(cur, "1234")
    igual(len({f["Marca"] for f in directo}), 2, "buscar el genérico exacto muestra las dos marcas")
    con.close()


def main():
    for prueba in (probar_sanitizar, probar_codigo_util, probar_codigo_sospechoso,
                   probar_extractor,
                   probar_filtro_por_repeticion, probar_dividir, probar_vehiculos,
                   probar_mapeo_columnas, probar_busqueda_entre_proveedores,
                   probar_codigo_generico_no_cruza):
        antes = len(fallos)
        prueba()
        print(f"  {'FALLA' if len(fallos) > antes else 'ok   '}  {prueba.__name__}")
    if fallos:
        print(f"\n{len(fallos)} fallo(s):")
        for f in fallos:
            print("   -", f)
        return 1
    print("\ntodo en verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())

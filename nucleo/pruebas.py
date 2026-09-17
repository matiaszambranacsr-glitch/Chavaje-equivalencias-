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
    # «140E24» y «1984E0» se agregaron después, y no salieron de pensar casos: se buscó un
    # código del catálogo tal cual estaba cargado y el buscador dijo que no existía. Estaba
    # guardado con codigo_clean = '139999999999999999798673408'.
    for real in ("233900E010", "2263051E00", "2263051E10", "1E0318760", "5960E6", "123456E7",
                 "140E24", "1984E0", "1267E3", "3322085E00"):
        igual(codigos.sanitizar(real), real, f"«{real}» es un código, no notación científica")
        cierto(not codigos.codigo_sospechoso(real, "")[0],
               f"«{real}» no se puede marcar como número roto")

    # Limpiar lo ya limpio no puede cambiar nada. De esto depende la pantalla que encuentra los
    # productos con el código de búsqueda viejo: compara lo guardado contra sanitizar(crudo), y
    # si la función no fuera estable marcaría filas sanas para siempre. Comprobado además
    # contra los 61.574 códigos del catálogo real: cero diferencias.
    for x in ("233900E010", "0221504036", "W712/94", "2776400.0", "FLO35122A", "26001FISPA",
              "TH9207.80J", "BI1043MMR", "140E24", "0001218760"):
        una = codigos.sanitizar(x)
        igual(codigos.sanitizar(una), una, f"sanitizar() es estable sobre «{x}»")


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

    # Cuando el proveedor DECLARA que lo que sigue es el código de fábrica —«// », «Nº ORIG»,
    # «REF ORIG»—, las reglas que existen para adivinar tienen que aflojarse: si no, se
    # descarta justo el mejor dato que trae la lista. Son 172 códigos reales en cinco listas.
    declarados = [
        ("JTA SCANIA 113 Nº ORIG 287559", "287559"),      # seis dígitos: el mínimo es siete
        ("TERMOSTATO 505 // 134048", "134048"),
        ("APRIETE VALVULAS // 006073", "006073"),
        ("O-RING TRANSIT // ERR4685B", "ERR4685B"),        # Land Rover, no un código de motor
        ("BOMBA REF ORIG 0360601402", "0360601402"),
    ]
    for texto, esperado in declarados:
        got = codigos.extraer_codigos_de_texto(texto)
        cierto(esperado in got, f"el proveedor declaró {esperado} en «{texto[:40]}» y no se tomó: {got}")
    # ...pero un rango de años o una medida no dejan de serlo porque los declaren
    for texto in ("FILTRO ORIGINAL 1998-2006", "JUNTA // 14X20X1", "TAPA // 2003-2008",
                  "SENSOR // A3-A4-A6", "BOBINA ORIG 16VREF"):
        cierto(not codigos.extraer_codigos_de_texto(texto),
               f"«{texto}» es texto aunque esté declarado")
    # ...y sin marcador, las formas ambiguas se siguen rechazando
    for texto in ("TERMOSTATO Motor XU7JP4", "SENSOR MR20DE", "BUJIA ERR4685B"):
        cierto(not codigos.extraer_codigos_de_texto(texto),
               f"«{texto}» no está declarado: la forma ambigua manda")

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


def probar_precision_del_rubro():
    """Las tres cosas que decidían mal si dos repuestos son de la misma clase.

    Se midieron sobre los 24.774 vínculos reales del catálogo: los marcados como «nombre de
    pieza muy distinto» bajaron de 963 a 608 y los de «rubro distinto» de 127 a 116, y en el
    camino aparecieron 7 vínculos realmente malos que estaban tapados."""
    # 1) El plural. «FILTROS PARA COMBUSTIBLE» caía afuera porque la clave dice «FILTRO».
    igual(vehiculos.clasificar_repuesto("FILTROS PARA COMBUSTIBLE 14002 FIAT PALIO"), "Filtros",
          "el plural de la clave también cuenta")
    igual(vehiculos.clasificar_repuesto("Filtros inyector - 10 Juegos MPI BOSCH"), "Filtros",
          "«Filtros inyector» es un filtro, no combustible")

    # 2) El nombre de la pieza: sin códigos y con las abreviaturas del proveedor.
    igual(vehiculos._nombre_de_la_pieza("CABLE DE BUJIA LEIHTV28ST"),
          vehiculos._nombre_de_la_pieza("KIT CAB Y BUJ (LEIHTV28ST)") - {"KIT"},
          "«CAB BUJ» es «CABLE BUJIA»")
    cierto(not any(any(ch.isdigit() for ch in x)
                   for x in vehiculos._nombre_de_la_pieza("BOMBA ELECTRICA 64033 FIAT")),
           "el número de parte no es parte del nombre de la pieza")
    cierto(vehiculos._parecido_nombre_pieza(
               "BUJIA NAFTA LSPFR6F11 HONDA CIVIC",
               "KIT CAB Y BUJ (LEIHTT66SC/LSPFR6F11) FIAT PALIO") >= 0.3,
           "dos formas de escribir lo mismo se tienen que parecer")
    # y lo que de verdad es distinto tiene que seguir dando bajo
    cierto(vehiculos._parecido_nombre_pieza(
               "FILTRO PARA COMBUSTIBLE 14101 RENAULT SCENIC",
               "SENSOR MAP 40024 VW GOL") < 0.3,
           "un filtro y un sensor no se pueden parecer")

    # 3) Un kit trae varias piezas: pedirle UNA familia y castigar por eso es inventar.
    igual(vehiculos.familia_para_comparar("KIT CAB Y BUJ (LEIHTT06SC/LSPKR6E) FIAT PALIO"),
          "Sin clasificar", "un kit de cables y bujías no tiene una sola familia")
    cierto(vehiculos.familia_para_comparar("KIT DE EMBRAGUE VALEO FIAT PALIO") != "Sin clasificar",
           "un kit de una sola familia sí se puede comparar")
    igual(vehiculos.familia_para_comparar("SENSOR MAP 40024 VW GOL"),
          vehiculos.clasificar_repuesto("SENSOR MAP 40024 VW GOL"),
          "lo que no es kit se clasifica igual que siempre")


def probar_comodines_y_kits():
    """Dos cosas que se rompen en silencio: los comodines del SQL y qué es un kit."""
    # En SQL, % y _ son comodines. Si llegan desde el buscador, la consulta deja de buscar lo
    # que se escribió: sobre el catálogo real, «100%» y «f_ltro» devolvían las 200 filas del
    # tope, ninguna relacionada. Y «aceite 100% sintético» es lo que dice la caja.
    igual(codigos.como_texto_en_like("100%"), "100\\%", "el % se escapa")
    igual(codigos.como_texto_en_like("f_ltro"), "f\\_ltro", "el _ se escapa")
    igual(codigos.como_texto_en_like("a\\b"), "a\\\\b", "la barra invertida también")
    igual(codigos.como_texto_en_like(None), "", "None no rompe")

    # Qué cuenta como kit, que es lo que decide si se ofrece «también viene en kit».
    for kit in ("KIT CAB Y BUJ (LEIHTT06SC/LSPKR6E) FIAT PALIO",
                "JUEGO DE JUNTAS MOTOR FIAT", "Jgo.Jtas.P/Motor NISSAN", "COMBO 3 FILTROS"):
        cierto(vehiculos.es_un_kit(kit), f"«{kit[:28]}» es un kit")
    for suelto in ("CABLE DE BUJIA LEIHTT06SC Fiat Palio", "BULBO DE TEMPERATURA PEUGEOT 505",
                   "SENSOR MAP 40024 VW GOL"):
        cierto(not vehiculos.es_un_kit(suelto), f"«{suelto[:28]}» no es un kit")


def probar_marcas_de_vehiculo():
    """Una descripción de proveedor nombra varios autos, y las listas abrevian.

    Los dos casos que arreglaron la pantalla de vehículos: «VW» no estaba en la lista de
    marcas —5.530 descripciones lo escriben así y ninguna dice VOLKSWAGEN— y de una
    descripción con varias marcas se tomaba una sola, elegida por el largo del nombre."""
    igual([m for m, _c, _r in vehiculos.marcas_vehiculo_en(
               "BUJIA NAFTA Ford Escort - VW Gol - Kombi")],
          ["FORD", "VOLKSWAGEN"], "las dos marcas, y VW es VOLKSWAGEN")
    igual([m for m, _c, _r in vehiculos.marcas_vehiculo_en(
               "BULBO TEMPERATURA PEUGEOT 405 - CITROEN ZX")],
          ["PEUGEOT", "CITROEN"], "el orden es el del texto, no el del largo del nombre")
    # el tramo de cada marca llega hasta la siguiente
    igual(dict((m, r) for m, _c, r in vehiculos.marcas_vehiculo_en(
               "BUJIA Ford Escort - VW Gol")).get("VOLKSWAGEN"), "Gol",
          "a cada marca le toca su propio modelo")
    igual(vehiculos.marcas_vehiculo_en("MANGUERA DE RADIADOR 1 6")[:1], [],
          "MANGUERA no es la marca MAN")
    igual(vehiculos.marcas_vehiculo_en("RAMPA DE INYECCION 1 6")[:1], [],
          "RAMPA no es la marca RAM")
    # alias: una sola marca aunque se escriba de varias formas
    igual([m for m, _c, _r in vehiculos.marcas_vehiculo_en("TAPA M.BENZ SPRINTER")],
          ["MERCEDES BENZ"], "M.BENZ es MERCEDES BENZ")
    cierto(not vehiculos.es_nombre_de_modelo("A0091547202"), "un número de parte no es modelo")
    cierto(not vehiculos.es_nombre_de_modelo("EA011610461"), "otro número de parte tampoco")
    cierto(vehiculos.es_nombre_de_modelo("F-250"), "F-250 sí es un modelo")
    cierto(vehiculos.es_nombre_de_modelo("COROLLA"), "COROLLA sí es un modelo")
    cierto(vehiculos.es_nombre_de_modelo("C20NE"), "un código de motor corto se conserva")


def probar_ref_pegado():
    """«REF ORIG» pegado a la palabra anterior. Aparece 9.038 veces en las listas reales.

    Importa por dos motivos: tapa el marcador que dice explícitamente cuál es el código de
    fábrica, y de paso genera códigos fantasma («10001REF», «L=515MMREF»). Despegarlo sacó
    461 códigos inventados de las descripciones reales, y ninguno de los 461 era de verdad."""
    igual(vehiculos.separar_texto_pegado("Passat 1 8 98REF ORIG 030121121B"),
          "Passat 1 8 98 REF ORIG 030121121B", "despegar REF del token anterior")
    igual(vehiculos.separar_texto_pegado("SENSOR 16VREF ORIG 0280155868"),
          "SENSOR 16V REF ORIG 0280155868", "16VREF es 16V + REF")
    # sin ORIG detrás no se toca: podría ser un código que termina en REF
    igual(vehiculos.separar_texto_pegado("CODIGO ABC123REF de catalogo"),
          "CODIGO ABC123REF de catalogo", "sin ORIG detrás, REF no se despega")
    # y el resultado: el código de fábrica sale y la basura no
    cierto("030121121B" in codigos.extraer_codigos_de_texto(
               vehiculos.separar_texto_pegado(
                   "CARCASA TERMOSTATO Volkswagen Passat 1 8 98REF ORIG 030121121B")),
           "el código declarado detrás de REF ORIG se reconoce")
    for basura in ("SENSOR ABS CITROEN BERLINGO TRASERO L=1010MMREF ORIG 4545E8",
                   "CABLE BUJIA 1060MM JUEGO",
                   "JUNTA MOTOR 1600-1800-2000cc"):
        for cod in codigos.extraer_codigos_de_texto(vehiculos.separar_texto_pegado(basura)):
            cierto(not cod.upper().endswith("REF") and "MM" not in cod.upper()
                   and not cod.lower().endswith("cc"),
                   f"«{cod}» no debería salir de «{basura[:34]}»")


def probar_familias_de_pieza():
    """La familia de la pieza es lo que usa el detector de puentes falsos para darse cuenta de
    que un código está uniendo repuestos que no tienen nada que ver, y también vale −40 en la
    confianza de un vínculo. Cuando una descripción cae en «Sin clasificar», esas dos cosas se
    quedan sin evidencia — por eso estos casos están clavados acá.

    Los de abajo salieron de las listas reales: son las formas que más aparecían entre las
    25.112 descripciones que antes no se clasificaban."""
    casos = [
        # El punto pegado de las abreviaturas de proveedor (1.332 productos decían esto)
        ("JTA.TAPA CIL. FORD FALCON", "Juntas y retenes"),
        ("Jgo.Jtas.P/Motor c/Retenes MAZDA B-2900", "Juntas y retenes"),
        ("Cpo.Acel. M.BENZ CLS350", "Combustible"),
        # Familias que faltaban enteras
        ("BULBO DE TEMPERATURA PEUGEOT 505", "Eléctrico y encendido"),
        ("INTERRUPTOR STOP M.BENZ 1214", "Eléctrico y encendido"),
        ("LLAVE TECLA Fiat UNO FARO", "Eléctrico y encendido"),
        ("MOTOR PASO/PASO FIAT PALIO", "Eléctrico y encendido"),
        ("CUERPO MARIPOSA Chevrolet CORSA", "Combustible"),
        ("SURTIDOR WEBER 30 DIC", "Combustible"),
        ("BOMBA ELECTRICA 64044 Nissan D21", "Combustible"),
        ("CANO Fiat DUNA salida filtro de aire", "Caños y mangueras"),
        ("COOLER DE ACEITE VW AMAROK", "Refrigeración"),
        ("ACTUADOR HIDRAULICO EMBRAGUE RENAULT", "Embrague"),
        # Y que las claves nuevas no le ganen a las que ya estaban (gana la más larga)
        ("TUBO DE ESCAPE VW GOL", "Escape"),
        ("MANGUERA DE RADIADOR PALIO", "Refrigeración"),
        ("TUBO CALEFACTOR PEUGEOT 307", "Climatización"),
        ("CANO DE ESCAPE FIAT UNO", "Escape"),
        ("PASTILLAS DE FRENO CORSA", "Frenos"),
        ("FILTRO DE AIRE 4RUNNER", "Filtros"),
    ]
    for texto, esperada in casos:
        igual(vehiculos.clasificar_repuesto(texto), esperada, f"familia de «{texto[:40]}»")


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
    # El caso que se veía en el mostrador como «no hace las equivalencias»: un producto cuyo
    # único código de fábrica es el código de barras del propio proveedor. La equivalencia
    # está cargada, pero no cuelga nada más, así que no lleva a ninguna otra marca.
    taranto = marca("MOTORARG")
    p_junta = producto(taranto, "321607", "Jta.Tapa Cilind.Ford Focus / Fiesta")
    p_barras = producto(oem, "7793960016251", "Jta.Tapa Cilind.Ford Focus / Fiesta")
    vincular(p_junta, p_barras)
    # Y el mismo repuesto con el código de barras donde va: en su propia columna.
    cur.execute("UPDATE productos SET codigo_barras = ? WHERE id = ?", ("7791234567890", p_jl))
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


def probar_codigo_de_barras_no_es_equivalencia():
    """Un código de fábrica que no cuelga nada más no puede presentarse como equivalencia."""
    con, cur = base_de_prueba()
    res = equivalencias.buscar_por_codigo(cur, codigos.sanitizar("321607"))
    igual(len(res), 2, "aparece el buscado y su código de barras")
    barras = [f for f in res if f["Codigo"] == "7793960016251"][0]
    cierto(barras["_sin_salida"], "el código de barras queda marcado como sin salida")
    cierto("nadie más lo tiene" in barras["Cadena"],
           f"la columna Cadena tiene que decirlo; dice {barras['Cadena']!r}")
    igual(barras["Confianza"], "", "sin salida no lleva confianza")
    igual(barras["Nivel"], "", "sin salida no lleva nivel")
    # Y el que SÍ cruza tiene que seguir mostrándose como antes.
    res2 = equivalencias.buscar_por_codigo(cur, codigos.sanitizar("624FISPA"))
    jl = [f for f in res2 if f["Marca"] == "JL"][0]
    cierto(not jl["_sin_salida"], "un equivalente de verdad no se marca como sin salida")
    igual(jl["Confianza"], "🟢 sólida", "el equivalente de verdad conserva su confianza")
    con.close()


def probar_columna_de_codigo_de_barras():
    """Reconocer la columna de código de barras ANTES de importarla como código de fábrica."""
    barras = [f"779396{n:07d}" for n in range(1, 61)]
    es, prefijo, _ = codigos.columna_es_codigo_de_barras(barras)
    cierto(es, "60 números de 13 dígitos con el mismo prefijo son códigos de barras")
    cierto(prefijo.startswith("779396"), f"tiene que decir el prefijo; dijo {prefijo!r}")
    # Códigos de fábrica de verdad: tienen letras, largos distintos, y no arrancan todos igual.
    reales = ["036115561G", "7700274177", "1109AH", "0451103316", "03C906433A", "55575988CA",
              "6Q0407365", "2H0919050B", "8200768913", "04E115561H", "1109CL", "LR004459",
              "MD972015", "55557300", "93745292", "96476884", "7701478031", "1651076J00",
              "0K2A114302", "281132E000", "77362191", "9091901210", "1338143", "0280142300"]
    es2, _, _ = codigos.columna_es_codigo_de_barras(reales)
    cierto(not es2, "una columna de códigos de fábrica de verdad no se confunde")
    es3, _, _ = codigos.columna_es_codigo_de_barras(["7793960016251", "7793960024980"])
    cierto(not es3, "con dos valores no alcanza para afirmarlo")


def probar_codigo_conocido_gana_a_la_forma():
    """Si alguien lo vende, es un código — aunque tenga forma de motorización."""
    desc = "JTA TAPA CILINDROS FORD FOCUS FIESTA TC-936-MG"
    igual(codigos.extraer_codigos_de_texto(desc), [],
          "sin catálogo, TC-936-MG se descarta por tener forma de código de motor")
    igual(codigos.extraer_codigos_de_texto(desc, codigos_conocidos={"TC936MG"}), ["TC-936-MG"],
          "si está cargado como producto, se toma")
    # Lo que el desempate NO tiene que reabrir: una motorización no la vende nadie, así que
    # nunca va a estar en el catálogo y sigue afuera.
    igual(codigos.extraer_codigos_de_texto("TERMOSTATO PEUGEOT 307 XU10J4R 2.0",
                                           codigos_conocidos={"TC936MG"}), [],
          "una motorización sigue descartada")
    # Y tampoco afloja el largo mínimo de los códigos de solo números: '260035' es la medida
    # 5/16 pegada al código, y da la casualidad de que existe como código de otra lista.
    igual(codigos.extraer_codigos_de_texto("CONECTOR PARA MANGUERA 260035 16 X 5 16 Liso",
                                           codigo_propio="26003FISPA",
                                           codigos_conocidos={"260035"}), [],
          "estar en el catálogo no vuelve código a un número corto pegado a una medida")


def probar_todos_los_autos_de_una_descripcion():
    """Una descripción que nombra cuatro autos tiene que dar los cuatro, cada uno con SU texto.

    Es el caso que rompía las aplicaciones deducidas. Sobre esta descripción real:
      «BULBO DE PRESION DE ACEITE 304VW Passat - Santana - Gol - ALFA ROMEO 155 T Spark -
       FORD Galaxy - Escort - SEAT Toledo»
    se guardaba UN solo auto, así que el repuesto desaparecía del catálogo de los otros tres."""
    desc = ("BULBO DE PRESION DE ACEITE 304VW Passat 1 6 tdi - Santana 1 8 - Gol - Saveiro "
            "ALFA ROMEO 155 T Spark 8V - FORD Galaxy - Escort - SEAT Toledo 1 6")
    marcas = [m for m, _c, _r in vehiculos.marcas_vehiculo_en(desc)]
    for esperada in ("VOLKSWAGEN", "ALFA ROMEO", "FORD", "SEAT"):
        cierto(esperada in marcas, f"{esperada} tiene que estar; salieron {marcas}")
    # Y a cada una le toca su propio pedazo, no el de la de al lado.
    tramos = {m: (r or "") for m, _c, r in vehiculos.marcas_vehiculo_en(desc)}
    cierto("Galaxy" in tramos.get("FORD", ""), f"a FORD le toca Galaxy; le tocó {tramos.get('FORD')!r}")
    cierto("Toledo" in tramos.get("SEAT", ""), f"a SEAT le toca Toledo; le tocó {tramos.get('SEAT')!r}")


def probar_marca_corta_pegada_a_un_numero():
    """«FI-IWP041VW Gol» — la marca pegada al código sin espacio.

    Las marcas de dos y tres letras no se despegan en general, a propósito: un «VW» suelto se
    mete adentro de cualquier palabra. Pero con un dígito justo antes no hay ambigüedad, y son
    1.150 descripciones reales. No es cosmético: de ahí sale el código de fábrica, y sin
    separar el código que se leía era IWP041VW en vez de IWP041."""
    igual(vehiculos.separar_texto_pegado("INYECTOR FI-IWP041VW Gol 1.0 16V"),
          "INYECTOR FI-IWP041 VW Gol 1.0 16V", "el VW pegado al código se despega")
    igual(codigos.extraer_codigos_de_texto(
              vehiculos.separar_texto_pegado("INYECTOR FI-IWP041VW Gol 1.0 16V")),
          ["FI-IWP041"], "y entonces el código que se lee es el bueno")
    igual(vehiculos.separar_texto_pegado("SONDA LAMBDA 80034GM ASTRA 1 8"),
          "SONDA LAMBDA 80034 GM ASTRA 1 8", "lo mismo con GM")
    # Lo que no se toca: un error de tipeo del proveedor no se parte en dos.
    igual(vehiculos.separar_texto_pegado("KIT DE DISTRIBUCION LKTCN1007TOYOYA AVENSIS"),
          "KIT DE DISTRIBUCION LKTCN1007TOYOYA AVENSIS",
          "«TOYOYA» es un error de tipeo, no la marca TOY pegada")


def probar_marcas_de_repuesto_pegadas_al_codigo():
    """«BOSCHF1003», «MPFIMARELLIF1011»: la marca del repuesto pegada al código.

    Sale de las listas y se lleva puesto el código: esos dos están cargados en la base como si
    fueran códigos de fábrica de Bosch y de Marelli. Se despegan igual que las marcas de auto.
    Medido sobre las 46.644 descripciones de proveedor: saca 35 códigos inventados y RECUPERA
    6 que estaban enterrados adentro del nombre de la marca."""
    for pegado, esperado in (
            ("MULTIPUNTO BOSCHF1003", "MULTIPUNTO BOSCH F1003"),
            ("MULTIPUNTO - MPFIMARELLIF1011", "MULTIPUNTO - MPFI MARELLI F1011"),
            ("MAGNETI MARELLIFORDF1101", "MAGNETI MARELLI FORD F1101")):
        igual(vehiculos.separar_texto_pegado(pegado), esperado, f"«{pegado}» se despega")
    # Y entonces deja de entrar como código de fábrica.
    for texto in ("KIT FILTROS Y O RINGS 11044PUNTAS INFERIORES MULTIPUNTO BOSCHF1003",
                  "KIT FILTROS 11030PUNTA INFERIORMULTIPUNTO - MPFIMARELLIF1011"):
        igual(codigos.extraer_codigos_de_texto(vehiculos.separar_texto_pegado(texto)), [],
              f"«{texto[:40]}» no tiene ningún código de fábrica adentro")


def probar_camiones_y_motorizaciones_no_son_codigos():
    """«F14000» es el camión y «6CTA8.3» el motor Cummins, no códigos de fábrica.

    El F14000 estaba cargado como código de fábrica uniendo un FILTRO DE COMBUSTIBLE con un
    CILINDRO MAESTRO, y el F4000 un filtro con un sensor de nivel. Aparecen en 148 y 123
    descripciones del catálogo real."""
    for texto in ("Despiece AGRALE O RING VIBRATORIO CHF AUTOELEVADOR F11000 F14000",
                  "Despiece CUMMINS BUS CAMION AGRICOLA C F14000 6CTA8.3",
                  "FILTRO COMB M.BENZ - FORD F100/F14000/F4000-CASE"):
        igual(codigos.extraer_codigos_de_texto(texto), [],
              f"«{texto[:44]}» son camiones y motores, no códigos")
    # Y los códigos de verdad que están al lado tienen que seguir saliendo.
    for texto, esperado in (
            ("Despiece FORD BOMBA ACEITE SERIE B F100 3931350 5264569 4BTA3.9", "3931350"),
            ("Despiece CHEVROLET VECTRA ZAFIRA ASTRA F14000 3910824", "3910824"),
            ("Despiece CUMMINS 3914388 TUBO DRENAJE ACEITE SERIE B F100", "3914388")):
        cierto(esperado in codigos.extraer_codigos_de_texto(texto),
               f"«{esperado}» sí es un código y tiene que salir de «{texto[:40]}»")


def probar_kit_que_trae_la_pieza():
    """Uno viene adentro del otro: eso NO es una equivalencia, y hay que saber decirlo.

    La bujía está adentro del «KIT CAB Y BUJ», la bomba de agua adentro de «DISTRIBUCION
    C/BOMBA». Los rubros no coinciden —una bujía no es un juego de cables— y aun así «rubros
    distintos» no describe lo que pasa: la relación es de verdad, solo que no es de
    intercambio. Sobre los 208 vínculos cargados con rubros distintos, 126 son de esta clase."""
    # Un kit que no dice la palabra «kit»: nombra los dos códigos que trae, sumados.
    cierto(vehiculos.es_un_kit("DISTRIBUCION C/BOMBA (LKTBN336 + LWPN007 )Citroen Berlingo"),
           "«(COD1 + COD2)» es un kit aunque no diga la palabra")
    # Lo que NO puede confundirse: así lista Illinois los códigos de fábrica de UNA pieza.
    cierto(not vehiculos.es_un_kit("Junta Tapa de Cilindros CUMMINS NT310 (3036100/3411461)"),
           "«(COD1/COD2)» son dos códigos de fábrica de la misma pieza, no un kit")
    cierto(vehiculos.es_un_kit("KIT CAB Y BUJ (LEIHTT66SC/LSPFR6F11) FIAT PALIO"),
           "y el que sí dice KIT sigue siendo kit")


def probar_vocabulario_de_pieza():
    """Las tres listas de palabras tienen que decir cada una lo suyo.

    firma_de_producto() parte el núcleo en QUÉ PIEZA ES y PARA QUÉ AUTO ES usando estos
    conjuntos, así que si se mezclan vuelve el error que tenían las sugerencias por
    descripción: comparar dos repuestos por los modelos de auto que nombran."""
    # Las marcas de repuesto no dicen qué pieza es
    for marca in ("BOSCH", "NGK", "VALEO", "MAGNETI"):
        cierto(marca in vehiculos.MARCAS_DE_REPUESTO, f"{marca} es marca de repuesto")
        cierto(marca in vehiculos.PALABRAS_NO_MODELO, f"{marca} tampoco es un modelo de auto")
    # El contexto (qué vehículo es) no dice qué pieza es
    for ctx in ("PICK", "UP", "CAMION", "TRACTOR", "CARGO", "DIESEL"):
        cierto(ctx in vehiculos.PALABRAS_DE_CONTEXTO, f"{ctx} es contexto, no pieza")
        cierto(ctx in vehiculos.PALABRAS_NO_MODELO, f"{ctx} tampoco es un modelo de auto")
    # Y los nombres de pieza no pueden estar en ninguno de los dos
    for pieza in ("JUNTA", "TAPA", "CILINDROS", "VALVULAS", "CARTER", "BOMBA", "CARBURADOR"):
        cierto(pieza in vehiculos.PALABRAS_NO_MODELO, f"{pieza} no es un modelo de auto")
        cierto(pieza not in vehiculos.MARCAS_DE_REPUESTO
               and pieza not in vehiculos.PALABRAS_DE_CONTEXTO,
               f"{pieza} SÍ dice qué pieza es: no puede estar en las otras dos listas")


def probar_abreviaturas_de_las_listas_reales():
    """Cada proveedor abrevia distinto la misma pieza y hay que poder compararlas.

    Los casos salen de las dos listas de juntas: Taranto escribe «Jta.Tapa Cilind.Ford» e
    Illinois «Junta Tapa de Cilindros FORD». Sin expandir, una pieza es JTA y la otra JUNTA."""
    for abreviado, entero in (("JTA", "JUNTA"), ("CILIND", "CILINDRO"), ("CILIN", "CILINDRO"),
                              ("CIL", "CILINDRO"), ("VAL", "VALVULA"), ("VALV", "VALVULA"),
                              ("JGO", "JUEGO"), ("BBA", "BOMBA")):
        igual(vehiculos.ABREVIATURAS_DE_PIEZA.get(abreviado), entero,
              f"«{abreviado}» tiene que expandirse a «{entero}»")
    # Y que sirva de punta a punta: las dos formas de nombrar la misma junta tienen que dar
    # el mismo nombre de pieza.
    taranto = vehiculos._nombre_de_la_pieza("Jta.Tapa Cilind.Ford Focus / Fiesta")
    illinois = vehiculos._nombre_de_la_pieza("Junta Tapa de Cilindros FORD FOCUS FIESTA")
    cierto(len(taranto & illinois) >= 2,
           f"las dos formas de escribir «junta tapa de cilindros» tienen que coincidir; "
           f"dieron {sorted(taranto)} y {sorted(illinois)}")


def probar_busqueda_por_codigo_de_barras():
    """Escanear la caja tiene que traer el repuesto Y sus equivalencias.

    Es la mitad que no se puede perder al sacar el EAN de la red de equivalencias: antes el
    código de barras se cargaba como un código de fábrica, y eso lo hacía buscable al precio de
    inventar un vínculo por producto. Ahora vive en productos.codigo_barras y la búsqueda
    arranca mirando esa columna también."""
    con, cur = base_de_prueba()
    res = equivalencias.buscar_por_codigo(cur, "7791234567890")
    cierto(res, "escanear el código de barras tiene que encontrar algo")
    propio = [f for f in res if f["Cadena"] == "— el buscado"]
    igual(len(propio), 1, "el producto escaneado es «el buscado», no un resultado más")
    igual(propio[0]["Codigo"], "WS3171", "y es el repuesto, no un producto fantasma")
    # Y trae la red entera: el de JL está vinculado al OEM 25186240, y por ahí al de FISPA.
    marcas = {f["Marca"] for f in res}
    cierto("FISPA" in marcas,
           f"escanear tiene que traer también los equivalentes; trajo {sorted(marcas)}")
    con.close()


def probar_modelos_y_motores_no_son_codigos_de_fabrica():
    """Una lista de juntas metía en la columna de OEM el modelo de la máquina o el motor.

    Salió de mirar la pantalla de puentes falsos sobre la base del negocio: «6PF-305» (un motor
    Perkins), «SUPER5» (un Renault), «308HDI» (un Peugeot), «L75-L76» (un Scania), «C1J-C1L»
    (motores Renault), «182.A8000» (un motor Fiat). Cada uno colgaba de sí mismo todo lo que lo
    nombrara: solo «6PF-305» aparece en 42 descripciones del catálogo real, o sea 861 pares de
    productos hermanados por compartir el motor y nada más.

    Lo que hay que cuidar es el otro lado, y por eso está acá: dos de las formas parecidas SON
    códigos de verdad. «55PP27-01» es un sensor de presión Bosch y «1201-K1» una bomba de agua
    Citroën. Cualquier regla que los toque hace más daño del que arregla — se midió contra los
    21.734 códigos OEM con vínculos del catálogo real y ninguna de las reglas nuevas le pega a
    uno que citen dos proveedores distintos."""
    def saca(texto):
        return codigos.extraer_codigos_de_texto(texto)

    igual(saca("Jgo.Jtas.Carter PERKINS 6PF-305"), [], "un motor Perkins no es un código")
    igual(saca("Jta.Tapa Cil. RENAULT R5 SUPER5"), [], "«SUPER5» es el modelo del Renault")
    igual(saca("JTC PEUGEOT 308HDI/308 2.0HDI"), [], "«308HDI» es el modelo con la motorización")
    igual(saca("Jta.Carter SCANIA L75-L76"), [], "dos modelos del mismo prefijo, no un código")
    igual(saca("Jgo.Jtas.Motor RENAULT C1J-C1L"), [], "dos motores del mismo prefijo")
    igual(saca("Jta.Tapa Valvulas FIAT 182.A8000"), [], "el número de motor que Fiat pone en el block")
    igual(saca("Jgo de motor KOMATSU 4D105-3"), [], "un motor Komatsu")
    igual(saca("Jgo juntas motor John Deere 3350-3550-650-6600-7500"), [],
          "cinco modelos encadenados no son un código")
    igual(saca("Jta.Tapa Cil.Esp.1,50 RODILLO"), [], "«Cil.Esp.1» es la descripción abreviada")

    # Y LO QUE NO SE PUEDE ROMPER. Si alguna de estas falla, la regla nueva está de más:
    # cada uno de estos códigos es un puente real entre dos listas de proveedor.
    igual(saca("SENSOR PRESION COMBUSTIBLE REF ORIG 55PP27-01"), ["55PP27-01"],
          "«55PP27-01» es un sensor de presión Bosch, no un motor")
    igual(saca("BOMBA DE AGUA CITROEN C4 REF ORIG 1201-K1"), ["1201-K1"],
          "«1201-K1» es una bomba de agua Citroën")
    igual(saca("TERMOSTATO PEUGEOT 206 REF ORIG 1336-Y80"), ["1336-Y80"],
          "«1336-Y80» es un termostato Peugeot")
    igual(saca("SENSOR MAP PALIO Fiorino TPRT05 THOMSON"), ["TPRT05"],
          "«TPRT05» es un sensor Thomson: se parece a un modelo pero no tiene vocales, y por "
          "ahí se lo distingue de SCENIC2 o MEGANE2")
    igual(saca("ROTULA VW GOL ORIG 6Q0407365"), ["6Q0407365"], "un código VW de toda la vida")


def probar_lo_que_excel_le_come_a_un_codigo_largo():
    """Excel rompe los números largos al guardar, y el resultado parece correcto.

    Es el error más caro que puede entrar por un archivo porque no se ve. Excel muestra los
    números de más de once dígitos en notación científica y, al guardar un CSV, escribe lo que
    muestra: el código de barras 7793960026946 sale del archivo como «7.79396E+12». Los últimos
    siete dígitos ya no están.

    Y reconstruirlo da 7793960000000 — trece dígitos, el prefijo argentino correcto, forma de
    código de barras perfecta. Se cargaba sin una queja y desde el mostrador se veía como «el
    escáner no encuentra nada», sin ninguna pista de por qué.

    La contracara importa igual o más: «233900E010» es el filtro de combustible Toyota
    23390-0E010 y NO es notación científica. Hay 283 códigos de esa forma en las listas reales,
    y marcarlos como rotos sería romper lo que hoy anda. Lo que los separa es el signo del
    exponente, que Excel siempre escribe y un código de fábrica nunca."""
    cierto(codigos.excel_le_comio_digitos("7.79396E+12"),
           "un código de barras truncado por Excel tiene que detectarse")
    cierto(codigos.excel_le_comio_digitos("7,79396E+12"),
           "y también con la coma decimal que usa el Excel en español")
    cierto(codigos.excel_le_comio_digitos("1.09E+11"), "lo mismo con un código de fábrica largo")

    cierto(not codigos.excel_le_comio_digitos("233900E010"),
           "«233900E010» es el Toyota 23390-0E010, no una notación científica: sin signo en el "
           "exponente no hay nada roto")
    cierto(not codigos.excel_le_comio_digitos("7793960026946"),
           "un código de barras entero no está roto")
    cierto(not codigos.excel_le_comio_digitos("2.5E+3"),
           "2.5E+3 son exactamente 2500: no se inventó ningún dígito que importe")
    cierto(not codigos.excel_le_comio_digitos("IWP065"), "un código común no es notación científica")
    cierto(not codigos.excel_le_comio_digitos(""), "y con la celda vacía no hay nada que decidir")

    # Y esto es lo que hace el daño: el número roto se limpia a algo que PARECE perfecto.
    igual(codigos.sanitizar("7.79396E+12"), "7793960000000",
          "reconstruido da trece dígitos con el prefijo correcto — por eso hay que frenarlo "
          "antes, no después")


def probar_el_digito_verificador_del_codigo_de_barras():
    """El dígito verificador separa un código de barras de un número largo cualquiera.

    Importa para el caso que el prefijo común NO agarra: una lista de un revendedor que trae
    productos de veinte fábricas tiene veinte prefijos distintos y ninguno llega al 70%, así que
    la detección por prefijo la deja pasar entera y se cargan miles de equivalencias muertas.
    La cuenta de GS1 la agarra igual.

    Está medido sobre la base real: de los 8.319 códigos largos de MOTORARG —que son códigos de
    barras— cierran los 8.319; de los de FISPA —códigos de fábrica de verdad, largos y
    numéricos— cierra el 13%, que es lo que da el azar.

    Y hay una trampa que ya se pisó: el DUN-14, que es el código de la CAJA. Tratarlo como «un
    EAN-13 con un dígito de agrupación adelante» —sacarle el primero y hacer la cuenta de
    trece— da otro número, y esos 21 códigos de caja de MOTORARG aparecían como mal copiados
    estando perfectos. La norma dice completar con ceros a la izquierda hasta trece y hacer UNA
    sola cuenta para los cuatro largos."""
    igual(codigos.digito_verificador_gtin("779396002694"), "6",
          "la cuenta de GS1 da el dígito que falta")
    igual(codigos.digito_verificador_gtin(""), "", "sin dígitos no hay cuenta que hacer")
    cierto(codigos.codigo_de_barras_cierra("7793960026946"), "un EAN bien copiado cierra")
    cierto(codigos.codigo_de_barras_cierra("96385074"), "un EAN-8 cierra con la misma cuenta")
    cierto(codigos.codigo_de_barras_cierra("045496730086"),
           "y un UPC-A de 12 dígitos también")
    cierto(codigos.codigo_de_barras_cierra("27793960977877"),
           "el DUN-14 de la caja cierra: no es un EAN-13 con un dígito adelante")
    cierto(codigos.codigo_de_barras_cierra("7793960026945") is False,
           "cambiando un dígito deja de cerrar: es lo que detecta un código mal tipeado")
    cierto(codigos.codigo_de_barras_cierra("036115561G") is None,
           "un código de fábrica no es un código mal copiado: es otra cosa, y hay que "
           "poder distinguirlo")

    # El caso que el prefijo no agarra: códigos de barras de fábricas distintas.
    de_varias_fabricas = ["7790396980569", "7892639001397", "4013628164265", "7501031311309",
                          "7793960026946", "7897707516933"] * 5
    es_barras, prefijo, _ = codigos.columna_es_codigo_de_barras(de_varias_fabricas)
    cierto(es_barras, "sin prefijo común, el dígito verificador tiene que delatarlos igual")
    igual(prefijo, "", "y no se inventa un prefijo común que no existe")


def probar_el_pais_del_codigo_de_barras():
    """El prefijo del código de barras dice el país, y hay que leerlo del código ENTERO.

    Lo caro es el UPC-A: son 12 dígitos y equivalen a un EAN-13 con un cero adelante que no está
    escrito. Si se mira el arranque tal cual viene, «045496…» cae en 040-049, que la norma
    reserva para uso interno del comercio, y la app diría que un producto de Estados Unidos es
    una etiqueta que imprimió una balanza. Mirando el código completo, 004 = Estados Unidos.

    También importa lo que NO es un país: si un escaneo da 200-299, ese número no identifica
    ningún repuesto y no tiene sentido salir a buscarlo."""
    igual(codigos.pais_del_codigo_de_barras("7793960026946"), "Argentina",
          "779 es el prefijo argentino")
    igual(codigos.pais_del_codigo_de_barras("7897707516933"), "Brasil", "789 es Brasil")
    igual(codigos.pais_del_codigo_de_barras("045496730086"), "Estados Unidos y Canadá",
          "un UPC-A de 12 dígitos se lee con el cero adelante, no como 045")
    igual(codigos.pais_del_codigo_de_barras("2001234567890"), "uso interno del comercio",
          "200-299 no es un país: es la etiqueta que imprime el comercio")
    cierto(codigos.pais_del_codigo_de_barras("2001234567890") in codigos.GS1_NO_ES_UN_PAIS,
           "y la app tiene que poder distinguir eso de un país de verdad")
    igual(codigos.pais_del_codigo_de_barras("123"), "",
          "con tres dígitos no se puede decir nada")
    # Y por lista: es como se detecta que una lista entera cargó códigos de barras.
    igual(codigos.pais_de_estos_codigos(["7793960026946", "7793960026947", "7793960026948"]),
          "Argentina", "una lista con todos los códigos del mismo prefijo tiene un país")
    igual(codigos.pais_de_estos_codigos(["ABC123", "XYZ"]), "",
          "si no son códigos de barras no se inventa un país")


def probar_la_patente_argentina():
    """Qué se puede leer de una patente sin consultar ninguna base.

    No existe una base pública y gratuita que traduzca patente a vehículo, así que de la
    patente sola nunca va a salir «Gol 1.6». Pero el formato y la serie sí se leen: si es
    Mercosur o vieja, si es auto o moto, de qué provincia salió —las provinciales— y sobre
    todo entre qué años se patentó, que es lo que en el mostrador se pregunta siempre después
    del modelo.

    El año es APROXIMADO y por eso va como rango: lo único seguro es el orden en que se
    entregan las series. La app lo afina después con las fichas del propio taller."""
    igual(vehiculos.leer_patente("AB 123 CD")["formato"], "mercosur", "AB123CD es Mercosur")
    igual(vehiculos.leer_patente("ABC 123")["formato"], "vieja", "ABC123 es la vieja")
    igual(vehiculos.leer_patente("B 123 456")["formato"], "provincial", "B123456 es provincial")
    igual(vehiculos.leer_patente("B123456")["provincia"], "Buenos Aires", "la B es Buenos Aires")
    igual(vehiculos.leer_patente("X123456")["provincia"], "Córdoba", "la X es Córdoba")
    igual(vehiculos.leer_patente("A123BCD")["vehiculo"], "moto", "una letra y tres es moto")
    igual(vehiculos.leer_patente("cualquiera")["formato"], None, "lo que no es patente no lo es")

    # El rango de años no se puede salir del período en que existió cada formato.
    vieja = vehiculos.leer_patente("AAA111")
    cierto(vieja["anio_desde"] >= 1995, "la serie vieja no arranca antes de 1995")
    ultima = vehiculos.leer_patente("PZZ999")
    cierto(ultima["anio_hasta"] <= 2016, "y no llega más allá de marzo de 2016")
    nueva = vehiculos.leer_patente("AA123AA")
    cierto(nueva["anio_desde"] >= 2015, "la Mercosur no existe antes de 2016")

    # Y el orden se respeta: una serie posterior no puede dar un año anterior.
    anteriores = None
    for serie in ("AAA111", "DVX123", "IZT456", "MHG789", "OQP321"):
        actual = vehiculos.leer_patente(serie)["anio_desde"]
        if anteriores is not None:
            cierto(actual >= anteriores, f"{serie} no puede ser más viejo que el anterior")
        anteriores = actual


def probar_bed_ford_no_es_ford():
    """«BED FORD» es el camión Bedford, no un Ford.

    Son 147 descripciones que lo escriben partido, y la marca no estaba en la lista: de todas
    ellas la app leía FORD, así que una junta de diferencial de un camión Bedford quedaba
    emparejada con repuestos de un Fiesta «porque coinciden en FORD». Gana la marca más larga
    porque la lista se ordena por largo."""
    hallado = vehiculos.marcas_vehiculo_en("Juntas para diferencial BED FORD EATON 162 GRANDE")
    igual([m for m, _c, _r in hallado], ["BEDFORD"], "BED FORD es Bedford, no Ford")
    hallado = vehiculos.marcas_vehiculo_en("JUNTA TAPA CILINDROS FORD FIESTA")
    igual([m for m, _c, _r in hallado], ["FORD"], "y un Ford sigue siendo un Ford")


def probar_la_marca_abreviada_es_la_misma_marca():
    """CHEV y CHEVROLET son la misma marca, y hasta ahora no lo eran para la firma.

    La firma buscaba cada marca como subcadena, sin resolver los alias, así que dos proveedores
    que abrevian distinto —«Chev Corsa» contra «CHEVROLET CORSA»— daban «autos distintos» y el
    par se rechazaba antes de mirar nada más. Son 3.705 descripciones del catálogo real."""
    for escrito, canonica in (("Ficha para sensor Chev Corsa", "CHEVROLET"),
                              ("RESISTOR PEUG 206 1 6", "PEUGEOT"),
                              ("RESISTOR CITR C3 AIRCROSS", "CITROEN"),
                              ("BUJIA VW Gol refrigerado", "VOLKSWAGEN")):
        igual([m for m, _c, _r in vehiculos.marcas_vehiculo_en(escrito)], [canonica],
              f"«{escrito.split()[-2]}» es {canonica}")


def probar_ref_orig_pegado_no_es_codigo():
    """«505REF» no es un código: es el modelo 505 con el «REF» de «REF ORIG» pegado atrás.

    Una de las listas escribe así 9.038 veces. La regla que lo despega ya existía para la
    pantalla de vehículos, pero no se aplicaba al adivinar códigos adentro de una descripción,
    y por eso entraron 212 códigos de fábrica terminados en REF: «505REF», «70010REF»,
    «1995REF», «2003-2012REF». Ninguno existe; son el modelo del auto, el año, o el número
    interno del proveedor.

    Y tapaba el mejor dato de la lista: «REF ORIG» es el proveedor diciendo cuál es el código
    de fábrica. Pegado, ese marcador no se reconocía y el número que venía después quedaba como
    una adivinanza más."""
    salida = codigos.extraer_codigos_de_texto(
        "BULBO DE TEMPERATURA DE ELECTROVENTILADOR 761 PEUGEOT 404 - 504 - 505REF ORIG "
        "024210 024212 204404 313320172 CA95260000 MLH TS6993")
    cierto("505REF" not in salida, "«505REF» no es un código")
    cierto("024210" in salida, "el código que viene después de REF ORIG sí")


def probar_marca_pegada_atras_del_numero():
    """«4EC1TBOSCH=0250202087» son tres cosas: un motor, una marca y un código.

    Así escribe una de las listas la equivalencia de Bosch. Sin partir por el igual entraba
    todo junto, y un código con la marca adelante no cruza con nadie porque nadie más lo
    escribe así. Despegada la marca, lo que queda —«4EC1T»— lo descartan las reglas de motor
    de siempre, que con la marca pegada no lo reconocían."""
    salida = codigos.extraer_codigos_de_texto(
        "BUJIA LEIGG008 CHEVROLET GM OPEL Astra 1 7 TD X17DT mot 4EC1TBOSCH=0250202087 "
        "GM94481972 HESCHER=HC173")
    igual(sorted(salida), ["0250202087", "GM94481972", "LEIGG008"],
          "el código de Bosch sí, el motor y la marca no")


def probar_lista_de_modelos_no_es_codigo():
    """«106-206-306-406-607» es la lista de autos a los que le va la pieza, no un código.

    Es de los peores códigos inventados que hay: cada uno cuelga de sí mismo todo lo que nombre
    esos autos. Lo que no puede pasar es llevarse puestos los códigos de fábrica con guiones,
    que son muchos y muy usados."""
    for lista in ("106-206-306-406-607", "307-308-408-208-3008-C4",
                  "316-318-320-325-330-520-530-540-X3-X5-Z3-Z4"):
        cierto(codigos._es_lista_de_modelos(lista), f"«{lista}» es una lista de modelos")
    for codigo in ("06K-905-601-B", "8-01115-315-0", "7700747549-7700850589", "6PU009161-021"):
        cierto(not codigos._es_lista_de_modelos(codigo), f"«{codigo}» es un código de verdad")
    igual(codigos.extraer_codigos_de_texto(
              "SENSOR DE VELOCIDAD 90023 PEUGEOT 106-206-306-406-607REF ORIG HELLA "
              "6PU009161-021"),
          ["6PU009161-021"], "de esa descripción sale un solo código")


def probar_la_coma_decimal_es_el_mismo_motor():
    """«1,6» y «1.6» son la misma cilindrada, y hasta ahora no lo eran.

    Illinois escribe la coma —3.105 descripciones de esa lista— y todos los demás el punto.
    Comparadas tal cual, las dos cilindradas nunca se cruzaban y la comparación cortaba con
    «cilindradas distintas»: la lista más nueva quedaba rechazada contra el resto del catálogo
    por cómo escribe un número. Sobre 1.500 x 1.500 productos reales eran 796 pares.

    Y la coma no era un caracter de palabra, así que «1,9TDI» se partía en «1» y «9TDI». Ese
    «9TDI» suelto aparece 129 veces y hacía de modelo compartido entre un 1,9 y un 2,9."""
    igual(vehiculos._RE_COMA_DECIMAL.sub(".", "JUNTA FORD FOCUS 1,6 16V"),
          "JUNTA FORD FOCUS 1.6 16V", "la coma entre números es un punto")
    igual(vehiculos._RE_COMA_DECIMAL.sub(".", "BOBINA VW GOL 1,9TDI"),
          "BOBINA VW GOL 1.9TDI", "1,9TDI no se parte")
    # La coma que NO está entre números se queda: separa una lista de autos.
    igual(vehiculos._RE_COMA_DECIMAL.sub(".", "JUNTA FIAT PALIO, SIENA, UNO"),
          "JUNTA FIAT PALIO, SIENA, UNO", "la coma que separa autos no se toca")


def probar_las_valvulas_no_dicen_para_que_auto_es():
    """«16V» no es un auto: es cómo es el motor. Compartirlo no es compartir el vehículo.

    Era la última evidencia que quedaba cuando una de las dos descripciones no nombra ninguna
    marca conocida, y así salían 43 pares de motores distintos de la misma marca: la junta de
    la Hilux D-4D contra la del Corolla 1ZZ-FE, la del Peugeot 306 XU7 contra la del 206 TU5,
    la del Fiat Freemont 2.4 contra la del Punto 1248cc. Todas «coinciden en 16V».

    Lo que NO tiene que agarrar son los modelos que se escriben número y letra: 320I, 318I,
    525D, 310D y 412D son BMW y Mercedes de verdad, y son de los datos más específicos que
    traen estas listas. Y la cilindrada exacta en centímetros cúbicos tampoco: «843CC» es lo
    único que une la junta del ASIA/KIA TOWNER con la del DAIHATSU HI-JET, que son el mismo
    motor con dos nombres."""
    for w in ("16V", "12V", "24V", "1.8I", "2.0L", "1.4I/1.6I", "1.8T"):
        cierto(bool(vehiculos._RE_SOLO_MOTORIZACION.match(w)),
               f"«{w}» dice cómo es el motor, no para qué auto es")
    for w in ("320I", "318I", "525D", "310D", "412D", "843CC", "1587CC", "K9K", "XU7JP4",
              "FOCUS", "S10"):
        cierto(not vehiculos._RE_SOLO_MOTORIZACION.match(w),
               f"«{w}» sí dice para qué auto es")


def probar_modelo_con_cilindrada_pegada():
    """«CORSA1.4» es el modelo con la cilindrada pegada, no un código.

    Sale de la exportación del proveedor, que se come el espacio, y hacía el daño de siempre:
    tiene forma de código, así que entraba como código de fábrica. En la base real el CORSA1.4
    llegó a colgar un tubo, una correa multicanal y un sensor MAP — tres repuestos que no
    tienen nada que ver, hermanados porque las tres descripciones nombran el mismo auto."""
    for pegado, separado in (("TUBO CHEV CORSA1.4/1.6 8v", "TUBO CHEV CORSA 1.4/1.6 8v"),
                             ("FILTRO VW AMAROK2.0 TD", "FILTRO VW AMAROK 2.0 TD"),
                             ("BOMBA CHEVROLET AVEO1.6 16v", "BOMBA CHEVROLET AVEO 1.6 16v")):
        igual(vehiculos.separar_texto_pegado(pegado), separado,
              f"«{pegado}» tiene que quedar separado")
    # Y aunque llegue sin separar, no puede entrar como código de fábrica.
    for texto in ("TUBO CHEV CORSA1.4/1.6/1.8 8v", "FILTRO de ACEITE VW AMAROK2.0 TD",
                  "BOBINA R 19/TWINGO/TRAFIC-1.6 1995/"):
        igual(codigos.extraer_codigos_de_texto(texto), [],
              f"«{texto}» no tiene ningún código de fábrica adentro")

    # Lo que NO se puede tocar: con una o dos letras adelante no es un modelo, es la
    # designación de un zócalo o una medida. Se piden cuatro letras justamente por esto.
    for medida in ("LAMPARA W2x4.6d 24v", "LAMPARA W2.1x9.5d 12v", "LAMPARA SV8,5-8 24v",
                   "LAMPARA BX8.2d 12v", "Tornillo M14X1.5X42_R", "TUBO 6mmx8mm x7,89mm"):
        igual(vehiculos.separar_texto_pegado(medida), medida,
              f"«{medida}» es una medida o un zócalo: no se toca")


def probar_numero_de_catalogo_no_es_puente():
    """Dos proveedores que numeran de corrido terminan chocando, y eso no es una equivalencia.

    JL numera sus filtros de corrido y Taranto sus juntas también: en la base real hay 19
    códigos numéricos de 6 y 7 dígitos que las dos listas usan, y los 19 son casualidad. El
    310007 de JL es un prefiltro de Focus y el de Taranto una junta de tapa de cilindros de un
    Ford MAX. Los de 8 dígitos o más, en cambio, son códigos de fábrica de verdad — hay 338 en
    la base real, y esos sí son el mismo repuesto.

    Se prueba el SALTO, que es lo peligroso: buscando un código se llega a otro producto por un
    vínculo, y desde ahí se salta a todo lo que tenga ESE mismo número. Un salto malo no suma
    un resultado, suma la red entera del otro."""
    con = equivalencias.preparar(sqlite3.connect(":memory:"))
    cur = con.cursor()

    def marca(nombre):
        cur.execute("INSERT INTO marcas (nombre, tipo) VALUES (?, ?)",
                    (nombre, "OEM" if nombre == "OEM / FABRICA" else "PROVEEDOR"))
        return cur.lastrowid

    def producto(marca_id, code, desc):
        cur.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id)"
                    " VALUES (?, ?, ?, ?)", (code, codigos.sanitizar(code), desc, marca_id))
        return cur.lastrowid

    def vincular(a, b):
        cur.execute("INSERT INTO equivalencias (producto_a_id, producto_b_id, confianza)"
                    " VALUES (?, ?, 80)", (min(a, b), max(a, b)))

    jl, taranto, oem = marca("JL"), marca("MOTORARG"), marca("OEM / FABRICA")

    # CHOQUE DE CATÁLOGO: se busca el prefiltro de JL, que cita el 310007 como código de
    # fábrica. Taranto tiene una junta con ESE mismo número. No pueden encadenarse.
    filtro = producto(jl, "FILT-1", "PRE-FILTRO FORD FOCUS")
    vincular(filtro, producto(oem, "310007", "PRE-FILTRO FORD FOCUS"))
    producto(taranto, "310007", "Jta.Tapa Cil. FORD MAX")

    # CÓDIGO DE FÁBRICA DE VERDAD: ocho dígitos. Acá el salto es lo que hace el trabajo.
    sensor = producto(jl, "SENS-1", "SENSOR GM")
    vincular(sensor, producto(oem, "93745292", "SENSOR GM"))
    producto(taranto, "93745292", "Sensor GM equivalente")
    con.commit()

    res = equivalencias.buscar_por_codigo(cur, codigos.sanitizar("FILT-1"))
    cierto("Jta.Tapa Cil. FORD MAX" not in {f["Descripcion"] for f in res},
           f"un número de catálogo de 6 dígitos no puede saltar de una marca a otra; "
           f"trajo {[f['Codigo'] for f in res]}")

    res2 = equivalencias.buscar_por_codigo(cur, codigos.sanitizar("SENS-1"))
    cierto("Sensor GM equivalente" in {f["Descripcion"] for f in res2},
           f"un código de fábrica de 8 dígitos sí tiene que cruzar; trajo "
           f"{[f['Codigo'] for f in res2]}")
    cierto(any(f["Cadena"].startswith("🔵") for f in res2),
           "y tiene que decir que llegó por «mismo código, otra marca»")
    con.close()


def main():
    for prueba in (probar_sanitizar, probar_codigo_util, probar_codigo_sospechoso,
                   probar_extractor,
                   probar_filtro_por_repeticion, probar_dividir, probar_vehiculos,
                   probar_familias_de_pieza, probar_precision_del_rubro, probar_comodines_y_kits,
                   probar_marcas_de_vehiculo, probar_ref_pegado,
                   probar_mapeo_columnas, probar_busqueda_entre_proveedores,
                   probar_codigo_generico_no_cruza,
                   probar_codigo_de_barras_no_es_equivalencia,
                   probar_columna_de_codigo_de_barras,
                   probar_codigo_conocido_gana_a_la_forma,
                   probar_todos_los_autos_de_una_descripcion,
                   probar_marca_corta_pegada_a_un_numero,
                   probar_marcas_de_repuesto_pegadas_al_codigo,
                   probar_camiones_y_motorizaciones_no_son_codigos,
                   probar_kit_que_trae_la_pieza,
                   probar_vocabulario_de_pieza,
                   probar_abreviaturas_de_las_listas_reales,
                   probar_busqueda_por_codigo_de_barras,
                   probar_la_patente_argentina,
                   probar_el_pais_del_codigo_de_barras,
                   probar_el_digito_verificador_del_codigo_de_barras,
                   probar_lo_que_excel_le_come_a_un_codigo_largo,
                   probar_modelos_y_motores_no_son_codigos_de_fabrica,
                   probar_bed_ford_no_es_ford,
                   probar_la_marca_abreviada_es_la_misma_marca,
                   probar_ref_orig_pegado_no_es_codigo,
                   probar_marca_pegada_atras_del_numero,
                   probar_lista_de_modelos_no_es_codigo,
                   probar_la_coma_decimal_es_el_mismo_motor,
                   probar_las_valvulas_no_dicen_para_que_auto_es,
                   probar_modelo_con_cilindrada_pegada,
                   probar_numero_de_catalogo_no_es_puente):
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

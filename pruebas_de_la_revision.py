"""Pruebas de la REVISIÓN de equivalencias: que las reglas no se equivoquen con pares conocidos.

Uso:
    python3 pruebas_de_la_revision.py                 # los pares de muestra, siempre
    python3 pruebas_de_la_revision.py --base copia.db # además, tus aprobaciones de esa base

Por qué existe: cada regla nueva del análisis («modelos distintos», «años distintos», «motores
distintos»…) se probó contra pares reales antes de subirla, pero con scripts sueltos que no
quedaban en ningún lado. La regla siguiente podía romper lo que la anterior había arreglado —o
bajar a rojo un par que aprobaste— y nadie se iba a enterar. Esto deja escrito lo que ya se sabe.

PARES DE MUESTRA: sacados de la cola real y revisados a mano, con lo que tienen que dar. «misma»
es que las descripciones concuerden; «distinta», que la app diga por qué son piezas distintas (un
motivo que tumba el par). Si se agrega una regla, se agregan acá los casos que la motivaron.

CON --base: arma una copia de la base en una carpeta temporal, pone todos los pares que
aprobaste como si recién llegaran —sin tus decisiones ni lo aprendido de ellas, para que no se
copien la respuesta— y los puntúa con el análisis de siempre. Falla si más del 1 % de lo aprobado
cae en 🔴. Sobre la copia de la base real del 5/10 —20.306 aprobados, con las decisiones de quien
atiende el mostrador— caen 127 (0,6 %), y aparte 117 que estaban mal aprobados y ya se revisaron
(ver ALARMAS_DE_APROBACIONES_MALAS): esos no cuentan. Sobre la base de prueba anterior (13.021
aprobados) eran 83, y 725 mal aprobados.

Y AL REVÉS, LOS FALSOS POSITIVOS: lo que RECHAZASTE va en otra tanda, puntuado igual. Un
rechazado que queda entre las «limpias» es uno que se habría aprobado en grupo con la muestra.
Falla si pasa del 1 % (TOPE_DE_FALSOS_POSITIVOS). Sobre la base real del 7/10: 3 de 2.633
(0,1 %), los tres con la descripción idéntica y del mismo rubro.

Nunca toca la base de trabajo: corre en una carpeta temporal, con una base propia.
"""
import os
import shutil
import sqlite3
import sys
import tempfile

# Los modelos de auto la app los aprende del catálogo (ver modelos_de_marca()): con una base
# vacía no reconoce ninguno. Los casos que dependen de eso se prueban solo con --base.
NECESITA_EL_CATALOGO = "necesita el catálogo"

# (descripción A, descripción B, lo que tiene que dar, de dónde salió[, NECESITA_EL_CATALOGO])
# «misma»: concuerdan. «distinta»: un motivo que contradice (rojo). «dudosa»: no concuerdan,
# pero sin un motivo que contradiga: van a revisión.
PARES_DE_MUESTRA = [
    # --- la misma pieza escrita distinto: tienen que concordar ---
    ("Jta.Tapa Cilindros Renault Master - Trafic - motor G9U 2463cc.",
     "Junta Tapa de Cilindros RENAULT (ESP 1.50mm) MASTER TRAFIC NISSAN : PRIMASTAR INTERSTAR - "
     "2,5 - G9U-720/724/730/750/754 (8200406743) (Metal Graf®)", "misma", "TARANTO / ILLINOIS"),
    ("Jta.Tapa Cil.ASTRA KADETT VECTRA",
     "Junta Tapa de Cilindros CHEVROLET MONZA KADETT ASTRA VECTRA ZAFIRA - 2,0/2,2 - "
     "C20NE/SEH/SER/NEF OHC", "misma", "TARANTO / ILLINOIS", NECESITA_EL_CATALOGO),
    ("Jta.Carter DEUTZ F5L 913", "Junta para Cárter DEUTZ 913 TRACTOR 5 CIL. - 5,1 - F5L (3018944)",
     "misma", "TARANTO / ILLINOIS"),
    ("Sensor de rotacion Hyundai Accent Elantra .",
     "SENSOR DE ROTACION 30173 HYUNDAI EXCEL -ELANTRA -ACCENT 1 3 Y 1 15 16V", "misma",
     "CRI-FA / FISPA"),
    ("Sensor de presion de colector MAP Citroen Berlingo 1.4 1.8 Xsara Saxo",
     "SENSOR MAP 40005 CITROEN BERLINGO - C5 - SAXO - XSARA - XANTIA - XM", "misma",
     "CRI-FA / FISPA"),
    ("Junta Distribucion VW GOL 1000", "JTA T.DIST VOLKSWAGEN GOL 1000", "misma",
     "TARANTO / IMPERIAL"),
    ("Jta.Tapa Valv. Ford F100-150 91/", "JTA T.V. FORD F100 4.9", "misma", "abreviatura T.V."),
    ("Jta.Carter FIAT 1100", "JTA CARTER FIAT 128/147 1100/", "misma", "TARANTO / IMPERIAL"),
    ("Jta.Tapa Cil. MAXION LAND ROVER", "JTA T.C. MAXION ROVER 1.60 mm", "misma",
     "abreviatura T.C."),
    ("JUNTA BOMBA VACIO A BLOCK PERKINS", "JTA BBA VACIO PERKINS 1006", "misma", "abreviatura BBA"),
    ("JTA C.VEL. FORD F100", "Juntas para caja de velocidad FORD F100", "misma",
     "abreviatura C.VEL."),
    ("Jta.Tapa Cil. SUZUKI CULTUS G13B 1298CC 1996/...",
     "Junta Tapa de Cilindros SUZUKI SWIFT SAMURAI CULTUS SIDEKICK JIMNY BARINA - 1,3 - G13B/A/K",
     "misma", "motores de la misma familia"),
    ("Jta.Tapa Cil. FIAT 1100", "Junta Tapa de Cilindros FIAT 1100/103 - 1,1 - 4 CIL. (4015455)",
     "misma", "TARANTO 250005 / ILLINOIS TC-206-15"),

    # --- piezas distintas: la app tiene que decir por qué ---
    ("Jgo.Jtas. ROVER 214/216/218/414/416", "JTA T.C. ROVER 111/214 11/14K", "distinta",
     "juego de juntas contra junta suelta"),
    ("Juego de juntas para Caja de Velocidad FORD F350", "Jta.Tapa Valvulas FORD F350", "distinta",
     "juego contra junta suelta"),
    ("Sonda Lambda Planar Volkswagen Gol Fox Voyage 1.0 16 Saveiro 1.6 Suran",
     "SONDA LAMBDA LECS012 GM ASTRA 1 8 - CELTA 1 4 GLS - CORSA 1 0 - VW GOLF REF ORIG", "distinta",
     "misma marca, ningún modelo en común", NECESITA_EL_CATALOGO),
    ("Junta Caja JHON DEERE", "JTA T.C.J.DEERE 1550/9650-6081", "distinta",
     "caja contra tapa de cilindros"),
    ("Jta.Tapa Cil. HONDA CIVIC 1500 EW 1488CC 12V 1984/1989",
     "Junta Tapa de Cilindros HONDA CIVIC 2015/... - 1.5 - L15B8 (MLS)", "distinta",
     "años que no se cruzan"),
    ("Termostato carcasa termostática con sensor Ford Transit 2,0 2016/2022 .",
     "TERMOSTATO CON CARCASA 97024 FORD FOCUS ECOSPORT MONDEO III 2006-2007 TRANSIT 2004-2006",
     "distinta", "años que no se cruzan"),
    ("Jta.Carter DEUTZ F4L 913", "Junta para Cárter DEUTZ 913 TRACTOR 5 CIL. - 5,1 - F5L (3018944)",
     "distinta", "cuatro cilindros contra cinco"),
    ("Jta.Tapa Cil. HYUNDAI SONATA TCI TUCSON TCI D4EA 16V 2005/...",
     "Junta Tapa de Cilindros HYUNDAI SONATA 2007/... RONDO 2006/... MAGENTIS 2005/... - 2.0 - "
     "G4KA", "distinta", "diésel D4EA contra nafta G4KA"),
    ("Jta.Tapa Cil.Superm. FIAT 1100",
     "Junta Tapa de Cilindros FIAT 1100/103 - 1,1 - 4 CIL. (4015455)", "distinta",
     "TARANTO 250006 es supermedida; la de ILLINOIS, estándar"),
    ("Junta Tapa de valvulas superior Mercedes Benz OM352",
     "Junta Tapa de Válvulas Lateral M. BENZ1215 1620 - 5,7/6,0 - OM352 OM366 (3520150160)",
     "distinta", "TARANTO 350332 / ILLINOIS JVL-163-43: tapa superior contra lateral"),
    ("Bulbo presion de aceite Ford F100 F250 F4000 F12000 F14000 Cargo Electronico Cummins Mwm "
     "0.40 BAR Normal abierto - ANTES ERA TAPON NEGRO",
     "BULBO DE PRESION DE ACEITE 349 CHEVROLET AVEO 1 6 CRUZE 1 8 TRACKER 1 8 REF ORIG 55354325 "
     "96802844 PS503 Vernet OS3573 ERA 330366 FAE 12436", "distinta",
     "CRI-FA 32-42371 / 349FISPA: Ford contra Chevrolet; Cummins y MWM no lo salvan"),
    ("Bulbo presion de aceite Ford F100 F250 F4000 F12000 F14000 Cargo Electronico Cummins Mwm "
     "0.40 BAR Normal abierto - ANTES ERA TAPON NEGRO",
     "BULBO DE PRESION DE ACEITE 358 FORD ESCORT - ORION - SEAT CORDOBA - IBIZA - VOLKSWAGEN GOL "
     "I - GOL II - GOL III - POINTER - POLO - QUANTUM - SAVEIRO - PRESION 0 5 BAR - AISLANTE NEGRO "
     "REF ORIG SEAT 0279190811 - VOLKSWAGEN 0309190811", "distinta",
     "CRI-FA 32-42371 / 358FISPA: 0,40 contra 0,5 bar"),
    ("Jta.Carter DEUTZ F4L 913", "JTA CARTER DEUTZ 913 6 CIL.", "distinta",
     "TARANTO / IMPERIAL: F4L es de cuatro cilindros"),
    ("JUNTAS FORD ESCORT/ CHEV ETTE 1.6 Wb", "Jta.Carter CHEVROLET CHEV ETTE", "distinta",
     "JL / TARANTO: Wb es Weber, la de JL es del carburador"),
    ("JUNTA MPI FIAT TEMPRA 2.0 16V .", "JTA T.C. FIAT TEMPRA 2.0 cc.", "distinta",
     "JL / IMPERIAL: la de la inyección contra la de tapa de cilindros"),
    ("Jta.Tapa Cil. JEEP CHEROKEE 4 l",
     "Junta Tapa de Cilindros JEEP RENEGADE 2014/... CHEROKEE 2013/... - 2.4 - ED6 // 68188889AF "
     "(MLS)", "distinta", "TARANTO / ILLINOIS: 4 litros contra 2,4"),
    ("Termostato carcasa termostática con sensor Ford Transit 2,0 2016/2022 .",
     "TERMOSTATO CON CARCASA 97012 FORD FOCUS 2 0L MFI 05 -11 RANGER 2 3L MFI 01 -06 MONDEO III 1 "
     "8 00 -08 REF ORIG VERNET TH6939", "distinta",
     "CRI-FA 48-6148 / 97012FISPA: los años de FISPA con dos cifras"),
    ("Termostato Chevrolet Blazer S10 -2.2 inyeccion. Valvula reparacion de carcaza y junta. "
     "Naftero.", "TERMOSTATO COMPLETO 97066 Chevrolet S10 2012 2013 Motor 180 Duramax REF ORIG "
     "12650485 12625212", "distinta", "CRI-FA 14-V211.87 / 97066FISPA: nafta contra diésel"),
    ("JUNTA DE CARTER TOYOTA HILUX 2779CC", "JTA CARTER TOYOTA HILUX 2200 D", "distinta",
     "TARANTO / IMPERIAL: 2,8 contra 2,2"),
    ("Juntas para diferencial CHEVROLET / FORD DANA 70 - F250/F350", "JTA DIFERENCIAL DANA 44 FORD",
     "distinta", "ILLINOIS / IMPERIAL: dos puentes Dana distintos"),
    ("Bulbo de temperatura crítica. Citroen Evasion - Xantia - ZX 2.0-1.9 - Diesel. Tapón azul. "
     "Aro verde.", "BULBO DE TEMPERATURA RELOJ 206 CITROEN Berlingo - Xantia - Xsara - ZX - "
     "PEUGEOT 106 - 306 - 405", "distinta", "CRI-FA / FISPA: el de la luz contra el del reloj"),

    # --- dudosas: no se descartan de una, pero tampoco pasan sin mirarlas ---
    ("Junta Tapa Valvulas MWM SPRINT 4.07",
     "Junta Tapa de Válvulas CHEVROLET SPRINT SWIFT CULTUS VAN TURBO 1984/… - 1,0 - 61 G10 G10T "
     "50 HP", "dudosa", "TARANTO 330510/1 / ILLINOIS JVS-324-30: SPRINT es un motor MWM y un "
     "Chevrolet", NECESITA_EL_CATALOGO),
    ("Junta Tapa Valvulas MWM SPRINT 4.07",
     "Junta Tapa de Válvulas FORD FALCON PICK UP - 2,8/3,1/3,6 - 170 187 188 MAX ECONO 221 221 "
     "SPRINT 4/7B (CODE6584B)", "dudosa", "TARANTO 330510/1 / ILLINOIS JVS-142-30: el Falcon "
     "Sprint", NECESITA_EL_CATALOGO),
    # Revisando a mano los amarillos y rojos de la cola, uno por uno.
    ("JUNTAS JEEP IKA CARTER YF", "Junta para Cárter JEEP IKA BERGANTIN 57/78 - 2,5 - 4L 151 "
     "(2000169/2016713)", "distinta", "JL / ILLINOIS: el carburador Carter YF no es el cárter"),
    ("JTA LAT.CARTER DEUTZ 514 2 C.", "Junta para Cárter DEUTZ 514 1114 2 CIL. - 2,7/2,9/3,2 - "
     "F2L (D1540)", "distinta", "IMPERIAL / ILLINOIS: la tapa lateral del cárter"),
    ("Juego de juntas para Carburador CITROEN 3CV SOLEX 69/73", "JUNTAS CITROEN 3CV 74/9 SOLEX",
     "distinta", "ILLINOIS / JL: los años de dos cifras con barra"),
    ("Juego de juntas para Carburador CITROEN 3CV SOLEX 69/73", "JUNTAS CITROEN 3CV 70/3 SOLEX",
     "misma", "ILLINOIS / JL: los mismos años"),
    ("Inyector de combustible Renault Megane Clio Magneti Marelli aro gris.",
     "INYECTOR LEICJ051 RENAULT CLIO - SCENIC 2 0 16V - LAGUNA II 1 8 - TRAFFIC II 2 0 ARO VERDE "
     "REF ORIG MARELLI IWP 042", "distinta", "CRI-FA / FISPA: el aro de color"),
    ("Termostato Ford Fiesta Focus Ecosport 1.6 Sigma Ka 1.5 Sigma 82 grados .",
     "TERMOSTATO COMPLETO 97010 FORD FIESTA 1 6 8V ROCAM FLEX 05 ECOSPORT 1 6 8V ROCAM FLEX 05",
     "distinta", "CRI-FA / FISPA: Sigma no es Rocam"),
    ("Termostato para carcaza Volkswagen Up Fox Gol 1.0 12V Fox Suran Saveiro 1.6 16V 80 Grados .",
     "TERMOSTATO COMPLETO 97043 Vw Fox Suran Golf POLO SAVEIRO 1 6 16V Msi - VW UP 1 0 12V",
     "distinta", "CRI-FA / FISPA: el termostato solo contra el que trae la carcasa"),
    ("KIT DE CORREA POLY V LAKN32000A1 FIAT FIORINO - UNO - STRADA 1.3 MPI - PALIO - PUNTO",
     "CORREA POLY V 3PK905 PALIO/SIENA 1.3 16v Fire/PUNTO 1.4-FIORINO Bosch", "distinta",
     "FISPA / JL: el kit contra la correa suelta"),
    ("Juego de juntas para Turbo Compresor M. BENZ SALIDA TURBO (ESPÁRRAGOS 10MM)",
     "Juego de juntas para Turbo Compresor M. BENZ SALIDA TURBO (ESPÁRRAGOS 8MM)", "distinta",
     "ILLINOIS: los espárragos del turbo"),
    ("Junta Tapa de Cilindros JOHN DEERE 3530 4420 4530 - 5,4/5,9 - 6329D (119MM)",
     "Junta Tapa de Cilindros JOHN DEERE 3420 6 CIL. - 5,0 - 303 (115MM)", "distinta",
     "ILLINOIS: el diámetro del cilindro"),
    ("Junta carter aceite IVECO Euro trakker - Euro star 89/ motor 8210.42L/K",
     "JTA RAD.ACEITE IVECO EURO TRA", "distinta", "TARANTO / IMPERIAL: el radiador de aceite"),
    ("JTA BASE CARB F. SIERRA 1.6 cc", "JUNTAS SIERRA 1.6 1983/86 WEBER", "distinta",
     "IMPERIAL / JL: la base del carburador contra el juego"),
    ("JUNTA TAPA CUBA HOLLEY- FORD", "JUNTA TAPA CUBA Renault 18/Ford SIERRA TEIE- SEVEL",
     "distinta", "TARANTO / JL: TEIE es un Solex"),
    ("JUNTA BOMBA DE AGUA - TORINO", "JTA CODO AGUA TORINO 4/7 B.", "distinta",
     "TARANTO / IMPERIAL: el codo no es la bomba"),
    # Revisando muestras de los verdes.
    ("Sensor de temperatura Volkswagen Fox Suran Gol Trend Voyage 2 salidas color gris .",
     "SENSOR TEMP EXTERIOR VW BORA/GOLF 1.6/1.8T/1.9TD-POLO 1.9TD-SURAN- AUDI Masser", "distinta",
     "CRI-FA / JL: el sensor del aire de afuera"),
    ("Jta.Bomba Hidraulica IVECO 150", "JTA BBA INYECTO FIAT 150- IVECO", "distinta",
     "TARANTO / IMPERIAL: la bomba hidráulica no es la inyectora"),
    ("BOBINA IGNICION,VW POLO/ GOLF / PASSAT CON MODULO",
     "BOBINA DE IGNICION 70125 VW POLO-GOLF-PASSAT Sin Modulo REF ORIG 6NO 905 104", "distinta",
     "TARANTO / FISPA: con y sin módulo"),
    ("Jta.Tapa Cil. HONDA CIVIC CRX VTEC D15Z6/Z7 16V 1590CC 1992/1995",
     "Junta Tapa de Cilindros HONDA CIVIC CRX - 1.6 - B16A1/2/3 16V VTEC VT (12251P30004/014)",
     "distinta", "TARANTO / ILLINOIS: motores Honda de otra serie"),
    ("Junta para Cárter CUMMINS ELECTRÓNICO - 3,9 - ISBE (4897877/4939246)",
     "JTA CARTER CUMMINS 6 CIL ISBe", "distinta", "ILLINOIS / IMPERIAL: el Cummins 3.9 es de 4"),
    ("Jta.Carter CHEVROLET SPRINT 6.07 T", "JTA CARTER MWM SPRINT 4 CIL.", "distinta",
     "TARANTO / IMPERIAL: el Sprint 6.07 es de 6, aunque no diga MWM"),
    ("Jta.Carter CHEVROLET SPRINT 4.07T", "JTA CARTER MWM SPRINT 4 CIL.", "dudosa",
     "TARANTO / IMPERIAL: el mismo Sprint de 4, con la marca del auto y la del motor",
     NECESITA_EL_CATALOGO),
    ("Sonda Lambda Renault Clio II Kangoo 1.4 - Largo cable 36 centimetros -",
     "SONDA LAMBDA 80048 RENAULT CLIO II MEGANE II 1 6 8 16V Cable de 63cm REF ORIG BOSCH",
     "distinta", "CRI-FA / FISPA: 36 contra 63 cm de cable, aunque la cilindrada sea solo una duda"),
]


def _cargar_la_logica(carpeta):
    """La lógica de la app, con una base vacía en `carpeta`."""
    raiz = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, raiz)
    os.chdir(carpeta)
    import logica
    return logica


def probar_pares_de_muestra(logica, con_catalogo):
    """Devuelve (fallas, cuántos se probaron)."""
    fallas, probados = [], 0
    for desc_a, desc_b, esperado, origen, *extra in PARES_DE_MUESTRA:
        if NECESITA_EL_CATALOGO in extra and not con_catalogo:
            continue
        probados += 1
        fa, fb = logica.firma_de_producto(desc_a), logica.firma_de_producto(desc_b)
        ok, motivo = logica.firmas_compatibles(fa, fb)
        if esperado == "misma" and not ok:
            fallas.append(f"«{desc_a[:40]}» / «{desc_b[:40]}» ({origen}): tenían que concordar "
                          f"y dio «{motivo}»")
        if esperado == "distinta" and (ok or not motivo.startswith(
                logica._MOTIVOS_QUE_CONTRADICEN)):
            fallas.append(f"«{desc_a[:40]}» / «{desc_b[:40]}» ({origen}): tenían que ser piezas "
                          f"distintas y dio {'que concuerdan' if ok else f'«{motivo}»'}")
        if esperado == "dudosa" and (ok or motivo.startswith(logica._MOTIVOS_QUE_CONTRADICEN)):
            fallas.append(f"«{desc_a[:40]}» / «{desc_b[:40]}» ({origen}): tenían que quedar para "
                          f"revisar y dio {'que concuerdan' if ok else f'«{motivo}» (rojo)'}")
    return fallas, probados


def preparar_la_base_de_aprobaciones(ruta_base, destino):
    """Copia la base a `destino` con tus aprobaciones puestas como si recién llegaran: sin tus
    decisiones ni lo aprendido de ellas, para que el análisis no se copie la respuesta. Se hace
    ANTES de cargar la lógica, que abre la conexión al arrancar. Devuelve cuántos pares quedan."""
    shutil.copy(ruta_base, destino)
    con = sqlite3.connect(destino)
    aprobados = {(min(a, b), max(a, b)) for a, b in con.execute(
        "SELECT producto_a_id, producto_b_id FROM equivalencias_revisadas WHERE decision = 'ok'")}
    pares = [(a, b) for a, b in sorted(aprobados)
             if con.execute("SELECT COUNT(*) FROM productos WHERE id IN (?, ?)",
                            (a, b)).fetchone()[0] == 2]
    # Y LO QUE RECHAZASTE, en otra tanda: es lo que dice cuántos vínculos malos dejaría pasar
    # el puntaje (los falsos positivos). Un par rechazado que el análisis pone entre las
    # «limpias» es uno que se hubiera aprobado en grupo con la muestra.
    rechazados = {(min(a, b), max(a, b)) for a, b in con.execute(
        "SELECT producto_a_id, producto_b_id FROM equivalencias_revisadas "
        "WHERE decision = 'rechazada'")} - aprobados
    rechazados = [(a, b) for a, b in sorted(rechazados)
                  if con.execute("SELECT COUNT(*) FROM productos WHERE id IN (?, ?)",
                                 (a, b)).fetchone()[0] == 2]
    con.executemany("DELETE FROM equivalencias_pendientes WHERE MIN(producto_a_id, "
                    "producto_b_id) = ? AND MAX(producto_a_id, producto_b_id) = ?", rechazados)
    con.executemany("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, "
                    "lote) VALUES (?, ?, 'lista_proveedor', ?)",
                    [(a, b, LOTE_DE_LOS_RECHAZOS) for a, b in rechazados])
    con.execute("DELETE FROM equivalencias_revisadas")
    con.executemany("DELETE FROM equivalencias WHERE MIN(producto_a_id, producto_b_id) = ? "
                    "AND MAX(producto_a_id, producto_b_id) = ?", pares)
    con.executemany("DELETE FROM equivalencias_pendientes WHERE MIN(producto_a_id, "
                    "producto_b_id) = ? AND MAX(producto_a_id, producto_b_id) = ?", pares)
    con.executemany("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, "
                    "lote) VALUES (?, ?, 'lista_proveedor', ?)",
                    [(a, b, LOTE_DE_LA_PRUEBA) for a, b in pares])
    con.commit()
    con.close()
    return len(pares)


LOTE_DE_LA_PRUEBA = "PRUEBA DE APROBACIONES"
LOTE_DE_LOS_RECHAZOS = "PRUEBA DE RECHAZOS"
# Cuántos de los rechazados a mano pueden quedar entre las «limpias», en %. Sobre la base real
# del 7/10 eran 3 de 2.633 (0,1 %); más del 1 % es que una regla nueva abrió la puerta.
TOPE_DE_FALSOS_POSITIVOS = 1.0

# Alarmas que, sobre la base de prueba, se revisaron una por una y en todos los casos el vínculo
# aprobado estaba mal: 🧰 son el kit de reparación unido a la bomba que repara (283), la tapa de
# flotante, el sensor de nivel o la rampa unidos a la bomba o a los inyectores donde van (70) y
# la polea unida a los alternadores que la llevan (332), el capuchón o el microfiltro unidos a
# la bobina o al inyector donde van (26) y 14 tapas y sensores más con la frase pegada
# («2015Conj Bomba»).
# 🔎 se sumó con la base real del 5/10: 117 aprobados en bloque con reglas viejas, y el
# «número de fábrica» es el nombre del motor o del modelo (X12SZ8V, SQR472, F2CFE601A, N13B16A).
ALARMAS_DE_APROBACIONES_MALAS = ("🧰", "🔎")


def probar_aprobaciones(logica, cuantos):
    """Puntúa las aprobaciones preparadas. Devuelve (fallas, resumen)."""
    if not cuantos:
        return [], "la base no tiene aprobaciones con los dos productos cargados"
    limpias, sospechosas, relacionadas = logica.analizar_lote_pendiente(LOTE_DE_LA_PRUEBA,
                                                                        limite=None)
    todos = limpias + sospechosas + relacionadas
    rojos = [f for f in todos if (f.get("confianza") or 0) < 30]
    # Los que están mal aprobados y ya se revisaron a mano: no cuentan contra el 1 %, porque ahí
    # el rojo es el acierto. Se informan aparte para que se vea cuántos quedan.
    mal_aprobados = [f for f in rojos
                     if (f.get("alarmas") or [""])[0].startswith(ALARMAS_DE_APROBACIONES_MALAS)]
    rojos = [f for f in rojos if f not in mal_aprobados]
    resumen = (f"{cuantos:,} aprobados: {len(limpias):,} limpios, {len(sospechosas):,} en "
               f"revisión, {len(rojos):,} en rojo ({100 * len(rojos) / cuantos:.1f} %)"
               + (f", y {len(mal_aprobados):,} que estaban mal aprobados" if mal_aprobados
                  else ""))
    fallas = []
    if len(rojos) > 0.01 * cuantos:
        fallas.append(f"más del 1 % de lo aprobado cae en rojo: {resumen}. Ejemplos: "
                      + "; ".join(f"{f.get('cod_a')} / {f.get('cod_b')}: "
                                  f"{(f.get('alarmas') or [''])[0][:70]}" for f in rojos[:5]))
    return fallas, resumen


def probar_rechazos(logica):
    """Los FALSOS POSITIVOS: lo que rechazaste a mano, puntuado como si recién llegara.
    Devuelve (cuántos, cuántos quedan limpios, cuántos 🟢 ≥75, ejemplos de los limpios)."""
    logica_ns = logica.todo_lo_de_la_logica()
    n = logica_ns["c"].execute("SELECT COUNT(*) FROM equivalencias_pendientes WHERE lote = ?",
                               (LOTE_DE_LOS_RECHAZOS,)).fetchone()[0]
    if not n:
        return 0, 0, 0, []
    limpias, sospechosas, relacionadas = logica.analizar_lote_pendiente(LOTE_DE_LOS_RECHAZOS,
                                                                        limite=None)
    altas = [f for f in limpias if (f.get("confianza") or 0) >= 75]
    return n, len(limpias), len(altas), limpias


def main():
    ruta_base = None
    if "--base" in sys.argv:
        ruta_base = os.path.abspath(sys.argv[sys.argv.index("--base") + 1])
    carpeta = tempfile.mkdtemp(prefix="pruebas_revision_")
    try:
        cuantos = (preparar_la_base_de_aprobaciones(
            ruta_base, os.path.join(carpeta, "equivalencias_app.db")) if ruta_base else 0)
        logica = _cargar_la_logica(carpeta)
        fallas, probados = probar_pares_de_muestra(logica, con_catalogo=bool(ruta_base))
        salteados = len(PARES_DE_MUESTRA) - probados
        print(f"{'✅' if not fallas else '❌'} pares de muestra: {probados - len(fallas)} de "
              f"{probados} bien" + (f" ({salteados} necesitan el catálogo: correlo con --base)"
                                    if salteados else ""))
        if ruta_base:
            f2, resumen = probar_aprobaciones(logica, cuantos)
            print(f"{'✅' if not f2 else '❌'} aprobaciones: {resumen}")
            fallas += f2
            n_r, limpios_r, altos_r, _ejemplos = probar_rechazos(logica)
            if n_r:
                print(f"   rechazos (falsos positivos): {n_r:,} rechazados a mano: "
                      f"{limpios_r:,} quedarían limpios ({100 * limpios_r / n_r:.1f} %), "
                      f"{altos_r:,} con 75 o más ({100 * altos_r / n_r:.1f} %)")
                if 100 * limpios_r / n_r > TOPE_DE_FALSOS_POSITIVOS:
                    fallas.append(f"{limpios_r} de {n_r} rechazados a mano quedarían limpios: "
                                  f"más del {TOPE_DE_FALSOS_POSITIVOS:g} %")
                if "--ver" in sys.argv:
                    for f in _ejemplos[:25]:
                        print(f"     {f.get('confianza')}: {f.get('cod_a')} / {f.get('cod_b')} — "
                              f"{[s for _, s in (f.get('senales') or [])][:4]}")
        for f in fallas:
            print("   ✗", f)
        print("todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

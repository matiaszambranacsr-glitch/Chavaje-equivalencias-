"""Pruebas de las FUENTES DE AFUERA: el INDEC, el BCRA, el DNRPA y la NHTSA, sin salir a internet.

Uso:
    python3 pruebas_de_las_fuentes.py

Por qué existe: la app lee tres APIs públicas (ver «FUENTES OFICIALES DE AFUERA» en
logica/salud.py y consultar_vin_en_nhtsa() en logica/mecanico.py), y la única forma de saber si
las lee bien era mirar la pantalla en el servidor. Así quedó guardada en la base real una
«inflación de agosto» de −21,5%: la serie traía la variación mensual y se la dividía como si
fuera el índice. Acá se le dan respuestas con la forma de cada API —la del índice, la de la
variación como fracción y como porcentaje, una rota— y se controla lo que sale.

Nunca toca la base de trabajo ni sale a internet: corre en una carpeta temporal y reemplaza el
pedido a la red por las respuestas de muestra.
"""
import json
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


def _con_respuestas(g, respuestas):
    """Reemplaza _pedir_json() por uno que contesta según el principio de la URL."""
    def falso(url, tiempo_maximo=4):
        for prefijo, respuesta in respuestas.items():
            if url.startswith(prefijo):
                return respuesta
        return None
    g["_pedir_json"] = falso


# El IPC: índice (base dic-2016 = 100). Agosto subió 1,9% sobre julio, julio 2,4% sobre junio.
_INDICE = {"data": [["2026-08-01", 9234.56], ["2026-07-01", 9062.37], ["2026-06-01", 8849.97]],
           "count": 3, "meta": [{"frequency": "month"}]}
# La misma información como variación mensual: es lo que traía la serie que se usaba.
_VARIACION_FRACCION = {"data": [["2026-08-01", 0.019], ["2026-07-01", 0.0242]]}
_VARIACION_PORCENTAJE = {"data": [["2026-08-01", 1.9], ["2026-07-01", 2.42]]}
_ROTA = {"data": [["2026-08-01", 9234.56], ["2026-07-01", 0.0242]]}

_BCRA = {"status": 200, "metadata": {"resultset": {"count": 2}},
         "results": [{"fecha": "2026-09-25", "detalle": [
                          {"codigoMoneda": "USD", "descripcion": "DOLAR E.E.U.U.",
                           "tipoPase": 1.0, "tipoCotizacion": 1490.0}]},
                     {"fecha": "2026-09-26", "detalle": [
                          {"codigoMoneda": "USD", "descripcion": "DOLAR E.E.U.U.",
                           "tipoPase": 1.0, "tipoCotizacion": 1500.0}]}]}
_MINORISTA = [{"casa": "oficial", "compra": 1495.0, "venta": 1545.0, "fecha": "2026-09-26"},
              {"casa": "oficial", "compra": 1450.0, "venta": 1500.0, "fecha": "2026-08-27"}]
_MINORISTA_MAL_LEIDO = [{"casa": "oficial", "compra": 14950.0, "venta": 15450.0,
                         "fecha": "2026-09-26"}]

_VPIC = {"Count": 1, "Message": "Results returned successfully",
         "Results": [{"Make": "FIAT", "Manufacturer": "FIAT AUTOMOVEIS SA",
                      "Model": "Palio", "ModelYear": "2012", "DisplacementL": "1.4",
                      "EngineCylinders": "4", "FuelTypePrimary": "Gasoline",
                      "BodyClass": "Hatchback", "PlantCity": "BETIM",
                      "PlantCountry": "BRAZIL", "ErrorText": "0 - VIN decoded clean."}]}


# El portal del Ministerio de Justicia es un CKAN: package_show lista los archivos del dataset.
_PORTAL = {"success": True, "result": {"name": "transferencias-de-autos", "resources": [
    {"name": "DNRPA. Transferencias de autos - 202607", "format": "CSV",
     "url": "https://datos.jus.gob.ar/dataset/x/resource/a/download/dnrpa-transferencias-autos-202607.csv"},
    {"name": "DNRPA. Transferencias de autos - 202608", "format": "CSV",
     "url": "https://datos.jus.gob.ar/dataset/x/resource/b/download/dnrpa-transferencias-autos-202608.csv"},
    {"name": "DNRPA. Transferencias de autos - 2025", "format": "ZIP",
     "url": "https://datos.jus.gob.ar/dataset/x/resource/c/download/dnrpa-transferencias-autos-2025.zip"}]}}
# El encabezado, tal cual la documentación oficial del dataset.
_ENCABEZADO_DNRPA = ("tramite_tipo,tramite_fecha,fecha_inscripcion_inicial,registro_seccional_codigo,"
                     "registro_seccional_descripcion,registro_seccional_provincia,automotor_origen,"
                     "automotor_anio_modelo,automotor_tipo_codigo,automotor_tipo_descripcion,"
                     "automotor_marca_codigo,automotor_marca_descripcion,automotor_modelo_codigo,"
                     "automotor_modelo_descripcion,automotor_uso_codigo,automotor_uso_descripcion,"
                     "titular_tipo_persona,titular_domicilio_localidad,titular_domicilio_provincia,"
                     "titular_genero,titular_anio_nacimiento,titular_pais_nacimiento,"
                     "titular_porcentaje_titularidad,titular_domicilio_provincia_id,"
                     "titular_pais_nacimiento_id")


def _renglon_dnrpa(provincia, marca, modelo, anio):
    return (f"TRANSFERENCIA NACIONAL,2026-08-03,2010-05-04,1001,CAPITAL FEDERAL N° 1,{provincia},N,"
            f"{anio},A,SEDAN 5 PUERTAS,X,{marca},Y,\"{modelo}\",1,Privado,Física,UNA LOCALIDAD,"
            f"{provincia},Masculino,1970,ARGENTINA,100,02,200")


_CSV_DNRPA = [_ENCABEZADO_DNRPA] + (
    [_renglon_dnrpa("Buenos Aires", "VOLKSWAGEN", "GOL TREND 1.6 PACK I", 2010)] * 5
    + [_renglon_dnrpa("Buenos Aires", "FORD", "KA 1.0 FLY VIRAL", 2008)] * 3
    + [_renglon_dnrpa("Córdoba", "FIAT", "PALIO (326) ATTRACTIVE 5P 1.4 8V", 2014)] * 2
    + [_renglon_dnrpa("Buenos Aires", "MERCEDES-BENZ", "SPRINTER 415 CDI", 2015)])


def probar(L):
    ns = L.todo_lo_de_la_logica()
    g = ns["inflacion_desde"].__globals__
    fallas = []

    def esperar(nombre, real, esperado):
        if real != esperado:
            fallas.append(f"{nombre}: dio {real!r}, se esperaba {esperado!r}")

    def cerca(nombre, real, esperado, tol=0.0005):
        if real is None or abs(real - esperado) > tol:
            fallas.append(f"{nombre}: dio {real!r}, se esperaba ≈{esperado!r}")

    # 1. El IPC, venga como venga.
    url_ipc = g["URL_IPC_INDEC"].split("?")[0]
    for nombre, respuesta in (("índice", _INDICE), ("fracción", _VARIACION_FRACCION),
                              ("porcentaje", _VARIACION_PORCENTAJE)):
        _con_respuestas(g, {url_ipc: respuesta})
        ipc = g["_inflacion_mensual_indec"]()
        esperar(f"IPC ({nombre}): último mes", ipc.get("mes"), "2026-08")
        cerca(f"IPC ({nombre}): agosto", ipc.get("variacion"), 0.019, tol=0.0002)
    # Una serie que mezcla índice y variación no se cree.
    _con_respuestas(g, {url_ipc: _ROTA})
    esperar("IPC roto", g["_inflacion_mensual_indec"](), {})
    # Si el Estado no contesta, el respaldo de argentinadatos (porcentaje mensual), sin la
    # hiperinflación del 89 que viene al principio de la serie.
    _argdatos = ([{"fecha": "1989-07-31", "valor": 196.6}]
                 + [{"fecha": f"2026-{m:02d}-28", "valor": v}
                    for m, v in ((6, 1.6), (7, 2.42), (8, 1.9))])
    _con_respuestas(g, {g["URL_INFLACION_ARGENTINADATOS"]: _argdatos})
    ipc = g["_inflacion_mensual_indec"]()
    esperar("IPC de respaldo: de dónde vino", (ipc.get("mes"), ipc.get("serie")),
            ("2026-08", "argentinadatos (republica el INDEC)"))
    cerca("IPC de respaldo: agosto", ipc.get("variacion"), 0.019, tol=0.0002)
    _con_respuestas(g, {url_ipc: _INDICE, g["URL_INFLACION_ARGENTINADATOS"]: _argdatos})
    esperar("IPC: el del INDEC antes que el respaldo", g["_inflacion_mensual_indec"]().get("serie"),
            g["SERIES_IPC_INDEC"][0])

    # 2. La inflación desde una fecha: meses ENTEROS después del de la fecha.
    _con_respuestas(g, {url_ipc: _INDICE})
    ipc = g["_inflacion_mensual_indec"]()
    inf, hasta = g["inflacion_desde"]("2026-06-15 10:00:00", ipc)
    cerca("inflación desde junio", inf, (1 + 0.024) * (1 + 0.019) - 1, tol=0.001)
    esperar("inflación desde junio: hasta", hasta, "2026-08")
    esperar("inflación desde agosto", g["inflacion_desde"]("2026-08-20", ipc), (0.0, "2026-08"))

    # 3. Lo guardado antes del arreglo (solo el último mes, −21,5%) no se usa.
    g["guardar_config"]("ultimo_ipc", json.dumps(
        {"mes": "2026-08-01", "variacion": -0.21504964181836306, "_traido": "2026-09-25 19:43:55"}))
    esperar("IPC viejo guardado", g["ipc_guardado"](), {})
    g["guardar_config"]("ultimo_ipc", json.dumps(ipc))
    esperar("IPC nuevo guardado: mes", g["ipc_guardado"]().get("mes"), "2026-08")

    # 4. El dólar: el minorista, controlado con el BCRA.
    url_bcra = g["URL_DOLAR_BCRA"].split("?")[0]
    url_min = g["URL_DOLAR_OFICIAL"]
    _con_respuestas(g, {url_bcra: _BCRA, url_min: _MINORISTA})
    d = g["_dolar_oficial"]()
    esperar("dólar: venta", d.get("venta"), 1545.0)
    esperar("dólar: fecha", d.get("fecha"), "2026-09-26")
    cerca("dólar: variación 30 días", d["variacion"].get("30"), 1545 / 1500 - 1)
    _con_respuestas(g, {url_bcra: _BCRA, url_min: _MINORISTA_MAL_LEIDO})
    esperar("dólar mal leído: se usa el BCRA", g["_dolar_oficial"]().get("venta"), 1500.0)
    _con_respuestas(g, {url_bcra: _BCRA})
    esperar("dólar sin el minorista: BCRA", g["_dolar_oficial"]().get("venta"), 1500.0)
    _con_respuestas(g, {url_min: _MINORISTA})
    esperar("dólar sin el BCRA: minorista", g["_dolar_oficial"]().get("venta"), 1545.0)
    _con_respuestas(g, {})
    esperar("dólar sin ninguna", g["_dolar_oficial"](), {})

    # 5. Una lista en dólares toma el dólar guardado como coeficiente.
    g["c"].execute("INSERT INTO marcas (nombre, tipo) VALUES ('PRUEBA USD', 'PROVEEDOR')")
    mid = g["c"].execute("SELECT id FROM marcas WHERE nombre = 'PRUEBA USD'").fetchone()[0]
    g["guardar_config"]("ultimo_dolar", json.dumps({"venta": 1545.0, "fecha": "2026-09-26"}))
    esperar("coeficiente sin dólares", g["coeficiente_de_lista"](mid), 1.0)
    g["guardar_coeficiente_de_lista"](mid, 1545.0, True, en_dolares=True)
    esperar("coeficiente en dólares", g["coeficiente_de_lista"](mid), 1545.0)
    g["guardar_config"]("ultimo_dolar", json.dumps({"venta": 1600.0, "fecha": "2026-10-01"}))
    esperar("coeficiente en dólares, al día siguiente", g["coeficiente_de_lista"](mid), 1600.0)

    # 6. El parque automotor del DNRPA.
    _con_respuestas(g, {g["URL_PORTAL_JUSTICIA"].split("{")[0]: _PORTAL})
    url, mes = g["archivo_mas_reciente_del_parque"]("transferencias-de-autos")
    esperar("DNRPA: el mes más reciente", mes, "202608")
    cuenta = g["contar_el_parque"](iter(_CSV_DNRPA))
    esperar("DNRPA: Gol en Buenos Aires", cuenta.get(("BUENOS AIRES", "VOLKSWAGEN", "GOL", 2010)), 5)
    esperar("DNRPA: Mercedes-Benz", cuenta.get(("BUENOS AIRES", "MERCEDES BENZ", "SPRINTER", 2015)), 1)
    esperar("DNRPA: provincia con tilde", cuenta.get(("CORDOBA", "FIAT", "PALIO", 2014)), 2)
    esperar("DNRPA: palabra del modelo", [g["palabra_del_modelo"](x) for x in
                                          ("208 ACTIVE 1.6", "S10 2.8 TDI", "KA 1.0", "1.6 ALGO")],
            ["208", "S10", "KA", "ALGO"])
    g["_renglones_de"] = lambda _url: iter(_CSV_DNRPA)
    resumen = g["actualizar_parque_automotor"](forzar=True) or {}
    esperar("DNRPA: autos guardados", (resumen.get("parque") or {}).get("autos"), 11)
    esperar("DNRPA: 0 km guardados", (resumen.get("0km") or {}).get("autos"), 11)
    esperar("DNRPA: de qué días son", ((resumen.get("parque") or {}).get("desde"),
                                       (resumen.get("parque") or {}).get("hasta")),
            ("2026-08-03", "2026-08-03"))
    esperar("DNRPA: cada uno de su dataset",
            [(resumen.get(k) or {}).get("dataset") for k in ("parque", "0km")],
            ["transferencias-de-autos", "inscripciones-iniciales-de-autos"])
    columnas = [r[1] for r in g["c"].execute("PRAGMA table_info(parque_automotor)").fetchall()]
    esperar("DNRPA: no se guarda nada de los titulares",
            [x for x in columnas if x.startswith("titular")], [])
    esperar("DNRPA: provincias (transferencias y 0 km)", g["provincias_del_parque"](),
            [("BUENOS AIRES", 18), ("CORDOBA", 4)])
    for desc in ("JTA TAPA CIL. VW GOL 1.6", "Sonda lambda Volkswagen Gol Trend", "BOMBA AGUA FORD KA",
                 "FILTRO KA", "Junta tapa Fiat Palio 1.4"):
        g["c"].execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
                       "VALUES (?, ?, ?, ?)", (desc[:8], desc[:8].replace(" ", ""), desc, mid))
    autos = {(a["Marca"], a["Modelo"]): a["Productos que lo nombran"]
             for a in g["autos_que_mas_circulan_contra_el_catalogo"]("BUENOS AIRES")}
    esperar("DNRPA: productos que nombran el Gol", autos.get(("VOLKSWAGEN", "GOL")), 2)
    esperar("DNRPA: «FILTRO KA» sin la marca no cuenta", autos.get(("FORD", "KA")), 1)
    esperar("DNRPA: el Palio es de Córdoba", ("FIAT", "PALIO") in autos, False)
    esperar("DNRPA: no se vuelve a bajar enseguida", g["actualizar_parque_automotor"](), None)
    cero = g["cero_km_contra_el_catalogo"]("BUENOS AIRES")
    esperar("DNRPA: 0 km con su columna", [(a["Modelo"], a.get("Se patentaron"),
                                            a["Productos que lo nombran"]) for a in cero],
            [("GOL", 5, 2), ("KA", 3, 1), ("SPRINTER", 1, 0)])
    esperar("DNRPA: los 0 km no dicen años", any("Años" in a for a in cero), False)
    esperar("DNRPA: un CSV sin las columnas no cuenta nada",
            g["contar_el_parque"](iter(["a,b,c", "1,2,3"])), {})

    # 6b. El IPC de transporte: el código de la serie sale del buscador oficial, no a mano.
    _hallado = {"field": {"id": "999.9_TRANSPORTE_NAC", "frequency": "R/P1M",
                          "title": "ipc_transporte_nacional", "units": "Índice",
                          "description": "Índice de Precios al Consumidor. Transporte. Nacional. "
                                         "Base diciembre 2016. Valores mensuales.",
                          "time_index_end": "2026-08-01"},
                "dataset": {"source": "Instituto Nacional de Estadística y Censos (INDEC)"}}
    _interanual = {"field": dict(_hallado["field"], id="1.1_INTERANUAL", units="Variación interanual",
                                 description="IPC. Transporte. Nacional. Variación interanual.")}
    _region = {"field": dict(_hallado["field"], id="2.2_GBA",
                             description="Índice de Precios al Consumidor. Transporte. GBA.")}
    _trimestral = {"field": dict(_hallado["field"], id="3.3_TRIM", frequency="R/P3M")}
    _de_otro = {"field": dict(_hallado["field"], id="4.4_OTRO"),
                "dataset": {"source": "Una consultora"}}
    url_buscar = g["URL_BUSCAR_SERIES"].split("?")[0]
    _con_respuestas(g, {url_buscar: {"data": [_interanual, _region, _trimestral, _de_otro, _hallado]},
                        url_ipc: _INDICE})
    esperar("IPC transporte: la serie que corresponde", g["serie_del_ipc_de_transporte"](),
            "999.9_TRANSPORTE_NAC")
    traido = g["actualizar_ipc_de_transporte"](forzar=True) or {}
    esperar("IPC transporte: el último mes", traido.get("mes"), "2026-08")
    esperar("IPC transporte: guardado", g["ipc_de_transporte_guardado"]().get("serie"),
            "999.9_TRANSPORTE_NAC")
    acumulada, _hasta = g["inflacion_desde"]("2026-06-15", g["ipc_de_transporte_guardado"]())
    cerca("IPC transporte: acumulada desde junio", acumulada, 9234.56 / 8849.97 - 1)
    esperar("IPC transporte: no se vuelve a traer enseguida",
            g["actualizar_ipc_de_transporte"](), None)
    _con_respuestas(g, {url_buscar: {"data": [_interanual, _region]}})
    esperar("IPC transporte: si el buscador no trae la serie, nada", g["serie_del_ipc_de_transporte"](),
            None)
    _con_respuestas(g, {})
    esperar("IPC transporte: sin internet, nada", g["serie_del_ipc_de_transporte"](), None)

    # 7. El BCRA: cheques denunciados, Central de Deudores y el CUIT.
    import requests as _rq

    class _R:
        def __init__(self, estado, cuerpo):
            self.status_code, self._cuerpo = estado, cuerpo

        def json(self):
            return self._cuerpo
    _respuestas_bcra = {
        "/cheques/v1.0/entidades": (200, {"status": 200, "results": [
            {"codigoEntidad": 11, "denominacion": "BANCO DE LA NACION ARGENTINA"},
            {"codigoEntidad": 7, "denominacion": "BANCO DE GALICIA Y BUENOS AIRES S.A."}]}),
        # El ejemplo de la documentación oficial (Cheques Denunciados v1.0).
        "/denunciados/11/20377516": (200, {"status": 200, "results": {
            "numeroCheque": 20377516, "denunciado": True, "fechaProcesamiento": "2024-05-24",
            "denominacionEntidad": "BANCO DE LA NACION ARGENTINA",
            "detalles": [{"sucursal": 524, "numeroCuenta": 5240055962,
                          "causal": "Denunciado por tercero"}]}}),
        "/denunciados/11/12345678": (404, {"status": 404, "errorMessages": ["No se encontró"]}),
        "/Deudas/33693450239": (200, {"status": 200, "results": {
            "identificacion": 33693450239, "denominacion": "TALLER DE PRUEBA SA",
            "periodos": [{"periodo": "202607", "entidades": [
                             {"entidad": "BANCO A", "situacion": 1, "monto": 120.0,
                              "diasAtrasoPago": 0}]},
                         {"periodo": "202608", "entidades": [
                             {"entidad": "BANCO A", "situacion": 1, "monto": 130.0,
                              "diasAtrasoPago": 0},
                             {"entidad": "TARJETA B", "situacion": 3, "monto": 45.5,
                              "diasAtrasoPago": 75, "refinanciaciones": True,
                              "procesoJud": True, "situacionJuridica": False}]}]}}),
        "/Deudas/30500010912": (404, {"status": 404}),
        # El período con guion, como en otros ejemplos de la misma API.
        "/Deudas/20111111112": (200, {"status": 200, "results": {
            "denominacion": "OTRO", "periodos": [{"periodo": "2026-08", "entidades": [
                {"entidad": "BANCO C", "situacion": 1, "monto": 1.0, "situacionJuridica": True}]}]}}),
        # Historicas: el formato de la especificación OpenAPI (HistorialDeuda).
        "/Historicas/33693450239": (200, {"status": 200, "results": {
            "identificacion": 33693450239, "denominacion": "TALLER DE PRUEBA SA",
            "periodos": [{"periodo": p, "entidades": [
                             {"entidad": "BANCO A", "situacion": 1, "monto": 100.0},
                             {"entidad": "TARJETA B", "situacion": sit, "monto": 40.0}]}
                         for p, sit in (("202601", 1), ("202602", 1), ("202603", 2),
                                        ("202604", 1), ("202605", 1), ("202606", 1),
                                        ("202607", 1), ("202608", 3))]}}),
        "/Historicas/30500010912": (404, {"status": 404}),
        # ChequesRechazados: el formato de la especificación OpenAPI (ChequeRechazado).
        "/ChequesRechazados/33693450239": (200, {"status": 200, "results": {
            "identificacion": 33693450239, "denominacion": "TALLER DE PRUEBA SA",
            "causales": [{"causal": "SIN FONDOS SUFICIENTES", "entidades": [
                {"entidad": 44, "detalle": [
                    {"nroCheque": 12345678.0, "fechaRechazo": "2026-05-10", "monto": 50000.0,
                     "fechaPago": None, "fechaPagoMulta": None, "estadoMulta": None,
                     "ctaPersonal": True, "denomJuridica": None, "enRevision": False,
                     "procesoJud": False},
                    {"nroCheque": 12345679.0, "fechaRechazo": "2026-02-01", "monto": 20000.0,
                     "fechaPago": "2026-02-20", "ctaPersonal": True}]}]},
                {"causal": "DEFECTOS FORMALES", "entidades": [
                    {"entidad": 11, "detalle": [
                        {"nroCheque": 555.0, "fechaRechazo": "2026-07-01", "monto": 1000.0,
                         "fechaPago": None}]}]}]}}),
        "/ChequesRechazados/30500010912": (404, {"status": 404}),
    }
    _original = _rq.get

    def _falso_get(url, *a, **k):
        for clave, (estado, cuerpo) in _respuestas_bcra.items():
            if url.endswith(clave):
                return _R(estado, cuerpo)
        return _R(500, None)
    _rq.get = _falso_get
    try:
        esperar("CUIT válido", g["cuit_valido"]("33-69345023-9"), "33693450239")
        esperar("CUIT con el dígito mal", g["cuit_valido"]("33-69345023-8"), None)
        esperar("bancos del BCRA", g["bancos_del_bcra"](),
                [(7, "BANCO DE GALICIA Y BUENOS AIRES S.A."), (11, "BANCO DE LA NACION ARGENTINA")])
        ch, err = g["consultar_cheque"](11, "20.377.516")
        esperar("cheque denunciado", (err, ch["denunciado"], ch["detalles"][0][2]),
                (None, True, "Denunciado por tercero"))
        ch, err = g["consultar_cheque"](11, "12345678")
        esperar("cheque que no figura", (err, ch["denunciado"]), (None, False))
        ch, err = g["consultar_cheque"](99, "1")
        esperar("cheque sin respuesta", (ch, bool(err)), (None, True))
        sit, err = g["situacion_en_el_bcra"]("33-69345023-9")
        esperar("deudor: peor situación del último período", (err, sit["peor"], sit["periodo"],
                                                              len(sit["deudas"])),
                (None, 3, "2026-08", 2))
        esperar("deudor: lo que marca el banco", [d[4] for d in sit["deudas"]],
                ["", "en juicio, refinanciada"])
        sit, err = g["situacion_en_el_bcra"]("20-11111111-2")
        esperar("deudor: período con guion y concurso", (err, sit["periodo"], sit["deudas"][0][4]),
                (None, "2026-08", "concurso o quiebra"))
        hist, err = g["historia_en_el_bcra"]("33-69345023-9")
        esperar("historia: meses, peor y total", (err, len(hist["meses"]), hist["meses"][2],
                                                  hist["meses"][-1][0]),
                (None, 8, ("2026-03", 2, 140.0), "2026-08"))
        esperar("historia: empeoró", hist["tendencia"], "empeoró")
        hist, err = g["historia_en_el_bcra"]("30-50001091-2")
        esperar("historia: no figura", (err, hist["meses"], hist["tendencia"]), (None, [], ""))
        rech, err = g["cheques_rechazados_en_el_bcra"]("33-69345023-9")
        esperar("cheques rechazados: todos, el más nuevo primero",
                (err, [(f, c_, n) for f, c_, n, _m, _p in rech["cheques"]]),
                (None, [("2026-07-01", "Defectos formales", "555"),
                        ("2026-05-10", "Sin fondos suficientes", "12345678"),
                        ("2026-02-01", "Sin fondos suficientes", "12345679")]))
        esperar("cheques rechazados: sin pagar", (rech["sin_pagar"], rech["monto_sin_pagar"]),
                (2, 51000.0))
        rech, err = g["cheques_rechazados_en_el_bcra"]("30-50001091-2")
        esperar("cheques rechazados: no figura", (err, rech["cheques"], rech["sin_pagar"]),
                (None, [], 0))
        rech, err = g["cheques_rechazados_en_el_bcra"]("20-11111111-1")
        esperar("cheques rechazados: CUIT inválido", (rech, bool(err)), (None, True))
        sit, err = g["situacion_en_el_bcra"]("30-50001091-2")
        esperar("sin deudas informadas", (err, sit["deudas"], sit["peor"]), (None, [], 0))
        sit, err = g["situacion_en_el_bcra"]("20-11111111-1")
        esperar("deudor: CUIT inválido no sale a consultar", (sit, bool(err)), (None, True))
    finally:
        _rq.get = _original

    # 8. La NHTSA.
    import requests

    class _Respuesta:
        status_code = 200

        def json(self):
            return _VPIC
    original = requests.get
    requests.get = lambda *a, **k: _Respuesta()
    try:
        datos, error = ns["consultar_vin_en_nhtsa"]("9BD17834MC4383475")
    finally:
        requests.get = original
    esperar("NHTSA: error", error, None)
    esperar("NHTSA: marca y modelo", (datos or {}).get("marca"), "FIAT")
    esperar("NHTSA: motor", (datos or {}).get("motor"), "1.4L 4cil Gasoline")

    # 9. La NHTSA: campañas de seguridad y reclamos por componente.
    esperar("componente: freno de mano antes que frenos",
            ns["componente_en_castellano"]("PARKING BRAKE:CONVENTIONAL"), "Freno de mano")
    esperar("componente: motor y refrigeración",
            ns["componente_en_castellano"]("ENGINE AND ENGINE COOLING:ENGINE"),
            "Motor y refrigeración")
    esperar("componente: no se reconoce", ns["componente_en_castellano"]("ALGO RARO"), None)
    esperar("reclamo con coma adentro del nombre",
            ns["_componentes_del_reclamo"]("SERVICE BRAKES, HYDRAULIC,ENGINE"), ["Frenos", "Motor"])
    esperar("reclamo sin nada reconocible", ns["_componentes_del_reclamo"](""), ["Otro"])
    esperar("modelo: F150 es F-150", ns["el_mismo_modelo"]("F150", ["RANGER", "F-150"]), "F-150")
    esperar("modelo: CRUZE es CRUZE", ns["el_mismo_modelo"]("CRUZE", ["CRUZE LIMITED", "CRUZE"]),
            "CRUZE")
    esperar("modelo: CRUZE es CRUZE LIMITED", ns["el_mismo_modelo"]("CRUZE", ["CRUZE LIMITED"]),
            "CRUZE LIMITED")
    esperar("modelo: el Gol no es el Golf", ns["el_mismo_modelo"]("GOL", ["GOLF", "JETTA"]), None)
    esperar("marca: VW", ns["marca_para_la_nhtsa"]("vw"), "VOLKSWAGEN")
    esperar("marca: Mercedes", ns["marca_para_la_nhtsa"]("MERCEDES BENZ"), "MERCEDES-BENZ")
    _campanias = {"Count": 1, "Message": "Results returned successfully", "results": [
        {"Manufacturer": "Ford Motor Company", "NHTSACampaignNumber": "20V332000",
         "parkIt": False, "parkOutSide": False, "ReportReceivedDate": "02/06/2020",
         "Component": "SEAT BELTS:FRONT:RETRACTORS", "Summary": "The seat belt may not lock.",
         "Consequence": "Increased risk of injury.", "Remedy": "Dealers will replace it.",
         "ModelYear": "2019", "Make": "FORD", "Model": "RANGER"}]}
    _reclamos = {"count": 3, "message": "Results returned successfully", "results": [
        {"odiNumber": 1, "crash": False, "fire": False,
         "components": "SERVICE BRAKES, HYDRAULIC,ENGINE", "summary": "..."},
        {"odiNumber": 2, "crash": True, "fire": False, "components": "POWER TRAIN"},
        {"odiNumber": 3, "crash": False, "fire": True, "components": "SERVICE BRAKES"}]}
    _modelos = {"Count": 2, "results": [{"modelYear": "2019", "make": "FORD", "model": "RANGER"},
                                         {"modelYear": "2019", "make": "FORD", "model": "F-150"}]}
    pedidas = []
    _respuestas_nhtsa = {"https://api.nhtsa.gov/recalls/": _campanias,
                         "https://api.nhtsa.gov/complaints/": _reclamos,
                         "https://api.nhtsa.gov/products/": _modelos}

    def _nhtsa_falsa(url, tiempo_maximo=4):
        pedidas.append(url)
        return next((r for prefijo, r in _respuestas_nhtsa.items() if url.startswith(prefijo)),
                    None)
    g["_pedir_json"] = _nhtsa_falsa
    ns["del_proceso"]("lo_traido_de_la_nhtsa", dict).clear()
    esperar("modelos de la NHTSA", ns["modelos_en_la_nhtsa"]("FORD", 2019), ["F-150", "RANGER"])
    datos, error = ns["fallas_reportadas"]("Ford", "Ranger", 2019)
    esperar("fallas: sin error", error, None)
    esperar("fallas: la campaña", [(x["numero"], x["componente"], x["no_usar"])
                                   for x in (datos or {}).get("campanias", [])],
            [("20V332000", "Cinturones de seguridad", False)])
    esperar("fallas: reclamos", (datos or {}).get("reclamos"), 3)
    esperar("fallas: por componente", (datos or {}).get("por_componente"),
            [("Frenos", 2, 0, 1), ("Caja y transmisión", 1, 1, 0), ("Motor", 1, 0, 0)])
    esperar("fallas: el modelo va en mayúsculas en la consulta",
            any("model=RANGER" in u and "make=FORD" in u for u in pedidas), True)
    antes = len(pedidas)
    ns["fallas_reportadas"]("Ford", "Ranger", 2019)
    esperar("fallas: la segunda vez no sale a internet", len(pedidas), antes)
    ns["fallas_reportadas"]("MERCEDES BENZ", "SPRINTER", 2019)
    esperar("fallas: Mercedes como la escribe la NHTSA",
            any("make=MERCEDES-BENZ" in u for u in pedidas), True)
    g["_pedir_json"] = lambda url, tiempo_maximo=4: None
    ns["del_proceso"]("lo_traido_de_la_nhtsa", dict).clear()
    esperar("fallas: sin internet, el error", bool(ns["fallas_reportadas"]("FORD", "RANGER", 2019)[1]),
            True)
    esperar("fallas: sin año", bool(ns["fallas_reportadas"]("FORD", "RANGER", "")[1]), True)
    return fallas


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_fuentes_")
    try:
        fallas = probar(_cargar_la_logica(carpeta))
        for f in fallas:
            print("   ✗", f)
        print("✅ fuentes de afuera: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

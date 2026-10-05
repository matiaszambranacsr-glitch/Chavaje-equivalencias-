"""Pruebas de las FUENTES DE AFUERA: el INDEC, el BCRA y la NHTSA, sin salir a internet.

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

    # 6. La NHTSA.
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

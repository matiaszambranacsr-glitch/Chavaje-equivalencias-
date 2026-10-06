"""Pruebas del interés por mora de las cuentas corrientes (con la tasa del BCRA).

Uso:
    python3 pruebas_de_las_cuentas.py

Con fechas fijas, para que las cuentas se puedan hacer a mano. Ver «INTERÉS POR MORA» en
logica/mecanico.py. Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import json
import os
import shutil
import sys
import tempfile
from datetime import date, datetime


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

    ns["crear_mecanico"]("Taller Gómez", "clave-de-prueba-2")
    taller = c.execute("SELECT id FROM mecanicos WHERE nombre = 'Taller Gómez'").fetchone()[0]
    ns["configurar_cuenta_de_taller"](taller, 0, 30, False)

    def movimiento(fecha, concepto, importe, vence=None):
        c.execute("INSERT INTO movimientos_de_cuenta (mecanico_id, fecha, concepto, importe, vence)"
                  " VALUES (?, ?, ?, ?, ?)", (taller, fecha, concepto, importe, vence))
        conn.commit()
        return c.lastrowid
    # Un cargo de 100.000 que venció el 31/1, otro de 50.000 que venció el 1/3, y un pago de
    # 120.000: cubre el primero entero y 20.000 del segundo. Quedan 30.000 vencidos desde el 1/3.
    movimiento("2026-01-01 10:00:00", "Repuestos enero", 100000, "2026-01-31")
    movimiento("2026-01-30 10:00:00", "Repuestos febrero", 50000, "2026-03-01")
    movimiento("2026-02-15 10:00:00", "Pago", -120000)

    calc = ns["interes_por_mora"](taller, 60, hoy=date(2026, 3, 31))
    esperar("solo lo impago del segundo cargo",
            [(r["Cargo"], r["Impago"], r["Días"]) for r in calc["renglones"]],
            [("Repuestos febrero", 30000.0, 30)])
    esperar("interés: 30.000 × 60% × 30/365", calc["total"], round(30000 * 0.6 * 30 / 365, 2))
    esperar("antes de vencer, nada", ns["interes_por_mora"](taller, 60, hoy=date(2026, 1, 15))["total"],
            0.0)
    ok, _ = ns["cargar_el_interes_por_mora"](taller, 60, "prueba", usuario="ana",
                                             hoy=date(2026, 1, 15))
    esperar("sin vencido no se carga", ok, False)

    ok, aviso = ns["cargar_el_interes_por_mora"](taller, 60, "prueba", usuario="ana",
                                                 hoy=date(2026, 3, 31))
    esperar("cargado", (ok, aviso), (True, aviso))
    fila = c.execute("SELECT id, importe, vence, date(fecha) FROM movimientos_de_cuenta "
                     "WHERE concepto LIKE 'Interés por mora%'").fetchone()
    esperar("el movimiento", (fila[1], fila[2], fila[3]),
            (round(30000 * 0.6 * 30 / 365, 2), "2026-04-30", "2026-03-31"))
    # Diez días después: cuenta desde el 31/3, no desde el 1/3 otra vez.
    calc = ns["interes_por_mora"](taller, 60, hoy=date(2026, 4, 10))
    esperar("no se cobra dos veces", (calc["desde"], [r["Días"] for r in calc["renglones"]]),
            (date(2026, 3, 31), [10]))
    esperar("los diez días", calc["total"], round(30000 * 0.6 * 10 / 365, 2))
    ns["anular_movimiento_de_cuenta"](fila[0])
    calc = ns["interes_por_mora"](taller, 60, hoy=date(2026, 4, 10))
    esperar("anulado, vuelven a contar todos los días", ([r["Días"] for r in calc["renglones"]],
                                                         calc["desde"]), ([40], None))
    # Un pago que cubre todo: no hay interés.
    movimiento("2026-04-05 10:00:00", "Pago", -30000)
    esperar("pagado todo, nada", ns["interes_por_mora"](taller, 60, hoy=date(2026, 4, 10))["total"],
            0.0)

    # La tasa: la elegida más los puntos; si la elegida no vino, la primera que haya.
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ns["guardar_config"]("tasas_bcra", json.dumps({"traido": ahora, "tasas": {
        "adelantos": {"nombre": "Adelantos en cuenta corriente (empresas)", "tna": 55.2,
                      "fecha": "2026-09-30"},
        "tamar": {"nombre": "TAMAR (bancos privados)", "tna": 38.1, "fecha": ""}}}))
    ns["guardar_configuracion_de_la_mora"]("tamar", 5)
    tna, origen = ns["tasa_de_mora"]()
    esperar("tasa elegida + puntos", tna, 43.1)
    esperar("dice de dónde sale", "TAMAR" in origen and "5" in origen, True)
    ns["guardar_configuracion_de_la_mora"]("personales", 0)
    esperar("si la elegida no vino, la primera que haya", ns["tasa_de_mora"]()[0], 55.2)
    ns["guardar_configuracion_de_la_mora"]("tamar", -3)
    esperar("puntos negativos no", ns["configuracion_de_la_mora"]()["puntos"], 0.0)
    ns["guardar_config"]("tasas_bcra", json.dumps({"traido": ahora, "tasas": {}}))
    esperar("sin tasas, lo dice", ns["tasa_de_mora"]()[0], None)
    return fallas


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_cuentas_")
    try:
        fallas = probar(_cargar_la_logica(carpeta))
        for f in fallas:
            print("   ✗", f)
        print("✅ cuentas: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

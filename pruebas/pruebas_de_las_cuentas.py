"""Pruebas del interés por mora de las cuentas corrientes (con la tasa del BCRA).

Uso:
    python3 pruebas/pruebas_de_las_cuentas.py

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

    # El recargo es de cada cuenta, y viene apagado: sin prenderlo no se carga nada.
    esperar("sin configurar, la cuenta no cobra mora",
            ns["configuracion_de_cuenta"](taller)["cobra_mora"], False)
    ok, _ = ns["cargar_el_interes_por_mora"](taller, 60, "prueba", usuario="ana",
                                             hoy=date(2026, 3, 31))
    esperar("con el recargo apagado no se carga", ok, False)
    ns["configurar_cuenta_de_taller"](taller, 0, 30, False, cobra_mora=True)
    ns["configurar_cuenta_de_taller"](taller, 0, 45, False)
    esperar("cambiar otra cosa no apaga el recargo",
            ns["configuracion_de_cuenta"](taller)["cobra_mora"], True)
    ns["configurar_cuenta_de_taller"](taller, 0, 30, False)
    ok, aviso = ns["cargar_el_interes_por_mora"](taller, 60, "prueba", usuario="ana",
                                                 hoy=date(2026, 3, 31))
    esperar("cargado", (ok, aviso), (True, aviso))
    fila = c.execute("SELECT id, importe, vence, date(fecha, '-3 hours') FROM movimientos_de_cuenta "
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

    # Una base de antes del recargo por cuenta: a la que ya se le cargó un interés le queda
    # prendido; a las demás, apagado. Y correr el esquema otra vez no lo vuelve a prender.
    ns["crear_mecanico"]("Taller Sin Mora", "clave-de-prueba-3")
    otro = c.execute("SELECT id FROM mecanicos WHERE nombre = 'Taller Sin Mora'").fetchone()[0]
    ns["configurar_cuenta_de_taller"](otro, 0, 30, False)
    c.execute("ALTER TABLE cuentas_de_taller DROP COLUMN cobra_mora")
    conn.commit()
    ns["crear_esquema"](c)
    conn.commit()
    esperar("la que ya tenía intereses queda prendida",
            (ns["configuracion_de_cuenta"](taller)["cobra_mora"],
             ns["configuracion_de_cuenta"](otro)["cobra_mora"]), (True, False))
    ns["configurar_cuenta_de_taller"](taller, 0, 30, False, cobra_mora=False)
    ns["crear_esquema"](c)
    conn.commit()
    esperar("apagada a mano, el arranque no la vuelve a prender",
            ns["configuracion_de_cuenta"](taller)["cobra_mora"], False)

    # EL LÍMITE CON VARIOS CARGANDO A LA VEZ (lo señaló una revisión de código con ChatGPT): un
    # taller que debe $90.000 con $100.000 de límite, y ocho cargos de $8.000 al mismo tiempo.
    # Entra uno solo. El saldo se lee lento a propósito, para que todos lleguen a mirarlo antes
    # de que el primero escriba: así se veía la carrera cuando se miraba antes de la transacción.
    import threading
    import time
    ns["crear_mecanico"]("Taller Carrera", "clave-de-prueba-4")
    carrera = c.execute("SELECT id FROM mecanicos WHERE nombre = 'Taller Carrera'").fetchone()[0]
    ns["configurar_cuenta_de_taller"](carrera, 100000, 30, False)
    esperar("la deuda de antes", ns["cargar_a_la_cuenta"](carrera, "Deuda vieja", 90000)[0], True)
    g = ns["cargar_a_la_cuenta"].__globals__
    original = g["estado_de_cuenta"]

    def lento(mid):
        estado = original(mid)
        time.sleep(0.05)
        return estado
    g["estado_de_cuenta"] = lento
    largada = threading.Barrier(8)
    resultados = []

    def vendedor(n):
        largada.wait()
        resultados.append(ns["cargar_a_la_cuenta"](carrera, f"Cargo {n}", 8000)[0])
    hilos = [threading.Thread(target=vendedor, args=(n,)) for n in range(8)]
    try:
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(timeout=60)
    finally:
        g["estado_de_cuenta"] = original
    esperar("ocho cargos a la vez contra el límite: entra uno solo", sorted(resultados),
            [False] * 7 + [True])
    esperar("y la deuda no pasa el límite", ns["estado_de_cuenta"](carrera)["saldo"], 98000.0)

    # EL PERMISO PARA PASAR EL LÍMITE: lo pide el que atiende y lo da solo un administrador.
    ns["crear_mecanico"]("Taller Permiso", "clave-de-prueba-5")
    tp = c.execute("SELECT id FROM mecanicos WHERE nombre = 'Taller Permiso'").fetchone()[0]
    ns["configurar_cuenta_de_taller"](tp, 100000, 30, False)
    esperar("la deuda de antes, al borde", ns["cargar_a_la_cuenta"](tp, "Deuda", 95000)[0], True)
    ok, aviso = ns["cargar_a_la_cuenta"](tp, "Repuestos", 10000)
    esperar("sin permiso no pasa, y dice que se puede pedir",
            (ok, ns["es_por_el_limite"](aviso), ns["SE_PUEDE_PEDIR_PERMISO"] in aviso),
            (False, True, True))
    esperar("cuánto hay que pedir", ns["cuanto_pasa_del_limite"](tp, 10000), 5000.0)
    pedir, contestar = ns["pedir_permiso_de_limite"], ns["contestar_permiso_de_limite"]
    esperar("sin monto, no", pedir(tp, 0, "paga el viernes")[0], False)
    esperar("sin motivo, no", pedir(tp, 5000, "   ")[0], False)
    esperar("una cuenta sin límite no lo necesita", pedir(taller, 5000, "x")[0], False)
    esperar("pedido", pedir(tp, 5000, "paga el viernes", usuario="beto")[0], True)
    esperar("uno a la vez por cuenta", pedir(tp, 8000, "otra vez", usuario="carla")[0], False)
    permiso = ns["permisos_de_limite"](mecanico_id=tp)[0]
    esperar("esperando respuesta",
            (permiso["estado"], permiso["esperando"], permiso["pedido_por"], permiso["importe"],
             ns["cuantos_permisos_esperando"]()), ("pendiente", 1, "beto", 5000.0, 1))
    esperar("pedido no es autorizado", ns["cargar_a_la_cuenta"](tp, "Repuestos", 10000)[0], False)

    def _sin_permiso(funcion, *args, **kwargs):
        try:
            funcion(*args, **kwargs)
            return False
        except PermissionError:
            return True
    originales = (g["_nivel_de_quien_esta_adentro"], g["hay_claves_configuradas"])
    g["hay_claves_configuradas"] = lambda: True
    try:
        g["_nivel_de_quien_esta_adentro"] = lambda: "operador"
        esperar("un empleado no lo autoriza", _sin_permiso(contestar, permiso["id"], True), True)
        esperar("ni lo rechaza", _sin_permiso(contestar, permiso["id"], False), True)
        esperar("ni pasa el límite a mano",
                _sin_permiso(ns["cargar_a_la_cuenta"], tp, "x", 10000, pasar_el_limite=True), True)
        esperar("pero pedirlo, sí", _sin_permiso(pedir, tp, 1000, "x"), False)
        g["_nivel_de_quien_esta_adentro"] = lambda: ""                  # entró sin contraseña
        esperar("sin contraseña, ni pedirlo", _sin_permiso(pedir, tp, 1000, "x"), True)
        esperar("y sigue esperando", ns["permisos_de_limite"](mecanico_id=tp)[0]["estado"],
                "pendiente")
        g["_nivel_de_quien_esta_adentro"] = lambda: "admin"
        esperar("el administrador sí", contestar(permiso["id"], True, "lo conozco",
                                                 usuario="dueño")[0], True)
        esperar("y contestado no se vuelve a contestar", contestar(permiso["id"], False)[0], False)
    finally:
        g["_nivel_de_quien_esta_adentro"], g["hay_claves_configuradas"] = originales
    esperar("quién y cuánto dura", tuple(c.execute(
        "SELECT estado, resuelto_por, nota, ROUND((julianday(vence) - julianday(resuelto_en)) * 24) "
        "FROM permisos_de_credito WHERE id = ?", (permiso["id"],)).fetchone()),
        ("autorizada", "dueño", "lo conozco", float(ns["HORAS_QUE_VALE_UN_PERMISO"])))
    esperar("con el permiso, pasa", ns["cargar_a_la_cuenta"](tp, "Repuestos", 10000)[0], True)
    esperar("y el cargo queda con su número", c.execute(
        "SELECT autorizacion_id FROM movimientos_de_cuenta WHERE mecanico_id = ? "
        "ORDER BY id DESC LIMIT 1", (tp,)).fetchone()[0], permiso["id"])
    esperar("más de lo autorizado, no", ns["cargar_a_la_cuenta"](tp, "Más", 1000)[0], False)
    esperar("una venta con el permiso", ns["permisos_de_limite"](mecanico_id=tp)[0]["usos"], 1)
    esperar("no sirve para otra cuenta", ns["cargar_a_la_cuenta"](carrera, "x", 5000)[0], False)
    esperar("los cambios quedan anotados", sorted({r["Qué"] for r in ns["cambios_registrados"](
        entidad="cuenta") if "límite" in r["Qué"]}),
        ["autorizó pasar el límite", "pidió permiso para pasar el límite"])

    # VENCIDO, el tope vuelve a ser el límite.
    c.execute("UPDATE permisos_de_credito SET vence = datetime('now', 'localtime', '-1 minutes') "
              "WHERE id = ?", (permiso["id"],))
    conn.commit()
    ns["registrar_pago_de_cuenta"](tp, 3000, "Efectivo")
    esperar("vencido, no pasa", ns["cargar_a_la_cuenta"](tp, "x", 4000)[0], False)
    esperar("y ya no está vigente", ns["permisos_de_limite"](mecanico_id=tp)[0]["vigente"], 0)

    # RECHAZADO no suma nada; y lo muy viejo no se contesta ni impide pedir de nuevo.
    esperar("se pide de nuevo", pedir(tp, 4000, "de nuevo")[0], True)
    otro_permiso = ns["permisos_de_limite"](mecanico_id=tp)[0]["id"]
    esperar("no autorizado", contestar(otro_permiso, False, "que pague primero")[0], True)
    esperar("y no pasa", ns["cargar_a_la_cuenta"](tp, "x", 4000)[0], False)
    esperar("otro pedido", pedir(tp, 4000, "otra vez")[0], True)
    viejo = ns["permisos_de_limite"](mecanico_id=tp)[0]["id"]
    c.execute("UPDATE permisos_de_credito SET pedido_en = datetime('now', 'localtime', ?) "
              "WHERE id = ?", (f"-{ns['HORAS_QUE_VALE_UN_PERMISO'] + 1} hours", viejo))
    conn.commit()
    esperar("de hace más de un día no se contesta", contestar(viejo, True)[0], False)
    esperar("ni cuenta como esperando", ns["cuantos_permisos_esperando"](), 0)
    esperar("y se puede pedir otro", pedir(tp, 6000, "hoy")[0], True)
    # EL ADMINISTRADOR PUEDE DAR MENOS de lo pedido.
    nuevo = ns["permisos_de_limite"](mecanico_id=tp)[0]["id"]
    esperar("autoriza otro monto", contestar(nuevo, True, importe=4000)[0], True)
    esperar("el margen es lo autorizado", ns["margen_autorizado"](tp), (4000.0, nuevo))
    esperar("lo que falta pedir descuenta el permiso", ns["cuanto_pasa_del_limite"](tp, 4000), 2000.0)
    esperar("entra lo que cabe", (ns["cargar_a_la_cuenta"](tp, "x", 4000)[0],
                                  ns["cargar_a_la_cuenta"](tp, "x", 2000)[0]), (False, True))

    # EL RECIBO DEL PAGO (ver esa sección en logica/mecanico.py): número, cuánto, cómo, y el
    # saldo de antes y el de después, en texto y en PDF (hoja o ticket).
    ns["guardar_telefono_de_la_cuenta"](tp, "11 4567-8901")
    _saldo_antes = ns["estado_de_cuenta"](tp)["saldo"]
    ns["registrar_pago_de_cuenta"](tp, 1500, "Transferencia", "a cuenta de la semana")
    _pago = ns["pagos_de_la_cuenta"](tp, 1)[0]
    _recibo = ns["recibo_de_pago"](_pago["id"])
    esperar("el recibo: cuánto, cómo y los saldos",
            {k: _recibo[k] for k in ("numero", "importe", "medio", "saldo_antes",
                                     "saldo_despues", "telefono")},
            {"numero": _pago["id"], "importe": 1500.0, "medio": "Transferencia",
             "saldo_antes": round(_saldo_antes, 2), "saldo_despues": round(_saldo_antes - 1500, 2),
             "telefono": "11 4567-8901"})
    _texto_rec = ns["texto_del_recibo"](_recibo)
    esperar("en texto, con la nota y el saldo",
            (_texto_rec.startswith(f"Recibo N° {_pago['id']} — El Chavo — "),
             "Recibimos de Taller Permiso: $1.500" in _texto_rec,
             "Nota: a cuenta de la semana" in _texto_rec,
             f"Saldo actual: ${ns['miles'](_saldo_antes - 1500, 0)}" in _texto_rec),
            (True, True, True, True))
    esperar("en PDF, hoja y ticket; un cargo no tiene recibo",
            (ns["pdf_del_recibo"](_recibo)[:4], ns["pdf_del_recibo"](_recibo, True)[:4],
             ns["recibo_de_pago"](c.execute("SELECT MAX(id) FROM movimientos_de_cuenta WHERE "
                                            "importe > 0").fetchone()[0]),
             ns["texto_del_recibo"](None)), (b"%PDF", b"%PDF", None, ""))
    ns["registrar_pago_de_cuenta"](tp, 100000, "Cheque", cheque_fecha="2030-01-15")
    _rec_ch = ns["recibo_de_pago"](ns["pagos_de_la_cuenta"](tp, 1)[0]["id"])
    esperar("con cheque, la fecha; si queda a favor, lo dice",
            ("Cómo pagó: Cheque (fecha 15/01/2030)" in ns["texto_del_recibo"](_rec_ch),
             "a favor" in ns["texto_del_recibo"](_rec_ch)), (True, _rec_ch["saldo_despues"] < 0))
    esperar("los últimos pagos, el más nuevo primero",
            [p_["importe"] for p_ in ns["pagos_de_la_cuenta"](tp, 2)], [100000.0, 1500.0])

    # LOS CHEQUES PARA DEPOSITAR (ver esa sección en logica/mecanico.py): de todas las cuentas,
    # el que vence primero arriba; vencen a los 30 días de su fecha; «Depositado» los saca.
    from datetime import timedelta as _td
    _hoy = ns["hoy_aca"]()
    for _dias, _imp in ((3, 1000), (28, 2000), (40, 3000)):
        ns["registrar_pago_de_cuenta"](tp, _imp, "Cheque",
                                       cheque_fecha=(_hoy - _td(days=_dias)).isoformat())
    _ch = ns["cheques_sin_depositar"]()
    esperar("todos, el que vence primero arriba, con lo que le falta",
            [(x["importe"], x["se_puede"], x["dias_para_vencer"], x["vencido"]) for x in _ch],
            [(3000.0, True, -10, True), (2000.0, True, 2, False), (1000.0, True, 27, False),
             (100000.0, False, (ns["date"](2030, 1, 15) - _hoy).days + 30, False)])
    ns["invalidar_salud"]()
    _aviso_ch = [p_ for p_ in ns["diagnostico_de_salud"]() if "para depositar" in p_["titulo"]]
    esperar("la campanita: los que ya se pueden, fuerte porque uno venció",
            [(p_["nivel"], p_["titulo"], p_["detalle"].startswith("Uno ya venció"))
             for p_ in _aviso_ch], [("alto", "🏦 3 cheque(s) para depositar ($6.000)", True)])
    _id_b = _ch[1]["id"]
    esperar("depositado, sale; dos veces, no",
            (ns["marcar_cheque_depositado"](_id_b)[0], ns["marcar_cheque_depositado"](_id_b)[0],
             [x["importe"] for x in ns["cheques_sin_depositar"]()]),
            (True, False, [3000.0, 1000.0, 100000.0]))
    # EL CHEQUE RECHAZADO: los depositados hace poco, con «deshacer» y «lo rechazaron».
    esperar("los depositados hace poco",
            [(x["id"], x["importe"]) for x in ns["cheques_depositados"]()], [(_id_b, 2000.0)])
    esperar("deshacer lo vuelve a los que esperan; dos veces, no",
            (ns["deshacer_cheque_depositado"](_id_b)[0], ns["deshacer_cheque_depositado"](_id_b)[0],
             _id_b in [x["id"] for x in ns["cheques_sin_depositar"]()]), (True, False, True))
    ns["marcar_cheque_depositado"](_id_b)
    _antes_r = ns["estado_de_cuenta"](tp)
    esperar("el gasto del banco, ni negativo ni letras",
            (ns["rechazar_cheque"](_id_b, -1)[0], ns["rechazar_cheque"](_id_b, "mucho")[0]),
            (False, False))
    esperar("rechazado: vuelve a la cuenta, con el gasto del banco, ya vencido",
            ns["rechazar_cheque"](_id_b, 350),
            (True, "❌ Cheque rechazado: $2.350 de nuevo en la cuenta (con $350 del banco)."))
    _despues_r = ns["estado_de_cuenta"](tp)
    # (Esta cuenta tiene saldo a favor por el cheque de 2030: lo vencido no se ve acá; el cargo
    # vence ayer, así que en una cuenta que debe ya cuenta como vencido.)
    esperar("el saldo sube, vencido desde ayer; sale de los depositados y de los que esperan",
            (round(_despues_r["saldo"] - _antes_r["saldo"], 2),
             c.execute("SELECT MAX(vence) FROM movimientos_de_cuenta WHERE mecanico_id = ? AND "
                       "concepto LIKE 'Cheque rechazado%'", (tp,)).fetchone()[0],
             ns["cheques_depositados"](),
             _id_b in [x["id"] for x in ns["cheques_sin_depositar"]()],
             ns["rechazar_cheque"](_id_b)[0]),
            (2350.0, (_hoy - _td(days=1)).isoformat(), [], False, False))
    esperar("los dos cargos dicen de qué cheque son",
            [r[0].startswith(("Cheque rechazado del ", "Gasto del banco por el cheque rechazado "))
             for r in c.execute("SELECT concepto FROM movimientos_de_cuenta WHERE mecanico_id = ? "
                                "ORDER BY id DESC LIMIT 2", (tp,))], [True, True])
    esperar("el aviso al taller",
            ns["mensaje_de_cheque_rechazado"]("Taller Permiso", 2000, 350),
            "Hola Taller Permiso! Te escribimos de El Chavo: el banco nos rechazó el cheque de "
            "$2.000 (y nos cobró $350 por el rechazo). Quedó de nuevo en tu cuenta corriente. "
            "¿Cómo lo querés pagar? ¡Gracias!")
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
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

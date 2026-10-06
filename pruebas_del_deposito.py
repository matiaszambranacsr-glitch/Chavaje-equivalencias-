"""Pruebas del depósito y del descuento de cada cuenta.

Uso:
    python3 pruebas_del_deposito.py

El circuito, como lo trabaja el negocio: el mostrador pide desde el buscador, el depósito lo
busca y lo da de baja, y queda en la cuenta del que se lo lleva para facturarlo. Con el
descuento de esa cuenta, que no se ve en ningún otro lado. Ver logica/deposito.py.

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

    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('PRUEBA', 'PROVEEDOR')")
    marca = c.lastrowid
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio, "
              "stock, ubicacion) VALUES ('F100', 'F100', 'FILTRO DE ACEITE', ?, 10000, 5, 'B2')",
              (marca,))
    filtro = c.lastrowid
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio, "
              "stock, ubicacion) VALUES ('J200', 'J200', 'JUNTA', ?, 2500, NULL, 'A1')", (marca,))
    junta = c.lastrowid
    conn.commit()
    ns["crear_mecanico"]("Taller Pérez", "clave-de-prueba-1")
    taller = c.execute("SELECT id FROM mecanicos WHERE nombre = 'Taller Pérez'").fetchone()[0]

    # El descuento se guarda, se topea y None no lo pisa.
    ns["configurar_cuenta_de_taller"](taller, 0, 30, False, 15)
    esperar("descuento guardado", ns["configuracion_de_cuenta"](taller)["descuento"], 15.0)
    ns["configurar_cuenta_de_taller"](taller, 0, 30, False)
    esperar("descuento=None lo deja", ns["configuracion_de_cuenta"](taller)["descuento"], 15.0)
    ns["configurar_cuenta_de_taller"](taller, 0, 30, False, 500)
    esperar("descuento topeado", ns["configuracion_de_cuenta"](taller)["descuento"],
            ns["DESCUENTO_MAXIMO"])
    ns["configurar_cuenta_de_taller"](taller, 0, 30, False, 15)
    esperar("precio de la cuenta", ns["precio_de_la_cuenta"](10000, 15), 8500.0)

    # Cantidades fuera de rango no se piden.
    esperar("cantidad 0", ns["pedir_al_deposito"](filtro, 0, usuario="mostrador")[0], False)
    esperar("cantidad 51", ns["pedir_al_deposito"](filtro, 51, usuario="mostrador")[0], False)

    # Pedido para la cuenta: aparece pendiente, sin precios, ordenado por ubicación.
    ok, _ = ns["pedir_al_deposito"](filtro, 2, taller, usuario="mostrador", nota="lo espera")
    esperar("pedido a la cuenta", ok, True)
    ok, _ = ns["pedir_al_deposito"](junta, 1, None, usuario="mostrador")
    esperar("pedido de mostrador", ok, True)
    pend = ns["pedidos_pendientes"]()
    esperar("pendientes", len(pend), 2)
    esperar("ordenados por ubicación", [p["ubicacion"] for p in pend], ["A1", "B2"])
    esperar("la cola no trae precios",
            any(k in p for p in pend for k in ("precio", "precio_lista", "importe", "descuento")),
            False)
    id_filtro = next(p["id"] for p in pend if p["producto_id"] == filtro)
    id_junta = next(p["id"] for p in pend if p["producto_id"] == junta)

    # Entregar: stock, venta, movimiento con descuento; y no dos veces.
    ventas_antes = c.execute("SELECT COUNT(*) FROM ventas_registradas").fetchone()[0]
    ok, _ = ns["entregar_pedido"](id_filtro, usuario="deposito")
    esperar("entregado", ok, True)
    esperar("stock bajó", c.execute("SELECT stock FROM productos WHERE id = ?",
                                    (filtro,)).fetchone()[0], 3)
    esperar("venta anotada", c.execute("SELECT COUNT(*) FROM ventas_registradas").fetchone()[0],
            ventas_antes + 1)
    esperar("cargado en la cuenta con el descuento",
            c.execute("SELECT importe FROM movimientos_de_cuenta WHERE mecanico_id = ?",
                      (taller,)).fetchall()[-1][0], 17000.0)
    esperar("saldo de la cuenta", ns["estado_de_cuenta"](taller)["saldo"], 17000.0)
    ok, _ = ns["entregar_pedido"](id_filtro, usuario="deposito")
    esperar("no se entrega dos veces", ok, False)
    esperar("el stock no bajó de nuevo", c.execute("SELECT stock FROM productos WHERE id = ?",
                                                   (filtro,)).fetchone()[0], 3)
    esperar("un solo movimiento", c.execute("SELECT COUNT(*) FROM movimientos_de_cuenta WHERE "
                                            "mecanico_id = ?", (taller,)).fetchone()[0], 1)

    # Sin stock cargado (NULL) se entrega igual y sigue en NULL; Mostrador no carga cuenta.
    ok, _ = ns["entregar_pedido"](id_junta, usuario="deposito")
    esperar("entregado sin stock cargado", ok, True)
    esperar("stock NULL sigue NULL", c.execute("SELECT stock FROM productos WHERE id = ?",
                                               (junta,)).fetchone()[0], None)

    # Para facturar: una por cuenta, con lista, descuento e importe.
    fact = ns["para_facturar"]()
    esperar("cuentas para facturar", sorted(k[1] for k in fact),
            sorted(["Taller Pérez", ns["NOMBRE_DEL_MOSTRADOR"]]))
    renglon = fact[(taller, "Taller Pérez")][0]
    esperar("renglón a facturar", (renglon["precio_lista"], renglon["descuento"],
                                   renglon["importe"]), (10000.0, 15.0, 17000.0))
    esperar("mostrador a precio de lista", fact[(None, ns["NOMBRE_DEL_MOSTRADOR"])][0]["importe"],
            2500.0)
    esperar("marcar facturado", ns["marcar_facturado"]([renglon["id"]]), 1)
    esperar("marcar facturado dos veces", ns["marcar_facturado"]([renglon["id"]]), 0)
    esperar("ya no figura", (taller, "Taller Pérez") in ns["para_facturar"](), False)

    # No hay: va a reposición. Cancelar: no toca nada.
    ns["pedir_al_deposito"](filtro, 1, None, usuario="mostrador")
    pid = ns["pedidos_pendientes"]()[0]["id"]
    esperar("no hay", ns["no_hay_en_el_deposito"](pid, usuario="deposito")[0], True)
    esperar("quedó para reponer", c.execute("SELECT estado FROM pedidos_reposicion WHERE "
                                            "producto_id = ?", (filtro,)).fetchone()[0],
            "pendiente")
    ns["pedir_al_deposito"](filtro, 1, None, usuario="mostrador")
    pid = ns["pedidos_pendientes"]()[0]["id"]
    esperar("cancelar", ns["cancelar_pedido_del_deposito"](pid), True)
    esperar("cancelado no se entrega", ns["entregar_pedido"](pid)[0], False)
    esperar("stock intacto", c.execute("SELECT stock FROM productos WHERE id = ?",
                                       (filtro,)).fetchone()[0], 3)

    # Código de retiro: sin él no se pide; con él sí, y no sirve dos veces.
    ns["configurar_cuenta_de_taller"](taller, 0, 30, True)
    esperar("sin código no", ns["pedir_al_deposito"](filtro, 1, taller, "")[0], False)
    codigo, _ = ns["generar_codigo_de_retiro"](taller)
    esperar("con código sí", ns["pedir_al_deposito"](filtro, 1, taller, codigo)[0], True)
    esperar("el código se gastó", ns["pedir_al_deposito"](filtro, 1, taller, codigo)[0], False)

    # Límite de crédito: contra el precio con descuento, y sumando lo pedido sin entregar.
    # Debe 17.000 y tiene pedido (pendiente) 1 filtro = 8.500. Uno más = 8.500.
    ns["configurar_cuenta_de_taller"](taller, 25500, 30, False)
    esperar("lo pedido sin entregar cuenta para el límite",
            ns["pedir_al_deposito"](filtro, 1, taller)[0], False)
    pendiente = [p["id"] for p in ns["pedidos_pendientes"]() if p["mecanico_id"] == taller]
    esperar("había uno pendiente de la cuenta", len(pendiente), 1)
    ns["cancelar_pedido_del_deposito"](pendiente[0])
    ns["configurar_cuenta_de_taller"](taller, 25000, 30, False)
    esperar("pasa el límite", ns["pedir_al_deposito"](filtro, 1, taller)[0], False)
    ns["configurar_cuenta_de_taller"](taller, 25500, 30, False)
    esperar("justo en el límite", ns["pedir_al_deposito"](filtro, 1, taller)[0], True)
    for p in ns["pedidos_pendientes"]():
        ns["cancelar_pedido_del_deposito"](p["id"])
    ns["configurar_cuenta_de_taller"](taller, 0, 30, True)

    # La cuenta se elige UNA vez: el código se gasta al elegirla y después no se pide más.
    esperar("autorizar sin código", ns["autorizar_retiro"](taller, "")[0], False)
    codigo, _ = ns["generar_codigo_de_retiro"](taller)
    esperar("autorizar con código", ns["autorizar_retiro"](taller, codigo)[0], True)
    esperar("el código ya no sirve", ns["autorizar_retiro"](taller, codigo)[0], False)
    st = ns["st"]
    st.session_state["cuenta_elegida"] = {"id": taller, "nombre": "Taller Pérez",
                                          "desde": ns["time"].time()}
    esperar("cuenta elegida", ns["nombre_de_la_cuenta_elegida"](), "Taller Pérez")
    pedidos, fallas_ = ns["pedir_lo_elegido_al_deposito"]([(filtro, 1), (junta, 2)],
                                                         usuario="mostrador")
    esperar("varios a la cuenta elegida, sin código", (len(pedidos), fallas_), (2, []))
    esperar("quedaron a nombre de la cuenta",
            sorted(p["mecanico_id"] for p in ns["pedidos_pendientes"]()), [taller, taller])
    st.session_state["cuenta_elegida"]["desde"] -= ns["HORAS_DE_LA_CUENTA_ELEGIDA"] * 3600 + 1
    esperar("la cuenta elegida vence", ns["cuenta_elegida"](), None)
    pedidos, _ = ns["pedir_lo_elegido_al_deposito"]([(junta, 1)], usuario="mostrador")
    esperar("vencida, va a Mostrador",
            c.execute("SELECT mecanico_id FROM pedidos_deposito ORDER BY id DESC LIMIT 1"
                      ).fetchone()[0], None)
    for p in ns["pedidos_pendientes"]():
        ns["cancelar_pedido_del_deposito"](p["id"])

    # Cuánto tarda: desde que se pide hasta que se da de baja. Lo cancelado no cuenta.
    esperar("minutos entre", ns["minutos_entre"]("2026-10-06 10:00:00", "2026-10-06 10:12:59"), 12)
    esperar("minutos ilegibles", ns["minutos_entre"]("cualquier cosa"), None)
    esperar("espera corta", ns["como_se_lee_la_espera"](3), "⏱️ 3 min")
    esperar("recién pedido", ns["como_se_lee_la_espera"](0), "⏱️ <1 min")
    esperar("espera amarilla", ns["como_se_lee_la_espera"](12), "🟡 12 min")
    esperar("espera roja", ns["como_se_lee_la_espera"](65), "🔴 1 h 05")
    c.execute("DELETE FROM pedidos_deposito")
    for minutos, quien, estado in ((4, "Juan", "entregado"), (6, "Juan", "entregado"),
                                   (30, "Pedro", "no_hay"), (90, "Pedro", "cancelado")):
        c.execute("""INSERT INTO pedidos_deposito (producto_id, cantidad, estado, resuelto_por,
                                                   pedido_en, resuelto_en)
                     VALUES (?, 1, ?, ?, datetime('now', 'localtime', ?),
                             datetime('now', 'localtime'))""",
                  (filtro, estado, quien, f"-{minutos} minutes"))
    c.execute("""INSERT INTO pedidos_deposito (producto_id, cantidad, estado, resuelto_por,
                                               pedido_en, resuelto_en)
                 VALUES (?, 1, 'entregado', 'Juan', datetime('now', 'localtime', '-20 days'),
                         datetime('now', 'localtime', '-20 days', '+50 minutes'))""", (filtro,))
    conn.commit()
    t = ns["tiempos_del_deposito"](dias=7)
    redondo = lambda r: {k: (round(v) if isinstance(v, float) else v) for k, v in r.items()}
    esperar("tiempos de hoy", redondo(t["periodo"]),
            {"cuantos": 3, "promedio": 13, "mediana": 6, "maximo": 30, "a_tiempo": 67})
    esperar("por persona", {q: r["cuantos"] for q, r in t["por_persona"].items()},
            {"Juan": 2, "Pedro": 1})
    esperar("hoy = período", t["hoy"]["cuantos"], 3)
    esperar("con 30 días entra el viejo", ns["tiempos_del_deposito"](dias=30)["periodo"]["cuantos"],
            4)
    esperar("sin nada", ns["_resumen_de_tiempos"]([])["promedio"], None)

    esperar("últimos resueltos", len(ns["ultimos_pedidos_del_deposito"]()) >= 4, True)
    return fallas


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_deposito_")
    try:
        fallas = probar(_cargar_la_logica(carpeta))
        for f in fallas:
            print("   ✗", f)
        print("✅ depósito: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

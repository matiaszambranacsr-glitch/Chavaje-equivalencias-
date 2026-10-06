"""Prueba de carga: diez personas usando la app a la vez, más el mantenimiento y la copia.

Uso:
    python3 pruebas_de_carga.py            (unos 30 segundos)

Lo propuso una revisión con ChatGPT: «en vez de seguir agregando funciones, una prueba de
estrés». Diez hilos —uno por persona, cada uno con su propia conexión a la base, como cada
sesión de Streamlit— buscan, cambian precios, anotan ventas, apartan stock, piden al depósito,
entregan pedidos (todos compitiendo por los mismos), cargan vínculos y registran pagos. Al
mismo tiempo corren el mantenimiento del día y la copia de seguridad. Al final se controla:

  · que no haya habido NINGÚN error («database is locked» incluido);
  · que la base siga sana (PRAGMA integrity_check);
  · que ningún pedido se haya entregado dos veces ni cargado dos veces en la cuenta;
  · que el saldo de la cuenta sea exactamente lo entregado menos lo pagado;
  · que lo apartado nunca pase el stock;
  · que no se haya perdido ninguna venta anotada.

Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import os
import random
import shutil
import sys
import tempfile
import threading
import time
import traceback

PERSONAS = 10
VUELTAS_POR_PERSONA = 250


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

    # Un catálogo chico: tres marcas, 300 productos; 20 «de mostrador» con stock.
    # Los «escasos» tienen poco stock y todos quieren apartarlos: ahí se ve si el control de
    # lo libre y la reserva van juntos (ver reservar_stock()).
    ids, calientes, escasos = [], [], []
    for m in ("ALFA", "BETA", "GAMMA"):
        c.execute("INSERT INTO marcas (nombre, tipo) VALUES (?, 'PROVEEDOR')", (m,))
        marca = c.lastrowid
        for i in range(100):
            c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, "
                      "precio, stock) VALUES (?, ?, ?, ?, ?, ?)",
                      (f"{m[0]}{i:04d}", f"{m[0]}{i:04d}", f"FILTRO {m} {i}", marca,
                       1000 + i, 500 if i < 7 else 30 if i < 9 else None))
            ids.append(c.lastrowid)
            if i < 7:
                calientes.append(c.lastrowid)
            elif i < 9:
                escasos.append(c.lastrowid)
    conn.commit()
    ns["crear_mecanico"]("Taller Carga", "clave-de-carga-1")
    taller = c.execute("SELECT id FROM mecanicos").fetchone()[0]
    ns["configurar_cuenta_de_taller"](taller, 0, 30, False, 10)

    errores = []
    reservas_ok = {p: 0 for p in escasos}
    pagos = []
    ventas_anotadas = [0]
    candado_cuentas = threading.Lock()
    corriendo = threading.Event()
    corriendo.set()

    def persona(n):
        azar = random.Random(n)
        try:
            for vuelta in range(VUELTAS_POR_PERSONA):
                accion = (vuelta + n) % 8
                pid = azar.choice(ids)
                if accion == 0:
                    ns["buscar_con_variantes_del_cero"](
                        c.execute("SELECT codigo_clean FROM productos WHERE id = ?",
                                  (pid,)).fetchone()[0], "Todas", 3)
                elif accion == 1:
                    # Como el editor de la pantalla: manda el stock que mostraba, y si en el
                    # medio cambió, no lo pisa (ver actualizar_precio_stock()).
                    mostrado = c.execute("SELECT stock FROM productos WHERE id = ?",
                                         (pid,)).fetchone()[0]
                    ns["actualizar_precio_stock"](pid, 1000 + azar.randint(0, 999), mostrado,
                                                  stock_mostrado=mostrado)
                elif accion == 2:
                    ns["registrar_venta"](pid, "carga")
                    with candado_cuentas:
                        ventas_anotadas[0] += 1
                elif accion == 3:
                    escaso = azar.choice(escasos)
                    ok, _ = ns["reservar_stock"](escaso, 3, f"cliente {n}")
                    if ok:
                        with candado_cuentas:
                            reservas_ok[escaso] += 3
                elif accion == 4:
                    ns["pedir_al_deposito"](azar.choice(calientes), 1, taller, usuario=f"v{n}",
                                            retiro_autorizado=True)
                elif accion == 5:
                    # Todos compiten por los mismos pedidos: el primero pendiente.
                    fila = c.execute("SELECT id FROM pedidos_deposito WHERE estado = 'pendiente' "
                                     "ORDER BY id LIMIT 1").fetchone()
                    if fila:
                        ns["entregar_pedido"](fila[0], usuario=f"d{n}")
                elif accion == 6:
                    a, b = sorted(azar.sample(ids, 2))
                    ns["guardar_equivalencias_pendientes"]([(a, b)], "manual", f"carga-{n}")
                else:
                    ok, _ = ns["registrar_pago_de_cuenta"](taller, 100, "Efectivo",
                                                          usuario=f"v{n}")
                    if ok:
                        with candado_cuentas:
                            pagos.append(100)
        except Exception as _err:
            errores.append(f"persona {n}: {type(_err).__name__}: {_err}\n"
                           + traceback.format_exc(limit=4))

    def de_fondo(nombre, funcion):
        try:
            while corriendo.is_set():
                funcion()
                time.sleep(0.05)
        except Exception as _err:
            errores.append(f"{nombre}: {type(_err).__name__}: {_err}\n"
                           + traceback.format_exc(limit=4))

    fondo = [threading.Thread(target=de_fondo, args=("copia", ns["generar_backup_sin_fotos"])),
             threading.Thread(target=de_fondo, args=("salud", ns["diagnostico_de_salud"]))]
    gente = [threading.Thread(target=persona, args=(n,)) for n in range(PERSONAS)]
    inicio = time.monotonic()
    for h in fondo + gente:
        h.start()
    ns["tareas_automaticas_del_dia"](presupuesto_segundos=5)
    for h in gente:
        h.join(timeout=300)
    corriendo.clear()
    for h in fondo:
        h.join(timeout=120)
    duro = time.monotonic() - inicio
    # Lo que quedó pendiente lo entrega uno solo al final, para cerrar las cuentas.
    for (pid_pedido,) in c.execute("SELECT id FROM pedidos_deposito WHERE estado = 'pendiente'"
                                   ).fetchall():
        ns["entregar_pedido"](pid_pedido, usuario="cierre")

    for e in errores[:5]:
        fallas.append(e)
    esperar("errores durante la carga", len(errores), 0)
    esperar("base sana", c.execute("PRAGMA integrity_check").fetchone()[0], "ok")
    # El depósito: cada pedido entregado, con su movimiento, una sola vez.
    entregados = c.execute("SELECT COUNT(*), COUNT(DISTINCT movimiento_id), "
                           "SUM(movimiento_id IS NULL), COALESCE(SUM(importe), 0) "
                           "FROM pedidos_deposito WHERE estado = 'entregado'").fetchone()
    pedidos = c.execute("SELECT COUNT(*) FROM pedidos_deposito").fetchone()[0]
    esperar("todos los pedidos entregados", entregados[0], pedidos)
    esperar("un movimiento distinto por pedido", entregados[1], entregados[0])
    esperar("ningún pedido de cuenta sin cargar", entregados[2], 0)
    cargos = c.execute("SELECT COUNT(*), COALESCE(SUM(importe), 0) FROM movimientos_de_cuenta "
                       "WHERE mecanico_id = ? AND importe > 0", (taller,)).fetchone()
    esperar("cargos en la cuenta = pedidos entregados", cargos[0], entregados[0])
    esperar("saldo = entregado − pagado", round(ns["estado_de_cuenta"](taller)["saldo"], 2),
            round(entregados[3] - sum(pagos), 2))
    # El stock: lo apartado no pasa lo que hay, y lo entregado se descontó.
    for p in calientes:
        stock = c.execute("SELECT stock FROM productos WHERE id = ?", (p,)).fetchone()[0]
        entregado = c.execute("SELECT COALESCE(SUM(cantidad), 0) FROM pedidos_deposito "
                              "WHERE producto_id = ? AND estado = 'entregado'", (p,)).fetchone()[0]
        if stock != max(0, 500 - entregado):
            fallas.append(f"stock de {p}: {stock}, se esperaba {max(0, 500 - entregado)}")
    for p in escasos:
        apartado = c.execute("SELECT COALESCE(SUM(cantidad), 0) FROM reservas_stock "
                             "WHERE producto_id = ? AND estado = 'activa'", (p,)).fetchone()[0]
        if apartado != reservas_ok[p] or apartado > 30:
            fallas.append(f"apartado de {p}: {apartado} sobre 30 (se aceptaron {reservas_ok[p]})")
    # Las ventas: las anotadas por las personas más las de cada entrega.
    ventas = c.execute("SELECT COUNT(*) FROM ventas_registradas").fetchone()[0]
    esperar("ninguna venta perdida", ventas, ventas_anotadas[0] + entregados[0])
    print(f"   {PERSONAS} personas × {VUELTAS_POR_PERSONA} acciones, con copia, salud y "
          f"mantenimiento a la vez: {duro:.1f} s; {pedidos} pedidos, {len(pagos)} pagos, "
          f"{ventas} ventas")
    return fallas


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_carga_")
    try:
        fallas = probar(_cargar_la_logica(carpeta))
        for f in fallas:
            print("   ✗", f)
        print("✅ carga: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

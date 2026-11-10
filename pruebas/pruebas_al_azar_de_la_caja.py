"""La caja, al azar: cientos de operaciones mezcladas, y después de cada una se mira que la
plata, el stock y las cuentas cierren.

Uso:
    python3 pruebas/pruebas_al_azar_de_la_caja.py [--semillas 1,2,3] [--pasos 300]

Las otras pruebas siguen un camino pensado: vender, cobrar, devolver. Los errores de plata
aparecen en los caminos que nadie pensó —cobrar con descuento, volverla a la caja, cobrarla de
nuevo con otro, devolver una parte, corregir cómo pagó—. Acá el camino lo arma el azar (con
semilla fija: si falla, falla siempre igual y dice en qué paso) y lo que se controla no depende
del camino:

  - cada venta vale lo que suman sus renglones, y lo devuelto nunca pasa de lo vendido;
  - sin descuento, cada cosa está al precio de lista (también después de deshacer un cobro);
  - el stock es el del principio menos lo que salió más lo que volvió, y nunca negativo;
  - el saldo de cada cuenta es lo puesto a cuenta menos lo devuelto y lo pagado;
  - el cierre de caja es lo cobrado menos lo devuelto, por cada forma de pago y en total, y lo
    que espera en la caja es lo que espera;
  - lo que espera en la caja no tiene forma de pago, descuento ni cargo en ninguna cuenta.

Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import os
import random
import shutil
import sys
import tempfile

SEMILLAS = (1, 2, 3)
PASOS = 250
DESCUENTOS = (0, 0, 0, 5, 10, 7.5, 33.33, 50)
# Precios con centavos a propósito: es donde un redondeo de ida y vuelta se come un centavo.
# Uno sin stock cargado (no se cuenta) y uno con poco: se vende igual aunque no alcance —si se
# vendió, estaba—, el stock queda en cero y no baja de ahí.
PRODUCTOS = (("AZ1", 12100, 1000), ("AZ2", 999.99, 1000), ("AZ3", 1234.5, 1000),
             ("AZ4", 10.01, 1000), ("AZ5", 15300.37, 1000), ("AZ6", 8750, None),
             ("AZ7", 500, 3))


def _cargar_la_logica(carpeta):
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, raiz)
    os.chdir(carpeta)
    import logica
    return logica


class Caja:
    """La caja de verdad (las funciones de la app) y, al lado, lo que tendría que dar."""

    def __init__(self, ns, azar, marca):
        self.ns, self.azar = ns, azar
        self.c, self.conn = ns["c"], ns["conn"]
        self.lista, self.stock = {}, {}
        for codigo, precio, stock in PRODUCTOS:
            self.c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, "
                           "precio, stock) VALUES (?, ?, 'FILTRO', ?, ?, ?)",
                           (f"{codigo}S{marca}", f"{codigo}S{marca}", marca, precio, stock))
            self.lista[self.c.lastrowid], self.stock[self.c.lastrowid] = precio, stock
        self.conn.commit()
        self.talleres = []
        for nombre, descuento in ((f"Taller A {marca}", 0), (f"Taller B {marca}", 5)):
            ns["crear_mecanico"](nombre, f"clave-{nombre.replace(' ', '-').lower()}")
            taller = self.uno("SELECT id FROM mecanicos WHERE nombre = ?", nombre)
            ns["configurar_cuenta_de_taller"](taller, 0, 30, False, descuento=descuento)
            self.talleres.append(taller)
        self.descuento_de = dict(zip(self.talleres, (0, 5)))
        self.saldo = {t: 0.0 for t in self.talleres}
        # venta -> {estado: esperando | cobrada | cuenta | anulada, d, forma, taller, devuelta,
        #           items: {renglón: [producto, cantidad, devuelto]}}
        self.ventas = {}
        self.hecho = []

    def uno(self, sql, *args):
        fila = self.c.execute(sql, args).fetchone()
        return fila[0] if fila else None

    def _las(self, *estados, sin_devoluciones=False):
        return [v for v, d in self.ventas.items() if d["estado"] in estados
                and not (sin_devoluciones and d["devuelta"])]

    # ---- las operaciones ---------------------------------------------------------------------
    def vender(self):
        azar, ns = self.azar, self.ns
        productos = azar.sample(list(self.lista), azar.randint(1, 3))
        items = [dict(ns["item_de_venta"](p, azar.randint(1, 4))) for p in productos]
        taller = azar.choice([None, None, None] + self.talleres)
        a_la_caja = azar.random() < 0.8
        forma = "" if a_la_caja else azar.choice(ns["FORMAS_DE_PAGO"])
        venta, _ = ns["cerrar_venta"](items, forma_de_pago=forma, mecanico_id=taller,
                                      a_la_caja=a_la_caja)
        # [producto, cantidad, devuelto, lo que bajó del stock: no más de lo que había]
        renglones = {f["id"]: [f["producto_id"], f["cantidad"], 0, 0] for f in self.c.execute(
            "SELECT id, producto_id, cantidad FROM ventas_items WHERE venta_id = ?", (venta,))}
        for renglon in renglones.values():
            producto, cantidad = renglon[0], renglon[1]
            if self.stock[producto] is not None:
                renglon[3] = min(cantidad, self.stock[producto])
                self.stock[producto] -= renglon[3]
        self.ventas[venta] = {"estado": "esperando" if a_la_caja else "cobrada", "d": 0,
                              "forma": forma, "taller": taller, "devuelta": False,
                              "items": renglones}
        return f"vender #{venta}" + ("" if a_la_caja else f" ({forma})")

    def cobrar(self):
        esperando = self._las("esperando")
        if not esperando:
            return None
        venta = self.azar.choice(esperando)
        forma = self.azar.choice(self.ns["FORMAS_DE_COBRO"])
        d = self.azar.choice(DESCUENTOS)
        ok, texto = self.ns["cobrar_venta"](venta, forma, cuotas=self.azar.choice([1, 3, 6]),
                                            descuento=d)
        assert ok, f"no dejó cobrar la #{venta}: {texto}"
        self.ventas[venta].update(estado="cobrada", d=d, forma=forma)
        return f"cobrar #{venta} {forma} -{d}%"

    def a_cuenta(self):
        esperando = self._las("esperando")
        if not esperando:
            return None
        venta = self.azar.choice(esperando)
        taller = self.ventas[venta]["taller"] or self.azar.choice(self.talleres)
        d = self.azar.choice((None,) + DESCUENTOS)
        ok, texto = self.ns["poner_a_cuenta"](venta, taller, descuento=d)
        assert ok, f"no dejó poner a cuenta la #{venta}: {texto}"
        d = self.descuento_de[taller] if d is None else d
        self.ventas[venta].update(estado="cuenta", d=d, forma=self.ns["A_CUENTA"], taller=taller)
        self.saldo[taller] += self.uno("SELECT total FROM ventas WHERE id = ?", venta)
        return f"a cuenta #{venta} -{d}%"

    def devolver(self):
        con_algo = [(v, r) for v in self._las("cobrada", "cuenta")
                    for r, (_p, cantidad, devuelto, _b) in self.ventas[v]["items"].items()
                    if devuelto < cantidad]
        if not con_algo:
            return None
        venta, renglon = self.azar.choice(con_algo)
        producto, cantidad, devuelto, _bajo = self.ventas[venta]["items"][renglon]
        cuantos = self.azar.randint(1, cantidad - devuelto)
        motivo = self.azar.choice(list(self.ns["MOTIVOS_DE_DEVOLUCION"]))
        ok, texto = self.ns["devolver_de_una_venta"](renglon, cuantos, motivo)
        assert ok, f"no dejó devolver de la #{venta}: {texto}"
        self.ventas[venta]["items"][renglon][2] += cuantos
        self.ventas[venta]["devuelta"] = True
        if self.stock[producto] is not None and motivo not in self.ns["NO_VUELVE_AL_STOCK"]:
            self.stock[producto] += cuantos
        if self.ventas[venta]["estado"] == "cuenta":
            self.saldo[self.ventas[venta]["taller"]] -= round(
                cuantos * self.uno("SELECT precio FROM ventas_items WHERE id = ?", renglon), 2)
        return f"devolver {cuantos} de la #{venta} ({motivo})"

    def _anulada(self, venta):
        datos = self.ventas[venta]
        # Vuelve lo que bajó, no lo vendido: si no alcanzaba, bajó menos.
        for producto, _cantidad, _d, bajo in datos["items"].values():
            if self.stock[producto] is not None:
                self.stock[producto] += bajo
        if datos["estado"] == "cuenta":
            self.saldo[datos["taller"]] -= self.uno("SELECT total FROM ventas WHERE id = ?", venta)
        datos["estado"] = "anulada"

    def anular(self):
        vivas = self._las("esperando", "cobrada", "cuenta")
        if not vivas:
            return None
        venta = self.azar.choice(vivas)
        ok, texto = self.ns["anular_venta"](venta)
        assert ok == (not self.ventas[venta]["devuelta"]), \
            f"anular la #{venta} dio {ok} ({texto}) y tiene devoluciones: {self.ventas[venta]['devuelta']}"
        if ok:
            self._anulada(venta)
        return f"anular #{venta}: {'sí' if ok else 'no, tiene devoluciones'}"

    def deshacer(self):
        esperando = self._las("esperando")
        if not esperando:
            return None
        venta = self.azar.choice(esperando)
        ok, texto, _items = self.ns["deshacer_mi_venta"](venta)
        assert ok, f"no dejó deshacer la #{venta}: {texto}"
        self._anulada(venta)
        return f"deshacer #{venta}"

    def corregir_como_pago(self):
        cobradas = self._las("cobrada", "cuenta")
        if not cobradas:
            return None
        venta = self.azar.choice(cobradas)
        datos = self.ventas[venta]
        forma = self.azar.choice(self.ns["FORMAS_DE_PAGO"])
        ok, texto = self.ns["cambiar_como_se_pago"](venta, forma, cuotas=1)
        cuotas = self.uno("SELECT COALESCE(cuotas, 1) FROM ventas WHERE id = ?", venta)
        se_esperaba = (datos["estado"] == "cobrada" and not datos["devuelta"]
                       and not (forma == datos["forma"] and cuotas == 1 and not ok))
        assert ok == se_esperaba or (not ok and "Ya estaba así" in texto), \
            f"corregir cómo pagó la #{venta} dio {ok}: {texto}"
        if ok:
            datos["forma"] = forma
        return f"corregir #{venta} a {forma}: {'sí' if ok else 'no'}"

    def volver(self):
        cobradas = self._las("cobrada", "cuenta")
        if not cobradas:
            return None
        venta = self.azar.choice(cobradas)
        datos = self.ventas[venta]
        en_cuenta = self.uno("SELECT total FROM ventas WHERE id = ?", venta)
        ok, texto = self.ns["volver_a_la_caja"](venta)
        assert ok == (not datos["devuelta"]), f"volver la #{venta} a la caja dio {ok}: {texto}"
        if ok:
            if datos["estado"] == "cuenta":
                self.saldo[datos["taller"]] -= en_cuenta
            datos.update(estado="esperando", d=0, forma="")
        return f"volver #{venta} a la caja: {'sí' if ok else 'no, tiene devoluciones'}"

    def anular_el_cargo(self):
        """El cargo de una venta a cuenta no se anula suelto desde la cuenta corriente."""
        en_cuenta = self._las("cuenta")
        if not en_cuenta:
            return None
        venta = self.azar.choice(en_cuenta)
        ok, texto = self.ns["anular_movimiento_de_cuenta"](
            self.uno("SELECT movimiento_id FROM ventas WHERE id = ?", venta))
        assert not ok, f"dejó anular suelto el cargo de la #{venta}: {texto}"
        return f"anular el cargo de la #{venta}: no"

    def pagar(self):
        taller = self.azar.choice(self.talleres)
        importe = round(self.azar.uniform(100, 30000), 2)
        ok, texto = self.ns["registrar_pago_de_cuenta"](taller, importe, "Efectivo")
        assert ok, f"no dejó registrar el pago: {texto}"
        self.saldo[taller] -= importe
        return f"pago de {importe}"

    # ---- lo que tiene que cerrar, pase lo que pase -------------------------------------------
    def problemas(self):
        mal, c = [], self.c
        totales = {}
        for venta, datos in self.ventas.items():
            v = dict(c.execute("""SELECT total, COALESCE(cobrada, 1) AS cobrada, anulada,
                                         COALESCE(forma_de_pago, '') AS forma,
                                         COALESCE(descuento, 0) AS descuento, movimiento_id,
                                         cobrada_por FROM ventas WHERE id = ?""",
                               (venta,)).fetchone())
            renglones = [dict(f) for f in c.execute(
                "SELECT id, producto_id, cantidad, precio, COALESCE(devuelto, 0) AS devuelto "
                "FROM ventas_items WHERE venta_id = ?", (venta,))]
            totales[venta] = v["total"]
            suma = round(sum(r["cantidad"] * r["precio"] for r in renglones), 2)
            if abs(suma - v["total"]) > 0.005:
                mal.append(f"#{venta}: vale {v['total']} y sus renglones suman {suma}")
            for r in renglones:
                _p, cantidad, devuelto, _bajo = datos["items"][r["id"]]
                anotado = self.uno("SELECT COALESCE(SUM(cantidad), 0) FROM ventas_devoluciones "
                                   "WHERE venta_item_id = ?", r["id"])
                if not (0 <= r["devuelto"] <= r["cantidad"]) or r["devuelto"] != devuelto \
                        or anotado != devuelto:
                    mal.append(f"#{venta}: de {r['cantidad']} figuran devueltos {r['devuelto']}, "
                               f"anotados {anotado}, y se devolvieron {devuelto}")
                lista = self.lista[r["producto_id"]]
                if not datos["d"] and abs(r["precio"] - lista) > 0.001:
                    mal.append(f"#{venta}: sin descuento, el renglón está a {r['precio']} y de "
                               f"lista vale {lista}")
                if datos["d"] and abs(r["precio"] - lista * (1 - datos["d"] / 100)) > 0.0051:
                    mal.append(f"#{venta}: con {datos['d']}% el renglón está a {r['precio']} y de "
                               f"lista vale {lista}")
            if (v["anulada"] == 1) != (datos["estado"] == "anulada"):
                mal.append(f"#{venta}: anulada={v['anulada']} y tendría que estar {datos['estado']}")
            if datos["estado"] == "esperando" and (v["cobrada"] or v["forma"] or v["descuento"]
                                                   or v["movimiento_id"] or v["cobrada_por"]):
                mal.append(f"#{venta}: espera en la caja con restos de un cobro: {v}")
            if datos["estado"] in ("cobrada", "cuenta") and (not v["cobrada"]
                                                             or v["forma"] != datos["forma"]):
                mal.append(f"#{venta}: tendría que estar {datos['estado']} ({datos['forma']}) y "
                           f"dice cobrada={v['cobrada']}, {v['forma']!r}")
            cargo = c.execute("SELECT importe, anulado FROM movimientos_de_cuenta WHERE id = ?",
                              (v["movimiento_id"],)).fetchone() if v["movimiento_id"] else None
            if datos["estado"] == "cuenta" and (not cargo or cargo["anulado"]
                                                or abs(cargo["importe"] - v["total"]) > 0.005):
                mal.append(f"#{venta}: a cuenta por {v['total']} y su cargo es "
                           f"{dict(cargo) if cargo else None}")
            if datos["estado"] != "cuenta" and cargo and not cargo["anulado"]:
                mal.append(f"#{venta}: {datos['estado']} y sigue con un cargo vivo en la cuenta")
        for producto, esperado in self.stock.items():
            real = self.uno("SELECT stock FROM productos WHERE id = ?", producto)
            if real != esperado or (real is not None and real < 0):
                mal.append(f"stock del producto {producto}: hay {real} y tendría que haber {esperado}")
        for taller, esperado in self.saldo.items():
            real = self.ns["estado_de_cuenta"](taller)["saldo"]
            if abs(real - esperado) > 0.005:
                mal.append(f"cuenta {taller}: debe {real} y tendría que deber {round(esperado, 2)}")
        # El cierre de caja de hoy: todo lo de esta prueba es de hoy.
        devuelto_de = {v: self.uno("SELECT COALESCE(SUM(importe), 0) FROM ventas_devoluciones "
                                   "WHERE venta_id = ?", v) for v in self.ventas}
        cobradas = self._las("cobrada", "cuenta")
        por_forma = {}
        for v in cobradas:
            forma = self.ventas[v]["forma"] or "Sin decir"
            por_forma[forma] = por_forma.get(forma, 0.0) + totales[v] - devuelto_de[v]
        cierre = self.ns["cierre_de_caja"]()
        total = round(sum(por_forma.values()), 2)
        de_la_app = {f: t for f, _n, t in cierre["por_forma"]}
        for forma in set(por_forma) | set(de_la_app):
            if abs(por_forma.get(forma, 0.0) - de_la_app.get(forma, 0.0)) > 0.005:
                mal.append(f"cierre, {forma}: dice {de_la_app.get(forma, 0.0)} y entró "
                           f"{round(por_forma.get(forma, 0.0), 2)}")
        esperando = self._las("esperando")
        resumen = self.ns["resumen_de_la_caja"]()
        for que, real, esperado in (
                ("el total", cierre["total"], total),
                ("las ventas", cierre["ventas"], len(cobradas)),
                ("por quién atendió", round(sum(t for _u, _n, t in cierre["por_usuario"]), 2), total),
                ("lo que espera", cierre["a_cobrar"], len(esperando)),
                ("el total que espera", cierre["total_a_cobrar"],
                 round(sum(totales[v] for v in esperando), 2)),
                ("las anuladas", cierre["anuladas"], len(self._las("anulada"))),
                ("cajón + otros medios + a cuenta", round(resumen["efectivo"] + resumen["otros_medios"]
                                                          + resumen["a_cuenta"], 2), total),
                ("el efectivo esperado", self.ns["efectivo_esperado"](),
                 round(por_forma.get("Efectivo", 0.0), 2))):
            if abs(real - esperado) > 0.005:
                mal.append(f"cierre, {que}: dice {real} y tendría que decir {esperado}")
        return mal


OPERACIONES = (("vender", 30), ("cobrar", 22), ("a_cuenta", 10), ("devolver", 12), ("anular", 4),
               ("deshacer", 3), ("corregir_como_pago", 6), ("volver", 8), ("pagar", 5),
               ("anular_el_cargo", 3))


def probar(L, semillas=SEMILLAS, pasos=PASOS):
    ns = L.todo_lo_de_la_logica()
    c, conn, st = ns["c"], ns["conn"], ns["st"]
    st.session_state["admin_nombre"], st.session_state["nivel_usuario"] = "ana", "admin"
    fallas = []
    try:
        for semilla in semillas:
            c.execute("INSERT INTO marcas (nombre, tipo) VALUES (?, 'PROVEEDOR')",
                      (f"AZAR {semilla}",))
            marca = c.lastrowid
            conn.commit()
            caja = Caja(ns, random.Random(semilla), marca)
            # Las de las otras semillas siguen en el cierre de hoy: fuera, para contar solo esta.
            c.execute("UPDATE ventas SET anulada = 1 WHERE anulada = 0")
            c.execute("DELETE FROM ventas_devoluciones")
            c.execute("DELETE FROM ventas")
            conn.commit()
            nombres = [n for n, _peso in OPERACIONES]
            pesos = [peso for _n, peso in OPERACIONES]
            for paso in range(1, pasos + 1):
                operacion = caja.azar.choices(nombres, pesos)[0]
                try:
                    que = getattr(caja, operacion)()
                    mal = caja.problemas() if que else []
                except AssertionError as e:
                    que, mal = operacion, [str(e)]
                if que:
                    caja.hecho.append(que)
                if mal:
                    fallas.append(f"semilla {semilla}, paso {paso} ({que}): " + " · ".join(mal[:3])
                                  + " — venía de: " + " → ".join(caja.hecho[-6:]))
                    break
            else:
                print(f"   semilla {semilla}: {len(caja.hecho)} operaciones, "
                      f"{len(caja.ventas)} ventas, todo cierra")
    finally:
        for k in ("admin_nombre", "nivel_usuario"):
            st.session_state.pop(k, None)
    return fallas


def main():
    semillas, pasos = SEMILLAS, PASOS
    if "--semillas" in sys.argv:
        semillas = tuple(int(x) for x in sys.argv[sys.argv.index("--semillas") + 1].split(","))
    if "--pasos" in sys.argv:
        pasos = int(sys.argv[sys.argv.index("--pasos") + 1])
    carpeta = tempfile.mkdtemp(prefix="pruebas_al_azar_")
    try:
        fallas = probar(_cargar_la_logica(carpeta), semillas, pasos)
        for f in fallas:
            print("   ✗", f)
        print("✅ la caja al azar: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

"""Pruebas del registro de cambios, los permisos adentro de las funciones y las reglas de la base.

Uso:
    python3 pruebas_de_los_cambios.py

De la revisión con ChatGPT (puntos 43 a 58): quién cambió qué y qué había antes; que la función
que borra vuelva a mirar quién está adentro; que un vínculo no pueda guardarse al revés; que el
stock no quede negativo en silencio; qué trae un backup antes de restaurarlo; y el mensaje de
WhatsApp armado aparte de la pantalla. Ver «PERMISOS ADENTRO DE LAS FUNCIONES Y REGISTRO DE
CAMBIOS» en logica/base.py.

Corre en una carpeta temporal: nunca toca la base de trabajo.
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


def probar(L):
    ns = L.todo_lo_de_la_logica()
    c, conn = ns["c"], ns["conn"]
    g = ns["inflacion_desde"].__globals__
    fallas = []

    def esperar(nombre, real, esperado):
        if real != esperado:
            fallas.append(f"{nombre}: dio {real!r}, se esperaba {esperado!r}")

    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('PRUEBA', 'PROVEEDOR')")
    marca = c.lastrowid
    ids = []
    for i in range(4):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio, "
                  "stock) VALUES (?, ?, ?, ?, 1000, ?)", (f"P{i}", f"P{i}", f"PIEZA {i}", marca,
                                                          1 if i == 0 else None))
        ids.append(c.lastrowid)
    conn.commit()
    a, b, x, y = ids

    # 1. Los vínculos se guardan ordenados, los da vuelta la base misma.
    c.execute("INSERT INTO equivalencias (producto_a_id, producto_b_id, lote) VALUES (?, ?, 'L')",
              (b, a))
    c.execute("INSERT OR IGNORE INTO equivalencias (producto_a_id, producto_b_id) VALUES (?, ?)",
              (a, b))
    c.execute("INSERT INTO equivalencias (producto_a_id, producto_b_id) VALUES (?, ?)", (x, x))
    c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen) "
              "VALUES (?, ?, 'manual')", (y, x))
    conn.commit()
    esperar("vínculo al revés: se dio vuelta, una sola vez, con su lote",
            [tuple(r) for r in c.execute("SELECT producto_a_id, producto_b_id, lote "
                                         "FROM equivalencias")], [(a, b, "L")])
    esperar("pendiente al revés: se dio vuelta",
            [tuple(r) for r in c.execute("SELECT producto_a_id, producto_b_id "
                                         "FROM equivalencias_pendientes")], [(x, y)])

    # 2. Precio y stock: se guardan, pero NO se anota quién los cambió (no se quiere). Y lo
    # que había quedado anotado de antes se borra al arrancar.
    ns["actualizar_precio_stock"](a, 1500, 1, stock_mostrado=1)
    esperar("precio guardado", c.execute("SELECT precio FROM productos WHERE id = ?",
                                         (a,)).fetchone()[0], 1500.0)
    esperar("precio: no se anota quién", ns["cambios_registrados"](entidad="producto",
                                                                   entidad_id=a), [])
    c.execute("INSERT INTO registro_de_cambios (usuario, accion, entidad, entidad_id) "
              "VALUES ('ana', 'cambió precio/stock', 'producto', ?)", (str(a),))
    conn.commit()
    ns["crear_esquema"](c)
    conn.commit()
    esperar("lo anotado de antes se borra", ns["cambios_registrados"]("precio"), [])

    # 3. La cuenta de un taller: el descuento que se cambió.
    ns["crear_mecanico"]("Taller Ruiz", "clave-ruiz-1")
    taller = c.execute("SELECT id FROM mecanicos").fetchone()[0]
    ns["configurar_cuenta_de_taller"](taller, 0, 30, True, 0)
    ns["configurar_cuenta_de_taller"](taller, 0, 30, True, 12)
    cuenta = ns["cambios_registrados"](entidad="taller", entidad_id=taller)
    esperar("cuenta: el descuento anotado", json.loads(cuenta[0]["Después"]), {"descuento": 12.0})

    # 4. Vínculos cortados.
    ns["eliminar_equivalencia"](a, b, recordar_rechazo=False)
    esperar("vínculo cortado: anotado", ns["cambios_registrados"](entidad="equivalencia")[0]["Sobre"],
            f"equivalencia {a}-{b}")

    # 5. La segunda barrera: la función vuelve a mirar quién está adentro.
    ns["crear_usuario"]("eva", "clave-eva-1", "operador")
    eva = c.execute("SELECT id FROM usuarios WHERE nombre = 'eva'").fetchone()[0]
    originales = (g["_nivel_de_quien_esta_adentro"], g["hay_claves_configuradas"])
    g["hay_claves_configuradas"] = lambda: True
    try:
        for nivel, puede_borrar, puede_precio in (("", False, False), ("operador", False, True),
                                                  ("admin", True, True)):
            g["_nivel_de_quien_esta_adentro"] = lambda n=nivel: n
            try:
                ns["activar_desactivar_usuario"](eva, True)
                borro = True
            except PermissionError:
                borro = False
            try:
                ns["actualizar_precio_stock"](b, 1000, None)
                precio = True
            except PermissionError:
                precio = False
            esperar(f"nivel «{nivel or 'invitado'}»: tocar empleados / precios",
                    (borro, precio), (puede_borrar, puede_precio))
        # LAS QUE FALTABAN (lo señaló una revisión con ChatGPT: «verificar los permisos también
        # en la lógica»): cada una pide adentro lo mismo que su pantalla. Con ids que no existen:
        # lo que se mira es si deja entrar, no lo que hace.
        _de_admin = (("eliminar un producto", ns["borrar_producto_con_papelera"], (999999,)),
                     ("deshacer una importación", ns["deshacer_importacion"], ("NO-EXISTE",)),
                     ("fusionar marcas", ns["fusionar_marcas"], (999998, 999999)),
                     ("aplicar los precios frenados", ns["aplicar_precios_frenados"], ([],)),
                     ("ajustar los precios de una marca", ns["aumentar_precios_por_marca"], (999999, 5)),
                     ("corregir un código con la marca pegada",
                      ns["corregir_codigo_con_la_marca_pegada"], (999999, "123")))
        _de_empleado = (("aprobar", ns["aprobar_pendientes"], ("NO-EXISTE", [])),
                        ("registrar un pago", ns["registrar_pago_de_cuenta"], (999999, 0, "Efectivo")),
                        ("un remito", ns["aplicar_carga_remito"], ([],)),
                        ("cortar un vínculo", ns["eliminar_equivalencia"], (999998, 999999, False)),
                        ("cortar los vínculos", ns["cortar_todos_los_vinculos"], (999999, False)),
                        ("restaurar de la papelera", ns["restaurar_de_papelera"], (999999,)),
                        ("la ficha de un vehículo", ns["get_or_create_vehiculo"], ("AB123CD",)),
                        ("el número de motor", ns["guardar_numero_de_motor"], ("AB123CD", "M1")),
                        ("el link de una marca", ns["guardar_plantilla_de_ficha"], (999999, None)))
        for nivel, entran in (("", ()), ("operador", ("empleado",)),
                              ("admin", ("empleado", "admin"))):
            g["_nivel_de_quien_esta_adentro"] = lambda n=nivel: n
            for de, lista in (("admin", _de_admin), ("empleado", _de_empleado)):
                for nombre, funcion, args in lista:
                    try:
                        funcion(*args)
                        entro = True
                    except PermissionError:
                        entro = False
                    esperar(f"nivel «{nivel or 'invitado'}»: {nombre}", entro, de in entran)
        # Y lo que guardan hace lo que dice (antes lo escribían las pantallas a mano).
        g["_nivel_de_quien_esta_adentro"] = lambda: "operador"
        esperar("el número de motor, con la patente en minúsculas",
                (ns["guardar_numero_de_motor"]("ab123cd", " K9K-123 "),
                 c.execute("SELECT numero_motor FROM vehiculos WHERE patente = 'AB123CD'").fetchone()[0],
                 ns["guardar_numero_de_motor"]("ZZ999ZZ", "X")), (True, "K9K-123", False))
        _marca_link = c.execute("SELECT id FROM marcas LIMIT 1").fetchone()[0]
        ns["guardar_plantilla_de_ficha"](_marca_link, "https://x.example/{codigo}")
        esperar("el link de la marca", c.execute("SELECT url_ficha_template FROM marcas WHERE id = ?",
                                                 (_marca_link,)).fetchone()[0], "https://x.example/{codigo}")
        ns["guardar_plantilla_de_ficha"](_marca_link, "")
        esperar("y vacío lo borra", c.execute("SELECT url_ficha_template FROM marcas WHERE id = ?",
                                              (_marca_link,)).fetchone()[0], None)
        # El freno de precios de la importación (estaba adentro del ciclo, en la pantalla).
        _m_fr = ns["get_or_create_marca"]("PRUEBA FRENO")
        poner = ns["poner_precio_y_stock_de_la_lista"]
        with ns["db_lock"], ns["transaccion"]():
            _p_fr = ns["get_or_create_producto"]("FR-1", "FR1", "Filtro de prueba", _m_fr)
            _r = [poner(_p_fr, 100.0, None, 200),       # sin precio antes: entra
                  poner(_p_fr, 120.0, 5, 200),          # +20 %: entra, con el stock
                  poner(_p_fr, 12000.0, 7, 200),        # cien veces: se frena; el stock no
                  poner(_p_fr, None, None, 200),        # la fila no trae nada
                  poner(_p_fr, 120.0, None, 200)]       # el mismo precio: no va al historial
        _precio_stock = lambda: tuple(c.execute("SELECT precio, stock FROM productos WHERE id = ?",
                                                (_p_fr,)).fetchone())
        _historial = lambda: [r[0] for r in c.execute(
            "SELECT precio FROM historial_precios WHERE producto_id = ? ORDER BY id", (_p_fr,))]
        esperar("el freno de precios: qué entra y qué se frena",
                [(f[0] if f else None, cambio) for f, cambio in _r],
                [(None, True), (None, True), (120.0, False), (None, False), (None, False)])
        esperar("y dice por qué", "cien veces" in (_r[2][0] or ("", ""))[1], True)
        esperar("el precio frenado no se pisa, el stock sí", _precio_stock(), (120.0, 7))
        esperar("el historial, sin repetidos", _historial(), [100.0, 120.0])
        # Un precio que quedó en 0 se compara con el último de verdad, no con el 0.
        c.execute("UPDATE productos SET precio = 0 WHERE id = ?", (_p_fr,))
        with ns["db_lock"], ns["transaccion"]():
            _r0 = poner(_p_fr, 12000.0, None, 200)
        esperar("con el precio en 0, se compara con el del historial", _r0[0] and _r0[0][0], 120.0)
        g["_nivel_de_quien_esta_adentro"] = lambda: "admin"
        esperar("aplicar igual lo frenado: solo lo que trae precio",
                (ns["aplicar_precios_frenados"]([{"_id": _p_fr, "Precio de la lista": 12000.0},
                                                {"_id": _p_fr, "Precio de la lista": None}]),
                 _precio_stock()[0], _historial()[-1]), (1, 12000.0, 12000.0))
        # ¿La de internet? Ahí el repositorio está en /mount/src (ver corre_en_streamlit_cloud()).
        _carpeta = g["_CARPETA"]
        esperar("acá no es la app de internet", ns["corre_en_streamlit_cloud"](), False)
        g["_CARPETA"] = "/mount/src/chavaje-equivalencias-/logica"
        esperar("en /mount/src sí", ns["corre_en_streamlit_cloud"](), True)
        g["_CARPETA"] = _carpeta
        # EL AJUSTE DE PRECIOS POR PORCENTAJE (Marcas): con su renglón en el historial, sin tocar
        # los que no tienen precio, y con tope (ver aumentar_precios_por_marca()). No tenía
        # ninguna prueba.
        g["_nivel_de_quien_esta_adentro"] = lambda: "admin"
        _m_aj = ns["get_or_create_marca"]("PRUEBA AJUSTE")
        with ns["db_lock"], ns["transaccion"]():
            _aj = [ns["get_or_create_producto"](f"AJ-{i}", f"AJ{i}", "Pieza de prueba", _m_aj)
                   for i in range(3)]
        for _pid, _precio in zip(_aj, (1000.0, 0.0, None)):
            c.execute("UPDATE productos SET precio = ? WHERE id = ?", (_precio, _pid))
        ns["conn"].commit()

        def _precios_aj():
            return [c.execute("SELECT precio FROM productos WHERE id = ?", (p,)).fetchone()[0]
                    for p in _aj]

        def _historial_aj(pid):
            return [r[0] for r in c.execute("SELECT precio FROM historial_precios WHERE "
                                            "producto_id = ? ORDER BY id", (pid,))]
        esperar("subir 10 %: solo el que tiene precio, y queda en su historial",
                (ns["productos_con_precio_de_la_marca"](_m_aj),
                 ns["aumentar_precios_por_marca"](_m_aj, 10), _precios_aj(), _historial_aj(_aj[0]),
                 _historial_aj(_aj[1])), (1, 1, [1100.0, 0.0, None], [1100.0], []))
        for _malo in (-100, -150, 5000):
            try:
                ns["aumentar_precios_por_marca"](_m_aj, _malo)
                _paso = True
            except ValueError:
                _paso = False
            esperar(f"un ajuste de {_malo} % no se aplica", _paso, False)
        esperar("y los precios quedan como estaban", _precios_aj(), [1100.0, 0.0, None])
        esperar("bajar 99 % se puede", (ns["aumentar_precios_por_marca"](_m_aj, -99), _precios_aj()[0]),
                (1, 11.0))

        # EL MARGEN, sobre el precio de venta (ver margen_de()). Tampoco tenía prueba.
        esperar("el margen, sobre el precio de venta", ns["margen_de"](1000, 650), (35.0, 350))
        esperar("sin costo o sin precio no hay margen",
                [ns["margen_de"](1000, None), ns["margen_de"](0, 500), ns["margen_de"](1000, 0)],
                [(None, None)] * 3)
        esperar("y en la fila, sin borrar el costo",
                [(f.get("Margen"), "_costo" in f) for f in ns["agregar_margen"](
                    [{"Precio": 1000, "_costo": 650}, {"Precio": 1000}])],
                [("35% ($350)", True), ("", False)])

        # CERRAR UNA RESERVA: vendida descuenta del stock UNA vez; cancelada solo libera (ver
        # cerrar_reserva()). Sin prueba hasta ahora.
        c.execute("UPDATE productos SET stock = 10 WHERE id = ?", (_aj[0],))
        ns["conn"].commit()

        def _stock_aj():
            return c.execute("SELECT stock FROM productos WHERE id = ?", (_aj[0],)).fetchone()[0]

        def _ultima_reserva():
            return c.execute("SELECT id FROM reservas_stock WHERE producto_id = ? ORDER BY id DESC",
                             (_aj[0],)).fetchone()[0]
        ns["reservar_stock"](_aj[0], 3, "Cliente de prueba")
        _r1 = _ultima_reserva()
        esperar("vendida, descuenta del stock una sola vez",
                (ns["cerrar_reserva"](_r1, True), _stock_aj(), ns["cerrar_reserva"](_r1, True),
                 _stock_aj()), (True, 7, False, 7))
        ns["reservar_stock"](_aj[0], 2, "Cliente de prueba")
        _r2 = _ultima_reserva()
        esperar("cancelada, solo libera",
                (ns["cerrar_reserva"](_r2, False), _stock_aj(),
                 c.execute("SELECT estado FROM reservas_stock WHERE id = ?", (_r2,)).fetchone()[0]),
                (True, 7, "cancelada"))

        # BORRAR UNA MARCA Y RESTAURARLA (ver eliminar_marca_con_papelera()). No tenía prueba, y
        # una marca con un solo producto con foto no se podía borrar: «bytes is not JSON
        # serializable». Y volvía sin la historia de sus productos.
        _m_bo = ns["get_or_create_marca"]("MARCA CON FOTOS")
        _m_otra = ns["get_or_create_marca"]("OTRA MARCA")
        with ns["db_lock"], ns["transaccion"]():
            _mf1 = ns["get_or_create_producto"]("MF-1", "MF1", "Filtro con foto", _m_bo)
            _mf2 = ns["get_or_create_producto"]("MF-2", "MF2", "Filtro sin foto", _m_bo)
            _ot1 = ns["get_or_create_producto"]("OT-1", "OT1", "Filtro de otra marca", _m_otra)
        c.execute("UPDATE productos SET imagen_orb_blob = ?, precio = 100 WHERE id = ?",
                  (b"\x00\x01firma", _mf1))
        c.execute("INSERT INTO historial_precios (producto_id, precio) VALUES (?, 90), (?, 100)",
                  (_mf1, _mf1))
        c.execute("INSERT INTO producto_fotos (producto_id, imagen_data, estado) "
                  "VALUES (?, ?, 'ok')", (_mf1, b"\x89PNGfoto"))
        c.execute("INSERT INTO equivalencias (producto_a_id, producto_b_id) VALUES (?, ?)",
                  (min(_mf1, _ot1), max(_mf1, _ot1)))
        ns["conn"].commit()
        g["_nivel_de_quien_esta_adentro"] = lambda: "admin"
        esperar("una marca con un producto con foto se puede borrar",
                (ns["eliminar_marca_con_papelera"]("MARCA CON FOTOS"),
                 c.execute("SELECT COUNT(*) FROM marcas WHERE nombre = 'MARCA CON FOTOS'"
                           ).fetchone()[0]), (True, 0))
        # Mientras está en la papelera, se vuelve a importar la lista: la marca y un producto
        # vuelven con otro id.
        _m_bo2 = ns["get_or_create_marca"]("MARCA CON FOTOS")
        with ns["db_lock"], ns["transaccion"]():
            _mf1_nuevo = ns["get_or_create_producto"]("MF-1", "MF1", "Filtro con foto", _m_bo2)
        _papel = c.execute("SELECT id FROM papelera WHERE tipo = 'marca' ORDER BY id DESC"
                           ).fetchone()[0]
        _ok_rest, _detalle_rest = ns["restaurar_de_papelera"](_papel)
        esperar(f"y se restaura aunque la hayan vuelto a crear ({_detalle_rest})", _ok_rest, True)
        _mf1_ahora = c.execute("SELECT p.id, p.imagen_orb_blob FROM productos p JOIN marcas m ON "
                               "m.id = p.marca_id WHERE m.nombre = 'MARCA CON FOTOS' AND "
                               "p.codigo_clean = 'MF1'").fetchall()
        esperar("una sola marca y un solo MF1: el que volvió con la importación",
                (c.execute("SELECT COUNT(*) FROM marcas WHERE nombre = 'MARCA CON FOTOS'"
                           ).fetchone()[0], [r[0] for r in _mf1_ahora]), (1, [_mf1_nuevo]))
        esperar("y el otro producto también volvió",
                c.execute("SELECT COUNT(*) FROM productos WHERE codigo_clean = 'MF2'"
                          ).fetchone()[0], 1)
        esperar("con su historia: los precios anteriores, la foto y el vínculo",
                (c.execute("SELECT COUNT(*) FROM historial_precios WHERE producto_id = ?",
                           (_mf1_nuevo,)).fetchone()[0],
                 c.execute("SELECT COUNT(*) FROM producto_fotos WHERE producto_id = ?",
                           (_mf1_nuevo,)).fetchone()[0],
                 c.execute("SELECT COUNT(*) FROM equivalencias WHERE ? IN (producto_a_id, "
                           "producto_b_id) AND ? IN (producto_a_id, producto_b_id)",
                           (_mf1_nuevo, _ot1)).fetchone()[0]), (2, 1, 1))
        g["_nivel_de_quien_esta_adentro"] = lambda: "operador"

        # Se saca lo creado: más abajo se cuentan los productos y las marcas.
        for _m in (_m_bo2, _m_otra):
            for (_pid,) in c.execute("SELECT id FROM productos WHERE marca_id = ?", (_m,)).fetchall():
                for _t in ("historial_precios", "producto_fotos"):
                    c.execute(f"DELETE FROM {_t} WHERE producto_id = ?", (_pid,))
                c.execute("DELETE FROM equivalencias WHERE ? IN (producto_a_id, producto_b_id)",
                          (_pid,))
                c.execute("DELETE FROM productos WHERE id = ?", (_pid,))
            c.execute("DELETE FROM marcas WHERE id = ?", (_m,))
        c.execute("DELETE FROM historial_precios WHERE producto_id = ?", (_p_fr,))
        c.execute("DELETE FROM productos WHERE id = ?", (_p_fr,))
        c.execute("DELETE FROM marcas WHERE id = ?", (_m_fr,))
        for _pid in _aj:
            c.execute("DELETE FROM reservas_stock WHERE producto_id = ?", (_pid,))
            c.execute("DELETE FROM historial_precios WHERE producto_id = ?", (_pid,))
            c.execute("DELETE FROM productos WHERE id = ?", (_pid,))
        c.execute("DELETE FROM marcas WHERE id = ?", (_m_aj,))
        ns["conn"].commit()
        g["_nivel_de_quien_esta_adentro"] = lambda: ""
        try:
            ns["eliminar_usuario"](eva)
        except PermissionError:
            pass
        esperar("sin permiso, no borró", c.execute("SELECT COUNT(*) FROM usuarios WHERE id = ?",
                                                   (eva,)).fetchone()[0], 1)
        g["_nivel_de_quien_esta_adentro"] = lambda: None        # trabajo de fondo / sin sesión
        ns["activar_desactivar_usuario"](eva, True)
    finally:
        g["_nivel_de_quien_esta_adentro"], g["hay_claves_configuradas"] = originales

    # 6. El stock no queda negativo en silencio.
    ns["pedir_al_deposito"](a, 3, None, usuario="mostrador")
    pedido = c.execute("SELECT id FROM pedidos_deposito").fetchone()[0]
    ok, aviso = ns["entregar_pedido"](pedido, usuario="deposito")
    esperar("entrega con faltante: se entrega", ok, True)
    esperar("stock en 0, no negativo", c.execute("SELECT stock FROM productos WHERE id = ?",
                                                 (a,)).fetchone()[0], 0)
    esperar("lo avisa", "conviene contarlo" in aviso, True)
    esperar("y queda anotado", ns["cambios_registrados"]("stock de menos")[0]["Quién"], "deposito")

    # 7. Lo que trae un backup, antes de restaurarlo.
    vistazo = ns["vistazo_de_un_backup"](ns["generar_backup_sin_fotos"]())
    esperar("vistazo de un backup", (vistazo.get("productos"), vistazo.get("marcas")), (4, 1))
    esperar("vistazo de algo que no es un backup", bool(ns["vistazo_de_un_backup"](b"xx")
                                                       .get("error")), True)

    # 8. El mensaje de WhatsApp, armado aparte.
    mensaje = ns["armar_mensaje_de_cotizacion"](
        [{"codigo_buscado": "W712", "resultados": [
            {"Marca": "MANN", "Codigo": "W712", "Descripcion": "FILTRO", "Precio": 12500,
             "Stock": 3}]}], "Hola", "Gracias", True, False, para="Taller Ruiz")
    esperar("mensaje", mensaje, "Hola\n\nPara: *Taller Ruiz*\n\n\n📦 *W712*\n"
                                "  • MANN: W712 - FILTRO ($12.500)\n\nGracias")

    # 9. El registro no crece para siempre.
    g["CAMBIOS_QUE_SE_GUARDAN"] = 10
    for i in range(1000):
        ns["anotar_cambio"]("prueba", "nada", i)
    conn.commit()
    esperar("el registro se recorta", c.execute("SELECT COUNT(*) FROM registro_de_cambios"
                                                ).fetchone()[0] < 1000, True)

    # 9b. Qué es cada columna en una lista SIN TÍTULOS (ver adivinar_columnas_por_datos()). No
    # tenía prueba, y con el precio primero, ordenado de menor a mayor —precios que no se
    # repiten— y códigos numéricos, tomaba el precio como código y el código como precio.
    _descs = ["FILTRO DE ACEITE VW GOL 1.6", "PASTILLA DE FRENO FORD KA", "BOMBA DE AGUA FIAT",
              "CORREA DISTRIBUCION RENAULT", "BUJIA NGK BPR6ES"]
    _adiv = ns["adivinar_columnas_por_datos"]
    _casos = {
        "típica": ([[f"W{700 + i}/{i % 9}", _descs[i % 5], str((1500, 2300, 4100)[i % 3]),
                     str(i % 7)] for i in range(40)], 4, (0, 1, 2)),
        "precio con decimales primero, sin repetir": (
            [[f"{1000 + i * 37.25:.2f}", str(100000 + i * 7), _descs[i % 5]] for i in range(40)],
            3, (1, 2, 0)),
        "precio entero primero, sin repetir": (
            [[str(500 + i * i * 41), str(100000 + i * 7), _descs[i % 5]] for i in range(40)],
            3, (1, 2, 0)),
        "código numérico y precio con coma": (
            [[str(3000 + i), _descs[i % 5], ("1500,50", "2300,50")[i % 2]] for i in range(40)],
            3, (0, 1, 2)),
    }
    for _nombre, (_filas, _ancho, _esperado) in _casos.items():
        _h = _adiv(_filas, _ancho)
        esperar(f"columnas de una lista sin títulos ({_nombre}): código, descripción, precio",
                (_h["prov"], _h["desc"], _h["precio"]), _esperado)

    # 9c. El dígito verificador del VIN (ver digito_verificador_vin() y verificar_vin()). No tenía
    # prueba. El de la norma: 1M8GDM9AXKP042788 lleva X.
    esperar("el dígito verificador de la norma", [ns["digito_verificador_vin"](v) for v in
                                                  ("1M8GDM9AXKP042788", "11111111111111111")],
            ["X", "1"])
    esperar("un carácter mal copiado en un VIN de Estados Unidos se marca",
            [ns["verificar_vin"](v)[0] for v in ("1M8GDM9AXKP042788", "1M8GDM9A1KP042788",
                                                 "9BWZZZ377VT004251")],
            ["ok", "mal", "no_aplica"])
    esperar("la O donde va un cero se corrige", ns["corregir_confusiones_vin"]("1M8GDM9AXKPO42788")[0],
            "1M8GDM9AXKP042788")
    # Y lo que llega a la pantalla: decodificar_vin() lo pisaba más abajo con None o True/False,
    # y el «❌ VIN mal copiado» no salía nunca (lo encontró el control 6e de auditar.py).
    esperar("lo que ve la pantalla del VIN, bien, mal copiado y de afuera",
            [(ns["decodificar_vin"](v)["digito_verificador"],
              bool(ns["decodificar_vin"](v)["mensaje_digito"]))
             for v in ("1M8GDM9AXKP042788", "1M8GDM9A1KP042788", "9BWZZZ377VT004251")],
            [("ok", True), ("mal", True), ("no_aplica", True)])
    esperar("el país por los dos primeros del VIN donde todas las tablas de ISO 3779 coinciden",
            [ns["PAISES_VIN_2"].get(x) for x in ("VA", "VC", "VE", "8K", "8L", "8R")],
            ["Austria", "Austria", "Austria", "Chile", "Ecuador", "Ecuador"])

    # 9d. Los códigos de falla de la sonda lambda (ver _dtc_sistematicos()). P0134 es «sin
    # actividad» y P0135 el calefactor; el generador los tenía corridos y pisaba los buenos.
    def _dtc(codigo):
        return c.execute("SELECT descripcion FROM codigos_dtc WHERE codigo = ? AND fabricante = ''",
                         (codigo,)).fetchone()[0]
    esperar("P0134 y P0135 de cada sonda, como dice la norma",
            [_dtc(x).split(",")[0] for x in ("P0134", "P0135", "P0140", "P0141", "P0166", "P0167")],
            ["Sin actividad detectada en el sensor de oxígeno",
             "Falla eléctrica en el calefactor del sensor de oxígeno"] * 3)
    esperar("P0451 es fuera de rango, no falla eléctrica", _dtc("P0451"),
            "Sensor de presión del sistema EVAP fuera de rango")
    # Y en una base que ya tenía los textos viejos: se corrigen solos, salvo lo editado a mano.
    _viejo = "Circuito del calefactor del sensor de oxígeno, banco 1 sensor 1"
    c.execute("UPDATE codigos_dtc SET descripcion = ?, editado = 0 WHERE codigo = 'P0134'", (_viejo,))
    c.execute("UPDATE codigos_dtc SET descripcion = 'lo que puso el taller', editado = 1 "
              "WHERE codigo = 'P0140'")
    c.execute("UPDATE configuracion SET valor = '3' WHERE clave = 'semilla_dtc_version'")
    ns["_datos_precargados_y_migraciones"](c)
    conn.commit()
    esperar("al actualizar la app se corrige el texto viejo y se respeta lo editado a mano",
            (_dtc("P0134").split(",")[0], _dtc("P0140")),
            ("Sin actividad detectada en el sensor de oxígeno", "lo que puso el taller"))
    # Una falla del turbo no ofrece solenoides de caja automática (la causa decía «válvula
    # solenoide»); una de la caja, sí.
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
              "VALUES ('SOLCAJA1', 'SOLCAJA1', 'SOLENOIDE CAJA AUTOMATICA', ?)", (marca,))
    conn.commit()
    esperar("qué piezas ofrece un código del turbo y uno de la caja",
            [[r["pieza"] for r in ns["repuestos_para_el_dtc"](x)] for x in ("P0045", "P0750")],
            [[], ["SOLENOIDE DE CAJA"]])
    c.execute("DELETE FROM productos WHERE codigo_clean = 'SOLCAJA1'")
    conn.commit()

    # 9e. Los años imposibles de las aplicaciones ya deducidas (ver
    # _corregir_anios_imposibles_de_aplicaciones()): se vuelven a leer de la descripción.
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
              "VALUES ('ANIO1', 'ANIO1', 'JUNTA PEUGEOT 2061.0 16V 2000/.', ?)", (marca,))
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
              "VALUES ('ANIO2', 'ANIO2', 'BOBINA PEUGEOT 2051.0/1.1', ?)", (marca,))
    c.executemany("INSERT INTO aplicaciones (marca_auto, modelo_auto, motor, anio_desde, anio_hasta, "
                  "codigo, codigo_clean, marca_repuesto, origen) VALUES "
                  "('PEUGEOT', ?, '', ?, ?, ?, ?, 'PRUEBA', ?)",
                  [("206", 2061, 2061, "ANIO1", "ANIO1", "deducida"),
                   ("205", 2051, 2051, "ANIO2", "ANIO2", "deducida"),
                   ("106", 2051, 2051, "ANIO2", "ANIO2", "catálogo")])
    c.execute("DELETE FROM configuracion WHERE clave = 'version_anios_de_aplicaciones'")
    conn.commit()
    ns["_poner_al_dia_los_anios_de_aplicaciones"]()
    esperar("los años imposibles se releen de la descripción; lo del catálogo no se toca",
            [tuple(f) for f in c.execute("SELECT codigo_clean, origen, anio_desde, anio_hasta "
                                         "FROM aplicaciones WHERE codigo_clean IN ('ANIO1', 'ANIO2') "
                                         "ORDER BY 1, 2").fetchall()],
            [("ANIO1", "deducida", 2000, 2000), ("ANIO2", "catálogo", 2051, 2051),
             ("ANIO2", "deducida", None, None)])
    esperar("y queda anotado: no se vuelve a hacer",
            c.execute("SELECT valor FROM configuracion "
                      "WHERE clave = 'version_anios_de_aplicaciones'").fetchone()[0],
            ns["VERSION_ANIOS_DE_APLICACIONES"])
    c.execute("DELETE FROM aplicaciones WHERE codigo_clean IN ('ANIO1', 'ANIO2')")
    c.execute("DELETE FROM productos WHERE codigo_clean IN ('ANIO1', 'ANIO2')")
    conn.commit()

    # 10. «Borrar los productos vacíos» (ver depurar_huerfanos()). Borraba todos los que no
    # tenían una equivalencia aprobada: en la copia de la base, el 72 % del catálogo, casi
    # todos con precio. Ahora solo los que no tienen nada. Va al final: borra los vacíos que
    # dejaron las pruebas de arriba.
    _mv = ns["get_or_create_marca"]("PRUEBA VACIOS")
    with ns["db_lock"], ns["transaccion"]():
        _v = {n: ns["get_or_create_producto"](f"V-{n}", f"V{n}", "Pieza de prueba", _mv)
              for n in ("vacio", "precio", "stock", "pendiente", "rechazado", "historia",
                        "vinculado", "socio")}

    def _par(x, y):
        return (min(_v[x], _v[y]), max(_v[x], _v[y]))
    # Cada uno con UNA sola cosa; los vínculos, con un socio que tiene precio (no está vacío).
    c.execute("UPDATE productos SET precio = 100 WHERE id IN (?, ?)", (_v["precio"], _v["socio"]))
    c.execute("UPDATE productos SET stock = 2 WHERE id = ?", (_v["stock"],))
    c.execute("INSERT INTO equivalencias_pendientes (producto_a_id, producto_b_id, origen, lote) "
              "VALUES (?, ?, 'x', 'VACIOS')", _par("pendiente", "socio"))
    c.execute("INSERT INTO equivalencias_revisadas (producto_a_id, producto_b_id, decision) "
              "VALUES (?, ?, 'rechazada')", _par("rechazado", "socio"))
    c.execute("INSERT INTO historial_precios (producto_id, precio) VALUES (?, 50)",
              (_v["historia"],))
    c.execute("INSERT INTO equivalencias (producto_a_id, producto_b_id) VALUES (?, ?)",
              _par("vinculado", "socio"))
    conn.commit()
    _vacios_antes = ns["contar_productos_vacios"]()
    g["_nivel_de_quien_esta_adentro"] = lambda: "operador"
    try:
        ns["depurar_huerfanos"]()
        _paso = True
    except PermissionError:
        _paso = False
    esperar("un empleado no borra productos vacíos", _paso, False)
    g["_nivel_de_quien_esta_adentro"] = lambda: "admin"
    _borrados = ns["depurar_huerfanos"]()
    _quedan = {n for n, pid in _v.items()
               if c.execute("SELECT 1 FROM productos WHERE id = ?", (pid,)).fetchone()}
    esperar("borra solo lo vacío: lo que tiene precio, stock, algo por revisar, un rechazo, "
            "historia o un vínculo se queda",
            (_borrados == _vacios_antes, _quedan),
            (True, {"precio", "stock", "pendiente", "rechazado", "historia", "vinculado",
                    "socio"}))
    esperar("y no queda ninguno vacío", ns["contar_productos_vacios"](), 0)
    g["_nivel_de_quien_esta_adentro"] = lambda: None
    return fallas


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_cambios_")
    try:
        fallas = probar(_cargar_la_logica(carpeta))
        for f in fallas:
            print("   ✗", f)
        print("✅ cambios: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

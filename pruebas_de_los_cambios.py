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
                      ns["corregir_codigo_con_la_marca_pegada"], (999999, "123")),
                     # Adónde transfieren los clientes: lo podía cambiar cualquier empleado.
                     ("cambiar los datos de cobro", ns["guardar_alias_transferencia"],
                      ("PRUEBA-PERMISO", "alias.prueba", "", "")),
                     ("eliminar los datos de cobro", ns["eliminar_alias_transferencia"], (999999,)),
                     ("sacar el QR de cobro", ns["eliminar_qr_real"], (999999,)),
                     ("cambiar el coeficiente de una lista", ns["guardar_coeficiente_de_lista"],
                      (999999, 1.0, False)),
                     ("activar o desactivar un taller", ns["activar_desactivar_mecanico"],
                      (999999, True)))
        _de_empleado = (("aprobar", ns["aprobar_pendientes"], ("NO-EXISTE", [])),
                        ("registrar un pago", ns["registrar_pago_de_cuenta"], (999999, 0, "Efectivo")),
                        ("un remito", ns["aplicar_carga_remito"], ([],)),
                        ("cortar un vínculo", ns["eliminar_equivalencia"], (999998, 999999, False)),
                        ("cortar los vínculos", ns["cortar_todos_los_vinculos"], (999999, False)),
                        ("restaurar de la papelera", ns["restaurar_de_papelera"], (999999,)),
                        ("la ficha de un vehículo", ns["get_or_create_vehiculo"], ("AB123CD",)),
                        ("el número de motor", ns["guardar_numero_de_motor"], ("AB123CD", "M1")),
                        ("el link de una marca", ns["guardar_plantilla_de_ficha"], (999999, None)),
                        ("confirmar una equivalencia sugerida", ns["confirmar_candidata"],
                         ("NOEXISTE", 999999, "NOEXISTE")))
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
        # EL INVITADO MIRA, NO TOCA (ver logica/base.py): lo que se podía anotar o cambiar
        # desde las secciones abiertas sin contraseña. Con datos inventados: lo que importa es si
        # deja pasar; si pasa y después falla por el dato (un id que no existe), igual entró.
        _al_mirar = (
            ("anotar una venta", ns["registrar_venta"], (999999, "PERMISO")),
            ("anotar para reponer", ns["solicitar_reposicion"], (999999,)),
            ("marcar un favorito", ns["alternar_favorito"], (999999, True)),
            ("anotar una consulta", ns["anotar_consulta_cliente"], ("", "")),
            ("apartar stock", ns["reservar_stock"], (999999, 1)),
            ("pedir al depósito", ns["pedir_al_deposito"], (999999, 1)),
            ("cargar un código de falla", ns["agregar_dtc"], ("PERMISO1", "prueba", "", "")),
            ("cargar códigos de falla", ns["importar_dtc_masivo"], ("",)),
            ("cargar un fabricante del VIN", ns["agregar_fabricante_vin"], ("ZZ9", "PRUEBA", "")),
            ("enseñar un modelo del VIN", ns["enseniar_modelo_vin"], ("ZZ9", "ZZZZZ", "PRUEBA")),
            ("enseñar un motor del VIN", ns["enseniar_motor_vin"], ("ZZ9", "Z", "PRUEBA")),
            ("borrar un modelo del VIN", ns["olvidar_modelo_vin"], ("ZZ9", "ZZZZZ")),
            ("borrar un motor del VIN", ns["olvidar_motor_vin"], ("ZZ9", "Z")),
            ("subir un esquema", ns["guardar_esquema"],
             ("PRUEBA-PERMISO", "X", "Y", "Z", "", b"", "x.png")),
            ("precargar un vehículo de esquemas", ns["agregar_vehiculo_catalogo"],
             ("PRUEBA-PERMISO", "Y")),
            ("eliminar un esquema", ns["eliminar_esquema"], (999999,)),
            ("marcar una pieza en un esquema", ns["agregar_punto_esquema"], (999999, "1", "x", "")),
            ("sacar una pieza de un esquema", ns["eliminar_punto_esquema"], (999999,)),
            ("la tarea en segundo plano", ns["prender_tarea_de_fondo"],
             ("fotos", "fotos_automaticas", False)),
            ("cortar vínculos", ns["borrar_equivalencias_dudosas"], ([],)),
            ("anotar una devolución", ns["registrar_devolucion"], (999999, "X", "PERMISO")),
            ("anotar que anduvo", ns["registrar_que_anduvo"], (999999, "X")),
            ("autorizar un retiro a cuenta", ns["autorizar_retiro"], (999999, "000000")),
            ("sacar un vehículo de los esquemas", ns["eliminar_vehiculo_catalogo"],
             ("PRUEBA-PERMISO", "Y")),
        )
        for nivel, entra in (("", False), ("mecanico", False), ("operador", True), ("admin", True)):
            g["_nivel_de_quien_esta_adentro"] = lambda n=nivel: n
            for nombre, funcion, args in _al_mirar:
                try:
                    funcion(*args)
                    entro = True
                except PermissionError:
                    entro = False
                except Exception:
                    entro = True
                esperar(f"nivel «{nivel or 'invitado'}»: {nombre}", entro, entra)
        c.execute("DELETE FROM codigos_dtc WHERE codigo = 'PERMISO1'")
        c.execute("DELETE FROM fabricantes_vin WHERE wmi = 'ZZ9'")
        c.execute("DELETE FROM esquemas WHERE titulo = 'PRUEBA-PERMISO'")
        c.execute("DELETE FROM esquemas_catalogo WHERE marca = 'PRUEBA-PERMISO'")
        conn.commit()
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
    # Lo que lee el cliente (ver para_el_cliente() y precio_para_el_cliente()): la marca con
    # los precios en otra escala no sale con un número, el «?» suelto es un separador y el «:»
    # colgado de un código se va. En el mensaje y en el PDF.
    _fila_fuera = {"Marca": "TARANTO", "Codigo": "CT6KMR :", "Descripcion": "BUJIA FIAT ? PEUGEOT",
                   "Precio": 370}
    _lista_fuera = [{"codigo_buscado": "X", "resultados": [_fila_fuera]}]
    esperar("cotización con una lista fuera de escala",
            ns["armar_mensaje_de_cotizacion"](_lista_fuera, marcas_sin_precio={"TARANTO"}),
            "\n📦 *X*\n  • TARANTO: CT6KMR - BUJIA FIAT · PEUGEOT (precio a confirmar)")
    esperar("y sin estar fuera de escala, con su precio",
            ns["armar_mensaje_de_cotizacion"](_lista_fuera, marcas_sin_precio=set()).endswith(
                "($370)"), True)
    esperar("un «?» pegado a una palabra no se toca (es otra cosa)",
            ns["para_el_cliente"]("JUNTA N? 5 ? TAPA"), "JUNTA N? 5 · TAPA")
    _pdf = ns["generar_pdf_cotizacion"](_lista_fuera, marcas_sin_precio={"TARANTO"})
    esperar("el PDF se arma igual", _pdf[:4], b"%PDF")

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

    # 9c bis. El conversor de unidades (ver CONVERSIONES_DE_TALLER): contra valores conocidos,
    # que salen de las definiciones (1 kgf = 9,80665 N; 1 milla = 1,609344 km; 1 CV = 75 kgf·m/s).
    _conv = ns["convertir_unidad"]
    esperar("el conversor, contra valores conocidos",
            [round(_conv(v, cat, d)[0], 4) for v, cat, d in (
                (100, "Torque", "lb-ft → Nm"), (10, "Torque", "kgf·m → Nm"),
                (135.5818, "Torque", "Nm → lb-ft"), (32, "Presión", "PSI → Bar"),
                (2, "Presión", "kg/cm² → PSI"), (100, "Temperatura", "°C → °F"),
                (-40, "Temperatura", "°F → °C"), (1, "Longitud", "Millas → km"),
                (1, "Volumen", "Galones (EE.UU.) → Litros"), (100, "Potencia", "CV → kW"),
                (100, "Potencia", "HP → kW"), (1, "Longitud", "Pulgadas → mm"))],
            [135.5818, 98.0665, 100.0, 2.2063, 28.4467, 212.0, -40.0, 1.6093, 3.7854, 73.5499,
             74.57, 25.4])
    esperar("cada dirección que se ofrece se puede convertir, ida y vuelta",
            [d for cat in ns["CONVERSIONES_DE_TALLER"] for d in ns["direcciones_de_conversion"](cat)
             if round(_conv(_conv(7.5, cat, d)[0], cat,
                            " → ".join(reversed(d.split(" → "))))[0], 9) != 7.5], [])

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
    # _corregir_anios_imposibles_de_aplicaciones()): se vuelven a leer de la descripción. Y el
    # «modelo» MPFI, que es la inyección, se borra (ver _borrar_modelos_que_no_son_autos()).
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
    c.execute("INSERT INTO aplicaciones (marca_auto, modelo_auto, motor, codigo, codigo_clean, "
              "marca_repuesto, origen) VALUES ('CHEVROLET', 'MPFI', '', 'ANIO1', 'ANIO1', 'PRUEBA', "
              "'deducida')")
    c.execute("DELETE FROM configuracion WHERE clave = 'version_limpieza_de_aplicaciones'")
    conn.commit()
    ns["_poner_al_dia_las_aplicaciones_deducidas"]()
    esperar("los años imposibles se releen de la descripción; lo del catálogo no se toca",
            [tuple(f) for f in c.execute("SELECT codigo_clean, origen, anio_desde, anio_hasta "
                                         "FROM aplicaciones WHERE codigo_clean IN ('ANIO1', 'ANIO2') "
                                         "ORDER BY 1, 2").fetchall()],
            [("ANIO1", "deducida", 2000, 2000), ("ANIO2", "catálogo", 2051, 2051),
             ("ANIO2", "deducida", None, None)])
    esperar("y queda anotado: no se vuelve a hacer",
            c.execute("SELECT valor FROM configuracion "
                      "WHERE clave = 'version_limpieza_de_aplicaciones'").fetchone()[0],
            ns["VERSION_LIMPIEZA_DE_APLICACIONES"])
    # Si al cargar la lógica no se pudo (la base ocupada), la tarea del día la reintenta.
    c.execute("DELETE FROM configuracion WHERE clave IN ('version_limpieza_de_aplicaciones', "
              "'ultimas_tareas_dia')")
    conn.commit()
    ns["tareas_automaticas_del_dia"](presupuesto_segundos=0)
    esperar("la tarea del día reintenta la limpieza que no se pudo hacer al cargar",
            tuple(c.execute("SELECT valor FROM configuracion "
                            "WHERE clave = 'version_limpieza_de_aplicaciones'").fetchone() or ()),
            (ns["VERSION_LIMPIEZA_DE_APLICACIONES"],))
    c.execute("DELETE FROM aplicaciones WHERE codigo_clean IN ('ANIO1', 'ANIO2')")
    c.execute("DELETE FROM productos WHERE codigo_clean IN ('ANIO1', 'ANIO2')")
    conn.commit()

    # 9f. La escala de precios, contra cada proveedor (ver escala_de_precios_por_marca()): una
    # lista que cuesta 15 veces menos que TODOS sus equivalentes está corrida pareja.
    _ids = {}
    for _nom in ("ESCALA-A", "ESCALA-B", "ESCALA-C"):
        c.execute("INSERT INTO marcas (nombre, tipo) VALUES (?, 'PROVEEDOR')", (_nom,))
        _ids[_nom] = c.lastrowid
    _pares = []
    for i in range(6):
        _de_a = []
        for _nom, _precio in (("ESCALA-A", 100.0), ("ESCALA-B", 1500.0), ("ESCALA-C", 1600.0)):
            c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, "
                      "precio) VALUES (?, ?, 'PIEZA DE ESCALA', ?, ?)",
                      (f"ESC{_nom[-1]}{i}", f"ESC{_nom[-1]}{i}", _ids[_nom], _precio))
            _de_a.append(c.lastrowid)
        _pares += [(min(_de_a[0], x), max(_de_a[0], x)) for x in _de_a[1:]]
    c.executemany("INSERT INTO equivalencias (producto_a_id, producto_b_id, confianza) "
                  "VALUES (?, ?, 80)", _pares)
    conn.commit()
    ns["olvidar_la_escala_de_precios"]()
    _esc = ns["escala_de_precios_por_marca"]()["ESCALA-A"]
    esperar("la escala contra cada proveedor",
            {k: round(v, 4) for k, v in _esc["por_proveedor"].items()},
            {"ESCALA-B": round(100 / 1500, 4), "ESCALA-C": round(100 / 1600, 4)})
    c.execute("DELETE FROM equivalencias WHERE producto_a_id IN (SELECT id FROM productos "
              "WHERE codigo_clean LIKE 'ESC%')")
    c.execute("DELETE FROM productos WHERE codigo_clean LIKE 'ESC%' AND descripcion = "
              "'PIEZA DE ESCALA'")
    c.execute("DELETE FROM marcas WHERE nombre LIKE 'ESCALA-%'")
    conn.commit()
    ns["olvidar_la_escala_de_precios"]()

    # 9g. La auditoría de stock (ver generar_auditoria_hoy()): solo lo que tiene stock cargado,
    # y un conteo sin stock en el sistema no es una diferencia.
    c.execute("DELETE FROM auditoria_diaria")
    c.execute("UPDATE productos SET stock = NULL")
    conn.commit()
    esperar("sin stock cargado en ningún producto, no hay auditoría", ns["generar_auditoria_hoy"](5),
            None)
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio, "
              "stock) VALUES ('AUD1', 'AUD1', 'ACEITE POR LITRO', ?, 100, 2.5)", (marca,))
    conn.commit()
    esperar("con uno, la muestra es ese", (ns["generar_auditoria_hoy"](5),
                                          [f["Codigo"] for f in ns["listar_auditoria_hoy"]()]),
            (True, ["AUD1"]))
    _aud = ns["listar_auditoria_hoy"]()[0]["ID_auditoria"]
    ns["registrar_conteo_auditoria"](_aud, 1)
    _dif = ns["listar_auditoria_hoy"]()[0]["Diferencia"]
    esperar("la diferencia con decimales se muestra sin romper",
            [ns["texto_del_conteo"](x) for x in (_dif, 0, 3, None)],
            ["⚠️ Diferencia: −1,5", "✅ OK", "⚠️ Diferencia: +3",
             "sin stock en el sistema para comparar"])
    c.execute("INSERT INTO auditoria_diaria (fecha, producto_id, stock_sistema) "
              "VALUES ('2000-01-01', (SELECT id FROM productos WHERE codigo_clean = 'AUD1'), NULL)")
    _vieja = c.lastrowid
    conn.commit()
    ns["registrar_conteo_auditoria"](_vieja, 4)
    esperar("un conteo sin stock en el sistema no es una diferencia",
            c.execute("SELECT diferencia FROM auditoria_diaria WHERE id = ?", (_vieja,)).fetchone()[0],
            None)
    c.execute("DELETE FROM auditoria_diaria")
    c.execute("DELETE FROM productos WHERE codigo_clean = 'AUD1'")
    conn.commit()

    # 9h. Las consultas de clientes (ver historial_de_un_cliente()): el teléfono se encuentra
    # aunque esté anotado de otra forma, una letra suelta no trae a todos, y una consulta se
    # cierra solo como vendida o cancelada.
    for _nom, _tel in (("Ruiz", "11 5555-1234"), ("Gómez", "+54 9 351 444-9876"),
                       ("Alba", "")):
        ns["anotar_consulta_cliente"](_nom, _tel, codigo="W712", descripcion="FILTRO")
    _quien = lambda t: sorted(f["Cliente"] for f in ns["historial_de_un_cliente"](t))
    esperar("el teléfono, como esté anotado",
            [_quien(t) for t in ("1155551234", "+54 9 11 5555 1234", "15-5555-1234",
                                 "3514449876", "ruiz", "a", "%")],
            [["Ruiz"], ["Ruiz"], ["Ruiz"], ["Gómez"], ["Ruiz"], [], []])
    _una = ns["consultas_de_clientes"]()[0]["_id"]
    try:
        ns["cerrar_consulta"](_una, "vendido")
        _cerro = "aceptó «vendido»"
    except ValueError:
        _cerro = "no"
    esperar("una consulta no se cierra con un estado que no existe", _cerro, "no")
    esperar("y sí como vendida", ns["cerrar_consulta"](_una, "vendida"), True)
    c.execute("DELETE FROM consultas_cliente")
    conn.commit()

    # 9i. Pegar códigos de barras en masa (ver cargar_codigos_de_barras_masivo()). No tenía
    # prueba. Un código que no cierra no entra (salvo numeración propia); uno que ya tiene otro
    # producto de la misma lista tampoco; uno que tiene otra lista entra y se avisa.
    _dv = ns["digito_verificador_gtin"]
    _ean = lambda cuerpo: cuerpo + _dv(cuerpo)
    _b1, _b2, _b3 = _ean("779396002694"), _ean("779396002695"), _ean("779396002696")
    _typo = _b2[:-1] + str((int(_b2[-1]) + 1) % 10)
    _l = {}
    for _nom in ("BARRAS-1", "BARRAS-2", "BARRAS-3"):
        c.execute("INSERT INTO marcas (nombre, tipo) VALUES (?, 'PROVEEDOR')", (_nom,))
        _l[_nom] = c.lastrowid
    for _cod, _nom in (("BA1", "BARRAS-1"), ("BA2", "BARRAS-1"), ("BA3", "BARRAS-1"),
                       ("BB1", "BARRAS-2"), ("BC1", "BARRAS-3"), ("BC2", "BARRAS-3")):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
                  "VALUES (?, ?, 'PIEZA', ?)", (_cod, _cod, _l[_nom]))
    conn.commit()
    _cb = ns["cargar_codigos_de_barras_masivo"]
    _r1 = _cb([("BA1", _b1), ("BA2", _typo), ("BA3", _b3)], _l["BARRAS-1"])
    _r2 = _cb([("BA3", _b1)], _l["BARRAS-1"])
    _r3 = _cb([("BB1", _b1)], _l["BARRAS-2"])
    _r4 = _cb([("BC1", "1234567890123"), ("BC2", "1234567890124")], _l["BARRAS-3"])
    _barras = lambda cod: c.execute("SELECT codigo_barras FROM productos WHERE codigo_clean = ?",
                                    (cod,)).fetchone()[0]
    esperar("pegar códigos de barras: qué entra y qué no",
            ([_barras(x) for x in ("BA1", "BA2", "BA3", "BB1", "BC1", "BC2")],
             [x["Código"] for x in _r1["no_cierran"]], len(_r2["de_otro_de_la_lista"]),
             len(_r3["tambien_en_otra_lista"]), _r4["puestos"]),
            ([_b1, None, _b3, _b1, "1234567890123", "1234567890124"], ["BA2"], 1, 1, 2))
    c.execute("DELETE FROM productos WHERE codigo_clean IN ('BA1','BA2','BA3','BB1','BC1','BC2')")
    c.execute("DELETE FROM marcas WHERE nombre LIKE 'BARRAS-%'")
    conn.commit()

    # 9j. El «.0» de Excel (ver _RE_DECIMAL_DE_EXCEL): la alerta cuenta lo mismo que arregla el
    # botón. Un código que termina en «.0» porque así es («707994.00.0» de IMPERIAL, el espesor
    # de «900E-2.0») no es un error.
    for _cod in ("2776400.0", "707994.00.0", "900E-2.0"):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
                  "VALUES (?, ?, 'PIEZA', ?)", (_cod, ns["sanitizar"](_cod), marca))
    conn.commit()
    _antes_dec = ns["contar_codigos_con_decimal"]()
    _arreglados = ns["reparar_codigos_con_decimal"]()
    esperar("el «.0» de Excel: cuenta, arregla y queda en cero",
            (_antes_dec, _arreglados, ns["contar_codigos_con_decimal"](),
             sorted(r[0] for r in c.execute("SELECT codigo_raw FROM productos WHERE codigo_raw "
                                            "IN ('2776400', '707994.00.0', '900E-2.0')"))),
            (1, 1, 0, ["2776400", "707994.00.0", "900E-2.0"]))
    c.execute("DELETE FROM productos WHERE codigo_raw IN ('2776400', '707994.00.0', '900E-2.0')")
    conn.commit()

    # 9k. Los reemplazos de código (ver guardar_reemplazo()). No tenía prueba: un código viejo
    # tiene UN reemplazo vigente, un círculo no se acepta, y borrar el anterior y escribir el
    # nuevo es todo o nada.
    _gr = ns["guardar_reemplazo"]
    _r = [_gr("REEMP-A", "REEMP-B")[0], _gr("REEMP-A", "REEMP-C"), _gr("REEMP-C", "REEMP-A")[0],
          _gr("REEMP-A", "reemp a")[0]]
    esperar("reemplazos: uno vigente, sin círculos ni el mismo código",
            (_r[0], _r[1][0], "REEMP-B" in _r[1][1], _r[2], _r[3],
             [tuple(x) for x in c.execute("SELECT codigo_viejo_clean, codigo_nuevo_clean FROM "
                                          "reemplazos_codigo WHERE codigo_viejo_clean LIKE 'REEMP%'")]),
            (True, True, True, False, False, [("REEMPA", "REEMPC")]))
    _gn = ns["guardar_reemplazo"].__globals__
    _obtener = _gn["obtener_usuario_actual"]
    _gn["obtener_usuario_actual"] = lambda: (_ for _ in ()).throw(RuntimeError("corte"))
    try:
        _gr("REEMP-A", "REEMP-D")
    except RuntimeError:
        pass
    _gn["obtener_usuario_actual"] = _obtener
    esperar("si escribir el nuevo falla, el anterior sigue",
            [tuple(x) for x in c.execute("SELECT codigo_viejo_clean, codigo_nuevo_clean FROM "
                                         "reemplazos_codigo WHERE codigo_viejo_clean LIKE 'REEMP%'")],
            [("REEMPA", "REEMPC")])
    c.execute("DELETE FROM reemplazos_codigo WHERE codigo_viejo_clean LIKE 'REEMP%'")
    conn.commit()

    # 9l. El CBU/CVU de cobro (ver problema_del_cbu()): 22 números y sus dos dígitos
    # verificadores. Va impreso en el QR de cada cotización.
    c.execute("DELETE FROM alias_transferencia WHERE nombre = 'PRUEBA-PERMISO'")
    c.execute("DELETE FROM configuracion WHERE clave = 'coeficiente_lista_999999'")
    _cbu_bien = "2850590940090418135201"
    esperar("el CBU: bien, con espacios, mal copiado, corto, vacío",
            [bool(ns["problema_del_cbu"](x)) for x in
             (_cbu_bien, "285 0590-9 40090418135201", "2850590940090418135202",
              "2850590940090418135", "")],
            [False, False, True, True, False])
    try:
        ns["guardar_alias_transferencia"]("PRUEBA-CBU", "alias.mal", "2850590940090418135202", "")
        _guardo_mal = True
    except ValueError:
        _guardo_mal = False
    ns["guardar_alias_transferencia"]("PRUEBA-CBU", "alias.bien", "285 0590-9 40090418135201", "")
    esperar("con el CBU mal no se guarda; bien, se guarda solo con los números",
            (_guardo_mal, c.execute("SELECT cbu FROM alias_transferencia WHERE nombre = "
                                    "'PRUEBA-CBU'").fetchone()[0]), (False, _cbu_bien))
    c.execute("DELETE FROM alias_transferencia WHERE nombre LIKE 'PRUEBA-%'")
    conn.commit()

    # 9l bis. El link de pago (ver «EL QR QUE ABRE LA PÁGINA PARA PAGAR»): es lo que abre el QR
    # de la cotización, así que se controla como el CBU. La @ es la trampa: abre la otra página.
    esperar("el link: bien, http, con @, con espacio, sin https, sin sitio, vacío",
            [bool(ns["problema_del_link_de_pago"](x)) for x in
             ("https://link.mercadopago.com.ar/elchavo", "http://link.mercadopago.com.ar/x",
              "https://mercadopago.com.ar@otro.sitio/x", "https://link.mercado pago.com/x",
              "link.mercadopago.com.ar/x", "https://localhost/x", "")],
            [False, True, True, True, True, True, False])
    esperar("la página que abre, la de después de la @",
            (ns["sitio_del_link_de_pago"]("https://link.mercadopago.com.ar/elchavo"),
             "otro.sitio" in ns["problema_del_link_de_pago"]("https://mercadopago.com.ar@otro.sitio/x")),
            ("link.mercadopago.com.ar", True))
    try:
        ns["guardar_alias_transferencia"]("PRUEBA-LINK", "el.chavo", "", "", link_pago="http://x.com")
        _guardo_mal = True
    except ValueError:
        _guardo_mal = False
    _link = "https://link.mercadopago.com.ar/elchavo"
    ns["guardar_alias_transferencia"]("PRUEBA-LINK", "el.chavo", _cbu_bien, "El Chavo SRL",
                                      link_pago=f"  {_link} ")
    _al = next(a for a in ns["listar_alias_transferencia"]() if a["Nombre"] == "PRUEBA-LINK")
    ns["guardar_alias_transferencia"]("PRUEBA-LINK", "el.chavo", _cbu_bien, "El Chavo SRL",
                                      alias_id=_al["ID"])
    _sigue = next(a for a in ns["listar_alias_transferencia"]() if a["Nombre"] == "PRUEBA-LINK")["Link"]
    esperar("con el link mal no se guarda; bien, sin espacios; sin pasarlo queda el que tenía",
            (_guardo_mal, _al["Link"], _sigue), (False, _link, _link))
    _msj = ns["armar_mensaje_de_cotizacion"](
        [{"codigo_buscado": "W712", "resultados": [{"Marca": "MANN", "Codigo": "W712"}]}],
        "ENCABEZADO", "PIE", False, cobro=_al)
    esperar("el mensaje: link para tocar, alias y CBU, antes del pie",
            (f"💳 *Para pagar:* {_link}" in _msj, "alias *el.chavo*" in _msj,
             f"CBU/CVU {_cbu_bien}" in _msj, "a nombre de El Chavo SRL" in _msj,
             _msj.index(_link) < _msj.index("PIE"),
             "Para pagar" in ns["armar_mensaje_de_cotizacion"](
                 [{"codigo_buscado": "W712", "resultados": []}], "", "", False)),
            (True, True, True, True, True, False))
    _gi = ns["generar_pdf_cotizacion"].__globals__
    _qr_original, _textos_qr = _gi["generar_qr_bytes"], []
    _gi["generar_qr_bytes"] = lambda texto: (_textos_qr.append(texto), _qr_original(texto))[1]
    try:
        _pdf_link = ns["generar_pdf_cotizacion"](
            [{"codigo_buscado": "W712", "resultados": [{"Marca": "MANN", "Codigo": "W712"}]}],
            False, False, _al, None)
        ns["generar_pdf_cotizacion"](
            [{"codigo_buscado": "W712", "resultados": []}], False, False, dict(_al, Link=""), None)
        ns["generar_pdf_cotizacion"](
            [{"codigo_buscado": "W712", "resultados": []}], False, False, _al, _qr_original("REAL"))
    finally:
        _gi["generar_qr_bytes"] = _qr_original
    esperar("el QR del PDF: el link si hay; si no, el texto; con el real, ninguno armado acá",
            (_textos_qr[0], _textos_qr[1].startswith("Alias: el.chavo"), len(_textos_qr),
             f"/URI ({_link})".encode() in _pdf_link),
            (_link, True, 2, True))
    ns["eliminar_alias_transferencia"](_al["ID"])
    _papelera = c.execute("SELECT id FROM papelera WHERE tipo = 'alias' ORDER BY id DESC").fetchone()[0]
    ns["restaurar_de_papelera"](_papelera)
    esperar("borrado y restaurado, vuelve con su link",
            c.execute("SELECT link_pago FROM alias_transferencia WHERE nombre = 'PRUEBA-LINK'").fetchone()[0],
            _link)
    c.execute("DELETE FROM alias_transferencia WHERE nombre LIKE 'PRUEBA-%'")
    conn.commit()

    # 9l ter. Lo que ve el cliente de su auto (ver «LO QUE VE EL CLIENTE DE SU AUTO»): cuánto
    # le falta a cada pieza con la ÚLTIMA vez que se cambió, y entrar solo con el link o con
    # los últimos 4 del teléfono, sin ver nombre, teléfono ni notas, y con tope de intentos.
    c.execute("""INSERT INTO vehiculos (patente, cliente_nombre, cliente_telefono, marca_auto,
                 modelo_auto, anio, km_registro, km_actual, created_at, km_actualizado_fecha)
                 VALUES ('AB 123 CD', 'Juan Prueba', '11 4567-8901', 'VW', 'Gol', '2012',
                         50000, 60000, datetime('now', '-100 days'), datetime('now', '-10 days'))""")
    _auto = c.lastrowid
    for _pieza, _km, _vida, _nota in (("Filtro de aceite", 50000, 10000, ""),
                                      ("FILTRO DE ACEITE", 59000, None, "debe plata"),
                                      ("Correa de distribución", 20000, 40000, ""),
                                      ("Pastillas de freno", 58000, 5000, ""),
                                      ("Escobillas", 60000, None, "")):
        c.execute("""INSERT INTO historial_piezas (vehiculo_id, descripcion_pieza, marca_pieza,
                     km_instalacion, vida_util_km, nota) VALUES (?, ?, 'MARCA', ?, ?, ?)""",
                  (_auto, _pieza, _km, _vida, _nota))
    conn.commit()
    _v = dict(c.execute("SELECT * FROM vehiculos WHERE id = ?", (_auto,)).fetchone())
    # Cargada con espacios, se encuentra junta y con guiones; y guardarla escrita de otra forma
    # actualiza esa ficha en vez de crear otra (ver buscar_vehiculo()).
    c.execute("""INSERT INTO vehiculos (patente, marca_auto) VALUES ('AF 555 GH', 'FORD')""")
    _otra_forma = ns["get_or_create_vehiculo"]("af-555-gh", modelo_auto="Ka")
    esperar("la patente como esté escrita: se encuentra, y no se duplica la ficha",
            (ns["buscar_vehiculo"]("af555gh")["marca_auto"], ns["buscar_vehiculo"]("AF-555-GH")["id"],
             _otra_forma == ns["buscar_vehiculo"]("AF555GH")["id"],
             c.execute("SELECT COUNT(*), MAX(modelo_auto) FROM vehiculos WHERE "
                       "REPLACE(patente, ' ', '') = 'AF555GH'").fetchone()[:],
             ns["guardar_numero_de_motor"]("af555gh", "M-9"),
             ns["buscar_vehiculo"]("ZZ999ZZ")),
            ("FORD", _otra_forma, True, (1, "Ka"), True, None))
    c.execute("DELETE FROM vehiculos WHERE marca_auto = 'FORD' AND patente = 'AF 555 GH'")
    _estado = ns["estado_de_cada_pieza"](_v)
    # 10.000 km en 90 días: 111 por día; 10 días después de anotado, hoy tendría 61.111.
    esperar("cuánto le falta a cada pieza: la última vez, con la vida útil de la anterior",
            [(p["Pieza"], p["Estado"], p["Le falta"]) for p in _estado],
            [("Correa de distribución", "🔴 Ya le toca", "ya pasó 1.111 km"),
             ("Pastillas de freno", "🟡 Le toca pronto", "1.889 km (unos 17 días)"),
             ("FILTRO DE ACEITE", "🟢 Bien", "7.889 km (unos 71 días)"),
             ("Escobillas", "⚪ Sin datos", "falta la vida útil")])
    _avisos = [x for x in ns["a_quien_avisar"](30) if x["Patente"] == "AB 123 CD"]
    esperar("a quién avisar: la misma cuenta (el filtro se cambió a los 59.000, no toca), con "
            "el link del auto en el mensaje",
            (sorted(x["Pieza"] for x in _avisos),
             all("auto%3DAB123CD%26clave%3D" in x["_whatsapp"] for x in _avisos)),
            (["Correa de distribución", "Pastillas de freno"], True))
    _link = ns["link_publico_del_auto"](_auto)
    _clave = _link.rsplit("clave=", 1)[-1]
    _link_otra_vez = ns["link_publico_del_auto"](_auto)
    esperar("el link: la app, la patente sin espacios y una clave de 10 que se puede dictar",
            (_link.startswith(ns["URL_DE_LA_APP"] + "?auto=AB123CD&clave="), len(_clave),
             set(_clave) <= set(ns["_LETRAS_DE_LA_CLAVE"]), _link_otra_vez == _link),
            (True, 10, True, True))
    _con_link, _motivo_link = ns["abrir_ficha_publica"]("ab123cd", clave=_clave.lower())
    _todo = json.dumps(_con_link, ensure_ascii=False, default=str)
    # Ya hay una ficha «AB123CD» de una prueba de arriba, sin clave ni teléfono: son dos fichas
    # de la misma patente escrita distinto, y tiene que encontrar la que coincide.
    esperar("con el link se ve el auto, sin nombre, teléfono ni notas",
            (_con_link["auto"], len(_con_link["historial"]), _con_link["km_hoy"],
             "Juan" in _todo, "4567" in _todo, "8901" in _todo, "debe plata" in _todo,
             "ID" in _con_link["historial"][0], _con_link["historial"][0]["Km"],
             _con_link["historial"][0]["Código"], len(_con_link["historial"][0]["Fecha"])),
            ("VW Gol 2012", 5, 61111, False, False, False, False, False, "60.000", "", 10))
    _con_km, _ = ns["abrir_ficha_publica"]("AB123CD", clave=_clave, km_de_hoy=62000)
    _km_menor, _ = ns["abrir_ficha_publica"]("AB123CD", clave=_clave, km_de_hoy=55000)
    esperar("lo próximo, lo que le toca, y el km que escribe el cliente (menor al anotado, no)",
            (_con_link["proximo"], _con_link["le_toca"], _con_km["km_hoy"],
             _con_km["km_del_cliente"], _con_km["proximo"]["Le falta"],
             _km_menor["km_hoy"], _km_menor["km_del_cliente"], bool(_km_menor["km_de_hoy_no_va"])),
            ({"Pieza": "Correa de distribución", "Estado": "🔴 Ya le toca",
              "Le falta": "ya pasó 1.111 km"}, ["Correa de distribución", "Pastillas de freno"],
             62000, True, "ya pasó 2.000 km", 61111, False, True))
    esperar("el km del cliente no se guarda",
            c.execute("SELECT km_actual FROM vehiculos WHERE id = ?", (_auto,)).fetchone()[0], 60000)
    esperar("el WhatsApp del negocio: bien, sin 9, con 0 y 15, vacío",
            [bool(ns["problema_del_whatsapp_del_negocio"](x)) for x in
             ("+54 9 11 4567-8901", "541145678901", "54 9 011 15 4567 8901", "")],
            [False, True, True, False])
    _nuevo = ns["link_publico_del_auto"](_auto, nueva=True)
    _viejo, _motivo_viejo = ns["abrir_ficha_publica"]("AB123CD", clave=_clave)
    esperar("un link que no anda no cuenta como intento fallido (la clave no se adivina)",
            c.execute("SELECT COUNT(*) FROM intentos_consulta_publica").fetchone()[0], 0)
    _tel_bien, _ = ns["abrir_ficha_publica"]("AB-123-CD", ultimos_del_telefono="8901")
    _tel_mal, _motivo_mal = ns["abrir_ficha_publica"]("AB123CD", ultimos_del_telefono="8900")
    _no_existe, _motivo_no_existe = ns["abrir_ficha_publica"]("ZZ999ZZ", ultimos_del_telefono="8901")
    _sin_numeros, _motivo_sin = ns["abrir_ficha_publica"]("AB123CD")
    esperar("link cambiado no anda; con los 4 del teléfono sí; mal o sin auto, lo mismo",
            (_nuevo != _link, _viejo, _tel_bien is not None, _tel_mal, _motivo_mal == _motivo_viejo,
             _no_existe, _motivo_no_existe == _motivo_mal, _sin_numeros, "4 números" in _motivo_sin),
            (True, None, True, None, True, None, True, None, True))
    # El link viejo no cuenta como intento: la clave no se adivina, y si contara, fallando
    # con links cualquiera se le bloqueaba el link bueno al dueño.
    for _ in range(ns["INTENTOS_FALLIDOS_POR_PATENTE_POR_DIA"] - 1):
        ns["abrir_ficha_publica"]("AB123CD", ultimos_del_telefono="0000")
    _antes_del_tope = c.execute("SELECT COUNT(*) FROM intentos_consulta_publica WHERE "
                                "patente = 'AB123CD'").fetchone()[0]
    _bloqueado, _motivo_bloqueo = ns["abrir_ficha_publica"]("AB123CD", ultimos_del_telefono="8901")
    _con_link_igual, _ = ns["abrir_ficha_publica"]("AB123CD", clave=_nuevo.rsplit("=", 1)[-1])
    esperar("con 5 intentos mal en el día, ni con los números bien; con el link, sí",
            (_antes_del_tope, _bloqueado, "demasiados intentos" in _motivo_bloqueo,
             _con_link_igual is not None), (5, None, True, True))
    c.execute("DELETE FROM intentos_consulta_publica")
    c.execute("""INSERT INTO vehiculos (patente, cliente_telefono, km_actual)
                 VALUES ('AC456DE', '1234', 1000)""")
    _tel_corto, _ = ns["abrir_ficha_publica"]("AC456DE", ultimos_del_telefono="1234")
    c.executemany("INSERT INTO intentos_consulta_publica (patente) VALUES (?)",
                  [(f"XX{i:03d}XX",) for i in range(ns["INTENTOS_FALLIDOS_EN_TOTAL_POR_HORA"])])
    _todos_bloqueados, _ = ns["abrir_ficha_publica"]("AB123CD", ultimos_del_telefono="8901")
    esperar("con teléfono corto solo entra con el link; con 60 intentos en la hora, nadie",
            (_tel_corto, _todos_bloqueados), (None, None))
    _pdf_ficha = ns["generar_pdf_ficha_vehiculo"](_v, {}, [], [], [], _nuevo)
    esperar("la ficha en PDF lleva el link tocable",
            f"/URI ({_nuevo})".encode() in _pdf_ficha, True)
    # Anotar una pieza: queda atada al producto del catálogo si el código no deja dudas, y sin
    # vida útil usa la de las otras veces (ver agregar_pieza_historial()).
    _con_codigo = ns["agregar_pieza_historial"](_auto, "filtro  de ACEITE", "", "p-1", 61000,
                                                None, "")
    _otra_marca = ns["agregar_pieza_historial"](_auto, "Bujía", "OTRA MARCA", "P1", 61000,
                                                None, "")
    c.execute("UPDATE vehiculos SET numero_motor = 'MOTPRUEBA-77' WHERE id = ?", (_auto,))
    _por_motor = ns["repuestos_por_numero_motor"]("MOTPRUEBA77")
    esperar("la pieza anotada: atada al catálogo, con su marca y la vida útil de antes; de "
            "otra marca, suelta; y por número de motor se ve aunque esté suelta",
            (_con_codigo, _otra_marca["producto_id"], _otra_marca["vida_util"],
             sorted((f["Código"], f["Marca"]) for f in _por_motor if f["Código"])),
            ({"producto_id": b, "marca": "PRUEBA", "vida_util": 10000,
              "vida_de_otras_veces": True}, None, None,
             [("P1", "OTRA MARCA"), ("P1", "PRUEBA")]))
    c.execute("DELETE FROM intentos_consulta_publica")
    c.execute("DELETE FROM historial_piezas WHERE vehiculo_id = ?", (_auto,))
    c.execute("DELETE FROM vehiculos WHERE patente IN ('AB 123 CD', 'AC456DE')")
    conn.commit()

    # 9m. Confirmar una sugerencia (ver confirmar_candidata()). No tenía prueba: si el código
    # que pedía el cliente no existe, lo crea con la marca elegida y los vincula en UNA fila;
    # sin marca no inventa nada, y dos veces no duplica.
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
              "VALUES ('CAND1', 'CAND1', 'FILTRO DE PRUEBA', ?)", (marca,))
    _cand = c.lastrowid
    conn.commit()
    _sin_marca = ns["confirmar_candidata"]("PEDIDO9", _cand, "pedido-9")
    _con_marca = ns["confirmar_candidata"]("PEDIDO9", _cand, "pedido-9", "FABRICA PRUEBA")
    _otra_vez = ns["confirmar_candidata"]("PEDIDO9", _cand, "pedido-9", "FABRICA PRUEBA")
    _mismo = ns["confirmar_candidata"]("CAND1", _cand, "CAND1")
    _pedido = c.execute("SELECT id, descripcion FROM productos WHERE codigo_clean = 'PEDIDO9'").fetchall()
    esperar("confirmar una sugerencia: crea, vincula una vez, sin inventar",
            (_sin_marca[0], _con_marca, _otra_vez[0], _mismo[0], len(_pedido),
             _pedido[0]["descripcion"] if _pedido else None,
             c.execute("SELECT COUNT(*) FROM equivalencias WHERE ? IN (producto_a_id, producto_b_id)",
                       (_cand,)).fetchone()[0]),
            (False, (True, None), True, False, 1, "FILTRO DE PRUEBA", 1))
    c.execute("DELETE FROM equivalencias WHERE ? IN (producto_a_id, producto_b_id)", (_cand,))
    c.execute("DELETE FROM productos WHERE codigo_clean IN ('CAND1', 'PEDIDO9')")
    c.execute("DELETE FROM marcas WHERE nombre = 'FABRICA PRUEBA'")
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

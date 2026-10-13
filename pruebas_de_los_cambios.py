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
                     ("aplicar los precios frenados", ns["aplicar_precios_frenados"], ([],)))
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
        # Se saca lo creado: más abajo se cuentan los productos y las marcas.
        c.execute("DELETE FROM historial_precios WHERE producto_id = ?", (_p_fr,))
        c.execute("DELETE FROM productos WHERE id = ?", (_p_fr,))
        c.execute("DELETE FROM marcas WHERE id = ?", (_m_fr,))
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

"""Pruebas de la factura electrónica de ARCA, a pedido de la caja: el permiso firmado con el
certificado, el CAE, el número que sigue, la que queda pendiente por un corte, la nota de
crédito, el QR y el PDF.

Uso:
    python3 pruebas/pruebas_de_las_facturas.py

ARCA no se llama de verdad: se simula con respuestas como las del WSAA y el WSFEv1, y un
certificado hecho en el momento. Ver «LA FACTURA ELECTRÓNICA (ARCA)» en logica/facturas.py.
Corre en una carpeta temporal: nunca toca la base de trabajo.
"""
import base64
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone


def _cargar_la_logica(carpeta):
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, raiz)
    os.chdir(carpeta)
    import logica
    return logica


def _certificado_de_prueba():
    """(certificado PEM, clave PEM) hechos en el momento: no hace falta uno de ARCA."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "prueba"),
                        x509.NameAttribute(NameOID.SERIAL_NUMBER, "CUIT 20111111112")])
    ahora = datetime.now(timezone.utc)
    certificado = (x509.CertificateBuilder().subject_name(nombre).issuer_name(nombre)
                   .public_key(clave.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(ahora - timedelta(days=1))
                   .not_valid_after(ahora + timedelta(days=30)).sign(clave, hashes.SHA256()))
    return (certificado.public_bytes(serialization.Encoding.PEM).decode(),
            clave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode())


class _ArcaDePrueba:
    """Contesta como el WSAA y el WSFEv1. Anota lo que le pidieron."""

    def __init__(self, requests_de_verdad):
        self.RequestException = requests_de_verdad.RequestException
        self._ConnectionError = requests_de_verdad.ConnectionError
        self.ultimo = {}          # (pto, tipo) -> último número autorizado
        self.autorizadas = {}     # (pto, tipo, número) -> (cae, total)
        self.pedidos = []         # (acción, cuerpo)
        self.logins = 0
        self.cortar_el_proximo_cae = False
        self.autorizar_aunque_se_corte = False

    def post(self, url, data=None, timeout=None, headers=None):
        accion = (headers or {}).get("SOAPAction", "").strip('"')
        cuerpo = data.decode("utf-8")
        self.pedidos.append((accion, cuerpo))
        if accion == "":
            self.logins += 1
            cms = re.search(r"<in0>(.*?)</in0>", cuerpo).group(1)
            assert b"<loginTicketRequest" in base64.b64decode(cms), "el TRA no va adentro"
            vence = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
            ticket = (f"<loginTicketResponse><header><expirationTime>{vence}</expirationTime>"
                      "</header><credentials><token>TOKEN&amp;1</token><sign>FIRMA</sign>"
                      "</credentials></loginTicketResponse>")
            return self._respuesta(f"<loginCmsResponse><loginCmsReturn>"
                                   f"{ticket.replace('&', '&amp;').replace('<', '&lt;')}"
                                   "</loginCmsReturn></loginCmsResponse>")
        def valor(nombre):
            m = re.search(rf"<{nombre}>(.*?)</{nombre}>", cuerpo)
            return m.group(1) if m else ""
        if accion.endswith("FECompUltimoAutorizado"):
            n = self.ultimo.get((int(valor("PtoVta")), int(valor("CbteTipo"))), 0)
            return self._respuesta(f"<R><CbteNro>{n}</CbteNro></R>")
        if accion.endswith("FECAESolicitar"):
            pto, tipo, numero = int(valor("PtoVta")), int(valor("CbteTipo")), int(valor("CbteDesde"))
            if numero != self.ultimo.get((pto, tipo), 0) + 1:
                return self._respuesta("<R><Resultado>R</Resultado><Errors><Err><Code>10016</Code>"
                                       "<Msg>El numero no es el proximo a autorizar</Msg></Err>"
                                       "</Errors></R>")
            cae = f"7{pto:03d}{tipo:02d}{numero:08d}"
            if self.cortar_el_proximo_cae:
                self.cortar_el_proximo_cae = False
                if self.autorizar_aunque_se_corte:
                    self.ultimo[(pto, tipo)] = numero
                    self.autorizadas[(pto, tipo, numero)] = (cae, float(valor("ImpTotal")))
                raise self._ConnectionError("se cortó")
            self.ultimo[(pto, tipo)] = numero
            self.autorizadas[(pto, tipo, numero)] = (cae, float(valor("ImpTotal")))
            return self._respuesta(f"<R><Resultado>A</Resultado><CAE>{cae}</CAE>"
                                   "<CAEFchVto>20261120</CAEFchVto></R>")
        if accion.endswith("FECompConsultar"):
            clave = (int(valor("PtoVta")), int(valor("CbteTipo")), int(valor("CbteNro")))
            if clave in self.autorizadas:
                cae, total = self.autorizadas[clave]
                return self._respuesta(f"<R><CodAutorizacion>{cae}</CodAutorizacion>"
                                       f"<ImpTotal>{total:.2f}</ImpTotal><FchVto>20261120</FchVto></R>")
            return self._respuesta("<R><Errors><Err><Code>602</Code><Msg>No existen datos</Msg>"
                                   "</Err></Errors></R>")
        raise AssertionError(f"acción desconocida: {accion}")

    @staticmethod
    def _respuesta(adentro):
        class R:
            status_code = 200
            content = ('<?xml version="1.0"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org'
                       f'/soap/envelope/"><soap:Body>{adentro}</soap:Body></soap:Envelope>').encode()
        return R()


def probar(L):
    ns = L.todo_lo_de_la_logica()
    c, conn, st = ns["c"], ns["conn"], ns["st"]
    g = ns["facturar_venta"].__globals__
    fallas = []

    def esperar(nombre, real, esperado):
        if real != esperado:
            fallas.append(f"{nombre}: dio {real!r}, se esperaba {esperado!r}")

    def uno(sql, *args):
        fila = c.execute(sql, args).fetchone()
        return fila[0] if fila else None

    # 1. Lo que se arma sin hablar con nadie.
    esperar("el tipo: C del monotributista; A al inscripto y B a los demás",
            [ns["tipo_de_factura"](n, k) for n, k in
             (("monotributo", "Responsable inscripto"), ("responsable_inscripto",
              "Responsable inscripto"), ("responsable_inscripto", "Consumidor final"))],
            [11, 1, 6])
    esperar("los importes: en la B se separa el IVA del total; en la C no",
            (ns["importes_de_la_factura"](12100, 6), ns["importes_de_la_factura"](12100, 11)),
            ({"total": 12100.0, "neto": 10000.0, "iva": 2100.0},
             {"total": 12100.0, "neto": 12100.0, "iva": 0.0}))
    _cliente = ns["cliente_de_la_factura"]
    esperar("el cliente: sin documento, con DNI, con CUIT; y lo que no va",
            [(_cliente(*a)[0] or {}).get("doc_tipo") for a in
             (("Consumidor final", ""), ("Consumidor final", "30.123.456"),
              ("Responsable inscripto", "20-11111111-2"), ("Responsable inscripto", ""),
              ("Consumidor final", "123"))],
            [99, 96, 80, None, None])
    esperar("sin los datos en los secretos, dice qué falta",
            (ns["configuracion_de_arca"](), len(ns["lo_que_falta_para_facturar"]()) >= 4),
            (None, True))

    # 2. Con los datos, contra un ARCA de prueba.
    cert, clave = _certificado_de_prueba()
    secretos = {"cuit": "20-11111111-2", "punto_de_venta": 3, "condicion": "responsable_inscripto",
                "ambiente": "homologacion", "certificado": cert, "clave_privada": clave,
                "razon_social": "El Chavo de prueba", "domicilio": "Calle 1"}
    _secretos_reales, _requests_reales = g["_secretos_de_arca"], g["requests"]
    g["_secretos_de_arca"] = lambda: dict(secretos)
    arca = _ArcaDePrueba(_requests_reales)
    g["requests"] = arca
    try:
        st.session_state["admin_nombre"], st.session_state["nivel_usuario"] = "ana", "operador"
        c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('PRUEBA', 'PROVEEDOR')")
        marca = c.lastrowid
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio, "
                  "stock) VALUES ('F1', 'F1', 'FILTRO ACEITE', ?, 12100, 10)", (marca,))
        pid = c.lastrowid
        conn.commit()
        item = lambda n=1: dict(ns["item_de_venta"](pid, n))
        esperar("la configuración se lee", (ns["configuracion_de_arca"] () or {}).get("cuit"),
                "20111111112")
        arca.ultimo[(3, 6)] = 41
        v1, _ = ns["cerrar_venta"]([item()], a_la_caja=True)
        esperar("esperando en la caja no se factura",
                ns["facturar_venta"](v1)[0], False)
        ns["cobrar_venta"](v1, "Efectivo")
        ok1, texto1 = ns["facturar_venta"](v1)
        f1 = dict(c.execute("SELECT * FROM facturas WHERE venta_id = ?", (v1,)).fetchone())
        esperar("facturada: la B que sigue a la 41, con su CAE",
                (ok1, f1["tipo"], f1["numero"], f1["estado"], f1["cae"], f1["cae_vence"],
                 "Factura B 00003-00000042" in texto1),
                (True, 6, 42, "autorizada", "700306" + "00000042", "2026-11-20", True))
        _pedido = next(b for a, b in arca.pedidos if a.endswith("FECAESolicitar"))
        esperar("lo que se le mandó: consumidor final, IVA separado, la condición del cliente",
                [re.search(rf"<{n}>(.*?)</{n}>", _pedido).group(1)
                 for n in ("DocTipo", "ImpTotal", "ImpNeto", "ImpIVA", "CondicionIVAReceptorId")],
                ["99", "12100.00", "10000.00", "2100.00", "5"])
        esperar("el token va escapado en el XML", "<Token>TOKEN&amp;1</Token>" in _pedido, True)
        esperar("la misma venta no se factura dos veces", ns["facturar_venta"](v1)[0], False)
        v2, _ = ns["cerrar_venta"]([item(2)], a_la_caja=True)
        ns["cobrar_venta"](v2, "Transferencia")
        ok2, _ = ns["facturar_venta"](v2, "Responsable inscripto", "30-71234567-1", "Taller SA")
        esperar("a un inscripto, la A; y el permiso de ARCA se usó de nuevo, sin pedir otro",
                (ok2, uno("SELECT tipo FROM facturas WHERE venta_id = ?", v2), arca.logins),
                (True, 1, 1))

        # 3. Se corta en el medio: queda pendiente y se resuelve consultándola.
        v3, _ = ns["cerrar_venta"]([item()], a_la_caja=True)
        ns["cobrar_venta"](v3, "Efectivo")
        arca.cortar_el_proximo_cae, arca.autorizar_aunque_se_corte = True, True
        ok3, texto3 = ns["facturar_venta"](v3)
        f3 = uno("SELECT id FROM facturas WHERE venta_id = ?", v3)
        esperar("cortado: pendiente, y lo dice sin direcciones",
                (ok3, uno("SELECT estado FROM facturas WHERE id = ?", f3), "pendiente" in texto3,
                 "http" in texto3 or "afip.gov" in texto3), (False, "pendiente", True, False))
        esperar("pendiente no se pide de nuevo", ns["facturar_venta"](v3)[0], False)
        esperar("y la campanita la avisa",
                any("factura(s) pendiente(s)" in p["titulo"] for p in ns["diagnostico_de_salud"]()),
                True)
        ok3b, _ = ns["consultar_factura_pendiente"](f3)
        esperar("ARCA la tenía: queda autorizada con su CAE",
                (ok3b, uno("SELECT estado FROM facturas WHERE id = ?", f3),
                 bool(uno("SELECT cae FROM facturas WHERE id = ?", f3))), (True, "autorizada", True))
        v4, _ = ns["cerrar_venta"]([item()], a_la_caja=True)
        ns["cobrar_venta"](v4, "Efectivo")
        arca.cortar_el_proximo_cae, arca.autorizar_aunque_se_corte = True, False
        ns["facturar_venta"](v4)
        f4 = uno("SELECT id FROM facturas WHERE venta_id = ? ORDER BY id DESC", v4)
        ns["consultar_factura_pendiente"](f4)
        esperar("ARCA no la tenía: rechazada, y se puede volver a facturar",
                (uno("SELECT estado FROM facturas WHERE id = ?", f4), ns["facturar_venta"](v4)[0]),
                ("rechazada", True))

        # 4. La nota de crédito, y lo que no se puede hacer con una venta facturada.
        esperar("con factura: no vuelve a la caja", ns["volver_a_la_caja"](v1)[0], False)
        st.session_state["nivel_usuario"] = "admin"
        esperar("ni se anula", ns["anular_venta"](v1)[0], False)
        st.session_state["nivel_usuario"] = "operador"
        esperar("cambiar cómo pagó sí", ns["cambiar_como_se_pago"](v1, "Tarjeta de débito")[0], True)
        okn, textonc = ns["nota_de_credito"](f1["id"])
        _nc = next(b for a, b in reversed(arca.pedidos) if a.endswith("FECAESolicitar"))
        esperar("la nota de crédito: la B anula con la 8, asociada a la factura",
                (okn, uno("SELECT tipo FROM facturas WHERE asociada_a = ?", f1["id"]),
                 "<CbtesAsoc><CbteAsoc><Tipo>6</Tipo><PtoVta>3</PtoVta><Nro>42</Nro>" in _nc,
                 "Nota de crédito B" in textonc), (True, 8, True, True))
        esperar("anulada la factura: ya no está vigente, y no se anula dos veces",
                (ns["factura_vigente_de"](v1), ns["nota_de_credito"](f1["id"])[0]), (None, False))
        esperar("con la nota de crédito, vuelve a la caja", ns["volver_a_la_caja"](v1)[0], True)

        # 4b. La nota de crédito parcial: lo devuelto de una venta facturada. La factura sigue
        # vigente por lo que le queda, y la última nota cierra justo el neto y el IVA.
        v6, _ = ns["cerrar_venta"]([item(2)], a_la_caja=True)
        ns["cobrar_venta"](v6, "Efectivo")
        ns["facturar_venta"](v6)
        f6 = ns["factura_vigente_de"](v6)
        okp, textop = ns["nota_de_credito"](f6["id"], 12100)
        esperar("parcial: hecha, y a la factura le queda la otra mitad",
                (okp, ns["factura_vigente_de"](v6)["queda"], ns["volver_a_la_caja"](v6)[0]),
                (True, 12100.0, False))
        esperar("más de lo que queda, no", ns["nota_de_credito"](f6["id"], 20000)[0], False)
        okr, _ = ns["nota_de_credito"](f6["id"])
        esperar("la última por lo que queda: cierran el neto y el IVA, y deja de estar vigente",
                (okr, uno("SELECT SUM(neto) FROM facturas WHERE asociada_a = ?", f6["id"]),
                 uno("SELECT SUM(iva) FROM facturas WHERE asociada_a = ?", f6["id"]),
                 ns["factura_vigente_de"](v6)), (True, f6["neto"], f6["iva"], None))

        # 4c. Lo que dice el comprobante queda guardado al hacerlo: lo devuelto antes de facturar
        # no se factura, la nota por lo devuelto lleva ese renglón, la que anula entera repite
        # los de la factura. Y lo que ARCA rechazaría se frena antes: el CUIT mal tipeado y el
        # consumidor final sin documento de mucha plata.
        _mal = ns["cliente_de_la_factura"]("Responsable inscripto", "30-71234567-2")
        esperar("el CUIT con el último número que no cierra: no pasa, y dice cuál",
                (_mal[0], "30-71234567-2 no cierra" in (_mal[1] or "")), (None, True))
        v9, _ = ns["cerrar_venta"]([item(3)], a_la_caja=True)
        ns["cobrar_venta"](v9, "Tarjeta de crédito", cuotas=3)
        ns["devolver_de_una_venta"](uno("SELECT id FROM ventas_items WHERE venta_id = ?", v9), 1,
                                    "no_le_iba")
        ok9, _ = ns["facturar_venta"](v9)
        f9 = dict(c.execute("SELECT * FROM facturas WHERE venta_id = ?", (v9,)).fetchone())
        _d9 = json.loads(f9["detalle"])
        esperar("devuelto uno antes de facturar: la factura va por los otros dos, y lo dice",
                (ok9, f9["total"], _d9["renglones"], _d9["condicion_de_venta"]),
                (True, 24200.0, [[2, "PRUEBA F1 - FILTRO ACEITE", 12100.0]],
                 "Tarjeta de crédito (3 cuotas)"))
        okd, _ = ns["nota_de_credito"](f9["id"], 12100,
                                       renglones=[[1, "PRUEBA F1 - FILTRO ACEITE", 12100.0]])
        _n9 = json.loads(uno("SELECT detalle FROM facturas WHERE asociada_a = ?", f9["id"]))
        esperar("la nota por lo devuelto: ese renglón, con la condición de venta de la factura",
                (okd, _n9["renglones"], _n9["condicion_de_venta"]),
                (True, [[1, "PRUEBA F1 - FILTRO ACEITE", 12100.0]], "Tarjeta de crédito (3 cuotas)"))
        esperar("sin renglones: la parcial y la que cierra lo dicen",
                [json.loads(d)["renglones"][0][1].split(" de la Factura")[0] for (d,) in
                 c.execute("SELECT detalle FROM facturas WHERE asociada_a = ? ORDER BY id",
                           (f6["id"],)).fetchall()],
                ["Anulación parcial", "Anulación de lo que quedaba"])
        esperar("la que anula entera repite los renglones de la factura",
                json.loads(uno("SELECT detalle FROM facturas WHERE asociada_a = ?",
                               f1["id"]))["renglones"], json.loads(f1["detalle"])["renglones"])
        v10, _ = ns["cerrar_venta"]([item()], a_la_caja=True)
        ns["cobrar_venta"](v10, "Efectivo")
        _tope = g["TOPE_CONSUMIDOR_FINAL_SIN_DOCUMENTO"]
        g["TOPE_CONSUMIDOR_FINAL_SIN_DOCUMENTO"] = 10000
        try:
            _sin = ns["facturar_venta"](v10)
            _con = ns["facturar_venta"](v10, "Consumidor final", "30.123.456")
        finally:
            g["TOPE_CONSUMIDOR_FINAL_SIN_DOCUMENTO"] = _tope
        esperar("pasado el tope, el consumidor final va con DNI",
                (_sin[0], "DNI" in _sin[1], _con[0],
                 uno("SELECT doc_tipo FROM facturas WHERE venta_id = ? AND estado = 'autorizada'",
                     v10)), (False, True, True, 96))
        v11, _ = ns["cerrar_venta"]([item()], a_la_caja=True)
        ns["cobrar_venta"](v11, "Efectivo")
        ns["devolver_de_una_venta"](uno("SELECT id FROM ventas_items WHERE venta_id = ?", v11), 1,
                                    "no_le_iba")
        esperar("devuelta entera: no queda nada para facturar",
                ns["facturar_venta"](v11), (False, "De esa venta se devolvió todo: no queda nada "
                                                   "para facturar."))
        _mes = ns["hoy_aca"]().isoformat()[:7]
        _filas = ns["comprobantes_para_el_contador"](_mes, "homologacion")
        esperar("para el contador: las notas en negativo, el total al final, y la planilla sale",
                (ns["meses_con_comprobantes"]("homologacion"), _filas[-1]["Comprobante"],
                 any(f["Total"] < 0 for f in _filas[:-1]),
                 round(sum(f["Total"] for f in _filas[:-1]), 2) == _filas[-1]["Total"],
                 ns["to_excel_bytes"](_filas)[:2]), ([_mes], "TOTAL DEL MES", True, True, b"PK"))
        esperar("lo que conviene completar para el PDF: lo que no está en los secretos",
                [x.split(" ")[0] for x in ns["lo_que_conviene_completar"]()],
                ["ingresos_brutos", "inicio_de_actividades"])
        _pdf_nc = ns["factura_para_descargar"](uno("SELECT id FROM facturas WHERE asociada_a = ?",
                                                    f9["id"]))
        esperar("el PDF de una nota de crédito también sale", _pdf_nc[:4], b"%PDF")

        # 5. El QR y el PDF.
        _fa = dict(c.execute("SELECT * FROM facturas WHERE venta_id = ?", (v2,)).fetchone())
        _qr = ns["url_del_qr"](_fa, "20111111112")
        _datos = json.loads(base64.b64decode(_qr.split("?p=")[1]))
        esperar("el QR de ARCA",
                (_qr.startswith("https://www.afip.gob.ar/fe/qr/?p="), _datos["tipoCmp"],
                 _datos["nroDocRec"], _datos["importe"], _datos["tipoCodAut"]),
                (True, 1, 30712345671, 24200.0, "E"))
        _pdf = ns["factura_para_descargar"](_fa["id"])
        esperar("el PDF sale", (_pdf[:4], len(_pdf) > 2000), (b"%PDF", True))
        esperar("los del día", len(ns["facturas_del_dia"]()) >= 5, True)
        # 6. Lo que se prueba desde Administrar, sin facturar nada.
        esperar("probar la conexión: los tres pasos en verde",
                [ok for _, ok, _ in ns["probar_la_conexion_con_arca"]()], [True, True, True])

        # 7. En la pantalla: la caja le hace la factura a la venta recién cobrada, y Administrar
        # dice que está lista y prueba la conexión.
        from streamlit.testing.v1 import AppTest
        v5, _ = ns["cerrar_venta"]([item()], a_la_caja=True)
        ns["cobrar_venta"](v5, "Efectivo")
        at = AppTest.from_file(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "app.py"), default_timeout=300)
        at.secrets["admin_passwords"] = {"duenio": "clave-duenio-1"}
        at.run()
        at.text_input(key="login_inicial_clave").set_value("clave-duenio-1")
        [b for b in at.button if "Ingresar con contraseña" in b.label][0].click().run()
        at.session_state["caja_recien"] = v5
        at.session_state["pagina_actual"] = ns["PAGINAS"][11]
        at.run()
        [b for b in at.button if b.key == "caja_recien_facturar"][0].click().run()
        esperar("desde el comprobante de la caja: hecha, a la vista y con su PDF",
                (uno("SELECT estado FROM facturas WHERE venta_id = ?", v5),
                 any("Factura B" in x.value and "CAE" in x.value for x in at.success),
                 [e.value for e in at.exception]), ("autorizada", True, []))
        at.session_state["pagina_actual"] = ns["PAGINAS"][3]
        at.session_state["sub_admin"] = ns["SUB_ADMIN"][2]
        at.run()
        [b for b in at.button if b.key == "arca_probar"][0].click().run()
        esperar("Administrar: lista, y la conexión en verde",
                (any("···1112" in x.value for x in at.caption),
                 sum(x.value.startswith(("Los datos", "El permiso", "El último"))
                     for x in at.success)), (True, 3))
        esperar("Administrar: los comprobantes del mes para el contador, y lo que falta en el PDF",
                (at.selectbox(key="arca_mes_contador").value,
                 any("ingresos_brutos" in x.value for x in at.caption)), (_mes, True))
        # El cierre de la caja: cualquiera de las autorizadas del día se baja en PDF.
        at.session_state["pagina_actual"] = ns["PAGINAS"][11]
        at.session_state["exp_ventas_cierre_caja_hoy"] = True
        at.run()
        esperar("el cierre: el selector de los comprobantes para bajar, sin errores",
                ([len(x.options) >= 5 for x in at.selectbox if x.key == "factura_para_bajar"]
                 == [True],
                 [e.value for e in at.exception]), (True, []))
        # Una devolución de una venta facturada: la nota de crédito por lo devuelto, tildada de
        # entrada.
        v7, _ = ns["cerrar_venta"]([item(2)], a_la_caja=True)
        ns["cobrar_venta"](v7, "Efectivo")
        ns["facturar_venta"](v7)
        f7 = ns["factura_vigente_de"](v7)["id"]
        at.session_state["pagina_actual"] = ns["PAGINAS"][10]
        at.session_state["sub_devoluciones"] = ns["SUB_DEVOLUCIONES"][1]
        at.run()
        at.text_input(key="venta_buscar_dev").set_value(str(v7)).run()
        at.selectbox(key="venta_dev_sel").set_value(v7).run()
        esperar("la casilla de la nota de crédito, tildada",
                [x.value for x in at.checkbox if "nota de crédito" in x.label], [True])
        [b for b in at.button if "Devolver" in b.label and b.type == "primary"
         or getattr(b, "label", "") == "↩️ Devolver"][0].click().run()
        esperar("devuelto uno: la nota de crédito por ese, y la factura con la otra mitad",
                (uno("SELECT total FROM facturas WHERE asociada_a = ?", f7),
                 ns["factura_vigente_de"](v7)["queda"], [e.value for e in at.exception]),
                (12100.0, 12100.0, []))
        # Sin la caja aparte cobra el vendedor: la factura, si la pide, desde la venta recién
        # terminada.
        ns["guardar_config"]("caja_aparte", "0")
        at.session_state["pagina_actual"] = ns["PAGINAS"][9]
        at.session_state["venta_recien_cerrada"] = None
        at.session_state["venta_items"] = [item()]
        at.run()
        [b for b in at.button if b.key == "venta_terminar"][0].click().run()
        [b for b in at.button if b.key == "venta_confirmar_cierre"][0].click().run()
        v8 = uno("SELECT MAX(id) FROM ventas")
        [b for b in at.button if b.key == "venta_recien_facturar"][0].click().run()
        esperar("sin caja aparte: el vendedor la factura desde la venta terminada",
                (uno("SELECT cobrada FROM ventas WHERE id = ?", v8),
                 uno("SELECT estado FROM facturas WHERE venta_id = ?", v8),
                 [e.value for e in at.exception]), (1, "autorizada", []))
        ns["guardar_config"]("caja_aparte", "1")
    finally:
        g["_secretos_de_arca"], g["requests"] = _secretos_reales, _requests_reales
        for k in ("admin_nombre", "nivel_usuario"):
            st.session_state.pop(k, None)
    return fallas


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_facturas_")
    try:
        fallas = probar(_cargar_la_logica(carpeta))
        for f in fallas:
            print("   ✗", f)
        print("✅ facturas: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

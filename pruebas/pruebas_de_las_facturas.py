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


def _texto_del_pdf(pdf):
    """Lo escrito en un PDF de fpdf2 (sus tramos vienen comprimidos), para buscar adentro."""
    import zlib
    partes = []
    for tramo in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
        try:
            partes.append(zlib.decompress(tramo).decode("latin-1"))
        except zlib.error:
            continue
    return "\n".join(partes)


class _ArcaDePrueba:
    """Contesta como el WSAA y el WSFEv1. Anota lo que le pidieron."""

    def __init__(self, requests_de_verdad):
        self.RequestException = requests_de_verdad.RequestException
        self._ConnectionError = requests_de_verdad.ConnectionError
        self.ultimo = {}          # (pto, tipo) -> último número autorizado
        self.autorizadas = {}     # (pto, tipo, número) -> lo que ARCA guarda del comprobante
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
            asociado = re.search(r"<CbteAsoc><Tipo>(\d+)</Tipo><PtoVta>(\d+)</PtoVta><Nro>(\d+)"
                                 r"</Nro>", cuerpo)
            guardado = {"cae": cae, "total": float(valor("ImpTotal")),
                        "neto": float(valor("ImpNeto")), "iva": float(valor("ImpIVA")),
                        "doc_tipo": valor("DocTipo"), "doc_nro": valor("DocNro"),
                        "fecha": valor("CbteFch"), "condicion": valor("CondicionIVAReceptorId"),
                        "asociado": asociado.groups() if asociado else None}
            if self.cortar_el_proximo_cae:
                self.cortar_el_proximo_cae = False
                if self.autorizar_aunque_se_corte:
                    self.ultimo[(pto, tipo)] = numero
                    self.autorizadas[(pto, tipo, numero)] = guardado
                raise self._ConnectionError("se cortó")
            self.ultimo[(pto, tipo)] = numero
            self.autorizadas[(pto, tipo, numero)] = guardado
            return self._respuesta(f"<R><Resultado>A</Resultado><CAE>{cae}</CAE>"
                                   "<CAEFchVto>20261120</CAEFchVto></R>")
        if accion.endswith("FECompConsultar"):
            clave = (int(valor("PtoVta")), int(valor("CbteTipo")), int(valor("CbteNro")))
            if clave in self.autorizadas:
                a = self.autorizadas[clave]
                asociado = ("<CbtesAsoc><CbteAsoc><Tipo>%s</Tipo><PtoVta>%s</PtoVta><Nro>%s</Nro>"
                            "</CbteAsoc></CbtesAsoc>" % a["asociado"]) if a["asociado"] else ""
                return self._respuesta(
                    f"<R><ResultGet><DocTipo>{a['doc_tipo']}</DocTipo><DocNro>{a['doc_nro']}"
                    f"</DocNro><CbteFch>{a['fecha']}</CbteFch><ImpTotal>{a['total']:.2f}"
                    f"</ImpTotal><ImpNeto>{a['neto']:.2f}</ImpNeto><ImpIVA>{a['iva']:.2f}</ImpIVA>"
                    f"<CondicionIVAReceptorId>{a['condicion']}</CondicionIVAReceptorId>"
                    f"<CodAutorizacion>{a['cae']}</CodAutorizacion><FchVto>20261120</FchVto>"
                    f"{asociado}</ResultGet></R>")
            return self._respuesta("<R><Errors><Err><Code>602</Code><Msg>No existen datos</Msg>"
                                   "</Err></Errors></R>")
        raise AssertionError(f"acción desconocida: {accion}")

    @staticmethod
    def perder_en_la_app(c, conn, factura_id):
        """Como un reinicio justo después de que ARCA autorizó: el renglón se va de la app y
        ARCA lo sigue teniendo."""
        c.execute("DELETE FROM facturas WHERE id = ?", (factura_id,))
        conn.commit()

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
    esperar("el tipo: C del monotributista; A al inscripto y al monotributista (RG 5003), y B "
            "a los demás",
            [ns["tipo_de_factura"](n, k) for n, k in
             (("monotributo", "Responsable inscripto"), ("responsable_inscripto",
              "Responsable inscripto"), ("responsable_inscripto", "Consumidor final"),
              ("responsable_inscripto", "Monotributista"), ("responsable_inscripto", "Exento"))],
            [11, 1, 6, 1, 6])
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

    # 1b. El certificado sin OpenSSL: la clave y el pedido que ARCA pide subir, y el bloque para
    # los secretos. El pedido lleva el CUIT como lo quiere ARCA y está firmado con esa clave.
    from cryptography import x509 as _x509
    from cryptography.hazmat.primitives import serialization as _ser
    _clave_pem, _pedido_pem = ns["pedido_de_certificado"]("20-11111111-2", "El  Chavo SRL", "mi alias!")
    _pedido = _x509.load_pem_x509_csr(_pedido_pem.encode())
    _clave = _ser.load_pem_private_key(_clave_pem.encode(), password=None)
    esperar("el pedido de certificado: firmado con la clave, con el CUIT, el nombre y el alias",
            (_pedido.is_signature_valid, _pedido.subject.rfc4514_string(),
             _pedido.public_key().public_numbers() == _clave.public_key().public_numbers(),
             _clave.key_size),
            (True, "2.5.4.5=CUIT 20111111112,CN=mialias,O=El Chavo SRL,C=AR", True, 2048))
    _mal_cert = []
    for _args in (("20-11111111-3", "El Chavo", "a"), ("20-11111111-2", "", "a"),
                  ("20-11111111-2", "El Chavo", "¡!")):
        try:
            ns["pedido_de_certificado"](*_args)
            _mal_cert.append("pasó")
        except ValueError:
            _mal_cert.append("no")
    esperar("sin un CUIT que cierre, sin nombre o sin alias, no se hace", _mal_cert, ["no"] * 3)
    _bloque = ns["secretos_de_arca_para_pegar"]("20-11111111-2", 'El "Chavo"', "monotributo",
                                                _clave_pem)
    import tomllib
    _leido = tomllib.loads(_bloque)["arca"]
    esperar("el bloque de los secretos se lee como TOML, con la clave entera",
            (_leido["cuit"], _leido["condicion"], _leido["ambiente"], _leido["razon_social"],
             _leido["clave_privada"].strip() == _clave_pem.strip()),
            ("20111111112", "monotributo", "homologacion", "El Chavo", True))

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

        # 4d. Lo que no se puede perder en un reinicio. La copia se pide al instante; una
        # pendiente que ARCA no tiene no traba la factura que sigue; y lo que ARCA tiene y la app
        # perdió se trae solo —y si es por el mismo importe que lo que se está por facturar, se
        # frena para enlazarla en vez de hacer dos por la misma venta—.
        import threading
        _pedida = ns["del_proceso"]("copia_pedida_ya", threading.Event)
        esperar("después de facturar, la copia quedó pedida", _pedida.is_set(), True)
        _gc = ns["_esperar_o_retirarse"].__globals__
        _otra_version = _gc["llego_otra_version_de_la_logica"]
        _gc["llego_otra_version_de_la_logica"] = lambda: False
        try:
            import time as _time
            _t0 = _time.time()
            _se_va = ns["_esperar_o_retirarse"](60, despertar=_pedida)
        finally:
            _gc["llego_otra_version_de_la_logica"] = _otra_version
        esperar("el vigía de la copia se despierta enseguida, y el pedido queda atendido",
                (_se_va, _pedida.is_set(), _time.time() - _t0 < 5), (False, False, True))
        v13, _ = ns["cerrar_venta"]([item()], a_la_caja=True)
        ns["cobrar_venta"](v13, "Efectivo")
        arca.cortar_el_proximo_cae, arca.autorizar_aunque_se_corte = True, False
        ns["facturar_venta"](v13)
        f13 = dict(c.execute("SELECT * FROM facturas WHERE venta_id = ? ORDER BY id DESC",
                             (v13,)).fetchone())
        v14, _ = ns["cerrar_venta"]([item()], a_la_caja=True)
        ns["cobrar_venta"](v14, "Efectivo")
        ok14, _ = ns["facturar_venta"](v14)
        esperar("con una pendiente que ARCA no tiene, la que sigue se hace igual: con su número",
                (f13["estado"], ok14, uno("SELECT estado FROM facturas WHERE id = ?", f13["id"]),
                 uno("SELECT numero FROM facturas WHERE venta_id = ? AND estado = 'autorizada'",
                     v14)), ("pendiente", True, "rechazada", f13["numero"]))
        # Un reinicio se lleva una factura (y su venta) de otro importe: se trae sola al facturar
        # la que sigue, sin la venta, y no frena.
        v15, _ = ns["cerrar_venta"]([item(4)], a_la_caja=True)
        ns["cobrar_venta"](v15, "Efectivo")
        ns["facturar_venta"](v15, "Consumidor final", "30.123.456")
        f15 = dict(c.execute("SELECT * FROM facturas WHERE venta_id = ?", (v15,)).fetchone())
        arca.perder_en_la_app(c, conn, f15["id"])
        v16, _ = ns["cerrar_venta"]([item()], a_la_caja=True)
        ns["cobrar_venta"](v16, "Efectivo")
        ok16, _ = ns["facturar_venta"](v16)
        _traida = dict(c.execute("SELECT * FROM facturas WHERE tipo = 6 AND numero = ?",
                                 (f15["numero"],)).fetchone())
        esperar("la que la app perdió se trae de ARCA: sus importes, su CAE, sin venta",
                (ok16, _traida["venta_id"], _traida["total"], _traida["neto"], _traida["iva"],
                 _traida["cae"], _traida["doc_tipo"], _traida["doc_nro"], _traida["usuario"],
                 _traida["fecha"], _traida["estado"]),
                (True, None, f15["total"], f15["neto"], f15["iva"], f15["cae"], 96, 30123456,
                 "ARCA", f15["fecha"], "autorizada"))
        esperar("y sale en la planilla del contador",
                any(x.get("Número") == f15["numero"] and x["Código"] == 6
                    for x in ns["comprobantes_para_el_contador"](
                        ns["hoy_aca"]().isoformat()[:7], "homologacion")), True)
        # Del mismo importe que la venta que se factura: puede ser esa misma. Se frena, se
        # enlaza, y no quedan dos facturas por una venta.
        v17, _ = ns["cerrar_venta"]([item()], a_la_caja=True)
        ns["cobrar_venta"](v17, "Efectivo")
        ns["facturar_venta"](v17)
        f17 = dict(c.execute("SELECT * FROM facturas WHERE venta_id = ?", (v17,)).fetchone())
        arca.perder_en_la_app(c, conn, f17["id"])
        _antes = arca.ultimo[(3, 6)]
        ok17, texto17 = ns["facturar_venta"](v17)
        _suelta = ns["facturas_sin_venta"](12100.0)
        esperar("del mismo importe: no hace otra, la trae y avisa",
                (ok17, "Es la de esta venta" in texto17, arca.ultimo[(3, 6)] == _antes,
                 [x["numero"] for x in _suelta]), (False, True, True, [f17["numero"]]))
        esperar("no se enlaza con una venta de otro importe",
                ns["enlazar_factura_con_venta"](_suelta[0]["id"], v15)[0], False)
        ok_e, _ = ns["enlazar_factura_con_venta"](_suelta[0]["id"], v17)
        _vig17 = ns["factura_vigente_de"](v17)
        esperar("enlazada: es la factura de la venta, con sus renglones, y no se factura otra vez",
                (ok_e, _vig17["numero"], json.loads(_vig17["detalle"])["renglones"],
                 ns["facturar_venta"](v17)[0], ns["facturas_sin_venta"](12100.0)),
                (True, f17["numero"], [[1, "PRUEBA F1 - FILTRO ACEITE", 12100.0]], False, []))
        # Con la copia frenada no se hacen facturas de verdad (de prueba sí).
        v18, _ = ns["cerrar_venta"]([item()], a_la_caja=True)
        ns["cobrar_venta"](v18, "Efectivo")
        ns["guardar_config"]("copia_frenada_sin_cifrar", "2026-10-12 15:56:50")
        secretos["ambiente"] = "produccion"
        _pedidos = len(arca.pedidos)
        try:
            _frenada = ns["facturar_venta"](v18)
        finally:
            secretos["ambiente"] = "homologacion"
        _pedidos_frenada = len(arca.pedidos) - _pedidos
        _de_prueba = ns["facturar_venta"](v18)
        ns["guardar_config"]("copia_frenada_sin_cifrar", "")
        esperar("con la copia frenada: de verdad no (y ni se le habla a ARCA), de prueba sí",
                (_frenada[0], "copia de seguridad" in _frenada[1], _pedidos_frenada,
                 _de_prueba[0]), (False, True, 0, True))

        # 4e. Lo que se sabe del cliente: la venta de un taller viene con su CUIT (el de su
        # cuenta corriente, o el de la primera factura que se le hizo), con la condición y el
        # nombre de la última; y a un documento ya facturado se le recuerda el nombre.
        st.session_state["nivel_usuario"] = "admin"
        ns["crear_mecanico"]("Taller Sur", "clave-sur-1")
        st.session_state["nivel_usuario"] = "operador"
        _taller = uno("SELECT id FROM mecanicos WHERE nombre = 'Taller Sur'")
        v20, _ = ns["cerrar_venta"]([item()], mecanico_id=_taller, a_la_caja=True)
        ns["cobrar_venta"](v20, "Efectivo")
        esperar("un taller sin CUIT cargado: consumidor final, sin nada",
                ns["cliente_sugerido_para_la_factura"](v20), ("Consumidor final", "", ""))
        ns["facturar_venta"](v20, "Monotributista", "30-71234567-1", "Taller Sur SRL")
        v21, _ = ns["cerrar_venta"]([item()], mecanico_id=_taller, a_la_caja=True)
        ns["cobrar_venta"](v21, "Efectivo")
        esperar("facturado una vez: su CUIT queda en la cuenta, y la próxima viene con todo",
                (ns["obtener_config"](f"cuit_taller_{_taller}", ""),
                 ns["cliente_sugerido_para_la_factura"](v21)),
                ("30712345671", ("Monotributista", "30-71234567-1", "Taller Sur SRL")))
        ns["facturar_venta"](v21, "Monotributista", "30-71234567-1", "")
        esperar("sin nombre y con un documento conocido: el de la última vez",
                uno("SELECT nombre_receptor FROM facturas WHERE venta_id = ?", v21),
                "Taller Sur SRL")

        # 5. El QR y el PDF.
        _fa = dict(c.execute("SELECT * FROM facturas WHERE venta_id = ?", (v2,)).fetchone())
        _qr = ns["url_del_qr"](_fa, "20111111112")
        _datos = json.loads(base64.b64decode(_qr.split("?p=")[1]))
        esperar("el QR de ARCA",
                (_qr.startswith("https://www.afip.gob.ar/fe/qr/?p="), _datos["tipoCmp"],
                 _datos["nroDocRec"], _datos["importe"], _datos["tipoCodAut"]),
                (True, 1, 30712345671, 24200.0, "E"))
        _pdf = ns["factura_para_descargar"](_fa["id"])
        _escrito = _texto_del_pdf(_pdf)
        esperar("el PDF sale, con el código, el número, el CUIT con guiones y la condición de venta",
                (_pdf[:4], [x in _escrito for x in ("COD. 001", "Comp. Nro", "30-71234567-1",
                                                     "Transferencia bancaria", "s/IVA")]),
                (b"%PDF", [True] * 5))
        # A un monotributista, la A con la leyenda de la RG 5003.
        v12, _ = ns["cerrar_venta"]([item()], a_la_caja=True)
        ns["cobrar_venta"](v12, "Efectivo")
        ok12, _ = ns["facturar_venta"](v12, "Monotributista", "20-11111111-2", "Taller Mono")
        f12 = dict(c.execute("SELECT * FROM facturas WHERE venta_id = ?", (v12,)).fetchone())
        esperar("al monotributista: la A, con la leyenda en el PDF (y en la B no va)",
                (ok12, f12["tipo"], "27.618" in _texto_del_pdf(ns["factura_para_descargar"](f12["id"])),
                 "27.618" in _texto_del_pdf(ns["factura_para_descargar"](f1["id"]))),
                (True, 1, True, False))
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
        # Sin configurar, Administrar arma el pedido de certificado: la clave se muestra para
        # copiarla y no queda guardada en la base.
        g["_secretos_de_arca"] = lambda: {}
        try:
            at.session_state["exp_certificado_de_arca"] = True
            at.run()
            at.text_input(key="arca_cert_cuit").set_value("20-11111111-2")
            at.text_input(key="arca_cert_razon").set_value("El Chavo SRL")
            at.run()
            [b for b in at.button if b.key == "arca_cert_generar"][0].click().run()
            _codigos = [x.value for x in at.code]
            esperar("Administrar: el pedido para bajar y el bloque con la clave para copiar",
                    (any("BEGIN PRIVATE KEY" in x and 'cuit = "20111111112"' in x for x in _codigos),
                     len(at.get("download_button")) >= 1,
                     uno("SELECT COUNT(*) FROM configuracion WHERE valor LIKE '%PRIVATE KEY%'"),
                     [e.value for e in at.exception]), (True, True, 0, []))
            [b for b in at.button if b.key == "arca_cert_limpiar"][0].click().run()
            esperar("y se saca de la pantalla", [x.value for x in at.code
                                                 if "PRIVATE KEY" in x.value], [])
        finally:
            g["_secretos_de_arca"] = lambda: dict(secretos)
        at.session_state["exp_certificado_de_arca"] = False
        # El cierre de la caja: cualquiera de las autorizadas del día se baja en PDF.
        at.session_state["pagina_actual"] = ns["PAGINAS"][11]
        at.session_state["exp_ventas_cierre_caja_hoy"] = True
        at.run()
        _con_factura = [list(d.value["Factura"]) for d in at.dataframe
                        if "Factura" in getattr(d.value, "columns", [])]
        esperar("el cierre: el selector de los comprobantes para bajar, y cada venta con su "
                "factura a la vista, sin errores",
                ([len(x.options) >= 5 for x in at.selectbox if x.key == "factura_para_bajar"]
                 == [True], len(_con_factura),
                 any(str(x).startswith(("B 00003-", "A 00003-")) for x in (_con_factura or [[]])[0]),
                 [e.value for e in at.exception]), (True, 1, True, []))
        # Lo tipeado para una venta que no se facturó no sigue puesto en la siguiente; y la de
        # un taller con CUIT viene con sus datos.
        v22, _ = ns["cerrar_venta"]([item(7)], a_la_caja=True)
        ns["cobrar_venta"](v22, "Efectivo")
        v23, _ = ns["cerrar_venta"]([item(7)], mecanico_id=_taller, a_la_caja=True)
        ns["cobrar_venta"](v23, "Efectivo")
        at.session_state["caja_recien"] = v22
        at.run()
        at.text_input(key=f"caja_recien_v{v22}_documento_factura").set_value("30123456").run()
        at.session_state["caja_recien"] = v23
        at.run()
        esperar("otra venta, sus propios campos: los del taller, no lo tipeado para la anterior",
                ([x.value for x in at.text_input if (x.key or "").endswith("_documento_factura")],
                 [x.value for x in at.selectbox if (x.key or "").endswith("_condicion_factura")],
                 [e.value for e in at.exception]),
                (["30-71234567-1"], ["Monotributista"], []))
        # Una factura que la app perdió, del mismo importe que una venta sin factura: el
        # comprobante de la caja ofrece enlazarla en vez de hacer otra.
        v19, _ = ns["cerrar_venta"]([item()], a_la_caja=True)
        ns["cobrar_venta"](v19, "Efectivo")
        ns["facturar_venta"](v19)
        f19 = dict(c.execute("SELECT * FROM facturas WHERE venta_id = ?", (v19,)).fetchone())
        arca.perder_en_la_app(c, conn, f19["id"])
        ns["facturar_venta"](v19)                      # la trae, y frena
        at.session_state["caja_recien"] = v19
        at.run()
        _avisa = any("la app había perdido" in x.value for x in at.warning)
        [b for b in at.button if (b.key or "").startswith("caja_recien_enlazar_")][0].click().run()
        esperar("la caja ofrece enlazar la factura traída de ARCA, y queda como la de la venta",
                (_avisa, (ns["factura_vigente_de"](v19) or {}).get("numero"),
                 [e.value for e in at.exception]), (True, f19["numero"], []))
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

"""La factura electrónica de ARCA (la ex AFIP), a pedido de la caja.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

import base64
import html as _html
import xml.etree.ElementTree as _ET
from datetime import timezone as _tz


# ============================================================================================
# LA FACTURA ELECTRÓNICA (ARCA)
# ============================================================================================
# Lo pidió el dueño: «vamos a hacer lo de ARCA pero sin que sea en todas las ventas
# automáticamente, que sean en las que la chica encargada de la caja quiera hacerlas». Así que
# nada se factura solo: al cobrar hay un «🧾 Con factura» que arranca apagado, y una venta ya
# cobrada se puede facturar después (desde el comprobante o el cierre de caja).
#
# Cómo se habla con ARCA —los dos servicios de siempre de la factura electrónica—:
#   - WSAA: con el certificado del negocio se firma un pedido de acceso («TRA») y ARCA devuelve
#     un permiso («TA», token y firma) que vale 12 horas. Mientras uno esté vigente ARCA no da
#     otro: se guarda en la base (si la app se reinicia y lo pierde, no se puede facturar hasta
#     que venza). Ver _ticket_de_acceso().
#   - WSFEv1: con ese permiso se pregunta el último número autorizado de ese punto de venta y
#     tipo, y se pide el CAE para el siguiente. Ver facturar_venta().
# El renglón de la factura se anota «pendiente» ANTES de pedir el CAE: si se corta en el medio
# (la red, la app que se reinicia), no se sabe si ARCA la autorizó, y pedirla de nuevo con otro
# número podía dejar dos facturas por la misma venta. Una pendiente se resuelve preguntándole a
# ARCA por ese número (consultar_factura_pendiente()), nunca pidiéndola otra vez.
#
# Lo que hace falta, en los secretos de Streamlit (Settings → Secrets), nunca en el repositorio:
#     [arca]
#     cuit = "20123456789"
#     punto_de_venta = 3                # el habilitado para web services
#     condicion = "monotributo"         # o "responsable_inscripto"
#     ambiente = "homologacion"         # de prueba; «produccion» cuando ande
#     certificado = """-----BEGIN CERTIFICATE----- …"""
#     clave_privada = """-----BEGIN PRIVATE KEY----- …"""
#     razon_social = "…"; domicilio = "…"; inicio_de_actividades = "01/01/2020";
#     ingresos_brutos = "…"             # para el PDF de la factura
AMBIENTES_DE_ARCA = {
    "homologacion": {"wsaa": "https://wsaahomo.afip.gov.ar/ws/services/LoginCms",
                     "wsfe": "https://wswhomo.afip.gov.ar/wsfev1/service.asmx"},
    "produccion": {"wsaa": "https://wsaa.afip.gov.ar/ws/services/LoginCms",
                   "wsfe": "https://servicios1.afip.gov.ar/wsfev1/service.asmx"},
}
CONDICIONES_DEL_NEGOCIO = ("monotributo", "responsable_inscripto")
# El tipo de comprobante de ARCA: (qué es, letra).
TIPOS_DE_COMPROBANTE = {1: ("Factura", "A"), 6: ("Factura", "B"), 11: ("Factura", "C"),
                        3: ("Nota de crédito", "A"), 8: ("Nota de crédito", "B"),
                        13: ("Nota de crédito", "C")}
NOTA_DE_CREDITO_DE = {1: 3, 6: 8, 11: 13}
# Quién compra (RG 5616: la condición frente al IVA del que recibe la factura va siempre).
CONDICIONES_DEL_CLIENTE = {"Consumidor final": 5, "Responsable inscripto": 1,
                           "Monotributista": 6, "Exento": 4}
DOC_CUIT, DOC_DNI, DOC_SIN_IDENTIFICAR = 80, 96, 99
# Desde este total, ARCA rechaza la factura a un consumidor final sin DNI ni CUIT (RG 5700/2025:
# antes eran $191.624). Si ARCA lo cambia, se cambia acá.
TOPE_CONSUMIDOR_FINAL_SIN_DOCUMENTO = 10_000_000
# La condición de venta del comprobante, según cómo se cobró (ver condicion_de_venta()).
CONDICION_DE_VENTA_DE = {"Efectivo": "Contado", "Tarjeta de débito": "Tarjeta de débito",
                         "Tarjeta de crédito": "Tarjeta de crédito",
                         "Transferencia": "Transferencia bancaria",
                         "A cuenta": "Cuenta corriente"}
IVA_GENERAL = 21.0
ID_DEL_IVA_GENERAL = 5          # el código de ARCA de la alícuota del 21%
SEGUNDOS_PARA_ARCA = 30
_NS_WSFE = "http://ar.gov.afip.dif.FEV1/"
_NS_WSAA = "http://wsaa.view.sua.dvadac.desein.afip.gov"


class ErrorDeArca(Exception):
    """Lo que dijo ARCA (o que no se pudo hablar con ARCA), dicho para la pantalla: sin
    direcciones ni claves (ver tapar_lo_sensible())."""


def configuracion_de_arca():
    """Lo de [arca] en los secretos, revisado, o None si falta algo para facturar (ver
    lo_que_falta_para_facturar())."""
    if lo_que_falta_para_facturar():
        return None
    datos = _secretos_de_arca()
    return {"cuit": re.sub(r"\D", "", str(datos["cuit"])),
            "punto_de_venta": int(datos["punto_de_venta"]),
            "condicion": str(datos["condicion"]).strip().lower(),
            "ambiente": str(datos.get("ambiente") or "homologacion").strip().lower(),
            "certificado": str(datos["certificado"]).strip(),
            "clave_privada": str(datos["clave_privada"]).strip(),
            "razon_social": str(datos.get("razon_social") or "").strip(),
            "domicilio": str(datos.get("domicilio") or "").strip(),
            "inicio_de_actividades": str(datos.get("inicio_de_actividades") or "").strip(),
            "ingresos_brutos": str(datos.get("ingresos_brutos") or "").strip()}


def _secretos_de_arca():
    try:
        return dict(st.secrets.get("arca", {}) or {})
    except Exception as _err:          # sin archivo de secretos, Streamlit levanta su error
        anotar_error("_secretos_de_arca", _err)
        return {}


def lo_que_falta_para_facturar():
    """Qué falta en los secretos para poder facturar, en castellano. [] si está todo."""
    datos = _secretos_de_arca()
    falta = []
    if not cuit_valido(datos.get("cuit")):
        falta.append("el CUIT del negocio (11 números, con el último que cierre)")
    try:
        if int(datos.get("punto_de_venta") or 0) <= 0:
            raise ValueError
    except (TypeError, ValueError):
        falta.append("el punto de venta habilitado para web services")
    if str(datos.get("condicion") or "").strip().lower() not in CONDICIONES_DEL_NEGOCIO:
        falta.append("la condición frente al IVA («monotributo» o «responsable_inscripto»)")
    if str(datos.get("ambiente") or "homologacion").strip().lower() not in AMBIENTES_DE_ARCA:
        falta.append("el ambiente («homologacion» o «produccion»)")
    if "BEGIN CERTIFICATE" not in str(datos.get("certificado") or ""):
        falta.append("el certificado de ARCA")
    if "PRIVATE KEY" not in str(datos.get("clave_privada") or ""):
        falta.append("la clave privada del certificado")
    return falta


def tipo_de_factura(condicion_del_negocio, condicion_del_cliente):
    """El tipo de comprobante: el monotributista hace C; el responsable inscripto, A a otro
    responsable inscripto y B a los demás."""
    if condicion_del_negocio == "monotributo":
        return 11
    return 1 if condicion_del_cliente == "Responsable inscripto" else 6


def importes_de_la_factura(total, tipo):
    """{total, neto, iva}. En la C no se discrimina el IVA; en la A y la B el total lo trae
    adentro (los precios de la app son finales) y se separa al 21%."""
    total = round(float(total), 2)
    if tipo in (11, 13):
        return {"total": total, "neto": total, "iva": 0.0}
    neto = round(total / (1 + IVA_GENERAL / 100), 2)
    return {"total": total, "neto": neto, "iva": round(total - neto, 2)}


def documento_legible(doc_tipo, doc_nro):
    """«CUIT 30-71234567-1», «DNI 30.123.456» o "" (consumidor final sin identificar)."""
    if doc_tipo == DOC_CUIT:
        n = f"{int(doc_nro):011d}"
        return f"CUIT {n[:2]}-{n[2:10]}-{n[10]}"
    if doc_tipo == DOC_DNI:
        return f"DNI {miles(int(doc_nro), 0)}"
    return ""


def cliente_de_la_factura(condicion="Consumidor final", documento=""):
    """El que recibe la factura, revisado: (cliente, None) o (None, qué está mal). Un
    consumidor final puede ir sin documento; con 7 u 8 números es un DNI y con 11, un CUIT. Los
    demás, siempre con CUIT."""
    if condicion not in CONDICIONES_DEL_CLIENTE:
        return None, "Elegí la condición del cliente frente al IVA."
    numero = re.sub(r"\D", "", str(documento or ""))
    if not numero:
        if condicion != "Consumidor final":
            return None, f"Para un {condicion.lower()} hace falta el CUIT."
        return {"condicion": condicion, "doc_tipo": DOC_SIN_IDENTIFICAR, "doc_nro": 0}, None
    if len(numero) == 11:
        # Con el dígito verificador (cuit_valido(), en logica/salud.py): un número mal tipeado
        # lo rechazaba ARCA con un error que la cajera no entendía; así sabe cuál revisar.
        if not cuit_valido(numero):
            return None, (f"El CUIT {numero[:2]}-{numero[2:10]}-{numero[10]} no cierra: el "
                          "último número no corresponde a los otros. Revisalo.")
        return {"condicion": condicion, "doc_tipo": DOC_CUIT, "doc_nro": int(numero)}, None
    if len(numero) in (7, 8) and condicion == "Consumidor final":
        return {"condicion": condicion, "doc_tipo": DOC_DNI, "doc_nro": int(numero)}, None
    return None, ("El documento no se entiende: un DNI tiene 7 u 8 números y un CUIT, 11."
                  if condicion == "Consumidor final" else "El CUIT tiene 11 números.")


def nombre_del_comprobante(tipo, punto_de_venta, numero):
    """«Factura B 00003-00000123»."""
    que, letra = TIPOS_DE_COMPROBANTE.get(int(tipo), ("Comprobante", "?"))
    return f"{que} {letra} {int(punto_de_venta):05d}-{int(numero):08d}"


# ---- WSAA: el permiso para facturar ---------------------------------------------------------
def _pedido_de_acceso(servicio="wsfe", ahora=None):
    """El TRA: quién pide, para qué servicio y por cuánto. En UTC, como todo lo que se guarda."""
    ahora = ahora or datetime.now(_tz.utc)
    return ('<?xml version="1.0" encoding="UTF-8"?><loginTicketRequest version="1.0"><header>'
            f"<uniqueId>{int(ahora.timestamp())}</uniqueId>"
            f"<generationTime>{(ahora - timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%S')}Z"
            f"</generationTime><expirationTime>"
            f"{(ahora + timedelta(minutes=10)).strftime('%Y-%m-%dT%H:%M:%S')}Z</expirationTime>"
            f"</header><service>{servicio}</service></loginTicketRequest>").encode("utf-8")


def _firmar_pedido(pedido, certificado_pem, clave_pem):
    """El TRA firmado con el certificado del negocio (CMS con el contenido adentro), en base64,
    como lo pide el WSAA."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.serialization import pkcs7
    try:
        certificado = x509.load_pem_x509_certificate(certificado_pem.encode("utf-8"))
        clave = serialization.load_pem_private_key(clave_pem.encode("utf-8"), password=None)
    except (ValueError, TypeError) as _err:
        raise ErrorDeArca("El certificado o la clave privada de ARCA no se pueden leer: "
                          "revisá cómo se pegaron en los secretos.") from _err
    firmado = (pkcs7.PKCS7SignatureBuilder().set_data(pedido)
               .add_signer(certificado, clave, hashes.SHA256())
               .sign(serialization.Encoding.DER, []))
    return base64.b64encode(firmado).decode("ascii")


def _hablar_con_arca(url, accion, cuerpo):
    """Un pedido SOAP. Devuelve el XML de la respuesta, o levanta ErrorDeArca con lo que dijo
    ARCA (o que no contestó), sin la dirección."""
    sobre = ('<?xml version="1.0" encoding="utf-8"?><soap:Envelope '
             'xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
             f"{cuerpo}</soap:Body></soap:Envelope>")
    try:
        respuesta = requests.post(url, data=sobre.encode("utf-8"), timeout=SEGUNDOS_PARA_ARCA,
                                  headers={"Content-Type": "text/xml; charset=utf-8",
                                           "SOAPAction": f'"{accion}"'})
    except requests.RequestException as _err:
        anotar_error("_hablar_con_arca", _err)
        raise ErrorDeArca("No se pudo hablar con ARCA (la conexión o ARCA que no contesta). "
                          "Probá de nuevo en un rato.") from _err
    try:
        raiz = _ET.fromstring(respuesta.content)
    except _ET.ParseError as _err:
        anotar_error("_hablar_con_arca", _err)
        raise ErrorDeArca(f"ARCA contestó algo que no se entiende (código "
                          f"{respuesta.status_code}).") from _err
    falla = _primero_de_arca(raiz, "faultstring")
    if falla is not None:
        raise ErrorDeArca(f"ARCA dijo: {tapar_lo_sensible((falla.text or '').strip())[:200]}")
    return raiz


def _primero_de_arca(raiz, nombre):
    """El primer elemento con ese nombre, sin importar el espacio de nombres."""
    for elemento in raiz.iter():
        if elemento.tag == nombre or elemento.tag.endswith("}" + nombre):
            return elemento
    return None


def _texto_de_arca(raiz, nombre, defecto=""):
    elemento = _primero_de_arca(raiz, nombre)
    return (elemento.text or "").strip() if elemento is not None and elemento.text else defecto


def _ticket_de_acceso(cfg):
    """{token, sign} vigentes: el guardado si le quedan más de diez minutos, o uno nuevo."""
    clave = f"arca_ta_{cfg['ambiente']}_{cfg['cuit']}"
    try:
        guardado = json.loads(obtener_config(clave, "") or "{}")
        if guardado and datetime.fromisoformat(guardado["vence"]) - datetime.now(_tz.utc) > \
                timedelta(minutes=10):
            return guardado
    except (ValueError, KeyError, TypeError):
        pass
    cms = _firmar_pedido(_pedido_de_acceso(), cfg["certificado"], cfg["clave_privada"])
    try:
        raiz = _hablar_con_arca(AMBIENTES_DE_ARCA[cfg["ambiente"]]["wsaa"], "",
                                f'<loginCms xmlns="{_NS_WSAA}"><in0>{cms}</in0></loginCms>')
    except ErrorDeArca as e:
        if "TA valido" in str(e) or "TA válido" in str(e):
            raise ErrorDeArca("ARCA dice que ya hay un permiso vigente que la app perdió (se "
                              "reinició): se puede volver a facturar cuando venza, en menos de "
                              "12 horas.") from e
        raise
    ticket = _ET.fromstring(_texto_de_arca(raiz, "loginCmsReturn").encode("utf-8"))
    nuevo = {"token": _texto_de_arca(ticket, "token"), "sign": _texto_de_arca(ticket, "sign"),
             "vence": datetime.fromisoformat(_texto_de_arca(ticket, "expirationTime")).astimezone(_tz.utc)
             .isoformat()}
    if not nuevo["token"] or not nuevo["sign"]:
        raise ErrorDeArca("ARCA no devolvió el permiso para facturar.")
    guardar_config(clave, json.dumps(nuevo))
    return nuevo


# ---- WSFEv1: el CAE -------------------------------------------------------------------------
def _autenticacion(cfg, ticket):
    return (f"<Auth><Token>{_html.escape(ticket['token'])}</Token>"
            f"<Sign>{_html.escape(ticket['sign'])}</Sign><Cuit>{cfg['cuit']}</Cuit></Auth>")


def _pedir_al_wsfe(cfg, metodo, adentro):
    ticket = _ticket_de_acceso(cfg)
    raiz = _hablar_con_arca(AMBIENTES_DE_ARCA[cfg["ambiente"]]["wsfe"], _NS_WSFE + metodo,
                            f'<{metodo} xmlns="{_NS_WSFE}">{_autenticacion(cfg, ticket)}'
                            f"{adentro}</{metodo}>")
    return raiz


def _errores_de(raiz):
    """Los errores y las observaciones de una respuesta del WSFE, en un texto."""
    partes = []
    for nombre in ("Err", "Obs"):
        for elemento in raiz.iter():
            if elemento.tag == nombre or elemento.tag.endswith("}" + nombre):
                partes.append(f"{_texto_de_arca(elemento, 'Code')}: {_texto_de_arca(elemento, 'Msg')}")
    return " · ".join(p for p in partes if p.strip(": "))


def ultimo_autorizado(cfg, tipo):
    """El último número autorizado por ARCA para ese punto de venta y tipo (0 si ninguno)."""
    raiz = _pedir_al_wsfe(cfg, "FECompUltimoAutorizado",
                          f"<PtoVta>{cfg['punto_de_venta']}</PtoVta><CbteTipo>{tipo}</CbteTipo>")
    numero = _texto_de_arca(raiz, "CbteNro")
    if not numero.isdigit():
        raise ErrorDeArca(f"ARCA no dijo el último número: {_errores_de(raiz) or 'sin detalle'}.")
    return int(numero)


def _detalle_del_pedido(cfg, f, asociada=None):
    """El FECAEDetRequest de un comprobante (f: el renglón de la tabla facturas)."""
    iva = (f"<Iva><AlicIva><Id>{ID_DEL_IVA_GENERAL}</Id><BaseImp>{f['neto']:.2f}</BaseImp>"
           f"<Importe>{f['iva']:.2f}</Importe></AlicIva></Iva>" if f["tipo"] not in (11, 13)
           else "")
    asociado = ""
    if asociada:
        asociado = (f"<CbtesAsoc><CbteAsoc><Tipo>{asociada['tipo']}</Tipo>"
                    f"<PtoVta>{asociada['punto_de_venta']}</PtoVta><Nro>{asociada['numero']}</Nro>"
                    f"<Cuit>{cfg['cuit']}</Cuit><CbteFch>{asociada['fecha'].replace('-', '')}"
                    "</CbteFch></CbteAsoc></CbtesAsoc>")
    return (f"<FeCAEReq><FeCabReq><CantReg>1</CantReg><PtoVta>{f['punto_de_venta']}</PtoVta>"
            f"<CbteTipo>{f['tipo']}</CbteTipo></FeCabReq><FeDetReq><FECAEDetRequest>"
            f"<Concepto>1</Concepto><DocTipo>{f['doc_tipo']}</DocTipo>"
            f"<DocNro>{f['doc_nro']}</DocNro><CbteDesde>{f['numero']}</CbteDesde>"
            f"<CbteHasta>{f['numero']}</CbteHasta><CbteFch>{f['fecha'].replace('-', '')}</CbteFch>"
            f"<ImpTotal>{f['total']:.2f}</ImpTotal><ImpTotConc>0.00</ImpTotConc>"
            f"<ImpNeto>{f['neto']:.2f}</ImpNeto><ImpOpEx>0.00</ImpOpEx>"
            f"<ImpTrib>0.00</ImpTrib><ImpIVA>{f['iva']:.2f}</ImpIVA>"
            f"<MonId>PES</MonId><MonCotiz>1</MonCotiz>"
            f"<CondicionIVAReceptorId>{f['condicion_receptor']}</CondicionIVAReceptorId>"
            f"{asociado}{iva}</FECAEDetRequest></FeDetReq></FeCAEReq>")


def _emitir(cfg, tipo, cliente, importes, venta_id, asociada=None, nombre_cliente="",
            detalle=None):
    """Pide el CAE de un comprobante y lo deja anotado, con lo que va a decir el PDF
    (`detalle`: los renglones y la condición de venta). (ok, texto, id del renglón)."""
    if importes["total"] <= 0:
        return False, "No se factura algo en cero.", None
    # Uno a la vez: el número sale de preguntarle a ARCA el último, y dos a la vez pedirían el
    # mismo (un candado propio y no db_lock: adentro se habla con ARCA, que tarda).
    with del_proceso("candado_de_arca", threading.Lock):
        try:
            numero = ultimo_autorizado(cfg, tipo) + 1
        except ErrorDeArca as e:
            return False, str(e), None
        fila = {"venta_id": venta_id, "tipo": tipo, "punto_de_venta": cfg["punto_de_venta"],
                "numero": numero, "fecha": hoy_aca().isoformat(), "doc_tipo": cliente["doc_tipo"],
                "doc_nro": cliente["doc_nro"],
                "condicion_receptor": CONDICIONES_DEL_CLIENTE[cliente["condicion"]],
                "nombre_receptor": (nombre_cliente or "").strip()[:80], **importes}
        with db_lock, transaccion():
            c.execute("""INSERT INTO facturas (venta_id, tipo, punto_de_venta, numero, fecha,
                                               doc_tipo, doc_nro, condicion_receptor,
                                               nombre_receptor, total, neto, iva, estado,
                                               detalle, ambiente, asociada_a, usuario)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendiente', ?, ?, ?, ?)""",
                      (venta_id, tipo, fila["punto_de_venta"], numero, fila["fecha"],
                       fila["doc_tipo"], fila["doc_nro"], fila["condicion_receptor"],
                       fila["nombre_receptor"], fila["total"], fila["neto"], fila["iva"],
                       json.dumps(detalle or {}, ensure_ascii=False), cfg["ambiente"],
                       asociada["id"] if asociada else None, obtener_usuario_actual()))
            factura_id = c.lastrowid
        try:
            raiz = _pedir_al_wsfe(cfg, "FECAESolicitar", _detalle_del_pedido(cfg, fila, asociada))
        except ErrorDeArca as e:
            return False, (f"{e} La {nombre_del_comprobante(tipo, fila['punto_de_venta'], numero)} "
                           "quedó pendiente: tocá «🔄 Consultar en ARCA» para saber si se hizo."), \
                factura_id
        return _anotar_la_respuesta(factura_id, raiz)


def _anotar_la_respuesta(factura_id, raiz):
    """Lo que contestó ARCA a un FECAESolicitar, en el renglón. (ok, texto, id)."""
    c.execute("SELECT tipo, punto_de_venta, numero FROM facturas WHERE id = ?", (factura_id,))
    f = c.fetchone()
    nombre = nombre_del_comprobante(f["tipo"], f["punto_de_venta"], f["numero"])
    resultado, cae = _texto_de_arca(raiz, "Resultado"), _texto_de_arca(raiz, "CAE")
    errores = _errores_de(raiz)
    with db_lock, transaccion():
        if resultado == "A" and cae:
            vence = _texto_de_arca(raiz, "CAEFchVto")
            c.execute("""UPDATE facturas SET estado = 'autorizada', cae = ?, cae_vence = ?,
                                observaciones = ? WHERE id = ?""",
                      (cae, f"{vence[:4]}-{vence[4:6]}-{vence[6:8]}" if len(vence) == 8 else vence,
                       errores, factura_id))
            anotar_cambio("hizo un comprobante de ARCA", "factura", factura_id, None,
                          {"comprobante": nombre, "cae": cae})
            return True, f"🧾 {nombre} autorizada: CAE {cae}.", factura_id
        c.execute("UPDATE facturas SET estado = 'rechazada', observaciones = ? WHERE id = ?",
                  (errores or "sin detalle", factura_id))
    return False, f"ARCA no autorizó la {nombre}: {errores or 'sin detalle'}.", factura_id


def lo_que_queda_de_la_factura(factura_id):
    """Lo que todavía no anuló ninguna nota de crédito (autorizada o pendiente): el total, si no
    tiene ninguna. Una devolución hace una nota parcial (ver nota_de_credito())."""
    c.execute("""SELECT f.total - COALESCE((SELECT SUM(n.total) FROM facturas n
                                            WHERE n.asociada_a = f.id
                                              AND n.estado IN ('autorizada', 'pendiente')), 0)
                 FROM facturas f WHERE f.id = ?""", (factura_id,))
    fila = c.fetchone()
    return round(float(fila[0]), 2) if fila and fila[0] is not None else 0.0


def factura_vigente_de(venta_id):
    """La factura autorizada (o pendiente) de una venta a la que le queda algo sin anular con
    notas de crédito: dict (con «queda») o None."""
    c.execute("""SELECT f.* FROM facturas f
                 WHERE f.venta_id = ? AND f.tipo IN (1, 6, 11)
                   AND f.estado IN ('autorizada', 'pendiente')
                 ORDER BY f.id DESC""", (venta_id,))
    for fila in c.fetchall():
        queda = lo_que_queda_de_la_factura(fila["id"])
        if queda > 0.005:
            return dict(fila, queda=queda)
    return None


def renglones_de_la_venta(venta_id):
    """[[cantidad, qué, precio final por unidad]] de lo que el cliente se quedó: sin lo que ya
    devolvió."""
    c.execute("""SELECT cantidad - COALESCE(devuelto, 0) AS cantidad, marca, codigo, descripcion,
                        COALESCE(precio, 0) AS precio
                 FROM ventas_items WHERE venta_id = ? ORDER BY id""", (venta_id,))
    return [[f["cantidad"], f"{f['marca'] or ''} {f['codigo'] or ''} - {f['descripcion'] or ''}"
             .strip(" -"), round(float(f["precio"]), 2)]
            for f in c.fetchall() if f["cantidad"] > 0]


def lo_que_se_puede_facturar(venta_id):
    """El total de la venta menos lo devuelto: una devolución antes de facturar no se factura
    (la factura de una venta de $30.000 a la que le devolvieron un filtro de $8.000 va por
    $22.000, no por lo que se cobró al principio)."""
    c.execute("""SELECT v.total - COALESCE((SELECT SUM(d.importe) FROM ventas_devoluciones d
                                            WHERE d.venta_id = v.id), 0)
                 FROM ventas v WHERE v.id = ?""", (venta_id,))
    fila = c.fetchone()
    return round(float(fila[0] or 0), 2) if fila else 0.0


def condicion_de_venta(venta_id):
    """«Contado», «Tarjeta de crédito (3 cuotas)», «Cuenta corriente»…: va en el comprobante."""
    c.execute("SELECT forma_de_pago, cuotas FROM ventas WHERE id = ?", (venta_id,))
    v = c.fetchone()
    if not v:
        return "Contado"
    forma = CONDICION_DE_VENTA_DE.get(v["forma_de_pago"] or "", "Contado")
    if v["forma_de_pago"] == "Tarjeta de crédito" and (v["cuotas"] or 1) > 1:
        forma += f" ({v['cuotas']} cuotas)"
    return forma


def facturar_venta(venta_id, condicion="Consumidor final", documento="", nombre=""):
    """«🧾 Con factura»: la factura electrónica de una venta cobrada, si la cajera la pide.
    (ok, texto)."""
    exigir_nivel("empleado", "hacer una factura")
    cfg = configuracion_de_arca()
    if not cfg:
        return False, "Falta configurar la factura electrónica: " + \
            ", ".join(lo_que_falta_para_facturar()) + "."
    cliente, problema = cliente_de_la_factura(condicion, documento)
    if problema:
        return False, problema
    c.execute("SELECT total, COALESCE(cobrada, 1) AS cobrada, COALESCE(anulada, 0) AS anulada "
              "FROM ventas WHERE id = ?", (venta_id,))
    venta = c.fetchone()
    if not venta:
        return False, "Esa venta no existe."
    if venta["anulada"]:
        return False, "Esa venta está anulada."
    if not venta["cobrada"]:
        return False, "Se factura al cobrarla: todavía espera en la caja."
    ya = factura_vigente_de(venta_id)
    if ya:
        nombre_ya = nombre_del_comprobante(ya["tipo"], ya["punto_de_venta"], ya["numero"])
        return False, (f"Ya tiene la {nombre_ya}"
                       + (" (pendiente: consultala en ARCA)." if ya["estado"] == "pendiente"
                          else "."))
    total = lo_que_se_puede_facturar(venta_id)
    if total <= 0.005:
        return False, "De esa venta se devolvió todo: no queda nada para facturar."
    if (cliente["doc_tipo"] == DOC_SIN_IDENTIFICAR
            and total >= TOPE_CONSUMIDOR_FINAL_SIN_DOCUMENTO):
        return False, (f"Desde {formato_precio(TOPE_CONSUMIDOR_FINAL_SIN_DOCUMENTO)} ARCA pide el "
                       "DNI o el CUIT del consumidor final: cargalo y volvé a tocar.")
    tipo = tipo_de_factura(cfg["condicion"], cliente["condicion"])
    detalle = {"renglones": renglones_de_la_venta(venta_id),
               "condicion_de_venta": condicion_de_venta(venta_id)}
    ok, texto, _id = _emitir(cfg, tipo, cliente, importes_de_la_factura(total, tipo),
                             venta_id, nombre_cliente=nombre, detalle=detalle)
    return ok, texto


def nota_de_credito(factura_id, importe=None, renglones=None):
    """La nota de crédito de una factura, al mismo cliente: por lo que le queda (anularla), o
    por `importe` (lo devuelto de una venta facturada, con sus `renglones` [[cantidad, qué,
    precio]]). (ok, texto)."""
    exigir_nivel("empleado", "hacer una nota de crédito")
    cfg = configuracion_de_arca()
    if not cfg:
        return False, "Falta configurar la factura electrónica."
    c.execute("SELECT * FROM facturas WHERE id = ?", (factura_id,))
    factura = c.fetchone()
    if not factura or factura["tipo"] not in NOTA_DE_CREDITO_DE:
        return False, "Esa factura no existe."
    factura = dict(factura)
    if factura["estado"] != "autorizada":
        return False, "Solo se anula una factura autorizada."
    if factura["ambiente"] != cfg["ambiente"]:
        return False, "Esa factura es de otro ambiente de ARCA (prueba o real)."
    queda = lo_que_queda_de_la_factura(factura_id)
    if queda <= 0.005:
        return False, "Esa factura ya está anulada entera con notas de crédito."
    importe = queda if importe is None else round(float(importe), 2)
    if not 0 < importe <= queda + 0.005:
        return False, (f"La nota de crédito va de más de cero a {formato_precio(queda)}: es lo "
                       "que le queda a la factura.")
    tipo = NOTA_DE_CREDITO_DE[factura["tipo"]]
    # Por lo que queda, los importes de la factura menos los de las notas que ya tiene (así el
    # neto y el IVA cierran justo); por una parte, separados de nuevo.
    importes = importes_de_la_factura(importe, tipo)
    if abs(importe - queda) < 0.005:
        c.execute("""SELECT COALESCE(SUM(neto), 0), COALESCE(SUM(iva), 0) FROM facturas
                     WHERE asociada_a = ? AND estado IN ('autorizada', 'pendiente')""",
                  (factura_id,))
        neto_ya, iva_ya = c.fetchone()
        importes = {"total": round(queda, 2), "neto": round(factura["neto"] - neto_ya, 2),
                    "iva": round(factura["iva"] - iva_ya, 2)}
    condicion = next((k for k, v in CONDICIONES_DEL_CLIENTE.items()
                      if v == factura["condicion_receptor"]), "Consumidor final")
    cliente = {"condicion": condicion, "doc_tipo": factura["doc_tipo"],
               "doc_nro": factura["doc_nro"]}
    # Lo que dice: lo devuelto; o, si anula la factura entera, lo mismo que ella; o una parte.
    nombre_f = nombre_del_comprobante(factura["tipo"], factura["punto_de_venta"], factura["numero"])
    if not renglones:
        entera = abs(importe - factura["total"]) < 0.005
        renglones = (detalle_del_comprobante(factura)["renglones"] if entera else
                     [[1, f"Anulación de lo que quedaba de la {nombre_f}"
                       if abs(importe - queda) < 0.005 else f"Anulación parcial de la {nombre_f}",
                       importe]])
    detalle = {"renglones": renglones,
               "condicion_de_venta": detalle_del_comprobante(factura)["condicion_de_venta"]}
    ok, texto, _id = _emitir(cfg, tipo, cliente, importes, factura["venta_id"],
                             asociada=factura, nombre_cliente=factura["nombre_receptor"],
                             detalle=detalle)
    return ok, texto


def consultar_factura_pendiente(factura_id):
    """Pregunta a ARCA por una pendiente: si la autorizó, queda autorizada con su CAE; si no la
    tiene, queda rechazada y se puede volver a pedir. (ok, texto)."""
    exigir_nivel("empleado", "consultar una factura")
    cfg = configuracion_de_arca()
    if not cfg:
        return False, "Falta configurar la factura electrónica."
    c.execute("SELECT * FROM facturas WHERE id = ? AND estado = 'pendiente'", (factura_id,))
    f = c.fetchone()
    if not f:
        return False, "Esa factura no está pendiente."
    nombre = nombre_del_comprobante(f["tipo"], f["punto_de_venta"], f["numero"])
    try:
        raiz = _pedir_al_wsfe(cfg, "FECompConsultar",
                              f"<FeCompConsReq><CbteTipo>{f['tipo']}</CbteTipo>"
                              f"<CbteNro>{f['numero']}</CbteNro><PtoVta>{f['punto_de_venta']}"
                              "</PtoVta></FeCompConsReq>")
    except ErrorDeArca as e:
        return False, str(e)
    cae = _texto_de_arca(raiz, "CodAutorizacion")
    total = _texto_de_arca(raiz, "ImpTotal")
    with db_lock, transaccion():
        if cae and total and abs(float(total) - f["total"]) < 0.01:
            vence = _texto_de_arca(raiz, "FchVto")
            c.execute("""UPDATE facturas SET estado = 'autorizada', cae = ?, cae_vence = ?
                         WHERE id = ?""",
                      (cae, f"{vence[:4]}-{vence[4:6]}-{vence[6:8]}" if len(vence) == 8 else vence,
                       factura_id))
            return True, f"🧾 ARCA sí la autorizó: {nombre}, CAE {cae}."
        if cae:
            return False, (f"ARCA tiene la {nombre} con otro importe ({total}): no se tocó. "
                           "Revisalo con el contador.")
        c.execute("UPDATE facturas SET estado = 'rechazada', observaciones = ? WHERE id = ?",
                  ("ARCA no la tiene: no llegó a hacerse", factura_id))
    return True, f"ARCA no tiene la {nombre}: no llegó a hacerse. Se puede volver a facturar."


def facturas_del_dia(dia=None):
    """Los comprobantes hechos en un día de acá (hoy, si no se dice), el último primero."""
    dia = dia or hoy_aca().isoformat()
    c.execute("SELECT * FROM facturas WHERE fecha = ? ORDER BY id DESC", (dia,))
    return [dict(f) for f in c.fetchall()]


def meses_con_comprobantes(ambiente):
    """["2026-11", "2026-10", …]: los meses con comprobantes autorizados, el último primero."""
    c.execute("""SELECT DISTINCT substr(fecha, 1, 7) FROM facturas
                 WHERE estado = 'autorizada' AND ambiente = ? ORDER BY 1 DESC""", (ambiente,))
    return [f[0] for f in c.fetchall()]


def comprobantes_para_el_contador(mes, ambiente):
    """Los comprobantes autorizados de un mes («2026-11»), uno por renglón como los pide el
    contador para el libro de IVA ventas: las notas de crédito en negativo, y el total al
    final. [dict]."""
    c.execute("""SELECT * FROM facturas WHERE estado = 'autorizada' AND ambiente = ?
                   AND substr(fecha, 1, 7) = ? ORDER BY tipo, punto_de_venta, numero""",
              (ambiente, mes))
    filas, suma = [], {"Neto": 0.0, "IVA": 0.0, "Total": 0.0}
    for f in c.fetchall():
        signo = -1 if f["tipo"] in (3, 8, 13) else 1
        que, letra = TIPOS_DE_COMPROBANTE[f["tipo"]]
        cond = next((k for k, v in CONDICIONES_DEL_CLIENTE.items()
                     if v == f["condicion_receptor"]), "")
        importes = {"Neto": signo * f["neto"], "IVA": signo * f["iva"], "Total": signo * f["total"]}
        for k, v in importes.items():
            suma[k] += v
        filas.append({"Fecha": f"{f['fecha'][8:10]}/{f['fecha'][5:7]}/{f['fecha'][:4]}",
                      "Comprobante": f"{que} {letra}", "Código": f["tipo"],
                      "Punto de venta": f["punto_de_venta"], "Número": f["numero"],
                      "Cliente": f["nombre_receptor"] or cond,
                      "Documento": documento_legible(f["doc_tipo"], f["doc_nro"]),
                      "Condición frente al IVA": cond,
                      **{k: round(v, 2) for k, v in importes.items()},
                      "CAE": f["cae"], "Venta": f["venta_id"] or ""})
    if filas:
        filas.append({"Fecha": "", "Comprobante": "TOTAL DEL MES",
                      **{k: round(v, 2) for k, v in suma.items()}})
    return filas


def url_del_qr(factura, cuit):
    """El QR de la factura (RG 4892): la dirección de ARCA con los datos del comprobante."""
    datos = {"ver": 1, "fecha": factura["fecha"], "cuit": int(cuit),
             "ptoVta": int(factura["punto_de_venta"]), "tipoCmp": int(factura["tipo"]),
             "nroCmp": int(factura["numero"]), "importe": round(float(factura["total"]), 2),
             "moneda": "PES", "ctz": 1, "tipoDocRec": int(factura["doc_tipo"]),
             "nroDocRec": int(factura["doc_nro"]), "tipoCodAut": "E",
             "codAut": int(factura["cae"])}
    texto = base64.b64encode(json.dumps(datos, separators=(",", ":")).encode()).decode()
    return f"https://www.afip.gob.ar/fe/qr/?p={texto}"


def detalle_del_comprobante(factura):
    """{renglones, condicion_de_venta} de un comprobante: lo guardado al hacerlo. Los de antes
    de guardarlo (no hubo ninguno en producción) se rearman de la venta."""
    try:
        detalle = json.loads(factura.get("detalle") or "{}")
    except ValueError:
        detalle = {}
    if not detalle.get("renglones") and factura.get("venta_id"):
        detalle["renglones"] = renglones_de_la_venta(factura["venta_id"])
    detalle.setdefault("renglones", [])
    if not detalle.get("condicion_de_venta"):
        detalle["condicion_de_venta"] = (condicion_de_venta(factura["venta_id"])
                                         if factura.get("venta_id") else "Contado")
    return detalle


def factura_para_descargar(factura_id):
    """El PDF de un comprobante, armado como los de ARCA: arriba el negocio a la izquierda, la
    letra en su recuadro al medio y el número a la derecha; el cliente con su condición y la
    condición de venta; lo vendido; los totales (en la A, el neto y el IVA; en la B, el IVA
    contenido de la Ley 27.743); y el CAE con el QR. bytes."""
    from fpdf import FPDF
    import qrcode
    cfg = configuracion_de_arca() or {}
    c.execute("SELECT * FROM facturas WHERE id = ?", (factura_id,))
    f = dict(c.fetchone())
    que, letra = TIPOS_DE_COMPROBANTE[f["tipo"]]
    detalle = detalle_del_comprobante(f)
    discrimina = f["tipo"] in (1, 3)        # en la A el detalle va sin IVA

    def latin(texto):
        return str(texto or "").encode("latin-1", "replace").decode("latin-1")

    def dia(iso):
        iso = str(iso or "")
        return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if len(iso) >= 10 else iso

    pdf = FPDF()
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()

    def cortar(texto, ancho):
        """Lo que entra en `ancho` mm, con «…» si no entra (la celda no corta sola)."""
        texto = latin(texto)
        if pdf.get_string_width(texto) <= ancho:
            return texto
        while texto and pdf.get_string_width(texto + "...") > ancho:
            texto = texto[:-1]
        return texto + "..."

    # EL ENCABEZADO: un recuadro partido al medio, con la letra arriba en el centro.
    x0, y0, ancho, alto = 10, 10, 190, 46
    pdf.rect(x0, y0, ancho, alto)
    pdf.line(105, y0 + 20, 105, y0 + alto)
    pdf.set_fill_color(255, 255, 255)
    pdf.rect(96, y0, 18, 20, style="DF")
    pdf.set_xy(96, y0 + 1)
    pdf.set_font("Helvetica", "B", 26)
    pdf.cell(18, 11, letra, align="C")
    pdf.set_xy(96, y0 + 13)
    pdf.set_font("Helvetica", "B", 7)
    pdf.cell(18, 4, f"COD. {f['tipo']:03d}", align="C")
    # A la izquierda, el negocio.
    pdf.set_xy(13, y0 + 5)
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(80, 8, cortar(cfg.get("razon_social") or "El Chavo", 80))
    pdf.set_font("Helvetica", "", 9)
    condicion = ("Responsable Monotributo" if cfg.get("condicion") == "monotributo"
                 else "IVA Responsable Inscripto")
    y = y0 + 24
    for rotulo, valor in (("Domicilio comercial", cfg.get("domicilio")),
                          ("Condición frente al IVA", condicion)):
        if valor:
            pdf.set_xy(13, y)
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(pdf.get_string_width(latin(rotulo + ": ")) + 1, 5, latin(rotulo + ": "))
            pdf.set_font("Helvetica", "", 9)
            pdf.multi_cell(88 - pdf.get_string_width(latin(rotulo + ": ")), 5, latin(valor))
            y = pdf.get_y() + 1
    # A la derecha, el comprobante.
    pdf.set_xy(117, y0 + 4)
    pdf.set_font("Helvetica", "B", 17)
    pdf.cell(80, 9, latin(que.upper()))
    cuit = re.sub(r"\D", "", str(cfg.get("cuit") or ""))
    renglones_derecha = [("Punto de venta", f"{f['punto_de_venta']:05d}",
                          "Comp. Nro", f"{f['numero']:08d}"),
                         ("Fecha de emisión", dia(f["fecha"])),
                         ("CUIT", documento_legible(DOC_CUIT, cuit)[5:] if len(cuit) == 11 else cuit)]
    if cfg.get("ingresos_brutos"):
        renglones_derecha.append(("Ingresos Brutos", cfg["ingresos_brutos"]))
    if cfg.get("inicio_de_actividades"):
        renglones_derecha.append(("Inicio de actividades", cfg["inicio_de_actividades"]))
    y = y0 + 22             # debajo del recuadro de la letra: más arriba se le metía encima
    for pares in renglones_derecha:
        pdf.set_xy(108, y)
        for rotulo, valor in zip(pares[::2], pares[1::2]):
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(pdf.get_string_width(latin(rotulo + ": ")) + 1, 5, latin(rotulo + ": "))
            pdf.set_font("Helvetica", "", 9)
            pdf.cell(pdf.get_string_width(latin(valor)) + 6, 5, latin(valor))
        y += 5.5

    # EL CLIENTE, en su recuadro.
    cond_cliente = next((k for k, v in CONDICIONES_DEL_CLIENTE.items()
                         if v == f["condicion_receptor"]), "")
    asociada = None
    if f["asociada_a"]:
        c.execute("SELECT tipo, punto_de_venta, numero, fecha FROM facturas WHERE id = ?",
                  (f["asociada_a"],))
        asociada = c.fetchone()
    renglones_cliente = [
        ("Cliente", (f["nombre_receptor"] or ("Consumidor final" if cond_cliente ==
                                               "Consumidor final" else "")),
         documento_legible(f["doc_tipo"], f["doc_nro"])),
        ("Condición frente al IVA", cond_cliente, ""),
        ("Condición de venta", detalle["condicion_de_venta"], ""),
    ]
    if asociada:
        renglones_cliente.append(
            ("Comprobante asociado", nombre_del_comprobante(asociada["tipo"],
                                                            asociada["punto_de_venta"],
                                                            asociada["numero"]),
             f"del {dia(asociada['fecha'])}"))
    y = y0 + alto + 3
    pdf.rect(x0, y, ancho, 4 + 5.5 * len(renglones_cliente))
    y += 2
    for rotulo, valor, a_la_derecha in renglones_cliente:
        pdf.set_xy(13, y)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(pdf.get_string_width(latin(rotulo + ": ")) + 1, 5, latin(rotulo + ": "))
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(110, 5, cortar(valor, 108))
        if a_la_derecha:
            pdf.set_xy(140, y)
            pdf.cell(57, 5, latin(a_la_derecha), align="R")
        y += 5.5

    # LO VENDIDO.
    pdf.set_xy(x0, y + 5)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(230, 230, 230)
    columnas = ((16, "Cant.", "C"), (104, "Descripción", "L"),
                (35, "P. unit." + (" s/IVA" if discrimina else ""), "R"),
                (35, "Importe" + (" s/IVA" if discrimina else ""), "R"))
    for ancho_col, rotulo, alinear in columnas:
        pdf.cell(ancho_col, 7, latin(rotulo), border=1, align=alinear, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for cantidad, texto, precio in detalle["renglones"]:
        unitario = float(precio or 0) / ((1 + IVA_GENERAL / 100) if discrimina else 1)
        pdf.cell(16, 6, miles(cantidad, 0), border="LR", align="C")
        pdf.cell(104, 6, cortar(texto, 101), border="LR")
        pdf.cell(35, 6, latin(formato_precio(unitario)), border="LR", align="R")
        pdf.cell(35, 6, latin(formato_precio(unitario * cantidad)), border="LR", align="R",
                 new_x="LMARGIN", new_y="NEXT")
    pdf.cell(ancho, 0, "", border="T", new_x="LMARGIN", new_y="NEXT")

    # LOS TOTALES.
    pdf.ln(3)
    totales = ([("Importe neto gravado", f["neto"]), (f"IVA {miles(IVA_GENERAL, 0)}%", f["iva"])]
               if discrimina else [])
    for rotulo, valor in totales:
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(155, 6, latin(rotulo + ":"), align="R")
        pdf.cell(35, 6, latin(formato_precio(valor)), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(155, 8, "Importe total:", align="R")
    pdf.cell(35, 8, latin(formato_precio(f["total"])), align="R", new_x="LMARGIN", new_y="NEXT")
    if f["tipo"] in (6, 8):
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(0, 5, latin("Régimen de Transparencia Fiscal al Consumidor (Ley 27.743) - "
                             f"IVA contenido: {formato_precio(f['iva'])}"), align="R",
                 new_x="LMARGIN", new_y="NEXT")

    # EL CAE Y EL QR.
    if f["estado"] == "autorizada" and f["cae"]:
        imagen = io.BytesIO()
        qrcode.make(url_del_qr(f, cfg.get("cuit") or 0)).save(imagen, format="PNG")
        imagen.seek(0)
        y = pdf.get_y() + 6
        if y > 245:
            pdf.add_page()
            y = 15
        pdf.line(x0, y - 2, x0 + ancho, y - 2)
        pdf.image(imagen, x=x0, y=y, w=32)
        pdf.set_xy(x0 + 38, y + 5)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 6, latin("Comprobante autorizado por ARCA"), new_x="LMARGIN", new_y="NEXT")
        for rotulo, valor in (("CAE N°", f["cae"]),
                              ("Fecha de vencimiento del CAE", dia(f["cae_vence"]))):
            pdf.set_x(x0 + 38)
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(pdf.get_string_width(latin(rotulo + ": ")) + 1, 5, latin(rotulo + ": "))
            pdf.set_font("Helvetica", "", 9)
            pdf.cell(0, 5, latin(valor), new_x="LMARGIN", new_y="NEXT")
        if f["ambiente"] != "produccion":
            pdf.set_x(x0 + 38)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(180, 0, 0)
            pdf.cell(0, 6, latin("DE PRUEBA (homologación): no tiene validez fiscal"),
                     new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
    return bytes(pdf.output())


def lo_que_conviene_completar():
    """Los datos del negocio que no hacen falta para facturar pero sí para que el PDF diga todo
    lo que pide ARCA: [en castellano]."""
    datos = _secretos_de_arca()
    return [que for clave, que in (("razon_social", "razon_social (el nombre del negocio)"),
                                   ("domicilio", "domicilio (el comercial)"),
                                   ("ingresos_brutos", "ingresos_brutos (el número)"),
                                   ("inicio_de_actividades", "inicio_de_actividades (dd/mm/aaaa)"))
            if not str(datos.get(clave) or "").strip()]


def probar_la_conexion_con_arca():
    """Para Administrar: [(qué, bien o mal, detalle)] de cada paso —los secretos, el permiso,
    el último número de cada tipo—, sin facturar nada."""
    pasos = []
    falta = lo_que_falta_para_facturar()
    pasos.append(("Los datos en los secretos", not falta,
                  "completos" if not falta else "falta " + ", ".join(falta)))
    if falta:
        return pasos
    cfg = configuracion_de_arca()
    try:
        _ticket_de_acceso(cfg)
        pasos.append(("El permiso de ARCA (WSAA)", True, f"ambiente {cfg['ambiente']}"))
    except ErrorDeArca as e:
        pasos.append(("El permiso de ARCA (WSAA)", False, str(e)))
        return pasos
    tipo = tipo_de_factura(cfg["condicion"], "Consumidor final")
    try:
        numero = ultimo_autorizado(cfg, tipo)
        pasos.append(("El último número (WSFE)", True,
                      f"{nombre_del_comprobante(tipo, cfg['punto_de_venta'], numero)}"
                      if numero else "todavía no hay ninguna"))
    except ErrorDeArca as e:
        pasos.append(("El último número (WSFE)", False, str(e)))
    return pasos


def elegir_cliente_de_la_factura(prefijo):
    """Los campos del cliente de la factura, para la caja: (condición, documento, nombre).
    Consumidor final de entrada, que puede ir sin documento."""
    # La condición sola en su renglón: en el diálogo de cobrar, de a tres, «Consumidor final» se
    # cortaba en «Consumidor f…» (se vio en una captura).
    condicion = st.selectbox("Cliente:", list(CONDICIONES_DEL_CLIENTE),
                             key=f"{prefijo}_condicion_factura")
    _c2, _c3 = cols([1, 1])
    documento = _c2.text_input("DNI o CUIT" + (" (opcional)" if condicion == "Consumidor final"
                                               else ""),
                               key=f"{prefijo}_documento_factura", placeholder="Ej: 30123456")
    nombre = _c3.text_input("Nombre (opcional)", key=f"{prefijo}_nombre_factura")
    return condicion, documento, nombre


def mostrar_la_factura_de(venta_id, prefijo):
    """En la caja: el estado de la factura de una venta cobrada y lo que se puede hacer —el
    PDF, consultarla si quedó pendiente, o hacerla si todavía no tiene—. Nada si no hay ARCA."""
    vigente = factura_vigente_de(venta_id)
    if vigente and vigente["estado"] == "autorizada":
        _f1, _f2 = cols([3, 1])
        _f1.success(f"🧾 {nombre_del_comprobante(vigente['tipo'], vigente['punto_de_venta'], vigente['numero'])}"
                    f" · CAE {vigente['cae']}"
                    + ("" if vigente["ambiente"] == "produccion" else " · de prueba"))
        _f2.download_button("📄 Factura (PDF)",
                            data=lambda: factura_para_descargar(vigente["id"]),
                            file_name=f"factura_{vigente['punto_de_venta']:05d}-"
                                      f"{vigente['numero']:08d}.pdf",
                            mime="application/pdf", key=f"{prefijo}_pdf_factura", width="stretch")
        return
    if vigente:
        st.warning(f"🧾 La {nombre_del_comprobante(vigente['tipo'], vigente['punto_de_venta'], vigente['numero'])}"
                   " quedó pendiente: no se sabe si ARCA la hizo.")
        if st.button("🔄 Consultar en ARCA", key=f"{prefijo}_consultar_factura"):
            ok, texto = consultar_factura_pendiente(vigente["id"])
            avisar("success" if ok else "warning", texto)
            st.rerun()
        return
    if not configuracion_de_arca():
        return
    with st.container(border=True):
        st.markdown("**🧾 ¿Le hacés factura?**")
        condicion, documento, nombre = elegir_cliente_de_la_factura(prefijo)
        if candado("hacer una factura", st.button("🧾 Hacer la factura", key=f"{prefijo}_facturar"),
                   f"{prefijo}_facturar_candado", nivel="empleado"):
            ok, texto = facturar_venta(venta_id, condicion, documento, nombre)
            avisar("success" if ok else "warning", texto)
            st.rerun()

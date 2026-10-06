"""Las fotos de las fichas: la cadena de certificados incompleta (con certificados de verdad
y sin internet) y la marca pegada al código en la dirección de la ficha.

Uso:
    python3 pruebas_de_los_certificados.py

Por qué existe: las 5.063 búsquedas de foto de FISPA fallaron con «SSLError» desde el
servidor. Lo más común es que el sitio no mande el certificado intermedio: el navegador lo baja
solo y Python no. Ver pedir_con_la_cadena_completa() en logica/proveedores.py.

Arma con openssl una autoridad, un intermedio y el certificado de un sitio que dice de dónde
bajar el intermedio, levanta ese sitio en esta máquina SIN mandar el intermedio, y controla:
que el pedido común falle, que con la cadena completa ande verificando, y que un sitio con un
certificado de OTRA autoridad siga fallando (no se apaga la verificación).
"""
import http.server
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading


def _openssl(*args, cwd):
    subprocess.run(["openssl", *args], cwd=cwd, check=True, capture_output=True)


def _armar_certificados(d, puerto_aia):
    with open(os.path.join(d, "ext_inter.cnf"), "w") as f:
        f.write("basicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\n")
    with open(os.path.join(d, "ext_sitio.cnf"), "w") as f:
        f.write("basicConstraints=CA:FALSE\nsubjectAltName=DNS:localhost,IP:127.0.0.1\n"
                f"authorityInfoAccess=caIssuers;URI:http://127.0.0.1:{puerto_aia}/inter.der\n")
    for nombre in ("raiz", "inter", "sitio", "otra"):
        _openssl("genrsa", "-out", f"{nombre}.key", "2048", cwd=d)
    _openssl("req", "-x509", "-new", "-key", "raiz.key", "-days", "2", "-subj", "/CN=Raiz de prueba",
             "-out", "raiz.pem", cwd=d)
    _openssl("req", "-x509", "-new", "-key", "otra.key", "-days", "2", "-subj", "/CN=Otra raiz",
             "-out", "otra.pem", cwd=d)
    _openssl("req", "-new", "-key", "inter.key", "-subj", "/CN=Intermedio de prueba",
             "-out", "inter.csr", cwd=d)
    _openssl("x509", "-req", "-in", "inter.csr", "-CA", "raiz.pem", "-CAkey", "raiz.key",
             "-CAcreateserial", "-days", "2", "-extfile", "ext_inter.cnf", "-out", "inter.pem", cwd=d)
    _openssl("x509", "-in", "inter.pem", "-outform", "DER", "-out", "inter.der", cwd=d)
    _openssl("req", "-new", "-key", "sitio.key", "-subj", "/CN=localhost", "-out", "sitio.csr", cwd=d)
    _openssl("x509", "-req", "-in", "sitio.csr", "-CA", "inter.pem", "-CAkey", "inter.key",
             "-CAcreateserial", "-days", "2", "-extfile", "ext_sitio.cnf", "-out", "sitio.pem", cwd=d)


class _Silencioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def _servir(d, tls=False):
    manejador = lambda *a, **k: _Silencioso(*a, directory=d, **k)
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), manejador)
    if tls:
        contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        contexto.load_cert_chain(os.path.join(d, "sitio.pem"), os.path.join(d, "sitio.key"))
        servidor.socket = contexto.wrap_socket(servidor.socket, server_side=True)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor


def main():
    d = tempfile.mkdtemp(prefix="pruebas_cert_")
    raiz = os.path.dirname(os.path.abspath(__file__))
    fallas = []
    try:
        aia = _servir(d)                         # sirve inter.der por http
        _armar_certificados(d, aia.server_port)
        with open(os.path.join(d, "hola.txt"), "w") as f:
            f.write("hola")
        sitio = _servir(d, tls=True)             # presenta SOLO sitio.pem, sin el intermedio
        url = f"https://127.0.0.1:{sitio.server_port}/hola.txt"
        os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
        os.environ["REQUESTS_CA_BUNDLE"] = os.path.join(d, "raiz.pem")   # «las de siempre»
        os.environ.pop("CURL_CA_BUNDLE", None)
        sys.path.insert(0, raiz)
        os.chdir(d)
        import logica
        import requests
        ns = logica.todo_lo_de_la_logica()
        g = ns["descargar_imagen"].__globals__
        g["direccion_interna"] = lambda u: ""    # el intermedio está en 127.0.0.1, a propósito

        try:
            requests.get(url, timeout=10)
            fallas.append("el pedido común debía fallar (el sitio no manda el intermedio)")
        except requests.exceptions.SSLError as e:
            if "issuer" not in str(e).lower():
                fallas.append(f"el pedido común falló por otra cosa: {e}")
            if ns["motivo_del_error"](e) != "SSLError: le falta un certificado intermedio":
                fallas.append(f"motivo: {ns['motivo_del_error'](e)}")
        r = ns["pedir_con_la_cadena_completa"](requests.get, url, timeout=10)
        if r.status_code != 200 or r.text != "hola":
            fallas.append(f"con la cadena completa: {r.status_code} {r.text[:40]!r}")

        # Con OTRA autoridad como «las de siempre», el intermedio no alcanza: tiene que fallar.
        ns["del_proceso"]("paquetes_de_certificados", dict).clear()
        os.environ["REQUESTS_CA_BUNDLE"] = os.path.join(d, "otra.pem")
        try:
            ns["pedir_con_la_cadena_completa"](requests.get, url, timeout=10)
            fallas.append("con una autoridad desconocida NO tenía que andar")
        except requests.exceptions.SSLError:
            pass

        # Y el intermedio en una dirección interna no se baja (el control de siempre).
        g["direccion_interna"] = lambda u: "dirección interna"
        ns["del_proceso"]("paquetes_de_certificados", dict).clear()
        os.environ["REQUESTS_CA_BUNDLE"] = os.path.join(d, "raiz.pem")
        if ns["paquete_con_la_cadena_completa"](url) is not None:
            fallas.append("bajó el intermedio de una dirección interna")
        # La otra mitad de las fotos de FISPA: la marca pegada al código en la dirección de la
        # ficha. En el sitio de FISPA se saca; en otro sitio, o si es otra marca, no.
        p = "https://www.fispaargentina.com.ar/catalogo.php?b={codigo}#fispa"
        for codigo, esperado in (("24058FISPA", "b=24058#"), ("11000AFISPA", "b=11000A#"),
                                 ("LFDN005LUCAS", "b=LFDN005LUCAS#"), ("40011", "b=40011#")):
            if esperado not in ns["url_de_la_ficha"](p, codigo):
                fallas.append(f"ficha de {codigo}: {ns['url_de_la_ficha'](p, codigo)}")
        if "c=24058FISPA" not in ns["url_de_la_ficha"]("https://otra.example/?c={codigo}", "24058FISPA"):
            fallas.append("en otro sitio la marca pegada no se saca")
        sitio.shutdown()
        aia.shutdown()
    finally:
        os.chdir(raiz)
        shutil.rmtree(d, ignore_errors=True)
    for f in fallas:
        print("   ✗", f)
    print("✅ certificados: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())

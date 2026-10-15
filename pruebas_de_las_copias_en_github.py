"""Pruebas de la copia en GitHub con las fotos en bloques, contra un GitHub de mentira.

Uso:
    python3 pruebas_de_las_copias_en_github.py

Levanta en esta máquina un servidor que contesta como la API de GitHub (lo justo: blobs,
árboles, commits, ramas y bajar un archivo) y apunta la app ahí con EQUIVALENCIAS_API_DE_GITHUB.
Prueba el ciclo entero: subir la base y los bloques de fotos, «reiniciar» con el disco vacío y
ver que vuelvan; que subir la base no borre los bloques; que una foto nueva suba solo su bloque;
y que si al arrancar no se pueden bajar las fotos, no se borre nada de GitHub.

Nunca toca la base de trabajo ni sale a internet.
"""
import base64
import hashlib
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs


class GitHubDeMentira:
    def __init__(self):
        self.blobs, self.arboles, self.commits, self.ramas = {}, {}, {}, {}
        self.fallar_contenidos = ()          # rutas que contestan 500 al bajarlas
        self.privado = True                  # lo que contesta /repos/dueño/repo
        self.subidas = []                    # rutas de los blobs subidos, en orden

    def _sha(self, datos):
        return hashlib.sha1(datos + os.urandom(4)).hexdigest()

    def arbol_de(self, rama):
        commit = self.ramas.get(rama)
        return self.arboles[self.commits[commit]["tree"]] if commit else None


def _manejador(gh):
    class M(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _responder(self, estado, cuerpo=None, crudo=None):
            datos = crudo if crudo is not None else json.dumps(cuerpo or {}).encode()
            self.send_response(estado)
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)

        def _cuerpo(self):
            return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")

        def do_GET(self):
            u = urlparse(self.path)
            partes = u.path.split("/")
            q = parse_qs(u.query)
            if "/git/trees/" in u.path:
                arbol = gh.arbol_de(partes[-1])
                if arbol is None:
                    return self._responder(404, {"message": "Not Found"})
                return self._responder(200, {"truncated": False, "tree": [
                    {"path": p, "mode": "100644", "type": "blob", "sha": s} for p, s in arbol.items()]})
            if "/git/ref/heads/" in u.path:
                return self._responder(200 if partes[-1] in gh.ramas else 404, {})
            if "/contents/" in u.path:
                ruta = u.path.split("/contents/", 1)[1]
                arbol = gh.arbol_de(q.get("ref", [""])[0]) or {}
                if ruta in gh.fallar_contenidos:
                    return self._responder(500, {"message": "error"})
                if ruta not in arbol:
                    return self._responder(404, {"message": "Not Found"})
                return self._responder(200, crudo=gh.blobs[arbol[ruta]])
            if len(partes) == 4:            # /repos/dueño/repo
                return self._responder(200, {"private": gh.privado})
            return self._responder(404, {})

        def do_POST(self):
            u = urlparse(self.path)
            cuerpo = self._cuerpo()
            if u.path.endswith("/git/blobs"):
                datos = base64.b64decode(cuerpo["content"])
                sha = gh._sha(datos)
                gh.blobs[sha] = datos
                return self._responder(201, {"sha": sha})
            if u.path.endswith("/git/trees"):
                arbol = {}
                for e in cuerpo["tree"]:
                    if "content" in e:
                        sha = gh._sha(e["content"].encode())
                        gh.blobs[sha] = e["content"].encode()
                    else:
                        sha = e["sha"]
                        assert sha in gh.blobs, f"blob desconocido {sha}"
                        gh.subidas.append(e["path"]) if False else None
                    arbol[e["path"]] = sha
                sha = gh._sha(b"tree")
                gh.arboles[sha] = arbol
                return self._responder(201, {"sha": sha})
            if u.path.endswith("/git/commits"):
                sha = gh._sha(b"commit")
                gh.commits[sha] = cuerpo
                return self._responder(201, {"sha": sha})
            if u.path.endswith("/git/refs"):
                gh.ramas[cuerpo["ref"].rsplit("/", 1)[1]] = cuerpo["sha"]
                return self._responder(201, {})
            return self._responder(404, {})

        def do_PATCH(self):
            u = urlparse(self.path)
            rama = u.path.rsplit("/", 1)[1]
            if rama not in gh.ramas:
                return self._responder(422, {"message": "Reference does not exist"})
            gh.ramas[rama] = self._cuerpo()["sha"]
            return self._responder(200, {})
    return M


def _foto(color):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (300, 300), color)
    d = ImageDraw.Draw(img)
    for i in range(0, 300, 23):
        d.line((i, 0, 300 - i, 300), fill=(255 - i % 255, i % 255, 90), width=3)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def probar(ns, gh, carpeta):
    fallas = []

    def esperar(nombre, real, esperado):
        if real != esperado:
            fallas.append(f"{nombre}: dio {real!r}, se esperaba {esperado!r}")

    g = ns["inflacion_desde"].__globals__
    g["secretos_app"] = lambda: {"github_token": "x", "github_repo": "yo/repo"}
    g["FOTOS_POR_BLOQUE"] = 2                 # bloques chicos, para tener varios
    c = ns["c"]
    c.execute("INSERT INTO marcas (nombre, tipo) VALUES ('PRUEBA', 'PROVEEDOR')")
    mid = c.execute("SELECT id FROM marcas WHERE nombre = 'PRUEBA'").fetchone()[0]
    ids = []
    for i in range(4):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
                  "VALUES (?, ?, ?, ?)", (f"P{i}", f"P{i}", f"PIEZA {i}", mid))
        ids.append(c.lastrowid)
    fotos = [ns["agregar_foto_producto"](ids[i], _foto((40 * i, 90, 160)))[0] for i in range(3)]
    ns["agregar_foto_producto"](ids[3], _foto((1, 2, 3)), origen="ficha",
                                fuente="https://proveedor.example/foto.jpg")
    ns["conn"].commit()

    ok, texto = ns["subir_la_copia_si_cambio"]()
    esperar("se sube la base", ok, True)
    ok, texto = ns["subir_las_fotos_si_cambiaron"]()
    esperar(f"se suben las fotos ({texto})", ok, True)
    rama = ns["RAMA_DE_LA_COPIA"]
    bloques = sorted(p for p in gh.arbol_de(rama) if p.startswith("fotos_propias/"))
    esperar("bloques en GitHub (3 fotos propias, de a 2)", len(bloques),
            len({f // 2 for f in fotos}))
    copia = gh.blobs[gh.arbol_de(rama)["datos_iniciales.db.gz"]]
    import gzip
    ruta_copia = os.path.join(carpeta, "mirar.db")
    with open(ruta_copia, "wb") as f:
        f.write(gzip.decompress(copia))
    esperar("la copia de la base ya no lleva las fotos",
            sqlite3.connect(ruta_copia).execute("SELECT COUNT(*) FROM producto_fotos").fetchone()[0], 0)
    # Lo que apunta a algo que no está, en cualquier tabla: la prueba de la copia lo ve.
    _mirar = sqlite3.connect(ruta_copia)
    def _rotas():
        return [p_ for p_ in ns["_usarla_como_la_usaria_el_mostrador"](_mirar)
                if "apuntan a algo que no está" in p_]
    esperar("la copia sana, sin filas rotas", _rotas(), [])
    _mirar.execute("INSERT INTO ventas_registradas (producto_id, termino_pedido) VALUES (999999, 'x')")
    _mirar.commit()
    esperar("una venta de un producto que no está, se ve", _rotas(),
            ["1 fila(s) apuntan a algo que no está (en ventas_registradas)"])
    _mirar.close()

    # La ficha de la copia y la copia de hoy en el historial: el mismo archivo, sin subirlo de nuevo.
    from datetime import date, timedelta
    hoy = date.today()
    arbol = gh.arbol_de(rama)
    esperar("la de hoy en el historial es el mismo archivo",
            arbol.get(f"historial/{hoy.isoformat()}/datos_iniciales.db.gz"),
            arbol["datos_iniciales.db.gz"])
    ficha = json.loads(gh.blobs[arbol["datos_iniciales.db.gz.json"]])
    esperar("la ficha dice qué tiene", (ficha["productos"], ficha["control_de_integridad"],
                                        ficha["bytes"]), (4, "ok", len(copia)))
    esperar("y la del historial también tiene su ficha",
            f"historial/{hoy.isoformat()}/datos_iniciales.db.gz.json" in arbol, True)

    # Qué copias viejas quedan: 200 días seguidos de copias, y se sube la de hoy.
    viejo = gh.blobs[arbol["datos_iniciales.db.gz"]]
    for d in range(1, 201):
        arbol[f"historial/{(hoy - timedelta(days=d)).isoformat()}/datos_iniciales.db.gz"] = \
            arbol["datos_iniciales.db.gz"]
    c.execute("UPDATE productos SET precio = 7 WHERE id = ?", (ids[0],))
    ns["conn"].commit()
    ok, _ = ns["subir_la_copia_si_cambio"]()
    fechas = sorted({p.split("/")[1] for p in gh.arbol_de(rama) if p.startswith("historial/")})
    esperar("quedan las 7 diarias, las semanales y las mensuales",
            fechas, sorted(ns["copias_a_guardar"]({f: 1 for f in fechas + [
                (hoy - timedelta(days=d)).isoformat() for d in range(1, 201)]}, hoy.isoformat())))
    esperar("cuántas quedan (entre 7 y 17)", 7 <= len(fechas) <= 17, True)
    esperar("los últimos 7 días están", all((hoy - timedelta(days=d)).isoformat() in fechas
                                            for d in range(7)), True)
    esperar("la de hoy es la nueva, no la de antes",
            gh.blobs[gh.arbol_de(rama)[f"historial/{hoy.isoformat()}/datos_iniciales.db.gz"]] != viejo,
            True)
    # Con el tope de tamaño se sueltan las más viejas, y la de hoy queda siempre.
    g["MB_DEL_HISTORIAL"] = 3
    quedan = ns["copias_a_guardar"]({(hoy - timedelta(days=d)).isoformat(): 1024 * 1024
                                     for d in range(30)}, hoy.isoformat())
    esperar("con tope: las 3 más nuevas", sorted(quedan),
            sorted((hoy - timedelta(days=d)).isoformat() for d in range(3)))
    g["MB_DEL_HISTORIAL"] = 400

    # Subir la base otra vez (cambió un precio) no borra los bloques.
    c.execute("UPDATE productos SET precio = 99 WHERE id = ?", (ids[0],))
    ns["conn"].commit()
    ok, _ = ns["subir_la_copia_si_cambio"]()
    esperar("se vuelve a subir la base", ok, True)
    esperar("los bloques siguen", sorted(p for p in gh.arbol_de(rama) if p.startswith("fotos_propias/")),
            bloques)
    esperar("sin cambios en las fotos no se sube nada", ns["subir_las_fotos_si_cambiaron"]()[0], None)

    # «Reinicio»: una base vacía se restaura de GitHub, con sus fotos.
    vacia = sqlite3.connect(os.path.join(carpeta, "reiniciada.db"))
    esperar("se restaura", ns["_restaurar_desde_semilla"](vacia), True)
    esperar("vuelven las fotos propias",
            sorted(r[0] for r in vacia.execute("SELECT id FROM producto_fotos")), sorted(fotos))
    esperar("con su firma",
            vacia.execute("SELECT COUNT(*) FROM producto_fotos WHERE firma_blob IS NOT NULL").fetchone()[0],
            c.execute("SELECT COUNT(*) FROM producto_fotos WHERE firma_blob IS NOT NULL "
                      "AND origen = 'subida'").fetchone()[0])
    esperar("y son la foto de su ficha",
            vacia.execute("SELECT COUNT(*) FROM productos WHERE imagen_url LIKE 'data:%'").fetchone()[0], 3)
    vacia.close()

    # Una foto nueva sube su bloque, y borrar una saca el bloque que quedó vacío.
    ns["agregar_foto_producto"](ids[3], _foto((200, 10, 10)))
    ns["conn"].commit()
    antes = dict(gh.arbol_de(rama))
    ok, texto = ns["subir_las_fotos_si_cambiaron"]()
    despues = gh.arbol_de(rama)
    cambiaron = sorted(p for p in despues if p.startswith("fotos_propias/") and antes.get(p) != despues[p])
    esperar(f"foto nueva: un solo bloque ({texto})", len(cambiaron), 1)
    esperar("la base no se tocó", despues["datos_iniciales.db.gz"], antes["datos_iniciales.db.gz"])
    ns["eliminar_foto_producto"](fotos[0])
    ns["conn"].commit()
    ns["subir_las_fotos_si_cambiaron"]()
    restantes = c.execute("SELECT id FROM producto_fotos WHERE origen = 'subida'").fetchall()
    esperar("bloques después de borrar",
            sorted(p for p in gh.arbol_de(rama) if p.startswith("fotos_propias/")),
            sorted({ns["ruta_del_bloque_de_fotos"](r[0] // 2) for r in restantes}))

    # Si al arrancar no se pueden bajar las fotos: se anota, y no se borra nada de GitHub.
    gh.fallar_contenidos = tuple(p for p in gh.arbol_de(rama) if p.startswith("fotos_propias/"))
    vacia = sqlite3.connect(os.path.join(carpeta, "reiniciada2.db"))
    ns["_restaurar_desde_semilla"](vacia)
    esperar("sin poder bajar las fotos: queda anotado",
            vacia.execute("SELECT valor FROM configuracion WHERE clave = 'fotos_github_sin_bajar'").fetchone(),
            ("1",))
    vacia.close()
    ns["guardar_config"]("fotos_github_sin_bajar", "1")
    c.execute("DELETE FROM producto_fotos")
    ns["conn"].commit()
    antes = dict(gh.arbol_de(rama))
    ok, texto = ns["subir_las_fotos_si_cambiaron"]()
    esperar("y mientras tanto no se sube (ni se borra) nada", (ok, gh.arbol_de(rama)), (False, antes))
    gh.fallar_contenidos = ()
    ok, texto = ns["subir_las_fotos_si_cambiaron"]()
    esperar("cuando GitHub vuelve, se bajan las fotos", ns["obtener_config"]("fotos_github_sin_bajar", ""), "")
    esperar("y están otra vez en la base",
            c.execute("SELECT COUNT(*) FROM producto_fotos").fetchone()[0], len(restantes) + 0)

    # SIN CIFRAR, SOLO A UN REPOSITORIO PRIVADO (ver se_puede_subir_sin_cifrar()). Público y sin
    # clave: no sube nada, ni la base ni las fotos, y la salud lo dice en rojo.
    gh.privado = False
    cfg_gh = ns["config_github"]()
    cab_gh = ns["_cabeceras_de_github"](cfg_gh)
    esperar("público y sin clave, no", ns["se_puede_subir_sin_cifrar"](cfg_gh, cab_gh),
            (False, ns["TEXTO_COPIA_FRENADA_SIN_CIFRAR"]))
    antes_de_frenar = dict(gh.arbol_de(rama))
    c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id) "
              "VALUES ('P90', 'P90', 'PIEZA NUEVA', ?)", (mid,))
    ns["conn"].commit()
    ok, texto = ns["subir_la_copia_si_cambio"](aunque_no_haya_cambios=True)
    esperar("la base no sube", (ok, texto.startswith("🔓")), (False, True))
    esperar("ni las fotos", ns["subir_las_fotos_si_cambiaron"]()[0], False)
    esperar("y en GitHub no cambió nada", gh.arbol_de(rama), antes_de_frenar)
    esperar("la salud lo dice en rojo", [p["nivel"] for p in ns["diagnostico_de_salud"]()
                                         if "NO SE ESTÁ SUBIENDO" in p["titulo"]], ["alto"])
    # Y la pantalla de la copia no dice «al día»: decía «✅ se actualiza sola, se pierden como
    # mucho 15 minutos» con la copia frenada (ver cuanto_perderias_si_reinicia()).
    _ultima_buena = ns["obtener_config"]("ultimo_backup_github", "")
    _r = ns["cuanto_perderias_si_reinicia"]()
    esperar("la copia frenada se ve atrasada, desde la última buena",
            (_r["atrasada"], _r["fecha_semilla"][:10], "🔓" in _r["por_que"]),
            (True, f"{_ultima_buena[8:10]}/{_ultima_buena[5:7]}/{_ultima_buena[:4]}", True))
    esperar("y la salud dice de cuándo es la última copia buena",
            [f"la última copia que subió es del {_ultima_buena[:16]}" in p["detalle"]
             for p in ns["diagnostico_de_salud"]() if "NO SE ESTÁ SUBIENDO" in p["titulo"]], [True])
    # «Frenada desde»: la primera vez, no la última vuelta del vigía.
    ns["guardar_config"]("copia_frenada_sin_cifrar", "2026-10-12 15:56:00")
    ns["se_puede_subir_sin_cifrar"](cfg_gh, cab_gh)
    esperar("frenada desde la primera vez", ns["obtener_config"]("copia_frenada_sin_cifrar", ""),
            "2026-10-12 15:56:00")
    # Con la clave sube, y cifrada; el aviso se va.
    g["secretos_app"] = lambda: {"github_token": "x", "github_repo": "yo/repo",
                                 "clave_copia": "una frase larga de prueba"}
    ok, texto = ns["subir_la_copia_si_cambio"](aunque_no_haya_cambios=True)
    esperar(f"con clave, sube ({texto})", ok, True)
    esperar("y va cifrada", ns["esta_cifrada"](gh.blobs[gh.arbol_de(rama)["datos_iniciales.db.gz"]]),
            True)
    esperar("y el aviso se fue", [p for p in ns["diagnostico_de_salud"]()
                                  if "NO SE ESTÁ SUBIENDO" in p["titulo"]], [])
    esperar("y la copia ya no está atrasada", ns["cuanto_perderias_si_reinicia"]()["atrasada"], False)
    # LO DAÑADO NO SE SUBE (ver la_base_esta_sana()): pisaría la última copia buena, que es la
    # que se usa para arrancar después de un reinicio.
    _buena = ns["generar_backup_sin_fotos"]()
    antes_del_dano = dict(gh.arbol_de(rama))
    for _nombre, _danada in (("cortada a la mitad", _buena[:len(_buena) // 2]),
                             ("con el encabezado roto", b"\x00" * 100 + _buena[100:]),
                             ("que no es una base", b"esto no es una base" * 500)):
        ok, texto = ns["subir_backup_a_github"](_danada, "prueba")
        esperar(f"una base {_nombre} no se sube", (ok, "daño" in texto), (False, True))
    esperar("y en GitHub sigue la buena", gh.arbol_de(rama), antes_del_dano)
    esperar("la salud lo sabe", bool(ns["obtener_config"]("base_danada", "")), True)
    ok, texto = ns["subir_la_copia_si_cambio"](aunque_no_haya_cambios=True)
    esperar("con la base sana vuelve a subir, y el aviso se va",
            (ok, ns["obtener_config"]("base_danada", "")), (True, ""))
    _frases = {ns["frase_para_la_copia"]() for _ in range(50)}
    esperar("la frase que propone la app: larga, distinta cada vez y sin lo que rompe los secretos",
            (len(_frases), min(len(f) for f in _frases),
             any(ch in f for f in _frases for ch in "\"\\'0O1lI ")), (50, 35, False))
    # Subirla sin cifrar a uno público se puede, pero solo puesto a propósito en los secretos.
    g["secretos_app"] = lambda: {"github_token": "x", "github_repo": "yo/repo",
                                 "subir_copia_sin_cifrar": True}
    esperar("aceptado a propósito, sí", ns["se_puede_subir_sin_cifrar"](cfg_gh, cab_gh), (True, ""))
    g["secretos_app"] = lambda: {"github_token": "x", "github_repo": "yo/repo"}
    gh.privado = True
    esperar("privado y sin clave, sí", ns["se_puede_subir_sin_cifrar"](cfg_gh, cab_gh), (True, ""))

    # LA COPIA EN PARTES, Y BAJARLA: lo que hace la app al arrancar, y lo que pasa cuando la
    # copia pase de 90 MB (ver partes_de_la_copia() y bajar_la_copia_de_github()). No tenía
    # prueba. Con topes chicos, para que la copia de prueba se parta.
    def _productos_de(ruta):
        con = sqlite3.connect(ruta)
        try:
            return con.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
        finally:
            con.close()
    _en_la_base = c.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
    _archivo = ns["config_github"]()["archivo"]
    _tope, _tamano = g["TOPE_DE_UN_ARCHIVO_EN_GITHUB"], g["TAMANO_DE_CADA_PARTE"]
    g["TOPE_DE_UN_ARCHIVO_EN_GITHUB"], g["TAMANO_DE_CADA_PARTE"] = 2_000, 1_000
    ok, texto = ns["subir_la_copia_si_cambio"](aunque_no_haya_cambios=True)
    _arbol = gh.arbol_de(rama)
    esperar(f"grande, va en partes y sin el archivo entero de antes ({texto})",
            (ok, _archivo in _arbol, f"{_archivo}.partes" in _arbol, f"{_archivo}.parte2" in _arbol),
            (True, False, True, True))
    _bajada = ns["bajar_la_copia_de_github"](os.path.join(tempfile.mkdtemp(), "bajada.db"))
    esperar("al bajarla se juntan las partes y se abre",
            (bool(_bajada), _productos_de(_bajada) if _bajada else None), (True, _en_la_base))
    gh.fallar_contenidos = (f"{_archivo}.parte2",)
    esperar("si falta una parte, una copia incompleta no se usa",
            ns["bajar_la_copia_de_github"](os.path.join(tempfile.mkdtemp(), "b2.db")), None)
    gh.fallar_contenidos = ()
    g["TOPE_DE_UN_ARCHIVO_EN_GITHUB"], g["TAMANO_DE_CADA_PARTE"] = _tope, _tamano
    ok, texto = ns["subir_la_copia_si_cambio"](aunque_no_haya_cambios=True)
    _arbol = gh.arbol_de(rama)
    esperar("chica otra vez, va entera y las partes viejas se van",
            (ok, _archivo in _arbol, any(r.startswith(f"{_archivo}.parte") for r in _arbol)),
            (True, True, False))
    _bajada = ns["bajar_la_copia_de_github"](os.path.join(tempfile.mkdtemp(), "b3.db"))
    esperar("y entera también se baja", _productos_de(_bajada) if _bajada else None, _en_la_base)

    # EL VIGÍA SE VA CUANDO LLEGA CÓDIGO NUEVO (ver vigilar_la_copia()). Seguía corriendo el
    # código con que arrancó el servidor: la copia del 12/10 la subió una versión del 7/10.
    import time
    import types
    g["SEGUNDOS_ANTES_DE_LA_PRIMERA_COPIA"] = 0
    g["SEGUNDOS_ENTRE_MIRADAS"] = 0.05
    g["MINUTOS_ENTRE_COPIAS"] = 0.02                      # 1,2 segundos entre vueltas
    vueltas = []
    g["subir_la_copia_si_cambio"] = lambda *a, **k: vueltas.append(1) or (None, "")
    candado = ns["del_proceso"]("candado_de_la_copia_a_github", threading.Lock)
    esperar("el vigía arranca", ns["vigilar_la_copia"](), True)
    esperar("y uno solo", ns["vigilar_la_copia"](), False)
    time.sleep(0.5)
    esperar("y da vueltas", len(vueltas) >= 1, True)
    esperar("con la misma lógica no se va", candado.locked(), True)
    _logica = sys.modules["logica"]
    sys.modules["logica"] = types.ModuleType("logica")    # lo que hace app.py al recargarla
    try:
        libre = False
        for _ in range(100):
            if not candado.locked():
                libre = True
                break
            time.sleep(0.05)
    finally:
        sys.modules["logica"] = _logica
    esperar("con otra versión de la lógica se va y suelta el candado", libre, True)
    esperar("y la de ahora larga el suyo", ns["vigilar_la_copia"](), True)
    return fallas


def main():
    gh = GitHubDeMentira()
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _manejador(gh))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    os.environ["EQUIVALENCIAS_API_DE_GITHUB"] = f"http://127.0.0.1:{servidor.server_port}"
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
    carpeta = tempfile.mkdtemp(prefix="pruebas_github_")
    raiz = os.path.dirname(os.path.abspath(__file__))
    try:
        sys.path.insert(0, raiz)
        os.chdir(carpeta)
        import logica
        fallas = probar(logica.todo_lo_de_la_logica(), gh, carpeta)
        for f in fallas:
            print("   ✗", f)
        print("✅ copias en GitHub: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        servidor.shutdown()
        os.chdir(raiz)
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

"""Pruebas de los frenos: lo que la app hace cuando algo anda mal.

Uso:
    python3 pruebas_de_los_frenos.py

De la revisión con ChatGPT (puntos 59 a 78):
  · la base con daño: solo el administrador cambia cosas (ver TEXTO_DE_SOLO_LECTURA);
  · los avisos técnicos, solo para el administrador;
  · un proveedor que sigue caído: el descanso crece hasta un día (ver _descansar_por_falla());
  · el catálogo que se achica de golpe: aviso, y la copia buena no se pisa sola;
  · la copia de GitHub se baja y se prueba (ver verificar_la_copia_de_github()).

Corre en una carpeta temporal: nunca toca la base de trabajo, ni sale a internet (lo que
hablaría con GitHub se reemplaza por funciones de prueba).
"""
import os
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta


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
    for i in range(300):
        c.execute("INSERT INTO productos (codigo_raw, codigo_clean, descripcion, marca_id, precio, "
                  "stock) VALUES (?, ?, 'FILTRO', ?, 1000, 2)", (f"F{i:04d}", f"F{i:04d}", marca))
    conn.commit()

    # 1. La base con daño: el empleado no cambia nada; el administrador sí.
    originales = {k: g[k] for k in ("_nivel_de_quien_esta_adentro", "hay_claves_configuradas",
                                    "es_admin", "config_github", "subir_backup_a_github",
                                    "bajar_la_copia_de_github")}
    g["hay_claves_configuradas"] = lambda: True

    def puede(nivel):
        g["_nivel_de_quien_esta_adentro"] = lambda: nivel
        try:
            ns["exigir_nivel"]("empleado", "cambiar precios")
            return True
        except PermissionError:
            return False
    try:
        esperar("sana: el empleado puede", puede("operador"), True)
        ns["guardar_config"]("base_danada", "07/10 10:00 — *** in database main ***")
        esperar("con daño: el empleado no", puede("operador"), False)
        esperar("con daño: el administrador sí", puede("admin"), True)
        g["es_admin"] = lambda: False
        esperar("con daño: solo lectura para el empleado", ns["modo_solo_lectura"](), True)
        g["es_admin"] = lambda: True
        esperar("con daño: no para el administrador", ns["modo_solo_lectura"](), False)

        # 2. Los avisos técnicos van marcados para el administrador; los demás no.
        problemas = ns["diagnostico_de_salud"]()
        dano = [p for p in problemas if "daño" in p["titulo"]]
        esperar("el aviso de la base con daño es solo para el administrador",
                [p["solo_admin"] for p in dano], [True])
        esperar("todos los avisos dicen para quién son",
                all("solo_admin" in p for p in problemas), True)
        ns["guardar_config"]("base_danada", "")
        esperar("arreglada: el empleado vuelve a poder", puede("operador"), True)
    finally:
        g.update({k: v for k, v in originales.items()
                  if k in ("_nivel_de_quien_esta_adentro", "hay_claves_configuradas", "es_admin")})

    # 3. El descanso por falla crece: 1 h, 2 h, 4 h… hasta un día; y vuelve a una hora si anduvo.
    t0 = datetime(2026, 10, 7, 10, 0)
    minutos, ahora = [], t0
    for _ in range(7):
        m = ns["_descansar_por_falla"]("prueba", ahora=ahora)
        minutos.append(m)
        ahora += timedelta(minutes=m + 5)        # falla otra vez apenas termina el descanso
    esperar("el descanso crece hasta un día", minutos, [60, 120, 240, 480, 960, 1440, 1440])
    esperar("después de andar bien, vuelve a una hora",
            ns["_descansar_por_falla"]("prueba", ahora=ahora + timedelta(days=3)), 60)

    # 4. El catálogo que se achica de golpe.
    ayer, hoy = date(2030, 1, 6), date(2030, 1, 7)
    esperar("la primera foto no avisa", ns["cambio_anormal_del_catalogo"](ayer)[0], [])
    c.execute("DELETE FROM productos WHERE id IN (SELECT id FROM productos LIMIT 250)")
    conn.commit()
    cambios, desde = ns["cambio_anormal_del_catalogo"](hoy)
    esperar("300 → 50 productos: avisa", (cambios[:1], desde), (["productos 300 → 50"], "06/01"))
    esperar("y las unidades en stock", any("stock" in x for x in cambios), True)
    esperar("una caída chica no avisa",
            ns["cambio_anormal_del_catalogo"](hoy + timedelta(days=1))[0], [])

    # 5. Y la copia buena no se pisa sola. Lo que habla con GitHub se reemplaza.
    subidas = []
    try:
        g["config_github"] = lambda: {"repo": "prueba/prueba", "token": "x", "rama": "otra",
                                      "archivo": "copia.db"}
        g["subir_backup_a_github"] = lambda datos, mensaje: (subidas.append(datos) or True, "ok")
        ns["guardar_config"]("huella_copia_github", "vieja")
        ns["guardar_config"]("productos_en_la_copia", "1000")
        ok, texto = ns["subir_la_copia_si_cambio"]()
        esperar("1000 → 50: no se sube sola", (ok, "bajó de 1.000 a 50" in texto, len(subidas)),
                (False, True, 0))
        ok, _ = ns["subir_la_copia_si_cambio"](aunque_no_haya_cambios=True)
        esperar("con el botón, sí", (ok, len(subidas)), (True, 1))
        esperar("y ahora cuenta desde la nueva", ns["obtener_config"]("productos_en_la_copia"), "50")

        # 6. La prueba de recuperación: baja la copia aparte y mira que sea la última.
        huella, datos = ns["copia_para_github"]("")

        def bajar(destino=None):
            with open(destino, "wb") as f:
                f.write(datos)
            return destino
        g["bajar_la_copia_de_github"] = bajar
        ns["guardar_config"]("huella_copia_github", huella)
        ok, detalle = ns["verificar_la_copia_de_github"]()
        esperar("la copia se puede recuperar", (ok, "50 productos" in detalle), (True, True))
        esperar("verificada hace un rato: no toca", ns["toca_verificar_la_copia"](), False)
        esperar("al día siguiente, sí",
                ns["toca_verificar_la_copia"](datetime.now() + timedelta(hours=25)), True)
        ns["guardar_config"]("huella_copia_github", "otra")
        ok, detalle = ns["verificar_la_copia_de_github"]()
        esperar("no es la última que se subió", (ok, "huella" in detalle), (False, True))
        esperar("falló: se reintenta en dos horas",
                ns["toca_verificar_la_copia"](datetime.now() + timedelta(hours=3)), True)
        g["bajar_la_copia_de_github"] = lambda destino=None: None
        esperar("no se pudo bajar", ns["verificar_la_copia_de_github"]()[0], False)
        ns["guardar_config"]("base_danada", "")
        problemas = ns["diagnostico_de_salud"]()
        esperar("el aviso de la copia que no se recupera",
                [p["solo_admin"] for p in problemas if "recuperación" in p["titulo"]], [True])
        esperar("y nada quedó tirado en la carpeta",
                [f for f in os.listdir(".") if f.endswith(".verificar")], [])
    finally:
        g.update(originales)
    return fallas


def main():
    carpeta = tempfile.mkdtemp(prefix="pruebas_frenos_")
    try:
        fallas = probar(_cargar_la_logica(carpeta))
        for f in fallas:
            print("   ✗", f)
        print("✅ frenos: todo en verde" if not fallas else f"{len(fallas)} falla(s)")
        return 1 if fallas else 0
    finally:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

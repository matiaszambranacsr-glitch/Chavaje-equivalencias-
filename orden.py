"""En qué orden corren los archivos de la app. Lo leen la app misma y las herramientas.

La app estaba en un solo archivo de 30.800 líneas. Ahora está partida en:

    app.py        lo que corre en cada toque: la configuración de la página, el encabezado, la
                  entrada y la navegación. Después ejecuta la pantalla elegida.
    logica/       todo lo que no es una pantalla: la base, los códigos, las equivalencias, las
                  copias, los proveedores... Se carga UNA vez por proceso, no en cada toque.
    pantallas/    una pantalla por archivo. Corren en cada toque, como corrían antes.

El orden importa igual que antes: cada parte usa sin importarlos los nombres que definen las
anteriores. Este archivo es el que lo dice, en un solo lugar.

Las herramientas (auditar.py, nucleo/generar.py) necesitan ver la app entera en el orden en que
corre: fuente_completa() la arma, y dice de qué archivo y qué línea salió cada renglón.
"""
import os

AQUI = os.path.dirname(os.path.abspath(__file__))

PARTES_DE_LA_LOGICA = [
    "base.py",
    "datos.py",
    "codigos.py",
    "copias_y_mantenimiento.py",
    "mostrador.py",
    "equivalencias_descubiertas.py",
    "importar.py",
    "busqueda.py",
    "salud.py",
    "proveedores.py",
    "calidad.py",
    "descripciones.py",
    "negocio.py",
    "interfaz.py",
    "vehiculos.py",
    "piezas.py",
    "mecanico.py",
]

# En el orden en que estaban: cada una empieza con su «if pagina == PAGINAS[n]:», así que
# correrlas todas en fila es lo mismo que tenerlas escritas una abajo de la otra.
PANTALLAS = [
    "buscador.py",
    "vincular.py",
    "cargar_excel.py",
    "administrar.py",
    "estadisticas.py",
    "whatsapp.py",
    "vehiculos.py",
    "mecanico.py",
]

# En app.py, la línea donde se ejecutan las pantallas. fuente_completa() pone ahí su texto.
MARCA_DE_LAS_PANTALLAS = "# «AQUÍ CORREN LAS PANTALLAS»"


def _leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return f.read()


def fuente_completa():
    """(texto, de_donde): la app entera como si fuera un solo archivo, en el orden en que corre.

    de_donde[i] es (archivo, línea) del renglón i+1 del texto. Arriba de todo va la descripción
    de app.py (su docstring), que es el mapa de las secciones; después la lógica, y después el
    resto de app.py con las pantallas puestas donde se ejecutan."""
    lineas, de_donde = [], []

    def agregar(archivo, texto, desde=1):
        partes = texto.split("\n")
        if partes and partes[-1] == "":
            partes.pop()
        for i, renglon in enumerate(partes, desde):
            lineas.append(renglon)
            de_donde.append((archivo, i))

    app = _leer(os.path.join(AQUI, "app.py"))
    renglones_app = app.split("\n")
    fin_doc = _fin_del_docstring(renglones_app)
    agregar("app.py", "\n".join(renglones_app[:fin_doc]))
    for parte in PARTES_DE_LA_LOGICA:
        agregar(f"logica/{parte}", _leer(os.path.join(AQUI, "logica", parte)))
    marca = next(i for i, r in enumerate(renglones_app) if r.strip() == MARCA_DE_LAS_PANTALLAS)
    agregar("app.py", "\n".join(renglones_app[fin_doc:marca]), desde=fin_doc + 1)
    for pantalla in PANTALLAS:
        agregar(f"pantallas/{pantalla}", _leer(os.path.join(AQUI, "pantallas", pantalla)))
    agregar("app.py", "\n".join(renglones_app[marca:]), desde=marca + 1)
    return "\n".join(lineas) + "\n", de_donde


def _fin_del_docstring(renglones):
    """Cuántos renglones ocupa el docstring de arriba de app.py (con las comillas)."""
    if not renglones or not renglones[0].startswith('"""'):
        return 0
    if renglones[0].count('"""') >= 2:
        return 1
    for i in range(1, len(renglones)):
        if '"""' in renglones[i]:
            return i + 1
    return 0

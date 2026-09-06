# nucleo/ — la lógica sola, para llevarla a otro sistema

Este paquete es la parte de `app.py` que **no depende de Streamlit**: limpiar códigos, leer
listas de proveedor, sacar el código de fábrica de adentro de una descripción, y encadenar
equivalencias entre proveedores.

`app.py` **no cambió**: sigue teniendo su propia copia y anda igual que siempre. Este paquete
es para el otro sistema.

## Qué hay en cada archivo

| archivo | qué resuelve | depende de |
|---|---|---|
| `errores.py` | registro de errores que se deciden ignorar | nada |
| `codigos.py` | limpiar y reconocer códigos; sacar el OEM de la descripción | `errores` |
| `vehiculos.py` | marcas de auto, familias de pieza, medidas y años desde el texto | `errores`, `codigos` |
| `planillas.py` | leer Excel/CSV/PDF y adivinar qué es cada columna | `errores`, `codigos`, `openpyxl` |
| `equivalencias.py` | el SQL recursivo que encadena saltos entre proveedores | `errores`, SQLite |
| `pruebas.py` | las pruebas de todo lo anterior | los demás |

Los cuatro primeros son funciones puras sobre strings y listas: se prueban sin base de datos.
Solo `equivalencias.py` necesita SQLite, y **recibe el cursor por parámetro** — a diferencia de
`app.py`, donde toma uno global. Ese es el único cambio de fondo respecto del original, y está
hecho para que el otro sistema use su propia conexión y su propio manejo de concurrencia.

Dependencias externas: `openpyxl` (Excel) y, si se quieren leer PDF, `pdfplumber`. Nada más.

```bash
python3 -m nucleo.pruebas       # 9 grupos de pruebas, sin Streamlit y sin la app
```

## Uso de punta a punta

```python
import sqlite3
from nucleo import codigos, equivalencias, planillas

filas = planillas.leer_excel("lista_proveedor.xlsx")

# Adivinar qué columna es cada cosa. Ojo con esto: de cinco listas reales, CUATRO no traían
# encabezado, así que hay que deducir mirando los valores y no los títulos.
encabezado = filas[0]
titulos_utiles = sum(1 for x in encabezado
                     if x is not None and str(x).strip() and not str(x).strip()[0].isdigit())
if titulos_utiles >= 2:
    mapa = planillas.adivinar_columnas(encabezado)
else:
    mapa = planillas.adivinar_columnas_por_datos(filas[1:60], len(encabezado))

con = equivalencias.preparar(sqlite3.connect("equivalencias.db"))
cur = con.cursor()
# ... cargar marcas, productos y vínculos con ese mapeo ...
resultados = equivalencias.buscar_por_codigo(cur, codigos.sanitizar("036115561G"))
```

## Lo único que hay que entender antes de tocarlo

**El código de fábrica adentro de la descripción es lo que cruza dos proveedores.** Las listas
de acá casi nunca traen una columna de OEM: de cinco listas reales, ninguna la tenía, y entre
las cinco no compartían prácticamente ningún código. Lo que sí comparten es el código de fábrica
mencionado en el texto (`SENSOR TEMPERATURA Chevrolet ONIX (25186240)`).

**Y eso hay que mirarlo sobre la lista ENTERA, no fila por fila.** `CLA200` (un modelo de
Mercedes) e `IWP065` (un inyector Magneti Marelli) tienen exactamente la misma forma —tres
letras y tres números— y no hay expresión regular que los distinga. Lo que los distingue es en
cuántas filas aparece cada uno: el inyector en 2, el modelo en 15. Por eso el orden correcto es:

```python
# 1) contar sobre TODA la lista
pares = [(descripcion, codigo_de_esa_fila) for ...]
buenos, conteo = codigos.codigos_confiables_de_descripciones(pares)

# 2) recién ahí, fila por fila
oem = [x for x in codigos.extraer_codigos_de_texto(desc, codigo_propio=cod)
       if codigos.sanitizar(x) in buenos]
```

Saltearse el paso 1 llena la base de equivalencias falsas, y el daño **crece al cuadrado**: un
texto que aparece 130 veces en una lista y 6 en otra declara 780 pares de repuestos
"equivalentes" que no tienen nada que ver.

El `codigo_propio=` del paso 2 tampoco es opcional. Muchas listas exportan perdiendo un espacio,
y la fila `52031FISPA` termina con la descripción `FICHA DE INYECCION 52031Ficha para...`: sin
pasarle el código de la fila, de ahí sale `52031Ficha` como si fuera un código de fábrica. Sobre
una lista real eran 4.443 de 5.063 filas.

## Por qué `extraer_codigos_de_texto` descarta tanto

Cada cosa que descarta está ahí porque hizo daño en una lista real. Lo que rechaza:

- **rangos de años** (`1998-2006`) — eran 163 de los 224 "códigos" que dos listas compartían;
- **listas de modelos** (`205-206-306`, `A3-A4-A6`, `4-RUNNER`);
- **motorizaciones** (`TU5JP4`, `DW10BTED4`, `2GD-FTV`) — juntaban un termostato con un sensor
  de RPM, y una bujía con un kit de embrague;
- **medidas de correa** (`6PK1555`) — unían una bomba de agua con una correa suelta;
- **el código de la propia fila con una palabra pegada** (ver arriba);
- **HTML** metido en la descripción (`0001115005<br>BOSCH`) y **texto roto al exportar** (`118?CREF`).

Antes de aflojar cualquiera de esos filtros, corré `python3 -m nucleo.pruebas`: los casos que
dicen "NO debía sacar nada" son justamente esos, y están escritos con descripciones reales.

## Las dos formas de llegar de un producto a otro

`buscar_por_codigo` encadena por dos caminos, y hacen falta los dos:

1. **por un vínculo cargado** — alguien puso los dos códigos en la misma fila. Cuesta un salto.
2. **porque es el mismo código bajo otra marca** — no cuesta salto, porque no es una suposición:
   es el mismo número. Este es el caso más común entre proveedores distintos, y es el que
   faltaba cuando la búsqueda "solo relacionaba dentro del mismo proveedor".

El camino 2 **no se aplica a códigos genéricos**: un `1234` de una marca y un `1234` de otra son
casi seguro piezas distintas, porque los catálogos numeran de corrido. El corte va en los
puramente numéricos de menos de 6 dígitos y en cualquier código de menos de 4 caracteres.

## Regenerar el paquete

Los archivos se generan sacando el texto exacto de `app.py`, para que no haya forma de que la
app y el paquete digan cosas distintas por una transcripción:

```bash
python3 nucleo/generar.py && python3 -m nucleo.pruebas
```

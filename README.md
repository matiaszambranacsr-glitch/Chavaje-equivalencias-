# Chavaje — buscador de equivalencias de repuestos

Una app de mostrador: buscás el código que te pide el cliente y te dice qué otros códigos, de
qué proveedores, son el mismo repuesto. Corre con Streamlit sobre una base SQLite.

## Qué es cada archivo

| archivo | qué es |
|---|---|
| `app.py` | La aplicación. Es un solo archivo a propósito: se despliega tal cual, sin paquete ni rutas que configurar. Arranca con un mapa de sus secciones. |
| `nucleo/` | La misma lógica pero **sin Streamlit**, para poder usarla desde otro sistema. Se genera desde `app.py`. |
| `auditar.py` | Revisa `app.py` y busca los errores que ya pasaron alguna vez. Correlo antes de subir un cambio. |
| `requirements.txt` | Lo que hay que instalar. |
| `Equivalencias` | El prototipo original, de antes de `app.py`. No lo usa nadie; queda por si querés mirarlo. Se puede borrar. |

## Antes de subir un cambio

```bash
python3 auditar.py app.py        # tiene que dar ERROR 0
python3 nucleo/generar.py        # regenerar el paquete desde app.py
python3 -m nucleo.pruebas        # tiene que decir "todo en verde"
```

El auditor no es un linter genérico: cada control salió de un error que rompió la app de
verdad, y el mensaje cuenta cuál fue. Si marca algo, conviene leerlo antes de descartarlo.

## Cómo encontrar las cosas en `app.py`

Son 21.000 líneas, así que está partido en secciones con un encabezado de tres líneas:

```
# ============================================
# NOMBRE DE LA SECCIÓN
# ============================================
```

Buscando `# ===` se salta de una a otra. El índice completo está en el docstring del principio
del archivo, y el auditor avisa si ese índice y las secciones dejan de coincidir.

El orden va de lo más básico a lo más específico: primero la conexión y el esquema, después el
manejo de códigos, después las equivalencias, y las pantallas al final.

## Lo que conviene entender antes de tocar las equivalencias

**Las listas de proveedor de acá casi nunca traen una columna de código de fábrica.** Sobre
cinco listas reales (89.852 productos) ninguna la tenía, y entre todas no compartían
prácticamente ningún código. Lo único que las une es el código de fábrica escrito adentro de
la descripción: `SENSOR TEMPERATURA Chevrolet ONIX (25186240)`.

Sacar códigos de un texto es adivinar, y adivinar de más hace más daño que no adivinar: un
falso código no agrega un resultado equivocado, **fusiona dos familias enteras de repuestos**.
Por eso `extraer_codigos_de_texto()` descarta tanto —rangos de años, motorizaciones, modelos,
medidas— y por eso hay un filtro por repetición: un código de fábrica real aparece una o dos
veces en una lista; lo que se repite más es texto.

Antes de aflojar cualquiera de esos filtros, corré `python3 -m nucleo.pruebas`: los casos que
dicen «NO debía sacar nada» están escritos con descripciones reales de esas listas.

## Base de datos

SQLite en modo WAL, con **una conexión por sesión** para que puedan usar la app dos personas a
la vez. Dos consecuencias que ya causaron problemas y conviene tener presentes:

- **No se puede reemplazar el archivo `.db` a mano.** Si hay otra sesión abierta, su `-wal`
  sobrevive y se aplica encima de la base nueva: quedan mezcladas dos bases. Para restaurar se
  usa la API `backup()` de SQLite, que escribe a través de la base (ver `restaurar_backup()`).
- **Cuidado con los `IN (?, ?, …)` largos.** SQLite tiene un tope de variables por consulta que
  en muchas instalaciones es 999. Para listas que crecen con el catálogo hay que usar
  `en_tandas()`, que además tiene en cuenta si la lista aparece más de una vez en la consulta.

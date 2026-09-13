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

## Quién puede hacer qué

La app **deja entrar sin contraseña a propósito**: el botón «Continuar» del login te mete
igual, porque en el mostrador se usa así. La consecuencia es que la protección no está en la
puerta sino en cada acción: lo que borra o reescribe va adentro de un
`if pedir_password_admin("para qué"):`.

Eso se olvida fácil, y se olvidó: el candado estaba en «eliminar una marca» y faltaba en
«separar las descripciones pegadas», que reescribe el catálogo entero. El auditor ahora marca
como ERROR cualquier función destructiva llamada desde una pantalla sin ese candado. Si
agregás un botón que borra algo, ponele el candado o el auditor no te deja subir.

Hay dos candados, y no son lo mismo:

- `pedir_password_admin("para qué")` — para lo que borra o configura.
- `pedir_password_operador_o_admin("para qué")` — para el trabajo de mostrador: hoy, tocar el
  precio y el stock. Alcanza con la contraseña de operador, y como el nivel queda en la
  sesión se pide una vez por turno, no en cada producto.

## Secrets de Streamlit

Se leen con `secretos_app()`, nunca con `st.secrets` directo. El atributo existe siempre pero
LEERLO revienta si el servidor no tiene un `secrets.toml`, así que el `if hasattr(st, "secrets")`
que había no protegía nada: en una instalación nueva, apretar «Ingresar con contraseña» tiraba
la excepción en pantalla. El auditor marca cualquier vuelta a esa forma.

## La pantalla de vehículos

«Buscar por auto» no sale de un catálogo comprado: sale de leer las descripciones de tus
propias listas. Tres cosas que conviene saber antes de tocarla:

- **Una descripción nombra varios autos** («BUJIA Ford Escort - VW Gol - Kombi»): son el 19%
  de las descripciones reales. Por eso existe `marcas_vehiculo_en()`, que devuelve todas, y el
  producto aparece en el catálogo de cada una. `separar_por_marca_vehiculo()` devuelve solo la
  primera y se usa donde hace falta una sola.
- **Las listas abrevian** («VW», «CHEV», «PEU») y **escriben en minúsculas**. Las abreviaturas
  están en `MARCAS_VEHICULO` y se unifican con `ALIAS_MARCA_VEHICULO`; el reconocimiento va en
  IGNORECASE. Si agregás una abreviatura, contá antes cuántas descripciones reales la usan
  como palabra suelta: una de dos o tres letras se mete adentro de cualquier cosa.
- **El número que muestra el desplegable tiene que ser el que devuelve la pantalla.** Eran dos
  cálculos distintos y no coincidían: MAN ofrecía 749 productos y daba 3.

## Base de datos

SQLite en modo WAL, con **una conexión por sesión** para que puedan usar la app dos personas a
la vez. Tres consecuencias que ya causaron problemas y conviene tener presentes:

- **Restaurar un backup trae el esquema del día que se hizo.** Por eso `restaurar_backup()`
  vuelve a correr `crear_esquema()` después de copiar: sin eso, un backup anterior a una
  columna nueva la hace desaparecer, y no vuelve hasta que alguien reinicie la app. Está
  probado: con un backup previo a la columna `resumen`, la papelera se caía al abrirla.
- **No se puede reemplazar el archivo `.db` a mano.** Si hay otra sesión abierta, su `-wal`
  sobrevive y se aplica encima de la base nueva: quedan mezcladas dos bases. Para restaurar se
  usa la API `backup()` de SQLite, que escribe a través de la base (ver `restaurar_backup()`).
- **Está en autocommit: cada sentencia se confirma sola.** Sirve para que la importación de
  una persona no se mezcle con la de otra, pero significa que una operación de varios pasos
  cortada a la mitad deja la base a medias. Cuando varias sentencias tienen que valer todas o
  ninguna va `with transaccion():` (ver la sección *TODO O NADA* de `app.py`). El auditor marca
  las funciones que escriben en dos tablas y no lo usan.
- **Cuidado con los `IN (?, ?, …)` largos.** SQLite tiene un tope de variables por consulta que
  en muchas instalaciones es 999. Para listas que crecen con el catálogo hay que usar
  `en_tandas()`, que además tiene en cuenta si la lista aparece más de una vez en la consulta.

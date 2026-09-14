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

## Botones que piden contraseña

Van con `candado(motivo, st.button(...), "clave")`, NUNCA con
`if st.button(...): if pedir_password_admin(...):`. La forma vieja no funciona y es difícil de
ver: Streamlit vuelve a correr la página entera en cada interacción, `st.button()` devuelve
True solo en la corrida del clic, y cuando llega la contraseña ya devuelve False — el `if` de
afuera no entra y la acción nunca corre. `candado()` anota el pedido en la sesión para que
sobreviva a esa segunda corrida. El auditor acepta las dos formas, así que esto hay que
respetarlo a mano.

## Pantallas con secciones

Nada de `st.tabs` en pantallas con botones: no recuerda qué pestaña estabas mirando y cada
clic te devuelve a la primera. Va un `st.radio` con `key` en session_state, como la navegación
principal y como Mantenimiento.

## El cursor es uno solo

`c` es un cursor compartido. Nunca poner un `c.fetchone()` en la misma expresión que una
llamada a otra función de la app: Python evalúa de izquierda a derecha, la función hace sus
consultas sobre el mismo cursor y el fetch termina leyendo otro resultado. Fetch primero, a
una variable, y después llamar. El auditor lo marca.

## Kits

El mostrador pregunta «¿y el kit con las bujías?», así que el buscador lo ofrece solo:
`kits_que_lo_traen()` y `que_trae_este_kit()`. No hay nada cargado a mano — cuando el proveedor
arma un kit escribe adentro de la descripción los códigos de lo que trae
(`KIT CAB Y BUJ (LEIHTT06SC/LSPKR6E)`), y eso alcanza.

Dos filtros para no inventar: el kit tiene que tener OTRA descripción que el producto (varias
filas del catálogo son el mismo kit cargado con distintos códigos) y el código tiene que tener
al menos seis caracteres. Y se muestra una fila por kit, la que se puede vender: con precio y
con stock.

## Comodines del SQL

Todo `LIKE` que reciba texto de una persona o un código va con `como_texto_en_like()` y
`ESCAPE '\'`. En SQL `%` es «cualquier cosa» y `_` es «un carácter cualquiera»: sin escaparlos,
buscar «100%» devolvía 200 filas al azar. Y ojo con el patrón vacío — `LIKE '%%'` coincide con
todo, que es lo que pasaba al buscar un solo símbolo.

## Decidir si dos repuestos son la misma clase de pieza

Tres funciones, y conviene no confundirlas:

- `clasificar_repuesto()` — la familia para MOSTRAR (el filtro de categoría de la pantalla).
  Siempre devuelve una. Acepta el plural de cada clave.
- `familia_para_comparar()` — la familia para DECIDIR. Devuelve «Sin clasificar» cuando la
  descripción es un kit de varias piezas, porque «KIT CAB Y BUJ» trae cables y bujías y
  elegirle una sola familia es un sorteo que después castiga vínculos correctos.
- `_nombre_de_la_pieza()` — las palabras del nombre, sin los números de parte (eran el 73% de
  las palabras que entraban) y con las abreviaturas del proveedor expandidas: CAB=CABLE,
  BUJ=BUJIA, JTA=JUNTA.

Si tocás alguna, medí contra los vínculos reales antes y después. La referencia de hoy, sobre
24.774: «nombre muy distinto» 608, «rubro distinto» 116.

## Cuando mejorás `sanitizar()`

`codigo_clean` es por donde busca la app, y se calcula UNA vez, al importar. Así que cada
arreglo en `sanitizar()` deja atrás a las filas que ya estaban: siguen buscándose por el valor
viejo y no aparecen ni escribiendo el código exacto de la caja.

Por eso existe Mantenimiento → **«🔎 Códigos que el buscador no encuentra»**, que compara lo
guardado contra `sanitizar(codigo_raw)` y los recalcula. Después de tocar `sanitizar()`, mirá
ahí. Y no rompas la propiedad de la que depende: limpiar lo ya limpio tiene que dar lo mismo
(hay una prueba en `nucleo/pruebas.py`).

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

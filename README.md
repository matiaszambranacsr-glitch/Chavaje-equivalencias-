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

## El código de barras tiene su propia columna

`productos.codigo_barras`. Parece un detalle de esquema y es el origen del problema de abajo.

Antes no existía, y la única forma de dejar el EAN buscable era cargarlo como código de
fábrica — `adivinar_columnas()` lo hacía solo cuando la lista no traía OEM. La intención era
buena (escanear la caja y encontrar el repuesto) pero el lugar estaba mal: **la columna de OEM
es por donde se cruzan los proveedores**, y el código de barras es de un proveedor y de nadie
más. Cada fila quedaba con una equivalencia que no lleva a ningún lado.

Con columna propia se consiguen las dos cosas:

- `buscar_por_codigo()` arranca con `WHERE codigo_clean = ? OR codigo_barras = ?`, así que
  escanear trae el repuesto y toda su red. Los orígenes (`origenes`) se buscan con el mismo
  criterio: si no, la fila escaneada saldría como un resultado más y no como «el buscado».
- El trigger de `busqueda` incluye `codigo_barras`, así que la búsqueda por texto también lo
  encuentra. Ese trigger se **borra y se vuelve a crear** en cada arranque, no con
  `IF NOT EXISTS`: la expresión cambió, y con `IF NOT EXISTS` una base ya creada se quedaba
  con la versión vieja sin ningún error a la vista.

Para lo que ya estaba cargado, **Mantenimiento → 🩺 Estado** tiene el arreglo:
`codigos_de_barras_mal_cargados()` + `mover_codigos_de_barras_a_su_columna()`. La decisión se
toma **por lista y no por código**, porque un número de 13 dígitos suelto puede ser un código
de fábrica de verdad que todavía no tiene nadie más; lo que delata al EAN es el conjunto —
todos con el mismo prefijo de empresa. Y solo toca los que cuelgan un solo producto: si
colgara dos, algo une y no se toca.

Sobre la base real: mueve 8.319 códigos de barras a su columna, borra 8.319 productos fantasma
de «OEM / FABRICA» y 8.319 vínculos falsos. El catálogo pasa de 61.574 a 53.255 productos sin
perder un solo dato — el número sigue estando, en el lugar que le corresponde.

## Una equivalencia que no lleva a ningún lado no es una equivalencia

El error más caro de todo esto no rompe nada: la importación sale bien, se cargan miles de
vínculos, y ninguno sirve.

Pasa cuando la columna que se mapeó como «código de fábrica» **no es el código de fábrica**.
El caso real: la lista de MOTORARG entró con la columna del **código de barras**. Son 8.076
números que empiezan todos con `7793960` —el prefijo de GS1 de esa empresa— y que ningún otro
proveedor va a traer nunca. Quedaron 8.652 productos con una equivalencia cargada que cuelga
un solo producto: el mismo.

Medido sobre la base real (61.574 productos, 24.774 vínculos): de los 21.828 códigos de
fábrica cargados, **solo 2.483 unen dos productos o más**. Los otros 19.251 son callejones
sin salida, y arrastran a 12.060 productos —el 20% del catálogo— que en la búsqueda mostraban
«🟢 directo / 🟢 sólida / Exacta» apuntando a sí mismos.

Tres cosas lo cubren ahora, y conviene no aflojar ninguna:

- `buscar_por_codigo()` cuenta a cuántos productos se cuelga cada código de fábrica del
  resultado. Los de grado 1 se marcan `_sin_salida`, la columna **Cadena** lo dice con todas
  las letras, y no llevan confianza ni nivel. El Buscador cuenta las equivalencias **de
  verdad** aparte del total de filas.
- `columna_es_codigo_de_barras()` lo detecta **antes de importar**: 12 a 14 dígitos, todo
  números, y el mismo prefijo en el 70% de la muestra. Avisa en rojo en la vista previa.
- `listas_que_no_cruzan()` (Mantenimiento → 🩺 Estado) lo contesta para lo que ya está
  cargado, con el motivo escrito. La columna que importa es **«Cruzan con otra marca»**: si
  dice 0, esa lista no sirve para responder «¿qué otra marca me sirve?».

La cuenta que vale no es cuántas equivalencias tiene una lista, es **a cuántos productos de
otro proveedor llega**.

## El modelo con la cilindrada pegada

`CORSA1.4`, `AMAROK2.0`, `HILLUX2.4`, `Siena1.0`. Sale de la exportación del proveedor, que se
come el espacio, y hace daño dos veces: el modelo deja de ser reconocible como modelo, y
—peor— eso tiene forma de código, así que entraba como código de fábrica. En la base real el
`CORSA1.4` llegó a colgar un tubo, una correa multicanal y un sensor MAP: tres repuestos que no
tienen nada que ver, hermanados porque las tres descripciones nombran el mismo auto.

Se arregla en los dos lados: `separar_texto_pegado()` los despega, y
`extraer_codigos_de_texto()` los rechaza aunque lleguen pegados (va en `formas_solo_texto`, o
sea que ni un «REF ORIG» adelante los rescata).

**Se piden cuatro letras antes del número, y ahí está todo el cuidado.** Con menos se rompen
las designaciones de zócalo y las medidas, que tienen la misma forma con una o dos letras:
`W2x4.6d`, `BX8.2d`, `SV8,5-8`, `M14X1.5X42`, `6mmx8mm x7,89mm`. Medido sobre las 53.255
descripciones reales: separa 158 y no toca ninguna de esas.

## Las sugerencias por descripción: dos preguntas, no una

Cuando ninguna de las dos listas trae el código de fábrica —el caso de Taranto, que no lo
trae en ninguna columna— lo único que queda es comparar las descripciones. Eso lo hace
`firma_de_producto()` + `firmas_compatibles()`, y tiene que contestar **dos** preguntas:

    pieza       QUÉ PIEZA ES         JUNTA, TAPA, CILINDRO
    aplicacion  PARA QUÉ AUTO ES     FOCUS, FIESTA, SIGMA, 16V
    autos       la marca del auto    FORD

Estaban en una sola bolsa (`nucleo`) y la regla era «que compartan dos palabras», sin mirar
cuáles. Las dos formas de equivocarse salían de ahí:

- dos **modelos** compartidos daban por equivalentes piezas distintas: «Junta Salida de
  Escape R9 R11 R19» con «Junta Tapa de Válvulas R9 R11 R19»;
- dos **nombres de pieza** compartidos daban por equivalentes aplicaciones distintas:
  cualquier junta de tapa de cilindros con cualquier otra, de cualquier motor.

Ahora tienen que coincidir las dos cosas, y del lado de la pieza con dos condiciones:
**al menos dos palabras** (con una sola alcanzaba «JUNTA», que está en el 7,5% del catálogo)
y **la descripción más pobre entera adentro de la otra** — que es lo único que separa «Tapa
de VÁLVULAS» de «Tapa de CILINDROS», porque la palabra en la que se diferencian es
justamente la que dice cuál de las dos es.

Tres listas de palabras sostienen esto y no hay que mezclarlas:

    MARCAS_DE_REPUESTO    BOSCH, NGK, VALEO       no dicen ni la pieza ni el auto
    PALABRAS_DE_CONTEXTO  PICK, UP, CAMION, CARGO qué vehículo es → van con la aplicación
    PALABRAS_NO_MODELO    todo lo anterior + JUNTA, TAPA, CILINDROS, BOMBA...

`PALABRAS_NO_MODELO` menos las dos primeras **es** el vocabulario de pieza. El bug más caro
que tuvo esto fue usar `PALABRAS_NO_MODELO` entera para filtrar el núcleo: el núcleo, que
existe para guardar qué pieza es, tiraba exactamente las palabras que lo dicen y se quedaba
con los modelos de auto.

Otras tres cosas que parecen detalles y no lo son:

- **El punto que pega dos palabras.** «Jta.Tapa Cilind.Ford Focus» daba las palabras
  `JTA.TAPA` y `CILIND.FORD`, así que ese producto quedaba sin ninguna marca de auto. Se
  separa solo entre dos letras: entre números el punto es parte del dato (1.6, 278.897).
- **Las abreviaturas.** `ABREVIATURAS_DE_PIEZA` ya existía y la firma no la usaba: JTA/JUNTA,
  CILIND/CIL/CILINDROS, VAL/VALV. Al expandir hay que sumar las formas en el conteo de
  palabras genéricas, si no la forma expandida parece rarísima y pasa por «específica».
- **El orden de los candidatos.** De cada producto se guardan solo los mejores, y «mejor» era
  cuántas MARCAS de auto compartían — casi siempre 1, así que desempataba el azar. Ahora
  `fuerza_de_la_coincidencia()` pone primero el modelo y la cilindrada, que es lo que
  discrimina.

Medido sobre las listas reales de Illinois (6.900) y Taranto (8.708), las dos de juntas:
las sugerencias pasan de 59 a 1.411, y el error sistemático de proponer una junta de tapa de
válvulas contra una de tapa de cilindros queda en 13 de 1.411 (0,9%).

## Un número de catálogo no es un código de fábrica

La búsqueda salta de una marca a otra cuando dos productos tienen **el mismo número**. Es el
atajo más productivo que tiene —el proveedor A pone `036115561G` en su columna OEM y el
proveedor B lo usa como su propio código— y también el más fácil de arruinar.

El corte está en la forma del código, y el dato lo decide. En la base real hay 542 códigos que
aparecen en dos marcas o más, y son dos poblaciones que no se mezclan:

    288 numéricos de 10 dígitos  ┐
     36 numéricos de 8           ├─ códigos de fábrica: es el mismo repuesto
     10 numéricos de 12          │
    185 con letras               ┘
     19 numéricos de 6 y 7       ─── casualidad: los 19, revisados uno por uno

Los 19 son siempre el mismo choque: JL numera sus filtros de corrido y Taranto sus juntas
también. El `310007` de JL es un prefiltro de Focus; el de Taranto, una junta de tapa de
cilindros de un Ford MAX. Por eso el salto pide **8 dígitos** cuando el código es solo números
(antes pedía 6), y sigue pidiendo 4 caracteres para cualquier código.

Las dos filas con ese número **se siguen mostrando** —es el número que se escribió— pero
`el_mismo_numero_en_dos_piezas()` avisa que no son la misma pieza. Ese aviso también se decide
por la forma del código, no por la descripción: la primera versión comparaba los nombres de las
piezas y marcaba 143 de los 542, porque el mismo repuesto se describe distinto en cada lista
(`0280130039` es «BULBO DE TEMPERATURA DE AGUA» para uno y «SENSOR INYEC» para el otro). Con la
forma del código marca 19 de 19, sin un solo falso.

## Cuando alguien vende el código, es un código

`extraer_codigos_de_texto()` descarta por forma las motorizaciones (`MR20DE`, `Z18XER`,
`XU10J4R`), y esa regla se llevaba puestos códigos de repuesto reales que tienen la misma
forma: sobre los 39.746 códigos del catálogo, 724 —bujías `CT5FMR`, capuchones `RB9009B`,
juntas `TC-936-MG`—.

El desempate es el catálogo: si el token coincide con el código de un producto de una lista
de **PROVEEDOR**, es un código, porque una motorización no la vende nadie. Se pasa con
`codigos_conocidos=codigos_del_catalogo(version_del_catalogo())`.

Dos límites que están puestos a propósito y no hay que sacar:

- **Solo códigos de marcas PROVEEDOR**, nunca los de «OEM / FABRICA». Muchos de esos los creó
  una importación anterior leyendo una descripción: si contaran, la basura de ayer se
  legitimaría sola. En la base real hay `DS3-BMW`, `i30-KIA` y `gol1.0-golf` cargados como
  códigos de fábrica.
- **No afloja el largo mínimo de los códigos de solo números.** La descripción
  `CONECTOR PARA MANGUERA 260035 16 X 5 16` trae la medida 5/16 pegada al código 26003, y
  `260035` existe en otra lista como una junta de colector. Aflojando el largo, esa medida
  rota unía un conector de manguera con una junta de admisión.

Medido: rescata 15 códigos (todos bujías NGK/Bosch, que es justo lo que cruza una bujía de un
proveedor con la de otro), pierde 0, y las 30 motorizaciones conocidas siguen afuera.

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

## Antes de desplegar: la copia de arranque

**Streamlit Cloud borra el disco en cada redespliegue.** Lo único que sobrevive son los
archivos del repositorio, así que si no hay un `datos_iniciales.db` subido, la app arranca
VACÍA y hay que volver a importar todas las listas.

El paso, cada vez que se va a desplegar algo importante:

1. En la app: **📊 Estadísticas → 💾 Backup y config → descargar el backup**.
2. Subir ese archivo al repositorio con el nombre exacto `datos_iniciales.db`.
3. Recién ahí, mergear.

`_restaurar_desde_semilla()` lo usa solo si la base está vacía, así que no pisa nada.

Ojo con una trampa que ya estaba: el `.gitignore` tenía `*.db`, que ignoraba también a
`datos_iniciales.db`. Se hacía `git add`, git no se quejaba, el archivo no subía, y el
problema aparecía recién al redesplegar. Ahora hay una excepción explícita.

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

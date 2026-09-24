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
python3 revisar_con_gemini.py    # opcional: una segunda opinión sobre el diff
```

Uno por uno y mirando la salida de cada uno. Encadenarlos con `&&` y quedarse con lo último
que imprime la consola ya dejó pasar un paquete `nucleo` roto: el `&&` se enganchó de un `head`
que terminó bien y el fallo de las pruebas no se vio.

El auditor no es un linter genérico: cada control salió de un error que rompió la app de
verdad, y el mensaje cuenta cuál fue. Si marca algo, conviene leerlo antes de descartarlo.

El último es de otra clase y no bloquea nada: ver *Una segunda opinión, de otro modelo*.

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

## Las capas de `nucleo/` van en un solo sentido

    errores.py  ←  codigos.py  ←  vehiculos.py  ←  planillas.py
                                  equivalencias.py

`codigos.py` **no puede** depender de `vehiculos.py`. Vale la pena escribirlo porque es fácil
tropezar: al revisar los códigos de fábrica cargados aparecieron cuatro que son en realidad la
marca del auto con un número pegado (`Peugeot106`, `Renault11-R`, `Cummins-6.4`), y el arreglo
natural —rechazarlos en `extraer_codigos_de_texto()` usando `MARCAS_PARA_DESPEGAR`— crea un
import circular.

Las dos salidas son peores que el problema: duplicar la lista de marcas en `codigos.py` (dos
listas que se separan con el tiempo, que es justo lo que este README pide no hacer) o mover
`extraer_codigos_de_texto()` a `vehiculos.py` (donde no pertenece). Con cuatro códigos de
46.644 no vale: quedan, y la pantalla de puentes falsos los muestra.

## Dos pantallas no pueden contar distinto el mismo producto

El buscador dice «este código todavía no tiene equivalencias con otra marca» cuando lo único
que aparece es su código de fábrica. Administrar, en cambio, lo daba por resuelto, porque en
la tabla de equivalencias **sí** tiene una fila. Mismo producto, dos respuestas.

`contar_con_equivalencia_muerta()` cierra ese hueco: son **12.060** productos además de los
31.947 que no tienen ninguna. La diferencia entre «el 48% del catálogo no cruza con nadie» y
el 68% real.

Un vecino cuenta como útil si es el producto de **otro proveedor** —ahí la equivalencia ya
está hecha, aunque ese vecino no tenga ningún otro vínculo— o si es un código de fábrica que
cuelga algo más que a mí. Esa primera mitad es fácil de olvidar y da 201 de diferencia.

**Y no se suman a lo que borra `depurar_huerfanos()`, a propósito.** No son filas de más:
tienen su código de fábrica cargado y se encadenan solos el día que otro proveedor traiga ese
mismo número. Lo que hace falta con ellos es otra lista, no borrarlos — y la pantalla lo dice.

## Un tope que no ahorra nada solo esconde resultados

`sugerir_entre_todas_las_marcas()` recorre el catálogo entero y propone pares. Tenía un tope de
600 y cortaba de verdad: con Illinois cargada salen **787** y se veían 600, sin que nada lo
dijera. Y el tope no ahorraba tiempo — el recorrido cuesta 19 s con tope o sin él, porque lo
caro es armar el índice y comparar, no guardar el resultado.

Antes ya había pasado lo mismo con el tope en 200: de 284 pares reales se veían 84. Es el
mismo error dos veces, así que ahora el tope es una constante (`TOPE_SUGERENCIAS_TODAS`) y
**la pantalla avisa cuando se llega**.

La misma idea vale para las otras cotas de la app: el LIMIT 400 de la búsqueda avisa, el tope
de 4.000 productos por comparación avisa, y el de saltos avisa. Una cota que corta en silencio
es indistinguible de «no hay más».

## `st.cache_data` no quiere decir gratis

Una función cacheada tiene que decidir si el caché sigue vigente, y acá el testigo es
`version_del_catalogo()`: un `COUNT(*) + SUM(LENGTH(descripcion))` sobre la tabla entera.
Después hay que deserializar lo guardado. Son 34 ms — nada, hasta que la llamada queda adentro
de un bucle.

La pantalla de **Equivalencias sugeridas** tardaba **37 segundos** después de importar Illinois.
De esos, 13 eran `cuantas_veces_aparece_cada_palabra()` llamada una vez por vínculo desde
`evidencia_cruzada()`: 400 recorridas completas de `productos` para volver a leer el mismo
diccionario de 100.000 palabras. Se calcula una vez en `analizar_lote_pendiente()` y se pasa
hecha. **37 s → 4,1 s**, y la función sola de 14 s a 1,4 s.

El control 24 del auditor lo busca solo: una función cacheada llamada adentro de un bucle **sin
recibir nada que dependa de la vuelta**. Esa última condición es la que lo hace usable —
`modelos_de_marca(marca, _version_cat)` adentro de un bucle está bien, porque el testigo ya se
calculó afuera y la marca cambia en cada vuelta.

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

## El dígito verificador: la lista que el prefijo no agarraba

`columna_es_codigo_de_barras()` reconocía un EAN cargado como código de fábrica porque **todos
arrancan igual** — el prefijo de empresa de GS1. Funciona con una lista de un solo fabricante,
que es el caso de MOTORARG. Pero un revendedor que trae productos de veinte fábricas tiene
veinte prefijos distintos y ninguno llega al 70%: esa lista pasaba entera, sin aviso, y dejaba
miles de equivalencias muertas.

La segunda señal es la cuenta de GS1: los dígitos alternando peso 1 y 3, y el verificador es lo
que falta para llegar a la decena. Medido sobre la base real, separa perfectamente:

    MOTORARG   8.319 códigos largos que son EAN      8.319 cierran  (100%)
    FISPA      117 códigos de fábrica largos             16 cierran  (13%, lo que da el azar)
    JL         3 idem                                     0 cierran

Con eso alcanza para detectar la lista de prefijos mezclados sin marcar de más — probado: FISPA
y JL siguen dando «no es una columna de códigos de barras».

El mismo dígito sirve en otros dos lugares:

- **Escaneando**: si no cierra, el número está mal leído o mal tipeado, y conviene decirlo antes
  de que alguien salga a buscar un código que no existe.
- **Buscando**: si lo que se escaneó son los 12 dígitos sin el verificador, el que está cargado
  es el de 13. Ese dígito no hay que adivinarlo, se calcula.

**La trampa del DUN-14.** El código de la caja tiene 14 dígitos, y la primera versión de esto lo
trataba como «un EAN-13 con un dígito de agrupación adelante»: sacarle el primero y hacer la
cuenta de trece. Da otro número. Sobre la lista real, 21 códigos de caja de MOTORARG aparecían
como mal copiados **estando perfectos** — y como la pantalla que los muestra dice «el escáner no
los va a encontrar», habría mandado a alguien a revisar 21 cajas que están bien. Lo que dice la
norma es completar con ceros a la izquierda hasta trece dígitos y hacer **una sola cuenta** para
los cuatro largos (EAN-8, UPC-A, EAN-13 y DUN-14). Hay prueba de los cuatro.

Un detalle que parece menor y no lo es: `codigo_de_barras_cierra()` devuelve **`None`** —no
`False`— cuando el largo no es de código de barras. «Este código está mal copiado» y «esto no
es un código de barras» son cosas distintas, y confundirlas haría que la app acuse de error a un
código de fábrica que nunca pretendió ser un EAN.

## El prefijo del código de barras dice el país, gratis

Los tres primeros dígitos de un EAN los asigna GS1 y son públicos: no hay que consultar nada ni
pagarle a nadie. `pais_del_codigo_de_barras()` los traduce. Sirve en dos lugares distintos:

- **Escaneando en el mostrador**: «el código lo registró una empresa de Argentina» contesta sola
  la pregunta de si el repuesto lo consigue un proveedor local o hay que traerlo. Ojo con lo que
  dice de verdad: es el país de **quien registró el código**, no el de la fábrica.
- **Mirando una lista entera**: la tabla de códigos de barras mal cargados mostraba «Empiezan
  con: 7793960…», que es una tira de dígitos. Ahora dice además **Argentina**, y el aviso de la
  vista previa de la importación —el único momento en que el error se arregla barato— también.

Y hay prefijos que **no son un país**: 020-029 y 200-299 son de uso interno del comercio (los
que imprime una balanza), 977-979 son revistas y libros, 05x y 98x-99x son cupones. Si un
escaneo cae ahí, ese número no identifica ningún repuesto y la app lo dice en vez de contestar
«no está cargado», que manda a buscar algo que no existe.

Una trampa que ya está probada y conviene no volver a pisar: **el país se lee del código
entero, no del prefijo común de la lista**. Un UPC-A de 12 dígitos es un EAN-13 con un cero
adelante que no está escrito, así que cortando el arranque tal como viene, «045496…» cae en
040-049 —uso interno— cuando en realidad es 004, Estados Unidos. Por eso
`pais_de_estos_codigos()` recibe los códigos completos y no el prefijo que devuelve
`columna_es_codigo_de_barras()`.

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

## Lo que se pega al código, y lo que no es un código

Tres cosas distintas que terminaban todas en la columna de códigos de fábrica:

- **La marca pegada al número.** `BOSCHF1003`, `MPFIMARELLIF1011`, `MAGNETI MARELLIFORDF1101`.
  `MARCAS_PARA_DESPEGAR` ya despegaba las marcas de AUTO; ahora también las de **repuesto**
  (`MARCAS_DE_REPUESTO`) y las siglas de inyección que se pegan igual (`MPFI`, `TBI`, `SPI`).
- **El camión.** `F14000`, `F4000`, `F12000`. El F14000 estaba uniendo un **filtro de
  combustible** con un **cilindro maestro**, y el F4000 un filtro con un sensor de nivel.
- **La motorización.** `4BTA3.9`, `6BTA5.9`, `6CTA8.3` — cilindros + familia + litros.

Para los dos últimos se probó primero la regla general —descartar lo que aparece en muchas
descripciones— y **no sirve**: los mejores puentes que tiene la base son las tablas de Bosch,
donde un mismo número de arranque está en 84 descripciones. La forma sí los separa: `^F\d{3,5}$`
y `^\d[A-Z]{2,4}\d[.,]?\d?$` le pegan a **0** de los 46.644 códigos de proveedor.

Medido sobre las 46.644 descripciones: saca **35** códigos inventados y **recupera 6** que
estaban enterrados adentro del nombre de la marca (`0250202025`, `K20178X30XSA`, `4679625`).

## Uno adentro del otro no es una equivalencia

La bujía está adentro del «KIT CAB Y BUJ», la bomba de agua adentro de «DISTRIBUCION C/BOMBA»,
el filtro de la bomba de nafta cita el mismo número de Bosch que la bomba. Los rubros no
coinciden y el vínculo terminaba en la pila roja como si fuera un error.

No lo es: la relación es **de verdad**, solo que no es de intercambio — no se puede vender una
en lugar de la otra. Sobre los 208 vínculos cargados con rubros distintos, **126 son de esta
clase**. `_uno_trae_al_otro()` lo dice con todas las letras, y el buscador ofrece el kit igual.

Tres detalles que costaron:

- **El código con la marca pegada atrás.** El proveedor se llama `LSPFR6F11LUCAS` a sí mismo y
  en el kit escribe `LSPFR6F11`. Buscando el código completo el kit no aparecía **nunca** —son
  2.245 códigos así—. Buscando las dos formas, las relaciones kit→pieza pasan de **59 a 234**.
- **Un kit que no dice «kit».** `DISTRIBUCION C/BOMBA (LKTBN336 + LWPN007)`. Se pide el
  paréntesis **y** el más: con la barra en lugar del más se rompe, porque así lista Illinois
  los códigos de fábrica de UNA pieza (`(3036100/3411461)`) y serían 747 falsos kits.
- **Sin tocar la base.** Preguntarlo con `kits_que_lo_traen()` cuesta un LIKE sobre 70.888
  descripciones por par: revisar una tanda pasaba de 1,4 a **15,9 s**. Con los dos textos y
  nada más: 2,7 s.

Y hay una consecuencia que no se ve: 79 de esos pares estaban cayendo en «sin alarmas», o sea
que el botón de aprobar en bloque los cargaba como equivalencias.

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

## Lo que encontraba relaciones solo corría si alguien apretaba un botón

Era el agujero más grande que quedaba, y no se veía porque nada fallaba. El barrido de todo el
catálogo, las aplicaciones deducidas de las descripciones y el cruce por auto **existían y
andaban** — pero solo corrían si alguien entraba a Estadísticas → Mantenimiento y apretaba el
botón. Desde el mostrador nadie entra ahí. Así que en la práctica se importaba una lista, la app
decía «entraron 6.900 filas», y las 8.649 relaciones que esas filas hacían posibles se quedaban
sin buscar para siempre.

`descubrimiento_post_importacion()` corre eso solo, **después de importar** y no una vez por
día: es el único momento en que hay algo nuevo que encontrar, y el único en que la persona ya
está esperando. El orden va de lo que enriquece a lo que consume:

    1. aplicaciones_desde_descripciones()       32 s + 17 s   dato nuevo sobre cada producto
    2. derivar_equivalencias_de_aplicaciones()  22 s          USA esas aplicaciones
    3. sugerir_entre_todas_las_marcas()         23 s          lo más caro y lo que más produce

Medido sobre la base real (70.888 productos, cinco listas): **98 s**, y deja 120.691
aplicaciones y 17.308 pares nuevos en la cola de revisión — la cola pasa de 3.185 a 20.493.
Nada se carga como equivalencia: va todo a pendientes, igual que cuando se apretaba el botón.
Lo único que cambia es que ahora **se busca**.

Tiene presupuesto de tiempo como las tareas del día, pero mucho más grande (120 s contra 6 s), y
por una razón concreta: las tareas del día caen sobre alguien que abrió la app a buscar un
repuesto y no pidió nada; esto cae sobre alguien que acaba de subir una planilla de 26.000 filas
y está mirando una barra de progreso. Si igual se acaba, los pasos son independientes: se dice
qué quedó y se hace en la próxima importación.

**Y un número que mentía.** `guardar_equivalencias_pendientes()` devolvía `len(pares)` —lo que
se INTENTÓ guardar— y no lo que entró. Con `INSERT OR IGNORE`, lo que ya estaba en la cola no
entra. Apretando el botón a mano casi no se notaba; corriendo solo después de cada importación
se notaba siempre, porque el barrido propone los mismos 8.649 pares cada vez y la app iba a
anunciar «8.649 nuevos» en cada importación para siempre. Ahora devuelve `rowcount`, que con
`INSERT OR IGNORE` cuenta solo lo que realmente entró: la segunda corrida seguida no dice nada,
que es la verdad.

## Los vínculos malos que YA está devolviendo la búsqueda

De todos los controles, `auditar_equivalencias_cargadas()` es el único que mira lo que la
búsqueda está devolviendo **ahora**: los demás miran lo que todavía no entró. Y era el único que
seguía dependiendo de que alguien apretara un botón. Sobre la base real encuentra **270 vínculos
con evidencia en contra** entre los 24.774 cargados — 270 resultados equivocados que alguien
puede estar leyendo en el mostrador hoy.

Ahora se mide solo, como cuarto paso de `descubrimiento_post_importacion()` (11 s más, total
110 s), y el número queda guardado en la configuración. El chequeo de salud —que corre en
**todas** las pantallas, no en una de mantenimiento— lo lee de ahí y lo muestra arriba de todo.

La división es a propósito: **medir es automático, cortar no**. Cortar un vínculo es
destructivo, así que la app avisa y la decisión sigue siendo de una persona, con la lista
ordenada de peor a mejor y el motivo al lado. El chequeo lee el número guardado en vez de
recalcularlo porque medirlo cuesta 11 s y esa pantalla se dibuja todo el tiempo.

## Las equivalencias que publica la ficha del proveedor, de a quince por día

Es la única fuente de equivalencias que no es una deducción: lo dice el fabricante en su propio
catálogo web. Ya se podía leer, pero de a tandas a mano, y son miles de fichas.

Para que avance solo faltaba una cosa: **saber por dónde iba**. La consulta ordena por stock y
corta con `LIMIT`, así que cada tanda volvía a leer las mismas primeras fichas y no llegaba
nunca al resto del catálogo. La columna `productos.ficha_equiv_leida` guarda la fecha en que se
consultó cada código — la fecha y no un sí/no, para poder volver a pasar en unos meses, porque
una ficha puede publicar equivalencias nuevas.

Se anota **haya dado equivalencias o no**. El "no" también es información: sin anotarlo, la
próxima tanda vuelve a golpear las mismas fichas vacías. Es exactamente el problema que ya se
había arreglado para las fotos con `foto_busqueda_estado`.

Probado sin salir a internet, simulando el servidor del proveedor: tres tandas seguidas de 5
consultan 5 códigos distintos cada una (5 → 10 → 15 marcados). Antes habrían sido los mismos 5
tres veces. El interruptor está al lado del de las fotos, apagado por defecto porque sale a
internet, y arriba dice cuántas fichas faltan y cuántos días son a ese ritmo: sin ese número,
«automático» no dice si termina en una semana o en dos años.

## Nadie frenaba los intentos de contraseña

Salió de una revisión externa del código. La app vive en una dirección pública y el ingreso es
**un solo campo de contraseña, sin nombre de usuario**: cualquiera puede probar claves todo el
día. PBKDF2 protege el hash si alguien se baja la base —y la base se sube sola al repositorio,
así que eso importa— pero no protege nada contra probar «chavaje», «1234» o el nombre del
negocio contra la pantalla de ingreso, que es como se entra de verdad a un sistema de mostrador.

Ahora la espera se duplica con cada fallo desde el tercero, y se corta en un minuto:

    fallos    3    4    5    6    7    8    9+
    espera   1s   2s   4s   8s  16s  32s  60s

Dos decisiones que importan más que la fórmula:

- **El intento rechazado también cuenta.** La primera versión no lo contaba y la espera se
  quedaba clavada en un segundo para siempre: el que insiste vuelve a probar cada segundo y en
  un día prueba ochenta mil claves. Se vio probándolo, contando intento por intento.
- **El contador va en la base, no en `session_state`.** Un freno guardado en session_state se
  saltea apretando F5.

Y el precio, dicho de frente: desde Streamlit no hay forma de saber la IP, así que el freno es
para todos. Alguien que insista puede dejar al dueño esperando hasta un minuto. Por eso el tope
es un minuto y **no se bloquea ninguna cuenta**: la espera pasa sola. Un minuto de espera es
molesto; probar claves sin límite contra la caja es otra cosa.

De paso, las claves de los secrets se comparaban con `==`. `verificar_password()` ya tenía
escrito por qué eso está mal —comparar de a byte tarda distinto según cuántos caracteres
coincidan— pero ese cuidado no valía para las claves de administrador. Ahora las dos van por
`hmac.compare_digest`.

### Lo que esa misma revisión marcaba y ya estaba hecho

Vale anotarlo para no volver a discutirlo: **WAL** ya está activo, la **conexión es por hilo**
(`_ConexionPorSesion`, con el segmentation fault que lo motivó documentado ahí mismo),
`st.cache_data` se usa en toda la app, el **backup** por `conn.backup()` existe y se sube solo
al repositorio, y hay **39 índices** creados, incluidos los tres que la revisión sugería.

Y una que **no hay que hacer**: mover las fotos de la base a una carpeta en disco. En Streamlit
Cloud el disco se borra en cada redespliegue — los BLOBs están adentro de la base justamente
porque la base es lo único que sobrevive, y por eso existe `generar_backup_sin_fotos()`. Sacarlas
a disco perdería todas las fotos en el primer reinicio.

## El modelo de la máquina y el número del motor, cargados como código de fábrica

Salió de mirar la pantalla de puentes falsos sobre la base del negocio. Una lista de juntas de
motor metía en la columna de OEM cosas como estas:

    6PF-305        el motor Perkins            4D105-3     el motor Komatsu
    SUPER5         el Renault 5                308HDI      el Peugeot con su motorización
    L75-L76        dos modelos de Scania       C1J-C1L     dos motores Renault
    182.A8000      el número de motor Fiat     Cil.Esp.1   la descripción abreviada
    3350-3550-650-6600-7500                    cinco modelos de John Deere encadenados

Cada uno cuelga de sí mismo todo lo que lo nombre. Solo `6PF-305` aparece en **42 descripciones**
del catálogo real: 861 pares de productos hermanados por compartir el motor y nada más.

Entraron ocho reglas nuevas. **Lo que las hace difíciles no es reconocer el modelo, es no
romper los códigos que se le parecen** — y hay dos que se parecen mucho:

- **`55PP27-01` es un sensor de presión Bosch de verdad**, y tiene casi la forma de `6PF-305`.
  Los separa que el código de Bosch lleva dígitos entre las letras y el guion.
- **`1201-K1` es una bomba de agua Citroën y `1336-Y80` un termostato Peugeot.** Tienen
  exactamente la misma forma que `3420-J1`, que es un modelo de John Deere. Por eso `3420-J1`
  **quedó sin resolver**: por la forma no se puede distinguir, y romper los Citroën para
  atrapar un John Deere es un mal negocio. Lo mismo con `128-1500` (hay nueve códigos reales
  con forma `123-4567`) y con `AP2000` (`^[A-Z]{2}\d{4}$` le pega a 196 códigos reales:
  `IS0957`, `SW1311`, `TH7111`, todos bulbos y sensores).
- **`SUPER5` contra `TPRT05`.** Los dos son letras con un número atrás; el primero es un
  Renault y el segundo un sensor Thomson. Lo que los separa es que un modelo de auto **se
  pronuncia**: se piden dos vocales. Sin eso la regla se lleva puestos `TPRT05`, `TMAP14` y
  `CVMMF35`.

Todo se midió contra los **21.734 códigos OEM que hoy tienen vínculos**, separando los que
citan DOS proveedores distintos — esos son puentes reales y no se pueden tocar. Las ocho reglas
juntas sacan 65 códigos y **ninguno es de dos proveedores**. Pasando el catálogo entero por el
extractor viejo y el nuevo:

    códigos distintos extraídos     18.171 → 18.059
    dejan de salir                  112        empiezan a salir: 0
    pares de productos que unían    3.644
    equivalencias falsas evitadas   1.192      (las que cruzaban marcas distintas)

## Los puentes falsos que quedaron de antes

*(Reescrito: la primera versión no encontraba nada y el usuario lo reportó. Los tres errores
están abajo.)*

Arreglar el extractor evita los que vienen. Los que ya están cargados siguen ensuciando la
búsqueda, y son los que se ven desde el mostrador. Cada vez que se le enseña a la app a
reconocer un modelo o un motor queda atrás una camada generada con las reglas viejas que nadie
vuelve a revisar.

`puentes_que_hoy_no_se_generarian()` los encuentra **sin inventar ningún criterio**: le da la
vuelta a cada código cargado, lo pone adentro de un texto y lo pasa por el mismo extractor que
se usa al importar. Si hoy no lo sacaría de una descripción, tampoco debería estar como código
de fábrica. Solo mira los que unen productos de **dos listas distintas**, que son los que
fabrican la equivalencia falsa.

Probado inyectando los seis casos de la pantalla real junto a tres códigos verdaderos: detecta
los 6, respeta los 3, y al borrarlos desaparecen solo los códigos de fábrica falsos y sus
vínculos — los productos quedan intactos.

### Los tres errores de la primera versión

**1. Miraba la tabla equivocada.** Solo revisaba `equivalencias` —los vínculos ya aprobados— y
los códigos que hacen el daño estaban casi todos en `equivalencias_pendientes`, esperando
revisión. Se corría la limpieza, no aparecía nada, y los puentes falsos seguían ahí. Un código
que ensucia cuatro pendientes ensucia igual: son cuatro decisiones que hay que tomar por algo
que no es un código. Ahora mira las dos colas, y el borrado se lleva los pendientes también —
si no, al aprobar la cola se vuelve a crear exactamente el vínculo que se acababa de borrar.

**2. Estaba en la pantalla equivocada.** Quedó en 🧠 Calidad y aprendizaje, decimosegundo de la
lista, cuando el que tiene el problema entra a 🧹 Limpiar vínculos. Ahora va segundo ahí, al
lado de «Códigos puente».

**3. Le hacía al extractor la pregunta equivocada, y esa es la interesante.** El extractor tiene
dos juegos de reglas: unas AMBIGUAS —aciertan casi siempre, pero la misma forma la tiene algún
código de verdad, así que dejan de aplicarse en cuanto hay señal de que eso ES un código— y
otras que son texto sin discusión. Preguntándole a secas se aplican las ambiguas también, y el
control marcaba como falsos a `AT-05103R` (un código real, que une dos motores paso a paso de
la misma aplicación Fiat/Renault) y a `BX8.4d` (un zócalo de lámpara). **Borrarlos habría sacado
vínculos buenos, que es justo lo que este control existe para no hacer.**

La pregunta correcta es más dura: *«suponiendo que este código YA estuviera cargado en la lista
de un proveedor, ¿el extractor lo seguiría rechazando?»*. Así solo sobreviven las formas que son
texto sin discusión. Probado sobre 22 casos de la base real: respeta los 8 códigos verdaderos y
marca las 14 basuras, la familia `505REF` incluida.

Sobre el catálogo real, con la pregunta bien hecha: **81 códigos falsos, 185 vínculos cargados y
15 pendientes**, y ninguno de los 7 códigos reales de control.

## El cartel verde que decía «está todo bien» sobre algo que no controla

El usuario corrió «🔍 Revisar los vínculos que YA están cargados», le dijo *«se revisaron 26.685
vínculos y ninguno quedó por debajo del umbral de confianza»*, y entendió lo razonable: que no
había nada que limpiar. Los puentes falsos estaban ahí arriba, en la misma pantalla.

Ese control mide la **confianza** de cada vínculo, no si el código que los unió es un código. Y
un modelo de auto cargado como código de fábrica une repuestos que comparten el mismo auto —
compartir auto es justamente lo que *sube* la confianza. Sale en verde y sigue estando mal.

El cartel ahora dice qué no mira y adónde ir. Un control que contesta una pregunta distinta de
la que le hacen es peor que no tenerlo: manda a la gente a otro lado convencida.

## Lo que Excel le come a un código largo, y por qué es peor que una fecha

Ya estaba resuelto el caso de la fecha: Excel toma «12-15» por una fecha, el código se pierde, y
la app lo detecta y frena la fila. Eso se nota porque una fecha no parece un código.

Este es el mismo problema pero invisible. Excel muestra los números de más de once dígitos en
notación científica y, al guardar un CSV, **escribe lo que muestra**: el código de barras
`7793960026946` sale del archivo como `7.79396E+12`. Los últimos siete dígitos ya no están.

Y `sanitizar()` lo reconstruía: `7793960000000`. Trece dígitos, prefijo argentino correcto,
forma de código de barras perfecta. Se cargaba **sin una sola queja**, y desde el mostrador se
veía como «el escáner no encuentra nada», sin ninguna pista de por qué.

`excel_le_comio_digitos()` lo reconoce contando: `7.79396E+12` trae seis dígitos escritos y el
número reconstruido tiene trece. Los otros siete los inventó la cuenta, no estaban en el
archivo. No se arregla solo a propósito — adivinar el número sería inventar un código de barras,
que es justo lo que se quiere evitar.

La contracara importa igual o más: **`233900E010` es el filtro de combustible Toyota
23390-0E010** y no es notación científica. Hay 283 códigos de esa forma en las listas reales.
Lo que los separa es el signo del exponente, que Excel siempre escribe y un código de fábrica
nunca — la misma regla que ya usaba `sanitizar()`, ahora compartida.

Avisa en los dos lugares por donde entra un archivo: la vista previa de la importación (mirando
también la columna del EAN, que es la que más sufre porque trece dígitos siempre pasan el largo
donde Excel cambia de formato) y la carga masiva de códigos de barras. En los dos casos esas
filas **no se cargan**, y el mensaje dice cómo exportar de nuevo.

## Cargar los códigos de barras que ya están pegados en las cajas

Un negocio que ya etiquetó su mercadería tiene los números y las etiquetas puestas; lo que falta
es que la app los sepa. Hasta ahora la única forma era **reimportar la lista entera** del
proveedor con la columna del EAN mapeada, y eso toca todo lo demás: pisa precios, pisa stock,
genera equivalencias nuevas y deja un lote para revisar. Para pegarle un número a cada producto,
es una operación enorme al lado de lo que hace falta.

`cargar_codigos_de_barras_masivo()` hace solo eso: dos columnas —código del producto y código de
barras— y se pegan. **No crea productos**: un fantasma con una etiqueta pegada no le sirve a
nadie, así que lo que no está cargado se informa y se puede bajar en Excel.

Tres cosas que decide y conviene saber por qué:

- **Conviene elegir la lista.** El mismo código de fábrica lo usan varios proveedores; sin
  elegir, la misma etiqueta se le pegaría a los productos de todos. Sin lista elegida, los
  códigos que aparecen en más de una se saltean y se informan.
- **Los códigos de barras repetidos en el archivo no se cargan.** Es un error que no se ve:
  escanear esa etiqueta trae dos repuestos y nadie sabe cuál es. La primera versión los avisaba
  *después* de haberlos escrito, que es dejar el problema hecho y contarlo. Y se comparan ya
  limpios: «779-396-0026946» y «7793960026946» son el mismo número, y comparando el texto crudo
  pasaban como dos distintos.
- **Se puede correr dos veces sin miedo.** Probado sobre el catálogo real: la segunda pasada
  pone 0 y marca 3.002 como «ya estaban igual».

Medido sobre la base real con 3.002 etiquetas: entran las 3.002, los 2 códigos inexistentes se
informan sin crear nada, el repetido se detecta, y **los productos siguen siendo 70.888 y las
equivalencias 24.774** — no tocó nada más.

## Un control que avisaba de un problema que no existe

El dígito verificador distingue un EAN bien copiado de uno mal tipeado. Pero **eso solo vale si
la etiqueta la imprimió el fabricante.** Un negocio que etiqueta su propia mercadería genera los
números él mismo y no tienen por qué cumplir la cuenta de GS1 — y el escáner los encuentra
igual, porque la etiqueta se imprimió DESDE ese número: coinciden dígito por dígito, cierre la
cuenta o no.

Sin esto, el negocio que ya tiene todo etiquetado se encontraba con dos carteles falsos:

- La pantalla de Estado listando miles de códigos «que el escáner no va a encontrar» — y
  mandando a revisar cajas que están bien.
- **Un cartel de «está mal leído o mal tipeado» en CADA escaneo**, incluso cuando el repuesto
  aparecía perfecto.

Las dos se arreglan con el mismo criterio que ya usa `columna_es_codigo_de_barras()`: decidir
por el conjunto y no por el código suelto. Si en una lista falla la mitad o más, eso no son
errores de tipeo, es una numeración propia, y la lista sale del control entera — diciéndolo en
pantalla, porque que un control decida no mirar algo también hay que contarlo.

Y en el escáner, el dígito verificador **solo se menciona cuando no se encontró nada**. Si el
repuesto apareció, el número está bien por definición: coincide con el cargado.

De paso, el consejo para un código de uso interno (200-299) es el contrario según quién imprime
las etiquetas: «escaneaste la etiqueta equivocada» si son del fabricante, «es una etiqueta tuya
que todavía no cargaste» si el negocio imprime las suyas. `el_negocio_etiqueta_con_codigos_
propios()` lo deduce de lo que ya está cargado, en vez de preguntarlo.

## El 87% del catálogo tenía el índice de búsqueda viejo

`productos.busqueda` es la columna con el texto ya normalizado que usa la búsqueda por
descripción. La mantienen dos triggers, y los triggers **se borran y se vuelven a crear en cada
arranque** justamente porque la fórmula cambió alguna vez y con `IF NOT EXISTS` una base ya
creada se quedaba con la versión vieja. Eso arregla el trigger. **No arregla los valores ya
guardados.**

El relleno existía, pero con `WHERE busqueda IS NULL`: cubre «nunca se calculó» y no cubre «se
calculó con otra fórmula». Cuando `codigo_barras` se sumó a la expresión, las filas que ya
estaban cargadas se quedaron con el valor anterior para siempre, porque el trigger solo toca lo
que se inserta o se modifica de ahí en adelante.

Sobre la base real: **61.574 de 70.888 productos (87%)**. Se los reconoce porque su valor
guardado no termina en el espacio que deja el `codigo_barras` vacío.

Qué significa en el mostrador, probado de punta a punta: un producto con código de barras
cargado y el índice viejo **no aparece tipeando su código de barras**, ni reiniciando la app.

    ANTES, buscando el código de barras por texto          0 resultados
    ANTES, después de reiniciar la app                     0 resultados
    AHORA, después de arrancar con el relleno por versión  1 resultado

Ahora el relleno va por versión (`VERSION_NORMALIZACION`), igual que las semillas de WMI y de
códigos de falla: cambiar la fórmula obliga a recalcular una vez sobre todo lo cargado. Cuesta
0,6 s la primera vez y 0,0 s después. Y va en `_datos_precargados_y_migraciones()`, que corre
al final, no en `_esquema_catalogo()`: ahí todavía no existe la tabla de configuración y no
habría dónde anotar que ya se hizo, así que se repetiría en cada arranque.

## El SQL no sacaba los mismos acentos que Python, y no se le pueden agregar muchos más

`normalizar_texto()` usa NFKD y manda a ASCII todo lo que se pueda. `_sql_sin_acentos()` hacía
doce REPLACE. No es lo mismo: sobre el catálogo real había **80 productos** con una letra que
Python normaliza y el SQL no —«SENSOR RPM cigüeñal», «CITROËN», «Conexão», «PÒINTER»— y esos
80 no se encontraban buscando CIGUENAL ni CITROEN.

Lo interesante es por qué no se arregla agregando todas las letras: **cada par es un `REPLACE()`
anidado adentro del anterior, y SQLite tiene un techo de anidamiento**. Medido en 3.45: revienta
a los 31 con `parser stack overflow`. Y no son 31 libres — la consulta que envuelve la expresión
gasta del mismo presupuesto, así que con 28 pares la expresión anda suelta y falla adentro de un
`COUNT()`. Un intento de agregar el juego completo de acentos latinos (50 pares) no compila.

Así que van cuatro letras elegidas por lo que aparece de verdad en las listas cargadas —ü, ê, ë,
â, que cubren 73 de los 80— y el tope queda en 20 pares, con diez de margen. **`auditar.py` lo
controla** (chequeo 27): pasarse no da un error al escribir el código, rompe la búsqueda entera
de la app en tiempo de ejecución, que es exactamente la forma en que nadie se entera hasta que
hay un cliente esperando. Probado contra una copia con 28 pares: el auditor la rechaza.

Medido después del cambio: `CIGUENAL` pasa de 261 a 268 productos y `CITROEN` de 3.564 a 3.567.

## Buscar adentro de la descripción costaba doce REPLACE por fila

Sacarle los acentos a la descripción **en la consulta** son doce `REPLACE()` anidados por fila.
Sobre 70.888 productos son 170 ms por búsqueda, y hay pantallas que la hacen cuatro o cinco
veces seguidas: de ahí salían los 215 ms que tardaba en contestar un código de falla.

La columna `busqueda` ya tiene el texto normalizado, pero **no sirve de reemplazo**: además de
la descripción trae el código y el código de barras, así que buscar «FIAT» ahí también engancha
un código que lo tenga adentro. Usarla directo cambiaría lo que la consulta significa.

Por eso `like_en_descripcion()` la usa de **prefiltro** y deja la condición exacta como
confirmación: la columna barata descarta casi todo y los `REPLACE` corren solo sobre lo que
pasó. Es una sustitución sin pérdida — cualquier texto que esté en la descripción normalizada
está también en la columna, que la contiene entera.

    repuestos_para_el_dtc, los 191 códigos del diccionario
      antes    49,9 s   (mediana 184 ms por código)
      después   4,3 s   (mediana  23 ms)            0 respuestas distintas

Las 191 respuestas se compararon **grupo por grupo y producto por producto**, no por el total.
El `IS NULL` del prefiltro no debería hacer falta —hay relleno y triggers— pero sin él una fila
con la columna vacía desaparecería de los resultados sin ningún error a la vista.

## El descubrimiento ya no te hace esperar dos minutos

`descubrimiento_post_importacion()` tarda 110 s sobre el catálogo real, y los hacía esperar
adentro de la pantalla de importar. En un celular —con la pantalla que se apaga sola y el
navegador que puede cortar— eso era la peor parte de haberlo automatizado.

Ahora la importación solo **pide** el descubrimiento y el hilo de fondo lo levanta. Probado:
corre completo desde el hilo en 109 s, con el mismo resultado (120.691 aplicaciones, 8.649 pares
del barrido, 270 vínculos dudosos medidos) y sin un solo error — incluidas las funciones
cacheadas de Streamlit, que era lo que había que verificar antes de sacarlas del hilo principal.
Si no le alcanza el tiempo, queda pedido para la vuelta siguiente.

Y dos cosas que aparecieron revisando el hilo de fondo con la lupa:

- **Del cupo diario se descontaba lo que se pedía, no lo que se consultaba.** Si quedaban tres
  fichas y la subtanda es de cincuenta, se le cobraban cincuenta al cupo: cuarenta y siete
  consultas tiradas a la basura.
- **El bucle se daba por productivo porque había una marca pendiente**, no porque hubiera
  avanzado. La consulta que elige la marca y la que trae las fichas son dos, y el día que
  alguien toque una sola de las dos, el bucle gira diez minutos contra la base sin hacer nada.

## Catálogos que piden usuario y contraseña

Muchos proveedores tienen la ficha detrás de un login. Sin manejarlo, la app pide la página, el
sitio le devuelve el formulario de ingreso, y de ahí no sale ni foto ni equivalencia: el catálogo
entero queda afuera sin que nada falle a la vista.

**Las credenciales van en los secretos de Streamlit, no en la base.** No es una preferencia: todo
lo que se guarda en la tabla `configuracion` sale de la app por dos puertas —el backup que se
sube solo al repositorio de GitHub, y el botón de bajar la base completa—, así que una contraseña
guardada ahí termina copiada en el repositorio. En los secretos no toca la base.

    [catalogo.MOTORARG]
    url_login     = "https://ejemplo.com/ingresar"
    usuario       = "micuenta@ejemplo.com"
    clave         = "loquesea"
    campo_usuario = "email"        # cómo llama el sitio a ese campo
    campo_clave   = "password"

Los nombres de campo salen de mirar el formulario del proveedor: cada sitio los llama distinto y
no se pueden adivinar. Se lee siempre por `secretos_app()` y nunca por `st.secrets` directo —
leer `st.secrets` sin un `secrets.toml` levanta excepción, que es el bug que ya está documentado
más abajo.

Tres decisiones:

- **Una sesión por marca, guardada y reusada.** Una tanda son cientos de fichas; loguearse en
  cada una serían cientos de ingresos contra el proveedor, que es la forma más rápida de que te
  bloqueen la cuenta.
- **Las sesiones vencen.** El sitio corta a las pocas horas y desde ahí *todas* las fichas
  contestan el formulario. Si una tanda falla en más del 80%, se tira la sesión guardada y la
  siguiente vuelve a entrar. El 80% y no «alguna»: en cualquier catálogo hay fichas que no
  existen, y tirar la sesión por eso sería loguearse de nuevo en cada tanda.
- **Si el login falla, no se rompe nada**: se sigue sin sesión, exactamente como antes.

Probado contra un servidor HTTP de verdad levantado para la prueba, con cookie de sesión:

    sin credenciales      6 fichas → 0 propuestas, el sitio devolvió el formulario 6 veces
    con credenciales      1 login  → 6 fichas leídas, 6 propuestas
    segunda tanda         sigue en 1 login (reusa la sesión)
    sesión vencida        falla todo, tira la sesión, y la tanda siguiente vuelve a entrar sola
    clave equivocada      None, y la tanda sigue sin sesión
    sin secrets.toml      None, sin excepción

Y una advertencia que la pantalla también da: **avisale al proveedor**. Sos cliente y tenés
acceso, pero muchos catálogos prohíben en sus condiciones consultarlos de forma automatizada, y
cientos de consultas seguidas pueden hacer que te corten el usuario.

## Quince por día son trece años

Las dos tandas que bajan cosas del catálogo del proveedor —fotos y equivalencias— iban de a 15
por día, enganchadas a las tareas del día. Con 500 productos eso alcanza. Con los 70.888 de la
base real son **trece años**, y con medio millón no termina nunca.

El límite no era el proveedor: era **dónde corría la tanda**. Estaba adentro del dibujo de la
pantalla, con el presupuesto de 6 segundos de las tareas del día, así que agrandarla significaba
hacer esperar a alguien que entró a buscar un repuesto.

La tanda se fue a un hilo aparte. Nadie espera, así que ahora puede ser tan grande como se
quiera, y lo único que la limita es lo único que corresponde que la limite: el servidor del
proveedor. Se elige a mano, de 15 a 10.000 por día, con los días que faltan escritos al lado —
sin ese número, «automático» no dice si termina en una semana o en trece años.

Tres cosas la hacen segura:

- **Una sola a la vez en todo el proceso.** Con cinco pestañas abiertas serían cinco tandas
  pidiéndole lo mismo al proveedor al mismo tiempo. Y el candado se toma **antes** de crear el
  hilo, no adentro: mirar si está libre y después crear el hilo deja una rendija entre las dos
  cosas por la que entran dos. El de adentro no alcanzaba a hacer trabajo de más, pero la
  función contestaba «la largué» sin haber largado nada, y probándola se veía.
- **Subtandas de 50 que van guardando.** Streamlit Cloud apaga el servidor por inactividad; si
  pasa, se pierde la subtanda en curso y nada más.
- **Nunca toca `st`.** Un hilo de fondo no tiene pantalla donde dibujar. Todo lo que tiene para
  contar lo deja en la configuración, y la pantalla lo lee de ahí.

Alterna fotos y equivalencias en vez de terminar una y después la otra: si no, prender las dos
significaría que la segunda no arranca hasta dentro de un mes.

Probado contra la base real con un servidor de proveedor simulado (acá no hay internet): con
cupos de 200 fotos y 300 fichas, pide exactamente 200 y 300, **sin repetir un solo código**, los
pendientes bajan de 5.063 a 4.763, y con el cupo del día gastado no pide nada más.

**Y el techo que no se arregla agrandando la tanda.** Leer ficha por ficha son tantas consultas
como productos: medio millón de consultas al servidor del proveedor, que te va a cortar mucho
antes. Cuando faltan más de 60 días al ritmo elegido, la pantalla lo dice y propone lo que de
verdad sirve a esa escala — pedirle al proveedor el archivo y cargarlo por 📁 Cargar Excel.

## El dólar y la inflación: lo único que la app va a buscar afuera

`contexto_de_precios()` trae el dólar oficial del BCRA (api.argentinadatos.com) y el IPC del
INDEC (apis.datos.gob.ar). Las dos son públicas, sin clave y sin costo.

No decide nada: el ritmo con el que se decide sigue siendo el de **tus** importaciones. Contesta
las dos cosas que el historial propio no puede — cuánto se movió el dólar, que es lo que manda
en lo importado, y **qué proveedor viene subiendo por debajo de la inflación**, o sea cuál está
quedando barato y conviene comprarle ahora.

Cuatro decisiones que salieron de probarlo, no de escribirlo:

- **No usa `st.cache_data`.** Streamlit cachea también el FALLO: si justo cuando se pide no hay
  internet, el `{}` vacío queda seis horas guardado y la pantalla no dice nada aunque la conexión
  haya vuelto a los dos minutos. Y ese caché se pierde al reiniciar el servidor, que en Streamlit
  Cloud pasa seguido. Guardado en la tabla de configuración, lo último que se supo sobrevive.
- **Penitencia después de un fallo.** Sin eso, con internet caído se reintentaba en cada dibujo
  de pantalla: cuatro segundos por vez. Ahora espera media hora.
- **Si hoy no se puede, muestra lo último que supo**, marcado como viejo. Es más útil que no
  decir nada, y marcarlo evita hacerlo pasar por el dato de hoy.
- **Las claves de `variacion` son texto, no números.** Pasa por JSON para guardarse, y JSON no
  tiene claves numéricas: al volver, el `30` es `"30"`. Buscándolo como número no se encontraba
  nunca y la línea simplemente no aparecía, sin ningún error.

Probado contra nueve respuestas rotas distintas (`None`, lista vacía, `{"data": None}`, texto
suelto, cotización en cero, una sola fila de IPC): ninguna levanta excepción. **Lo que no pude
probar es la llamada real** — este entorno bloquea los dos dominios por política de red —, así
que el parseo está probado con respuestas simuladas con la forma que devuelven esas APIs, y todo
el camino de fallo está probado de verdad. Si la forma cambió, la pantalla no muestra la línea;
no rompe nada.

## Cuánto atrasada está una lista, medido con tu propio historial

En Argentina una lista de precios de hace dos meses no es una lista de precios. Pero «hace dos
meses» no dice cuánto estás perdiendo: depende de cuánto aumentó **ese** proveedor.

No hace falta ningún índice ni ninguna consulta paga. La app ya guarda cada cambio de precio en
`historial_precios`, y con eso alcanza: `envejecimiento_de_precios()` mide a qué ritmo aumenta
cada lista, lo compara con los días desde la última importación y devuelve un número accionable
— *«MOTORARG tiene 45 días y viene subiendo 9% por mes: estos precios están 13% abajo»*.
Aparece en 📥 Importaciones y, cuando pasa del 5%, también en el diagnóstico de salud, que es
el único punto de esa lista que cuesta plata en **cada venta** y no cuando algo sale mal.

Tres decisiones que no son obvias y que ya se probaron contra la base real:

- **La mediana, no el promedio.** En cada importación hay un puñado de productos que pasan de
  100 a 100.000 porque cambió la unidad o se corrigió un error de carga. Con el promedio, esos
  pocos deciden el número de toda la lista.
- **A ritmo mensual, no «cuánto subió».** Un 4% en 15 días no es un 4% en 90:
  `razon ** (30 / dias) - 1`. Y se piden al menos 20 muestras antes de afirmar un ritmo.
- **`COUNT(DISTINCT p.id)`.** El `LEFT JOIN` con el historial multiplica la fila del producto
  por cada cambio de precio que tenga: contando a secas, un proveedor con dos importaciones
  aparecía con el doble de productos. Y los días nunca son negativos — una fecha adelantada (el
  reloj de la máquina, una lista cargada con fecha futura) no significa que los precios sean del
  futuro.

Cuando todavía no hay dos importaciones de una lista no se inventa un ritmo: si además pasaron
más de 60 días, avisa igual, pero diciendo que no sabe cuánto.

## Los códigos de falla que se arman solos

El diccionario de códigos OBD2 traía 191 códigos copiados a mano, y ahí se veía dónde se había
cansado quien los copió: los fallos de encendido llegaban hasta **P0304**. Un motor de seis
cilindros tira P0305 y P0306, y la app no sabía qué eran.

Buena parte del estándar genérico es una serie: el mismo texto con el número de cilindro, el
banco o el sensor cambiado. Eso no se copia, se arma:

    P0301 a P0312    fallo de encendido, cilindro 1 a 12
    P0201 a P0212    circuito del inyector, cilindro 1 a 12
    P0261 a P0284    bajo / alto / contribución de cada cilindro
    P0130 a P0167    sonda lambda y su calefactor, por banco y por sensor
    U0100, U0101…    se perdió la comunicación con el módulo de motor, de la caja, del ABS…
    C0035 a C0050    sensores de velocidad de rueda

Son 264 códigos ahora. Y hay una trampa que vale anotar: **la numeración va en decimal, no en
hexadecimal**. Los códigos parecen hexadecimales y no lo son — después de P0269 viene P0270, no
P026A. Armando la serie con aritmética hexadecimal, que es lo que sale natural, del cilindro 4
en adelante salen códigos que no existen.

La semilla ahora va por versión, como la de los WMI: quien ya tenía la app recibe los códigos
nuevos sin perder los que cargó o corrigió a mano.

## Del código de falla al repuesto

El diccionario decía qué significa la falla y ahí terminaba. El que atiende leía «fallo de
encendido en el cilindro 6 — bujía, bobina, inyector» y salía a buscar cada una de esas piezas
al buscador, a mano, una por una.

Ahora las busca la app. No es una base nueva ni una consulta paga: son las palabras del propio
código cruzadas con las descripciones del catálogo que ya está cargado.

    P0306            →  BUJIA (8)  ·  CABLE DE BUJIA (7)  ·  BOBINA (8)  ·  INYECTOR (2)
    P0306 + FIAT     →  BUJIA (8)  ·  CABLE DE BUJIA (3)  ·  BOBINA (8)  ·  INYECTOR (1)
    P0135            →  SONDA LAMBDA → «SENSOR DE OXIGENO NGK JAPON»

Dos cuidados que costaron una vuelta:

- **La palabra entera, no la subcadena.** «CABLE» está adentro de «CABLEADO», que es la causa
  de casi todos los códigos eléctricos: buscando la subcadena, todos los códigos del
  diccionario ofrecían cables de bujía.
- **Primero lo que EMPIEZA con esa palabra.** En una descripción el nombre de la pieza va
  adelante, así que «BUJIA NGK FIAT PALIO» es una bujía y «ARANDELA CAPUCHON BUJIAS» es otra
  cosa que la nombra.

## La junta tapaba a la pieza

El 59% de lo que ofrecía «del código de falla al repuesto» empezaba con JUNTA, ARANDELA, JTA,
O'RING o CANO. No estaba mal buscado: **estaba mal ordenado**. Un P0016 ofrecía un o-ring de la
tapa de distribución en vez del kit; un P0335 ofrecía la junta de la tapa anterior del cigüeñal
en vez del sensor de rotación; un P0420, la junta del catalizador.

Tres cosas se juntaban para producir eso:

- **El `LIMIT` estaba en el SQL, y el orden en Python.** La consulta pedía 8 filas ordenadas por
  precio; la junta siempre sale más barata que la pieza, así que las 8 filas que llegaban eran 8
  juntas y la pieza de verdad no entraba nunca — ordenarlas después no la podía traer de vuelta.
  Ahora se piden doce veces más y se corta **después** de ordenar.
- **«La palabra en los primeros 12 caracteres» no distingue nada.** «JUNTA DISTRIBUCION» cumple
  esa regla igual que «KIT DE DISTRIBUCION». Ahora hay una lista de con qué arranca el nombre de
  un **accesorio** de la pieza (`_ACCESORIO_DE_LA_PIEZA`) y esos van al final del grupo — no se
  esconden, porque a veces la junta es justo lo que falta.
- **Los grupos salían en el orden del diccionario**, que no quiere decir nada. Ahora salen en el
  orden en que **el propio código** los nombra: el texto arranca con la descripción de la falla y
  sigue con las causas escritas de la más probable a la menos.

Y dos detalles que costaron una vuelta cada uno:

- «CABLE» a secas no sirve como nombre de pieza: *«cableado cortado o en corto»* es la causa de
  casi todos los códigos eléctricos del diccionario, así que una falla del electroventilador
  terminaba ofreciendo cables de bujía. El cable de bujía se nombra con las dos palabras.
- «TURBO» y «COMPRESOR» se probaron como piezas nuevas y **quedaron afuera**: traen 965 y 324
  productos que no son eso (las aplicaciones dicen «2.0 TD» y hay caños «al turbocompresor»).
  «DISTRIBUCION» en cambio trae los 603 kits y nada más. La palabra se elige contra el catálogo
  real, no por lo que suena bien.

Sobre los 316 códigos del diccionario: **299 grupos ofrecidos, 3 encabezados por un accesorio**
(antes eran 231 grupos y 136 accesorios). El tiempo por código no cambió: 0,34 s.

## Cincuenta y dos códigos de falla más, y los que ya estaban no se podían corregir

Entraron las familias que faltaban y que terminan en una venta:

    P0016 a P0019    la distribución se corrió (cigüeñal y levas fuera de fase) → el kit
    P0671 a P0678    bujía incandescente por cilindro → el diesel que no arranca en frío
    P0087…P0193      presión del riel, regulador, fuga → common rail
    P0045/46, P0299  geometría variable y falta de presión del turbo
    P2101 a P2138    cuerpo de mariposa y pedal del acelerador (P2135 es de los que más salen)
    P2195 a P2198    la sonda quedó pegada en pobre o en rica
    P0691/92, P0645  relés del electroventilador y del compresor del aire
    P0622 a P0629    campo del alternador y bomba de combustible
    P2002, P2463     filtro de partículas

De 264 a 316 códigos, y de 189 a 236 los que ofrecen un repuesto del catálogo.

Pero apareció algo peor que la falta de códigos: **la semilla no podía corregir lo que ya había
cargado**. Entraba con `INSERT OR IGNORE`, así que arreglar el texto de un código existente no
llegaba nunca a una base que ya existía. `P0380` decía «falla en la bujía/circuito calefactor» y
por eso ofrecía **bujías de nafta para un motor diesel**; corregirlo acá no cambiaba nada en la
base del negocio. Ahora hay una columna `editado`: la semilla corrige los códigos que vinieron
con la app, y **no toca** los que cargó o corrigió el usuario (`agregar_dtc()` y la importación
masiva los marcan con 1). Está probado con los dos casos: `P0380` se corrigió solo, y un `P0301`
editado a mano sobrevivió intacto.

## De la patente al repuesto, sin pagar una consulta

Lo gratis que existe y lo que no, para que quede escrito:

| Lo que se busca | Gratis |
|---|---|
| Patente → marca, modelo, año | **No.** El informe de dominio del registro automotor se paga por consulta, y las páginas que lo ofrecen «gratis» devuelven el dato de un scraping que se cae solo |
| Patente → si está denunciado | Sí, la consulta pública de automotores sustraídos — pero eso no dice qué auto es |
| **Foto de la cédula → todo el vehículo** | **Sí**, y es mejor que cualquier consulta |
| VIN → país, fabricante, año | Sí, es la norma ISO, y ya estaba en la app |

Así que el camino es el de la cédula. `leer_cedula_por_foto()` lee una cédula verde, una azul o
un título y saca dominio, marca, modelo, año, **número de motor** y **número de chasis**. Los
dos últimos no los da ninguna consulta gratuita, y son justo los que después sirven cuando el
auto tiene el motor cambiado y el VIN ya no representa lo que hay abajo del capot.

Una foto, una vez, y de ahí en más la patente sola alcanza. Nada se guarda solo: lo leído sale
a un formulario para corregir antes de aceptar, y el prompt le pide explícitamente que deje en
blanco lo que no se lea bien —un número de chasis inventado hace que después se busquen
repuestos de otro auto.

## Y la pieza que hace falta

Con el auto identificado, la pantalla de patente mostraba «7 repuesto(s)» y una tabla con los
nombres de las listas adentro. El error era de una línea: `repuestos_de_este_auto()` devuelve
las cuatro fuentes SEPARADAS a propósito —lo que ya se le puso a este auto, lo que se le puso a
otro igual, lo que dice el fabricante y lo que dice el catálogo— y la pantalla dibujaba el
diccionario entero. Los 200 productos que le entran a un Palio 2001 estaban ahí y no se veían.

Ahora se ven las cuatro fuentes, cada una con su cartel de cuánto vale, y arriba está la
pregunta del mostrador: **¿qué pieza necesita?**

    DVX 123  →  Fiat Palio 2001  →  1.855 repuestos en el catálogo para ese auto
    «junta tapa»  →  70

Ese filtro va en la CONSULTA y no sobre el resultado, que es donde estaba la trampa: la lista
viene cortada en los primeros 200, así que filtrar esos 200 por «junta de tapa» no encontraba
nada aunque el catálogo tuviera setenta.

Y si alguien escribe una patente en el buscador de códigos —pasa, el cliente la dice y uno la
escribe donde está el cursor— en vez de «sin resultados» ahora dice qué es, de qué años y dónde
se usa.

## Lo que la patente dice sola

No existe una base pública y gratuita que traduzca patente a vehículo —las que hay cobran por
consulta— así que de la patente sola nunca va a salir «Gol 1.6 2012». Pero no es cierto que no
diga nada, y lo que dice es justo lo que el mostrador pregunta después del modelo: **de qué año
es**.

`leer_patente()` reconoce los cuatro formatos argentinos sin consultar nada:

    AB 123 CD   Mercosur, auto        desde abril de 2016
    A 123 BCD   Mercosur, moto        desde abril de 2016
    ABC 123     vieja, auto           1995 a marzo de 2016
    123 ABC     vieja, moto
    B 123 456   provincial, hasta 1994 — y la letra dice la provincia (B = Buenos Aires,
                X = Córdoba, S = Santa Fe, M = Mendoza…)

Y estima el año por la serie. Eso es lo delicado: **no hay una tabla oficial publicada** de qué
serie salió en qué mes. Lo único seguro es el ORDEN —las series se entregan alfabéticamente— así
que con unas pocas anclas conocidas se interpola el resto, el resultado va siempre como RANGO y
la pantalla dice que es aproximado. El rango además se recorta a los años en que ese formato
existió: una `AAA 111` no puede ser de 1993 ni una `PZZ 999` de 2018.

Lo que hace que esto sea de verdad útil es la segunda parte: **el taller corrige la tabla sin
darse cuenta**. Cada ficha cargada con patente Y año es un dato exacto de esta zona y de este
parque, así que `anio_probable_de_patente()` busca las fichas propias más cercanas por arriba y
por abajo de esa serie e interpola entre esas dos. Con dos fichas ya no usa la tabla general, y
lo dice: «estimado con las 14 fichas que tenés cargadas con patente y año».

    sin fichas    DVX 123  →  2000-2004   estimado por la serie (aproximado)
    con 4 fichas  DZZ 999  →  2001-2003   estimado con tus fichas

## Veinte WMI más

El lector de VIN trae precargados los fabricantes por WMI —los tres primeros caracteres— y
estaban los 328 que cubren el parque argentino. Faltaban los que las marcas estrenaron en los
últimos años y algunos que acá se ven seguido: Mercedes `W1K`/`W1N`/`W1V`, BMW i `WBY`, BMW
Motorrad `WB1`, las nuevas de PSA `VR1`/`VR3`/`VR7`, Mazda `JM1`, Great Wall `LGW`, Tesla
`7SA`/`LRW`, Volvo China `LYV`, Honda y Acura de Estados Unidos `19U`/`19X`/`5FN`/`5J6`, Kia
`5XY`, Ford Tailandia `MNA`, SAIC-GM-Wuling `LZW`. Son 348.

Van solo los que se pueden dar por seguros: un WMI equivocado hace que la app afirme una marca
que no es, y eso es peor que no saberla. La lista sigue siendo editable desde la app y lo que
esté cargado a mano no se pisa nunca.

## «PVC» era un código, y unía 76 cables

En la base real hay **196 vínculos entre dos productos de la misma lista**, todos de JL. No son
equivalencias: salen de una celda de código que traía dos cosas y una no era un código.

    208.856 C  ↔  PVC        Cable VW GACEL 1.6/GOL/SENDA
    23 8130R   ↔  SOPORTE    RELAY UNIVERS Tipo A Simple 30A c/soporte
    BF 3       ↔  SPR        BOBINA 1000 ST aceite / SPR aceite
    274.899 c  ↔  CHAPA      Cable VW CARAT

Los códigos de una misma celda **sí** se vinculan entre sí a propósito —son dos números del
mismo producto— y ahí está el agujero: cuando el pedazo que sobra es una palabra suelta, esa
palabra queda como un producto que se repite en decenas de filas y termina uniéndolas a todas.
El «CHAPA» de la lista de JL colgaba **76 cables distintos**, y era el código puente número uno
de toda la base.

Se reconocen por no tener **ningún dígito**. En las 70.888 filas del catálogo real hay 14
códigos así, y los pocos que son de verdad son herramientas sueltas —HGONIOMETRO, APLIGAL,
HCRV— que no necesitan equivalencia con nada. Así que un código sin números deja de vincularse
con sus compañeros de celda.

Para los que ya están cargados hay dos avisos nuevos, uno en cada pantalla que revisa vínculos:

- «los dos son de JL y **«PVC» no tiene ningún número**: es un pedazo de la descripción que
  quedó como código»
- «los dos son de JL y **dicen exactamente lo mismo**: es una fila de la lista leída dos veces»

Con eso, «Revisar los vínculos que YA están cargados» pasa de encontrar 127 dudosos a 270 sobre
los mismos 24.774. Y de paso ese listado dejó de cortarse en 300: como ordena por confianza, el
tope escondía justo lo que hay que ver.

## Pedir el 206 y que no venga el 9662063280

El filtro por modelo de la pantalla de vehículos buscaba el modelo **adentro** del texto de la
descripción. Con los modelos de siempre eso andaba —PARTNER solo aparece cuando dice PARTNER—
pero desde que el desplegable ofrece los que son números, buscar «206» engancha cualquier
número de parte que lo contenga: pedir el 206 traía 1.554 productos y 100 eran filas de
Citroën con el código `9662063280`.

Ahora se busca como PALABRA, sobre el texto ya despegado. Lo segundo hace falta para no perder
los que una de las listas escribe pegados: «Peugeot 206 - 307REF ORIG» — como palabra suelta,
ese 307 tampoco daría.

    206      1.554 → 1.462
    307      1.169 → 1.132
    405      1.025 →   916
    PARTNER  1.275 → 1.272

El texto despegado se guarda al armar el catálogo de la marca, que ya va cacheado por versión
del catálogo: separar las 6.991 descripciones de Peugeot cuesta 0,35 s y así se paga una vez y
no en cada vuelta de la pantalla.

## El desplegable de autos no tenía ni el 206 ni el A3

Eligiendo Peugeot, la app ofrecía como «modelos»: HDI, PARTNER, BOXER, EXPERT, THP, DW8, XD2…
Eligiendo Audi: TDI, QUATTRO, TFSI, FSI, AVANT, SPORTBACK. O sea versiones, inyecciones y
códigos de motor — y **ningún 206, ningún 307, ningún A3**.

Dos causas, las dos en el patrón que junta los candidatos:

- **El modelo que es un número se descartaba por ser número.** Peugeot 206, Fiat 600, Mercedes
  1620: son modelos, y la regla los tiraba junto con los años y las medidas.
- **El de dos caracteres no llegaba al mínimo de tres.** A3, A4, Q7, X5.

Y las palabras que sí entraban estaban arriba de todo porque la lista va por frecuencia: TDI
está en miles de descripciones. Ni la inyección ni la carrocería son un modelo, así que ahora
se descartan por nombre (TDI, HDI, TDCI, JTD, FIRE, ZETEC, QUATTRO, AVANT, BREAK…). Los
CÓDIGOS de motor se quedan —DW8, TU5JP4, EW10J4 identifican una aplicación de verdad— pero
dejan de tapar a los modelos.

    antes  PEUGEOT → HDI, PARTNER, BOXER, EXPERT, THP, DW8, XD2, CIT, XD3, TU5JP4…
    ahora  PEUGEOT → 306, 206, PARTNER, 307, 405, 406, 207, 106, 205, 505, BOXER, 504…

    antes  AUDI → TDI, QUATTRO, TFSI, FSI, AVANT, CABRIOLET, SPORTBACK, FAHR…
    ahora  AUDI → A3, A4, A6, A5, Q5, A1, Q7, Q3, A2, A8, S3, A7…

Cada candidato sigue pasando por el mismo filtro de siempre —solo queda si aparece casi
siempre dentro de esa marca— así que un número que además es una medida se cae ahí.

## «PALIO/SIENA/UNO» eran tres autos y se guardaba uno

Al leer de las descripciones a qué auto le va cada repuesto, de cada marca nombrada se tomaba
**el primer modelo y nada más**. Las listas escriben «FIAT PALIO/SIENA/UNO 1.3» y «RENAULT
CLIO MEGANE KANGOO», así que el repuesto desaparecía del catálogo de los otros: de 41.857
productos, 35.061 quedaban con UNA sola aplicación.

Tomando todos los modelos de cada tramo —cada uno validado igual contra los que la app
reconoce para esa marca— las aplicaciones pasan de **52.534 a 120.691**, y los productos con
una sola bajan de 35.061 a 15.602.

Eso mueve dos cosas más: el barrido por descripción encuentra 8.661 pares en vez de 8.122
(cada producto sabe a qué autos va aunque su descripción no los nombre), y el cruce por
aplicación pasa de 146 a 3.300 pares —todos con las dos condiciones nuevas puestas, así que
son pares como «SENSOR ABS JEEP COMPASS/PATRIOT» contra «SENSOR ABS JEEP COMPASS/PATRIOT 2.4»
y no cinco sondas distintas colgadas del mismo código.

## Cruzar por auto: 32.768 sugerencias de las que servían 146

Si dos fabricantes dicen que su pieza va exactamente a los mismos autos, las dos hacen el mismo
trabajo. Eso es lo que cruza `derivar_equivalencias_de_aplicaciones()`, y funcionaba bien
mientras la tabla de aplicaciones se llenaba solo con el catálogo que manda un fabricante: unos
cientos de filas.

Desde que se leen de las descripciones son **52.534**, y ahí «mismo tipo de pieza y mismo auto»
deja de alcanzar. Lo que proponía:

    0258001027 (OEM)  ↔  80034FISPA      13 autos
    0258001027 (OEM)  ↔  80039FISPA      13 autos
    0258001027 (OEM)  ↔  80041FISPA      13 autos
    0258001027 (OEM)  ↔  LECS012LUCAS    13 autos
    0258001027 (OEM)  ↔  LECS025LUCAS    13 autos

Cinco sondas lambda **distintas** —se diferencian en los cables, el largo y la ficha— colgadas
del mismo código de Bosch por ir a los mismos trece autos. Así salían **32.768 pares**.

Dos condiciones nuevas, y las dos son la misma idea: lo que la tabla guarda es más grueso que
antes, así que hay que pedir más.

- **El «fabricante» no puede ser OEM / FABRICA.** Esa marca no es el catálogo de nadie: son los
  códigos de fábrica que la propia app dedujo. Cruzarlos por aplicación propone el mismo
  vínculo que ya hace el puente por código, pero sin la certeza del número. Quedan 1.987.
- **Las descripciones tienen que coincidir**, con el mismo criterio de siempre. El tipo de
  pieza que se guarda es la FAMILIA —21 en total— y eso mete todas las sondas del auto en la
  misma bolsa. Quedan **146**.

De paso, los productos se buscan de a tandas: eran dos consultas por candidato, o sea 65.536
consultas para los 32.768 candidatos. Ahora tarda 7,3 s en vez de 12,6.

Y hay un efecto de arrastre que vale la pena anotar: con las 52.534 aplicaciones cargadas, el
barrido por descripción encuentra **8.885** pares en vez de 8.122, porque cada producto sabe a
qué autos va aunque su descripción no los nombre.

## Las palabras que decían para qué auto es, sin ser un auto

Para aceptar una sugerencia hay que contestar dos preguntas: **qué pieza es** y **para qué auto
es**. La segunda se contestaba con cualquier palabra que no estuviera en la lista de nombres de
pieza — y esa lista estaba armada para otra cosa (el desplegable de vehículos), así que le
faltaba medio vocabulario del rubro eléctrico.

Contando qué palabras entraban del lado del AUTO en las descripciones reales:

    REF 11.421   SENSOR 3.988   CANO 2.188   ARRANQUE 2.074   ROTACION 1.743
    BULBO 1.298  TODOS 1.251    PRESION 1.057  BOBINA 1.012   INYECTOR 968 …

Ninguna es un auto. Con eso adentro, dos sensores de detonación de autos distintos «coincidían
en para qué auto es» porque los dos decían SENSOR y DETONACION.

Se partió en dos, y la diferencia importa:

- **Nombres de pieza** (SENSOR, BULBO, BOBINA, IGNICION, SONDA, LAMBDA, INTERRUPTOR, CANO,
  RADIADOR, MAP, ABS…) → pasan al lado de la PIEZA, donde sirven para distinguir un «SENSOR DE
  ROTACION» de un «SENSOR MAP».
- **Relleno** (REF, OEM, TODOS, DESDE, HASTA, LIVIANA, PESADA, VOLTS, DIAMETRO, VIAS…) → salen
  del núcleo entero. Ponerlos del lado de la pieza fue el primer intento y se llevó puestos
  1.308 pares buenos: «BOBINA DE IGNICION … REF ORIG» dejaba de parecerse a «BOBINA … desde
  2012» porque REF y DESDE contaban como parte del nombre de la pieza.

Y una vez que el vocabulario quedó limpio hubo que aflojar una regla: se pedían DOS palabras de
pieza en común, y cuando el que menos dice nombra la pieza con UNA sola —«BOBINA» contra
«BOBINA DE IGNICION»— pedirle dos es pedirle algo que no escribió. Ahora con una alcanza, si
esa está del otro lado **y** además comparten el modelo del auto y no solo la marca. El caso
que la regla de dos cuidaba sigue cuidado: «Juego de juntas para Caja de Velocidad FORD F100»
contra «Jta.Tapa Valvulas FORD F100» comparten JUNTA y nada más, pero el que menos dice nombra
tres palabras, así que la contención falla igual.

## CHEV y CHEVROLET eran dos marcas distintas

La firma buscaba cada marca de vehículo como subcadena, sin resolver los alias. Consecuencia:
un proveedor que escribe «Chev Corsa» y otro que escribe «CHEVROLET CORSA» daban **«autos
distintos»**, que es un rechazo tajante, antes de mirar nada más. Lo mismo con PEUG/PEUGEOT,
CITR/CITROEN, VW/VOLKSWAGEN y MERCEDES-BENZ/MERCEDES: **3.705 descripciones** del catálogo
real.

Y al revés, de yapa: el camión **BED FORD** —147 descripciones, escrito partido— no estaba en
la lista de marcas, así que la app leía FORD y una junta de diferencial de un Bedford podía
emparejarse con cualquier repuesto de un Fiesta.

Las dos cosas se arreglan usando `marcas_vehiculo_en()`, que ya resolvía los alias y elige
siempre la marca más larga, en vez de buscar subcadenas a mano.

Todo junto, sobre el barrido del catálogo real: **5.597 → 8.122 sugerencias**, con la confianza
media un poco mejor (56,8 → 59,2) y el mismo 3% naciendo en rojo. Y el tope pasó a 20.000
porque 8.000 volvía a cortar justo, ahora ordenando antes de cortar: si alguna vez se llega,
lo que queda afuera son los peores y no los que el recorrido tocó último.

## Cuando el modelo del auto es un número

Un Fiat 128, un Fiat 600, un Peugeot 404, un VW 1300, un Mercedes 1620: en los autos viejos y
en los camiones **el modelo ES un número**, y la firma los tiraba a todos junto con los años y
las medidas, por la regla de «lo que es puro número no dice qué pieza es».

Se veía en las sugerencias. De estas dos descripciones,

    Jgo.Jtas.Carburador FIAT 125
    Juego de juntas para Carburador FIAT 1600 128 …

lo único que quedaba era la palabra FIAT, y con eso el par pasaba. Y al revés, dos juntas del
MISMO 128 no tenían nada específico en común que las hiciera subir en la lista.

Ahora un número de 2 a 4 dígitos que viene **justo detrás de la marca del auto** cuenta como
modelo. Se pide esa posición porque es como se escriben, y deja afuera lo que no lo es: los
años (se descartan aparte), los códigos internos del proveedor —los de FISPA son de 5 dígitos,
«SENSOR DE DETONACION 12006»— y la cilindrada de las listas que la escriben separada («FIAT
PALIO 1 3»), que es de un dígito.

Con eso el modelo numérico entra además al mismo criterio que la cilindrada, las siglas y la
posición: **si las dos descripciones lo declaran y no comparten ninguno, son de autos
distintos**. Medido sobre el barrido del catálogo real: 146 pares nuevos que antes no se
encontraban (FIAT 128 ↔ FIAT 128 EUROPA, FIAT 600 ↔ FIAT 600 D/E/R, DEUTZ 913 ↔ DEUTZ 913) y
118 cortados que estaban mal (Citroën C3/C4 Picasso contra Peugeot 405/505, Alfa 166 contra
Fiat 500, BMW serie 7 contra BMW 135).

Hizo falta una salvedad para no cortar de más: como el número se reconoce solo detrás de la
marca y las listas encadenan modelos («FIAT 128 EUROPA 147 DUNA»), del segundo en adelante no
quedan anotados. Antes de cortar se mira si el número del otro aparece en algún lado de la
descripción; sin eso, «FIAT 147 DUNA» contra «FIAT 128 EUROPA 147 DUNA» —que son la misma
junta— salía como «modelos distintos».

## Un caché que no se refrescaba nunca

Streamlit **no hashea los parámetros que empiezan con guion bajo** — es su forma de decir «esto
no entra en la clave del caché». Cinco funciones de la app recibían el testigo del catálogo
como `_version`:

    descripciones_por_palabra(_version)     el conteo de palabras de todo el catálogo
    codigos_del_catalogo(_version)          los códigos que el extractor usa de desempate
    modelos_de_marca(marca, _version)       los modelos del desplegable de vehículos
    catalogo_por_vehiculo(marca, _version)  lo que se ofrece para cada auto
    marcas_vehiculo_disponibles(_version)   qué marcas aparecen en las descripciones

O sea que se calculaban **una vez por arranque de la app** y después devolvían siempre lo
mismo. Justo lo contrario de para lo que existe el testigo: importabas una lista nueva y la
pantalla de vehículos seguía mostrando los modelos viejos, y el extractor seguía sin conocer
los códigos recién cargados, hasta reiniciar.

Es un error que no se ve leyendo la función: se ve en el nombre del parámetro. Por eso va
además como chequeo del auditor (el 26), que lo marca en rojo si vuelve.

## El barrido: siete veces más relaciones por tres segundos

El barrido de todo el catálogo no compara todo contra todo —serían seis mil millones de
pares— sino los que comparten alguna palabra **poco común**. Dónde cortar ese «poco común» es
la decisión más cara de ahí, y estaba en 40 sin haberla medido nunca. Corriendo sobre el
catálogo real y cambiando solo ese número:

| corte | sugerencias | tiempo | confianza media | nacen en rojo |
|---|---|---|---|---|
| 40 | 807 | 15,9 s | 51,5 | 1% |
| 100 | 2.280 | 16,2 s | 52,4 | 2% |
| **250** | **5.597** | **18,8 s** | **61,4** | **1%** |
| 500 | 11.899 | 26,4 s | 45,4 | 41% ← se rompe |

Con 40 se perdían **siete de cada ocho** relaciones buenas para ahorrar tres segundos. Y el
límite de verdad está entre 250 y 500: pasando de ahí entran los pares que solo comparten la
marca del auto y dos palabras genéricas —un «INTERRUPTOR STOP FORD» contra otro «INTERRUPTOR
STOP FORD» de otro modelo— y cuatro de cada diez nacen ya en rojo.

El tiempo casi no se mueve entre 40 y 250 porque **lo caro no es comparar**: de los 18,8 s,
15,2 son leer las 46.644 descripciones y sacarles la firma. Eso ahora va cacheado por versión
del catálogo (17 MB, 0,4 s en volver a leerlo), así que:

    barrido, primera vez     19,6 s
    barrido, otra vez         4,0 s
    comparar dos proveedores 14,5 s → 5,4 s   (usa las mismas firmas)

Y las sugerencias salen **ordenadas de mejor a peor** — primero el modelo compartido, después
la cilindrada, el nombre de la pieza y la marca. Con 807 daba igual el orden; con 5.597 no:
nadie revisa 5.597 de una sentada, y el que revisa las primeras cincuenta tiene que estar
viendo las cincuenta mejores.

## El kit se muestra, pero no como un reemplazo

Buscando la bujía `LSPFR6F11LUCAS` el kit `L206LUCAS` («KIT CAB Y BUJ (LEIHTT66SC/LSPFR6F11)»)
aparecía en la tabla de resultados como una fila más, con su confianza 🟢 y todo. La tabla de
resultados quiere decir una cosa sola: **esto se lo podés vender en lugar de lo que te pidió**.
Y un kit no: trae otras cosas y cuesta otra plata. Al revés tampoco — la bujía suelta no
reemplaza al kit.

Sacarlo de la tabla sería peor, porque es la venta más grande del mostrador. Así que se queda,
y la fila dice qué es:

    LSPFR6F11LUCAS   FISPA       — el buscado
    LSPFR6F11        OEM         🟢 directo                                🟢 sólida
    ZFR6F-11         MOTORARG    🟢 directo                                🟢 sólida
    L206LUCAS        FISPA       📦 kit que la trae adentro — NO es lo mismo
    LEIHTT66SC       OEM         ⚪ código de fábrica, nadie más lo tiene

Y al revés, buscando el kit, las piezas salen marcadas «🧩 va adentro del kit — NO es lo
mismo». Además:

- **No cuentan como equivalencia** en el cartel de arriba («8 equivalencias» y no 9).
- **No compiten por «el más barato en stock»** ni entran en la comparación de margen: el kit
  casi siempre sale más caro, y coronarlo sería comparar dos ventas distintas.
- **No llevan confianza**: la pregunta «¿es la misma pieza?» ya está contestada, y es que no.

La relación se calcula con los dos textos y nada más —la misma `_uno_trae_al_otro()` que usa la
cola de revisión— así que no cuesta una sola consulta de más. Y las dos secciones de abajo
siguen estando, que son las que encuentran el kit **aunque no haya ningún vínculo cargado**:
salen de que el proveedor escribe adentro de la descripción del kit los códigos de lo que trae.

## Tres formas de inventar un código de fábrica

Sobre las descripciones reales, adivinando códigos salían 17.499 distintos. **307 no eran
códigos**, y los tres motivos se pueden nombrar:

**El «REF» de «REF ORIG» pegado atrás.** Una de las listas escribe
`PEUGEOT 404 - 504 - 505REF ORIG 024210`, y de ahí salían 212 códigos terminados en REF:
`505REF` (el modelo), `1995REF` y `2003-2012REF` (los años), `70010REF` (el número interno del
proveedor). La regla que despega ese REF ya existía —se usa para que el desplegable de
vehículos no muestre «16VREF» como si fuera un modelo— pero no se aplicaba acá. Y mientras
estaba pegado tapaba el mejor dato que trae la lista: **«REF ORIG» es el proveedor diciendo
cuál es el código de fábrica**, y sin reconocer el marcador el número que sigue queda como una
adivinanza más.

**La marca pegada al número.** `4EC1TBOSCH=0250202087` son tres cosas: el motor 4EC1T, la marca
y el código. El igual no separaba nada, así que entraba todo junto — y un código con la marca
adelante no cruza con nadie, porque nadie más lo escribe así. Separado por el igual y
despegada la marca de atrás (`26001FISPA`, `2015NGK`, `tu5pjp4NGK`), lo que queda cuando
adelante había una motorización lo descartan las reglas de siempre, que con la marca pegada no
la reconocían.

**La lista de modelos.** `106-206-306-406-607`, `307-308-408-208-3008-C4`,
`316-318-320-325-330-520-530-540-X3-X5-Z3-Z4`. Son los peores códigos inventados que hay,
porque cada uno cuelga de sí mismo todo lo que nombre esos autos. Se piden tres segmentos de
TRES dígitos y ninguno de más de cuatro caracteres, y ahí está todo el cuidado: los códigos de
fábrica con guiones o tienen un segmento largo (`8-01115-315-0` de Isuzu, `7700747549-7700850589`
de Renault) o no llegan a tres segmentos de tres (`06K-905-601-B` de VW). Medido contra los
70.888 códigos del catálogo: marca 25, y los 25 son listas de modelos.

En total salen 307 y entran 10, y entre los que entran están los códigos que estaban tapados:
`0250202087` de Bosch, `7700105290` de Renault, `93183739` de GM, `TG15C020`.

## El caracter de control que Excel escribe con letras

`INYECTOR FI-0280155888_x001f_Ford Ka 1.0 8V` — ese `_x001f_` es cómo Excel escribe un caracter
de control que quedó adentro de la celda, y llega tal cual, como siete caracteres de texto.
Pega dos palabras y arruina las dos: de ahí salió un producto con el código
`FI-0280155888_x001f_Fo`. Se cambia por el espacio que había cuando se lee la celda, así que no
depende de qué columna sea.

## Los topes que escondían trabajo

«Se revisaron 8.000 vínculos y ninguno quedó por debajo del umbral» se lee como «está todo
bien». En la base real hay **24.774**: faltaba el 68%. Revisarlos todos cuesta 10,5 s contra
3,9 s, o sea que el tope ahorraba seis segundos y escondía 16.774 vínculos.

No era el único. Los que cortaban de verdad sobre el catálogo real:

| Dónde | Antes | Ahora | Lo que costaba |
|---|---|---|---|
| Revisar los vínculos ya cargados | 8.000 de 24.774 | todos | 3,9 s → 10,5 s |
| Contar los rojos de una importación | primeros 600 | todos | 1,4 s → 6,6 s |
| Analizar los pendientes de una lista | arrancaba en 1.000 | arranca cubriendo la lista entera | 3.185 en 6,6 s |
| Comparar dos proveedores por descripción | 4.000 de cada lista | 50.000 | 4,4 s → 16,5 s |
| «Descargar lista completa» de huérfanos | 2.000 de 34.457 | todos | 0,1 s |
| Leer aplicaciones de las descripciones | 400 de 52.534 | todas | 12,2 s → 30,6 s |

Dos de esos no eran lentitud, eran un número equivocado a la vista: el informe de importación
decía «N de los 3.185 vínculos nuevos están casi seguro mal» contando N sobre 600, y el botón
que dice «descargar lista **completa**» bajaba 2.000 de 34.457.

Y el de 4.000 era el peor de todos porque no es aleatorio: las filas que quedaban afuera eran
**siempre las mismas** —las últimas de cada lista— corrieras la comparación las veces que la
corrieras. Sobre JL, que tiene 25.975 productos, era el 85% del proveedor que no se comparaba
nunca. Sacándolo, JL × MOTORARG pasa de **11 sugerencias a 776**.

## El kit que se citaba a sí mismo

Un juego de juntas de Illinois se llama «Juego de juntas para Carburador PEUGEOT 405 GL SR
SOLEX **1433630**», y de esa misma descripción sale el código de fábrica 1433630, que queda
cargado como producto OEM con la descripción idéntica.

Cuando después se comparaban esos dos, la app encontraba el número del OEM adentro del texto
del kit y concluía lo peor posible: **«no son equivalentes, el kit lo trae adentro»**, −40 de
confianza. Es justo al revés: ese par es el puente entre el proveedor y el código original, el
vínculo que más sirve de toda la base.

Los números de la base real, con `_uno_trae_al_otro()` sin arreglar:

    786 de los 3.185 pendientes      marcados «no son equivalentes» — 598 con las dos
                                      descripciones IDÉNTICAS
  1.054 de los 24.774 ya cargados    lo mismo
    100% de los dos grupos           eran OEM contra PROVEEDOR

Un kit y su pieza suelta son dos productos que un proveedor vende por separado. Un código de
fábrica no es ni un kit ni una pieza suelta: es el número con el que la fábrica llama a una de
las dos, y del otro lado siempre está el producto del que salió ese número. Con que uno de los
dos lados sea OEM, no hay nada que mirar.

Los «🔴 casi seguro mal» de la lista de Illinois pasan de **938 a 379**.

## Un kit y su pieza no se preguntan

Cuando la relación es de verdad —dos productos de proveedores distintos, uno es el kit y el
otro la pieza que viene adentro— tampoco hay nada que decidir: no son intercambiables, así que
no van a la cola de revisión. `pares_de_kit_y_pieza()` los saca antes de guardarlos, y los que
ya estaban se muestran en una línea con un botón para descartarlos juntos, en vez de aparecer
mezclados con los que sí hay que mirar.

El buscador los sigue ofreciendo como kit cuando alguien busca la pieza suelta: eso lo resuelve
`kits_que_lo_traen()` leyendo las descripciones en el momento, sin necesidad de que el vínculo
esté cargado.

## «Ya cargué el catálogo de esa marca y no figura»

Dos cosas distintas se llamaban igual: la **lista de productos** de un proveedor y la
**dirección web** de su catálogo, que es la que hace falta para ir a leer las referencias
cruzadas de cada ficha. La pantalla decía «ninguna marca tiene cargada la dirección de su
catálogo» sin nombrar ninguna marca, y eso se lee como «no ve mi lista».

Ahora el aviso nombra los proveedores que sí están cargados y aclara que lo que falta es el
link, y la tabla de Administrar → Marcas tiene una columna **Catálogo web** que dice cuál lo
tiene y cuál no.

Y había un error que hacía parecer cargado lo que no lo estaba: el campo del patrón usaba una
sola clave para todas las marcas. Streamlit, con la clave puesta, se queda con lo último
tipeado e ignora el valor que le pasás, así que al cambiar de marca el campo seguía mostrando
la dirección de la anterior —y si apretabas Guardar, se la copiabas a esta—. La clave ahora
lleva el id de la marca.

## «1,6» y «1.6» no eran la misma cilindrada

Illinois escribe la coma —3.105 descripciones de esa lista— y todos los demás el punto: son
23.244 con punto contra 4.534 con coma, y las dos poblaciones casi no se mezclan porque cada
proveedor escribe siempre igual.

Comparadas tal cual, las cilindradas de las dos listas **nunca se cruzan**, y la comparación
corta con «cilindradas distintas» antes de mirar nada más. Sobre 1.500 × 1.500 productos
reales eran **796 pares rechazados por cómo se escribe un número**. La pantalla de vehículos
ya pasaba la coma a punto antes de comparar; en la firma faltaba.

De paso arregla otra cosa que no se veía: la coma no era un caracter de palabra, así que
`1,9TDI` se partía en `1` y `9TDI`. Ese `9TDI` suelto —129 veces en el catálogo— quedaba en la
firma como si fuera un modelo, y hermanaba un 1,9 TDI con un 2,9 TDI.

Lo que aparece cuando se arregla son pares como este, que estaban a la vista:

    Junta Salida de Escape FORD SIERRA 1984/... - 1,6 - OHC   ↔   Jta.Salida Escape FORD SIERRA 1.6
    Juego de juntas Carburador FIAT DUNA UNO - 1,4/1,5/1,6    ↔   Jgo.Jtas.Carburador FIAT DUNA 1.6
    Junta para Cárter FIAT IVECO DUCATO - 2,4/2,5/2,8         ↔   Junta carter Fiat Ducato 2.8L Goma

## «16V» no es un auto

Para aceptar una sugerencia hay que contestar dos preguntas: qué pieza es y **para qué auto
es**. La segunda se contestaba con cualquier palabra que no fuera el nombre de la pieza, y ahí
entraban la cilindrada y la cantidad de válvulas. `16V` está en 3.513 descripciones.

Cuando una de las dos descripciones no nombra ninguna marca de vehículo conocida —pasa
seguido, la marca va pegada o abreviada— eso era **lo único** que quedaba. Los 43 pares que
salieron al sacarlo son todos el mismo error, motores distintos de la misma marca:

    Junta Tapa Cil. HILUX D-4D 2KD-FTV      ↔  Jta.Tapa Cil. TOYOTA 1ZZ-FE (el Corolla)
    Junta Tapa Cil. PEUGEOT 306 406 XU7JP4  ↔  Junta tapa cil. Peugeot 206-307 TU5JP4
    Junta Tapa Cil. FIAT FREEMONT 2.4       ↔  Jta.Tapa Cil. Fiat Punto 1248CC
    Junta Tapa Cil. HYUNDAI ATOS 999CC      ↔  Jgo.Jta.Tapa Cil. HYUNDAI SONATA 2972CC V6

y los 17 que entraron en su lugar comparten el modelo, no el motor genérico.

Dos cosas que costaron medirlas:

- **Se descuenta al aceptar, no en la firma.** Sacar la cilindrada de la firma cambia también
  el ORDEN de los candidatos —de cada producto se guardan los tres mejores— y con eso se
  perdían pares buenos («Jta.Tapa Cil. RENAULT CLIO II», «JUNTA TAPA CILINDROS FORD M. ZETEC»)
  a cambio de otros. Para ordenar, la cilindrada sí sirve: confirma la aplicación.
- **La cilindrada exacta en centímetros cúbicos se queda.** `843CC` no es una forma de hablar,
  es un motor: es lo único que une la junta del ASIA/KIA TOWNER con la del DAIHATSU HI-JET, que
  son el mismo auto con dos nombres. Y el patrón pide la coma decimal o la V de las válvulas
  justamente para no llevarse puestos los modelos que son número y letra: 320I, 318I, 525D,
  310D y 412D son BMW y Mercedes de verdad.

## Un código que apunta a ocho piezas

Cuando una lista nueva deja cientos de pendientes, casi nunca son cientos de problemas: son
unos pocos códigos malos repetidos. Para eso está el aviso «N producto(s) con código dudoso
generan X de estos pendientes», que los resuelve de una en vez de vínculo por vínculo.

Con la lista de Illinois **ese aviso no aparecía nunca**. La única condición era
`codigo_sospechoso()` —forma rara, letra suelta, número corto— y sobre esa lista da **cero**,
porque los culpables tienen forma perfecta de código de fábrica:

    MAXIONS4     8 pendientes   el motor Maxion S4
    7679315      7              un número de camión
    MB616.912    4              el OM 616 de Mercedes-Benz
    OHL355       4              el OH L-355
    BENZ813913   4              el 813 y el 913

`productos_que_mas_ensucian()` los busca ahora por lo que hacen, no por cómo se escriben: un
código de **FÁBRICA** que apunta a 3 o más productos **del mismo proveedor**. Un código de
fábrica identifica UNA pieza; si señala a ocho del mismo catálogo, o no es un código o la lista
lo cita en piezas que no lo llevan. Son 15 culpables y 67 pendientes, en 0,0 s.

El corte es por proveedor (`GROUP BY po.id, mp.id`) y no por total: un código de fábrica
legítimo aparece en varias listas a la vez —es justo para eso que sirve— y contando todo junto
ese sería el primero de la lista.

## Que la app no se caiga, y que un reinicio no borre nada

En el Streamlit Cloud gratis la app «se cae» de tres maneras. Las tres se miraron con números.

### 1. Diez tandas de fondo donde tenía que haber una

Streamlit vuelve a ejecutar `app.py` entero en cada toque, **en un módulo nuevo**. Todo lo que
se crea arriba de todo con `= threading.Lock()` o `= []` es otro objeto en cada pasada. El
candado de la tanda de fondo (`_CANDADO_FONDO`) estaba así: cada toque traía uno nuevo y
libre, y la regla de «una sola tanda a la vez» no se cumplía nunca. Probado con una base con
trabajo de fondo pendiente, contando los hilos por nombre con `py-spy`:

| el mismo recorrido de seis toques | antes | ahora |
|---|---|---|
| tandas de fondo corriendo a la vez | **10** | **1** |
| pico de memoria del servidor | 535 MB | **275 MB** |
| CPU gastada | 69 s | **14,5 s** |

El trabajo es el mismo (24.774 vínculos puntuados, ninguno sin puntaje): se hacía diez veces.
Ahora esos objetos viven en `del_proceso()`, que los guarda donde Streamlit no los toca entre
pasadas. Pasó lo mismo con el registro de errores (`_ULTIMOS_ERRORES`): la pantalla que los
muestra veía solo los de su propia pasada, y los de los hilos de fondo no los veía nadie.

`db_lock` tiene el mismo problema y **se dejó así a propósito**, con el porqué al lado: las
escrituras entre sesiones ya las ordena SQLite (WAL y `busy_timeout`), y volverlo del proceso
abre una traba —uno con el candado esperando la base, otro con la base esperando el
candado— que hoy no existe.

### 2. La copia en GitHub: casi nunca se subía

Con los secretos configurados, la copia se subía **una vez por día**, como último paso de las
tareas diarias y dentro de sus seis segundos (si los pasos de antes los gastaban, ese día no
había copia). Además se subía **solo si había más productos que en la anterior**: aprobar 8.000
equivalencias, cambiar precios, anotar ventas o cargar fichas de autos no la disparaba. Todo eso
vivía solo en un disco que se borra al reiniciar.

Ahora:

- **Se sube cuando cambia algo.** Un hilo (`vigilar_la_copia()`) arma la copia cada 15 minutos,
  le saca una huella (sha256) y la sube solo si cambió. Armarla cuesta 0,7 s. La huella deja
  afuera la tabla de configuración, porque ahí van marcas que cambian solas; la copia subida
  sí la lleva. Lo máximo que se pierde en un reinicio son 15 minutos.
- **Va a una rama propia, `copia-de-seguridad`, con un solo commit** que se reemplaza cada vez.
  Con un commit nuevo por copia en `main`, a 11 MB cada uno, el repositorio engordaría gigas por
  año, y cada copia chocaría con los cambios de código. Si en los secretos se pone
  `github_rama`, se usa esa como antes, con un commit por copia: a `main` no se le puede
  reemplazar el historial.
- **Al arrancar con el disco vacío, la app la baja sola** (`bajar_la_copia_de_github()`), con
  10 segundos de tope para conectar. Si GitHub no contesta, sigue con la del repositorio.
- **Nunca pisa la copia buena con una mala.** Si GitHub no contestara justo al arrancar, la app
  arrancaría vacía, o con la copia vieja del repositorio, y a los 15 minutos el vigía la
  subiría encima de la buena. Por eso: una base vacía no se sube nunca, y una base que no viene
  de la copia (no tiene su huella) no reemplaza sola una copia que ya existe. Avisa, y deja la
  decisión al botón de «Subir ahora».

Probado de punta a punta contra un GitHub de mentira que responde como la API de git (la
variable `EQUIVALENCIAS_API_DE_GITHUB` sirve solo para eso). El servidor de verdad subió la
copia solo. Después se lo apagó, **se le borró la base**, se lo prendió y arrancó con los 70.893
productos y las 24.774 equivalencias. En la primera revisión, al minuto de arrancar, no la
volvió a subir, porque no había cambiado nada. Aparte, en diez casos:

| caso | resultado |
|---|---|
| primera copia | crea la rama, 1 commit, la copia y un LEEME |
| sin cambios | no sube |
| solo cambió la configuración | no sube |
| cambió un precio | sube; la rama sigue con 1 commit |
| base restaurada de la copia | la reconoce y no la vuelve a subir |
| restaurar sobre una base con datos | no toca nada |
| base que no viene de la copia | no pisa la de GitHub; avisa |
| base vacía, aun con el botón | no sube |

Hubo un error en el camino que vale anotar: la huella se sacaba leyendo el archivo con la
conexión abierta. La copia hereda el modo WAL, lo escrito va primero a un archivo aparte, y la
misma base daba a veces otra huella. Ahora se lee con la copia cerrada.

### 3. Dormida

Streamlit apaga las apps gratis que pasan 12 horas sin visitas. La primera persona de la mañana
ve un cartel, toca «Yes, get this app back up!» y espera, y el servidor arranca de cero.
`.github/workflows/mantener_despierta.yml` abre la app cada 4 horas en un navegador de verdad
(`.github/despertar_la_app.py`). Si la encuentra dormida la despierta, y si no aparece en 4
minutos el trabajo falla: **GitHub le manda un mail al dueño del repositorio**, y eso sirve de
alarma de «la app está caída». Se puede correr a mano desde Actions → «Mantener la app
despierta» → Run workflow. Probado con la app andando, con una página que imita el cartel de
dormida (la despierta) y con una que nunca despierta (sale con error).

Lo que no depende de la app: Streamlit puede reiniciar el servidor cuando quiera
(mantenimiento, actualizaciones). Con lo de arriba, eso cuesta como mucho 15 minutos de datos,
no todo.

## Celular o computadora: se elige sola

La vista arrancaba **siempre** en «📱 Celular». El que entraba desde la computadora la tenía que
cambiar a mano cada vez, porque el selector no se guarda entre visitas. Ahora se elige según el
navegador: si dice «Mobi» (así se presentan Chrome y Firefox en Android, Safari en iPhone,
Samsung Internet) es celular, y si no, computadora. Una tablet Android no dice «Mobi» y un iPad
se presenta como una Mac, así que las dos quedan en vista de computadora, que es lo que les va
con esa pantalla. Si no se puede saber, queda en celular, como antes. El selector sigue estando
para cuando no acierte, y una vez tocado manda lo que se eligió.

Probado con los perfiles de navegador reales de iPhone 13, Pixel 7, Galaxy S9+ (celular), Galaxy
Tab S4, Chrome y Firefox de escritorio (computadora), y cambiándola a mano en el iPhone: sigue
en computadora después de moverse por la app.

**Una trampa de Streamlit.** La primera versión guardaba lo detectado en
`st.session_state["modo_vista"]`, que es la clave del selector. En la pantalla de entrada el
selector todavía no existe, y cargar su clave antes de que exista deja a Streamlit con el valor
bueno y a la pantalla mostrando la primera opción. En la computadora se veía el CSS de
computadora con el selector diciendo «Celular», y al primer toque la pantalla le devolvía su
valor y la vista se daba vuelta sola. Reproducido en una app de diez renglones. Ahora lo
detectado entra como opción inicial del selector (`index=`), y la clave la escribe solo el
selector.

## Los botones del celular no eran anchos, aunque el CSS decía que sí

El CSS del celular pedía botones a lo ancho (`.stButton > button { width: 100% }`), pero en esta
versión de Streamlit el botón está uno o dos niveles más adentro (más todavía si tiene ayuda) y
la caja de afuera se achica al texto. La regla no agarraba nada: en el celular, «🔍 Buscar
Equivalencias» medía 169 px de 336. Ahora todos van a lo ancho, que es más fácil de acertar con el
pulgar. De paso, las métricas van de a dos por renglón en vez de una. En «Equivalencias
sugeridas» las seis ocupaban una pantalla entera antes de llegar a lo que hay que revisar.

## Revisar los sospechosos: de 315 decisiones a 45

En «Equivalencias sugeridas», los vínculos para revisar se agrupan por motivo, para decidir el
grupo de una vez. Pero se agrupaba por el **texto entero** de la alarma, y el texto trae el
dato de cada par: «se diferencian 25 veces» y «40 veces» eran dos motivos, y lo mismo cada
código ambiguo o cada «DELANTERA+DERECHA vs TRASERA+IZQUIERDA». Además se agrupaba dentro de
cada página de 10, así que un grupo nunca pasaba de 10. Con los datos reales:

| para revisar todo, de a 10 por página | antes | ahora |
|---|---|---|
| ILLINOIS (381 vínculos) | 315 decisiones | **45** |
| BARRIDO (461) | 205 | **52** |
| código escrito en la descripción (241) | 85 | **32** |

`tipo_de_alarma()` saca el dato de cada par («💲 Los precios se diferencian 8 veces o más»,
«📐 NO coinciden: posición»), y la lista se ordena por motivo **antes** de cortar en páginas: primero
el motivo con el peor vínculo, como antes iba primero el peor vínculo. El título dice «10
vínculo(s) (de 286 con este motivo)». El detalle no se pierde, porque la vista de a uno lo
muestra en cada par. Lo que sí cambia la decisión se deja en el motivo y no se junta: los dos
rubros de «rubros distintos», las dos siglas de «siglas distintas», qué medida no coincide.

De paso, **150 de los 12.668 vínculos mostraban la misma alarma dos veces**: «💲 Los precios se
diferencian 19 veces» y abajo «💲 los precios se diferencian 19 veces». El precio y los rubros
los miran dos partes del análisis, cada una con su redacción, y la que evitaba repetir comparaba
el texto exacto. Ahora son 0. Los puntajes no cambian: la repetida solo se mostraba.

## La app en el celular, mirada en un celular

La app se usa desde el teléfono, en el mostrador. Se sacaron capturas con un celular simulado
(390 px de ancho, el de un teléfono común) y se midió dónde queda cada cosa. «Pantalla 4,3»
quiere decir que hay que bajar el dedo tres pantallas y un tercio para llegar.

| en el celular | antes | ahora |
|---|---|---|
| dónde está la caja de búsqueda, al abrir | a 2.787 px: **pantalla 4,3** | a 663 px: **pantalla 1,8** |
| largo de la página, buscando LRSC030120LUCAS (62 resultados) | **17,2 pantallas** | **3,9 pantallas** |
| con el teléfono en modo claro | etiquetas y botones casi ilegibles | igual que en modo oscuro |

**Con el teléfono en modo claro no se leía.** El diseño de la app es oscuro y su CSS pinta el
fondo oscuro sin preguntar, pero Streamlit elegía SU tema según el teléfono: en modo claro ponía
texto gris oscuro y botones blancos encima de ese fondo. «Tu nombre:», «➡️ Continuar» y los «Ir a
arreglarlo →» casi no se veían. Lo arregla `.streamlit/config.toml`, que fija el tema oscuro
con los mismos colores del CSS. Si se cambia un color, hay que cambiarlo en los dos lados.

**La caja de búsqueda estaba abajo de todo.** Antes de ella había, en este orden: el encabezado
con su subtítulo, las alertas de salud abiertas (seis, cada una con su explicación y su botón), el
«para qué sirve» de la página, la guía rápida y el cartel de lo que espera aprobación. En el
celular ahora:

- las alertas van plegadas en una sola línea («🔴 6 cosa(s) que conviene mirar hoy · 🟡 …»), y
  se abren con un toque;
- el encabezado queda solo con el nombre;
- el «para qué sirve» no aparece en el buscador, que se entiende solo;
- la guía y el cartel de pendientes van **debajo** de la búsqueda, y el cartel en una línea.

En la computadora no cambia nada. La pantalla es ancha y todo eso entra sin tapar la búsqueda.

**124 botones para decir qué se llevó el cliente.** Abajo de los resultados, cada uno tenía su
par «🛒 Se llevó» / «📌 Pedir». En el celular las columnas se apilan, así que con 62 resultados
eran 124 botones del ancho de la pantalla, uno abajo del otro: 13 de las 17 pantallas. Hasta 5
resultados sigue igual, que es un toque. Con más aparece un selector «¿Cuál? (62 resultados)» y
los dos botones una sola vez. El selector elige por ID y no por el texto, porque dos productos con
la misma marca, código y stock darían el mismo rótulo y uno taparía al otro.

**Tocar «Se llevó» no mostraba nada.** Tampoco «Pedir». La venta se anotaba, pero la pantalla
no daba ninguna señal, y en el celular eso invita a tocar de nuevo. Cada toque de más es otra venta, que después pesa en
«Equivalencias sugeridas» como si el cliente hubiera vuelto, y otro «veces pedido» en
reposición. Ahora aparece un aviso flotante: «🛒 Anotado: se llevó FISPA - LRSC030120LUCAS». Es
flotante (`st.toast`) y no el `avisar()` de siempre porque `avisar()` escribe arriba de todo, y en
el celular uno está abajo, mirando el resultado.

**Un detalle del CSS:** las opciones de los grupos de botones redondos (`st.radio`) se dibujan
como pastillas. La regla era `.stRadio label`, que agarraba también el **título** del grupo, así
que «Buscar por:» aparecía como una pastilla más, igual que las opciones. Ahora es
`.stRadio [role="radiogroup"] label`: solo las opciones.

## Reimportar una lista volvía a mandar a revisión todo lo ya aprobado

Lo más común en la vida real es que un proveedor mande su lista nueva de precios y se la vuelva
a importar. Se probó con las listas reales, apretando los botones de «📁 Cargar Excel»:
reimportando la de FISPA, que ya estaba cargada, la cola pasó de 12.747 a **26.690** pendientes.

**13.756 de esos 13.943 «vínculos nuevos» ya eran equivalencias aprobadas.** La importación no
revivía lo rechazado (filtraba `rechazados_antes`), pero sí volvía a preguntar por lo aprobado.
Es el mismo agujero que se cerró en el descubrimiento automático, del lado de la importación.

| reimportando la lista de FISPA | antes | ahora |
|---|---|---|
| vínculos «esperando tu revisión» | **13.943** | **187** (los nuevos de verdad) |
| «casi seguro mal», según el informe | «539 de los 13.943» | «117 de los 187» |
| la importación tarda | 23,5 s | **9,5 s** |

Tarda menos porque el informe de después analiza 187 vínculos y no 13.943. Una lista que no
estaba (IMPERIAL, 43.303 filas) deja exactamente la misma base antes y ahora. Las bases que ya
reimportaron algo tienen los repetidos en la cola: `VERSION_COLA_PENDIENTES = "3"` los saca al
abrir.

De paso, el cartel del final decía dos cosas que no eran:

- «**Las 4.446 fila(s)** que traían código de fábrica quedaron esperando tu aprobación», con casi
  todo aprobado de antes. Ahora: «**187 vínculo(s) nuevos** todavía no… Otros 13.756 ya estaban
  cargados de antes y siguen funcionando». Y si la lista no trae nada nuevo, lo dice en verde.
- «Se leyeron 43.303 filas y quedaron cargados **43.347 productos**» —más productos que filas— y la
  marca quedó con 43.101. Sumaba «filas con equivalencia» más «códigos sin equivalencia», que son
  unidades distintas, y un código repetido en la lista contaba dos veces. Ahora cuenta productos
  distintos: 43.101.

Reimportando también las otras tres listas reales (JL, ILLINOIS y la de MOTORARG) aparecieron
dos más del mismo tipo:

- Con la de JL, un cartel decía «se cargaron **25.916** productos que no traían código de
  fábrica» al lado de otro que decía «quedaron cargados **25.912**». El primero sumaba de a código
  por fila, con los repetidos. Ahora cuenta productos distintos, y descuenta los que en otra fila
  de la lista sí trajeron código. (Que JL tenga más productos que filas es correcto: hay celdas
  con dos códigos, «A/B».)
- Con la de MOTORARG, la vista previa dejaba un `ArrowTypeError` largo en el registro en cada
  importación: la columna de códigos mezcla números (`140000`) y textos (`150000-R`) y no se puede
  convertir a tabla tal cual. Streamlit lo arreglaba solo, pero ensuciaba el registro justo donde
  uno mira cuando algo falla. La vista previa ahora muestra todo como texto, que es además lo que
  dice la celda. Barriendo las 31 pantallas no aparece en ninguna otra tabla.

## La copia de seguridad en GitHub: nunca se hizo, y no hubiera aguantado

**En ninguna rama del repositorio hay ni hubo nunca un `datos_iniciales.db`.** O sea: la subida
automática a GitHub no está configurada (o nunca anduvo), y los datos de la app publicada viven
solo en el disco del servidor, que Streamlit Cloud borra al reiniciar. La app lo avisa en rojo
—«No hay copia en el repositorio. Hoy un reinicio borra TODO»—, pero es fácil acostumbrarse a un
cartel. **Esto se arregla configurando dos secretos en Streamlit, no con código:** ver «Backup y
config» en la app.

Revisando el código de la subida para cuando se configure, aparecieron tres problemas:

**1. La copia no iba a entrar.** GitHub no acepta archivos de más de 100 MB. La copia sin fotos de
la base real pesa **60,6 MB**, y por la API viaja en base64: **80,8 MB**. Dos o tres listas más y
deja de subirse justo cuando más hay para proteger. Ahora se sube **comprimida**,
`datos_iniciales.db.gz`: **11,2 MB** en el repositorio, 15 MB en el viaje. Al arrancar, si la
copia está comprimida se descomprime al lado —a un temporal y después se renombra, para que un
arranque cortado no deje una base a medio escribir— y se restaura como siempre. Si hay una
`datos_iniciales.db` vieja sin comprimir, se sigue leyendo cuando es la única; si están las dos,
manda la comprimida. Probado: restaura los 70.893 productos, prefiere la comprimida, y si la
comprimida está rota cae a la otra sin romper nada.

**2. La segunda subida iba a fallar.** Para reemplazar un archivo GitHub exige su `sha`, y la app
lo pedía con el tipo de respuesta de siempre, que devuelve el archivo entero en base64 **solo
hasta 1 MB**. Con una base de decenas de MB no venía el `sha`, y el reemplazo fallaba con
«"sha" wasn't supplied»: la primera copia se subía y ninguna más. Ahora se pide con
`application/vnd.github.object`, que da los datos sin el contenido, y si aun así no aparece se
lista la carpeta, que trae el `sha` de cada archivo.

Desde este entorno no se puede hablar con GitHub, así que esto se probó contra un **modelo** de la
API armado con ese comportamiento: con el código anterior la 2ª subida falla, con el de ahora las
dos andan, y lo que queda en el repositorio se descomprime y abre con los 70.893 productos. Es un
modelo; si GitHub se comporta distinto, la vía de listar la carpeta cubre el caso igual.

**3. Si fallaba, no se enteraba nadie.** La subida diaria corre sola en
`tareas_automaticas_del_dia()`, y un fallo ahí no dejaba rastro: la app seguía mostrando el mismo
«no hay copia» de siempre, sin decir que se estaba intentando y fallando. Ahora cada intento
anota su resultado, y si falla aparece arriba de todo, en rojo, «La copia automática a GitHub
está fallando», con lo que dijo GitHub —«GitHub rechazó el token…»—, y también en la pantalla de
backup.

## La tarea de fondo le cede el paso a quien está usando la app

Se midieron **todas** las pantallas con la tarea de fondo corriendo, cada una en un proceso
aparte. Tres se arrastraban:

| con la tarea de fondo corriendo | antes | ahora |
|---|---|---|
| «🧹 Limpiar y corregir», cada clic | 7–10 s | **0,4–0,5 s** |
| «🏷️ Códigos de barras», cada clic | 1–2 s | **0,4 s** |
| «🔗 Equivalencias sugeridas», la primera vez | 19 s | **6 s** (sola tarda 5) |

- **Limpiar y corregir** pasaba los 70.888 códigos por `sanitizar()` en cada clic, para ver si
  alguno quedó con el código limpio viejo. Ahora los trae en una sola fila y **recuerda entre
  clics** lo que dio `sanitizar()` para cada código crudo. Es exacto sin testigo —un código que
  cambia es otro código y se calcula de nuevo— y se olvida si cambia `app.py`. Mismo resultado
  sobre la base real y sobre una con 325 códigos rotos a propósito.
- **Códigos de barras** traía hasta 3.000 códigos por lista, fila por fila, y eso además corre
  en el chequeo de salud de cualquier pantalla. Ahora en una sola fila. Mismo resultado.
- **Equivalencias sugeridas** no tenía una consulta mala: la pantalla y la tarea de fondo se
  **repartían el procesador**. Un hilo de Python no corre en paralelo con otro, se turnan: el
  análisis solo tarda 4 s, y con la tarea de fondo al lado —que es justo después de importar,
  cuando uno entra a revisar— tardaba 19.

  Ahora `ceder_al_mostrador()`: mientras hay una pantalla dibujándose, la tarea de fondo **espera
  a que termine**. Está en sus bucles pesados y antes de sus lecturas grandes. La primera versión
  solo dormía 50 ms por vuelta y dejaba la pantalla en 12,5 s; muestreando el hilo de fondo se
  vio que seguía compitiendo con sus lecturas de 24.774 filas, que no pasan por ningún bucle.
  Tiene un tope de 20 s —si una pantalla termina en un `st.stop()` la marca de «terminó» no se
  anota, y sin tope la tarea quedaría frenada para siempre—, y es una sola marca para todo el
  proceso, no una por persona: simple antes que exacto. La tarea de fondo igual termina: a los
  25 s en vez de 22.

Se probó también pedir los pares de la lista como un solo JSON, porque medida sola esa consulta
«tardaba 4,2 s» con la tarea de fondo al lado. No cambió nada y se deshizo: el reloj corría
mientras el hilo esperaba su turno, y lo que había era la competencia por el procesador.

### Un error que el auditor no veía

Escribiendo esto se puso `_actividad_del_mostrador()` arriba de todo del archivo con la función
definida 11.000 líneas más abajo: **la app no hubiera arrancado**. Se vio leyendo el diff, no
por el auditor. El control 8j miraba qué funciones usa por dentro lo que corre al arrancar, pero
no si lo que corre al arrancar está definido más abajo — y en este archivo todo lo que no está
adentro de una función corre de arriba hacia abajo en cada dibujo, pantallas incluidas. Ahora lo
mira: sobre el archivo roto encuentra exactamente ese caso, y sobre el de ahora, ninguno.

## Lo que la app se traga en silencio

Se recorrieron todas las pantallas, subpantallas y grupos de mantenimiento, más cinco búsquedas,
juntando lo que `anotar_error()` registra sin mostrar. Solo 2, los dos de red —este entorno no
deja salir a buscar el dólar y la inflación—, y los dos ya tienen su freno de 30 minutos antes de
reintentar. La app está limpia.

## La página lenta justo cuando se la usa

Se cronometró cada pantalla sobre la base real. Primero, una trampa de la medición misma: el
arnés de pruebas de Streamlit vuelve a compilar `app.py` en cada dibujo —29.700 líneas, ~1 s—, y
el servidor de verdad lo compila **una vez** y lo guarda (`ScriptCache`). Midiendo con la app
envuelta para sacar ese segundo, casi todas las pantallas abren en **0,2–0,4 s**. Ese «1,4 s por
clic» que daban las mediciones anteriores no lo sufre nadie.

Lo que sí se sufre es otra cosa: la **tarea de fondo** —la que corre después de cada importación
y de cada actualización de la app, que es justo cuando alguien la está usando—. Mientras corre,
cada fila que SQLite le entrega a Python obliga a soltar el intérprete y volver a pedirlo, y el
hilo de fondo lo tiene ocupado. Una consulta que trae 70.000 filas para quedarse con diez pasa de
0,2 s a 9 s. Tres de esas estaban en el camino de todos los días:

| con la tarea de fondo corriendo | antes | ahora |
|---|---|---|
| «📌 Para pedir», cada clic | 6–10 s | **0,3–0,7 s** |
| buscar un código que no existe (W712/94) | 3,8–4,1 s | **0,55 s** |
| buscar 06A905115 | 1,3 s | 0,5 s |

- `variacion_de_precios_por_marca()` traía una fila por cada uno de los 70.888 productos para
  descartar casi todas: con un solo precio no hay aumento. Ahora trae solo los que tienen dos o
  más. Mismo resultado, comprobado con 20.000 cambios de precio sintéticos.
- `codigos_por_tipeo()` —las sugerencias por error de tipeo— traía hasta 7.444 filas completas,
  con descripción y precio, para devolver diez. Ahora trae id y código en **una sola fila**
  (`group_concat`), mide la distancia en Python y pide completas solo las que quedan cerca. Los
  mismos 27.645 candidatos en 504 búsquedas de prueba. Entre empatados —misma distancia, sin
  stock— el orden lo decidía el plan de SQLite; ahora es alfabético.

Se probó también partir en tandas la escritura de `recalcular_confianzas()`, sospechando del
candado. No cambió nada (10 s → 8–14 s) y se deshizo: no era el candado.

## «Equivalencias sugeridas» abre en la mitad

La primera vez que se abre analiza la lista entera. Sobre la lista del barrido —8.648 pares— eran
**9 s**; ahora **5 s**, con el resultado idéntico al de antes en las cuatro listas.

- Los 8.648 pares salen de solo **4.399 productos**, y cada par preguntaba por los dos: sus autos
  en los catálogos, en las fichas del taller, sus cambios de código y su firma. Ahora se recuerdan
  **mientras dura el análisis** y se tiran al terminar —guardarlos más obligaría a acordarse de
  invalidarlos—: de 95.144 consultas a 56.456, y la firma de 17.296 cálculos a 4.399.
- La señal «📋 Lo confirman N listas distintas» (+20) **no se disparaba nunca**: se contaba con
  `COUNT(DISTINCT lote)` por par, y la cola tiene clave primaria por par — un par está en una
  sola lista. Costaba 2 s por análisis. No se la hizo andar: de ~12.700 pares propuestos, 44 los
  propone más de una fuente, y 30 de esos ya los cuenta `evidencia_cruzada()` como dos métodos
  que coinciden. Sumarles +20 sería contar dos veces lo mismo.
- La consulta de al lado armaba un `IN` con todos los productos de la lista sin tandas. Hoy entra
  (4.399 contra un tope de 32.766), pero no tiene techo.

## La papelera devolvía el producto sin lo que lo hacía útil

Borrar un producto lo mandaba a la papelera, pero solo la fila del producto. La pantalla lo
avisaba: «si lo restaurás, el producto vuelve pero **sin** esos vínculos — hay que volver a
vincularlo manualmente». Medido con un producto real:

| LRSC030120LUCAS | antes | ahora |
|---|---|---|
| vínculos antes de borrarlo | 61 | 61 |
| vínculos después de restaurarlo | **0** | **61** |
| lo que trae la búsqueda después de restaurarlo | **1** (él solo) | 62 |

Ahora `borrar_producto_con_papelera()` guarda el producto **con sus vínculos y sus pendientes**,
en una sola transacción, y restaurarlo los repone. Si mientras estuvo en la papelera el mismo
código volvió a entrar con una importación, antes fallaba con «UNIQUE constraint failed»; ahora
se le devuelven los vínculos al que entró.

## Una marca en la papelera que no se podía restaurar nunca

Borrar una marca entera sí guardaba sus vínculos. Pero al restaurarla se los volvía a meter de a
uno con un `INSERT` a secas, y el otro lado de cada vínculo es casi siempre un código de fábrica
de OTRA marca. Si mientras tanto se borraba **uno solo** de esos —depurar huérfanos, cortar un
puente, los códigos basura—, la clave foránea rechazaba ese `INSERT` y con él la restauración
**entera**:

| restaurar FISPA después de borrar UN código de fábrica | antes | ahora |
|---|---|---|
| resultado | «No se pudo restaurar: FOREIGN KEY constraint failed» | restaurada |
| la marca | **no vuelve nunca** | vuelve con sus 5.068 productos |
| vínculos | 0 de 14.607 | 14.603, y dice que 4 no se pudieron reponer |

Ahora la marca y el producto pasan por `_reponer_vinculos()`, que repone lo que puede y cuenta
lo que no.

Probándolo con la app corriendo —apretando «↩️ Restaurar» en la pantalla— apareció otro: el
cartel con el resultado se dibujaba adentro del «la papelera tiene cosas». Restaurar lo ÚLTIMO
que había la deja vacía, así que el cartel no salía, quedaba guardado en la sesión y aparecía la
próxima vez que alguien borrara algo, fuera de lugar. Ahora se muestra antes: «Restaurado con 61
de sus 61 vínculo(s)».

Y el «todo o nada» de borrar una marca no era todo o nada. `mover_a_papelera()` hace
`conn.commit()`, y un commit adentro de `transaccion()` la cierra antes de tiempo. Probado
cortando justo antes del `DELETE`: la marca **seguía en la base y además quedaba una copia en la
papelera**. Ahora se guarda con `_guardar_en_papelera_sin_candado()`, que no confirma nada, y el
corte deja 0 copias.

`auditar.py` tiene un control nuevo (38) para esa clase de error: una función que hace
`conn.commit()` llamada adentro de `transaccion()`, o un `commit()` directo ahí adentro. Pasado
por el archivo de antes de este arreglo devuelve exactamente ese caso, y ningún otro.

## Pendientes colgando de productos que ya no existen

`equivalencias` se limpia sola al borrar un producto (`ON DELETE CASCADE`). La cola de pendientes
no tiene claves foráneas, y de los **seis** lugares que borran productos solo la fusión se
acordaba de ella. El resultado es el mismo agujero de conteo del lote anterior: invisibles en la
revisión —que hace `JOIN` con productos—, pero contados en el cartel del buscador y en «Descartar
TODO». Borrar ILLINOIS dejaba **6.001 pendientes huérfanos**.

En vez de arreglar cinco lugares, un trigger (`productos_sin_pendientes_colgando`) los borra con
el producto, venga de donde venga el borrado —incluido el que se agregue mañana—. Por eso ahora
la papelera guarda también los pendientes: al restaurar ILLINOIS la cola vuelve a sus 12.747.
Las bases que ya tienen huérfanos se limpian al abrir (`VERSION_COLA_PENDIENTES = "2"`).

## «Lo que te pidieron y no tenías» ahora dice si ya lo tenés

«🔎 Búsquedas sin resultado» era un registro muerto: qué te pidieron y no estaba cargado. Lo
normal es que después sí esté —entra con la lista siguiente— y que nadie se entere: el cliente
que lo pidió tres veces ya no vuelve a preguntar.

`busquedas_fallidas_que_ahora_estan()` vuelve a mirar cada pedido contra el catálogo de hoy, con
el mismo criterio con que arranca la búsqueda (código limpio o código de barras):

- arriba de la pantalla, en verde, los que **ya están**, con cómo están cargados;
- en la lista de siempre, una columna «¿Hoy?»;
- y al terminar de importar una lista, un cartel: «📞 Esta lista trajo N código(s) que te habían
  pedido y no tenías».

Las formas distintas de escribir lo mismo cuentan como un solo pedido: «271 1500» buscado dos
veces y «2711500» una vez son 3 pedidos del 2711500. Tarda 1 ms.

## Generar el paquete tardaba siete minutos

`nucleo/generar.py` copia de `app.py` el texto de cada bloque con `ast.get_source_segment()`, y
esa función vuelve a partir **el archivo entero** en líneas cada vez que se la llama. Una vez por
bloque, unos 2.000 bloques, 29.700 líneas: cuadrático. Nadie lo cambió; fue creciendo con el
archivo hasta pasar los **siete minutos**, casi todo adentro de `ast._splitlines_no_ff`.

Ahora las líneas se parten una sola vez y el recorte se hace a mano, en bytes UTF-8 como lo hace
`ast`. **De más de 7 minutos a 0,87 s**, y el paquete generado es idéntico byte por byte al de la
versión lenta.

## Rechazabas un vínculo y volvía con la lista siguiente

El más grave de este lote, y es consecuencia directa de haber hecho automático el
descubrimiento.

Revisar la cola sirve si la decisión **queda**. No quedaba. Los dos que más proponen —el
barrido de todo el catálogo y los códigos escritos en la descripción— no miraban lo que ya se
había decidido, y `guardar_equivalencias_pendientes()` tampoco. Mientras había que apretar un
botón para correrlos, eso pasaba de vez en cuando; desde que corren solos después de cada
importación, pasaba **siempre**.

Medido sobre la base real, con el descubrimiento ya corrido: se decidieron 300 pares a mano,
como lo hace la pantalla, y se corrió el descubrimiento de la importación siguiente.

| | antes | ahora |
|---|---|---|
| rechazados que volvieron a la cola | **300 de 300** | 0 |
| aprobados que volvieron a la cola como pendientes | **300 de 300** | 0 |

Y la app encima los anunciaba como nuevos: «100 par(es) de códigos que el proveedor escribió…
200 par(es) del barrido…» — exactamente los 300 que se acababan de decidir.

La importación de una lista ya lo hacía bien (filtra `rechazados_antes`), y
`guardar_equivalencias_derivadas()` también miraba los rechazos. Ahora las dos pasan por el mismo
lugar, que además saca lo que ya está cargado. Se hace adentro de
`guardar_equivalencias_pendientes()` y no en quien llama porque quien llama son cinco lugares
distintos, y alcanza con que uno se olvide.

## Una fila por par, y los números que decían el doble

De paso, el mismo lugar ahora guarda **una fila por par**, `(menor, mayor)`. Quien llamaba
mandaba la ida y la vuelta, la cola guardaba las dos, y todo lo que la cuenta con `COUNT(*)`
decía el doble —mientras la pantalla de revisión, que filtra `a < b`, mostraba la mitad—:

| en la base real, después de un descubrimiento | decía | pares de verdad |
|---|---|---|
| cartel del buscador, «esperando aprobación» | 22.309 | 12.747 |
| selector de listas, el barrido | 17.326 | 8.648 |
| «Descartar TODO lo pendiente» | 22.309 | 12.747 |

Y un caso peor: cuando el mismo par caía en dos listas, una se quedaba con la ida y la otra con
la vuelta —la clave primaria no deja repetir la fila exacta, pero la vuelta es otra fila—. La
vuelta es **invisible** en la revisión, que filtra `a < b`. Eran 30 en el barrido: una lista que
no se terminaba de vaciar nunca.

Las bases que ya tienen la cola así se arreglan solas al abrir la app (`VERSION_COLA_PENDIENTES`):
se borra la vuelta de los pares que tienen la ida, se dan vuelta los que quedaron solos al revés,
y se saca de la cola lo ya rechazado y lo ya cargado. Sobre la cola real: **22.309 filas → 12.747
pares, en 0,06 s**. En la base de la prueba de arriba saca justo los 300 rechazados que habían
vuelto.

`aprobar_pendientes()` y `rechazar_pendientes()` borran ahora las dos direcciones, igual que
`borrar_equivalencias_dudosas()`: el botón «Descartar esos N» de kit y pieza mandaba solo la ida.
Y `rechazar_pendientes()` devuelve lo que borró, no cuántos pares le pasaron — la pantalla casi
siempre manda ida y vuelta, así que decía el doble.

## De dónde salían las «equivalencias anotadas dos veces»

Hay una herramienta entera para unificarlas y un aviso de salud que las cuenta. Salían de dos
lugares que las creaban a propósito:

- **«Vincular manual»** con varios códigos recorría cada par dos veces —i contra j y j contra i—.
- **La confirmación desde el mostrador** guardaba la ida y la vuelta de cada sustitución.

| | antes | ahora |
|---|---|---|
| vincular 3 códigos: la pantalla decía | «6 relaciones creadas» | «3 relaciones» |
| filas guardadas | 6 (3 espejadas) | 3 |
| confirmar 1 sustitución en el mostrador | 2 filas | 1 |

Ahora los dos pasan por `_guardar_equivalencia_una_vez()`, que guarda `(menor, mayor)` y, si el
par ya estaba anotado al revés, se lleva esa fila. El buscador mira las dos columnas, así que con
una fila alcanza: probado buscando cada uno de los cuatro códigos, los cuatro traen a los otros
tres.

## «Se cortaron 2 vínculos» y el vínculo seguía ahí

El peor de este lote. No lo encontró el auditor: el control nuevo marcó la consulta de
`auditar_equivalencias_cargadas()` —la de al lado— y esto apareció leyendo qué hacía después
con lo que esa consulta devuelve.

En Administrar → Limpiar vínculos se analiza lo que la búsqueda está devolviendo hoy, se
listan los peores y hay un botón «✂️ Cortar los N peores». El corte hacía esto:

```sql
DELETE FROM equivalencias WHERE producto_a_id = ? AND producto_b_id = ?
```

con el par normalizado a `(menor, mayor)`. Pero la tabla **no guarda siempre el par en ese
orden**, y no por accidente: hay tres lugares que meten la fila sin normalizar, y uno de ellos
mete las dos direcciones a propósito —las sustituciones que confirma el mostrador
(`app.py:7695`), «Vincular manual» con varios productos a la vez (`app.py:22814`) y la
importación con carga directa (`app.py:23709`)—.

Contra una fila guardada al revés, ese `DELETE` no coincide con nada. La pantalla decía «se
cortaron N vínculos» igual, `marcar_revision()` lo anotaba como rechazado, y **el vínculo malo
seguía cargado y la búsqueda seguía devolviéndolo**.

Medido sobre la base real con un vínculo creado como lo crea la app:

| cómo quedó guardado | antes | ahora |
|---|---|---|
| las dos direcciones (mostrador / vincular manual) | dice «se cortaron 1» → **queda 1 fila viva** | dice 2 → **queda 0** |
| solo al revés `(b, a)` | dice «se cortaron 0» → **queda 1 fila viva** | dice 1 → **queda 0** |

Ahora el `DELETE` se lleva las dos direcciones. Si la relación está espejada hay que llevarse
las dos filas, porque la que quede sigue siendo el mismo vínculo para el buscador.

Detalle que ayuda a ver de qué tamaño era el descuido: `marcar_revision()`, que corre en la
línea siguiente, **ya guardaba las dos direcciones** —`(a,b)` y `(b,a)`— desde el principio. El
anotar estaba bien; el borrar, no.

## Un par contado como dos

El mismo origen. `equivalencias` puede tener la relación anotada de ida y de vuelta —para eso
existe «🔁 Equivalencias anotadas dos veces» y su aviso de salud—, y varias consultas que
cuentan **pares** estaban contando **filas**:

- el aviso «N par(es) de equivalentes con precios muy distintos» decía el doble;
- `precios_incoherentes_entre_equivalentes()` mostraba el mismo par dos veces en la tabla, con
  las columnas dadas vuelta, y gastaba la mitad del `LIMIT 200` en repetidos;
- `auditar_equivalencias_cargadas()` analizaba el mismo vínculo dos veces —cuesta el doble—,
  lo listaba dos veces entre «los peores», y el «se revisaron N vínculos» de la pantalla decía
  de más. Medido con un par espejado encima de la base real: **24.776 → 24.775**;
- `quien_conviene_por_rubro()` pide 5 comparaciones mínimas para que una marca entre al
  ranking, y con el par duplicado alcanzaban dos y media.

La condición quedó en una sola constante, `SIN_CONTAR_EL_ESPEJO`. Y **no es
`producto_a_id < producto_b_id`**, que es lo primero que uno escribe: eso esconde los pares que
solo están anotados al revés. Probado con cuatro productos, dos pares —uno espejado y otro
guardado solo al revés—:

| | pares contados |
|---|---|
| como estaba | 3 |
| con `a_id < b_id` a secas | 1 ← **pierde uno de los dos** |
| con `SIN_CONTAR_EL_ESPEJO` | **2** |

`recalcular_confianzas()` es la excepción y se quedó como estaba: escribe una confianza **por
fila**, y la fila que quedara sin puntuar contaría como neutra en el buscador. Lo dice adentro
del SQL, con la marca `FILA Y NO PAR`, que es lo que el auditor acepta como respuesta.

El `NOT EXISTS` es correlacionado y eso se paga, pero poco: `auditar_equivalencias_cargadas()`
sobre los 24.774 vínculos reales pasó de **5,0 s a 5,2 s**, con las mismas 922 dudosas.

**Sobre la base real de hoy esto no cambia ningún número**: tiene 0 equivalencias espejadas y 0
guardadas al revés. Lo que cambia es que ya no depende de que eso siga siendo cierto — y los
tres lugares que las crean están ahí, andando.

### El control que lo encontró

`auditar.py` tiene un chequeo nuevo (37): **una consulta que sale de `equivalencias` y engancha
`productos` dos veces está mirando un par, no una fila**. Si no descarta el espejo, se reporta.
Marcó cinco consultas: las cuatro de arriba y `recalcular_confianzas()`, que es la excepción
legítima. El `DELETE` que no borraba **no lo marca** —no tiene ningún JOIN—, pero fue lo que
apareció mirando una de las cinco.

Para escribirlo hubo que enseñarle al auditor a leer **f-strings**: al mover la condición a una
constante, la consulta pasó a ser un f-string y el nombre dejó de estar en un `ast.Constant`
—vive en un `FormattedValue`—, así que el control se disparaba sobre la consulta ya arreglada.
Y a no entrar adentro del f-string, porque sus pedazos, mirados sueltos, son exactamente la
consulta sin el hueco.

## La tabla te pedía aprobar un cambio que no te mostraba

En Administrar → «🔍 Ver qué se podría completar» sale una tabla con una columna
`Se completaría`, y abajo el botón «✅ Completar esas medidas». Esa tabla es lo único que la
persona mira antes de apretar.

La columna se armaba con una lista de ocho campos escrita adentro de la función.
`medidas_desde_descripcion()` ya devuelve **diez** —se le sumaron `cantidad_canales` y
`posicion`—, así que un producto al que solo se le leía la posición aparecía con la celda
**vacía**.

Contado sobre las 70.888 descripciones reales:

| | |
|---|---|
| productos con algo para completar | 5.449 |
| que mostraban la celda **vacía** | **3.524** |

El 65 % de la tabla. Y no eran casos raros: `KIT FILTROS Y O'RINGS 11044 PUNTAS INFERIORES
MULTIPUNTO` → `posición=INFERIOR`, que ahora se lee.

Ahora la celda se arma recorriendo lo que se va a escribir, no una lista aparte, así que no se
puede volver a desincronizar. Lo que no tenga etiqueta se muestra con el nombre de la columna:
feo, pero visible.

## Dos pasos que solo corrían una vez en la vida

`completar_marcas_de_repuesto()` —quién FABRICA la pieza, leído del final de la descripción— y
`aprender_motores_que_van_juntos()` —la tabla que evita que el veto por motor separe las bujías
del TU5JP4 de las del EW10— existían, andaban, y **solo corrían en el hilo de fondo, colgados de
una bandera de migración**. Esa bandera se prende una vez, al actualizar la app, y se apaga.

O sea: todo lo que entra DESPUÉS —que es justamente cada lista nueva que se importa— no los veía
nunca. La columna «Fabricante» del buscador quedaba en blanco para lo recién importado, para
siempre.

Probado contra la base real, con las banderas de migración ya consumidas (el estado normal de
quien viene usando la app) y cinco productos nuevos importados encima:

| | antes | ahora |
|---|---|---|
| productos nuevos sin marca del repuesto | **5 de 5** | **1 de 5** |
| pares de motores compatibles al día | no se tocaban | 1.334 |
| duración del descubrimiento completo | 98 s | 84 s |

El que sigue sin marca es FERODO, que no está en la lista de fabricantes — y no se agregó a
propósito: en el catálogo real no aparece ni una sola vez, así que agregarla sería inventar.

El orden importa y por eso `aprender_motores_que_van_juntos()` va **antes** del cruce por auto y
del barrido: los dos puntúan con `evaluar_equivalencia()`, que lee esa tabla para decidir el
veto. Aprenderlos después sería vetar pares que la lista recién importada acaba de demostrar
compatibles, y esos pares no vuelven — quedan descartados hasta la próxima importación.

Cuesta 3,2 s sobre un presupuesto de 120 s (2,6 s las marcas, 0,6 s los motores), y correrlo de
nuevo no pisa nada: la segunda pasada completa 0 productos en 0,3 s.

## Nueve fabricantes que faltaban, sacados de contar y no de acordarse

`MARCAS_QUE_FABRICAN_LA_PIEZA` tenía 41 marcas puestas a mano. Para ampliarla no se pensó en
marcas: se listaron **las últimas palabras de las 70.888 descripciones reales**, se sacaron las
que son marca de AUTO (`FIAT`, `RENAULT`, `PEUGEOT`) y las que son palabra de repuesto
(`DIESEL`, `CILINDRO`, `JUNTA`), y quedaron nueve que cierran la descripción como la cierra un
fabricante:

`PRESTOLITE` · `KOBLA` · `BOUGICORD` · `HOLLEY` · `TAILLOT` · `INDIEL` · `LOCX` · `PAIA` · `GATES`

| | |
|---|---|
| productos con fabricante, antes | 13.705 |
| productos con fabricante, ahora | **14.127** |
| diferencia | +422 |

**DAYCO no entró**, y eso es parte del resultado: aparece 73 veces en el catálogo y **ninguna al
final** —siempre en el medio de un kit—, y esta lectura solo mira el final. Hay una línea en las
pruebas que lo deja escrito, para que si algún día se la agrega se note.

## Una columna nueva tumbaba el buscador entero

Salió de una medición que ni siquiera era sobre esto: al cronometrar las búsquedas contra la
base real —donde todavía no corrió la migración— saltó

```
sqlite3.OperationalError: no such column: p.marca_repuesto
```

y lo que se cae ahí no es una comodidad: es **la pantalla principal de la app**. Agregar
`marca_repuesto` a la búsqueda por código y por texto la dejó atada a que la columna exista.

Es exactamente el caso que `_columnas_de_medidas_que_existen()` ya cubría para las medidas —una
conexión cacheada, un backup viejo restaurado con otra sesión adentro— y que se había olvidado
acá. Ahora las dos consultas piden la columna por `campo_opcional_de_producto()`, que devuelve
`p.marca_repuesto AS "Fabricante"` si existe y `NULL AS "Fabricante"` si no.

Devolver NULL y no omitir la columna es a propósito: quien lee el resultado encuentra la clave
igual, vacía, que es exactamente lo que significa «esta base todavía no tiene ese dato».

Comprobado por los dos lados, 25 búsquedas completas de cada uno:

| | resultados | por búsqueda |
|---|---|---|
| base SIN la columna | 803 | 118 ms |
| base CON la columna | 803 | 114 ms |

Sin la columna, `Fabricante` llega en `None`; con ella, llega BOSCH y MASSER.

El primer intento cacheaba el `PRAGMA table_info` con `lru_cache` y limpiaba el caché al
restaurar un backup. Se sacó: lo que se está cacheando cuesta **50 µs** y se pide dos veces por
búsqueda —0,1 ms—, y a cambio obliga a acordarse de limpiarlo cada vez que el esquema puede
cambiar. Esa clase de olvido es justamente lo que esta función existe para cubrir; no tiene
sentido que la función traiga adentro el mismo problema que vino a resolver. Barato y sin
estado le gana a rápido y con una trampa.

Y una segunda: el paquete `nucleo` se lleva el **cuerpo** de `buscar_por_codigo()`, así que en
cuanto la búsqueda empezó a llamar a un ayudante nuevo, el paquete quedó con un
`NameError: name 'campo_opcional_de_producto' is not defined`. Ahora `generar.py` copia también
los dos ayudantes, y como en el paquete el cursor viaja por parámetro, `campo_opcional_de_producto()`
lo recibe igual que las demás —es la razón por la que no usa el cursor de módulo.

## Doce barridos del catálogo por cada búsqueda

`kits_que_lo_traen()` contesta la pregunta del mostrador —«¿y el kit con las bujías?»— con un
`LIKE '%…%'` sobre `busqueda`, que **ningún índice de SQLite puede servir**: es un barrido de
las 70.888 descripciones. La pantalla de resultados la llamaba una vez por cada uno de los doce
primeros productos. Doce barridos. En el camino más caliente de la app, el que corre cada vez
que alguien busca un repuesto.

Ahora es **una sola consulta** con las formas de los doce códigos, y el reparto se hace en
Python: se trae también `busqueda`, que es el mismo texto contra el que el `LIKE` compara, así
que decidir a qué producto corresponde cada kit es mirar si esa forma está adentro. Los filtros
que son POR producto —que el kit no sea el producto mismo, que no compartan descripción— se
aplican al repartir, porque en el SQL serían otra vez doce consultas.

Medido sobre doce productos que **sí** están adentro de algún kit (la primera medición usó
productos al azar, ninguno tenía kit, y no probaba nada):

| | |
|---|---|
| de a uno, doce consultas | 0,265 s |
| de una sola vez | **0,124 s** |
| diferencias en el resultado | **0** |

Y quedó UNA implementación, no dos: `kits_que_lo_traen()` se borró en vez de dejarla como
envoltorio. El auditor la marcó como «definida y nunca usada» apenas dejó de llamarse, que es
exactamente para lo que está ese control.

## Cinco botones que ya se habían apretado solos

En «🔎 Encontrar equivalencias» hay nueve herramientas, y `descubrimiento_post_importacion()`
dispara varias de ellas **sola, después de cada importación**. El índice no lo decía.

El resultado es el peor de los dos mundos: el que entra ve nueve botones sin saber cuáles ya se
hicieron, y termina corriendo a mano —y esperando— algo que la app ya hizo. Ahora las que
corren solas lo dicen en su propia línea del índice:

> 📝 Códigos de fábrica que el proveedor escribió en la descripción
> Lee los «REF ORIG» que ya están escritos en las descripciones cargadas.
> **✅ Ya corre solo después de cada importación: esto es para volver a pasarlo.**

Y «🏭 Catálogo de aplicaciones» ahora dice que adentro está el botón para deducirlas de las
propias descripciones sin subir nada, que era el que no encontraba nadie.

## La pantalla de equivalencias sugeridas reanalizaba todo por tocar una casilla

`analizar_lote_pendiente()` tarda 5,2 s sobre los 3.185 pendientes reales, y estaba corriendo
en **cada dibujado** de la pantalla. Mover el slider de «cuántos analizar», cambiar de tanda o
tildar un checkbox volvía a analizar de cero: cinco segundos de reloj de arena por tocar una
casilla.

Medido dibujando la pantalla de verdad contra la base real:

| | |
|---|---|
| primera vez | 12,75 s |
| segunda | **1,35 s** |
| tercera | **1,26 s** |

**La parte que importa es la invalidación**, no el caché. La clave incluye el total de
pendientes del lote, así que aprobar o descartar lo rehace justo cuando dejó de valer y no
antes. Comprobado apretando el botón de verdad: «✅ Aprobar los 2.719 sin alarmas» cambió la
clave de 3.185 a 466 y el análisis se recalculó solo, sin una excepción.

Lo que se hace en OTRO lote no lo toca, y está bien: el análisis de éste sigue siendo cierto.

### Dos arreglos chicos del mismo informe

**El `PRAGMA` que corría 3.186 veces.** `_columnas_de_medidas_que_existen()` es puro esquema y
se llamaba una vez por par. Cacheada con `lru_cache(1)`, con el cuidado que hacía falta:
`restaurar_backup()` la limpia, porque la base que acaba de entrar puede tener otras columnas —
que es exactamente el caso que esa función existe para cubrir.

**El caché de modelos desalojaba a los 20.** `modelos_de_marca()` tenía `max_entries=20` y hay
**117 marcas de vehículo con productos** en el catálogo. El que mira más de veinte marcas en una
sesión empezaba a repagar 0,65 s justo al volver sobre una que ya había abierto. Sube a 130; lo
que se guarda son listas de palabras, no filas.

## Una búsqueda tardó 23,78 segundos, y la mediana decía que todo estaba bien

Después de cinco marcas de versión nuevas en un día, la primera vez que se abre la app la tarea
de fondo hace TODO junto: resepara 12.255 descripciones, completa 4.144 medidas, pone 13.706
marcas de repuesto, deduce 112.499 aplicaciones y repuntúa 24.774 vínculos. Nunca se había
corrido entera, así que se corrió.

**Dos cosas aparecieron, y ninguna se veía leyendo el código.**

### 1. El bloque que decía ir primero iba tercero

El comentario del bloque que resepara las descripciones decía «va ANTES QUE TODO lo demás, y el
orden no es casual: las medidas, el combustible y las aplicaciones se leen de la descripción».
Era falso: había quedado **después** del de medidas.

Se vio porque al terminar la tanda `medidas_pendientes` quedaba otra vez en «1» — este bloque lo
vuelve a pedir cuando el texto cambió, y el de medidas ya había pasado. Funcionaba igual, en dos
arranques en vez de uno, y las medidas se leían del texto viejo. Con el bloque donde decía estar:
las cinco banderas quedan en 0 en una sola pasada y `medidas_completadas` sube de 4.076 a
**4.144** — los 68 que antes había que esperar a un segundo arranque.

### 2. La peor búsqueda tardaba 24 segundos

Midiendo búsquedas desde otro hilo mientras la tanda corría:

```
mediana 0,02 s    9 de cada 10 bajo 0,21 s    PEOR: 23,78 s
```

La mediana estaba perfecta y por eso no se veía promediando. Lo que hay que mirar es **la
peor**, porque esa es la que tiene a alguien esperando en el mostrador.

La causa: la tarea de fondo escribía decenas de miles de filas tomando `db_lock` **una sola
vez**. `reseparar_descripciones_viejas()` lo tomaba para las 70.888 filas de una; el INSERT de
las 112.499 aplicaciones, también.

Ahora el candado se suelta cada 500 filas, así que la otra sesión se cuela en el medio:

| | antes | después |
|---|---|---|
| peor búsqueda | **23,78 s** | **2,91 s** |
| búsquedas de más de 3 s | 2 | **0** |
| mediana | 0,02 s | 0,02 s |
| la tanda entera | 85 s | 95 s |

La tanda tarda un 12% más. Es el precio de no dejar a nadie esperando 24 segundos, y está bien
pagado.

## Las bujías del TU5JP4 y las del EW10 son las mismas

Esto lo corrigió el dueño, y corrige algo que se había agregado el día anterior.

El veto por motor dice «si los dos declaran motor y es distinto, no son equivalentes». Suena
bien y **está mal seguido**: las bujías del TU5JP4 y las del EW10 son las mismas, pero cada
proveedor escribe en su descripción los motores que se le ocurren. Uno pone TU5JP4, el otro
pone EW10, y el veto separa dos piezas que se reemplazan.

**La evidencia ya estaba en el catálogo**, y no hace falta ningún dato de afuera: cuando un
proveedor vende UN producto y en su descripción nombra VARIOS motores, está diciendo que esa
pieza entra en todos.

Sobre el catálogo real hay **838 descripciones que nombran dos motores o más**, y de ahí salen
**1.334 pares de motores con su tipo de pieza**. El ejemplo del mostrador está adentro:

```
TU5JP4 + EW10J4    Combustible
DV6TD4 + DV6TED4   Juntas y retenes   (17 listas lo dicen)
EW10D  + EW10J4    Juntas y retenes   (13 listas lo dicen)
D4D    + D4F       Juntas y retenes   (13 listas lo dicen)
```

**Se exige el MISMO tipo de pieza**, y no es un detalle: que K4M y K7M compartan una bomba de
agua no prueba que compartan la junta de tapa de cilindros — son un 16 válvulas y un 8
válvulas, y la tapa es otra. Pidiendo la misma familia se liberan 3.755 pares y quedan frenados
16.056; sin pedirla se liberarían 6.408, y varios de esos de más son justamente juntas entre
motores de distinta tapa.

Tampoco es transitivo a propósito: que A vaya con B y B con C no dice nada de A con C.

Y lo mismo que con el motor: las equivalencias derivadas siguen en 156. Ninguno de esos 3.755
llegaba al final igual. Lo que cambia es que el veto dejó de estar equivocado.

## Las descripciones que entraron antes de que el separador aprendiera

`separar_texto_pegado()` corre al importar, pero fue aprendiendo después: las descripciones que
entraron antes quedaron como vinieron. Son **12.255 de 70.888 que todavía cambiarían**, y lo que
arregla casi siempre es lo mismo — el «REF ORIG» pegado a la palabra anterior, que se come lo
que venía justo antes:

```
antes: «…TOYOTA COROLLA 1 6 - 1 8REF ORIG…»
ahora: «…TOYOTA COROLLA 1 6 - 1 8 REF ORIG…»
```

Medido qué gana y qué pierde sobre esas 12.255:

| | gana | pierde |
|---|---|---|
| combustible | **+377** | −6 |
| medidas | +68 | 0 |
| familia | +5 | 0 |
| fabricante | +1 | 0 |
| motor | 0 | −3 |

Los 3 «motores perdidos» son en realidad el arreglo: antes se leía «YD25REF» —el motor pegado a
REF— que no es ningún motor. Lo que se pierde es un dato equivocado.

**Y lo que se esperaba ganar no se ganó**: cero descripciones recuperan un año. El informe que
originó esto decía 113; sobre esta base son 0. La ganancia está en el combustible, no en los
años.

Corre antes que todo lo demás en la tarea de fondo, y el orden no es casual: las medidas, el
combustible, la marca del repuesto y las aplicaciones se leen de la descripción. Hacerlo después
sería leer el texto viejo y tener que rehacerlo. 12.255 en 4 s, idempotente, y la columna
`busqueda` se mantiene sola porque hay un trigger `AFTER UPDATE OF descripcion`.

## Qué motor lleva, y por qué un dato parcial puede empeorar las cosas

`aplicaciones.motor` existía y se insertaba **siempre vacía**. Llenarla parecía trivial y
resultó ser el cambio que más cuidado necesitó de los cuatro.

### Primero, cómo leerlo

Buscar una palabra con forma de motor suelta en el texto da 2.109 productos, y se cuela basura:
«Y10I» —que es el Lancia Y10— o «JA0REF», que son dos pedazos pegados. Hace falta que el texto
diga **dónde** está el motor, y hay dos lugares donde lo dice sin dudar:

- detrás de la palabra MOTOR: «Aro piston RENAULT Kangoo - Motor K7M - Nafta»;
- detrás de la cilindrada entre guiones, que es la forma fija de estas listas:
  «Junta Tapa de Cilindros CHEVROLET SPIN COBALT - **1.8 - N18XFN**».

Las dos juntas: **998 productos, 187 motores distintos**, encabezados por F8Q (39), K9K (37),
K7M (30). En dos muestras de 10 y 14 al azar revisadas a mano, 24/24 correctas. Llevado a las
aplicaciones son **4.880 filas con motor**.

### Y después, lo que casi sale mal

El cruce por auto comparaba `a.motor = b.motor`. Con la columna siempre vacía, eso era «todos
contra todos»; apenas se llena para algunos, **el que declara su motor deja de cruzar con el
que no lo declara** — y los que no lo declaran son la enorme mayoría.

Medido:

| comparación | pares candidatos |
|---|---|
| `a.motor = b.motor` (la que había) | 1.419.859 |
| contradice solo si los dos lo saben | **1.504.721** |

O sea que llenar la columna, con la comparación estricta, **habría perdido 84.862 cruces que
hoy funcionan bien, sin ganar nada a cambio**. Un dato parcial comparado por igualdad estricta
es peor que no tener el dato.

La regla correcta es la que ya usa `comparar_medidas()`: si a uno de los dos le falta, no se
concluye nada. Con eso, el veto frena **6.896 pares donde los dos declaran motor y es distinto**
—un Peugeot Partner para el XU5CP contra uno para el TU3JP, que no se reemplazan— y no toca
ninguno de los otros.

Las equivalencias derivadas quedan en 156, las mismas que antes: ninguno de esos 6.896
sobrevivía igual a los demás filtros. O sea que hoy el veto no cambia el resultado, y vale
decirlo así. Lo que cambia es que el dato está, se ve, y el día que dos piezas de motores
distintos lleguen juntas al final, ahí las frena.

## Las medidas escritas con palabras: la pantalla de buscar por medida cubría el 26%

El lector de medidas entendía «35x52x7», «22 ESTRIAS» y «M24 X 1.5». Pero las listas de poleas
y alternadores no escriben así:

```
POLEA LRAP016 Citroen C5 … Diametro interno 17mm - Diametro Externo 54 5mm - Cantidad de canales 6
```

523 productos tenían las tres columnas vacías **teniendo la medida a la vista**.

El «54 5mm» es 54,5: la importación se comió el separador decimal y dejó un espacio. Por eso el
decimal acepta coma, punto o espacio — **pegado al «mm»**, que es lo que lo hace seguro: sin esa
ancla, cualquier «54 5» suelto de la descripción entraría como medida.

Y los canales se piden con el número DETRÁS («CANTIDAD DE CANALES 6»), porque en esa misma lista
hay «Polea de 4 canales 96 >», donde el número que sigue es un año. Tomando el de atrás quedaba
una polea de 96 canales. Comprobado: esa descripción ahora devuelve vacío.

| | antes | después |
|---|---|---|
| productos con diámetro interno/externo | 184 | **707** |
| productos con ancho | 184 | 310 |
| productos con canales de polea | — | **523** |

La pantalla **📐 Buscar por medidas** pasa de 184 productos a 707, casi cuatro veces. Y el veto
físico encuentra **3 equivalencias ya cargadas que se contradicen**: poleas de 5 canales contra
6, con diámetro externo de 54,0 contra 48,8 y de 61,0 contra 55,0. No son la misma polea.

## «VOLVO LRA974» no es un modelo de Volvo

De las 4.229 combinaciones marca+modelo que el extractor saca de las descripciones, muchas no
son modelos: «VOLVO LRA974», «IVECO ALTT150», «DAF STRB014», «FIAT D6RA32». Es el propio número
del proveedor, que quedó adentro de la descripción y el extractor lo tomó por modelo. Nadie
busca repuestos «para un LRA974», y como aparece en decenas de descripciones junta entre sí todo
lo que lo nombre.

Es la misma idea que `parece_designacion_de_motor()`, una vuelta más: **preguntarle al catálogo
en vez de adivinar**. Si la palabra existe como código de un producto, sospechá.

Pero eso solo no alcanza, y medirlo lo dejó clarísimo:

> **«F1000» está cargado como código de un repuesto Y es una Ford F1000 de verdad.**

Lo mismo con «S16» (el Peugeot 306 S16) y «NV200» (el Nissan NV200). Así que se pide además la
FORMA de un código de proveedor: tres o más letras seguidas de números, o letras y números
alternados en dos grupos. «F1000» tiene una sola letra adelante y queda afuera del filtro.

Resultado: **298 combinaciones y 1.909 filas menos** (114.673 → 112.764), y en una muestra de 14
al azar revisada a mano no hay un solo modelo de verdad — son códigos de proveedor (KPV149,
KTB764, IWP101), designaciones de motor (EW10J4RFN, DOHC16V) y dos modelos pegados entre sí
(«GOL-R19»), que tampoco son un modelo. Comprobado uno por uno que F100, S16, NV200, GOL e
HILUX siguen ahí.

## El juego y la junta que trae adentro no son lo mismo

`_uno_trae_al_otro()` ya resolvía el caso en que el kit **nombra** el código de la pieza —«KIT
CAB Y BUJ (LEIHTT06SC/LSPKR6E)»—, y por eso daba 0 relacionadas sobre los 3.185 pendientes: en
esta lista eso no pasa nunca. El juego y la junta no se citan entre sí. Se encuentran porque los
dos llevan **el mismo número original**, y ese número es de la junta:

```
OEM 460S36T   pieza  TC-963-17    Junta Tapa de Cilindros IVECO STRALIS I 460S36T…
              JUEGO  JR-602-17R   Juego Completo de Reparación IVECO STRALIS I 460S36T…
```

La primera idea fue usar los prefijos de ILLINOIS —`JR-`, `JD-`, `SJ-` son juegos; `TC-`,
`JC-`, `JVS-` son piezas— pero **no hace falta y habría sido peor**: la descripción ya lo dice
con todas las letras, «Juego Completo de Reparación» contra «Junta Tapa de Cilindros», y
`es_un_kit()` ya sabe leer eso. La regla queda general en vez de atada a cómo numera un
proveedor.

Cuando en un mismo número de fábrica conviven un juego y una pieza suelta, el del **juego** no
es una equivalencia: no se puede vender uno en lugar del otro. Va al balde de «relacionadas»,
que la pantalla muestra en una línea. Sobre la cola real: **55 grupos, 79 pares**.

## Con qué anda el auto

Una pieza del 1.6 nafta no entra en el 1.9 diesel aunque el auto se llame igual. Las siglas
valen tanto como la palabra —nadie escribe «diesel» al lado de «HDI», y «MPI» quiere decir
nafta sin decirlo—, así que se leen las dos formas.

Sobre las 46.644 descripciones de proveedor: **4.292 dicen diesel, 2.215 dicen nafta**, y 129
dicen las dos —listas que cubren las dos versiones del mismo auto— y quedan sin decidir. Muestra
de 14 al azar: 14 correctas.

Llevado a las aplicaciones deducidas son **30.920 filas con combustible** (21.964 diesel, 8.956
nafta), y de ahí sale el uso que importa: el cruce por auto ya no junta una pieza diesel con una
nafta del mismo modelo.

| | sin el filtro | con el filtro |
|---|---|---|
| pares candidatos del cruce | 2.598.796 | 1.511.755 |
| equivalencias derivadas | 177 | **156** |

21 equivalencias que se iban a derivar cruzando combustibles distintos ya no se derivan.

### Números de la cola, acumulado

| | al empezar el día | ahora |
|---|---|---|
| 🟢 aprobar sin mirar | 2.266 | 2.489 |
| 🟡 conviene una mirada | 502 | 328 |
| 🔴 casi seguro mal | 417 | 289 |
| apartadas como «juego y pieza» | 0 | 79 |
| **decisiones a mano** | **919** | **617** |

## Dónde va la pieza: el caño de arriba del radiador no es el de abajo

Tercer dato que estaba escrito en miles de descripciones y no leía nadie, después de las
medidas y las aplicaciones. Y como esos, no es solo un dato a la vista: es **prueba física**.
Un sensor de ABS trasero izquierdo no reemplaza al delantero derecho por más que los dos sean
del mismo auto.

Tres ejes, y de cada uno se toma un lado: delantera/trasera, izquierda/derecha,
superior/inferior. Si la descripción nombra **los dos** lados de un eje —un kit que trae ambos—
no se decide nada: adivinar sería peor que no saber, porque esto alimenta un veto.

Lo delicado fueron las abreviaturas, y costó una medición encontrarlo: **«DEL» suelto es la
preposición más común del español**. Con ella, «Junta Tapa de Cilindros FORD CORCEL BELINA
PAMPA DEL REY» —que es el Ford Del Rey— quedaba como pieza *delantera*. Exigiendo «DEL.» o
«DEL-», los falsos positivos desaparecen: de 4.239 productos se baja a 3.528, y en una muestra
de 16 al azar revisada a mano, 16 correctas.

Sobre la base real: **3.553 productos** con posición, en 9 s. Y el veto encuentra **4
equivalencias ya cargadas que están mal**:

```
SENSOR ABS M.BENZ ML270/ML320    DELANTERA+IZQUIERDA  ↔  DELANTERA+DERECHA
SENSOR ABS AUDI A4-A5-A6…        TRASERA+DERECHA      ↔  TRASERA+IZQUIERDA
SENSOR ABS KIA SPORTAGE/TUCSON   TRASERA+IZQUIERDA    ↔  TRASERA+DERECHA
CANO Ford F100-F1000-F4000       radiador SUPERIOR    ↔  radiador INFERIOR
```

Las cuatro son de las que mandan la pieza equivocada al mostrador.

### El voltaje se midió y se descartó

La idea era la misma —12 V no reemplaza a 24 V, y hay 4 equivalencias cargadas que los
mezclan— pero **en este catálogo «16V» y «24V» casi siempre son VÁLVULAS, no volts**:
«CANO Renault LAGUNA 3.0 24V», «KIT TTC NISSAN 2.8 6 CIL DIESEL 12V».

Se probó filtrando por rubro eléctrico y exigiendo que no viniera una cilindrada delante. Eso
baja de 1.582 a 460 productos, pero en una muestra de 16 seguían colándose dos sensores donde
el «24V» eran válvulas. Un veto que se equivoca manda a revisar piezas que están bien, así que
**no entra**. Queda medido acá para no volver a intentarlo sin saberlo.

## Los avisos ahora tienen botón, y eso destapó que once mentían

De los 28 textos de la app que mandan a otra pantalla, **uno solo tenía botón**. Los demás
terminaban en una miga de pan escrita —«📍 Administrar → Mantenimiento → 🧹 Limpiar y corregir
→ Códigos puente»— y ahí quedaba: había que acordarse del camino y hacerlo a mano.

En vez de escribir un destino por aviso, el botón **lee la miga**. Eso tiene una ventaja que no
es de código: si la miga miente, el botón no llega, y se nota. Pasó apenas se escribió:

- **11 lugares decían «Estadísticas → Mantenimiento»** y Mantenimiento vive en Administrar.
- Uno mandaba a «Estadísticas → Vínculos de listas esperando revisión», una solapa que no
  existe.
- Varios escriben la solapa sin su emoji («Backup y config» contra «💾 Backup y config»), y
  exigir el emoji dejaba el botón a mitad de camino.

Ninguna de las tres se había visto nunca, porque **una miga de pan escrita no se prueba sola**.
Ahora los 8 avisos de la base real llegan a su pantalla, comprobado uno por uno.

## 8.319 códigos de barras cargados como código de fábrica: la app lo sabía y no lo decía

Una de cada tres equivalencias de la base —**8.319 de 24.774**— sale de un producto fantasma
cuyo «código de fábrica» es en realidad un código de barras de MOTORARG (prefijo `7793960…`,
Argentina). Cada uno deja una equivalencia que no lleva a ningún lado: es lo que hace que el
buscador prometa un equivalente que no existe.

Lo llamativo es que **ya estaba todo hecho menos avisar**. `codigos_de_barras_mal_cargados()`
los detecta —decide por lista y no por código suelto, con el dígito verificador y el prefijo de
empresa— y `mover_codigos_de_barras_a_su_columna()` los arregla. Lo que faltaba era que el
diagnóstico de salud lo dijera: había que entrar a la herramienta a mirar para enterarse.

Probado sobre una copia de la base real:

| | antes | después |
|---|---|---|
| productos | 70.888 | 62.569 |
| equivalencias | 24.774 | 16.455 |
| con código de barras en su columna | 0 | **8.319** |

Y lo que importa: **MOTORARG cruzaba con 0 proveedores antes y con 0 después**. No se pierde
nada, porque esas 8.319 equivalencias no unían nada — es literalmente lo que el README ya
llamaba «una equivalencia que no lleva a ningún lado». Comprobado además que los productos se
siguen encontrando por su código, por el código de barras y por texto, con `integrity_check` en
ok y 0 equivalencias huérfanas.

**No se arregla solo, y es a propósito**: el arreglo borra productos, y lo que borra tiene que
decidirlo una persona. El aviso sale en rojo con el botón al lado.

## Quién fabrica la pieza: 13.705 productos lo dicen y no había dónde guardarlo

Las 5 marcas de la tabla `marcas` son **proveedores** —JL, MOTORARG, ILLINOIS, FISPA y el nodo
de fábrica—. Quién **fabrica** la pieza no estaba en ninguna columna, y en el mostrador suele ser
la primera pregunta: «¿lo tenés en Bosch o en Masser?».

Está escrito al final de la descripción. La pregunta era cómo reconocerlo sin inventar.

Primero se midió, sobre las 46.644 descripciones de proveedor, cuántas veces cada palabra
aparece **al final** contra cuántas aparece en cualquier lado — una marca es una firma, va al
final:

| | al final | en total | proporción |
|---|---|---|---|
| MASSER | 6.258 | 6.261 | 1,00 |
| CAUPLAS | 3.483 | 3.489 | 1,00 |
| MLH | 563 | 576 | 0,98 |
| RETENES | 692 | 1.023 | 0,68 |
| **BOSCH** | 834 | 2.581 | **0,32** |
| DIESEL | 339 | 1.260 | 0,27 |

Y ahí se ve que la proporción **no alcanza**: BOSCH da 0,32 porque también aparece en el medio
como referencia cruzada («REF ORIG BOSCH 0281002764»), y RETENES da 0,68 sin ser marca de nada.
O sea que sirve para DESCUBRIR candidatos, no para decidir. La decisión es una lista curada de
41 marcas, como la que ya existe para los vehículos.

La regla pide que esté **al final**, y eso es lo que la hace confiable: en el medio, «BOSCH»
quiere decir que la pieza *reemplaza* a una Bosch, no que lo sea.

Resultado: **13.705 productos** con fabricante, encabezados por MASSER (6.261), CAUPLAS (3.483),
BOSCH (833), MLH (563) y MARELLI (555). En una muestra de 14 al azar revisada a mano, 14
correctas. Se llena sola por `VERSION_MARCAS_REPUESTO` (2,7 s), no pisa lo que alguien corrija a
mano, y ahora aparece como columna **Fabricante** en la búsqueda por código y por texto:

```
buscando «SENSOR MAF»
  12 7162          JL   fab=—        SENSOR MAF THOMSON MAREA 2.0
  0280 217 512 :   JL   fab=BOSCH    SENSOR MAF VW GOLF 2.8 BOSCH
  MAF 208          JL   fab=MASSER   SENSOR MAF AUDI A6 3.0 Masser
```

El primero se queda sin fabricante a propósito: ahí «THOMSON» está en el medio, y la regla no
adivina.

## El hermano que llegó segundo arrancaba 35 puntos abajo, y nada más que por eso

La señal más fuerte del puntaje es «📄 los dos tienen exactamente la misma descripción», +35.
Pero en esta cola esa señal no prueba lo que parece.

El importador crea el producto de fábrica **copiando la descripción** de la fila que primero
nombró ese número. O sea que «la descripción coincide» quiere decir, en realidad, «esta fila
fue la primera». Sobre la cola real: de 2.397 números de fábrica, **2.296 tienen exactamente
una fila de origen**, y de los 919 vínculos que había que revisar a mano, **643 (el 70 %) son
hermanos** — filas que citan el mismo número con la misma evidencia y llegaron segundas.

El hermano que es **la misma pieza en otra medida** —`TC-703-MG` contra `TC-703-15`— ahora
recibe la misma señal, con su propio texto, porque tiene la misma evidencia detrás. Se pide que
compartan la base del código, que es lo que distingue a una variante.

Lo mismo arregla dos cosas más que venían del mismo malentendido:

- **La alarma de ambigüedad no le corresponde al hermano variante.** Que la junta venga en tres
  espesores no quiere decir que alguno esté mal cargado.
- **El veto por medidas tampoco.** El nodo de fábrica no tiene medidas propias: se leyeron de la
  descripción que copió. Comparar el espesor de `TC-615-MG 4M` (2,40 mm) contra el que el nodo
  heredó de `TC-615-MG 0M` (1,65 mm) es compararlo contra su propio hermano — la diferencia está
  garantizada por construcción. Comprobado: de los 3.185 pendientes hay **34 con la medida
  contradiciéndose y los 34 son exactamente este caso**. Ni uno era una pieza distinta.

## Y lo que se aprobaba sin mirar tenía basura adentro

Eso solo no se podía soltar. Subir 300 hermanos al botón de «aprobar sin mirar» sirve si el
botón está limpio, y no lo estaba.

`ILLINOIS` escribe la descripción con una forma fija: primero qué es la pieza y para qué autos,
y al final los números de fábrica de verdad, entre paréntesis o detrás de `//`. Cuando el número
cargado como código **no está en esa zona** pero la zona existe y tiene otros números, lo que
pasó es claro: el extractor lo levantó del texto del medio, donde van los motores.

```
«Junta para Cárter RENAULT CLIO … - 1,4/1,5/1,6 - K4M K4J K9K16V (8200………)»
   quedó cargado «K9K16V», que es el MOTOR. El número real estaba en el paréntesis.
«Junta Tapa de Cilindros SCANIA … - 10,6/11,7 - … DSC12.01 (…)»   -> «DSC12.01»
«Junta Tapa de Válvulas PERKINS … - 3,3 - 4.203/4-PA.203 (…)»     -> «4-PA.203»
```

Los tres tenían **100 de confianza** y entraban al botón de aprobar en bloque.

**No baja a rojo, baja a amarillo**, y la diferencia es deliberada. El objetivo es sacarlos de
«aprobar sin mirar», no darlos por perdidos. Revisando 22 a mano: 17 eran designaciones de motor
o de chasis, y **5 eran números de fábrica reales con la marca pegada adelante** («AGCO SISU
POWER836122282», «JOHN DEERER43413»). Con el castigo en rojo esas 5 quedaban como basura; en
amarillo cuestan una mirada, que es lo que cuestan.

### El efecto, medido sobre los 3.185

| | hoy | después |
|---|---|---|
| 🟢 se puede aprobar sin mirar | 2.266 | **2.456** |
| 🟡 conviene una mirada | 502 | 335 |
| 🔴 casi seguro mal | 417 | 394 |
| **hay que mirar a mano** | **919** | **729** |

190 decisiones manuales menos, y **104 vínculos con un motor como número de fábrica salieron
del botón de aprobar en bloque**. Ninguno de los 2.456 verdes tiene una señal en contra ni una
alarma.

### Lo que no queda perfecto, dicho como es

Revisé 15 de los 324 que subieron a verde por la señal nueva: 14 son números de fábrica reales
(`7702023675` de Renault, `06A103383AN` de VW, `BB3Q6051C1A` de Ford). **Uno no**: `MF:1075`, que
es un modelo de tractor Massey Ferguson, y el detector de referencias no lo agarra porque esa
descripción no tiene zona de referencias.

O sea: el botón de aprobar en bloque queda **más limpio que antes** —salen 104 y entra cerca de
una veintena— pero no queda limpio. La basura que queda es la misma clase de siempre: un modelo
de vehículo metido en la columna del código de fábrica, y se sigue atacando por donde ya se
venía atacando, en «Puentes que hoy ya no se generarían».

## Pegar códigos de barras en masa nunca funcionó por la opción que viene puesta

```sql
SELECT id, codigo_barras FROM productos p
JOIN marcas m ON m.id = p.marca_id
WHERE p.codigo_clean = ? AND m.tipo <> 'OEM'
```

`id` está en `productos` **y** en `marcas`. Sin calificar, SQLite corta con
`ambiguous column name: id`.

Lo que lo vuelve grave es cuál es esa rama. Corre cuando no se elige una lista en el
desplegable, y esa es la **primera opción**, o sea la que viene puesta:

```python
_opc_b = {"— todas las listas (más riesgoso) —": None}
```

El recorrido completo: subir la planilla, mapear las columnas, ver el preview, tildar el
candado, apretar «🏷️ Pegar los N códigos de barras» — y la pantalla se cae con un error crudo.
Cero códigos cargados, y **ni siquiera queda anotado**, porque la excepción no la atrapa nadie.
La única manera de que la herramienta anduviera era acordarse de elegir una lista concreta.

Una cosa tranquiliza: reventaba en el primer `SELECT`, antes de cualquier `UPDATE`. Era «no
anda», no «deja la base a medias».

### El chequeo 35: preparar cada consulta de verdad

El chequeo 30a compara `alias.columna` contra el mapa de columnas y es útil, pero solo ve lo
que está calificado. La columna **sin** alias en un JOIN se le escapa entera.

Así que en vez de razonar sobre el texto, el chequeo 35 arma el esquema ejecutando los
`CREATE TABLE` y `ALTER TABLE` que están en el propio `app.py` —39 tablas, 47 alters, 34
índices— y después **prepara** cada consulta literal con `EXPLAIN`. Lo que SQLite acepta, pasa.
No hace falta la base real.

Los pedazos de SQL que se concatenan o se formatean en tiempo de ejecución no se pueden
preparar y se saltean: dan `incomplete input` o `unrecognized token "{"`. Medido sobre `app.py`:
de **541 consultas literales, 51 son pedazos** y el resto prepara limpio.

La comprobación que importa: sobre el archivo con el bug adentro el chequeo devuelve
**exactamente 1 hallazgo, el bueno**; sobre el arreglado, 0.

## Las 114.673 aplicaciones nunca se cargaron, y la app decía que sí

La tabla `aplicaciones` —la que dice qué repuesto le va a cada auto— tiene **0 filas**. Y la
configuración dice que el trabajo está hecho: `aplicaciones_pendientes = 0`,
`version_aplicaciones = 2`.

Las dos cosas no pueden ser ciertas, y la prueba de cuál miente está en la misma tabla: las
claves `aplicaciones_deducidas` y `aplicaciones_fecha`, que se escriben **recién al terminar**,
no existen. Tampoco existen `medidas_completadas`, `medidas_fecha`, `confianza_repuntuada` ni
`confianza_fecha`. Ninguno de los tres trabajos de fondo dejó nunca su marca de terminado.

El porqué está en una sola línea, y es del tipo que no se ve leyendo:

```python
if obtener_config("aplicaciones_pendientes", "") == "1":
    try:
        guardar_config("aplicaciones_pendientes", "0")   # se apaga ANTES de trabajar
        _apl_ded = aplicaciones_desde_descripciones()    # 48 segundos
```

Si el proceso se muere en esos 48 segundos, la bandera ya está en «0» y **nadie la vuelve a
prender**. Un proceso que muere no lanza una excepción, así que el `except` que la reponía no
llega a correr nunca. Y morirse es lo normal: Streamlit Cloud se redespliega, se reinicia y
recicla el contenedor. El hilo es `daemon`, o sea que se va con el proceso, a mitad de camino.

Apagarla antes tampoco protegía de nada: que no corran dos a la vez ya lo asegura
`_CANDADO_FONDO`, que se toma en `arrancar_tanda_de_fondo()`.

Ahora la bandera se apaga en `_quedo_hecho()`, **después** de que el trabajo terminó. Y como
eso solo haría que un trabajo que siempre falla se reintente para siempre, `_hay_que_hacerlo()`
cuenta los intentos: a los cinco se rinde y anota el error, que es lo que hay que ver.

Para que las que faltan se carguen en las bases que ya dicen «hecho», `VERSION_APLICACIONES`
pasa a «3». Comprobado sobre una copia de la base real: la marca de versión vuelve a pedir el
trabajo (`aplicaciones_pendientes` de «0» a «1»), la deducción carga **114.673 filas de 87
marcas de auto y 4.229 combinaciones en 48 s**, y el tope de reintentos corta al sexto.

### Y no había ningún botón para correrlo a mano

Esa era la parte peor. La deducción existía solo adentro de la tarea de fondo: si el hilo se
moría, no había nada que apretar. La herramienta «🏭 Catálogo de aplicaciones» solo sabía subir
un PDF de NGK o de Bosch.

Ahora arriba del archivo hay un **🧠 Deducir de mis descripciones**, porque el que llega ahí con
la tabla vacía no necesita salir a buscar el catálogo de un fabricante: el dato está adentro de
lo que ya importó.

Y el aviso de salud cambió de tono. Decía, en amarillo, «Sin catálogos de aplicaciones
cargados — varios fabricantes los publican gratis», que manda a buscar afuera algo que está
adentro. Ahora dice en rojo **«La búsqueda por vehículo no tiene datos»** y señala el botón.

## Una expresión regular en lugar de 522 búsquedas por descripción

`clasificar_repuesto()` hacía `texto.find(f" {clave} ")` por cada clave y por cada plural: 261
claves × 2 formas = **522 `str.find` y 522 f-strings por descripción**. Con cProfile sobre el
catálogo entero eran 24.348.168 llamadas a `str.find`, el ítem número uno del perfil.

Ahora es una sola expresión alternada, construida una vez. La alternación de Python devuelve el
match más a la izquierda y, a igual posición, la alternativa listada primero: ordenando las
formas de más larga a más corta, eso **es** el criterio de desempate de antes —`(posición,
-largo)`— sin escribirlo.

| sobre las 70.888 descripciones reales | antes | después | |
|---|---|---|---|
| `clasificar_repuesto()` | 10,26 s | **0,70 s** | 14,6× |
| `familia_para_comparar()` | 13,16 s | **3,36 s** | 3,9× |

**0 diferencias** en las dos, descripción por descripción, más los tipos raros que llegan de una
planilla (`None`, `''`, un número, bytes).

### Lo que NO se hizo, y por qué

El mismo bucle está en `familia_para_comparar()` y la tentación era cambiarlo igual. Se probó y
**cambia 60 resultados**: las dos preguntas no son la misma. `clasificar_repuesto()` busca UNA
clave, la de más a la izquierda, y la alternación la da gratis. La otra necesita saber CUÁNTAS
familias distintas nombra el texto, y una expresión regular consume lo que va encontrando: en
«JUNTA TAPA DE CILINDROS», si una clave es «JUNTA TAPA», se la come entera y ya no puede ver
también «TAPA» de otra familia.

Puede que los 60 nuevos sean mejores —«Jgo. Junta tapa de cilindros» pasaba de «Sin clasificar»
a «Juntas y retenes»— pero eso es un cambio de criterio, y un cambio de criterio no entra
escondido adentro de un arreglo de velocidad. El bucle se quedó como estaba, y la función igual
bajó 3,9× porque lo caro lo tenía abajo.

## Se podían reservar 7 unidades de un stock de 5

`reservar_stock()` preguntaba cuánto hay libre **afuera** del candado y metía la reserva
adentro. Entre la pregunta y la respuesta se cuela la otra sesión.

Y es exactamente el caso que la tabla de reservas existe para evitar. Está escrito en el
comentario de su propia tabla: *«Con varios atendiendo a la vez, vender dos veces la misma
pieza es cuestión de tiempo: uno cotiza 4 pastillas, el otro ve stock 4 y las vende.»* El
agujero estaba en la función que lo tenía que tapar.

Reproducido sobre una copia de la base real — stock 5, dos sesiones a la vez:

```
pidió 4 -> (True, 'Se apartaron 4 unidad(es).')
pidió 3 -> (True, 'Se apartaron 3 unidad(es).')
RESERVADO EN TOTAL: 7 sobre un stock de 5
```

Ahora la lectura va adentro de `db_lock` y de `transaccion()`. `BEGIN IMMEDIATE` además pide el
candado de escritura de SQLite desde el arranque, así que tampoco se cuela otro proceso, no
solo otro hilo. Verificado en cuatro escenarios: 4+3, 3+3, 5+5 y 1+1 sobre stock 5. En los tres
primeros entra una sola y la otra recibe el «solo quedan N»; en el último —que es legítimo—
entran las dos. Nunca se pasa de 5.

## Un costo de $0 se guardaba como «sin costo»

`actualizar_precio_stock()` hacía `costo or None`, y en Python el cero es falso. Pedir que el
costo quede en 0 —mercadería bonificada, una muestra— guardaba NULL.

```
se pidió guardar costo=5000.0 -> quedó 5000.0
se pidió guardar costo=0.0    -> quedó None
```

Que el cero es un valor que esta app usa de verdad se ve en la misma base: hay **21 productos
con precio 0**. Quién decide si el costo se toca es `costo is not None`, que es la pregunta
correcta; el `or` de adentro solo pisaba un valor legítimo.

En la misma función había un segundo problema: si el producto **ya no existe** —lo borró la
otra sesión mientras la pantalla estaba abierta— los dos UPDATE no encontraban fila y se iban
en silencio, pero el INSERT del historial sí se intentaba, porque `precio_anterior` quedaba en
None y None siempre es distinto del precio nuevo. Con las claves foráneas prendidas, que lo
están, eso revienta con `IntegrityError` adentro de la transacción y la pantalla se cae con un
error crudo. Ahora la función devuelve `False` y la pantalla dice qué pasó, en vez de mentir un
«Guardado».

## Una segunda opinión, de otro modelo

Las tres compuertas de arriba cazan lo que ya nos rompió la app alguna vez: cada control del
auditor y cada prueba salió de un error real. Lo que por definición no pueden cazar es lo que
todavía no se nos ocurrió mirar.

Ahí gana un modelo distinto, y no porque sea mejor: porque **se equivoca en otros lugares**. En
este repositorio está probado. Dos de los peores agujeros los encontró Gemini leyendo el
código, no las compuertas:

- el `pickle.loads()` de las firmas visuales, que dejaba ejecutar código cualquiera con un blob
  armado a mano;
- el `<` de las descripciones, que se comía medio renglón en 1.435 productos porque el
  navegador lo tomaba como una etiqueta HTML abierta.

Hasta ahora ese circuito era a mano: copiar el código, pegarlo en Gemini, leer las capturas.
`revisar_con_gemini.py` lo hace solo sobre el diff.

```bash
export GEMINI_API_KEY="..."                              # nunca en el repositorio
python3 revisar_con_gemini.py                            # lo que no commiteaste todavía
python3 revisar_con_gemini.py --desde main               # todo lo que la rama le agrega a main
python3 revisar_con_gemini.py --funcion evaluar_equivalencia
```

Tres decisiones que vale la pena explicar:

**Le pasa el contexto del proyecto.** Sin eso marca como problemas cosas que son decisiones
tomadas y medidas —el autocommit, los comentarios largos, el paquete `nucleo/` generado— y la
revisión se vuelve ruido que se aprende a ignorar. También le dice qué controla ya el auditor,
para que no lo repita.

**Nunca devuelve error.** No es una compuerta que bloquea. Cada hallazgo hay que comprobarlo
contra la base real antes de tocar código, igual que con las capturas; un modelo que marca de
más no puede frenar un push. Y «sin hallazgos» no quiere decir que esté bien: quiere decir que
ese modelo, leyendo ese diff, no vio nada.

**Corta antes de mandar si en el diff hay algo con forma de clave o de token.** Esto sale a un
servicio externo. Está probado con una clave falsa en el diff: corta y no envía.

### Estreno: lo que encontró en la primera corrida

Se corrió sobre el diff del día (las variantes de junta y el backup por WAL) y devolvió dos
hallazgos. **Los dos eran ciertos**, y ninguno lo habían agarrado el auditor, las 48 pruebas ni
el barrido de pantallas.

**1. Un comentario que mentía.** El docstring de `codigo_base_sin_variante()` decía que de
«TC-687-20 2M» devuelve «TC-687-20». Devuelve «TC-687»: el `while` recorta todos los tramos
cortos del final, no uno. El código está bien —está medido que de los 350 grupos que se
sueltan, 42 dependen de ese segundo recorte y los 42 son la misma junta en otro material—, pero
el comentario decía otra cosa, y en este repositorio un comentario que miente es un error: es
justamente lo que el prompt le pide buscar, y cayó uno propio en la primera corrida.

**2. El archivo temporal del backup tenía nombre fijo.** `backup_completo.db` en la carpeta de
temporales, igual para todos. La app está hecha para que la usen dos personas a la vez, así que
si los dos tocan «Preparar backup», el segundo le borra el archivo al primero mientras SQLite
lo está escribiendo. Gemini lo puso en «confianza media»; medido, es peor: con el nombre fijo y
cuatro pedidos simultáneos **fallan los cuatro, todas las veces** — `disk I/O error`,
`no such table: productos` y `FileNotFoundError`. Con un nombre único por llamada, los cuatro
devuelven la base entera con `integrity_check` en ok.

El mismo error estaba en `generar_backup_sin_fotos()` desde antes; Gemini no lo vio porque no
estaba en el diff. Los dos quedaron arreglados, con `destino.close()` en un `finally` —si
`backup()` se cae, la conexión quedaba abierta contra el temporal y el borrado fallaba— y con
el **chequeo 33** del auditor, que marca cualquier temporal con nombre fijo que vuelva a
aparecer.

De paso salió un tercero, mío: el comentario de `generar_backup_completo()` decía que
«`backup()` no acepta el proxy por sesión». Eso vale cuando el proxy es el DESTINO
(`restaurar_backup()`), no cuando es el origen — `_ConexionPorSesion` tiene su propio
`.backup()` y es el que usa el backup liviano desde siempre. Había copiado el motivo del lado
equivocado.

### Lo que esto NO resuelve

El cuello de botella de este proyecto no es pensar, es **medir**. Lo de las variantes de junta
—350 grupos de 557— fueron cinco minutos de idea y cuarenta de comprobarlo contra los 70.888
productos y revisar 22 grupos a mano. Dos modelos tirando el doble de ideas **duplican el
trabajo de verificación, no lo dividen**. Por eso la segunda opinión sirve como revisor
independiente y no como segundo obrero.

## La misma junta en otro espesor no es un error de carga

La cola de revisión tenía 3.185 vínculos: 🟢 1.785, 🟡 695, 🔴 705. Mirando los 695 amarillos
apareció algo raro: **los 695 tenían cero señales en contra**. Ninguno. Estaban ahí por una sola
cosa, la misma para todos:

> ⚠️ El código 7785351 apunta a más de un producto de ILLINOIS — alguno de los dos está mal cargado

Esa alarma resta 35 puntos y la idea es correcta: el fabricante tiene UNA pieza por número, así
que dos productos del mismo proveedor colgando del mismo número quieren decir que alguno se
cargó mal. Pero mirando qué cuelga del 7785351:

```
TC-615-MG 0M   Junta Tapa de Cilindros FIAT (ESP 1.65MM) FIORINO UNO TIPO PALIO ...
TC-615-MG 4M   Junta Tapa de Cilindros FIAT (ESP 2.40MM) FIORINO UNO TIPO PALIO ...
TC-615-20 0M   Junta Tapa de Cilindros FIAT (ESP 1.65MM) FIORINO UNO TIPO PALIO ...
```

Es **la misma junta** en dos espesores y dos materiales. Las tres entran en ese motor y las tres
corresponden a ese número de fábrica. No hay nada mal cargado: ILLINOIS vende la junta en varias
medidas, como todo el rubro de juntas.

Lo que distingue a una variante es el **código**, no la descripción. El proveedor numera las
variantes agregando un sufijo corto: `TC-615-…`, `JVL-168-24 / -28 / -34`, `JI-276` y `JI-276-R`
(el mismo juego, con retenes). `codigo_base_sin_variante()` recorta esos sufijos y nunca baja de
dos tramos, que es lo que evita pasarse: el compresor `OHL355` cuelga `JCA-120`, `JCA-121`,
`JCA-122` y `JCA-123` —cuatro kits **distintos**— y recortando de más quedarían todos en «JCA».

Y a propósito **no** alcanza con que las descripciones coincidan, que era el atajo tentador: esos
cuatro kits de compresor están descriptos los cuatro «Juego de juntas para Compresor de Aire
KNORR».

| | grupos | |
|---|---|---|
| disparaban la alarma | 557 | |
| son variantes de una misma pieza | **350** | se sueltan |
| son piezas distintas de verdad | **207** | siguen marcados |

Los 207 que quedan son los que la alarma vino a cazar: el `7703061078` cuelga `2712800`
(guarnición de bomba depresora) y `2627400` (arandela de fibra de tapa de válvula); el `4JH1TC`
cuelga la junta de tapa de cilindros sola y el juego completo de reparación.

Efecto en la cola, sobre los 3.185 pendientes reales:

| | antes | después |
|---|---|---|
| 🟢 se puede aprobar sin mirar | 1.785 | **2.266** |
| 🟡 conviene una mirada | 695 | 502 |
| 🔴 casi seguro mal | 705 | 417 |

Y el control que importa: de los 2.266 verdes, **ninguno** tiene una sola señal en contra ni una
sola alarma — ni rubros distintos, ni medidas que se contradigan. Se revisaron a mano 22 grupos
sueltos al azar y los 22 son variantes de espesor o de material.

De paso, un error que estaba al lado: el grupo de «qué cuelga de este código de fábrica» se
armaba con TODAS las filas, y cuando ninguno de los dos lados era de fábrica igual tomaba el
código B como si lo fuera. El uso ya estaba protegido —se arregló cuando se vio que entre dos
proveedores un código repetido no significa nada— pero armar el grupo con códigos que no son de
fábrica solo puede meter ruido. Ahora se arma solo con las filas que tienen un lado de fábrica.

## El backup completo podía bajarse sin la mitad de la base

El botón **Backup y config → Preparar backup completo** hacía `open(DB_PATH, "rb").read()`:
leía el archivo `.db` a mano. La base anda en **modo WAL**, o sea que todo lo escrito desde el
último *checkpoint* vive en `equivalencias_app.db-wal`, no adentro del `.db`. Leer el archivo
crudo entrega la base como estaba hace un rato — y ni siquiera de forma pareja, porque el
checkpoint corre cuando SQLite quiere.

Medido con una base nueva en WAL, 5.000 filas insertadas y **commiteadas**:

| | tamaño | al abrirlo |
|---|---|---|
| el `.db` crudo, como lo bajaba el botón | 4.096 bytes | `no such table: productos` |
| `conn.backup()` | 94.208 bytes | las 5.000 filas |

O sea que el backup completo podía entregar un archivo **que no tenía ni la tabla**. Y ese es
el archivo con el que se restaura todo cuando el hosting borra el disco: no hay otra copia
atrás. Un backup que miente es peor que no tener backup, porque uno deja de revisar.

Lo más incómodo es que era el **mismo error, del otro lado**. Hace unos días se arregló
`restaurar_backup()` por exactamente esto y el comentario de esa función explica el WAL en
detalle; el camino de salida quedó sin tocar. El backup liviano —el que se sube al
repositorio— ya usaba `backup()` desde el principio, y por eso el problema no se veía: el que
se genera todos los días salía bien.

Ahora hay `generar_backup_completo()`, que copia con la API `backup()` de SQLite. Sobre la base
real: 38,0 MB en 0,1 s, 70.888 productos, 24.774 equivalencias, `PRAGMA integrity_check` = ok.
Y el **chequeo 32** del auditor marca cualquier `open(DB_PATH, ...)` que vuelva a aparecer,
verificado reproduciendo la línea vieja.

## El aviso rojo gritaba 31 códigos puente y el verdadero era uno

`contar_codigos_puente()` contaba los códigos con más de 30 vínculos. Sobre la base real daban
31, el aviso salía en **rojo todos los días**, y mirando la columna que importa:

| vínculos | códigos | de ellos, con 1 sola marca |
|---|---|---|
| más de 15 | 76 | 75 |
| más de 30 | 31 | 30 |
| más de 50 | 8 | 7 |

Un puente es, por definición, un código que **fusiona familias de proveedores distintos**. Si
todos sus vínculos se quedan adentro de una marca, no está puenteando nada. Y hay un caso
perfectamente sano que tiene decenas de vínculos en una sola marca: la tabla de referencias
cruzadas que el propio proveedor publica. `LRAC03043LUCAS` tiene 65 vínculos y una sola marca
porque su descripción lista 45 códigos de fábrica de Bosch, Delco, Valeo y Magneti Marelli, y
los 45 son ciertos.

El único puente de verdad es **`CHAPA`** —la palabra, cargada como código— con 76 vínculos y 2
marcas.

Ahora el aviso cuenta los que tocan **2 marcas o más**: de 31 pasa a **1**, y tarda lo mismo
(46 ms → 44 ms). La pantalla sigue mostrando los 76 con la columna «Marcas distintas» al lado,
porque mirarlos no hace daño; lo que cambia es de qué avisa la app sola. Un aviso en rojo que
grita 31 cuando hay 1 enseña a ignorar los avisos, incluso los que importan.

Honestidad sobre una parte: la lista de la pantalla ahora se ordena por marcas distintas antes
que por vínculos, y **hoy eso no cambia nada** — `CHAPA` también es el que más vínculos tiene,
así que ya encabezaba. El orden está por el día que aparezca un puente con 20 vínculos
repartidos en 5 marcas: ese hace mucho más daño que 60 vínculos adentro de una sola, y
ordenado por vínculos quedaría abajo de treinta motores de arranque inofensivos.

## 254 errores que la app se tragaba en silencio, todos el mismo

Se me ocurrió contar los errores que la app decide ignorar —`anotar_error()` los guarda y
después nadie los mira— durante una corrida completa de la tarea de fondo. Salieron **254, y
los 254 eran el mismo**:

    autos_de_todas_las_fuentes → OperationalError: no such column: v.marca

`autos_de_todas_las_fuentes()` junta a qué autos le va un producto desde tres lugares, y su
docstring los enumera: el catálogo del fabricante, **las fichas de vehículo del propio taller**,
y la descripción. La consulta de la fuente 2 pedía `v.marca` y `v.modelo`, y esas columnas se
llaman `marca_auto` y `modelo_auto`.

O sea que **esa fuente no anduvo nunca**. Y no se notaba porque la consulta está adentro de un
`try / except OperationalError` que la tapa: la app seguía andando con dos fuentes de tres, y la
tercera —la única que sale de tu propio taller, la que sabe que a ese Ranger le pusiste esta
pieza— devolvía vacío siempre.

Probado antes y después con un auto cargado y una pieza puesta:

| | autos que aporta la ficha del taller |
|---|---|
| antes | `[]` — y un error tragado |
| después | `['FORD', 'RANGER']` — 0 errores |

Durante el ciclo completo de la tarea de fondo: **254 errores → 0**.

### El chequeo que faltaba

Una consulta que nombra una columna inexistente, adentro de un `try/except`, es un error que
puede vivir para siempre. El **chequeo 30a** del auditor arma el mapa de columnas leyendo los
`CREATE TABLE` y los `ALTER TABLE ADD COLUMN` del propio archivo, y después controla cada
referencia `alias.columna` de cada consulta contra la tabla de ese alias.

Es a propósito conservador: solo juzga un alias cuya tabla conoce entera, y saltea las
consultas con CTE o subconsultas, donde un alias puede ser una tabla armada al vuelo. Verificado
con dos casos rotos a propósito — el error real de hoy, y una columna inventada en `productos`.

## Lo mismo, dos veces: el texto que se separaba una y otra vez

Salió de cronometrar las ocho pantallas contra la base real. Casi todas responden en 1,3-1,8 s,
pero dos funciones se llevaban todo:

| | antes |
|---|---|
| `marcas_vehiculo_disponibles()` (Modo Mecánico → Repuestos por vehículo) | **6,44 s** |
| `_contar_descripciones_pegadas()` (Mantenimiento → Limpiar y corregir) | **2,77 s** |
| `aplicaciones_desde_descripciones()` (la tarea de fondo) | **36,8 s** |

Las tres pasan por el mismo lugar: `separar_texto_pegado()`, que hace **seis pasadas de
expresión regular** sobre cada descripción, y `marcas_vehiculo_en()`, que la llama y encima
corre la expresión de las 174 marcas de vehículo.

Y sobre las 70.888 descripciones reales hay **27.201 repetidas (el 38%)**, porque el producto
OEM se crea copiando la descripción de la fila del proveedor. Esas 27.201 se estaban volviendo
a separar, y a parsear, cada vez.

Las dos funciones ahora recuerdan su resultado por descripción (`lru_cache`, 50.000 entradas —
las distintas de esta base son 43.687). Son funciones puras: dependen del texto y de constantes
que se arman una sola vez al abrir el archivo.

| | antes | después |
|---|---|---|
| `marcas_vehiculo_disponibles()` | 6,44 s | **2,97 s** |
| `_contar_descripciones_pegadas()` | 2,77 s | **1,41 s** |
| `aplicaciones_desde_descripciones()` | 36,8 s | **19,1 s** |

Comprobado que no cambia nada: sobre las 70.888 descripciones, **0 resultados distintos** en las
dos funciones, y lo mismo con los tipos raros que llegan de una planilla (`None`, `''`, un
número, bytes).

Un cuidado que hacía falta: `marcas_vehiculo_en()` devuelve una **lista**, y devolver siempre el
mismo objeto significa que dos pantallas comparten la lista y la que la modifique le cambia el
resultado a la otra. Se guarda una tupla y se devuelve una lista nueva cada vez — copiar tres
tuplas no cuesta nada al lado de la expresión regular.

### Tres errores que aparecieron haciendo esto

**1. La app no arrancaba.** El decorador `@functools.lru_cache(maxsize=MAXIMO_...)` quedó arriba
de una función que estaba ANTES de donde se define esa constante. Los decoradores se evalúan al
importar el archivo, de arriba hacia abajo: `NameError` apenas se abre la app, pantalla en
blanco. Lo agarró el barrido de pantallas, no el auditor — el chequeo que controla el orden
miraba las *llamadas* al arrancar, no los decoradores. Ahora está el **chequeo 30b**, verificado
reproduciendo el archivo roto.

**2. El paquete `nucleo` se comía el decorador.** `nucleo/generar.py` copia el CUERPO de cada
función, así que el `@lru_cache` quedaba afuera y en el paquete la función corría sin caché —
haciendo el doble de trabajo que en `app.py`, sin que nadie se enterara. El generador ahora se
lo devuelve, y el **chequeo 31** controla que ese ajuste siga estando.

**3. Un `while True` en un hilo de fondo.** El llenado de medidas giraba hasta que la consulta
no devolviera filas. Si alguna vez el lector devuelve una medida que la escritura no deja
guardada —una columna que no existe, un valor que vuelve NULL—, la consulta devuelve las mismas
filas para siempre y el hilo queda girando sin que nadie lo vea. Ahora tiene tope de vueltas y
corta con un error anotado si una tanda no completa nada.

### Dos cosas que se comprobaron y estaban bien

**La tanda de fondo no se siente.** Ahora hace 96 s de trabajo la primera vez que se abre la app
—medidas, aplicaciones, repuntaje— y la duda razonable era si eso traba la pantalla, porque
escribe 114.673 filas tomando el candado de la base. Medido con los tres pedidos forzados y 30
refrescos seguidos del buscador **mientras el hilo trabajaba**: peor 1,51 s, mediana 1,43 s —
los mismos números que con todo quieto.

**La base vacía arranca.** Es el caso de un usuario nuevo y el de después de que el hosting
borra el disco, y lo tocan las tres marcas de versión nuevas. Arranca en 1,7 s, las ocho
pantallas dibujan sin una sola excepción, la tarea de fondo no hace nada (no hay qué procesar) y
no se traga ningún error.

## A qué auto le va cada pieza: 114.673 filas que ya estaban en el texto

La tabla de aplicaciones —lo que hace andar la búsqueda por vehículo— tenía **0 filas**, y las
descripciones de los proveedores dan **114.673**. La función que las lee existía y andaba, pero
corría solo después de importar una lista; en una base donde no se importó nada desde que existe
esa función, nunca corrió.

Ahora corre sola, por `VERSION_APLICACIONES`, igual que las medidas y el repuntaje: al abrir la
app se deja pedido y lo hace la tarea de fondo. Resultado sobre la base real: **87 marcas de
auto, 4.229 combinaciones marca+modelo**, VW con 432 modelos y 17.990 piezas.

### Pero antes de prenderla, dos cosas que aparecieron midiendo

**1. Los motores entraban como si fueran modelos.** «RENAULT K4M», «PEUGEOT TU5JP4»,
«CHEVROLET Z18XER» — el K4M solo movía 184 filas. `modelos_de_marca()` los confirma como
modelos legítimamente: su regla es «esta palabra aparece muchas veces y casi solo en esta
marca», y un motor de Renault cumple las dos. Pero nadie busca repuestos «para un K4M», y como
el motor aparece en decenas de descripciones, junta entre sí todo lo que lo nombre.

`parece_designacion_de_motor()` saca **566 combinaciones y 6.048 filas (5%)**, y entre las 566 no
hay un solo modelo de verdad: son los motores de Renault, de PSA y de Opel.

El primer intento estuvo mal y vale contarlo, porque se vio enseguida midiendo: preguntarle al
extractor de códigos «¿esto sería un código?» tiraba **GOLF, CLIO, FIESTA y PALIO — el 88% de
las aplicaciones**, porque el extractor exige que haya un dígito. La pregunta no era «¿esto
sería un código?», era «¿esto tiene la forma de un motor?». Las dos expresiones de motor ahora
están a nivel de módulo, compartidas con el extractor, para no tener dos copias de la misma
regla.

**2. Cargarlas le sumaba 25 de confianza a casi todo sin aportar nada nuevo.** El puntaje tiene
una señal que vale +25 y se llama «🏭 el catálogo del fabricante respalda este vínculo», y se
alimenta de la tabla de aplicaciones. Una aplicación **deducida** no sale de ningún catálogo:
sale de leerle el auto a la misma descripción que el resto de las señales ya está comparando.
Contarla es contar dos veces la misma evidencia, y encima decirle al usuario algo que no es
cierto. Lo mismo en `evidencia_cruzada()`, donde cuenta como uno de los tres caminos
independientes que fuerzan el puntaje a 90.

Las dos consultas ahora piden `origen <> 'deducida'`. Las aplicaciones deducidas sirven para
buscar por vehículo y para el cruce por auto; no para decir que lo dice el fabricante.

### Y una decisión de alcance que también salió de probarlo

La primera versión, después de cargar las aplicaciones, pedía el descubrimiento **completo**. Eso
larga también el barrido de todo el catálogo —que no necesita las aplicaciones para nada— y la
cola de revisión pasaba de **3.185 a 22.235** de una sola vez.

Que crezca así está bien después de importar una lista: hay algo nuevo que mirar. No está bien
cuando lo único que pasó es que la app se actualizó — nadie pidió 9.000 pares nuevos, y abrir la
app y encontrarlos parece que algo se rompió. Ahora se corre solo **el cruce por auto**, que es
el paso que usa las aplicaciones. El barrido sigue corriendo después de cada importación, como
siempre.

Probado de punta a punta sobre una copia de la base, con todas las tandas automáticas apagadas:
la tarea de fondo tarda **96 s**, completa 1.402 productos con medidas, carga 114.673
aplicaciones con **0 motores adentro**, repuntúa los 24.774 vínculos, agrega **10** pares del
cruce por auto (cola: 3.185 → 3.195) y la segunda corrida no repite nada.

Lo que queda sucio y no se filtró: la cola de modelos raros —«AUDI ACLARACION», «AUDI SAME»,
«BMW BOSCH-HALL»— que salen de palabras sueltas de la descripción. Aparecen una o dos veces cada
una, así que mueven ~2% de las filas, y filtrarlas por forma sería adivinar. La defensa que ya
hay es la de `modelos_de_marca()`: si una palabra aparece en varias marcas, no es un modelo.

## Los datos ya estaban escritos en la descripción: el espesor y las vías

La pregunta fue qué más datos automáticos se pueden poner. Lo primero fue medir qué hay cargado
hoy, columna por columna, sobre los 70.888 productos:

| dato | cargado |
|---|---|
| precio | 46.644 (65,8 %) |
| stock | **0** |
| fotos | **0** |
| aplicaciones (qué auto lleva cada pieza) | **0** |
| todas las medidas juntas | **0** |

Y las descripciones están llenas de datos que nadie lee. Dos de ellos son exactamente los que
hacen que dos piezas **no** sean intercambiables aunque todo lo demás coincida:

### El espesor de la junta

    Junta Tapa de Cilindros ISUZU (ESP 1.50MM) TROOPER ...
    Junta Tapa de Cilindros ISUZU (ESP 1.60MM) TROOPER ...
    Junta Tapa de Cilindros ISUZU (ESP 1.70MM) TROOPER ...

Tres piezas distintas —el espesor cambia la relación de compresión— y para todas las reglas de
texto de la app son casi la misma fila. **630 productos lo traen escrito y había 0 cargados.**

Consecuencia medida: **32 vínculos esperando revisión unen juntas de espesor distinto**. El peor
propone el mismo código de fábrica para 0,2 / 0,3 / 0,5 y 0,8 mm a la vez.

### Las vías de la ficha

Un sensor de 2 polos y uno de 3 no son intercambiables, y la descripción lo dice. **483 productos
lo traen escrito, 0 cargados.** Y hay dos vínculos **ya cargados** que unen un sensor de rotación
de 3 polos con uno de 2 —misma marca, mismo auto, misma resistencia— que el buscador venía
mostrando con **95 de confianza**.

### El tope que faltaba: la medida le ganaba al código

Cargar las medidas no alcanzaba, y esto solo se vio probándolo. `evaluar_equivalencia()` dice
arriba de todo que las medidas que se contradicen son «prueba física en contra, no hay vuelta»,
pero **restaba 45 en vez de topear**. Ese sensor de 3 polos contra el de 2 bajaba a 20 por la
medida y volvía a 50 porque el código de fábrica que los une es largo y cuelga pocos productos.
Quedaba arriba del umbral, la auditoría no lo mostraba nunca, y el buscador lo daba por bueno.

Que el código «parezca un código» no puede ganarle a que las dos piezas midan distinto: lo
primero es una pista sobre el número, lo segundo es la pieza. Ahora topea.

Resultado sobre la base real:

| | antes | después |
|---|---|---|
| Pares de juntas con espesor distinto en la cola | 4 🔴 / 28 🟠 | **32 🔴**, con «📐 NO coinciden: espesor: 0.2 vs 0.3» |
| Vínculos cargados marcados por medidas | 0 | **3** (2 de vías, 1 de paso de rosca) |
| Confianza guardada de los dos sensores | **95** | **30** |

El tercero apareció solo: `7700785258 ↔ BS4508`, paso de rosca 1 contra 1,5. No es que se
parezcan poco — es que no enrosca.

### Y que pase solo

Llenar las medidas era un botón en Mantenimiento que había que saber apretar, y el resultado se
ve en la tabla de arriba: 0 cargadas con 1.402 productos que las tenían escritas. Ahora corre en
dos momentos, sin que nadie lo pida:

- **Después de cada importación**, como primer paso del descubrimiento. Va primero porque es lo
  más barato (3 s sobre 70.888 productos) y porque SACA vínculos falsos: con la medida cargada,
  los cuatro pasos siguientes ya cuentan con la prueba física.
- **Cuando el lector aprende a leer algo nuevo**, por `VERSION_MEDIDAS`, igual que la versión del
  índice de búsqueda y la de confianza. Al abrir la app se deja pedido y lo hace la tarea de
  fondo, que arranca también por esto aunque estén apagadas las tandas automáticas.

El orden entre las dos tareas de fondo importa y está escrito: **las medidas van antes que el
repuntaje**, porque el puntaje las usa como prueba física y repuntuar primero sería repuntuar sin
ellas.

Probado de punta a punta sobre una copia de la base: abrir la app deja los dos pedidos, la tarea
de fondo completa 1.402 productos y repuntúa los 24.774 vínculos en 16,7 s con todo lo demás
apagado, los dos sensores caen de 95 a 30, y correrla de nuevo no repite nada.

### Y una columna nueva no puede tumbar una pantalla

El barrido lo agarró: la pantalla de equivalencias sugeridas se cayó con «no such column:
espesor». La causa era del banco de pruebas —la conexión queda cacheada por Streamlit y el
archivo se reemplaza por debajo, así que la migración de esta versión no había corrido sobre esa
conexión— pero el agujero es real y pasa igual **al restaurar un backup viejo con otra sesión
abierta**, que es algo que la app hace.

`cargar_medidas_de_varios()` armaba el SELECT con una lista de columnas fija. Ahora recorta la
lista a las que la tabla tiene de verdad, y `comparar_medidas()` lee con `.get()`: lo que falte
se compara como «todavía no medido», que es exactamente lo que es. Una medida nueva agrega un
dato, no puede sacar una pantalla.

## Los vínculos viejos se juzgaban con reglas viejas

La pregunta fue: si cambiamos tanto la confianza, ¿el botón de revisión también vuelve a mirar
los que ya están cargados? Buscando la respuesta aparecieron tres cosas, una de ellas un error
mío del día anterior.

### El error mío: el veto le preguntaba lo que no correspondía

`codigo_que_hoy_no_se_tomaria()` pregunta **«¿el extractor sacaría esto de un texto?»**. Eso vale
para un código de fábrica —que se adivinó de una descripción— pero **no** para el código propio
de un proveedor, que vino de su columna. El día anterior lo había aplicado a los dos lados del
vínculo. Medido sobre los 24.774 cargados:

| | vínculos vetados |
|---|---|
| Preguntando por los dos lados | **12.508** |
| Preguntando solo por el lado del código de fábrica | **681** |

Los 11.827 de más eran pares perfectos: `10082FISPA` con `8200488774A`, misma descripción,
obviamente el mismo repuesto. Quedaban marcados como basura porque `10082FISPA` sin la marca es
`10082`, y un número de cinco cifras suelto no se adivinaría de un texto. **Nunca se adivinó:
estaba en la columna del código.** Es el principio que ya estaba escrito en el extractor —«si el
proveedor lo puso en la columna del código, es un código y se respeta»— y lo había pasado por
alto.

No llegó a hacer daño porque la cola de hoy es ILLINOIS↔OEM y esos códigos sobreviven. En la
próxima importación de FISPA habría mandado miles de vínculos buenos al fondo.

### Lo que faltaba: la misma regla en las tres partes

Hay tres lugares que puntúan un vínculo, y usaban reglas distintas:

| | qué puntúa | tenía la regla nueva |
|---|---|---|
| `analizar_lote_pendiente()` | la cola de revisión | sí |
| `auditar_equivalencias_cargadas()` | el botón «revisar los que ya están» | **no** |
| `recalcular_confianzas()` | el puntaje **guardado**, el que el buscador muestra en cada búsqueda | **no** |

Que las tres no coincidan tiene una consecuencia concreta: la pantalla de auditoría te dice que
un vínculo está mal y el buscador te lo sigue mostrando como confiable. Ahora las tres hacen el
mismo control.

Sobre la base real:

- La auditoría de cargados pasó de marcar **265** a **922** (657 nuevos, 0 perdidos). Los nuevos
  cuelgan de `ORION1` (el Ford Orion), `V8-628-635-730-735-740-840-850-M3-M5-Z3` (una lista de
  BMW), `1994REF`, `295REF`, `1998-2002REF`, `10x18mm`, `180E25`. Modelos, años y medidas.
- El puntaje guardado: **671 vínculos pasaron de «confiable» a «casi seguro mal»**. El buscador
  los venía mostrando con 80-95% de confianza colgados de `5008REF`, `150E20`, `CLA250`,
  `2007-2009REF`, `146REF`.

### Y el puntaje guardado quedaba viejo sin que nadie se enterara

La confianza se guarda en la base porque el buscador la necesita en cada búsqueda. Cuando las
reglas cambian, lo guardado queda contando una película vieja — y recalcularlo era un botón que
había que saber apretar.

`VERSION_CONFIANZA` funciona igual que la versión del índice de búsqueda que ya existía: al
abrir la app, si la versión guardada no es la de hoy, se deja **pedido** el repuntaje (no se
hace ahí: son 13 segundos) y lo corre la tarea de fondo. Esa tarea ahora arranca también por
esto, aunque estén apagadas las tandas automáticas de fotos y equivalencias — que es el caso
normal, y si no, el puntaje viejo se quedaría para siempre.

Probado de punta a punta sobre una copia de la base: abrir la app deja el pedido, la tarea de
fondo repuntúa los 24.774 en 13,8 s con todo lo demás apagado, cambian 22.257 puntajes, y
correrla de nuevo no repite nada.

La pantalla lo dice mientras pasa («se están recalculando solos en segundo plano — el análisis
de acá abajo ya usa las reglas nuevas igual, porque recalcula al vuelo») y después muestra
cuántos y cuándo.

Y se agregó la aclaración que faltaba arriba del botón: **vuelve a mirar todo cada vez que lo
corrés, con las reglas de hoy.** No queda nada marcado como «ya revisado», justamente porque las
reglas cambian y uno que pasaba limpio hace un mes puede no pasar hoy.

## La cola de revisión tenía 3.185 vínculos y ni uno solo en verde

Salió de mirar qué le queda por hacer a la app sobre la base del negocio. El aviso decía
«3.185 vínculos esperando revisión», y revisarlos de a uno es el cuello de botella: a cinco
segundos cada uno son más de cuatro horas.

Corriendo el analizador sobre esa cola, el resultado era este:

| | antes |
|---|---|
| 🟢 Muy probables | **0** |
| 🟡 Probables | 1.333 |
| 🟠 Dudosas | 1.473 |
| 🔴 Casi seguro mal | 379 |

**Cero en verde, y el puntaje más alto de los 3.185 era 65.** O sea que el botón de «aprobar
en bloque los muy probables» —que existe— no servía para nada, y había que mirar 3.185 de a uno
para aprobar una lista que estaba bien.

### Lo que el puntaje no miraba

De esos 3.185 pares, **2.495 tienen la descripción palabra por palabra igual de los dos lados**.
Y el puntaje los repartía entre 🟡 (1.330), 🟠 (1.048) y hasta 🔴 (117), porque miraba el rubro,
las medidas, el precio, las ventas y el catálogo del fabricante — pero nunca si las dos
descripciones eran **el mismo texto**.

Qué prueba eso, dicho sin exagerar: que el vínculo salió de **una misma fila** de la lista del
proveedor. El importador copia la descripción de la fila al crear el producto OEM, así que
descripción idéntica significa «esto lo declaró el proveedor en su lista», la misma clase de
evidencia que un «REF ORIG». No es una certeza —si la columna de OEM de esa lista está mal
mapeada, van a estar todas mal y todas con la descripción igual— y por eso suma fuerte pero no
blinda: el rubro distinto, las medidas que se contradicen y el puente que cuelga de veinte
productos siguen restando y tumban el par igual.

### El agujero que abrió esa señal, y cómo se tapó

Medí el resultado antes de cantar victoria, y apareció el problema: **15 pares llegaban a 100 de
confianza con un modelo de camión como código**.

    conf 100   JC-375-34  ↔  240E42
      A: Junta para Cárter FIAT IVECO CAMIÓN EURO TRAKKER STAR TECH 180E42...
      B: Junta para Cárter FIAT IVECO CAMIÓN EURO TRAKKER STAR TECH 180E42...

`240E42` es un camión Iveco y `BENZ1722` es un Mercedes 1722. Las descripciones son idénticas
—claro, el producto OEM se creó copiando esa fila— así que la señal nueva los empujaba justo
al botón de aprobar en bloque.

El arreglo es la pregunta que ya hacía el control de puentes viejos, ahora compartida en
`codigo_que_hoy_no_se_tomaria()`: *suponiendo que este código ya estuviera cargado, ¿las reglas
de hoy lo seguirían rechazando?* Si la respuesta es sí, el par se va al fondo con un cartel que
dice dónde borrar ese código. **No alcanza con que la descripción coincida: si el código no es
un código, el vínculo no sirve aunque las dos filas digan lo mismo.**

| | antes | después |
|---|---|---|
| 🟢 Muy probables | 0 | **1.784** |
| … con un modelo de vehículo adentro | — | **0** (eran 15) |
| … con rubros distintos | — | **0** |
| Pares con un código que hoy no se tomaría | repartidos | **85, todos en 🔴** |

De 3.185 revisiones a mano, 1.784 pasan a ser un botón, y los 85 realmente rotos quedan arriba
de todo con el cartel de qué hacer.

## El nombre del camión pegado al número

Buscando de dónde salían esos códigos apareció la familia entera. Las listas escriben
«M. BENZ 1618 1620» y la exportación se come el espacio: queda **`BENZ1618`**, que es el camión
1618 de Mercedes. Lo mismo con `Peugeot106`, `Renault11-R`, `MINI116I`, `Cummins-6.4`.

Y los Iveco, que se numeran «toneladas + E + caballos»: `240E42`, `260E37`, `440E39`, `720E31`,
`120E20C`.

Medido sobre los 70.888 códigos del catálogo: **29 códigos, y los 29 son modelos de vehículo**.
No tienen vínculos cargados que se pierdan, pero sí **31 esperando revisión** — 31 códigos
basura a punto de entrar, cada uno listo para colgar de sí mismo todo lo que nombre ese camión.

La lista de marcas va escrita en la capa de códigos y no sale de `MARCAS_VEHICULO` a propósito:
el extractor no puede depender de lo que la app sabe de autos, porque la capa de códigos va
antes que la de vehículos (ver `nucleo/generar.py`). Son las que aparecen de verdad pegadas a un
número en estas listas.

Los 7 que ya cuelgan dos productos o más aparecen ahora en **🧹 Limpiar y corregir → «Puentes
que hoy ya no se generarían»**, con el botón para borrarlos.

## Mantenimiento tenía 36 herramientas y una sola forma de encontrarlas: bajar

El reclamo fue «tenés que ir una banda para abajo si querés encontrar algo», y medido es
exactamente eso. Mantenimiento son **2.072 líneas y 36 herramientas**, repartidas en cuatro
grupos muy desparejos:

| grupo | herramientas | líneas de scroll |
|---|---|---|
| 🧹 Limpiar vínculos | 10 | 403 |
| 🧠 Calidad y aprendizaje | **17** | **1.060** |
| 📷 Fotos | 2 | 202 |
| 🩺 Estado y papelera | 7 | 351 |

«Calidad y aprendizaje» se había quedado con casi la mitad de todo, y adentro tenía cosas que
no se parecen en nada: buscar equivalencias nuevas, deshacer una importación, y limpiar puentes
falsos, todo en la misma tirada de mil líneas.

### 1. Seis grupos, por lo que uno viene a hacer

No por el orden en que se fueron sumando, que es como habían quedado:

| grupo | herramientas | líneas |
|---|---|---|
| 🔎 Encontrar equivalencias | 9 | 704 |
| 🧹 Limpiar y corregir | 12 | 475 |
| 🧠 Calidad y aprendizaje | 3 | 121 |
| 🏷️ Códigos de barras | 3 | 193 |
| 📷 Fotos | 2 | 202 |
| 🩺 Estado y papelera | 7 | 329 |

El grupo más largo pasó de 1.060 líneas a 704, y el que más herramientas tiene (12) es de 475.

**Nada de código se movió de lugar.** Un grupo puede aparecer en varios `if grupo ==
GRUPOS[n]:` salteados a lo largo de la pantalla, y el orden de adentro lo da el archivo. Mover
mil líneas para agrupar distinto es mucho más peligroso que repetir una guarda, y el barrido de
pantallas no distingue una cosa de la otra: vería las dos verdes. Lo único que se movió fueron
cinco líneas de una consulta que estaba separada del bloque que la usa.

### 2. Un índice arriba de cada grupo

Antes de bajar, la lista de lo que hay, en dos columnas, **con una línea de qué hace cada una**.
Eso es lo que hace que la pantalla se explique sola: sin esa línea, «🧯 Puentes que hoy ya no se
generarían» solo lo entiende el que lo programó. Ahora dice al lado: *«Puentes falsos que
quedaron cargados antes de que las reglas mejoraran.»*

### 3. Un buscador de herramientas, en dos lugares

Es lo que ningún menú resuelve: **sabés qué querés hacer y no te acordás dónde estaba**. Se
escribe lo que se busca y salen las herramientas con su grupo y un botón «Ir 👉».

Está arriba de **Mantenimiento** para el que ya está adentro, y arriba de **Administrar** para
el que todavía no sabe que existe una solapa llamada «Mantenimiento». Desde ahí el botón mueve
las dos solapas: probado desde 🏷️ Marcas, escribir «papelera» y apretar Ir deja la pantalla en
Mantenimiento → 🩺 Estado y papelera.

Busca con la misma regla que ya usa el buscador de productos —cuenta cuántas palabras coinciden
en vez de exigirlas todas, y afloja antes de devolver nada—, porque nadie escribe la palabra
exacta. Dos detalles que salieron de probarlo:

- **Al principio de una palabra, no en cualquier lado.** Buscando «no me aparece un codigo», el
  «no» de adentro de *vi**no**s* y el «un» de adentro de *una* le daban puntos a media pantalla
  y la herramienta que servía quedaba cuarta.
- **Las palabras del mostrador, no las del programador.** «borre algo sin querer» tiene que
  encontrar la papelera, y «me equivoque al cargar una lista» tiene que encontrar *Deshacer una
  importación*. Están las dos cosas en las palabras clave.

### El índice no puede mentir

Todo esto sale de una tabla escrita a mano (`HERRAMIENTAS_MANTENIMIENTO`), y una tabla a mano se
desactualiza: alguien agrega una herramienta y no la anota, o le cambia el título y no lo cambia
en la tabla. Ahí el índice pasa a prometer algo que no está, que es peor que no tener índice.

El **chequeo 30 del auditor** compara la tabla contra lo que la pantalla dibuja de verdad y falla
si sobra, falta o está en otro grupo. Verificado rompiéndolo a propósito en los tres casos.

De paso se corrigió el **chequeo 8k**: marcaba como error un índice de menú repetido, y ahora el
repetido es legítimo. Lo que hay que detectar es el índice que NO se usa —esa sí es una pantalla
inalcanzable— y ese caso ahora es ERROR en vez de REVISAR. Probado agregando un grupo al
principio de la lista: lo agarra.

## Cuando no hay foto para comparar: preguntarle a internet

La comparación visual tenía un agujero que no es un caso raro, es **el caso normal**: compara tu
foto contra las fotos que estén cargadas en el catálogo, y hoy en esta base hay **cero**. O sea
que el paso 2 no fallaba a veces — no podía encontrar nada, nunca. Y el paso 1 (leer el código
grabado) falla justo cuando más se lo necesita: la pieza gastada, tapada de grasa, o con la
etiqueta arrancada.

Ahora hay un **paso 3**. Le manda la foto a Gemini **con la búsqueda de Google activada**, así
que sale a mirar catálogos, tiendas y foros por la forma, el material, la cantidad de vías de la
ficha, los caños, los dientes y los logos parciales. Vuelve con qué pieza es, para qué autos, con
qué números se vende, y **las páginas que consultó** — sin fuente, una identificación de repuesto
no se puede verificar.

### La regla que hace que esto se pueda usar

Una IA inventa números de pieza con total seguridad, y por el texto no hay forma de distinguir
uno inventado de uno real. Por los datos sí. Entonces, de todo lo que conteste, a la pantalla
llega separado en cuatro:

| | qué es |
|---|---|
| ✅ **Exactos** | el número está en tu catálogo. Si está cargado, alguien lo vende |
| 🟡 **Por tipeo** | no está así escrito, pero tenés uno casi idéntico (`0 280 155 786` vs `0280155786`, o un dígito de diferencia) |
| ℹ️ **Por descripción** | ningún código pegó, así que busca por el tipo de pieza + el auto. Lo más flojo, y se muestra como tal |
| ⚠️ **No los tenés** | aparte, marcado como pista para pedirle al proveedor. **Nunca mezclado con lo de arriba** |

**Un código inventado cae solo en la última fila**: para colarse en las otras tres tendría que
coincidir con algo que alguien ya cargó. Probado con la base real — de `["0280155786",
"0 280 155 78", "IWP-NOEXISTE-999"]` salieron 10 exactos con precio y stock, 10 candidatos por
tipeo (el correcto entre ellos), y el inventado solo, abajo, sin mezclarse.

Lo demás que se midió, con un cliente de Gemini falso porque la clave es del negocio: se activa
la herramienta de búsqueda, `temperature` en 0 (con el valor por omisión inventaba más números),
la pista que escribe la persona viaja en el pedido, y las cuatro formas de fallar —sin clave,
respuesta sin JSON, cuota agotada, metadata con otra forma— devuelven un mensaje y no una
pantalla rota.

Dos detalles que salieron de probarlo:

- **El JSON viene envuelto en prosa.** Con la búsqueda activada el modelo ya no acepta que se le
  exija responder solo JSON: contesta el objeto adentro de una explicación, o de un bloque
  markdown, o las dos cosas. `_json_de_una_respuesta()` busca la primera llave y la última, que
  es lo único que sobrevive a las tres formas.
- **A veces devuelve un texto donde se pidió una lista.** Y un texto recorrido con `for` son sus
  letras sueltas: `"0280155786, 0280150830"` entraba como los códigos `0`, `2`, `8`, `1`, `5`,
  `7`. Se vio probándolo, y por eso `_lista_de_texto()` se aplica en los dos lados.

Y el paso 2 ahora avisa antes, no después: si el catálogo no tiene ni una foto, lo dice arriba
del botón en vez de dejar que alguien lo apriete y espere.

**Lo que esto NO es:** una confirmación. Es el punto de partida para buscar, no el número para
facturar. Que un código exista en tu catálogo no prueba que sea ESA pieza — hay repuestos que de
foto son idénticos y no son intercambiables.

## «Esta lista se cargó sin código de fábrica» — y no era cierto

Salió de correr el diagnóstico de salud sobre la base del negocio. Decía, en rojo:

> **1 lista no cruza con ninguna otra marca.** Ninguno de los productos de ILLINOIS está
> vinculado a otra marca… Casi siempre es que se importaron sin indicar la columna de código de
> fábrica (OEM).

Y la pantalla de «¿Cuánto cruza tu catálogo?» remataba: *«esta lista se cargó sin código de
fábrica, así que no tiene con qué cruzar»*, con un cartel rojo que decía **volvé a importarla**.

Los números reales de ILLINOIS son otros:

| | |
|---|---|
| Vínculos cargados | **0** ← por esto saltaba la alarma |
| Productos con vínculos **esperando revisión** | **2.367** |
| Códigos de fábrica que esa lista aportó | **2.397** |

No le faltaba la columna. Estaba todo encontrado y esperando que alguien entrara a aprobarlo.
El consejo de la app era reimportar una lista que estaba perfecta: una tarde de trabajo para
llegar exactamente al mismo lugar.

**Por qué mentía:** las dos funciones que dan ese diagnóstico miraban solo la tabla de
equivalencias CARGADAS. Cero cargadas y cero conclusiones posibles, así que caían en el último
motivo de la lista, que es el de la lista sin OEM. Ahora las dos consultan también la cola de
pendientes, y ese caso tiene su propio mensaje, su propio cartel y su propio destino
(**Estadísticas → 🔗 Equivalencias sugeridas**, no la pantalla de importar). El conteo de
«códigos de fábrica que aportó» también suma los pendientes: que nadie los haya aprobado todavía
no cambia lo que la lista trajo.

Ahora dice:

> **ILLINOIS: las equivalencias están encontradas y sin aprobar.** 2.367 producto(s) de esa
> lista ya tienen equivalencias esperando revisión… la lista está bien importada, lo que falta
> es revisarlas.

## El número interno de un proveedor no es el código de otro

La importación guarda el código con la marca pegada para que dos proveedores no se pisen
—`MAF126FISPA`, `LECS032LUCAS`, `FI-0280155786FISPA`— pero adentro de la descripción el
proveedor escribe el número pelado: «SENSOR DE MASA DE AIRE **MAF126** RENAULT MASTER 2 5».

Ese `MAF126` es su propio código, y volvía a entrar como si fuera una referencia cruzada. La
regla que descarta el código propio existía, pero solo en un sentido: sabía que `52031Ficha` es
`52031` con una palabra pegada, y no sabía que `MAF126` es `MAF126FISPA` sin la marca.

El daño es fino y por eso no se veía: **el número interno de un proveedor choca con el de otro**.

| lo que la app iba a proponer | lo que son en realidad |
|---|---|
| FISPA `MAF126` = Masser `MAF 126` | Renault Master ≠ Mercedes C280 |
| FISPA `MAF085` = Masser `MAF 085` | Mercedes ≠ VW Vento / Audi |
| FISPA `MAF054` = Masser `MAF 054` | Toyota Corolla ≠ Citroën C3 |

En la base real son **88 pares**, y mirados uno por uno los 88 están mal. Después del arreglo:
88 menos, **0 pares nuevos** (o sea que no se rompió nada de lo que sí encontraba).

El cuidado está en qué se considera «la marca pegada»: se exige que lo que sobra sea el nombre
de uno de los doce proveedores que se pegan al código, y no «cualquier letra». Si fuera
cualquier letra se perdería la diferencia entre `06A906265` y `06A906265E`, que son dos piezas
distintas de VW.

## Los dos puentes falsos que quedaban eran modelos de Mercedes

`puentes_sospechosos()` sobre la base del negocio devolvía exactamente dos, y los dos eran lo
mismo:

- **`CLS350`** unía una tapa de aceite, un sensor de fase y un cuerpo de aceleración.
- **`CLA250`** unía una sonda lambda, una brida de refrigeración y un sensor de ABS.

No son códigos: son modelos de Mercedes. Aparecen en cualquier descripción que nombre ese auto
—«TAPA ACEITE M.BENZ B200/C200/**CLS350**/E320/GL500/ML350»— y todo lo que el texto nombre junto
a ellos queda hermanado.

**Por qué no estaban cubiertos:** `CLS350` es tres letras y tres números, y esa forma la tienen
**2.558 códigos REALES** del catálogo — `IWP210`, `GWP065`, `ZSE161`. Un patrón general se los
llevaría puestos a todos. Así que las clases van listadas una por una, igual que los sufijos de
motorización (`308HDI`, `213CDI`): `CLS CLA CLK GLK GLC GLE GLA GLS SLK SLC SLS CL ML SL GL`,
con **tres dígitos exactos**. Medido: le pega a **14 códigos de los 70.888** del catálogo, y los
14 son modelos.

Los 14 ya estaban cargados, así que la regla sola no los borra — pero ahora la pantalla
**🧹 Limpiar vínculos → puentes que hoy no se generarían** los muestra (10 de los 14, los que
tienen dos o más productos colgando) y se borran de a uno.

Y una consecuencia que vale anotar: esto dejó desactualizado el ejemplo que usaba el filtro por
repetición, que decía «`CLA200` e `IWP065` tienen la misma forma y no hay expresión regular que
los distinga». Sigue siendo cierto en general —cambié el ejemplo a `CLC250`, que es otra clase
de Mercedes y **no** está en la lista—, y por eso ese filtro sigue siendo el que hace el trabajo
de fondo: una lista escrita a mano nunca va a estar completa.

**Sumando los dos arreglos del extractor de esta tanda:** 110 pares equivocados que dejan de
proponerse, y **0 pares que se pierdan** de los que sí encontraba.

## El código que el proveedor ya había escrito, y nadie volvía a leer

Buscar el código de fábrica adentro de la descripción ya existía, pero **solo en el momento de
importar**, detrás de una casilla que viene apagada. Si no se tildó —y no se tildó— ese dato no
se vuelve a mirar nunca: la descripción queda guardada con el número adentro y ahí muere.

Y aunque se tilde, igual hace falta correrlo después, por una razón de fondo: **el cruce solo
existe cuando están las dos listas**. Una descripción de FISPA que cita «REF ORIG 0258006980» no
vale nada hasta que se importa la lista que vende ese Bosch — y para entonces la importación de
FISPA pasó hace meses.

`equivalencias_escritas_en_las_descripciones()` recorre las 70.888 descripciones en **4
segundos** y propone **884 pares nuevos**. Corre sola después de cada importación (primera de
los cuatro pasos del descubrimiento, por ser la más barata y la más limpia) y tiene su botón en
Administrar → Mantenimiento.

**La decisión cara: solo toma los códigos DECLARADOS**, los que van después de `REF ORIG`, `//`,
`OEM` o `EQUIVALE`. Medido sobre la base real:

| | pares nuevos | entre familias distintas |
|---|---|---|
| Códigos **declarados** | 884 | **1,1 %** |
| Códigos adivinados | 2.154 | **8,7 %** |
| *(referencia)* los 24.774 vínculos que ya aprobaste a mano | — | **0,8 %** |

O sea que lo declarado nace casi tan limpio como lo que aprobó una persona, y lo adivinado nace
ocho veces más sucio. El motivo se ve mirando una descripción: en «SONDA LAMBDA **80045** AUDI
A3» el 80045 es el número interno de ESE proveedor —el mismo problema de la sección de arriba,
en su forma general—. Cuando el proveedor escribe «REF ORIG» ya no estamos adivinando: nos lo
están diciendo.

Una cosa chica que se arregló de paso: el par «un kit y la pieza que trae adentro» se descarta
ahora al BUSCAR y no solo al guardar. Sin eso la pantalla decía «8 pares nuevos», uno los
mandaba a la cola, no entraba ninguno, y a la corrida siguiente volvían a salir los mismos 8
para siempre. Se vio corriendo el barrido dos veces seguidas: ahora la segunda corrida da 0.

## El «<» de «Master 98<» se comía la mitad de la descripción

Salió de la segunda tanda de la revisión externa, que lo marcaba como un agujero de seguridad.
Lo es, pero lo que se encontró midiendo contra la base del negocio es peor y más cotidiano: un
bug de pantalla que estaba pasando **hoy, en 1.435 productos**.

Los proveedores usan el signo `<` para decir «hasta tal año». Así vienen las descripciones de
FISPA:

    INTERRUPTOR DE STOP 31028 MITSUBISHI Colt III RENAULT Clio 2 - Kangoo -
    Laguna 01< - Master 98< - Megane 00-03 - Todos Cuadripolar RENAULT
    Trafic 00< - Twingo 96<REF ORIG RENAULT - 93852863 - NISSAN 4404452 ...

Mirá el final: `96<REF`. Cuando lo que sigue al `<` es una letra, el navegador no lee «menor
que»: lee el principio de una etiqueta HTML y se traga todo hasta encontrar un `>`. Como no hay
ninguno, **se come el resto del renglón**. En la pantalla de auditoría —donde uno mira
justamente para decidir si una equivalencia está bien— la descripción terminaba en «Twingo 96»
y desaparecían los códigos originales de Renault, Nissan y Mitsubishi.

Medido sobre los 70.888 productos: **1.435 descripciones afectadas, 265.805 caracteres que no
llegaban a la pantalla**. Después del arreglo, cero.

Pasaba solo en las tres listas que usan `unsafe_allow_html=True`, que lo necesitan para el
`<small>` del segundo renglón. Ahora el texto que sale de la base pasa por `texto_para_html()`
antes de entrar ahí. De paso cierra la puerta que marcaba la revisión: una descripción importada
de un Excel ajeno que traiga `<script>` se dibujaba como código de verdad.

**Los códigos no se escapan** y es a propósito: van entre acentos graves, y adentro de un bloque
de código markdown ya se escriben literales. Escapándolos se vería `Tow&amp;Country-300M` en vez
de `Tow&Country-300M`, que es un código real de la base.

## Una firma de foto podía ser un programa

Las firmas visuales de las fotos se guardan con `pickle`, y `pickle` **no es un formato de
datos: es una receta de construcción**. Al leerlo puede fabricar cualquier objeto de cualquier
módulo instalado, `os.system` incluido.

Por sí solo eso no sería un problema —las escribe la propia app— salvo por una puerta que
existe y se usa: **📊 Estadísticas → ♻️ Restaurar backup reemplaza la base entera con un `.db`
que sube una persona**. O sea que el contenido de `firma_blob` no siempre lo escribió esta app.
Con un archivo preparado a mano, el código de adentro corre en el servidor apenas alguien entra
a buscar por foto.

Está comprobado, no deducido: con `pickle.loads` pelado el «exploit» de prueba creó su archivo;
con el lector nuevo no se creó nada y saltó `UnpicklingError: Una firma visual no puede contener
posix.system`.

`leer_firma_visual()` solo sabe armar arrays de numpy (la lista está en
`FIRMAS_CLASES_PERMITIDAS`, con los dos nombres del módulo interno porque numpy 2 lo renombró de
`numpy.core` a `numpy._core` y las firmas viejas se siguen leyendo). Un blob raro ya no llega a
construirse: se corta y la foto queda marcada como ilegible, que es lo mismo que ya pasaba con
una firma corrupta. Probado con el formato nuevo, con el viejo (el array de descriptores pelado)
y con el payload malicioso.

El auditor tiene ahora dos chequeos más —el 28 y el 29— para que ninguno de los dos arreglos se
pueda deshacer sin que salte. Los dos se verificaron rompiendo el código a propósito.

### Lo que esa revisión marcaba y acá no aplica

Otra vez, para no volver a discutirlo — cada uno se fue a mirar contra el código y contra la
base real:

- **`VACUUM` después de borrar.** `PRAGMA freelist_count` sobre la base del negocio da **0**:
  9.159 páginas ocupadas, ninguna desperdiciada. No hay nada que compactar. El único `VACUUM`
  que hace falta ya está, en `generar_backup_sin_fotos()`, para que el archivo pese menos.
- **Path traversal con el nombre del archivo subido.** El nombre de un archivo subido se guarda
  como texto en la base y nunca se usa para armar una ruta. El único `os.path.join` con variable
  de toda la app arma `backup_sin_fotos.db` en el directorio temporal.
- **Inyección SQL.** Hay 43 consultas armadas con f-string. Ninguna mete texto del usuario: son
  marcadores `?` repetidos (`en_tandas()`), listas de columnas fijas, o nombres de tabla que
  vienen de tuplas escritas en el código. Los nombres de columna de `restaurar_papelera()` salen
  del JSON que escribió la propia app con `dict(row)` de una tabla real.
- **`st.exception` mostrando el rastro del error al usuario.** No se usa en ninguna parte.
- **`maxUploadSize`.** No hay `.streamlit/config.toml`, así que rige el límite por defecto de
  Streamlit: 200 MB. La base entera con fotos pesa hoy 37,5 MB, y el backup que se sube al
  repositorio va sin fotos justamente para que entre en GitHub. Queda anotado por si algún día
  la base pasa los 200 MB; hoy no hay nada que arreglar.

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
  de las descripciones reales. Por eso `marcas_vehiculo_en()` devuelve **todas**, cada una con
  su pedazo de texto (hasta la marca siguiente), y el producto aparece en el catálogo de cada
  una. Hubo una función que devolvía solo la primera y ya no está: cada vez que se usaba, el
  repuesto desaparecía del catálogo de los otros autos y el modelo se leía del pedazo
  equivocado.
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

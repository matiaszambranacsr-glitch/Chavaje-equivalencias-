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

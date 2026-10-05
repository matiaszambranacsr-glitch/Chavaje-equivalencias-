# Chavaje — buscador de equivalencias de repuestos

Una app de mostrador: buscás el código que te pide el cliente y te dice qué otros códigos, de
qué proveedores, son el mismo repuesto. Corre con Streamlit sobre una base SQLite.

## Qué es cada archivo

| archivo | qué es |
|---|---|
| `app.py` | Lo que Streamlit corre en cada toque: la configuración de la página, el encabezado, la entrada y la navegación. Arranca con el mapa de todas las secciones de la app. |
| `logica/` | Todo lo que no es una pantalla: la base, los códigos, las equivalencias, las copias, los proveedores. 17 archivos. Se carga **una vez** por proceso. |
| `pantallas/` | Una pantalla por archivo (buscador, administrar, estadísticas...). Corren en cada toque, al final de `app.py`. |
| `orden.py` | En qué orden corren las partes de `logica/` y las pantallas. Lo leen la app y las herramientas. |
| `nucleo/` | La misma lógica pero **sin Streamlit**, para poder usarla desde otro sistema. Se genera desde `logica/`. |
| `auditar.py` | Revisa la app entera y busca los errores que ya pasaron alguna vez. Correlo antes de subir un cambio. |
| `pruebas_de_la_revision.py` | Que el análisis de equivalencias no se equivoque con pares ya revisados a mano, y (con `--base`) que no baje a rojo lo que aprobaste. |
| `requirements.txt` | Lo que hay que instalar. |
| `Equivalencias` | El prototipo original, de antes de `app.py`. No lo usa nadie; queda por si querés mirarlo. Se puede borrar. |

## Antes de subir un cambio

```bash
python3 auditar.py               # tiene que dar ERROR 0 (revisa la app entera)
python3 nucleo/generar.py        # regenerar el paquete desde logica/
python3 -m nucleo.pruebas        # tiene que decir "todo en verde"
python3 pruebas_de_la_revision.py   # si tocaste el análisis: "todo en verde"
python3 pruebas_de_la_revision.py --base copia.db   # y contra tus aprobaciones
python3 revisar_con_gemini.py    # opcional: una segunda opinión sobre el diff
```

Uno por uno y mirando la salida de cada uno. Encadenarlos con `&&` y quedarse con lo último
que imprime la consola ya dejó pasar un paquete `nucleo` roto: el `&&` se enganchó de un `head`
que terminó bien y el fallo de las pruebas no se vio.

El auditor no es un linter genérico: cada control salió de un error que rompió la app de
verdad, y el mensaje cuenta cuál fue. Si marca algo, conviene leerlo antes de descartarlo.

El último es de otra clase y no bloquea nada: ver *Una segunda opinión, de otro modelo*.

## Cómo encontrar las cosas

La app son 30.900 líneas repartidas en `app.py`, `logica/` y `pantallas/` (ver *La app
partida en archivos*). Cada archivo está dividido en secciones con un encabezado de tres
líneas:

```
# ============================================
# NOMBRE DE LA SECCIÓN
# ============================================
```

Buscando `# ===` se salta de una a otra. El índice completo, archivo por archivo, está en el
docstring del principio de `app.py`, y el auditor avisa si ese índice y las secciones dejan de
coincidir.

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

## La computadora del mostrador, y lo que la app se tragaba

**La caja de búsqueda en la computadora.** La mitad del equipo va a usar la app desde una
computadora, y hasta acá se había acomodado el celular. En una de 1366x768, un empleado veía
arriba de la caja de búsqueda los 7 avisos de salud abiertos, cada uno con su explicación y su
botón, y el cartel de «12.747 equivalencias esperando aprobación». Son tareas de
administración: «Ir a arreglarlo» le pide la clave, y aprobar no puede. Ahora, para quien no es
administrador, los avisos van plegados en una línea (como en el celular) y la guía y el cartel
van al final de la página. El administrador en la computadora los sigue viendo abiertos arriba,
que es quien los arregla.

| computadora 1366x768, empleado | antes | ahora |
|---|---|---|
| dónde está la caja de búsqueda | a 1.646 px (tercera pantalla) | **a 663 px (se ve al entrar)** |

**Lo que la app se traga.** La app anota en memoria los errores que decide ignorar (hay 142
lugares así). Corriendo los dos barridos en un mismo proceso y leyendo ese registro al final
aparecieron 148 «no such column: espesor» en el análisis de sugeridas. Era de la prueba: el
barrido cambia el archivo de la base entre sesiones y la lógica, que ahora se carga una vez,
seguía con las columnas de la base anterior. En la app de verdad la base solo se cambia con
`restaurar_backup()`, que corre las migraciones y limpia ese caché. Con el barrido arreglado
(cada base nueva limpia los cachés, como un servidor nuevo) quedan 2 errores, los dos de
internet: las consultas del dólar y la inflación, bloqueadas desde el entorno de prueba. Esas
ya tienen 4 s de tope y no reintentan por 30 minutos si fallan.

**Probado y sin cambios:** cada búsqueda cuesta 0,2 s de procesador y tarda 0,5 s. Entrar a la
app cuesta 0,4 s de procesador (1,4 s al principio de estas rondas). Lo que queda es de
Streamlit: servirle los archivos de la página a cada navegador nuevo (un celular de verdad los
guarda de una visita a la otra) y, una vez por arranque, cargar la librería de gráficos. El
análisis de sugeridas ocupa unos 25 MB por persona que lo abre; como lo abre quien revisa, no
quien atiende, no hace falta compartirlo.

## Escribir a la vez: importaciones, stock y confirmaciones

**Importar mientras los demás trabajan.** 8 personas en el celular buscando y tocando «Se
llevó» y «Pedir» sin parar, y en el medio se importa IMPERIAL (43.303 filas nuevas), contra un
servidor de un procesador:

| 8 personas escribiendo | sin importar | importando IMPERIAL |
|---|---|---|
| escrituras | 128 | 409 |
| mediana / peor | 0,74 s / 1,9 s | 0,89 s / 4,5 s |
| errores, «database is locked» | 0 | 0 |

No hubo que tocar nada: la importación confirma fila por fila (autocommit), así que los demás
entran entre fila y fila, y lo que sí es largo va con `BEGIN IMMEDIATE` y 8 s de espera.

**El stock que se pisaba.** «✏️ Editar precio, costo y stock» escribía siempre el stock que
mostraba la pantalla al dibujarse, aunque solo se cambiara el precio. Uno abre el editor con
stock 10, otro cierra una venta de 2 (queda 8), el primero guarda el precio y el stock vuelve a
10. `actualizar_precio_stock()` recibe ahora lo que la pantalla mostraba: si el stock no se
cambió, no se escribe; si se cambió pero en la base ya no está lo que se mostraba, tampoco, y
avisa cuánto hay ahora. Probado con las dos versiones:

| caso | antes | ahora |
|---|---|---|
| A cambia solo el precio mientras B vende 2 | stock 10 (se perdió la venta) | **8** |
| A corrige el stock a 20 mientras B vende 1 | 20 (se pisó la venta) | **7, y avisa** |
| A corrige el stock sin que nadie más toque | 15 | 15 |

Los demás cambios de stock (cerrar una reserva, cargar un remito) ya suman o restan sobre lo
que hay, y no tienen este problema.

**Las confirmaciones que no aparecían.** Contando toques contra filas en la base, no se perdió
ninguna venta ni ningún pedido: 83 «Se llevó», 83 ventas. Pero 1 de cada 4 veces no aparecía el
aviso. Siguiendo la pantalla cada 50 ms: si el aviso flotante anterior seguía visible (duran
4 s), el nuevo no aparecía nunca. «Se llevó» y enseguida «Pedir», que es lo normal, mostraba
solo el primero, y eso invita a tocar «Pedir» de nuevo (cada toque suma a «veces pedido»).
Ahora la confirmación va **abajo de los botones**, donde se está mirando, y queda hasta el
próximo toque (`mostrar_lo_anotado()`). Con 8 personas a la vez: 0 de 178 sin confirmación.

## La app partida en archivos

`app.py` tenía 30.800 líneas. Ahora:

- **`logica/`**: las 55 secciones de funciones y datos, en 17 archivos por tema. Se cargan
  **una vez por proceso**, todas en un mismo espacio de nombres, en el orden de `orden.py`.
- **`pantallas/`**: las 8 pantallas, una por archivo. Corren en cada toque, en el mismo lugar
  del flujo en que estaban, y se compilan una vez por cambio.
- **`app.py`**: la configuración de la página, el encabezado, la entrada, la navegación y la
  vuelta que ejecuta las pantallas.

**Por qué un solo espacio de nombres y no módulos que se importan entre sí.** Son 566 funciones
que se llaman por su nombre, sin prefijo, porque nacieron en un archivo. Como módulos habría
que escribir cientos de imports cruzados, y con importaciones circulares el orden de carga
decide qué nombre existe: un error que aparece recién al tocar el botón que usa esa función.
Así, todo se sigue viendo como antes.

**Cómo se controló que no se rompiera nada:**
- La partición la hizo un programa, cortando en los encabezados de sección: cada una de las
  30.806 líneas del original quedó **exactamente en un lugar**, ninguna perdida ni repetida.
- Antes de cortar se analizó con `symtable` qué usa cada función. Una sola cosa de la lógica
  dependía de la pantalla (`GRUPOS_MANTENIMIENTO` y `HERRAMIENTAS_MANTENIMIENTO`, que usa el
  buscador de herramientas): se mudó a `logica/`. Nada de lo que corre al cargar la lógica
  depende de quién está usando la app. Y nada usaba la «magia» de Streamlit (mostrar una
  variable suelta), que solo funciona en el archivo principal.
- `auditar.py` revisa la app entera: arma las tres partes en el orden en que corren y dice
  `archivo:línea`. Tiene un control nuevo, el 40: una función de `logica/` que use un nombre
  que solo existe en una pantalla (daría `NameError` al llamarla). Probado metiendo uno a
  propósito: lo encuentra y dice dónde.
- `nucleo/generar.py` lee la app partida y genera **exactamente los mismos archivos** que antes.
- Los dos barridos (31 y 17 combinaciones de pantalla y usuario), las 19 pantallas en un iPhone
  simulado, la revisión por tandas, las diez pruebas de la copia a GitHub y la de dos personas
  decidiendo el mismo vínculo dan lo mismo que antes de partir.

**Un cambio de código se toma sin reiniciar.** Las pantallas se recompilan solas si cambió el
archivo. La lógica no alcanzaba con el vigilante de archivos de Streamlit: se probó cambiando
un texto con el servidor andando, y la lógica seguía vieja. Cada sesión abierta tiene su propio
vigilante, y solo las que estaban conectadas en el momento del cambio tiran la versión vieja.
Una sesión nueva, o cualquiera si al subir un cambio no había nadie adentro, seguía con la
lógica vieja hasta reiniciar. Ahora `app.py` mira en cada toque las fechas de los archivos de
la lógica (19 consultas al disco, microsegundos) y, si alguno cambió, la vuelve a cargar.
Probado: los dos cambios se ven en el toque siguiente. Probándolo apareció otro caso: un
`app.py` nuevo con una lógica cargada antes de que existiera esa función. También se recarga.

**Con 15 personas a la vez** (misma prueba que *15 personas a la vez*, dos rondas cada una):

| | un archivo | partida |
|---|---|---|
| procesador del servidor | 19,4 y 21,4 s | **16,8 y 16,0 s** |
| memoria, pico | 378 y 331 MB | **285 y 282 MB** |
| errores | 0 | 0 |

Es lo que se esperaba: antes, en cada toque de cada persona se volvían a definir 566 funciones
y se rearmaba cada `@st.cache_data`. Ahora eso pasa una vez. Los tiempos de espera no se mueven
de forma clara: entrar con 15 personas llegando juntas sigue siendo una cola sobre un solo
procesador.

## Revisar sugeridas por tandas, y dos personas decidiendo el mismo vínculo

**Por tandas.** En «Equivalencias sugeridas», cada «Los N están bien» se aplicaba al tocarlo,
y cada aplicación rehace el análisis del lote entero: 5 a 8 s en BARRIDO. Revisar todo son unas
50 decisiones. Rehacer el análisis no se puede evitar (decidir unos pares cambia el puntaje de
otros, medido más abajo), pero sí hacerlo una vez por tanda. Ahora cada grupo tiene un selector
«— / ✅ Están bien / 🚫 Descartar», y adentro de «Ver uno por uno», uno por vínculo. Un botón
«💾 Aplicar lo marcado: ✅ N bien · 🚫 M a descartar», arriba y abajo de los grupos, aplica todo.
Lo marcado se guarda **por par** y no por grupo: el mismo motivo sigue en la página siguiente, y
atado al grupo lo decidido en la página 1 se hubiera aplicado a los de la 2. Con «➡️ Página
siguiente» se pasa de página sin subir hasta el número.

Probado en un iPhone simulado: grupo de la página 1 a descartar, un vínculo de ese grupo
cambiado a bien, grupo de la página 2 a bien, vuelta a la página 1 (sigue todo marcado). Un
solo «Aplicar»: 11 aprobados, 9 descartados, 20 pendientes menos, **una espera de 5,6 s** en
vez de tres.

**Dos personas, el mismo vínculo.** `aprobar_pendientes()` con una lista de pares creaba la
equivalencia para todos los pares de la lista, sin mirar si seguían en la cola. Con varias
personas revisando a la vez:

| | antes | ahora |
|---|---|---|
| A descarta un vínculo; B, con la pantalla vieja, lo aprueba | **queda cargado** | queda descartado |
| A aprueba uno; B, tarde, lo descarta | sigue cargado, pero **anotado como rechazado** | sigue cargado, sin anotar nada |
| aprobar los 8.185 limpios de BARRIDO | 7,1 s | **3,5 s** |

Ahora las dos solo deciden sobre lo que sigue esperando (`_los_que_siguen_pendientes()`), y el
aviso dice cuántos ya había resuelto otra persona. Aprobar los limpios tarda la mitad porque la
pantalla manda cada par en las dos direcciones y se procesaban dos veces (y el número que
devolvía era el doble).

## 15 personas a la vez

La app la van a usar 10 a 15 personas a la vez, la mitad desde la computadora y la mitad
desde el celular. Hasta acá todo se había probado de a una. `carga.py` (en las herramientas de
prueba) abre N navegadores al mismo tiempo, mitad computadora y mitad iPhone, cada uno entra
con su nombre, busca 5 códigos reales y cambia de pantalla. El servidor corre en **un solo
procesador** (`taskset`), como el de Streamlit gratis.

Con una persona: entrar 3,6 s, buscar 0,6 s. Con 15 llegando juntas, antes:

| 15 a la vez, un procesador | antes | ahora |
|---|---|---|
| procesador que gasta el servidor | 34,9 s | **21,1 s** |
| entrar, mediana / peor | 16,0 s / 26,8 s | 12,9 s / 18,9 s |
| buscar, mediana / peor | 0,7 s / 4,9 s | 0,8 s / 2,3 s |
| memoria, pico | 365 MB | 365 MB |
| errores | 0 | 0 |

Lo que se encontró muestreando el servidor con `py-spy` mientras entraban:

- **El chequeo de salud se calculaba una vez por persona.** Estaba en la sesión de cada uno,
  pero da lo mismo para todos: no mira quién pregunta. Era el 40% del procesador al entrar.
  Ahora `salud_compartida()` lo calcula la primera persona; las que llegan mientras tanto
  esperan ese resultado, y las siguientes lo reciben hecho por tres minutos o hasta que alguien
  cambie algo, como antes.
- **Streamlit corría el recolector de basura completo después de cada toque de cada persona**
  (`runner.postScriptGC`). Era la cuarta parte del procesador. Se apagó en
  `.streamlit/config.toml`. La memoria se midió en tres rondas seguidas de 15 personas, con y
  sin: 321 y 316 MB en uso al final, casi igual. Python lo corre solo cuando hace falta.

Lo que queda, y por qué no se tocó todavía:

- **22%: el vigilante de archivos de Streamlit.** Después de cada toque recorre todos los
  módulos cargados. Se puede apagar, pero es lo que usa Streamlit Cloud para tomar el código
  nuevo cuando se sube un cambio, y eso no se puede probar desde acá.
- **10%: rearmar las funciones guardadas (`@st.cache_data`) en cada toque.** Streamlit vuelve
  a ejecutar el archivo entero, y cada vez les calcula la huella leyendo su código. Se va a
  resolver partiendo la app en módulos que se importan una sola vez.

«Entrar» sigue siendo lo más lento cuando llegan todos juntos: 15 personas en tres segundos es
una cola sobre un solo procesador. Espaciadas, como se llega a un negocio, cada una tarda lo
que tardaría sola.

## Lo que se perdía en cada toque, un control para que no vuelva, y detalles de pantalla

**Las sesiones con los proveedores.** `_SESIONES_DE_CATALOGO` y `_SESIONES_PORTAL` guardaban
la sesión ya logueada para no entrar al sitio del proveedor en cada ficha. Pero eran
diccionarios del archivo, y Streamlit los vacía en cada toque (lo mismo que pasaba con el
candado de la tanda de fondo). Medido contra un proveedor de mentira que cuenta los ingresos:
**3 logins en 3 toques** antes; ahora 1. La del catálogo ya sabía descartar una sesión vencida.
La del portal no, y el vaciado de cada toque la renovaba sin querer: ahora se renueva a
propósito, a la hora.

**Control 39 en `auditar.py`.** Marca todo candado creado al nivel del archivo, y todo
diccionario o lista que alguna función modifica, salvo que el comentario de arriba diga que
es «de cada pasada» a propósito. Pasado por el código de antes de estas dos tandas, encuentra
exactamente los siete casos: los seis arreglados y `db_lock`, que quedó así con el porqué al
lado. Sobre el de hoy encontró uno más, `_MODELOS_CACHE`. Se midió y quedó como estaba: armar
la lista de modelos cuesta 60 ms (la primera medición dio 828 ms, pero contaba la apertura de
la conexión), y rearmarla en cada toque hace que una lista de aplicaciones recién importada
entre sin avisarle a nadie.

**Probado y descartado: no rehacer el análisis de sugeridas después de cada decisión.** El
análisis de BARRIDO tarda 5 a 8 s y se rehace entero después de cada «Los N están bien» o
«Descartar los N». La idea era sacar del análisis guardado solo los pares decididos. Se probó
con los datos reales, decidiendo grupos y comparando par por par contra el análisis completo:
decidir unos cambia el puntaje de otros (en BARRIDO, 51 de los 101 que quedan pasan de 50 a 65 y
dejan de ser sospechosos; en ILLINOIS aparecen 79 que el atajo no mostraría). Con el atajo se
vería información vieja, así que se rehace. Tampoco hay un punto caro que atacar: el tiempo está
repartido en muchas partes chicas del motor que puntúa, y tocarlo por uno o dos segundos no vale
el riesgo.

**En pantalla:**
- En «Para pedir», lo que marcaron los empleados con «📌 Pedir» (y los favoritos con poco
  stock y el mensaje para el proveedor) va arriba, pegado a «lo que se va a acabar». Estaba al
  final, casi cinco pantallas abajo en el celular.
- Estando en Mantenimiento se veían dos buscadores de herramientas seguidos, el de Administrar
  y el de adentro. El de arriba ahora aparece solo en las otras sub-secciones.
- Textos en inglés: las cajas de subir archivos decían «Upload» y «200MB per file» (en cinco
  pantallas) y un selector «Choose options». Ahora dicen «Elegir archivo», «Hasta 200 MB por
  archivo» y «Elegí uno o más». Se encontraron recorriendo las 19 pantallas y juntando lo que se
  ve en inglés, no lo que dice el código: «Choose an option» aparecía en todas, pero es el texto
  de fondo de un campo que ya tiene valor y no se ve.

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

La dirección es `https://equivalenciasdelchavo.streamlit.app/`. Estuvo en pausa un tiempo
porque tenía otra (`elchavo.streamlit.app`), y Streamlit contestaba «You do not have access to
this app or it does not exist» —que es lo mismo que contesta para una app privada—. Si algún
día cambia, se cambia sin tocar código, en la variable `URL_DE_LA_APP` del repositorio.

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

## Motores leídos como códigos, juntas de otro auto y rubros heredados

Tres cosas que se vieron en capturas del uso real, las tres en las equivalencias.

### 1. «F6L913», «OHC181» y «STAND.5» no son códigos de fábrica

Al importar la lista de IMPERIAL con «buscar códigos originales en la descripción», la vista
previa ofrecía como códigos de fábrica cosas como `F6L913` y `BF6L913` (de «DEUTZ
F6L913/BF6L913»), `OHC181` (de «RENAULT TORNADO 4BANC./OHC181/»), `FA6L714` o `STAND.5` (de
«LLAVE FIJA T STAND.5 mm»). Son designaciones de motor y medidas: si entran como códigos,
unen productos que no tienen nada que ver.

En `formas_solo_texto` (logica/codigos.py) entraron las formas de las designaciones de motor
de Deutz, Perkins, Isuzu, Renault, Iveco, Indenor y Scania, más OHC/OHV, «MOT.», los rangos de
años («1500-1800»), «16V-307» y «PALABRA.5». Cada una se midió contra los códigos reales de
proveedor que hay en la base y contra los puentes buenos: **ninguna toca un código real**
(`04283299`, `T-36042` y `LKS026` se siguen tomando). Con la lista de IMPERIAL, los puentes
hacia otras listas bajaron de 16 a 5, y los 5 que quedan son números de verdad.

La vista previa, además, ahora aplica el mismo filtro que la importación («el mismo número
repetido en muchas filas es un motor, no una pieza»), así que muestra lo que de verdad va a
entrar.

### 2. La misma junta de otro auto

La junta de tapa de cilindros de la S10/Trail Blazer salía con 90 puntos contra la del Corsa, y
con 100 contra la de un Isuzu. Las dos «coincidían» en todo lo que se miraba: el rubro, la
palabra CHEVROLET y el espesor. Tres arreglos:

- **La marca sola no alcanza.** Si las dos descripciones nombran modelos y no comparten
  ninguno —y ninguna nombra al de la otra, ni comparten un código de motor—, son autos
  distintos. Solo cuando las dos son específicas (tres modelos o menos): una lista larga de un
  sensor que va en veinte autos no se contradice por anotar otros veinte.
- **Un modelo compartido tampoco, si las marcas no coinciden.** «S10-TRAIL Blazer» y «Nissan
  X-TRAIL» compartían TRAIL. Las marcas que comparten motores y plataformas (GM con Chevrolet
  y Opel, Peugeot con Citroën, Fiat con Chrysler e Iveco, el grupo Volkswagen, Renault con
  Nissan...) cuentan como la misma, y las que hacen motores para las demás (MWM, Cummins,
  Perkins...) no contradicen nunca.
- **El espesor solo no prueba nada.** Separa las tres variantes de una misma junta, pero dos
  juntas de motores distintos pueden medir 1,10 las dos. Ahora las medidas cuentan como prueba
  a favor solo si hay alguna que identifique la pieza (un diámetro, un largo). El espesor suma
  cuando las descripciones ya dijeron que es la misma junta del mismo auto: ahí confirma que es
  la misma variante.

Lo que el texto **contradice** —autos, marcas o modelos distintos— ahora tumba el par, igual
que las medidas que no coinciden. Antes solo dejaba de sumar, y con «mismo rubro» y «precio
parecido» el par llegaba igual a 75 y se aprobaba solo. No aplica cuando el par está unido por
un número (un código de fábrica, o el código de uno escrito en la descripción del otro): ahí la
pieza la dice el número, y que cada lista anote autos distintos es lo normal.

Medido sobre la cola real (12.747 vínculos): **356 pasan de «limpios» a «para revisar»**; en
las muestras revisadas eran juntas de otro motor, sensores de otra marca, la S10 contra la
X-Trail. La junta que sí es la de la S10 1,30 mm (TC-804-11 3M) sigue aprobada.

### 3. El rubro de un código de fábrica es el de los que lo citan

El producto de un código de fábrica copia la descripción de la **primera** fila que lo nombró.
El 2H0919050B es la bomba de combustible de la Amarok, pero la primera fila que lo citó fue el
filtro de esa bomba («FILTRO BOMBA DE COMBUSTIBLE ... REF ORIG 2H0919050B»), así que el código
quedó como «Filtros» y las dos bombas que lo citan salían con **0/100 y «Son de rubros
distintos»**.

Ahora el rubro de cada código de fábrica sale de la mayoría de los productos unidos a él (al
menos dos, y más de la mitad), en los vínculos cargados y en los pendientes. Con eso, las dos
bombas pasan de 30 a 85. Contra la fila de la que el código sacó su descripción no se aplica:
ahí los dos lados son el mismo texto. Se usa en la revisión de pendientes, en la auditoría de
vínculos cargados y en el recálculo de confianzas (por eso `VERSION_CONFIANZA` pasó a «4»: los
puntajes guardados se recalculan solos). En la cola real, 37 reguladores de presión que
estaban «para revisar» pasan a limpios, y ninguno limpio cae.

## Medido sobre la base de verdad: la cola de 30.234

Con la copia de seguridad en GitHub se pudo, por primera vez, medir sobre la base que se usa
en el negocio y no sobre una copia vieja: 87.155 productos, **5 equivalencias aprobadas y
30.234 esperando revisión**. Salieron dos cosas.

### Las listas que nunca marcan el código de fábrica

De los 1.861 pares entre IMPERIAL y un «código de fábrica», el extractor de ese momento
volvía a sacar 1.727, y casi todos eran medidas, motores o herramientas: `85x105x`,
`ESTR.32MM`, `220V-50HZ`, `RANGER3L`, `206-TU5`, `HEXAG.17MM`, `Chev.S10`.

No hay regla de forma que los separe de los códigos reales: medido contra los 71.659 códigos
que los proveedores escriben en su propia columna, los reales también tienen puntos,
minúsculas o una «x» entre números. Lo que sí los separa es **la lista**:

| Lista | Filas que marcan el código («REF ORIG», «Nº», «//») |
|---|---|
| FISPA | 67 % |
| ILLINOIS | 9 % |
| IMPERIAL | 2 de 43.101 |
| TARANTO, JL, CRI-FA | ninguna |

En una lista que marca el código de fábrica, lo que no marcó también suele serlo: el tercer
número de «REF ORIG 6G91-7A095-AD - 0792231 - LR00291», o el que ILLINOIS pone entre
paréntesis al final. En una lista que no lo marca nunca, lo que parece un código es otra cosa.

Ahora, al importar con «buscar el código de fábrica en la descripción», si la lista marca el
código en menos del 2 % de las filas (`la_lista_declara_codigos()`), se toman solo los
marcados y los que ya son el código de otra lista. Sobre las listas reales: IMPERIAL pasa de
1.731 códigos a 2 (los dos «Nº ORIG» de verdad), TARANTO de 304 a 1, JL y CRI-FA a 0, y FISPA
e ILLINOIS no cambian. No se pierde la búsqueda: si nadie tiene ese número, el buscador lo
encuentra en la descripción.

Para lo que ya estaba cargado, en Mantenimiento → 🧹 Limpiar y corregir está **🧽 Códigos
adivinados que no unen nada**: los que cuelgan de una sola lista que no marca códigos, están
escritos sin marcar en la descripción, no son el código de otro proveedor y no tienen nada
aprobado. En la base real son 1.450 códigos y **1.911 pares menos en la cola**; borrarlos
tarda 3 segundos y no toca ningún producto.

### «Lo normal entre estas dos listas» estaba mal medido

Para no marcar como raro un precio que es distinto solo porque una lista está en otra escala
(una desactualizada, otra sin IVA), la app compara contra lo típico entre las dos listas. Eso
se medía con la mediana de TODOS los precios de cada lista, y eso mezcla cuánto cobra la lista
con qué vende. Medido con los pares que las unen:

| Listas | La misma pieza, de verdad | Lo que se suponía |
|---|---|---|
| FISPA / JL | 1,06 veces | 8,6 |
| IMPERIAL / JL | 0,71 | 5,3 |
| ILLINOIS / IMPERIAL | 2,3 | 0,72 |

Así, 262 pares con el mismo precio salían «se diferencian 1 vez, y lo normal es 9» y se iban a
revisión. Ahora la escala sale de los pares mismos (aprobados, pendientes y los que comparten
código de fábrica): la mediana de la razón de precios por cada par de listas, y una escala por
lista que las explica a todas juntas. Además se mira **para qué lado** va la diferencia: si A
suele ser 10 veces más cara que B y en un par sale 10 veces más barata, ese par se aparta 100
veces de lo normal, y antes pasaba como normal.

Sobre la cola real, 455 pares pasan a limpios (la misma junta de base de carburador del
Regatta, la misma tapa de cilindros del Volvo N12, frenadas por un precio que era la escala de
la lista) y 345 pasan a revisión (juego completo de motor contra una junta de tapa de
válvulas, tapa de cilindros contra tapa de válvulas: el precio ahora sí lo delata).

### Las abreviaturas de IMPERIAL y el juego contra la junta suelta

Dos cosas más que mostró la cola real, las dos en la comparación de descripciones:

- **«JTA T.V.», «JTA T.C.», «M.ESC.», «A.LEVA».** IMPERIAL abrevia con una letra y un punto:
  «T.C.» (tapa de cilindros) aparece 1.072 veces, «T.V.» (tapa de válvulas) 267. La letra sola
  se tiraba por corta, así que «JTA T.V. DODGE 1500» quedaba como «JUNTA» a secas y se
  emparejaba con cualquier junta del mismo auto. Ahora se expanden antes de comparar (ver
  `_ABREVIATURAS_CON_PUNTO`), con las que se contaron en su lista. En la cola real: 28 pares
  dejan de aprobarse solos (juntas de admisión de Monza contra Corsa, que pasaban porque «ADM»
  contaba como una palabra del auto).
- **El juego de juntas del motor contra una junta suelta.** «Jgo.Jtas.P/Motor FORD FALCON» y
  «JTA T.C. FORD FALCON» son del mismo rubro y del mismo auto, y no son lo mismo: la junta viene
  adentro del juego. Ahora se distingue qué juego de motor es —completo, superior
  (descarbonización), inferior, completo sin tapa de cilindros— y si uno lo es y el otro no, o
  son de tipos distintos, son productos distintos (ver `tipo_de_juego_de_motor()`). No se cortan
  los juegos que no son de motor: «Juego de juntas para Carburador» contra «JUNTAS FIAT 128
  WEBER» sigue siendo el mismo juego. En la cola real: 250 pares dejan de aprobarse solos.

## Aprobar por grupos con una muestra de control, y rechazos que enseñan

En la base real había 5 equivalencias aprobadas y 23.001 «limpias» esperando. «Limpia» quiere
decir que el análisis no encontró nada en contra, no que esté bien, y la única salida que tenía
la pantalla era aprobarlas todas a ciegas. Ahora, en Estadísticas → 🔗 Equivalencias sugeridas:

**🎯 Aprobar las limpias por grupos, con una muestra de control.** Un grupo son las limpias
entre dos listas (ILLINOIS ↔ TARANTO, CRI-FA ↔ FISPA...), porque los errores se parecen dentro
de un par de listas y cambian entre uno y otro. De cada grupo la app sortea una muestra —30, 50
u 80 pares según el tamaño— y la guarda en la base (`muestras_de_control`): es siempre la
misma, aunque se recargue o la revise otra persona, así que no se puede «revisar hasta que
salga limpia». Se marcan de a 10 en un formulario, sin recargar la pantalla con cada toque.
Con la muestra completa, la app dice cuántos errores se pueden esperar en el resto (el límite
de arriba del intervalo de Wilson al 95%: con 0 errores en 80, menos de 5%) y:

- con 0 errores, ofrece aprobar el resto del grupo de un toque;
- con 1, lo ofrece igual, o mirar 30 más;
- con 2 o más, recomienda revisar uno por uno, y si la mitad está mal ofrece descartar el resto.

**🧠 Los rechazos enseñan.** Al marcar un par como malo se dice por qué: otro auto o motor, otra
medida o variante, juego contra pieza suelta, otra pieza, código mal leído. El motivo se guarda
(`equivalencias_revisadas.motivo`), y con él la app busca en la lista los pares con el MISMO
problema y ofrece descartarlos juntos (`pares_parecidos()`). Los criterios son estrechos a
propósito, porque lo que se ofrece se descarta con un botón: el mismo producto contra una
variante del otro con la misma descripción salvo el espesor; contra otro que nombra
exactamente los mismos modelos; contra otro con la misma medida; los mismos dos tipos de juego
entre las mismas dos listas; todo lo que cuelga del mismo código de fábrica. Con un código de
fábrica del otro lado no se busca por texto, porque su descripción es una copia.

**Lo que la muestra encontró en la primera pasada**, y que se corrigió en las reglas:

- «Jta.Tapa Cil. S10» contra «Junta Tapa de Válvulas M.W.M.» quedaba limpia con 75 puntos. El
  texto dice que son dos piezas distintas, y eso solo dejaba de sumar. Ahora, cuando cada
  descripción nombra un lugar del motor que la otra no —cárter contra tapa de válvulas,
  múltiple contra salida de escape, carburador contra tapa de cilindros—, el par se tumba.
  En la cola real: 422 pares.
- «Ranger Puma 2168cc» contra «Fiesta Focus Transit 1,8» se salvaban de «modelos distintos»
  porque las dos dicen TDCI. Las tecnologías de motor (TDCI, HDI, 16V, TURBO...) ya no cuentan
  como motor compartido. En la cola real: 95 pares.
- «JTA S.TAPA A.LEVA» de IMPERIAL es la junta de tapa de válvulas de los motores con el árbol
  de levas arriba, y ahora se lee así.

### Una ronda de muestras de control hecha sobre la base real

Antes de dejar la muestra de control en manos de nadie, se hizo una ronda leyendo pares al azar
de cada grupo grande. ILLINOIS↔TARANTO y los grupos contra códigos de fábrica salieron bien;
**CRI-FA↔FISPA salió mal**: sensor de velocidad de Logan contra el de Megane, sensor de rotación
de Fiat Marea contra el de Audi A3, sonda de Honda Fit contra la de GM Astra. Lo que había detrás:

- **Un par entre dos proveedores se aprobaba sin ninguna evidencia.** Arranca en 50, suma 15 por
  el rubro y 10 por el precio: 75, limpio. Ahora, si no los une ningún código y las
  descripciones no concuerdan, queda en 50 con «🤷 Nada dice que sean la misma pieza».
- **Coincidir en la pieza y en la marca no es concordar.** «Sonda lambda ... Ford» contra
  «SONDA LAMBDA ... FORD ESCORT MONDEO ...» coincide en eso y nada más, y FISPA nombra veinte
  autos por producto. Ahora hace falta un modelo o un motor en común.
- **El mismo motor escrito distinto sí cuenta**: «PERKINS 4.203» y «4-203», «6.354» y «6-354»
  (se comparan sin el separador); y un modelo que es un número cuenta aunque no venga pegado a
  la marca («FIAT 1600 125» contra «FIAT 125»).
- **Los sensores de tipos distintos son piezas distintas**: velocímetro contra mariposa, MAP
  contra rotación. Se lee qué mide cada sensor, con sus sinónimos (`tipos_de_sensor()`).
- **Cables, terminales y salidas** se leen como la cantidad de vías: «4 CABLES» contra «3
  terminales» son sensores distintos.

Sobre la cola real, las limpias pasan de 22.484 a 21.045; de las que bajan, casi todas son de
CRI-FA↔FISPA y de pares sin nada en común más que la marca.

### El motivo también en la revisión de a uno, y las medidas de o'rings y retenes

- **Descartar con motivo en toda la revisión.** En la lista de «para revisar», al marcar un
  grupo o un par como «🚫 Descartar» aparece «¿Por qué?» (opcional). Al aplicar, el motivo
  queda guardado y, con el análisis nuevo, la app busca los pares con el mismo problema y los
  ofrece arriba, igual que en la muestra de control (`parecidos_de_varios()`).
- **Las medidas de dos números, cuando se sabe qué pieza es.** El lector no tomaba «20x2.5»
  porque en un o'ring es diámetro por cordón y en un retén interno por externo. Pero la
  descripción casi siempre lo dice: «O´RING 36,5X3.53MM» se lee como diámetro interno y cordón,
  «RET DIST FORD 1.4 TDCI 40x55x» y «ARAND 16x22» como interno y externo. Además, «Reten Arbol
  Secund.30x44x8» no se leía porque el punto de la abreviatura parecía un decimal. En la base
  real, los productos con diámetro interno leído pasan a unos 600. `VERSION_MEDIDAS` pasó a «5»:
  la tarea de fondo relee las descripciones sola.

### Segunda ronda de muestras: carburadores, cilindros, bujías

Leyendo muestras de los grupos medianos (IMPERIAL↔JL, IMPERIAL↔TARANTO, ILLINOIS↔IMPERIAL,
FISPA↔JL) salieron cinco errores sistemáticos más, todos corregidos:

- **JL no escribe «carburador»**: «JUNTAS FIAT TEMPRA WEBER», «JUNTAS DODGE 1500 STROMBERG». La
  marca del carburador (Weber, Solex, Holley, Stromberg, Zenith, Caresa, Brosol...) ahora dice
  que es un juego de carburador, y dos carburadores distintos no son el mismo juego.
- **La cantidad de cilindros**: «Junta para Cárter DEUTZ 913 ... 5 CIL.» contra «JTA CARTER
  DEUTZ 913 3 CIL.» es el mismo motor con otro cárter.
- **Bujía de encendido contra bujía de precalentamiento**: se llaman igual; las de FISPA
  «LEIGG...» son de diésel. Se lee cuál es (`tipo_de_bujia()`).
- **«J.DEERE», «J. DEERE» y «JHON DEERE» son John Deere**: sin eso «DEERE» contaba como un modelo
  compartido entre cualquier par de juntas de John Deere.
- **«Diferencial», «colector», «filtro»** ahora son palabras de pieza, y «JGO JTAS SIN T.CIL.»
  es el juego completo sin la junta de tapa de cilindros.

Sobre la cola real, 380 pares más dejan de aprobarse solos; en las muestras, todos mal
emparejados.

### 🪭 El abanico: un producto con muchos candidatos, elegido a mano

La tercera ronda de muestras mostró el error más grande que quedaba: **un producto emparejado
con muchos productos distintos de la otra lista**. La sonda 80007 de FISPA nombra tantos autos
que «concordaba» con 25 sondas distintas de CRI-FA; la junta de ILLINOIS de la Hilux 2,8 estaba
con 11 juntas de TARANTO de otros motores de la Hilux. Como mucho una de cada abanico es la
equivalente, y aprobar el grupo las aprobaba todas.

- **En el análisis**: cuando un producto tiene 4 o más candidatos distintos en una misma lista
  (las variantes de una misma pieza cuentan como uno), se queda el que mejor coincide —más
  modelos, motor y cilindrada en común— y los demás van a revisión con «🪭». Si empatan más de
  dos, van todos. Para comparar la cilindrada, «2779cc» ahora es 2.8 y «1587CC» es 1.6.
- **En la pantalla**: **🪭 Elegí cuál es la equivalente** muestra cada producto con sus
  candidatos, de a 5 productos por página. Cada opción es una pieza con todas sus variantes
  (52 candidatos que eran 11 juntas en 2 materiales y 3 espesores quedan en 11 opciones); si el
  producto dice su espesor, se aprueban solo las de ese espesor. Se marca la que es y, con «Ya
  lo miré», el resto se descarta. Una decisión resuelve todo el abanico.
- Los que están en revisión solo por el abanico no se repiten en la lista de «para revisar».

Sobre la cola real: las limpias quedan en 15.489 (11.096 de FISPA y 2.726 de ILLINOIS contra
códigos de fábrica, que en las muestras salieron bien) y 4.463 pares pasan a resolverse en
1.078 decisiones de abanico, en vez de aprobarse a ciegas.

### La revisión, más rápida

Cada decisión en la pantalla de revisión rehace el análisis de la lista entera, y en la lista de
FISPA eso eran 14 segundos. 10,6 se iban en leer las mismas descripciones una y otra vez: el
código de fábrica copia la descripción del producto que lo nombró, y cada vuelta volvía a leer
todo. Ahora lo que sale del texto se lee una vez por proceso (`_firma_del_texto()`, y también
`familia_para_comparar()`, `codigo_sospechoso()` y `codigo_que_hoy_no_se_tomaria()`, que
dependen solo del texto); los autos que la base sabe de cada producto se siguen preguntando cada
vez. Con los mismos resultados:

| Lista | Antes | Primera vez | Después de cada decisión |
|---|---|---|---|
| FISPA (13.941 pares) | 14 s | 9 s | 4,3 s |
| BARRIDO (10.899) | 6,2 s | 4,1 s | 2,9 s |
| ILLINOIS (3.172) | 3,1 s | 1,9 s | 1,3 s |

### 📋 Para revisar, por motivo

Con todo lo anterior, lo que queda «para revisar» en la base real son unos 8.000 pares, y la
única forma de resolverlos era la lista de a 10 por página. Ahora, arriba de esa lista:

- **Un resumen con todos los motivos** de la lista, cuántos pares tiene cada uno y qué conviene
  hacer. Los motivos que son contradicciones del texto se agrupan sin el detalle («piezas de
  lugares distintos: CARTER vs CILINDRO» y «...: CARBURADOR vs VALVULA» son un solo grupo).
- **🚫 Descartar el grupo**, para los que el texto contradice —otro auto u otro motor, otra
  cantidad de cilindros, dos piezas de lugares distintos, un juego contra una junta suelta, las
  medidas que no dan, un código que no es un código—: se muestran 8 ejemplos al azar y se
  descarta el grupo entero con su motivo guardado. Si se prefiere, se puede mirar una muestra
  antes.
- **🎯 Con muestra**, para las dudas —«nada dice que sean la misma pieza», el precio, un código
  que apunta a dos productos—: la misma muestra de control que las limpias, con aprobar o
  descartar el resto según lo que salga (`_panel_de_muestra()`, compartido por los dos).

Las dudas, además, se separan **por par de listas** («nada dice que sean la misma pieza ·
CRI-FA ↔ FISPA» es un grupo e «IMPERIAL ↔ TARANTO» es otro): una muestra sólo sirve si todo el
grupo se parece, y dos proveedores que escriben distinto no se parecen.

En la lista del barrido, por ejemplo, 4.875 pares quedan en 11 grupos para descartar (el más
grande, «cilindradas distintas», son 1.066 pares de un toque) y las dudas se resuelven con una
muestra por par de listas (631 pares de CRI-FA ↔ FISPA, 477 de IMPERIAL ↔ TARANTO…).

**Agua y aceite** cuentan ahora como lugares de la pieza: «JTA CPO.BBA. ACEITE» y «JTA
CPO.BBA.AGUA» son dos juntas distintas, aunque todo lo demás coincida.

**Y una falsa alarma menos**: «el código de fábrica apunta a más de un producto de FISPA» salía
en 2.585 pares, y casi todos eran la misma pieza de las dos marcas que vende FISPA en su lista
(«40015FISPA» y «LEMSM017LUCAS» citando el mismo número). La ambigüedad ahora se busca dentro de
cada marca (`_submarca_del_codigo()`), y 1.380 pares vuelven a limpios.

### 🌐 El portal del proveedor como otra forma de relacionar

Un distribuidor como JL vende el mismo repuesto en varias marcas —el caño de Cauplas y el de
otra, el sensor de Masser y el de Bosch— y en su portal la ficha de uno muestra los otros. Es lo
que uno relacionaría a mano, escrito por alguien que conoce la pieza.

Ahora, con el portal configurado en los secretos (`[portal_JL]`, lo mismo que ya servía para
traer autos), **Mantenimiento → 🔎 Encontrar equivalencias → 🔐 Portal del proveedor** lee las
fichas de a tandas y de cada una saca dos cosas en una sola visita: los autos, como antes, y los
productos de tu catálogo que la ficha nombra (`leer_fichas_del_portal()`).

- **Los códigos se buscan al revés**: en vez de adivinar qué es un código, se prueban los
  pedazos del texto contra los códigos ya cargados. Así entran los de JL con espacios («MBS
  018», «390 718 060»). Un pedazo de varias palabras cuenta solo si está escrito exactamente
  como en la lista; los precios se sacan antes, y un número corto suelto no cuenta
  (`productos_nombrados_en_la_pagina()`).
- **Una ficha que nombra más de 10 productos tuyos es un listado** y no cuenta.
- **No decide solo.** Los pares van a revisión en su propia lista («PORTAL JL · …») y quedan
  anotados en `productos_juntos_en_portal`. En el análisis es una prueba más de
  `evidencia_cruzada()` —«🌐 el portal de JL los muestra juntos»—: con la descripción que
  concuerda son dos métodos, pero si las medidas, el rubro o el auto dicen otra cosa, el veto
  gana igual. Un portal no tiene todas las relaciones y en la misma página puede haber
  «productos relacionados» que no son la misma pieza.
- **Cada tanda sigue donde quedó** (`fichas_de_portal_leidas`), primero lo que tiene stock.

Probado contra un portal simulado sobre la base real: dos pares del barrido que JL mostraba
juntos pasaron de «un solo método» a «dos métodos coinciden», y un sensor que la página nombraba
al lado de una junta siguió vetado por rubros distintos.

### 🚗 Los modelos más vendidos no se reconocían

La lista de modelos conocidos salía de la columna de modelo de las aplicaciones **con un tope de
3.000**, y la base real tiene 4.042: el corte caía donde caía y dejaba afuera GOL, GOLF, POLO,
MEGANE, LOGAN, KANGOO, HILUX, PASSAT y VENTO. Además «Toyota Corolla.» —con el punto, como
escribe CRI-FA— no se leía como COROLLA, y en cambio «DESDE» (de «desde 2008») sí contaba como
modelo. Arreglado las tres cosas (`_modelos_conocidos()`, `_PALABRAS_QUE_NO_SON_MODELOS`).

Con los modelos bien leídos, **«modelos distintos» alcanza con que UNA descripción sea
específica** (uno o dos modelos), aunque la otra sea la lista larga de FISPA: «Sensor MAP
Chevrolet Onix Prisma» contra «SENSOR MAP CHEVROLET CAPTIVA - LACETTI - NUBIRA...» es el sensor
de otros autos. Lo que lo salva sigue igual: el modelo escrito en cualquier lado de la otra, o
un motor en común.

Sobre la cola real: «🤷 nada dice que sean la misma pieza» baja de 1.510 a 1.173 pares, y
«modelos distintos» —que se descarta de un toque— sube de 259 a 593. En una muestra de 25 de los
nuevos descartes, los 25 eran de autos distintos. Y el motivo del abanico ya no se parte en un
grupo por cantidad («emparejado con 4», «con 5»…).

### ➕ Cargar un portal es pegar un link

Antes, un portal se configuraba escribiendo en los secretos de Streamlit la dirección de la ficha
con `{codigo}` adentro, el login y los nombres de los campos del formulario; y el catálogo
público de una marca era otra cosa aparte, que servía para fotos y links pero no para leer autos
ni relacionar productos.

Ahora son lo mismo. En **🔐 Portal del proveedor → ➕ Cargar un portal** se elige el proveedor
y se pega el link de la ficha de cualquier producto suyo, copiado del navegador:

- **La app encuentra el código en el link** (`plantilla_desde_un_ejemplo()`) y arma la
  dirección para todos los demás. Acepta que el sitio escriba el código a su manera:
  `{codigo}` como en la lista, `{codigo_pegado}` sin guiones ni espacios,
  `{codigo_minusculas}` y `{codigo_pegado_minusculas}`. Todas pasan por
  `url_de_la_ficha()`, que además limpia el código para que no pueda convertir una consulta en
  otra cosa. Sin el `https://` (copiado del celular) también sirve.
- **La prueba antes de guardar** con ese producto y con otro de la lista
  (`probar_plantilla_de_portal()`): si la ficha se lee, qué autos nombra y cuántos productos
  tuyos muestra. Si la página abre pero no muestra el código, avisa: el sitio la arma con
  JavaScript o el link no es el de la ficha.
- **Un portal sin contraseña, como el de Wega, no necesita nada más.** Los secretos quedan solo
  para el usuario y la clave de los que piden login; la dirección la tiene la app.
- Guardado, sirve para todo lo que usa el catálogo: leer autos y productos juntos, las fotos y
  el link a la ficha en el buscador. En Administrar → Marcas también se puede pegar el link en
  vez del patrón.
- Si varias fichas seguidas no abren, la tanda se corta y esas fichas **no** quedan como
  leídas: un error de red no es una respuesta, y antes se perdían para siempre.

### 🧾 Wega, y los autos que se leen de una ficha

**Wega ya es un portal conocido** (`PORTALES_CONOCIDOS`): su ficha es
`www.wega.com.ar/catalogo/filtros/detalle/wo-161` —el código en minúsculas, con el guion— y la
página se arma en el servidor, así que las aplicaciones se leen sin JavaScript. Cuando la lista
de Wega esté cargada, «➕ Cargar un portal» la ofrece con un botón, sin pegar ningún link; se
prueba igual antes de guardarla. Los catálogos de Taranto, Illinois y FISPA no entran porque se
recorren por rubro o por auto y no tienen una ficha por código.

**Los autos de una ficha se guardaban mal**, y eso metía pruebas falsas en el análisis. Se
juntaban todas las palabras conocidas de la página y cada una era un auto aparte: «BOXER» con
marca BOXER, y también «APLICACIONES» o «DIAMETRO», que son títulos de la página. Como
aplicaciones de fábrica, eso contaba como «dos fabricantes lo dan para el mismo auto». Ahora
cada modelo va con la marca que lo precede (`_autos_del_texto()`), mirando solo las 8
palabras que siguen —la última marca de la página no se come el pie—, y sin modelo no se
guarda nada.

**Y la lista de modelos conocidos se limpia sola.** Las aplicaciones deducidas de las
descripciones traían basura en la columna de modelo: DIAMETRO como modelo de Fiat, CAMION,
FAMILIA, PISTON, VAN. Un modelo de verdad aparece casi siempre con su marca —GOL con
Volkswagen en el 85% de las descripciones que lo nombran, COROLLA con Toyota en el 96%— y esas
no: DIAMETRO está con Fiat en el 13% y con otras marcas en el 80%. Se saca la que anda con su
marca menos del 30% de las veces y con otras al menos el 20%
(`_modelos_que_andan_con_otras_marcas()`); las que casi nunca van con marca (MACHO, PRIMARIO)
están a mano, porque así también son TORINO y GALILEO, que sí sirven. En la cola real cambian 4
pares, los cuatro bien: juntas de escape de Fiesta y Clio que «coincidían» con una de motor MWM
porque ACOPLE contaba como modelo.

### 🪭 El abanico, sin los candidatos que ya estaban vetados

El abanico —un producto emparejado con cuatro o más productos distintos de otra lista— se armaba
con TODOS sus pares, también los que el texto ya contradecía. Eso hacía dos daños:

- aparecían como opción en «Elegí cuál es la equivalente»: la junta de tapa de válvulas del
  Peugeot 404 contra el juego de carburador, la de cárter y la de diferencial;
- inflaban el abanico: un producto con UN candidato bueno y cuatro vetados era «un abanico», y
  el bueno tenía que ganarles en fuerza de la coincidencia o se iba a revisión.

Ahora cada par se evalúa primero y el abanico se arma después, solo con los que no quedaron
vetados. Sobre la cola real: **258 pares vuelven a limpios** (juntas de tapa de MWM Sprint,
Sprinter, Pathfinder, Cruze 1.4, Fire 1.4…), y «Elegí cuál» baja de 1.078 productos con 10.746
opciones a 767 con 6.778.

**Y las juntas de carburador de JL.** «JUNTAS FIAT 128 1972/ WEBER 1b» dice que es de carburador
por la marca del carburador, pero WEBER, SOLEX y HOLLEY también son marcas de repuesto y se
sacaban antes de mirar: quedaba «JUNTA 128» a secas y concordaba con la junta de tapa de
cilindros del 128. Ahora la marca de carburador se busca en todo el texto, solo en las juntas
(un «SENSOR TPS WEBER» es de inyección). 45 pares de cárter o tapa de válvulas contra juegos de
carburador pasan a descartarse, y 6 juegos de carburador que sí coinciden pasan a limpios.

### 🔢 La cilindrada de FISPA, y sus mellizos con LUCAS

**FISPA escribe la cilindrada sin punto**: su lista llega sin ningún signo, así que «FOCUS 2 0
DURATEC» o «ASTRA 1 8 - CELTA 1 4» son el 2.0, el 1.8 y el 1.4, y no se leían. «Sensor MAP Ford
Focus 1.8» no se podía separar del sensor del Focus 2.0. Ahora se leen, solo en las
descripciones que no traen ningún número con punto o coma, y no después de una «X» («M 12 x 1
5» es una rosca).

**Los mellizos FISPA/LUCAS cuentan como una sola opción del abanico**
(`pieza_para_el_abanico()`): «SENSOR MAP 40068 FORD FIESTA VI…» y «SENSOR MAP LEMSM057 FORD
FIESTA VI…» son la misma pieza con dos códigos, y contados como dos, cualquier producto que
encajara con ese sensor tenía un empate de más.

Sobre la cola real: 149 pares pasan a limpios (el MAP del Aveo 1.4 con el de FISPA para Aveo
1 4, la bobina del Cruze 1.8 con la de LUCAS) y 50 a descartarse por cilindrada (el inyector del
Kuga 1.6T contra el de Focus/Kuga 1 5, la bujía de S10 4.3 V6 contra una de S10 2 8 diésel). Los
pares en revisión solo por el abanico bajan de 4.209 a 3.580.

### ⚠️ «El código apunta a dos productos de FISPA»: accesorios, kits y versiones originales

Era la alarma más grande de la lista de FISPA (1.034 pares), y en las muestras había cuatro
clases de casos que no son errores de carga (`_dos_que_citan_el_mismo_numero()`):

- **uno nombra al otro**: «CAPUCHONES 79012 … MONTA EN BOBINA 70213», «70120 (reemplaza a
  70181)»;
- **la misma pieza en versión común y «(ORIGINAL)»**: 84029 y 831259, el mismo sensor de la
  Amarok;
- **piezas distintas que van juntas**: el microfiltro y el inyector, el kit de reparación y el
  aforador.

Esos dejan de ser alarma. Y cuando uno es el **accesorio** o el **kit que trae la pieza**, su
par con el número no es una equivalencia y se aparta con los kits (`_es_accesorio_del_numero()`):
lo que «monta en» otra pieza, lo que tiene el número dentro del código del otro («FI-IWP006» es
el inyector IWP006, no el microfiltro que lo cita), o el kit frente a la pieza suelta. No se
decide por quién trajo el número primero: el capuchón suele ser esa fila, y la bobina —la dueña
del número— quedaba como su accesorio. «Reemplaza a» nunca se aparta.

**Y en general, un kit no es sus componentes** (`_numero_de_un_componente()`): «KIT BOB CAB
(LEIG005/LEIHTG73SC)» es la bobina LEIG005 más los cables, y «DISTRIBUCION C/BOMBA (LKTBN285 +
LWPN029)» el kit LKTBN285 más la bomba. El importador toma esos códigos como números de fábrica
del kit, y el vínculo decía que el kit ES la bobina. Cuenta como componente si está en una lista
con «+», o con «/» y además es el código de otro producto de la misma marca.

Sobre la cola real: 246 pares pasan a limpios, 225 se apartan como kit o accesorio (118 de ellos
estaban limpios y eran errores: capuchones contra la bobina, kits contra su componente), y la
alarma de código ambiguo baja de 1.394 pares a 804.

### 💲 El precio, dicho como se entiende, y el motivo que decide

La alarma del precio decía «los precios se diferencian 1 veces, y entre estos dos proveedores lo
normal es 9»: correcto e incomprensible. Ahora dice «cuestan casi lo mismo, y entre estos dos
proveedores lo normal es que uno salga 9 veces más. Puede ser más (o menos) pieza» —que es lo
que pasa: un juego completo de motor al precio de una junta suelta— (`texto_de_precios_que_no_cierran()`).

Y **el grupo de «Para revisar, por motivo» lo decide la alarma más clara**, no la primera
(`motivo_para_agrupar()`). El precio sale primero porque lo avisa `evaluar_equivalencia()` antes
que los vetos, y 386 pares de la cola real con, por ejemplo, «juego completo contra junta
suelta» caían en el grupo del precio —que pide muestra— en vez del de juegos distintos, que se
descarta de un toque. En el barrido, de 5.443 pares en revisión, 3.945 quedan ahora en grupos
de un toque.

**Y los kits que dicen la cantidad** —«KIT BOB BUJ (LEIG030 X 4/LSPR6F13)»— también se reconocen
como kit con sus componentes.

### 🚜 Modelos con barra, cilindros como «4 C.» y botadores

Tres formas de escribir que la app no leía, casi todas de IMPERIAL y de las juntas de tractor y
camión:

- **Los modelos con número y barra**: «J.DEERE 2420/2730», «FIAT 128/147», «FIAT 1500/1600». La
  barra dejaba todo como una sola palabra que no era ni número ni modelo, y la marca con punto
  («J.DEERE», «M.BENZ») tampoco contaba como marca. Ahora cada número cuenta como modelo.
  24 pares pasan a limpios —el cárter del Fiat 128/147 con el de Illinois, el del 1500/1600, el
  de John Deere 3420/4220— y 3 se descartan por modelos distintos.
- **Los cilindros como «3 C.» o «4/6 C.»** (para 4 y 6 cilindros), además de «4 CIL.». Con el
  punto después de la C y sin un número pegado adelante: «ORING 12x3.5 C.D.ACE» es una medida.
  El cárter del Fiat tractor 400 de 4 cilindros ya no se da por igual al de 3.
- **BOTADORES** como lugar de la pieza: «JTA LATERAL BOTADORES» y «JTA LATERAL T.V.» son dos
  tapas distintas.

### 🌡️ El largo del cable de la sonda y la temperatura del bulbo

Dos datos que las listas escriben y distinguen variantes de la misma pieza para el mismo auto:

- **El largo del cable de la sonda lambda** (`largo_de_cable_mm()`): CRI-FA escribe «Largo
  cable 28 centimetros» —y lo repite en el código: «14-R8834.40.046» es la de 46 cm— y FISPA
  «Cable de 48cm» o «LARGO DEL CABLE 530mm». Dos sondas del mismo auto con cables de 46 y 103
  cm son dos sondas distintas (antes y después del catalizador, u otro motor). Tolerancia: 3 cm
  o el 10%. Veto «largo de cable distinto», que se descarta de a grupo como variante.
- **Las temperaturas de un bulbo** (`temperaturas_declaradas()`): «92º/82º», «temp. 102/97»,
  y FISPA «Temp 86? 76?» con el signo de grado roto. Un bulbo de electroventilador de 92/82 no
  reemplaza a uno de 102/97. Solo pares de 70 a 125 grados y en descripciones que hablan de
  bulbo o temperatura.

Y **la frase del largo del cable ya no cuenta como palabras en común**: «LARGO» y «CABLE»
hacían concordar a cualquier sonda de CRI-FA con cualquiera de FISPA —una de Honda Fit
«coincidía en LAMBDA, LARGO, SONDA, CABLE» con una de Ford Zetec—.

Sobre la cola real: 254 pares con cables de largo distinto y 17 bulbos con otras temperaturas
quedan vetados; 30 que estaban limpios pasan a descartarse, y 19 sondas que el abanico frenaba
—porque competían con las de otro largo— pasan a limpias (Gol/Fox con Gol Trend/Fox, Honda
Fit con Honda Fit, Berlingo con Berlingo).

### 🧬 Los mellizos FISPA/LUCAS que no concordaban, y un motivo para los que no tenían

FISPA vende lo suyo y lo de LUCAS con la misma descripción, y el número de fábrica lo trae una
sola de las dos filas. El mellizo quedaba en 50 puntos y **sin ningún aviso** cuando las
descripciones no «concordaban» por una palabra rota o un plural: «REGULADORES DE PRESIo N 16004
FIAT Brava 1 6 16v» contra «REGULADOR DE PRESION LEICP003 FIAT Brava 1 6 16v».

Ahora se reconocen (`_descripciones_mellizas()`): las mismas palabras sin los códigos, sin
«ORIGINAL» y sin la S final, en 3 de cada 4. Solo entre **dos marcas** —FISPA y LUCAS—: dos
productos de LUCAS con casi la misma descripción son dos versiones (dos motores de arranque
para los mismos autos), que es justamente la duda de «el código apunta a más de un producto».
Cuentan igual que la variante de la fila de origen: +35. Sobre la cola real, 164 pares pasan a
limpios —reguladores de presión, ralentís, kits de reparación de bomba, sondas, MAF— y en la
muestra todos eran mellizos de verdad.

Y **ningún par en revisión queda sin motivo**: los que solo une el número de fábrica —las
descripciones no dicen lo mismo y el número solo no alcanza— dicen eso («🔢 Solo los une el
número de fábrica»), en vez de caer en «Sin alarma puntual».

### 🔧 Motores Fiat, VW AP y Perkins no son números de fábrica; la pieza dueña del número

- **Códigos de motor que estaban como números de fábrica**: los Fiat sin punto (188A9000,
  199A2000, 176B2000, 939A4.000), el VW AP (AP2000) y los Perkins con punto (1004.4T). Unían
  juntas de tapa de Fiat con las de la Chevrolet Combo —mismo motor— y aros de pistón de Ford
  con los de Volkswagen. Ninguno de los códigos de proveedor del catálogo tiene esas formas.
  12 vínculos que estaban limpios pasan a 🧯.
- **La pieza dueña del número**: cuando el número lo cita un kit o un accesorio —el kit de
  reparación de la bomba de combustible cita el número del aforador— y queda una sola pieza
  que no es accesorio, el número es de ella y queda respaldada por la fila del kit, igual que
  la variante por la fila de origen. 49 aforadores pasan a limpios.
- **El aviso 🔢 solo en los unidos por un número**. Los pares entre dos proveedores que quedan
  cortos dicen «🤏 Las descripciones se parecen, pero no alcanza».

### 🚌 Ómnibus y tractores como números de fábrica; variantes de material; medidas de verdad

- **Más modelos que estaban como números de fábrica**: los ómnibus Mercedes (OH1115, OHL1320,
  OHL355) y los modelos escritos marca+número (DEERE730, DEERE3350, VW1500, MB3500). Con 3 o 4
  cifras, para no tocar números reales como «BENZ312015220». Ninguno de los códigos de
  proveedor tiene esas formas. 21 vínculos que estaban limpios pasan a 🧯.
- **La misma pieza en otro material o espesor no es un código ambiguo**: Illinois lista «MEDIA
  LUNA TAPA DE VALVULAS (SINTETICO)» y «(SILICONA)», o la junta de bomba de nafta de 0,8 y de
  1,6 mm, y las dos citan el número de la pieza. Tampoco los juegos del mismo motor de distinto
  tipo (descarbonización, inferior, «sin TC»): el análisis de cada par ya descarta el tipo que
  no es.
- **Un código con forma de medida no se aprueba sin mirar**: «Materiales para junta CORCHO Y
  GOMA» contra «800MM.X600MM» llegaba a 65. Ahora queda en revisión.
- **Y la alarma «parece una medida» ya no marca números reales**: el número tiene que estar
  suelto y tener un tamaño que la unidad admita. «E0NN6051CC» (Ford), «BI0113MM» (Magneti
  Marelli pega MM al final), «1920LT» y «1525KG» (Peugeot/Citroën) y «19208W» dejaron de
  perder 35 puntos; «1600CC», «24V» y «700MM.X470MM» se siguen marcando.

### 🧪 Lo que se probó y NO se dejó

Dos reglas que parecían buenas y la cola real dijo que no:

- **Las muescas del código como espesor** («TC-355-MG 2M», «232407-2M»): Illinois y Taranto no
  numeran igual —Illinois usa la marca del fabricante, con 0M; Taranto cuenta 1M, 2M, 3M—. En
  los pares que declaran espesor, «291307-3M» de 1,3 mm es «TC-130-20 0M» de 1,3 mm, y hay pares
  con las mismas muescas y espesores distintos. No sirve para comparar entre marcas.
- **Juego de juntas contra junta suelta** sin tipo de juego: frenaba 158 limpios, y Taranto
  llama «Jgo.Jta.Tapa Cil.» a la junta de tapa con sus accesorios, o al par de juntas de un
  motor en V, que puede ser el mismo producto que la «Junta Tapa de Cilindros» de Illinois.

Sí quedó «DIFER.» como abreviatura de DIFERENCIAL: la tapa de diferencial tipo 34 de la Transit
concordaba con la del Dana 46 de la F-100 porque las dos decían «DIFER.».

### ⏱️ Más rápido: `sanitizar()` recordada y los modelos guardados

Con todas las reglas nuevas, analizar la lista de FISPA tardaba 11,3 s la primera vez. El perfil
mostraba a `sanitizar()` llamada 793.000 veces —casi siempre con los mismos códigos y las mismas
palabras— y a las comparaciones de mellizos y variantes limpiando cada palabra dos veces.

- `sanitizar()` ahora recuerda (lru_cache de 200.000); lo que no sirve de clave pasa directo.
- Las palabras de cada descripción sin su código se calculan una vez por producto
  (`_palabras_sin_el_codigo()`).
- La limpieza de la lista de modelos (2,6 s recorriendo el catálogo) se guarda en la
  configuración con una huella del catálogo y se rehace solo cuando el catálogo cambia: el
  segundo arranque tarda 0,03 s.

FISPA: 11,3 → 8,9 s la primera vez, 5,8 → 4,6 las siguientes; el barrido 5,1 → 4,4 y 4,3 → 3,3.
La clasificación de la cola no cambia en un solo par.

**Y `evidencia_cruzada()` sin ocho consultas por par** (`precargar_para_evidencia()`): los dos
productos y sus medidas se traen de una vez para toda la lista, y las tablas enteras —ventas,
vínculos cargados, portales, reemplazos, aplicaciones de fábrica— se leen una sola vez por
análisis; la cadena de reemplazos y el cruce de aplicaciones solo se consultan para los códigos
que los tienen. En FISPA eran 128.000 consultas. Ahora: FISPA 7,5 s la primera vez y 3,0 las
siguientes; el barrido 3,3 y 2,1. Los avisos y las pruebas de cada par son idénticos.

Los autos que la base sabe de cada producto (aplicaciones y lo que el taller le puso a cada
vehículo) también se precargan por tandas con los mismos topes: eran dos consultas por producto.
FISPA queda en 7,0 s la primera vez y 2,7 las siguientes; el barrido en 2,9 y 2,1.

### 🧭 Cómo resolver esta lista, paso a paso

La pantalla de revisión tiene cinco herramientas —los kits y accesorios, los descartes por
motivo, las muestras de las limpias, las muestras de las dudas y los abanicos— y con miles de
pares no era obvio por dónde empezar. Arriba de todo, debajo de los contadores de confianza,
ahora hay un plan (`plan_de_la_lista()`): los pasos en el orden que conviene —de lo que se
resuelve de un toque a lo que hay que mirar—, cuántos pares resuelve cada uno, cuánto trabajo a
mano lleva y en qué parte de la pantalla está. Cada par se cuenta una sola vez: los pasos suman
el total de la lista.

En el barrido real: 4.360 pares se descartan en 13 toques; 1.879 limpias se aprueban con 307
marcas en 10 muestras; 1.551 dudas se resuelven con 385 marcas en 22 muestras; y quedan 698
productos para elegir a mano entre varios candidatos (3.109 pares). En la lista de FISPA, 12.790
limpias se aprueban con una sola muestra de 80.

### ⭐ Elegí cuál: la sugerida viene elegida, y primero los fáciles

En «🪭 Elegí cuál es la equivalente», cuando una sola de las opciones le gana a todas —el análisis
la dejó limpia y las demás en revisión—, viene ya elegida y marcada con ⭐
(`pieza_sugerida_del_abanico()`). Nada se aprueba sin mirar: hay que guardar igual, y si no es,
se saca. Y el orden ahora va de lo fácil a lo difícil: primero los que tienen sugerida y, entre
esos, los de menos opciones. Antes iban primero los de más candidatos. En el barrido, 149 de los
698 productos traen sugerida.

De paso, **la tapa trasera y la tapa delantera del motor son lugares de la pieza**: «JTA TAPA
TRASERA FIAT FIRE 16V» salía limpia —y con ⭐— contra la junta de tapa de válvulas del Fire.
Con las abreviaturas de Imperial («TAPA TRASE.», «TAPA DELAN.», «TAPA DEL.») y sin confundir la
preposición («TAPA DEL CARTER»). La tapa delantera del block es la de la distribución, así que
«TAPA BLOCK LADO DIST.» coincide con «TAPA DELAN. BLOCK».

### 🎯 Los grupos grandes de limpias, partidos por confianza

Las 12.790 limpias de FISPA contra los números de fábrica eran un solo grupo con una muestra de
80: 10.222 con confianza 100 —la descripción es la de la fila que trajo el número— y 1.283 entre
65 y 74, que pasaron con algún aviso. En 80 al azar entraban unas 8 de esas: si estaban todas mal,
la muestra no lo mostraba.

Ahora un grupo de 500 limpias o más se parte en dos si cada franja tiene al menos 100: confianza
alta (85 o más) y media, cada una con su muestra (`grupos_de_limpias()`). FISPA queda en 11.501 de
confianza alta (muestra de 80) y 1.289 de confianza media (muestra de 50): 50 marcas más para
saber de verdad cómo están las dudosas. Los grupos chicos no cambian. Las muestras de los grupos
partidos se guardan con otro nombre, así que si había una empezada sobre el grupo entero, se
empieza una nueva por franja (las marcas ya hechas siguen guardadas).

### 🛡️ La muestra de control, más exigente y sin trampas sin querer

Tres agujeros, todos probados sobre la base real con la pantalla de verdad:

- **Aprobar el resto pide que el error posible sea chico, no que haya pocos errores.** Antes se
  aprobaba con 0 o 1 error sin importar de cuántos: 1 en 30 pasaba igual que 1 en 80. Pero 1 en
  30 deja un tope de 17% —en un grupo de 1.000, hasta 170 vínculos malos—. Ahora el tope del
  intervalo de Wilson al 95% tiene que quedar en 12% o menos (`se_puede_aprobar_el_resto()`):
  0 en 30 alcanza (11%), 1 en 30 no (17%) y pide mirar 30 más; 1 en 60 sí (9%), 2 en 50 no, 2
  en 80 sí.
- **Lo aprendido de tus decisiones ya no mueve pares de franja por sí solo.** «De N
  ILLINOIS↔TARANTO que revisaste, aprobaste el 100%» suma 15, y los que se revisan son sobre todo
  limpias —la muestra sale de ellas—. Marcar bien 20 de la muestra subía los 919 del grupo de 75
  a 90, partía el grupo en dos a mitad de la muestra —la muestra empezada quedaba colgada— y
  metía 27 que eran sospechosos entre las limpias. Ahora lo aprendido suma, pero si sin él el
  par no llegaba a 55 (limpia) o a 85 (confianza alta), queda justo abajo de la línea
  (`sin_cruzar_la_linea_por_lo_aprendido()`). Para abajo no hay tope.
- **La muestra solo aprueba a los que estaban cuando se sorteó.** Se guarda qué pares tenía el
  grupo en ese momento (`pares_al_sortear_la_muestra`). Si después entran otros —una prueba
  nueva, otra tanda—, la pantalla los cuenta aparte y no los aprueba con esa muestra; cuando se
  terminan los de antes, les toca la suya («vuelta 2»: `clave_vigente_de_la_muestra()`). Al
  ampliar la muestra también se sortea solo entre los de antes, para que la estimación siga
  hablando de un solo grupo.

### 🔁 Lo aprobado, revisado con las reglas de hoy

Cada regla nueva se aplicaba a la cola que llega. Lo aprobado antes quedaba como estaba, y la
auditoría de siempre no lo vuelve a mirar: salta lo marcado «ok», y aprobar la cola marca «ok» a
todo lo aprobado. En Estadísticas → 🔗 Equivalencias sugeridas, **«🔁 Revisar lo aprobado»**
pasa cada vínculo cargado por `evidencia_cruzada()` —los mismos vetos de la cola— y por el control
del código de fábrica que hoy no se tomaría (`aprobados_que_hoy_se_vetarian()`). Muestra los que
chocan agrupados por motivo, con ejemplos, y cada grupo se corta o se confirma de un toque; lo
confirmado no vuelve a aparecer. Probado aprobando las 12.790 limpias de FISPA más 800 vetadas:
encuentra 78, y ninguna limpia con un veto de verdad. Tarda 1,4 s sobre 13.000 vínculos.

### 🧯 Los códigos de fábrica de 6 cifras no son basura

`codigo_que_hoy_no_se_tomaria()` le preguntaba al extractor con «PIEZA 453402 ORIG», donde el
número no queda declarado, y un número solo sin declarar pide 7 cifras. Los de Peugeot, Ford o
Scania que llegan como «REF ORIG PEUGEOT 453402» salían como «no es un código de fábrica»: 122
de los 14.046 de la base real, y la limpieza de «Puentes que hoy ya no se generarían» los hubiera
borrado con sus vínculos. Ahora se pregunta con el código declarado («REF ORIG 453402»), que es
como llegan. En la cola, 136 pares con esos códigos pasan de revisión a limpias —interruptores de
stop, bulbos, bombas, válvulas EGR, todos con la misma descripción de los dos lados—.

Y los topes por un código dudoso —🧯 a 15, 🔎 a 74, el código con forma de medida a 50— se
aplicaban antes de sumar la evidencia a favor, que los subía a 72 o 90. Con un código de fábrica
que no es un código la descripción coincide siempre —el producto de fábrica se crea copiando la de
la fila—, así que esa evidencia no dice nada del código. Ahora el tope vale hasta el final: la
junta TC-687-20 contra «4JB1TC», que es un motor Isuzu, estaba limpia con 72.

### 🎯 Una confianza que distingue mejor

Revisando a mano 45 limpias entre proveedores salieron cuatro clases de error que ahora el
análisis reconoce, y una clase de acierto que no veía:

- **El carburador.** «Juego de juntas para Carburador FIAT 1500 WEBER» y «JUNTAS FIAT 128/1500
  SOLEX» son del mismo auto y de otro carburador. La marca del carburador ya decía que era una
  junta de carburador; ahora, si las dos la dicen y no coincide, es un veto («carburadores
  distintos»). 12 vínculos de la cola real.
- **Las válvulas, en la tapa de cilindros.** La junta de un Fire 8V no es la de un Fire 16V, ni
  la de un Captiva 16V la del V6 de 24. Solo en juntas de tapa de cilindros: un sensor o una
  sonda nombran varios motores y dicen las válvulas de algunos, y ahí no se puede concluir nada.
  Y no cuenta si los une un código, como los demás motivos del auto. 10 vínculos.
- **S-MAX, C-MAX, B-MAX.** Partidos por el guion dejaban un MAX suelto: «Jta.Tapa Cil. FORD MAX
  ECONO» concordaba con la junta de un S-MAX 2.3 Duratec.
- **El abanico cuenta piezas, no códigos.** IMPERIAL vende la misma junta en varios materiales,
  cada uno con su código y la misma descripción (604AC2, 604AD2, 604AD6: «JTA CARTER DEUTZ 913 4
  CIL.»); contados como piezas distintas, la junta de Illinois de ese cárter tenía un abanico de
  tres empatados y ninguno quedaba limpio. Ahora dos candidatos son la misma opción si comparten
  el código base o dicen lo mismo sin el código (`piezas_del_abanico()`), en el análisis y en la
  pantalla de elegir. Y en las listas con varias marcas —FISPA vende lo suyo y lo de LUCAS— un
  candidato de cada marca no compite. 668 vínculos salen de revisión: Amarok, Duratorq, K9K,
  TU5JP4, Honda Fit, Deutz 913… en la muestra, casi todos bien.

**Lo que se probó y NO se dejó:** aplicar el abanico desde 2 candidatos en vez de 4. Bajaba
718 limpias, pero en la muestra muchas eran las buenas —Honda CRV 2.0 B20B, Fiat Tractor 700E,
Perkins 4-203, Fiesta HCS—: con dos o tres candidatos parecidos, «el que mejor coincide» por
palabras en común es casi azar. Tampoco puntuar por cuántas palabras de modelo comparten: los
pares buenos de motores viejos coinciden solo en un número («PERKINS 4-203», «FIAT 619») y se
hubieran castigado.

La cola queda en 18.300 limpias, 9.558 para revisar y 465 relacionadas.

### 🔍 Tres lecturas que confundían piezas

De otra muestra de 50 limpias entre proveedores:

- **«NEW», «NUEVO» y «NUEVA» no son modelos.** «Jgo.Jta.Tapa Cil. SUBARU NEW LEONE» y una junta de
  «VOLKSWAGEN ... NEW BEETLE» tenían un «modelo en común», y eso salteaba el control de autos
  distintos.
- **«4 CIL.» no es la tapa de cilindros.** «Junta Tapa de Válvulas M.W.M. CHEV S10 TURBO 4 CIL.»
  quedaba como junta de tapa de CILINDROS y concordaba con la de la tapa de cilindros del mismo
  motor. La cantidad de cilindros se sigue leyendo, pero ya no suma palabras a la pieza.
- **PERKINS y MWM dicen los cilindros en el nombre del motor.** «4.203», «6.354», «4.07T»: el
  primer número. «Junta Termostato MWM SPRINT 4.07» concordaba con «JTA BASE.TERM. MWM SPRINT 6 C.».

13 vínculos de la cola real pasan a revisión, todos con el error a la vista.

### 🔎 La alarma de «no está entre las referencias», solo donde corresponde

`el_codigo_no_figura_entre_las_referencias()` está pensada para el formato de ILLINOIS, que
pone los números de fábrica entre paréntesis AL FINAL: «... - 3.0 - 4JH1-TC (8974908951/...)».
Pero miraba cualquier paréntesis, y en FISPA los paréntesis son otra cosa: años —«Fiat Stilo 1.8
MPI 16V (2003-2008) ... (2003-2006)IWP156»—, «(reemplaza a 40035)», los chasis de un arranque.
Pasaban por una lista de referencias que no nombraba al código, y el código estaba escrito más
adelante, en «REF ORIG BOSCH 0261230027». Ahora cuentan solo los paréntesis del final (y lo que va
después de «//»), y los años no hacen de referencia.

De 851 alarmas 🔎 quedan 166, todas de ILLINOIS con un motor tomado como código (EW10J4RFN,
DOHC16V, K9K16V, 4JH1-TC). 640 vínculos de inyectores, sensores MAP, arranques y válvulas VVT de
FISPA pasan de confianza media (74) a alta, donde debían estar: la misma fila trae el número dos
veces.

### 🚚 Los modelos de camión y de motor que son un número

El número que va pegado a la marca ya contaba como modelo —«FIAT 128», «VW 1300»—, pero solo de
2 a 4 cifras y sin nada pegado. Quedaban afuera «FORD 14000», «PERKINS 1006.6C/T/TW» y
«PERKINS 1004.4/T», y esas juntas «solo compartían la marca del auto». Ahora entran los de 5
cifras y los que tienen decimal, y cuando traen la versión con barra se toma el número («1006.6»
de «1006.6C/T/TW»). Los que tienen una letra sola pegada quedan enteros: «22R» y «6359D» son
motores que el otro proveedor escribe igual. 5 juntas de cárter salen de revisión, y la de
bomba inyectora «Perkins 1004.4T» deja de concordar con la del «PERKINS 1006», que es otro motor.

## 🎨 Diseño más moderno, con las ayudas plegadas

- **Las ayudas se despliegan.** `explicar()` dejaba el resumen siempre a la vista y el detalle en
  un desplegable aparte: dos renglones por ayuda. Ahora es uno solo, «ℹ️ resumen», con todo
  adentro. Y 49 textos fijos que explicaban una opción debajo de cada cosa (`st.caption` de más
  de 140 caracteres) pasaron a `ayuda()`, igual de plegados. Se dejaron a la vista los que no son
  ayuda: avisos de lo que se borra, estados vacíos, errores y lo que decide una venta («No son
  equivalentes», «Confirmá con el cliente el modelo»). También la línea «para qué sirve» de cada
  sección. Las ayudas se dibujan livianas —un renglón gris que al abrirse muestra el texto con
  una línea de color al costado— para no confundirse con los desplegables que son parte de la
  pantalla, y por eso pueden ir adentro de otro desplegable sin quedar como cajas anidadas (el
  control de auditar.py las exceptúa).
- **Encabezado en una barra** en vez de una tarjeta que ocupaba media pantalla del celular.
- **La navegación es una barra de pestañas de un renglón.** En el celular se desliza de
  costado; antes ocupaba tres renglones. Ojo con el detalle que costó encontrar: los botones de
  radio escondidos de cada opción van con `position: absolute`, y sin `position: relative` en la
  barra ensanchaban el contenedor principal y la página entera se corría de costado al tocar una
  sección de la derecha (medido con Playwright en un celular simulado).
- **Opciones sin el puntito de formulario:** los radios se ven como pastillas y la elegida en
  color.
- **Sin el botón «Deploy»** ni el menú de desarrollador (`toolbarMode = "minimal"`).

## 🏭 Catálogos de fabricantes, solos

Tus listas nombran piezas de fabricantes que no son proveedores tuyos: «BOMBA DE AGUA … SKF
VKPC85304», «BUJIA … NGK= BP5HS», «REF ORIG MANN P 716». En la base real: 402 productos citan 96
códigos SKF, 105 citan 23 bujías NGK y 72 citan 29 filtros MANN. Esos fabricantes publican una
ficha por código con los números originales y las equivalencias de otras marcas.

`leer_catalogo_de_fabricante()` abre la ficha de cada código citado —primero los más citados—
y, si ahí aparece el código de otro producto tuyo, anota el par en `productos_juntos_en_portal`
como «CATÁLOGO SKF». Es una prueba más a favor en `evidencia_cruzada()` («🌐 el catálogo de SKF
los muestra juntos»), igual que el portal del proveedor: no decide nada sola, y los pares que no
estaban van a revisión en su propia lista. La ficha tiene que mostrar el código pedido; si no,
es la portada o un buscador y se anota como «sin ficha». Más de 25 productos tuyos nombrados es
un listado y no cuenta.

**Corre solo**, en la tarea de fondo: hasta 150 fichas por día con 1,5 s entre una y otra. Si un
sitio falla cinco veces seguidas se pausa un día (`catalogo_pausado_…`). Se apaga en Administrar
→ Mantenimiento → «🏭 Catálogos de fabricantes».

Las direcciones salen de fichas reales que publican los buscadores. El servidor donde se armó
esto no llega a esos sitios, así que se probó con un servidor falso local que imita las
fichas: códigos leídos, pares anotados, ficha inexistente (404), sitio caído (se reintenta, y
tras cinco fallas se pausa):

| Fabricante | Ficha por código |
|---|---|
| SKF | `automotive.skf.com/eur/es/product-catalogue/VKMA01250` |
| MANN-FILTER | `mann-filter.com/en/catalog/international/search-results/product.html/w712/95_mann-filter.html` (la barra del código es parte de la dirección) |
| NGK (bujías) | `sparkplug-crossreference.com/convert/NGK_PN/BKR6E`: una tabla de equivalencias de bujías por código NGK; no es de NGK, la ficha oficial lleva un número de stock que no sale del código |

Quedaron afuera FRAM, MAHLE, BOSCH, TARANTO, CORVEN y FISPA, porque sus catálogos buscan con un
formulario o listan por rubro: no hay una dirección por código. E ILLINOIS, que publica un PDF
por juego con las piezas que trae adentro: juntaría cada juego con sus juntas, que no son
equivalentes.

## 🔄 Los «reemplaza a» de las descripciones, cargados solos

La tabla de reemplazos (`reemplazos_codigo`) ya hacía mucho: el buscador sigue la cadena del
código viejo al vigente, la evidencia la usa, y una tarea diaria une lo vinculado al viejo con
el nuevo. Pero se cargaba solo a mano, y en la base real estaba vacía, con 185 descripciones que
lo dicen: «SENSOR MAP 40011 (reemplaza a 40035)», «… REEMPLAZA AL 10044», «Junta tapa de
cilindros - Reemplazada por 272008».

`cargar_reemplazos_de_las_descripciones()` los lee una vez por día (y con un botón en
Estadísticas → 📌 Para pedir → «🔄 Códigos reemplazados por el fabricante»):

- solo de las listas de proveedor: el producto de fábrica copia la descripción de la fila y
  daría el reemplazo con el código equivocado;
- con un código después, que tenga un número y no sea un año: «REEMPLAZO LLAVE DE LUCES» o
  «REEMPLAZA AL AZUL» no son reemplazos de código; «reemplaza a 90021-90022» son dos;
- el código viejo como lo escribe la lista —«40035FISPA», no «40035»—, porque a secas choca con
  otra marca: el «10 107» de JL se unía con el reemplazo del 10107 de FISPA;
- sin pisar lo cargado a mano, sin círculos, y si dos filas dicen reemplazar al mismo código no
  se carga ninguno.

En la base real entran 40 reemplazos, y el cruce propone un par a revisión (Taranto 981308 →
272008).

## 🛒 Mercado Libre: pistas para relacionar y precio de mercado

Con la aplicación de desarrollador cargada en los secretos (`[mercadolibre]` con `client_id` y
`client_secret`; se crea gratis en developers.mercadolibre.com.ar), `leer_mercado_libre()` busca
tus códigos —primero lo que tenés en stock— y se queda solo con las publicaciones que son de ese
producto: el código en el título o como número de pieza, y la marca si no es un código de
fábrica (`publicaciones_de_tu_producto()`). De ahí:

- **Pistas**: si esas publicaciones nombran el código de otro producto tuyo, el par queda en
  `productos_juntos_en_portal` como «MERCADO LIBRE» —«🌐 las publicaciones de Mercado Libre los
  muestran juntos»— y va a revisión. No decide nada solo: el que publica escribe lo que le
  conviene.
- **Precio de mercado**: la mediana de lo publicado en pesos, con al menos dos publicaciones, en
  `mercado_libre_leidos`. Estadísticas → 📌 Para pedir → «💲 Tus precios contra Mercado Libre»
  lista los que están a más de 1,6 veces (elegible), primero lo que tenés en stock.

Corre solo en la tarea de fondo, hasta 200 búsquedas por día, con el token guardado en memoria
hasta que vence. Se prueba y se apaga en Administrar → Mantenimiento → «🛒 Mercado Libre». El
servidor donde se armó esto no llega a la API, así que se probó con un servidor falso que
responde como ella: token, búsqueda, publicaciones ajenas descartadas, pares y precios.

## 🏭 Los códigos de fábrica unen, pero no se muestran

Un arranque de LUCAS que cita 53 números de Bosch salía en el buscador con 53 filas de «MOTOR DE
ARRANQUE…» y el cartel de «sin equivalencias»: los códigos de fábrica son los que unen las listas
de los proveedores, pero no son algo que se venda. Ahora:

- **Buscando por código** se esconden de la tabla —salvo el que se buscó— y no cuentan como
  equivalencias. El aviso dice cuántos cita («Cita 63 código(s) de fábrica…»), y una casilla
  «🏭 Mostrar también los N código(s) de fábrica» los muestra si hace falta. Buscar un código de
  fábrica sigue funcionando igual: lleva a los productos que lo citan.
- **Buscando por descripción** no aparecen (copian la descripción de la fila y salían
  repetidos), salvo que se escriba el código exacto. Tampoco en las equivalencias que se abren
  debajo de cada resultado.

## 📷 Fotos de Mercado Libre y de los fabricantes, para la búsqueda por cámara

La búsqueda por cámara compara contra `producto_fotos`, y en la base real no había ninguna.
Ahora, cuando Mercado Libre trae publicaciones de un producto tuyo, la foto de la primera (la
miniatura en tamaño original, «-O.jpg») queda como la del producto; y cuando la ficha de un
fabricante (SKF, MANN-FILTER, NGK) declara su foto principal (`og:image`), queda para los
productos que citan ese código. Solo para productos sin foto, nunca para los de fábrica, y sin
pisar nada (`proponer_foto()`). La tarea de fondo las baja en modo liviano —queda el link y la
miniatura— y les calcula la firma visual.

De paso, un error de antes: en modo liviano la foto bajada se guarda como el mismo link, así que
`bajar_fotos_pendientes()` volvía a elegir las ya bajadas y las sumaba repetidas en cada tanda.
Ahora solo baja las de productos sin fotos, y un link que no existe queda como `link_roto` para
no reintentarlo siempre.

## ⚡ Sin topes diarios en la carga automática

La tarea de fondo (`_trabajo_de_fondo()` en `logica/proveedores.py`) ya no tiene cupo por día
ni corta a los 10 minutos: corre hasta que no queda nada pendiente. Eso vale para las fotos y
las equivalencias de las fichas del proveedor, los catálogos de fabricante (SKF, MANN-FILTER,
NGK), Mercado Libre, las fotos que esos sitios dejan propuestas y las firmas visuales de la
cámara (que antes iban de a 20 por día). Las pausas entre pedido y pedido bajaron (0,3 s en
los catálogos y 0,15 s en Mercado Libre), y las fotos se bajan de a 6 a la vez.

Lo único que la frena es un **descanso**, que se ve en la pantalla («😴 descansa hasta las …»,
con un botón para que retome ya):

- **30 minutos** si una tarea no encontró nada para hacer, para no mirar la base en cada toque.
- **Una hora** si el sitio falla cinco veces seguidas o falla más de la mitad de una tanda. Sin
  cupo por día este freno es el que importa: las fichas que fallan por la red vuelven a salir
  en la vuelta siguiente, y sin él la tanda giraría sobre las mismas cincuenta golpeando a un
  sitio caído. Solo cuenta como avance lo que quedó resuelto.

Si mientras corre llega trabajo de los que van primero (una lista importada, puntajes por
rehacer), la tanda corta y vuelve a arrancar para hacerlo antes. Las fotos y las equivalencias
de las fichas siguen siendo interruptores que se prenden a mano, porque salen a internet con
el nombre de tu catálogo.

Medido con un servidor falso: los 96 códigos SKF citados en la base real se leyeron en una sola
pasada (antes eran hasta 150 por día); con el sitio caído cortó a los 5 pedidos y se pausó una
hora.

## 🔎 Revisión cruzada: nueve errores que encontró otra IA

Los cambios del día los revisó un agente independiente (otra instancia de Claude, sin el
contexto de la conversación). Encontró nueve errores reales; están corregidos y probados:

1. **La sesión se cerraba apenas se volvía a entrar**: el reloj de inactividad de una sesión
   anterior («Salir» no lo borraba) cerraba la nueva. Ahora sin sesión con contraseña no hay
   reloj.
2. **La búsqueda por número de motor mostraba el titular y el km al invitado** (hasta 50 pares
   patente + cliente con cuatro caracteres). Ahora solo con contraseña, y sin el `_id` interno.
3. **Una copia cifrada escrita en el repositorio mismo dejaba la app vacía al arrancar**:
   `ruta_de_la_semilla()` ahora la descifra.
4. **Restaurar a mano no volvía a pedir las fotos** y dejaba entrar una base dañada. Ahora pasa
   por `la_base_esta_sana()` y `pedir_de_nuevo_las_fotos()`, igual que al arrancar.
5. **Una tanda de 50 links vencidos apagaba la bajada de fotos** con miles pendientes. Ahora se
   apaga solo cuando no queda nada que intentar (cada falla queda marcada, así no gira).
6. **Tareas que no terminaban nunca**: una falla vieja huérfana las dejaba «descansando hasta
   mañana» todos los días. Ahora solo cuenta lo que falló hoy.
7. **`clave_copia` pegada dentro de `[admin_passwords]` funcionaba como contraseña de
   administrador** (`es_un_usuario_de_los_secretos()`).
8. **La columna Stock desaparecía cuando nada tenía stock**: el 0 es un dato, no un vacío.
9. **El recorte del análisis de sugeridas dejaba pares sin ver** cuando la lista no entraba en
   una tanda. Ahora recorta solo si la tanda cubría la lista entera.

### Y dos más, de la revisión con Gemini

La misma revisión se le pidió a Gemini. Con la clave del plan gratis solo respondió el modelo más
liviano (Gemini 3.1 Flash Lite; los Pro no están en el plan gratis y los Flash estaban saturados), y
la mayoría de lo que marcó eran consejos genéricos o cosas que el código ya hace. Dos puntos sí
valían:

- **Una vez que hubo contraseñas, la app no se abre sola** (`hubo_claves` en
  `hay_claves_configuradas()`). Si un día Streamlit no pudiera leer los secretos, la app creía
  que nunca se configuraron y abría todo, backups incluidos.
- **La frase de la copia se estira con 600.000 vueltas de PBKDF2** (lo que recomienda OWASP),
  no 200.000. La copia lleva la versión en la marca del principio (`CHAVO-COPIA-CIFRADA-2`), así
  que las copias ya subidas con la versión 1 se siguen abriendo.

### Ideas de usabilidad de Gemini, mirando capturas

A Gemini 3 Flash se le mandaron capturas del buscador en un iPhone y de la revisión de
sugeridas (sin datos de clientes). De sus diez ideas se tomaron las que no estaban ya hechas y
cambian el trabajo diario:

- **Tarjetas en el celular** (`mostrar_tarjetas_de_resultados()`): marca y código, precio en
  negrita y el stock con color —🟢 hay, 🔴 no hay, ⚪ sin dato—, porque se mira de reojo
  mientras se habla con el cliente. La tabla queda a un toque («📋 Ver como tabla»).
- **En la revisión, en negrita lo que difiere** (`resaltar_lo_que_difiere()`): los datos con
  números que la otra descripción no dice («1968CC», «16V», «1,55MM»). «1.4CC» y «1,4» cuentan
  como el mismo dato. Las palabras sin números no se marcan: casi siempre son abreviaturas del
  proveedor.
- **Filtro por marca en la búsqueda por descripción**: «sensor rotacion ford» son 197 filas de
  tres listas; el selector dice cuántas hay de cada una («CRI-FA (86)»).
- De una segunda tanda, mirando Mantenimiento, Estadísticas y Vehículos:
  - **Números con punto de miles** en todas las métricas (`miles()`): 85.705, no 85705.
  - **El gráfico de marcas horizontal y ordenado**: parado, los nombres salían girados y cortados.
  - **«Uso de IA» solo si se usó**; antes era una sección entera para decir «todavía nada».
  - **El aviso de «sin contraseña» en palabras simples**, sin «Secrets» ni «[admin_passwords]».
  - **Crear la primera contraseña ya no es un callejón sin salida**: Usuarios pedía una contraseña
    de administrador que todavía no existía, y el aviso mandaba justo ahí.
  - **En Vehículos, la patente a la vista**: «A quién avisar» y «Mantenimiento atrasado» van
    plegados (el título dice cuántos hay) en vez de empujar la búsqueda abajo.
- Y de la revisión de la tarea de fondo: **el caché de fichas tiene tope de tamaño** (40 MB),
  no solo de cantidad; 400 fichas grandes podían ocupar más de la mitad de la memoria del
  servidor.

### El buscador, revisado por otra IA

Un revisor independiente (Claude, sin el contexto de la conversación) comparó el buscador contra
un recorrido de referencia sobre 600 códigos al azar —daba lo mismo— y encontró siete errores en
los bordes, reproducidos sobre la base real. Corregidos:

1. **Con filtro de marca, el reintento del cero traía otra pieza**: «041064» (una lente de CRI-FA)
   filtrando por IMPERIAL devolvía el 41064 de IMPERIAL, de Toyota. Ahora el cero se prueba solo si
   el código no existe en ninguna marca, y eso tampoco se anota como «búsqueda sin resultado».
2. **El mismo código en otra marca se perdía justo en el tope**: con «Solo directos», la bujía
   TARANTO BKR6EZ no salía y la pantalla decía que nadie más la tenía. La rama «mismo código» no
   suma saltos, así que va con `<=`.
3. **«Hay 64 equivalencias más» y no aparecía ninguna**: contaba códigos de fábrica que la pantalla
   esconde. Ahora es la diferencia entre la búsqueda sin tope y la que se ve, con las mismas opciones.
4. **Tocar un código desde otra lista buscaba con toda la cadena**, sin mirar las opciones (38
   filas en vez de 15). Ahora usa las elegidas (`opciones_de_busqueda_actuales()`).
5. **Los códigos de motor cargados como de fábrica (K4M700, F4R770) hacían de puente**: buscando un
   motor paso a paso salía una bomba de agua «a 2 saltos». La búsqueda no sigue por ellos
   (`GLOB_DE_MOTOR_CON_INDICE`), salvo que sea lo que se buscó.
6. **La búsqueda por descripción con un símbolo suelto** («QQQZZZ °») devolvía 200 productos
   cualquiera: aflojaba a «cero palabras».
7. **La confianza y la cadena mostradas salen del mismo camino**: el de mejor confianza y, de esos,
   el más corto. Antes se podía ver «🟢 directo · 🟢 sólida» sobre un vínculo directo muy débil.

Y dos menores: los códigos de fábrica van al final de cada nivel (el tope de 400 ya no recorta
proveedores), y si se llegó por la variante del cero o el código de barras, «le sirve a qué
autos» y «hay más» usan el código encontrado.

### Importar una lista, revisado por otra IA

El mismo revisor pasó por la carga de listas con planillas armadas para cada caso, y encontró
diez errores. Todos reproducidos antes y comprobados después:

1. **«Aplicar igual esos precios» no aplicaba nada**: el botón vivía adentro del toque de
   «Procesar», así que al tildar «Revisé la lista» desaparecía. Ahora los frenados quedan
   guardados en la sesión y se aplican (o se descartan) desde afuera.
2. **Un precio 0 pisaba el precio real** y encima el freno de saltos no lo miraba: el repuesto
   quedaba a $0. Ahora 0 o negativo es «sin precio», y si el guardado ya estaba en 0, el freno
   se compara con el último precio de verdad del historial.
3. **El mapeo recordado se aplicaba por posición** aunque el proveedor hubiera movido las
   columnas: el código quedaba apuntando al precio. Ahora se guardan los títulos y se reubica por
   título; si aun así no cuadra con los datos, se usa la detección automática
   (`reubicar_mapeo_por_titulos()`, `problemas_del_mapeo()`). Precio y stock en la misma columna
   no deja importar; un código que parece un importe o que repite siempre lo mismo pide confirmar.
4. **La fila de títulos y la hoja quedaban pegadas de un archivo al otro**: la lista sin tapa se
   leía desde la fila 3 y perdía dos productos. Se reinician al cambiar de archivo
   (`identidad_del_archivo()`).
5. **El proveedor propuesto quedaba pegado**: «Usar otro archivo», subir la de MAHLE, y se
   importaba como ILLINOIS. Lo que propuso la app se vuelve a proponer; lo que escribiste, no.
6. **Títulos que engañaban**: «DESCUENTO %» como descripción, «PESO NETO» como precio,
   «CANT. X BULTO» como stock, «ORIGEN» (CHINA, BRASIL…) y «FABRICANTE» como código de fábrica.
   Las pistas van al principio de palabra y hay una lista de las que no son (`PISTAS_QUE_NO_SON`).
7. **La importación no era todo-o-nada**: cortada a la mitad, quedaban precios pisados sin
   vínculos ni registro para deshacerla. Ahora va en una transacción: probado cortándola en la
   fila 25, no quedó nada a medias.
8. **Cada toque releía el Excel entero dos veces**: con 30.000 filas, 5,2 s por toque. Ahora se
   lee una vez por archivo (0,0 s después). Y la importación de esa lista bajó de 31,5 s a 5,5 s:
   25 s eran el análisis de los vínculos nuevos, que en listas de más de 6.000 corre por atrás y
   en las demás queda guardado para que «Equivalencias sugeridas» abra al instante.
9. **Deshacer una lista no sacaba los pares que ya esperaban revisión**, que el cartel contaba
   como nuevos; y el lote tenía minutos sin año, así que dos importaciones del mismo minuto
   compartían etiqueta. Ahora esos pares se cuentan aparte y el lote lleva año y segundos.
10. **Números mal leídos**: «2 x 1.500» era 21.500, «1.5E+3» era 1,53, «$ -100» era positivo y
    una fecha entraba como precio. `leer_numero()` los resuelve o devuelve «sin número».

Y uno más que salió probando: si la lista trae el mismo código dos veces con precios distintos
(unidad y caja), ahora se avisa con ejemplos.

### Auditar lo ya cargado: los originales no cuentan

- **«Productos con muchísimos vínculos» ya no cuenta los códigos originales.** Un burro de
  arranque que reemplaza a 30 números de Bosch es una pieza completa, no basura. Ahora cuenta
  solo los vínculos con productos de otras marcas de repuesto (10 o más), y los originales
  se muestran aparte como dato. El botón sigue cortando todos.
- **La revisión ya no queda corta.** Miraba 20.000 vínculos y la base tiene más: lo último
  cargado no se revisaba nunca. Ahora mira hasta 150.000 (`VINCULOS_QUE_MIRA_LA_AUDITORIA`).
  Los 32.960 de la base de prueba tardan 1,4 s, y con eso apareció arriba «JL · CHAPA», basura
  real pegada a 75 cables, que el tope escondía.
- **Las descripciones sin `<br>` ni `<b>` escritos**: `texto_para_html()` pasa los saltos a « · »
  y saca las etiquetas de formato que traen algunas listas.

### Elegir en los abanicos: lo que distingue a cada opción, a la vista

En «🪭 Elegí cuál es la equivalente», arriba de las opciones de cada producto va una tabla
(`tabla_del_abanico()`): el producto y cada candidato con sus modelos en común, años, motor,
cilindrada, largo de cable, vías y espesor, con ⚠️ donde los dos dicen algo distinto. Antes
cada opción era «código — los primeros 80 caracteres», y lo que separa una junta de otra (el
motor, el espesor) o una sonda de otra (el cable, los años) casi siempre está al final. Las
columnas que ninguna opción tiene no se muestran, para que entre en el celular.

### ¿Qué tan bien acierta la app? Medido con lo que decidiste

En Estadísticas → 🔗 Equivalencias sugeridas, plegado: «📏 ¿Qué tan bien acierta la app?»
(`aciertos_de_la_revision()`). Tres tablas:

- **Muestras de control**: de los «limpios» sorteados al azar que revisaste de a uno, cuántos
  estaban mal, por origen (lista importada o automático) y franja de confianza, con el techo de
  error del grupo al 95 % (con 0 mal en 30 el grupo puede tener hasta 11 %).
- **Por confianza**: lo que decidiste según cómo lo había puntuado la app. Incluye lo aprobado
  en bloque, así que el verde sale mejor de lo que es.
- **Por alarma**: de lo que cada alarma mandó a revisión, cuánto aprobaste igual. La alarma
  que se equivoca seguido es la regla para ajustar.

Para las dos últimas, `marcar_revision()` anota ahora la confianza y la primera alarma que tenía
el par en la pantalla de revisión al decidir (columnas nuevas `confianza` y `senal` de
`equivalencias_revisadas`). Lo decidido antes cuenta solo en las muestras.

### Una prueba que cuida lo que ya revisaste

`pruebas_de_la_revision.py` deja escrito lo que se aprendió revisando la cola a mano, para que
la regla siguiente no lo rompa sin que se note:

- **Pares de muestra**: 20 pares reales, cada uno con lo que tiene que dar —«misma» o
  «distinta»— y de dónde salió. Se corre con una base vacía en una carpeta temporal, así que
  nunca toca la de trabajo. Los que dependen de modelos de auto se prueban solo con una base,
  porque los modelos la app los aprende del catálogo.
- **Con `--base copia.db`**: pone todos los pares que aprobaste como si recién llegaran —sin tus
  decisiones ni lo aprendido de ellas— y los puntúa. Falla si más del 1 % cae en rojo. Sobre la
  base de prueba: 13.021 aprobados, 12.853 limpios, 86 en rojo (0,7 %, vínculos por códigos que
  hoy ya no se tomarían).

Probada rompiendo la regla de motores a propósito: falla y dice cuál par se rompió
(«Deutz F4L contra F5L: tenían que ser piezas distintas y dio que concuerdan»).

### Los años y los motores también dicen «son otra pieza»

Siguiendo con la revisión a mano de la cola, dos datos que las descripciones traen y el análisis
no miraba:

- **Los años** (`rangos_de_anios()`): todos los rangos que escribe cada descripción («1984/1989»,
  «2013/...», «2005>2013»), no solo el primero. Si las dos escriben rangos y ninguno se cruza, son
  de autos distintos: «HONDA CIVIC … 1984/1989» contra «HONDA CIVIC 2015/... L15B8», «Transit
  2016/2022» contra «Transit 2004-2006». El año suelto no cuenta: «J.DEERE 2030» es un tractor.
- **Los motores** (`motores_de_la_descripcion()`): los códigos con forma de motor de la parte que
  habla del auto, sin las referencias del final («// …B1C/B1B», «REF ORIG», «NGK= BP5HS»), sin el
  código del propio producto y sin contar bujías. Si las dos nombran motores y no comparten la
  familia (G10BB, G10A y G10T son G10; D4F y D4K son D4) ni el catálogo los declara juntos, son
  de motores distintos: cárter Deutz F4L contra F5L, junta de tapa Master G9U contra S8U, Sonata
  D4EA diésel contra G4KA nafta.

Los dos cuentan como motivos «del auto»: si los une un código, el código manda (un inyector
ICD00107 de un Corsa 1993 y uno de un Corsa 1999 son el mismo).

Sobre la cola de prueba: 28 pares que estaban en 🟢/🟡 pasan a 🔴 —revisados uno por uno, todos
son otro motor u otra época— y 12 dudosos más también. 22 dudosos suben a 🟢 porque, al caerse
los de otro motor, quedan como el mejor candidato (juntas de Daily/Ducato, bobinas de Twingo).
Las 13.021 aprobaciones siguen con el mismo puntaje y lo ya cargado no cambia.

### Los dudosos, revisados uno por uno

Se tomaron los 3.595 pares «🟠 dudosos» de la cola de prueba y se revisaron muestras a mano,
leyendo las descripciones enteras. Dos cosas que decían «son piezas distintas» y el puntaje no
escuchaba:

- **Misma marca de auto, ningún modelo en común.** «Sonda Lambda Volkswagen Gol Fox Voyage
  Saveiro Suran» contra la LUCAS de «GM Astra Celta Corsa … VW Golf» compartían VOLKSWAGEN y nada
  más, y quedaban en 50, como si faltara un dato. Cuando las dos nombran modelos y no comparten
  ninguno, ahora es «modelos distintos» (salvo marcas de motores como Perkins o MWM, donde un lado
  nombra el motor y el otro el vehículo).
- **Juntas de lugares distintos aunque compartan una sola palabra.** «Junta Caja JHON DEERE»
  contra «JTA T.C. J.DEERE» (caja contra tapa de cilindros) cortaba antes por «solo comparten 1
  palabra», que no descarta. Y la junta de caja de velocidades cuenta como lugar (no la «caja de
  admisión», que es el múltiple).

Resultado sobre la cola: 163 dudosos pasan a 🔴 (las 12 muestras revisadas estaban todas mal) y
12 pasan a 🟢 porque quedaron como único candidato. Las 13.021 aprobaciones de la base de prueba
quedan con el mismo puntaje, y lo ya cargado que «hoy se vetaría» sigue igual (78).

Se probó y se descartó un tope más: bajar a amarillo al que queda como único candidato después
de los vetos. Bajaba 1.029 verdes, y revisando una muestra casi todos estaban bien.

Lo que sigue dudoso es dudoso de verdad: 2.272 pares cuyas descripciones concuerdan pero el
producto de enfrente concuerda con varios de la misma lista (como mucho uno es el equivalente,
y la pantalla deja elegir cuál), y 691 donde una de las dos descripciones no nombra ningún modelo.

### Un juego de juntas no es la junta de tapa de cilindros

«Jgo.Jtas. ROVER 214/216/218» salía entre las «limpias» emparejado con «JTA T.C. ROVER 111/214»:
el juego completo con la junta de tapa sola. El juego se reconocía como kit, pero como no decía
«completo» ni «superior» quedaba sin tipo, igual que una junta suelta. Ahora:

- Un juego de juntas que no dice cuál es cuenta como juego (`JUEGO_SIN_DECIR_CUAL`): nunca es
  equivalente de una junta suelta, y con otro juego no choca, porque puede ser cualquiera
  (`juegos_que_chocan()`).
- «Juego de juntas de tapa de cilindros» es el juego superior (el de descarbonización), así que
  tampoco se empareja con el completo. «Sin TC» se mira antes, para no confundirlos.
- Los juegos de carburador quedan aparte, como antes.

Sobre la cola de prueba: 110 pares juego contra junta suelta estaban entre las limpias; ahora
ninguno (395 van a sospechosas y 3 a relacionadas). Lo ya aprobado con esa regla vieja aparece en
«Revisar lo aprobado con las reglas de hoy».

### Auditar lo ya cargado: que cuadre, no cuántos

- **«Muchos vínculos» dejó de ser la señal.** Una sonda lambda que va en 60 autos y cita 7
  originales tiene, con razón, 15 equivalentes de otras marcas, y salía primera como basura.
  Ahora un producto aparece solo si al menos 5 de sus vínculos (y el 40%) **no son la misma
  pieza**: otro rubro, autos sin nada en común, otra posición, cilindrada o tipo de sensor
  (`vinculos_que_no_cuadran()`). Un vínculo cuadra seguro si los dos citan el mismo original.
  Sobre la base de prueba: de 30 productos marcados queda 1, JL · CHAPA, con 37 de sus 75
  cables de otros autos, y se pueden cortar solo esos 37 dejando los buenos.
- **Un original apuntando a varios productos de la misma lista** tampoco es error por sí solo:
  la lista de FISPA trae piezas FISPA y LUCAS, y un 40027FISPA y un LEMSM022LUCAS con el mismo
  original son equivalentes. Ahora salen solo los que se contradicen o mezclan un juego con una
  pieza suelta (`_por_que_chocan()`), con el motivo a la vista: de 2.466 a 391.
- Las descripciones largas se muestran cortadas: una de FISPA ocupaba la pantalla entera.

### ¿Aguanta 60 proveedores? Probado con una base de 63

Se armó una base copiando 8 veces los 7 proveedores reales (63 proveedores, 658.977 productos,
117.189 equivalencias cargadas y 137.763 pendientes, 275 MB) y se midió todo:

| | Hoy (7 proveedores) | 63 proveedores |
|---|---|---|
| Buscar un código | 0 ms (peor 19 ms) | 0 ms (peor 24 ms) |
| Buscar por descripción | 44 ms | 363 ms |
| Abrir Administrar | 0,5 s | **20,2 s → 1,0 s** (cada toque 16,6 s → 0,1 s) |
| Importar 10.000 filas | — | 7–13 s |
| Copia a GitHub | 13 MB | 58 MB (el tope de GitHub es 100 MB) |

Lo que no aguantaba, y se arregló:

- **Administrar**: `marcas_probablemente_duplicadas()` hacía una consulta por par de marcas
  (2.016 con 64) en cada toque. Ahora es una sola y se guarda hasta que cambian productos o marcas.
- **La búsqueda automática de después de importar** rehacía todo el catálogo en cada lista:
  22 minutos con 63 proveedores y picos de 3,6 GB. Ahora cada paso trabaja solo con lo nuevo
  (medidas, aplicaciones, cruce por auto y barrido guardan hasta dónde llegaron), el cruce por auto
  usa un índice y tiene tope de tiempo, el barrido no guarda los pares ya vistos y rehace las
  firmas solo de lo que cambió, y los modelos de las 65 marcas de auto salen de una sola pasada.
  Cada cambio se comparó con el anterior sobre la base de hoy: mismos resultados.
- **Escrituras de a una**: las aplicaciones deducidas se confirmaban fila por fila (172 s → 42 s).
- **La copia**: el cuerpo de la subida se arma en bytes; antes el base64 existía cuatro veces en
  memoria.

Lo que sigue siendo pesado con 63 proveedores es la búsqueda automática en sí: unos minutos de
procesador por lista importada (corre por atrás) y alrededor de 2 GB de memoria en el barrido.
Con ese tamaño conviene un servidor con más memoria que el gratuito de Streamlit.

### Preparada para crecer: barrido con interruptor, búsqueda en una pasada, copia en partes

- **El barrido de todo el catálogo se puede apagar.** En el panel de carga automática hay un
  interruptor nuevo: «Después de importar, barrer todo el catálogo…» (config
  `barrido_automatico`, prendido por defecto). Es lo que más memoria pide (unos 2 GB con 63
  proveedores). Apagado, el resto de lo de después de importar sigue igual, el informe lo dice, y
  el barrido se corre a mano desde Administrar → Mantenimiento → «🧠 Buscar en todo el catálogo».
- **Buscar por descripción recorre la tabla una vez.** Las coincidencias se contaban dos veces
  (en el SELECT y en el WHERE), y si no aparecía nada con todas las palabras se volvía a recorrer
  todo pidiendo una menos. Ahora se trae de una lo que llega al mínimo aflojado y el mínimo de
  verdad se aplica después. Comparado con la versión anterior en 14 búsquedas: mismos resultados
  en las dos bases; con 63 proveedores, mediana de 365 a 333 ms y la peor de 594 a 450 ms.
- **La copia a GitHub puede ir en partes.** GitHub no acepta archivos de más de 100 MB; hoy la
  copia con 63 proveedores pesa 58 MB. Si pasa de 90 MB (`TOPE_DE_UN_ARCHIVO_EN_GITHUB`) se sube
  en pedazos de 45 MB (`partes_de_la_copia()`): `archivo.parte1`, `.parte2`… y `archivo.partes`,
  un índice con cuántas son, cuánto pesan y su huella SHA-256. Al arrancar,
  `bajar_la_copia_de_github()` busca el archivo único y, si no está, junta las partes; si falta
  una o no da la huella, no la usa (arranca con la del repositorio, como con cualquier copia
  fallida). Probado contra un GitHub simulado con partes de 3 MB: sube 4 partes + índice, baja y
  abre con los mismos 70.893 productos; con una parte alterada o faltante no restaura nada; y
  cuando la copia vuelve a entrar en un archivo, la rama queda con el archivo solo. El LEEME de
  la rama explica cómo pegarlas a mano.

### Lo ya aprobado se revisa solo con las reglas de hoy, y se avisa arriba

Midiendo las 13.021 aprobaciones de la base de prueba con el análisis de hoy, 86 caen en rojo, y
mirándolas una por una casi todas están mal de verdad: una junta de tapa de cilindros unida a una
bujía por el código de motor 4JB1TC, poleas de 54 contra 48,8 mm, un motor paso a paso unido a
una bomba de agua de otro auto. Se aprobaron en bloque antes de que existieran las reglas de
rubros, medidas y «ese código es un motor», y el buscador las sigue mostrando como equivalentes.

«🔁 Revisar lo aprobado con las reglas de hoy» ya las encontraba (78 de las 86; las otras 8 son
de «un código apunta a varios productos de FISPA», que se mira por lista y no por par), pero había
que apretar el botón, y está al final de la pantalla. Ahora:

- **La tarea de fondo la corre sola** (`revisar_lo_aprobado_por_atras()`) cuando cambia el código
  de la app (una huella de los archivos de `logica/`) o cambian los vínculos cargados, en ese caso
  como mucho cada 30 minutos (`MINUTOS_ENTRE_REVISIONES_DE_LO_APROBADO`). Son 7 s con 13.021
  vínculos, cediéndole el paso al mostrador cada 500. Guarda un resumen en la configuración.
- **Arriba de 🔗 Equivalencias sugeridas** sale el aviso con cuántos son y los tres motivos más
  comunes, sin revisar nada al dibujar la pantalla. «🔁 Ver cuáles y resolverlos» los muestra ahí
  mismo, agrupados, con «✂️ Cortar» y «✅ Están bien» por grupo, y el aviso se actualiza con lo
  que se resuelva. Probado en la app: 78 → cortando un grupo de 5 → 73.

### La supermedida no es la estándar

En la revisión salía sin alarmas TARANTO 250006 «Jta.Tapa Cil.Superm. FIAT 1100» con ILLINOIS
TC-206-15, la junta estándar del mismo motor: todo coincidía —rubro, marca, modelo— y nada
miraba que una es para motor rectificado. Ahora la firma anota la sobremedida
(`sobremedida_de()`), escrita como la escribe cada lista: «Superm.» (TARANTO), «SOBREMEDIDA»,
«SUPERMEDIDA» o «SUPERME» cortado (ILLINOIS, IMPERIAL), «s/m» (JL), o la medida: «+ 0,5»,
«+0,7», «+0.030». «O.S.» no, porque «OS3573» es un código de Vernet; y si dice también «STD» es
una línea entera y no cuenta.

- **Motivo nuevo, «sobremedida distinta»** (`sobremedidas_que_chocan()`): una dice sobremedida y
  la otra no (nadie vende una sobremedida sin avisarlo), o las dos dicen cuánta y no es la misma.
  Es de los que contradicen, así que el par va a rojo, y no es un motivo «del auto»: corta aunque
  los una un código, porque la supermedida suele citar el número original de la estándar.
- En la base real reconoce 75 productos, todos sobremedida de verdad. En la cola de prueba corta
  17 pares, todos juntas supermedida de TARANTO contra la estándar de ILLINOIS o IMPERIAL. Entre
  los vínculos ya cargados no había ninguno, y las 13.021 aprobaciones dan igual que antes.
- **En la tabla del abanico**, columna «Medida» cuando alguna opción es sobremedida, con ⚠️ en
  las que no coinciden con el producto.
- `pruebas_de_la_revision.py` suma el par: la 250005 con la TC-206-15 es la misma; la 250006, no.

### SPRINT no es lo mismo en cada marca, y la tapa superior no es la lateral

Dos pares que salían sin alarmas en la revisión de TARANTO contra ILLINOIS:

- **«Junta Tapa Valvulas MWM SPRINT 4.07»** (el motor MWM Sprint) contra la tapa de válvulas del
  «FORD FALCON … 221 SPRINT» y la del «CHEVROLET SPRINT SWIFT». La regla de «marcas distintas»
  no corta cuando una es marca de motores (una junta de MWM va en una S10 o en una Ranger: ver
  `_MARCAS_DE_MOTORES`), y lo único en común era SPRINT. Ahora, si las marcas no se cruzan y lo
  único que comparten es un nombre de modelo, no concuerdan: «un nombre de modelo de marcas
  distintas». Va a **revisión y no a rojo** (`_MOTIVOS_QUE_AVISAN`): sobre la cola, lo demás que
  agarra es «FORD F100» contra «PERKINS F100», la misma camioneta, que puede tener el mismo motor
  o no. En la cola de prueba cambian 7 pares, los 7 de esos. Con un motor o un número en común no
  se corta, y como es un motivo «del auto», tampoco si los une un código.
- En revisión, esos pares muestran el motivo en vez de «🤷 Nada dice que sean la misma pieza»:
  `evidencia_cruzada()` lo pasa en el veredicto cuando no hay nada a favor.
- **«Junta Tapa de valvulas superior Mercedes Benz OM352»** contra la «Tapa de Válvulas Lateral»
  del mismo OM352: son dos tapas distintas. SUPERIOR contra LATERAL es ahora «posiciones
  distintas». LATERAL no pasó a ser una posición más, a propósito: «soporte motor lateral
  izquierdo» y «soporte motor izquierdo» son el mismo soporte.
- `pruebas_de_la_revision.py` tiene una tercera respuesta posible, «dudosa» (no concuerdan pero
  sin un motivo que contradiga), y suma los tres pares.

### El bulbo de F100 no es el de Aveo: marcas de motor, colores y presión

CRI-FA 32-42371 «Bulbo presion de aceite Ford F100 F250 F4000 … Cargo … Cummins Mwm 0.40 BAR …
ANTES ERA TAPON NEGRO» salía sin alarmas contra el 349FISPA (Chevrolet Aveo, Cruze, Tracker) y
con 75 contra el 358FISPA (Escort, Gol, Polo: 0,5 bar). Tres agujeros:

- **La marca de motores salvaba aunque el mismo lado nombrara un vehículo.** Cummins y MWM hacían
  que FORD contra CHEVROLET no se comparara. Ahora `_marcas_que_se_cruzan()` deja pasar la marca
  de motores solo si ese lado no nombra también un vehículo. Si además comparten un nombre de
  modelo («PERKINS CASE 580H F350 VW680» contra «FORD F350»), no se corta: va a revisión.
- **ERA, FAE, VERNET, ANTES, ELECTRONICO se habían aprendido como modelos de auto** («Vernet
  OS3573 ERA 330366 FAE 12436», «ANTES ERA TAPON NEGRO»), y ERA era el «modelo en común». Van a
  `_PALABRAS_QUE_NO_SON_MODELOS`.
- **Los colores contaban como algo del auto**: «aislante NEGRO» contra «tapón NEGRO» salvaba de
  «modelos distintos». Pasan a `_RUIDO_EN_FIRMA`, afuera de las dos preguntas. Probado ponerlos
  del lado de la pieza: «aro GRIS» contra «aro NARANJA» hacía que dos inyectores «no coincidieran
  en qué pieza es», y se descartó. En la cola, sacarlos sube 6 bulbos bien emparejados que el
  color frenaba y baja a revisión 10 que solo compartían el color y la marca.
- **Motivo nuevo, «presiones distintas»** (`presiones_en_bar()`): la presión en bar como la escribe
  cada lista —«0.40 BAR», «1.40 Bar», «3BAR» y FISPA con espacio en vez de coma, «0 5 BAR»—. No
  toma «M3 3BAR» como 33 ni los rangos de un sensor continuo («0-7 BAR», «0-10 bar»). Si las dos
  la dicen y no coincide (0,05 de tolerancia), rojo. En la cola corta 14 pares: bulbos de 0,3
  contra 0,4, 0,5 contra 0,35, el aforador diésel de 0,2 bar contra el de nafta de 3. De las
  13.021 aprobaciones pasa a rojo una: la bomba Bosch 0580464981 de 4 bar contra el aforador
  23183 de 3 bar.
- `pruebas_de_la_revision.py` suma los dos pares del bulbo.

### Revisando a mano los «sin alarmas» del barrido

En vez de esperar la próxima captura, se leyeron a mano 80 pares al azar de los 2.446 que el
barrido dejaba limpios. Unos 10 estaban mal. Una segunda muestra de otros 60, con los arreglos ya
hechos, dio 4, y de esos salieron las últimas reglas:

- **Deutz dice los cilindros en el nombre**: F3L, F4L, BF6L, BF4M (`_RE_CILINDROS_DEUTZ`). «Jta.
  Carter DEUTZ F4L 913» concordaba con los cárteres del 913 de 5 y de 6 cilindros.
- **«Wb» es Weber** en JL: «JUNTAS FORD ESCORT/ CHEV ETTE 1.6 Wb» es de carburador y concordaba
  con la junta de cárter del Chevette. Contra «WEBER» no choca: se normaliza.
- **«JUNTA MPI»** (JL) es la de la inyección, y concordaba con la de tapa de cilindros del mismo
  Tempra. Una junta que dice MPI, SPI o TBI y ningún otro lugar pasa a ser de INYECCION.
- **La cilindrada en litros** («CHEROKEE 4 l», «2,5 L», «2.0 lts») y **con el combustible atrás**
  («HILUX 2200 D», «GACEL 1600 DIESEL», hasta 3900: «FORD TRACTOR 6600» es un modelo). No toma
  «HILUX 2L» (el motor 2L de Toyota) ni «F4L». De paso, el formato de FISPA con la L pegada
  —«ASTRA 1 8L 2 0»— ya no pierde el 1,8.
- **Los años de FISPA con dos cifras**: «FOCUS 2 0L MFI 05 -11» es 2005-2011. Con espacio antes
  del guion es siempre un rango; «03-97» sin espacio es mes y año y no entra.
- **Nafta contra diésel** (`combustible_desde_descripcion()`, que ya existía y el análisis no
  usaba; suma DURAMAX): «Termostato … S10 2.2 … Naftero» concordaba con el de la S10 Duramax.
  Solo en los rubros del motor (`_RUBROS_QUE_DEPENDEN_DEL_COMBUSTIBLE`): un sensor de velocidad
  suele ser el mismo en las dos versiones. Es motivo «del auto»: si los une un código, no corta.
- **El bulbo del reloj contra el de la luz**: «Bulbo de temperatura crítica» (el testigo) contra
  «BULBO DE TEMPERATURA RELOJ» (el indicador). Son dos piezas aunque los dos sean de temperatura.
- **Los puentes Dana**: «DANA 70» no es el «DANA 44».

Sobre la cola de prueba: 66 pares pasan a rojo (23 desde verde) y 9 pasan a verde, que el
abanico o una cilindrada mal leída frenaban y están bien. Queda uno conocido: el termostato de
«Transit 2023» contra el del Focus 05-11, porque un año suelto no se toma como rango (a
propósito: «J.DEERE 2030» es un tractor). Las 13.021 aprobaciones no cambian.
`pruebas_de_la_revision.py` suma los 9 pares.

### Todos los amarillos y rojos de la cola, mirados uno por uno

Se leyeron todos los amarillos (584) y los grupos de rojos que quedaban sin revisar, par por par. Lo
que el texto de las dos listas decide pasó a regla; lo que no decide quedó en revisión con el
motivo escrito, en vez de «sin alarma puntual».

**Códigos de fábrica que no lo eran**
- 🔎 **Sacado del medio de la descripción**: los ~150 de la cola eran motores o modelos
  (OM651.901, 4JB1TC, THD100, 19320E, DEERE1104) o el número de otra pieza. Ahora es rojo, no
  amarillo. También cuando la fila no trae números al final y el código está en el tramo de la
  cilindrada y los motores (`_codigo_en_el_tramo_de_los_motores()`, solo con la forma de ILLINOIS
  y solo códigos con letras: K4JK4M, 61-G10-G10T, 700-E800).
- **JC-MAT.15** (el material) y **F100-350** (la gama de Ford) salen del extractor.
- 🏷️ **La marca pegada adelante** —«AGCO SISU POWER836120129», «JOHN DEERER43413», «M.
  BENZ3120150080»— no es un error del vínculo: el número es el de la pieza, mal escrito. El
  extractor ya lo despega (`despegar_marca_de_adelante()`), y **Mantenimiento → 🧹 → «Códigos de
  fábrica con la marca pegada»** corrige los que están: sobre la base de prueba, 169, y 34 se
  juntan con el número limpio que ya estaba. No se borra nada.

**Un número de fábrica que la misma lista le pone a piezas distintas** (⚠️, rojo)
El 36866416 de ILLINOIS es a la vez una junta de escape, una de cárter y un adaptador; el
E30110271 de Mazda, la de escape, la de tapa de válvulas y la de tapa de cilindros; el 4089998
de Cummins, el juego de descarbonización y el inferior. Aprobarlos las haría equivalentes. Se
mira el lugar de la pieza, el sustantivo (solo en las filas de ILLINOIS, que ponen el número
como suyo; FISPA lo cita: la rampa nombra el de sus inyectores), el tipo de juego y «chica»
contra «grande». Se miran también los vínculos ya aprobados y los de las otras listas de la
cola: el aforador de BMW aprobado hace rato es lo que muestra que los dos kits que citan su
número son kits (van a «relacionadas»). Si la misma lista pone el número en piezas iguales
—la misma junta para otro motor, otro material, otra cantidad de cilindros—, no hay alarma.

**Lo que ya decía el texto y no se leía** (rojo)
«CARTER YF» y «CARTER RBS» son carburadores Carter; «JTA LAT.CARTER» es la tapa lateral;
«69/73» y «74/9» son años; el aro gris no es el aro verde (inyectores y sensores); Sigma no es
Rocam (no en sensores, que nombran varios motores); el termostato «para carcaza» no es el
«completo»; un kit no es la pieza suelta (fuera de las juntas, y sin contar el kit que trajo el
número de fábrica); espárragos de 10 contra 8 mm; diámetro de cilindro 119 contra 115 mm;
«RAD.ACEITE» es el radiador; el codo no es la bomba; TEIE es un Solex; la base del carburador no
es el juego de juntas del carburador, ni la intermedia.

**Lo que sube**: un producto de fábrica contra otra fila que lista ese número entre los suyos
—«(4309957/5957865/4444452)», «// 3281721»—, sin ninguna alarma, va a 90: es la misma
declaración que la del vínculo de origen (`el_codigo_esta_entre_las_referencias()`).

**Lo que queda en revisión, con el motivo**
- 🪭 Con **dos** candidatos distintos ya se elige el que mejor coincide, pero solo en los
  amarillos (los verdes no se tocan: ver `PRODUCTOS_DISTINTOS_PARA_ABANICO`).
- 🪞 **Mellizos de la otra lista**: «Jgo.Jtas.Carburador FIAT 125» es la descripción de tres
  productos de TARANTO; el texto no dice cuál. Las variantes de material de IMPERIAL
  («4505CG1», «4505AD4») son la misma junta y no cuentan (`codigo_base_sin_variante()`).

**Medido sobre la cola de prueba** (14.200 pares entre las cuatro bandas):

| | antes | después |
|---|---|---|
| 🟢 | 4.077 | 4.134 |
| 🟡 | 584 | 176 |
| 🟠 | 4.873 | 4.756 |
| 🔴 | 5.546 | 5.788 |

y 216 pasan a «relacionadas» (kits y accesorios del número). Las 13.021 aprobaciones: 82 en rojo
(0,6 %; eran 87). Los 176 amarillos que quedan son pares donde solo concuerda el texto, sin
número ni medida que lo confirme: mirados a mano, la gran mayoría están bien, y los que no se
pueden decidir con lo que dicen las listas son de dos clases —un genérico de TARANTO contra una
pieza específica («JTA.TAPA VALVULAS MITSUBISHI CANTER», varios motores posibles) y espesores o
series que una lista no dice—. `pruebas_de_la_revision.py` suma 14 pares.

### Muestras de los verdes: lo que se aprobaría sin mirar

Los verdes se aprueban en bloque, así que ahí un error cuesta más. Se leyeron dos muestras al
azar de 70 (una de todos los verdes entre listas, otra de los de 75, los más flojos): la primera
tenía 6 mal y la segunda 3. De ahí:

- **El espesor sin la unidad**: «JUNTA CABALLETE TAPA DE VAL. FIAT (esp. 0.40)» (TARANTO)
  concordaba con las de 0,20 / 0,30 / 0,50 y 0,80 mm de ILLINOIS. `medidas_desde_descripcion()`
  pedía «MM»; ahora también toma «ESP. 0.40» cerrando el paréntesis. Sube `VERSION_MEDIDAS`, así
  que la app relee las descripciones sola al arrancar.
- **El sensor del aire de afuera** («SENSOR TEMP EXTERIOR», el del tablero) no es el de
  temperatura del motor.
- **«BBA INYECTO»** es la bomba inyectora: no la bomba hidráulica del mismo Iveco.
- **La bobina con módulo** de encendido no es la «Sin Modulo».
- **Los motores de Honda** (D15Z6, B16A1, D16W4, B20A3: letra, cilindrada, serie y versión) no
  se reconocían como motores, así que las juntas de tapa del Civic D15 concordaban con las del
  B16.
- **Los cilindros de Cummins** salen de la cilindrada: la serie B 3.9 y el QSB 4.5 son de 4, el
  5.9, el 6.7 y el 8.3 de 6. «CUMMINS … 3,9 - ISBE» concordaba con «CUMMINS 6 CIL ISBe».

Sube también `VERSION_CONFIANZA`: con todas las reglas nuevas, el puntaje guardado de lo ya
aprobado se recalcula solo en la tarea de fondo.

Lo que se probó y NO se dejó: bajar también los verdes del «abanico de dos» cuando hay un
candidato que coincide mejor. Arreglaba la junta del Peugeot 208 EB2 (que queda con la del 208
que no dice motor), pero de 100 verdes que bajaban muchos eran el bueno perdiendo contra otro
por cómo está escrito, como el inyector CRI-FA 02-405 con el LEICJ014 de FISPA.

Sobre la cola de prueba: 24 pares más a rojo, todos confirmados a mano. Las 13.021 aprobaciones
siguen en 82 en rojo. `pruebas_de_la_revision.py` suma 5 pares.

### El kit de reparación no es la bomba que repara

FISPA escribe en la descripción el número de **otra** pieza, la del conjunto donde va la suya, y
el extractor lo tomaba como el número propio. Así nacían productos OEM unidos a lo que no son:

    KIT DE REPARACION KIT20408K … REF ORIG 9625476280        ← el kit repara la bomba 9625476280
    TAPA DE FLOTANTE 19009 … Compatible Bombas M Conj Bomba 93374782 93317613
    RAMPA DE INYECTORES 28005 … REF ORIG F000KV0206 REF Inyectores que montan 0280156020
    POLEA LRAP005 … VAG 058903119C INA 535000710 Para alternadores OEM 028903028F VW Bosch …

Sobre la base de prueba eran **685 vínculos aprobados**: 283 entre un kit de reparación y el
número de la bomba entera, 70 entre la tapa de flotante, el sensor de nivel o la rampa y la
bomba o los inyectores donde van, y 332 entre una polea y los alternadores que la llevan. Quien
buscaba la bomba de un Ford Ka recibía los dos kits de reparación como equivalentes, y quien
buscaba un alternador Bosch podía recibir la polea. Revisados los 685, todos estaban mal.

`tramos_del_conjunto()` encuentra esos tramos y `numero_del_conjunto_donde_va()` los usa. Si el
número está también afuera, dado como propio («REF ORIG FIAT 52004841 … Conj Bomba 52004841»),
no se decide. La misma regla corre en los cuatro lugares que tienen que decir lo mismo:

- **La cola** (`evidencia_cruzada()`): veto 🧰, rojo.
- **La auditoría de lo cargado** y **la confianza guardada** que muestra el buscador: 15. Sube
  `VERSION_CONFIANZA` a 6 para que se recalculen solas.
- **El buscador**: el kit sale «🧰 kit de reparación de lo buscado — NO es lo mismo», sin
  confianza, y no cuenta como equivalencia.
- **La importación**: de una descripción de kit de reparación ya no se saca ningún número, y de
  las otras se saca el tramo del conjunto. El número propio que va antes («REF ORIG
  9L559A299AC CONJUNTO DE BOMBA 9L559H307AC…») se sigue tomando.

Entre dos OEM no se aplica: los números que un mismo texto cita juntos son del mismo conjunto.
`pruebas_de_la_revision.py --base` cuenta aparte los 685 (`ALARMAS_DE_APROBACIONES_MALAS`).

En la cola: 25 verdes y 19 naranjas pasan a rojo.

Y dos más, de la misma ronda:

- **Bujías de moto de FISPA.** El número de NGK va como referencia original, sin decir NGK:
  «BUJIA NAFTA MOTO LSPC6HSA … REF. ORIG: C6HSA». Ahora se lee, igual que «NKG» mal escrito, y
  la CR8EH-9S de TARANTO deja de concordar con la C6HSA, la B7ES y la B8ES (3 pares a rojo).
- **El D4D de Renault es nafta.** Es el 1.0 16V del Clio II y el Twingo, y se leía como el D-4D
  diésel de Toyota en 60 descripciones. Sube `VERSION_APLICACIONES` a 8 para releerlas.

Otra muestra de 40 verdes al azar, mirados uno por uno: ninguno mal.

### La confianza del buscador y la de la cola, una sola regla

El número que el buscador muestra al lado de cada resultado es la confianza **guardada**:
`recalcular_confianzas()` la calcula en la tarea de fondo con `evaluar_equivalencia()`. La cola
de revisión puntúa con todo el análisis (`_analizar_lote_pendiente()`): además de eso mira las
alarmas de grupo —el número de fábrica que une piezas distintas de un mismo proveedor—, las
firmas —presión, largo de cable— y los kits. Eran dos motores, y no siempre decían lo mismo.

Medido sobre los 13.021 aprobados de la base de prueba, la guardada contra la de la cola:

| guardada → cola        | antes  | ahora  |
|------------------------|-------:|-------:|
| 🟢 → 🟢                 | 11.958 | 11.932 |
| 🟢 → 🟡                 |    268 |    268 |
| 🟢 → 🟠                 |     20 |     20 |
| **🟢 → 🔴**             | **10** |  **0** |
| 🟠 → 🔴                 |     16 |      0 |
| 🔴 → 🔴 (o no es equivalencia) | 742 | 794 |

Los 10 que el buscador mostraba 🟢 y la cola daba 🔴 eran el microfiltro unido al inyector, la
sonda de 48 cm con la de 153, la bomba de 4 bar con la de 3 y el kit de cables y bujías con la
bujía. Ahora el análisis de la cola corre también sobre lo cargado
(`vetos_del_analisis_sobre_lo_cargado()`, con `_analizar_filas()` separado de la lectura del
lote) y **lo que la cola pone en rojo, o aparta porque no es una equivalencia, baja a ese
puntaje en la confianza guardada y en la auditoría de lo cargado**. Lo demás no se toca: el
🟡 de la cola quiere decir «miralo antes de aprobar», y un vínculo cargado ya se aprobó. Los 268
🟢 → 🟡 son números de fábrica con la descripción copiada de otra fila (la cola los deja en 65
para que alguien mire), y mirados, están bien.

Cuesta tiempo en segundo plano: recalcular los 13.021 pasa de 6 a 19 s, y la auditoría tarda
13 s. Sube `VERSION_CONFIANZA` a 6 para que se recalcule todo al desplegar.

De paso, a la regla del conjunto se suman el **capuchón de bobina** («CAPUCHONES PARA BOBINA
79002 … REF ORIG SAGEM 2526182A»: los números son de la bobina) y el **microfiltro de
inyección** (los del inyector): 26 aprobados más, revisados, todos mal. Y la frase se buscaba
con un `\b` adelante, pero FISPA la pega a lo anterior —«NAFTEROCompatible Bombas M», «2015Conj
Bomba 770100K010»— y a veces parte el número —«Conj Bomba 97FP 9H307 AG»—: 14 tapas y sensores
más. La prueba con `--base` cuenta ahora 725 mal aprobados aparte.

El **filtro de la bomba** no entra, aunque lo parezca: de 18 aprobados, casi todos citan la
bomba («24075 VW amarok REF ORIG 2H0919050B»), pero «24077 Toyota Etios REF.ORIG: 23217-0Y020»
es el número del filtro, y la regla veta.

**Las cadenas.** El buscador también salta: X → número de fábrica → Y. Medido sobre la base de
prueba, todos los pares de marcas distintas que se unen así tienen además su propio vínculo
directo, con su propia confianza. Los que no lo tienen son 649, todos de la misma marca (el
inyector original de FISPA y el Lucas con el mismo número), y de esos 15 se contradicen, casi
todos por los autos que cada fila nombra, que con el número declarado no cuentan.

### Lo que se revisó a mano en el mostrador, y las cadenas largas

Mirando la lista de lo aprobado que choca con las reglas de hoy, quien atiende el mostrador
marcó dos errores de la regla:

- **La tapa de inspección es la tapa.** «JTA. TAPA CAM.AGUA DIESEL» (TARANTO) y «JTA
  T.INSP.CAM.AGUA FIAT REGAT» (IMPERIAL) son la misma junta, igual que la tapa del árbol de
  levas y la de inspección del árbol de levas. El veto «la del INSPECCION vs la pieza entera»
  existía por la tapita de inspección de la tapa de cilindros, que no es la junta de tapa de
  cilindros. Ahora vale solo contra las tapas grandes (`_PIEZAS_CON_TAPA_DE_INSPECCION`:
  cilindros, válvulas, cárter), y «INSP» se lee también sin el punto: «JTA TAPA INSP BLOCK»
  contra «JTA TAPA.INSP. BLOCK» salía rojo con las dos diciendo lo mismo.
- **La tapa de flotante NO es el conjunto de la bomba.** Se probó sacarla de la regla del
  conjunto («TAPA DE FLOTANTE 19012 … Conj Bomba 7S65 9H307CB») por un malentendido, y quien
  atiende el mostrador lo aclaró: la tapa y el conjunto son dos productos. Sigue en la regla,
  igual que el sensor de nivel, el kit, la rampa, la polea y el capuchón.

Y uno que salió de pasar la prueba con la copia de la base real (20.306 aprobados): de los 74
que ponía en rojo «⚠️ un número de fábrica que ILLINOIS le pone a piezas distintas», 62 eran
**la fila dueña del número** —la que lo trajo y lo pone en su propia lista de referencias—, que
se llevaba la culpa de la otra fila que lo cita. Ahora la alarma queda solo en la otra. En rojo
quedan 127 (0,6 %), y aparte 117 🔎 revisados: el «número de fábrica» es el nombre del motor
(X12SZ8V, SQR472, N13B16A), aprobados en bloque con reglas viejas.

**Las cadenas largas.** El buscador encadena hasta tres saltos y a cada resultado le pone lo que
vale su eslabón más flojo. Pero cada eslabón puede estar bien y el primero y el último no ser la
misma pieza: el del medio es vago y une dos específicos. Medido en la base real, 2.000
búsquedas al azar: **9.979 resultados a dos saltos o más, y 3.604 se contradicen con lo
buscado** —la junta de cárter MWM de 6 cilindros llegaba a la Perkins 4-203 de 4, a la del
Sprint 1.0 y a la del V8; el diferencial DANA 70 al DANA 30—, todos con «🟢 sólida».
`marcar_cadenas_que_no_aguantan()` compara lo buscado con cada resultado lejano con la regla de
la cola, y a los que se contradicen los pone «🔴 no es lo mismo», dice por qué en la cadena, y
con «sin vínculos flojos» los saca. Si el camino pasa por un número de fábrica que los dos
tienen, lo del auto no cuenta, igual que en la cola. Cuesta menos de un milisegundo por
búsqueda.

### 🧩 ¿Qué más lleva este trabajo?

En el buscador, debajo de los resultados, el interruptor **«🧩 ¿Qué más lleva este trabajo, para
el mismo motor?»**. Quien se lleva la junta de tapa de cilindros del Fire 1.4 también cambia la
de tapa de válvulas, la de admisión y la de escape de ese motor, y el catálogo ya las tiene:

    Jta.Tapa Cilindros Fiat Fire 8V 1.4CC  →  Junta de tapa de válvulas: 260310 TARANTO, JVL-168-28 ILLINOIS…
                                              Junta de escape: 260218 TARANTO, JSA-285 ILLINOIS (FIRE MPI 8V)…

`lo_que_va_con()` sale de `TRABAJOS_CON_COMPLEMENTOS`: la junta de tapa de cilindros (tapa de
válvulas, retenes de válvula, admisión, escape), la bomba de agua (su junta, el termostato), el
termostato (su junta), la bobina (bujías de encendido, cables) y las bujías (cables). Busca en
el catálogo por el texto, como todo lo que dice a qué auto le va una pieza: alguna marca de
auto en común, diésel con diésel, y el mismo motor o la misma cilindrada (con algún modelo en
común si los dos los nombran, y las mismas válvulas si las dicen). Ordena por cuánto lo dice el
texto, después lo que tiene stock, después lo más barato, y trae cuatro por pieza.

Probado sobre la base real, en 300 piezas al azar de esos tipos: 81 encuentran algo, a 98 ms.
Las reglas de combustible salieron de ahí: sin ellas la junta del Fiesta 1.4 TDCi traía la de
escape del Zetec SE naftero y la del 2.0 HDi la del 504 2.0. Y de ahí salieron dos arreglos que
sirven también a la cola: «ESP 1.6MM» se leía como cilindrada 1.6 (la junta de la Daily traía las
del Palio), y «MULTIPUNTO» ahora dice nafta. Solo busca cuando se prende el interruptor, y el
cartel pide confirmarlo con el cliente: es lo que dice el texto, no un catálogo de aplicaciones.

### ❓ Antes de vender, preguntá

Un proveedor tiene a veces varias versiones de la misma pieza para el mismo auto, y lo que las
separa es lo que hay que preguntar en el mostrador. Ahora el buscador lo dice arriba de los
resultados:

    ❓ Antes de vender, preguntá. FISPA tiene otras versiones de esta pieza para el mismo auto:
       - largo de cable: 58 cm → 80026FISPA, LECS020LUCAS · 128 cm → 80058FISPA

`versiones_para_preguntar()` busca en la lista del MISMO proveedor la misma pieza (la misma
cabeza, las mismas partes, el mismo tipo de sensor, kit con kit) para el mismo auto (alguna
marca y algún modelo en común, la cilindrada que no choque, diésel con diésel), y muestra lo
que las separa: vías, forma de la ficha, color, fase, largo de cable, espesor y años (estos solo
si son uno o dos rangos; los despieces listan diez autos con sus años). Sobre la base real, en
500 productos al azar aparece en 13, a 42 ms: la llave de luces de la Ranger de 14 o de 19
pines, la F100 fase I o fase II, la carcasa termostática de 2 o de 4 vías, los años del sensor
de rotación de la Ranger. Es lo que otra IA proponía como «variación de fase/restyling» con dos
fotos para elegir; fotos de las fichas no hay, pero el texto del proveedor dice qué preguntar.

Y en las cadenas largas, los resultados que no son lo mismo que lo buscado tampoco cuentan como
equivalencia ni compiten por «el más barato en stock», igual que los kits.

### 💳 Cuenta corriente de los talleres, y el código de retiro

En **Administrar → 💳 Cuentas corrientes**, cada taller (los mecánicos de 👥 Usuarios) tiene su
cuenta: lo que se lleva fiado (con vencimiento según los días de plazo de su cuenta), lo que
paga (efectivo, transferencia o cheque con su fecha), el saldo, lo **vencido** —los pagos se
imputan a lo más viejo, así que es lo que queda del saldo después de los cargos que todavía no
vencieron—, el límite de crédito y los cheques en cartera. Arriba, lo que hay para cobrar entre
todos, ordenado por quién debe más vencido; abajo, los movimientos con el saldo después de cada
uno y un botón para mandarle el saldo por WhatsApp. Un movimiento mal cargado se **anula**, no
se borra: queda a la vista, marcado.

**El código de retiro.** Para cargarle algo a la cuenta de un taller hace falta un código de 6
cifras que el taller genera en su portal (🔑 Generar código de retiro): vale una sola vez y por
24 horas, y generar otro anula el anterior. Se guarda el hash, no el código. Así nadie se lleva
repuestos a nombre de un taller diciendo «vengo de parte de Pérez». Es lo que otra IA
proponía como «OTP o biometría para retirar a nombre de un taller», en la forma que se puede
usar en el mostrador. Se apaga por taller en su configuración.

El taller ve en su portal su saldo, lo vencido, lo disponible y sus movimientos. Un mecánico
que debe plata no se puede eliminar (se lo desactiva): su cuenta se lista por los mecánicos que
existen, y borrándolo la deuda desaparecería de la pantalla.

Y de paso: **«👥 Usuarios» no se mostraba.** La rama de esa sección tenía una sangría de más y
quedaba adentro de la de Mantenimiento: elegirla dejaba la pantalla vacía, sin empleados ni
mecánicos. El auditor ahora marca como ERROR una rama de sección a otra altura que las demás.

### Las ideas de otra IA: qué ya estaba, qué se hizo, qué no

Una lista de ideas de Gemini para la app, revisada contra lo que hay y contra el catálogo real
(juntas de IMPERIAL, TARANTO e ILLINOIS; eléctricos y sensores de FISPA, CRI-FA y JL):

| Idea | Cómo quedó |
|---|---|
| Patente → auto | Ya estaba, y sin la consulta paga: la patente dice el año sola (`leer_patente()`) y la foto de la cédula dice el resto (`leer_cedula_por_foto()`) |
| VIN → auto, y número de fábrica | Ya estaba: VIN (`buscar_vehiculo_por_vin()`), y el número de fábrica es la base de toda la búsqueda |
| Código de falla OBD → pieza | Ya estaba («Del código de falla al repuesto») |
| Recordatorios de service, historial por auto | Ya estaba: `historial_piezas`, `calcular_proyeccion_mantenimiento()`, `a_quien_avisar()` |
| Stock, reservas, reposición | Ya estaba |
| Venta cruzada de complementos | Estaban los combos a mano (3 cargados). **Se hizo** «¿Qué más lleva este trabajo?», con las piezas del catálogo para el mismo motor |
| Kit de service / puesta a punto (filtros, frenos, bujías) | No: en el catálogo hay 656 aplicaciones de filtros y 10 de frenos contra 15.438 de juntas. El kit que sí sale de este catálogo es el del trabajo, y es el de arriba |
| Litros de aceite por motor | No: no hay de dónde sacarlo, y un dato inventado hace vender de menos |
| VTV, oblea de GNC, multas | No: no hay una consulta pública con una interfaz para programas; hacerlo sería leer páginas de organismos que cambian sin aviso, y no es lo que se resuelve en el mostrador |
| Complejidad de instalación, tutoriales, modelo 3D, puntos, lockers | No: son de una tienda para el que compra, y esta app es la del que vende |
| Variación de fase / restyling / ficha | **Se hizo** «❓ Antes de vender, preguntá», con lo que dicen las descripciones (no hay fotos de fichas) |
| Cuentas corrientes de talleres, OTP para retirar | **Se hizo**: cuenta corriente con plazo, límite y cheques, y el código de retiro de un solo uso que genera el taller. Biometría no: no hay cómo hacerla desde una página web de mostrador |
| Pasaporte de mantenimiento del auto | Ya estaba: la ficha del vehículo con su historial de piezas se descarga en PDF. Firmarla o «blockchain» no agrega nada sin una página pública donde verificarla |

### 📍 Las indicaciones de «andá a…» llevan a donde dicen

Muchos avisos terminan diciendo dónde se arregla («📍 Administrar → Mantenimiento → …»). Una
revisión de todas encontró **más de 20 que mandaban a un lugar que no existe** o que ya se había
mudado: «Estadísticas → Reposición» (se llama «📌 Para pedir»), «Mantenimiento → Calidad» (la
herramienta está en «🔎 Encontrar equivalencias»), «Vínculos que unen familias» (es «…unen DOS
familias de repuestos», en «🧹 Limpiar y corregir»), «Traer fotos en tanda», «Administrar → 💳
Alias para QR» (está adentro de «💬 Mensajería y cobros»), «Mantenimiento → 🩺 Estado» para
cargar códigos de barras (es «🏷️ Códigos de barras»), y otras.

- **Ya no se escriben a mano.** `miga_hasta("Códigos puente")` arma la miga entera desde el
  nombre de la herramienta, la solapa o el grupo, y si ese nombre no existe da error en vez de
  mandar a buscar algo que no está. Las listas de pantallas y solapas viven en un solo lugar
  (`logica/interfaz.py`, «NAVEGACIÓN: DÓNDE ESTÁ CADA COSA»).
- **El botón «Ir a arreglarlo →» llega a todos lados.** Antes solo sabía de las solapas de
  Estadísticas: un aviso que apuntaba a «Administrar → 💳 Cuentas corrientes» dejaba en la
  primera solapa de Administrar. Ahora llega a la pantalla, la solapa, el grupo de Mantenimiento
  y, si nombra una herramienta, al grupo donde está. Probado con los 69 destinos posibles y con
  los 6 avisos de la base real.
- **El auditor lo controla.** `python3 auditar.py` da ERROR si un `miga_hasta("…")` no
  encuentra su destino, o si un texto que nombra una pantalla sigue con «→» hacia algo que no es
  una solapa, un grupo ni una herramienta. Si se renombra una herramienta, avisa en qué textos
  quedó el nombre viejo.

### 🧭 Más simple de recorrer

Capturas de la base real en una pantalla de 1366×768, antes y después:

- **El menú va arriba de todo.** Iba debajo de los avisos del día, y con cuatro avisos abiertos
  quedaba a media pantalla en TODAS las secciones: para pasar de Administrar a Estadísticas había
  que bajar a buscarlo. Ahora es lo primero debajo del encabezado.
- **Los avisos se abren solo en el Buscador**, que es donde se arranca. En las demás secciones
  quedan en un renglón plegado («🔴 4 cosa(s) que conviene mirar hoy · 🟡 2 sin apuro»), y lo que
  uno vino a hacer aparece enseguida: en Administrar, el contenido pasó de empezar debajo de los
  cuatro avisos a empezar a los 380 px.
- **Cada sección y cada solapa dice para qué sirve, a la vista.** La de la sección estaba
  escondida detrás de «ℹ️ ¿Para qué sirve esta sección?», que ocupaba el mismo renglón que la
  respuesta. Las solapas no tenían ninguna: «🧹 Mantenimiento» o «🧮 Auditoría y depósito» no
  dicen solos qué hay adentro. Ahora las 21 tienen su renglón (`PARA_QUE_SIRVE_LA_SOLAPA`), y el
  auditor da ERROR si se agrega una solapa sin él.
- **Una sola forma de dibujar las solapas** (`elegir_solapa()`): las tres pantallas que tienen
  solapas repetían las mismas líneas, cada una con su lista.
- Textos que mandaban a un botón o lugar con otro nombre: «🔄 Procesar fotos pendientes» (el
  botón es «🔄 Procesar las … que faltan ahora»), «cargala desde 'Administrar'» (es
  Administrar → 📦 Productos), «traerlas desde Mantenimiento» (dice ahora a qué herramienta).

- **Botones que llevan, en vez de «andá a la pestaña…».** Después de agregar un código a la
  lista de WhatsApp aparece «📋 Ir a la lista (N) →». En «🧩 Productos sin equivalencias», «🔗
  Usar» lleva directo a Vincular manual con el código ya puesto. Ese aviso, además, decía
  «completá el Código B», y Vincular manual ya no tiene Código A y B: se arma una tanda.

Recorridas las 30 pantallas, solapas y grupos de Mantenimiento como administrador sobre la base
real: ninguna da error.

### 📝 Los textos de ayuda, revisados uno por uno

Se leyeron los ~210 textos de ayuda (los plegables «ℹ️» y los «?» de cada control). Lo que
decía algo que no es cierto:

- **Matriz ABC**: decía «como la app no tiene un módulo de ventas, la rotación se aproxima con
  las búsquedas». Las ventas se anotan con «🛒 Se llevó». Ahora la matriz ordena primero por lo
  vendido en los últimos seis meses y después por lo buscado, y muestra las dos columnas.
- **Precios que no cierran**: mandaba a cortar el vínculo «desde Vincular manual», que no corta
  vínculos. Ahora dice dónde: en el Buscador, «🧭 ¿Por qué apareció…?» → «✂️ Cortar ese
  vínculo», o «🌉 Códigos puente» si es un mismo código en muchos pares.
- **Números viejos escritos a mano**: «son 24.774 vínculos y tarda 12 segundos», «un catálogo
  de 110.000 productos» (hoy son 10.153 y 87.155).
- **«Las primeras 4 funciones usan una API key»** en el uso de la IA, sobre una tabla que no
  tiene orden fijo.
- **Resúmenes con la frase cortada** («La copa es cónica, así que se cargan sus dos
  diámetros:» y la respuesta adentro del plegable): cinco. El auditor ahora no deja que el
  resumen de una ayuda termine en «:».
- Ayudas escritas como lista de cambios («Ahora va de a 6 fichas en vez de una por una», «la
  reposición hasta ahora era manual», «antes había que hacerlo de a pares»): para quien la lee
  por primera vez no hay «antes».
- Más botones que llevan: «🏭 Ir al catálogo de aplicaciones →» cuando se sube a Cargar Excel un
  catálogo de aplicaciones, y «🔢 Ir a Chasis / VIN →» en Repuestos por vehículo.

### 🗂️ Mantenimiento, un archivo por grupo

`pantallas/administrar.py` tenía 3.371 renglones y 2.500 eran Mantenimiento, con las
herramientas de un mismo grupo repartidas en tramos intercalados con las de otros (las de «🔎
Encontrar equivalencias» estaban en tres lugares distintos del archivo). Ahora:

| Archivo | Qué tiene |
|---|---|
| `pantallas/administrar.py` | Marcas, Productos, Mensajería, Combos, Usuarios, Cuentas corrientes (841 renglones) |
| `pantallas/mantenimiento.py` | Lo de arriba de Mantenimiento: borrar un producto, el buscador de herramientas, el grupo |
| `pantallas/mantenimiento_encontrar.py` | 🔎 Encontrar equivalencias |
| `pantallas/mantenimiento_limpiar.py` | 🧹 Limpiar y corregir |
| `pantallas/mantenimiento_calidad.py` | 🧠 Calidad y aprendizaje |
| `pantallas/mantenimiento_barras.py` | 🏷️ Códigos de barras |
| `pantallas/mantenimiento_fotos.py` | 📷 Fotos |
| `pantallas/mantenimiento_estado.py` | 🩺 Estado y papelera |

Los bloques se movieron tal cual, sin cambiar un renglón. Comprobado dibujando cada grupo con la
versión anterior y con esta sobre la base real: los mismos títulos, botones y desplegables, en el
mismo orden.

## 🔗 Revisar sugeridas: primero lo que hay que hacer

Mirado con capturas sobre la base real (15.308 pendientes en 8 listas):

- **Abre en la lista que importa.** Las listas iban por fecha y la más nueva era siempre la
  automática del día, de uno o dos pares: la pantalla abría ahí mientras la importación de
  13.941 esperaba en el selector. Ahora las de menos de `PARES_DE_UNA_LISTA_CHICA` (20) van al
  final (`resumen_lotes_pendientes()`).
- **La revisión va primero.** «Revisar lo ya cargado» y «Revisar lo aprobado con las reglas de
  hoy», que se usan de vez en cuando, pasaron abajo: lo que se viene a hacer a esta pantalla
  quedaba tercero.
- **Sin un consejo equivocado.** El aviso «más del 70% dispara alarmas: la importación quedó mal
  mapeada, descartá toda la lista» salía también en el BARRIDO automático, donde es lo esperable,
  y hacía tirar las 2.558 limpias con el resto. Ahora sale solo en las listas importadas.
- **La muestra de control, compacta.** Cada par eran cinco renglones; ahora las dos
  descripciones van juntas y la decisión al lado del motivo. Diez pares entran en una pantalla.

## 📱 El buscador, pensado para el mostrador (y el celular)

Mirado con capturas en un iPhone y en una computadora, con la base real:

- **El formulario ocupaba toda la primera pantalla del celular** (filtro de marca, tres opciones
  de distancia apiladas y una casilla) y el resultado quedaba abajo. Ahora van la caja del código
  y **Buscar** a lo ancho, y las opciones en **⚙️ Opciones**, cuyo título dice lo que está
  puesto («todas las marcas · hasta 3 saltos»), así un filtro elegido nunca queda escondido.
- **La tabla muestra primero lo que se contesta en el mostrador**: Código, Marca, Precio y
  Stock (`COLUMNAS_PRIMERO`). En el celular antes se veían Código y Descripción, y lo demás
  quedaba afuera de la pantalla.
- **Sin columnas que no dicen nada** (`columnas_que_dicen_algo()`): se esconden las que en esa
  búsqueda están vacías —se veía «None» en Fabricante, Stock e Imagen— o dicen siempre lo mismo
  (Tipo: PROVEEDOR, Favorito: 0).
- **El precio con separador de miles** según el idioma del navegador (18.375).
- **El resumen dice lo que se ve**: «✅ 3 equivalencias en 2 marcas: …». Antes decía «1
  equivalencia, sobre 10 filas en total» y se veían dos (las otras eran códigos de fábrica).
- **En la búsqueda por descripción se toca la fila** para abrir ese código con todas sus
  equivalencias (`abrir_la_fila_elegida()`). Antes abajo de la tabla se repetía la lista entera
  como botones, uno por resultado, y en el celular eran tres pantallas más.
- **Sin «None» en los textos y el precio sin centavos** en pantalla (`para_mostrar()`); las
  filas guardadas no se tocan.
- **Arriba de la caja de búsqueda, solo lo del mostrador.** En el celular, el selector de vista
  (que se elige solo) va al pie de la página; los partes técnicos del mantenimiento y del
  descubrimiento, y el cartel de «N equivalencias esperando aprobación», se muestran solo a quien
  entró con contraseña, que es quien puede hacer algo con ellos.
- **«¿Se lo llevó?» en el celular es un selector desde dos resultados**: las columnas se apilan
  y cada fila eran dos botones a lo ancho.

## 📷 Las fotos sobreviven a los reinicios

La copia que se sube a GitHub —con la que arranca la app después de cada reinicio de
Streamlit Cloud— no lleva las fotos, por peso. Pero borraba también sus LINKS
(`imagen_url = NULL`), y eso tenía un costo que no se veía: las fotos que trajeron los catálogos
de fabricante y Mercado Libre se perdían en cada reinicio, y nada las volvía a buscar, porque esos
códigos ya figuraban como leídos y las tareas como terminadas. La búsqueda por cámara quedaba
vacía.

- **La copia conserva los links** (`_sacar_las_fotos()`): lo que pesa es la foto guardada
  adentro, las miniaturas y las firmas, no una dirección.
- **Al restaurar al arrancar se vuelven a bajar** (`_restaurar_desde_semilla()` prende
  `fotos_de_internet_pendientes` y reabre las tareas de fotos y firmas). No es repetir por
  repetir: lo que había se perdió con el disco.
- **Las fotos de la ficha del proveedor guardan el link de la IMAGEN**, no el de la ficha.
  Con el de la ficha, sin miniatura el buscador mostraba una foto rota, y volver a bajarla daba
  «no es una imagen».
- **Si un link resulta ser una página**, se busca la foto adentro y el link pasa a ser el de la
  imagen. Cubre las fotos de ficha guardadas antes de este cambio y los links de producto
  pegados en un Excel.

Probado con un servidor falso: 3 fotos de ficha con el link de la imagen, un link-página
corregido solo, la copia con los 4 links, y después de restaurarla en una base vacía, las 4
bajadas de nuevo con su firma para la cámara.

## 🔒 Seguridad: quién entra, adónde va la copia y qué se pide afuera

La app está publicada en internet y «➡️ Continuar» entra sin contraseña. Revisado entrando
como invitado, se podía armar y **descargar la base entera** (61 MB: precios, clientes,
teléfonos, usuarios), aprobar o descartar equivalencias en bloque, ver los clientes de
Vehículos y crear vínculos a mano. Solo pedían clave los botones que borran.

- **Candado por sección** (`seccion_permitida()`, `NIVEL_DE_CADA_SECCION` en app.py). Buscador,
  Lista WhatsApp y Modo Mecánico siguen abiertos: son el mostrador. Vincular manual,
  Administrar, Estadísticas y Vehículos piden contraseña de empleado (operador o
  administrador), y «💾 Backup y config» la de administrador. Los avisos de salud tampoco se
  le muestran a quien entró sin contraseña. Si todavía no hay ninguna contraseña configurada
  no se cierra nada —dejaría afuera al dueño—: la sección avisa que está abierta.
- **Cargar Excel usa el mismo candado** (`seccion_permitida("admin")`): con contraseñas pide la
  de administrador, igual que antes; sin ninguna configurada avisa y deja pasar, como el resto.
  Antes pedía una contraseña que no existía y no había forma de importar.
- **Adentro de lo que queda abierto**, el invitado consulta pero no carga ni ve datos de
  clientes (`es_empleado_o_abierto()`). En Modo Mecánico, buscar por patente ya no muestra el
  nombre y el teléfono del cliente ni lo que consultó antes —una patente se adivina—; cargar
  códigos de falla, leer la cédula con IA, guardar la ficha del auto, cargar fabricantes y
  aplicaciones pide contraseña de empleado, y borrar modelos o motores aprendidos, la de
  administrador. La búsqueda por voz del Buscador usa IA paga: también para empleados.
- **La sesión con contraseña se cierra sola** después de `HORAS_DE_SESION_SIN_USO` (4) horas
  sin tocar nada: en la computadora del mostrador la pestaña queda abierta días, y la sesión de
  administrador de la mañana la heredaba el que se sentara después. Usándola no se corta.
- **La copia a GitHub se sube cifrada** si en los secretos está
  `clave_copia = "una frase larga"` (AES-GCM, clave estirada con PBKDF2; ver
  `cifrar_copia()`). Al arrancar se descifra sola. Sin la frase se sigue subiendo como antes —
  perder la copia es peor—. **Guardá la frase también fuera de la app: sin ella la copia
  cifrada no se puede abrir.** Las copias viejas, sin cifrar, se siguen pudiendo leer.
- **Lo dañado no se sube ni se baja** (`la_base_esta_sana()`, un `PRAGMA quick_check` de
  0,1 s). Si la base se dañara, la copia automática la subía igual y pisaba la última copia
  buena —la que se usa para arrancar después de un reinicio—. Ahora no se sube, queda la buena
  y el control de salud lo avisa en rojo (`base_danada`). Al arrancar, una copia bajada de
  GitHub que no pasa el control tampoco se usa.
- **Restaurar acepta la copia de GitHub** tal cual está: `.gz`, cifrada o no. Sin la frase,
  o con otra, no se toca nada y lo dice.
- **Aviso si el repositorio es público.** Después de cada subida se pregunta a GitHub
  (`repo_copia_publico`) y el control de salud lo dice en rojo. El repositorio de esta app
  ES público, y la rama `copia-de-seguridad` tiene copias sin cifrar en su historial:
  hay que ponerlo en privado (GitHub → Settings → General → Change visibility).
- **Las fotos no pueden apuntar adentro del servidor** (`direccion_interna()`). Se bajan de
  links que escriben otros (og:image, miniaturas de Mercado Libre, <img> de catálogos), y una
  página hecha a propósito podía hacer que la app pidiera 169.254.169.254 (los datos internos
  de la nube) o localhost. Se revisa adónde resuelve el nombre y cada redirección. Para las
  pruebas con servidores falsos locales: `EQUIVALENCIAS_PERMITIR_RED_LOCAL=1`.
- Lo que ya estaba bien y se revisó: contraseñas con PBKDF2 y sal, comparación en tiempo
  constante, freno a los intentos repetidos, credenciales de portales solo en los secretos,
  texto de las listas escapado antes de entrar en HTML (lo controla el auditor), y ninguna
  clave ni token en el historial del repositorio.

## ⏱️ Revisar sugeridas sin esperar

«Estadísticas → 🔗 Equivalencias sugeridas» analiza la lista entera antes de mostrarla: 6 a 8 s
sobre la cola real (13.941 pares de FISPA). Tres cambios para no esperarlos:

- **Decidir no rehace el análisis.** Aprobar o descartar bajaba el total de pendientes y eso
  rehacía todo: 3,7 s por decisión. Ahora se sacan del análisis guardado los pares que ya no
  están pendientes (`pares_pendientes_del_lote()`) y el resto queda igual: **1,3 s**. Cada
  `RECORTES_ANTES_DE_REANALIZAR` (200) decisiones se rehace entero.
- **El análisis es del servidor, no de la sesión.** Recargar la página o entrar desde el
  celular abre una sesión nueva, y antes eso volvía a analizar todo. Ahora queda guardado
  (`analisis_de_lote_guardado()`) mientras no cambie el código, hasta
  `HORAS_QUE_DURA_EL_ANALISIS` (3 h): una sesión nueva abre en **0,7 s**.
- **Si ya se está preparando, se espera.** Entrar justo mientras la tanda de fondo lo hace
  arrancaba otro análisis al lado, y los dos se repartían el procesador (7,1 s). Ahora la
  pantalla espera al de fondo (`esperar_el_analisis_en_preparacion()`, 5,9 s), sin pedirle el
  paso mientras tanto: si no, se esperarían una a la otra hasta el tope de 20 s.
- **Se prepara de antemano.** La tanda de fondo deja hecho el análisis de la lista que la
  pantalla muestra primero, al arrancar el servidor y después de cada importación
  (`preparar_el_analisis_del_primer_lote()`). La primera apertura pasó de **6,6 s a 1,0 s**.

## 🧹 Mantenimiento más liviano

- El conteo de descripciones pegadas recorre las 70.000 descripciones (1,6 s). Tenía caché de
  Streamlit, que se pierde con cada reinicio del servidor; ahora se guarda en la base con la
  versión del catálogo y la del separador (`pegadas_version`): después de un reinicio cuesta
  0,017 s.
- El panel «⚡ Carga automática», que va arriba de Mantenimiento, es una lista y no una tabla:
  la tabla costaba 0,3 s en cada toque.

## ✅ Lo que ya se bajó no se vuelve a bajar

**Cuando una tarea automática termina, no se repite.** Si no encuentra nada pendiente queda
«terminada» (`terminado_<tarea>` en la configuración) y la tanda de fondo ya no la mira: ni cada
rato, ni al reiniciar el servidor, ni al importar una lista. Se reabre solo si lo pedís:

- **Administrar → Mantenimiento → ⚡ Carga automática → 🔄 Buscar lo nuevo** (o el mismo botón
  al lado del avance de cada tanda),
- prendiendo una tarea que estaba apagada,
- o, si prendés «Al importar una lista, buscar solo lo nuevo de esa lista», al importar
  (apagado de fábrica).

**Y al reabrirla no baja nada de lo que ya bajó.** Cada fuente anota lo hecho: la foto en el
producto, `ficha_equiv_leida`, `fichas_de_catalogo_leidas`, `mercado_libre_leidos`. Solo se pide
lo que falta. Además:

- **La misma ficha no se pide dos veces.** Las fotos y las equivalencias leen la misma página
  del proveedor; las últimas 400 fichas leídas quedan en memoria (sin scripts ni estilos), y
  las equivalencias van por la misma marca que acaban de recorrer las fotos. Medido con un
  servidor falso: 81 productos con las dos tareas prendidas, 81 fichas pedidas, ninguna dos
  veces.
- **Una foto compartida se baja una vez.** La foto de un catálogo de fabricante queda
  propuesta para todos los productos que citan ese código. Antes se bajaba una vez por cada
  uno; ahora una vez por link (3 productos con el mismo link: 1 pedido).
- **Lo que falla por la red se reintenta una vez por día, hasta tres días**
  (tabla `descargas_fallidas`, ver `_anotar_fallas()`). Lo que falló hoy no se vuelve a pedir
  hoy. Al tercer día se deja de intentar, se marca como hecho y figura en «Dejadas de
  intentar». Mientras quede algo para reintentar, la tarea descansa hasta mañana en vez de
  terminar. **♻️ Reintentar las que fallaron** vuelve a probar solo esas: en la prueba, 3
  pedidos y no los 96 del catálogo.
- Un «no hay ficha» (404) o «la ficha no tiene foto» es una respuesta, no una falla: queda
  anotado y no se reintenta.
- **A mano tampoco se repite.** «🌐 Leer las fichas y proponer equivalencias» sigue donde
  quedó la tanda anterior; releer las ya leídas es una casilla aparte, para cuando el
  proveedor actualizó su catálogo. Y «🔄 Volver a probar esos códigos» (fotos) rehabilita solo
  los marcados «sin foto» o «fallo»: antes limpiaba el estado de todos los productos, incluidos
  los links rotos, que se volvían a bajar sabiendo que no andaban.

## 🎯 Tus propios datos: qué pedir y a quién avisar

- **Qué te conviene cargar o pedir** (Estadísticas → 🔎 Búsquedas sin resultado). La lista de
  búsquedas fallidas decía QUÉ faltó; `que_conviene_cargar_o_pedir()` dice qué hacer con cada
  código, mirando tu base: 🔗 si otro producto lo nombra en su descripción lo tenés con otro
  número y falta el vínculo; ⌨️ si hay un código que se escribe casi igual
  (`codigos_por_tipeo()`) probablemente fue un error de tipeo; 🛒 si no aparece en ningún lado y
  lo pidieron más de una vez, es para pedirle al proveedor. Junta las formas de escribir lo
  mismo, y lo pedido una sola vez sin ninguna pista no se muestra.
- **📞 A quién avisar** (Vehículos). El ranking de atrasados comparaba cuántas veces se cambió
  una pieza contra cuántas debería, con el último km anotado. `a_quien_avisar()` mira la ÚLTIMA
  vez que se cambió cada pieza y el km de HOY estimado con lo que anda ese auto por día
  (`km_estimado_hoy()`: entre que se cargó la ficha y la última vez que se anotó el km, con al
  menos una semana de por medio). Lista lo que ya pasó su vida útil o llega en 30 días, con el
  mensaje de WhatsApp armado para cada cliente.

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

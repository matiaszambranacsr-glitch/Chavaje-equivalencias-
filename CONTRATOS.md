# Lo que no se puede romper

Cada regla dice qué prueba la sostiene. Si una prueba falla, se rompió la regla: no se
«arregla» la prueba, se arregla el código. Una regla sin prueba lo dice.

Las pruebas se corren como dice el README, en «Antes de subir un cambio».

## Las equivalencias

| Regla | Dónde se cuida | La prueba |
|---|---|---|
| Un vínculo A↔B existe una sola vez, y B↔A no puede existir si existe A↔B | Clave primaria + trigger `equivalencias_en_orden` (la base da vuelta lo que entra al revés) | `pruebas_de_los_cambios.py` (1) |
| Un producto no se vincula consigo mismo | El mismo trigger | `pruebas_de_los_cambios.py` (1) |
| Una sugerencia por tipeo nunca se guarda como vínculo | Solo se muestra, con «son códigos distintos» | — (es solo pantalla) |
| El análisis no se equivoca con pares ya revisados a mano | El análisis del lote | `pruebas_de_la_revision.py` |
| Lo rechazado a mano no queda entre las limpias (más del 1 % es una falla) | El análisis del lote | `pruebas_de_la_revision.py --base` |
| «Confirmada» solo con una fuente que declare el vínculo (una lista, un catálogo, una persona) | `veredicto_de_la_equivalencia()`, `respaldo_del_origen()` | `pruebas_de_la_precision.py` (1, 2) |
| Una contradicción (medidas, rubro, posición) gana sobre cualquier fuente y cualquier puntaje | `ficha_de_prueba()`, `TOPE_CON_VETO` | `pruebas_de_la_precision.py` (3, 4) |
| Las ventas solas no pasan un vínculo de franja | `sin_cruzar_la_linea_por_lo_aprendido()` | `pruebas_de_la_precision.py` (3) |
| Comprobar en la mano no borra de qué lista vino el vínculo | `comprobar_en_la_mano()` | `pruebas_de_la_precision.py` (5) |
| Si el proveedor cambia de equivalente, se avisa y no se borra nada | `equivalentes_que_la_lista_dejo_de_declarar()` | `pruebas_de_la_precision.py` (8) |
| Con y sin ABS, aire o sensor son piezas distintas | `firmas_compatibles()`, `equipamiento_declarado()` | `pruebas_de_la_revision.py` (pares de muestra), `pruebas_de_la_precision.py` (9) |
| Las medidas que salen del mismo texto no suman dos veces | `evaluar_equivalencia()` | `pruebas_de_la_precision.py` (10) |
| Lo que volvió porque no le iba baja el vínculo y gana sobre cualquier fuente | `registrar_devolucion()`, `pares_devueltos()` | `pruebas_de_la_precision.py` (11) |
| Un rechazo no se pisa: sale de la cola, no se aprueba en grupo, y vincularlo a mano pide confirmarlo | `marcar_revision()`, `aprobar_pendientes()`, `rechazos_del_grupo()` | `pruebas_de_la_precision.py` (12) |
| Una pieza de seguridad confirmada igual pide mirarla en la mano | `riesgo_de_la_pieza()`, `veredicto_de_la_equivalencia()` | `pruebas_de_la_precision.py` (13) |
| Al volver a puntuar todo queda anotado qué cambió de franja | `anotar_la_deriva()` | `pruebas_de_la_precision.py` (14) |

## El stock, los precios y la plata

| Regla | Dónde se cuida | La prueba |
|---|---|---|
| Lo que otro cambió mientras se editaba (precio, stock, costo) no se pisa | `actualizar_precio_stock()` con lo mostrado, campo por campo; `valor_con_que_se_abrio()` | `pruebas_de_los_frenos.py` (15b) y en la app con dos sesiones |
| «Completar medidas» no pisa lo cargado a mano | `aplicar_medidas_deducidas()` con `COALESCE` | `pruebas_de_los_frenos.py` (13) |
| Lo apartado nunca pasa el stock | `reservar_stock()` en una transacción | `pruebas_de_carga.py` |
| El mismo remito no suma el stock dos veces | `aplicar_carga_remito()` con huella | `pruebas_de_los_frenos.py` (14) |
| Un pedido al depósito se entrega y se cobra una sola vez | `entregar_pedido()` | `pruebas_de_carga.py` |
| El límite de crédito no se pasa, ni con varios pidiendo a la vez | `pedir_al_deposito()`: el límite adentro de la transacción | `pruebas_del_deposito.py` (ocho a la vez) |
| El saldo de una cuenta es lo entregado menos lo pagado | `estado_de_cuenta()` | `pruebas_de_carga.py` |
| El interés por mora solo en las cuentas que lo tienen prendido, y nunca dos veces los mismos días | `cargar_el_interes_por_mora()` | `pruebas_de_las_cuentas.py` |
| Un presupuesto guardado no cambia si después cambia un precio | Se guarda con sus precios (`items_json`) | `pruebas_de_los_frenos.py` (10) |
| Un presupuesto no se guarda dos veces por un doble toque | `guardar_presupuesto_mecanico()` | `pruebas_de_los_frenos.py` (10) |

## Las cuentas y los permisos

| Regla | Dónde se cuida | La prueba |
|---|---|---|
| Cada cuenta tiene su clave (la clave sola dice quién entra) | `clave_ya_usada()` | `pruebas_de_los_frenos.py` (12) |
| El freno de intentos vale para todos, también para los talleres | `validar_password(con_mecanicos=True)` | `pruebas_de_los_frenos.py` (7) |
| Un taller ve su portal y nada más | `mostrar_portal_mecanico()` | `pruebas_de_la_sesion.py` (4) |
| Las funciones sensibles vuelven a mirar quién está adentro | `exigir_nivel()` | `pruebas_de_los_cambios.py` (5) |
| Un empleado desactivado o con otro rol pierde los permisos al instante | `nivel_vigente_de_la_sesion()` | `pruebas_de_la_sesion.py` |
| Después de «Salir» no queda nada del anterior | `cerrar_sesion()` | `pruebas_de_la_sesion.py` |
| Con la base dañada, los empleados solo pueden buscar | `modo_solo_lectura()` | `pruebas_de_los_frenos.py` (1) |

## Las copias

| Regla | Dónde se cuida | La prueba |
|---|---|---|
| Restaurar deja la base sana y con los mismos datos, también desde la copia cifrada de GitHub | `restaurar_backup()` | `pruebas_de_los_frenos.py` (16) |
| Un backup dañado no entra ni toca nada | `la_base_esta_sana()` antes de restaurar | `pruebas_de_los_frenos.py` (16), `pruebas_de_la_recuperacion.py` |
| Una base dañada no se sube y no pisa la copia buena | `subir_backup_a_github()` | — (ver «Sin prueba automática») |
| Si el catálogo cae a la mitad, la copia buena no se pisa sola | `subir_la_copia_si_cambio()` | `pruebas_de_los_frenos.py` (5) |
| La copia de GitHub se puede recuperar (se prueba sola cada día) | `verificar_la_copia_de_github()` | `pruebas_de_los_frenos.py` (6) |
| Quedan copias anteriores (7 diarias, 4 semanales, 6 mensuales) | `copias_a_guardar()` | `pruebas_de_las_copias_en_github.py` |
| Subir la base no borra las fotos de la rama | `_publicar_en_la_rama()` | `pruebas_de_las_copias_en_github.py` |
| La base que no se puede leer abre en modo recuperación | `mostrar_modo_recuperacion()` | `pruebas_de_la_recuperacion.py` |

## El código

| Regla | Dónde se cuida | La prueba |
|---|---|---|
| `nucleo/` se regenera desde `logica/` y está al día | `nucleo/generar.py` | `auditar.py` (lo regenera aparte y compara) |
| Ningún archivo tiene escrita la carpeta de una máquina | — | `auditar.py` |
| Un error anotado no lleva claves ni contraseñas | `tapar_lo_sensible()` | `pruebas_de_los_frenos.py` (8), `nucleo/pruebas.py` |
| Una búsqueda que falla no se confunde con «no hay» | El buscador | `pruebas_del_buscador.py` |
| Las librerías son las que se probaron | `requirements.txt` con rangos | Correr las pruebas con esas versiones |

## Sin prueba automática todavía

- La importación de una lista es todo o nada: va en una transacción (ver
  pantallas/cargar_excel.py), pero no hay prueba que la corte a la mitad.
- Una base dañada no se sube a GitHub: `subir_backup_a_github()` la controla antes, sin prueba
  propia (la de la copia que no se pisa con el catálogo a la mitad es otra).
- La revisión de un lote saltea lo que otro ya resolvió (`aplicar_decisiones()`).
- Los cachés se limpian al restaurar.

# Lo que no se puede romper

Cada regla dice qué prueba la sostiene. Si una prueba falla, se rompió la regla: no se
«arregla» la prueba, se arregla el código. Una regla sin prueba lo dice.

Las pruebas están en la carpeta `pruebas/` y se corren como dice el README, en «Antes de subir un
cambio» (todas juntas: `python .github/correr_las_pruebas.py`).

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
| La limpieza de productos borra solo los vacíos (sin vínculos, decisiones, precio, stock ni historia) | `depurar_huerfanos()` | `pruebas_de_los_cambios.py` (10) |
| Un código de fábrica con la marca pegada se renombra, o se junta con el limpio sin perder pendientes ni decisiones | `corregir_codigo_con_la_marca_pegada()` | `pruebas_de_la_precision.py` (74) |
| Aplicar lo decidido en una tanda saltea lo que otro resolvió mientras tanto | `aplicar_decisiones()`, `_los_que_siguen_pendientes()` | `pruebas_de_la_precision.py` (73) |
| Un rechazo no se pisa: sale de la cola, no se aprueba en grupo, y vincularlo a mano pide confirmarlo | `marcar_revision()`, `aprobar_pendientes()`, `rechazos_del_grupo()` | `pruebas_de_la_precision.py` (12) |
| Una pieza de seguridad confirmada igual pide mirarla en la mano | `riesgo_de_la_pieza()`, `veredicto_de_la_equivalencia()` | `pruebas_de_la_precision.py` (13) |
| Al volver a puntuar todo queda anotado qué cambió de franja | `anotar_la_deriva()` | `pruebas_de_la_precision.py` (14) |
| Otra tensión, caudal, rosca, giro, cantidad, otros dientes, otra fase o una reacondicionada son otra pieza | `parametros_que_chocan()` | `pruebas_de_la_revision.py` (pares de muestra), `pruebas_de_la_precision.py` (17) |
| Dos medidas coinciden con la tolerancia de cada una y la precisión con que se escribieron | `diferencia_que_se_acepta()` | `pruebas_de_la_precision.py` (18) |
| Un código leído de una foto nunca se acepta solo | `codigos_por_tipeo(de_una_foto=True)` | `pruebas_de_la_precision.py` (19) |
| Una ficha distinta al reimportar se avisa y no se pisa | `fichas_que_cambiaron()` | `pruebas_de_la_precision.py` (20) y en la app |
| Cada decisión guarda todo lo que había a favor y en contra | `marcar_revision()` | `pruebas_de_la_precision.py` (21) |
| Una revisión vence según el riesgo: a los 6 meses una pieza de seguridad, a los 12 una que rompe el motor y a los 36 el resto | `ficha_de_prueba()`, `MESES_DE_VIGENCIA_POR_RIESGO` | `pruebas_de_la_precision.py` (22) |
| Un cambio de reglas que hace pasar limpio algo rechazado se frena | La línea de base | `pruebas_de_la_revision.py --linea-base` |
| Lo que alguien rechazó y vuelve por otro camino sale «🔴 rechazada», no compite por el más barato ni por el margen y no va a la cotización | `anotar_el_respaldo()`, `no_compite_por_precio()`, `filas_para_cotizar()` | `pruebas_de_la_precision.py` (23) |
| Una ficha con algo en contra arranca diciendo qué; la de una pieza de seguridad dice si cada marca tiene CHAS | `ficha_de_prueba()` | `pruebas_de_la_precision.py` (22, 23) |
| Cada decisión queda en el historial con la lista y la versión de las reglas, y el historial no se corrige ni se borra | `marcar_revision()`, disparadores de `historial_de_revisiones` | `pruebas_de_la_precision.py` (24) |
| Cualquier «no le iba» (medida, rosca, ficha, lado, versión, le faltaba algo, hubo que modificarla) baja el vínculo; «vino fallada», no | `MOTIVOS_DE_NO_ERA_LA_PIEZA` | `pruebas_de_la_precision.py` (25) |
| El lado no es una variante: la rosca izquierda o el borne del otro lado no se agrupan con la otra | `codigo_base_sin_variante()`, `TRAMOS_DE_LADO` | `pruebas_de_la_precision.py` (26), `nucleo/pruebas.py` |
| Lo que no está confirmado sale «a confirmar» en WhatsApp y en el PDF, y con su veredicto en el Excel | `hay_que_confirmarla()` | `pruebas_de_la_precision.py` (27) |
| Aprobar en bloque nunca aprueba una pieza de seguridad | `aprobar_pendientes(en_bloque=True)` | `pruebas_de_la_precision.py` (28) |
| Corregir las medidas a mano vuelve a puntuar los vínculos de ese producto, y solo esos | `repuntuar_los_vinculos_de()` | `pruebas_de_la_precision.py` (29) |
| Una pieza de seguridad sin confirmar se muestra, pero no se corona «más barato» ni «mejor margen» | `no_se_recomienda()` | `pruebas_de_la_precision.py` (30) |
| Lo que falta medir va de lo que más identifica a la pieza a lo que menos | `ficha_de_prueba()`, `_PIEZAS_Y_SUS_MEDIDAS` | `pruebas_de_la_precision.py` (31) |
| Que no nombren autos en común avisa, pero no tumba la equivalencia | `autos_de_los_dos()` | `pruebas_de_la_precision.py` (32) |
| Lo que se exporta lleva el estado de cada vínculo, y los rechazados van aparte | `estado_del_vinculo()`, `exportar_catalogo_zip()` | `pruebas_de_la_precision.py` (34) |
| Si al volver a puntuar suben de franja demasiados vínculos de una vez, se avisa | `deriva_sospechosa()` | `pruebas_de_la_precision.py` (36) |
| La ficha dice qué se buscó en contra en las descripciones y cómo salió | `_lo_que_dicen_las_descripciones()` | `pruebas_de_la_precision.py` (37) |
| Cada medida cambiada a mano queda con lo que había; guardar sin cambios no anota nada | `actualizar_medidas()`, `historial_de_medidas()` | `pruebas_de_la_precision.py` (39) |
| Lo vendido sin estar confirmado queda como alternativa comercial y no confirma la equivalencia; la venta guarda el veredicto de ese momento | `registrar_venta()`, `_pares_vendidos()` | `pruebas_de_la_precision.py` (40) |
| Una familia con más devoluciones que el mes anterior se marca como empeorando | `tablero_de_calidad()` | `pruebas_de_la_precision.py` (41) |
| Una tanda automática que trae demasiado de una vez se avisa en la cola | `anomalia_de_la_tanda()` | `pruebas_de_la_precision.py` (42) |
| El lector de medidas no lee media pulgada («1/2X20»), la rosca de un tornillo («M11X012»), modelos («X1 X3 X4») ni un externo más de 8 veces el interno | `medidas_desde_descripcion()`, `_diametros_posibles()` | `pruebas_de_la_precision.py` (44), `nucleo.pruebas` |
| Un diámetro imposible no prueba nada, ni a favor ni en contra, y la ficha lo marca | `medidas_imposibles()`, `sin_diametros_imposibles()`, `comparar_medidas()` | `pruebas_de_la_precision.py` (44) |
| Lo que el lector leyó mal se descarta solo, nunca lo cargado a mano, nunca lo corregido después de listarlo, y queda en el historial de medidas | `medidas_mal_leidas()`, `descartar_medidas_mal_leidas()` | `pruebas_de_la_precision.py` (44) |
| Cada medida dice de dónde salió: de la descripción o a mano, quién y cuándo | `origen_de_las_medidas()`, `aplicar_medidas_deducidas()` | `pruebas_de_la_precision.py` (44, 46) |
| Cada medida dice qué diferencia la cambiaría (la explicación contrafactual) | `medidas_lado_a_lado()` | `pruebas_de_la_precision.py` (45) |
| Si cambia una medida que ya estaba después de aprobarla, la ficha deja de darla por verificada hasta que alguien la vuelva a mirar; completar una vacía no | `medidas_cambiadas_desde()`, `ficha_de_prueba()` | `pruebas_de_la_precision.py` (46) |
| El historial dice cómo se decidió cada par, una fila por par aunque llegue la ida y la vuelta, y desde cuándo esperaba en la cola | `marcar_revision()`, `_lo_que_dice_la_cola()`, `COMO_SE_DECIDIO` | `pruebas_de_la_precision.py` (46, 47) |
| Lo que dicen las descripciones veta aunque la medida no esté guardada; lo guardado manda | `evidencia_cruzada()`, `_medidas_con_lo_que_dice_el_texto()` | `pruebas_de_la_precision.py` (48) |
| Una pieza de seguridad o de riesgo alto necesita, aparte de la fuente, la evidencia mínima de su riesgo (o la comprobación en la mano) | `EVIDENCIA_MINIMA_POR_RIESGO`, `ficha_de_prueba()` | `pruebas_de_la_precision.py` (22, 49) |
| La venta guarda lo que la sostenía en ese momento, y el registro de errores lo muestra | `evidencia_de_la_fila()`, `registrar_venta()`, `registro_de_errores()` | `pruebas_de_la_precision.py` (41) |
| La métrica principal cuenta solo lo vendido como equivalente que volvió porque no era la pieza | `tablero_de_calidad()` | `pruebas_de_la_precision.py` (41) |
| Un caso de muestra sellado no se borra ni se le cambia lo que tiene que dar | `verificar_los_casos_sellados()`, `casos_sellados.txt` | `pruebas_de_la_revision.py` |
| El buscador, WhatsApp, el PDF, la venta y el ZIP dicen el mismo estado que la ficha de prueba | `anotar_el_estado()`, `estados_de_los_vinculos()`, `ficha_de_prueba(liviana=True)` | `pruebas_de_la_precision.py` (50, 53), `pruebas_de_la_revision.py --base` (una sola verdad) |
| Lo que no se pudo comprobar no sale confirmado | `anotar_el_estado()`, `veredicto_de_la_equivalencia()` | `pruebas_de_la_precision.py` (50) |
| El código de fábrica toma el rubro de los que lo citan, también en la ficha | `rubros_de_los_codigos_de_fabrica(ids)` | `pruebas_de_la_precision.py` (53) |
| Un texto donde va un número no entra a la base, y dice qué campo | `_esquema_numeros_que_son_numeros()` | `pruebas_de_la_precision.py` (51) |
| Una versión de reglas que mueve de franja el 40 % de lo cargado avisa | `deriva_sospechosa()` | `pruebas_de_la_precision.py` (53) |
| Lo vendido como equivalente que volvió, el cambio de reglas grande y las medidas imposibles aparecen en lo que necesita atención | `diagnostico_de_salud()` | `pruebas_de_la_precision.py` (53) |
| La copia diaria no solo se abre: se busca en ella y no puede tener vínculos huérfanos | `_usarla_como_la_usaria_el_mostrador()` | `pruebas_de_los_frenos.py` (6) |
| La versión anterior del programa trabaja sobre la base migrada por esta, y cada paso da lo que tiene que dar | — | `pruebas_de_compatibilidad.py --base` |
| Lo que suele cambiarse junto se avisa al vender; un combo borrado a mano no vuelve solo | `lo_que_suele_ir_con()`, `COMBOS_DE_FABRICA` | `pruebas_de_la_precision.py` (52) |
| Antes de vender, primero la pregunta que más separa | `ordenar_por_lo_que_separa()` | `pruebas_de_la_precision.py` (53) |
| Solo se recomienda lo buscado, lo 🟢 y lo 🟡 (lo 🟡 no, si es de seguridad); lo 🟠, 🔴, 🔵 y ⚪ se muestra pero no se corona | `no_se_recomienda()`, `la_recomendacion_explicada()` | `pruebas_de_la_precision.py` (30, 54) |
| La recomendación dice por qué, por qué no la más barata (o por qué ninguna) y el stock por clase, sin mezclar lo confirmado con lo que no | `la_recomendacion_explicada()`, `por_que_no_se_recomienda()` | `pruebas_de_la_precision.py` (54) |
| Primero lo que sirve, después lo que conviene: lo buscado, 🟢, 🟡, 🔵, 🟠, ⚪, 🔴, y dentro de cada uno el stock y el precio | `ordenar_por_seguridad_y_disponibilidad()`, `coronar_la_recomendada()` | `pruebas_de_la_precision.py` (54) |
| Si se vende otra que la recomendada, la venta lo anota, y el tablero cuenta cuántas y cuántas volvieron | `evidencia_de_la_fila(recomendada=)`, `ventas_contra_la_recomendacion()` | `pruebas_de_la_precision.py` (54, 55) |
| Una devolución por instalación, otro auto, transporte o error al entregar no baja el vínculo ni cuenta como error | `MOTIVOS_DE_DEVOLUCION`, `MOTIVOS_DE_NO_ERA_LA_PIEZA` | `pruebas_de_la_precision.py` (55) |
| «Vino fallada» es calidad de la marca, no equivalencia: se cuenta aparte y avisa si crece | `calidad_por_marca()`, `marcas_con_fallas_en_aumento()`, `diagnostico_de_salud()` | `pruebas_de_la_precision.py` (55) |
| La comprobación guiada: alcanza con que difiera una para rechazarla, y solo con todo coincidiendo se marca sin texto | `preguntas_para_comprobar()`, `resultado_de_la_comprobacion()`, `rechazar_por_la_comprobacion()` | `pruebas_de_la_precision.py` (56) |
| Practicar no cambia nada: mitad aprobados y mitad rechazados, primero los rechazos con motivo | `casos_para_practicar()`, `la_respuesta_del_caso()` | `pruebas_de_la_precision.py` (57) |
| Para no comprar, la equivalente tiene que estar confirmada y en stock | `equivalentes_confirmadas_con_stock()` | `pruebas_de_la_precision.py` (58) |
| Lo que el motor del auto ya dice (nafta o diésel) no se pregunta | `repuestos_de_este_auto()` | `pruebas_de_la_precision.py` (59) |
| Lo aprendido (marcas, instalaciones) suma, pero no hace pasar ninguna franja del buscador, de la ficha ni de la cola | `LINEAS_DE_CONFIANZA`, `sin_cruzar_la_linea_por_lo_aprendido()` | `pruebas_de_la_precision.py` (3, 60) |
| Vender y no oír nada no confirma: solo suma lo que alguien dijo que anduvo, y nunca lo que volvió | `registrar_que_anduvo()`, `pares_que_anduvieron()`, `seguimiento_de_lo_vendido()` | `pruebas_de_la_precision.py` (40, 61) |
| Lo que une dos redes grandes no se aprueba en bloque, y se ve primero | `cuanto_une_cada_par()`, `pares_que_unen_redes()`, `puentes_del_lote()`, `aprobar_pendientes(en_bloque=True)` | `pruebas_de_la_precision.py` (62) |
| Antes de borrar se dice lo que toca, y la papelera devuelve el producto con toda su historia | `impacto_de_borrar()`, `borrar_producto_con_papelera()`, `restaurar_de_papelera()` | `pruebas_de_la_precision.py` (63) |
| Un vínculo cargado y rechazado a la vez (y las otras relaciones imposibles) se ve y avisa | `relaciones_imposibles()`, `chequear_integridad_bd()`, `diagnostico_de_salud()` | `pruebas_de_la_precision.py` (64) |
| Una versión de las reglas no se publica con regresiones ni con un rechazo de seguridad que vuelve limpio | `imprimir_el_veredicto()` | `pruebas_de_la_revision.py --base --linea-base` |
| El mismo número en otra lista no tapa lo que la ficha sabe: si es otra pieza, el buscador lo dice; lo devuelto o rechazado tampoco queda tapado | `veredicto_de_la_equivalencia()` | `pruebas_de_la_precision.py` (65) |
| Lo 🔴 no se anota como vendido sin confirmarlo, y lo 🔴 de seguridad no se anota nunca, ni llamando de otro lado | `bloqueo_de_venta()`, `anotar_venta_y_avisar()`, `mostrar_boton_de_venta()` | `pruebas_de_la_precision.py` (66) y en la app |
| El historial de medidas no se corrige ni se borra | Disparadores de `historial_de_medidas` | `pruebas_de_la_precision.py` (46) |
| Un expediente tocado después de bajarlo no pasa la verificación | `expediente_en_texto()`, `verificar_el_expediente()` | `pruebas_de_la_precision.py` (68) |
| Lo vendido con un par que después se rechazó se ve, para avisarle al cliente | `vendido_con_lo_que_despues_se_rechazo()` | `pruebas_de_la_precision.py` (72) |
| La red con que se calcula cuánto une cada pendiente se rehace sola cuando cambian las equivalencias (alta, baja o un vínculo por otro) | `_red_de_equivalencias()` con su firma | `pruebas_de_la_precision.py` (62) |

## El stock, los precios y la plata

| Regla | Dónde se cuida | La prueba |
|---|---|---|
| Lo que otro cambió mientras se editaba (precio, stock, costo) no se pisa | `actualizar_precio_stock()` con lo mostrado, campo por campo; `valor_con_que_se_abrio()` | `pruebas_de_los_frenos.py` (15b) y en la app con dos sesiones |
| «Completar medidas» no pisa lo cargado a mano, y una medida en blanco cuenta como vacía | `aplicar_medidas_deducidas()`: completa solo lo que sigue vacío con el candado tomado; `medida_vacia()` | `pruebas_de_los_frenos.py` (13), `pruebas_de_la_precision.py` (44) |
| Lo apartado nunca pasa el stock | `reservar_stock()` en una transacción | `pruebas_de_carga.py` |
| El mismo remito no suma el stock dos veces | `aplicar_carga_remito()` con huella | `pruebas_de_los_frenos.py` (14) |
| Un pedido al depósito se entrega y se cobra una sola vez | `entregar_pedido()` | `pruebas_de_carga.py` |
| El límite de crédito no se pasa, ni con varios pidiendo o cargando a la vez, ni con el precio de antes de esperar; el cargo a mano también cuenta lo pedido sin entregar | `pedir_al_deposito()` y `cargar_a_la_cuenta()`: el precio, el saldo y el límite adentro de la transacción | `pruebas_del_deposito.py`, `pruebas_de_las_cuentas.py` (ocho a la vez) |
| El saldo de una cuenta es lo entregado menos lo pagado | `estado_de_cuenta()` | `pruebas_de_carga.py` |
| El interés por mora solo en las cuentas que lo tienen prendido, y nunca dos veces los mismos días | `cargar_el_interes_por_mora()` | `pruebas_de_las_cuentas.py` |
| Un presupuesto guardado no cambia si después cambia un precio | Se guarda con sus precios (`items_json`) | `pruebas_de_los_frenos.py` (10) |
| Un presupuesto no se guarda dos veces por un doble toque, ni desde otro proceso | `guardar_presupuesto_mecanico()` en `transaccion()` | `pruebas_de_los_frenos.py` (10) |
| Una importación que se corta a la mitad no deja nada; entera, entra entera | La transacción de `pantallas/cargar_excel.py` | `pruebas_de_la_sesion.py` (2c) |
| Un ajuste de precios por porcentaje anota el historial, no toca los de precio 0, va de −99 % a 1000 % y es del administrador | `aumentar_precios_por_marca()` | `pruebas_de_los_cambios.py` |
| El margen es sobre el precio de venta | `margen_de()` | `pruebas_de_los_cambios.py` |
| Una reserva vendida descuenta del stock una sola vez; cancelada, solo libera | `cerrar_reserva()` | `pruebas_de_los_cambios.py` |
| En una lista sin títulos, una columna de importes nunca se toma por el código | `adivinar_columnas_por_datos()`, `_parecen_precios()` | `pruebas_de_los_cambios.py` (9b) |
| Una lista con un precio que salta mucho no lo pisa (el stock sí), y se compara con el último precio de verdad si el guardado quedó en 0 | `poner_precio_y_stock_de_la_lista()` | `pruebas_de_los_cambios.py` |
| «Aplicar igual» lo frenado es del administrador, todo o nada | `aplicar_precios_frenados()` | `pruebas_de_los_cambios.py` |
| El buscador dice de cuándo es el precio de cada lista, y marca lo viejo | `fecha_de_la_lista()`, `texto_de_la_fecha_de_los_precios()` | `pruebas_de_la_precision.py` (71) |

## Las cuentas y los permisos

| Regla | Dónde se cuida | La prueba |
|---|---|---|
| Cada cuenta tiene su clave (la clave sola dice quién entra) | `clave_ya_usada()` | `pruebas_de_los_frenos.py` (12) |
| El freno de intentos vale para todos, también para los talleres | `validar_password(con_mecanicos=True)` | `pruebas_de_los_frenos.py` (7) |
| Un taller ve su portal y nada más | `mostrar_portal_mecanico()` | `pruebas_de_la_sesion.py` (4) |
| Las funciones sensibles vuelven a mirar quién está adentro (también borrar, fusionar, deshacer, aprobar, cobrar, restaurar, la ficha y el motor del vehículo, el link de una marca y aplicar los precios frenados) | `exigir_nivel()` | `pruebas_de_los_cambios.py` (5) |
| Pasar el límite de crédito: lo pide el empleado y lo da solo un administrador, por un monto y 24 horas | `pedir_permiso_de_limite()`, `contestar_permiso_de_limite()`, `margen_autorizado()` | `pruebas_de_las_cuentas.py`, `pruebas_del_deposito.py` |
| Un empleado desactivado o con otro rol pierde los permisos al instante | `nivel_vigente_de_la_sesion()` | `pruebas_de_la_sesion.py` |
| Después de «Salir» no queda nada del anterior | `cerrar_sesion()` | `pruebas_de_la_sesion.py` |
| Ir a otra pantalla y volver no borra la búsqueda, los filtros ni la solapa elegida | `recordar_lo_elegido_al_cambiar_de_pantalla()` | `pruebas_de_la_sesion.py` (2b), `auditar.py` (6d) |
| A quien vende le llega un aviso cuando otro cobra o pone a cuenta su venta, o el depósito entrega o no encuentra lo que pidió; lo que hizo él mismo, no | `novedades_de()` | `pruebas_de_la_caja.py` (9d) |
| Lo que corre solo cada pocos segundos (lo que espera en la caja, los avisos a quien vende) va por un índice que achica, sin recorrer las ventas ni los pedidos de la historia | `ventas_a_cobrar()`, `novedades_de()`, `idx_ventas_de_quien`, `idx_pedidos_deposito_de_quien` | `pruebas_de_la_caja.py` (9e) |
| La venta y el presupuesto a medio armar sobreviven a una recarga: se avisa al entrar, se recuperan con cantidades, precios, cliente y lo destildado, y terminada la venta no queda guardada; solo lo del día y solo a quien lo armaba | `guardar_lo_que_se_esta_armando()`, `recuperar_la_venta_a_medio_armar()`, `recuperar_el_presupuesto_a_medio_armar()` | `pruebas_de_la_sesion.py` (5) |
| La ganancia por marca del período: la que más ganó primero, el margen sobre lo vendido con costo, lo vendido sin costo aparte y la ganancia a costo de hoy (reposición) | `ganancia_por_marca()` | `pruebas_de_las_ventas.py` (13) |
| Un código que no aparece ofrece como botón los que se escriben casi igual, y tocarlo los busca | `codigos_por_tipeo()`, `mostrar_lista_clickeable()` | `pruebas_de_las_pantallas.py` |
| Ajustar los precios de una marca solo en lo que dice ciertas palabras (sin acentos ni mayúsculas); un «%» tipeado no toca nada | `aumentar_precios_por_marca(…, que_dice)`, `_solo_la_linea()` | `pruebas_de_los_cambios.py` |
| El presupuesto del Buscador se manda derecho por WhatsApp, con lo que tiene y el total | — | `pruebas_de_las_pantallas.py` |
| Todas las pantallas y solapas se dibujan sin errores, sin contraseña, como operador y como administrador, también con los desplegables perezosos abiertos | — | `pruebas_de_las_pantallas.py` |
| Sin sesión, «📲 Consultar por WhatsApp» le escribe al negocio con lo que se buscó (si el número está cargado); con sesión no sale | `boton_para_consultar()`, `texto_para_consultar()` | `pruebas_de_las_pantallas.py`, `pruebas_del_buscador.py` (2d) |
| En las tablas de resultados, «s/d» donde no se sabe el stock | `con_stock_legible()` | `pruebas_del_buscador.py` (2d) |
| Si lo escrito no está: el código con la marca que la lista pega atrás, y sin la marca escrita adelante o atrás, solo si lo que queda existe y siempre con aviso; si el número pelado es otro producto, ese | `buscar_con_variantes_del_cero()`, `marcas_que_se_escriben_con_el_codigo()` | `pruebas_del_buscador.py` (2f) |
| Lo que se dibuja debajo de los resultados se calcula una vez por clave y otra vez si entra un producto o cambia un vínculo; de cada cosa, las últimas 24 | `recordado_mientras_no_cambie()`, `testigo_de_los_vinculos()` | `pruebas_del_buscador.py` (2e) |
| Sin sesión, la barra tiene solo las secciones abiertas y los resultados no muestran nada del mostrador (ni apagado ni con candado) | `PAGINAS_ABIERTAS`, `solo_mirar()`, `COLUMNAS_DEL_NEGOCIO` | `pruebas_de_las_pantallas.py` |
| Sin sesión, ni los links al sitio del proveedor ni sus catálogos, y las búsquedas recientes son las de esa visita (no las de otros clientes) | `solo_mirar()`, `historial_reciente()` | `pruebas_de_las_pantallas.py` |
| Un solo «ℹ️ Cómo funciona» plegado arriba de cada pantalla, con para qué sirve la sección, la solapa y la ayuda de la pantalla; la ayuda de una parte queda en su parte | `empezar_la_ayuda_de_la_pantalla()`, `elegir_solapa()`, `ayuda()` | `pruebas_de_la_sesion.py` (2d) |
| Con la base dañada, los empleados solo pueden buscar | `modo_solo_lectura()` | `pruebas_de_los_frenos.py` (1) |

## Las copias

| Regla | Dónde se cuida | La prueba |
|---|---|---|
| Borrar una marca guarda sus productos (con fotos y firmas) y la historia de cada uno, y se restaura aunque se haya vuelto a importar | `eliminar_marca_con_papelera()`, `_reponer_marca_y_productos()` | `pruebas_de_los_cambios.py` |
| La copia en partes se junta al bajarla, y si falta una no se usa | `bajar_la_copia_de_github()` | `pruebas_de_las_copias_en_github.py` |
| El backup completo se restaura con sus fotos | `generar_backup_completo()` | `pruebas_de_la_recuperacion.py` |
| Restaurar (o cambiar una base dañada por otra) olvida lo guardado de la base anterior: cobertura, escala de precios, marcas con CHAS, la red | `olvidar_lo_guardado_de_la_base()`, `MEMORIAS_DE_LA_BASE` | `pruebas_de_la_recuperacion.py` (también controla que cada memoria del proceso esté clasificada) |
| Restaurar deja la base sana y con los mismos datos, también desde la copia cifrada de GitHub | `restaurar_backup()` | `pruebas_de_los_frenos.py` (16) |
| La copia sin cifrar no sube a un repositorio público | `se_puede_subir_sin_cifrar()` | `pruebas_de_las_copias_en_github.py` |
| Si la última vuelta no pudo subir, la pantalla dice «atrasada» y desde cuándo, nunca «al día» | `cuanto_perderias_si_reinicia()` | `pruebas_de_las_copias_en_github.py` |
| La frase que propone la app para `clave_copia` es al azar, larga y no rompe los secretos | `frase_para_la_copia()` | `pruebas_de_las_copias_en_github.py` |
| La prueba de la copia mira las claves foráneas de todas las tablas | `_usarla_como_la_usaria_el_mostrador()` | `pruebas_de_las_copias_en_github.py` |
| Lo que empieza con «=» va como texto al Excel | `to_excel_bytes()` | `pruebas_de_los_frenos.py` |
| Un backup dañado no entra ni toca nada | `la_base_esta_sana()` antes de restaurar | `pruebas_de_los_frenos.py` (16), `pruebas_de_la_recuperacion.py` |
| Una base dañada (cortada, con el encabezado roto o que no es una base) no se sube y no pisa la copia buena | `subir_backup_a_github()` con `la_base_esta_sana()` | `pruebas_de_las_copias_en_github.py` |
| Si el catálogo cae a la mitad, la copia buena no se pisa sola | `subir_la_copia_si_cambio()` | `pruebas_de_los_frenos.py` (5) |
| La copia de GitHub se puede recuperar (se prueba sola cada día) | `verificar_la_copia_de_github()` | `pruebas_de_los_frenos.py` (6) |
| Quedan copias anteriores (7 diarias, 4 semanales, 6 mensuales) | `copias_a_guardar()` | `pruebas_de_las_copias_en_github.py` |
| Subir la base no borra las fotos de la rama | `_publicar_en_la_rama()` | `pruebas_de_las_copias_en_github.py` |
| La base que no se puede leer abre en modo recuperación | `mostrar_modo_recuperacion()` | `pruebas_de_la_recuperacion.py` |

## El código

| Regla | Dónde se cuida | La prueba |
|---|---|---|
| El auditor y todas las pruebas corren solos en cada subida a `main` y a las ramas de trabajo | `.github/workflows/pruebas.yml`, `.github/correr_las_pruebas.py` | GitHub Actions (la ✗ roja y el mail) |
| El vigía de la copia y la tanda de fondo corren el código de ahora, no el con que arrancó el servidor | `llego_otra_version_de_la_logica()` | `pruebas_de_las_copias_en_github.py` |
| `nucleo/` se regenera desde `logica/` y está al día | `nucleo/generar.py` | `auditar.py` (lo regenera aparte y compara) |
| Ningún archivo tiene escrita la carpeta de una máquina | — | `auditar.py` |
| Un error anotado no lleva claves ni contraseñas | `tapar_lo_sensible()` | `pruebas_de_los_frenos.py` (8), `nucleo/pruebas.py` |
| Una búsqueda que falla no se confunde con «no hay» | El buscador | `pruebas_del_buscador.py` |
| Las librerías son las que se probaron | `requirements.txt` con rangos | Correr las pruebas con esas versiones |
| Un dato que se calcula no se pisa antes de que alguien lo lea | — | `auditar.py` (control 6e) |
| Ningún diccionario escrito a mano tiene la misma clave dos veces | — | `auditar.py` (control 6f) |
| El VIN mal copiado se avisa en la pantalla («mal», no None ni False) | `decodificar_vin()` con `verificar_vin()` | `pruebas_de_los_cambios.py` (9c) |
| El país del VIN y del código de barras sale de las tablas de la norma (ISO 3779, GS1) | `PAISES_VIN_2`, `PREFIJOS_GS1` | `pruebas_de_los_cambios.py` (9c), `nucleo/pruebas.py` |
| Los códigos de falla dicen lo que dice la norma, y al actualizar se corrigen sin pisar lo editado a mano | `_dtc_sistematicos()`, `SEMILLA_DTC_VERSION` | `pruebas_de_los_cambios.py` (9d) |
| Un año que no puede ser de un auto no se toma, y los ya guardados se releen una vez | `extraer_anios()`, `_corregir_anios_imposibles_de_aplicaciones()` | `nucleo/pruebas.py`, `pruebas_de_los_cambios.py` (9e) |
| «Según el catálogo del fabricante» muestra solo lo que vino de un catálogo, nunca lo deducido de una descripción | `buscar_aplicaciones()` | `pruebas_de_repuestos_por_auto.py` |
| Una motorización o una versión (MPFI, SDI, GLX…) no es un modelo de auto, y las ya deducidas se borran una vez | `MOTORIZACIONES_QUE_NO_SON_MODELO`, `_borrar_modelos_que_no_son_autos()` | `pruebas_de_los_cambios.py` (9e) |
| El conversor de unidades sale de definiciones exactas y cada conversión va y vuelve al mismo número | `CONVERSIONES_DE_TALLER`, `convertir_unidad()` | `pruebas_de_los_cambios.py` (9c bis) |
| Un error de tipeo se corrige solo si la palabra no aparece en ningún producto, y la pantalla lo dice | `palabras_corregidas()`, `texto_con_las_correcciones()` | `pruebas_del_buscador.py` (2c) |
| La escala de precios de cada lista se ve contra cada proveedor, no solo el promedio | `escala_de_precios_por_marca()` («por_proveedor») | `pruebas_de_los_cambios.py` (9f) |
| La limpieza de una vez de las aplicaciones se reintenta cada día hasta que sale | `_tareas_automaticas_del_dia()` | `pruebas_de_los_cambios.py` (9e) |
| El precio de una lista fuera de escala no sale en la cotización (WhatsApp ni PDF) | `precio_para_el_cliente()` | `pruebas_de_los_cambios.py` (8) |
| La auditoría de stock sortea solo lo que tiene stock cargado, y sin stock no hay diferencia | `generar_auditoria_hoy()`, `registrar_conteo_auditoria()`, `texto_del_conteo()` | `pruebas_de_los_cambios.py` (9g) |
| Un cliente se encuentra por teléfono como sea que esté anotado | `historial_de_un_cliente()` | `pruebas_de_los_cambios.py` (9h) |
| Un código de barras que no cierra o que ya tiene otro producto de la misma lista no se pega | `cargar_codigos_de_barras_masivo()` | `pruebas_de_los_cambios.py` (9i) |
| La alerta del «.0» cuenta lo mismo que arregla su botón | `_RE_DECIMAL_DE_EXCEL`, `contar_codigos_con_decimal()` | `pruebas_de_los_cambios.py` (9j) |
| Un código viejo tiene un reemplazo vigente, sin círculos, y cambiarlo es todo o nada | `guardar_reemplazo()` | `pruebas_de_los_cambios.py` (9k) |
| Lo que borra y vuelve a escribir en una tabla va en una transacción | — | `auditar.py` (control 15) |
| Los datos de cobro (alias, CBU, QR) los cambia solo un administrador, y el CBU/CVU cierra con sus dígitos verificadores | `guardar_alias_transferencia()`, `problema_del_cbu()` | `pruebas_de_los_cambios.py` (5, 9l) |
| El coeficiente de una lista, activar un taller y confirmar una sugerencia miran el permiso adentro | `guardar_coeficiente_de_lista()`, `activar_desactivar_mecanico()`, `confirmar_candidata()` | `pruebas_de_los_cambios.py` (5, 9m) |
| El QR de cobro abre el link de pago si hay, el link se controla (https, sin usuario adentro) y va al final del mensaje | `problema_del_link_de_pago()`, `texto_para_pagar()`, `generar_pdf_cotizacion()` | `pruebas_de_los_cambios.py` (9l bis) |
| El cliente ve su auto solo con la clave del link o los 4 números del teléfono, sin datos personales y con tope de intentos | `abrir_ficha_publica()`, `resumen_publico_del_auto()`, `link_publico_del_auto()` | `pruebas_de_los_cambios.py` (9l ter) |
| Cuánto le falta a cada pieza sale de la última vez que se cambió, igual para el negocio y para el cliente | `estado_de_cada_pieza()`, `a_quien_avisar()` | `pruebas_de_los_cambios.py` (9l ter) |
| Una pieza anotada queda atada al producto del catálogo solo si el código no deja dudas, y sin vida útil usa la de las otras veces | `agregar_pieza_historial()`, `producto_del_codigo_anotado()`, `vida_util_de_las_otras_veces()` | `pruebas_de_los_cambios.py` (9l ter) |
| El link del cliente anda aunque la patente esté frenada por intentos con los 4 números, y el km que escribe el cliente no se guarda | `abrir_ficha_publica()`, `resumen_publico_del_auto()` | `pruebas_de_los_cambios.py` (9l ter) |
| Un invitado (y un mecánico externo) no puede anotar ni cambiar nada desde las secciones abiertas: cada función que escribe pide el permiso adentro | `exigir_nivel()`, `solo_mirar()` | `pruebas_de_los_cambios.py` (5), `auditar.py` (control 16) |
| La patente se encuentra como esté escrita, y guardarla de otra forma no duplica la ficha | `buscar_vehiculo()`, `get_or_create_vehiculo()`, `guardar_numero_de_motor()` | `pruebas_de_los_cambios.py` (9l ter) |
| Una pieza vence por km o por tiempo, lo que llegue primero, desde su último cambio (aunque se haya anotado sin km) | `estado_de_cada_pieza()`, `a_quien_avisar()`, `_sumar_meses()` | `pruebas_de_los_cambios.py` (9l ter) |
| Los atrasados, el aviso por WhatsApp y el PDF de la ficha usan la misma cuenta que el link del cliente | `listar_vehiculos_atrasados()`, `generar_pdf_ficha_vehiculo()` | `pruebas_de_los_cambios.py` (9l ter) |
| Descartar una lista entera de pendientes es de administrador; los pares elegidos, de empleado | `rechazar_pendientes()` | `pruebas_de_los_cambios.py` (5) |
| Una venta descuenta el stock sin dejarlo negativo, guarda el precio de ese momento y aprende lo vendido, todo o nada; anular devuelve lo descontado | `cerrar_venta()`, `anular_venta()` | `pruebas_de_las_ventas.py` |
| Del presupuesto a la venta pasa solo lo marcado en «Se lleva» (todo, si no se toca nada); lo destildado queda en el presupuesto, destildado | `pasar_el_presupuesto_a_una_venta()`, `se_lleva()` | `pruebas_de_las_ventas.py` |
| En Ventas, lo 🔴 en lugar de lo pedido se confirma, y el 🔴 de seguridad no se vende como reemplazo; lo vendido se aprende con su veredicto y cómo se vendió | `cerrar_venta()`, `sumar_a_la_venta()` | `pruebas_de_las_ventas.py` (8) |
| Anular una venta saca de la ficha del auto sus piezas y lo aprendido de ella | `anular_venta()` | `pruebas_de_las_ventas.py` (5) |
| El cierre de caja de un día: por forma de pago y por quién atendió, sin lo anulado | `cierre_de_caja()` | `pruebas_de_las_ventas.py` (9) |
| Al vender: lo que suele ir con lo vendido y no está, y lo que se quedó sin stock | `lo_que_suele_ir_con_la_venta()`, `lo_que_se_termino()` | `pruebas_de_las_ventas.py` (9) |
| Escanear suma solo el código de barras que cierra y es de un solo producto | `producto_por_codigo_de_barras()` | `pruebas_de_las_ventas.py` (12) |
| El comprobante de una venta, en texto y PDF, dice que no es factura | `texto_del_comprobante()`, `pdf_del_comprobante()` | `pruebas_de_las_ventas.py` (11) |
| La ganancia usa el costo de cuando se vendió, y solo lo que tiene costo | `cierre_de_caja()`, `lo_mas_vendido()` | `pruebas_de_las_ventas.py` (10, 13) |
| Lo que más se vende: sin anuladas, todos los días del período | `lo_mas_vendido()` | `pruebas_de_las_ventas.py` (13) |
| Devolver una cosa de una venta: el stock (salvo lo que no se puede volver a vender), la plata del cierre de ese día, lo aprendido si se vendió en lugar de otro código; una venta con devoluciones no se anula | `devolver_de_una_venta()`, `cierre_de_caja()`, `anular_venta()` | `pruebas_de_las_ventas.py` (14) |
| Buscar una venta por número, cliente, patente o teléfono | `buscar_ventas()` | `pruebas_de_las_ventas.py` (14) |
| El arqueo: lo contado contra el efectivo esperado | `arquear_la_caja()`, `efectivo_esperado()` | `pruebas_de_las_ventas.py` (15, 16) |
| Lo que se va a terminar con lo que se vende | `lo_que_se_va_a_terminar()` | `pruebas_de_las_ventas.py` (16) |
| Lo entregado para Mostrador queda a nombre de quien lo pidió hasta venderlo, facturarlo o devolverlo | `lo_que_tiene()`, `quien_tiene_que_devolver()` | `pruebas_de_lo_que_queda_afuera.py` |
| Vender lo que ya se tiene del depósito no baja el stock otra vez ni anota dos veces lo aprendido; anular lo vuelve a su nombre | `cerrar_venta()`, `anular_venta()` | `pruebas_de_lo_que_queda_afuera.py` |
| Vuelve al stock solo lo escaneado con la etiqueta nuestra (no el código original de la caja), una unidad por escaneo, nunca más de lo que la persona tiene, con su contraseña o la de un administrador, recibido por otra persona; todo o nada | `devolver_lo_escaneado()`, `que_es_lo_escaneado()`, `quienes_tienen_lo_escaneado()` | `pruebas_de_lo_que_queda_afuera.py` |
| Lo de un taller no vuelve: no está afuera y nadie lo descarga | `lo_que_tiene()`, `devolver_lo_escaneado()` | `pruebas_de_lo_que_queda_afuera.py` (9) |
| El código nuestro: «CH» + número + dígito verificador; un dígito mal leído no es nada | `codigo_nuestro()`, `producto_por_codigo_nuestro()` | `pruebas_de_lo_que_queda_afuera.py` (1) |
| Las etiquetas se pueden leer (barra fina de 0,25 mm o más) y entran en la etiqueta | `pdf_de_etiquetas()`, `productos_para_etiquetar()` | `pruebas_de_lo_que_queda_afuera.py` (12) |
| Lo que llega a 0 al vender o al entregar se anota solo para reponer, una vez | `anotar_lo_que_se_termino()` | `pruebas_de_lo_que_queda_afuera.py` (13), `pruebas_de_las_ventas.py` (16) |
| «Sumar a la venta» lo que se tiene del depósito, con su cantidad | `sumar_lo_que_tengo_a_la_venta()` | `pruebas_de_lo_que_queda_afuera.py` (11) |
| El plano en letras: estanterías, módulos, entrada, y lo que no se entiende dicho en palabras | `leer_plano()` | `pruebas_del_mapa.py` (1) |
| Armado rápido, sumar, mover y sacar estanterías, sin pisar otra cosa | `armado_rapido()`, `sumar_estanteria()`, `mover_estanteria()`, `sacar_estanteria()` | `pruebas_del_mapa.py` (2, 3) |
| Las distancias son caminando por el pasillo; lo que no se alcanza va al final | `planear_el_recorrido()` | `pruebas_del_mapa.py` (4) |
| Una ubicación es un lugar del mapa que existe (módulo y estante incluidos), y se guarda escrita como en el mapa | `leer_ubicacion()`, `lugar_en_el_mapa()`, `ubicar_producto()` | `pruebas_del_mapa.py` (5, 8, 9) |
| Las estanterías tienen código único en todos los depósitos; cambiarlo pasa lo ubicado al código nuevo | `guardar_plano()`, `guardar_estanteria()` | `pruebas_del_mapa.py` (7, 13) |
| Guardar un plano que deja productos fuera del mapa se avisa antes | `lo_que_se_pierde_con()`, `guardar_plano()` | `pruebas_del_mapa.py` (12) |
| La cola por piso: por ubicación, o la más cerca de lo último que entregó ESE usuario en ese piso dentro de los minutos del piso | `la_cola_por_piso()`, `elegir_orden_de_la_cola()` | `pruebas_del_mapa.py` (14, 15) |
| Ubicar escaneando, o pegando una lista: solo lo que está bien | `que_es_lo_escaneado_al_ubicar()`, `ubicar_de_una_lista()` | `pruebas_del_mapa.py` (10, 11) |
| Dónde poner lo que no tiene lugar: lugares libres, primero la planta baja, cerca de la entrada y a la altura de la cintura | `lugares_sugeridos()` | `pruebas_del_mapa.py` (17) |
| Los del depósito ven solo el depósito; el administrador nunca queda limitado | `es_del_deposito()`, `cambiar_solo_deposito()` | `pruebas_del_mapa.py` (19) |
| Armar y ubicar, un empleado; borrar un piso o un depósito, el administrador | `exigir_nivel()` | `pruebas_del_mapa.py` (20) |
| Los lados de una estantería: códigos únicos en todo (estanterías y lados); se llega por el pasillo de ese lado; cambiar o sacar un código mueve lo ubicado sin mezclarlo; sacar la estantería o borrar el piso se lleva sus lados | `guardar_lados()`, `lugar_en_el_mapa()`, `la_cola_por_piso()`, `lo_que_se_pierde_con()` | `pruebas_del_mapa.py` (18b, 21) |
| Lo que manda el vendedor espera en la caja: el stock baja ya, no cuenta en el cierre hasta cobrarlo y no se devuelve sin cobrar | `cerrar_venta(a_la_caja=True)`, `ventas_a_cobrar()`, `cierre_de_caja()` | `pruebas_de_la_caja.py` (2, 4) |
| F10: la forma de pago, cuotas solo con crédito, descuento de 0 a 50% en cada cosa de la venta; se cobra una sola vez | `cobrar_venta()`, `total_con_descuento()` | `pruebas_de_la_caja.py` (3, 9b) |
| F11: a la cuenta de la venta (o la elegida, si era de Mostrador), activa, con su descuento, su plazo y su límite; si no entra no cambia nada; anular anula el cargo y devolver se le acredita | `poner_a_cuenta()`, `anular_venta()`, `devolver_de_una_venta()` | `pruebas_de_la_caja.py` (5, 6, 7, 9b) |
| El día de la caja es el día que se cobró; apagada la caja aparte, se cobra al terminar | `ventas_del_dia()`, `cierre_de_caja()`, `caja_aparte()` | `pruebas_de_la_caja.py` (8, 9) |
| Uno más, uno menos y quitar, en la venta y en el presupuesto (el menú del click derecho) | `cambiar_cantidad_en_la_venta()`, `quitar_de_la_venta()`, `quitar_del_presupuesto()` | `pruebas_de_las_ventas.py` (7, 7b) |
| Lo de arriba de la caja: el cajón (efectivo menos lo devuelto), tarjeta y transferencia, lo puesto a cuenta aparte y lo que espera | `resumen_de_la_caja()` | `pruebas_de_la_caja.py` (9c) |
| El cartel de un pedido nuevo del depósito: qué, cuánto, para quién y quién lo pidió, sin precios | `el_aviso_del_pedido()` | `pruebas_del_deposito.py` |
| Los desplegables y recuadros tienen clave: no se cierran solos cuando cambia su título | — | `auditar.py` (8f) |
| Ningún texto muestra dos «$» sin escapar (Streamlit los toma como una fórmula), tampoco los que pone `formato_precio()` | `formato_precio(…, en_markdown=True)` | `auditar.py` (8e) |
| Lo de cada cuenta: un empleado ve lo suyo, el administrador todas | `resumen_de_la_cuenta()`, `cuentas_para_mirar()` | `pruebas_de_lo_que_queda_afuera.py` |
| Al terminar la venta, la patente y los km anotan cada pieza en la ficha del auto, una sola vez, y frenan los km para atrás | `anotar_la_venta_en_el_auto()`, `nombre_de_la_pieza()` | `pruebas_de_las_ventas.py` |
| Un aviso por cliente con todo lo que le toca; «Ya le avisé» lo saca de la lista 15 días | `avisos_por_cliente()`, `marcar_avisado()` | `pruebas_de_los_cambios.py` (9l ter) |
| Un mecánico solo lee y escribe su propia cuenta | `exigir_que_sea_su_cuenta()` | `pruebas_de_los_cambios.py` (5) |
| Fusionar dos productos no pierde lo que apunta al que se va (apartados, ventas, pedidos, fichas, pendientes) | `fusionar_productos()` | `pruebas_de_la_plata_y_el_stock.py` |
| Apartar contra el stock libre, pagos y cargos de las cuentas, mejor margen | `reservar_stock()`, `registrar_pago_de_cuenta()`, `mejor_margen_entre_equivalentes()` | `pruebas_de_la_plata_y_el_stock.py` |
| Otro producto de la misma lista que lo buscado es otra pieza (salvo variantes, mellizos FISPA/LUCAS y reemplazos): el buscador lo marca y no lo cuenta, la ficha lo da en rojo, «solo confiables» lo saca | `otra_pieza_de_la_misma_lista()`, `evidencia_cruzada()`, `marcar_cadenas_que_no_aguantan()` | `pruebas_de_la_precision.py` (75) |
| El costo con la bonificación del proveedor: se calcula para lo que no tiene costo, sigue al precio (aumentos, importaciones, altas), no toca lo cargado a mano, y sacarla saca solo lo calculado | `guardar_bonificacion_del_proveedor()`, `_esquema_costo_por_bonificacion()`, `actualizar_precio_stock()` | `pruebas_de_la_plata_y_el_stock.py` (6) |
| Qué tan completo está el catálogo, por lista y con «Todas» al final | `que_tan_completo_esta_el_catalogo()` | `pruebas_de_la_plata_y_el_stock.py` (7) |
| El descarte automático viene apagado; prendido descarta solo lo 🔴 y los kits con su pieza (nunca aprueba), lo firma «🤖 la app», no cuenta para lo aprendido y se devuelve todo a la cola | `descartar_solos_los_casi_seguro_mal()`, `devolver_lo_que_descarto_sola()`, `aprender_de_las_decisiones()` | `pruebas_de_la_precision.py` (80), `pruebas_de_la_sesion.py` (6) |
| Lo que solo se alcanza pasando por otra pieza de la misma lista queda 🟠 para revisar, no cuenta y «solo confiables» lo saca; si hay otro camino, nada | `ficha_de_prueba()`, `camino_entre(evitar=)`, `anotar_el_estado()` | `pruebas_de_la_precision.py` (78) |
| Dos de la misma lista que citan el mismo número de fábrica son la misma pieza | `otra_pieza_de_la_misma_lista()` | `pruebas_de_la_precision.py` (75) |
| «Hay N más» no cuenta lo que la búsqueda ya marcó como otra cosa; 🕸️ lista los unidos a 3 piezas distintas de una lista, y aprobado como universal deja de salir | `equivalentes_mas_alla_del_tope()`, `unidos_a_piezas_distintas()` | `pruebas_de_la_precision.py` (79) |
| Las medidas de una bujía salen de su código (NGK, Bosch, el que cita la descripción); si dos códigos del mismo producto no coinciden, ninguno; lo que no se sabe leer no tiene medidas | `medidas_de_la_bujia()` | `pruebas_de_la_precision.py` (82) |
| Dos bujías que calzan igual (rosca, largo, hexágono, asiento, material) suman a favor, no se vetan por el auto ni son «otra pieza» de la misma lista; la que no entra se veta; si solo cambia el material decide el NGK | `evidencia_cruzada()`, `otra_pieza_de_la_misma_lista()`, `los_une_un_numero()` | `pruebas_de_la_precision.py` (82) |
| La app aprueba las de la cola y une las que calzan (también lo rechazado antes de esto, nunca lo rechazado después), no lo repite, y deshacer devuelve cada par a como estaba y lo apaga | `relacionar_las_bujias_que_calzan()`, `deshacer_lo_de_las_bujias()` | `pruebas_de_la_precision.py` (82) |
| En el buscador, la bujía que calza dice su grado al lado del de lo buscado, y un vínculo de bujías que calzan no se encadena | `anotar_el_grado_de_las_bujias()`, `buscar_por_codigo()` | `pruebas_de_la_precision.py` (82) |
| Entre las confirmadas, primero la bujía del mismo grado (o el más cercano) y la 🏆 también, diciendo por qué no la más barata | `ordenar_por_seguridad_y_disponibilidad()`, `la_recomendacion_explicada()` | `pruebas_de_la_precision.py` (82) |
| Dos listas distintas que citan el mismo número de fábrica (el nodo aprobado o el que trajo la lista, o el mismo número largo en las dos) no se vetan por el auto ni el motor; lo que contradice la pieza sí, si cambia el nombre de la pieza vale lo del auto, dentro de una misma lista el auto sigue contando, y con el nodo de fábrica de un lado no se vuelve a comparar (su descripción puede ser de otra pieza). La ficha y el buscador dicen lo mismo | `los_une_un_numero()`, `numero_de_fabrica_en_comun()`, `lo_que_vale_sin_el_auto()`, `evidencia_cruzada()`, `marcar_cadenas_que_no_aguantan()` | `pruebas_de_la_precision.py` (81) |
| El abanico se pregunta desde el lado con más opciones, y trae ⭐ la que ya es su equivalente por vínculos aprobados (🔗) | `abanicos_para_elegir()`, `pieza_sugerida_del_abanico()`, `tabla_del_abanico()` | `pruebas_de_la_precision.py` (76, 77) |
| Buscando un código, lo que espera aprobación de ese producto: contado en el título, con el mismo veredicto que la revisión de su lista, aprobar lo trae a la tabla sin anotar la búsqueda otra vez, lo rojo se descarta junto y el invitado no lo ve | `cuantos_esperan_aprobacion()`, `lo_que_espera_aprobacion()` | `pruebas_del_buscador.py` (2g) |
| Las sugerencias por descripción no comparan lo que firmas_compatibles() rechaza siempre, y no dejan afuera ningún par que concuerda ni cambian el orden | `_los_que_pueden_concordar()`, `nombra_algun_auto()` | `pruebas_de_la_revision.py` (el atajo) |

## Sin prueba automática todavía

- El menú del click derecho, las teclas (F2, F9, F10, F11), el pitido y los textos de Streamlit
  pasados al castellano: son JavaScript en el navegador (`AYUDAS_DEL_NAVEGADOR`); se probaron con
  un navegador de verdad, no hay prueba que los corra sola. Lo mismo el formato de los gráficos
  (`grafico_de_barras()`), lo que se mueve en la pantalla (la barra que trabaja, los números que
  se iluminan: «LO QUE SE MUEVE» en `logica/base.py`) que el aviso al vendedor llegue solo cada
  20 segundos, el cursor en la caja de búsqueda al entrar a cada pantalla y, en el teléfono, que
  la pantalla baje sola hasta lo encontrado después de buscar: lo hace el navegador.
- Lo que necesita la base real (`pruebas_de_la_revision.py --base`, `pruebas_de_compatibilidad.py`)
  no corre en GitHub: se corre a mano antes de publicar.

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
| El VIN mal copiado se avisa en la pantalla («mal», no None ni False) | `decodificar_vin()` con `verificar_vin()` | `pruebas_de_los_cambios.py` (9c) |
| El país del VIN y del código de barras sale de las tablas de la norma (ISO 3779, GS1) | `PAISES_VIN_2`, `PREFIJOS_GS1` | `pruebas_de_los_cambios.py` (9c), `nucleo/pruebas.py` |
| Los códigos de falla dicen lo que dice la norma, y al actualizar se corrigen sin pisar lo editado a mano | `_dtc_sistematicos()`, `SEMILLA_DTC_VERSION` | `pruebas_de_los_cambios.py` (9d) |
| Un año que no puede ser de un auto no se toma, y los ya guardados se releen una vez | `extraer_anios()`, `_corregir_anios_imposibles_de_aplicaciones()` | `nucleo/pruebas.py`, `pruebas_de_los_cambios.py` (9e) |
| «Según el catálogo del fabricante» muestra solo lo que vino de un catálogo, nunca lo deducido de una descripción | `buscar_aplicaciones()` | `pruebas_de_repuestos_por_auto.py` |
| Una motorización o una versión (MPFI, SDI, GLX…) no es un modelo de auto, y las ya deducidas se borran una vez | `MOTORIZACIONES_QUE_NO_SON_MODELO`, `_borrar_modelos_que_no_son_autos()` | `pruebas_de_los_cambios.py` (9e) |
| El conversor de unidades sale de definiciones exactas y cada conversión va y vuelve al mismo número | `CONVERSIONES_DE_TALLER`, `convertir_unidad()` | `pruebas_de_los_cambios.py` (9c bis) |

## Sin prueba automática todavía

- Lo que necesita la base real (`pruebas_de_la_revision.py --base`, `pruebas_de_compatibilidad.py`)
  no corre en GitHub: se corre a mano antes de publicar.

"""Piezas de pantalla que se repiten, PDF, leer el archivo, y el índice de herramientas de Mantenimiento.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================================================
# PIEZAS DE INTERFAZ QUE SE REPITEN
# ============================================================================================
def seccion_plegable(titulo, key, abierto=False):
    """Una sección que se abre y se cierra, PERO que se puede usar adentro de un expander.

    Streamlit no permite un st.expander dentro de otro: tira
    «Expanders may not be nested inside other expanders» y se corta el renderizado ahí mismo,
    dejando media pantalla sin dibujar. Los resultados de la búsqueda ya van dentro de un
    expander por código, así que todo lo de adentro tiene que usar esto en vez de otro expander.
    """
    return st.toggle(titulo, key=key, value=abierto)


def herramientas_del_grupo(indice_grupo):
    """Las herramientas de un grupo de mantenimiento, en el orden en que se dibujan."""
    return [h for h in HERRAMIENTAS_MANTENIMIENTO if h[1] == indice_grupo]


def herramientas_que_coinciden(texto):
    """Las herramientas de mantenimiento que matchean lo que se escribió.

    Busca en el título, en la descripción y en las palabras clave, sin acentos y sin importar
    el orden: «codigos barras», «barras codigo» y «códigos de barras» dan lo mismo.

    Cuenta cuántas palabras coinciden en vez de exigirlas todas, que es la misma regla que ya
    usa buscar_por_texto() para los productos y por el mismo motivo: nadie escribe la palabra
    exacta. Con una o dos palabras se piden las dos —si no aparece cualquier cosa—, con tres o
    más alcanza con dos tercios, y si aun así no sale nada se afloja una más antes de devolver
    la lista vacía. Cero resultados es la peor respuesta posible: el que busca concluye que la
    herramienta no existe, y existe."""
    palabras = [normalizar_texto(p) for p in (texto or "").split() if p.strip()]
    palabras = [p for p in palabras if p]
    if not palabras:
        return []
    puntuadas = []
    for titulo, grupo, que_hace, claves in HERRAMIENTAS_MANTENIMIENTO:
        bolsa = normalizar_texto(f"{titulo} {que_hace} {claves}")
        # Al PRINCIPIO de una palabra, no en cualquier lado. Buscando «no me aparece un
        # codigo», el «no» de adentro de «vinculados» y el «un» de adentro de «una» le daban
        # puntos a media pantalla, y la herramienta que servía quedaba cuarta. Prefijo y no
        # palabra entera para que «codigo» encuentre «códigos» y «foto» encuentre «fotos».
        puntaje = sum(1 for p in palabras if re.search(r"\b" + re.escape(p), bolsa))
        if puntaje:
            puntuadas.append((puntaje, titulo, grupo, que_hace, claves))
    if not puntuadas:
        return []
    cuantas = len(palabras)
    minimo = cuantas if cuantas <= 2 else max(2, (cuantas * 2) // 3)
    salida = [x for x in puntuadas if x[0] >= minimo]
    while not salida and minimo > 1:
        minimo -= 1
        salida = [x for x in puntuadas if x[0] >= minimo]
    salida.sort(key=lambda x: (-x[0], HERRAMIENTAS_MANTENIMIENTO.index(
        (x[1], x[2], x[3], x[4]))))
    return [(t, g, q, c) for _p, t, g, q, c in salida]


def _ir_al_grupo_de_mantenimiento(nombre_grupo):
    """Cambia de grupo desde un botón, y de paso entra a Mantenimiento si no estabas ahí.

    Va como callback y no como código suelto a propósito: Streamlit no deja tocar la clave de
    un widget que ya se dibujó en esta pasada («cannot be modified after the widget is
    instantiated»). Adentro de un on_click corre ANTES de que se vuelva a dibujar, y ahí sí.

    Mueve las DOS solapas porque el buscador también está arriba de Administrar, donde todavía
    no elegiste Mantenimiento: si moviera solo el grupo, apretar «Ir» no haría nada visible."""
    st.session_state["sub_admin"] = "🧹 Mantenimiento"
    st.session_state["sub_mantenimiento"] = nombre_grupo


def buscador_de_herramientas(clave, titulo="¿Qué querés hacer?"):
    """El buscador de las 36 herramientas de mantenimiento. Devuelve True si mostró algo.

    Está en dos lugares y es a propósito: arriba de Administrar, para el que no sabe todavía
    que existe una pantalla llamada «Mantenimiento», y arriba de Mantenimiento, para el que ya
    está adentro y no se acuerda en qué grupo estaba. El caso que resuelve es el mismo, y es el
    que ningún menú resuelve: sabés qué querés hacer, no dónde está."""
    texto = st.text_input(
        titulo, key=clave,
        placeholder="Escribí lo que buscás: barras, fotos, papelera, puentes, precios...",
        help=f"Busca en las {len(HERRAMIENTAS_MANTENIMIENTO)} herramientas de mantenimiento, "
             "estén en el grupo que estén."
    )
    if not texto.strip():
        return False
    encontradas = herramientas_que_coinciden(texto)
    if not encontradas:
        st.caption("No encontré ninguna herramienta con esas palabras. Probá con una sola "
                    "palabra, o mirá los grupos.")
        return True
    st.caption(f"{len(encontradas)} herramienta(s):")
    for titulo_h, grupo_h, que_hace, _claves in encontradas[:8]:
        col_txt, col_btn = st.columns([4, 1])
        col_txt.markdown(
            f"**{texto_para_html(titulo_h)}**  \n<span style='opacity:.75;font-size:.87em'>"
            f"{texto_para_html(que_hace)} · <i>{texto_para_html(GRUPOS_MANTENIMIENTO[grupo_h])}"
            f"</i></span>", unsafe_allow_html=True)
        col_btn.button("Ir 👉", key=f"ir_{clave}_{abs(hash(titulo_h))}",
                        on_click=_ir_al_grupo_de_mantenimiento,
                        args=(GRUPOS_MANTENIMIENTO[grupo_h],),
                        help=f"Está en {GRUPOS_MANTENIMIENTO[grupo_h]}")
    st.markdown("---")
    return True


def texto_para_html(valor):
    """Deja un texto de la base listo para meter adentro de un st.markdown con HTML prendido.

    Hace falta de verdad, no es precaución teórica. Los proveedores usan el signo «<» para
    decir «hasta tal año»: «Master 98<», «Clio 2 2000<». Y cuando lo que sigue al «<» es una
    letra —«...Dakota 2 5 8v 3 9 1997<REF ORIG VW 377919058D»— el navegador no lee «menor
    que»: lee el principio de una etiqueta HTML, y se traga todo hasta encontrar un «>». Como
    no hay ninguno, se come el resto de la descripción. En la base de hoy son 1.435 productos
    y 265.805 caracteres que desaparecían de la pantalla de auditoría: justamente la parte que
    dice a qué autos entra la pieza, que es para lo que uno la mira.

    Y de paso cierra la otra puerta: una descripción importada de un Excel ajeno que traiga
    «<script>» se dibujaba como código de verdad, porque estas pantallas necesitan
    unsafe_allow_html para las etiquetas <small> del renglón.

    No va en los códigos: esos se muestran entre acentos graves, y adentro de un bloque de
    código markdown ya los escribe literales. Escapándolos se vería «Tow&amp;Country-300M» en
    vez de «Tow&Country-300M», que es un código real de la base."""
    return html.escape(str(valor if valor is not None else ""))


def explicar(resumen, detalle, abierto=False, en_expander=False):
    """Una línea corta siempre visible, y el porqué largo a un toque de distancia.

    Las explicaciones largas sirven la primera vez y estorban las otras cien: en el celular
    empujan los botones fuera de la pantalla y hay que scrollear para llegar a lo que uno vino
    a hacer. Pero borrarlas tampoco sirve — sin ellas nadie entiende para qué es cada cosa.
    Así queda el resumen a la vista y el detalle disponible para quien lo necesite.

    Ojo con dónde se la llama. Esta función abre un expander, así que llamarla adentro de otro
    deja un expander dentro de un expander: en el celular quedan dos cajas anidadas y hay que
    tocar dos veces para leer tres renglones. Las versiones viejas de Streamlit ni siquiera lo
    permitían —tiraban excepción y cortaban el renderizado ahí—; las nuevas lo dejan pasar pero
    sigue quedando mal.

    Para eso está en_expander: adentro de un expander el detalle va en un popover, que se abre
    encima y no agrega otro nivel. Con en_expander=True el parámetro 'abierto' no aplica: un
    popover no se puede dejar abierto de entrada."""
    st.caption(resumen)
    caja = None
    if not en_expander:
        try:
            caja = st.expander("¿Por qué? / ¿Cómo funciona?", expanded=abierto)
        except Exception:
            caja = None
    if caja is None:
        try:
            caja = st.popover("¿Por qué? / ¿Cómo funciona?")
        except Exception:
            st.caption(detalle)
            return
    with caja:
        st.markdown(detalle)


def avisar(tipo, texto):
    """Guarda un mensaje para mostrarlo DESPUÉS del refresco de pantalla.

    El problema que resuelve: en toda la app había mensajes escritos justo antes de un
    st.rerun(). El rerun redibuja la pantalla de cero, así que ese "Guardado" se borraba antes
    de que nadie llegara a leerlo. Uno tocaba el botón, la pantalla parpadeaba, y quedaba sin
    saber si había funcionado o no — y de paso volvía a tocarlo por las dudas."""
    st.session_state.setdefault("_avisos", []).append((tipo, texto))


def mostrar_avisos_pendientes():
    """Muestra lo que quedó guardado por avisar() antes del último refresco."""
    for tipo, texto in st.session_state.pop("_avisos", []):
        getattr(st, tipo, st.info)(texto)


def recordar_archivo(archivo, clave):
    """Guarda el archivo subido en la sesión y devuelve siempre esa copia.

    Por qué: en el celular, con conexión lenta, la subida a veces se pierde (un refresco de
    pantalla en el medio, la conexión que se corta) y el widget vuelve a quedar vacío — de ahí
    lo de 'tengo que subirlo 2 o 3 veces'. Con esto, la PRIMERA subida que llegue bien queda
    guardada, y aunque el widget se vacíe después, el archivo sigue disponible."""
    import io as _io

    if archivo is not None:
        try:
            datos = archivo.getvalue()
            if datos:
                st.session_state[f"_archivo_{clave}"] = {
                    "nombre": getattr(archivo, "name", "archivo"),
                    "datos": datos,
                }
        except Exception as _err:
            anotar_error("recordar_archivo", _err)
            pass

    guardado = st.session_state.get(f"_archivo_{clave}")
    if not guardado:
        return None

    copia = _io.BytesIO(guardado["datos"])
    copia.name = guardado["nombre"]
    copia.size = len(guardado["datos"])
    return copia


def _clave_widget_archivo(clave):
    """La 'key' que usa el widget de subida hoy. Le va pegado un número que se incrementa cada
    vez que se pide vaciarlo: cambiarle la key es la única forma de que Streamlit lo trate como
    un widget nuevo y arranque en blanco."""
    return f"_up_{clave}_{st.session_state.get(f'_nonce_{clave}', 0)}"


def olvidar_archivo(clave):
    """Borra la copia guardada Y vacía el widget de subida de verdad.

    Antes solo se borraba la copia de la sesión. El widget seguía teniendo el archivo adentro,
    así que en el refresco siguiente lo devolvía igual, se volvía a guardar solo, y el botón
    'Usar otra foto / otro archivo' quedaba sin efecto: no había forma de cambiar el archivo
    sin recargar la página entera. Ese era el problema de la carga que seguía apareciendo."""
    st.session_state.pop(f"_archivo_{clave}", None)
    viejo = _clave_widget_archivo(clave)
    st.session_state.pop(viejo, None)  # soltar los bytes del widget viejo, si no queda ocupando RAM
    st.session_state[f"_nonce_{clave}"] = st.session_state.get(f"_nonce_{clave}", 0) + 1


def subir_archivo(etiqueta, tipos, clave, **kwargs):
    """Subida de archivo estándar de la app: widget + memoria + reset. Usar SIEMPRE esta en vez
    de st.file_uploader directo, así todos los puntos de carga se comportan igual."""
    subido = st.file_uploader(etiqueta, type=tipos, key=_clave_widget_archivo(clave), **kwargs)
    return recordar_archivo(subido, clave)


def boton_otro_archivo(clave, etiqueta="🗑️ Usar otro archivo", key=None):
    """Botón para descartar lo subido y empezar de nuevo. Devuelve True si se tocó."""
    if st.button(etiqueta, key=key or f"btn_otro_{clave}"):
        olvidar_archivo(clave)
        st.rerun()
    return False


def archivo_listo(archivo, etiqueta="archivo"):
    """Muestra si el archivo terminó de subir. Antes los botones directamente no aparecían hasta
    que el archivo estaba, así que con una conexión lenta parecía que no había pasado nada y la
    gente volvía a tocar 2 o 3 veces pensando que había fallado. Ahora el botón está siempre,
    apagado hasta que el archivo llega, y acá abajo se ve el estado."""
    if archivo is None:
        st.caption(
            f"⏳ Todavía no llegó ningún {etiqueta}. Si ya lo elegiste y la conexión está lenta, "
            "esperá unos segundos sin volver a tocar: cuando termine de subir se avisa acá."
        )
        return False
    tamano = getattr(archivo, "size", None)
    detalle = f" ({tamano/1024:,.0f} KB)" if tamano else ""
    st.caption(f"✅ Recibido: {getattr(archivo, 'name', etiqueta)}{detalle}")
    return True


# ============================================================================================
# PDF: cotización y ficha del vehículo
# ============================================================================================
def pdf_con_cache(nombre, generador, *args):
    """El botón de descarga de Streamlit necesita el archivo listo de antemano, así que el PDF
    se arma en CADA refresco de pantalla aunque nadie lo descargue. Esto guarda el último
    generado y lo reusa mientras los datos no cambien, en vez de rehacerlo cada vez.
    Se usa un caché propio (y no st.cache_data) para no depender de cómo Streamlit compara
    listas y diccionarios: acá la clave se calcula de forma explícita y predecible."""
    try:
        firma = json.dumps(args, default=str, sort_keys=True)
    except Exception as _err:
        anotar_error("pdf_con_cache", _err)
        return generador(*args)  # si algo no se puede resumir, se genera sin cachear
    clave = nombre + ":" + hashlib.md5(firma.encode("utf-8")).hexdigest()
    guardado = st.session_state.get("_cache_pdf")
    if guardado and guardado[0] == clave:
        return guardado[1]
    resultado = generador(*args)
    st.session_state["_cache_pdf"] = (clave, resultado)
    return resultado


def generar_pdf_cotizacion(lista_productos, incluir_precio=True, incluir_stock=False, alias_qr=None, qr_real_bytes=None):
    """Genera un PDF simple de cotización a partir de la lista armada para WhatsApp.
    Si se pasa alias_qr (un dict con nombre/alias/cbu/titular), agrega un QR con esos datos
    para transferencia — el cliente lo escanea y ve el alias/CBU listo para pegar, sin tipear."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Equivalencias El Chavo - Cotizacion", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Fecha: {datetime.now():%d/%m/%Y %H:%M}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    def limpiar(texto):
        # fpdf2 con fuentes básicas no soporta todo unicode; reemplazamos lo problemático
        return str(texto).encode("latin-1", "replace").decode("latin-1")

    for item in lista_productos:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, limpiar(f"Codigo buscado: {item['codigo_buscado']}"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        for fila in item["resultados"]:
            linea = f"  - {fila['Marca']}: {fila['Codigo']}"
            if fila.get("Descripcion"):
                linea += f" - {fila['Descripcion']}"
            extras = []
            if incluir_precio and fila.get("Precio"):
                extras.append(f"${fila['Precio']:,.0f}")
            if incluir_stock and fila.get("Stock") is not None:
                extras.append(f"Stock: {fila['Stock']}")
            if extras:
                linea += " (" + " / ".join(extras) + ")"
            pdf.multi_cell(0, 6, limpiar(linea), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    if alias_qr:
        qr_bytes = qr_real_bytes if qr_real_bytes else generar_qr_bytes(
            f"Alias: {alias_qr['Alias']}\nCBU: {alias_qr['CBU']}\nTitular: {alias_qr['Titular']}"
        )
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, limpiar(f"Transferir a: {alias_qr['Nombre']}"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, limpiar(f"Alias: {alias_qr['Alias']}  /  CBU: {alias_qr['CBU']}  /  Titular: {alias_qr['Titular']}"),
                       new_x="LMARGIN", new_y="NEXT")
        pdf.image(io.BytesIO(qr_bytes), w=35)
        pdf.set_font("Helvetica", "I", 8)
        if qr_real_bytes:
            pdf.multi_cell(0, 4, "Escaneá el QR con tu app de Mercado Pago/MODO/banco para transferir.",
                           new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.multi_cell(0, 4, "Escaneá el QR para ver el alias/CBU y transferir desde tu banco o billetera virtual.",
                           new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


def generar_pdf_ficha_vehiculo(vehiculo, km_calc, alertas, proyeccion, historial):
    """Genera un PDF con el resumen de la ficha digital del vehículo, para entregarle al cliente."""
    from fpdf import FPDF

    def limpiar(texto):
        return str(texto).encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Equivalencias El Chavo - Ficha del vehiculo", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Fecha: {datetime.now():%d/%m/%Y %H:%M}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, limpiar(f"Patente: {vehiculo['patente']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    nombre_auto = f"{vehiculo.get('marca_auto') or ''} {vehiculo.get('modelo_auto') or ''}".strip()
    if nombre_auto:
        pdf.cell(0, 6, limpiar(nombre_auto), new_x="LMARGIN", new_y="NEXT")
    if vehiculo.get("cliente_nombre"):
        pdf.cell(0, 6, limpiar(f"Cliente: {vehiculo['cliente_nombre']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "Kilometraje", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    km_reg = vehiculo.get("km_registro")
    km_act = vehiculo.get("km_actual")
    pdf.cell(0, 6, limpiar(f"Km de registro: {km_reg if km_reg is not None else '-'}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, limpiar(f"Km actual: {km_act if km_act is not None else '-'}"), new_x="LMARGIN", new_y="NEXT")
    if km_calc.get("km_recorridos") is not None:
        pdf.cell(0, 6, limpiar(f"Km recorridos: {km_calc['km_recorridos']:,}"), new_x="LMARGIN", new_y="NEXT")
    if km_calc.get("promedio_mensual") is not None:
        pdf.cell(0, 6, limpiar(f"Promedio aproximado: {km_calc['promedio_mensual']:,} km/mes"),
                  new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    if alertas:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 7, "Alertas de mantenimiento", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        for a in alertas:
            linea = f"- {a['Pieza']} ({a.get('Marca') or 's/marca'}): {a['% consumido']}% de su vida util consumida"
            pdf.multi_cell(0, 6, limpiar(linea), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    if proyeccion:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 7, "Proyeccion de mantenimiento", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        for p in proyeccion:
            linea = (f"- {p['Pieza']}: cambiada {p['Veces cambiada']} vez/veces, "
                      f"deberia {p['Veces que debería (según km)']} - atraso: {p['Atraso estimado']}")
            pdf.multi_cell(0, 6, limpiar(linea), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    if historial:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 7, "Historial de piezas cambiadas", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        for h in historial:
            linea = f"- {h['Pieza']} ({h.get('Marca') or ''}) - {h.get('Fecha') or ''} - {h.get('Km instalación') or '-'} km"
            pdf.multi_cell(0, 6, limpiar(linea), new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


# ============================================================================================
# LEER EL ARCHIVO: encabezado, hojas y codificación
# ============================================================================================
def _puntaje_como_encabezado(fila, siguientes):
    """Qué tan probable es que ESTA fila sea la de títulos de columna.

    No alcanza con mirar la fila sola: un título de tapa ("LISTA DE PRECIOS", "Vigente desde")
    también tiene texto. Lo que distingue al encabezado de verdad es que las filas de ABAJO
    tengan la misma cantidad de columnas llenas que él, y que abajo aparezcan números (precios,
    stock) donde arriba hay palabras."""
    celdas = [c for c in fila if c is not None and str(c).strip() != ""]
    if len(celdas) < 2:
        return -1

    textos = [str(c).strip() for c in celdas]
    puntaje = 0.0

    # Un encabezado son etiquetas cortas, no frases
    if all(len(t) <= 28 for t in textos):
        puntaje += 2
    largo_promedio = sum(len(t) for t in textos) / len(textos)
    if largo_promedio <= 18:
        puntaje += 1

    # Los títulos no se repiten entre sí
    if len(set(t.upper() for t in textos)) == len(textos):
        puntaje += 1.5

    # Casi ningún título es un número suelto
    numericos = sum(1 for t in textos if t.replace(".", "").replace(",", "").isdigit())
    puntaje -= numericos * 1.5

    # Palabras que titulan columnas en cualquier lista de repuestos
    texto_junto = " ".join(textos).upper()
    aciertos = sum(1 for pistas in PISTAS_COLUMNAS.values()
                   for pista in pistas if pista in texto_junto)
    puntaje += min(aciertos, 4) * 1.5

    # Y lo más decisivo: que abajo siga una tabla con la misma forma
    llenas = len(celdas)
    parecidas = 0
    con_numeros = 0
    for sig in siguientes:
        celdas_sig = [c for c in sig if c is not None and str(c).strip() != ""]
        if not celdas_sig:
            continue
        if abs(len(celdas_sig) - llenas) <= 1:
            parecidas += 1
        if any(isinstance(c, (int, float)) or
               str(c).strip().replace(".", "").replace(",", "").isdigit() for c in celdas_sig):
            con_numeros += 1
    puntaje += parecidas * 1.2
    puntaje += min(con_numeros, 3) * 0.8

    # Una fila de tapa suele tener texto largo en la primera celda y nada más
    if len(celdas) <= 2 and largo_promedio > 20:
        puntaje -= 3
    return puntaje


def detectar_fila_encabezado(filas, maximo=25):
    """En qué fila están los títulos de las columnas.

    Hace falta porque las listas casi nunca empiezan en la fila 1: traen el nombre del
    proveedor, el teléfono, la fecha de vigencia, filas vacías. La detección anterior agarraba
    la PRIMERA fila con dos textos, así que en una lista con título y fecha arriba se quedaba
    con 'Vigente desde... / IVA incluido' como si fueran los nombres de las columnas. A partir
    de ahí todo salía mal: el mapeo apuntaba a columnas equivocadas y las filas de arriba
    entraban como si fueran productos.
    """
    if not filas:
        return 0

    # Primero: ¿dónde arrancan los datos? Muchas listas empiezan con filas totalmente vacías.
    primera_con_datos = 0
    for idx, fila in enumerate(filas[:maximo]):
        if any(x is not None and str(x).strip() != "" for x in fila):
            primera_con_datos = idx
            break

    mejor_fila, mejor_puntaje = primera_con_datos, -999
    for idx in range(primera_con_datos, min(len(filas), maximo)):
        p = _puntaje_como_encabezado(filas[idx], filas[idx + 1:idx + 6])
        if p > mejor_puntaje:
            mejor_fila, mejor_puntaje = idx, p

    # Muchísimas listas de proveedor NO TIENEN encabezado: arrancan directo con el primer
    # producto. Sin este control, el detector igual elegía "la fila que más se parece a un
    # encabezado", que terminaba siendo una fila de datos — y ahí se pierde ese producto y se
    # toman sus valores como si fueran los nombres de las columnas.
    #
    # La señal de que NO hay encabezado: la primera fila con datos se parece a las que siguen.
    # Un encabezado real es distinto de sus datos (dice palabras donde abajo hay números).
    if _parece_fila_de_datos(filas[primera_con_datos], filas[primera_con_datos + 1:primera_con_datos + 6]):
        return max(primera_con_datos - 1, 0)

    return mejor_fila if mejor_puntaje > 0 else primera_con_datos


def _parece_fila_de_datos(fila, siguientes):
    """¿Esta fila es un producto más, y no los títulos de las columnas?

    Se compara con las que vienen abajo: si tiene el mismo tipo de contenido en las mismas
    posiciones —número donde abajo hay números, texto donde abajo hay texto— entonces es una
    fila de datos igual a las demás, y esta lista no tiene encabezado."""
    if not siguientes:
        return False

    def perfil(f):
        p = []
        for celda in f:
            if celda is None or str(celda).strip() == "":
                p.append("vacio")
            elif isinstance(celda, (int, float)) or str(celda).strip().replace(".", "").replace(",", "").isdigit():
                p.append("num")
            else:
                p.append("texto")
        return p

    mio = perfil(fila)
    llenas = sum(1 for x in mio if x != "vacio")
    # Tiene que ser una fila de TABLA, con al menos 3 columnas con contenido. Sin este piso, un
    # título de tapa suelto ("ACTUALIZACION DE PRECIOS") se parecía a las otras filas de tapa
    # que venían abajo y la lista se tomaba como si no tuviera encabezado.
    if llenas < 3:
        return False

    iguales = 0
    comparadas = 0
    for sig in siguientes:
        perfil_sig = perfil(sig)
        if sum(1 for x in perfil_sig if x != "vacio") < 3:
            continue
        comparadas += 1
        largo = min(len(mio), len(perfil_sig))
        if largo and sum(1 for i in range(largo) if mio[i] == perfil_sig[i]) / largo >= 0.8:
            iguales += 1
    return comparadas >= 2 and iguales / comparadas >= 0.6


def hojas_del_excel(archivo):
    """Las hojas del archivo con cuántas filas tiene cada una.

    Importa porque antes se leía siempre wb.active —la hoja que quedó abierta cuando el
    proveedor guardó el archivo— y podía ser la de instrucciones o una vacía. Si la lista
    estaba en otra hoja, no se importaba nada y no había forma de darse cuenta."""
    nombre = archivo if isinstance(archivo, str) else getattr(archivo, "name", "")
    if not nombre.lower().endswith((".xlsx", ".xlsm", ".xltx")):
        return []
    try:
        if not isinstance(archivo, str):
            archivo.seek(0)
        # SIN read_only a propósito. En modo read_only, openpyxl devuelve max_row = None para
        # muchos archivos (pasa con las listas reales de proveedor), así que todas las hojas
        # figuraban con 0 filas: el selector no servía para nada y la elección automática de
        # "la hoja con más filas" terminaba tomando la primera por descarte.
        wb = load_workbook(archivo, data_only=True)
        hojas = [(ws.title, ws.max_row or 0) for ws in wb.worksheets]
        wb.close()
        return hojas
    except Exception as _err:
        anotar_error("hojas_del_excel", _err)
        return []


def _decodificar_texto(crudo):
    """Pasa los bytes de un archivo de texto a string, probando las codificaciones que se usan.

    Antes se decodificaba solo como UTF-8 y, si el archivo venía en otra, la lectura fallaba
    entera con 'No se pudo leer el archivo'. El problema es que Excel en español guarda los CSV
    en Windows-1252, no en UTF-8: cualquier lista con una 'ó' o una 'ñ' —o sea, casi todas—
    era imposible de importar y no había forma de saber por qué.

    El orden importa: primero las que pueden fallar (UTF-8 detecta bytes inválidos), y latin-1
    al final porque acepta cualquier byte y nunca falla, así que si va antes gana siempre y
    deja los acentos mal."""
    for codificacion in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return crudo.decode(codificacion)
        except (UnicodeDecodeError, AttributeError) as _err:
            anotar_error("_decodificar_texto", _err)
            continue
    return crudo.decode("latin-1", errors="replace")


def _detectar_separador(texto):
    """Con qué carácter están separadas las columnas.

    Se mira solo el ENCABEZADO y las primeras filas, no el archivo entero: en una lista larga
    las descripciones traen comas ('FILTRO, ACEITE, FORD') y al contar sobre todo el texto la
    coma le ganaba al separador verdadero. Y se incluye la tabulación, que antes no se
    contemplaba: un archivo separado por tabs quedaba todo en una sola columna."""
    lineas_muestra = [l for l in texto.splitlines()[:15] if l.strip()]
    if not lineas_muestra:
        return ","
    mejor, mejor_puntaje = ",", -1
    for cand in ("\t", ";", ",", "|"):
        cuentas = [l.count(cand) for l in lineas_muestra]
        if not cuentas or max(cuentas) == 0:
            continue
        # Un separador de verdad aparece la MISMA cantidad de veces en todas las filas
        parejas = sum(1 for x in cuentas if x == cuentas[0])
        puntaje = cuentas[0] * 2 + parejas
        if puntaje > mejor_puntaje:
            mejor, mejor_puntaje = cand, puntaje
    return mejor


def leer_excel(archivo, nrows=None, hoja=None):
    """Lee un archivo Excel, CSV o PDF (subido o por ruta) y devuelve una lista de listas (filas)."""
    nombre = archivo if isinstance(archivo, str) else getattr(archivo, "name", "")
    nombre_lower = nombre.lower()
    # Volver al principio del archivo: esta función se llama primero para la vista previa y
    # después para la carga completa. Si el puntero quedó al final de la primera lectura, la
    # segunda leía vacío — de ahí que algunos archivos "se subieran mal" o salieran incompletos.
    if not isinstance(archivo, str):
        try:
            archivo.seek(0)
        except Exception as _err:
            anotar_error("leer_excel", _err)
            pass

    if nombre_lower.endswith((".csv", ".txt", ".tsv")):
        import csv as csv_module
        if isinstance(archivo, str):
            crudo = open(archivo, "rb").read()
        else:
            archivo.seek(0)
            crudo = archivo.read()
            if isinstance(crudo, str):
                crudo = crudo.encode("utf-8")

        texto = _decodificar_texto(crudo)
        delimitador = _detectar_separador(texto)
        filas = []
        for i, row in enumerate(csv_module.reader(texto.splitlines(), delimiter=delimitador)):
            filas.append(row)
            if nrows and i + 1 >= nrows:
                break
        return filas

    if nombre_lower.endswith(".pdf"):
        import pdfplumber
        filas = []
        with pdfplumber.open(archivo) as pdf:
            for pagina in pdf.pages:
                # extract_tables() en plural: antes se usaba extract_table() (singular), que
                # devuelve SOLO la primera tabla de cada página. En las listas de precios que
                # traen la tabla partida en varios bloques por hoja, se perdía casi todo.
                tablas = pagina.extract_tables() or []
                encontro_algo = False
                for tabla in tablas:
                    for row in tabla:
                        if row and any(celda not in (None, "") for celda in row):
                            filas.append([celda if celda is not None else "" for celda in row])
                            encontro_algo = True
                            if nrows and len(filas) >= nrows:
                                return filas
                if not encontro_algo:
                    # Muchos PDF de proveedor no tienen líneas de tabla: son columnas alineadas
                    # con espacios. Acá NO sirve partir el texto por «dos o más espacios»:
                    # extract_text() colapsa los espacios múltiples en uno solo, así que toda la
                    # fila vuelve como una sola celda y no entra ni un producto. Comprobado
                    # generando un PDF de ese formato: devolvía 0 filas.
                    #
                    # Lo que sí funciona es mirar dónde está cada palabra en la hoja: si entre
                    # el final de una y el comienzo de la siguiente hay un hueco grande, ahí
                    # cambia la columna. Es el mismo criterio que usa el ojo al leerlo.
                    try:
                        palabras = pagina.extract_words() or []
                    except Exception as _err:
                        anotar_error("leer_excel", _err)
                        palabras = []
                    renglones = {}
                    for w in palabras:
                        # Se agrupan por altura, redondeando: los caracteres de una misma línea
                        # nunca están exactamente a la misma altura.
                        clave = round(float(w["top"]) / 3)
                        renglones.setdefault(clave, []).append(w)

                    # Dónde EMPIEZA cada columna, mirando la página entera. Un umbral fijo de
                    # separación no alcanza: cuando una descripción larga llena su columna, el
                    # hueco con el precio es el de un espacio común y quedan pegados. Pero en
                    # estas listas las columnas están alineadas fila a fila, así que las
                    # posiciones donde arrancan las palabras se repiten — y esas repeticiones
                    # son los bordes de las columnas.
                    inicios = {}
                    for w in palabras:
                        x = round(float(w["x0"]) / 4) * 4
                        inicios[x] = inicios.get(x, 0) + 1
                    # Un borde de columna real aparece en CASI TODAS las filas, no en un tercio.
                    # Con el umbral bajo entraban como columna las posiciones donde arrancan
                    # palabras sueltas de la descripción, y la descripción terminaba partida en
                    # cinco pedazos. Se pide el 70% de los renglones.
                    minimo_filas = max(3, int(len(renglones) * 0.7))
                    bordes = sorted(x for x, veces in inicios.items() if veces >= minimo_filas)

                    for clave in sorted(renglones):
                        grupo = sorted(renglones[clave], key=lambda w: float(w["x0"]))
                        if bordes:
                            columnas_fila = {}
                            for w in grupo:
                                # A qué columna pertenece: el borde más cercano a su izquierda
                                x = float(w["x0"])
                                borde = max([b for b in bordes if b <= x + 3], default=bordes[0])
                                columnas_fila.setdefault(borde, []).append(w["text"])
                            celdas = [" ".join(columnas_fila[b]) for b in sorted(columnas_fila)]
                        else:
                            celdas, actual, fin_anterior = [], [], None
                            for w in grupo:
                                if fin_anterior is not None and float(w["x0"]) - fin_anterior > 8:
                                    celdas.append(" ".join(actual))
                                    actual = []
                                actual.append(w["text"])
                                fin_anterior = float(w["x1"])
                            if actual:
                                celdas.append(" ".join(actual))
                        celdas = [x.strip() for x in celdas if x.strip()]
                        if len(celdas) >= 2:
                            filas.append(celdas)
                            if nrows and len(filas) >= nrows:
                                return filas
        return filas

    wb = load_workbook(archivo, data_only=True)
    if hoja and hoja in wb.sheetnames:
        ws = wb[hoja]
    else:
        # Sin hoja elegida, se toma la que MÁS FILAS tiene, no la que quedó activa: la activa
        # es simplemente la que el proveedor tenía abierta al guardar, y muchas veces es la de
        # instrucciones o una en blanco.
        ws = max(wb.worksheets, key=lambda w: w.max_row or 0)
    filas = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        filas.append(list(row))
        if nrows and i + 1 >= nrows:
            break
    return filas




# Mantenimiento tiene 36 herramientas. Cuatro grupos no alcanzaban: «Calidad y aprendizaje»
# se había quedado con 17 de las 36 —1.060 líneas de una sola tirada— y era donde la pregunta
# «¿dónde estaba eso?» terminaba en bajar y bajar. Ahora se agrupan por LO QUE UNO VIENE A
# HACER, que es lo que una persona sabe antes de entrar: busco vínculos nuevos, limpio los que
# están mal, miro cómo está la base.
GRUPOS_MANTENIMIENTO = ["🔎 Encontrar equivalencias", "🧹 Limpiar y corregir",
                        "🧠 Calidad y aprendizaje", "🏷️ Códigos de barras", "📷 Fotos",
                        "🩺 Estado y papelera"]

# Cada herramienta con su grupo, una línea de qué hace, y las palabras con las que alguien la
# buscaría. No es decorado: es lo que hace que la pantalla se explique sola.
#   · El índice de arriba de cada grupo dice QUÉ HAY antes de bajar a buscarlo.
#   · El buscador encuentra una herramienta aunque esté en otro grupo, que es el caso que
#     duele: sabés qué querés hacer y no te acordás dónde estaba.
# El título tiene que ser EXACTAMENTE el que se dibuja abajo, si no el índice miente. El
# auditor lo controla.
HERRAMIENTAS_MANTENIMIENTO = [
    # (título, grupo, qué hace en una línea, palabras con que se busca)
    ("🏭 Catálogo de aplicaciones (qué repuesto le va a cada auto)", 0,
     "Subís el catálogo de NGK, Bosch o Mann y la app sabe qué pieza entra en qué auto. "
     "Deducirlas de tus propias descripciones ✅ ya corre solo después de cada importación; "
     "el botón de adentro es para volver a pasarlo. Subir un catálogo sigue siendo a mano.",
     "aplicaciones catalogo ngk bosch mann skf auto modelo deducir descripciones automatico solo"),
    ("📐 Equivalencias por medidas", 0,
     "Propone equivalentes de dos marcas que tienen las mismas medidas cargadas.",
     "medidas milimetros diametro largo rosca mecanicas"),
    ("🔄 Reunir lo que separó un cambio de número", 0,
     "Junta lo que quedó partido cuando el proveedor le cambió el código a una pieza.",
     "cambio numero renumero sucesor reemplazo separado"),
    ("🔐 Traer autos del portal del proveedor", 0,
     "Entra al catálogo web del proveedor y trae a qué autos va cada código.",
     "portal proveedor web autos aplicaciones clave contraseña"),
    ("🔤 Vincular dos proveedores por la descripción", 0,
     "Compara dos listas por el texto y propone los que son la misma pieza.",
     "descripcion texto dos proveedores comparar"),
    ("🔗 Equivalencias deducidas cruzando catálogos", 0,
     "Si A equivale a B y B a C, propone A con C.",
     "deducidas cruzar cadena transitiva"),
    # El «✅ ya corre solo» no es decoración: estas dos las dispara
    # descubrimiento_post_importacion() después de cada importación, y el índice no lo decía.
    # Sin eso, el que entra a este grupo ve nueve botones y no tiene forma de saber cuáles ya
    # se hicieron ni en qué orden conviene apretar los demás — y termina corriendo de nuevo,
    # a mano y esperando, algo que la app ya hizo sola.
    ("📝 Códigos de fábrica que el proveedor escribió en la descripción", 0,
     "Lee los «REF ORIG» que ya están escritos en las descripciones cargadas. "
     "✅ Ya corre solo después de cada importación: esto es para volver a pasarlo.",
     "ref orig oem descripcion escrito declarado automatico solo"),
    ("🧠 Buscar equivalencias en TODO el catálogo de una", 0,
     "Compara todas las marcas entre sí en una sola pasada, en vez de de a dos. "
     "✅ Ya corre solo después de cada importación: esto es para volver a pasarlo.",
     "todo catalogo barrido todas las marcas automatico solo"),
    ("🌐 Leer equivalencias del catálogo digital del proveedor", 0,
     "Abre la ficha web de cada código y trae los códigos cruzados que lista.",
     "catalogo digital web ficha equivalencias proveedor"),

    ("🌉 Códigos puente — los que rompen la búsqueda", 1,
     "Códigos vinculados a demasiadas cosas: cortar uno limpia miles de resultados falsos.",
     "puente puentes fusiona familias muchos vinculos resultados falsos basura mezclado"),
    ("🧯 Puentes que hoy ya no se generarían", 1,
     "Puentes falsos que quedaron cargados antes de que las reglas mejoraran.",
     "puentes viejos falsos limpiar reglas nuevas"),
    ("🔗 Vínculos que unen dos familias de repuestos", 1,
     "Pares donde un lado es un filtro y el otro un sensor: alguno está mal.",
     "familias rubro distinto mal vinculado"),
    ("🔍 Revisar los vínculos que YA están cargados", 1,
     "Audita lo que la búsqueda está devolviendo hoy, no lo que falta entrar. "
     "✅ Ya corre solo después de cada importación: el resultado está escrito en la pantalla.",
     "auditar revisar cargados confianza automatico solo"),
    ("💲 Precios que no cierran entre equivalentes", 1,
     "Dos piezas «iguales» con precios muy distintos: casi siempre una está mal.",
     "precio precios distinto diferencia equivalentes caro barato raro"),
    ("🗑️ Códigos que son solo un número suelto", 1,
     "Códigos que en realidad eran una cantidad o una medida.",
     "numero suelto basura medida cantidad"),
    ("🔎 Códigos que el buscador no encuentra", 1,
     "Productos cargados que no aparecen al escribir su código.",
     "no aparece no encuentra no figura no sale buscador indice invisible"),
    ("🔢 Códigos que quedaron con '.0'", 1,
     "El listado de los que Excel guardó como número, con el «.0» pegado atrás.",
     "excel punto cero decimal numero"),
    ("🔢 Códigos con el '.0' de Excel", 1,
     "El botón que se los saca a todos de una.",
     "excel punto cero decimal numero arreglar"),
    ("📝 Descripciones con las columnas pegadas", 1,
     "Filas donde la exportación pegó dos columnas en una.",
     "descripcion pegada columnas separar"),
    ("🕵️ Puentes falsos: códigos que unen repuestos que no tienen nada que ver", 1,
     "Busca los códigos que fusionan familias enteras y te deja borrarlos de a uno.",
     "puentes falsos fusionan familias borrar"),
    ("🔁 Equivalencias anotadas dos veces", 1,
     "La misma relación guardada de ida y de vuelta.",
     "duplicadas espejadas dos veces repetidas"),

    ("🎯 Puntuar los vínculos para el buscador", 2,
     "Le pone nota a cada vínculo para que el buscador muestre primero los buenos.",
     "puntuar confianza nota ordenar"),
    ("🧾 Equivalencias que confirmó el mostrador", 2,
     "Las que se usaron de verdad en una venta: la mejor evidencia que hay.",
     "confirmadas mostrador venta usadas"),
    ("📚 Lo que la app aprendió de tus decisiones", 2,
     "Los patrones que salieron de lo que fuiste aprobando y rechazando.",
     "aprendio patrones decisiones aprendizaje"),

    ("🏷️ Códigos de barras cargados como código de fábrica", 3,
     "El código de barras entró en la columna del OEM: se mueve solo al lugar que va.",
     "barras ean gtin columna equivocada oem"),
    ("🏷️ Cargar códigos de barras en masa", 3,
     "Subís una planilla de códigos de barras y se cargan de una.",
     "barras masa planilla escaner cargar"),
    ("🔢 Códigos de barras que no cierran con su dígito verificador", 3,
     "Los que el escáner no va a encontrar porque están mal copiados.",
     "barras digito verificador escaner mal copiado"),

    ("📷 Traer fotos de productos en tanda", 4,
     "Baja las fotos del catálogo del proveedor de a muchas.",
     "fotos tanda bajar imagenes masivo foto imagen"),
    ("Traerlas desde la ficha del proveedor", 4,
     "La dirección web de cada marca, que es de donde salen las fotos.",
     "ficha url direccion web proveedor plantilla"),

    ("⏳ Qué tan atrasada está cada lista", 5,
     "Cuántos días tiene cada lista de precios y cuánto viene subiendo.",
     "precios atrasados dias lista aumento inflacion"),
    ("↩️ Deshacer una importación", 5,
     "Vuelve atrás una carga de Excel entera.",
     "deshacer importacion revertir excel lista cargue mal me equivoque"),
    ("🔀 ¿Cuánto cruza tu catálogo entre proveedores?", 5,
     "Marca por marca: cuántos productos llegan a otra marca, y por qué no.",
     "cruza cruces proveedores aislada"),
    ("🔗 Listas que no cruzan con ninguna otra", 5,
     "El motivo escrito de por qué una lista no genera equivalencias.",
     "no cruza aislada motivo lista sola"),
    ("🔍 Salud de los datos", 5,
     "Revisa la base buscando cosas rotas o incoherentes.",
     "salud integridad roto corrupto chequeo"),
    ("Limpieza de la base", 5,
     "Borrar huérfanos, vínculos muertos y productos de prueba.",
     "limpieza huerfanos muertos borrar depurar"),
    ("🗑️ Papelera", 5,
     "Lo que borraste, para restaurarlo.",
     "papelera borrado restaurar recuperar deshacer borre borro elimine sin querer equivoque error"),
]

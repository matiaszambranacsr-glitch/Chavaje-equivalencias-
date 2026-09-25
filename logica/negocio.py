"""Combos, IA, buscar por pieza y auto, discontinuados, reposición, configuración, papelera, historial y cobros.

Es una parte de la lógica de la app: se ejecuta, junto con las otras y en el orden de
orden.PARTES_DE_LA_LOGICA, en un solo espacio de nombres (ver logica/__init__.py). Por eso acá
se usan sin importarlos los nombres que definen las partes anteriores."""

# ============================================================
# COMBOS DE REPUESTOS RELACIONADOS (ej: correa de distribución -> kit + tensor + bomba de agua)
# ============================================================
def normalizar_texto(texto):
    """Mayúsculas y sin acentos, para poder comparar 'distribución' con 'distribucion'."""
    texto = texto or ""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return texto.upper().strip()


def buscar_combos_para_descripcion(descripcion):
    """Devuelve {disparador: [items]} para los disparadores que aparecen dentro de la descripción dada."""
    desc_norm = normalizar_texto(descripcion)
    c.execute("SELECT disparador, item FROM combos_sugeridos ORDER BY disparador, item")
    resultado = {}
    for row in c.fetchall():
        if normalizar_texto(row["disparador"]) in desc_norm:
            resultado.setdefault(row["disparador"], []).append(row["item"])
    return resultado


def listar_combos():
    c.execute("SELECT DISTINCT disparador FROM combos_sugeridos ORDER BY disparador")
    disparadores = [r["disparador"] for r in c.fetchall()]
    resultado = []
    for d in disparadores:
        c.execute("SELECT item FROM combos_sugeridos WHERE disparador = ? ORDER BY item", (d,))
        resultado.append({"disparador": d, "items": [r["item"] for r in c.fetchall()]})
    return resultado


def guardar_combo(disparador, items_lista):
    disparador = disparador.strip().lower()
    with db_lock:
        c.execute("DELETE FROM combos_sugeridos WHERE disparador = ?", (disparador,))
        c.executemany(
            "INSERT INTO combos_sugeridos (disparador, item) VALUES (?, ?)",
            [(disparador, item.strip()) for item in items_lista if item.strip()]
        )
        conn.commit()


def eliminar_combo(disparador):
    disparador = disparador.strip().lower()
    c.execute("SELECT item FROM combos_sugeridos WHERE disparador = ?", (disparador,))
    items = [r["item"] for r in c.fetchall()]
    if items:
        mover_a_papelera("combo", {"disparador": disparador, "items": items})
    with db_lock:
        c.execute("DELETE FROM combos_sugeridos WHERE disparador = ?", (disparador,))
        conn.commit()


# ============================================================================================
# INTELIGENCIA ARTIFICIAL: fotos, audio y remitos
# ============================================================================================
def identificar_pieza_por_foto(imagen_bytes):
    """Le manda una foto a Gemini y le pide que identifique la pieza, extrayendo el código
    de forma estructurada (no solo texto libre) para poder buscarlo directo en el catálogo."""
    from google import genai
    from google.genai import types

    api_key = secretos_app().get("gemini_api_key")
    if not api_key:
        return None, "No configuraste 'gemini_api_key' en Streamlit Cloud (Settings → Secrets)."

    try:
        client = genai.Client(api_key=api_key)
        prompt = (
            "Esta es una foto de un repuesto de auto tomada en un taller o local de repuestos. Tu "
            "tarea principal es ENCONTRAR EL CÓDIGO — mirá con mucha atención toda la superficie de "
            "la pieza: suelen estar grabados en bajorrelieve sobre el metal (a veces se ven mejor con "
            "el contraste de la luz, poco legibles a simple vista), impresos en una etiqueta pegada, "
            "moldeados en el plástico/goma, o troquelados en el borde. Es una combinación de letras y "
            "números, a veces con guiones, barras o puntos. Revisá TODOS los lados de la pieza que se "
            "vean en la foto antes de rendirte. Devolvé ÚNICAMENTE un JSON válido (sin texto extra, "
            'sin markdown), con esta forma exacta: {"codigo": "...", "marca_visible": "...", '
            '"tipo_pieza": "...", "confianza": "alta/media/baja"}. Si después de mirar con atención en '
            'serio no hay ningún código legible, dejá "codigo" como null — no inventes ni completes un '
            "código que no se vea con claridad."
        )
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=[
                prompt,
                types.Part.from_bytes(data=imagen_bytes, mime_type="image/jpeg"),
            ],
        )
        texto = response.text.strip()
        if texto.startswith("```"):
            texto = texto.split("```")[1]
            texto = texto[4:] if texto.lower().startswith("json") else texto
        datos = json.loads(texto)
        registrar_uso_ia("Identificar pieza por foto", True)
        return datos, None
    except json.JSONDecodeError as _err:
        anotar_error("identificar_pieza_por_foto", _err)
        registrar_uso_ia("Identificar pieza por foto", False)
        return None, "No pude interpretar la respuesta — probá con una foto más clara y de más cerca."
    except Exception as e:
        anotar_error("identificar_pieza_por_foto", e)
        registrar_uso_ia("Identificar pieza por foto", False)
        return None, traducir_error_gemini(e)


def _json_de_una_respuesta(texto):
    """Saca el JSON de una respuesta que puede venir con texto alrededor.

    Hace falta acá y no en las otras funciones de IA porque cuando se activa la búsqueda en
    Google el modelo NO acepta que se le exija responder solo JSON: contesta el JSON envuelto en
    una explicación, o adentro de un bloque markdown, o las dos cosas. Se busca la primera llave
    y la última, que es lo único que sobrevive a las tres formas."""
    t = (texto or "").strip()
    if "```" in t:
        partes = t.split("```")
        for p in partes:
            p = p[4:] if p.lower().startswith("json") else p
            if p.strip().startswith("{"):
                t = p
                break
    ini, fin = t.find("{"), t.rfind("}")
    if ini < 0 or fin <= ini:
        raise json.JSONDecodeError("no hay ningún objeto JSON en la respuesta", t or "", 0)
    return json.loads(t[ini:fin + 1])


def _lista_de_texto(valor, tope=20):
    """Una lista de strings, venga como venga.

    El modelo devuelve a veces un texto donde se le pidió una lista, y eso no se puede recorrer
    con un for: son las letras sueltas. Se vio probándolo — «0280155786, 0280150830» entraba
    como los códigos «0», «2», «8», «1», «5», «7»."""
    if isinstance(valor, str):
        valor = [x for x in re.split(r"[,;\n]", valor)]
    elif not isinstance(valor, list):
        valor = []
    return [str(x).strip() for x in valor if str(x).strip()][:tope]


def identificar_pieza_por_internet(imagen_bytes, pista=""):
    """Busca la pieza EN INTERNET a partir de la foto: qué es, para qué autos, y con qué
    números se vende. Devuelve (datos, error).

    Es el paso que faltaba para el caso más común de todos: la pieza no tiene el código
    legible —está gastado, tapado de grasa, o la etiqueta se cayó— y en el catálogo no hay
    ninguna foto contra la cual compararla. Ahí, hasta ahora, la app no tenía nada que decir.
    Y no es un caso raro: la comparación visual necesita que ALGUIEN haya cargado antes la foto
    de esa misma pieza, y una base recién armada tiene cero.

    A diferencia de identificar_pieza_por_foto(), que solo lee lo que está escrito en la pieza,
    esta sale a buscar afuera: se le activa la búsqueda de Google al modelo, así que puede
    mirar catálogos, foros y tiendas y volver con los números con que esa pieza se vende. Por
    eso también devuelve las páginas que usó — una identificación sin fuente no se puede
    verificar, y esto NO es una respuesta confirmada.

    LA REGLA QUE HACE QUE ESTO SEA USABLE está en la función de al lado, no acá: de todo lo que
    conteste, a la pantalla solo llegan como respuesta los códigos que EXISTEN EN TU CATÁLOGO.
    Un modelo de lenguaje inventa números de pieza con total seguridad, y no hay forma de
    distinguir por el texto uno inventado de uno real. Pero sí hay forma de distinguirlo por los
    datos: si el número está en tu base, alguien lo vende; si no, es una pista para chequear a
    mano y se muestra aparte, nunca mezclado con lo que tenés.

    'pista' es lo que sepa la persona —«es de un Gol 1.6», «va en el motor»— y cambia mucho el
    resultado: sin ella el modelo tiene que adivinar también el auto."""
    from google import genai
    from google.genai import types

    api_key = secretos_app().get("gemini_api_key")
    if not api_key:
        return None, "No configuraste 'gemini_api_key' en Streamlit Cloud (Settings → Secrets)."

    try:
        client = genai.Client(api_key=api_key)
        prompt = (
            "Sos un vendedor de repuestos de auto con muchos años de mostrador, en Argentina. "
            "En la foto hay un repuesto que un cliente trajo en la mano. NO tiene el código "
            "legible: por eso hay que identificarlo por lo que se ve.\n\n"
            + (f"Lo que sabe el cliente: {pista}\n\n" if pista.strip() else "")
            + "Buscá en internet para identificarla. Fijate en todo lo que sirva: la forma, el "
            "material, el tipo y la cantidad de conexiones (vías de la ficha, bocas, agujeros, "
            "dientes, roscas), la cantidad de caños o terminales, los logos o letras parciales "
            "que se lleguen a ver, y el color. Buscá esa combinación en catálogos de repuestos "
            "y en tiendas.\n\n"
            "Devolvé un JSON con esta forma exacta:\n"
            '{"tipo_pieza": "el nombre con que se pide en el mostrador, ej: SENSOR DE ROTACION", '
            '"descripcion": "una línea describiendo la pieza y sus rasgos distintivos", '
            '"autos": ["los autos en los que se usa, lo más concreto posible"], '
            '"codigos": ["los números con que se vende: OEM y de fabricantes de reposición"], '
            '"marca_visible": "la marca que se llegue a leer en la pieza, o null", '
            '"confianza": "alta/media/baja", '
            '"por_que": "en una línea, qué rasgo de la foto te hizo decidir"}\n\n'
            "Reglas que importan más que la respuesta:\n"
            "- Si no estás seguro, poné confianza baja y MENOS códigos. Un número inventado le "
            "hace perder una venta y la confianza del cliente.\n"
            "- «codigos» van tal como se escriben en los catálogos, uno por elemento, sin "
            "agregarles texto.\n"
            "- Si de la foto no se puede saber ni qué tipo de pieza es, poné confianza baja y "
            "«codigos» vacío. Decir «no sé» es una respuesta válida y útil."
        )
        respuesta = client.models.generate_content(
            model="gemini-flash-latest",
            contents=[prompt, types.Part.from_bytes(data=imagen_bytes, mime_type="image/jpeg")],
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                # Cero temperatura: acá no se quiere creatividad, se quiere que repita lo que
                # encontró. Con el valor por omisión inventaba más números.
                temperature=0.0,
            ),
        )
        datos = _json_de_una_respuesta(respuesta.text)

        # Las páginas que consultó. Sin esto la respuesta no se puede verificar, y una
        # identificación de repuesto que no se puede verificar no sirve para vender.
        datos["fuentes"] = []
        datos["consultas"] = []
        try:
            meta = respuesta.candidates[0].grounding_metadata
            for trozo in (getattr(meta, "grounding_chunks", None) or []):
                web = getattr(trozo, "web", None)
                if web and getattr(web, "uri", None):
                    datos["fuentes"].append({
                        "titulo": getattr(web, "title", None) or getattr(web, "domain", "") or web.uri,
                        "url": web.uri,
                    })
            datos["consultas"] = list(getattr(meta, "web_search_queries", None) or [])
        except Exception as _err:
            anotar_error("identificar_pieza_por_internet/fuentes", _err)

        # Se normaliza acá y no en la pantalla. Ver _lista_de_texto().
        for campo in ("codigos", "autos"):
            datos[campo] = _lista_de_texto(datos.get(campo))

        registrar_uso_ia("Identificar pieza por internet", True)
        return datos, None
    except json.JSONDecodeError as _err:
        anotar_error("identificar_pieza_por_internet", _err)
        registrar_uso_ia("Identificar pieza por internet", False)
        return None, ("No pude interpretar la respuesta. Probá de nuevo, o con una foto donde la "
                      "pieza se vea entera y sobre un fondo liso.")
    except Exception as e:
        anotar_error("identificar_pieza_por_internet", e)
        registrar_uso_ia("Identificar pieza por internet", False)
        return None, traducir_error_gemini(e)


def cruzar_con_el_catalogo_lo_de_internet(datos, familia=None, limite_texto=25):
    """Lo que dijo internet, pasado por tu catálogo. Devuelve un dict con cuatro listas.

    Esta es la función que convierte una respuesta de IA en algo que se puede usar para
    vender, y lo hace con una sola idea: NO se le cree al modelo, se le cree a tu base.

      - «exactos»:   códigos que dijo y que están cargados. Son los que valen.
      - «por_tipeo»: códigos que no están pero se escriben casi igual que uno que sí. Un
                     catálogo escribe «0 280 155 786» y otro «0280155786»; también es el
                     caso de un dígito leído mal.
      - «por_texto»: si ningún código pegó, se busca por la descripción que dio, con el mismo
                     buscador de siempre. Es más flojo, y por eso va último y se muestra como
                     lo que es.
      - «no_los_tenes»: los códigos que no están ni se parecen a nada. Se muestran aparte, con
                     su fuente, como pista para pedirle al proveedor — NUNCA mezclados con lo
                     que sí tenés, que es lo que haría creer que son parte de la respuesta.

    Un código inventado por el modelo cae solo en la última lista: para colarse en las otras
    tres tendría que coincidir con algo que alguien ya cargó."""
    salida = {"exactos": [], "por_tipeo": [], "por_texto": [], "no_los_tenes": []}
    if not datos:
        return salida

    # _lista_de_texto() otra vez acá, aunque identificar_pieza_por_internet() ya normaliza:
    # esta función es la que decide qué se muestra, y si alguna vez la llama otro camino con un
    # dict armado a mano, un texto suelto se recorrería letra por letra.
    vistos = set()
    for bruto in _lista_de_texto(datos.get("codigos")):
        # dividir_codigos() porque los catálogos escriben «0280155786 / F 000 TE1 124» en una
        # sola línea, y así se aprovechan los dos.
        for candidato in (dividir_codigos(bruto) or [bruto]):
            limpio = sanitizar(candidato)
            if not limpio or limpio in vistos:
                continue
            vistos.add(limpio)
            filas = buscar_por_codigo(limpio)
            if filas:
                for f in filas:
                    f["_pedido"] = candidato
                salida["exactos"].extend(filas)
                continue
            parecidos = codigos_por_tipeo(limpio)
            if parecidos:
                for f in parecidos:
                    f["_pedido"] = candidato
                salida["por_tipeo"].extend(parecidos)
            else:
                salida["no_los_tenes"].append(candidato)

    if not salida["exactos"] and not salida["por_tipeo"]:
        # El texto que se busca junta la pieza con el auto, que es como se pide en el mostrador.
        # Solo el tipo de pieza devuelve el rubro entero; solo el auto devuelve cualquier cosa.
        texto = " ".join(filter(None, [str(datos.get("tipo_pieza") or "")]
                                + _lista_de_texto(datos.get("autos"))[:2]))
        if texto.strip():
            try:
                filas = buscar_por_texto(texto)
            except Exception as _err:
                anotar_error("cruzar_con_el_catalogo_lo_de_internet", _err)
                filas = []
            if familia:
                filas = [f for f in filas
                         if clasificar_repuesto(f.get("Descripcion")) == familia]
            salida["por_texto"] = filas[:limite_texto]
    return salida


def extraer_datos_cedula(imagen_bytes):
    """Lee una foto de cédula verde/azul o título del auto y extrae patente, marca, modelo, año
    y motorización con Gemini. SIEMPRE hay que revisar antes de guardar — el OCR puede confundir
    caracteres parecidos (0/O, 1/I) y en la patente o el VIN eso es grave."""
    from google import genai
    from google.genai import types
    import json

    api_key = secretos_app().get("gemini_api_key")
    if not api_key:
        return None, "No configuraste 'gemini_api_key' en Streamlit Cloud (Settings → Secrets)."

    try:
        client = genai.Client(api_key=api_key)
        prompt = (
            "Esta es una foto de una cédula verde/azul o título de un vehículo argentino. Extraé "
            "ÚNICAMENTE un JSON válido (sin texto extra, sin markdown), con esta forma exacta: "
            '{"patente": "...", "marca": "...", "modelo": "...", "anio": "...", "motorizacion": "..."}. '
            "Si no podés leer algún campo con claridad, dejalo como null en vez de adivinar. No inventes datos."
        )
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=[prompt, types.Part.from_bytes(data=imagen_bytes, mime_type="image/jpeg")],
        )
        texto = response.text.strip()
        if texto.startswith("```"):
            texto = texto.split("```")[1]
            texto = texto[4:] if texto.lower().startswith("json") else texto
        datos = json.loads(texto)
        registrar_uso_ia("Leer cédula/título", True)
        return datos, None
    except json.JSONDecodeError as _err:
        anotar_error("extraer_datos_cedula", _err)
        registrar_uso_ia("Leer cédula/título", False)
        return None, "No pude interpretar la respuesta como datos del vehículo — probá con una foto más clara."
    except Exception as e:
        anotar_error("extraer_datos_cedula", e)
        registrar_uso_ia("Leer cédula/título", False)
        return None, traducir_error_gemini(e)


def transcribir_audio(audio_bytes, mime_type="audio/wav"):
    """Transcribe un audio a texto con Gemini — esto es solo 'hablar en vez de tipear', no un
    asistente conversacional: el texto transcripto se busca con el buscador normal de siempre."""
    from google import genai
    from google.genai import types

    api_key = secretos_app().get("gemini_api_key")
    if not api_key:
        return None, "No configuraste 'gemini_api_key' en Streamlit Cloud (Settings → Secrets)."

    try:
        client = genai.Client(api_key=api_key)
        prompt = "Transcribí exactamente lo que se dice en este audio, en español. Devolvé solo el texto transcripto, nada más — sin comillas, sin comentarios."
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=[prompt, types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)],
        )
        registrar_uso_ia("Búsqueda por voz", True)
        return response.text.strip(), None
    except Exception as e:
        anotar_error("transcribir_audio", e)
        registrar_uso_ia("Búsqueda por voz", False)
        return None, traducir_error_gemini(e)


def leer_remito_por_foto(imagen_bytes):
    """Le pide a Gemini que lea un remito/factura de proveedor y devuelva los ítems en JSON.
    Devuelve (lista_items, error) — lista_items siempre queda para revisión manual antes de
    tocar el stock, la IA nunca actualiza nada por sí sola."""
    from google import genai
    from google.genai import types
    import json

    api_key = secretos_app().get("gemini_api_key")
    if not api_key:
        return None, "No configuraste 'gemini_api_key' en Streamlit Cloud (Settings → Secrets)."

    try:
        client = genai.Client(api_key=api_key)
        prompt = (
            "Esta es una foto de un remito o factura de un proveedor de repuestos. Extraé cada ítem "
            "listado y devolvé ÚNICAMENTE un JSON válido (sin texto extra, sin markdown), con esta forma "
            'exacta: [{"codigo": "...", "descripcion": "...", "cantidad": 0, "costo_unitario": 0.0}, ...]. '
            "Si no podés leer algún campo con claridad, dejalo como null. No inventes datos que no estén "
            "visibles en la imagen."
        )
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=[prompt, types.Part.from_bytes(data=imagen_bytes, mime_type="image/jpeg")],
        )
        texto = response.text.strip()
        if texto.startswith("```"):
            texto = texto.split("```")[1]
            texto = texto[4:] if texto.lower().startswith("json") else texto
        items = json.loads(texto)
        if not isinstance(items, list):
            registrar_uso_ia("Leer remito por foto", False)
            return None, "Gemini no devolvió una lista de ítems reconocible."
        registrar_uso_ia("Leer remito por foto", True)
        return items, None
    except json.JSONDecodeError as _err:
        anotar_error("leer_remito_por_foto", _err)
        registrar_uso_ia("Leer remito por foto", False)
        return None, "No pude interpretar la respuesta como una lista de ítems — probá con una foto más clara."
    except Exception as e:
        anotar_error("leer_remito_por_foto", e)
        registrar_uso_ia("Leer remito por foto", False)
        return None, traducir_error_gemini(e)


def leer_cedula_por_foto(imagen_bytes):
    """Lee una cédula verde/azul o un título del automotor y devuelve los datos del vehículo.

    ES LA RESPUESTA A «DE LA PATENTE NO SALE NADA». No existe una base pública y gratuita que
    traduzca dominio a vehículo, pero el dato completo está impreso en el papel que el cliente
    lleva en la guantera: dominio, marca, modelo, año, motor y chasis. Una foto, una vez, y de
    ahí en más la patente sola alcanza para todo — que es lo que se pedía.

    Y lo que sale de acá es MEJOR que cualquier consulta: el número de motor y el de chasis no
    están en ninguna consulta gratuita, y son los que después dejan buscar por VIN.

    Devuelve (datos, error). Nada se guarda solo: los datos van a un formulario para revisar."""
    from google import genai
    from google.genai import types
    import json

    api_key = secretos_app().get("gemini_api_key")
    if not api_key:
        return None, "No configuraste 'gemini_api_key' en Streamlit Cloud (Settings → Secrets)."

    try:
        client = genai.Client(api_key=api_key)
        prompt = (
            "Esta es una foto de una cédula de identificación del automotor argentina (cédula "
            "verde o azul) o de un título del automotor. Extraé los datos del vehículo y devolvé "
            "ÚNICAMENTE un JSON válido (sin texto extra, sin markdown), con esta forma exacta: "
            '{"dominio": "...", "marca": "...", "modelo": "...", "anio": "...", '
            '"motor": "...", "chasis": "...", "titular": "..."}. '
            "El DOMINIO es la patente (AB123CD o ABC123). El AÑO es el año modelo, cuatro "
            "dígitos. MOTOR es el número de motor y CHASIS el número de chasis o VIN, que suelen "
            "ser largos y mezclar letras y números: copialos carácter por carácter, sin espacios. "
            "Si algún campo no se lee con claridad, dejalo como null: no completes ni adivines "
            "nada, un número de chasis inventado hace que después se busquen repuestos de otro "
            "auto."
        )
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=[prompt, types.Part.from_bytes(data=imagen_bytes, mime_type="image/jpeg")],
        )
        texto = response.text.strip()
        if texto.startswith("```"):
            texto = texto.split("```")[1]
            texto = texto[4:] if texto.lower().startswith("json") else texto
        datos = json.loads(texto)
        if not isinstance(datos, dict):
            registrar_uso_ia("Leer cédula por foto", False)
            return None, "Gemini no devolvió los datos en la forma esperada."
        # Se normaliza acá y no en la pantalla: el dominio se guarda sin espacios ni guiones
        # porque así se busca, y el chasis en mayúsculas porque así se compara con el VIN.
        limpio = {}
        for clave in ("dominio", "marca", "modelo", "anio", "motor", "chasis", "titular"):
            valor = datos.get(clave)
            limpio[clave] = "" if valor is None else str(valor).strip()
        limpio["dominio"] = re.sub(r'[^A-Z0-9]', '', limpio["dominio"].upper())
        limpio["chasis"] = re.sub(r'[^A-Z0-9]', '', limpio["chasis"].upper())
        limpio["motor"] = re.sub(r'\s+', '', limpio["motor"].upper())
        limpio["anio"] = (re.findall(r'(19|20)\d{2}', limpio["anio"]) and
                          re.search(r'((?:19|20)\d{2})', limpio["anio"]).group(1)) or ""
        registrar_uso_ia("Leer cédula por foto", True)
        return limpio, None
    except json.JSONDecodeError as _err:
        anotar_error("leer_cedula_por_foto", _err)
        registrar_uso_ia("Leer cédula por foto", False)
        return None, ("No pude interpretar la respuesta — probá con una foto más derecha y con "
                      "buena luz, que se lean los números.")
    except Exception as e:
        anotar_error("leer_cedula_por_foto", e)
        registrar_uso_ia("Leer cédula por foto", False)
        return None, traducir_error_gemini(e)


def cotejar_items_remito(items):
    """Para cada ítem leído del remito, busca si el código ya existe en el catálogo."""
    resultado = []
    for item in items:
        codigo = (item.get("codigo") or "").strip()
        clean = sanitizar(codigo) if codigo else ""
        producto_id, marca_actual, stock_actual = None, None, None
        if clean:
            c.execute("""SELECT p.id, m.nombre AS marca, p.stock FROM productos p
                         JOIN marcas m ON m.id = p.marca_id WHERE p.codigo_clean = ? LIMIT 1""", (clean,))
            fila = c.fetchone()
            if fila:
                producto_id, marca_actual, stock_actual = fila["id"], fila["marca"], fila["stock"]
        resultado.append({
            "Código": codigo or "(sin leer)",
            "Descripción": item.get("descripcion") or "",
            "Cantidad": item.get("cantidad") if item.get("cantidad") is not None else 0,
            "Costo unitario": item.get("costo_unitario") if item.get("costo_unitario") is not None else 0.0,
            "_producto_id": producto_id,
            "Coincide con": f"{marca_actual} (stock actual: {stock_actual})" if producto_id else "❌ No está en el catálogo",
        })
    return resultado


def aplicar_carga_remito(items_cotejados):
    """Suma la cantidad recibida al stock de los ítems que sí coinciden con un producto ya cargado."""
    actualizados = 0
    with db_lock:
        for item in items_cotejados:
            if item.get("_producto_id"):
                cantidad = item.get("Cantidad") or 0
                c.execute("UPDATE productos SET stock = COALESCE(stock, 0) + ? WHERE id = ?",
                          (cantidad, item["_producto_id"]))
                actualizados += 1
        conn.commit()
    return actualizados


def actualizar_precio_stock(producto_id, precio, stock, costo=None, stock_mostrado=None):
    """Guarda precio, stock y —si se pasa— el precio de costo. Devuelve False si el producto ya no
    está, "stock_cambio" si no se tocó el stock porque otro lo cambió mientras se editaba, y True
    si se guardó todo.

    EL STOCK NO SE PISA. La pantalla de edición mandaba siempre el stock que mostraba al
    dibujarse, aunque solo se hubiera cambiado el precio. Con varias personas a la vez: uno abre
    el editor con stock 10, otro cierra una venta de 2 (queda 8), el primero guarda el precio
    nuevo y el stock vuelve a 10. Stock inventado y en silencio. Con `stock_mostrado` —lo que la
    pantalla mostraba—: si no se cambió, el stock no se escribe; si se cambió pero en la base ya
    no está lo que se mostraba, tampoco, y se avisa. El precio se guarda igual.

    El costo va como parámetro opcional para que las llamadas viejas sigan funcionando: hay
    varias en la app y cambiarlas todas de golpe es pedir un error tonto.

    Dos cosas que parecen detalles y no lo son:

    COSTO CERO ES UN COSTO. Antes decía `costo or None`, y en Python el cero es falso: pedir
    que el costo quede en 0 —mercadería bonificada, una muestra, un costo que se quiere poner
    en cero a propósito— guardaba NULL. Comprobado sobre una copia de la base real: pidiendo
    guardar 5000 queda 5000, pidiendo guardar 0 quedaba None. Y que el cero es un valor que
    esta app usa de verdad se ve en la misma base: hay 21 productos con precio 0. Quién decide
    si el costo se toca es `costo is not None`, que es la pregunta correcta; el `or` de adentro
    solo pisaba un valor legítimo.

    SI EL PRODUCTO NO ESTÁ, NO SE ESCRIBE NADA. Los dos UPDATE no encuentran fila y se van en
    silencio, pero el INSERT del historial sí se intentaba, porque `precio_anterior` quedaba en
    None y None siempre es distinto del precio nuevo. Con las claves foráneas prendidas —que lo
    están— eso revienta con IntegrityError adentro de la transacción y la pantalla se cae con
    un error crudo. Pasa si alguien borra el producto desde la otra sesión entre que se dibujó
    la pantalla y se apretó Guardar, que es exactamente para lo que la app tiene una conexión
    por sesión. Reproducido con un id inexistente."""
    # Todo o nada: el precio nuevo y su renglón en el historial van juntos. Si se guarda uno
    # sin el otro, el historial deja de servir justo para lo que está: saber cuándo subió.
    with db_lock, transaccion():
        c.execute("SELECT precio FROM productos WHERE id = ?", (producto_id,))
        fila = c.fetchone()
        if not fila:
            return False
        precio_anterior = fila["precio"]
        if costo is not None:
            c.execute("UPDATE productos SET precio_costo = ? WHERE id = ?",
                      (costo, producto_id))
        c.execute("UPDATE productos SET precio = ? WHERE id = ?", (precio, producto_id))
        resultado = True
        if stock_mostrado is None:
            c.execute("UPDATE productos SET stock = ? WHERE id = ?", (stock, producto_id))
        elif stock != stock_mostrado:
            c.execute("UPDATE productos SET stock = ? WHERE id = ? AND COALESCE(stock, 0) = ?",
                      (stock, producto_id, stock_mostrado))
            if c.rowcount == 0:
                resultado = "stock_cambio"
        # Solo se guarda un registro nuevo en el historial si el precio realmente cambió
        # (evita ensuciar el historial cada vez que se toca el stock sin tocar el precio).
        if precio_anterior != precio:
            c.execute("INSERT INTO historial_precios (producto_id, precio) VALUES (?, ?)", (producto_id, precio))
    return resultado


def historial_precio_producto(producto_id, limite=50):
    c.execute("""SELECT precio AS "Precio", fecha AS "Fecha" FROM historial_precios
                 WHERE producto_id = ? ORDER BY fecha DESC LIMIT ?""", (producto_id, limite))
    return filas_a_listas(c)


# Palabras que aparecen en cualquier pedido y no aportan: si se toman por modelo de auto,
# «necesito algo para el auto» terminaría buscando productos que digan «NECESITO».
_PALABRAS_DE_RELLENO = {
    "PARA", "DEL", "LOS", "LAS", "CON", "SIN", "UNA", "UNO", "UNAS", "UNOS", "QUE", "POR",
    "NECESITO", "QUIERO", "BUSCO", "TENES", "TIENE", "HAY", "DAME", "PASAME", "AUTO", "COCHE",
    "CAMIONETA", "VEHICULO", "REPUESTO", "PIEZA", "ALGO", "ESTE", "ESTA", "ESE", "ESA",
}


def interpretar_pedido_hablado(texto):
    """Saca de una frase suelta qué pieza y qué auto está pidiendo el cliente.

    En el mostrador nadie dice un código: dice «pastillas de freno para un Gol 1.6». Cuando la
    búsqueda por texto no encuentra nada, hoy se muere ahí. Pero de esa frase se puede sacar
    bastante: qué RUBRO es (con el clasificador que ya usamos) y qué AUTO (con la lista de
    marcas de vehículo). Con esas dos cosas se puede ofrecer algo en vez de nada."""
    if not texto or not texto.strip():
        return None
    limpio = normalizar_texto(texto)
    familia = clasificar_repuesto(texto)
    marca_auto = next((mv for mv in MARCAS_VEHICULO
                       if f" {mv} " in f" {limpio} "), None)
    # El cliente casi nunca dice la marca: dice «para el Gol», «para un Palio». Se busca el
    # MODELO directamente en las descripciones del catálogo, que es donde están los que
    # realmente vendés. Sin esto, «bujías para el gol» perdía el auto entero.
    modelo_suelto = None
    if not marca_auto:
        # Se descartan también las palabras que ya se usaron para reconocer el RUBRO: en
        # «pastillas de freno para un gol», «freno» aparece en muchas descripciones y se
        # tomaba por modelo de auto. No rompía el resultado, pero decía una cosa por otra —
        # y un cartel que dice «para un FRENO» hace desconfiar de todo lo demás.
        del_rubro = set()
        if familia and familia in FAMILIAS_REPUESTO:
            for clave in FAMILIAS_REPUESTO[familia]:
                del_rubro.update(clave.split())
        palabras_utiles = [w for w in limpio.split()
                           if len(w) >= 3 and w not in _PALABRAS_DE_RELLENO
                           and w not in del_rubro
                           and not w.replace(".", "").replace(",", "").isdigit()]
        for w in palabras_utiles:
            try:
                _cond, _par = like_en_descripcion(f"% {w} %")
                c.execute(f"SELECT COUNT(*) FROM productos p WHERE {_cond}", _par)
                if c.fetchone()[0] >= 2:
                    modelo_suelto = w
                    break
            except Exception as _err:
                anotar_error("interpretar_pedido_hablado", _err)
                break
    cil = re.search(r'\b(\d[.,]\d)\b', limpio)
    anio = re.search(r'\b(19\d{2}|20\d{2})\b', limpio)
    # El modelo: lo que queda después de sacar la marca, el rubro y los números
    modelo = modelo_suelto
    if marca_auto:
        resto = limpio.split(marca_auto, 1)[1].strip() if marca_auto in limpio else ""
        candidatos = [w for w in resto.split()
                      if len(w) >= 3 and not w.replace(".", "").replace(",", "").isdigit()
                      and w not in ("PARA", "DEL", "LOS", "LAS", "CON", "SIN")]
        modelo = candidatos[0] if candidatos else modelo_suelto
    if familia == "Sin clasificar" and not marca_auto and not modelo_suelto:
        return None
    return {"familia": familia if familia != "Sin clasificar" else None,
            "marca_auto": marca_auto, "modelo": modelo,
            "cilindrada": cil.group(1).replace(",", ".") if cil else None,
            "anio": int(anio.group(1)) if anio else None}


# ============================================================================================
# BUSCAR POR PIEZA Y AUTO
# ============================================================================================
def buscar_por_pieza_y_auto(familia=None, marca_auto=None, modelo=None,
                            cilindrada=None, limite=60):
    """Lo que tenés de ese rubro para ese auto, aunque no coincida ni una palabra del pedido."""
    condiciones, params = [], []
    for _texto in (marca_auto, modelo):
        if _texto:
            _cond, _par = like_en_descripcion(f"%{normalizar_texto(_texto)}%")
            condiciones.append(_cond)
            params.extend(_par)
    if cilindrada:
        condiciones.append("p.descripcion LIKE ?")
        params.append(f"%{cilindrada}%")
    if not condiciones:
        return []
    c.execute(f"""SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
                         m.nombre AS "Marca", p.precio AS "Precio", p.stock AS "Stock"
                  FROM productos p JOIN marcas m ON m.id = p.marca_id
                  WHERE {" AND ".join(condiciones)}
                  LIMIT 800""", params)
    filas = filas_a_listas(c)
    if familia:
        filas = [f for f in filas if clasificar_repuesto(f["Descripcion"]) == familia]
    filas.sort(key=lambda f: (-(f["Stock"] or 0), f["Codigo"]))
    return filas[:limite]


def autos_de_un_codigo(clean_code, limite=200):
    """A qué autos le va este código, según los catálogos de fabricante que cargaste."""
    if not clean_code:
        return []
    try:
        c.execute("""SELECT DISTINCT marca_auto AS "Marca", modelo_auto AS "Modelo",
                            motor AS "Motor",
                            COALESCE(anio_desde, '') || '-' || COALESCE(anio_hasta, '') AS "Años",
                            marca_repuesto AS "Según"
                     FROM aplicaciones WHERE codigo_clean = ?
                     ORDER BY marca_auto, modelo_auto LIMIT ?""", (clean_code, limite))
        return filas_a_listas(c)
    except sqlite3.OperationalError as _err:
        anotar_error("autos_de_un_codigo", _err)
        return []


def le_sirve_a_este_auto(clean_code, marca_auto, modelo="", anio=None):
    """¿Este código le va a ese auto? Devuelve (respuesta, motivo).

    Es la pregunta que más se hace en el mostrador después de «¿lo tenés?», y la que más caro
    sale contestar mal: una pieza vendida para el auto equivocado vuelve, y con ella se va la
    confianza del cliente.

    Se responde SOLO con lo que dice el catálogo del fabricante. Cuando no hay dato, se dice que
    no hay dato — no se estira una respuesta que no se tiene."""
    aplic = autos_de_un_codigo(clean_code)
    if not aplic:
        return None, ("Ese código no figura en ningún catálogo de aplicaciones cargado, así que "
                      "no puedo confirmarlo por acá. Verificalo por medidas o con el proveedor.")

    marca_auto = (marca_auto or "").strip().upper()
    modelo = (modelo or "").strip().upper()
    coinciden = [a for a in aplic if marca_auto and marca_auto in (a["Marca"] or "").upper()]
    if modelo:
        coinciden = [a for a in coinciden if modelo in (a["Modelo"] or "").upper()]

    if not coinciden:
        marcas_que_si = sorted({a["Marca"] for a in aplic})[:6]
        return False, ("Según el catálogo, ese código **no** figura para ese auto. Sí figura "
                       f"para: {', '.join(marcas_que_si)}.")

    if anio:
        en_anio = []
        for a in coinciden:
            desde, hasta = (a["Años"].split("-") + [""])[:2]
            d = int(desde) if desde.isdigit() else None
            h = int(hasta) if hasta.isdigit() else None
            if (d is None or d <= int(anio)) and (h is None or h >= int(anio)):
                en_anio.append(a)
        if not en_anio:
            rangos = ", ".join(sorted({a["Años"] for a in coinciden}))[:80]
            return False, (f"Figura para ese modelo, pero **no para el año {anio}**. "
                           f"El catálogo lo da para: {rangos}.")
        coinciden = en_anio

    motores = sorted({a["Motor"] for a in coinciden if a["Motor"]})[:5]
    fuente = sorted({a["Según"] for a in coinciden})
    detalle = f"Lo dice el catálogo de {', '.join(fuente)}."
    if motores:
        detalle += f" Motorizaciones: {', '.join(motores)}."
    return True, detalle


def identificar_codigo_ajeno(clean_code):
    """Un código que NO tenés cargado, pero que aparece en algún catálogo de fabricante.

    Es una venta que hoy se pierde. Te piden un código, no lo tenés, y la app dice «no hay
    ningún producto con ese código» — punto. Pero puede estar en un catálogo de aplicaciones
    que ya cargaste: ahí figura qué pieza es, de qué marca y a qué autos le va.

    Con eso se puede ofrecer un equivalente en vez de perder al cliente."""
    if not clean_code:
        return None
    try:
        c.execute("""SELECT codigo, marca_repuesto, tipo_pieza,
                            COUNT(*) AS aplicaciones,
                            COUNT(DISTINCT marca_auto || '|' || modelo_auto) AS autos
                     FROM aplicaciones WHERE codigo_clean = ?
                     GROUP BY codigo, marca_repuesto, tipo_pieza LIMIT 1""", (clean_code,))
        info = c.fetchone()
    except sqlite3.OperationalError as _err:
        anotar_error("identificar_codigo_ajeno", _err)
        return None
    if not info:
        return None

    c.execute("""SELECT DISTINCT marca_auto, modelo_auto, motor, anio_desde, anio_hasta
                 FROM aplicaciones WHERE codigo_clean = ?
                 ORDER BY marca_auto, modelo_auto LIMIT 40""", (clean_code,))
    autos = [dict(r) for r in c.fetchall()]
    return {"codigo": info["codigo"], "marca": info["marca_repuesto"],
            "tipo": info["tipo_pieza"] or "", "autos": autos,
            "cantidad_autos": info["autos"]}


def equivalentes_para_los_mismos_autos(clean_code, limite=30):
    """Qué SÍ tenés que le sirva a los mismos autos que ese código que no tenés.

    Es el paso que convierte «no lo tengo» en una venta. Si el código que te piden va a un
    Palio 1.0 y vos tenés otra marca que, según su propio catálogo, también va a ese Palio 1.0,
    eso es lo que hay que ofrecer.

    Se exige el mismo tipo de pieza y otro fabricante, igual que al deducir equivalencias: dos
    piezas que van al mismo auto no son intercambiables si una es una bujía y la otra un filtro."""
    try:
        c.execute("""SELECT DISTINCT p.codigo_raw AS "Código", m.nombre AS "Marca",
                            p.descripcion AS "Descripción", p.precio AS "Precio",
                            p.stock AS "Stock", b.marca_repuesto AS "Según el catálogo de",
                            COUNT(DISTINCT b.marca_auto || b.modelo_auto || b.motor) AS "Autos en común"
                     FROM aplicaciones a
                     JOIN aplicaciones b
                       ON a.marca_auto = b.marca_auto AND a.modelo_auto = b.modelo_auto
                      AND a.motor = b.motor
                      AND COALESCE(a.tipo_pieza,'') = COALESCE(b.tipo_pieza,'')
                      AND a.marca_repuesto <> b.marca_repuesto
                     JOIN productos p ON p.codigo_clean = b.codigo_clean
                     JOIN marcas m ON m.id = p.marca_id
                     WHERE a.codigo_clean = ?
                       AND COALESCE(a.tipo_pieza,'') <> ''
                     GROUP BY p.id
                     ORDER BY (p.stock > 0) DESC, "Autos en común" DESC LIMIT ?""",
                  (clean_code, limite))
        return filas_a_listas(c)
    except sqlite3.OperationalError as _err:
        anotar_error("equivalentes_para_los_mismos_autos", _err)
        return []


def quien_conviene_por_rubro(limite=40, minimo_comparaciones=5):
    """En los repuestos que tenés de varias marcas, cuál sale más barata más seguido.

    Solo se comparan productos que son EQUIVALENTES entre sí: comparar el precio promedio de dos
    marcas sin eso no dice nada, porque una puede vender frenos caros y la otra filtros baratos.
    Acá cada comparación es entre dos códigos que hacen el mismo trabajo."""
    # SIN_CONTAR_EL_ESPEJO porque acá se cuentan COMPARACIONES, y el mínimo para que una marca
    # entre en el ranking son 5: con el par anotado de ida y de vuelta, dos comparaciones y
    # media alcanzaban para pasar un filtro pensado para cinco.
    c.execute(f"""SELECT ma.nombre AS marca_a, mb.nombre AS marca_b,
                        pa.precio AS precio_a, pb.precio AS precio_b
                 FROM equivalencias e
                 JOIN productos pa ON pa.id = e.producto_a_id
                 JOIN productos pb ON pb.id = e.producto_b_id
                 JOIN marcas ma ON ma.id = pa.marca_id
                 JOIN marcas mb ON mb.id = pb.marca_id
                 WHERE {SIN_CONTAR_EL_ESPEJO} AND pa.precio > 0 AND pb.precio > 0
                   AND ma.nombre <> mb.nombre
                   AND COALESCE(e.confianza, 50) >= 50
                   AND MAX(pa.precio, pb.precio) / MIN(pa.precio, pb.precio) < 8""")
    marcador = {}
    for r in c.fetchall():
        clave = tuple(sorted((r["marca_a"], r["marca_b"])))
        d = marcador.setdefault(clave, {"total": 0, clave[0]: 0, clave[1]: 0, "dif": []})
        d["total"] += 1
        barata = r["marca_a"] if r["precio_a"] < r["precio_b"] else r["marca_b"]
        d[barata] = d.get(barata, 0) + 1
        d["dif"].append(max(r["precio_a"], r["precio_b"]) / min(r["precio_a"], r["precio_b"]))

    salida = []
    for (ma, mb), d in marcador.items():
        if d["total"] < minimo_comparaciones:
            continue
        gana, pierde = (ma, mb) if d[ma] >= d[mb] else (mb, ma)
        proporcion = d[gana] / d["total"]
        d["dif"].sort()
        mediana_dif = d["dif"][len(d["dif"]) // 2]
        salida.append({
            "Comparación": f"{ma} vs {mb}",
            "Sale más barata": gana,
            "En": f"{proporcion * 100:.0f}% de los casos",
            "Diferencia típica": f"{(mediana_dif - 1) * 100:.0f}%",
            "Repuestos comparados": d["total"],
            "_prop": proporcion, "_total": d["total"],
        })
    salida.sort(key=lambda x: (-x["_prop"], -x["_total"]))
    return salida[:limite]


def variacion_de_precios_por_marca(meses=6, minimo_productos=10):
    """Cuánto aumentó cada proveedor, medido sobre tu propio historial.

    La app viene guardando cada cambio de precio y solo lo mostraba producto por producto. Pero
    la pregunta que importa no es cuánto aumentó UN filtro, sino cuánto aumentó el proveedor:
    con eso se decide a quién comprarle y con quién hay que hablar.

    Se usa la MEDIANA, no el promedio. Un solo precio mal cargado —de esos que llegan con el
    separador de decimales al revés y quedan cien veces más caros— alcanza para inflar un
    promedio y hacer parecer que un proveedor aumentó 400%. La mediana lo ignora.

    SOLO LOS QUE TIENEN DOS PRECIOS O MÁS, y es lo que hacía lenta la pantalla «Para pedir».
    Se traía una fila por cada uno de los 70.888 productos para descartar casi todas en Python:
    sobre la base real, 46.644 productos tienen historial y casi todos con UN precio solo, que
    no puede ser un aumento. Sola tardaba 0,18 s y no se notaba. Pero cada fila la arma Python,
    y mientras corre la tarea de fondo —después de cada importación y de cada actualización,
    que es cuando alguien está usando la app— cada una de las 70.888 espera su turno para
    agarrar el intérprete: la pantalla pasaba a tardar 9 s por clic. Con un solo precio, el
    «antes» y el «ahora» son el mismo y el producto se descartaba igual, así que filtrar acá
    no cambia el resultado: se comprobó con el mismo historial por los dos caminos."""
    c.execute("""WITH con_cambios AS (SELECT producto_id FROM historial_precios
                                      GROUP BY producto_id HAVING COUNT(*) >= 2)
                 SELECT m.nombre AS marca, p.id AS pid,
                        (SELECT hp.precio FROM historial_precios hp
                          WHERE hp.producto_id = p.id AND hp.fecha >= datetime('now', ?)
                          ORDER BY hp.fecha ASC LIMIT 1) AS antes,
                        (SELECT hp.precio FROM historial_precios hp
                          WHERE hp.producto_id = p.id
                          ORDER BY hp.fecha DESC LIMIT 1) AS ahora
                 FROM con_cambios cc
                 JOIN productos p ON p.id = cc.producto_id
                 JOIN marcas m ON m.id = p.marca_id""",
              (f"-{int(meses) * 30} days",))
    por_marca = {}
    for r in c.fetchall():
        antes, ahora = r["antes"], r["ahora"]
        if not antes or not ahora or antes <= 0 or ahora <= 0 or antes == ahora:
            continue
        razon = ahora / antes
        # Se descartan los saltos absurdos: son errores de carga, no aumentos
        if razon > 20 or razon < 0.05:
            continue
        por_marca.setdefault(r["marca"], []).append(razon)

    salida = []
    for marca, razones in por_marca.items():
        if len(razones) < minimo_productos:
            continue
        razones.sort()
        n = len(razones)
        mediana = razones[n // 2] if n % 2 else (razones[n // 2 - 1] + razones[n // 2]) / 2
        subieron = sum(1 for x in razones if x > 1.01)
        salida.append({
            "Marca": marca,
            "Aumento típico": f"{(mediana - 1) * 100:+.0f}%",
            "Productos medidos": n,
            "Subieron": f"{subieron / n * 100:.0f}%",
            "El que más subió": f"{(razones[-1] - 1) * 100:+.0f}%",
            "El que menos": f"{(razones[0] - 1) * 100:+.0f}%",
            "_mediana": mediana,
        })
    salida.sort(key=lambda x: -x["_mediana"])
    return salida


# ============================================================================================
# DISCONTINUADOS Y REEMPLAZOS DE FÁBRICA
# ============================================================================================
def productos_probablemente_discontinuados(marca_id=None, listas_seguidas=2, limite=300):
    """Productos que el proveedor dejó de mandar en sus últimas listas.

    Cuando llega una lista nueva de una marca, los productos que vienen se actualizan y los que
    NO vienen quedan intactos. Si un código faltó en las últimas dos o tres listas, casi seguro
    el proveedor lo discontinuó o le cambió el número — pero en la base sigue figurando igual,
    con su precio viejo, como si nada.

    Eso cuesta plata de dos maneras: se cotiza algo que ya no existe y el cliente se va cuando
    no llega, y el stock muerto queda ocupando lugar sin que nadie lo note.

    No se borra nada: son candidatos para que los mires. Un producto puede faltar en una lista
    simplemente porque el proveedor lo mandó aparte."""
    c.execute("""SELECT m.id, m.nombre, COUNT(*) AS listas, MAX(i.fecha) AS ultima
                 FROM importaciones i JOIN marcas m ON UPPER(m.nombre) = UPPER(i.marca)
                 WHERE (? IS NULL OR m.id = ?)
                 GROUP BY m.id HAVING COUNT(*) >= ?""",
              (marca_id, marca_id, listas_seguidas))
    marcas = [dict(r) for r in c.fetchall()]
    if not marcas:
        return [], 0

    salida = []
    revisados = 0
    for mk in marcas:
        # La fecha de corte: el comienzo de las últimas N listas de esta marca
        c.execute("""SELECT fecha FROM importaciones
                     WHERE UPPER(marca) = UPPER(?) ORDER BY fecha DESC LIMIT ?""",
                  (mk["nombre"], listas_seguidas))
        fechas = [r["fecha"] for r in c.fetchall()]
        if len(fechas) < listas_seguidas:
            continue
        corte = fechas[-1]

        c.execute("""SELECT p.id AS "_id", p.codigo_raw AS "Código", p.descripcion AS "Descripción",
                            p.precio AS "Precio", p.stock AS "Stock",
                            (SELECT MAX(hp.fecha) FROM historial_precios hp
                              WHERE hp.producto_id = p.id) AS "_ultimo_precio",
                            (SELECT COUNT(*) FROM ventas_registradas v
                              WHERE v.producto_id = p.id
                                AND v.fecha >= datetime('now','-365 days')) AS "Ventas del año"
                     FROM productos p WHERE p.marca_id = ?""", (mk["id"],))
        for f in filas_a_listas(c):
            revisados += 1
            ultimo = f.pop("_ultimo_precio", None)
            # Sin precio nunca cargado no se puede concluir nada: puede que esa marca no traiga
            # precios en sus listas.
            if not ultimo or ultimo >= corte:
                continue
            f["Marca"] = mk["nombre"]
            f["Sin aparecer desde"] = str(ultimo)[:10]
            f["_stock"] = f["Stock"] or 0
            salida.append(f)

    # Primero los que tenés en stock: es plata parada en algo que quizá ya no se pide
    salida.sort(key=lambda x: (-(x["_stock"] or 0), -(x["Ventas del año"] or 0)))
    return salida[:limite], revisados


def guardar_reemplazo(codigo_viejo, codigo_nuevo, marca="", nota=""):
    """Anota que un código fue reemplazado por otro. Devuelve (ok, mensaje)."""
    v, n = sanitizar(codigo_viejo), sanitizar(codigo_nuevo)
    if not v or not n:
        return False, "Faltan los dos códigos."
    if v == n:
        return False, "Son el mismo código."
    # Si el nuevo ya lleva de vuelta al viejo, esto arma un círculo (A→B→A). Buscar no se cuelga
    # —la cadena corta al repetirse— pero la respuesta pasa a depender de por dónde se entre, que
    # es peor que no tener el dato: se ve creíble y está mal.
    if any(paso["clean"] == v for paso in cadena_de_reemplazos(n)):
        return False, (f"No se puede: {codigo_nuevo} ya lleva de vuelta a {codigo_viejo}. "
                       "Revisá cuál de los dos es el vigente.")
    # Un código viejo tiene UN reemplazo vigente, no varios. La clave de la tabla es el par
    # (viejo, nuevo), así que cargar A→B y después A→C dejaba las dos filas, y la búsqueda seguía
    # la que SQLite devolviera primero: la misma consulta podía contestar B o C según cómo
    # estuvieran guardadas. Se reemplaza el anterior y se avisa cuál se pisó.
    anterior = None
    try:
        c.execute("""SELECT codigo_nuevo FROM reemplazos_codigo
                     WHERE codigo_viejo_clean = ? AND codigo_nuevo_clean != ?""", (v, n))
        fila_previa = c.fetchone()
        anterior = fila_previa["codigo_nuevo"] if fila_previa else None
    except sqlite3.OperationalError as _err:
        anotar_error("guardar_reemplazo", _err)
        anterior = None
    with db_lock:
        c.execute("DELETE FROM reemplazos_codigo WHERE codigo_viejo_clean = ?", (v,))
        c.execute("""INSERT OR REPLACE INTO reemplazos_codigo
                     (codigo_viejo, codigo_viejo_clean, codigo_nuevo, codigo_nuevo_clean,
                      marca, nota, cargado_por)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (codigo_viejo.strip(), v, codigo_nuevo.strip(), n,
                   (marca or "").strip().upper() or None, (nota or "").strip() or None,
                   obtener_usuario_actual()))
        conn.commit()
    if anterior:
        return True, (f"{codigo_viejo} → {codigo_nuevo} anotado. "
                      f"Antes decía que lo reemplazaba {anterior}; quedó este.")
    return True, f"{codigo_viejo} → {codigo_nuevo} anotado."


def cadena_de_reemplazos(clean_code, tope=6):
    """Sigue la cadena de reemplazos hasta el código vigente.

    Los fabricantes discontinúan un código y lo reemplazan por otro, que a su vez puede volver
    a reemplazarse. Sin esto, alguien busca el código viejo, no aparece, y se rechaza una venta
    creyendo que la pieza no existe — cuando en realidad existe con otro número.

    Tiene tope de saltos porque un dato mal cargado puede armar un círculo (A→B→A) y dejar la
    búsqueda dando vueltas para siempre."""
    if not clean_code:
        return []
    # Copia de cada paso: lo recordado no se toca desde afuera. Ver _recordado().
    return [dict(x) for x in _recordado(("reemplazos", clean_code, tope),
                                        lambda: _cadena_de_reemplazos(clean_code, tope))]


def _cadena_de_reemplazos(clean_code, tope):
    cadena, visto, actual = [], {clean_code}, clean_code
    for _ in range(tope):
        try:
            c.execute("""SELECT codigo_nuevo, codigo_nuevo_clean, marca, nota
                         FROM reemplazos_codigo WHERE codigo_viejo_clean = ?
                         ORDER BY fecha DESC LIMIT 1""", (actual,))
            fila = c.fetchone()
        except sqlite3.OperationalError as _err:
            anotar_error("cadena_de_reemplazos", _err)
            return []
        if not fila or fila["codigo_nuevo_clean"] in visto:
            break
        cadena.append({"codigo": fila["codigo_nuevo"], "clean": fila["codigo_nuevo_clean"],
                       "marca": fila["marca"] or "", "nota": fila["nota"] or ""})
        visto.add(fila["codigo_nuevo_clean"])
        actual = fila["codigo_nuevo_clean"]
    return cadena


# ============================================================================================
# REPOSICIÓN Y FAVORITOS
# ============================================================================================
def productos_estancados(dias_sin_vender=180, minimo_stock=1, limite=100):
    """Lo que tenés en el estante y no se mueve. Es capital dormido.

    Se cruza el stock con la última venta. Lo que nunca se vendió cuenta como estancado solo si
    hace rato que está cargado: un producto que entró la semana pasada todavía no tuvo chance.

    Para saber desde cuándo está se usa el primer cambio de precio y, si no tuvo ninguno, la
    fecha en que se cargó. Antes se miraba SOLO el historial de precios, y ese historial recién
    se escribe cuando un precio CAMBIA: un producto importado una vez y nunca tocado no tiene
    ninguna fila ahí. O sea que quedaban afuera justamente los que nunca se movieron —los clavos
    más clavos, que son los que esta pantalla existe para encontrar."""
    try:
        # Las fechas salen de dos tablas ya resumidas, no de una subconsulta por producto: así
        # las ventas se leen una sola vez en total y no una vez por artículo. Tampoco se puede
        # unir directo contra las tablas crudas, porque un producto con 30 ventas y 10 cambios
        # de precio saldría 300 veces antes de agrupar.
        c.execute("""SELECT p.id AS "_id", p.codigo_raw AS "Código", m.nombre AS "Marca",
                            p.descripcion AS "Descripción", p.stock AS "Stock",
                            p.precio AS "Precio",
                            v.ultima AS "_ultima_venta",
                            COALESCE(h.primera, p.created_at) AS "_desde"
                     FROM productos p
                     JOIN marcas m ON m.id = p.marca_id
                     LEFT JOIN (SELECT producto_id, MAX(fecha) AS ultima
                                  FROM ventas_registradas GROUP BY producto_id) v
                            ON v.producto_id = p.id
                     LEFT JOIN (SELECT producto_id, MIN(fecha) AS primera
                                  FROM historial_precios GROUP BY producto_id) h
                            ON h.producto_id = p.id
                     WHERE COALESCE(p.stock, 0) >= ?""", (minimo_stock,))
        filas = filas_a_listas(c)
    except sqlite3.OperationalError as _err:
        anotar_error("productos_estancados", _err)
        return []

    from datetime import datetime as _dt
    hoy = _dt.now()
    salida = []
    for f in filas:
        ultima = f.pop("_ultima_venta", None)
        desde = f.pop("_desde", None)
        if ultima:
            try:
                dias = (hoy - _dt.strptime(str(ultima)[:10], "%Y-%m-%d")).days
            except Exception as _err:
                anotar_error("productos_estancados", _err)
                continue
            detalle = f"hace {dias} día(s)"
        else:
            # Nunca vendido: solo cuenta si hace rato que está en la base
            if not desde:
                continue
            try:
                dias = (hoy - _dt.strptime(str(desde)[:10], "%Y-%m-%d")).days
            except Exception as _err:
                anotar_error("productos_estancados", _err)
                continue
            detalle = "nunca se vendió"
        if dias < dias_sin_vender:
            continue
        f["Última venta"] = detalle
        f["Plata parada"] = (f["Precio"] or 0) * (f["Stock"] or 0)
        f["_dias"] = dias
        salida.append(f)
    # Primero lo que más plata tiene inmovilizada
    salida.sort(key=lambda x: -(x["Plata parada"] or 0))
    return salida[:limite]


def productos_por_quebrar(dias_aviso=21, minimo_ventas=3, limite=100):
    """Qué se va a acabar antes de que alguien se dé cuenta.

    La reposición hoy es 100% manual: alguien tiene que acordarse de tocar «Pedir». Y de lo que
    uno no se acuerda es justamente de lo que se vende parejo todos los días — el filtro común
    que nadie mira hasta que un cliente lo pide y no está.

    Se calcula el ritmo real de venta de cada producto y se estima en cuántos días se termina.
    Se ignora lo que se vendió una o dos veces: con eso no se puede calcular un ritmo, solo
    ruido."""
    c.execute("""SELECT p.id AS "_id", p.codigo_raw AS "Código", m.nombre AS "Marca",
                        p.descripcion AS "Descripción", p.stock AS "Stock",
                        COUNT(v.id) AS "Vendidos",
                        julianday('now') - julianday(MIN(v.fecha)) AS "_dias_historia"
                 FROM productos p
                 JOIN marcas m ON m.id = p.marca_id
                 JOIN ventas_registradas v ON v.producto_id = p.id
                 WHERE v.fecha >= datetime('now', '-180 days')
                 GROUP BY p.id
                 HAVING COUNT(v.id) >= ?
                 ORDER BY COUNT(v.id) DESC LIMIT 400""", (minimo_ventas,))
    filas = filas_a_listas(c)

    salida = []
    for f in filas:
        dias = max(f["_dias_historia"] or 0, 7)      # con menos de una semana no hay ritmo
        por_dia = f["Vendidos"] / dias
        if por_dia <= 0:
            continue
        stock = f["Stock"] or 0
        dias_restantes = stock / por_dia
        if dias_restantes > dias_aviso:
            continue
        salida.append({
            "Código": f["Código"], "Marca": f["Marca"],
            "Descripción": (f["Descripción"] or "")[:48],
            "Stock": stock,
            "Se vende": f"{por_dia * 30:.1f} por mes",
            "Se acaba en": ("ya sin stock" if stock <= 0
                             else f"{dias_restantes:.0f} día(s)"),
            "_dias": dias_restantes, "_id": f["_id"],
        })
    salida.sort(key=lambda x: x["_dias"])
    return salida[:limite]


def solicitar_reposicion(producto_id):
    with db_lock:
        c.execute(
            "INSERT INTO pedidos_reposicion (producto_id, veces_solicitado, ultimo_solicitado_por, ultima_fecha, estado) "
            "VALUES (?, 1, ?, datetime('now'), 'pendiente') "
            "ON CONFLICT(producto_id) DO UPDATE SET veces_solicitado = veces_solicitado + 1, "
            "ultimo_solicitado_por = excluded.ultimo_solicitado_por, ultima_fecha = excluded.ultima_fecha, "
            "estado = 'pendiente'",
            (producto_id, obtener_usuario_actual())
        )
        conn.commit()


def anotar_venta_y_avisar(producto_id, termino_pedido, rotulo, donde=""):
    """Lo que corre al tocar «Se llevó». Sin el aviso el botón no mostraba nada: en el celular
    eso invita a tocar de nuevo, y cada toque es otra venta anotada que después pesa en las
    equivalencias sugeridas como si el cliente hubiera vuelto.

    El aviso va ABAJO DE LOS BOTONES, no flotando (ver mostrar_lo_anotado()). Iba con st.toast,
    y medido en un iPhone simulado: si el aviso anterior seguía en pantalla —duran 4 s— el nuevo
    no aparecía nunca; quedaba el viejo hasta vencerse. «Se llevó» y enseguida «Pedir», que es
    lo normal en el mostrador, mostraba solo el primero, y el segundo invitaba a tocar de nuevo.
    Tampoco con avisar(), que escribe arriba de todo y en el celular no se ve."""
    registrar_venta(producto_id, termino_pedido)
    st.session_state.setdefault("_lo_anotado", {})[donde] = f"🛒 Anotado: se llevó {rotulo}"


def pedir_reposicion_y_avisar(producto_id, rotulo, donde=""):
    """Lo mismo para «Pedir»: cada toque suma uno a «veces pedido»."""
    solicitar_reposicion(producto_id)
    st.session_state.setdefault("_lo_anotado", {})[donde] = f"📌 {rotulo} quedó en la lista para pedir"


def mostrar_lo_anotado(donde=""):
    """Muestra, abajo de los botones de «Se llevó» / «Pedir» de ese lugar, lo que se acaba de
    anotar ahí. Queda a la vista hasta el próximo toque, justo donde se estaba mirando."""
    texto = st.session_state.get("_lo_anotado", {}).pop(donde, None)
    if texto:
        st.success(texto)


def listar_pedidos_reposicion(estado="pendiente"):
    c.execute("""SELECT pr.id AS "ID", p.id AS "ProductoID", p.codigo_raw AS "Codigo",
                 p.descripcion AS "Descripcion", m.nombre AS "Marca", p.stock AS "Stock actual",
                 pr.veces_solicitado AS "Veces pedido", pr.ultimo_solicitado_por AS "Último en pedirlo",
                 pr.ultima_fecha AS "Fecha"
                 FROM pedidos_reposicion pr
                 JOIN productos p ON p.id = pr.producto_id
                 JOIN marcas m ON m.id = p.marca_id
                 WHERE pr.estado = ?
                 ORDER BY pr.veces_solicitado DESC, pr.ultima_fecha DESC""", (estado,))
    return filas_a_listas(c)


def marcar_pedido_resuelto(pedido_id):
    with db_lock:
        c.execute("UPDATE pedidos_reposicion SET estado = 'resuelto' WHERE id = ?", (pedido_id,))
        conn.commit()


def descartar_pedido_reposicion(pedido_id):
    with db_lock:
        c.execute("DELETE FROM pedidos_reposicion WHERE id = ?", (pedido_id,))
        conn.commit()


def alternar_favorito(producto_id, valor):
    with db_lock:
        c.execute("UPDATE productos SET favorito = ? WHERE id = ?", (1 if valor else 0, producto_id))
        conn.commit()


def listar_favoritos():
    c.execute("""SELECT p.id AS "ID", p.codigo_raw AS "Codigo", p.descripcion AS "Descripcion",
                 m.nombre AS "Marca", p.precio AS "Precio", p.stock AS "Stock"
                 FROM productos p JOIN marcas m ON m.id = p.marca_id
                 WHERE p.favorito = 1 ORDER BY p.codigo_raw""")
    return filas_a_listas(c)


# ============================================================================================
# CONFIGURACIÓN, USUARIO Y USO DE IA
# ============================================================================================
def obtener_config(clave, default=""):
    c.execute("SELECT valor FROM configuracion WHERE clave = ?", (clave,))
    fila = c.fetchone()
    return fila["valor"] if fila and fila["valor"] is not None else default


def guardar_config(clave, valor):
    with db_lock:
        c.execute(
            "INSERT INTO configuracion (clave, valor) VALUES (?, ?) "
            "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
            (clave, valor)
        )
        conn.commit()


def obtener_usuario_actual():
    """Nombre que identifica a la persona para su historial personal: si está logueada como
    admin usa ese nombre, si no usa el que puso al entrar, o 'Invitado' si no puso nada."""
    return st.session_state.get("admin_nombre") or st.session_state.get("usuario_nombre") or "Invitado"


def registrar_uso_ia(funcion, exito):
    with db_lock:
        c.execute("INSERT INTO uso_ia (funcion, usuario, exito) VALUES (?, ?, ?)",
                   (funcion, obtener_usuario_actual(), 1 if exito else 0))
        conn.commit()


def traducir_error_gemini(e):
    """Convierte el JSON crudo de error de la API de Gemini en un mensaje legible en español.
    Estas funciones tienen un límite de consultas por minuto compartido entre todos los
    empleados — chocarse con ese límite es lo más común que puede pasar."""
    texto_error = str(e)
    if "RESOURCE_EXHAUSTED" in texto_error or "429" in texto_error or "quota" in texto_error.lower():
        return (
            "⏳ Se alcanzó el límite de consultas de la IA por ahora (es un límite por minuto, "
            "compartido entre todos los que usan la app). Esperá un minuto y probá de nuevo — "
            "no es un error, es solo que hay que esperar a que se libere cupo."
        )
    return f"Error consultando a Gemini: {texto_error}"


def resumen_uso_ia(dias=30):
    c.execute("""SELECT funcion, COUNT(*) AS total, SUM(exito) AS exitosos
                 FROM uso_ia WHERE fecha >= datetime('now', ?) GROUP BY funcion ORDER BY total DESC""",
              (f"-{dias} days",))
    return [{"Función": r["funcion"], "Usos": r["total"], "Exitosos": r["exitosos"],
              "Con error": r["total"] - r["exitosos"]} for r in c.fetchall()]


# ============================================================================================
# PAPELERA (borrar con red)
# ============================================================================================
def _resumen_de_papelera(tipo, datos):
    """Una línea que describe lo borrado, para poder listar la papelera sin abrir el JSON."""
    try:
        if tipo == "marca":
            return f"{datos['marca']['nombre']} ({len(datos['productos'])} producto(s))"
        if tipo == "producto":
            return datos.get("codigo_raw", "")
        if tipo == "combo":
            return datos.get("disparador", "")
        if tipo == "alias":
            return datos.get("nombre", "")
    except (KeyError, TypeError) as _err:
        anotar_error("_resumen_de_papelera", _err)
    return ""


def mover_a_papelera(tipo, datos_dict):
    """Guarda lo borrado entero, más un resumen corto aparte.

    El resumen no es un lujo: el snapshot de una marca grande son 10,6 MB de JSON en una sola
    fila, y la pantalla de papelera lo abría ENTERO —de las cien filas— solo para leer el
    nombre de la marca y contar los productos. Con dos o tres marcas borradas eso es parsear
    decenas de megas cada vez que se abre la pantalla."""
    with db_lock:
        _guardar_en_papelera_sin_candado(tipo, datos_dict)
        conn.commit()


def _guardar_en_papelera_sin_candado(tipo, datos_dict):
    """El INSERT de mover_a_papelera(), para quien ya tiene el candado y una transacción
    abierta: db_lock no es reentrante, y guardar en la papelera y borrar tienen que pasar
    juntos o no pasar."""
    c.execute("INSERT INTO papelera (tipo, datos_json, eliminado_por, resumen) "
              "VALUES (?, ?, ?, ?)",
              (tipo, json.dumps(datos_dict, ensure_ascii=False), obtener_usuario_actual(),
               _resumen_de_papelera(tipo, datos_dict)))


def borrar_producto_con_papelera(producto_id):
    """Borra un producto dejándolo en la papelera CON sus vínculos. Devuelve cuántos guardó.

    Antes se guardaba la fila del producto sola, y la pantalla lo avisaba: «si lo restaurás, el
    producto vuelve pero SIN esos vínculos — hay que volver a vincularlo manualmente». Medido con
    un producto real de LUCAS: tenía 61 vínculos y la búsqueda traía 62 resultados; borrado y
    restaurado, volvía con 0 y la búsqueda traía 1. Una papelera que devuelve el producto sin
    lo que lo hacía útil es un borrado con otro nombre.

    Se guardan también sus pendientes: el trigger productos_sin_pendientes_colgando los borra
    con el producto, y restaurar tiene que devolverlos.

    Todo en una transacción: guardarlo en la papelera y borrarlo pasan juntos o no pasan. Antes
    eran dos pasos sueltos, y cortado en el medio quedaba en la papelera y también en la base."""
    with db_lock, transaccion():
        c.execute("SELECT * FROM productos WHERE id = ?", (producto_id,))
        fila = c.fetchone()
        if not fila:
            return None
        datos = dict(fila)
        c.execute("""SELECT * FROM equivalencias
                     WHERE producto_a_id = ? OR producto_b_id = ?""", (producto_id, producto_id))
        datos["_equivalencias"] = [dict(r) for r in c.fetchall()]
        c.execute("""SELECT * FROM equivalencias_pendientes
                     WHERE producto_a_id = ? OR producto_b_id = ?""", (producto_id, producto_id))
        datos["_pendientes"] = [dict(r) for r in c.fetchall()]
        _guardar_en_papelera_sin_candado("producto", datos)
        c.execute("DELETE FROM productos WHERE id = ?", (producto_id,))
    return len(datos["_equivalencias"])


def _reponer_vinculos(tabla, filas, cambiar_id):
    """Vuelve a meter los vínculos guardados en la papelera. Devuelve (repuestos, perdidos).

    `cambiar_id` es {id viejo: id nuevo}, para cuando el producto ya había vuelto a entrar
    con una importación y se restauran los vínculos sobre ese. Un vínculo cuyo OTRO producto
    ya no existe no se puede reponer —las claves foráneas no lo dejan, y no tendría a dónde
    apuntar—: se cuenta como perdido y se dice."""
    repuestos = perdidos = 0
    for vinc in filas:
        vinc = dict(vinc)
        vinc["producto_a_id"] = cambiar_id.get(vinc["producto_a_id"], vinc["producto_a_id"])
        vinc["producto_b_id"] = cambiar_id.get(vinc["producto_b_id"], vinc["producto_b_id"])
        a, b = vinc["producto_a_id"], vinc["producto_b_id"]
        c.execute("SELECT COUNT(*) FROM productos WHERE id IN (?, ?)", (a, b))
        if a == b or c.fetchone()[0] < 2:
            perdidos += 1
            continue
        columnas = ", ".join(vinc.keys())
        c.execute(f"INSERT OR IGNORE INTO {tabla} ({columnas}) VALUES "
                  f"({', '.join('?' * len(vinc))})", list(vinc.values()))
        repuestos += 1
    return repuestos, perdidos


def eliminar_marca_con_papelera(nombre_marca):
    """Guarda la marca completa (con todos sus productos y las equivalencias que los tocan)
    en la papelera antes de borrarla — es la operación más destructiva de la app, así que
    ahora también tiene red de seguridad."""
    c.execute("SELECT * FROM marcas WHERE nombre = ?", (nombre_marca,))
    marca_row = c.fetchone()
    if not marca_row:
        return False
    marca_id = marca_row["id"]
    c.execute("SELECT * FROM productos WHERE marca_id = ?", (marca_id,))
    productos_rows = [dict(r) for r in c.fetchall()]
    producto_ids = [p["id"] for p in productos_rows]
    equivalencias_rows = []
    if producto_ids:
        # Se pregunta por la MARCA, no por la lista de ids. Antes se armaba un IN con todos
        # los productos —dos veces, uno por cada lado del vínculo—: borrar un proveedor de
        # 43.303 productos generaba una consulta con 86.176 variables. El límite habitual de
        # SQLite es 32.766, así que en un servidor con la compilación estándar la operación
        # falla con «too many SQL variables» y no se puede borrar justamente a los proveedores
        # más grandes, que son los que uno quiere borrar cuando la importación salió mal.
        # Con el JOIN va un solo parámetro y no depende del tamaño de la marca.
        c.execute("""SELECT DISTINCT e.* FROM equivalencias e
                     JOIN productos p ON p.id IN (e.producto_a_id, e.producto_b_id)
                     WHERE p.marca_id = ?""", (marca_id,))
        equivalencias_rows = [dict(r) for r in c.fetchall()]

    # Los pendientes también: al borrar los productos, el trigger productos_sin_pendientes_colgando
    # se los lleva, y antes quedaban huérfanos en la cola —invisibles pero contados— hasta que
    # se restauraba la marca. Ahora viajan con ella.
    pendientes_rows = []
    if producto_ids:
        c.execute("""SELECT DISTINCT ep.* FROM equivalencias_pendientes ep
                     JOIN productos p ON p.id IN (ep.producto_a_id, ep.producto_b_id)
                     WHERE p.marca_id = ?""", (marca_id,))
        pendientes_rows = [dict(r) for r in c.fetchall()]

    snapshot = {"marca": dict(marca_row), "productos": productos_rows,
                "equivalencias": equivalencias_rows, "pendientes": pendientes_rows}
    # Todo o nada: la copia en la papelera y el borrado de la marca. Si se guarda la copia y
    # el borrado falla, la marca aparece duplicada al restaurarla; si se borra sin copia, no
    # hay vuelta atrás de la operación más destructiva de la app.
    # Y el candado AFUERA, con la variante que no confirma. Estaba escrito así y no andaba:
    # mover_a_papelera() hace conn.commit(), y un commit adentro de transaccion() la cierra
    # antes de tiempo. Probado cortando justo antes del DELETE: la marca seguía en la base Y
    # quedaba una copia en la papelera, que al restaurarla chocaba con la que nunca se fue.
    with db_lock, transaccion():
        _guardar_en_papelera_sin_candado("marca", snapshot)
        c.execute("DELETE FROM marcas WHERE id = ?", (marca_id,))
    return True


def listar_papelera():
    # NO se trae datos_json: son 10,6 MB por marca borrada y acá solo hace falta el resumen.
    # Las filas viejas, de antes de que existiera la columna, se resuelven abriendo el JSON de
    # a una y solo esas.
    c.execute("""SELECT id AS "ID", tipo AS "Tipo", resumen, eliminado_por AS "Eliminado por",
                 eliminado_en AS "Fecha" FROM papelera ORDER BY id DESC LIMIT 100""")
    filas = []
    for row in c.fetchall():
        detalle = row["resumen"] or ""
        if not detalle:
            c.execute("SELECT datos_json FROM papelera WHERE id = ?", (row["ID"],))
            _vieja = c.fetchone()
            if _vieja:
                try:
                    detalle = _resumen_de_papelera(row["Tipo"], json.loads(_vieja["datos_json"]))
                except (ValueError, TypeError) as _err:
                    anotar_error("listar_papelera", _err)
        filas.append({"ID": row["ID"], "Tipo": row["Tipo"], "Detalle": detalle,
                       "Eliminado por": row["Eliminado por"], "Fecha": row["Fecha"]})
    return filas


def quitar_item_lista_sesion(nombre_lista, indice):
    """Saca un ítem de una lista guardada en la sesión (presupuesto del mecánico, tanda de
    equivalencias). Va como callback para no tener que forzar un refresco de página."""
    lista = st.session_state.get(nombre_lista)
    if lista and 0 <= indice < len(lista):
        lista.pop(indice)


def borrar_papelera_definitivo(item_id):
    with db_lock:
        c.execute("DELETE FROM papelera WHERE id = ?", (item_id,))
        conn.commit()


def cb_restaurar_papelera(item_id):
    """Callback para el botón de restaurar. Guarda el resultado en session_state para poder
    mostrarlo después del refresco, ya que un callback corre antes de dibujar la pantalla."""
    ok, texto = restaurar_de_papelera(item_id)
    st.session_state["resultado_papelera"] = ("ok", texto or "Restaurado.") if ok else ("error", texto)


def vaciar_papelera_antigua(dias=30):
    """Borra en forma permanente lo que ya lleva más de `dias` en la papelera."""
    with db_lock:
        c.execute("DELETE FROM papelera WHERE eliminado_en < datetime('now', ?)", (f"-{dias} days",))
        conn.commit()


def restaurar_de_papelera(item_id):
    """Devuelve (ok, texto): el error si no se pudo, o un detalle de lo restaurado si hay."""
    detalle = None
    c.execute("SELECT tipo, datos_json FROM papelera WHERE id = ?", (item_id,))
    row = c.fetchone()
    if not row:
        return False, "No se encontró ese ítem en la papelera (puede que ya se haya restaurado)."
    tipo, datos = row["tipo"], json.loads(row["datos_json"])
    with db_lock:
        try:
            # Todo o nada. Restaurar una marca son tres altas encadenadas —la marca, sus miles
            # de productos y sus equivalencias— más el borrado del renglón de la papelera.
            # Cortado en el medio quedaba media marca restaurada y la papelera todavía llena,
            # así que el segundo intento chocaba contra lo que ya estaba. El except de abajo
            # llamaba a conn.rollback() creyendo que deshacía: en autocommit no deshace nada.
            with transaccion():
                if tipo == "combo":
                    for item in datos["items"]:
                        c.execute("INSERT INTO combos_sugeridos (disparador, item) VALUES (?, ?)",
                                  (datos["disparador"], item))
                elif tipo == "alias":
                    c.execute(
                        "INSERT INTO alias_transferencia (nombre, alias, cbu, titular) VALUES (?, ?, ?, ?)",
                        (datos["nombre"], datos["alias"], datos["cbu"], datos["titular"])
                    )
                elif tipo == "producto":
                    # Los de antes de este cambio no traen vínculos: se restauran igual.
                    _equivs = datos.pop("_equivalencias", None) or []
                    _pends = datos.pop("_pendientes", None) or []
                    # Si mientras estuvo en la papelera volvió a entrar con una importación, ya
                    # existe otro con el mismo código y la misma marca, y la base no deja dos
                    # (UNIQUE codigo_clean, marca_id). Antes eso era «No se pudo restaurar:
                    # UNIQUE constraint failed». Ahora se le devuelven los vínculos a ese.
                    c.execute("SELECT id FROM productos WHERE codigo_clean = ? AND marca_id = ?",
                              (datos.get("codigo_clean"), datos.get("marca_id")))
                    _ya_esta = c.fetchone()
                    if _ya_esta:
                        _cambiar = {datos.get("id"): _ya_esta["id"]}
                    else:
                        _cambiar = {}
                        columnas = ", ".join(datos.keys())
                        placeholders = ", ".join("?" * len(datos))
                        c.execute(f"INSERT INTO productos ({columnas}) VALUES ({placeholders})",
                                  list(datos.values()))
                    _rep, _perd = _reponer_vinculos("equivalencias", _equivs, _cambiar)
                    _reponer_vinculos("equivalencias_pendientes", _pends, _cambiar)
                    if _equivs:
                        detalle = f"Restaurado con {_rep} de sus {len(_equivs)} vínculo(s)."
                        if _perd:
                            detalle += (f" {_perd} no se pudieron reponer: el otro producto ya "
                                        "no existe.")
                    if _ya_esta:
                        detalle = ("Ese código ya había vuelto a entrar con una importación: "
                                   "se le devolvieron los vínculos a ese. " + (detalle or ""))
                elif tipo == "marca":
                    marca = datos["marca"]
                    columnas_marca = ", ".join(marca.keys())
                    placeholders_marca = ", ".join("?" * len(marca))
                    c.execute(f"INSERT INTO marcas ({columnas_marca}) VALUES ({placeholders_marca})",
                              list(marca.values()))
                    for producto in datos["productos"]:
                        columnas_p = ", ".join(producto.keys())
                        placeholders_p = ", ".join("?" * len(producto))
                        c.execute(f"INSERT INTO productos ({columnas_p}) VALUES ({placeholders_p})",
                                  list(producto.values()))
                    # Con _reponer_vinculos() y no un INSERT por fila: el otro lado de un vínculo
                    # es casi siempre un código de fábrica de OTRA marca, y si mientras tanto se
                    # lo borró —depurar huérfanos, cortar un puente, los códigos basura— la clave
                    # foránea rechazaba el INSERT y con él la restauración ENTERA: «No se pudo
                    # restaurar: FOREIGN KEY constraint failed», y la marca no volvía nunca.
                    _rep, _perd = _reponer_vinculos("equivalencias", datos["equivalencias"], {})
                    _reponer_vinculos("equivalencias_pendientes", datos.get("pendientes") or [], {})
                    detalle = (f"Restaurada con {len(datos['productos'])} producto(s) y {_rep} "
                               "vínculo(s).")
                    if _perd:
                        detalle += (f" {_perd} vínculo(s) no se pudieron reponer: el otro "
                                    "producto ya no existe.")
                else:
                    return False, f"No sé cómo restaurar el tipo '{tipo}'."
                c.execute("DELETE FROM papelera WHERE id = ?", (item_id,))
            return True, detalle
        except Exception as e:
            anotar_error("restaurar_de_papelera", e)
            return False, f"No se pudo restaurar: {e}"


# ============================================================================================
# HISTORIAL, DUPLICADOS Y EXPORTAR A EXCEL
# ============================================================================================
def guardar_busqueda(termino):
    with db_lock:
        c.execute("INSERT INTO historial_busquedas (termino, usuario) VALUES (?, ?)",
                   (termino, obtener_usuario_actual()))
        conn.commit()


def historial_reciente(limite=10):
    """Solo las búsquedas de la persona actual — antes mezclaba las de todos los empleados."""
    c.execute("""SELECT DISTINCT termino FROM historial_busquedas WHERE usuario = ?
                 ORDER BY id DESC LIMIT ?""", (obtener_usuario_actual(), limite))
    return [r["termino"] for r in c.fetchall()]


def similitud(a, b):
    """Similitud simple entre dos strings (0 a 1) usando coincidencia de secuencia."""
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()


def detectar_posibles_duplicados(marca_id, umbral=0.87, limite_productos=1500):
    """Busca códigos parecidos pero no idénticos dentro de la misma marca (posibles errores de tipeo).
    Es una comparación O(n²), así que por seguridad no corre si la marca tiene demasiados productos."""
    c.execute("SELECT id, codigo_raw, codigo_clean FROM productos WHERE marca_id = ?", (marca_id,))
    productos = c.fetchall()
    if len(productos) > limite_productos:
        return None  # catálogo muy grande: se omite para no colgar la app
    sospechosos = []
    vistos = set()
    for i in range(len(productos)):
        for j in range(i + 1, len(productos)):
            a, b = productos[i], productos[j]
            if a["codigo_clean"] == b["codigo_clean"]:
                continue
            par = tuple(sorted([a["id"], b["id"]]))
            if par in vistos:
                continue
            if similitud(a["codigo_clean"], b["codigo_clean"]) >= umbral:
                sospechosos.append({"Código 1": a["codigo_raw"], "Código 2": b["codigo_raw"]})
                vistos.add(par)
    return sospechosos


def quitar_id(filas):
    """Quita la clave ID de cada diccionario para mostrar en pantalla."""
    return [{k: v for k, v in f.items() if k != "ID"} for f in filas]


def to_excel_bytes(filas, columnas=None):
    """Genera un archivo .xlsx en memoria a partir de una lista de diccionarios."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Resultados"
    if not filas:
        wb.save(buf := io.BytesIO())
        return buf.getvalue()
    columnas = columnas or list(filas[0].keys())
    ws.append(columnas)
    for fila in filas:
        ws.append([fila.get(col, "") for col in columnas])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ============================================================================================
# COBROS: alias de transferencia y QR
# ============================================================================================
def listar_alias_transferencia():
    c.execute("""SELECT id AS "ID", nombre AS "Nombre", alias AS "Alias",
                 cbu AS "CBU", titular AS "Titular",
                 CASE WHEN qr_real_blob IS NOT NULL THEN 1 ELSE 0 END AS "TieneQrReal"
                 FROM alias_transferencia ORDER BY nombre""")
    return filas_a_listas(c)


def guardar_alias_transferencia(nombre, alias, cbu, titular, alias_id=None, qr_real_bytes=None):
    with db_lock:
        if alias_id:
            if qr_real_bytes is not None:
                c.execute(
                    "UPDATE alias_transferencia SET nombre=?, alias=?, cbu=?, titular=?, qr_real_blob=? WHERE id=?",
                    (nombre.strip(), alias.strip(), cbu.strip(), titular.strip(), qr_real_bytes, alias_id)
                )
            else:
                c.execute(
                    "UPDATE alias_transferencia SET nombre=?, alias=?, cbu=?, titular=? WHERE id=?",
                    (nombre.strip(), alias.strip(), cbu.strip(), titular.strip(), alias_id)
                )
        else:
            c.execute(
                "INSERT INTO alias_transferencia (nombre, alias, cbu, titular, qr_real_blob) VALUES (?, ?, ?, ?, ?)",
                (nombre.strip(), alias.strip(), cbu.strip(), titular.strip(), qr_real_bytes)
            )
        conn.commit()


def obtener_qr_real(alias_id):
    c.execute("SELECT qr_real_blob FROM alias_transferencia WHERE id = ?", (alias_id,))
    fila = c.fetchone()
    return fila["qr_real_blob"] if fila else None


def eliminar_qr_real(alias_id):
    with db_lock:
        c.execute("UPDATE alias_transferencia SET qr_real_blob = NULL WHERE id = ?", (alias_id,))
        conn.commit()


def eliminar_alias_transferencia(alias_id):
    c.execute("SELECT nombre, alias, cbu, titular, qr_real_blob FROM alias_transferencia WHERE id = ?", (alias_id,))
    fila = c.fetchone()
    if fila:
        mover_a_papelera("alias", {
            "nombre": fila["nombre"], "alias": fila["alias"], "cbu": fila["cbu"], "titular": fila["titular"]
        })
        # El QR real (si tenía) no se puede guardar en la papelera como texto — si restaurás este
        # alias vas a tener que volver a subirlo.
    with db_lock:
        c.execute("DELETE FROM alias_transferencia WHERE id = ?", (alias_id,))
        conn.commit()



def generar_qr_bytes(texto):
    """Genera una imagen QR (PNG) con el texto dado — el alias/CBU/titular como texto plano.
    No es un pago directo por QR (eso requiere ser comercio adherido a un sistema de cobro real):
    al escanearlo, la mayoría de las apps de billetera muestran ese texto para que el
    cliente confirme la transferencia, en vez de tener que tipear el alias a mano."""
    import qrcode
    img = qrcode.make(texto)
    salida = io.BytesIO()
    img.save(salida, format="PNG")
    return salida.getvalue()

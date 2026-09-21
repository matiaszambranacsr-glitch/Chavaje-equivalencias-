"""Le pide a Gemini que revise el cambio que estás por subir.

POR QUÉ EXISTE. El auditor, las pruebas y el barrido de pantallas cazan lo que ya nos rompió
la app alguna vez: cada control salió de un error real. Lo que no pueden cazar es lo que
todavía no se nos ocurrió mirar. Y ahí un modelo distinto gana, no porque sea mejor, sino
porque se equivoca en otros lugares.

Está probado en este repositorio: dos de los peores agujeros los encontró Gemini leyendo el
código, no las compuertas. El `pickle.loads()` de las firmas visuales —que dejaba ejecutar
código cualquiera con un blob armado a mano— y el `<` de las descripciones, que se comía medio
renglón en 1.435 productos porque el navegador lo tomaba como etiqueta HTML.

Hasta hoy ese circuito era a mano: copiar el código, pegarlo en Gemini, mandar capturas. Esto
lo hace solo, sobre el diff, y se corre como una compuerta más.

CÓMO SE USA

    export GEMINI_API_KEY="..."            # o cargala en el entorno, NUNCA en el repositorio
    python3 revisar_con_gemini.py          # lo que todavía no commiteaste
    python3 revisar_con_gemini.py --desde main        # todo lo que la rama le agrega a main
    python3 revisar_con_gemini.py --funcion evaluar_equivalencia
    python3 revisar_con_gemini.py --modelo gemini-flash-latest

LO QUE NO HACE. No decide nada. Devuelve una lista de sospechas y cada una hay que
comprobarla contra la base real antes de tocar código — igual que con las capturas. Un modelo
leyendo un diff no sabe que ILLINOIS numera las variantes con un sufijo corto ni que hay
27.201 descripciones repetidas; va a marcar cosas que están bien a propósito. Que marque de
más es aceptable: cuesta una lectura. Que no marque nada no quiere decir que esté bien.
"""
import argparse
import os
import re
import subprocess
import sys

MODELO_POR_DEFECTO = "gemini-flash-latest"   # el mismo que usa la app

# Un diff enorme no se revisa mejor, se revisa peor: el modelo reparte la atención y devuelve
# generalidades. Pasado este tamaño se avisa y se manda igual, pero conviene partir el cambio.
LARGO_QUE_CONVIENE = 120_000

# Nunca mandar afuera lo que no es código. La clave de Gemini, la de GitHub y el archivo de
# secrets no tienen por qué estar en un diff, pero si alguna vez aparecen, el error sería
# mandarlas a un servicio externo sin darse cuenta. Se corta antes de enviar.
SEÑALES_DE_SECRETO = [
    re.compile(r"(?i)\b(api[_-]?key|token|password|secret)\b\s*[:=]\s*['\"][^'\"]{12,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),        # forma de las claves de Google
    re.compile(r"gh[pousr]_[0-9A-Za-z]{20,}"),     # forma de los tokens de GitHub
    re.compile(r"(?m)^\+\+\+ b/.*secrets\.toml"),
]

# Contexto del proyecto. Sin esto el modelo señala como problemas cosas que son decisiones
# tomadas y medidas, y la revisión se vuelve ruido que se aprende a ignorar.
CONTEXTO = """Estás revisando un cambio en una aplicación Streamlit de un negocio de repuestos
de automotor, escrita en un solo archivo `app.py` de unas 28.000 líneas, en español.

Lo que ya se sabe del proyecto, para que no lo señales como problema:
- La base es SQLite en modo WAL, con UNA CONEXIÓN POR SESIÓN (hay dos personas usándola a la
  vez). Escribe en autocommit; cuando varias sentencias tienen que valer todas o ninguna se usa
  `with transaccion():`, y toda escritura va con `with db_lock:`.
- Cualquier copia de la base se hace con la API `backup()` de SQLite, nunca leyendo el `.db`.
- Todo el código, los comentarios y los mensajes están en español, a propósito.
- Los comentarios largos que explican por qué algo es así están a propósito: cuentan el error
  real que motivó esa línea. No propongas borrarlos ni acortarlos.
- Hay un paquete `nucleo/` que se GENERA desde app.py con `nucleo/generar.py`; no se edita a
  mano.
- Existe `auditar.py` con 32 controles estáticos y `python3 -m nucleo.pruebas` con 48 pruebas.
  No repitas lo que esos ya controlan (orden de definiciones, `IN (?,?)` sin `en_tandas()`,
  `pickle.loads` pelado, texto de la base dentro de `unsafe_allow_html`, leer `DB_PATH` a mano).

Lo que SÍ queremos que busques, en este orden:
1. Errores de corrección: una consulta que nombra una columna que no existe, un índice o una
   clave que puede no estar, un caso de borde que revienta (`None`, lista vacía, división por
   cero, un texto que no es un número).
2. Datos que se pierden o se corrompen en silencio: algo que se guarda a medias, un `except`
   que se traga un error importante, una escritura sin candado.
3. Seguridad: cualquier cosa que ejecute, deserialice o interpole contenido que viene de la
   base, de una planilla importada o de un archivo subido.
4. Rendimiento que se nota: una consulta adentro de un bucle sobre 70.888 productos, una
   función cara sin caché que se llama al dibujar cada pantalla.
5. Que el comentario mienta: si el comentario afirma un número o un comportamiento que el
   código no hace, eso es un problema y hay que decirlo.

NO informes: estilo, nombres, tipos, formato, "se podría refactorizar", ni sugerencias
genéricas de buenas prácticas.

Formato de la respuesta, en español y sin relleno. Para cada hallazgo:

  ### <archivo>:<línea aproximada> — <qué pasa en una línea>
  **Cómo falla:** <entradas o estado concretos -> qué sale mal>
  **Confianza:** alta / media / baja

Ordenado de más grave a menos. Si no encontrás nada que cumpla lo de arriba, respondé
exactamente: `SIN HALLAZGOS`. No inventes para llenar."""


def correr(orden):
    """Un comando de git, o cortar con un mensaje que se entienda."""
    r = subprocess.run(orden, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"Falló `{' '.join(orden)}`:\n{r.stderr.strip()}")
    return r.stdout


def el_cambio(args):
    """Qué se manda a revisar. Devuelve (texto, de dónde salió)."""
    if args.funcion:
        # Una función entera y no el diff: sirve para revisar algo que ya está commiteado hace
        # rato, que es justamente lo que el diff nunca muestra.
        import ast
        fuente = open(args.archivo, encoding="utf-8").read()
        for nodo in ast.walk(ast.parse(fuente)):
            if isinstance(nodo, ast.FunctionDef) and nodo.name == args.funcion:
                lineas = fuente.splitlines()[nodo.lineno - 1:nodo.end_lineno]
                cuerpo = "\n".join(lineas)
                return (f"# {args.archivo}, desde la línea {nodo.lineno}\n\n{cuerpo}",
                        f"la función {args.funcion}()")
        sys.exit(f"No hay ninguna función que se llame {args.funcion} en {args.archivo}.")

    if args.desde:
        base = correr(["git", "merge-base", "HEAD", args.desde]).strip()
        return correr(["git", "diff", base, "HEAD"]), f"lo que esta rama le agrega a {args.desde}"

    # Por defecto: lo que todavía no está commiteado. Si el árbol está limpio, el último commit
    # —que es el caso de «ya commiteé, revisame esto antes de pushear».
    sucio = correr(["git", "diff", "HEAD"])
    if sucio.strip():
        return sucio, "los cambios sin commitear"
    return correr(["git", "show", "HEAD"]), "el último commit"


def revisar_que_no_se_escape_nada(texto):
    for forma in SEÑALES_DE_SECRETO:
        encontrado = forma.search(texto)
        if encontrado:
            sys.exit("CORTADO: en el cambio hay algo con forma de clave o de token "
                     f"(«{encontrado.group(0)[:24]}...»). Esto se manda a un servicio externo, "
                     "así que no sale de acá. Sacalo del diff y volvé a correrlo.")


def preguntarle_a_gemini(texto, modelo, clave):
    import logging
    from google import genai
    from google.genai import types

    # La librería avisa en cada llamada que para «automatic function calling» conviene usar
    # Chat en vez de generate_content. Acá no se usan herramientas, así que el aviso no aplica
    # y solo tapa la respuesta.
    logging.getLogger("google_genai.models").setLevel(logging.ERROR)

    cliente = genai.Client(api_key=clave)
    respuesta = cliente.models.generate_content(
        model=modelo,
        contents=f"{CONTEXTO}\n\nEl cambio a revisar:\n\n```diff\n{texto}\n```",
        config=types.GenerateContentConfig(
            # 0.0 igual que en la app: queremos la misma respuesta para el mismo diff, para
            # poder volver a correrlo y comparar en vez de recibir una opinión distinta cada vez.
            temperature=0.0,
        ),
    )
    return (respuesta.text or "").strip()


def explicar_la_falla(err):
    """El error crudo de la librería es un JSON de veinte líneas donde el motivo está enterrado.

    La app ya tiene traducir_error_gemini() para lo mismo, pero vive adentro de app.py, que
    importa Streamlit y abre la base al cargarse: traerlo acá costaría más de lo que resuelve.
    Los cuatro casos de abajo son los que salen de verdad."""
    crudo = str(err)
    if "API_KEY_INVALID" in crudo or "API key not valid" in crudo:
        return ("La clave no es válida. Revisá GEMINI_API_KEY — tiene que ser la misma que "
                "está en los Secrets de Streamlit Cloud como 'gemini_api_key'.")
    if "RESOURCE_EXHAUSTED" in crudo or "429" in crudo:
        return "Te pasaste de la cuota de Gemini. Esperá un rato o revisá el plan de la clave."
    if "NOT_FOUND" in crudo and "model" in crudo.lower():
        return f"Ese modelo no existe o la clave no lo tiene habilitado. Probá con --modelo {MODELO_POR_DEFECTO}."
    if "DEADLINE" in crudo or "504" in crudo or "timeout" in crudo.lower():
        return "Tardó demasiado. Si el diff es grande, partí el cambio y probá de a una parte."
    return f"{type(err).__name__}: {crudo[:300]}"


def main():
    p = argparse.ArgumentParser(description="Le pide a Gemini que revise el cambio.")
    p.add_argument("--desde", help="rama o commit contra el que comparar (por ejemplo: main)")
    p.add_argument("--funcion", help="revisar una función entera en vez del diff")
    p.add_argument("--archivo", default="app.py", help="de dónde sacar la función (con --funcion)")
    p.add_argument("--modelo", default=MODELO_POR_DEFECTO)
    p.add_argument("--guardar", help="además de mostrarlo, escribirlo en este archivo")
    args = p.parse_args()

    clave = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not clave:
        sys.exit("Falta la clave. Cargala como variable de entorno (NO en el repositorio):\n"
                 "    export GEMINI_API_KEY=\"...\"\n"
                 "Es la misma que está en los Secrets de Streamlit Cloud como 'gemini_api_key'.")

    texto, de_donde = el_cambio(args)
    if not texto.strip():
        sys.exit("No hay nada que revisar.")
    revisar_que_no_se_escape_nada(texto)

    print(f"Revisando {de_donde} — {len(texto):,} caracteres, con {args.modelo}.")
    if len(texto) > LARGO_QUE_CONVIENE:
        print(f"  ⚠️  Son más de {LARGO_QUE_CONVIENE:,} caracteres. Va igual, pero un cambio "
              "grande se revisa peor: el modelo reparte la atención y contesta generalidades.")

    try:
        salida = preguntarle_a_gemini(texto, args.modelo, clave)
    except Exception as err:
        sys.exit(f"Gemini no contestó. {explicar_la_falla(err)}")

    print()
    print(salida or "(no contestó nada)")
    if args.guardar:
        open(args.guardar, "w", encoding="utf-8").write(salida)
        print(f"\nGuardado en {args.guardar}")

    # Código de salida 0 siempre, a propósito: esto NO es una compuerta que bloquea. Cada
    # hallazgo hay que comprobarlo contra la base real antes de tocar nada, y un modelo que
    # marca de más no puede frenar un push.
    if salida.startswith("SIN HALLAZGOS"):
        print("\n(Sin hallazgos no quiere decir que esté bien: quiere decir que este modelo, "
              "leyendo este diff, no vio nada. Las compuertas de siempre siguen valiendo.)")


if __name__ == "__main__":
    main()

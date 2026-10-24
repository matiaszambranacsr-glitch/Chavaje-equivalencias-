# Guía corta para trabajar en este repositorio

App de Streamlit (1.65, ver requirements.txt) de un negocio de repuestos: buscador de
equivalencias entre marcas, ventas, caja, depósito con mapa, devoluciones, vehículos.
Todo —pantallas, nombres, comentarios, mensajes de commit— va en castellano rioplatense (vos).

## Dónde está cada cosa

- `app.py` corre en cada toque. Su docstring tiene **el mapa**: cada archivo y sus secciones.
- `logica/*.py` se ejecutan en un solo espacio de nombres, en el orden de `orden.py`: se usan sin
  importar los nombres de las partes anteriores. Las secciones van con encabezados
  `# ====` / `# NOMBRE` / `# ====`: `grep -n "^# [A-ZÁÉÍÓÚÑ]" logica/x.py` las lista.
- `pantallas/*.py`: cada una es un bloque `if pagina == PAGINAS[n]:` (PAGINAS y las solapas
  están en `logica/interfaz.py`).
- `nucleo/` se genera con `python nucleo/generar.py` (no editar a mano lo generado).
- `README.md` tiene 8.500 renglones (675 KB): **no leerlo entero**; buscar con grep.
  `CONTRATOS.md` dice qué está garantizado y qué prueba lo controla.

## Validar antes de subir (salidas cortas)

- `python .github/correr_las_pruebas.py` → auditor + todas las `pruebas_*.py` (~1 min, una línea
  por prueba). Es lo mismo que corre GitHub.
- `python auditar.py` solo, cuando se toca código de pantallas (tiene que dar 0 / 0 / 0).
- `python pruebas_de_compatibilidad.py --base <copia de la base real> --contra origin/main`.
- Probar en el navegador: Chromium y Playwright ya están instalados (`/opt/pw-browsers/chromium`).

## Reglas que el auditor hace cumplir

- Todo `st.expander` y `st.popover` lleva `key=` (sin clave se cierran solos al cambiar el título).
- Dos «$» en un mismo texto de markdown se leen como fórmula: escapar `\\$`.
- Las claves de los widgets no se repiten entre pantallas.
- Explicaciones: `ayuda()` / `explicar()` o `help=`, no `st.caption` largos a la vista. Una sola
  «ℹ️ Cómo funciona» por pantalla (ver «LA AYUDA DE CADA PANTALLA» en `logica/interfaz.py`).
- Una sección nueva en `logica/` va también en el mapa del docstring de `app.py`.
- Números para la pantalla con `miles()` (punto de miles), nunca `f"{x:,}"`.

## Cómo se trabaja

- Comentarios que dicen el porqué con el caso real que lo motivó, como el resto del código.
- El JavaScript del navegador (click derecho, teclas, pitido, textos de Streamlit en castellano)
  está en `AYUDAS_DEL_NAVEGADOR` (texto crudo `r"""…"""`) en `logica/interfaz.py`.
- Cambios: en la rama de trabajo, commit, push, y main por avance directo; después mirar el CI.
- Nunca escribir claves (de Gemini, de administrador, `clave_copia`) en archivos ni commits, ni
  mandar datos de la base o de clientes a servicios de afuera. No tocar la rama de la copia.

## Para gastar pocos tokens

- `grep -n` antes que leer; leer con `offset`/`limit` el tramo que hace falta.
- Las salidas largas, a un archivo, y mostrar solo `tail` o lo que falló.
- No imprimir tablas de la base ni el README; no releer lo que ya se leyó.

# El relevo de los mensajes de WhatsApp

Meta **no deja preguntarle** por los mensajes de WhatsApp: los **avisa**, mandándolos a una
dirección de internet fija que tiene que contestar siempre. La app de Streamlit se duerme, así
que va este «relevo» en el medio: un Worker de Cloudflare, **gratis**, que recibe el aviso,
controla que lo mandó Meta y lo guarda hasta que la app lo pasa a buscar (cada minuto, mientras
alguien tiene la app abierta). Facebook e Instagram no lo necesitan: la app les pregunta directo.

## Armarlo (una vez, unos 15 minutos)

1. Entrá a <https://dash.cloudflare.com> (la cuenta gratis alcanza).
2. **Storage & Databases → KV → Create**: nombralo `avisos-del-chavo`.
3. **Workers & Pages → Create → Worker**: ponele un nombre (por ejemplo `relevo-chavo`), tocá
   *Deploy*, después *Edit code*, borrá lo que trae, pegá todo `worker.js` y *Deploy*.
4. En el Worker, **Settings → Bindings → Add → KV namespace**: nombre de la variable `AVISOS`,
   y elegí `avisos-del-chavo`.
5. En **Settings → Variables and Secrets**, sumá tres de tipo **Secret** (inventalas largas, de
   30 letras o más, salvo la segunda):
   - `VERIFICAR`: una palabra cualquiera que vas a poner también en Meta (paso 7).
   - `SECRETO_DE_LA_APP`: el «App secret» de tu app de Meta (*Configuración de la app →
     Básica*).
   - `CLAVE_DEL_RELEVO`: la que va a usar la app para pasar a buscar los mensajes.
6. Anotá la dirección del Worker: `https://relevo-chavo.<tu-cuenta>.workers.dev`.
7. En <https://developers.facebook.com>, en tu app → **WhatsApp → Configuración → Webhook**:
   - *URL de devolución de llamada*: la dirección del Worker con `/webhook` al final.
   - *Token de verificación*: lo mismo que pusiste en `VERIFICAR`.
   - Tocá *Verificar y guardar*, y en *Campos del webhook* suscribí **messages** (y, si usás la
     coexistencia con la aplicación del teléfono, **smb_message_echoes**).
8. En los secretos de Streamlit (*Settings → Secrets*), en la sección `[mensajes]`:

   ```toml
   relevo_url = "https://relevo-chavo.<tu-cuenta>.workers.dev"
   relevo_clave = "la misma que CLAVE_DEL_RELEVO"
   ```

9. En la app: 🗂️ Administrar → 💬 Mensajería y cobros → «📲 Conectar WhatsApp, Facebook e
   Instagram» → **🔌 Probar la conexión**.

## La respuesta fuera de horario, al instante (si querés)

Al que escribe por WhatsApp con el local cerrado, el relevo le contesta solo, en el momento
(aunque la app esté dormida), una vez cada 12 horas: «Ahora estamos cerrados, te contestamos
apenas abramos». En el chat de la app queda como «🤖 respuesta automática» y el chat sigue sin
leer, para que lo conteste una persona al abrir.

1. En la app: 🗂️ Administrar → 💬 Mensajería y cobros → «🌙 Respuesta fuera de horario»:
   prendela, poné el horario («lun-vie 8:00-18:00, sab 8:30-13:00») y el texto, y «💾 Guardar».
   Abajo te muestra las dos líneas para el relevo.
2. En Cloudflare, el Worker → **Settings → Variables and Secrets**:
   - **HORARIO** (texto común): el horario, igual que en la app.
   - **RESPUESTA** (texto común): lo que se le contesta.
   - **WHATSAPP_TOKEN** (**Secret**): el mismo permiso que `whatsapp_token` en los secretos de
     Streamlit.
3. **Deploy**. Sin alguna de las tres, el relevo no contesta nada (la app igual contesta cuando
   trae los mensajes, y Facebook e Instagram los contesta siempre la app).

Si cambiás el horario en la app, cambialo también acá.

## Lo que hay que saber

- **Las claves no van en ningún archivo**: ni en `worker.js`, ni en el repositorio, ni en un
  chat. Solo como «Secret» del Worker y en los secretos de Streamlit.
- El Worker guarda cada aviso **7 días** como mucho: si la app no lo pasa a buscar en ese
  tiempo (nadie la abrió en una semana), se pierde. Lo que la app ya guardó se borra enseguida.
- Plan gratis de Cloudflare: 1.000 escrituras por día (un mensaje que llega es una) y 1.000
  consultas de «qué hay guardado» (la app hace una por minuto mientras está abierta). Para un
  negocio de repuestos sobra; si un día no alcanza, el plan pago es de 5 dólares por mes.
- **El número de WhatsApp**: para contestar desde la app, el número del negocio tiene que estar
  en la «API de WhatsApp Cloud» de Meta. Un número que hoy usa la aplicación **WhatsApp Business**
  del teléfono, si se pasa a la API deja de andar en el teléfono, salvo con la **coexistencia**
  (los dos a la vez), que se activa por un proveedor de Meta. Antes de pasarlo, averiguá eso o
  usá un número aparte.

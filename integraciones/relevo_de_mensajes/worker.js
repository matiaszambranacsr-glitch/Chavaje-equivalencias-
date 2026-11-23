// EL RELEVO DE LOS MENSAJES DE WHATSAPP para «Equivalencias El Chavo». Ver LEEME.md acá al lado.
//
// Meta no deja preguntarle por los mensajes de WhatsApp: los AVISA, mandándolos a una dirección
// de internet fija que tiene que contestar siempre. La app de Streamlit se duerme y no tiene
// una dirección así, de modo que va este Worker de Cloudflare (gratis) en el medio:
//
//   GET  /webhook     Meta comprueba que la dirección es nuestra (hub.verify_token = VERIFICAR).
//   POST /webhook     Un aviso de Meta. Se controla que lo firmó Meta (X-Hub-Signature-256, con
//                     SECRETO_DE_LA_APP) y, si trae mensajes, se guarda 7 días en el KV AVISOS.
//                     «Entregado» y «leído» no se guardan: el plan gratis deja 1.000 escrituras
//                     por día, y cada mensaje que mandamos trae tres de esos.
//   GET  /avisos      La app pasa a buscar lo guardado (Authorization: Bearer CLAVE_DEL_RELEVO).
//   POST /confirmar   La app dice qué ya guardó en su base, y se borra de acá.
//
// Las tres claves van como variables «Secret» del Worker (nunca en este archivo), y el KV se
// enlaza con el nombre AVISOS. Sirve igual para los avisos de la página de Facebook y de
// Instagram, si algún día se suscriben a la misma dirección.
//
// LA RESPUESTA FUERA DE HORARIO (si se quiere): con HORARIO y RESPUESTA (variables, las que
// muestra la app en Administrar → 🌙 Respuesta fuera de horario) y WHATSAPP_TOKEN (Secret), al
// que escribe con el local cerrado se le contesta al instante, una vez cada 12 horas (o las
// que diga HORAS_ENTRE_RESPUESTAS, variable común, si se quiere otra cosa). Lo que se
// mandó se guarda como un aviso más (un «eco» marcado "automatica"), así la app lo muestra en el
// chat sin darlo por atendido y no contesta otra vez. Sin esas tres, no contesta nada.

const SIETE_DIAS = 7 * 24 * 60 * 60;
const TOPE_DE_UN_AVISO = 256 * 1024;

// Comparar sin cortar en la primera letra distinta: si no, cuánto tarda en contestar «no»
// dice cuántas letras de la clave se acertaron.
function iguales(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || !a || a.length !== b.length) return false;
  let distinto = 0;
  for (let i = 0; i < a.length; i++) distinto |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return distinto === 0;
}

async function firmaDe(secreto, cuerpo) {
  const clave = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secreto), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const bytes = new Uint8Array(await crypto.subtle.sign("HMAC", clave, cuerpo));
  return "sha256=" + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

function autorizado(pedido, env) {
  return Boolean(env.CLAVE_DEL_RELEVO)
    && iguales(pedido.headers.get("Authorization") || "", "Bearer " + env.CLAVE_DEL_RELEVO);
}

// Si el aviso trae algo que la app guarda: un mensaje (o el eco de uno contestado desde el
// teléfono). Lo demás —entregado, leído, cambios de la cuenta— se contesta «ok» y no se guarda.
function traeMensajes(aviso) {
  for (const entrada of (aviso && aviso.entry) || []) {
    for (const cambio of (entrada && entrada.changes) || []) {
      const valor = (cambio && cambio.value) || {};
      if ((valor.messages || []).length || (valor.message_echoes || []).length) return true;
    }
    for (const evento of (entrada && entrada.messaging) || []) {
      if (evento && evento.message) return true;
    }
  }
  return false;
}

// EL HORARIO, el mismo dibujo que la app (tramos_del_horario() en logica/mensajes.py):
// «lun-vie 8:00-18:00, sab 8:30-13:00», en hora de Argentina (UTC-3, sin cambio de hora).
const DIAS = { lun: 1, mar: 2, mie: 3, jue: 4, vie: 5, sab: 6, dom: 0 };
const UN_TRAMO = /^([a-z]{3})[a-z]*(?:\s*(?:-|\ba\b)\s*([a-z]{3})[a-z]*)?\s+(\d{1,2})(?:[:.](\d{2}))?\s*(?:-|\ba\b)\s*(\d{1,2})(?:[:.](\d{2}))?\s*(?:hs?)?$/;
// Cada cuántas horas al mismo cliente: HORAS_ENTRE_RESPUESTAS (la misma que en la app, en
// «⏱️ Los tiempos de la página»), entre 1 y 72; si no está o no se entiende, 12.
function horasEntreRespuestas(env) {
  const horas = Math.round(Number(env.HORAS_ENTRE_RESPUESTAS));
  return horas >= 1 && horas <= 72 ? horas : 12;
}

function abierto(horario, ahora) {
  const aca = new Date(ahora.getTime() - 3 * 60 * 60 * 1000);
  // Lunes primero, como en la app: domingo es el último.
  const dia = (aca.getUTCDay() + 6) % 7;
  const minuto = aca.getUTCHours() * 60 + aca.getUTCMinutes();
  let entendido = false;
  const texto = String(horario || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  for (const pedazo of texto.split(/[,;\n]/)) {
    const m = pedazo.trim().match(UN_TRAMO);
    if (!m || !(m[1] in DIAS) || (m[2] && !(m[2] in DIAS))) continue;
    const d1 = (DIAS[m[1]] + 6) % 7, d2 = (DIAS[m[2] || m[1]] + 6) % 7;
    const desde = Number(m[3]) * 60 + Number(m[4] || 0), hasta = Number(m[5]) * 60 + Number(m[6] || 0);
    if (!(desde < hasta && hasta <= 24 * 60)) continue;
    entendido = true;
    const enElDia = d1 <= d2 ? (dia >= d1 && dia <= d2) : (dia >= d1 || dia <= d2);
    if (enElDia && minuto >= desde && minuto < hasta) return true;
  }
  return entendido ? false : null;
}

// Contesta solo a los que escribieron con el local cerrado (una vez cada 12 horas cada uno) y
// guarda lo mandado como eco. Nunca rompe el aviso: si algo falla, el aviso ya está guardado.
async function contestarFueraDeHorario(aviso, env) {
  if (!env.WHATSAPP_TOKEN || !env.HORARIO || !env.RESPUESTA || aviso.object !== "whatsapp_business_account") return;
  if (abierto(env.HORARIO, new Date()) !== false) return;
  for (const entrada of aviso.entry || []) {
    for (const cambio of (entrada && entrada.changes) || []) {
      const valor = (cambio && cambio.value) || {};
      const numeroId = valor.metadata && valor.metadata.phone_number_id;
      for (const m of valor.messages || []) {
        if (!numeroId || !m || !m.from || await env.AVISOS.get("auto:" + m.from)) continue;
        await env.AVISOS.put("auto:" + m.from, "1", { expirationTtl: horasEntreRespuestas(env) * 60 * 60 });
        try {
          const r = await fetch(`https://graph.facebook.com/v26.0/${numeroId}/messages`, {
            method: "POST",
            headers: { Authorization: "Bearer " + env.WHATSAPP_TOKEN, "Content-Type": "application/json" },
            body: JSON.stringify({ messaging_product: "whatsapp", recipient_type: "individual", to: m.from,
                                   type: "text", text: { preview_url: false, body: env.RESPUESTA } }),
          });
          const datos = await r.json();
          const id = datos && datos.messages && datos.messages[0] && datos.messages[0].id;
          if (!r.ok || !id) continue;
          const eco = { object: "whatsapp_business_account", entry: [{ changes: [{ value: {
            messaging_product: "whatsapp", metadata: { phone_number_id: numeroId },
            message_echoes: [{ id, to: m.from, timestamp: String(Math.floor(Date.now() / 1000)),
                               type: "text", text: { body: env.RESPUESTA }, automatica: true }] } }] }] };
          await env.AVISOS.put(`m:${String(Date.now()).padStart(15, "0")}:${crypto.randomUUID()}`,
                               JSON.stringify(eco), { expirationTtl: SIETE_DIAS });
        } catch (_e) { /* sin respuesta automática esta vez */ }
      }
    }
  }
}

const respuesta = (texto, estado) => new Response(texto, { status: estado });
const comoJson = (datos) => new Response(JSON.stringify(datos), {
  status: 200, headers: { "Content-Type": "application/json" } });

export default {
  async fetch(pedido, env) {
    const url = new URL(pedido.url);

    if (url.pathname === "/webhook" && pedido.method === "GET") {
      const esMeta = url.searchParams.get("hub.mode") === "subscribe"
        && iguales(url.searchParams.get("hub.verify_token") || "", env.VERIFICAR || "");
      return esMeta ? respuesta(url.searchParams.get("hub.challenge") || "", 200) : respuesta("no", 403);
    }

    if (url.pathname === "/webhook" && pedido.method === "POST") {
      const cuerpo = await pedido.arrayBuffer();
      if (cuerpo.byteLength > TOPE_DE_UN_AVISO) return respuesta("muy grande", 413);
      const firma = pedido.headers.get("X-Hub-Signature-256") || "";
      if (!env.SECRETO_DE_LA_APP || !iguales(firma, await firmaDe(env.SECRETO_DE_LA_APP, cuerpo))) {
        return respuesta("firma", 401);
      }
      const texto = new TextDecoder().decode(cuerpo);
      let aviso;
      try { aviso = JSON.parse(texto); } catch (_e) { return respuesta("ok", 200); }
      if (!traeMensajes(aviso)) return respuesta("ok", 200);
      const id = `m:${String(Date.now()).padStart(15, "0")}:${crypto.randomUUID()}`;
      await env.AVISOS.put(id, texto, { expirationTtl: SIETE_DIAS });
      try { await contestarFueraDeHorario(aviso, env); } catch (_e) { /* el aviso ya está guardado */ }
      return respuesta("ok", 200);
    }

    if (url.pathname === "/avisos" && pedido.method === "GET") {
      if (!autorizado(pedido, env)) return respuesta("no", 401);
      const lista = await env.AVISOS.list({ prefix: "m:", limit: 100 });
      if (url.searchParams.get("solo_cuantos")) return comoJson({ cuantos: lista.keys.length });
      const avisos = [];
      for (const k of lista.keys) {
        const cuerpo = await env.AVISOS.get(k.name);
        if (cuerpo !== null) avisos.push({ id: k.name, cuerpo });
      }
      return comoJson({ avisos });
    }

    if (url.pathname === "/confirmar" && pedido.method === "POST") {
      if (!autorizado(pedido, env)) return respuesta("no", 401);
      let datos;
      try { datos = await pedido.json(); } catch (_e) { return respuesta("no es JSON", 400); }
      const ids = (Array.isArray(datos && datos.ids) ? datos.ids : [])
        .filter((i) => typeof i === "string" && i.startsWith("m:")).slice(0, 200);
      for (const id of ids) await env.AVISOS.delete(id);
      return comoJson({ borrados: ids.length });
    }

    return respuesta("", 404);
  },
};

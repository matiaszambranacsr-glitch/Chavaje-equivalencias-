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

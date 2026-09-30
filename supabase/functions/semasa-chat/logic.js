/* The pure half of the AI chat function (index.ts). Plain ESM so the Edge Function (Deno) and web/chat.test.mjs (Node)
   run the very same code; nothing here touches the network or a key. */

export const LIMITS = { turns: 30, chars: 8000, images: 4, imageChars: 4_200_000, textFiles: 3, fileChars: 20000 };

export const SYSTEM = [
  "Anda pembantu Wan (Ahli Kimia Berdaftar, pakar RA kosmetik dan ASEAN) untuk kerja ws.regulab dan LinkedIn beliau.",
  "Jawab dalam Bahasa Malaysia (bukan Bahasa Indonesia) melainkan diminta dalam Inggeris; istilah rasmi seperti Notifikasi",
  "Kosmetik, Garis Panduan dan Borang kekal asal.",
  "Jangan reka nombor notifikasi, klausa, tarikh, had kepekatan atau angka. Jika tidak pasti, nyatakan apa yang perlu",
  "disemak dan di mana (NPRA, ACD, EC 1223/2009, SCCS). Kapsyen tidak mengandungi ajakan bertindak atau URL ws.regulab,",
  "dan tidak menyebut Reddit atau YouTube sebagai sumber.",
].join(" ");

/** A solid red 32x32 PNG. The model is asked its colour, so "it accepted an image" and "it read one" are told apart. */
export const TEST_IMAGE =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAAKklEQVR4nGO4IydHU8QwasGoBaMWjFowasGoBaMWjFowasGoBaMWDBULAJI2YD1ZaHIvAAAAAElFTkSuQmCC";

const IMAGE_URL = /^data:image\/(png|jpe?g|webp|gif);base64,[A-Za-z0-9+/=]+$/;

export const cors = {
  "access-control-allow-origin": "*",     // the bearer token decides who may call, not the origin (no cookies are used)
  "access-control-allow-headers": "authorization, x-client-info, apikey, content-type",
  "access-control-allow-methods": "POST, OPTIONS",
};

/** OpenAI-dialect messages from the page's conversation. Notes the page shows itself never reach the model. */
export function buildMessages(history, files = [], system = SYSTEM) {
  const turns = (Array.isArray(history) ? history : [])
    .filter((m) => m && (m.role === "user" || m.role === "assistant") && typeof m.text === "string" && m.text.trim())
    .slice(-LIMITS.turns)
    .map((m) => ({ role: m.role, text: m.text.slice(0, LIMITS.chars) }));
  if (!turns.length || turns[turns.length - 1].role !== "user") throw new Error("the last message must be from the user");

  const images = [], docs = [], skipped = [];
  for (const f of Array.isArray(files) ? files : []) {
    const name = String(f?.name || "fail").slice(0, 80);
    if (typeof f?.dataUrl === "string") {
      if (images.length >= LIMITS.images) skipped.push(`${name} (terlalu banyak gambar)`);
      else if (!IMAGE_URL.test(f.dataUrl)) skipped.push(`${name} (bukan gambar PNG/JPEG/WEBP/GIF)`);
      else if (f.dataUrl.length > LIMITS.imageChars) skipped.push(`${name} (gambar terlalu besar)`);
      else images.push({ name, url: f.dataUrl });
    } else if (typeof f?.text === "string" && f.text.trim()) {
      if (docs.length >= LIMITS.textFiles) skipped.push(`${name} (terlalu banyak fail teks)`);
      else docs.push({ name, text: f.text.slice(0, LIMITS.fileChars) });
    } else {
      skipped.push(`${name}${f?.skipped ? ` (${String(f.skipped).slice(0, 60)})` : ""}`);
    }
  }

  const out = [{ role: "system", content: system }];
  turns.forEach((m, i) => {
    if (i < turns.length - 1 || m.role !== "user") { out.push({ role: m.role, content: m.text }); return; }
    let text = m.text;
    for (const d of docs) text += `\n\n[Fail: ${d.name}]\n${d.text}`;
    if (skipped.length) text += `\n\n(Lampiran ini tidak dapat dibaca dan tidak dihantar: ${skipped.join("; ")})`;
    out.push({
      role: "user",
      content: images.length
        ? [{ type: "text", text }, ...images.map((im) => ({ type: "image_url", image_url: { url: im.url } }))]
        : text,
    });
  });
  return { messages: out, sent: { images: images.length, docs: docs.length, skipped } };
}

const norm = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]/g, "");

/** What the page's "check" button shows. `models` is the ids Mireld lists (or null when the list could not be read),
    `image` is {ok, answer, error} from asking the model the colour of TEST_IMAGE. */
export function checkReport(wanted, models, image) {
  const ids = Array.isArray(models) ? models : null;
  const exact = ids ? ids.find((m) => m === wanted) : null;
  const same = ids ? ids.find((m) => norm(m) === norm(wanted)) : null;
  const related = ids ? ids.filter((m) => norm(m).includes("sonnet") || norm(m).includes("claude")).slice(0, 12) : [];
  const sawRed = !!image && typeof image.answer === "string" && /\b(red|merah)\b/i.test(image.answer);
  return {
    model: wanted,
    listed: ids ? { read: true, count: ids.length, exact: !!exact, spelled_as: same && !exact ? same : null, related } : { read: false },
    image: !image ? { tested: false }
      : image.error ? { tested: true, reads: false, error: String(image.error).slice(0, 200) }
        : { tested: true, reads: sawRed, answer: String(image.answer || "").slice(0, 80) },
  };
}

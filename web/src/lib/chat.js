/* The AI chat's one door to a model (pages/ChatTab.jsx), connected to supabase/functions/semasa-chat (Wan, 30 Sep
   2026: "for AI chat link to open AI model claude-sonnet-5.5, Base URL https://api.mireld.my/v1").

   The key is NOT in the browser: the page is public and anything under VITE_* is readable by every visitor. The call
   goes to the Edge Function, which holds MIRELD_API_KEY, accepts only a signed-in Semasa user and forwards the
   conversation. Until the function is deployed the page says so plainly (connected:false), never with a made-up reply.

   messages: [{ role: "user" | "assistant" | "note", text, at }]   (notes are the page's own and are never sent)
   returns   { text, connected } */
import { supabase } from "./SupabaseClient";

const MAX_IMAGE_BYTES = 3_000_000;
const MAX_TEXT_BYTES = 200_000;
const TEXT_EXT = /\.(txt|md|csv|json|tsv|log)$/i;

function readAs(file, how) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result || ""));
    r.onerror = () => reject(r.error);
    r[how](file);
  });
}

/** What the function can use: a picture (PNG/JPEG/WEBP/GIF) or a plain-text file. Anything else is named, not hidden. */
export async function prepareFiles(files) {
  const out = [];
  for (const f of files || []) {
    const name = f?.name || "fail";
    try {
      if (/^image\/(png|jpe?g|webp|gif)$/.test(f.type)) {
        out.push(f.size > MAX_IMAGE_BYTES ? { name, skipped: "gambar lebih 3 MB" } : { name, dataUrl: await readAs(f, "readAsDataURL") });
      } else if (f.type.startsWith("text/") || TEXT_EXT.test(name)) {
        out.push(f.size > MAX_TEXT_BYTES ? { name, skipped: "fail teks lebih 200 KB" } : { name, text: await readAs(f, "readAsText") });
      } else {
        out.push({ name, skipped: "jenis fail ini belum boleh dibaca (PDF dan Word belum)" });
      }
    } catch {
      out.push({ name, skipped: "gagal dibaca" });
    }
  }
  return out;
}

/** The answer a failed call carries: our function always answers {error}; a missing function is a plain 404. */
export async function explain(error) {
  const res = error?.context;
  if (res && typeof res.status === "number") {
    if (res.status === 404) return { missing: true };
    try { const j = await res.clone().json(); if (j?.error) return { message: String(j.error) }; } catch { /* not JSON */ }
    return { message: `HTTP ${res.status}` };
  }
  return { message: String(error?.message || error) };
}

export async function askAI(messages, { files = [] } = {}) {
  if (!supabase) return { connected: false, text: "" };
  const history = (messages || []).filter((m) => m.role === "user" || m.role === "assistant").map((m) => ({ role: m.role, text: m.text }));
  const { data, error } = await supabase.functions.invoke("semasa-chat", {
    body: { action: "chat", messages: history, files: await prepareFiles(files) },
  });
  if (error) {
    const why = await explain(error);
    if (why.missing) return { connected: false, text: "" };
    throw new Error(why.message);
  }
  if (!data?.text) throw new Error(data?.error || "Tiada jawapan / no answer");
  return { connected: true, text: data.text };
}

/** The "check" action: is the model listed, and does it read a picture. Used from the chat tab's check button. */
export async function checkAI() {
  if (!supabase) return { error: "not configured" };
  const { data, error } = await supabase.functions.invoke("semasa-chat", { body: { action: "check" } });
  if (error) {
    const why = await explain(error);
    return { error: why.missing ? "function belum dipasang / not deployed" : why.message };
  }
  return data;
}

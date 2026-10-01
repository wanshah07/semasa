/* Attachments for the AI chat, the pure part (Node tests it): the FAQ bar's readers (lib/faqAi.js prepareInputs) hand back one item per
   picture, per PDF page, per sheet; the chat wants one attachment per FILE, so the parts of a document are folded back together. */

/** items → [{ name, dataUrl } | { name, text } | { name, skipped }], documents folded by file. */
export function foldAttachments(items) {
  const out = [];
  const docs = new Map();
  for (const it of Array.isArray(items) ? items : []) {
    if (!it) continue;
    if (it.dataUrl) { out.push({ name: it.name, dataUrl: it.dataUrl }); continue; }
    if (typeof it.text === "string") {
      const m = String(it.name || "fail").match(/^(.*?) · (halaman|bahagian|helaian) (.*)$/);
      const base = m ? m[1] : String(it.name || "fail");
      const d = docs.get(base) || { name: base, parts: [] };
      d.parts.push(m ? `[${m[2]} ${m[3]}]\n${it.text}` : it.text);
      docs.set(base, d);
      continue;
    }
    out.push({ name: it.name || "fail", skipped: it.skipped || "tidak dibaca" });
  }
  for (const d of docs.values()) out.push({ name: d.name, text: d.parts.join("\n\n") });
  return out;
}

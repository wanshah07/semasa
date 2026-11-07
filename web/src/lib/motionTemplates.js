/* Motion's film templates (Wan, 7 Nov 2026: "buatkan motion boleh buat macam ni, storyboard dari gemini, picture from chatgpt or
   cloudflare"). An explainer is the film Motion has always made; a product showcase and a photo story are laid out by the worker
   (backend/semasa/motion_templates.py) from a storyboard Gemini writes first. The choice rides in the row's existing
   `options` jsonb (options.template, options.products, options.brand), so no database change is needed. Pure, tested in
   web/motionTemplates.test.mjs. */

import { motionRow } from "./motion.js";

export const TEMPLATES = [
  { id: "explainer", bm: "Penerang", en: "Explainer",
    descBm: "Hook, Fakta, Kenapa, Solusi: suara atau teks, gaya dipilih ikut kesesuaian. Seperti sebelum ini.",
    descEn: "Hook, Fact, Why, Solution: voiced or silent, styles chosen for fit. As before." },
  { id: "showcase", bm: "Pameran produk", en: "Product showcase",
    descBm: "Latar lembut dijana AI, logo dan tagline syarikat di atas, satu babak untuk setiap produk (gambar produk anda sendiri atas kad putih), penutup dengan semua produk. 9:16, kira-kira 20 saat, tanpa suara.",
    descEn: "A soft AI-generated background, the business's logo and tagline on top, one scene per product (your own product photo on a white card) and a finale with every product. 9:16, about 20 seconds, silent." },
  { id: "story", bm: "Cerita foto", en: "Photo story",
    descBm: "Lima foto AI penuh skrin dengan zum perlahan, kiraan 01 / 05 dan kapsyen, kemudian kad gelap dengan tajuk. Hanya perlu idea. 9:16, 20 saat, tanpa suara.",
    descEn: "Five full-screen AI photographs with a slow zoom, a 01 / 05 counter and a caption, then a dark card with the title. Needs only an idea. 9:16, 20 seconds, silent." },
];
export const templateOf = (v) => (TEMPLATES.some((x) => x.id === v) ? v : "explainer");
export const MAX_PRODUCTS = 5;
/* a template film has one line of words per place, so it is Malay or English (the worker reads "both" as Malay) */
export const TEMPLATE_LANGUAGES = [["bm", "Bahasa Malaysia"], ["en", "English"]];

const clip = (v, n) => String(v ?? "").replace(/\s+/g, " ").trim().slice(0, n);

/** A product as it is saved on the row: a library picture's id (the worker reads its address from the database) or a private
    upload's reference, plus the words the user typed. `thumb` is only for the form and is never sent. */
export function productOf(p) {
  const out = { name: clip(p?.name, 60), benefits: clip(p?.benefits, 120) };
  if (p?.media_id) out.media_id = String(p.media_id).slice(0, 64);
  else if (p?.ref && typeof p.ref === "object") out.ref = { path: p.ref.path, mime: p.ref.mime, size: p.ref.size, rights: p.ref.rights, role: p.ref.role || "product" };
  return out;
}

/** Why the products cannot make a showcase yet: "none" | "picture" | "many" | "" (they can). */
export function productsRefusal(products) {
  const list = Array.isArray(products) ? products : [];
  if (!list.length) return "none";
  if (list.length > MAX_PRODUCTS) return "many";
  if (list.some((p) => !p?.media_id && !p?.ref)) return "picture";
  return "";
}

/** The library pictures a product can use: finished images with an address, newest first (uploads to the library included). */
export function libraryPictures(rows, limit = 40) {
  return (rows || []).filter((r) => r && r.status === "done" && r.generated_media_url && (r.type || "image") === "image" && r.mode !== "slides")
    .slice(0, limit).map((r) => ({ id: r.id, url: r.generated_media_url, label: clip(r.prompt || r.meta?.alt || "", 60) }));
}

/** The row to insert for a template film, or {error}. An explainer goes through motionRow unchanged. A template film is silent,
    upright and Malay or English; a showcase needs 1 to 5 products, each with its own picture, and may have no brief (the
    product names stand in for it); a photo story needs only the idea or a link. */
export function templateRow(form, userId = null) {
  const template = templateOf(form?.template);
  if (template === "explainer") return motionRow(form, userId);
  const products = (form?.products || []).map(productOf);
  if (template === "showcase") {
    const why = productsRefusal(form?.products);
    if (why) return { error: `products:${why}` };
  }
  const brief = String(form?.brief || "").trim() || (template === "showcase" ? products.map((p) => p.name).filter(Boolean).join(", ") || "Product showcase" : "");
  const built = motionRow({ ...form, brief, voice: "off", resolution: "portrait", mode: "explainer", seconds: 30, aiBackground: false,
    language: form?.language === "en" ? "en" : "bm", effects: [], effectMode: "auto", assets: [] }, userId);
  if (built.error) return built;
  const options = { ...built.row.options, template };
  if (template === "showcase") options.products = products;
  if (template === "showcase") options.brand = { business_id: form?.businessId || "wsregulab", tagline: clip(form?.tagline, 60) };
  return { row: { ...built.row, options, ai_background: false } };
}

/** What a film's card says about its template, or "" for an explainer. */
export function templateLabel(row, L = 0) {
  const t = TEMPLATES.find((x) => x.id === row?.options?.template && x.id !== "explainer");
  return t ? (L ? t.en : t.bm) : "";
}

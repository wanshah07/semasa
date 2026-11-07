/* The Bank hook page (Wan, 11 Oct 2026, Phase 4: "hooks bank boleh edit, add, apply"). The built-in 25 live in the worker
   (backend/semasa/hook_bank.py FAMILIES, series order); this is the page's copy, checked word for word against that file by
   hookBank.test.mjs, so the two cannot drift. The 25 themselves are never edited in place: "Salin untuk diubah" makes a hook set
   of Wan's own (semasa_hook_styles, source "manual", supabase/067) holding a copy he edits, adds to and applies like any other. */

export const SERIES = ["curiosity", "transform", "vulnerable", "bold", "relatable"];
export const OFF_BRAND = ["vulnerable"];       // first person about a named human: never on the company account (ws.regulab)

export const BUILTIN_FAMILIES = {
  curiosity: ["Takde sapa cakap pasal ___ tapi ni sebab aku ___",
    "Aku ignore ___ berbulan2. Pastu aku try dan ___",
    "Benda pasal ___ yg takde sapa bagitau kau: ___",
    "Ni apa sebenarnya jadi bila kau ___",
    "Aku wish ada org bagitau aku ___ sebelum aku start ___"],
  transform: ["6 bulan lepas aku x boleh ___. Hari ni aku ___",
    "Aku dulu fikir ___ mustahil sampai la ___",
    "Hari aku stop buat ___, everything changed",
    "Before ___ vs After ___: ni apa yg berubah",
    "Aku dari ___ ke ___ sbb buat SATU benda ni je"],
  vulnerable: ["Aku takut nak share ___ tapi ni kenapa penting",
    "Kegagalan terbesar aku dgn ___ ajar aku ___",
    "Aku almost give up bila ___ tapi lepas tu ___",
    "Takde sapa nampak part mana aku ___",
    "Aku struggle ___ bulan dgn ___ sebelum aku figured out ___"],
  bold: ["Semua org ckp ___ tapi realitinya ___",
    "Stop buat ___ kalau kau nak ___",
    "___ dah mati. Ni apa yg actually works skrg",
    "Sebab sebenar kenapa kau masih x ___ lagi",
    "Hot take: ___ x penting mana pun compared to ___"],
  relatable: ["POV: kau ___ tapi ___",
    "Feeling tu bila kau dah ___ tapi masih ___",
    "Aku: esok la aku ___. Also aku: ___",
    "Cuba nak ___ sambil ___ be like",
    "Org lain: ___. Aku: masih figuring out ___"],
};

export const FAMILY_WORDS = {
  curiosity: ["Rasa ingin tahu", "Curiosity"], transform: ["Perubahan", "Transformation"], vulnerable: ["Pengakuan", "Vulnerable"],
  bold: ["Berani", "Bold"], relatable: ["Dekat di hati", "Relatable"], other: ["Lain-lain", "Other"],
};

/** [{n, family, text}] for all 25, numbered 1 to 25 in series order (the number the writer reports as hook_shape). */
export function builtinNumbered() {
  const out = [];
  for (const family of SERIES) for (const text of BUILTIN_FAMILIES[family]) out.push({ n: out.length + 1, family, text });
  return out;
}

/** The worker's default guidance for the 25 (hook_bank.DEFAULT_GUIDANCE), the starting instruction of a copy. */
export const DEFAULT_GUIDANCE = "Write a Malay post's hook as the shape is written; write an English post's hook as a faithful translation "
  + "that keeps the shape's structure and what each blank is for. If no shape can be filled without inventing a fact, take a RELATABLE "
  + "or CURIOSITY shape: they assert nothing and always fit.";

/** The row "Salin untuk diubah" inserts: a manual hook set holding the 25 and their default guidance. */
export function builtinCopy(name, uid) {
  return { name: String(name || "").trim().slice(0, 60) || "Bank hook saya", source: "manual", status: "ready", images: [], created_by: uid,
    instruction: DEFAULT_GUIDANCE, shapes: builtinNumbered().map(({ family, text }) => ({ family, text })),
    summary: "Salinan 25 bentuk terbina untuk diubah suai." };
}

/** A shape added from the one-line box: "family | text" or just the text; "" when it has no ___ (not a shape). */
export function quickShape(line) {
  const raw = String(line || "").trim().replace(/_{2,}/g, "___");
  const m = /^([a-z]+)\s*\|\s*(.+)$/i.exec(raw);
  const fam = m && [...SERIES, "other"].includes(m[1].toLowerCase()) ? m[1].toLowerCase() : "";
  const text = (fam ? m[2] : raw).trim();
  if (!/___/.test(text) || text.length > 160 || text.replace(/___/g, "").replace(/\W+/g, "").length < 3) return "";
  return fam && fam !== "other" ? `${fam} | ${text}` : text;
}

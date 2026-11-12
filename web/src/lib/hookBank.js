/* The Bank hook page (Wan, 11 Oct 2026, Phase 4: "hooks bank boleh edit, add, apply"). The built-in 25 live in the worker
   (backend/semasa/hook_bank.py FAMILIES, series order); this is the page's copy, checked word for word against that file by
   hookBank.test.mjs, so the two cannot drift. The 25 themselves are never edited in place: "Salin untuk diubah" makes a hook set
   of Wan's own (semasa_hook_styles, source "manual", supabase/067) holding a copy he edits, adds to and applies like any other. */

export const SERIES = ["curiosity", "transform", "vulnerable", "bold", "relatable"];
export const OFF_BRAND = ["vulnerable"];       // first person about a named human: never on the company account (ws.regulab)

export const BUILTIN_FAMILIES = {
  curiosity: ["Takde sapa cakap pasal ___ tapi ni sebab aku ___",
    "Aku ignore ___ berbulan-bulan. Lepas tu aku cuba, dan ___",
    "Soalan yang takde sapa tanya pasal ___: ___. Jawapannya, ___",
    "Ni apa sebenarnya jadi bila kau ___",
    "Aku harap ada orang bagitau aku ___ sebelum aku mula ___"],
  transform: ["Enam bulan lepas aku tak boleh ___. Hari ni aku ___",
    "Aku dulu fikir ___ mustahil, sampai lah ___",
    "Hari aku berhenti buat ___, semua berubah",
    "Dulu ___ vs sekarang ___: ni apa yang berubah",
    "Aku dari ___ ke ___ sebab buat satu benda je"],
  vulnerable: ["Aku takut nak kongsi ___ tapi ni kenapa penting",
    "Kegagalan terbesar aku dengan ___ ajar aku ___",
    "Aku hampir give up bila ___, tapi lepas tu ___",
    "Takde sapa nampak part mana aku ___",
    "Aku struggle ___ bulan dengan ___ sebelum aku jumpa jalan ___"],
  bold: ["Semua orang cakap ___, tapi realitinya ___",
    "Berhenti buat ___ kalau kau nak ___",
    "___ dah mati. Ni apa yang sebenarnya berkesan sekarang",
    "Sebab sebenar kenapa kau masih tak ___ lagi",
    "Berani aku cakap: ___ tak penting mana pun berbanding ___"],
  relatable: ["POV: kau ___ tapi ___",
    "Perasaan tu bila kau dah ___ tapi masih ___",
    "Aku: esok lah aku ___. Lepas tu aku: ___",
    "Cuba nak ___ sambil ___ memang macam ni",
    "Orang lain: ___. Aku: masih pikir ___"],
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
  + "or CURIOSITY shape: they assert nothing and always fit. "
  + "A strong hook leans on the S.T.O.P. formula (Wan, 12 Nov 2026: saved and applied): S - Shock (a bold claim or reality check that "
  + "surprises), T - Target (name the reader: founders, mak-mak, pekerja 9 to 5), O - Open loop (hold a little back so the reader wants "
  + "the rest), P - Proof (result first, then how). Fold whichever of these fit into the shape's blanks; you never need all four, and "
  + "never a fact the SOURCE does not give.";

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

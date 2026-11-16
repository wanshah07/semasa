/* Ayat al-Quran on a card: the page's half (Wan, 16 Nov 2026: "make sure can write ayat al-Quran for reminder or under
   fatwa"). Mirrors backend/semasa/quran.py; rules/quran_cases.json is run by both test suites, on answers recorded from the
   two sources, so the page and the worker fetch a verse to the same words.

   THE VERSE IS NEVER TYPED. A slide names it by surah:ayat ("2:168", or "2:168-169" for up to QURAN.max_span ayat) and
   fetchAyat() gets the Arabic (Uthmani script) and the stream's translation from a published source. Two sources:
   alquran.cloud (the Tanzil text) and quran.com. The Arabic prefers alquran.cloud; the translation asks them in the order
   its edition names; when both answered, their Arabic is compared letter for letter and a verse they disagree on is refused. */
import { QURAN, ayatEdition, ayatLabel, ayatRef } from "./compliance";

export class QuranError extends Error {}

const ARABIC_FROM = "alquran.cloud";
const CLOUD = (key, ed) => `https://api.alquran.cloud/v1/ayah/${key}/editions/${QURAN.arabic.edition},${ed.id}`;
const QURAN_COM = (key, ed) => `https://api.quran.com/api/v4/verses/by_key/${key}?translations=${ed.quran_com}&fields=text_uthmani`;

/** The letters of an Arabic text with every mark removed: the sources write the same Uthmani words with different marks,
    so anything that compares Arabic compares letters, never code points. (skeleton in quran.py) */
export const skeleton = (arabic) => [...String(arabic ?? "").normalize("NFD").replace(/ـ/g, "").replace(/ٱ/g, "ا").replace(/ء/g, "")]
  .filter((ch) => /\p{Lo}|\p{Nd}/u.test(ch)).join("");
const BISMILLAH = QURAN.bismillah.split(/\s+/).map(skeleton);

/** The ayat as the source gives it, minus a byte-order mark and the Bismillah alquran.cloud puts in front of ayat 1 of
    every surah. In Al-Fatihah the Bismillah IS ayat 1 and is kept. The four words are recognised by their letters. */
export function cleanArabic(text, surah, ayat) {
  let words = String(text ?? "").replace(/﻿/g, "").split(/\s+/).filter(Boolean);
  const n = BISMILLAH.length;
  if (ayat === 1 && surah !== 1 && words.length > n && words.slice(0, n).every((w, i) => skeleton(w) === BISMILLAH[i])) words = words.slice(n);
  return words.join(" ");
}
/** A translation as the source gives it, minus footnote markers and markup (quran.com sends <sup> footnotes). */
export const cleanTranslation = (text) => String(text ?? "").replace(/<sup[^>]*>[\s\S]*?<\/sup>|<[^>]+>/g, "").replace(/﻿/g, "").replace(/\s+/g, " ").trim();

async function getJson(url, fetchFn) {
  const r = await fetchFn(url, { headers: { Accept: "application/json" } });
  if (!r || r.status !== 200) throw new QuranError(`HTTP ${r ? r.status : "?"}`);
  return r.json();
}
const SOURCES = {
  "alquran.cloud": async (surah, ayat, ed, fetchFn) => {
    const data = (await getJson(CLOUD(`${surah}:${ayat}`, ed), fetchFn))?.data;
    const by = Object.fromEntries((Array.isArray(data) ? data : []).map((e) => [String(e?.edition?.identifier), e]));
    const ar = by[QURAN.arabic.edition], tr = by[ed.id];
    // the answer must be the ayat that was asked for: the source's own surah and ayat numbers are checked, not assumed
    for (const e of [ar, tr]) if (!e || Number(e?.surah?.number) !== surah || Number(e?.numberInSurah) !== ayat) throw new QuranError("the source answered with a different ayat");
    return [cleanArabic(ar.text, surah, ayat), cleanTranslation(tr.text)];
  },
  "quran.com": async (surah, ayat, ed, fetchFn) => {
    const v = (await getJson(QURAN_COM(`${surah}:${ayat}`, ed), fetchFn))?.verse || {};
    if (String(v.verse_key) !== `${surah}:${ayat}`) throw new QuranError("the source answered with a different ayat");
    const tr = (v.translations || []).find((t) => Number(t.resource_id) === Number(ed.quran_com));
    if (!tr) throw new QuranError("the source has no such translation");
    return [cleanArabic(v.text_uthmani, surah, ayat), cleanTranslation(tr.text)];
  },
};
/** Every ayat of a reference from ONE source, or null (with the reason added to `why`) when it cannot give them all. */
async function all(name, surah, first, last, ed, fetchFn, why) {
  const out = [];
  for (let n = first; n <= last; n++) {
    let pair;
    try { pair = await SOURCES[name](surah, n, ed, fetchFn); } catch (e) { why.push(`${name}: ${e?.message || "failed"}`); return null; }
    if (!pair[0] || !pair[1]) { why.push(`${name}: empty text for ${surah}:${n}`); return null; }
    out.push(pair);
  }
  return out;
}

/** {ayat, ayat_ar, ayat_tr, ayat_ed} for a reference: the Arabic and the stream's translation, one line per ayat.
    Throws QuranError when the reference does not exist, when no source could give every ayat of it, or when both sources
    answered and their Arabic is not letter for letter the same. (fetch in quran.py) */
export async function fetchAyat(ref, stream, fetchFn = (...a) => fetch(...a)) {
  const p = ayatRef(ref);
  if (!p) throw new QuranError(`"${ref}" is not an ayat: write surah:ayat, for example 2:168 (at most ${QURAN.max_span} ayat, e.g. 2:168-169)`);
  const [surah, first, last] = p, ed = ayatEdition(stream), why = [], got = {};
  let trSrc = "";
  for (const name of ed.sources) {
    got[name] = await all(name, surah, first, last, ed, fetchFn, why);
    if (got[name]) { trSrc = name; break; }
  }
  if (!trSrc) throw new QuranError(`could not fetch ${ayatLabel(ref)} from a published source (${why.join("; ")}). Try again.`);
  if (!(ARABIC_FROM in got)) got[ARABIC_FROM] = await all(ARABIC_FROM, surah, first, last, ed, fetchFn, why);
  const arabic = got[ARABIC_FROM] || got[trSrc];
  const both = Object.values(got).filter(Boolean);
  if (both.length === 2 && both[0].map((x) => skeleton(x[0])).join("\n") !== both[1].map((x) => skeleton(x[0])).join("\n")) {
    throw new QuranError(`the two published sources do not give the same Arabic for ${ayatLabel(ref)}. It is not used.`);
  }
  return { ayat: `${surah}:${first}` + (last !== first ? `-${last}` : ""), ayat_ar: arabic.map((x) => x[0]).join("\n"),
    ayat_tr: got[trSrc].map((x) => x[1]).join("\n"), ayat_ed: `${ed.id}@${trSrc}` };
}

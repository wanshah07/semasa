/* The glossary of technical terms (rules/glossary.json) and what follows from it (Wan, 22 Nov 2026: a technical term gets a small
   footnote on the poster, slide or card AND a "Definisi:" line at the end of the caption). The page's twin of
   backend/semasa/glossary.py: the same forms, the same whole-word match, the same reading of a footnote, so the soft check Wan sees
   before he approves and the one the worker runs are the same check. A test holds the two equal on the same cases. */
import GLOSSARY from "../../../rules/glossary.json";

export const ENTRIES = GLOSSARY.terms;
export const LABEL = { bm: "Definisi", en: "Definition" };
export const FOOT_TERMS = 2;        // terms on one slide's footnote
export const CAPTION_TERMS = 5;     // terms in one caption's Definisi paragraph
export const CUSTOM_WORDS = 16;     // a term the writer defined itself may run slightly longer; past this the pair is dropped
export const FOOT_CAP = 300;        // SLIDE_WORDS.foot in compliance.js

const DEF_HEAD = /^\s*(?:definisi|definition)s?\s*:\s*/i;
const WORDISH = "[\\p{L}\\p{N}_]";
const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const upperCount = (s) => [...s].filter((c) => c !== c.toLowerCase() && c === c.toUpperCase()).length;

/** A form as a whole word. A form with two or more capital letters (NPRA, MoS, PIF) keeps its capitals; any other matches in any case. */
export function formRe(form) {
  const pat = form.split(/\s+/).filter(Boolean).map(escRe).join("\\s+");
  return new RegExp(`(?<!${WORDISH})${pat}(?!${WORDISH})`, upperCount(form) >= 2 ? "u" : "iu");
}
const COMPILED = ENTRIES.map((e) => ({ e, forms: e.term.map((f) => [f, formRe(f)]) }));
const BY_ID = Object.fromEntries(ENTRIES.map((e) => [e.id, e]));

export const entry = (id) => BY_ID[id] || null;
export const meaningOf = (e, lang) => String(e[lang === "en" ? "en" : "bm"]).trim();
export const labelOf = (e, lang) => String((e.label || {})[lang === "en" ? "en" : "bm"] || e.term[0]);
const norm = (s) => String(s ?? "").split(/\s+/).filter(Boolean).join(" ");

/** [[entry, the form as written]] for every glossary term `text` uses, in the order each first appears. `scanOnly` skips the words so
    common that the check never asks for their footnote (`scan: false`). */
export function used(text, scanOnly = true) {
  const t = String(text ?? "");
  const found = [];
  for (const { e, forms } of COMPILED) {
    if (scanOnly && e.scan === false) continue;
    let best = null;
    for (const [, rx] of forms) {
      const m = rx.exec(t);
      if (m && (!best || m.index < best.index || (m.index === best.index && m[0].length > best.text.length))) best = { index: m.index, text: m[0] };
    }
    if (best) found.push([best.index, e, best.text]);
  }
  return found.sort((a, b) => a[0] - b[0]).map(([, e, w]) => [e, w]);
}

/** The glossary entry a footnote's term names (one of its forms or its label), else null. */
export function lookup(term) {
  const low = norm(term).toLowerCase();
  if (!low) return null;
  for (const { e, forms } of COMPILED) {
    const names = new Set([...forms.map(([f]) => f.toLowerCase()), ...Object.values(e.label || {}).map((v) => String(v).toLowerCase())]);
    if (names.has(low)) return e;
  }
  for (const { e, forms } of COMPILED) if (forms.some(([, rx]) => rx.test(String(term ?? "")))) return e;
  return null;
}

/** [[term, meaning]] of a footnote or a Definisi paragraph: the leading "Definisi:" dropped, pairs split on ";" and a pair on its first "=". */
export function pairsOf(text) {
  const body = String(text ?? "").trim().replace(DEF_HEAD, "");
  const out = [];
  for (let piece of body.split(/[;\n]+/)) {
    piece = piece.trim().replace(/\.+$/, "");
    const sep = piece.includes("=") ? "=" : piece.includes(":") ? ":" : "";
    if (!sep) continue;
    const at = piece.indexOf(sep);
    const term = norm(piece.slice(0, at)), mean = norm(piece.slice(at + 1));
    if (term && mean) out.push([term, mean]);
  }
  return out;
}

/** Ids of the glossary entries a footnote or a Definisi paragraph defines (a pair's TERM names the entry). */
export function definedIn(text) {
  const ids = new Set();
  for (const [term] of pairsOf(text)) { const e = lookup(term); if (e) ids.add(e.id); }
  return ids;
}
const paragraphs = (t) => String(t ?? "").trim().split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
export const definisiParagraphs = (caption) => paragraphs(caption).filter((p) => DEF_HEAD.test(p));
export function definedInCaption(caption) {
  const ids = new Set();
  for (const p of definisiParagraphs(caption)) for (const id of definedIn(p)) ids.add(id);
  return ids;
}
/** The caption without its Definisi paragraphs: what the check reads for the terms the caption USES. */
export const stripDefinisi = (caption) => String(caption ?? "").split(/\n\s*\n/).filter((p) => !DEF_HEAD.test(p)).join("\n\n");

/** A glossary term takes the glossary's own label and meaning verbatim; any other term is the writer's own plain explanation, kept only when short. */
export function cleanPairs(pairs, lang) {
  const out = [], seen = new Set();
  for (let [term, mean] of pairs) {
    const e = lookup(term);
    let key;
    if (e) { key = e.id; term = labelOf(e, lang); mean = meaningOf(e, lang); }
    else {
      key = term.toLowerCase();
      if (mean.split(/\s+/).length > CUSTOM_WORDS || /https?:\/\/|www\./i.test(mean)) continue;
    }
    if (seen.has(key)) continue;
    seen.add(key);
    out.push([term, mean]);
  }
  return out;
}
const head = (lang) => LABEL[lang === "en" ? "en" : "bm"];

/** The `foot` of one slide as stored: "Definisi: term = meaning; term2 = meaning." (BM) or "Definition: ..." (EN), at most `limit`
    terms and FOOT_CAP characters; a term that would not fit is dropped whole. "" when nothing usable is left. */
export function cleanFoot(raw, lang, limit = FOOT_TERMS) {
  const pairs = Array.isArray(raw) ? raw.filter((x) => x && typeof x === "object").map((x) => [String(x.term ?? ""), String(x.meaning ?? "")]) : pairsOf(String(raw ?? ""));
  const kept = cleanPairs(pairs, lang).slice(0, limit);
  while (kept.length) {
    const text = `${head(lang)}: ${kept.map(([t, m]) => `${t} = ${m.replace(/\.+$/, "")}`).join("; ")}.`;
    if ([...text].length <= FOOT_CAP) return text;
    kept.pop();
  }
  return "";
}

/** A footnote built from the glossary for the terms `text` uses (what the writer did not define itself). */
export function footFor(text, lang, limit = FOOT_TERMS) {
  const ents = used(text).map(([e]) => e).slice(0, limit);
  return cleanFoot(ents.map((e) => ({ term: labelOf(e, lang), meaning: meaningOf(e, lang) })), lang, limit);
}

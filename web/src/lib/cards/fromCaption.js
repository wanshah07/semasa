/* Slides built from a post's own caption: Studio's "Reset from caption" (argus studio/part2.html factUnits,
   splitCarousel, headAndRest, breakLong, autoSlides), brought over 27 Sep 2026.
   Wan's shape (7 Sep 2026): a cover, at least three slides carrying facts, then a closing line that leaves them curious.
   Every paragraph of the caption becomes at least one slide's worth of text: a long paragraph is packed into slide-sized
   units, never dropped (Studio lost 77 paragraphs that way before). A sentence that asks for something, or carries the
   ws.regulab website, is never built onto the artwork. */
/* The caller hands in the caption as it is on screen now (not the last saved copy) and the scanner's own isPromo
   (web/src/lib/compliance.js), so this file needs nothing else and runs under Node for the tests as it is. */

export const CAROUSEL_MAX = 8;
export const CAROUSEL_MIN_FACTS = 3;
const FACT_MAX = 150;            // a headline plus a supporting line fit in about this much
const HEAD_MAX = 110;

export function sentencesOf(p) {
  return String(p || "").split(/(?<=[.!?])\s+/).map((s) => s.trim()).filter(Boolean);
}

/* Split one point near its middle: at a clause boundary when one falls near the middle, else at a word break. */
export function breakLong(t) {
  const mid = t.length / 2;
  const lo = Math.max(30, Math.round(t.length * 0.28));
  const hi = Math.round(t.length * 0.72);
  const cand = (re, bonus) => [...t.matchAll(re)].map((m) => m.index + m[0].length)
    .filter((i) => i >= lo && i <= hi).map((i) => ({ i, score: Math.abs(i - mid) - bonus }));
  const all = [...cand(/[,;:–—]\s+/g, t.length * 0.12), ...cand(/\s+/g, 0)];
  if (!all.length) return [t, ""];
  const c = all.reduce((x, y) => (y.score < x.score ? y : x)).i;
  return [t.slice(0, c).replace(/[\s,;:–—]+$/, ""), t.slice(c).trim()];
}

/* A headline and what supports it: the first sentence, broken again and again until it fits (once was not enough:
   a 343-character sentence left a 195-character headline). */
export function headAndRest(text) {
  const s = sentencesOf(text);
  let head = s.length ? s[0] : "";
  const rest = s.slice(1).join(" ");
  if (head.length <= HEAD_MAX) return [head, rest];
  const tails = [];
  for (let i = 0; i < 6 && head.length > HEAD_MAX; i++) {
    const [h, tail] = breakLong(head);
    if (!tail || h === head) break;
    head = h; tails.unshift(tail);
  }
  return [head, [...tails, rest].filter(Boolean).join(" ")];
}

/** The caption as slide-sized facts, without the hook, hashtags, the website, the sources block or any ask.
    post = {hook, caption, stream}; isPromo(sentence) says what must never reach the artwork. */
export function factUnits(post, isPromo = () => false) {
  const hook = String(post.hook || "").trim();
  const paras = String(post.caption || "").split(/\n+/).map((x) => x.trim()).filter(Boolean)
    .filter((p) => !/^#/.test(p) && !/^www\./i.test(p) && !/^(Rujukan|Sources|Sumber)\b/i.test(p) && p !== hook)
    .filter((p) => !isPromo(p));
  const units = [];
  for (const p of paras) {
    if (p.length <= FACT_MAX) { units.push(p); continue; }
    let buf = "";
    for (const sen of sentencesOf(p)) {
      if (isPromo(sen)) continue;
      if (!buf) buf = sen;
      else if ((buf + " " + sen).length <= FACT_MAX) buf += " " + sen;
      else { units.push(buf); buf = sen; }
    }
    if (buf) units.push(buf);
  }
  return units.filter((u) => u.length > 12);
}

/** Fact slides and one closing line, and how many points the slide ceiling could not carry (said, never hidden). */
export function splitCarousel(post, isPromo = () => false) {
  const all = factUnits(post, isPromo);
  const cap = CAROUSEL_MAX - 2;
  let close = "";
  let cut = all.length;
  if (all.length > CAROUSEL_MIN_FACTS) {
    for (let i = all.length - 1; i >= CAROUSEL_MIN_FACTS; i--) {
      if (!/\?\s*$/.test(all[i]) && !isPromo(all[i])) { close = all[i]; cut = i; break; }
    }
  }
  const facts = all.slice(0, Math.min(cut, cap));
  return { facts, close, over: Math.max(0, cut - facts.length) };
}

/** A whole carousel from the caption, in Semasa's slide shape. */
export function slidesFromCaption(post, isPromo = () => false) {
  const { facts, close, over } = splitCarousel(post, isPromo);
  const linkedin = post.stream === "linkedin";
  const [ct, cl] = headAndRest(String(post.hook || "").trim() || facts[0] || "");
  const slides = [{ title: ct, points: [], ...(cl ? { lead: cl } : {}) }];
  for (const f of facts) {
    const [title, lead] = headAndRest(f);
    slides.push({ title, points: [], ...(lead ? { lead } : {}) });
  }
  if (close) {
    const [title, lead] = headAndRest(close);
    slides.push({ title, points: [], ...(lead ? { lead } : {}), eyebrow: linkedin ? "The part most miss" : "Yang ramai tak sedar" });
  }
  return { slides: slides.slice(0, CAROUSEL_MAX), over };
}

/** One card: the hook as the headline and the caption's first substantial line under it (Studio's single card). */
export function cardFromCaption(post, isPromo = () => false) {
  const hook = String(post.hook || "").trim();
  const paras = String(post.caption || "").split(/\n+/).map((x) => x.trim()).filter(Boolean);
  const lead = paras.find((p) => p !== hook && p.length > 30 && !/^#|^www\./i.test(p) && !isPromo(p)) || "";
  const [title, rest] = headAndRest(hook || lead);
  const under = hook ? lead : rest;
  return [{ title, points: [], ...(under ? { lead: under } : {}) }];
}

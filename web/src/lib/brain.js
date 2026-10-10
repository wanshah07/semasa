/* Otak AI (supabase/036_brain.sql): the page's logic. Plain functions with no imports, so web/brain.test.mjs runs them under Node.
   The worker (backend/semasa/brain.py) reads what is dropped in and files it as entries; this decides what a drop becomes,
   filters and searches what is filed, takes an edit, and writes a skill, a prompt or the whole library out as files. */

export const KINDS = ["note", "faq", "skill", "prompt", "reference", "checklist"];
export const KIND_WORDS = {
  note: ["Nota", "Note"], faq: ["FAQ", "FAQ"], skill: ["Skill", "Skill"], prompt: ["Prompt", "Prompt"],
  reference: ["Rujukan", "Reference"], checklist: ["Senarai semak", "Checklist"],
};
export const KIND_HELP = {
  note: ["Ringkasan yang patut diingat", "A summary worth remembering"],
  faq: ["Soalan dan jawapan yang berdiri sendiri", "A question and an answer that stands alone"],
  skill: ["Cara buat yang boleh diulang: bila guna, langkah demi langkah", "Repeatable know-how: when to use it, step by step"],
  prompt: ["Arahan AI yang sedia ditampal", "An AI instruction ready to paste"],
  reference: ["Fakta untuk dirujuk: had, tarikh, klausa, pautan", "Facts to look up: limits, dates, clauses, links"],
  checklist: ["Senarai untuk ditanda", "A list to tick off"],
};
export const STATUS_WORDS = {
  pending: ["Menunggu AI", "Waiting for the AI"], working: ["Sedang dibaca", "Being read"], done: ["Selesai", "Done"],
  needs_text: ["Perlu teks", "Needs the text"], error: ["Gagal", "Failed"],
};
export const SOURCE_WORDS = {
  text: ["Teks", "Text"], image: ["Gambar", "Picture"], file: ["Fail", "File"], link: ["Pautan", "Link"], scrape: ["Scrape", "Scrape"],
};
export const DEFAULT_CATEGORIES = ["regulatori", "kosmetik", "halal", "makanan", "farmaseutikal", "pemasaran", "kandungan", "teknologi", "kewangan", "operasi", "klien", "lain"];

const URL_RE = /https?:\/\/[^\s<>"')\]]+/gi;
export const LIMITS = { text: 60_000, rows: 40, note: 500 };

/** Every address in a pasted block, trailing punctuation removed, each once, in order. */
export function urlsIn(text) {
  const seen = [];
  for (const m of String(text || "").matchAll(URL_RE)) {
    const u = m[0].replace(/[.,;:!?]+$/, "");
    if (!seen.includes(u)) seen.push(u);
  }
  return seen;
}

/** The inbox rows a pasted block becomes. A line that is only an address is a link (or a scrape when `scrape` is ticked), one
    row each; everything else, with its own addresses left in, is one text row. Nothing is dropped silently: a block too long
    for the reader is cut at LIMITS.text and `cut` says so. */
export function rowsFromPaste(text, { scrape = false, hint = "", note = "" } = {}) {
  const lines = String(text || "").replace(/\r/g, "").split("\n");
  const rows = [];
  const rest = [];
  for (const line of lines) {
    const s = line.trim();
    const only = s && urlsIn(s).length === 1 && urlsIn(s)[0] === s;
    if (only) rows.push({ source_kind: scrape ? "scrape" : "link", url: s });
    else rest.push(line);
  }
  const body = rest.join("\n").trim();
  const cut = body.length > LIMITS.text;
  if (body) rows.push({ source_kind: "text", body: body.slice(0, LIMITS.text) });
  const common = { hint: KINDS.includes(hint) ? hint : "", note: String(note || "").trim().slice(0, LIMITS.note) };
  return { rows: rows.slice(0, LIMITS.rows).map((r) => ({ ...r, ...common })), cut, extra: Math.max(0, rows.length - LIMITS.rows) };
}

/** What an address is, for the word on its chip: the host without www. */
export function hostOf(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return ""; }
}
const WALLED = ["instagram.com", "facebook.com", "fb.com", "fb.watch", "threads.net", "threads.com", "tiktok.com", "linkedin.com", "x.com", "twitter.com"];
/** A host that shows its posts only to a signed-in browser: the worker reads what the preview shows and says so otherwise. */
export const isWalled = (url) => { const h = hostOf(url); return WALLED.some((w) => h === w || h.endsWith(`.${w}`)); };

/** The tiles and the by-kind counts. */
export function brainSummary(entries, inbox) {
  const byKind = Object.fromEntries(KINDS.map((k) => [k, 0]));
  const cats = {};
  for (const e of entries || []) {
    if (byKind[e.kind] != null) byKind[e.kind]++;
    cats[e.category || "lain"] = (cats[e.category || "lain"] || 0) + 1;
  }
  const inb = inbox || [];
  return {
    total: (entries || []).length, byKind, byCategory: cats,
    waiting: inb.filter((r) => r.status === "pending" || r.status === "working").length,
    needsText: inb.filter((r) => r.status === "needs_text").length,
    failed: inb.filter((r) => r.status === "error").length,
    pinned: (entries || []).filter((e) => e.pinned).length,
    lowConfidence: (entries || []).filter((e) => e.confidence != null && Number(e.confidence) < 0.6 && !e.edited).length,
  };
}

/** Categories to offer: the settings list first, then any a filed entry carries that the list no longer has. */
export function categoriesOf(entries, configured) {
  const base = (configured && configured.length ? configured : DEFAULT_CATEGORIES).map((c) => String(c).toLowerCase());
  const extra = [...new Set((entries || []).map((e) => e.category).filter(Boolean))].filter((c) => !base.includes(c));
  return [...base, ...extra];
}

const fold = (s) => String(s || "").toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "");
const haystack = (e) => fold([e.title, e.summary, e.body, e.question, e.answer, (e.tags || []).join(" "), e.category, e.source_url].join(" \n "));

/** Filter then search: kind, category, tag, pinned only, and a free-text query where every word must appear somewhere. Pinned
    first, then newest. */
export function filterEntries(entries, { kind = "", category = "", tag = "", q = "", pinned = false } = {}) {
  const words = fold(q).split(/\s+/).filter(Boolean);
  return (entries || [])
    .filter((e) => (!kind || e.kind === kind) && (!category || e.category === category) && (!tag || (e.tags || []).includes(tag)) && (!pinned || e.pinned))
    .filter((e) => { if (!words.length) return true; const h = haystack(e); return words.every((w) => h.includes(w)); })
    .slice()
    .sort((a, b) => (Number(!!b.pinned) - Number(!!a.pinned)) || String(b.created_at || "").localeCompare(String(a.created_at || "")));
}

/** The tags in use with how many entries carry each, most used first. */
export function tagCloud(entries, limit = 24) {
  const n = {};
  for (const e of entries || []) for (const t of e.tags || []) n[t] = (n[t] || 0) + 1;
  return Object.entries(n).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, limit).map(([tag, count]) => ({ tag, count }));
}

export const tagsFrom = (v) => [...new Set((Array.isArray(v) ? v : String(v || "").split(/[,;\n]+/)).map((t) => String(t).trim().toLowerCase().replace(/^#/, "").slice(0, 30)).filter(Boolean))].slice(0, 12);
export const variablesIn = (body) => [...new Set([...String(body || "").matchAll(/\{\{\s*([A-Za-z0-9_ -]{1,40}?)\s*\}\}/g)].map((m) => m[1]))];

/** What stops an edit being saved. */
export function validateEntry(e) {
  const bad = [];
  if (!String(e.title || "").trim()) bad.push("title");
  if (!KINDS.includes(e.kind)) bad.push("kind");
  if (e.kind === "faq" && (!String(e.question || "").trim() || !String(e.answer || "").trim())) bad.push("question/answer");
  else if (e.kind !== "faq" && !String(e.body || "").trim()) bad.push("body");
  return bad;
}

/** An edited entry as the database takes it: the kind's own fields rebuilt from what was typed, and `edited` set so a re-read
    never replaces it. `steps` and `items` arrive as one line each. */
export function entryRow(e) {
  const lines = (v) => (Array.isArray(v) ? v : String(v || "").split("\n")).map((x) => String(x).replace(/^\s*(?:[-*•]|\d+[.)]|\[[ x]\])\s*/i, "").trim()).filter(Boolean);
  const kind = KINDS.includes(e.kind) ? e.kind : "note";
  let data = {};
  let body = String(e.body || "").trim();
  if (kind === "skill") {
    const steps = lines(e.steps ?? e.data?.steps);
    data = { when: String(e.when ?? e.data?.when ?? "").trim(), steps };
    if (steps.length) body = steps.map((s, i) => `${i + 1}. ${s}`).join("\n");
  } else if (kind === "prompt") {
    data = { use: String(e.use ?? e.data?.use ?? "").trim(), variables: variablesIn(body) };
  } else if (kind === "checklist") {
    const items = lines(e.items ?? e.data?.items);
    data = { items };
    if (items.length) body = items.map((s) => `- [ ] ${s}`).join("\n");
  }
  const answer = kind === "faq" ? String(e.answer || "").trim() : "";
  return {
    kind, category: String(e.category || "lain").toLowerCase(), title: String(e.title || "").trim().slice(0, 120),
    summary: String(e.summary || "").trim().slice(0, 300), body: kind === "faq" ? answer : body,
    question: kind === "faq" ? String(e.question || "").trim() : "", answer, tags: tagsFrom(e.tags), data, edited: true,
  };
}

/** The text a Copy button puts on the clipboard: a prompt is its words, an FAQ is Q and A, the rest their body. */
export function copyText(e) {
  if (e.kind === "faq") return `${e.question}\n\n${e.answer || e.body}`.trim();
  return String(e.body || e.summary || "").trim();
}

const slug = (s) => fold(s).replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "entri";
const yamlStr = (s) => JSON.stringify(String(s || "").replace(/\s+/g, " ").trim());

/** One entry as Markdown with a small front matter, the form every entry is exported in. */
export function toMarkdown(e) {
  const head = ["---", `title: ${yamlStr(e.title)}`, `kind: ${e.kind}`, `category: ${e.category || "lain"}`, `tags: [${(e.tags || []).map(yamlStr).join(", ")}]`,
    ...(e.source_url ? [`source: ${yamlStr(e.source_url)}`] : []), "---", ""];
  const body = e.kind === "faq" ? `## ${e.question}\n\n${e.answer || e.body}` : e.kind === "skill"
    ? [e.data?.when ? `**Bila guna / When to use:** ${e.data.when}\n` : "", e.body].filter(Boolean).join("\n")
    : e.kind === "prompt" ? [e.data?.use ? `**Untuk / For:** ${e.data.use}\n` : "", "```", e.body, "```"].filter((x) => x !== "").join("\n") : e.body;
  return `${head.join("\n")}${e.kind === "faq" || e.kind === "skill" || e.kind === "prompt" ? "" : `# ${e.title}\n\n`}${body}\n`;
}

/** A skill as a SKILL.md another assistant can load: name is a slug, description says what it does and when to use it. */
export function toSkillMd(e) {
  const when = e.data?.when || e.summary || "";
  const desc = [e.summary, when && when !== e.summary ? `Use when: ${when}` : ""].filter(Boolean).join(" ").slice(0, 1000);
  return `---\nname: ${slug(e.title)}\ndescription: ${yamlStr(desc)}\n---\n\n# ${e.title}\n\n${e.body}\n`;
}

/** The whole library (or a filtered part) as one file per entry: [{ name, text }], the skills as <slug>/SKILL.md. */
export function exportFiles(entries) {
  const used = new Set();
  const unique = (base) => { let n = base, i = 2; while (used.has(n)) n = `${base}-${i++}`; used.add(n); return n; };
  return (entries || []).map((e) => {
    const s = unique(slug(e.title));
    return e.kind === "skill" ? { name: `skills/${s}/SKILL.md`, text: toSkillMd(e) } : { name: `${e.kind}/${s}.md`, text: toMarkdown(e) };
  });
}

/** A short line on an inbox row: what it was and how it went. */
export function inboxLabel(r) {
  if (r.source_kind === "link" || r.source_kind === "scrape") return hostOf(r.url) || r.url || "";
  if (r.source_kind === "image" || r.source_kind === "file") return r.file_name || r.title || "";
  return (r.title || r.body || "").replace(/\s+/g, " ").trim().slice(0, 80);
}

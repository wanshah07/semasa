/* Expert content (Wan, 14 Nov 2026): the page's logic. Plain functions with no imports, so web/experts.test.mjs runs them under Node.
   The page owns settings.experts (categories, handles, the platforms ticked for each, the niche, the search words, the "send to
   AI brain" switch and the dismissed names); the sweep (backend/semasa/experts.py) only reads it and owns
   settings.expert_suggestions. So nothing here ever writes a suggestion list: adding or dismissing a name is a change to the
   category, and the list is FILTERED by the category, which is why a name leaves it the moment it is added. */

export const PLATFORMS = ["threads", "facebook", "instagram"];
export const PLATFORM_NAMES = { threads: "Threads", facebook: "Facebook", instagram: "Instagram" };
export const MAX_HANDLES = 20;          // per category
export const MAX_CATEGORIES = 12;
export const MAX_KEYWORDS = 5;
export const READS_PER_SWEEP = 20;      // backend/semasa/experts.py MAX_READS: profile pages opened in one sweep

export const DEFAULT_EXPERTS = {
  enabled: true, hours: 336, per_handle: 5,
  categories: [
    { id: "ai", name: "AI Expert", brain: true, handles: [], dismissed: [],
      niche: "artificial intelligence in practice: AI tools, large language models, agents, prompting, automation",
      keywords: ["AI agent", "prompt engineering", "LLM"] },
    { id: "halal", name: "Halal Expert", brain: false, handles: [], dismissed: [],
      niche: "halal certification and compliance in Malaysia: JAKIM, MPPHM, MS 1500, halal assurance, ingredients",
      keywords: ["sijil halal", "halal JAKIM", "pensijilan halal"] },
  ],
};

const HANDLE = /^[\w.-]{1,60}$/;
const low = (v) => String(v || "").toLowerCase();

/** A handle from what a person types or pastes: "@name", "name", or a profile address on any of the three platforms. */
export function cleanHandle(v) {
  let h = String(v || "").trim();
  const url = /^(?:https?:\/\/)?(?:www\.|m\.|web\.)?(?:threads\.(?:net|com)|instagram\.com|facebook\.com|fb\.com)\/([^?#]+)/i.exec(h);
  if (url) h = url[1].split("/").filter(Boolean)[0] || "";
  h = h.replace(/^@+/, "").replace(/\/+$/, "").trim();
  return HANDLE.test(h) ? h : "";
}

const platformsOf = (v) => PLATFORMS.filter((p) => (Array.isArray(v) ? v : []).includes(p));

/** The settings row as the page reads it: every category whole, every handle clean, nothing undefined. */
export function configOf(setting) {
  const s = setting && typeof setting === "object" ? setting : {};
  const cats = Array.isArray(s.categories) ? s.categories : DEFAULT_EXPERTS.categories;
  const seenCat = new Set();
  const categories = [];
  for (const c of cats) {
    const id = String((c && c.id) || "").trim().slice(0, 40);
    if (!id || seenCat.has(id)) continue;
    seenCat.add(id);
    const seen = new Set();
    const handles = [];
    for (const h of Array.isArray(c.handles) ? c.handles : []) {
      const handle = cleanHandle(h && typeof h === "object" ? h.handle : h);
      const platforms = platformsOf(h && typeof h === "object" ? h.platforms : ["threads"]);
      if (!handle || !platforms.length || seen.has(low(handle))) continue;
      seen.add(low(handle));
      handles.push({ handle, platforms });
    }
    categories.push({
      id, name: String(c.name || id).slice(0, 60), brain: Boolean(c.brain), niche: String(c.niche || "").slice(0, 300), handles,
      keywords: (Array.isArray(c.keywords) ? c.keywords : []).map((k) => String(k).trim().slice(0, 60)).filter(Boolean).slice(0, MAX_KEYWORDS),
      dismissed: [...new Set((Array.isArray(c.dismissed) ? c.dismissed : []).map((d) => low(cleanHandle(d))).filter(Boolean))].slice(-200),
    });
  }
  return { enabled: s.enabled !== false, hours: Number(s.hours) || DEFAULT_EXPERTS.hours, per_handle: Number(s.per_handle) || DEFAULT_EXPERTS.per_handle, categories };
}

const mapCat = (cfg, id, fn) => ({ ...cfg, categories: cfg.categories.map((c) => (c.id === id ? fn(c) : c)) });

/** An id for a new category from its name ("Pakar Kosmetik" → "pakar-kosmetik"), never one already taken. */
export function slugOf(name, taken = []) {
  const base = low(name).normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 32) || "kategori";
  let id = base;
  for (let n = 2; taken.includes(id); n++) id = `${base}-${n}`;
  return id;
}

/** { cfg } with the new category last, or { error } in words. */
export function addCategory(cfg, name) {
  const clean = String(name || "").trim().slice(0, 60);
  if (!clean) return { error: "name" };
  if (cfg.categories.some((c) => low(c.name) === low(clean))) return { error: "exists" };
  if (cfg.categories.length >= MAX_CATEGORIES) return { error: "full" };
  const id = slugOf(clean, cfg.categories.map((c) => c.id));
  return { id, cfg: { ...cfg, categories: [...cfg.categories, { id, name: clean, brain: false, niche: "", handles: [], keywords: [], dismissed: [] }] } };
}

export const removeCategory = (cfg, id) => ({ ...cfg, categories: cfg.categories.filter((c) => c.id !== id) });

/** Rename, or change the niche, the search words or the brain switch. Unknown keys are ignored. */
export function patchCategory(cfg, id, patch) {
  return mapCat(cfg, id, (c) => ({
    ...c,
    ...(patch.name !== undefined && String(patch.name).trim() ? { name: String(patch.name).trim().slice(0, 60) } : {}),
    ...(patch.niche !== undefined ? { niche: String(patch.niche).trim().slice(0, 300) } : {}),
    ...(patch.brain !== undefined ? { brain: Boolean(patch.brain) } : {}),
    ...(patch.keywords !== undefined ? { keywords: keywordsFrom(patch.keywords) } : {}),
  }));
}

/** Search words from a typed line: commas or new lines between them, each once, at most five. */
export function keywordsFrom(v) {
  const parts = Array.isArray(v) ? v : String(v || "").split(/[,\n]/);
  const out = [];
  for (const p of parts) {
    const k = String(p).trim().slice(0, 60);
    if (k && !out.some((x) => low(x) === low(k))) out.push(k);
  }
  return out.slice(0, MAX_KEYWORDS);
}

/** Register a handle on the platforms ticked. A name already there gains the new platforms (one row a name). Adding a name
    also takes it off the dismissed list. { cfg } or { error: "handle" | "platform" | "full" }. */
export function addHandle(cfg, catId, raw, platforms) {
  const handle = cleanHandle(raw);
  const plats = platformsOf(platforms);
  if (!handle) return { error: "handle" };
  if (!plats.length) return { error: "platform" };
  const cat = cfg.categories.find((c) => c.id === catId);
  if (!cat) return { error: "category" };
  const has = cat.handles.some((h) => low(h.handle) === low(handle));
  if (!has && cat.handles.length >= MAX_HANDLES) return { error: "full" };
  return {
    handle, merged: has,
    cfg: mapCat(cfg, catId, (c) => ({
      ...c,
      handles: has
        ? c.handles.map((h) => (low(h.handle) === low(handle) ? { ...h, platforms: PLATFORMS.filter((p) => h.platforms.includes(p) || plats.includes(p)) } : h))
        : [...c.handles, { handle, platforms: plats }],
      dismissed: c.dismissed.filter((d) => d !== low(handle)),
    })),
  };
}

export const removeHandle = (cfg, catId, handle) =>
  mapCat(cfg, catId, (c) => ({ ...c, handles: c.handles.filter((h) => low(h.handle) !== low(handle)) }));

/** Tick or untick one platform of a handle. The last platform cannot be unticked: remove the handle instead. */
export function togglePlatform(cfg, catId, handle, platform) {
  if (!PLATFORMS.includes(platform)) return cfg;
  return mapCat(cfg, catId, (c) => ({
    ...c,
    handles: c.handles.map((h) => {
      if (low(h.handle) !== low(handle)) return h;
      const on = h.platforms.includes(platform);
      if (on && h.platforms.length === 1) return h;
      return { ...h, platforms: PLATFORMS.filter((p) => (p === platform ? !on : h.platforms.includes(p))) };
    }),
  }));
}

export const dismissSuggestion = (cfg, catId, handle) =>
  mapCat(cfg, catId, (c) => ({ ...c, dismissed: [...new Set([...c.dismissed, low(cleanHandle(handle))].filter(Boolean))] }));

/** The accounts worth following for one category: the sweep's list without anyone registered or dismissed since. */
export function suggestionsFor(suggestions, cfg, catId) {
  const cat = cfg.categories.find((c) => c.id === catId);
  const list = suggestions && suggestions.lists && Array.isArray(suggestions.lists[catId]) ? suggestions.lists[catId] : [];
  if (!cat) return [];
  const skip = new Set([...cat.handles.map((h) => low(h.handle)), ...cat.dismissed]);
  const seen = new Set();
  return list.filter((s) => {
    const h = low(cleanHandle(s && s.handle));
    if (!h || skip.has(h) || seen.has(h)) return false;
    seen.add(h);
    return true;
  });
}

/** One category's feed rows, newest first. Hidden markers (off the niche) are left out unless asked for. */
export function rowsFor(rows, catId, { hidden = false, q = "", handle = "" } = {}) {
  const needle = low(q).trim();
  return (rows || [])
    .filter((r) => r.section === "expert" && r.raw && r.raw.category === catId && r.relevant !== false && (hidden || !r.dismissed)
      && (!handle || low(r.raw.handle) === low(handle))
      && (!needle || [r.title, r.summary, r.why, r.raw.original, r.raw.handle].some((v) => low(v).includes(needle))))
    .sort((a, b) => String(b.published_at || b.created_at || "").localeCompare(String(a.published_at || a.created_at || "")));
}

/** How many profile pages one sweep opens for this setting, against what it can open: over the limit, the rest take turns. */
export function readLoad(cfg) {
  const reads = cfg.categories.reduce((n, c) => n + c.handles.reduce((m, h) => m + h.platforms.length, 0), 0);
  return { reads, limit: READS_PER_SWEEP, over: reads > READS_PER_SWEEP };
}

/** The AI brain's inbox row for one feed row the person sends by hand (the sweep files its own for a category with the switch
    on): the expert's own words first, then the summary, as a reference. */
export function brainRow(r) {
  const raw = r.raw || {};
  const body = `Expert: @${raw.handle || ""} on ${PLATFORM_NAMES[raw.platform] || raw.platform || ""} (${raw.category_name || raw.category || ""})\n\n`
    + `Original post:\n${String(raw.original || "").slice(0, 2000)}\n\nSummary: ${r.summary || ""}${r.why ? `\nTakeaway: ${r.why}` : ""}`;
  return { source_kind: "text", title: String(r.title || "").slice(0, 200), url: r.url || "", body, hint: "reference",
    note: `Expert content (${raw.category_name || raw.category || ""}): a reference only, the view of one expert, not a verified fact.` };
}

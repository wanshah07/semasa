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
/* One sweep is budgeted in PAGE LOADS (backend/semasa/experts.py LOAD_COST, MAX_LOADS): an Instagram profile is its grid and
   six post pages, a Threads or Facebook profile is one page. */
export const LOAD_COST = { threads: 1, facebook: 1, instagram: 7 };
export const LOADS_PER_SWEEP = 60;
export const SEARCH_AGAIN_MS = 60 * 60 * 1000;      // "Search again" for accounts worth following: once an hour at most

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

/** The usernames that differ from the owner's main name, only for platforms the owner is ticked on (Wan, 15 Nov 2026: one owner,
    a different username on each platform). A name equal to the main one, or not a valid username, is not kept. */
export function namesOf(handle, platforms, raw) {
  const out = {};
  for (const p of platforms) {
    const v = cleanHandle(raw && raw[p]);
    if (v && low(v) !== low(handle)) out[p] = v;
  }
  return out;
}

/** The username an owner has on one platform. */
export const accountOf = (h, platform) => (h.names && h.names[platform]) || h.handle;

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
      const names = namesOf(handle, platforms, h && typeof h === "object" ? h.names : null);
      handles.push({ handle, platforms, ...(Object.keys(names).length ? { names } : {}) });
    }
    categories.push({
      id, name: String(c.name || id).slice(0, 60), brain: Boolean(c.brain), niche: String(c.niche || "").slice(0, 300), handles,
      keywords: (Array.isArray(c.keywords) ? c.keywords : []).map((k) => String(k).trim().slice(0, 60)).filter(Boolean).slice(0, MAX_KEYWORDS),
      dismissed: [...new Set((Array.isArray(c.dismissed) ? c.dismissed : []).map((d) => low(cleanHandle(d))).filter(Boolean))].slice(-200),
    });
  }
  const asked = typeof s.discover_request === "string" && Number.isFinite(Date.parse(s.discover_request)) ? s.discover_request : null;
  return { enabled: s.enabled !== false, hours: Number(s.hours) || DEFAULT_EXPERTS.hours, per_handle: Number(s.per_handle) || DEFAULT_EXPERTS.per_handle,
    ...(asked ? { discover_request: asked } : {}), categories };
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
export function addHandle(cfg, catId, raw, platforms, names = {}) {
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
        ? c.handles.map((h) => {
          if (low(h.handle) !== low(handle)) return h;
          const all = PLATFORMS.filter((p) => h.platforms.includes(p) || plats.includes(p));
          const merged = namesOf(h.handle, all, { ...(h.names || {}), ...names });
          return { handle: h.handle, platforms: all, ...(Object.keys(merged).length ? { names: merged } : {}) };
        })
        : [...c.handles, { handle, platforms: plats, ...(Object.keys(namesOf(handle, plats, names)).length ? { names: namesOf(handle, plats, names) } : {}) }],
      dismissed: c.dismissed.filter((d) => d !== low(handle)),
    })),
  };
}

export const removeHandle = (cfg, catId, handle) =>
  mapCat(cfg, catId, (c) => ({ ...c, handles: c.handles.filter((h) => low(h.handle) !== low(handle)) }));

/** Set the usernames an owner has on the platforms in `map` ({ instagram: "dr.aiman", threads: "" }) in ONE change; an empty one
    (or the main name) means "same as the main name". */
export function setAccountNames(cfg, catId, handle, map) {
  return mapCat(cfg, catId, (c) => ({
    ...c,
    handles: c.handles.map((h) => {
      if (low(h.handle) !== low(handle)) return h;
      const names = namesOf(h.handle, h.platforms, { ...(h.names || {}), ...(map || {}) });
      const { names: _old, ...rest } = h;
      return Object.keys(names).length ? { ...rest, names } : rest;
    }),
  }));
}

/** Tick or untick one platform of a handle. The last platform cannot be unticked: remove the handle instead. */
export function togglePlatform(cfg, catId, handle, platform) {
  if (!PLATFORMS.includes(platform)) return cfg;
  return mapCat(cfg, catId, (c) => ({
    ...c,
    handles: c.handles.map((h) => {
      if (low(h.handle) !== low(handle)) return h;
      const on = h.platforms.includes(platform);
      if (on && h.platforms.length === 1) return h;
      const platforms = PLATFORMS.filter((p) => (p === platform ? !on : h.platforms.includes(p)));
      const names = namesOf(h.handle, platforms, h.names);       // a platform that is unticked takes its own username with it
      const { names: _old, ...rest } = h;
      return { ...rest, platforms, ...(Object.keys(names).length ? { names } : {}) };
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
  const skip = new Set([...cat.handles.flatMap((h) => [low(h.handle), ...Object.values(h.names || {}).map(low)]), ...cat.dismissed]);
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
      && (!handle || low(r.raw.owner || r.raw.handle) === low(handle))
      && (!needle || [r.title, r.summary, r.why, r.raw.original, r.raw.handle, r.raw.owner].some((v) => low(v).includes(needle))))
    .sort((a, b) => String(b.published_at || b.created_at || "").localeCompare(String(a.published_at || a.created_at || "")));
}

/** How many pages one sweep would load for this setting, against what it loads: over the limit, the accounts take turns. An
    account listed twice on one platform is read once, as the sweep does. */
export function readLoad(cfg) {
  const seen = new Set();
  let loads = 0;
  for (const c of cfg.categories) {
    for (const h of c.handles) {
      for (const p of h.platforms) {
        const key = `${p}|${low(accountOf(h, p))}`;
        if (seen.has(key)) continue;
        seen.add(key);
        loads += LOAD_COST[p] || 1;
      }
    }
  }
  return { loads, accounts: seen.size, limit: LOADS_PER_SWEEP, over: loads > LOADS_PER_SWEEP };
}

/** The parts of an original post: one for a single post, several for a chain the sweep joined ("— 2/4 —" between them). */
export function chainParts(original) {
  return String(original || "").split(/\n\n— \d+\/\d+ —\n\n/).map((x) => x.trim()).filter(Boolean);
}

/** Per owner in one category, from the feed rows: posts shown, posts Wan hid, and posts the bot judged off the niche. So "0
    posts" can be told from "everything judged off the niche". Keys are the owner's main name in lower case. */
export function ownerStats(rows, catId) {
  const out = {};
  for (const r of rows || []) {
    if (r.section !== "expert" || !r.raw || r.raw.category !== catId) continue;
    const k = low(r.raw.owner || r.raw.handle);
    if (!k) continue;
    const s = (out[k] ||= { shown: 0, hidden: 0, off: 0 });
    if (r.relevant === false) s.off++;
    else if (r.dismissed) s.hidden++;
    else s.shown++;
  }
  return out;
}

/** Ask the sweep to search for accounts worth following again: the time of the request goes in the setting, and the sweep
    searches when it is newer than its last search (it never has to clear it, so only the page writes this row). */
export const requestDiscovery = (cfg, nowIso) => ({ ...cfg, discover_request: nowIso });

/** May "Search again" be pressed: not within an hour of the last press or of the last search. { ok, waitMin }. */
export function canSearchAgain(cfg, suggestions, nowMs = Date.now()) {
  const last = Math.max(Date.parse(cfg && cfg.discover_request) || 0, Date.parse(suggestions && suggestions.at) || 0);
  const left = last + SEARCH_AGAIN_MS - nowMs;
  return { ok: left <= 0, waitMin: left > 0 ? Math.ceil(left / 60000) : 0, pending: Boolean(cfg && cfg.discover_request)
    && (Date.parse(cfg.discover_request) || 0) > (Date.parse(suggestions && suggestions.at) || 0) };
}

/** The feed rows of one category that could still go to the AI brain by hand: shown, and not marked as filed. */
export const notInBrain = (rows, catId, sent = new Set()) => rowsFor(rows, catId).filter((r) => !(r.raw && r.raw.brain) && !sent.has(r.id));

/** The AI brain's inbox row for one feed row the person sends by hand (the sweep files its own for a category with the switch
    on): the expert's own words first, then the summary, as a reference. */
export function brainRow(r) {
  const raw = r.raw || {};
  const chain = raw.parts ? ` (a chain of ${raw.parts} posts)` : "";
  const body = `Expert: @${raw.handle || ""} on ${PLATFORM_NAMES[raw.platform] || raw.platform || ""} (${raw.category_name || raw.category || ""})\n\n`
    + `Original post${chain}:\n${String(raw.original || "").slice(0, 8000)}\n\nSummary: ${r.summary || ""}${r.why ? `\nTakeaway: ${r.why}` : ""}`;
  return { source_kind: "text", title: String(r.title || "").slice(0, 200), url: r.url || "", body, hint: "reference",
    note: `Expert content (${raw.category_name || raw.category || ""}): a reference only, the view of one expert, not a verified fact.` };
}

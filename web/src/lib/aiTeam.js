/* The AI team in the page (Wan, 23 Oct 2026): every gateway is one Wanshah robot, each with a state and the jobs it does.
   Rows are semasa_api_status (the probe) and semasa_api_usage (every AI call); the router's own decision is
   settings.ai_team_state (backend/semasa/ai_team.py), and settings.ai_team holds Wan's pins. Pure functions, tested in
   aiTeam.test.mjs. The ROBOTS table here mirrors the backend's: one slug, one robot, in both. */

export const ROBOTS = {
  rootsys: { robot: "W1", name: "Wanshah 1", tone: "afiq", does: ["read", "write"] },
  // Mireld lists gpt-image models too (9 Nov 2026: "add wanshah2, mireld" to the picture maker); whether it really draws is what Test shows
  mireld: { robot: "W2", name: "Wanshah 2", tone: "mireld", does: ["read", "write", "make_image"] },
  kiosapi: { robot: "W3", name: "Wanshah 3", tone: "kios", does: ["read", "write", "read_image", "make_image"] },
  // Gemini (Wan, 6 Nov 2026): several keys picked automatically; it shows only once a key has been probed (not in ORDER)
  gemini: { robot: "W4", name: "Wanshah 4", tone: "guest", does: ["read", "write", "read_image", "make_image"] },
  // ChatGPT (Wan, 7 Nov 2026): Wan's own ChatGPT login, shown once the API check has asked it
  chatgpt: { robot: "W5", name: "Wanshah 5", tone: "guest", does: ["read", "write", "read_image", "make_image"] },
};
// shown in this order, like halal-executive: Wanshah 1, then 3, then 2
export const ORDER = ["rootsys", "kiosapi", "mireld"];
export const FIRST_PROVIDER_ROBOT = 6;   // the first provider Wan adds on the API tab is Wanshah 6 (backend ai_providers.FIRST_ROBOT)

/** ROBOTS plus the providers Wan added (semasa_ai_providers rows, supabase/074) as W6, W7, ... in creation order, each keyed by
    its id. The backend numbers them the same way (every row, on or off, so a switched-off provider keeps its number). */
export function robotsWith(providers) {
  const out = { ...ROBOTS };
  const rows = [...(providers || [])].filter((p) => p && p.id && !ROBOTS[p.id])
    .sort((a, b) => `${a.created_at || ""}${a.id}`.localeCompare(`${b.created_at || ""}${b.id}`));
  rows.forEach((p, n) => {
    out[p.id] = { robot: `W${FIRST_PROVIDER_ROBOT + n}`, name: p.name || p.id, tone: "provider", does: ["read", "write"], added: true, enabled: p.enabled !== false };
  });
  return out;
}
export const DOES = {
  read: ["Baca", "Read"], write: ["Tulis", "Write"], read_image: ["Baca gambar", "Read image"], make_image: ["Buat gambar", "Make image"],
};
export const JOBS = {
  reader: ["Penulis teks", "Text writer"], motion: ["Penulis motion", "Motion writer"], image_reader: ["Pembaca gambar", "Picture reader"], image_gen: ["Pelukis", "Picture maker"],
};
const ACTIVE_MS = 3 * 3600_000;
const STALE_MS = 13 * 3600_000;

/** A robot for a status row's slug: the named five, a provider Wan added, else a guest robot named after the host. */
export function robotOf(slug, row, providers) {
  const table = providers ? robotsWith(providers) : ROBOTS;
  if (table[slug]) return { slug, ...table[slug] };
  const host = (row?.base_url || slug || "").replace(/^https?:\/\//, "").split("/")[0];
  return { slug, robot: "W?", name: row?.name || host || slug, tone: "guest", does: row?.role === "image" ? ["make_image"] : ["read", "write"] };
}

/** active = did real work in the last 3 h (a usage row that was ok) or the probe just answered; standby = reachable but idle;
    offline = unreachable, key refused, no key, or not checked in 13 h. */
export function stateOf(row, usageRows = [], now = Date.now()) {
  if (!row || !row.key_set) return "offline";
  if (row.checked_at && now - new Date(row.checked_at).getTime() > STALE_MS) return "offline";
  if (!row.reachable || row.key_ok === false) return "offline";
  if (row.chat_ok === false) return "offline";
  const last = (usageRows || []).reduce((m, u) => (u.gateway === row.slug && u.ok && u.area !== "probe" && u.area !== "pulse" ? Math.max(m, new Date(u.created_at).getTime()) : m), 0);
  return now - last < ACTIVE_MS ? "active" : "standby";
}

/** Every robot the page should draw: the three named ones always (a missing row is an offline robot with no key), plus any
    other gateway the probe wrote, plus every provider Wan added (a provider the probe has not reached yet is an offline W6). */
export function teamCards(statusRows, usageRows = [], now = Date.now(), providers = []) {
  const bySlug = Object.fromEntries((statusRows || []).map((r) => [r.slug, r]));
  const table = robotsWith(providers);
  const added = Object.keys(table).filter((s) => table[s].added);
  const slugs = [...ORDER, ...Object.keys(bySlug).filter((s) => !ORDER.includes(s) && !added.includes(s)).sort(), ...added];
  return slugs.map((slug) => {
    const row = bySlug[slug] || null;
    const r = robotOf(slug, row, providers);
    return { ...r, row, state: stateOf(row, usageRows, now), configured: !!row?.key_set };
  });
}

/** What the router decided, from settings.ai_team_state: {chosen, backup, order, skipped, pin, why, at} for a job. */
export function decisionOf(state, job = "reader") {
  const s = (state || {})[job] || {};
  return { chosen: s.chosen || null, backup: s.backup || null, order: s.order || [], skipped: s.skipped || [], pin: s.pin || null, why: s.why || "", at: (state || {}).at || "",
    live: s.live || null };
}

/** The pin to save for a job, or null for auto. */
export function pinFor(team, job) {
  const p = (team || {}).pins?.[job];
  return p && p.gateway ? { gateway: p.gateway, model: p.model || "" } : null;
}

/** settings.ai_team with one job's pin changed; everything else untouched. `changed_at` says when, so the page can tell a decision
    made before the change (the worker has not looked yet) from one made after it (supabase/057 wakes the worker at once). */
export function withPin(team, job, pin, now = new Date()) {
  const pins = { ...((team || {}).pins || {}) };
  pins[job] = pin && pin.gateway ? { gateway: pin.gateway, model: pin.model || "" } : null;
  return { ...(team || {}), pins, changed_at: now.toISOString() };
}

/** The model Wan chose as a robot's own default (settings.ai_team.models[slug]), or "" when he chose none: the one its probe asks and
    its jobs use unless a pin names another (9 Nov 2026: "allow me to adjust model mireld"). */
export function modelOverride(team, slug) {
  const m = (team || {}).models?.[slug];
  return typeof m === "string" ? m : "";
}

/** settings.ai_team with one robot's default model set (empty clears it); pins and the other robots are untouched. `changed_at` wakes
    the worker the same way a pin does (supabase/057), so the new decision shows within a minute. */
export function withModel(team, slug, model, now = new Date()) {
  const models = { ...((team || {}).models || {}) };
  const m = String(model || "").trim();
  if (m) models[slug] = m; else delete models[slug];
  return { ...(team || {}), models, changed_at: now.toISOString() };
}

/** True while a saved pin has not been decided on yet: the last decision is older than the change (and the change is recent,
    so a worker that never wakes does not leave "testing" on the page for ever). */
export function decisionPending(team, state, now = Date.now()) {
  const changed = Date.parse((team || {}).changed_at || "");
  if (!Number.isFinite(changed) || now - changed > 15 * 60_000) return false;
  const decided = Date.parse((state || {}).at || "");
  return !Number.isFinite(decided) || decided < changed;
}

/** What the live check said about a job's chosen or pinned model, as short words for the card: [{ok, text}]. */
export function liveLines(live, job) {
  const out = [];
  for (const [key, a] of Object.entries(live?.answers || {})) {
    const [slug, model] = key.split("|");
    out.push({ ok: !!a.ok, text: `${model} · ${slug}: ${a.ok ? `${a.ms ?? "?"} ms` : (a.error || "no answer")}` });
  }
  for (const [slug, model] of Object.entries(live?.found || {})) out.push({ ok: true, text: `${slug}: ${model} (found)`, found: true });
  return out;
}

/** The models a robot may be pinned to for a job: what its probe listed, the configured one first; image models for the
    painter, text models for the writer (the router refuses an image model on a text job, so the page does not offer it). */
const IMAGE_RE = /image|dall-?e|flux|stable-?diffusion|sdxl|imagen|seedream|sora|veo|kling|wan2|hunyuan/i;
export function modelsFor(row, job) {
  const list = [...new Set([row?.model, ...(row?.models || [])].filter(Boolean))];
  const want = job === "image_gen" ? (m) => IMAGE_RE.test(m) : (m) => !IMAGE_RE.test(m);   // reader, motion, image_reader: chat models
  const ok = list.filter(want);
  return ok.length ? ok : list;
}

/** Which robots may take a job at all (the text jobs, reader and motion, take any robot that writes). */
export function robotsFor(cards, job) {
  const need = job === "image_gen" ? "make_image" : job === "image_reader" ? "read_image" : "write";
  return cards.filter((c) => c.does.includes(need) || (job === "image_reader" && c.does.includes("read")));
}

export const fmtMs = (ms) => (ms == null ? "" : ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`);

/* A rating for one model from the function's live "check" answer (Wan, 9 Nov 2026: pick a model as a button, then try it live and get a
   rating). Out of 100, from what the check really measured, never from a guess:
     answered   25  the model answered a request at all (the picture question is a real chat call)
     listed     10  the gateway lists it by this exact name (5 when only spelled differently)
     picture    20  it read the red test picture            tools    20  it called the test tool
     speed      25  the picture question's time: full at 2 s or less, nothing at 15 s or more, in between linearly
   A check that could not run (an image maker, the ChatGPT login, a function not deployed) is `tested: false`, never a low score.
   Pure, so web/aiRate.test.mjs runs this under Node. */
export function rateCheck(report) {
  if (!report || typeof report !== "object" || report.error) return { tested: false, why: String(report?.error || "no answer").slice(0, 160) };
  const img = report.image || {}, tools = report.tools || {}, ms = Number(report.image_ms);
  const answered = img.tested && !img.error ? 25 : 0;
  const listed = report.listed?.exact ? 10 : report.listed?.spelled_as ? 5 : 0;
  const picture = img.reads ? 20 : 0, calls = tools.calls ? 20 : 0;
  const speed = Number.isFinite(ms) && answered ? Math.round(25 * Math.min(1, Math.max(0, (15000 - ms) / 13000))) : 0;
  const score = answered + listed + picture + calls + speed;
  const stars = score >= 90 ? 5 : score >= 75 ? 4 : score >= 55 ? 3 : score >= 35 ? 2 : score > 0 ? 1 : 0;
  return { tested: true, score, stars, ms: Number.isFinite(ms) ? ms : null,
    parts: { answered: !!answered, listed: !!listed, picture: !!picture, tools: !!calls, speed },
    note: !answered ? "did not answer" : !picture && !calls ? "answers, but reads no picture and calls no tool" : "" };
}

/* A rating for one PICTURE model from the function's image check (one small real drawing). Out of 100, from what was measured:
     drew      60  a picture came back          listed  10  the gateway lists the model by this exact name (5 when spelled differently)
     speed     30  the drawing's time: full at 15 s or less, nothing at 60 s or more, in between linearly
   A check that could not run (a function not deployed, a robot with no key) is `tested: false`, never a low score. */
export function rateImage(report) {
  if (!report || typeof report !== "object" || report.error) return { tested: false, why: String(report?.error || "no answer").slice(0, 160) };
  const g = report.image_gen || {};
  if (!g.tested) return { tested: false, why: "no answer" };
  const ms = Number(g.ms);
  const drew = g.ok ? 60 : 0;
  const listed = report.listed?.exact ? 10 : report.listed?.spelled_as ? 5 : 0;
  const speed = g.ok && Number.isFinite(ms) ? Math.round(30 * Math.min(1, Math.max(0, (60000 - ms) / 45000))) : 0;
  const score = drew + listed + speed;
  const stars = score >= 90 ? 5 : score >= 75 ? 4 : score >= 55 ? 3 : score >= 35 ? 2 : score > 0 ? 1 : 0;
  return { tested: true, kind: "image", score, stars, ms: Number.isFinite(ms) ? ms : null,
    parts: { drew: !!drew, listed: !!listed, speed }, note: g.ok ? "" : String(g.error || "no picture came back").slice(0, 160) };
}

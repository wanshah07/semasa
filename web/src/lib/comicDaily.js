/* The daily comic series on the page (Wan, 17 Nov 2026: "can start create comic series storyboard and after approve create motion -
   this series will comeout everyday which contain about isu semasa>halal>regulatory>fatwa"). The worker (backend/semasa/comic_daily.py)
   plans one episode a day from the feed, writes its storyboard and waits for Wan; this file is only what the page needs to show it:
   the settings row `comic_series` (the switch, the pause, the lanes in his order), the series' episodes (Motion films whose
   options.template is "comic"), the worker's own record of looked-at days (`comic_series_log`), and the button.
   Plain functions, so comicDaily.test.mjs runs them in Node. Nothing here decides anything the worker does not check again. */
import RULES from "../../../rules/comic.json";

export const DAILY = RULES.daily;
export const LANES = DAILY.lane_defs;
export const LANE_IDS = LANES.map((l) => l.id);
export const SETTING = "comic_series";
export const STATE = "comic_series_log";
const MYT_MS = 8 * 3600 * 1000;

const obj = (v) => (v && typeof v === "object" && !Array.isArray(v) ? v : {});
const hhmm = (v, fallback) => (/^([01]\d|2[0-3]):[0-5]\d$/.test(String(v || "").trim()) ? String(v).trim() : fallback);

/** The settings row with the file's defaults: the switch is OFF unless it is exactly true, a lane the list does not name is off, an
    unknown lane is dropped, an empty list is no lane at all (mirrors comic_daily.config). */
export function dailyConfig(value) {
  const v = obj(value);
  const given = Array.isArray(v.lanes) ? v.lanes : DAILY.lanes;
  const lanes = [];
  for (const id of given) if (LANE_IDS.includes(id) && !lanes.includes(id)) lanes.push(id);
  return { enabled: v.enabled === true, paused: v.paused === true, lanes, at: hhmm(v.at, DAILY.at), series: String(v.series || DAILY.series),
    wordsMode: v.words_mode === "auto" ? "auto" : "art", makeNow: String(v.make_now || "") };
}

/** Every lane in the order the worker tries them (the ones switched on first, in Wan's order), then the switched-off ones:
    [{ id, on, name: {bm, en}, reads: {bm, en} }]. */
export function laneRows(cfg) {
  const on = cfg.lanes.map((id) => ({ ...LANES.find((l) => l.id === id), on: true }));
  const off = LANES.filter((l) => !cfg.lanes.includes(l.id)).map((l) => ({ ...l, on: false }));
  return [...on, ...off];
}

/** The lane list after moving a switched-on lane up (-1) or down (+1); a lane at the end stays where it is. */
export function moveLane(lanes, id, step) {
  const i = lanes.indexOf(id);
  const j = i + step;
  if (i < 0 || j < 0 || j >= lanes.length) return [...lanes];
  const out = [...lanes];
  [out[i], out[j]] = [out[j], out[i]];
  return out;
}

/** The lane list with one lane switched on (added at the end) or off. */
export const toggleLane = (lanes, id) => (lanes.includes(id) ? lanes.filter((x) => x !== id) : LANE_IDS.includes(id) ? [...lanes, id] : [...lanes]);

/** The settings value with `patch` merged in: Wan's other keys are kept as they are (the page replaces the whole row on save). */
export function withConfig(value, patch) {
  const v = obj(value);
  const cfg = dailyConfig(v);
  return { ...v, enabled: cfg.enabled, paused: cfg.paused, lanes: cfg.lanes, at: cfg.at, series: cfg.series, words_mode: cfg.wordsMode, ...patch };
}

/** The value a press of "Buat episod hari ini sekarang" writes: the worker answers a timestamp it has not answered yet. */
export const withMakeNow = (value, now = new Date()) => withConfig(value, { make_now: now.toISOString() });

/** Today, Malaysia time, as YYYY-MM-DD (the worker's day, comic_daily.myt_day). */
export const mytDay = (now = new Date()) => new Date(now.getTime() + MYT_MS).toISOString().slice(0, 10);

/** The series' episodes from Motion films, newest first: { id, episode, day, lane, title, status, stage, error, source, postId,
    videoUrl, posterUrl, seconds, requested, item, ruling }. A film that is not the series' is left out. */
export function episodesOf(rows) {
  return (rows || []).filter((r) => r?.options?.template === "comic").map((r) => {
    const s = obj(r.options?.series);
    const sb = obj(r.storyboard?.sb);
    return { id: r.id, episode: Number(s.episode) || 0, day: String(s.day || ""), lane: String(s.lane || ""), title: String(r.title || sb.title || s.item?.title || ""),
      status: r.status, stage: r.stage || "", error: String(r.error || ""), source: String(sb.source || s.source || ""), postId: r.queued_post_id || null,
      videoUrl: r.video_url || "", posterUrl: r.poster_url || "", seconds: Number(r.duration_s) || 0, requested: String(s.requested || ""),
      item: obj(s.item), ruling: s.ruling || null, createdAt: r.created_at || "", row: r };
  }).sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)) || b.episode - a.episode);
}

/** Today's episode: the newest of today's that is not a rejected storyboard (a rejected one is no episode, comic_daily.plan_today). */
export const todayOf = (episodes, now = new Date()) => (episodes || []).find((e) => e.day === mytDay(now) && e.status !== "rejected") || null;

/** One line for where an episode is: [Bahasa Malaysia, English, tone]. */
export function statusWords(e) {
  const done = e.postId ? ["Siap, draf post sudah dibuat (menunggu Lulus anda)", "Finished, the draft post is made (waiting for your Approve)"]
    : ["Filem siap; draf post belum dibuat, ia dibuat pada larian seterusnya", "The film is finished; the draft post is made on the next run"];
  const table = {
    pending: e.stage === "pictures" || e.stage === "film" || (e.row?.storyboard_approved_at) ? ["Diluluskan, menunggu worker melukis komik dan membuat filem", "Approved, waiting for the worker to draw the comic and make the film", "ok"]
      : ["Menunggu worker menulis storyboard", "Waiting for the worker to write the storyboard", "muted"],
    working: e.stage === "film" ? ["Filem sedang dibuat", "The film is being made", "ok"] : e.stage === "pictures" ? ["Komik sedang dilukis", "The comic is being drawn", "ok"]
      : ["Storyboard sedang ditulis", "The storyboard is being written", "ok"],
    review: ["Storyboard menunggu kelulusan anda: tiada gambar dibayar sebelum itu", "The storyboard waits for your approval: no picture is paid for before that", "warn"],
    done: [...done, e.postId ? "ok" : "muted"],
    rejected: ["Storyboard ditolak: tiada gambar dilukis", "Storyboard rejected: nothing was drawn", "muted"],
    error: ["Gagal; baca sebabnya di bawah. Komik yang sudah dilukis tidak dilukis semula", "Failed; read the reason below. A comic already drawn is not drawn again", "danger"],
    waiting: ["Dalam giliran", "Queued", "muted"],
  };
  return table[e.status] || [String(e.status || ""), String(e.status || ""), "muted"];
}

/** The worker's record of days (`comic_series_log`): the last 30, newest first, each { day, status, lane, title, reason, episode, at }. */
export function logLines(state) {
  const s = obj(state);
  return (Array.isArray(s.log) ? s.log : []).filter((x) => x && x.day).slice().reverse().map((x) => ({
    day: String(x.day), status: String(x.status || ""), lane: String(x.lane || ""), title: String(x.title || ""), reason: String(x.reason || ""),
    episode: x.episode || null, at: String(x.at || ""), via: String(x.via || "") }));
}

/** What the worker said to the last press of the button, if it has answered the press the page wrote: { status, reason } or null. */
export function makeNowAnswer(cfg, state) {
  const s = obj(state);
  if (!cfg.makeNow) return null;
  if (String(s.make_now_done || "") < cfg.makeNow) return { status: "waiting", reason: "" };
  return { status: String(s.make_now_result || ""), reason: String(s.make_now_reason || "") };
}

/** The skipped-day reason is the worker's English sentence; the status words are the page's. */
export const dayStatusWords = (status) => ({ planned: ["storyboard ditulis", "storyboard written"], skipped: ["tiada episod", "no episode"] }[status] || [status, status]);

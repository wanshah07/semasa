/* The comic (dialogue poster) on the page: the styles and series, the script as Wan types it, and what the worker did with the
   words. The built-in styles and series are rules/comic.json, the one file the worker reads too
   (backend/semasa/comic_library.py); Wan's own are the settings row `comic` ({styles, series}), merged over them by id.
   Everything here is plain functions, so comic.test.mjs runs them in Node. The worker is the judge: it rebuilds the cast
   from the series, checks the script again and decides the episode number. */
import RULES from "../../../rules/comic.json";
import { bi } from "./bi";
import { readsMalay, scan, vagueHits } from "./compliance";

export const LIMITS = RULES.limits;
export const SPEAKERS = ["A", "B"];
export const BUILT_IN = { styles: RULES.styles.map((s) => s.id), series: RULES.series.map((s) => s.id) };
const ID_RE = /^[a-z0-9][a-z0-9-]{1,39}$/;
const chars = (s) => [...String(s ?? "")].length;

/** One line of plain text, or "" when it is not text or is over the limit (refused whole, never cut: the worker does the same). */
const line = (value, limit) => {
  if (typeof value !== "string") return "";
  // eslint-disable-next-line no-control-regex
  const text = value.replace(/[\u0000-\u001f\u007f\u2028\u2029]+/g, " ").split(/\s+/).filter(Boolean).join(" ");
  return chars(text) <= limit ? text : "";
};

const pair = (value, limit) => {
  const bm = value && typeof value === "object" ? line(value.bm, limit) : line(value, limit);
  const en = value && typeof value === "object" ? line(value.en, limit) : bm;
  return { bm: bm || en, en: en || bm };
};

export function cleanStyle(raw) {
  if (!raw || typeof raw !== "object" || !ID_RE.test(String(raw.id || ""))) return null;
  const prompt = line(raw.prompt, LIMITS.style_prompt);
  const name = pair(raw.name, LIMITS.name);
  if (chars(prompt) < 40 || !name.bm) return null;
  return { id: String(raw.id), name, about: pair(raw.about, LIMITS.about), prompt, lettering: line(raw.lettering, LIMITS.lettering) };
}

export function cleanSeries(raw) {
  if (!raw || typeof raw !== "object" || !ID_RE.test(String(raw.id || ""))) return null;
  const name = line(raw.name, LIMITS.name);
  const cast = {};
  for (const who of SPEAKERS) {
    const c = (raw.cast && typeof raw.cast === "object" && raw.cast[who]) || {};
    const person = { name: line(c.name, LIMITS.name), look: line(c.look, LIMITS.look), role: line(c.role, LIMITS.role), voice: line(c.voice, LIMITS.voice) };
    if (!person.name || chars(person.look) < 20) return null;
    cast[who] = person;
  }
  if (!name) return null;
  return { id: String(raw.id), name, about: pair(raw.about, LIMITS.about), setting: line(raw.setting, LIMITS.setting), cast };
}

function merge(builtIn, own, clean, most) {
  const out = builtIn.map(clean).filter(Boolean);
  let kept = 0;
  for (const raw of Array.isArray(own) ? own : []) {
    const item = clean(raw);
    if (!item) continue;
    const at = out.findIndex((x) => x.id === item.id);
    if (at >= 0) { out[at] = { ...item, ...(out[at].own ? { own: true } : { edited: true }) }; continue; }
    if (kept >= most) continue;
    kept += 1;
    out.push({ ...item, own: true });
  }
  return out;
}

/** { styles, series, defaultStyle, defaultSeries }: the built-in ones with Wan's merged over them (mirrors comic_library.library). */
export function comicLibrary(value) {
  const v = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const styles = merge(RULES.styles, v.styles, cleanStyle, LIMITS.own_styles);
  const series = merge(RULES.series, v.series, cleanSeries, LIMITS.own_series);
  const pick = (want, items, fallback) => (items.some((x) => x.id === want) ? want : fallback);
  return { styles, series, defaultStyle: pick(v.default_style, styles, RULES.default_style), defaultSeries: pick(v.default_series, series, RULES.default_series) };
}

/** A new id from a name: "Kedai Runcit Pak Mat" becomes "kedai-runcit-pak-mat", never one already taken. */
export function newId(name, taken = []) {
  const base = String(name || "").toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 32) || "komik";
  let id = base.length < 2 ? `${base}-1` : base;
  for (let n = 2; taken.includes(id); n += 1) id = `${base}-${n}`;
  return id;
}

/** The settings value with one style or series saved into it (`kind`: "styles" | "series"). null when the entry is not whole. */
export function withEntry(value, kind, entry) {
  const item = (kind === "styles" ? cleanStyle : cleanSeries)(entry);
  if (!item) return null;
  const v = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const list = (Array.isArray(v[kind]) ? v[kind] : []).filter((x) => x && x.id !== item.id);
  return { ...v, [kind]: [...list, item] };
}

/** The settings value without Wan's entry `id`: his own one is gone, a built-in one he edited is the file's again. */
export function withoutEntry(value, kind, id) {
  const v = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  return { ...v, [kind]: (Array.isArray(v[kind]) ? v[kind] : []).filter((x) => x && x.id !== id) };
}

/** Why a style or series form cannot be saved yet, or "". */
export function entryProblem(kind, entry) {
  if (kind === "styles") {
    if (!line(entry?.name?.bm ?? entry?.name, LIMITS.name)) return bi("Beri nama gaya (paling banyak {n} aksara).", "Give the style a name (at most {n} characters).").replace("{n}", LIMITS.name);
    const p = String(entry?.prompt || "").trim();
    if (chars(p) < 40) return bi("Terangkan gaya dengan lebih terperinci: garis, warna, lorekan, perkadaran, wajah, latar.", "Describe the style in more detail: line, colour, shading, proportions, faces, background.");
    if (chars(p) > LIMITS.style_prompt) return bi("Penerangan gaya terlalu panjang.", "The style description is too long.");
    if (chars(entry?.lettering || "") > LIMITS.lettering) return bi("Penerangan huruf terlalu panjang.", "The lettering description is too long.");
    return cleanStyle(entry) ? "" : bi("Gaya belum lengkap.", "The style is not complete yet.");
  }
  if (!line(entry?.name, LIMITS.name)) return bi("Beri nama siri (paling banyak {n} aksara).", "Give the series a name (at most {n} characters).").replace("{n}", LIMITS.name);
  for (const who of SPEAKERS) {
    const c = entry?.cast?.[who] || {};
    if (!line(c.name, LIMITS.name)) return bi("Beri nama watak {w}.", "Give character {w} a name.").replace("{w}", who);
    const look = String(c.look || "").trim();
    if (chars(look) < 20) return bi("Terangkan rupa watak {w} dengan tepat: umur, wajah, pakaian, warna.", "Describe character {w}'s appearance exactly: age, face, clothes, colours.").replace("{w}", who);
    if (chars(look) > LIMITS.look) return bi("Rupa watak {w} terlalu panjang.", "Character {w}'s appearance is too long.").replace("{w}", who);
  }
  return cleanSeries(entry) ? "" : bi("Siri belum lengkap.", "The series is not complete yet.");
}

/* ---- the script ---- */

export const blankScript = () => ({ title: "", setting: "", panels: Array.from({ length: LIMITS.panels }, () => ({ scene: "", lines: [{ who: "A", text: "" }, { who: "B", text: "" }] })) });

const flat = (v) => String(v ?? "").replace(/\*/g, "").split(/\s+/).filter(Boolean).join(" ");

/** The script as it is sent: empty bubbles dropped, words flattened. The worker puts the cast in from the series. */
export function tidyScript(raw) {
  const panels = (Array.isArray(raw?.panels) ? raw.panels : []).map((p) => ({
    scene: flat(p?.scene).slice(0, LIMITS.scene),
    lines: (Array.isArray(p?.lines) ? p.lines : []).map((l) => ({ who: SPEAKERS.includes(l?.who) ? l.who : "A", text: flat(l?.text) })).filter((l) => l.text),
  }));
  return { title: flat(raw?.title), setting: flat(raw?.setting).slice(0, LIMITS.setting), panels };
}

/** A written or stored script back in the form's shape: four panels, two bubble rows each (the second may be empty). */
export function formScript(raw) {
  const s = tidyScript(raw || {});
  const panels = Array.from({ length: LIMITS.panels }, (_, i) => {
    const p = s.panels[i] || { scene: "", lines: [] };
    const first = p.lines[0] || { who: "A", text: "" };
    const second = p.lines[1] || { who: first.who === "A" ? "B" : "A", text: "" };
    return { scene: p.scene, lines: [first, second] };
  });
  return { title: s.title, setting: s.setting, panels };
}

/** Why a script cannot be drawn as typed, or "" (the worker's comic.check, in the page's language). */
export function scriptProblem(raw, source = "") {
  const s = tidyScript(raw);
  if (!s.title) return bi("Komik perlukan tajuk.", "The comic needs a title.");
  if (chars(s.title) > LIMITS.title) return bi("Tajuk {n} aksara, melebihi {m}.", "The title has {n} characters, more than {m}.").replace("{n}", chars(s.title)).replace("{m}", LIMITS.title);
  if (chars(flat(source)) > LIMITS.source) return bi("Sumber terlalu panjang.", "The source is too long.");
  if (s.panels.length !== LIMITS.panels) return bi("Komik ada tepat {n} panel.", "A comic has exactly {n} panels.").replace("{n}", LIMITS.panels);
  for (let i = 0; i < s.panels.length; i += 1) {
    const lines = s.panels[i].lines;
    const n = i + 1;
    if (lines.length < 1) return bi("Panel {n}: tulis sekurang-kurangnya satu gelembung.", "Panel {n}: write at least one bubble.").replace("{n}", n);
    if (lines.length > LIMITS.lines) return bi("Panel {n}: paling banyak dua gelembung.", "Panel {n}: at most two bubbles.").replace("{n}", n);
    if (new Set(lines.map((l) => l.who)).size !== lines.length) return bi("Panel {n}: setiap watak bercakap sekali sahaja dalam satu panel.", "Panel {n}: each person speaks once in a panel.").replace("{n}", n);
    const long = lines.find((l) => chars(l.text) > LIMITS.chars);
    if (long) return bi("Panel {n}: satu gelembung ada {c} aksara, melebihi {m} yang masih mudah dibaca.", "Panel {n}: a bubble has {c} characters, more than the {m} that stay readable.").replace("{n}", n).replace("{c}", chars(long.text)).replace("{m}", LIMITS.chars);
  }
  return "";
}

/** The comic's words in reading order: the title, then every bubble. */
export const scriptUnits = (raw) => { const s = tidyScript(raw); return [s.title, ...s.panels.flatMap((p) => p.lines.map((l) => l.text))]; };

/** The comic's words in the shape a design's words are kept in (the worker's comic_writer.artwork). */
export const scriptArtwork = (raw) => { const s = tidyScript(raw); return [{ title: s.title, points: [] }, ...s.panels.map((p) => ({ title: "", points: p.lines.map((l) => l.text) }))]; };

export const sourceLine = (source, stream) => {
  const s = flat(source);
  if (!s || /^\s*(sumber|source|rujukan)\s*:/i.test(s)) return s;
  return `${stream === "linkedin" ? "Source" : "Sumber"}: ${s}`;
};

/** [{hard, where, msg}] for a typed script, by the rules the worker uses (comic_writer.flags): the post rules over the title
    and every bubble, the vague-wording rule in reading order, English on LinkedIn, no em dash. */
export function scriptFlags(raw, stream, source = "", brand = null) {
  const s = tidyScript(raw);
  if (!s.title && !s.panels.some((p) => p.lines.length)) return [];
  const out = [];
  // only what is written is judged, and each entry keeps its own name, so "Comic panel 3" is panel 3 while panel 2 is still empty
  const art = [], labels = [];
  if (s.title) { art.push({ title: s.title, points: [] }); labels.push("Comic title"); }
  s.panels.forEach((p, i) => { if (p.lines.length) { art.push({ title: "", points: p.lines.map((l) => l.text) }); labels.push(`Comic panel ${i + 1}`); } });
  for (const f of scan({ stream, citation: sourceLine(source, stream), media: [{ artwork: art }] }, brand)) {
    const m = /^Design \d+, slide (\d+)$/.exec(f.where);
    if (m) out.push({ ...f, where: labels[Number(m[1]) - 1] || "Comic" });
    else if (f.where === "Source") out.push(f);
  }
  const units = scriptUnits(raw);
  for (const phrase of vagueHits(units)) out.push({ hard: true, where: "Comic", msg: `vague: "${phrase}". Say exactly which, how many or from when: put the figure, the date or the entry number in that bubble or the two after it.` });
  const text = units.join("\n");
  if (stream === "linkedin" && readsMalay(text)) out.push({ hard: true, where: "Comic", msg: "reads as Bahasa Malaysia. The LinkedIn stream is English: write the comic in English." });
  if (/[\u2014\u2013]/.test(text)) out.push({ hard: true, where: "Comic", msg: "an em dash. Use a full stop or a comma." });
  return out;
}

/* ---- episodes ---- */

const whole = (v) => { const n = Number.parseInt(v, 10); return Number.isInteger(n) && n >= 1 && n <= 9999 && String(n) === String(v).trim() ? n : 0; };

/** The next episode of a series from the comics the page holds: its finished comics, and never less than the highest number
    one of them carries. The worker counts again when it draws (comic_job.episodes_so_far), and its number is the one printed. */
export function nextEpisode(rows, seriesId) {
  let count = 0, highest = 0;
  for (const r of rows || []) {
    const c = r?.meta?.comic;
    if (r?.meta?.design !== "comic" || r.status !== "done" || !c || c.series !== seriesId || !c.episode) continue;
    count += 1;
    highest = Math.max(highest, whole(c.episode));
  }
  return Math.max(count, highest) + 1;
}

export const episodeLine = (name, n, lang = "bm") => {
  const s = flat(name);
  if (!s) return "";
  if (lang === "en") return n ? `${s} · Episode ${n}` : s;
  return n ? `Siri ${s} · Episod ${n}` : `Siri ${s}`;
};

/* ---- the job ---- */

/** The meta of a comic Design job. `script` is Wan's own (words "own"); else the worker writes it from `brief`. */
export function comicMeta({ stream, series, style, source = "", brief = "", script = null, review = true, wordsMode = "auto", episode = "" }) {
  const own = script ? tidyScript(script) : null;
  const n = whole(episode);
  return {
    flow: "design", design: "comic", format: "portrait", stream, citation: flat(source).slice(0, LIMITS.source),
    ...(own ? { slides: scriptArtwork(own) } : { brief: String(brief || "").trim().slice(0, 4000) }),
    comic: {
      series: series.id, style: style.id, series_copy: cleanSeries(series), style_copy: cleanStyle(style),
      words_mode: wordsMode === "art" ? "art" : "auto", ...(own ? { script: own } : { review: !!review }), ...(n ? { episode: n } : {}),
    },
  };
}

/** A comic row sent back to the worker with Wan's edited script: drawn from exactly these words, the episode number kept. */
export function redrawMeta(meta, script) {
  const own = tidyScript(script);
  const { revise: _r, ...c } = meta?.comic || {};
  return { ...meta, slides: scriptArtwork(own), comic: { ...c, script: own, stage: "draw" } };
}

/** What stage a comic row is at for the page: "script" (waiting for Wan to read it), "done", "error", or "working". */
export function comicStage(row) {
  if (row?.status === "error") return "error";
  if (row?.status !== "done") return "working";
  return row?.meta?.comic?.stage === "script" && !row.generated_media_url ? "script" : "done";
}

/** How the words got onto the comic, for the card: { tone: "ok" | "warn", bm, en } or null before it is drawn. */
export function wordsNote(words) {
  if (!words || !words.path) return null;
  if (words.path === "full") {
    const twice = words.draws > 1;
    return { tone: "ok",
      bm: `Perkataan ditulis oleh pelukis gambar dan disemak: setiap gelembung sepadan dengan skrip${twice ? ` (dilukis ${words.draws} kali)` : ""}.`,
      en: `The picture maker wrote the words and they were checked: every bubble matches the script${twice ? ` (drawn ${words.draws} times)` : ""}.` };
  }
  const why = String(words.why || "");
  const reason = /no picture reader/.test(why) ? ["tiada pembaca gambar, jadi perkataan pelukis tidak dapat disemak", "no picture reader is available, so the picture maker's words could not be checked"]
    : /gave no answer/.test(why) ? ["pembaca gambar tidak menjawab, jadi perkataan pelukis tidak dapat disemak", "the picture reader gave no answer, so the picture maker's words could not be checked"]
      : /differed/.test(why) ? ["perkataan pelukis berbeza daripada skrip dua kali", "the picture maker's words differed from the script twice"]
        : /asked to print/.test(why) ? ["itu yang anda pilih", "that is what you chose"] : ["", ""];
  return { tone: /asked to print/.test(why) ? "ok" : "warn",
    bm: `Perkataan dicetak oleh Semasa sendiri, tepat seperti skrip${reason[0] ? `: ${reason[0]}` : ""}.`,
    en: `Semasa printed the words itself, exactly as the script has them${reason[1] ? `: ${reason[1]}` : ""}.` };
}

/* The watchdog light of each scrape source (Wan, 14 Nov 2026: "add light watchdog in semasa, green live, orange standby, red unlive").
   The lights are worked out by the backend (backend/semasa/source_lights.py) and saved as settings.source_lights, so this file
   only READS them: the dot here and the watchdog e-mail cannot disagree. If the watchdog itself has not updated for hours the
   dot goes grey ("unknown"), never a stale green.
   Each light also carries `checked`: when that source itself was last swept (Wan, 14 Nov 2026: "make button color based on
   status and what time checked"). The buttons, the status line under them and the dashboard card all read it from here. */
export const LIGHT_BG = { green: "bg-ok", orange: "bg-warn", red: "bg-danger", unknown: "bg-line" };
/* a whole button or tile tinted by its light: a soft fill and a ring of the same colour, so the label keeps the page's own ink */
export const LIGHT_TINT = {
  green: "bg-ok/15 ring-1 ring-inset ring-ok/50", orange: "bg-warn/15 ring-1 ring-inset ring-warn/60",
  red: "bg-danger/15 ring-1 ring-inset ring-danger/60", unknown: "bg-surface-2 ring-1 ring-inset ring-line",
};
export const LIGHT_NAME = { green: ["Hidup", "Live"], orange: ["Siaga", "Standby"], red: ["Tidak hidup", "Unlive"], unknown: ["Belum diketahui", "Unknown"] };
export const STALE_MS = 13 * 3600 * 1000;      // the health run refreshes the lights every six hours
/* every light the backend works out, in the order the page shows them; `tab` is where a press on it leads */
export const SOURCES = [
  ["regulatory", "Regulatori", "Regulatory", "isu"], ["publication", "Penerbitan", "Publications", "isu"], ["reddit", "Reddit", "Reddit", "isu"],
  ["youtube", "YouTube", "YouTube", "isu"], ["threads", "Threads", "Threads", "isu"], ["facebook", "Facebook", "Facebook", "isu"],
  ["instagram", "Instagram", "Instagram", "isu"], ["folder", "OneDrive", "OneDrive", "isu"], ["myra", "MYRA", "MYRA", "isu"],
  ["expert", "Kandungan pakar", "Expert content", "pakar"],
];

/** { light: "green" | "orange" | "red" | "unknown", why, checked } for one source. `checked` is an ISO time or "". */
export function lightOf(setting, section, nowMs = Date.now()) {
  const lights = setting && setting.lights;
  const one = lights && lights[section];
  if (!one || !LIGHT_BG[one.light]) return { light: "unknown", why: "no reading yet", checked: "" };
  const at = Date.parse(setting.at);
  const checked = String(one.checked || "");
  if (Number.isFinite(at) && nowMs - at > STALE_MS) {
    return { light: "unknown", why: `the watchdog has not updated for ${Math.floor((nowMs - at) / 3600000)} h`, checked };
  }
  return { light: one.light, why: String(one.why || ""), checked };
}

const MYT_MS = 8 * 3600 * 1000;
const MONTHS = ["Jan", "Feb", "Mac", "Apr", "Mei", "Jun", "Jul", "Ogo", "Sep", "Okt", "Nov", "Dis"];
const MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** When a source was checked, short enough for a button: "17:12" today (Malaysia time), "13 Nov 17:12" on another day, "" when
    never. Pure arithmetic, no Intl, so it reads the same in every browser and under Node. */
export function checkedText(iso, nowMs = Date.now(), en = false) {
  const at = Date.parse(iso);
  if (!Number.isFinite(at)) return "";
  const d = new Date(at + MYT_MS), n = new Date(nowMs + MYT_MS);
  const hm = `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
  if (d.toISOString().slice(0, 10) === n.toISOString().slice(0, 10)) return hm;
  return `${d.getUTCDate()} ${(en ? MONTHS_EN : MONTHS)[d.getUTCMonth()]} ${hm}`;
}

/** How many sources are in each state, for the dashboard card's headline. */
export function lightCounts(setting, nowMs = Date.now()) {
  const n = { green: 0, orange: 0, red: 0, unknown: 0 };
  for (const [section] of SOURCES) n[lightOf(setting, section, nowMs).light]++;
  return n;
}

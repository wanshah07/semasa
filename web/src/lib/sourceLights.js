/* The watchdog light of each scrape source (Wan, 14 Nov 2026: "add light watchdog in semasa, green live, orange standby, red unlive").
   The lights are worked out by the backend (backend/semasa/source_lights.py) and saved as settings.source_lights, so this file
   only READS them: the dot here and the watchdog e-mail cannot disagree. If the watchdog itself has not updated for hours the
   dot goes grey ("unknown"), never a stale green. */
export const LIGHT_BG = { green: "bg-ok", orange: "bg-warn", red: "bg-danger", unknown: "bg-line" };
export const LIGHT_NAME = { green: ["Hidup", "Live"], orange: ["Siaga", "Standby"], red: ["Tidak hidup", "Unlive"], unknown: ["Belum diketahui", "Unknown"] };
export const STALE_MS = 13 * 3600 * 1000;      // the health run refreshes the lights every six hours

/** { light: "green" | "orange" | "red" | "unknown", why: string } for one tab of Isu semasa. */
export function lightOf(setting, section, nowMs = Date.now()) {
  const lights = setting && setting.lights;
  const one = lights && lights[section];
  if (!one || !LIGHT_BG[one.light]) return { light: "unknown", why: "no reading yet" };
  const at = Date.parse(setting.at);
  if (Number.isFinite(at) && nowMs - at > STALE_MS) {
    return { light: "unknown", why: `the watchdog has not updated for ${Math.floor((nowMs - at) / 3600000)} h` };
  }
  return { light: one.light, why: String(one.why || "") };
}

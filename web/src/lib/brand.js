import { currentLang } from "./i18n";
/* Defaults mirror supabase/005_studio.sql; the live values come from semasa_settings.brand. */
export const DEFAULT_BRAND = {
  regulab: {
    name: "ws.regulab", website: "www.kkmhalalconsultant.com", handle: "@ws.regulab",
    slots: ["08:00", "13:00", "21:00"],
    schedule: { 0: ["halal_my", "fatwa"], 1: ["kosmetik", "sains_kosmetik"], 2: ["halal_my", "fatwa"],
      3: ["kosmetik", "kajian_kes"], 4: ["farmaseutikal", "makanan"], 5: ["kosmetik", "sains_kosmetik"],
      6: ["farmaseutikal", "makanan"] },
    domains: { kosmetik: "Cosmetics (NPRA)", makanan: "Food & beverage (FSQD/BKKM)", halal_my: "Halal Malaysia (JAKIM/JAIN)",
      farmaseutikal: "Pharmaceuticals & supplements (NPRA/DCA)", fatwa: "Fatwa (MKI / State Muftis)",
      kajian_kes: "Case studies", sains_kosmetik: "Cosmetic science (latest publications)" },
  },
  linkedin: {
    name: "Ts. ChM Muhammad Ridzuan", slots: ["06:00", "19:00"], days: [0, 1, 2, 3, 4, 5, 6],
    angles: { A: "Regulatory change", B: "Halal", C: "WTO TBT notification", D: "Regulation × mechanism",
      E: "Case study", F: "Cosmetic science (new paper)", G: "Medicine or dermatology in plain English" },
  },
};

export const STREAMS = [["regulab", "ws.regulab (FB · IG · Threads)"], ["linkedin", "LinkedIn (Wan)"]];
export const DAY_NAMES = ["Ahad", "Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu"];
const DAY_NAMES_EN = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
/** Weekday names (0 = Sunday) in the page's language. */
export const dayNames = () => (currentLang() === "en" ? DAY_NAMES_EN : DAY_NAMES);

export function brandOf(settings) {
  const b = (settings && settings.brand) || {};
  return {
    regulab: { ...DEFAULT_BRAND.regulab, ...(b.regulab || {}) },
    linkedin: { ...DEFAULT_BRAND.linkedin, ...(b.linkedin || {}) },
  };
}

/** Headline category → the ws.regulab domain it most likely belongs to. */
export const CATEGORY_TO_DOMAIN = { kosmetik: "kosmetik", halal: "halal_my", makanan: "makanan",
  farmaseutikal: "farmaseutikal", kesihatan: "farmaseutikal" };

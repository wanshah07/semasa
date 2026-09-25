import { currentLang, tr } from "./i18n";

export const CATEGORY_LABEL = {
  kosmetik: "Kosmetik", halal: "Halal", makanan: "Makanan", farmaseutikal: "Farmaseutikal",
  kesihatan: "Kesihatan", ekonomi: "Ekonomi", politik: "Politik", jenayah: "Jenayah", sosial: "Sosial",
  teknologi: "Teknologi", hiburan: "Hiburan", sukan: "Sukan", pendidikan: "Pendidikan",
  alam_sekitar: "Alam sekitar", lain: "Lain-lain",
};
export const CATEGORIES = Object.keys(CATEGORY_LABEL);
const CATEGORY_LABEL_EN = {
  kosmetik: "Cosmetics", halal: "Halal", makanan: "Food", farmaseutikal: "Pharmaceuticals",
  kesihatan: "Health", ekonomi: "Economy", politik: "Politics", jenayah: "Crime", sosial: "Society",
  teknologi: "Technology", hiburan: "Entertainment", sukan: "Sport", pendidikan: "Education",
  alam_sekitar: "Environment", lain: "Other",
};
/** A scraped headline's category, in the page's language. */
export const categoryLabel = (key) => (currentLang() === "en" ? CATEGORY_LABEL_EN[key] : CATEGORY_LABEL[key]) || key;

/** "3 min", "2 j", "5 hari" (or "2 h", "5 d") — short, for a card corner, in the page's language. */
export function timeAgo(iso, now = Date.now()) {
  if (!iso) return "";
  const s = Math.max(0, (now - new Date(iso).getTime()) / 1000);
  if (s < 60) return tr("baru sahaja", "just now");
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  if (s < 86400) return `${Math.floor(s / 3600)} ${tr("j", "h")}`;
  return `${Math.floor(s / 86400)} ${tr("hari", "d")}`;
}

/** Malaysia clock for tooltips and the run stamp. */
export function stampMYT(iso) {
  if (!iso) return "";
  return new Intl.DateTimeFormat(currentLang() === "en" ? "en-GB" : "ms-MY", {
    timeZone: "Asia/Kuala_Lumpur", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(new Date(iso)) + " MYT";
}

export function hostOf(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return ""; }
}

export function bytesText(n) {
  if (!n && n !== 0) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}

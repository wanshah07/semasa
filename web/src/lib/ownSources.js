/* Wan's own sources (supabase/024): Reddit, YouTube, the OneDrive reference folders and MYRA's sheet. Each is a tab in the
   Isu semasa row, over the same semasa_watch rows; the sweep that fills them is backend/semasa/intake.py. */
export const OWN_SECTIONS = ["reddit", "youtube", "folder", "myra"];

/** The address a card can open: a web link only. A file in OneDrive opens by its own web address, a MYRA finding by its
    source link when it has one; onedrive:// and myra:// are keys, not addresses. */
export function linkOf(r) {
  const raw = r.raw || {};
  const pick = [r.url, raw.web_url, raw.link].find((u) => /^https?:\/\//i.test(String(u || "")));
  return pick || null;
}

/** One line of what the platform or the file actually said (never a number the source did not return). */
export function ownLine(r, t) {
  const raw = r.raw || {};
  if (r.section === "reddit" || r.section === "youtube") return raw.metrics || "";
  if (r.section === "folder") {
    return [raw.urgent_for ? t("Segera untuk {d}", "Urgent for {d}", { d: raw.urgent_for }) : "", raw.cite ? t("Rujukan: {c}", "Reference: {c}", { c: raw.cite }) : "",
      raw.matrix && raw.citation ? t("Petikan: {c}", "Citation: {c}", { c: raw.citation }) : ""].filter(Boolean).join(" · ");
  }
  if (r.section === "myra") {
    return [raw.ref_no ? t("Rujukan: {r}", "Ref: {r}", { r: raw.ref_no }) : "", raw.markets,
      raw.link_shared ? t("pautan dikongsi oleh beberapa penemuan", "link shared by several findings") : ""].filter(Boolean).join(" · ");
  }
  return "";
}

/** What the last run of the own-sources sweep said, in the shape the segment header reads. */
export function ownSummary(section, s) {
  const rep = (s && s.report) || {};
  const c = rep.community || {};
  const n = section === "reddit" || section === "youtube" ? (c.shown || {})[section] : section === "folder" ? (rep.folders || {}).angles : (rep.myra || {}).new;
  const part = section === "folder" ? "folders" : section === "myra" ? "myra" : "community";
  const failing = [];
  if (rep[part] && rep[part].ok === false) failing.push({ name: part, error: rep[part].error });
  if (section === "youtube" && c.youtube_error) failing.push({ name: "YouTube", error: c.youtube_error === "quota" ? "kuota carian YouTube habis hari ini / the YouTube search quota is used up for today" : c.youtube_error });
  if (section === "reddit" && c.reddit_error) failing.push({ name: "Reddit", error: c.reddit_error });
  return { new: n ?? 0, failing, last: s && s.last_run };
}

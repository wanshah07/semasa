/* "Rebuild in Canva" (Wan, 4 Oct 2026: "to have choice render or rebuild in canva"). Semasa draws a card, a poster or a
   carousel itself, free and in seconds (web/src/lib/cards/studio.js). The other choice is to hand the same words, size
   and look to Canva and have the design rebuilt there as live, editable Canva text and shapes: for a client who wants
   to move things about, or a layout this renderer does not draw.

   Canva cannot be called from this page (its connector is signed in on a Claude session, not here), so the hand-off is a
   brief: everything a Claude chat with the Canva connector needs to rebuild the design without asking anything, and the
   rendered pictures as the reference to match. Pure text in, text out; nothing here touches the network. */
import { PALETTES, templateLabel } from "./cards/studio.js";

const FACES = {
  grid: "Poppins ExtraBold for the headline (one word in the accent colour), Instrument Sans for the supporting lines, JetBrains Mono for the small source line, Caveat for sticky notes",
  era: "Poppins ExtraBold for the headline with a yellow highlighter stroke behind it, Instrument Sans for body text, Caveat for notes, JetBrains Mono for the source line",
  photo: "Poppins ExtraBold in white for the headline, Instrument Sans for body text, JetBrains Mono for the source line; a dark gradient over the photograph so the words read",
};
const LOOK_NAME = { grid: "Grid", era: "Info ERA", photo: "Photo", classic: "Semasa" };

const hex = (o) => Object.entries(o).filter(([, v]) => /^#[0-9a-f]{6}$/i.test(String(v))).map(([k, v]) => `${k} ${v}`).join(" · ");

/** A slide as the lines of the brief. Empty fields are left out, so nothing is asked for that was never written. */
export function slideLines(s, i, n) {
  const pts = (Array.isArray(s.points) ? s.points : String(s.points || "").split("\n")).map((x) => String(x).trim()).filter(Boolean);
  const kind = i === 0 && n > 1 ? "cover" : i === n - 1 && n > 1 ? "closing slide" : n > 1 ? `slide ${i + 1}` : "single card";
  const tpl = s.template ? ` · design ${templateLabel(s.template)}` : "";
  const out = [`Page ${i + 1} (${kind}${tpl})`];
  const put = (label, v) => { if (String(v || "").trim()) out.push(`  ${label}: ${String(v).trim()}`); };
  put("Eyebrow", s.eyebrow);
  put("Headline", s.title);
  put("Supporting line", s.lead);
  pts.forEach((p, j) => out.push(`  Point ${j + 1}: ${p}`));
  put("Note", s.note);
  put("Chip", s.chip);
  put("Source line", s.footnote);
  return out.join("\n");
}

/** The whole brief. `slides` are the stored slides ({title, points, lead, ...}); `urls` the drawn pictures, if any. */
export function canvaBrief({ slides = [], urls = [], stream = "regulab", size = [1080, 1080], look = "classic", citation = "",
  eyebrow = "", sizeName = "", kind = "carousel" }) {
  const n = slides.length;
  const li = stream === "linkedin";
  const fam = PALETTES[look];
  const lines = [
    `Rebuild this ${kind === "carousel" && n > 1 ? "carousel" : kind === "poster" ? "poster" : "card"} in Canva as an editable design, with the Canva connector. ` +
      `One Canva page per slide, ${n} page${n === 1 ? "" : "s"}.`,
    "",
    `Size: ${size[0]}×${size[1]} px${sizeName ? ` (${sizeName})` : ""}. Channel: ${li ? "LinkedIn (a named chemist writing to peers, English)" : "ws.regulab (Facebook, Instagram, Threads, Bahasa Malaysia mix)"}.`,
    `Look to match: ${LOOK_NAME[look] || "Semasa"}.`,
  ];
  if (fam) lines.push(`Colours: ${hex(fam)}.`);
  if (FACES[look]) lines.push(`Type: ${FACES[look]}.`);
  lines.push("");
  if (urls.length) {
    lines.push("Reference: Semasa's own drawing of each page. Match its layout, spacing and mood, but rebuild every word and shape as live, editable Canva elements, not as a flattened picture:");
    urls.forEach((u, i) => lines.push(`  Page ${i + 1}: ${u}`));
    lines.push("");
  }
  lines.push("The words, exactly as written. Add nothing, drop nothing, change no number, name or reference. A word between *asterisks* "
    + "is the one drawn in the accent colour: colour it, and leave the asterisks out:");
  slides.forEach((s, i) => { lines.push(slideLines({ ...s, eyebrow: s.eyebrow || eyebrow }, i, n)); });
  if (citation.trim() && !slides.some((s) => String(s.footnote || "").trim())) lines.push("", `Source line, small, on the last page: ${citation.trim()}`);
  lines.push(
    "",
    "Rules that hold in Canva too:",
    "  - No call to action and no claim of your own. The words above are the whole design.",
    li ? "  - LinkedIn: no ws.regulab logo, name, handle or website anywhere on any page."
      : "  - ws.regulab: the brand logo and the website only in the footer. The website appears nowhere else.",
    "  - A mark of a regulator (NPRA, JAKIM, EU) is never drawn as if it endorsed the post; name the instrument in words.",
    "  - Keep the text inside a 72 px margin and out of the bottom 150 px, where the source line sits.",
    "",
    "When it is done, give me the Canva design link, and export every page as PNG at the size above.",
  );
  return lines.join("\n");
}

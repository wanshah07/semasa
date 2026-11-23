import assert from "node:assert/strict";
import { writtenCap, fitPoints, limitSlides } from "./src/lib/limitSlides.js";

let n = 0; const ok = (c, m) => { assert.ok(c, m); n += 1; };
const set = (k) => [{ title: "Tajuk utama", points: [] },
  ...Array.from({ length: k - 2 }, (_, i) => ({ title: `Fakta nombor ${i + 1}`, lead: "Satu ayat sokongan yang pendek.", points: [] })),
  { title: "Penutup yang jelas", lead: "Satu baris akhir.", points: [] }];
const words = (list) => list.flatMap((s) => [s.title, s.lead, ...(s.points || []), s.note]).filter(Boolean).join(" ").replace(/[.;:]/g, "").split(/\s+/).map((w) => w.toLowerCase()).sort().join(" ");

ok(writtenCap("regulab") === 7 && writtenCap("linkedin") === 9, "7 written for ws.regulab, 9 for LinkedIn");
const r = limitSlides(set(16), 7);
ok(r.slides.length === 7 && r.joined === 9, `16 slides come down to 7 (${r.slides.length}, ${r.joined})`);
ok(r.slides[0].title === "Tajuk utama" && r.slides.at(-1).title === "Penutup yang jelas", "the first and the last slide stay alone");
ok(words(r.slides) === words(set(16)), "every word kept");
ok(r.slides.every((s) => s.points.length <= 5), "at most 5 points on a slide");
ok(limitSlides(set(5), 7).joined === 0, "a short set is left alone");
// a verse is never folded in
const withAyat = set(10); withAyat[3] = { title: "Peringatan", points: [], ayat: "2:168" };
ok(limitSlides(withAyat, 7).slides.some((s) => s.ayat === "2:168"), "the verse slide stays on its own");
// too dense: not joined
const long = "Ayat yang sangat panjang tentang peraturan dan notifikasi ".repeat(8);
ok(limitSlides([...set(10).slice(0, 1), ...Array.from({ length: 8 }, (_, i) => ({ title: `F${i}`, lead: long, points: [] })), set(2)[1]], 7).joined === 0, "a join too dense to read is refused");
ok(fitPoints(["aa", "b", "c", "dddd", "e", "f", "g"], 5).length === 5, "points merged to the limit");
ok(words([{ title: "", points: fitPoints(["un", "dua", "tiga", "empat", "lima", "enam", "tujuh"], 5) }]) === words([{ title: "", points: ["un", "dua", "tiga", "empat", "lima", "enam", "tujuh"] }]), "no word lost in merged points");
console.log(`limitSlides: ${n} checks passed`);

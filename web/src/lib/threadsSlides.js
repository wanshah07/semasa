/* The Threads-style slide design (Wan, 9 Nov 2026): 2 to 5 pages, each a short piece of text with a picture under it (or beside it).
   The worker draws it (backend/semasa/threads_slides.py, Pillow, no AI); this file holds what the page needs to know BEFORE a job
   is queued: that the design is offered, what it asks of the words and the size, and which `design` the job's meta carries.
   Pure rules with no imports, so web/threadsSlides.test.mjs runs them under Node. The numbers are the worker's own
   (threads_slides.py MIN_PAGES, MAX_PAGES, MAX_POINTS, MAX_PAGE_CHARS, MAX_HOOK_WORDS, MIN_SIDE, MAX_RATIO): the test reads the
   Python file and fails if the two differ. */
export const THREADS = { minPages: 2, maxPages: 5, maxPoints: 3, maxChars: 420, maxHookWords: 16, minSide: 600, maxRatio: 2 };

/** The picker's entry. It sits beside Studio's looks but is not one of them (STUDIO_LOOKS, cards/studio.js, stay as they were):
 *  the worker draws it with its own code, and only a job whose meta says design "threads" is drawn this way. */
export const THREADS_LOOK = {
  k: "threads", bm: "Threads", en: "Threads",
  hintBm: "2 hingga 5 halaman: teks pendek dengan gambar di bawahnya, nombor halaman dan titik bersambung. Tiada AI.",
  hintEn: "2 to 5 pages: a short piece of text with a picture under it, a page number and connected dots. No AI.",
};

export const isThreads = (look) => look === "threads";

/** The `design` a job's meta carries: Threads-style when that look is chosen, else the kind the page already had (poster, card,
 *  carousel). Every other look leaves the job exactly as it was. */
export const jobDesign = (look, design) => (isThreads(look) ? "threads" : design);

/** The look an idea is sent with: a Threads-style set is a carousel, so any other format falls back to `fallback`. */
export const ideaLook = (look, format, fallback) => (isThreads(look) && format !== "carousel" ? fallback : look);

const plain = (s) => String(s || "").replace(/\*([^*\n]+)\*/g, "$1");

/** What the worker would refuse, as {n, bm, en} (n = the page, or 0 for the whole set), in the worker's own order. `slides` are
 *  [{title, points[]}]; `size` is [width, height] or null (the stream's own size, which this design always holds). */
export function threadsProblems(slides, size = null) {
  const out = [];
  const list = Array.isArray(slides) ? slides : [];
  const { minPages, maxPages, maxPoints, maxChars, maxHookWords, minSide, maxRatio } = THREADS;
  if (list.length < minPages || list.length > maxPages) {
    out.push({ n: 0, bm: `Set Threads mesti ${minPages} hingga ${maxPages} halaman, tetapi ${list.length} diberi.`,
      en: `A Threads-style set must have ${minPages} to ${maxPages} pages, but ${list.length} were given.` });
  }
  if (Array.isArray(size)) {
    const [w, h] = size;
    if (Math.min(w, h) < minSide || Math.max(w, h) > maxRatio * Math.min(w, h)) {
      out.push({ n: 0, bm: `Reka bentuk ini perlukan sisi pendek sekurang-kurangnya ${minSide}px dan nisbah tidak lebih ${maxRatio}:1; ${w}x${h} tidak muat. Pilih petak suapan, potret 4:5 atau cerita.`,
        en: `This design needs a short side of at least ${minSide}px and no more than ${maxRatio}:1; ${w}x${h} does not fit. Pick a feed square, a 4:5 portrait or a story.` });
    }
  }
  list.forEach((s, i) => {
    const n = i + 1, title = String(s?.title || ""), points = (s?.points || []).map(String);
    if (n === 1 && !title.trim()) out.push({ n, bm: "Halaman 1 ialah kulit dan perlukan tajuk: itulah hook.", en: "Page 1 is the cover and needs a headline: that is the hook." });
    const hook = plain(title).split(/\s+/).filter(Boolean).length;
    if (n === 1 && hook > maxHookWords) out.push({ n, bm: `Halaman 1: hook ialah ${hook} perkataan, paling banyak ${maxHookWords}.`, en: `Page 1: the hook is ${hook} words, at most ${maxHookWords}.` });
    if (points.length > maxPoints) out.push({ n, bm: `Halaman ${n}: ${points.length} poin, paling banyak ${maxPoints}.`, en: `Page ${n}: ${points.length} points, at most ${maxPoints}.` });
    if (title.length + points.reduce((a, p) => a + p.length, 0) > maxChars) {
      out.push({ n, bm: `Halaman ${n}: terlalu panjang untuk halaman Threads (paling banyak ${maxChars} aksara). Pendekkan atau pecahkan kepada dua halaman.`,
        en: `Page ${n}: too long for a Threads-style page (at most ${maxChars} characters). Shorten it or split it into two pages.` });
    }
  });
  return out;
}

/** Sample words for the preview while the real ones are not written: a cover, then one page. */
export function threadsSample(stream) {
  const en = stream === "linkedin";
  return [
    { title: en ? "Your *hook* goes here" : "Hook *anda* di sini", points: [] },
    { title: en ? "One idea per page" : "Satu idea satu halaman", points: [en ? "Short, cited, with a picture under it." : "Ringkas, bersumber, dengan gambar di bawahnya."] },
    { title: en ? "Remember this" : "Ingat ini", points: [en ? "The takeaway, never a call to action." : "Kesimpulan, bukan seruan tindakan."] },
  ];
}

import { useEffect, useMemo, useState } from "react";
import { artFor, artIndex, dataUrlOf } from "./slideArt";

const CACHE = new Map();                                    // address → {cut, page} data addresses, kept for the session

/** The slides with their own drawings from the post's slide jobs: `art_url` (the cut-out) and `art_page` (the whole page, for Diari).
    A slide without a drawing is returned as it was. Nothing is saved; this is only for the pictures in the picker. */
export default function useSlideArt(slides, jobs) {
  const [got, setGot] = useState({});                       // slide index → {cut, page}
  const jobKey = useMemo(() => [...artIndex(jobs).entries()].map(([k, u]) => `${k}=${u}`).join("|"), [jobs]);
  const key = JSON.stringify([slides.map((s) => [s?.title, s?.lead, s?.points, s?.note]), jobKey]);
  useEffect(() => {
    let live = true;
    if (!jobKey) { setGot({}); return undefined; }
    (async () => {
      const urls = await artFor(slides, jobs);
      const out = {};
      for (let i = 0; i < urls.length; i++) {
        const { cut, page } = urls[i], from = page || cut;      // the whole picture first (the worker draws it for every look now)
        if (!from) continue;
        if (!CACHE.has(from)) {
          // the picture as the worker drew it, on every look (Wan, 23 Nov 2026: no cut-out): one blob address per drawing
          const data = await dataUrlOf(from);
          if (!data) continue;
          CACHE.set(from, { cut: data, page: data });
        }
        out[i] = CACHE.get(from);
      }
      if (live) setGot(out);
    })();
    return () => { live = false; };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return useMemo(() => slides.map((s, i) => (got[i] ? { ...s, art_url: got[i].cut, art_page: got[i].page } : s)), [slides, got]);
}

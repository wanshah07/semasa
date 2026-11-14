import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronLeft, ChevronRight, Download, X } from "lucide-react";
import { useLang } from "../lib/i18n";

/* A picture opened in place (Wan, 3 Oct 2026: "when we click the card, nothing appear, make it popup enough for us to see
   the wording on the card, no need open new tab"). A drawn card is a data: address, and a browser will not open one
   as a page of its own, so the old link to a new tab was a blank page. This is a full-screen viewer over the page:
   Esc or a click outside closes it, the arrow keys (and the buttons) step through the set, and the card fills as much
   of the screen as it can so every word on it can be read.

   It is drawn into document.body, never inside whoever opened it (Wan, 14 Nov 2026: "I cannot overview the slides, and close it").
   The Glass look gives every card a backdrop-filter, and a backdrop-filter makes the card the containing block of anything
   `fixed` inside it: opened from the post editor, the viewer was pinned inside the editor's card, clipped by it, with its
   close button scrolled out of sight and its overlay washing over the editor. Its overlay is also always dark: bg-ink is a
   LIGHT colour under the dark themes, which turned it into a pale veil over a dark card. */

/** The viewer's state: `open(i)` shows picture i of the list. Render <ImageLightbox {...box.props} /> once. */
export function useLightbox(items) {
  const [at, setAt] = useState(null);
  const open = useCallback((i) => setAt(i), []);
  const close = useCallback(() => setAt(null), []);
  return { open, close, props: { items, at, setAt, onClose: close } };
}

/** items: [{url, title?, alt?}] */
export default function ImageLightbox({ items = [], at, setAt, onClose }) {
  const { t } = useLang();
  const n = items.length;
  const shown = at !== null && at >= 0 && at < n ? items[at] : null;
  const step = useCallback((d) => setAt((i) => (i === null ? i : (i + d + n) % n)), [n, setAt]);

  useEffect(() => {
    if (!shown) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight" && n > 1) step(1);
      else if (e.key === "ArrowLeft" && n > 1) step(-1);
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";                 // the page behind must not scroll while a card is read
    return () => { window.removeEventListener("keydown", onKey); document.body.style.overflow = prev; };
  }, [shown, n, step, onClose]);

  if (!shown) return null;
  const label = shown.title || shown.alt || t("Gambar {n}", "Picture {n}", { n: at + 1 });
  return createPortal(
    <div className="fixed inset-0 z-[70] flex flex-col bg-black/85 p-3 text-white sm:p-6" role="dialog" aria-modal="true" aria-label={label}
      onMouseDown={(e) => { e.currentTarget.dataset.down = e.target === e.currentTarget ? "1" : ""; }}
      onClick={(e) => { if (e.target === e.currentTarget && e.currentTarget.dataset.down === "1") onClose(); }}>
      <div className="mb-2 flex items-center gap-3 text-white" onClick={(e) => e.stopPropagation()}>
        <p className="min-w-0 flex-1 truncate text-sm">{n > 1 ? `${at + 1} / ${n} · ` : ""}{label}</p>
        <a href={shown.url} download={`slide-${at + 1}.jpg`} className="inline-flex items-center gap-1 rounded-pill bg-white/15 px-3 py-1.5 text-xs hover:bg-white/25">
          <Download size={13} /> {t("Muat turun", "Download")}</a>
        <button type="button" onClick={onClose} aria-label={t("Tutup", "Close")} className="rounded-full bg-white/15 p-2 hover:bg-white/25"><X size={16} /></button>
      </div>
      <div className="relative flex min-h-0 flex-1 items-center justify-center"
        onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
        {n > 1 && (
          <button type="button" onClick={() => step(-1)} aria-label={t("Sebelum", "Previous")}
            className="absolute left-0 z-10 rounded-full bg-white/20 p-2 text-white hover:bg-white/35"><ChevronLeft size={22} /></button>
        )}
        <img src={shown.url} alt={shown.alt || label} className="max-h-full max-w-full rounded-tile bg-surface object-contain shadow-lift" />
        {n > 1 && (
          <button type="button" onClick={() => step(1)} aria-label={t("Seterusnya", "Next")}
            className="absolute right-0 z-10 rounded-full bg-white/20 p-2 text-white hover:bg-white/35"><ChevronRight size={22} /></button>
        )}
      </div>
    </div>,
    document.body,
  );
}

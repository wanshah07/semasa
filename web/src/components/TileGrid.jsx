import { useState } from "react";
import { AlertTriangle, Clapperboard, Clock, ImageOff, Loader2, Play } from "lucide-react";
import { useLang } from "../lib/i18n";
import { Modal } from "./ui/Field";

/* The compact library every Create page uses (Wan, 11 Oct 2026: "do separate library, make it compact, tile 8 per row"):
   a square tile per item, 3 across on a phone up to 8 across at 1280 px, and a click opens the full card in a dialog. The
   full card is the page's own (retry, delete, post, download), so nothing a card could do is lost by making the grid small.
   `items`: [{ id, src, kind: "image" | "video", label, status, sub }]; `detail(item)` draws the dialog's content. */
export const TILES_PER_ROW = "grid-cols-3 sm:grid-cols-4 md:grid-cols-6 xl:grid-cols-8";

const BADGE = {
  pending: { Icon: Clock, cls: "bg-warn/90 text-white", bm: "Menunggu", en: "Waiting" },
  waiting: { Icon: Clock, cls: "bg-accent/90 text-white", bm: "Beratur", en: "Queued" },
  processing: { Icon: Loader2, cls: "bg-accent/90 text-white", spin: true, bm: "Menjana", en: "Generating" },
  working: { Icon: Loader2, cls: "bg-accent/90 text-white", spin: true, bm: "Menjana", en: "Generating" },
  error: { Icon: AlertTriangle, cls: "bg-danger/90 text-white", bm: "Gagal", en: "Failed" },
};

function Thumb({ item }) {
  if (!item.src) {
    const Icon = item.kind === "video" ? Clapperboard : ImageOff;
    return <span className="grid h-full w-full place-items-center bg-surface-2 text-muted"><Icon size={20} /></span>;
  }
  if (item.kind === "video") {
    return (
      <>
        <video src={item.src.includes("#") ? item.src : `${item.src}#t=0.1`} muted playsInline preload="metadata" className="h-full w-full bg-black object-cover" />
        <span className="absolute right-1.5 top-1.5 grid h-5 w-5 place-items-center rounded-full bg-ink/70 text-bg"><Play size={10} /></span>
      </>
    );
  }
  return <img src={item.src} alt="" loading="lazy" className="h-full w-full object-cover" onError={(e) => { e.currentTarget.style.visibility = "hidden"; }} />;
}

export default function TileGrid({ items, detail, title, empty }) {
  const { t, lang } = useLang();
  const [openId, setOpenId] = useState(null);
  const open = items.find((x) => x.id === openId) || null;
  if (!items.length) return <p className="rounded-card border border-dashed border-line p-10 text-center text-sm text-muted">{empty}</p>;
  return (
    <>
      <ul className={`grid gap-3 ${TILES_PER_ROW}`} data-tile-grid>
        {items.map((it) => {
          const b = BADGE[it.status];
          return (
            <li key={it.id} className="min-w-0">
              <button type="button" onClick={() => setOpenId(it.id)} title={it.label} data-tile={it.id}
                className="group relative block aspect-square w-full overflow-hidden rounded-tile border border-line bg-surface-2 transition hover:shadow-card focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">
                <Thumb item={it} />
                {b && <span className={`absolute left-1.5 top-1.5 inline-flex items-center gap-1 rounded-pill px-1.5 py-0.5 text-[10px] font-semibold ${b.cls}`}>
                  <b.Icon size={10} className={b.spin ? "animate-spin" : ""} /> {lang === "en" ? b.en : b.bm}</span>}
              </button>
              <p className="mt-1 truncate text-[11px] text-ink">{it.label}</p>
              {it.sub && <p className="truncate text-[10px] text-muted">{it.sub}</p>}
            </li>
          );
        })}
      </ul>
      <Modal open={!!open} onClose={() => setOpenId(null)} title={open?.label || title || t("Butiran", "Details")} wide>
        {open && detail(open)}
      </Modal>
    </>
  );
}

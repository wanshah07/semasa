import { useLang } from "../lib/i18n";
import { segmentOf } from "../lib/tabs";

/* The pages inside the segment that is open, as one row of tabs above the page (Wan, 11 Oct 2026: segments in the sidebar,
   the pages of a segment beside each other). The sidebar shows segments; a page keeps its own address (#post, #office…), so
   a link or a Back press lands on the same page as before. A segment with one page shows no bar. */
export default function SegmentBar({ tab, setTab }) {
  const { t } = useLang();
  const seg = segmentOf(t, tab);
  if (!seg || seg.pages.length < 2) return null;
  return (
    <nav role="tablist" aria-label={seg.label} data-segment-bar={seg.id}
      className="mx-auto flex max-w-page gap-1.5 overflow-x-auto px-4 pt-5 sm:px-6">
      <span className="mr-1 hidden shrink-0 self-center text-[11px] font-semibold uppercase tracking-wide text-muted sm:inline">{seg.label}</span>
      {seg.pages.map(({ id, label, icon: Icon }) => (
        <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
          className={`flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-pill px-3.5 py-1.5 text-sm font-medium transition ${
            tab === id ? "bg-ink text-bg" : "bg-surface-2 text-muted hover:text-ink"}`}>
          <Icon size={14} /> {label}
        </button>
      ))}
    </nav>
  );
}

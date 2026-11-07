import { useLang } from "../lib/i18n";
import { segmentOf } from "../lib/tabs";
import { AnimatedTabs } from "@/components/ui/animated-tabs";

/* The pages inside the segment that is open, as one row of tabs above the page (Wan, 11 Oct 2026: segments in the sidebar,
   the pages of a segment beside each other), with the sliding pill of AnimatedTabs (Wan, 7 Nov 2026). The sidebar shows
   segments; a page keeps its own address (#post, #office…), so a link or a Back press lands on the same page as before. A
   segment with one page shows no bar. */
export default function SegmentBar({ tab, setTab }) {
  const { t } = useLang();
  const seg = segmentOf(t, tab);
  if (!seg || seg.pages.length < 2) return null;
  return (
    <nav data-segment-bar={seg.id} aria-label={seg.label} className="mx-auto flex max-w-page items-center gap-2 overflow-x-auto px-4 pt-5 sm:px-6">
      <span className="mr-1 hidden shrink-0 text-[11px] font-semibold uppercase tracking-wide text-muted sm:inline">{seg.label}</span>
      <AnimatedTabs className="w-auto max-w-none" hideContent value={tab} onChange={setTab} aria-label={seg.label}
        tabs={seg.pages.map(({ id, label, icon: Icon }) => ({ id, label: <><Icon size={14} /> {label}</> }))} />
    </nav>
  );
}

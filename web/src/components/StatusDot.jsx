import { useLang } from "../lib/i18n";
import { STATE_NAME, detailText, rowState } from "../lib/slotCheck";

const DOT = { passed: "bg-ok", queued: "bg-queue", failed: "bg-danger", waiting: "bg-wait", off: "bg-line" };

/* The post's colour in a list (Wan, 11 Nov 2026: "add color circle every row to show the status post"): green passed, yellow queued,
   red failed, magenta waiting for approval, grey for a rejected post. The words are in the tooltip and the screen-reader name,
   so the colour is never the only way to read it. The same rules as the Slot check tab (lib/slotCheck.js). */
export default function StatusDot({ post, className = "" }) {
  const { t } = useLang();
  const r = rowState(post);
  const name = t(STATE_NAME[r.state][0], STATE_NAME[r.state][1]);
  const why = detailText(r.detail, t);
  const label = why ? `${name}: ${why}` : name;
  return <span role="img" aria-label={label} title={label} data-state={r.state}
    className={`inline-block h-3 w-3 shrink-0 rounded-full ${DOT[r.state]} ${className}`} />;
}

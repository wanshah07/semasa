import { useEffect, useMemo, useState } from "react";
import { Check, Clock, ExternalLink, Hourglass, RefreshCw, X } from "lucide-react";
import { useLang } from "../lib/i18n";
import { myt } from "../lib/slots";
import { STATES, detailText, slotRows, tally } from "../lib/slotCheck";
import { fmtDate } from "../lib/billing";
import Button from "./ui/Button";
import Card from "./ui/Card";

// four colours, and a word and an icon beside each, so the colour is never the only way to read a state
const LOOK = {
  passed: { Icon: Check, dot: "bg-ok", box: "border-ok/40 bg-ok/10 text-ok", name: ["Berjaya", "Passed"] },
  queued: { Icon: Clock, dot: "bg-queue", box: "border-queue/60 bg-queue/15 text-ink", name: ["Dalam barisan", "Queued"] },
  failed: { Icon: X, dot: "bg-danger", box: "border-danger/40 bg-danger/10 text-danger", name: ["Gagal", "Failed"] },
  waiting: { Icon: Hourglass, dot: "bg-wait", box: "border-wait/40 bg-wait/10 text-wait", name: ["Tunggu kelulusan", "Waiting for approval"] },
};
const RANGES = [["today", ["Hari ini", "Today"], 0], ["week", ["7 hari", "7 days"], 7], ["all", ["Semua akan datang", "All upcoming"], 400]];
const CHANNEL = { instagram: "Instagram", facebook: "Facebook", threads: "Threads", tiktok: "TikTok", linkedin: "LinkedIn" };

/* The post-slot check (Wan, 11 Nov 2026). One line per post, one coloured pill per channel: green passed (the platform has it),
   yellow queued (handed to Zernio, or approved and waiting to be), red failed (refused, stuck, missed or blocked, with the reason),
   magenta waiting for your approval. It reads the posts the page already holds, which update live; the worker that fills them in
   (backend/semasa/slotcheck.py) reads Zernio back 25 minutes after each slot and tells you on Telegram about a failure. */
export default function SlotCheck({ posts, onOpen, onReload }) {
  const { t } = useLang();
  const [range, setRange] = useState("week");
  const [only, setOnly] = useState(null);
  const [streamF, setStreamF] = useState("all");
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const id = window.setInterval(() => setNow(Date.now()), 60_000); return () => window.clearInterval(id); }, []);

  const days = (RANGES.find(([v]) => v === range) || RANGES[1])[2];
  const all = useMemo(() => slotRows(posts, { from: myt(now).date, days, now })
    .filter((r) => streamF === "all" || (r.post.stream || "regulab") === streamF), [posts, days, now, streamF]);
  const counts = tally(all);
  const rows = only ? all.filter((r) => r.state === only) : all;
  const label = (pair) => t(pair[0], pair[1]);

  return (
    <section className="mt-6" aria-label={t("Semakan slot", "Post-slot check")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-2 text-xs">
          {RANGES.map(([v, name]) => (
            <button key={v} type="button" aria-pressed={range === v} onClick={() => setRange(v)}
              className={`min-h-[44px] rounded-pill px-3 py-1.5 lg:min-h-0 ${range === v ? "bg-ink text-bg" : "bg-surface-2 text-muted"}`}>
              {label(name)}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <select value={streamF} onChange={(e) => setStreamF(e.target.value)} aria-label={t("Aliran", "Stream")}
            className="rounded-pill border border-line bg-surface px-3 py-1.5 text-xs">
            <option value="all">{t("Semua", "All")}</option><option value="regulab">ws.regulab</option><option value="linkedin">LinkedIn</option>
          </select>
          <Button size="sm" variant="ghost" onClick={onReload} aria-label={t("Muat semula", "Reload")}><RefreshCw size={13} /></Button>
        </div>
      </div>

      {/* the four colours, doubling as filters */}
      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {STATES.map((s) => {
          const L = LOOK[s];
          const active = only === s;
          return (
            <button key={s} type="button" aria-pressed={active} onClick={() => setOnly(active ? null : s)}
              className={`flex min-h-[56px] items-center gap-3 rounded-tile border px-3 py-2 text-left transition ${L.box} ${active ? "ring-2 ring-ink/30" : ""}`}>
              <L.Icon size={18} className="shrink-0" aria-hidden="true" />
              <span className="min-w-0">
                <span className="block text-2xl font-semibold leading-none">{counts[s]}</span>
                <span className="mt-1 block text-[12px] leading-tight">{label(L.name)}</span>
              </span>
            </button>
          );
        })}
      </div>

      {!rows.length && (
        <p className="mt-4 rounded-card border border-dashed border-line p-10 text-center text-sm text-muted">
          {only ? t("Tiada post dalam keadaan ini.", "No posts in this state.") : t("Tiada post dalam tempoh ini.", "No posts in this range.")}
        </p>
      )}

      <ul className="mt-4 space-y-2">
        {rows.map((r) => {
          const p = r.post;
          const L = LOOK[r.state] || LOOK.queued;
          const gone = r.due < now;
          return (
            <li key={p.id}>
              <Card className="p-3">
                <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
                  <button type="button" onClick={() => onOpen(p.id)} className="flex min-w-0 flex-1 basis-60 items-start gap-3 text-left">
                    <span className={`mt-1.5 h-3 w-3 shrink-0 rounded-full ${L.dot}`} aria-hidden="true" />
                    <span className="min-w-0">
                      <span className="block text-[12px] text-muted">
                        {fmtDate(p.date)} {p.slot} MYT · {(p.stream || "regulab") === "linkedin" ? "LinkedIn" : "ws.regulab"}
                        {gone ? "" : ` · ${t("belum tiba", "not yet due")}`}
                      </span>
                      <span className="mt-0.5 line-clamp-2 block text-sm font-medium">{p.hook || t("(tiada tajuk)", "(no title)")}</span>
                    </span>
                  </button>
                  <div className="flex flex-wrap gap-2">
                    {r.cells.filter((c) => c.state !== "off").map((c) => {
                      const K = LOOK[c.state];
                      const body = (
                        <>
                          <K.Icon size={13} aria-hidden="true" />
                          <span className="font-medium">{CHANNEL[c.ch] || c.ch}</span>
                          <span className="opacity-80">{label(c.label)}</span>
                          {c.url ? <ExternalLink size={11} aria-hidden="true" /> : null}
                        </>
                      );
                      const cls = `inline-flex min-h-[32px] items-center gap-1.5 rounded-pill border px-2.5 py-1 text-[12px] ${K.box}`;
                      return c.url
                        ? <a key={c.ch} href={c.url} target="_blank" rel="noopener noreferrer" className={cls} title={c.url}>{body}</a>
                        : <span key={c.ch} className={cls} title={detailText(c.detail, t) || undefined}>{body}</span>;
                    })}
                  </div>
                </div>
                {r.cells.filter((c) => c.state === "failed" && c.detail).map((c) => (
                  <p key={c.ch} className="mt-2 rounded-tile bg-danger/10 px-3 py-2 text-[12px] text-danger">
                    <b>{CHANNEL[c.ch] || c.ch}:</b> {detailText(c.detail, t)}
                  </p>
                ))}
              </Card>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

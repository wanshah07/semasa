import { useMemo } from "react";
import { Briefcase, CalendarPlus, Megaphone } from "lucide-react";
import { useLang } from "../lib/i18n";
import { coverage, refOf, slotsOf } from "../lib/slots";

/* The schedule as a map (Wan, 3 Oct 2026: "map schedule so easy to see which slot have been filled, separate between
   ws.regulab and LinkedIn, asingkan this segment visibly"). Two lanes, one under the other, each its own colour and
   heading, four weeks of days in weekday columns, and inside every day one small tile per slot:
     filled (posted / scheduled / approved / draft), empty (dashed: a click writes an idea for that slot), a slot that
     already went by, and a day the stream does not post on. A tile is a button: a filled one opens the post. */

const DAYS = { bm: ["Isn", "Sel", "Rab", "Kha", "Jum", "Sab", "Ahd"], en: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] };
const WEEKS = 4;

/* Each lane has its own fixed colour (not the theme's accent, which the status tiles use): teal for ws.regulab, LinkedIn's own
   blue for LinkedIn, so the two are told apart at a glance whatever theme is on. */
const LANES = {
  regulab: { name: "ws.regulab", sub: ["Facebook · Instagram · Threads melalui Buffer", "Facebook · Instagram · Threads through Buffer"], Icon: Megaphone,
    head: "bg-[#0F766E] text-white", bar: "bg-[#0F766E]", text: "text-[#0F766E]", edge: "border-[#0F766E]", ring: "ring-[#0F766E]", tint: "bg-[#0F766E]/[0.04]" },
  linkedin: { name: "LinkedIn", sub: ["Profil peribadi Wan melalui Composio", "Wan's own profile through Composio"], Icon: Briefcase,
    head: "bg-[#0A66C2] text-white", bar: "bg-[#0A66C2]", text: "text-[#0A66C2]", edge: "border-[#0A66C2]", ring: "ring-[#0A66C2]", tint: "bg-[#0A66C2]/[0.04]" },
};
const URGENT_DAYS = 3;                                    // an empty slot this close is a red flag; further out it is only room

const TILE = {
  posted: { cls: "bg-ink text-bg", mark: "✓", bm: "sudah keluar", en: "posted" },
  scheduled: { cls: "bg-accent/20 text-accent border border-accent/50", mark: "●", bm: "dijadualkan", en: "scheduled" },
  approved: { cls: "bg-ok/20 text-ok border border-ok/50", mark: "◐", bm: "diluluskan", en: "approved" },
  draft: { cls: "bg-warn/15 text-warn border border-warn/50", mark: "✎", bm: "draf", en: "draft" },
};

export const LEGEND = ["posted", "scheduled", "approved", "draft"];

function Tile({ c, d, stream, brand, onOpen, onNewIdea, t, lang, urgent }) {
  const p = c.posts[0];
  if (p) {
    const tone = TILE[p.status] || TILE.draft;
    const ref = refOf(p, brand) || p.id.slice(0, 6);
    return (
      <button type="button" onClick={() => onOpen(p.id)}
        title={`${d.date} ${c.slot} · ${ref} · ${lang === "en" ? tone.en : tone.bm}${p.hook ? ` · ${p.hook}` : ""}`}
        className={`flex w-full items-center justify-between gap-1 rounded px-1 py-0.5 text-left text-[10.5px] leading-tight ${tone.cls} ${c.clash ? "ring-2 ring-danger" : ""}`}>
        <span className="tabular-nums">{c.slot}</span>
        <span aria-hidden="true">{c.clash ? `${c.posts.length}×` : tone.mark}</span>
      </button>
    );
  }
  if (c.gap) {
    return (
      <button type="button" onClick={() => onNewIdea({ stream, date: d.date, slot: c.slot, domain: (d.domains || [])[0] || "" })}
        title={t("Kosong: tulis idea untuk slot ini", "Empty: write an idea for this slot")}
        className={`flex w-full items-center justify-between gap-1 rounded border border-dashed px-1 py-0.5 text-left text-[10.5px] leading-tight hover:border-accent hover:text-accent ${
          urgent ? "border-danger/60 bg-danger/5 text-danger" : "border-line text-muted"}`}>
        <span className="tabular-nums">{c.slot}</span><CalendarPlus size={10} aria-hidden="true" />
      </button>
    );
  }
  return (
    <span className="flex w-full items-center justify-between rounded px-1 py-0.5 text-[10.5px] leading-tight text-muted/70 line-through">
      <span className="tabular-nums">{c.slot}</span></span>
  );
}

function Lane({ stream, posts, brand, onOpen, onNewIdea }) {
  const { t, lang } = useLang();
  const lane = LANES[stream];
  const days = useMemo(() => coverage({ posts, brand, stream, days: WEEKS * 7 }), [posts, brand, stream]);
  const slots = slotsOf(brand, stream);
  const lead = (days[0].dow + 6) % 7;                         // Monday-first columns: blanks before today's weekday
  const cells = [...Array.from({ length: lead }, () => null), ...days];
  const upcoming = days.flatMap((d) => (d.posting ? d.cells.filter((c) => !c.past) : []));
  const filled = upcoming.filter((c) => c.posts.length).length;
  const empty = upcoming.filter((c) => c.gap).length;
  const soon = days.slice(0, URGENT_DAYS).flatMap((d) => d.cells.filter((c) => c.gap)).length;
  const next = days.flatMap((d) => d.cells.filter((c) => c.gap).map((c) => ({ d, c })))[0];
  const pct = upcoming.length ? Math.round((filled / upcoming.length) * 100) : 0;
  const names = DAYS[lang === "en" ? "en" : "bm"];
  const today = days[0].date;

  return (
    <section className={`overflow-hidden rounded-card border-2 ${lane.edge} ${lane.tint}`} aria-label={lane.name}>
      <header className={`flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2.5 ${lane.head}`}>
        <span className="inline-flex items-center gap-1.5 text-base font-semibold"><lane.Icon size={16} /> {lane.name}</span>
        <span className="text-[11px] opacity-90">{t(lane.sub[0], lane.sub[1])} · {slots.join(" · ")}</span>
        <span className="ml-auto flex items-center gap-2 text-[12px]">
          <span className="tabular-nums"><b>{filled}</b> / {upcoming.length} {t("slot terisi", "slots filled")}</span>
          <span className="hidden h-2 w-28 overflow-hidden rounded-full bg-white/30 sm:block" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}
            aria-label={t("Slot terisi", "Slots filled")}><span className="block h-full bg-white" style={{ width: `${pct}%` }} /></span>
          <span className="rounded-pill bg-white px-2 py-0.5 font-medium" style={{ color: soon ? "#b42318" : "#067647" }}>
            {soon ? t("{n} kosong dalam {d} hari", "{n} empty in the next {d} days", { n: soon, d: URGENT_DAYS }) : t("{d} hari seterusnya penuh", "next {d} days full", { d: URGENT_DAYS })}</span>
        </span>
      </header>
      {next && (
        <p className="px-3 pb-1 text-[11px] text-muted">{t("Slot kosong seterusnya:", "Next empty slot:")}{" "}
          <button type="button" className="font-medium underline" onClick={() => onNewIdea({ stream, date: next.d.date, slot: next.c.slot, domain: (next.d.domains || [])[0] || "" })}>
            {names[(next.d.dow + 6) % 7]} {next.d.date.slice(8)}/{next.d.date.slice(5, 7)} {next.c.slot}</button></p>
      )}
      <div className="overflow-x-auto px-2 pb-2.5">
        <div className="grid min-w-[34rem] grid-cols-7 gap-1">
          {names.map((n, i) => <span key={n} className={`pb-0.5 text-center text-[10.5px] font-medium ${i >= 5 ? "text-muted/70" : "text-muted"}`}>{n}</span>)}
          {cells.map((d, i) => d === null
            ? <span key={`b${i}`} />
            : (
              <div key={d.date} className={`min-w-0 rounded-tile p-1 ${d.posting ? "bg-surface" : "bg-surface-2/60"} ${d.date === today ? `ring-2 ${lane.ring}` : "border border-line"}`}>
                <p className="mb-0.5 flex items-baseline justify-between text-[10.5px]">
                  <span className={`font-semibold tabular-nums ${d.date === today ? lane.text : ""}`}>{d.date.slice(8)}{d.date.slice(8) === "01" || i === lead ? `/${d.date.slice(5, 7)}` : ""}</span>
                  {!d.posting && <span className="text-muted">{t("rehat", "off")}</span>}
                </p>
                {d.posting ? (
                  <div className="space-y-0.5">
                    {d.cells.map((c) => <Tile key={c.slot} c={c} d={d} stream={stream} brand={brand} onOpen={onOpen} onNewIdea={onNewIdea} t={t} lang={lang}
                      urgent={days.indexOf(d) < URGENT_DAYS} />)}
                    {d.extra.map((p) => (
                      <button key={p.id} type="button" onClick={() => onOpen(p.id)} title={`${p.date} ${p.slot} · ${p.hook || ""}`}
                        className={`flex w-full items-center justify-between rounded px-1 py-0.5 text-left text-[10.5px] ${(TILE[p.status] || TILE.draft).cls}`}>
                        <span className="tabular-nums">{p.slot}</span><span aria-hidden="true">{(TILE[p.status] || TILE.draft).mark}</span></button>
                    ))}
                  </div>
                ) : <p className="py-2 text-center text-[10px] text-muted">{t("tiada post", "no posting")}</p>}
              </div>
            ))}
        </div>
      </div>
    </section>
  );
}

/** Both streams, each in its own lane. */
export default function ScheduleMap({ posts, brand, onOpen, onNewIdea }) {
  const { t, lang } = useLang();
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted" aria-label={t("Petunjuk", "Legend")}>
        <b className="text-ink">{t("Peta jadual · 4 minggu", "Schedule map · 4 weeks")}</b>
        {LEGEND.map((k) => <span key={k} className="inline-flex items-center gap-1"><span className={`inline-block rounded px-1 text-[10px] ${TILE[k].cls}`}>{TILE[k].mark}</span> {lang === "en" ? TILE[k].en : TILE[k].bm}</span>)}
        <span className="inline-flex items-center gap-1"><span className="inline-block rounded border border-dashed border-line px-1 text-[10px]">+</span> {t("kosong (klik untuk tulis idea; merah = dalam 3 hari)", "empty (click to write an idea; red = within 3 days)")}</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block rounded px-1 text-[10px] text-muted/70 line-through">08:00</span> {t("sudah lepas", "already past")}</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block rounded ring-2 ring-danger px-1 text-[10px]">2×</span> {t("dua post satu slot", "two posts on one slot")}</span>
      </div>
      <Lane stream="regulab" posts={posts} brand={brand} onOpen={onOpen} onNewIdea={onNewIdea} />
      <Lane stream="linkedin" posts={posts} brand={brand} onOpen={onOpen} onNewIdea={onNewIdea} />
    </div>
  );
}

import { useEffect, useMemo, useState } from "react";
import { Briefcase, CalendarPlus, GripVertical, Lock, Megaphone, X } from "lucide-react";
import { useLang } from "../lib/i18n";
import { coverage, moveCheck, refOf, slotsOf } from "../lib/slots";

/* The schedule as a map (Wan, 3 Oct 2026: "map schedule so easy to see which slot have been filled, separate between
   ws.regulab and LinkedIn, asingkan this segment visibly"). Two lanes, one under the other, each its own colour and
   heading, four weeks of days in weekday columns, and inside every day one small tile per slot:
     filled (posted / scheduled / approved / draft), empty (dashed: a click writes an idea for that slot), a slot that
     already went by, and a day the stream does not post on. A tile is a button: a filled one opens the post.

   A draft or approved post can be MOVED (Wan, 3 Oct 2026: "allow us to drag and drop the post to dedicated time"): drag its
   tile onto an empty slot of the same lane, or press the grip, then click an empty slot (a touch screen has no drag, and
   Esc cancels). A post already scheduled in Buffer or posted is locked, because Buffer holds its time. A slot that is taken,
   past, off the stream's days or not one of its slots refuses the drop and says why; the database refuses the same moves
   (supabase/026), so a second tab cannot slip one through. */

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

const MOVABLE = ["draft", "approved"];

function PostTile({ p, c, d, brand, onOpen, t, lang, canMove, drag, startDrag, endDrag, pick }) {
  const tone = TILE[p.status] || TILE.draft;
  const ref = refOf(p, brand) || p.id.slice(0, 6);
  const movable = canMove && MOVABLE.includes(p.status);
  const mine = drag && drag.id === p.id;
  const label = `${d.date} ${c.slot} · ${ref} · ${lang === "en" ? tone.en : tone.bm}${p.hook ? ` · ${p.hook}` : ""}`;
  return (
    <div draggable={movable} onDragStart={movable ? (e) => startDrag(e, p) : undefined} onDragEnd={movable ? endDrag : undefined}
      title={movable ? `${label} · ${t("seret ke slot kosong untuk pindah", "drag to an empty slot to move it")}` : label}
      className={`flex w-full items-center gap-0.5 rounded px-0.5 py-0.5 text-[10.5px] leading-tight ${tone.cls} ${c.clash ? "ring-2 ring-danger" : ""} ${
        mine ? "opacity-40" : ""} ${movable ? "cursor-grab active:cursor-grabbing" : ""}`}>
      {movable ? (
        <button type="button" onClick={() => pick(p)} aria-label={t("Pindah post ini: pilih, kemudian klik slot kosong", "Move this post: pick it, then click an empty slot")}
          className={`shrink-0 rounded p-0 hover:bg-bg/30 ${mine ? "bg-bg/40" : ""}`}><GripVertical size={11} aria-hidden="true" /></button>
      ) : canMove ? (
        <span className="shrink-0 opacity-70" title={t("Dikunci: sudah dijadualkan atau diterbitkan", "Locked: already scheduled or posted")}><Lock size={10} aria-hidden="true" /></span>
      ) : null}
      <span role="button" tabIndex={0} onClick={() => onOpen(p.id)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpen(p.id); } }}
        className="flex min-w-0 flex-1 cursor-pointer items-center justify-between gap-1 text-left">
        <span className="tabular-nums">{c.slot}</span>
        <span aria-hidden="true">{c.clash ? `${c.posts.length}×` : tone.mark}</span>
      </span>
    </div>
  );
}

/** One slot of one day: its posts (all of them, so a clash can be pulled apart), or an empty/past/off placeholder. */
function Tile({ c, d, stream, brand, onOpen, onNewIdea, t, lang, urgent, canMove, drag, startDrag, endDrag, pick, picking, aim, onDropHere }) {
  if (c.posts.length) {
    return (
      <div className="space-y-0.5">
        {c.posts.map((p) => <PostTile key={p.id} p={p} c={c} d={d} brand={brand} onOpen={onOpen} t={t} lang={lang} canMove={canMove}
          drag={drag} startDrag={startDrag} endDrag={endDrag} pick={pick} />)}
      </div>
    );
  }
  if (c.gap) {
    const live = aim && aim.ok;                                       // a post is being moved and this empty slot would take it
    return (
      <button type="button"
        onClick={() => (picking ? onDropHere(d.date, c.slot) : onNewIdea({ stream, date: d.date, slot: c.slot, domain: (d.domains || [])[0] || "" }))}
        title={picking ? (live ? t("Pindahkan ke sini", "Move it here") : t("Slot ini tidak boleh menerima post itu", "This slot cannot take that post"))
          : t("Kosong: tulis idea untuk slot ini", "Empty: write an idea for this slot")}
        className={`flex w-full items-center justify-between gap-1 rounded border border-dashed px-1 py-0.5 text-left text-[10.5px] leading-tight ${
          live ? "border-accent bg-accent/15 font-medium text-accent ring-2 ring-accent/50"
            : urgent ? "border-danger/60 bg-danger/5 text-danger hover:border-accent hover:text-accent" : "border-line text-muted hover:border-accent hover:text-accent"}`}>
        <span className="tabular-nums">{c.slot}</span>
        {live ? <span aria-hidden="true">{t("letak", "drop")}</span> : <CalendarPlus size={10} aria-hidden="true" />}
      </button>
    );
  }
  return (
    <span className="flex w-full items-center justify-between rounded px-1 py-0.5 text-[10.5px] leading-tight text-muted/70 line-through">
      <span className="tabular-nums">{c.slot}</span></span>
  );
}

function Lane({ stream, posts, brand, onOpen, onNewIdea, canMove, drag, dragPost, startDrag, endDrag, pick, onDropHere }) {
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
  const dragHere = dragPost && (dragPost.stream || "regulab") === stream;       // only a post of THIS stream may land in this lane
  // what a drag carries says whose lane it may land in. Read from the drag itself (its types are visible while it is over a
  // target), never from React state, which is a render behind the first dragover and would refuse a quick drop
  const accepts = (e) => canMove && Array.from(e.dataTransfer.types || []).includes(`application/x-semasa-${stream}`);
  const aimAt = (date, slot) => (dragHere ? moveCheck({ post: dragPost, date, slot, posts, brand }) : null);

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
                    {d.cells.map((c) => (
                      <div key={c.slot}
                        onDragOver={(e) => { if (accepts(e)) { e.preventDefault(); e.dataTransfer.dropEffect = "move"; } }}
                        onDrop={(e) => { if (accepts(e)) { e.preventDefault(); onDropHere(d.date, c.slot, e.dataTransfer.getData("text/plain")); } }}>
                        <Tile c={c} d={d} stream={stream} brand={brand} onOpen={onOpen} onNewIdea={onNewIdea} t={t} lang={lang}
                          urgent={days.indexOf(d) < URGENT_DAYS} canMove={canMove} drag={drag} startDrag={startDrag} endDrag={endDrag} pick={pick}
                          picking={!!(dragHere && drag.how === "pick")} aim={c.gap ? aimAt(d.date, c.slot) : null} onDropHere={onDropHere} />
                      </div>
                    ))}
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

/** Both streams, each in its own lane. `onMove(post, date, slot)` moves a post (it explains a refusal itself); without it the
    map is read-only. */
export default function ScheduleMap({ posts, brand, onOpen, onNewIdea, onMove }) {
  const { t, lang } = useLang();
  const [drag, setDrag] = useState(null);                           // {id, how: "drag" | "pick"}: the post in hand
  const dragPost = drag ? posts.find((p) => p.id === drag.id) || null : null;
  const stop = () => setDrag(null);
  useEffect(() => {
    if (!drag) return undefined;
    const onKey = (e) => { if (e.key === "Escape") setDrag(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drag]);
  useEffect(() => { if (drag && !dragPost) setDrag(null); }, [drag, dragPost]);     // the post went away (a refresh, another tab)

  const canMove = typeof onMove === "function";
  const startDrag = (e, p) => {
    e.dataTransfer.setData("text/plain", p.id);
    e.dataTransfer.setData(`application/x-semasa-${p.stream || "regulab"}`, "1");
    e.dataTransfer.effectAllowed = "move";
    window.setTimeout(() => setDrag({ id: p.id, how: "drag" }), 0);   // after the browser has taken its drag image
  };
  const pick = (p) => setDrag((cur) => (cur && cur.id === p.id ? null : { id: p.id, how: "pick" }));
  const dropHere = async (date, slot, idFromEvent) => {
    const post = (idFromEvent && posts.find((p) => p.id === idFromEvent)) || dragPost;
    setDrag(null);
    if (post && canMove) await onMove(post, date, slot);
  };
  const lane = (stream) => (
    <Lane stream={stream} posts={posts} brand={brand} onOpen={onOpen} onNewIdea={onNewIdea} canMove={canMove} drag={drag} dragPost={dragPost}
      startDrag={startDrag} endDrag={stop} pick={pick} onDropHere={dropHere} />
  );
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted" aria-label={t("Petunjuk", "Legend")}>
        <b className="text-ink">{t("Peta jadual · 4 minggu", "Schedule map · 4 weeks")}</b>
        {LEGEND.map((k) => <span key={k} className="inline-flex items-center gap-1"><span className={`inline-block rounded px-1 text-[10px] ${TILE[k].cls}`}>{TILE[k].mark}</span> {lang === "en" ? TILE[k].en : TILE[k].bm}</span>)}
        <span className="inline-flex items-center gap-1"><span className="inline-block rounded border border-dashed border-line px-1 text-[10px]">+</span> {t("kosong (klik untuk tulis idea; merah = dalam 3 hari)", "empty (click to write an idea; red = within 3 days)")}</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block rounded px-1 text-[10px] text-muted/70 line-through">08:00</span> {t("sudah lepas", "already past")}</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block rounded ring-2 ring-danger px-1 text-[10px]">2×</span> {t("dua post satu slot", "two posts on one slot")}</span>
        {canMove && <span className="inline-flex items-center gap-1"><GripVertical size={11} aria-hidden="true" /> {t("seret draf atau post diluluskan ke slot kosong", "drag a draft or approved post onto an empty slot")}</span>}
        {canMove && <span className="inline-flex items-center gap-1"><Lock size={10} aria-hidden="true" /> {t("dikunci: sudah dijadualkan", "locked: already scheduled")}</span>}
      </div>
      {/* fixed, never in the page's flow: a banner that pushed the lanes down would move the target from under the pointer */}
      {drag && dragPost && (
        <div role="status" className="fixed inset-x-3 bottom-3 z-40 mx-auto flex max-w-3xl flex-wrap items-center gap-2 rounded-tile border border-accent/60 bg-surface px-3 py-2 text-[12px] shadow-lift">
          <span className="min-w-0 flex-1">
            {t("Memindahkan", "Moving")} <b>{refOf(dragPost, brand) || dragPost.id.slice(0, 6)}</b>{dragPost.hook ? ` · ${String(dragPost.hook).slice(0, 70)}` : ""}.{" "}
            {t("Letakkan pada slot kosong yang bergaris putus-putus dalam lorong", "Drop it on a dashed empty slot in the")}{" "}
            <b>{(dragPost.stream || "regulab") === "linkedin" ? "LinkedIn" : "ws.regulab"}</b>
            {dragPost.status === "approved" && ` · ${t("selepas dipindah ia kembali ke draf: luluskan semula", "after the move it goes back to draft: approve it again")}`}
          </span>
          <button type="button" onClick={stop} className="inline-flex items-center gap-1 rounded-pill border border-line bg-surface px-2 py-0.5 hover:border-accent">
            <X size={11} aria-hidden="true" /> {t("Batal (Esc)", "Cancel (Esc)")}</button>
        </div>
      )}
      {lane("regulab")}
      {lane("linkedin")}
    </div>
  );
}

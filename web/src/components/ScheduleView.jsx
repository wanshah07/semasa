import { useMemo, useState } from "react";
import { AlertTriangle, CalendarPlus, MoveRight } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { clashes, coverage, isPastDue, nextFreeSlot, offRota, refOf, takenSet } from "../lib/slots";
import { withDecision } from "../lib/workflow";
import ScheduleMap from "./ScheduleMap";
import Button from "./ui/Button";
import { Segmented } from "./ui/Field";

const DAY = { bm: ["Ahd", "Isn", "Sel", "Rab", "Kha", "Jum", "Sab"], en: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] };
const TONE = { draft: "bg-surface-2 text-ink", approved: "bg-ok/15 text-ok", scheduled: "bg-accent/15 text-accent", posted: "bg-ink text-bg" };

/* Studio's Schedule tab: three weeks of positions for one stream, what holds each, and what is wrong, in one view.
   An empty slot is a click away from an idea written FOR it. Posts whose slot went by are moved in one go, each to
   the next free position its rota allows, re-reading the database first so two tabs never book the same slot. */
export default function ScheduleView({ posts, brand, onOpen, onNewIdea, onToast, onChanged }) {
  const { t, lang } = useLang();
  const [stream, setStream] = useState("regulab");
  const [busy, setBusy] = useState(false);
  const days = useMemo(() => coverage({ posts, brand, stream, days: 21 }), [posts, brand, stream]);
  const mine = posts.filter((p) => (p.stream || "regulab") === stream);
  const late = mine.filter((p) => isPastDue(p));
  const off = stream === "regulab" ? offRota(posts, brand) : [];
  const clash = clashes(mine).filter((c) => c.date >= days[0].date);
  const gaps = days.reduce((n, d) => n + d.cells.filter((c) => c.gap).length, 0);
  const name = (p) => refOf(p, brand) || p.id.slice(0, 6);

  async function bumpAll() {
    if (!late.length) return;
    setBusy(true);
    const { data, error } = await supabase.from(TABLES.posts).select("id,stream,status,date,slot").eq("stream", stream).neq("status", "rejected");
    if (error) { setBusy(false); return onToast(errText(error), "danger"); }
    const taken = takenSet(data || [], stream);
    let moved = 0, stuck = 0;
    for (const p of [...late].sort((a, b) => `${a.date}${a.slot}`.localeCompare(`${b.date}${b.slot}`))) {
      const pos = nextFreeSlot({ posts: [], taken, brand, stream, domain: p.domain });
      if (!pos) { stuck++; continue; }
      const patch = { date: pos.date, slot: pos.slot, ...("decisions" in p ? { decisions: withDecision(p, "moved", `from ${p.date} ${p.slot}: the slot had passed`) } : {}) };
      // only while it is still the post it was: a post approved, sent or edited meanwhile is left alone
      const res = await supabase.from(TABLES.posts).update(patch).eq("id", p.id).eq("date", p.date).eq("slot", p.slot)
        .in("status", ["draft", "approved"]).select("id");
      if (res.error || !(res.data || []).length) { stuck++; continue; }
      taken.add(`${pos.date} ${pos.slot}`);
      moved++;
    }
    setBusy(false);
    onToast(t("{m} post dipindah ke slot kosong seterusnya{s}.", "{m} post(s) moved to the next free slot{s}.",
      { m: moved, s: stuck ? t("; {n} tidak dapat dipindah", "; {n} could not be moved", { n: stuck }) : "" }), stuck ? "warn" : "ok");
    onChanged();
  }

  return (
    <div className="mt-4 space-y-3">
      <ScheduleMap posts={posts} brand={brand} onOpen={onOpen} onNewIdea={onNewIdea} />

      <div className="flex flex-wrap items-center gap-3 border-t border-line pt-3">
        <b className="text-[12px]">{t("Butiran dan pembetulan untuk:", "Details and fixes for:")}</b>
        <Segmented value={stream} onChange={setStream} options={[["regulab", "ws.regulab"], ["linkedin", "LinkedIn"]]} />
        <span className="text-[12px] text-muted">{t("{g} slot kosong dalam 21 hari", "{g} empty slot(s) in the next 21 days", { g: gaps })}</span>
      </div>

      {late.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-tile border border-danger/40 bg-danger/5 p-3 text-[12px]">
          <AlertTriangle size={14} className="text-danger" />
          <span className="flex-1">{t("{n} post sudah lepas slotnya dan tidak akan dihantar: {l}", "{n} post(s) are past their slot and will never be sent: {l}",
            { n: late.length, l: late.map(name).join(", ") })}</span>
          <Button size="sm" variant="soft" disabled={busy} onClick={bumpAll}><MoveRight size={12} /> {t("Pindah semua ke slot kosong", "Bump all to free slots")}</Button>
        </div>
      )}
      {clash.length > 0 && (
        <p className="rounded-tile border border-warn/40 bg-warn/10 p-3 text-[12px]">{t("Dua post pada satu slot: ", "Two posts on one slot: ")}
          {clash.map((c) => `${c.date} ${c.slot} (${c.posts.map(name).join(" + ")})`).join(" · ")}</p>
      )}
      {off.length > 0 && (
        <p className="rounded-tile border border-line bg-surface-2/50 p-3 text-[12px] text-muted">
          {t("Di luar rota (nota, bukan sekatan): ", "Off the rota (a note, not a block): ")}
          {off.map((p) => <button key={p.id} type="button" className="mr-2 underline" onClick={() => onOpen(p.id)}>{name(p)} · {p.domain}</button>)}</p>
      )}

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {days.map((d) => (
          <div key={d.date} className={`rounded-tile border p-2 ${d.posting ? "border-line" : "border-dashed border-line opacity-60"}`}>
            <p className="flex items-baseline justify-between text-[12px] font-medium">
              <span>{DAY[lang === "en" ? "en" : "bm"][d.dow]} · {d.date.slice(8)}/{d.date.slice(5, 7)}</span>
              <span className="text-[10.5px] font-normal text-muted">{d.posting ? (d.domains || []).join(" · ") : t("tiada post", "no posting")}</span>
            </p>
            <ul className="mt-1 space-y-1">
              {d.cells.map((c) => (
                <li key={c.slot} className="flex items-start gap-2 text-[12px]">
                  <span className={`w-10 shrink-0 tabular-nums ${c.past ? "text-muted line-through" : "text-muted"}`}>{c.slot}</span>
                  <span className="min-w-0 flex-1 space-y-0.5">
                    {c.posts.map((p) => (
                      <button key={p.id} type="button" onClick={() => onOpen(p.id)} title={p.hook || ""}
                        className={`block w-full truncate rounded px-1.5 py-0.5 text-left ${TONE[p.status] || "bg-surface-2"} ${c.clash ? "ring-1 ring-warn" : ""}`}>
                        {name(p)} · {p.hook || t("(tiada cangkuk)", "(no hook)")}</button>
                    ))}
                    {c.gap && (
                      <button type="button" onClick={() => onNewIdea({ stream, date: d.date, slot: c.slot, domain: (d.domains || [])[0] || "" })}
                        className="flex w-full items-center gap-1 rounded border border-dashed border-line px-1.5 py-0.5 text-left text-muted hover:border-accent hover:text-accent">
                        <CalendarPlus size={11} /> {t("kosong: tulis idea untuk slot ini", "empty: write an idea for this slot")}</button>
                    )}
                  </span>
                </li>
              ))}
              {d.extra.map((p) => (
                <li key={p.id} className="flex items-start gap-2 text-[12px]">
                  <span className="w-10 shrink-0 tabular-nums text-muted">{p.slot}</span>
                  <button type="button" onClick={() => onOpen(p.id)} className={`min-w-0 flex-1 truncate rounded px-1.5 py-0.5 text-left ${TONE[p.status] || "bg-surface-2"}`}>
                    {name(p)} · {p.hook || ""}</button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

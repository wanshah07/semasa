import { useState } from "react";
import { AlertTriangle, CalendarClock, Send } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { resendView } from "../lib/resend";
import { moveCheck, myt, nextFreeSlot, nextRunMs, slotsOf } from "../lib/slots";
import { withDecision } from "../lib/workflow";
import Button from "./ui/Button";
import { Input, Label, Select } from "./ui/Field";

const NAME = { instagram: "Instagram", facebook: "Facebook", threads: "Threads", linkedin: "LinkedIn", tiktok: "TikTok" };
const names = (list) => list.map((c) => NAME[c] || c).join(", ");

/* A half-sent post (Wan, 16 Nov 2026: "move to new slot"). When a slot comes a platform can refuse its channel while the others
   go out. This box says which channels failed, in the platform's own words, and moves the post to a new slot. The move is the
   whole instruction: the publisher then hands over ONLY the failed channels for the new slot, and a channel that went out is
   never sent twice (backend/semasa/publisher.py stale_failures). It writes the date and slot and nothing else; the database
   refuses the move while any channel is still queued (supabase/084_resend_failed_channels.sql). */
export default function PostResend({ post, posts = [], brand, onToast, onChanged }) {
  const { t } = useLang();
  const [date, setDate] = useState("");
  const [slot, setSlot] = useState("");
  const [busy, setBusy] = useState(false);
  const v = resendView(post);
  if (!v.show) return null;

  const stream = post.stream || "regulab";
  const slots = slotsOf(brand, stream);
  const run = myt(nextRunMs()).time;
  const refusal = (chk) => ({
    status: t("Post ini tidak boleh dipindah sekarang.", "This post cannot be moved now."),
    published: t("Satu saluran masih dalam barisan penjadual: tunggu ia keluar dahulu.", "A channel is still in the scheduler's queue: wait until it has gone out."),
    same: t("Post ini memang di slot itu.", "This post is already on that slot."),
    slot: t("{s} bukan salah satu slot lorong ini.", "{s} is not one of this lane's slots.", { s: slot }),
    day: t("Lorong ini tidak menerbitkan pada {d}.", "This lane does not post on {d}.", { d: date }),
    past: t("Slot itu sudah lepas atau terlalu hampir.", "That slot has passed or is too close."),
    run: t("Slot itu terlalu awal: penerbit hanya menyerahkan post pada 06:20, 11:20 dan 19:20, dan lariannya yang seterusnya ialah {r}. Pilih slot selepas itu.",
      "That slot is too early: the publisher hands posts over only at 06:20, 11:20 and 19:20, and its next run is {r}. Pick a slot after that.", { r: chk.run }),
    taken: t("Slot {d} {s} sudah dipegang oleh: {h}. Satu slot, satu post.", "The slot {d} {s} is already held by: {h}. One post to a slot.",
      { d: date, s: slot, h: (chk.by || []).map((x) => x.hook || String(x.id).slice(0, 8)).join(" · ") }),
  }[chk.why]);

  function takeNextFree() {
    // never a slot the publisher's next run comes too late for
    const leadMin = Math.max(30, Math.ceil((nextRunMs() - Date.now()) / 60_000));
    const pos = nextFreeSlot({ posts, brand, stream, domain: post.domain, skipId: post.id, leadMin });
    if (!pos) return onToast?.(t("Tiada slot kosong dalam 60 hari.", "No free slot in the next 60 days."), "warn");
    setDate(pos.date); setSlot(pos.slot);
  }

  async function move() {
    if (!date || !slot || busy) return;
    setBusy(true);
    // the slot is asked of the database first: the list on screen can be a poll behind
    const { data: live, error } = await supabase.from(TABLES.posts).select("id,stream,status,date,slot,hook")
      .eq("stream", stream).neq("status", "rejected").eq("date", date);
    if (error) { setBusy(false); return onToast?.(errText(error), "danger"); }
    const chk = moveCheck({ post, date, slot, posts: live || [], brand });
    if (!chk.ok) { setBusy(false); return onToast?.(refusal(chk), "warn"); }
    const patch = { date, slot, ...("decisions" in post ? { decisions: withDecision(post, "moved", `from ${post.date} ${post.slot}: to send ${v.failed.join(", ")} again`) } : {}) };
    // only while it is still the post it was: same position, same status
    const res = await supabase.from(TABLES.posts).update(patch).eq("id", post.id).eq("date", post.date).eq("slot", post.slot)
      .eq("status", post.status).select("id,status");
    setBusy(false);
    if (res.error) {
      return onToast?.(/sudah diserahkan|row-level security/.test(errText(res.error))
        ? t("Pangkalan data menolak pemindahan ini: jalankan supabase/084_resend_failed_channels.sql sekali di SQL editor.",
          "The database refused this move: run supabase/084_resend_failed_channels.sql once in the SQL editor.")
        : errText(res.error), "danger");
    }
    if (!(res.data || []).length) {
      onChanged?.();
      return onToast?.(t("Post ini berubah semasa anda memindahkannya. Tiada apa-apa dipindah.", "This post changed while you were moving it. Nothing was moved."), "warn");
    }
    setDate(""); setSlot("");
    onToast?.(res.data[0].status === "draft"
      ? t("Dipindah ke {d} {s}. Post ini kembali ke draf kerana masanya berubah: luluskan semula, kemudian hanya {c} dihantar.",
        "Moved to {d} {s}. It went back to draft because its time changed: approve it again, then only {c} is sent.", { d: date, s: slot, c: names(v.failed) })
      : t("Dipindah ke {d} {s}. Penerbit menghantar {c} sahaja pada slot itu.", "Moved to {d} {s}. The publisher sends only {c} at that slot.",
        { d: date, s: slot, c: names(v.failed) }), "ok");
    onChanged?.();
  }

  return (
    <div className="rounded-tile border border-danger/40 bg-surface-2 p-3 text-sm" data-post-resend>
      <p className="flex items-center gap-1.5 font-medium text-danger"><AlertTriangle size={14} />
        {t("Saluran yang gagal: {c}", "Failed channels: {c}", { c: names(v.failed) })}</p>
      <ul className="mt-1 space-y-0.5 text-xs text-muted">
        {v.failed.map((c) => <li key={c}><b>{NAME[c] || c}</b>: {v.reasons[c] || t("platform menolaknya", "the platform refused it")}</li>)}
      </ul>
      {v.sent.length > 0 && <p className="mt-1 text-xs text-muted">
        {t("Sudah keluar dan tidak akan dihantar lagi: {c}.", "Already out and never sent again: {c}.", { c: names(v.sent) })}</p>}

      {v.state === "waiting" && <p className="mt-2 text-xs">
        {t("Post ini sudah dipindah ke {d} {s}. Penerbit menyerahkan {c} sahaja untuk slot itu pada lariannya yang seterusnya ({r}). Tiada apa-apa lagi perlu dibuat.",
          "This post has been moved to {d} {s}. The publisher hands over only {c} for that slot at its next run ({r}). Nothing more to do.",
          { d: post.date, s: post.slot, c: names(v.again), r: run })}</p>}

      {v.state === "approve" && <p className="mt-2 text-xs">
        {t("Post ini sudah dipindah ke {d} {s} dan kembali ke draf. Luluskan semula: penerbit kemudian menyerahkan {c} sahaja untuk slot itu.",
          "This post has been moved to {d} {s} and went back to draft. Approve it again: the publisher then hands over only {c} for that slot.",
          { d: post.date, s: post.slot, c: names(v.again) })}</p>}

      {v.state === "queued" && <p className="mt-2 text-xs">
        {t("{q} masih dalam barisan penjadual, jadi post ini belum boleh dipindah. Selepas ia keluar, pindahkan post ini ke slot baharu untuk menghantar semula saluran yang gagal.",
          "{q} is still in the scheduler's queue, so this post cannot move yet. Once it has gone out, move this post to a new slot to send the failed channels again.",
          { q: names(v.queued) })}</p>}

      {(v.state === "move" || v.state === "missed") && (
        <>
          <p className="mt-2 text-xs">
            {v.state === "missed"
              ? t("Slot {d} {s} lepas sebelum penerbit sempat menyerahkannya semula. Pindahkan ke slot yang lebih lewat.",
                "The slot {d} {s} passed before the publisher could hand it over again. Move it to a later slot.", { d: post.date, s: post.slot })
              : t("Untuk menghantar semula, pindahkan post ini ke slot baharu. Hanya {c} dihantar; kata-kata dan gambarnya kekal seperti yang diluluskan.",
                "To send again, move this post to a new slot. Only {c} is sent; its words and pictures stay as approved.", { c: names(v.failed) })}
            {v.lost.length > 0 && ` ${t("Semak {c} dahulu: jika post itu sudah ada di sana, jangan pindahkan.", "Check {c} first: if the post is already there, do not move it.", { c: names(v.lost) })}`}
            {post.status === "approved" && ` ${t("Selepas dipindah ia kembali ke draf: luluskan semula.", "After the move it goes back to draft: approve it again.")}`}
          </p>
          <div className="mt-2 flex flex-wrap items-end gap-2">
            <label><Label>{t("Tarikh baharu (MYT)", "New date (MYT)")}</Label><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="w-44" /></label>
            <label><Label>{t("Slot baharu", "New slot")}</Label><Select value={slot} onChange={setSlot} options={[["", t("Pilih", "Choose")], ...slots.map((s) => [s, s])]} /></label>
            <Button type="button" size="sm" variant="ghost" onClick={takeNextFree}><CalendarClock size={12} /> {t("Slot kosong seterusnya", "Next free slot")}</Button>
            <Button type="button" size="sm" disabled={busy || !date || !slot} onClick={move}><Send size={12} /> {t("Pindah dan hantar semula", "Move and send again")}</Button>
          </div>
          <p className="mt-1 text-[11px] text-muted">{t("Penerbit menyerahkan post pada 06:20, 11:20 dan 19:20 sahaja; lariannya yang seterusnya ialah {r}.",
            "The publisher hands posts over at 06:20, 11:20 and 19:20 only; its next run is {r}.", { r: run })}</p>
        </>
      )}
    </div>
  );
}

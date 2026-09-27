import { useState } from "react";
import { History, Loader2, PenLine, RotateCcw, XCircle } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { stampMYT } from "../lib/format";
import { useLang } from "../lib/i18n";
import { restoreVersion, withDecision } from "../lib/workflow";
import { dueMs } from "../lib/slots";
import Button from "./ui/Button";
import { Input, Label } from "./ui/Field";

const NEED_021 = /versions|decisions|revise_|rejected_at|column/i;

/* Studio's revise, reject-and-replace and history, in one place under the editor (supabase/021_studio_workflow.sql).
   Better than Studio in three ways: a revise keeps the slides and their designs (Studio wrote the card again), a
   replacement keeps the rejected draft's own photographs instead of paying for new ones, and restoring an old version
   keeps the words it replaces, so no rewrite can ever lose what Wan wrote. */
export default function PostWorkflow({ post, dirty, locked, mediaById, lastLook, onToast, onChanged, user }) {
  const { t } = useLang();
  const [note, setNote] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [why, setWhy] = useState("");
  const [replace, setReplace] = useState(true);
  const [keepPics, setKeepPics] = useState(true);
  const [busy, setBusy] = useState(false);
  const [showHist, setShowHist] = useState(false);
  const has021 = "versions" in post && "revise_state" in post;
  const versions = Array.isArray(post.versions) ? post.versions : [];
  const decisions = Array.isArray(post.decisions) ? post.decisions : [];
  // photographs only: a drawn slide set carries the old words (the worker checks the same, ideas.kept_media)
  const photos = (post.media_ids || []).filter((id) => mediaById[id] && mediaById[id].mode !== "slides"
    && mediaById[id].status === "done");

  const need021 = () => onToast(t("Jalankan supabase/021_studio_workflow.sql sekali dahulu.",
    "Run supabase/021_studio_workflow.sql once first."), "warn");

  async function update(patch, msg) {
    setBusy(true);
    const { error } = await supabase.from(TABLES.posts).update(patch).eq("id", post.id);
    setBusy(false);
    if (error) { onToast(NEED_021.test(errText(error)) && !has021 ? t("Jalankan supabase/021_studio_workflow.sql sekali dahulu.", "Run supabase/021_studio_workflow.sql once first.") : errText(error), "danger"); return false; }
    if (msg) onToast(msg, "ok");
    onChanged();
    return true;
  }

  async function askRevise() {
    if (!has021) return need021();
    if (!note.trim()) return onToast(t("Tulis nota: apa yang patut berubah.", "Write a note: what should change."), "warn");
    if (dirty) return onToast(t("Simpan suntingan anda dahulu: bot menulis semula perkataan yang disimpan.",
      "Save your edits first: the bot rewrites the saved words."), "warn");
    if (await update({ revise_note: note.trim().slice(0, 800), revise_state: "new", revise_error: null },
      t("Dihantar. Bot menulis semula post ini dengan nota anda; perkataan lama disimpan dalam Sejarah.",
        "Sent. The bot rewrites this post with your note; the old words are kept in History."))) setNote("");
  }

  async function reject() {
    const reason = why.trim();
    const patch = { status: "rejected", ...(has021 ? { decisions: withDecision(post, "rejected", reason) } : {}) };
    setBusy(true);
    const { error } = await supabase.from(TABLES.posts).update(patch).eq("id", post.id);
    if (error) { setBusy(false); return onToast(errText(error), "danger"); }
    if (!replace) {
      setBusy(false); setRejecting(false); setWhy("");
      onToast(t("Ditolak. Ia dipadam sendiri 72 jam lagi; Pulihkan sebelum itu jika perlu.",
        "Rejected. It deletes itself in 72 hours; Restore it before then if needed."), "ok");
      return onChanged();
    }
    // the replacement: a new idea on the same source, for the same slot while it is still ahead, with Wan's reason
    let src = {};
    if (post.idea_id) {
      const { data } = await supabase.from(TABLES.ideas).select("source_title,source_url,source_name,source_summary,trend_id,reference_urls,make_media")
        .eq("id", post.idea_id).maybeSingle();
      src = data || {};
    }
    const keep = keepPics ? photos : [];
    const brief = { replaces: post.id };
    if (post.date && post.slot && dueMs(post.date, post.slot) > Date.now() + 30 * 60_000) brief.position = { date: post.date, slot: post.slot };
    if (keep.length) brief.keep_media_ids = keep;
    if (lastLook && lastLook !== "classic") brief.look = lastLook;
    const row = {
      trend_id: src.trend_id ?? null, source_title: (src.source_title || post.hook || t("Post ditolak", "Rejected post")).slice(0, 500),
      source_url: src.source_url ?? null, source_name: src.source_name ?? null, source_summary: src.source_summary ?? null,
      reference_urls: src.reference_urls || [], stream: post.stream || "regulab",
      make_media: keep.length ? "none" : src.make_media === "video" ? "video" : "image",
      note: [t("Pengganti draf yang ditolak.", "Replaces a rejected draft."),
        reason ? `${t("Sebab", "Reason")}: ${reason}` : "", post.hook ? `${t("Cangkuk yang ditolak", "Rejected hook")}: ${post.hook}` : ""]
        .filter(Boolean).join(" "),
      domain: post.stream === "regulab" ? post.domain || null : null, angle: post.stream === "linkedin" ? post.angle || null : null,
      status: "new", created_by: user.id, brief,
      ...((post.slides || []).length > 1 ? { make_slides: true } : {}),
    };
    const ins = await supabase.from(TABLES.ideas).insert(row);
    setBusy(false); setRejecting(false); setWhy("");
    if (ins.error) return onToast(t("Ditolak, tetapi idea pengganti gagal: {e}", "Rejected, but the replacement idea failed: {e}", { e: errText(ins.error) }), "danger");
    onToast(brief.position
      ? t("Ditolak. Pengganti sedang ditulis untuk {d} {s}{k}.", "Rejected. A replacement is being written for {d} {s}{k}.",
        { d: post.date, s: post.slot, k: keep.length ? t(", dengan gambar yang sama", ", with the same pictures") : "" })
      : t("Ditolak. Pengganti sedang ditulis untuk slot kosong seterusnya.", "Rejected. A replacement is being written for the next free slot."), "ok");
    onChanged();
  }

  async function restoreV(i) {
    if (dirty && !window.confirm(t("Suntingan yang belum disimpan akan hilang. Teruskan?", "Unsaved edits will be lost. Continue?"))) return;
    const patch = restoreVersion(post, i);
    if (patch) await update(patch, t("Versi itu dipulihkan; perkataan tadi disimpan dalam Sejarah.", "That version is back; the words it replaced are kept in History."));
  }

  const state = post.revise_state;
  return (
    <div className="space-y-3">
      {post.status === "draft" && !locked && (
        <div className="rounded-tile border border-line p-3">
          <Label hint={t("bot menulis semula perkataan sahaja; slaid, reka bentuk dan gambar kekal", "the bot rewrites the words only; slides, designs and pictures stay")}>
            <PenLine size={12} className="mr-1 inline" />{t("Tulis semula dengan nota", "Revise with a note")}</Label>
          {state === "new" || state === "working" ? (
            <p className="flex items-center gap-2 text-[12px] text-muted"><Loader2 size={13} className="animate-spin" />
              {t("Bot sedang menulis semula: \"{n}\"", "The bot is rewriting: \"{n}\"", { n: post.revise_note || "" })}</p>
          ) : (
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input value={note} onChange={(e) => setNote(e.target.value)} maxLength={800} disabled={busy}
                placeholder={t("cth. Pendekkan, mula dengan kesilapan yang biasa berlaku", "e.g. Shorter, open with the usual mistake")} />
              <Button size="sm" variant="soft" disabled={busy || !note.trim()} onClick={askRevise}>{t("Tulis semula", "Revise")}</Button>
            </div>
          )}
          {state === "error" && (
            <p className="mt-2 text-[12px] text-danger">{post.revise_error}{" "}
              <button type="button" className="underline" disabled={busy}
                onClick={() => update({ revise_state: null, revise_error: null }, "")}>{t("Tutup", "Dismiss")}</button></p>
          )}
        </div>
      )}

      {(post.status === "draft" || post.status === "approved") && !locked && (
        rejecting ? (
          <div className="rounded-tile border border-danger/40 p-3">
            <Label>{t("Tolak post ini", "Reject this post")}</Label>
            <Input value={why} onChange={(e) => setWhy(e.target.value)} maxLength={400} disabled={busy}
              placeholder={t("Sebab (pilihan, dibaca oleh penulis pengganti)", "Reason (optional, read by the replacement's writer)")} />
            <label className="mt-2 flex items-start gap-2 text-[12px]">
              <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} className="mt-0.5" />
              <span>{t("Tulis pengganti untuk slot yang sama", "Write a replacement for the same slot")}</span></label>
            {replace && photos.length > 0 && (
              <label className="mt-1 flex items-start gap-2 text-[12px]">
                <input type="checkbox" checked={keepPics} onChange={(e) => setKeepPics(e.target.checked)} className="mt-0.5" />
                <span>{t("Guna semula {n} gambar post ini (tiada kos gambar baharu)", "Reuse this post's {n} picture(s) (no new picture paid for)", { n: photos.length })}</span></label>
            )}
            <div className="mt-2 flex gap-2">
              <Button size="sm" variant="danger" disabled={busy} onClick={reject}><XCircle size={12} /> {replace ? t("Tolak & ganti", "Reject & replace") : t("Tolak", "Reject")}</Button>
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => setRejecting(false)}>{t("Batal", "Cancel")}</Button>
            </div>
          </div>
        ) : (
          <Button variant="ghost" size="sm" disabled={busy} onClick={() => setRejecting(true)}><XCircle size={12} /> {t("Tolak…", "Reject…")}</Button>
        )
      )}

      {(versions.length > 0 || decisions.length > 0) && (
        <div>
          <button type="button" className="flex items-center gap-1 text-xs font-medium text-muted hover:text-ink" onClick={() => setShowHist((x) => !x)}
            aria-expanded={showHist}>
            <History size={12} /> {t("Sejarah · {v} versi, {d} keputusan", "History · {v} versions, {d} decisions", { v: versions.length, d: decisions.length })}
          </button>
          {showHist && (
            <div className="mt-2 space-y-2">
              {[...versions].map((v, i) => ({ v, i })).reverse().map(({ v, i }) => (
                <div key={i} className="rounded-tile border border-line p-2 text-[12px]">
                  <p className="text-muted">{stampMYT(v.at)}{v.why ? ` · ${v.why}` : ""}</p>
                  <p className="mt-0.5 font-medium [overflow-wrap:anywhere]">{v.hook || t("(tiada cangkuk)", "(no hook)")}</p>
                  {!locked && post.status !== "rejected" && <Button size="sm" variant="ghost" className="mt-1" disabled={busy} onClick={() => restoreV(i)}>
                    <RotateCcw size={11} /> {t("Pulihkan versi ini", "Restore this version")}</Button>}
                </div>
              ))}
              {decisions.length > 0 && (
                <ul className="space-y-0.5 text-[11.5px] text-muted">
                  {[...decisions].reverse().map((d, i) => (
                    <li key={i}>{stampMYT(d.at)} · <b>{d.action}</b>{d.by && d.by !== "page" ? ` (${d.by})` : ""}{d.note ? `: ${d.note}` : ""}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

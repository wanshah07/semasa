import { useState } from "react";
import { CheckCircle2, Pencil, RefreshCw } from "lucide-react";
import { errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { changed, decideWords, previewOf, scenesOf, termsOf, withEdits, writtenEpoch } from "../lib/motionReview";
import Button from "./ui/Button";
import { Input, TextArea } from "./ui/Field";

/* A film waiting on its storyboard (Wan, 7 Nov 2026: "make sure all storyboard appear and approve before proceed for motion
   creation"). Every scene is shown in full; Wan approves it as it is, edits the words and approves, or asks for a new one.
   Approving goes through semasa_motion_storyboard_decide (supabase/071), which stamps who approved it and wakes the worker;
   the worker checks the edited words again before it draws a single picture. */
export default function MotionStoryboardReview({ film, onDone, onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const sb = film?.storyboard;
  const scenes = scenesOf(sb);
  const terms = termsOf(sb);
  const preview = previewOf(sb);
  const [editing, setEditing] = useState(false);
  const [edits, setEdits] = useState({});
  const [busy, setBusy] = useState("");
  const set = (key, field, value) => setEdits((e) => ({ ...e, [key]: { ...(e[key] || {}), [field]: value } }));
  const val = (sc, field) => {
    const e = edits[sc.key]?.[field];
    if (e !== undefined) return e;
    return field === "lines" ? sc.lines.join("\n") : sc[field];
  };

  const decide = async (action) => {
    setBusy(action);
    try {
      const body = action === "approve" && editing && changed(sb, edits) ? withEdits(sb, edits) : null;
      const { data, error } = await supabase.rpc("semasa_motion_storyboard_decide", { p_motion: film.id, p_action: action, p_storyboard: body, p_written: writtenEpoch(sb) });
      if (error) throw new Error(errText(error));
      onToast?.(decideWords(data, action, L), data === "ok" ? "ok" : "error");
      if (data === "ok") { setEditing(false); setEdits({}); }
      onDone?.();
    } catch (e) { onToast?.(e.message || String(e), "error"); } finally { setBusy(""); }
  };

  if (!sb || !scenes.length) {
    return <p className="mt-3 rounded-tile bg-warn/10 p-3 text-xs text-warn" data-storyboard-missing>{t("Storyboard belum disimpan. Tekan Tulis semula.", "No storyboard was saved. Press Write again.")}
      <Button size="sm" variant="ghost" className="ml-2" disabled={!!busy} onClick={() => decide("rewrite")}><RefreshCw size={12} /> {t("Tulis semula", "Write again")}</Button></p>;
  }
  return (
    <div className="mt-3 rounded-tile border border-accent/30 bg-accent/5 p-3" data-storyboard-review>
      <p className="text-sm font-medium">{t("Storyboard menunggu kelulusan anda", "The storyboard is waiting for your approval")}</p>
      <p className="mt-0.5 text-xs text-muted">{t("Suara dan video hanya dibuat selepas anda luluskan. Tukar teks Gambar untuk lukis semula gambar babak itu. Semua perkataan disemak semula sebelum digunakan.",
        "The voice and the film are made only after you approve. Change a scene's Picture text to have it drawn again. Every word is checked again before it is used.")}{sb.note ? ` · ${sb.note}` : ""}</p>
      {terms.length ? (
        <div className="mt-3 rounded-tile bg-surface p-2 text-xs" data-storyboard-terms>
          <p className="text-[11px] uppercase tracking-wide text-muted">{t("Apa itu", "What it is")}</p>
          <ul className="mt-1 space-y-1">{terms.map((x) => <li key={x.term}><b>{x.term}</b>: {x.meaning}</li>)}</ul>
        </div>
      ) : null}
      {preview ? (
        <div className="mt-3" data-storyboard-preview>
          <p className="text-[11px] uppercase tracking-wide text-muted">{t("Pratonton rupa filem", "Preview of the film")}</p>
          <a href={preview.sheet} target="_blank" rel="noreferrer"><img src={preview.sheet} alt={t("Pratonton setiap babak", "A frame of every scene")} loading="lazy" className="mt-1 w-full rounded-tile border border-line" /></a>
          <p className="mt-1 text-[11px] text-muted">{t("Dilukis daripada kata-kata dan gambar yang disimpan; mengubah perkataan di bawah tidak mengemas kini pratonton ini.", "Drawn from the saved words and pictures; editing the words below does not update this preview.")}</p>
        </div>
      ) : null}
      <ol className="mt-3 space-y-2" data-storyboard-scenes>
        {scenes.map((sc) => (
          <li key={sc.key} className="rounded-tile bg-surface p-2 text-xs" data-storyboard-scene={sc.key}>
            <p className="text-[11px] uppercase tracking-wide text-muted">{sc.label}</p>
            {sc.image ? <img src={sc.image} alt="" loading="lazy" data-storyboard-image className="mb-2 mt-1 h-40 w-full rounded-tile object-cover" /> : null}
            {editing && sc.edit.heading
              ? <Input value={val(sc, "heading")} onChange={(e) => set(sc.key, "heading", e.target.value)} aria-label={t("Tajuk babak", "Scene heading")} />
              : <p className="font-medium">{sc.heading}</p>}
            {editing && sc.edit.lines
              ? <TextArea className="mt-1" rows={Math.max(2, sc.lines.length)} value={val(sc, "lines")} onChange={(e) => set(sc.key, "lines", e.target.value)} aria-label={t("Baris (satu sebaris)", "Lines (one a line)")} />
              : sc.lines.filter(Boolean).length > 0 && <ul className="mt-0.5 list-disc pl-4">{sc.lines.filter(Boolean).map((x, i) => <li key={i}>{x}</li>)}</ul>}
            {(sc.said || (editing && sc.edit.said)) && (editing && sc.edit.said
              ? <TextArea className="mt-1" rows={2} value={val(sc, "said")} onChange={(e) => set(sc.key, "said", e.target.value)} aria-label={t("Suara", "Narration")} />
              : <p className="mt-1 text-muted">🔊 {sc.said}</p>)}
            {(sc.shot || (editing && sc.edit.shot)) && (editing && sc.edit.shot
              ? <TextArea className="mt-1" rows={2} value={val(sc, "shot")} onChange={(e) => set(sc.key, "shot", e.target.value)} aria-label={t("Gambar", "Picture")} />
              : <p className="mt-1 text-muted">🖼 {sc.shot}</p>)}
          </li>
        ))}
      </ol>
      {/* the decision stays in reach on a long storyboard and on a phone */}
      <div className="sticky bottom-0 -mx-3 mt-3 flex flex-wrap gap-2 border-t border-line bg-surface/95 px-3 py-2 backdrop-blur">
        <Button disabled={!!busy} onClick={() => decide("approve")} data-storyboard-approve>
          <CheckCircle2 size={12} /> {editing && changed(sb, edits) ? t("Luluskan dengan suntingan", "Approve with my edits") : t("Luluskan", "Approve")}</Button>
        <Button size="sm" variant="ghost" disabled={!!busy} onClick={() => { setEditing((v) => !v); setEdits({}); }} data-storyboard-edit>
          <Pencil size={12} /> {editing ? t("Batal suntingan", "Cancel edits") : t("Ubah perkataan", "Edit the words")}</Button>
        <Button size="sm" variant="ghost" disabled={!!busy} onClick={() => decide("rewrite")} data-storyboard-rewrite>
          <RefreshCw size={12} /> {t("Tulis semula", "Write again")}</Button>
      </div>
    </div>
  );
}

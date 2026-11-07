import { useState } from "react";
import { CheckCircle2, Pencil, RefreshCw } from "lucide-react";
import { errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { changed, decideWords, scenesOf, withEdits, writtenEpoch } from "../lib/motionReview";
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
      <p className="mt-0.5 text-xs text-muted">{t("Gambar dan video hanya dibuat selepas anda luluskan. Semua perkataan disemak semula sebelum digunakan.",
        "Pictures and the film are made only after you approve. Every word is checked again before it is used.")}{sb.note ? ` · ${sb.note}` : ""}</p>
      <ol className="mt-3 space-y-2" data-storyboard-scenes>
        {scenes.map((sc) => (
          <li key={sc.key} className="rounded-tile bg-surface p-2 text-xs" data-storyboard-scene={sc.key}>
            <p className="text-[11px] uppercase tracking-wide text-muted">{sc.label}{sc.hookShape ? ` · ${t("bentuk hook", "hook shape")} ${sc.hookShape}` : ""}</p>
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
      <div className="mt-3 flex flex-wrap gap-2">
        <Button size="sm" disabled={!!busy} onClick={() => decide("approve")} data-storyboard-approve>
          <CheckCircle2 size={12} /> {editing && changed(sb, edits) ? t("Luluskan dengan suntingan", "Approve with my edits") : t("Luluskan", "Approve")}</Button>
        <Button size="sm" variant="ghost" disabled={!!busy} onClick={() => { setEditing((v) => !v); setEdits({}); }} data-storyboard-edit>
          <Pencil size={12} /> {editing ? t("Batal suntingan", "Cancel edits") : t("Ubah perkataan", "Edit the words")}</Button>
        <Button size="sm" variant="ghost" disabled={!!busy} onClick={() => decide("rewrite")} data-storyboard-rewrite>
          <RefreshCw size={12} /> {t("Tulis semula", "Write again")}</Button>
      </div>
    </div>
  );
}

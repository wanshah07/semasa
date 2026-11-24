import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { stampMYT } from "../lib/format";
import Button from "./ui/Button";

/* Redraw a ws.regulab carousel or film IN PLACE (Wan, 24 Nov 2026: "add redraw in semasa and telegram button"). Its words, slot and
   approval stay exactly as they are; the worker (supabase/093, backend/semasa/rerender.py) takes the Zernio copy out, draws the
   pictures again with the current design and the publisher queues it again. It asks by inserting a row; nothing is approved or
   sent from here. Not for LinkedIn (no brand cover: use Refresh in the slides editor) or for a post already sent. */
/* The worker's own test (rerender.redrawable): a finished carousel (not a Diari or Threads design pack), or, once the post is not a
   draft any more, a Motion film. Anything else would be refused, so no button is shown (Codex review on #341). */
export function redrawable(post, media) {
  if ((post.stream || "regulab") !== "regulab") return false;
  return (media || []).some((m) => {
    const meta = m.meta || {};
    if (m.status !== "done") return false;
    if (m.mode === "slides" && !meta.design && meta.look !== "threads") return true;
    return post.status !== "draft" && m.type === "video" && meta.flow === "motion" && !meta.film_purged_at && !!meta.motion_id;
  });
}

export default function PostRedraw({ post, media, onToast, onChanged }) {
  const { t } = useLang();
  const [req, setReq] = useState(null);
  const [busy, setBusy] = useState(false);
  const [missing, setMissing] = useState(false);

  async function load() {
    if (!supabase) return;
    const { data, error } = await supabase.from(TABLES.postRedraws).select("id,state,note,requested_at,done_at")
      .eq("post_id", post.id).order("requested_at", { ascending: false }).limit(1);
    if (error) { setMissing(/does not exist|schema cache|relation/i.test(error.message || "")); return; }
    setReq((data || [])[0] || null);
  }
  useEffect(() => { load(); const id = setInterval(load, 20000); return () => clearInterval(id); }, [post.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (req?.state === "done") onChanged?.(); }, [req?.state]); // eslint-disable-line react-hooks/exhaustive-deps

  async function ask() {
    setBusy(true);
    const { error } = await supabase.from(TABLES.postRedraws).insert({ post_id: post.id });
    setBusy(false);
    if (error) return onToast?.(/duplicate|unique/i.test(error.message || "") ? t("Sudah diminta: menunggu pekerja.", "Already asked: waiting for the worker.") : errText(error), "danger");
    onToast?.(t("Diminta. Pekerja melukisnya semula dalam beberapa minit; kata-kata, slot dan kelulusan kekal.", "Asked. The worker draws it again within a few minutes; the words, slot and approval stay."), "ok");
    load();
  }

  if (!["draft", "approved", "scheduled"].includes(post.status) || !redrawable(post, media)) return null;
  const pending = req?.state === "pending";
  return (
    <div className="rounded-tile border border-line bg-surface-2 p-3 text-sm" data-post-redraw>
      <p className="font-medium">{t("Lukis semula karusel", "Redraw the carousel")}</p>
      <p className="mt-0.5 text-xs text-muted">{t("Dilukis semula dengan reka bentuk dan ilustrasi semasa. Kata-kata, slot dan kelulusan tidak berubah.",
        "Drawn again with the current design and illustrations. The words, slot and approval do not change.")}</p>
      {missing ? <p className="mt-2 text-xs text-danger">{t("Migrasi 093 belum dijalankan di pangkalan data.", "Migration 093 has not been run on the database yet.")}</p> : (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Button size="sm" variant="soft" disabled={busy || pending} onClick={ask}><RefreshCw size={12} /> {t("Lukis semula", "Redraw")}</Button>
          {pending && <span className="text-xs text-muted">{t("Menunggu pekerja (paling lewat sejam)…", "Waiting for the worker (an hour at most)…")}</span>}
          {req?.state === "refused" && <span className="text-xs text-danger">{t("Tidak dapat", "Could not")}: {req.note} · {stampMYT(req.done_at)}</span>}
          {req?.state === "done" && <span className="text-xs text-muted">{req.note} · {stampMYT(req.done_at)}</span>}
        </div>
      )}
    </div>
  );
}

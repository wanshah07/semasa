import { useEffect, useState } from "react";
import { Undo2 } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { stampMYT } from "../lib/format";
import Button from "./ui/Button";

/* Edit a post that is already scheduled (Wan, 10 Nov 2026: "make sure aku boleh ubah post untuk ws.regulab atau linkedin").
   Once the publisher has handed a post to Zernio that service holds its words, so the editor cannot change them. This asks the
   worker (supabase/076, backend/semasa/pullback.py) to take it out of the queue and put it back to DRAFT, with its date and slot
   kept; it then has to be approved again. Refused, with the reason, when a channel has already published. */
export default function PostPullBack({ post, onToast, onChanged }) {
  const { t } = useLang();
  const [req, setReq] = useState(null);
  const [busy, setBusy] = useState(false);
  const [missing, setMissing] = useState(false);

  async function load() {
    if (!supabase) return;
    const { data, error } = await supabase.from(TABLES.postPullbacks).select("id,state,note,requested_at,done_at")
      .eq("post_id", post.id).order("requested_at", { ascending: false }).limit(1);
    if (error) { setMissing(/does not exist|schema cache|relation/i.test(error.message || "")); return; }
    setReq((data || [])[0] || null);
  }
  useEffect(() => { load(); const id = setInterval(load, 20000); return () => clearInterval(id); }, [post.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (req?.state === "done") onChanged?.(); }, [req?.state]); // eslint-disable-line react-hooks/exhaustive-deps

  async function ask() {
    if (!window.confirm(t("Tarik post ini balik daripada jadual supaya boleh diubah? Ia menjadi draf (tarikh dan slot kekal) dan perlu diluluskan semula.",
      "Pull this post back from the schedule so it can be edited? It becomes a draft (date and slot kept) and must be approved again."))) return;
    setBusy(true);
    const { error } = await supabase.from(TABLES.postPullbacks).insert({ post_id: post.id });
    setBusy(false);
    if (error) return onToast?.(errText(error), "danger");
    onToast?.(t("Diminta. Pekerja menariknya balik dalam beberapa minit.", "Asked. The worker pulls it back within a few minutes."), "ok");
    load();
  }

  if (post.status !== "scheduled") return null;
  const pending = req?.state === "pending";
  return (
    <div className="rounded-tile border border-line bg-surface-2 p-3 text-sm" data-post-pullback>
      <p className="font-medium">{t("Post ini sudah dijadualkan", "This post is already scheduled")}</p>
      <p className="mt-0.5 text-xs text-muted">{t("Kata-katanya dipegang oleh perkhidmatan penjadual, jadi tidak boleh diubah di sini. Tarik balik untuk mengubahnya.",
        "Its words are held by the scheduler, so they cannot be changed here. Pull it back to edit them.")}</p>
      {missing ? <p className="mt-2 text-xs text-danger">{t("Migrasi 076 belum dijalankan di pangkalan data.", "Migration 076 has not been run on the database yet.")}</p> : (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Button size="sm" variant="soft" disabled={busy || pending} onClick={ask}><Undo2 size={12} /> {t("Tarik balik untuk ubah", "Pull back to edit")}</Button>
          {pending && <span className="text-xs text-muted">{t("Menunggu pekerja (paling lewat sejam)…", "Waiting for the worker (an hour at most)…")}</span>}
          {req?.state === "refused" && <span className="text-xs text-danger">{t("Ditolak", "Refused")}: {req.note} · {stampMYT(req.done_at)}</span>}
          {req?.state === "done" && <span className="text-xs text-muted">{req.note}</span>}
        </div>
      )}
    </div>
  );
}

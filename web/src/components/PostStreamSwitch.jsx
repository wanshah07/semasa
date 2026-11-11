import { useEffect, useState } from "react";
import { Repeat } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { STREAM_CHOICES, otherStreamRow } from "../lib/ideaPair";
import { useLang } from "../lib/i18n";
import Button from "./ui/Button";
import { Label, Segmented } from "./ui/Field";

/* For: ws.regulab | LinkedIn, on a post (Wan, 11 Nov 2026: "where is the button to switch the post for linkedin and ws regulab").
   The two voices are never mixed (ws.regulab speaks BM to SMEs, LinkedIn is Wan in English), so pressing the other stream does not
   convert this post: it sends a NEW idea for that stream, from the same issue, which the worker writes, draws and queues in its own
   voice, on its own slots. This post is not touched. A second press finds the idea already sent instead of making a duplicate. */
export default function PostStreamSwitch({ post, user, onToast, onChanged }) {
  const { t } = useLang();
  const now = post.stream === "linkedin" ? "linkedin" : "regulab";
  const other = now === "linkedin" ? "regulab" : "linkedin";
  const name = (s) => (s === "linkedin" ? "LinkedIn" : "ws.regulab");
  const [ask, setAsk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [made, setMade] = useState(null);

  useEffect(() => {
    let live = true;
    setMade(null); setAsk(false);
    if (!supabase || !post?.id) return undefined;
    supabase.from(TABLES.ideas).select("id,status,stream,created_at").eq("brief->>from_post", post.id).eq("stream", other)
      .order("created_at", { ascending: false }).limit(1)
      .then(({ data, error }) => { if (live && !error && data?.length) setMade(data[0]); });
    return () => { live = false; };
  }, [post?.id, other]);

  async function send() {
    if (busy) return;
    setBusy(true);
    let idea = null;
    if (post.idea_id) {
      const got = await supabase.from(TABLES.ideas).select("*").eq("id", post.idea_id).maybeSingle();
      idea = got.data || null;
    }
    const row = otherStreamRow(post, idea, { userId: user?.id || null,
      pairId: globalThis.crypto?.randomUUID?.() || `p${Date.now()}` });
    if (!row.source_title) { setBusy(false); return onToast(t("Post ini tiada tajuk untuk dijadikan idea.", "This post has no title to make an idea from."), "warn"); }
    const { data, error } = await supabase.from(TABLES.ideas).insert(row).select("id,status,stream,created_at").limit(1);
    setBusy(false);
    if (error) return onToast(errText(error), "danger");
    setMade(data?.[0] || { status: "new", stream: other });
    setAsk(false);
    onToast(t("Idea untuk {s} dihantar: ia ditulis dalam suaranya sendiri, dilukis dan dijadualkan di aliran itu. Anda lulus ia berasingan.",
      "Idea for {s} sent: it is written in its own voice, drawn and queued on that stream. You approve it separately.", { s: name(other) }), "ok");
    onChanged?.();
  }

  return (
    <div data-stream-switch className="space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        <Label>{t("Untuk", "For")}</Label>
        <Segmented value={now} onChange={(v) => { if (v !== now) setAsk(true); }} options={STREAM_CHOICES} />
        <span className="text-[11px] text-muted">{t("Post ini ialah versi {s}.", "This post is the {s} version.", { s: name(now) })}</span>
      </div>
      {made && (
        <p className="flex items-start gap-1.5 text-[12px] text-muted"><Repeat size={12} className="mt-0.5 shrink-0" />
          {t("Versi {s} sudah dihantar sebagai idea ({st}). Cari ia dalam Idea dan Post.", "The {s} version was already sent as an idea ({st}). Find it in Ideas and Posts.",
            { s: name(other), st: made.status || "new" })}</p>
      )}
      {ask && !made && (
        <div className="rounded-tile bg-accent/10 p-3 text-[12px]">
          <p>{t("Dua suara tidak dicampur: post ini tidak ditukar. Semasa menulis idea baharu untuk {s} daripada isu yang sama ({l}), melukis dan menjadualkannya di aliran itu.",
            "The two voices are never mixed, so this post is not converted. Semasa writes a new idea for {s} from the same issue ({l}), then draws and schedules it on that stream.",
            { s: name(other), l: other === "linkedin" ? t("Inggeris, suara Wan", "English, Wan's voice") : t("BM untuk PKS", "BM for SMEs") })}</p>
          <div className="mt-2 flex gap-2">
            <Button type="button" size="sm" disabled={busy} onClick={send}>{t("Buat versi {s}", "Make the {s} version", { s: name(other) })}</Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setAsk(false)}>{t("Batal", "Cancel")}</Button>
          </div>
        </div>
      )}
    </div>
  );
}

import { useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Clock, FileText, Loader2, Plus, RotateCcw, Trash2, XCircle } from "lucide-react";
import { fadeUp } from "../design/motion";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { timeAgo } from "../lib/format";
import { useLang } from "../lib/i18n";
import IdeaComposer from "../components/IdeaComposer";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";

// GitHub starts scheduled runs late or skips them when it is busy; the database dispatch
// (supabase/004 + the Vault token) is what wakes the bot at once. Until then, say so.
const WORKER_URL = "https://github.com/wanshah07/semasa/actions/workflows/media.yml";
const LATE_MIN = 20;

// label is [Malay, English], read through t() at render so it follows the language switch
const STATUS = {
  new: { icon: Clock, label: ["Menunggu bot", "Waiting for the bot"], cls: "text-warn bg-warn/10" },
  working: { icon: Loader2, label: ["Bot sedang menulis", "The bot is writing"], cls: "text-accent bg-accent/10", spin: true },
  drafted: { icon: CheckCircle2, label: ["Draf siap", "Draft ready"], cls: "text-ok bg-ok/10" },
  error: { icon: AlertTriangle, label: ["Gagal", "Failed"], cls: "text-danger bg-danger/10" },
  rejected: { icon: XCircle, label: ["Ditolak", "Rejected"], cls: "text-muted bg-surface-2" },
};

export default function IdeasTab({ ideas, user, brand, onToast, openPost }) {
  const { t, lang } = useLang();
  const [composer, setComposer] = useState(false);
  const [filter, setFilter] = useState("open");

  async function update(id, patch, msg) {
    const { error } = await supabase.from(TABLES.ideas).update(patch).eq("id", id);
    if (error) onToast(errText(error), "danger"); else { onToast(msg, "ok"); ideas.reload(); }
  }
  async function remove(id) {
    const { error } = await supabase.from(TABLES.ideas).delete().eq("id", id);
    if (error) onToast(errText(error), "danger"); else ideas.reload();
  }

  const shown = ideas.rows.filter((r) => (filter === "open" ? r.status !== "rejected" : r.status === "rejected"));
  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">{t("Aliran A", "Flow A")}</p>
          <h1 className="mt-2 text-4xl leading-tight">{t("Isu → idea → draf.", "Issue → idea → draft.")}</h1>
          <p className="mt-3 max-w-2xl text-sm text-muted">
            {lang === "en" ? (
              <>
                Press <b>Make an idea</b> on any issue, or write your own. The bot reads the source, writes a draft in the
                ws.regulab or LinkedIn voice, checks the Studio rules and generates a picture. The draft waits for your approval
                in the Posts tab.
              </>
            ) : (
              <>
                Tekan <b>Jadikan idea</b> pada mana-mana isu, atau tulis sendiri. Bot membaca sumber, menulis draf ikut suara
                ws.regulab atau LinkedIn, menyemak peraturan Studio, dan menjana gambar. Draf menunggu kelulusan anda di tab Post.
              </>
            )}
          </p>
        </div>
        <Button onClick={() => setComposer(true)}><Plus size={14} /> {t("Idea baharu", "New idea")}</Button>
      </motion.div>
      <div className="mt-6 flex gap-2 text-xs">
        {[["open", t("Aktif", "Active")], ["rejected", t("Ditolak", "Rejected")]].map(([v, l]) => (
          <button key={v} onClick={() => setFilter(v)}
            className={`rounded-pill px-3 py-1.5 ${filter === v ? "bg-ink text-bg" : "bg-surface-2 text-muted"}`}>{l}</button>
        ))}
      </div>
      {ideas.error && <p className="mt-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{ideas.error}</p>}
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {!shown.length && !ideas.loading && (
          <p className="rounded-card border border-dashed border-line p-10 text-center text-sm text-muted md:col-span-2">{t("Tiada idea di sini.", "No ideas here.")}</p>
        )}
        {shown.map((r) => {
          const st = STATUS[r.status] || STATUS.new;
          const Icon = st.icon;
          const src = r.brief?.source;
          return (
            <Card key={r.id} className="p-4">
              <div className="flex items-center justify-between gap-2">
                <span className={`inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 text-[11px] font-semibold ${st.cls}`}>
                  <Icon size={12} className={st.spin ? "animate-spin" : ""} /> {t(...st.label)}
                </span>
                <span className="text-[11px] text-muted">
                  {r.stream === "linkedin" ? "LinkedIn" : "ws.regulab"}{r.domain ? ` · ${r.domain}` : ""}{r.angle ? ` · ${r.angle}` : ""} · {{ image: t("imej", "image"), video: "video", none: t("tiada media", "no media") }[r.make_media] || r.make_media} · {timeAgo(r.created_at)}
                </span>
              </div>
              <h3 className="mt-2 font-display text-[17px] leading-snug">{r.source_title}</h3>
              {r.note && <p className="mt-1 text-sm text-muted">“{r.note}”</p>}
              {src && (
                <p className="mt-2 text-[11px] text-muted">
                  {src.ok ? t("Bot membaca artikel penuh.", "The bot read the full article.")
                    : t("Ditulis daripada tajuk sahaja: {why}.", "Written from the headline only: {why}.",
                      { why: src.why || t("artikel tidak dapat dibaca", "the article could not be read") })}
                </p>
              )}
              {r.error && <p className="mt-2 break-words rounded-tile bg-danger/5 p-2 text-[12px] text-danger">{r.error}</p>}
              {r.status === "new" && Date.now() - new Date(r.updated_at || r.created_at).getTime() > LATE_MIN * 60_000 && (
                <p className="mt-2 rounded-tile bg-warn/10 p-2 text-[12px] text-ink">
                  {t("Bot belum bermula: jadual GitHub kadang-kadang lewat atau terlepas. Mulakan sekarang di",
                    "The bot has not started: GitHub's schedule sometimes runs late or is skipped. Start it now at")}{" "}
                  <a href={WORKER_URL} target="_blank" rel="noopener noreferrer" className="font-medium text-accent underline">
                    GitHub → Generate media → Run workflow</a>.{" "}
                  {t("Token penghantaran dalam Vault (004, 009) membangunkan bot serta-merta.",
                    "The dispatch token in Vault (004, 009) wakes the bot at once.")}
                </p>
              )}
              <div className="mt-3 flex flex-wrap gap-2">
                {r.status === "drafted" && r.brief?.post_id && (
                  <Button size="sm" variant="soft" onClick={() => openPost(r.brief.post_id)}><FileText size={12} /> {t("Buka draf", "Open draft")}</Button>
                )}
                {(r.status === "error" || r.status === "rejected") && (
                  <Button size="sm" variant="soft" onClick={() => update(r.id, { status: "new", error: null }, t("Dihantar semula ke bot.", "Sent back to the bot."))}>
                    <RotateCcw size={12} /> {t("Cuba lagi", "Try again")}</Button>
                )}
                {(r.status === "new" || r.status === "error") && (
                  <Button size="sm" variant="ghost" onClick={() => update(r.id, { status: "rejected" }, t("Ditolak.", "Rejected."))}>
                    {t("Tolak", "Reject")}</Button>
                )}
                {r.status !== "working" && (
                  <Button size="sm" variant="danger" onClick={() => remove(r.id)} title={t("Padam idea", "Delete idea")}><Trash2 size={12} /></Button>
                )}
              </div>
            </Card>
          );
        })}
      </div>
      <IdeaComposer open={composer} onClose={() => setComposer(false)} trend={null} user={user} brand={brand}
        onToast={onToast} onDone={ideas.reload} />
    </main>
  );
}

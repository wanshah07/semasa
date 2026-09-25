import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Clock, Loader2, RotateCcw, Trash2 } from "lucide-react";
import { pop, stagger } from "../design/motion";
import { stampMYT, timeAgo } from "../lib/format";
import { useLang } from "../lib/i18n";
import Button from "./ui/Button";
import Card from "./ui/Card";
import { providersOf } from "./MediaUploader";

// A job that failed for want of a key is retried on the runner's default (Cloudflare once its secrets are set),
// not on the provider that has no key: on 25 Sep 2026 three jobs sat pinned to Replicate/OpenAI and every Retry
// failed the same way. Any other failure keeps the provider it had.
const KEY_PROBLEM = /is not set|must both be set|refused the (key|token)/i;
const retryDefault = (row) => (KEY_PROBLEM.test(row.error || "") ? "" : row.provider || "");

function Retry({ row, onRequeue }) {
  const { t } = useLang();
  const [provider, setProvider] = useState(() => retryDefault(row));
  return (
    <>
      <select value={provider} onChange={(e) => setProvider(e.target.value)} aria-label={t("Cuba semula dengan", "Retry with")}
        title={t("Cuba semula dengan", "Retry with")}
        className="max-w-[9rem] rounded-pill border border-line bg-surface px-2 py-1 text-[11px] text-ink outline-none">
        {providersOf(t).map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
      </select>
      <Button size="sm" variant="soft" onClick={() => onRequeue(row.id, provider)} title={t("Cuba lagi", "Try again")}><RotateCcw size={12} /></Button>
    </>
  );
}

const statusOf = (t) => ({
  pending: { icon: Clock, label: t("Menunggu", "Waiting"), cls: "text-warn bg-warn/10" },
  processing: { icon: Loader2, label: t("Menjana", "Generating"), cls: "text-accent bg-accent/10", spin: true },
  done: { icon: CheckCircle2, label: t("Siap", "Done"), cls: "text-ok bg-ok/10" },
  error: { icon: AlertTriangle, label: t("Gagal", "Failed"), cls: "text-danger bg-danger/10" },
});

function Media({ row }) {
  const { t } = useLang();
  if (row.status === "done" && row.generated_media_url) {
    return row.type === "video"
      ? <video src={row.generated_media_url} controls playsInline className="aspect-video w-full bg-black object-contain" />
      : <img src={row.generated_media_url} alt={row.prompt} loading="lazy" className="w-full object-cover" />;
  }
  if (!row.reference_url) {
    return <div className="grid aspect-video w-full place-items-center bg-surface-2 text-xs text-muted">{t("prompt sahaja", "prompt only")}</div>;
  }
  return (
    <div className="relative">
      <img src={row.reference_url} alt="" loading="lazy" className="w-full object-cover opacity-60" onError={(e) => { e.currentTarget.style.display = "none"; }} />
      <span className="absolute left-2 top-2 rounded-pill bg-ink/70 px-2 py-0.5 text-[10px] text-bg">{t("rujukan", "reference")}</span>
    </div>
  );
}

export default function GenerationGallery({ rows, user, onRequeue, onRemove }) {
  const { t } = useLang();
  if (!rows.length) {
    return <p className="rounded-card border border-dashed border-line p-10 text-center text-sm text-muted">{t("Belum ada kerja. Muat naik rujukan di atas.", "No jobs yet. Upload a reference above.")}</p>;
  }
  return (
    <motion.div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" variants={stagger(0.04)} initial="hidden" animate="show">
      <AnimatePresence>
        {rows.map((row) => {
          const STATUS = statusOf(t);
          const st = STATUS[row.status] || STATUS.pending;
          const Icon = st.icon;
          const mine = user && row.created_by === user.id;
          return (
            <motion.div key={row.id} variants={pop} layout exit="exit" className="min-w-0">
              <Card className="overflow-hidden">
                <Media row={row} />
                <div className="p-4">
                  <div className="flex items-center justify-between gap-2">
                    <span className={`inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 text-[11px] font-semibold ${st.cls}`}>
                      <Icon size={12} className={st.spin ? "animate-spin" : ""} /> {st.label}
                    </span>
                    <span className="text-[11px] text-muted" title={stampMYT(row.updated_at)}>{row.type} · {timeAgo(row.created_at)}</span>
                  </div>
                  <p className="mt-2 line-clamp-3 text-sm text-ink">{row.mode === "slides"
                    ? `${t("Slaid carousel · {n} slaid", ["Carousel slides · {n} slide", "Carousel slides · {n} slides"], { n: row.meta?.count || row.meta?.slides?.length || "?" })}${
                    row.meta?.slides?.[0]?.title ? `: ${row.meta.slides[0].title.replace(/\*/g, "")}` : ""}`
                    : row.prompt}</p>
                  {row.mode === "recreate" && (
                    <details className="mt-2 text-[12px] text-muted">
                      <summary className="cursor-pointer">{row.reference_read ? t("Apa yang bot baca pada rujukan", "What the bot read in the reference")
                        : t("Rujukan belum dibaca", "Reference not read yet")}</summary>
                      <p className="mt-1">{row.reference_read || (row.status === "done"
                        ? t("Tiada model penglihatan (VISION_MODEL): dijana daripada gambar dan prompt sahaja.",
                          "No vision model (VISION_MODEL): generated from the image and prompt only.")
                        : t("Bot membacanya apabila kerja ini bermula.", "The bot reads it when this job starts."))}</p>
                    </details>
                  )}
                  {(row.idea_id || row.post_id) && <p className="mt-1 text-[11px] text-accent">{t("Aliran A · untuk draf post", "Flow A · for a draft post")}</p>}
                  {row.error && <p className="mt-2 rounded-tile bg-danger/5 p-2 text-[11px] text-danger [overflow-wrap:anywhere]">{row.error}</p>}
                  <div className="mt-3 flex items-center justify-between text-[11px] text-muted">
                    <span>{row.provider || "—"}{row.model ? ` · ${row.model}` : ""}{row.attempts ? ` · ${t("cubaan {n}", "attempt {n}", { n: row.attempts })}` : ""}</span>
                    {mine && (
                      <span className="flex items-center gap-1">
                        {row.status === "error" && (
                          <Retry row={row} onRequeue={onRequeue} />
                        )}
                        {row.status !== "processing" && (
                          <Button size="sm" variant="danger" onClick={() => onRemove(row)} title={t("Padam", "Delete")}><Trash2 size={12} /></Button>
                        )}
                      </span>
                    )}
                  </div>
                  {row.generated_media_url && (
                    <a href={row.generated_media_url} target="_blank" rel="noopener noreferrer" className="mt-2 block text-[11px] text-accent hover:underline">
                      {t("Buka fail penuh", "Open full file")}
                    </a>
                  )}
                </div>
              </Card>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </motion.div>
  );
}

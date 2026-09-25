import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Clock, Loader2, RotateCcw, Trash2 } from "lucide-react";
import { pop, stagger } from "../design/motion";
import { stampMYT, timeAgo } from "../lib/format";
import Button from "./ui/Button";
import Card from "./ui/Card";

const STATUS = {
  pending: { icon: Clock, label: "Menunggu", cls: "text-warn bg-warn/10" },
  processing: { icon: Loader2, label: "Menjana", cls: "text-accent bg-accent/10", spin: true },
  done: { icon: CheckCircle2, label: "Siap", cls: "text-ok bg-ok/10" },
  error: { icon: AlertTriangle, label: "Gagal", cls: "text-danger bg-danger/10" },
};

function Media({ row }) {
  if (row.status === "done" && row.generated_media_url) {
    return row.type === "video"
      ? <video src={row.generated_media_url} controls playsInline className="aspect-video w-full bg-black object-contain" />
      : <img src={row.generated_media_url} alt={row.prompt} loading="lazy" className="w-full object-cover" />;
  }
  if (!row.reference_url) {
    return <div className="grid aspect-video w-full place-items-center bg-surface-2 text-xs text-muted">prompt sahaja</div>;
  }
  return (
    <div className="relative">
      <img src={row.reference_url} alt="" loading="lazy" className="w-full object-cover opacity-60" onError={(e) => { e.currentTarget.style.display = "none"; }} />
      <span className="absolute left-2 top-2 rounded-pill bg-ink/70 px-2 py-0.5 text-[10px] text-bg">rujukan</span>
    </div>
  );
}

export default function GenerationGallery({ rows, user, onRequeue, onRemove }) {
  if (!rows.length) {
    return <p className="rounded-card border border-dashed border-line p-10 text-center text-sm text-muted">Belum ada kerja. Muat naik rujukan di atas.</p>;
  }
  return (
    <motion.div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" variants={stagger(0.04)} initial="hidden" animate="show">
      <AnimatePresence>
        {rows.map((row) => {
          const st = STATUS[row.status] || STATUS.pending;
          const Icon = st.icon;
          const mine = user && row.created_by === user.id;
          return (
            <motion.div key={row.id} variants={pop} layout exit="exit">
              <Card className="overflow-hidden">
                <Media row={row} />
                <div className="p-4">
                  <div className="flex items-center justify-between gap-2">
                    <span className={`inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 text-[11px] font-semibold ${st.cls}`}>
                      <Icon size={12} className={st.spin ? "animate-spin" : ""} /> {st.label}
                    </span>
                    <span className="text-[11px] text-muted" title={stampMYT(row.updated_at)}>{row.type} · {timeAgo(row.created_at)}</span>
                  </div>
                  <p className="mt-2 line-clamp-3 text-sm text-ink">{row.prompt}</p>
                  {row.mode === "recreate" && (
                    <details className="mt-2 text-[12px] text-muted">
                      <summary className="cursor-pointer">{row.reference_read ? "Apa yang bot baca pada rujukan" : "Rujukan belum dibaca"}</summary>
                      <p className="mt-1">{row.reference_read || (row.status === "done"
                        ? "Tiada model penglihatan (VISION_MODEL): dijana daripada gambar dan prompt sahaja."
                        : "Bot membacanya apabila kerja ini bermula.")}</p>
                    </details>
                  )}
                  {(row.idea_id || row.post_id) && <p className="mt-1 text-[11px] text-accent">Aliran A · untuk draf post</p>}
                  {row.error && <p className="mt-2 break-words rounded-tile bg-danger/5 p-2 text-[11px] text-danger">{row.error}</p>}
                  <div className="mt-3 flex items-center justify-between text-[11px] text-muted">
                    <span>{row.provider || "—"}{row.model ? ` · ${row.model}` : ""}{row.attempts ? ` · cubaan ${row.attempts}` : ""}</span>
                    {mine && (
                      <span className="flex gap-1">
                        {row.status === "error" && (
                          <Button size="sm" variant="soft" onClick={() => onRequeue(row.id)} title="Cuba lagi"><RotateCcw size={12} /></Button>
                        )}
                        {row.status !== "processing" && (
                          <Button size="sm" variant="danger" onClick={() => onRemove(row)} title="Padam"><Trash2 size={12} /></Button>
                        )}
                      </span>
                    )}
                  </div>
                  {row.generated_media_url && (
                    <a href={row.generated_media_url} target="_blank" rel="noopener noreferrer" className="mt-2 block text-[11px] text-accent hover:underline">
                      Buka fail penuh
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

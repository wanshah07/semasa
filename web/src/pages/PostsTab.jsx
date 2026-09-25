import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { ShieldOff } from "lucide-react";
import { fadeUp } from "../design/motion";
import { hardCount, langOf, scan, textOf, platformsFor } from "../lib/compliance";
import PostEditor from "../components/PostEditor";
import Card from "../components/ui/Card";

const TABS = [["draft", "Draf"], ["approved", "Diluluskan"], ["scheduled", "Dijadualkan"], ["posted", "Diterbitkan"], ["rejected", "Ditolak"]];
const TONE = { draft: "bg-surface-2 text-muted", approved: "bg-ok/10 text-ok", scheduled: "bg-accent/10 text-accent",
  posted: "bg-ink text-bg", rejected: "bg-surface-2 text-muted line-through" };

export default function PostsTab({ posts, media, log, brand, user, settings, onToast, focusId, setFocusId }) {
  const [status, setStatus] = useState("draft");
  const mediaById = useMemo(() => Object.fromEntries(media.rows.map((m) => [m.id, m])), [media.rows]);

  useEffect(() => {
    if (!focusId) return;
    const p = posts.rows.find((r) => r.id === focusId);
    if (p) setStatus(p.status);
  }, [focusId, posts.rows]);

  const counts = useMemo(() => {
    const c = {};
    for (const p of posts.rows) c[p.status] = (c[p.status] || 0) + 1;
    return c;
  }, [posts.rows]);
  const shown = posts.rows.filter((p) => p.status === status)
    .sort((a, b) => `${a.date || "9"}${a.slot || ""}`.localeCompare(`${b.date || "9"}${b.slot || ""}`));
  const publishing = settings.publishing || {};

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div variants={fadeUp} initial="hidden" animate="show">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">Post</p>
        <h1 className="mt-2 text-4xl leading-tight">Satu pintu: kelulusan anda.</h1>
        <p className="mt-3 max-w-2xl text-sm text-muted">
          Setiap draf disemak dengan peraturan yang sama seperti Studio (tiada CTA, tiada laman web dalam kapsyen, tiada
          [SAHKAN] tertunggak, tiada sumber media sosial, BM Malaysia). Hanya post yang anda luluskan akan dihantar.
        </p>
      </motion.div>

      {!publishing.enabled && (
        <p className="mt-5 flex items-start gap-2 rounded-tile border border-warn/40 bg-warn/10 p-3 text-sm text-ink">
          <ShieldOff size={16} className="mt-0.5 shrink-0 text-warn" />
          <span><b>Penerbitan dimatikan.</b> Semasa belum menghantar apa-apa ke Buffer atau LinkedIn. Penerbit berjalan
            sebagai cubaan kering dan merekod apa yang <i>akan</i> dihantar (lihat log dalam setiap post). Ia hanya boleh
            dihidupkan di Supabase SQL editor, dan hanya selepas Routine ws.regulab Studio dimatikan.</span>
        </p>
      )}

      <div className="mt-6 flex flex-wrap gap-2 text-xs">
        {TABS.map(([v, l]) => (
          <button key={v} onClick={() => setStatus(v)}
            className={`rounded-pill px-3 py-1.5 ${status === v ? "bg-ink text-bg" : "bg-surface-2 text-muted"}`}>
            {l} {counts[v] ? `· ${counts[v]}` : ""}
          </button>
        ))}
      </div>
      {posts.error && <p className="mt-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{posts.error}</p>}

      <div className="mt-4 space-y-3">
        {!shown.length && !posts.loading && (
          <p className="rounded-card border border-dashed border-line p-10 text-center text-sm text-muted">Tiada post di sini.</p>
        )}
        {shown.map((p) => {
          const open = focusId === p.id;
          const lang = langOf(p);
          const first = textOf(p, platformsFor(p.stream)[0], lang);
          const pics = (p.media_ids || []).map((id) => mediaById[id]).filter((m) => m && m.status === "done");
          const hard = hardCount(scan({ ...p, media: pics.map((m) => ({ alt: m.meta?.alt || "" })) }, brand.regulab, brand.regulab.schedule));
          return (
            <Card key={p.id} className={`p-4 ${open ? "ring-2 ring-accent/40" : ""}`}>
              {!open ? (
                <button type="button" className="flex w-full items-start gap-3 text-left" onClick={() => setFocusId(p.id)}>
                  {pics[0]
                    ? (pics[0].type === "video"
                      ? <video src={pics[0].generated_media_url} className="h-16 w-16 shrink-0 rounded-tile bg-black object-cover" muted />
                      : <img src={pics[0].generated_media_url} alt="" className="h-16 w-16 shrink-0 rounded-tile object-cover" />)
                    : <span className="h-16 w-16 shrink-0 rounded-tile bg-surface-2" />}
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
                      <span className={`rounded-pill px-2 py-0.5 ${TONE[p.status]}`}>{p.status}</span>
                      <span>{p.stream === "linkedin" ? "LinkedIn" : "ws.regulab"}{p.domain ? ` · ${p.domain}` : ""}{p.angle ? ` · ${p.angle}` : ""}</span>
                      <span>{p.date ? `${p.date} ${p.slot || ""} MYT` : "tiada slot"}</span>
                      <span className={hard ? "text-danger" : "text-ok"}>{hard ? `■ ${hard} sekatan` : "✓ semakan lulus"}</span>
                    </span>
                    <span className="mt-1 block truncate font-display text-[16px]">{p.hook || first.split("\n")[0] || "(tiada kapsyen)"}</span>
                  </span>
                </button>
              ) : (
                <PostEditor post={p} mediaById={mediaById} mediaRows={media.rows} log={log.rows} brand={brand} user={user}
                  onToast={onToast} onChanged={() => { posts.reload(); media.reload(); }} onClose={() => setFocusId(null)} />
              )}
            </Card>
          );
        })}
      </div>
    </main>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, ShieldOff, Timer } from "lucide-react";
import { fadeUp } from "../design/motion";
import { useLang } from "../lib/i18n";
import { hardCount, langOf, scan, scanMedia, textOf, platformsFor } from "../lib/compliance";
import PostEditor from "../components/PostEditor";
import IdeaComposer from "../components/IdeaComposer";
import ScheduleView from "../components/ScheduleView";
import { fmtLeft, isPastDue, purgeLeftMs, refOf } from "../lib/slots";
import Card from "../components/ui/Card";
import ViewToggle, { TBODY, TD, TH, THEAD, TR, TableFrame, useView } from "../components/ViewToggle";

const tabsOf = (t) => [["draft", t("Draf", "Drafts")], ["approved", t("Diluluskan", "Approved")], ["scheduled", t("Dijadualkan", "Scheduled")],
  ["posted", t("Diterbitkan", "Published")], ["archived", t("Arkib", "Archive")], ["rejected", t("Ditolak", "Rejected")],
  ["schedule", t("Jadual", "Schedule")]];
// a published post is archived (and compacted) by the publisher 24 hours after it went out (supabase/010_archive.sql)
const bucketOf = (p) => (p.status === "posted" && p.archived_at ? "archived" : p.status);
const TONE = { draft: "bg-surface-2 text-muted", approved: "bg-ok/10 text-ok", scheduled: "bg-accent/10 text-accent",
  posted: "bg-ink text-bg", archived: "bg-surface-2 text-muted", rejected: "bg-surface-2 text-muted line-through" };

function Thumb({ pic, small }) {
  const size = small ? "h-12 w-12" : "h-16 w-16";
  if (!pic) return <span className={`${size} block shrink-0 rounded-tile bg-surface-2`} />;
  return pic.type === "video"
    ? <video src={pic.generated_media_url} className={`${size} shrink-0 rounded-tile bg-black object-cover`} muted />
    : <img src={pic.generated_media_url} alt="" className={`${size} shrink-0 rounded-tile object-cover`} />;
}

export default function PostsTab({ posts, media, log, brand, user, settings, onToast, focusId, setFocusId }) {
  const { lang: uiLang, t } = useLang();
  const [status, setStatus] = useState("draft");
  const [view, setView] = useView("post");
  const [streamF, setStreamF] = useState("all");
  const [slotIdea, setSlotIdea] = useState(null);     // an empty Schedule slot being written for (kept stable while open)
  const mediaById = useMemo(() => Object.fromEntries(media.rows.map((m) => [m.id, m])), [media.rows]);

  // Move to the opened post's tab once per opening. It used to run on every change to posts.rows, so any live update
  // (the worker attaching a picture) threw Wan back from the tab he had just chosen, and closed an editor with unsaved
  // typing. A post opened before it has loaded (fresh from an idea) is still followed when it arrives.
  const followed = useRef(null);
  useEffect(() => {
    if (!focusId) { followed.current = null; return; }
    if (followed.current === focusId) return;
    const p = posts.rows.find((r) => r.id === focusId);
    if (p) { setStatus(bucketOf(p)); followed.current = focusId; }
  }, [focusId, posts.rows]);
  // the post opened from a row or a card is edited at the top of the list: bring it into view
  useEffect(() => {
    if (!focusId) return;
    const id = window.setTimeout(() => document.getElementById("post-editor")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    return () => window.clearTimeout(id);
  }, [focusId]);

  const counts = useMemo(() => {
    const c = {};
    for (const p of posts.rows) c[bucketOf(p)] = (c[bucketOf(p)] || 0) + 1;
    return c;
  }, [posts.rows]);
  const shown = posts.rows.filter((p) => bucketOf(p) === status && (streamF === "all" || (p.stream || "regulab") === streamF))
    .sort((a, b) => `${a.date || "9"}${a.slot || ""}`.localeCompare(`${b.date || "9"}${b.slot || ""}`));
  const publishing = settings.publishing || {};
  const summary = (p) => {
    const lang = langOf(p);
    const first = textOf(p, platformsFor(p.stream)[0], lang);
    const pics = (p.media_ids || []).map((id) => mediaById[id]).filter((m) => m && m.status === "done");
    return {
      pics, label: (tabsOf(t).find(([v]) => v === bucketOf(p)) || [null, p.status])[1],
      forText: `${p.stream === "linkedin" ? "LinkedIn" : "ws.regulab"}${p.domain ? ` · ${p.domain}` : ""}${p.angle ? ` · ${p.angle}` : ""}${p.pillar ? ` · ${p.pillar}` : ""}`,
      hook: p.hook || first.split("\n")[0] || t("(tiada kapsyen)", "(no caption)"),
      hard: hardCount(scan({ ...p, media: pics.map(scanMedia) }, brand.regulab, brand.regulab.schedule, settings.bahasa?.indo)),
      ref: refOf(p, brand), late: isPastDue(p), purge: purgeLeftMs(p),
    };
  };

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div variants={fadeUp} initial="hidden" animate="show">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">Post</p>
        <h1 className="mt-2 text-4xl leading-tight">{t("Satu pintu: kelulusan anda.", "One gate: your approval.")}</h1>
        <p className="mt-3 max-w-2xl text-sm text-muted">
          {t("Setiap draf disemak dengan peraturan yang sama seperti Studio (tiada CTA, tiada laman web dalam kapsyen, "
            + "tiada sumber media sosial, BM Malaysia). Hanya post yang anda luluskan akan dihantar.",
          "Every draft is checked against the same rules as Studio (no CTA, no website in a caption, "
            + "no social media source, Malaysian BM). Only posts you approve are sent.")}
        </p>
      </motion.div>

      {!publishing.enabled && (
        <p className="mt-5 flex items-start gap-2 rounded-tile border border-warn/40 bg-warn/10 p-3 text-sm text-ink">
          <ShieldOff size={16} className="mt-0.5 shrink-0 text-warn" />
          {uiLang === "en" ? (
            <span><b>Publishing is off.</b> Semasa has not sent anything to Buffer or LinkedIn. The publisher runs
              as a dry run and records what it <i>would</i> send (see the log in each post). It can only be
              switched on in the Supabase SQL editor, and only after the ws.regulab Studio Routine is switched off.</span>
          ) : (
            <span><b>Penerbitan dimatikan.</b> Semasa belum menghantar apa-apa ke Buffer atau LinkedIn. Penerbit berjalan
              sebagai cubaan kering dan merekod apa yang <i>akan</i> dihantar (lihat log dalam setiap post). Ia hanya boleh
              dihidupkan di Supabase SQL editor, dan hanya selepas Routine ws.regulab Studio dimatikan.</span>
          )}
        </p>
      )}

      <div className="mt-6 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-2 text-xs">
          {tabsOf(t).map(([v, l]) => (
            <button key={v} onClick={() => setStatus(v)} aria-pressed={status === v}
              className={`rounded-pill px-3 py-1.5 ${status === v ? "bg-ink text-bg" : "bg-surface-2 text-muted"}`}>
              {l} {counts[v] ? `· ${counts[v]}` : ""}
            </button>
          ))}
        </div>
        {status !== "schedule" && (
          <div className="flex items-center gap-2">
            <select value={streamF} onChange={(e) => setStreamF(e.target.value)} aria-label={t("Aliran", "Stream")}
              className="rounded-pill border border-line bg-surface px-3 py-1.5 text-xs">
              <option value="all">{t("Semua", "All")}</option><option value="regulab">ws.regulab</option><option value="linkedin">LinkedIn</option>
            </select>
            <ViewToggle view={view} setView={setView} />
          </div>
        )}
      </div>
      {status === "rejected" && shown.length > 0 && (
        <p className="mt-3 text-[12px] text-muted">{t("Post ditolak dipadam sendiri 72 jam selepas ditolak (kecuali yang ada rekod penghantaran). Pulihkan sebelum itu jika perlu.",
          "A rejected post deletes itself 72 hours after it was rejected (except one with a delivery record). Restore it before then if needed.")}</p>
      )}
      {posts.error && <p className="mt-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{posts.error}</p>}

      {status === "schedule" && (
        <ScheduleView posts={posts.rows} brand={brand} onToast={onToast} onChanged={() => posts.reload()}
          onOpen={(id) => { const p = posts.rows.find((r) => r.id === id); if (p) setStatus(bucketOf(p)); setFocusId(id); }}
          onNewIdea={setSlotIdea} />
      )}
      <IdeaComposer open={Boolean(slotIdea)} onClose={() => setSlotIdea(null)} trend={null} position={slotIdea} user={user} brand={brand}
        onToast={onToast} onDone={() => posts.reload()} />
      {status !== "schedule" && !shown.length && !posts.loading && (
        <p className="mt-4 rounded-card border border-dashed border-line p-10 text-center text-sm text-muted">{t("Tiada post di sini.", "No posts here.")}</p>
      )}
      {/* the post being edited opens above the list in either view */}
      {shown.filter((p) => p.id === focusId).map((p) => (
        <Card key={p.id} id="post-editor" className="mt-4 scroll-mt-32 p-4 ring-2 ring-accent/40">
          <PostEditor post={p} posts={posts.rows} mediaById={mediaById} mediaRows={media.rows} log={log.rows} brand={brand} user={user}
            indoExtra={settings.bahasa?.indo}
            onToast={onToast} onChanged={() => { posts.reload(); media.reload(); }} onClose={() => setFocusId(null)} />
        </Card>
      ))}
      {status === "schedule" ? null : view === "table" && shown.length > 0 ? (
        <div className="mt-4">
          <TableFrame label={t("Post", "Posts")}>
            <thead className={THEAD}>
              <tr>
                <th className={TH}>{t("Gambar", "Picture")}</th>
                <th className={TH}>Status</th>
                <th className={TH}>{t("Slot", "Slot")}</th>
                <th className={TH}>{t("Untuk", "For")}</th>
                <th className={`${TH} w-[36%]`}>{t("Cangkuk", "Hook")}</th>
                <th className={TH}>{t("Semakan", "Checks")}</th>
              </tr>
            </thead>
            <tbody className={TBODY}>
              {shown.map((p) => {
                const s = summary(p);
                return (
                  <tr key={p.id} onClick={() => setFocusId(p.id)} className={`${TR} cursor-pointer hover:bg-surface-2/50 ${focusId === p.id ? "bg-accent/5" : ""}`}>
                    <td className={TD} data-label={t("Gambar", "Picture")}><Thumb pic={s.pics[0]} small /></td>
                    <td className={TD} data-label="Status"><span className={`whitespace-nowrap rounded-pill px-2 py-0.5 text-[11px] ${TONE[bucketOf(p)]}`}>{s.label}</span></td>
                    <td className={`${TD} whitespace-nowrap text-[12px] text-muted`} data-label={t("Slot", "Slot")}>{p.date ? `${p.date} ${p.slot || ""}` : t("tiada slot", "no slot")}
                      {s.ref && <span className="block text-[10.5px]">{s.ref}</span>}
                      {s.late && <span className="block text-danger">{t("slot sudah lepas", "slot passed")}</span>}
                      {s.purge !== null && <span className="block">{t("dipadam dalam {x}", "deleted in {x}", { x: fmtLeft(s.purge) })}</span>}</td>
                    <td className={`${TD} text-[12px] text-muted`} data-label={t("Untuk", "For")}>{s.forText}</td>
                    <td className={`${TD} [overflow-wrap:anywhere]`} data-label={t("Cangkuk", "Hook")}><button type="button" className="text-left font-medium leading-snug hover:text-accent" onClick={() => setFocusId(p.id)}>
                      <span className="line-clamp-2">{s.hook}</span></button></td>
                    <td className={`${TD} whitespace-nowrap text-[12px] ${s.hard ? "text-danger" : "text-ok"}`} data-label={t("Semakan", "Checks")}>
                      {s.hard ? `■ ${t("{n} sekatan", "{n} blocking", { n: s.hard })}` : t("✓ lulus", "✓ passed")}</td>
                  </tr>
                );
              })}
            </tbody>
          </TableFrame>
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          {shown.filter((p) => p.id !== focusId).map((p) => {
            const s = summary(p);
            return (
              <Card key={p.id} className="min-w-0 p-4">
                <button type="button" className="flex w-full items-start gap-3 text-left" onClick={() => setFocusId(p.id)}>
                  <Thumb pic={s.pics[0]} />
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
                      <span className={`rounded-pill px-2 py-0.5 ${TONE[bucketOf(p)]}`}>{s.label}</span>
                      <span>{s.forText}</span>
                      <span>{p.date ? `${p.date} ${p.slot || ""} MYT` : t("tiada slot", "no slot")}{s.ref ? ` · ${s.ref}` : ""}</span>
                      {s.late && <span className="flex items-center gap-1 text-danger"><AlertTriangle size={11} /> {t("slot sudah lepas", "slot passed")}</span>}
                      {s.purge !== null && <span className="flex items-center gap-1"><Timer size={11} /> {t("dipadam dalam {x}", "deleted in {x}", { x: fmtLeft(s.purge) })}</span>}
                      <span className={s.hard ? "text-danger" : "text-ok"}>{s.hard ? `■ ${t("{n} sekatan", "{n} blocking", { n: s.hard })}` : t("✓ semakan lulus", "✓ checks passed")}</span>
                    </span>
                    <span className="mt-1 line-clamp-2 block [overflow-wrap:anywhere] font-display text-[16px] leading-snug">{s.hook}</span>
                  </span>
                </button>
              </Card>
            );
          })}
        </div>
      )}
    </main>
  );
}

import { useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, CalendarClock, CheckCircle2, Clock, ExternalLink, FileText, Loader2, Pencil, Plus, RotateCcw, Search, Trash2, XCircle } from "lucide-react";
import { fadeUp } from "../design/motion";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { timeAgo } from "../lib/format";
import { useLang } from "../lib/i18n";
import IdeaComposer from "../components/IdeaComposer";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { Input, Select, TextArea } from "../components/ui/Field";
import ViewToggle, { TBODY, TD, TH, THEAD, TR, TableFrame, useView } from "../components/ViewToggle";

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

function StatusChip({ r }) {
  const { t } = useLang();
  const st = STATUS[r.status] || STATUS.new;
  const Icon = st.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-pill px-2.5 py-1 text-[11px] font-semibold ${st.cls}`}>
      <Icon size={12} className={st.spin ? "animate-spin" : ""} /> {t(...st.label)}
    </span>
  );
}

/* A failed idea can be given a note before it is tried again. The worker's refusal for news that already has a post
   says "add a note saying what the new post should say, then Cuba lagi", and without this there was nowhere to add
   one, so Cuba lagi met the same refusal every time. */
function NoteRetry({ r, onSave }) {
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState(r.note || "");
  const [busy, setBusy] = useState(false);
  if (!open) {
    return <Button size="sm" variant="ghost" onClick={() => { setNote(r.note || ""); setOpen(true); }}>
      {r.note ? t("Ubah nota", "Edit note") : t("Tambah nota", "Add a note")}</Button>;
  }
  return (
    <div className="mt-2 w-full space-y-2">
      <TextArea rows={3} value={note} onChange={(e) => setNote(e.target.value)} maxLength={1500} autoFocus
        placeholder={t("Apa yang post baharu patut katakan (contoh: susulan, apa yang berubah)", "What the new post should say (for example: a follow-up, what changed)")} />
      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={busy || !note.trim()} onClick={async () => {
          setBusy(true); await onSave(note.trim()); setBusy(false); setOpen(false);
        }}><RotateCcw size={12} /> {t("Simpan nota & cuba lagi", "Save note & try again")}</Button>
        <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>{t("Batal", "Cancel")}</Button>
      </div>
    </div>
  );
}

/* Studio's idea editor: an idea still waiting (or failed) is changed in place before the bot writes it. The database
   allows the page to edit an idea only while it is new, rejected or failed (005), which is exactly when this shows. */
function IdeaEdit({ r, brand, onSave, onCancel }) {
  const { t } = useLang();
  const [f, setF] = useState({ source_title: r.source_title || "", note: r.note || "", domain: r.domain || "", angle: r.angle || "",
    make_media: r.make_media || "image" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (v) => setF((x) => ({ ...x, [k]: v?.target ? v.target.value : v }));
  const domains = Object.entries(brand?.regulab?.domains || {});
  const angles = Object.entries(brand?.linkedin?.angles || {});
  return (
    <div className="mt-2 w-full space-y-2 rounded-tile border border-line p-2">
      <Input value={f.source_title} onChange={set("source_title")} maxLength={500} aria-label={t("Isu / tajuk", "Issue / title")} />
      <TextArea rows={2} value={f.note} onChange={set("note")} maxLength={1500}
        placeholder={t("Nota untuk bot (pilihan)", "A note for the bot (optional)")} />
      <div className="flex flex-wrap gap-2">
        {r.stream === "linkedin"
          ? <Select value={f.angle} onChange={set("angle")} aria-label={t("Sudut", "Angle")}
              options={[["", t("Bot pilih", "Bot chooses")], ...angles.map(([k, v]) => [k, `${k} · ${v}`])]} />
          : <Select value={f.domain} onChange={set("domain")} aria-label="Domain"
              options={[["", t("Bot pilih", "Bot chooses")], ...domains]} />}
        <Select value={f.make_media} onChange={set("make_media")} aria-label="Media"
          options={[["image", t("Imej", "Image")], ["video", "Video"], ["none", t("Tiada media", "No media")]]} />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={busy || !f.source_title.trim()} onClick={async () => {
          setBusy(true);
          await onSave({ source_title: f.source_title.trim(), note: f.note.trim(), make_media: f.make_media,
            ...(r.stream === "linkedin" ? { angle: f.angle || null } : { domain: f.domain || null }) });
          setBusy(false);
        }}>{t("Simpan", "Save")}</Button>
        <Button size="sm" variant="ghost" onClick={onCancel}>{t("Batal", "Cancel")}</Button>
      </div>
    </div>
  );
}

const hostOf = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return ""; } };

/* Where an idea came from and what it is for, as pills: the source's own site (a link back, never into a post), the
   issuer when it is a regulator or journal, a replacement for a rejected draft, and the slot it was made for. */
function SourcePills({ r }) {
  const { t } = useLang();
  const host = hostOf(r.source_url);
  const pos = r.brief?.position;
  const pill = "inline-flex max-w-full items-center gap-1 truncate rounded-pill bg-surface-2 px-2 py-0.5 text-[11px] text-muted";
  if (!host && !r.source_name && !r.brief?.replaces && !pos && !r.brief?.auto) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {host && <a href={r.source_url} target="_blank" rel="noopener noreferrer" className={`${pill} hover:text-ink`} title={r.source_url}>
        <ExternalLink size={10} className="shrink-0" /> {host}</a>}
      {r.source_name && hostOf(`https://${r.source_name}`) !== host && <span className={pill}>{r.source_name}</span>}
      {r.brief?.auto && <span className={`${pill} text-accent`}>{t("Auto-isi slot kosong", "Auto-filled empty slot")}</span>}
      {r.brief?.replaces && <span className={`${pill} text-warn`}>{t("Pengganti draf ditolak", "Replaces a rejected draft")}</span>}
      {pos?.date && <span className={pill}><CalendarClock size={10} className="shrink-0" /> {t("Untuk {d} {s}", "For {d} {s}", { d: pos.date, s: pos.slot })}</span>}
    </div>
  );
}

function LateNote({ r }) {
  const { t } = useLang();
  if (!(r.status === "new" && Date.now() - new Date(r.updated_at || r.created_at).getTime() > LATE_MIN * 60_000)) return null;
  return (
    <p className="mt-2 rounded-tile bg-warn/10 p-2 text-[12px] text-ink">
      {t("Bot belum bermula: jadual GitHub kadang-kadang lewat atau terlepas. Mulakan sekarang di",
        "The bot has not started: GitHub's schedule sometimes runs late or is skipped. Start it now at")}{" "}
      <a href={WORKER_URL} target="_blank" rel="noopener noreferrer" className="font-medium text-accent underline">
        GitHub → Generate media → Run workflow</a>.{" "}
      {t("Token penghantaran dalam Vault (004, 009) membangunkan bot serta-merta.",
        "The dispatch token in Vault (004, 009) wakes the bot at once.")}
    </p>
  );
}

export default function IdeasTab({ ideas, posts, user, brand, onToast, openPost }) {
  const { t, lang } = useLang();
  const [composer, setComposer] = useState(false);
  const [filter, setFilter] = useState("open");
  const [streamF, setStreamF] = useState("all");
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState(null);
  const [view, setView] = useView("idea");

  async function update(id, patch, msg) {
    const { error } = await supabase.from(TABLES.ideas).update(patch).eq("id", id);
    if (error) onToast(errText(error), "danger"); else { onToast(msg, "ok"); ideas.reload(); }
  }
  // an idea whose post is approved or out is how the bot knows that news was already written (supabase/019 keeps it)
  const published = new Set((posts?.rows || []).filter((p) => ["approved", "scheduled", "posted"].includes(p.status) && p.idea_id).map((p) => p.idea_id));
  async function remove(id) {
    if (!window.confirm(t("Padam idea ini?", "Delete this idea?"))) return;
    const { error } = await supabase.from(TABLES.ideas).delete().eq("id", id);
    if (error) onToast(errText(error), "danger"); else ideas.reload();
  }

  const inFilter = (r) => ({ open: r.status !== "rejected", waiting: r.status === "new" || r.status === "working",
    error: r.status === "error", drafted: r.status === "drafted", rejected: r.status === "rejected" })[filter];
  const needle = q.trim().toLowerCase();
  const shown = ideas.rows.filter((r) => inFilter(r) && (streamF === "all" || (r.stream || "regulab") === streamF)
    && (!needle || [r.source_title, r.note, r.source_name, r.source_url, r.domain, r.angle].some((x) => String(x || "").toLowerCase().includes(needle))));
  const count = (k) => ideas.rows.filter((r) => ({ open: r.status !== "rejected", waiting: r.status === "new" || r.status === "working",
    error: r.status === "error", drafted: r.status === "drafted", rejected: r.status === "rejected" })[k]).length;
  const forText = (r) => `${r.stream === "linkedin" ? "LinkedIn" : "ws.regulab"}${r.domain ? ` · ${r.domain}` : ""}${r.angle ? ` · ${r.angle}` : ""} · ${
    { image: t("imej", "image"), video: "video", none: t("tiada media", "no media") }[r.make_media] || r.make_media}${
    r.brief?.format === "poster" ? " · poster" : r.make_slides || r.brief?.format === "carousel" ? " · carousel" : ""}`;
  const actions = (r) => (
    <>
      {r.status === "drafted" && r.brief?.post_id && (
        <Button size="sm" variant="soft" onClick={() => openPost(r.brief.post_id)}><FileText size={12} /> {t("Buka draf", "Open draft")}</Button>
      )}
      {(r.status === "error" || r.status === "rejected") && (
        <Button size="sm" variant="soft" onClick={() => update(r.id, { status: "new", error: null }, t("Dihantar semula ke bot.", "Sent back to the bot."))}>
          <RotateCcw size={12} /> {t("Cuba lagi", "Try again")}</Button>
      )}
      {r.status === "error" && (
        <NoteRetry r={r} onSave={(note) => update(r.id, { note, status: "new", error: null }, t("Nota disimpan, dihantar semula ke bot.", "Note saved, sent back to the bot."))} />
      )}
      {(r.status === "new" || r.status === "error") && editing !== r.id && (
        <Button size="sm" variant="ghost" onClick={() => setEditing(r.id)}><Pencil size={12} /> {t("Ubah", "Edit")}</Button>
      )}
      {editing === r.id && (
        <IdeaEdit r={r} brand={brand} onCancel={() => setEditing(null)}
          onSave={async (patch) => { await update(r.id, patch, t("Idea dikemas kini.", "Idea updated.")); setEditing(null); }} />
      )}
      {(r.status === "new" || r.status === "error") && (
        <Button size="sm" variant="ghost" onClick={() => update(r.id, { status: "rejected" }, t("Ditolak.", "Rejected."))}>
          {t("Tolak", "Reject")}</Button>
      )}
      {r.status !== "working" && !published.has(r.id) && (
        <Button size="sm" variant="danger" onClick={() => remove(r.id)} title={t("Padam idea", "Delete idea")}><Trash2 size={12} /></Button>
      )}
    </>
  );
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
      <div className="mt-6 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-2 text-xs">
          {[["open", t("Aktif", "Active")], ["waiting", t("Menunggu", "Waiting")], ["error", t("Gagal", "Failed")],
            ["drafted", t("Draf siap", "Drafted")], ["rejected", t("Ditolak", "Rejected")]].map(([v, l]) => (
            <button key={v} onClick={() => setFilter(v)} aria-pressed={filter === v}
              className={`rounded-pill px-3 py-1.5 ${filter === v ? "bg-ink text-bg" : "bg-surface-2 text-muted"}`}>{l}{count(v) ? ` · ${count(v)}` : ""}</button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="relative">
            <Search size={12} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Cari idea", "Search ideas")} aria-label={t("Cari idea", "Search ideas")}
              className="w-40 rounded-pill border border-line bg-surface py-1.5 pl-8 pr-3 text-xs outline-none focus:border-accent" />
          </label>
          <select value={streamF} onChange={(e) => setStreamF(e.target.value)} aria-label={t("Aliran", "Stream")}
            className="rounded-pill border border-line bg-surface px-3 py-1.5 text-xs">
            <option value="all">{t("Semua", "All")}</option><option value="regulab">ws.regulab</option><option value="linkedin">LinkedIn</option>
          </select>
          <ViewToggle view={view} setView={setView} />
        </div>
      </div>
      {ideas.error && <p className="mt-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{ideas.error}</p>}
      {!shown.length && !ideas.loading && (
        <p className="mt-4 rounded-card border border-dashed border-line p-10 text-center text-sm text-muted">{t("Tiada idea di sini.", "No ideas here.")}</p>
      )}
      {view === "table" && shown.length > 0 ? (
        <div className="mt-4">
          <TableFrame label={t("Idea", "Ideas")}>
            <thead className={THEAD}>
              <tr>
                <th className={TH}>Status</th>
                <th className={`${TH} w-[40%]`}>{t("Isu / tajuk", "Issue / title")}</th>
                <th className={TH}>{t("Untuk", "For")}</th>
                <th className={TH}>{t("Masa", "When")}</th>
                <th className={TH}>{t("Tindakan", "Actions")}</th>
              </tr>
            </thead>
            <tbody className={TBODY}>
              {shown.map((r) => (
                <tr key={r.id} className={`${TR} hover:bg-surface-2/50`}>
                  <td className={TD} data-label="Status"><StatusChip r={r} /></td>
                  <td className={`${TD} [overflow-wrap:anywhere]`} data-label={t("Isu / tajuk", "Issue / title")}>
                    <p className="font-medium leading-snug">{r.source_title}</p>
                    {r.note && <p className="mt-1 line-clamp-2 text-[12px] text-muted">“{r.note}”</p>}
                    {r.error && <p className="mt-1 text-[12px] text-danger">{r.error}</p>}
                    <SourcePills r={r} />
                    <LateNote r={r} />
                  </td>
                  <td className={`${TD} text-[12px] text-muted`} data-label={t("Untuk", "For")}>{forText(r)}</td>
                  <td className={`${TD} whitespace-nowrap text-[12px] text-muted`} data-label={t("Masa", "When")}>{timeAgo(r.created_at)}</td>
                  <td className={TD} data-label={t("Tindakan", "Actions")}><div className="flex flex-wrap gap-1.5">{actions(r)}</div></td>
                </tr>
              ))}
            </tbody>
          </TableFrame>
        </div>
      ) : (
        <div className="mt-4 grid items-start gap-3 md:grid-cols-2">
          {shown.map((r) => {
            const src = r.brief?.source;
            return (
              <Card key={r.id} className="min-w-0 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <StatusChip r={r} />
                  <span className="text-[11px] text-muted">{forText(r)} · {timeAgo(r.created_at)}</span>
                </div>
                <h3 className="mt-2 [overflow-wrap:anywhere] font-display text-[17px] leading-snug">{r.source_title}</h3>
                {r.note && <p className="mt-1 [overflow-wrap:anywhere] text-sm text-muted">“{r.note}”</p>}
                {src && (
                  <p className="mt-2 text-[11px] text-muted">
                    {src.ok ? t("Bot membaca sumber penuh.", "The bot read the full source.")
                      : t("Ditulis daripada tajuk sahaja: {why}.", "Written from the headline only: {why}.",
                        { why: src.why || t("artikel tidak dapat dibaca", "the article could not be read") })}
                  </p>
                )}
                <SourcePills r={r} />
                {r.error && <p className="mt-2 [overflow-wrap:anywhere] rounded-tile bg-danger/5 p-2 text-[12px] text-danger">{r.error}</p>}
                <LateNote r={r} />
                <div className="mt-3 flex flex-wrap gap-2">{actions(r)}</div>
              </Card>
            );
          })}
        </div>
      )}
      <IdeaComposer open={composer} onClose={() => setComposer(false)} trend={null} user={user} brand={brand}
        onToast={onToast} onDone={ideas.reload} />
    </main>
  );
}

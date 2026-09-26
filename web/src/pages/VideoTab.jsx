import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Clapperboard, ExternalLink, FileText, Loader2, Plus, RotateCcw, Scissors, ShieldCheck,
  Trash2 } from "lucide-react";
import { fadeUp } from "../design/motion";
import { STREAMS } from "../lib/brand";
import { platformsFor, scan } from "../lib/compliance";
import { stampMYT, timeAgo } from "../lib/format";
import { useLang } from "../lib/i18n";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { Input, Label, Segmented, Select, TextArea } from "../components/ui/Field";

/* The Video tab (Wan, 26 Sep 2026: "add segment that can cut, edit video for short video such as youtube video (ceramah
   agama) to able act idea and post, allow me to paste youtube page to you scrape, once approve can cut edit and create
   into short video"). The page adds a link; the worker reads it and proposes clips (backend/semasa/video.py); Wan
   confirms he may use the video, edits a clip and approves it; the worker cuts a 9:16 short with captions and writes a
   DRAFT post with it, which then goes through the Posts tab like any other. */

export const VIDEO_TABLE = "semasa_videos";
const VIDEO_COLUMNS = "id,source_url,source_kind,stream,domain,angle,note,status,title,channel,channel_url,duration_s,"
  + "thumbnail_url,upload_date,license,transcript_source,clips,rights,rights_note,rights_at,error,attempts,created_at,updated_at";
const YT = /(?:youtube\.com\/(?:watch\?(?:.*&)?v=|shorts\/|live\/|embed\/)|youtu\.be\/)([\w-]{11})/;
const ytId = (u) => (String(u || "").match(YT) || [])[1] || null;
const MIN_CLIP = 3, MAX_CLIP = 90;

export function fmtTs(sec) {
  const s = Math.max(0, Math.round(Number(sec) || 0));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}` : `${m}:${String(r).padStart(2, "0")}`;
}
export function parseTs(v) {
  const s = String(v ?? "").trim();
  if (!/^\d{1,2}(:\d{1,2}){0,2}(\.\d+)?$/.test(s)) return null;
  return s.split(":").reduce((a, p) => a * 60 + Number(p), 0);
}

function useVideos(enabled) {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  async function load() {
    if (!supabase || !enabled) return;
    const { data, error: e } = await supabase.from(VIDEO_TABLE).select(VIDEO_COLUMNS).order("created_at", { ascending: false }).limit(60);
    if (e) setError(/semasa_videos/.test(errText(e)) ? "setup" : errText(e)); else { setRows(data || []); setError(""); }
    setLoading(false);
  }
  useEffect(() => {
    if (!supabase || !enabled) return undefined;
    load();
    const ch = supabase.channel("semasa_videos_live")
      .on("postgres_changes", { event: "*", schema: "public", table: VIDEO_TABLE }, () => load()).subscribe();
    const id = setInterval(() => { if (!document.hidden) load(); }, 60_000);
    return () => { supabase.removeChannel(ch); clearInterval(id); };
  }, [enabled]); // eslint-disable-line react-hooks/exhaustive-deps
  return { rows, error, loading, reload: load };
}

export default function VideoTab({ user, gens, brand, onToast, openPost }) {
  const { t } = useLang();
  const videos = useVideos(true);
  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div variants={fadeUp} initial="hidden" animate="show">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">Video</p>
        <h1 className="mt-2 text-4xl leading-tight">{t("Video panjang jadi klip pendek.", "A long video becomes short clips.")}</h1>
        <p className="mt-3 max-w-2xl text-sm text-muted">
          {t("Tampal pautan YouTube (cth: ceramah agama). Bot baca transkrip dan cadang 3 hingga 6 klip pendek. Anda sahkan hak guna video, "
            + "ubah klip, kemudian luluskan: bot potong klip 9:16 dengan kapsyen dan tulis draf post. Tiada apa diterbitkan tanpa kelulusan anda di tab Post.",
          "Paste a YouTube link (e.g. a religious talk). The bot reads the transcript and proposes 3 to 6 short clips. You confirm you may use "
            + "the video, edit a clip, then approve: the bot cuts a 9:16 clip with captions and writes a draft post. Nothing is published without your approval in the Posts tab.")}
        </p>
      </motion.div>
      {videos.error === "setup" ? (
        <p className="mt-8 rounded-tile bg-warn/10 p-4 text-sm text-warn">{t("Video belum disediakan dalam pangkalan data: jalankan supabase/011_video.sql sekali di Supabase SQL editor.",
          "Video is not set up in the database yet: run supabase/011_video.sql once in the Supabase SQL editor.")}</p>
      ) : (
        <>
          <AddVideo user={user} brand={brand} onToast={onToast} onAdded={videos.reload} />
          {videos.error && <p className="mt-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{videos.error}</p>}
          <div className="mt-8 space-y-6">
            {videos.loading && <p className="text-sm text-muted">{t("Memuatkan…", "Loading…")}</p>}
            {!videos.loading && !videos.rows.length && (
              <p className="rounded-card border border-dashed border-line p-10 text-center text-sm text-muted">{t("Belum ada video. Tampal pautan di atas.", "No videos yet. Paste a link above.")}</p>
            )}
            {videos.rows.map((v) => <VideoCard key={v.id} v={v} user={user} gens={gens} brand={brand} onToast={onToast} reload={videos.reload} openPost={openPost} />)}
          </div>
        </>
      )}
    </main>
  );
}

function AddVideo({ user, brand, onToast, onAdded }) {
  const { t } = useLang();
  const [url, setUrl] = useState("");
  const [stream, setStream] = useState("regulab");
  const [domain, setDomain] = useState("fatwa");
  const [angle, setAngle] = useState("");
  const [note, setNote] = useState("");
  const [paste, setPaste] = useState("");
  const [busy, setBusy] = useState(false);
  const kind = ytId(url) ? "youtube" : "link";
  const valid = /^https?:\/\/\S+$/.test(url.trim());

  async function add(e) {
    e.preventDefault();
    if (!valid) return onToast(t("Tampal pautan penuh (https://…).", "Paste a full link (https://…)."), "warn");
    setBusy(true);
    const { error } = await supabase.from(VIDEO_TABLE).insert({
      source_url: url.trim(), source_kind: kind, stream, domain: stream === "regulab" ? domain || null : null,
      angle: stream === "linkedin" ? angle || null : null, note: note.trim(), transcript_paste: paste.trim() || null,
      status: "new", created_by: user.id,
    });
    setBusy(false);
    if (error) return onToast(errText(error), "danger");
    onToast(t("Dihantar. Bot baca video dan cadang klip dalam beberapa minit.", "Sent. The bot reads the video and proposes clips within a few minutes."), "ok");
    setUrl(""); setNote(""); setPaste(""); onAdded();
  }

  return (
    <Card as="form" onSubmit={add} className="mt-8 space-y-4 p-5 sm:p-6">
      <label className="block"><Label hint={kind === "youtube" ? "YouTube" : t("fail video (pautan terus atau Google Drive)", "a video file (direct link or Google Drive)")}>
        {t("Pautan video", "Video link")}</Label>
        <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.youtube.com/watch?v=…" inputMode="url" /></label>
      <div className="grid gap-4 md:grid-cols-2">
        <div><Label>{t("Untuk", "For")}</Label><Segmented value={stream} onChange={setStream} options={STREAMS} /></div>
        {stream === "regulab"
          ? <label className="block"><Label>Domain</Label><Select value={domain} onChange={setDomain} className="w-full"
              options={[["", t("Bot pilih", "Bot chooses")], ...Object.entries(brand.regulab.domains || {})]} /></label>
          : <label className="block"><Label>{t("Sudut", "Angle")}</Label><Select value={angle} onChange={setAngle} className="w-full"
              options={[["", t("Bot pilih", "Bot chooses")], ...Object.entries(brand.linkedin.angles || {}).map(([k, v]) => [k, `${k} · ${v}`])]} /></label>}
      </div>
      <label className="block"><Label hint={t("pilihan", "optional")}>{t("Apa yang anda mahu daripada video ini", "What you want from this video")}</Label>
        <TextArea rows={2} value={note} onChange={(e) => setNote(e.target.value)} maxLength={1500}
          placeholder={t("Cth: bahagian tentang makanan syubhah dan sijil halal", "E.g. the part about doubtful food and halal certificates")} /></label>
      <details className="rounded-tile bg-surface-2/50 p-3 text-sm">
        <summary className="cursor-pointer font-medium">{t("Tampal transkrip sendiri (jika YouTube menolak bot)", "Paste the transcript yourself (if YouTube refuses the bot)")}</summary>
        <p className="mt-2 text-[12px] text-muted">{t("Di YouTube: buka huraian → Tunjukkan transkrip → pilih semua → salin, dan tampal di sini dengan masanya sekali.",
          "On YouTube: open the description → Show transcript → select all → copy, and paste it here with its times.")}</p>
        <TextArea rows={5} value={paste} onChange={(e) => setPaste(e.target.value)} className="mt-2" placeholder={"0:00\nAssalamualaikum…\n0:05\n…"} />
      </details>
      <div className="flex justify-end">
        <Button type="submit" disabled={busy || !valid}>{busy ? <Loader2 size={14} className="animate-spin" /> : <Clapperboard size={14} />} {t("Baca video", "Read the video")}</Button>
      </div>
    </Card>
  );
}

const statusChip = (t, s) => ({
  new: [t("Menunggu bot", "Waiting for the bot"), "text-warn bg-warn/10", true],
  working: [t("Membaca", "Reading"), "text-accent bg-accent/10", true],
  ready: [t("Klip dicadang", "Clips proposed"), "text-ok bg-ok/10", false],
  error: [t("Gagal", "Failed"), "text-danger bg-danger/10", false],
}[s] || [s, "bg-surface-2", false]);

function VideoCard({ v, user, gens, brand, onToast, reload, openPost }) {
  const { t } = useLang();
  const [label, cls, spin] = statusChip(t, v.status);
  const clips = Array.isArray(v.clips) ? v.clips : [];
  const jobs = gens.rows.filter((m) => m.mode === "clip" && m.meta?.video_id === v.id);
  const id = ytId(v.source_url);

  async function patch(fields, ok) {
    const { data, error } = await supabase.from(VIDEO_TABLE).update(fields).eq("id", v.id).select("id");
    if (error) { onToast(errText(error), "danger"); return false; }
    if (!data?.length) { onToast(t("Tiada perubahan disimpan (0 baris).", "Nothing was saved (0 rows)."), "danger"); return false; }
    if (ok) onToast(ok, "ok");
    reload();
    return true;
  }
  async function remove() {
    if (!window.confirm(t("Padam video ini dan cadangan kliknya? Klip yang sudah dipotong dan draf post kekal.", "Delete this video and its proposed clips? Clips already cut and their draft posts stay."))) return;
    const { error } = await supabase.from(VIDEO_TABLE).delete().eq("id", v.id);
    if (error) onToast(errText(error), "danger"); else { onToast(t("Dipadam.", "Deleted."), "info"); reload(); }
  }
  function addClip() {
    const n = { id: `m${Date.now().toString(36)}`, start: 0, end: 30, title: "", hook: "", caption: "", why: t("klip anda sendiri", "your own clip"), sensitive: false,
      speaker: clips[0]?.speaker || v.channel || "" };
    patch({ clips: [...clips, n] }, t("Klip kosong ditambah: tetapkan masa dan kapsyennya.", "An empty clip was added: set its times and caption."));
  }

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-col gap-4 p-4 sm:flex-row sm:p-5">
        {v.thumbnail_url
          ? <img src={v.thumbnail_url} alt="" className="aspect-video w-full rounded-tile object-cover sm:w-64 sm:shrink-0" />
          : <div className="grid aspect-video w-full place-items-center rounded-tile bg-surface-2 text-muted sm:w-64 sm:shrink-0"><Clapperboard size={28} /></div>}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 text-[11px] font-semibold ${cls}`}>
              {spin && <Loader2 size={12} className="animate-spin" />} {label}</span>
            <span className="text-[11px] text-muted" title={stampMYT(v.created_at)}>{timeAgo(v.created_at)}</span>
            {v.duration_s ? <span className="text-[11px] text-muted">· {fmtTs(v.duration_s)}</span> : null}
            {v.transcript_source && <span className="text-[11px] text-muted">· {t("transkrip", "transcript")}: {v.transcript_source}</span>}
          </div>
          <h3 className="mt-2 [overflow-wrap:anywhere] text-lg leading-snug">{v.title || v.source_url}</h3>
          {v.channel && <p className="text-sm text-muted">{v.channel}</p>}
          <a href={v.source_url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-flex items-center gap-1 text-[12px] text-accent hover:underline">
            <ExternalLink size={11} /> {t("Buka sumber", "Open the source")}</a>
          {v.note && <p className="mt-2 [overflow-wrap:anywhere] text-[12px] text-muted">{t("Nota", "Note")}: {v.note}</p>}
          {v.error && <p className="mt-2 [overflow-wrap:anywhere] rounded-tile bg-danger/5 p-2 text-[12px] text-danger">{v.error}</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            {(v.status === "error" || v.status === "ready") && (
              <Button size="sm" variant="soft" onClick={() => patch({ status: "new", error: null }, t("Dibaca semula.", "Reading again."))}>
                <RotateCcw size={12} /> {t("Baca semula", "Read again")}</Button>
            )}
            {v.status === "ready" && <Button size="sm" variant="ghost" onClick={addClip}><Plus size={12} /> {t("Klip sendiri", "Own clip")}</Button>}
            <Button size="sm" variant="danger" onClick={remove} title={t("Padam", "Delete")}><Trash2 size={12} /></Button>
          </div>
        </div>
      </div>

      {v.status === "ready" && <Rights v={v} patch={patch} />}

      {v.status === "ready" && clips.length > 0 && (
        <div className="grid gap-4 border-t border-line p-4 sm:p-5 xl:grid-cols-2">
          {clips.map((c, i) => (
            <ClipCard key={c.id || i} v={v} c={c} ytid={id} user={user} brand={brand} onToast={onToast} jobs={jobs.filter((j) => j.meta?.clip_id === c.id)}
              save={(next) => patch({ clips: clips.map((x, k) => (k === i ? next : x)) })} openPost={openPost} reloadGens={gens.reload} />
          ))}
        </div>
      )}
    </Card>
  );
}

/* Whether Wan may use this video at all. A clip is never cut before this is answered, and the worker checks it again. */
function Rights({ v, patch }) {
  const { t } = useLang();
  const [kind, setKind] = useState(v.rights || "");
  const [note, setNote] = useState(v.rights_note || "");
  const [sure, setSure] = useState(false);
  const cc = /creative commons/i.test(v.license || "");
  if (v.rights) {
    return (
      <p className="flex flex-wrap items-center gap-1.5 border-t border-line px-4 py-3 text-[12px] text-ok sm:px-5">
        <ShieldCheck size={14} /> {t("Hak guna disahkan", "Rights confirmed")}: <b>{{ own: t("video sendiri", "own video"), permission: t("izin pemilik", "the owner's permission"), cc: "Creative Commons" }[v.rights]}</b>
        {v.rights_note && <span className="[overflow-wrap:anywhere] text-muted">· {v.rights_note}</span>}
        <span className="text-muted">· {stampMYT(v.rights_at)}</span>
      </p>
    );
  }
  return (
    <div className="space-y-3 border-t border-line bg-warn/5 px-4 py-4 sm:px-5">
      <p className="flex items-start gap-1.5 text-sm font-medium text-warn"><AlertTriangle size={15} className="mt-0.5 shrink-0" />
        {t("Sebelum memotong: adakah anda boleh guna video ini?", "Before cutting: may you use this video?")}</p>
      <p className="text-[12px] text-muted">{t("Memotong dan menyiarkan semula ceramah orang lain tanpa izin boleh melanggar Akta Hak Cipta 1987 dan syarat YouTube. Pilih satu, dan simpan bukti izin anda.",
        "Cutting and republishing someone else's talk without permission can infringe the Copyright Act 1987 and YouTube's terms. Pick one, and keep your proof of permission.")}
        {cc && ` ${t("YouTube melabel video ini Creative Commons.", "YouTube labels this video Creative Commons.")}`}</p>
      <div className="flex flex-wrap items-end gap-3">
        <Select value={kind} onChange={setKind} aria-label={t("Hak guna", "Rights")} options={[["", t("Pilih…", "Choose…")],
          ["own", t("Video saya sendiri", "My own video")], ["permission", t("Pemilik memberi izin", "The owner gave permission")], ["cc", "Creative Commons"]]} />
        <div className="min-w-0 flex-1 basis-60"><Input value={note} onChange={(e) => setNote(e.target.value)} maxLength={300}
          placeholder={t("Bukti: cth \"izin WhatsApp Ustaz A, 26/9\"", "Proof: e.g. \"WhatsApp permission from Ustaz A, 26/9\"")} /></div>
      </div>
      <label className="flex items-start gap-2 text-[12px]">
        <input type="checkbox" className="mt-0.5" checked={sure} onChange={(e) => setSure(e.target.checked)} />
        <span>{t("Saya mengesahkan kenyataan ini benar dan saya bertanggungjawab atasnya.", "I confirm this statement is true and I am responsible for it.")}</span>
      </label>
      <Button size="sm" disabled={!kind || !sure || (kind === "permission" && !note.trim())}
        onClick={() => patch({ rights: kind, rights_note: note.trim() || null, rights_at: new Date().toISOString() }, t("Hak guna direkod.", "Rights recorded."))}>
        <ShieldCheck size={12} /> {t("Rekod hak guna", "Record the rights")}</Button>
    </div>
  );
}

function ClipCard({ v, c, ytid, user, brand, onToast, jobs, save, openPost, reloadGens }) {
  const { t } = useLang();
  const [start, setStart] = useState(fmtTs(c.start));
  const [end, setEnd] = useState(fmtTs(c.end));
  const [hook, setHook] = useState(c.hook || "");
  const [caption, setCaption] = useState(c.caption || "");
  const [frame, setFrame] = useState(c.frame || "fit");
  const [captions, setCaptions] = useState(c.captions !== false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setStart(fmtTs(c.start)); setEnd(fmtTs(c.end)); setHook(c.hook || ""); setCaption(c.caption || ""); }, [c.id]); // eslint-disable-line

  const s = parseTs(start), e = parseTs(end);
  const len = s != null && e != null ? e - s : null;
  const timeBad = len == null || len < MIN_CLIP || len > MAX_CLIP || (v.duration_s && e > v.duration_s + 1);
  const stream = v.stream || "regulab";
  const lang = stream === "linkedin" ? "en" : "bm";
  const speaker = c.speaker || v.channel || "";
  const flags = useMemo(() => scan({ stream, lang, text: { [lang]: Object.fromEntries(platformsFor(stream).map((p) => [p, caption])) },
    citation: `${speaker}, ${v.title || ""}`, media: [{ type: "video" }] }, brand?.regulab)
    .filter((f) => f.where.startsWith("Caption") || f.where === "Source"), [caption, stream, lang, speaker, v.title, brand]);
  const hard = flags.filter((f) => f.hard);
  const latest = jobs.slice().sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))[0];
  const edited = { ...c, start: s ?? c.start, end: e ?? c.end, hook, caption, frame, captions };

  async function cut() {
    if (!v.rights) return onToast(t("Rekod hak guna video dahulu.", "Record the video's rights first."), "warn");
    if (timeBad) return onToast(t("Klip mesti {a} hingga {b} saat, di dalam video.", "A clip is {a} to {b} seconds, inside the video.", { a: MIN_CLIP, b: MAX_CLIP }), "warn");
    if (hard.length) return onToast(t("Selesaikan perkara bertanda merah dalam kapsyen dahulu.", "Fix the red items in the caption first."), "warn");
    setBusy(true);
    await save(edited);
    const { error } = await supabase.from(TABLES.media).insert({
      mode: "clip", type: "video", status: "pending", created_by: user.id, prompt: hook || c.title || "",
      post_id: latest?.post_id && latest?.status === "done" ? latest.post_id : null,
      meta: { video_id: v.id, clip_id: c.id, start: s, end: e, hook, caption, speaker, title: c.title || "", frame, captions, stream },
    });
    setBusy(false);
    if (error) {
      return onToast(/mode_check/.test(errText(error)) ? t("Klip belum disediakan: jalankan supabase/011_video.sql.", "Clips are not set up: run supabase/011_video.sql.") : errText(error), "danger");
    }
    onToast(t("Diluluskan. Bot potong klip dan tulis draf post dalam beberapa minit.", "Approved. The bot cuts the clip and writes a draft post within a few minutes."), "ok");
    reloadGens();
  }

  const embed = ytid && s != null && e != null && e > s
    ? `https://www.youtube-nocookie.com/embed/${ytid}?start=${Math.floor(s)}&end=${Math.ceil(e)}&rel=0` : null;

  return (
    <div className="min-w-0 rounded-tile border border-line bg-surface p-3 sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="min-w-0 [overflow-wrap:anywhere] font-medium">{c.title || t("Klip", "Clip")}</p>
        <span className="text-[12px] text-muted">{fmtTs(c.start)}–{fmtTs(c.end)} · {Math.round((c.end || 0) - (c.start || 0))} s</span>
      </div>
      {c.why && <p className="mt-1 text-[12px] text-muted">{c.why}</p>}
      {c.sensitive && <p className="mt-2 flex items-start gap-1.5 rounded-tile bg-warn/10 p-2 text-[12px] text-warn"><AlertTriangle size={13} className="mt-0.5 shrink-0" />
        {t("Klip ini menyebut hukum: semak konteks dan syaratnya kekal sebelum diluluskan.", "This clip states a ruling: check its context and conditions stay before approving.")}</p>}
      {embed && <iframe title={c.title || "clip"} src={embed} className="mt-3 aspect-video w-full rounded-tile" allow="encrypted-media; picture-in-picture" allowFullScreen loading="lazy" />}

      <div className="mt-3 grid grid-cols-2 gap-3">
        <label><Label>{t("Mula", "Start")}</Label><Input value={start} onChange={(ev) => setStart(ev.target.value)} inputMode="numeric" /></label>
        <label><Label>{t("Tamat", "End")}</Label><Input value={end} onChange={(ev) => setEnd(ev.target.value)} inputMode="numeric" /></label>
      </div>
      {timeBad && <p className="mt-1 text-[12px] text-danger">{t("Masa m:ss, {a} hingga {b} saat.", "Times as m:ss, {a} to {b} seconds.", { a: MIN_CLIP, b: MAX_CLIP })}</p>}
      <label className="mt-3 block"><Label hint={t("baris pertama di atas video, maksimum 8 perkataan", "first line on the video, at most 8 words")}>{t("Cangkuk", "Hook")}</Label>
        <Input value={hook} onChange={(ev) => setHook(ev.target.value)} maxLength={90} /></label>
      <label className="mt-3 block"><Label hint={speaker ? t("dikreditkan kepada {s}", "credited to {s}", { s: speaker }) : ""}>{t("Kapsyen post", "Post caption")}</Label>
        <TextArea rows={5} value={caption} onChange={(ev) => setCaption(ev.target.value)} maxLength={2200} /></label>
      {flags.length > 0 && (
        <ul className="mt-2 space-y-1 text-[12px]">
          {flags.map((f, k) => <li key={k} className={`[overflow-wrap:anywhere] ${f.hard ? "text-danger" : "text-warn"}`}>{f.hard ? "■" : "□"} <b>{f.where}</b>: {f.msg}</li>)}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-3 text-[12px]">
        <Segmented value={frame} onChange={setFrame} options={[["fit", t("Penuh + latar kabur", "Whole + blurred sides")], ["fill", t("Potong penuh", "Crop to fill")]]} />
        <label className="flex items-center gap-1.5"><input type="checkbox" checked={captions} onChange={(ev) => setCaptions(ev.target.checked)} /> {t("Sari kata", "Captions")}</label>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button size="sm" disabled={busy || !v.rights || timeBad || hard.length > 0} onClick={cut}
          title={!v.rights ? t("Rekod hak guna dahulu", "Record the rights first") : ""}>
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Scissors size={12} />} {latest ? t("Potong semula", "Cut again") : t("Luluskan & potong", "Approve & cut")}</Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => save(edited).then((ok) => ok !== false && onToast(t("Disimpan.", "Saved."), "ok"))}>{t("Simpan", "Save")}</Button>
      </div>

      {latest && (
        <div className="mt-4 rounded-tile bg-surface-2/50 p-3">
          {(latest.status === "pending" || latest.status === "processing") && (
            <p className="flex items-center gap-1.5 text-[12px] text-muted"><Loader2 size={12} className="animate-spin" />
              {t("Bot sedang memotong klip ini (beberapa minit).", "The bot is cutting this clip (a few minutes).")}</p>
          )}
          {latest.status === "error" && <p className="[overflow-wrap:anywhere] text-[12px] text-danger">{latest.error}</p>}
          {latest.status === "done" && latest.generated_media_url && (
            <div className="flex flex-col gap-3 sm:flex-row">
              <video src={latest.generated_media_url} poster={latest.meta?.poster_url || undefined} controls playsInline
                className="aspect-[9/16] w-full max-w-[280px] rounded-tile bg-black object-contain sm:w-48" />
              <div className="min-w-0 text-[12px]">
                <p className="flex items-center gap-1.5 text-ok"><CheckCircle2 size={13} /> {t("Klip siap", "Clip ready")} · {latest.meta?.seconds} s · {Math.round((latest.meta?.bytes || 0) / 1e6)} MB</p>
                {latest.post_id && <Button size="sm" variant="soft" className="mt-2" onClick={() => openPost?.(latest.post_id)}>
                  <FileText size={12} /> {t("Buka draf post", "Open the draft post")}</Button>}
                <a href={latest.generated_media_url} target="_blank" rel="noopener noreferrer" className="mt-2 block text-accent hover:underline">{t("Muat turun klip", "Download the clip")}</a>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

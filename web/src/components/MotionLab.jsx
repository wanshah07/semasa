import { useState } from "react";
import { AlertTriangle, Clapperboard, Download, Loader2, Plus, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useTable } from "../lib/hooks";
import { timeAgo } from "../lib/format";
import { STREAMS } from "../lib/brand";
import { RESOLUTIONS, SECONDS, STATUS_WORDS, checkItems, fmtBytes, motionLabel, motionRepoRow, motionRow, styleRepos } from "../lib/motion";
import Card from "./ui/Card";
import Button from "./ui/Button";
import { Input, Label, Segmented, Select, TextArea } from "./ui/Field";

/* Motion (Wan, 23 Oct 2026: "in video segment, add motion segment that can create the motion video ... add this skill/prompt
   to create motion, create the video for this [link/idea]"). Wan gives an idea or a link; the row lands pending; the database
   wakes the worker, which has the AI write a HyperFrames composition, checks it, renders the MP4 on the runner and stores it.
   The card plays the video. Nothing is posted from here: the file is used like a Kanvas design. Wan's own skill/prompt text
   lives in Tetapan (settings.motion.prompt) and is added to every brief. */

const STATUS_CLS = { pending: "bg-warn/15 text-warn", working: "bg-accent/15 text-accent", done: "bg-ok/15 text-ok", error: "bg-danger/15 text-danger" };

export default function MotionLab({ user, onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const w = (v) => (Array.isArray(v) ? v[L] : v);
  const motions = useTable(TABLES.motions, { enabled: true, order: "created_at", limit: 60, realtime: true, everyMs: 60_000 });
  const [brief, setBrief] = useState("");
  const [url, setUrl] = useState("");
  const [stream, setStream] = useState("regulab");
  const [resolution, setResolution] = useState("portrait");
  const [seconds, setSeconds] = useState(SECONDS.default);
  const [styleRepoId, setStyleRepoId] = useState("");
  const [aiBackground, setAiBackground] = useState(false);
  const [repoUrl, setRepoUrl] = useState("");
  const [busy, setBusy] = useState("");
  // the motion repos in Pustaka repo: each one is a different look the writer can follow (Wan, 23 Oct 2026: "allow me to
  // add repo motion, so I can have choice to create different angle of motion video")
  const libT = useTable(TABLES.repoLibrary, { enabled: true, order: "updated_at", limit: 500, realtime: false, everyMs: 120_000 });
  const styles = styleRepos(libT.rows);
  const styleOf = (id) => libT.rows.find((r) => r.id === id);
  const missing = /semasa_motions/.test(motions.error || "");

  const add = async () => {
    const built = motionRow({ brief, url, stream, resolution, seconds, styleRepoId, aiBackground }, user?.id || null);
    if (built.error === "empty") return onToast?.(t("Tulis idea atau tampal pautan.", "Write an idea or paste a link."), "warn");
    if (built.error === "url") return onToast?.(t("Pautan perlu bermula dengan https://", "The link must start with https://"), "warn");
    setBusy("add");
    try {
      const { error } = await supabase.from(TABLES.motions).insert(built.row);
      if (error) throw new Error(errText(error));
      setBrief(""); setUrl("");
      onToast?.(t("Dihantar: bot tulis komposisi, semak dan render MP4. Biasanya 2 hingga 5 minit.", "Sent: the bot writes the composition, checks it and renders the MP4. Usually 2 to 5 minutes."), "ok");
      motions.reload();
    } catch (e) { onToast?.(e.message || String(e), "error"); } finally { setBusy(""); }
  };
  const addRepo = async () => {
    const row = motionRepoRow(repoUrl, user?.id || null);
    if (!row) return onToast?.(t("Tampal pautan github.com/owner/nama.", "Paste a github.com/owner/name link."), "warn");
    setBusy("repo");
    try {
      const { data, error } = await supabase.from(TABLES.repoLibrary).insert(row).select("id").single();
      if (error) throw new Error(/duplicate|unique/i.test(errText(error)) ? t("Repo ini sudah ada dalam pustaka: pilih ia di senarai gaya.", "This repo is already in the library: pick it in the style list.") : errText(error));
      setRepoUrl("");
      if (data?.id) setStyleRepoId(data.id);
      onToast?.(t("Repo motion ditambah ke Pustaka repo; bot membacanya sebentar lagi, dan ia sudah boleh dipilih sebagai gaya.", "Motion repo added to the repo library; the bot reads it shortly, and it can already be chosen as the style."), "ok");
      libT.reload();
    } catch (e) { onToast?.(e.message || String(e), "error"); } finally { setBusy(""); }
  };
  const patch = async (r, fields) => {
    setBusy(r.id);
    try {
      const { error } = await supabase.from(TABLES.motions).update(fields).eq("id", r.id);
      if (error) throw new Error(errText(error));
      motions.reload();
    } catch (e) { onToast?.(e.message || String(e), "error"); } finally { setBusy(""); }
  };
  const remove = async (r) => {
    setBusy(r.id);
    try {
      const { error } = await supabase.from(TABLES.motions).delete().eq("id", r.id);
      if (error) throw new Error(errText(error));
      motions.reload();
    } catch (e) { onToast?.(e.message || String(e), "error"); } finally { setBusy(""); }
  };

  return (
    <section className="mt-10" data-motion>
      <div className="mb-3">
        <h2 className="flex items-center gap-2 font-display text-2xl"><Clapperboard size={18} className="text-accent" /> {t("Motion", "Motion")}</h2>
        <p className="mt-1 max-w-2xl text-sm text-muted">{t("Video grafik gerak daripada idea atau pautan. Bot tulis komposisi HTML (kontrak HyperFrames), semak, render MP4 di pelayan dan paparkan di sini. Tiada apa disiarkan: fail ini untuk anda guna.",
          "A motion-graphics video from an idea or a link. The bot writes the HTML composition (the HyperFrames contract), checks it, renders the MP4 on the runner and shows it here. Nothing is posted: the file is yours to use.")}</p>
      </div>
      {missing && <p className="mb-4 rounded-tile bg-warn/10 p-3 text-sm text-warn">{t("Jadual belum ada: jalankan supabase/043_motion.sql sekali.", "The table is not there yet: run supabase/043_motion.sql once.")}</p>}
      {motions.error && !missing && <p className="mb-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{motions.error}</p>}

      <Card className="space-y-4 p-5">
        <label className="block"><Label hint={t("idea, hook, atau 3 perkara yang video perlu sampaikan", "the idea, the hook, or the 3 things the video must say")}>{t("Idea", "Idea")}</Label>
          <TextArea rows={3} value={brief} onChange={(e) => setBrief(e.target.value)} maxLength={2000}
            placeholder={t("Cth: Tiga perkara tentang PFAS dalam kosmetik yang SME perlu tahu sebelum 2027", "E.g. Three things about PFAS in cosmetics an SME must know before 2027")} /></label>
        <label className="block"><Label hint={t("pilihan: bot baca halaman itu", "optional: the bot reads that page")}>{t("Pautan", "Link")}</Label>
          <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" inputMode="url" /></label>
        <div className="grid gap-4 md:grid-cols-[1fr_auto]" data-motion-style>
          <label className="block"><Label hint={t("repo kategori motion dalam Pustaka repo; setiap satu gaya yang berbeza", "a motion-category repo from the repo library; each one a different look")}>{t("Gaya (repo motion)", "Style (motion repo)")}</Label>
            <Select value={styleRepoId} onChange={setStyleRepoId} className="w-full"
              options={[["", t("Gaya lalai Semasa", "Semasa's default look")], ...styles.map((r) => [r.id, `${r.name || r.full_name}${r.status !== "done" ? ` · ${t("belum dibaca", "not read yet")}` : ""}${r.safety === "avoid" ? ` · ${t("elakkan", "avoid")}` : ""}`])]} /></label>
          <div className="flex items-end gap-2">
            <label className="block min-w-0 flex-1"><Label>{t("Tambah repo motion", "Add a motion repo")}</Label>
              <Input value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} placeholder="https://github.com/owner/nama" inputMode="url" onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addRepo())} /></label>
            <Button variant="ghost" size="sm" className="mb-0.5" onClick={addRepo} disabled={busy === "repo" || !repoUrl.trim()}>{busy === "repo" ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} {t("Tambah", "Add")}</Button>
          </div>
        </div>
        {styleRepoId && styleOf(styleRepoId)?.summary_bm && <p className="text-xs text-muted">{L ? styleOf(styleRepoId).summary_en || styleOf(styleRepoId).summary_bm : styleOf(styleRepoId).summary_bm}</p>}
        <div className="grid gap-4 md:grid-cols-3">
          <div><Label>{t("Untuk", "For")}</Label><Segmented value={stream} onChange={setStream} options={STREAMS} /></div>
          <label className="block"><Label>{t("Saiz", "Size")}</Label><Select value={resolution} onChange={setResolution} className="w-full"
            options={Object.entries(RESOLUTIONS).map(([k, v]) => [k, w([v.bm, v.en])])} /></label>
          <label className="block"><Label hint={`${SECONDS.min}–${SECONDS.max}`}>{t("Saat", "Seconds")}</Label>
            <Input type="number" min={SECONDS.min} max={SECONDS.max} value={seconds} onChange={(e) => setSeconds(e.target.value)} /></label>
        </div>
        <label className="flex items-start gap-2 text-sm" data-motion-bg>
          <input type="checkbox" className="mt-1" checked={aiBackground} onChange={(e) => setAiBackground(e.target.checked)} />
          <span>{t("Latar gambar AI", "AI background picture")}
            <span className="block text-[12px] text-muted">{t("Satu gambar dilukis oleh slot Penjana gambar (KiosAPI jika itu yang anda tetapkan) dan diletak di bawah komposisi. Menggunakan kredit gambar; tiada gambar = video tetap dibuat.",
              "One picture drawn by the Image generation slot (KiosAPI if that is what you set) and placed under the composition. It spends picture credits; if it cannot be made the video is still made.")}</span></span>
        </label>
        <Button onClick={add} disabled={busy === "add"}>{busy === "add" ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />} {t("Buat video motion", "Make the motion video")}</Button>
      </Card>

      <div className="mt-6 grid gap-4 md:grid-cols-2 [&>*]:min-w-0">
        {!motions.loading && !motions.error && !motions.rows.length && (
          <p className="rounded-card border border-dashed border-line p-8 text-center text-sm text-muted md:col-span-2">{t("Belum ada video motion.", "No motion videos yet.")}</p>
        )}
        {motions.rows.map((r) => {
          const items = checkItems(r);
          return (
            <Card key={r.id} className="p-4" data-motion-row>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-display text-lg">{motionLabel(r) || t("(tiada tajuk)", "(untitled)")}</p>
                  <p className="truncate text-xs text-muted">{r.stream === "linkedin" ? "LinkedIn" : "ws.regulab"} · {w([RESOLUTIONS[r.resolution]?.bm, RESOLUTIONS[r.resolution]?.en]) || r.resolution} · {r.seconds}s{r.model ? ` · ${r.model}` : ""}{r.style_repo_id ? ` · ${t("gaya", "style")}: ${styleOf(r.style_repo_id)?.name || styleOf(r.style_repo_id)?.full_name || r.style_note.split(":")[0] || "repo"}` : ""}</p>
                </div>
                <span className={`inline-flex items-center gap-1 rounded-pill px-2 py-0.5 text-[11px] ${STATUS_CLS[r.status] || ""}`}>{r.status === "working" && <Loader2 size={10} className="animate-spin" />}{w(STATUS_WORDS[r.status] || [r.status, r.status])}</span>
              </div>
              {r.status === "done" && r.video_url && (
                <video className="mt-3 w-full rounded-tile bg-black" style={{ aspectRatio: `${r.width || 9} / ${r.height || 16}`, maxHeight: 480 }} controls playsInline preload="metadata" poster={r.poster_url || undefined} src={r.video_url} />
              )}
              {r.brief && r.title && <p className="mt-2 text-xs text-muted">{r.brief}</p>}
              {r.error && <p className="mt-2 rounded-tile bg-danger/10 p-2 text-xs text-danger">{r.error}</p>}
              {items.length > 0 && (
                <details className="mt-2 text-xs"><summary className="cursor-pointer text-muted"><AlertTriangle size={11} className="mr-1 inline" />{t("{n} nota semakan", "{n} check notes", { n: items.length })}</summary>
                  <ul className="mt-1 space-y-0.5">{items.map((it, i) => <li key={i} className={it.level === "error" ? "text-danger" : "text-muted"}><b>{it.code}</b> · {it.message}</li>)}</ul></details>
              )}
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {r.status === "done" && r.video_url && <a className="inline-flex items-center gap-1 rounded-pill bg-surface-2 px-3 py-1.5 text-xs hover:bg-line" href={r.video_url} download target="_blank" rel="noreferrer"><Download size={12} /> MP4{r.bytes ? ` · ${fmtBytes(r.bytes)}` : ""}</a>}
                <Button size="sm" variant="ghost" disabled={busy === r.id || r.status === "working"} onClick={() => patch(r, { status: "pending", attempts: 0, error: "" })}><RefreshCw size={12} /> {t("Buat semula", "Make again")}</Button>
                <Button size="sm" variant="ghost" disabled={busy === r.id} onClick={() => remove(r)}><Trash2 size={12} /> {t("Buang", "Remove")}</Button>
                <span className="ml-auto text-[11px] text-muted">{r.created_at ? timeAgo(r.created_at) : ""}</span>
              </div>
            </Card>
          );
        })}
      </div>
    </section>
  );
}

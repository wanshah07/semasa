import { useEffect, useState } from "react";
import { AlertTriangle, Clapperboard, Download, FolderGit2, Loader2, Plus, RefreshCw, Save, Sparkles, Trash2 } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useSettings, useTable } from "../lib/hooks";
import { timeAgo } from "../lib/format";
import { STREAMS } from "../lib/brand";
import { LANGUAGES, RESOLUTIONS, SECONDS, STATUS_WORDS, VOICES, checkItems, defaultLanguage, fmtBytes, formOf, freshUrl, motionDefaults, motionLabel, motionRepoRow, motionRow, selectedSeconds, startFields, styleRepos, withDefaults } from "../lib/motion";
import MotionAmbient from "./MotionAmbient";
import { designOptions, recipeOptions, recipeOf, styleOf as validStyle } from "../lib/motionStyles";
import MotionEffectLibrary from "./MotionEffectLibrary";
import MotionQueue from "./MotionQueue";
import { effectGroups } from "../lib/motionEffects";
import Card from "./ui/Card";
import Button from "./ui/Button";
import { Input, Label, Segmented, Select, TextArea } from "./ui/Field";

/* Motion (Wan, 23 Oct 2026: "in video segment, add motion segment that can create the motion video ... add this skill/prompt
   to create motion, create the video for this [link/idea]"). Wan gives an idea or a link; the row lands pending; the database
   wakes the worker, which has the AI write a HyperFrames composition, checks it, renders the MP4 on the runner and stores it.
   The card plays the video. Nothing is posted from here: the file is used like a Kanvas design. Wan's own skill/prompt text
   lives in Tetapan (settings.motion.prompt) and is added to every brief. */

const STATUS_CLS = { waiting: "bg-accent/15 text-accent", pending: "bg-warn/15 text-warn", working: "bg-accent/15 text-accent", done: "bg-ok/15 text-ok", error: "bg-danger/15 text-danger" };

export default function MotionLab({ user, onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const w = (v) => (Array.isArray(v) ? v[L] : v);
  const motions = useTable(TABLES.motions, { enabled: true, order: "created_at", limit: 60, realtime: true, everyMs: 60_000 });
  const [brief, setBrief] = useState("");
  const [url, setUrl] = useState("");
  const [stream, setStreamOnly] = useState("regulab");
  // the words on screen follow the stream until Wan picks otherwise (Wan, 24 Oct 2026: "english, malay, or english + malay")
  const [language, setLanguage] = useState(defaultLanguage("regulab"));
  const [langTouched, setLangTouched] = useState(false);
  const setStream = (v) => { setStreamOnly(v); if (!langTouched) setLanguage(defaultLanguage(v)); };
  const pickLanguage = (v) => { setLanguage(v); setLangTouched(true); };
  const [resolution, setResolution] = useState("portrait");
  const [seconds, setSeconds] = useState(SECONDS.default);
  const [mode, setMode] = useState("explainer");
  const [styleRepoId, setStyleRepoId] = useState("");
  const [style, setStyle] = useState("bright-education");
  const [design, setDesign] = useState("bright-editorial");
  const [ambient, setAmbient] = useState("mint");
  const [effects, setEffects] = useState(['B04']);
  const [effectMode, setEffectMode] = useState('auto');
  const [assets, setAssets] = useState([]);
  const [assetsBusy, setAssetsBusy] = useState(false);
  const assetMode = assets.length ? 'mixed' : 'auto';
  const [aiBackground, setAiBackground] = useState(false);
  const [voice, setVoice] = useState("kitten");
  const [repoUrl, setRepoUrl] = useState("");
  const [busy, setBusy] = useState("");
  // Wan's saved way (Wan, 24 Oct 2026: "save the skill to create and apply to all idea if I need"): the form opens on it, and
  // every idea or draft made into a video takes it
  const { settings, save } = useSettings(true);
  const defaultsKey = JSON.stringify(settings.motion?.defaults || null);
  useEffect(() => {
    const d = motionDefaults(settings);
    if (!settings.motion?.defaults) return;
    setLanguage(d.language || defaultLanguage(stream)); setLangTouched(!!d.language); setVoice(d.voice); setStyle(validStyle(d.style)); setDesign(d.design); setAmbient(d.ambient || "mint");
    setEffects(d.effects); setEffectMode(d.effectMode || 'auto');
    setResolution(d.resolution); setMode(d.mode); setSeconds(d.seconds); setAiBackground(!!d.aiBackground); setStyleRepoId(d.styleRepoId || "");
  }, [defaultsKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const saveDefaults = async () => {
    setBusy("defaults");
    try {
      await save("motion", withDefaults(settings.motion, { language: langTouched ? language : "", voice, resolution, seconds, aiBackground, styleRepoId, style, mode, design, ambient, effects, effectMode }));
      onToast?.(t("Disimpan sebagai cara lalai: setiap idea atau draf yang dijadikan video motion ikut tetapan ini.", "Saved as the default way: every idea or draft made into a motion video follows these settings."), "ok");
    } catch (e) { onToast?.(/0 rows|motion/i.test(e.message) ? t("Jalankan supabase/043_motion.sql dahulu.", "Run supabase/043_motion.sql first.") : e.message, "error"); } finally { setBusy(""); }
  };
  // the motion repos in Pustaka repo: each one is a different look the writer can follow (Wan, 23 Oct 2026: "allow me to
  // add repo motion, so I can have choice to create different angle of motion video")
  const libT = useTable(TABLES.repoLibrary, { enabled: true, order: "updated_at", limit: 500, realtime: false, everyMs: 120_000 });
  const styles = styleRepos(libT.rows);
  const styleOf = (id) => libT.rows.find((r) => r.id === id);
  const missing = /semasa_motions/.test(motions.error || "");

  const add = async () => {
    if (assetsBusy) return;
    const built = motionRow({ brief, url, stream, resolution, seconds, styleRepoId, aiBackground, language, voice, style, mode, design, ambient, effects, effectMode, assetMode, assets }, user?.id || null);
    if (built.error === "empty") return onToast?.(t("Tulis idea atau tampal pautan.", "Write an idea or paste a link."), "warn");
    if (built.error === "url") return onToast?.(t("Pautan perlu bermula dengan https://", "The link must start with https://"), "warn");
    setBusy("add");
    try {
      const { error } = await supabase.from(TABLES.motions).insert(built.row);
      if (error) throw new Error(errText(error));
      setBrief(""); setUrl(""); setAssets([]);
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
  // the queue: a row made from an idea or a draft waits until Wan has chosen its styles, then goes to the worker
  const startOne = async (r, form) => {
    setBusy(r.id);
    try {
      const { error } = await supabase.from(TABLES.motions).update(startFields(r, form)).eq("id", r.id);
      if (error) throw new Error(errText(error));
      onToast?.(t("Dimulakan: bot tulis komposisi, semak dan render MP4. Biasanya 2 hingga 5 minit.", "Started: the bot writes the composition, checks it and renders the MP4. Usually 2 to 5 minutes."), "ok");
      motions.reload();
    } catch (e) { onToast?.(e.message || String(e), "error"); } finally { setBusy(""); }
  };
  const startAll = async () => {
    const waiting = motions.rows.filter((r) => r.status === "waiting");
    if (!waiting.length) return;
    setBusy("all");
    try {
      for (const r of waiting) {
        const { error } = await supabase.from(TABLES.motions).update(startFields(r, formOf(r, motionDefaults(settings)))).eq("id", r.id);
        if (error) throw new Error(errText(error));
      }
      onToast?.(t("{n} video dimulakan dengan cara lalai.", "{n} videos started with the default way.", { n: waiting.length }), "ok");
      motions.reload();
    } catch (e) { onToast?.(e.message || String(e), "error"); } finally { setBusy(""); }
  };
  const effectName = Object.fromEntries(effectGroups().flatMap((g) => g.effects).map((e) => [e.id, e.name]));
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
        <MotionAmbient value={ambient} onChange={setAmbient} />
        <label className="block" data-motion-design><Label>Design variant (preserved)</Label>
          <select aria-label="Design variant" value={design} onChange={e => setDesign(e.target.value)} className="w-full rounded-tile border border-line bg-surface p-2">
            {designOptions.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select></label>
        <label className="block" data-motion-recipe><Label>{t("Gaya lampiran", "Attachment style")}</Label>
          <select aria-label="Attachment style" value={style} onChange={e => setStyle(e.target.value)} className="w-full rounded-tile border border-line bg-surface p-2">
            {recipeOptions().map(r => <option key={r.id} value={r.id} disabled={!r.available}>{r.name}{!r.available ? ` · ${r.reason}` : ""}</option>)}
          </select></label>
        <MotionEffectLibrary brief={brief} mode={mode} effects={effects} effectMode={effectMode}
          onEffects={setEffects} onEffectMode={setEffectMode} assets={assets} onAssets={setAssets}
          client={supabase} user={user} onBusy={setAssetsBusy} />
        <p className="text-xs text-muted" data-motion-audio-rights>Preferred preview music: supplied reel (rights unverified, private preview only, v17 quiet mix). Public export: cleared/self-owned piano; alternatively add licensed platform audio yourself. Reel audio is not bundled or downloaded automatically; unavailable preview source does not block the cleared export.</p>
        <p className="text-xs text-muted">{recipeOf(style).name} · Hook → Fact → Why → Solution. 30s by default; optional 60s for fuller publication context. 10s is only an explicitly selected gimmick/teaser, never an explainer. Long explainers include a separate 3s outro; 10s gimmicks stay in one continuous composition. Missing real footage/captures/data disables unsuitable recipes; charts and counters are omitted without verified data.</p>
        <label className="block" data-motion-style><Label hint={t("repo motion dari kotak di bawah; setiap satu gaya yang berbeza", "a motion repo from the box below; each one a different look")}>{t("Gaya (repo motion)", "Style (motion repo)")}</Label>
          <Select value={styleRepoId} onChange={setStyleRepoId} className="w-full"
            options={[["", t("Gaya lalai Semasa", "Semasa's default look")], ...styles.map((r) => [r.id, `${r.name || r.full_name}${r.status !== "done" ? ` · ${t("belum dibaca", "not read yet")}` : ""}${r.safety === "avoid" ? ` · ${t("elakkan", "avoid")}` : ""}`])]} /></label>
        {styleRepoId && styleOf(styleRepoId)?.summary_bm && <p className="text-xs text-muted">{L ? styleOf(styleRepoId).summary_en || styleOf(styleRepoId).summary_bm : styleOf(styleRepoId).summary_bm}</p>}
        <div className="grid gap-4 md:grid-cols-2">
          <div><Label>{t("Untuk", "For")}</Label><Segmented value={stream} onChange={setStream} options={STREAMS} /></div>
          <div data-motion-language><Label hint={t("perkataan di skrin; BM + English letak kedua-dua baris", "the words on screen; BM + English puts both lines up")}>{t("Bahasa", "Language")}</Label>
            <Segmented value={language} onChange={pickLanguage} options={LANGUAGES} /></div>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block"><Label>{t("Saiz", "Size")}</Label><Select value={resolution} onChange={setResolution} className="w-full"
            options={Object.entries(RESOLUTIONS).map(([k, v]) => [k, w([v.bm, v.en])])} /></label>
          <label className="block"><Label>{t("Mod", "Mode")}</Label>
            <Select value={mode} onChange={v => { setMode(v); setSeconds(v === "teaser" ? 10 : selectedSeconds(seconds, v)); }}
              options={[["explainer", "Explainer · Hook / Fact / Why / Solution"], ["teaser", "Gimmick / teaser only · not an explainer"]]} /></label>
          <label className="block"><Label>{t("Saat", "Seconds")}</Label>
            <Select value={String(seconds)} onChange={setSeconds} options={mode === "teaser" ? [["10", "10s · one persistent gimmick scene"], ["30", "30s"], ["60", "60s"]] : [["30", "30s · default"], ["60", "60s"]]} /></label>
        </div>
        <div className="grid gap-4 md:grid-cols-2" data-motion-voice>
          <div><Label hint={t("suara Edge neural: Osman / Yasmin (BM), Andrew / Ava (EN)", "VoiceStudio KittenTTS: English preset, configured worker required; BM/both automatically uses native Edge female +15%")}>{t("Suara", "Voice")}</Label>
            <Segmented value={voice} onChange={setVoice} options={VOICES.map(([k, bm, en]) => [k, L ? en : bm])} /></div>
          <p className="text-[12px] text-muted md:pt-6">{t("Setiap video: Hook, Fakta, Kenapa, Solusi, gambar Unsplash, gaya dipilih ikut kesesuaian. Dengan suara: lebih laju. Tanpa suara: perlahan supaya boleh dibaca.", "Every video: Hook, Fact, Why, Solution, Unsplash photos, styles chosen for fit. With a voice: brisk. Without: slow enough to read.")}</p>
        </div>
        <label className="flex items-start gap-2 text-sm" data-motion-bg>
          <input type="checkbox" className="mt-1" checked={aiBackground} onChange={(e) => setAiBackground(e.target.checked)} />
          <span>{t("Latar gambar AI", "AI background picture")}
            <span className="block text-[12px] text-muted">{t("Satu gambar dilukis oleh slot Penjana gambar (KiosAPI jika itu yang anda tetapkan) dan diletak di bawah komposisi. Menggunakan kredit gambar; tiada gambar = video tetap dibuat.",
              "One picture drawn by the Image generation slot (KiosAPI if that is what you set) and placed under the composition. It spends picture credits; if it cannot be made the video is still made.")}</span></span>
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={add} disabled={busy === "add" || assetsBusy}>{busy === "add" ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />} {t("Buat video motion", "Make the motion video")}</Button>
          <Button variant="ghost" size="sm" onClick={saveDefaults} disabled={busy === "defaults"} title={t("Bahasa, suara, saiz, saat, gaya dan latar: dipakai bila idea atau draf dijadikan video", "Language, voice, size, seconds, style and background: used when an idea or draft is made into a video")}
            data-motion-save-defaults>{busy === "defaults" ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} {t("Simpan sebagai cara lalai", "Save as the default way")}</Button>
          {settings.motion?.defaults && <span className="text-[11px] text-muted">{t("Cara lalai tersimpan: idea dan draf ikutnya.", "Default way saved: ideas and drafts follow it.")}</span>}
        </div>
      </Card>

      <Card className="mt-4 space-y-3 p-5" data-motion-repos>
        <div>
          <h3 className="flex items-center gap-2 font-display text-lg"><FolderGit2 size={16} className="text-accent" /> {t("Repo motion", "Motion repos")}</h3>
          <p className="mt-1 text-sm text-muted">{t("Setiap repo satu gaya: bot baca ia (Pustaka repo), semak keselamatan dan ringkaskan; kemudian ia boleh dipilih sebagai Gaya di atas. Seberapa banyak yang anda mahu.",
            "Each repo is one look: the bot reads it (Pustaka repo), checks it for safety and summarises it; then it can be chosen as the Style above. Add as many as you like.")}</p>
        </div>
        <div className="flex items-end gap-2">
          <label className="block min-w-0 flex-1"><Label>{t("Tambah repo motion", "Add a motion repo")}</Label>
            <Input value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} placeholder="https://github.com/owner/nama" inputMode="url" onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addRepo())} /></label>
          <Button variant="ghost" size="sm" className="mb-0.5" onClick={addRepo} disabled={busy === "repo" || !repoUrl.trim()}>{busy === "repo" ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} {t("Tambah", "Add")}</Button>
        </div>
        {!styles.length && <p className="text-xs text-muted">{t("Belum ada repo motion. Cth: https://github.com/heygen-com/hyperframes", "No motion repos yet. E.g. https://github.com/heygen-com/hyperframes")}</p>}
        {styles.length > 0 && (
          <ul className="divide-y divide-line">
            {styles.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-2 py-2 text-sm" data-motion-repo>
                <button type="button" className={`truncate text-left font-medium hover:underline ${styleRepoId === r.id ? "text-accent" : ""}`} onClick={() => setStyleRepoId(r.id)} title={t("Guna sebagai gaya", "Use as the style")}>{r.name || r.full_name}</button>
                <a className="truncate text-xs text-muted hover:underline" href={r.url} target="_blank" rel="noreferrer">{r.full_name}</a>
                <span className={`rounded-pill px-2 py-0.5 text-[11px] ${r.status === "done" ? (r.safety === "avoid" ? "bg-danger/15 text-danger" : r.safety === "caution" ? "bg-warn/15 text-warn" : "bg-ok/15 text-ok") : "bg-surface-2 text-muted"}`}>
                  {r.status !== "done" ? t("belum dibaca", "not read yet") : r.safety === "avoid" ? t("elakkan", "avoid") : r.safety === "caution" ? t("berhati-hati", "caution") : t("selamat", "safe")}</span>
                {styleRepoId === r.id && <span className="text-[11px] text-accent">{t("dipilih", "chosen")}</span>}
                {(L ? r.summary_en || r.summary_bm : r.summary_bm) && <p className="w-full text-xs text-muted">{L ? r.summary_en || r.summary_bm : r.summary_bm}</p>}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <MotionQueue rows={motions.rows.filter((r) => r.status === "waiting")} defaults={motionDefaults(settings)} client={supabase} user={user}
        busy={busy} onStart={startOne} onStartAll={startAll} onRemove={remove} />

      <div className="mt-6 grid gap-4 md:grid-cols-2 [&>*]:min-w-0">
        {!motions.loading && !motions.error && !motions.rows.some((r) => r.status !== "waiting") && (
          <p className="rounded-card border border-dashed border-line p-8 text-center text-sm text-muted md:col-span-2">{t("Belum ada video motion.", "No motion videos yet.")}</p>
        )}
        {motions.rows.filter((r) => r.status !== "waiting").map((r) => {
          const items = checkItems(r);
          return (
            <Card key={r.id} className="p-4" data-motion-row>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-display text-lg">{motionLabel(r) || t("(tiada tajuk)", "(untitled)")}</p>
                  <p className="truncate text-xs text-muted">{r.stream === "linkedin" ? "LinkedIn" : "ws.regulab"} · {(LANGUAGES.find(([k]) => k === (r.language || defaultLanguage(r.stream))) || [])[1]} · {w([RESOLUTIONS[r.resolution]?.bm, RESOLUTIONS[r.resolution]?.en]) || r.resolution} · {r.seconds}s{r.voice && r.voice !== "off" ? ` · ${t("suara", "voice")}` : ""}{r.model ? ` · ${r.model}` : ""}{r.style_repo_id ? ` · ${t("gaya", "style")}: ${styleOf(r.style_repo_id)?.name || styleOf(r.style_repo_id)?.full_name || (r.style_note || "").split(":")[0] || "repo"}` : ""}</p>
                </div>
                <span className={`inline-flex items-center gap-1 rounded-pill px-2 py-0.5 text-[11px] ${STATUS_CLS[r.status] || ""}`}>{r.status === "working" && <Loader2 size={10} className="animate-spin" />}{w(STATUS_WORDS[r.status] || [r.status, r.status])}</span>
              </div>
              {r.status === "done" && r.video_url && (
                <video key={`${r.id}-${r.updated_at}`} className="mt-3 w-full rounded-tile bg-black" style={{ aspectRatio: `${r.width || 9} / ${r.height || 16}`, maxHeight: 480 }} controls playsInline preload="metadata" poster={freshUrl(r.poster_url, r.updated_at) || undefined} src={freshUrl(r.video_url, r.updated_at)} />
              )}
              {r.brief && r.title && <p className="mt-2 text-xs text-muted">{r.brief}</p>}
              {r.error && <p className="mt-2 rounded-tile bg-danger/10 p-2 text-xs text-danger">{r.error}</p>}
              {r.check_report?.auto_effects && <details className="mt-2 text-xs" data-motion-applied>
                <summary className="cursor-pointer text-muted">{t("{n} gaya dipakai ikut kesesuaian", "{n} styles applied for fit", { n: r.check_report.auto_effects.applied })}</summary>
                <p className="mt-1">{[...new Set([...Object.values(r.check_report.auto_effects.scenes || {}).flat(), ...Object.values(r.check_report.auto_effects.video || {}), ...(r.check_report.auto_effects.audio || [])])]
                  .map((id) => `${id} ${effectName[id] || ""}`.trim()).join(" · ")}</p></details>}
              {r.check_report?.asset_plan && <details className="mt-2 text-xs">
                <summary className="cursor-pointer text-muted">Prepared assets & actual effect readiness</summary>
                <ul className="mt-1 space-y-1">{r.check_report.asset_plan.effects.map(e => <li key={e.id}><b>{e.id} · {e.readiness}</b> — {e.reason}</li>)}</ul>
                {r.check_report.asset_plan.notes.map((note,i)=><p key={i} className="mt-1 text-muted">{note}</p>)}
              </details>}
              {items.length > 0 && (
                <details className="mt-2 text-xs"><summary className="cursor-pointer text-muted"><AlertTriangle size={11} className="mr-1 inline" />{t("{n} nota semakan", "{n} check notes", { n: items.length })}</summary>
                  <ul className="mt-1 space-y-0.5">{items.map((it, i) => <li key={i} className={it.level === "error" ? "text-danger" : "text-muted"}><b>{it.code}</b> · {it.message}</li>)}</ul></details>
              )}
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {r.status === "done" && r.video_url && <a className="inline-flex items-center gap-1 rounded-pill bg-surface-2 px-3 py-1.5 text-xs hover:bg-line" href={freshUrl(r.video_url, r.updated_at)} download target="_blank" rel="noreferrer"><Download size={12} /> MP4{r.bytes ? ` · ${fmtBytes(r.bytes)}` : ""}</a>}
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

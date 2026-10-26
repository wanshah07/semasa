import { useState } from "react";
import { ListChecks, Loader2, Play, Trash2 } from "lucide-react";
import { useLang } from "../lib/i18n";
import { FORMAT_WORDS, LANGUAGES, VOICES, defaultLanguage, formOf, formatOf, motionLabel, selectedSeconds } from "../lib/motion";
import { VIDEO_FORMATS, selectFormat } from "../lib/videoFormatPolicy";
import { designOptions } from "../lib/motionStyles";
import MotionEffectLibrary from "./MotionEffectLibrary";
import Card from "./ui/Card";
import Button from "./ui/Button";
import { Label, Segmented, Select } from "./ui/Field";

/* The queue (Wan, 26 Oct 2026: "when I click Idea to be motion video, it will queue to motion video for me to choose styles for
   motion video"). An idea or a draft made into a video waits here as `waiting`; the worker ignores it until Wan presses Mula,
   which sends the styles he chose (or Auto: the bot picks at least 15 of the 99 for each film) and sets it `pending`. */

function QueueCard({ row, defaults, client, user, busy, onStart, onRemove }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const [form, setForm] = useState(() => formOf(row, defaults));
  const [assetsBusy, setAssetsBusy] = useState(false);
  const [open, setOpen] = useState(false);          // the 99 cards are drawn only when asked for: a long queue stays light
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const format = formatOf(form);
  return (
    <Card className="space-y-3 p-4" data-motion-queue-row>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 font-display text-lg">{motionLabel(row) || t("(tiada tajuk)", "(untitled)")}</p>
          <p className="truncate text-xs text-muted">{row.stream === "linkedin" ? "LinkedIn" : "ws.regulab"} · {row.seconds}s · {t("Format", "Format")}: {FORMAT_WORDS[format][L]}</p>
        </div>
        <span className="rounded-pill bg-accent/15 px-2 py-0.5 text-[11px] text-accent">{t("Pilih gaya", "Choose styles")}</span>
      </div>
      <label className="block" data-video-format><Label>Video format</Label>
        <Select value={form.format} onChange={(value) => set(selectFormat(form, value, row.stream))}
          options={VIDEO_FORMATS.map(f => [f.id, f.name])} /></label>
      <div className="grid gap-3 md:grid-cols-2">
        <div><Label>{t("Bahasa", "Language")}</Label>
          <Segmented value={form.language || defaultLanguage(row.stream)} onChange={(v) => set({ language: v, voice: v !== "en" && form.voice === "kitten" ? "male" : form.voice })} options={LANGUAGES} /></div>
        <div><Label>{t("Suara", "Voice")}</Label>
          <Segmented value={form.voice} onChange={(v) => set({ voice: v })} options={VOICES.map(([k, bm, en]) => [k, L ? en : bm])} /></div>
        <label className="block"><Label>{t("Reka bentuk", "Design")}</Label>
          <Select value={form.design} onChange={(v) => set({ design: v })} className="w-full" options={designOptions.map((d) => [d.id, d.name])} /></label>
        <label className="block"><Label>{t("Mod dan saat", "Mode and seconds")}</Label>
          <Select value={`${form.mode}:${selectedSeconds(form.seconds, form.mode)}`} className="w-full"
            onChange={(v) => { const [mode, s] = v.split(":"); set({ mode, seconds: Number(s) }); }}
            options={[["explainer:30", "Explainer · 30s"], ["explainer:60", "Explainer · 60s"], ["teaser:10", "Gimmick · 10s (one scene)"]]} /></label>
      </div>
      <details className="rounded-tile border border-line p-3" data-motion-queue-styles onToggle={(e) => setOpen(e.currentTarget.open)}>
        <summary className="cursor-pointer text-sm">
          {form.effectMode === "auto"
            ? t("Gaya: Auto · bot pilih sekurang-kurangnya 15 daripada 99 ikut setiap babak", "Styles: Auto · the bot picks at least 15 of the 99 for each scene")
            : t("Gaya: pilihan anda · {n}", "Styles: your choice · {n}", { n: form.effects.length })}
        </summary>
        {open && <div className="mt-3">
          <MotionEffectLibrary brief={row.brief || ""} mode={form.mode} effects={form.effects} effectMode={form.effectMode}
            onEffects={(effects) => set({ effects })} onEffectMode={(effectMode) => set({ effectMode })}
            assets={form.assets} onAssets={(assets) => set({ assets })} client={client} user={user} onBusy={setAssetsBusy} />
        </div>}
      </details>
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => onStart(row, form)} disabled={busy === row.id || assetsBusy}>
          {busy === row.id ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />} {t("Mula buat video", "Start the video")}</Button>
        <Button variant="ghost" size="sm" onClick={() => onRemove(row)} disabled={busy === row.id}><Trash2 size={12} /> {t("Buang daripada giliran", "Remove from the queue")}</Button>
      </div>
    </Card>
  );
}

export default function MotionQueue({ rows, defaults, client, user, busy, onStart, onStartAll, onRemove }) {
  const { t } = useLang();
  if (!rows.length) return null;
  return (
    <div className="mt-6" data-motion-queue>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="flex items-center gap-2 font-display text-lg"><ListChecks size={16} className="text-accent" /> {t("Giliran video: pilih gaya dahulu", "Video queue: choose the styles first")} · {rows.length}</h3>
          <p className="mt-1 max-w-2xl text-sm text-muted">{t("Idea atau draf yang dijadikan video menunggu di sini. Pilih bahasa, suara, reka bentuk dan gaya, kemudian tekan Mula. Tiada apa dibuat sehingga anda tekan.",
            "An idea or draft made into a video waits here. Choose the language, voice, design and styles, then press Start. Nothing is made until you do.")}</p>
        </div>
        <Button variant="ghost" size="sm" onClick={onStartAll} disabled={busy === "all"} data-motion-queue-all>
          {busy === "all" ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />} {t("Mula semua dengan cara lalai (Auto)", "Start all with the default way (Auto)")}</Button>
      </div>
      <div className="grid gap-4 md:grid-cols-2 [&>*]:min-w-0">
        {rows.map((r) => <QueueCard key={r.id} row={r} defaults={defaults} client={client} user={user} busy={busy} onStart={onStart} onRemove={onRemove} />)}
      </div>
    </div>
  );
}

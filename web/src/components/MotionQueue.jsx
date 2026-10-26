import { useState } from "react";
import { ListChecks, Loader2, Play, Trash2 } from "lucide-react";
import { useLang } from "../lib/i18n";
import { FORMAT_WORDS, LANGUAGES, VOICES, defaultLanguage, formOf, formatOf, motionLabel, selectedSeconds } from "../lib/motion";
import { designOptions } from "../lib/motionStyles";
import MotionAmbient from "./MotionAmbient";
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
  const isGimmick = format === "gimmick";
  /* Gimmick or full content (Wan, 26 Oct 2026: "make sure we can choose gimmick or full content for idea"): the first thing on every
     card, because it decides everything after it: one scene of 10 s, or the four-scene film, as long as its information needs and never more than 70 s. */
  const chooseKind = (v) => set(v === "gimmick" ? { mode: "teaser", seconds: 10 }
    : { mode: "explainer", seconds: selectedSeconds(form.seconds, "explainer") === 60 ? 60 : 30 });
  return (
    <Card className="space-y-3 p-4" data-motion-queue-row>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 font-display text-lg">{motionLabel(row) || t("(tiada tajuk)", "(untitled)")}</p>
          <p className="truncate text-xs text-muted">{row.stream === "linkedin" ? "LinkedIn" : "ws.regulab"} · {row.seconds}s · {t("Format", "Format")}: {FORMAT_WORDS[format][L]}</p>
        </div>
        <span className="rounded-pill bg-accent/15 px-2 py-0.5 text-[11px] text-accent">{t("Pilih gaya", "Choose styles")}</span>
      </div>
      <div data-motion-queue-kind>
        <Label>{t("Jenis video", "Kind of video")}</Label>
        <Segmented value={isGimmick ? "gimmick" : "full"} onChange={chooseKind}
          options={[["gimmick", t("Gimik · 10s, satu babak", "Gimmick · 10s, one scene")], ["full", t("Kandungan penuh · 4 babak", "Full content · 4 scenes")]]} />
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <div><Label>{t("Bahasa", "Language")}</Label>
          <Segmented value={form.language || defaultLanguage(row.stream)} onChange={(v) => set({ language: v, voice: v !== "en" && form.voice === "kitten" ? "female" : form.voice })} options={LANGUAGES} /></div>
        <div><Label>{t("Suara", "Voice")}</Label>
          <Segmented value={form.voice} onChange={(v) => set({ voice: v })} options={VOICES.map(([k, bm, en]) => [k, L ? en : bm])} /></div>
        <div className="md:col-span-2"><MotionAmbient value={form.ambient} onChange={(v) => set({ ambient: v })} /></div>
        <label className="block"><Label>{t("Reka bentuk", "Design")}</Label>
          <Select value={form.design} onChange={(v) => set({ design: v })} className="w-full" options={designOptions.map((d) => [d.id, d.name])} /></label>
        {isGimmick ? null : (
          <div><Label>{t("Panjang kandungan penuh", "Full content length")}</Label>
            <p className="rounded-tile bg-surface-2 px-3 py-2 text-xs text-muted" data-motion-length>
              {t("Ikut maklumat: video sepanjang yang diperlukan untuk maklumat sampai, tidak lebih 70 saat.",
                "As long as the information needs: the video runs as long as it takes to deliver it, never more than 70 seconds.")}</p></div>
        )}
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

import { ArrowDown, ArrowUp, ExternalLink, Layers, Loader2, Plus, Trash2 } from "lucide-react";
import { slidesKey } from "../lib/compliance";
import { useLang } from "../lib/i18n";
import Button from "./ui/Button";
import { Input, Label, Select, TextArea } from "./ui/Field";

export const MAX_SLIDES = 10;

/** Editor rows <-> stored slides. The editor keeps empty rows while typing; the scan and the save
    see normaliseSlides() of them, which drops empties exactly as the worker does. */
export const toRows = (slides) => (Array.isArray(slides) ? slides : []).map((s) => ({
  title: String(s?.title ?? ""), points: (Array.isArray(s?.points) ? s.points : []).join("\n"),
}));
export const fromRows = (rows) => rows.map((r) => ({ title: r.title, points: r.points }));

const kindOf = (t, i, n) => (i === 0 ? t("Kulit", "Cover") : i === n - 1 && n > 1 ? t("Penutup · sumber dilukis di sini", "Closing · source drawn here")
  : t("Slaid {n}", "Slide {n}", { n: i + 1 }));

/* The carousel of one post: its words, where they are drawn from, and the drawn pictures.
   Drawing is done by the worker (backend/semasa/slides.py) with no AI and no key. */
export default function SlidesEditor({ post, rows, setRows, locked, jobs, attachedIds, bg, setBg, bgOptions, busy,
  onRender, onUse }) {
  const { t } = useLang();
  const n = rows.length;
  const size = post.stream === "linkedin" ? "1080×1350" : "1080×1080";
  const latest = jobs[0];
  const latestDone = jobs.find((j) => j.status === "done");
  const drawnStale = latestDone && slidesKey(latestDone.meta?.slides) !== slidesKey(fromRows(rows));
  const set = (i, patch) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const move = (i, d) => {
    const j = i + d;
    if (j < 0 || j >= n) return;
    const next = rows.slice();
    [next[i], next[j]] = [next[j], next[i]];
    setRows(next);
  };

  return (
    <div className="rounded-tile border border-line p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 text-sm font-medium"><Layers size={14} /> {t("Slaid carousel", "Carousel slides")}</p>
        <span className="text-[11px] text-muted">{n} / {MAX_SLIDES} {t("slaid", "slides")} · {size} · {t("dilukis tanpa AI, percuma", "drawn without AI, free")}</span>
      </div>
      <p className="mt-1 text-[11px] text-muted">
        {t("Satu fakta satu slaid. Tanda satu perkataan dengan *bintang* untuk penekanan. Sumber dilukis pada slaid terakhir "
          + "daripada medan Sumber. Peraturan kapsyen berlaku pada setiap slaid.",
        "One fact per slide. Mark a word with *asterisks* for emphasis. The source is drawn on the last slide "
          + "from the Source field. Caption rules apply to every slide.")}
      </p>

      <ol className="mt-3 space-y-3">
        {rows.map((r, i) => (
          <li key={i} className="rounded-tile bg-surface-2/60 p-2.5">
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-accent">{kindOf(t, i, n)}</span>
              {!locked && (
                <span className="flex gap-1">
                  <button type="button" aria-label={t("Naik", "Move up")} disabled={i === 0} onClick={() => move(i, -1)} className="rounded p-1 text-muted hover:text-ink disabled:opacity-30"><ArrowUp size={13} /></button>
                  <button type="button" aria-label={t("Turun", "Move down")} disabled={i === n - 1} onClick={() => move(i, 1)} className="rounded p-1 text-muted hover:text-ink disabled:opacity-30"><ArrowDown size={13} /></button>
                  <button type="button" aria-label={t("Buang slaid", "Remove slide")} onClick={() => setRows(rows.filter((_, j) => j !== i))} className="rounded p-1 text-muted hover:text-danger"><Trash2 size={13} /></button>
                </span>
              )}
            </div>
            <Input value={r.title} disabled={locked} maxLength={240} onChange={(e) => set(i, { title: e.target.value })}
              placeholder={i === 0 ? t("Tajuk kulit (cth: Notifikasi *bukan* kelulusan)", "Cover title (e.g. Notification is *not* approval)")
                : t("Tajuk slaid", "Slide title")} />
            <TextArea rows={i === 0 ? 2 : 3} value={r.points} disabled={locked} className="mt-1.5"
              onChange={(e) => set(i, { points: e.target.value })}
              placeholder={i === 0 ? t("Baris kecil di bawah tajuk (pilihan)", "Small line under the title (optional)")
                : t("Satu poin satu baris (maksimum 5)", "One point per line (up to 5)")} />
          </li>
        ))}
      </ol>

      {!locked && (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <Button type="button" size="sm" variant="ghost" disabled={n >= MAX_SLIDES}
            onClick={() => setRows([...rows, { title: "", points: "" }])}><Plus size={12} /> {t("Tambah slaid", "Add slide")}</Button>
          <label className="ml-auto"><Label>{t("Latar", "Background")}</Label>
            <Select value={bg} onChange={setBg} options={bgOptions} aria-label={t("Latar slaid", "Slide background")} /></label>
          <Button type="button" size="sm" disabled={busy || !n} onClick={onRender}
            title={t("Simpan post ini, kemudian bot melukis slaid", "Save this post, then the bot draws the slides")}>
            <Layers size={12} /> {t("Jana slaid", "Generate slides")}</Button>
        </div>
      )}

      {latest && (latest.status === "pending" || latest.status === "processing") && (
        <p className="mt-3 flex items-center gap-1.5 text-[12px] text-muted"><Loader2 size={12} className="animate-spin" />
          {t("Bot sedang melukis {n} slaid; ia masuk ke post ini sendiri selagi post ini draf.",
            ["The bot is drawing {n} slide; it comes into this post by itself while it is a draft.", "The bot is drawing {n} slides; they come into this post by themselves while it is a draft."],
            { n: latest.meta?.slides?.length || "" })}</p>
      )}
      {latest && latest.status === "error" && (
        <p className="mt-3 [overflow-wrap:anywhere] rounded-tile bg-danger/5 p-2 text-[12px] text-danger">{t("Lukisan terakhir gagal:", "Last drawing failed:")} {latest.error}</p>
      )}

      {latestDone && (
        <div className="mt-3">
          <div className="flex gap-2 overflow-x-auto pb-1" style={{ scrollSnapType: "x mandatory" }}>
            {(latestDone.meta?.slide_urls || []).map((u, i) => (
              <a key={u} href={u} target="_blank" rel="noopener noreferrer" className="relative shrink-0" style={{ scrollSnapAlign: "start" }}
                title={t("Slaid {n}: buka saiz penuh", "Slide {n}: open full size", { n: i + 1 })}>
                <img src={u} alt={t("Slaid {n}", "Slide {n}", { n: i + 1 })} className={`${post.stream === "linkedin" ? "h-[120px] w-24" : "h-24 w-24"} rounded-tile border border-line object-cover`} />
                <span className="absolute left-1 top-1 rounded bg-ink/80 px-1 text-[10px] text-bg">{i + 1}</span>
              </a>
            ))}
          </div>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted">
            {t("{n} slaid dilukis", ["{n} slide drawn", "{n} slides drawn"], { n: latestDone.meta?.count })}
            {latestDone.meta?.bg_missing ? ` · ${latestDone.meta.bg_missing}`
              : latestDone.meta?.bg_used ? ` · ${t("atas gambar post", "on the post picture")}` : ` · ${t("atas kertas", "on paper")}`}
            <a href={latestDone.meta?.slide_urls?.[0]} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 text-accent"><ExternalLink size={10} /> {t("buka", "open")}</a>
          </p>
          {drawnStale && <p className="mt-1 text-[12px] text-warn">
            {t("Slaid di atas telah diubah sejak dilukis. Tekan Jana slaid supaya gambar membawa perkataan yang sama.",
              "The slides above changed since they were drawn. Press Generate slides so the pictures carry the same words.")}</p>}
          {!attachedIds.includes(latestDone.id) && !locked && (
            <p className="mt-1 text-[12px] text-muted">
              {t("Set ini belum dilampirkan pada post (post bukan draf ketika ia siap).",
                "This set is not attached to the post yet (the post was not a draft when it finished).")}{" "}
              <button type="button" className="font-medium text-accent underline" onClick={() => onUse(latestDone.id)}>
                {t("Guna set ini", "Use this set")}</button></p>
          )}
        </div>
      )}
    </div>
  );
}

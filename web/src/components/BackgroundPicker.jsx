import { useState } from "react";
import { Check, ImageIcon, Loader2, Sparkles, X } from "lucide-react";
import { useLang } from "../lib/i18n";
import { GROUNDS } from "../lib/cards/library";
import { UnsplashCredit, UnsplashResults, UnsplashSearch } from "./Unsplash";
import Button from "./ui/Button";
import { Segmented, TextArea } from "./ui/Field";

/* One place to choose what a card is drawn on (Wan, 3 Oct 2026: "allow us to choose background from unsplashed or image
   generate"). Three sources in one window, for the whole set or for one slide:
     - the post's own pictures (Unsplash picks, generated, uploaded) and Wan's photographs: one click;
     - a new Unsplash search (the worker answers in about a minute, the photographer is credited);
     - a new generated picture from a prompt (the same job the Pictures section queues).
   A search or a generation is not instant, so the window stays useful while it works: the pictures that arrive show up
   under "Pictures" by themselves and one click puts them behind the card. */

/** target: {i: null} the whole set, or {i: n} slide n+1. current: the bg token in force there. */
export default function BackgroundPicker({ open, onClose, target, current, nSlides, onChoose, picker }) {
  const { t } = useLang();
  const [tab, setTab] = useState("pictures");
  const [prompt, setPrompt] = useState("");
  const [all, setAll] = useState(false);
  if (!open) return null;
  const slide = target && target.i !== null && target.i !== undefined;
  const { pictures = [], unsplashOpen = [], pending = [], user, post, onQueued, onGenerate, busy, onToast = () => {} } = picker || {};
  const choose = (token) => { onChoose(token, slide && all); };
  const Tile = ({ token, url, label, sub }) => (
    <button type="button" onClick={() => choose(token)} title={label}
      className={`relative min-w-0 overflow-hidden rounded-tile border text-left ${current === token ? "border-accent ring-2 ring-accent/40" : "border-line hover:border-accent"}`}>
      <span className="block bg-surface-2" style={{ aspectRatio: "1 / 1" }}>
        {url ? <img src={url} alt={label} loading="lazy" className="h-full w-full object-cover" />
          : <span className="grid h-full w-full place-items-center text-[11px] text-muted">{label}</span>}
      </span>
      <span className="block truncate px-1.5 py-1 text-[11px] text-muted">{sub || label}</span>
      {current === token && <span className="absolute right-1 top-1 rounded-full bg-accent p-0.5 text-bg"><Check size={11} /></span>}
    </button>
  );

  return (
    <div className="fixed inset-0 z-[55] flex items-start justify-center overflow-y-auto bg-ink/45 p-3 pt-10 sm:p-6 sm:pt-14"
      onMouseDown={(e) => { e.currentTarget.dataset.down = e.target === e.currentTarget ? "1" : ""; }}
      onClick={(e) => { if (e.target === e.currentTarget && e.currentTarget.dataset.down === "1") onClose(); }}>
      <div className="w-full max-w-3xl rounded-card border border-line bg-surface p-4 shadow-lift sm:p-5" role="dialog" aria-modal="true"
        aria-label={t("Pilih latar", "Choose a background")} onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center gap-3">
          <h3 className="min-w-0 flex-1 text-lg">
            {slide ? t("Latar slaid {n}", "Background for slide {n}", { n: target.i + 1 }) : t("Latar untuk semua slaid", "Background for the whole set")}</h3>
          <button type="button" onClick={onClose} aria-label={t("Tutup", "Close")} className="rounded-full p-1.5 text-muted hover:bg-surface-2 hover:text-ink"><X size={16} /></button>
        </div>
        <Segmented value={tab} onChange={setTab} options={[["pictures", t("Gambar", "Pictures")], ["unsplash", "Unsplash"], ["generate", t("Jana gambar", "Generate")]]} />
        {slide && nSlides > 1 && (
          <label className="mt-3 flex items-center gap-2 text-[12px]">
            <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} />
            {t("Guna pilihan ini pada semua {n} slaid", "Use my choice on all {n} slides", { n: nSlides })}</label>
        )}

        {tab === "pictures" && (
          <div className="mt-3 space-y-3">
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-5">
              {slide && <Tile token="" label={t("Ikut set", "As the set")} />}
              <Tile token="none" label={t("Kertas (tiada gambar)", "Paper (no picture)")} />
              {pictures.map((m, i) => (
                <Tile key={m.id} token={m.id} url={m.url} label={m.label || t("Gambar {n}", "Picture {n}", { n: i + 1 })}
                  sub={m.credit ? `${t("Foto oleh", "Photo by")} ${m.credit}` : m.label} />
              ))}
            </div>
            {!pictures.length && (
              <p className="text-[12px] text-muted">{t("Post ini belum ada gambar. Cari di Unsplash atau jana satu: ia muncul di sini sendiri.",
                "This post has no pictures yet. Search Unsplash or generate one: it appears here by itself.")}</p>
            )}
            <div>
              <p className="mb-1 flex items-center gap-1.5 text-[11px] font-medium text-muted"><ImageIcon size={12} /> {t("Foto Wan", "Wan's own photographs")}</p>
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-6">
                {GROUNDS.map((g) => <Tile key={g.k} token={`lib:${g.k}`} url={g.url} label={g.name} />)}
              </div>
            </div>
          </div>
        )}

        {tab === "unsplash" && (
          <div className="mt-3 space-y-2">
            <UnsplashSearch user={user} postId={post?.id} ideaId={post?.idea_id} stream={post?.stream} onToast={onToast} onQueued={onQueued} compact />
            {unsplashOpen.map((m) => (
              <div key={m.id} className="rounded-tile border border-line"><UnsplashResults row={m} onToast={onToast} onPicked={onQueued} /></div>
            ))}
            <p className="text-[12px] text-muted">{t("Selepas anda memilih foto, ia disimpan dalam kira-kira seminit, kemudian muncul di tab Gambar. Klik di sana untuk meletakkannya di belakang kad.",
              "After you pick a photo it is stored in about a minute, then it appears under Pictures. Click it there to put it behind the card.")}</p>
            {pictures.filter((m) => m.credit).slice(0, 4).map((m) => (
              <UnsplashCredit key={m.id} row={{ meta: { credit: m.creditMeta } }} className="mt-0.5" />))}
          </div>
        )}

        {tab === "generate" && (
          <div className="mt-3 space-y-2">
            <TextArea rows={3} value={prompt} maxLength={400} onChange={(e) => setPrompt(e.target.value)}
              placeholder={t("Terangkan gambar latar (Inggeris lebih tepat), cth: soft-focus cosmetic laboratory bench, teal tones, no people, no text",
                "Describe the background (English is more exact), e.g. soft-focus cosmetic laboratory bench, teal tones, no people, no text")} />
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" size="sm" disabled={busy || !prompt.trim()}
                onClick={async () => { const ok = await onGenerate?.(prompt.trim()); if (ok) setPrompt(""); }}>
                {busy ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />} {t("Jana gambar", "Generate picture")}</Button>
              <span className="text-[11px] text-muted">{t("Mengambil kira-kira seminit. Ia muncul di tab Gambar bila siap.",
                "Takes about a minute. It appears under Pictures when it is ready.")}</span>
            </div>
            {pending.length > 0 && (
              <ul className="space-y-1 text-[12px] text-muted">
                {pending.map((m) => (
                  <li key={m.id} className="flex items-center gap-1.5"><Loader2 size={12} className="animate-spin" />
                    <span className="min-w-0 truncate">{m.prompt}</span></li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="mt-4 flex justify-end"><Button type="button" size="sm" variant="ghost" onClick={onClose}>{t("Siap", "Done")}</Button></div>
      </div>
    </div>
  );
}

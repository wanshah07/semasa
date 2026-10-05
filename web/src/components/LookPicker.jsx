import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Loader2, Palette, Plus } from "lucide-react";
import { LOOKS, ensureFonts, isStudioLook, renderSlides, setLogo } from "../lib/cards/studio";
import { GROUNDS } from "../lib/cards/library";
import { resolveLook, useDesigns } from "../lib/designs";
import { useLang } from "../lib/i18n";
import ImageLightbox, { useLightbox } from "./ImageLightbox";

/* Pick how a carousel (or a single card) is drawn (Wan, 26 Sep 2026: "copy the code design that already in ws.regulab
   studio, so we can choose the design"). Semasa's own drawing, or one of Studio's three: Grid, Info ERA, Photo.
   Studio's looks are previewed here with the SAME file the worker draws with (web/src/lib/cards/studio.js), so a
   slide the preview calls too full is the slide the worker would refuse: the parent is told, and blocks Generate. */

const BASE = `${import.meta.env.BASE_URL}cards/`;
const NO_PICTURE = "This design is built on a picture";

function sizeOf(stream, size) {
  if (Array.isArray(size)) return size;
  return stream === "linkedin" ? [1080, 1350] : [1080, 1080];
}

/* Draw slides in one look, debounced, in this browser. Nothing leaves the page. */
function usePreview(slides, opts, enabled) {
  const [state, setState] = useState({ pics: [], busy: false, error: "" });
  const key = JSON.stringify([slides, opts, enabled]);
  useEffect(() => {
    if (!enabled || !slides.length) { setState({ pics: [], busy: false, error: "" }); return undefined; }
    let live = true;
    setState((s) => ({ ...s, busy: true }));
    const timer = setTimeout(async () => {
      try {
        setLogo(`${BASE}logo.png`);
        await ensureFonts(BASE);
        const pics = await renderSlides(slides, opts);
        if (live) setState({ pics, busy: false, error: "" });
      } catch (e) {
        if (live) setState({ pics: [], busy: false, error: e?.message || String(e) });
      }
    }, 350);
    return () => { live = false; clearTimeout(timer); };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return state;
}

/* No words yet (a post with no slides written): the designs are shown on sample words rather than as blank tiles. */
function sampleWords(stream) {
  const en = stream === "linkedin";
  return [
    { title: en ? "Your *headline* here" : "Tajuk *anda* di sini", points: [en ? "One supporting line under the title." : "Satu baris sokongan di bawah tajuk."] },
    { title: en ? "What the rule says" : "Apa kata peraturan", points: en ? ["One fact per slide.", "Short and cited."] : ["Satu fakta satu slaid.", "Ringkas dan bersumber."] },
  ];
}

/* One saved design (My designs) as a tile: its cover on the words in hand, drawn by the same code as everything else. */
function DesignTile({ d, opts, cover, ratio, on, onPick, disabled, defaultId }) {
  const { t } = useLang();
  const g = d.bg && d.bg.startsWith("lib:") ? GROUNDS.find((x) => `lib:${x.k}` === d.bg) : null;
  const pic = usePreview(cover, { ...opts, bg: g?.url || opts.bg, look: d.look, design: d }, true).pics[0];
  return (
    <button type="button" role="radio" aria-checked={on} disabled={disabled} onClick={onPick}
      className={`min-w-0 overflow-hidden rounded-tile border text-left transition ${on ? "border-accent ring-2 ring-accent/30" : "border-line hover:border-ink/30"} disabled:opacity-50`}>
      <div className="relative w-full bg-surface-2" style={{ aspectRatio: ratio }}>
        {pic ? <img src={pic.url} alt={d.name} className="h-full w-full object-cover" />
          : <span className="absolute inset-0 flex items-center justify-center text-muted"><Loader2 size={16} className="animate-spin" /></span>}
      </div>
      <div className="px-2 py-1.5">
        <div className="truncate text-sm font-semibold leading-none lg:text-[12px]">{d.name}</div>
        <div className="mt-1 text-[10.5px] leading-snug text-muted">{defaultId === d.id ? t("reka bentuk lalai", "default design") : t("reka bentuk saya", "my design")}</div>
      </div>
    </button>
  );
}

export default function LookPicker({ value, onChange, slides: given, sample: givenSample = false, stream = "regulab", eyebrow = "",
  citation = "", bgUrl = "", bgChosen = false, size = null, full = true, onBlocked, disabled = false, mascots = [],
  fit = false, onFit = null }) {
  const { t, lang } = useLang();
  const { designs, defaultId } = useDesigns();
  const chosen = resolveLook(value, designs);                    // "d:<id>" is one of My designs: its family, colours and layouts
  const sample = givenSample || !given.length;
  const slides = given.length ? given : sampleWords(stream);
  const [W, H] = sizeOf(stream, size);
  const ratio = `${W} / ${H}`;
  const opts = { stream, eyebrow, citation, bg: bgUrl || "", size: Array.isArray(size) ? size : undefined,
    mascots: mascots.map((m) => ({ k: m.k, url: m.url })), ...(fit ? { fit: true } : {}) };
  const cover = slides.slice(0, 1);
  // one cover per Studio look for the tiles, and the whole set in the chosen look
  const grid = usePreview(cover, { ...opts, look: "grid" }, true);
  const era = usePreview(cover, { ...opts, look: "era" }, true);
  const photo = usePreview(cover, { ...opts, look: "photo" }, true);
  const tiles = { grid, era, photo };
  const dBg = chosen.design?.bg && chosen.design.bg.startsWith("lib:") ? GROUNDS.find((x) => `lib:${x.k}` === chosen.design.bg)?.url : "";
  const all = usePreview(slides, { ...opts, look: chosen.look, bg: bgUrl || dBg || "", ...(chosen.design ? { design: chosen.design } : {}) },
    full && isStudioLook(chosen.look));
  const box = useLightbox(all.pics.map((p, i) => ({ url: p.url, title: t("Slaid {n} daripada {m}", "Slide {n} of {m}", { n: i + 1, m: all.pics.length }) })));

  // Studio's own warnings, minus "no picture" while a picture is chosen but not made yet (the worker waits for it)
  const problems = useMemo(() => all.pics.map((p, i) => ({ n: i + 1,
    warn: (p.warn || []).filter((w) => !(bgChosen && w.startsWith(NO_PICTURE))) })).filter((p) => p.warn.length),
  [all.pics, bgChosen]);
  const photoNeedsPicture = chosen.look === "photo" && !bgChosen && !chosen.design?.bg;
  const blocked = photoNeedsPicture ? "photo" : isStudioLook(chosen.look) && !sample && problems.length ? "full" : null;
  useEffect(() => { onBlocked?.(blocked); }, [blocked]); // eslint-disable-line react-hooks/exhaustive-deps

  const name = (l) => (lang === "bm" ? l.bm : l.en);
  const hint = (l) => (lang === "bm" ? l.hintBm : l.hintEn);

  return (
    <div className="min-w-0">
      <p className="flex items-center gap-1.5 text-[12px] font-medium"><Palette size={13} /> {t("Reka bentuk slaid", "Slide design")}
        {sample && <span className="font-normal text-muted">· {t("pratonton dengan contoh perkataan", "preview with sample words")}</span>}</p>
      <div role="radiogroup" aria-label={t("Reka bentuk slaid", "Slide design")} className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4 lg:gap-2">
        {LOOKS.map((l) => {
          const on = value === l.k;
          const tile = tiles[l.k];
          const pic = tile?.pics?.[0];
          const needs = l.k === "photo" && !bgChosen;
          return (
            <button type="button" key={l.k} role="radio" aria-checked={on} disabled={disabled}
              onClick={() => onChange(l.k)} title={hint(l)}
              className={`min-w-0 overflow-hidden rounded-tile border text-left transition ${on ? "border-accent ring-2 ring-accent/30" : "border-line hover:border-ink/30"} disabled:opacity-50`}>
              <div className="relative w-full bg-surface-2" style={{ aspectRatio: ratio }}>
                {l.k === "classic" ? (
                  <div className="flex h-full w-full flex-col justify-center gap-1 bg-[#FAF7F2] p-3">
                    <span className="h-1.5 w-8 rounded bg-[#B0792A]" />
                    <span className="line-clamp-3 [overflow-wrap:anywhere] font-serif text-2xl font-semibold leading-tight text-[#1C1917] lg:text-[13px]">
                      {(cover[0]?.title || "Semasa").replace(/\*/g, "")}</span>
                  </div>
                ) : pic ? (
                  <img src={pic.url} alt={name(l)} className="h-full w-full object-cover" />
                ) : (
                  <span className="absolute inset-0 flex items-center justify-center text-muted">
                    {tile?.busy ? <Loader2 size={16} className="animate-spin" /> : "·"}</span>
                )}
                {needs && <span className="absolute inset-x-1 bottom-1 rounded bg-ink/80 px-1 py-0.5 text-center text-[10px] text-bg">
                  {t("perlu gambar latar", "needs a background")}</span>}
              </div>
              <div className="px-2 py-1.5">
                <div className="text-sm font-semibold leading-none lg:text-[12px]">{name(l)}</div>
                <div className="mt-1 line-clamp-2 text-[12px] leading-snug text-muted lg:text-[10.5px]">{hint(l)}</div>
              </div>
            </button>
          );
        })}
        {designs.map((d) => {
          const r = resolveLook(`d:${d.id}`, designs);
          return (
            <DesignTile key={d.id} d={r.design ? { ...r.design, id: d.id, name: d.name } : { look: "grid", id: d.id, name: d.name }}
              opts={opts} cover={cover} ratio={ratio} on={value === `d:${d.id}`} defaultId={defaultId} disabled={disabled} onPick={() => onChange(`d:${d.id}`)} />
          );
        })}
        {!disabled && (
          <button type="button" onClick={() => window.dispatchEvent(new Event("semasa:my-designs"))}
            className="grid min-w-0 place-items-center rounded-tile border border-dashed border-line p-3 text-center text-[12px] text-accent hover:border-accent"
            style={{ minHeight: "6rem" }}>
            <span><Plus size={16} className="mx-auto mb-1" />{t("Reka bentuk saya daripada gambar rujukan", "My design from a reference picture")}</span>
          </button>
        )}
      </div>

      {onFit && isStudioLook(chosen.look) && (
        <label className="mt-2 flex cursor-pointer items-start gap-2 text-[12px]">
          <input type="checkbox" checked={!!fit} disabled={disabled} onChange={(e) => onFit(e.target.checked)} className="mt-0.5 accent-[var(--accent)]" />
          <span><span className="font-medium">{t("Padankan reka bentuk dengan setiap slaid", "Fit the design to each slide")}</span>
            <span className="block text-muted">{t("Dalam keluarga yang dipilih, setiap slaid mendapat templat yang sesuai dengan isinya: angka, mitos dan fakta, langkah, senarai semak atau panel bernombor. Dimatikan, semua slaid tengah guna satu templat. Templat yang anda pilih sendiri pada satu slaid sentiasa menang.",
              "Inside the chosen family, each slide gets the template that suits its words: a figure, myth and fact, steps, a checklist or numbered panels. Off, every middle slide uses one template. A template you pick yourself on a slide always wins.")}</span></span>
        </label>
      )}

      {photoNeedsPicture && (
        <p className="mt-2 flex items-start gap-1.5 text-[12px] text-warn"><AlertTriangle size={13} className="mt-0.5 shrink-0" />
          {t("Foto dilukis di atas gambar. Pilih latar (gambar post atau muat naik) dahulu, atau pilih Grid / Info ERA.",
            "Photo is drawn on a picture. Choose a background (the post's picture or an upload) first, or pick Grid / Info ERA.")}</p>
      )}

      {full && isStudioLook(chosen.look) && slides.length > 0 && (
        <div className="mt-3">
          <p className="flex items-center gap-1.5 text-[11px] text-muted">
            {all.busy && <Loader2 size={11} className="animate-spin" />}
            {sample ? t("Contoh sahaja: bot menulis slaid sebenar kemudian, dalam reka bentuk ini.",
              "A sample only: the bot writes the real slides later, in this design.")
              : t("Pratonton setiap slaid, dilukis dengan kod yang sama seperti bot.", "Every slide previewed, drawn by the same code as the bot.")}
            {bgChosen && !bgUrl && ` ${t("Gambar latar belum siap: pratonton tanpa gambar.", "The background is not ready: previewed without it.")}`}
          </p>
          <div className="mt-1.5 flex gap-2 overflow-x-auto pb-1" style={{ scrollSnapType: "x mandatory" }}>
            {all.pics.map((p, i) => {
              const bad = problems.find((x) => x.n === i + 1);
              return (
                <button type="button" key={i} onClick={() => box.open(i)} className="relative shrink-0 cursor-zoom-in" style={{ scrollSnapAlign: "start" }}
                  title={bad ? bad.warn.join(" ") : t("Slaid {n}: klik untuk baca perkataan pada kad", "Slide {n}: click to read the words on the card", { n: i + 1 })}>
                  <img src={p.url} alt={t("Slaid {n}", "Slide {n}", { n: i + 1 })}
                    className={`h-72 max-w-[80vw] rounded-tile border object-cover sm:h-64 lg:h-36 ${bad ? "border-danger ring-2 ring-danger/40" : "border-line"}`} style={{ aspectRatio: ratio }} />
                  <span className="absolute left-1 top-1 rounded bg-ink/80 px-1 text-[10px] text-bg">{i + 1}</span>
                </button>
              );
            })}
          </div>
          {all.error && <p className="mt-1 [overflow-wrap:anywhere] text-[12px] text-danger">{t("Pratonton gagal:", "Preview failed:")} {all.error}</p>}
          {!sample && problems.length > 0 && (
            <p className="mt-1 flex items-start gap-1.5 text-[12px] text-danger"><AlertTriangle size={13} className="mt-0.5 shrink-0" />
              <span>{t("Terlalu penuh untuk reka bentuk ini: slaid {n}. Pendekkan, pecahkan kepada dua slaid, atau pilih reka bentuk lain. Tiada perkataan dipotong.",
                "Too full for this design: slide {n}. Shorten it, split it into two slides, or pick another design. No word is ever cut.",
                { n: problems.map((p) => p.n).join(", ") })}</span></p>
          )}
        </div>
      )}
      <ImageLightbox {...box.props} />
    </div>
  );
}

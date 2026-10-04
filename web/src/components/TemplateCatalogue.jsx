import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { ensureFonts, renderSlides, setLogo } from "../lib/cards/studio";
import { GROUNDS, MASCOTS, TEMPLATES } from "../lib/cards/library";
import { useLang } from "../lib/i18n";

/* Studio's design catalogue (tplSample / tplGrid): every template drawn on sample words shaped for it, so a design is
   chosen by sight. Each one is drawn once per page and kept. The samples are Studio's own. */
const BASE = `${import.meta.env.BASE_URL}cards/`;
const SAMPLE = { eyebrow: "Cosmetics (NPRA)", title: "Produk dinotifikasi bukan bermakna produk diluluskan.",
  lead: "Notifikasi ialah pemberitahuan kepada NPRA, bukan kelulusan.", chip: "NPRA", footnote: "Annex III" };
const SHAPE = {
  g_title: { note: "Semak sumber sebelum semak claim." },
  g_stat: { title: "tempoh purata satu permohonan lengkap", points: ["245", "hari"], footnote: "Cosmetic Guidelines Malaysia" },
  g_bars: { title: "Had *maksimum* ikut pasaran", lead: "angka contoh", chip: "ACD",
    points: ["Malaysia (ACD) | 0.5 | 0.5%", "Kesatuan Eropah | 0.4 | 0.4%", "China (CSAR) | 0.3 | 0.3%"] },
  g_rows: { title: "Empat *dokumen* wajib", lead: "", points: ["Surat kebenaran pengilang | Daripada pengeluar produk asal.",
    "Senarai penuh INCI | Setiap bahan, tiada terkecuali.", "Artwork label siap | Bahasa dan format yang betul."] },
  g_table: { title: "Tiga *peringkat* tindakan", lead: "", points: ["I | Surat amaran | Pinda atau henti iklan.",
    "II | Pembatalan | Produk tidak lagi sah dijual.", "III | Rujukan | Penguatkuasa KKM atau MCMC."] },
  e_hook: { eyebrow: "Info ERA", title: "Kenapa notifikasi boleh *ditarik balik*", lead: "Sedangkan produk sudah ada di pasaran?",
    points: ["Apa yang dilanggar?", "Siapa yang menyemak?", "Berapa kosnya?"] },
  e_explain: { eyebrow: "Info ERA", title: "Apa yang disemak?", lead: "", note: "Semak sumber sebelum semak claim.",
    points: ["Senarai INCI | Setiap bahan mesti padan dengan formula.", "Artwork label | Nama, kuantiti dan amaran."] },
  e_flow: { eyebrow: "Info ERA", title: "Selepas aduan, apa jadi?", lead: "", note: "Kos tarik balik ditanggung syarikat.",
    points: ["Aduan diterima | Fail siasatan dibuka.", "Sampel diambil | Produk diuji semula.", "Notifikasi digantung | Tidak lagi sah dijual."] },
  e_vs: { eyebrow: "Info ERA", title: "Kos *pematuhan* vs kos tarik balik", lead: "", note: "Angka ini belum termasuk…", chip: "Contoh",
    points: ["Ujian dan dokumen awal", "RM8,000 | Tarik balik satu lot | RM240,000", "Kos hentian pengeluaran", "Kos pampasan pengedar"] },
  g_check: { title: "Semak *sebelum* hantar", lead: "", points: ["Senarai penuh INCI | Setiap bahan, tiada terkecuali.", "Artwork label siap | Bahasa dan format yang betul.", "Surat kebenaran pengilang"] },
  g_myth: { title: "Notifikasi *bukan* kelulusan", lead: "", points: ["Produk ada nombor, jadi sudah diluluskan | Nombor hanya bukti pemberitahuan diterima", "NPRA menguji setiap produk | NPRA menyemak maklumat, bukan formula"] },
  g_steps: { title: "Dari borang ke *pasaran*", lead: "", points: ["Sediakan PIF | Dokumen produk lengkap.", "Hantar notifikasi | Melalui QUEST3+.", "Terima nombor | Kemudian boleh dijual."] },
  e_myth: { eyebrow: "Info ERA", title: "Satu *mitos* yang mahal", lead: "", note: "Semak sumber sebelum semak claim.", points: ["Produk bernombor bermakna sudah diluluskan | Nombor notifikasi hanya bukti pemberitahuan, bukan kelulusan."] },
  e_check: { eyebrow: "Info ERA", title: "Sebelum *notifikasi*", lead: "", note: "Satu tiada, satu lot tertahan.", points: ["Senarai INCI | Setiap bahan mesti padan dengan formula.", "Artwork label | Nama, kuantiti dan amaran.", "Surat pengilang"] },
  e_stat: { eyebrow: "Info ERA", title: "Tempoh *purata* satu permohonan", lead: "Daripada hantar hingga nombor diterima.", note: "Angka contoh.", points: ["14", "hari bekerja"] },
  p_stat: { photo: true, title: "Tempoh purata satu permohonan lengkap", lead: "", points: ["245", "hari"] },
  p_list: { photo: true, title: "Empat *dokumen* wajib", lead: "", points: ["Surat kebenaran pengilang | Daripada pengeluar asal.", "Senarai penuh INCI | Setiap bahan.", "Artwork label siap | Bahasa yang betul."] },
  p_split: { photo: true, title: "Notifikasi bukan kelulusan", lead: "Nombor hanya bukti pemberitahuan diterima.", points: ["Semak maklumat produk", "Bukan ujian formula"] },
  p_title: { photo: true },
  p_fact: { photo: true, lead: "", points: ["Surat kebenaran pengilang", "Senarai penuh INCI", "Artwork label siap"] },
  p_quote: { photo: true, title: "Notifikasi bukan kelulusan.", lead: "Cosmetic Guidelines Malaysia, NPRA" },
};
const cache = new Map();              // template -> Promise<url>

function thumb(k, stream) {
  const key = `${k}:${stream}`;
  if (!cache.has(key)) {
    const { photo, ...shape } = SHAPE[k] || {};
    const slide = { ...SAMPLE, points: [], ...shape, template: k, ...(photo ? { bg_url: GROUNDS[0]?.url } : {}) };
    cache.set(key, (async () => {
      setLogo(`${BASE}logo.png`);
      await ensureFonts(BASE);
      const [r] = await renderSlides([slide], { look: "grid", stream, mascots: MASCOTS.map((m) => ({ k: m.k, url: m.url })) });
      return r?.url || "";
    })().catch(() => ""));
  }
  return cache.get(key);
}

export default function TemplateCatalogue({ value, onPick, stream = "regulab", disabled = false }) {
  const { t, lang } = useLang();
  const [urls, setUrls] = useState({});
  useEffect(() => {
    let live = true;
    (async () => {
      for (const tpl of TEMPLATES) {
        const u = await thumb(tpl.k, stream);
        if (!live) return;
        setUrls((x) => ({ ...x, [tpl.k]: u }));
      }
    })();
    return () => { live = false; };
  }, [stream]);
  const groups = [["grid", "Grid"], ["era", "Info ERA"], ["photo", t("Foto", "Photo")]];
  const ratio = stream === "linkedin" ? "1080 / 1350" : "1 / 1";
  return (
    <div className="space-y-2">
      {groups.map(([g, name]) => (
        <div key={g}>
          <p className="text-[10.5px] font-semibold uppercase tracking-wide text-muted">{name}</p>
          <div role="radiogroup" aria-label={name} className="mt-1 flex gap-2 overflow-x-auto pb-1" style={{ scrollSnapType: "x mandatory" }}>
            {TEMPLATES.filter((x) => x.group === g).map((x) => (
              <button key={x.k} type="button" role="radio" aria-checked={value === x.k} disabled={disabled} onClick={() => onPick(value === x.k ? "" : x.k)}
                title={t(x.hint, x.hintEn)} style={{ scrollSnapAlign: "start" }}
                className={`w-28 shrink-0 overflow-hidden rounded-tile border text-left ${value === x.k ? "border-accent ring-2 ring-accent/30" : "border-line hover:border-ink/30"}`}>
                <div className="relative w-full bg-surface-2" style={{ aspectRatio: ratio }}>
                  {urls[x.k] ? <img src={urls[x.k]} alt="" className="h-full w-full object-cover" />
                    : <span className="absolute inset-0 grid place-items-center text-muted"><Loader2 size={14} className="animate-spin" /></span>}
                </div>
                <span className="block truncate px-1.5 py-1 text-[10.5px]">{(lang === "bm" ? x.name : x.en).split(" · ")[1]}</span>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
